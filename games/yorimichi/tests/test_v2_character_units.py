"""Character body declarations and bodies: one unit per asset bundle, keyed export members, no monolith."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path.insert(0, str(GAME))
import v2_character_units as characters  # noqa: E402

spec = importlib.util.spec_from_file_location('character_recipe', GAME / 'build.py')
recipe = importlib.util.module_from_spec(spec); sys.modules['character_recipe'] = recipe; spec.loader.exec_module(recipe)
spec = importlib.util.spec_from_file_location('character_v2', GAME / 'world/character_v2.py')
body = importlib.util.module_from_spec(spec); spec.loader.exec_module(body)
DEFINITION = characters._definition(ROOT)
MOVERS = DEFINITION.movers()
COMPRESSION = {'unit': 'unreal.animation.compression', 'item': 'asset', 'package': characters.COMPRESSION}


@pytest.fixture(scope='module')
def rows():
    steps = [step for character in MOVERS for step in recipe.mover_import_steps(character, ROOT / 'build/yorimichi')]
    return [row for row in extract(steps, checkout=ROOT, build_root=ROOT / 'build')
            if row['id'] in {f"unreal.{c.id.replace('-', '_')}" for c in MOVERS}]


def source(piece):
    return {'kind': 'group_member', 'unit': 'characters.export', 'group': 'export', 'piece': piece}


def members(cloth=('nox',)):
    return {c.id: {'body': source(f'{c.id}/{c.name}.fbx'), 'cloth': c.id in cloth,
                   'materials': {'M_Body': {'texture': {'file': 'T_Body.png', 'source': source('T_Body.png')}}, 'M_Hair': {}},
                   'clips': {'Wave': {'sample_rate': 30, 'source': source('A_Wave.fbx')}}} for c in MOVERS}


def natives():
    return {'compression': dict(COMPRESSION),
            **{c.id: {'export': {'unit': f"characters.{c.id.replace('-', '_')}.import", 'item': 'product0'}} for c in MOVERS}}


def build(rows, **change):
    return characters.character_units(rows, checkout=ROOT, natives=change.get('natives', natives()),
                                      members=change.get('members', members()))


def test_actual_targets_refuse_without_keyed_export_members(rows):
    assert sorted(r['id'] for r in rows) == ['unreal.cairo', 'unreal.modori', 'unreal.nox', 'unreal.paul', 'unreal.sword_trainer']
    with pytest.raises(characters.DynamicMembership, match='cairo, modori, nox, paul, sword-trainer'):
        characters.character_units(rows, checkout=ROOT, natives=natives())


def test_units_per_asset_bundle_with_original_import_options(rows):
    result = build(rows)
    by_id = {u['id']: u for u in result['units']}
    assert result['aliases']['unreal.paul'] == tuple(f'unreal.character.paul.{n}' for n in (
        'texture.raw.T_Body', 'texture.T_Body', 'material.M_Body', 'material.M_Hair', 'raw', 'mesh', 'clip.raw.Wave',
        'clip.Wave', 'base'))
    nox, paul = by_id['unreal.character.nox.raw'], by_id['unreal.character.paul.raw']
    assert nox['params']['create_physics_asset'] is False and paul['params']['create_physics_asset'] is True
    assert nox['params']['fbx']['import_morph_targets'] is True and 'import_morph_targets' not in paul['params']['fbx']
    assert nox['params']['fbx']['vertex_color_import_option'] == {'unreal_enum': 'VertexColorImportOption.REPLACE'}
    assert 'vertex_color_import_option' not in paul['params']['fbx']
    assert [o['class'] for o in paul['outputs']] == ['RawSkeletalMesh', 'Skeleton', 'PhysicsAsset']
    assert [o['class'] for o in nox['outputs']] == ['RawSkeletalMesh', 'Skeleton']
    assert 'native_Paul_Textures_T_Body' in {i['name'] for i in by_id['unreal.character.paul.mesh']['inputs']}
    mesh = by_id['unreal.character.nox.mesh']
    assert mesh['params']['partners'] == {'skeleton': '/Game/Nox/SK_Nox_Skeleton'}
    assert [(o['logical_path'], o['class']) for o in mesh['outputs']] == [
        ('/Game/Nox/SK_Nox', 'SkeletalMesh'), ('/Game/Nox/SK_Nox_Skeleton', 'Skeleton'), ('/Game/Nox/PA_Nox_Cloth', 'PhysicsAsset')]
    assert [o['logical_path'] for o in by_id['unreal.character.paul.mesh']['outputs']] == [
        '/Game/Paul/SK_Paul', '/Game/Paul/SK_Paul_Skeleton', '/Game/Paul/SK_Paul_PhysicsAsset']
    assert result['module_requirements']['unreal.character.nox.mesh'][0]['name'] == 'YorimichiImport'
    assert result['plugin_requirements']['unreal.character.nox.mesh'] == ['AtelierCore']
    clip_raw, clip = by_id['unreal.character.cairo.clip.raw.Wave'], by_id['unreal.character.cairo.clip.Wave']
    assert clip_raw['params']['fbx'] == {**characters.CLIP_FBX, 'custom_sample_rate': 30,
                                         'delete_existing_morph_target_curves': True, 'do_not_import_curve_with_zero': False}
    assert clip_raw['inputs'][1]['source'] == {'kind': 'item', 'unit': 'unreal.character.cairo.mesh', 'item': 'skeleton'}
    names = {i['name']: i['source'] for i in clip['inputs']}
    assert names['compression'] == {'kind': 'item', 'unit': COMPRESSION['unit'], 'item': 'asset'}
    assert 'native_Cairo_M_Body' in names and 'native_Cairo_Textures_T_Body' in names
    base = by_id['unreal.character.paul.base']
    assert base['outputs'][0]['class'] == 'WandererDefinition' and base['outputs'][0]['logical_path'] == '/Game/Paul/DA_PaulBase'
    assert base['params']['args']['camera_height'] == 40.0
    assert {r['refusal'] for r in result['runtime_refusals']} == {characters.SKELETON_MUTATION}
    assert {r['unit'] for r in result['runtime_refusals']} == {'unreal.character.cairo.clip.raw.Wave', 'unreal.character.nox.clip.raw.Wave'}


def test_finished_identities_carry_transitive_dependencies(rows):
    packages = build(rows)['packages']
    mesh = packages['/Game/Paul/SK_Paul']
    assert {d['package'] for d in mesh['dependencies']} == {
        '/Game/Paul/M_Body', '/Game/Paul/Textures/T_Body', '/Game/Paul/M_Hair', '/Game/Paul/SK_Paul_Skeleton',
        '/Game/Paul/SK_Paul_PhysicsAsset'}
    assert packages['/Game/Paul/M_Body']['dependencies'] == [
        {'unit': 'unreal.character.paul.texture.T_Body', 'item': 'texture', 'package': '/Game/Paul/Textures/T_Body'}]
    base = packages['/Game/Paul/DA_PaulBase']
    assert [d['package'] for d in base['dependencies']] == ['/Game/Paul/SK_Paul', '/Game/Paul/A_Wave']


@pytest.mark.parametrize('change', ['compression', 'export', 'shape', 'material', 'texture', 'clip', 'source', 'unselected',
                                    'row', 'modules'])
def test_missing_producers_or_reshaped_inputs_refuse(rows, change):
    selected, supplied, roster = deepcopy(rows), natives(), members()
    if change == 'compression': supplied['compression']['package'] = '/Game/Other'
    elif change == 'export': del supplied['nox']['export']
    elif change == 'shape': del roster['nox']['cloth']
    elif change == 'material': roster['nox']['materials']['M/Bad'] = {}
    elif change == 'texture': roster['nox']['materials']['M_Body']['texture'] = {'file': 'T_Body.png'}
    elif change == 'clip': roster['nox']['clips']['Wave']['sample_rate'] = 30.0
    elif change == 'source': roster['nox']['body'] = {'kind': 'file', 'path': 'build/x.fbx'}
    elif change == 'unselected': roster['ghost'] = roster['nox']
    elif change == 'row': selected[0]['outputs'] = []
    elif change == 'modules': selected[0]['commands'][0]['modules'] = ['Other']
    with pytest.raises(characters.Unsupported):
        characters.character_units(selected, checkout=ROOT, natives=supplied, members=roster)


# ---- bodies ---------------------------------------------------------------------------------------------------------

class Asset:
    def __init__(self, path, **props): self.path, self.props = path, dict(props)
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[1]
    def get_editor_property(self, name): return self.props[name]
    def set_editor_property(self, name, value): self.props[name] = value


class SkeletalMesh(Asset):
    @property
    def materials(self): return self.props['materials']
    def get_all_morph_target_names(self): return []


class Skeleton(Asset): pass
class PhysicsAsset(Asset): pass
class AnimSequence(Asset): pass


class Slot(Asset):
    @property
    def material_interface(self): return self.props['material_interface']


@pytest.fixture
def editor(tmp_path, monkeypatch):
    export = tmp_path / 'inputs/export'; export.mkdir(parents=True)
    config = {'materials': {'M_Body': {'texture': 'T_Body.png', 'two_sided': False, 'meshes': ['Body'], 'roughness': 1,
                                       'metallic': 0, 'specular': 0}},
              'parents': {'root': None, 'pelvis': 'root'}, 'cloth': None,
              'clips': {'Wave': {'duration': 1.0, 'frames': 30, 'fps': 30}}, 'rest_ankles_cm': {'L': 8.0, 'R': 8.5}, 'sole_cm': 1.0}
    (export / 'export.json').write_text(json.dumps(config))
    for helper in ('animation_compression.py', 'skin_morph_contacts.py'):
        target = tmp_path / body.SCRIPTS / helper; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((ROOT / body.SCRIPTS / helper).read_text())
    world = tmp_path / 'games/yorimichi/world'; world.mkdir(parents=True)
    (world / 'yori.py').write_text('OUT = None\n')
    assets, saves = {}, []
    def duplicate(source, destination):
        copy = type(assets[source])(destination, **assets[source].props); assets[destination] = copy; return copy
    unreal = NS(SkeletalMesh=SkeletalMesh, Skeleton=Skeleton, PhysicsAsset=PhysicsAsset, AnimSequence=AnimSequence,
                EditorAssetLibrary=NS(load_asset=lambda p: assets.get(p.split('.', 1)[0]), does_asset_exist=lambda p: p in assets,
                                      duplicate_asset=duplicate, save_loaded_asset=lambda a, d=True: saves.append(a.path) or True),
                SkeletalMeshEditorSubsystem=NS(set_allow_cpu_access=lambda mesh, value: mesh.props.update(cpu=value)),
                get_editor_subsystem=lambda _: NS(get_bone_children=lambda mesh, bone: ['pelvis'] if bone == 'root' else []),
                SkinMorphContactLibrary=NS(clear_skin_morph_contacts=lambda mesh: mesh.props.update(cleared=True)))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    return NS(assets=assets, saves=saves, root=tmp_path, export=export, config=config, unreal=unreal)


def mesh_case(editor, *, physics):
    raw_skeleton = Skeleton('/Game/_Raw/Characters/paul/SK_Paul_Skeleton')
    raw_physics = PhysicsAsset('/Game/_Raw/Characters/paul/SK_Paul_PhysicsAsset') if physics else None
    material = Asset('/Game/Paul/M_Body', used_with_skeletal_mesh=True, used_with_morph_targets=True, two_sided=False)
    raw = SkeletalMesh('/Game/_Raw/Characters/paul/SK_Paul', skeleton=raw_skeleton, physics_asset=raw_physics,
                       materials=[Slot('slot', imported_material_slot_name='M_Body', material_interface=None)])
    for asset in (raw, raw_skeleton, material, *([raw_physics] if physics else [])):
        editor.assets[asset.path] = asset
    partners = {'skeleton': '/Game/Paul/SK_Paul_Skeleton', **({'physics_asset': '/Game/Paul/SK_Paul_PhysicsAsset'} if physics else {})}
    return NS(job_dir=str(editor.root), inputs={'raw': 'x', 'material_M_Body': 'x', 'export': str(editor.export)},
              packages={'raw': [raw.path], 'material_M_Body': [material.path]},
              outputs=['/Game/Paul/SK_Paul', *partners.values()],
              params={'op': 'finish', 'kind': 'skeletal_mesh', 'source': 'raw', 'destination': '/Game/Paul/SK_Paul',
                      'partners': partners, 'args': {'action': 'mesh', 'name': 'Paul', 'dest': '/Game/Paul', 'export': 'export',
                                                     'materials': {'M_Body': 'material_M_Body'}, 'cpu_access': True,
                                                     'morphs': True, 'contact_morphs': []}})


def test_mesh_finish_owns_its_bundle_and_binds_materials(editor):
    context = mesh_case(editor, physics=True)
    mesh = body.run(context)
    assert mesh.path == '/Game/Paul/SK_Paul' and mesh.props['cpu'] is True and mesh.props['cleared'] is True
    assert mesh.props['skeleton'].path == '/Game/Paul/SK_Paul_Skeleton'
    assert mesh.props['physics_asset'].path == '/Game/Paul/SK_Paul_PhysicsAsset'
    assert mesh.materials[0].material_interface.path == '/Game/Paul/M_Body'
    assert editor.saves[-1] == '/Game/Paul/SK_Paul'


def test_mesh_without_physics_refuses_a_raw_physics_asset(editor):
    context = mesh_case(editor, physics=False)
    assert body.run(context).props['physics_asset'] is None
    editor.assets.clear(); editor.saves.clear()
    context = mesh_case(editor, physics=True)
    del context.params['partners']['physics_asset']; context.outputs = context.outputs[:2]
    with pytest.raises(ValueError, match='physics_asset = false'):
        body.run(context)


@pytest.mark.parametrize('failure', ['parents', 'outputs', 'material', 'cloth'])
def test_mesh_finish_refuses_inconsistent_state(editor, failure):
    context = mesh_case(editor, physics=True)
    if failure == 'parents':
        editor.config['parents']['head'] = 'pelvis'
    elif failure == 'outputs':
        context.outputs = context.outputs[:1]
    elif failure == 'material':
        editor.assets['/Game/_Raw/Characters/paul/SK_Paul'].props['materials'][0].props['imported_material_slot_name'] = 'M_Other'
    elif failure == 'cloth':
        editor.config['cloth'] = {'mesh': 'Body', 'colliders': []}
    (editor.export / 'export.json').write_text(json.dumps(editor.config))
    with pytest.raises(ValueError):
        body.run(context)


def test_clip_and_base_finish_from_declared_items(editor):
    skeleton, settings = Skeleton('/Game/Paul/SK_Paul_Skeleton'), Asset(characters.COMPRESSION)
    mesh = SkeletalMesh('/Game/Paul/SK_Paul', morph_targets=[])
    raw = AnimSequence('/Game/_Raw/Characters/paul/A_Wave', skeleton=skeleton, sequence_length=1.0, enable_root_motion=True,
                       bone_compression_settings=None)
    for asset in (skeleton, settings, mesh, raw):
        editor.assets[asset.path] = asset
    context = NS(job_dir=str(editor.root), inputs={k: 'x' for k in ('raw', 'skeleton', 'compression', 'mesh')} | {'export': str(editor.export)},
                 packages={'raw': [raw.path], 'skeleton': [skeleton.path], 'compression': [settings.path], 'mesh': [mesh.path]},
                 outputs=['/Game/Paul/A_Wave'],
                 params={'op': 'finish', 'kind': 'animation', 'source': 'raw', 'destination': '/Game/Paul/A_Wave',
                         'args': {'action': 'clip', 'name': 'Wave', 'export': 'export', 'skeleton': 'skeleton', 'mesh': 'mesh',
                                  'compression': 'compression'}})
    clip = body.run(context)
    assert clip.props['enable_root_motion'] is False and clip.props['bone_compression_settings'] is settings
    created = {}
    def create(name, folder, cls, factory):
        created['factory'] = factory; asset = Asset(folder + '/' + name); editor.assets[asset.path] = asset; return asset
    editor.unreal.AssetToolsHelpers = NS(get_asset_tools=lambda: NS(create_asset=create))
    editor.unreal.DataAssetFactory = lambda: Asset('factory')
    editor.unreal.WandererDefinition = Asset
    editor.unreal.Vector2D = lambda x, y: (x, y)
    context = NS(job_dir=str(editor.root), inputs={'mesh': 'x', 'clip_Wave': 'x', 'export': str(editor.export)},
                 packages={'mesh': [mesh.path], 'clip_Wave': [clip.path]}, outputs=['/Game/Paul/DA_PaulBase'],
                 params={'settings': [], 'args': {'action': 'base', 'name': 'DA_PaulBase', 'dest': '/Game/Paul', 'export': 'export',
                                                  'mesh': 'mesh', 'clips': {'Wave': 'clip_Wave'}, 'camera_height': 40.0}})
    base = body.run(context)
    assert base.props == {'mesh': mesh, 'actions': {'Wave': clip}, 'use_authored_movement': True, 'rest_ankle_heights': (8.0, 8.5),
                          'sole_height': 1.0, 'camera_height': 40.0}
    assert created['factory'].props['data_asset_class'] is Asset
