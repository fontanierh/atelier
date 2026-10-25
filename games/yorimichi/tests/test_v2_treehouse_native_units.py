"""Finite Treehouse piece declarations and exact selected-source proof, without native work."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import numpy as np
import pytest
from atelier import mesh_ir

ROOT = Path(__file__).resolve().parents[3]
WORLD = ROOT / 'games/yorimichi/world'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


units = load('games/yorimichi/v2_treehouse_native_units.py', 'treehouse_unit_test')
island = load('games/yorimichi/world/island_finish_v2.py', 'island_finish_source_test')
# Same named sibling resolution as the production entry's world directory.
sys.modules.setdefault('island_finish_v2', island)
finish = load('games/yorimichi/world/treehouse_finish_v2.py', 'treehouse_finish_test')


def template(parent):
    family = 'trees' if parent in units.TREES else 'props' if parent in units.PROPS else 'surfaces'
    return {'producer': f'world.treehouse_{family}.geometry.{parent}', 'group': 'geometry',
            'unit_prefix': f'world.treehouse_{family}.export.{parent}',
            'op': {'kind': 'blender_export_piece', 'version': '1'}, 'params': {'format': 'fbx'}}


def supplied(parents):
    geometry = {'templates': [template(parent) for parent in parents]}
    unresolved = units.attach_followers(geometry, {}, [], checkout=ROOT)
    packages, native = {}, []
    for i, package in enumerate(unresolved['missing_material_packages']):
        owner = 'material.' + str(i)
        packages[package] = {'unit': owner, 'item': 'asset', 'package': package}
        native.append({'id': owner, 'inputs': [], 'outputs': [
            {'id': 'asset', 'logical_path': package, 'class': 'MaterialInstance'}]})
    return geometry, packages, native


def test_complete_family_uses_actual_selected_export_raw_and_payload_no_sibling_identity():
    parents = (*units.TREES, *units.PROPS, *units.SURFACES)
    geometry, packages, native = supplied(parents)
    before = deepcopy(geometry)
    result = units.attach_followers(geometry, packages, native, checkout=ROOT)
    assert geometry == before
    assert result['missing_material_packages'] == result['unrepresented_parents'] == []
    assert len(result['geometry']['templates']) == 21
    for row in result['geometry']['templates']:
        raw, finished = [f['unit'] for f in row['followers']]
        assert raw['outputs'][0]['destination'] == 'store'
        assert finished['outputs'][0]['destination'] == 'checkout'
        assert finished['inputs'][0]['source'] == {'kind': 'item', 'unit': '$previous', 'item': 'raw'}
        assert finished['inputs'][2]['source'] == {'kind': 'group_member', 'unit': row['producer'],
                                                   'group': 'geometry', 'piece': '$piece'}
        assert all((ROOT / path).is_file() for path in finished['code'])
    dressing = result['geometry']['templates'][-1]['followers'][1]['unit']
    assert dressing['params']['destination'] == '/Game/Japan/Treehouse/Pieces/$piece'
    trunks = result['geometry']['templates'][-2]['followers'][1]['unit']
    slot = trunks['params']['args']['materials']['TH_bark']
    ref = next(r['source'] for r in trunks['inputs'] if r['name'] == slot)
    assert packages[units.MATERIALS + 'MI_TH_trunk']['unit'] == ref['unit']


def test_missing_palette_roles_explicit_without_fake_native_owners():
    result = units.attach_followers({'templates': [template('TH_Frame')]}, {}, [], checkout=ROOT)
    assert units.MATERIALS + 'MI_TH_pane' in result['missing_material_packages']
    assert 'followers' not in result['geometry']['templates'][0]
    assert result['units'] == [] and result['packages'] == {}


def test_wrong_native_item_owner_and_unknown_template_refuse():
    geometry, packages, native = supplied(['TH_P_barrel'])
    native[0]['outputs'][0]['logical_path'] = '/Game/Foreign'
    with pytest.raises(ValueError, match='actual native Item'):
        units.attach_followers(geometry, packages, native, checkout=ROOT)
    bad = template('TH_Frame'); bad['producer'] += '.foreign'
    with pytest.raises(ValueError):
        units.attach_followers({'templates': [bad]}, {}, [], checkout=ROOT)


def source_case(tmp_path, parent='TH_Frame'):
    payload, exported = tmp_path / 'payload', tmp_path / 'export'
    payload.mkdir(); exported.mkdir()
    uvs = ['UVMap', 'Piece1', 'Piece2', 'Piece3', 'Piece4'] if parent in ('TH_Frame', 'TH_Dressing') else ['UVMap']
    piece = {'positions': [[0, 0, 0], [1, 0, 0], [0, 1, 0]], 'normals': [[0, 0, 1]] * 3,
             'faces': [[0, 1, 2]], 'materials': [0], 'smooth': [False],
             'uvs': [(label, [[0, 0], [1, 0], [0, 1]]) for label in uvs], 'colours': []}
    data = mesh_ir.encode(piece, key=parent, slots=['TH_wood_plank'], matrix=np.eye(4).tolist(), options={})
    (payload / (parent + '.npz')).write_bytes(data)
    primary = parent + '.fbx'; (exported / primary).write_bytes(b'finished-source-fbx')
    receipt = {'schema': 1, 'asset': parent, 'primary': primary, 'triangles': 1,
               'bounds': [[0., 0., 0.], [1., 1., 0.]],
               'sha256': hashlib.sha256((exported / primary).read_bytes()).hexdigest(),
               'metadata': {'geometry_sha256': hashlib.sha256(data).hexdigest(), 'slots': ['TH_wood_plank'],
                            'polygons': 1, 'collision_hulls': 0, 'uv_channels': uvs}}
    (exported / 'export.json').write_text(json.dumps(receipt))
    context = NS(job_dir=str(tmp_path), inputs={'export': exported, 'payload': payload},
                 params={'args': {'source_export': 'export', 'payload': 'payload'}})
    return context, receipt, exported, payload


def test_real_decoder_binds_complete_five_uv_source_and_export(tmp_path):
    context, receipt, _, _ = source_case(tmp_path)
    checked, meta, _, facts = finish.source_facts(context, 'TH_Frame')
    assert checked == receipt and len(facts['uv_channels']) == 5 and meta['collisions'] == []


@pytest.mark.parametrize('damage', ['receipt', 'payload', 'foreign', 'link', 'parent'])
def test_selected_source_damage_refuses(tmp_path, damage):
    context, receipt, exported, payload = source_case(tmp_path)
    if damage == 'receipt':
        receipt['metadata']['collision_hulls'] = 3
        (exported / 'export.json').write_text(json.dumps(receipt))
    elif damage == 'payload':
        (payload / 'TH_Frame.npz').write_bytes(b'broken')
    elif damage == 'foreign':
        (payload / 'foreign').write_bytes(b'x')
    elif damage == 'link':
        (payload / 'TH_Frame.npz').rename(payload / 'other.npz')
        (payload / 'TH_Frame.npz').symlink_to(payload / 'other.npz')
    with pytest.raises((ValueError, OSError)):
        finish.source_facts(context, 'TH_Trunks' if damage == 'parent' else 'TH_Frame')
