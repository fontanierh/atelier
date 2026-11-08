"""Faceted sea-cliff rock for Brinecove: stacked prism outcrops, and smooth value noise for terrain materials.

The concept cliffs are pale, blocky stone in vertical columns and stepped drums, with jungle on every shelf. A sampled
heightfield alone reads as a smooth ramp with a striped texture, so the steep faces are dressed with irregular prisms
that protrude from the slope, split into drums so horizontal strata catch the light. Plain Python.
"""
import math
import random

from brinecove import layout as L
from brinecove import region as R
from brinecove.kit import bush, fern, leaf_canopy

TAU = math.pi * 2
# Palette entries for the redesign's materials. They live here, not in layout.py: the atlas geography signature hashes
# layout.py and ground.py, and these are material colours, not terrain.
L.COLORS.update({'terrain': '#8a8f58', 'cover_fern': '#4f7a34', 'cover_fern_light': '#6f9a3e', 'cover_grass': '#6d8f3c',
                 'cover_grass_dry': '#a99a58', 'cover_leaf': '#3f6c35', 'cover_leaf_light': '#5d8a3f'})


def _hash(ix, iy, seed):
    n = (ix * 374761393 + iy * 668265263 + seed * 2147483647) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def value_noise(x, y, seed=0):
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a = _hash(ix, iy, seed)
    b = _hash(ix + 1, iy, seed)
    c = _hash(ix, iy + 1, seed)
    d = _hash(ix + 1, iy + 1, seed)
    return (a + (b - a) * sx) + ((c + (d - c) * sx) - (a + (b - a) * sx)) * sy


def fbm(x, y, scale=60.0, octaves=4, seed=0):
    """Fractal value noise in [0, 1], with features about scale metres across."""
    total, amp, norm = 0.0, 1.0, 0.0
    fx, fy = x / scale, y / scale
    for o in range(octaves):
        total += value_noise(fx, fy, seed + o * 31) * amp
        norm += amp
        amp *= 0.5
        fx, fy = fx * 2.03, fy * 2.03
    return total / norm


# The ground the game actually builds. build.py sets FINAL to the collar-eased ground, where the region is joined to
# the far hills: there the layout's heights are tens of metres off (the north collar climbs 60 m in 70 m, the
# backdrop cliff of playtest note 7; the east collar drops 40 m to the sea under notes 1-4). Dressing placed on the
# layout there floated, sank or missed the real cliffs. The review scene leaves it unset and keeps the layout.
FINAL = None
FIXED = ('final',)  # anchor for faces already placed on the final ground: the collar must not move them again


def ground(x, y):
    return FINAL(x, y) if FINAL is not None else L.height(x, y)


def uphill(x, y, step=4.0):
    gx = (ground(x + step, y) - ground(x - step, y)) / (2 * step)
    gy = (ground(x, y + step) - ground(x, y - step)) / (2 * step)
    n = math.hypot(gx, gy)
    return (gx / n, gy / n, n) if n > 1e-6 else (0.0, 1.0, 0.0)


def prism(b, centre, z0, z1, radius, along, rng, mat, top_mat=None, squash=0.72, sides=None, tilt=0.0, bulge=True):
    """An irregular vertical prism, elongated along the contour, with a top tilted downhill by tilt metres.

    bulge rounds the drum into an eroded boss (sea boulders); without it the sides stay flat fractured planes."""
    sides = sides or rng.randint(5, 7)
    ax, ay = along
    px, py = -ay, ax  # out of the slope (downhill is -uphill; callers pass along = contour direction)
    ring = []
    for i in range(sides):
        a = TAU * i / sides + rng.uniform(-0.25, 0.25)
        r = radius * rng.uniform(0.72, 1.12)
        u, v = math.cos(a) * r, math.sin(a) * r * squash
        ring.append((centre[0] + ax * u + px * v, centre[1] + ay * u + py * v, u, v))
    shrink = rng.uniform(0.82, 0.96)
    bottom = [(x, y, z0) for x, y, _, _ in ring]
    top = []
    for x, y, u, v in ring:
        tx = centre[0] + (x - centre[0]) * shrink
        ty = centre[1] + (y - centre[1]) * shrink
        top.append((tx, ty, z1 - tilt * (v / max(radius * squash, 1e-3)) + rng.uniform(-0.25, 0.25)))
    # A bulging middle ring rounds each drum into an eroded boss instead of a cut block.
    mid = []
    for (bx, by, bz), (tx, ty, tz) in zip(bottom, top):
        k = rng.uniform(1.04, 1.16) if bulge else rng.uniform(0.98, 1.03)
        mx, my = (bx + tx) / 2, (by + ty) / 2
        mid.append((centre[0] + (mx - centre[0]) * k, centre[1] + (my - centre[1]) * k,
                    (bz + tz) / 2 + rng.uniform(-0.3, 0.3)))
    for i in range(sides):
        j = (i + 1) % sides
        b.quad(bottom[i], bottom[j], mid[j], mid[i], mat)
        b.quad(mid[i], mid[j], top[j], top[i], mat)
    c = (sum(p[0] for p in top) / sides, sum(p[1] for p in top) / sides,
         sum(p[2] for p in top) / sides + rng.uniform(0.0, 0.35))
    for i in range(sides):
        b.tri(top[i], top[(i + 1) % sides], c, top_mat or mat)


_ICO = {}


def _icosphere(level):
    """Unit icosphere (vertices, triangles), cached per subdivision level."""
    if level in _ICO:
        return _ICO[level]
    t = (1 + 5 ** 0.5) / 2
    verts = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
             (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    verts = [tuple(c / math.sqrt(sum(k * k for k in v)) for c in v) for v in verts]
    tris = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
            (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11),
            (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    for _ in range(level):
        mids, out = {}, []

        def mid(i, j):
            key = (min(i, j), max(i, j))
            if key not in mids:
                m = [(a + b) / 2 for a, b in zip(verts[i], verts[j])]
                n = math.sqrt(sum(c * c for c in m))
                verts.append(tuple(c / n for c in m))
                mids[key] = len(verts) - 1
            return mids[key]
        for a, b_, c in tris:
            ab, bc, ca = mid(a, b_), mid(b_, c), mid(c, a)
            out += [(a, ab, ca), (b_, bc, ab), (c, ca, bc), (ab, bc, ca)]
        tris = out
    _ICO[level] = (verts, tris)
    return _ICO[level]


def boulder(b, x, y, base, size, rng, mat='rock', yaw=None, bury=0.35, strata=0.55, level=None, lean=(0.0, 0.0),
            fixed=False):
    """One natural rock: a noise-displaced icosphere with soft horizontal bedding, its foot buried in the ground.

    size is (length, width, height) in metres; base is the ground height under it. Smooth vertex normals round the
    shoulders and the terrace steps of the bedding catch the light as fractured ledges, as in the approved rock
    concept; the material projects its texture in world space, so the mesh needs no UVs. The faces share one anchor,
    so the collar moves the rock whole (build.split)."""
    sx, sy, sz = size
    # Only the largest masses need the finer sphere; the fracture planes carry the shape of the rest.
    level = level if level is not None else (2 if max(sx, sy, sz) > 22.0 else 1)
    verts, tris = _icosphere(level)
    yaw = rng.uniform(0, TAU) if yaw is None else yaw
    ca, sa = math.cos(yaw), math.sin(yaw)
    seed = rng.randrange(1 << 20)
    step = rng.uniform(0.22, 0.34)
    cz = base - sz * bury + sz * 0.5
    # Two to four fracture planes cut flat faces into the sides, so the rock reads as split stone, not a pebble.
    cuts = []
    for _ in range(rng.randint(2, 4)):
        a, e = rng.uniform(0, TAU), rng.uniform(-0.35, 0.5)
        cuts.append(((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e)), rng.uniform(0.55, 0.8)))
    # The crown tilts and breaks unevenly: a level clamp left small rocks with a flat tabletop (note 3 review).
    ta = rng.uniform(0, TAU)
    tilt = rng.uniform(0.06, 0.2)
    tx, ty = math.cos(ta) * tilt, math.sin(ta) * tilt
    pts = []
    for vx, vy, vz in verts:
        r = 1.0 + 0.22 * (value_noise(vx * 1.6 + vz, vy * 1.6 - vz, seed) - 0.5) \
            + 0.10 * (value_noise(vx * 4.1 + vz * 2, vy * 4.1, seed + 7) - 0.5)
        px, py, pz = vx * r, vy * r, vz * r
        # Bedding: pull heights toward terraces, then cap the crown in a tilted, broken weathered top.
        for (nx, ny, nz), d in cuts:
            over = px * nx + py * ny + pz * nz - d
            if over > 0:
                px, py, pz = px - nx * over, py - ny * over, pz - nz * over
        q = round(pz / step) * step
        pz = pz + (q - pz) * strata
        cap = 0.74 + 0.16 * value_noise(vx * 2.2, vy * 2.2, seed + 3) + tx * px + ty * py
        if pz > cap:
            pz = cap + (pz - cap) * 0.3
        lx, ly, lz = px * sx * 0.5, py * sy * 0.5, pz * sz * 0.5
        lx, ly = lx + lean[0] * lz, ly + lean[1] * lz
        pts.append((x + lx * ca - ly * sa, y + lx * sa + ly * ca, cz + lz))
    normals = [[0.0, 0.0, 0.0] for _ in pts]
    for i, j, k in tris:
        (ax, ay, az), (bx, by, bz), (qx, qy, qz) = pts[i], pts[j], pts[k]
        ux, uy, uz, wx, wy, wz = bx - ax, by - ay, bz - az, qx - ax, qy - ay, qz - az
        n = (uy * wz - uz * wy, uz * wx - ux * wz, ux * wy - uy * wx)
        for v in (i, j, k):
            normals[v][0] += n[0]
            normals[v][1] += n[1]
            normals[v][2] += n[2]
    unit = []
    for n in normals:
        m = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
        unit.append((n[0] / m, n[1] / m, n[2] / m))
    previous = b.anchor
    b.anchor = FIXED if fixed else (x, y)
    floor = base - sz * bury - 0.05
    for i, j, k in tris:
        if max(pts[i][2], pts[j][2], pts[k][2]) < floor + 0.2:
            continue  # wholly underground
        # Half the face normal into each corner: shoulders stay rounded, fracture faces and edges stay crisp.
        (ax, ay, az), (bx, by, bz), (qx, qy, qz) = pts[i], pts[j], pts[k]
        ux, uy, uz, wx, wy, wz = bx - ax, by - ay, bz - az, qx - ax, qy - ay, qz - az
        fn = (uy * wz - uz * wy, uz * wx - ux * wz, ux * wy - uy * wx)
        fm = math.sqrt(sum(c * c for c in fn)) or 1.0
        fn = tuple(c / fm for c in fn)
        corner = []
        for v in (i, j, k):
            c = [unit[v][a] * 0.5 + fn[a] * 0.5 for a in range(3)]
            cm = math.sqrt(sum(e * e for e in c)) or 1.0
            corner.append(tuple(e / cm for e in c))
        b.face((pts[i], pts[j], pts[k]), mat, None, corner)
    b.anchor = previous
    return cz + sz * 0.5 * 0.78


def outcrop(b, x, y, base, radius, height, rng, along, mat='rock', fixed=False, level=None):
    """A cliff outcrop: two or three broad bedded masses stepped back up the slope, never a stack of drums.

    Each tier is wider than tall and set back uphill from the one below, so the face reads as ledges and
    buttresses in relief; the tiers overlap inside, never at a visible seam. Returns the top height."""
    ax, ay = along
    ux, uy = ay, -ax  # uphill is to the left of the contour direction (callers pass along = (-uy, ux))
    tiers = 1 if height < 7 else (2 if height < 16 else 3)
    z = base
    top = base
    for k in range(tiers):
        h = height / tiers * rng.uniform(1.25, 1.5)
        w = radius * 2.6 * (1.0 - 0.1 * k) * rng.uniform(0.9, 1.15)
        d = radius * rng.uniform(1.3, 1.7)
        cx = x + ux * radius * 0.35 * k + rng.uniform(-1.0, 1.0)
        cy = y + uy * radius * 0.35 * k + rng.uniform(-1.0, 1.0)
        top = boulder(b, cx, cy, z, (w, d, h), rng, mat, yaw=math.atan2(ay, ax) + rng.uniform(-0.25, 0.25),
                      bury=0.18 if k else 0.3, strata=0.8, fixed=fixed, level=level)
        z = z + h * 0.5
    return top


def vines(b, x, y, z_top, length, width, out, rng):
    """Foliage spilling over a crest and down the face; out is the unit downhill direction.

    Lobes of leaf cards (kit.leaf_canopy, as the trees use) hang in chains that narrow and thin as they drop, held
    a little proud of the rock below. Flat hanging strips tiled the leaf atlas into a dotted grid."""
    ox, oy = out
    tx, ty = -oy, ox
    lobes = max(1, int(width / 3.4))
    for k in range(lobes):
        s = ((k + 0.5) / lobes - 0.5) * width + rng.uniform(-0.6, 0.6)
        drop = length * rng.uniform(0.35, 1.0)
        z, r = z_top + 0.6, rng.uniform(2.2, 3.4)
        while z > z_top - drop and r > 0.8:
            off = r * 0.5 + (z_top - z) * 0.08
            leaf_canopy(b, (x + tx * s + ox * off, y + ty * s + oy * off, z), (r, r * 0.8, r * 1.4),
                        max(6, int(4.5 * r * r)), 0.85 + 0.25 * r, rng, warm=0.07)
            z -= r * 1.4
            r *= rng.uniform(0.78, 0.92)
            s += rng.uniform(-0.4, 0.4)


def cliff_rocks(b, rng, spacing=12.0):
    """Dress every steep, dry face with big stepped blocks under hanging green. Returns the number of outcrops.

    The bridge paintings (references/bridge.py) read the cliffs as a few large angular masses with flat fractured
    faces and plants on every ledge; many small rounded bosses read as one boulder stamped over a wall.
    """
    from brinecove.landmarks import footprint
    placed = {}
    cell = spacing
    count = 0

    def free(x, y, gap):
        gx, gy = int(x // cell), int(y // cell)
        span = int(math.ceil(gap / cell))
        for i in range(gx - span, gx + span + 1):
            for j in range(gy - span, gy + span + 1):
                for ox, oy in placed.get((i, j), ()):
                    if (ox - x) ** 2 + (oy - y) ** 2 < gap * gap:
                        return False
        return True

    for _ in range(320000):
        x = rng.uniform(L.VIEW_X_MIN + 60, L.VIEW_X_MAX - 60)
        y = rng.uniform(-700, 760)
        if L.is_water(x, y):
            continue
        z = ground(x, y)
        if z < 2.5:
            continue
        ux, uy, grad = uphill(x, y)
        # The collar's eased ramps are gentler than the layout's cliffs but are the cliffs players see there.
        if grad < (0.6 if R.collar_weight(x, y) > 0.0 else 0.85) or L.in_lot(x, y, 4.0) or L.on_shore_walkway(x, y, 5.0) or L.on_street(x, y, 4.0):
            continue
        # falls.py dresses the canyon with its own wet rock; the margin keeps outcrop flanks off the curtain.
        if L.in_gorge(x, y, 9.0):
            continue
        if footprint(x, y, 10.0):
            continue  # keep the fort, its ramp, the shipyard and the hill stair clear
        # The collar's long ramps are the backdrop cliffs seen from the harbor: fewer, far larger masses that overlap
        # into continuous stepped strata. Many small bosses there read as boulders peppered over a green band (note 7).
        collar = R.collar_weight(x, y) > 0.0 and z > 20.0  # high backdrop only: beach slopes stay human-scale
        if not free(x, y, spacing * 1.6 if collar else spacing):
            continue
        placed.setdefault((int(x // cell), int(y // cell)), []).append((x, y))
        count += 1
        along = (-uy, ux)
        # Broad buttresses where the noise is high, small ledges in the gullies between them.
        buttress = fbm(x, y, 140.0, 2, 23)
        radius = rng.uniform(4.5, 8.0) * (0.75 + 0.7 * buttress) * (1.7 if collar else 1.0)
        # Push the outcrop out of the slope so its downhill faces stand proud of the heightfield.
        out = radius * rng.uniform(0.25, 0.5)
        cx, cy = x - ux * out, y - uy * out
        base = ground(cx, cy) - 2.5
        # The top stops a little above the ground uphill of the outcrop, so it reads as a ledge, not a tower.
        crest = ground(x + ux * radius * 1.2, y + uy * radius * 1.2) + rng.uniform(-0.8, 1.6)
        height = max(3.0, min(crest - base, rng.uniform(16.0, 40.0) if collar else rng.uniform(10.0, 28.0)))
        # The strongest buttresses stand proud of the crest, so the skyline breaks instead of running dead level.
        if buttress > 0.6:
            height += rng.uniform(3.0, 9.0) * (buttress - 0.6) / 0.4
        light = fbm(x, y, 90.0, 3, 17)
        # Sunlit golden stone with only a few dark weathered masses (the bridge paintings' palette).
        mat = 'rock_light' if light > 0.48 else ('rock_dark' if light < 0.2 else 'rock')
        # Tiered bedded masses stepped back up the slope (outcrop); plants catch on the ledge tops.
        # The outcrop and its plants are placed on the final ground: the collar must not move them again.
        previous = b.anchor
        if FINAL is not None:
            b.anchor = FIXED
        # Backdrop masses keep the coarse sphere: their fracture planes carry the shape at harbor distance.
        top = outcrop(b, cx, cy, base, radius, height, rng, along, mat, fixed=FINAL is not None,
                      level=1 if collar else None)
        if rng.random() < 0.85:
            bush(b, cx + ux * radius * 0.6, cy + uy * radius * 0.6, top - 0.3, 0.0,
                 rng.uniform(1.4, 2.4) * radius / 6.0, rng)
        if rng.random() < 0.35:
            fern(b, cx - ux * radius * 0.2, cy - uy * radius * 0.2, top - 0.2, rng.uniform(0, 360),
                 rng.uniform(0.9, 1.4), rng)
        # Green spills over nearly every crest and down most of the face.
        if height > 4 and rng.random() < 0.92:
            vines(b, cx - ux * radius * 0.7, cy - uy * radius * 0.7, top,
                  min(height * 0.95, rng.uniform(8.0, 22.0)), rng.uniform(radius * 0.9, radius * 1.8), (-ux, -uy), rng)
        # A fallen block or two bedded into the ground at the foot.
        if rng.random() < 0.4:
            fx, fy = cx - ux * radius * 1.3, cy - uy * radius * 1.3
            r = radius * rng.uniform(0.3, 0.5)
            boulder(b, fx, fy, ground(fx, fy), (r * 2.0, r * 1.6, r * 1.3), rng, 'rock', fixed=FINAL is not None)
        b.anchor = previous
    return count


def terrain_material(gx, gy, zavg, sl, i, j):
    """Natural ground is one blended material: the terrain shader picks sand, meadow, forest floor and rock per
    pixel from height, slope and noise (import_brinecove.terrain_parent). One material per 4 m cell painted the
    shore as square sand patches and the slopes as a repeated leaf print (playtest notes 1, 3 and 5)."""
    return 'terrain'


def crag(b, x, y, base, top, radius, rng, count=9):
    """A craggy sea rock: a tall bedded core ringed by lower leaning boulders, all rising from below the sea."""
    core = (top - base)
    boulder(b, x, y, base, (radius * 1.3, radius * 1.0, core * 1.25), rng, 'rock', bury=0.1, strata=0.6,
            lean=(rng.uniform(-0.15, 0.15), rng.uniform(-0.15, 0.15)))
    for k in range(1, count):
        a = TAU * k / (count - 1) + rng.uniform(-0.3, 0.3)
        d = radius * rng.uniform(0.45, 0.85)
        h = core * rng.uniform(0.25, 0.7) * (1.0 - d / radius * 0.5)
        r = radius * rng.uniform(0.35, 0.6)
        boulder(b, x + math.cos(a) * d, y + math.sin(a) * d, base, (r * 2.0, r * 1.6, h * 1.3), rng,
                'rock_dark' if h < 4 else 'rock', bury=0.15, lean=(math.cos(a) * 0.2, math.sin(a) * 0.2))


def canopy_hill(b, x, y, r, sx, sz, rng, spacing=16.0):
    """Cover a distant dome with rounded crown blobs, so far hills read as forest, not a green shell."""
    count = 0
    for _ in range(int(sx * r * r * 3.1416 / (spacing * spacing) * 1.6)):
        u, v = rng.uniform(-1, 1), rng.uniform(-1, 1)
        q = u * u + v * v
        if q > 0.92:
            continue
        px, py = x + u * r * sx, y + v * r
        pz = -5.0 + sz * r * math.sqrt(1.0 - q)
        if pz < 1.0:
            continue
        n = fbm(px, py, 120.0, 3, 41)
        mat = ('jungle_dark', 'jungle', 'jungle_light', 'autumn_olive', 'autumn_gold')[
            min(4, int(n * 4.2 + rng.uniform(-0.6, 0.6)) if n > 0 else 0)]
        rad = rng.uniform(7.5, 11.5)
        b.sphere((px, py, pz + rad * 0.15), rad, mat, (1.0, 1.0, 0.8), subdiv=0)
        count += 1
    return count
