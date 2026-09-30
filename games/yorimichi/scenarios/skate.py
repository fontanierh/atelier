#!/usr/bin/env python3
"""Shared live-bridge helpers and entry point for the recovered skating runtime checks."""
import argparse, json, sys, time
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world')); import yori  # noqa: E402
from atelier import live as bridge  # noqa: E402

def py(code):
    out = bridge.request('/python', code)
    if not out.get('ok'): raise RuntimeError(out.get('result', '') + out.get('output', ''))
    return out.get('output', '')


def parse(state):
    head, _, rest = state.partition(' | ')
    f = {}
    for kv in head.split(' '):
        if '=' in kv and not kv.startswith('flick'): k, v = kv.split('=', 1); f[k] = v
    parts = state.split(' | ')
    f['combo'] = parts[1][6:] if len(parts) > 1 else ''
    tail = ' '.join(parts[2:])
    for kv in tail.split(' '):
        if '=' in kv: k, v = kv.split('=', 1); f.setdefault(k, v)
    return f


def run_scenario(args, seconds):
    py(f'live.scenario({args})')
    time.sleep(seconds + .6)
    rows = json.loads(py('import json; live.stop("rec"); print(json.dumps(live.REC))').strip().splitlines()[-1])
    return [parse(r) for r in rows]


def modes(rows): return {r.get('mode') for r in rows}
def ever(rows, key, value): return any(r.get(key) == value for r in rows)
def combos(rows): return ' / '.join(dict.fromkeys(r['combo'] for r in rows if r.get('combo')))
def count(rows, key): return int(rows[-1].get(key, 0)) - int(rows[0].get(key, 0))


def settle(minimum=50., seconds=3., limit=300.):
    """Wait for a steady frame rate: a fresh project compiles shaders for minutes, and the mouse cases read gestures
    frame by frame."""
    start = time.monotonic(); steady = None
    while time.monotonic() - start < limit:
        fps = bridge.request('/state').get('fps', 0)
        steady = steady or (time.monotonic() if fps >= minimum else None)
        if fps < minimum: steady = None
        if steady and time.monotonic() - steady >= seconds: return
        time.sleep(.25)
    print(f'warning: frame rate still under {minimum:.0f} fps after {limit:.0f} s', flush=True)



if __name__ == '__main__':
    import skate_runtime
    try:
        raise SystemExit(skate_runtime.main())
    finally:
        skate_runtime.release_controls()
