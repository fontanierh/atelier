"""Scene transforms and ground clearance, without needing private game assets."""
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
    def tearDown(self):
        L.cover.cache_clear(); L.grid.cache_clear()

    def test_rigid_transform_and_access(self):
        points = np.random.default_rng(7).uniform(-40, 40, (30, 3))
        np.testing.assert_allclose(L.local(L.place(points)), points, atol=1e-12)
        np.testing.assert_allclose(np.linalg.norm(np.diff(L.place(points), axis=0), axis=1), np.linalg.norm(np.diff(points, axis=0), axis=1))
        path = L.access(); np.testing.assert_allclose(path[[0, -1]], np.array([L.ACCESS[0], L.ENTRY]))
        grade = abs(np.diff(path[:, 2]))/np.linalg.norm(np.diff(path[:, :2], axis=0), axis=1)
        self.assertLess(float(grade.max()), .10)

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
            trees = L.screen_trees(base)
            self.assertEqual(trees, L.screen_trees(base))
        self.assertGreater(sum(map(len, trees.values())), 200)
        self.assertTrue(all(not name.endswith('_lo') and not name.startswith('HD_North') for name in trees))
        for rows in trees.values():
            a = np.asarray(rows); positions = L.place(a[:, :3])
            self.assertTrue(np.all((abs(positions[:, 0]-1280) >= 56) | (abs(positions[:, 1]-560) >= 60)))
            distance, _ = L.access_nearest(positions[:, 0], positions[:, 1])
            self.assertGreaterEqual(float(distance.min()), 11.)
            self.assertGreaterEqual(float(a[:, 4].min()), 1.3)


if __name__ == '__main__':
    unittest.main()
