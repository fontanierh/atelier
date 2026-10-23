"""Assemble Brinecove as nine separate collections, then hand them to the Blender exporter."""
import functools
import json
import math
import random
from pathlib import Path
from brinecove import falls
from brinecove import landmarks as LM
from brinecove import layout as L
from brinecove import rocks
from brinecove.geom import Builder, _surface_scale as surface_scale
from brinecove.kit import (awning, balcony, banana, barrel, bench, bollard, building, bush, crate, door,
                 fern, fish_crate, grass_tuft, lantern_post, laundry_line, local,
                 goods, jungle_tree, market_stall, palm, parasol, pennants, potted_plant, rowboat, sack, sign,
                 vine, window)

TAU = math.pi * 2
RNG = random.Random(49157)
from brinecove.paths import MODELS as ASSETS
HAS_STATUE = (ASSETS / 'pirate-queen-statue.glb').exists()
HAS_FIGUREHEAD = (ASSETS / 'galleon-figurehead.glb').exists()
HAS_WHEEL = (ASSETS / 'ships-wheel.glb').exists()
# The Tripo hero hull (galleon_hull.py) replaces the lofted hull; the rig stays procedural.
HAS_HULL = (ASSETS / 'galleon-hull.glb').exists()
HULL = (json.loads((ASSETS / 'galleon-hull.provenance.json').read_text())['processing']
        if HAS_HULL else None)


def cell_material(a, bb, c, d, gx, gy, sl, i, j):
    """Material for one ground cell from its corners, centre (local metres) and slope."""
    zavg = (a[2] + bb[2] + c[2] + d[2]) / 4
    # A cell that straddles the waterline at a cliff toe must not paint seabed above the sea.
    dry = max(a[2], bb[2], c[2], d[2]) > 0.8
    if zavg < 0.15 and not dry:
        return 'seabed'
    if zavg < 2.2:
        return 'terrain'
    if L.is_water(gx, gy):
        return 'terrain' if dry else 'seabed'
    if L.in_gorge(gx, gy, 3.0):
        if sl > 0.45:
            return 'rock' if falls_cliff(gx, gy, zavg) else 'terrain'
        return 'seabed'
    if sl < 0.4 and L.town_floor(gx, gy):
        return yard_material(gx, gy)
    if falls_cliff(gx, gy, zavg) and (sl > 0.3 or max(a[2], bb[2], c[2], d[2]) - min(a[2], bb[2], c[2], d[2]) > 1.6):
        return 'rock'
    return rocks.terrain_material(gx, gy, zavg, sl, i, j)


@functools.lru_cache(maxsize=1)
def _falls_zone():
    g = L.gorge_levels()
    return g['lower'] - 45.0, g['upper'] + 8.0, g['pool'] + 14.0


def falls_cliff(x, y, z):
    """The sea cliff that frames the waterfall, below the ledge shelf: its jagged 4 m ground cells stood out of the
    rock outcrops as flat meadow-green triangles (note 9 second review), so they take the rock layer alone."""
    x0, x1, top = _falls_zone()
    return x0 <= x <= x1 and abs(y - L.GORGE_Y) < 75.0 and z < top


def yard_material(x, y):
    """Beaten earth and old setts between the houses and the paved streets, never a lawn."""
    n = rocks.fbm(x, y, 18.0, 3, 41)
    return 'cobble_dark' if n > 0.58 else 'earth'


def ground_face(b, a, bb, c, d, mat, gx, gy, sl):
    """Two ground triangles. They project straight down: per-face box projection flips axis between neighbouring
    triangles on 45-degree slopes, which painted the hills as a diamond checkerboard. Cliffs instead project onto
    the vertical plane along their smoothed contour, which turns slowly enough to stay continuous; straight down,
    a cliff's texture smeared into vertical streaks."""
    k = 1.0 / max(0.05, surface_scale(mat))
    if sl > 1.1:
        ux, uy, _ = rocks.uphill(gx, gy, 14.0)
        uv = lambda p: ((p[0] * -uy + p[1] * ux) * k, p[2] * k)  # noqa: E731
    else:
        uv = lambda p: (p[0] * k, p[1] * k)  # noqa: E731
    b.face((a, bb, c), mat, [uv(a), uv(bb), uv(c)])
    b.face((a, c, d), mat, [uv(a), uv(c), uv(d)])


def terrain(hills=True):
    from brinecove.ground import jag_point
    b = Builder('01_terrain')
    nx, ny = 600, 480
    dx = (L.VIEW_X_MAX - L.VIEW_X_MIN) / nx
    dy = (L.VIEW_Y_MAX - L.VIEW_Y_MIN) / ny
    zs = [[L.ground(L.VIEW_X_MIN + i * dx, L.VIEW_Y_MIN + j * dy) for j in range(ny + 1)] for i in range(nx + 1)]
    for i in range(nx):
        for j in range(ny):
            x0 = L.VIEW_X_MIN + i * dx; x1 = x0 + dx
            y0 = L.VIEW_Y_MIN + j * dy; y1 = y0 + dy
            a = (x0, y0, zs[i][j]); bb = (x1, y0, zs[i + 1][j])
            c = (x1, y1, zs[i + 1][j + 1]); d = (x0, y1, zs[i][j + 1])
            # Break the sampled heightfield on steep faces (see ground.jag_point).
            a, bb, c, d = (jag_point(a), jag_point(bb), jag_point(c), jag_point(d))
            gx = (x0 + x1) / 2; gy = (y0 + y1) / 2
            sl = L.slope(gx, gy)
            ground_face(b, a, bb, c, d, cell_material(a, bb, c, d, gx, gy, sl, i, j), gx, gy, sl)
    terrain_dressing(b, hills)
    return b


def terrain_dressing(b, hills=True):
    """Rock shelves, crags, the statue islet, foam and (for the review scene only) the distant domed hills."""
    # Angular coastal rock shelves break up the sampled heightfield edge.
    rock_points = []
    for y in range(-620, 61, 26):
        hw = L.bay_half(y)
        for side in (-1, 1):
            x = side * (hw + RNG.uniform(1, 12))
            rock_points.append((x, y + RNG.uniform(-8, 8), L.height(x, y), RNG.uniform(3.5, 8.5)))
    for x, y, z, r in rock_points:
        rock_cluster(b, x, y, z - 1.0, r, RNG.randint(2, 4))
    crag_rng = random.Random(3307)
    for x, y, _, r in L.SEA_STACKS:
        rocks.crag(b, x, y, -3.0, r * crag_rng.uniform(1.1, 1.8), r, crag_rng, 7)
        foam_ring(b, x, y, r * 1.05, 16)
    # Broken rock shelves on both headlands keep the cliff silhouette from
    # reading as one smooth sampled surface.
    for side in (-1, 1):
        for _ in range(120):
            x = side * RNG.uniform(420, 790)
            y = RNG.uniform(-220, 470)
            if L.is_water(x, y) or L.slope(x, y) < 0.45:
                continue
            z = L.height(x, y)
            if z < 4.0:
                continue
            rock_cluster(b, x, y, z - 1.2, RNG.uniform(2.0, 6.0), RNG.randint(1, 3))
        # Ferns and dry grass on the steep ground between the outcrops. Thin ledge beams and spikes used to stand
        # here; drawn across uneven slopes they floated and crossed each other (playtest note 2).
        for _ in range(500):
            x = side * RNG.uniform(420, 800)
            y = RNG.uniform(-260, 520)
            if L.is_water(x, y) or L.slope(x, y) < 0.55 or L.height(x, y) < 5.0:
                continue
            if RNG.random() < 0.5:
                bush(b, x, y, L.height(x, y) - 0.2, 0.0, RNG.uniform(0.35, 0.75), RNG)
            else:
                grass_tuft(b, x, y, L.height(x, y) - 0.05, RNG.uniform(0, 360), RNG.uniform(0.6, 1.2), RNG)
    # Tiered bedded outcrops dress every steep face (rocks.py).
    rocks.cliff_rocks(b, random.Random(6113))
    # The statue islet: a craggy spire whose core top is the statue's plinth.
    rock_cluster(b, L.STATUE[0], L.STATUE[1], -2.5, 16.0, 6, tall=False)
    rocks.crag(b, L.STATUE[0], L.STATUE[1], -3.0, 12.0, 15.0, random.Random(911), 11)
    b.cylinder((L.STATUE[0], L.STATUE[1], 10.5), (L.STATUE[0], L.STATUE[1], 12.2), 5.2, 'rock_light', 9,
               radius_b=4.6)
    for i in range(5):
        b.sphere((L.STATUE[0] + RNG.uniform(-7, 7), L.STATUE[1] + RNG.uniform(-7, 7),
                  RNG.uniform(1, 10)), RNG.uniform(1.0, 2.6), 'rock_light' if i % 2 else 'rock',
                 (1.2, 1.0, 0.8), subdiv=0)
    foam_ring(b, L.STATUE[0], L.STATUE[1], 17.5, 20)
    shoreline_foam(b)
    shore_foam(b)
    if not hills:
        return b
    # Distant forested hills, low and rounded so they frame rather than
    # dominate the cove. Several overlapping domes make each ridge. The game has its own far hills.
    hill_rng = random.Random(7741)
    for x, y, r, mat in [
        (-720, 640, 210, 'jungle_dark'), (-470, 700, 240, 'jungle_dark'),
        (-210, 740, 220, 'jungle'), (60, 720, 250, 'jungle_dark'),
        (330, 690, 230, 'jungle'), (590, 650, 205, 'jungle_dark'),
        (-880, 240, 210, 'rock'), (890, 260, 220, 'rock'),
        (-870, -30, 180, 'jungle_dark'), (880, -10, 190, 'jungle_dark'),
    ]:
        b.sphere((x, y, -5), r, mat, (1.35, 1.0, 0.27), subdiv=1)
        b.sphere((x + r * 0.55, y + r * 0.2, -5), r * 0.72, mat, (1.2, 1.0, 0.24), subdiv=1)
        if mat != 'rock':
            rocks.canopy_hill(b, x, y, r, 1.35, 0.27, hill_rng)
            rocks.canopy_hill(b, x + r * 0.55, y + r * 0.2, r * 0.72, 1.2, 0.24, hill_rng)
    return b


def foam_ring(b, x, y, radius, segments=14):
    """A broken collar of animated foam around a rock or islet: v runs 0 at the rock to 1 offshore."""
    falls.foam_ring(b, x, y, 0.07, radius * 0.72, radius * 1.18, random.Random(int(x * 7 + y * 13)), segments)


def shoreline_foam(b):
    for y in range(-560, 56, 13):
        hw = L.bay_half(y)
        for side in (-1, 1):
            x = side * (hw + 1.5)
            wobble = 2.2 * math.sin(y * 0.18 + side)
            b.quad((x + side * 3.0, y - 4.2, 0.04),
                   (x + side * (11.0 + wobble), y - 3.4, 0.03),
                   (x + side * (10.0 + wobble), y + 3.4, 0.03),
                   (x + side * 3.0, y + 4.2, 0.04), 'water_shallow')
            # Two broad shallow shelves fade the deep blue into the shore.
            b.quad((x + side * 8.0, y - 6.0, 0.02),
                   (x + side * (42.0 + wobble), y - 5.0, 0.01),
                   (x + side * (38.0 + wobble), y + 5.0, 0.01),
                   (x + side * 8.0, y + 6.0, 0.02), 'water_shallow')
            b.quad((x + side * 38.0, y - 6.0, 0.005),
                   (x + side * (82.0 + wobble), y - 5.0, 0.0),
                   (x + side * (78.0 + wobble), y + 5.0, 0.0),
                   (x + side * 38.0, y + 6.0, 0.005), 'water_mid')


def final_ground(x, y):
    """The ground the game builds (rocks.ground): foam must meet the real shoreline, which the collar moves."""
    return rocks.ground(x, y)


def shore_foam(b, step=3.0, width=3.4, level=0.05):
    """Animated foam hugging the real waterline: marching squares on the final ground at sea level, each crossing
    becoming a thin strip laid seaward (v 0 at the shore, 1 offshore), so foam only touches actual shore."""
    import brinecove.region as R
    x0, y0, x1, y1 = R.OUTER
    nx, ny = int((x1 - x0) / step), int((y1 - y0) / step)
    z = [[final_ground(x0 + i * step, y0 + j * step) - level for j in range(ny + 1)] for i in range(nx + 1)]
    count = 0
    for i in range(nx):
        for j in range(ny):
            c = ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))
            v = [z[a][bb] for a, bb in c]
            if min(v) > 0 or max(v) < 0 or max(v) - min(v) > 18.0:
                continue
            cx, cy = x0 + (i + 0.5) * step, y0 + (j + 0.5) * step
            if L.in_gorge(cx, cy, 4.0) or L.on_pier(cx, cy, 4.0) or L.town_floor(cx, cy, 2.0):
                continue
            cross = []
            for k in range(4):
                (ia, ja), (ib, jb) = c[k], c[(k + 1) % 4]
                za, zb = z[ia][ja], z[ib][jb]
                if (za > 0) != (zb > 0):
                    t = za / (za - zb)
                    cross.append((x0 + (ia + (ib - ia) * t) * step, y0 + (ja + (jb - ja) * t) * step))
            if len(cross) != 2:
                continue
            (ax, ay), (bx, by) = cross
            # Seaward is down the ground's gradient; steep cliff feet get a thinner collar.
            gx = (v[1] + v[2] - v[0] - v[3]) / (2 * step)
            gy = (v[2] + v[3] - v[0] - v[1]) / (2 * step)
            g = math.hypot(gx, gy)
            if g < 1e-4:
                continue
            sx, sy = -gx / g, -gy / g
            w = width / (1.0 + 0.6 * min(g, 3.0))
            pts = [(ax, ay, 0.07), (bx, by, 0.07), (bx + sx * w, by + sy * w, 0.06), (ax + sx * w, ay + sy * w, 0.06)]
            # Keep the strip's winding facing up.
            if (bx - ax) * (sy * w) - (by - ay) * (sx * w) < 0:
                pts = [pts[1], pts[0], pts[3], pts[2]]
            uv = [((p[0] + p[1]) / 4.0, 0.0 if k < 2 else 1.0) for k, p in enumerate(pts)]
            b.face(pts, 'foam', uv)
            count += 1
    return count


def rock_cluster(b, x, y, z, radius, count, tall=False):
    for i in range(count):
        ang = RNG.uniform(0, TAU)
        rr = RNG.uniform(0, radius * 0.75)
        px, py = x + math.cos(ang) * rr, y + math.sin(ang) * rr
        sx = RNG.uniform(0.55, 1.15) * radius
        sy = RNG.uniform(0.55, 1.15) * radius
        sz = RNG.uniform(0.55, 1.3) * radius * (1.8 if tall else 1.0)
        # Bedded, noise-eroded boulders half buried in the ground (rocks.boulder), never cut prisms.
        rocks.boulder(b, px, py, z + 1.0, (sx * 1.2, sy, sz), RNG, ('rock', 'rock_dark', 'rock_light')[i % 3])


def harbor():
    b = Builder('02_harbor')

    def run(half, y, z, sy, sz, mat):
        """A quay-long course from -half to half, broken where the shipyard slip cuts through the wall."""
        n0, n1 = LM.SLIP_NOTCH
        for x0, x1 in ((-half, n0), (n1, half)):
            b.box(((x0 + x1) / 2, y, z), (x1 - x0, sy, sz), mat)

    # Quay wall and its coping, seated on the wall top (it used to sit buried in the wall with its back edge proud).
    run(390, L.QUAY_Y, 0.35, 4.2, 9.4, 'stone')
    run(392, L.QUAY_Y + 1.15, 5.15, 1.9, 0.2, 'stone_light')
    # The seaward face needs a scale and rhythm of its own: a wet base,
    # horizontal courses and recessed arch-headed doors between the buttresses.
    # Everything on the face stays below the wall's top (0.35 + 9.4 / 2 = 5.05 m).
    run(390, L.QUAY_Y - 2.18, 0.75, 0.35, 1.5, 'stone_dark')
    for zz, mat in ((2.7, 'stone_light'), (3.95, 'stone')):
        run(390, L.QUAY_Y - 2.18, zz, 0.35, 0.28, mat)
    for x in range(-342, 343, 76):
        if abs(x) < 22:
            continue
        b.box((x, L.QUAY_Y - 2.28, 2.55), (8.2, 0.35, 4.5), 'stone_dark')
        b.box((x, L.QUAY_Y - 2.38, 4.6), (9.4, 0.45, 0.75), 'stone_light')
        b.box((x, L.QUAY_Y - 2.38, 2.25), (9.8, 0.45, 0.45), 'stone_light')
        b.box((x, L.QUAY_Y - 2.46, 2.25), (6.0, 0.28, 3.35), 'wood_dark')
        for dx in (-2.0, 0.0, 2.0):
            b.box((x + dx, L.QUAY_Y - 2.62, 2.25), (0.16, 0.12, 3.3), 'metal')
        # An iron mooring peg out of the face (its axis must have length).
        b.cylinder((x - 6.4, L.QUAY_Y - 2.2, 3.9), (x - 6.4, L.QUAY_Y - 2.75, 3.9), 0.18, 'metal', 8)
        # A stone arch header over the door instead of a square lintel.
        for k in range(7):
            a = math.pi * (k + 0.5) / 7
            b.box((x + math.cos(a) * 3.0, L.QUAY_Y - 2.58, 3.4 + math.sin(a) * 0.9),
                  (0.95, 0.36, 1.15), 'stone_light' if k % 2 else 'stone')
    for x in range(-390, 391, 38):
        b.box((x, L.QUAY_Y - 2.5, 0.4), (5.2, 2.4, 9.0), 'stone_light')
        b.cylinder((x, L.QUAY_Y - 3.9, 1.0), (x, L.QUAY_Y - 3.9, 1.0), 0.65, 'metal', 10)
    for x in range(-360, 361, 90):
        if x + 6 > LM.SLIP_NOTCH[0] and x - 6 < LM.SLIP_NOTCH[1]:
            continue
        b.box((x, L.QUAY_Y - 0.2, 5.2), (12, 1.2, 0.6), 'stone_dark')
    # The three piers, with piles down into the water.
    for name, px, y0, y1, width in L.PIERS:
        length = y0 - y1
        b.box((px, (y0 + y1) / 2, 4.9), (width, length, 0.7), 'wood_light')
        for yy in [y0 - 1.5 - i * 8 for i in range(int(length / 8) + 1)]:
            for side in (-1, 1):
                bx = px + side * (width / 2 - 1.0)
                b.cylinder((bx, yy, -4.5), (bx, yy, 5.0), 0.55, 'wood_dark', 7)
                b.beam((bx, yy, 0.5), (px, yy, 3.9), 0.25, 'wood_dark')
        for i in range(int(length / 9)):
            yy = y0 - 4 - i * 9
            b.box((px, yy, 5.28), (width - 0.4, 0.18, 0.08), 'wood_dark')
        # T-head on the main and east piers.
        if name in ('central', 'east'):
            tw = 40 if name == 'central' else 26
            b.box((px, y1 + 2, 4.9), (tw, 14, 0.7), 'wood_light')
            for xx in (-tw / 2 + 2, tw / 2 - 2):
                b.cylinder((px + xx, y1 - 3, -4.5), (px + xx, y1 - 3, 5.0), 0.6, 'wood_dark', 7)
        for i in range(max(2, int(length / 42))):
            yy = y0 - 14 - i * 42
            for side in (-1, 1):
                if i % 2:
                    bollard(b, px + side * (width / 2 - 1.2), yy, 5.3)
        lantern_post(b, px - width / 2 + 1.4, y1 + 3, 5.3, 3.0)
        lantern_post(b, px + width / 2 - 1.4, y0 - 16, 5.3, 3.0)
    # Quay promenade paving and steps into the water.
    # The promenade runs right up to the quay wall's back (y 62.1): a 2.9 m strip of bare ground between them
    # z-fought with the paving and showed as grass under the kerb (playtest notes 3 and 4). The wall's coping is the
    # seaward edge now.
    paving(b, -390.0, 390.0, 65.0, 107.0, z=4.745, tile=7.0, thick=0.25, kerbs=(False, False), seed=7)
    n0, n1 = LM.SLIP_NOTCH
    for x0, x1 in ((-390.0, n0), (n1, 390.0)):
        paving(b, x0, x1, L.QUAY_Y + 2.1, 65.0, z=4.745, tile=7.0, thick=0.25, kerbs=(False, False), seed=8)
        # Ground under the quay wall itself stays below the paving too: build.split clamps vertex by vertex, so a
        # ground triangle with one corner under the wall stood up past the paving edge as a grass wedge (note 3).
        FLAT_PAVING.append((x0, x1, L.QUAY_Y - 2.1, L.QUAY_Y + 2.1, 4.745 - 0.25))
    for x in (-130, 135):
        for i in range(6):
            b.box((x, L.QUAY_Y - 1.0 - i * 0.8, 4.3 - i * 0.7), (9.0, 0.9, 0.3), 'stone')
    # Palms in stone planters line the working quay, as in the harbor refs.
    for px, py in ((-330, 72), (-280, 96), (-180, 72), (-110, 96), (110, 96), (180, 72),
                   (280, 96), (330, 72), (-200, 96), (200, 96), (-300, 72), (300, 72)):
        pz = L.ground(px, py)
        b.cylinder((px, py, pz + 0.05), (px, py, pz + 1.0), 1.25, 'stone_light', 9, radius_b=0.95)
        b.cylinder((px, py, pz + 0.95), (px, py, pz + 1.08), 1.12, 'clay', 9)
        palm(b, px, py, pz + 1.05, RNG.uniform(0, 360), RNG.uniform(0.62, 0.82), RNG)
    # Fish market shed by the east pier.
    # Posts every 8 m carry eave plates and tie beams; the roof is a solid slab seated on the plates. Its single-sided
    # roof used to vanish from the street, leaving only two 36 m fascia beams floating overhead (playtest note 14).
    shed_x, shed_y = 305, 86
    for xx in range(-16, 17, 8):
        for yy in (-7, 7):
            b.beam((shed_x + xx, shed_y + yy, 5.0), (shed_x + xx, shed_y + yy, 11.0), 0.34, 'wood_dark')
            b.beam((shed_x + xx, shed_y + yy, 9.9), (shed_x + xx + (1.0 if xx < 16 else -1.0), shed_y + yy, 10.9),
                   0.16, 'wood_dark')
        b.beam((shed_x + xx, shed_y - 7, 10.8), (shed_x + xx, shed_y + 7, 10.8), 0.28, 'wood_dark')
    for yy in (-7, 7):
        b.beam((shed_x - 17, shed_y + yy, 10.85), (shed_x + 17, shed_y + yy, 10.85), 0.3, 'wood_dark')
    b.gable_roof((shed_x, shed_y, 11.0), 32, 14, 11.0, 3.0, 'roof_terra', 0, ridge='x', overhang=1.0)
    b.box((shed_x, shed_y - 2.0, 5.7), (30, 2.0, 1.2), 'wood_light')
    for i in range(6):
        b.box((shed_x - 12 + i * 4.8, shed_y - 2.3, 6.5), (2.2, 1.0, 0.5), 'sail_stripe' if i % 2 else 'cream')
    # Cargo cranes: a timber A-frame, jib, rope and a hanging crate.
    for cx, cy, ang in ((-334, 84, -22), (412, 128, 16)):
        b.beam((cx - 4, cy, 4.7), (cx, cy, 18.0), 0.5, 'wood_dark')
        b.beam((cx + 4, cy, 4.7), (cx, cy, 18.0), 0.5, 'wood_dark')
        b.beam((cx, cy, 15.0), (cx + math.cos(math.radians(ang)) * 16, cy + math.sin(math.radians(ang)) * 16, 17.5), 0.35, 'wood')
        b.rope((cx, cy, 17.0), (cx + math.cos(math.radians(ang)) * 14, cy + math.sin(math.radians(ang)) * 14, 9.5), 0.0, 0.06)
        crate(b, cx + math.cos(math.radians(ang)) * 14, cy + math.sin(math.radians(ang)) * 14, 7.8, 1.4)
    # Shipyard: the half-built hull on its cradle, the slip running into the sea, scaffold, crane and shed.
    LM.shipyard(b)
    for i in range(8):
        crate(b, 400 + RNG.uniform(-3, 3), 112 + i * 4.8, 4.7, RNG.uniform(0.8, 1.4), RNG.uniform(0, 90))
    for i in range(2):
        b.cylinder((408, 95 + i * 5, 4.7), (408, 95 + i * 5, 4.9), 2.4, 'wood_light', 10)
    # Cargo clusters along the working piers.
    for name, px, y0, y1, width in L.PIERS:
        for t, off in ((0.22, -4.2), (0.52, 3.4), (0.78, -2.6)):
            py = y0 + (y1 - y0) * t
            crate(b, px + off, py, 5.3, 0.9, RNG.uniform(0, 90))
            barrel(b, px + off + 1.5, py + 0.9, 5.3, 0.85)
            if t > 0.5:
                b.ring((px + off - 1.2, py - 1.0, 5.32), 0.55, 0.07, 'rope', sides=10)
    # Small boats give the open water scale and life.
    for x, y, yaw in ((-225, -40, -22), (-150, -90, -14), (-30, -150, 8), (100, -70, 35),
                      (180, -160, -8), (300, -60, 18), (-380, -40, -22), (420, -120, 12)):
        if L.is_water(x, y):
            rowboat(b, x, y, 0.0, yaw, 1.0)
    return b


def paving_material(x, y, seed=0):
    """Mostly cobble, with drifts of darker worn setts and patches of big flagstones, never a tile checkerboard."""
    n = rocks.fbm(x, y, 34.0, 3, 61 + seed)
    m = rocks.fbm(x, y, 13.0, 2, 83 + seed)
    if n < 0.3:
        return 'stone_light' if m > 0.45 else 'stone'
    if n > 0.7 or (n > 0.6 and m > 0.62):
        return 'cobble_dark'
    return 'cobble'


# Flat paved rectangles (x0, x1, y0, y1, underside): build.split keeps the ground below them, or the layout ground
# where it rises above a level quay pokes through the slabs as square sand patches (playtest notes 5 and 8).
FLAT_PAVING = []


def covered(rect, xa, xb, ya, yb):
    """Whether the rectangle [xa, xb] x [ya, yb] lies wholly inside rect (x0, x1, y0, y1)."""
    return rect is not None and rect[0] <= xa and xb <= rect[1] and rect[2] <= ya and yb <= rect[3]


def paving_grid(x0, x1, y0, y1, tile=6.5):
    """The slab grid paving() lays over a rectangle: (nx, ny, slab width, slab depth)."""
    nx, ny = max(1, round((x1 - x0) / tile)), max(1, round((y1 - y0) / tile))
    return nx, ny, (x1 - x0) / nx, (y1 - y0) / ny


def paving(b, x0, x1, y0, y1, z=None, tile=6.5, thick=0.22, kerbs=(True, True), seed=0, skip=None):
    """Tile a street rectangle in abutting slabs; z=None follows the ground per slab. Kerbs line the y edges.
    skip is a floor (x0, x1, y0, y1) laid by another module: only slabs and kerbs wholly under it are left out, so
    the street still meets that floor's edge instead of leaving bare ground beside it."""
    if z is not None and skip is None:
        FLAT_PAVING.append((min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1), z - thick))
    nx, ny, sx, sy = paving_grid(x0, x1, y0, y1, tile)
    for i in range(nx):
        cx = x0 + (i + 0.5) * sx
        for j in range(ny):
            cy = y0 + (j + 0.5) * sy
            if covered(skip, cx - sx / 2, cx + sx / 2, cy - sy / 2, cy + sy / 2):
                continue
            top = L.ground(cx, cy) + 0.16 if z is None else z
            b.box((cx, cy, top - thick / 2), (sx, sy, thick), paving_material(cx, cy, seed))
        for edge, on in zip((y0 + 0.25, y1 - 0.25), kerbs):
            if on and not covered(skip, cx - sx / 2, cx + sx / 2, edge - 0.85, edge + 0.85):
                top = L.ground(cx, edge) + 0.16 if z is None else z
                b.box((cx, edge, top + 0.06), (sx, 0.5, 0.36), 'stone_light')
                # A dark gutter of upright setts just inside the kerb.
                gy = edge + (0.6 if edge < (y0 + y1) / 2 else -0.6)
                b.box((cx, gy, top), (sx, 0.7, 0.06), 'cobble_dark')


# The market square's own cobble floor (market()); street bands leave out only what it covers.
MARKET_FLOOR = (-98.0, 98.0, 94.0, 226.0)


def pave_band(b, y0, y1, skip_market=True):
    """Pave a street band in terrain-following slabs with kerbs, leaving the market open."""
    paving(b, -372.0, 372.0, y0, y1, seed=int(y0),
           skip=MARKET_FLOOR if skip_market else None)
    # Planters and laundry break up the paved bands and tie them to the walls.
    for px in range(-350, 351, 44):
        if skip_market and -112 < px < 112 and y0 < 228.0:
            continue
        pz = L.ground(px, y0 + 2.2)
        b.box((px, y0 + 2.2, pz + 0.38), (3.8, 1.1, 0.75), 'stone_light')
        bush(b, px, y0 + 2.2, pz + 0.75, 0.0, 0.85, RNG)
    for lx in range(-330, 331, 92):
        if skip_market and -118 < lx < 118 and y0 < 228.0:
            continue
        ly = y0 + 4.0
        lz = L.ground(lx, ly)
        b.beam((lx, ly, lz), (lx, ly, lz + 5.4), 0.12, 'wood_dark')
        b.beam((lx + 24, ly + 5.0, lz), (lx + 24, ly + 5.0, lz + 5.4), 0.12, 'wood_dark')
        b.rope((lx, ly, lz + 5.0), (lx + 24, ly + 5.0, lz + 5.0), 0.5, 0.03)
        for k in range(3):
            qx = lx + 4 + k * 6.4
            b.panel((qx, ly + k * 1.25, lz + 4.95), (qx + 4.6, ly + k * 1.25, lz + 4.95),
                    (qx + 4.6, ly + k * 1.25, lz + 2.8), (qx, ly + k * 1.25, lz + 2.8),
                    ('canvas', 'canvas_red', 'canvas_teal')[k], thick=0.04)


# The lower town's terrain-following streets: side roads (centre x, centre y, width, depth) and full-width bands.
LOWER_ROADS = ((-260, 230, 34, 10), (240, 230, 34, 10), (-390, 120, 12, 58), (390, 120, 12, 58))
LOWER_BANDS = ((137, 179), (210, 242), (266, 282))


def lower_street_slabs():
    """Every terrain-following slab lower_town() lays, as (x0, x1, y0, y1, top): the same grid and skip as paving()."""
    if not _STREET_SLABS:
        rects = [(x - w / 2, x + w / 2, y - d / 2, y + d / 2, None) for x, y, w, d in LOWER_ROADS]
        rects += [(-372.0, 372.0, y0, y1, MARKET_FLOOR) for y0, y1 in LOWER_BANDS]
        for x0, x1, y0, y1, skip in rects:
            nx, ny, sx, sy = paving_grid(x0, x1, y0, y1)
            for i in range(nx):
                cx = x0 + (i + 0.5) * sx
                for j in range(ny):
                    cy = y0 + (j + 0.5) * sy
                    if not covered(skip, cx - sx / 2, cx + sx / 2, cy - sy / 2, cy + sy / 2):
                        _STREET_SLABS.append((cx - sx / 2, cx + sx / 2, cy - sy / 2, cy + sy / 2, L.ground(cx, cy) + 0.16))
    return _STREET_SLABS


_STREET_SLABS = []


def lower_town():
    b = Builder('03_town_lower')
    # Street surfaces, edges and lanes.
    for x, y, w, d in LOWER_ROADS:
        paving(b, x - w / 2, x + w / 2, y - d / 2, y + d / 2, kerbs=(False, False), seed=int(x))
    for y0, y1 in LOWER_BANDS:
        pave_band(b, y0, y1)
    # Lower quay houses and the two lanes behind them.
    for spec in L.DENSE_LOTS:
        if spec[2] < 280:
            if spec[0].startswith(('slope-', 'ridge-')):
                b.box((spec[1], spec[2], spec[3] - 2.1), (spec[4] + 1.0, spec[5] + 1.0, 4.2),
                      'stone', spec[9])
            if spec[0].startswith('slope-') and sum(map(ord, spec[0])) % 3 == 0:
                lx, ly = local(spec[1], spec[2], spec[9], -spec[4] / 2 - 0.7, spec[5] * 0.22)
                for dz in (0.0, 1.0):
                    b.beam((lx + dz, ly, spec[3]), (lx + dz, ly, spec[3] + 5.2), 0.10, 'wood_dark')
                for r in range(6):
                    b.beam((lx, ly, spec[3] + 0.8 + r * 0.75), (lx + 1.0, ly, spec[3] + 0.8 + r * 0.75),
                           0.06, 'wood')
            if spec[8] == 'shack':
                spec = (*spec[:3], L.ground(spec[1], spec[2]) + 0.1, *spec[4:])
            for sub in split_lot(spec, RNG):
                building(b, sub, RNG)
    # Stilt houses on the headland shores.
    for spec in L.SHORE_BUILDINGS:
        key, x, y, _, w, d, h, floors, style, yaw, roof = spec
        z = L.height(x, y) + 1.2
        b.box((x, y, z - 2.0), (w + 3.0, d + 3.0, 4.0), 'stone', yaw)
        for side in (-1, 1):
            px, py = local(x, y, yaw, side * (w * 0.36), 0)
            b.cylinder((px, py, z - 6.0), (px, py, z - 1.0), 0.35, 'wood_dark', 6)
        building(b, (key, x, y, z, w, d, h, floors, style, yaw, roof), RNG)
    # Timber walkways link the stilt houses along each headland.
    for side in (-1, 1):
        specs = sorted([s for s in L.SHORE_BUILDINGS if s[1] * side > 0], key=lambda s: s[2])
        for a, c in zip(specs, specs[1:]):
            ax, ay, az = a[1], a[2], L.height(a[1], a[2]) + 2.2
            cx, cy, cz = c[1], c[2], L.height(c[1], c[2]) + 2.2
            b.beam((ax, ay, az), (cx, cy, cz), 0.8, 'wood_light')
            for off in (-0.6, 0.6):
                b.rope((ax, ay + off, az + 1.0), (cx, cy + off, cz + 1.0), 1.4, 0.06)
    # Low garden walls, cisterns and a few steps at the terrace foot.
    for x in range(-360, 370, 46):
        y = 236
        if abs(x) < 30:
            continue
        b.box((x, y, L.ground(x, y) + 0.65), (34, 1.0, 1.3), 'stone')
        if x % 3 == 0:
            b.sphere((x + RNG.uniform(-8, 8), y + 3.5, L.ground(x, y) + 0.5), 1.1, 'jungle', (1.2, 1, 0.8), subdiv=0)
    # Bunting and working clutter along the waterfront lane: short local spans between pairs of posts, never one
    # line along the whole front (playtest note 14).
    for x in (-300, -150, 0, 150, 300):
        for k, run in enumerate((14.0, 11.0)):
            x0 = x - 16 + k * 22
            for xx in (x0, x0 + run):
                b.beam((xx, 96.5, L.ground(xx, 96.5)), (xx, 96.5, L.ground(xx, 96.5) + 6.2), 0.14, 'wood_dark')
            pennants(b, (x0, 96.5, L.ground(x0, 96.5) + 5.9), (x0 + run, 96.5, L.ground(x0 + run, 96.5) + 5.9), 0.6, 7)
    for x, y, yaw in ((-300, 91, 12), (-150, 91, -10), (0, 91, 8), (150, 91, -12), (300, 91, 10)):
        fish_crate(b, x, y, L.ground(x, y) + 0.1, yaw, 1.1)
    for x, y in ((-260, 166), (-90, 166), (60, 166), (220, 166)):
        potted_plant(b, x, y, L.ground(x, y) + 0.05, 0.75, RNG)
        sack(b, x + 1.4, y + 0.6, L.ground(x, y) + 0.1, 0.85)
    return b


def market():
    b = Builder('04_market')
    x0, x1, y0, y1 = MARKET_FLOOR
    b.box(((x0 + x1) / 2, (y0 + y1) / 2, 4.68), (x1 - x0, y1 - y0, 0.28), 'cobble')
    # A flagstone border and a grid of stone ribs divide the square into the paved bays of a piazza;
    # darker setts fill a few bays so the field never reads as one flat sheet.
    for cx, cy, sx, sy in ((0, 96.5, 196, 5), (0, 223.5, 196, 5), (-95.5, 160, 5, 132), (95.5, 160, 5, 132)):
        b.box((cx, cy, 4.83), (sx, sy, 0.06), 'stone_light')
    for gx in range(-84, 85, 12):
        b.box((gx, 160, 4.83), (0.7, 122, 0.06), 'stone_light')
    for gy in range(106, 215, 12):
        b.box((0, gy, 4.83), (186, 0.7, 0.06), 'stone_light')
    for gx in range(-84, 73, 12):
        for gy in range(106, 203, 12):
            if rocks.fbm(gx, gy, 30.0, 2, 17) > 0.62:
                b.box((gx + 6, gy + 6, 4.825), (11.3, 11.3, 0.05), 'cobble_dark')
    # Lantern posts at the square's front corners (their strings ran 184 m across the square: playtest note 14).
    for xx in (-92, 92):
        lantern_post(b, xx, 96, L.ground(xx, 96) + 0.1, 5.0)
    cloths = ('canvas', 'canvas_red', 'canvas_teal', 'canvas_gold', 'canvas_blue', 'canvas_green', 'canvas_red')
    for i, (x, y, w, d, cloth) in enumerate(L.MARKET_STALLS):
        # Loosen the grid: real market rows drift, turn and leave gaps.
        x += RNG.uniform(-2.5, 2.5)
        y += RNG.uniform(-2.0, 2.0)
        yaw = RNG.uniform(-16, 16)
        canvas = cloths[RNG.randrange(len(cloths))]
        market_stall(b, x, y, L.ground(x, y) + 0.1, w, d, canvas, yaw)
        barrel(b, x - w * 0.58, y + d * 0.25, L.ground(x, y) + 0.1, 0.72)
        crate(b, x + w * 0.55, y - d * 0.18, L.ground(x, y) + 0.1, 0.8, RNG.uniform(0, 90))
    # South-edge stalls frame the market camera and close the empty cobbles.
    for x, cloth in ((-76, 'canvas_red'), (58, 'canvas_teal')):
        y = 98
        market_stall(b, x, y, L.ground(x, y) + 0.1, 13, 8, cloth, -7 if x < 0 else 8)
    for x, y, cloth in ((-96, 108, 'canvas_red'), (96, 112, 'canvas_teal')):
        b.cylinder((x, y, L.ground(x, y) + 0.1), (x, y, L.ground(x, y) + 7.5), 0.12, 'wood_dark', 6)
        b.panel((x, y, L.ground(x, y) + 7.4), (x + 4.0, y, L.ground(x, y) + 6.8),
                (x + 4.0, y, L.ground(x, y) + 4.4), (x, y, L.ground(x, y) + 5.0), cloth, thick=0.04)
    for x, y in ((-70, 105), (-30, 105), (30, 105), (70, 105)):
        barrel(b, x, y, L.ground(x, y) + 0.1, 0.8)
        crate(b, x + 2.2, y + 1.2, L.ground(x, y) + 0.1, 0.8, 12)
    # Stone colonnades frame the square after the arcade concept (references/redesign/arcade.jpg): short groups of
    # square piers, each with its own lintel, a timber pergola on posts and a striped shade per bay. One 122 m
    # lintel and plank used to run the whole side into the terrace wall (playtest note 11).
    for side in (-1, 1):
        x = side * 96
        xi = x - side * 3.4
        for g, ys in enumerate(((108, 120, 132, 144), (158, 170, 182, 194), (206, 217))):
            gz = L.ground(x, (ys[0] + ys[-1]) / 2)
            top = gz + 4.9
            for y in ys:
                pz = L.ground(x, y)
                b.box((x, y, pz + 0.25), (1.15, 1.15, 0.5), 'stone')
                b.box((x, y, (pz + 0.5 + top - 0.6) / 2), (0.78, 0.78, top - 0.6 - pz - 0.5), 'stone_light')
                b.box((x, y, top - 0.45), (1.1, 1.1, 0.3), 'stone')
                b.beam((xi, y, L.ground(xi, y)), (xi, y, top - 0.25), 0.24, 'wood_dark')
                b.box((xi, y, L.ground(xi, y) + 0.12), (0.5, 0.5, 0.24), 'stone')
            b.box((x, (ys[0] + ys[-1]) / 2, top), (1.3, ys[-1] - ys[0] + 1.6, 0.6), 'stone_light')
            b.beam((xi, ys[0] - 0.7, top - 0.2), (xi, ys[-1] + 0.7, top - 0.2), 0.26, 'wood_dark')
            n = int((ys[-1] - ys[0]) / 1.5)
            for k in range(n + 1):
                y = ys[0] + (ys[-1] - ys[0]) * k / n
                b.beam((x + side * 0.9, y, top + 0.38), (xi - side * 0.6, y, top - 0.02), 0.14, 'wood_dark', 0.2)
            for k, (y0, y1) in enumerate(zip(ys, ys[1:])):
                b.panel((x + side * 0.4, y0 + 0.4, top + 0.5), (x + side * 0.4, y1 - 0.4, top + 0.5),
                        (xi - side * 0.3, y1 - 0.4, top + 0.12), (xi - side * 0.3, y0 + 0.4, top + 0.12),
                        ('canvas', 'canvas_teal', 'canvas_red')[(g + k) % 3], thick=0.05)
    # Lantern strings and a loose crowd make the open square read as a working
    # market rather than an empty plaza from the harbor camera.
    # Each string is a short local span between two posts, never one line across the whole square.
    for yy in (118, 168, 214):
        for x0, x1 in ((-89, -68), (-10, 10), (68, 89)):
            for xx in (x0, x1):
                lantern_post(b, xx, yy, L.ground(xx, yy) + 0.1, 5.5)
            za, zc = L.ground(x0, yy) + 5.6, L.ground(x1, yy) + 5.6
            b.rope((x0, yy, za), (x1, yy, zc), 0.6, 0.05)
            for k in range(1, 4):
                t = k / 4
                b.sphere((x0 + (x1 - x0) * t, yy, za + (zc - za) * t - 0.6 * math.sin(math.pi * t) - 0.3), 0.22,
                         'lantern', subdiv=1)
                b.beam((x0 + (x1 - x0) * t, yy, za + (zc - za) * t - 0.6 * math.sin(math.pi * t)),
                       (x0 + (x1 - x0) * t, yy, za + (zc - za) * t - 0.6 * math.sin(math.pi * t) - 0.1), 0.02, 'metal')
    # Handcarts, fish baskets and sack piles fill the lanes between stalls.
    for cx, cy, cyaw in ((-66, 150, 18), (66, 152, -24), (-52, 206, 8), (54, 204, -12)):
        cz = L.ground(cx, cy) + 0.1
        b.box((cx, cy, cz + 0.75), (4.2, 2.0, 0.35), 'wood_light', cyaw)
        for side in (-1, 1):
            wx, wy = local(cx, cy, cyaw, side * 1.45, 0.35)
            b.ring((wx, wy, cz + 0.45), 0.62, 0.16, 'wood_dark', axis='x', sides=10)
            b.cylinder((wx - 0.08, wy, cz + 0.45), (wx + 0.08, wy, cz + 0.45), 0.18, 'metal', 8)
        for k in range(3):
            crate(b, cx + RNG.uniform(-1.4, 1.4), cy + RNG.uniform(-0.7, 0.7), cz + 0.4,
                  RNG.uniform(0.45, 0.7), cyaw + RNG.uniform(-20, 20))
    for fx, fy in ((-78, 120), (76, 118), (-74, 224), (74, 222)):
        fz = L.ground(fx, fy) + 0.1
        b.cylinder((fx, fy, fz), (fx, fy, fz + 0.7), 0.7, 'wood', 10, radius_b=0.55)
        for k in range(5):
            b.sphere((fx + RNG.uniform(-0.5, 0.5), fy + RNG.uniform(-0.5, 0.5), fz + 0.75),
                     RNG.uniform(0.16, 0.26), 'sail', (1.3, 0.8, 0.7), subdiv=0)
    # Parasols, shade trees and paving rings break the square into rooms, as in the paintings' crowded markets.
    pair = (('canvas', 'canvas_red'), ('canvas', 'canvas_teal'), ('canvas_gold', 'canvas'), ('canvas_blue', 'canvas'),
            ('canvas_green', 'cream'), ('canvas_red', 'canvas_gold'))
    placed = 0
    for _ in range(400):
        if placed >= 34:
            break
        px, py = RNG.uniform(-86, 86), RNG.uniform(104, 222)
        if any(abs(px - sx) < sw / 2 + 3.2 and abs(py - sy) < sd / 2 + 3.2 for sx, sy, sw, sd, _ in L.MARKET_STALLS):
            continue
        if math.hypot(px - 0, py - 158) < 9 or math.hypot(px - 47, py - 137) < 6 or math.hypot(px + 44, py - 188) < 8:
            continue
        parasol(b, px, py, L.ground(px, py) + 0.1, RNG.uniform(2.2, 3.2), pair[RNG.randrange(len(pair))], RNG)
        placed += 1
    cz = L.ground(0, 158) + 0.1
    for r, mat in ((13.0, 'stone_light'), (12.4, 'cobble_dark'), (8.0, 'stone_light')):
        b.cylinder((0, 158, cz - 0.02), (0, 158, cz + 0.06), r, mat, 32)
    for k in range(8):
        a = TAU * k / 8
        b.box((math.cos(a) * 30, 158 + math.sin(a) * 30, cz + 0.04), (60, 0.5, 0.06), 'stone_light', math.degrees(a))
    for tx, ty in ((-60, 132), (60, 132), (-60, 196), (60, 196), (-24, 160), (24, 160)):
        tz = L.ground(tx, ty)
        b.cylinder((tx, ty, tz), (tx, ty, tz + 0.55), 2.3, 'stone_light', 12)
        b.cylinder((tx, ty, tz + 0.5), (tx, ty, tz + 0.6), 2.0, 'moss', 12)
        jungle_tree(b, tx, ty, tz + 0.5, RNG.uniform(0, 360), RNG.uniform(0.75, 0.95), RNG)
    # Potted palms soften the hard market edges and frame the two entrances.
    for px, py in ((-66, 102), (66, 102), (-66, 214), (66, 214), (0, 102), (0, 212)):
        pz = L.ground(px, py)
        b.cylinder((px, py, pz + 0.1), (px, py, pz + 1.2), 1.1, 'clay', 9, radius_b=0.8)
        palm(b, px, py, pz + 1.1, RNG.uniform(0, 360), 0.62, RNG)
    # Signal mast, crossyard, rigging, bunting and a crow's nest.
    mx, my, mz = 0, 158, 4.9
    b.cylinder((mx, my, mz), (mx, my, mz + 23), 0.32, 'wood_dark', 8, radius_b=0.18)
    b.beam((mx - 6, my, mz + 18), (mx + 6, my, mz + 18), 0.28, 'wood')
    b.beam((mx, my, mz + 22.4), (mx + 9, my - 4, mz + 15.5), 0.16, 'wood')
    b.ring((mx, my, mz + 18.5), 1.2, 0.10, 'wood', axis='z', sides=10)
    for i in range(5):
        xx = -4.5 + i * 2.25
        b.panel((mx + xx, my, mz + 19.5), (mx + xx + 1.0, my, mz + 19.5),
                (mx + xx + 1.0, my, mz + 18.1), (mx + xx, my, mz + 18.1),
                ('flag_red', 'cream', 'roof_teal')[i % 3], thick=0.04)
    b.rope((mx, my, mz + 17), (mx - 18, my + 6, 9.0), 0.7, 0.05)
    b.rope((mx, my, mz + 17), (mx + 18, my - 6, 9.0), 0.7, 0.05)
    for i in range(7):
        xx = -15 + i * 5
        yy = my + 6 - (abs(xx) / 18) * 12
        b.panel((mx + xx, yy, 9.0 - (abs(xx) / 18) * 0.8), (mx + xx + 2.0, yy - 0.8, 8.8),
                (mx + xx + 2.0, yy - 0.8, 7.8), (mx + xx, yy, 8.0), ('flag_red', 'cream')[i % 2], thick=0.04)
    # Well.
    wx, wy = 47, 137
    b.cylinder((wx, wy, 4.8), (wx, wy, 6.1), 2.2, 'stone', 12)
    b.cylinder((wx, wy, 6.0), (wx, wy, 6.15), 2.35, 'water_deep', 12)
    for sx in (-1.5, 1.5):
        b.beam((wx + sx, wy, 6.0), (wx + sx, wy, 8.9), 0.16, 'wood_dark')
    b.gable_roof((wx, wy, 8.8), 4.6, 4.0, 8.8, 1.4, 'roof_terra', 0, ridge='x', overhang=0.4)
    # Auction block with steps and a small canopy.
    ax, ay = -44, 188
    b.box((ax, ay, 5.25), (8, 5, 1.0), 'wood_light')
    b.box((ax - 3.5, ay, 4.9), (2.8, 5.2, 0.4), 'stone')
    for sx in (-3.4, 3.4):
        for sy in (-2.1, 2.1):
            b.beam((ax + sx, ay + sy, 5.7), (ax + sx, ay + sy, 9.4), 0.16, 'wood_dark')
    b.gable_roof((ax, ay, 9.3), 9, 6.2, 9.3, 1.8, 'roof_teal', 0, ridge='x', overhang=0.5)
    # Benches, ropes and market clutter.
    for i in range(8):
        x = -82 + i * 23
        y = 210 if i % 2 else 106
        b.box((x, y, 5.2), (5.4, 1.1, 0.25), 'wood_light')
        for sx in (-2.2, 2.2):
            b.beam((x + sx, y, 4.4), (x + sx, y, 5.2), 0.14, 'wood_dark')
    # Bunting over the stalls and a thicker layer of working clutter.
    for y, z in ((118, 10.2), (160, 10.4), (205, 10.0)):
        pennants(b, (-88, y, z), (88, y, z), 1.1, 15)
    for x, y, yaw in ((-70, 150, 12), (-24, 208, -8), (52, 148, 18), (70, 206, -14)):
        fish_crate(b, x, y, L.ground(x, y) + 0.1, yaw, 1.1)
    for x, y in ((-58, 176), (-6, 122), (44, 190), (78, 156)):
        sack(b, x, y, L.ground(x, y) + 0.1, 1.0)
    for x, y in ((-88, 128), (88, 128), (-88, 198), (88, 198)):
        potted_plant(b, x, y, L.ground(x, y) + 0.1, 0.8, RNG)
    # Break up the open foreground of the market camera with a working cluster.
    for x, y, yaw in ((-26, 128, 8), (24, 134, -12), (-42, 120, 0), (38, 120, 20)):
        fish_crate(b, x, y, L.ground(x, y) + 0.1, yaw, 1.05)
        sack(b, x + 1.5, y + 0.7, L.ground(x, y) + 0.1, 0.9)
    potted_plant(b, 0, 124, L.ground(0, 124) + 0.1, 0.9, RNG)
    # A low line of goods and bunting fills the market camera's foreground.
    for x, y, yaw in ((-16, 120, 6), (-6, 118, -10), (6, 121, 12), (16, 119, -4)):
        fish_crate(b, x, y, L.ground(x, y) + 0.1, yaw, 1.0)
        sack(b, x + 1.2, y + 0.9, L.ground(x, y) + 0.1, 0.85)
    pennants(b, (-88, 128, 9.2), (88, 128, 9.2), 0.8, 21)
    # Fill the open cobbles with lanes of smaller stalls, as in the market painting: a bazaar, not a parade ground.
    taken = [(x, y, w / 2 + 3.5, d / 2 + 3.5) for x, y, w, d, _ in L.MARKET_STALLS]
    taken += [(0, 158, 7, 7), (47, 137, 6, 6), (-44, 188, 7, 6), (0, 126, 30, 14), (-16, 134, 10, 7)]
    lane = 0
    for gy in range(112, 220, 15):
        lane += 1
        for gx in range(-84, 86, 13):
            x = gx + RNG.uniform(-2.0, 2.0) + (6.5 if lane % 2 else 0.0)
            y = gy + RNG.uniform(-1.5, 1.5)
            w, d = RNG.uniform(6.5, 9.0), RNG.uniform(4.5, 5.8)
            if abs(x) > 86 or any(abs(x - tx) < w / 2 + hw and abs(y - ty) < d / 2 + hd for tx, ty, hw, hd in taken):
                continue
            taken.append((x, y, w / 2 + 2.5, d / 2 + 2.5))
            yaw = RNG.uniform(-6, 6)
            z = L.ground(x, y) + 0.1
            market_stall(b, x, y, z, w, d, ('canvas', 'canvas_red', 'canvas_teal', 'canvas')[RNG.randrange(4)], yaw)
            for side in (-1, 1):
                gx2, gy2 = local(x, y, yaw, side * w * 0.3, -d * 0.62)
                goods(b, gx2, gy2, z, yaw, RNG)
    # A working stall just ahead of the market camera anchors the foreground.
    market_stall(b, -16, 134, L.ground(-16, 134) + 0.1, 12, 7, 'canvas_teal', 4)
    for x, y, yaw in ((-2, 131, 8), (6, 137, -12), (-28, 133, 16)):
        fish_crate(b, x, y, L.ground(x, y) + 0.1, yaw, 1.0)
        sack(b, x + 1.3, y + 0.8, L.ground(x, y) + 0.1, 0.85)
    return b


TERRACE_STAIRS = ((0.0, 22.0), (-238.0, 8.0), (252.0, 8.0))  # quay-to-terrace stairs: centre x, tread width
TERRACE_CHEEKS = {0.0: 1.6, -238.0: 0.7, 252.0: 0.7}  # each stair's parapet width beyond its treads
STAIR_FOOT_Y, STAIR_TOP_Y = 230.0, 279.0    # foot on the quay street north of the market; top at the terrace edge
STAIR_RISE_MAX, STAIR_LANDING, STAIR_FLIGHT = 0.24, 2.2, 22   # riser cap (m), landing depth (m), risers per flight
NOSING_LIFT = 0.01          # each tread's nosing stands this far above the tread (terrace_stair)
STAIR_APRON = 2.4           # depth of the level foot apron in front of each stair (m)
APRON_LIFT = 0.03           # the apron's top clears the highest street slab it covers by this much


def stair_apron(x):
    """The level foot apron in front of the stair at x: (x0, x1, y0, y1, top). Its top clears every street slab
    under it, so the street's slab-by-slab heights never reach the first riser."""
    width = dict(TERRACE_STAIRS)[x]; cheek = TERRACE_CHEEKS[x]
    x0, x1, y0, y1 = x - width / 2 - cheek, x + width / 2 + cheek, STAIR_FOOT_Y - STAIR_APRON, STAIR_FOOT_Y
    under = [top for a, b, c, d, top in lower_street_slabs() if a < x1 and b > x0 and c < y1 and d > y0]
    return x0, x1, y0, y1, max(under + [L.ground(x, STAIR_FOOT_Y) + 0.16]) + APRON_LIFT


@functools.lru_cache(maxsize=None)
def terrace_stair_plan(x):
    """@cc [owner:fontanierh,label:correctness] terrace-stair-climbable
    The quay-to-terrace stair at x, bottom to top: (foot z, [(y0, y1, top z)]) of abutting treads and landings.
    The foot z is the top of the stair's level apron (stair_apron), which clears every emitted street slab under it.
    Every riser as built, nosing included, MUST be at most STAIR_RISE_MAX, well under the pawn's 0.45 m step: the
    first from the apron, every one between treads and the last onto the terrace paving. Treads and landings MUST
    abut in y with no gap, and the last riser MUST land flush on the terrace paving at STAIR_TOP_Y.
    """
    # Playtest note 410-1/2: the r10 stair climbed 25.5 m in 24 one-metre risers on floating 0.8 m slabs, so the pawn
    # could not climb it, daylight showed under every nosing and the terrace paving walled off its top four treads.
    # The street slabs at the foot follow the ground slab by slab (up to 6 cm apart), so the stair starts from an
    # apron above them rather than from the ground under its first riser.
    z0 = stair_apron(x)[4]
    z1 = L.UPPER_Z + 0.22                           # the terrace paving top
    n = math.ceil((z1 - z0) / (STAIR_RISE_MAX - NOSING_LIFT))
    flights = math.ceil(n / STAIR_FLIGHT)
    rise = (z1 - z0) / n
    tread = (STAIR_TOP_Y - STAIR_FOOT_Y - (flights - 1) * STAIR_LANDING) / (n - flights)
    sizes = [n // flights + (1 if i < n % flights else 0) for i in range(flights)]
    steps, y, k = [], STAIR_FOOT_Y, 0
    for f, m in enumerate(sizes):
        for _ in range(m - 1):
            k += 1
            steps.append((y, y + tread, z0 + rise * k))
            y += tread
        k += 1
        if f < flights - 1:
            steps.append((y, y + STAIR_LANDING, z0 + rise * k))
            y += STAIR_LANDING
    return z0, steps


def terrace_stair(b, x, width, cheek):
    """Solid masonry treads from the quay up to the terrace with landings between flights, a pale nosing on each
    tread, and a coped parapet on each side that climbs with the flights."""
    z0, steps = terrace_stair_plan(x)
    base = z0 - 0.6
    hw = width / 2
    # The foot apron: one level slab over the street's slabs, its top the stair's foot.
    ax0, ax1, ay0, ay1, _ = stair_apron(x)
    b.box(((ax0 + ax1) / 2, (ay0 + ay1) / 2, z0 - 0.15), (ax1 - ax0, ay1 - ay0, 0.3), 'stone_light')
    for y0, y1, top in steps:
        b.box((x, (y0 + y1) / 2, (top + base) / 2), (width, y1 - y0, top - base), 'stone_light')
        # The nosing stands 2 cm proud of the riser and 1 cm in from each side, so none of its faces is coplanar
        # with the tread's (coplanar faces z-fought into streaks along every step edge).
        b.box((x, y0 + 0.05, top + NOSING_LIFT - 0.04), (width - 0.02, 0.14, 0.08), 'stone')
    # Parapets: one sloped block per flight over its nosing line, a flat one per landing, each coped.
    runs, cur = [], []
    for y0, y1, top in steps:
        if y1 - y0 > STAIR_LANDING - 1e-6:
            if cur:
                runs.append(('flight', cur))
            runs.append(('landing', [(y0, y1, top)]))
            cur = []
        else:
            cur.append((y0, y1, top))
    if cur:
        runs.append(('flight', cur))
    for side in (-1, 1):
        xa, xb = sorted((x + side * hw, x + side * (hw + cheek)))
        for _, run in runs:
            ya, yb = run[0][0], run[-1][1]
            ta, tb = run[0][2] + 0.95, run[-1][2] + 0.95
            LM._block(b, [(xa, ya, base), (xb, ya, base), (xb, yb, base), (xa, yb, base)],
                      [(xa, ya, ta), (xb, ya, ta), (xb, yb, tb), (xa, yb, tb)], 'stone')
            LM._block(b, [(xa - 0.05, ya, ta), (xb + 0.05, ya, ta), (xb + 0.05, yb, tb), (xa - 0.05, yb, tb)],
                      [(xa - 0.05, ya, ta + 0.15), (xb + 0.05, ya, ta + 0.15), (xb + 0.05, yb, tb + 0.15),
                       (xa - 0.05, yb, tb + 0.15)], 'stone_light')
        # A newel at the foot.
        b.box(((xa + xb) / 2, STAIR_FOOT_Y + 0.4, (base + steps[0][2] + 1.3) / 2), (xb - xa + 0.2, 0.8,
              steps[0][2] + 1.3 - base), 'stone_light')


def upper_town():
    b = Builder('05_town_upper')
    # Terrace surface and street.
    paving(b, -320.0, 320.0, 287.0, 393.0, z=L.UPPER_Z + 0.22, tile=7.0, thick=0.4, kerbs=(False, False), seed=5)
    paving(b, -320.0, 320.0, 279.0, 287.0, z=L.UPPER_Z + 0.22, tile=7.0, thick=0.4, kerbs=(False, False), seed=6)
    # The terrace's carriageway: a band of dark setts between two flagstone kerbs.
    b.box((0, 340, L.UPPER_Z + 0.16), (620, 22, 0.18), 'cobble_dark')
    for yy in (328.8, 351.2):
        b.box((0, yy, L.UPPER_Z + 0.3), (620, 0.6, 0.2), 'stone_light')
    for y0, y1 in ((354, 400), (424, 452)):
        pave_band(b, y0, y1, skip_market=False)
    # Balustrade along the harbor edge, broken for the three stairs.
    for x in range(-310, 311, 4):
        if abs(x) < 18 or 224 < abs(x) < 262:
            continue
        b.box((x, 283, L.UPPER_Z + 0.7), (3.2, 0.55, 1.4), 'stone')
        b.box((x, 283, L.UPPER_Z + 1.45), (3.5, 0.8, 0.28), 'stone_light')
    for x in (-309, -265, -221, -18, 18, 221, 265, 309):
        b.box((x, 283, L.UPPER_Z + 0.9), (2.2, 1.2, 1.8), 'stone_light')
        b.sphere((x, 283, L.UPPER_Z + 1.95), 0.55, 'stone_dark', (1.0, 1.0, 0.8), subdiv=0)
    # Retaining wall, buttresses, niches and a coping.
    wall_mid = (L.QUAY_Z + L.UPPER_Z) / 2
    wall_h = L.UPPER_Z - L.QUAY_Z
    for x0, x1 in ((-322, -252), (-224, -26), (26, 224), (262, 342)):
        b.box(((x0 + x1) / 2, 281, wall_mid), (x1 - x0, 3.0, wall_h), 'stone')
        b.box(((x0 + x1) / 2, 279.7, L.UPPER_Z + 0.15), (x1 - x0 + 2, 4.6, 0.5), 'stone_light')
        # Warm ashlar courses and hanging greenery give the tall retaining
        # wall a human scale instead of one long grey viaduct face.
        for zz in range(7, 29, 4):
            b.box(((x0 + x1) / 2, 279.42, zz), (x1 - x0, 0.36, 0.20), 'stone_light')
        for x in range(int(x0) + 10, int(x1), 32):
            b.box((x, 278.8, wall_mid - 0.5), (5.0, 2.8, wall_h - 1.0), 'stone_light')
            b.box((x, 278.4, wall_mid + 0.4), (2.4, 0.8, 4.2), 'stone_dark')
            b.box((x, 278.2, wall_mid + 2.5), (2.4, 0.7, 2.4), 'stone_dark')
    for i in range(30):
        vx = RNG.uniform(-316, 336)
        if abs(vx) < 32:
            continue
        vine(b, vx, 278.9, L.UPPER_Z - 0.2, RNG.uniform(3.4, 9.5), RNG)
    # Painted banners break up the long retaining wall.
    for i, bx in enumerate(range(-300, 301, 74)):
        mat = ('flag_red', 'cream', 'roof_teal', 'canvas_red')[i % 4]
        b.panel((bx - 3.0, 278.2, 21.5), (bx + 3.0, 278.2, 21.5),
                (bx + 2.4, 278.2, 12.5), (bx - 2.4, 278.2, 12.5), mat, thick=0.04)
        b.beam((bx - 3.2, 278.1, 21.6), (bx + 3.2, 278.1, 21.6), 0.12, 'wood_dark')
    # A planted string course halfway up breaks the 25 m wall into two tiers.
    for x0, x1 in ((-322, -252), (-224, -26), (26, 224), (262, 342)):
        b.box(((x0 + x1) / 2, 278.95, 17.5), (x1 - x0, 1.35, 0.55), 'stone_light')
        for x in range(int(x0) + 12, int(x1), 24):
            b.box((x, 278.70, 18.2), (2.8, 1.1, 0.85), 'stone')
            bush(b, x, 278.70, 18.55, 0.0, 0.62, RNG)
    # Grand stair from the quay to the terrace, its cheeks closing on the retaining wall's (12.6 m).
    terrace_stair(b, *TERRACE_STAIRS[0], cheek=TERRACE_CHEEKS[TERRACE_STAIRS[0][0]])
    # The retaining wall closes on the stair's cheeks: the gap beside the flights showed the raw cliff as flat beige
    # planes, a box trench in the note 7 view. Ashlar cheeks with courses, a coping and greenery match the wall.
    for side in (-1, 1):
        x0, x1 = sorted((side * 12.6, side * 26.0))
        b.box(((x0 + x1) / 2, 281, wall_mid), (x1 - x0, 3.0, wall_h), 'stone')
        b.box(((x0 + x1) / 2, 279.7, L.UPPER_Z + 0.15), (x1 - x0 + 1.0, 4.6, 0.5), 'stone_light')
        for zz in range(7, 29, 4):
            b.box(((x0 + x1) / 2, 279.42, zz), (x1 - x0, 0.36, 0.20), 'stone_light')
        b.box((side * 13.4, 279.2, wall_mid - 0.5), (1.6, 1.6, wall_h - 1.0), 'stone_light')
        for k in range(3):
            vine(b, side * (16.0 + k * 3.6), 279.0, L.UPPER_Z - 0.2, RNG.uniform(5.0, 12.0), RNG)
        bush(b, side * 19.0, 278.4, L.QUAY_Z, 0.0, 1.1, RNG)
    for x, width in TERRACE_STAIRS[1:]:
        terrace_stair(b, x, width, cheek=TERRACE_CHEEKS[x])
    # Upper buildings.
    for spec in L.DENSE_LOTS:
        if spec[2] >= 280:
            if spec[0].startswith(('slope-', 'ridge-')):
                b.box((spec[1], spec[2], spec[3] - 2.1), (spec[4] + 1.0, spec[5] + 1.0, 4.2),
                      'stone', spec[9])
            if spec[0].startswith('slope-') and sum(map(ord, spec[0])) % 3 == 0:
                lx, ly = local(spec[1], spec[2], spec[9], -spec[4] / 2 - 0.7, spec[5] * 0.22)
                for dz in (0.0, 1.0):
                    b.beam((lx + dz, ly, spec[3]), (lx + dz, ly, spec[3] + 5.2), 0.10, 'wood_dark')
                for r in range(6):
                    b.beam((lx, ly, spec[3] + 0.8 + r * 0.75), (lx + 1.0, ly, spec[3] + 0.8 + r * 0.75),
                           0.06, 'wood')
            if spec[8] == 'shack':
                spec = (*spec[:3], L.ground(spec[1], spec[2]) + 0.1, *spec[4:])
            for sub in split_lot(spec, RNG):
                building(b, sub, RNG)
    # The stilted hamlet perched on the upper slope. Long foundations and
    # posts keep every hut grounded on the uneven ridge.
    for spec in L.HILLSIDE_BUILDINGS:
        key, x, y, _, w, d, h, floors, style, yaw, roof = spec
        z = L.ground(x, y) + 0.4
        b.box((x, y, z - 3.8), (w + 4.0, d + 4.0, 7.6), 'stone', yaw)
        for side in (-1, 1):
            px, py = local(x, y, yaw, side * (w * 0.34), 0)
            b.cylinder((px, py, z - 8.0), (px, py, z - 1.0), 0.38, 'wood_dark', 6)
        building(b, (key, x, y, z, w, d, h, floors, style, yaw, roof), RNG)
    # A cistern and a laundry line on the terrace.
    cx, cy = -24, 360
    b.cylinder((cx, cy, L.UPPER_Z), (cx, cy, L.UPPER_Z + 2.6), 2.8, 'stone', 12)
    b.cylinder((cx, cy, L.UPPER_Z + 2.5), (cx, cy, L.UPPER_Z + 2.65), 3.0, 'stone_light', 12)
    for i in range(3):
        b.rope((cx - 7, cy + 4 + i * 0.4, L.UPPER_Z + 4.5), (cx - 1, cy + 4 + i * 0.4, L.UPPER_Z + 4.5), 0.3, 0.03)
        b.panel((cx - 6, cy + 4 + i * 0.4, L.UPPER_Z + 4.45), (cx - 4.3, cy + 4 + i * 0.4, L.UPPER_Z + 4.45),
                (cx - 4.3, cy + 4 + i * 0.4, L.UPPER_Z + 2.9), (cx - 6, cy + 4 + i * 0.4, L.UPPER_Z + 2.9),
                ('cream', 'flag_red', 'roof_teal')[i], thick=0.04)
    # Foreground pots and a laundry line frame the terrace view.
    for x, y in ((-14, 310), (14, 310), (-34, 306), (34, 306)):
        b.cylinder((x, y, L.UPPER_Z + 0.1), (x, y, L.UPPER_Z + 1.1), 0.9, 'clay', 8, radius_b=0.7)
        palm(b, x, y, L.UPPER_Z + 1.0, 0, 0.36, RNG)
    b.rope((-36, 314, L.UPPER_Z + 4.8), (36, 314, L.UPPER_Z + 4.8), 0.5, 0.04)
    for i in range(4):
        x = -24 + i * 16
        b.panel((x, 314, L.UPPER_Z + 4.7), (x + 6, 314, L.UPPER_Z + 4.7),
                (x + 6, 314, L.UPPER_Z + 2.7), (x, 314, L.UPPER_Z + 2.7),
                ('canvas', 'canvas_red', 'canvas_teal', 'canvas')[i], thick=0.04)
    # A switchback stair climbs from the terrace to the ridge hamlet's shelf.
    LM.hill_stair(b)
    # Bunting, pots and seating make the upper lane read as a street.
    for y in (306, 342, 378):
        pennants(b, (-240, y, L.UPPER_Z + 5.2), (240, y, L.UPPER_Z + 5.2), 1.2, 21)
    for x, y in ((-120, 300), (120, 300), (-200, 336), (200, 336), (-90, 374), (90, 374)):
        potted_plant(b, x, y, L.ground(x, y) + 0.05, 0.75, RNG)
    for x in (-180, -60, 60, 180):
        bench(b, x, 296, L.ground(x, 296) + 0.1, 180)
    return b


def landmarks():
    b = Builder('06_landmarks')
    lighthouse(b)
    if not HAS_STATUE:
        statue(b)
    LM.fort(b)
    # The two-tier waterfall, its canyon river, rope bridge and ledge shrine (falls.py).
    falls.waterfall(b)
    return b


def lighthouse(b):
    x, y, _ = L.LIGHTHOUSE
    z = L.ground(x, y) + 0.4
    # Broad rock plinth, then a tall tapered tower with three broad red bands.
    b.cylinder((x, y, z - 1.5), (x, y, z + 2.0), 7.2, 'stone', 14, radius_b=5.4)
    b.cylinder((x, y, z + 1.9), (x, y, z + 2.35), 6.8, 'stone_light', 14)
    z0 = z + 2.2
    bands = 11
    for i in range(bands):
        r0 = 4.35 - i * 0.13
        r1 = 4.35 - (i + 1) * 0.13
        mat = 'flag_red' if i in (1, 2, 6, 7, 10) else 'cream'
        b.cylinder((x, y, z0 + i * 2.55), (x, y, z0 + (i + 1) * 2.55), r0, mat, 14, radius_b=r1)
    # Gallery and railing.
    zz = z0 + bands * 2.55
    b.cylinder((x, y, zz), (x, y, zz + 0.55), 3.1, 'stone_dark', 14, radius_b=3.0)
    for i in range(14):
        a = i * TAU / 14
        px, py = x + math.cos(a) * 3.3, y + math.sin(a) * 3.3
        b.beam((px, py, zz + 0.5), (px, py, zz + 2.25), 0.10, 'metal')
    b.ring((x, y, zz + 2.15), 3.3, 0.10, 'metal', sides=16)
    b.ring((x, y, zz + 1.1), 3.3, 0.06, 'metal', sides=16)
    # Lantern room, glazing bars, dome and lightning rod.
    b.cylinder((x, y, zz + 0.55), (x, y, zz + 3.6), 2.35, 'glass_warm', 12)
    for i in range(8):
        a = i * TAU / 8
        px, py = x + math.cos(a) * 2.34, y + math.sin(a) * 2.34
        b.beam((px, py, zz + 0.6), (px, py, zz + 3.55), 0.08, 'metal')
    b.cylinder((x, y, zz + 3.55), (x, y, zz + 4.1), 2.75, 'metal', 12, radius_b=2.35)
    b.cylinder((x, y, zz + 4.05), (x, y, zz + 5.25), 2.55, 'roof_teal', 12, radius_b=0.15)
    b.cylinder((x, y, zz + 5.2), (x, y, zz + 6.1), 0.10, 'metal', 6)
    b.sphere((x, y, zz + 6.2), 0.35, 'gold', subdiv=0)
    # Door, small windows and the keeper's cottage at the foot.
    b.box((x, y - 4.35, z + 4.1), (1.9, 0.5, 3.6), 'wood_dark')
    for f in (0.35, 0.62):
        b.box((x - 4.2, y, z + 2.2 + f * 20), (0.25, 1.1, 1.4), 'glass_warm', 90)
    kx, ky = x + 24, y + 12
    kz = L.ground(kx, ky) + 0.2
    b.box((kx, ky, kz + 2.2), (17, 12, 4.4), 'cream')
    b.gable_roof((kx, ky, kz + 4.4), 17, 12, kz + 4.4, 3.8, 'roof_terra', 0, ridge='x')
    window(b, kx, ky, 0, -4.4, -6.05, kz + 1.5, 1.25, 1.55, True, True)
    window(b, kx, ky, 0, 4.2, -6.05, kz + 1.5, 1.25, 1.55, True, True)
    door(b, kx, ky, 0, 0, -6.05, kz, 1.5, 2.3)
    b.box((kx + 5.5, ky + 2.5, kz + 6.4), (1.1, 1.1, 3.4), 'stone')
    b.box((kx + 5.5, ky + 2.5, kz + 8.2), (1.4, 1.4, 0.3), 'stone_dark')
    lantern_post(b, kx - 10, ky - 8, kz, 3.2)
    # A low signal wall and a pair of cannon on the seaward edge, run out through gaps in it.
    for i in range(10):
        px = x - 18 + i * 4.2
        if i in (3, 6):
            b.box((px, y - 15.0, z + 0.3), (4.2, 1.2, 0.6), 'stone')
            LM.cannon(b, px, y - 12.6, L.ground(px, y - 12.6), 0.0, 1.8)
            continue
        b.box((px, y - 15.0, z + 1.0), (4.2, 1.2, 2.0), 'stone')
    # A lived-in headland: a stone path links cottage and tower, a rope fence
    # follows the cliff edge, and garden beds and palms break up the lawn.
    for i in range(22):
        t = i / 21
        px = x + 24 * t
        py = y + 12 * t
        pz = L.ground(px, py) + 0.10
        b.box((px, py, pz), (2.3, 2.3, 0.18),
              'stone_light' if i % 4 else 'sand', 0)
    for i in range(13):
        px = x - 30 + i * 5.0
        py = y - 27.0
        pz = L.ground(px, py)
        b.beam((px, py, pz), (px, py, pz + 2.3), 0.16, 'wood_dark')
        if i < 12:
            qx = px + 5.0
            qz = L.ground(qx, py)
            b.beam((px, py, pz + 1.8), (qx, py, qz + 1.8), 0.07, 'rope')
            b.beam((px, py, pz + 0.9), (qx, py, qz + 0.9), 0.05, 'rope')
    for side, off in ((-1, -18), (1, 18)):
        gx, gy = x + off, y + 2
        gz = L.ground(gx, gy)
        b.box((gx, gy, gz + 0.35), (7.5, 3.2, 0.7), 'stone')
        for i in range(4):
            bush(b, gx - 2.6 + i * 1.8, gy, gz + 0.7, 0.0, 0.55, RNG)
    for i in range(16):
        rx = x - 38 + RNG.uniform(0, 76)
        ry = y - 34 + RNG.uniform(-5, 2)
        rock_cluster(b, rx, ry, L.height(rx, ry) - 0.8, RNG.uniform(1.4, 3.2), 2)
    for px, py, scale in ((-30, -8, 1.0), (34, 16, 0.82), (18, -20, 0.7)):
        palm(b, x + px, y + py, L.ground(x + px, y + py), RNG.uniform(0, 360), scale, RNG)
    b.box((x + 31, y + 19, L.ground(x + 31, y + 19) + 1.1), (4.0, 3.0, 2.2), 'wood')
    b.gable_roof((x + 31, y + 19, L.ground(x + 31, y + 19) + 2.1), 4.0, 3.0,
                 L.ground(x + 31, y + 19) + 2.1, 1.4, 'roof_terra', 0, ridge='x', overhang=0.5)


def statue(b):
    x, y, _ = L.STATUE
    z = 8.0
    start = len(b.verts)
    # Plinth and figure, all in one stone material so the silhouette reads from the harbor.
    b.box((x, y, z + 2.2), (11, 11, 4.4), 'stone')
    b.box((x, y, z + 4.5), (13, 13, 0.5), 'stone_light')
    base = z + 4.8
    # Boots, legs and coat.
    for side in (-1, 1):
        b.box((x + side * 1.2, y, base + 2.0), (2.0, 3.2, 4.0), 'stone')
    b.box((x, y, base + 6.8), (5.6, 3.6, 6.8), 'stone_light')
    b.sphere((x, y, base + 8.2), 1.8, 'stone', (1.8, 0.9, 2.0), subdiv=1)
    # Torso, shoulders and head.
    b.box((x, y, base + 11.4), (5.2, 3.0, 3.4), 'stone')
    b.box((x, y, base + 13.0), (7.2, 3.3, 1.3), 'stone')
    b.sphere((x, y, base + 14.4), 1.45, 'stone_light', (0.95, 0.9, 1.1), subdiv=1)
    # Tricorn hat: brim and three raised points.
    b.cylinder((x, y, base + 15.2), (x, y, base + 15.55), 2.4, 'stone_dark', 3)
    b.sphere((x, y, base + 15.9), 1.15, 'stone_dark', (1.1, 1.1, 0.55), subdiv=0)
    # Cape billowing behind.
    for i in range(3):
        b.quad((x - 2.8 + i * 2.8, y + 1.6, base + 12.8),
               (x - 2.8 + i * 2.8, y + 2.1, base + 12.8),
               (x - 4.2 + i * 3.2, y + 5.6 + i * 0.8, base + 5.5),
               (x - 5.2 + i * 3.2, y + 5.2 + i * 0.8, base + 5.5), 'stone_dark')
    # Right arm raised with a cutlass; left hand on the hip.
    b.beam((x + 2.8, y, base + 12.9), (x + 5.8, y - 0.2, base + 15.8), 0.55, 'stone')
    b.beam((x + 5.8, y - 0.2, base + 15.8), (x + 6.6, y - 0.4, base + 18.7), 0.35, 'stone_light')
    b.beam((x + 6.2, y - 0.3, base + 18.0), (x + 10.2, y - 1.8, base + 22.0), 0.18, 'metal')
    b.beam((x + 9.2, y - 1.5, base + 20.5), (x + 10.8, y - 2.1, base + 22.4), 0.25, 'metal')
    b.beam((x - 2.8, y, base + 12.9), (x - 4.5, y - 1.2, base + 9.3), 0.55, 'stone')
    b.beam((x - 4.5, y - 1.2, base + 9.3), (x - 1.4, y - 1.7, base + 7.8), 0.35, 'stone')
    # A lantern held low on the seaward side.
    b.box((x - 5.0, y - 2.3, base + 8.4), (0.9, 0.9, 1.2), 'lantern')
    # The queen is a harbor landmark: make her a little larger than life.
    scale = 1.5
    for i in range(start, len(b.verts)):
        vx, vy, vz = b.verts[i]
        b.verts[i] = (x + (vx - x) * scale, y + (vy - y) * scale, z + (vz - z) * scale)


def ships():
    b = Builder('07_ships')
    for i, spec in enumerate(L.SHIPS):
        name, x, y, yaw, scale, sails = spec
        # The paintings' two pirate galleons fly black canvas; the sloop keeps cream.
        ship(b, x, y, -1.1, yaw, scale, sails=sails, unfinished=False,
             canvas='sail_dark' if name.startswith('galleon') else 'sail')
    # The broken hull on the western rocks is a dark, readable landmark from the harbor mouth.
    ship(b, -492, -246, -2.8, 34, 0.60, sails=False, unfinished=True)
    return b


def ship(b, x, y, z, yaw, scale=1.0, sails=True, unfinished=False, canvas='sail_dark'):
    """A three-masted galleon with a lofted hull, gun deck and layered rigging.

    Local +Y is the bow.  The hull stations carry width, keel and gunwale
    height; four shell bands give the tumblehome and wale that the blockout
    lacked.
    """
    def T(lx, ly, lz):
        return local(x, y, yaw, lx * scale, ly * scale) + (z + lz * scale,)

    def box(lx, ly, lz, sx, sy, sz, mat, rot=0.0):
        b.box(T(lx, ly, lz), (sx * scale, sy * scale, sz * scale), mat, yaw + rot)

    stations = [
        (-32.0, 2.2, 3.6, 7.4), (-29.0, 4.4, 2.5, 8.1), (-25.0, 6.2, 1.7, 8.7),
        (-18.0, 7.4, 1.0, 9.0), (-8.0, 8.0, 0.6, 9.1), (2.0, 8.0, 0.5, 9.1),
        (12.0, 7.4, 0.9, 8.9), (20.0, 6.0, 1.7, 8.5), (26.0, 4.0, 2.9, 7.8),
        (30.0, 1.2, 4.6, 6.8),
    ]
    if not (HAS_HULL and not unfinished):
        # Hull shell in four horizontal bands.  The upper bands pull inward for
        # tumblehome; the wale is a darker band with a proud rubbing strake.
        bands = ((0.24, 0.72, 0.0, 2.5, 'wood_dark'), (0.72, 1.0, 2.5, 4.7, 'hull'),
                 (1.0, 0.94, 4.7, 6.6, 'hull'), (0.94, 0.82, 6.6, 8.6, 'wood_light'))
        for i in range(len(stations) - 1):
            y0, w0, k0, g0 = stations[i]
            y1, w1, k1, g1 = stations[i + 1]
            for side in (-1, 1):
                for fa, fb, za, zb, mat in bands:
                    zz0 = k0 + (g0 - k0) * za / 8.6 if za else k0
                    zz1 = k1 + (g1 - k1) * za / 8.6 if za else k1
                    a = T(side * w0 * fa, y0, zz0)
                    bb = T(side * w1 * fa, y1, zz1)
                    c = T(side * w1 * fb, y1, k1 + (g1 - k1) * zb / 8.6)
                    d = T(side * w0 * fb, y0, k0 + (g0 - k0) * zb / 8.6)
                    b.quad(a, bb, c, d, mat)
                # Proud wale and a row of iron nail heads.
                b.beam(T(side * w0 * 1.01, y0, 4.8), T(side * w1 * 1.01, y1, 4.8), 0.20, 'wood_dark')
                b.beam(T(side * w0 * 0.96, y0, 6.55), T(side * w1 * 0.96, y1, 6.55), 0.10, 'metal')
                # Gun ports and cannon muzzles on the lower gun deck.
                for yy in (y0 + 2.0, y0 + 7.0):
                    if yy < y1:
                        px, py = local(x, y, yaw, side * (w0 + 0.1) * scale, yy * scale)
                        slot = py + 0.0
                        b.box((px, slot, z + 5.7 * scale), (0.35 * scale, 1.4 * scale, 0.9 * scale), 'glass', yaw)
                        b.cylinder((px, slot, z + 5.7 * scale),
                                   T(side * (w0 + 1.5), yy, 5.7), 0.20 * scale, 'metal', 7)
        # Deck planking, keel and deck beams.
        for i in range(len(stations) - 1):
            y0, w0, _, _ = stations[i]
            y1, w1, _, _ = stations[i + 1]
            b.quad(T(-w0 * 0.94, y0, 4.7), T(w0 * 0.94, y0, 4.7),
                   T(w1 * 0.94, y1, 4.7), T(-w1 * 0.94, y1, 4.7), 'deck_planks')
            b.beam(T(-w0 * 0.92, y0, 4.55), T(w0 * 0.92, y0, 4.55), 0.16, 'wood_dark')
        b.beam(T(0, -32, 1.1), T(0, 30, 1.1), 0.7, 'wood_dark')
        # Transom, stern galleries and the raised cabin.
        b.quad(T(-2.3, -32.1, 4.4), T(2.3, -32.1, 4.4), T(2.7, -32.1, 8.7), T(-2.7, -32.1, 8.7), 'wood')
        for side in (-1, 1):
            b.box(T(side * 2.5, -32.4, 9.3), (0.32, 0.32, 0.52), 'lantern')
            b.beam(T(side * 2.5, -32.4, 9.56), T(side * 2.5, -32.4, 9.9), 0.03, 'metal')
        box(0, -24.0, 7.0, 11.0, 12.0, 3.2, 'wood')
        box(0, -24.0, 9.0, 12.0, 13.0, 0.35, 'wood_dark')
        for side in (-1, 1):
            for yy in (-29.0, -26.0, -23.0, -20.0, -17.0):
                box(side * 5.1, yy, 7.8, 0.18, 1.15, 1.25, 'glass_warm')
                box(side * 5.2, yy, 6.65, 0.22, 1.4, 0.16, 'gold')
            # Stern gallery rail and brackets.
            b.beam(T(side * 5.4, -30.0, 9.25), T(side * 5.4, -15.0, 9.25), 0.12, 'wood_dark')
            for yy in (-29, -25, -21, -17):
                b.beam(T(side * 5.4, yy, 8.9), T(side * 5.4, yy, 10.1), 0.10, 'wood')
        # Forecastle deck and its rail.
        box(0, 22.0, 6.65, 10.0, 9.0, 3.2, 'wood')
        box(0, 22.0, 8.15, 10.2, 9.2, 0.25, 'wood_dark')
        for side in (-1, 1):
            for yy in (18, 21, 24, 27):
                b.beam(T(side * 4.8, yy, 8.2), T(side * 4.8, yy, 9.25), 0.10, 'wood')
            b.beam(T(side * 4.8, 18.0, 9.2), T(side * 4.8, 27.0, 9.2), 0.13, 'wood_dark')
        # Bowsprit, stem and a carved figurehead block (a TRELLIS figurehead is
        # loaded over this when the asset is present).
        b.beam(T(0, 29, 7.6), T(0, 44, 12.4), 0.38, 'wood_dark')
        b.beam(T(0, 29, 7.6), T(0, 39, 9.6), 0.18, 'metal')
        if not HAS_FIGUREHEAD:
            b.sphere(T(0, 43.2, 11.8), 1.05, 'gold', (0.75, 1.4, 0.8), subdiv=0)
            b.sphere(T(0, 45.0, 12.6), 0.55, 'gold', (0.7, 1.1, 0.7), subdiv=0)
        # Deck furniture: hatch, capstan, ship's boat and a wheel.
        box(0, 6.0, 5.0, 6.0, 5.0, 0.35, 'wood_dark')
        box(0, 6.0, 5.2, 5.2, 4.2, 0.25, 'wood_light')
        b.cylinder(T(0, 12, 4.8), T(0, 12, 6.4), 0.85, 'wood', 10, radius_b=0.65)
        b.beam(T(-2.2, 12, 5.9), T(2.2, 12, 5.9), 0.16, 'wood_dark')
        b.beam(T(0, 9.8, 5.9), T(0, 14.2, 5.9), 0.16, 'wood_dark')
        box(0, -10.0, 5.15, 4.8, 7.2, 0.6, 'wood_light')
        if not HAS_WHEEL:
            b.ring(T(0, -16.5, 6.3), 1.05, 0.10, 'wood', axis='x', sides=12)
            for i in range(8):
                a = i * TAU / 8
                b.beam(T(0, -16.5, 6.3), T(math.cos(a) * 1.1, -16.5, 6.3 + math.sin(a) * 1.1), 0.06, 'wood')
        # Fenders and a pair of anchors stowed at the bow.
        for yy in (-18, -2, 14):
            b.cylinder(T(8.1, yy, 5.4), T(8.1, yy, 8.2), 0.34, 'rope', 7)
        for side in (-1, 1):
            b.ring(T(side * 3.4, 26.0, 5.8), 0.8, 0.12, 'metal', axis='x', sides=10)
    if unfinished:
        # Exposed ribs and staging make the shipyard hull read as work in progress.
        for y0, w0, k0, g0 in stations:
            for side in (-1, 1):
                b.beam(T(side * w0 * 0.35, y0, k0), T(side * w0, y0, g0), 0.22, 'wood_dark')
        for yy in (-24, -16, -8, 0, 8, 16, 24):
            for side in (-1, 1):
                b.beam(T(side * 8.6, yy, 0), T(side * 8.6, yy, 9.6), 0.16, 'wood_light')
        b.beam(T(-10, 24, 8.6), T(10, 24, 8.6), 0.18, 'wood_dark')
        return
    # Masts, tops, yards, layered sails and standing rigging.  On the Tripo hull the rig stands on its waist deck
    # (keel a draft below the sea, as hero_assets seats it) and on its mast stumps, a little taller for the bigger hull.
    deck, masts = 4.7, [(-15.0, 21.0, 0.62), (3.0, 30.0, 1.0), (18.0, 24.0, 0.74)]
    if HULL:
        deck = HULL['deck_z'] - 0.24 * HULL['top_z'] - 0.3
        masts = [(my, mh * 1.12, strength) for my, (_, mh, strength) in zip(HULL['masts'], masts)]
    rise = deck - 4.7
    if HULL:
        # Bowsprit for the forestays.
        b.cylinder(T(0, 26.0, deck + 1.5), T(0, 44.0, 12.4 + rise), 0.42, 'wood_dark', 8, radius_b=0.2)
    for my, mh, strength in masts:
        b.cylinder(T(0, my, deck), T(0, my, deck + mh), 0.50 * strength, 'wood_dark', 8,
                   radius_b=0.24 * strength)
        # Mast top and crosstrees.
        b.cylinder(T(0, my, deck + mh * 0.58), T(0, my, deck + mh * 0.61), 1.7 * strength,
                   'wood', 10, radius_b=1.4 * strength)
        b.beam(T(-2.4 * strength, my, deck + mh * 0.605), T(2.4 * strength, my, deck + mh * 0.605),
               0.16, 'wood_dark')
        if my == masts[1][0]:
            # Crow's nest on the mainmast.
            b.cylinder(T(0, my, deck + mh * 0.86), T(0, my, deck + mh * 0.89), 1.55, 'wood', 10)
            for i in range(10):
                a = i * TAU / 10
                b.beam(T(math.cos(a) * 1.5, my + math.sin(a) * 1.5, deck + mh * 0.89),
                       T(math.cos(a) * 1.5, my + math.sin(a) * 1.5, deck + mh * 0.89 + 0.8), 0.07, 'wood_dark')
        for frac, width in ((0.34, 11.5), (0.55, 9.8), (0.76, 7.2)):
            zz = deck + mh * frac
            yard_w = width * strength
            b.beam(T(-yard_w, my, zz), T(yard_w, my, zz), 0.24, 'wood')
            b.beam(T(-yard_w * 0.96, my + 0.12, zz), T(-yard_w * 0.96, my + 0.12, zz - 0.4), 0.08, 'wood_dark')
            b.beam(T(yard_w * 0.96, my + 0.12, zz), T(yard_w * 0.96, my + 0.12, zz - 0.4), 0.08, 'wood_dark')
            if sails and frac > 0.3:
                # One square sail per yard, bellied forward by the wind and narrowing a little at the foot.
                cols, rows = 6, 4
                grid = []
                for r in range(rows + 1):
                    v = r / rows
                    row = []
                    for c in range(cols + 1):
                        u = c / cols
                        half = yard_w * (0.97 - 0.08 * v)
                        belly = 2.2 * math.sin(math.pi * u) * math.sin(math.pi * (0.15 + 0.8 * v)) * strength
                        row.append(T(-half + 2 * half * u, my + 0.25 + belly + 1.0 * v, zz - 0.15 - 4.7 * v))
                    grid.append(row)
                for r in range(rows):
                    for c in range(cols):
                        b.quad(grid[r][c], grid[r][c + 1], grid[r + 1][c + 1], grid[r + 1][c], canvas)
                # Bolt-rope along the foot.
                for c in range(cols):
                    b.beam(grid[rows][c], grid[rows][c + 1], 0.06, 'rope')
                # Reef points across the sail foot.
                for j in range(6):
                    xx = -yard_w + 2 * yard_w * (j + 0.5) / 6
                    b.beam(T(xx, my + 1.0, zz - 3.4), T(xx, my + 1.25, zz - 4.5), 0.025, 'wood_dark')
        # Standing rigging to the bowsprit, stern and channels.
        top = deck + mh * 0.82
        b.rope(T(0, my, top), T(0, 44, 12.4 + rise), 0.0, 0.035)
        b.rope(T(0, my, top), T(0, -30, 8.5 + rise), 0.0, 0.035)
        for side in (-1, 1):
            b.rope(T(0, my, top), T(side * 8.6, my - 10.0, 7.0 + rise), 0.15, 0.03)
            b.rope(T(0, my, top), T(side * 8.6, my + 8.0, 7.0 + rise), 0.15, 0.03)
            # Shrouds and ratlines.
            for k in range(5):
                x0 = side * (3.0 + k * 1.25)
                b.rope(T(x0, my - 2.0, top - 0.5), T(x0, my - 4.8, 8.6 + rise), 0.0, 0.025)
                for r in range(6):
                    t = r / 6
                    z0 = top - 0.5 + (8.6 + rise - (top - 0.5)) * t
                    yy = my - 2.0 - 2.8 * t
                    b.beam(T(x0 - 0.6, yy, z0), T(x0 + 0.6, yy, z0), 0.018, 'rope')
    # A long pennant and a black stern flag with a pale skull, its staff above the stern castle.
    stern = HULL['top_z'] * 0.76 - 0.3 - 9.4 if HULL else 0.0
    for my, mh, _ in masts:
        b.cylinder(T(0, my, deck + mh), T(0, my, deck + mh + 1.4), 0.07, 'metal', 5)
        b.quad(T(0, my, deck + mh + 1.3), T(4.6, my, deck + mh + 0.7),
               T(4.6, my, deck + mh + 0.25), T(0, my, deck + mh + 0.55),
               'flag_black' if my == masts[1][0] else 'flag_red')
    b.cylinder(T(0, -30, 9.4 + stern), T(0, -30, 20.5 + stern), 0.13, 'metal', 6)
    b.quad(T(0, -30, 20.2 + stern), T(5.8, -30, 19.0 + stern), T(5.8, -30, 15.1 + stern), T(0, -30, 15.7 + stern), 'flag_black')
    b.sphere(T(2.7, -30.06, 17.6 + stern), 0.72, 'cream', (1.0, 0.06, 1.1), subdiv=0)


def props():
    b = Builder('08_props')
    # Quay and street furniture.
    for x in range(-360, 361, 44):
        if abs(x) < 16:
            continue
        lantern_post(b, x, 103, 4.7, 3.4)
    for x in (-320, -270, -210, 150, 205, 270, 320):
        for y in (146, 184):
            barrel(b, x + RNG.uniform(-1.5, 1.5), y + RNG.uniform(-1, 1), 4.7, RNG.uniform(0.8, 1.1))
        crate(b, x + RNG.uniform(-2, 2), 176 + RNG.uniform(-1, 1), 4.7, RNG.uniform(0.7, 1.2), RNG.uniform(0, 90))
    for x in range(-300, 321, 40):
        lantern_post(b, x, 326, L.UPPER_Z, 3.4)
    for x in (-250, -190, 70, 130, 190, 250):
        barrel(b, x, 370, L.UPPER_Z, 0.9)
        crate(b, x + 3, 366, L.UPPER_Z, 0.8, 12)
    # Pier clutter and fenders.
    for _, px, y0, y1, width in L.PIERS:
        for yy in (y0 - 24, y1 + 18):
            barrel(b, px + width * 0.25, yy, 5.25, 0.9)
            crate(b, px - width * 0.25, yy - 3, 5.25, 1.0, 20)
    # Buoys, rowboats and fish baskets in the water.
    for x, y, z, yaw, scale in [(-155, -205, 0.0, 20, 1.0), (145, -228, 0.0, -14, 0.9),
                                 (-270, -145, 0.0, 65, 0.8), (270, -182, 0.0, -70, 0.9)]:
        rowboat(b, x, y, 0.0, yaw, scale)
    for x, y in [(-200, -160), (190, -190), (-90, -210)]:
        b.sphere((x, y, 0.45), 0.7, 'flag_red', (1.0, 1.0, 1.0), subdiv=1)
        b.cylinder((x, y, 0.2), (x, y, 1.6), 0.12, 'metal', 6)
    # Fish baskets and nets near the market shed.
    for i in range(7):
        bx = 290 + i * 4.2
        b.cylinder((bx, 78, 4.8), (bx, 78, 5.35), 1.0, 'wood_light', 9)
        b.sphere((bx, 78, 5.4), 0.5, 'sail', (1.3, 0.6, 0.5), subdiv=0)
    for i in range(3):
        b.ring((330 + i * 3, 70, 4.9), 1.6, 0.08, 'rope', sides=12)
    # Cargo clusters, rope coils and net racks along the working quay.
    for cx, cy in ((-250, 94), (-170, 94), (120, 94), (270, 94), (-60, 84), (60, 84)):
        for i in range(2):
            crate(b, cx + i * 1.25, cy, 4.75, RNG.uniform(0.9, 1.3), RNG.uniform(-8, 8))
            barrel(b, cx - 1.8 - i * 1.1, cy + 1.4, 4.75, RNG.uniform(0.7, 1.0))
        b.ring((cx, cy + 3.0, 4.82), 0.85, 0.07, 'rope', sides=12)
    for x, y in ((274, 70), (286, 70)):
        for side in (-1, 1):
            b.beam((x, y + side * 3.2, 4.8), (x, y + side * 3.2, 9.2), 0.16, 'wood_dark')
        for i in range(6):
            yy = y - 3.0 + i * 1.2
            b.rope((x - 0.2, yy, 8.8), (x + 0.2, yy, 5.4), 0.35, 0.035)
            b.panel((x - 1.4, yy - 0.5, 8.7), (x + 1.4, yy - 0.5, 8.7),
                    (x + 1.6, yy + 0.5, 5.6), (x - 1.6, yy + 0.5, 5.6), 'rope', thick=0.04)
    # Two big cannon on the quay aimed at the harbor mouth, at the old hero model's landmark size (the TRELLIS hero
    # cannon imported as broken triangles).
    for x, y, yaw in ((-206, 88.0, 18), (210, 88.0, -14)):
        LM.cannon(b, x, y, max(L.ground(x, y), LM.QUAY_TOP), yaw, 2.5)
    # The quay anchor is procedural too (the TRELLIS one imported with scrambled triangles: playtest note 13).
    LM.anchor(b, -292, 90, max(L.ground(-292, 90), LM.QUAY_TOP), 28)
    # Gulls over the harbor mouth.
    for i in range(18):
        gx = RNG.uniform(-320, 320)
        gy = RNG.uniform(-300, 40)
        gz = RNG.uniform(20, 58)
        b.sphere((gx, gy, gz), 0.22, 'sail', (1.0, 0.6, 0.5), subdiv=0)
        b.quad((gx - 1.1, gy, gz), (gx, gy, gz + 0.35), (gx + 1.1, gy, gz), (gx, gy, gz - 0.1), 'sail')
    # Potted palms on the upper terrace and by tavern doors.
    for x, y in [(-300, 300), (-170, 300), (120, 300), (280, 300), (-40, 236), (45, 236)]:
        b.cylinder((x, y, L.ground(x, y) + 0.3), (x, y, L.ground(x, y) + 1.2), 1.0, 'clay' if 'clay' in L.COLORS else 'coral', 8, radius_b=0.8)
        palm(b, x, y, L.ground(x, y) + 1.1, 0, 0.38, RNG)
    return b


def rowboat(b, x, y, z, yaw, scale=1.0):
    # A simple clinker rowboat: two side strips, a floor and a transom.
    def T(lx, ly, lz):
        return local(x, y, yaw, lx * scale, ly * scale) + (z + lz * scale,)
    for side in (-1, 1):
        b.panel(T(side * 1.4, -4.2, 1.2), T(side * 1.4, 4.2, 1.4),
                T(side * 1.0, 4.8, 0.4), T(side * 1.0, -4.8, 0.4), 'wood', thick=0.04)
        b.panel(T(side * 1.4, -4.2, 1.2), T(side * 1.4, 4.2, 1.4),
                T(side * 1.45, 4.2, 1.8), T(side * 1.45, -4.2, 1.6), 'wood_dark', thick=0.04)
    b.box((*local(x, y, yaw, 0, 0), z + 0.7 * scale), (2.0 * scale, 8.0 * scale, 0.2 * scale), 'wood_light', yaw)
    b.panel(T(-1.4, -4.2, 1.2), T(1.4, -4.2, 1.2), T(1.0, -4.8, 0.4), T(-1.0, -4.8, 0.4), 'wood', thick=0.04)
    b.beam(T(-1.6, 0, 1.5), T(1.6, 0, 1.5), 0.12, 'wood_dark')
    b.beam(T(0, -3.0, 1.1), T(0, 3.0, 1.3), 0.08, 'wood_dark')


def vegetation():
    # Trees, palms, shrubs and flowering mounds are instanced from flora.py by the build; this mesh carries the
    # one-off understory: vines, ferns, bananas and crest grass.
    b = Builder('09_vegetation')
    sc = L.scatter()
    # Vines on the wet east cliff and the west headland.
    for y in range(90, 230, 12):
        vine(b, 438 - RNG.uniform(0, 8), y, 48 - RNG.uniform(0, 8), RNG.uniform(12, 26), RNG)
    for y in range(-80, 150, 16):
        vine(b, -430 - RNG.uniform(0, 12), y, 42 - RNG.uniform(0, 12), RNG.uniform(8, 18), RNG)
    # Hanging green breaks up the bare cliff bands along both headland shores.
    for side in (-1, 1):
        for y in range(-220, 62, 11):
            x = side * (L.bay_half(y) + RNG.uniform(16.0, 58.0))
            z = L.height(x, y)
            if z > 8.0:
                vine(b, x, y, z + RNG.uniform(0.5, 3.0), RNG.uniform(10, 24), RNG)
    # Ferns and banana plants give the understory a second layer.
    for i, (x, y, z, _, scale) in enumerate(sc['bushes']):
        if i % 5 == 0:
            fern(b, x + RNG.uniform(-1, 1), y + RNG.uniform(-1, 1), z,
                 RNG.uniform(0, 360), RNG.uniform(0.75, 1.25), RNG)
        if i % 13 == 0:
            banana(b, x + RNG.uniform(-1.5, 1.5), y + RNG.uniform(-1.5, 1.5), z,
                   RNG.uniform(0, 360), RNG.uniform(0.8, 1.3), RNG)
    # Dry crest grass catches the late light on both headlands.
    for _ in range(900):
        side = -1 if RNG.random() < 0.5 else 1
        x = side * RNG.uniform(420, 790)
        y = RNG.uniform(-220, 500)
        z = L.height(x, y)
        if z < 44.0 or L.is_water(x, y):
            continue
        grass_tuft(b, x, y, z + 0.05, RNG.uniform(0, 360), RNG.uniform(0.7, 1.4), RNG)
    return b


def split_lot(spec, rng):
    """Break a wide waterfront block into narrow houses with their own rooflines.

    The painted references read as many 8-14 m facades, while the generated
    lots are 34-46 m blocks.  Splitting them keeps the same footprint but gives
    the town the varied height, colour and roof rhythm the cove needs.
    """
    key, x, y, z, w, d, h, floors, style, yaw, roof = spec
    if style == 'warehouse' or w < 20.0:
        return [spec]
    n = 2 if w < 34.0 else 3
    weights = ([0.46, 0.54] if n == 2 else [0.30, 0.38, 0.32])
    jitter = [rng.uniform(-0.045, 0.045) for _ in range(n)]
    scale = sum(weights)
    weights = [max(0.2, weight / scale + jitter[i]) for i, weight in enumerate(weights)]
    scale = sum(weights)
    weights = [weight / scale for weight in weights]
    roofs = ('roof_terra', 'roof_teal', 'roof_terra_light', 'roof_slate', 'roof_terra')
    out = []
    cursor = -w / 2
    for i, weight in enumerate(weights):
        sw = w * weight
        cx = cursor + sw / 2
        px, py = local(x, y, yaw, cx, 0.0)
        out.append((f'{key}-{i}', px, py, z, max(6.0, sw - 0.35), d,
                    h + rng.uniform(-1.1, 1.3), max(1, floors + (1 if rng.random() < 0.22 else 0)),
                    style, yaw, roofs[(i + sum(map(ord, key))) % len(roofs)]))
        cursor += sw
    return out


MODULES = {
    '01_terrain': terrain,
    '02_harbor': harbor,
    '03_town_lower': lower_town,
    '04_market': market,
    '05_town_upper': upper_town,
    '06_landmarks': landmarks,
    '07_ships': ships,
    '08_props': props,
    '09_vegetation': vegetation,
}
