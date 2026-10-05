"""The horse export's rigid meshes (assets/characters/horses/export.py): a mesh on a skin with identity bind matrices,
modelled in its bone's space, is moved into model space and rebound to the body's skin."""
import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np

CHARACTERS = Path(__file__).resolve().parents[1] / 'assets/characters'
sys.path.insert(0, str(CHARACTERS / 'botw'))
spec = importlib.util.spec_from_file_location('horse_export', CHARACTERS / 'horses/export.py')
horses = importlib.util.module_from_spec(spec)
spec.loader.exec_module(horses)


def rig():
    """Two joints (a root, and a toe 2 m along x, turned 90 degrees about z); the body skin binds them at rest, the
    rigid skin with identities. One body vertex, and one rigid vertex 1 m along the toe's own x."""
    gltf = {'nodes': [{'name': 'Root', 'children': [1]},
                      {'name': 'Toe', 'translation': [2, 0, 0], 'rotation': [0, 0, .7071068, .7071068]},
                      {'name': 'Body', 'mesh': 0, 'skin': 0}, {'name': 'Shoe', 'mesh': 1, 'skin': 1}],
            'meshes': [], 'skins': [], 'bufferViews': [], 'accessors': []}
    binary = bytearray()
    writer = horses.bake.Writer(gltf, binary)
    toe = np.eye(4); toe[:3, :3] = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]; toe[:3, 3] = [2, 0, 0]
    inverse = np.stack([np.eye(4), np.linalg.inv(toe)]).transpose(0, 2, 1).reshape(2, 16)
    gltf['skins'] = [{'joints': [0, 1], 'inverseBindMatrices': writer.floats(inverse, 'MAT4')},
                     {'joints': [1, 0], 'inverseBindMatrices': writer.floats(np.tile(np.eye(4).reshape(16), (2, 1)), 'MAT4')}]

    def primitive(position, normal, joint):
        joints = np.array([[joint, 0, 0, 0]], '<u2')
        binary.extend(b'\x00' * (-len(binary) % 4))
        gltf['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': joints.nbytes})
        binary.extend(joints.tobytes())
        gltf['accessors'].append({'bufferView': len(gltf['bufferViews']) - 1, 'componentType': 5123, 'count': 1, 'type': 'VEC4'})
        joint_accessor = len(gltf['accessors']) - 1
        return {'attributes': {'POSITION': writer.floats([position], 'VEC3'), 'NORMAL': writer.floats([normal], 'VEC3'),
                               'JOINTS_0': joint_accessor, 'WEIGHTS_0': writer.floats([[1, 0, 0, 0]], 'VEC4')}}
    gltf['meshes'] = [{'primitives': [primitive([0, 1, 0], [0, 1, 0], 0)]},
                      {'primitives': [primitive([1, 0, 0], [1, 0, 0], 0)]}]   # rigid joint 0 is the toe
    return gltf, binary


class RigidMeshes(unittest.TestCase):
    def test_rigid_mesh_moves_to_its_bone_and_joins_the_body_skin(self):
        gltf, binary = rig()
        horses._rigid_to_model(gltf, binary)
        shoe = gltf['meshes'][1]['primitives'][0]['attributes']
        read = lambda index: horses._accessor(gltf, binary, index)[0]  # noqa: E731
        np.testing.assert_allclose(read(shoe['POSITION']), [2, 1, 0], atol=1e-5)
        np.testing.assert_allclose(read(shoe['NORMAL']), [0, 1, 0], atol=1e-5)
        self.assertEqual(gltf['nodes'][3]['skin'], 0)
        self.assertEqual(read(shoe['JOINTS_0'])[0], 1)   # the toe's slot in the body skin

    def test_bound_meshes_are_left_alone(self):
        gltf, binary = rig()
        body = dict(gltf['meshes'][0]['primitives'][0]['attributes'])
        horses._rigid_to_model(gltf, binary)
        self.assertEqual(gltf['meshes'][0]['primitives'][0]['attributes'], body)
        self.assertEqual(gltf['nodes'][2]['skin'], 0)


if __name__ == '__main__':
    unittest.main()
