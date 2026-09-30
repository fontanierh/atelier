"""The tree house's reference views: every place and room, the trail glimpse, the porch reveal, the crow's nest both
ways and two aerials, captured in the game and set beside their Sunburst references.

    python games/yorimichi/scenarios/treehouse.py LABEL [view ...] [--dry-run]

Writes build/yorimichi/treehouse/captures/LABEL/<view>.png through the guarded runner (1920 x 1080, the desktop
quality settings, player and HUD hidden), LABEL-sheet.jpg, and LABEL-compare/<view>.jpg with the capture on the left
and its reference (assets/treehouse/refs) on the right: the pairs the build was hill-climbed against. A label is never
reused. Cameras are Blender metres, placed from the layout: each place has an approach view from one of its bridges
with its neighbours behind, and each room an inside view from the doorway corner.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
import json, math, os, subprocess, sys
import importlib.util as _util
import numpy as np
from village.layout import sample
# This file is itself named treehouse: load the region's layout by path, not as the treehouse package.
_spec = _util.spec_from_file_location('treehouse_layout', yori.REGIONS/'treehouse'/'layout.py')
L = _util.module_from_spec(_spec); _spec.loader.exec_module(L)

EYE = 1.55
CAPTURES = yori.OUT/'treehouse'/'captures'
REFS = yori.ASSETS/'treehouse'/'refs'
SETTINGS = ('performance=1;render_scale=100;painterly=0.35;paint_radius=2;toon=0;outline=0;exposure=0.9;saturation=1;'
            'wind=3.5;sun_height=48;sun_yaw=15;desktop=1')
COMMANDS = 'r.DynamicRes.OperationMode 0,r.ScreenPercentage 100,r.RHISetGPUCaptureOptions 0'


def unit(a):
    return np.array([math.cos(math.radians(a)), math.sin(math.radians(a))])


def forest(world, box):
    """Standing tree crowns near the build: (x, y, crown low, crown high, reach), from the integrated world."""
    x0, x1, y0, y1 = box; out = []
    for k, v in world['instances'].items():
        if not k.startswith('Tree'): continue
        d = L.SPECIES.get(k, (5., 2., 9., 3.))
        out += [(x, y, z+d[1]*s, z+d[2]*s, d[3]*s*.85) for x, y, z, _, s in v if x0 < x < x1 and y0 < y < y1]
    return out


def open_spot(centre, target, h, trees, radii=(9, 11)):
    """The ground spot around centre whose eye line to target stays furthest from any crown (the forest is dense)."""
    best = None
    for r in radii:
        for a in range(0, 360, 10):
            p = np.array(centre)+unit(a)*r; eye = np.array([*p, float(sample(h, *p))+EYE]); m = 99.
            for x, y, lo, hi, reach in trees:
                ab = target[:2]-eye[:2]; t = np.clip(((x-eye[0])*ab[0]+(y-eye[1])*ab[1])/(ab@ab), 0, 1)
                q = eye+(target-eye)*t
                if lo < q[2] < hi: m = min(m, math.hypot(x-q[0], y-q[1])-reach)
                m = min(m, math.hypot(x-p[0], y-p[1])-reach)
            if best is None or m > best[0]: best = (m, p)
    return best[1]


def cameras(pl, h, trees=None):
    P = pl['places']; out = []
    def add(i, pos, target, fov=75):
        out.append(dict(id=i, camera_position=[round(float(v), 3) for v in pos], camera_target=[round(float(v), 3) for v in target], fov=fov))

    def on_bridge(a, b, t, up=EYE):
        br = next(x for x in pl['bridges'] if {x['a'], x['b']} == {a, b})
        A, B = (br['start'], br['end']) if br['a'] == a else (br['end'], br['start'])
        A, B = np.array(A), np.array(B); q = A+(B-A)*t; q[2] += -4*br['sag']*t*(1-t)+up
        return q

    def centre(n, up):
        return [*P[n]['xy'], P[n]['deck']+up]

    def hut(n):
        p = P[n]; u = unit(p['open']); v = np.array([-u[1], u[0]]); d2, w2 = L.HUT[1]/2, L.HUT[0]/2
        diffs = [((l['angle']-p['open']+540) % 360)-180 for l in p['links']]
        side = 1 if min(diffs, key=abs) > 0 else -1
        c = np.array(p['xy'])+u*(p['trunk']+.3+d2)
        return c, u, v*side, d2, w2

    E = P['entry']; ex, ey = E['xy']; z = E['deck']
    g = float(sample(h, *L.GLIMPSE))
    add('entry-glimpse', (*L.GLIMPSE, g+EYE), (ex, ey, z+1.4), 70)
    add('entry-inside', (ex+1.82, ey+1.33, z+1.5), (ex-.43, ey-1.33, z+1.15), 90)
    add('entry-reveal', (ex+.4, ey-2.6, z+EYE), (-139, 165, 72.5), 80)
    add('library-approach', on_bridge('entry', 'library', .2), centre('library', 1.4), 70)
    for n in ('library', 'kitchen', 'sleep'):
        c, u, s, d2, w2 = hut(n); z = P[n]['deck']
        pos = c-u*(d2-.35)+s*(w2-.25); tgt = c+u*d2*.35-s*w2   # in the corner by the door, looking across the room to the window
        add(f'{n}-inside', (*pos, z+1.55), (*tgt, z+1.0), 84)
    add('heart-approach', on_bridge('library', 'heart', .35), centre('heart', 2.2), 72)
    hx, hy = P['heart']['xy']; z = P['heart']['deck']
    add('heart-inside', (*(np.array([hx, hy])+unit(135)*3.55), z+1.55), (*(np.array([hx, hy])+unit(350)*3.3), z+1.15), 90)
    add('kitchen-approach', on_bridge('heart', 'kitchen', .12), centre('kitchen', 1.4), 72)
    add('sleep-approach', on_bridge('library', 'sleep', .3), centre('sleep', 1.4), 72)
    add('boat-approach', on_bridge('kitchen', 'boat', .3), centre('boat', 1.4), 72)
    b = P['boat']; u = unit(b['open']); t = unit(b['open']+90); c = np.array(b['xy'])+u*(b['trunk']+1.3)
    add('boat-inside', (*(c-t*3.1+u*.5), b['deck']+1.35), (*(c+t*1.2), b['deck']+1.35), 85)
    add('slide-approach', on_bridge('boat', 'slide', .3), centre('slide', -2.5), 75)
    s = pl['slide']; tgt = np.array([*s['center'][:2], P['slide']['deck']-4])
    foot = open_spot(s['center'][:2], tgt, h, trees or [])
    add('slide-foot', (*foot, float(sample(h, *foot))+EYE), tgt, 78)
    add('pulley-approach', on_bridge('heart', 'pulley', .4), centre('pulley', 1.6), 72)
    add('chimes-approach', on_bridge('heart', 'chimes', .6), centre('chimes', 1.4), 72)
    add('lookout-approach', on_bridge('chimes', 'lookout', .05), centre('lookout', 3.5), 80)
    lx, ly = P['lookout']['xy']; f = pl['crow']['floor']
    add('crow-sea', (lx+.2, ly+.9, f+1.75), (lx-6, ly-60, f-9), 80)
    add('crow-back', (lx+1.6*math.cos(math.radians(330)), ly+1.6*math.sin(math.radians(330)), f+1.7), (-131, 168, 79.0), 80)
    add('overview-south', (-128, 100, 112), (-134, 168, 70), 55)
    add('overview-east', (-68, 158, 102), (-135, 168, 70), 55)
    return out


def sheet(folder, out, columns=4, width=640):
    from PIL import Image
    thumbs = [Image.open(p).convert('RGB') for p in sorted(folder.glob('*.png'))]
    thumbs = [t.resize((width, round(width*t.height/t.width))) for t in thumbs]
    cell = max(t.height for t in thumbs); rows = (len(thumbs)+columns-1)//columns
    canvas = Image.new('RGB', (columns*width, rows*cell), (18, 18, 20))
    for i, t in enumerate(thumbs): canvas.paste(t, ((i % columns)*width, (i//columns)*cell))
    canvas.save(out, quality=88)


def compare(folder, label, width=560):
    """Each capture beside its reference, one file per view and all of them stacked."""
    from PIL import Image, ImageDraw
    out = CAPTURES/f'{label}-compare'; out.mkdir(parents=True, exist_ok=True); rows = []
    for cap in sorted(folder.glob('*.png')):
        ref = next((r for r in (REFS/f'ref-{cap.stem}.jpg', REFS/f'{cap.stem}.jpg') if r.exists()), None)
        if ref is None: continue
        a = Image.open(cap).convert('RGB'); b = Image.open(ref).convert('RGB'); h = round(width*a.height/a.width)
        im = Image.new('RGB', (2*width+6, h), (20, 20, 20))
        im.paste(a.resize((width, h), Image.LANCZOS), (0, 0)); im.paste(b.resize((width, h), Image.LANCZOS), (width+6, 0))
        d = ImageDraw.Draw(im); d.text((8, 8), f'{label} {cap.stem}', fill=(255, 255, 255)); d.text((width+14, 8), 'reference', fill=(255, 255, 255))
        im.save(out/f'{cap.stem}.jpg', quality=90); rows.append(im)
    if rows:
        stack = Image.new('RGB', (rows[0].width, sum(r.height for r in rows)))
        for i, r in enumerate(rows): stack.paste(r, (0, i*rows[0].height))
        stack.save(CAPTURES/f'{label}-compare.jpg', quality=85)
    return len(rows)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args: raise SystemExit(__doc__)
    label, views = args[0], args[1:]
    h = np.load(yori.OUT/'heightmap.npy'); world = json.loads((yori.OUT/'world.json').read_text())
    shots = cameras(world['treehouse'], h, forest(world, (-190, -80, 110, 230)))
    if views: shots = [s for s in shots if s['id'] in views]
    if '--dry-run' in sys.argv: return print(json.dumps(shots, indent=1))
    folder = CAPTURES/label; folder.mkdir(parents=True, exist_ok=False)
    spec = folder/'shots.json'
    spec.write_text(json.dumps(dict(shots=shots, probes=[], settle_frames=90, initial_settle_frames=240), indent=1))
    from atelier.build import Context
    ctx = Context('yorimichi')
    command = [str(ctx.unreal_app), str(ctx.uproject), '-game', '-RenderOffscreen', '-ForceRes', '-resx=1920', '-resy=1080',
               '-noshaderworker', '-buildingreview='+str(spec), '-reviewdir='+str(folder), '-unattended', '-nosplash', '-stdout',
               '-abslog='+str(folder/'game.log'), '-set='+SETTINGS, '-ExecCmds='+COMMANDS]
    subprocess.run([sys.executable, '-m', 'atelier.safety.guarded', '--report', str(folder), '--', *command], check=True,
                   env={**os.environ, 'PYTHONPATH': str(yori.REPO/'platform/studio')})
    result = json.loads((folder/'completed.json').read_text()); print('PASS', result['passed'], result.get('errors'))
    assert result['passed']
    log = (folder/'game.log').read_text(errors='replace')
    assert 'Failed to compile Material' not in log, 'a material fell back to the checkerboard shader'
    line = next((l for l in log.splitlines() if 'TREEHOUSE lights' in l), '')
    print(line.split('Display: ')[-1] or 'no TREEHOUSE line in the log'); assert ' rooms 0' not in line and line
    sheet(folder, CAPTURES/f'{label}-sheet.jpg')
    print(compare(folder, label), 'pairs ->', CAPTURES/f'{label}-compare')


if __name__ == '__main__':
    main()
