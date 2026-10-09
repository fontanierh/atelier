#!/usr/bin/env python3
"""Verify board child geometry and mass against the frozen original constructor.

Run compilation and comparison through the shared render lock/memory guard.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
from check_aggregate_mass_parity import bits
from reference_build import build_probe
from session_parity import PLUGIN


def corpus():
    rng = random.Random(0x82c09290)
    cases, labels = [], []
    offset = 0

    def add(op, words, size, **details):
        nonlocal offset
        labels.append(dict(case=len(cases), operation=op, output_word=offset, output_words=size, **details))
        offset += size
        cases.append([op, *words])

    stock = [0x3e75c28f, 0x3f170a3d, 0x3c75c28f, 0x3e28f5c3, 0x41500000, 0x41480000, 5, 1, 1]
    add(0, [1, *stock, bits(6.), bits(27.)], 47+44*15, stock=True)
    for index in range(384):
        count = (-3, 0, 1, 2, 3, 5, 8, 12)[index % 8]
        settings = [bits(v) for v in (rng.uniform(.18, .32), rng.uniform(.45, .8),
                    rng.uniform(.008, .025), rng.uniform(.09, .24),
                    rng.uniform(-10, 30), rng.uniform(-10, 30))]
        settings += [count & 0xffffffff, (index//8) % 2, (index//16) % 2]
        add(0, [0, *settings, bits((0., -1., 3., 6., 12.)[index % 5]), bits(rng.uniform(0, 60))],
            47+44*(5+2*max(0, count)), children=5+2*max(0, count))
    for flags in range(4):
        settings = [*stock[:7], flags & 1, (flags >> 1) & 1]
        add(0, [0, *settings, bits(6.), bits(27.)], 47+44*15, collision_toggles=flags)

    # Explicit child transforms are independent from deck generation; triangle
    # mass must ignore them, while every primitive must apply them exactly once.
    for index in range(512):
        kind = index % 4
        if kind == 0:
            payload = [bits(v) for v in (.1, .007, .3, rng.uniform(0, .01))]
        elif kind == 1:
            payload = [bits(rng.uniform(.003, .02)), bits(rng.uniform(.1, .5))]
        elif kind == 2:
            payload = [bits(rng.uniform(.01, .1))]
        else:
            payload = [bits(rng.uniform(-2, 2)) for _ in range(9)]
            payload += [bits(rng.uniform(.001, .1)), bits(1.), bits(-1.), bits(1.), rng.getrandbits(32)]
        payload += [0]*(14-len(payload))
        basis = [1., 0., 0., 0., 1., 0., 0., 0., 1.] if index % 8 < 4 else [.8, .6, 0., -.6, .8, 0., 0., 0., 1.]
        add(1, [kind, *payload, *map(bits, basis), *[bits(rng.uniform(-3, 3)) for _ in range(3)], index % 2],
            44, shape=kind)
    add(2, [], 7*21, stock_assembly=True)
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
    reference = build_probe(output, 'deck-geometry-reference', PLUGIN/'Tests/Reference/deck_geometry_probe.rs', args.target_dir)
    code = output/'simulation-source'
    if code.exists():
        shutil.rmtree(code)
    code.mkdir()
    for name in ('SimulationMath.h', 'SimulationMath.cpp', 'RigidBody.h', 'BodyMass.h', 'BodyMass.cpp',
                 'AggregateMass.h', 'AggregateMass.cpp', 'GeometryTypes.h', 'DeckGeometry.h', 'DeckGeometry.cpp'):
        shutil.copy2(PLUGIN/'Source/AtelierSkate/Private/Simulation'/name, code/name)
    candidate = output/'deck-geometry-cpp'
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-exceptions',
                    '-Wall', '-Wextra', '-Werror', '-I', str(code),
                    *[str(code/name) for name in ('SimulationMath.cpp', 'BodyMass.cpp', 'AggregateMass.cpp', 'DeckGeometry.cpp')],
                    str(PLUGIN/'Tests/Simulation/deck_geometry_probe.cpp'), '-o', str(candidate)], check=True)
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
                  comparison='exact deck child order/shapes/transforms/flags, per-child and aggregate volume moments, final deck override and seven stock body masses')
    (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
