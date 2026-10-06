"""Ride the island's ground in the real game and check each kind rides as it should (docs/SKATE.md, "Ground").

    uv run python games/yorimichi/tools/review_skate_terrain.py [--port 8871]

Run after unreal.compile, unreal.world, unreal.mega and unreal.sounds. Under the render guard it launches the island
with skate.SurfaceDebug on and puts the rider on the board: dropping in on the mini-mega and riding its flat and landing
(plywood with seams), across the footbridge into the Mega Park both ways (from the footpath over planks with gaps and
the sill onto the road deck, and back), and along the mini-mega's trail (dirt) and the clearing beside it (grass). Each
run pushes, then coasts, and keeps every frame's skate state. Writes
build/yorimichi/skate-terrain/review/{checks.json, rows_*.json, *.png, surface-debug.txt, game.log}. The
worker owns and quits only the game process it launches.
"""
from pathlib import Path
from contextlib import ExitStack
import argparse, json, math, re, subprocess, sys, time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world' / 'regions'))
import yori
from mega.layout import ORIGIN
from zeppelin.layout import PARK_BRIDGE, DECK_EDGE
from atelier.build import Context
from atelier.safety import guarded
from atelier.safety.guard import attach as attach_memory_guard, reap
from atelier.safety.process import spawn_game
from atelier import live

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
parser.add_argument('--port', type=int, default=8871)
args = parser.parse_args()
live.URL = f'http://127.0.0.1:{args.port}'
ctx = Context('yorimichi'); out = yori.OUT / 'skate-terrain' / 'review'; out.mkdir(parents=True, exist_ok=True)

if not args.worker:
    sys.exit(guarded.run([sys.executable, str(Path(__file__).resolve()), '--worker'] + sys.argv[1:], out / 'guard', timeout=900,
                         purpose='skate terrain review', kind='game'))

ox, oy, oz = ORIGIN
(b0, by), (b1, _) = PARK_BRIDGE; deck = DECK_EDGE[0][2]
# name: island point (metres; the ground is found within 20 m above and 60 m below it), heading (degrees from +x, counter-clockwise as the island's map), seconds pushing, coasting
RUNS = {
    'mega_drop_in': ((ox - 2, oy, oz + 12), 0, 0, 6),
    'mega_flat': ((ox + 45, oy - 2, oz + 2), 0, 1.5, 3.5),
    'mega_landing_up': ((ox + 52, oy + 2, oz + 2), 180, 1.5, 3.5),
    'bridge_in': ((b0 - 2.5, by, deck + 1), 0, 2.5, 3.5),
    'bridge_out': ((b1 + 4, by, deck + 1), 180, 1.5, 3.5),
    'trail_dirt': ((154., 204., oz + 10), math.degrees(math.atan2(188 - 204, 135 - 154)), 1.5, 3.5),
    'clearing_grass': ((149., 191.5, oz + 10), math.degrees(math.atan2(188 - 204, 135 - 154)), 1.5, 3.5),
}
checks = {}


def record(name, ok, note):
    checks[name] = dict(ok=bool(ok), note=note); print(('PASS ' if ok else 'FAIL ') + name + ': ' + note, flush=True)


log = (out / 'game.log').open('w')
cmd = [str(ctx.unreal_app), str(ctx.uproject), '-game', '-windowed', '-resx=1280', '-resy=720', '-nosplash', '-stdout', '-nofox',
       f'-liveport={args.port}', '-ini:Engine:[HTTPServer.Listeners]:DefaultBindAddress=localhost',
       '-ExecCmds=t.MaxFPS 60,r.RHISetGPUCaptureOptions 0,DisableAllScreenMessages,skate.SurfaceDebug 1']
p = spawn_game(cmd, stdout=log, stderr=subprocess.STDOUT)
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


def ride(name):
    """Place the rider, push then coast, and summarise every frame's skate state."""
    (x, y, z), heading, push, coast = RUNS[name]
    run(f'''
at = live.L.ground_at(unreal.Vector({x * 100!r}, {-y * 100!r}, {z * 100!r}))
assert live.L.skate_place(at, {-heading!r}), 'skate_place refused'
live.FEEL = []
live.behave('terrain_rec', lambda dt: live.FEEL.append((dt, live.L.skate_state())))
live.skate_script([(.4, {{}}), ({push!r}, {{'push': True}}), ({coast!r}, {{}})])
''')
    wait(.8); run(f"live.shot({str(out / f'{name}.png')!r})")
    wait(.4 + push + coast)
    rows = json.loads(run("import json; live.stop('terrain_rec'); print(json.dumps(live.FEEL))").strip().splitlines()[-1])
    (out / f'rows_{name}.json').write_text(json.dumps(rows, indent=1) + '\n')
    pos = [tuple(float(v) for v in re.search(r'pos=\(([-\d.]+),([-\d.]+),([-\d.]+)\)', s).groups()) for _, s in rows]
    # Ground speed over a quarter of a second, leaving out a frame's jump of more than half a metre (a placement).
    steps = [(dt, math.dist(a[:2], b[:2]) / 100) for (dt, _), a, b in zip(rows[1:], pos, pos[1:])]
    steps = [(dt, d if d < .5 else 0.) for dt, d in steps]
    def smooth(k):
        t = d = 0.
        for dt, dd in reversed(steps[:k + 1]):
            t += dt; d += dd
            if t >= .25: break
        return d / max(t, 1e-3)
    surfaces = sorted({m.group(1) for _, s in rows if (m := re.search(r'surface=([A-Za-z]+)', s))})
    count = [int(re.search(r'bails=(\d+)', s).group(1)) for _, s in rows]
    bails = count[-1] - count[0]
    # Until the wheels first leave the ground (the mini-mega's kicker): a gap flown with no input can come up short.
    air = next((k for k, (_, s) in enumerate(rows) if 'surface=none' in s), len(rows) - 1)
    return dict(top_speed_mps=round(max(smooth(k) for k in range(len(steps))), 2), end_speed_mps=round(smooth(len(steps) - 1), 2),
                distance_m=round(sum(d for _, d in steps), 1), bails=bails, bails_before_air=count[air] - count[0], surfaces=surfaces,
                frames=len(rows))


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
    for name in RUNS:
        results[name] = ride(name); print(name, json.dumps(results[name]), flush=True)
    r = results
    record('mega_drop_in', r['mega_drop_in']['bails_before_air'] == 0 and r['mega_drop_in']['top_speed_mps'] > 6 and 'Wood' in r['mega_drop_in']['surfaces'],
           json.dumps(r['mega_drop_in']))
    # The footbridge's runs reach the far side: the road deck's concrete going in, the footpath going out.
    for name, far in (('mega_flat', 'Wood'), ('mega_landing_up', 'Wood'), ('bridge_in', 'Concrete'), ('bridge_out', 'Dirt')):
        ok = r[name]['bails'] == 0 and r[name]['distance_m'] > 6 and {'Wood', far} <= set(r[name]['surfaces'])
        record(name, ok, json.dumps(r[name]))
    record('dirt_drags', 'Dirt' in r['trail_dirt']['surfaces'] and r['trail_dirt']['distance_m'] < r['mega_flat']['distance_m'], json.dumps(r['trail_dirt']))
    record('grass_barely_rolls', 'Grass' in r['clearing_grass']['surfaces'] and r['clearing_grass']['distance_m'] < r['trail_dirt']['distance_m'],
           json.dumps(r['clearing_grass']))
    debug = [l for l in (out / 'game.log').read_text(errors='replace').splitlines() if 'surface' in l.lower() and 'skate' in l.lower()]
    (out / 'surface-debug.txt').write_text('\n'.join(debug) + '\n')
    record('surface_debug_logged', bool(debug), f'{len(debug)} lines in surface-debug.txt')
    summary = dict(passed=all(c['ok'] for c in checks.values()), checks=checks, runs=results)
    (out / 'checks.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('PASSED' if summary['passed'] else 'FAILED', sum(c['ok'] for c in checks.values()), '/', len(checks), flush=True)
    if not summary['passed']: sys.exit(1)
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
