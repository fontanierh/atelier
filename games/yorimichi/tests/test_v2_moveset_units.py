"""Adventure move-set declarations and bodies: one unit per native asset, keyed clip members, no monolith."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS

import pytest
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path.insert(0, str(GAME))
import v2_moveset_units as movesets  # noqa: E402

spec = importlib.util.spec_from_file_location('moveset_recipe', GAME / 'build.py')
recipe = importlib.util.module_from_spec(spec); sys.modules['moveset_recipe'] = recipe; spec.loader.exec_module(recipe)
spec = importlib.util.spec_from_file_location('moveset_v2', GAME / 'world/moveset_v2.py')
body = importlib.util.module_from_spec(spec); spec.loader.exec_module(body)
DEFINITION = movesets._definition(ROOT)
MOVERS = DEFINITION.movers()
DONOR = MOVERS[0]


@pytest.fixture(scope='module')
def rows():
    return [row for row in extract(recipe.adventure_steps(ROOT / 'build/yorimichi'), checkout=ROOT, build_root=ROOT / 'build')
            if row['id'] != 'unreal.adventure' and row['id'].startswith('unreal.')]


def ref(package):
    return {'unit': 'native.' + package.rsplit('/', 1)[1], 'item': 'asset', 'package': package}


def natives():
    result = {'reference': {'skeleton': ref('/Game/Adventure/SKEL_Reference'), 'glide': ref('/Game/Adventure/A_Glide'),
                            'equipment': [ref('/Game/Adventure/SM_Sword')],
                            'record': {'unit': 'unreal.adventure', 'item': 'output0'},
                            'export': {'unit': 'characters.adventure', 'item': 'output0'}},
              'donor': {f"{DONOR.donor['folder']}/A_{c}": ref(f"{DONOR.donor['folder']}/A_{c}")
                        for c in ('DoubleJump', 'SwordIdle', 'SwordParry', 'SwordParryHit')}}
    for character in MOVERS:
        result[character.id] = {'skeleton': ref(character.adventure['mesh'] + '_Skeleton'),
                                'base': ref(character.adventure['base']),
                                'export': {'unit': f'characters.{character.id}_adventure', 'item': 'output0'}}
    return result


def members():
    result = {}
    for character in MOVERS:
        result[character.id] = [{'name': name, 'kind': 'clip', 'fps': 30, 'frames': 40, 'source': {
            'kind': 'group_member', 'unit': f'characters.{character.id}_adventure', 'group': 'fbx', 'piece': name}}
            for name in ('Idle', 'Walk', 'Glide')]
        if character.id != DONOR.id:
            result[character.id].append({'name': 'DoubleJump', 'kind': 'own', 'fps': 60, 'frames': 50,
                                         'source': {'kind': 'item', 'unit': 'own.' + character.id, 'item': 'DoubleJump'}})
    return result


def build(rows, **change):
    return movesets.moveset_units(rows, checkout=ROOT, natives=change.get('natives', natives()),
                                  members=change.get('members', members()))


def test_actual_targets_refuse_without_keyed_clip_members(rows):
    assert sorted(row['id'] for row in rows) == sorted(f"unreal.{c.id.replace('-', '_')}_adventure" for c in MOVERS)
    assert len(rows) == 5
    with pytest.raises(movesets.DynamicMembership, match='cairo, modori, nox, paul, sword-trainer'):
        movesets.moveset_units(rows, checkout=ROOT, natives=natives())


def test_one_unit_per_native_asset_and_a_shared_compression_owner(rows):
    result = build(rows)
    by_id = {unit['id']: unit for unit in result['units']}
    assert [u['id'] for u in result['units']].count(movesets.COMPRESSION_UNIT) == 1
    compression = by_id[movesets.COMPRESSION_UNIT]
    assert compression['outputs'][0]['class'] == 'AnimBoneCompressionSettings' and compression['inputs'] == []
    paul = DEFINITION.load('paul').adventure
    assert result['aliases']['unreal.paul_adventure'] == tuple(
        [f'unreal.moveset.paul.{step}.{n}' for n in ('Idle', 'Walk', 'Glide', 'DoubleJump') for step in ('raw', 'clip')]
        + [f'unreal.moveset.paul.blend.{t}' for t in ('Locomotion', 'Crouching', 'ArmedLocomotion')]
        + ['unreal.moveset.paul.definition', 'unreal.moveset.paul.record'])
    raw, clip = by_id['unreal.moveset.paul.raw.Walk'], by_id['unreal.moveset.paul.clip.Walk']
    assert raw['params'] == {'op': 'raw_import', 'kind': 'animation', 'source': 'source', 'destination': '/Game/_Raw/Moveset/paul/A_Walk',
                             'skeleton': 'skeleton', 'fbx': {**movesets.FBX, 'custom_sample_rate': 30}}
    assert raw['outputs'][0]['class'] == 'RawAnimation' and raw['outputs'][0]['destination'] == 'store'
    assert raw['inputs'][0]['source'] == {'kind': 'group_member', 'unit': 'characters.paul_adventure', 'group': 'fbx', 'piece': 'Walk'}
    assert clip['op'] == {'kind': 'unreal.finish', 'version': '1'} and clip['script'] == movesets.SCRIPT
    assert clip['outputs'][0]['logical_path'] == f"{paul['dest']}/A_Walk" and clip['outputs'][0]['class'] == 'Animation'
    assert {i['name']: i['source']['unit'] for i in clip['inputs']} == {
        'raw': raw['id'], 'skeleton': 'native.SK_Paul_Skeleton', 'compression': movesets.COMPRESSION_UNIT}
    assert by_id['unreal.moveset.paul.clip.DoubleJump']['params']['args']['fps'] == 60
    blend = by_id['unreal.moveset.paul.blend.Locomotion']
    assert blend['outputs'][0]['class'] == 'BlendSpace1D'
    assert blend['outputs'][0]['logical_path'] == f"{paul['dest']}/BS_PaulAdventureLocomotion"
    assert result['module_requirements'][blend['id']][0]['name'] == 'YorimichiImport'
    definition = by_id['unreal.moveset.paul.definition']
    assert definition['outputs'][0]['class'] == 'AdventureMoveSet' and definition['outputs'][0]['logical_path'] == paul['definition']
    assert result['module_requirements'][definition['id']][0]['name'] == 'Yorimichi'
    names = {i['name']: i['source']['unit'] for i in definition['inputs']}
    assert names['base'] == 'native.' + paul['base'].rsplit('/', 1)[1] and names['own_DoubleJump'] == 'unreal.moveset.paul.clip.DoubleJump'
    assert {names['blend_' + k] for k in ('locomotion', 'crouching', 'armed')} == {
        f'unreal.moveset.paul.blend.{t}' for t in ('Locomotion', 'Crouching', 'ArmedLocomotion')}
    record = by_id['unreal.moveset.paul.record']
    assert record['outputs'] == [{'id': 'record', 'logical_path': '/Game/_Data/paul/adventure', 'class': 'JsonData',
                                  'destination': 'checkout', 'files': [{'path': 'data/adventure.json', 'required': True,
                                  'install_path': 'games/yorimichi/unreal/Content/Data/paul/adventure.json'}]}]
    assert set(record['params']) == {'args', 'settings'}
    # Exactly the keys the pawn family consumes.
    assert result['packages'][paul['definition']]['unit'] == definition['id']
    assert result['packages']['games/yorimichi/unreal/Content/Data/paul/adventure.json'] == {'unit': record['id'], 'item': 'record'}


def test_the_donor_plays_its_own_imported_clips(rows):
    by_id = {unit['id']: unit for unit in build(rows)['units']}
    definition = by_id['unreal.moveset.cairo.definition']
    names = {i['name']: i['source']['unit'] for i in definition['inputs']}
    assert {n for n in names if n.startswith('donor_')} == {'donor_DoubleJump', 'donor_SwordIdle', 'donor_SwordParry', 'donor_SwordParryHit'}
    assert not any(n.startswith('own_') for n in names) and definition['params']['args']['is_donor'] is True
    supplied = members(); supplied['cairo'].append(dict(supplied['paul'][-1]))
    with pytest.raises(movesets.Unsupported, match='donor'):
        build(rows, members=supplied)


def test_native_dependencies_and_data_roots_are_staged(rows):
    supplied = natives()
    supplied['paul']['base']['dependencies'] = [ref('/Game/Paul/SK_Paul'), ref('/Game/Paul/A_PaulWave')]
    supplied['reference']['record']['root'] = {'archive_member': 'outputs/0.tree.tar', 'name': 'reference.json'}
    unit = next(u for u in build(rows, natives=supplied)['units'] if u['id'] == 'unreal.moveset.paul.definition')
    names = {i['name']: i['source']['unit'] for i in unit['inputs']}
    assert names['native_Paul_SK_Paul'] == 'native.SK_Paul' and names['native_Paul_A_PaulWave'] == 'native.A_PaulWave'
    assert unit['params']['input_roots'] == {'roster': {'archive_member': 'outputs/0.tree.tar', 'name': 'reference.json'}}


@pytest.mark.parametrize('change', ['skeleton', 'base_package', 'export', 'reference', 'equipment', 'donor_clip',
                                    'member_shape', 'empty', 'unselected', 'row_script', 'row_outputs'])
def test_missing_producers_or_reshaped_inputs_refuse(rows, change):
    selected, supplied, roster = deepcopy(rows), natives(), members()
    if change == 'skeleton': del supplied['nox']['skeleton']
    elif change == 'base_package': supplied['nox']['base']['package'] = '/Game/Nox/DA_Other'
    elif change == 'export': del supplied['nox']['export']
    elif change == 'reference': del supplied['reference']['glide']
    elif change == 'equipment': supplied['reference']['equipment'] = []
    elif change == 'donor_clip': del supplied['donor']['/Game/Cairo/A_SwordParry']
    elif change == 'member_shape': roster['nox'][0]['fps'] = 30.0
    elif change == 'empty': roster['nox'] = []
    elif change == 'unselected': roster['ghost'] = []
    elif change == 'row_script': selected[0]['commands'][0]['script'] = {'path': 'other.py'}
    elif change == 'row_outputs': selected[0]['outputs'] = []
    with pytest.raises(movesets.Unsupported):
        movesets.moveset_units(selected, checkout=ROOT, natives=supplied, members=roster)


def test_construction_never_scans_generated_content(rows, monkeypatch):
    original = Path.rglob
    def scan(path, pattern):
        assert 'Content' not in path.parts and 'build' not in path.parts
        return original(path, pattern)
    monkeypatch.setattr(Path, 'rglob', scan)
    assert len(build(rows)['units']) == 1 + 5 * (3 * 2 + 3 + 2) + 4 * 2


# ---- bodies ---------------------------------------------------------------------------------------------------------

def test_original_definitions_run_alone_without_the_monolith(tmp_path):
    staged = tmp_path / body.ORIGINAL; staged.parent.mkdir(parents=True)
    staged.write_text((ROOT / body.ORIGINAL).read_text())
    namespace = body.original(NS(job_dir=str(tmp_path)), U=None)
    assert set(body.FUNCTIONS) <= set(namespace)
    assert namespace['add']([1, 2], [3, 4]) == [4, 6] and namespace['cross']([1, 0, 0], [0, 1, 0]) == [0, 0, 1]
    assert 'CHARACTER' not in namespace and 'clips' not in namespace   # no top-level statement ran
    staged.write_text('def add(a, b): return a\n')
    with pytest.raises(ValueError, match='lacks'):
        body.original(NS(job_dir=str(tmp_path)))


class Asset:
    def __init__(self, path, **props):
        self.path, self.props = path, dict(props)
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[1]
    def get_editor_property(self, name): return self.props[name]
    def set_editor_property(self, name, value): self.props[name] = value


class AnimSequence(Asset):
    pass


@pytest.fixture
def editor(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'path', list(sys.path))
    fake_yori = ModuleType('yori')
    fake_yori.OUT = None
    monkeypatch.setitem(sys.modules, 'yori', fake_yori)
    for relative in (body.COMPRESSION_SCRIPT, body.ORIGINAL):
        target = tmp_path / relative; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((ROOT / relative).read_text())
    world = tmp_path / 'games/yorimichi/world'; world.mkdir(parents=True, exist_ok=True)
    (world / 'yori.py').write_text('OUT = None\n')
    assets, saves = {}, []
    def duplicate(source, destination):
        copy = type(assets[source])(destination, **assets[source].props); assets[destination] = copy; return copy
    def save(asset, only_dirty=True):
        saves.append(asset.path); return True
    def create(name, folder, cls, factory):
        asset = cls(folder + '/' + name, codecs=[], error_threshold=None); assets[asset.path] = asset; return asset
    codec = Asset('codec')
    unreal = NS(AnimSequence=AnimSequence, AnimBoneCompressionSettings=Asset, AnimBoneCompressionSettingsFactory=lambda: None,
                EditorAssetLibrary=NS(load_asset=lambda p: assets.get(p.split('.', 1)[0]), does_asset_exist=lambda p: p in assets,
                                      duplicate_asset=duplicate, save_loaded_asset=save, make_directory=lambda p: True),
                AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=create)),
                load_class=lambda outer, path: 'PerTrack', new_object=lambda cls, outer, name: codec)
    codec.get_class = lambda: 'PerTrack'
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    return NS(assets=assets, saves=saves, unreal=unreal, root=tmp_path)


def test_compression_owner_is_made_by_the_original_helper(editor):
    context = NS(job_dir=str(editor.root), inputs={}, packages={}, outputs=[body.COMPRESSION],
                 params={'args': {'action': 'compression'}, 'settings': []})
    settings = body.run(context)
    assert settings.path == body.COMPRESSION and settings.props['error_threshold'] == .0001
    assert body.COMPRESSION in editor.saves
    with pytest.raises(ValueError, match='fresh'):
        body.run(context)


def test_clip_finish_duplicates_and_assigns_the_declared_compression(editor):
    skeleton = Asset('/Game/Paul/SK_Paul_Skeleton')
    settings = Asset(body.COMPRESSION)
    raw = AnimSequence('/Game/_Raw/Moveset/paul/A_Walk', skeleton=skeleton, sequence_length=40 / 30,
                       enable_root_motion=True, bone_compression_settings=None)
    editor.assets.update({raw.path: raw, skeleton.path: skeleton, settings.path: settings})
    destination = '/Game/Paul/Adventure/A_Walk'
    context = NS(job_dir=str(editor.root), inputs={'raw': 'x', 'skeleton': 'x', 'compression': 'x'},
                 packages={'raw': [raw.path], 'skeleton': [skeleton.path], 'compression': [settings.path]}, outputs=[destination],
                 params={'op': 'finish', 'kind': 'animation', 'source': 'raw', 'destination': destination,
                         'args': {'action': 'clip', 'name': 'Walk', 'frames': 40, 'fps': 30, 'skeleton': 'skeleton',
                                  'compression': 'compression'}})
    clip = body.run(context)
    assert clip.path == destination and clip.props['enable_root_motion'] is False
    assert clip.props['bone_compression_settings'] is settings and raw.props['enable_root_motion'] is True
    del editor.assets[destination]
    context.params['args']['frames'] = 41
    with pytest.raises(ValueError, match='length'):
        body.run(context)


def test_record_returns_only_its_json_value(editor, tmp_path, monkeypatch):
    data = tmp_path / 'data'; data.mkdir()
    (data / 'export.json').write_text(json.dumps({'body': 1.1, 'reference_scale': 1.0}))
    ref_export = tmp_path / 'ref'; ref_export.mkdir()
    (ref_export / 'export.json').write_text(json.dumps({'characters': [{'name': 'Reference', 'skate': {'hip': 'Hips'}}]}))
    roster = tmp_path / 'roster'; roster.mkdir()
    (roster / 'reference.json').write_text(json.dumps({'characters': [{'name': 'Reference', 'clips': {'Glide': {'path': '/Game/Adventure/A_Glide.A_Glide'}},
        'moves': {'actions': {'Glide': {'clip': 'Glide', 'speed': 10.0, 'path': [[1.0, 2.0, 3.0, 90]]}},
                  'params': {'SwimHang': 10.0}, 'equipment': {'sword': {'mesh': '/Game/Adventure/SM_Sword'}}}}]}))
    for path in ('/Game/Paul/SK_Paul_Skeleton', '/Game/Adventure/SKEL_Reference', '/Game/Adventure/A_Glide', '/Game/Adventure/SM_Sword'):
        editor.assets[path] = Asset(path)
    for name in ('Glide', 'DoubleJump', 'SwordIdle', 'SwordParry', 'SwordParryHit'):
        editor.assets[f'/Game/Paul/Adventure/A_{name}'] = AnimSequence(f'/Game/Paul/Adventure/A_{name}', sequence_length=1.23456)
    class Rig:
        def __init__(self, skeleton, names, pose=None): self.skeleton = skeleton
        def at(self, role): return [0, 0, 110.0 if self.skeleton.path.endswith('SK_Paul_Skeleton') else 100.0]
    monkeypatch.setattr(body, 'original', lambda context, **globals_: {
        'Rig': Rig, 'equipment': lambda reference, wearer, glide: ({'sword': {'hand': 'hand_R'}}, {'glider': {'grip_miss_cm': [1.0, 2.0]}})})
    editor.unreal.AnimPoseExtensions = NS(get_anim_pose_at_time=lambda clip, t, options: clip)
    editor.unreal.AnimPoseEvaluationOptions = lambda: None
    packages = {'skeleton': ['/Game/Paul/SK_Paul_Skeleton'], 'reference_skeleton': ['/Game/Adventure/SKEL_Reference'],
                'reference_glide': ['/Game/Adventure/A_Glide'], 'equipment_0': ['/Game/Adventure/SM_Sword'],
                'clip_Glide': ['/Game/Paul/Adventure/A_Glide'],
                **{f'own_{n}': [f'/Game/Paul/Adventure/A_{n}'] for n in ('DoubleJump', 'SwordIdle', 'SwordParry', 'SwordParryHit')}}
    inputs = {**{slot: 'x' for slot in packages}, 'export': str(data), 'reference_export': str(ref_export), 'roster': str(roster)}
    donor = {'double_jump': 'DoubleJump', 'gestures': [], 'actions': {a: dict(t) for a, t in DONOR.donor['actions'].items()}}
    context = NS(job_dir=str(tmp_path), inputs=inputs, packages=packages, outputs=[], data_outputs=('data/adventure.json',),
                 params={'settings': [], 'args': {'action': 'record', 'character': 'paul', 'export': 'export',
                         'reference_export': 'reference_export', 'roster': 'roster', 'skeleton': 'skeleton',
                         'reference_skeleton': 'reference_skeleton', 'reference_glide': 'reference_glide',
                         'equipment': ['equipment_0'], 'clips': {'Glide': 'clip_Glide'},
                         'own': {n: f'own_{n}' for n in ('DoubleJump', 'SwordIdle', 'SwordParry', 'SwordParryHit')},
                         'donor': {}, 'fit': {}, 'donor_spec': donor, 'is_donor': False}})
    result = body.run(context)
    record = result['data/adventure.json']
    assert list(result) == ['data/adventure.json'] and list(record) == ['actions', 'params', 'equipment']
    assert record['actions']['Glide'] == {'clip': 'Glide', 'speed': 11.0, 'path': [[1.1, 2.2, 3.3, 90]]}
    assert record['actions']['SwordParry']['length'] == 1.2346 and record['actions']['SwordParry']['guard'] == [[0.0333, 0.3]]
    assert record['params'] == {'SwimHang': 11.0, 'BodyScale': 1.1, 'TwoHandedGuard': 1}
    context.outputs = ['/Game/Paul/Other']
    with pytest.raises(ValueError, match='only its JsonData'):
        body.run(context)


def test_a_scalar_native_member_is_resolved_by_identity_without_guessing_a_future_unit():
    token = {'derived_items': {'root': 'derived/reference', 'templates': [
        {'producer': 'reference.clips', 'group': 'clips', 'unit_prefix': 'reference.clip', 'follower': 1, 'item': 'animation'}]}}
    reference = {'derived': token, 'piece': 'Glide', 'package': '/Game/Adventure/Reference/A_Reference_Glide'}
    declared = movesets._native(reference, 'glide')
    inputs = movesets._Inputs()
    binding = inputs.native('glide', declared)
    assert inputs.items == []
    assert binding['derived_native']['items']['derived_items']['templates'][0]['piece'] == 'Glide'
    assert 'piece' not in token['derived_items']['templates'][0]
    resolved = {'derived_native': {'package': reference['package'], 'items': {'derived_items': {
        'root': 'derived/reference', 'members': [{'piece': 'Glide', 'slot': 'derived_0'}]}}}}
    context = NS(inputs={'derived_0': 'input'}, packages={'derived_0': reference['package']})
    assert body._selected(context, resolved) == reference['package']
    context.packages['derived_0'] = '/Game/Adventure/Other'
    with pytest.raises(ValueError, match='differs'):
        body._selected(context, resolved)
