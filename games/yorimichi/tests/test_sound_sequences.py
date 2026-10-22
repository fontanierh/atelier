"""Candidate identity, pinned audio profile and interrupted publication."""
import importlib.util
import json
from pathlib import Path
import shutil
import wave
from unittest.mock import patch

import numpy as np
import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'tools/render_sound_sequences.py'
spec = importlib.util.spec_from_file_location('sound_sequences', SOURCE)
sequences = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sequences)


@pytest.fixture
def prepared(tmp_path):
    (tmp_path / 'samples').mkdir()
    clips = []
    for number, cue in enumerate(('footstep.concrete', 'skate.roll.concrete', 'skate.skid.concrete', 'skate.land.concrete'), 1):
        path = tmp_path / 'samples' / f'sample-{number:04d}.wav'
        frames = 12000
        samples = .2 * np.sin(np.arange(frames) * 2 * np.pi * (180 + number * 70) / 48000)
        with wave.open(str(path), 'wb') as handle:
            handle.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
            handle.writeframes((samples * 32767).astype('<i2').tobytes())
        clips.append(dict(id=f'sample-{number:04d}', file=f'samples/{path.name}', status='ready', cue=cue,
                          surface='concrete', loop=cue.startswith(('skate.roll.', 'skate.skid.')),
                          audio=dict(sha256=sequences.digest(path), frames=frames)))
    (tmp_path / 'prepared.json').write_text(json.dumps(dict(clips=clips)))
    return tmp_path


def test_contacts_alternate_and_render_reproducibly_without_clipping(prepared):
    pools, _, _ = sequences.prepared_sources(prepared)
    walk, events, description = sequences.render('walk', 'concrete', pools, 41)
    repeat, again, _ = sequences.render('walk', 'concrete', pools, 41)
    assert np.array_equal(walk, repeat) and events == again
    assert [event['side'] for event in events] == [i % 2 for i in range(len(events))]
    assert np.allclose(np.diff([event['time'] for event in events]), .5)
    assert len(events) == 16
    assert np.isclose(8 + events[0]['time'] - events[-1]['time'], .5)
    assert 'approximation' in description
    assert len(walk) == 8 * 48000 and 0 < np.max(np.abs(walk)) < 1
    _, run, _ = sequences.render('run', 'concrete', pools, 41)
    assert len(run) == 24
    assert np.isclose(8 + run[0]['time'] - run[-1]['time'], 1 / 3, atol=1.e-6)
    assert all(.88 <= event['gain'] <= 1 for event in run)
    assert all(.9964 <= event['pitch'] <= 1.1236 for event in run)


def test_runtime_binding_and_speed_contact_profile():
    assert sequences.runtime_identity() == sequences.RUNTIME
    assert sequences.skate_gain_pitch(0) == (.0, .75)
    assert sequences.skate_gain_pitch(4.5) == (.85, .9525)
    assert sequences.skate_gain_pitch(8, True) == (.9, 1.2)


def test_footstep_bank_profile_revalidation_witness():
    game = SOURCE.parents[1]
    witness = json.loads((game / 'assets/audio/profile/footstep-bank-revalidation.json').read_text())
    assert witness['version'] == 1
    assert witness['before_sha256'] == '26e57e1a9589b2d73521ea3b7e3cdcf9fad3322aa0f4a753686f3f0f86e36e80'
    follow = json.loads((game / 'assets/audio/profile/menu-ready-revalidation.json').read_text())
    assert witness['after_sha256'] == next(row['before_sha256'] for row in follow['sources'] if row['source'] == witness['source'])
    text = (sequences.REPO / witness['source']).read_text()
    assert set(witness['unchanged_function_bodies']) == {'SurfaceAt', 'Plant', 'Land', 'TickComponent'}
    for name, expected in witness['unchanged_function_bodies'].items():
        start = text.index('{', text.index('UJapanFootstepComponent::' + name + '('))
        depth = 0
        for end in range(start, len(text)):
            depth += (text[end] == '{') - (text[end] == '}')
            if depth == 0:
                break
        assert depth == 0
        assert sequences.hashlib.sha256(text[start:end + 1].encode()).hexdigest() == expected


def _body_digest(text, owner, name):
    start = text.index('{', text.index(owner + '::' + name + '('))
    depth = 0
    for end in range(start, len(text)):
        depth += (text[end] == '{') - (text[end] == '}')
        if depth == 0:
            break
    assert depth == 0
    return sequences.hashlib.sha256(text[start:end + 1].encode()).hexdigest()


def test_ready_notifications_preserve_exact_contact_and_skate_profile_bodies():
    game = SOURCE.parents[1]
    witness = json.loads((game / 'assets/audio/profile/menu-ready-revalidation.json').read_text())
    assert witness['version'] == 1 and witness['parent'] == '60e953aa664867713d23009e4a2a8e2af2d78f2d'
    assert len(witness['sources']) == 2
    follow = json.loads((game / 'assets/audio/profile/footstep-preferences-revalidation.json').read_text())
    assert follow['version'] == 1
    assert follow['defaults'] == {'soften_footsteps': False, 'footstep_volume': 1.0}
    assert set(follow['changed_function_bodies']) == {'Play'}
    later = {row['source']: row for row in json.loads(
        (game / 'assets/audio/profile/skate-preferences-revalidation.json').read_text())['sources']}
    original = {row['source']: row for row in json.loads(
        (game / 'assets/audio/profile/original-only-revalidation.json').read_text())['sources']}
    cache = {row['source']: row for row in json.loads(
        (game / 'assets/audio/profile/foliage-cache-revalidation.json').read_text())['sources']}
    for row in witness['sources']:
        # Each later witness starts exactly where the previous one ended.
        chain = [row] + ([follow] if row['source'] == follow['source'] else []) + [later[row['source']]]
        chain += [original[row['source']]] if row['source'] in original else []
        chain += [cache[row['source']]] if row['source'] in cache else []
        bodies = dict(row['unchanged_function_bodies'])
        for previous, record in zip(chain, chain[1:]):
            assert previous['after_sha256'] == record['before_sha256'] and previous['owner'] == record['owner']
            for name, change in record['changed_function_bodies'].items():
                if name in bodies:
                    assert bodies[name] == change['before_sha256']
                bodies[name] = change['after_sha256']
            for name, value in record['unchanged_function_bodies'].items():
                assert bodies.setdefault(name, value) == value
        path = sequences.REPO / row['source']
        assert chain[-1]['after_sha256'] == sequences.RUNTIME[row['source']] == sequences.digest(path)
        text = path.read_text()
        for name, expected in bodies.items():
            assert _body_digest(text, row['owner'], name) == expected


def test_original_only_revalidation_witness():
    """Removing the alternative banks changes only DrawStep and Play; every other footstep body is byte-identical."""
    game = SOURCE.parents[1]
    witness = json.loads((game / 'assets/audio/profile/original-only-revalidation.json').read_text())
    assert witness['version'] == 1
    (row,) = witness['sources']
    assert Path(row['source']).name == 'JapanFootsteps.cpp' and row['owner'] == 'UJapanFootstepComponent'
    assert set(row['changed_function_bodies']) == {'DrawStep', 'Play'}
    assert set(row['unchanged_function_bodies']) == {'SurfaceAt', 'Plant', 'Land', 'TickComponent', 'Hoof',
                                                     'ApplyVoicePreferences'}
    path = sequences.REPO / row['source']
    assert row['after_sha256'] == sequences.RUNTIME[row['source']] == sequences.digest(path)
    text = path.read_text()
    bodies = dict(row['unchanged_function_bodies'])
    bodies.update({name: value['after_sha256'] for name, value in row['changed_function_bodies'].items()})
    for name, expected in bodies.items():
        assert _body_digest(text, row['owner'], name) == expected


def test_skate_preferences_revalidation_witness():
    game = SOURCE.parents[1]
    witness = json.loads((game / 'assets/audio/profile/skate-preferences-revalidation.json').read_text())
    assert witness['version'] == 1
    assert witness['defaults'] == {'soften_skate': False, 'skate_volume': 1.0}
    assert {Path(row['source']).name for row in witness['sources']} == {'SkateComponent.cpp', 'SkateRuntime.cpp', 'JapanFootsteps.cpp'}
    # A later witness takes over where this one ended (the chain test above follows it to the current source).
    later = {row['source']: row for row in json.loads(
        (game / 'assets/audio/profile/original-only-revalidation.json').read_text())['sources']}
    later.update({row['source']: row for row in json.loads(
        (game / 'assets/audio/profile/foliage-cache-revalidation.json').read_text())['sources']})
    for row in witness['sources']:
        if row['source'] in later:
            assert row['after_sha256'] == later[row['source']]['before_sha256']
            continue
        path = sequences.REPO / row['source']
        assert row['after_sha256'] == sequences.RUNTIME[row['source']] == sequences.digest(path)
        text = path.read_text()
        bodies = {name: value for name, value in row['unchanged_function_bodies'].items()}
        bodies.update({name: value['after_sha256'] for name, value in row['changed_function_bodies'].items()})
        for name, expected in bodies.items():
            assert _body_digest(text, row['owner'], name) == expected


def test_skate_volume_reaches_the_main_menu_and_phone():
    game = Path(__file__).resolve().parents[1]
    menu = (game / 'unreal/Source/Yorimichi/JapanPreferences.cpp').read_text(encoding='utf-8')
    # the Skate feel page owns its knobs by membership; a skate_ prefix filter hid the audio slider
    assert 'StartsWith(TEXT("skate_"))' not in menu
    assert 'if (IsSkateFeelKey(Values[I].Key)) continue;' in menu
    phone = (game / 'phone/settings.js').read_text(encoding='utf-8')
    assert "['Audio',['volume','music','music_volume','soften_footsteps','footstep_volume','soften_skate','skate_volume']]" in phone


def test_missing_surface_or_modified_candidate_fails(prepared):
    pools, _, _ = sequences.prepared_sources(prepared)
    with pytest.raises(ValueError, match='Missing surface'):
        sequences.render('walk', 'wood', pools, 1)
    with pytest.raises(ValueError, match='Incomplete skate'):
        sequences.plans({'skate.roll.wood': pools['skate.roll.concrete']})
    path = next((prepared / 'samples').iterdir())
    path.write_bytes(path.read_bytes()[:-2] + b'\0\0')
    with pytest.raises(ValueError, match='checksum'):
        sequences.prepared_sources(prepared)
    assert not (prepared / 'sequences.json').exists()


def test_interruption_changed_source_preserves_old_bank_and_manifest(prepared, tmp_path):
    encoder = prepared / 'encoder'; encoder.write_bytes(b'fixture encoder')
    def encode(samples, path):
        path.write_bytes(b'fixture encoded:' + sequences.hashlib.sha256(samples.tobytes()).digest())
        return dict(sha256=sequences.digest(path), bytes=path.stat().st_size, seconds=8, decoded_rms=.1)
    with patch.object(sequences.shutil, 'which', return_value=str(encoder)), patch.object(
            sequences.subprocess, 'check_output', return_value='fixture version'), patch.object(sequences, 'encode', side_effect=encode):
        old = sequences.build(prepared)
        manifest = (prepared / 'sequences.json').read_bytes()
        files = {c['file']: (prepared / c['file']).read_bytes() for c in old['clips']}
        doc = json.loads((prepared / 'prepared.json').read_text())
        source = prepared / doc['clips'][0]['file']
        data = bytearray(source.read_bytes()); data[-20:] = b'\0' * 20; source.write_bytes(data)
        doc['clips'][0]['audio']['sha256'] = sequences.digest(source)
        (prepared / 'prepared.json').write_text(json.dumps(doc))
        count = 0
        def interrupt(samples, path):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError('Interrupted publication')
            return encode(samples, path)
        with patch.object(sequences, 'encode', side_effect=interrupt), pytest.raises(RuntimeError, match='Interrupted'):
            sequences.build(prepared)
        assert (prepared / 'sequences.json').read_bytes() == manifest
        assert all((prepared / name).read_bytes() == raw for name, raw in files.items())
        assert len(list((prepared / 'sequences').iterdir())) == 2


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='Local AAC encoder required')
def test_real_aac_duration_signal_and_size_budget(tmp_path):
    samples = .15 * np.sin(np.arange(8 * 48000) * (2 * np.pi * 330 / 48000))
    details = sequences.encode(samples, tmp_path / 'example.m4a')
    assert details['seconds'] == 8
    assert .05 < details['decoded_rms'] < .2
    assert details['bytes'] <= 160 * 1024


def test_foliage_cache_revalidation_preserves_the_sound_runtime_body():
    witness = json.loads((SOURCE.parents[1] / 'assets/audio/profile/foliage-cache-revalidation.json').read_text())
    row, = witness['sources']
    assert witness['version'] == 1 and not row['changed_function_bodies']
    assert row['after_sha256'] == sequences.RUNTIME[row['source']] == sequences.digest(sequences.REPO / row['source'])
    assert _body_digest((sequences.REPO / row['source']).read_text(), row['owner'], 'EndPlay') == row['unchanged_function_bodies']['EndPlay']
