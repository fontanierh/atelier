"""Actual characters.wanderer row, committed clip roster, Wanderer V2 units and fake-editor native bodies."""
from copy import copy, deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]; GAME = ROOT / 'games/yorimichi'
sys.path[:0] = [str(GAME), str(GAME / 'world')]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


units = load('games/yorimichi/v2_wanderer_units.py', 'wanderer_units_test')
body = load(units.SCRIPT, 'wanderer_body_test')
COMPRESSION = {'unit': 'unreal.animation.compression', 'item': 'asset', 'package': units.COMPRESSION}
SOURCE = {'unit': 'characters.wanderer', 'item': 'product0',
          'root': {'archive_member': 'products/0-0.tree.tar', 'name': 'wanderer'}}


@pytest.fixture(scope='module')
def rows():
    factory = load('games/yorimichi/build.py', 'wanderer_build_test')
    steps = [s for s in factory.character_steps(NS(out=ROOT / 'build/yorimichi')) if s.name == 'characters.wanderer']
    return extract(steps, checkout=ROOT, build_root=ROOT / 'build')


def natives():
    return {'wanderer': dict(SOURCE), 'compression': dict(COMPRESSION)}


def test_roster_is_committed_actions_and_original_blendspaces():
    clips = units.roster(ROOT)
    assert clips[:4] == ['Idle', 'Walk', 'Jog', 'Run'] and {'CrouchIdle', 'CrouchWalk', 'Sprint', 'TurnRight'} <= set(clips)
    assert units.blendspaces(ROOT) == {'BS_Locomotion': ['Idle', 'Walk', 'Jog', 'Run'], 'BS_Crouching': ['CrouchIdle', 'CrouchWalk']}


def test_units_per_asset_bundle_with_original_import_options(rows):
    assert rows[0]['outputs'] == []
    assert rows[0]['products'] == [{'id': 'characters.wanderer.export',
        'paths': ['build/yorimichi/wanderer'], 'optional_paths': []}]
    result = units.wanderer_units(rows, checkout=ROOT, natives=natives())
    by_id = {u['id']: u for u in result['units']}
    clips = result['clips']
    assert len(by_id) == 3 + 2 * len(clips) + 2 + 1
    raw = by_id['unreal.wanderer.raw']['params']
    assert raw['source_member'] == 'fbx/Wanderer.fbx' and raw['create_physics_asset'] is True and raw['fbx'] == units.MESH_FBX
    assert raw['input_roots'] == {'wanderer': SOURCE['root']}
    assert [o['logical_path'] for o in by_id['unreal.wanderer.mesh']['outputs']] == [
        '/Game/Wanderer/V2/SK_Wanderer', '/Game/Wanderer/V2/SK_Wanderer_Skeleton', '/Game/Wanderer/V2/SK_Wanderer_PhysicsAsset']
    for clip in clips:
        imported = by_id[f'unreal.wanderer.clip.raw.{clip}']
        assert imported['params']['source_member'] == f'fbx/{clip}.fbx' and imported['params']['fbx']['custom_sample_rate'] == 60
        assert imported['inputs'][0]['source'] == {'kind': 'item', 'unit': 'unreal.wanderer.mesh', 'item': 'skeleton'}
        finish = by_id[f'unreal.wanderer.clip.{clip}']
        names = {i['name']: i['source'] for i in finish['inputs']}
        assert names['compression'] == {'kind': 'item', 'unit': COMPRESSION['unit'], 'item': 'asset'}
        assert names[finish['params']['args']['skeleton']]['item'] == 'skeleton'
        assert finish['outputs'][0]['logical_path'] == f'/Game/Wanderer/V2/A_{clip}'
    definition = by_id['unreal.wanderer.definition']
    assert definition['outputs'][0]['logical_path'] == '/Game/Wanderer/DA_Wanderer' and definition['outputs'][0]['class'] == 'WandererDefinition'
    assert set(definition['params']['args']['clips']) == set(clips)
    assert by_id['unreal.wanderer.material']['inputs'] == [] and 'unreal.wanderer.material' in result['module_requirements']
    assert all(set(result['staged_inputs'][u]) == {i['name'] for i in by_id[u]['inputs']} for u in by_id)
    assert all((ROOT / p).is_file() for p in definition['code'])
    for unit in by_id.values():
        produced = {i['source']['unit'] for i in unit['inputs']} - {'characters.wanderer', COMPRESSION['unit']}
        assert produced <= set(by_id) and not any(u == unit['id'] for u in produced)
    assert result['packages']['/Game/Wanderer/DA_Wanderer']['dependencies'][0]['package'] == '/Game/Wanderer/V2/SK_Wanderer'


@pytest.mark.parametrize('damage', ['row', 'command', 'source', 'foreign', 'compression', 'alias'])
def test_missing_producers_or_changed_original_refuse(rows, damage):
    rows, refs = deepcopy(rows), natives()
    if damage == 'row': rows = []
    elif damage == 'command': rows[0]['commands'][0]['args'] = ['--export']
    elif damage == 'source': del refs['wanderer']
    elif damage == 'foreign': refs['wanderer']['unit'] = 'characters.other'
    elif damage == 'compression': del refs['compression']
    else: refs['compression']['package'] = '/Game/Other'
    with pytest.raises(units.Unsupported):
        units.wanderer_units(rows, checkout=ROOT, natives=refs)


def test_roster_refuses_untuned_motion_edits(tmp_path):
    for relative in ('kit/animate.py', 'wanderer_motion.py'):
        target = tmp_path / units.SOURCE / relative; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((ROOT / units.SOURCE / relative).read_text())
    motion = tmp_path / units.SOURCE / 'wanderer_motion.py'
    motion.write_text(motion.read_text() + "\nACTIONS['Extra']=dict(duration=1)\n")
    with pytest.raises(units.Unsupported):
        units.roster(tmp_path)


# ---- native bodies --------------------------------------------------------------------------------------------------

class Props:
    def __init__(self, **values): self.values = dict(values)
    def get_editor_property(self, key): return self.values[key]
    def set_editor_property(self, key, value): self.values[key] = value
class Asset(Props):
    def __init__(self, path, **values): super().__init__(**values); self.path = path
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[-1]
class Material(Asset): pass
class Skeleton(Asset): pass
class Physics(Asset): pass
class Mesh(Asset): pass
class Sequence(Asset): pass
class Blend(Asset): pass
class Definition(Asset): pass
CLASSES = {'Material': Material, 'Blend': Blend, 'Definition': Definition}


def export_item(tmp_path, clips=('Idle', 'Walk', 'Jog', 'Run', 'CrouchIdle', 'CrouchWalk')):
    root = tmp_path / 'inputs/wanderer'; (root / 'fbx').mkdir(parents=True)
    model = {'bones': {'root': None, 'pelvis': 'root', 'head': 'pelvis'}, 'materials': ['Wanderer_Palette']}
    speeds = {'Walk': .9, 'Jog': 1.8, 'Run': 3., 'CrouchWalk': .5}
    manifest = {c: {'duration': 1.0, 'frames': 61, **({'speed': speeds[c]} if c in speeds else {})} for c in clips}
    files = {'model_manifest.json': json.dumps(model), 'animation_manifest.json': json.dumps(manifest),
             'animation_targets.json': '{}', 'Wanderer.blend': 'blend', 'fbx/Wanderer.fbx': 'mesh',
             **{f'fbx/{c}.fbx': c for c in clips}}
    for name, text in files.items():
        (root / name).write_text(text)
    (root / 'build.json').write_text(json.dumps({'sources': {}, 'artifacts': {
        name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()}}))
    return root, model, manifest


def editor(tmp_path, monkeypatch, assets, bones):
    state = NS(saves=[], configured=[])
    def create(name, folder, cls, factory):
        asset = CLASSES[cls.__name__](folder + '/' + name, **({'blend_parameters': [Props()], 'interpolation_param': [Props()]}
                                                            if cls is Blend else {}))
        assets[asset.path] = asset; return asset
    def duplicate(path, target):
        # A duplicate keeps its references to other packages, as the editor does.
        result = copy(assets[path]); result.values = {k: copy(v) if isinstance(v, list) else v for k, v in result.values.items()}
        result.path = target; assets[target] = result; return result
    def save(asset, dirty):
        state.saves.append(asset.path); return True
    graph = NS(delete_all_material_expressions=lambda m: None, recompile_material=lambda m: None,
               create_material_expression=lambda *a: Props(), connect_material_expressions=lambda *a: True,
               connect_material_property=lambda *a: True)
    children = {}
    for bone, parent in bones.items():
        if parent: children.setdefault(parent, []).append(bone)
    unreal = NS(Material=Material, MaterialInterface=Material, SkeletalMesh=Mesh, Skeleton=Skeleton, PhysicsAsset=Physics,
        AnimSequence=Sequence, BlendSpace1D=Blend, WandererDefinition=Definition, MaterialFactoryNew=lambda: None,
        MaterialExpressionVertexColor=0, MaterialExpressionCustom=0, MaterialExpressionConstant=0, MaterialExpressionMultiply=0,
        CustomMaterialOutputType=NS(CMOT_FLOAT3=3), CustomInput=Props, MaterialEditingLibrary=graph,
        MaterialProperty=NS(MP_BASE_COLOR=0, MP_ROUGHNESS=1, MP_SPECULAR=2, MP_EMISSIVE_COLOR=3),
        BlendSpaceFactory1D=Props, DataAssetFactory=Props, SkeletalMeshEditorSubsystem=object(),
        get_editor_subsystem=lambda cls: NS(get_bone_children=lambda mesh, bone: children.get(bone, [])),
        AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=create)),
        WandererContentLibrary=NS(configure_blend_space=lambda b, c, s: state.configured.append((b.path, [x.path for x in c], s)) or True),
        EditorAssetLibrary=NS(load_asset=assets.get, does_asset_exist=lambda p: p in assets, duplicate_asset=duplicate, save_loaded_asset=save))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    return state


def context(tmp_path, params, inputs, outputs):
    return NS(job_dir=str(tmp_path), inputs={k: v[0] for k, v in inputs.items()}, packages={k: v[1] for k, v in inputs.items()},
              outputs=outputs, params=params)


def test_material_keeps_original_flat_two_sided_graph(tmp_path, monkeypatch):
    assets = {}; state = editor(tmp_path, monkeypatch, assets, {})
    mat = body.run(context(tmp_path, {'args': {'action': 'material'}, 'settings': []}, {}, ['/Game/Wanderer/V2/M_Wanderer']))
    assert mat.values == {'used_with_skeletal_mesh': True, 'two_sided': True} and state.saves == [mat.path]


def mesh_case(tmp_path, monkeypatch):
    root, model, _ = export_item(tmp_path)
    raw = '/Game/_Raw/Wanderer/SK_Wanderer'
    assets = {raw + '_Skeleton': Skeleton(raw + '_Skeleton'), raw + '_PhysicsAsset': Physics(raw + '_PhysicsAsset'),
              '/Game/Wanderer/V2/M_Wanderer': Material('/Game/Wanderer/V2/M_Wanderer')}
    assets[raw] = Mesh(raw, skeleton=assets[raw + '_Skeleton'], physics_asset=assets[raw + '_PhysicsAsset'],
                       materials=[Props(material_interface=None)])
    state = editor(tmp_path, monkeypatch, assets, model['bones'])
    dest = '/Game/Wanderer/V2/SK_Wanderer'
    ctx = context(tmp_path, {'op': 'finish', 'kind': 'skeletal_mesh', 'source': 'raw', 'destination': dest,
                             'partners': {'skeleton': dest + '_Skeleton', 'physics_asset': dest + '_PhysicsAsset'},
                             'args': {'action': 'mesh', 'material': 'material', 'wanderer': 'wanderer'}},
                  {'raw': ('r', [raw]), 'material': ('m', ['/Game/Wanderer/V2/M_Wanderer']), 'wanderer': (str(root), [])},
                  [dest, dest + '_Skeleton', dest + '_PhysicsAsset'])
    return assets, state, ctx, root


def test_mesh_owns_compact_skeleton_and_checks_manifest_bones(tmp_path, monkeypatch):
    assets, state, ctx, _ = mesh_case(tmp_path, monkeypatch)
    mesh = body.run(ctx)
    assert mesh.get_editor_property('skeleton').path == '/Game/Wanderer/V2/SK_Wanderer_Skeleton'
    assert mesh.get_editor_property('materials')[0].values['material_interface'] is assets['/Game/Wanderer/V2/M_Wanderer']
    assert state.saves == ctx.outputs[1:] + ctx.outputs[:1]


@pytest.mark.parametrize('damage', ['bones', 'digest', 'slots', 'fresh', 'material'])
def test_mesh_refuses_changed_sources(tmp_path, monkeypatch, damage):
    assets, state, ctx, root = mesh_case(tmp_path, monkeypatch)
    raw = assets['/Game/_Raw/Wanderer/SK_Wanderer']
    if damage == 'bones':
        (root / 'model_manifest.json').write_text(json.dumps({'bones': {'root': None, 'spine': 'root'}, 'materials': ['P']}))
        build = json.loads((root / 'build.json').read_text())
        build['artifacts']['model_manifest.json'] = hashlib.sha256((root / 'model_manifest.json').read_bytes()).hexdigest()
        (root / 'build.json').write_text(json.dumps(build))
    elif damage == 'digest': (root / 'fbx/Wanderer.fbx').write_text('other')
    elif damage == 'slots': raw.values['materials'] = [Props(material_interface=None)] * 2
    elif damage == 'fresh': assets[ctx.outputs[0]] = Mesh(ctx.outputs[0])
    else: ctx.packages['material'] = ['/Game/Other/M']; assets['/Game/Other/M'] = Material('/Game/Other/M')
    with pytest.raises(ValueError):
        body.run(ctx)


def clip_case(tmp_path, monkeypatch, name='Walk'):
    root, _, manifest = export_item(tmp_path)
    skeleton = Skeleton('/Game/Wanderer/V2/SK_Wanderer_Skeleton')
    raw = f'/Game/_Raw/Wanderer/A_{name}'
    assets = {raw: Sequence(raw, skeleton=skeleton, sequence_length=1.0, enable_root_motion=True),
              skeleton.path: skeleton, units.COMPRESSION: Asset(units.COMPRESSION)}
    state = editor(tmp_path, monkeypatch, assets, {})
    scripts = tmp_path / body.SCRIPTS; scripts.mkdir(parents=True)
    (scripts / 'animation_compression.py').write_text(
        "_settings=None\ndef apply_to(sequence):\n    sequence.set_editor_property('bone_compression_settings', _settings)\n")
    dest = f'/Game/Wanderer/V2/A_{name}'
    ctx = context(tmp_path, {'op': 'finish', 'kind': 'animation', 'source': 'raw', 'destination': dest,
                             'args': {'action': 'clip', 'name': name, 'skeleton': 'skeleton', 'compression': 'compression',
                                      'wanderer': 'wanderer'}},
                  {'raw': ('r', [raw]), 'skeleton': ('s', [skeleton.path]), 'compression': ('c', [units.COMPRESSION]),
                   'wanderer': (str(root), [])}, [dest])
    return assets, ctx, root


def test_clip_keeps_duration_root_motion_and_shared_compression(tmp_path, monkeypatch):
    assets, ctx, _ = clip_case(tmp_path, monkeypatch)
    clip = body.run(ctx)
    assert clip.values['enable_root_motion'] is False and clip.values['bone_compression_settings'] is assets[units.COMPRESSION]


@pytest.mark.parametrize('damage', ['duration', 'skeleton', 'compression', 'roster', 'kind'])
def test_clip_refuses_changed_sources(tmp_path, monkeypatch, damage):
    assets, ctx, root = clip_case(tmp_path, monkeypatch)
    raw = assets['/Game/_Raw/Wanderer/A_Walk']
    if damage == 'duration': raw.values['sequence_length'] = 1.5
    elif damage == 'skeleton': raw.values['skeleton'] = Skeleton('/Game/Other_Skeleton')
    elif damage == 'compression': ctx.packages['compression'] = ['/Game/Other']; assets['/Game/Other'] = Asset('/Game/Other')
    elif damage == 'roster': (root / 'fbx/Walk.fbx').unlink()
    else: ctx.params['kind'] = 'static_mesh'
    with pytest.raises(ValueError):
        body.run(ctx)


def test_blendspaces_and_public_definition_use_manifest_speeds(tmp_path, monkeypatch):
    root, _, manifest = export_item(tmp_path)
    skeleton = Skeleton('/Game/Wanderer/V2/SK_Wanderer_Skeleton')
    assets = {skeleton.path: skeleton, '/Game/Wanderer/V2/SK_Wanderer': Mesh('/Game/Wanderer/V2/SK_Wanderer'),
              **{f'/Game/Wanderer/V2/A_{c}': Sequence(f'/Game/Wanderer/V2/A_{c}', skeleton=skeleton) for c in manifest}}
    state = editor(tmp_path, monkeypatch, assets, {})
    item = {'wanderer': (str(root), []), 'skeleton': ('s', [skeleton.path]),
            **{'clip_' + c: ('c', [f'/Game/Wanderer/V2/A_{c}']) for c in manifest}}
    for name, names in units.blendspaces(ROOT).items():
        blend = body.run(context(tmp_path, {'args': {'action': 'blendspace', 'name': name, 'skeleton': 'skeleton',
                                                     'clips': {c: 'clip_' + c for c in names}, 'wanderer': 'wanderer'}, 'settings': []},
                                 item, [f'/Game/Wanderer/V2/{name}']))
        assert blend.values['interpolation_param'][0].values['interpolation_time'] == body.INTERPOLATION[name]
    assert state.configured[0] == ('/Game/Wanderer/V2/BS_Locomotion', [f'/Game/Wanderer/V2/A_{c}' for c in ('Idle', 'Walk', 'Jog', 'Run')],
                                   [0, 90., 180., 300.])
    item.update(mesh=('m', ['/Game/Wanderer/V2/SK_Wanderer']), loco=('b', ['/Game/Wanderer/V2/BS_Locomotion']),
                crouch=('b', ['/Game/Wanderer/V2/BS_Crouching']))
    args = {'action': 'definition', 'mesh': 'mesh', 'clips': {c: 'clip_' + c for c in manifest}, 'locomotion': 'loco',
            'crouching': 'crouch', 'camera_height': 35., 'wanderer': 'wanderer'}
    asset = body.run(context(tmp_path, {'args': args, 'settings': []}, item, ['/Game/Wanderer/DA_Wanderer']))
    assert asset.path == '/Game/Wanderer/DA_Wanderer' and asset.values['walk_speed'] == 90. and asset.values['crouch_speed'] == 50.
    del args['clips']['Idle']
    del assets['/Game/Wanderer/DA_Wanderer']
    with pytest.raises(ValueError):
        body.run(context(tmp_path, {'args': args, 'settings': []}, item, ['/Game/Wanderer/DA_Wanderer']))
