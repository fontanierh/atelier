"""The Mega Park restyle: desert plants become island trees where they stood, the forest round the park turns
detailed, SHARKS becomes 寄り道 in its place."""
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world' / 'regions'))
from megapark import cars, forest, placement, plants, sign  # noqa: E402


class PlantTests(unittest.TestCase):
    def test_every_plant_becomes_one_island_tree(self):
        trees = plants.replacements()
        self.assertTrue(0 < len(plants.plants()) - sum(map(len, trees.values())) < 12)   # those on the roll-in go
        self.assertGreater(len(plants.plants()), 300)
        self.assertEqual(trees, plants.replacements())
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

    def test_the_seam_is_planted_on_its_own_hillside(self):
        seam = plants.seam()
        rows = np.array([p[:3] for items in seam.values() for p in items])
        self.assertGreater(len(rows), 200)
        self.assertTrue({'HD_NorthRockA', 'HD_NorthRockB'} & set(seam))
        island = placement.native_to_island(rows)
        self.assertTrue(placement.contains(island[:, 0], island[:, 1]).all())
        lo, hi = placement.seam_render().reshape(-1, 3).min(0) - 1, placement.seam_render().reshape(-1, 3).max(0) + 1
        self.assertTrue(((rows >= lo) & (rows <= hi)).all())

    def test_every_foliage_texture_is_in_the_park(self):
        models, _ = placement.kept()
        used = {p.get('retail_texture_ids', {}).get('diffuse') for m in models for p in m['meshes']}
        self.assertLessEqual(set(plants.FOLIAGE), used)

    def test_park_trees_are_the_detailed_kind(self):
        trees = plants.trees()
        self.assertFalse([name for name in trees if name.endswith('_lo') or name.startswith('Tree_Canopy')])

    def test_ledge_plants_grow_on_rock_and_soil_clear_of_the_built_park_and_the_lines(self):
        ledges = plants.ledges()
        def shrub(name, scale):     # a small maple or pine is a shrub (plants.SHRUB_SCALE)
            return not name.startswith('Tree') or scale <= plants.SHRUB_SCALE.get(name, (0, 0))[1] + 1e-3
        kinds = [shrub(name, row[4]) for name, rows in ledges.items() for row in rows]
        self.assertGreater(kinds.count(False), 200); self.assertGreater(kinds.count(True), 1000)
        _, built = plants._surfaces()
        for name, rows in ledges.items():
            for row in rows[::7]:
                small = shrub(name, row[4])
                q = np.array(row[:3]); q[1] += .15 if small else plants.SINK
                clear = plants.BUILT_CLEAR[1 if small else 0]
                self.assertGreater(np.linalg.norm(built - q, axis=1).min(), clear - .01, (name, q))
                self.assertFalse(plants._ridden(q, 0.), (name, q))


class ForestTests(unittest.TestCase):
    def setUp(self):
        x0, y0, x1, y1 = forest.near_box()
        gx, gy = np.meshgrid(np.arange(x0 - 60, x1 + 60, 9.), np.arange(y0 - 60, y1 + 60, 9.))
        self.xy = np.stack([gx.ravel(), gy.ravel()], 1)
        self.d = forest.distance(self.xy[:, 0], self.xy[:, 1])

    def test_distance_is_zero_on_the_park_and_grows_off_it(self):
        x, y = self.xy.T
        self.assertTrue((self.d[placement.contains(x, y)] == 0).all())
        self.assertTrue((self.d[~placement.contains(x, y, margin=10.)] > 2.5).all())
        x0, y0, x1, y1 = forest.near_box()
        inside = (x > x0) & (x < x1) & (y > y0) & (y < y1)
        self.assertTrue(inside[self.d < forest.FAR - 5].all())

    def test_low_poly_crowns_turn_detailed_round_the_park(self):
        off = self.d > forest.CLEAR
        rows = [[x, y, 50., 0., 1.] for x, y in self.xy[off]]
        instances = {'HD_NorthTreeRust': [list(r) for r in rows]}
        flat = lambda x, y: np.full(np.shape(x), 50.)
        far = lambda x, y: np.full(np.shape(x), 1e3)
        forest.grow(instances, flat, far)
        # Crowns past the band stay where they were, in the clump of where they stand; opaque crowns close the canopy
        # in the gaps beyond the detailed band, out to OUTER.
        kinds = {k: np.array(v) for k, v in instances.items() if k.startswith('HD_NorthTree')}
        crowns = np.concatenate(list(kinds.values()))[:, :2]
        kind = np.concatenate([np.full(len(v), forest.CROWNS.index(k.removeprefix('HD_NorthTree').removeprefix('Backdrop')))
                               for k, v in kinds.items()])
        planted = {tuple(r[:2]) for r in rows}
        original = np.array([tuple(q) in planted for q in crowns.tolist()])
        d = forest.distance(crowns[:, 0], crowns[:, 1])
        self.assertTrue((d[original] >= forest.NEAR).all())
        self.assertEqual(int((d[original] >= forest.FAR).sum()), int((self.d[off] >= forest.FAR).sum()))
        self.assertGreater(int((~original).sum()), 0)
        self.assertTrue(((d[~original] > forest.NEAR + 30) & (d[~original] < forest.OUTER)).all())
        band = d > forest.NEAR + 90
        self.assertGreater(float((kind[band] == forest._clump(*crowns[band].T, forest.CROWN_CLUMPS)).mean()), .75)
        added = {k: np.array(v) for k, v in instances.items() if k.startswith('Tree')}
        self.assertLessEqual(set(added), set(forest.HEIGHT))
        under = {k for k in instances if not k.startswith(('Tree', 'HD_NorthTree'))}
        self.assertLessEqual(under, {n for n, _ in forest.BUSHES} | {'Grass_A', 'Grass_B'} | {n for n, _, _ in forest.SEAM_PLANTS})
        new = np.concatenate(list(added.values()))
        self.assertTrue((forest.distance(new[:, 0], new[:, 1]) > forest.CLEAR).all())
        self.assertGreater(len(new), int((self.d[off] < forest.NEAR).sum()))
        again = {'HD_NorthTreeRust': [list(r) for r in rows]}
        forest.grow(again, flat, far)
        self.assertEqual(again, instances)


    def test_the_crowns_replace_the_far_forest_west_of_the_park(self):
        grid = [[float(x), float(y), 150., 0., 2.] for x in range(-1800, -400, 40) for y in range(400, 2400, 40)]
        world = {'instances': {'Tree_Maple_lo': [list(r) for r in grid], 'Tree_Maple_A': [list(r) for r in grid]}}
        forest.clear_far_forest(world)
        self.assertEqual(world['instances']['Tree_Maple_A'], grid)
        left = {tuple(q[:2]) for q in world['instances']['Tree_Maple_lo']}
        gone = np.array([r[:2] for r in grid if tuple(r[:2]) not in left])
        self.assertGreater(len(gone), 100)
        self.assertTrue((gone[:, 0] < forest.mountains.BOUNDS[0]).all() and (gone[:, 1] > 650).all())
        self.assertTrue((forest.distance(gone[:, 0], gone[:, 1]) < forest.OUTER).all())
        kept = np.array([r[:2] for r in grid if tuple(r[:2]) in left])
        inner = ((kept[:, 0] < forest.mountains.BOUNDS[0]) & (kept[:, 1] > 650)
                 & (forest.distance(kept[:, 0], kept[:, 1]) < forest.OUTER - 250))
        self.assertFalse(inner.any())


class CarTests(unittest.TestCase):
    def test_the_traffic_cars_are_the_cars_park_cars(self):
        models = {m['asset_id']: m for m in placement.kept()[0]}
        self.assertLessEqual(set(cars.CARS), set(models))
        names = [p['material_name'].lower() for a in cars.CARS for p in models[a]['meshes'] if cars.is_car(models[a], p)]
        self.assertEqual(len(names), 5)
        self.assertTrue(all(any(k in n for k in ('traf', 'sport', 'sedan', 'suv', 'tire')) for n in names), names)
        self.assertEqual(len(cars.bays()), len(cars.KEI))

    def test_only_the_cars_leave_the_collision(self):
        section = next(c for c in placement.source()['collision'] if c['id'] == cars.SECTION)
        triangles = np.load(placement.SOURCE / section['npz'])['triangles']
        mask = cars.collision_mask(triangles)
        self.assertEqual(int(mask.sum()), 762)
        for lo, hi in cars.bays():      # the bays' ground stays
            self.assertTrue(np.isfinite(cars._ground(triangles[~mask].astype('f8'), (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2)))
        for other in placement.kept()[1]:
            if other['id'] != cars.SECTION:
                self.assertFalse(cars.collision_mask(np.load(placement.SOURCE / other['npz'])['triangles']).any(), other['id'])

    def test_kei_cars_stand_on_the_ground_in_their_bays(self):
        for prop, (lo, hi) in zip(cars.props(), cars.bays()):
            x, z, y = np.array(prop['location_cm']) / 100
            self.assertTrue(lo[0] < x < hi[0] and lo[2] < z - cars.KEI_LENGTH / 2 and z + cars.KEI_LENGTH / 2 < hi[2], prop)
            self.assertLess(abs(y - lo[1]), .2, prop)
            forward, up = np.array(prop['forward']), np.array(prop['up'])
            self.assertGreater(up[2], .99); self.assertGreater(forward[1], .99)
            self.assertAlmostEqual(float(forward @ up), 0., 6)


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
