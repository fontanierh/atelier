"""The playable boy must be usable from a fresh checkout without the upstream project."""
import hashlib
import io
import json
from pathlib import Path
import tomllib

import numpy as np
from PIL import Image
from atelier.gltf import glb_parts

GAME = Path(__file__).resolve().parents[1]
ASSETS = GAME / 'assets'
SOURCE = ASSETS / 'characters/paul'


def read(doc, binary, index):
    a = doc['accessors'][index]
    v = doc['bufferViews'][a['bufferView']]
    dtype = {5126: '<f4', 5123: '<u2', 5121: 'u1'}[a['componentType']]
    width = {'VEC3': 3, 'VEC4': 4}[a['type']]
    offset = v.get('byteOffset', 0) + a.get('byteOffset', 0)
    return np.frombuffer(binary, dtype=dtype, count=a['count'] * width, offset=offset).reshape(-1, width)


def test_self_contained_source_and_manifest():
    record = json.loads((SOURCE / 'source-manifest.json').read_text())
    data = (SOURCE / record['native']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == record['native_sha256']
    library = json.loads((ASSETS / 'source-library.json').read_text())['files']
    assert library['characters/paul/Paul.glb'] == {'bytes': len(data), 'sha256': record['native_sha256']}
    doc, binary = glb_parts(data)
    assert not doc.get('animations')
    assert len(doc['skins']) == 1 and len(doc['materials']) == 2
    assert all('uri' not in b for b in doc['buffers'])
    for image in doc['images']:
        assert 'uri' not in image and 'bufferView' in image
        v = doc['bufferViews'][image['bufferView']]
        start = v.get('byteOffset', 0)
        Image.open(io.BytesIO(binary[start:start+v['byteLength']])).verify()


def test_contract_fingers_and_skinned_geometry():
    from atelier.character.names import mixamo_aliases
    doc, binary = glb_parts((SOURCE / 'Paul.glb').read_bytes())
    joints = doc['skins'][0]['joints']
    names = {doc['nodes'][j]['name'] for j in joints}
    aliases = mixamo_aliases()
    assert set(aliases) - {'Root'} <= names            # Tripo's auto-rig: the contract's bones and fingers, Mixamo names
    ends = {n for n in names - set(aliases) if n.endswith(('4', '_End'))}
    assert names - set(aliases) == ends and len(ends) == 13    # head top, toe ends and fingertips (dropped on export)
    triangles = 0
    for mesh in doc['meshes']:
        for p in mesh['primitives']:
            attrs = p['attributes']
            weights = read(doc, binary, attrs['WEIGHTS_0'])
            indices = read(doc, binary, attrs['JOINTS_0'])
            assert np.isfinite(weights).all() and (weights >= 0).all()
            assert np.allclose(weights.sum(axis=1), 1, atol=1e-6)
            assert indices.max() < len(joints)
            used = {joints[i] for i in np.unique(indices[weights > 0])}
            assert not {doc['nodes'][j]['name'] for j in used} & ends   # the end bones carry no weight
            triangles += doc['accessors'][p['indices']]['count']//3
    record = json.loads((SOURCE / 'source-manifest.json').read_text())
    assert triangles == record['geometry']['triangles']


def test_rest_guard_accepts_precision_noise_and_refuses_moved_or_turned_bones():
    # Exercise the exporter guard without importing Blender in the studio runner.
    import ast
    import math
    from types import SimpleNamespace
    import pytest
    tree = ast.parse((ASSETS / 'characters/pipeline/rig.py').read_text())   # the shared rig's guard
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'measure_rest')
    scope = {'np': np, 'math': math}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'rest_guard', 'exec'), scope)
    check = scope['measure_rest']
    before = {'spine': np.eye(4)}
    def measure(matrix):
        return check(before, [SimpleNamespace(name='spine', matrix_local=matrix)])
    noisy = np.eye(4)
    noisy[0, 0] += 6e-6
    noisy[0, 3] = 2e-7
    assert measure(noisy)['max_head_m'] == 2e-7
    moved = np.eye(4)
    moved[0, 3] = .001
    with pytest.raises(AssertionError):
        measure(moved)
    turned = np.eye(4)
    angle = math.radians(.1)
    turned[:2, :2] = [[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]]
    with pytest.raises(AssertionError):
        measure(turned)
    invalid = np.eye(4)
    invalid[0, 0] = 1.01
    with pytest.raises(AssertionError):
        measure(invalid)
