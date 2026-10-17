#!/usr/bin/env python3
"""Verify Kiyo's committed source and GLB without opening Blender."""
import hashlib
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = {'root', 'pelvis', 'spine', 'spine_mid', 'chest', 'neck', 'head',
        'clavicle_L', 'upperarm_L', 'forearm_L', 'hand_L',
        'clavicle_R', 'upperarm_R', 'forearm_R', 'hand_R',
        'thigh_L', 'shin_L', 'foot_L', 'toe_L', 'thigh_R', 'shin_R', 'foot_R', 'toe_R'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def glb_json(path):
    raw = Path(path).read_bytes()
    magic, version, length = struct.unpack_from('<4sII', raw)
    assert magic == b'glTF' and version == 2 and length == len(raw), 'not a complete glTF 2 binary'
    chunk_length, chunk_type = struct.unpack_from('<II', raw, 12)
    assert chunk_type == 0x4E4F534A, 'first GLB chunk is not JSON'
    return json.loads(raw[20:20 + chunk_length].decode('utf-8'))


def main():
    manifest = json.loads((HERE / 'source-manifest.json').read_text())
    blend, glb = HERE / manifest['native'], HERE / manifest['render_glb']
    assert sha(blend) == manifest['native_sha256'], 'native Blender source hash differs'
    assert sha(glb) == manifest['render_glb_sha256'], 'GLB hash differs'
    doc = glb_json(glb)
    meshes = doc.get('meshes', [])
    assert len(meshes) == 1, f'expected one mesh, found {len(meshes)}'
    primitive = meshes[0]['primitives'][0]
    attributes = primitive['attributes']
    for required in ('POSITION', 'NORMAL', 'COLOR_0', 'JOINTS_0', 'WEIGHTS_0'):
        assert required in attributes, f'GLB primitive has no {required}'
    skins = doc.get('skins', [])
    assert len(skins) == 1, f'expected one skin, found {len(skins)}'
    nodes = doc.get('nodes', [])
    names = {nodes[index].get('name') for index in skins[0]['joints']}
    assert CORE <= names, 'GLB skin is missing core humanoid joints: ' + ', '.join(sorted(CORE - names))
    assert not doc.get('animations'), 'Kiyo r01 is a static NPC model; unexpected clips'
    for reference in manifest['references']:
        path = HERE / reference
        assert path.exists(), f'missing reference {reference}'
        assert sha(path) == manifest['reference_sha256'][reference], f'reference hash differs: {reference}'
    report = {
        'source': blend.name,
        'source_bytes': blend.stat().st_size,
        'glb': glb.name,
        'glb_bytes': glb.stat().st_size,
        'core_joints': len(CORE),
        'skin_joints': len(names),
        'extra_joints': sorted(names - CORE),
        'attributes': sorted(attributes),
        'material': manifest['material'],
        'triangles': manifest['geometry']['triangles'],
        'height_cm': manifest['height_cm'],
        'references': list(manifest['reference_sha256']),
    }
    print(json.dumps(report, indent=2), flush=True)
    print('KIYO VERIFIED', flush=True)


if __name__ == '__main__':
    main()
