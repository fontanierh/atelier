"""Henry's stable at Hidamari (world/regions/hidamari_stable/layout.py): the plan's numbers, its clearances and its site."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
import yori  # noqa: E402,F401
from regions.hidamari_stable import layout as L  # noqa: E402
from regions.hippodrome import layout as HL  # noqa: E402


def corners(box):
    """The eight corners of a collision box (rotations about x, y, z in degrees, applied x then y then z)."""
    (cx, cy, cz), (sx, sy, sz), (rx, ry, rz) = box['centre'], box['size'], box['rot']
    out = []
    for dx in (-1, 1):
        for dy in (-1, 1):
            for dz in (-1, 1):
                x, y, z = dx * sx / 2, dy * sy / 2, dz * sz / 2
                a = math.radians(rx); y, z = y * math.cos(a) - z * math.sin(a), y * math.sin(a) + z * math.cos(a)
                a = math.radians(ry); x, z = x * math.cos(a) + z * math.sin(a), -x * math.sin(a) + z * math.cos(a)
                a = math.radians(rz); x, y = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
                out.append((cx + x, cy + y, cz + z))
    return out


def bounds(box):
    c = corners(box)
    return [min(p[i] for p in c) for i in range(3)], [max(p[i] for p in c) for i in range(3)]


def contains(box, p):
    """Whether point p lies inside a box tilted about x only (the roof slabs)."""
    (cx, cy, cz), (sx, sy, sz), (rx, _, _) = box['centre'], box['size'], box['rot']
    x, y, z = p[0] - cx, p[1] - cy, p[2] - cz
    a = -math.radians(rx); y, z = y * math.cos(a) - z * math.sin(a), y * math.sin(a) + z * math.cos(a)
    return abs(x) <= sx / 2 and abs(y) <= sy / 2 and abs(z) <= sz / 2


def hits(box, lo, hi):
    """Whether the box overlaps the volume lo..hi: exact for axis-aligned boxes, sampled every 0.1 m for tilted ones."""
    a, b = bounds(box)
    if not all(a[i] < hi[i] - 1e-6 and b[i] > lo[i] + 1e-6 for i in range(3)):
        return False
    if not any(box['rot']):
        return True
    steps = [max(2, int((hi[i] - lo[i]) / .1) + 1) for i in range(3)]
    grid = [[lo[i] + (hi[i] - lo[i]) * k / (steps[i] - 1) for k in range(steps[i])] for i in range(3)]
    return any(contains(box, (x, y, z)) for x in grid[0] for y in grid[1] for z in grid[2])


def course_distance(x, y):
    """Metres from an island point to the hippodrome's outer rail (0 inside the oval)."""
    ox, oy = HL.ORIGIN
    dx = max(abs(x - ox) - HL.HALF, 0.)
    return max(math.hypot(dx, y - oy) - (HL.RADIUS + HL.WIDTH / 2), 0.)


class Programme(unittest.TestCase):
    def test_ten_stalls_with_doors_plates_and_horses(self):
        stalls = L.stalls()
        self.assertEqual(len(stalls), 10)
        self.assertEqual(len({s['id'] for s in stalls}), 10)
        for s in stalls:
            x0, y0, x1, y1, z = s['box']
            self.assertGreaterEqual(x1 - x0, 3.5); self.assertGreaterEqual(y1 - y0, 3.5)
            d = s['door']
            self.assertGreaterEqual(d['width'], 1.3); self.assertGreaterEqual(d['height'], 2.4)
            # the opening lies in the stall's front, and the plate beside it, clear of the opening
            self.assertGreaterEqual(d['pivot'][0] - d['width'] / 2, x0); self.assertLessEqual(d['pivot'][0] + d['width'] / 2, x1)
            px = s['plaque']['centre'][0]; pw = s['plaque']['size'][0]
            self.assertGreater(px - pw / 2, d['pivot'][0] + d['width'] / 2)
            self.assertLess(px + pw / 2, x1)
            self.assertTrue(x0 < s['horse']['at'][0] < x1 and y0 < s['horse']['at'][1] < y1)
            # the plate faces the aisle
            self.assertEqual(s['plaque']['normal'][1], -s['side'])

    def test_open_doors_never_cover_a_doorway_or_a_plate(self):
        doors = [(s['door'], s['plaque']) for s in L.stalls()] + [(r['door'], None) for r in L.rooms().values()]
        for door, _ in doors:
            x, y, _ = door['pivot']
            lo = x + door['slide'][0] * door['travel'] - door['width'] / 2
            hi = lo + door['width']
            for other, plaque in doors:
                if abs(other['pivot'][1] - y) > .3:
                    continue                                  # the other side of the aisle
                if other is not door:
                    ox = other['pivot'][0]
                    self.assertFalse(lo < ox + other['width'] / 2 and hi > ox - other['width'] / 2)
                if plaque:
                    px, pw = plaque['centre'][0], plaque['size'][0]
                    self.assertFalse(lo < px + pw / 2 and hi > px - pw / 2)
        self.assertGreater(min(door['pivot'][0] + door['slide'][0] * door['travel'] - door['width'] / 2 for door, _ in doors),
                           L.BARN_X0 + L.WALL)

    def test_barn_dimensions(self):
        self.assertAlmostEqual(L.BARN_LENGTH, 2 * L.WALL + L.ROOM_W + 5 * (L.PART + L.STALL_W))
        self.assertAlmostEqual(L.AISLE_Y1 - L.AISLE_Y0, 3.5)
        self.assertGreaterEqual(L.AISLE_DOOR[0], 3.); self.assertGreaterEqual(L.AISLE_DOOR[1], 3.)
        self.assertGreater(L.RIDGE_Z, L.EAVE_Z + 2.)
        self.assertGreaterEqual(L.ROOM_DOOR[1], 2.)
        rooms = L.rooms()
        self.assertEqual(set(rooms), {'tack', 'office'})
        nb = L.notice_board(); x0, y0, x1, y1, z = rooms['office']['box']
        self.assertTrue(x0 < nb['centre'][0] <= x1 and y0 < nb['centre'][1] < y1)


class Clearances(unittest.TestCase):
    def setUp(self):
        self.boxes = L.collision_boxes()

    def assertClear(self, lo, hi, what):
        blocked = [b['name'] for b in self.boxes if hits(b, lo, hi)]
        self.assertEqual(blocked, [], what)

    def test_aisle_and_doorways_are_clear_for_a_horse(self):
        h = L.HORSE['height']; f = L.FLOOR_Z
        self.assertClear((L.BARN_X0 + L.WALL, L.AISLE_Y0 + .01, f), (L.BARN_X1 - L.WALL, L.AISLE_Y1 - .01, f + h), 'the aisle')
        cy = L.BARN_CENTRE[1]
        for x in (L.BARN_X0, L.BARN_X1):
            self.assertClear((x - .5, cy - L.AISLE_DOOR[0] / 2 + .01, f), (x + .5, cy + L.AISLE_DOOR[0] / 2 - .01, f + L.AISLE_DOOR[1] - .01), 'an aisle door')

    def test_stall_and_room_doorways_are_clear(self):
        f = L.FLOOR_Z
        for s in L.stalls():
            x, y, _ = s['door']['pivot']; w = s['door']['width']; side = s['side']
            y0, y1 = sorted((y, y + side * (L.PART + 1.)))
            self.assertClear((x - w / 2 + .01, y0, f), (x + w / 2 - .01, y1, f + L.HORSE['height']), f'stall {s["id"]}')
            self.assertGreaterEqual(w, L.HORSE['width'] + .4)
        for name, r in L.rooms().items():
            x, y, _ = r['door']['pivot']; w = r['door']['width']
            self.assertClear((x - w / 2 + .01, y - .5, f), (x + w / 2 - .01, y + .5, f + L.PLAYER['height']), f'{name} door')

    def test_gate_paddock_gate_and_path_are_clear(self):
        gx, gy = L.GATE['at']; o = L.GATE['opening'] / 2
        self.assertClear((gx - 1., gy - o + .01, 0.), (gx + 1., gy + o - .01, 3.), 'the gate')
        self.assertGreaterEqual(L.GATE['height'], 3.)
        px, w = L.PADDOCK_GATE['x'], L.PADDOCK_GATE['width']
        self.assertClear((px - w / 2 + .1, L.PADDOCK[3] - .5, 0.), (px + w / 2 - .1, L.PADDOCK[3] + .5, 2.5), 'the paddock gate')
        self.assertClear((L.COMPOUND[0], gy - 1., 0.), (L.BARN_X0 - .01, gy + 1., 2.5), 'the way from the gate to the barn')

    def test_collision_is_simple(self):
        self.assertLessEqual(len(self.boxes), L.BUDGETS['collision_boxes'])
        for b in self.boxes:
            self.assertTrue(all(s > 0 for s in b['size']), b['name'])
        roof = [b for b in self.boxes if b['name'].startswith('roof')]
        self.assertEqual(len(roof), 2)
        for b in roof:
            self.assertGreater(bounds(b)[0][2], L.AISLE_DOOR[1])      # never low enough to catch a rider at the doors

    def test_unreal_boxes_keep_the_ways_clear(self):
        """The axis-aligned boxes the import gives Unreal (the roof as steps) block no doorway, aisle or gate."""
        boxes = L.aabb_boxes()
        self.assertLessEqual(len(boxes), L.BUDGETS['collision_boxes'])
        f = L.FLOOR_Z; cy = L.BARN_CENTRE[1]; gx, gy = L.GATE['at']; o = L.GATE['opening'] / 2
        ways = [((L.BARN_X0 - 1., cy - L.AISLE_DOOR[0] / 2 + .01, f), (L.BARN_X1 + 1., cy + L.AISLE_DOOR[0] / 2 - .01, f + L.AISLE_DOOR[1] - .01)),
                ((gx - 1., gy - o + .01, 0.), (gx + 1., gy + o - .01, 3.))]
        for s in L.stalls():
            x, y, _ = s['door']['pivot']; w = s['door']['width']
            ways.append(((x - w / 2 + .01, min(y, y + s['side'] * 1.2), f), (x + w / 2 - .01, max(y, y + s['side'] * 1.2), f + 2.4)))
        for lo, hi in ways:
            hit = [b['name'] for b in boxes if all(b['box'][i] < hi[i] and b['box'][i + 3] > lo[i] for i in range(3))]
            self.assertEqual(hit, [], (lo, hi))
        for b in boxes:
            self.assertTrue(all(b['box'][i] < b['box'][i + 3] for i in range(3)), b['name'])

    def test_spots_stand_free(self):
        spots = L.spots()
        for p in spots['npc'] + spots['horse'][10:] + [spots['arrival']]:
            x, y, z = p['at']
            self.assertClear((x - .2, y - .2, z + .05), (x + .2, y + .2, z + 1.7), p.get('id', 'arrival'))
            self.assertTrue(L.COMPOUND[0] - 10 < x < L.COMPOUND[2] and L.COMPOUND[1] < y < L.COMPOUND[3])


def inside(poly, x, y):
    hit = False
    for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1]):
        if (ya > y) != (yb > y) and x < xa + (y - ya) * (xb - xa) / (yb - ya):
            hit = not hit
    return hit


class Site(unittest.TestCase):
    def test_off_the_course_grounds(self):
        bx, by = L.SITE[0] + L.BARN_CENTRE[0], L.SITE[1] + L.BARN_CENTRE[1]
        self.assertLessEqual(course_distance(bx, by), 350.)
        x0, y0, x1, y1 = L.COMPOUND
        r = L.GRADE_REACH
        pad = (L.SITE[0] + x0 - r, L.SITE[1] + y0 - r, L.SITE[0] + x1 + r, L.SITE[1] + y1 + r)
        for poly in HL.clearance():
            xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
            self.assertFalse(pad[0] < max(xs) and pad[2] > min(xs) and pad[1] < max(ys) and pad[3] > min(ys))

    def test_road_continues_the_street_to_the_gate(self):
        pts = [(x + L.SITE[0], y + L.SITE[1]) for x, y in L.road_points()]
        self.assertAlmostEqual(pts[0][0], L.STREET_END[0]); self.assertAlmostEqual(pts[0][1], L.STREET_END[1])
        self.assertAlmostEqual(pts[1][0], L.STREET_END[0])                       # it leaves heading north, as the street runs
        gx, gy = L.GATE['at']
        end = L.road_points()[-1]
        self.assertAlmostEqual(end[1], gy)
        self.assertTrue(L.COMPOUND[0] < end[0] < gx)
        for a, b, c in zip(pts, pts[1:], pts[2:]):
            self.assertLessEqual(math.dist(a, b), 2.2)
            turn = abs(math.remainder(math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(b[1] - a[1], b[0] - a[0]), math.tau))
            self.assertLessEqual(turn / max(math.dist(b, c), 1e-6), 1 / 5., (a, b, c))   # no bend tighter than 5 m

    def test_grading_is_flat_on_the_pad_and_gentle_round_it(self):
        import numpy as np
        x0, y0, x1, y1 = L.COMPOUND
        xs, ys = np.meshgrid(np.arange(x0 - 30., x1 + 30.5, .5) + L.SITE[0], np.arange(y0 - 30., y1 + 30.5, .5) + L.SITE[1])
        ground = 42.6 + (ys - (L.SITE[1] + y0)) * 4.4 / (y1 - y0)          # the site's natural slope, south to north
        z = L.grade(xs, ys, ground)
        on = (xs >= L.SITE[0] + x0) & (xs <= L.SITE[0] + x1) & (ys >= L.SITE[1] + y0) & (ys <= L.SITE[1] + y1)
        self.assertTrue(np.allclose(z[on], L.PAD_Z))
        dzy, dzx = np.gradient(z, .5)
        self.assertLessEqual(float(np.max(np.hypot(dzx, dzy))), 1 / L.GRADE_SLOPE + .02)   # about 1 in 4 at the steepest
        d = np.hypot(np.maximum(np.maximum(L.SITE[0] + x0 - xs, xs - L.SITE[0] - x1), 0.),
                     np.maximum(np.maximum(L.SITE[1] + y0 - ys, ys - L.SITE[1] - y1), 0.))
        self.assertTrue(np.array_equal(z[d >= L.GRADE_REACH], ground[d >= L.GRADE_REACH]))   # untouched beyond the reach

    @unittest.skipUnless((yori.OUT / 'heightmap.npy').exists(), 'world.layout not built')
    def test_hidamari_terrain_carries_the_grading(self):
        import numpy as np
        from regions.hidamari import layout as H
        self.assertAlmostEqual(float(H.height(np.array([L.SITE[0]]), np.array([L.SITE[1]]))[0]), L.PAD_Z, 3)
        far = float(H.height(np.array([L.SITE[0]]), np.array([L.SITE[1] + L.COMPOUND[3] + L.GRADE_REACH + 1.]))[0])
        self.assertAlmostEqual(far, float(H.north_height(np.array([L.SITE[0]]), np.array([500.]))[0]), 1)

    @unittest.skipUnless((yori.OUT / 'heightmap.npy').exists(), 'world.layout not built')
    def test_road_climbs_gently(self):
        import numpy as np
        from regions.hidamari import layout as H
        pts = np.array(L.road_points()) + L.SITE
        z = H.north_height(pts[:, 0], pts[:, 1])
        run = np.hypot(*np.diff(pts, axis=0).T)
        self.assertLessEqual(float(np.max(np.abs(np.diff(z)) / run)), .2, 'no stretch of road steeper than 20 %')

    def test_clearance_covers_the_pad_and_the_road(self):
        pad, road = L.clearance()
        xs = [p[0] for p in pad]; ys = [p[1] for p in pad]
        self.assertLessEqual(min(xs), L.SITE[0] + L.COMPOUND[0])
        self.assertGreaterEqual(max(ys), L.SITE[1] + L.COMPOUND[3])
        self.assertLess(max(ys), L.SITE[1] + L.COMPOUND[3] + L.GRADE_REACH)   # the slopes keep Hidamari's grass
        for x, y in L.road_points():
            self.assertTrue(inside(road, x + L.SITE[0], y + L.SITE[1]), (x, y))

    def test_to_world(self):
        self.assertEqual(L.to_world((1., 2., 3.), 50.), (L.SITE[0] + 1., L.SITE[1] + 2., 53.))

    def test_everything_sits_on_the_pad(self):
        x0, y0, x1, y1 = L.COMPOUND
        for rect in (L.YARD, L.PADDOCK):
            self.assertTrue(x0 <= rect[0] and rect[2] <= x1 and y0 <= rect[1] and rect[3] <= y1)
        self.assertTrue(x0 <= L.BARN_X0 and L.BARN_X1 + L.EAVE_OVERHANG <= x1)
        self.assertTrue(y0 <= L.BARN_Y0 and L.BARN_Y1 + L.EAVE_OVERHANG <= y1)
        self.assertTrue(L.PADDOCK[3] < L.BARN_Y0 - L.EAVE_OVERHANG)


if __name__ == '__main__':
    unittest.main()
