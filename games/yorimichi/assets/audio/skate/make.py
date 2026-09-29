#!/usr/bin/env python3
"""Build the skateboard sounds (docs/SKATE.md) into japan/audio/skate/<cue>/<cue>_NN.wav (48 kHz mono 16-bit).

Loops (roll, grind, slide, skid) are synthesised as noise shaped in the frequency domain, which makes every loop
seamless by construction. The pop, landing, catch and bail clatter are built around two wooden stick hits from the
Sonniss GDC masters already in audio/sonniss/combat (local signal processing only, see audio/sonniss/LICENSE.txt), with
synthetic thumps and clicks under them. Deterministic: fixed seeds.

    <python with numpy> japan/tools/make_skate_sfx.py
"""
import json, wave
from pathlib import Path
import numpy as np

import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from atelier.paths import cache_dir  # noqa: E402
ROOT = yori.OUT
OUT = ROOT / 'audio/skate'
SONNISS = cache_dir('sonniss', 'combat')
SR = 48000
rng = np.random.default_rng(17)


def read(path):
    w = wave.open(str(path)); n, ch, width, rate = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
    raw = np.frombuffer(w.readframes(n), np.uint8)
    if width == 3:
        b = raw.reshape(-1, 3).astype(np.int32)
        x = (b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)); x = np.where(x >= 1 << 23, x - (1 << 24), x) / float(1 << 23)
    else:
        x = np.frombuffer(raw.tobytes(), np.int16) / 32768.0
    x = x.reshape(-1, ch).mean(axis=1)
    if rate != SR: x = resample(x, SR / rate)
    return x


def resample(x, ratio):
    """Linear resampling by `ratio` (>1 lengthens, i.e. lowers the pitch when played at the same rate)."""
    n = int(len(x) * ratio)
    return np.interp(np.arange(n) / ratio, np.arange(len(x)), x)


def write(cue, index, x, peak=.85):
    x = np.asarray(x, np.float64)
    x = x / max(np.max(np.abs(x)), 1e-9) * peak
    d = OUT / cue; d.mkdir(parents=True, exist_ok=True)
    path = d / f'{cue}_{index:02d}.wav'
    w = wave.open(str(path), 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes()); w.close()
    return {'file': str(path.relative_to(ROOT)), 'seconds': round(len(x) / SR, 3)}


def shaped_noise(seconds, envelope, seed=None):
    """Periodic noise whose magnitude spectrum follows envelope(freq_hz): loops without a seam."""
    r = np.random.default_rng(seed) if seed is not None else rng
    n = int(seconds * SR)
    f = np.fft.rfftfreq(n, 1 / SR)
    spec = (r.normal(size=len(f)) + 1j * r.normal(size=len(f))) * envelope(f)
    spec[0] = 0
    x = np.fft.irfft(spec, n)
    return x / (np.std(x) + 1e-12)


def peak(f, centre, width, gain=1.0):
    return gain * np.exp(-0.5 * ((f - centre) / width) ** 2)


def band(f, lo, hi, slope=2.0):
    return 1 / (1 + (lo / np.maximum(f, 1)) ** (2 * slope)) / (1 + (f / hi) ** (2 * slope))


def periodic_mod(seconds, lo, hi, depth, seed):
    """A slow random amplitude wobble that also loops (roughness of a scrape)."""
    m = shaped_noise(seconds, lambda f: band(f, lo, hi, 1.5), seed)
    return 1 + depth * np.tanh(m * .8)


def env(n, attack, decay):
    t = np.arange(n) / SR
    return np.minimum(t / max(attack, 1e-4), 1) * np.exp(-np.maximum(t - attack, 0) / decay)


def thump(freq, seconds, decay, drop=.6):
    t = np.arange(int(seconds * SR)) / SR
    f = freq * (1 + drop * np.exp(-t / .012))              # the pitch falls in the first milliseconds, like a hit on a slab
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(t), .002, decay)


def click(seconds, decay, lo, hi, seed):
    n = int(seconds * SR)
    return shaped_noise(seconds, lambda f: band(f, lo, hi), seed)[:n] * env(n, .0005, decay)


def mix(*parts):
    n = max(len(p) for p, _ in parts)
    out = np.zeros(n)
    for p, g in parts: out[:len(p)] += p * g
    return out


def fade_tail(x, seconds=.02):
    n = int(seconds * SR); x = x.copy(); x[-n:] *= np.linspace(1, 0, n); return x


def main():
    report = {}
    stick = read(SONNISS / 'audioville_stick_hit_13_wild.wav')
    sword = read(SONNISS / 'audioville_wooden_sword_hit_11.wav')
    def transient(x, seconds):
        start = int(np.argmax(np.abs(x) > .2 * np.max(np.abs(x))))
        seg = x[max(0, start - 48): start + int(seconds * SR)]
        return fade_tail(seg)
    stick_t, sword_t = transient(stick, .22), transient(sword, .18)
    # roll: wheels on smooth concrete, a low rumble with fine grain; the game scales volume and pitch with speed
    roll = shaped_noise(2.0, lambda f: band(f, 50, 2600, 1.5) * (1 / np.maximum(f, 30) ** .5) * (1 + peak(f, 320, 120, 1.4) + peak(f, 900, 300, .5)), 1)
    grain = shaped_noise(2.0, lambda f: band(f, 1500, 5000), 2) * periodic_mod(2.0, 15, 60, .9, 3)
    report['roll'] = [write('roll', 1, roll + .18 * grain, .5)]
    # grind: steel truck on a steel rail or ledge edge, bright inharmonic partials and a rough, fast wobble
    partials = [(820, 25, 1.0), (1630, 35, .8), (2440, 40, .7), (3510, 50, .55), (4870, 60, .4), (6100, 70, .3), (7900, 90, .2)]
    metal = shaped_noise(2.0, lambda f: sum(peak(f, c, w, g) for c, w, g in partials) + .08 * band(f, 1500, 9000), 4)
    report['grind'] = [write('grind', 1, metal * periodic_mod(2.0, 6, 28, .55, 5) + .25 * shaped_noise(2.0, lambda f: band(f, 90, 400), 6), .6)]
    # slide: the deck's wood across a ledge or rail, duller and lower
    slide = shaped_noise(2.0, lambda f: band(f, 180, 2600) * (1 + peak(f, 620, 180, 1.2) + peak(f, 1400, 300, .6)), 7)
    report['slide'] = [write('slide', 1, slide * periodic_mod(2.0, 4, 20, .5, 8), .55)]
    # skid: urethane scrubbing sideways (powerslide), noise with a faint wavering squeal
    t = np.arange(int(1.5 * SR)) / SR
    squeal = sum(np.sin(2 * np.pi * (k * 1140 * t + k * 6 * np.sin(2 * np.pi * 4 * t) / (2 * np.pi * 4))) / k ** 1.5 for k in (1, 2, 3))
    skid = shaped_noise(1.5, lambda f: band(f, 350, 3200) * (1 + peak(f, 900, 250, .8)), 9)
    report['skid'] = [write('skid', 1, skid * periodic_mod(1.5, 5, 25, .4, 10) + .35 * squeal, .55)]
    # scrape: a shoe dragged on concrete (foot brake)
    report['scrape'] = [write('scrape', 1, shaped_noise(1.0, lambda f: band(f, 500, 6000) * (1 + peak(f, 2200, 800, .6)), 11) * periodic_mod(1.0, 3, 12, .35, 12), .45)]
    report['pop'], report['land'], report['catch'], report['push'], report['flick'], report['clatter'] = [], [], [], [], [], []
    for i in range(3):
        # pop: the tail cracking on the ground: a woody crack over a short slab thump and a bright click
        crack = resample(stick_t if i != 1 else sword_t, [1.0, 1.08, .93][i])
        pop = mix((crack, 1.0), (thump([125, 140, 115][i], .12, .035), .8), (click(.03, .004, 2000, 9000, 20 + i), .35))
        report['pop'].append(write('pop', i + 1, pop))
        # land: four wheels and the deck slapping down: a low thump, the wheels' smack, a dull wood knock
        knock = resample(sword_t if i != 2 else stick_t, [1.35, 1.25, 1.45][i])
        land = mix((thump([82, 95, 74][i], .28, .07, .9), 1.0), (click(.05, .012, 250, 2500, 30 + i), .7), (knock, .45))
        report['land'].append(write('land', i + 1, land))
        # catch: the feet slapping the board back after a flip, lighter than a landing
        report['catch'].append(write('catch', i + 1, mix((click(.04, .008, 600, 5000, 40 + i), .8), (resample(sword_t, [1.6, 1.5, 1.7][i]), .5), (thump(180, .08, .02), .4)), .6))
        # push: the shoe scuffing and planting on concrete
        n = int(.22 * SR)
        scuff = shaped_noise(.22, lambda f: band(f, 400, 5500), 50 + i)[:n] * env(n, .03, .07)
        report['push'].append(write('push', i + 1, mix((scuff, 1.0), (thump(160, .06, .015), .5)), .45))
        # flick: the board spinning under the feet, a short airy whirr
        n = int(.32 * SR); t = np.arange(n) / SR
        whirr = shaped_noise(.32, lambda f: band(f, 500, 3500), 60 + i)[:n] * env(n, .04, .1) * (1 + .6 * np.sin(2 * np.pi * (18 + 6 * i) * t))
        report['flick'].append(write('flick', i + 1, whirr, .35))
        # clatter: the board tumbling away after a bail, a few wooden knocks that die out
        out = np.zeros(int(1.2 * SR))
        at, gain = 0.0, 1.0
        r = np.random.default_rng(70 + i)
        for k in range(5):
            hit = resample(stick_t if k % 2 else sword_t, r.uniform(1.1, 1.6)) * gain
            s = int(at * SR); e = min(len(out), s + len(hit)); out[s:e] += hit[:e - s]
            at += r.uniform(.12, .25) * (1 - .12 * k); gain *= r.uniform(.45, .7)
        report['clatter'].append(write('clatter', i + 1, out, .7))
    (OUT / 'manifest.json').write_text(json.dumps({'sample_rate': SR, 'loops': ['roll', 'grind', 'slide', 'skid', 'scrape'], 'cues': report}, indent=1) + '\n')
    print('SKATE SFX READY', sum(len(v) for v in report.values()), 'files')


if __name__ == '__main__':
    main()
