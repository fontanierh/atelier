"""The Mega Park moves into the island as one rigid body, and the island terrain stays under it."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world' / 'regions'))
from megapark import placement  # noqa: E402
from hidamari import mountains  # noqa: E402


class PlacementTests(unittest.TestCase):
    def test_keeps_the_park_itself(self):
        models, sections = placement.kept()
        self.assertEqual(len(models), 32)
        self.assertEqual(len(sections), 20)
        self.assertTrue(all(placement.is_park_model(m) for m in models))

    def test_rigid_and_unreal_transform_agree(self):
        rng = np.random.default_rng(5)
        native = rng.uniform([100, 60, -900], [520, 230, -400], (200, 3))
        island = placement.native_to_island(native)
        unreal = placement.to_unreal(native) / 100 * [1, -1, 1]
        np.testing.assert_allclose(island, unreal, atol=1e-6)
        before = np.linalg.norm(native[:, None] - native[None], axis=-1)
        after = np.linalg.norm(island[:, None] - island[None], axis=-1)
        np.testing.assert_allclose(before, after, atol=1e-6)
        self.assertAlmostEqual(float(placement.place(placement.collision_triangles())[..., 2].min()), placement.BASE, 6)

    def test_terrain_cells_under_the_park_stay_below_it(self):
        """Every 10 m terrain cell with all four corners under the park lies below every park surface in the cell."""
        t = placement.place(placement.collision_triangles())
        points = placement.surface_samples(t, 2.)
        s = mountains.STEP
        x0, y0 = mountains.BOUNDS[:2]
        i = np.floor((points[:, 0] - x0) / s).astype(int); j = np.floor((points[:, 1] - y0) / s).astype(int)
        lowest = {}
        for key, z in zip(zip(j.tolist(), i.tolist()), points[:, 2]):
            if z < lowest.get(key, np.inf): lowest[key] = z
        cells = np.array(list(lowest))
        corners = [(0, 0), (0, 1), (1, 0), (1, 1)]
        cx = np.stack([x0 + (cells[:, 1] + b) * s for _, b in corners], 1)
        cy = np.stack([y0 + (cells[:, 0] + a) * s for a, _ in corners], 1)
        under = placement.contains(cx, cy).all(1)
        height = mountains.raw_height(cx, cy, np.zeros_like(cx))
        floor = np.array([lowest[tuple(c)] for c in cells.tolist()])
        self.assertGreater(under.sum(), 800)
        self.assertLessEqual(float((height.max(1) - floor)[under].max()), -placement.UNDER + 1e-6)


if __name__ == '__main__':
    unittest.main()
