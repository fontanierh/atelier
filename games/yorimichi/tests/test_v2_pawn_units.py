"""Playable pawn declarations replace the character_pawn.py targets from committed definitions only."""
import ast
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

import pytest
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path.insert(0, str(GAME))
import v2_pawn_units as pawns  # noqa: E402

spec = importlib.util.spec_from_file_location('pawn_recipe', GAME / 'build.py')
recipe = importlib.util.module_from_spec(spec); sys.modules['pawn_recipe'] = recipe; spec.loader.exec_module(recipe)
DEFINITION = pawns._definition(ROOT)
PLAYABLE = [c for c in DEFINITION.movers() if c.playable]


@pytest.fixture(scope='module')
def rows():
    return extract(recipe.pawn_steps([]), checkout=ROOT, build_root=ROOT / 'build')


def natives():
    result = {}
    for character in PLAYABLE:
        result[character.adventure['definition']] = {'unit': 'moves.' + character.id, 'item': 'definition'}
        result[f'{pawns.CONTENT}/Data/{character.id}/adventure.json'] = {'unit': 'record.' + character.id, 'item': 'product0'}
    return result


def test_every_original_pawn_target_becomes_blueprint_author_and_registration(rows):
    result = pawns.author_units(rows, checkout=ROOT, natives=natives())
    assert sorted(result['aliases']) == sorted(row['id'] for row in rows) and len(rows) == len(PLAYABLE) == 4
    by_id = {unit['id']: unit for unit in result['units']}
    registrations = {row['id']: row for row in result['rows']}
    for character in PLAYABLE:
        key = character.id.replace('-', '_')
        blueprint_id, registration_id = result['aliases'][f'unreal.{key}_pawn']
        unit = by_id[blueprint_id]
        blueprint = f'{character.unreal_path}/BP_{character.name}'
        assert unit['op'] == {'kind': 'unreal.author', 'version': '1'} and unit['script'] == pawns.SCRIPT
        assert pawns.SCRIPT in unit['code'] and pawns.ORIGINAL not in unit['code']
        output, = unit['outputs']
        assert (output['logical_path'], output['class'], output['destination']) == (blueprint, 'Blueprint', 'checkout')
        assert output['files'][0] == {'path': f'content{blueprint}.uasset', 'required': True,
                                      'install_path': f'{pawns.CONTENT}{blueprint.removeprefix("/Game")}.uasset'}
        assert set(unit['params']) == {'args', 'settings'} and unit['params']['settings'] == []
        assert {item['name']: item['source'] for item in unit['inputs']} == {
            'definition': {'kind': 'item', 'unit': 'moves.' + character.id, 'item': 'definition'},
            'adventure': {'kind': 'item', 'unit': 'record.' + character.id, 'item': 'product0'}}
        assert result['module_requirements'][blueprint_id] == [
            {'name': 'Yorimichi', 'kind': 'Runtime', 'loading_phase': 'Default'}]
        row = registrations[registration_id]
        assert row['needs'] == [blueprint_id]
        assert row['outputs'] == [f'{pawns.CONTENT}/Data/{character.id}/character.json']
        assert {'path': f'{pawns.CONTENT}{blueprint.removeprefix("/Game")}.uasset', 'root': 'checkout',
                'optional': False} in row['inputs']
        command, = row['commands']
        assert command['script'] == {'path': pawns.REGISTRATION}
        record = json.loads(command['args'][1])
        assert record == {'name': character.toml['display_name'], 'id': character.id, 'class': character.pawn,
                          'definition': pawns.object_path(character.adventure['definition']),
                          'build_step': f'unreal.{key}_pawn', 'default': bool(character.game['default']),
                          'aliases': list(character.game['aliases'])}


def test_values_mirror_the_original_script_field_for_field():
    tree = ast.parse((ROOT / pawns.ORIGINAL).read_text())
    assigned = {node.targets[0].id: node.value for node in tree.body
                if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
    original_defaults = [key.value for key in assigned['DEFAULTS'].keys]
    original_components = {key.value: [k.value for k in value.keys]
                           for key, value in zip(assigned['COMPONENTS'].keys, assigned['COMPONENTS'].values)}
    assert ast.literal_eval(assigned['SOLE']) == pawns.SOLE
    record = [node for node in tree.body if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') == 'record']
    original_record = [key.value for key in record[0].value.keys]
    for character in PLAYABLE:
        blueprint, defaults, components, values = pawns.values(character)
        assert list(defaults) == original_defaults
        assert {k: list(v) for k, v in components.items()} == original_components
        assert list(values) == original_record
        assert components['mesh']['relative_location']['args'][2] == -(float(character.game['half_height']) + .65)
    modori = pawns.values(DEFINITION.load('modori'))[1]
    assert (modori['cloth_teleport_distance'], modori['cloth_teleport_rotation']) == (150.0, 60.0)
    cairo = pawns.values(DEFINITION.load('cairo'))[1]
    assert cairo['hair_spring_morphs'] == ['head_Hair_fore', 'head_Hair_side'] and cairo['cloth_teleport_distance'] == 0.0


def test_move_set_dependencies_are_staged_transitively(rows):
    supplied = natives()
    paul = DEFINITION.load('paul')
    supplied[paul.adventure['definition']]['dependencies'] = ['/Game/Paul/SK_Paul']
    supplied['/Game/Paul/SK_Paul'] = {'unit': 'mesh.paul', 'item': 'mesh', 'dependencies': ['/Game/Paul/SKEL_Paul']}
    supplied['/Game/Paul/SKEL_Paul'] = {'unit': 'skeleton.paul', 'item': 'skeleton'}
    result = pawns.author_units(rows, checkout=ROOT, natives=supplied)
    unit = next(u for u in result['units'] if u['id'] == 'unreal.paul_pawn.blueprint')
    assert {item['name']: item['source']['unit'] for item in unit['inputs']} == {
        'definition': 'moves.paul', 'adventure': 'record.paul',
        'native_Paul_SK_Paul': 'mesh.paul', 'native_Paul_SKEL_Paul': 'skeleton.paul'}
    assert result['staged_inputs'][unit['id']]['native_Paul_SKEL_Paul'] == 'inputs/native_Paul_SKEL_Paul'
    del supplied['/Game/Paul/SKEL_Paul']
    with pytest.raises(pawns.Unsupported, match='SKEL_Paul'):
        pawns.author_units(rows, checkout=ROOT, natives=supplied)


def test_explicit_record_root_binding_is_passed_through(rows):
    supplied = natives()
    key = f'{pawns.CONTENT}/Data/nox/adventure.json'
    supplied[key]['root'] = {'archive_member': 'outputs/0.tree.tar', 'name': 'adventure.json'}
    unit = next(u for u in pawns.author_units(rows, checkout=ROOT, natives=supplied)['units']
                if u['id'] == 'unreal.nox_pawn.blueprint')
    assert unit['params']['input_roots'] == {'adventure': {'archive_member': 'outputs/0.tree.tar', 'name': 'adventure.json'}}


@pytest.mark.parametrize('change', ['definition', 'record', 'script', 'env', 'outputs', 'missing', 'extra'])
def test_missing_natives_or_reshaped_targets_refuse(rows, change):
    selected, supplied = deepcopy(rows), natives()
    if change == 'definition': del supplied['/Game/Nox/DA_Nox']
    elif change == 'record': del supplied[f'{pawns.CONTENT}/Data/nox/adventure.json']
    elif change == 'script': selected[0]['commands'][0]['script'] = {'path': 'other.py'}
    elif change == 'env': selected[0]['commands'][0]['env'] = [['CHARACTER', 'someone']]
    elif change == 'outputs': selected[0]['outputs'].append('games/yorimichi/unreal/Content/Other.uasset')
    elif change == 'missing': del selected[0]
    elif change == 'extra':
        extra = deepcopy(selected[0]); extra['id'] = 'unreal.ghost_pawn'; selected.append(extra)
    with pytest.raises(pawns.Unsupported):
        pawns.author_units(selected, checkout=ROOT, natives=supplied)


def test_registration_row_consumes_the_produced_blueprint_item(rows):
    from atelier.build_v2 import recipe_compiler
    result = pawns.author_units(rows, checkout=ROOT, natives=natives())
    unit = deepcopy(next(u for u in result['units'] if u['id'] == 'unreal.cairo_pawn.blueprint'))
    unit['inputs'] = []
    target = recipe_compiler.compile_rows(
        [row for row in result['rows'] if row['id'] == 'unreal.cairo_pawn.registration'], project='yorimichi',
        targets=('unreal.cairo_pawn.registration',), checkout=ROOT,
        native={'units': [unit], 'staged_inputs': {unit['id']: {}}, 'content_slots': {}, 'aliases': {}})
    registration = next(u for u in target.declaration['units'] if u['id'] == 'unreal.cairo_pawn.registration')
    assert registration['op']['kind'] == 'recipe.python'
    assert registration['inputs'][0]['source'] == {'kind': 'item', 'unit': 'unreal.cairo_pawn.blueprint', 'item': 'blueprint'}


def test_construction_never_scans_generated_content(rows, monkeypatch):
    original = Path.rglob
    def scan(path, pattern):
        assert 'Content' not in path.parts
        return original(path, pattern)
    monkeypatch.setattr(Path, 'rglob', scan)
    monkeypatch.setattr(Path, 'iterdir', lambda *_: (_ for _ in ()).throw(AssertionError('folder scan')))
    assert len(pawns.author_units(rows, checkout=ROOT, natives=natives())['units']) == 4
