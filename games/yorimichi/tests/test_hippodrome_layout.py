"""The hippodrome's course (world/regions/hippodrome/layout.py): the oval and the public venue plan."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
import yori  # noqa: E402,F401
from regions.hippodrome import layout as L  # noqa: E402


def inside(poly, x, y):
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    return min(xs) <= x <= max(xs) and min(ys) <= y <= max(ys)


class Course(unittest.TestCase):
    def test_centre_line_is_continuous_and_one_lap_long(self):
        step = .05
        points = [L.centre(i * step) for i in range(int(L.LAP / step) + 1)]
        run = sum(math.dist(a[:2], b[:2]) for a, b in zip(points, points[1:]))
        self.assertAlmostEqual(run, L.LAP, delta=.05)
        for a, b in zip(points, points[1:]):
            self.assertLess(math.dist(a[:2], b[:2]), step * 1.001)

    def test_heading_follows_the_line_counter_clockwise(self):
        for s in range(0, int(L.LAP), 7):
            x, y, h = L.centre(s); x2, y2, _ = L.centre(s + .01)
            self.assertAlmostEqual(math.atan2(y2 - y, x2 - x) % (2 * math.pi), h % (2 * math.pi), delta=1e-3)
        self.assertAlmostEqual(L.centre(0.)[2], 0.)                  # east past the grandstand
        self.assertAlmostEqual(L.centre(L.LAP / 2)[2], math.pi)      # west along the back straight

    def test_offset_is_outwards(self):
        for s in range(0, int(L.LAP), 11):
            ox, oy = L.ORIGIN
            a = L.centre(s, -3.); b = L.centre(s, 3.)
            da = abs(a[1] - oy) if abs(a[0] - ox) <= L.HALF else math.hypot(abs(a[0] - ox) - L.HALF, a[1] - oy)
            db = abs(b[1] - oy) if abs(b[0] - ox) <= L.HALF else math.hypot(abs(b[0] - ox) - L.HALF, b[1] - oy)
            self.assertGreater(db, da)

    def test_curvature_scale_matches_the_turn_arc(self):
        s = L.HALF + math.pi * L.RADIUS / 2             # mid east turn
        d = math.dist(L.centre(s, 5.)[:2], L.centre(s + .1, 5.)[:2]) / .1
        self.assertAlmostEqual(L.curvature_scale(s, 5.), d, places=3)
        self.assertEqual(L.curvature_scale(10., 5.), 1.)

    def test_plan_fits_the_platform_and_its_clearance(self):
        x0, y0, x1, y1 = L.PLATFORM
        for s in range(0, int(L.LAP)):
            for off in (-L.WIDTH / 2, L.WIDTH / 2):
                x, y, _ = L.centre(s, off)
                self.assertTrue(x0 <= x <= x1 and y0 <= y <= y1, (s, off, x, y))
        pad = L.clearance()[0]
        for spot in (L.RETURN['at'], *(v['at'] for v in L.STRUCTURES.values())):
            self.assertTrue(inside(pad, *spot), spot)
        # The arrival point stands off the track, between it and the grandstand.
        for spot in (L.RETURN['at'],):
            self.assertLess(spot[1], L.ORIGIN[1] - L.RADIUS - L.WIDTH / 2)


if __name__ == '__main__':
    unittest.main()
