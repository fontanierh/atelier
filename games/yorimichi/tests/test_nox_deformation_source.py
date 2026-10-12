"""The deformation source preserves the approved neutral design and embeds its pose corrections."""
import hashlib
import json
from pathlib import Path

import numpy as np

from atelier.gltf import glb_parts

SOURCE = Path(__file__).resolve().parents[1] / 'assets/characters/nox'


def neutral_fingerprint(doc, binary, contract):
    """Remove only the allowed body weights and appended seat-shape declarations."""
    doc = json.loads(json.dumps(doc))
    mesh = doc['meshes'][0]
    mesh['primitives'][0].pop('targets', None)
    mesh.pop('weights', None)
    if 'extras' in mesh:
        mesh['extras'].pop('targetNames', None)
        if not mesh['extras']:
            mesh.pop('extras')
    for node in doc['nodes']:
        if node.get('mesh') == 0:
            node.pop('weights', None)
    doc['accessors'] = doc['accessors'][:contract['accessors']]
    doc['bufferViews'] = doc['bufferViews'][:contract['buffer_views']]
    doc['buffers'][0]['byteLength'] = contract['buffer_bytes']
    blob = bytearray(binary[:contract['buffer_bytes']])
    for key in ('JOINTS_0', 'WEIGHTS_0'):
        accessor = doc['accessors'][mesh['primitives'][0]['attributes'][key]]
        view = doc['bufferViews'][accessor['bufferView']]
        start = view.get('byteOffset', 0)
        blob[start:start + view['byteLength']] = bytes(view['byteLength'])
    digest = hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(',', ':')).encode())
    digest.update(blob)
    return digest.hexdigest()


def test_neutral_geometry_and_non_body_skin_are_preserved():
    provenance = json.loads((SOURCE / 'provenance/deformation-repair.json').read_text())
    doc, binary = glb_parts((SOURCE / 'Nox.glb').read_bytes())
    assert neutral_fingerprint(doc, binary, provenance['neutral_contract']) == provenance['neutral_sha256']


def test_body_weights_are_valid_and_uv_seams_move_together():
    doc, binary = glb_parts((SOURCE / 'Nox.glb').read_bytes())
    attributes = doc['meshes'][0]['primitives'][0]['attributes']
    def read(name, dtype, width):
        accessor = doc['accessors'][attributes[name]]
        view = doc['bufferViews'][accessor['bufferView']]
        dtype = np.dtype(dtype)
        return np.ndarray((accessor['count'], width), dtype, binary,
                          offset=view.get('byteOffset', 0) + accessor.get('byteOffset', 0),
                          strides=(view.get('byteStride', width * dtype.itemsize), dtype.itemsize))
    joints, weights = read('JOINTS_0', 'u1', 4), read('WEIGHTS_0', '<f4', 4)
    bone_count = len(doc['skins'][0]['joints'])
    assert int(joints.max()) < bone_count
    assert np.all(np.isfinite(weights)) and np.all(weights >= 0)
    np.testing.assert_allclose(weights.sum(axis=1), 1., rtol=0, atol=2e-6)
    positions = read('POSITION', '<f4', 3)
    _, first, inverse = np.unique(positions, axis=0, return_index=True, return_inverse=True)
    dense = np.zeros((len(weights), bone_count), dtype=np.float32)
    np.add.at(dense, (np.arange(len(weights))[:, None], joints), weights)
    np.testing.assert_allclose(dense, dense[first][inverse], rtol=0, atol=2e-6)


def test_seat_targets_are_complete_sparse_and_neutral_at_rest():
    doc, binary = glb_parts((SOURCE / 'Nox.glb').read_bytes())
    body, head = doc['meshes']
    primitive = body['primitives'][0]
    names = body['extras']['targetNames']
    grid = [-25, 0, 35, 70, 105]
    angle = lambda value: 'm' + str(-value) if value < 0 else str(value)
    expected = [f'NoxSeat_L{angle(left)}_R{angle(right)}' for left in grid for right in grid]
    assert names == expected and body['weights'] == [0.] * 25
    assert 'targets' not in head['primitives'][0]
    assert all(node.get('weights', [0.] * 25) == [0.] * 25 for node in doc['nodes'] if node.get('mesh') == 0)
    assert len(primitive['targets']) == 25
    vertex_count = doc['accessors'][primitive['attributes']['POSITION']]['count']
    for target, (left, right) in zip(primitive['targets'], ((left, right) for left in grid for right in grid)):
        assert set(target) == {'POSITION'}
        accessor = doc['accessors'][target['POSITION']]
        assert accessor['componentType'] == 5126 and accessor['type'] == 'VEC3'
        assert accessor['count'] == vertex_count and 'bufferView' not in accessor
        if max(left, right) <= 35:
            assert 'sparse' not in accessor
            assert accessor['min'] == accessor['max'] == [0., 0., 0.]
            continue
        sparse = accessor['sparse']
        assert sparse['count'] == 1474 and sparse['indices']['componentType'] == 5123
        view = doc['bufferViews'][sparse['indices']['bufferView']]
        indices = np.frombuffer(binary, '<u2', sparse['count'], view.get('byteOffset', 0))
        assert int(indices[-1]) < vertex_count and np.all(indices[1:] > indices[:-1])
        view = doc['bufferViews'][sparse['values']['bufferView']]
        values = np.frombuffer(binary, '<f4', sparse['count'] * 3, view.get('byteOffset', 0)).reshape(-1, 3)
        assert np.all(np.isfinite(values)) and np.all(np.linalg.norm(values, axis=1) > 0)
