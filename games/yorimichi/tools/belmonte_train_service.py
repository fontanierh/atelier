"""The Belmonte train service as data for Unreal: the line, the consist and each train's position over one cycle.

    uv run atelier build yorimichi world.belmonte_train_service    # writes build/yorimichi/belmonte-train/service/

Reads the approved route (belmonte-train/route/route.json), the assembled consist (assembly/consist.json) and each
vehicle's placements (<vehicle>/<vehicle>-placements.json), all from the Train Builder's outputs, and writes
service.json, which `import_belmonte_train.py` copies to Content/Data/belmonte_train/ for ABelmonteTrainService.

- The line: the route's samples (every 10 m of chainage) and the passing loop's second track, in Unreal centimetres
  (Blender metres, y flipped). The loop's height follows the main line at the same chainage.
- The consist: each vehicle's offset from the consist centre, its bogie centres, its fixed collision boxes (UCX), its
  switchable boxes (doors and gangway locks, kept by name) and its furniture as instances per asset.
- The service: summary.service.schedule when the route has one (legs with departures, loop stops and arrivals),
  otherwise two trains half a cycle apart. Each train's chainage is sampled every DT seconds over one cycle; the game
  interpolates. Runs follow the route's per-direction speed profile; a stop in the loop brakes into it and starts out
  of it at the rates the profiles start and end with, and each run is stretched to its scheduled time.

The train's reference point is the consist centre: the speed profiles start and end at the station centres
(chainage 100 and length - 100), and a 131 m consist centred there stands within the 160 m platforms.
"""
import argparse
import bisect
import hashlib
import json
import math
import os
import sys
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world'))
import yori  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gltf_subset as G  # noqa: E402

TRAIN = yori.OUT / 'belmonte-train'
OUTPUT = TRAIN / 'service' / 'service.json'
MESH_ROOT = '/Game/BelmonteTrain'
DT = 0.5                  # seconds between position samples
DEFAULT_DWELL = 90.0      # seconds at a terminus when the route has no schedule
CLOCK_LEAD = 60.0         # the game starts this long before train A leaves Hidamari
SMALL_ITEM = 0.6          # metres: furniture no larger than this casts no shadow
RENDER = {
    # Static mesh LOD screen sizes (LOD0 from 0.6 up, LOD1 from 0.15, LOD2 below), the cull distance and the
    # furniture draw distances, in Unreal cm. Interior furniture is only seen through the windows close by.
    'screen_sizes': [1.0, 0.6, 0.15],
    'min_screen_size': 0.01,
    'cull_cm': 250000.0,
    'furniture_cull_cm': 6000.0,
    'small_furniture_cull_cm': 2500.0,
}


def to_ue(x, y, z):
    return [round(x * 100.0, 2), round(-y * 100.0, 2), round(z * 100.0, 2)]


def mesh_path(name):
    return f'{MESH_ROOT}/{name}.{name}'


def furniture_mesh(asset):
    name = 'SM_BTF_' + ''.join(part.capitalize() for part in asset.split('-'))
    return f'{MESH_ROOT}/Furniture/{name}.{name}'


def box_ue(box):
    """[x0, x1, y0, y1, z0, z1] metres in the vehicle frame -> [min xyz, max xyz] Unreal cm (y flipped)."""
    x0, x1, y0, y1, z0, z1 = box
    return [round(x0 * 100, 2), round(-y1 * 100, 2), round(z0 * 100, 2),
            round(x1 * 100, 2), round(-y0 * 100, 2), round(z1 * 100, 2)]


# ---------------------------------------------------------------- the line

def line(route):
    samples = route['samples']
    main = [[round(s['s'], 3), *to_ue(s['x'], s['y'], s['rail_z'])] for s in samples]
    chain = [s['s'] for s in samples]

    def rail_z(c):
        i = min(max(bisect.bisect_right(chain, c) - 1, 0), len(chain) - 2)
        a, b = samples[i], samples[i + 1]
        f = (c - a['s']) / (b['s'] - a['s'])
        return a['rail_z'] + f * (b['rail_z'] - a['rail_z'])
    loop = route.get('passing_loop') or {}
    points = [[round(c, 3), *to_ue(x, y, rail_z(c))] for c, x, y in loop.get('second_track', [])]
    return {'main': main, 'loop': {'start': loop.get('start'), 'end': loop.get('end'), 'points': points},
            'viewpoints': viewpoints(samples)}


def viewpoints(samples, shortest=150.0):
    """Stretches where the rails are at or above today's ground (embankments, the viaduct), longest first: until the
    track worker carves the cuttings and tunnels, these are where a train can be seen."""
    stretches, run = [], []
    for s in samples + [None]:
        if s is not None and s['rail_z'] >= s['ground_z'] - 0.3:
            run.append(s)
            continue
        if run and run[-1]['s'] - run[0]['s'] >= shortest:
            middle = (run[0]['s'] + run[-1]['s']) / 2
            stretches.append({'s': round(middle, 1), 'start': run[0]['s'], 'end': run[-1]['s'],
                              'class': max({r['class'] for r in run}, key=[r['class'] for r in run].count)})
        run = []
    return sorted(stretches, key=lambda v: v['start'] - v['end'])


# ---------------------------------------------------------------- runs

class Profile:
    """A speed profile [chainage, seconds, km/h] as speed (m/s) against chainage, ending at a stop at `stop`."""

    def __init__(self, rows, stop):
        rows = [(float(s), float(t), float(v) / 3.6) for s, t, v in rows]
        if rows[-1][2] > 0 and abs(stop - rows[-1][0]) > 1e-6:
            rows.append((stop, rows[-1][1] + 2 * abs(stop - rows[-1][0]) / rows[-1][2], 0.0))
        self.rows = rows
        self.start, self.stop = rows[0][0], rows[-1][0]
        self.sign = 1 if self.stop > self.start else -1
        ordered = sorted((s, v) for s, _, v in rows)
        self.s = [s for s, _ in ordered]
        self.v = [v for _, v in ordered]
        # The rates the profile starts and stops at: a stop in the loop uses the same.
        first, last = rows[1], rows[-2]
        self.accel = min(max(first[2] ** 2 / (2 * abs(first[0] - rows[0][0])), .2), 1.5)
        self.brake = min(max(last[2] ** 2 / (2 * abs(rows[-1][0] - last[0])), .2), 1.5)
        self.seconds = rows[-1][1]

    def speed(self, c):
        i = bisect.bisect_right(self.s, c)
        if i <= 0:
            return self.v[0]
        if i >= len(self.s):
            return self.v[-1]
        a, b = self.s[i - 1], self.s[i]
        # v^2 is linear in distance under a constant rate: interpolating v itself made the last samples into a stop a
        # slow exponential crawl, and warping the run to the timetable then sped up everything else.
        f = (c - a) / (b - a)
        return math.sqrt(max(self.v[i - 1] ** 2 + f * (self.v[i] ** 2 - self.v[i - 1] ** 2), 0.))

    def run(self, origin, target):
        """(seconds, chainage) from a stop at `origin` to a stop at `target`, along the profile's direction."""
        length = abs(target - origin)
        steps = max(2, int(math.ceil(length)))
        out = [(0.0, origin)]
        t, previous = 0.0, 0.0
        for k in range(1, steps + 1):
            d = length * k / steps
            c = origin + self.sign * d
            v = min(self.speed(c), math.sqrt(2 * self.accel * d), math.sqrt(2 * self.brake * (length - d)))
            ds = length / steps
            t += 2 * ds / max(previous + v, 1e-3)
            previous = v
            out.append((t, c))
        return out


def warp(run, seconds):
    """The run stretched to take `seconds`."""
    scale = seconds / run[-1][0]
    return [(t * scale, c) for t, c in run]


def legs_from_schedule(route, up, down):
    service = route['summary'].get('service') or {}
    schedule = service.get('schedule')
    loop = route.get('passing_loop') or {}
    stop = (loop['start'] + loop['end']) / 2 if loop else None
    waiting = service.get('waiting_direction', 'down')
    if not schedule:
        dwell = float(service.get('dwell_s') or DEFAULT_DWELL)
        cycle = up.seconds + down.seconds + 2 * dwell
        legs = [dict(direction='up', depart=0.0, arrive=up.seconds),
                dict(direction='down', depart=up.seconds + dwell, arrive=up.seconds + dwell + down.seconds)]
        trains = [('A', legs), ('B', [dict(leg, depart=leg['depart'] + cycle / 2, arrive=leg['arrive'] + cycle / 2) for leg in legs])]
        return cycle, trains, stop, waiting
    cycle = float(service['cycle_s'])
    trains = []
    for entry in schedule:
        legs = []
        for leg in entry['legs']:
            origin, _, _ = leg['direction'].partition('->')
            direction = 'up' if origin.strip().lower().startswith('hidamari') else 'down'
            item = dict(direction=direction, depart=float(leg['depart_s']), arrive=float(leg['arrive_s']))
            if stop is not None and leg.get('loop_arrive_s') is not None and leg['loop_leave_s'] - leg['loop_arrive_s'] > 30:
                item.update(loop_arrive=float(leg['loop_arrive_s']), loop_leave=float(leg['loop_leave_s']))
            legs.append(item)
        trains.append((entry['train'], sorted(legs, key=lambda leg: leg['depart'])))
    return cycle, trains, stop, waiting


def timeline(legs, cycle, profiles, stop, waiting, loop):
    """One cycle of a train as samples of chainage every DT seconds from its first departure, plus the intervals it
    runs on the loop's second track."""
    start = legs[0]['depart']
    moves, loop_track = [], []
    for leg in legs:
        profile = profiles[leg['direction']]
        if 'loop_arrive' in leg:
            first = warp(profile.run(profile.start, stop), leg['loop_arrive'] - leg['depart'])
            second = warp(profile.run(stop, profile.stop), leg['arrive'] - leg['loop_leave'])
            moves.append((leg['depart'], first))
            moves.append((leg['loop_leave'], second))
        else:
            moves.append((leg['depart'], warp(profile.run(profile.start, profile.stop), leg['arrive'] - leg['depart'])))
        if leg['direction'] == waiting and loop.get('points'):
            loop_track.append([round(leg['depart'] - start, 3), round(leg['arrive'] - start, 3)])
    if legs[-1]['arrive'] > start + cycle + 1e-6:
        raise ValueError('a train\'s legs do not fit in one cycle')
    for (t0, run), (t1, _) in zip(moves, moves[1:] + [(start + cycle, None)]):
        if t0 + run[-1][0] > t1 + 1e-6:
            raise ValueError('a run overlaps the next departure')
    times = [t0 for t0, _ in moves]
    s = []
    for k in range(int(round(cycle / DT))):
        t = start + k * DT
        i = bisect.bisect_right(times, t) - 1
        t0, run = moves[i] if i >= 0 else moves[-1]
        if i < 0:
            t += cycle
        local = t - t0
        if local >= run[-1][0]:
            c = run[-1][1]
        else:
            j = bisect.bisect_right([r[0] for r in run], local)
            (ta, ca), (tb, cb) = run[j - 1], run[j]
            c = ca + (local - ta) / (tb - ta) * (cb - ca)
        s.append(round(c, 3))
    return start, s, loop_track


def centred(rows, shift):
    return [[s + shift, t, v] for s, t, v in rows]


def service(route):
    up_rows, down_rows = route['speed_profile'], route['speed_profile_down']
    summary = route['summary'].get('service') or {}
    if summary.get('profile_reference') == 'head':
        # The route gives the leading end's chainage (the head stops at the end of the line); the game places the
        # consist by its centre, half a train behind the head in each direction.
        h = float(summary['train_length_m']) / 2
        up_rows, down_rows = centred(up_rows, -h), centred(down_rows, h)
    up = Profile(up_rows, down_rows[0][0])
    down = Profile(down_rows, up_rows[0][0])
    cycle, trains, stop, waiting = legs_from_schedule(route, up, down)
    loop = line(route)['loop']
    out = []
    for name, legs in trains:
        start, s, loop_track = timeline(legs, cycle, {'up': up, 'down': down}, stop, waiting, loop)
        out.append({'name': name, 't0': round(start, 3), 'dt': DT, 's': s, 'loop_track': loop_track,
                    'legs': [{k: round(v, 3) if isinstance(v, float) else v for k, v in leg.items()} for leg in legs]})
    first = min(leg['depart'] for leg in trains[0][1])
    return {'cycle_s': round(cycle, 3), 'clock_start_s': round((first - CLOCK_LEAD) % cycle, 3),
            'waiting_direction': waiting, 'loop_stop': stop, 'terminals': [up.start, down.start], 'trains': out}


def position(train, cycle, t):
    """A train's chainage at service time t (the game's FBelmonteTrainLine::Chainage)."""
    local = (t - train['t0']) % cycle
    f = local / train['dt']
    i = int(f) % len(train['s'])
    j = (i + 1) % len(train['s'])
    return train['s'][i] + (f - int(f)) * (train['s'][j] - train['s'][i])


def crossings(data):
    """Times and chainages where the two trains pass each other, and whether each is inside the loop."""
    if len(data['trains']) < 2:
        return []
    a, b = data['trains'][:2]
    cycle = data['cycle_s']
    found, previous = [], None
    steps = int(cycle / DT)
    for k in range(steps + 1):
        t = k * DT
        gap = position(a, cycle, t) - position(b, cycle, t)
        if previous is not None and (gap == 0 or (gap > 0) != (previous > 0)):
            found.append({'t': t, 's': round(position(a, cycle, t), 1)})
        previous = gap
    return found


# ---------------------------------------------------------------- the consist

def vehicle_field(v, p, key, default=()):
    """A vehicle's record from consist.json (step 9 carries everything), else from its placements file."""
    value = v.get(key)
    return value if value is not None else p.get(key, default)


def door_mesh(name, leaf):
    asset = 'SM_BTD_' + name.removeprefix('SM_BT_') + '_' + ''.join(c if c.isalnum() else '_' for c in leaf.removeprefix('Door_'))
    return f'{MESH_ROOT}/Doors/{asset}.{asset}'


def seat_yaw(yaw):
    """Unreal actor yaw (degrees, -180..180) of a passenger seated facing `yaw` in the layout (0 = -Y, 90 = +X)."""
    return (90. - float(yaw) + 180.) % 360. - 180.


def doors(v, p, name, switchable):
    """The vehicle's doors for Interact: handles, the collision box that follows the door, and each leaf's motion.
    `side` is the side of the train a door is on (l: +y, the left looking up the line; r: -y; '' inside)."""
    boxes = {b['name']: b['box'] for b in switchable}
    out = []
    listed = vehicle_field(v, p, 'door_interactions', None)
    for d in listed if listed is not None else p.get('doors', []):
        y0, y1 = d['box'][2], d['box'][3]
        side = 'l' if y0 >= 1.6 else 'r' if y1 <= -1.6 else ''
        leaves = []
        for leaf in d.get('leaves', []):
            item = {'node': leaf['name'], 'mesh': door_mesh(name, leaf['name']), 'pivot': to_ue(*leaf['pivot'])}
            if leaf['kind'] == 'sliding':
                ox, oy, oz = leaf.get('open_offset_m', [0, 0, 0])
                item.update(motion='sliding', offset=[round(ox * 100, 2), round(-oy * 100, 2), round(oz * 100, 2)])
            else:
                item.update(motion='hinged', yaw=-float(leaf.get('swing_deg', 90)))
            leaves.append(item)
        out.append({'id': d['id'], 'kind': d['kind'], 'opens': d.get('opens', 'any'),
                    'locked': bool(d.get('locked')), 'side': side,
                    'handles': [to_ue(*h['point']) for h in d.get('handles', [])],
                    'collision': boxes.get(d.get('collision')) or box_ue(d['box']), 'leaves': leaves})
    return out


def _point(value):
    """[x, y, z] from a point, or from a tread record (the middle of its box, at its top)."""
    if isinstance(value, dict):
        if 'box' in value:
            x0, x1, y0, y1 = value['box'][:4]
            return [(x0 + x1) / 2, (y0 + y1) / 2, float(value.get('top_z', value.get('z', 0.)))]
        value = value.get('point') or value.get('at') or [value.get('x'), value.get('y'), value.get('z')]
    return [float(c) for c in value[:3]]


def boarding(v, p):
    """The scripted way up or down at each passenger door and balcony gate, from outside to inside, in Unreal cm: the
    Train Builder's 'boarding' records (outside start on the ground, the treads, the inside end on the floor); before
    those existed, from each station door's box: 0.8 m out, the two hanging steps (0.66 and 0.96 m above the rail),
    the threshold and 0.6 m in."""
    records = vehicle_field(v, p, 'boarding', None)
    out = []
    if records is not None:
        for r in records:
            path = [_point(r['outside']), *sorted((_point(t) for t in r.get('treads', [])), key=lambda t: t[2]),
                    _point(r['inside'])]
            out.append({'door': r['id'], 'path': [to_ue(*q) for q in path], 'source': 'record'})
        return out
    listed = vehicle_field(v, p, 'door_interactions', None)
    for d in listed if listed is not None else p.get('doors', []):
        if d['kind'] not in ('exterior', 'gate') or d.get('opens') != 'station' or d['id'].startswith('cargo'):
            continue
        x0, x1, y0, y1 = d['box'][:4]
        side = 1 if y0 >= 1.6 else -1 if y1 <= -1.6 else 0
        if not side:
            continue
        xc, face = (x0 + x1) / 2, 1.8
        path = [[xc, side * (face + 0.8), 0.0], [xc, side * (face + 0.08), 0.66], [xc, side * (face - 0.1), 0.96],
                [xc, side * (face - 0.2), 1.25], [xc, side * (face - 0.6), 1.25]]
        out.append({'door': d['id'], 'path': [to_ue(*q) for q in path], 'source': 'door box'})
    return out


def consist(assembly, placements, records=None):
    records = records or {}
    vehicles = assembly['vehicles']
    front = max(v['x'] + v['length'] / 2 for v in vehicles)
    back = min(v['x'] - v['length'] / 2 for v in vehicles)
    centre = (front + back) / 2
    sizes = assembly.get('furniture', {})
    out, assets = [], {}
    for v in vehicles:
        p = placements.get(v['id'], {})
        name = v['glb'].removesuffix('.glb').removesuffix('_LOD0')
        bogies = list((p.get('body') or {}).get('bogies') or [])
        if len(bogies) != 2:
            bogies = [-0.3 * v['length'], 0.3 * v['length']]
        groups = {}
        for item in vehicle_field(v, p, 'placements'):
            yaw = -float(item.get('yaw', 0))
            groups.setdefault(item['asset'], []).append([*to_ue(item['x'], item['y'], item['z']), yaw])
            if item['asset'] not in assets:
                assets[item['asset']] = furniture_entry(item['asset'], sizes.get(item['asset']) or {}, records.get(item['asset']))
        boxes = vehicle_field(v, p, 'collision_boxes')
        switchable = [{'name': b['name'], 'group': b['group'], 'part': b.get('part', ''), 'box': box_ue(b['box'])}
                      for b in boxes if b.get('group', 'fixed') != 'fixed']
        out.append({
            'id': v['id'], 'mesh': mesh_path(name), 'name': name, 'length': v['length'],
            'offset': round(v['x'] - centre, 3), 'bogies': bogies,
            'furniture': [{'asset': a, 'instances': rows} for a, rows in sorted(groups.items())],
            'collision': [box_ue(b['box']) for b in boxes if b.get('group', 'fixed') == 'fixed'],
            'switchable': switchable,
            'doors': doors(v, p, name, switchable),
            # a seat's yaw is the way the passenger faces in the layout's convention (0 = -Y, 90 = +X); in Unreal a
            # character faces +X at yaw 0 and Y is mirrored, so -Y there is +90
            'seats': [{'id': s['id'], 'at': [*to_ue(s['x'], s['y'], s['z']), seat_yaw(s.get('yaw', 0))]}
                      for s in vehicle_field(v, p, 'seats')],
            'interiors': [{'name': i['name'], 'box': box_ue(i['box']), 'no_sprint': 'no_sprint' in i.get('tags', []),
                           'no_climb': 'no_climb' in i.get('tags', ['no_climb']), 'camera': 'interior' in i.get('tags', ['interior'])}
                          for i in vehicle_field(v, p, 'interior_volumes')],
            'exteriors': [{'name': i['name'], 'box': box_ue(i['box']), 'no_climb': 'no_climb' in i.get('tags', [])}
                          for i in vehicle_field(v, p, 'exterior_volumes')],
            'boarding': boarding(v, p),
        })
    return {'length': round(front - back, 3), 'head': 'up', 'vehicles': out}, dict(sorted(assets.items()))


THIN_SHEETS = ('restaurant-table', 'table-lamp', 'wall-sconce', 'curtain', 'shade')


def furniture_entry(asset, spec, record):
    """A furniture asset's mesh, its levels and its cull distance. The levels are the LOD worker's (consist.json's
    `lods`, else furniture/<asset>.json's), in furniture/lod/; without them, the fitted Tripo GLB alone. The cull
    distance turns the recorded cull screen size into cm (Unreal's screen size is about radius / distance)."""
    record_lods = (record or {}).get('lods') or {}
    levels = spec.get('lods') if isinstance(spec.get('lods'), list) else record_lods.get('levels')
    size = spec.get('dimensions_m') or {}
    largest = max([size.get(k, 1.) for k in ('width', 'depth', 'height')] or [1.])
    entry = {'mesh': furniture_mesh(asset), 'shadow': largest > SMALL_ITEM, 'small': largest <= SMALL_ITEM}
    # Thin single-sheet parts (the restaurant tablecloth's drape, lamp and sconce shades, curtains) are seen from both
    # sides: their materials are drawn two-sided.
    entry['two_sided'] = bool(spec.get('two_sided', (record or {}).get('two_sided', any(t in asset for t in THIN_SHEETS))))
    if levels:
        entry['levels'] = [{'glb': level['glb'] if level['glb'].startswith('lod/') else 'lod/' + level['glb'],
                            'screen_size': level['screen_size'], 'triangles': level.get('triangles')}
                           for level in sorted(levels, key=lambda level: level['level'])]
        cull = spec.get('cull_screen_size') or record_lods.get('cull_screen_size')
        radius = record_lods.get('bounds_radius_m') or (math.sqrt(sum(v * v for v in size.values())) / 2 if size else None)
        if cull and radius:
            entry['cull_cm'] = round(100 * radius / cull, 1)
    else:
        entry['levels'] = [{'glb': f'{asset}.glb', 'screen_size': 1.0}]
    entry.setdefault('cull_cm', RENDER['small_furniture_cull_cm'] if entry['small'] else RENDER['furniture_cull_cm'])
    return entry


# ---------------------------------------------------------------- the vehicles' meshes

def split_meshes(root, train, folder):
    """Each vehicle's LOD0 and LOD1 without its door leaves (they move), and each leaf from LOD0 as its own GLB, in
    vehicle coordinates; LOD2 keeps its doors shut. Without the GLBs (tests), the levels name the Train Builder's files."""
    for v in train['vehicles']:
        name = v['name']
        source = [root / v['id'] / f'{name}_LOD{i}.glb' for i in range(3)]
        v["levels"] = [os.path.relpath(p, root) for p in source]
        if not source[0].exists():
            continue
        leaves = {leaf['node'] for d in v['doors'] for leaf in d['leaves']}
        for level in (0, 1):
            if not source[level].exists():
                continue
            gltf, binary = G.read(source[level])
            index = G.names(gltf)
            drop = {index[n] for n in leaves if n in index}
            body, data = G.keep(gltf, binary, drop=drop)
            path = folder / f'{name}_LOD{level}.glb'
            G.write(path, body, data)
            v['levels'][level] = os.path.relpath(path, root)
            if level == 0:
                for d in v['doors']:
                    for leaf in d['leaves']:
                        if leaf['node'] not in index:
                            leaf['mesh'] = None
                            continue
                        part, data = G.keep(gltf, binary, only={index[leaf['node']]})
                        target = folder / 'doors' / (leaf['mesh'].rsplit('/', 1)[1].split('.')[0] + '.glb')
                        G.write(target, part, data)
                        leaf['glb'] = os.path.relpath(target, root)


# ---------------------------------------------------------------- the termini

PLATFORM = {'edge_m': 1.85, 'width_m': 4.0, 'top_above_rail_m': 1.0, 'extra_length_m': 12.0}


def stations(route, train, terminals):
    """The platform on the station's authored side (left by default), its buffer stop and map arrival near a door.
    Hidamari's platform extends the town station at its existing floor height; Belmonte keeps the raised platform.
    """
    samples = route['samples']
    chain = [s['s'] for s in samples]

    def at(c):
        i = min(max(bisect.bisect_right(chain, c) - 1, 0), len(chain) - 2)
        a, b = samples[i], samples[i + 1]
        f = (c - a['s']) / (b['s'] - a['s'])
        x, y = a['x'] + f * (b['x'] - a['x']), a['y'] + f * (b['y'] - a['y'])
        dx, dy = b['x'] - a['x'], b['y'] - a['y']
        n = math.hypot(dx, dy)
        return x, y, a['rail_z'] + f * (b['rail_z'] - a['rail_z']), dx / n, dy / n
    names = sorted(route.get('stations', {}), key=lambda k: route['stations'][k]['centre'][1])
    first = next((v for v in train['vehicles'] if v['id'] == 'first-class'), train['vehicles'][len(train['vehicles']) // 2])
    out = []
    for index, (chainage, end) in enumerate(zip(terminals, (chain[0], chain[-1]))):
        name = names[index] if index < len(names) else ('Hidamari', 'Belmonte')[index]
        spec = route.get('stations', {}).get(name, {})
        side = spec.get('side', 'l')
        sign = -1 if side == 'r' else 1
        door = next((d for d in first['doors'] if d['kind'] == 'exterior' and d['side'] == side), None)
        x, y, z, dx, dy = at(chainage)
        lx, ly = -dy * sign, dx * sign
        length = train['length'] + PLATFORM['extra_length_m']
        middle = PLATFORM['edge_m'] + PLATFORM['width_m'] / 2
        lo = min(s['ground_z'] for s in samples if abs(s['s'] - chainage) <= length / 2 + 10)
        height = spec.get('top_above_rail_m', PLATFORM['top_above_rail_m'])
        top = z + height
        bottom = min(lo - 1.0, top - 0.5)
        door_x = (first['offset'] + (door['collision'][0] + door['collision'][3]) / 200) if door else first['offset']
        ax, ay, az, adx, ady = at(chainage + door_x - 7.0)
        arrival = (ax - ady * sign * (PLATFORM['edge_m'] + 2.5), ay + adx * sign * (PLATFORM['edge_m'] + 2.5), az + height)
        ex, ey, ez, edx, edy = at(end)
        out.append({
            'key': name.lower() + '_station', 'name': 'Gare de ' + name, 'chainage': chainage, 'side': side,
            'platform': {'centre': to_ue(x + lx * middle, y + ly * middle, (top + bottom) / 2),
                         'yaw': round(-math.degrees(math.atan2(dy, dx)), 3),
                         'size': [round(length * 100, 1), round(PLATFORM['width_m'] * 100, 1), round((top - bottom) * 100, 1)]},
            'buffer': {'centre': to_ue(ex, ey, ez + 0.6), 'yaw': round(-math.degrees(math.atan2(edy, edx)), 3), 'size': [80.0, 300.0, 120.0]},
            # Facing the train: the yaw toward the line, a few degrees along it toward the door.
            'arrival': {'location': to_ue(*arrival), 'yaw': round(-math.degrees(math.atan2(-ly, -lx)), 3)},
        })
    return out


# ---------------------------------------------------------------- the file

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(root=TRAIN, glb=None, *, use_record_lods=True):
    route_path = root / 'route' / 'route.json'
    consist_path = root / 'assembly' / 'consist.json'
    route = json.loads(route_path.read_text())
    assembly = json.loads(consist_path.read_text())
    placements = {}
    for v in assembly['vehicles']:
        path = root / v['id'] / f'{v["id"]}-placements.json'
        if path.exists():
            placements[v['id']] = json.loads(path.read_text())
    records = {}
    for path in (sorted((root / 'furniture').glob('*.json')) if use_record_lods else ()):
        try:
            records[path.stem] = json.loads(path.read_text())
        except ValueError:
            pass
    train, furniture = consist(assembly, placements, records)
    data = {
        'version': 1,
        'about': 'Belmonte train service for ABelmonteTrainService (games/yorimichi/tools/belmonte_train_service.py)',
        'units': 'Unreal cm for points and boxes (y flipped from Blender); chainage, offsets and bogies in metres',
        'sources': {'route': sha(route_path), 'consist': sha(consist_path)},
        'render': RENDER,
        'line': line(route),
        'consist': train,
        'furniture': furniture,
        'service': service(route),
    }
    split_meshes(root, train, glb or root / 'service' / 'glb')
    data['stations'] = stations(route, train, data['service']['terminals'])
    data['service']['crossings'] = [
        dict(c, in_loop=bool(data['line']['loop']['points']) and data['line']['loop']['start'] <= c['s'] <= data['line']['loop']['end'])
        for c in crossings(data['service'])]
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, default=TRAIN, help='the Train Builder output folder')
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    data = build(args.root, args.output.parent / 'glb', use_record_lods=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, separators=(',', ':')) + '\n')
    s = data['service']
    print(f'BELMONTE TRAIN SERVICE vehicles={len(data["consist"]["vehicles"]) * len(s["trains"])} '
          f'trains={len(s["trains"])} cycle={s["cycle_s"]} s crossings={json.dumps(s["crossings"])} -> {args.output}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
