#!/usr/bin/env python3
"""Build Cairo's bike sounds (docs/BIKE.md) into build/yorimichi/audio/bike/<cue>/<cue>_NN.wav (48 kHz mono 16-bit).

Loops are noise shaped in the frequency domain (seamless by construction, as the skateboard's): the tyres on each kind
of ground, the freewheel ticking while he coasts, the chain while he pedals (one loop is one crank turn, so the game
plays it at the cadence), the wind at speed and the back tyre skidding. One-shots: the mamachari's thumb bell, the
stand flipping up and down, the saddle spring, landings, the basket rattling over bumps, the crash into a wall and the
bike falling on its side. Impacts stay thuddy (noise and low damped knocks, not bright sticks and pure sines). The
crash and fall are built around two Sonniss GDC masters already in sonniss/combat (local signal processing only, see
audio/SONNISS-LICENSE.txt). Deterministic: fixed seeds. The DSP helpers are the skateboard's (audio/skate/make.py).
"""
import importlib.util, json, wave
from pathlib import Path
import numpy as np

_spec = importlib.util.spec_from_file_location('skate_make', Path(__file__).resolve().parent.parent / 'skate' / 'make.py')
sk = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(sk)
SR, shaped_noise, band, peak, periodic_mod, env, thump, click, filtered, mix, impulses, fade_tail, resample, read = (
    sk.SR, sk.shaped_noise, sk.band, sk.peak, sk.periodic_mod, sk.env, sk.thump, sk.click, sk.filtered, sk.mix,
    sk.impulses, sk.fade_tail, sk.resample, sk.read)
ROOT = sk.ROOT
OUT = ROOT / 'audio/bike'
SONNISS = sk.SONNISS
# UBikeComponent plays tyre_<ground> for each kind of ground (ESkateSurface folded: concrete, asphalt and metal are
# the plain tyre; sand rides as dirt).
GROUNDS = ['wood', 'stone', 'dirt', 'grass']
LOOPS = ['tyre'] + ['tyre_' + g for g in GROUNDS] + ['freewheel', 'chain', 'wind', 'skid', 'skid_dirt']


def write(cue, index, x, peak_=.85):
    x = np.asarray(x, np.float64)
    x = x / max(np.max(np.abs(x)), 1e-9) * peak_
    d = OUT / cue; d.mkdir(parents=True, exist_ok=True)
    path = d / f'{cue}_{index:02d}.wav'
    w = wave.open(str(path), 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes()); w.close()
    return {'file': str(path.relative_to(ROOT)), 'seconds': round(len(x) / SR, 3)}


def ring(freqs, seconds, decays, gains, beat=0.):
    """Struck metal: decaying partials, each a close pair `beat` Hz apart so a dome shimmers rather than beeps."""
    t = np.arange(int(seconds * SR)) / SR
    out = np.zeros(len(t))
    for f, d, g in zip(freqs, decays, gains):
        out += g * np.exp(-t / d) * (np.sin(2 * np.pi * f * t) + .6 * np.sin(2 * np.pi * (f + beat) * t + 1.3))
    return out


def rattle(seconds, count, seed, lo=900, hi=6000, decay=.004):
    """Loose parts (the wicker basket, the chain case, the rack strap) knocking a few times and settling."""
    r = np.random.default_rng(seed)
    out = np.zeros(int(seconds * SR)); at, gain = r.uniform(0, .01), 1.
    for _ in range(count):
        hit = click(.03, decay * r.uniform(.7, 1.4), lo, hi, int(r.integers(1 << 30))) * gain
        s = int(at * SR); e = min(len(out), s + len(hit)); out[s:e] += hit[:e - s]
        at += r.uniform(.018, .05); gain *= r.uniform(.6, .9)
    return out


def main():
    report = {}
    # --------------------------------------------------------------------------------------------- loops (2 s unless said)
    # tyre: a pneumatic tyre on smooth ground, a soft low hum and a faint tread hiss; far gentler than the board's wheels
    hum = shaped_noise(2., lambda f: band(f, 35, 700, 1.5) * (1 / np.maximum(f, 30) ** .6) * (1 + peak(f, 140, 50, 1.2)), 201)
    hiss = shaped_noise(2., lambda f: band(f, 1800, 7000) * (1 + peak(f, 3200, 900, .5)), 202) * periodic_mod(2., 2, 9, .35, 203)
    tyre = hum + .22 * hiss
    report['tyre'] = [write('tyre', 1, tyre, .5)]
    # wood: bridge and deck planks, a soft hollow bump at each joint (the rate rises with the pitch, i.e. the speed)
    plank = lambda r: mix((thump(r.uniform(70, 95), .12, .03, .5), 1.), (shaped_noise(.08, lambda f: band(f, 120, 900), int(r.integers(1 << 30)))[:int(.08 * SR)] * env(int(.08 * SR), .001, .015), .5))
    report['tyre_wood'] = [write('tyre_wood', 1, .8 * tyre + 1.5 * impulses(2., 7, .08, plank, 204), .55)]
    # stone: flagstones and cobbles, the tyre thudding dully over joints and a little rougher hum
    cobble = lambda r: mix((thump(r.uniform(85, 130), .08, .02, .6), 1.), (click(.02, .004, 300, 2000, int(r.integers(1 << 30))), .25))
    grit = shaped_noise(2., lambda f: band(f, 900, 5000), 205) * periodic_mod(2., 20, 70, 1., 206)
    report['tyre_stone'] = [write('tyre_stone', 1, tyre + .25 * grit + 1.2 * impulses(2., 11, .3, cobble, 207), .55)]
    # dirt: packed earth and gravel, a crunch of small stones under the tread
    stones = lambda r: click(.014, .003, 1200, 8000, int(r.integers(1 << 30)))
    dull = shaped_noise(2., lambda f: band(f, 35, 600, 1.5) * (1 / np.maximum(f, 30) ** .5), 208)
    crunch = shaped_noise(2., lambda f: band(f, 500, 3500), 209) * periodic_mod(2., 6, 30, 1.3, 210)
    report['tyre_dirt'] = [write('tyre_dirt', 1, dull + .45 * crunch + 1.1 * impulses(2., 90, .5, stones, 211), .5)]
    # grass: the tyres pressing through blades, a brushing swish over a muffled hum
    swish = shaped_noise(2., lambda f: band(f, 400, 6000) * (1 + peak(f, 2200, 1000, .6)), 212) * periodic_mod(2., 1.5, 5, .7, 213)
    report['tyre_grass'] = [write('tyre_grass', 1, .55 * shaped_noise(2., lambda f: band(f, 35, 400), 214) + swish, .4)]
    # freewheel: the hub's pawls ticking over the ratchet as he coasts, 30 ticks a second at pitch 1 (the game sets the
    # pitch from the wheel's turning); evenly spaced, so the loop is seamless
    n = SR; ticks = np.zeros(n)
    for k in range(30):
        tick = click(.012, .0018, 2500, 9000, 300 + k) + .5 * np.sin(2 * np.pi * 4300 * np.arange(int(.012 * SR)) / SR) * env(int(.012 * SR), .0002, .002)
        at = k * n // 30; ticks[at:at + len(tick)] += tick[:n - at] * (1 if k % 2 else .8)
    report['freewheel'] = [write('freewheel', 1, ticks, .45)]
    # chain: one crank turn in .75 s (80 rpm at pitch 1): the chain's light whirr over the sprockets and a soft knock of
    # the bottom bracket as each pedal goes down
    whirr = shaped_noise(.75, lambda f: band(f, 400, 4000) * (1 + peak(f, 1100, 300, .8)), 215) * periodic_mod(.75, 30, 120, .8, 216)
    stroke = np.zeros(int(.75 * SR))
    for k, at in enumerate((0, int(.375 * SR))):
        knock = mix((thump(110 + 12 * k, .1, .025, .3), 1.), (click(.04, .01, 300, 1500, 217 + k), .3))
        stroke[at:at + len(knock)] += knock[:len(stroke) - at]
    report['chain'] = [write('chain', 1, .7 * whirr + stroke, .45)]
    # wind: rushing past the ears at speed, a broad low roar with slow gusts (3 s)
    report['wind'] = [write('wind', 1, shaped_noise(3., lambda f: band(f, 60, 1800, 1.2) * (1 / np.maximum(f, 60) ** .3), 218) * periodic_mod(3., .4, 2, .45, 219), .5)]
    # skid: the locked back tyre scrubbing smooth ground, rubbery with a low moan rather than the board's squeal
    t = np.arange(int(1.5 * SR)) / SR
    moan = sum(np.sin(2 * np.pi * (k * 420 * t + k * 4 * np.sin(2 * np.pi * 5 * t) / (2 * np.pi * 5))) / k ** 1.3 for k in (1, 2, 3))
    scrub = shaped_noise(1.5, lambda f: band(f, 250, 3000) * (1 + peak(f, 700, 200, .9)), 220) * periodic_mod(1.5, 8, 30, .5, 221)
    report['skid'] = [write('skid', 1, scrub + .2 * moan, .55)]
    # skid on dirt and grass: a gravelly scrunch and spray
    spray = lambda r: click(.02, .005, 900, 7000, int(r.integers(1 << 30)))
    report['skid_dirt'] = [write('skid_dirt', 1, .7 * shaped_noise(1.5, lambda f: band(f, 300, 3000), 222) * periodic_mod(1.5, 5, 25, 1., 223) + 1.3 * impulses(1.5, 160, .5, spray, 224), .55)]

    # --------------------------------------------------------------------------------------------- one-shots, 3 variants
    body = read(SONNISS / 'gamemaster_body_thump_02.wav')
    dirt = read(SONNISS / 'redlib_bodyfall_dirt_hard_10.wav')
    def transient(x, seconds):
        start = int(np.argmax(np.abs(x) > .2 * np.max(np.abs(x))))
        return fade_tail(x[max(0, start - 48): start + int(seconds * SR)])
    body_t, dirt_t = transient(body, .5), transient(dirt, .6)
    for cue in ('bell', 'stand_up', 'stand_down', 'creak', 'land', 'rattle', 'crash', 'fall'): report[cue] = []
    for i in range(3):
        r = np.random.default_rng(400 + i)
        # bell: the thumb lever spins a striker against a steel dome, two or three quick strikes ("chirin") that ring on
        f0 = [2380, 2310, 2440][i]
        dome = lambda: ring([f0, f0 * 1.51, f0 * 2.33, f0 * 3.2], 1.1, [.42, .2, .09, .05], [1., .55, .3, .12], beat=[3.5, 4.2, 3.0][i])
        strike = mix((dome(), 1.), (click(.01, .0012, 3000, 12000, 410 + i), .5))
        bell = np.zeros(int(1.2 * SR))
        for k, (at, g) in enumerate([(0, 1.), (.032, .7), (.061, .45)][:3 if i != 1 else 2]):
            s = int(at * SR); e = min(len(bell), s + len(strike)); bell[s:e] += g * strike[:e - s]
        report['bell'].append(write('bell', i + 1, bell, .8))
        # stand flipping up into its clip: a dull knock of steel on the frame's rubber stop, a tiny spring after it
        up = mix((thump([190, 205, 180][i], .12, .02, .4), 1.), (click(.05, .006, 400, 3000, 420 + i), .45),
                 (ring([1650 * [1, 1.06, .95][i]], .2, [.035], [1.]), .08))
        report['stand_up'].append(write('stand_up', i + 1, up, .6))
        # stand down: its feet hit the ground and the bike settles back onto it
        down = mix((thump([120, 132, 112][i], .2, .04, .5), 1.), (click(.06, .008, 300, 2500, 430 + i), .5),
                   (np.pad(thump([95, 100, 90][i], .2, .05, .3), (int(.14 * SR), 0)), .6), (np.pad(rattle(.2, 3, 435 + i, decay=.003), (int(.15 * SR), 0)), .2))
        report['stand_down'].append(write('stand_down', i + 1, down, .6))
        # creak: the saddle's coil springs taking his weight, a short low squeak
        n = int(.3 * SR); tt = np.arange(n) / SR
        glide = np.sin(2 * np.pi * np.cumsum(np.linspace([620, 580, 660][i], [470, 440, 500][i], n)) / SR)
        creak = glide * env(n, .03, .07) * (1 + .5 * np.sin(2 * np.pi * 38 * tt)) + .4 * shaped_noise(.3, lambda f: band(f, 300, 1500), 440 + i)[:n] * env(n, .02, .06)
        report['creak'].append(write('creak', i + 1, creak, .35))
        # land: both tyres thumping down after a hop, the frame's dull knock and the basket rattling
        n = int(.35 * SR)
        thud = shaped_noise(.35, lambda f: band(f, 30, 220), 450 + i)[:n] * env(n, .001, .05) + .6 * thump([70, 78, 64][i], .35, .07, .4)
        land = mix((thud, 1.), (np.pad(thud[:int(.2 * SR)] * .5, (int([.05, .07, .04][i] * SR), 0)), .7), (rattle(.35, 6, 455 + i), .3))
        report['land'].append(write('land', i + 1, land, .75))
        # rattle: a bump on rough ground, the basket and chain case knocking
        report['rattle'].append(write('rattle', i + 1, mix((rattle(.3, [5, 7, 6][i], 460 + i, 700, 4500, .005), 1.), (thump(140, .08, .015, .3), .3)), .4))
        # crash: the front wheel into a wall, a heavy body thump, the frame's knock, the basket and a stray ring of the bell
        knock = filtered(resample(body_t, [1., .92, 1.08][i]), 40, 1400)
        crash = mix((knock, 1.), (thump([62, 70, 56][i], .5, .09, .5), .8), (rattle(.6, 9, 470 + i), .45),
                    (np.pad(ring([f0], .9, [.3], [1.], 3.5), (int(.06 * SR), 0)), .07))
        report['crash'].append(write('crash', i + 1, crash, .85))
        # fall: the bike dropping on its side on the ground, a dull thud, a skid of the pedal and a rattle
        thud = filtered(resample(dirt_t, [1.1, 1., 1.2][i]), 40, 3000)
        fall = mix((thud, 1.), (np.pad(rattle(.5, 8, 480 + i), (int(.04 * SR), 0)), .4),
                   (np.pad(shaped_noise(.25, lambda f: band(f, 500, 4000), 485 + i)[:int(.25 * SR)] * env(int(.25 * SR), .02, .08), (int(.08 * SR), 0)), .25))
        report['fall'].append(write('fall', i + 1, fall, .8))
    (OUT / 'manifest.json').write_text(json.dumps({'sample_rate': SR, 'loops': LOOPS, 'cues': report}, indent=1) + '\n')
    print('BIKE SFX READY', sum(len(v) for v in report.values()), 'files')


if __name__ == '__main__':
    main()
