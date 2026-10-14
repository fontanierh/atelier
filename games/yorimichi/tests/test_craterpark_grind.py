"""Crater Park's grind lines run along the lips already in the park (world/regions/craterpark/grind.py)."""
from pathlib import Path
import sys
import unittest

import numpy as np

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world' / 'regions'))
from craterpark import grind  # noqa: E402


def quad(a, b, c, d):
    """Two triangles a-b-c, a-c-d, wound so a level quad listed counter-clockwise seen from below faces up (native y)."""
    return [[a, c, b], [a, d, c]]


def box(x0, z0, x1, z1, top, bottom=0.):
    """A closed box: its level top, four sides."""
    t = quad((x0, top, z0), (x1, top, z0), (x1, top, z1), (x0, top, z1))
    for (ax, az), (bx, bz) in (((x0, z0), (x1, z0)), ((x1, z0), (x1, z1)), ((x1, z1), (x0, z1)), ((x0, z1), (x0, z0))):
        t += [[(ax, bottom, az), (bx, bottom, bz), (bx, top, bz)], [(ax, bottom, az), (bx, top, bz), (ax, top, az)]]
    return t


def floor(x0, z0, x1, z1, y=0.):
    return quad((x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1))


def faces_up(t):
    t = np.asarray(t, 'f8')
    n = grind.unit_normals(t)
    t[n[:, 1] < -.5] = t[n[:, 1] < -.5][:, [0, 2, 1]]                  # the test shapes face up wherever level
    return t


def length(line):
    return float(np.linalg.norm(np.diff(line, axis=0), axis=1).sum())


class GrindTests(unittest.TestCase):
    def lines(self, riding, solid=()):
        riding = faces_up(riding)
        solid = faces_up(solid) if len(solid) else np.zeros((0, 3, 3))
        return grind.grind_lines(riding, solid)

    def test_a_box_on_the_floor_grinds_round_its_top(self):
        lines = self.lines(floor(-5, -5, 5, 5) + box(-1, -1, 2, 1, .4))
        self.assertEqual(len(lines), 4)                                  # the corners split it
        for line in lines:
            self.assertTrue(np.allclose(line[:, 1], .4))
        self.assertAlmostEqual(sum(length(l) for l in lines), 10., delta=.05)
        for line in lines:
            self.assertLessEqual(np.linalg.norm(np.diff(line, axis=0), axis=1).max(), grind.STEP + 1e-6)

    def test_a_stair_has_no_grind_on_its_nosings(self):
        steps = []
        for k in range(5):                                              # 0.2 m risers, 0.65 m treads, down along +x
            steps += box(.65 * k, -1, .65 * (k + 1), 1, 1. - .2 * k)
        lines = self.lines(floor(-3, -3, 6, 3) + floor(-3, -1, 0, 1, 1.) + steps)
        on_nosing = [l for l in lines if np.ptp(l[:, 0]) < .01 and .1 < l[0, 0] < 3.2]
        self.assertEqual(on_nosing, [])

    def test_a_path_edge_over_the_hillside_is_no_lip(self):
        path = floor(-1, -10, 1, 10, 2.)                                 # a raised path; under it only the hillside
        hillside = floor(-20, -20, 20, 20, 0.)
        self.assertEqual(self.lines(path, hillside), [])

    def test_a_ledge_under_a_roof_is_no_lip(self):
        riding = floor(-5, -5, 5, 5) + box(-1, -1, 2, 1, .4)
        roof = floor(-2, -2, 2, 2, .6)                                   # 20 cm over the ledge: no room to grind
        self.assertEqual(self.lines(riding, roof), [])

    def test_a_short_box_is_left_out(self):
        self.assertEqual(self.lines(floor(-5, -5, 5, 5) + box(0, 0, 1, 1, .4)), [])


if __name__ == '__main__':
    unittest.main()
