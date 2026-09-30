"""Plan map and side view of the tree house layout, drawn from the same data the build uses.

    python games/yorimichi/world/regions/treehouse/plan_views.py [OUT_DIR]

Reads the built world (build/yorimichi/world.json, with the trees the tree house removed from
build/yorimichi/treehouse/removed.json) and treehouse/layout.py,
and writes plan-map.png (top view: terrain, trail, every tree, what is removed, platforms, bridges, slide) and
plan-section.png (the spine from the trail to the crow's nest, true scale).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import copy, json, math, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from village.layout import sample
from treehouse import layout as L

FONT = '/System/Library/Fonts/Supplemental/Arial.ttf'; BOLD = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'
def font(size, bold=False): return ImageFont.truetype(BOLD if bold else FONT, size)
TREE_COLORS = {'Maple': (196, 70, 38), 'Ginkgo': (222, 176, 40), 'Broad': (104, 142, 58), 'Cedar': (38, 104, 96), 'Pine': (46, 84, 52)}
WOOD, HUT, ROPE, INK = (190, 140, 88), (120, 72, 40), (110, 78, 44), (40, 34, 30)


def species(name):
    return next((c for k, c in TREE_COLORS.items() if k in name), (120, 120, 120))


def source_world():
    w = json.loads((yori.OUT/'world.json').read_text()); h = np.load(yori.OUT/'heightmap.npy')
    return w, h


def plan_map(w, h, pl, gone, path, X=(-178., -96.), Y=(130., 219.), S=12):
    W, H = int((X[1]-X[0])*S), int((Y[1]-Y[0])*S); panel = 380
    def P(x, y): return ((x-X[0])*S, (Y[1]-y)*S)
    xs = X[0]+(np.arange(W)+.5)/S; ys = Y[1]-(np.arange(H)+.5)/S
    gx, gy = np.meshgrid(xs, ys); z = sample(h, gx, gy)
    dzx = np.gradient(z, axis=1)*S; dzy = -np.gradient(z, axis=0)*S
    shade = np.clip(.78+.55*(-.6*dzx+.8*dzy)/np.sqrt(1+dzx**2+dzy**2), .5, 1.1)
    base = np.array([214, 214, 190], float)
    rgb = np.clip(base[None, None]*shade[..., None], 0, 255)
    lines = np.abs(np.diff(np.floor(z), axis=0, prepend=np.floor(z[:1]))) + np.abs(np.diff(np.floor(z), axis=1, prepend=np.floor(z[:, :1])))
    major = np.abs(np.diff(np.floor(z/5), axis=0, prepend=np.floor(z[:1]/5))) + np.abs(np.diff(np.floor(z/5), axis=1, prepend=np.floor(z[:, :1]/5)))
    rgb[lines > 0] *= .88; rgb[major > 0] = rgb[major > 0]*.7
    mp = Image.fromarray(rgb.astype(np.uint8)); d = ImageDraw.Draw(mp, 'RGBA')
    trail = np.array(w['zeppelin']['trail'])
    d.line([P(x, y) for x, y, _ in trail], fill=(176, 146, 104, 255), width=int(3.2*S), joint='curve')
    for x, y, zz in trail[::40]:
        if X[0] < x < X[1] and Y[0] < y < Y[1]: d.text(P(x, y+2.6), f'{zz:.0f}', fill=(90, 70, 40), font=font(13))
    # contour labels along a north-south line
    for zz in range(55, 80, 5):
        col = np.flatnonzero(np.abs(sample(h, np.full(400, -170.), np.linspace(Y[0], Y[1], 400))-zz) < .05)
        if len(col):
            yy = np.linspace(Y[0], Y[1], 400)[col[0]]; d.text(P(-176.5, yy+.7), f'{zz} m', fill=(80, 80, 60), font=font(13))
    for name, placements in w['instances'].items():
        if not name.startswith('Tree'): continue
        a = np.array(placements, float)
        if not len(a): continue
        m = (a[:, 0] > X[0]) & (a[:, 0] < X[1]) & (a[:, 1] > Y[0]) & (a[:, 1] < Y[1])
        c = species(name); dims = L.SPECIES.get(name, (5, 2, 9, 3))
        for x, y, zz, _, s in a[m]:
            r = dims[3]*s*.55*S; (px, py) = P(x, y)
            d.ellipse([px-r, py-r, px+r, py+r], fill=(*c, 26), outline=(*c, 70))
            d.ellipse([px-2.5, py-2.5, px+2.5, py+2.5], fill=(*c, 255))
    for name, placements in gone.items():
        if not name.startswith('Tree'): continue
        for x, y, *_ in placements:
            (px, py) = P(x, y); d.line([px-4, py-4, px+4, py+4], fill=(60, 60, 60, 230), width=2); d.line([px-4, py+4, px+4, py-4], fill=(60, 60, 60, 230), width=2)
    for c in pl['crowns']:
        x, y = pl['places'][c['place']]['xy']; (px, py) = P(x, y); r = c['radius']*S
        for k in range(0, 360, 12):
            a0, a1 = math.radians(k), math.radians(k+6)
            d.line([px+r*math.cos(a0), py-r*math.sin(a0), px+r*math.cos(a1), py-r*math.sin(a1)], fill=(*species(c['key']), 255), width=2)
    for b in pl['bridges']:
        (x0, y0, _), (x1, y1, _) = b['start'], b['end']
        u = np.array([x1-x0, y1-y0]); u /= np.linalg.norm(u); v = np.array([-u[1], u[0]])*L.BRIDGE_WIDTH/2
        for sgn in (-1, 1):
            d.line([P(x0+sgn*v[0], y0+sgn*v[1]), P(x1+sgn*v[0], y1+sgn*v[1])], fill=(*ROPE, 255), width=2)
        n = int(b['span']/.6)
        for k in range(n+1):
            t = k/n; cx, cy = x0+(x1-x0)*t, y0+(y1-y0)*t
            d.line([P(cx-v[0], cy-v[1]), P(cx+v[0], cy+v[1])], fill=(*WOOD, 255), width=2)
        mx, my = P((x0+x1)/2, (y0+y1)/2); d.text((mx+6, my-8), f"{b['span']:.0f} m", fill=(70, 50, 30), font=font(12))
    s = pl['slide']
    d.line([P(x, y) for x, y, *_ in s['path']]+[P(x, y) for x, y, _ in s['runout']], fill=(236, 212, 150, 255), width=int(1.0*S))
    d.line([P(x, y) for x, y, *_ in s['path']]+[P(x, y) for x, y, _ in s['runout']], fill=(150, 110, 60, 255), width=2)
    for x, y, _ in pl['stones']:
        (px, py) = P(x, y); d.ellipse([px-6, py-5, px+6, py+5], fill=(150, 150, 140, 255), outline=(90, 90, 80, 255))
    ex = pl['entry_stairs']
    for k in range(ex['steps']):
        y = ex['top_y']+(k+.5)*ex['tread']; d.line([P(ex['x']-.55, y), P(ex['x']+.55, y)], fill=(*HUT, 255), width=2)
    for i, p in enumerate(pl['places'].values()):
        x, y = p['xy']
        d.polygon([P(x+a, y+b) for a, b in p['poly']], fill=(*WOOD, 235), outline=(*INK, 255))
        r = p.get('room')
        if r is not None:              # the room's walls from the layout: the hall an octagon, the others rectangles
            cx, cy = r['center']
            if p['kind'] == 'heart':
                outline = L.turn(L.octagon(r['apothem']/math.cos(math.radians(22.5))), r['angle'])
            else:
                hx, hy = r['half']; outline = L.turn([(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)], r['angle'])
            d.polygon([P(cx+a, cy+b) for a, b in outline], fill=(*HUT, 255) if p['kind'] != 'boat' else (70, 96, 120, 255))
        if p['kind'] == 'pulley':
            a = math.radians(p['open']); d.line([P(x, y), P(x+4.6*math.cos(a), y+4.6*math.sin(a))], fill=(*INK, 255), width=4)
        if p['kind'] == 'lookout':
            r = pl['crow']['R']*S; (px, py) = P(x, y); d.ellipse([px-r, py-r, px+r, py+r], outline=(*INK, 255), width=3)
        (px, py) = P(x, y); rt = p['trunk']*S
        d.ellipse([px-rt, py-rt, px+rt, py+rt], fill=(80, 50, 40, 255))
        label = f"{i+1} {p['label']}"; sub = f"deck {p['deck']:.1f} m, +{p['deck']-p['ground']:.0f} m"
        if p['kind'] == 'lookout': sub += f"; nest {p['crow']:.1f} (+{p['crow']-p['ground']:.0f})"
        off = {'entry': (2.6, 2.6), 'heart': (6.0, 1.0), 'sleep': (-3.5, -4.0), 'pulley': (-9.0, -4.2), 'lookout': (-4, -4.6),
               'chimes': (2.8, -2.4), 'slide': (4.4, -2.5), 'boat': (-3.0, -4.4), 'kitchen': (4.0, 3.2), 'library': (4.0, 2.4)}[p['name']]
        tx, ty = P(x+off[0], y+off[1])
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            d.text((tx+dx, ty+dy), label, fill=(255, 255, 255), font=font(17, True)); d.text((tx+dx, ty+19+dy), sub, fill=(255, 255, 255), font=font(13))
        d.text((tx, ty), label, fill=INK, font=font(17, True)); d.text((tx, ty+19), sub, fill=INK, font=font(13))
    E = pl['places']['entry']; Lk = pl['places']['lookout']
    a, b = np.array(P(E['xy'][0]-.5, E['xy'][1]-3.0)), np.array(P(*Lk['xy']))
    for t in np.arange(0, 1, .03):
        q0, q1 = a+(b-a)*t, a+(b-a)*min(1, t+.015); d.line([tuple(q0), tuple(q1)], fill=(40, 90, 170, 200), width=2)
    # north arrow, scale, legend
    d.polygon([(W-40, 22), (W-50, 52), (W-40, 46), (W-30, 52)], fill=INK); d.text((W-46, 56), 'N', fill=INK, font=font(16, True))
    d.line([(20, H-24), (20+10*S, H-24)], fill=INK, width=4); d.text((20, H-46), '10 m', fill=INK, font=font(14))
    im = Image.new('RGB', (W+panel, H), (246, 243, 236)); im.paste(mp, (0, 0)); d = ImageDraw.Draw(im, 'RGBA')
    lx = W+22; ly = 24
    d.text((lx, ly), 'Tree house plan', fill=INK, font=font(24, True)); ly += 36
    d.text((lx, ly), 'west hillside, below the air-station trail', fill=INK, font=font(14)); ly += 34
    for c, t in [(WOOD, 'deck (octagon round its tree)'), (HUT, 'hut or room'), ((70, 96, 120), 'upturned rowboat room'), (ROPE, f"rope bridge ({pl['bridge_width']:.1f} m wide)"),
                 ((236, 212, 150), 'spiral slide to the ground'), ((150, 150, 140), 'stepping stones in the bank gap')]:
        d.rectangle([lx, ly+3, lx+22, ly+17], fill=c, outline=INK); d.text((lx+32, ly), t, fill=INK, font=font(14)); ly += 24
    d.line([lx, ly+10, lx+22, ly+10], fill=(40, 90, 170), width=2); d.text((lx+32, ly), 'reveal sightline: porch to crow\'s nest', fill=INK, font=font(14)); ly += 24
    d.line([lx+4, ly+4, lx+14, ly+14], fill=(60, 60, 60), width=2); d.line([lx+4, ly+14, lx+14, ly+4], fill=(60, 60, 60), width=2)
    d.text((lx+32, ly), f"tree removed ({sum(len(v) for k, v in gone.items() if k.startswith('Tree'))})", fill=INK, font=font(14)); ly += 24
    for k, c in TREE_COLORS.items():
        d.ellipse([lx+5, ly+4, lx+17, ly+16], fill=c); d.text((lx+32, ly), {'Broad': 'broadleaf'}.get(k, k.lower()), fill=INK, font=font(14)); ly += 22
    d.text((lx, ly+6), 'dashed ring: anchor crown', fill=INK, font=font(14)); ly += 30
    d.text((lx, ly), 'contours every 1 m, bold every 5 m', fill=INK, font=font(14)); ly += 40
    d.text((lx, ly), 'Places (deck height, height above ground)', fill=INK, font=font(15, True)); ly += 26
    for i, p in enumerate(pl['places'].values()):
        d.text((lx, ly), f"{i+1}. {p['label']}", fill=INK, font=font(14, True)); ly += 18
        words = p['role'].split(); line = ''
        for wd in words:
            if len(line+wd) > 44: d.text((lx+16, ly), line, fill=INK, font=font(13)); ly += 16; line = ''
            line += wd+' '
        d.text((lx+16, ly), line, fill=INK, font=font(13)); ly += 22
    im.save(path, optimize=True)


def section(w, h, pl, path):
    names = ['entry', 'library', 'heart', 'chimes', 'lookout']
    pts = [np.array(pl['stones'][0][:2])]+[np.array(pl['places'][n]['xy']) for n in names]+[np.array(pl['places']['lookout']['xy'])+np.array([-4, -12])]
    seg = np.r_[0, np.cumsum([np.linalg.norm(b-a) for a, b in zip(pts[:-1], pts[1:])])]
    total = seg[-1]; S = 11; Z0, Z1 = 50., 94.; W = int(total*S)+160; H = int((Z1-Z0)*S)+90
    def at(s):
        k = min(np.searchsorted(seg, s, 'right')-1, len(pts)-2); t = (s-seg[k])/(seg[k+1]-seg[k]); return pts[k]+(pts[k+1]-pts[k])*t
    def P(s, z): return (80+s*S, 30+(Z1-z)*S)
    im = Image.new('RGB', (W, H), (246, 243, 236)); d = ImageDraw.Draw(im, 'RGBA')
    for z in range(int(Z0), int(Z1)+1, 5):
        d.line([P(0, z), P(total, z)], fill=(210, 205, 195), width=1); d.text((10, P(0, z)[1]-8), f'{z} m', fill=(90, 90, 80), font=font(13))
    # existing trees near the line, in their real heights
    for name, placements in w['instances'].items():
        if not name.startswith('Tree'): continue
        a = np.array(placements, float); c = species(name); dims = L.SPECIES.get(name, (5, 2, 9, 3))
        m = (a[:, 0] > -190) & (a[:, 0] < -90) & (a[:, 1] > 110) & (a[:, 1] < 225)
        for x, y, zz, _, s in a[m]:
            best = None
            for k in range(len(pts)-1):
                u = pts[k+1]-pts[k]; Lk = np.linalg.norm(u); t = np.clip(((x-pts[k][0])*u[0]+(y-pts[k][1])*u[1])/Lk**2, 0, 1)
                dd = np.hypot(x-pts[k][0]-t*u[0], y-pts[k][1]-t*u[1])
                if best is None or dd < best[0]: best = (dd, seg[k]+t*Lk)
            if best[0] > 5: continue
            s0 = best[1]; r = dims[3]*s*.7
            d.line([P(s0, zz), P(s0, zz+dims[0]*s)], fill=(*c, 120), width=3)
            d.ellipse([P(s0-r, zz+dims[2]*s)[0], P(s0, zz+dims[2]*s)[1], P(s0+r, 0)[0], P(s0, zz+dims[1]*s)[1]], fill=(*c, 60))
    ss = np.linspace(0, total, 500); gz = [float(sample(h, *at(s))) for s in ss]
    d.polygon([P(s, z) for s, z in zip(ss, gz)]+[P(total, Z0), P(0, Z0)], fill=(150, 130, 96))
    d.line([P(s, z) for s, z in zip(ss, gz)], fill=(90, 70, 50), width=3)
    sp = dict(zip(names, seg[1:-1]))
    for n in names:
        p = pl['places'][n]; s0 = sp[n]; R = p.get('R', 3.)
        d.line([P(s0, p['ground']-.5), P(s0, p['trunk_top'])], fill=(90, 58, 44), width=max(3, int(p['trunk']*2*S)))
        d.rectangle([P(s0-R, p['deck']), P(s0+R, p['deck']-.25)], fill=(*WOOD, 255), outline=INK)
        if n in pl['places'] and 'trunk_top' in p and n != 'lookout':
            c = next(c for c in pl['crowns'] if c['place'] == n); r = c['radius']
            d.ellipse([P(s0-r, c['crown'][1]), P(s0+r, c['crown'][0])], fill=(*species(c['key']), 110), outline=(*species(c['key']), 200))
        if p['kind'] in ('hut', 'entry', 'heart'):
            half = p['room']['half'][0]; wall = p['room']['wall']; top = p['deck']+L.ROOF_TOP[p['kind']]
            d.rectangle([P(s0-half, p['deck']+wall), P(s0+half, p['deck'])], fill=(*HUT, 255))
            d.polygon([P(s0-half-.5, p['deck']+wall-.2), P(s0, top), P(s0+half+.5, p['deck']+wall-.2)], fill=(64, 70, 84, 255))
        d.text((P(s0, 0)[0]-40, 8), p['label'], fill=INK, font=font(14, True))
        d.text((P(s0-R, p['deck']-.4)[0], P(0, p['deck']-.4)[1]), f"{p['deck']:.1f} (+{p['deck']-p['ground']:.0f})", fill=INK, font=font(12))
    for a, b in zip(names[:-1], names[1:]):
        A, B = pl['places'][a], pl['places'][b]; sa = sp[a]+A.get('R', 3.)*.9; sb = sp[b]-B.get('R', 3.)*.9
        br = next((x for x in pl['bridges'] if {x['a'], x['b']} == {a, b}), None)
        if br is None: continue
        ts = np.linspace(0, 1, 30); zz = A['deck']+(B['deck']-A['deck'])*ts-br['sag']*4*ts*(1-ts)
        d.line([P(sa+(sb-sa)*t, z) for t, z in zip(ts, zz)], fill=(*ROPE, 255), width=4)
        d.line([P(sa+(sb-sa)*t, z+.95) for t, z in zip(ts, zz+br['sag']*1.6*ts*(1-ts))], fill=(*ROPE, 160), width=2)
    Lk = pl['places']['lookout']; s0 = sp['lookout']; cr = pl['crow']
    d.rectangle([P(s0-cr['R'], cr['floor']), P(s0+cr['R'], cr['floor']-.25)], fill=(*WOOD, 255), outline=INK)
    d.line([P(s0-cr['R'], cr['floor']+1.0), P(s0+cr['R'], cr['floor']+1.0)], fill=INK, width=2)
    d.text((P(s0+cr['R']+.4, cr['floor'])), f"crow's nest {cr['floor']:.1f} (+{cr['floor']-Lk['ground']:.0f})", fill=INK, font=font(12))
    for k in range(0, cr['steps'], 3):
        z = Lk['deck']+k*cr['rise']; x = math.cos(math.radians(cr['start']+k*cr['da']))*1.3
        d.rectangle([P(s0+x-.4, z+.05), P(s0+x+.4, z)], fill=(*HUT, 255))
    s = pl['stones'][0]; d.text((P(0, s[2]+2.2)), 'trail', fill=INK, font=font(14, True))
    E = pl['places']['entry']; eye = (sp['entry']-1.5, E['deck']+1.45)
    d.line([P(*eye), P(s0, cr['floor']+1.2)], fill=(40, 90, 170, 200), width=2)
    d.text((P(sp['library'], 88)), 'reveal: from the porch the crow\'s nest shows past the heart crown', fill=(40, 90, 170), font=font(13))
    d.text((P(total-40, 91.5)), 'south, towards the sea  >', fill=INK, font=font(14))
    d.text((P(0, 91.5)), '<  north, the trail', fill=INK, font=font(14))
    im.save(path, optimize=True)


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else yori.REVIEW/'treehouse'/'plan'
    out.mkdir(parents=True, exist_ok=True)
    w, h = source_world(); pl = L.plan(h)
    gone = json.loads((yori.OUT/'treehouse'/'removed.json').read_text())
    plan_map(w, h, pl, gone, out/'plan-map.png')
    section(w, h, pl, out/'plan-section.png')
    print('wrote', out/'plan-map.png', out/'plan-section.png')


if __name__ == '__main__':
    main()
