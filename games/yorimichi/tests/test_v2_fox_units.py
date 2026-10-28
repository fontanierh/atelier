"""unreal.fox_hunter as native units: the actual rows, member projection over a synthetic export, bodies on a fake editor."""
from copy import deepcopy
import ast
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2.file_groups import emit
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path.insert(0, str(GAME))
import v2_fox_units as units  # noqa: E402
from v2_texture_units import Unsupported  # noqa: E402


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


members = load(units.BODY, 'fox_members_test')
body = load(units.SCRIPT, 'fox_body_test')
MANIFEST = json.loads((ROOT / units.MANIFEST).read_text())
COMPRESSION = {'unit': 'unreal.animation.compression', 'item': 'asset', 'package': units.COMPRESSION}


@pytest.fixture(scope='module')
def rows():
    spec = importlib.util.spec_from_file_location('fox_recipe', GAME / 'build.py')
    recipe = importlib.util.module_from_spec(spec); sys.modules['fox_recipe'] = recipe; spec.loader.exec_module(recipe)
    context = NS(uproject=GAME / 'unreal/Yorimichi.uproject', out=ROOT / 'build/yorimichi')
    steps = [s for s in recipe.steps(context) if s.name in ('characters.fox_hunter', 'unreal.fox_hunter')]
    for step in steps:
        step.needs = [n for n in step.needs if n == 'characters.fox_hunter']; step.after = []; step.reads = []
    found = extract(steps, checkout=ROOT, build_root=ROOT / 'build')
    producer = next(r for r in found if r['id'] == 'characters.fox_hunter')
    assert [p for p in producer['products'] if p['id'] == units.PRODUCT] == [
        {'id': units.PRODUCT, 'paths': list(units.EXPORT_PATHS), 'optional_paths': []}]
    return found


@pytest.fixture(scope='module')
def declared(rows):
    result = units.fox_units(rows, checkout=ROOT, natives={'compression': COMPRESSION})
    for unit in result['units']:
        assert not {o['id'] for o in unit['outputs']} & {g['id'] for g in unit.get('output_groups', [])}
    return result


def test_every_package_from_the_actual_rows(declared):
    found = {u['id']: u for u in declared['units']}
    assert len(MANIFEST['clips']) == 15 and MANIFEST['fps'] == 30
    assert sorted(found) == sorted(['characters.fox_hunter.members.images', 'characters.fox_hunter.members.materials',
                                    'characters.fox_hunter.members.clips', 'characters.fox_hunter.body', 'unreal.fox_hunter.raw',
                                    'unreal.fox_hunter.mesh', 'unreal.fox_hunter.locomotion', 'unreal.fox_hunter.definition',
                                    'unreal.fox_hunter.record'])
    source = found['characters.fox_hunter.members.clips']['inputs'][0]
    assert source['source'] == {'kind': 'item', 'unit': 'characters.fox_hunter', 'item': 'product0'} and 'whole' in source
    paths = found['characters.fox_hunter.body']['params']['recipe']['paths']
    assert paths[units.OUT + '/fbx'] == 'inputs/export/products/0-1.tree.tar'
    raw = found['unreal.fox_hunter.raw']
    assert raw['params']['create_physics_asset'] is True and raw['params']['fbx']['import_morph_targets'] is False
    assert raw['params']['input_roots'] == {'source': {'archive_member': 'member.tree.tar', 'name': 'member'}}
    mesh = found['unreal.fox_hunter.mesh']
    assert mesh['params']['partners'] == {'skeleton': '/Game/FoxHunter/SK_FoxHunter_Skeleton',
                                          'physics_asset': '/Game/FoxHunter/SK_FoxHunter_PhysicsAsset'}
    assert mesh['params']['args']['materials'] == units.token('materials')
    assert found['unreal.fox_hunter.definition']['outputs'][0]['class'] == 'DataAsset'
    assert declared['module_requirements']['unreal.fox_hunter.definition'][0]['name'] == 'Yorimichi'
    record = found['unreal.fox_hunter.record']
    assert [o['destination'] for o in record['outputs']] == ['store'] and units.REPORT_FILE in declared['packages']
    templates = {t['unit_prefix']: t for t in declared['templates']}
    assert sorted(templates) == ['unreal.fox_hunter.clips', 'unreal.fox_hunter.images', 'unreal.fox_hunter.materials']
    clip_raw, clip_finish = (f['unit'] for f in templates['unreal.fox_hunter.clips']['followers'])
    assert clip_raw['params']['fbx']['custom_sample_rate'] == 30 and clip_raw['params']['skeleton'] == 'skeleton'
    assert clip_finish['params']['destination'] == '/Game/FoxHunter/A_Fox$piece'
    assert {i['name']: i['source']['unit'] for i in clip_finish['inputs']}['compression'] == COMPRESSION['unit']
    material = templates['unreal.fox_hunter.materials']['followers'][0]['unit']
    assert material['params']['args']['images'] == units.token('images') and material['outputs'][0]['logical_path'] == '/Game/FoxHunter/$piece'
    for template in declared['templates']:
        for follower in template['followers']:
            assert all(i['source']['unit'] != 'characters.fox_hunter' for i in follower['unit']['inputs'])
    assert declared['aliases']['unreal.fox_hunter'] == tuple(found)


# The classes the native controller (platform/build-v2/src/unreal_controller.rs) admits for authored assets.
AUTHORED = {'Material', 'MaterialInstance', 'MaterialParameterCollection', 'Map', 'Blueprint', 'BlendSpace1D',
            'AdventureMoveSet', 'AnimBoneCompressionSettings', 'WandererDefinition', 'SoundAttenuation', 'DataAsset', 'JsonData'}
OTHERS = {'Data', 'RawTexture', 'Texture', 'RawSkeletalMesh', 'Skeleton', 'PhysicsAsset', 'SkeletalMesh', 'RawAnimation', 'Animation'}


def test_emitted_output_classes_are_registered(declared):
    units = [*declared['units'], *(f['unit'] for t in declared['templates'] for f in t['followers'])]
    for unit in units:
        allowed = AUTHORED if unit['op']['kind'] == 'unreal.author' else OTHERS
        assert {o['class'] for o in unit['outputs']} <= allowed, unit['id']
    assert {t['output_class'] for t in declared['templates']} == {'Data'}


@pytest.mark.parametrize('damage', ['importer', 'product', 'compression'])
def test_declaration_drift_refuses(rows, damage):
    rows, natives = deepcopy(rows), {'compression': dict(COMPRESSION)}
    found = {r['id']: r for r in rows}
    if damage == 'importer':
        found['unreal.fox_hunter']['commands'][0]['env'] = [['X', '1']]
    elif damage == 'product':
        found['characters.fox_hunter']['products'][-1]['paths'].pop()
    else:
        natives['compression']['package'] = '/Game/Other'
    with pytest.raises(Unsupported):
        units.fox_units(rows, checkout=ROOT, natives=natives)


# ---- projection -----------------------------------------------------------------------------------------------------

PNG = b'\x89PNG\r\n\x1a\n' + b'x' * 8


@pytest.fixture
def export(tmp_path):
    (tmp_path / 'fbx').mkdir(); (tmp_path / 'textures').mkdir()
    (tmp_path / 'fbx/FoxHunter.fbx').write_bytes(b'mesh')
    clips = {}
    for name in MANIFEST['clips']:
        (tmp_path / f'fbx/A_Fox{name}.fbx').write_bytes(name.encode())
        clips[name] = {'duration': 1.5, 'sample_rate': 30, 'root_motion': name.startswith('Dash'), 'loop': name == 'Idle',
                       'holds_last_pose': name == 'Death', 'travel_cm': [0., 0., 0.], 'yaw_degrees': 0.,
                       'travel_speed_cm_s': {'Idle': 0., 'Creep': 90., 'Run': 420.}.get(name, 0.)}
    clips['Kick'].update(hit_window=[.2, .4], strike_bone='foot_R', reach_cm=60.)
    (tmp_path / 'textures/T_FoxHunter_body.png').write_bytes(PNG)
    config = {'source_sha256': 'abc', 'mesh': 'fbx/FoxHunter.fbx', 'bones': {'root': 'root', 'pelvis': 'pelvis', 'hips': 'pelvis'},
              'rest_bones_cm': {'pelvis': [0, 0, 90]}, 'clips': clips, 'capsule': {'radius_cm': 26, 'half_height_cm': 86.},
              'sole_cm': 2., 'materials': {name: {'texture': 'textures/T_FoxHunter_body.png', 'two_sided': two, 'roughness': .8,
                                                  'metallic': 0., 'specular': .5, 'base_color': [1, 1, 1, 1]}
                                           for name, two in (('M_FoxHunter_Body', False), ('M_FoxHunter_Cloth', True))}}
    (tmp_path / 'export.json').write_text(json.dumps(config))
    return NS(root=tmp_path, config=config, args=(tmp_path / 'export.json', tmp_path / 'fbx', tmp_path / 'textures', ROOT / units.MANIFEST))


def test_projection_members_are_each_owner_narrow_view(export, tmp_path):
    value = members.members(*export.args)[0]
    assert list(value['clips']) == list(MANIFEST['clips']) and value['clips']['Kick']['fbx'] == b'Kick'
    assert value['clips']['Kick']['strike_bone'] == 'foot_R'
    assert list(value['images']) == ['T_FoxHunter_body'] and value['images']['T_FoxHunter_body']['image'] == PNG
    assert value['materials']['M_FoxHunter_Cloth'] == {'name': 'M_FoxHunter_Cloth', 'texture': 'T_FoxHunter_body', 'two_sided': True,
                                                       'roughness': .8, 'metallic': 0., 'specular': .5}
    members.project(*export.args, tmp_path / 'out', 'clips')
    manifest = emit(tmp_path / 'out', tmp_path / 'files', parent='FoxHunter_clips', extensions=['.json'])
    assert len(manifest['pieces']) == 15
    selected = tmp_path / 'selected'; selected.mkdir()
    (selected / 'Kick.json').write_bytes((tmp_path / 'out/Kick.json').read_bytes())
    members.select(selected, tmp_path / 'member', tmp_path / 'meta', 'Kick')
    assert (tmp_path / 'member/Kick.fbx').read_bytes() == b'Kick'
    assert json.loads((tmp_path / 'member/export.json').read_text())['primary'] == 'Kick.fbx'
    assert json.loads((tmp_path / 'meta/meta.json').read_text())['hit_window'] == [.2, .4]
    members.body(*export.args, tmp_path / 'body/member', tmp_path / 'body/facts')
    facts = json.loads((tmp_path / 'body/facts/facts.json').read_text())
    assert facts['bones'] == ['pelvis', 'root'] and facts['speeds'] == {'Idle': 0., 'Creep': 90., 'Run': 420.}
    assert facts['materials'] == ['M_FoxHunter_Body', 'M_FoxHunter_Cloth']
    assert (tmp_path / 'body/member/FoxHunter.fbx').read_bytes() == b'mesh'


@pytest.mark.parametrize('damage', ['missing', 'rate', 'texture'])
def test_projection_refuses_sources_that_differ(export, damage):
    config = deepcopy(export.config)
    if damage == 'missing':
        del config['clips']['Jump']
    elif damage == 'rate':
        config['clips']['Run']['sample_rate'] = 60
    else:
        config['materials']['M_FoxHunter_Body']['texture'] = None
    (export.root / 'export.json').write_text(json.dumps(config))
    with pytest.raises(ValueError):
        members.members(*export.args)


# ---- bodies ---------------------------------------------------------------------------------------------------------

def test_material_body_is_the_original_loop_without_its_texture_import():
    module = body.material_body((ROOT / units.ORIGINAL).read_text())
    source = ast.unparse(module)
    assert module.body[0].name == 'asset' and 'AssetImportTask' not in source and 'import_asset_tasks' not in source
    assert "sample.set_editor_property('texture', texture)" in source and "materials[name] = mat" in source
    with pytest.raises(ValueError):
        body.material_body('for name, cfg in CONFIG["materials"].items():\n    pass\n')


class Asset:
    def __init__(self, path, **props): self.path, self.props = path, dict(props)
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[1]
    def get_editor_property(self, key): return self.props[key]
    def set_editor_property(self, key, value): self.props[key] = value
class Texture2D(Asset): pass
class Skeleton(Asset): pass
class AnimSequence(Asset): pass
class Material(Asset): pass


class Anything:
    """MaterialEditingLibrary and expression stand-ins: every call succeeds."""
    def __getattr__(self, name): return Anything()
    def __call__(self, *args, **kwargs): return Anything()


@pytest.fixture
def editor(tmp_path):
    assets, saves = {}, []
    def duplicate(source, destination):
        assets[destination] = type(assets[source])(destination, **assets[source].props); return assets[destination]
    def create(name, folder, cls, factory):
        assets[f'{folder}/{name}'] = Material(f'{folder}/{name}'); return assets[f'{folder}/{name}']
    library = NS(load_asset=lambda p: assets.get(p), does_asset_exist=lambda p: p in assets, duplicate_asset=duplicate,
                 save_loaded_asset=lambda a, *_: saves.append(a.path) or True)
    unreal = NS(EditorAssetLibrary=library, Texture2D=Texture2D, Skeleton=Skeleton, AnimSequence=AnimSequence, Material=Material,
                MaterialFactoryNew=lambda: None, MaterialEditingLibrary=Anything(),
                AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=create)),
                RootMotionRootLock=NS(REF_POSE='ref'), **{n: Anything() for n in (
                    'MaterialExpressionTextureSample', 'MaterialExpressionMultiply', 'MaterialExpressionScalarParameter',
                    'MaterialExpressionConstant3Vector', 'MaterialExpressionAdd', 'MaterialExpressionNoise', 'MaterialExpressionSubtract',
                    'MaterialExpressionOneMinus', 'MaterialExpressionSaturate', 'MaterialExpressionConstant', 'LinearColor',
                    'MaterialProperty', 'BlendMode')})
    job = tmp_path / 'job'
    (job / units.ORIGINAL).parent.mkdir(parents=True)
    (job / units.ORIGINAL).write_bytes((ROOT / units.ORIGINAL).read_bytes())
    return NS(assets=assets, saves=saves, unreal=unreal, job=job)


def context(editor, outputs, inputs, packages, params, data=()):
    roots = {}
    for slot, value in inputs.items():
        path = editor.job / 'inputs' / slot
        path.mkdir(parents=True, exist_ok=True)
        if value is not None:
            (path / value[0]).write_text(json.dumps(value[1]))
        roots[slot] = str(path)
    return NS(outputs=outputs, inputs=roots, packages=packages, params=params, job_dir=str(editor.job), data_outputs=data)


def roster(rows):
    return {'derived_items': {'members': [{'piece': piece, 'slot': slot, 'root': 'r'} for piece, slot in rows.items()]}}


def test_material_runs_the_original_loop_on_its_declared_texture(editor):
    editor.assets['/Game/FoxHunter/Textures/T_FoxHunter_body'] = Texture2D('/Game/FoxHunter/Textures/T_FoxHunter_body')
    meta = {'name': 'M_FoxHunter_Body', 'texture': 'T_FoxHunter_body', 'two_sided': False, 'roughness': .8, 'metallic': 0., 'specular': .5}
    args = {'action': 'material', 'name': 'M_FoxHunter_Body', 'meta': 'meta', 'images': roster({'T_FoxHunter_body': 'image_0'})}
    job = context(editor, {'/Game/FoxHunter/M_FoxHunter_Body': {}}, {'meta': ('meta.json', meta), 'image_0': None},
                  {'image_0': ['/Game/FoxHunter/Textures/T_FoxHunter_body']}, {'args': args, 'settings': []})
    mat = body.material(job, editor.unreal, args)
    assert mat.path == '/Game/FoxHunter/M_FoxHunter_Body' and mat.props['two_sided'] is False
    assert mat.props['used_with_skeletal_mesh'] is True and editor.saves == ['/Game/FoxHunter/M_FoxHunter_Body']
    meta['texture'] = 'T_Other'
    editor.assets.pop('/Game/FoxHunter/M_FoxHunter_Body')
    job = context(editor, {'/Game/FoxHunter/M_FoxHunter_Body': {}}, {'meta': ('meta.json', meta), 'image_0': None},
                  {'image_0': ['/Game/FoxHunter/Textures/T_FoxHunter_body']}, {'args': args, 'settings': []})
    with pytest.raises(ValueError, match='not a declared fox image'):
        body.material(job, editor.unreal, args)


def test_clip_checks_length_and_applies_root_motion_lock_and_compression(editor, monkeypatch):
    skeleton = Skeleton('/Game/FoxHunter/SK_FoxHunter_Skeleton')
    editor.assets.update({skeleton.path: skeleton, units.COMPRESSION: Asset(units.COMPRESSION),
                          '/Game/_Raw/FoxHunter/A_FoxKick': AnimSequence('/Game/_Raw/FoxHunter/A_FoxKick', skeleton=skeleton, sequence_length=1.5)})
    compression = editor.job / units.COMPRESSION_SCRIPT
    compression.write_text('def apply_to(sequence):\n    sequence.set_editor_property("bone_compression_settings", _settings)\n')
    args = {'action': 'clip', 'name': 'Kick', 'meta': 'meta', 'skeleton': 'skeleton', 'compression': 'compression'}
    params = {'op': 'finish', 'kind': 'animation', 'source': 'raw', 'destination': '/Game/FoxHunter/A_FoxKick', 'args': args}
    def job(duration):
        return context(editor, {'/Game/FoxHunter/A_FoxKick': {}},
                       {'meta': ('meta.json', {'name': 'Kick', 'duration': duration, 'root_motion': True}), 'raw': None,
                        'skeleton': None, 'compression': None},
                       {'raw': ['/Game/_Raw/FoxHunter/A_FoxKick'], 'skeleton': [skeleton.path], 'compression': [units.COMPRESSION]}, params)
    with pytest.raises(ValueError, match='length differs'):
        body.clip(job(1.2), editor.unreal, args)
    editor.assets.pop('/Game/FoxHunter/A_FoxKick')
    clip = body.clip(job(1.5), editor.unreal, args)
    assert clip.props['enable_root_motion'] is True and clip.props['root_motion_root_lock'] == 'ref'
    assert clip.props['bone_compression_settings'] is editor.assets[units.COMPRESSION]


def test_record_owns_only_its_report(editor):
    job = context(editor, {'/Game/FoxHunter/X': {}}, {}, {}, {'args': {'action': 'record'}}, data=('data/unreal_import.json',))
    with pytest.raises(ValueError, match='only its report'):
        body.record(job, editor.unreal, {'action': 'record'})
