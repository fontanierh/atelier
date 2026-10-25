"""Selected CraterPark transport assembly preserves mesh and runtime identities."""
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import numpy as np
import pytest
from atelier import mesh_ir
from atelier.build_v2.recipe_job import pack_root
from atelier.export_manifest import publish_receipt

GAME = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(GAME / 'world'), str(GAME / 'world/regions')]
import craterpark_assembly_v2 as body  # noqa: E402


def selected_case(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_CRATERPARK_EDITOR_PARK', 'off')
    monkeypatch.delenv('ATELIER_CRATERPARK_V4_DESIGN', raising=False)
    source = tmp_path / 'source'; source.mkdir()
    np.savez(source / 'metadata.npz', index=np.asarray(json.dumps({'rails': []})))
    selected = {kind: [] for kind in ('render', 'collision', 'seed')}
    assets = []
    for kind, name in [('render', 'SM_CP_Test'), ('collision', 'UC_CP_Test'), ('seed', 'SM_CP_ImportSeed')]:
        packet = mesh_ir.encode(dict(positions=[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]],
            faces=[[0, 1, 2]], normals=[[0., 0., 1.]] * 3, materials=[0], smooth=[False],
            uvs=[], colours=[]), key=name, slots=['test_material'], matrix=np.eye(4).tolist(), options={})
        digest = hashlib.sha256(packet).hexdigest()
        folder = tmp_path / name; folder.mkdir()
        for role in ('export', 'payload', 'metadata'): (folder / role).mkdir()
        (folder / 'export' / (name + '.fbx')).write_bytes(b'owned test export ' + name.encode())
        publish_receipt(folder / 'export', key=name, primary=name + '.fbx', triangles=1,
                        bounds=[[0, 0, 0], [1, 1, 0]], metadata={'geometry_sha256': digest})
        (folder / 'payload' / (name + '.npz')).write_bytes(packet)
        (folder / 'metadata/plan.json').write_text(json.dumps({'pieces': [{'name': name,
            'sha256': digest, 'triangles': 1, 'source_faces': [0]}]}))
        (folder / 'metadata' / (name + '.json')).write_text(json.dumps({'schema': 1,
            'entry': {'name': name, 'native_origin': [10., 20., 30.]}}))
        for role in ('export', 'payload', 'metadata'): pack_root(folder / role, folder / (role + '.tree.tar'))
        selected[kind].append((NS(products=[NS(paths=[folder])]), name))
        assets.append({'name': name, 'kind': kind})
    (source / 'inputs.json').write_text(json.dumps({'schema': 1, 'complete': True, 'assets': assets}))
    return source, selected


def test_selected_transport_produces_original_runtime_and_complete_library(tmp_path, monkeypatch):
    source, selected = selected_case(tmp_path, monkeypatch)
    destination = tmp_path / 'out'
    body.assemble(source, selected, destination)
    build = json.loads((destination / 'build.json').read_bytes())
    park = json.loads((destination / 'park.json').read_bytes())
    assert [row['name'] for row in build['render']] == ['SM_CP_Test']
    assert [row['name'] for row in build['collision']] == ['UC_CP_Test']
    assert build['render'][0]['source_faces'] == [0]
    assert build['render'][0]['bounds'] == {'minimum': [10., 20., 29.], 'maximum': [11., 20., 30.]}
    assert park['render'] == [{'name': 'SM_CP_Test', 'origin_cm': [1000., 3000., 2000.]}]
    manifest = json.loads((destination / 'fbx/manifest.json').read_bytes())
    assert {row['asset'] for row in manifest['exports']} == {'SM_CP_Test', 'UC_CP_Test', 'SM_CP_ImportSeed'}
    assert (destination / 'fbx/SM_CP_Test.fbx').read_bytes() == b'owned test export SM_CP_Test'


@pytest.mark.parametrize('damage', ['missing', 'duplicate', 'payload'])
def test_selected_library_refuses_incomplete_or_changed_export_inputs(tmp_path, monkeypatch, damage):
    source, selected = selected_case(tmp_path, monkeypatch)
    if damage == 'missing': selected['seed'] = []
    if damage == 'duplicate': selected['render'] *= 2
    if damage == 'payload':
        folder = selected['render'][0][0].products[0].paths[0]
        (folder / 'payload/SM_CP_Test.npz').write_bytes(b'changed')
        pack_root(folder / 'payload', tmp_path / 'replacement.tar')
        (tmp_path / 'replacement.tar').replace(folder / 'payload.tree.tar')
    with pytest.raises(ValueError): body.assemble(source, selected, tmp_path / 'out')
