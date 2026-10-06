"""Ride Cairo's bike through every move in the real game, check what happened and film it (docs/BIKE.md).

    uv run python games/yorimichi/tools/review_bike.py [--port 8871] [--no-film] [--site x,y,yaw] [--crash x,y,yaw]

Run after unreal.compile, unreal.bike, unreal.cairo_bike and data.stage. Under the render guard it launches the
island, finds open level ground for the ride and a clear run for the crash near the towns (or takes --site/--crash in
Unreal cm and degrees), runs scenarios/bike_live.py on a fixed 60 fps step, then checks the recorded rows: the bike
comes out beside him, he mounts, pedals, turns both ways, rings, waves, hops, skids to a foot-down stop, parks on the
stand, gets back on the same parked bike, crashes at speed into a test wall put up across his path, and rides up a test
ramp with both wheels on it. Writes
build/yorimichi/bike/review/{checks.json, rows.json, sites.json, bike_*.png, bike.mp4, game.log}, and bike_sound.mp4
(and -720p): the film with its soundtrack mixed from the sounds the game played, the bike's loops and the camera
(scenarios/skate_mix_showreel.py). The worker owns and quits only the game process it launches.
"""
from pathlib import Path
from contextlib import ExitStack
import argparse, csv, json, math, shutil, subprocess, sys, time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
import yori
from atelier.build import Context
from atelier.safety import guarded
from atelier.safety.guard import attach as attach_memory_guard, reap
from atelier import live

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
parser.add_argument('--port', type=int, default=8871)
parser.add_argument('--no-film', action='store_true')
parser.add_argument('--site', default='', help='x,y,yaw (Unreal cm, degrees): level ground for the ride')
parser.add_argument('--crash', default='', help='x,y,yaw: at least 13 m of level, clear ground ahead (a test wall goes up at 11 m)')
parser.add_argument('--keep-frames', action='store_true')
parser.add_argument('--recheck', action='store_true', help='check the last run\'s rows.json again without the game')
args = parser.parse_args()
live.URL = f'http://127.0.0.1:{args.port}'
ctx = Context('yorimichi'); out = yori.OUT / 'bike' / 'review'; out.mkdir(parents=True, exist_ok=True)

ZONES = {z['key']: z for z in json.loads((yori.OUT / 'map' / 'map.json').read_text())['zones']}
# Island metres to Unreal centimetres.
def island(x, y, z): return (x * 100., -y * 100., z * 100.)

SEARCH = r'''
import math, json, unreal
world = unreal.LiveLibrary.game_world(); me = unreal.LiveLibrary.player()
def hit(a, b):
    h = unreal.SystemLibrary.line_trace_single(world, a, b, unreal.TraceTypeQuery.ECC_VISIBILITY, False, [me], unreal.DrawDebugTrace.NONE, True)
    if h is None: return None
    try: t = h.to_tuple()      # blocking_hit, initial_overlap, time, distance, location, impact_point, normal, impact_normal, ...
    except AttributeError: t = [h.get_editor_property(k) for k in ('blocking_hit', 'initial_overlap', 'time', 'distance', 'location', 'impact_point', 'normal', 'impact_normal')]
    if not t[0]: return None
    return t[3], t[7]
def ground(x, y, z): return unreal.LiveLibrary.ground_at(unreal.Vector(x, y, z))
def survey(x, y, z, reach=2500.):
    g = ground(x, y, z + 3000.)
    if abs(g.z - (z + 3000.)) < 1: return None
    rays = []
    for k in range(36):
        a = math.radians(k * 10.); d = (math.cos(a), math.sin(a))
        free = reach; wall = None
        for h in (45., 150.):
            r = hit(unreal.Vector(g.x, g.y, g.z + h), unreal.Vector(g.x + d[0] * reach, g.y + d[1] * reach, g.z + h))
            if r:
                free = min(free, r[0])
                if h == 45. and r[1].z < .6: wall = r[0]
        # Level and solid all the way: the ground stays within 40 cm every 2 m out to the first obstacle.
        flat = free
        for s in range(200, int(free) + 1, 200):
            q = ground(g.x + d[0] * s, g.y + d[1] * s, g.z + 400.)
            if abs(q.z - g.z) > 40. or abs(q.z - (g.z + 400.)) < 1: flat = s - 200; break
        rays.append(dict(heading=k * 10., free=free, flat=flat, wall=wall))
    return dict(x=g.x, y=g.y, z=g.z, rays=rays)
results = []
for key, (cx, cy, cz) in CANDIDATES.items():
    for dx in range(-1500, 1501, 1500):
        for dy in range(-1500, 1501, 1500):
            s = survey(cx + dx, cy + dy, cz)
            if s: s['zone'] = key; results.append(s)
print(json.dumps(results))
'''

def choose(results):
    """The ride: the most room all round (the lap's circle is about 15 m across). The crash: somewhere else with level,
    clear ground at least 13 m ahead, where the scenario puts up a test wall at 11 m."""
    def room(s): return min(min(r['flat'], r['free']) for r in s['rays'])
    ride = max(results, key=room)
    best = max(ride['rays'], key=lambda r: min(r['flat'], r['free']))
    runs = [(min(r['flat'], r['free']), s, r) for s in results if s is not ride for r in s['rays']]
    runs = [w for w in runs if w[0] >= 1300]
    crash = None
    if runs:
        _, s, r = max(runs, key=lambda w: w[0])
        crash = (s['x'], s['y'], r['heading'])
    return dict(site=(ride['x'], ride['y'], best['heading']), site_room_cm=room(ride), site_zone=ride['zone'], crash=crash,
                crash_run_cm=max(runs, key=lambda w: w[0])[0] if runs else None,
                crash_zone=max(runs, key=lambda w: w[0])[1]['zone'] if runs else None)


def rows_of(rows, seg): return [r for r in rows if r['seg'] == seg]
def num(r, k): return float(r[k])
def at(rows, t): return min(rows, key=lambda r: abs(r['t'] - t))
def clips(rows, t0=-1, t1=1e9): return [r['clip'] for r in rows if t0 <= r['t'] <= t1]


def check(rows, sites):
    results = {}
    def record(name, ok, note):
        results[name] = dict(ok=bool(ok), note=note); print(('PASS ' if ok else 'FAIL ') + name + ': ' + note, flush=True)
    ride = rows_of(rows, 'ride')
    before = at(ride, 1.55); first = next((r for r in ride if r['state'] == '1'), None)
    record('mount_starts', first is not None, f"Mounting from t={first['t'] if first else None}")
    if first:
        a, b = vec(before['pos']), vec(first['pos'])
        moved = math.hypot(a[0] - b[0], a[1] - b[1])
        record('summoned_beside', 15 < moved < 90, f'he steps {moved:.0f} cm onto the bike as it appears beside him')
    seated = at(ride, 3.6)
    record('mount_ends_riding', seated['state'] == '2' and seated['clip'] in ('BikeRide', 'BikeFootDown'), f"t=3.6 state={seated['state']} clip={seated['clip']}")
    top = max(num(r, 'speed') for r in ride if 3.7 <= r['t'] <= 6.5)
    record('pedals_up_to_speed', top > 400, f'{top:.0f} cm/s at 0.8 stick')
    def yaw_change(t0, t1):
        y0, y1 = num(at(ride, t0), 'yaw'), num(at(ride, t1), 'yaw'); return (y1 - y0 + 540) % 360 - 180
    right, left = yaw_change(6.5, 8.4), yaw_change(8.5, 10.4)
    record('turns_right', right > 45, f'{right:.0f} deg in 1.9 s steering right')
    record('turns_left', left < -45, f'{left:.0f} deg in 1.9 s steering left')
    steer = [num(r, 'steer') for r in ride if 7. <= r['t'] <= 8.4]
    record('bars_follow_stick', min(steer) > .3, f'steering {min(steer):.2f}..{max(steer):.2f}')
    for name, clip, t0, t1 in [('bell', 'BikeBell', 11., 12.2), ('wave', 'BikeWave', 12.2, 14.), ('hop', 'BikeHop', 14.2, 15.6)]:
        seen = clip in clips(ride, t0, t1); back = at(ride, t1 - .1)['clip'] == 'BikeRide'
        record(name, seen and back, f'{clip} seen={seen}, back on BikeRide={back}')
    lift = [r for r in ride if r['clip'] == 'BikeHop']
    dash = rows_of(rows, 'sprint')
    if dash:
        sprint = max(num(r, 'speed') for r in dash if 3. <= r['t'] <= 5.6)
        record('sprint', sprint > 1000, f'{sprint:.0f} cm/s pedalling hard from a standstill in 2.5 s (cruising tops at 600)')
        held = [r['sprint'] for r in dash if 3.1 <= r['t'] <= 5.45]
        ended = at(dash, 6.)['sprint']
        record('sprint_toggles', bool(held) and all(h == '1' for h in held) and ended == '0', f'on after one tap for {len(held)} rows, off at the skid: {ended == "0"}')
        skid = [r for r in dash if r['clip'] == 'BikeSkid']
        stop = next((r for r in dash if r['t'] > 5.5 and num(r, 'speed') < 15), None)
        record('sprint_skid_stop', bool(skid) and stop is not None and stop['t'] < 7.5, f"skid from {num(skid[0], 'speed') if skid else 0:.0f} cm/s, stopped at t={stop['t'] if stop else None}")
    else:
        record('sprint', False, 'no sprint segment (needs --crash)')
    skid = [r for r in ride if r['clip'] == 'BikeSkid']
    stop = next((r for r in ride if r['t'] > 18. and num(r, 'speed') < 15), None)
    record('skid_stop', bool(skid) and stop is not None and stop['t'] < 20. and 'BikeFootDown' in clips(ride, 18., 20.6),
           f"skid from {num(skid[0], 'speed') if skid else 0:.0f} cm/s, stopped at t={stop['t'] if stop else None}, then a foot down")
    states = ''.join(dict.fromkeys(r['state'] for r in ride if 20.75 <= r['t'] <= 24.2))
    parked = at(ride, 24.2)
    record('dismount_and_park', states.startswith('34') and parked['state'] == '0' and parked['parked'] == '1', f'states {states}, parked={parked["parked"]}')
    rot = vec(parked['bikerot']); bike = vec(parked['bike']); me = vec(parked['pos'])
    record('stands_upright', abs(rot[0]) < 3 and abs(rot[2]) < 3, f'bike pitch {rot[0]:.1f} roll {rot[2]:.1f} on its stand')
    gap = math.hypot(bike[0] - me[0], bike[1] - me[1])
    record('steps_off_beside', 20 < gap < 90, f'he stands {gap:.0f} cm from the bike origin')
    again = next((r for r in ride if r['t'] > 24.3 and r['state'] == '1'), None)
    if again:
        moved = math.dist(vec(again['bike'])[:2], bike[:2])
        record('remounts_parked_bike', moved < 5, f'the parked bike moved {moved:.1f} cm when he got back on')
    else: record('remounts_parked_bike', False, 'did not mount again')
    final = ride[-1]
    record('parks_again', final['state'] == '0' and final['parked'] == '1', f"end state={final['state']} parked={final['parked']} hint={final['hint']}")
    hints = sorted({r['hint'] for r in ride})
    record('no_refusals', not any(h.startswith(('Find', 'Stand', 'Only', 'The_bike')) for h in hints), ', '.join(hints))
    crash = rows_of(rows, 'crash')
    if sites.get('crash'):
        hit = next((r for r in crash if r['state'] == '5'), None)
        before = crash[crash.index(hit) - 1] if hit else None
        record('crash', hit is not None, f"crashed at {num(before, 'speed'):.0f} cm/s" if hit else 'no crash')
        if hit:
            # The test wall's near face is 1080 cm ahead of the crash start; his hands reach 164 cm ahead of where he is.
            x, y, yaw = sites['crash']; d = (math.cos(math.radians(yaw)), math.sin(math.radians(yaw)))
            ahead = max((vec(r['pos'])[0] - x) * d[0] + (vec(r['pos'])[1] - y) * d[1] for r in crash if r['state'] == '5')
            record('crash_clear_of_wall', ahead + 164 <= 1080, f'his reach ends {1080 - ahead - 164:.0f} cm short of the wall')
        if hit:
            end = crash[-1]; roll = vec(end['bikerot'])[2]
            record('crash_bike_down', end['state'] == '0' and abs(roll) > 50, f"end state={end['state']}, bike roll {roll:.0f} deg")
    else:
        record('crash', False, 'no clear 13 m run found near the towns: pass --crash x,y,yaw')
    # Wheels on the ground: neither sinks in while he rides on the ground, on the level or up the test ramp. The walking
    # capsule steps down over a kink in the terrain a few cm in one frame, so a sink counts once it lasts three frames
    # (the reported bug was a front wheel buried for as long as he rode a slope); one frame may not go past 9 cm.
    def gaps(r): return vec(r['gaps'])
    for seg in ('ride', 'sprint', 'slope'):
        rolling = [r for r in rows if r['seg'] == seg and r['state'] == '2' and r.get('air') == '0' and r['clip'] in ('BikeRide', 'BikeFootDown')]
        if len(rolling) < 3: continue
        low = [min(gaps(r)) for r in rolling]
        held = max(range(len(low) - 2), key=lambda i: -max(low[i:i + 3]))
        lasting, worst = max(low[held:held + 3]), min(low)
        record(f'wheels_not_sunk_{seg}', lasting > -4. and worst > -9.,
               f"deepest sink lasting 3 frames {lasting:.1f} cm (t={rolling[held]['t']}), deepest single frame {worst:.1f} cm")
    slope = rows_of(rows, 'slope')
    if slope:
        # On the ramp (pitched within 1 degree of its 12.5): both wheels on its face. Off its top the front wheel rightly
        # hangs over the drop, so those rows are not counted.
        up = [r for r in slope if r['state'] == '2' and r.get('air') == '0' and num(r, 'groundpitch') > 11.5][3:]   # settled onto it
        on = [max(abs(g) for g in gaps(r)) for r in up]
        record('ramp_pitch', len(up) > 20 and max(on) < 3., f"{len(up)} rows pitched up the ramp, top {max((num(r, 'groundpitch') for r in slope), default=0):.1f} deg, "
               f"wheels within {max(on, default=0):.1f} cm of it")
    else:
        record('ramp_pitch', False, 'no slope segment')
    return results


def vec(text): return [float(x) for x in text.strip('()').split(',')]


if args.recheck:
    rows = json.loads((out / 'rows.json').read_text()); sites = json.loads((out / 'sites.json').read_text())
    results = check(rows, sites)
    print('PASSED' if all(r['ok'] for r in results.values()) else 'FAILED', sum(r['ok'] for r in results.values()), '/', len(results))
    sys.exit(0)
if not args.worker:
    sys.exit(guarded.run([sys.executable, str(Path(__file__).resolve()), '--worker'] + sys.argv[1:], out / 'guard', timeout=1200,
                         purpose='bike review', kind='game'))
(out / 'checks.json').unlink(missing_ok=True)
for old in list(out.glob('bike_*.png')) + [out / 'bike.mp4']: old.unlink(missing_ok=True)
shutil.rmtree(out / 'film', ignore_errors=True)
log = (out / 'game.log').open('w')
cmd = [str(ctx.unreal_app), str(ctx.uproject), '-game', '-windowed', '-resx=1280', '-resy=720', '-nosplash', '-stdout', '-nofox',
       f'-liveport={args.port}', '-ini:Engine:[HTTPServer.Listeners]:DefaultBindAddress=localhost',
       '-preferencesfile=' + str(out / 'settings.txt'), '-ExecCmds=t.MaxFPS 60,r.RHISetGPUCaptureOptions 0,DisableAllScreenMessages']
p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
guards = ExitStack(); monitor = None


def run(code, timeout=60):
    if monitor is not None and monitor.poll() is not None and p.poll() is None:
        raise RuntimeError('Memory monitor exited before the game')
    r = live.request('/python', code, timeout=timeout)
    if not r.get('ok'): raise RuntimeError(r)
    return r.get('output', '')


try:
    monitor = guards.enter_context(attach_memory_guard(p.pid, out / 'memory-health.json', duration=1100))
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        if p.poll() is not None: raise RuntimeError('Game exited ' + str(p.returncode))
        try: live.request('/state', timeout=1); break
        except OSError: time.sleep(1)
    else: raise RuntimeError('Bridge startup timed out')
    # Shaders and streaming: wait for a steady frame rate before the fixed-step run.
    steady, start = None, time.monotonic()
    print('bridge up; waiting for a steady frame rate', flush=True)
    while time.monotonic() - start < 240:
        fps = live.request('/state').get('fps', 0)
        if int(time.monotonic() - start) % 10 == 0: print(f'warming up {time.monotonic() - start:.0f} s, {fps:.0f} fps', flush=True)
        steady = (steady or time.monotonic()) if fps >= 25 else None
        if steady and time.monotonic() - steady > 3: break
        time.sleep(.5)
    state = run('print(live.bike_state())').strip()
    print(state, flush=True)
    assert 'no bike' not in state, state
    def parse_site(text): return tuple(float(v) for v in text.split(',')) if text else None
    sites = dict(site=parse_site(args.site), crash=parse_site(args.crash))
    if not sites['site'] or not sites['crash']:
        candidates = {k: island(ZONES[k]['x'], ZONES[k]['y'], ZONES[k]['z']) for k in ('park', 'plaza', 'arrival', 'hamlet', 'spawn', 'station', 'arcade', 'hillside')}
        print('searching for a ride site and a crash run', flush=True)
        results = json.loads(run('CANDIDATES=' + repr(candidates) + '\n' + SEARCH, timeout=300).strip().splitlines()[-1])
        chosen = choose(results)
        sites = dict(chosen, site=sites['site'] or chosen['site'], crash=sites['crash'] or chosen['crash'])
    (out / 'sites.json').write_text(json.dumps(sites, indent=2) + '\n')
    print('sites', json.dumps(sites), flush=True)
    script = (yori.GAME / 'scenarios' / 'bike_live.py').read_text()
    run(f"OUT={str(out)!r}; SITE={tuple(sites['site'])!r}; CRASH={tuple(sites['crash']) if sites['crash'] else None!r}; FILM={not args.no_film}\n" + script)
    deadline = time.monotonic() + 800
    began, said = time.monotonic(), 0.
    while not (out / 'done.json').exists():
        if p.poll() is not None: raise RuntimeError('Game exited ' + str(p.returncode))
        if time.monotonic() > deadline: raise RuntimeError('bike scenario timed out')
        if time.monotonic() - said > 10:
            said = time.monotonic()
            try: progress = json.loads((out / 'progress.json').read_text())
            except (OSError, ValueError): progress = 'no frames yet'
            print(f'scenario running {said - began:.0f} s: {progress}', flush=True)
        time.sleep(1)
    time.sleep(1)
    done = json.loads((out / 'done.json').read_text())
    rows = json.loads((out / 'rows.json').read_text())
    if done['error']: print(done['error'], flush=True)
    results = check(rows, sites) if not done['error'] or rows else {}
    log.flush()
    summons = [line.split('ready=')[1].strip() for line in (out / 'game.log').read_text(errors='replace').splitlines() if 'BIKE summon: materials ready=' in line]
    results['materials_ready_at_summon'] = dict(ok=bool(summons) and all(r == '1' for r in summons), note=f"M_Bike's shaders made at each summon: {summons}")
    print(('PASS ' if results['materials_ready_at_summon']['ok'] else 'FAIL ') + 'materials_ready_at_summon: ' + results['materials_ready_at_summon']['note'], flush=True)
    for still, frame in done.get('film_copies', []):
        if Path(still).exists(): shutil.copyfile(still, frame)
    film = [f for seg in ('ride', 'sprint', 'crash', 'slope') for f in sorted((out / 'film').glob(f'{seg}_*.png'))]
    if film:
        listing = out / 'film' / 'list.txt'
        listing.write_text(''.join(f"file '{f.name}'\nduration 0.0333333\n" for f in film))
        subprocess.run(['nice', '-n', '10', 'ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(listing), '-vf', 'fps=30,format=yuv420p',
                        '-c:v', 'libx264', '-crf', '22', '-preset', 'medium', '-threads', '3', str(out / 'bike.mp4')], check=True)
        if (out / 'audio.json').exists() and (out / 'loops.csv').exists() and (out / 'loops.csv').read_text().strip():
            # The soundtrack: the film's frames in order, the camera per frame and the bike's loops per 60 Hz tick.
            sys.path.insert(0, str(yori.GAME / 'scenarios')); import skate_mix_showreel as showreel
            for k, f in enumerate(film): (out / 'film' / f'seq_{k:05d}.png').symlink_to(f.name)
            cams = [[float(r['frame']), float(r['x']), float(r['y']), float(r['z']), float(r['yaw'])] for r in csv.DictReader(open(out / 'camera.csv'))]
            loops = json.loads((yori.OUT / 'audio' / 'bike' / 'manifest.json').read_text())['loops']
            sound = showreel.mix(out, out / 'film' / 'seq_%05d.png', len(film), cams, [r for r in (out / 'loops.csv').read_text().split('\n') if r.strip()],
                                 json.loads((out / 'audio.json').read_text()), 'bike_sound', loops=('bike', loops))
            print('soundtrack', json.dumps(sound), flush=True)
        if not args.keep_frames: shutil.rmtree(out / 'film')
    summary = dict(passed=bool(results) and all(r['ok'] for r in results.values()) and not done['error'], error=done['error'],
                   frames=done['frames'], checks=results, sites=sites)
    (out / 'checks.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('PASSED' if summary['passed'] else 'FAILED', sum(r['ok'] for r in results.values()), '/', len(results), flush=True)
finally:
    try:
        if p.poll() is None: live.request('/python', "unreal.SystemLibrary.quit_game(unreal.LiveLibrary.game_world(),None,unreal.QuitPreference.QUIT,False)", timeout=5)
    except Exception: pass
    try: p.wait(timeout=20)
    except subprocess.TimeoutExpired: reap(p)
    # A game that quits early can leave its SDK check (Turnkey under RunUAT) running, holding the UAT mutex every
    # compile waits on. End only the ones started for this checkout's project.
    found = subprocess.run(['pgrep', '-f', f'Turnkey.*{ctx.uproject}|{ctx.uproject}.*Turnkey'], capture_output=True, text=True).stdout.split()
    if found:
        print('ending this checkout\'s leftover Turnkey:', ' '.join(found), flush=True)
        subprocess.run(['kill', '-TERM', *found], check=False)
    guards.close(); log.close()
