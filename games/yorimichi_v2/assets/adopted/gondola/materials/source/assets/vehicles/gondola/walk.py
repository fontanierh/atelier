"""Walkability audit of the gondola cabin and the three stations, from the same collision proxies that build.py
exports as UCX hulls for Unreal.

uv run python games/yorimichi/assets/vehicles/gondola/walk.py
Reads build/yorimichi/gondola/layout_<piece>.json (written by build.py) and writes, under build/yorimichi/gondola/review/:
walk_report.json and one top-down layout image per piece (walk_cabin.png, walk_valley.png, walk_rim.png,
walk_crater.png).

The walking surface is the platform (z = 0), plus ramps (the rim boardwalk) and stairs (the crater stair) from the
layout. A cell is blocked when any proxy covers it in plan, with any part of its height between 0.30 m (the step
limit) and 2.0 m (required headroom) above the surface there. The player capsule's centre (radius 0.22 m) may stand
where the clearance to the nearest blocked cell is at least the radius. Clear width at a point is twice that
clearance; routes report their bottleneck (max-min) width. Trapping pockets are free cells, reachable from the open
floor, that the capsule cannot sweep; unswept slots no wider than 0.3 m are listed separately as slivers. Station
layouts have a cabin standing in each berth with its doors open, so the boarding routes run into the cabins.

The raster analysis is shared with the ferry through world/walk_raster.py; this file owns the gondola layouts and verdict policy.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import json
import hashlib
import math
from collections import deque
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[5]
OUT = yori.OUT / 'gondola'
REVIEW = OUT / 'review'
CELL = 0.05
RADIUS = 0.22
STEP, HEAD = 0.30, 2.0       # step limit and required headroom (m)
MIN_WIDTH, HARD_MIN = 0.9, 0.6
RISER_MAX, TREAD_MIN = 0.30, 0.25
DOOR_MIN = (0.9, 2.0)        # cabin door clear width and height (m)
BOARDING_GAP_MIN, BOARDING_GAP_MAX = 0.05, 0.12   # berth: cabin door sill to the platform edge, across (m)
SILL_MIN, SILL_MAX = 0.0, 0.03                    # berth: the cabin sill above the platform (m)
CAPSULE_HALF_HEIGHT = 0.755
SLIVER = 2 * RADIUS          # an unswept slot narrower than the capsule cannot be entered, so it cannot trap

from walk_raster import edt_1d,edt,label,bfs_path,inside_poly,plane,bottlenecks,pinch_points,pockets
import walk_raster as _raster


class Deck(_raster.Deck):
    def __init__(self,name,x0,x1,y0,y1,region,surface,own):
        super().__init__(name,x0,x1,y0,y1,region,surface,own,cell=CELL,radius=RADIUS,step=STEP,head=HEAD,
                         min_width=MIN_WIDTH,hard_min=HARD_MIN,sliver=SLIVER,record_routes=True)


def draw(deck,pinches,routes,marks,path,pockets_=(),scale=40):
    try:
        from PIL import Image,ImageDraw
    except ImportError:
        return
    return _raster.draw(deck,pinches,routes,marks,path,pockets_,scale,image=Image,image_draw=ImageDraw)


# ------------------------------------------------------------------ gondola pieces
def path_s(X, Y, line):
    """Distance along a centreline polyline of the nearest point to (X, Y): a ramp that follows a curved path."""
    best = np.full(X.shape, np.inf); out = np.zeros(X.shape); s0 = 0.0
    for p, q in zip(line[:-1], line[1:]):
        dx, dy = q[0] - p[0], q[1] - p[1]; L2 = dx * dx + dy * dy
        t = np.clip(((X - p[0]) * dx + (Y - p[1]) * dy) / L2, 0.0, 1.0)
        dd = (X - p[0] - t * dx) ** 2 + (Y - p[1] - t * dy) ** 2
        better = dd < best; best = np.where(better, dd, best); out = np.where(better, s0 + t * np.sqrt(L2), out)
        s0 += np.sqrt(L2)
    return out


def surface_fn(surfaces):
    """Walking-surface height: 0 by default, planes and stairs where the layout has them."""
    def S(X, Y):
        z = np.zeros(X.shape)
        for s in surfaces:
            m = inside_poly(X, Y, s['poly'])
            if 'plane' in s:
                a, b, c = s['plane']; z = np.where(m, a + b * X + c * Y, z)
            elif 'path' in s:
                z = np.where(m, -path_s(X, Y, s['path']) * s['grade'], z)
            elif 'stair' in s:
                st = s['stair']; k = np.ceil((Y - st['y0']) / st['tread'] - 1e-9)
                z = np.where(m, np.maximum(st['bottom_z'], st['top_z'] - st['rise'] * np.maximum(k, 0)), z)
            else:
                z = np.where(m, s['z'], z)
        return z
    return S


def union_fn(polys):
    def R(X, Y):
        r = np.zeros(X.shape, dtype=bool)
        for p in polys:
            r |= inside_poly(X, Y, p)
        return r
    return R


def analyse(deck, pts, routes, image):
    lab, n = label(deck.walk)
    comps = {int(lab[deck.snap(*p)]) for p in pts.values() if deck.snap(*p)} or set(range(1, n + 1))
    rts = bottlenecks(deck, routes); pin = pinch_points(deck, comps, lab); poc, sliv = pockets(deck)
    # A narrowing that no route passes through (a notch beside a gate post, a gap behind a bench) is not a pinch
    # on a walkable route: it is kept in the list and labelled as such.
    w = deck.walk.shape[1]; near = max(1, int(0.15 / CELL)); cells = getattr(deck, 'route_cells', set())
    on_route = np.zeros(deck.walk.shape, dtype=bool)
    for c in cells:
        i, j = divmod(c, w); on_route[max(0, i - near):i + near + 1, max(0, j - near):j + near + 1] = True
    for p in pin:
        i, j = deck.cell(*p['at'])
        p['on_route'] = bool(on_route[i, j])
        if not p['on_route'] and p['clear_width_m'] < MIN_WIDTH:
            p['status'] = 'off-route notch (no route passes)'
    marks = [(k, x, y, (220, 110, 0)) for k, (x, y) in pts.items()]
    draw(deck, pin, rts, marks, REVIEW / image, poc, scale=260 if CELL < 0.04 else 24)
    main_area = max((int((lab == c).sum()) for c in comps), default=0)
    return {'walkable_area_m2': round(float(deck.walk.sum() * CELL * CELL), 1), 'components': n,
            'main_component_area_m2': round(main_area * CELL * CELL, 1),
            'routes': rts, 'pinch_points': pin, 'trapping_pockets': poc, 'slivers': sliv, 'image': f'review/{image}'}


def cabin_report():
    global CELL
    CELL = 0.02
    L = json.loads((OUT / 'layout_cabin.json').read_text())
    z = L['floor_z']; d = L['door']; inner = [tuple(p) for p in L['interior']]
    x0, x1 = d['x']; apron = [(x0 - 1.0, d['y_outer'] - 1.6), (x1 + 1.0, d['y_outer'] - 1.6), (x1 + 1.0, d['y_outer']), (x0 - 1.0, d['y_outer'])]
    strip = [(x0, d['y_outer']), (x1, d['y_outer']), (x1, d['y_inner'] + 0.01), (x0, d['y_inner'] + 0.01)]
    region = [inner, strip, apron]
    proxies = [dict(p, z0=[v - z for v in p['z0']], z1=[v - z for v in p['z1']]) for p in L['proxies'] if p['name'] != 'cabin floor']
    xs = [p[0] for p in inner]; ys = [p[1] for p in inner]
    deck = Deck('cabin (doors open, platform apron outside the door)', min(xs) - 0.6, max(xs) + 0.6, d['y_outer'] - 1.7, max(ys) + 0.1,
                union_fn(region), lambda X, Y: np.zeros(X.shape), set()).rasterise(proxies)
    b = L['benches']
    pts = {'platform apron': (0.0, d['y_outer'] - 0.7), 'door': (0.0, (d['y_outer'] + d['y_inner']) / 2), 'centre': (0.0, 0.0),
           'east bench front': (b['east'][0] - 0.3, 0.2), 'west bench front': (b['west'][1] + 0.3, 0.2), 'back bench front': (0.0, b['back_y'][0] - 0.3)}
    routes = [(f'platform apron -> {k}', pts['platform apron'], v) for k, v in pts.items() if k != 'platform apron']
    rep = analyse(deck, pts, routes, 'walk_cabin.png')
    xi = max(xs)
    rep['door'] = {'clear_width_m': round(x1 - x0, 3), 'clear_height_m': d['clear_height'], 'required_m': list(DOOR_MIN),
                   'ok': (x1 - x0) >= DOOR_MIN[0] and d['clear_height'] >= DOOR_MIN[1]}
    rep['headroom_m'] = L['headroom']; rep['aisle_between_side_benches_m'] = round(b['east'][0] - b['west'][1], 3)
    rep['bench_seat_height_m'] = b['seat_height']; rep['interior_floor_m'] = [round(2 * xi, 3), round(max(ys) - min(ys), 3)]
    return rep


def station_deck(L,key):
    global CELL
    CELL = 0.05
    polys = [[tuple(q) for q in r] for r in L['regions']] + [[tuple(q) for q in s['poly']] for s in L.get('surfaces', [])]
    allx = [q[0] for p in polys for q in p]; ally = [q[1] for p in polys for q in p]
    return Deck(f'{key} station (cabins in both berths, doors open)', min(allx) - 0.3, max(allx) + 0.3, min(ally) - 0.3, max(ally) + 0.3,
                union_fn(polys), surface_fn(L.get('surfaces', [])), set()).rasterise(L['obstacles'])


def station_routes(L,key):
    """Native driving waypoints use the same capsule raster as the kit audit."""
    deck=station_deck(L,key);w=deck.walk.shape[1];routes={}
    start=deck.snap(*L['access'][0]['point'])
    if start is None:raise ValueError('Station access has no walking cell')
    for berth in L['berths']:
        end=deck.snap(*berth['cabin_grip'][:2],reach=.2)
        if end is None:raise ValueError('Station berth has no walking cell')
        path=bfs_path(deck.walk,start[0]*w+start[1],end[0]*w+end[1])
        if not path:raise ValueError('No capsule route from station access to cabin')
        cells=[divmod(c,w) for c in path]
        # Drop only collinear intermediate cells. Corners and staircase points
        # remain, so the live drive follows the audited route rather than a chord.
        keep=[cells[0]]
        for i in range(1,len(cells)-1):
            a,b,c=cells[i-1:i+2]
            if (b[0]-a[0],b[1]-a[1])!=(c[0]-b[0],c[1]-b[1]):keep.append(b)
        keep.append(cells[-1])
        routes[str(berth['side'])]=[[float(deck.xs[j]),float(deck.ys[i]),float(deck.S[i,j])] for i,j in keep]
    return routes


def station_report(key):
    L = json.loads((OUT / f'layout_{key}.json').read_text())
    deck=station_deck(L,key)
    pts = {}
    for a in L['access']:
        pts[a['name']] = tuple(a['point'])
    for b in L['berths']:
        s = b['side']; x = b['cabin_grip'][0]; ye = b['platform_edge']['y']
        pts[f'berth {s:+d} platform'] = (x, ye + s * 0.8)
        pts[f'berth {s:+d} cabin'] = (x, b['cabin_grip'][1])
    for name, p in L.get('points', {}).items():
        pts[name] = tuple(p)
    first = L['access'][0]['name']
    routes = [(f'{first} -> {k}', pts[first], v) for k, v in pts.items() if k != first]
    rep = analyse(deck, pts, routes, f'walk_{key}.png')
    rep['boarding'] = [{'side': b['side'], 'door_centre': b['door_centre'], 'gate_x': b['platform_edge']['x'],
                        'door_within_gate': (b['platform_edge']['x'][0] <= b['door_centre'][0] - b['door_clear_width'] / 2
                                             and b['door_centre'][0] + b['door_clear_width'] / 2 <= b['platform_edge']['x'][1]),
                        'gap_door_to_edge_m': b['gap_door_to_edge_m'], 'sill_above_platform_m': b['door_centre'][2],
                        'gap_ok': BOARDING_GAP_MIN - 1e-9 <= b['gap_door_to_edge_m'] <= BOARDING_GAP_MAX + 1e-9,
                        'sill_ok': SILL_MIN - 1e-9 <= b['door_centre'][2] <= SILL_MAX + 1e-9} for b in L['berths']]
    rep['stairs'] = [dict(s, riser_ok=s['riser_m'] <= RISER_MAX + 1e-9, tread_ok=s['tread_m'] >= TREAD_MIN - 1e-9,
                          width_ok=s['width_m'] >= MIN_WIDTH) for s in L['stairs']]
    return rep


def verdict(r):
    """The reasons one piece fails the walk audit (empty when it passes)."""
    why = [f'route {x["route"]}: ' + ('not connected' if not x.get('connected') else f'bottleneck {x.get("bottleneck_width_m")} m < {MIN_WIDTH} m')
           for x in r['routes'] if not x.get('connected') or not x.get('meets_0.9')]
    why += [f'pinch {p["clear_width_m"]} m at {p["at"]}' for p in r['pinch_points'] if p['status'] == 'too narrow']
    why += [f'trapping pocket at {p.get("at")}' for p in r['trapping_pockets']]
    why += [f'stair at {s["x"]}, {s["y"]}: riser {s["riser_m"]} / tread {s["tread_m"]} / width {s["width_m"]}'
            for s in r.get('stairs', []) if not (s['riser_ok'] and s['tread_ok'] and s['width_ok'])]
    if 'door' in r and not r['door']['ok']:
        why.append(f'cabin door {r["door"]["clear_width_m"]} x {r["door"]["clear_height_m"]} m under {DOOR_MIN}')
    for b in r.get('boarding', []):
        if not b['door_within_gate']:
            why.append(f'berth {b["side"]:+d}: door outside the gate')
        if not b.get('gap_ok', True):
            why.append(f'berth {b["side"]:+d}: boarding gap {b["gap_door_to_edge_m"]} m outside {BOARDING_GAP_MIN}..{BOARDING_GAP_MAX} m')
        if not b.get('sill_ok', True):
            why.append(f'berth {b["side"]:+d}: sill {b["sill_above_platform_m"]} m above the platform, outside {SILL_MIN}..{SILL_MAX} m')
    return why


def audit(quiet=False):
    """Run the walk audit on the layouts build.py wrote; returns (report, list of failures). Writes walk_report.json
    and (when PIL is available) the review images."""
    REVIEW.mkdir(parents=True, exist_ok=True)
    report = {'capsule': {'radius_m': RADIUS, 'half_height_m': CAPSULE_HALF_HEIGHT},
              'rules': {'min_clear_width_m': MIN_WIDTH, 'headroom_m': HEAD, 'step_m': STEP, 'riser_max_m': RISER_MAX, 'tread_min_m': TREAD_MIN,
                        'door_min_m': list(DOOR_MIN), 'boarding_gap_m': [BOARDING_GAP_MIN, BOARDING_GAP_MAX], 'sill_m': [SILL_MIN, SILL_MAX]},
              'source': 'collision proxies = the UCX hulls in assets/GD_*_Collision.fbx', 'pieces': {}}
    report['pieces']['cabin'] = cabin_report()
    for key in ('valley', 'rim', 'crater'):
        if (OUT / f'layout_{key}.json').exists():
            report['pieces'][key] = station_report(key)
    failures = []
    for name, r in report['pieces'].items():
        why = verdict(r)
        r['verdict'] = 'pass' if not why else 'fail'; r['failures'] = why
        failures += [f'{name}: {w}' for w in why]
        if quiet:
            continue
        print(name, r['verdict'], 'area', r['walkable_area_m2'], 'components', r['components'])
        for x in r['routes']:
            print('  ', x['route'], x.get('bottleneck_width_m'), x.get('bottleneck_at'), 'OK' if x.get('meets_0.9') else 'FAIL')
        for p in r['pinch_points']:
            print('   pinch', p)
        for p in r['trapping_pockets']:
            print('   pocket', p)
    report['all_pass'] = not failures; report['failures'] = failures
    report['inputs'] = {'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'raster_sha256':hashlib.sha256(Path(_raster.__file__).read_bytes()).hexdigest(),
                        'layouts':{name:hashlib.sha256((OUT/f'layout_{name}.json').read_bytes()).hexdigest()
                                   for name in report['pieces']}}
    (REVIEW / 'walk_report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report, failures


def main():
    _, failures = audit()
    for f in failures:
        print('FAIL', f)
    print('walk report:', 'PASS' if not failures else 'FAIL')
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
