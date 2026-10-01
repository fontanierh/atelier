"""The Mega Park tour: one camera path over and through the Super Ultra Mega Park, filmed in the game and cut into a
short film.

    python games/yorimichi/scenarios/megapark_tour.py plan                # the shots, their times and clearances
    python games/yorimichi/scenarios/megapark_tour.py film LABEL          # render the frames in the game
    python games/yorimichi/scenarios/megapark_tour.py film LABEL --preview  # a few small frames a second, to check
    python games/yorimichi/scenarios/megapark_tour.py cut LABEL           # the film: build/yorimichi/megapark/tour/LABEL.mp4

The shots follow the way a skater finds the park: over the west hills to the rock in the autumn forest, low over
the canopy to its south face, down the roll-in from the start deck behind a rider's line, past the samurai
billboard over the canyon, along the oni ads over the snake bowl, round the concrete bowls, up to 寄り道 on the
cliff, and away into the air with the volcano behind.

The camera path is the tree house tour's (scenarios/treehouse_tour.py): the trailer's `keys` in Blender metres,
Catmull-Rom between keys, every shot settled still for a moment after each jump and the settling frames cut out.
`plan` prints each shot's nearest park surface, ground and tree crown, so no path runs through rock or leaves.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
import argparse, json, math, os, shutil, subprocess, sys
from functools import lru_cache
from pathlib import Path
import numpy as np
import importlib.util as _util
from megapark import placement, plants
_spec = _util.spec_from_file_location('treehouse_tour', Path(__file__).resolve().parent/'treehouse_tour.py')
T = _util.module_from_spec(_spec); _spec.loader.exec_module(T); V = T.V

FPS = T.FPS
OUT = yori.OUT/'megapark'/'tour'
PLAYER = (1060., 1130., 134.)  # the player waits at the foothills zone, far out of every shot
TRACE = [(-56.0, 1325.4), (-68.7, 1327.3), (-78.3, 1324.0), (-91.3, 1316.5), (-114.0, 1305.8), (-137.8, 1307.0)]
SAMURAI = (np.array([4.3, 1262.9, 124.6]), np.array([-.91, .41]))       # the billboard's centre and facing
ONI = (np.array([-189.2, 1390.7, 69.3]), np.array([-154., 1411.1, 69.3]), np.array([.5, -.87]))
SIGN = np.array([14.7, 1333.5, 145.7])                                  # 寄り道, facing west over the deck
SUMMIT = np.array([550., 1930., 480.])


@lru_cache(maxsize=1)
def surface():
    """The park's collision as points every half metre in island metres, binned by 4 m cell, and the highest surface
    on a 1 m grid."""
    pts = placement.surface_samples(placement.place(placement.collision_triangles()), .5)
    bins = {}
    for k, p in zip(map(tuple, np.floor(pts[:, :2]/4).astype(int)), pts):
        bins.setdefault(k, []).append(p)
    return {k: np.array(v) for k, v in bins.items()}, placement.footprint(1.)


def park_top(x, y):
    """The highest park surface under (x, y), or -inf off the park."""
    _, (x0, y0, cell, _, top, _) = surface()
    i, j = int((y-y0)//cell), int((x-x0)//cell)
    if 0 <= i < top.shape[0] and 0 <= j < top.shape[1] and np.isfinite(top[i, j]): return float(top[i, j])
    return -math.inf


@lru_cache(maxsize=1)
def crowns():
    """Tree crowns round the park as (x, y, bottom, top, radius) rows: the island's trees and the park's own."""
    city = json.loads((yori.OUT/'hidamari'/'city.json').read_text())['instances']
    rows = []
    for name, items in city.items():
        if not name.startswith(('Tree', 'HD_NorthTree')): continue
        size = plants.MESHES.get(name, (13., 3.))
        for x, y, z, _, s in items:
            if -1000 < x < 400 and 800 < y < 1800: rows.append((x, y, z+.25*size[0]*s, z+size[0]*s, size[1]*s))
    for name, items in plants.trees().items():
        size = plants.MESHES.get(name, (13., 3.))
        for p in items:
            x, y, z = placement.native_to_island(p[:3]); s = p[4]
            rows.append((x, y, z+.25*size[0]*s, z+size[0]*s, size[1]*s))
    return np.array(rows)


def ground(x, y):
    from hidamari.layout import north_height
    return float(north_height(x, y))


def above(x, y, h):
    """A point h metres above the highest of the ground, the park and the tree crowns at (x, y)."""
    c = crowns(); near = np.hypot(c[:, 0]-x, c[:, 1]-y) < c[:, 4]+2
    return np.array([x, y, max(ground(x, y), park_top(x, y), c[near, 3].max() if near.any() else -math.inf)+h])


def clearance(p):
    """(park, ground, crown): metres from p to the nearest park surface, the ground below and the nearest crown."""
    bins, _ = surface(); i, j = int(p[0]//4), int(p[1]//4)
    near = [bins[(a, b)] for a in range(i-2, i+3) for b in range(j-2, j+3) if (a, b) in bins]
    park = float(np.linalg.norm(np.concatenate(near)-p, axis=1).min()) if near else 99.
    c = crowns(); band = (c[:, 2]-1 < p[2]) & (p[2] < c[:, 3]+1)
    crown = float((np.hypot(c[band, 0]-p[0], c[band, 1]-p[1])-c[band, 4]).min()) if band.any() else 99.
    return min(park, 99.), p[2]-ground(p[0], p[1]), min(crown, 99.)


def ride(points, eye, step=2.5):
    """Points every `step` metres along the polyline, `eye` metres out from the park surface under them along its
    normal (the roll-in is near vertical at its steepest, where straight up would be inside the wall)."""
    p = np.array(points, float); seg = np.linalg.norm(np.diff(p, axis=0), axis=1); s = np.r_[0, np.cumsum(seg)]
    out = []
    for d in np.arange(0, s[-1]+1e-6, step):
        k = min(np.searchsorted(s, d, 'right')-1, len(p)-2); u = (d-s[k])/seg[k]; x, y = p[k]+(p[k+1]-p[k])*u
        n = np.array([park_top(x-2, y)-park_top(x+2, y), park_top(x, y-2)-park_top(x, y+2), 4.])
        q = np.array([x, y, park_top(x, y)])+n/np.linalg.norm(n)*eye; q[2] = max(q[2], park_top(*q[:2])+.7*eye)
        out.append(q)
    return np.array(out), s[-1]


def chase(points, back, ahead, high, secs, step=2.):
    """Keys along the plan polyline: the camera `back` metres behind and `high` above the park under it, looking at the
    surface `ahead` metres on, accelerating evenly from rest over `secs` seconds. Down a wall the camera sinks no
    faster than it moves on, so it cranes down after the line instead of hugging the wall."""
    p = np.array(points, float); seg = np.linalg.norm(np.diff(p, axis=0), axis=1); s = np.r_[0, np.cumsum(seg)]
    def at(d):
        k = int(np.clip(np.searchsorted(s, d, 'right')-1, 0, len(p)-2)); u = (d-s[k])/seg[k]
        return p[k]+(p[k+1]-p[k])*u     # straight on past either end
    keys = []; z = -math.inf
    for d in np.arange(0, s[-1]+1e-6, step):
        c, here, t = at(d-back), at(d), at(d+ahead)
        z = max(max(park_top(*c), park_top(*here))+high, z-step)
        keys.append((secs*math.sqrt(d/s[-1]), (*c, z), (*t, park_top(*t)+1.), 74))
    return keys


def shots():
    """[(name, caption, keys)], keys [(t, camera, target, fov)] from t = 0 within the shot."""
    out = []
    park = np.array([-130., 1320., 95.])
    # 1. over the west hills: the rock rises out of the autumn forest
    out.append(('hills', 'Over the west hills', [
        (0, (-720, 1060, 300), (-130, 1335, 100), 52), (9, (-470, 1170, 225), park, 52)]))
    # 2. low over the canopy to the park's south face
    a, b = above(-175, 960, 14), above(-165, 1090, 14)
    out.append(('canopy', '', [(0, a, (-140, 1300, 85), 62), (8, b, (-135, 1300, 92), 62)]))
    # 3. down the roll-in from the start deck: a chase camera behind and above the line, looking down it, so the lip and
    # the drop below it read; slow off the deck, faster down the wall, as a rider gathers speed
    out.append(('drop', 'The roll-in', chase(TRACE, back=9., ahead=11., high=5.5, secs=8.)))
    # 4. past the samurai billboard over the canyon
    c, f = SAMURAI; side = np.array([-f[1], f[0]])
    out.append(('samurai', 'The canyon', [
        (0, (*(c[:2]+f*30-side*14), c[2]-6), c, 48), (7, (*(c[:2]+f*24+side*8), c[2]-3), c+(0, 0, -1), 44)]))
    # 5. along the oni ads over the snake bowl
    o1, o2, f = ONI
    out.append(('oni', 'The snake bowl', [
        (0, (*(o1[:2]+f*18), o1[2]+2), o1, 58), (7, (*(o2[:2]+f*18), o2[2]+2), o2, 58)]))
    # 6. round the concrete bowls, over their open east side
    centre = np.array([-98., 1240., 77.]); keys = []
    for k, ang in enumerate(np.linspace(-40, 60, 5)):
        p = centre[:2]+30*np.array([math.cos(math.radians(ang)), math.sin(math.radians(ang))])
        keys.append((9*k/4, (*p, 98-2*k/4), centre, 62))
    out.append(('bowls', 'The bowls', keys))
    # 7. up over the upper deck to 寄り道 on the cliff, stopping short of the deck's banners
    out.append(('sign', '', [(0, (-44, 1352, 120.5), SIGN+(0, 0, -4), 58), (6, (-36, 1344, 125), SIGN+(0, 0, -2), 54)]))
    # 8. away into the air, the volcano behind the park
    out.append(('aerial', 'Super Ultra Mega Park', [
        (0, (-260, 1130, 150), (-120, 1320, 90), 60), (6, (-340, 1030, 230), (-60, 1420, 120), 58),
        (12, (-430, 930, 330), (90, 1640, 220), 56)]))
    return out


def plan():
    keys, spans, total = T.timeline(shots())
    for name, caption, a, b in spans:
        worst = [99., 99., 99.]
        for t in np.arange(a, b, .1):
            for i, v in enumerate(clearance(T.curve(keys, t)[0])): worst[i] = min(worst[i], v)
        print(f'{name:8s} {a:6.2f} {b:6.2f}  {b-a:4.1f} s  park {worst[0]:5.1f} m  ground {worst[1]:6.1f} m  '
              f'crown {worst[2]:5.1f} m  {caption}')
    print(f'{len(keys)} keys, {total:.1f} s rendered, film {sum(b-a for *_, a, b in spans)-T.FADE*(len(spans)-1):.1f} s')
    return keys, spans, total


def film(label, preview=False):
    keys, spans, total = plan()
    folder = OUT/label
    if folder.exists(): raise SystemExit(f'{folder} exists: labels are never reused')
    folder.mkdir(parents=True)
    w, h, fps = (960, 540, 2) if preview else (1920, 1080, FPS)
    spec = dict(kind='world', seconds=round(total+.2, 3), capture_fps=fps, format='jpg', width=w, height=h,
                warmup=T.WARMUP, events=[], road_index=0, fov=70, keys=keys, player_position=list(PLAYER))
    (folder/'tour.json').write_text(json.dumps(spec)+'\n')
    (folder/'shots.json').write_text(json.dumps([dict(name=n, caption=c, start=a, end=b) for n, c, a, b in spans], indent=1)+'\n')
    from atelier.build import Context
    ctx = Context('yorimichi'); saved = ctx.uproject.parent/'Saved'/'settings.txt'; backup = folder/'settings.before.txt'
    if saved.exists(): shutil.copy(saved, backup)
    command = [str(ctx.unreal_app), str(ctx.uproject),
               '-game', '-RenderOffscreen', '-ForceRes', f'-resx={w}', f'-resy={h}', f'-trailershot={folder/"tour.json"}',
               f'-reviewdir={folder}', '-UseFixedTimeStep', '-FPS=60', '-unattended', '-nosplash', '-stdout', '-noshaderworker',
               f'-set={V.SETTINGS};show_fps=0', f'-ExecCmds={V.COMMANDS}', f'-abslog={folder/"game.log"}']
    try:
        subprocess.run([sys.executable, '-m', 'atelier.safety.guarded', '--report', str(folder/'guard'), '--timeout', '5400',
                        '--purpose', f'Mega Park tour {label}', '--', *command], check=True, stdout=subprocess.DEVNULL,
                       env={**os.environ, 'PYTHONPATH': str(yori.REPO/'platform'/'studio')})
    finally:
        if backup.exists(): shutil.copy(backup, saved)
    frames = sorted(folder.glob('frame_*.jpg'))
    print(len(frames), 'frames;', next((l.split('Display: ')[-1] for l in (folder/'game.log').read_text(errors='replace').splitlines() if 'TRAILER SHOT COMPLETE' in l), 'no completion line'))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('step', choices=('plan', 'film', 'cut')); ap.add_argument('label', nargs='?')
    ap.add_argument('--preview', action='store_true'); ap.add_argument('--no-captions', action='store_true')
    a = ap.parse_args()
    if a.step == 'plan': plan()
    elif not a.label: raise SystemExit('film and cut need a LABEL')
    elif a.step == 'film': film(a.label, a.preview)
    else: T.cut(a.label, not a.no_captions, OUT)


if __name__ == '__main__':
    main()
