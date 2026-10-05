#!/usr/bin/env python3
"""Build the hippodrome race music, its rhythm charts and the race sounds into build/yorimichi/audio/hippodrome.

Everything is synthesised here with numpy (no recorded samples): Karplus-Strong plucks for the shamisen/koto lead,
taiko from pitched sine and noise bursts, a shinobue-like flute (sine partials with breath, scoop and vibrato), a sine
bass, a soft sho-like pad, shaker ticks and a chanchiki bell over a galloping triplet groove. All of it is in D major
pentatonic, so the win and lose jingles fit every song. Deterministic: fixed seeds.

Each song is first composed as a list of timed events (compose); the audio is rendered from that list (render) and the
chart is chosen from the same list (chart), so every chart note starts on the sample where a lead note or a drum hit
starts. Outputs:

    music/race_<cup>.wav       48 kHz 16-bit stereo, about -14 LUFS, peaks below -1 dBFS
    charts.json                the three charts: count-in, start, loop points and notes {t, lane, hold}
    HR_<cue>/HR_<cue>_NN.wav   48 kHz 16-bit mono race sounds (HR_CrowdLoop loops seamlessly)
    manifest.json, check.json  files and durations; loudness, peaks, spectra and chart/onset alignment
    preview/*.mp3              review copies (not imported): each song, and each song with a tick on every chart note

    uv run python games/yorimichi/assets/audio/hippodrome/make.py
"""
import json, shutil, subprocess, wave
from bisect import bisect_left, insort
from pathlib import Path
import numpy as np

import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402

ROOT = yori.OUT
OUT = ROOT / 'audio/hippodrome'
SR = 48000
KEY = 62                                   # D4
PENT = (0, 2, 4, 7, 9)                     # major pentatonic: D E F# A B
LUFS_TARGET, CEILING_DB = -14.0, -1.2
PRE = 0.25                                 # silence before the first count-in beat

# ---------------------------------------------------------------------------------------------------- composition
# A chord: root (semitones above D), the pad's triad, and the pentatonic degree classes (index into PENT) it contains.
CHORDS = {'I': (0, (0, 4, 7), {0, 2, 3}), 'ii': (2, (2, 5, 9), {1, 4}), 'iii': (4, (4, 7, 11), {2, 3}),
          'IV': (5, (5, 9, 12), {4, 0}), 'V': (7, (7, 11, 14), {3, 1}), 'vi': (9, (9, 12, 16), {4, 0, 2})}
PROGRESSIONS = {'intro': 'I I IV V', 'A': 'I vi IV V I vi V I', 'B': 'IV V iii vi IV V I I', 'C': 'vi IV I V vi IV V V',
                'build': 'IV IV V V', 'sprint': 'I vi IV V I vi IV V', 'sprint2': 'I vi IV V I vi IV V', 'outro': 'I I'}
# A bar is 12 triplet-eighth slots (4 beats of 3); a rhythm is one cell per beat. '-' continues a long note.
CELLS = {'q': [(0, 3)], 's': [(0, 2), (2, 1)], 't': [(0, 1), (1, 1), (2, 1)], 'e': [(0, 1), (2, 1)], 'p': [(2, 1)],
         'r': [], '-': [], 'h': [(0, 6)], 'D': [(0, 9)], 'W': [(0, 12)]}
POOLS = {
    'A': dict(calm=['s s q q', 'q s q s', 's q s q', 'q q s s', 'e q s q'], busy=['t q s q', 's t q s', 't s t q'],
              half=['q s h -', 's q h -', 'q q h -'], end=['h - q r', 'W - - -', 'h - h -']),
    'B': dict(calm=['h - q q', 'q q h -', 's s h -', 'D - - q', 'q s h -'], busy=['h - t q', 's t h -', 'q t h -'],
              half=['h - h -', 'D - - q'], end=['W - - -', 'h - h -']),
    'C': dict(calm=['s s s q', 's q s s', 'q s s s'], busy=['t s t s', 's t t q', 't t s q'],
              half=['q s h -', 's s h -'], end=['s q h -', 'h - h -']),
    'sprint': dict(calm=['s s s s', 't s q s', 's t s q'], busy=['t t s s', 't s t s', 't t t q'],
                   half=['t q h -', 's s h -'], end=['s s h -', 't q h -']),
}
RANGE = {'A': (2, 9), 'B': (3, 10), 'C': (3, 9), 'sprint': (4, 10)}
# Per cup: tempo, sections, the two-bar hook that opens every A section (rhythm, pentatonic degrees: 0 = D4, 5 = D5),
# how busy the generated melody is, and the chart rules (density in notes/s after the gate; minimum gap between
# notes and the longest run of 1/3-beat gaps; minimum same-lane gap in beats; holds may overlap other lanes; chords;
# the shortest lead note, in slots, that becomes a hold).
CUPS = {
    'maiden': dict(song='race_maiden', bpm=132, seed=1320, busy=.15,
                   sections=[('intro', 4), ('A', 8), ('B', 8), ('A', 8), ('B', 8), ('build', 4), ('sprint', 8), ('outro', 2)],
                   hook=[('s s q q', [5, 3, 5, 6, 7, 5]), ('q s h -', [4, 5, 4, 2])],
                   density=1.5, min_gap=2 / 3, run=1, jack=.5, overlap=False, chords=None, hold_slots=9),
    'stakes': dict(song='race_stakes', bpm=148, seed=1480, busy=.45,
                   sections=[('intro', 4), ('A', 8), ('B', 8), ('A', 8), ('C', 8), ('build', 4), ('sprint', 8), ('outro', 2)],
                   hook=[('s q s q', [7, 6, 5, 3, 5, 7]), ('s s h -', [8, 7, 6, 4])],
                   density=2.3, min_gap=1 / 3, run=3, jack=.5, overlap=False, chords='phrase', hold_slots=6),
    'cup': dict(song='race_cup', bpm=164, seed=1640, busy=.8,
                sections=[('intro', 4), ('A', 8), ('B', 8), ('A', 8), ('C', 8), ('B', 8), ('A', 8), ('build', 8),
                          ('sprint', 8), ('sprint2', 8), ('outro', 2)],
                hook=[('t s t q', [5, 6, 7, 8, 7, 5, 6, 7, 8]), ('s t h -', [9, 8, 7, 8, 7, 5])],
                density=3.0, min_gap=1 / 3, run=6, jack=.25, overlap=True, chords='bar', hold_slots=6),
}
WEIGHT = {'intro': .6, 'A': .9, 'B': .85, 'C': 1.05, 'build': 1.0, 'sprint': 1.25, 'sprint2': 1.45}


def midi_of(d):
    return KEY + 12 * (d // 5) + PENT[d % 5]


def mtof(m):
    return 440. * 2 ** ((m - 69) / 12)


def rhythm(spec):
    return [(3 * b + o, l) for b, c in enumerate(spec.split()) for o, l in CELLS[c]]


def snap(d, tones, lo, hi):
    """The nearest degree in range whose class is a chord tone."""
    d = min(max(d, lo), hi)
    for delta in (0, -1, 1, -2, 2):
        if lo <= d + delta <= hi and (d + delta) % 5 in tones:
            return d + delta
    return d


def bar_pitches(notes, tones, first, lo, hi, rng, steps=None, end_tonic=False):
    """Degrees for a bar's notes: a pentatonic walk from `first` (or following `steps`), strong beats on chord tones."""
    out, cur = [], first
    for k, (s, l) in enumerate(notes):
        if k == 0:
            d = first
        else:
            if steps is not None and k < len(steps):
                step = steps[k]
            else:
                mid = (lo + hi) / 2
                step = int(rng.choice([-2, -1, -1, 0, 1, 1, 2]))
                if cur > mid + 2 and rng.random() < .6: step = -abs(step) or -1
                if cur < mid - 2 and rng.random() < .6: step = abs(step) or 1
            d = cur + step
        strong = s % 3 == 0 and (s % 6 == 0 or l >= 3)
        d = snap(d, tones, lo, hi) if strong or l >= 3 else min(max(d, lo), hi)
        if len(out) >= 2 and out[-1] == out[-2] == d:
            d = d + 1 if d < hi else d - 1
        out.append(d); cur = d
    if end_tonic and out:
        out[-1] = snap(out[-1], {0}, lo, hi)
    steps = [0] + [b - a for a, b in zip(out, out[1:])]
    return out, steps


def section_melody(kind, n, prog, rng, busy, hook=None):
    """Bars of (slot, length, degree): motif, its sequence, an answer and a half cadence; the motif again, a new answer
    and a full cadence. A hook replaces the first two bars."""
    pool, (lo, hi) = POOLS[kind], RANGE[kind]
    plan = ['motif', 'seq', 'answer', 'half', 'm0', 'm1', 'answer', 'end'] * (n // 8)
    bars, prev = [], (lo + hi) // 2
    for i, role in enumerate(plan):
        tones = CHORDS[prog[i]][2]
        if role in ('motif', 'seq') and hook:
            spec, degs = hook[0 if role == 'motif' else 1]
            bars.append(list(zip([s for s, _ in rhythm(spec)], [l for _, l in rhythm(spec)], degs)))
        elif role in ('m0', 'm1'):
            bars.append(list(bars[i - 4]))
        elif role == 'seq':
            notes = [(s, l) for s, l, _ in bars[i - 1]]
            first = snap(bars[i - 1][0][2] + int(rng.choice([-1, 1])), tones, lo, hi)
            degs, _ = bar_pitches(notes, tones, first, lo, hi, rng, steps=motif_steps)
            bars.append([(s, l, d) for (s, l), d in zip(notes, degs)])
        else:
            if role in ('half', 'end'):
                spec = pool[role][int(rng.integers(len(pool[role])))]
            else:
                choices = pool['busy'] if rng.random() < busy else pool['calm']
                spec = choices[int(rng.integers(len(choices)))]
            notes = rhythm(spec)
            degs, steps = bar_pitches(notes, tones, snap(prev, tones, lo, hi), lo, hi, rng, end_tonic=role == 'end')
            bars.append([(s, l, d) for (s, l), d in zip(notes, degs)])
            if role == 'motif': motif_steps = steps
        if role == 'motif' and hook:
            motif_steps = [0] + [b[2] - a[2] for a, b in zip(bars[-1], bars[-1][1:])]
        prev = bars[-1][-1][2] if bars[-1] else prev
    return bars


def build_melody(n):
    """A rising pentatonic sequence, then a triplet run up to D6 into the sprint."""
    bars = []
    for i in range(n):
        if i == n - 1:
            bars.append([(k, 1, 10 - 11 + k) for k in range(12)])
        else:
            b = 1 + round(i * 4 / max(n - 2, 1))
            bars.append([(s, l, b + o) for (s, l), o in zip(rhythm('s s s s'), (0, 2, 1, 3, 2, 4, 3, 5))])
    return bars


def groove(kind, i, n):
    """Drum hits of bar i of a section: {instrument: [(slot, velocity)]}."""
    shaker = [(s, (.9, .45, .6)[s % 3]) for s in range(12)]
    if kind == 'intro':
        return {'don': [(0, .95), (6, .75)], 'ka': [(3, .55), (9, .55)] if i >= 1 else [], 'shaker': shaker if i >= 1 else []}
    if kind in ('A', 'C'):
        return {'don': [(0, 1.), (6, .8), (11, .5)], 'shime': [(1, .35), (2, .5), (7, .35), (8, .5)],
                'ka': [(3, .6), (9, .6)], 'shaker': shaker}
    if kind == 'B':
        return {'don': [(0, .9), (6, .7)], 'shime': [(4, .3), (5, .45), (10, .3), (11, .45)], 'ka': [(3, .5), (9, .5)],
                'kane': [(0, .45), (6, .35)], 'shaker': shaker}
    if kind == 'build':
        levels = [[0, 6], [0, 3, 6, 9], [0, 2, 3, 5, 6, 8, 9, 11], list(range(12))]
        plan = [1, 1, 2, 3] if n <= 4 else [0, 1, 0, 1, 1, 2, 2, 3]
        q = (i + 1) / n
        return {'don': [(s, .45 + .5 * q * (.8 + .2 * (s % 3 == 0))) for s in levels[plan[i % len(plan)]]],
                'shaker': [(s, v * (.5 + .5 * q)) for s, v in shaker]}
    if kind in ('sprint', 'sprint2'):
        return {'don': [(0, 1.), (3, .75), (6, .9), (9, .75)], 'shime': [(s, (0, .4, .55)[s % 3]) for s in range(12) if s % 3],
                'ka': [(3, .6), (9, .6)], 'kane': [(0, .6), (3, .4), (5, .35), (6, .5), (9, .4), (11, .35)], 'shaker': shaker}
    if kind == 'outro':
        return {'don': [(0, 1.)], 'kane': [(0, .7)]} if i == 0 else {}
    return {}


def bassline(kind, i, root):
    r, f, o = 38 + root, 38 + root + 7, 50 + root
    if kind == 'intro':
        return [(0, 2, r), (2, 1, r), (6, 2, r), (8, 1, f)]
    if kind in ('A', 'C'):
        return [n for b in range(4) for n in ((3 * b, 2, r if b % 2 == 0 else f), (3 * b + 2, 1, r))]
    if kind == 'B':
        return [(0, 3, r), (3, 3, f), (6, 3, r), (9, 2, o), (11, 1, f)]
    if kind == 'build':
        return [(3 * b, 3, r) for b in range(4)]
    if kind in ('sprint', 'sprint2'):
        return [n for b in range(4) for n in ((3 * b, 2, r), (3 * b + 2, 1, o))]
    if kind == 'outro' and i == 0:
        return [(0, 12, r)]
    return []


def compose(cup):
    """The song as timed events, its sections, and its timing (count-in, start, loop points, length)."""
    spec = CUPS[cup]
    rng = np.random.default_rng(spec['seed'])
    beat = 60. / spec['bpm']; slot = beat / 3; bar_s = 4 * beat
    count_in = [PRE + k * beat for k in range(4)]
    start = PRE + 4 * beat
    events, sections, melodies, seen = [], [], {}, {}

    def at(gslot):
        n = int(round((start + gslot * slot) * SR))
        return n, n / SR

    for k, t in enumerate(count_in):
        n = int(round(t * SR))
        events.append(dict(inst='don', n=n, t=n / SR, gslot=-1, vel=(.8, .8, .8, 1.)[k], variant=k % 3, count=True, sec=-1, kind='count'))
    bar = 0
    for si, (kind, nbars) in enumerate(spec['sections']):
        prog = (PROGRESSIONS[kind].split() * 4)[:nbars]
        occ = seen[kind] = seen.get(kind, 0) + 1
        sections.append(dict(kind=kind, bar=bar, bars=nbars, t=at(bar * 12)[1]))
        if kind in POOLS or kind == 'sprint2':
            base = 'sprint' if kind == 'sprint2' else kind
            if kind not in melodies:
                if kind == 'sprint2':           # the sprint again with busier answers
                    first = melodies['sprint']
                    var = section_melody('sprint', nbars, prog, rng, 1.)
                    melodies[kind] = [first[0], first[1], var[2], first[3], first[0], first[1], var[6], first[7]]
                else:
                    melodies[kind] = section_melody(base, nbars, prog, rng, spec['busy'], hook=spec['hook'] if kind == 'A' else None)
            mel = melodies[kind]
        elif kind == 'build':
            mel = build_melody(nbars)
        elif kind == 'outro':
            mel = [[(0, 12, 5)], []]
        else:
            mel = [[] for _ in range(nbars)]
        for i in range(nbars):
            chord = prog[i]; root = CHORDS[chord][0]
            g0 = (bar + i) * 12
            for inst, hits in groove(kind, i, nbars).items():
                for s, v in hits:
                    n, t = at(g0 + s)
                    events.append(dict(inst=inst, n=n, t=t, gslot=g0 + s, vel=v, variant=(g0 + s) % 3, sec=si, kind=kind))
            for s, l, m in bassline(kind, i, root):
                n, t = at(g0 + s)
                events.append(dict(inst='bass', n=n, t=t, gslot=g0 + s, midi=m, dur=l * slot, vel=.9 if s % 3 == 0 else .7, sec=si, kind=kind))
            if kind != 'intro' or i >= 2:
                if not (kind == 'outro' and i == 1):
                    n, t = at(g0)
                    events.append(dict(inst='pad', n=n, t=t, gslot=g0, chord=chord, dur=bar_s * (1.6 if kind == 'outro' else 1.),
                                       vel=.7 + .3 * (kind == 'build') * (i + 1) / nbars, sec=si, kind=kind))
            for s, l, d in mel[i]:
                n, t = at(g0 + s)
                m = midi_of(d)
                vel = .72 + .18 * (s % 3 == 0) + .1 * (s == 0)
                events.append(dict(inst='lead', n=n, t=t, gslot=g0 + s, midi=m, deg=d, slots=l, dur=l * slot, vel=vel, sec=si, kind=kind))
                # the flute doubles the longer notes in B and the sprint, which also sustains the chart's holds
                if kind in ('B', 'sprint', 'sprint2', 'outro') and l >= 2:
                    events.append(dict(inst='flute', n=n, t=t, gslot=g0 + s, midi=m, dur=l * slot, vel=vel, sec=si, kind=kind))
            # long counter-melody tones: the intro's second half, repeated A sections and C
            if (kind == 'intro' and i >= 2) or (kind == 'A' and occ >= 2) or kind == 'C':
                n, t = at(g0)
                d = snap(8, CHORDS[chord][2], 6, 10)
                events.append(dict(inst='flute', n=n, t=t, gslot=g0, midi=midi_of(d), dur=bar_s * .96, vel=.55, sec=si, kind=kind))
        bar += nbars
    events.sort(key=lambda e: (e['n'], e['inst']))
    outro = next(s for s in sections if s['kind'] == 'outro')
    loop = sections[-2]
    length = start + bar * bar_s
    return dict(cup=cup, song=spec['song'], bpm=spec['bpm'], beat=beat, count_in=[round(int(round(t * SR)) / SR, 6) for t in count_in],
                start=round(at(0)[1], 6), length=round(length, 6), loop_from=round(loop['t'], 6), loop_to=round(outro['t'], 6),
                sections=sections, events=events)


# ---------------------------------------------------------------------------------------------------- charts
def radical_inverse(i):
    r, f = 0., .5
    while i:
        r += f * (i & 1); i >>= 1; f /= 2
    return r


def chart(song):
    """Choose the chart from the song's own lead notes and drum hits, then give each note a lane."""
    spec = CUPS[song['cup']]
    beat = song['beat']; sl = beat / 3; bar_s = 4 * beat; eps = 1e-4
    first = song['start'] + beat - eps
    groups = {}
    for e in song['events']:
        if e.get('count') or e['inst'] not in ('lead', 'don', 'ka'):
            continue
        g = groups.setdefault(e['gslot'], dict(t=e['t'], gslot=e['gslot'], sec=e['sec'], kind=e['kind']))
        g[e['inst']] = e
    groups = [g for g in sorted(groups.values(), key=lambda g: g['t']) if g['t'] >= first]
    sec_slot = {i: s['bar'] * 12 for i, s in enumerate(song['sections'])}
    for g in groups:
        pos = g['gslot'] % 12
        base = 4 if pos == 0 else 3 if pos % 3 == 0 else 2 if pos % 3 == 2 else 1
        mel = g.get('lead')
        g['hold'] = 0.
        if mel is not None:
            g['prio'] = base + 1.5
            if mel['slots'] >= spec['hold_slots'] and mel['dur'] - sl >= .4:
                g['hold'] = float(np.floor(min(1.6, mel['dur'] - sl) * 1e4) / 1e4); g['prio'] += 1
        else:
            g['prio'] = base + (.5 if 'don' in g else 0)
        rel = g['gslot'] - sec_slot[g['sec']]
        both = mel is not None and 'don' in g
        g['chord'] = both and (
            (spec['chords'] == 'phrase' and g['kind'] in ('A', 'C', 'sprint', 'sprint2') and rel % 48 == 0) or
            (spec['chords'] == 'bar' and (g['kind'] in ('A', 'B', 'C') and rel % 24 == 0 or g['kind'].startswith('sprint') and pos == 0 or
                                          g['kind'] == 'sprint2' and pos == 6)) or
            (spec['chords'] is not None and g['kind'] == 'outro'))
        if g['chord'] or g['kind'] == 'outro':
            g['prio'] += 10
    # quotas: the density target spread over the sections by weight (the sprint is densest), the outro gets its final hit
    span = song['loop_to'] - song['start']
    secs = []
    for i, s in enumerate(song['sections']):
        t0 = max(s['t'], first); t1 = s['t'] + s['bars'] * bar_s
        secs.append((i, s['kind'], max(t1 - t0, 0)))
    weighted = sum(WEIGHT.get(k, 0) * d for _, k, d in secs)
    base = spec['density'] * span / weighted
    acc_t, acc, holds = [], {}, []
    mg = spec['min_gap'] * beat; fast = .5 * beat

    def ok(g, as_hold):
        t = g['t']; i = bisect_left(acc_t, t)
        if i and t - acc_t[i - 1] < mg - eps: return False
        if i < len(acc_t) and acc_t[i] - t < mg - eps: return False
        left = 0; j = i - 1; prev = t
        while j >= 0 and prev - acc_t[j] < fast: left += 1; prev = acc_t[j]; j -= 1
        right = 0; j = i; prev = t
        while j < len(acc_t) and acc_t[j] - prev < fast: right += 1; prev = acc_t[j]; j += 1
        if left + right + 1 > spec['run'] and left + right > 0: return False
        for h0, h1 in holds:
            if h0 - eps < t < h1 + sl - eps and (not spec['overlap'] or g['chord']): return False
        if as_hold:
            t1 = t + g['hold'] + sl
            inside = [acc[x] for x in acc_t[bisect_left(acc_t, t + eps):bisect_left(acc_t, t1 - eps)]]
            if inside and (not spec['overlap'] or any(o['chord'] for o in inside)): return False
            if any(h0 < t1 and t < h1 + sl for h0, h1 in holds): return False
        return True

    plan = {}
    for i, kind, dur in secs:
        mine = [g for g in groups if g['sec'] == i]
        levels = {}
        for g in mine:
            levels.setdefault(round(g['prio'], 2), []).append(g)
        order = []
        for p in sorted(levels, reverse=True):
            order += sorted(levels[p], key=lambda g, lv=levels[p]: radical_inverse(lv.index(g)))
        quota = (2 if mine else 0) if kind == 'outro' else base * WEIGHT.get(kind, 0) * dur
        plan[i] = dict(kind=kind, order=order, quota=quota, count=0, stuck=False)
    target = spec['density'] * span
    for _ in range(4):                  # sections that run out of room hand their remaining quota to the others
        for i, p in plan.items():
            for g in p['order']:
                if p['count'] >= round(p['quota']) or (p['kind'] == 'outro' and p['count']): break
                if g['t'] in acc: continue
                hold = g['hold'] > 0 and ok(g, True)
                if not hold and not ok(g, False): continue
                if not hold: g['hold'] = 0.
                insort(acc_t, g['t']); acc[g['t']] = g
                if hold: holds.append((g['t'], g['t'] + g['hold']))
                p['count'] += 2 if g['chord'] else 1
            p['stuck'] = p['count'] < round(p['quota'])
        total = sum(p['count'] for p in plan.values())
        open_ = [p for p in plan.values() if not p['stuck'] and p['kind'] != 'outro']
        if total >= target - .5 or not open_: break
        room = sum(p['quota'] for p in open_)
        for p in open_:
            p['quota'] += (target - total) * p['quota'] / room
    chosen = [acc[t] for t in acc_t]
    return lanes(chosen, spec, beat, bar_s)


def lanes(chosen, spec, beat, bar_s):
    """Melody notes climb the lanes with the pitch (relative to the notes around them), drums sit low (don 0/1, ka 2/3),
    a chord is a don on lane 0/1 with the melody on 2/3; no lane repeats faster than the jack limit or inside a hold."""
    sl = beat / 3; eps = 1e-4
    mel = [(g['t'], g['lead']['deg']) for g in chosen if 'lead' in g]
    last = [-1e9] * 4; free = [-1e9] * 4
    prev = None; drum = {'don': 1, 'ka': 3}
    notes = []

    def usable(L, t, taken):
        return L not in taken and t >= free[L] - eps and t - last[L] >= spec['jack'] * beat - eps

    for g in chosen:
        t, taken, out = g['t'], set(), []
        parts = []
        if 'lead' in g: parts.append(('lead', g['lead']))
        if 'lead' not in g or g['chord']: parts.append(('don', g['don']) if 'don' in g else ('ka', g['ka']))
        for role, e in parts:
            if role == 'lead':
                d = e['deg']
                win = [x for tt, x in mel if abs(tt - t) <= bar_s]
                lo, hi = min(win), max(win)
                if hi - lo >= 3:
                    q = int((d - lo) / (hi - lo) * 3.999)
                elif prev:
                    q = min(max(prev[2] + int(np.sign(d - prev[1])), 0), 3)
                else:
                    q = 2 if d >= 5 else 1
                if prev and t - prev[0] <= 2 * beat:
                    pt, pd, pl = prev
                    if d > pd and q <= pl: q = min(pl + 1, 3)
                    elif d < pd and q >= pl: q = max(pl - 1, 0)
                    elif d == pd: q = pl
                opts = sorted(range(4), key=lambda L: (abs(L - q), -L if prev and d >= prev[1] else L))
                if prev and d == prev[1] and t - prev[0] < .5 * beat and prev[2] in opts:
                    opts.remove(prev[2]); opts.append(prev[2])
                if g['chord']:
                    opts = [L for L in opts if L >= 2] + [L for L in opts if L < 2]
                hold = g['hold']
            else:
                a, b = (0, 1) if role == 'don' else (2, 3)
                first = b if drum[role] == a else a
                opts = [first, a + b - first] + ([] if g['chord'] else [L for L in range(4) if L not in (a, b)])
                hold = 0.
            L = next((L for L in opts if usable(L, t, taken)), None)
            if L is None:
                continue
            taken.add(L); last[L] = t
            if hold: free[L] = t + hold + sl
            if role == 'lead': prev = (t, e['deg'], L)
            else: drum[role] = L
            out.append(dict(t=round(t, 6), lane=L, hold=round(hold, 4)))
        notes += sorted(out, key=lambda n: n['lane'])
    return notes


def chart_problems(c, cup):
    """Invariant violations of a chart entry (the pytest and the build both use this)."""
    spec = CUPS[cup]; beat = 60. / c['bpm']; eps = 1e-6
    notes, out = c['notes'], []
    if [(n['t'], n['lane']) for n in notes] != sorted((n['t'], n['lane']) for n in notes): out.append('notes not sorted')
    if any(n['lane'] not in (0, 1, 2, 3) for n in notes): out.append('lane out of range')
    if notes and notes[0]['t'] < c['start'] + beat - eps: out.append('note before start + 1 beat')
    if any(n['t'] <= max(c['count_in']) + eps for n in notes): out.append('note during count-in')
    if any(n['hold'] and not .4 - eps <= n['hold'] <= 1.6 + eps for n in notes): out.append('hold length outside 0.4-1.6 s')
    by_lane = {}
    for n in notes:
        by_lane.setdefault(n['lane'], []).append(n)
    for lane, ns in by_lane.items():
        for a, b in zip(ns, ns[1:]):
            if b['t'] < a['t'] + a['hold'] + eps: out.append(f'lane {lane} overlap at {b["t"]}')
            if b['t'] - a['t'] < spec['jack'] * beat - eps: out.append(f'lane {lane} jack at {b["t"]}')
    times = [n['t'] for n in notes]
    chords = len(times) - len(set(times))
    if spec['chords'] is None and chords: out.append('chords in an easy chart')
    if any(times.count(t) > 2 for t in set(times)): out.append('more than two notes at once')
    span = c['loop_to'] - c['start']
    density = len(notes) / span
    if abs(density - spec['density']) > .2 * spec['density']: out.append(f'density {density:.2f} far from {spec["density"]}')
    return out


def chart_entry(song, notes):
    return dict(song=song['song'], bpm=song['bpm'], beat=round(song['beat'], 6), count_in=song['count_in'], start=song['start'],
                length=song['length'], loop_from=song['loop_from'], loop_to=song['loop_to'],
                sections=[dict(kind=s['kind'], t=round(s['t'], 6), bars=s['bars']) for s in song['sections']], notes=notes)


def charts():
    """All three charts without rendering any audio (what the test regenerates)."""
    return {cup: chart_entry(s, chart(s)) for cup, s in ((cup, compose(cup)) for cup in CUPS)}


# ---------------------------------------------------------------------------------------------------- DSP helpers
def fftfilter(x, response, pad=4096):
    """Filter along axis 0 with a frequency response response(f) (real = zero phase, complex = as given)."""
    x = np.asarray(x, np.float64)
    n = len(x) + 2 * pad
    N = 1 << (n - 1).bit_length()
    f = np.fft.rfftfreq(N, 1 / SR)
    H = response(f)
    if x.ndim == 2: H = H[:, None]
    y = np.fft.irfft(np.fft.rfft(np.pad(x, [(pad, N - len(x) - pad)] + [(0, 0)] * (x.ndim - 1)), axis=0) * H, N, axis=0)
    return y[pad:pad + len(x)]


def lowpass(x, fc, order=2):
    return fftfilter(x, lambda f: 1 / np.sqrt(1 + (f / fc) ** (2 * order)))


def highpass(x, fc, order=2):
    return fftfilter(x, lambda f: 1 / np.sqrt(1 + (fc / np.maximum(f, 1e-3)) ** (2 * order)))


def bandnoise(n, lo, hi, seed):
    r = np.random.default_rng(seed)
    x = fftfilter(r.normal(size=n), lambda f: 1 / np.sqrt(1 + (lo / np.maximum(f, 1e-3)) ** 4) / np.sqrt(1 + (f / hi) ** 4), pad=0)
    return x / (np.std(x) + 1e-12)


def env(n, attack, decay):
    t = np.arange(n) / SR
    return np.minimum(t / max(attack, 1e-5), 1) * np.exp(-np.maximum(t - attack, 0) / decay)


def release(x, at, tau):
    """Damp x from `at` seconds on (a note-off)."""
    t = np.arange(len(x)) / SR
    return x * np.exp(-np.maximum(t - at, 0) / tau)


def resample(x, ratio):
    n = int(len(x) * ratio)
    return np.interp(np.arange(n) / ratio, np.arange(len(x)), x)


def phase(freq):
    return 2 * np.pi * np.cumsum(freq) / SR


def fftconv(x, h):
    n = len(x) + len(h) - 1
    N = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, N) * np.fft.rfft(h, N), N)[:len(x)]


def reverb_ir(seconds, t60, seed, lp=4500, predelay=.015):
    n = int(seconds * SR); t = np.arange(n) / SR
    r = np.random.default_rng(seed)
    x = r.normal(size=n) * np.exp(-6.9 * t / t60)
    x = .6 * lowpass(x, lp) + .4 * lowpass(x, lp / 3)            # darker as it decays
    x[:int(predelay * SR)] = 0
    return x / np.sqrt(np.sum(x ** 2))


# ---------------------------------------------------------------------------------------------------- voices
def don(variant=0, size=1.):
    """Taiko 'don': a low membrane with a falling pitch, a second mode and a soft slap."""
    n = int(1.1 * SR); t = np.arange(n) / SR
    f = 72 / size * (1 + .5 * np.exp(-t / .028)) * (1 + .01 * variant)
    body = np.sin(phase(f)) * env(n, .0015, .3)
    m2 = np.sin(phase(f * 1.59)) * env(n, .0015, .12) * .4
    m3 = np.sin(phase(f * 2.31)) * env(n, .001, .06) * .25
    m4 = np.sin(phase(f * 3.6)) * env(n, .001, .04) * .18            # the skin's ring, so small speakers hear it too
    slap = bandnoise(n, 150, 1600, 100 + variant) * env(n, .0008, .02) * .5
    return body + m2 + m3 + m4 + slap


def shime(variant=0):
    """A small high taiko: the gallop's pickups."""
    n = int(.3 * SR); t = np.arange(n) / SR
    f = 300 * (1 + .25 * np.exp(-t / .01)) * (1 + .015 * variant)
    return np.sin(phase(f)) * env(n, .001, .06) + .45 * bandnoise(n, 500, 3500, 110 + variant) * env(n, .0005, .012)


def ka(variant=0):
    """A wooden rim click ('ka')."""
    n = int(.12 * SR); t = np.arange(n) / SR
    x = np.sin(2 * np.pi * (1450 + 40 * variant) * t) * env(n, .0005, .014) + .7 * bandnoise(n, 1100, 5000, 120 + variant) * env(n, .0003, .007)
    return lowpass(x, 6500)


def shaker(variant=0):
    n = int(.1 * SR)
    return lowpass(bandnoise(n, 2500, 7500, 130 + variant) * env(n, .003, .022), 7000)


def kane(variant=0):
    """The chanchiki hand gong: a few inharmonic partials, kept low and soft."""
    n = int(.6 * SR); t = np.arange(n) / SR
    f0 = 1180 * (1 + .006 * variant)
    x = sum(a * np.sin(2 * np.pi * f0 * r * t) * env(n, .0008, d) for r, a, d in ((1, 1, .3), (2.24, .45, .14), (3.52, .22, .07), (4.61, .1, .04)))
    return lowpass(x + .3 * bandnoise(n, 2000, 6000, 140 + variant) * env(n, .0003, .004), 6500)


def pluck(midi, dur, variant=0):
    """Karplus-Strong shamisen/koto: a filtered noise burst in a lossy delay line, tuned exactly by resampling."""
    f = mtof(midi)
    a = float(np.clip(.5 * (300 / f) ** .7, .12, .5))             # loss-filter blend: high strings keep their overtones
    N = int(SR / f - a); fks = SR / (N + a)
    t60 = float(np.clip(1.8 * (440 / f) ** .4, .7, 2.8))
    g = 10 ** (-3 / (t60 * fks))
    total = int((dur + .5) * SR * f / fks) + N
    r = np.random.default_rng(int(midi * 10 + variant))
    x = np.arange(N) / N
    burst = np.where(x < .13, x / .13, (1 - x) / .87)             # the string pulled into a triangle near the bridge
    burst = burst + .35 * np.convolve(r.uniform(-1, 1, 3 * N), np.ones(3) / 3, 'same')[N:2 * N]   # and a little grit
    burst -= burst.mean()
    y = np.zeros(total + 1); y[1:N + 1] = burst
    k = N + 1
    while k < total + 1:
        m = min(N, total + 1 - k)
        y[k:k + m] = g * ((1 - a) * y[k - N:k - N + m] + a * y[k - N - 1:k - N - 1 + m])
        k += m
    y = resample(y[1:], fks / f)
    y = release(y, dur * .95, .07)[:int((dur + .4) * SR)]
    n = len(y)
    pick = bandnoise(n, 900, 4500, 150 + variant) * env(n, .0004, .004) * .25 * np.max(np.abs(y))
    return lowpass(y + pick + .04 * np.tanh(2 * y), 6000)       # a touch of shamisen buzz


def flute(midi, dur, variant=0):
    """Shinobue-like: sine partials, a small scoop up to pitch, delayed vibrato, breath and chiff."""
    f = mtof(midi); n = int((dur + .15) * SR); t = np.arange(n) / SR
    vib = 1 + .006 * np.sin(2 * np.pi * 5.4 * t) * np.clip((t - .15) / .25, 0, 1)
    ph = phase(f * vib * (1 - .018 * np.exp(-t / .04)))
    tone = np.sin(ph) + .22 * np.sin(2 * ph) + .07 * np.sin(3 * ph) + .025 * np.sin(4 * ph)
    amp = np.clip(t / .045, 0, 1) * (1 + .08 * np.clip(t / max(dur, .1), 0, 1)) * np.exp(-np.maximum(t - dur * .97, 0) / .07)
    breath = bandnoise(n, 1500, 6000, 160 + variant) * .035 * amp + bandnoise(n, 2000, 6500, 170 + variant) * env(n, .002, .03) * .12
    return lowpass(tone * amp + breath, 7000)


def bass(midi, dur, variant=0):
    f = mtof(midi); n = int((dur + .12) * SR); t = np.arange(n) / SR
    ph = phase(np.full(n, f))
    tone = np.sin(ph) + .25 * np.sin(2 * ph) + .06 * np.sin(3 * ph)
    amp = np.minimum(t / .006, 1) * (.65 + .35 * np.exp(-t / .25)) * np.exp(-np.maximum(t - dur * .92, 0) / .04)
    return lowpass(tone * amp, 1400)


def pad(chord, dur, variant=0):
    """Soft sho-like chord: detuned pairs of mellow tones with a slow swell."""
    semis = CHORDS[chord][1]
    n = int((dur + .5) * SR); t = np.arange(n) / SR
    x = np.zeros(n)
    for s in semis:
        f = mtof(50 + s)
        for det in (-.0025, .0025):
            ph = phase(np.full(n, f * (1 + det)))
            x += sum(np.sin(k * ph) / k ** 2 for k in range(1, 6))
    amp = np.clip(t / .25, 0, 1) * np.exp(-np.maximum(t - dur, 0) / .18)
    return lowpass(x * amp, 1800)


VOICES = {'don': lambda e: don(e['variant']), 'shime': lambda e: shime(e['variant']), 'ka': lambda e: ka(e['variant']),
          'shaker': lambda e: shaker(e['variant']), 'kane': lambda e: kane(e['variant']),
          'lead': lambda e: pluck(e['midi'], e['dur'], e['n'] % 2), 'flute': lambda e: flute(e['midi'], e['dur']),
          'bass': lambda e: bass(e['midi'], e['dur']), 'pad': lambda e: pad(e['chord'], e['dur'])}
STEM = {'don': 'taiko', 'shime': 'taiko', 'ka': 'ka', 'shaker': 'shaker', 'kane': 'kane', 'lead': 'lead', 'flute': 'flute', 'bass': 'bass', 'pad': 'pad'}
LEVEL = {'taiko': 0, 'bass': -3, 'lead': -1, 'flute': -7, 'pad': -14, 'shaker': -16, 'ka': -11, 'kane': -17}   # dB, active RMS
PAN = {'taiko': 0, 'bass': 0, 'lead': -.25, 'flute': .3, 'pad': 0, 'shaker': .35, 'ka': .2, 'kane': .4}
SEND = {'taiko': .1, 'bass': 0, 'lead': .22, 'flute': .32, 'pad': .35, 'shaker': .05, 'ka': .18, 'kane': .25}


# ---------------------------------------------------------------------------------------------------- mastering
K1 = ((1.53512485958697, -2.69169618940638, 1.19839281085285), (1, -1.69065929318241, .73248077421585))
K2 = ((1., -2., 1.), (1, -1.99004745483398, .99007225036621))


def k_response(f):
    z = np.exp(-2j * np.pi * f / SR)
    H = np.ones_like(z)
    for b, a in (K1, K2):
        H = H * (b[0] + b[1] * z + b[2] * z * z) / (a[0] + a[1] * z + a[2] * z * z)
    return H


def lufs(x):
    """Integrated loudness (ITU-R BS.1770: K-weighting, 400 ms blocks, absolute and relative gates)."""
    x = x if x.ndim == 2 else x[:, None]
    y = fftfilter(x, k_response)
    block, hop = int(.4 * SR), int(.1 * SR)
    c = np.concatenate([np.zeros((1, y.shape[1])), np.cumsum(y ** 2, axis=0)])
    starts = np.arange(0, len(y) - block + 1, hop)
    if not len(starts): starts = np.array([0]); block = len(y)
    power = ((c[starts + block] - c[starts]) / block).sum(axis=1)
    loud = -.691 + 10 * np.log10(np.maximum(power, 1e-20))
    gated = power[loud > -70]
    if not len(gated): return -70.
    rel = -.691 + 10 * np.log10(gated.mean()) - 10
    return float(-.691 + 10 * np.log10(power[(loud > -70) & (loud > rel)].mean()))


def limit(x, ceiling, block=32, attack=.0015, release_s=.09):
    """Look-ahead peak limiter: block gains that never exceed what any neighbouring block needs, smoothed both ways."""
    n = len(x)
    a = np.abs(x).max(axis=1)
    nb = -(-n // block)
    bp = np.pad(a, (0, nb * block - n)).reshape(nb, block).max(axis=1)
    req = np.minimum(1, ceiling / np.maximum(bp, 1e-9))
    g = req.copy()
    for s in (-3, -2, -1, 1, 2, 3):
        g = np.minimum(g, np.roll(np.pad(req, 3, constant_values=1), s)[3:-3])
    up = np.exp(block / (release_s * SR)); down = np.exp(block / (attack * SR))
    gl = np.log(g); ul, dl = np.log(up), np.log(down)
    out = gl.copy()
    for j in range(1, nb):                      # release: recover slowly
        out[j] = min(out[j], out[j - 1] + ul)
    for j in range(nb - 2, -1, -1):             # attack: start ducking a little ahead
        out[j] = min(out[j], out[j + 1] + dl)
    centres = np.arange(nb) * block + block / 2
    gain = np.interp(np.arange(n), centres, np.exp(out))
    return np.clip(x * gain[:, None], -ceiling, ceiling), float(-20 * np.log10(np.exp(out).min()))


def active_rms(x):
    block = int(.4 * SR)
    nb = len(x) // block
    if nb < 1: return float(np.sqrt(np.mean(x ** 2)) + 1e-12)
    p = (x[:nb * block].reshape(nb, block) ** 2).mean(axis=1)
    keep = p > p.max() * 1e-4
    return float(np.sqrt(p[keep].mean()) + 1e-12)


def master(mix, target=LUFS_TARGET):
    ceiling = 10 ** (CEILING_DB / 20)
    gain = 10 ** ((target - lufs(mix)) / 20)
    for _ in range(3):
        y, reduction = limit(mix * gain, ceiling)
        loud = lufs(y)
        if abs(loud - target) < .1: break
        gain *= 10 ** ((target - loud) / 20)
    return y, loud, reduction


def render_stems(song):
    """Each instrument group on its own track, levelled to LEVEL (dB of active RMS)."""
    n = int(round(song['length'] * SR))
    stems = {k: np.zeros(n) for k in LEVEL}
    cache = {}
    for e in song['events']:
        key = (e['inst'], e.get('midi'), e.get('chord'), round(e.get('dur', 0), 4), e.get('variant', e['n'] % 2 if e['inst'] == 'lead' else 0))
        if key not in cache:
            cache[key] = VOICES[e['inst']](e)
        x = cache[key] * e['vel']
        m = min(len(x), n - e['n'])
        stems[STEM[e['inst']]][e['n']:e['n'] + m] += x[:m]
    return {k: x * 10 ** ((LEVEL[k] - 20) / 20) / active_rms(x) for k, x in stems.items()}


def render(song):
    stems = render_stems(song)
    n = len(stems['lead'])
    dry = np.zeros((n, 2)); send = np.zeros(n)
    for k, x in stems.items():
        p = (PAN[k] + 1) * np.pi / 4
        dry[:, 0] += x * np.cos(p) * np.sqrt(2); dry[:, 1] += x * np.sin(p) * np.sqrt(2)
        send += x * SEND[k]
    wet = np.stack([fftconv(send, reverb_ir(1.6, 1.3, 7)), fftconv(send, reverb_ir(1.6, 1.3, 8))], axis=1)
    mix = highpass(dry + .5 * wet, 30)
    fade = int(.6 * SR)
    mix[-fade:] *= np.linspace(1, 0, fade)[:, None] ** 2
    mix[:int(.005 * SR)] *= np.linspace(0, 1, int(.005 * SR))[:, None]
    return master(mix)


# ---------------------------------------------------------------------------------------------------- race sounds
def brass(midi, dur, variant=0):
    """A soft festival horn: harmonics that brighten after the attack."""
    f = mtof(midi); n = int((dur + .2) * SR); t = np.arange(n) / SR
    ph = phase(f * (1 + .004 * np.sin(2 * np.pi * 5 * t) * np.clip((t - .2) / .3, 0, 1)))
    bright = .25 + .75 * np.clip(t / .05, 0, 1) * (.75 + .25 * np.exp(-t / .2))
    x = sum(np.sin(k * ph) / k * np.exp(-(k - 1) * .45 / bright) for k in range(1, 12))
    amp = np.clip(t / .03, 0, 1) * np.exp(-np.maximum(t - dur, 0) / .08)
    return lowpass(x * amp, 5000)


def place(out, x, at, gain=1.):
    s = int(round(at * SR)); m = min(len(x), len(out) - s)
    if m > 0: out[s:s + m] += x[:m] * gain


def with_room(x, amount=.18, seconds=1.2, t60=1.):
    return x + amount * fftconv(x, reverb_ir(seconds, t60, 9))


def babble(seconds, voices, seed, circular=True, rise=0., f0=(110, 260), formants=((600, 1.), (1250, .6), (2600, .3))):
    """Many vowel-like syllables (harmonic tones with syllable envelopes) through broad formant bands. Placed on a
    circle when `circular`, so the result loops without a seam."""
    r = np.random.default_rng(seed)
    n = int(seconds * SR); out = np.zeros(n)
    for _ in range(voices):
        L = int(r.uniform(.12, .4) * SR); tt = np.arange(L) / SR
        f = r.uniform(*f0) * (1 + rise * tt / tt[-1] + .04 * np.sin(2 * np.pi * r.uniform(2, 6) * tt))
        ph = phase(f)
        tone = sum(np.sin(k * ph + r.uniform(0, 6.28)) / k for k in range(1, 14))
        syl = np.clip(np.sin(np.pi * tt / tt[-1]), 0, 1) ** 1.5 * r.uniform(.3, 1)
        s = int(r.uniform(0, n))
        idx = (s + np.arange(L)) % n if circular else s + np.arange(L)
        keep = idx < n
        np.add.at(out, idx[keep], (tone * syl)[keep])
    shape = lambda fr: sum(g * np.exp(-.5 * ((fr - c) / (c * .35)) ** 2) for c, g in formants) + .05
    spec = np.fft.rfft(out) * shape(np.fft.rfftfreq(n, 1 / SR))
    return np.fft.irfft(spec, n)


def periodic_noise(seconds, lo, hi, seed):
    n = int(seconds * SR); r = np.random.default_rng(seed)
    f = np.fft.rfftfreq(n, 1 / SR)
    spec = (r.normal(size=len(f)) + 1j * r.normal(size=len(f))) / np.sqrt(1 + (lo / np.maximum(f, 1)) ** 4) / np.sqrt(1 + (f / hi) ** 4)
    spec[0] = 0
    x = np.fft.irfft(spec, n)
    return x / np.std(x)


def bell(f0, seconds, strikes=((0, 1.),), seed=0):
    """A bronze bell: hum, prime, tierce, quint and nominal partials with their own decays."""
    n = int(seconds * SR); out = np.zeros(n)
    partials = ((.5, .45, 2.2), (1, 1, 1.5), (1.19, .55, 1.1), (1.5, .35, .9), (2, .5, .7), (2.51, .22, .45), (3.01, .14, .3))
    for at, g in strikes:
        L = n - int(at * SR); t = np.arange(L) / SR
        x = sum(a * np.sin(2 * np.pi * f0 * r * t) * env(L, .001, d) for r, a, d in partials)
        x += .3 * bandnoise(L, 1500, 6000, seed + int(at * 100)) * env(L, .0005, .006)
        place(out, x, at, g)
    return lowpass(out, 7000)


def write_mono(cue, index, x, peak=.85, loop=False):
    x = np.asarray(x, np.float64)
    x = x / max(np.max(np.abs(x)), 1e-9) * peak
    if not loop:                                # a loop must keep its seam intact
        fade = min(int(.01 * SR), len(x) // 4)
        x[-fade:] *= np.linspace(1, 0, fade)
    d = OUT / cue; d.mkdir(parents=True, exist_ok=True)
    path = d / f'{cue}_{index:02d}.wav'
    write_wav(path, x)
    return {'file': str(path.relative_to(ROOT)), 'seconds': round(len(x) / SR, 3), 'peak_db': round(20 * np.log10(peak), 1),
            'lufs': round(lufs(x), 1)}


def write_wav(path, x):
    x = np.asarray(x)
    if not np.all(np.isfinite(x)): raise SystemExit(f'{path.name}: not finite')
    ch = 1 if x.ndim == 1 else x.shape[1]
    w = wave.open(str(path), 'wb'); w.setnchannels(ch); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(x, -1, 1) * 32767).round().astype('<i2').tobytes()); w.close()


def jingle(notes, length, drums=(), chord=None, flute_notes=(), slot=.14):
    out = np.zeros(int(length * SR))
    for s, l, m in notes:
        place(out, pluck(m, l * slot), s * slot, .8)
    for s, l, m in flute_notes:
        place(out, flute(m, l * slot), s * slot, .35)
    if chord:
        for at, name, dur in chord:
            place(out, pad(name, dur), at * slot, .06)
    for s, v in drums:
        place(out, don(int(s) % 3), s * slot, v)
    return out


def sfx():
    report = {}
    # fanfare: two horns in sixths over taiko, a pentatonic call that climbs to a held D
    slot = .14
    t1 = [(0, 1, 69), (1, 1, 69), (2, 1, 69), (3, 3, 74), (6, 1, 69), (7, 1, 74), (8, 1, 78), (9, 6, 81), (15, 1, 78), (16, 1, 81), (17, 1, 83), (18, 9, 86)]
    t2 = [(0, 1, 62), (1, 1, 62), (2, 1, 62), (3, 3, 66), (6, 1, 62), (7, 1, 66), (8, 1, 69), (9, 6, 74), (15, 1, 69), (16, 1, 74), (17, 1, 76), (18, 9, 78)]
    out = np.zeros(int(4.2 * SR))
    for s, l, m in t1: place(out, brass(m, l * slot * .95), s * slot, .55)
    for s, l, m in t2: place(out, brass(m, l * slot * .95), s * slot, .4)
    for s in (0, 3, 9, 18): place(out, don(s % 3), s * slot, .8)
    for k in range(6): place(out, shime(k % 3), (12 + k) * slot, .25 + .05 * k)
    place(out, kane(0), 18 * slot, .25); place(out, pad('I', 1.6), 18 * slot, .05)
    report['HR_Fanfare'] = [write_mono('HR_Fanfare', 1, with_room(out, .22))]
    # gate: the stall doors bang open one after another: steel plates, latches, a short rattle
    report['HR_GateClang'] = []
    for v in range(2):
        r = np.random.default_rng(300 + v)
        out = np.zeros(int(1.3 * SR))
        at = 0.
        for k in range(8):
            L = int(.9 * SR); t = np.arange(L) / SR
            f0 = r.uniform(190, 330)
            plate = sum(a * np.sin(2 * np.pi * f0 * q * t + r.uniform(0, 6)) * env(L, .0005, d) for q, a, d in
                        ((1, 1, .35), (2.43, .7, .22), (3.97, .5, .14), (5.61, .35, .09), (7.33, .2, .06)))
            latch = ka(k % 3) * 1.5
            hit = plate * r.uniform(.5, 1) + np.pad(latch, (0, L - len(latch))) + .5 * bandnoise(L, 300, 4000, 310 + k + 10 * v) * env(L, .0005, .03)
            place(out, hit, at)
            at += r.uniform(.012, .035)
        place(out, don(1, 1.3), 0, .5)
        report['HR_GateClang'].append(write_mono('HR_GateClang', v + 1, lowpass(with_room(out, .12), 8000)))
    # crowd loop: a periodic murmur (circular babble and periodic noise), seamless by construction
    seconds = 9.
    mur = babble(seconds, 900, 400)
    mur = mur / np.std(mur) + .35 * periodic_noise(seconds, 200, 2500, 401)
    n = len(mur)
    wob = periodic_noise(seconds, .1, 1.2, 402)
    mur = mur * (1 + .15 * np.tanh(wob))
    report['HR_CrowdLoop'] = [write_mono('HR_CrowdLoop', 1, mur, .5, loop=True)]
    # cheers: a swelling 'aah' with rising voices, claps and (in one) a whistle
    report['HR_CrowdCheer'] = []
    for v in range(3):
        L = 2.6; n = int(L * SR); t = np.arange(n) / SR
        x = babble(L, 260, 410 + v, circular=False, rise=.18, f0=(140, 330), formants=((750, 1.), (1200, .7), (2700, .35)))
        x = x / np.std(x)
        x += .3 * bandnoise(n, 300, 3000, 420 + v)
        swell = np.clip(t / (.35 + .1 * v), 0, 1) ** 1.5 * np.exp(-np.maximum(t - 1.2, 0) / .55)
        r = np.random.default_rng(430 + v)
        claps = np.zeros(n)
        for at in np.sort(r.uniform(.15, 2.2, 40)):
            c = bandnoise(int(.04 * SR), 900, 3500, int(at * 1000)) * env(int(.04 * SR), .0005, .008)
            place(claps, c, at, r.uniform(.3, 1))
        x = x * swell + 1.2 * claps * swell
        if v == 1:
            w = np.sin(phase(2100 * (1 + .25 * np.clip((t - .5) / .25, 0, 1) - .2 * np.clip((t - .9) / .3, 0, 1)))) * ((t > .5) & (t < 1.25)) * .5
            x += lowpass(w, 5000) * swell
        report['HR_CrowdCheer'].append(write_mono('HR_CrowdCheer', v + 1, lowpass(x, 6000), .8))
    # hooves: a dirt thud, a crunch of soil and a faint click of the shoe
    report['HR_Hoof'] = []
    for v in range(6):
        r = np.random.default_rng(500 + v)
        n = int(.25 * SR); t = np.arange(n) / SR
        f0 = r.uniform(70, 105)
        thud = np.sin(phase(f0 * (1 + .8 * np.exp(-t / .012)))) * env(n, .001, r.uniform(.045, .07))
        crunch = bandnoise(n, 250, 2200, 510 + v) * env(n, .001, r.uniform(.015, .03)) * r.uniform(.35, .55)
        click = bandnoise(n, 2000, 6000, 520 + v) * env(n, .0003, .003) * .15
        report['HR_Hoof'].append(write_mono('HR_Hoof', v + 1, lowpass(thud + crunch + click, 5000), .8))
    # hit feedback: a soft glassy A6 tick for perfect, a mellow D6 for good, a muted thud for a miss
    n = int(.15 * SR); t = np.arange(n) / SR
    perfect = np.sin(2 * np.pi * 1760 * t) * env(n, .001, .035) + .3 * np.sin(2 * np.pi * 3520 * t) * env(n, .001, .018) \
        + .2 * bandnoise(n, 3000, 8000, 600) * env(n, .0003, .002)
    report['HR_HitPerfect'] = [write_mono('HR_HitPerfect', 1, lowpass(perfect, 9000), .5)]
    good = np.sin(2 * np.pi * 1175 * t) * env(n, .002, .03) + .15 * bandnoise(n, 1500, 4000, 601) * env(n, .0005, .003)
    report['HR_HitGood'] = [write_mono('HR_HitGood', 1, lowpass(good, 5000), .4)]
    n = int(.22 * SR); t = np.arange(n) / SR
    miss = np.sin(phase(70 * (1 + .6 * np.exp(-t / .02)))) * env(n, .002, .06) + .4 * bandnoise(n, 80, 600, 602) * env(n, .001, .03)
    report['HR_Miss'] = [write_mono('HR_Miss', 1, lowpass(miss, 1500), .5)]
    # spur: a whoosh whose band sweeps up, and a small bell
    n = int(.8 * SR); t = np.arange(n) / SR
    hop = int(.01 * SR); win = np.hanning(2 * hop)
    whoosh = np.zeros(n + 2 * hop)
    for k, s in enumerate(range(0, int(.55 * SR), hop)):
        c = 500 * (2500 / 500) ** (s / (.55 * SR))
        whoosh[s:s + 2 * hop] += bandnoise(2 * hop, c * .6, c * 1.6, 700 + k) * win
    whoosh = whoosh[:n] * np.sin(np.pi * np.clip(t / .55, 0, 1)) ** 2
    ring = np.zeros(n); L = n - int(.12 * SR); tt = np.arange(L) / SR
    place(ring, sum(a * np.sin(2 * np.pi * 2350 * q * tt) * env(L, .001, d) for q, a, d in ((1, 1, .35), (2.76, .35, .15), (5.4, .12, .06))), .12)
    report['HR_Spur'] = [write_mono('HR_Spur', 1, lowpass(.8 * whoosh + .45 * ring, 9000), .75)]
    report['HR_Countdown'] = [write_mono('HR_Countdown', 1, don(0)[:int(1. * SR)], .85)]
    report['HR_FinishBell'] = [write_mono('HR_FinishBell', 1, bell(587.3, 2.5, ((0, 1.), (.42, .7))), .8)]
    # win: a bright run up to D6 over a D chord, a taiko roll and a final don; lose: a slow fall to a soft D
    win = jingle([(0, 1, 74), (1, 1, 76), (2, 1, 78), (3, 2, 81), (5, 1, 83), (6, 2, 86), (8, 1, 83), (9, 9, 86)], 3.2,
                 drums=[(0, .8), (3, .6), (6, .8), (9, 1.)] + [(12 + k * .5, .25 + .03 * k) for k in range(6)] + [(15, .9)],
                 chord=[(0, 'I', .8), (6, 'IV', .4), (9, 'I', 1.6)], flute_notes=[(9, 9, 86)])
    report['HR_Win'] = [write_mono('HR_Win', 1, with_room(win, .2)[:int(3. * SR)], .85)]
    lose = jingle([(0, 2, 81), (2, 2, 78), (4, 2, 76), (6, 3, 74), (9, 3, 71), (12, 6, 74)], 2.6, drums=[(12, .35)],
                  chord=[(0, 'IV', 1.2), (12, 'I', 1.2)], slot=.15)
    report['HR_Lose'] = [write_mono('HR_Lose', 1, with_room(lose, .25)[:int(2.5 * SR)], .7)]
    return report


# ---------------------------------------------------------------------------------------------------- checks
def onset_envelope(mono, hop=256, size=1024):
    frames = 1 + (len(mono) - size) // hop
    idx = np.arange(size)[None, :] + hop * np.arange(frames)[:, None]
    mags = np.log1p(np.abs(np.fft.rfft(mono[idx] * np.hanning(size), axis=1)) * 10)
    flux = np.maximum(np.diff(mags, axis=0), 0).sum(axis=1)
    times = (np.arange(1, frames) * hop + size / 2) / SR
    return times, flux / (flux.mean() + 1e-12)


def onset_check(stereo, c):
    """Onset strength at the chart's notes against random times after the gate, and where the sound starts at each note."""
    times, flux = onset_envelope(stereo.mean(axis=1))

    def strength(ts, lag=0.):
        out = []
        for t in ts:
            a, b = np.searchsorted(times, [t + lag - .012, t + lag + .03])
            out.append(flux[a:b].max() if b > a else 0)
        return np.array(out)

    nt = np.array(sorted({n['t'] for n in c['notes']}))
    r = np.random.default_rng(99)
    rt = r.uniform(c['start'] + c['beat'], c['loop_to'], 2000)
    on, off = strength(nt), strength(rt)
    # where the signal's energy (1 ms causal window of its first difference) first jumps above 4x its level 10-20 ms
    # before the note: 0 ms means the note sits on the sample where the sound starts
    mono = stereo.mean(axis=1)
    e = np.convolve(np.diff(mono, prepend=0) ** 2, np.ones(48) / 48)[:len(mono)]
    rises = []
    for t in nt:
        s = int(round(t * SR)); seg = e[s - 480:s + 960]; before = e[s - 960:s - 480].mean() + 1e-12
        if np.any(seg > 4 * before): rises.append((np.argmax(seg > 4 * before) - 480) / SR * 1000)
    return dict(notes_mean=round(float(on.mean()), 2), random_mean=round(float(off.mean()), 2), ratio=round(float(on.mean() / off.mean()), 2),
                above_random_median=round(float((on > np.median(off)).mean()), 3),
                onset_rise_ms=dict(median=round(float(np.median(rises)), 2), p95_abs=round(float(np.percentile(np.abs(rises), 95)), 2),
                                   found=len(rises), notes=len(nt)))


def spectrum(stereo):
    m = stereo.mean(axis=1)
    p = np.abs(np.fft.rfft(m)) ** 2; f = np.fft.rfftfreq(len(m), 1 / SR)
    tot = p.sum()
    return {f'above_{k}k': round(float(p[f > k * 1000].sum() / tot), 4) for k in (5, 10)} | \
           {'below_150': round(float(p[f < 150].sum() / tot), 3)}


def mp3(wav, mp3_path):
    if not shutil.which('ffmpeg'): return False
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(wav), '-codec:a', 'libmp3lame', '-q:a', '3', str(mp3_path)], check=True)
    return True


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'music').mkdir(exist_ok=True)
    preview = OUT / 'preview'; preview.mkdir(exist_ok=True)
    all_charts, music, checks = {}, {}, {}
    tick = np.sin(2 * np.pi * 1760 * np.arange(int(.08 * SR)) / SR) * env(int(.08 * SR), .001, .025)
    for cup in CUPS:
        song = compose(cup)
        notes = chart(song)
        entry = chart_entry(song, notes)
        problems = chart_problems(entry, cup)
        if problems: raise SystemExit(f'{cup} chart: {problems[:5]}')
        all_charts[cup] = entry
        print(f'{cup}: composed {len(song["events"])} events, {len(notes)} chart notes; rendering', flush=True)
        stereo, loud, reduction = render(song)
        path = OUT / 'music' / f'{song["song"]}.wav'
        write_wav(path, stereo)
        peak = float(20 * np.log10(np.abs(stereo).max()))
        span = entry['loop_to'] - entry['start']
        times = [n['t'] for n in notes]
        checks[cup] = dict(lufs=round(loud, 2), peak_db=round(peak, 2), limiter_max_reduction_db=round(reduction, 1),
                           spectrum=spectrum(stereo), onsets=onset_check(stereo, entry), notes=len(notes),
                           density=round(len(notes) / span, 2), chords=len(times) - len(set(times)),
                           holds=sum(1 for n in notes if n['hold']), lanes=[sum(1 for n in notes if n['lane'] == L) for L in range(4)])
        music[song['song']] = {'file': str(path.relative_to(ROOT)), 'seconds': round(len(stereo) / SR, 3), 'bpm': song['bpm'],
                               'cup': cup, 'lufs': round(loud, 2), 'peak_db': round(peak, 2)}
        print(f'{cup}: {music[song["song"]]["seconds"]} s, {loud:.2f} LUFS, peak {peak:.2f} dBFS, onsets {checks[cup]["onsets"]}', flush=True)
        mp3(path, preview / f'{song["song"]}.mp3')
        ticks = np.zeros(len(stereo))
        clicked = stereo * .75
        for nt in notes:
            p = (-.75 + .5 * nt['lane'] + 1) * np.pi / 4
            s = int(round(nt['t'] * SR)); m = min(len(tick), len(stereo) - s)
            clicked[s:s + m, 0] += tick[:m] * .2 * np.cos(p); clicked[s:s + m, 1] += tick[:m] * .2 * np.sin(p)
        tmp = preview / f'{song["song"]}_chart.wav'
        write_wav(tmp, np.clip(clicked, -.99, .99))
        if mp3(tmp, preview / f'{song["song"]}_chart.mp3'): tmp.unlink()
    (OUT / 'charts.json').write_text(json.dumps({'cups': all_charts}, indent=1) + '\n')
    print('race sounds', flush=True)
    cues = sfx()
    (OUT / 'manifest.json').write_text(json.dumps({'sample_rate': SR, 'music': music, 'charts': 'charts.json',
                                                    'loops': ['HR_CrowdLoop'], 'cues': cues}, indent=1) + '\n')
    (OUT / 'check.json').write_text(json.dumps(checks, indent=1) + '\n')
    print(json.dumps(checks, indent=1))
    print('HIPPODROME AUDIO READY', len(music), 'songs,', sum(len(v) for v in cues.values()), 'sound files')


if __name__ == '__main__':
    main()
