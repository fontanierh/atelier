"""Current-scene coverage, portable source assets and the physical northern join."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
import yori  # noqa: E402,F401
from atelier.gltf import glb_parts  # noqa: E402
from belmonte import layout as L, source, planting, terrain, appearance  # noqa: E402
from hidamari import layout as H  # noqa: E402


class CurrentSource(unittest.TestCase):
    def test_every_model_is_current_consumed_and_checksum_pinned(self):
        data = source.manifest()
        self.assertEqual(data['source']['revision'], 'fec48785a36e666d092134f73cebb157f020d3cd')
        self.assertEqual(len(data['meshes']), 288)
        used = {entry['asset'] for entry in data['placements']}
        self.assertEqual(used, {entry['source_asset'] for entry in data['meshes']})
        for entry in data['meshes']:
            path = source.LIBRARY / entry['path']
            self.assertEqual(source.sha(path), entry['sha256'], entry['name'])
            if 'collision' in entry:
                self.assertEqual(source.sha(source.LIBRARY / entry['collision']['path']), entry['collision']['sha256'])
            self.assertNotIn('Backdrop', entry['name'])
            self.assertFalse(entry['name'].startswith('SM_BM_BV_'))

    def test_render_primitives_have_no_foliage_or_collision_hulls(self):
        for entry in source.manifest()['meshes']:
            doc, _ = glb_parts((source.LIBRARY / entry['path']).read_bytes())
            self.assertTrue(all(not node['name'].startswith('UCX_') for node in doc['nodes']))
            self.assertTrue(all('foliage' not in material['name'].lower() for material in doc['materials']))
            self.assertEqual(sum(doc['accessors'][primitive['indices']]['count'] // 3
                                 for mesh in doc['meshes'] for primitive in mesh['primitives']), entry['triangles'])

    def test_only_consumed_colour_textures_enter_the_library(self):
        data = source.manifest()
        for entry in data['textures'].values():
            self.assertEqual(source.sha(source.LIBRARY / entry['file']), entry['sha256'])
        used = {entry['textures'].get('BaseColor') or entry['textures'].get('DryColor')
                for path, entry in data['materials'].items() if not path.endswith('MI_B_foliage')}
        self.assertEqual(set(data['textures']), used - {None})


class Terrain(unittest.TestCase):
    def test_terrain_colours_use_the_authored_layer_instead_of_fake_white(self):
        for entry in source.manifest()['meshes']:
            if not entry['name'].startswith('SM_BM_BT_Terrain_'):
                continue
            doc, binary = glb_parts((source.LIBRARY / entry['path']).read_bytes())
            for primitive in doc['meshes'][0]['primitives']:
                attrs = primitive['attributes']
                self.assertIn('COLOR_0', attrs)
                self.assertNotIn('COLOR_1', attrs)
                accessor = doc['accessors'][attrs['COLOR_0']]
                view = doc['bufferViews'][accessor['bufferView']]
                self.assertEqual(doc['extras']['atelier_vertex_colours'], 'native-byte-rgb-linear-alpha')
                colour = np.frombuffer(binary, dtype='<u2', count=accessor['count']*4,
                                       offset=view.get('byteOffset', 0)+accessor.get('byteOffset', 0)).reshape(-1, 4)
                self.assertTrue(np.all(colour[:, :3] % 257 == 0))
                np.testing.assert_allclose((colour/65535.).sum(1), 1., atol=.006)

    def test_join_colour_interpolation_and_rim_weights(self):
        surface = source.Surface([[[0., 0., 0.], [10., 0., 10.], [0., 10., 20.]]],
                                 [[[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]])
        np.testing.assert_allclose(surface.colour(2., 3.), [.5, .2, .3])
        x = (L.BOUNDS[0]+L.BOUNDS[2])/2
        self.assertEqual(float(appearance.forest_weight(x, L.BOUNDS[1])), 0.)
        self.assertEqual(float(appearance.forest_weight(x, terrain.OUTER[1])), 1.)
        self.assertTrue(.25 < float(appearance.forest_weight(x, (L.BOUNDS[1]+terrain.OUTER[1])/2)) < .75)

    def test_height_is_triangle_intersection_not_nearest_vertex(self):
        surface = source.Surface([[[0., 0., 0.], [10., 0., 10.], [0., 10., 20.]],
                                  [[10., 0., 10.], [10., 10., 30.], [0., 10., 20.]]])
        np.testing.assert_allclose(surface.height([2., 5., 10.], [3., 5., 10.]), [8., 15., 30.])
        self.assertTrue(np.isnan(surface.height(20., 20.)))

    def test_whole_valley_has_terrain_and_boundary_coverage(self):
        xs = np.linspace(L.SOURCE_BOUNDS[0], L.SOURCE_BOUNDS[2], 65)
        ys = np.linspace(L.SOURCE_BOUNDS[1], L.SOURCE_BOUNDS[3], 57)
        x, y = np.meshgrid(xs, ys)
        height = source.terrain().height(x, y)
        self.assertTrue(np.isfinite(height).all(), 'Current terrain coverage has a hole')
        self.assertGreater(float(height.max() - height.min()), 100.)

    def test_built_apron_matches_both_actual_boundaries(self):
        # The pure Python build may not have run in a fresh checkout; compare the
        # authored seam inputs here, and the actual exported mesh when present.
        x = np.linspace(L.BOUNDS[0], L.BOUNDS[2], 51)
        expected_north = source.terrain().height(x - L.ORIGIN[0], np.full_like(x, L.SOURCE_BOUNDS[1])) + L.ORIGIN[2]
        self.assertTrue(np.isfinite(expected_north).all())
        path = yori.OUT / 'belmonte/glb/SM_BM_NorthApron.glb'
        if path.is_file():
            mesh = source.Surface(source.triangles(path))
            north = mesh.height(x - L.ORIGIN[0], np.full_like(x, L.BOUNDS[1] - L.ORIGIN[1])) + L.ORIGIN[2]
            south = mesh.height(x - L.ORIGIN[0], np.full_like(x, L.SOUTH_JOIN - L.ORIGIN[1])) + L.ORIGIN[2]
            np.testing.assert_allclose(north, expected_north, atol=.002)
            np.testing.assert_allclose(south, H.north_height(x, np.full_like(x, L.SOUTH_JOIN)), atol=.02)

    def test_country_and_collar_keep_the_full_rim_closed(self):
        path = yori.OUT / 'belmonte/glb/SM_BM_NorthApron.glb'
        if not path.is_file():
            self.skipTest('Generated mesh is checked after world.belmonte')
        mesh = source.Surface(source.triangles(path))
        for axis, edge, low, high in [(1, L.BOUNDS[1], L.BOUNDS[0], L.BOUNDS[2]),
                                     (0, L.BOUNDS[2], L.BOUNDS[1], L.BOUNDS[3]),
                                     (1, L.BOUNDS[3], L.BOUNDS[0], L.BOUNDS[2]),
                                     (0, L.BOUNDS[0], L.BOUNDS[1], L.BOUNDS[3])]:
            along = np.linspace(low, high, 67)
            x, y = (along, np.full_like(along, edge)) if axis == 1 else (np.full_like(along, edge), along)
            actual = mesh.height(x - L.ORIGIN[0], y - L.ORIGIN[1]) + L.ORIGIN[2]
            expected = source.terrain().height(x - L.ORIGIN[0], y - L.ORIGIN[1]) + L.ORIGIN[2]
            np.testing.assert_allclose(actual, expected, atol=.002)
        outside = source.Surface(source.triangles(yori.OUT / 'belmonte/glb/SM_BM_NorthCountry.glb'))
        for x, y in [(np.full(61, terrain.OUTER[0]), np.linspace(terrain.OUTER[1], terrain.OUTER[3], 61)),
                     (np.full(61, terrain.OUTER[2]), np.linspace(terrain.OUTER[1], terrain.OUTER[3], 61)),
                     (np.linspace(terrain.OUTER[0], terrain.OUTER[2], 61), np.full(61, terrain.OUTER[3]))]:
            a = mesh.height(x - L.ORIGIN[0], y - L.ORIGIN[1]) + L.ORIGIN[2]
            b = outside.height(x - L.ORIGIN[0], y - L.ORIGIN[1]) + L.ORIGIN[2]
            np.testing.assert_allclose(a, b, atol=.002)

    def test_country_sinks_under_the_foothills_north_of_the_far_hills(self):
        path = yori.OUT / 'belmonte/glb/SM_BM_NorthCountry.glb'
        if not path.is_file():
            self.skipTest('Generated country checked after world.belmonte')
        mesh = source.Surface(source.triangles(path))
        y = (3200. + L.SOUTH_JOIN) / 2
        beside = mesh.height(-1500. - L.ORIGIN[0], y - L.ORIGIN[1]) + L.ORIGIN[2]
        np.testing.assert_allclose(beside, terrain.country_height(-1500., y), atol=.002)
        under = mesh.height(1000. - L.ORIGIN[0], y - L.ORIGIN[1]) + L.ORIGIN[2]
        self.assertLess(float(under), float(H.north_height(1000., y)) - 20.)
        # South of the far hills' last row the far hills own the ground, as before.
        self.assertTrue(np.isnan(mesh.height(-1500. - L.ORIGIN[0], 3100. - L.ORIGIN[1])))

    def test_the_valley_keeps_clear_of_the_volcano(self):
        from hidamari import mountains as M
        corners = np.array([(L.BOUNDS[0], L.BOUNDS[1]), (L.BOUNDS[2], L.BOUNDS[1])])
        self.assertGreater(float(np.hypot(*(corners - M.VOLCANO).T).min()), M.BASE_RADIUS)
        self.assertEqual(M.BOUNDS[3], L.SOUTH_JOIN)

    def test_grid_sampler_follows_exported_triangle_diagonal(self):
        z = np.array([[0., 0.], [0., 10.]])
        self.assertEqual(float(terrain.grid_height([0., 1.], [0., 1.], z, .75, .25)), 2.5)
        self.assertEqual(float(terrain.grid_height([0., 1.], [0., 1.], z, .25, .75)), 2.5)



class Flora(unittest.TestCase):
    def test_replacement_is_deterministic_and_uses_only_existing_island_models(self):
        data = {'meshes': [], 'placements': [], 'planting': [
            {'name': 'SM_BV_HolmOak_A', 'bounds_cm': [[-200., -200., 0.], [200., 200., 900.]],
             'count': 3, 'transforms': [
                 {'translation_cm': [1000., 1000., 0.], 'rotation_xyzw': [0., 0., 0., 1.], 'scale': [1., 1., 1.]},
                 {'translation_cm': [1001., 1001., 0.], 'rotation_xyzw': [0., 0., 0., 1.], 'scale': [1., 1., 1.]},
                 {'translation_cm': [2000., 1000., 0.], 'rotation_xyzw': [0., 0., 0., 1.], 'scale': [1., 1., 1.]}]}]}
        first, report = planting.replacements(data)
        self.assertEqual((first, report), planting.replacements(data))
        self.assertEqual(set(first), {'Tree_Tuscan_Oak'})
        self.assertEqual(len(first['Tree_Tuscan_Oak']), 2)
        self.assertLessEqual(report['kinds']['tree']['selected'], planting.BUDGETS['tree'])

    def test_tv_spots_follow_committed_building_transforms(self):
        from belmonte import build as B
        spots = {s['id']: s for s in B.tv_spots()}
        self.assertEqual(set(spots), {'osteria_front', 'osteria_back', 'salon_paris', 'salon_bar'})
        self.assertEqual(spots['osteria_front']['pivot_cm'], [-2600., -190., 248.])
        self.assertEqual(spots['osteria_front']['watch_cm'], [-3040., -160., 18.])
        self.assertEqual(spots['salon_paris']['pivot_cm'], [7500., -29720., 3255.])
        moved = json.loads(json.dumps(source.manifest()))
        taproom = {m['source_asset'] for m in moved['meshes'] if m['name'] == 'SM_BM_BH_Osteria_Taproom'}
        for p in moved['placements']:
            if p['asset'] in taproom:
                p['transform']['translation_cm'][0] += 250.
        shifted = {s['id']: s for s in B.tv_spots(moved)}
        self.assertAlmostEqual(shifted['osteria_front']['pivot_cm'][0], -2350., places=2)
        self.assertAlmostEqual(shifted['osteria_front']['watch_cm'][0], -2790., places=2)


if __name__ == '__main__':
    unittest.main()
