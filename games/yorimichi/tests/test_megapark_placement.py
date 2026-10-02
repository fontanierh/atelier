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
        self.check_terrain_under(placement.place(placement.collision_triangles()), 800, placement.UNDER)

    def test_terrain_cells_under_the_seam_stay_below_it(self):
        self.check_terrain_under(placement.place(placement.seam_triangles()), 40, .5)   # SEAM_REACH is one cell

    def check_terrain_under(self, t, cells_under, below):
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
        self.assertGreater(under.sum(), cells_under)
        self.assertLessEqual(float((height.max(1) - floor)[under].max()), -below + 1e-6)


class SeamTests(unittest.TestCase):
    """The seam: the piece of the source's hills where the park meets the air station's footbridge."""

    def test_render_and_collision_are_the_same_hillside(self):
        self.assertEqual(int(placement.seam_mask().sum()), 333)
        self.assertEqual(sum(len(f) for *_, f in placement.seam_parts()), 333)
        self.assertFalse(any(m['asset_id'] in placement.SEAM for m in placement.kept()[0]))
        self.assertNotIn(placement.SEAM_SECTION, {c['id'] for c in placement.kept()[1]})

    def test_the_skirt_hangs_level_and_outward_under_open_edges(self):
        skirt, t = placement.seam_skirt(), placement.skirt_triangles()
        self.assertEqual(len(skirt), 33); self.assertEqual(len(t), 2 * len(skirt))
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        out = np.repeat([[o[0], 0., o[1]] for *_, o in skirt], 2, 0)
        self.assertTrue(((n * out).sum(1) > 0).all())
        np.testing.assert_allclose(n[:, 1], 0., atol=1e-9)
        np.testing.assert_allclose(t[0::2, 1, 1] - t[0::2, 2, 1], placement.SKIRT_DROP)
        np.testing.assert_allclose(t[1::2, 0, 1] - t[1::2, 2, 1], placement.SKIRT_DROP)


if __name__ == '__main__':
    unittest.main()
