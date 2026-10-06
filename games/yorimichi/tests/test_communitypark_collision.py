"""Ramp the joint lips of separately placed park pieces without touching ledges or real steps."""
import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'world'))
import yori  # noqa: E402,F401
from communitypark import collision as C  # noqa: E402


def slab(x0, y0, x1, y1, z0, z1):
    """A closed box, faces wound outward, as a placed source piece."""
    vertices = np.array([(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)], float)
    faces = [(0, 2, 3), (0, 3, 1), (4, 5, 7), (4, 7, 6), (0, 1, 5), (0, 5, 4),
             (2, 6, 7), (2, 7, 3), (0, 4, 6), (0, 6, 2), (1, 3, 7), (1, 7, 5)]
    return vertices, np.array(faces)


def floor_tiles():
    """Two flush tiles of a deck: their shared edge rises 0 and must stay unramped."""
    return [slab(-4, -4, 0, 4, -.2, 0.), slab(0, -4, 4, 4, -.2, 0.)]


class RidingCollisionTest(unittest.TestCase):
    def test_flush_tiles_weld_without_ramps(self):
        vertices, faces, owner, report = C.riding_collision(floor_tiles())
        self.assertEqual(report['wedges'], 0)
        self.assertLess(report['welded_vertices'], 16)
        self.assertEqual(C.steps(vertices, faces, owner), [])

    def test_a_proud_pad_gets_a_shallow_ramp_on_every_side(self):
        pad = slab(-1, -1, 1, 1, -.1, .02)
        before = C.steps(*C.weld(floor_tiles()+[pad]))
        self.assertTrue(before and all(abs(r-.02) < 1e-9 for _, r, _ in before))
        vertices, faces, owner, report = C.riding_collision(floor_tiles()+[pad])
        self.assertEqual([x for x in C.steps(vertices, faces, owner) if x[2] >= 0], [])
        self.assertAlmostEqual(report['max_rise_m'], .02)
        ramps = vertices[faces[owner < 0]]
        # 1:8 at most (the run is never shorter than 10 cm), and never above the pad or below the floor.
        self.assertGreaterEqual(ramps[..., 2].min(), -1e-9); self.assertLessEqual(ramps[..., 2].max(), .02+1e-9)
        normals = C._normals(ramps)[0]
        self.assertTrue(np.all(normals[:, 2] > np.cos(np.arctan(.2/.1))-1e-9))
        self.assertTrue(np.all(normals[:, 2] > 0))
        self.assertAlmostEqual(report['wedged_length_m'], 8., places=6)

    def test_ledges_and_real_steps_stay_sharp(self):
        ledge = slab(-1, -.2, 1, .2, -.1, .04)
        step = slab(2, -3, 3.5, 3, -.1, .3)
        vertices, faces, owner, report = C.riding_collision(floor_tiles()+[ledge, step], obstacles={2})
        self.assertEqual(report['wedges'], 0)
        self.assertEqual(C.steps(vertices, faces, owner, obstacles={2}), [])


if __name__ == '__main__':
    unittest.main()
