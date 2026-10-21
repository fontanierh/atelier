#!/usr/bin/env python3
"""Build the kart's sounds from the recorded sources in recordings/ into build/yorimichi/audio/kart/<cue>/<cue>_NN.wav.

The engine, tyre, skid, wind, impact and bump banks are real recordings, cut into seamless loops where the game loops
them (the engine at five engine speeds, the tyres and wind at three, the skid at three slip levels) and kept whole where
it plays them once (impacts and suspension knocks). They are levelled for the game's mix, resampled to 48 kHz mono
16-bit, and each loop's seam is closed after resampling. Deterministic: fixed input files, no randomness.
"""
import importlib.util, json, wave
from pathlib import Path
import numpy as np

_spec = importlib.util.spec_from_file_location('skate_make', Path(__file__).resolve().parent.parent / 'skate' / 'make.py')
sk = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(sk)
resample, SR = sk.resample, 48000
ROOT = sk.ROOT
OUT = ROOT / 'audio/kart'
SOURCE = Path(__file__).resolve().parent / 'recordings'
# Cue -> (variants, loop, peak). The engine's five loops are a ladder from idle to the limiter; the component
# crossfades them by engine speed.
CUES = {
    'engine': (5, True, .82),
    'tyre': (3, True, .58),
    'skid': (3, True, .78),
    'wind': (3, True, .55),
    'impact': (4, False, .92),
    'bump': (3, False, .78),
}
LOOPS = [cue for cue, (_, loop, _) in CUES.items() if loop]


def read(path):
    w = wave.open(str(path)); sr = w.getframerate(); ch = w.getnchannels()
    x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float64) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def close_seam(x, ms=2.0):
    """Resampling shifts the loop boundary by a fraction of a sample; fold a couple of milliseconds to hide it."""
    n = int(SR * ms / 1000)
    if len(x) <= 2 * n:
        return x
    fade = np.linspace(0, 1, n)
    y = x[:-n].copy()
    y[:n] = x[:n] * fade + x[-n:] * (1 - fade)
    return y


def write(cue, index, x, peak_):
    x = np.asarray(x, np.float64)
    x = x / max(np.max(np.abs(x)), 1e-9) * peak_
    d = OUT / cue; d.mkdir(parents=True, exist_ok=True)
    path = d / f'{cue}_{index:02d}.wav'
    w = wave.open(str(path), 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes()); w.close()
    return {'file': str(path.relative_to(ROOT)), 'seconds': round(len(x) / SR, 3)}


def main():
    report = {}
    for cue, (variants, loop, peak_) in CUES.items():
        report[cue] = []
        for index in range(1, variants + 1):
            src = SOURCE / f'{cue}_{index:02d}.wav'
            x, sr = read(src)
            if sr != SR:
                x = resample(x, SR / sr)
            if loop:
                x = close_seam(x)
            report[cue].append(write(cue, index, x, peak_))
    (OUT / 'manifest.json').write_text(json.dumps(
        {'sample_rate': SR, 'loops': LOOPS, 'cues': report}, indent=2) + '\n')
    print(f'kart audio: {sum(len(v) for v in report.values())} waves in {OUT}')


if __name__ == '__main__':
    main()
