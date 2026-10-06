"""Open the Skate feel menu in the real game, set skate_* values live and check the board feels them (docs/SKATE.md).

    uv run python games/yorimichi/tools/review_skate_feel.py [--port 8871]

Run after unreal.compile and data.stage. Under the render guard it launches the island, captures the settings menu and
its Skate feel page, then puts the rider on the skate pier and ollies on flat deck: stock (Normal), Normal with a custom
skate_gravity 0.7 saved (a preset ignores it), and Custom with it (set live through the preferences, as the menu does):
the jump height stays and the air time stretches. Writes build/yorimichi/skate-feel/review/{checks.json, menu_*.png, settings.txt, game.log}. The worker owns
and quits only the game process it launches.
"""
from pathlib import Path
from contextlib import ExitStack
import argparse, json, math, re, subprocess, sys, time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
import yori
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
ctx = Context('yorimichi'); out = yori.OUT / 'skate-feel' / 'review'; out.mkdir(parents=True, exist_ok=True)

if not args.worker:
    sys.exit(guarded.run([sys.executable, str(Path(__file__).resolve()), '--worker'] + sys.argv[1:], out / 'guard', timeout=900,
                         purpose='skate feel review', kind='game'))

# One ollie at speed on the pier, every frame's skate state kept in live.FEEL until done.
OLLIE = r'''
live.skate_park()
live.FEEL = []
live.behave('feel_rec', lambda dt: live.FEEL.append((dt, live.L.skate_state())))
live.skate_script([(1.2, {'push': True}), (.6, {})] + [(.18, {'right': live.FLICKS['ollie'][0]}), (.03, {'right': live.FLICKS['ollie'][1]}), (2.4, {})])
'''
checks = {}


def record(name, ok, note):
    checks[name] = dict(ok=bool(ok), note=note); print(('PASS ' if ok else 'FAIL ') + name + ': ' + note, flush=True)


log = (out / 'game.log').open('w')
(out / 'settings.txt').unlink(missing_ok=True)
cmd = [str(ctx.unreal_app), str(ctx.uproject), '-game', '-windowed', '-resx=1280', '-resy=720', '-nosplash', '-stdout', '-nofox',
       f'-liveport={args.port}', '-ini:Engine:[HTTPServer.Listeners]:DefaultBindAddress=localhost',
       '-preferencesfile=' + str(out / 'settings.txt'), '-ExecCmds=t.MaxFPS 60,r.RHISetGPUCaptureOptions 0,DisableAllScreenMessages']
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


def ollie(label):
    """Ride the pier's ollie and return its peak height above the take-off and its air time from the rows."""
    run(OLLIE); wait(5.5)
    rows = json.loads(run("import json; live.stop('feel_rec'); print(json.dumps(live.FEEL))").strip().splitlines()[-1])
    (out / f'rows_{label}.json').write_text(json.dumps(rows, indent=1) + '\n')
    zs = [float(re.search(r'pos=\([-\d.]+,[-\d.]+,([-\d.]+)\)', s).group(1)) for _, s in rows]
    modes = [re.search(r' mode=(\d+)', s).group(1) for _, s in rows]
    ground_mode = modes[len(modes) // 4]
    base = sorted(zs[:len(zs) // 3])[len(zs) // 6]
    air = sum(dt for (dt, _), m in zip(rows, modes) if m != ground_mode)
    return dict(height_cm=max(zs) - base, airtime_s=air, bails=re.search(r'bails=(\d+)', rows[-1][1]).group(1), frames=len(rows))


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

    # The menu: its main page with the Skate feel button, then the Skate feel page itself.
    run("live.press('menu')"); wait(1.5); run(f"live.shot({str(out / 'menu_main.png')!r})"); wait(1)
    run("live.press('skate_feel')"); wait(1.5); run(f"live.shot({str(out / 'menu_skate.png')!r})"); wait(1)
    run("live.press('menu')"); wait(1)
    record('menu_shots', (out / 'menu_main.png').exists() and (out / 'menu_skate.png').exists(), 'menu_main.png, menu_skate.png (Normal)')

    # Live preferences reach the board: set, then saved to settings.txt.
    stock = ollie('stock')
    # A preset ignores the custom values; Custom applies them.
    ok = run("print(live.preference('skate_gravity', .7), live.preference('skate_rail_magnetism', 2))").strip()
    preset = ollie('normal_with_custom_values')
    ok += ' ' + run("print(live.preference('skate_mode', 3))").strip()
    run(f"live.press('skate_feel')"); wait(1.5); run(f"live.shot({str(out / 'menu_custom.png')!r})"); wait(1); run("live.press('menu')"); wait(1)
    floaty = ollie('custom_gravity_0.7')
    saved = (out / 'settings.txt').read_text() if (out / 'settings.txt').exists() else ''
    record('preferences_set', ok == 'True True True' and 'skate_gravity' in saved, f'set {ok}; saved={"skate_gravity" in saved}')
    preset_ratio = preset['airtime_s'] / max(stock['airtime_s'], 1e-3)
    record('preset_ignores_custom', abs(preset_ratio - 1) < .05, f'Normal with custom gravity 0.7 saved: air time x{preset_ratio:.2f}')
    record('stock_ollie', stock['height_cm'] > 15 and stock['bails'] == '0', json.dumps(stock))
    ratio = floaty['airtime_s'] / max(stock['airtime_s'], 1e-3)
    record('gravity_keeps_height', abs(floaty['height_cm'] - stock['height_cm']) < .12 * stock['height_cm'] + 4, f"{floaty['height_cm']:.0f} vs {stock['height_cm']:.0f} cm")
    record('gravity_stretches_air', 1.08 < ratio < 1.32, f'air time x{ratio:.2f} (1/sqrt(0.7) = {1 / math.sqrt(.7):.2f})')
    run("live.preference('skate_gravity', 1); live.preference('skate_rail_magnetism', 1); live.preference('skate_mode', 1)")
    refused = [l for l in (out / 'game.log').read_text(errors='replace').splitlines() if 'skate feel' in l.lower() and 'refus' in l.lower()]
    record('no_refusals', not refused, refused[0] if refused else 'none')
    summary = dict(passed=all(c['ok'] for c in checks.values()), checks=checks, stock=stock, normal_with_custom=preset, custom_gravity_0_7=floaty)
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
