"""Real six-producer declarations project ordinary WAV members, without Unreal."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import wave

import pytest
from atelier.build_v2.recipe_dependencies import extract
from atelier.build_v2.recipe_job import pack_root, prepare_view
from atelier.build_v2.file_groups import emit

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path.insert(0, str(GAME))
import v2_audio_templates as audio  # noqa: E402


@pytest.fixture(scope='module')
def rows():
    spec = importlib.util.spec_from_file_location('audio_template_source', GAME / 'build.py')
    source = importlib.util.module_from_spec(spec); spec.loader.exec_module(source)
    steps = source.sound_effect_steps(SimpleNamespace(out=ROOT / 'build/yorimichi'))
    return [row for row in extract(steps, checkout=ROOT, build_root=ROOT / 'build') if row['id'] in audio.ROSTER]


def test_all_six_actual_producers_have_finite_cue_templates_and_original_loop_settings(rows):
    result = audio.audio_templates(rows, checkout=ROOT)
    assert {unit['inputs'][0]['source']['unit'] for unit in result['units']} == set(audio.ROSTER)
    assert len(result['units']) == len(result['templates']) == len(result['groups']) == 102
    counts = {producer: len(audio.cue_settings(producer, checkout=ROOT)) for producer in audio.ROSTER}
    assert counts == {'audio.footsteps': 7, 'audio.combat': 18, 'audio.skate': 28,
                      'audio.bike': 18, 'audio.transport': 25, 'audio.kart': 6}
    by_id = {unit['id']: unit for unit in result['units']}
    for template in result['templates']:
        producer = by_id[template['producer']]
        family, cue = producer['id'].split('.files.')
        properties = template['followers'][0]['unit']['params']['properties']
        expected = audio.cue_settings(family, checkout=ROOT)[cue]
        assert properties['looping'] is expected
        assert properties.get('streaming') is (False if family == 'audio.footsteps' else None)
        assert template['derive_payload'] is False
        assert template['output_class'] == 'RawSound'
        assert template['params']['destination'] == template['logical_namespace'] + '/$piece'
        follower = template['followers'][0]['unit']
        assert follower['inputs'][0]['source'] == {'kind': 'item', 'unit': '$export', 'item': 'asset'}
        assert follower['outputs'][0]['id'] == 'sound'
        assert follower['outputs'][0]['destination'] == 'checkout'
        assert all('/$piece' in file['path'] for file in template['files'])
        assert all('$piece' in file['install_path'] for file in follower['outputs'][0]['files'])
        assert 'properties' not in template['params'] and 'payload_encoding' not in template['params']
        assert {audio.RECIPE, audio.EMITTER} <= set(producer['code'])
        assert all((ROOT / path).is_file() for path in producer['code'])
        assert producer['params']['recipe']['commands'] == producer['params']['recipe']['outputs'] == []
        assert producer['inputs'][0]['source']['item'] == 'product0'
        assert producer['params']['recipe']['paths'] == {'source': 'inputs/source/products/0-0.tree.tar'}
        assert producer['output_groups'][0]['encoding'] == 'file_set'
    loops = audio.cue_settings('audio.skate', checkout=ROOT)
    assert loops['scrape'] and loops['roll_asphalt'] and not loops['pop_dirt']
    assert audio.cue_settings('audio.combat', checkout=ROOT)['ambience_countryside']
    assert result['aliases'] == {}
    assert {gap['class'] for gap in result['gaps']} == {'SoundAttenuation', 'JapanFootstepSet', 'SoundWave'}


def test_actual_root_archive_prepared_view_projects_exact_temp_wav_members(rows, tmp_path):
    source = tmp_path / 'completed'
    for cue in ('engine', 'impact'):
        (source / cue).mkdir(parents=True)
        for index in (1, 2):
            with wave.open(str(source / cue / f'{cue}_{index:02}.wav'), 'wb') as stream:
                stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(48000)
                stream.writeframes(bytes([index, 0]) * 16)
    (source / 'manifest.json').write_text('{}')
    result = audio.audio_templates(rows, checkout=ROOT)
    unit = next(unit for unit in result['units'] if unit['id'] == 'audio.kart.files.engine')
    job = tmp_path / 'job'; archive = job / 'inputs/source/products/0-0.tree.tar'
    archive.parent.mkdir(parents=True); pack_root(source, archive)
    (job / '.recipe-runtime').mkdir()
    view, protected, writes = prepare_view({'params': unit['params'], 'code': [], 'inputs': [{'path': 'inputs/source'}]}, job)
    assert writes == [] and str(view / 'source') in protected
    group = unit['params']['recipe']['file_group']
    output = job / unit['params']['file_root']
    manifest = emit(view / group['source'], output, parent=group['parent'], extensions=group['extensions'])
    assert manifest['kind'] == 'file_set' and manifest['complete'] is True
    assert [piece['name'] for piece in manifest['pieces']] == ['engine_01', 'engine_02']
    assert json.loads((output / 'plan.json').read_bytes()) == manifest
    for piece in manifest['pieces']:
        assert piece['metadata'] == {}
        assert (output / piece['payload']).read_bytes() == (source / 'engine' / piece['payload']).read_bytes()
    assert not (output / 'impact_01.wav').exists()
    raw = next(template for template in result['templates'] if template['producer'] == unit['id'])
    piece = manifest['pieces'][0]['name']
    assert raw['params']['destination'].replace('$piece', piece) == '/Game/_Raw/Audio/Driving/engine_01'
    assert raw['files'][0]['path'].replace('$piece', piece) == 'content/Game/_Raw/Audio/Driving/engine_01.uasset'


@pytest.mark.parametrize('damage', ['duplicate', 'product', 'command'])
def test_source_shape_refusal_preserves_original_rows(rows, damage):
    changed = deepcopy(rows)
    if damage == 'duplicate': changed.append(deepcopy(changed[0]))
    elif damage == 'product': changed[0]['products'][0]['paths'] = ['build/yorimichi/audio/foreign']
    else: changed[0]['commands'][0]['args'] = ['--foreign']
    with pytest.raises(audio.Unsupported): audio.audio_templates(changed, checkout=ROOT)


def test_no_generated_membership_or_generator_execution(rows, monkeypatch):
    original = Path.read_bytes
    def read(path):
        assert path.is_relative_to(ROOT / 'games/yorimichi/assets/audio')
        return original(path)
    monkeypatch.setattr(Path, 'read_bytes', read)
    assert len(audio.audio_templates(rows, checkout=ROOT)['templates']) == 102


def test_cue_source_policy_unknown_dynamic_role_refuses(tmp_path):
    path = tmp_path / audio.ROSTER['audio.bike'][1]
    path.parent.mkdir(parents=True)
    path.write_text('LOOPS=[]\ndef main():\n report={}\n report[unknown_role]=[]\n')
    with pytest.raises(audio.Unsupported, match='finite literal'):
        audio.cue_settings('audio.bike', checkout=tmp_path)
