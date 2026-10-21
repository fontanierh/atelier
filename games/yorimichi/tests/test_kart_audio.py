"""The driving sound set: every cue the component loads exists, loops wrap, and the engine ladder rises with revs."""
import importlib.util
import json
import wave
from pathlib import Path

import numpy as np
import pytest


SPEC = importlib.util.spec_from_file_location('kart_audio', Path(__file__).resolve().parents[1] / 'assets/audio/kart/make.py')
kart = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(kart)


@pytest.fixture(scope='module')
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp('kart-audio')
    kart.ROOT = out
    kart.OUT = out
    kart.main()
    return out, json.loads((out / 'manifest.json').read_text())


def read(path):
    w = wave.open(str(path))
    assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 48000)
    return np.frombuffer(w.readframes(w.getnframes()), np.int16) / 32768.0


def test_every_cue_the_component_loads_is_built(built):
    out, manifest = built
    assert manifest['loops'] == ['engine', 'tyre', 'skid', 'wind']
    for cue, (variants, _, _) in kart.CUES.items():
        files = sorted(p.name for p in (out / cue).glob('*.wav'))
        assert files == [f'{cue}_{i:02d}.wav' for i in range(1, variants + 1)], cue
        assert all(0.02 < e['seconds'] < 3.5 for e in manifest['cues'][cue])


def test_loops_wrap_without_a_new_seam(built):
    out, manifest = built
    for cue in manifest['loops']:
        for index in range(1, len(manifest['cues'][cue]) + 1):
            x = read(out / cue / f'{cue}_{index:02d}.wav')
            steps = np.abs(np.diff(x))
            assert abs(x[0] - x[-1]) <= steps.max() * 1.05 + 1e-3, (cue, index)


def test_engine_loops_rise_from_idle_to_the_limiter(built):
    out, manifest = built
    brightness = []
    for index in range(1, len(manifest['cues']['engine']) + 1):
        x = read(out / 'engine' / f'engine_{index:02d}.wav')
        brightness.append(centroid(x))
    # Each loop is taken higher up the rev range: the spectrum moves up with it.
    assert all(b > a * 1.08 for a, b in zip(brightness, brightness[1:])), brightness


def centroid(x):
    spectrum = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freq = np.fft.rfftfreq(len(x), 1 / 48000)
    return float((spectrum * freq).sum() / max(spectrum.sum(), 1e-9))
