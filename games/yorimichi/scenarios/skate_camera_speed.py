#!/usr/bin/env python3
"""The skate camera and the shown rider at very high speed (40 to 47 m/s, 145 to 170 km/h).

Run against a running game (atelier play yorimichi):
    atelier qa yorimichi skate_camera_speed [--label follow2] [--camera-follow 1] [--at X,Y --yaw Y --speed 46]
    atelier qa yorimichi skate_camera_speed --probe --at X,Y --yaw Y     # the ground's profile along the run only

It puts the rider on the board at --at (Unreal cm) facing --yaw, launches it at --speed (m/s), rides hands off, and
records every rendered frame (from the bridge's post-tick callback, after the frame's camera update): the real frame
time, the session's tick, the board's speed, the camera's world location, the pelvis and deck world locations, the
pelvis in the deck's frame, the pelvis and deck projected to the screen (in 2560x1440 pixels whatever the window) and
the camera-to-pelvis distance. A second, identical run takes a short sequence of frames at top speed (shots cost
frames, so they never share a run with the measurement).

--camera-follow sets USkateSettings.CameraFollow on the class default and switches the rider out and back so the new
pawn takes it (FSkateFeel::Defaults reads the class default), without saving any setting. The measured gap growth
shows which follow speed was in effect.

Writes build/yorimichi/skateqa/camera/<label>.json (summary and every frame) and <label>-NN.png.
"""
import argparse
import json
import math
import re
import sys
import time

import skate as qa

SAMPLER = r'''
import re, time
W = live.L.game_world()
PC = unreal.GameplayStatics.get_player_controller(W, 0)
PCM = unreal.GameplayStatics.get_player_camera_manager(W, 0)
P = live.L.player(); M = P.get_editor_property('mesh')
D = next(c for c in P.get_components_by_class(unreal.StaticMeshComponent) if c.get_name() == 'SkateDeck')
_num = re.compile(r'(?:^|\s)(mode|speed|tick)=([-0-9.]+)')
_world = re.compile(r'world=(\d+):(\d+) cost=([0-9.]+)/([0-9.]+)')
def _screen(at):
    r = unreal.GameplayStatics.project_world_to_screen(PC, at, False)
    if isinstance(r, tuple): r = r[1] if r[0] else None
    return [round(r.x, 2), round(r.y, 2)] if r is not None else None
live.CAM = []; live.CAM_T0 = time.perf_counter()
def cam_sample(dt):
    s = live.skate_state()
    f = {}
    for k, v in _num.findall(s.split(' | ')[0]): f.setdefault(k, v)
    w = _world.search(s)
    c = PCM.get_camera_location(); cr = PCM.get_camera_rotation()
    pel = M.get_socket_location('pelvis'); dk = D.get_world_location()
    inside = D.get_world_transform().inverse_transform_location(pel)
    vx, vy = PC.get_viewport_size()
    live.CAM.append([round(time.perf_counter() - live.CAM_T0, 5), round(dt, 5), int(f.get('tick', 0)), int(f.get('mode', -1)),
        float(f.get('speed', 0)), [round(c.x, 1), round(c.y, 1), round(c.z, 1)], [round(cr.pitch, 3), round(cr.yaw, 3)],
        [round(pel.x, 1), round(pel.y, 1), round(pel.z, 1)], [round(dk.x, 1), round(dk.y, 1), round(dk.z, 1)],
        [round(inside.x, 2), round(inside.y, 2), round(inside.z, 2)], _screen(pel), _screen(dk), [vx, vy],
        [int(w.group(1)), int(w.group(2)), float(w.group(3)), float(w.group(4))] if w else None])
live.behave('cam_sample', cam_sample)
'''
# USkateSettings is not a BlueprintType: Python reaches it by path and its properties by their C++ names.
SETTINGS = "unreal.get_default_object(unreal.load_class(None, '/Script/AtelierSkate.SkateSettings'))"
FIELDS = ('t', 'dt', 'tick', 'mode', 'speed', 'camera', 'camera_rotation', 'pelvis', 'deck', 'pelvis_in_deck', 'screen_pelvis',
          'screen_deck', 'viewport', 'world')


def percentile(values, p):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * p))] if ordered else 0.


def stats(values, digits=2):
    values = [abs(v) for v in values]
    if not values:
        return {}
    return dict(mean=round(sum(values) / len(values), digits), p95=round(percentile(values, .95), digits),
                max=round(max(values), digits))


def reversals(deltas, floor):
    """Sign changes between successive frame-to-frame moves bigger than `floor` (a stutter's back-and-forth)."""
    signs = [1 if d > floor else -1 if d < -floor else 0 for d in deltas]
    signs = [s for s in signs if s]
    return sum(a != b for a, b in zip(signs, signs[1:]))


def dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def summarize(rows, low, high, skip=0.):
    """The frames whose board speed is in [low, high] m/s while riding (mode 1), as one window, from `skip` seconds
    after the sampler starts (the launch itself makes the rider drop into a crouch over a few frames)."""
    frames = [dict(zip(FIELDS, r)) for r in rows]
    frames = [f for f in frames if f['t'] >= skip]
    for f in frames:
        f['speed_ms'] = f['speed'] / 100.
        f['gap_m'] = dist(f['camera'], f['pelvis']) / 100.
    # The longest contiguous run of frames riding (mode 1, not in the air) in the speed band.
    best, start = (0, 0), None
    for i, f in enumerate(frames + [None]):
        inside = f is not None and low <= f['speed_ms'] <= high and f['mode'] == 1
        if inside and start is None: start = i
        if not inside and start is not None:
            if i - start > best[1] - best[0]: best = (start, i)
            start = None
    window = frames[best[0]:best[1]]
    if len(window) < 10:
        return dict(frames=len(frames), window_frames=len(window), note='too few frames in the speed window')
    seconds = window[-1]['t'] - window[0]['t']
    dts = [f['dt'] * 1000 for f in window[1:]]
    ticks = [b['tick'] - a['tick'] for a, b in zip(window, window[1:])]
    scale = 1440. / max(window[0]['viewport'][1], 1)
    sp = [(f['screen_pelvis'][0] * scale, f['screen_pelvis'][1] * scale) if f['screen_pelvis'] else None for f in window]
    pairs = [(a, b) for a, b in zip(sp, sp[1:]) if a and b]
    dx = [b[0] - a[0] for a, b in pairs]; dy = [b[1] - a[1] for a, b in pairs]
    d2x = [b - a for a, b in zip(dx, dx[1:])]; d2y = [b - a for a, b in zip(dy, dy[1:])]
    inside = [f['pelvis_in_deck'] for f in window]
    ix = [[b[k] - a[k] for a, b in zip(inside, inside[1:])] for k in range(3)]
    # The camera's own motion: its distance per frame over the frame's time, against the board's speed.
    cam_speed = [dist(a['camera'], b['camera']) / 100. / max(b['dt'], 1e-4) for a, b in zip(window, window[1:])]
    rider_speed = [dist(a['pelvis'], b['pelvis']) / 100. / max(b['dt'], 1e-4) for a, b in zip(window, window[1:])]
    ratio = [c / max(r, 1e-3) for c, r in zip(cam_speed, rider_speed)]
    gap = [f['gap_m'] for f in window]
    n = len(gap); ts = [f['t'] - window[0]['t'] for f in window]
    mt, mg = sum(ts) / n, sum(gap) / n
    slope = sum((t - mt) * (g - mg) for t, g in zip(ts, gap)) / max(sum((t - mt) ** 2 for t in ts), 1e-9)
    hitches = [round(f['t'] - window[0]['t'], 3) for f in window[1:] if f['dt'] > .025]
    worlds = [f['world'][0] for f in window if f['world']]
    return dict(
        window_starts_s=round(window[0]['t'] - frames[0]['t'], 2), seconds=round(seconds, 2), frames=len(window), speed_ms=dict(start=round(window[0]['speed_ms'], 1), end=round(window[-1]['speed_ms'], 1),
        min=round(min(f['speed_ms'] for f in window), 1), max=round(max(f['speed_ms'] for f in window), 1)),
        camera_gap_m=dict(start=round(gap[0], 2), end=round(gap[-1], 2), min=round(min(gap), 2), max=round(max(gap), 2),
                          growth_m_per_s=round(slope, 3),
                          every_quarter_second=[round(f['gap_m'], 2) for f in window[::15]]),
        screen_pelvis_px_1440=dict(x=stats(dx), y=stats(dy), x_accel=stats(d2x), y_accel=stats(d2y),
                                   x_reversals=reversals(dx, .5), y_reversals=reversals(dy, .5),
                                   position_x=dict(min=round(min(p[0] for a in pairs for p in a), 1), max=round(max(p[0] for a in pairs for p in a), 1)),
                                   position_y=dict(min=round(min(p[1] for a in pairs for p in a), 1), max=round(max(p[1] for a in pairs for p in a), 1))),
        pelvis_in_deck_cm=dict(x=stats(ix[0]), y=stats(ix[1]), z=stats(ix[2]),
                               x_reversals=reversals(ix[0], .3), y_reversals=reversals(ix[1], .3), z_reversals=reversals(ix[2], .3)),
        camera_vs_rider_speed=dict(ratio_mean=round(sum(ratio) / len(ratio), 3), ratio_p05=round(percentile(ratio, .05), 3),
                                   ratio_p95=round(percentile(ratio, .95), 3)),
        pacing=dict(fps=round(1000 / (sum(dts) / len(dts)), 2), p95_ms=round(percentile(dts, .95), 2), p99_ms=round(percentile(dts, .99), 2),
                    worst_ms=round(max(dts), 2), over_25ms=len(hitches), hitch_times_s=hitches[:40],
                    repeated_simulation_frames=sum(t == 0 for t in ticks), double_tick_frames=sum(t >= 2 for t in ticks),
                    collision_rebuilds=(max(worlds) - min(worlds)) if worlds else None))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--port', type=int, default=8830)
    parser.add_argument('--label', default='run')
    parser.add_argument('--at', default='', help='start, Unreal cm "x,y" (default: the Crater Park floor straight)')
    parser.add_argument('--yaw', type=float, default=None, help='heading, Unreal yaw degrees')
    parser.add_argument('--z', type=float, default=0., help='about the ground height there, Unreal cm (live GroundAt traces +20 m/-60 m)')
    parser.add_argument('--speed', type=float, default=46., help='launch speed, m/s')
    parser.add_argument('--seconds', type=float, default=7.)
    parser.add_argument('--low', type=float, default=40.); parser.add_argument('--high', type=float, default=47.5)
    parser.add_argument('--camera-follow', type=float, default=None, help='set USkateSettings.CameraFollow (1 stock, 2 this game)')
    parser.add_argument('--rider', default='', help='switch to this rider first (and back through another for --camera-follow)')
    parser.add_argument('--shots', type=int, default=8, help='frames in the shot sequence (0 none)')
    parser.add_argument('--shot-at', type=float, default=2.5, help='seconds after the launch the sequence starts')
    parser.add_argument('--probe', action='store_true', help='print the ground profile along the run and stop')
    parser.add_argument('--skip', type=float, default=.8, help='seconds of the record left out of the summary (launch at .2 s)')
    parser.add_argument('--from-json', default='', help='summarize a saved run again (no game) and rewrite its summary')
    args = parser.parse_args()
    if args.from_json:
        saved = json.loads(open(args.from_json).read())
        saved['summary'] = summarize(saved['frames'], args.low, args.high, args.skip); saved['skip'] = args.skip
        open(args.from_json, 'w').write(json.dumps(saved) + '\n')
        print(json.dumps(saved['summary'], indent=1)); return 0
    qa.bridge.URL = f'http://127.0.0.1:{args.port}'
    qa.py((qa.GAME / 'scenarios/skate_live_skate.py').read_text())
    x, y = (float(v) for v in args.at.split(',')) if args.at else (0., 0.)
    yaw = args.yaw if args.yaw is not None else 0.
    if args.probe:
        print(qa.py(f'''
import math
h = math.radians({yaw}); prev = None; z = {args.z} + 1000
for i in range(0, 401, 5):
    p = live.L.ground_at(unreal.Vector({x} + math.cos(h) * i * 100, {y} + math.sin(h) * i * 100, z))
    print(i, round(p.z / 100, 2), '' if prev is None else round((p.z - prev) / 500, 3)); prev = p.z; z = p.z + 1000
'''))
        return 0
    if args.camera_follow is not None:
        qa.py(f"{SETTINGS}.set_editor_property('CameraFollow', {args.camera_follow!r})")
        print('CameraFollow class default now', qa.py(f"print({SETTINGS}.get_editor_property('CameraFollow'))").strip(), flush=True)
        rider = args.rider or 'Modori'
        other = 'Cairo' if rider != 'Cairo' else 'Modori'
        for name in (other, rider):
            print('switch', qa.py(f'print(live.L.switch_character({name!r}))').strip(), flush=True); time.sleep(3)
    elif args.rider:
        print('switch', qa.py(f'print(live.L.switch_character({args.rider!r}))').strip(), flush=True); time.sleep(3)
    qa.py('live.L.fixed_step(0); live.skate_park(); live.skate_input()')
    for _ in range(60):
        if 'simulation=PhysicsGround' in qa.py('print(live.skate_state())'):
            break
        time.sleep(.5)
    else:
        raise RuntimeError('Ride did not mount')
    qa.settle(minimum=55, seconds=2, limit=60)
    out = qa.yori.OUT / 'skateqa' / 'camera'; out.mkdir(parents=True, exist_ok=True)
    report = dict(label=args.label, at=[x, y], yaw=yaw, speed=args.speed,
                  camera_follow=float(qa.py(f"print({SETTINGS}.get_editor_property('CameraFollow'))").strip()),
                  rider=qa.py('print(live.L.player().get_editor_property("mesh").get_skeletal_mesh_asset().get_name())').strip())

    def ride(shots):
        qa.py(f'live.skate_place(live.L.ground_at(unreal.Vector({x}, {y}, {args.z + 1000})), {yaw}); live.skate_input()')
        time.sleep(2.)    # the board camera eases in over about 0.6 s; then the session settles
        qa.py(SAMPLER)
        time.sleep(.2)
        h = math.radians(yaw)
        qa.py(f'live.L.skate_launch(unreal.Vector({args.speed * 100 * math.cos(h)}, {args.speed * 100 * math.sin(h)}, 0))')
        start = time.monotonic(); taken = []
        if shots:
            time.sleep(args.shot_at)
            for i in range(shots):
                path = out / f'{args.label}-{i:02d}.png'
                qa.py(f'live.L.screenshot({str(path)!r})'); taken.append(path.name)
                time.sleep(.12)
        time.sleep(max(0., args.seconds - (time.monotonic() - start)))
        rows = json.loads(qa.py("live.stop('cam_sample'); import json; print(json.dumps(live.CAM))").strip().splitlines()[-1])
        return rows, taken

    rows, _ = ride(0)
    report['state_at_end'] = qa.py('print(live.skate_state())').strip()[:300]
    report['summary'] = summarize(rows, args.low, args.high, args.skip); report['skip'] = args.skip
    report['whole_run_speed_ms'] = [round(r[4] / 100, 1) for r in rows[::15]]
    print(json.dumps(report['summary'], indent=1), flush=True)
    if args.shots:
        shot_rows, taken = ride(args.shots)
        report['shots'] = taken
        report['shot_run_speed_ms'] = [round(r[4] / 100, 1) for r in shot_rows[::15]]
    report['frames'] = rows
    (out / f'{args.label}.json').write_text(json.dumps(report) + '\n')
    print('wrote', out / f'{args.label}.json', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    finally:
        if '--from-json' not in sys.argv:
            qa.py("live.stop('cam_sample'); live.skate_release()")
