"""The Mega Park restyle: desert plants become island trees where they stood, SHARKS becomes 寄り道 in its place."""
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world' / 'regions'))
from megapark import placement, plants, sign  # noqa: E402


class PlantTests(unittest.TestCase):
    def test_every_plant_becomes_one_island_tree(self):
        trees = plants.trees()
        self.assertEqual(sum(map(len, trees.values())), len(plants.plants()))
        self.assertGreater(len(plants.plants()), 300)
        self.assertEqual(trees, plants.trees())
        self.assertLessEqual(set(trees), set(plants.MESHES))
        smallest = min(r[0] for _, r in plants.CHOICES.values()) * .92
        largest = max(r[1] for _, r in plants.CHOICES.values()) * 1.08
        for items in trees.values():
            scales = np.array(items)[:, 4]
            self.assertTrue(((scales >= smallest - 1e-3) & (scales <= largest + 1e-3)).all())

    def test_trees_stand_on_the_park(self):
        base = np.array([p[:3] for items in plants.trees().values() for p in items])
        island = placement.native_to_island(base)
        self.assertTrue(placement.contains(island[:, 0], island[:, 1]).all())

    def test_every_foliage_texture_is_in_the_park(self):
        models, _ = placement.kept()
        used = {p.get('retail_texture_ids', {}).get('diffuse') for m in models for p in m['meshes']}
        self.assertLessEqual(set(plants.FOLIAGE), used)



class LetterTests(unittest.TestCase):
    def test_letters_face_the_park_with_the_trusses_behind(self):
        f = sign.frame()
        _, _, supports = sign._source()
        self.assertLess(float(((supports - f['centre']) @ f['normal']).mean()), -.5)
        _, sections = placement.kept()
        park = np.concatenate([np.load(placement.SOURCE / s['npz'])['triangles'].reshape(-1, 3)[::50] for s in sections])
        self.assertGreater(float((((park - f['centre']) @ f['normal']) > 0).mean()), .95)
        np.testing.assert_allclose(np.cross(f['axis'], [0, 1, 0]), f['normal'], atol=1e-12)

    def test_only_the_letters_leave_the_collision(self):
        section = next(c for c in placement.source()['collision'] if c['id'] == sign.SECTION)
        triangles = np.load(placement.SOURCE / section['npz'])['triangles']
        mask = sign.letters_mask(triangles)
        self.assertEqual(int(mask.sum()), 2172)
        self.assertGreater(float(triangles[mask][..., 1].min()), sign.frame()['bottom'] - .05)
        for other in placement.source()['collision']:
            if other['id'] != sign.SECTION:
                self.assertFalse(sign.letters_mask(np.load(placement.SOURCE / other['npz'])['triangles']).any(), other['id'])

    def test_font_has_the_black_glyphs(self):
        from fontTools.ttLib import TTFont
        with tempfile.TemporaryDirectory() as tmp:
            face = TTFont(sign.font(Path(tmp) / 'letters.ttf'))
            self.assertNotIn('fvar', face)
            self.assertLessEqual({ord(c) for c in sign.TEXT}, set(face.getBestCmap()))


if __name__ == '__main__':
    unittest.main()
