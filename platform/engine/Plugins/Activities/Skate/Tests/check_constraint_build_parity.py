#!/usr/bin/env python3
"""Compare complete joint/drive construction and packed rows with frozen Rust.

Run under the shared render lock/memory guard. Expected records come from the
original public builders and the byte-identical private production packer.
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
    rng = random.Random(0x82ae3bc8)
    cases, labels = [], []
    offset = 0

    def add(op, words, size, **details):
        nonlocal offset
        labels.append(dict(case=len(cases), operation=op, output_word=offset, output_words=size, **details))
        offset += size
        cases.append([op, *words])

    def quat(index):
        if index % 13 == 0:
            return [0., 0., 0., 1.]
        values = [rng.uniform(-1, 1) for _ in range(4)]
        norm = math.sqrt(sum(v*v for v in values))
        return [v/norm for v in values]

    def basis(q):
        x, y, z, w = q
        return [1-2*(y*y+z*z), 2*(x*y+w*z), 2*(x*z-w*y),
                2*(x*y-w*z), 1-2*(x*x+z*z), 2*(y*z+w*x),
                2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y)]

    def body(index, state, q=None):
        q = quat(index) if q is None else q
        # Basis is an independent source field, not recomputed by the candidate.
        b = basis(q if index % 4 else quat(index+1))
        values = [*q, *b]
        values.extend(rng.uniform(-10, 10) for _ in range(3))
        values.extend(rng.uniform(-30, 30) for _ in range(12))
        values.extend([rng.uniform(.01, 2), rng.uniform(.5, 5),
                       rng.uniform(-.1, .1), rng.uniform(-.1, .1),
                       rng.uniform(.5, 5), rng.uniform(.5, 5), rng.uniform(-.1, .1)])
        return [rng.getrandbits(32), state, *map(bits, values)]

    def frame(index, q=None):
        return [*(quat(index) if q is None else q), *(rng.uniform(-1, 1) for _ in range(3))]

    states = [(4, 4), (4, 0), (0, 4), (0, 0), (7, 12), (1, 5)]
    dt = [1/60, 1/30, 1/120, .001, .05]
    # Every swing/twist branch and all active/kinematic combinations.
    for index in range(2880):
        swing, twist = index % 5, (index//5) % 4
        state_a, state_b = states[(index//20) % len(states)]
        p = [rng.uniform(0, .5) for _ in range(3)] + [rng.uniform(-10, 10)]
        p += [rng.uniform(0, 10) for _ in range(6)]
        p += [rng.uniform(-10, 10), rng.uniform(-10, 10)]
        p += [rng.uniform(-1, 1), rng.uniform(-1, 1)]
        parameters = [*map(bits, p), swing, twist]
        a, b = frame(index), frame(index+1)
        frames = [*map(bits, a), rng.getrandbits(32), *map(bits, b), rng.getrandbits(32), *map(bits, quat(index+2))]
        add(0, [*parameters, *frames, *body(index, state_a), *body(index+1, state_b),
                bits(dt[index % len(dt)]), rng.getrandbits(32)], 96,
            swing=swing, twist=twist, states=[state_a, state_b])
    # Exact parallel axes, zero denominators, and either side of cone guard.
    for q in ([0., 0., 0., 1.], [1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.],
              [0., .001, 0., math.sqrt(1-.001**2)], [0., .002, 0., math.sqrt(1-.002**2)]):
        for swing in range(4):
            for twist in range(3):
                parameters = [bits(0.)]*16
                parameters[8:10] = [bits(2.), bits(4.)]
                parameters[12:16] = [bits(.8), bits(.7), swing, twist]
                frames = [*map(bits, [0., 0., 0., 1., 0., 0., 0., 0.]*2+[0., 0., 0., 1.])]
                add(0, [*parameters, *frames, *body(1, 4, [0., 0., 0., 1.]), *body(1, 4, q),
                        bits(1/60), 0xffffffff], 96, branch_boundary=True, swing=swing, twist=twist)
    # Disabled, soft, hard: strength remains meaningful even for type zero.
    for index in range(3456):
        state_a, state_b = states[index % len(states)]
        kinds = [(index//6) % 3, (index//18) % 3]
        parameters = []
        for kind in kinds:
            parameters.extend(map(bits, [rng.uniform(0, 2000), rng.uniform(0, 100), rng.uniform(0, 50000)]))
            parameters.append(kind)
        add(1, [*body(index, state_a), *body(index+1, state_b),
                *map(bits, frame(index)+frame(index+1)), *parameters, bits(dt[index % len(dt)])], 148,
            types=kinds, states=[state_a, state_b])
    # Saturating one relative quaternion component must replace all three axes.
    for q in ([1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.],
              [1.1, .2, .3, .4], [.2, 1.1, .3, .4], [.2, .3, 1.1, .4], [0., 0., 0., 1.]):
        for linear in range(3):
            for angular in range(3):
                a = body(1, 4, [0., 0., 0., 1.])
                b = body(1, 4, q)
                parameters = [bits(1.), bits(2.), bits(3.), linear, bits(4.), bits(5.), bits(6.), angular]
                add(1, [*a, *b, *map(bits, [0., 0., 0., 1., .2, -.3, .4]*2), *parameters, bits(1/60)], 148,
                    quaternion_singularity=True, types=[linear, angular])
    for linear in (0, 1):
        for hard in (0, 1):
            add(2, [linear, hard, bits(10.), bits(0.), bits(11.)], 24, stock=True)
            for _ in range(64):
                add(2, [linear, hard, *map(bits, [rng.uniform(0, 100), rng.uniform(0, 100), rng.uniform(0, 100)])], 24)
    add(3, [1, 0, 0, 0], 240, stock=True)
    for _ in range(512):
        add(3, [0, *map(bits, [rng.uniform(-180, 180), rng.uniform(-180, 180), rng.uniform(0, 1000000)])], 240)
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
    reference = build_probe(output, 'constraint-build-reference', PLUGIN/'Tests/Reference/constraint_build_probe.rs', args.target_dir)
    code = output/'simulation-source'
    if code.exists():
        shutil.rmtree(code)
    code.mkdir()
    for name in ('SimulationMath.h', 'SimulationMath.cpp', 'RigidBody.h', 'GeometryTypes.h', 'DriveFrames.h',
                 'ConstraintFrames.h', 'ConstraintFrames.cpp', 'ConstraintSolver.h', 'JointBuild.h',
                 'JointBuild.cpp', 'DriveBuild.h', 'DriveBuild.cpp', 'BoardTypes.h', 'JointRecords.h', 'JointRecords.cpp',
                 'DriveFrames.cpp', 'BodyMass.h', 'BodyMass.cpp', 'AggregateMass.h', 'AggregateMass.cpp', 'DeckGeometry.h', 'DeckGeometry.cpp'):
        shutil.copy2(PLUGIN/'Source/AtelierSkate/Private/Simulation'/name, code/name)
    candidate = output/'constraint-build-cpp'
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-exceptions',
                    '-Wall', '-Wextra', '-Werror', '-I', str(code),
                    *[str(code/name) for name in ('SimulationMath.cpp', 'ConstraintFrames.cpp', 'JointBuild.cpp', 'DriveBuild.cpp',
                                                'JointRecords.cpp', 'DriveFrames.cpp', 'BodyMass.cpp', 'AggregateMass.cpp', 'DeckGeometry.cpp')],
                    str(PLUGIN/'Tests/Simulation/constraint_build_probe.cpp'), '-o', str(candidate)], check=True)
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
                  comparison='exact complete joint packed workspaces, typed drive rows and private production packing, stock/custom drive parameters, all six authored joint records')
    (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
