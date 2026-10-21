"""Old-school passenger ferry, concept C (ferry_oldschool_c.jpg). Procedural Blender build.

blender --background --factory-startup --threads 3 -P games/yorimichi/assets/vehicles/ferry/build.py
Metres; +X is the bow, z is up and the waterline is z=0. Writes one FBX per mesh, ferry.blend and manifest.json
into build/yorimichi/ferry/. Every part is a closed solid with outward normals (checked before export).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402,F401
import json
import hashlib
from pathlib import Path
import math

import bpy
from mathutils import Matrix, Vector

import solid_mesh as SM  # noqa: E402  (world/, the shared closed-solid builder)
from solid_mesh import circle, offset_loop, rect, resample, rounded_rect, signed_area  # noqa: E402,F401

OUT = yori.OUT / 'ferry'

# ------------------------------------------------------------------ materials (sRGB, roughness, metallic)
WHITE, BLUE, GOLD, TIMBER, DECK = 'FY_WhitePaint', 'FY_BootTopBlue', 'FY_GoldMoulding', 'FY_VarnishedTimber', 'FY_DeckTimber'
CREAM, BLACK, BRASS, CANVAS, GLASS = 'FY_CreamFunnel', 'FY_Black', 'FY_Brass', 'FY_Canvas', 'FY_Glass'
IRON, BUOY, BOAT, ROPE = 'FY_DarkIron', 'FY_Lifebuoy', 'FY_BoatTimber', 'FY_TarredRope'
THROAT, ANCHOR, POCKET = 'FY_CowlThroat', 'FY_AnchorBronze', 'FY_HawseRecess'
BOAT2, GUNWALE, COVER = 'FY_BoatTimberDark', 'FY_BoatGunwale', 'FY_BoatCover'
MATERIALS = {
    WHITE: ((238, 232, 229), .55, 0.), BLUE: ((46, 84, 158), .5, 0.), GOLD: ((214, 168, 82), .4, .3),
    TIMBER: ((172, 112, 58), .45, 0.), DECK: ((196, 152, 104), .7, 0.), CREAM: ((240, 230, 208), .55, 0.),
    BLACK: ((40, 38, 42), .6, 0.), BRASS: ((206, 164, 78), .35, .55), CANVAS: ((228, 210, 176), .85, 0.),
    GLASS: ((66, 84, 112), .15, 0.), IRON: ((60, 60, 64), .5, .3), BUOY: ((232, 112, 50), .6, 0.),
    BOAT: ((170, 113, 66), .4, 0.), ROPE: ((66, 50, 38), .8, 0.), BOAT2: ((148, 97, 57), .4, 0.),
    GUNWALE: ((70, 44, 30), .4, 0.), COVER: ((236, 220, 196), .85, 0.),
    THROAT: ((118, 70, 36), .5, .35), ANCHOR: ((128, 98, 68), .45, .45), POCKET: ((46, 52, 70), .7, 0.),
}

# ------------------------------------------------------------------ hull lines (fitted to the concept camera)
STERN, STEM = -40.0, 40.0
BEAM = 5.6                    # half-beam of the parallel middle body
PAR_AFT, PAR_FWD = -20.0, 14.0
Z_BOTTOM = -2.6
ZL = 1.0                      # freeboard lift: the concept shows a deep blue boot-top above the water
BOOT = 1.6 + ZL               # top of the blue boot-top band
H1 = 3.9                      # main deck to boat deck
SLAB = 0.42


def clamp(v, a=0.0, b=1.0):
    return max(a, min(b, v))


def deck_z(x):
    """Main deck sheer: low aft, rising to a high raked bow."""
    if x < -8.0:
        return ZL + 5.6 - 0.7 * ((x + 8.0) / 32.0) ** 2
    return ZL + 5.6 + 3.0 * ((x + 8.0) / 48.0) ** 3


def boat_z(x):
    return deck_z(x) + H1


def rope_z(x):
    return deck_z(x) - 2.15 + 0.25 * clamp((x - 10.0) / 30.0)


def stem_x(z):
    top = deck_z(STEM)
    if z >= 0.0:
        return STEM - (top - z) * 0.5
    return STEM - top * 0.5 - (-z / -Z_BOTTOM) ** 1.5 * 5.0


def stern_x(z):
    top = deck_z(STERN)
    if z >= 0.0:
        return STERN + (top - z) * 0.3
    return STERN + top * 0.3 + (-z / -Z_BOTTOM) ** 1.4 * 6.0


def section(z):
    if z >= 0.6:
        return 1.0
    t = (0.6 - z) / (0.6 - Z_BOTTOM)
    return 0.5 + 0.5 * math.sqrt(max(0.0, 1 - t * t))


def half_width(x, z):
    w = BEAM * section(z)
    if x < PAR_AFT:
        u = clamp((x - PAR_AFT) / (stern_x(z) - PAR_AFT))
        w *= math.sqrt(max(0.0, 1 - u * u))
    elif x > PAR_FWD:
        u = clamp((x - PAR_FWD) / (stem_x(z) - PAR_FWD))
        p = 1.8 + 1.4 * clamp(z / deck_z(x))
        w *= 1 - u ** p
    return max(0.07, w)


def deck_half(x):
    return half_width(x, deck_z(x))


PLATE_DEPTH = 0.65                        # landing plate, inboard from the hull edge at a gate


def landing_plate(x, width):
    """(underside z, top z) of the brass landing plate at a gate: level on top, 3 cm above the highest deck under it,
    and 2 cm into the deck at its lowest point."""
    lo, hi = min(deck_z(x - width / 2), deck_z(x + width / 2)), max(deck_z(x - width / 2), deck_z(x + width / 2))
    return lo - 0.02, hi + 0.03


def gate_runs(edge):
    """Split a deck-edge polyline (sorted by x) where it crosses a boarding gate, ending exactly at the gate edges."""
    runs, run = [], []
    cuts = [(x - w / 2, x + w / 2) for x, w in GATES]
    inside = lambda x: any(a < x < b for a, b in cuts)
    for p, q in zip(edge, edge[1:] + [None]):
        if not inside(p[0]):
            run.append(p)
        if q is None:
            break
        for a, b in cuts:
            for c, entering in ((a, True), (b, False)):
                if min(p[0], q[0]) < c < max(p[0], q[0]):
                    t = (c - p[0]) / (q[0] - p[0]); cp = tuple(u + (v - u) * t for u, v in zip(p, q))
                    if entering == (q[0] > p[0]):
                        run.append(cp); runs.append(run); run = []
                    else:
                        run = [cp]
    if len(run) > 1:
        runs.append(run)
    return [r for r in runs if len(r) > 1]


def hull_normal(x, z, side=-1):
    """Outward plan normal of the hull side at (x, z); side -1 is starboard."""
    h = 0.05
    dw = (half_width(x + h, z) - half_width(x - h, z)) / (2 * h)
    n = Vector((-dw, side * 1.0, 0.0))
    return n.normalized()


# ------------------------------------------------------------------ layout
HW1 = 3.7                     # forward (timber) deckhouse half-width
HW_MID = 3.3                  # midship deckhouse half-width: a wider walk under the lifeboats
STEP = (13.2, 13.6)           # where the midship house widens into the forward house
T1_AFT, T1_FWD, T1_FRONT = -22.0, 27.0, 4.6
FRONT_P = 2.5                 # superellipse exponent of the rounded house fronts in plan
OVERHANG = 0.26               # boat-deck slab overhang beyond the tier-1 walls
WH_AFT, WH_FWD, WH_HW, WH_H, WH_FRONT = 14.2, 21.4, 2.7, 3.0, 2.2
FUNNEL_X = 2.0
CASING = (-1.6, 5.8, 2.25, 2.0)           # x0, x1, half-width, height
AFT_HOUSE = (-12.6, -9.8, 2.25, 2.45)
BOATS = [-12.35, 8.9]                     # lifeboat centres, both sides (fitted to the concept camera)
BOAT_Y = 4.62                                # just clear of the boat-deck edge; the boats stay inside the hull's beam
BOAT_L, BOAT_HB = 8.6, 0.84
BAY_PILLARS = [-17.0, -7.75, 4.4, 13.0]       # white pillars framing the lifeboat bays (clear of the bay windows)
FWD_HOUSE_X = 16.6                        # the varnished forward house starts here
MID_BAYS = [-19.4 + 3.4 * k for k in range(10)]
GATES = [(15.2, 2.2)]                     # boarding openings (centre x, width), both sides
FOREMAST_X, AFTMAST_X = 20.4, -20.9
CANOPY = (-38.6, -24.6, 9.5 + ZL)        # aft x, fwd x, roof underside z (stops short of the stair for headroom)
STAIR_Y = (-1.7, -0.7)                    # companionway from the stern deck up to the boat deck's aft edge
STAIR_TREAD, STAIR_MAX_RISE = 0.28, 0.25
BENCHES = [-36.5, -33.05, -29.65]         # 3 m stern-deck benches, backs to the rail, filling the bays between canopy posts


# ------------------------------------------------------------------ registries for the deck audit and collision
SEATS = []      # (label, x, y, base z, allowed embedding) for everything that stands on a deck
BOAT_FACES = []  # face ranges of the lifeboats themselves (for the clearance check)
BLOCKS = []     # collision boxes for fittings: (label, cx, cy, sx, sy, z0, z1, yaw degrees)


def seat(label, x, y, z, embed=0.06, probe=0.3):
    SEATS.append((label, round(x, 3), round(y, 3), round(z, 4), embed, probe))


def block(label, cx, cy, sx, sy, z0, z1, yaw=0.0):
    BLOCKS.append((label, cx, cy, sx, sy, z0, z1, yaw))


STERN_LOCKER_X = -38.1         # forward face of the stern seat-locker, flush with the aft ends of the stern benches


def stern_locker(inset):
    """Plan polygon and heights of the seat-locker that fills the stern tip, where the deck is too narrow to stand."""
    end = STERN + (0.06 if inset == 0 else 0.45)                  # the visible locker stops short of the stern rail
    xs = [STERN_LOCKER_X + (end - STERN_LOCKER_X) * k / 8 for k in range(9)]
    ys = [max(deck_half(x) - inset, 0.08) for x in xs]
    poly = [(x, -y) for x, y in zip(xs, ys)] + [(x, y) for x, y in reversed(list(zip(xs, ys)))]
    z0 = min(deck_z(x) for x in xs) - 0.03
    return poly, z0, deck_z(STERN_LOCKER_X) + 0.45


def stair_plan():
    """Companionway: equal risers <= STAIR_MAX_RISE, STAIR_TREAD treads, top nosing at the boat deck's aft edge."""
    xt = T1_AFT - OVERHANG; zt = boat_z(xt)
    for n in range(8, 40):
        xf = xt - (n - 1) * STAIR_TREAD; rise = (zt - deck_z(xf)) / n
        if rise <= STAIR_MAX_RISE:
            break
    zf = deck_z(xf)
    treads = [(xt - (n - k) * STAIR_TREAD, xt - (n - k - 1) * STAIR_TREAD, zf + k * rise) for k in range(1, n)]
    return {'risers': n, 'rise': rise, 'tread': STAIR_TREAD, 'foot_x': xf, 'foot_z': zf, 'top_x': xt, 'top_z': zt,
            'treads': treads, 'width': STAIR_Y[1] - STAIR_Y[0], 'angle_deg': math.degrees(math.atan2(rise, STAIR_TREAD))}


# ------------------------------------------------------------------ mesh core
def Mesh(name):
    """The shared closed-solid builder (world/solid_mesh.py), capping per-edge prisms in white paint."""
    return SM.Mesh(name, default_mat=WHITE)


def window(m, w, h, frame_mat, t=0.09, d=0.11, transom=True):
    """Framed window in the current wall frame, centred on the origin, glass set back inside the frame."""
    m.box((0, 0, 0.0), (w, h, 0.08), GLASS)
    m.box((-(w + t) / 2, 0, d / 2), (t, h + 2 * t, d), frame_mat)
    m.box(((w + t) / 2, 0, d / 2), (t, h + 2 * t, d), frame_mat)
    m.box((0, (h + t) / 2, d / 2), (w, t, d), frame_mat)
    m.box((0, -(h + t) / 2 - 0.02, d / 2 + 0.02), (w + 2 * t + 0.12, t + 0.04, d + 0.04), frame_mat)
    m.box((0, 0, d / 2 - 0.02), (t * 0.55, h, d - 0.04), frame_mat)
    if transom:
        m.box((0, h * 0.24, d / 2 - 0.02), (w, t * 0.55, d - 0.04), frame_mat)


def door(m, w, h, mat=TIMBER, frame_mat=WHITE):
    """Door panel standing on the wall-frame origin's y (bottom at y=0)."""
    m.box((0, h / 2, 0.05), (w, h, 0.1), mat, bevel=0.02)
    m.box((0, h * 0.72, 0.12), (w * 0.5, h * 0.25, 0.06), GLASS)
    m.box((-(w / 2 + 0.07), h / 2 + 0.035, 0.08), (0.14, h + 0.07, 0.16), frame_mat)
    m.box(((w / 2 + 0.07), h / 2 + 0.035, 0.08), (0.14, h + 0.07, 0.16), frame_mat)
    m.box((0, h + 0.07, 0.08), (w + 0.28, 0.14, 0.16), frame_mat)
    m.lathe((w * 0.32, h * 0.47, 0.1), [(0, 0.04), (0.08, 0.04), (0.12, 0)], BRASS, n=6)


def loop_points(outline, step):
    pts = resample(outline, step)
    return pts + [pts[0]]


# ------------------------------------------------------------------ hull
NCOL = 76
HULL_ROWS = [
    lambda x: Z_BOTTOM, lambda x: -1.9, lambda x: -0.8, lambda x: 0.4, lambda x: BOOT,
    lambda x: (BOOT + rope_z(x)) / 2, rope_z, lambda x: (rope_z(x) + deck_z(x)) / 2, lambda x: deck_z(x) - 0.14, deck_z,
]
BOOT_ROW = 4


def col_x(s, z):
    a, b = stern_x(z), stem_x(z)
    if s < 0.24:
        return a + (PAR_AFT - a) * (1 - math.cos(s / 0.24 * math.pi / 2))
    if s < 0.6:
        return PAR_AFT + (PAR_FWD - PAR_AFT) * (s - 0.24) / 0.36
    return PAR_FWD + (b - PAR_FWD) * math.sin((s - 0.6) / 0.4 * math.pi / 2)


def hull_point(s, row):
    z = 2.0
    for _ in range(6):
        x = col_x(s, z); z = row(x)
    x = col_x(s, z)
    return x, half_width(x, z), z


# Anchor pocket (hawse recess): outer lip corners (x, z) fitted to the painted rectangle through the concept camera.
POCKET_LIP = [(34.69, 5.50), (36.02, 5.70), (36.23, 3.94), (34.83, 3.66)]
POCKET_DEPTH = 0.3


def pocket_corners(inset=0.84):
    cx = sum(p[0] for p in POCKET_LIP) / 4; cz = sum(p[1] for p in POCKET_LIP) / 4
    return [(cx + (x - cx) * inset, cz + (z - cz) * inset) for x, z in POCKET_LIP], (cx, cz)


def skin_point(x, z, side):
    return Vector((x, side * half_width(x, z), z)), hull_normal(x, z, side)


def pocket_cutter(side):
    """A closed eight-cornered solid through the hull skin at the pocket: 0.6 m outside, POCKET_DEPTH inside."""
    opening, _ = pocket_corners()
    outer, inner = [], []
    for x, z in opening:
        p, n = skin_point(x, z, side)
        outer.append(tuple(p + n * 0.6)); inner.append(tuple(p - n * POCKET_DEPTH))
    verts = outer + inner
    faces = [[0, 1, 2, 3], [7, 6, 5, 4]] + [[k, 4 + k, 4 + (k + 1) % 4, (k + 1) % 4] for k in range(4)]
    vol = sum(Vector(verts[f[0]]).dot(Vector(verts[f[i]]).cross(Vector(verts[f[i + 1]]))) for f in faces for i in range(1, len(f) - 1))
    return verts, faces if vol > 0 else [f[::-1] for f in faces]


def cut_solid(verts, faces, mats, cutters, cut_mat):
    """Boolean-difference closed cutters out of a closed shell (exact solver); cut faces take cut_mat."""
    names = list(dict.fromkeys(mats))
    me = bpy.data.meshes.new('cut_shell'); me.from_pydata(verts, [], [list(f) for f in faces]); me.update()
    for n in names:
        me.materials.append(bpy.data.materials[n])
    me.polygons.foreach_set('material_index', [names.index(n) for n in mats]); me.update()
    ob = bpy.data.objects.new('cut_shell', me); bpy.context.scene.collection.objects.link(ob)
    temps = []
    for k, (cv, cf) in enumerate(cutters):
        cm = bpy.data.meshes.new(f'cutter{k}'); cm.from_pydata(cv, [], cf); cm.update(); cm.materials.append(bpy.data.materials[cut_mat])
        co = bpy.data.objects.new(f'cutter{k}', cm); bpy.context.scene.collection.objects.link(co); co.hide_render = True
        mod = ob.modifiers.new(f'cut{k}', 'BOOLEAN'); mod.operation = 'DIFFERENCE'; mod.solver = 'EXACT'; mod.object = co
        try:
            mod.material_mode = 'TRANSFER'
        except (AttributeError, TypeError):
            pass
        temps.append((co, cm))
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get()); res = bpy.data.meshes.new_from_object(ev)
    out_v = [tuple(v.co) for v in res.vertices]; out_f = [tuple(p.vertices) for p in res.polygons]
    out_m = [res.materials[p.material_index].name for p in res.polygons]
    for co, cm in temps:
        bpy.data.objects.remove(co); bpy.data.meshes.remove(cm)
    bpy.data.objects.remove(ob); bpy.data.meshes.remove(me); bpy.data.meshes.remove(res)
    return out_v, out_f, out_m


def anchor_pocket(m, side):
    """White lip round the recess and a stockless anchor seated in it, both following the bow's curve."""
    opening, (cx, cz) = pocket_corners()
    mid = [((xo + xl) / 2, (zo + zl) / 2) for (xo, zo), (xl, zl) in zip(opening, POCKET_LIP)]
    for k in range(4):
        a, b = mid[k], mid[(k + 1) % 4]
        for j in range(4):
            t0, t1 = j / 4, (j + 1) / 4
            pa, na = skin_point(a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0, side)
            pb, nb = skin_point(a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1, side)
            n = (na + nb).normalized(); A = (pb - pa).normalized(); L = (pb - pa).length
            e0 = 0.08 if j == 0 else 0.0; e1 = 0.08 if j == 3 else 0.01
            with m.frame(pa + n * 0.015 - A * e0, n.cross(A).normalized(), n, A):
                m.prism(rect(-0.085, -0.05, 0.085, 0.05), 0.0, L + e0 + e1, WHITE)
    p, n = skin_point(cx, cz, side)
    up = Vector((0, 0, 1)); A = n; U = up.cross(A).normalized(); V = A.cross(U)
    with m.frame(p - n * (POCKET_DEPTH - 0.12), U, V, A), m._push(Matrix.Scale(1.15, 4)):
        m.box((0, 0.02, 0), (0.15, 1.05, 0.1), ANCHOR, bevel=0.02)
        m.box((0, -0.53, 0), (0.42, 0.16, 0.12), ANCHOR, bevel=0.03)
        for sx in (-1, 1):
            m.beam((sx * 0.14, -0.55, 0), (sx * 0.36, -0.2, 0), 0.13, 0.1, ANCHOR)
            m.prism([(sx * 0.27, -0.4), (sx * 0.47, -0.16), (sx * 0.33, -0.06)] if sx > 0 else [(sx * 0.27, -0.4), (sx * 0.33, -0.06), (sx * 0.47, -0.16)], -0.05, 0.05, ANCHOR)
        m.box((0, 0.5, 0), (0.24, 0.08, 0.12), ANCHOR)
        m.torus((0, 0.65, 0), 0.11, 0.032, ANCHOR, n=12, m=5)
        with m.frame((0, 0.85, 0.0), Vector((0, 0, 1)), Vector((0, 1, 0)), Vector((-1, 0, 0))):
            m.torus((0, 0, 0), 0.09, 0.028, ANCHOR, n=10, m=5)


def hull(m):
    cols = [i / NCOL for i in range(NCOL + 1)]
    grid = [[hull_point(s, row) for row in HULL_ROWS] for s in cols]
    R = len(HULL_ROWS); C = len(cols)
    verts = []
    for side in (-1, 1):
        for i in range(C):
            for j in range(R):
                x, w, z = grid[i][j]; verts.append((x, side * w, z))
    S = lambda i, j: i * R + j
    P = lambda i, j: C * R + i * R + j
    faces = []; mats = []
    band = lambda j: BLUE if j < BOOT_ROW else WHITE
    for i in range(C - 1):
        for j in range(R - 1):
            faces.append([S(i, j), S(i + 1, j), S(i + 1, j + 1), S(i, j + 1)]); mats.append(band(j))
            faces.append([P(i, j), P(i, j + 1), P(i + 1, j + 1), P(i + 1, j)]); mats.append(band(j))
        t = R - 1
        faces.append([S(i, t), S(i + 1, t), P(i + 1, t), P(i, t)]); mats.append(DECK)
        faces.append([S(i, 0), P(i, 0), P(i + 1, 0), S(i + 1, 0)]); mats.append(BLUE)
    for j in range(R - 1):
        faces.append([S(0, j), S(0, j + 1), P(0, j + 1), P(0, j)]); mats.append(band(j))
        faces.append([S(C - 1, j), P(C - 1, j), P(C - 1, j + 1), S(C - 1, j + 1)]); mats.append(band(j))
    verts, faces, mats = cut_solid(verts, faces, mats, [pocket_cutter(s) for s in (-1, 1)], POCKET)
    m.part(verts, faces, mats)

    # Rounded covering board along the deck edge, both sides. It stops at the boarding gates, where the landing plate
    # runs out to the hull edge, so a brow's lip lies flat on the plate.
    for side in (-1, 1):
        edge = [(x, side * max(0.0, w - 0.05), z + 0.03) for x, w, z in (g[R - 1] for g in grid)]
        for run in gate_runs(edge):
            m.tube(run, 0.1, WHITE, n=6)

    # Gold rope moulding: one twisted rope from bow to bow around the stern.
    rope = [g[6] for g in grid]
    end = max(i for i, (x, w, z) in enumerate(rope) if x < stem_x(z) - 0.55)
    loop = [(x, -w, z) for x, w, z in rope[end::-1]] + [(x, w, z) for x, w, z in rope[1:end + 1]]
    loop = resample(loop, 0.4, closed=False)
    path = []
    for i, p in enumerate(loop):
        a, b = Vector(loop[max(0, i - 1)]), Vector(loop[min(len(loop) - 1, i + 1)])
        t = (b - a); t.z = 0; t.normalize()
        nrm = Vector((-t.y, t.x, 0))
        path.append(tuple(Vector(p) + nrm * 0.07))
    m.tube(path, 0.15, GOLD, n=8, star=0.9, twist=0.35)
    for side in (-1, 1):
        x = loop[0][0] + 0.2; z = rope_z(x); w = half_width(x, z)
        n = hull_normal(x, z, side)
        with m.wall((x, side * w, z), n):
            m.lathe((0, 0, -0.08), [(0, 0.46), (0.14, 0.46), (0.2, 0.36), (0.26, 0.22), (0.28, 0)], BRASS, n=12)
            m.torus((0, 0, 0.16), 0.36, 0.06, BRASS, n=12, m=5)

    # Portholes: rounded rectangles aft, round forward.
    rects = [-37.2, -34.7, -32.2, -29.7, -27.2, -24.7, -22.2, -19.7, -17.2, -14.7, -12.2, -9.7]
    rounds = [-6.4, -3.5, -0.6, 2.3, 5.2, 8.0, 10.8, 13.5, 16.2, 19.0, 22.0, 25.2, 28.8, 32.6]
    for side in (-1, 1):
        for x in rects + rounds:
            z = (deck_z(x) + rope_z(x)) / 2 - 0.05
            w = half_width(x, z); n = hull_normal(x, z, side)
            with m.wall((x, side * w, z), n):
                if x in rects:
                    o = rounded_rect(0.42, 0.66, 0.16)
                    m.prism(o, -0.12, 0.03, GLASS)
                    m.ring_prism(offset_loop(o, 0.1), offset_loop(o, -0.02), -0.06, 0.08, WHITE)
                else:
                    m.prism(circle(0.31, 12), -0.12, 0.03, GLASS)
                    m.ring_prism(circle(0.42, 12), circle(0.29, 12), -0.06, 0.08, WHITE)
        anchor_pocket(m, side)

    # Boarding openings: brass landing plates at the gates in the main-deck rail, out to the hull edge. The top is level
    # (a brow lip rests on it) and the underside follows the sheer down, so no edge floats.
    for x, width in GATES:
        for side in (-1, 1):
            w = deck_half(x); z0, z1 = landing_plate(x, width)
            m.box((x, side * (w - PLATE_DEPTH / 2), (z0 + z1) / 2), (width, PLATE_DEPTH, z1 - z0), BRASS)
            for xx in (x - width / 2, x, x + width / 2):          # the underside is buried deepest at the high end
                seat('landing plate', xx, side * (w - PLATE_DEPTH / 2), z0, embed=z1 - z0)


# ------------------------------------------------------------------ superstructure
def superellipse_front(xc, rx, hw, n, p=FRONT_P):
    """Rounded front in plan from (xc, -hw) round the bow-facing end to (xc, hw), endpoints excluded."""
    out = []
    for k in range(1, n):
        a = -math.pi / 2 + math.pi * k / n; c, s = math.cos(a), math.sin(a)
        out.append((xc + rx * abs(c) ** (2 / p), hw * math.copysign(abs(s) ** (2 / p), s)))
    return out


def t1_half(x):
    """Half-width of the tier-1 deckhouse walls at x (midship house, then the wider forward house)."""
    return HW_MID + (HW1 - HW_MID) * clamp((x - STEP[0]) / (STEP[1] - STEP[0]))


def t1_outline(grow=0.0, n=28):
    hm, hf = HW_MID + grow, HW1 + grow; xa = T1_AFT - grow; xc = T1_FWD - T1_FRONT; rx = T1_FRONT + grow
    s0, s1 = STEP[0] - grow * 0.4, STEP[1] - grow * 0.4
    starboard = [(xa, -hm), (s0, -hm), (s1, -hf), (xc, -hf)]
    port = [(x, -y) for x, y in reversed(starboard)]
    return starboard + superellipse_front(xc, rx, hf, n) + port


def slab_outline():
    """Boat deck: the tier-1 roof with a narrow white overhang that follows the rounded front."""
    return t1_outline(OVERHANG)


def slab_half(x):
    return t1_half(x) + OVERHANG


def wh_outline(grow=0.0, n=16):
    """Wheelhouse: shorter and narrower than the house below, set well back, with a rounded front."""
    hw = WH_HW + grow; xa = WH_AFT - grow; xc = WH_FWD - WH_FRONT; rx = WH_FRONT + grow
    return [(xa, -hw), (xc, -hw)] + superellipse_front(xc, rx, hw, n, p=2.8) + [(xc, hw), (xa, hw)]


def outline_walk(outline, step, corner=35.0, clear=0.5):
    """Evenly spaced points along a CCW outline, with outward normals, kept clear of sharp corners."""
    pts = [Vector(p) for p in outline]; n = len(pts); sharp = []
    for i in range(n):
        e1, e2 = pts[i] - pts[i - 1], pts[(i + 1) % n] - pts[i]
        if e1.length > 1e-6 and e2.length > 1e-6 and math.degrees(e1.angle(e2)) > corner:
            sharp.append(pts[i])
    segs = []; total = 0.0
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]; L = (b - a).length
        if L > 1e-6:
            segs.append((a, b, L, total)); total += L
    out = []; s = step / 2
    while s < total:
        for a, b, L, s0 in segs:
            if s0 <= s < s0 + L:
                p = a.lerp(b, (s - s0) / L); e = (b - a) / L
                if all((p - c).length > clear for c in sharp):
                    out.append((p.x, p.y, e.y, -e.x))
                break
        s += step
    return out


def superstructure(m):
    sheer0 = lambda x, y: deck_z(x) - 0.3
    t1_top = lambda x, y: boat_z(x) - SLAB + 0.02
    wall_mat = lambda x, y: TIMBER if x > FWD_HOUSE_X else WHITE
    m.loft_prism(t1_outline(), sheer0, t1_top, wall_mat, top=WHITE, bottom=WHITE, bevel=0.08)
    # Boat deck: a thick white slab whose fascia follows the rounded front.
    m.loft_prism(slab_outline(), lambda x, y: boat_z(x) - SLAB, lambda x, y: boat_z(x), WHITE, top=DECK, bottom=WHITE, bevel=0.1)

    # Midship house: white walls; each bay is a raised white portal round a varnished panel with two big
    # white-framed windows, and white pilasters stand between the bays.
    wall_h = H1 - SLAB + 0.3
    for side in (-1, 1):
        with m.mirrored(side > 0):
            for k, x in enumerate(MID_BAYS):
                z0 = deck_z(x) - 0.3
                with m.wall((x, -HW_MID, z0), (0, -1)):
                    pw, ph, f = 2.5, 2.95, 0.22
                    m.box((0, 0.3 + ph / 2, 0.025), (pw - 2 * f + 0.02, ph - f, 0.05), TIMBER)
                    m.box((-(pw - f) / 2, 0.3 + ph / 2, 0.08), (f, ph, 0.16), WHITE, bevel=0.03)
                    m.box(((pw - f) / 2, 0.3 + ph / 2, 0.08), (f, ph, 0.16), WHITE, bevel=0.03)
                    m.box((0, 0.3 + ph - f / 2, 0.09), (pw + 0.08, f, 0.18), WHITE, bevel=0.03)
                    m.box((0, 0.36, 0.09), (pw + 0.08, 0.14, 0.18), WHITE, bevel=0.03)
                    for u in (-0.5, 0.5):
                        m.box((u, 0.95, 0.07), (0.7, 0.72, 0.04), TIMBER, bevel=0.02)
                        with m.at((u, 2.1, 0.06)):
                            window(m, 0.62, 1.4, TIMBER, t=0.09, d=0.1)
                    if k < len(MID_BAYS) - 1:
                        m.box(((MID_BAYS[k + 1] - x) / 2, wall_h / 2, 0.05), (0.42, wall_h - 0.1, 0.1), WHITE, bevel=0.03)
            # Boarding door in its white portal, facing the gate.
            x = GATES[0][0]; z0 = deck_z(x)
            with m.wall((x, -HW1, z0), (0, -1)):
                m.box((0, 1.5, 0.12), (2.2, 3.0, 0.26), WHITE, bevel=0.04)
                with m.at((0, 0.02, 0.24)):
                    door(m, 1.05, 2.2, TIMBER, WHITE)
            # White pillars framing each lifeboat bay: from the main deck up under the boat deck's edge.
            for x in BAY_PILLARS:   # top fills the slab's chamfered lower edge; outer face flush with its fascia
                yo = t1_half(x) + OVERHANG
                m.prism(rect(x - 0.18, -yo, x + 0.18, -(HW_MID - 0.04)), lambda x_, y_: deck_z(x_) - 0.05,
                        lambda x_, y_: boat_z(x_) - SLAB + 0.1, WHITE)
                seat('bay pillar', x, side * (yo - 0.05), deck_z(x) - 0.05)   # outboard of the bay portals' frames
                block('bay pillar', x, side * (HW_MID - 0.04 + yo) / 2, 0.36, yo - HW_MID + 0.04, deck_z(x), boat_z(x) - SLAB)
            # White pilaster where the forward timber house begins.
            x = FWD_HOUSE_X
            m.box((x, -HW1 - 0.06, deck_z(x) - 0.3 + wall_h / 2), (0.5, 0.2, wall_h), WHITE, bevel=0.04)
    # Forward timber house: a continuous band of tall framed windows wrapping round the rounded front, varnished
    # pilasters between them, an oval window on each side.
    for x, y, nx, ny in outline_walk(t1_outline(), 1.22, corner=60.0, clear=0.3):
        if x < FWD_HOUSE_X + 0.75:
            continue
        z0 = deck_z(x) - 0.3
        with m.wall((x, y, z0), (nx, ny)):
            m.box((0, 0.95, 0.04), (0.92, 0.72, 0.05), TIMBER, bevel=0.02)
            m.box((0.61, wall_h / 2 + 0.1, 0.05), (0.2, wall_h - 0.4, 0.1), TIMBER, bevel=0.02)
            if abs(x - 19.2) < 0.61 and abs(ny) > 0.9:
                with m.at((0, 2.25, 0)), m._push(Matrix.Diagonal((0.8, 1.0, 1.0, 1.0))):
                    m.prism(circle(0.62, 16), -0.02, 0.07, GLASS)
                    m.ring_prism(circle(0.76, 16), circle(0.6, 16), 0.0, 0.14, TIMBER)
            else:
                with m.at((0, 2.28, 0.03)):
                    window(m, 0.84, 1.78, TIMBER, transom=False)

    # Tier 2: a shorter, narrower, set-back wheelhouse with a rounded front and a band of tall windows, under a white
    # roof slab whose railed top is the monkey island.
    m.loft_prism(wh_outline(), lambda x, y: boat_z(x) - 0.12, lambda x, y: boat_z(x) + WH_H, TIMBER, top=WHITE, bevel=0.07)
    m.loft_prism(wh_outline(0.3), lambda x, y: boat_z(x) + WH_H - 0.04, lambda x, y: boat_z(x) + WH_H + 0.3, WHITE, top=DECK, bevel=0.08)
    for x, y, nx, ny in outline_walk(wh_outline(), 1.0, corner=60.0, clear=0.3):
        if nx < -0.9:
            continue
        z0 = boat_z(x)
        with m.wall((x, y, z0), (nx, ny)):
            m.box((0, 0.5, 0.03), (0.78, 0.62, 0.05), TIMBER, bevel=0.02)
            m.box((0.5, WH_H / 2, 0.05), (0.16, WH_H - 0.2, 0.1), TIMBER, bevel=0.02)
            with m.at((0, 1.0 + 0.78, 0.03)):
                window(m, 0.7, 1.5, TIMBER, transom=False)
    with m.wall((WH_AFT, 0, boat_z(WH_AFT)), (-1, 0)):
        door(m, 0.95, 2.15, TIMBER, TIMBER)
    # Funnel casing and the aft timber house.
    x0, x1, hw, h = CASING
    m.loft_prism(rect(x0, -hw, x1, hw), lambda x, y: boat_z(x) - 0.1, lambda x, y: boat_z(x) + h, WHITE, bevel=0.1)
    for side in (-1, 1):
        with m.mirrored(side > 0):
            for x in (x0 + 1.4, x1 - 3.0):
                with m.wall((x, -hw, boat_z(x)), (0, -1)):
                    door(m, 0.85, 1.75, TIMBER, WHITE)
    x0, x1, hw, h = AFT_HOUSE
    m.loft_prism(rect(x0, -hw, x1, hw), lambda x, y: boat_z(x) - 0.1, lambda x, y: boat_z(x) + h, TIMBER, top=WHITE, bevel=0.07)
    m.loft_prism(rect(x0 - 0.25, -hw - 0.25, x1 + 0.25, hw + 0.25), lambda x, y: boat_z(x) + h - 0.04, lambda x, y: boat_z(x) + h + 0.22, WHITE, top=DECK, bevel=0.05)
    for x, y, nx, ny in outline_walk(rect(x0, -hw, x1, hw), 1.1):
        with m.wall((x, y, boat_z(x)), (nx, ny)):
            with m.at((0, 1.0 + 0.6, 0.03)):
                window(m, 0.62, 1.2, TIMBER, t=0.08)

    # Stern canopy over the open aft deck: canvas roof with a valance, brass posts.
    xa, xf, zc = CANOPY
    xs = [xa + (xf - xa) * k / 10 for k in range(11)]
    outline = [(x, -(deck_half(x) - 0.55)) for x in xs] + [(x, deck_half(x) - 0.55) for x in reversed(xs)]
    m.prism(outline, zc, zc + 0.16, CANVAS, bevel=0.04)
    m.prism(offset_loop(outline, -0.4), zc + 0.12, zc + 0.3, CANVAS, bevel=0.06)
    m.ring_prism(offset_loop(outline, 0.04), offset_loop(outline, -0.03), zc - 0.28, zc + 0.02, CANVAS)

    # Companionway stair from the stern deck up to the boat deck's aft edge, running fore-and-aft so it reads from
    # the side: solid white flights (no daylight) under varnished tread boards with nosings, and white stringers
    # whose tops run along the inner corners of the steps, so the stepped profile shows above them. Railed both sides.
    st = stair_plan(); y0, y1 = STAIR_Y
    for x0, x1, zk in st['treads']:
        m.prism(rect(x0 - 0.03, y0, x1, y1), lambda x, y: deck_z(x) - 0.05, zk, WHITE, top=DECK)
        m.prism(rect(x0 - 0.06, y0 - 0.02, x1, y1 + 0.02), zk - 0.05, zk + 0.01, TIMBER, top=DECK)
    drop = st['rise'] + 0.02 + 0.18 / math.cos(math.radians(st['angle_deg']))   # stringer centre below the nosing line
    for y in (y0 - 0.07, y1 + 0.07):
        xf, zf = st['foot_x'], st['foot_z']
        m.beam((xf - 0.3, y, zf + st['rise'] - drop - 0.3 * math.tan(math.radians(st['angle_deg']))), (st['top_x'] + 0.25, y, st['top_z'] - drop + 0.25 * math.tan(math.radians(st['angle_deg']))),
               0.1, 0.36, WHITE)                                  # runs on into the filler under the deck edge
    # White panel closing the slot between the top of the flight and the deckhouse's aft wall, under the overhang.
    m.prism(rect(st['top_x'] - 0.02, y0 - 0.1, T1_AFT + 0.05, y1 + 0.1), lambda x, y: deck_z(x) - 0.05, lambda x, y: boat_z(x) - SLAB + 0.02, WHITE)
    seat('stair foot', st['foot_x'] + 0.1, (y0 + y1) / 2, deck_z(st['foot_x'] + 0.1), embed=0.06, probe=0.1)
    # Climb-only ladder up the wheelhouse's aft face to the monkey island: rungs facing aft, side rails running up
    # through the roof rail's gate to grab height.
    zb2 = boat_z(WH_AFT)
    lx = WH_AFT - 0.46                    # clear of the roof slab's overhang
    for y in (1.25, 1.85):
        m.box((lx, y, zb2 + (WH_H + 1.3) / 2), (0.07, 0.07, WH_H + 1.3), WHITE)
        m.box(((lx + WH_AFT) / 2, y, zb2 + WH_H - 0.4), (WH_AFT - lx + 0.02, 0.06, 0.06), WHITE)
        seat('ladder foot', lx, y, zb2, probe=0.2)
    for k in range(10):
        m.box((lx, 1.55, zb2 + 0.3 + k * 0.3), (0.06, 0.6, 0.05), BRASS)
    block('ladder', (lx - 0.12 + WH_AFT) / 2, 1.55, WH_AFT - lx + 0.12, 0.75, zb2, zb2 + WH_H + 1.3)   # fills the gap behind the ladder


# ------------------------------------------------------------------ funnel
def funnel(m):
    """Fat, faceted, slightly raked oval funnel: a cream barrel tapering to a black top band, and a smaller black
    inner stack standing above the band, as painted."""
    x = FUNNEL_X; base = boat_z(x) + CASING[3] - 0.25
    top = 18.6 + ZL; black = 16.4 + ZL; rake = -0.5
    def centre(z):
        return x + rake * (z - base) / (top - base)
    inner_top = top + 0.75
    prof = [(base, 1.0, CREAM), (base + 1.2, 0.975, CREAM), (black, 0.89, CREAM), (black, 0.91, BLACK), (top, 0.89, BLACK),
            (top, 0.66, BLACK), (inner_top, 0.64, BLACK), (inner_top, 0.5, BLACK)]
    n = 12; a, b = 2.75, 2.2; verts = []; rings = []
    for z, s, _ in prof:
        rings.append(list(range(len(verts), len(verts) + n)))
        verts += [(centre(z) + a * s * math.cos(2 * math.pi * (k + 0.5) / n), b * s * math.sin(2 * math.pi * (k + 0.5) / n), z) for k in range(n)]
    bottom = rings[-1]; cz = inner_top - 0.5
    inner = list(range(len(verts), len(verts) + n))
    verts += [(centre(cz) + a * 0.5 * math.cos(2 * math.pi * (k + 0.5) / n), b * 0.5 * math.sin(2 * math.pi * (k + 0.5) / n), cz) for k in range(n)]
    faces = []; fm = []
    for i in range(len(rings) - 1):
        r0, r1 = rings[i], rings[i + 1]
        for k in range(n):
            j = (k + 1) % n
            faces.append([r0[k], r0[j], r1[j], r1[k]]); fm.append(prof[i + 1][2] if prof[i][2] != prof[i + 1][2] else prof[i][2])
    for k in range(n):
        j = (k + 1) % n
        faces.append([bottom[k], bottom[j], inner[j], inner[k]]); fm.append(BLACK)
    faces.append(list(reversed(rings[0]))); fm.append(CREAM)
    faces.append(list(inner)); fm.append(BLACK)
    m.part(verts, faces, fm)
    # Steam whistle and pipe on the funnel's front.
    fz = 15.4 + ZL; fx = centre(fz) + a * 0.92
    m.lathe((fx + 0.25, 0, fz), [(0, 0.12), (0.7, 0.12), (0.75, 0.2), (1.0, 0.2), (1.1, 0)], BRASS, n=8)
    m.beam((fx - 0.05, 0, fz + 0.2), (fx + 0.25, 0, fz + 0.2), 0.12, 0.12, BRASS)
    m.lathe((fx + 0.25, 0, base), [(0, 0.09), (fz - base, 0.09)], CREAM, n=6)


# ------------------------------------------------------------------ lifeboats and davits
BOAT_D, BOAT_SHEER = 1.35, 0.4           # depth amidships; rise of the gunwale at the ends
BOAT_RAISE = 0.2                         # keel 1.55 m below the boat deck: >= 2.05 m headroom over the main-deck walk


def boat_half(t):
    return max(0.04, BOAT_HB * (1 - abs(t) ** 1.9) ** 0.8)       # fine, pointed double-ended plan


def boat_gunwale(t):
    return BOAT_D + BOAT_SHEER * abs(t) ** 2.4                  # flat amidships, rising to both ends


def boat_keel(t):
    """Keel line: flat amidships, sweeping up in a round forefoot to high stems (a canoe profile, no plumb ends)."""
    return 1.2 * (1 - math.sqrt(max(0.0, 1 - abs(t) ** 4)))


def cover_half(t):
    return boat_half(t) + 0.12                                  # skirt clears the gunwale's rubbing strake


def skirt_z(x, g):
    s = x / 0.85 - round(x / 0.85)                              # lashings every 0.85 m pull the skirt down
    return g - 0.19 + 0.06 * math.sin(math.pi * s) ** 2


def lifeboat(m, L=BOAT_L):
    """Clinker-built double-ended boat, keel at z=0: seven varnished strakes in two tones so the laps read, a dark
    gunwale cap, and a cream canvas cover tented over a ridge line with its skirt draped below the gunwale."""
    stations = 25; NS = 7
    rings = []
    for i in range(stations):
        t = -1 + 2 * i / (stations - 1); x = t * L / 2; w = boat_half(t); g = boat_gunwale(t); k = boat_keel(t)
        lap = 0.03 * min(1.0, w / 0.3)
        def p(u):
            return (w * math.sin(u * math.pi / 2) ** 0.6, k + (g - k) * (1 - math.cos(u * math.pi / 2)) ** 1.25)
        side = []; rseg = []
        for j in range(NS):
            u0, u1 = j / NS, (j + 1) / NS
            y0, z0 = p(u0); y1, z1 = p(u1); mat = BOAT if j % 2 == 0 else BOAT2
            if j:   # proud lower edge of the strake: the clinker lap
                ty, tz = y1 - y0, z1 - z0; L2 = math.hypot(ty, tz) or 1.0
                side.append((y0 + lap * tz / L2, z0 - lap * ty / L2)); rseg.append(mat)
            side.append((y1, z1)); rseg.append(mat)
        rub = [(w + 0.05, g - 0.12), (w + 0.08, g - 0.1), (w + 0.08, g + 0.04), (max(0.02, w - 0.06), g + 0.06)]
        right = side + rub; rseg += [GUNWALE] * len(rub); N = len(right)
        ring = [(-y, z) for y, z in reversed(right)] + [(0.0, k - 0.14)] + right
        rings.append([(x, y, z) for y, z in ring])
        seg_mat = [rseg[N - 1 - q] for q in range(N)] + rseg + [TIMBER]
    loft(m, rings, lambda q: seg_mat[q])
    # Keel: a varnished bar along the bottom, rising into stem and sternpost.
    keel = [(t * L / 2 * 0.995, 0.0, boat_keel(t) - 0.1 + 0.25 * max(0.0, abs(t) - 0.9) / 0.1) for t in [-1 + k / 15 for k in range(31)]]
    m.tube(keel, 0.06, GUNWALE, n=6)
    # Cover: tented over a ridge line (a rope ridge on top), full shoulders over the gunwale, the slopes sagging a
    # little between the hoops, and the skirt hanging below the gunwale, scalloped between the lashings.
    cov = []; n = 49
    for i in range(n):
        t = -0.955 + 1.91 * i / (n - 1); x = t * L / 2; wc = cover_half(t); g = boat_gunwale(t)
        H = 0.7 * (1 - 0.8 * abs(t) ** 7); zs = skirt_z(x, g)          # the cover closes down towards the stems
        sag = 0.035 * math.sin(math.pi * (x / 1.4 - round(x / 1.4))) ** 2
        right = [(wc, zs), (wc + 0.015, g + 0.0), (wc - 0.01, g + 0.11), (0.86 * wc, g + 0.21)]
        for f in (0.62, 0.36, 0.12):
            right.append((f * wc, g + 0.21 + (H - 0.21) * (1 - f / 0.86) - sag * math.sin(math.pi * f / 0.86)))
        right.append((0.0, g + H + 0.035))                         # ridge rope
        arch = right[:-1] + [right[-1]] + [(-y, z) for y, z in reversed(right[:-1])]
        cov.append([(x, y, z) for y, z in arch])
    loft(m, cov, COVER)
    lx = [0.85 * k for k in range(-4, 5)]
    for x in lx:
        t = x / (L / 2); w = boat_half(t); g = boat_gunwale(t); wc = cover_half(t)
        for sd in (-1, 1):   # lashing from the skirt's edge down under the rubbing strake to a hook on the planking
            m.tube([(x, sd * (wc - 0.005), skirt_z(x, g) + 0.03), (x, sd * 0.95 * w, g - 0.42)], 0.014, ROPE, n=4)


def loft(m, rings, mat):
    n = len(rings[0]); verts = [p for r in rings for p in r]; faces = []; mats = []
    for i in range(len(rings) - 1):
        for k in range(n):
            j = (k + 1) % n
            faces.append([i * n + k, i * n + j, (i + 1) * n + j, (i + 1) * n + k]); mats.append(mat(k) if callable(mat) else mat)
    faces.append(list(reversed(range(n)))); faces.append([(len(rings) - 1) * n + k for k in range(n)])
    end = mat(0) if callable(mat) else mat
    m.part(verts, faces, mats + [end, end])


def davit_path(x, yb, zb, side=-1):
    """Curved (crook) davit arm from the boat-deck edge, over the top and out above the boat's centreline."""
    R = (BOAT_Y - yb) / (1 - math.cos(math.radians(150))); cz = zb + 1.65; oc = yb + R
    pts = [(x, side * yb, zb - 0.05), (x, side * yb, zb + 0.7), (x, side * yb, cz)]
    for k in range(1, 11):
        f = math.radians(150 * k / 10)
        pts.append((x, side * (oc - R * math.cos(f)), cz + R * math.sin(f)))
    return pts, (x, side * oc, cz + R)


def lifeboats(m):
    L = BOAT_L
    for side in (-1, 1):
        with m.mirrored(side > 0):
            for xc in BOATS:
                keel = boat_z(xc) - BOAT_RAISE - BOAT_D
                f0 = len(m.faces)
                with m.at((xc, -BOAT_Y, keel)):
                    lifeboat(m, L)
                BOAT_FACES.append((f0, len(m.faces)))
                for dx in (-L / 2 + 0.15, L / 2 - 0.15):
                    x = xc + dx; zb = boat_z(x); yb = slab_half(x) - 0.1
                    pts, crown = davit_path(x, yb, zb)
                    m.tube(pts, [0.18 - 0.07 * i / (len(pts) - 1) for i in range(len(pts))], GOLD, n=8, sx=0.75, sy=1.25)
                    m.box((x, -(yb - 0.06), zb + 0.05), (0.5, 0.36, 0.14), GOLD, bevel=0.04)
                    m.lathe((crown[0], crown[1], crown[2] + 0.02), [(0, 0.1), (0.12, 0.19), (0.3, 0.17), (0.4, 0.06), (0.45, 0)], GOLD, n=8)
                    # Fall: block under the davit head, rope down to a block and hook on the boat's lifting eye.
                    t = dx / (L / 2); tip = Vector(pts[-1]); eye = Vector((x, -BOAT_Y, keel + boat_gunwale(t) + 0.08))
                    top_block = tip - Vector((0, 0, 0.28)); low_block = eye + Vector((0, 0, 0.42))
                    m.lathe(tuple(top_block), [(0, 0.05), (0.04, 0.1), (0.2, 0.1), (0.24, 0.05)], TIMBER, n=8)
                    m.tube([tuple(tip - Vector((0, 0, 0.06))), tuple(top_block + Vector((0, 0, 0.22)))], 0.03, BRASS, n=4)
                    m.tube([tuple(top_block), tuple(low_block + Vector((0, 0, 0.22)))], 0.02, ROPE, n=4)
                    m.lathe(tuple(low_block), [(0, 0.05), (0.04, 0.09), (0.18, 0.09), (0.22, 0.05)], TIMBER, n=8)
                    m.tube([tuple(low_block), tuple(eye + Vector((0, 0, 0.06)))], 0.025, BRASS, n=4)
                    with m.frame(eye, Vector((1, 0, 0)), Vector((0, 0, 1)), Vector((0, -1, 0))):
                        m.torus((0, 0, 0), 0.07, 0.022, BRASS, n=10, m=4)
                    m.lathe(tuple(eye - Vector((0, 0, 0.12))), [(0, 0.035), (0.08, 0.035)], BRASS, n=6)
                    seat('davit foot', x, side * (yb - 0.06), zb - 0.02)
                    block('davit', x, side * yb, 0.34, 0.46, zb, zb + 2.4)


# ------------------------------------------------------------------ rails
RAIL_H = 1.05


def even(pts, step):
    """Resample a polyline at an even arc-length spacing close to step, keeping both ends."""
    P = [Vector(p) for p in pts]; cum = [0.0]
    for a, b in zip(P[:-1], P[1:]):
        cum.append(cum[-1] + (b - a).length)
    total = cum[-1]; k = max(1, round(total / step)); out = []; j = 0
    for i in range(k + 1):
        s = total * i / k
        while j < len(P) - 2 and cum[j + 1] < s:
            j += 1
        seg = cum[j + 1] - cum[j]
        out.append(tuple(P[j].lerp(P[j + 1], 0 if seg < 1e-9 else (s - cum[j]) / seg)))
    return out


def rail_run(m, pts, h=RAIL_H, spacing=1.25, cap=TIMBER, post=WHITE, embed=0.06):
    """White stanchions, two white rails and a varnished cap rail along a polyline of deck points."""
    if len(pts) < 2:
        return
    for p in even(pts, spacing):
        m.box((p[0], p[1], p[2] + (h - 0.04) / 2 - 0.03), (0.065, 0.065, h - 0.02), post)
        seat('rail stanchion', p[0], p[1], p[2] - 0.04, 0.2 if abs(p[0]) > 39.4 else embed)
    path = even(pts, 0.6)
    q = math.pi / 4; c = math.sqrt(2)
    for z in (0.36, 0.7):
        m.tube([(x, y, zz + z) for x, y, zz in path], 1.0, post, n=4, phase=q, sx=0.02 * c, sy=0.02 * c)
    m.tube([(x, y, zz + h) for x, y, zz in path], 1.0, cap, n=4, phase=q, sx=0.038 * c, sy=0.066 * c)


def split_loop(loop, gaps):
    """Split a polyline wherever a gap(x0, x1, side) covers a segment."""
    runs = [[]]
    for p in loop:
        inside = any(x0 <= p[0] <= x1 and (p[1] * side > 0) for x0, x1, side in gaps)
        if inside:
            if runs[-1]:
                runs.append([])
        else:
            runs[-1].append(p)
    return [r for r in runs if len(r) > 1]


def rails(m):
    # Main deck: one loop round the hull, open at the boarding gates.
    s_pts = []
    for i in range(0, 241):
        x = STERN + 0.15 + (STEM - 0.4 - STERN - 0.15) * i / 240
        w = max(0.0, deck_half(x) - 0.2)
        s_pts.append((x, -w, deck_z(x)))
    loop = s_pts + [(x, -y, z) for x, y, z in reversed(s_pts)]
    loop = resample(loop, 0.25, closed=False)
    gaps = []
    for x, width in GATES:
        for side in (-1, 1):
            gaps.append((x - width / 2, x + width / 2, side))
    for run in split_loop(loop, gaps):
        rail_run(m, run)
    for x, width in GATES:
        for side in (-1, 1):
            for gx in (x - width / 2 - 0.05, x + width / 2 + 0.05):
                y = side * (deck_half(gx) - 0.2)
                seat('gate post', gx, y, deck_z(gx) - 0.05); block('gate post', gx, y, 0.22, 0.22, deck_z(gx), deck_z(gx) + RAIL_H + 0.38)
                m.lathe((gx, y, deck_z(gx) - 0.05), [(0, 0.09), (RAIL_H + 0.1, 0.07), (RAIL_H + 0.16, 0.11), (RAIL_H + 0.3, 0.09), (RAIL_H + 0.38, 0)], BRASS, n=8)
    # Boat deck perimeter, open at the stair head (with gate posts) and where the davits stand in the rail line.
    so = offset_loop(slab_outline(), -0.14)
    loop = [(x, y, boat_z(x)) for x, y in resample(so, 0.2)]
    loop = loop + [loop[0]]
    y0, y1 = STAIR_Y
    davits = [xc + dx for xc in BOATS for dx in (-BOAT_L / 2 + 0.15, BOAT_L / 2 - 0.15)]
    def opening(p):
        if p[0] < T1_AFT and y0 - 0.12 < p[1] < y1 + 0.12:
            return True
        return abs(p[1]) > 3.0 and any(abs(p[0] - dx) < 0.3 for dx in davits)
    runs = [[]]
    for p in loop:
        if opening(p):
            if runs[-1]:
                runs.append([])
        else:
            runs[-1].append(p)
    for run in runs:
        rail_run(m, run)
    st = stair_plan(); xt = st['top_x']
    for gy in (y0 - 0.14, y1 + 0.14):
        m.lathe((xt + 0.12, gy, boat_z(xt) - 0.05), [(0, 0.08), (RAIL_H + 0.1, 0.065), (RAIL_H + 0.16, 0.1), (RAIL_H + 0.28, 0.08), (RAIL_H + 0.34, 0)], BRASS, n=8)
        seat('stair gate post', xt + 0.12, gy, boat_z(xt) - 0.05)
        block('stair gate post', xt + 0.12, gy, 0.2, 0.2, boat_z(xt) - 0.05, boat_z(xt) + RAIL_H + 0.34)
    # Stair handrails both sides, following the flight, onto the gate posts.
    # Posts stand on the stringer tops (just below the steps' inner corners); the handrail runs 0.95 m above the nosings.
    nose = lambda x: st['foot_z'] + st['rise'] * (1 + (x - st['foot_x']) / st['tread'])
    low = st['rise'] + 0.02
    for gy in (y0 - 0.07, y1 + 0.07):
        pts = [(x, gy, nose(x) - low) for x in [st['foot_x'] + 0.15 + (xt - 0.05 - st['foot_x'] - 0.15) * k / 12 for k in range(13)]]
        rail_run(m, pts, h=0.95 + low, spacing=1.15, embed=0.06)
    # Monkey island and the aft house roof.
    loop = [(x, y, boat_z(x) + WH_H + 0.3) for x, y in resample(offset_loop(wh_outline(0.3), -0.14), 0.25)]
    loop = [p for p in loop + [loop[0]]]
    runs = [[]]
    for p in loop:
        if p[0] < WH_AFT + 0.0 and 1.1 < p[1] < 2.0:
            if runs[-1]:
                runs.append([])
        else:
            runs[-1].append(p)
    for run in runs:
        rail_run(m, run, h=0.95, cap=BRASS, post=BRASS)
    x0, x1, hw, h = AFT_HOUSE
    loop = [(x, y, boat_z(x) + h + 0.22) for x, y in resample(offset_loop(rect(x0, -hw, x1, hw), 0.12), 0.25)]
    rail_run(m, loop + [loop[0]], h=0.9)


# ------------------------------------------------------------------ masts and rigging
def masts(m):
    zb = boat_z(FOREMAST_X) - 0.1; top = 22.4 + ZL; rake = -0.06
    mx = lambda z: FOREMAST_X + rake * (z - zb)
    pts = [(mx(z), 0, z) for z in [zb + (top - zb) * k / 8 for k in range(9)]]
    m.tube(pts, [0.3 - 0.15 * k / 8 for k in range(9)], TIMBER, n=8)
    xtree, plat = top - 0.45, 19.2 + ZL           # masthead crosstree; lamp platform with the lower shroud band
    for z in (zb + WH_H + 0.6, 17.0 + ZL, plat - 0.12, xtree - 0.12):
        r = 0.3 - 0.15 * (z - zb) / (top - zb) + 0.035
        m.lathe((mx(z), 0, z - 0.1), [(0, r), (0.2, r)], BRASS, n=8)
    m.lathe((mx(top), 0, top - 0.05), [(0, 0.15), (0.15, 0.2), (0.32, 0.17), (0.45, 0.06), (0.62, 0.0)], BRASS, n=8)
    # Short crosstree under the truck, and the lamp platform bracketed forward of the mast.
    m.beam((mx(xtree), -0.5, xtree), (mx(xtree), 0.5, xtree), 0.12, 0.12, TIMBER)
    m.beam((mx(plat) - 0.15, -0.38, plat), (mx(plat) - 0.15, 0.38, plat), 0.14, 0.14, TIMBER)
    # Lamp platform bracketed out on the forward side of the mast, with a brass masthead lantern on it.
    m.box((mx(plat) + 0.62, 0, plat + 0.02), (1.45, 0.62, 0.1), TIMBER, bevel=0.02)
    m.beam((mx(plat - 0.9) + 0.12, 0, plat - 0.9), (mx(plat) + 1.1, 0, plat - 0.03), 0.08, 0.1, TIMBER)
    lantern(m, (mx(plat) + 1.0, 0, plat + 0.07))
    # Aft mast with a small crosstree.
    zb2 = boat_z(AFTMAST_X) - 0.1; top2 = 15.8 + ZL
    ax = lambda z: AFTMAST_X - 0.06 * (z - zb2)
    m.tube([(ax(z), 0, z) for z in [zb2 + (top2 - zb2) * k / 6 for k in range(7)]], [0.18 - 0.08 * k / 6 for k in range(7)], TIMBER, n=8)
    m.lathe((ax(top2), 0, top2 - 0.05), [(0, 0.11), (0.12, 0.15), (0.26, 0.13), (0.36, 0.05), (0.5, 0.0)], BRASS, n=8)
    ay = top2 - 0.42                        # crosstree right under the truck, as painted
    m.lathe((ax(ay + 0.12), 0, ay + 0.06), [(0, 0.11), (0.16, 0.11)], WHITE, n=8)
    m.beam((ax(ay), -0.42, ay), (ax(ay), 0.42, ay), 0.1, 0.1, TIMBER)
    m.lathe((ax(ay), 0, ay - 0.2), [(0, 0.13), (0.16, 0.13)], BRASS, n=8)
    # Standing rigging, as painted: a few fine, taut, tarred stays. The fore shrouds set up on the monkey island
    # inside its rail (landing points fitted to the concept camera), the forestay pair on the foredeck, and a pair
    # of shrouds each side of the aft mast on the boat deck. Brass turnbuckles and eye plates at the deck ends.
    zr = lambda x: boat_z(x) + WH_H + 0.3
    for side in (-1, 1):
        yr = WH_HW + 0.3 - 0.36
        stay(m, (mx(xtree), side * 0.45, xtree - 0.02), (16.85, side * yr, zr(16.85)))
        stay(m, (mx(plat) - 0.15, side * 0.3, plat - 0.02), (17.3, side * yr, zr(17.3)))
        stay(m, (mx(plat) - 0.15, side * 0.3, plat - 0.02), (20.05, side * yr, zr(20.05)))
        stay(m, (mx(plat) + 0.05, side * 0.12, plat - 0.1), (33.6, side * 0.45, deck_z(33.6)))
        for xs in (-22.0, -19.6):
            stay(m, (ax(ay), side * 0.38, ay - 0.02), (xs, side * (slab_half(xs) - 0.3), boat_z(xs)), r=0.016)


def lantern(m, c):
    """Brass masthead lantern: footed base, glazed octagonal body with brass corner posts, domed cap and finial."""
    x, y, z = c
    m.lathe((x, y, z), [(0, 0.24), (0.06, 0.24), (0.12, 0.17), (0.2, 0.2), (0.24, 0.27)], BRASS, n=8)
    m.lathe((x, y, z + 0.24), [(0, 0.22), (0.56, 0.22)], GLASS, n=8, phase=math.pi / 8)
    for k in range(8):
        a = math.pi * k / 4
        m.box((x + 0.235 * math.cos(a), y + 0.235 * math.sin(a), z + 0.52), (0.05, 0.05, 0.58), BRASS)
    m.lathe((x, y, z + 0.78), [(0, 0.3), (0.06, 0.3), (0.22, 0.2), (0.34, 0.08), (0.4, 0.06), (0.46, 0.1), (0.54, 0)], BRASS, n=10)


def stay(m, top, foot, r=0.02):
    """A taut tarred stay from a mast fitting down to a brass turnbuckle on an eye plate at the deck."""
    a, b = Vector(top), Vector(foot); d = (b - a).normalized()
    tb0, tb1 = b - d * 0.62, b - d * 0.08
    m.tube([tuple(a), tuple(tb0 + d * 0.05)], r, ROPE, n=4, phase=math.pi / 4)
    with m.frame(tb0, *_perp(d), d):
        m.lathe((0, 0, 0), [(0, 0.03), (0.08, 0.045), (0.46, 0.045), (0.54, 0.03), (0.54, 0.0)], BRASS, n=6)
    m.tube([tuple(tb0 + d * 0.5), tuple(b + Vector((0, 0, 0.02)))], 0.022, BRASS, n=4)
    m.box((b.x, b.y, b.z + 0.02), (0.22, 0.12, 0.06), BRASS, bevel=0.015)
    seat('stay eye plate', b.x, b.y, b.z - 0.01)


def _perp(d):
    ref = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
    u = ref.cross(d).normalized(); return u, d.cross(u)


# ------------------------------------------------------------------ fittings
def cowl(m, x, y, z, hc=2.75, r=0.27, R=0.6, yaw=0.0, base_h=0.7):
    """Short, fat brass cowl ventilator on a white drum: a stubby neck (about 45% of the mouth), a tight elbow and a
    big flared bell whose recessed throat is dark warm brass. hc is the mouth centre above the deck."""
    f = Vector((math.cos(math.radians(yaw)), math.sin(math.radians(yaw)), 0)); up = Vector((0, 0, 1))
    rb = 0.34; zt = z + hc - rb
    m.lathe((x, y, z - 0.04), [(0, 0.44), (base_h, 0.44), (base_h, 0.47), (base_h + 0.07, 0.47)], [WHITE, WHITE, WHITE], n=14)
    m.lathe((x, y, z + base_h + 0.05), [(0, r + 0.14), (0.08, r + 0.14), (0.16, r + 0.03), (0.3, r + 0.01)], BRASS, n=14)
    base = Vector((x, y, z + base_h + 0.05)); path = [base, Vector((x, y, zt))]
    for k in range(1, 7):
        a = math.pi / 2 * k / 6
        path.append(Vector((x, y, zt)) + up * rb * math.sin(a) + f * rb * (1 - math.cos(a)))
    m.tube([tuple(p) for p in path], r, BRASS, n=14)
    m.lathe((x, y, z + base_h + 0.45), [(0, r + 0.05), (0.12, r + 0.05)], BRASS, n=14)
    with m.frame(path[-1] - f * 0.02, up.cross(f).normalized(), up, f):
        m.lathe((0, 0, 0), [(0, r), (0.1, r * 1.15), (0.26, R * 0.8), (0.4, R * 0.97), (0.46, R), (0.46, R - 0.06), (0.36, R * 0.86),
                            (0.2, R * 0.62), (0.06, r * 0.88)], [BRASS, BRASS, BRASS, BRASS, BRASS, BRASS, THROAT, THROAT], n=18)
    seat('cowl drum', x, y, z - 0.04)
    mc = Vector((x, y)) + Vector((f.x, f.y)) * (rb + 0.46)
    bx = [x - 0.47, x + 0.47, mc.x - R * abs(f.y) - 0.1, mc.x + R * abs(f.y) + 0.1]; by = [y - 0.47, y + 0.47, mc.y - R * abs(f.x) - 0.1, mc.y + R * abs(f.x) + 0.1]
    block('cowl', (min(bx) + max(bx)) / 2, (min(by) + max(by)) / 2, max(bx) - min(bx), max(by) - min(by), z, z + hc + R)


def plinth(m, label, outline, surf, zb, mat):
    """Deck-following solid under a flat-based fitting: on the sloping sheer a flat base would float at its low edge.
    It runs from just inside the deck up past the fitting's base (hidden inside the fitting), and every corner
    is registered for the seating audit, so the audit checks the whole footprint rather than one centre point."""
    top = max([zb] + [surf(x) for x, y in outline]) + 0.03
    m.prism(outline, lambda x, y: surf(x) - 0.03, top, mat)
    for x, y in outline[::max(1, len(outline) // 6)]:
        seat(label, x, y, surf(x) - 0.03, embed=0.04)


def turned(cx, cy, pts, yaw):
    c, s_ = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    return [(cx + c * u - s_ * v, cy + s_ * u + c * v) for u, v in pts]


def lifebuoy(m, x, side):
    """White locker just inboard of the rail (clear of its stanchions and the covering board), with the buoy hung
    on the outside of the rail in front of it."""
    w = deck_half(x); wn = min(deck_half(x - 0.45), deck_half(x + 0.45), w)   # rail line at the locker's narrower end
    y = side * (wn - 0.5); z = deck_z(x)       # 0.29 m clear of the deck edge: inboard of stanchions and the 0.13 m cap rail
    block('lifebuoy locker', x, side * (wn - 0.355), 0.95, 0.71, z, z + 1.3)   # out to the deck edge: no slot
    plinth(m, 'lifebuoy locker', rect(x - 0.42, y - 0.18, x + 0.42, y + 0.18), deck_z, z, WHITE)
    m.box((x, y, z + 0.62), (0.9, 0.42, 1.24), WHITE, bevel=0.05)
    with m.frame((x, side * (w - 0.07), z + 0.78),   # just outboard of the cap rail
                  Vector((-side, 0, 0)), Vector((0, 0, 1)), Vector((0, side, 0))):
        m.torus((0, 0, 0.05), 0.3, 0.09, BUOY, n=16, m=6, mats=lambda i: WHITE if i % 4 == 0 else BUOY)


def fittings(m):
    # Foredeck: windlass, capstan, bollards and the jackstaff at the stem.
    x = 32.6; z = deck_z(x)
    block('windlass', x, 0, 1.3, 2.5, z, z + 1.45)
    plinth(m, 'windlass', rect(x - 0.56, -1.16, x + 0.56, 1.16), deck_z, z, IRON)
    m.box((x, 0, z + 0.25), (1.2, 2.4, 0.5), IRON, bevel=0.06)
    for y in (-0.75, 0.75):
        with m.frame((x, y - 0.35, z + 0.75), Vector((1, 0, 0)), Vector((0, 0, 1)), Vector((0, 1, 0))):
            m.lathe((0, 0, 0), [(0, 0.5), (0.1, 0.38), (0.6, 0.38), (0.7, 0.5)], IRON, n=12)
    m.lathe((x, 0, z + 0.4), [(0, 0.3), (0.5, 0.3), (0.6, 0.38), (0.8, 0.38), (0.9, 0.2), (1.0, 0)], BRASS, n=10)
    x = 35.4; z = deck_z(x)
    block('capstan', x, 0, 0.9, 0.9, z, z + 1.1)
    plinth(m, 'capstan', [(x + px, py) for px, py in circle(0.4, 12)], deck_z, z - 0.05, BRASS)
    m.lathe((x, 0, z - 0.05), [(0, 0.45), (0.2, 0.42), (0.3, 0.3), (0.8, 0.3), (0.9, 0.42), (1.05, 0.42), (1.15, 0)], BRASS, n=12)
    for bx in (30.6, 34.2):   # bollards turned to follow the rail line; collision runs out to the rail: no slot or wedge
        w0, w1 = deck_half(bx - 0.55), deck_half(bx + 0.55)
        by = (w0 + w1) / 2 - 0.55
        for side in (-1, 1):
            z = deck_z(bx); yaw = side * math.degrees(math.atan2(w1 - w0, 1.1)); wb = 0.55 + 0.25 + 0.05
            c, s_ = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
            plinth(m, 'bollard', turned(bx, side * by, rect(-0.52, -0.22, 0.52, 0.22), yaw), deck_z, z, BRASS)
            v = side * (wb / 2 - 0.25)                     # collision centre: from the bollard's inboard face out to the rail
            block('bollard', bx - s_ * v, side * by + c * v, 1.1, wb, z, z + 0.76, yaw)
            with m.at((bx, side * by, z), yaw):
                m.box((0, 0, 0.07), (1.1, 0.5, 0.16), BRASS, bevel=0.04)
                for dx in (-0.3, 0.3):
                    m.lathe((dx, 0, -0.01), [(0, 0.17), (0.55, 0.15), (0.62, 0.22), (0.72, 0.22), (0.76, 0)], BRASS, n=8)
    x = STEM - 0.9; z = deck_z(x)
    block('jackstaff', x, 0, 0.34, 0.34, z, z + 2.6)
    plinth(m, 'jackstaff', [(x + px, py) for px, py in circle(0.13, 8)], deck_z, z - 0.05, BRASS)
    m.lathe((x, 0, z - 0.05), [(0, 0.16), (0.3, 0.14), (2.1, 0.09), (2.15, 0.15), (2.35, 0.17), (2.55, 0.08), (2.7, 0)], BRASS, n=8)
    # Ventilator box with a cap in front of the deckhouse.
    x = 30.4
    block('vent box', x, -1.75, 1.05, 1.05, deck_z(x), deck_z(x) + 1.31)
    plinth(m, 'vent box', rect(x - 0.42, -2.17, x + 0.42, -1.33), deck_z, deck_z(x), WHITE)
    m.box((x, -1.75, deck_z(x) + 0.55), (0.9, 0.9, 1.1), WHITE, bevel=0.06)
    m.box((x, -1.75, deck_z(x) + 1.2), (1.05, 1.05, 0.22), WHITE, bevel=0.05)
    # Lifebuoys on white lockers at the rail.
    for side in (-1, 1):
        for x in (-6.2, 17.8, -27.65):
            lifebuoy(m, x, side)
    # Big brass cowl ventilators round the funnel and aft on the boat deck, white vent trunks beside the casing.
    for side in (-1, 1):
        # As painted: one pair aft of the funnel facing aft and outboard, one pair forward of it facing forward
        # and outboard, each beside a white rounded-top vent trunk; the boat-deck walks stay clear.
        cowl(m, -3.9, side * 1.35, boat_z(-3.9), yaw=180 - side * 35)
        cowl(m, 6.2, side * 1.5, boat_z(6.2), hc=2.6, R=0.62, yaw=side * 10)
        for x in (-4.8, 8.6):
            m.box((x, side * 1.3, boat_z(x) + 0.7), (1.0, 1.1, 1.5), WHITE, bevel=0.08)
            seat('vent trunk', x, side * 1.3, boat_z(x) - 0.05); block('vent trunk', x, side * 1.3, 1.0, 1.1, boat_z(x), boat_z(x) + 2.0)
            with m.frame((x - 0.5, side * 1.3, boat_z(x) + 1.45), Vector((0, 1, 0)), Vector((0, 0, 1)), Vector((1, 0, 0))):
                m.prism([(0.55 * math.cos(math.pi * k / 10), 0.5 * math.sin(math.pi * k / 10)) for k in range(11)], 0.0, 1.0, WHITE)
        # Brass lamps on white pedestals at the front of the boat deck.
        x = T1_FWD - T1_FRONT + 0.6; y = side * (HW1 - 0.25); z = boat_z(x)
        plinth(m, 'lamp pedestal', rect(x - 0.2, y - 0.2, x + 0.2, y + 0.2), boat_z, z, WHITE)
        block('lamp pedestal', x, side * (HW1 - 0.5 + 0.35), 0.5, 0.7, z, z + 2.0)   # out to the rail: no corner slot behind it
        m.box((x, y, z + 0.55), (0.45, 0.45, 1.1), WHITE, bevel=0.05)
        m.lathe((x, y, z + 1.08), [(0, 0.12), (0.2, 0.12)], BRASS, n=8)
        searchlight(m, (x, y, z + 1.55))
    # Monkey island: binnacle, bell and a brass searchlight on a post at the aft corner.
    rz = lambda x: boat_z(x) + WH_H + 0.3
    for lbl, x, y, r in (('binnacle', 18.4, 0.4, 0.26), ('bell post', 19.2, -1.6, 0.1), ('searchlight post', 15.3, -1.6, 0.16)):
        plinth(m, lbl, [(x + px, y + py) for px, py in circle(r, 10)], rz, rz(x) - 0.02, BRASS if r > 0.1 else WHITE)
        block(lbl, x, y, 0.5, 0.5, rz(x), rz(x) + 1.5)
    m.lathe((18.4, 0.4, rz(18.4) - 0.02), [(0, 0.3), (0.15, 0.26), (0.9, 0.2), (1.0, 0.3), (1.15, 0.3), (1.35, 0.18), (1.45, 0)], BRASS, n=10)
    m.box((19.2, -1.6, rz(19.2) + 0.48), (0.12, 0.12, 1.0), WHITE)
    m.lathe((19.2, -1.6, rz(19.2) + 0.95), [(0, 0.08), (0.05, 0.32), (0.32, 0.28), (0.48, 0.14), (0.54, 0)], BRASS, n=12)
    m.lathe((15.3, -1.6, rz(15.3) - 0.02), [(0, 0.2), (0.15, 0.12), (1.2, 0.1), (1.3, 0.16)], BRASS, n=8)
    searchlight(m, (15.3, -1.6, rz(15.3) + 1.7))
    # Stern deck benches and a lantern on the stern.
    xa, xf, zc = CANOPY
    for x0 in BENCHES:
        for side in (-1, 1):
            bench(m, x0, side)
    # Seat-locker across the stern tip (white body, timber seat), carrying the stern lantern and the aft canopy post.
    poly, z0, zt = stern_locker(0.34)
    m.prism(poly, z0, zt - 0.06, WHITE); m.prism(poly, zt - 0.06, zt, DECK)
    for sx, sy in ((STERN_LOCKER_X, -1.5), (STERN_LOCKER_X, 1.5), (STERN_LOCKER_X, 0.0), (-39.45, 0.0)):
        seat('stern locker', sx + 0.05, sy, z0, embed=deck_z(STERN_LOCKER_X) - z0 + 0.01)
    x = -39.2; z = zt
    block('stern lantern', x, 0, 0.4, 0.4, z, z + 1.5)
    m.box((x, 0, z + 0.55), (0.12, 0.12, 1.1), BRASS)
    m.box((x, 0, z + 1.3), (0.3, 0.3, 0.42), GLASS)
    m.lathe((x, 0, z + 1.5), [(0, 0.22), (0.08, 0.22), (0.28, 0.06), (0.38, 0)], BRASS, n=8)
    m.box((x, 0, z + 1.08), (0.36, 0.36, 0.06), BRASS)
    # Canopy posts: brass, with finials on the forward corners.
    pts = [(x, -(deck_half(x) - 0.62)) for x in (xa + 0.4, xa + 3.8, xa + 7.3, xf - 0.3)]
    for side in (-1, 1):
        for i, (x, y) in enumerate(pts):
            z = deck_z(x); tall = 0.85 if i == len(pts) - 1 else 0.35
            if x < STERN_LOCKER_X:            # the aft pair stands on the stern locker's seat
                z = stern_locker(0.34)[2] + 0.02
            else:
                seat('canopy post', x, side * -y, z - 0.05)
            block('canopy post', x, side * (deck_half(x) - 0.42), 0.26, 0.66, z, zc)   # out to the rail: no slot behind the post
            m.lathe((x, side * -y, z - 0.05), [(0, 0.11), (0.25, 0.08), (zc - z - 0.1, 0.07), (zc - z + tall - 0.15, 0.07), (zc - z + tall, 0.13), (zc - z + tall + 0.2, 0)], BRASS, n=8)
    for x in (xa + 0.15,):   # stands on the stern locker
        z = stern_locker(0.34)[2]; block('canopy post', x, 0, 0.22, 0.22, z, zc)
        m.lathe((x, 0, z - 0.03), [(0, 0.1), (zc - z + 0.4, 0.07), (zc - z + 0.55, 0.13), (zc - z + 0.75, 0)], BRASS, n=8)


def searchlight(m, c):
    x, y, z = c
    with m.frame((x - 0.2, y, z), Vector((0, 1, 0)), Vector((0, 0, 1)), Vector((1, 0, 0))):
        m.lathe((0, 0, 0), [(0, 0.22), (0.4, 0.26), (0.48, 0.3), (0.55, 0.3)], BRASS, n=12)
        m.prism(circle(0.25, 12), 0.5, 0.58, GLASS)
    m.box((x - 0.05, y, z - 0.3), (0.12, 0.12, 0.3), BRASS)


def bench(m, x, side):
    """Slatted bench with its back to the rail, turned to follow the curving deck edge (no gap to step into)."""
    w0, w1 = deck_half(x - 1.5), deck_half(x + 1.5)
    yaw = side * math.degrees(math.atan2(w1 - w0, 3.0)); y = side * ((w0 + w1) / 2 - 0.62); z = deck_z(x)   # back clear of the cap rail
    c, s_ = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    with m.at((x, y, z), yaw):
        m.box((0, 0, 0.45), (3.0, 0.5, 0.08), DECK)
        m.box((0, side * 0.22, 0.75), (3.0, 0.08, 0.5), TIMBER)
        for dx in (-1.3, 0.0, 1.3):
            zl = deck_z(x + dx * c) - z - 0.02          # each leg reaches the sloping deck under it
            m.box((dx, 0, (zl + 0.46) / 2), (0.1, 0.45, 0.46 - zl), BRASS)
    for dx in (-1.3, 0.0, 1.3):
        for dv in (-0.2, 0.2):
            seat('bench leg', x + dx * c - dv * s_, y + dx * s_ + dv * c, deck_z(x + dx * c) - 0.02)
    # Collision fills the strip behind the back up to the rail, so there is no slot between bench and rail.
    block('bench', x, side * ((w0 + w1) / 2 - 0.45), 3.05, 0.86, z, z + 1.0, yaw)


# ------------------------------------------------------------------ validation and export
def check(m):
    """Every part closed; any inward-wound part is flipped. Returns a report."""
    edges = {}
    for f in m.faces:
        for a, b in zip(f, f[1:] + f[:1]):
            k = (min(a, b), max(a, b))
            edges[k] = edges.get(k, 0) + 1
    open_edges = sum(1 for c in edges.values() if c != 2)
    flipped = 0
    V = m.verts
    for start, end in m.parts:
        vol = 0.0
        for f in m.faces[start:end]:
            a = Vector(V[f[0]])
            for i in range(1, len(f) - 1):
                vol += a.dot(Vector(V[f[i]]).cross(Vector(V[f[i + 1]]))) / 6
        if vol < 0:
            flipped += 1
            for i in range(start, end):
                m.faces[i] = tuple(reversed(m.faces[i]))
    return {'open_edges': open_edges, 'flipped_parts': flipped, 'parts': len(m.parts)}


def make_materials():
    mats = {}
    for name, (rgb, rough, metal) in MATERIALS.items():
        lin = tuple(((c / 255) / 12.92) if c / 255 <= 0.04045 else (((c / 255) + 0.055) / 1.055) ** 2.4 for c in rgb)
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        try:
            mat.use_nodes = True
        except Exception:
            pass
        bsdf = mat.node_tree.nodes.get('Principled BSDF')
        bsdf.inputs['Base Color'].default_value = (*lin, 1)
        bsdf.inputs['Roughness'].default_value = rough
        bsdf.inputs['Metallic'].default_value = metal
        mat.diffuse_color = (*lin, 1)
        mats[name] = mat
    return mats


SHARP_DEGREES = {'FY_Funnel': 15}  # the funnel keeps its flat facets, as painted


def to_object(m, mats):
    return SM.to_object(m, mats, MATERIALS, SHARP_DEGREES.get(m.name, 38))


# ------------------------------------------------------------------ deck audit, walk layout and collision proxies
def _prism(name, poly, f0, f1):
    pts = [tuple(p) for p in poly]
    if signed_area(pts) < 0:
        pts = pts[::-1]
    return {'name': name, 'poly': [[round(x, 4), round(y, 4)] for x, y in pts],
            'z0': [round(f0(x, y), 4) for x, y in pts], 'z1': [round(f1(x, y), 4) for x, y in pts]}


def _box(name, cx, cy, sx, sy, z0, z1, yaw=0.0):
    c, s_ = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    poly = [(cx + c * u - s_ * v, cy + s_ * u + c * v) for u, v in ((-sx / 2, -sy / 2), (sx / 2, -sy / 2), (sx / 2, sy / 2), (-sx / 2, sy / 2))]
    return _prism(name, poly, lambda x, y: z0, lambda x, y: z1)


def _strip(name, a, b, t, z0, z1):
    """Thin box along a deck-edge segment a->b (x, y), t thick, z0/z1 callables of x."""
    d = Vector((b[0] - a[0], b[1] - a[1])); n = Vector((-d.y, d.x)).normalized() * (t / 2)
    poly = [(a[0] - n.x, a[1] - n.y), (b[0] - n.x, b[1] - n.y), (b[0] + n.x, b[1] + n.y), (a[0] + n.x, a[1] + n.y)]
    return _prism(name, poly, lambda x, y: z0(x), lambda x, y: z1(x))


def collision_proxies():
    """Convex, low-poly collision consistent with the walk layout: decks, house walls, rails to rail height,
    fittings as boxes. Each proxy is a prism: a convex plan polygon with bottom/top heights per corner."""
    P = []
    breaks = sorted({STERN + 0.05, STEM - 0.05, *[g[0] + s_ * g[1] / 2 for g in GATES for s_ in (-1, 1)],
                     *[STERN + 0.05 + k * 1.5 for k in range(1, 54) if STERN + 0.05 + k * 1.5 < STEM - 0.05]})
    for x0, x1 in zip(breaks[:-1], breaks[1:]):
        w0, w1 = deck_half(x0), deck_half(x1)
        P.append(_prism('main deck', [(x0, -w0), (x1, -w1), (x1, w1), (x0, w0)], lambda x, y: 0.0, lambda x, y: deck_z(x)))
        gate = any(g[0] - g[1] / 2 - 1e-6 <= (x0 + x1) / 2 <= g[0] + g[1] / 2 + 1e-6 for g in GATES)
        for sd in (-1, 1):
            if gate:
                continue
            a = (x0, sd * (deck_half(x0) - 0.19)); b = (x1, sd * (deck_half(x1) - 0.19))
            P.append(_strip('main rail', a, b, 0.14, deck_z, lambda x: deck_z(x) + RAIL_H + 0.06))
    # Tier-1 house walls (with the relief of portals and pilasters) and the boat-deck slab over them.
    house_top = lambda x, y: boat_z(x) - SLAB
    xs = [T1_AFT + k * (STEP[0] - T1_AFT) / 9 for k in range(10)]
    for x0, x1 in zip(xs[:-1], xs[1:]):
        P.append(_prism('house', [(x0, -HW_MID - 0.2), (x1, -HW_MID - 0.2), (x1, HW_MID + 0.2), (x0, HW_MID + 0.2)], lambda x, y: deck_z(x) - 0.3, house_top))
    P.append(_prism('house', [(STEP[0], -HW_MID - 0.2), (STEP[1], -HW1 - 0.14), (STEP[1], HW1 + 0.14), (STEP[0], HW_MID + 0.2)], lambda x, y: deck_z(x) - 0.3, house_top))
    xc = T1_FWD - T1_FRONT
    xs = [STEP[1] + k * (xc - STEP[1]) / 4 for k in range(5)]
    for x0, x1 in zip(xs[:-1], xs[1:]):
        P.append(_prism('house', [(x0, -HW1 - 0.14), (x1, -HW1 - 0.14), (x1, HW1 + 0.14), (x0, HW1 + 0.14)], lambda x, y: deck_z(x) - 0.3, house_top))
    P.append(_prism('house', [(xc, -HW1 - 0.14)] + superellipse_front(xc, T1_FRONT + 0.14, HW1 + 0.14, 16) + [(xc, HW1 + 0.14)], lambda x, y: deck_z(x) - 0.3, house_top))
    gx = GATES[0][0]
    for sd in (-1, 1):
        P.append(_box('door portal', gx, sd * (HW1 + 0.14), 2.3, 0.32, deck_z(gx), deck_z(gx) + 3.0))
    so = slab_outline(); xa = T1_AFT - OVERHANG; hm, hf = HW_MID + OVERHANG, HW1 + OVERHANG
    s0, s1 = STEP[0] - OVERHANG * 0.4, STEP[1] - OVERHANG * 0.4
    xs = [xa + k * (s0 - xa) / 9 for k in range(10)]
    slab = (lambda x, y: boat_z(x) - SLAB, lambda x, y: boat_z(x))
    for x0, x1 in zip(xs[:-1], xs[1:]):
        P.append(_prism('boat deck', [(x0, -hm), (x1, -hm), (x1, hm), (x0, hm)], *slab))
    P.append(_prism('boat deck', [(s0, -hm), (s1, -hf), (s1, hf), (s0, hm)], *slab))
    xs = [s1 + k * (xc - s1) / 4 for k in range(5)]
    for x0, x1 in zip(xs[:-1], xs[1:]):
        P.append(_prism('boat deck', [(x0, -hf), (x1, -hf), (x1, hf), (x0, hf)], *slab))
    P.append(_prism('boat deck', [(xc, -hf)] + superellipse_front(xc, T1_FRONT + OVERHANG, hf, 16) + [(xc, hf)], *slab))
    # Boat-deck rails, open at the stair head and the davits (exactly as modelled).
    loop = [(x, y) for x, y in resample(offset_loop(so, -0.14), 0.2)]; loop.append(loop[0])
    y0, y1 = STAIR_Y
    davits = [xc_ + dx for xc_ in BOATS for dx in (-BOAT_L / 2 + 0.15, BOAT_L / 2 - 0.15)]
    def opening(p):
        return (p[0] < T1_AFT and y0 - 0.12 < p[1] < y1 + 0.12) or (abs(p[1]) > 3.0 and any(abs(p[0] - d) < 0.3 for d in davits))
    for a, b in zip(loop[:-1], loop[1:]):
        if not (opening(a) or opening(b)):
            P.append(_strip('boat rail', a, b, 0.12, boat_z, lambda x: boat_z(x) + RAIL_H + 0.06))
    # Wheelhouse with its roof (the monkey island) and roof rail, open at the ladder.
    P.append(_prism('wheelhouse', wh_outline(0.08), lambda x, y: boat_z(x) - 0.12, lambda x, y: boat_z(x) + WH_H))
    P.append(_prism('monkey island', wh_outline(0.3), lambda x, y: boat_z(x) + WH_H - 0.04, lambda x, y: boat_z(x) + WH_H + 0.3))
    loop = resample(offset_loop(wh_outline(0.3), -0.14), 0.25); loop.append(loop[0])
    for a, b in zip(loop[:-1], loop[1:]):
        if not any(p[0] < WH_AFT and 1.1 < p[1] < 2.0 for p in (a, b)):
            P.append(_strip('roof rail', a, b, 0.1, lambda x: boat_z(x) + WH_H + 0.3, lambda x: boat_z(x) + WH_H + 1.3))
    x0, x1, hw, h = CASING
    for dx in (x0 + 1.4, x1 - 3.0):
        for sd in (-1, 1):
            P.append(_box('casing door', dx, sd * (hw + 0.08), 1.2, 0.18, boat_z(dx), boat_z(dx) + 2.0))
    P.append(_prism('casing', rect(x0, -hw, x1, hw), lambda x, y: boat_z(x) - 0.1, lambda x, y: boat_z(x) + h))
    P.append(_prism('funnel', [(FUNNEL_X + 2.75 * math.cos(2 * math.pi * (k + 0.5) / 12), 2.2 * math.sin(2 * math.pi * (k + 0.5) / 12)) for k in range(12)],
                    lambda x, y: boat_z(FUNNEL_X) + h - 0.3, lambda x, y: 19.4 + ZL))
    x0, x1, hw, h = AFT_HOUSE
    P.append(_prism('aft house', rect(x0 - 0.08, -hw - 0.08, x1 + 0.08, hw + 0.08), lambda x, y: boat_z(x) - 0.1, lambda x, y: boat_z(x) + h))
    P.append(_prism('aft house roof', rect(x0 - 0.25, -hw - 0.25, x1 + 0.25, hw + 0.25), lambda x, y: boat_z(x) + h - 0.04, lambda x, y: boat_z(x) + h + 1.1))
    # Stern canopy roof.
    xa_, xf_, zc = CANOPY
    xs = [xa_ + (xf_ - xa_) * k / 10 for k in range(11)]
    P.append(_prism('canopy', [(x, -(deck_half(x) - 0.51)) for x in xs] + [(x, deck_half(x) - 0.51) for x in reversed(xs)],
                    lambda x, y: zc - 0.28, lambda x, y: zc + 0.3))
    # Companionway: a solid ramp under the treads (walkable at its pitch) with handrails both sides.
    st = stair_plan(); xr0 = st['foot_x'] - st['tread']; ramp = lambda x: st['foot_z'] + (st['top_z'] - st['foot_z']) * (x - xr0) / (st['top_x'] - xr0)
    P.append(_prism('stair', rect(xr0, y0, st['top_x'], y1), lambda x, y: deck_z(x) - 0.05, lambda x, y: ramp(x)))
    poly, z0, zt = stern_locker(0.0)
    P.append(_prism('stern locker', poly, lambda x, y: z0, lambda x, y: zt))
    P.append(_prism('stair filler', rect(st['top_x'] - 0.02, y0 - 0.1, T1_AFT + 0.05, y1 + 0.1), lambda x, y: deck_z(x) - 0.05, lambda x, y: boat_z(x) - SLAB + 0.02))
    for gy in (y0 - 0.06, y1 + 0.06):
        P.append(_strip('stair rail', (st['foot_x'], gy), (st['top_x'] + 0.1, gy), 0.12, lambda x: min(ramp(x), st['top_z']) - 0.05, lambda x: min(ramp(x), st['top_z']) + 1.0))
    # Masts and the hanging lifeboats.
    P.append(_box('foremast', FOREMAST_X, 0, 0.6, 0.6, boat_z(FOREMAST_X), 23.4 + ZL))
    P.append(_box('aft mast', AFTMAST_X, 0, 0.4, 0.4, boat_z(AFTMAST_X), 15.8 + ZL))
    for xc_ in BOATS:
        for sd in (-1, 1):
            keel = boat_z(xc_) - BOAT_RAISE - BOAT_D
            P.append(_box('lifeboat', xc_, sd * BOAT_Y, BOAT_L, 2 * (BOAT_HB + 0.14) + 0.1, keel - 0.18, keel + BOAT_D + BOAT_SHEER + 0.7))
    for label, cx, cy, sx, sy, z0, z1, yaw in BLOCKS:
        P.append(_box(label, cx, cy, sx, sy, z0, z1, yaw))
    return P


def export_collision(proxies):
    """FY_Collision.fbx: a tiny placeholder render mesh plus one UCX_ convex hull per proxy (Unreal custom collision)."""
    objs = []
    me = bpy.data.meshes.new('FY_Collision'); s_ = 0.05
    me.from_pydata([(x * s_, y * s_, z * s_ - 2.0) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], [],
                   [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]])
    objs.append(bpy.data.objects.new('FY_Collision', me))
    for i, pr in enumerate(proxies):
        n = len(pr['poly'])
        verts = [(x, y, z) for (x, y), z in zip(pr['poly'], pr['z0'])] + [(x, y, z) for (x, y), z in zip(pr['poly'], pr['z1'])]
        faces = [list(reversed(range(n))), list(range(n, 2 * n))] + [[k, (k + 1) % n, n + (k + 1) % n, n + k] for k in range(n)]
        cm = bpy.data.meshes.new(f'UCX_FY_Collision_{i:03d}'); cm.from_pydata(verts, [], faces); cm.update()
        objs.append(bpy.data.objects.new(cm.name, cm))
    for o in objs:
        bpy.context.collection.objects.link(o)
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.fbx(filepath=str(OUT / 'assets' / 'FY_Collision.fbx'), use_selection=True, apply_unit_scale=True,
                             apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z', object_types={'MESH'},
                             mesh_smooth_type='FACE', bake_anim=False, use_custom_props=False)
    for o in objs:
        data = o.data; bpy.data.objects.remove(o); bpy.data.meshes.remove(data)
    return len(proxies)


def seating_check(meshes):
    """Ray-cast each registered deck fitting's base down onto the deck-bearing meshes (hull and superstructure):
    fail on a gap over 1 cm or a penetration beyond the fitting's declared embedding."""
    from mathutils.bvhtree import BVHTree
    verts, faces = [], []
    for name in ('FY_Hull', 'FY_Superstructure'):
        m = meshes[name]; base = len(verts); verts += m.verts; faces += [[base + i for i in f] for f in m.faces]
    bvh = BVHTree.FromPolygons(verts, faces)
    rows = []
    for label, x, y, z, embed, probe in SEATS:
        hit = bvh.ray_cast(Vector((x, y, z + probe)), Vector((0, 0, -1)), 3.0)
        if hit[0] is None:
            rows.append({'label': label, 'at': [x, y, z], 'status': 'no deck under base'}); continue
        gap = z - hit[0].z
        ok = -(embed + 0.005) <= gap <= 0.01
        rows.append({'label': label, 'at': [x, y, z], 'deck_z': round(hit[0].z, 4), 'gap_m': round(gap, 4), 'embed_allowed_m': embed,
                     'status': 'ok' if ok else ('floating' if gap > 0.01 else 'sunk')})
    # The lifeboats (hull, keel, cover) must not touch rails, house walls or decks.
    lb = meshes['FY_Lifeboats']; bv, bf = lb.verts, [f for a, b in BOAT_FACES for f in lb.faces[a:b]]
    boats = BVHTree.FromPolygons(bv, bf)
    hits = {}
    for name in ('FY_Rails', 'FY_Superstructure', 'FY_Hull', 'FY_Fittings'):
        other = meshes[name]; ov = BVHTree.FromPolygons(other.verts, other.faces)
        hits[name] = len(boats.overlap(ov))
    # Deck fittings must not run through the rails: list where any fitting triangle meets a rail triangle.
    fm, rm = meshes['FY_Fittings'], meshes['FY_Rails']
    pairs = BVHTree.FromPolygons(fm.verts, fm.faces).overlap(BVHTree.FromPolygons(rm.verts, rm.faces))
    spots = sorted({tuple(round(sum(fm.verts[v][k] for v in fm.faces[i]) / len(fm.faces[i]) * 2) / 2 for k in range(3)) for i, _ in pairs})
    hits['fitting_rail_contacts'] = [list(p) for p in spots]
    return rows, hits


def walk_layout(proxies, seats, boat_hits):
    st = stair_plan()
    xs = [STERN + 0.02 + k * 0.1 for k in range(int((STEM - STERN - 0.04) / 0.1) + 1)]
    return {
        'capsule': {'radius': 0.22, 'half_height': 0.755, 'height': 1.51, 'max_riser': 0.30, 'max_slope_deg': 50},
        'main_deck': {'x': [round(x, 3) for x in xs], 'half_width': [round(deck_half(x), 4) for x in xs], 'z': [round(deck_z(x), 4) for x in xs]},
        'boat_deck': {'outline': [[round(x, 4), round(y, 4)] for x, y in slab_outline()],
                      'z': {'x': [round(x, 3) for x in xs], 'z': [round(boat_z(x), 4) for x in xs]}},
        'monkey_island': {'outline': [[round(x, 4), round(y, 4)] for x, y in wh_outline(0.3)], 'z_offset_from_boat_deck': WH_H + 0.3,
                          'access': 'climb-only ladder on the wheelhouse aft face', 'ladder': {'x': WH_AFT - 0.46, 'y': [1.25, 1.85]}},
        'boarding_openings': [{'side': sd, 'x': g[0], 'width': g[1], 'y': sgn * deck_half(g[0])} for g in GATES for sd, sgn in (('starboard', -1), ('port', 1))],
        'stair': {k: (round(v, 4) if isinstance(v, float) else v) for k, v in st.items() if k != 'treads'} | {
            'treads': [[round(a, 4), round(b, 4), round(z, 4)] for a, b, z in st['treads']], 'y': list(STAIR_Y)},
        'proxies': proxies, 'seating': seats, 'lifeboat_overlaps': boat_hits,
    }


def export_fbx(obj, path):
    bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True); bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, apply_unit_scale=True,
                             apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z', object_types={'MESH'},
                             mesh_smooth_type='EDGE', bake_anim=False, use_custom_props=False)


def boarding_gate(mesh):
    """Hinged brass boarding rail; origin is the hinge at floor height, +X runs across the opening."""
    width = GATES[0][1] - .2
    for z in (.48, 1.02):
        mesh.tube([(0, 0, z), (width, 0, z)], .035, GOLD, n=8)
    for x in (width * i / 6 for i in range(7)):
        mesh.tube([(float(x), 0, .2), (float(x), 0, 1.02)], .022, GOLD, n=8)
    mesh.lathe((0, 0, .1), [(0, .055), (.95, .055), (1.02, 0)], BRASS, n=10)


def main():
    (OUT / 'assets').mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats = make_materials()
    builders = [('FY_Hull', hull), ('FY_Superstructure', superstructure), ('FY_Funnel', funnel), ('FY_Lifeboats', lifeboats),
                ('FY_Rails', rails), ('FY_Masts', masts), ('FY_Fittings', fittings), ('FY_BoardingGate', boarding_gate)]
    manifest = {'sources': {str(p.relative_to(yori.REPO)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in (Path(__file__), Path(SM.__file__))}, 'materials': MATERIALS, 'meshes': {}, 'units': 'metres, +X bow, z up, waterline z=0'}
    lo = Vector((1e9, 1e9, 1e9)); hi = -lo
    meshes = {}
    for name, fn in builders:
        m = Mesh(name); fn(m); meshes[name] = m
        report = check(m)
        obj, names = to_object(m, mats)
        tris = sum(len(f) - 2 for f in m.faces)
        bmin = [min(v[i] for v in m.verts) for i in range(3)]; bmax = [max(v[i] for v in m.verts) for i in range(3)]
        lo = Vector([min(lo[i], bmin[i]) for i in range(3)]); hi = Vector([max(hi[i], bmax[i]) for i in range(3)])
        manifest['meshes'][name] = {'triangles': tris, 'vertices': len(m.verts), 'materials': names,
                                    'min': [round(v, 3) for v in bmin], 'max': [round(v, 3) for v in bmax], **report}
        print(f'{name}: {tris} triangles, {report}')
        export_fbx(obj, OUT / 'assets' / f'{name}.fbx')
    seed = Mesh('FY_ImportSeed'); seed.box((0, 0, 0), (.1, .1, .1), WHITE)
    seed_object, _ = to_object(seed, mats)
    export_fbx(seed_object, OUT / 'assets/FY_ImportSeed.fbx')
    bpy.data.objects.remove(seed_object, do_unlink=True)
    gate_x, gate_w = GATES[0]
    manifest['dimensions'] = {'min': [round(v, 3) for v in lo], 'max': [round(v, 3) for v in hi],
                              'length': round(hi.x - lo.x, 2), 'beam': round(hi.y - lo.y, 2), 'height_above_waterline': round(hi.z, 2),
                              'draft': round(-lo.z, 2)}
    manifest['boarding_openings'] = [
        {'side': s, 'centre': [gate_x, round(sign * deck_half(gate_x), 3), round(deck_z(gate_x), 3)], 'width': gate_w,
         'clear_height': 'open above', 'outward': [0, sign, 0]}
        for s, sign in (('starboard', -1), ('port', 1))]
    manifest['decks'] = {'main_deck_z': {'stern': round(deck_z(-38), 2), 'midships': round(deck_z(0), 2), 'bow': round(deck_z(38), 2)},
                         'boat_deck_z_midships': round(boat_z(0), 2), 'monkey_island_z': round(boat_z(19) + WH_H + 0.3, 2),
                         'rail_height': RAIL_H}
    manifest['triangles'] = sum(v['triangles'] for v in manifest['meshes'].values())
    proxies = collision_proxies()
    manifest['collision'] = {'file': 'assets/FY_Collision.fbx', 'convex_hulls': export_collision(proxies)}
    seats, boat_hits = seating_check(meshes)
    contacts = boat_hits.pop('fitting_rail_contacts')
    bad_seats = [r for r in seats if r['status'] != 'ok']
    manifest['deck_audit'] = {'fittings_checked': len(seats), 'failures': len(bad_seats), 'lifeboat_overlaps': boat_hits,
                              'fitting_rail_contacts': contacts}
    st = stair_plan()
    manifest['stair'] = {'risers': st['risers'], 'rise': round(st['rise'], 3), 'tread': st['tread'], 'width': st['width'],
                         'angle_deg': round(st['angle_deg'], 1), 'foot': [round(st['foot_x'], 3), round(st['foot_z'], 3)],
                         'top': [round(st['top_x'], 3), round(st['top_z'], 3)]}
    (OUT / 'deck_layout.json').write_text(json.dumps(walk_layout(proxies, seats, boat_hits)) + '\n')
    for r in bad_seats:
        print('SEAT', r)
    print('deck audit:', len(seats), 'seated fittings,', len(bad_seats), 'failures; lifeboat overlaps', boat_hits)
    print('fitting/rail contacts:', len(contacts), contacts)
    manifest['files'] = {str(p.relative_to(OUT)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in [*(OUT / 'assets').glob('FY_*.fbx'), OUT / 'deck_layout.json']}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'ferry.blend'))
    bad = [n for n, v in manifest['meshes'].items() if v['open_edges']]
    print('FERRY BUILD COMPLETE', manifest['triangles'], 'triangles', 'open edges in' if bad else 'all parts closed', bad or '')
    if bad or bad_seats or sum(boat_hits.values()) or contacts:
        raise SystemExit(1)       # open edges, an unseated fitting, a lifeboat touching the ship or a fitting through a rail fail the build


if __name__ == '__main__':
    main()
