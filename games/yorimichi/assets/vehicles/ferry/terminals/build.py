"""Ferry terminals at Hidamari and Brinecove, matched to the v2 concepts. Procedural Blender build.

blender --background --factory-startup --threads 3 --python-exit-code 1 -P games/yorimichi/assets/vehicles/ferry/terminals/build.py
Reads build/yorimichi/ferry/terminals/site.json (site.py: the berths, boarding gates, fender faces and the exported
walk levels), and refuses it when its recorded inputs (world probes, site.py, the ship's build.py) changed or its
sweep failed. Each terminal is modelled in its region's frame (Hidamari: world metres; Brinecove: region-local) and
exported with its origin at the anchor recorded in the manifest, on the fender face opposite the boarding gate at sea
level. Writes FT_*.fbx (render meshes), FT_*_Collision.fbx (UCX_ convex hulls), terminals.blend, manifest.json and
walk.json.

Audits (any failure exits 1): closed meshes; a ray-cast walk from the promenade over the brow onto the ship's deck
(step, headroom, width, floor) with ship C at its berth; and ship against terminal in 3D: no triangle of a terminal
mesh may meet a triangle of the ship at its berth pose, and the gaps of the parts meant to come close (fenders, brow
body, brow lip on the landing plate) are reported.
"""
import importlib.util
import hashlib
import json
import math
import sys
import types
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import build as F  # noqa: E402  (the ferry's mesh builder; importing it does not build the ship)
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

sys.modules['ferry_build'] = F               # site.py reads the hull lines from this same module
_spec = importlib.util.spec_from_file_location('ferry_site', HERE / 'site.py')   # not the stdlib site module
FS = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(FS)
_spec = importlib.util.spec_from_file_location('ferry_walkcheck', HERE / 'walkcheck.py')
WC = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(WC)
OUT = F.OUT / 'terminals'
SITE = json.loads((OUT / 'site.json').read_text())
if FS.stale_inputs(SITE) or not SITE.get('pass'):
    raise SystemExit(f'site.json is stale or failed ({FS.stale_inputs(SITE) or "sweep FAIL"}): rerun world_probe.py and site.py')
SILL = SITE['ship']['sill_z']
GATE_W = SITE['ship']['gate_width']
DOOR_RISER = 0.2                           # waiting-house door steps: riser limit (under walkcheck.STEP_MAX)
BROW_W = 1.9            # brow width: clear of the ship's brass gate posts (inner faces 1.04 m off the gate centre)
LIP = 0.55              # the brow's steel lip runs this far inboard of the hull side, onto the landing plate
LIP_T, LIP_GAP = 0.02, 0.003    # lip thickness; it rests 3 mm above the plate (resting, never through it)
HULL_GAP = 0.03         # the brow body stops this far outside the hull side
FENDER_GAP = 0.05       # hung fenders stop this far off the hull
PLATE_TOP = F.landing_plate(*F.GATES[0])[1]
COL = []                # fixed terminal hulls
BROW_COL = []           # moving hulls, exported with the brow


def col(points):
    COL.append([tuple(p) for p in points])


def col_box(x0, y0, x1, y1, z0, z1):
    col([(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)])


def col_seg(a, b, t, z0, z1):
    """A thin upright slab along a plan segment (rails, walls)."""
    d = Vector((b[0] - a[0], b[1] - a[1], 0)); n = Vector((-d.y, d.x, 0)).normalized() * (t / 2)
    col([(p[0] + s * n.x, p[1] + s * n.y, z) for p in (a, b) for s in (-1, 1) for z in (z0, z1)])

# ------------------------------------------------------------------ materials (sRGB, roughness, metallic)
TIMBER, TIMBER_DARK, PLANK, PLASTER, KAWARA, RIDGE = 'FT_Timber', 'FT_TimberDark', 'FT_Plank', 'FT_Plaster', 'FT_Kawara', 'FT_KawaraRidge'
STONE, BLACK, IRON, WHITE, GLASS, PAPER = 'FT_Stone', 'FT_FenderBlack', 'FT_Iron', 'FT_WhitePaint', 'FT_Glass', 'FT_Paper'
ROPE, NET, FLOAT, CRATE, BRASS, GLOW, INK, TERRACOTTA, MOSS = ('FT_Rope', 'FT_Net', 'FT_Float', 'FT_Crate', 'FT_Brass',
                                                             'FT_LanternGlow', 'FT_Ink', 'FT_Terracotta', 'FT_Moss')
MATERIALS = {
    TIMBER: ((132, 88, 52), .7, 0.), TIMBER_DARK: ((84, 58, 40), .75, 0.), PLANK: ((168, 126, 84), .8, 0.),
    PLASTER: ((236, 230, 216), .85, 0.), KAWARA: ((74, 78, 90), .55, .1), RIDGE: ((56, 59, 70), .5, .1),
    STONE: ((150, 146, 136), .9, 0.), BLACK: ((34, 34, 36), .7, 0.), IRON: ((44, 44, 46), .45, .5),
    WHITE: ((236, 236, 232), .5, 0.), GLASS: ((70, 86, 104), .15, 0.), PAPER: ((240, 232, 210), .9, 0.),
    ROPE: ((196, 168, 118), .9, 0.), NET: ((58, 104, 108), .9, 0.), FLOAT: ((232, 112, 50), .6, 0.),
    CRATE: ((150, 108, 66), .8, 0.), BRASS: ((206, 164, 78), .35, .55), GLOW: ((255, 214, 150), .5, 0.),
    INK: ((40, 36, 34), .8, 0.), TERRACOTTA: ((176, 98, 62), .8, 0.), MOSS: ((92, 118, 70), .9, 0.),
}
F.MATERIALS.update(MATERIALS)          # the ferry's to_object orders slots by this table

RISER_MAX = 0.24
TREAD = 0.28
RAIL_H = 1.05


def frame_axes(U, V):
    """A right-handed frame from two axes: U, V and their cross product."""
    U, V = Vector(U).normalized(), Vector(V).normalized()
    return U, V, U.cross(V)


# ------------------------------------------------------------------ structural pieces
SINK = 0.01            # fitting bases start this far into what carries them: no base face shares the support's plane


def post(m, x, y, z0, z1, s=0.26, mat=TIMBER, footing=False):
    """A square post standing on z0 (sunk SINK into it), up to z1; a footing takes the post's foot 3 cm into it."""
    with m.fitting('post') as base:
        zb = z0 - SINK + (0.03 if footing else 0.0)
        m.box((x, y, (zb + z1) / 2), (s, s, z1 - zb), mat, bevel=0.015)
        if footing:
            m.box((x, y, z0 - SINK + 0.12), (s + 0.22, s + 0.22, 0.24), STONE, bevel=0.03)
        base.append((x, y, z0 - SINK))


def rail_line(m, pts, z, h=RAIL_H, spacing=1.6, mat=TIMBER):
    """Timber railing along a polyline at floor height z: square posts, a capped top rail and a mid rail. Rails of
    alternate segments are 6 mm larger in section, so two rails meeting at a corner share no face."""
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        e = 0.006 * (i % 2)
        L = math.dist(a, b); n = max(1, math.ceil(L / spacing))
        for k in range(n + 1):
            if k == 0 and a is not pts[0]:
                continue
            x = a[0] + (b[0] - a[0]) * k / n; y = a[1] + (b[1] - a[1]) * k / n
            m.box((x, y, z + h / 2), (0.13, 0.13, h), mat, bevel=0.01)
            m.box((x, y, z + h + 0.03), (0.17, 0.17, 0.06), mat)
        m.beam((a[0], a[1], z + h - 0.05), (b[0], b[1], z + h - 0.05), 0.11 + e, 0.14 + e, mat)
        m.beam((a[0], a[1], z + h * 0.5), (b[0], b[1], z + h * 0.5), 0.07 + e, 0.1 + e, mat)
        col_seg(a, b, 0.17, z, z + h + 0.06)


def solid_stair(m, foot, direction, width, z0, flights, r, tread=TREAD, landing=1.2, top_mat=PLANK, side_mat=TIMBER_DARK,
                T=0.25):
    """Flights of closed steps (treads and risers in one solid each, so there is no daylight between steps), each with
    a soffit parallel to its pitch, joined by landing slabs. foot is the centre of the first riser on the floor at z0;
    the stair climbs along direction. Each flight's last riser stands 5 mm inside what it climbs onto (a landing or
    the floor at the top), so the riser's face does not share that floor's front face; landings are 1 cm wider than
    the flights and the stringers run 5 mm into the flight's sides, so no side faces coincide. Returns its run, rise
    and top."""
    d = Vector((direction[0], direction[1], 0)).normalized()
    U, V, A = frame_axes(d, (0, 0, 1))
    u, z = 0.0, 0.0; treads = []
    with m.frame((foot[0], foot[1], z0), U, V, A):
        for fi, n in enumerate(flights):
            us, zs = u, z
            pts = [(us, zs)]
            for k in range(n):
                z += r; pts.append((u, z))
                if k < n - 1:
                    treads.append((u, u + tread, z)); u += tread; pts.append((u, z))
            ue = u + 0.005                # the last riser, 5 mm inside the landing or floor it climbs onto
            if n > 1:
                pts[-2] = (ue, pts[-2][1])
            pts[-1] = (ue, z)
            pts += [(ue, z - r - T), (us + T * tread / r, zs)]
            mats = {}
            for a_, b_ in zip(pts, pts[1:] + pts[:1]):
                horizontal = abs(a_[1] - b_[1]) < 1e-6 and b_[0] > a_[0]
                mats[(round((a_[0] + b_[0]) / 2, 4), round((a_[1] + b_[1]) / 2, 4))] = top_mat if horizontal else side_mat
            m.prism(pts, -width / 2, width / 2, lambda x, y, mats=mats: mats.get((round(x, 4), round(y, 4)), side_mat),
                    top=side_mat, bottom=side_mat)
            for sd in (-1, 1):            # stringers on both sides, 0.25 m proud of the pitch line, 5 mm into the
                # flight's sides and starting 5 mm before its first riser
                sl = [(us - 0.005, zs - 0.05), (us - 0.005, zs + r + 0.25), (u, z + 0.25), (u, z - r - T - 0.05)]
                m.prism(sl, *sorted((sd * (width / 2 - 0.005), sd * (width / 2 + 0.08))), TIMBER)
            # Collision: a ramp over the nosings of the flight (players walk the stair as a slope), down to the soffit.
            Wd = lambda uu, zz, vv: tuple(Vector((foot[0], foot[1], z0)) + U * uu + V * zz + A * vv)
            col([Wd(uu, zz, vv) for uu, zz in ((us, zs), (u, z), (u, z - r - T), (us, zs - T)) for vv in (-width / 2, width / 2)])
            if fi < len(flights) - 1:
                col([Wd(uu, zz, vv) for uu in (u, u + landing) for zz in (z - T, z) for vv in (-width / 2, width / 2)])
                # One landing slab: its walking face (the profile edge at z) takes the tread finish, so no second
                # slab shares that face.
                m.prism(F.rect(u, z - T, u + landing, z), -width / 2 - 0.005, width / 2 + 0.005,
                        lambda x, y, z=z: top_mat if abs(y - z) < 1e-6 else side_mat, top=side_mat, bottom=side_mat)
                treads.append((u, u + landing, z)); u += landing
    top = (foot[0] + d.x * u, foot[1] + d.y * u, z0 + z)
    return {'run': round(u, 4), 'rise': round(z, 4), 'top': [round(v, 4) for v in top], 'risers': sum(flights), 'riser': round(r, 5),
            'tread': tread, 'landing': landing, 'width': width}


def stair_run(flights, tread=TREAD, landing=1.2):
    return sum((n - 1) * tread for n in flights) + landing * (len(flights) - 1)


def gable_roof(m, x0, y0, x1, y1, ze, pitch, axis='x', over=(0.9, 0.9, 0.9, 0.9), t=0.16, ribs=True, gable_mat=TIMBER_DARK):
    """Kawara gable roof over the wall rectangle; ridge along axis; eave height ze at the wall line.
    over = (west, east, south, north) overhangs. Returns the ridge height."""
    if axis == 'y':          # build along x in a rotated frame: swap axes by mirroring through x = y
        with m._push(F.Matrix(((0, 1, 0, 0), (1, 0, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))):
            return gable_roof(m, y0, x0, y1, x1, ze, pitch, 'x', (over[2], over[3], over[0], over[1]), t, ribs, gable_mat)
    yc = (y0 + y1) / 2; D = (y1 - y0) / 2; zr = ze + D * pitch
    ow, oe, os_, on = over
    for s, o in ((-1, os_), (1, on)):
        run = D + o; L = math.hypot(run, run * pitch)
        V = Vector((0, s * run, -run * pitch)).normalized()
        U, V, A = frame_axes((1, 0, 0), V)
        flip = A.z < 0
        if flip:
            U, V, A = frame_axes((-1, 0, 0), V)
        ua, ub = (-(x1 + oe), -(x0 - ow)) if flip else (x0 - ow, x1 + oe)
        with m.frame((0, yc, zr + 0.02), U, V, A):
            m.prism(F.rect(ua, 0.0, ub, L), 0.0, t, KAWARA, top=KAWARA, bottom=TIMBER_DARK)
        if ribs:
            n = int((x1 + oe - (x0 - ow)) / 0.3)
            for k in range(n + 1):
                x = x0 - ow + 0.12 + k * (x1 + oe - x0 + ow - 0.24) / n
                # Each rib starts 1 cm down the slope, so its end cap is clear of the slab's ridge face.
                p0 = Vector((x, yc, zr + 0.02)) + A * (t + 0.02) + V * 0.01; p1 = p0 + V * (L - 0.06)
                m.tube([tuple(p0), tuple(p1)], 0.065, KAWARA, n=5)
            # Round eave tiles and a fascia board under the eave edge.
            e = Vector((0, yc, zr + 0.02)) + V * L
            m.beam((x0 - ow, e.y, e.z - 0.12), (x1 + oe, e.y, e.z - 0.12), 0.12, 0.22, TIMBER_DARK)
        # Rafter ends under the overhang, their tops 3 mm into the roof slab (they carry it).
        zt = ze + 0.02 - 0.047 * math.hypot(1.0, pitch)      # the axis, 0.047 m under the slab across the pitch
        for k in range(int((x1 - x0) / 0.6) + 1):
            x = x0 + k * (x1 - x0) / int((x1 - x0) / 0.6)
            a = Vector((x, y0 if s < 0 else y1, zt)); b = Vector((x, yc + s * (D + o - 0.1), zt - (o - 0.1) * pitch))
            m.beam(tuple(a), tuple(b), 0.08, 0.1, TIMBER_DARK)
    # Ridge: a capped tile ridge with onigawara end blocks. The beam and the tube end at different depths inside the
    # end blocks, clear of the bargeboards' faces.
    m.beam((x0 - ow - 0.07, yc, zr + 0.18), (x1 + oe + 0.07, yc, zr + 0.18), 0.4, 0.36, RIDGE)
    m.tube([(x0 - ow - 0.04, yc, zr + 0.4), (x1 + oe + 0.04, yc, zr + 0.4)], 0.15, RIDGE, n=8)
    for x in (x0 - ow - 0.1, x1 + oe + 0.1):
        m.box((x, yc, zr + 0.42), (0.22, 0.56, 0.62), RIDGE, bevel=0.04)
    # Gable triangles and bargeboards at both ends. Each triangle reaches 3 mm into the roof slabs (no gap under the
    # roof); its sloped top edges are registered as upward seats that must find the roof underside within 2 mm, one
    # ray per point (side rays on the slope would land at other heights and could pass a gap).
    for x, o in ((x0, -ow), (x1, oe)):
        tri = [(y0, ze), (y1, ze), (y1, ze + 0.023), (yc, zr + 0.023), (y0, ze + 0.023)]
        with m.fitting('gable infill', embed=0.005, direction=(0, 0, 1), gap=0.002, spread=0) as base:
            with m.frame((x - 0.06, 0, 0), Vector((0, 1, 0)), Vector((0, 0, 1)), Vector((1, 0, 0))):
                m.prism(tri, 0.0, 0.12, gable_mat)
            apex = max(tri, key=lambda p: p[1])
            for ya in (y0, y1):      # points along each sloped top edge, mid-thickness, taken from the triangle itself
                eave = max((p for p in tri if p[0] == ya), key=lambda p: p[1])
                for f in (0.15, 0.4, 0.65, 0.9):
                    base.append((x, eave[0] + (apex[0] - eave[0]) * f, eave[1] + (apex[1] - eave[1]) * f))
        for s in (-1, 1):            # the second bargeboard is 8 mm wider, so the pair share no face at the apex
            ye = yc + s * (D + (os_ if s < 0 else on)); zz = ze - (os_ if s < 0 else on) * pitch
            m.beam((x + o, yc, zr + 0.12), (x + o, ye, zz + 0.05), 0.1 if s < 0 else 0.108, 0.32, TIMBER_DARK)
    return zr


def tie_truss(m, x, y0, y1, ze, zr, mat=TIMBER):
    """Exposed king-post truss across the building at x (under a gable_roof over y0..y1 from ze to zr): the king post
    runs up into the roof slabs (5 mm, at its faces) and carries them."""
    yc = (y0 + y1) / 2; pitch = (zr - ze) / ((y1 - y0) / 2)
    m.beam((x, y0, ze - 0.2), (x, y1, ze - 0.2), 0.22, 0.3, mat)
    m.beam((x, yc, ze - 0.05), (x, yc, zr + 0.02 - 0.1 * pitch + 0.005), 0.2, 0.2, mat)
    for s, w in ((y0, 0.16), (y1, 0.15)):       # struts 1 cm apart in width: their faces meet at the king post apart
        m.beam((x, s + (yc - s) * 0.12, ze - 0.05), (x, yc, zr - 0.25), w, 0.18, mat)


def knee(m, p, q, mat=TIMBER):
    m.beam(p, q, 0.12, 0.14, mat)


def bollard(m, x, y, z, r=0.22):
    z -= SINK
    with m.fitting('bollard') as base:
        m.lathe((x, y, z), [(0, r * 1.2), (0.08, r * 1.2), (0.12, r), (0.5, r * 0.9), (0.58, r * 1.35), (0.68, r * 1.35), (0.74, 0)],
                IRON, n=12)
        base.append((x, y, z))


def tyre(m, c, normal, R=0.36, r=0.13):
    n = Vector(normal).normalized(); U, V, A = frame_axes(Vector((0, 0, 1)).cross(n) if abs(n.z) < 0.9 else Vector((1, 0, 0)), n)
    with m.frame(c, U, A, V):
        m.torus((0, 0, 0), R, r, BLACK, n=14, m=6)


def rope_coil(m, x, y, z, R=0.42, turns=3):
    with m.fitting('rope coil') as base:
        for k in range(turns):
            m.torus((x, y, z + 0.05 + k * 0.075), R - k * 0.05, 0.045, ROPE, n=16, m=5)
        base.append((x + R, y, z + 0.005))       # the bottom turn's underside


def crate(m, x, y, z, s=0.9, yaw=0.0):
    with m.at((x, y, z - SINK), yaw), m.fitting('crate') as base:
        base += [(u * s * 0.4, v * s * 0.4, 0.0) for u in (-1, 1) for v in (-1, 1)]
        m.box((0, 0, s / 2), (s, s, s), CRATE, bevel=0.02)
        for h in (0.12, s - 0.12):
            m.ring_prism(F.rect(-s / 2 - 0.02, -s / 2 - 0.02, s / 2 + 0.02, s / 2 + 0.02), F.rect(-s / 2 + 0.01, -s / 2 + 0.01, s / 2 - 0.01, s / 2 - 0.01),
                         h - 0.05, h + 0.05, TIMBER_DARK)


def barrel(m, x, y, z, h=0.95):
    z -= SINK
    with m.fitting('barrel') as base:
        m.lathe((x, y, z), [(0, 0.27), (0.1, 0.31), (h / 2, 0.36), (h - 0.1, 0.31), (h, 0.27), (h, 0)], CRATE, n=14)
        for hz in (0.12, h - 0.12):
            m.lathe((x, y, z + hz - 0.03), [(0, 0.325), (0.06, 0.325), (0.06, 0)], IRON, n=14)
        base.append((x, y, z))


def net_pile(m, x, y, z, r=0.75):
    with m.fitting('net pile') as base:
        m.lathe((x, y, z - SINK), [(0, r), (r * 0.35, r * 0.9), (r * 0.6, r * 0.55), (r * 0.72, 0)], NET, n=12, sx=1.0, sy=0.8)
        base.append((x, y, z - SINK))
    for k in range(5):
        a = k * 1.3
        m.lathe((x + 0.55 * r * math.cos(a), y + 0.45 * r * math.sin(a), z + 0.18 + 0.12 * (k % 2)),
                [(0, 0.0), (0.04, 0.12), (0.14, 0.15), (0.24, 0.12), (0.28, 0.0)], FLOAT, n=10)


def lantern(m, x, y, z, h=0.42):
    m.box((x, y, z + h / 2), (0.26, 0.26, h), GLOW)
    m.box((x, y, z + 0.02), (0.32, 0.32, 0.05), TIMBER_DARK)
    m.lathe((x, y, z + h), [(0, 0.24), (0.05, 0.24), (0.14, 0.05), (0.18, 0)], TIMBER_DARK, n=4, phase=math.pi / 4)


def ground_under(world, x0, y0, x1, y1):
    """The lowest exported walking surface under a footprint, so feet and bases meet the ground (sinking a little
    where it is higher, never floating where it is lower). Fails if any of the footprint has no surface."""
    z = FS.levels(world, FS.rect_points(x0, y0, x1, y1, 0.1), FS.HD.QUAY_RAIL + 0.5)
    if np.isnan(z).any():
        raise SystemExit(f'no exported ground under ({x0:.2f}, {y0:.2f})-({x1:.2f}, {y1:.2f})')
    return float(np.min(z))


def bench(m, a, b, z, depth=0.42, h=0.44):
    """A plank bench from a to b on floor z; its legs start 5 mm into the floor (posts sink SINK: no shared plane)."""
    d = Vector((b[0] - a[0], b[1] - a[1], 0)); L = d.length; d.normalize(); nrm = Vector((-d.y, d.x, 0))
    with m.fitting('bench') as base:
        m.beam((a[0], a[1], z + h), (b[0], b[1], z + h), depth, 0.07, PLANK)
        for t in (0.12, 0.5, 0.88):
            if L < 2.0 and t == 0.5:
                continue
            p = (a[0] + d.x * L * t, a[1] + d.y * L * t)
            m.box((p[0], p[1], z + h / 2 - 0.0225), (0.1 + abs(nrm.x) * (depth - 0.1), 0.1 + abs(nrm.y) * (depth - 0.1), h - 0.035), TIMBER_DARK)
            base.append((p[0], p[1], z - 0.005))


def wall(m, a, b, z0, h, t, mat, openings=(), frame_mat=TIMBER, end_post=True):
    """A straight wall from a to b (outward normal to the right of a->b) with rectangular openings
    [(u0, u1, v0, v1)] in metres along/up the wall; timber frame members at the ends and around openings.

    No two members share a face plane: the infill stops 1 cm inside the base board, top beam, sills and lintels, at
    the jamb centres and inside the corner posts; the corner posts stand 8 mm proud of the boards and beams, which
    stop inside them clear of the next wall's; jambs stand 5 mm proud of the lintels, which run 5 mm past them; the
    window grid's ends run 5 mm into the frame and its transoms are 5 mm shallower than its mullions. Walls round a
    building build each corner post once: pass end_post=False and close the loop."""
    d = Vector((b[0] - a[0], b[1] - a[1], 0)); L = d.length; d.normalize()
    U, V, A = frame_axes(d, (0, 0, 1))
    f = t / 2 + 0.03                  # base board and top beam half-depth
    P = f + 0.008                     # corner post half-size, both ways
    me = f + 0.004                    # boards and beams stop inside the corner posts, clear of the next wall's
    se = t / 2 + 0.004                # the infill stops inside the corner posts, clear of the next wall's infill
    doors = sorted(o for o in openings if o[2] <= 0.05)
    cuts = sorted({se, L - se, *[o[0] - 0.06 for o in openings], *[o[1] + 0.06 for o in openings]})
    with m.frame((a[0], a[1], z0), U, V, A):
        for u0, u1 in zip(cuts, cuts[1:]):
            spans = [(0.01, h - 0.01)]
            for o in openings:
                if o[0] - 0.06 <= u0 + 1e-6 and o[1] + 0.06 >= u1 - 1e-6:
                    spans = [(s0, s1) for s0, s1 in [(0.01, o[2] - 0.01), (o[3] + 0.01, h - 0.01)] if s1 - s0 > 1e-3]
            for v0, v1 in spans:
                m.prism(F.rect(u0, v0, u1, v1), -t / 2, t / 2, mat)
        for u in ((0.0, L) if end_post else (0.0,)):
            m.prism(F.rect(u - P, -0.01, u + P, h + 0.01), -P, P, frame_mat)
        m.prism(F.rect(me, h - 0.18, L - me, h), -f, f, frame_mat)
        base = [me]                   # the base board stops inside the jambs of a door
        for o in doors:
            base += [o[0] - 0.07, o[1] + 0.07]
        base.append(L - me)
        for u0, u1 in zip(base[::2], base[1::2]):
            if u1 - u0 > 1e-3:
                m.prism(F.rect(u0, 0.0, u1, 0.2), -f, f, frame_mat)
        for o in openings:
            u0, u1, v0, v1 = o[:4]; door = o[2] <= 0.05
            for u in (u0 - 0.06, u1 + 0.06):
                m.prism(F.rect(u - 0.06, -0.01 if door else v0 - 0.06, u + 0.06, min(h, v1 + 0.06)), -t / 2 - 0.04, t / 2 + 0.04, frame_mat)
            m.prism(F.rect(u0 - 0.125, v1, u1 + 0.125, v1 + 0.1), -t / 2 - 0.035, t / 2 + 0.035, frame_mat)
            if not door:
                m.prism(F.rect(u0 - 0.125, v0 - 0.1, u1 + 0.125, v0), -t / 2 - 0.05, t / 2 + 0.05, frame_mat)
            kind = o[4] if len(o) > 4 else 'window'
            if kind == 'window':      # sliding glazed sash with a timber grid (inset)
                m.prism(F.rect(u0, v0, u1, v1), -0.03, 0.03, GLASS)
                nx = max(1, round((u1 - u0) / 0.45)); ny = max(1, round((v1 - v0) / 0.45))
                for i in range(1, nx):
                    uu = u0 + (u1 - u0) * i / nx
                    m.prism(F.rect(uu - 0.025, v0 - 0.005, uu + 0.025, v1 + 0.005), -0.05, 0.05, frame_mat)
                for j in range(1, ny):
                    vv = v0 + (v1 - v0) * j / ny
                    m.prism(F.rect(u0 - 0.005, vv - 0.025, u1 + 0.005, vv + 0.025), -0.045, 0.045, frame_mat)
            elif kind == 'door':      # closed
                m.prism(F.rect(u0, 0.0, u1, v1), -0.04, 0.04, TIMBER_DARK)
                m.prism(F.rect(u0 + 0.12, v1 * 0.55, u1 - 0.12, v1 - 0.12), -0.06, 0.06, GLASS)
            elif kind == 'open door':  # a sliding door slid open: the leaf stands on the outer face beside the opening
                w = u1 - u0
                m.prism(F.rect(u0 - w, 0.0, u0, v1), t / 2 + 0.05, t / 2 + 0.09, TIMBER_DARK)
                m.prism(F.rect(u0 - w + 0.12, v1 * 0.55, u0 - 0.12, v1 - 0.12), t / 2 + 0.04, t / 2 + 0.10, GLASS)
            elif kind == 'counter':   # ticket window: an open hatch with a shelf 5 mm above the sill
                m.prism(F.rect(u0, v0 - 0.075, u1, v0 + 0.005), 0.0, 0.42, PLANK)


def piles_under(m, xs, ys, z_top, z_bot=-4.0, s=0.34, braces=True, mat=TIMBER_DARK):
    for x in xs:
        for y in ys:
            m.box((x, y, (z_top + z_bot) / 2), (s, s, z_top - z_bot), mat)
    if braces:                       # walings just above the water and cross-braces under the deck
        for y in ys:
            m.beam((xs[0], y, 0.6), (xs[-1], y, 0.6), 0.12, 0.22, mat)
            for xa, xb in zip(xs, xs[1:]):
                m.beam((xa, y, 0.7), (xb, y, z_top - 0.55), 0.1, 0.14, mat)


def brow(m, shore, hull, inboard, z_shore, width=BROW_W):
    """White truss gangway from the terminal edge (shore, walking level z_shore) to HULL_GAP outside the hull side
    (hull); its deck rises to the lip, a steel plate that runs LIP on inboard (unit vector) and rests LIP_GAP above the
    ship's level landing plate. Handrails 1.0 m; it fits between the ship's gate posts."""
    first_collision = len(COL)
    z_end = PLATE_TOP + LIP_GAP + LIP_T                  # walking level at the ship end
    d = Vector((hull[0] - shore[0], hull[1] - shore[1], 0)); L = d.length - HULL_GAP; d.normalize()
    nrm = Vector((-d.y, d.x, 0)); rise = z_end - z_shore
    U, V, A = frame_axes(d, (0, 0, 1))
    with m.frame((shore[0], shore[1], z_shore), U, V, A):     # deck: a profile in (along, up), across the width
        walk_face = lambda x, y: PLANK if abs(y - x * rise / L) < 1e-4 else WHITE
        m.prism([(0.0, -0.12), (L, rise - 0.12), (L, rise), (0.0, 0.0)], -width / 2, width / 2, walk_face, top=WHITE, bottom=WHITE)
    with m.frame((shore[0], shore[1], z_shore), d, nrm, Vector((0, 0, 1))):
        zz = lambda u: rise * u / L
        for s in (-1, 1):
            yy = s * (width / 2 - 0.05)
            yk = s * (width / 2 - 0.052)        # kick plate: inner face as before, outer face 4 mm inside the deck edge
            m.beam((0.0, yk, 0.06), (L, yk, rise + 0.06), 0.096, 0.12, WHITE)
            m.beam((0.0, yy, 1.0), (L, yy, rise + 1.0), 0.06, 0.06, WHITE)
            m.beam((0.0, yy, 0.5), (L, yy, rise + 0.5), 0.04, 0.04, WHITE)
            n = max(2, round(L / 0.55))
            for k in range(n + 1):
                u = L * k / n
                m.beam((u, yy, zz(u)), (u, yy, zz(u) + 1.0), 0.05, 0.05, WHITE)
        # The hinge barrel on the shore end, and the lip resting on the ship's landing plate.
        m.tube([(0.0, -width / 2 + 0.006, -0.06), (0.0, width / 2 - 0.006, -0.06)], 0.07, IRON, n=8)   # ends 6 mm in
        m.prism(F.rect(L - 0.05, -width / 2 + 0.1, L + HULL_GAP + LIP, width / 2 - 0.1), rise - LIP_T, rise, IRON)
    end = Vector((shore[0], shore[1], 0)) + d * (L + HULL_GAP + LIP)
    W = lambda u, v, z: (shore[0] + d.x * u + nrm.x * v, shore[1] + d.y * u + nrm.y * v, z)
    col([W(u, v, z_shore + rise * u / L + dz) for u in (0.0, L) for v in (-width / 2, width / 2) for dz in (-0.12, 0.0)])
    col([W(u, v, z_end + dz) for u in (L, L + HULL_GAP + LIP) for v in (-width / 2 + 0.1, width / 2 - 0.1) for dz in (-LIP_T, 0.0)])
    for s in (-1, 1):
        col_seg(W(0.0, s * (width / 2 - 0.05), 0)[:2], W(L, s * (width / 2 - 0.05), 0)[:2], 0.1, z_shore, z_end + 1.0)
    BROW_COL.extend(COL[first_collision:])
    del COL[first_collision:]
    return {'from': [round(shore[0], 3), round(shore[1], 3), round(z_shore, 3)], 'to': [round(end.x, 3), round(end.y, 3), round(z_end, 3)],
            'width': width, 'clear_width': round(width - 0.2, 3), 'rise': round(rise, 3), 'lip_on_plate_z': round(PLATE_TOP + LIP_GAP, 4)}


def timetable(m, x, y, z, yaw, w=2.4, h=1.7):
    """Timetable notice board on two posts with a small kawara hood and two lamps, as in concept v2."""
    with m.at((x, y, z), yaw):
        post_width = 0.2
        for s in (-1, 1):
            post(m, s * (w / 2 + post_width / 2 - SINK), 0, 0.0, 3.2, s=post_width, mat=TIMBER_DARK, footing=True)
        m.box((0, 0, 1.0 + h / 2), (w, 0.08, h), TIMBER_DARK)
        m.box((0, -0.05, 1.0 + h / 2), (w - 0.16, 0.04, h - 0.16), PAPER)
        m.box((0, 0, 3.05), (w + 0.7, 0.5, 0.12), TIMBER_DARK)
        with m.at((0, 0, 0)):
            gable_roof(m, -w / 2 - 0.25, -0.25, w / 2 + 0.25, 0.25, 3.12, 0.5, over=(0.15, 0.15, 0.3, 0.3), t=0.08, ribs=True)
        for s in (-1, 1):
            m.beam((s * 0.7, -0.05, 3.0), (s * 0.7, -0.35, 2.9), 0.04, 0.04, IRON)
            lantern(m, s * 0.7, -0.38, 2.55, h=0.3)


# ------------------------------------------------------------------ Hidamari (world metres)
def hidamari():
    return FS.HD.assemble(types.SimpleNamespace(**globals()))


# ------------------------------------------------------------------ Brinecove (region-local metres)
def brinecove():
    return FS.BC.assemble(types.SimpleNamespace(**globals()))


# ------------------------------------------------------------------ audit, export
SHIP_PARTS = ('hull', 'superstructure', 'funnel', 'lifeboats', 'rails', 'masts', 'fittings')
CLOSE_PARTS = {'FT_HD_Jetty': 'fenders', 'FT_HD_Brow': 'brow', 'FT_BC_Fenders': 'fenders', 'FT_BC_Brow': 'brow'}


def context_ground(name, route):
    """Audit-only ground (not exported): the exported world's own triangles (world_probe.py: ground and solids) within
    3 m of the route, less the world cuts site.json records for B3. Returns the mesh and each cut with what it removed
    in this audit (whole triangles; the world change splits them at the cut's x span)."""
    w = FS.load_world(name)
    tris = np.concatenate([w['ground'], w['solid']])
    xs = [p[0] for p in route]; ys = [p[1] for p in route]
    lo, hi = tris.min(1), tris.max(1)
    keep = (hi[:, 0] >= min(xs) - 3) & (lo[:, 0] <= max(xs) + 3) & (hi[:, 1] >= min(ys) - 3) & (lo[:, 1] <= max(ys) + 3)
    cuts = []
    for c in SITE[name]['berth']['world_cuts']:
        cut = keep & FS.cut_mask(tris, c)
        span = [round(float(lo[cut, 0].min()), 2), round(float(hi[cut, 0].max()), 2)] if cut.any() else None
        cuts.append({**c, 'audit_triangles_removed': int(cut.sum()), 'audit_removed_x_span': span})
        keep &= ~cut
    m = bpy.data.meshes.new('ctx_' + name); t = tris[keep]
    m.from_pydata(t.reshape(-1, 3).tolist(), [], [[3 * k, 3 * k + 1, 3 * k + 2] for k in range(len(t))])
    return m, cuts


def world_near(name, pts, margin=2.0):
    """The exported world's triangles (ground and solids) within margin of the given plan points, less the world cuts
    B3 makes: what carries the terminal's fittings in game."""
    w = FS.load_world(name)
    tris = np.concatenate([w['ground'], w['solid']])
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    lo, hi = tris.min(1), tris.max(1)
    keep = (hi[:, 0] >= min(xs) - margin) & (lo[:, 0] <= max(xs) + margin) & (hi[:, 1] >= min(ys) - margin) & (lo[:, 1] <= max(ys) + margin)
    for c in SITE[name]['berth']['world_cuts']:
        keep &= ~FS.cut_mask(tris, c)
    return tris[keep].tolist()


def ship_meshes(mats):
    """Ship C's render meshes in its own frame (audit only, never exported here)."""
    out = []
    for part in SHIP_PARTS:
        m = F.Mesh('FY_' + part.title()); getattr(F, part)(m); F.check(m)
        obj, _ = F.to_object(m, mats); obj.hide_render = True
        for c in list(obj.users_collection):
            c.objects.unlink(obj)
        out.append(obj)
    return out


def ship_at(ship, berth, coll):
    """Linked copies of the ship's meshes at a berth pose (waterline at z 0 in both frames)."""
    M = Matrix.Translation((berth['centre'][0], berth['centre'][1], 0.0)) @ Matrix.Rotation(math.radians(berth['heading_deg']), 4, 'Z')
    objs = []
    for o in ship:
        c = o.copy(); c.matrix_world = M; coll.objects.link(c); objs.append(c)
    return objs


def _bvh(o):
    from mathutils.bvhtree import BVHTree
    deps = bpy.context.evaluated_depsgraph_get(); me = o.evaluated_get(deps).to_mesh()
    verts = [o.matrix_world @ v.co for v in me.vertices]; polys = [list(p.vertices) for p in me.polygons]
    return BVHTree.FromPolygons(verts, polys), verts


def _inside(bvh, v):
    for d in (Vector((0, 0, 1)), Vector((0, 0, -1))):
        h = bvh.ray_cast(v + d * 1e-4, d, 50.0)
        if h[0] is None or h[1].dot(d) <= 0.0:
            return False
    return True


def ship_clash(terminal, ship):
    """Ship against terminal in 3D: every terminal mesh's triangles against every ship mesh's (BVH overlap), and the
    least vertex-to-surface gap of the parts meant to come close (fenders, brow)."""
    bpy.context.view_layer.update()
    ships = []
    for o in ship:
        bs, sv = _bvh(o)
        lo = Vector([min(v[i] for v in sv) for i in range(3)]); hi = Vector([max(v[i] for v in sv) for i in range(3)])
        ships.append((o.name.split('.')[0], bs, lo, hi))
    clashes, gaps = [], {}
    for t in terminal:
        bt, verts = _bvh(t)
        name = t.name.split('.')[0]
        for sname, bs, lo, hi in ships:
            pairs = bt.overlap(bs)
            if pairs:
                clashes.append({'terminal': name, 'ship': sname, 'triangle_pairs': len(pairs)})
            # A part wholly inside the ship meets no triangle: a vertex that sees the inside of the ship's closed solids
            # both up and down is inside.
            buried = sum(1 for v in verts if all(lo[i] <= v[i] <= hi[i] for i in range(3)) and _inside(bs, v))
            if buried:
                clashes.append({'terminal': name, 'ship': sname, 'vertices_inside': buried})
        if name in CLOSE_PARTS:
            best = (99.0, None, None)
            for sname, bs, _, _ in ships:
                for v in verts:
                    hit = bs.find_nearest(v, 2.0)
                    if hit[0] is not None and hit[3] < best[0]:
                        best = (hit[3], sname, [round(c, 3) for c in v])
            gaps[name] = {'part': CLOSE_PARTS[name], 'min_gap_m': round(best[0], 4), 'to': best[1], 'at': best[2]}
    return {'clashes': clashes, 'close_gaps': gaps, 'pass': not clashes}


def walk_audit(objs, walk):
    """walkcheck.audit over a BVH of the given objects (kit, exported world around the route, ship at its berth)."""
    from mathutils.bvhtree import BVHTree
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    verts, polys = [], []
    for o in objs:
        me = o.evaluated_get(deps).to_mesh(); base = len(verts)
        verts += [o.matrix_world @ v.co for v in me.vertices]; polys += [[base + i for i in p.vertices] for p in me.polygons]
    bvh = BVHTree.FromPolygons(verts, polys)

    def cast(o, d, dist):
        h = bvh.ray_cast(Vector(o), Vector(d), dist)
        return tuple(h[0]) if h[0] is not None else None
    audit = WC.audit(walk['route'], cast)
    audit['gate_sill'] = round(SILL, 3)
    return audit


def fbx(path, objs, smooth='EDGE'):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    from atelier.blender.fbx import export_fbx as export_scene_fbx
    export_scene_fbx(filepath=str(path), use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
                             axis_forward='-Y', axis_up='Z', object_types={'MESH'}, mesh_smooth_type=smooth, bake_anim=False,
                             use_custom_props=False)


def export(meshes, anchor, mats, objs_out):
    report = {}
    for name, m in meshes.items():
        m.verts[:] = [(x - anchor[0], y - anchor[1], z - anchor[2]) for x, y, z in m.verts]
        rep = F.check(m)
        obj, names = F.to_object(m, mats)
        tris = sum(len(f) - 2 for f in m.faces)
        report[name] = {'triangles': tris, 'materials': names, **rep}
        print(f'{name}: {tris} triangles, {rep}')
        hulls = collision_objects(name, anchor, BROW_COL) if name.endswith('_Brow') else []
        fbx(OUT / 'assets' / f'{name}.fbx', [obj, *hulls])
        remove_objects(hulls)
        obj.location = anchor
        objs_out.append(obj)
    return report


def collision_objects(name, anchor, proxies):
    """UCX hulls for a named fixed or moving mesh, from the same authored proxies."""
    import bmesh
    objs = []
    for i, pts in enumerate(proxies):
        bm = bmesh.new()
        for p in pts:
            bm.verts.new((p[0] - anchor[0], p[1] - anchor[1], p[2] - anchor[2]))
        bmesh.ops.convex_hull(bm, input=bm.verts)
        for v in [v for v in bm.verts if not v.link_faces]:
            bm.verts.remove(v)
        cm = bpy.data.meshes.new(f'UCX_{name}_{i:03d}'); bm.to_mesh(cm); bm.free()
        if len(cm.polygons) < 4:
            raise SystemExit(f'{cm.name}: degenerate collision hull')
        obj = bpy.data.objects.new(cm.name, cm)
        bpy.context.scene.collection.objects.link(obj)
        objs.append(obj)
    return objs


def remove_objects(objects):
    for obj in objects:
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(data)


def export_collision(prefix, anchor):
    """Fixed collision only: the brow's hulls move with its render mesh."""
    name = prefix + '_Collision'
    me = bpy.data.meshes.new(name); size = 0.05
    me.from_pydata([(x * size, y * size, z * size - 2.0) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], [],
                  [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]])
    obj = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(obj)
    objs = [obj, *collision_objects(name, anchor, COL)]
    fbx(OUT / 'assets' / f'{name}.fbx', objs, smooth='FACE')
    remove_objects(objs)
    return len(COL)


def code_sources():
    paths = (HERE / 'build.py', HERE / 'walkcheck.py', HERE / 'site.py', Path(FS.HD.__file__), Path(FS.BC.__file__),
             FS.REPO / 'games/yorimichi/world/solid_mesh.py', HERE.parent / 'build.py')
    return {str(p.relative_to(FS.REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def main():
    (OUT / 'assets').mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats = F.make_materials()
    ship = ship_meshes(mats)
    manifest = {'sources': code_sources(), 'materials': F.MATERIALS, 'units': 'metres, z up; Hidamari in world metres, Brinecove region-local', 'sill_z': SILL,
                'site_inputs': SITE['inputs'], 'limits': {'step_max': WC.STEP_MAX, 'headroom_min': WC.HEADROOM_MIN,
                                                          'width_min': WC.WIDTH_MIN, 'capsule_radius': WC.RADIUS},
                'terminals': {}}
    walks = {}
    # The seat, coplanar and carried-by audits first prove on known cases that they still catch what they are for.
    fixtures = F.SM.audit_fixtures(); manifest['audit_fixtures'] = fixtures
    failures = [f'audit fixture misjudged: {r["case"]} expected {r["expect"]}, got {r["got"]}' for r in fixtures if not r['ok']]
    print('audit fixtures', sum(r['ok'] for r in fixtures), 'of', len(fixtures), 'judged right')
    for name, fn, prefix in (('hidamari', hidamari, 'FT_HD'), ('brinecove', brinecove, 'FT_BC')):
        COL.clear(); BROW_COL.clear()
        meshes, walk = fn()
        objs = []
        # Fittings stand on the kit or the exported ground (seat rule), and no two parts share a visible face. In the
        # build frame, before export moves the kit to its anchor.
        kit = list(meshes.values()); bases = [s_['at'] for m in kit for s_ in m.seats]
        seat_rows, seat_bad = F.SM.seat_failures(kit, world_near(name, bases) if bases else ())
        n_cop, cop = F.SM.coplanar_overlaps(kit, limit=400)
        seats = {'count': len(seat_rows), 'failures': seat_bad, 'rule': {'gap_max_m': F.SM.SEAT_GAP, 'slack_m': F.SM.SEAT_SLACK}}
        coplanar = {'count': n_cop, 'samples': cop}
        # Every loose part is carried, through parts it touches, by the exported world (never by the ship).
        xs = [v[0] for m in kit for v in m.verts]; ys = [v[1] for m in kit for v in m.verts]
        c_sum, c_bad = F.SM.carried_failures(kit, world_near(name, [(min(xs), min(ys)), (max(xs), max(ys))]))
        carried = {**c_sum, 'failures': c_bad, 'rule': {'touch_m': F.SM.CARRY_TOUCH, 'carrier': 'exported world, less world cuts'}}
        coll = bpy.data.collections.new(name); bpy.context.scene.collection.children.link(coll)
        rep = export(meshes, walk['anchor'], mats, objs)
        hulls = export_collision(prefix, walk['anchor'])
        for o in objs:
            for c in o.users_collection:
                c.objects.unlink(o)
            coll.objects.link(o)
        cme, cuts = context_ground(name, walk['route']); cobj = bpy.data.objects.new(cme.name, cme); coll.objects.link(cobj)
        cobj.hide_render = True
        moored = ship_at(ship, SITE[name]['berth'], coll)
        clash = ship_clash(objs, moored)
        audit = walk_audit(objs + [cobj] + moored, walk)
        walks[name] = {**walk, 'audit': audit, 'ship_clash': clash, 'world_cuts_pending': cuts, 'seats': seats, 'coplanar': coplanar,
                       'carried': carried}
        manifest['terminals'][name] = {'anchor': walk['anchor'], 'frame': walk['frame'], 'meshes': rep, 'stair': walk['stair'],
                                       'brow': walk['brow'], 'board': walk['board'], 'gate': walk['gate'], 'walk': audit, 'ship_clash': clash,
                                       'world_cuts_pending': cuts, 'seats': seats, 'coplanar': coplanar, 'carried': carried,
                                       'collision': {'file': f'assets/{prefix}_Collision.fbx', 'convex_hulls': hulls, 'brow_convex_hulls': len(BROW_COL)},
                                       'triangles': sum(v['triangles'] for v in rep.values())}
        print(name, 'walk audit', audit)
        print(name, 'ship clash', clash)
        failures += [f'{name}: open edges in {n}' for n, v in rep.items() if v['open_edges']]
        failures += [f'{name}: walk audit failed'] * (not audit['pass'])
        failures += [f'{name}: {c["terminal"]} meets {c["ship"]} ({c})' for c in clash['clashes']]
        failures += [f'{name}: {r["label"]} in {r["mesh"]} {r["status"]} at {r["at"]} (gap {r.get("gap_m")})' for r in seat_bad]
        failures += [f'{name}: {n_cop} coplanar overlapping faces, e.g. {c["parts"]} at {c["at"]}' for c in cop[:8]] if n_cop else []
        failures += [f'{name}: {g["islands"]} uncarried parts ({", ".join(g["lines"][:6])}), nearest {g["nearest"]} '
                     f'{g["nearest_gap_m"]} m at {g["nearest_at"]}' for g in c_bad]
        print(name, 'seats', len(seat_rows), 'failures', len(seat_bad), 'coplanar', n_cop, 'carried', c_sum)
    manifest['failures'] = failures
    (OUT / 'walk.json').write_text(json.dumps(walks, indent=1) + '\n')
    manifest['files'] = {str(p.relative_to(OUT)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in [*(OUT / 'assets').glob('FT_*.fbx'), OUT / 'walk.json']}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=1) + '\n')
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'terminals.blend'))
    for f in failures:
        print('FAIL', f)
    print('TERMINALS BUILD', 'FAIL' if failures else 'PASS')
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
