"""The tree house tour: one camera path through the whole house, filmed in the game and cut into a short film.

    python games/yorimichi/scenarios/treehouse_tour.py plan          # the shots, their times and clearances
    python games/yorimichi/scenarios/treehouse_tour.py film LABEL    # render the frames in the game
    python games/yorimichi/scenarios/treehouse_tour.py cut LABEL     # the film: build/yorimichi/treehouse/tour/LABEL.mp4

Fifteen shots follow the way a child finds the house: the glimpse from the trail, the stepping stones, through the
little hut (at a child's eye height, under the noren) onto the porch, over the bridges and into the rooms, down the
slide, up the lookout, the view from the crow's nest and the whole house from the air.

The game renders them in one run as one camera path: the trailer's `keys` ([seconds, camera xyz, target xyz, fov],
Blender metres, Catmull-Rom between keys). Every shot's first and last keys are doubled so the curve neither swings
into the next shot nor out of the last, and the jump between shots falls between two frames. Before each shot the
camera holds still for SETTLE seconds while light and anti-aliasing settle after the jump; `cut` drops those frames,
crossfades the shots, writes the place names in the corner and lays the countryside ambience and a wind bell under
the picture.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
import argparse, json, math, os, shutil, subprocess, sys
from pathlib import Path
import numpy as np
import importlib.util as _util
from village.layout import sample
from atelier import paths
# the reference views (scenarios/treehouse.py) give the room cameras and the crowns; loaded by path, since the
# region package is also called treehouse
_spec = _util.spec_from_file_location('treehouse_views', Path(__file__).resolve().parent/'treehouse.py')
V = _util.module_from_spec(_spec); _spec.loader.exec_module(V); L = V.L

FPS, SETTLE, FADE, EPS, WARMUP = 30, 1.5, .8, .002, 10.
OUT = yori.OUT/'treehouse'/'tour'
AMBIENCE = yori.OUT/'audio'/'combat'/'ambience_countryside'/'ambience_countryside_01.wav'   # audio.combat
BELL = paths.cache_dir('sonniss', 'combat')/'eiravaein_japanese_windbell.wav'                  # atelier fetch
PLAYER = (-95., 230.)          # the player waits on the trail, out of every shot


def unit(a):
    return np.array([math.cos(math.radians(a)), math.sin(math.radians(a))])


def shots(pl, h):
    """[(name, caption, keys)], keys [(t, camera, target, fov)] from t = 0 within the shot."""
    P = pl['places']; g = lambda x, y: float(sample(h, x, y)); out = []
    cams = {c['id']: c for c in V.cameras(pl, h)}

    def bridge(a, b, t, up=1.5):
        br = next(x for x in pl['bridges'] if {x['a'], x['b']} == {a, b})
        A, B = (br['start'], br['end']) if br['a'] == a else (br['end'], br['start'])
        A, B = np.array(A), np.array(B); q = A+(B-A)*t; q[2] += -4*br['sag']*t*(1-t)+up
        return q

    def centre(n, up):
        return np.array([*P[n]['xy'], P[n]['deck']+up])

    def pan(cam, tgt, deg, fwd=0.):
        """The target turned deg about the camera (left is positive), and the camera moved fwd metres toward it."""
        cam, tgt = np.array(cam, float), np.array(tgt, float); v = tgt-cam; c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        v2 = np.array([c*v[0]-s*v[1], s*v[0]+c*v[1], v[2]]); step = v2/np.linalg.norm(v2)*fwd
        return cam+step, cam+v2

    def along_bridge(a, b, t0, t1, look, secs, fov=70):
        return [(0, bridge(a, b, t0), look[0], fov), (secs, bridge(a, b, t1), look[1], fov)]

    def room(view, deg0, deg1, fwd, secs, fov0, fov1):
        c = cams[view]; p, t = c['camera_position'], c['camera_target']
        c0, t0 = pan(p, t, deg0); c1, t1 = pan(p, t, deg1, fwd)
        return [(0, c0, t0, fov0), (secs, c1, t1, fov1)]

    # 1. the glimpse: a few steps down the trail toward the gap in the bank, the little hut in its maple
    E = P['entry']; ex, ey = E['xy']; z = E['deck']; st = pl['stones']
    a = np.array(L.GLIMPSE); b = a+.6*(np.array(st[0][:2])-a)
    out.append(('glimpse', 'A gap in the bank', [(0, (*a, g(*a)+1.6), (ex, ey, z+1.6), 62), (7, (*b, g(*b)+1.6), (ex, ey+.5, z+1.3), 62)]))
    # 2. down the stepping stones and up the plank steps to the north door
    es = pl['entry_stairs']; door = (ex+1.2, ey+1.5)
    stair_z = lambda y: es['foot'][2]+(es['foot'][1]-y)/(es['foot'][1]-es['top_y'])*(z-es['foot'][2])
    out.append(('stones', '', [
        (0, (st[1][0], st[1][1], st[1][2]+1.5), (*door, z+1.3), 66),
        (3.5, (st[4][0], st[4][1], st[4][2]+1.5), (*door, z+1.2), 66),
        (7, (es['x']+.1, 201.5, stair_z(201.5)+1.45), (door[0], door[1]-.5, z+1.0), 66)]))
    # 3. through the little hut at a child's eye height and out onto the porch: the reveal
    x = ex+1.2
    out.append(('porch', 'The little hut', [
        (0, (x, ey+2.7, z+1.1), (x, ey-2.5, z+1.0), 72),
        (2.5, (x, ey+1.3, z+1.1), (x-.05, ey-4.0, z+.95), 72),
        (5, (x, ey, z+1.1), (x-.5, ey-8.5, z+.6), 74),
        (7.5, (x-.05, ey-1.5, z+1.15), (x-2.2, ey-16.5, z-.5), 76),
        (10.5, (x-.5, ey-3.2, z+1.5), (-138.5, 168, 74.8), 78)]))
    # 4. over the first rope bridge to the map room
    out.append(('bridge-map', '', along_bridge('entry', 'library', .12, .8, (centre('library', 1.4), centre('library', 1.1)), 6.5)))
    # 5. inside the map room
    out.append(('map-room', 'The map room', room('library-inside', 16, -14, .25, 6.5, 84, 80)))
    # 6. toward the heart room
    out.append(('bridge-heart', '', along_bridge('library', 'heart', .1, .78, (centre('heart', 2.4), centre('heart', 1.9)), 7, 72)))
    # 7. round the camphor inside the heart room (the loft ladder stands at 108 degrees, the hammock at 242-252)
    H = P['heart']; hx, hy = H['xy']; hz = H['deck']
    keys = []
    for i, ang in enumerate(np.linspace(170, 115, 4)):
        keys.append((8*i/3, (*(np.array([hx, hy])+unit(ang)*3.3), hz+1.55), (*(np.array([hx, hy])+unit(ang-145)*3.3), hz+1.2), 88))
    out.append(('heart-room', 'The heart room', keys))
    # 8, 9. the kitchen and the sleeping nest
    out.append(('kitchen', 'The kitchen', room('kitchen-inside', 14, -16, .2, 6, 84, 80)))
    out.append(('sleep', 'The sleeping nest', room('sleep-inside', -12, 14, .2, 6, 84, 80)))
    # 10. over to the boat room
    out.append(('boat', 'The boat room', along_bridge('kitchen', 'boat', .15, .85, (centre('boat', 1.5), centre('boat', 1.2)), 6, 72)))
    # 11. down the spiral slide, sitting in the chute
    path = pl['slide']['path']; n = len(path); keys = []
    idx = list(range(3, n, 12))+[n-1]
    for i in idx:
        c = np.array(path[i][:3])+[0, 0, 1.0]
        j = min(i+10, n-1); t = np.array(path[j][:3])+[0, 0, .85]
        if j == n-1:          # past the end: straight on along the run-out
            d = np.array(path[-1][:3])-np.array(path[-4][:3]); t = np.array(path[-1][:3])+d/np.linalg.norm(d)*4*(1+(i-idx[-2])/12)+[0, 0, .85]
        keys.append((7.5*(i-idx[0])/(idx[-1]-idx[0]), c, t, 80))
    out.append(('slide', 'The slide', keys))
    # 12. to the chime tree
    out.append(('chimes', 'The chime tree', along_bridge('slide', 'chimes', .2, .9, (centre('chimes', 1.8), centre('chimes', 1.5)), 5.5, 72)))
    # 13. up past the lookout's spiral stairs, outside the tower, to the crow's nest
    lk = P['lookout']; lx, ly = lk['xy']; f = pl['crow']['floor']
    a0, r0 = lookout_arc(pl, h)
    keys = []
    for i, s in enumerate(np.linspace(0, 1, 4)):
        ang = a0+45*s; r = r0-1.0*s; zc = lk['deck']+1.5+(f+2.2-lk['deck']-1.5)*s
        keys.append((8.5*s, (*(np.array([lx, ly])+unit(ang)*r), zc), (lx, ly, zc-.8-.6*s), 70))
    out.append(('lookout', 'The lookout', keys))
    # 14. the crow's nest: from the sea round to the whole house
    heart = np.array([-131., 168., 79.])
    c0 = np.array([lx+.2, ly+.9, f+1.7]); c1 = np.array([lx+1.6*math.cos(math.radians(330)), ly+1.6*math.sin(math.radians(330)), f+1.7])
    sea = math.degrees(math.atan2(-60, -6)) % 360; home = math.degrees(math.atan2(heart[1]-c1[1], heart[0]-c1[0])) % 360 + 360
    keys = []
    for i, s in enumerate(np.linspace(0, 1, 5)):
        c = c0+(c1-c0)*(s*s*(3-2*s)); ang = sea+(home-sea)*s; dist = 60+(np.linalg.norm(heart[:2]-c1[:2])-60)*s
        t = np.array([*(c[:2]+unit(ang)*dist), (f-9)+(heart[2]-(f-9))*s]) if i < 4 else heart
        keys.append((10*s, c, t, 78))
    out.append(('crow', "The crow's nest", keys))
    # 15. the whole house from the air, rising away to the south
    out.append(('aerial', 'The tree house', [
        (0, (-127, 147, 95), (-133, 168, 75), 60), (5.5, (-127.5, 127, 104), (-133.5, 168, 72.5), 57),
        (11, (-128, 104, 114), (-134, 168, 71), 55)]))
    return out


def lookout_arc(pl, h, trees=None):
    """The start angle and radius of the rise past the lookout: the arc (45 degrees, 7.5 to 6.5 m out) whose
    camera stays furthest from crowns and bridges, facing the house from the south-west."""
    trees = trees if trees is not None else TREES
    lk = pl['places']['lookout']; lx, ly = lk['xy']; f = pl['crow']['floor']
    links = [math.degrees(math.atan2(pl['places'][o]['xy'][1]-ly, pl['places'][o]['xy'][0]-lx)) % 360
             for br in pl['bridges'] for o in (br['a'], br['b']) if 'lookout' in (br['a'], br['b']) and o != 'lookout']
    best = None
    for a0 in range(150, 290, 5):
        for r0 in (7.5, 8.5):
            m = 99.
            for s in np.linspace(0, 1, 9):
                ang = a0+45*s; r = r0-s; zc = lk['deck']+1.5+(f+2.2-lk['deck']-1.5)*s
                p = np.array([lx, ly])+unit(ang)*r
                m = min(m, crown_clearance((*p, zc), trees))
                if zc < lk['deck']+4: m = min(m, min(abs(((ang-l+540) % 360)-180) for l in links)/10)
            if best is None or m > best[0]: best = (m, a0, r0)
    return best[1], best[2]


def crown_clearance(p, trees):
    m = 99.
    for x, y, lo, hi, reach in trees:
        if lo-1 < p[2] < hi+1: m = min(m, math.hypot(x-p[0], y-p[1])-reach)
    return m


def timeline(shot_list):
    """The game's keys and each shot's (name, caption, start, end) in film seconds."""
    keys, spans, t = [], [], 0.
    def key(tt, c, g, fov):
        keys.append([round(tt, 4), *[round(float(v), 3) for v in c], *[round(float(v), 3) for v in g], fov])
    for name, caption, ks in shot_list:
        c0, g0, f0 = ks[0][1], ks[0][2], ks[0][3]
        if keys: key(t+EPS, c0, g0, f0)             # the jump, a hair after the last shot's final frame
        key(t+2*EPS, c0, g0, f0)
        start = math.ceil((t+SETTLE)*FPS)/FPS         # the hold: light and anti-aliasing settle
        key(start-EPS, c0, g0, f0); key(start, c0, g0, f0)
        for dt, c, g, fov in ks[1:]: key(start+dt, c, g, fov)
        end = start+ks[-1][0]; key(end+EPS/2, ks[-1][1], ks[-1][2], ks[-1][3])
        spans.append((name, caption, start, end)); t = end
    return keys, spans, t


def curve(keys, T):
    """AJapanWorld's trailer path (JapanTrailer.cpp): the camera and target at T seconds."""
    K = lambda i: keys[min(max(i, 0), len(keys)-1)]
    i = 0
    while i < len(keys)-2 and K(i+1)[0] <= T: i += 1
    u = min(max((T-K(i)[0])/max(K(i+1)[0]-K(i)[0], 1e-3), 0.), 1.)
    def c(o):
        p0, p1, p2, p3 = (np.array(K(j)[o:o+3]) for j in (i-1, i, i+1, i+2))
        return .5*(2*p1+(p2-p0)*u+(2*p0-5*p1+4*p2-p3)*u*u+(3*p1-p0-3*p2+p3)*u**3)
    return c(1), c(4)


def load():
    h = np.load(yori.OUT/'heightmap.npy'); world = json.loads((yori.OUT/'world.json').read_text())
    return world['treehouse'], h, V.forest(world, (-190, -80, 100, 230))


def plan():
    global TREES
    pl, h, TREES = load()
    keys, spans, total = timeline(shots(pl, h))
    for name, caption, a, b in spans:
        m = min(crown_clearance(curve(keys, T)[0], TREES) for T in np.arange(a, b, .1))
        print(f'{name:12s} {a:6.2f} {b:6.2f}  {b-a:4.1f} s  nearest crown {m:5.2f} m  {caption}')
    print(f'{len(keys)} keys, {total:.1f} s rendered, film {sum(b-a for *_, a, b in spans)-FADE*(len(spans)-1):.1f} s')
    return pl, h, keys, spans, total


def film(label):
    pl, h, keys, spans, total = plan()
    folder = OUT/label
    if folder.exists(): raise SystemExit(f'{folder} exists: labels are never reused')
    folder.mkdir(parents=True)
    spec = dict(kind='world', seconds=round(total+.2, 3), capture_fps=FPS, format='jpg', width=1920, height=1080,
                warmup=WARMUP, events=[], road_index=0, fov=70, keys=keys,
                player_position=[*PLAYER, float(sample(h, *PLAYER))+.3])
    (folder/'tour.json').write_text(json.dumps(spec)+'\n')
    (folder/'shots.json').write_text(json.dumps([dict(name=n, caption=c, start=a, end=b) for n, c, a, b in spans], indent=1)+'\n')
    from atelier.build import Context
    ctx = Context('yorimichi'); saved = ctx.uproject.parent/'Saved'/'settings.txt'; backup = folder/'settings.before.txt'
    if saved.exists(): shutil.copy(saved, backup)
    command = [str(ctx.unreal_app), str(ctx.uproject),
               '-game', '-RenderOffscreen', '-ForceRes', '-resx=1920', '-resy=1080', f'-trailershot={folder/"tour.json"}',
               f'-reviewdir={folder}', '-UseFixedTimeStep', '-FPS=60', '-unattended', '-nosplash', '-stdout', '-noshaderworker',
               f'-set={V.SETTINGS};show_fps=0', f'-ExecCmds={V.COMMANDS}', f'-abslog={folder/"game.log"}']
    try:
        subprocess.run([sys.executable, '-m', 'atelier.safety.guarded', '--report', str(folder/'guard'), '--timeout', '5400',
                        '--purpose', f'Tree house tour {label}', '--', *command], check=True, stdout=subprocess.DEVNULL,
                       env={**os.environ, 'PYTHONPATH': str(yori.REPO/'platform'/'studio')})
    finally:
        if backup.exists(): shutil.copy(backup, saved)
    frames = sorted(folder.glob('frame_*.jpg'))
    print(len(frames), 'frames;', next((l.split('Display: ')[-1] for l in (folder/'game.log').read_text(errors='replace').splitlines() if 'TRAILER SHOT COMPLETE' in l), 'no completion line'))


def cut(label, captions=True):
    from PIL import Image, ImageDraw, ImageFont
    folder = OUT/label; spans = json.loads((folder/'shots.json').read_text())
    frames = {int(p.stem.split('_')[1]): p for p in folder.glob('frame_*.jpg')}
    font = next((ImageFont.truetype(str(f), 38) for f in (Path('/System/Library/Fonts/Supplemental/Georgia Italic.ttf'),
                 Path('/System/Library/Fonts/Supplemental/Georgia.ttf')) if f.exists()), ImageFont.load_default())
    work = folder/'cut'; shutil.rmtree(work, ignore_errors=True); work.mkdir()
    pieces = [[frames[i] for i in range(round(s['start']*FPS), round(s['end']*FPS)+1) if i in frames] for s in spans]
    n_fade = round(FADE*FPS); out = []; bells = []
    for k, (s, pics) in enumerate(zip(spans, pieces)):
        start = len(out)-(n_fade if k else 0)
        if s['name'] in ('chimes', 'crow'): bells.append(start/FPS+1.2)
        for j, p in enumerate(pics):
            at = start+j; cap = (s['caption'], j, len(pics)) if captions and s['caption'] else None
            if at < len(out): out[at] = ('mix', out[at], (p, cap), (at-start+1)/(n_fade+1))
            else: out.append(('one', (p, cap)))
    def render(item):
        im = Image.open(item[0]).convert('RGB')
        if item[1]:
            text, j, n = item[1]; a = min(1., (j-.6*FPS)/(.6*FPS), (n-j-.9*FPS)/(.5*FPS))
            if a > 0:
                layer = Image.new('RGBA', im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
                d.text((72, im.height-104), text, font=font, fill=(0, 0, 0, int(110*a)), stroke_width=0)
                d.text((70, im.height-106), text, font=font, fill=(255, 246, 228, int(235*a)))
                im = Image.alpha_composite(im.convert('RGBA'), layer).convert('RGB')
        return im
    total = len(out)
    for i, item in enumerate(out):
        im = render(item[1]) if item[0] == 'one' else Image.blend(render(item[1][1]), render(item[2]), item[3])
        fade = min(1., i/(1.*FPS), (total-1-i)/(1.2*FPS))
        if fade < 1: im = Image.blend(Image.new('RGB', im.size), im, max(fade, 0.))
        im.save(work/f'{i:05d}.jpg', quality=94)
    seconds = total/FPS; film = OUT/f'{label}.mp4'
    audio = [('-stream_loop', '-1', '-i', str(AMBIENCE))]+[('-i', str(BELL)) for _ in bells]
    mix = '[1:a]volume=0.55,afade=t=in:d=1.5,afade=t=out:st=%.2f:d=2[amb]' % (seconds-2)
    parts = ['[amb]']
    for i, t in enumerate(bells):
        mix += f';[{i+2}:a]aresample=48000,volume=0.8,adelay={int(t*1000)}|{int(t*1000)}[b{i}]'; parts.append(f'[b{i}]')
    mix += ';'+''.join(parts)+f'amix=inputs={len(parts)}:normalize=0,atrim=0:{seconds:.3f}[a]'
    cmd = ['ffmpeg', '-y', '-v', 'error', '-framerate', str(FPS), '-i', str(work/'%05d.jpg')]
    for a in audio: cmd += list(a)
    cmd += ['-filter_complex', mix, '-map', '0:v', '-map', '[a]', '-c:v', 'libx264', '-preset', 'slow', '-crf', '18',
            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', '-shortest', str(film)]
    subprocess.run(cmd, check=True)
    print(film, f'{seconds:.1f} s, {total} frames, {film.stat().st_size/1e6:.1f} MB')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('step', choices=('plan', 'film', 'cut')); ap.add_argument('label', nargs='?')
    ap.add_argument('--no-captions', action='store_true')
    a = ap.parse_args()
    if a.step == 'plan': plan()
    elif not a.label: raise SystemExit('film and cut need a LABEL')
    elif a.step == 'film': film(a.label)
    else: cut(a.label, not a.no_captions)


TREES = []
if __name__ == '__main__':
    main()
