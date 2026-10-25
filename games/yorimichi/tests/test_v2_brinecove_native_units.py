"""Brinecove per-piece declarations and actual selected encoded source binding."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from atelier import encoded_glb
from test_encoded_region_plan import model

ROOT = Path(__file__).resolve().parents[3]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


units = load('games/yorimichi/v2_brinecove_native_units.py', 'brinecove_native_units_test')
sys.modules.setdefault('island_finish_v2', load('games/yorimichi/world/island_finish_v2.py', 'brinecove_island_helpers'))
body = load('games/yorimichi/world/brinecove_finish_v2.py', 'brinecove_finish_test')


def geometry():
    return {'templates': [{'producer': 'world.brinecove.geometry.SM_BC', 'group': 'geometry',
        'unit_prefix': 'world.brinecove.export.SM_BC', 'op': {'kind': 'encoded_export_piece', 'version': '1'}, 'params': {}}]}


def test_missing_palette_explicit_no_generic_material_or_fake_owner():
    result = units.attach_followers(geometry(), {}, [], checkout=ROOT)
    assert '/Game/Brinecove/Materials/MI_BC_terrain' in result['missing_material_packages']
    assert result['units'] == [] and result['packages'] == {}
    assert 'followers' not in result['geometry']['templates'][0]


def test_raw_glb_has_no_fbx_properties_and_finish_binds_actual_items():
    packages, native = {}, []
    for index, path in enumerate(units.material_packages(ROOT)):
        owner = 'material.' + str(index)
        packages[path] = {'unit': owner, 'item': 'asset', 'package': path}
        native.append({'id': owner, 'inputs': [], 'outputs': [{'id': 'asset', 'class': 'MaterialInstance', 'logical_path': path}]})
    original = geometry(); before = deepcopy(original)
    result = units.attach_followers(original, packages, native, checkout=ROOT)
    assert original == before and result['missing_material_packages'] == []
    raw, finish = [f['unit'] for f in result['geometry']['templates'][0]['followers']]
    assert raw['params'] == {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': '/Game/_Raw/Brinecove/$piece'}
    assert raw['outputs'][0]['destination'] == 'store'
    assert finish['outputs'][0]['destination'] == 'checkout'
    assert finish['params']['destination'] == '/Game/Brinecove/Meshes/$piece'
    assert finish['inputs'][2]['source'] == {'kind': 'group_member', 'unit': 'world.brinecove.geometry.SM_BC', 'group': 'geometry', 'piece': '$piece'}
    assert all((ROOT / path).is_file() for path in finish['code'])


def case(tmp_path, metadata):
    payload = tmp_path / 'payload'; payload.mkdir()
    packet = encoded_glb.encode(model(), key='SM_BC_Test', metadata=metadata)
    source = payload / 'SM_BC_Test.mesh'; source.write_bytes(packet)
    exported = tmp_path / 'export'
    stage = load('games/yorimichi/world/stage_encoded_export_v2.py', 'brinecove_actual_export_test')
    context = NS(inputs={'payload': payload}, params={'payload_member': source.name,
        'payload_encoding': 'encoded_glb', 'payload_role': 'render'}, outputs=['SM_BC_Test.glb', 'export.json'])
    context.input = lambda slot: payload
    def output(name):
        exported.mkdir(exist_ok=True); return exported / name
    context.output = output
    stage.run(context)
    finish = NS(job_dir=str(tmp_path), inputs={'source': exported, 'payload': payload},
                params={'args': {'source_export': 'source', 'payload': 'payload', 'materials': {}}})
    return finish, source, exported


def test_actual_encoded_export_decodes_selected_policy_and_geometry(tmp_path):
    context, _, _ = case(tmp_path, {'collision': True, 'lods': False})
    facts = body.source_facts(context)
    assert facts['collision'] is True and facts['lods'] is False and facts['asset'] == 'SM_BC_Test'
    assert facts['triangles'] > 0 and len(facts['bounds']) == 2


@pytest.mark.parametrize('damage', ['policy', 'payload', 'receipt', 'foreign'])
def test_missing_policy_or_changed_selected_source_refuses(tmp_path, damage):
    context, source, exported = case(tmp_path, {} if damage == 'policy' else {'collision': False, 'lods': True})
    if damage == 'payload': source.write_bytes(b'broken')
    elif damage == 'receipt':
        value = json.loads((exported / 'export.json').read_text()); value['metadata']['collision'] = True
        (exported / 'export.json').write_text(json.dumps(value))
    elif damage == 'foreign': (source.parent / 'other').write_bytes(b'x')
    with pytest.raises(ValueError): body.source_facts(context)
