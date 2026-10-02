#!/usr/bin/env python3
"""Record the native skating session as a reference ("oracle") for a replacement ride system.

Builds simple collision worlds (flat ground, a quarter pipe, a halfpipe with vert walls and coping, a rail, a ledge,
a kicker, a wall), plays scripted pad recipes for every mechanic and trick through complete GameplaySessions with
the ride recorder (Tests/Native/ride_oracle_recorder.cpp, built by build_ride_oracle.py), keeps the full per-tick
traces and condenses them into a compact reference: input recipes, clip sequences and measured numbers.

    python3 ride_oracle.py --recorder BIN --package DATA --traces DIR --reference FILE [--only PATTERN]

Run it under the render lock and memory guard (atelier.safety.guarded), after build_ride_oracle.py.
Native space is metres, x left, y up, z forward; a tick is 1/60 s.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fnmatch
import gzip
import json
import math
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ride_oracle_scenarios as scenarios  # noqa: E402
import ride_oracle_analysis as analysis  # noqa: E402


def write_world(path, world):
    lines = []
    for a, b, c in world['triangles']:
        lines.append('T ' + ' '.join(f'{v:.6g}' for v in (*a, *b, *c)))
    for rail in world['rails']:
        lines.append(f'R {len(rail)} ' + ' '.join(f'{v:.6g}' for p in rail for v in p))
    path.write_text('\n'.join(lines) + '\n')


def commands_for(case, worlds, traces):
    tune = case['tune']
    out = traces / (case['name'].replace('/', '__') + '.jsonl')
    lines = [f"world {worlds / (case['world'] + '.txt')}",
             'tune {difficulty} {goofy:d} {trucks} {pop} {spin} {speed} {power} {vert}'.format(**tune),
             'start {} {} {} {} {} {} {} {} {}'.format(case['name'], out, *case['spawn'], case['heading'],
                                                      *case['velocity'])]
    for pad in scenarios.expand(case):
        lines.append('p ' + ' '.join(str(int(v)) for v in pad))
    lines.append('end')
    return lines, out


def run_batch(recorder, package, cases, worlds, traces, log):
    lines, outputs = [], []
    for case in cases:
        more, out = commands_for(case, worlds, traces)
        lines += more
        outputs.append(out)
    lines.append('quit')
    with log.open('w') as err:
        result = subprocess.run([str(recorder), str(package)], input='\n'.join(lines) + '\n', text=True,
                                stdout=subprocess.PIPE, stderr=err)
    finished = result.stdout.count('done')
    for out in outputs[:finished]:
        data = out.read_bytes()
        with gzip.open(str(out) + '.gz', 'wb') as packed:
            packed.write(data)
        out.unlink()
    if result.returncode or 'error' in result.stdout:
        raise RuntimeError(f'recorder failed ({result.returncode}): {result.stdout[-2000:]}')


def run_clips(recorder, package, names, traces, log):
    folder = traces / 'clips'
    folder.mkdir(parents=True, exist_ok=True)
    lines = [f'clip {name} {folder / (name + ".jsonl")}' for name in names] + ['quit']
    with log.open('w') as err:
        result = subprocess.run([str(recorder), str(package)], input='\n'.join(lines) + '\n', text=True,
                                stdout=subprocess.PIPE, stderr=err)
    if result.returncode or 'error' in result.stdout:
        raise RuntimeError(f'clip dump failed: {result.stdout[-2000:]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recorder', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True, help='the native data bundle (SkateNative)')
    parser.add_argument('--traces', type=Path, required=True, help='folder for full traces (ignored build output)')
    parser.add_argument('--reference', type=Path, required=True, help='the compact reference.json to write')
    parser.add_argument('--only', default='*', help='record only scenarios matching these comma-separated globs')
    parser.add_argument('--jobs', type=int, default=3)
    parser.add_argument('--analyse-only', action='store_true', help='rebuild the reference from existing traces')
    args = parser.parse_args()
    traces = args.traces.resolve()
    worlds = traces / 'worlds'
    worlds.mkdir(parents=True, exist_ok=True)
    patterns = args.only.split(',')
    cases = [c for c in scenarios.all_cases() if any(fnmatch.fnmatch(c['name'], p) for p in patterns)]
    if not args.analyse_only:
        for name, world in scenarios.worlds().items():
            write_world(worlds / f'{name}.txt', world)
        started = time.monotonic()
        batches = [b for b in (cases[i::args.jobs] for i in range(args.jobs)) if b]
        for stale in traces.glob('*.jsonl'):
            stale.unlink()
        with ThreadPoolExecutor(args.jobs) as pool:
            list(pool.map(lambda ib: run_batch(args.recorder, args.package, ib[1], worlds, traces,
                                               traces / f'recorder-{ib[0]}.log'), enumerate(batches)))
        run_clips(args.recorder, args.package, scenarios.CLIPS_TO_DUMP, traces, traces / 'recorder-clips.log')
        print(f'recorded {len(cases)} scenarios in {time.monotonic() - started:.0f} s', flush=True)
    reference = analysis.build_reference(scenarios.all_cases(), traces, scenarios)
    args.reference.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(reference, separators=(',', ':'), allow_nan=False)
    args.reference.write_text(text + '\n')
    print(f'wrote {args.reference} ({len(text) / 1e6:.2f} MB)')


if __name__ == '__main__':
    main()
