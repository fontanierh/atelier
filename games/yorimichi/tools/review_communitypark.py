"""Capture and check the community park in an owned, guarded island game."""
import argparse
import json
import re
import socket
import subprocess
import sys
import time
from contextlib import ExitStack
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'world'))
import yori
from communitypark import layout as L
from communitypark.validate import surface_at
from atelier.build import Context
from atelier.safety import guarded
from atelier.safety.guard import attach, reap
from atelier import live


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--port', type=int, default=8843)
    parser.add_argument('--timeout', type=int, default=600, help='Guarded review duration in seconds (60–600)')
    args = parser.parse_args(); out = yori.OUT/'communitypark/game-review'; out.mkdir(parents=True, exist_ok=True)
    if not 60 <= args.timeout <= 600:
        parser.error('--timeout must be between 60 and 600 seconds')
    if not args.worker:
        return guarded.run([sys.executable, str(Path(__file__).resolve()), '--worker', '--port', str(args.port), '--timeout', str(args.timeout)],
                           out/'guard', timeout=args.timeout, kind='game', purpose='Hidamari community park validation and captures')
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', args.port)) == 0:
            raise RuntimeError(f'Review port {args.port} is occupied; refusing another game')
    ctx = Context('yorimichi'); live.URL = f'http://127.0.0.1:{args.port}'
    (out/'passed.json').unlink(missing_ok=True)
    log = (out/'game.log').open('w'); guards = ExitStack(); monitor = None; owns_bridge = False
    cmd = [str(ctx.unreal_app), str(ctx.uproject), '/Game/Japan/Maps/Slice', '-game', '-windowed', '-RenderOffscreen',
           '-ForceRes', '-resx=1600', '-resy=1000', '-nosplash', '-stdout', '-nofox', f'-liveport={args.port}',
           '-ini:Engine:[HTTPServer.Listeners]:DefaultBindAddress=localhost', '-preferencesfile='+str(out/'settings.txt'),
           '-ExecCmds=t.MaxFPS 60,r.RHISetGPUCaptureOptions 0,DisableAllScreenMessages']
    process = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
    def run(code):
        if process.poll() is not None: raise RuntimeError('Owned game exited')
        if monitor is not None and monitor.poll() is not None: raise RuntimeError('Game memory monitor exited')
        result = live.request('/python', code, timeout=30)
        if not result.get('ok'): raise RuntimeError(result)
        return result.get('output', '').strip()
    def ue(p): return [p[0]*100., -p[1]*100., p[2]*100.]
    def vector(p): return 'unreal.Vector('+','.join(str(float(x)) for x in ue(p))+')'
    def capture(name):
        file = out/(name+'.png'); file.unlink(missing_ok=True)
        run('unreal.LiveLibrary.screenshot('+repr(str(file))+')')
        for _ in range(150):
            if file.exists() and file.stat().st_size > 0: return
            time.sleep(.1)
        raise RuntimeError('Screenshot was not written: '+name)
    def ride(name, start, heading, seconds=3.5, speed=None):
        run('unreal.MegaParkValidation.restore_player_camera()\nunreal.YorimichiLive.film_hud(False)\n'
            f'assert unreal.YorimichiLive.skate_place({vector(start)},{-heading})\nunreal.YorimichiLive.skate_release()')
        for _ in range(40):
            state = run('print(unreal.YorimichiLive.skate_state())')
            if 'retail=PhysicsGround' in state: break
            time.sleep(.5)
        else: raise RuntimeError('Skate collision did not settle: '+state)
        run('ride_start=unreal.LiveLibrary.player().get_actor_location()')
        if speed is None:
            run('unreal.YorimichiLive.skate_input(unreal.Vector2D(),unreal.Vector2D(),True)')
        else:
            import math
            a = math.radians(-heading)
            run(f'assert unreal.YorimichiLive.skate_launch(unreal.Vector({speed*math.cos(a)},{speed*math.sin(a)},0))')
        rows = []; deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            time.sleep(.25); rows.append(run('print(unreal.YorimichiLive.skate_state())'))
        run('unreal.YorimichiLive.skate_release()')
        distance = float(run('q=unreal.LiveLibrary.player().get_actor_location()\nprint(unreal.Vector2D(q.x-ride_start.x,q.y-ride_start.y).length())').splitlines()[-1])
        bails = [int(re.search(r'\bbails=(\d+)', row).group(1)) for row in rows]
        assert max(bails) == 0, (name, rows)
        assert distance > 250, (name, distance, rows)
        (out/(name+'.txt')).write_text('\n'.join(rows)+'\n')
        capture(name)
        return {'displacement_cm': distance, 'bails': max(bails), 'samples': len(rows)}
    try:
        monitor = guards.enter_context(attach(process.pid, out/'memory-health.json', duration=args.timeout-20))
        deadline = time.monotonic()+180
        while time.monotonic() < deadline:
            if process.poll() is not None: raise RuntimeError('Game failed to start')
            try: initial = live.request('/state', timeout=1); break
            except OSError: time.sleep(1)
        else: raise RuntimeError('Owned bridge did not start')
        # Verify the bridge belongs to this exact checkout before moving anything.
        run('import unreal,json,os\nassert os.getpid() == '+str(process.pid)+'\nassert os.path.realpath(unreal.Paths.project_dir()) == '+repr(str(ctx.uproject.parent.resolve()))+'\n'
            'world=unreal.LiveLibrary.game_world()\nparks=unreal.GameplayStatics.get_all_actors_of_class(world,unreal.SkatePark)\n'
            'assert len(parks)==2\ncommunity=next(p for p in parks if p.actor_has_tag("communitypark"))\n'
            'pier=next(p for p in parks if p.actor_has_tag("skatepier"))\n'
            'all_components=community.get_components_by_class(unreal.StaticMeshComponent)\n'
            'components=[c for c in all_components if c.static_mesh and c.static_mesh.get_path_name().startswith("/Game/CommunityPark/")]\n'
            'assert len(components)==32 and all(c.static_mesh for c in components)\n'
            'assert all(c.static_mesh.get_path_name().startswith("/Game/CommunityPark/") for c in components)\n'
            'assert len(unreal.GameplayStatics.get_all_actors_of_class(world,unreal.SuperUltraMegaPark))==1')
        owns_bridge = True
        (out/'initial-state.json').write_text(json.dumps(initial, indent=2)+'\n')
        run(f'assert unreal.LiveLibrary.teleport_player({vector(L.SPAWN)},{-L.HEADING})\nunreal.YorimichiLive.film_hud(True)')
        time.sleep(12)
        shots = [('overview', (1430, 370, 150), (1280, 560, 49), 60.),
                 ('station_approach', (1240, 374, 42), (1290, 548, 55), 70.),
                 ('entrance', (1316, 507, 51), (1302, 555, 51), 70.),
                 ('bowls', (1248, 572, 59), (1283, 565, 47), 75.),
                 ('deck', (1252, 597, 50.2), (1280, 570, 51), 75.)]
        for name, at, target, fov in shots:
            run(f'assert unreal.MegaParkValidation.review_camera({vector(at)},{vector(target)},{fov})')
            time.sleep(4); capture(name); print('CAPTURE', out/(name+'.png'), flush=True)
        manifest = json.loads((yori.OUT/'communitypark/park.json').read_text())
        points = [(1300, 522), (1300, 528), (1300, 532), (1300, 536), (1280, 560), (1250, 575), (1255, 600), (1317, 540)]
        references = [[x, y, surface_at(x, y)] for x, y in points]
        traces = []
        for point in references:
            error = float(run(f'g=unreal.LiveLibrary.ground_at({vector([point[0], point[1], point[2]+10])})\nprint(abs(g.z-{point[2]*100}))').splitlines()[-1])
            assert error < .1, (point, error)
            traces.append({'point_m': point, 'error_cm': error})
        # The entrance and the station-side ribbon must be walkable too.
        for k in [0, 40, 100, 180, 260, 330, len(L.access())-1]:
            point = L.access()[k]; z = float(run(f'g=unreal.LiveLibrary.ground_at({vector(point+[0,0,10])})\nprint(g.z)').splitlines()[-1])
            # At the ribbon's exact boundary a trace may hit the street paving.
            # Allow a 2 cm join there; interior riding surfaces stay within 1 mm.
            tolerance = 2. if k == 0 else .1
            assert abs(z-point[2]*100) < tolerance, ('access', k, z, point.tolist())
        spawn = [float(x) for x in run('s=unreal.YorimichiLive.skate_park_spawn().translation\nprint(s.x,s.y,s.z)').splitlines()[-1].split()]
        assert spawn[0] < 0, ('Sunset Pier QA spawn changed', spawn)
        rides = {'deck': ride('ride_deck', [1250, 572, surface_at(1250, 572)], 90),
                 'approach': ride('ride_approach', L.access()[40].tolist(), 90),
                 'bowl': ride('ride_bowl', [1300, 522, surface_at(1300, 522)], 90, seconds=3, speed=200)}
        text = (out/'game.log').read_text(errors='ignore')
        assert re.search(r'SKATE PARK loaded: 32 meshes, '+str(len(manifest['rails']))+r' rails', text), 'Community grind paths not registered'
        result = {'park_actors': 2, 'source_meshes': 30, 'community_meshes': 32, 'grind_paths': len(manifest['rails']),
                  'screen_trees': sum(len(rows) for rows in manifest.get('trees', {}).values()),
                  'surface_traces': traces, 'access_traces': 7, 'captures': len(shots)+len(rides), 'rides': rides,
                  'sunset_pier_spawn_preserved': True}
        (out/'passed.json').write_text(json.dumps(result, indent=2)+'\n'); print(json.dumps(result, indent=2), flush=True)
        return 0
    finally:
        try:
            if process.poll() is None and owns_bridge:
                live.request('/python', 'unreal.SystemLibrary.quit_game(unreal.LiveLibrary.game_world(),None,unreal.QuitPreference.QUIT,False)', timeout=5)
        except OSError: pass
        try: process.wait(timeout=15)
        except subprocess.TimeoutExpired: reap(process)
        guards.close(); log.close()


if __name__ == '__main__':
    sys.exit(main())
