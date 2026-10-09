#!/usr/bin/env python3
"""Verify authored board poses and relative drive frames with the frozen original.

Run compilation and comparison through the shared render lock/memory guard.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
from check_aggregate_mass_parity import bits
from reference_build import build_probe
from session_parity import PLUGIN


def corpus():
    rng = random.Random(0x82c0c088)
    cases, labels = [], []
    offset = 0

    def add(op, words, size, **details):
        nonlocal offset
        labels.append(dict(case=len(cases), operation=op, output_word=offset, output_words=size, **details))
        offset += size
        cases.append([op, *words])

    def basis(index):
        if index % 5 == 0:
            return [1., 0., 0., 0., 1., 0., 0., 0., 1.]
        x, y, z, w = [rng.uniform(-1, 1) for _ in range(4)]
        norm = math.sqrt(x*x+y*y+z*z+w*w)
        x, y, z, w = [v/norm for v in (x, y, z, w)]
        return [1-2*(y*y+z*z), 2*(x*y+w*z), 2*(x*z-w*y),
                2*(x*y-w*z), 1-2*(x*x+z*z), 2*(y*z+w*x),
                2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y)]

    add(0, [1, *([0]*10)], 280, stock=True)
    for index in range(384):
        settings = [rng.uniform(.3, 1.5), rng.uniform(.01, .3), rng.uniform(-.2, .1),
                    rng.uniform(-.2, .1), rng.uniform(-.1, .1), rng.uniform(.3, 1.5),
                    rng.uniform(-.2, .1), rng.uniform(-.2, .1), rng.uniform(-.1, .1), rng.uniform(-180, 180)]
        add(0, [0, *map(bits, settings)], 280)
    for index in range(1024):
        words = []
        for side in range(2):
            words.extend(map(bits, basis(index+side)))
            words.extend(bits(rng.uniform(-20, 20)) for _ in range(3))
        add(1, words, 30)
    for index in range(512):
        add(2, list(map(bits, basis(index))), 4)
    # Strict dominant-component ties and signs exercise all conversion branches.
    for diagonal in ((1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1), (0, 0, 0)):
        matrix = [0.]*9
        for i, value in enumerate(diagonal):
            matrix[i*4] = value
        add(2, list(map(bits, matrix)), 4, diagonal=diagonal)
    add(3, [], 292, stock_defaults=True)
    words = [len(cases)]
    for case in cases:
        words.extend(case)
    return struct.pack(f'<{len(words)}I', *words), labels, offset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name in ('result.json', 'first-divergence.json'):
        (output/name).unlink(missing_ok=True)
    reference = build_probe(output, 'drive-frames-reference', PLUGIN/'Tests/Reference/drive_frames_probe.rs', args.target_dir)
    code = output/'simulation-source'
    if code.exists():
        shutil.rmtree(code)
    code.mkdir()
    for name in ('SimulationMath.h', 'SimulationMath.cpp', 'RigidBody.h', 'BodyMass.h', 'BodyMass.cpp',
                 'AggregateMass.h', 'AggregateMass.cpp', 'GeometryTypes.h', 'DeckGeometry.h', 'DeckGeometry.cpp',
                 'DriveFrames.h', 'DriveFrames.cpp'):
        shutil.copy2(PLUGIN/'Source/AtelierSkate/Private/Simulation'/name, code/name)
    candidate = output/'drive-frames-cpp'
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-exceptions',
                    '-Wall', '-Wextra', '-Werror', '-I', str(code),
                    *[str(code/name) for name in ('SimulationMath.cpp', 'BodyMass.cpp', 'AggregateMass.cpp', 'DeckGeometry.cpp', 'DriveFrames.cpp')],
                    str(PLUGIN/'Tests/Simulation/drive_frames_probe.cpp'), '-o', str(candidate)], check=True)
    source, labels, output_words = corpus()
    (output/'inputs.bin').write_bytes(source)
    (output/'cases.json').write_text(json.dumps(labels, indent=2)+'\n')
    expected = subprocess.check_output([str(reference)], input=source)
    actual = subprocess.check_output([str(candidate)], input=source)
    (output/'reference.bin').write_bytes(expected)
    (output/'candidate.bin').write_bytes(actual)
    if len(expected) != output_words*4:
        raise AssertionError(f'Wrong oracle output size: {len(expected)} != {output_words*4}')
    if expected != actual:
        first = next((i for i, (a, b) in enumerate(zip(expected, actual)) if a != b), min(len(expected), len(actual)))//4
        label = next((entry for entry in labels if entry['output_word'] <= first < entry['output_word']+entry['output_words']), None)
        report = dict(passed=False, first_word=first, case=label, field_word=first-label['output_word'] if label else None,
                      reference=expected[first*4:first*4+4].hex(), cpp=actual[first*4:first*4+4].hex())
        (output/'first-divergence.json').write_text(json.dumps(report, indent=2)+'\n')
        raise AssertionError(report)
    result = dict(passed=True, cases=len(labels), output_words=output_words, output_bytes=len(actual),
                  operations=dict(Counter(c['operation'] for c in labels)), sha256=hashlib.sha256(actual).hexdigest(),
                  comparison='exact authored body transforms/packed poses, truck transforms, matrix-to-quaternion and parent/child relative frames including raw lanes and stock defaults')
    (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
