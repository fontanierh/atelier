"""Scene transforms and ground clearance for the community park library scene."""
import json
import struct
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'world'))
import yori  # noqa: E402,F401
from communitypark.source import Scene, FRAME  # noqa: E402
from communitypark import layout as L  # noqa: E402
from communitypark.validate import triangle_error  # noqa: E402
from communitypark.murals import merge  # noqa: E402
from communitypark.props import spread  # noqa: E402


def fixture():
    binary = bytearray(); views = []; accessors = []
    def array(values, kind, component=5126, stride=None):
        values = np.asarray(values, dtype='<f4' if component == 5126 else '<u2')
        if stride:
            values = np.column_stack((values, np.zeros(len(values), dtype='<f4'))).astype('<f4')
        offset = len(binary); binary.extend(values.tobytes())
        views.append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(binary)-offset, **({'byteStride': stride} if stride else {})})
        accessors.append({'bufferView': len(views)-1, 'componentType': component, 'count': len(values), 'type': kind})
        return len(accessors)-1
    p = array([[0, 0, 0], [1, 0, 0], [0, 0, -1]], 'VEC3', stride=16)
    n = array([[0, 1, 0]]*3, 'VEC3')
    u0 = array([[0, 0], [1, 0], [0, 1]], 'VEC2')
    u1 = array([[.1, .2], [.3, .4], [.5, .6]], 'VEC2')
    f = array([0, 1, 2], 'SCALAR', component=5123)
    q = float(np.sqrt(.5)); translation = np.eye(4); translation[:3, 3] = [1, 2, 3]
    doc = {'asset': {'version': '2.0'}, 'scenes': [{'nodes': [0]}],
           'nodes': [{'translation': [5, 7, 9], 'scale': [2, 3, 4], 'rotation': [0, q, 0, q], 'children': [1]},
                     {'mesh': 0, 'matrix': translation.T.ravel().tolist()}],
           'meshes': [{'primitives': [{'attributes': {'POSITION': p, 'NORMAL': n, 'TEXCOORD_0': u0, 'TEXCOORD_1': u1}, 'indices': f, 'material': 0}]}],
           'bufferViews': views, 'accessors': accessors}
    header = json.dumps(doc).encode(); header += b' '*(-len(header) % 4); binary += b'\0'*(-len(binary) % 4)
    size = 12+8+len(header)+8+len(binary)
    return struct.pack('<III', 0x46546C67, 2, size)+struct.pack('<II', len(header), 0x4E4F534A)+header+struct.pack('<II', len(binary), 0x004E4942)+binary


class SourceTests(unittest.TestCase):
    def test_hierarchy_strides_axes_and_two_uvs(self):
        source = Scene(fixture()); part = source.parts[0]
        # Parent maps native x to -z and native z to x, after nonuniform scale.
        np.testing.assert_allclose(part['vertices'], [[17, -7, 13], [17, -5, 13], [13, -7, 13]], atol=1e-6)
        np.testing.assert_allclose(part['normals'], [[0, 0, 1]]*3, atol=1e-6)
        np.testing.assert_allclose(part['uv0'], [[0, 0], [1, 0], [0, 1]])
        np.testing.assert_allclose(part['uv1'], [[.1, .2], [.3, .4], [.5, .6]], atol=1e-6)
        np.testing.assert_array_equal(part['faces'], [[0, 1, 2]])
        self.assertAlmostEqual(float(np.linalg.det(FRAME)), 1.)

    def test_import_comparison_pairs_near_duplicates_and_rejects_drift(self):
        a = np.array([[12.04, 0, 0], [12.04, 5, 0], [12.04, 0, 7]])
        expected = np.stack((a, a+[.04, 0, 0], a+[.02, 0, 0]))
        actual = expected[[2, 0, 1]][:, [2, 0, 1]]+.0002
        self.assertLess(triangle_error(expected, actual), .001)
        actual[0, 1, 2] += .03
        with self.assertRaises(AssertionError): triangle_error(expected, actual)


class PlacementTests(unittest.TestCase):
    def setUp(self):
        available = patch('communitypark.layout.available', return_value=True); available.start(); self.addCleanup(available.stop)

    def tearDown(self):
        L.cover.cache_clear(); L.grid.cache_clear()

    def test_rigid_transform_and_access(self):
        points = np.random.default_rng(7).uniform(-40, 40, (30, 3))
        np.testing.assert_allclose(L.local(L.place(points)), points, atol=1e-12)
        np.testing.assert_allclose(np.linalg.norm(np.diff(L.place(points), axis=0), axis=1), np.linalg.norm(np.diff(points, axis=0), axis=1))
        path = L.access(); np.testing.assert_allclose(path[[0, -1]], np.array([L.ACCESS[0], L.ENTRY]))
        grade = abs(np.diff(path[:, 2]))/np.linalg.norm(np.diff(path[:, :2], axis=0), axis=1)
        self.assertLess(float(grade.max()), .10)

    def test_station_street_asphalt_stays_beneath_the_path_join(self):
        # The x=1240 street runs on to y=350 under the path: 2 m vertex rows of asphalt
        # 6.5 cm above the carved ground (hidamari streets()). No quad may rise above the ribbon.
        street = 36.
        x0, y0, z0 = L.ACCESS[0]
        self.assertAlmostEqual(z0, street+.065)
        u, v = np.meshgrid(np.linspace(0, 1, 9), np.linspace(0, 1, 21))
        ribbon = L.access()
        for row in range(336, 350, 2):  # the street's own vertex rows, every 2 m from y=-90
            for lo, hi in zip(np.linspace(-3.8, 3.8, 9)[:-1], np.linspace(-3.8, 3.8, 9)[1:]):
                corner = lambda dx, y: float(L.carve_access(x0+dx, y, street))+.065
                x = x0+lo+(hi-lo)*u; y = row+2*v
                asphalt = (corner(lo, row)*(1-u)+corner(hi, row)*u)*(1-v)+(corner(lo, row+2)*(1-u)+corner(hi, row+2)*u)*v
                under = (abs(x-x0) <= L.WIDTH/2) & (y >= y0)
                top = np.interp(y, ribbon[:, 1], ribbon[:, 2])
                self.assertLessEqual(float((asphalt-top)[under].max(initial=-1)), 1e-6, (row, lo))

    def test_thin_floor_between_grid_nodes_stays_clear(self):
        # No integer x lies inside this 0.3 m spacer; checking only grid-node
        # triangle interiors would leave the terrain over its entire surface.
        triangles = np.array([[[.15, -6, 7], [.45, -6, 7], [.45, 6, 7]],
                              [[.15, -6, 7], [.45, 6, 7], [.15, 6, 7]]])
        source = SimpleNamespace(triangles=lambda: triangles)
        def base(x, y): return np.full(np.broadcast(x, y).shape, 55.)
        with patch('communitypark.layout.scene', return_value=source):
            points = L.place(np.column_stack((np.full(30, .3), np.linspace(-6, 6, 30), np.full(30, 7))))
            ground = L.ground(points[:, 0], points[:, 1], base)
            self.assertGreaterEqual(float((points[:, 2]-ground).min()), .249)

    def test_downward_foundation_is_buried_and_patch_boundary_matches(self):
        triangles = np.array([[[-4, -4, 10], [4, -4, 10], [4, 4, 10]],
                              [[-4, -4, 10], [4, 4, 10], [-4, 4, 10]],
                              [[-4, -4, 0], [4, 4, 0], [4, -4, 0]]])
        source = SimpleNamespace(triangles=lambda: triangles)
        def base(x, y): return np.full(np.broadcast(x, y).shape, 55.)
        with patch('communitypark.layout.scene', return_value=source):
            self.assertAlmostEqual(float(L.ground(1280, 560, base)), L.ORIGIN[2]+10-.25)
            x, y, z = L.grid(base)
            np.testing.assert_allclose(z[0, :], L.carve_access(x[0], y[0], base(x[0], y[0])))
            np.testing.assert_allclose(z[-1, :], base(x[-1], y[-1]))

    def test_mature_forest_screen_keeps_riding_and_entrance_clear(self):
        source = SimpleNamespace(triangles=lambda: np.array([[[-47, -51, 10], [47, -51, 10], [47, 51, 10]],
                                                             [[-47, -51, 10], [47, 51, 10], [-47, 51, 10]]]))
        def base(x, y): return np.full(np.broadcast(x, y).shape, 48.)
        with patch('communitypark.layout.scene', return_value=source):
            plants = L.screen_vegetation(base)
            self.assertEqual(plants, L.screen_vegetation(base))
        canopy = {name: rows for name, rows in plants.items() if name.startswith('Tree_Canopy') or name == 'Tree_Cedar_A'}
        self.assertGreater(sum(map(len, canopy.values())), 1200)
        self.assertTrue(all(not name.endswith('_lo') and not name.startswith('HD_North') for name in plants))
        self.assertTrue(any(name.startswith('Bush') for name in plants))
        self.assertIn('Grass_A', plants); self.assertIn('Litter', plants)
        for name, rows in plants.items():
            a = np.asarray(rows); positions = L.place(a[:, :3])
            margin = 4.5 if name.startswith('Tree') else 2.7 if name.startswith('Bush') else 1.5
            self.assertTrue(np.all((abs(positions[:, 0]-1280) >= 47+margin) | (abs(positions[:, 1]-560) >= 51+margin)))
            distance, _ = L.access_nearest(positions[:, 0], positions[:, 1])
            gap = 9.5 if name in canopy else 6.8 if name.startswith('Tree') else 4.8 if name.startswith('Bush') else 3.2
            self.assertGreaterEqual(float(distance.min()), gap)
        # Sample the woodland belt independently of the scatter grid: isolated
        # rows of trees would leave wide gaps between these ground-level views.
        x, y = np.meshgrid(np.arange(1178., 1383., 5.), np.arange(454., 667., 5.))
        xy = np.column_stack((x.ravel(), y.ravel()))
        edge = np.maximum(abs(xy-[1280, 560])-[47, 51], 0).max(1)
        distance, _ = L.access_nearest(xy[:, 0], xy[:, 1])
        probes = xy[(edge > 12) & (edge < 50) & (distance > 15)]
        crowns = np.concatenate([L.place(np.asarray(rows)[:, :3])[:, :2] for rows in canopy.values()])
        nearest = np.linalg.norm(probes[:, None]-crowns[None], axis=2).min(1)
        self.assertLess(float(nearest.max()), 5.)



class OptionalSourceTests(unittest.TestCase):
    def test_without_the_private_source_hidamari_is_unchanged(self):
        def base(x, y): return np.full(np.broadcast(x, y).shape, 40.)
        trees = {'Tree_Maple_A': [[1280., 560., 40., 0., 1.]], 'HD_NorthTreeGold': [[1300., 450., 41., 0., 1.]]}
        before = {name: [list(row) for row in rows] for name, rows in trees.items()}
        with patch('communitypark.layout.available', return_value=False):
            x, y = np.array([1240., 1280., 1300.]), np.array([380., 450., 560.])
            np.testing.assert_array_equal(L.carve_access(x, y, base(x, y)), base(x, y))
            np.testing.assert_array_equal(L.surface(x, y, base), base(x, y))
            self.assertFalse(L.cell_inside(1250., 550.)); self.assertEqual(L.near_boxes(), [])
            L.clear(trees); self.assertEqual(trees, before)

    def test_recipe_declares_every_step_after_what_it_needs(self):
        # atelier runs steps in declaration order, so data.stage must come after the park export it stages.
        game = Path(__file__).resolve().parents[1]
        with patch.object(sys, 'path', [str(game.parents[1] / 'platform/studio'), *sys.path]):
            from atelier import build
            recipe = build.load_recipe(game.name)
        context = SimpleNamespace(game=game.name, out=game / 'build', uproject=game / 'unreal/Yorimichi.uproject')
        for park in (None, game / 'build/communitypark/source/megapark-textured.glb'):
            with self.subTest(source=bool(park)), patch.object(recipe, 'communitypark', return_value=park):
                names = [step.name for step in recipe.steps(context)]
                self.assertEqual('world.communitypark' in names, bool(park))
                for step in recipe.steps(context):
                    for need in step.needs + step.after:
                        self.assertLess(names.index(need), names.index(step.name), f'{step.name} runs before {need}')


class DecorationTests(unittest.TestCase):
    def test_coplanar_walls_sharing_an_edge_merge(self):
        wall = dict(normal=np.array([1., 0., 0.]), plane=5., u0=0., u1=2., z0=48., z1=50.)
        found = merge([wall, {**wall, 'u0': 2., 'u1': 3.5}, {**wall, 'u0': 0., 'u1': 3.5, 'z0': 50., 'z1': 51.},
                       {**wall, 'plane': 6.}])
        self.assertEqual(len(found), 2)
        joined = next(w for w in found if w['plane'] == 5.)
        self.assertEqual((joined['u0'], joined['u1'], joined['z0'], joined['z1']), (0., 3.5, 48., 51.))

    def test_props_spread_at_least_three_metres_apart(self):
        xy = np.column_stack((np.arange(0., 20., .5), np.zeros(40)))
        chosen = spread(xy, 10, [np.array([0., 0.])], np.random.default_rng(1))
        picked = np.vstack(([0., 0.], xy[chosen]))
        gaps = np.linalg.norm(picked[:, None]-picked[None], axis=2)+np.eye(len(picked))*99
        self.assertGreaterEqual(gaps.min(), 3.)
        self.assertEqual(len(chosen), 4)  # 19.5, ~10, ~5 and ~15 m; a fifth would be under 3 m from one


if __name__ == '__main__':
    unittest.main()
