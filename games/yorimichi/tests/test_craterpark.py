"""Crater Park stands on the caldera floor as one rigid body, from its author's arrays (docs/CRATERPARK.md)."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

import numpy as np

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world' / 'regions'))
from craterpark import placement  # noqa: E402
from hidamari import mountains  # noqa: E402


class LibraryTests(unittest.TestCase):
    def test_arrays_match_the_source_checksums(self):
        scene = placement.scene()
        self.assertEqual(len(scene['meshes']), scene['counts']['jsonMeshes'])
        triangles = 0
        for entry in scene['meshes']:
            a = placement.arrays(entry)
            digest = hashlib.sha256(a['positions'].tobytes() + a['uvs'].tobytes() + a['triangles'].tobytes()).hexdigest()
            self.assertEqual(digest, entry['arraysSha256'], entry['id'])
            self.assertEqual(len(a['triangles']), entry['triangleCount'])
            self.assertEqual(len(a['render_skip']), entry['render_skip'])
            triangles += len(a['triangles'])
        self.assertEqual(triangles, scene['counts']['triangles'])

    def test_every_material_resolves(self):
        materials = {m['id']: m for m in json.loads((placement.SOURCE / 'materials.json').read_text())}
        self.assertEqual({m['material'] for m in placement.scene()['meshes']} - set(materials), set())
        for m in materials.values():
            if m['texture']:
                self.assertTrue((placement.SOURCE / m['texture']).is_file(), m['texture'])
                self.assertIn(m['texture'], placement.scene()['textures'])


class PlacementTests(unittest.TestCase):
    def test_rigid_and_unreal_transform_agree(self):
        lo, hi = np.asarray(placement.scene()['bounds'])
        native = np.random.default_rng(7).uniform(lo, hi, (200, 3))
        island = placement.native_to_island(native)
        unreal = placement.to_unreal(native) / 100 * [1, -1, 1]
        np.testing.assert_allclose(island, unreal, atol=1e-6)
        before = np.linalg.norm(native[:, None] - native[None], axis=-1)
        after = np.linalg.norm(island[:, None] - island[None], axis=-1)
        np.testing.assert_allclose(before, after, atol=1e-6)

    def test_the_block_sits_inside_the_caldera_wall(self):
        """Every corner of the block keeps at least 60 m to the wall's foot."""
        t = placement.ground_triangles().reshape(-1, 3)
        _, _, r, angle = mountains.polar(t[:, 0], t[:, 1])
        self.assertGreater(float((mountains.wall_foot(angle) - r).min()), 60.)

    def test_the_tallest_ramps_rise_just_over_the_rim(self):
        """The main deck stands about level with the rim's lowest stretch and the tallest ramp over most of the rim, but
        no part of the park stands over the rim's high stretches."""
        a = np.linspace(0, 2 * np.pi, 720, endpoint=False); rim = mountains.rim_radius(a)
        crest = mountains.natural_height(mountains.VOLCANO[0] + rim * np.cos(a), mountains.VOLCANO[1] + rim * np.sin(a))
        deck = float(placement.native_to_island(np.array([[1300., 5., 1008.6]]))[0, 2])
        top = max(float(placement.native_to_island(placement.arrays(e)['positions'].astype('f8'))[:, 2].max())
                  for e in placement.meshes())
        self.assertLess(abs(deck - float(crest.min())), 10.)
        self.assertGreater(top, float(np.median(crest)) - 10.)
        self.assertLess(top, float(np.percentile(crest, 90)))

    def test_the_low_edge_meets_the_floor(self):
        self.assertLess(abs(float(np.nanmin(placement.footprint()[3])) - mountains.caldera_floor()), 10.)

    def test_the_drop_in_stands_on_the_park(self):
        ground, camera = placement.drop_in()
        self.assertTrue(placement.contains(ground[0], ground[1]))
        self.assertGreater(camera[2], ground[2])


class TerrainTests(unittest.TestCase):
    def test_ground_stays_inside_the_block(self):
        """Every terrain node on the block lies at least a metre under the block's top within a cell of it."""
        fx0, fy0, cell, top, mask = placement.footprint()
        s = mountains.STEP
        x, y = np.meshgrid(np.arange(fx0 - s, fx0 + top.shape[1] * cell + s, s), np.arange(fy0 - s, fy0 + top.shape[0] * cell + s, s))
        z = mountains.raw_height(x, y, 0.)
        on = placement.contains(x, y)
        reach = int(s / cell)
        padded = np.pad(np.where(mask, top, np.inf), reach, constant_values=np.inf)
        i = ((x - fx0) / cell).astype(int) + reach; j = ((y - fy0) / cell).astype(int) + reach
        lowest = np.min([padded[np.clip(j + dj, 0, padded.shape[0] - 1), np.clip(i + di, 0, padded.shape[1] - 1)]
                         for dj in range(-reach, reach + 1) for di in range(-reach, reach + 1)], axis=0)
        self.assertGreater(int(on.sum()), 1000)
        self.assertGreaterEqual(float((lowest - z)[on].min()), 1.)

    def test_ground_rises_to_the_block_edge(self):
        """Just outside the block the ground stands within a couple of metres of its top edge, so its sides are buried."""
        fx0, fy0, cell, top, mask = placement.footprint()
        q = np.pad(mask, 1)
        rim = mask & ~(q[:-2, 1:-1] & q[2:, 1:-1] & q[1:-1, :-2] & q[1:-1, 2:])
        j, i = np.nonzero(rim)
        x, y = fx0 + (i + .5) * cell, fy0 + (j + .5) * cell
        cx, cy = placement.CENTRE
        out = 1.5 * cell / np.hypot(x - cx, y - cy)
        ox, oy = x + (x - cx) * out, y + (y - cy) * out
        keep = ~placement.contains(ox, oy)
        gap = top[j, i][keep] - placement.terrain(ox[keep], oy[keep], mountains.natural_height(ox[keep], oy[keep]), mountains.natural_height)
        self.assertLess(float(np.percentile(np.abs(gap), 95)), 3.)


if __name__ == '__main__':
    unittest.main()
