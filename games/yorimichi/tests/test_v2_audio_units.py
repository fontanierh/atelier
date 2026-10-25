"""C3 sound declarations consume original audio producer rows and keyed members only."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path.insert(0, str(GAME))
import v2_audio_units as audio  # noqa: E402
from v2_texture_units import PLUGIN  # noqa: E402


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def rows():
    recipe = load(GAME / 'build.py', 'audio_unit_source_recipe')
    steps = recipe.sound_effect_steps(SimpleNamespace(out=ROOT / 'build/yorimichi'))
    return [row for row in extract(steps, checkout=ROOT, build_root=ROOT / 'build') if row['id'] in audio.ROSTER]


def member(producer, path):
    return {'path': path, 'item': {'unit': producer + '.member', 'item': path}}


def members():
    return {
        'audio.footsteps': {'files': [member('audio.footsteps', 'grass/grass_01.wav'),
                                      member('audio.footsteps', 'wood/wood_02.wav')]},
        'audio.combat': {'files': [member('audio.combat', 'clash/clash_01.wav'),
                                   member('audio.combat', 'ambience/ambience_countryside_01.wav')]},
        'audio.skate': {'loops': ['roll', 'roll_wood'], 'files': [member('audio.skate', 'roll/roll_01.wav'),
                                                                  member('audio.skate', 'pop/pop_01.wav')]},
        'audio.bike': {'loops': ['chain'], 'files': [member('audio.bike', 'chain/chain_01.wav')]},
        'audio.transport': {'loops': [], 'files': [member('audio.transport', 'horn/horn_01.wav')]},
        'audio.kart': {'loops': ['engine'], 'files': [member('audio.kart', 'engine/engine_01.wav')]},
    }


def test_actual_fixed_roster_refuses_without_keyed_generated_membership(rows):
    assert sorted(row['id'] for row in rows) == sorted(audio.ROSTER)
    with pytest.raises(audio.DynamicMembership, match='audio.bike, audio.combat, audio.footsteps'):
        audio.audio_units(rows, checkout=ROOT)


def test_keyed_members_become_store_raw_and_checkout_finish_units(rows):
    result = audio.audio_units(rows, checkout=ROOT, members=members())
    by_id = {unit['id']: unit for unit in result['units']}
    assert len(result['units']) == 2 * len(result['packages']) == 18
    for package, ref in result['packages'].items():
        finish = by_id[ref['unit']]
        raw = by_id[finish['inputs'][0]['source']['unit']]
        assert raw['op'] == {'kind': 'unreal.raw_import', 'version': '1'} and 'properties' not in raw['params']
        assert raw['params']['kind'] == finish['params']['kind'] == 'sound'
        assert raw['outputs'][0]['class'] == 'RawSound' and raw['outputs'][0]['destination'] == 'store'
        assert all('install_path' not in file for file in raw['outputs'][0]['files'])
        assert finish['inputs'][0]['source']['item'] == 'raw_sound'
        assert finish['params']['package_sources'] == {'raw': raw['params']['destination']}
        assert finish['outputs'][0]['class'] == 'Sound' and finish['outputs'][0]['destination'] == 'checkout'
        files = finish['outputs'][0]['files']
        assert files[0]['path'] == 'content' + package + '.uasset' and files[0]['required']
        assert files[0]['install_path'] == 'games/yorimichi/unreal/Content' + package.removeprefix('/Game') + '.uasset'
        assert ref == {'unit': finish['id'], 'item': 'sound', 'package': package}
        assert result['staged'][raw['id']] == {'source': 'inputs/source'}
        assert result['staged'][finish['id']] == {'raw': 'inputs/raw'}
    raw = by_id['unreal.sound.raw.footsteps.grass.grass_01']
    assert raw['inputs'][0]['source'] == {'kind': 'item', 'unit': 'audio.footsteps.member', 'item': 'grass/grass_01.wav'}


def test_destinations_and_looping_match_the_original_import_scripts(rows):
    packages = audio.audio_units(rows, checkout=ROOT, members=members())['packages']
    units = {unit['id']: unit for unit in audio.audio_units(rows, checkout=ROOT, members=members())['units']}
    props = {package: units[ref['unit']]['params']['properties'] for package, ref in packages.items()}
    assert props == {
        '/Game/Japan/Audio/Footsteps/grass/grass_01': {'looping': False, 'streaming': False},
        '/Game/Japan/Audio/Footsteps/wood/wood_02': {'looping': False, 'streaming': False},
        '/Game/Audio/Combat/clash_01': {'looping': False},
        '/Game/Audio/Combat/ambience_countryside_01': {'looping': True},
        '/Game/Audio/Skate/roll_01': {'looping': True},
        '/Game/Audio/Skate/pop_01': {'looping': False},
        '/Game/Audio/Bike/chain_01': {'looping': True},
        '/Game/Audio/Transport/horn_01': {'looping': False},
        '/Game/Audio/Driving/engine_01': {'looping': True}}


def test_unrepresentable_footstep_library_and_music_are_reported_gaps(rows):
    gaps = audio.audio_units(rows, checkout=ROOT, members=members())['gaps']
    assert [gap['package'] for gap in gaps] == ['/Game/Japan/Audio/A_Footstep', '/Game/Japan/Audio/DA_Footsteps',
                                                '/Game/Audio/Music']


@pytest.mark.parametrize('change', ['product', 'optional', 'output', 'command', 'args', 'duplicate'])
def test_wrong_source_shape_refuses(rows, change):
    selected = deepcopy(rows)
    row = selected[0]
    if change == 'product': row['products'][0]['paths'] = ['build/yorimichi/audio/other']
    elif change == 'optional': row['products'][0]['optional_paths'] = ['x.wav']
    elif change == 'output': row['outputs'].append('another.json')
    elif change == 'command': row['commands'][0]['script'] = {'path': 'other.py'}
    elif change == 'args': row['commands'][0]['args'] = ['--extra']
    elif change == 'duplicate': selected.append(deepcopy(row))
    with pytest.raises(audio.Unsupported):
        audio.audio_units(selected, checkout=ROOT, members=members())


@pytest.mark.parametrize('change', ['preview', 'nested', 'absolute', 'suffix', 'item', 'loops', 'empty', 'unselected'])
def test_wrong_member_shape_refuses(rows, change):
    roster = members()
    files = roster['audio.combat']['files']
    if change == 'preview': files[0]['path'] = 'preview/clash.wav'
    elif change == 'nested': files[0]['path'] = 'a/b/c.wav'
    elif change == 'absolute': files[0]['path'] = '/tmp/c.wav'
    elif change == 'suffix': files[0]['path'] = 'clash/clash_01.ogg'
    elif change == 'item': files[0]['item'] = {'unit': 'x'}
    elif change == 'loops': roster['audio.combat']['loops'] = ['clash']
    elif change == 'empty': roster['audio.combat']['files'] = []
    elif change == 'unselected': roster['audio.music'] = {'files': []}
    with pytest.raises(audio.Unsupported):
        audio.audio_units(rows, checkout=ROOT, members=roster)


def test_construction_never_scans_generated_content_or_mutates_rows(rows, monkeypatch):
    before = deepcopy(rows)
    original = Path.rglob
    def scan(path, pattern):
        assert path == ROOT / PLUGIN / 'Source'
        return original(path, pattern)
    def forbidden(*_args, **_kwargs):
        raise AssertionError('generated folder scan')
    monkeypatch.setattr(Path, 'rglob', scan)
    monkeypatch.setattr(Path, 'glob', forbidden)
    monkeypatch.setattr(Path, 'iterdir', forbidden)
    assert len(audio.audio_units(rows, checkout=ROOT, members=members())['units']) == 18
    assert rows == before
