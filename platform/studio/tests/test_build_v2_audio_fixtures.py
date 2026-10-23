"""H4b: the audio source fixtures are read by stdlib wave and match their hand-written samples.

These are source fixtures for the later audio import work (D4f and H4). This test proves only the
bytes, the WAV header and the integer samples; native import, cook and runtime stay out of scope.
"""
import hashlib
import json
from array import array
from pathlib import Path
import wave


AUDIO = Path(__file__).resolve().parents[3]/'platform/build-v2/fixtures/audio'
MANIFEST = json.loads((AUDIO/'manifest.json').read_text())
FORMAT = MANIFEST['format']
BASE = MANIFEST['base']
VARIANT = MANIFEST['variant']
CHANGED = VARIANT['changed_segment']


def expand(segments):
    """Every expected sample, taken from the manifest's integer segments only."""
    samples = []
    for segment in segments:
        assert segment['start_frame'] == len(samples), 'segments must be contiguous'
        values = segment['values']
        samples.extend(values[index % len(values)] for index in range(segment['frames']))
    return samples


def read(name):
    path = AUDIO/name
    with wave.open(str(path), 'rb') as handle:
        header = {
            'channels': handle.getnchannels(),
            'bits_per_sample': 8*handle.getsampwidth(),
            'sample_rate_hz': handle.getframerate(),
            'frame_count': handle.getnframes(),
            'compression': handle.getcomptype(),
        }
        frames = handle.readframes(handle.getnframes())
    return header, list(array('h', frames))


def expected_variant(base_samples):
    samples = list(base_samples)
    samples[CHANGED['start_frame']:CHANGED['start_frame'] + CHANGED['frames']] = [
        CHANGED['values'][index % len(CHANGED['values'])] for index in range(CHANGED['frames'])
    ]
    return samples


def test_header_and_checksums_match_the_manifest():
    assert FORMAT == {
        'container': 'wav',
        'encoding': 'pcm_s16le',
        'sample_rate_hz': 8000,
        'channels': 1,
        'bits_per_sample': 16,
        'frame_count': 800,
        'duration_ms': 100,
    }
    for name in (BASE, VARIANT):
        payload = (AUDIO/name['file']).read_bytes()
        assert len(payload) == name['byte_size']
        assert hashlib.sha256(payload).hexdigest() == name['sha256']
        header, samples = read(name['file'])
        assert header == {
            'channels': FORMAT['channels'],
            'bits_per_sample': FORMAT['bits_per_sample'],
            'sample_rate_hz': FORMAT['sample_rate_hz'],
            'frame_count': FORMAT['frame_count'],
            'compression': 'NONE',
        }
        assert len(samples) == FORMAT['frame_count']
        assert 1000*FORMAT['frame_count'] == FORMAT['sample_rate_hz']*FORMAT['duration_ms']


def test_base_samples_match_every_hand_written_segment():
    base = expand(BASE['segments'])
    assert len(base) == FORMAT['frame_count']
    assert base[:4] == [1000, -1000, 1000, -1000]
    assert base[396:404] == [8000, -8000, 8000, -8000, 250, -250, 250, -250]
    assert base[704:710] == [20000, -20000, 20000, -20000, 20000, -20000]
    assert base[799] == -20000
    assert any(base)

    _, actual = read(BASE['file'])
    assert actual == base


def test_variant_samples_match_the_base_plus_the_changed_segment():
    base = expand(BASE['segments'])
    variant = expected_variant(base)
    start, count = CHANGED['start_frame'], CHANGED['frames']
    assert (start, count, CHANGED['values']) == (400, 40, [12000, -12000, 6000, -6000])
    assert variant[start:start + 4] == [12000, -12000, 6000, -6000]
    assert variant[start + count - 1] == -6000

    _, actual = read(VARIANT['file'])
    assert actual == variant


def test_only_the_declared_segment_differs_between_the_two_files():
    _, base = read(BASE['file'])
    _, variant = read(VARIANT['file'])
    start, count = CHANGED['start_frame'], CHANGED['frames']

    assert base[:start] == variant[:start]
    assert base[start + count:] == variant[start + count:]
    for index in range(start, start + count):
        assert base[index] != variant[index], index
    assert sum(1 for left, right in zip(base, variant) if left != right) == count
