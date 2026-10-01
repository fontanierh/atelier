#!/usr/bin/env python3
"""Stock board settings, live child colliders and world-to-solver comparison.

Compile only through the shared render lock/memory guard. The Rust oracle loads
original settings and invokes the unchanged original colliders and BoardWorld.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
from check_gesture_parity import converter
from reference_build import build_probe
from session_parity import PLUGIN


def corpus():
    words = [128]
    def u(*values): words.extend(values)
    def f(*values): words.extend(struct.unpack('<I', struct.pack('<f', x))[0] for x in values)
    def transform(angle, x, y, z):
        c, s = math.cos(angle), math.sin(angle)
        f(c, 0, -s, 0, 1, 0, s, 0, c, x, y, z)
    for case in range(128):
        mode = 2 if case % 16 == 0 else 1 if case % 16 == 1 else 0
        u(mode)
        transform(case*.173, 0, (.0, .05, .3, 1.)[case % 4], 0)
        custom = case % 3 != 0
        u(custom)
        if custom:
            u(case % 2, 8)
            for n in range(8):
                kind = n % 4
                u(kind)
                if kind == 0: f(.02+.005*n)
                elif kind == 1: f(.015, .09)
                elif kind == 2: f(.07, .012, .18, .006)
                else:
                    f(-.06, 0, -.08, .06, 0, -.08, 0, 0, .09, .003, 1, 1, 1)
                    u(0)
                transform(n*.23, (n-4)*.008, .006, (n-4)*.025)
                u(n != case % 8)
        for n in range(7):
            u(1 if mode == 2 else 2 if mode == 1 else 1 if case % 8 == 3 and n == 4 else 4)
            f(.1*(case % 3), 0, .25*(case % 9))
        slope = (.0, .12, -.12, .4)[case % 4]
        verts = [(-20., -20*slope-.035, -20.), (20., 20*slope-.035, -20.),
                 (20., 20*slope-.035, 20.), (-20., -20*slope-.035, 20.)]
        u(2)
        for n, indices in enumerate(((0, 2, 1), (0, 3, 2))):
            for index in indices: f(*verts[index])
            f(0)
            u(0x10, 0x12340000+n)
        u(case % 2, 32)
        for tick in range(32):
            f((1/60, 1/120)[case % 2], 17)
            u(0)
            f(.001, 0, -9.81, 0)
            u((0, 1, 8, 25)[case % 4])
            f(.08*math.sin(tick*.2), -.06*math.cos(tick*.17), .1, 0, .3 if tick % 7 == 0 else 0, .01, 0, -.02)
            f(.01, .05, .5, .0001)
            u(0, (3, 16, 50)[case % 3])
            f(.00001)
            u(case % 2)
    return struct.pack(f'<{len(words)}I', *words)


def inspect(data):
    w = struct.unpack(f'<{len(data)//4}I', data)
    at = 1
    counts = Counter()
    primitive_words = (4, 8, 29, 16)
    for case in range(w[0]):
        end = at+1+w[at]
        at += 1+143
        frames = w[at]
        at += 1
        for tick in range(frames):
            stop = at+1+w[at]
            at += 1
            volumes = w[at]
            at += 1
            counts['volumes'] += volumes
            for _ in range(volumes):
                body, kind = w[at:at+2]
                assert body < 7 and kind < 4
                counts[f'primitive_{kind}'] += 1
                at += 8+primitive_words[kind]
            dropped, contacts = w[at:at+2]
            counts['dropped'] += dropped
            counts['generated_contacts'] += contacts
            at += 2+contacts*15+8*49+16+7*12
            solved = w[at]
            at += 1+solved*66
            reports = w[at]
            assert reports <= 16
            counts['solved_contacts'] += solved
            counts['reports'] += reports
            at += 1+reports*25
            assert at == stop, (case, tick, at, stop)
            counts['frames'] += 1
        assert at == end, (case, at, end)
    assert at == len(w)
    assert counts['frames'] == 4096 and counts['generated_contacts'] > 100
    assert counts['solved_contacts'] > 100 and counts['reports'] > 100
    assert all(counts[f'primitive_{kind}'] for kind in range(4))
    return counts


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assets', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--target-dir', type=Path, required=True)
    args = p.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name in ('result.json', 'first-divergence.json'):
        (output/name).unlink(missing_ok=True)
    native = PLUGIN/'Source/AtelierSkate/Private/Native'
    sources = ('NativeMath', 'RigidBody', 'BodyMass', 'AggregateMass', 'DeckGeometry', 'DriveFrames',
        'ConstraintFrames', 'ConstraintSolver', 'JointBuild', 'DriveBuild', 'JointRecords', 'TruckDriveFrames',
        'DrivePreparation', 'HookDrive', 'BoardAssembly', 'ContactBuild', 'ContactGeneration', 'BoardPose',
        'ForceQueue', 'CollisionBody', 'BoardContactFeedback', 'BoardStep', 'BoardRuntime', 'Geometry',
        'GeometrySweep', 'WorldGeometry', 'GeometryFeatures', 'GeometryPrism', 'GeometryTriangleFixup',
        'WorldPrimitiveContact', 'ContactRetention', 'WorldContactProducer', 'Settings', 'NameId',
        'BoardPhysicsSettings', 'BoardColliders')
    cpp = output/'board-world-runtime-cpp'
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math', '-fno-exceptions',
        '-Wall', '-Wextra', '-Werror', '-I', str(native), *(str(native/f'{n}.cpp') for n in sources),
        str(PLUGIN/'Tests/Native/board_world_runtime_probe.cpp'), '-o', str(cpp)], check=True)
    rust = build_probe(output, 'board-world-runtime-reference', PLUGIN/'Tests/Reference/board_world_runtime_probe.rs', args.target_dir)
    settings = output/'settings.native'
    settings.write_bytes(converter.encode_settings(args.assets/'private/stock/skater-collections.json'))
    commands = corpus()
    (output/'input.bin').write_bytes(commands)
    expected = subprocess.check_output([str(rust), str(args.assets.resolve())], input=commands)
    actual = subprocess.check_output([str(cpp), str(settings)], input=commands)
    (output/'reference.bin').write_bytes(expected)
    (output/'native.bin').write_bytes(actual)
    if actual != expected:
        first = next((i for i, (a, b) in enumerate(zip(actual, expected)) if a != b), min(len(actual), len(expected)))
        (output/'first-divergence.json').write_text(json.dumps(dict(byte=first, word=first//4, expected_bytes=len(expected), actual_bytes=len(actual)), indent=2)+'\n')
        raise AssertionError(f'Board world runtime differs at byte {first}, word {first//4}')
    result = dict(passed=True, streams=128, coverage=dict(inspect(expected)), output_words=len(actual)//4,
        output_bytes=len(actual), sha256=hashlib.sha256(actual).hexdigest(),
        comparison='Exact original settings load, ordered live child shapes, world contacts, complete integrated board and solver reports; all four shape types, static/frozen/active bodies and stateful slopes.',
        limitations='Board-only world simulation; live rider and gameplay state producers are separate. Malformed settings diagnostics are not part of this corpus.')
    (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
