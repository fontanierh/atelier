"""Condense ride oracle traces (ride_oracle.py) into the compact reference.

Every scenario keeps its input recipe, the sequence of player states, graph states and tricks, the clips that carried
real weight (start and end tick, weight samples, playback rate) and the numbers that describe the mechanic. A summary
gathers the key numbers across scenarios (top speeds, yaw rates, pop heights, flip rotations, snap tolerances...).
"""
import gzip
import json
import math
from pathlib import Path

DT = 1 / 60
KEY = ['TRAJECTORY', 'HIPS', 'SPINE3', 'HEAD', 'LEFTHAND', 'RIGHTHAND', 'LEFTFOOT', 'RIGHTFOOT', 'LEFTTOEBASE',
       'RIGHTTOEBASE', 'SKATEBOARD_ROOT', 'TRUCK_FRONT', 'TRUCK_BACK']
BONE = {name: i for i, name in enumerate(KEY)}
WIPEOUT_REASONS = {
    0: 'body or arm contact force over the regional limit', 1: 'pose displacement (rider pulled off his target)',
    2: 'deck acceleration in the board plane', 3: 'deck angle error', 4: 'upside down while flipping',
    5: 'landing angle', 6: 'landing impact speed', 7: 'vehicle contact', 8: 'grind impact speed',
    10: 'slide wipeout', 11: 'balance total', 12: 'hung up', 16: 'conflicting contacts',
    17: 'leaving a grind too long', 18: 'squash (pose error)', 19: 'lean contact', 20: 'opposing contact',
    21: 'deliberate or flagged bail', 24: 'cannot land on the deck', 27: 'dangerous landing'}
GRIND_FAMILIES = ['FiftyFifty', 'Boardslide', 'Tipslide', 'FiveO', 'Backslash', 'Darkslide']
RAIL_X = {'rail': 0.0, 'ledge': 0.3}
RAIL_TOP = {'rail': 0.5, 'ledge': 0.45}


def r(value, digits=3):
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return None
    return round(value, digits)


def load(traces, name):
    path = Path(traces) / (name.replace('/', '__') + '.jsonl.gz')
    if not path.exists():
        return None
    with gzip.open(path, 'rt') as f:
        return [json.loads(line) for line in f]


# ------------------------------------------------------------------------------------------------- geometry helpers
def axes(rec):
    b = rec['deck']['basis']
    return b[0:3], b[3:6], b[6:9]  # local x (left), y (up), z (forward) in world


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def sub(a, b):
    return [x - y for x, y in zip(a, b)]


def norm(a):
    return math.sqrt(dot(a, a))


def hspeed(rec):
    v = rec['deck']['v']
    return math.hypot(v[0], v[2])


def yaw(vec):
    return math.atan2(vec[0], vec[2])


def deck_yaw(rec):
    return yaw(axes(rec)[2])


def unwrap(values):
    out, offset, last = [], 0.0, None
    for v in values:
        if last is not None:
            d = v - last
            if d > math.pi:
                offset -= 2 * math.pi
            elif d < -math.pi:
                offset += 2 * math.pi
        out.append(v + offset)
        last = v
    return out


def bone(rec, name, field='bones'):
    f = rec[field][BONE[name]]
    return f[0:3], f[3:6], f[6:9], f[9:12]


def root_axes(rec):
    root = rec['root']
    return root[3:6], root[6:9], root[9:12]


def root_yaw(rec):
    return yaw(root_axes(rec)[2])


def relative_rotation(a, b):
    """Rotation from frame a to frame b (each three world axes) as (about x, about y, about z) radians in a's frame."""
    m = [[dot(a[i], b[j]) for j in range(3)] for i in range(3)]
    c = max(-1.0, min(1.0, (m[0][0] + m[1][1] + m[2][2] - 1) / 2))
    angle = math.acos(c)
    v = (m[2][1] - m[1][2], m[0][2] - m[2][0], m[1][0] - m[0][1])
    s = norm(v)
    if s < 1e-9:
        return 0.0, 0.0, 0.0
    return tuple(angle * x / s for x in v)


def accumulated(trace, s, e, frame=axes):
    """Per-tick rotation of a frame summed about its own axes: (pitch about left, yaw about up, roll about forward)
    in degrees, cumulative from tick s, one entry per tick s..e."""
    out = [(0.0, 0.0, 0.0)]
    total = [0.0, 0.0, 0.0]
    for a, b in zip(trace[s:e], trace[s + 1:e + 1]):
        d = relative_rotation(frame(a), frame(b))
        total = [total[i] + math.degrees(d[i]) for i in range(3)]
        out.append(tuple(total))
    return out


# ---------------------------------------------------------------------------------------------- sequence summaries
def runs(values):
    """[(value, start, end)] for consecutive equal values; end is exclusive."""
    out = []
    for i, v in enumerate(values):
        if out and out[-1][0] == v:
            out[-1][2] = i + 1
        else:
            out.append([v, i, i + 1])
    return out


CLIP_COLUMNS = ['clip', 'layer', 'start tick', 'end tick (exclusive)', 'peak weight', 'median playback rate',
                'clip time at start', 'clip time at end', 'wraps', '[tick, weight] samples']


def clip_segments(trace, threshold=0.15, samples=4, start=0):
    """Clips that reached `threshold` weight from tick `start` on, one row per continuous use (CLIP_COLUMNS)."""
    tracks = {}
    for rec in trace[start:]:
        seen = set()
        for name, weight, t, loops, source in rec.get('clips', []):
            key = (name, source)
            if key in seen:
                key = (name, source + '#2')
            seen.add(key)
            tracks.setdefault(key, {})[rec['t']] = (weight, t, loops)
    segments = []
    for (name, source), ticks in tracks.items():
        ordered = sorted(ticks)
        groups, current = [], [ordered[0]]
        for a, b in zip(ordered, ordered[1:]):
            if b != a + 1:
                groups.append(current)
                current = []
            current.append(b)
        groups.append(current)
        for group in groups:
            segments.append(dict(name=name, layer=source.replace('#2', ''), ticks=group,
                                 data={t: ticks[t] for t in group}))
    # A clip handed from one blend node to the next (same name, contiguous ticks, continuous time) is one use.
    segments.sort(key=lambda g: g['ticks'][0])
    merged = []
    for seg in segments:
        for prev in merged:
            last = prev['ticks'][-1]
            if (prev['name'] == seg['name'] and seg['ticks'][0] in (last, last + 1) and
                    abs(seg['data'][seg['ticks'][0]][1] - prev['data'][last][1]) < 0.05):
                prev['ticks'] = sorted(set(prev['ticks']) | set(seg['ticks']))
                for t, v in seg['data'].items():
                    if t not in prev['data'] or v[0] > prev['data'][t][0]:
                        prev['data'][t] = v
                break
        else:
            merged.append(seg)
    rows = []
    for seg in merged:
        group, data = seg['ticks'], seg['data']
        peak = max(data[t][0] for t in group)
        if peak < threshold:
            continue
        rates = []
        for a, b in zip(group, group[1:]):
            if data[b][2] == data[a][2] and data[b][1] > data[a][1] and b == a + 1:
                rates.append((data[b][1] - data[a][1]) / DT)
        rates.sort()
        step = max(1, len(group) // samples)
        picks = group[::step]
        if picks[-1] != group[-1]:
            picks.append(group[-1])
        rows.append([seg['name'], seg['layer'], group[0], group[-1] + 1, r(peak, 2),
                     r(rates[len(rates) // 2], 3) if rates else None, r(data[group[0]][1]), r(data[group[-1]][1]),
                     data[group[-1]][2] - data[group[0]][2], [[t, r(data[t][0], 2)] for t in picks]])
    rows.sort(key=lambda row: (row[2], -row[4]))
    return rows


def timeline(trace):
    leaf = lambda path: '/'.join(path.split('/')[-3:]) if path else ''
    wipes = {}
    for rec in trace:
        for i in rec['wipe']:
            wipes.setdefault(i, rec['t'])
    return dict(
        states=[[v, s, e] for v, s, e in runs([rec['state'] for rec in trace])],
        motion_graph=[[v, s, e] for v, s, e in runs([leaf(rec['mg']) for rec in trace])],
        action_graph=[[v, s, e] for v, s, e in runs([leaf(rec['ag']) for rec in trace])],
        tricks=[[v, s, e] for v, s, e in runs([rec['trick'] for rec in trace]) if v],
        grind=[[GRIND_FAMILIES[v] if 0 <= v < len(GRIND_FAMILIES) else v, s, e]
               for v, s, e in runs([rec['grind'] for rec in trace]) if v >= 0],
        wheels_down=[[v, s, e] for v, s, e in runs([rec['wheels'] > 0 for rec in trace])],
        bail=[[i, WIPEOUT_REASONS.get(i, '?'), t] for i, t in sorted(wipes.items(), key=lambda x: x[1])],
        score=r(trace[-1]['score'], 1))


AXIS_INTENTS = ('X', 'Y', 'Z', 'ANGLE', 'MAG', 'TIME', 'COMPRESSION', 'TRANSLATION', 'UPDOWN')


def intents_seen(trace, start=0):
    """First tick each discrete intent (action 'ai:' / motion 'mi:') is set; continuous stick axes are left out."""
    out = {}
    for rec in trace[start:]:
        for key in ('ai', 'mi'):
            for name, value in rec[key].items():
                if value and not name.endswith(AXIS_INTENTS):
                    out.setdefault(f'{key}:{name}', rec['t'])
    return out


def bailed(trace):
    return any(rec['wipe'] for rec in trace) or any('ipeout' in rec['mg'] or 'Bail' in rec['mg'] for rec in trace)


# ---------------------------------------------------------------------------------------------- mechanic numbers
def air_spans(trace, minimum=6):
    """Ticks with no wheel on the ground and no grind, at least `minimum` long: [(first, end exclusive)]."""
    flying = [rec['wheels'] == 0 and not rec['state'].startswith('Grind') and rec['grind'] < 0 for rec in trace]
    return [(s, e) for v, s, e in runs(flying) if v and e - s >= minimum and s > 0]


def world_yaw_turn(trace, s, e):
    """Degrees the deck's forward axis turns about world up (shove-it rotation), skipping near-vertical ticks."""
    total, last = 0.0, None
    for rec in trace[s:e + 1]:
        f = axes(rec)[2]
        if math.hypot(f[0], f[2]) < 0.3:
            continue
        a = yaw(f)
        if last is not None:
            d = (a - last + math.pi) % (2 * math.pi) - math.pi
            total += d
        last = a
    return math.degrees(total)


def frame_rel(rec, frame_axes, origin, p):
    x, y, z = frame_axes
    d = sub(p, origin)
    return [r(dot(d, x)), r(dot(d, y)), r(dot(d, z))]


def standing(trace):
    rec = trace[-1]
    board = bone(rec, 'SKATEBOARD_ROOT')
    hips = bone(rec, 'HIPS')[0]
    frame = axes(rec)
    anim_board = bone(rec, 'SKATEBOARD_ROOT', 'anim')
    return dict(
        hips_over_board_root=r(dot(sub(hips, board[0]), frame[1])),
        hips_over_ground=r(hips[1]),
        board_root_height=r(board[0][1]),
        deck_body_height=r(rec['deck']['p'][1]),
        head_height=r(bone(rec, 'HEAD')[0][1]),
        root_height=r(rec['root'][1]),
        bones_in_deck_frame={name: frame_rel(rec, frame, board[0], bone(rec, name)[0]) for name in KEY},
        animation_bones_in_board_frame={
            name: frame_rel(rec, anim_board[1:], anim_board[0], bone(rec, name, 'anim')[0]) for name in KEY},
        fakie=rec['fakie'], mirrored=rec['mirror'],
        note='bones_in_deck_frame: [left, up, forward] metres from the published SKATEBOARD_ROOT along the physical '
             'deck axes; animation_bones_in_board_frame: the same from the clip pose (root space) along the '
             'animated board bone axes')


def speed_curve(trace, every=6):
    return [[rec['t'], r(hspeed(rec), 2)] for rec in trace[::every]]


def push_numbers(trace):
    speeds = [hspeed(rec) for rec in trace]
    top = max(speeds)
    t90 = next((i for i, s in enumerate(speeds) if s >= 0.9 * top), None)
    pushes = [row for row in clip_segments(trace) if 'PUSH' in row[0].upper()]
    return dict(top_speed=r(top), time_to_90_percent=r((t90 - 30) * DT if t90 is not None else None),
                speed_curve=speed_curve(trace, 12), push_clip_uses=len(pushes),
                first_push_tick=pushes[0][2] if pushes else None,
                note='time_to_90_percent counts from the first press (tick 30)')


def decel(trace, start, end):
    s0, s1 = hspeed(trace[start]), hspeed(trace[end])
    return r((s0 - s1) / ((end - start) * DT))


def slowdown(trace, start=60):
    yaws = unwrap([deck_yaw(rec) for rec in trace])
    stop = next((i for i, rec in enumerate(trace) if i > start and hspeed(rec) < 0.2), None)
    vel_yaw = None
    return dict(start_speed=r(hspeed(trace[start])), deceleration_first_second=decel(trace, start, start + 60),
                deceleration_overall=decel(trace, start, min(len(trace) - 1, start + 240)),
                stop_tick=stop, deck_yaw_change_deg=r(math.degrees(yaws[-1] - yaws[start]), 1),
                speed_curve=speed_curve(trace), travel_yaw=vel_yaw)


def steer_numbers(trace, case):
    yaws = unwrap([deck_yaw(rec) for rec in trace])
    a, b = 120, 200
    rate = (yaws[b] - yaws[a]) / ((b - a) * DT)
    roll = [math.degrees(math.asin(max(-1, min(1, axes(rec)[0][1])))) for rec in trace[a:b]]
    onset = next((i for i in range(31, 200) if abs(yaws[i] - yaws[30]) > math.radians(1)), None)
    return dict(speed=case.get('speed'), stick=case.get('stick'), yaw_rate_deg_s=r(math.degrees(rate), 2),
                turn_radius=r(sum(hspeed(rec) for rec in trace[a:b]) / (b - a) / abs(rate) if rate else None, 2),
                speed_at_120=r(hspeed(trace[a])), speed_at_200=r(hspeed(trace[b])),
                deck_lean_deg=r(sum(roll) / len(roll), 2), first_degree_of_yaw_tick=onset,
                note='yaw rate over ticks 120-200 with the stick held from tick 30; positive yaw turns toward +x '
                     '(left); deck lean is the left axis elevation (+ left edge up)')


def kickturn_numbers(trace):
    yaws = unwrap([deck_yaw(rec) for rec in trace])
    ry = unwrap([root_yaw(rec) for rec in trace])
    return dict(deck_yaw_change_deg=r(math.degrees(yaws[-1] - yaws[0]), 1),
                root_yaw_change_deg=r(math.degrees(ry[-1] - ry[0]), 1),
                peak_yaw_rate_deg_s=r(max(abs(b - a) for a, b in zip(yaws, yaws[1:])) / DT * 180 / math.pi, 1),
                speed_end=r(hspeed(trace[-1])))


def air_profile(trace, s, e, rot, root_rot, every=2):
    base = trace[s - 1]['deck']['p'][1]
    rbase = trace[s - 1]['root'][1]
    out = []
    for i in range(s - 4, min(e + 6, len(trace)), every):
        rec = trace[i]
        k = i - s + 1
        rr = rot[k] if 0 <= k < len(rot) else (None, None, None)
        br = root_rot[k] if 0 <= k < len(root_rot) else (None, None, None)
        out.append([i, r(rec['deck']['p'][1] - base, 3), r(rec['deck']['v'][1], 2), r(rr[2], 1), r(rr[1], 1),
                    r(rr[0], 1), r(rec['root'][1] - rbase, 3), r(br[1], 1)])
    return out


def air_numbers(trace, span=None):
    spans = air_spans(trace)
    if not spans:
        return dict(airborne=False)
    s, e = span or spans[0]
    takeoff = trace[s - 1]
    base = takeoff['deck']['p'][1]
    heights = [rec['deck']['p'][1] for rec in trace[s:e]]
    peak = max(range(len(heights)), key=lambda i: heights[i])
    rot = accumulated(trace, s - 1, min(e + 4, len(trace) - 1))
    root_rot = accumulated(trace, s - 1, min(e + 4, len(trace) - 1), root_axes)
    final = rot[min(len(rot) - 1, e - s + 1)]
    steps = [max(abs(b[i] - a[i]) for i in range(3)) for a, b in zip(rot, rot[1:])]
    fast = [i for i, d in enumerate(steps) if d > 4]  # over 240 deg/s about any deck axis
    vys = [rec['deck']['v'][1] for rec in trace[s - 1:e]]
    # Effective gravity: slope of the deck's vertical speed away from take-off and landing (least squares).
    middle = [(i * DT, rec['deck']['v'][1]) for i, rec in enumerate(trace[s + 4:e - 4])]
    gravity = None
    if len(middle) > 8:
        mt = sum(t for t, _ in middle) / len(middle)
        mv = sum(v for _, v in middle) / len(middle)
        gravity = -sum((t - mt) * (v - mv) for t, v in middle) / sum((t - mt) ** 2 for t, _ in middle)
    after = trace[min(e + 30, len(trace) - 1)]
    landing = trace[min(e, len(trace) - 1)]
    return dict(
        airborne=True, takeoff_tick=s, landing_tick=e, air_time=r((e - s) * DT),
        takeoff_speed=r(hspeed(takeoff)), takeoff_vertical_speed=r(max(vys[:6])),
        pop_height=r(max(heights) - base), apex_tick=s + peak, apex_rise_time=r((peak + 1) * DT),
        landing_speed=r(hspeed(landing)), landing_vertical_speed=r(min(vys)),
        gravity=r(gravity, 2) if gravity is not None else None,
        deck_rotation_deg=dict(roll=r(final[2], 1), yaw=r(final[1], 1), pitch=r(final[0], 1),
                               world_yaw=r(world_yaw_turn(trace, s - 1, min(e, len(trace) - 1)), 1)),
        root_rotation_deg=dict(yaw=r(root_rot[min(len(root_rot) - 1, e - s + 1)][1], 1),
                               roll=r(root_rot[min(len(root_rot) - 1, e - s + 1)][2], 1),
                               pitch=r(root_rot[min(len(root_rot) - 1, e - s + 1)][0], 1)),
        board_spin_start_tick=(s - 1 + fast[0]) if fast else None,
        board_spin_end_tick=(s + fast[-1]) if fast else None,
        peak_deck_rate_deg_s=r(max(steps) * 60, 1) if steps else None,
        rode_away=not bailed(trace) and after['wheels'] > 0,
        profile=air_profile(trace, s, e, rot, root_rot))


def anim_board_rotation(trace, s, e):
    """How far the ANIMATION pose's board (SKATEBOARD_ROOT in root space) and the published board rotate over an air
    span, and how far the animation board travels from the root: shows whether the clip carries the flip."""
    anim = accumulated(trace, s - 1, e, lambda rec: bone(rec, 'SKATEBOARD_ROOT', 'anim')[1:])
    pub = accumulated(trace, s - 1, e, lambda rec: bone(rec, 'SKATEBOARD_ROOT')[1:])
    board_drop = [bone(rec, 'SKATEBOARD_ROOT', 'anim')[0][1] for rec in trace[s:e]]
    return dict(animation_board_rotation_deg=[r(v, 1) for v in anim[-1]],
                published_board_rotation_deg=[r(v, 1) for v in pub[-1]],
                animation_board_height_range=[r(min(board_drop)), r(max(board_drop))],
                note='[about the bone x, y, z axes] summed per tick, over the air span')


def feet_to_board(trace, s, e, every=3):
    out = []
    for rec in trace[s:e:every]:
        board = bone(rec, 'SKATEBOARD_ROOT')[0]
        lf, rf = bone(rec, 'LEFTFOOT')[0], bone(rec, 'RIGHTFOOT')[0]
        hips = bone(rec, 'HIPS')[0]
        out.append([rec['t'], r(norm(sub(lf, board)), 2), r(norm(sub(rf, board)), 2), r(hips[1] - board[1], 2),
                    r(norm(sub(rec['deck']['p'], rec['root'][0:3])), 2)])
    return out


def grind_numbers(case, trace):
    world = case['world']
    rail_x = RAIL_X.get(world, 0.0)
    top = RAIL_TOP.get(world, 0.5)
    first = next((i for i, rec in enumerate(trace) if rec['grind'] >= 0), None)
    mg_first = next((i for i, rec in enumerate(trace) if '/Grind' in rec['mg'] or 'Grind/' in rec['mg']), None)
    out = dict(grinded=first is not None, published_tick=first, motion_graph_grind_tick=mg_first)
    spans = air_spans(trace)
    if spans:
        s, e = spans[0]
        out['takeoff_tick'] = s
        out['air_landing_tick'] = e
        before = trace[s - 1]
        out['deck_x_at_takeoff'] = r(before['deck']['p'][0] - rail_x)
    start = mg_first if mg_first is not None else first
    if start is None:
        if spans:
            s, e = spans[0]
            land = trace[min(e, len(trace) - 1)]
            out['landed_offset'] = r(land['deck']['p'][0] - rail_x)
            out['landed_height'] = r(land['deck']['p'][1])
        out['bailed'] = bailed(trace)
        return out
    pre = trace[max(0, start - 1)]
    at = trace[start]
    rail_dir = [0, 0, 1]
    fwd = axes(at)[2]
    angle = math.degrees(math.atan2(fwd[0], fwd[2]))
    approach = trace[max(0, start - 3)]
    vel_angle = math.degrees(math.atan2(approach['deck']['v'][0], approach['deck']['v'][2]))
    grinding = [i for i, rec in enumerate(trace) if rec['grind'] >= 0 or '/Grind' in rec['mg']]
    end = grinding[-1] + 1
    mid = trace[(start + end) // 2]
    speeds = [hspeed(rec) for rec in trace[start:end]]
    names = []
    for rec in trace[start:end]:
        if rec['trick'] and rec['trick'] not in names:
            names.append(rec['trick'])
    out.update(
        entry_deck_offset=r(pre['deck']['p'][0] - rail_x), entry_deck_height_over_rail=r(pre['deck']['p'][1] - top),
        entry_snap_distance=r(abs(at['deck']['p'][0] - pre['deck']['p'][0]) + 0.0),
        grind_deck_offset=r(mid['deck']['p'][0] - rail_x), grind_deck_height_over_rail=r(mid['deck']['p'][1] - top),
        deck_angle_to_rail_deg=r(angle, 1), approach_velocity_angle_deg=r(vel_angle, 1),
        entry_speed=r(hspeed(pre)), exit_speed=r(hspeed(trace[end - 1])),
        speed_loss_per_s=r((speeds[0] - speeds[-1]) / max(DT, (end - start - 1) * DT)) if len(speeds) > 1 else None,
        duration=r((end - start) * DT), end_tick=end, tricks=names,
        families=sorted({GRIND_FAMILIES[rec['grind']] for rec in trace if 0 <= rec['grind'] < len(GRIND_FAMILIES)}),
        balance_range=[r(min(rec['balance'] for rec in trace[start:end])),
                       r(max(rec['balance'] for rec in trace[start:end]))],
        bailed=bailed(trace),
        note='offsets are deck-body x minus the rail line (+ left); the snap distance is the sideways jump of the '
             'deck on the first grinding tick; deck angle is the deck forward axis yaw from the rail (+z)')
    return out


def manual_numbers(trace):
    ticks = [i for i, rec in enumerate(trace) if rec['manual'] or 'anual' in rec['mg']]
    pitch = [math.degrees(math.asin(max(-1, min(1, -axes(rec)[2][1])))) for rec in trace]
    out = dict(manual_ticks=[ticks[0], ticks[-1] + 1] if ticks else None, bailed=bailed(trace),
               speed_start=r(hspeed(trace[60])), speed_end=r(hspeed(trace[-1])))
    if ticks:
        seg = trace[ticks[0]:ticks[-1] + 1]
        out.update(balance_samples=[[rec['t'], r(rec['balance'], 3), r(rec['manual'], 3),
                                     r(math.degrees(math.asin(max(-1, min(1, -axes(rec)[2][1])))), 1)]
                                    for rec in seg[::6]],
                   deck_pitch_deg_mean=r(sum(pitch[ticks[0]:ticks[-1] + 1]) / len(seg), 1),
                   balance_columns=['tick', 'balance', 'manual', 'deck pitch deg (+ nose down)'])
    return out


def bail_numbers(trace):
    first = None
    for rec in trace:
        if rec['wipe']:
            first = rec
            break
    out = dict(bailed=bailed(trace))
    if first:
        i = first['t']
        prev = trace[max(0, i - 2)]
        out.update(tick=i, reasons=[[k, WIPEOUT_REASONS.get(k, '?')] for k in first['wipe']],
                   speed=r(hspeed(prev)), vertical_speed=r(prev['deck']['v'][1]),
                   deck_up_y=r(axes(prev)[1][1]), state=first['state'], motion=first['mg'])
    return out


def transition_numbers(trace):
    """Per pass across the flat bottom (z crossing 0): speed; per air: height over the lip."""
    passes = []
    for a, b in zip(trace, trace[1:]):
        if (a['deck']['p'][2] < 0) != (b['deck']['p'][2] < 0):
            passes.append([b['t'], r(hspeed(b), 2)])
    airs = []
    for s, e in air_spans(trace):
        peak = max(trace[s:e], key=lambda rec: rec['deck']['p'][1])
        airs.append([s, e, r(peak['deck']['p'][1], 2), r((e - s) * DT, 2)])
    return dict(bottom_passes=passes, airs=airs, max_height=r(max(rec['deck']['p'][1] for rec in trace), 2),
                bailed=bailed(trace),
                note='bottom_passes: [tick, speed] each time the deck crosses z=0; airs: [take-off, landing, '
                     'apex deck height, air time]')


def mechanic_numbers(case, trace):
    group = case['group']
    if group == 'stand':
        return standing(trace)
    if group == 'push':
        return push_numbers(trace)
    if group in ('coast', 'brake', 'powerslide', 'revert'):
        out = slowdown(trace, 30 if group == 'coast' else 60)
        if group == 'revert':
            out.update(kickturn_numbers(trace))
        return out
    if group == 'steer':
        return steer_numbers(trace, case)
    if group == 'kickturn':
        return kickturn_numbers(trace)
    if group == 'manual':
        out = manual_numbers(trace)
        out['air'] = air_numbers(trace) if group == 'manual' and air_spans(trace) else None
        return out
    if group.startswith('grind'):
        out = grind_numbers(case, trace)
        if air_spans(trace):
            air = air_numbers(trace)
            out['air'] = {k: air[k] for k in ('takeoff_tick', 'pop_height', 'deck_rotation_deg', 'root_rotation_deg')}
        return out
    if group in ('transition', 'vert'):
        out = transition_numbers(trace)
        if air_spans(trace):
            out['first_air'] = air_numbers(trace)
        return out
    out = {}
    if group in ('bail', 'drop', 'ground'):
        out['bail'] = bail_numbers(trace)
    numbers = air_numbers(trace)
    if numbers.get('airborne'):
        s, e = numbers['takeoff_tick'], numbers['landing_tick']
        numbers.update(anim_board_rotation(trace, s, e))
        if group in ('ollie', 'flip'):
            numbers['feet_to_board'] = feet_to_board(trace, max(1, s - 6), min(len(trace), e + 9), 4)
    out.update(numbers)
    return out


# ---------------------------------------------------------------------------------------------- clip dumps
def clip_dump(path):
    lines = [json.loads(line) for line in Path(path).read_text().splitlines()]
    head, frames = lines[0], lines[1:]
    index = {name: i for i, name in enumerate(head['bones'])}

    def b(fr, name):
        f = fr['bones'][index[name]]
        return f[0:3], (f[3:6], f[6:9], f[9:12])
    board = [b(fr, 'SKATEBOARD_ROOT') for fr in frames]
    rot = [(0.0, 0.0, 0.0)]
    total = [0.0, 0.0, 0.0]
    for (pa, aa), (pb, ab) in zip(board, board[1:]):
        d = relative_rotation(aa, ab)
        total = [total[i] + math.degrees(d[i]) for i in range(3)]
        rot.append(tuple(total))
    samples = []
    step = max(1, len(frames) // 12)
    for i in list(range(0, len(frames), step)) + ([len(frames) - 1] if (len(frames) - 1) % step else []):
        fr = frames[i]
        bp, ba = board[i]
        rel = lambda name: [r(dot(sub(b(fr, name)[0], bp), ax), 3) for ax in ba]
        samples.append(dict(frame=i, board=[r(v, 3) for v in bp], board_rotation=[r(v, 1) for v in rot[i]],
                            trajectory=[r(v, 3) for v in fr['root'][0:3]],
                            hips=[r(v, 3) for v in b(fr, 'HIPS')[0]],
                            feet=[[r(v, 3) for v in b(fr, n)[0]] for n in ('LEFTFOOT', 'RIGHTFOOT')],
                            left_foot_in_board=rel('LEFTFOOT'), right_foot_in_board=rel('RIGHTFOOT'),
                            hips_in_board=rel('HIPS'), right_hand_in_board=rel('RIGHTHAND'),
                            left_hand_in_board=rel('LEFTHAND')))
    return dict(frames=head['frames'], fps=head['fps'], board_rotation_total=[r(v, 1) for v in rot[-1]],
                samples=samples,
                note='each frame composed onto RIG_TPOSE and BOARD_BACKWARDS, before the runtime\'s stance mirror (the live '
                     'regular rider is this pose reflected front to back, left and right swapped). board, hips, feet: '
                     'root space of the clip (metres, y up); trajectory: the clip\'s own TRAJECTORY track (root '
                     'motion before the runtime turns it into per-tick deltas); *_in_board: metres along the board '
                     'bone axes from the board root; board_rotation: summed about the board bone axes, degrees')


# ---------------------------------------------------------------------------------------------- summary
def summary(mechanics):
    m = mechanics
    get = lambda name, *keys: _dig(m.get(name, {}).get('numbers'), keys)
    out = {}
    out['standing'] = {k: get('stand/idle', k) for k in ('hips_over_board_root', 'hips_over_ground',
                                                         'board_root_height', 'head_height')}
    out['push'] = {name.split('/', 1)[1]: dict(top_speed=get(name, 'top_speed'),
                                               time_to_90_percent=get(name, 'time_to_90_percent'))
                   for name in m if name.startswith('push/')}
    out['coast_deceleration'] = {name: get(name, 'deceleration_overall') for name in m if name.startswith('coast/')}
    out['brake'] = {name: dict(decel_first_s=get(name, 'deceleration_first_second'), stop_tick=get(name, 'stop_tick'))
                    for name in m if name.startswith('brake/') or name.startswith('powerslide/')}
    out['steer_yaw_rate_deg_s'] = {name.split('/', 1)[1]: get(name, 'yaw_rate_deg_s')
                                   for name in m if name.startswith('steer/')}
    out['ollie'] = {name: dict(pop_height=get(name, 'pop_height'), air_time=get(name, 'air_time'),
                               takeoff_vy=get(name, 'takeoff_vertical_speed'), rode_away=get(name, 'rode_away'))
                    for name in m if name.startswith('ollie/') or name.startswith('nollie/')}
    flips = {}
    for name, entry in m.items():
        if entry['group'] in ('flip', 'late', 'fingerflip', 'bodyflip', 'spin'):
            n = entry.get('numbers') or {}
            if not n.get('airborne'):
                flips[name] = dict(trick=[t[0] for t in entry['tricks']], airborne=False)
                continue
            flips[name] = dict(trick=[t[0] for t in entry['tricks']], deck=n['deck_rotation_deg'],
                               body_yaw=n['root_rotation_deg']['yaw'], air_time=n['air_time'],
                               spin_ticks=[n['board_spin_start_tick'], n['board_spin_end_tick']],
                               takeoff=n['takeoff_tick'], rode_away=n['rode_away'], bail=entry['bail'])
    out['air_tricks'] = flips
    out['grabs'] = {name: dict(trick=[t[0] for t in entry['tricks']], rode_away=_dig(entry, ('numbers', 'rode_away')),
                               air_time=_dig(entry, ('numbers', 'air_time')))
                    for name, entry in m.items() if entry['group'] == 'grab'}
    out['grinds'] = {name: {k: _dig(entry, ('numbers', k)) for k in ('grinded', 'tricks', 'families',
                                                                      'deck_x_at_takeoff', 'entry_deck_offset',
                                                                      'deck_angle_to_rail_deg', 'entry_speed',
                                                                      'speed_loss_per_s', 'duration', 'bailed')}
                     for name, entry in m.items() if entry['group'].startswith('grind')}
    out['bails'] = {name: dict(bail=entry['bail'], bailed=_dig(entry, ('numbers', 'bail', 'bailed')),
                               numbers=_dig(entry, ('numbers', 'bail')),
                               states=[st for st in entry['states'] if 'ipeout' in st[0] or 'Grind' in st[0]],
                               landing_vertical_speed=_dig(entry, ('numbers', 'landing_vertical_speed')),
                               body_yaw=_dig(entry, ('numbers', 'root_rotation_deg', 'yaw')))
                    for name, entry in m.items() if entry['group'] in ('bail', 'drop')}
    out['ground_tricks'] = {name: dict(trick=[t[0] for t in entry['tricks']],
                                       states=[st[0] for st in entry['states']],
                                       pop_height=_dig(entry, ('numbers', 'pop_height')))
                            for name, entry in m.items() if entry['group'] == 'ground'}
    landings = {}
    for name, entry in m.items():
        clips = []
        for row in entry['clips']:
            if row[0].startswith('L_') and row[4] > 0.3 and row[0] not in clips:
                clips.append(row[0])
        if not clips:
            continue
        air = entry.get('numbers') or {}
        air = air.get('first_air') or air.get('air') or air
        deck, body = _dig(air, ('deck_rotation_deg', 'world_yaw')), _dig(air, ('root_rotation_deg', 'yaw'))
        landings[name] = dict(clips=clips, landing_vertical_speed=air.get('landing_vertical_speed'),
                              board_to_body_yaw_deg=r(deck - body, 1) if deck is not None and body is not None
                              else None, bailed=bool(entry['bail']) or any('ipeout' in st[0]
                                                                          for st in entry['states']))
    out['landings'] = dict(
        note='landing clips by scenario (weight over 0.3): L_HCOM / L_LCOM high or low centre of mass, LIMP / HIMP '
             'low or high impact, L_NICE clean (after spins), L_SKETCH sketchy; board_to_body_yaw_deg is the deck '
             'world yaw minus the body yaw over the first air',
        scenarios=landings)
    out['air_gravity'] = {name: get(name, 'gravity') for name in m
                          if m[name]['group'] in ('ollie', 'drop') and get(name, 'gravity') is not None}
    return out


def _dig(value, keys):
    for k in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(k)
    return value


def build_reference(cases, traces, scenarios):
    out = dict(
        format=1,
        source='Native GameplaySession (platform/engine/Plugins/Activities/Skate), recorded with '
               'Tests/ride_oracle.py and Tests/Native/ride_oracle_recorder.cpp',
        conventions=dict(
            tick='1/60 s; scenario tick 0 is the state right after Launch(velocity), tick n after n pad steps',
            units='metres, seconds, degrees where a key says deg',
            space='native: x left, y up, z forward; heading 0 rides toward +z; rotations right-handed',
            pad=dict(buttons=dict(A=0x1000, B=0x2000, X=0x4000, Y=0x8000, LB=0x0100, RB=0x0200, LS=0x0040,
                                  RS=0x0080, transfer=0x0800),
                     sticks='raw -32767..32767, +x right, +y up; conditioned = (|raw|/32768 - 0.25) x 1.4286, '
                            'clamped to 0..1 along the stick direction',
                     triggers='0..255 (255 on the ground is a ground grab; 1..254 crouches / pumps)',
                     event='[start_tick, end_tick (exclusive), {field: value}]; neutral pad elsewhere'),
            stance='regular unless the scenario uses the goofy tuning; the game mirrors Flick-It pattern names for a '
                   'regular rider (pattern Heelflip gives a kickflip)',
            tuning=dict(game=scenarios.GAME, stock=scenarios.STOCK),
            clips='clip segments: layer is the blend node or channel the clip played in; weight its effective share '
                  'of the evaluated pose (product of the blend weights above it); time the clip time in seconds '
                  'at the segment start and end; rate the median playback rate; loops the number of wraps',
            graph_states='last three levels of the motion / action graph state path',
            columns=dict(
                clips=CLIP_COLUMNS,
                profile=['tick', 'deck height over take-off', 'deck vy', 'deck roll deg', 'deck yaw deg',
                         'deck pitch deg', 'root height over take-off', 'root yaw deg'],
                feet_to_board=['tick', 'left foot to board root', 'right foot to board root', 'hips over board root',
                               'deck body to root origin']),
            rotations='deck rotations sum the per-tick rotation about the moving deck axes (right-handed; x left, '
                      'y up, z forward): roll about forward (+ lifts the left edge), yaw about up (+ turns the nose '
                      'toward +x, left), pitch about left (+ drops the nose); world_yaw is the turn of the deck '
                      'forward axis about world up (the shove-it part); board spin ticks bound the deck turning '
                      'faster than 240 deg/s; combined flips leak some shove-it into roll',
            bail_reasons=WIPEOUT_REASONS,
            gestures=dict(main=scenarios.MAIN, air=scenarios.AIR, fingerflip=scenarios.FINGERFLIP,
                          left=scenarios.LEFT,
                          note='conditioned stick points, +y up; a node starts within the tolerance (0.35-0.55) '
                               'of the first point and must reach each next point within ~10 missed ticks; '
                               'GestureSpeed = 1 when ticks/points <= 1.75, 0 at >= 4.4')),
        mechanics={}, clips={})
    for case in cases:
        trace = load(traces, case['name'])
        if trace is None:
            continue
        entry = dict(group=case['group'], note=case['note'], world=case['world'], spawn=case['spawn'],
                     heading=case['heading'], velocity=case['velocity'],
                     tuning='game' if case['tune'] == scenarios.GAME else
                     ('stock' if case['tune'] == scenarios.STOCK else
                      ('goofy' if case['tune'] == scenarios.GOOFY else case['tune'])),
                     recipe=dict(length=case['length'], events=case['events']))
        if case.get('pattern'):
            entry['pattern'] = case['pattern']
        # A launched rider spends ticks 2-50 in a "Bumped" reaction to the launch: skip it unless inputs start there.
        first_input = min([e[0] for e in case['events']] or [case['length']])
        start = 0 if case['velocity'] == [0, 0, 0] or first_input < 50 else 50
        entry['analysed_from'] = start
        entry.update(timeline(trace))
        entry['clips'] = clip_segments(trace, start=start)
        entry['intents'] = intents_seen(trace, start)
        entry['numbers'] = mechanic_numbers(case, trace)
        out['mechanics'][case['name']] = entry
    for path in sorted((Path(traces) / 'clips').glob('*.jsonl')):
        out['clips'][path.stem] = clip_dump(path)
    out['summary'] = summary(out['mechanics'])
    return out
