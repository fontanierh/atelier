#!/usr/bin/env python3
"""Build Yorimichi's combat one-shots (and the countryside ambience loop) from the
Sonniss masters restored by tools/fetch_sonniss_combat.py.

Every delivered WAV is described below in SPEC: which master, which seconds,
which channel, filters, gain, and (for layered sounds) where each layer sits.
The build is deterministic: same masters in, same bytes out.

Pipeline per sound:
  1. ffmpeg decodes each master to 48 kHz float (channels kept); one channel is
     picked, or the channels are averaged (wide/spaced stereo pairs use one
     channel so the mono fold-down does not comb-filter).
  2. each layer is cut, high/low-passed (RBJ biquads), gained and, if asked,
     shifted so its own onset lands at `at` seconds; layers are summed.
  3. DC is removed, the start is trimmed so the onset sits 2 ms after sample 0,
     trailing silence (-65 dB under the peak) is dropped, an optional longer
     `tail` fade shapes cut-off tails, then a 2 ms fade-in and a 5-30 ms
     fade-out are applied.
  4. per category: every variant is matched to the same loudness (max momentary
     LUFS), then the category is placed either at a peak ceiling (impacts, parry,
     hurt, falls: loudest peak at -1 dBFS) or relative to the hit_body loudness
     (swings -4..-6 LU, foley -10, fox vocals 0..+3), never above -1 dBFS peak.
  5. 16-bit PCM with seeded TPDF dither, mono 48 kHz (ambience: stereo loop with
     an equal-power crossfade, integrated -30 LUFS).

Outputs: audio/combat/<category>/<category>_<nn>.wav, audio/combat/manifest.json,
audio/combat/preview/<category>.wav (variants back to back, 0.4 s gaps).

Usage:  python3 tools/slice_combat_sfx.py [--only hit_body,parry]
"""
import argparse, json, subprocess, sys, wave, zlib
from pathlib import Path

import numpy as np

import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from atelier.paths import cache_dir  # noqa: E402
ROOT = yori.OUT
SRC = cache_dir('sonniss', 'combat')
DST = ROOT / 'audio' / 'combat'
RATE = 48_000

FADE_IN_S = 0.002
PRE_ROLL_S = 0.002
ONSET_DB = -30.0          # onset = first 1 ms RMS block within 30 dB of the peak block
TAIL_GATE_DB = -65.0      # trailing audio this far under the peak is dropped
GAP_S = 0.4               # silence between variants in the preview files

# ---------------------------------------------------------------------------
# What we ship. Times are seconds in the master. `ch`: 'mix' (average) or a
# channel index. `hp`/`lp`: filter corner in Hz. `gain`: dB. `at`: where the
# layer's onset lands in the output (layered sounds only).
# ---------------------------------------------------------------------------
L = lambda src, start, end, **kw: dict(src=src, start=start, end=end, **kw)

SPEC = {
 'sword_swing': dict(level=('rel', -5.0), variants=[
   dict(layers=[L('jse_woodstick_swish_03.wav', 0.110, 0.520, hp=150)], fade=0.02,
        why='Library "Woodstick Swish" take 1: a real wooden stick cut through the air, sharp onset, falling whistle.'),
   dict(layers=[L('jse_woodstick_swish_03.wav', 2.036, 2.446, hp=150)], fade=0.02,
        why='Woodstick swish take 2: same stick, slightly softer, keeps the set consistent for random picks.'),
   dict(layers=[L('jse_woodstick_swish_03.wav', 3.950, 4.360, hp=150)], fade=0.02,
        why='Woodstick swish take 3: medium strength cut.'),
   dict(layers=[L('jse_woodstick_swish_03.wav', 6.116, 6.526, hp=150)], fade=0.02,
        why='Woodstick swish take 4: strongest of the four, brightest whistle.'),
 ]),
 'sword_swing_heavy': dict(level=('rel', -4.0), variants=[
   dict(layers=[L('soundbits_whoosh_rod_pole_022.wav', 0.0, 0.85, hp=60)], fade=0.03,
        why='"Whoosh Rod Pole": a long pole swung hard, deep (centroid ~1.6 kHz) and broad, reads as a two-handed wooden strike.'),
   dict(layers=[L('ddumais_swing_large_03.wav', 0.05, 0.66, hp=60)], fade=0.03,
        why='David Dumais "Swing 3 Large": big weapon swing that swells into the release, for the charged strike.'),
 ]),
 'claw_swipe': dict(level=('rel', -5.0), variants=[
   dict(layers=[L('rts_rope_whoosh_fast_light_01.wav', 0.10, 0.47, ch=0, hp=300)], fade=0.02,
        why='"Rope Whoosh Fast Light" take 1: thin, bright (centroid ~5 kHz), airy; no weapon body, suits claws.'),
   dict(layers=[L('rts_rope_whoosh_fast_light_01.wav', 4.62, 4.98, ch=0, hp=300)], fade=0.02,
        why='Rope whoosh take 4: fastest attack of the takes, very thin top.'),
   dict(layers=[L('eiravaein_fencingfoil_swoosh.wav', 0.02, 0.44, hp=300)], fade=0.02,
        why='Fencing foil swoosh: a thin blade flicked fast, sharp and small; the third claw flavour.'),
 ]),
 'kick_swing': dict(level=('rel', -6.0), variants=[
   dict(layers=[L('soundholder_tshirt_fast_swings.wav', 0.33, 0.72, ch=0, hp=120)], fade=0.02,
        why='Soundholder "tshirt fast and short swings" take 1: cloth swung fast, a leg/trouser whoosh without a hit.'),
   dict(layers=[L('soundholder_tshirt_fast_swings.wav', 14.28, 14.68, ch=0, hp=120)], fade=0.02,
        why='T-shirt swing take 15: loudest take, a firmer cloth snap for kicks.'),
 ]),
 'dash': dict(level=('rel', -6.0), variants=[
   dict(layers=[L('airborne_fabric_glove_whoosh.wav', 0.02, 0.40, hp=100)], fade=0.02,
        why='Airborne "Organic Whoosh, Fabric, Glove, Airy, Breathy, Punchy": short cloth-and-air burst, ideal for a dodge.'),
   dict(layers=[L('mechwave_action_swish_02.wav', 2.53, 2.86, hp=100)], fade=0.02,
        why='Mechanical Wave "Action Swish" take 4: very fast attack air burst, 0.3 s.'),
 ]),
 'hit_body': dict(level=('peak', -1.0), variants=[
   dict(layers=[L('mchugh_wood_beating_flesh_medium_11.wav', 0.04, 0.25, hp=90, tail=0.05)], fade=0.02,
        why='Timothy McHugh "wood beating flesh - medium": literally a wooden stick on a body; cut before the wet splatter tail.'),
   dict(layers=[L('mchugh_wood_beating_flesh_soft_04.wav', 0.04, 0.22, hp=90, tail=0.05)], fade=0.02,
        why='Same session, softer blow: hard transient, less weight, for light cuts.'),
   dict(layers=[L('rts_flog_leather_hit_smack_01.wav', 13.54, 13.84, hp=60)], fade=0.02,
        why='Rock The Speakerbox "Flog Leather Hit Smack" take 6: a leather/cloth smack with body, the "through clothing" thwack.'),
   dict(layers=[L('duffield_keeper_punch_01.wav', 0.01, 0.33, hp=60)], fade=0.02,
        why='"Keeper Punch": gloved fist on a ball, a round punchy thud with a clean short decay.'),
 ]),
 'hit_heavy': dict(level=('peak', -1.0), variants=[
   dict(layers=[L('gamemaster_punch_heavy_huge_01.wav', 0.0, 0.45, ch=0, hp=40, at=0.0),
                L('344_explosive_hit_10_low_end.wav', 0.0, 0.90, hp=25, gain=-3.0, at=0.0, tail=0.45),
                L('344_spear_stick_impact_wooden.wav', 5.04, 5.34, hp=150, gain=-6.0, at=0.0)],
        fade=0.03,
        why='Layered: Gamemaster "punch heavy huge" body + 344 Audio low-end boom + a wooden stick crack on top, for the charged strike.'),
   dict(layers=[L('pmsfx_punch_clean_deep_48.wav', 0.225, 0.76, hp=40, at=0.0),
                L('344_explosive_hit_10_low_end.wav', 0.0, 0.80, hp=25, gain=-5.0, at=0.0, tail=0.4),
                L('344_spear_stick_impact_wooden.wav', 8.58, 8.86, hp=150, gain=-8.0, at=0.0)],
        fade=0.03,
        why='Layered: PMSFX "Lethal Blow punch clean deep" from its hit + low boom + wood crack; the finishing blow.'),
 ]),
 'parry': dict(level=('peak', -1.0), variants=[
   dict(layers=[L('audioville_stick_hit_13_wild.wav', 0.25, 0.70, hp=150)], fade=0.02,
        why='The AudioVille "Wooden Staffs and Sword Fight - Stick Hit Wild": hard wood-on-wood clack with a short tonal ring.'),
   dict(layers=[L('audioville_wooden_sword_hit_11.wav', 0.055, 0.267, hp=150)], fade=0.015,
        why='Same library, "Wooden Sword Hit": two wooden swords meeting, bright and tight.'),
   dict(layers=[L('344_spear_stick_impact_wooden.wav', 11.03, 11.40, hp=150, at=0.0),
                L('smartsound_sword_hit_metal_02.wav', 0.10, 0.75, ch=0, hp=1000, gain=-10.0, at=0.0, tail=0.3)],
        fade=0.03,
        why='Layered: 344 Audio wooden stick impact (1.5 ms attack) + a quiet metallic sword ring underneath for a "ting" payoff.'),
 ]),
 'sword_charge': dict(level=('rel', -6.0), variants=[
   dict(layers=[L('matiasvidal_riser_16.wav', 0.50, 2.00, hp=60)], fade=0.03,
        why='"Riser 16": 1.4 s noise-and-tone swell that builds and brightens, then eases; holds tension under a charge.'),
 ]),
 'charge_ready': dict(level=('rel', 0.0), variants=[
   dict(layers=[L('eiravaein_japanese_windbell.wav', 1.295, 2.45, ch=0, hp=700, tail=0.35)], fade=0.03,
        why='Eiravaein "Helina" Japanese porcelain wind bell (furin): one clean strike (2.5 kHz ring) with its natural decay; the Mid channel of the M/S master.'),
 ]),
 'sword_draw': dict(level=('rel', -10.0), variants=[
   dict(layers=[L('shapeforms_clothing_movement_08.wav', 0.0, 0.33, ch=0, hp=150, at=0.0),
                L('344_spear_stick_impact_wooden.wav', 7.89, 8.08, hp=150, gain=3.0, at=0.24)],
        fade=0.02,
        why='Layered: Shapeforms cloth movement (the bokken leaving the belt) then a soft 344 Audio wooden knock as the grip settles.'),
   dict(layers=[L('soundbits_scrape_cloth_10.wav', 0.07, 0.56, hp=150, at=0.0, tail=0.06),
                L('344_spear_stick_impact_wooden.wav', 10.24, 10.52, hp=150, gain=-4.0, at=0.40, tail=0.1)],
        fade=0.02,
        why='Layered: SoundBits cloth scrape (a slower draw) ending on a soft wooden knock.'),
 ]),
 'sword_sheathe': dict(level=('rel', -10.0), variants=[
   dict(layers=[L('344_spear_stick_impact_wooden.wav', 5.78, 6.06, hp=150, gain=-4.0, at=0.0, tail=0.1),
                L('esm_cloth_canvas_bag_slide_02.wav', 0.04, 0.52, hp=150, at=0.03)],
        fade=0.02,
        why='Layered: small wooden tap (tip meets the belt, 344 Audio stick impact) then an Epic Stock Media canvas cloth slide.'),
   dict(layers=[L('344_spear_stick_impact_wooden.wav', 7.89, 8.08, hp=150, gain=3.0, at=0.0),
                L('inmotion_tshirt_single_pats_04.wav', 0.06, 0.40, hp=150, at=0.04)],
        fade=0.02,
        why='Layered: soft wooden knock then an InMotion cloth pat, the sword pushed home against the clothes.'),
 ]),
 'player_hurt': dict(level=('peak', -1.0), variants=[
   dict(layers=[L('gamemaster_punch_body_impact_03.wav', 0.0, 0.33, ch=1, hp=50)], fade=0.02,
        why='Gamemaster "punch general body impact": a body blow with low thump, no voice.'),
   dict(layers=[L('chrisalan_deep_punch_02.wav', 0.0, 0.208, hp=50)], fade=0.015,
        why='The Chris Alan "Hand-to-Hand Combat - Deep Punch": short, dull, heavy torso hit.'),
   dict(layers=[L('gamemaster_body_thump_02.wav', 0.0, 0.45, hp=50)], fade=0.02,
        why='Gamemaster "bullet impact body thump": soft padded thud with a cloth-like top, the gentlest of the three.'),
 ]),
 'body_fall': dict(level=('peak', -1.0), variants=[
   dict(layers=[L('redlib_bodyfall_dirt_hard_10.wav', 0.0, 0.85, hp=50)], fade=0.03,
        why='Red Libraries "Bodyfall Dirt Close Hard Impact": torso then limbs landing on dirt, two contacts and settle.'),
   dict(layers=[L('chrisalan_body_slam_floor_08.wav', 0.095, 0.446, hp=60, at=0.0, tail=0.08),
                L('pmsfx_dry_grass_skid_drag.wav', 0.15, 0.62, hp=150, gain=-8.0, at=0.03, tail=0.2)],
        fade=0.03,
        why='Layered: Chris Alan "Body Slam Floor" for the weight + PMSFX dry grass skid so it lands on a meadow.'),
 ]),
 'fox_hurt': dict(level=('rel', 0.0), variants=[
   dict(layers=[L('vicic_red_fox_winter_scream.wav', 95.30, 95.95, ch=0, hp=300, tail=0.30)], fade=0.03,
        why='Ivo Vicic field recording of a real red fox scream; one call, its long natural echo faded out.'),
   dict(layers=[L('vicic_red_fox_winter_scream.wav', 105.34, 105.99, ch=0, hp=300, tail=0.30)], fade=0.03,
        why='Another scream from the same fox, slightly lower and harsher.'),
   dict(layers=[L('vicic_red_fox_winter_scream.wav', 3.70, 4.35, ch=0, hp=300, tail=0.30)], fade=0.03,
        why='Third call, rises in pitch (strongest energy near 1.4 kHz): the sharpest yelp of the set.'),
 ]),
 'fox_alert': dict(level=('rel', 3.0), variants=[
   dict(layers=[L('soundopolis_yorkshire_growl.wav', 1.02, 2.06, hp=150, at=0.0, tail=0.15),
                L('baxter_hit_big_drum_03.wav', 0.0, 1.30, hp=30, gain=-6.0, at=0.0, tail=0.8)],
        fade=0.03,
        why='Layered: a small canid growl (Soundopolis Yorkshire terrier, fox-sized) over one Baxter big drum hit as a taiko-like sting.'),
 ]),
 'fox_death': dict(level=('rel', 0.0), variants=[
   dict(layers=[L('articulated_magic_air_swirl_01.wav', 0.05, 2.25, hp=80, tail=0.5)], fade=0.03,
        why='Articulated Sounds "Magic Air Large Whoosh, Swirl, Wind Gust, Foliage": air swirls up and scatters through leaves; the spirit blowing away.'),
 ]),
 'ambience_countryside': dict(level=('lufs', -30.0), loop=dict(xfade=1.5), variants=[
   dict(layers=[L('soundexmachina_rural_summer.wav', 4.0, 44.0, ch='stereo', hp=25)], fade=0.0,
        why='Sound Ex Machina "Rural summer with birdsong, distant sea waves, breeze": 40 s without clicks, voices or engines, looped with a 1.5 s equal-power crossfade.'),
 ]),
}

# ---------------------------------------------------------------------------
# DSP helpers
# ---------------------------------------------------------------------------
_decoded: dict[str, np.ndarray] = {}


def decode(name: str) -> np.ndarray:
    """Master -> float64 array [samples, channels] at 48 kHz (cached)."""
    if name not in _decoded:
        path = SRC / name
        if not path.exists():
            sys.exit(f'missing master {path} - run tools/fetch_sonniss_combat.py first')
        probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries',
                                'stream=channels', '-of', 'csv=p=0', str(path)],
                               capture_output=True, text=True, check=True)
        ch = int(probe.stdout.strip())
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:a:0',
                              '-ar', str(RATE), '-f', 'f32le', '-'],
                             capture_output=True, check=True).stdout
        _decoded[name] = np.frombuffer(raw, dtype='<f4').astype(np.float64).reshape(-1, ch)
    return _decoded[name]


def biquad(kind: str, f0: float, q: float = 0.7071):
    """RBJ cookbook high/low-pass coefficients at RATE."""
    w = 2 * np.pi * f0 / RATE
    alpha = np.sin(w) / (2 * q)
    c = np.cos(w)
    if kind == 'hp':
        b = [(1 + c) / 2, -(1 + c), (1 + c) / 2]
    else:
        b = [(1 - c) / 2, 1 - c, (1 - c) / 2]
    a = [1 + alpha, -2 * c, 1 - alpha]
    return [v / a[0] for v in b], [1.0, a[1] / a[0], a[2] / a[0]]


def _impulse_response(b, a, n):
    y = [0.0] * n
    x1 = x2 = y1 = y2 = 0.0
    for i in range(n):
        x0 = 1.0 if i == 0 else 0.0
        y0 = b[0] * x0 + b[1] * x1 + b[2] * x2 - a[1] * y1 - a[2] * y2
        y[i] = y0
        x2, x1, y2, y1 = x1, x0, y1, y0
    return np.array(y)


_ir_cache: dict = {}


def iir(b, a, x: np.ndarray) -> np.ndarray:
    """Causal biquad on the last axis, done as FFT convolution with the filter's
    impulse response (2 s long: every filter used here has decayed below 1e-12)."""
    key = (tuple(b), tuple(a))
    if key not in _ir_cache:
        _ir_cache[key] = _impulse_response(b, a, 2 * RATE)
    h = _ir_cache[key]
    n = x.shape[-1]
    m = min(len(h), n)
    size = 1 << int(np.ceil(np.log2(n + m)))
    y = np.fft.irfft(np.fft.rfft(x, size, axis=-1) * np.fft.rfft(h[:m], size), size, axis=-1)
    return y[..., :n]


def hp(x, f):
    return iir(*biquad('hp', f), x)


def lp(x, f):
    return iir(*biquad('lp', f), x)


def env_db(x: np.ndarray, hop: int = 48) -> np.ndarray:
    """1 ms RMS envelope in dB (mono input)."""
    n = max(1, len(x) // hop)
    blocks = np.pad(x, (0, n * hop + hop - len(x)))[: n * hop].reshape(n, hop)
    return 10 * np.log10((blocks ** 2).mean(axis=1) + 1e-20)


def onset_sample(x: np.ndarray) -> int:
    e = env_db(x)
    return int(np.argmax(e > e.max() + ONSET_DB)) * 48


# --- BS.1770-4 loudness ----------------------------------------------------
K1 = ([1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585])
K2 = ([1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621])


def _kweighted_power(x: np.ndarray) -> np.ndarray:
    """x: [samples, ch] -> summed K-weighted power per sample (channel weights 1)."""
    y = iir(*K2, iir(*K1, x.T))
    return (y ** 2).sum(axis=0)


def lufs_integrated(x: np.ndarray) -> float:
    p = _kweighted_power(x)
    blk, step = int(0.4 * RATE), int(0.1 * RATE)
    if len(p) < blk:           # shorter than one gating block: the file is one block
        z = np.array([p.mean()])
    else:
        c = np.concatenate([[0.0], np.cumsum(p)])
        starts = np.arange(0, len(p) - blk + 1, step)
        z = (c[starts + blk] - c[starts]) / blk
    lk = -0.691 + 10 * np.log10(z + 1e-20)
    z = z[lk > -70]
    if not len(z):
        return -70.0
    rel = -0.691 + 10 * np.log10(z.mean()) - 10
    z = z[-0.691 + 10 * np.log10(z) > rel]
    return float(-0.691 + 10 * np.log10(z.mean()))


def lufs_momentary_max(x: np.ndarray) -> float:
    """Loudest 400 ms window (10 ms hop); shorter files are zero-padded to 400 ms."""
    p = _kweighted_power(x)
    blk, step = int(0.4 * RATE), int(0.01 * RATE)
    if len(p) < blk:
        p = np.pad(p, (0, blk - len(p)))
    c = np.concatenate([[0.0], np.cumsum(p)])
    starts = np.arange(0, len(p) - blk + 1, step)
    return float(-0.691 + 10 * np.log10(((c[starts + blk] - c[starts]) / blk).max() + 1e-20))


def peak_db(x: np.ndarray) -> float:
    return float(20 * np.log10(np.abs(x).max() + 1e-20))


# ---------------------------------------------------------------------------
# Building one sound
# ---------------------------------------------------------------------------
def render_layer(layer: dict) -> np.ndarray:
    src = decode(layer['src'])
    s0, s1 = int(round(layer['start'] * RATE)), int(round(layer['end'] * RATE))
    seg = src[s0:s1]
    ch = layer.get('ch', 'mix')
    if ch == 'stereo':
        x = seg.T.copy()                      # [2, n]
    elif ch == 'mix':
        x = seg.mean(axis=1)
    else:
        x = seg[:, ch].copy()
    if 'hp' in layer:
        x = hp(x, layer['hp'])
    if 'lp' in layer:
        x = lp(x, layer['lp'])
    x = x * 10 ** (layer.get('gain', 0.0) / 20)
    if layer.get('tail'):
        n = min(int(layer['tail'] * RATE), x.shape[-1])
        x[..., -n:] *= (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, n)))
    return x


def build_oneshot(v: dict):
    """Mix the layers, trim, fade. Returns (mono signal, per-layer source ranges, onset ms)."""
    parts = []
    for layer in v['layers']:
        x = render_layer(layer)
        pos = 0
        if 'at' in layer:                      # put this layer's onset at `at` seconds
            pos = int(round(layer['at'] * RATE)) - onset_sample(x)
        parts.append((pos, x))
    lo = min(p for p, _ in parts)
    parts = [(p - lo, x) for p, x in parts]
    n = max(p + len(x) for p, x in parts)
    mix = np.zeros(n)
    for p, x in parts:
        mix[p:p + len(x)] += x
    mix -= mix.mean()                          # DC offset

    start = max(0, onset_sample(mix) - int(PRE_ROLL_S * RATE))
    e = env_db(mix)
    alive = np.where(e > e.max() + TAIL_GATE_DB)[0]
    end = min(n, (alive[-1] + 1) * 48) if len(alive) else n
    out = mix[start:end].copy()

    fi = int(FADE_IN_S * RATE)
    out[:fi] *= np.linspace(0, 1, fi)
    fo = min(int(np.clip(v.get('fade', 0.02), 0.005, 0.03) * RATE), len(out) // 2)
    out[-fo:] *= np.linspace(1, 0, fo)

    ranges = []
    for layer, (p, x) in zip(v['layers'], parts):
        a = max(start, p) - p
        b = min(end, p + len(x)) - p
        if b <= a:
            continue
        ranges.append(dict(src=layer['src'], start=round(layer['start'] + a / RATE, 4),
                           end=round(layer['start'] + b / RATE, 4), gain_db=layer.get('gain', 0.0),
                           channel=layer.get('ch', 'mix'), highpass_hz=layer.get('hp'),
                           offset_s=round((max(start, p) - start) / RATE, 4)))
    onset_ms = (onset_sample(out) / RATE) * 1000
    return out, ranges, onset_ms


def build_loop(v: dict, xfade: float):
    layer = dict(v['layers'][0])
    xf = int(xfade * RATE)
    body = layer['end'] - layer['start']
    layer['end'] = layer['end'] + xfade          # read the crossfade material past the end
    x = render_layer(layer)                       # [2, n]
    x -= x.mean(axis=1, keepdims=True)
    n = int(round(body * RATE))
    t = np.linspace(0, np.pi / 2, xf)
    out = x[:, :n].copy()
    # the tail that runs past the loop point fades out over the head: seamless wrap
    out[:, :xf] = x[:, :xf] * np.sin(t) + x[:, n:n + xf] * np.cos(t)
    src = dict(src=layer['src'], start=layer['start'], end=round(layer['end'], 4), gain_db=0.0,
               channel='stereo', highpass_hz=layer.get('hp'), offset_s=0.0)
    return out.T, [src], 0.0


def write_wav(path: Path, x: np.ndarray, seed: int) -> np.ndarray:
    """Float -> 16-bit with seeded TPDF dither. Returns the quantised float data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    d = (rng.random(x.shape) - rng.random(x.shape))
    q = np.clip(np.round(x * 32767 + d), -32768, 32767).astype('<i2')
    ch = 1 if x.ndim == 1 else x.shape[1]
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(q.tobytes())
    return q.astype(np.float64) / 32767


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', help='comma-separated categories to rebuild (manifest keeps the rest)')
    args = ap.parse_args()
    only = set(args.only.split(',')) if args.only else None
    masters = {m['file']: m for m in json.loads((SRC / 'manifest.json').read_text())}

    built = {}
    for cat, spec in SPEC.items():
        rendered = []
        for v in spec['variants']:
            if 'loop' in spec:
                rendered.append((v, *build_loop(v, spec['loop']['xfade'])))
            else:
                rendered.append((v, *build_oneshot(v)))
        built[cat] = rendered

    # impact reference: loudness of hit_body once it sits at its peak ceiling
    def match_gains(cat):
        rendered = built[cat]
        loud = [lufs_momentary_max(x.reshape(len(x), -1)) for _, x, _, _ in rendered]
        target = max(loud)
        gains = [target - l for l in loud]                 # equal loudness inside the category
        peaks = [peak_db(x) + g for (_, x, _, _), g in zip(rendered, gains)]
        return target, gains, peaks

    t, g, p = match_gains('hit_body')
    ref_lufs = t + (SPEC['hit_body']['level'][1] - max(p))

    manifest = []
    for cat, spec in SPEC.items():
        rendered = built[cat]
        kind, value = spec['level']
        if kind == 'lufs':
            gains = [value - lufs_integrated(x) for _, x, _, _ in rendered]
            shift = 0.0
        else:
            target, gains, peaks = match_gains(cat)
            if kind == 'peak':
                shift = value - max(peaks)
            else:                                           # relative to the impact reference
                shift = (ref_lufs + value) - target
                shift = min(shift, -1.0 - max(peaks))       # never above -1 dBFS
        preview = []
        for i, ((v, x, ranges, onset_ms), gdb) in enumerate(zip(rendered, gains), 1):
            y = x * 10 ** ((gdb + shift) / 20)
            name = f'{cat}_{i:02d}.wav'
            out = DST / cat / name
            seed = zlib.crc32(f'{cat}/{name}'.encode())
            if only is None or cat in only:
                q = write_wav(out, y, seed)
            else:
                q = y
            q2 = q.reshape(len(q), -1)
            preview.append(q2.mean(axis=1) if q2.shape[1] > 1 else q2[:, 0])
            prim = ranges[0]
            m = masters[prim['src']]
            manifest.append({
                'category': cat,
                'file': f'{cat}/{name}',
                'channels': q2.shape[1],
                'duration_s': round(len(q) / RATE, 3),
                'peak_dbfs': round(peak_db(q), 2),
                'lufs': round(lufs_integrated(q2), 2),
                'lufs_momentary_max': round(lufs_momentary_max(q2), 2),
                'onset_ms': round(onset_ms, 1),
                'source_item': m['source_item'],
                'source_path': m['source_path'],
                'source_start_s': prim['start'],
                'source_end_s': prim['end'],
                'layers': [dict(r, source_item=masters[r['src']]['source_item'],
                                source_path=masters[r['src']]['source_path']) for r in ranges],
                'description': v['why'],
            })
            print(f'{cat:22s} {name:26s} {len(q) / RATE:6.3f}s  peak {peak_db(q):6.2f} dBFS  '
                  f'{lufs_integrated(q2):6.1f} LUFS  onset {onset_ms:4.1f} ms')
        if only is None or cat in only:
            if 'loop' in spec:
                # audition the seam: last 6 s of the loop straight into its first 6 s
                q = preview[0]
                pv = np.concatenate([q[-6 * RATE:], q[:6 * RATE]])
            else:
                gap = np.zeros(int(GAP_S * RATE))
                pv = np.concatenate([np.concatenate([p, gap]) for p in preview])[: -len(gap)]
            write_wav(DST / 'preview' / f'{cat}.wav', pv, zlib.crc32(f'preview/{cat}'.encode()))

    if only:
        old = json.loads((DST / 'manifest.json').read_text()) if (DST / 'manifest.json').exists() else []
        keep = [m for m in old if m['category'] not in only]
        fresh = [m for m in manifest if m['category'] in only]
        manifest = sorted(keep + fresh, key=lambda m: (list(SPEC).index(m['category']), m['file']))
    (DST / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    print(f'\n{len(manifest)} files -> {DST}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
