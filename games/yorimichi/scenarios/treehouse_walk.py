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
stuck. cut mixes the footsteps under the ambience (tools/mix_fight_film.py) and makes a phone copy under 30 MB.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
import json, math, os, shutil, subprocess, sys, time, urllib.request
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
WALK = yori.OUT/'treehouse'/'walk'
STEP = .25                    # route spacing (m)
HUT = (3.4, 2.8)              # layout.HUT: width, depth
UNREAL = Path(os.environ.get('UE_ROOT', '/Users/Shared/Epic Games/UE_5.8'))/'Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor'
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
    layout_heart_wall = lay['heart_wall']
    R = Route()
    # what hides Cairo without stopping a trace (cloth and lanterns have no collision), as (x, y, z, radius): the door
    # curtains and the paper lantern on the post at each bridge end; the chase camera keeps them out of its view
    curtains = []
    for br in lay['bridges']:
        A, B = np.array(br['start'], float), np.array(br['end'], float); u = (B-A)[:2]/np.linalg.norm((B-A)[:2]); v = np.array([-u[1], u[0]])
        for q, sd in ((A, 1), (B, -1)):
            curtains.append([*(q[:2]+v*sd*(lay['bridge_width']/2+.07)), q[2]+1.42, .3])

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

    def hut(n):
        p = P[n]; ang = p['open']; d2 = HUT[1]/2
        diffs = [((l['angle']-ang+540) % 360)-180 for l in p['links']]
        side = 1 if min(diffs, key=abs) > 0 else -1
        c = np.array(p['xy'])+unit(ang)*(p['trunk']+.3+d2)
        return lambda lx, sy, up=0.: [*(c+unit(ang)*lx+unit(ang+90)*side*sy), p['deck']+up]

    def polar(n, q):
        d = np.array(q[:2])-np.array(P[n]['xy']); return math.degrees(math.atan2(d[1], d[0])), float(np.linalg.norm(d))

    def around(n, a0, a1, r, avoid=None):
        """Arc from a0 to a1 at radius r, the way that does not cross the angle avoid (a hut)."""
        d = ((a1-a0+540) % 360)-180
        if avoid is not None:
            rel = ((avoid-a0+540) % 360)-180
            if 0 < rel < d or d < rel < 0: d = d-360 if d > 0 else d+360
        return arc(n, a0, a0+d, r)

    def room(n, inside, look_window, look_room, corner, walk=(), far=(1.15, -1.45, 1.95), mix=.45, enter=None):
        """From the deck into hut n by its door, a look round, and back out. Coming in and at the look, the camera holds
        in the top corner (lx, sy, height) by the door wall and turns with Cairo; going out it holds in the far corner,
        so he walks away from it to the door. It cuts in as he crosses the door and out as he leaves, as a game's room
        camera does. enter: a corner he walks in towards instead, cut to the door corner as he stops (where the door
        corner would look along the door wall)."""
        H = hut(n); w2 = HUT[0]/2; cam = ('room', *H(*corner), mix); out = ('room', *H(*far), mix)
        R.go([H(0, w2+.6), H(0, w2+.1)], 'run', .42, ('follow', -8))
        R.go([H(0, w2-.3)]+[H(*q) for q in walk]+[H(*inside)], 'run', .42, ('room', *H(*enter), 0.) if enter else cam)
        if enter: R.go([H(*inside)], 'run', .42, cam)
        R.stop(3.2, (0, H(*look_window, 1.3)), (1.7, H(*look_room, .9)))
        R.go([H(*q) for q in walk[::-1]]+[H(0, w2-.3), H(0, w2+.6)], 'run', .5, out)     # seen through the door
        curtains.append([*H(0, w2+.08, 1.5), .5])
        return polar(n, H(0, w2+.6))[0]

    # 1. the trail, the stepping stones and the entry steps
    st = [np.array(s) for s in lay['stones']]; back = st[0]+(st[0]-st[1])/np.linalg.norm(st[0]-st[1])*3.5
    es = lay['entry_stairs']; ex = es['x']; E = P['entry']; x0, y0 = E['xy']; ze = E['deck']
    R.go([back, back+(st[0]-back)*.05], 'walk', 1.)
    R.stop(2.8, (0, (x0, y0, ze+2.5)), (1.5, (x0-2, y0, ze+1.2)))
    R.go([*st[1:], es['foot'], (ex, es['top_y']-.15, ze)], 'run', .8, ('follow', -6))
    # 2. through the little hut (north door, south door) to the south porch and the view
    door = x0+1.2; curtains.extend([[door, y0+1.53, ze+1.54, .5], [door, y0-1.53, ze+1.54, .5]])
    cam = ('room', x0+1.75, y0-1.15, ze+1.9, .45)           # the south-east top corner: Cairo comes in towards it
    R.go([(ex+.1, y0+1.9, ze), (ex+.55, y0+1.82, ze), (door, y0+1.95, ze)], 'run', .45, ('follow', -8))
    R.go([(door, y0+1.4, ze), (door, y0+.35, ze)], 'run', .45, cam)
    R.stop(1.8, (0, (x0-.6, y0-.2, ze+1.5)), (1.0, (x0-1.4, y0+.8, ze+1.1)))
    R.go([(door, y0-.5, ze)], 'run', .45, cam)
    R.go([(door, y0-1.6, ze), (door-.2, y0-2.35, ze)], 'run', .45, ('follow', -8))
    R.stop(3.0, (0, (-139, 165, 73.5)), (1.6, (-131, 168, 76.0)))
    # 3. across to the Map room, inside, and round its deck to the sleeping nest
    b = bridge('entry', 'library'); R.go([b[0]+[.45, .55, 0]]+b, 'run', 1.)
    a_in = end_angle('library', 'entry'); H = hut('library'); a_door = polar('library', H(0, 2.3))[0]
    R.go(around('library', a_in, a_door, 3.3, P['library']['open']), 'run', .75)
    a_out = room('library', (0, -.55), (0, -3.5), (1.0, .4), (-1.15, 1.3, 1.95), enter=(1.15, -1.45, 1.95))
    R.go(around('library', a_out, end_angle('library', 'sleep'), 3.35, P['library']['open']), 'run', .9)
    R.go(bridge('library', 'sleep'), 'sprint', 1.)
    # 4. the sleeping nest: in along the rug to the hammock, out, round to the pulley bridge
    H = hut('sleep'); a_door = polar('sleep', H(0, 2.3))[0]
    R.go(around('sleep', end_angle('sleep', 'library'), a_door, 3.3, P['sleep']['open']), 'run', .75)
    a_out = room('sleep', (.6, -.75), (-.2, -3.5), (-.6, .3), (-1.15, 1.3, 1.95), walk=((.45, 1.35), (.55, .9)))
    R.go(around('sleep', a_out, end_angle('sleep', 'pulley'), 3.3, P['sleep']['open']), 'run', .9)
    R.go(bridge('sleep', 'pulley'), 'sprint', 1.)
    # 5. the pulley deck: a look at the crane and its basket
    pu = P['pulley']; a_in = end_angle('pulley', 'sleep'); a_to = end_angle('pulley', 'heart')
    a_mid = a_in-((a_in-a_to) % 360)*.45
    R.go(arc('pulley', a_in, a_mid, 2.2), 'run', .7)
    tip = np.array(pu['xy'])+unit(pu['open'])*3.75
    R.stop(2.2, (0, (*tip, pu['deck']+1.4)), (1.3, (*tip, pu['deck']-1.5)))
    R.go(arc('pulley', a_mid, a_to, 2.2, turn=-1), 'run', .8)
    R.go(bridge('pulley', 'heart'), 'sprint', 1.)
    # 6. the heart room: in by the south-west door, along the inner ring by the camphor to a look at the loft ladder
    # (from inside the ladder's radius the camera has the room behind Cairo), out round the ladder to the kitchen
    # Inside, the camera circles with him a little behind, high by the wall (the ring is too narrow for the chase
    # camera: its wall test would pull it in to his hair), and cuts in and out at the doors.
    a_in = end_angle('heart', 'pulley'); he = P['heart']; ring = ('ring', *he['xy'], 3.3, he['deck']+1.9, 48, .25)
    R.go([at('heart', a_in+4, 4.85), at('heart', 225, 4.75), at('heart', 225, 3.95)], 'run', .5, ('follow', -8))
    R.go([at('heart', 225, 3.4), at('heart', 222, 2.4)]+arc('heart', 222, 150, 2.35, turn=-1), 'run', .5, ring)
    R.stop(4.0, (0, at('heart', 108, 2.7, 1.5)), (1.5, at('heart', 70, 3.6, 2.5)), (2.9, at('heart', 0, 0, 1.7)))
    R.go(arc('heart', 150, 128, 2.35, turn=-1)+arc('heart', 118, 62, 3.25, turn=-1)+[at('heart', 45, 3.4)], 'run', .5, ring)
    # out through the curtain, seen from the kitchen bridge (on the narrow balcony the chase camera has no room)
    b = bridge('heart', 'kitchen'); back = ('room', *b[4][:2], b[4][2]+1.9, 0.)
    R.go([at('heart', 45, 4.2), at('heart', 45, 4.75), at('heart', end_angle('heart', 'kitchen')+4, 4.9)]+b[:2], 'run', .6, back)
    ap = layout_heart_wall*math.cos(math.radians(22.5))+.07
    curtains.extend([*at('heart', a, ap, 1.59), .5] for a in (45, 135, 225))
    R.go(b[2:], 'run', 1.)
    # 7. the kitchen: in to the stove, out, round to the boat bridge
    H = hut('kitchen'); a_door = polar('kitchen', H(0, 2.3))[0]
    R.go(around('kitchen', end_angle('kitchen', 'heart'), a_door, 3.3, P['kitchen']['open']), 'run', .8)
    a_out = room('kitchen', (.95, .95), (-.85, -1.1), (.3, -.1), (-1.15, 1.3, 1.95), walk=((.7, 1.35),), far=(1.2, -1.45, 2.0), mix=.3)
    R.go(around('kitchen', a_out, end_angle('kitchen', 'boat'), 3.3, P['kitchen']['open']), 'run', .9)
    R.go(bridge('kitchen', 'boat'), 'run', 1.)
    # 8. round the trunk on the open side of the boat room, with a look in under the upturned hull
    bo = P['boat']; c = np.array(bo['xy'])+unit(bo['open'])*(bo['trunk']+1.3); zb = bo['deck']
    a_in = end_angle('boat', 'kitchen'); a_to = end_angle('boat', 'slide')
    R.go(arc('boat', a_in, 168, 2.3, turn=1), 'run', .6, ('follow', -6))
    R.stop(2.4, (0, (*c, zb+1.5)), (1.4, (*(c+unit(bo['open']+90)*1.6), zb+1.1)))
    R.go(arc('boat', 168, a_to, 2.3, turn=1), 'run', .7)
    R.go(bridge('boat', 'slide'), 'sprint', 1.)
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
    R.go([at('lookout', a_in+3, 2.55), at('lookout', 355, 2.3), at('lookout', 335, 2.3), at('lookout', 312, 2.0), at('lookout', 300, 1.5),
          at('lookout', 312, rs), at('lookout', cr['start']-4, rs)], 'run', .7)
    # up the spiral the camera circles outside it; the last ten treads, from the crow's nest floor ahead of him,
    # looking down the stairwell (from outside it would be under the floor)
    top = cr['floor']; a_top = cr['start']+cr['steps']*cr['da']; hatch = ('ring', cx, cy, 2.2, top+1.75, 80, 0.)
    nest = ('follow', -6, top+1.9)             # under the canvas roof (cloth: no wall test stops the camera)
    R.go(helix[:-10], 'run', .75, ('orbit', cx, cy, 160, -20))
    R.go(helix[-10:]+[[cx+rs*math.cos(math.radians(a)), cy+rs*math.sin(math.radians(a)), top] for a in np.linspace(a_top, a_top+18, 4)],
         'run', .6, hatch)
    R.go([[cx+r*math.cos(math.radians(a)), cy+r*math.sin(math.radians(a)), top] for a, r in ((a_top+45, 1.6), (180, 1.9), (266, 2.0))],
         'run', .5, nest)
    R.stop(6.0, (0, (cx-6, cy-60, top-9)), (2.4, (cx+22, cy-50, top-12)), (4.2, (-131, 168, 79.0)))
    R.go([[cx+r*math.cos(math.radians(a)), cy+r*math.sin(math.radians(a)), top] for a, r in ((180, 1.7), (a_top+50, 1.55))],
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
    sys.path.insert(0, str(HERE)); import treehouse as views      # the capture look (SETTINGS, COMMANDS)
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
    sys.path.insert(0, str(HERE)); import treehouse_tour as tour
    out = WALK/take; done = json.loads((out/'done.json').read_text()); route = json.loads((WALK/'route.json').read_text())
    subprocess.run([sys.executable, str(REPO/'games/yorimichi/tools/mix_fight_film.py'), str(out), '--out', 'mix'], check=True)
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
