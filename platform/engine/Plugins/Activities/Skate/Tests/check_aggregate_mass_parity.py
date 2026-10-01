#!/usr/bin/env python3
"""Compare compound mass construction against the frozen original implementation.

Compile/run through the shared render lock and memory guard. All expected values
come from original Rust functions; this generator only supplies shared inputs.
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
from reference_build import build_probe
from session_parity import PLUGIN


def bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def corpus():
    rng = random.Random(0x82ae7508)
    cases, labels = [], []
    identity = [1., 0., 0., 0., 1., 0., 0., 0., 1.]
    mass_words = [bits(v) for v in (0., -0., -1., .1, 1., 5., 80.)]
    mass_words += [1, 0x007fffff, 0x00800000, 0x00800001]
    offset = 0

    def add(op, words, output_words, **details):
        nonlocal offset
        labels.append(dict(case=len(cases), operation=op, output_word=offset,
                           output_words=output_words, **details))
        offset += output_words
        cases.append([op, *words])

    def shape(kind):
        return [kind, *[bits(v) for v in (
            rng.uniform(.008, .25), rng.uniform(.01, .8), rng.uniform(0., .03),
            rng.uniform(.02, .3), rng.uniform(.005, .08), rng.uniform(.05, .6))]]

    def rotation(index):
        if index % 5 == 0:
            return identity
        if index % 5 == 1:
            return [.8, .6, 0., -.6, .8, 0., 0., 0., 1.]
        x, y, z, w = [rng.uniform(-1, 1) for _ in range(4)]
        scale = math.sqrt(x*x+y*y+z*z+w*w)
        x, y, z, w = [v/scale for v in (x, y, z, w)]
        return [1-2*(y*y+z*z), 2*(x*y+w*z), 2*(x*z-w*y),
                2*(x*y-w*z), 1-2*(x*x+z*z), 2*(y*z+w*x),
                2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y)]

    for index in range(1056):
        kind = index % 4
        for mass in (mass_words[index % len(mass_words)], bits(rng.uniform(.01, 120))):
            add(0, [*shape(kind), mass, bits(rng.uniform(10, 600)), bits(rng.uniform(0, 2))],
                31, shape=kind, requested_mass_word=mass)
    for kind in (4, 255):
        add(0, [*shape(kind), bits(1.), bits(30.), bits(.1)], 2, shape=kind)

    # Realistic compound shapes retain every intermediate volume moment, the
    # mutation into the center-of-mass frame, native axis order, and final inverse.
    for index in range(1024):
        count = (1, 2, 4, 8)[index % 4]
        words = [count]
        for child in range(count):
            basis = rotation(index+child)
            distance = (0., .00001, .0001, .001, .1, .4, 2., 20.)[index % 8]
            translation = [rng.uniform(-distance, distance) for _ in range(3)]
            words.extend([*shape((index+child) % 4), *map(bits, basis), *map(bits, translation)])
        mass = mass_words[index % len(mass_words)]
        words.extend([mass, bits(rng.uniform(10, 1000)), bits(rng.uniform(0, 1))])
        add(1, words, count*48+53, children=count, requested_mass_word=mass)

    for index in range(512):
        moments = [bits(rng.choice((0., -0., rng.uniform(-3, 3)))) for _ in range(16)]
        other = [bits(rng.uniform(-3, 3)) for _ in range(16)]
        add(2, [*moments, *map(bits, rotation(index)),
                *[bits(rng.uniform(-5, 5)) for _ in range(3)], *other], 32)

    for index in range(257):
        settings = [rng.uniform(.01, .08), rng.uniform(.01, .3), rng.uniform(.1, 10),
                    rng.uniform(.01, .08), rng.uniform(.04, .15), rng.uniform(.1, 2),
                    rng.uniform(.1, 2), rng.uniform(.1, 2), rng.uniform(.1, 10)]
        add(3, [int(index == 0), *map(bits, settings)], 56, stock=index == 0)

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
    reference = build_probe(output, 'aggregate-mass-reference',
                            PLUGIN/'Tests/Reference/aggregate_mass_probe.rs', args.target_dir)
    code = output/'native-source'
    if code.exists():
        shutil.rmtree(code)
    code.mkdir()
    for name in ('NativeMath.h', 'NativeMath.cpp', 'RigidBody.h', 'BodyMass.h',
                 'BodyMass.cpp', 'AggregateMass.h', 'AggregateMass.cpp'):
        shutil.copy2(PLUGIN/'Source/AtelierSkate/Private/Native'/name, code/name)
    candidate = output/'aggregate-mass-cpp'
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-exceptions',
                    '-Wall', '-Wextra', '-Werror', '-I', str(code),
                    *[str(code/name) for name in ('NativeMath.cpp', 'BodyMass.cpp', 'AggregateMass.cpp')],
                    str(PLUGIN/'Tests/Native/aggregate_mass_probe.cpp'), '-o', str(candidate)], check=True)
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
        first = next((i for i, (a, b) in enumerate(zip(expected, actual)) if a != b),
                     min(len(expected), len(actual)))//4
        label = next((entry for entry in labels if
                      entry['output_word'] <= first < entry['output_word']+entry['output_words']), None)
        report = dict(passed=False, first_word=first, case=label,
                      field_word=first-label['output_word'] if label else None,
                      reference=expected[first*4:first*4+4].hex(), cpp=actual[first*4:first*4+4].hex())
        (output/'first-divergence.json').write_text(json.dumps(report, indent=2)+'\n')
        raise AssertionError(report)
    result = dict(passed=True, cases=len(labels), output_words=output_words, output_bytes=len(actual),
                  operations=dict(Counter(c['operation'] for c in labels)),
                  sha256=hashlib.sha256(actual).hexdigest(),
                  comparison='exact primitive/compound mass, moment transforms/addition, principal axes, inverse frame, mass fallback, stock and generated wheel/truck construction')
    (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
