"""Tree house build (Blender, headless): decks, rope bridges, stairs, the slide, huts, rooms, trunks, dressing.

    atelier build yorimichi world.treehouse

Everything is placed from treehouse/layout.py in world space (Blender metres) and exported as three meshes that
AJapanWorld instances once at the origin: TH_Structure (walked on and bumped into: complex collision), TH_Trunks
(the ten anchor trunks: complex collision) and TH_Dressing (lanterns, thin ropes, cloth: no collision). Every face
has a vertex colour (the game's palette) and a material slot named after its texture (treehouse/tmesh.py,
tools/treehouse_textures.py); M_TreeHouse multiplies the two. Faces are single-sided with outward winding, so every
thin part seen from both sides is a closed solid or is built twice.

The Tripo props (treehouse/props.py) are placed here too. build/yorimichi/treehouse/runtime.json holds what the game needs
beside the meshes and AJapanWorld merges into world.json at load: every prop instance [x, y, z, yaw, scale]
(front = -y at yaw 0), the warm lights, and the rooms with their dimmer look.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import json, math, random, sys
from collections import defaultdict
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
from village.layout import sample
from treehouse import layout as L
from treehouse.tmesh import TMesh, export, material_factory

OUT = yori.OUT/'treehouse'
R = random.Random(1729)
PLANK, BOARD, WOOD, DARK = (.40, .24, .11), (.34, .20, .09), (.24, .13, .055), (.10, .055, .028)
PALE, ROPE, ROPE_LT, STRAW, SHIDE = (.62, .46, .26), (.55, .43, .27), (.62, .48, .29), (.72, .62, .42), (.95, .94, .90)
BARK, BARK_OLD = (.40, .27, .17), (.37, .25, .16)
SHINGLE, MOSS, TILE = (.24, .24, .26), (.20, .27, .08), (.20, .27, .38)
STONE, PAPER, GLASS, LANTERN = (.34, .35, .31), (.98, .80, .52), (.20, .52, .46), (1., .62, .30)
PLASTER, CANVAS, INDIGO, IRON, WHITE = (.60, .47, .32), (.80, .74, .62), (.20, .27, .48), (.12, .11, .11), (1., 1., 1.)
LEAF = [(.78, .20, .06), (.86, .36, .07), (.90, .60, .12), (.70, .14, .08)]
H = None
PLACED = defaultdict(list)          # prop key -> [[x, y, z, yaw, scale], ...]
LIGHTS = []                         # [x, y, z, lumens, radius m, shadows]: warm point lights (AJapanWorld)
ROOMS = []                          # interiors that get the room grade (AJapanWorld): boxes or spheres
# inside the rooms the paintings are dim wood lit by lanterns and window light: less saturated, a little darker
ROOM_GRADE = dict(tint=[1., .93, .80], saturation=1.08, contrast=1.1, exposure=.1, blend=.6)
WINDOWS = []                        # (inside corners, inward, along, floor z, kind): every glazed opening, for panes()
SUN = (1., .80, .52)                # the colour of the day in the windows


def vary(c, a=.08):
    f = R.uniform(1-a, 1+a)
    return tuple(min(1., x*f) for x in c)


def ground(x, y):
    return float(sample(H, x, y))


def prop(key, x, y, z, yaw=0., scale=1.):
    PLACED['TH_P_'+key].append([round(float(x), 3), round(float(y), 3), round(float(z), 3), round(float(yaw) % 360, 2), scale])


def light(x, y, z, lumens=300., radius=3.5, shadows=0):
    LIGHTS.append([round(float(x), 2), round(float(y), 2), round(float(z), 2), lumens, radius, shadows])


def interior(centre, extent=None, yaw=0., radius=None, half_height=None):
    """A room for the room grade and the camera see-through (docs/CAMERA.md): a box (half extent) or a round room
    (radius; half_height up to 35 cm over its walls, for the see-through's roof cut)."""
    r = dict(center=[round(float(v), 2) for v in centre], yaw=round(float(yaw), 2))
    if radius is not None:
        r['radius'] = radius
        if half_height is not None: r['half_height'] = round(float(half_height), 2)
    else: r['extent'] = [round(float(v), 2) for v in extent]
    ROOMS.append(r)


def face_yaw(dx, dy):
    """Yaw that turns a prop's front (-y) towards (dx, dy)."""
    return math.degrees(math.atan2(dx, -dy))


# ---------------------------------------------------------------------------------------------- solids

def hexa(m, p, color):
    """A closed six-sided solid from eight corners: one face (0-3), then the opposite face in the same order.
    The winding is fixed from the signed volume, so any corner order that keeps the topology works."""
    p = [np.asarray(q, float) for q in p]
    faces = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))
    vol = sum(p[f[0]]@np.cross(p[f[k]], p[f[k+1]]) for f in faces for k in (1, 2))
    if vol < 0:
        p = [p[0], p[3], p[2], p[1], p[4], p[7], p[6], p[5]]
    for f in faces:
        m.poly([tuple(p[i]) for i in f], color)


def board(m, a, b, width, thick, color, kind=None):
    """A board whose top centre line runs from a to b, level across its width; grain along it."""
    a, b = np.asarray(a, float), np.asarray(b, float); d = b-a; n = math.hypot(d[0], d[1])
    side = np.array([-d[1], d[0], 0.])/n*width/2 if n > 1e-6 else np.array([0., width/2, 0.])
    down = np.array([0., 0., thick])
    with m.use(kind, grain=tuple(d) if np.linalg.norm(d) > 1e-6 else (1, 0, 0), jitter=True):
        hexa(m, [a-side-down, b-side-down, b+side-down, a+side-down, a-side, b-side, b+side, a+side], color)


def post(m, x, y, z0, z1, w=.1, color=WOOD, kind='wood_timber'):
    with m.use(kind, grain=(0, 0, 1), jitter=True):
        m.box((x, y, (z0+z1)/2), (w, w, z1-z0), color)


def tube(m, pts, r, color=ROPE, n=6, kind='rope', closed=False):
    """A round tube along a polyline (rope, rings, pipes): u along its length, v round it."""
    pts = [np.asarray(q, float) for q in pts]
    if closed: pts = pts+[pts[0]]
    t = {'rope': .3, 'straw': .8}.get(kind, 1.); s = 0.; rings = []
    for i, q in enumerate(pts):
        d = (pts[min(i+1, len(pts)-1)]-pts[max(i-1, 0)]); d = d/(np.linalg.norm(d)+1e-9)
        up = np.array([0., 0., 1.]) if abs(d[2]) < .9 else np.array([1., 0., 0.])
        a = np.cross(d, up); a /= np.linalg.norm(a); b = np.cross(d, a)
        if i: s += float(np.linalg.norm(q-pts[i-1]))
        rings.append((s, [q+r*(math.cos(2*math.pi*k/n)*a+math.sin(2*math.pi*k/n)*b) for k in range(n)]))
    with m.use(kind):
        for (s0, ra), (s1, rb) in zip(rings[:-1], rings[1:]):
            for k in range(n):
                quad = [ra[k], ra[(k+1) % n], rb[(k+1) % n], rb[k]]
                uv = [(s0/t, k/n), (s0/t, (k+1)/n), (s1/t, (k+1)/n), (s1/t, k/n)]
                m.poly([tuple(q) for q in quad], color, uv=uv)


def ring(m, c, r, z, rr, color=ROPE, n=14, kind='rope'):
    tube(m, [(c[0]+r*math.cos(2*math.pi*k/n), c[1]+r*math.sin(2*math.pi*k/n), z) for k in range(n)], rr, color, 5, kind, True)


def rope(m, pts, r=.025, color=ROPE):
    tube(m, pts, r, color, 6)


def ccw(pts):
    pts = [tuple(q[:2]) for q in pts]
    area = sum(pts[i-1][0]*pts[i][1]-pts[i][0]*pts[i-1][1] for i in range(len(pts)))
    return pts if area > 0 else pts[::-1]


def prism(m, pts, z0, z1, top, side=None):
    pts = ccw(pts); side = side or top
    m.poly([(x, y, z1) for x, y in pts], top)
    m.poly([(x, y, z0) for x, y in pts[::-1]], side)
    for (ax, ay), (bx, by) in zip(pts, pts[1:]+pts[:1]):
        m.poly([(ax, ay, z0), (bx, by, z0), (bx, by, z1), (ax, ay, z1)], side)


def clip(poly, clipper):
    """Sutherland-Hodgman: a polygon cut to a convex counter-clockwise clipper."""
    out = [np.asarray(q, float) for q in poly]
    for i in range(len(clipper)):
        a = np.asarray(clipper[i], float); e = np.asarray(clipper[(i+1) % len(clipper)], float)-a
        side = lambda q: e[0]*(q[1]-a[1])-e[1]*(q[0]-a[0])
        inp, out = out, []
        for j, q in enumerate(inp):
            n = inp[(j+1) % len(inp)]; sq, sn = side(q), side(n)
            if sq >= 0: out.append(q)
            if (sq >= 0) != (sn >= 0): out.append(q+(n-q)*sq/(sq-sn))
        if not out: break
    return out


def sector(m, c, a0, a1, r0, r1, z0, z1, thick, color):
    """A curved piece from angle a0 to a1 (degrees), radii r0..r1, top rising from z0 to z1."""
    A0, A1 = math.radians(a0), math.radians(a1)
    P = lambda a, r, z: np.array([c[0]+r*math.cos(a), c[1]+r*math.sin(a), z])
    top = [P(A0, r1, z0), P(A1, r1, z1), P(A1, r0, z1), P(A0, r0, z0)]
    mid = (A0+A1)/2
    with m.use(grain=(-math.sin(mid), math.cos(mid), 0), jitter=True):
        hexa(m, [q-[0, 0, thick] for q in top]+top, color)


def two_sided(m, pts, color, back=None, uv=None):
    m.poly(pts, color, uv=uv); m.poly(pts[::-1], back or color, uv=uv[::-1] if uv else None)


def free_spans(a, b, gaps):
    a, b = np.asarray(a, float), np.asarray(b, float); e = b-a; n = float(np.linalg.norm(e)); u = e/n; cut = []
    for gx, gy, hw in gaps:
        w = np.array([gx, gy])-a; t = w@u; d2 = w@w-t*t
        if d2 < hw*hw:
            r = math.sqrt(hw*hw-d2); cut.append((t-r, t+r))
    spans, s = [], 0.
    for c0, c1 in sorted(cut):
        if c0 > s: spans.append((s, min(c0, n)))
        s = max(s, c1)
    if s < n: spans.append((s, n))
    return [(a+u*s0, a+u*s1) for s0, s1 in spans if s1-s0 > .2]


# ---------------------------------------------------------------------------------------------- the kit

def chochin(d, x, y, z, s=.3, hang=.25, lit=0.):
    """A round paper lantern: ribbed paper body, dark wooden caps, a cord up; lit (lumens) adds a point light."""
    if lit: light(x, y, z-.05, lit, 2.5+lit/250)
    prof = [(-s*.62, .0), (-s*.60, s*.20), (-s*.48, s*.38), (-s*.25, s*.48), (0, s*.5), (s*.25, s*.48), (s*.48, s*.38),
            (s*.60, s*.20), (s*.62, 0.)]
    with d.use('paper'):
        d.lathe((x, y, z), prof[1:-1], vary(LANTERN, .04), 12)
    with d.use('wood_timber'):
        for zz, sign in ((-s*.6, -1), (s*.6, 1)):
            d.lathe((x, y, z+zz), [(-.03*sign, s*.22), (.03*sign, s*.22)][::sign], DARK, 12)
            d.poly([(x+s*.22*math.cos(a), y+s*.22*math.sin(a), z+zz+.03*sign) for a in np.linspace(0, 2*math.pi, 13)[:-1]][::sign], DARK)
    for zz in (-s*.3, 0, s*.3):
        ring(d, (x, y), float(np.interp(zz, [q[0] for q in prof], [q[1] for q in prof]))+.004, z+zz, .006, DARK, 12, 'wood_timber')
    if hang > 0:
        post(d, x, y, z+s*.63, z+s*.63+hang, .014, DARK)


def andon(d, x, y, z, s=.26, lit=0.):
    """A square post lantern: paper box in a wooden frame with a little roof, standing at z."""
    h = s*1.25
    if lit: light(x, y, z+h*.6, lit, 2.5+lit/250)
    with d.use('paper'):
        d.box((x, y, z+.05+h/2), (s*.9, s*.9, h), vary(LANTERN, .04))
    for dx in (-1, 1):
        for dy in (-1, 1): post(d, x+dx*s*.47, y+dy*s*.47, z+.02, z+h+.1, .035, DARK)
    with d.use('wood_timber', grain=(1, 0, 0)):
        d.box((x, y, z+.03), (s*1.2, s*1.2, .06), WOOD)
        for k in range(2): d.box((x, y, z+h+.12+k*.05), (s*(1.35-.35*k), s*(1.35-.35*k), .05), DARK)
        d.box((x, y, z+h+.25), (.06, .06, .08), DARK)


def glass_float(d, x, y, z, r=.13, hang=.3):
    """A teal glass fishing float in a rope net, hanging on a cord."""
    with d.use('glass'):
        d.lathe((x, y, z), [(-r, .01), (-r*.7, r*.72), (0, r), (r*.7, r*.72), (r, .01)], vary(GLASS, .1), 12)
    for zz in (-r*.45, 0, r*.45):
        ring(d, (x, y), math.sqrt(max(r*r-zz*zz, 1e-4))+.006, z+zz, .007, ROPE, 12)
    for k in range(4):
        a = math.pi*k/4
        pts = [(x+(r+.006)*math.cos(t)*math.cos(a), y+(r+.006)*math.cos(t)*math.sin(a), z+(r+.006)*math.sin(t))
               for t in np.linspace(-math.pi/2, math.pi/2, 7)]
        tube(d, pts, .007, ROPE, 4)
        tube(d, [(2*x-px, 2*y-py, pz) for px, py, pz in pts], .007, ROPE, 4)
    if hang > 0: tube(d, [(x, y, z+r), (x, y, z+r+hang)], .007, ROPE, 4)


def fuurin(d, x, y, z, hang=.18):
    with d.use('glass'):
        d.lathe((x, y, z), [(0, .05), (.03, .055), (.075, .04), (.10, .012)], vary(GLASS, .15), 10)
    post(d, x, y, z-.12, z+.1+hang, .008, ROPE, 'rope')
    a = R.uniform(0, math.pi); t = np.array([math.cos(a), math.sin(a)])*.035
    with d.use('flat'):
        two_sided(d, [(x-t[0], y-t[1], z-.13), (x+t[0], y+t[1], z-.13), (x+t[0], y+t[1], z-.32), (x-t[0], y-t[1], z-.32)],
                  (.96, .92, .84))


def crate(m, x, y, z, s=(.55, .42, .4), yaw=0, color=None):
    """A slatted wooden crate."""
    w, dd, h = s; c = color or vary(PLANK, .12)
    with m.at((x, y, z), yaw):
        with m.use('wood_plank', grain=(1, 0, 0), jitter=True):
            m.box((0, 0, h/2), (w-.04, dd-.04, h-.02), c)
        with m.use('wood_timber', grain=(0, 0, 1), jitter=True):
            for dx in (-1, 1):
                for dy in (-1, 1): m.box((dx*(w/2-.03), dy*(dd/2-.03), h/2), (.06, .06, h), vary(WOOD, .1))
        with m.use('wood_plank', grain=(1, 0, 0), jitter=True):
            for dy in (-1, 1):
                for zz in (h*.28, h*.72): m.box((0, dy*(dd/2-.01), zz), (w-.08, .03, h*.3), vary(c, .06))


def stool(m, x, y, z, r=.17, h=.42):
    """A sawn log stool: bark round the side, pale end grain on top."""
    r = r*R.uniform(.92, 1.08)
    with m.use('bark', grain=(0, 0, 1), jitter=True):
        m.lathe((x, y, z), [(0, r*1.12), (.04, r*1.02), (h-.02, r), (h, r*.96)], vary((.55, .42, .30), .08), 12)
    with m.use('wood_pale'):
        m.lathe((x, y, z), [(h, r*.96), (h+.005, r*.5), (h+.006, .001)], vary(PALE, .06), 12)


BOOKS = [(.55, .20, .14), (.20, .28, .45), (.30, .40, .25), (.62, .50, .30), (.45, .22, .30)]


def basket(d, x, y, z, r=.2, h=.24, scrolls=0, fruit=0):
    """A woven straw basket, open at the top, with rolled maps standing in it or persimmons heaped in it."""
    with d.use('straw', grain=(0, 0, 1)):
        d.lathe((x, y, z), [(0, .001), (.005, r*.85), (h, r), (h+.02, r*1.03), (h+.02, r*.9), (h*.35, r*.8), (h*.35, .001)],
                vary(STRAW, .06), 12)
    for k in range(scrolls):
        a = 2*math.pi*k/max(1, scrolls)+R.uniform(-.3, .3); rr = r*.45*(k > 0)
        b = np.array([x+rr*math.cos(a), y+rr*math.sin(a), z+h*.35]); tip = b+[R.uniform(-.08, .08), R.uniform(-.08, .08), R.uniform(.45, .62)]
        tube(d, [b, tip], .032, vary(CANVAS, .05), 8, 'canvas')
    for k in range(fruit):
        a = 2*math.pi*k/max(1, fruit); rr = r*.5*(k > 0)
        with d.use('flat'):
            d.lathe((x+rr*math.cos(a), y+rr*math.sin(a), z+h-.01+.03*(k == 0)), [(-.035, .005), (-.03, .03), (0, .042), (.03, .03), (.035, .005)], vary((.92, .42, .08), .06), 8)


def book_stack(d, x, y, z, n=4, yaw=0.):
    """Cloth-bound books lying in a pile."""
    zz = 0.
    with d.at((x, y, z), yaw+R.uniform(-15, 15)):
        for k in range(n):
            w, l, t = R.uniform(.17, .22), R.uniform(.24, .3), R.uniform(.035, .06)
            with d.use('canvas', grain=(1, 0, 0)):
                d.box((R.uniform(-.02, .02), R.uniform(-.02, .02), zz+t/2), (w, l, t), vary(R.choice(BOOKS), .08))
            zz += t


def rope_coil(d, x, y, z, r=.28):
    for k in range(4):
        ring(d, (x+R.uniform(-.01, .01), y+R.uniform(-.01, .01)), r-.035*k*(k % 2), z+.025+.045*k, .025, ROPE, 16)


LEAVES = []     # (x, y, z, size) of every fallen leaf: a leaf never lies on another in the same plane


def maple_leaf(d, x, y, z, s=.09):
    """A flat fallen maple leaf; skipped where it would overlap another leaf at the same height (they would flicker)."""
    if any(abs(z-lz) < .004 and math.hypot(x-lx, y-ly) < s+ls for lx, ly, lz, ls in LEAVES):
        return
    LEAVES.append((x, y, z, s))
    a = R.uniform(0, 2*math.pi); c = vary(R.choice(LEAF), .08)
    pts = []
    for k in range(10):
        rr = s*(1 if k % 2 == 0 else .45)*(1.15 if k == 0 else 1)
        t = a+2*math.pi*k/10; pts.append((x+rr*math.cos(t), y+rr*math.sin(t), z))
    with d.use('flat'):
        d.poly(pts, c)


def leaves_on(d, poly, z, n):
    xs, ys = [q[0] for q in poly], [q[1] for q in poly]
    for _ in range(n*4):
        if n <= 0: break
        x, y = R.uniform(min(xs), max(xs)), R.uniform(min(ys), max(ys))
        if inside(poly, x, y): maple_leaf(d, x, y, z+.006, R.uniform(.06, .1)); n -= 1


def inside(poly, x, y):
    poly = ccw(poly)
    return all((b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0]) >= 0 for a, b in zip(poly, poly[1:]+poly[:1]))


def potted_plant(d, x, y, z, s=1.):
    with d.use('flat'):
        d.lathe((x, y, z), [(0, .1*s), (.02*s, .13*s), (.24*s, .16*s), (.28*s, .17*s)], vary((.52, .26, .14), .08), 10)
        d.poly([(x+.155*s*math.cos(a), y+.155*s*math.sin(a), z+.26*s) for a in np.linspace(0, 2*math.pi, 11)[:-1]], (.12, .07, .04))
        for k in range(9):
            a = k*2.39; zz = z+(.28+.03*k)*s; L0 = (.22+.02*k)*s
            tip = np.array([x+math.cos(a)*L0, y+math.sin(a)*L0, zz+.18*s]); base = np.array([x, y, zz])
            side = np.array([-math.sin(a), math.cos(a), 0])*.06*s; mid = (base+tip)/2
            two_sided(d, [tuple(base), tuple(mid+side), tuple(tip), tuple(mid-side)], vary((.22, .38, .10), .15))


def cloth(d, quad, uv, alphas):
    """A cloth face, both sides. Vertex alpha says how freely each corner hangs (0 where it is sewn, 1 at the hem):
    the tree house material sways and parts cloth by it (unreal/Scripts/see_through.py, docs/CAMERA.md)."""
    for pts, tex, al in ((quad, uv, alphas), (quad[::-1], uv[::-1], alphas[::-1])):
        before = len(d.faces)
        d.poly(pts, WHITE, uv=tex)
        if len(d.faces) > before and len(d.faces[-1]) == len(al):
            d.colors[-len(al):] = [(*WHITE, a) for a in al]


def noren(d, x, y, z, width, drop, yaw, pic='noren_cream'):
    """Split door curtain hanging from a rod at z, across a doorway facing yaw, gently waved: a band joined under the
    rod, then six strips with slits between them (one in the middle, where Cairo walks through), each strip two
    columns by six rows so the material can bend it. The picture runs on across the strips. The material finds a
    vertex's strip from its u in sixths and parts each strip whole, so keep six strips; alpha is 0 down the band and
    rises to 1 at the hem, where the strips hang free."""
    strips, rows, band, slit = 6, 8, 2, .012
    x0, x1 = -width/2+.01, width/2-.01
    step = (x1-x0+slit)/strips

    def wave(u): return .015*math.sin(u*18.+.6)

    def free(zz): return max(0., (-zz-drop*band/rows)/(drop-drop*band/rows))    # 0 down the band, 1 at the hem
    with d.at((x, y, z), yaw):
        post_rod = [(-width/2-.05, 0, .02), (width/2+.05, 0, .02)]
        tube(d, post_rod, .018, DARK, 6, 'wood_timber')
        with d.use(pic):
            columns = []                        # (left, right, is a slit)
            for k in range(strips):
                a = x0+k*step; b = a+step-slit; m = (a+b)/2
                columns += [(a, m, False), (m, b, False)] + ([(b, b+slit, True)] if k < strips-1 else [])
            for i in range(rows):
                za, zb = -drop*i/rows, -drop*(i+1)/rows
                for xa, xb, gap in columns:
                    if gap and i >= band: continue
                    ua, ub = (xa-x0)/(x1-x0), (xb-x0)/(x1-x0)
                    quad = [(xa, wave(xa), zb), (xb, wave(xb), zb), (xb, wave(xb), za), (xa, wave(xa), za)]
                    uv = [(ua, 1+zb/drop), (ub, 1+zb/drop), (ub, 1+za/drop), (ua, 1+za/drop)]
                    fa, fb = free(za), free(zb)
                    cloth(d, quad, uv, [fb, fb, fa, fa])


def picture(d, corners, pic, color=WHITE):
    """A flat picture (map, drawing, kite...) on the four corners, both sides, picture upright on the front."""
    uv = [(0, 0), (1, 0), (1, 1), (0, 1)]
    with d.use(pic):
        d.poly(corners, color, uv=uv)
        back = [np.asarray(q)-np.cross(np.subtract(corners[1], corners[0]), np.subtract(corners[3], corners[0])) /
                np.linalg.norm(np.cross(np.subtract(corners[1], corners[0]), np.subtract(corners[3], corners[0])))*.004 for q in corners]
        d.poly([tuple(q) for q in back[::-1]], color, uv=uv[::-1])


def wall_picture(d, frame, s, z0, z1, depth, pic, w=None, framed=False):
    """A picture on a wall: frame = (origin, along, inward) of the wall's inside face; s = centre along it."""
    o, u, n = frame; w = w or (z1-z0)
    c = o+u*s+n*depth
    if np.cross(u, [0, 0, 1])@n < 0: u = -u
    corners = [tuple(c-u*w/2+[0, 0, z0]), tuple(c+u*w/2+[0, 0, z0]), tuple(c+u*w/2+[0, 0, z1]), tuple(c-u*w/2+[0, 0, z1])]
    picture(d, corners, pic)
    if framed:
        for a, b in zip(corners, corners[1:]+corners[:1]):
            board(d, np.asarray(a)+n*.01, np.asarray(b)+n*.01, .04, .04, DARK, 'wood_timber')


def rug(d, cx, cy, z, w, l, yaw, pic='rug'):
    """A rug 14 mm over the floor: over the fallen leaves (6 mm), under what stands on it (12 mm and up)."""
    with d.at((cx, cy, z+.014), yaw):
        with d.use(pic):
            d.poly([(-w/2, -l/2, 0), (w/2, -l/2, 0), (w/2, l/2, 0), (-w/2, l/2, 0)], WHITE, uv=[(0, 0), (1, 0), (1, 1), (0, 1)])


def cushion(d, cx, cy, z, s=.6, yaw=0):
    with d.at((cx, cy, z), yaw):
        with d.use('indigo', grain=(1, 0, 0)):
            d.box((0, 0, .06), (s, s, .1), INDIGO, .03)
        with d.use('cushion'):
            d.poly([(-s/2+.02, -s/2+.02, .112), (s/2-.02, -s/2+.02, .112), (s/2-.02, s/2-.02, .112), (-s/2+.02, s/2-.02, .112)],
                   WHITE, uv=[(0, 0), (1, 0), (1, 1), (0, 1)])


def shelf(m, d, frame, s, z0, w, levels, stuff=True, depth=.3):
    """Wall shelves: boards on brackets along a wall's inside face, with jars, bowls and books on them."""
    o, u, n = frame
    for k in range(levels):
        z = z0+k*.42; c = o+u*s+n*(depth/2+.01)
        board(m, tuple(c-u*w/2+[0, 0, z]), tuple(c+u*w/2+[0, 0, z]), depth, .035, vary(PLANK, .08), 'wood_plank')
        for f in (-.4, .4):      # a brace from low on the wall up to the board's front half
            b = o+u*(s+f*w)+[0, 0, z-.035]; board(m, tuple(b+n*.02-[0, 0, .2]), tuple(b+n*(depth*.7)), .03, .04, DARK, 'wood_timber')
        if not stuff: continue
        x = -w/2+.08
        while x < w/2-.12:
            q = o+u*(s+x)+n*(depth*.5+.01)+[0, 0, z]; kind = R.random()
            if kind < .35:   # books, standing
                n_b = R.randint(3, 6); wb = .045*n_b
                if x+wb > w/2-.05: break
                cc = q+u*wb/2
                with d.use('books'):
                    ub = u if np.cross(u, [0, 0, 1])@n > 0 else -u
                    fr = [cc-ub*wb/2+n*.083, cc+ub*wb/2+n*.083, cc+ub*wb/2+n*.083+[0, 0, .235], cc-ub*wb/2+n*.083+[0, 0, .235]]
                    u0 = R.uniform(0, .6)
                    d.poly([tuple(q_) for q_ in fr], WHITE, uv=[(u0, 0), (u0+n_b/12, 0), (u0+n_b/12, 1), (u0, 1)])
                with d.use('flat'):   # seen from the side, a row of books shows its end cover, not plain wood
                    hexa(d, [cc-u*wb/2-n*.095, cc+u*wb/2-n*.095, cc+u*wb/2+n*.08, cc-u*wb/2+n*.08,
                             cc-u*wb/2-n*.095+[0, 0, .235], cc+u*wb/2-n*.095+[0, 0, .235], cc+u*wb/2+n*.08+[0, 0, .235], cc-u*wb/2+n*.08+[0, 0, .235]],
                         vary(R.choice([(.55, .18, .14), (.18, .28, .48), (.22, .38, .24), (.62, .46, .20)]), .1))
                x += wb+.03
            elif kind < .7:  # a jar
                r = R.uniform(.05, .075); hj = R.uniform(.12, .2)
                with d.use('glass'):
                    d.lathe(tuple(q+u*r), [(0, .01), (.01, r), (hj*.8, r), (hj, r*.7)], vary((.35, .45, .40), .1), 8)
                with d.use('wood_timber'):
                    d.lathe(tuple(q+u*r), [(hj, r*.72), (hj+.03, r*.72), (hj+.03, .005)], DARK, 8)
                x += 2*r+.04
            else:            # a bowl or pot
                r = R.uniform(.07, .1)
                with d.use('flat'):
                    d.lathe(tuple(q+u*r), [(0, .01), (.02, r*.6), (r*.8, r), (r*.85, r*.95)],
                            R.choice([(.32, .40, .55), (.55, .35, .22), (.62, .58, .50)]), 10)
                x += 2*r+.05


# ---------------------------------------------------------------------------------------------- decks

def world_poly(p):
    x0, y0 = p['xy']
    return ccw([(x0+a, y0+b) for a, b in p['poly']])


def railing(m, d, pts, z, gaps=(), height=.95, closed=True, avoid=()):
    """Chunky square posts with caps and rope lashings, a top rail and a lower rail, open at the gaps. A corner
    shared by two edges gets one post, and no post stands within 30 cm of a point in avoid (a bridge's end post
    already stands there). Rails stop 6 cm short of the posts' centres, so two rails never overlap in a corner."""
    edges = list(zip(pts, pts[1:]+pts[:1])) if closed else list(zip(pts[:-1], pts[1:]))
    placed = []
    for a, b in edges:
        for p, q in free_spans(a[:2], b[:2], gaps):
            n = max(1, math.ceil(np.linalg.norm(q-p)/1.3))
            for k in range(n+1):
                x, y = p+(q-p)*k/n
                if any(math.hypot(x-px, y-py) < .05 for px, py in placed): continue
                if any(math.hypot(x-ax, y-ay) < .3 for ax, ay in avoid): continue
                placed.append((x, y)); post(m, x, y, z-.05, z+height+.1, .12, vary(WOOD, .1))
                with m.use('wood_timber', grain=(1, 0, 0)):
                    m.box((x, y, z+height+.13), (.15, .15, .05), DARK)
                ring(d, (x, y), .09, z+height-.02, .018, ROPE_LT, 8)
                ring(d, (x, y), .09, z+height-.07, .018, ROPE_LT, 8)
            e = (q-p)/np.linalg.norm(q-p); p_, q_ = p+e*.06, q-e*.06
            board(m, (*p_, z+height+.035), (*q_, z+height+.035), .11, .08, vary(WOOD, .08), 'wood_timber')
            board(m, (*p_, z+.5), (*q_, z+.5), .06, .06, vary(WOOD, .08), 'wood_timber')
    return len(placed)


def deck(m, d, p):
    x0, y0 = p['xy']; z = p['deck']; poly = world_poly(p)
    th = math.radians(p['open']+90); u = np.array([math.cos(th), math.sin(th)]); v = np.array([-u[1], u[0]])
    Rm = max(math.hypot(a-x0, b-y0) for a, b in poly)+.5; k = -Rm; c = np.array([x0, y0])
    while k < Rm:
        rect = [c+u*s+v*t for s, t in ((-Rm, k), (Rm, k), (Rm, k+.215), (-Rm, k+.215))]
        piece = clip(ccw(rect), poly)
        if len(piece) >= 3:
            with m.use('wood_plank', grain=(u[0], u[1], 0), jitter=True):
                prism(m, piece, z-.06, z, vary(PLANK, .12), vary(DARK, .1))
        k += .23
    r = p['trunk']; lashed = []
    if 'box' in p:
        deck_frame(m, d, p)
    # A landing: joists to every corner and knee braces down to the trunk.
    for k, (vx, vy) in enumerate(poly if 'box' not in p else []):
        dd = np.array([vx-x0, vy-y0]); n = float(np.linalg.norm(dd)); w = dd/n
        dj = .0025 if len(poly) % 2 and k == len(poly)-1 else .005*(k % 2)     # joists meet at the trunk: staggered
        board(m, (*(c+w*r*.8), z-.06-dj), (*(c+w*(n-.08)), z-.06-dj), .12, .16, WOOD, 'wood_timber')
        if k % 2 == 0:
            zb = z-1.9-.1*n
            board(m, (*(c+w*r*.85), zb), (*(c+w*n*.72), z-.22), .12, .12, WOOD, 'wood_timber')
            if all(abs(zb-q) > .08 for q in lashed):      # one lashing per height: braces of equal length share it
                lashed.append(zb); ring(d, c, r+.06, zb+.05, .03, ROPE, 16)
    # the rim: neighbouring boards overlap in the corners, so every other one sits 5 mm lower (and a third height
    # closes an odd ring)
    for i, (a, b) in enumerate(zip(poly, poly[1:]+poly[:1])):
        dz = .0025 if len(poly) % 2 and i == len(poly)-1 else .005*(i % 2)
        e = (np.array(b)-np.array(a))/np.linalg.norm(np.array(b)-np.array(a))*.03
        board(m, (*(np.array(a)-e), z-.02-dz), (*(np.array(b)+e), z-.02-dz), .09, .26, DARK, 'wood_timber')
    # Cushions of moss in a few corners, inside the rim, and the season's leaves.
    for k in R.sample(range(len(poly)), min(3, len(poly))):
        a = np.array(poly[k]); inward = (c-a)/np.linalg.norm(c-a); q = a+inward*.45
        moss_pad(d, lambda x, y: np.array([x, y, z]), np.array([0, 0, 1.]), q[0], q[1], R.uniform(.18, .26), R.uniform(.16, .24), .035)
    leaves_on(d, poly, z, 14)


def deck_frame(m, d, p):
    """Under a room's deck (a chamfered rectangle round the trunk and the room, layout.box()): joists along its
    length every metre or so, on girders across it; the two end girders stand on stilts down to the ground at the
    corners away from the trunk, each with a knee brace and ties between them, and the girders either side of the
    trunk hang on knee braces from it. The joists stop at the bark."""
    x0, y0 = p['xy']; z = p['deck']; r = p['trunk']; ang, u0, u1, v0, v1, ch = p['box']
    a = math.radians(ang); U = np.array([math.cos(a), math.sin(a)]); V = np.array([-U[1], U[0]]); c = np.array([x0, y0])
    at = lambda u, v, zz: (*(c+U*u+V*v), zz)
    cut = lambda t0, t1: max(0., ch-t0, ch-t1)       # how far a chamfer cuts in, at distances t0, t1 from two edges
    nv = max(2, math.ceil((v1-v0-.3)/1.1))
    for i in range(nv+1):
        v = v0+.15+(v1-v0-.3)*i/nv; k = cut(v-v0, v1-v); lo, hi = u0+k+.08, u1-k-.08
        spans = [(lo, hi)]
        if abs(v) < r+.15:
            e = math.sqrt((r+.15)**2-v*v); spans = [(lo, -e), (e, hi)]
        for ua, ub in spans:
            if ub-ua > .3: board(m, at(ua, v, z-.06), at(ub, v, z-.06), .1, .16, WOOD, 'wood_timber')
    inset = max(.9, (ch+.5)/2)
    ends = [u0+inset, u1-inset]; mids = [u for u in (-(r+.25), r+.25) if all(abs(u-e) > .8 for e in ends)]
    for u in ends+mids:
        k = cut(u-u0, u1-u)
        board(m, at(u, v0+k+.1, z-.22), at(u, v1-k-.1, z-.22), .16, .2, DARK, 'wood_timber')
    for u in mids+[e for e in ends if abs(e) < r+1.6]:      # knee braces from the trunk to the girders near it
        s = 1 if u > 0 else -1
        for v in (-1.3, 1.3):
            board(m, at(s*r*.85, v*.2, z-2.1), at(u, v, z-.44), .12, .12, WOOD, 'wood_timber')
    ring(d, c, r+.06, z-2.1+.05, .03, ROPE, 16)
    for u in ends:
        feet = [v for _, _, us, v in p['stilts'] if abs(us-u) < .01]      # layout.stilts()
        for v in feet:
            q = at(u, v, 0); g = ground(q[0], q[1])
            post(m, q[0], q[1], g-.3, z-.42, .2, WOOD)
            s = -1 if v > 0 else 1                       # a knee brace in toward the middle of the girder
            board(m, at(u, v, z-1.7), at(u, v+s*1.2, z-.44), .1, .1, WOOD, 'wood_timber')
            ring(d, q[:2], .15, z-1.72, .025, ROPE, 10)
        if len(feet) == 2 and z-max(ground(*at(u, v, 0)[:2]) for v in feet) > 3.5:   # a tie and a cross between them
            zt = z-2.6
            board(m, at(u, feet[0], zt), at(u, feet[1], zt), .1, .12, WOOD, 'wood_timber')
            gl = max(ground(*at(u, v, 0)[:2]) for v in feet)+1.2
            if zt-gl > 1.5:
                board(m, at(u, feet[0], zt-.14), at(u, feet[1], gl), .09, .09, WOOD, 'wood_timber')


def gaps_for(p, pl, extra=()):
    x0, y0 = p['xy']; hw = L.BRIDGE_WIDTH/2+.1
    return [(x0+l['local'][0], y0+l['local'][1], hw) for l in p['links']]+list(extra)


# ---------------------------------------------------------------------------------------------- bridges

def bridge(m, d, b):
    A, B = np.array(b['start'], float), np.array(b['end'], float); W = L.BRIDGE_WIDTH
    dd = B[:2]-A[:2]; u = dd/np.linalg.norm(dd); v = np.array([-u[1], u[0]])

    def at(t, off=0., dz=0.):
        q = A+(B-A)*t; q[2] += -4*b['sag']*t*(1-t)+dz; q[:2] += v*off
        return q
    n = max(2, round(b['span']/.27))
    for k in range(n):
        q0, q1 = at(k/n), at((k+.82)/n); mid = (q0+q1)/2
        # boards run across the bridge: grain along v
        w = W*R.uniform(.95, 1.); a_ = mid-np.r_[v*w/2, 0]; b_ = mid+np.r_[v*w/2, 0]; th = float(np.linalg.norm(q1-q0))
        with m.use('wood_plank', grain=(v[0], v[1], 0), jitter=True):
            sd = np.r_[u*th/2, 0]; dn = np.array([0, 0, .05]); sl = (q1-q0)/2
            hexa(m, [a_-sl-dn, b_-sl-dn, b_+sl-dn, a_+sl-dn, a_-sl, b_-sl, b_+sl, a_+sl], vary(PLANK, .14))
            _ = sd
    ts = np.linspace(0, 1, 25)
    for side in (-1, 1):
        for t0, t1 in zip(ts[:-1], ts[1:]):
            board(m, at(t0, side*(W/2-.1), -.05), at(t1, side*(W/2-.1), -.05), .08, .1, DARK, 'wood_timber')
        off = side*(W/2+.03)
        tube(m, [at(t, off, .95) for t in ts], .05, ROPE_LT, 8)
        tube(m, [at(t, off, .5) for t in ts], .034, ROPE_LT, 6)
        for e in (0, 1):
            q = at(e, side*(W/2+.07))
            with m.at((q[0], q[1], 0), math.degrees(math.atan2(u[1], u[0]))):     # square to the bridge
                post(m, 0, 0, q[2]-.35, q[2]+1.18, .14, WOOD)
                with m.use('wood_timber'):
                    m.box((0, 0, q[2]+1.21), (.18, .18, .05), DARK)
            ring(d, q[:2], .085, q[2]+.95, .02, ROPE_LT, 8)
        nk = max(3, round(b['span']/.55))
        for k in range(1, nk):          # suspender ropes from the handrail down to the stringer
            q = at(k/nk, off); tube(d, [q+[0, 0, -.04], q+[0, 0, .95]], .012, ROPE, 4)
            if k % 2: tube(d, [at(k/nk, off, .5), at((k+1)/nk, off, .95)], .01, ROPE, 4)
    # Hanging lanterns along one handrail, a float here and there, a lantern post at each end.
    nl = max(1, round(b['span']/3.4))
    for k in range(1, nl+1):
        t = k/(nl+1); q = at(t, (W/2+.03)*(1 if k % 2 else -1), .95-.36)
        chochin(d, q[0], q[1], q[2], .2, .12) if k % 3 else glass_float(d, q[0], q[1], q[2]+.06, .1, .12)
    for e, side in ((0, 1), (1, -1)):
        q = at(e, side*(W/2+.07)); andon(d, q[0], q[1], q[2]+1.24, .24, 260)
    for _ in range(max(2, int(b['span']/2))):
        t = R.uniform(.05, .95); q = at(t, R.uniform(-.4, .4)); maple_leaf(d, q[0], q[1], q[2]+.006, R.uniform(.06, .09))


# ---------------------------------------------------------------------------------------------- walls, roofs

def xz_face(m, pts, y, color, facing):
    """A flat polygon in a wall's local xz plane at depth y; facing -1 shows it to -y, +1 to +y."""
    pts = [(x, y, z) for x, z in pts]
    area = sum(pts[i-1][0]*pts[i][2]-pts[i][0]*pts[i-1][2] for i in range(len(pts)))
    if (area > 0) != (facing < 0): pts = pts[::-1]
    m.poly(pts, color)


def wall(m, a, b, h, openings=(), t=.1, color=BOARD, centre=(0, 0), frames=None, outside='boards', turn=90.):
    """A board wall from a to b (current frame), h high, with openings (centre along the wall, width, bottom,
    top, kind); kind is 'door', 'window' (open, with mullions), 'round' (open, with a cross) or 'open-round'.
    Outside: vertical boards. Inside (towards centre): a board wainscot, a rail, and cream plaster above.
    turn is the angle to the next wall at both ends: the boards stop 3 cm short of the corner and the plaster, rail
    and plate stop where the neighbour's begin, so nothing of two walls lies in the same plane in a corner (it
    would flicker); the corner post covers the ends. Timbers that meet (jamb and header, sill and wall, mullion and
    transom) never share a face plane either. At a door or window the plaster and rail end in the middle of the jamb;
    the rail and the top plate stop a few millimetres short of the plaster's (and the boards') ends; the plaster stops
    a centimetre short of an opening's head or sill: no end of one lies in the face of the other."""
    a, b = np.asarray(a, float), np.asarray(b, float); n = float(np.linalg.norm(b-a))
    e = (b-a)/n; cn = np.asarray(centre, float)-a; inward = 1 if e[0]*cn[1]-e[1]*cn[0] > 0 else -1
    ang = math.degrees(math.atan2(b[1]-a[1], b[0]-a[0]))
    tb, ti = .03, .105*math.tan(math.radians(turn/2))+.006       # end trims: boards, inside finish
    if frames is not None:   # the inside face in the current frame, for pictures and shelves
        frames.append((a, e, np.array([-e[1], e[0]])*inward, n))
    jambed = [o for o in openings if o[4] not in ('round', 'open-round')]

    def finish(x, lo):      # where the plaster and rail stop at the cut x: the middle of a jamb, or the corner trim
        if any(abs(x-(o[0]-o[1]/2)) < 1e-6 for o in jambed): return x-.05
        if any(abs(x-(o[0]+o[1]/2)) < 1e-6 for o in jambed): return x+.05
        return max(x, ti) if lo else min(x, n-ti)
    with m.at((a[0], a[1], 0), ang):
        cuts = sorted({tb, n-tb, *[o[0]-o[1]/2 for o in openings], *[o[0]+o[1]/2 for o in openings]})
        for s0, s1 in zip(cuts[:-1], cuts[1:]):
            if s1-s0 < 1e-3: continue
            mid = (s0+s1)/2; hit = [o for o in openings if abs(o[0]-mid) < o[1]/2]
            for zb, zt in ([(0, h)] if not hit else [(0, hit[0][2]), (hit[0][3], h)]):
                if zt-zb < 1e-3: continue
                # vertical boards of about 18 cm, each its own grain
                k = max(1, round((s1-s0)/.18))
                for i in range(k):
                    xa, xb = s0+(s1-s0)*i/k, s0+(s1-s0)*(i+1)/k
                    with m.use('wood_plank', grain=(0, 0, 1), jitter=True):
                        m.box(((xa+xb)/2, -inward*.012, (zb+zt)/2), (xb-xa-.006, t-.024, zt-zb), vary(color, .09))
                # inside (and outside too for a plastered wall): plaster above the rail
                p0, p1 = finish(s0, True), finish(s1, False)
                if p1-p0 < .02: continue
                for f in ((inward, -inward) if outside == 'plaster' else (inward,)):
                    pz0, pz1 = max(zb+(.01 if zb > 0 else 0.), .95), min(zt-(.01 if zt < h else 0.), h-.1)
                    if pz1-pz0 > .05:
                        with m.use('plaster', jitter=True):
                            m.box(((p0+p1)/2, f*(t/2-.008), (pz0+pz1)/2), (p1-p0, .02, pz1-pz0), vary(PLASTER, .04))
                    if zb < .95 < zt:
                        with m.use('wood_timber', grain=(1, 0, 0), jitter=True):
                            m.box(((p0+p1)/2, f*(t/2+.01), .95), (p1-p0-.012, .05, .07), WOOD)
        # inside timber framing over the plaster: studs about every 85 cm clear of the openings, and a top plate
        k = max(1, round(n/.85))
        for f in ((inward, -inward) if outside == 'plaster' else (inward,)):
            for i in range(1, k):
                x = n*i/k
                if any(abs(x-o[0]) < o[1]/2+.12 for o in openings): continue
                with m.use('wood_timber', grain=(0, 0, 1), jitter=True):
                    m.box((x, f*(t/2+.022), (.98+h-.12)/2), (.08, .038, h-.12-.98), vary(WOOD, .06))
            with m.use('wood_timber', grain=(1, 0, 0), jitter=True):
                m.box((n/2, f*(t/2+.025), h-.14), (n-2*ti-.006, .05, .09), WOOD)
        for s, w, zb, zt, kind in openings:
            if kind in ('window', 'round'):
                X = m.transform; y = inward*t/2; zc = (zb+zt)/2
                pts = ([(s+w/2*math.cos(f), y, zc+w/2*math.sin(f)) for f in np.linspace(0, 2*math.pi, 13)[:-1]]
                       if kind == 'round' else [(s-w/2, y, zb), (s+w/2, y, zb), (s+w/2, y, zt), (s-w/2, y, zt)])
                WINDOWS.append(([tuple(X@Vector(q)) for q in pts], tuple(X.to_3x3()@Vector((0, inward, 0))),
                                tuple(X.to_3x3()@Vector((1, 0, 0))), (X@Vector((0, 0, 0))).z, kind))
            if kind in ('round', 'open-round'):
                r = w/2; zc = (zb+zt)/2; arc = [(s+r*math.cos(f), zc+r*math.sin(f)) for f in np.linspace(0, 2*math.pi, 25)]
                with m.use('wood_plank', grain=(0, 0, 1)):
                    for q in range(4):
                        corner = (s+r*(1 if q in (0, 3) else -1), zc+r*(1 if q < 2 else -1))
                        for i in range(6*q, 6*q+6):
                            for y, f in ((-t/2, -1), (t/2, 1)): xz_face(m, [corner, arc[i], arc[i+1]], y, color, f)
                with m.use('wood_timber'):
                    for i in range(24):
                        (x0, z0), (x1, z1) = arc[i], arc[i+1]; k0 = (r+.1)/r
                        rg = [(x0, z0), (x1, z1), (s+(x1-s)*k0, zc+(z1-zc)*k0), (s+(x0-s)*k0, zc+(z0-zc)*k0)]
                        hexa(m, [(x, -t/2-.04, z) for x, z in rg]+[(x, t/2+.04, z) for x, z in rg], DARK)
                if kind == 'round':
                    with m.use('wood_timber'):
                        m.box((s, 0, zc), (.045, .06, w), DARK); m.box((s, 0, zc), (w, .05, .045), DARK)
                else:
                    with m.use('wood_timber'):
                        m.box((s, 0, zc), (.06, t+.02, w), DARK)
                continue
            with m.use('wood_timber', grain=(0, 0, 1)):
                for x in (s-w/2-.05, s+w/2+.05): m.box((x, 0, (zb+zt)/2), (.1, t+.06, zt-zb+.04), DARK)
            with m.use('wood_timber', grain=(1, 0, 0)):      # the header, its underside a little inside the opening
                m.box((s, 0, zt+.03), (w+.22, t+.08, .12), DARK)
            if kind == 'window':
                with m.use('wood_timber', grain=(1, 0, 0)):    # the sill, its top a little over the wall below
                    m.box((s, 0, zb-.02), (w+.24, t+.12, .06), WOOD)
                with m.use('wood_timber', grain=(0, 0, 1)):
                    for i in (1, 2): m.box((s-w/2+w*i/3, 0, (zb+zt)/2), (.035, .06, zt-zb), DARK)
                    m.box((s, 0, (zb+zt)/2), (w, .05, .035), DARK)


def moss_pad(d, S, nrm, am, bm, ra, rb, h, n=9):
    """A cushion of moss on a surface: S(a, b) is its point at surface coordinates (a, b), nrm its up side, and the
    ellipse (am, bm, ra, rb) turns anticlockwise seen from there. An irregular rim just proud of the surface and a
    dome h high: moss that stands up off the shingles or boards instead of lying flat on them."""
    ts = sorted(2*math.pi*k/n+R.uniform(-.25, .25) for k in range(n)); fs = [R.uniform(.75, 1.15) for _ in ts]
    rim = [S(am+ra*f*math.cos(t), bm+rb*f*math.sin(t))+nrm*.006 for t, f in zip(ts, fs)]
    mid = [S(am+ra*f*.6*math.cos(t), bm+rb*f*.6*math.sin(t))+nrm*h*R.uniform(.65, .85) for t, f in zip(ts, fs)]
    top = S(am, bm)+nrm*h; col = vary(MOSS, .15)
    with d.use('moss'):
        for k in range(n):
            j = (k+1) % n
            d.poly([tuple(rim[k]), tuple(rim[j]), tuple(mid[j]), tuple(mid[k])], col)
            d.poly([tuple(mid[k]), tuple(mid[j]), tuple(top)], col)


def shingled(m, d, quad, rows=None, moss=.25, tiles=.1, ridge=None, phase=0):
    """A roof plane of overlapping shingle courses: quad = eave-left, eave-right, top-right, top-left.
    Each course is a thin slab lapping the one below, split into runs of shingle or blue tile; on some runs a
    cushion of moss (more along the eaves and the ridge)."""
    q = [np.asarray(x, float) for x in quad]
    slope = float(np.linalg.norm((q[3]+q[2])/2-(q[0]+q[1])/2)); rows = rows or max(3, round(slope/.34))
    P = lambda a, b: q[0]+(q[1]-q[0])*a+(q[3]-q[0])*b+(q[2]-q[1]-q[3]+q[0])*a*b
    along = (q[1]-q[0])/np.linalg.norm(q[1]-q[0])
    nrm = np.cross(q[1]-q[0], q[3]-q[0]); nrm /= np.linalg.norm(nrm)
    turn = 1 if nrm[2] > 0 else -1       # a pad's ellipse must turn anticlockwise seen from above
    if nrm[2] < 0: nrm = -nrm
    prev, pads = [], []
    for i in range(rows):
        b0, b1 = i/rows, min(1., (i+1.35)/rows)
        width = float(np.linalg.norm(P(1, b0)-P(0, b0))); runs = max(1, round(width/R.uniform(.7, 1.1)))
        ext = .008*((i+phase) % 2)/width    # every other row a little past the sides: lapping rows' ends not in one plane
        # runs at least 25 cm long (a sliver's two ends would lie in its neighbours' end faces), and no cut within
        # 4 cm of one in the row below (their ends overlap where the rows lap)
        inner = []
        for a in [R.uniform(.1, .9) for _ in range(runs-1)]:
            if all(abs(a-x)*width > .25 for x in inner) and all(abs(a-x)*width > .04 for x in prev): inner.append(a)
        cuts = sorted([-ext, 1.+ext]+inner); prev = inner
        for a0, a1 in zip(cuts[:-1], cuts[1:]):
            c = R.random(); edge = i == 0 or i == rows-1
            mossy = c < moss*(1.6 if edge else .7)
            kind, col = (('tile', vary(TILE, .1)) if not mossy and c < moss+tiles else ('shingle', vary(SHINGLE, .12)))
            lo = [P(a0, b0), P(a1, b0)]; hi = [P(a1, b1), P(a0, b1)]
            tip = .045+.015*R.random()
            pts = [lo[0]+nrm*tip, lo[1]+nrm*tip, hi[0]+nrm*.012, hi[1]+nrm*.012]
            with m.use(kind, grain=tuple(along), jitter=True):
                hexa(m, [pts[0]-nrm*.03, pts[1]-nrm*.03, pts[2]-nrm*.03, pts[3]-nrm*.03]+pts, col)
            if mossy:        # on the course's visible band, b0 to the next course's lower edge
                band = min(b1, (i+1)/rows)-b0
                top_of = lambda a, b, b0=b0, b1=b1, tip=tip: P(a, b)+nrm*(tip+(.012-tip)*(b-b0)/(b1-b0))
                fb = R.uniform(.38, .55); rb = min(R.uniform(.28, .4), fb-.1)
                pads.append((top_of, nrm, (a0+a1)/2+R.uniform(-.1, .1)*(a1-a0), b0+band*fb,
                             R.uniform(.3, .42)*(a1-a0), turn*band*rb, R.uniform(.045, .08)))
    # quad is in m's frame (the caller's m.at()), which d does not share: the pads go into d in that frame
    old, d.transform = d.transform, m.transform.copy()
    try:
        for pad in pads: moss_pad(d, *pad)
    finally:
        d.transform = old
    under = [tuple(x-nrm*.03) for x in q]
    if np.cross(q[1]-q[0], q[3]-q[0])@nrm > 0: under = under[::-1]
    with m.use('wood_plank', grain=tuple(along)):
        m.poly(under, vary(BOARD, .05))


def gable_roof(m, d, length, width, eave, top, over=.36):
    """Ridge along local x; eaves along +-y. length and width are the walls' outside sizes."""
    l2, w2 = length/2+over, width/2+over
    for s in (-1, 1):
        quad = [(-l2, s*w2, eave), (l2, s*w2, eave), (l2, 0, top), (-l2, 0, top)]
        if s < 0: quad = [quad[1], quad[0], quad[3], quad[2]]
        shingled(m, d, quad, phase=int(s < 0))     # the two sides' top rows meet at the ridge: opposite phases
        board(m, (-l2, s*w2, eave+.02), (l2, s*w2, eave+.02), .1, .16, DARK, 'wood_timber')
        for k in range(5):                 # rafters seen from inside; a pair meets at the ridge side by side
            x = -length/2+length*k/4+s*.004
            board(m, (x, s*(width/2-.07), eave-.02), (x, 0, top-.14), .08, .1, WOOD, 'wood_timber')
    with m.use('moss', grain=(1, 0, 0)):
        board(m, (-l2-.05, 0, top+.11), (l2+.05, 0, top+.11), .26, .12, vary(MOSS, .1), 'moss')
    board(m, (-l2-.03, 0, top+.02), (l2+.03, 0, top+.02), .18, .12, DARK, 'wood_timber')
    board(m, (-length/2, 0, top-.16), (length/2, 0, top-.16), .12, .14, WOOD, 'wood_timber')
    for x in (-length/2, length/2):
        o = 1 if x > 0 else -1             # the gable's outer side
        for f in (-1, 1):                  # outside, clear of the wall boards' face under it (5 cm out)
            xf = x+f*(.056 if f == o else .05)
            tri = [(xf, -width/2, eave+.02), (xf, width/2, eave+.02), (xf, 0, top-.02)]
            with m.use('wood_plank', grain=(0, 0, 1)):
                m.poly(tri if f > 0 else tri[::-1], BOARD)
        for f in (-1, 1):   # barge boards, the pair side by side where they meet at the apex
            board(m, (x+f*.004, f*w2, eave), (x+f*.004, 0, top+.06), .08, .16, DARK, 'wood_timber')


def hut_frame(p):
    """A hut's centre at deck height and the angle of its local x (layout.room(): out from the trunk, which stands
    behind the back wall), and side = 1: the furnishing works in plain hut-local y."""
    r = p['room']
    return np.array([*r['center'], p['deck']], float), r['angle'], 1


def local(c, ang, lx, ly, lz=0.):
    a = math.radians(ang)
    return np.array([c[0]+lx*math.cos(a)-ly*math.sin(a), c[1]+lx*math.sin(a)+ly*math.cos(a), c[2]+lz])


def hut_roof_z(lx):
    """Height over the floor of a hut roof's underside at hut-local x (the ridge runs across at lx = 0)."""
    d2 = L.HUT[1]/2; eave = L.WALL-.08
    return eave+(L.ROOF_TOP['hut']-eave)*(1-abs(lx)/(d2+.36))


def hut(m, d, p, name):
    """A hut beside its trunk (layout.room()): 7 m across between the doors in its two gable ends, 6 m deep from the
    back wall, which faces the trunk, to the outer wall, 3 m to the wall plate and open to the rafters. The ridge
    runs across, over both doors (1.3 x 2.5 m, each with a noren and a lantern). The outer wall has a six-pane window
    and a round one; the back wall two windows either side of the trunk, so it is never blank from the bridges; each
    gable a round window on the back side of its door, battens and a lantern. Inside, a lane 1.5 m wide runs from
    door to door through the middle (hut-local |x| < 0.75); the furniture keeps to the back and front halves."""
    c, ang, side = hut_frame(p); d2, w2 = p['room']['half']; h = L.WALL; dw, dh = L.DOOR; top = L.ROOF_TOP['hut']
    frames = []
    with m.at(tuple(c), ang):
        # wall positions: outer s = y+w2, back s = w2-y, gable -y s = x+d2, gable +y s = d2-x
        wall(m, (d2, -w2), (d2, w2), h, [(w2-1.6, 1.6, .9, 2.2, 'window'), (w2+1.9, 1.1, 1.1, 2.2, 'round')], frames=frames)
        # (the sill's underside clear of the plaster's, which starts at the rail, 0.95 m)
        wall(m, (-d2, w2), (-d2, -w2), h, [(w2-y, .9, 1.05, 2.05, 'window') for y in (2.5, -2.5)], frames=frames)
        wall(m, (-d2, -w2), (d2, -w2), h, [(d2, dw, 0., dh, 'door'), (d2-1.9, .8, 1.2, 2.0, 'round')], frames=frames)
        wall(m, (d2, w2), (-d2, w2), h, [(d2, dw, 0., dh, 'door'), (d2+1.9, .8, 1.2, 2.0, 'round')], frames=frames)
        for x in (-d2, d2):
            for y in (-w2, w2): post(m, x, y, -.04, h+.05, .16, DARK)
    with m.at(tuple(c), ang+90):          # roof frame: x along the ridge (hut-local y), y = -(hut-local x)
        gable_roof(m, d, 2*w2, 2*d2, h-.08, top)
    with d.at(tuple(c), ang+90):          # vertical battens on both gables, outside the gable boards
        e0 = h+.04                        # the gable board's top edge: gable_roof()'s triangle, eave+.02 to top-.02
        for o in (-1, 1):
            for yy in np.arange(-d2+.45, d2-.3, .5):
                z1 = (h-.06)+(top-.02-(h-.06))*(1-abs(yy)/d2)-.16
                if z1-e0 > .25:
                    with d.use('wood_timber', grain=(0, 0, 1)):
                        d.box((o*(w2+.08), yy, (e0+z1)/2), (.035, .07, z1-e0), DARK)
    # world-space inside frames: (origin, along, inward, length) per wall, in order outer, back, gable -y, gable +y
    W = [(local(c, ang, *f[0]), rot(f[1], ang), rot(f[2], ang), f[3]) for f in frames]
    for s in (-1, 1):
        q = local(c, ang, 0, s*(w2+.08))
        noren(d, q[0], q[1], c[2]+dh, dw-.1, .85, ang, 'noren_indigo' if name == 'library' else 'noren_cream')
        q = local(c, ang, .98, s*(w2+.3)); chochin(d, q[0], q[1], c[2]+2.35, .26, .3, 320)
    for lx, ly in ((d2+.34, -w2-.34), (d2+.34, w2+.34), (-d2-.3, -w2+.8), (-d2-.3, w2-.8)):
        q = local(c, ang, lx, ly); glass_float(d, q[0], q[1], c[2]+h-.5, .12, .3)
    q = local(c, ang, -d2-.3, 0); chochin(d, q[0], q[1], c[2]+h-.55, .26, .3, 260)     # on the back wall, by the trunk
    q = local(c, ang, d2+.36, .45); fuurin(d, q[0], q[1], c[2]+h-.3)
    for lx in (-1.8, 1.8):                # over the furniture, off the lane
        q = local(c, ang, lx, 0); chochin(d, q[0], q[1], c[2]+2.45, .24, .35, 420)
    interior((c[0], c[1], c[2]+h/2), (d2-.05, w2-.05, h/2+.35), ang)
    # leaves blown in through the doors, along the lane (never under the furniture)
    leaves_on(d, [tuple(local(c, ang, sx*.7, sy*(w2-.15))[:2]) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))], c[2], 6)
    light(c[0], c[1], c[2]+1.2, 300, 4.)      # warm fill low in the room
    return c, ang, side, W


def lyaw(ang, lx, ly):
    """Yaw that turns a prop's front towards the hut-local direction (lx, ly)."""
    return face_yaw(*rot((lx, ly), ang)[:2])


def rot(v, ang):
    a = math.radians(ang); v = np.asarray(v, float)
    return np.array([v[0]*math.cos(a)-v[1]*math.sin(a), v[0]*math.sin(a)+v[1]*math.cos(a), 0.])


def frame3(f, z):
    o, u, n, _ = f
    return (np.array([o[0], o[1], z]), u, n)


# ---------------------------------------------------------------------------------------------- rooms

def room(c, ang, side):
    """Hut-local placement: lx from the back wall (-d2, trunk side) to the outer wall (+d2); sy towards the door wall."""
    return lambda lx, sy, lz=0.: local(c, ang, lx, side*sy, lz)


def along(frame):
    return math.degrees(math.atan2(frame[1][1], frame[1][0]))


def persimmon(d, q):
    with d.use('flat'):
        d.lathe(tuple(q), [(-.035, .005), (-.03, .03), (0, .042), (.03, .03), (.035, .005)], vary((.92, .42, .08), .06), 8)


def table(m, q, ang, su, sn, h, color=None):
    """A plain plank table su x sn (su along hut-local x for the hut angle ang), h high, on four square legs."""
    q = np.asarray(q, float); u, n = rot((1, 0), ang), rot((0, 1), ang)
    block(m, q+[0, 0, h-.025], u, n, su, sn, .05, color or vary(PLANK, .06), 'wood_plank')
    for a in (-1, 1):
        for b in (-1, 1):
            block(m, q+u*a*(su/2-.07)+n*b*(sn/2-.07)+[0, 0, (h-.05)/2], u, n, .06, .06, h-.05, WOOD)
    return q+[0, 0, h]


def sack(d, q, r=.2, h=.5):
    """A tied sack of rice or flour standing on the floor."""
    q = np.asarray(q, float)
    with d.use('canvas'):
        d.lathe(tuple(q), [(0, r*.8), (h*.3, r), (h*.7, r*.92), (h*.9, r*.5), (h, r*.3), (h+.07, r*.42)], vary(CANVAS, .08), 10)
    ring(d, q[:2], r*.33, q[2]+h+.01, .016, ROPE, 8)


def drawer_chest(m, d, q, ang, w=1.0, dp=.42, h=.85):
    """A chest of three drawers against a wall: its back along hut-local y, its front toward +x."""
    q = np.asarray(q, float); n, u = rot((1, 0), ang), rot((0, 1), ang)
    block(m, q+[0, 0, h/2], u, n, w, dp, h, vary(WOOD, .05))
    for k in range(3):
        f = q+n*(dp/2+.009)+[0, 0, .08+k*(h-.12)/3+(h-.12)/6]
        block(d, f, u, n, w-.08, .018, (h-.12)/3-.04, vary(PLANK, .05), 'wood_plank')
        for sgn in (-1, 1):
            block(d, f+u*sgn*w/4+n*.03, u, n, .1, .02, .03, IRON, 'iron')


def furnish_kitchen(m, d, c, ang, side, W):
    """As painted: the clay stove against the back wall with its pipe up through the roof and split logs beside it,
    a counter of crates under a shelf, the water barrel in the back corner; the log table and stools on a blue rug in
    the front half; persimmons and herbs drying in front of the six-pane window. Hut-local x runs from the back wall
    (-d2) to the outer wall (+d2); the lane from door to door (|x| < 0.75) stays clear."""
    z = c[2]; outer, back, gm, gp = W; d2, w2 = L.HUT[1]/2, L.HUT[0]/2
    Hl = room(c, ang, side)
    q = Hl(-d2+.42, -1.1); prop('kamado', q[0], q[1], z, lyaw(ang, 1, 0), 1.)
    pipe = Hl(-d2+.2, -1.1)
    tube(m, [(pipe[0], pipe[1], z+.95), (pipe[0], pipe[1], z+hut_roof_z(-d2+.2)+.9)], .075, IRON, 8, 'iron')
    for zz in (1.9, 2.75): ring(m, pipe[:2], .08, z+zz, .015, IRON, 8, 'iron')
    for k in range(10):           # split logs stacked by the stove, under the back window
        q = Hl(-d2+.2+.13*(k % 4), -2.45, .07+.12*(k//4)); e = rot((0, .45), ang)
        tube(m, [q-e/2, q+e/2], .06, vary(WOOD, .15), 6, 'wood_timber')
    q = Hl(-d2+.5, 2.85); prop('barrel', q[0], q[1], z, lyaw(ang, 1, 0), .95)
    # the counter along the back wall (back wall s = w2-y): two crates, a board top, bowls; a shelf over it
    bo, bu, bn = frame3(back, z); yaw = along(back)
    for sc in (2.05, 2.8):
        q = bo+bu*sc+bn*.3; crate(m, q[0], q[1], z, (.72, .5, .78), yaw)
    top = [bo+bu*1.65+bn*.31+[0, 0, .8], bo+bu*3.2+bn*.31+[0, 0, .8]]
    board(m, tuple(top[0]), tuple(top[1]), .6, .05, vary(PLANK, .05), 'wood_plank')
    for k, sc in enumerate((1.85, 2.15, 2.6, 3.0)):
        q = bo+bu*sc+bn*.3+[0, 0, .8]
        with d.use('flat'):
            if k == 2:             # a bowl of persimmons
                d.lathe(tuple(q), [(0, .02), (.03, .12), (.08, .15)], (.55, .35, .22), 10)
                for j in range(4): persimmon(d, q+[.05*math.cos(j*1.6), .05*math.sin(j*1.6), .08])
            else:
                d.lathe(tuple(q), [(0, .01), (.02, .06), (.14+.04*k, .065), (.18+.04*k, .04)], R.choice([(.32, .40, .55), (.62, .58, .50), (.55, .35, .22)]), 10)
    towel = bo+bu*2.3+bn*.58
    with d.use('canvas'):
        two_sided(d, [tuple(towel+[0, 0, .82]), tuple(towel+bu*.3+[0, 0, .82]), tuple(towel+bu*.3+[0, 0, .45]), tuple(towel+[0, 0, .45])], vary(CANVAS, .05))
    shelf(m, d, frame3(back, z), 2.4, 1.4, 1.4, 2)
    q = Hl(-d2+.35, -.2); basket(d, q[0], q[1], z, .2, .22, fruit=5)
    # the table in the front half, on a rug, three log stools round it
    q = Hl(1.95, .5); rug(d, q[0], q[1], z, 2.0, 2.6, ang, 'rug_blue'); prop('log_table', q[0], q[1], z+.012, ang+25, 1.)
    # a work table in the back half, between the counter and the lane: a chopping board, bowls, a basket of greens
    top = table(m, Hl(-1.6, 1.75), ang, .6, 1.25, .8)
    block(d, top+rot((0, -.3), ang)+[0, 0, .015], rot((1, 0), ang), rot((0, 1), ang), .32, .45, .03, vary(PALE, .05), 'wood_pale')
    for lx, ly, r in ((-.12, .1, .12), (.13, .2, .09)):
        with d.use('flat'):
            d.lathe(tuple(top+rot((lx, ly), ang)), [(0, .01), (.02, r*.6), (r*.7, r), (r*.75, r*.95)], R.choice([(.32, .40, .55), (.62, .58, .50)]), 10)
    q = Hl(-1.6, 2.2, .8); basket(d, q[0], q[1], q[2], .15, .16, fruit=4)
    q = Hl(-1.6, 1.75); crate(m, q[0], q[1], z, (.45, .4, .36), ang+4)          # under the table, between its legs
    # sacks of rice and a basket by the front corner (the lane and the door stay clear)
    for lx, ly, r, hh in ((1.45, -2.95, .22, .52), (1.9, -3.0, .2, .46), (1.62, -2.5, .19, .42)):
        sack(d, Hl(lx, ly), r, hh)
    # outer wall (s = y+w2): a shelf between the windows; persimmons and herbs hung in front of the six-pane window
    o, u, n = frame3(outer, z)
    shelf(m, d, (o, u, n), 3.65, 1.3, 1.1, 2)
    for k in range(5):
        q = o+u*(.75+.45*k)+n*.42
        tube(d, [q+[0, 0, 1.5], q+[0, 0, 2.6]], .008, ROPE, 4)
        for j in range(5 if k % 2 == 0 else 0): persimmon(d, q+[0, 0, 1.55+.1*j])
        if k % 2:
            potted = q+[0, 0, 1.6]
            for j in range(6):
                a_ = j*1.05; tip = potted+[.12*math.cos(a_), .12*math.sin(a_), -.18]
                two_sided(d, [tuple(potted), tuple((potted+tip)/2+[.03, 0, 0]), tuple(tip), tuple((potted+tip)/2-[.03, 0, 0])], vary((.30, .42, .14), .12))
    q = Hl(d2-.55, w2-.55, 2.1); glass_float(d, q[0], q[1], q[2], .14, .35)
    q = Hl(d2-.35, -w2+.4); crate(m, q[0], q[1], z, (.5, .42, .4), ang+6)
    q = Hl(d2-.35, -w2+.4, .4); basket(d, q[0], q[1], q[2], .18, .2, fruit=4)


def furnish_library(m, d, c, ang, side, W):
    """As painted: bookshelves along the back wall between its windows, the desk under the six-pane window with the
    map beside it, the globe on a crate in the corner, a reading rug with cushions under the round window, the
    backpack and crates in the back corners, pictures and the kite on the gables. Hut-local x runs from the back
    wall (-d2) to the outer wall (+d2); the lane from door to door (|x| < 0.75) stays clear."""
    z = c[2]; outer, back, gm, gp = W; d2, w2 = L.HUT[1]/2, L.HUT[0]/2
    Hl = room(c, ang, side)
    for y, sc in ((-.56, 1.), (.56, 1.), (-1.5, .9), (1.5, .9)):      # a wall of books between the two windows
        q = Hl(-d2+.26, y); prop('bookshelf', q[0], q[1], z, lyaw(ang, 1, 0), sc)
    q = Hl(-2.1, -2.35); basket(d, q[0], q[1], z, .19, .26, scrolls=4)
    q = Hl(-d2+.35, 2.8); prop('backpack', q[0], q[1], z, lyaw(ang, 1, -.3), .95)
    q = Hl(-d2+.4, -2.85); crate(m, q[0], q[1], z, (.5, .42, .4), ang+8); crate(m, q[0], q[1], z+.4, (.4, .36, .3), ang-6)
    q = Hl(-1.8, -1.9); book_stack(d, q[0], q[1], z, 5, ang)
    q = Hl(d2-.45, -1.6); prop('crate_desk', q[0], q[1], z, lyaw(ang, -1, 0), 1.)
    q = Hl(1.55, -1.6); cushion(d, q[0], q[1], z, .5, ang+8)
    q = Hl(d2-.35, -w2+.4); crate(m, q[0], q[1], z, (.45, .45, .45), ang); prop('globe', q[0], q[1], z+.45, ang+200, 1.)
    q = Hl(1.85, 1.75); rug(d, q[0], q[1], z, 1.7, 2.3, ang, 'rug')
    for lx, ly, a in ((1.55, 1.3, 10), (2.25, 2.35, -20)):
        q = Hl(lx, ly); cushion(d, q[0], q[1], z+.012, .55, ang+a)
    q = Hl(2.4, 1.05); book_stack(d, q[0], q[1], z+.012, 3, ang+40)
    # the map table in front of the wall map: a chart spread out, a book and a lantern on it
    top = table(m, Hl(2.05, -.15), ang, .7, 1.1, .76)
    cs = [top+rot((a, b), ang)+[0, 0, .006] for a, b in ((-.3, -.45), (.3, -.45), (.3, .45), (-.3, .45))]
    picture(d, [tuple(x) for x in cs], 'map')
    q = top+rot((-.12, .35), ang); book_stack(d, q[0], q[1], q[2]+.012, 2, ang+15)
    o, u, n = frame3(outer, z)
    wall_picture(d, (o, u, n), 3.35, 1.0, 1.9, .075, 'map', .75)
    wall_picture(d, frame3(gm, z), 4.9, 1.2, 2.0, .075, 'kite', .6)       # gable -y s = x+d2, gable +y s = d2-x
    wall_picture(d, frame3(gp, z), 1.1, 1.3, 1.8, .075, 'pictures', .5, True)


def block(m, c, u, n, su, sn, sz, color, kind='wood_timber'):
    """An upright block centred on c: su along the horizontal u, sn along the horizontal n, sz tall."""
    c, u, n = np.asarray(c, float), np.asarray(u, float), np.asarray(n, float)
    corners = [c+u*a*su/2+n*b*sn/2 for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    with m.use(kind, grain=(0, 0, 1), jitter=True):
        hexa(m, [q-[0, 0, sz/2] for q in corners]+[q+[0, 0, sz/2] for q in corners], color)


def strut(m, a, b, w, t, side, color=WOOD, kind='wood_timber'):
    """A square timber centred on the line a-b: w across the horizontal side direction, t across the other."""
    a, b = np.asarray(a, float), np.asarray(b, float); ax = (b-a)/np.linalg.norm(b-a)
    s = np.asarray(side, float); s = s-ax*(s@ax); s /= np.linalg.norm(s); n = np.cross(ax, s)
    ring_ = [s*i*w/2+n*j*t/2 for i, j in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    with m.use(kind, grain=tuple(ax), jitter=True):
        hexa(m, [a+q for q in ring_]+[b+q for q in ring_], color)


def hammock(d, a0, a1, sag, width, ends, pic='quilt'):
    """A quilt hammock slung between two fixings: a deep bag gathered to a point at both ends, a fan of strings into
    each end and one rope to the fixing. Each end is ('wall', inward normal): a peg on a wooden plate at a0/a1 on the
    wall's inside face; or ('wrap', centre, radius): turns of rope round a trunk or post, a0/a1 on the rope."""
    fix = []
    for a, e in ((a0, ends[0]), (a1, ends[1])):
        a = np.asarray(a, float)
        if e[0] == 'wall':
            n = np.array([e[1][0], e[1][1], 0.]); n /= np.linalg.norm(n); u = np.cross(n, [0, 0, 1])
            block(d, a+n*.02, u, n, .12, .04, .3, DARK)
            tube(d, [a+n*.03+[0, 0, .03], a+n*.16+[0, 0, .05]], .022, DARK, 6, 'wood_timber')
            tube(d, [a+n*.1+[0, 0, .04], a+n*.14+[0, 0, .045]], .034, ROPE, 6)
            fix.append(a+n*.12+[0, 0, .03])
        else:
            c, r = e[1], e[2]
            for dz in (-.025, .025): ring(d, c, r, a[2]+dz, .02, ROPE, 18)
            fix.append(a)
    e0, e1 = fix; ax = (e1-e0)/np.linalg.norm(e1-e0); across = np.cross(ax, [0, 0, 1]); across /= np.linalg.norm(across)
    ts = np.linspace(.12, .88, 13); fs = np.linspace(-1, 1, 7)
    def pt(t, f):
        w = width*math.sin(math.pi*(t-.12)/.76)**.5          # gathered at the ends
        return e0+(e1-e0)*t-[0, 0, sag*math.sin(math.pi*t)+.16*w/width*(1-f*f)]+across*f*w/2
    with d.use(pic):
        for i in range(len(ts)-1):
            for j in range(len(fs)-1):
                quad = [pt(ts[i], fs[j]), pt(ts[i+1], fs[j]), pt(ts[i+1], fs[j+1]), pt(ts[i], fs[j+1])]
                uv = [(i/12, j/6), ((i+1)/12, j/6), ((i+1)/12, (j+1)/6), (i/12, (j+1)/6)]
                d.poly([tuple(x) for x in quad], WHITE, uv=uv); d.poly([tuple(x) for x in quad[::-1]], WHITE, uv=uv[::-1])
    for e, t0, t1 in ((e0, .12, .03), (e1, .88, .97)):
        knot = e0+(e1-e0)*t1-[0, 0, sag*math.sin(math.pi*t1)]
        tube(d, [e, knot], .014, ROPE, 5)
        for f in (-1, -.5, 0, .5, 1): tube(d, [knot, pt(t0+(ts[1]-ts[0])*(1 if t0 < .5 else -1), f)], .006, ROPE, 4)


def furnish_sleep(m, d, c, ang, side, W):
    """As painted: three futons side by side along the back wall, pillows to it, a shelf over them and a floor
    lantern; in the front half two quilt hammocks slung low along the outer wall, from each gable wall to a post in
    the middle; a rug in front of the futons, a crate of folded quilts, pictures and the kite. Hut-local x runs from
    the back wall (-d2) to the outer wall (+d2); the lane from door to door (|x| < 0.75) stays clear."""
    z = c[2]; outer, back, gm, gp = W; d2, w2 = L.HUT[1]/2, L.HUT[0]/2
    Hl = room(c, ang, side)
    for y in (-2.35, -1.15, .05):   # 1.6 x 1.13 m each
        q = Hl(-d2+.86, y); prop('futon', q[0], q[1], z, ang+180, .8)
    shelf(m, d, frame3(back, z), 4.55, 1.3, 1.5, 2)       # over the pillows (back wall s = w2-y)
    q = Hl(-d2+.35, 1.2); andon(d, q[0], q[1], z, .26, 220)
    q = Hl(-.35, -1.15); rug(d, q[0], q[1], z, 1.3, 3.4, ang, 'rug')
    drawer_chest(m, d, Hl(-d2+.27, 2.5), ang)                   # under the back window, quilts folded on it
    with d.at(tuple(Hl(-d2+.27, 2.5, .85)), ang), d.use('quilt', grain=(1, 0, 0)):
        d.box((0, 0, .07), (.36, .7, .12), WHITE, .03)
    q = Hl(-1.75, 1.6); cushion(d, q[0], q[1], z, .55, ang+12)
    q = Hl(-1.9, 2.6); book_stack(d, q[0], q[1], z, 4, ang)
    q = Hl(-1.3, 2.45); basket(d, q[0], q[1], z, .18, .22, scrolls=2)
    q = Hl(1.25, 2.7); crate(m, q[0], q[1], z, (.45, .4, .34), ang-5)      # the toy crate, a ball on it
    with d.use('flat'):
        d.lathe(tuple(q+[0, 0, .34]), [(0, .005), (.03, .07), (.1, .1), (.17, .07), (.2, .005)], (.75, .22, .12), 10)
    # the hammocks: a post under the ridge's side, the bags hanging about 0.6 m over the floor, clear of the outer
    # wall; their ropes round the post 10 cm apart in height (turns at the same height would lie in one another)
    hx, py = 2.05, .45; pc = Hl(hx, py)
    post(m, pc[0], pc[1], z-.02, z+hut_roof_z(hx)-.01, .14, WOOD)
    for a0, a1, ends in ((Hl(hx, -w2+.045, 1.55), Hl(hx, py-.12, 1.55), (('wall', rot((0, 1), ang)), ('wrap', pc[:2], .1))),
                         (Hl(hx, py+.12, 1.65), Hl(hx, w2-.045, 1.65), (('wrap', pc[:2], .1), ('wall', rot((0, -1), ang))))):
        hammock(d, a0, a1, .8, .42, ends)
    q = Hl(d2-.32, w2-.42); crate(m, q[0], q[1], z, (.5, .45, .42), ang)
    with d.at((q[0], q[1], z+.42), ang), d.use('quilt', grain=(1, 0, 0)):
        d.box((0, 0, .07), (.45, .4, .12), WHITE, .03)
    o, u, n = frame3(outer, z)
    wall_picture(d, (o, u, n), 3.65, 1.75, 2.2, .075, 'pictures', .42, True)
    wall_picture(d, frame3(back, z), 2.5, 1.2, 1.8, .075, 'kite', .5)


def furnish_entry(m, d, p):
    """The genkan of a children's secret base, everything against the walls: the way from door to door stays open
    (1.7 m between the shoe cupboard and the bench, 3.5 m in the middle), and so do the landing at the steps and the
    porch between the south door and the bridge. North wall: the shoe cupboard with the children's shoes and a
    lantern on it, slippers waiting on the floor; a bench under a peg rail with the straw hat, a red scarf, the
    backpack and a coil of rope. West wall: the island map over the treasure chest, a basket of rolled maps under the
    round window, crates and a rolled rug in the corner. East wall: the window seat with cushions under the big
    window, a shelf of jars of acorns and shells. By the south door the umbrella stand; the kite and the children's
    drawings high on the gables; a mat at the north door, a rug in the middle, the big lantern from the ridge.
    Outside: a crate bench against the south wall facing the view, a post lantern and a planter in the porch's far
    corner, a potted plant by the landing, the banner on the east wall, a woodpile on the west wall, the name board
    over the north door."""
    global R
    shared, R = R, random.Random(ENTRY_SEED+1)
    try:
        (X0, X1, Y0, Y1), walls = entry_walls(p)
        N, S, Wl, E = walls['north'], walls['south'], walls['west'], walls['east']
        x0, y0 = p['xy']; z = p['deck']; dx = L.ENTRY_DOOR; dw, dh = L.DOOR
        cx, cy = (X0+X1)/2, (Y0+Y1)/2; jamb = dw/2+.1         # the door jambs' outer faces from the doors' line
        W = lambda x, y, zz=0.: np.array([x0+x, y0+y, z+zz])
        at = wall_point
        # North wall, west of the door: the shoe cupboard (open shelves, a back, a top), shoes on every shelf
        a0, a1 = X0+.15, dx-jamb-.1; B, D, H = .1, .38, .9
        with m.use('wood_plank', grain=(0, 0, 1), jitter=True):
            for a in (a0, a1-.03): slab(m, N, a, a+.03, B, B+D, 0., H-.03, vary(PLANK, .06))
            slab(m, N, a0+.03, a1-.03, B+.003, B+.015, .06, H-.03, vary(BOARD, .05))
        with m.use('wood_plank', grain=tuple(N[1]), jitter=True):
            slab(m, N, a0-.02, a1+.02, B+.005, B+D+.02, H-.03, H, vary(PLANK, .05))
            for zz in (.06, .36, .64): slab(m, N, a0+.03, a1-.03, B+.015, B+D-.01, zz, zz+.025, vary(PLANK, .08))
        with m.use('wood_timber', grain=tuple(N[1])):
            slab(m, N, a0+.03, a1-.03, B+D-.035, B+D-.01, 0., .06, DARK)
        kinds = [('boots', 'sneakers', 'geta', 'boots'), ('geta', 'zori', 'sneakers', 'zori'), ('zori', 'geta', 'zori', 'sneakers')]
        for row, zz in zip(kinds, (.085, .385, .665)):
            for k, kind in enumerate(row):
                a = a0+.22+.32*k
                if a < a1-.15: entry_shoes(d, N, a, B+.05, zz, kind)
        q = at(N, a0+.3, B+D/2); andon(d, q[0], q[1], z+H, .22, 200)
        q = at(N, a1-.3, B+D/2); book_stack(d, q[0], q[1], z+H, 3, R.uniform(-10, 10))
        entry_shoes(d, N, a0+.55, B+D+.12, 0., 'zori'); entry_shoes(d, N, a0+.95, B+D+.1, 0., 'sneakers')
        # North wall, east of the door: a bench, and over it a peg rail with the hat, a scarf, the backpack and rope
        a0, a1 = dx+jamb+.1, X1-.15
        with m.use('wood_plank', grain=tuple(N[1]), jitter=True):
            slab(m, N, a0, a1, .12, .52, .38, .43, vary(PLANK, .06))
        with m.use('wood_timber', grain=(0, 0, 1), jitter=True):
            for a in (a0+.08, a1-.13): slab(m, N, a, a+.05, .15, .49, 0., .38, WOOD)
        with d.use('wood_timber', grain=tuple(N[1]), jitter=True):
            slab(d, N, a0, a1, .1, .13, 1.52, 1.62, DARK)
        pegs = [a0+.2+(a1-a0-.4)*k/3 for k in range(4)]
        for a in pegs: tube(d, [at(N, a, .12, 1.57), at(N, a, .27, 1.61)], .017, WOOD, 6, 'wood_timber')
        with along_axis(d, at(N, pegs[0], .16, 1.45), N[2]):        # the straw hat, its crown to the room
            with d.use('straw'):
                d.lathe((0, 0, 0), [(0, .001), (0, .21), (.02, .22), (.07, .1), (.11, .01)], vary(STRAW, .05), 14)
        red = vary((.72, .16, .10), .05)
        with d.use('canvas', grain=(0, 0, 1)):                        # the scarf, both ends hanging from the peg
            for s, b, lo in ((-.03, .2, .98), (.04, .215, 1.1)):
                two_sided(d, [tuple(at(N, pegs[1]+s-.065, b, lo)), tuple(at(N, pegs[1]+s+.065, b, lo)),
                              tuple(at(N, pegs[1]+s+.065, b, 1.6)), tuple(at(N, pegs[1]+s-.065, b, 1.6))], red)
        q = at(N, pegs[2], .33); prop('backpack', q[0], q[1], z+1.02, 0., .85)
        with along_axis(d, at(N, pegs[3], .2, 1.41), N[2]):          # a coil of rope
            for k, (r, off) in enumerate(((.17, 0.), (.15, .03), (.16, .055))):
                ring(d, (.01*k, -.01*k), r, off, .022, ROPE, 16)
        # West wall: the island map over the treasure chest; a basket of rolled maps under the round window; crates
        # and a rolled rug in the corner by the south door
        a0, a1 = cy-.55, cy+.55
        with m.use('wood_plank', grain=tuple(Wl[1]), jitter=True):
            slab(m, Wl, a0, a1, .12, .6, 0., .4, vary((.42, .21, .1), .05))
            slab(m, Wl, a0-.02, a1+.02, .1, .62, .4, .52, vary((.36, .18, .08), .05))
        with m.use('iron'):
            for a in (a0+.14, a1-.18): slab(m, Wl, a, a+.04, .115, .605, .003, .53, IRON)
            slab(m, Wl, cy-.06, cy+.06, .6, .635, .3, .45, IRON)
        wall_picture_at(d, Wl, cy, .1, 1.2, 1.15, 2.35, 'map')
        q = at(Wl, entry_round_window(), .32); basket(d, q[0], q[1], z, .2, .26, scrolls=4)
        q = W(X0+.45, Y0+.42); crate(m, q[0], q[1], z, (.6, .5, .45), R.uniform(-3, 3))
        crate(m, q[0], q[1], z+.45, (.46, .38, .32), R.uniform(-8, 8))
        with along_axis(d, W(X0+.1, Y0+.44, .86), (1, 0, 0)):
            with d.use('canvas'):
                d.lathe((0, 0, 0), [(0, .001), (0, .09), (.7, .09), (.7, .001)], vary((.62, .22, .12), .05), 12)
        # East wall: the window seat (two crates and a board) with cushions, a shelf of jars toward the south door
        for a in (cy-.5, cy+.5):
            q = at(E, a, .345); crate(m, q[0], q[1], z, (.95, .45, .38), 90)
        with m.use('wood_plank', grain=tuple(E[1]), jitter=True):
            slab(m, E, cy-1.05, cy+1.05, .1, .62, .38, .42, vary(PLANK, .06))
        for a in (cy-.62, cy, cy+.62):
            q = at(E, a, .36); cushion(d, q[0], q[1], z+.42, .48, 90+R.uniform(-6, 6))
        shelf(m, d, (E[0]+E[2]*.09, E[1], E[2]), (Y0+cy-.95)/2, 1.1, 1.0, 2)
        # South wall, east of the door: the umbrella stand, a tub with two closed paper umbrellas leaning in it
        q = at(S, dx+jamb+.35, .3)
        with m.use('wood_plank', grain=(0, 0, 1), jitter=True):
            m.lathe(tuple(q), [(0., .001), (.002, .15), (.44, .165), (.46, .165), (.46, .14), (.12, .13), (.12, .001)], vary(WOOD, .08), 12)
        for zz, r in ((.1, .158), (.36, .167)): ring(d, q[:2], r, q[2]+zz, .012, IRON, 12, 'iron')
        for off, lean, col in ((-.05, 7., (.75, .2, .12)), (.05, -6., (.25, .32, .55))):
            tilt = math.radians(lean); axis = -S[2]*abs(math.sin(tilt))*.8+S[1]*math.sin(tilt)*.6+np.array([0, 0, math.cos(tilt)])
            with along_axis(d, q+S[1]*off+[0, 0, .12], axis):
                with d.use('wood_timber'):
                    d.lathe((0, 0, 0), [(0., .012), (.32, .012)], DARK, 6)
                with d.use('paper'):
                    d.lathe((0, 0, 0), [(.26, .001), (.27, .05), (.4, .07), (.8, .075), (.95, .035), (.99, .001)], vary(col, .05), 12)
                with d.use('wood_timber'):
                    d.lathe((0, 0, 0), [(.98, .012), (1.05, .003)], DARK, 6)
        # the gables over the doors: the kite, the children's drawings; the mat at the north door, the rug, the lantern
        wall_picture_at(d, S, dx, .1, .75, 3.0, 3.75, 'kite', frame=False)
        wall_picture_at(d, N, dx, .1, .7, 3.0, 3.7, 'pictures')
        q = W(dx, Y1-.55); rug(d, q[0], q[1], z, dw+.1, .8, 0, 'rug_blue')
        q = W(cx, cy); rug(d, q[0], q[1], z, 1.9, 2.8, 0, 'rug')
        chochin(d, q[0], q[1], z+3.3, .36, L.ROOF_TOP['entry']-.3-3.3-.36*.63+.02, 700)
        # Outside. A crate bench against the south wall east of the door, facing the view, under the door lantern.
        q = at(S, (dx+jamb+.15+X1-.12)/2, -.285); crate(m, q[0], q[1], z, (1.3, .42, .38), 0)
        for s in (-.32, .32): cushion(d, q[0]+s, q[1], z+.38, .42, R.uniform(-8, 8))
        # The porch's far (south-east) corner: a post lantern and a planter, clear of the view from the south door
        # and of the way to the bridge; a potted plant in the landing's east corner, the banner on the east wall.
        bx0, bx1, by0, by1 = L.ENTRY_BOX
        q = W(bx1-.45, by0+1.5); andon(d, q[0], q[1], z, .3, 300)
        q = W(bx1-.85, by0+.8); prop('planter', q[0], q[1], z, face_yaw(-1, 1), .95)
        q = W(bx1-.65, by1-.85); potted_plant(d, q[0], q[1], z, 1.)
        wall_picture_at(d, E, .4, -.08, .8, 1.35, 2.15, 'flag', frame=False)
        tube(d, [at(E, .4-.47, -.105, 2.18), at(E, .4+.47, -.105, 2.18)], .015, DARK, 6, 'wood_timber')
        for s in (-.43, .43): tube(d, [at(E, .4+s, -.03, 2.18), at(E, .4+s, -.12, 2.18)], .012, DARK, 6, 'wood_timber')
        # The west wall outside, seen from the bridge: a woodpile along its southern half, clear of the way round the
        # corner to the bridge; the hut's name board over the north door, above the sliding door's track.
        entry_woodpile(m, Wl, Y0+.3, Y0+1.9)
        entry_sign(d, N, dx, dh+.21, dh+.46, 1.0)
    finally:
        R = shared


def hall_frame(p):
    """The heart hall (layout HALL): its centre at the deck, the angle of its local x (out from the camphor), apothem,
    wall height, and a map from hall-local metres (x out from the camphor, y to its left) to world."""
    r = p['room']; c = np.array([*r['center'], p['deck']], float); ang = r['angle']
    return c, ang, r['apothem'], r['wall'], (lambda lx, ly, lz=0.: local(c, ang, lx, ly, lz))


def hall_wall(c, ang, A, f):
    """The hall's flat facing f degrees from its x: (the middle of the wall's centre line at the deck, the direction
    along it, counter-clockwise seen from above, the inward normal), in world. Offsets along it are positive toward
    the corner at f+22.5."""
    a = math.radians(ang+f); out = np.array([math.cos(a), math.sin(a), 0.])
    return c+out*A, np.array([-out[1], out[0], 0.]), -out


def on_wall(frame, s, depth, zz=0.):
    """A point s along a wall frame, depth in from its centre line, zz up."""
    o, u, n = frame
    return o+u*s+n*depth+np.array([0., 0., zz])


def wall_yaw(frame):
    """The frame's yaw: a local x along the wall and local y into the room."""
    return math.degrees(math.atan2(frame[1][1], frame[1][0]))


def slab_table(m, x, y, z, r=.75, h=.38):
    """A low round table for sitting round on cushions: a thick slice of a big log, bark round its edge and a pale
    sawn top, on three stubby log legs."""
    with m.use('bark', grain=(0, 0, 1), jitter=True):
        for k in range(3):
            a = 2*math.pi*k/3+.4
            m.lathe((x+r*.5*math.cos(a), y+r*.5*math.sin(a), z), [(0, .13), (.05, .12), (h-.09, .1)], vary(BARK, .06), 10)
        m.lathe((x, y, z), [(h-.1, r*.95), (h-.07, r), (h, r)], vary(BARK, .05), 24)
    ring_ = [(math.cos(a), math.sin(a)) for a in np.linspace(0, 2*math.pi, 25)[:-1]]
    with m.use('wood_pale'):
        m.poly([(x+r*cx, y+r*cy, z+h) for cx, cy in ring_], vary(PALE, .05))
        m.poly([(x+r*.95*cx, y+r*.95*cy, z+h-.1) for cx, cy in ring_][::-1], vary(PALE, .05))
    for k in (1, 2, 3):      # growth rings on the top
        ring(m, (x, y), r*(.22*k+.05), z+h+.002, .004, vary(WOOD, .05), 20, 'wood_timber')


def window_bench(m, d, frame, s, length, z, depth=.5, h=.42, back=.1):
    """A built-in bench along a wall under a window: a plank box with a seat board, stiles down its front and an
    indigo pad."""
    q = on_wall(frame, s, back+depth/2); yaw = wall_yaw(frame)
    with m.at((q[0], q[1], z), yaw):
        with m.use('wood_plank', grain=(1, 0, 0), jitter=True):
            m.box((0, -.01, (h-.035)/2), (length-.08, depth-.06, h-.045), vary(BOARD, .06))
            m.box((0, 0, h-.02), (length, depth, .04), vary(PLANK, .06))
        with m.use('wood_timber', grain=(0, 0, 1), jitter=True):
            for x in np.linspace(-length/2+.07, length/2-.07, 4):
                m.box((x, depth/2-.045, (h-.05)/2), (.08, .06, h-.05), DARK)
    with d.at((q[0], q[1], z+h), yaw):
        with d.use('indigo', grain=(1, 0, 0)):
            d.box((0, .01, .045), (length-.12, depth-.1, .08), INDIGO, .03)


def tansu(m, d, frame, s, length, z, depth=.45, h=.55, back=.1):
    """A low chest of drawers against a wall: dark wood, three drawers with iron pulls."""
    q = on_wall(frame, s, back+depth/2); yaw = wall_yaw(frame)
    with m.at((q[0], q[1], z), yaw):
        with m.use('wood_timber', grain=(1, 0, 0), jitter=True):
            m.box((0, 0, h/2), (length, depth, h), vary(WOOD, .06))
            m.box((0, 0, h+.015), (length+.04, depth+.03, .03), DARK)
        w = (length-.08)/3
        for k in range(3):
            x = -length/2+.04+w*(k+.5)
            with m.use('wood_plank', grain=(1, 0, 0), jitter=True):
                m.box((x, depth/2+.008, h/2), (w-.03, .016, h-.1), vary(PLANK, .08))
            with m.use('iron'):
                m.box((x, depth/2+.03, h/2+.05), (.12, .025, .025), IRON)


def loft(m, d, frame, A, s0, z, top=2.8, deep=.8):
    """A sleeping shelf high on a wall (from s0 to the corner), on knee braces, with a low rail, folded quilts, one
    hanging over the edge, and a ladder fixed flat to the wall beside it. Everything on it is above head height."""
    t = math.tan(math.radians(22.5)); o, u, n = frame
    far = lambda dd: (A-dd)*t-.16                  # the adjacent wall cuts the corner end at 45 degrees
    q = lambda s_, dd, zz: on_wall(frame, s_, dd, zz)
    base = [q(s0, .1, 0), q(far(.1), .1, 0), q(far(deep), deep, 0), q(s0, deep, 0)]
    with m.use('wood_plank', grain=tuple(u), jitter=True):
        hexa(m, [b+[0, 0, top-.08] for b in base]+[b+[0, 0, top] for b in base], vary(PLANK, .08))
    board(m, q(s0+.02, deep-.06, top-.08), q(far(deep)-.02, deep-.06, top-.08), .1, .12, DARK, 'wood_timber')
    board(m, q(s0+.02, .16, top-.08), q(far(.16)-.02, .16, top-.08), .1, .1, DARK, 'wood_timber')
    for s_ in (s0+.35, far(deep)-.3):             # knee braces from the wall to the front beam
        strut(m, q(s_, .15, top-.95), q(s_, deep-.1, top-.19), .08, .08, u, WOOD)
    # a low rail along the front, the quilts, one hanging 20 cm over the edge
    xs = [s0+.06, (s0+far(deep))/2, far(deep)-.08]
    for s_ in xs: post(m, *q(s_, deep-.05, 0)[:2], z+top, z+top+.3, .06, WOOD)
    board(m, q(xs[0], deep-.05, top+.32), q(xs[-1], deep-.05, top+.32), .07, .04, WOOD, 'wood_timber')
    for k, s_ in enumerate(np.linspace(s0+.4, far(.45)-.35, 3)):
        c_ = q(s_, .45, top); yaw = wall_yaw(frame)+R.uniform(-6, 6)
        with d.at(tuple(c_), yaw):
            with d.use('quilt' if k != 1 else 'canvas', grain=(1, 0, 0)):
                d.box((0, 0, .08), (.6, .5, .15-.02*k), WHITE if k != 1 else vary(CANVAS, .05), .04)
    e0, e1 = q(s0+.55, deep+.02, top+.01), q(s0+1.25, deep+.02, top+.01)
    with d.use('quilt'):
        cloth(d, [tuple(e0-[0, 0, .2]), tuple(e1-[0, 0, .2]), tuple(e1), tuple(e0)], [(0, 0), (1, 0), (1, .3), (0, .3)], [0, 0, 0, 0])
    # the ladder, flat to the wall beside the loft's end
    for s_ in (s0-.5, s0-.1):
        post(m, *q(s_, .15, 0)[:2], z, z+top+.35, .06, WOOD)
    for k in range(1, 12):
        zz = .28*k
        if zz > top+.2: break
        tube(m, [q(s0-.47, .15, zz), q(s0-.13, .15, zz)], .02, WOOD, 6, 'wood_timber')


def furnish_heart(m, d, p):
    """The hall where the children meet, big and open in the middle, everything low against the walls: a low round
    log table on a rug toward the front window with cushions round it and the kettle stump; a window bench on the
    camphor side between the doors; bookshelves with the island map over them; a quilt hammock across the corner;
    a sleeping loft high on the wall with its ladder, a chest under the window; the view window left clear."""
    c, ang, A, h, H_ = hall_frame(p); z = c[2]
    W = {f: hall_wall(c, ang, A, f) for f in range(0, 360, 45)}
    # the table group, off the middle toward the front window (the door lanes end in the middle, clear)
    tx = 2.0; q = H_(tx, 0); rug(d, q[0], q[1], z, 2.9, 2.9, ang, 'rug')
    slab_table(m, q[0], q[1], z, .75, .38)
    k_ = H_(tx+1.22, 0); prop('stump_kettle', k_[0], k_[1], z+.012, face_yaw(*(q-k_)[:2]))
    for a in (60, 120, 240, 300):
        cq = H_(tx+1.15*math.cos(math.radians(a)), 1.15*math.sin(math.radians(a)))
        cushion(d, cq[0], cq[1], z+.012, .7, ang+a+R.uniform(-8, 8))
    # the window bench under the round window onto the camphor, between the doors
    window_bench(m, d, W[180], 0., 2.6, z)
    for s_ in (-.8, .8):
        cq = on_wall(W[180], s_, .38); cushion(d, cq[0], cq[1], z+.5, .45, wall_yaw(W[180])+R.uniform(-10, 10))
    # the shelf wall: two bookshelves side by side, the island map above them; the bell beside the front window
    for s_ in (-.5, .5):
        bq = on_wall(W[90], s_, .1+.225); prop('bookshelf', bq[0], bq[1], z, face_yaw(*W[90][2][:2]))
    wall_picture(d, W[90], 0., 2.0, 2.85, .1, 'map', 1.15)
    bq = on_wall(W[0], -1.4, .3); prop('bell', bq[0], bq[1], z+1.4, face_yaw(*W[0][2][:2]), .8)
    # the quilt hammock across the corner in front of the flat at 45, on pegs in the flats either side
    a0 = on_wall(W[0], 1.25, .055, 1.75); a1 = on_wall(W[90], -1.25, .055, 1.75)
    hammock(d, a0, a1, .85, .5, (('wall', W[0][2][:2]), ('wall', W[90][2][:2])))
    wall_picture(d, W[45], 0., 1.95, 2.75, .1, 'pictures', .8, True)
    # the loft over the flat at 315, its ladder beside it, a low chest and a plant under the window
    loft(m, d, W[315], A, -.95, z)
    tansu(m, d, W[315], .25, 1.3, z)
    q = on_wall(W[315], .55, .33, .58); potted_plant(d, q[0], q[1], q[2], .9)
    q = on_wall(W[315], -.05, .3, .58); book_stack(d, q[0], q[1], q[2], 3, wall_yaw(W[315]))
    # beside the doors: the kite and the children's drawings flat on the walls; the backpack and the scroll basket
    # on the floor in the corners past them
    wall_picture(d, W[225], 1.3, 1.15, 1.95, .062, 'kite', .6)
    wall_picture(d, W[135], -1.3, 1.25, 1.75, .062, 'pictures', .5, True)
    q = H_(*(3.9*np.array([math.cos(math.radians(112.5)), math.sin(math.radians(112.5))])))
    prop('backpack', q[0], q[1], z, face_yaw(*(c-q)[:2]))
    q = H_(*(3.95*np.array([math.cos(math.radians(247.5)), math.sin(math.radians(247.5))])))
    basket(d, q[0], q[1], z, .22, .26, scrolls=4)
    # a wind bell in the top of the view window
    q = on_wall(W[270], 0., 0.); fuurin(d, q[0], q[1], z+2.23, .1)


def furnish_boat(m, d, p, c, ang):
    """Under the hull: two bunks end to end along the outer gunwale (away from the trunk and the bridges), each with a
    quilt and a pillow, under one plank back; a sea chest with the rolled sail and a rope coil on the trunk side at
    the ends; a blue rug down the middle; oars lashed up in the hull, the fishing net slung under the keel and glass
    floats hanging from it, all above 2.9 m. The middle, end to end, and the trunk side stay clear."""
    z = c[2]; half = L.BOAT['length']/2
    B = lambda lx, ly, lz=0.: local(c, ang+90, lx, ly, lz)
    q = B(0, 0); rug(d, q[0], q[1], z, 1.3, 4.6, ang, 'rug_blue')
    # the bunks: x -2.05..2.05, y -1.42..-0.82 (the middle lane is |y| < 0.7)
    with m.at(tuple(B(0, -1.12)), ang+90):
        with m.use('wood_plank', grain=(1, 0, 0), jitter=True):
            m.box((0, .03, .2), (3.98, .48, .4), vary(BOARD, .06))              # the body, set back from the front
            m.box((0, .03, .43), (4.1, .56, .05), vary(PLANK, .06))             # the seat
            m.box((0, -.28, .45), (4.1, .05, .9), vary(BOARD, .06))             # the back, both faces planked
        with m.use('wood_timber', grain=(1, 0, 0), jitter=True):
            m.box((0, -.28, .92), (4.16, .09, .05), DARK)                       # the cap on the back
            for x in (-2.04, 0., 2.04):
                m.box((x, .03, .3325), (.06, .6, .655), DARK)                  # the ends and the middle board, arm high
    with d.at(tuple(B(0, -1.09, .455)), ang+90):
        with d.use('quilt', grain=(1, 0, 0)):
            for x in (-1., 1.):                                                 # two bunks, a quilt on each
                d.box((x, 0, .06), (1.86, .48, .11), WHITE, .03)
        with d.use('canvas', grain=(1, 0, 0)):
            for x in (-1.6, 1.62):
                d.box((x, -.06, .19), (.5, .3, .15), vary(CANVAS, .05), .05)
    # the sea chest and the rolled sail at the stern, a rope coil at the bow, both on the trunk side under the gunwale
    q = B(-2.7, 1.0); crate(m, q[0], q[1], z, (.9, .45, .45), ang+90, vary((.42, .25, .14), .05))
    sail = [B(-3.12+.84*t, 1.0, .45+.13) for t in np.linspace(0, 1, 5)]
    tube(d, sail, .13, vary(CANVAS, .04), 10, 'canvas')
    for t in (.2, .8):
        x = -3.12+.84*t
        tube(d, [B(x, 1.0+.14*math.cos(a), .58+.14*math.sin(a)) for a in np.linspace(0, 2*math.pi, 11)], .012, ROPE, 4)
    q = B(2.7, 1.05); rope_coil(d, q[0], q[1], z)
    # two oars up in the hull, one each side, lashed to the ribs
    for sgn in (-1, 1):
        y = sgn*.85; zz = min(hull_z(x, y) for x in np.linspace(-1.6, 1.4, 7))-.1
        a, b = B(-1.6, y, zz), B(1.1, y, zz)
        board(d, a, b, .06, .05, PALE, 'wood_pale')
        with d.at(tuple(b), ang+90):
            with d.use('wood_pale', grain=(1, 0, 0)):
                d.box((.27, 0, -.025), (.55, .16, .025), PALE)
        for x in (-.95, .45):
            tube(d, [B(x, y, zz-.06), B(x, y, hull_z(x, y)-.01)], .012, ROPE, 4)
    # the fishing net slung under the keel toward the bow, floats hanging from it
    xs, ys = np.linspace(.5, 2.3, 7), np.linspace(-.55, .55, 5)
    net = lambda x, y: hull_z(x, y)-.07-.2*math.sin(math.pi*(x-xs[0])/(xs[-1]-xs[0]))*math.sin(math.pi*(y-ys[0])/(ys[-1]-ys[0]))
    fine = np.linspace(0, 1, 9)
    for x in xs:
        tube(d, [B(x, y, net(x, y)) for y in ys[0]+(ys[-1]-ys[0])*fine], .008, ROPE, 4)
    for y in ys:
        tube(d, [B(x, y, net(x, y)) for x in xs[0]+(xs[-1]-xs[0])*fine], .008, ROPE, 4)
    for x, y in ((1.1, -.3), (1.7, .28), (2.05, -.1)):
        zt = net(x, y); q = B(x, y); glass_float(d, q[0], q[1], z+zt-.1-.11, .11, .1)


# ---------------------------------------------------------------------------------------------- special rooms

ENTRY_SEED = 1107       # the little hut's own random streams: changing it never reshuffles what is built after it


def entry_walls(p):
    """The little hut's walls in metres from its maple (L.ENTRY_HUT: x0, x1 east, y0, y1 north), and each wall as
    (a point of its centre line at the deck, the direction along it, the direction into the hut). Along the north and
    south walls a position is x from the maple, along the west and east walls y."""
    x, y = p['xy']; X0, X1, Y0, Y1 = L.ENTRY_HUT; O = np.array([x, y, p['deck']])
    ex, ey = np.array([1., 0, 0]), np.array([0, 1., 0])
    return (X0, X1, Y0, Y1), dict(north=(O+ey*Y1, ex, -ey), south=(O+ey*Y0, ex, ey), west=(O+ex*X0, ey, ex),
                                  east=(O+ex*X1, ey, -ex))


def entry_round_window():
    """Where the west wall's round window is (y from the maple): level with the maple, clear of the corners."""
    X0, X1, Y0, Y1 = L.ENTRY_HUT
    return min(Y1-.8, max(Y0+.8, 0.))


def wall_point(wall, a, b, zz=0.):
    """A point a along a wall (entry_walls), b in from its centre line (outside if negative), zz over the deck."""
    o, u, n = wall
    return o+u*a+n*b+np.array([0, 0, zz])


def slab(m, wall, a0, a1, b0, b1, z0, z1, color):
    """A box square to a wall (entry_walls): a0..a1 along it, b0..b1 in from its centre line, z0..z1 over the deck."""
    q = lambda a, b, zz: tuple(wall_point(wall, a, b, zz))
    hexa(m, [q(a0, b0, z0), q(a1, b0, z0), q(a1, b1, z0), q(a0, b1, z0), q(a0, b0, z1), q(a1, b0, z1), q(a1, b1, z1),
             q(a0, b1, z1)], color)


def wall_picture_at(d, wall, a, b, w, z0, z1, pic, frame=True):
    """A picture flat on a wall (entry_walls), w wide from z0 to z1, centred a along it, b in from its centre line (on
    the outside if negative), upright seen from that side; a dark frame round it, 2 cm proud."""
    f = wall[2]*math.copysign(1., b); r = np.cross([0, 0, 1.], f); c = wall_point(wall, a, b)
    q = lambda s, zz, t=0.: tuple(c+r*s+f*t+[0, 0, zz])
    picture(d, [q(-w/2, z0), q(w/2, z0), q(w/2, z1), q(-w/2, z1)], pic)
    if frame:
        fw = .05
        with d.use('wood_timber'):
            for s0, s1, za, zb in ((-w/2-fw, w/2+fw, z0-fw, z0), (-w/2-fw, w/2+fw, z1, z1+fw), (-w/2-fw, -w/2, z0, z1),
                                   (w/2, w/2+fw, z0, z1)):
                hexa(d, [q(s0, za, -.015), q(s1, za, -.015), q(s1, za, .02), q(s0, za, .02),
                         q(s0, zb, -.015), q(s1, zb, -.015), q(s1, zb, .02), q(s0, zb, .02)], DARK)


class along_axis:
    """`with along_axis(mesh, point, axis):` builds in a frame at point whose z runs along axis (lathes, rings)."""
    def __init__(self, mesh, point, axis):
        from mathutils import Matrix
        v = Vector(tuple(float(c) for c in axis)).normalized()
        M = v.to_track_quat('Z', 'Y' if abs(v.y) < .9 else 'X').to_matrix().to_4x4()
        M.translation = Vector(tuple(float(c) for c in point))
        self.mesh, self.M = mesh, Matrix(M)

    def __enter__(self):
        self.old = self.mesh.transform; self.mesh.transform = self.old@self.M

    def __exit__(self, *_):
        self.mesh.transform = self.old


def entry_shoes(d, wall, a, b, zz, kind):
    """A pair of small shoes side by side, a along a wall, from b to b+23 cm in from it (toes out), on zz: geta,
    straw zori, rain boots or canvas sneakers."""
    for s in (-.06, .06):
        A = a+s
        if kind == 'geta':
            with d.use('wood_pale', grain=tuple(wall[2])):
                slab(d, wall, A-.045, A+.045, b, b+.22, zz+.04, zz+.065, vary(PALE, .06))
                for t in (.03, .165): slab(d, wall, A-.04, A+.04, b+t, b+t+.025, zz+.002, zz+.04, WOOD)
        elif kind == 'zori':
            with d.use('straw', grain=tuple(wall[2])):
                slab(d, wall, A-.045, A+.045, b, b+.23, zz+.002, zz+.022, vary(STRAW, .06))
            with d.use('canvas'):
                slab(d, wall, A-.035, A+.035, b+.17, b+.19, zz+.022, zz+.036, (.62, .12, .08))
        elif kind == 'boots':
            with d.use('flat'):
                c = vary((.85, .62, .12), .05)
                slab(d, wall, A-.045, A+.045, b, b+.23, zz+.002, zz+.07, c)
                slab(d, wall, A-.042, A+.042, b+.005, b+.1, zz+.07, zz+.2, c)
        else:
            with d.use('flat'):
                slab(d, wall, A-.045, A+.045, b, b+.23, zz+.002, zz+.022, (.9, .88, .82))
            with d.use('canvas'):
                slab(d, wall, A-.04, A+.04, b+.01, b+.22, zz+.022, zz+.075, vary((.25, .34, .6), .06))


def entry_woodpile(m, wall, a0, a1, depth=.42, rows=4):
    """Split logs stacked outside a wall (entry_walls) from a0 to a1 along it, their cut ends out, on two sleepers
    and held by a pair of posts at each end. Logs lie a finger apart, so no two cut ends share a plane and touch."""
    r, step, rise = .075, .16, .14
    with m.use('wood_timber', grain=tuple(wall[1])):
        for b in (-.14, -.07-depth+.07): slab(m, wall, a0, a1, b-.03, b+.03, 0., .03, DARK)
    for row in range(rows):
        off = step/2*(row % 2); n = int((a1-a0-.16-off)/step)
        for k in range(n):
            a = a0+.08+r+off+k*step; rr = r*R.uniform(.85, 1.05); zz = .03+r+row*rise
            with along_axis(m, wall_point(wall, a, -.07, zz), -wall[2]):
                ln = depth*R.uniform(.9, 1.)
                with m.use('bark'):
                    m.lathe((0, 0, 0), [(0., rr), (ln, rr)], vary(BARK, .12), 7)
                with m.use('wood_pale'):
                    m.poly([(rr*math.cos(t), rr*math.sin(t), ln) for t in np.linspace(0, 2*math.pi, 8)[:-1]], vary(PALE, .08))
    for a in (a0+.03, a1-.03):
        for b in (-.1, -.07-depth+.03):
            q = wall_point(wall, a, b); post(m, q[0], q[1], -.02+q[2], q[2]+.03+rows*rise+.08, .05, WOOD)


def entry_sign(d, wall, a, z0, z1, w):
    """The hut's name board: a pale plank in a dark frame flat on the outside of a wall (entry_walls), a along it,
    with a red maple leaf painted on it."""
    with d.use('wood_pale', grain=tuple(wall[1]), jitter=True):
        slab(d, wall, a-w/2, a+w/2, -.09, -.055, z0, z1, vary(PALE, .04))
    with d.use('wood_timber', grain=tuple(wall[1])):
        for a0, a1, zb, zt in ((a-w/2-.03, a+w/2+.03, z0-.03, z0), (a-w/2-.03, a+w/2+.03, z1, z1+.02),
                               (a-w/2-.03, a-w/2, z0, z1), (a+w/2, a+w/2+.03, z0, z1)):
            slab(d, wall, a0, a1, -.1, -.055, zb, zt, DARK)
    f = -wall[2]; r = np.cross([0, 0, 1.], f); c = wall_point(wall, a, -.096, (z0+z1)/2); s = (z1-z0)*.4
    pts = []
    for k in range(10):
        rr = s*(1 if k % 2 == 0 else .45)*(1.15 if k == 0 else 1); t = math.pi/2+2*math.pi*k/10
        pts.append(tuple(c+r*rr*math.cos(t)+np.array([0, 0, rr*math.sin(t)])))
    with d.use('flat'):
        d.poly(pts, vary((.78, .2, .08), .04))


def entry_hut(m, d, p):
    """The little hut east of its maple, L.ENTRY_HUT from the trunk: plank walls L.WALL high on a timber frame, open to
    the rafters under a gable roof whose ridge runs north-south. A door L.DOOR in each gable at L.ENTRY_DOOR, with its
    noren, a plank sliding door parked open against the wall west of it and a lantern on a bracket east of it; a
    six-pane window in the east wall over the window seat, a round window in the west wall looking at the maple.
    Nothing stands on the landing at the steps or on the porch's way from the south door to the bridge."""
    global R
    shared, R = R, random.Random(ENTRY_SEED)
    try:
        (X0, X1, Y0, Y1), walls = entry_walls(p)
        x0, y0 = p['xy']; z = p['deck']; h = L.WALL; dw, dh = L.DOOR; dx = L.ENTRY_DOOR
        cx, cy, hx, hy = (X0+X1)/2, (Y0+Y1)/2, (X1-X0)/2, (Y1-Y0)/2
        W = lambda x, y, zz=0.: np.array([x0+x, y0+y, z+zz])
        with m.at(tuple(W(cx, cy)), 90):      # local x north, local y west: the ridge runs north-south
            wall(m, (hy, hx), (hy, -hx), h, [(dx-X0, dw, 0., dh, 'door')])                  # north gable, west to east
            wall(m, (-hy, -hx), (-hy, hx), h, [(X1-dx, dw, 0., dh, 'door')])                # south gable, east to west
            wall(m, (-hy, hx), (hy, hx), h, [(entry_round_window()-Y0, .9, 1.3, 2.2, 'round')])   # west, south to north
            wall(m, (hy, -hx), (-hy, -hx), h, [(Y1-cy, 1.6, .85, 2.0, 'window')])           # east, north to south
            for u in (-hy, hy):
                for v in (-hx, hx): post(m, u, v, -.04, h+.05, .16, DARK)
            # the roof on a stream of its own: the two slopes' top courses meet at the ridge, and a stream whose
            # shingle runs never end at the same place on both sides (checked by zfight.py) stays that way
            hut_R, R = R, random.Random(ENTRY_SEED+3)
            gable_roof(m, d, 2*hy, 2*hx, h-.08, L.ROOF_TOP['entry'])
            R = hut_R
        for wl, yaw, pic in ((walls['north'], 0, 'noren_indigo'), (walls['south'], 180, 'noren_cream')):
            # the noren's rod in the door head, the strips hanging to 1.7 m
            q = wall_point(wl, dx, -.03, dh-.03); noren(d, q[0], q[1], q[2], dw-.04, .8, yaw, pic)
            # the sliding door, parked open west of the doorway on its track over the door head
            a0, a1 = dx-dw/2-dw-.1, dx-dw/2; k = round((a1-a0)/.2)
            with m.use('wood_plank', grain=(0, 0, 1), jitter=True):
                for i in range(k):
                    slab(m, wl, a0+(a1-a0)*i/k, a0+(a1-a0)*(i+1)/k-.006, -.15, -.11, .02, dh+.08, vary(BOARD, .09))
            with m.use('wood_timber', grain=(1, 0, 0), jitter=True):
                for zz in (.4, dh-.3): slab(m, wl, a0+.05, a1-.05, -.18, -.15, zz, zz+.1, DARK)
                slab(m, wl, a0-.1, dx+dw/2+.12, -.18, -.105, dh+.1, dh+.17, DARK)
            with m.use('iron'):
                for a in (a0+.2, a1-.2): slab(m, wl, a-.02, a+.02, -.145, -.115, dh+.06, dh+.11, IRON)
            # the lantern east of the door, on a bracket at the top of the wall: all of it over 2.5 m
            a = dx+dw/2+.5
            with d.use('wood_timber', grain=tuple(-wl[2])):
                slab(d, wl, a-.025, a+.025, -.5, -.03, dh+.42, dh+.47, DARK)
                slab(d, wl, a-.06, a+.06, -.075, -.045, dh+.18, dh+.48, DARK)     # under the wall's top (3 m)
            q = wall_point(wl, a, -.42, dh+.2); chochin(d, q[0], q[1], q[2], .26, .08, 300)
        # a glass float at both eastern eave corners and a wind chime under the east eave, off every walk and hung
        # short from the eave (3 m), so nothing hangs lower than 2.5 m
        for y in (Y1+.2, Y0-.2):
            q = W(X1+.22, y); glass_float(d, q[0], q[1], z+2.7, .12, .18)
        q = W(X1+.22, cy); fuurin(d, q[0], q[1], z+2.84, .06)
        interior(tuple(W(cx, cy, h/2)), (hx-.05, hy-.05, h/2+.35))
        q = W(cx, cy); light(q[0], q[1], z+1.2, 250, 3.8)      # warm fill low in the room
        leaves_on(d, [tuple(W(x, y)[:2]) for x, y in ((X0+.3, Y0+.3), (X1-.3, Y0+.3), (X1-.3, Y1-.3), (X0+.3, Y1-.3))], z, 6)
        furnish_entry(m, d, p)
    finally:
        R = shared


def shimenawa(d, p, name, h):
    """A thick twisted straw rope hugging the trunk at h above the deck, with zigzag paper shide."""
    x0, y0 = p['xy']; z = p['deck']
    _, rad, wob, ph, _ = trunk_shape(x0, y0, p['trunk'], p['trunk_top'], z, len(name))
    zr = z+h; o = np.array([x0, y0])+wob(zr); rt = lambda a: rad(zr)*(1+.05*math.sin(5*a+ph[0]))+.055
    for tw in (0, 1):
        pts = [(o[0]+(rt(a)+.026*math.cos(11*a+tw*math.pi))*math.cos(a), o[1]+(rt(a)+.026*math.cos(11*a+tw*math.pi))*math.sin(a),
                zr+.026*math.sin(11*a+tw*math.pi)) for a in np.linspace(0, 2*math.pi, 121)]
        tube(d, pts, .042, STRAW, 8, 'straw')
    for k in range(6):
        a = math.radians(30+60*k); cx, cy = o[0]+(rt(a)+.03)*math.cos(a), o[1]+(rt(a)+.03)*math.sin(a); t = np.array([-math.sin(a), math.cos(a)])*.045
        zig = [(cx-t[0], cy-t[1], zr-.06), (cx+t[0], cy+t[1], zr-.06), (cx+t[0], cy+t[1], zr-.17), (cx, cy, zr-.2),
               (cx-t[0], cy-t[1], zr-.31), (cx, cy, zr-.33)]
        with d.use('flat'):
            two_sided(d, zig[:4], SHIDE); two_sided(d, [zig[2], zig[3], zig[5], zig[4]], SHIDE)


HALL_OPENINGS = {   # the hall's flats (degrees from its x, out from the camphor): what is in each wall
    0: (1.8, .85, 2.1, 'window'),           # the front window over the table
    45: None,                               # the hammock and the drawings
    90: None,                               # the bookshelves and the map
    135: 'door', 225: 'door',               # the doors, facing back past the camphor to the bridges
    180: (1.2, 1.0, 2.2, 'round'),          # onto the camphor and its rope, over the window bench
    270: (1.9, .55, 2.45, 'open-round'),    # the view window: the chime tree and the lookout
    315: (1.3, .85, 2.1, 'window'),         # under the loft
}


def heart_room(m, d, p):
    """The heart hall beside the camphor (layout HALL): eight plastered walls 3.2 m high, the two doors in the flats
    facing back toward the camphor, and an eight-sided shingle roof open to its rafters inside, a king post hanging
    from the top with lantern strings to the corners (all above 2.8 m). The eave comes within HALL['gap'] of the
    bark; the rope round the camphor is at 2.5 m, over the ways round it."""
    c, ang, A, h, H_ = hall_frame(p); z = c[2]; dw, dh = L.DOOR
    t22 = math.tan(math.radians(22.5)); side = 2*A*t22
    corner = lambda rho, a: (rho/math.cos(math.radians(22.5))*math.cos(math.radians(a)),
                             rho/math.cos(math.radians(22.5))*math.sin(math.radians(a)))
    with m.at(tuple(c), ang):
        for f in range(0, 360, 45):
            o = HALL_OPENINGS[f]
            ops = [] if o is None else [(side/2, dw, 0., dh, 'door')] if o == 'door' else [(side/2, *o)]
            wall(m, corner(A, f-22.5), corner(A, f+22.5), h, ops, outside='plaster', turn=45.)
            with m.at((*corner(A, f+22.5), 0), f+22.5):       # the corner post, square to the corner
                post(m, 0, 0, -.04, h-.03, .22, DARK)
    # The roof: eight planes through the wall plate's outer top edge up to a moss cap, the eaves HALL['over'] out.
    r0, z0 = A+.09, h+.18; rt, ztop = .5, L.ROOF_TOP['heart']-.35
    k = (ztop-z0)/(r0-rt); zr = lambda rho: z0+(r0-rho)*k; under = lambda rho: zr(rho)-.03
    re = A+L.HALL['over']
    P = lambda rho, a, zz: H_(*corner(rho, a), zz)
    for i, f in enumerate(range(0, 360, 45)):
        a0, a1 = f-22.5, f+22.5
        shingled(m, d, [P(re, a0, zr(re)), P(re, a1, zr(re)), P(rt, a1, ztop), P(rt, a0, ztop)], phase=i % 2)
        dz = .005*(i % 2)       # neighbouring fascias overlap in the corners: every other one lower
        board(m, P(re, a0, zr(re)+.02-dz), P(re, a1, zr(re)+.02-dz), .1, .16, DARK, 'wood_timber')
        board(m, P(re+.02, a1, zr(re)+.13), P(rt+.1, a1, ztop+.12), .14, .1, DARK, 'wood_timber')     # the hip cap
        # the wall plate, mitred at the corners, its top under the roof's underside
        lo, hi = A-.09, A+.09
        hexa(m, [P(lo, a0, h-.04), P(lo, a1, h-.04), P(hi, a1, h-.04), P(hi, a0, h-.04),
                 P(lo, a0, under(lo)-.004), P(lo, a1, under(lo)-.004), P(hi, a1, under(hi)-.004), P(hi, a0, under(hi)-.004)], DARK)
        # rafters seen from inside: along the hip and down the middle of the flat
        board(m, P(A-.12, a1, under(A-.12)-.005), P(.8, a1, under(.8)-.005), .1, .12, WOOD, 'wood_timber')
        mid = lambda rho, zz: H_(rho*math.cos(math.radians(f)), rho*math.sin(math.radians(f)), zz)
        board(m, mid(A-.12, under(A-.12)-.005), mid(.8, under(.8)-.005), .08, .1, WOOD, 'wood_timber')
    # the cap over the top: dark wood under (seen from inside, round the king post), moss over, a short finial
    with m.use('wood_timber'):
        prism(m, [tuple(P(.66, 22.5+45*j, 0)[:2]) for j in range(8)], z+ztop-.18, z+ztop-.06, DARK)
    with m.use('moss'):
        prism(m, [tuple(P(.7, 22.5+45*j, 0)[:2]) for j in range(8)], z+ztop-.06, z+ztop+.12, vary(MOSS), vary(MOSS, .1))
    with m.use('wood_timber', grain=(0, 0, 1)):
        m.lathe(tuple(H_(0, 0, ztop+.12)), [(0, .09), (.08, .06), (.13, .08), (.2, .035), (.23, .001)], DARK, 8)
    # the king post, its ring at 4 m and the lantern strings to the corners at the wall plate
    post(m, *H_(0, 0)[:2], z+4.0, z+ztop-.12, .16, WOOD)
    hub = H_(0, 0, 4.05); ring(d, hub[:2], .12, hub[2], .025, ROPE, 12)
    for f in range(0, 360, 45):
        a = f+22.5; s0 = H_(*corner(.1, a), 4.05); s1 = H_(*corner(A-.11, a), h+.05)
        pts = [s0+(s1-s0)*t-[0, 0, .3*math.sin(math.pi*t)] for t in np.linspace(0, 1, 9)]
        tube(d, pts, .009, ROPE, 4)
        q = s0+(s1-s0)*.5-[0, 0, .3]; chochin(d, q[0], q[1], q[2]-.25, .24, .1)
    # the doors: noren just outside the header, a lantern under the eave beside each (on the front side, off the way
    # to the bridges), glass floats at the four front corners
    for i, f in enumerate((135, 225)):
        W = hall_wall(c, ang, A, f); q = on_wall(W, 0, -.14)
        noren(d, q[0], q[1], z+dh-.06, 1.2, .62, wall_yaw(W), 'noren_indigo' if i == 0 else 'noren_cream')
        q = on_wall(W, -1.15 if f == 135 else 1.15, -.45); chochin(d, q[0], q[1], z+2.72, .28, .15, 280)
    for a in (22.5, 67.5, 292.5, 337.5):
        q = P(5.1, a, 0); glass_float(d, q[0], q[1], z+under(5.1)-.31, .13, .18)
    shimenawa(d, p, 'heart', 2.5)
    interior((c[0], c[1], z+h/2), radius=round(A+.1, 2), half_height=h/2+.35)
    leaves_on(d, [tuple(H_(*corner(A-.35, 22.5+45*j))[:2]) for j in range(8)], z, 8)
    for a in (45, 135, 225, 315):      # the room's warm light, as from the lantern strings
        q = H_(2.4*math.cos(math.radians(a)), 2.4*math.sin(math.radians(a))); light(q[0], q[1], z+2.6, 850, 5.5, int(a == 45))
    furnish_heart(m, d, p)


def boat_shape(s):
    """The upturned rowboat (L.BOAT) at s along it, -1 at the transom and 1 at the bow: half beam, gunwale height and
    keel height over the deck. Upside down, the gunwale dips toward the ends (the sheer, never under BOAT['gunwale'])
    and the keel runs nearly level along the top."""
    B, G = L.BOAT['beam']/2, L.BOAT['gunwale']
    hb = max(.03, B*math.sqrt(max(0., 1-s**2.2))) if s > 0 else B*(1-.55*(-s)**2.5)
    return hb, G+.25-(.25 if s > 0 else .17)*s*s, G+.95-.08*s*s


def hull_at(s, f, k=1., drop=0.):
    """A point of the hull's skin in boat-local metres (x along it, y across toward the trunk): s along, f round from
    the gunwale on the trunk side (0) over the keel to the other gunwale (pi); k < 1 and drop pull it inside."""
    hb, zg, zk = boat_shape(s)
    return np.array([s*L.BOAT['length']/2, hb*math.cos(f)*k, zg+(zk-zg)*max(0., math.sin(f))**.7*k-drop])


def hull_z(x, y):
    """The height of the hull's inside over boat-local (x, y)."""
    hb, zg, zk = boat_shape(x/(L.BOAT['length']/2))
    return zg+(zk-zg)*max(0., 1-min(1., (y/hb)**2))**.35


def boat_room(m, d, p):
    """The boat room: a 7 m rowboat upturned over the deck beside its trunk (layout BOAT), on four posts under its
    gunwales, open all round underneath. Faded blue planks outside with a pale strake at the gunwale, planking, ribs,
    a keelson and two thwarts inside, a pointed bow and a transom. The gunwale is 2.6 m over the deck at the ends and
    2.85 m in the middle, so the camera follows under it; the bridges land on the trunk side, which stays clear."""
    r = p['room']; c = np.array([*r['center'], p['deck']], float); ang = r['angle']; z = c[2]
    half = L.BOAT['length']/2; B = lambda lx, ly, lz=0.: local(c, ang+90, lx, ly, lz)
    S = np.sin(np.linspace(-math.pi/2, math.pi/2, 27)); F = np.linspace(0, math.pi, 17)
    sec = [[hull_at(s, f) for f in F] for s in S]
    with m.at(tuple(c), ang+90):
        for i in range(len(S)-1):
            for j in range(len(F)-1):
                q = [sec[i][j], sec[i+1][j], sec[i+1][j+1], sec[i][j+1]]
                mid = np.mean(q, axis=0); axis = np.array([mid[0], 0, boat_shape(mid[0]/half)[1]])
                out = q if np.cross(q[2]-q[0], q[3]-q[1])@(mid-axis) > 0 else q[::-1]
                out = [tuple(v) for v in out]
                if j in (0, len(F)-2):
                    with m.use('wood_pale', grain=(1, 0, 0)): m.poly(out, (.78, .74, .64))
                else:
                    with m.use('hull', grain=(1, 0, 0)): m.poly(out, WHITE)
                with m.use('wood_plank', grain=(1, 0, 0)): m.poly(out[::-1], vary(PLANK, .08))
        # the transom: painted outside, planked inside
        tr = [tuple(v) for v in sec[0]]
        nrm = sum(np.cross(np.array(tr[i]), np.array(tr[(i+1) % len(tr)])) for i in range(len(tr)))
        if nrm[0] > 0: tr = tr[::-1]
        with m.use('hull', grain=(0, 1, 0)): m.poly(tr, WHITE)
        with m.use('wood_plank', grain=(0, 1, 0)): m.poly(tr[::-1], vary(PLANK, .08))
        # rub rails along both gunwales and across the transom, the keel and stem outside, the keelson inside
        for sgn, f in ((1, 0.), (-1, math.pi)):
            tube(m, [hull_at(s, f)+[0, sgn*.03, -.01] for s in S], .045, DARK, 6, 'wood_timber')
        tube(m, [sec[0][0]+[-.03, .03, -.01], sec[0][-1]+[-.03, -.03, -.01]], .045, DARK, 6, 'wood_timber')
        tube(m, [(s*half, 0, boat_shape(s)[2]+.03) for s in S], .06, DARK, 6, 'wood_timber')
        top = boat_shape(1.)
        tube(m, [(half+.07*math.sin(math.pi*t*.5), 0, top[1]-.02+(top[2]-top[1]+.06)*t) for t in np.linspace(0, 1, 6)], .05, DARK, 6, 'wood_timber')
        tube(m, [(s*half*.97, 0, boat_shape(s*.97)[2]-.05) for s in np.linspace(-.96, .9, 12)], .05, WOOD, 6, 'wood_timber')
        for s in np.linspace(-.86, .86, 11):         # ribs
            tube(m, [hull_at(s, f, .965, .03) for f in np.linspace(.06, math.pi-.06, 12)], .03, WOOD, 4, 'wood_timber')
        for x in (-1.25, 1.25):                       # thwarts, high over the camera
            y = .96*max(yy for yy in np.linspace(0, 1.6, 81) if hull_z(x, yy) >= 3.17)
            board(m, (x, -y, 3.14), (x, y, 3.14), .24, .05, PALE, 'wood_pale')
        # four posts under the gunwales, clear of the ways in from the bridges (they come from the trunk side)
        for x in (-2.2, 2.2):
            hb = boat_shape(x/half)[0]
            for sgn in (-1, 1):
                y = sgn*(hb-.15); zt = min(hull_z(x+dx, y+dy) for dx in (-.08, .08) for dy in (-.08, .08))-.015
                post(m, x, y, -.04, zt, .16, WOOD)
    # the lantern from the keel, its bottom 2.75 m up; a low warm fill
    q = B(-.5, 0); zk = hull_z(-.5, 0)
    chochin(d, q[0], q[1], z+2.97, .3, zk-2.97-.19-.02, 1000)
    q = B(.5, 0); light(q[0], q[1], z+1.2, 250, 3.5)
    interior((c[0], c[1], z+L.BOAT['gunwale']/2), (L.BOAT['beam']/2-.05, half-.05, L.BOAT['gunwale']/2+.35), ang)
    furnish_boat(m, d, p, c, ang)


def pulley_crane(m, d, p):
    x0, y0 = p['xy']; z = p['deck']; a = math.radians(p['open']); u = np.array([math.cos(a), math.sin(a)]); c = np.array([x0, y0])
    edge = float(np.linalg.norm(L.ray_exit(p['poly'], p['open'])))      # the arm reaches 0.7 m past the deck's edge
    board(m, (*(c+u*.2), z+3.1), (*(c+u*(edge+.85)), z+3.1), .16, .18, WOOD, 'wood_timber')
    board(m, (*(c+u*p['trunk']*.9), z+1.5), (*(c+u*edge*.6), z+3.0), .14, .14, WOOD, 'wood_timber')
    ring(d, c, p['trunk']+.06, z+3.05, .035, ROPE, 16); ring(d, c, p['trunk']+.06, z+1.5, .035, ROPE, 16)
    tip = c+u*(edge+.7); v = np.array([-u[1], u[0]])
    for s in (-1, 1): board(d, (*(tip+v*s*.1), z+3.02), (*(tip+v*s*.1), z+2.75), .03, .1, DARK, 'wood_timber')
    wheel = [(*(tip+v*.045), ), (*(tip-v*.045),)]
    pts = [np.array([tip[0], tip[1], z+2.82])+np.r_[u*.15*math.cos(t), .15*math.sin(t)] for t in np.linspace(0, 2*math.pi, 13)]
    tube(d, pts, .03, WOOD, 6, 'wood_timber'); _ = wheel
    g = ground(*tip)
    tube(d, [(tip[0], tip[1], z+2.8), (tip[0], tip[1], z+1.62)], .018, ROPE, 5)
    tube(d, [(tip[0]+u[0]*.15, tip[1]+u[1]*.15, z+2.82), (tip[0]+u[0]*.15, tip[1]+u[1]*.15, g)], .018, ROPE, 5)
    prop('basket', tip[0], tip[1], z+.75, math.degrees(a), 1.)
    q = c+u*1.6+v*1.3; crate(m, q[0], q[1], z, (.55, .42, .42), math.degrees(a)+15)
    q = c+u*1.9+v*1.35; crate(m, q[0], q[1], z+.42, (.4, .35, .3), math.degrees(a)-10)
    q = c+u*1.5-v*1.4; rope_coil(d, q[0], q[1], z)
    # a sail awning between the crane mast and two posts
    for s in (-1, 1):
        q = c-u*.2+v*s*1.9
        if inside(world_poly(p), *q): post(m, q[0], q[1], z, z+2.3, .1, WOOD)
    q0, q1, q2 = c-u*.2+v*1.9, c-u*.2-v*1.9, c+u*1.2
    with d.use('canvas'):
        two_sided(d, [(*q0, z+2.3), (*q1, z+2.3), (*q2, z+3.05)], vary(CANVAS, .05))


def chime_hoop(m, d, p):
    x0, y0 = p['xy']; z = p['deck']; r = 1.6
    tube(d, [(x0+r*math.cos(a), y0+r*math.sin(a), z+2.25) for a in np.linspace(0, 2*math.pi, 33)], .045, WOOD, 6, 'wood_timber')
    for k in range(4):
        a = math.radians(45+90*k); board(d, (x0, y0, z+2.35), (x0+r*math.cos(a), y0+r*math.sin(a), z+2.3), .07, .07, WOOD, 'wood_timber')
    ring(d, (x0, y0), p['trunk']+.05, z+2.3, .04, ROPE, 14)
    for k in range(12):
        a = math.radians(30*k+8); x, y = x0+r*math.cos(a), y0+r*math.sin(a)
        fuurin(d, x, y, z+1.9, .22)
    for off in (-50, 30):           # both lanterns on the open side, off the walks between the bridges
        a = math.radians(p['open']+off); x, y = x0+2.3*math.cos(a), y0+2.3*math.sin(a)
        if inside(world_poly(p), x, y): andon(d, x, y, z, .28, 300)
    a = math.radians(p['open']+60); prop('planter', x0+2.0*math.cos(a), y0+2.0*math.sin(a), z, face_yaw(-math.cos(a), -math.sin(a)), 1.)


def slide(m, d, pl):
    s = pl['slide']; P = pl['places']['slide']; c = s['center']; rc, hw = s['rc'], s['width']/2; z = P['deck']
    a0, a1 = s['landing']
    for k in range(8):
        f0, f1 = a0+(a1-a0)*k/8, a0+(a1-a0)*(k+1)/8
        # 12 mm under the deck's planks, which it runs under near the trunk (the same plane would flicker)
        with m.use('wood_plank'): sector(m, c, f0, f1, 2.45, rc+hw, z-.012, z-.012, .08, vary(PLANK, .1))
        with m.use('wood_timber'): sector(m, c, f0, f1, rc+hw, rc+hw+.07, z+.42, z+.42, .5, DARK)
    with m.use('wood_timber'): sector(m, c, a0-2, a0, rc-hw, rc+hw+.07, z+.42, z+.42, .5, DARK)
    path = s['path']
    for p0, p1 in zip(path[:-1], path[1:]):
        f0, f1 = p0[3], p1[3]
        with m.use('wood_pale'): sector(m, c, f0, f1, rc-hw, rc+hw, p0[2], p1[2], .07, vary(PALE, .05))
        for r0, r1 in ((rc-hw-.07, rc-hw), (rc+hw, rc+hw+.07)):
            with m.use('wood_plank'): sector(m, c, f0, f1, r0, r1, p0[2]+.38, p1[2]+.38, .45, vary(BOARD, .06))
    # Columns stand outside both side walls, every 30 degrees; each carries every turn that passes it on a cross-beam
    # under the bed, so no post rises through the chute of the turn below.
    ang, bed, gnd = (np.array([q[i] for q in path]) for i in (3, 2, 4))
    ri_, ro_ = rc-hw-.2, rc+hw+.2
    for A in np.arange(ang[0]+12, ang[0]+360, 30):
        levels = [float(np.interp(B, ang, bed)) for B in (A, A+360) if B <= ang[-1] and np.interp(B, ang, bed)-np.interp(B, ang, gnd) > .6]
        if not levels: continue
        a = math.radians(A); e = np.array([math.cos(a), math.sin(a), 0.]); t = np.array([-e[1], e[0], 0.])
        for r in (ri_, ro_):
            x, y = c[0]+r*e[0], c[1]+r*e[1]; post(m, x, y, ground(x, y)-.2, max(levels)-.09, .12, WOOD)
        for lv in levels:
            board(m, (c[0]+(ri_-.06)*e[0], c[1]+(ri_-.06)*e[1], lv-.07), (c[0]+(ro_+.06)*e[0], c[1]+(ro_+.06)*e[1], lv-.07), .1, .12, DARK, 'wood_timber')
    last = np.array(path[-1][:3]); pts = [last]+[np.array(q) for q in s['runout']]
    for q0, q1 in zip(pts[:-1], pts[1:]):
        board(m, q0, q1, 2*hw, .08, vary(PALE), 'wood_pale')
    # the start gate: two posts, a crossbar, a little flag; a straw heap where the run-out ends
    ga = math.radians(a0); gx, gy = c[0]+rc*math.cos(ga), c[1]+rc*math.sin(ga); t = np.array([math.cos(ga), math.sin(ga)])
    for f in (-1, 1): post(m, gx+t[0]*f*(hw+.12), gy+t[1]*f*(hw+.12), z, z+1.9, .12, WOOD)
    board(m, (gx-t[0]*(hw+.2), gy-t[1]*(hw+.2), z+1.95), (gx+t[0]*(hw+.2), gy+t[1]*(hw+.2), z+1.95), .14, .14, DARK, 'wood_timber')
    andon(d, gx+t[0]*(hw+.12), gy+t[1]*(hw+.12), z+1.97, .22, 260)
    chochin(d, gx-t[0]*.1, gy-t[1]*.1, z+1.55, .2, .26, 220)
    end = np.array(s['runout'][-1]); gz = ground(end[0], end[1])
    with d.use('straw'):
        for k in range(7):
            q = end[:2]+np.array([R.uniform(-.6, .6), R.uniform(-.6, .6)]); rr = R.uniform(.45, .7)
            d.lathe((q[0], q[1], gz-.05), [(0, rr), (.12, rr*.9), (.25, rr*.6), (.32, .05)], vary(STRAW, .1), 10)
    for _ in range(25): maple_leaf(d, end[0]+R.uniform(-1.4, 1.4), end[1]+R.uniform(-1.4, 1.4), gz+.28, R.uniform(.07, .11))


def tower_legs(pl):
    """The crow's nest tower's four legs (foot, head). The feet stand in every other corner of the lookout deck, in
    place of the railing's corner posts, on the set of corners furthest from the bridges, so no leg stands on the
    deck's walk or in front of a bridge; the heads are under the crow's nest floor."""
    p = pl['places']['lookout']; x0, y0 = p['xy']; z = p['deck']; top = pl['crow']['floor']
    corners = world_poly(p)
    ang = lambda q: math.degrees(math.atan2(q[1]-y0, q[0]-x0))
    clear = lambda q: min(abs((ang(q)-l['angle']+540) % 360-180) for l in p['links'])
    feet = max((corners[0::2], corners[1::2]), key=lambda s: min(clear(q) for q in s))
    legs = []
    for fx, fy in feet:
        a = math.radians(ang((fx, fy)))
        legs.append(((fx, fy, z-.3), (x0+2.45*math.cos(a), y0+2.45*math.sin(a), top-.14)))
    return legs


def lookout(m, d, pl):
    p = pl['places']['lookout']; cr = pl['crow']; x0, y0 = p['xy']; z = p['deck']; top = cr['floor']
    # The treads run into the trunk (which narrows as it climbs) and are housed in a helical outer string that stands
    # a little above them; a knee brace from the trunk under every third tread.
    _, rad, wob, _, _ = trunk_shape(x0, y0, p['trunk'], p['trunk_top'], z, len('lookout'))
    inner = lambda h: rad(h)*.95-float(np.linalg.norm(wob(h)))-.04
    ro, da, rise = cr['ro'], cr['da'], cr['rise']
    for k in range(cr['steps']):
        a = cr['start']+k*da; t = z+(k+1)*rise
        tt = t-.004 if k == cr['steps']-1 else t        # the top tread meets the crow's nest floor, a hair under it
        with m.use('wood_plank'): sector(m, (x0, y0), a, a+da+1.5, inner(t), ro, tt, tt, .07, vary(PLANK, .12))
        with m.use('wood_timber'): sector(m, (x0, y0), a, a+da, ro-.01, ro+.07, z+(k+.6)*rise, z+(k+1.6)*rise, .32, DARK)
        if k % 2 == 0:
            x, y = x0+(ro+.03)*math.cos(math.radians(a)), y0+(ro+.03)*math.sin(math.radians(a))
            post(m, x, y, t-.05, t+1.0, .07, DARK)
        if k % 3 == 1:
            am = math.radians(a+da/2); e = np.array([math.cos(am), math.sin(am), 0.]); tg = np.array([-e[1], e[0], 0.])
            strut(m, np.array([x0, y0, t-.62])+e*inner(t-.62), np.array([x0, y0, t-.1])+e*(ro-.3), .06, .06, tg)
    helix = [(x0+(cr['ro']+.03)*math.cos(math.radians(cr['start']+k*cr['da'])),
              y0+(cr['ro']+.03)*math.sin(math.radians(cr['start']+k*cr['da'])), z+(k+1)*cr['rise']+.92)
             for k in range(0, cr['steps']+1)]
    tube(m, helix, .04, ROPE_LT, 6)
    for k in range(0, cr['steps'], 9):
        a = math.radians(cr['start']+k*cr['da']); x, y = x0+(cr['ro']+.15)*math.cos(a), y0+(cr['ro']+.15)*math.sin(a)
        chochin(d, x, y, z+(k+1)*cr['rise']+1.25, .18, .2, 200)
    h0, h1 = cr['hole']
    for k in range(24):
        f0, f1 = 15*k, 15*(k+1); mid = (f0+f1)/2
        inside_ = ((mid-h0) % 360) < ((h1-h0) % 360)
        with m.use('wood_plank'): sector(m, (x0, y0), f0, f1, cr['ro']+.05 if inside_ else .45, cr['R'], top, top, .14, vary(PLANK, .1))
    rim = [(x0+cr['R']*math.cos(a), y0+cr['R']*math.sin(a)) for a in np.linspace(0, 2*math.pi, 13)[:-1]]
    railing(m, d, rim, top, height=1.0)
    legs = tower_legs(pl)
    for lo, hi in legs:
        with m.use('wood_timber', grain=tuple(np.subtract(hi, lo)), jitter=True):
            hexa(m, [np.add(lo, dd) for dd in ((-.09, -.09, 0), (.09, -.09, 0), (.09, .09, 0), (-.09, .09, 0))] +
                 [np.add(hi, dd) for dd in ((-.09, -.09, 0), (.09, -.09, 0), (.09, .09, 0), (-.09, .09, 0))], WOOD)
    for k in range(4):
        (l0, h0_), (l1, h1_) = legs[k], legs[(k+1) % 4]
        for f in (.3, .65):
            pa = np.add(l0, np.subtract(h0_, l0)*f); pb = np.add(l1, np.subtract(h1_, l1)*(f+.3))
            board(m, pa, pb, .09, .09, WOOD, 'wood_timber')
            ring(d, pa[:2], .1, pa[2]-.02, .02, ROPE, 8)
    for k in range(4):
        a = math.radians(cr['start']+90*k)
        x, y = x0+2.55*math.cos(a), y0+2.55*math.sin(a); post(m, x, y, top, top+2.15, .11, WOOD)
        nxt = math.radians(cr['start']+90*(k+1)); xn, yn = x0+2.55*math.cos(nxt), y0+2.55*math.sin(nxt)
        with d.use('canvas'):
            two_sided(d, [(x, y, top+2.1), (xn, yn, top+2.1), (x0, y0, top+2.75)], vary(CANVAS, .08), vary(CANVAS, .05))
        glass_float(d, x, y, top+1.75, .12, .3) if k % 2 else fuurin(d, x*.97+x0*.03, y*.97+y0*.03, top+1.85)
    post(d, x0, y0, top+2.7, top+4.8, .07, WOOD)
    with d.use('flag'):
        fl = [(x0, y0, top+4.05), (x0+1.2, y0+.12, top+4.05), (x0+1.2, y0+.12, top+4.75), (x0, y0, top+4.75)]
        uv = [(0, 0), (1, 0), (1, 1), (0, 1)]
        d.poly(fl, WHITE, uv=uv); d.poly(fl[::-1], WHITE, uv=uv[::-1])
    # the telescope at the south rail, looking out to sea over the islet
    a = math.radians(300); x, y = x0+2.2*math.cos(a), y0+2.2*math.sin(a)
    prop('telescope', x, y, top, face_yaw(-.15, -1)+180, 1.)
    posts = [(x0+2.55*math.cos(math.radians(cr['start']+90*k)), y0+2.55*math.sin(math.radians(cr['start']+90*k))) for k in range(4)]
    for k in range(4):    # beams along the canopy edge
        (xa, ya), (xb, yb) = posts[k], posts[(k+1) % 4]
        board(m, (xa, ya, top+2.04+.005*(k % 2)), (xb, yb, top+2.04+.005*(k % 2)), .1, .12, DARK, 'wood_timber')
    # the bell on a hanging board under the canopy beam that faces the sea, turned to the floor
    k = min(range(4), key=lambda k: abs(((cr['start']+90*k+45-283.88+540) % 360)-180))
    mid = (np.array(posts[k])+np.array(posts[(k+1) % 4]))/2; inw = (np.array([x0, y0])-mid)/np.linalg.norm(np.array([x0, y0])-mid)
    along_ = np.array([-inw[1], inw[0]])
    with m.use('wood_plank', grain=(0, 0, 1)):
        hexa(m, [(*(mid+along_*f*.12+inw*g), top+zz) for zz in (1.22, 2.0) for f, g in ((-1, -.03), (1, -.03), (1, .03), (-1, .03))], WOOD)
    q = mid+inw*.29; prop('bell', q[0], q[1], top+1.3, face_yaw(*inw), .75)
    k = min(range(4), key=lambda k: abs(((cr['start']+90*k-58.88+540) % 360)-180))       # the banner on the post over the city
    px, py = posts[k]; inw = np.array([x0-px, y0-py])/math.hypot(x0-px, y0-py); tg = np.array([-inw[1], inw[0]])
    fq = np.array([px, py])+inw*.07
    picture(d, [(*(fq-tg*.28), top+.75), (*(fq+tg*.28), top+.75), (*(fq+tg*.28), top+1.95), (*(fq-tg*.28), top+1.95)], 'flag')
    k = min(range(4), key=lambda k: abs(((cr['start']+90*k+45-103.88+540) % 360)-180))
    mid = (np.array(posts[k])+np.array(posts[(k+1) % 4]))/2; chochin(d, mid[0], mid[1], top+1.78, .21, .25, 320)
    a = math.radians(cr['start']+200); x, y = x0+2.1*math.cos(a), y0+2.1*math.sin(a); crate(m, x, y, top, (.5, .4, .4), math.degrees(a))   # clear of the view back
    andon(d, x, y, top+.4, .24, 350)
    a = math.radians(cr['start']+250); x, y = x0+2.2*math.cos(a), y0+2.2*math.sin(a); rope_coil(d, x, y, top, .24)
    # banner down one tower leg
    lo, hi = legs[1]; q = np.add(lo, np.subtract(hi, lo)*.55)
    t = np.array([-(q[1]-y0), q[0]-x0, 0]); t /= np.linalg.norm(t)
    picture(d, [tuple(q-t*.3+[0, 0, -.9]), tuple(q+t*.3+[0, 0, -.9]), tuple(q+t*.3+[0, 0, .3]), tuple(q-t*.3+[0, 0, .3])], 'flag')


def entry_way(m, d, pl):
    """The plank steps down north from the little hut's north door (layout.entry_way(): L.STAIR_WIDTH wide, their
    stringers, rope handrails on short posts) and the stepping stones exactly where the layout puts them, each level;
    a post lantern beside the first stone. Its own random stream, so the stones keep their shapes whatever is built
    before them."""
    global R
    shared, R = R, random.Random(ENTRY_SEED+2)
    try:
        ex = pl['entry_stairs']; E = pl['places']['entry']; x = ex['x']; W = ex['width']
        for k in range(ex['steps']-1):
            y0 = ex['top_y']+k*ex['tread']; t = E['deck']-(k+1)*ex['rise']
            with m.use('wood_plank', grain=(1, 0, 0), jitter=True):
                m.box((x, y0+ex['tread']/2, t-.03), (W, ex['tread']+.02, .06), vary(PLANK, .1))
        fy, fz = ex['foot'][1], ex['foot'][2]
        for s in (-1, 1):
            xs = x+s*(W/2+.04); xp = x+s*(W/2+.075)      # posts just outside the treads: the way stays W clear
            board(m, (xs, ex['top_y'], E['deck']-.02), (xs, fy, fz), .07, .26, DARK, 'wood_timber')
            for yy, zz in ((ex['top_y']+.05, E['deck']), (fy-.1, fz)):
                post(m, xp, yy, zz-.3, zz+1.05, .11, WOOD)
            tube(m, [(xp, ex['top_y']+.05, E['deck']+.95), (xp, fy-.1, fz+.95)], .032, ROPE_LT, 6)
        # Every stone is level (layout.entry_way() sets its top). Stones at one height keep a gap between them; up the
        # bank, where each is a step over the last, they overlap like a flight cut into the slope. Each is long across
        # the way.
        st = pl['stones']; last = len(st)-1
        for i, (sx, sy, sz) in enumerate(st):
            if i == last:       # the stone at the stair foot: wider, square to the stair, against the lowest tread
                (rx, ry), rot_ = L.FOOT_STONE, 0.
            else:
                u = np.array(st[i+1][:2])-np.array(st[max(i-1, 0)][:2])
                half = []
                for j in (i-1, i+1) if i else (i+1,):
                    qx, qy, qz = st[j]; dist = math.hypot(qx-sx, qy-sy)
                    if j == last: half.append(dist-L.FOOT_STONE[1]-.05)
                    elif abs(qz-sz) < .06: half.append(dist/2-.05)
                    else: half.append(dist/2+.08)
                rx, ry = R.uniform(.44, .5), float(np.clip(min(half), .2, .42))
                rot_ = math.atan2(u[1], u[0])-math.pi/2+R.uniform(-.12, .12)
            wob = [1.+R.uniform(-.05, .05) for _ in range(10)] if i != last else [1.]*10
            pts = ccw([(sx+w*(rx*math.cos(a)*math.cos(rot_)-ry*math.sin(a)*math.sin(rot_)), sy+w*(rx*math.cos(a)*math.sin(rot_)+ry*math.sin(a)*math.cos(rot_)))
                       for a, w in zip(np.linspace(0, 2*math.pi, 11)[:-1], wob)])
            top = [(px, py, sz) for px, py in pts]
            zb = min([sz]+[ground(px, py) for px, py in pts])-.3
            with m.use('stone', jitter=True):
                m.poly(top, vary(STONE, .1))
                m.poly([(px, py, zb) for px, py in pts[::-1]], vary(STONE, .18))
                for a, b_ in zip(top, top[1:]+top[:1]):
                    m.poly([(a[0], a[1], zb), (b_[0], b_[1], zb), b_, a], vary(STONE, .18))
        # no rope fence along the stones: the way from the trail onto them stays open
        sx, sy, sz = pl['stones'][0]; post(d, sx-.8, sy, ground(sx-.8, sy)-.2, sz+1.3, .1, WOOD)
        andon(d, sx-.8, sy, sz+1.3, .26, 300)
    finally:
        R = shared


# ---------------------------------------------------------------------------------------------- trunks

def panes(d):
    """The day seen through every window: one face in the opening, a little inside it, in the pane slot of
    TH_Dressing, which M_TH_Light draws additive and unlit, so the outside reads brighter than the room, as painted.
    There are no sunbeam shafts or floor pools: they flickered through the walls and hid the rooms."""
    for corners, inward, along, floor, kind in WINDOWS:
        n = np.array(inward); k = len(corners)
        if kind == 'round':
            uv = [(.5+.5*math.cos(f), .5+.5*math.sin(f)) for f in np.linspace(0, 2*math.pi, k+1)[:-1]]
        else:
            uv = [(0, 0), (1, 0), (1, 1), (0, 1)]
        with d.use('pane'):        # a soft glow across the opening, dark on the cross
            before = len(d.faces); d.poly([tuple(np.array(q)-n*.01) for q in corners], SUN, uv=uv)
            if len(d.faces) > before: d.colors[-k:] = [(*SUN, 1.)]*k


def trunk_shape(x, y, r, z1, deck, seed):
    """The trunk's radius and axis offset by height, and its lobe phase: shared by the trunk and what wraps it."""
    g = ground(x, y); rr = random.Random(seed)
    rad = lambda z: r*(1+.45*max(0., 1-(z-g)/2.6)**2)*(1-.22*max(0., (z-deck)/max(1., z1-deck)))
    ph = [rr.uniform(0, 6.3) for _ in range(4)]
    wob = lambda z: np.array([.06*r*math.sin(z*.37+ph[0])+.04*r*math.sin(z*.9+ph[1]), .06*r*math.cos(z*.31+ph[2])+.04*r*math.sin(z*.8+ph[3])])
    return g, rad, wob, ph, rr


def trunk(m, x, y, r, z1, deck, roots=5, color=BARK, seed=0):
    g, rad, wob, ph, rr = trunk_shape(x, y, r, z1, deck, seed)
    zs = list(np.linspace(g-.6, g+2.4, 6))+list(np.linspace(g+3.2, z1, max(2, int((z1-g-3.2)/1.2)+1)))
    n = 16
    with m.use('bark', jitter=True):
        for z0_, z1_ in zip(zs[:-1], zs[1:]):
            # lathe with a wobbling axis: build the rings by hand
            ra = [(x+wob(z0_)[0]+rad(z0_)*(1+.05*math.sin(5*a+ph[0]))*math.cos(a), y+wob(z0_)[1]+rad(z0_)*(1+.05*math.sin(5*a+ph[0]))*math.sin(a), z0_) for a in np.linspace(0, 2*math.pi, n+1)]
            rb = [(x+wob(z1_)[0]+rad(z1_)*(1+.05*math.sin(5*a+ph[0]))*math.cos(a), y+wob(z1_)[1]+rad(z1_)*(1+.05*math.sin(5*a+ph[0]))*math.sin(a), z1_) for a in np.linspace(0, 2*math.pi, n+1)]
            circ = 2*math.pi*r
            for k in range(n):
                uv = [(circ*k/n/1.6, z0_/1.6), (circ*(k+1)/n/1.6, z0_/1.6), (circ*(k+1)/n/1.6, z1_/1.6), (circ*k/n/1.6, z1_/1.6)]
                m.poly([ra[k], ra[k+1], rb[k+1], rb[k]], vary(color, .05), uv=uv)
        top = [(x+wob(z1)[0]+rad(z1)*math.cos(a), y+wob(z1)[1]+rad(z1)*math.sin(a), z1) for a in np.linspace(0, 2*math.pi, n+1)[:-1]]
        m.poly(top, vary(color))
    for k in range(roots):
        a = 2*math.pi*k/roots+rr.uniform(-.3, .3); u = np.array([math.cos(a), math.sin(a)]); v = np.array([-u[1], u[0]])
        base = np.array([x, y])+u*r*.9; mid = np.array([x, y])+u*(r*1.8+rr.uniform(.1, .3)); tip = np.array([x, y])+u*(r*2.8+rr.uniform(.3, .9))
        gm, gt = ground(*mid), ground(*tip)
        wb, wm, wt = r*1.1, r*.6, .22; hb = g+.35+r*.6
        with m.use('bark', grain=(0, 0, 1), jitter=True):
            hexa(m, [(*(base-v*wb/2), g-.5), (*(mid-v*wm/2), gm-.4), (*(mid+v*wm/2), gm-.4), (*(base+v*wb/2), g-.5),
                     (*(base-v*wb/2), hb), (*(mid-v*wm/2), gm+.25), (*(mid+v*wm/2), gm+.25), (*(base+v*wb/2), hb)], vary(color, .1))
            hexa(m, [(*(mid-v*wm/2), gm-.4), (*(tip-v*wt/2), gt-.35), (*(tip+v*wt/2), gt-.35), (*(mid+v*wm/2), gm-.4),
                     (*(mid-v*wm/2), gm+.25), (*(tip-v*wt/2), gt+.06), (*(tip+v*wt/2), gt+.06), (*(mid+v*wm/2), gm+.25)], vary(color, .1))


def moss_on_trunk(d, x, y, r, g, top):
    """Moss patches on the north side of the trunk and around the root flare."""
    with d.use('moss'):
        for _ in range(6):
            z = R.uniform(g+.3, top-1.); a = math.radians(R.uniform(60, 120)); rr = r*(1+.45*max(0., 1-(z-g)/2.6)**2)+.03
            h = R.uniform(.3, .8); w = R.uniform(.35, .6)
            pts = [(x+(rr)*math.cos(a+w*math.cos(t)/rr), y+rr*math.sin(a+w*math.cos(t)/rr), z+h*math.sin(t)/2) for t in np.linspace(0, 2*math.pi, 9)[:-1]]
            d.poly(pts, vary(MOSS, .15)); d.poly(pts[::-1], vary(MOSS, .15))


def main():
    global H
    H = np.load(yori.OUT/'heightmap.npy')
    (OUT/'assets').mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats = material_factory()
    pl = L.plan(H); P = pl['places']
    m, trunks, d = TMesh('TH_Structure', 'wood_plank'), TMesh('TH_Trunks', 'bark'), TMesh('TH_Dressing', 'wood_timber')
    # where the bridges' end posts and the entry stair's top posts stand, the deck railings have none
    avoid = []
    for b in pl['bridges']:
        A, B = np.array(b['start'][:2], float), np.array(b['end'][:2], float); u = (B-A)/np.linalg.norm(B-A); v = np.array([-u[1], u[0]])
        avoid += [tuple(q+v*f*(L.BRIDGE_WIDTH/2+.07)) for q in (A, B) for f in (-1, 1)]
    ex = pl['entry_stairs']; avoid += [(ex['x']+f*(ex['width']/2+.04), ex['top_y']+.05) for f in (-1, 1)]
    avoid += [foot[:2] for foot, _ in tower_legs(pl)]          # the lookout tower's legs are those corners' posts
    for name, p in P.items():
        deck(m, d, p)
        extra = []
        if name == 'entry':
            ex = pl['entry_stairs']; extra.append((ex['x'], ex['top_y'], ex['width']/2+.1))
        if name == 'slide':
            mid = math.radians(sum(pl['slide']['landing'])/2); q = L.ray_exit(p['poly'], math.degrees(mid))
            extra.append((p['xy'][0]+q[0], p['xy'][1]+q[1], .75))
        railing(m, d, world_poly(p), p['deck'], gaps_for(p, pl, extra), avoid=avoid)
        big = name == 'heart'
        trunk(trunks, *p['xy'], p['trunk'], p['trunk_top'], p['deck'], 8 if big else 5, BARK_OLD if big else BARK, len(name))
        moss_on_trunk(d, *p['xy'], p['trunk'], ground(*p['xy']), p['deck'])
        ring(d, p['xy'], p['trunk']+.05, p['deck']-.3, .04, ROPE, 16)
        if name in ('library', 'kitchen', 'sleep'):
            # a crate and a planter or rope coil in the deck's front corners, past the outer wall and off the porches
            c, ang, _ = hut_frame(p); d2, w2 = p['room']['half']
            q = local(c, ang, d2+.45, -(w2+1.1)); crate(m, q[0], q[1], p['deck'], (.5, .4, .38), ang+R.uniform(-15, 15))
            q = local(c, ang, d2+.45, w2+1.1)
            if name in ('library', 'sleep'): prop('planter', q[0], q[1], p['deck'], lyaw(ang, -1, 0), .9)
            else: rope_coil(d, q[0], q[1], p['deck'])
        if name == 'chimes':
            # a crate and a rope coil in the deck corners furthest from the bridges
            poly = world_poly(p); c = np.array(p['xy'])
            busy = [l['angle'] for l in p['links']]
            gap = lambda q: min(abs(((math.degrees(math.atan2(q[1]-c[1], q[0]-c[0]))-b+540) % 360)-180) for b in busy)
            corners = sorted(range(len(poly)), key=lambda k: -gap(poly[k]))
            k1 = corners[0]; k2 = next(k for k in corners[1:] if min(abs(k-k1), len(poly)-abs(k-k1)) > 1)
            corner = np.array(poly[k1]); q = corner+(c-corner)/np.linalg.norm(c-corner)*.6
            crate(m, q[0], q[1], p['deck'], (.5, .4, .38), R.uniform(0, 90))
            corner = np.array(poly[k2]); q = corner+(c-corner)/np.linalg.norm(c-corner)*.65
            rope_coil(d, q[0], q[1], p['deck'])
    for b in pl['bridges']:
        bridge(m, d, b)
    entry_hut(m, d, P['entry'])
    rooms = {}
    for name in ('library', 'kitchen', 'sleep'):
        rooms[name] = hut(m, d, P[name], name)
    furnish_library(m, d, *rooms['library']); furnish_kitchen(m, d, *rooms['kitchen']); furnish_sleep(m, d, *rooms['sleep'])
    heart_room(m, d, P['heart'])
    boat_room(m, d, P['boat'])
    pulley_crane(m, d, P['pulley'])
    chime_hoop(m, d, P['chimes'])
    slide(m, d, pl)
    lookout(m, d, pl)
    entry_way(m, d, pl)
    panes(d); report = {'windows': len(WINDOWS)}
    for mesh in (m, trunks, d):
        _, report[mesh.name] = export(mesh, mats, OUT/'assets')
    report['props'] = {k: len(v) for k, v in PLACED.items()}
    runtime = dict(instances=PLACED, lights=LIGHTS, rooms=ROOMS, room_grade=ROOM_GRADE)
    (OUT/'runtime.json').write_text(json.dumps(runtime)+'\n'); report['lights'] = len(LIGHTS); report['rooms'] = len(ROOMS)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Treehouse.blend'))
    (OUT/'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print('TREEHOUSE BUILD COMPLETE', json.dumps({k: v.get('triangles', v) if isinstance(v, dict) and 'triangles' in v else v for k, v in report.items()}), flush=True)


if __name__ == '__main__':
    main()
