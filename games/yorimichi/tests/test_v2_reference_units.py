"""Reference (unreal.adventure) as native units: actual rows, narrow GLB views and members, bodies on a fake editor."""
import base64
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import numpy as np
import pytest
from atelier.build_v2.file_groups import emit
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path[:0] = [str(GAME), str(GAME / 'tests')]
import v2_reference_units as units  # noqa: E402
from test_v2_moveset_units import recipe  # noqa: E402


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


members = load(units.BODY, 'reference_members_test')
body = load(units.SCRIPT, 'reference_body_test')
bake = load(units.BAKE, 'reference_bake_test')
NATIVES = {'compression': {'unit': 'unreal.animation.compression', 'item': 'asset', 'package': units.COMPRESSION}}


@pytest.fixture(scope='module')
def rows():
    steps = [s for s in recipe.adventure_steps(ROOT / 'build/yorimichi') if s.name in ('characters.adventure', 'unreal.adventure')]
    for step in steps:
        step.needs = [n for n in step.needs if n == 'characters.adventure']; step.after = []
    return extract(steps, checkout=ROOT, build_root=ROOT / 'build')


@pytest.fixture(scope='module')
def declared(rows):
    return units.reference_units(rows, checkout=ROOT, natives=NATIVES)


def test_declaration_from_the_actual_rows(declared):
    found = {u['id']: u for u in declared['units']}
    assert set(declared['groups']) == {f'characters.adventure.members.{k}' for k in ('clips', 'images', 'materials')}
    views = found['characters.adventure.views']
    assert views['inputs'][0]['source'] == {'kind': 'item', 'unit': 'characters.adventure', 'item': 'product0'}
    assert views['params']['recipe']['paths'] == {'build/yorimichi/adventure/export.json': 'inputs/export/products/0-0.tree.tar',
                                                  'build/yorimichi/adventure/glb': 'inputs/export/products/0-1.tree.tar'}
    assert views['params']['recipe']['commands'][0]['call']['defaults'][-1] == 'Float'
    raw = found['unreal.adventure.raw.Reference']
    assert raw['params']['source_member'] == 'Reference' and raw['params']['create_physics_asset'] is False
    assert 'fbx' not in raw['params'] and [o['logical_path'] for o in raw['outputs']] == [
        '/Game/_Raw/Adventure/Reference/SK_Reference', '/Game/_Raw/Adventure/Reference/SK_Reference_Skeleton']
    clip = found['unreal.adventure.clip.raw.ReferenceGlider']
    assert clip['params']['destination'].rsplit('/', 1)[1] == 'Float' and clip['params']['source_member'] == 'ReferenceGlider_Float'
    assert found['unreal.adventure.mesh.Reference']['params']['args']['materials'] == declared['tokens']['materials']
    assert found['unreal.adventure.record']['outputs'][0]['files'][0]['install_path'] == units.RECORD_FILE
    reference = declared['reference']
    assert reference['skeleton'] == {'unit': 'unreal.adventure.mesh.Reference', 'item': 'skeleton',
                                     'package': '/Game/Adventure/Reference/SKEL_Reference'}
    assert reference['glide']['piece'] == 'Float_Float' and reference['glide']['derived'] == declared['tokens']['clips']
    assert [e['package'] for e in reference['equipment']] == ['/Game/Adventure/Reference/Sword/SM_ReferenceSword',
                                                             '/Game/Adventure/Reference/Glider/SK_ReferenceGlider']


def test_templates_bind_narrow_members_and_actual_derived_items(declared):
    keys = {(t['producer'], t['group'], t['unit_prefix']): t for t in declared['templates']}
    for token in declared['tokens'].values():
        for source in token['derived_items']['templates']:
            follower = keys[(source['producer'], source['group'], source['unit_prefix'])]['followers'][source['follower']]['unit']
            assert source['item'] in {o['id'] for o in follower['outputs']}
    for template in declared['templates']:
        for follower in template['followers']:
            assert all(i['source']['unit'] != 'characters.adventure' for i in follower['unit']['inputs'])
    clip = keys[('characters.adventure.members.clips', 'members', 'unreal.adventure.clips')]
    raw, finish = (f['unit'] for f in clip['followers'])
    assert raw['params']['destination'] == '/Game/_Raw/Adventure/Reference/$piece'
    assert finish['outputs'][0]['logical_path'] == '/Game/Adventure/Reference/A_Reference_$piece'
    material = keys[('characters.adventure.members.materials', 'members', 'unreal.adventure.materials')]
    assert [f['path'] for f in material['files']] == ['meta.tree.tar']


@pytest.mark.parametrize('damage', ['product', 'compression', 'importer'])
def test_declaration_drift_refuses(rows, damage):
    rows, natives = deepcopy(rows), deepcopy(NATIVES)
    found = {r['id']: r for r in rows}
    if damage == 'product':
        found['characters.adventure']['products'][0]['paths'].pop()
    elif damage == 'compression':
        natives.pop('compression')
    else:
        found['unreal.adventure']['commands'][0]['script'] = {'path': 'other.py'}
    with pytest.raises(ValueError):
        units.reference_units(rows, checkout=ROOT, natives=natives)


# ---- projection -----------------------------------------------------------------------------------------------------

PNG = b'\x89PNG\r\n\x1a\nfake'


def rig(path, *, animations, materials, image=None, extra=0):
    gltf = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0, 2]}],
            'nodes': [{'name': 'Root', 'children': [1]}, {'name': 'Hip'}, {'name': 'Body', 'mesh': 0, 'skin': 0}]}
    binary = bytearray(); writer = bake.Writer(gltf, binary)
    position = writer.floats(np.zeros((3, 3)), 'VEC3', bounds=True)
    for _ in range(extra):
        writer.floats(np.ones((64, 4)), 'VEC4')   # unreferenced bytes a view must drop
    gltf['skins'] = [{'joints': [0, 1], 'inverseBindMatrices': writer.floats(np.tile(np.eye(4).reshape(1, 16), (2, 1)), 'MAT4')}]
    gltf['meshes'] = [{'primitives': [{'attributes': {'POSITION': position}, 'material': i} for i in range(len(materials))]}]
    gltf['materials'] = [dict(m) for m in materials]
    if image:
        binary += b'\x00' * (-len(binary) % 4)
        gltf['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(image)}); binary += image
        gltf['images'] = [{'name': 'Skin', 'mimeType': 'image/png', 'bufferView': len(gltf['bufferViews']) - 1}]
        gltf['textures'] = [{'source': 0}]
    gltf['animations'] = []
    for name in animations:
        times, values = writer.floats(np.array([0., 1.]), 'SCALAR'), writer.floats(np.zeros((2, 4)), 'VEC4')
        gltf['animations'].append({'name': name, 'samplers': [{'input': times, 'output': values}],
                                   'channels': [{'sampler': 0, 'target': {'node': 1, 'path': 'rotation'}}]})
    bake.write_glb(path, gltf, binary)


def export_tree(tmp_path, *, glider_clip='Float', extra_clip=None):
    out = tmp_path / 'adventure'; glb = out / 'glb'; glb.mkdir(parents=True)
    rig(glb / 'Reference.glb', animations=['Idle', 'Float_Float', *([extra_clip] if extra_clip else [])], image=PNG, extra=4,
        materials=[{'name': 'Skin', 'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}}},
                   {'name': 'Hair cut', 'alphaMode': 'MASK', 'alphaCutoff': .3, 'emissiveFactor': [.1, .2, .3]}])
    rig(glb / 'ReferenceSword.glb', animations=[], materials=[{'name': 'Blade'}])
    rig(glb / 'ReferenceGlider.glb', animations=['FloatSource'], materials=[{'name': 'Cloth'}])
    clips = [{'name': n, 'frames': 30, 'loop': True, 'travel': [0., 0., 0.]} for n in ('Idle', 'Float_Float')]
    config = {'fps': 30, 'characters': [{'name': 'Reference', 'skeleton': 'Reference', 'glb': 'glb/Reference.glb',
        'label': 'Motion reference', 'kind': 'motion', 'scale': 1., 'height': 1.7, 'speeds': {'walk': 1.2},
        'roles': {'idle': 'Idle'}, 'clips': clips, 'moves': {'actions': {'Glide': {'clip': 'Float_Float'}}, 'params': {},
        'equipment': {'sword': {'glb': 'glb/ReferenceSword.glb', 'hand': 'Weapon_R', 'back': 'Pod_A', 'carry': {'location': [1, 2, 3]}},
                      'glider': {'glb': 'glb/ReferenceGlider.glb', 'hand': 'Weapon_R', 'back': '', 'clip': glider_clip, 'frames': 30}}}}]}
    (out / 'export.json').write_text(json.dumps(config))
    return out


def test_compact_keeps_only_referenced_bytes(tmp_path):
    out = export_tree(tmp_path)
    gltf, binary = bake.read_glb(out / 'glb/Reference.glb')
    view, packed = members.compact(gltf, binary, animations=(1,))
    assert [a['name'] for a in view['animations']] == ['Float_Float'] and 'images' not in view
    assert len(view['accessors']) == 4 and len(packed) < len(binary)
    assert 'baseColorTexture' not in view['materials'][0]['pbrMetallicRoughness']
    sampler = view['animations'][0]['samplers'][0]
    times = view['accessors'][sampler['input']]
    start = view['bufferViews'][times['bufferView']]['byteOffset']
    assert np.frombuffer(bytes(packed[start:start + 8]), '<f4').tolist() == [0., 1.]


def test_projection_members_and_selection(tmp_path):
    out = export_tree(tmp_path)
    args = (out / 'export.json', out / 'glb', ROOT / units.BAKE)
    found = {}
    for kind in ('clips', 'images', 'materials'):
        output = tmp_path / 'members' / kind
        members.project(*args, output, kind)
        found[kind] = sorted(p['name'] for p in emit(output, tmp_path / 'files' / kind, parent='Reference_' + kind,
                                                    extensions=['.json'])['pieces'])
    assert found == {'clips': ['Float_Float', 'Idle'], 'images': ['Reference_Skin'],
                     'materials': ['ReferenceGlider_Cloth', 'ReferenceSword_Blade', 'Reference_Hair_cut', 'Reference_Skin']}
    hair = json.loads((tmp_path / 'members/materials/Reference_Hair_cut.json').read_text())
    assert hair == {'name': 'Reference_Hair_cut', 'owner': 'Reference', 'slot': 'Hair cut', 'masked': True, 'base': None,
                    'emissive': None, 'emissive_factor': [.1, .2, .3], 'alpha_cutoff': .3}
    skin = json.loads((tmp_path / 'members/materials/Reference_Skin.json').read_text())
    assert skin['base'] == 'Reference_Skin' and skin['masked'] is False
    selected = tmp_path / 'selected'; selected.mkdir()
    (selected / 'Idle.json').write_bytes((tmp_path / 'members/clips/Idle.json').read_bytes())
    members.select(selected, tmp_path / 'member', tmp_path / 'meta', 'Idle')
    view, _ = bake.read_glb(tmp_path / 'member/Idle.glb')
    assert [a['name'] for a in view['animations']] == ['Idle']
    assert json.loads((tmp_path / 'meta/meta.json').read_text()) == {'name': 'Idle', 'frames': 30, 'fps': 30, 'loop': True,
                                                                    'travel': [0., 0., 0.]}
    image = tmp_path / 'image'; image.mkdir()
    (image / 'Reference_Skin.json').write_bytes((tmp_path / 'members/images/Reference_Skin.json').read_bytes())
    members.select(image, tmp_path / 'image_member', tmp_path / 'image_meta', 'Reference_Skin')
    assert (tmp_path / 'image_member/Reference_Skin.png').read_bytes() == PNG


def test_views_are_the_fixed_owners_sources(tmp_path):
    out = export_tree(tmp_path)
    members.views(out / 'export.json', out / 'glb', ROOT / units.BAKE, tmp_path / 'views', 'Float')
    assert sorted(p.name for p in (tmp_path / 'views').iterdir()) == ['Reference', 'ReferenceGlider', 'ReferenceGlider_Float',
                                                                     'ReferenceSword']
    reference, _ = bake.read_glb(tmp_path / 'views/Reference/Reference.glb')
    assert 'animations' not in reference and 'images' not in reference and len(reference['materials']) == 2
    sword, _ = bake.read_glb(tmp_path / 'views/ReferenceSword/ReferenceSword.glb')
    assert 'skins' not in sword and all('skin' not in n for n in sword['nodes'])
    clip, _ = bake.read_glb(tmp_path / 'views/ReferenceGlider_Float/ReferenceGlider_Float.glb')
    assert [a['name'] for a in clip['animations']] == ['Float']
    receipt = json.loads((tmp_path / 'views/Reference/export.json').read_text())
    assert receipt['primary'] == 'Reference.glb'


@pytest.mark.parametrize('damage', ['glider', 'extra_clip', 'two_rigs'])
def test_projection_refuses_an_export_that_differs(tmp_path, damage):
    out = export_tree(tmp_path, glider_clip='Other' if damage == 'glider' else 'Float',
                      extra_clip='Unlisted' if damage == 'extra_clip' else None)
    if damage == 'two_rigs':
        config = json.loads((out / 'export.json').read_text()); config['characters'].append(dict(config['characters'][0]))
        (out / 'export.json').write_text(json.dumps(config))
    with pytest.raises(ValueError):
        members.views(out / 'export.json', out / 'glb', ROOT / units.BAKE, tmp_path / 'views', 'Float')


# ---- bodies ---------------------------------------------------------------------------------------------------------

class Asset:
    def __init__(self, path, **props): self.path, self.props = path, dict(props)
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[1]
    def get_name(self): return self.path.rsplit('/', 1)[1]
    def get_editor_property(self, key): return self.props[key]
    def set_editor_property(self, key, value): self.props[key] = value
class Material(Asset): pass
class Instance(Asset): pass
class Sequence(Asset): pass
class Skeleton(Asset): pass
class Mesh(Asset):
    @property
    def materials(self): return self.props['materials']
    def get_bounds(self): return NS(box_extent=NS(x=40., y=20.))


@pytest.fixture
def editor(tmp_path, monkeypatch):
    assets, state = {}, NS(saves=[], params={})
    def create(name, folder, cls, factory):
        assets[folder + '/' + name] = cls(folder + '/' + name); return assets[folder + '/' + name]
    def duplicate(source, target):
        assets[target] = type(assets[source])(target, **assets[source].props); return assets[target]
    graph = NS(set_material_instance_parent=lambda mi, p: mi.set_editor_property('parent', p),
               set_material_instance_texture_parameter_value=lambda mi, k, v: state.params.setdefault(mi.path, {}).update({k: v}),
               set_material_instance_vector_parameter_value=lambda mi, k, v: state.params.setdefault(mi.path, {}).update({k: v}),
               set_material_instance_scalar_parameter_value=lambda mi, k, v: state.params.setdefault(mi.path, {}).update({k: v}),
               update_material_instance=lambda mi: None)
    unreal = NS(Material=Material, MaterialInstanceConstant=Instance, MaterialInstanceConstantFactoryNew=lambda: None,
                AnimSequence=Sequence, Skeleton=Skeleton, SkeletalMesh=Mesh, StaticMesh=Mesh, LinearColor=lambda *v: v,
                MaterialEditingLibrary=graph, AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=create)),
                EditorAssetLibrary=NS(load_asset=lambda p: assets.get(p.split('.', 1)[0]), does_asset_exist=lambda p: p in assets,
                                      duplicate_asset=duplicate, save_loaded_asset=lambda a, d=True: state.saves.append(a.path) or True))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    target = tmp_path / units.COMPRESSION_SCRIPT; target.parent.mkdir(parents=True)
    target.write_text('def apply_to(sequence): sequence.set_editor_property("bone_compression_settings", _settings)\n')
    return NS(assets=assets, state=state, root=tmp_path)


def meta(tmp_path, name, value):
    folder = tmp_path / ('meta_' + name); folder.mkdir(); (folder / 'meta.json').write_text(json.dumps(value)); return str(folder)


def derived(**slots):
    return {'derived_items': {'root': 'r', 'members': [{'piece': k, 'slot': v, 'root': 'r/' + k} for k, v in slots.items()]}}


def test_instance_is_the_restyled_material(editor):
    masters = {m: Material(f'/Game/Adventure/{n}') for m, n in units.MASTERS.items()}
    texture = Asset('/Game/Adventure/Reference/Textures/T_Reference_Skin')
    for asset in (*masters.values(), texture):
        editor.assets[asset.path] = asset
    value = {'name': 'Reference_Hair', 'owner': 'Reference', 'slot': 'Hair', 'masked': True, 'base': 'Reference_Skin',
             'emissive': None, 'emissive_factor': [.1, .2, .3], 'alpha_cutoff': 0}
    context = NS(job_dir=str(editor.root), outputs=[f'{units.MATERIALS}/MI_Reference_Hair'],
                 inputs={'meta': meta(editor.root, 'hair', value), 'master_true': 'x', 'master_false': 'x', 'derived_0': 'x'},
                 packages={'meta': [], 'master_true': [masters[True].path], 'master_false': [masters[False].path],
                           'derived_0': [texture.path]},
                 params={'args': {'action': 'instance', 'name': 'Reference_Hair', 'meta': 'meta', 'folder': units.MATERIALS,
                                  'masters': {'false': 'master_false', 'true': 'master_true'},
                                  'images': derived(Reference_Skin='derived_0')}, 'settings': []})
    mi = body.run(context)
    assert mi.props['parent'] is masters[True]
    assert editor.state.params[mi.path] == {'BaseColorTexture': texture, 'EmissiveFactor': (.1, .2, .3, 1.), 'AlphaCutoff': .5}


def test_skeletal_finish_binds_slots_and_clips_check_their_member(editor):
    mi = Instance(f'{units.MATERIALS}/MI_Reference_Hair_cut')
    raw_skeleton = Skeleton('/Game/_Raw/Adventure/Reference/SK_Reference_Skeleton')
    slot = Asset('slot', imported_material_slot_name='Hair cut', material_interface=None)
    raw = Mesh('/Game/_Raw/Adventure/Reference/SK_Reference', skeleton=raw_skeleton, materials=[slot])
    for asset in (mi, raw_skeleton, raw):
        editor.assets[asset.path] = asset
    context = NS(job_dir=str(editor.root), outputs=['/Game/Adventure/Reference/SK_Reference', '/Game/Adventure/Reference/SKEL_Reference'],
                 inputs={'raw': 'x', 'derived_0': 'x'}, packages={'raw': [raw.path], 'derived_0': [mi.path]},
                 params={'op': 'finish', 'kind': 'skeletal_mesh', 'source': 'raw', 'destination': '/Game/Adventure/Reference/SK_Reference',
                         'partners': {'skeleton': '/Game/Adventure/Reference/SKEL_Reference'},
                         'args': {'action': 'mesh', 'owner': 'Reference', 'material_folder': units.MATERIALS,
                                  'materials': derived(Reference_Hair_cut='derived_0')}})
    mesh = body.run(context)
    assert mesh.materials[0].props['material_interface'] is mi and mesh.props['skeleton'].path.endswith('SKEL_Reference')
    settings = Asset(units.COMPRESSION)
    skeleton = editor.assets['/Game/Adventure/Reference/SKEL_Reference']
    raw_clip = Sequence('/Game/_Raw/Adventure/Reference/Idle', skeleton=skeleton, sequence_length=1.)
    editor.assets.update({settings.path: settings, raw_clip.path: raw_clip})
    def clip_context(frames):
        return NS(job_dir=str(editor.root), outputs=['/Game/Adventure/Reference/A_Reference_Idle'],
                  inputs={'raw': 'x', 'skeleton': 'x', 'compression': 'x',
                          'meta': meta(editor.root, f'idle{frames}', {'name': 'Idle', 'frames': frames, 'fps': 30})},
                  packages={'raw': [raw_clip.path], 'skeleton': [skeleton.path], 'compression': [settings.path], 'meta': []},
                  params={'op': 'finish', 'kind': 'animation', 'source': 'raw', 'destination': '/Game/Adventure/Reference/A_Reference_Idle',
                          'args': {'action': 'clip', 'meta': 'meta', 'skeleton': 'skeleton', 'compression': 'compression'}})
    with pytest.raises(ValueError, match='length'):
        body.run(clip_context(31))
    del editor.assets['/Game/Adventure/Reference/A_Reference_Idle']
    sequence = body.run(clip_context(30))
    assert sequence.props['enable_root_motion'] is False and sequence.props['bone_compression_settings'] is settings
