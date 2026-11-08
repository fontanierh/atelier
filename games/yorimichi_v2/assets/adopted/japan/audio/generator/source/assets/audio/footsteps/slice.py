#!/usr/bin/env python3
"""Turn raw Sonniss footstep recordings into game-ready single-step WAVs.

The bundle files are library masters: 96/192 kHz, 24-bit, and mostly long
performances (a 40 s run across leaves). Unreal wants short mono one-shots at a
sane rate, so this:

  1. converts each source to 48 kHz / 16-bit / mono via ffmpeg
  2. finds each footfall with an RMS envelope and slices it out
  3. trims, fades and peak-normalises every slice to a consistent level

Output: japan/audio/footsteps/<surface>/<surface>_<stem>_<nn>.wav

Usage:  python3 tools/slice_footsteps.py [--surface grass] [--dry-run]
"""
import argparse, json, subprocess, sys, wave
from pathlib import Path

import numpy as np

import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from atelier.paths import cache_dir  # noqa: E402
ROOT = yori.OUT
SRC = cache_dir('sonniss', 'footsteps')
DST = ROOT / 'audio' / 'footsteps'
TMP = ROOT / 'audio' / '.tmp'

RATE = 48_000
TARGET_PEAK = 10 ** (-3.0 / 20)      # -3 dBFS
MIN_GAP_S = 0.11                     # closest two footfalls can be
MAX_STEP_S = 0.60                    # hard cap on one slice
PRE_ROLL_S = 0.012                   # keep a little air before the transient
FADE_IN_S = 0.003
FADE_OUT_S = 0.030
MIN_KEEP_S = 0.07                    # shorter than this is a clipped step, not a step
HOP = 96                             # 2 ms envelope hop at 48 kHz

# Sources that are already a single footfall: trim and normalise, do not slice.
SINGLE_HINTS = ('single', 'crouch', 'ground_walk')


def to_mono_48k(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ['ffmpeg', '-v', 'error', '-y', '-i', str(src),
         '-ac', '1', '-ar', str(RATE), '-sample_fmt', 's16', str(dst)],
        check=True)


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), 'rb') as w:
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype='<i2').astype(np.float32) / 32768.0


def write_wav(path: Path, x: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(x, -1.0, 1.0)
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes((pcm * 32767).astype('<i2').tobytes())


def envelope(x: np.ndarray) -> np.ndarray:
    """Short-time RMS, one value per HOP samples."""
    n = len(x) // HOP
    if n == 0:
        return np.zeros(1, dtype=np.float32)
    blocks = x[: n * HOP].reshape(n, HOP)
    return np.sqrt((blocks ** 2).mean(axis=1) + 1e-12)


def find_steps(x: np.ndarray) -> list[tuple[int, int]]:
    """Return (start, end) sample ranges, one per footfall."""
    env = envelope(x)
    floor = np.percentile(env, 20)
    peak = env.max()
    if peak <= floor * 2:
        return []
    thresh = max(floor * 4.0, peak * 0.16)
    gate = peak * 0.06                       # where a step has decayed away

    min_gap = int(MIN_GAP_S * RATE / HOP)
    candidates = []
    i = 0
    while i < len(env):
        if env[i] >= thresh:
            # local peak of this burst
            j = i
            while j < len(env) and env[j] >= gate:
                j += 1
            burst = env[i:j]
            if len(burst):
                candidates.append(i + int(np.argmax(burst)))
            i = max(j, i + min_gap)
        else:
            i += 1

    spans = []
    for n, p in enumerate(candidates):
        # never let one slice run into the next footfall
        next_p = candidates[n + 1] if n + 1 < len(candidates) else len(env)
        local = env[p]
        s = p
        while s > 0 and env[s] > local * 0.12 and (p - s) * HOP < 0.05 * RATE:
            s -= 1
        limit = min(len(env) - 1, next_p - int(0.02 * RATE / HOP))
        e = p
        while e < limit and env[e] > local * 0.05 and (e - p) * HOP < MAX_STEP_S * RATE:
            e += 1
        start = max(0, s * HOP - int(PRE_ROLL_S * RATE))
        end = min(len(x), next_p * HOP - int(0.01 * RATE),
                  e * HOP + int(FADE_OUT_S * RATE))
        if end - start < 0.035 * RATE:
            continue
        if spans and start < spans[-1][1] - int(0.02 * RATE):
            continue                          # overlaps the previous slice
        spans.append((start, end))
    return spans


def shape(seg: np.ndarray) -> np.ndarray | None:
    seg = seg.copy()
    pk = np.abs(seg).max()
    if pk < 1e-4 or len(seg) < MIN_KEEP_S * RATE:
        return None
    # a footfall is an attack then a decay; if the loudest moment is in the back
    # half we clipped into the next step instead of capturing this one
    if int(np.argmax(np.abs(seg))) > 0.55 * len(seg):
        return None
    fi, fo = int(FADE_IN_S * RATE), min(int(FADE_OUT_S * RATE), len(seg) // 2)
    if fi and len(seg) > fi:
        seg[:fi] *= np.linspace(0, 1, fi, dtype=np.float32)
    if fo:
        seg[-fo:] *= np.linspace(1, 0, fo, dtype=np.float32)
    return seg * (TARGET_PEAK / pk)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--surface', help='only process this surface folder')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    sources = sorted(p for p in SRC.rglob('*.wav'))
    if args.surface:
        sources = [p for p in sources if p.parent.name == args.surface]
    if not sources:
        print(f'no sources under {SRC}', file=sys.stderr)
        return 1

    manifest = []
    for src in sources:
        surface = src.parent.name
        stem = src.stem
        to_mono_48k(src, TMP / surface / f'{stem}.wav')
        x = read_wav(TMP / surface / f'{stem}.wav')

        if any(h in stem for h in SINGLE_HINTS):
            spans = find_steps(x)[:1] or [(0, len(x))]
        else:
            spans = find_steps(x)

        kept = 0
        for start, end in spans:
            seg = shape(x[start:end])
            if seg is None:
                continue
            kept += 1
            out = DST / surface / f'{surface}_{stem}_{kept:02d}.wav'
            if not args.dry_run:
                write_wav(out, seg)
            manifest.append({
                'surface': surface,
                'file': str(out.relative_to(ROOT)),
                'source': 'sonniss/footsteps/' + str(src.relative_to(SRC)),
                'source_offset_s': round(start / RATE, 3),
                'duration_s': round(len(seg) / RATE, 3),
            })
        print(f'{surface:12s} {stem:42s} -> {kept:3d} steps')

    if not args.dry_run:
        (DST / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    per = {}
    for m in manifest:
        per[m['surface']] = per.get(m['surface'], 0) + 1
    print('\n' + '  '.join(f'{k}:{v}' for k, v in sorted(per.items())))
    print(f'{len(manifest)} one-shots -> {DST}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
