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
    def encode(samples, path, **kwargs):
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
        def interrupt(samples, path, **kwargs):
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


def test_preflight_keeps_source_pins_and_rejects_changes_before_lazy_read(prepared):
    pools, _, _ = sequences.prepared_sources(prepared)
    samples = [sample for entries in pools.values() for _, sample in entries]
    assert all(isinstance(sample, sequences.PreparedSample) for sample in samples)
    changed = samples[0]
    original = changed.path.read_bytes()
    changed.path.write_bytes(original[:-2] + b'\0\0')
    with pytest.raises(ValueError, match='checksum'):
        changed.load()


def test_oversized_source_refuses_before_decoding(prepared):
    doc = json.loads((prepared / 'prepared.json').read_text())
    clip = doc['clips'][0]
    source = prepared / clip['file']
    with source.open('ab') as handle:
        handle.write(b'\0' * sequences.MAX_SOURCE)
    clip['audio']['sha256'] = sequences.digest(source)
    (prepared / 'prepared.json').write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='checksum/path'):
        sequences.prepared_sources(prepared)
    assert not (prepared / 'sequences.json').exists()


def test_encoder_and_decoder_bound_filters_codecs_and_library_workers(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENBLAS_NUM_THREADS','8')
    monkeypatch.setenv('AUDIO_TEST_MARKER','keep')
    binary=tmp_path/'ffmpeg';binary.write_text('fixture');binary.chmod(0o700)
    monkeypatch.setattr(sequences.shutil,'which',lambda name:str(binary))
    samples = np.full(48000 * 8,.1)
    commands=[]
    def run(command,report,**kwargs):
        command.verify();commands.append(list(command))
        for option in ('-filter_threads','-filter_complex_threads'):
            assert command[command.argv.index(option)+1]=='1'
        assert command[command.argv.index('-protocol_whitelist')+1]=='file'
        assert all(sequences.worker_environment()[name]=='1' for name in sequences.WORKER_ENV)
        assert sequences.worker_environment()['AUDIO_TEST_MARKER']=='keep'
        if len(commands)==1:Path(command[-1]).write_bytes(b'encoded fixture')
        else:Path(command[-1]).write_bytes(np.asarray(samples,dtype='<f4').tobytes())
    monkeypatch.setattr(sequences.ffmpeg_audio,'run',run)
    details=sequences.encode(samples,tmp_path/'fixture.m4a')
    assert len(commands)==2 and details['decoded_frames']==len(samples)
    assert sequences.os.environ['OPENBLAS_NUM_THREADS']=='8'
