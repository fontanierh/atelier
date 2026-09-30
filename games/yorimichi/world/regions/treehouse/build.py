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
    # Joists to every corner, a rim, and knee braces down to the trunk.
    r = p['trunk']; lashed = []
    for k, (vx, vy) in enumerate(poly):
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
    # Moss creeping in from the rim at a few corners, and the season's leaves.
    for k in R.sample(range(len(poly)), min(3, len(poly))):
        a = np.array(poly[k]); inward = (c-a)/np.linalg.norm(c-a)
        blob = [a+inward*.1+np.array([math.cos(t), math.sin(t)])*R.uniform(.18, .32) for t in np.linspace(0, 2*math.pi, 9)[:-1]]
        blob = [q for q in blob if inside(poly, *q)]
        if len(blob) >= 3:
            with d.use('moss'):
                d.poly([(*q, z+.008) for q in ccw(blob)], vary(MOSS, .12))
    leaves_on(d, poly, z, 14)


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


def shingled(m, d, quad, rows=None, moss=.25, tiles=.1, ridge=None, phase=0):
    """A roof plane of overlapping shingle courses: quad = eave-left, eave-right, top-right, top-left.
    Each course is a thin slab lapping the one below, split into runs of shingle, moss or blue tile."""
    q = [np.asarray(x, float) for x in quad]
    slope = float(np.linalg.norm((q[3]+q[2])/2-(q[0]+q[1])/2)); rows = rows or max(3, round(slope/.34))
    P = lambda a, b: q[0]+(q[1]-q[0])*a+(q[3]-q[0])*b+(q[2]-q[1]-q[3]+q[0])*a*b
    along = (q[1]-q[0])/np.linalg.norm(q[1]-q[0])
    nrm = np.cross(q[1]-q[0], q[3]-q[0]); nrm /= np.linalg.norm(nrm)
    if nrm[2] < 0: nrm = -nrm
    for i in range(rows):
        b0, b1 = i/rows, min(1., (i+1.35)/rows)
        width = float(np.linalg.norm(P(1, b0)-P(0, b0))); runs = max(1, round(width/R.uniform(.7, 1.1)))
        ext = .008*((i+phase) % 2)/width    # every other row a little past the sides: lapping rows' ends not in one plane
        cuts = sorted([-ext, 1.+ext]+[R.uniform(.1, .9) for _ in range(runs-1)])
        for a0, a1 in zip(cuts[:-1], cuts[1:]):
            c = R.random(); edge = i == 0 or i == rows-1
            kind, col = (('moss', vary(MOSS, .15)) if c < moss*(1.6 if edge else .7) else
                         ('tile', vary(TILE, .1)) if c < moss+tiles else ('shingle', vary(SHINGLE, .12)))
            lo = [P(a0, b0), P(a1, b0)]; hi = [P(a1, b1), P(a0, b1)]
            tip = .045+.015*R.random()
            pts = [lo[0]+nrm*tip, lo[1]+nrm*tip, hi[0]+nrm*.012, hi[1]+nrm*.012]
            with m.use(kind, grain=tuple(along), jitter=True):
                hexa(m, [pts[0]-nrm*.03, pts[1]-nrm*.03, pts[2]-nrm*.03, pts[3]-nrm*.03]+pts, col)
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


def hut_frame(p, depth):
    x0, y0 = p['xy']; z = p['deck']; ang = p['open']; r0 = p['trunk']+.3
    diffs = [((l['angle']-ang+540) % 360)-180 for l in p['links']]
    side = 1 if min(diffs, key=abs) > 0 else -1
    c = np.array([x0+(r0+depth/2)*math.cos(math.radians(ang)), y0+(r0+depth/2)*math.sin(math.radians(ang)), z])
    return c, ang, side


def local(c, ang, lx, ly, lz=0.):
    a = math.radians(ang)
    return np.array([c[0]+lx*math.cos(a)-ly*math.sin(a), c[1]+lx*math.sin(a)+ly*math.cos(a), c[2]+lz])


def hut(m, d, p, depth, width, name, wall_h=2.25, top=L.ROOF_TOP['hut']):
    c, ang, side = hut_frame(p, depth); d2, w2 = depth/2, width/2
    frames = []
    with m.at(tuple(c), ang):
        wall(m, (d2, -w2), (d2, w2), wall_h, [(w2-side*.5, 1.12, .78, 1.9, 'round')], frames=frames)
        wall(m, (-d2, w2), (-d2, -w2), wall_h, frames=frames)
        for s in (-1, 1):
            ops = [(d2, .86, 0., 1.86, 'door')] if s == side else [(d2, 1.3, .88, 1.8, 'window')]
            wall(m, (-d2, s*w2), (d2, s*w2), wall_h, ops, frames=frames)
        for x in (-d2, d2):
            for y in (-w2, w2): post(m, x, y, -.04, wall_h+.05, .16, DARK)
        gable_roof(m, d, depth, width, wall_h-.08, top)
    # world-space inside frames: (origin, along, inward, length) per wall, in order outer, back, side -1, side +1
    W = [(local(c, ang, *f[0]), rot(f[1], ang), rot(f[2], ang), f[3]) for f in frames]
    door = local(c, ang, 0, side*(w2+.08))
    noren(d, door[0], door[1], c[2]+1.86, .8, .72, ang, 'noren_indigo' if name == 'library' else 'noren_cream')
    lan = local(c, ang, d2*.55, side*(w2+.32)); chochin(d, lan[0], lan[1], c[2]+1.72, .26, .3, 320)
    for lx, ly in ((d2+.34, -w2-.34), (-d2-.1, -side*(w2+.34))):
        q = local(c, ang, lx, ly); glass_float(d, q[0], q[1], c[2]+wall_h-.45, .12, .3)
    q = local(c, ang, d2+.36, .45); fuurin(d, q[0], q[1], c[2]+wall_h-.3)
    inside = local(c, ang, 0, 0); chochin(d, inside[0], inside[1], c[2]+2.05, .24, .35, 650)
    interior((inside[0], inside[1], c[2]+wall_h/2), (d2-.05, w2-.05, wall_h/2+.35), ang)
    leaves_on(d, [tuple(local(c, ang, sx*(d2-.2), sy*(w2-.2))[:2]) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))], c[2], 7)
    q = local(c, ang, d2*.6, 0); light(q[0], q[1], c[2]+1.2, 250, 3.2)      # warm fill low in the room
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


def furnish_kitchen(m, d, c, ang, side, W):
    """As painted: the clay stove and its pipe in the back corner, a counter under the far window, the log table
    and stools on a blue rug in the middle, the water barrel by the door, persimmons drying from the rafters."""
    z = c[2]; outer, back, s_m, s_p = W; far = s_m if side > 0 else s_p; d2, w2 = L.HUT[1]/2, L.HUT[0]/2
    Hl = room(c, ang, side)
    q = Hl(-d2+.55, -w2+.6); prop('kamado', q[0], q[1], z, lyaw(ang, .7, side*.8), 1.)
    pipe = Hl(-d2+.2, -w2+.42)
    tube(m, [(pipe[0], pipe[1], z+.95), (pipe[0], pipe[1], z+L.ROOF_TOP['hut']+.55)], .075, IRON, 8, 'iron')
    for zz in (1.9, 3.0): ring(m, pipe[:2], .08, z+zz, .015, IRON, 8, 'iron')
    for k in range(7):            # split logs stacked by the stove
        q = Hl(-d2+.2+.13*(k % 4), -w2+1.45, .07+.12*(k//4)); e = rot((0, .45), ang)
        tube(m, [q-e/2, q+e/2], .06, vary(WOOD, .15), 6, 'wood_timber')
    q = Hl(.3, -.1); rug(d, q[0], q[1], z, 1.7, 2.1, ang+90, 'rug_blue'); prop('log_table', q[0], q[1], z+.012, ang+25, 1.)
    q = Hl(-d2+.45, w2-1.0); prop('barrel', q[0], q[1], z, lyaw(ang, 1, 0), .95)
    for lx, sy in ((-.48, 0.), (1.08, -.5), (.42, .8)):     # log stools round the table
        q = Hl(lx, sy); stool(m, q[0], q[1], z)
    fo, fu, fn = frame3(far, z); yaw = along(far)
    for sc in (1.55, 2.3):         # a counter of two crates under the far window, a board top
        q = fo+fu*sc+fn*.3; crate(m, q[0], q[1], z, (.72, .5, .78), yaw)
    top = [fo+fu*1.15+fn*.31+[0, 0, .8], fo+fu*2.7+fn*.31+[0, 0, .8]]
    board(m, tuple(top[0]), tuple(top[1]), .6, .05, vary(PLANK, .05), 'wood_plank')
    for k, sc in enumerate((1.35, 1.6, 2.05, 2.45)):
        q = fo+fu*sc+fn*.3+[0, 0, .8]
        with d.use('flat'):
            if k == 2:             # a bowl of persimmons
                d.lathe(tuple(q), [(0, .02), (.03, .12), (.08, .15)], (.55, .35, .22), 10)
                for j in range(4):
                    d.lathe(tuple(q+[.05*math.cos(j*1.6), .05*math.sin(j*1.6), .08]), [(-.035, .005), (-.03, .03), (0, .042), (.03, .03), (.035, .005)], vary((.92, .42, .08), .06), 8)
            else:
                d.lathe(tuple(q), [(0, .01), (.02, .06), (.14+.04*k, .065), (.18+.04*k, .04)], R.choice([(.32, .40, .55), (.62, .58, .50), (.55, .35, .22)]), 10)
    towel = fo+fu*2.0+fn*.58
    with d.use('canvas'):
        two_sided(d, [tuple(towel+[0, 0, .82]), tuple(towel+fu*.3+[0, 0, .82]), tuple(towel+fu*.3+[0, 0, .45]), tuple(towel+[0, 0, .45])], vary(CANVAS, .05))
    # wall positions: outer s = w2+side*sy, back s = w2-side*sy, far s = lx+d2
    shelf(m, d, frame3(outer, z), w2+side*.8, 1.05, .8, 2)
    shelf(m, d, frame3(back, z), w2+side*.55, 1.45, .7, 2)     # over the stove's side, clear of the door camera
    for k in range(4):     # persimmons and herbs hung from the rafters along the far wall
        q = fo+fu*(.9+.45*k)+fn*.45
        tube(d, [q+[0, 0, 1.5], q+[0, 0, 2.3]], .008, ROPE, 4)
        for j in range(4 if k % 2 == 0 else 0):
            with d.use('flat'):
                d.lathe(tuple(q+[0, 0, 1.55+.1*j]), [(-.035, .005), (-.03, .03), (0, .042), (.03, .03), (.035, .005)], vary((.92, .42, .08), .06), 8)
        if k % 2:
            potted = q+[0, 0, 1.55]
            for j in range(6):
                a_ = j*1.05; tip = potted+[.12*math.cos(a_), .12*math.sin(a_), -.18]
                two_sided(d, [tuple(potted), tuple((potted+tip)/2+[.03, 0, 0]), tuple(tip), tuple((potted+tip)/2-[.03, 0, 0])], vary((.30, .42, .14), .12))
    q = Hl(d2-.55, w2-.55, 1.75); glass_float(d, q[0], q[1], q[2], .14, .35)
    q = Hl(d2-.3, .35); basket(d, q[0], q[1], z, .2, .22, fruit=5)


def furnish_library(m, d, c, ang, side, W):
    """As painted: the desk under the far window with the map and lamp, bookshelves along the back wall, the globe
    on a crate in the corner, a rug and cushion, the backpack and crates by the door, pictures and the kite."""
    z = c[2]; outer, back, s_m, s_p = W; far = s_m if side > 0 else s_p; d2, w2 = L.HUT[1]/2, L.HUT[0]/2
    Hl = room(c, ang, side)
    q = Hl(0., -w2+.47); prop('crate_desk', q[0], q[1], z, lyaw(ang, 0, side), 1.)
    for sy in (-1.15, -.15):      # toward the far wall, so the doorway corner looks along them
        q = Hl(-d2+.26, sy); prop('bookshelf', q[0], q[1], z, lyaw(ang, 1, 0), 1.)
    q = Hl(d2-.36, -w2+.38); crate(m, q[0], q[1], z, (.45, .45, .45), ang); prop('globe', q[0], q[1], z+.45, ang+200, 1.)
    q = Hl(.35, .25); rug(d, q[0], q[1], z, 1.3, 1.8, ang, 'rug'); cushion(d, q[0], q[1], z+.012, .55, ang+10)
    q = Hl(-d2+.38, w2-.42); prop('backpack', q[0], q[1], z, lyaw(ang, 1, -side*.3), .95)
    q = Hl(d2-.4, w2-.5); crate(m, q[0], q[1], z, (.5, .42, .4), ang+8); crate(m, q[0], q[1], z+.4, (.4, .36, .3), ang-6)
    o, u, n = frame3(outer, z)
    wall_picture(d, (o, u, n), w2+side*.95, 1.1, 1.85, .075, 'kite', .6)
    fo, fu, fn = frame3(far, z)
    wall_picture(d, (fo, fu, fn), .47, 1.0, 1.9, .07, 'map', .75)
    wall_picture(d, (fo, fu, fn), 2.33, 1.2, 1.7, .075, 'pictures', .5, True)
    q = Hl(d2-.3, .3); basket(d, q[0], q[1], z, .19, .26, scrolls=4)
    q = Hl(-.62, -.5); book_stack(d, q[0], q[1], z, 5, ang)
    q = Hl(.9, .95); book_stack(d, q[0], q[1], z, 3, ang+40)


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
    """As painted: a quilt hammock slung low along the far wall under the window, from the back wall to the outer
    wall; two futons side by side in front of it, pillows to the back wall, and a rug along the outer wall to the
    round window; shelves and pictures, a crate of folded quilts."""
    z = c[2]; outer, back, s_m, s_p = W; far = s_m if side > 0 else s_p; d2, w2 = L.HUT[1]/2, L.HUT[0]/2
    Hl = room(c, ang, side)
    for sy in (-.6, .56):           # 1.6 x 1.13 m each; the strip by the outer wall stays free to walk in
        q = Hl(-d2+.86, sy); prop('futon', q[0], q[1], z, ang+180, .8)
    hy = -w2+.3                     # the bag (hanging 0.55 m over the floor) stays clear of the wall and the futons
    hammock(d, Hl(-d2+.045, hy, 1.55), Hl(d2-.045, hy, 1.55), .84, .42, (('wall', rot((1, 0), ang)), ('wall', rot((-1, 0), ang))))
    shelf(m, d, frame3(back, z), w2-side*.45, 1.3, 1.1, 2)      # over the pillows, clear of the hammock's peg
    fo, fu, fn = frame3(far, z)
    wall_picture(d, (fo, fu, fn), .45, 1.15, 1.6, .075, 'pictures', .42, True)
    q = Hl(d2-.32, w2-.42); crate(m, q[0], q[1], z, (.5, .45, .42), ang)
    with d.use('quilt', grain=(1, 0, 0)):
        d.box((q[0], q[1], z+.42+.07), (.45, .4, .12), WHITE, .03)
    q = Hl(d2-.62, -.15); rug(d, q[0], q[1], z, .95, 2.1, ang, 'rug')
    q = Hl(.95, -.95); cushion(d, q[0], q[1], z, .5, ang+12)     # under the round window, clear of the door-to-hammock path
    o, u, n = frame3(outer, z); wall_picture(d, (o, u, n), w2+side*.95, 1.1, 1.7, .075, 'kite', .5)
    q = Hl(-d2+.3, w2-.3); book_stack(d, q[0], q[1], z, 4, ang)
    q = Hl(d2-.3, .45); basket(d, q[0], q[1], z, .18, .22, scrolls=2)


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
        on_wall(d, Wl, cy, .1, 1.2, 1.15, 2.35, 'map')
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
        on_wall(d, S, dx, .1, .75, 3.0, 3.75, 'kite', frame=False)
        on_wall(d, N, dx, .1, .7, 3.0, 3.7, 'pictures')
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
        on_wall(d, E, .4, -.08, .8, 1.35, 2.15, 'flag', frame=False)
        tube(d, [at(E, .4-.47, -.105, 2.18), at(E, .4+.47, -.105, 2.18)], .015, DARK, 6, 'wood_timber')
        for s in (-.43, .43): tube(d, [at(E, .4+s, -.03, 2.18), at(E, .4+s, -.12, 2.18)], .012, DARK, 6, 'wood_timber')
        # The west wall outside, seen from the bridge: a woodpile along its southern half, clear of the way round the
        # corner to the bridge; the hut's name board over the north door, above the sliding door's track.
        entry_woodpile(m, Wl, Y0+.3, Y0+1.9)
        entry_sign(d, N, dx, dh+.21, dh+.46, 1.0)
    finally:
        R = shared


def furnish_heart(m, d, p):
    x0, y0 = p['xy']; z = p['deck']; Rw = L.HEART_WALL
    P = lambda a, r, zz=0.: np.array([x0+r*math.cos(math.radians(a)), y0+r*math.sin(math.radians(a)), z+zz])
    q = P(45, 2.2); rug(d, q[0], q[1], z, 1.3, 2.3, 45, 'rug')
    prop('stump_kettle', q[0], q[1], z+.012, 20)
    for a, r in ((45+30, 2.2), (45-30, 2.25), (47, 3.0)):
        cq = P(a, r); cushion(d, cq[0], cq[1], z+.012, .6, a)
    q = P(103, 2.95); rug(d, q[0], q[1], z, 1.1, 1.8, 103, 'rug_blue')
    q = P(296, 2.5); rug(d, q[0], q[1], z, 1.5, 2.2, 296, 'rug')
    for a, r in ((296+20, 2.3), (296-22, 2.35)):
        cq = P(a, r); cushion(d, cq[0], cq[1], z+.012, .55, a)
    ap = Rw*math.cos(math.radians(22.5))
    def on_panel(mid, off, depth):
        a = math.radians(mid); nrm = np.array([math.cos(a), math.sin(a)]); t = np.array([-nrm[1], nrm[0]])
        return np.array([x0, y0])+nrm*(ap-depth)+t*off, t, -nrm
    for mid, off in ((180, -1.05), (180, 1.05), (0, 1.05)):
        q, t, nin = on_panel(mid, off, .24); prop('bookshelf', q[0], q[1], z, face_yaw(*nin), .95)
    q = P(205, Rw-.5); prop('backpack', q[0], q[1], z, face_yaw(x0-q[0], y0-q[1]))
    q = P(62, Rw-.55); crate(m, q[0], q[1], z, (.55, .42, .42), 62); q2 = P(70, Rw-.5); crate(m, q2[0], q2[1], z, (.45, .4, .36), 80)
    q, t, nin = on_panel(45, -1.12, .245); prop('bell', q[0], q[1], z+1.45, face_yaw(*nin), .8)   # its plate on the wall
    # map and kite on the panels beside the round windows
    for mid, off, pic, w, z0, z1 in ((180, 1.1, 'map', .75, 1.0, 1.85), (0, -1.05, 'kite', .7, 1.15, 1.85), (225, -1.1, 'pictures', .45, 1.25, 1.7)):
        q, t, nin = on_panel(mid, off, .075)
        wall_picture(d, (np.array([q[0], q[1], z]), np.r_[t, 0], np.r_[nin, 0]), 0, z0, z1, .0, pic, w)
    # a hammock from turns of rope round the camphor (over the shimenawa) to a peg on the panel beside the open
    # round window, its bag 0.6 m over the floor; lanterns strung from the trunk to the posts
    _, rad, wob, _, _ = trunk_shape(x0, y0, p['trunk'], p['trunk_top'], z, len('heart'))
    hz = z+1.72; o = np.array([x0, y0])+wob(hz); rr = rad(hz)*1.06+.03; a_ = math.radians(242)
    pc = math.radians(270); ap = Rw*math.cos(math.radians(22.5))-.045
    hammock(d, np.array([o[0]+rr*math.cos(a_), o[1]+rr*math.sin(a_), hz]), P(252, ap/math.cos(math.radians(252-270)), 1.74),
            .95, .42, (('wrap', o, rr), ('wall', (-math.cos(pc), -math.sin(pc)))))
    for k in range(8):
        a = 22.5+45*k; s0, s1 = P(a, p['trunk']+.15, 2.75), P(a, Rw-.1, 2.72)
        pts = [s0+(s1-s0)*t-[0, 0, .3*math.sin(math.pi*t)] for t in np.linspace(0, 1, 7)]
        tube(d, pts, .007, DARK, 4, 'wood_timber')
        for t in (.35, .7):
            q = s0+(s1-s0)*t-[0, 0, .3*math.sin(math.pi*t)]
            chochin(d, q[0], q[1], q[2]-.2, .2, .14)
    for a in (90, 270, 0):
        q = P(a, Rw-.35); glass_float(d, q[0], q[1], z+2.2, .13, .45)
    q = P(150, Rw-.6); basket(d, q[0], q[1], z, .2, .26, scrolls=4)
    q = P(58, 3.0); book_stack(d, q[0], q[1], z+.012, 4, 58)
    q = P(312, 3.25); book_stack(d, q[0], q[1], z+.012, 3, 10)
    q = P(120, Rw-.6); basket(d, q[0], q[1], z, .22, .24, fruit=6)
    # the loft shelf high on the north side, quilts folded on it (looks only)
    a0_, a1_ = 67.5, 112.5
    for f in (a0_+6, a1_-6):
        board(m, tuple(P(f, Rw-.15, 1.55)), tuple(P(f, 3.25, 2.18)), .1, .1, WOOD, 'wood_timber')
    pts = [P(a0_, Rw-.05)[:2], P(a1_, Rw-.05)[:2], P(a1_, 3.05)[:2], P(a0_, 3.05)[:2]]
    with m.use('wood_plank', grain=(1, 0, 0), jitter=True):
        prism(m, pts, z+2.2, z+2.28, vary(PLANK, .08), DARK)
    # The ladder stands square to the loft's straight front edge at its west end, clear of the window and of the
    # cushions round the stump: square rails leaning on the edge and standing on 0.85 m past it as handholds, round
    # rungs, and a low rail along the rest of the edge.
    u = np.array([0., 1., 0.]); v = np.array([1., 0., 0.]); c0 = np.array([x0, y0, z])
    edge = 3.05*math.cos(math.radians(22.5)); half = 3.05*math.sin(math.radians(22.5)); lean = 1/math.tan(math.radians(74))
    foot = edge-.06-2.28*lean; l0, l1 = -1.1, -.7
    for f in (l0, l1):
        strut(m, c0+u*foot+v*f, c0+u*(foot+3.13*lean)+v*f+[0, 0, 3.13], .075, .085, v)
    for k in range(1, 9):
        h = .26*k; q = c0+u*(foot+h*lean)+[0, 0, h]
        tube(m, [q+v*l0, q+v*l1], .022, WOOD, 6, 'wood_timber')
    rail = c0+u*(edge-.05)+[0, 0, 2.28]
    for f in (-.5, .3, half-.06):
        post(m, *(rail+v*f)[:2], rail[2], rail[2]+.62, .07, WOOD)
    board(m, tuple(rail+v*-.54+[0, 0, .64]), tuple(rail+v*(half-.02)+[0, 0, .64]), .08, .045, WOOD, 'wood_timber')
    tube(d, [rail+v*f+[0, 0, .3] for f in (-.5, half-.06)], .014, ROPE, 5)
    for k in range(3):
        q = P(80+10*k, 3.7); c = [(.20, .27, .48), (.80, .74, .62), (.62, .20, .12)][k]
        with d.use('quilt' if k != 1 else 'canvas', grain=(1, 0, 0)):
            d.box((q[0], q[1], z+2.28+.08+.0*k), (.55, .5, .16), WHITE if k != 1 else c, .04)


def furnish_boat(m, d, p, c, ang):
    z = c[2]
    q = local(c, ang+90, 0, 0); rug(d, q[0], q[1], z, 1.3, 2.6, ang, 'rug_blue')
    for s in (-1, 1):
        q = local(c, ang+90, .3, s*.72); crate(m, q[0], q[1], z, (1.2, .4, .38), ang+90)
        cushion(d, *local(c, ang+90, .0, s*.72)[:2], z+.38, .4, ang); cushion(d, *local(c, ang+90, .55, s*.72)[:2], z+.38, .4, ang+5)
    for s in (-1, 1):   # oars laid along the ribs
        a = local(c, ang+90, -1.3, s*.5, 1.72); b = local(c, ang+90, 1.1, s*.55, 1.78)
        board(d, a, b, .06, .04, PALE, 'wood_pale')
        with d.at(tuple(b), ang+90):
            with d.use('wood_pale', grain=(1, 0, 0)):
                d.box((.25, 0, 0), (.5, .16, .03), PALE)
    # a fishing net hung under the hull, sagging between the posts
    for k in range(6):
        a = local(c, ang+90, -1.6+.55*k, -.75, 1.72); b = local(c, ang+90, -1.6+.55*k, .75, 1.72)
        tube(d, [a+(b-a)*t-[0, 0, .35*math.sin(math.pi*t)] for t in np.linspace(0, 1, 7)], .008, ROPE, 4)
    for k in range(5):
        pts = [local(c, ang+90, -1.6+2.75*t, -.75+.3*k+.05, 1.72-.35*math.sin(math.pi*(.3*k+.05)/1.5)) for t in np.linspace(0, 1, 7)]
        tube(d, pts, .008, ROPE, 4)
    for k in range(3):
        q = local(c, ang+90, -1.2+.6*k, .3*(k-1), 1.45); glass_float(d, q[0], q[1], q[2], .11, .2)


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


def on_wall(d, wall, a, b, w, z0, z1, pic, frame=True):
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


def heart_room(m, d, p):
    x0, y0 = p['xy']; z = p['deck']; Rw = L.HEART_WALL; h = 2.8; top = z+L.ROOF_TOP['heart']
    ring8 = L.octagon(Rw); panel = 2*Rw*math.sin(math.radians(22.5))
    kinds = {45: 'door', 135: 'door', 225: 'door', 270: 'open-round', 0: 'round', 180: 'round', 90: 'window', 315: 'window'}
    with m.at((x0, y0, z), 0):
        for k in range(8):
            a, b = ring8[k], ring8[(k+1) % 8]; mid = round(45*(k+1)) % 360; kind = kinds[mid]
            op = {'door': (panel/2, .95, 0., 1.95, 'door'), 'open-round': (panel/2, 1.5, .65, 2.15, 'open-round'),
                  'round': (panel/2, 1.25, .75, 2.0, 'round'), 'window': (panel/2, 1.7, .8, 1.95, 'window')}[kind]
            wall(m, a, b, h, [op], outside='plaster', turn=45.)
            post(m, a[0], a[1], -.04, h+.05, .22, DARK)
    for k, mid in enumerate((45, 135, 225)):
        a = math.radians(mid); r = Rw*math.cos(math.radians(22.5))+.07
        noren(d, x0+r*math.cos(a), y0+r*math.sin(a), z+1.95, .92, .72, mid+90, 'noren_indigo' if k != 1 else 'noren_cream')
    eave = [(x0+x*(Rw+.85)/Rw, y0+y*(Rw+.85)/Rw) for x, y in ring8]
    collar = [(x0+x*1.45/Rw, y0+y*1.45/Rw) for x, y in ring8]
    ze = z+h-.05
    for k in range(8):
        a, b = eave[k], eave[(k+1) % 8]; ca, cb = collar[k], collar[(k+1) % 8]
        shingled(m, d, [(*a, ze), (*b, ze), (*cb, top), (*ca, top)])
        dz = .005*(k % 2)        # neighbouring fascias and plates overlap in the corners: every other one lower
        board(m, (*a, ze+.02-dz), (*b, ze+.02-dz), .1, .16, DARK, 'wood_timber')
        board(m, (*ca, top-.12), (*a, ze-.08), .12, .14, WOOD, 'wood_timber')          # rafter, seen from inside
        mid = (np.array(a)+np.array(b))/2; mc = (np.array(ca)+np.array(cb))/2
        board(m, (*mc, top-.14), (*mid, ze-.08), .08, .1, WOOD, 'wood_timber')
        glass_float(d, a[0], a[1], ze-.35, .13, .28) if k % 2 else chochin(d, a[0], a[1], ze-.42, .26, .3, 260)
    with m.use('moss'):
        prism(m, [(x0+x*1.55/Rw, y0+y*1.55/Rw) for x, y in ring8], top-.08, top+.08, vary(MOSS), vary(MOSS, .1))
    for k in range(8):
        a, b = ring8[k], ring8[(k+1) % 8]; dz = .005*(k % 2)
        board(m, (x0+a[0], y0+a[1], z+h+.02-dz), (x0+b[0], y0+b[1], z+h+.02-dz), .16, .16, DARK, 'wood_timber')
    shimenawa(d, p, 'heart', 1.38)
    interior((x0, y0, z+1.5), radius=round(Rw*math.cos(math.radians(22.5))+.1, 2), half_height=h-1.5+.35)
    leaves_on(d, [(x0+x*(Rw-.3)/Rw, y0+y*(Rw-.3)/Rw) for x, y in ring8], z, 16)
    shimenawa(d, p, 'heart', L.ROOF_TOP['heart']+.55)          # and where the camphor leaves the roof
    for k in (1, 3, 5, 7):
        a = math.radians(45*k); chochin(d, x0+(Rw+.5)*math.cos(a), y0+(Rw+.5)*math.sin(a), z+2.3, .3, .2, 300)
    for a in (20, 110, 200, 290):      # the room's warm light, from the lantern strings round the trunk
        r_ = (p['trunk']+Rw)/2; light(x0+r_*math.cos(math.radians(a)), y0+r_*math.sin(math.radians(a)), z+2.3, 850, 5.5, int(a == 290))
    furnish_heart(m, d, p)


def boat_room(m, d, p):
    x0, y0 = p['xy']; z = p['deck']; ang = p['open']; rc = p['trunk']+1.3
    c = np.array([x0+rc*math.cos(math.radians(ang)), y0+rc*math.sin(math.radians(ang)), z])
    xs = np.linspace(-2.1, 2.1, 17); fs = np.linspace(0, math.pi, 12)
    hb = lambda s: .95*math.sqrt(max(0., 1-max(0., s)**2.5))
    zg = lambda s: 1.72+.28*max(0., s)**2
    dp = lambda s: .78*(1-.2*max(0., s)**2)
    sec = [[(x, hb(x/2.1)*math.cos(f), zg(x/2.1)+dp(x/2.1)*math.sin(f)) for f in fs] for x in xs]
    with m.at(tuple(c), ang+90):
        for i in range(len(xs)-1):
            for j in range(len(fs)-1):
                q = [sec[i][j], sec[i+1][j], sec[i+1][j+1], sec[i][j+1]]
                mid = np.mean(q, axis=0); axis = np.array([mid[0], 0, zg(mid[0]/2.1)])
                nrm = np.cross(np.subtract(q[1], q[0]), np.subtract(q[3], q[0]))
                out = q if nrm@(mid-axis) > 0 else q[::-1]
                if j in (0, len(fs)-2):
                    with m.use('wood_pale', grain=(1, 0, 0)): m.poly(out, (.78, .74, .64))
                else:
                    with m.use('hull', grain=(1, 0, 0)): m.poly(out, WHITE)
                with m.use('wood_plank', grain=(1, 0, 0)): m.poly(out[::-1], vary(PLANK, .08))
        with m.use('hull', grain=(0, 1, 0)):
            two_sided(m, sec[0], WHITE, vary(PLANK))
        for x in np.linspace(-1.9, 1.9, 9):      # ribs inside the hull
            s = x/2.1; pts = [(x, hb(s)*math.cos(f)*.96, zg(s)+dp(s)*math.sin(f)*.96-.02) for f in np.linspace(0, math.pi, 10)]
            tube(m, pts, .035, WOOD, 4, 'wood_timber')
        tube(m, [(x, 0, zg(x/2.1)+dp(x/2.1)+.03) for x in np.linspace(-2.1, 2.05, 12)], .06, DARK, 6, 'wood_timber')  # keel
        for x in (-1.75, 1.15):
            for s in (-1, 1): post(m, x, s*hb(x/2.1)*.9, 0, zg(x/2.1)+.02, .13, WOOD)
        for x in (-1.75, 1.15):
            board(m, (x, -hb(x/2.1)*.9, zg(x/2.1)), (x, hb(x/2.1)*.9, zg(x/2.1)), .12, .12, DARK, 'wood_timber')
    q = local(c, ang+90, 0, 0); chochin(d, q[0], q[1], z+1.95, .3, .45, 1000)
    furnish_boat(m, d, p, c, ang)


def pulley_crane(m, d, p):
    x0, y0 = p['xy']; z = p['deck']; a = math.radians(p['open']); u = np.array([math.cos(a), math.sin(a)]); c = np.array([x0, y0])
    board(m, (*(c+u*.2), z+3.1), (*(c+u*3.9), z+3.1), .16, .18, WOOD, 'wood_timber')
    board(m, (*(c+u*p['trunk']*.9), z+1.5), (*(c+u*2.1), z+3.0), .14, .14, WOOD, 'wood_timber')
    ring(d, c, p['trunk']+.06, z+3.05, .035, ROPE, 16); ring(d, c, p['trunk']+.06, z+1.5, .035, ROPE, 16)
    tip = c+u*3.75; v = np.array([-u[1], u[0]])
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
        if name in ('library', 'kitchen', 'sleep', 'chimes'):
            # a crate and a planter or rope coil in the deck corners furthest from the bridges and the hut
            poly = world_poly(p); c = np.array(p['xy'])
            busy = [l['angle'] for l in p['links']]+([p['open']]*2 if name != 'chimes' else [])
            gap = lambda q: min(abs(((math.degrees(math.atan2(q[1]-c[1], q[0]-c[0]))-b+540) % 360)-180) for b in busy)
            corners = sorted(range(len(poly)), key=lambda k: -gap(poly[k]))
            k1 = corners[0]; k2 = next(k for k in corners[1:] if min(abs(k-k1), len(poly)-abs(k-k1)) > 1)
            corner = np.array(poly[k1]); q = corner+(c-corner)/np.linalg.norm(c-corner)*.6
            crate(m, q[0], q[1], p['deck'], (.5, .4, .38), R.uniform(0, 90))
            corner = np.array(poly[k2]); q = corner+(c-corner)/np.linalg.norm(c-corner)*.65
            if name in ('library', 'sleep'): prop('planter', q[0], q[1], p['deck'], face_yaw(*(c-q)), .9)
            else: rope_coil(d, q[0], q[1], p['deck'])
    for b in pl['bridges']:
        bridge(m, d, b)
    entry_hut(m, d, P['entry'])
    rooms = {}
    for name in ('library', 'kitchen', 'sleep'):
        rooms[name] = hut(m, d, P[name], L.HUT[1], L.HUT[0], name)
    furnish_library(m, d, *rooms['library']); furnish_kitchen(m, d, *rooms['kitchen']); furnish_sleep(m, d, *rooms['sleep'])
    # quilts over the sleeping nest's rail, persimmons under the kitchen eaves
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
