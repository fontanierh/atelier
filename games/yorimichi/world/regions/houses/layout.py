"""The five houses on the main road: where each lot sits, how the ground is shaped for it, what grows around it.

Pure numpy; gen_world.py calls it. A lot is a level terrace beside the road that the house faces: a stone kerb and a
clipped hedge along the road verge with a gate opening in front of the entrance, a gravel yard with stepping stones
to the genkan, a small garden in the opposite front corner, and dry-stone walls (ishigaki) round the sides and back
where the ground falls away. Uphill lots are cut into the bank, which rises again beyond a flat margin.

Lot frame (the frame of the House_* and HouseLot_* instances): origin at the house centre on the lot level, -y
toward the road (the house front), +x along the road. World = centre + R(yaw) @ local; the front direction in
the world is (sin yaw, -cos yaw).
"""
import math
import numpy as np

# House variants. `walls`: outer wall lines; `ground`: everything standing on the ground (engawa, porch, steps,
# lean-to); `roof`: the eave outline seen from above; `door_x`: the entrance, which the gate and stepping stones
# line up with. All (x0, x1, y0, y1) in the lot frame. build.py models the houses to these numbers.
HOUSES = {
    'A': dict(about='single-storey tiled house, hip-and-gable (irimoya) roof, engawa and a gabled entrance porch',
              walls=(-5.0, 5.0, -3.4, 3.4), ground=(-5.3, 5.3, -5.45, 3.6), roof=(-6.25, 6.25, -5.45, 4.15), door_x=2.8),
    'B': dict(about='thatched farmhouse (kayabuki), wide engawa with storm shutters, earth-floored entrance, woodpile lean-to',
              walls=(-5.5, 5.5, -3.7, 3.7), ground=(-5.8, 7.6, -5.1, 3.9), roof=(-6.9, 7.9, -5.2, 5.2), door_x=2.7),
    'C': dict(about='two-storey tiled house, pent roof round the ground floor, gabled upper roof, balcony',
              walls=(-4.6, 4.6, -3.6, 3.6), ground=(-4.9, 4.9, -5.1, 3.8), roof=(-5.6, 5.6, -4.9, 4.6), door_x=2.4),
}

# (road sample s in metres, side: -1 downhill / +1 uphill, house variant). Uphill lots sit between the utility poles
# (every 30 m from s = 12 at 4.3 m uphill) so no pole stands in a frontage; s = 150 is left to the skate path.
LOTS = ((96, -1, 'A'), (147, +1, 'B'), (177, +1, 'C'), (327, -1, 'A'), (357, +1, 'C'))

# The five house spots the world had before the lots. Their pads decided where the scatter put trees and bushes; the
# scatter still asks them, so the forest everywhere else stays exactly as it was. The pad at s = 150 stays in the
# ground: the skate path was laid on it.
LEGACY = ((96, -1), (150, -1), (185, +1), (300, -1), (338, +1))
KEEP_LEGACY_PAD = (150,)

HALF_W = 9.5            # lot half-width along the road
BACK = 6.8              # back edge behind the house centre
CENTRE_OFF = 15.0       # house centre from the road centreline
HEDGE_OFF = {-1: 5.0, +1: 5.6}      # hedge line from the road centreline (uphill: clear of the 4.3 m poles)
RISE = {-1: 0.08, +1: 0.45}         # lot level above the road at the lot centre (uphill: three steps up the gate)
WALL = {-1: 1.5, +1: 0.4}           # most a side or back wall shows above the ground at its foot
BERM = 2.4              # ground held level with the wall foot (or the lot) outside the edge: one terrain cell and more
FILL_SLOPE = 0.7        # beyond the berm the ground falls to the natural slope at most this steeply
CUT_SLOPE = 0.9         # ... or rises back up to it
FRONT_BAND = 2.5        # ground inside the lot this close to the hedge is held at the lot level (the verge stays flat)
ROAD_KEEP = 3.3         # the road and its shoulder are never regraded
GATE_HALF = 0.95        # half-width of the gate opening
SINK = 0.08             # the terrain under a lot stays this far below its surface
REACH_OUT = 25.0        # grading never reaches further than this outside a lot


def _frame(s, side, RX, RY, RZ, NX, NY, UP):
    i = int(s)
    u = np.array([NX[i] * UP[i], NY[i] * UP[i]]) * side            # road -> lot
    return i, np.array([RX[i], RY[i]]), float(RZ[i]), u


def to_local(lot, x, y):
    a = math.radians(lot['yaw']); c, s = math.cos(a), math.sin(a)
    dx = np.asarray(x) - lot['centre'][0]; dy = np.asarray(y) - lot['centre'][1]
    return dx * c + dy * s, -dx * s + dy * c


def to_world(lot, lx, ly):
    a = math.radians(lot['yaw']); c, s = math.cos(a), math.sin(a)
    lx = np.asarray(lx); ly = np.asarray(ly)
    return lot['centre'][0] + lx * c - ly * s, lot['centre'][1] + lx * s + ly * c


def front_y(lot, lx):
    """Local y of the hedge line at local x (the polyline is sorted by x)."""
    f = np.array(lot['front'])
    return np.interp(np.clip(lx, f[0, 0], f[-1, 0]), f[:, 0], f[:, 1])


def plan(RX, RY, RZ, NX, NY, UP):
    """Every lot's frame, level, hedge line, polygon, gate, garden and frontage along the road."""
    lots = []
    for k, (s, side, variant) in enumerate(LOTS):
        i, p, z, u = _frame(s, side, RX, RY, RZ, NX, NY, UP)
        f = -u
        yaw = round(math.degrees(math.atan2(f[0], -f[1])), 1)
        cx, cy = (round(float(v), 2) for v in p + u * CENTRE_OFF)
        level = round(z + RISE[side], 2)
        lot = dict(name=f'HouseLot_{k + 1}', house=f'House_{variant}', variant=variant, s=s, side=side,
                   centre=[cx, cy], level=level, yaw=yaw)
        # hedge line: the road offset by HEDGE_OFF toward the lot, clipped to the lot's width
        pts = []
        for j in range(i - 20, i + 21):
            uj = np.array([NX[j] * UP[j], NY[j] * UP[j]]) * side
            q = np.array([RX[j], RY[j]]) + uj * HEDGE_OFF[side]
            lx, ly = to_local(lot, q[0], q[1])
            pts.append((float(lx), float(ly), float(RZ[j]) - level, j))
        pts.sort()
        front, frontage = [], []
        for (x0, y0, z0, j0), (x1, y1, z1, j1) in zip(pts[:-1], pts[1:]):
            for edge in (-HALF_W, HALF_W):
                if (x0 - edge) * (x1 - edge) < 0:
                    t = (edge - x0) / (x1 - x0)
                    front.append((edge, y0 + (y1 - y0) * t, z0 + (z1 - z0) * t)); frontage.append(j0 + t * (j1 - j0))
            if -HALF_W < x1 < HALF_W:
                front.append((x1, y1, z1)); frontage.append(j1)
        front.sort()
        lot['front'] = [[round(a, 3), round(b, 3), round(c, 3)] for a, b, c in front]    # x, y, verge height - level
        lot['frontage'] = [round(min(frontage), 1), round(max(frontage), 1)]            # road samples along the lot
        lot['polygon'] = [[a, b] for a, b, _ in lot['front']] + [[HALF_W, BACK], [-HALF_W, BACK]]
        spec = HOUSES[variant]
        gx = spec['door_x']
        lot['gate'] = [round(gx - GATE_HALF, 2), round(gx + GATE_HALF, 2)]
        lot['gate_verge'] = round(float(np.interp(gx, [q[0] for q in front], [q[2] for q in front])), 3)
        lot['house_ground'] = list(spec['ground']); lot['house_roof'] = list(spec['roof'])
        # garden in the front corner away from the gate; the yard is the rest of the front
        gside = -1 if gx > 0 else 1
        yf = float(front_y(lot, gside * 6.0))
        lot['garden'] = dict(centre=[round(gside * 6.3, 2), round(yf + 2.7, 2)], radii=[2.4, 1.7])
        world_c = [float(v) for v in to_world(lot, 0.0, 0.0)]
        assert abs(world_c[0] - cx) < 1e-6 and abs(world_c[1] - cy) < 1e-6
        lots.append(lot)
    return lots


def _outside(lot, lx, ly):
    """(distance outside the lot polygon, inside?, depth behind the hedge line) for local points."""
    yf = front_y(lot, lx)
    ex = np.maximum(np.abs(lx) - HALF_W, 0.0)
    ey = np.maximum.reduce([ly - BACK, yf - ly, np.zeros_like(ly)])
    inside = (np.abs(lx) <= HALF_W) & (ly <= BACK) & (ly >= yf)
    return np.hypot(ex, ey), inside, ly - yf


def grade(H, X, Y, D, NEAR, RZ, SIDE, lots):
    """Shape the ground for every lot, in place. SIDE: each cell's signed offset from the road (+ uphill), valid
    where D (its distance from the road) is under 20 m. Returns the mask of changed cells."""
    changed = np.zeros(H.shape, bool)
    for lot in lots:
        L = lot['level']; side = lot['side']; hw = WALL[side]
        cx, cy = lot['centre']
        win = (np.abs(X - cx) < 45) & (np.abs(Y - cy) < 45)
        lx, ly = to_local(lot, X[win], Y[win])
        d, inside, depth = _outside(lot, lx, ly)
        h = H[win].copy(); new = h.copy()
        # inside: never above the lot surface, never so far below it that the wall foot shows a trench
        new = np.where(inside, np.clip(h, L - hw, L - SINK), new)
        new = np.where(inside & (depth < FRONT_BAND), L - SINK, new)
        # outside, on the lot's side of the road only: a level berm at the wall foot, then no steeper than the fill /
        # cut slopes back to the ground
        mine = (D[win] > 19.0) | (SIDE[win] * side > 0)
        lo = np.where(d <= BERM, L - hw, L - hw - (d - BERM) * FILL_SLOPE)
        hi = np.where(d <= BERM, L - SINK, L - SINK + (d - BERM) * CUT_SLOPE)
        new = np.where(~inside & mine & (d < REACH_OUT), np.clip(h, lo, hi), new)
        # the verge between the road shoulder and the hedge follows the road
        verge = (~inside) & mine & (np.abs(lx) <= HALF_W + 1.0) & (ly < front_y(lot, lx)) & (D[win] <= HEDGE_OFF[side] + 0.6)
        new = np.where(verge, RZ[NEAR[win]] - 0.02, new)
        keep = D[win] < ROAD_KEEP
        new = np.where(keep, h, new)
        H[win] = new
        changed[win] |= np.abs(new - h) > 1e-6
    return changed


def rail_blocked(lots, s):
    """True where a downhill lot's hedge replaces the guardrail."""
    return any(lot['side'] < 0 and lot['frontage'][0] - 0.5 <= s <= lot['frontage'][1] + 0.5 for lot in lots)


# ----------------------------------------------------------------------------- vegetation and dressing
TREE_REACH = 5.5          # crown radius of a full-size scattered tree (times its scale)
REACH = {'Bush_Flower_A': 1.75, 'Bush_Flower_B': 1.45, 'Bush_Green_A': 1.88, 'Bush_Green_B': 1.48, 'Bush_Ochre_A': 1.98,
         'Bush_Ochre_B': 1.58, 'Rock_A': 1.8, 'Rock_B': 1.1, 'Rock_C': 2.6, 'Litter': 0.25}
GRASS_REACH = 0.52


def _reach(name, scale):
    if name.startswith('Tree'): return None
    if name.startswith('Grass'): return GRASS_REACH * scale
    if name.startswith(('Bush', 'Rock')) or name == 'Litter': return REACH.get(name, 2.0) * scale + 0.18
    return None


def blocked(lots, name, items):
    """Placements that would stand in a lot, its walls' berm, its verge, or (trees) reach over a roof."""
    if not items: return np.zeros(0, bool)
    P = np.asarray(items, float); out = np.zeros(len(P), bool)
    for lot in lots:
        lx, ly = to_local(lot, P[:, 0], P[:, 1])
        d, inside, depth = _outside(lot, lx, ly)
        if name.startswith('Tree'):
            # trunks off the lot and its berm; crowns off the roof
            out |= inside | (d < BERM + 0.6)
            x0, x1, y0, y1 = lot['house_roof']
            ex = np.maximum.reduce([x0 - lx, lx - x1, np.zeros(len(lx))]); ey = np.maximum.reduce([y0 - ly, ly - y1, np.zeros(len(ly))])
            out |= np.hypot(ex, ey) < TREE_REACH * P[:, 4] * 0.6 + 0.5
            continue
        r = _reach(name, P[:, 4])
        if r is None: continue
        out |= inside | (d < BERM + r)
        verge = (np.abs(lx) <= HALF_W + 1.0) & (ly < front_y(lot, lx)) & (ly > front_y(lot, lx) - (HEDGE_OFF[lot['side']] - 2.6) - r)
        out |= verge
    return out


def dressing(lots, sample_h, seed=7):
    """Garden and backdrop placements for every lot: (asset, x, y, z, yaw, scale)."""
    rng = np.random.default_rng(seed); out = []
    for lot in lots:
        L = lot['level']; gx, gy = lot['garden']['centre']; gs = 1 if gx > 0 else -1
        def put(name, lx, ly, z, yaw, scale):
            x, y = to_world(lot, lx, ly)
            out.append([name, round(float(x), 2), round(float(y), 2), round(float(z), 2), round(float(yaw), 1), round(float(scale), 3)])
        # garden: a stone lantern at its front on the yard side, a small pine at its back, a small maple in the far
        # corner (their crowns clear of the lantern and the eaves), a clipped shrub and three rocks on the moss
        put('Lantern', gx - gs * 2.0, gy - 0.5, L + 0.03, lot['yaw'] + rng.uniform(-8, 8), 0.8)
        put('Tree_Pine_B', gx + gs * 0.4, gy + 1.3, L - 0.05, rng.uniform(0, 360), 0.42)
        put('Tree_Maple_B', gx + gs * 1.7, gy + 0.3, L - 0.05, rng.uniform(0, 360), 0.5)
        put('Bush_Green_B', gx - gs * 0.2, gy - 0.9, L - 0.02, rng.uniform(0, 360), 0.55)
        for dx, dy, sc in ((-0.9, -0.9, 0.30), (-0.4, -0.3, 0.22), (0.4, 0.9, 0.26)):
            put('Rock_B', gx + gs * dx, gy + dy, L - 0.06, rng.uniform(0, 360), sc)
        # a flowering shrub against the hedge in the other front corner
        put('Bush_Flower_B', -gs * 7.9, float(front_y(lot, -gs * 7.9)) + 1.3, L - 0.05, rng.uniform(0, 360), 0.7)
        # tall trees behind the lot, on the ground beyond its back berm
        for k, (bx, name, sc) in enumerate(((-6.5, 'Tree_Pine_A', 1.15), (1.0, 'Tree_Cedar_B', 1.0), (7.0, 'Tree_Maple_A', 0.95))):
            lx = bx + rng.uniform(-1.2, 1.2); ly = BACK + BERM + 1.6 + rng.uniform(0, 1.5)
            x, y = to_world(lot, lx, ly)
            put(name, lx, ly, sample_h(float(x), float(y)) - 0.15, rng.uniform(0, 360), sc * rng.uniform(0.95, 1.1))
    return out


# The tree house draws its canopy trees over the whole map's broadleaf lists in order, so the forest it plans on
# keeps the few gaps the former houses' roofs made in it (their tree rule, at their spots); the lots are cleared
# and planted after it (gen_world.py).
LEGACY_ROOF = (-5.65, 5.65, -4.35, 4.35)


def legacy_tree_gaps(world, spots):
    """Remove the trees whose crowns reached the former houses' roofs. `spots`: (x, y, yaw) as they were placed."""
    removed = {}
    for name, items in world['instances'].items():
        if not name.startswith('Tree') or not items: continue
        P = np.asarray(items, float); out = np.zeros(len(P), bool); reach = TREE_REACH * P[:, 4] + 0.18
        for hx, hy, yaw in spots:
            a = math.radians(yaw); dx = P[:, 0] - hx; dy = P[:, 1] - hy
            lx = dx * math.cos(a) + dy * math.sin(a); ly = -dx * math.sin(a) + dy * math.cos(a)
            x0, x1, y0, y1 = LEGACY_ROOF
            ex = np.maximum.reduce([x0 - lx, lx - x1, np.zeros(len(lx))]); ey = np.maximum.reduce([y0 - ly, ly - y1, np.zeros(len(ly))])
            out |= np.hypot(ex, ey) < reach
        if out.any():
            removed[name] = int(out.sum())
            world['instances'][name] = [p for p, m in zip(items, out) if not m]
    return removed


def _lantern_mask(name, items, lanterns):
    from torii_clearance import occupied_mask          # (torii_clearance imports this module)
    return occupied_mask(name, items, {'Lantern': lanterns})


def clear_and_dress(world, sample_h):
    """Last step of the layout: clear the lots of scattered plants and rocks, then plant their gardens. Plants keep
    off the garden lanterns as they keep off every other lantern (torii_clearance.py)."""
    lots = world['houses']['lots']; removed = {}
    dressed = dressing(lots, sample_h)
    lanterns = [p for n, *p in dressed if n == 'Lantern']
    for name, *p in dressed:
        assert not _lantern_mask(name, [p], lanterns).any(), ('garden planting too close to its lantern', name, p)
    for name, items in world['instances'].items():
        mask = blocked(lots, name, items) | _lantern_mask(name, items, lanterns)
        if mask.any():
            removed[name] = int(mask.sum())
            world['instances'][name] = [p for p, m in zip(items, mask) if not m]
    for name, *p in dressed:
        world['instances'].setdefault(name, []).append(p)
    world['houses']['removed'] = removed
    world['houses']['dressing'] = dressed
    return removed


def check(world):
    """Nothing scattered stands in a lot (the gardens' own planting excepted)."""
    lots = world['houses']['lots']
    own = {(n, p[0], p[1]) for n, *p in world['houses']['dressing']}
    bad = {}
    for name, items in world['instances'].items():
        mask = blocked(lots, name, items)
        n = sum(1 for p, m in zip(items, mask) if m and (name, p[0], p[1]) not in own)
        if n: bad[name] = n
    assert not bad, ('scattered placements inside house lots', bad)
    return {'house_lots': len(lots), 'house_lots_clear': True}
