"""unreal.horses as native units: the actual rows, member projection over synthetic GLBs, bodies on a fake editor."""
from copy import deepcopy
import base64
import importlib.util
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2.file_groups import emit
from atelier.build_v2.recipe_dependencies import extract
from atelier.gltf import glb_pack, glb_parts

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path.insert(0, str(GAME))
import v2_horse_units as units  # noqa: E402
from v2_texture_units import Unsupported  # noqa: E402


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


members = load(units.BODY, 'horse_members_test')
body = load(units.SCRIPT, 'horse_body_test')
LIBRARY = json.loads((ROOT / units.LIBRARY).read_text())
COMPRESSION = {'unit': 'unreal.animation.compression', 'item': 'asset', 'package': units.COMPRESSION}


@pytest.fixture(scope='module')
def rows():
    spec = importlib.util.spec_from_file_location('horse_recipe', GAME / 'build.py')
    recipe = importlib.util.module_from_spec(spec); sys.modules['horse_recipe'] = recipe; spec.loader.exec_module(recipe)
    context = NS(uproject=GAME / 'unreal/Yorimichi.uproject', out=ROOT / 'build/yorimichi')
    steps = [s for s in recipe.steps(context) if s.name in ('world.horses', 'unreal.horses')]
    for step in steps:
        step.needs = [n for n in step.needs if n == 'world.horses']; step.after = []; step.reads = []
    return extract(steps, checkout=ROOT, build_root=ROOT / 'build')


@pytest.fixture(scope='module')
def declared(rows):
    return units.horse_units(rows, checkout=ROOT, natives={'compression': COMPRESSION})


def test_every_package_from_the_actual_rows(declared):
    found = {u['id']: u for u in declared['units']}
    breeds, tack = list(LIBRARY['breeds']), len(LIBRARY['tack_sets']) * 2
    variants = json.loads((ROOT / units.VARIANTS).read_text())['variants']
    assert len(breeds) == 6 and tack == 14 and len(variants) == 16
    assert len([u for u in found if '.tack.' in u and '.raw.' not in u]) == 6 * tack
    assert len(declared['templates']) == 18 and len(declared['groups']) == 18
    assert sorted(u for u in found if u.startswith('unreal.horses.master.')) == sorted(
        'unreal.horses.master.' + n for n in units.MASTERS.values())
    coat = found['unreal.horses.master.M_HorseCoat']
    assert coat['inputs'] == [{'role': 'content', 'name': 'mask', 'source': {'kind': 'item', 'unit': 'unreal.horses.mask.Solid', 'item': 'texture'}}]
    body_source = found['horses.arabian.members.clips']['inputs'][0]
    assert body_source['source'] == {'kind': 'item', 'unit': 'world.horses', 'item': 'output1'} and 'whole' in body_source
    assert found['horses.arabian.members.clips']['params']['recipe']['outputs'][0]['kind'] == 'tree'
    reins = found['unreal.horses.quarter.tack.raw.Reins_06']
    assert reins['params']['skeleton'] == 'skeleton' and {i['name']: i['source']['unit'] for i in reins['inputs']} == {
        'source': 'horses.quarter.views', 'skeleton': 'unreal.horses.quarter.mesh'}
    assert '/Game/Horses/Quarter/Tack/Reins_06/SK_Horse_Quarter_Reins_06' in declared['packages']
    assert 'unreal.horses.record' not in found
    roster, report = found['unreal.horses.roster'], found['unreal.horses.report']
    assert [(o['id'], o['class'], o['destination']) for o in roster['outputs']] == [('roster', 'JsonData', 'checkout')]
    assert [(o['id'], o['class'], o['destination']) for o in report['outputs']] == [('report', 'JsonData', 'store')]
    assert roster['outputs'][0]['files'] == [{'path': 'data/roster.json', 'install_path': units.ROSTER_FILE, 'required': True}]
    assert report['outputs'][0]['files'] == [{'path': 'data/unreal_import.json', 'required': True}]
    same = lambda unit: {**unit['params'], 'args': {**unit['params']['args'], 'action': None}}
    assert roster['inputs'] == report['inputs'] and same(roster) == same(report)
    assert list(roster['params']['input_roots']) == ['built'] and roster['params']['input_roots']['built']['name'] == 'manifest.json'
    assert sorted(roster['params']['args']['breeds']) == sorted(breeds)
    assert len(roster['params']['args']['coat_variants']) == 16
    assert declared['packages'][units.ROSTER_FILE] == {'unit': 'unreal.horses.roster', 'item': 'roster'}
    assert declared['packages'][units.REPORT_FILE] == {'unit': 'unreal.horses.report', 'item': 'report'}
    clips = {t['unit_prefix']: t for t in declared['templates']}['unreal.horses.friesian.clips']
    raw, finish = (f['unit'] for f in clips['followers'])
    assert raw['params']['destination'].endswith('/$piece') and finish['params']['destination'] == '/Game/Horses/Friesian/A_Horse_Friesian_$piece'
    for template in declared['templates']:
        assert all(o['kind'] == 'tree' for o in template['params']['recipe']['outputs'])
        for follower in template['followers']:
            assert all(i['source']['unit'] != 'world.horses' for i in follower['unit']['inputs'])
    assert declared['aliases']['unreal.horses'] == tuple(found)


@pytest.mark.parametrize('damage', ['importer', 'producer', 'compression'])
def test_declaration_drift_refuses(rows, damage):
    rows, natives = deepcopy(rows), {'compression': dict(COMPRESSION)}
    found = {r['id']: r for r in rows}
    if damage == 'importer':
        found['unreal.horses']['outputs'] = found['unreal.horses']['outputs'][:1]
    elif damage == 'producer':
        found['world.horses']['outputs'] = found['world.horses']['outputs'][:-1]
    else:
        natives['compression']['package'] = '/Game/Other'
    with pytest.raises(Unsupported):
        units.horse_units(rows, checkout=ROOT, natives=natives)


# ---- projection -----------------------------------------------------------------------------------------------------

PNG = b'\x89PNG\r\n\x1a\n' + b'x' * 8


def glb(*, animations=(), materials=(('Coat', 'OPAQUE'),), base=True):
    """A minimal skinned GLB: one triangle, one joint, an embedded image per material, the given animations."""
    binary = bytearray(struct.pack('<9f', 0, 0, 0, 1, 0, 0, 0, 1, 0))
    binary += struct.pack('<16f', *(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1))
    binary += struct.pack('<2f', 0, 1) + struct.pack('<8f', 0, 0, 0, 1, 0, 0, 0, 1)
    views = [{'buffer': 0, 'byteOffset': 0, 'byteLength': 36}, {'buffer': 0, 'byteOffset': 36, 'byteLength': 64},
             {'buffer': 0, 'byteOffset': 100, 'byteLength': 8}, {'buffer': 0, 'byteOffset': 108, 'byteLength': 32}]
    accessors = [{'bufferView': 0, 'componentType': 5126, 'count': 3, 'type': 'VEC3', 'min': [0, 0, 0], 'max': [1, 1, 0]},
                 {'bufferView': 1, 'componentType': 5126, 'count': 1, 'type': 'MAT4'},
                 {'bufferView': 2, 'componentType': 5126, 'count': 2, 'type': 'SCALAR'},
                 {'bufferView': 3, 'componentType': 5126, 'count': 2, 'type': 'VEC4'}]
    images, textures, mats = [], [], []
    for index, (name, mode) in enumerate(materials):
        views.append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(PNG)}); binary += PNG
        images.append({'name': f'{name}_Alb.png', 'mimeType': 'image/png', 'bufferView': len(views) - 1})
        textures.append({'source': index})
        pbr = {'baseColorTexture': {'index': index}} if base else {}
        mats.append({'name': name, 'alphaMode': mode, 'pbrMetallicRoughness': pbr})
    doc = {'asset': {'version': '2.0'}, 'scenes': [{'nodes': [0, 1]}], 'scene': 0,
           'nodes': [{'name': 'Bone'}, {'name': 'Body', 'mesh': 0, 'skin': 0}],
           'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'material': i} for i in range(len(mats))]}],
           'skins': [{'joints': [0], 'inverseBindMatrices': 1}], 'materials': mats, 'images': images, 'textures': textures,
           'accessors': accessors, 'bufferViews': views, 'buffers': [{'byteLength': len(binary)}]}
    if animations:
        doc['animations'] = [{'name': name, 'samplers': [{'input': 2, 'output': 3}],
                              'channels': [{'sampler': 0, 'target': {'node': 0, 'path': 'rotation'}}]} for name in animations]
    return glb_pack(doc, bytes(binary))


@pytest.fixture
def breed(tmp_path):
    library = {**LIBRARY, 'tack_sets': ['00'], 'clips': {'Idle': {'loop': True}, 'Walk': {'loop': True}}}
    (tmp_path / 'manifest.json').write_text(json.dumps(library))
    (tmp_path / 'arabian/tack').mkdir(parents=True)
    (tmp_path / 'arabian/tack/Saddle_00.glb').write_bytes(glb(materials=[('Saddle_00_Mt_Cloth', 'MASK')]))
    (tmp_path / 'arabian/tack/Reins_00.glb').write_bytes(glb(materials=[('Reins_00_Mt_Reins', 'OPAQUE')]))
    clips = ['Idle', 'horse_Walk', 'TurnLeft', 'TurnRight', 'Jump']
    (tmp_path / 'arabian.glb').write_bytes(glb(animations=clips, materials=[('Coat', 'OPAQUE'), ('Mane', 'OPAQUE')]))
    return NS(root=tmp_path, args=(tmp_path / 'manifest.json', 'arabian', tmp_path / 'arabian.glb', tmp_path / 'arabian',
                                   ROOT / units.HORSE_DATA))


def test_projection_members_are_each_owner_narrow_view(breed, tmp_path):
    value = members.members(*breed.args)[0]
    assert sorted(value['clips']) == ['Idle', 'Jump', 'TurnLeft', 'TurnRight', 'Walk']
    walk = glb_parts(value['clips']['Walk']['glb'])[0]
    assert [a['name'] for a in walk['animations']] == ['Walk'] and 'images' not in walk
    assert value['clips']['Jump']['loop'] is False
    assert value['materials']['SK_Horse_Arabian_Mane'] == {
        'name': 'SK_Horse_Arabian_Mane', 'owner': 'SK_Horse_Arabian', 'slot': 'Mane', 'role': 'hair', 'masked': False,
        'base': 'SK_Horse_Arabian_Mane_Alb', 'alpha_cutoff': .5}
    assert value['materials']['Saddle_00_Saddle_00_Mt_Cloth']['masked'] is True
    assert value['images']['Reins_00_Reins_00_Mt_Reins_Alb']['image'] == PNG
    members.project(*breed.args, tmp_path / 'out', 'materials')
    manifest = emit(tmp_path / 'out', tmp_path / 'files', parent='Horse_Arabian_materials', extensions=['.json'])
    assert len(manifest['pieces']) == 4
    selected = tmp_path / 'selected'; selected.mkdir()
    (selected / 'SK_Horse_Arabian_Coat.json').write_bytes((tmp_path / 'out/SK_Horse_Arabian_Coat.json').read_bytes())
    members.select(selected, tmp_path / 'member', tmp_path / 'meta', 'SK_Horse_Arabian_Coat')
    assert json.loads((tmp_path / 'meta/meta.json').read_text())['role'] == 'coat'
    members.views(*breed.args, tmp_path / 'views')
    assert sorted(p.name for p in (tmp_path / 'views').iterdir()) == ['Reins_00', 'SK_Horse_Arabian', 'Saddle_00']
    assert 'animations' not in glb_parts((tmp_path / 'views/SK_Horse_Arabian/SK_Horse_Arabian.glb').read_bytes())[0]


@pytest.mark.parametrize('damage', ['missing', 'extra', 'base'])
def test_projection_refuses_sources_that_differ(breed, damage):
    clips = {'missing': ['Idle', 'Walk', 'TurnLeft', 'TurnRight'],
             'extra': ['Idle', 'Walk', 'TurnLeft', 'TurnRight', 'Jump', 'Rear']}.get(damage)
    if clips:
        breed.args[2].write_bytes(glb(animations=clips))
    else:
        (breed.root / 'arabian/tack/Reins_00.glb').write_bytes(glb(base=False))
    with pytest.raises(ValueError):
        members.members(*breed.args)


# ---- bodies ---------------------------------------------------------------------------------------------------------

class Asset:
    def __init__(self, path, **props): self.path, self.props = path, dict(props)
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[1]
    def get_editor_property(self, key): return self.props[key]
    def set_editor_property(self, key, value): self.props[key] = value
class Material(Asset): pass
class Texture2D(Asset): pass
class Skeleton(Asset): pass
class MaterialInstanceConstant(Asset): pass
class SkeletalMesh(Asset):
    @property
    def materials(self): return self.props.get('materials', [])
class AnimSequence(Asset): pass


@pytest.fixture
def editor(tmp_path, monkeypatch):
    assets, saves, calls = {}, [], []
    def create(name, folder, cls, factory):
        assets[f'{folder}/{name}'] = cls(f'{folder}/{name}'); return assets[f'{folder}/{name}']
    def duplicate(source, target):
        assets[target] = type(assets[source])(target, **assets[source].props); return assets[target]
    M = NS(set_material_instance_parent=lambda mi, p: mi.props.update(parent=p),
           set_material_instance_vector_parameter_value=lambda mi, k, v: mi.props.update({k: v}),
           set_material_instance_scalar_parameter_value=lambda mi, k, v: mi.props.update({k: v}),
           set_material_instance_texture_parameter_value=lambda mi, k, v: mi.props.update({k: v}),
           get_material_instance_texture_parameter_value=lambda mi, k: mi.props[k],
           update_material_instance=lambda mi: None)
    unreal = NS(Material=Material, Texture2D=Texture2D, Skeleton=Skeleton, SkeletalMesh=SkeletalMesh,
                AnimSequence=AnimSequence, MaterialInstanceConstant=MaterialInstanceConstant,
                MaterialInstanceConstantFactoryNew=lambda: None, LinearColor=lambda *c: tuple(c), MaterialEditingLibrary=M,
                AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=create)),
                EditorAssetLibrary=NS(load_asset=lambda p: assets.get(p.split('.', 1)[0]), does_asset_exist=lambda p: p in assets,
                                      duplicate_asset=duplicate, save_loaded_asset=lambda a, d=True: saves.append(a.path) or True))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    for key, name in units.MASTERS.items():
        assets[f'/Game/Horses/{name}'] = Material(f'/Game/Horses/{name}')
    return NS(assets=assets, saves=saves, calls=calls, root=tmp_path)


def stage(editor, name, value, file):
    path = editor.root / name; path.mkdir(exist_ok=True)
    (path / file).write_text(json.dumps(value))
    return str(path)


def instance_context(editor, meta):
    texture = '/Game/Horses/Arabian/Textures/T_' + meta['base']
    editor.assets[texture] = Texture2D(texture)
    inputs = {'meta': stage(editor, 'meta', meta, 'meta.json'), 'img': 'x', **{'master_' + k: 'x' for k in units.MASTERS}}
    packages = {'meta': [], 'img': [texture], **{'master_' + k: [f'/Game/Horses/{n}'] for k, n in units.MASTERS.items()}}
    folder = '/Game/Horses/Arabian/Materials'
    return NS(job_dir=str(editor.root), outputs=[f'{folder}/MI_{meta["name"]}'], inputs=inputs, packages=packages,
              params={'settings': [], 'args': {'action': 'instance', 'name': meta['name'], 'meta': 'meta', 'folder': folder,
                      'hair_colour': [.2, .1, .5], 'masters': {k: 'master_' + k for k in units.MASTERS},
                      'images': {'derived_items': {'root': 'r', 'members': [{'piece': meta['base'], 'slot': 'img', 'root': 'r'}]}}}})


@pytest.mark.parametrize('role, masked, parent, extra', [
    ('hair', False, 'M_HorseHair', {'PrimaryColor': (.2, .1, .5, 1.), 'SecondaryColor': (.27, .135, .675, 1.)}),
    ('tack', True, 'M_HorseTackMasked', {'AlphaCutoff': .4}),
    ('coat', True, 'M_HorseCoat', {})])
def test_instance_is_restyle_instance(editor, role, masked, parent, extra):
    meta = {'name': 'SK_Horse_Arabian_X', 'owner': 'SK_Horse_Arabian', 'slot': 'X', 'role': role, 'masked': masked,
            'base': 'SK_Horse_Arabian_X_Alb', 'alpha_cutoff': .4}
    mi = body.run(instance_context(editor, meta))
    assert mi.props['parent'].path == '/Game/Horses/' + parent
    assert mi.props['BaseColorTexture'].path == '/Game/Horses/Arabian/Textures/T_SK_Horse_Arabian_X_Alb'
    assert {k: (tuple(round(c, 4) for c in v) if isinstance(v, tuple) else v) for k, v in mi.props.items()
            if k not in ('parent', 'BaseColorTexture')} == extra


def test_tack_refuses_a_foreign_skeleton(editor):
    skeleton, other = Skeleton('/Game/Horses/Arabian/SKEL_Horse_Arabian'), Skeleton('/Game/Other/SKEL')
    editor.assets.update({skeleton.path: skeleton, other.path: other})
    raw = SkeletalMesh('/Game/_Raw/Horses/Arabian/Tack/Reins_00', skeleton=other, materials=[])
    editor.assets[raw.path] = raw
    context = NS(job_dir=str(editor.root), outputs=['/Game/Horses/Arabian/Tack/Reins_00/SK_Horse_Arabian_Reins_00'],
                 inputs={'raw': 'x', 'skeleton': 'x'}, packages={'raw': [raw.path], 'skeleton': [skeleton.path]},
                 params={'op': 'finish', 'kind': 'skeletal_mesh', 'source': 'raw',
                         'destination': '/Game/Horses/Arabian/Tack/Reins_00/SK_Horse_Arabian_Reins_00',
                         'args': {'action': 'tack', 'owner': 'Reins_00', 'skeleton': 'skeleton',
                                  'material_folder': '/Game/Horses/Arabian/Materials', 'materials': {}}})
    with pytest.raises(ValueError, match='breed skeleton'):
        body.run(context)


def test_master_runs_only_the_original_function(editor, monkeypatch):
    seen = []
    monkeypatch.setattr(body, 'original', lambda context, unreal, names: seen.append(names) or {
        names[0]: lambda name, *extra: editor.assets.setdefault(f'/Game/Horses/{name}', Material(f'/Game/Horses/{name}'))})
    del editor.assets['/Game/Horses/M_HorseTackMasked']
    context = NS(job_dir=str(editor.root), outputs=['/Game/Horses/M_HorseTackMasked'], inputs={}, packages={},
                 params={'args': {'action': 'master', 'key': 'tack_masked'}, 'settings': []})
    assert body.run(context).path == '/Game/Horses/M_HorseTackMasked'
    assert seen == [('make_tack_master', *body.HELPERS)]


def test_roster_and_report_each_own_one_json(monkeypatch):
    seen = []
    def collect(context, unreal, args, owned):
        seen.append((args['action'], owned)); return {'breeds': {}}, {'/Game/Horses/A/SK_Horse_A': {'mi': 'tex'}}
    monkeypatch.setattr(body, '_record', collect)
    assert body.roster(None, None, {'action': 'roster'}) == {body.ROSTER: {'breeds': {}}}
    assert body.report(None, None, {'action': 'report'}) == {
        body.REPORT: {'breeds': {}, 'materials': {'/Game/Horses/A/SK_Horse_A': {'mi': 'tex'}}}}
    assert seen == [('roster', body.ROSTER), ('report', body.REPORT)]
    monkeypatch.undo()
    both = NS(outputs={}, data_outputs=(body.ROSTER, body.REPORT))
    with pytest.raises(ValueError, match='owns only data/roster.json'):
        body.roster(both, None, {'action': 'roster'})
