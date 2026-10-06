"""Ride Cairo in the real game and check his feet stay on the board: rolling, in ollies and manuals, at 60 and 30 fps,
and that big airs land back in the transition.

    uv run python games/yorimichi/tools/review_skate_jump_feet.py [--port 8871] [--rider CairoBotw|Cairo] [--settings FILE] [--desktop-profile]

Run after unreal.compile. Under the render guard it launches the island and:
- stands Cairo on foot on the mini-mega's flat and measures his soles and capsule over the floor;
- on the wood flat before the mini-mega's quarter, puts him back on the board before every trial, pushes and ollies
  (three times) and holds a manual, with the physical rider (skate.RidePhysical 1, the default) and animated only (0),
  at 60 and then 30 fps. Every frame it keeps the frame's time, the skate state and, in the deck's own frame, each ankle
  and toe bone's height over the deck's top and offset along it. The animated rider stands on the deck by construction,
  so the physical rider's feet must match it: one that trails the board (Physics Control ticking after the physics
  step) shows as feet behind and above the deck in the air and sunk into it in a manual, by the speed times the frame;
- pushes from the flat into the quarter three times, harder each time, so the board airs out and lands back in the
  transition;
- pushes off the mini-mega's roll-in, over its kicker into the landing;
- reads the game's log for the physical rider's warning that it ticks after the physics step.
The close shots look at the deck from the side. The rider is Cairo as a person plays him, with the merged move set
(CairoBotw, the default since #28), or his legacy moves (Cairo), which scripted sessions get unless asked. --settings
plays with a saved settings file (a copy of a player's settings.txt: skate mode, feel, stance), copied into the output
folder so the game's own saves leave the original alone. Writes
build/yorimichi/skate-jump-feet/review/<rider>[-<label>]/{checks.json, rows_*.json, *.png, game.log}.
--desktop-profile uses normal native 1440p play (including city tiles), preserving an isolated copy of saved preferences.
The worker owns and quits only the game process it launches.
"""
from pathlib import Path
from contextlib import ExitStack
import argparse, itertools, json, re, socket, subprocess, sys, time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world' / 'regions'))
import yori
from mega.layout import ORIGIN
from atelier.build import Context
from atelier.safety import guarded
from atelier.safety.guard import attach as attach_memory_guard, reap
from atelier import live
from desktop_preview import bridge_bind_error, command as desktop_command, read_preferences, renderer_arguments, toggle

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
parser.add_argument('--port', type=int, default=8871)
parser.add_argument('--rider', default='CairoBotw', choices=('CairoBotw', 'Cairo'))
parser.add_argument('--settings', type=Path, help="a player's settings.txt to play with")
parser.add_argument('--label', default='', help='output subfolder suffix, to keep runs with different settings apart')
parser.add_argument('--settle-fps', type=float, default=25., help='frame rate to hold for 3 s before the checks (a slower host may name a lower one; the phases\' own frame timing is still graded)')
parser.add_argument('--desktop-profile', action='store_true', help='normal native 1440p play profile, with an isolated copy of saved preferences')
args = parser.parse_args()
live.URL = f'http://127.0.0.1:{args.port}'
ctx = Context('yorimichi'); out = yori.OUT / 'skate-jump-feet' / 'review' / (args.rider + (f'-{args.label}' if args.label else '')); out.mkdir(parents=True, exist_ok=True)

if not args.worker:
    sys.exit(guarded.run([sys.executable, str(Path(__file__).resolve()), '--worker'] + sys.argv[1:], out / 'guard', timeout=900,
                         purpose='skate jump feet review', kind='game'))

ox, oy, oz = ORIGIN
FLAT_Z = oz + .45                       # the START flat's height (m)
START = (ox + 50, oy + 3, oz + 2)     # on foot: the landing's level wood (0.45 m from x 49 to 56), clear of the rollout
LANE = (ox + 44.6, oy - 2, oz + 2)    # the landing's run-out (4° down) before the quarter, riding toward +x
DROP_IN = (ox - 2.6, oy, oz + 12)     # the roll-in's top deck
QUARTER_X = 56.                       # where the quarter's transition starts, along the ramp
OLLIES = 3
QUARTER_PUSHES = (2.5, 3.0, 3.5)   # seconds of pushing from the lane, as a player would; the board reaches the transition
                                   # ~11 m on, at 8.4-8.9 m/s (Easy, Normal), so a longer push adds nothing
QUARTER_LAUNCHES = (11., 12., 13.)  # m/s along +x from the lane, no push: the native regression's speeds, as from a drop-in.
                                    # A regression trial for landing back in the transition, not a measure of ordinary pushing
# A physical foot may differ from the animated one by this much (cm, a phase's mean, any bone, up or along the deck).
# They match within 0.6 cm when Physics Control ticks before the physics step; a frame behind, the feet sit 10 cm off
# at 60 fps (5.5 m/s for 17 ms) and twice that at 30.
TRACKING = 2.0
LATE_TICK = 'Physics Control ticks after the physics step'
# The recorder: the frame's time, the skate state, then per bone (ankle and toe, left then right) its height over the
# deck's top in the deck's frame (cm) and its offset along and across the deck.
RECORDER = r'''
P = unreal.LiveLibrary.player(); M = P.get_editor_property('mesh')
D = next(c for c in P.get_components_by_class(unreal.StaticMeshComponent) if c.get_name() == 'SkateDeck')
live.DECK_TOP = D.get_editor_property('static_mesh').get_bounding_box().max.z
live.FEET = []
def _feet(dt):
    T = D.get_world_transform(); bones = []
    for b in ('foot_L', 'toe_L', 'foot_R', 'toe_R'):
        p = T.inverse_transform_location(M.get_socket_location(b)); bones.append((round(p.z - live.DECK_TOP, 2), round(p.x, 1), round(p.y, 1)))
    live.FEET.append((dt, live.L.skate_state(), bones))
live.behave('feet_rec', _feet)
'''
# The close view: the player's camera beside the deck, looking at it, held there over the game's own camera.
CLOSE = r'''
P = unreal.LiveLibrary.player(); D = next(c for c in P.get_components_by_class(unreal.StaticMeshComponent) if c.get_name() == 'SkateDeck')
C = P.get_components_by_class(unreal.CameraComponent)[0]
if getattr(live, 'CAMHOME', None) is None:
    live.CAMHOME = (C.get_attach_parent(), C.get_attach_socket_name(), C.get_relative_transform(), C.get_editor_property('field_of_view'))
T = D.get_world_transform(); at = T.translation; v = P.get_velocity(); v.z = 0
f = v.normal() if v.length() > 10 else T.rotation.get_forward_vector()
loc = at + unreal.Vector(-f.y, f.x, 0) * 95 + unreal.Vector(0, 0, 14)
C.detach_from_component(unreal.DetachmentRule.KEEP_WORLD, unreal.DetachmentRule.KEEP_WORLD, unreal.DetachmentRule.KEEP_WORLD)
C.set_world_location_and_rotation(loc, unreal.MathLibrary.find_look_at_rotation(loc, at + unreal.Vector(0, 0, 8)), False, True)
C.attach_to_component(D, '', unreal.AttachmentRule.KEEP_WORLD, unreal.AttachmentRule.KEEP_WORLD, unreal.AttachmentRule.KEEP_WORLD, False)
C.set_editor_property('field_of_view', 45.0)
unreal.YorimichiLive.hold_camera(6.0)
'''
# The on-foot close view: low beside Cairo, level with his shoes, so a sole sunk into the floor shows against it.
FOOT_CLOSE = r'''
P = unreal.LiveLibrary.player(); C = P.get_components_by_class(unreal.CameraComponent)[0]
if getattr(live, 'CAMHOME', None) is None:
    live.CAMHOME = (C.get_attach_parent(), C.get_attach_socket_name(), C.get_relative_transform(), C.get_editor_property('field_of_view'))
M = P.get_editor_property('mesh'); f = P.get_actor_forward_vector(); f.z = 0; f = f.normal()
feet = (M.get_socket_location('foot_L') + M.get_socket_location('foot_R')) * .5
loc = feet + unreal.Vector(-f.y, f.x, 0) * 70 + unreal.Vector(0, 0, 1)
C.detach_from_component(unreal.DetachmentRule.KEEP_WORLD, unreal.DetachmentRule.KEEP_WORLD, unreal.DetachmentRule.KEEP_WORLD)
C.set_world_location_and_rotation(loc, unreal.MathLibrary.find_look_at_rotation(loc, feet - unreal.Vector(0, 0, 2)), False, True)
C.set_editor_property('field_of_view', 35.0)
unreal.YorimichiLive.hold_camera(6.0)
'''
HOME = r'''
P = unreal.LiveLibrary.player(); C = P.get_components_by_class(unreal.CameraComponent)[0]
if getattr(live, 'CAMHOME', None) is not None:   # nothing to restore before a close view has moved the camera
    parent, sock, rel, fov = live.CAMHOME
    C.attach_to_component(parent, sock, unreal.AttachmentRule.KEEP_RELATIVE, unreal.AttachmentRule.KEEP_RELATIVE, unreal.AttachmentRule.KEEP_RELATIVE, False)
    C.set_relative_transform(rel, False, True); C.set_editor_property('field_of_view', fov)
unreal.YorimichiLive.hold_camera(0.0)
'''


def record(name, ok, note):
    checks[name] = dict(ok=bool(ok), note=note); print(('PASS ' if ok else 'FAIL ') + name + ': ' + note, flush=True)


checks = {}
owns_bridge = False
with socket.socket() as probe:
    if probe.connect_ex(('127.0.0.1', args.port)) == 0:
        raise RuntimeError(f'Review port {args.port} is occupied; refusing another game')
# The desktop launcher writes its own abslog; never point redirected stdout at that same file.
log = (out / ('console.log' if args.desktop_profile else 'game.log')).open('w')
cmd = [str(ctx.unreal_app), str(ctx.uproject), '-game', '-windowed', '-resx=1280', '-resy=720', '-nosplash', '-stdout', '-nofox',
       f'-liveport={args.port}', '-ini:Engine:[HTTPServer.Listeners]:DefaultBindAddress=localhost',
       '-ExecCmds=t.MaxFPS 60,r.RHISetGPUCaptureOptions 0,DisableAllScreenMessages']
if args.rider == 'CairoBotw': cmd.append('-rider=CairoBotw')   # without it a scripted session keeps his legacy moves
if args.settings:
    (out / 'settings.txt').write_text(args.settings.read_text()); cmd.append(f"-preferencesfile={out / 'settings.txt'}")
preferences = out / 'settings.txt' if args.settings else ctx.uproject.parent / 'Saved' / 'settings.txt'
cmd.extend(renderer_arguments(toggle(read_preferences(preferences), 'renderer', 0)))
if args.desktop_profile:
    if not args.settings:
        (out / 'settings.txt').write_text(preferences.read_text() if preferences.exists() else '')
    cmd = desktop_command(ctx, out, windowed=True, shared_settings=True, preferences=out / 'settings.txt',
                          extra=['-nofox', f'-liveport={args.port}',
                                 '-ini:Engine:[HTTPServer.Listeners]:DefaultBindAddress=localhost',
                                 *(['-rider=CairoBotw'] if args.rider == 'CairoBotw' else [])])
p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
guards = ExitStack(); monitor = None


def run(code, timeout=60):
    if monitor is not None and monitor.poll() is not None and p.poll() is None:
        raise RuntimeError('Memory monitor exited before the game')
    r = live.request('/python', code, timeout=timeout)
    if not r.get('ok'): raise RuntimeError(r)
    return r.get('output', '')


def wait(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if p.poll() is not None: raise RuntimeError('Game exited ' + str(p.returncode))
        time.sleep(.1)


def console(command): run(f"unreal.SystemLibrary.execute_console_command(unreal.LiveLibrary.game_world(), {command!r})")


def view(code, what):
    """The close view is for people to look at; the checks do not need it."""
    try: run(code)
    except RuntimeError as e: print(what + ' failed:', str(e)[:300], flush=True)


def shot(name): run(f"live.shot({str(out / f'{name}.png')!r})")


def to_start():
    """Cairo on foot, standing still on the flat START, the park's view: the fixture every check starts from. START is
    above the flat, so he falls and settles first; then refuses unless he stands on it (capsule bottom within 5 cm of
    the floor traced under him, at the flat's height within 10 cm) and it is level (within 1°)."""
    x, y, z = START
    run(f'''
P = unreal.LiveLibrary.player(); C = P.get_component_by_class(unreal.CapsuleComponent); half = C.get_scaled_capsule_half_height()
P.get_movement_component().stop_movement_immediately()
P.set_actor_location(unreal.Vector({x * 100!r}, {-y * 100!r}, {z * 100!r}) + unreal.Vector(0, 0, half + 3), False, True)
unreal.YorimichiLive.drive(unreal.Vector2D(), 0)
''')
    wait(2.)
    fixture = json.loads(run(r'''
import json, math
W = unreal.LiveLibrary.game_world(); P = unreal.LiveLibrary.player()
C = P.get_component_by_class(unreal.CapsuleComponent); half = C.get_scaled_capsule_half_height()
a = C.get_world_location()
h = unreal.SystemLibrary.line_trace_single(W, a, a - unreal.Vector(0, 0, half + 400), unreal.TraceTypeQuery.ECC_VISIBILITY, False, [P], unreal.DrawDebugTrace.NONE, True)
t = None if h is None else h.to_tuple()
print(json.dumps(None if t is None else dict(floor=round(t[5].z, 2), gap=round(a.z - half - t[5].z, 2),
                                             tilt=round(math.degrees(math.acos(max(-1., min(1., t[7].z)))), 2))))
''').strip().splitlines()[-1])
    if (fixture is None or abs(fixture['gap']) > 5 or abs(fixture['floor'] - FLAT_Z * 100) > 10 or fixture['tilt'] > 1):
        raise RuntimeError(f'Cairo is not standing on the level START flat: {fixture}')
    tilt = fixture['tilt']
    view(HOME, 'camera home')
    return tilt


def stand():
    """Cairo on foot on the flat: each ankle and toe bone's height over the floor traced under it, the capsule's bottom
    over the floor and the mesh's offset from that bottom (cm), so soles sunk into the ground show which one is off.
    Also each foot's toe drop (ankle minus toe height, cm), to set against the animation's, and the ground normal the
    foot contact node samples under each ankle (its trace, from 45 cm over the capsule's bottom), as degrees from up."""
    to_start()
    measured = run(r'''
import json, math
M = P.get_editor_property('mesh')
def floor(p):
    h = unreal.SystemLibrary.line_trace_single(W, p + unreal.Vector(0, 0, 60), p - unreal.Vector(0, 0, 60), unreal.TraceTypeQuery.ECC_VISIBILITY, True, [P], unreal.DrawDebugTrace.NONE, True)
    return None if h is None else h.to_tuple()[5].z
bottom = C.get_world_location() - unreal.Vector(0, 0, half)
bones = {}
for b in ('foot_L', 'toe_L', 'foot_R', 'toe_R'):
    p = M.get_socket_location(b); f = floor(p)
    bones[b] = None if f is None else round(p.z - f, 2)
f = floor(bottom)
drop = {s: round(M.get_socket_location('foot_' + s).z - M.get_socket_location('toe_' + s).z, 2) for s in 'LR'}
ground = {}
for s in 'LR':
    a = M.get_socket_location('foot_' + s); a.z = bottom.z + 45
    h = unreal.SystemLibrary.line_trace_single(W, a, a - unreal.Vector(0, 0, 95), unreal.TraceTypeQuery.ECC_VISIBILITY, False, [P], unreal.DrawDebugTrace.NONE, True)
    n = None if h is None else h.to_tuple()[7]
    ground[s] = None if n is None else dict(normal=[round(n.x, 4), round(n.y, 4), round(n.z, 4)], tilt_deg=round(math.degrees(math.acos(max(-1., min(1., n.z)))), 2))
print(json.dumps(dict(bones=bones, capsule_bottom=None if f is None else round(bottom.z - f, 2),
                      mesh_from_bottom=round(M.get_world_location().z - bottom.z, 2), half=round(half, 2), toe_drop=drop, ground=ground)))
''')
    result = json.loads(measured.strip().splitlines()[-1]); shot('on_foot')
    view(FOOT_CLOSE, 'on-foot close view'); wait(.3); shot('on_foot_side'); view(HOME, 'camera home')
    return result


def place(at, physical):
    """On the board at rest at `at`, recording from here on."""
    x, y, z = at
    run(f'''
unreal.SystemLibrary.execute_console_command(unreal.LiveLibrary.game_world(), 'skate.RidePhysical {physical}')
live.stop('feet_rec'); live.stop('skate_script')
at = live.L.ground_at(unreal.Vector({x * 100!r}, {-y * 100!r}, {z * 100!r}))
assert live.L.skate_place(at, 0.0), 'skate_place refused'
''')
    wait(1.2); run(RECORDER)


F = lambda pattern, s, default=None: (m.group(1) if (m := re.search(pattern, s)) else default)


def frames():
    rows = json.loads(run("import json; live.stop('feet_rec'); print(json.dumps(live.FEET))").strip().splitlines()[-1])
    return [dict(dt=dt, retail=F(r'retail=(\w+)', s, ''), phys=F(r'phys=(\w+)', s, ''), manual=F(r'manual=(\d)', s) == '1',
                 push=F(r' push=(\d)', s) == '1' or F(r' ps=(\d)', s, '0') != '0', bail=F(r' bail=(\d)', s, '0') != '0',
                 speed=float(F(r' speed=(-?\d+)', s, 0)), bails=int(F(r'bails=(\d+)', s, 0)), surface=F(r'surface=(\w+)', s, ''),
                 deck=[float(v) for v in F(r'deck=(-?[\d.]+,-?[\d.]+,-?[\d.]+)', s, '0,0,0').split(',')],
                 height=[b[0] for b in bones], along=[b[1] for b in bones]) for dt, s, bones in rows]


def mean(rows, key):
    return [round(sum(c) / len(c), 1) for c in zip(*[r[key] for r in rows])] if rows else None


def ollie(name, physical):
    place(LANE, physical); view(CLOSE, 'close view')
    run("live.skate_script([(.5, {'push': True}), (.05, {})])"); wait(1.1)
    if name.endswith('0'): shot(name + '_rolling')
    run("live.flick('ollie')"); wait(.45); shot(name + '_air'); wait(1.4)
    view(HOME, 'camera home')
    return frames()


def manual(name, physical):
    # The right stick half back, nose up on the back wheels.
    place(LANE, physical); view(CLOSE, 'close view')
    run("live.skate_script([(.5, {'push': True}), (.5, {}), (1.8, {'right': (0, -.5)}), (.1, {})])"); wait(1.9)
    shot(name); wait(1.2)
    view(HOME, 'camera home')
    return frames()


def feet(name, physical):
    """Each phase's mean ankle and toe heights over the deck and offsets along it. Rolling is the coast before the
    first ollie, not pushing (the pushing foot is off the deck)."""
    trials = [('ollie', ollie(f'{name}_ollie{k}', physical)) for k in range(OLLIES)] + [('manual', manual(f'{name}_manual', physical))]
    (out / f'rows_{name}.json').write_text(json.dumps(trials) + '\n')
    phases = {'rolling': [], 'air': [], 'manual': []}
    for kind, rows in trials:
        first_air = next((i for i, r in enumerate(rows) if 'Air' in r['retail']), len(rows))
        clean = lambda r: not r['bail'] and r['phys'] not in ('Bail', 'GetUp')
        phases['rolling'] += [r for r in rows[:first_air] if clean(r) and r['retail'] in ('PhysicsGround', 'GroundAnimation') and not r['push']
                              and not r['manual'] and r['phys'] in ('Riding', '') and r['speed'] > 50]
        if kind == 'ollie': phases['air'] += [r for r in rows if clean(r) and 'Air' in r['retail']]
        else: phases['manual'] += [r for r in rows if clean(r) and r['manual']]
    dts = sorted(r['dt'] for _, rows in trials for r in rows)
    return dict({k: dict(frames=len(v), height=mean(v, 'height'), along=mean(v, 'along')) for k, v in phases.items()},
                bails=sum(rows[-1]['bails'] - rows[0]['bails'] for _, rows in trials if rows),
                frame_ms=dict(mean=round(1000 * sum(dts) / max(1, len(dts)), 1), p50=round(1000 * dts[(len(dts) - 1) // 2], 1) if dts else None,
                              p95=round(1000 * dts[int(.95 * (len(dts) - 1))], 1) if dts else None))


def back_on_lane(rows):
    """The frames up to the board's return across the lane from the quarter: a board that stalls short of the lip
    rolls back fakie, and a push still held then carries it backwards up the landing and over the gap, which is not
    the quarter's landing."""
    up = next((k for k, r in enumerate(rows) if r['deck'][0] > (ox + QUARTER_X) * 100), None)
    back = next((k for k in range(up, len(rows)) if rows[k]['deck'][0] < (LANE[0] - 2) * 100), None) if up is not None else None
    return rows[:back] if back else rows


def airs_out(name, physical, push, at=LANE, window=None, launch=None):
    """Pushes for `push` seconds (or is launched at `launch` m/s along +x) and lets the board run, to air out of a
    transition and land back: each air of 10 frames or more, and whether the board then rolled on for half a second."""
    place(at, physical)
    if launch: run(f'assert unreal.YorimichiLive.skate_launch(unreal.Vector({launch * 100!r}, 0, 0))')
    else: run(f"live.skate_script([({push}, {{'push': True}}), (.05, {{}})])")
    wait(push + 9.); rows = frames(); (out / f'rows_{name}.json').write_text(json.dumps(rows) + '\n')
    rows = window(rows) if window else rows
    runs = [(air, len(list(g))) for air, g in itertools.groupby('Air' in r['retail'] for r in rows)]
    airs = [dict(frames=n, landed=k + 1 < len(runs) and runs[k + 1][1] >= 30) for k, (air, n) in enumerate(runs) if air and n >= 10]
    return dict(airs=airs, bails=rows[-1]['bails'] - rows[0]['bails'] if rows else None,
                top_speed_mps=round(max((r['speed'] for r in rows), default=0) / 100, 2),
                # The speed as the deck reaches the quarter's transition: what the quarter actually gets.
                entry_speed_mps=next((round(r['speed'] / 100, 2) for r in rows if r['deck'][0] > (ox + QUARTER_X) * 100), None))


try:
    monitor = guards.enter_context(attach_memory_guard(p.pid, out / 'memory-health.json', duration=800))
    deadline = time.monotonic() + 300
    last_notice = 0.
    while time.monotonic() < deadline:
        if p.poll() is not None: raise RuntimeError('Game exited ' + str(p.returncode))
        for path in (out / 'game.log', out / 'console.log'):
            error = bridge_bind_error(path.read_text(errors='replace'), args.port) if path.exists() else None
            if error:
                raise RuntimeError('Owned bridge failed to bind; ending this game: ' + error)
        if time.monotonic()-last_notice >= 20:
            game_log = out / 'game.log'
            print('Waiting for owned bridge; game log bytes', game_log.stat().st_size if game_log.exists() else 0, flush=True); last_notice=time.monotonic()
        # The bridge answers on the game thread. A cold shader/asset hitch can exceed one second;
        # allow a bounded request to finish instead of accumulating abandoned requests during startup.
        try: live.request('/state', timeout=min(10, max(.1, deadline - time.monotonic()))); break
        except OSError: time.sleep(1)
    else: raise RuntimeError('Bridge startup timed out')
    run('import os,unreal; assert os.getpid() == '+str(p.pid)+'; assert os.path.realpath(unreal.Paths.project_dir()) == '+repr(str(ctx.uproject.parent.resolve())))
    owns_bridge = True
    # Settle where the checks run, not at the spawn: the forest road's view is a different, heavier frame. The phases'
    # own frame timing still has to meet its requested rate.
    for attempt in range(6):   # the park's collision may still be streaming in just after startup
        try: print('START fixture level, tilt', to_start(), 'deg', flush=True); break
        except RuntimeError as e:
            if attempt == 5: raise
            print('START fixture not ready:', str(e)[:200], flush=True); time.sleep(5)
    steady, start = None, time.monotonic(); last_notice = 0.
    while time.monotonic() - start < 240:
        try: fps = live.request('/state', timeout=min(10, max(.1, 240 - (time.monotonic() - start)))).get('fps', 0)
        except OSError:
            fps = 0
        if time.monotonic()-last_notice >= 20:
            print(f'Owned game settling: observed {fps:.1f} FPS, elapsed {time.monotonic()-start:.0f}s; waiting for three seconds >={args.settle_fps:g} FPS', flush=True); last_notice=time.monotonic()
        steady = (steady or time.monotonic()) if fps >= args.settle_fps else None
        if steady and time.monotonic() - steady > 3: break
        time.sleep(.5)
    else: raise RuntimeError(f'Owned game did not settle at >={args.settle_fps:g} FPS within 240s')
    print('bridge up and steady', flush=True)
    results = {}
    results['on_foot'] = stand(); print('on_foot', json.dumps(results['on_foot']), flush=True)
    for fps in (60, 30):
        console(f't.MaxFPS {fps}'); wait(.5)
        for name, physical in ((f'physical{fps}', 1), (f'animated{fps}', 0)):
            results[name] = feet(name, physical); print(name, json.dumps(results[name]), flush=True)
    console('t.MaxFPS 60')
    for push in QUARTER_PUSHES:
        results[f'quarter_{push}'] = airs_out(f'quarter_{push}', 1, push, window=back_on_lane); print(f'quarter_{push}', json.dumps(results[f'quarter_{push}']), flush=True)
    for v in QUARTER_LAUNCHES:
        name = f'quarter_launch_{v:g}mps'
        results[name] = airs_out(name, 1, 0., launch=v, window=back_on_lane); print(name, json.dumps(results[name]), flush=True)
    results['mega_drop_in'] = airs_out('mega_drop_in', 1, 1., DROP_IN); print('mega_drop_in', json.dumps(results['mega_drop_in']), flush=True)

    for fps in (60, 30):
        phys, anim = results[f'physical{fps}'], results[f'animated{fps}']
        seen = lambda r: {k: r[k]['frames'] for k in ('rolling', 'air', 'manual')} | {k: r[k] for k in ('bails', 'frame_ms')}
        # The lag this guards against is speed x frame time, so each phase must really run at its rate. The median frame
        # within 5% of the requested one and the 95th percentile within 15%; a reset's clamped 125 ms frame moves neither.
        # Physical and animated at the same rate, so they compare like for like.
        target = 1000 / fps; timing = {'physical': phys['frame_ms'], 'animated': anim['frame_ms']}
        record(f'frame_timing_{fps}', all(t['p50'] is not None and abs(t['p50'] - target) <= .05 * target and t['p95'] <= 1.15 * target
                                          for t in timing.values()) and abs(timing['physical']['p50'] - timing['animated']['p50']) <= .05 * target,
               json.dumps(dict(target_ms=round(target, 1)) | timing))
        record(f'rides_clean_{fps}', all(r['bails'] == 0 and min(r[k]['frames'] for k in ('rolling', 'air', 'manual')) >= 20 for r in (phys, anim)),
               json.dumps({'physical': seen(phys), 'animated': seen(anim)}))
        for phase in ('rolling', 'air', 'manual'):
            a, b = phys[phase], anim[phase]
            if not a['frames'] or not b['frames']:
                record(f'physical_feet_track_animated_{phase}_{fps}', False, f'no {phase} frames'); continue
            off = {k: [round(x - y, 1) for x, y in zip(a[k], b[k])] for k in ('height', 'along')}
            record(f'physical_feet_track_animated_{phase}_{fps}', max(abs(v) for d in off.values() for v in d) <= TRACKING,
                   f'physical minus animated (ankle L, toe L, ankle R, toe R), cm: up {off["height"]}, along {off["along"]}; '
                   f'physical up {a["height"]}, along {a["along"]}')
    # Every air lands and rolls on; the last may still be in the air when the recording ends. A push too short to clear
    # the quarter's lip rolls back down the transition without bailing; one of them airs out.
    for name in [f'quarter_{push}' for push in QUARTER_PUSHES] + ['mega_drop_in']:
        r = results[name]
        record(f'{name}_lands', r['bails'] == 0 and (r['airs'] or name.startswith('quarter')) and all(a['landed'] for a in r['airs'][:-1])
               and (not r['airs'] or r['airs'][0]['landed']), json.dumps(r))
    # Regression trials, apart from ordinary pushing: launched at drop-in speed, the board must air out and land back.
    for v in QUARTER_LAUNCHES:
        name = f'quarter_launch_{v:g}mps'; r = results[name]
        record(f'{name}_airs_and_lands', r['bails'] == 0 and bool(r['airs']) and all(a['landed'] for a in r['airs'][:-1])
               and r['airs'][0]['landed'], json.dumps(r))
    record('quarter_airs_out', any(results[f'quarter_{push}']['airs'] for push in QUARTER_PUSHES),
           json.dumps({push: results[f'quarter_{push}']['airs'] for push in QUARTER_PUSHES}))
    # The toe bones sit inside the shoes, above their soles: one at or under the floor means the shoe is sunk into it.
    toes = [results['on_foot']['bones'].get(b) for b in ('toe_L', 'toe_R')]
    record('on_foot_toes_above_floor', all(t is not None and t >= 1.0 for t in toes), json.dumps(results['on_foot']))
    # The toe bone sits 2.1-2.5 cm over Cairo's sole, so its height alone cannot tell a level shoe from one tipped into
    # the floor. His standing idles keep the rest pose's toe drop (ankle minus toe height); the game should too, unless
    # the ground under the foot is sloped (its normal is recorded beside it).
    rest = json.loads((yori.OUT / 'cairo' / 'unreal_validation.json').read_text())['rest_bones_cm']
    authored = {s: rest[f'foot_{s}'][2] - rest[f'toe_{s}'][2] for s in 'LR'}
    drops = results['on_foot'].get('toe_drop') or {}
    record('on_foot_toe_drop_as_animated', all(drops.get(s) is not None and abs(drops[s] - authored[s]) <= .5 for s in 'LR'),
           json.dumps(dict(game=drops, authored={s: round(v, 2) for s, v in authored.items()}, ground=results['on_foot'].get('ground'))))
    record('on_foot_capsule_on_floor', results['on_foot']['capsule_bottom'] is not None and abs(results['on_foot']['capsule_bottom']) <= 2.5,
           json.dumps(results['on_foot']))
    log.flush(); late = [l.strip() for l in (out / 'game.log').read_text(errors='replace').splitlines() if LATE_TICK in l]
    record('physics_control_before_physics', not late, late[0][-300:] if late else 'no late-tick warning')
    summary = dict(passed=all(c['ok'] for c in checks.values()), settle_fps=args.settle_fps, checks=checks, runs=results)
    (out / 'checks.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('PASSED' if summary['passed'] else 'FAILED', sum(c['ok'] for c in checks.values()), '/', len(checks), flush=True)
    sys.exit(0 if summary['passed'] else 1)
finally:
    if not owns_bridge and p.poll() is None:
        reap(p)
    try:
        if p.poll() is None and owns_bridge: live.request('/python', "unreal.SystemLibrary.quit_game(unreal.LiveLibrary.game_world(),None,unreal.QuitPreference.QUIT,False)", timeout=5)
    except Exception: pass
    try: p.wait(timeout=20)
    except subprocess.TimeoutExpired: reap(p)
    found = subprocess.run(['pgrep', '-f', f'Turnkey.*{ctx.uproject}|{ctx.uproject}.*Turnkey'], capture_output=True, text=True).stdout.split()
    if found:
        print('ending this checkout\'s leftover Turnkey:', ' '.join(found), flush=True)
        subprocess.run(['kill', '-TERM', *found], check=False)
    guards.close(); log.close()
