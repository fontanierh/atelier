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
SOURCE = ASSETS / 'characters/garcon'


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
    assert library['characters/garcon/Garcon.glb'] == {'bytes': len(data), 'sha256': record['native_sha256']}
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
    doc, binary = glb_parts((SOURCE / 'Garcon.glb').read_bytes())
    contract = tomllib.loads((GAME.parents[1] / 'platform/conventions/rigs/humanoid.toml').read_text())
    joints = doc['skins'][0]['joints']
    names = {doc['nodes'][j]['name'] for j in joints}
    required = {n for group in contract['required'].values() for n in group}
    fingers = {n+s for n in contract['optional']['fingers']['per_hand'] for s in ('_L', '_R')}
    assert required | fingers <= names
    assert names - required - fingers == {'spine_02', 'spine_04', 'neck_02'}
    triangles = 0
    for mesh in doc['meshes']:
        for p in mesh['primitives']:
            attrs = p['attributes']
            weights = read(doc, binary, attrs['WEIGHTS_0'])
            indices = read(doc, binary, attrs['JOINTS_0'])
            assert np.isfinite(weights).all() and (weights >= 0).all()
            assert np.allclose(weights.sum(axis=1), 1, atol=1e-6)
            assert indices.max() < len(joints)
            triangles += doc['accessors'][p['indices']]['count']//3
    assert triangles == 32024
