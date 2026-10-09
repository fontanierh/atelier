"""A gameplay walk through the tree house: Cairo comes up from the trail and explores it the way a player would (the
rooms, the bridges, the spiral stairs to the crow's nest and back down, then the slide to the forest floor), filmed
in the running game with the normal follow camera.

    python games/yorimichi/scenarios/treehouse_walk.py plan
    python games/yorimichi/scenarios/treehouse_walk.py film TAKE [--rehearse]
    python games/yorimichi/scenarios/treehouse_walk.py cut TAKE

plan writes build/yorimichi/treehouse/walk/route.json from the layout: the path every 0.25 m (Blender metres, feet on
the floor) with the gait and camera for each point, and the stops where Cairo stands and looks round. film launches
the game through the guarded runner and sends treehouse_walk_live.py over the live bridge; it steers Cairo along the
route with stick input at a fixed 60 fps step and saves every frame, the camera and the sounds the game starts into
build/yorimichi/treehouse/walk/TAKE. --rehearse runs the same route without saving frames and reports where Cairo got
stuck. cut mixes the footsteps under the ambience (tools/mix_capture.py) and makes a phone copy under 30 MB.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
import importlib.util, json, math, os, shutil, subprocess, sys, time, urllib.request
from pathlib import Path
import numpy as np
from atelier.engine import unreal_app

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
WALK = yori.OUT/'treehouse'/'walk'
STEP = .25                    # route spacing (m)
UNREAL = unreal_app()
PROJECT = REPO/'games/yorimichi/unreal'
BRIDGE = 'http://127.0.0.1:8830'


def unit(a):
    return np.array([math.cos(math.radians(a)), math.sin(math.radians(a))])


class Route:
    """Points every STEP metres with a gait, a stick magnitude and a camera each; stops hold Cairo still while the
    camera looks at a list of targets."""
    def __init__(self):
        self.points, self.gait, self.mag, self.cam, self.stops = [], [], [], [], []

    def go(self, pts, gait='run', mag=1., cam=('follow', -10)):
        pts = [np.asarray(p, float) for p in pts]
        if self.points: pts = [np.asarray(self.points[-1])]+pts
        for a, b in zip(pts, pts[1:]):
            n = max(1, int(math.ceil(np.linalg.norm(b-a)/STEP)))
            for k in range(1, n+1):
                self.points.append([round(float(v), 3) for v in a+(b-a)*k/n])
                self.gait.append(gait); self.mag.append(mag); self.cam.append(list(cam))

    def stop(self, seconds, *looks, pitch=-5):
        """looks: (time, (x, y, z)) targets for the camera, eased from one to the next. The chase camera looks no
        higher than pitch: looking up drops it behind his head to the floor or the rail."""
        self.stops.append({'at': len(self.points)-1, 'seconds': seconds, 'looks': [[t, [float(v) for v in q]] for t, q in looks], 'pitch': pitch})


def plan():
    lay = json.loads((yori.OUT/'treehouse'/'layout.json').read_text()); P = lay['places']; cr = lay['crow']; sl = lay['slide']
    dh = lay['door'][1]
    R = Route()
    # what hides Cairo without stopping a trace (cloth and lanterns have no collision), as (x, y, z, radius): the door
    # curtains (noren) of every room and the paper lanterns on the bridges' end posts; the chase camera keeps them
    # out of its view
    curtains = [[*q[:2], q[2]+1.42, .3] for br in lay['bridges'] for q in br['lanterns']]
    for p in P.values():
        for d in p.get('room', {}).get('doors', []):
            curtains.append([d[0], d[1], p['deck']+dh-.45, .55])

    def at(n, a, r, up=0.):
        p = P[n]; return [*(np.array(p['xy'])+unit(a)*r), p['deck']+up]

    def arc(n, a0, a1, r, up=0., turn=0):
        """Points round place n from angle a0 to a1 at radius r; turn=1 counter-clockwise, -1 clockwise, 0 as given."""
        if turn > 0: a1 = a0+(a1-a0) % 360
        elif turn < 0: a1 = a0-(a0-a1) % 360
        k = max(2, int(abs(a1-a0)/8)+1)
        return [at(n, a, r, up) for a in np.linspace(a0, a1, k)]

    def bridge(a, b):
        br = next(x for x in lay['bridges'] if {x['a'], x['b']} == {a, b})
        A, B = (br['start'], br['end']) if br['a'] == a else (br['end'], br['start'])
        A, B = np.array(A), np.array(B); ax = (B-A)/np.linalg.norm(B-A); out = [A-ax*.5]
        for t in np.linspace(0, 1, 9):
            q = A+(B-A)*t; q[2] -= 4*br['sag']*t*(1-t); out.append(q)
        return out+[B+ax*.5]

    def end_angle(n, other):
        """Angle round place n of the bridge end towards other."""
        br = next(x for x in lay['bridges'] if {x['a'], x['b']} == {n, other})
        q = np.array(br['start'] if br['a'] == n else br['end'])[:2]-np.array(P[n]['xy'])
        return math.degrees(math.atan2(q[1], q[0]))

    def room(n, lx, ly, up=0.):
        """A point in place n's room frame (layout room(): x out from the trunk, the doors at -y and +y)."""
        r = P[n]['room']; a = r['angle']
        return [*(np.array(r['center'])+unit(a)*lx+unit(a+90)*ly), P[n]['deck']+up]

    def door(n, k, out=0.):
        """Door k of place n's room, or a point `out` metres in front of it (negative: inside)."""
        d = P[n]['room']['doors'][k]; return [*(np.array(d[:2])+unit(d[2])*out), P[n]['deck']]

    def through(n, k, stop, looks, mid=()):
        """From the porch in by door k, along the way from door to door to the stop (a look round), and out by the
        other door onto its porch. The rooms are big enough for the chase camera to follow him in."""
        R.go([door(n, k, 1.4), door(n, k, .3)], 'run', .6)
        R.go([door(n, k, -.8), *mid, stop], 'run', .5, ('follow', -8))
        R.stop(3.4, *looks)
        R.go([door(n, 1-k, -.8), door(n, 1-k, .3), door(n, 1-k, 1.4)], 'run', .55, ('follow', -8))

    # 1. the trail, the stepping stones and the entry steps up to the little hut's north door
    st = [np.array(s) for s in lay['stones']]; back = st[0]+(st[0]-st[1])/np.linalg.norm(st[0]-st[1])*3.5
    es = lay['entry_stairs']; ex = es['x']; E = P['entry']; ze = E['deck']; ec = E['room']['center']
    R.go([back, back+(st[0]-back)*.05], 'walk', 1.)
    R.stop(2.8, (0, (*ec, ze+2.5)), (1.5, (ec[0]-2, ec[1], ze+1.2)))
    R.go([*st[1:], es['foot'], (ex, es['top_y']-.15, ze)], 'run', .8, ('follow', -6))
    # 2. through the little hut (north door, south door) to the south porch and the view
    R.go([door('entry', 0, .3)], 'run', .45, ('follow', -8))
    R.go([door('entry', 0, -.8), room('entry', 0, 0)], 'run', .45, ('follow', -8))
    R.stop(2.2, (0, room('entry', -1.8, .4, 1.5)), (1.2, room('entry', 1.8, -.6, 1.2)))
    R.go([door('entry', 1, -.8), door('entry', 1, .3), door('entry', 1, 1.5)], 'run', .45, ('follow', -8))
    R.stop(3.0, (0, (-139, 165, 73.5)), (1.6, (-131, 168, 76.0)))
    # 3. across to the Map room: in by the door by the landing, a look at the map table and the shelves, out by the
    # other door to the sleeping nest's bridge
    R.go(bridge('entry', 'library'), 'run', 1.)
    through('library', 0, room('library', 0, 0), ((0, room('library', 2.1, -.2, .9)), (1.7, room('library', -2.7, 0, 1.3))))
    R.go(bridge('library', 'sleep'), 'sprint', 1.)
    # 4. the sleeping nest: a look at the futons and the hammocks, out to the pulley bridge
    through('sleep', 0, room('sleep', .2, 0), ((0, room('sleep', -2.1, -1.2, .4)), (1.7, room('sleep', 2.0, 2.9, 1.0))))
    R.go(bridge('sleep', 'pulley'), 'sprint', 1.)
    # 5. the pulley deck: a look at the crane and its basket
    pu = P['pulley']; a_in = end_angle('pulley', 'sleep'); a_to = end_angle('pulley', 'heart')
    a_mid = a_in-((a_in-a_to) % 360)*.45
    R.go(arc('pulley', a_in, a_mid, 2.6), 'run', .7)
    tip = np.array(pu['xy'])+unit(pu['open'])*3.75
    R.stop(2.2, (0, (*tip, pu['deck']+1.4)), (1.3, (*tip, pu['deck']-1.5)))
    R.go(arc('pulley', a_mid, a_to, 2.6, turn=-1), 'run', .8)
    R.go(bridge('pulley', 'heart'), 'sprint', 1.)
    # 6. the heart hall: in by the west door, a look round from the middle (the table by the front window, the
    # camphor through the round window, the view window), out by the north door to the kitchen bridge
    through('heart', 0, room('heart', 0, 0), ((0, room('heart', 2.0, 0, .6)), (1.4, room('heart', -4.5, 0, 1.6)),
                                               (2.8, room('heart', 0, -4.5, 1.9))))
    R.go(bridge('heart', 'kitchen'), 'run', 1.)
    # 7. the kitchen: a look at the stove and the table, out to the boat bridge
    through('kitchen', 1, room('kitchen', .2, 0), ((0, room('kitchen', -2.6, -1.1, .9)), (1.7, room('kitchen', 1.95, .5, .6))))
    R.go(bridge('kitchen', 'boat'), 'run', 1.)
    # 8. in under the upturned hull from the trunk side, a look up at the lantern and the bunks, and out to the slide
    bo = P['boat']; c = bo['room']['center']; zb = bo['deck']
    R.go([[*c, zb]], 'run', .6, ('follow', -6))
    R.stop(2.4, (0, (*c, zb+2.4)), (1.4, room('boat', 0, -1.2, .6)))
    R.go(bridge('boat', 'slide')[:1], 'run', .7)
    R.go(bridge('boat', 'slide')[1:], 'sprint', 1.)
    # 9. past the slide's mouth to the chime tree and the lookout
    a_in = end_angle('slide', 'boat'); a_to = end_angle('slide', 'chimes')
    R.go(arc('slide', a_in, a_to, 2.0, turn=1), 'run', .8)
    R.go(bridge('slide', 'chimes'), 'run', 1.)
    a_in = end_angle('chimes', 'slide'); a_to = end_angle('chimes', 'lookout')
    R.go(arc('chimes', a_in, a_in+100, 1.8), 'run', .6)     # past the lantern post at the bridge end
    R.stop(2.0, (0, at('chimes', a_in+125, 1.6, 2.0)), (1.2, at('chimes', a_in+165, 1.6, 1.9)))
    R.go(arc('chimes', a_in+100, a_to, 1.8, turn=1), 'run', .8)
    R.go(bridge('chimes', 'lookout'), 'sprint', 1.)
    # 10. the spiral stairs up to the crow's nest, a look at the sea and back at the tree house, and down again
    lo = P['lookout']; cx, cy = lo['xy']; zl = lo['deck']; a_in = end_angle('lookout', 'chimes'); rs = 1.22
    helix = [[cx+rs*math.cos(math.radians(a)), cy+rs*math.sin(math.radians(a)), zl+(k+1)*cr['rise']]
             for k in range(cr['steps']) for a in (cr['start']+(k+.5)*cr['da'],)]
    R.go([at('lookout', a_in+3, 2.55), at('lookout', 355, 2.5), at('lookout', 335, 2.5), at('lookout', 312, 2.2), at('lookout', 300, 1.5),
          at('lookout', 312, rs), at('lookout', cr['start']-4, rs)], 'run', .7)
    # up the spiral the camera circles outside it; the last ten treads, from the crow's nest floor ahead of him,
    # looking down the stairwell (from outside it would be under the floor)
    top = cr['floor']; a_top = cr['start']+cr['steps']*cr['da']; hatch = ('ring', cx, cy, 2.2, top+1.75, 80, 0.)
    nest = ('follow', -6, top+1.9)             # under the canvas roof (cloth: no wall test stops the camera)
    R.go(helix[:-10], 'run', .75, ('orbit', cx, cy, 160, -20))
    R.go(helix[-10:]+[[cx+rs*math.cos(math.radians(a)), cy+rs*math.sin(math.radians(a)), top] for a in np.linspace(a_top, a_top+18, 4)],
         'run', .6, hatch)
    R.go([[cx+r*math.cos(math.radians(a)), cy+r*math.sin(math.radians(a)), top] for a, r in ((a_top+45, 1.45), (190, 1.55), (266, 2.0))],
         'run', .5, nest)
    R.stop(6.0, (0, (cx-6, cy-60, top-9)), (2.4, (cx+22, cy-50, top-12)), (4.2, (-131, 168, 79.0)))
    R.go([[cx+r*math.cos(math.radians(a)), cy+r*math.sin(math.radians(a)), top] for a, r in ((190, 1.55), (a_top+50, 1.55))],
         'run', .6, ('follow', -10, top+1.9))
    R.go([[cx+rs*math.cos(math.radians(a_top+14)), cy+rs*math.sin(math.radians(a_top+14)), top]]+helix[::-1][:7], 'run', .7, (*hatch[:5], -80, 0.))
    R.go(helix[::-1][7:], 'run', 1., ('orbit', cx, cy, 200, -22))
    R.go([at('lookout', cr['start']-14, 1.3), at('lookout', 298, 1.8), at('lookout', 310, 2.3), at('lookout', 340, 2.45),
          at('lookout', a_in+3, 2.55)], 'run', .7)
    # 11. back over the chimes to the slide, and down it
    R.go(bridge('lookout', 'chimes'), 'sprint', 1.)
    a_in = end_angle('chimes', 'lookout'); a_to = end_angle('chimes', 'slide')
    R.go(arc('chimes', a_in, a_to, 1.8, turn=-1), 'run', .8)
    R.go(bridge('chimes', 'slide'), 'run', 1.)
    sc = np.array(sl['center']); zs = P['slide']['deck']; a_in = end_angle('slide', 'chimes')
    R.go(arc('slide', a_in, 282, 2.0, turn=1)+[[*(sc+unit(296)*2.9), zs], [*(sc+unit(306)*sl['rc']), zs]], 'run', .7)
    path = sl['path']; R.go([q[:3] for q in path], 'sprint', 1., ('follow', -20))
    tail = np.array(path[-1][:2]); tg = unit(path[-1][3]+90); e = unit(path[-1][3]); g = path[-1][4]
    R.go([[*(tail+tg*2.0), g], [*(tail+tg*3.2+e*.8), g], [*(tail+tg*4.0+e*2.2), g]], 'run', .6, ('follow', -8))
    R.stop(4.0, (0, (*sc, zs+1.0)), (2.2, (-131, 168, 78)), pitch=14)
    R.go([[*(tail+tg*4.1+e*2.4), g]], 'walk', .5)

    WALK.mkdir(parents=True, exist_ok=True)
    speed = {'walk': .92, 'run': 4.08, 'sprint': 6.37}
    secs = sum(STEP/(speed[g]*max(m, .3)) for g, m in zip(R.gait, R.mag))+sum(s['seconds'] for s in R.stops)
    out = {'points': R.points, 'gait': R.gait, 'mag': R.mag, 'cam': R.cam, 'stops': R.stops,
           'curtains': [[round(float(v), 3) for v in c] for c in curtains],
           'estimate_seconds': round(secs, 1)}
    (WALK/'route.json').write_text(json.dumps(out))
    print(f'route: {len(R.points)} points ({len(R.points)*STEP:.0f} m), {len(R.stops)} stops, about {secs:.0f} s -> {WALK/"route.json"}')


def bridge_up():
    try:
        with urllib.request.urlopen(BRIDGE+'/state', timeout=3) as r: return r.status == 200
    except Exception: return False


def send(code):
    req = urllib.request.Request(BRIDGE+'/python', data=code.encode(), method='POST')
    with urllib.request.urlopen(req, timeout=120) as r: out = json.loads(r.read().decode())
    if not out.get('ok'): raise RuntimeError(out.get('result', out))
    return out.get('output', '')


def film(take, rehearse):
    # the capture look (SETTINGS, COMMANDS) from the reference views, loaded by path: `import treehouse` is the region
    spec = importlib.util.spec_from_file_location('treehouse_views', HERE/'treehouse.py')
    views = importlib.util.module_from_spec(spec); spec.loader.exec_module(views)
    out = WALK/take
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True)
    if not (WALK/'route.json').exists(): plan()
    settings = PROJECT/'Saved/settings.txt'; saved = out/'settings.before.txt'
    if settings.exists(): shutil.copy(settings, saved)
    cmd = [sys.executable, '-m', 'atelier.safety.guarded', '--report', str(out/'guard'), '--timeout', '5400', '--purpose', f'Tree house walk {take}',
           '--', str(UNREAL), str(PROJECT/'Yorimichi.uproject'), '-game', '-RenderOffscreen', '-ForceRes', '-resx=1920', '-resy=1080', '-nofox',
           '-unattended', '-nosplash', '-stdout', '-noshaderworker', '-set='+views.SETTINGS+';show_fps=0;stamina_rings=5;cam_dist=330',
           '-ExecCmds='+views.COMMANDS, '-abslog='+str(out/'game.log')]
    env = dict(os.environ, PYTHONPATH=str(REPO/'platform/studio'))
    game = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        t0 = time.time()
        while not bridge_up():
            if game.poll() is not None: raise RuntimeError('the game quit before the live bridge started; see game.log')
            if time.time()-t0 > 900: raise RuntimeError('no live bridge after 15 minutes')
            time.sleep(3)
        print(f'bridge up after {time.time()-t0:.0f} s')
        send(f'TAKE = {take!r}; FILM = {not rehearse}')
        print(send((HERE/'treehouse_walk_live.py').read_text()).strip())
        t0 = time.time(); last = -1
        while not (out/'done.json').exists():
            if game.poll() is not None: raise RuntimeError('the game quit during the walk; see game.log')
            time.sleep(10)
            n = len([f for f in os.listdir(out) if f.endswith('.jpg')])
            prog = out/'progress.txt'
            if n != last or prog.exists():
                print(f'  {time.time()-t0:5.0f} s  {n} frames  {prog.read_text().strip() if prog.exists() else ""}', flush=True); last = n
        print((out/'done.json').read_text())
        try: send('unreal.SystemLibrary.execute_console_command(None, "quit")')
        except Exception: pass
        game.wait(timeout=180)
    finally:
        if game.poll() is None: game.terminate(); time.sleep(5); game.kill()
        if saved.exists(): shutil.copy(saved, settings)


def cut(take):
    """The game's own sounds mixed under the ambience, and a wind bell where Cairo stops under the chimes and on the
    crow's nest (as in the tour)."""
    import treehouse_tour as tour                                 # this script's folder is on the path
    out = WALK/take; done = json.loads((out/'done.json').read_text()); route = json.loads((WALK/'route.json').read_text())
    subprocess.run([sys.executable, str(REPO/'games/yorimichi/tools/mix_capture.py'), str(out), '--out', 'mix'], check=True)
    lay = json.loads((yori.OUT/'treehouse'/'layout.json').read_text()); P = lay['places']
    near = lambda q, n, r: math.hypot(q[0]-P[n]['xy'][0], q[1]-P[n]['xy'][1]) < r and abs(q[2]-(lay['crow']['floor'] if n == 'lookout' else P[n]['deck'])) < 1.
    bells = [m['frame']/60+.4 for m in done['stops'] if any(near(route['points'][m['stop']], n, 3.) for n in ('chimes', 'lookout'))]
    mp4 = out/'treehouse-walk.mp4'; phone = out/'treehouse-walk-phone.mp4'
    mix = '[1:a]anull[m]'; parts = ['[m]']
    for i, t in enumerate(bells):
        mix += f';[{i+2}:a]aresample=48000,volume=0.7,adelay={int(t*1000)}|{int(t*1000)}[b{i}]'; parts.append(f'[b{i}]')
    mix += ';'+''.join(parts)+f'amix=inputs={len(parts)}:normalize=0:duration=first[a]'
    cmd = ['ffmpeg', '-y', '-v', 'error', '-i', str(out/'mix.mp4'), '-i', str(out/'mix.wav')]+sum([['-i', str(tour.BELL)] for _ in bells], [])
    subprocess.run(cmd+['-filter_complex', mix, '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '256k',
                        '-movflags', '+faststart', str(mp4)], check=True)
    secs = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(mp4)],
                                capture_output=True, text=True, check=True).stdout)
    rate = int(min(2600, 27*8*1024*1024/secs/1000-160))          # kbit/s of video that keeps the copy under ~27 MB
    for n in (1, 2):
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(mp4), '-vf', 'scale=1280:720', '-c:v', 'libx264', '-preset', 'slow',
                        '-b:v', f'{rate}k', '-pass', str(n), '-passlogfile', str(out/'pass'), '-pix_fmt', 'yuv420p']
                       + (['-an', '-f', 'mp4', os.devnull] if n == 1 else ['-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', str(phone)]),
                       check=True)
    for f in out.glob('pass*'): f.unlink()
    print(f'{mp4} ({mp4.stat().st_size/1e6:.0f} MB), phone copy {phone} ({phone.stat().st_size/1e6:.1f} MB, {secs:.0f} s)')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args or args[0] not in ('plan', 'film', 'cut'): print(__doc__); sys.exit(2)
    if args[0] == 'plan': plan()
    elif args[0] == 'film': film(args[1], '--rehearse' in sys.argv)
    else: cut(args[1])
