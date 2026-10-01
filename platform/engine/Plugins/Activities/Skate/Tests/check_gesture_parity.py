#!/usr/bin/env python3
"""Compare original Rust/PAT input with the C++ recognizer and native data, bit for bit.

Run under atelier.safety: this command compiles and executes both probes.
All generated binaries, native data, replay inputs, outputs and reports go to --output.
"""
import argparse
import bisect
import hashlib
import importlib.util
import json
from pathlib import Path
import historical_oracle as historical
import random
import struct
import subprocess

PLUGIN = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('convert_native_data', PLUGIN/'Tools/convert_native_data.py')
converter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(converter)


def corpus(sets):
    records = bytearray()
    spans = []
    def case(label):
        spans.append(dict(begin=len(records)//24, label=label))
    def sample(group, point=(0, 0), difficulty=0, misses=3, reset=False):
        records.extend(struct.pack('<IIIIff', group, 0 if reset else 1, difficulty, misses, *point))
    for group, data in enumerate(sets):
        for index, pattern in enumerate(data['patterns']):
            for difficulty in (0, 1, 2):
                for repeats in (1, 2, 3, 7):
                    for misses in (0, 1, 3, 63):
                        case(f'{data["name"]}/{index}/{pattern["name"]}/difficulty={difficulty}/repeat={repeats}/misses={misses}')
                        sample(group, reset=True)
                        sample(group, difficulty=difficulty, misses=misses)
                        for point in pattern['points']:
                            for _ in range(repeats):
                                sample(group, point, difficulty, misses)
                        for _ in range(4):
                            sample(group, pattern['points'][-1], difficulty, misses)
                        for _ in range(3):
                            sample(group, difficulty=difficulty, misses=misses)
        # Exercise the source's 10-bit elapsed and 6-bit miss counters, delayed
        # first samples, held queries before recognition, and repeated gestures.
        for misses in (3, 63, 255):
            case(f'{data["name"]}/long-hold-and-counter-wrap/{misses}')
            sample(group, reset=True)
            sample(group)
            points = data['patterns'][0]['points']
            sample(group, points[0], misses=misses)
            for _ in range(2200):
                sample(group, (10, -10), misses=misses)
            for point in points:
                sample(group, point, misses=misses)
        # Repeatable random input includes authored points and neighbourhoods;
        # uniform noise alone overwhelmingly exercises the no-match branch.
        rng = random.Random(0x534b4154 + group)
        points = [point for pattern in data['patterns'] for point in pattern['points']]
        for difficulty in (0, 1, 2):
            case(f'{data["name"]}/seeded-stream/{difficulty}')
            sample(group, reset=True)
            for frame in range(12000):
                if frame % 13 < 8:
                    point = rng.choice(points)
                    jitter = rng.choice((0, 1e-6, .025, .15, .4))
                    point = (point[0]+rng.uniform(-jitter, jitter), point[1]+rng.uniform(-jitter, jitter))
                else:
                    point = (rng.uniform(-1, 1), rng.uniform(-1, 1))
                sample(group, point, difficulty, (0, 1, 3, 63)[frame//3000])
    return bytes(records), spans


def execute(command, output, source=None):
    with output.open('wb') as stdout:
        if source is None:
            subprocess.run(command, stdout=stdout, check=True)
        else:
            with source.open('rb') as stdin:
                subprocess.run(command, stdin=stdin, stdout=stdout, check=True)
    return output.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = args.assets.resolve()/'private/stock/data/joystick'
    sets = converter.gesture_sets(source)
    native = output/'gestures.skate'
    native.write_bytes(converter.encode_gestures(sets))
    cpp = output/'gesture-cpp'
    rust = output/'gesture-reference'
    code = PLUGIN/'Source/AtelierSkate/Private/Native'
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math', '-Wall', '-Wextra', '-Werror',
                    '-I', str(code), str(code/'Gestures.cpp'), str(PLUGIN/'Tests/Native/gesture_probe.cpp'),
                    '-o', str(cpp)], check=True)
    rust_source = historical.stage_path_probe(PLUGIN/'Tests/Reference/gesture_probe.rs', output, {
        '../../ThirdParty/skate-runtime/crates/skate-core/src/input/gesture.rs': 'crates/skate-core/src/input/gesture.rs',
        '../../ThirdParty/skate-runtime/crates/skate-data/src/gesture_patterns.rs': 'crates/skate-data/src/gesture_patterns.rs'})
    subprocess.run(['rustc', '+1.97.1', '--edition=2024', '-O', str(rust_source),
                    '-o', str(rust)], check=True)
    reference_data = execute([str(rust), str(source), 'dump'], output/'reference-data.bin')
    cpp_data = execute([str(cpp), str(native), 'dump'], output/'cpp-data.bin')
    if reference_data != native.read_bytes() or cpp_data != reference_data:
        raise AssertionError('Native conversion or C++ loading changed the source patterns')
    stream, spans = corpus(sets)
    replay = output/'input.bin'
    replay.write_bytes(stream)
    (output/'cases.json').write_text(json.dumps(spans, indent=2)+'\n')
    reference = execute([str(rust), str(source), 'replay'], output/'reference.bin', replay)
    actual = execute([str(cpp), str(native), 'replay'], output/'cpp.bin', replay)
    count = len(stream)//24
    if len(reference) != count*20 or len(actual) != len(reference):
        raise AssertionError(f'Output count mismatch: {count=}, {len(reference)=}, {len(actual)=}')
    if actual != reference:
        first = next(i for i, (a, b) in enumerate(zip(actual, reference)) if a != b)//20
        case = spans[bisect.bisect_right([s['begin'] for s in spans], first)-1]
        details = dict(first_record=first, case=case,
                       input=struct.unpack_from('<IIIIff', stream, first*24),
                       reference_words=struct.unpack_from('<IIIII', reference, first*20),
                       cpp_words=struct.unpack_from('<IIIII', actual, first*20))
        (output/'first-divergence.json').write_text(json.dumps(details, indent=2)+'\n')
        raise AssertionError(details)
    # A decoder must reject truncated/extended data instead of partially installing it.
    for index, malformed in enumerate((b'', native.read_bytes()[:11], native.read_bytes()[:-1], native.read_bytes()+b'\0')):
        bad = output/f'invalid-{index}.skate'
        bad.write_bytes(malformed)
        result = subprocess.run([str(cpp), str(bad), 'dump'], capture_output=True)
        if result.returncode != 2:
            raise AssertionError('C++ loader accepted malformed native data')
    matches = sum(struct.unpack_from('<I', reference, i*20+4)[0] != 0xffffffff for i in range(count))
    if matches == 0:
        raise AssertionError('Replay did not exercise recognition')
    report = dict(passed=True, comparison='exact output bytes; no floating-point tolerance',
                  patterns=sum(len(group['patterns']) for group in sets), cases=len(spans), records=count, matches=matches,
                  native_data_sha256=hashlib.sha256(reference_data).hexdigest(),
                  inputs_sha256=hashlib.sha256(stream).hexdigest(), outputs_sha256=hashlib.sha256(reference).hexdigest(),
                  reference_sources={'ThirdParty/skate-runtime/'+relative: hashlib.sha256(historical.source_bytes(relative)).hexdigest() for relative in (
                      'crates/skate-core/src/input/gesture.rs',
                      'crates/skate-data/src/gesture_patterns.rs')})
    (output/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    historical.run_cli(main)
