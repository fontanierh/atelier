"""The houses on the main road in Blender: three house models and the five lots they stand on (layout.py).

    blender -b --python-exit-code 1 --python games/yorimichi/world/regions/houses/build.py

House_A (tiled, hip-and-gable roof), House_B (thatched farmhouse) and House_C (two storeys) are modelled in the lot
frame: origin at the house centre on the lot level, -y toward the road. They use the village kit (one opaque
vertex-colour material, M_Village in Unreal) and a few UCX boxes for collision: the body, the engawa, the porch and
the steps.

HouseLot_1..5 are the level terraces the houses stand on, one mesh per lot because each meets its own ground: the lot
top (slot Ground: the terrain's MI_Ground with the terrain's UVs, world metres / 6, so it reads as the same earth),
the gravel yard, the stepping stones from the gate to the entrance, the moss garden bed, the gravel drip line under
the eaves, the stone kerb and clipped hedge along the road with the gate and its steps, and battered dry-stone walls
(ishigaki) down the sides and back to the final heightmap. They collide as complex.

Writes build/yorimichi/houses/assets/*.fbx, Houses.blend (every house on its lot), manifest.json (triangles,
materials, bounds) and build-identity.json.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import hashlib, json, math, random
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
from village.build import Mesh as KitMesh, PALETTE as KIT
from houses.layout import HOUSES, HALF_W, BACK, to_world, front_y

HERE = Path(__file__).resolve().parent
OUT = yori.OUT / 'houses'
# Linear colours, as the village kit's (M_Village converts the exported sRGB vertex colours back). Keep clear of the
# lamp range (r >= .8, .35 <= g <= .72, b <= .3), which M_Village lights up.
PAL = dict(KIT)
PAL.update({
    'plaster': (.66, .59, .43), 'plaster_shade': (.52, .45, .31),
    'timber': (.075, .034, .012), 'timber_light': (.17, .080, .026), 'board': (.042, .021, .010), 'skirt': (.030, .018, .010),
    'tile': (.028, .037, .052), 'tile_roll': (.046, .058, .076), 'tile_edge': (.014, .020, .030),
    'thatch': (.21, .14, .060), 'thatch_dark': (.13, .082, .038), 'thatch_light': (.27, .18, .080), 'thatch_cut': (.33, .22, .10),
    'shoji': (.74, .67, .50), 'glass': (.022, .034, .042), 'soffit': (.040, .020, .009),
    'stone': (.20, .19, .15), 'stone_light': (.31, .29, .22), 'stone_dark': (.10, .095, .075),
    'gravel': (.44, .41, .33), 'moss': (.050, .088, .020), 'hedge': (.036, .090, .018), 'hedge_light': (.060, .135, .026),
    'log': (.20, .12, .045), 'log_end': (.38, .26, .12),
})
# The front edge of each entrance's step (lot frame y): the stepping stones from the gate stop short of it.
DOOR_STEP = {'A': -5.5, 'B': -4.35, 'C': -5.0}
R = random.Random(41)


def variant(key, amount=.06):
    f = R.uniform(1 - amount, 1 + amount)
    return tuple(min(1., c * f) for c in PAL[key])


def smooth(t):
    t = min(1., max(0., t)); return t * t * (3 - 2 * t)


def newell(pts):
    n = Vector((0, 0, 0))
    for a, b in zip(pts, pts[1:] + pts[:1]):
        n.x += (a.y - b.y) * (a.z + b.z); n.y += (a.z - b.z) * (a.x + b.x); n.z += (a.x - b.x) * (a.y + b.y)
    return n


class Mesh(KitMesh):
    """The village kit's mesh with the house palette, a second material slot (1: the terrain's Ground) and faces
    wound by an outward hint (`out`, in the current local frame)."""

    def __init__(self, name, lot=None):
        super().__init__(name); self.slots = []; self.lot = lot

    def poly(self, points, color, slot=0, out=None):
        if isinstance(color, str): color = PAL[color]
        if out is not None and newell([Vector(q) for q in points]).dot(Vector(out)) < 0:
            points = list(points)[::-1]
        k = len(self.faces); super().poly(points, color)
        if len(self.faces) > k: self.slots.append(slot)

    def bar(self, c, s, color):
        """A box without its back and bottom: a member standing proud of a wall that lies behind it (+y)."""
        x, y, z = c; w, d, h = s
        p = [(x + dx * w / 2, y + dy * d / 2, z + dz * h / 2) for dx, dy, dz in
             [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]]
        for f in [(4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (3, 0, 4, 7)]: self.poly([p[i] for i in f], color)

    def log(self, a, b, r, color, end, n=6):
        """A log from a to b (along x), its cut end showing at b."""
        ring = [(r * math.cos(t), r * math.sin(t)) for t in np.linspace(0, math.tau, n + 1)[:-1]]
        A = [(a[0], a[1] + u, a[2] + v) for u, v in ring]; B = [(b[0], b[1] + u, b[2] + v) for u, v in ring]
        for k in range(n):
            u = (ring[k][0] + ring[(k + 1) % n][0]) / 2; v = (ring[k][1] + ring[(k + 1) % n][1]) / 2
            self.poly([A[k], B[k], B[(k + 1) % n], A[(k + 1) % n]], color, out=(0, u, v))
        self.poly(B, end, out=(1, 0, 0))

    def object(self, mats, shade=None):
        data = bpy.data.meshes.new(self.name); data.from_pydata(self.vertices, [], self.faces); data.update()
        used = sorted(set(self.slots)); index = {s: i for i, s in enumerate(used)}
        for s in used: data.materials.append(mats[s])
        uv = data.uv_layers.new(name='UVMap')
        for f, s in zip(data.polygons, self.slots):
            f.material_index = index[s]
            if s == 1:      # the terrain's UVs
                for li in f.loop_indices:
                    co = data.vertices[data.loops[li].vertex_index].co
                    wx, wy = to_world(self.lot, co.x, co.y)
                    uv.data[li].uv = (float(wx) / 6., float(wy) / 6.)
            else:           # dominant-plane UVs: no texture reads them, they give valid tangents
                drop = max(range(3), key=lambda i: abs(f.normal[i])); axes = [i for i in range(3) if i != drop]
                for li in f.loop_indices:
                    co = data.vertices[data.loops[li].vertex_index].co
                    uv.data[li].uv = (co[axes[0]], co[axes[1]])
        col = data.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='POINT')
        for i, c in enumerate(self.colors):
            k = shade(self.vertices[i][2]) if shade else 1.
            col.data[i].color = (c[0] * k, c[1] * k, c[2] * k, c[3])
        obj = bpy.data.objects.new(self.name, data); bpy.context.collection.objects.link(obj)
        return obj


# ----------------------------------------------------------------------------- roofs
def tiled(m, pts, up, body='tile', roll='tile_roll', spacing=.34, r=.055, under=.16):
    """One tiled roof face: the convex polygon `pts`, round-tile rolls running up the slope (`up`: horizontal, toward
    the ridge) and its underside `under` metres below."""
    P = [np.array(p, float) for p in pts]
    n = np.array(newell([Vector(p) for p in pts])); n /= np.linalg.norm(n)
    if n[2] < 0: n = -n
    m.poly(pts, body, out=n)
    m.poly([(p[0], p[1], p[2] - under) for p in pts], 'soffit', out=-n)
    v = np.array([up[0], up[1], 0.], float); v -= n * v.dot(n); v /= np.linalg.norm(v)
    u = np.cross(v, n); o = P[0]
    S = [float((p - o).dot(u)) for p in P]; T = [float((p - o).dot(v)) for p in P]
    for s in np.arange(min(S) + spacing / 2, max(S) - spacing / 4, spacing):
        ts = []
        for a in range(len(P)):
            b = (a + 1) % len(P)
            if (S[a] - s) * (S[b] - s) < 0: ts.append(T[a] + (T[b] - T[a]) * (s - S[a]) / (S[b] - S[a]))
        if len(ts) < 2 or max(ts) - min(ts) < .25: continue
        t0, t1 = min(ts), max(ts) - .03
        a0 = o + u * s + v * t0; a1 = o + u * s + v * t1
        L0, L1, R0, R1, C0, C1 = a0 - u * r, a1 - u * r, a0 + u * r, a1 + u * r, a0 + n * r * 1.2, a1 + n * r * 1.2
        c = variant(roll, .05)
        m.poly([L0, L1, C1, C0], c, out=n - u); m.poly([C0, C1, R1, R0], c, out=n + u); m.poly([L0, C0, R0], c, out=-v)


def ridge(m, a, b, w=.34, h=.36, color='tile_edge'):
    m.beam((a[0], a[1], a[2] + h / 2 - .08), (b[0], b[1], b[2] + h / 2 - .08), w, h, color)


def onigawara(m, x, y, z, yaw):
    """The ridge-end tile, a plate across the ridge's end."""
    with m.at((x, y, z), yaw):
        m.box((0, 0, .20), (.18, .46, .55), 'tile_edge', .05)
        m.box((0, 0, .52), (.14, .56, .14), 'tile_edge', .03)


def eave_ends(m, a, b, z, out, pitch, under=.16, spacing=.46, color='timber_light'):
    """Rafters under an eave edge from a to b (xy), their ends toward `out`, just under the roof's underside."""
    a, b = np.array(a, float), np.array(b, float); L = np.linalg.norm(b - a); d = (b - a) / L; o = np.array(out, float)
    z0 = z - under - .055; n = int(L / spacing)
    for k in range(1, n):
        p = a + d * k * L / n
        m.beam((p[0] - o[0] * .9, p[1] - o[1] * .9, z0 + .9 * pitch), (p[0] - o[0] * .1, p[1] - o[1] * .1, z0 + .1 * pitch), .075, .09, color)


def fascia(m, a, b, z, h=.18, color='timber'):
    m.beam((a[0], a[1], z - h / 2 + .02), (b[0], b[1], z - h / 2 + .02), .09, h, color)


def irimoya(m, xe, yf, yb, ze, p, a, g):
    """Hip-and-gable roof: eaves round the rectangle +-xe by yf..yb at ze, pitch p. The hips run `a` in to where the
    gable (tsuma) stands; the upper gable roof overhangs it by g."""
    yc = (yf + yb) / 2; zr = ze + (yc - yf) * p; xr = xe - a; zm = ze + a * p
    xg = xr + g; zg = ze + (a - g) * p
    front = [(-xe, yf, ze), (xe, yf, ze), (xg, yf + a - g, zg), (xg, yc, zr), (-xg, yc, zr), (-xg, yf + a - g, zg)]
    back = [(x, yb + yf - y, z) for x, y, z in front]
    tiled(m, front, (0, 1)); tiled(m, back, (0, -1))
    for s in (-1, 1):
        tiled(m, [(s * xe, yf, ze), (s * xe, yb, ze), (s * xr, yb - a, zm), (s * xr, yf + a, zm)], (-s, 0))
        # the gable: plaster in a timber frame, set back under the upper roof, a gegyo board under the ridge end
        m.poly([(s * xr, yf + a, zm), (s * xr, yb - a, zm), (s * xr, yc, zr - .05)], 'plaster', out=(s, 0, 0))
        m.beam((s * (xr + .03), yf + a, zm + .06), (s * (xr + .03), yb - a, zm + .06), .12, .16, 'timber')
        m.beam((s * (xr + .03), yf + a + .8, zm + .45), (s * (xr + .03), yb - a - .8, zm + .45), .09, .10, 'timber')
        m.beam((s * (xr + .03), yc, zm), (s * (xr + .03), yc, zr - .1), .10, .10, 'timber')
        m.box((s * (xg + .02), yc, zr - .45), (.08, .34, .55), 'timber_light', .03)
        for yy, sy in ((yf, 1), (yb, -1)):
            m.beam((s * (xg + .02), yy + sy * (a - g), zg - .05), (s * (xg + .02), yc, zr - .05), .08, .26, 'timber')   # verge board
            ridge(m, (s * xe, yy, ze), (s * xg, yy + sy * (a - g), zg), .22, .22)                                    # hip
            m.beam((s * xe, yy, ze + .08), (s * (xe + .22), yy - sy * .22, ze + .34), .18, .18, 'tile_edge')      # its turned-up end
        onigawara(m, s * (xg + .05), yc, zr, 0)
        fascia(m, (s * xe, yf), (s * xe, yb), ze)
    ridge(m, (-xg, yc, zr), (xg, yc, zr), .36, .40)
    m.beam((-xg + .4, yc, zr + .30), (xg - .4, yc, zr + .30), .22, .14, 'tile_roll')
    for yy in (yf, yb): fascia(m, (-xe, yy), (xe, yy), ze)


def gable_y(m, xc, half, y0, y1, ze, p, g=.25):
    """A small gabled porch roof, its ridge along y from the house (y0) out to its front (y1 < y0)."""
    zr = ze + half * p
    for s in (-1, 1):
        tiled(m, [(xc + s * half, y1 - g, ze), (xc + s * half, y0, ze), (xc, y0, zr), (xc, y1 - g, zr)], (-s, 0), spacing=.30)
        m.beam((xc + s * half, y1 - g - .02, ze - .02), (xc, y1 - g - .02, zr - .02), .08, .24, 'timber')   # verge board
        fascia(m, (xc + s * half, y0), (xc + s * half, y1 - g), ze)
    m.poly([(xc - half + .25, y1, ze + .08), (xc + half - .25, y1, ze + .08), (xc, y1, zr - .15)], 'plaster', out=(0, -1, 0))
    m.beam((xc - half + .2, y1 + .02, ze + .05), (xc + half - .2, y1 + .02, ze + .05), .14, .16, 'timber')
    ridge(m, (xc, y0 - .3, zr), (xc, y1 - g, zr), .26, .30)
    onigawara(m, xc, y1 - g - .03, zr, 90)
    m.poly([(xc - half, y0, ze - .16), (xc + half, y0, ze - .16), (xc + half, y1 - g, ze - .16), (xc - half, y1 - g, ze - .16)],
           'soffit', out=(0, 0, -1))


def pent(m, inner, outer, zi, zo):
    """A pent roof (hisashi) round a storey: from the rectangle `inner` (x0, x1, y0, y1) at zi down to `outer` at zo."""
    (a0, a1, b0, b1), (c0, c1, d0, d1) = inner, outer
    for pts, up in (([(c0, d0, zo), (c1, d0, zo), (a1, b0, zi), (a0, b0, zi)], (0, 1)),
                    ([(c1, d1, zo), (c0, d1, zo), (a0, b1, zi), (a1, b1, zi)], (0, -1)),
                    ([(c1, d0, zo), (c1, d1, zo), (a1, b1, zi), (a1, b0, zi)], (-1, 0)),
                    ([(c0, d1, zo), (c0, d0, zo), (a0, b0, zi), (a0, b1, zi)], (1, 0))):
        tiled(m, pts, up, under=.14)
    corners = [(c0, d0), (c1, d0), (c1, d1), (c0, d1)]; inner_c = [(a0, b0), (a1, b0), (a1, b1), (a0, b1)]
    for (x, y), (xi, yi) in zip(corners, inner_c): ridge(m, (x, y, zo), (xi, yi, zi), .18, .18)
    for (x0, y0), (x1, y1) in zip(corners, corners[1:] + corners[:1]): fascia(m, (x0, y0), (x1, y1), zo, .15)


# ----------------------------------------------------------------------------- walls, doors, windows
# In a wall frame: x along the wall, the wall face at y = 0, outside toward -y.
def post(m, x, y, z0, z1, s=.15, stone=True, color='timber'):
    m.box((x, y, (z0 + z1) / 2), (s, s, z1 - z0), color)
    if stone:
        m.lathe((x, y, z0 - .02), [(0, s * 1.35), (.10, s * 1.4), (.17, s * 1.05), (.19, 0)], variant('stone_light', .08), 8)


def glass_door(m, x, w, z0, h):
    m.bar((x, -.05, z0 + h / 2), (w, .04, h), 'glass')
    for xx in (x - w / 2 + .03, x + w / 2 - .03): m.bar((xx, -.08, z0 + h / 2), (.06, .05, h), 'timber_light')
    for zz, hh in ((z0 + .16, .32), (z0 + h * .62, .04), (z0 + h - .03, .06)):
        m.bar((x, -.085, zz), (w - .06, .05, hh), 'timber_light' if hh > .1 else 'timber')


def shoji(m, x, w, z0, h, cols=3, rows=5):
    m.bar((x, -.04, z0 + h / 2), (w, .03, h), 'shoji')
    for xx in (x - w / 2 + .025, x + w / 2 - .025): m.bar((xx, -.07, z0 + h / 2), (.05, .04, h), 'timber_light')
    for k in range(1, cols): m.bar((x - w / 2 + w * k / cols, -.065, z0 + h / 2), (.022, .03, h - .05), 'timber_light')
    for k in range(1, rows): m.bar((x, -.065, z0 + h * k / rows), (w - .04, .03, .022), 'timber_light')
    m.bar((x, -.07, z0 + .12), (w - .04, .04, .24), 'timber_light')


def lattice_door(m, x, w, z0, h, pitch=.085):
    m.bar((x, -.04, z0 + h / 2), (w, .03, h), 'board')
    for xx in (x - w / 2 + .03, x + w / 2 - .03): m.bar((xx, -.08, z0 + h / 2), (.06, .05, h), 'timber_light')
    for zz in (z0 + .05, z0 + h * .45, z0 + h - .04): m.bar((x, -.08, zz), (w - .06, .05, .07), 'timber_light')
    n = int(w / pitch)
    for k in range(1, n): m.bar((x - w / 2 + k * w / n, -.07, z0 + h / 2), (.025, .03, h - .1), 'timber_light')


def koshi_window(m, x, z, w, h):
    """A paper window behind a timber lattice (koshi)."""
    m.bar((x, -.02, z), (w, .03, h), 'shoji')
    for dz in (-1, 1): m.bar((x, -.05, z + dz * (h / 2 + .035)), (w + .14, .06, .07), 'timber')
    for dx in (-1, 1): m.bar((x + dx * (w / 2 + .035), -.05, z), (.07, .06, h), 'timber')
    n = max(2, int(w / .11))
    for k in range(1, n): m.bar((x - w / 2 + k * w / n, -.06, z), (.03, .04, h), 'timber')
    m.bar((x, -.09, z - h / 2 - .09), (w + .24, .08, .05), 'timber')


def amado(m, x, w, z0, h):
    """A wooden storm shutter."""
    m.bar((x, -.06, z0 + h / 2), (w - .01, .05, h), variant('board', .12))
    for k in (1, 2): m.bar((x, -.09, z0 + h * k / 3), (w - .05, .03, .035), 'timber')


def wall_frame(m, w, z0, z1, posts, kamoi=None):
    """Posts, sill, top beam and door head on a wall face."""
    for x in posts: m.bar((x, -.02, (z0 + z1) / 2), (.16, .06, z1 - z0), 'timber')
    m.bar((0, -.03, z0 + .06), (w + .04, .07, .14), 'timber')
    m.bar((0, -.03, z1 - .08), (w + .04, .08, .18), 'timber')
    if kamoi: m.bar((0, -.035, kamoi), (w + .02, .08, .12), 'timber')


def skirt(m, w, z1, posts):
    """Under the raised floor: a dark recessed skirt between posts on foundation stones."""
    m.bar((0, .03, z1 / 2), (w, .04, z1), 'skirt')
    for x in posts: post(m, x, -.02, .0, z1, .16, True)


def wall(m, side, w, d):
    """The wall frame of one side of a w x d body: front (-y), back (+y), left (-x), right (+x)."""
    return {'front': m.at((0, -d / 2, 0), 0), 'back': m.at((0, d / 2, 0), 180),
            'left': m.at((-w / 2, 0, 0), -90), 'right': m.at((w / 2, 0, 0), 90)}[side]


def bays(L, n):
    return [-L / 2 + k * L / n for k in range(n + 1)]


def mid(posts, k):
    return (posts[k] + posts[k + 1]) / 2


def body_walls(m, w, d, fl, top, kamoi, posts_of, dress):
    """Skirt, frame and whatever `dress(side, L, posts)` adds, on each of the four walls."""
    for side in ('front', 'back', 'left', 'right'):
        L = w if side in ('front', 'back') else d
        posts = posts_of(side, L)
        with wall(m, side, w, d):
            skirt(m, L, fl, [p for p in posts if abs(p) < L / 2 - .01] + [-L / 2 + .08, L / 2 - .08])
            wall_frame(m, L, fl, top, posts, kamoi)
            dress(side, L, posts)


def pots(m, x, y):
    for dx, sc, key in ((0, .9, 'clay'), (.45, .7, 'bluepot')):
        with m.at((x + dx, y, 0)):
            m.lathe((0, 0, 0), [(a * sc, b * sc) for a, b in [(0, 0), (.02, .16), (.25, .22), (.40, .19), (.40, 0)]], key, 8)
            m.lathe((0, 0, .40 * sc), [(0, .17 * sc), (.12 * sc, .24 * sc), (.30 * sc, .12 * sc), (.34 * sc, 0)], variant('leaf', .2), 7)


def step_stone(m, x, y, z, w, d):
    """A flat stone step, its top at z."""
    m.box((x, y, z / 2 - .02), (w, d, z + .04), variant('stone_light', .08), .05)
    m.collider((x, y, z / 2), (w, d, max(z, .05)))


def engawa(m, x0, x1, y_wall, depth, top=.5):
    """The veranda along the front: boards, an edge beam on short posts, its collision box. Returns its edge."""
    boards = int(round(depth / .23))
    for k in range(boards):
        m.box(((x0 + x1) / 2, y_wall - (k + .5) * depth / boards, top - .03), (x1 - x0, depth / boards - .01, .06), variant('timber_light', .07))
    ye = y_wall - depth
    m.box(((x0 + x1) / 2, ye + .06, top - .1), (x1 - x0, .12, .12), 'timber')
    for x in np.linspace(x0 + .1, x1 - .1, 5): post(m, float(x), ye + .06, 0, top - .16, .11)
    m.collider(((x0 + x1) / 2, y_wall - depth / 2, top / 2), (x1 - x0, depth, top))
    return ye


# ----------------------------------------------------------------------------- the houses
def house_a(m):
    """Tiled single-storey house: irimoya roof, engawa with glass doors, gabled entrance porch."""
    w, d, fl, top = 10.0, 6.8, .55, 3.30
    door = HOUSES['A']['door_x']; ze, p = 2.78, .45
    m.box((0, 0, (fl + top) / 2), (w, d, top - fl), 'plaster')
    m.collider((0, 0, 2.2), (w, d, 4.4))
    front = [-5.0, -3.375, -1.75, -.125, 1.5, 5.0]

    def dress(side, L, posts):
        if side == 'front':
            for x0, x1 in zip(front[:4], front[1:5]):
                bw = (x1 - x0) / 2
                for k in range(2): glass_door(m, x0 + bw * (k + .5), bw - .02, fl, 1.78)
                m.bar(((x0 + x1) / 2, -.03, 2.6), (x1 - x0 - .16, .04, .36), 'shoji')          # transom
            koshi_window(m, 4.45, 1.75, .6, .9)
            return
        m.bar((0, -.01, (fl + 1.25) / 2), (L - .02, .04, 1.25 - fl), 'board')                  # wainscot
        for k in ((0, 2) if side == 'back' else (1, 3)): koshi_window(m, mid(posts, k), 1.8, 1.1 if side == 'back' else .9, .8)
    body_walls(m, w, d, fl, top, 2.35, lambda side, L: front if side == 'front' else bays(L, 4), dress)
    # engawa along the glass doors, the eave posts along its edge, a shoe stone, the shutter box at its end
    ye = engawa(m, -5.0, 1.45, -3.4, .92)
    for x in (-4.95, -1.75, 1.45): post(m, x, ye - .02, .0, 2.62, .14)
    m.box((-1.75, ye - .02, 2.56), (6.9, .16, .2), 'timber')
    step_stone(m, -2.6, ye - .27, .25, .9, .45)
    m.box((-4.72, -3.62, 1.4), (.5, .38, 1.7), 'board')
    # genkan: an open porch with plaster side walls, a stone floor, lattice sliding doors and its own gable
    py = -5.0
    m.box((door, -4.2, .07), (2.3, 1.7, .14), 'stone')
    for x in (door - 1.02, door + 1.02): post(m, x, py + .08, .14, 2.44, .15)
    m.box((door, py + .08, 2.36), (2.35, .16, .18), 'timber')
    for s in (-1, 1):
        m.box((door + s * 1.1, -4.2, 1.35), (.12, 1.6, 2.2), 'plaster')
        m.box((door + s * 1.1, -4.2, .6), (.14, 1.62, .9), 'board')
    with m.at((door, -3.4, 0)):
        for k in (-1, 1): lattice_door(m, k * .48, .96, .14, 2.05)
        m.bar((0, -.03, 2.3), (2.0, .04, .3), 'shoji')
    gable_y(m, door, 1.4, -3.3, py, 2.62, .55)
    step_stone(m, door, -5.25, .12, 1.3, .5)
    pots(m, door + 1.45, -5.0)
    m.collider((door, -4.2, 1.3), (2.3, 1.6, 2.6))
    # roof
    irimoya(m, 6.25, -4.75, 4.15, ze, p, 2.4, .45)
    eave_ends(m, (-6.0, -4.75), (door - 1.5, -4.75), ze, (0, -1), p)
    eave_ends(m, (-6.0, 4.15), (6.0, 4.15), ze, (0, 1), p)


def house_b(m):
    """Thatched farmhouse: steep hipped thatch, engawa with storm shutters and shoji, wide earth-floored entrance,
    woodpile lean-to."""
    w, d, fl, top = 11.0, 7.4, .50, 2.55
    door = HOUSES['B']['door_x']
    m.box((0, 0, (fl + top) / 2), (w, d, top - fl), 'plaster')
    m.box((0, 0, top + .6), (w - .2, d - .2, 1.2), 'soffit')                  # the loft, up under the thatch
    m.collider((0, 0, 2.0), (w, d, 4.0))

    def dress(side, L, posts):
        if side == 'front':
            bay = L / 6
            for k in range(4):                                                  # the engawa: shutters, then shoji
                for j in range(2): (amado if k < 2 else shoji)(m, posts[k] + bay / 4 + j * bay / 2, bay / 2 - .02, fl, 1.55)
                m.bar((mid(posts, k), -.03, 2.3), (bay - .16, .04, .3), 'plaster_shade')
            with m.at((door, 0, 0)):                                           # the doma door: wide planks
                m.bar((0, -.05, 1.0), (1.9, .05, 2.0), 'timber')
                for k in range(6): m.bar((-.8 + k * .32, -.08, 1.0), (.03, .03, 1.95), 'board')
                m.bar((0, -.09, 1.95), (2.1, .06, .12), 'timber_light')
            m.bar((door, -.02, .08), (2.3, .06, .16), 'stone')
            koshi_window(m, mid(posts, 5), 1.55, 1.0, .7)
            return
        for k in range(len(posts) - 1):
            m.bar((mid(posts, k), -.012, (fl + top) / 2 - .1), (posts[k + 1] - posts[k] - .18, .03, top - fl - .3), variant('board', .12))
        if side == 'left': koshi_window(m, mid(posts, 1), 1.7, 1.0, .7)
        if side == 'back': koshi_window(m, mid(posts, 4), 1.7, 1.2, .7)
    body_walls(m, w, d, fl, top, 2.1, lambda side, L: bays(L, 6 if L > 10 else 4), dress)
    ye = engawa(m, -5.5, 1.75, -3.7, .92)
    step_stone(m, -2.0, ye - .27, .25, .9, .45)
    m.box((-5.22, -3.95, 1.3), (.5, .4, 1.6), 'board')
    step_stone(m, door, -4.05, .12, 1.5, .6)
    pots(m, door - 1.6, -4.05)
    # thatch: a steep hip, thick at the eave, a tiled ridge cap with crossed ridge logs
    xe, yf, yb, ze, p, t = 6.9, -5.2, 5.2, 2.65, .85, .5
    yc = (yf + yb) / 2; zr = ze + (yc - yf) * p; xr = xe - (yc - yf)
    for pts, out in (([(-xe, yf, ze), (xe, yf, ze), (xr, yc, zr), (-xr, yc, zr)], (0, -1, 1)),
                     ([(xe, yb, ze), (-xe, yb, ze), (-xr, yc, zr), (xr, yc, zr)], (0, 1, 1)),
                     ([(xe, yf, ze), (xe, yb, ze), (xr, yc, zr)], (1, 0, 1)),
                     ([(-xe, yb, ze), (-xe, yf, ze), (-xr, yc, zr)], (-1, 0, 1))):
        m.poly(pts, 'thatch', out=out)
        m.poly([(x, y, z - t) for x, y, z in pts], 'soffit', out=(-out[0], -out[1], -1))
        # a darker, older band toward the ridge and a lighter trimmed band along the eave, standing proud
        for z0, z1, key in ((ze + (zr - ze) * .62, zr + 1, 'thatch_dark'), (ze - 1, ze + (zr - ze) * .16, 'thatch_light')):
            m.poly([(x + out[0] * .02, y + out[1] * .02, z + .02) for x, y, z in _band(pts, z0, z1)], variant(key, .04), out=out)
    ring = [(-xe, yf), (xe, yf), (xe, yb), (-xe, yb)]
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):                 # the thick cut edge, in two layers
        nx, ny = (y1 - y0), -(x1 - x0); ln = math.hypot(nx, ny); nx, ny = nx / ln, ny / ln
        if nx * (x0 + x1) + ny * (y0 + y1) < 0: nx, ny = -nx, -ny
        m.poly([(x0, y0, ze), (x1, y1, ze), (x1, y1, ze - t * .55), (x0, y0, ze - t * .55)], 'thatch_cut', out=(nx, ny, 0))
        m.poly([(x0 - nx * .06, y0 - ny * .06, ze - t * .55), (x1 - nx * .06, y1 - ny * .06, ze - t * .55),
                (x1 - nx * .06, y1 - ny * .06, ze - t), (x0 - nx * .06, y0 - ny * .06, ze - t)], 'thatch_dark', out=(nx, ny, 0))
    m.box((0, yc, zr + .12), (2 * xr + 1.2, .9, .40), 'tile_edge', .05)
    m.box((0, yc, zr + .38), (2 * xr + .9, .42, .20), 'tile_roll', .04)
    for x in np.linspace(-xr + .1, xr - .1, 4):
        for s in (-1, 1): m.beam((float(x), -s * .75, zr - .15), (float(x), s * .55, zr + .75), .10, .10, 'log')
    for s in (-1, 1): m.beam((s * (xr + .5), yc, zr + .2), (s * (xr + .9), yc, zr + .55), .16, .16, 'log')
    # lean-to over the woodpile on the +x side, under the thatch's eave
    lx0, lx1 = w / 2, 7.6
    for y in (-2.3, 2.3): post(m, lx1 - .1, y, 0, 1.72, .13)
    m.box((lx1 - .1, 0, 1.68), (.14, 4.9, .14), 'timber')
    tiled(m, [(lx0, -2.8, 2.0), (lx0, 2.8, 2.0), (lx1 + .3, 2.8, 1.70), (lx1 + .3, -2.8, 1.70)], (-1, 0),
          body='board', roll='timber_light', spacing=.42, r=.04, under=.08)
    for row in range(3):
        for k in range(8 - row):
            y = -1.75 + k * .47 + row * .235; z = .18 + row * .31
            m.log((lx0 + .1, y, z), (lx0 + 1.75 + R.uniform(-.08, .08), y, z), .16, variant('log', .15), variant('log_end', .1))
    m.collider(((lx0 + lx1) / 2, 0, 1.0), (lx1 - lx0, 4.8, 2.0))


def _band(pts, z0, z1):
    """The part of a planar polygon between heights z0 and z1."""
    def clip(poly, level, above):
        out = []
        for a, b in zip(poly, poly[1:] + poly[:1]):
            ina = a[2] >= level if above else a[2] <= level
            inb = b[2] >= level if above else b[2] <= level
            if ina: out.append(a)
            if ina != inb:
                s = (level - a[2]) / (b[2] - a[2]); out.append(tuple(a[i] + (b[i] - a[i]) * s for i in range(3)))
        return out
    return clip(clip(list(pts), z0, True), z1, False)


def house_c(m):
    """Two storeys: a pent roof round the ground floor, a gabled upper roof, a balcony, the genkan under a small gable."""
    w, d, fl, top = 9.2, 7.2, .45, 3.10
    uw, ud, uz, utop = 7.8, 5.8, 3.40, 6.0
    door = HOUSES['C']['door_x']
    m.box((0, 0, (fl + top) / 2), (w, d, top - fl), 'plaster')
    m.box((0, 0, (uz - .2 + utop) / 2), (uw, ud, utop - uz + .2), 'plaster')
    m.collider((0, 0, 1.8), (w, d, 3.6)); m.collider((0, 0, 4.7), (uw, ud, 2.6))
    front = [-4.6, -2.3, 0, 1.45, 3.35, 4.6]

    def dress(side, L, posts):
        if side == 'front':
            for x0, x1 in zip(front[:2], front[1:3]):
                bw = (x1 - x0) / 2
                for k in range(2): glass_door(m, x0 + bw * (k + .5), bw - .02, fl, 1.8)
            with m.at((door, 0, 0)):
                for k in (-1, 1): lattice_door(m, k * .43, .86, .12, 2.0)
            m.bar((door, -.02, .06), (1.9, .06, .12), 'stone')
            koshi_window(m, mid(front, 2), 1.8, .8, .8)
            koshi_window(m, mid(front, 4), 1.8, .6, .8)
            return
        m.bar((0, -.01, (fl + 1.2) / 2), (L - .02, .04, 1.2 - fl), 'board')
        for k in (0, 2): koshi_window(m, mid(posts, k), 1.8, 1.0, .8)
    body_walls(m, w, d, fl, top, 2.3, lambda side, L: front if side == 'front' else bays(L, 4), dress)
    # the upper storey: glass doors onto the balcony, windows round the rest
    for side in ('front', 'back', 'left', 'right'):
        L = uw if side in ('front', 'back') else ud
        posts = bays(L, 3)
        with wall(m, side, uw, ud):
            wall_frame(m, L, uz, utop, posts, 5.45)
            if side == 'front':
                for j in (-1, 1): glass_door(m, j * L / 12, L / 6 - .02, uz + .18, 1.8)
                for k in (0, 2): koshi_window(m, mid(posts, k), 4.6, 1.3, .9)
            elif side == 'back':
                for k in (0, 2): koshi_window(m, mid(posts, k), 4.7, 1.2, .8)
            else:
                koshi_window(m, mid(posts, 1), 4.7, 1.0, .8)
    pent(m, (-uw / 2, uw / 2, -ud / 2, ud / 2), (-5.6, 5.6, -4.6, 4.6), uz + .08, 2.82)
    # balcony over the pent roof, in front of the middle bay's glass doors
    by0, by1, bz, bx = -ud / 2, -ud / 2 - .95, uz + .18, 1.9
    m.box((0, (by0 + by1) / 2, bz - .04), (2 * bx, .95, .08), 'timber_light')
    for x in np.linspace(-bx + .05, bx - .05, 4):
        m.box((float(x), by1 + .04, bz + .45), (.08, .08, .9), 'timber')
        m.beam((float(x), by1 + .04, bz - .06), (float(x), by0 - .02, bz - .4), .07, .07, 'timber')
    for s in (-1, 1): m.box((s * (bx - .05), (by0 + by1) / 2, bz + .9), (.08, .95, .07), 'timber_light')
    m.box((0, by1 + .04, bz + .9), (2 * bx, .12, .07), 'timber_light')
    m.box((0, by1 + .04, bz + .12), (2 * bx, .07, .06), 'timber')
    for x in np.linspace(-bx + .15, bx - .15, 19): m.box((float(x), by1 + .04, bz + .5), (.035, .035, .7), 'timber_light')
    # the upper gable roof, its ridge along x
    xe, ye, ze, p = uw / 2 + .65, ud / 2 + .95, 5.62, .52
    zr = ze + ye * p
    for s in (-1, 1):
        tiled(m, [(-xe, s * ye, ze), (xe, s * ye, ze), (xe, 0, zr), (-xe, 0, zr)], (0, -s))
        fascia(m, (-xe, s * ye), (xe, s * ye), ze)
        eave_ends(m, (-xe + .3, s * ye), (xe - .3, s * ye), ze, (0, s), p)
        gz0 = zr - .16
        m.poly([(s * uw / 2, -ud / 2, utop - .02), (s * uw / 2, ud / 2, utop - .02), (s * uw / 2, 0, gz0)], 'plaster', out=(s, 0, 0))
        with m.at((s * uw / 2, 0, 0), 90 * s):
            m.bar((0, -.03, utop + .08), (ud, .06, .12), 'timber')
            m.bar((0, -.03, utop + .75), (ud * .5, .06, .10), 'timber')
            m.bar((0, -.03, (utop + gz0) / 2), (.12, .06, gz0 - utop), 'timber')
        for sy in (-1, 1): m.beam((s * (xe + .02), sy * ye, ze - .05), (s * (xe + .02), 0, zr - .05), .08, .26, 'timber')
        onigawara(m, s * (xe + .05), 0, zr, 0)
    ridge(m, (-xe, 0, zr), (xe, 0, zr), .34, .38)
    # the genkan's gable on the pent roof, its steps and pots
    gable_y(m, door, 1.0, -3.4, -4.6, 2.62, .6, .2)
    step_stone(m, door, -4.0, .12, 1.4, .6)
    step_stone(m, door, -4.75, .06, 1.0, .5)
    pots(m, door - 1.5, -4.0)


# ----------------------------------------------------------------------------- the lots
class Ground:
    """The final heightmap (world.json's grid)."""

    def __init__(self, world, h):
        self.h = h; self.n = world['n']; self.size = world['size']; self.step = self.size / (self.n - 1)

    def low(self, x, y):
        """The lowest corner of the cell under (x, y): the terrain never shows below it."""
        fx = (x + self.size / 2) / self.step; fy = (y + self.size / 2) / self.step
        i = int(np.clip(math.floor(fx), 0, self.n - 2)); j = int(np.clip(math.floor(fy), 0, self.n - 2))
        return float(self.h[j:j + 2, i:i + 2].min())


KERB, STEP_RISE, STEP_RUN = .45, .16, .36


def lot_mesh(lot, ground):
    m = Mesh(lot['name'], lot)
    spec = HOUSES[lot['variant']]; level = lot['level']
    F = np.array(lot['front'])                      # x, y, verge - level along the hedge line
    g0, g1 = lot['gate']; gx = (g0 + g1) / 2
    def yf(x): return float(front_y(lot, x))
    def low(lx, ly):
        wx, wy = to_world(lot, lx, ly); return ground.low(float(wx), float(wy)) - level

    # the lot top, from behind the kerb to the back edge (the terrain's ground)
    xs = sorted(set([float(v) for v in F[:, 0]] + [g0, g1]))
    for x0, x1 in zip(xs[:-1], xs[1:]):
        m.poly([(x0, yf(x0) + KERB, 0), (x1, yf(x1) + KERB, 0), (x1, BACK, 0), (x0, BACK, 0)], 'soil', slot=1, out=(0, 0, 1))
    # a gravel yard across the front, the moss garden bed with its edging stones, gravel drip lines under the eaves
    gcx, gcy = lot['garden']['centre']; grx, gry = lot['garden']['radii']; gs = 1 if gcx > 0 else -1
    hx0, hx1, hy0, hy1 = spec['walls']; rx0, rx1, ry0, ry1 = spec['roof']; yard_back = spec['ground'][2] + .1
    yard_x = np.linspace(*sorted([gcx - gs * (grx + .35), -gs * (HALF_W - .7)]), 9)
    for x0, x1 in zip(yard_x[:-1], yard_x[1:]):
        x0, x1 = float(x0), float(x1)
        m.poly([(x0, yf(x0) + KERB + .35, .015), (x1, yf(x1) + KERB + .35, .015), (x1, yard_back, .015), (x0, yard_back, .015)],
               variant('gravel', .025), out=(0, 0, 1))
    ring = [(gcx + grx * math.cos(a), gcy + gry * math.sin(a), .02) for a in np.linspace(0, math.tau, 17)[:-1]]
    m.poly(ring, 'moss', out=(0, 0, 1))
    for x, y, _ in ring[::2]:
        with m.at((x, y, 0), math.degrees(math.atan2(y - gcy, x - gcx)) + 90):
            m.box((0, 0, .04), (.55, .26, .16), variant('stone_light', .1), .04)
    for x0, x1, y0, y1 in ((rx0 + .2, rx1 - .2, hy1 + .05, min(ry1 - .15, BACK - .2)), (rx0 + .2, hx0 - .05, hy0, hy1 + .05),
                           (hx1 + .05, rx1 - .2, hy0, hy1 + .05)):
        if x1 - x0 > .2 and y1 - y0 > .2:
            m.poly([(x0, y0, .018), (x1, y0, .018), (x1, y1, .018), (x0, y1, .018)], variant('gravel', .04), out=(0, 0, 1))
    # stepping stones from the gate to the entrance step
    y, k = yf(gx) + KERB + .5, 0
    while y < DOOR_STEP[lot['variant']] - .45:
        with m.at((gx + (.14 if k % 2 else -.14), y, 0), R.uniform(-20, 20)):
            r = R.uniform(.40, .48)
            top = [(r * math.cos(a) * R.uniform(.85, 1.1), r * .8 * math.sin(a) * R.uniform(.85, 1.1)) for a in np.linspace(0, math.tau, 8)[:-1]]
            m.poly([(a, b, .07) for a, b in top], variant('stone', .1), out=(0, 0, 1))
            for (xa, ya), (xb, yb) in zip(top, top[1:] + top[:1]):
                m.poly([(xa, ya, .07), (xb, yb, .07), (xb, yb, -.05), (xa, ya, -.05)], 'stone_dark', out=(xa + xb, ya + yb, 0))
        y += .9; k += 1

    def pillow(q, out, bulge=.07, gap=.03, key='stone', amount=.16):
        """A rounded stone on a wall face: the quad q (corners in order) drawn in by `gap`, its middle pushed out."""
        Q = [np.array(p, float) for p in q]; c = sum(Q) / 4; o = np.array(out, float) / np.linalg.norm(out)
        Q = [p + (c - p) * min(.4, gap / max(np.linalg.norm(c - p), 1e-6)) + o * .015 for p in Q]
        top = c + o * bulge; col = variant(key, amount)
        for i in range(4): m.poly([Q[i], Q[(i + 1) % 4], top], col, out=o)

    # the stone kerb (rounded stones on a dark bed) and the clipped hedge on it, either side of the gate
    tops = {}
    for run in ([x for x in xs if x <= g0 + 1e-6], [x for x in xs if x >= g1 - 1e-6]):
        if len(run) < 2: continue
        dz = [float(np.interp(x, F[:, 0], F[:, 2])) for x in run]
        top = max(0, max(dz)) + .30
        for x in run: tops[x] = top
        for (xa, da), (xb, db) in zip(zip(run[:-1], dz[:-1]), zip(run[1:], dz[1:])):
            ya, yb = yf(xa), yf(xb)
            segs = max(1, int(round(math.hypot(xb - xa, yb - ya) / .55)))
            for s in range(segs):
                t0, t1 = s / segs, (s + 1) / segs
                x0, x1 = xa + (xb - xa) * t0, xa + (xb - xa) * t1; y0, y1 = ya + (yb - ya) * t0, ya + (yb - ya) * t1
                zb0, zb1 = min(da + (db - da) * t0, 0) - .3, min(da + (db - da) * t1, 0) - .3
                m.poly([(x0, y0, zb0), (x1, y1, zb1), (x1, y1, top), (x0, y0, top)], 'stone_dark', out=(0, -1, 0))
                course = (top + max(zb0, zb1)) / 2 + R.uniform(-.07, .07)
                split = R.uniform(.35, .65)
                xm, ym = x0 + (x1 - x0) * split, y0 + (y1 - y0) * split
                pillow([(x0, y0, max(zb0, -.1 + min(da, 0))), (x1, y1, max(zb1, -.1 + min(db, 0))), (x1, y1, course), (x0, y0, course)], (0, -1, 0))
                pillow([(x0, y0, course), (xm, ym, course), (xm, ym, top), (x0, y0, top)], (0, -1, 0))
                pillow([(xm, ym, course), (x1, y1, course), (x1, y1, top), (xm, ym, top)], (0, -1, 0))
                m.poly([(x0, y0, top), (x1, y1, top), (x1, y1 + KERB, top), (x0, y0 + KERB, top)], variant('stone_light', .08), out=(0, 0, 1))
                m.poly([(x0, y0 + KERB, top), (x1, y1 + KERB, top), (x1, y1 + KERB, -.05), (x0, y0 + KERB, -.05)], 'stone', out=(0, 1, 0))
        for x, cap in ((run[0], -1), (run[-1], 1)):
            if abs(x) > HALF_W - .01: continue           # a lot corner: the side wall closes it
            y0 = yf(x); base = min(0, float(np.interp(x, F[:, 0], F[:, 2]))) - .3
            m.poly([(x, y0, base), (x, y0 + KERB, base), (x, y0 + KERB, top), (x, y0, top)], 'stone', out=(cap, 0, 0))
        # hedge: a clipped, rounded profile swept along the kerb, its crown a little uneven
        shape = [(0, 0), (-.05, .30), (-.03, .50), (.05, .62), (.20, .67), (.36, .67), (.50, .62), (.58, .50), (.60, .30), (.55, 0)]
        rings = []
        for i, x in enumerate(run):
            end = i in (0, len(run) - 1)
            bump = 0 if end else R.uniform(-.035, .035); swell = 0 if end else R.uniform(-.025, .025)
            rings.append([(x, yf(x) + a - .05 + (swell * (1 if a < .25 else -1) if 0 < z < .6 else 0), top + z + (bump if z > .55 else 0))
                          for a, z in shape])
        for ra, rb in zip(rings[:-1], rings[1:]):
            for k in range(len(shape) - 1):
                (a0, z0), (a1, z1) = shape[k], shape[k + 1]
                up = (a1 - a0) / math.hypot(a1 - a0, z1 - z0)
                m.poly([ra[k], rb[k], rb[k + 1], ra[k + 1]], variant('hedge_light' if up > .6 else 'hedge', .06), out=(0, -(z1 - z0), (a1 - a0)))
        m.poly(rings[0], 'hedge', out=(-1, 0, 0)); m.poly(rings[-1], 'hedge', out=(1, 0, 0))
    # the gate: two square posts with caps, a threshold stone in the kerb and steps down to the verge
    dzg = lot['gate_verge']; yg = yf(gx)
    for x in (g0 - .12, g1 + .12):
        m.box((x, yf(x) + KERB / 2, .75), (.2, .2, 1.8), 'timber', .02)
        m.box((x, yf(x) + KERB / 2, 1.68), (.26, .26, .07), 'tile_edge', .02)
    m.box((gx, yg + KERB / 2, -.1), (g1 - g0 + .1, KERB + .1, .2), variant('stone_light', .05), .03)
    n = int(math.ceil(-dzg / STEP_RISE)) if dzg < -.02 else 0
    for k in range(1, n):
        zt = dzg * k / n
        m.box((gx, yg - STEP_RUN * (k - .5), (zt + dzg - .15) / 2), (g1 - g0 + .1, STEP_RUN + .02, zt - dzg + .15),
              variant('stone_light', .06), .04)

    # battered dry-stone walls down the sides and the back, to the ground of the final heightmap
    for (xa, ya), (xb, yb) in (((-HALF_W, yf(-HALF_W)), (-HALF_W, BACK)), ((-HALF_W, BACK), (HALF_W, BACK)),
                               ((HALF_W, BACK), (HALF_W, yf(HALF_W)))):
        length = math.hypot(xb - xa, yb - ya); dx, dy = (xb - xa) / length, (yb - ya) / length
        nx, ny = -dy, dx
        if nx * (xa + xb) + ny * (ya + yb) < 0: nx, ny = -nx, -ny          # outward
        cols = max(2, int(round(length / .85)))
        for c in range(cols):
            p0 = np.array([xa + (xb - xa) * c / cols, ya + (yb - ya) * c / cols])
            p1 = np.array([xa + (xb - xa) * (c + 1) / cols, ya + (yb - ya) * (c + 1) / cols])
            bottom = min(low(*(p0 + (nx * .5, ny * .5))), low(*(p1 + (nx * .5, ny * .5))), -.12) - .3
            courses = max(1, int(round(-bottom / .42)))
            def at(p, z, out=0.):     # a point on the face at height z (0: the lot level), leaning back as it rises
                k = -z * .16 + out
                return (float(p[0] + nx * k), float(p[1] + ny * k), z)
            m.poly([at(p0, bottom), at(p1, bottom), at(p1, 0), at(p0, 0)], 'stone_dark', out=(nx, ny, .1))
            for r_ in range(courses):
                z0 = bottom * (1 - r_ / courses); z1 = bottom * (1 - (r_ + 1) / courses)
                for f0, f1 in (((0, .55), (.55, 1.0)) if (c + r_) % 3 else ((0, 1.0),)):
                    a0 = p0 + (p1 - p0) * f0; a1 = p0 + (p1 - p0) * f1
                    pillow([at(a0, z0), at(a1, z0), at(a1, z1), at(a0, z1)], (nx, ny, 0), .08, .035)
            m.poly([at(p0, .03, .02), at(p1, .03, .02), at(p1, .03, -.3), at(p0, .03, -.3)], variant('stone_light', .08), out=(0, 0, 1))
            m.poly([at(p0, -.08, .03), at(p1, -.08, .03), at(p1, .03, .03), at(p0, .03, .03)], variant('stone_light', .08), out=(nx, ny, 0))
    for x in (-HALF_W, HALF_W):                    # the front corners: close the wall ends behind the kerb
        y0 = yf(x); s = 1 if x > 0 else -1
        bottom = min(low(x + s * .5, y0 + .5), -.12) - .3
        m.poly([(x, y0, bottom), (x, y0 + KERB, bottom), (x, y0 + KERB, tops.get(x, .3)), (x, y0, tops.get(x, .3))], 'stone', out=(s, 0, 0))
    return m


# ----------------------------------------------------------------------------- export
def materials():
    out = []
    for name in ('Village', 'Ground'):
        mat = bpy.data.materials.new(name); mat.use_nodes = True
        nodes = mat.node_tree.nodes; bsdf = nodes.get('Principled BSDF')
        if name == 'Village':
            vc = nodes.new('ShaderNodeVertexColor'); vc.layer_name = 'Color'
            mat.node_tree.links.new(vc.outputs['Color'], bsdf.inputs['Base Color'])
        elif (yori.TEXTURES / 'T_ground.jpg').exists():   # for looking at in Blender; Unreal uses MI_Ground
            tex = nodes.new('ShaderNodeTexImage'); tex.image = bpy.data.images.load(str(yori.TEXTURES / 'T_ground.jpg'))
            mat.node_tree.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
        bsdf.inputs['Roughness'].default_value = .92; bsdf.inputs['Specular IOR Level'].default_value = .1
        out.append(mat)
    return out


def export(m, mats, shade=None):
    obj = m.object(mats, shade); objs = [obj]
    for i, (c, s, rotation) in enumerate(m.colliders):
        bpy.ops.mesh.primitive_cube_add(size=1, location=c, rotation=rotation)
        ob = bpy.context.object; ob.name = f'UCX_{m.name}_{i:02d}'; ob.scale = s
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        objs.append(ob)
    bpy.ops.object.select_all(action='DESELECT')
    for ob in objs: ob.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.fbx(filepath=str(OUT / 'assets' / f'{m.name}.fbx'), use_selection=True, apply_unit_scale=True,
                             apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z', object_types={'MESH'},
                             mesh_smooth_type='FACE', bake_anim=False, use_custom_props=False)
    for ob in objs[1:]: bpy.data.objects.remove(ob, do_unlink=True)
    V = np.array(m.vertices)
    return obj, {'triangles': sum(len(f) - 2 for f in m.faces), 'vertices': len(m.vertices),
                 'materials': [mats[s].name for s in sorted(set(m.slots))], 'collision_boxes': len(m.colliders),
                 'min': V.min(0).round(3).tolist(), 'max': V.max(0).round(3).tolist()}


def house_shade(z):
    """Ground-contact darkening on the houses."""
    return .72 + .28 * smooth((z + .1) / 1.4)


def main():
    (OUT / 'assets').mkdir(parents=True, exist_ok=True)
    for old in (OUT / 'assets').glob('*.fbx'): old.unlink()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats = materials()
    world = json.loads((yori.OUT / 'world.json').read_text()); h = np.load(yori.OUT / 'heightmap.npy')
    lots = world['houses']['lots']; ground = Ground(world, h)
    manifest, objects = {}, {}
    for key, fn in (('A', house_a), ('B', house_b), ('C', house_c)):
        m = Mesh(f'House_{key}'); fn(m)
        objects[m.name], manifest[m.name] = export(m, mats, house_shade)
        manifest[m.name]['about'] = HOUSES[key]['about']
    for lot in lots:
        m = lot_mesh(lot, ground)
        objects[m.name], manifest[m.name] = export(m, mats)
        manifest[m.name].update(house=lot['house'], centre=lot['centre'], level=lot['level'], yaw=lot['yaw'])
    # a scene to look at: every house on its lot where the world puts them, the three templates below the world
    for lot in lots:
        house = objects[lot['house']].copy(); bpy.context.collection.objects.link(house)
        for ob in (objects[lot['name']], house):
            ob.location = (*lot['centre'], lot['level']); ob.rotation_euler.z = math.radians(lot['yaw'])
    for key in 'ABC': objects[f'House_{key}'].location.z = -1000
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'Houses.blend'))
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    identity = {'sources': {str(p.relative_to(yori.REGIONS)): sha(p) for p in (HERE / 'build.py', HERE / 'layout.py', yori.REGIONS / 'village' / 'build.py')},
                'world_sha256': sha(yori.OUT / 'world.json'), 'heightmap_sha256': sha(yori.OUT / 'heightmap.npy'),
                'exports': {p.name: sha(p) for p in sorted((OUT / 'assets').glob('*.fbx'))}}
    (OUT / 'build-identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    for name, e in manifest.items(): print(f"{name:12s} {e['triangles']:6d} triangles  {e['materials']}  {e['collision_boxes']} boxes")
    print('HOUSES BUILD COMPLETE', sum(e['triangles'] for e in manifest.values()), 'triangles', flush=True)


if __name__ == '__main__':
    main()
