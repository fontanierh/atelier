"""The east river and its two-tier waterfall: slot-canyon river, upper cascade, ledge pool and the 30 m sea fall.

layout.py carves the canyon, pool and lip notch into the terrain and owns the water levels; this module draws the
water and its dressing on top: curved ribbon sheets that follow the cliff, plunge foam and mist, wet rock, a rope
bridge over the slot and the ledge shrine. Plain Python.
"""
import math
import random

from brinecove import layout as L
from brinecove import rocks
from brinecove.kit import bush, cell_uvs, fern, lantern_post, vine

TAU = math.pi * 2


_CORNERS = {}


def mesh_height(x, y):
    """The highest the built ground mesh can stand at (x, y): ground.py samples the layout on a 4 m grid and jitters
    steep corners by up to 0.84 m sideways and 2.2 m up, so across the fall's narrow notch its triangles bridge in
    front of the analytic cliff and cut the curtain off on a diagonal. Every triangle lies under its cell's corners."""
    from brinecove import ground_sampling as G
    import brinecove.region as R
    ox0, oy0, ox1, oy1 = R.OUTER
    if 'axes' not in _CORNERS:
        _CORNERS['axes'] = (G._axis(ox0, ox1, G.STEP), G._axis(oy0, oy1, G.STEP))
    xs, ys = _CORNERS['axes']
    sx, sy = xs[1] - xs[0], ys[1] - ys[0]
    top = L.height(x, y)
    for i in range(int((x - 0.9 - ox0) // sx), int((x + 0.9 - ox0) // sx) + 2):
        for j in range(int((y - 0.9 - oy0) // sy), int((y + 0.9 - oy0) // sy) + 2):
            if 0 <= i < len(xs) and 0 <= j < len(ys):
                if (i, j) not in _CORNERS:
                    _CORNERS[i, j] = G.jag_point((xs[i], ys[j], L.ground(xs[i], ys[j])))[2]
                top = max(top, _CORNERS[i, j])
    return top


def face_x(y, z, x_hi, x_lo=425.0):
    """The ground mesh's face x at height z on row y, searching seaward from x_hi."""
    if mesh_height(x_hi, y) <= z:
        return x_hi
    lo, hi = x_lo, x_hi
    for _ in range(24):
        mid = (lo + hi) / 2
        if mesh_height(mid, y) > z:
            hi = mid
        else:
            lo = mid
    return lo


def sheet(b, lip_x, y0, y1, top, bottom, rng, throw=4.0, segments=12, widen=0.18, ragged=0.0):
    """One curtain of falling water from a lip at lip_x toward -x, widening (or, with widen < 0, narrowing) as it falls.

    ragged drops parts of the crest by up to that many metres, so the lip never reads as a ruler edge.

    The streak texture's alpha breaks the curtain up; a darker water body sits just behind it. Strips of separate
    ribbons overlapped into a shattered-glass staircase.
    """
    cols = max(4, int((y1 - y0) / 1.1))
    rows = max(segments, 20)
    u_span = (y1 - y0) / 5.0
    phase = rng.uniform(0, TAU)
    grid = []
    for k in range(rows + 1):
        s = k / rows
        spread = widen * (y1 - y0) * s * s
        row = []
        for c in range(cols + 1):
            t = c / cols
            y = y0 - spread + (y1 - y0 + 2 * spread) * t
            z = top - (top - bottom) * s - ragged * (0.5 + 0.5 * math.sin(t * 7.0 + phase)) * (1 - s)
            # Ballistic throw off the lip, a little ripple across the width, and never inside the rock.
            x = lip_x - throw * math.sqrt(s) - 0.3 + 0.35 * math.sin(t * 9.0 + phase) * s
            x = min(x, face_x(y, z, lip_x) - 0.8)
            row.append((x, y, z, t * u_span, (top - z) / 7.0))
        grid.append(row)
    out = (-1.0, 0.0, 0.1)
    for k in range(rows):
        for c in range(cols):
            p = (grid[k][c], grid[k][c + 1], grid[k + 1][c + 1], grid[k + 1][c])
            b.face([q[:3] for q in p], 'waterfall', [(q[3], q[4]) for q in p], (out, out, out, out))
    # Loose strands peel off both edges, so the curtain has ragged sides instead of a cut slab.
    for side in (0, cols):
        for _ in range(3):
            y = grid[0][side][1] + (rng.uniform(-1.6, -0.3) if side == 0 else rng.uniform(0.3, 1.6))
            w = rng.uniform(0.4, 0.9)
            reach = rng.uniform(0.5, 1.0)
            u0 = rng.uniform(0, 3)
            prev = None
            for k in range(rows + 1):
                s = k / rows * reach
                z = top - (top - bottom) * s
                x = min(lip_x - throw * math.sqrt(s) - 0.2, face_x(y, z, lip_x) - 0.6)
                cur = ((x, y - w / 2, z), (x, y + w / 2, z), (top - z) / 7.0)
                if prev:
                    b.face((prev[0], prev[1], cur[1], cur[0]), 'waterfall',
                           ((u0, prev[2]), (u0 + 0.15, prev[2]), (u0 + 0.15, cur[2]), (u0, cur[2])), (out,) * 4)
                prev = cur


def mist(b, x, y, z, radius, count, rng, height=10.0):
    """Spray at a plunge: large feathered billow cards, low and wide, overlapping into one bright cloud.

    Small crossed cards with sharp puffs read as cotton balls (the review renders before the bridge paintings).
    """
    for i in range(count):
        a = rng.uniform(0, TAU)
        d = rng.uniform(0, radius) * (0.4 + 0.6 * i / max(1, count - 1))
        px, py = x + math.cos(a) * d * 0.7, y + math.sin(a) * d
        size = rng.uniform(9.0, 16.0) * (1.0 - 0.3 * d / max(radius, 1e-3))
        pz = z + size * 0.25 + rng.uniform(0.0, height) * (1.0 - d / max(radius, 1e-3)) ** 2
        yaw = rng.uniform(0, math.pi)
        b.card((px, py, pz), (math.cos(yaw), math.sin(yaw), 0.0), size, size * 0.75, 'mist',
               ((0, 0), (1, 0), (1, 1), (0, 1)))


def foam_ring(b, x, y, z, r0, r1, rng, segments=28, squash=1.0):
    """Plunge foam: an annulus in the animated foam material, v running 0 at the inner edge to 1 at the outer.

    The material drifts the lace outward and breathes the outer edge with time, so the foam spreads and fades
    instead of lying on the water as static white cards (playtest notes 4 and 9)."""
    wobble = [rng.uniform(0.85, 1.15) for _ in range(segments)]
    span = TAU * (r0 + r1) / 2 / 4.0
    for i in range(segments):
        j = (i + 1) % segments
        a0, a1 = TAU * i / segments, TAU * (i + 1) / segments
        w0, w1 = wobble[i], wobble[j]
        pts = [(x + math.cos(a0) * r0 * squash, y + math.sin(a0) * r0, z),
               (x + math.cos(a1) * r0 * squash, y + math.sin(a1) * r0, z),
               (x + math.cos(a1) * r1 * w1 * squash, y + math.sin(a1) * r1 * w1, z),
               (x + math.cos(a0) * r1 * w0 * squash, y + math.sin(a0) * r1 * w0, z)]
        u0, u1 = span * i / segments, span * (i + 1) / segments
        b.face(pts, 'foam', ((u0, 0.0), (u1, 0.0), (u1, 1.0), (u0, 1.0)))


def pool_surface(b, x0, x1, y_half, level, mat, step=3.0):
    """A flat water grid clipped to the carved bed, so the shoreline follows the terrain.

    A cell needs its centre and most corners under the level: with any one corner, the grid ran out over the
    cliff below the lip as a flat grey plate.
    """
    x = x0
    while x < x1:
        y = L.GORGE_Y - y_half
        while y < L.GORGE_Y + y_half:
            corners = ((x, y), (x + step, y), (x + step, y + step), (x, y + step))
            wet = sum(L.height(cx, cy) < level for cx, cy in corners)
            if wet >= 3 and L.height(x + step / 2, y + step / 2) < level - 0.05:
                b.quad(*[(cx, cy, level) for cx, cy in corners], mat)
            y += step
        x += step


def river_surface(b, x0, x1, half=5.6, step=4.0):
    x = x0
    while x < x1:
        za, zb = L.river_level(x), L.river_level(x + step)
        b.quad((x, L.GORGE_Y - half, za), (x + step, L.GORGE_Y - half, zb),
               (x + step, L.GORGE_Y + half, zb), (x, L.GORGE_Y + half, za), 'water_mid')
        x += step


def waterfall(b):
    rng = random.Random(5501)
    g = L.gorge_levels()
    lower, upper, pool, river = g['lower'], g['upper'], g['pool'], g['river']
    # River down the slot canyon, with broken white water where it steepens toward the lip.
    river_surface(b, upper - 3.0, 684.0)
    # The river springs from a boulder choke at the slot's head, just inside the region's own ground: east of it the
    # collar eases the ground into the far hills.
    for _ in range(11):
        px, py = rng.uniform(682.0, 699.0), L.GORGE_Y + rng.uniform(-8.0, 8.0)
        top = max(L.river_level(px) + rng.uniform(4.0, 11.0), L.height(px, py) + rng.uniform(-2.0, 1.0))
        r = rng.uniform(3.0, 6.0)
        rocks.boulder(b, px, py, L.river_level(px) - 1.0, (r * 2.0, r * 1.7, top - L.river_level(px) + 2.0), rng,
                      'rock_dark', bury=0.25)
    # White water down the steepening run: a strip of animated foam along the river, its lace flowing downstream.
    x = upper - 2.0
    while x < upper + 40.0:
        za, zb = L.river_level(x) + 0.05, L.river_level(x + 4.0) + 0.05
        b.face(((x, L.GORGE_Y - 3.6, za), (x + 4.0, L.GORGE_Y - 3.6, zb), (x + 4.0, L.GORGE_Y + 3.6, zb),
                (x, L.GORGE_Y + 3.6, za)), 'foam',
               (((x - upper) / 4.0, 0.0), ((x - upper) / 4.0 + 1.0, 0.0), ((x - upper) / 4.0 + 1.0, 1.0),
                ((x - upper) / 4.0, 1.0)))
        x += 4.0
    # Upper cascade: out of the slot onto the ledge pool.
    upper_lip = face_x(L.GORGE_Y, river - 0.5, upper + 4.0) + 0.6
    sheet(b, upper_lip, L.GORGE_Y - 4.8, L.GORGE_Y + 4.8, river + 0.2, pool - 0.3, rng, throw=2.5, segments=8)
    mist(b, upper_lip - 4.0, L.GORGE_Y, pool, 6.0, 8, rng, height=4.0)
    lower_lip = face_x(L.GORGE_Y, pool - 0.6, lower + 4.0) + 0.4
    pool_surface(b, lower_lip, upper_lip, 14.0, pool, 'water_shallow')
    # Lower fall: the pool spills through the notch in a wide, 30 m sheet into the sea.
    # It widens only a little: where its edges spread over the notch's flanks, the cliff toe stands proud of the lip
    # and the clamp to the face dragged the curtain's corner out along the slope (note 9 third capture). The paired
    # ribbon beside it hugged the same toe as a white smear with rock showing through, so it is gone.
    # Since the r10 notes (5: 'looks too square') it falls as four tongues of different width, crest height and
    # length, split by dark wet rock ribs on the lip, after references/redesign/waterfall.jpg.
    tongues = ((-8.6, -4.7, -0.7, -0.4, 4.0, -0.06), (-3.3, 1.3, 0.0, -0.4, 4.8, 0.03),
               (2.3, 5.1, -0.35, -0.4, 4.4, -0.05), (6.1, 8.3, -1.5, pool * 0.38, 3.2, -0.12))
    for lo, hi, crest, foot, throw, widen in tongues:
        sheet(b, lower_lip, L.GORGE_Y + lo, L.GORGE_Y + hi, pool + crest, foot, rng, throw=throw, segments=24,
              widen=widen, ragged=0.45)
    # A second, slightly proud layer thickens the main tongue so it reads white.
    sheet(b, lower_lip - 0.5, L.GORGE_Y - 2.6, L.GORGE_Y + 0.6, pool - 0.3, -0.4, rng, throw=5.2, segments=24,
          widen=0.02, ragged=0.3)
    # The short north tongue breaks onto a ledge: spray where it lands.
    mist(b, face_x(L.GORGE_Y + 7.2, pool * 0.38, lower + 4.0) - 2.5, L.GORGE_Y + 7.2, pool * 0.38, 3.0, 4, rng,
         height=2.0)
    # Wet rock ribs between the tongues, standing on the lip and running a little way down the face.
    for yy, height in ((-4.0, 5.5), (1.8, 4.2), (5.6, 6.0)):
        py = L.GORGE_Y + yy
        px = face_x(py, pool - 2.0, lower + 4.0) + 0.6
        rocks.boulder(b, px, py, pool - height, (3.4, 1.5, height + 1.0), rng, 'rock_dark', bury=0.1, strata=0.8)
        rocks.boulder(b, px - 0.8, py + rng.uniform(-0.3, 0.3), pool * 0.55 - 2.0, (2.4, 1.3, 4.0), rng,
                      'rock_dark', bury=0.1, strata=0.8)
    # Froth down the curtain and white water spilling over the lip: the painting's fall is a churning white
    # column, not one smooth sheet.
    for k in range(5):
        z = pool * (0.85 - 0.17 * k)
        mist(b, face_x(L.GORGE_Y, z, lower + 4.0) - 3.5, L.GORGE_Y + rng.uniform(-3.0, 3.0), z, 4.0 + k, 3, rng,
             height=2.0)
    foam_ring(b, upper_lip - 4.0, L.GORGE_Y, pool + 0.05, 2.0, 9.0, rng, 20, squash=0.8)
    base_x = face_x(L.GORGE_Y, 0.5, lower) - 6.0
    mist(b, base_x, L.GORGE_Y, 0.0, 16.0, 22, rng, height=10.0)
    # Plunge foam spreading from the curtain's foot and fading out over the sea; nothing static on open water.
    foam_ring(b, base_x, L.GORGE_Y, 0.07, 4.0, 22.0, rng, 32, squash=0.75)
    # Wet boulders in the plunge and on the pool lip, and dark stone framing the falls.
    for _ in range(14):
        a = rng.uniform(0, TAU)
        d = rng.uniform(7.0, 16.0)
        px, py = base_x + math.cos(a) * d * 0.7, L.GORGE_Y + math.sin(a) * d
        r = rng.uniform(1.2, 2.8)
        rocks.boulder(b, px, py, -0.6, (r * 2.0, r * 1.7, rng.uniform(2.4, 5.0)), rng, 'rock_dark', bury=0.4)
    for side in (-1, 1):
        for k in range(7):
            # Clear of the curtain, which flares to about 11 m off the axis at its foot (and the paired ribbon at
            # +9..+12): framing stone inside that hid the lower fall behind slanted faces, a cut-off triangle.
            yy = L.GORGE_Y + side * rng.uniform(14.0, 19.0)
            xx = lower - rng.uniform(1.0, 9.0)
            top = L.height(xx + 3.0, yy) + rng.uniform(-1.0, 1.5)
            r = rng.uniform(2.2, 3.6)
            rocks.boulder(b, xx, yy, L.height(xx, yy) - 1.5, (r * 1.8, r * 2.0, top - L.height(xx, yy) + 3.0), rng,
                          'rock_dark', bury=0.2, strata=0.75)
    # Ledged outcrops step up both walls of the slot canyon past the rope bridge, clear of the river: the carved walls
    # alone read as two flat planes in a V (note 9 review).
    for side in (-1, 1):
        x = upper + 12.0  # an outcrop spans ~2.6 radii along the wall: clear of the rope bridge at upper + 3.5
        while x < upper + 64.0:
            yy = L.GORGE_Y + side * rng.uniform(9.0, 10.5)
            r = rng.uniform(3.2, 4.6)
            base = L.height(x, yy) - 2.0
            crest = L.height(x, L.GORGE_Y + side * 14.0) + rng.uniform(-1.0, 1.5)
            top = rocks.outcrop(b, x, yy, base, r, max(6.0, crest - base), rng, (-side, 0.0),
                                rng.choice(('rock', 'rock_dark', 'rock_light')))
            if rng.random() < 0.7:
                vine(b, x + rng.uniform(-2.0, 2.0), yy - side * 1.5, top, rng.uniform(4.0, 9.0), rng)
            x += rng.uniform(7.5, 10.5)
    # And on the open V below the bridge, between the two lips: stepped ledges up both flanks, below the deck.
    for side in (-1, 1):
        x = lower + 8.0
        while x < upper - 2.0:
            yy = L.GORGE_Y + side * rng.uniform(13.0, 16.0)
            r = rng.uniform(3.0, 4.2)
            base = L.height(x, yy) - 2.0
            crest = min(L.height(x, L.GORGE_Y + side * 20.0), L.gorge_levels()['river'] + 12.0)
            top = rocks.outcrop(b, x, yy, base, r, max(5.0, crest - base), rng, (-side, 0.0),
                                rng.choice(('rock', 'rock_light')))
            if rng.random() < 0.6:
                bush(b, x, yy + side * 1.5, top - 0.3, 0.0, rng.uniform(0.9, 1.5), rng)
            x += rng.uniform(8.0, 11.0)
    for _ in range(10):
        px = rng.uniform(lower + 2.0, upper_lip - 3.0)
        py = L.GORGE_Y + rng.choice((-1, 1)) * rng.uniform(4.0, 11.0)
        r = rng.uniform(0.8, 1.8)
        rocks.boulder(b, px, py, pool - 0.4, (r * 2.0, r * 1.6, rng.uniform(1.6, 3.0)), rng, 'rock_dark', bury=0.4)
    # Ferns, moss mounds and hanging vines on the wet canyon walls.
    for _ in range(60):
        px = rng.uniform(lower - 6.0, upper + 60.0)
        py = L.GORGE_Y + rng.choice((-1, 1)) * rng.uniform(6.0, 16.0)
        pz = L.height(px, py)
        if L.slope(px, py) > 1.6:
            vine(b, px, py, pz + 0.5, rng.uniform(4.0, 12.0), rng)
        elif rng.random() < 0.5:
            fern(b, px, py, pz, rng.uniform(0, 360), rng.uniform(0.9, 1.5), rng)
        else:
            bush(b, px, py, pz, 0.0, rng.uniform(0.6, 1.1), rng)
    # Low jungle on the shelves either side of the falls: headland_plantable keeps trees out of the town's view of
    # the falls, which left the shelves bare grass.
    shelf = random.Random(5509)
    for _ in range(2800):
        px, py = shelf.uniform(lower - 40.0, 650.0), shelf.uniform(L.GORGE_Y - 80.0, L.GORGE_Y + 90.0)
        if L.in_gorge(px, py, 1.5) or L.is_water(px, py) or L.in_lot(px, py, 4.0) or L.on_street(px, py, 3.0):
            continue
        pz = L.height(px, py)
        if pz < 4.0 or L.slope(px, py) > 1.0:
            continue
        if shelf.random() < 0.65:
            bush(b, px, py, pz - 0.1, 0.0, shelf.uniform(1.2, 2.4), shelf)
        else:
            fern(b, px, py, pz, shelf.uniform(0, 360), shelf.uniform(1.2, 2.0), shelf)
    # The painting's lantern bridge spans the slot at its mouth, where the sea and the harbor can see it.
    rope_bridge(b, upper + 3.5, lanterns=True)
    shrine(b, rng, lower, upper_lip)


def rope_bridge(b, x, lanterns=False, half=17.0):
    """A sagging plank bridge across the gorge, anchored where the ground on each side is highest."""
    y0, y1 = L.GORGE_Y - half, L.GORGE_Y + half
    z0, z1 = L.height(x, y0) + 0.6, L.height(x, y1) + 0.6
    if lanterns:
        for y, z in ((y0, z0), (y1, z1)):
            for side in (-1, 1):
                lantern_post(b, x + side * 1.9, y, z - 0.6, 2.6)
    for y, z in ((y0, z0), (y1, z1)):
        for side in (-1, 1):
            b.beam((x + side * 1.3, y, z - 2.5), (x + side * 1.3, y, z + 1.6), 0.26, 'wood_dark')
    planks = 22
    for i in range(planks + 1):
        t = i / planks
        y = y0 + (y1 - y0) * t
        z = z0 + (z1 - z0) * t - 2.4 * math.sin(math.pi * t)
        b.box((x, y, z), (2.6, 0.62, 0.12), 'wood_light' if i % 4 else 'wood', (i % 3 - 1) * 3.0)
    for side in (-1, 1):
        b.rope((x + side * 1.3, y0, z0 + 1.2), (x + side * 1.3, y1, z1 + 1.2), 2.3, 0.07, segments=12)
        b.rope((x + side * 1.3, y0, z0), (x + side * 1.3, y1, z1), 2.4, 0.06, segments=12)
        for i in range(1, 9):
            t = i / 9
            y = y0 + (y1 - y0) * t
            z = z0 + (z1 - z0) * t - 2.4 * math.sin(math.pi * t)
            b.beam((x + side * 1.3, y, z), (x + side * 1.3, y, z + 1.2 + 0.1 * math.sin(math.pi * t)), 0.04, 'rope')


def shrine(b, rng, lower, upper_lip):
    """A small stone shrine with lanterns on the flat ledge above the pool, its back tucked against the cliff
    riser, facing the harbor. Its podium reaches down into the rock wherever the ground drops away (note 9 second
    review: the old site straddled the ledge's lip and its base hung in the air over the cliff slope)."""
    sx, sy = (lower + upper_lip) / 2 + 8.0, L.GORGE_Y + 21.0
    foot = [L.height(sx + dx, sy + dy) for dx in (-3.7, -1.8, 0.0, 1.8, 3.7) for dy in (-3.1, 0.0, 3.1)]
    sz = max(foot) + 0.4
    low = min(foot) - 1.5
    b.box((sx, sy, (low + sz - 0.1) / 2), (7.0, 5.8, sz - 0.1 - low), 'stone')
    b.box((sx, sy, sz + 0.3), (7.4, 6.2, 0.8), 'stone')
    b.box((sx, sy, sz + 2.1), (4.4, 3.6, 3.0), 'stone_light')
    b.box((sx - 2.25, sy, sz + 1.6), (0.3, 1.6, 2.2), 'wood_dark')
    b.hip_roof((sx, sy, sz + 3.6), 4.4, 3.6, sz + 3.6, 1.8, 'roof_teal', 0, overhang=0.7)
    for dy in (-2.4, 2.4):
        lantern_post(b, sx - 3.4, sy + dy, sz + 0.6, 2.2)
    # Steps down off the podium's front, each a solid block to the ground, stopping where they meet it.
    for k in range(4):
        x, tread = sx - 4.1 - k * 0.8, sz + 0.35 - k * 0.35
        g = max(L.height(x + dx, sy + dy) for dx in (-0.4, 0.4) for dy in (-1.2, 1.2))
        if tread < g + 0.1:
            break
        b.box((x, sy, (tread + g - 0.6) / 2), (0.8, 2.4, tread - g + 0.6), 'stone')
    for _ in range(5):
        b.card((sx + rng.uniform(-3, 3), sy + 3.2, sz + rng.uniform(1.5, 3.5)), (0, -1, 0.2), 1.4, 1.4,
               'leaf_mid', cell_uvs(rng.randrange(4)))
