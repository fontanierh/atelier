"""Capture Crater Park in the island from fixed cameras under the render guard (docs/CRATERPARK.md, "Review").

Run with project Python after the build. The cameras are the grounded target views: island metres (x east, y north,
z up) and a horizontal field of view, at 1536 x 1024. The worker checks both parks are placed, drops the rider at the
marked drop-in, takes every shot in the game's own look and quits only the game process it launched.
"""
from pathlib import Path
from contextlib import ExitStack
import argparse, json, subprocess, sys, time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world' / 'regions'))
import yori
from craterpark import placement
from atelier.build import Context
from atelier.safety import guarded
from atelier.safety.guard import attach as attach_memory_guard, reap
from atelier.safety.process import spawn_game
from atelier import live

# name: (camera, target, horizontal field of view); island metres.
SHOTS = {
    'air': ((1001, 2550, 738), (700, 200, 40), 62.),
    'rim': ((1180, 2080, 735), (900, 2420, 690), 62.),
    'zeppelin': ((300, 1300, 1300), (860, 2420, 650), 55.),
    'city': ((720, 430, 82), (850, 2400, 600), 55.),
    'dropin': ((985, 2505, 719.4), (820, 2380, 690), 75.),
    'bowls': ((790, 2335, 692), (700, 2445, 676), 72.),
    # The volcano from far away, from the ground (docs/VOLCANO.md).
    'hidamari': ((730, 167, 40), (850, 2400, 560), 50.),
    'belmonte': ((550, 4500, 215), (850, 2400, 560), 50.),
    'road': ((-149, 1474, 132), (850, 2400, 600), 55.),
}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
parser.add_argument('--port', type=int, default=8841)
parser.add_argument('--shots', default='', help='comma-separated shot names (default: all)')
parser.add_argument('--out', default='', help='folder for the shots (default: build output craterpark/review)')
parser.add_argument('--settle', type=float, default=6., help='seconds to wait at each camera before the shot')
parser.add_argument('--memory-gib', type=float, default=10., help='memory guard limit, 10 (the default) to 14 GiB, as atelier play')
parser.add_argument('--startup', type=float, default=780., help='seconds to wait for the game (a first run builds shaders)')
args = parser.parse_args()
if not 10. <= args.memory_gib <= 14.:
    sys.exit('--memory-gib must be 10 to 14')
live.URL = f'http://127.0.0.1:{args.port}'
ctx = Context('yorimichi')
out = Path(args.out) if args.out else yori.OUT / 'craterpark' / 'review'
out.mkdir(parents=True, exist_ok=True)
if not args.worker:
    sys.exit(guarded.run([sys.executable, str(Path(__file__).resolve()), '--worker', '--port', str(args.port), '--out', str(out),
                          '--settle', str(args.settle), '--startup', str(args.startup), '--memory-gib', str(args.memory_gib)] + (['--shots', args.shots] if args.shots else []),
                         out / 'guard', timeout=args.startup + 420, purpose='Crater Park review', kind='game',
                         limit_gib=args.memory_gib))


def ue(p):
    return (p[0] * 100., -p[1] * 100., p[2] * 100.)


shots = {k: v for k, v in SHOTS.items() if not args.shots or k in args.shots.split(',')}
(out / 'passed.json').unlink(missing_ok=True)
log = (out / 'game.log').open('w')
cmd = [str(ctx.unreal_app), str(ctx.uproject), '/Game/Japan/Maps/Slice', '-game', '-windowed', '-resx=1536', '-resy=1024',
       '-nosplash', '-stdout', f'-liveport={args.port}', '-ini:Engine:[HTTPServer.Listeners]:DefaultBindAddress=localhost',
       '-preferencesfile=' + str(out / 'settings.txt'), '-ExecCmds=t.MaxFPS 60,r.RHISetGPUCaptureOptions 0,DisableAllScreenMessages']
p = spawn_game(cmd, stdout=log, stderr=subprocess.STDOUT)
guards = ExitStack()
monitor = None


def run(code):
    if monitor is not None and monitor.poll() is not None and p.poll() is None:
        raise RuntimeError('Memory monitor exited before the game')
    r = live.request('/python', code, timeout=60)
    if not r.get('ok'):
        raise RuntimeError(r)
    print(r.get('output', '').strip(), flush=True)
    return r


def shot(name):
    path = out / (name + '.png'); path.unlink(missing_ok=True)
    run('unreal.LiveLibrary.screenshot(' + repr(str(path)) + ')')
    for _ in range(300):
        if path.exists():
            break
        time.sleep(.1)
    assert path.exists(), path


try:
    monitor = guards.enter_context(attach_memory_guard(p.pid, out / 'memory-health.json', duration=args.startup + 360,
                                                        limit_gib=args.memory_gib))
    deadline = time.monotonic() + args.startup
    while time.monotonic() < deadline:
        if p.poll() is not None:
            raise RuntimeError('Game exited ' + str(p.returncode))
        try:
            state = live.request('/state', timeout=1); break
        except OSError:
            time.sleep(1)
    else:
        raise RuntimeError('Bridge startup timed out')
    (out / 'initial-state.json').write_text(json.dumps(state, indent=2))
    run("import unreal, json\nw=unreal.LiveLibrary.game_world()\nparks=unreal.GameplayStatics.get_all_actors_of_class(w,unreal.SuperUltraMegaPark)\n"
        "print(len(parks),'parks')\nassert len(parks)==2,len(parks)\n"
        "crater=[a for a in parks if abs(a.get_actor_location().z-%r)<1]\nassert crater,'no Crater Park actor'\n"
        "print('crater park components',len(crater[0].get_components_by_class(unreal.StaticMeshComponent)))"
        % placement.unreal_transform()['location_cm'][2])
    ground, _ = placement.drop_in()
    g = ue(ground)
    traced = run(f'g=unreal.LiveLibrary.ground_at(unreal.Vector({g[0]},{g[1]},{g[2] + 500}))\nprint(json.dumps([g.x,g.y,g.z]))')
    hit = json.loads(traced['output'].strip().split('\n')[-1])
    # The marked ground point lies 1.7 m under its camera point, the ramp deck the trace finds.
    assert abs(hit[2] - g[2]) < 300, ('drop-in ground', hit, g)
    run('unreal.YorimichiLive.film_hud(True)')
    for i, (name, (at, target, fov)) in enumerate(shots.items()):
        x, y, z = ue(at); tx, ty, tz = ue(target)
        run(f'assert unreal.MegaParkValidation.review_camera(unreal.Vector({x},{y},{z}),unreal.Vector({tx},{ty},{tz}),{fov})')
        # The island streams textures and builds distance fields for a while after loading.
        time.sleep(25 if i == 0 else args.settle)
        shot(name)
    run('unreal.MegaParkValidation.restore_player_camera()\nunreal.YorimichiLive.film_hud(False)\n'
        f'assert unreal.YorimichiLive.skate_place(unreal.Vector({g[0]},{g[1]},{g[2]}),{placement.unreal_transform()["yaw_deg"]})')
    time.sleep(4)
    state = run('print(unreal.YorimichiLive.skate_state())')['output']
    (out / 'ride.txt').write_text(state)
    shot('riding')
    (out / 'passed.json').write_text(json.dumps({'shots': list(shots), 'drop_in_ground_cm': hit, 'ride': state}, indent=2))
finally:
    try:
        if p.poll() is None:
            live.request('/python', "unreal.SystemLibrary.quit_game(unreal.LiveLibrary.game_world(),None,unreal.QuitPreference.QUIT,False)", timeout=5)
    except Exception:
        pass
    try:
        p.wait(timeout=15)
    except subprocess.TimeoutExpired:
        reap(p)
    guards.close()
    log.close()
