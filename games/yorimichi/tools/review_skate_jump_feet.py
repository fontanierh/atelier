"""Ollie in the real game and measure how far Cairo's feet stand off the deck, on the ground and in the air.

    uv run python games/yorimichi/tools/review_skate_jump_feet.py [--port 8871]

Run after unreal.compile. Under the render guard it launches the island, stands Cairo on foot on the mini-mega's flat
and measures his soles and capsule over the floor, then puts the rider on the board there, pushes and ollies a few
times, once with the physical rider (skate.RidePhysical 1, the default) and once animated only (0), and last drops in
on the mini-mega with no input, over its kicker into the landing. Every frame it keeps the skate state and, in the
deck's own frame, the height of each
foot's ankle and toe bones over the deck's top, so a foot that floats off the board in the air shows as a gap the
ground does not have. Writes build/yorimichi/skate-jump-feet/review/{checks.json, rows_*.json, *.png, game.log}. The
worker owns and quits only the game process it launches.
"""
from pathlib import Path
from contextlib import ExitStack
import argparse, json, re, subprocess, sys, time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world' / 'regions'))
import yori
from mega.layout import ORIGIN
from atelier.build import Context
from atelier.safety import guarded
from atelier.safety.guard import attach as attach_memory_guard, reap
from atelier import live

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
parser.add_argument('--port', type=int, default=8871)
args = parser.parse_args()
live.URL = f'http://127.0.0.1:{args.port}'
ctx = Context('yorimichi'); out = yori.OUT / 'skate-jump-feet' / 'review'; out.mkdir(parents=True, exist_ok=True)

if not args.worker:
    sys.exit(guarded.run([sys.executable, str(Path(__file__).resolve()), '--worker'] + sys.argv[1:], out / 'guard', timeout=900,
                         purpose='skate jump feet review', kind='game'))

ox, oy, oz = ORIGIN
START = (ox + 30, oy - 2, oz + 2)   # the mini-mega's flat, riding toward +x
OLLIES = 3
# The recorder: the skate state, then per bone (ankle and toe, left then right) its height over the deck's top in the
# deck's frame (cm) and its offset along and across the deck.
RECORDER = r'''
import json
P = live.player(); M = P.get_editor_property('mesh')
D = next(c for c in P.get_components_by_class(unreal.StaticMeshComponent) if c.get_name() == 'SkateDeck')
_box = D.get_editor_property('static_mesh').get_bounding_box()
live.DECK_TOP = _box.max.z
live.FEET = []
def _feet(dt):
    T = D.get_world_transform()
    bones = []
    for b in ('foot_L', 'toe_L', 'foot_R', 'toe_R'):
        p = T.inverse_transform_location(M.get_socket_location(b))
        bones.append((round(p.z - live.DECK_TOP, 2), round(p.x, 1), round(p.y, 1)))
    live.FEET.append((dt, live.L.skate_state(), bones))
live.behave('feet_rec', _feet)
'''


def record(name, ok, note):
    checks[name] = dict(ok=bool(ok), note=note); print(('PASS ' if ok else 'FAIL ') + name + ': ' + note, flush=True)


checks = {}
log = (out / 'game.log').open('w')
cmd = [str(ctx.unreal_app), str(ctx.uproject), '-game', '-windowed', '-resx=1280', '-resy=720', '-nosplash', '-stdout', '-nofox',
       f'-liveport={args.port}', '-ini:Engine:[HTTPServer.Listeners]:DefaultBindAddress=localhost',
       '-ExecCmds=t.MaxFPS 60,r.RHISetGPUCaptureOptions 0,DisableAllScreenMessages']
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
        time.sleep(.25)


def stand():
    """Cairo on foot on the flat: each ankle and toe bone's height over the floor traced under it, the capsule's bottom
    over the floor and the mesh's offset from that bottom (cm), so soles sunk into the ground show which one is off."""
    x, y, z = START
    run(f'''
W = unreal.LiveLibrary.game_world(); P = unreal.LiveLibrary.player(); M = P.get_editor_property('mesh')
C = P.get_component_by_class(unreal.CapsuleComponent); half = C.get_scaled_capsule_half_height()
P.get_movement_component().stop_movement_immediately()
P.set_actor_location(unreal.Vector({x * 100!r}, {-y * 100!r}, {z * 100!r}) + unreal.Vector(0, 0, half + 3), False, True)
unreal.YorimichiLive.drive(unreal.Vector2D(), 0)
''')
    wait(2.)
    measured = run(r'''
import json
def floor(p):
    h = unreal.SystemLibrary.line_trace_single(W, p + unreal.Vector(0, 0, 60), p - unreal.Vector(0, 0, 60), unreal.TraceTypeQuery.ECC_VISIBILITY, True, [P], unreal.DrawDebugTrace.NONE, True)
    return None if h is None else h.to_tuple()[5].z
bottom = C.get_world_location() - unreal.Vector(0, 0, half)
bones = {}
for b in ('foot_L', 'toe_L', 'foot_R', 'toe_R'):
    p = M.get_socket_location(b); f = floor(p)
    bones[b] = None if f is None else round(p.z - f, 2)
f = floor(bottom)
print(json.dumps(dict(bones=bones, capsule_bottom=None if f is None else round(bottom.z - f, 2),
                      mesh_from_bottom=round(M.get_world_location().z - bottom.z, 2), half=round(half, 2))))
''')
    result = json.loads(measured.strip().splitlines()[-1]); run(f"live.shot({str(out / 'on_foot.png')!r})")
    return result


def ride(name, physical, at=None, ollies=OLLIES, coast=0.):
    x, y, z = at or START
    run(f'''
unreal.SystemLibrary.execute_console_command(unreal.LiveLibrary.game_world(), 'skate.RidePhysical {physical}')
at = live.L.ground_at(unreal.Vector({x * 100!r}, {-y * 100!r}, {z * 100!r}))
assert live.L.skate_place(at, 0.0), 'skate_place refused'
{RECORDER}
''')
    wait(1.)
    if coast:
        wait(.6); run(f"live.shot({str(out / f'{name}_air.png')!r})"); wait(coast)
    else:
        run("live.skate_script([(1.6, {'push': True}), (.2, {})])"); wait(2.)
    for k in range(ollies):
        run("live.flick('ollie')"); wait(.55)
        run(f"live.shot({str(out / f'{name}_air{k}.png')!r})"); wait(1.6)
        run("live.skate_script([(.6, {'push': True}), (.1, {})])"); wait(.9)
    rows = json.loads(run("import json; live.stop('feet_rec'); print(json.dumps(live.FEET))").strip().splitlines()[-1])
    (out / f'rows_{name}.json').write_text(json.dumps(rows, indent=1) + '\n')
    phases = {}
    for _, s, bones in rows:
        m = re.search(r'retail=(\w+)', s); bail = re.search(r'bail=(\d)', s)
        if not m or (bail and bail.group(1) != '0'): continue
        kind = 'air' if 'Air' in m.group(1) else 'ground' if m.group(1) in ('PhysicsGround', 'GroundAnimation') else None
        if kind: phases.setdefault(kind, []).append([b[0] for b in bones])
    summary = {}
    for kind, values in phases.items():
        cols = list(zip(*values))
        summary[kind] = dict(frames=len(values), mean=[round(sum(c) / len(c), 1) for c in cols], max=[round(max(c), 1) for c in cols],
                             min=[round(min(c), 1) for c in cols])
    counts = [int(m.group(1)) for _, s, _ in rows if (m := re.search(r'bails=(\d+)', s))]
    summary['bails'] = counts[-1] - counts[0] if counts else None
    return summary


try:
    monitor = guards.enter_context(attach_memory_guard(p.pid, out / 'memory-health.json', duration=800))
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        if p.poll() is not None: raise RuntimeError('Game exited ' + str(p.returncode))
        try: live.request('/state', timeout=1); break
        except OSError: time.sleep(1)
    else: raise RuntimeError('Bridge startup timed out')
    steady, start = None, time.monotonic()
    while time.monotonic() - start < 240:
        fps = live.request('/state').get('fps', 0)
        steady = (steady or time.monotonic()) if fps >= 25 else None
        if steady and time.monotonic() - steady > 3: break
        time.sleep(.5)
    print('bridge up and steady', flush=True)
    results = {}
    results['on_foot'] = stand(); print('on_foot', json.dumps(results['on_foot']), flush=True)
    for name, physical in (('physical', 1), ('animated', 0)):
        results[name] = ride(name, physical); print(name, json.dumps(results[name]), flush=True)
    # The mini-mega's drop-in, over its kicker and the gap: a big air landed into the transition, no input.
    results['mega_drop_in'] = ride('mega_drop_in', 1, (ox - 2, oy, oz + 12), 0, 6.); print('mega_drop_in', json.dumps(results['mega_drop_in']), flush=True)
    # Ankle and toe heights over the deck in the air may rise above the ground's by no more than this (cm).
    record('mega_drop_in_lands', results['mega_drop_in']['bails'] == 0, json.dumps(results['mega_drop_in']))
    record('on_foot_capsule_on_floor', results['on_foot']['capsule_bottom'] is not None and abs(results['on_foot']['capsule_bottom']) <= 2.5,
           json.dumps(results['on_foot']))
    for name, r in results.items():
        if name in ('mega_drop_in', 'on_foot'): continue
        if 'air' not in r or 'ground' not in r:
            record(f'{name}_jumped', False, json.dumps(r)); continue
        lift = [round(a - g, 1) for a, g in zip(r['air']['mean'], r['ground']['mean'])]
        record(f'{name}_feet_on_deck_in_air', max(lift) <= 2.0, f'air minus ground (ankle L, toe L, ankle R, toe R): {lift} cm; {json.dumps(r)}')
    summary = dict(passed=all(c['ok'] for c in checks.values()), checks=checks, runs=results)
    (out / 'checks.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('PASSED' if summary['passed'] else 'FAILED', sum(c['ok'] for c in checks.values()), '/', len(checks), flush=True)
finally:
    try:
        if p.poll() is None: live.request('/python', "unreal.SystemLibrary.quit_game(unreal.LiveLibrary.game_world(),None,unreal.QuitPreference.QUIT,False)", timeout=5)
    except Exception: pass
    try: p.wait(timeout=20)
    except subprocess.TimeoutExpired: reap(p)
    found = subprocess.run(['pgrep', '-f', f'Turnkey.*{ctx.uproject}|{ctx.uproject}.*Turnkey'], capture_output=True, text=True).stdout.split()
    if found:
        print('ending this checkout\'s leftover Turnkey:', ' '.join(found), flush=True)
        subprocess.run(['kill', '-TERM', *found], check=False)
    guards.close(); log.close()
