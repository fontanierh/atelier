#!/usr/bin/env python3
"""Compare persistent reckoning frames and signed angles against frozen Rust.

The oracle runs unchanged skate-core source from 46513a6. This checks retained frame translations, body flips, dynamic lean and lateral
tilt; actual frame producers and the gameplay scheduler are separate checks.
Run through the shared render lock and memory guard.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tarfile

PLUGIN = Path(__file__).resolve().parents[1]
REFERENCE_REVISION = '46513a6'
OPERATIONS = ('signed_angle', 'frame_stream')
FRAME_WIDTH = 89


def bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def scalar(word):
    return struct.unpack('<f', struct.pack('<I', word))[0]


def f(values):
    return list(map(bits, values))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def corpus():
    rng = random.Random(0x82d8d688)
    records, cases = [], []

    def add(op, payload, label, **meta):
        cases.append(dict(index=len(cases), operation=OPERATIONS[op], label=label, **meta))
        records.append(struct.pack('<' + 'I' * (len(payload) + 1), op, *payload))

    def normal():
        v = [rng.uniform(-1., 1.) for _ in range(3)]
        length = math.sqrt(sum(x*x for x in v))
        return [x/length for x in v]

    def matrix(angle):
        c, s = math.cos(angle), math.sin(angle)
        return f([c, 0., -s, rng.choice((0., -0., .25)), 0., 1., 0., rng.choice((0., -0., 1.)), s, 0., c, rng.choice((0., -0., -.5))] + [rng.uniform(-20., 20.) for _ in range(4)])

    for seed in range(2048):
        a, b, axis = normal(), normal(), normal()
        scale = (1.e-5, .01, .01000001, .1, 1., 20.)[seed%6]
        add(0, f([v*scale for v in a] + b + axis), 'one-refinement angle gates and signed cross direction')
    vectors = ([0., 0., 0.], [.01, 0., 0.], [.01000001, 0., 0.], [1., 0., 0.], [-1., 0., 0.], [0., 1., 0.], [0., 0., 1.], [0., -.0, -1.])
    for a in vectors:
        for b in vectors:
            for axis in ([0., 1., 0.], [0., -1., 0.], [0., 0., 0.]):
                add(0, f(a+b+axis), 'signed angle zero/small/reversal/coplanar gates')
    for seed in range(256):
        initial = [seed%2]
        if initial[0]:
            initial += [w for j in range(5) for w in matrix(.03*j)] + f(normal()+[rng.choice((0., .25, -1.)), .3, .5, -.0, .25, -1.])
        curves = f([0., .1, .25, .5, .75, 1., 2., 3.] + [rng.uniform(-1., 1.) for _ in range(8)] + [0., .1, .25, .5, .75, 1., 2., 3.] + [rng.uniform(0., 1.) for _ in range(8)])
        commands = [[4]+f([3., 4., 5., .5]), [5]+f([7., -2., 9., -.25]), [3]+matrix(.7)]
        for tick in range(24):
            roll = rng.uniform(-math.pi, math.pi)
            up = [math.sin(roll), math.cos(roll), 0., rng.choice((0., -.0, .25))]
            ground = normal()+[rng.choice((0., -.0, -.5))]
            commands.append([0]+f(up+ground))
            commands.append([1]+f(up+normal()+[rng.choice((0., -.0, .25))]))
            commands.append([2,tick%2])
            if tick%8 == 7:
                commands.append([3]+matrix(roll))
        commands += [[6], [0]+f([0., 1., 0., 0.]*2), [2,0], [1]+f([0., 1., 0., 0.]*2)]
        add(1, initial+curves+[len(commands)]+[w for c in commands for w in c], 'body flips retain ground translation; composed systems, lean and conditional lateral tilt', commands=[c[0] for c in commands])
    for up in ([0., 0., 0., 0.], [1., 0., 0., 0.], [0., 1., 0., 0.], [0., -1., 0., 0.], [0., .999, .04471018, 0.]):
        curves=f([0., .1, .25, .5, .75, 1., 2., 3.] + [.5]*8)*2
        commands=[[0]+f(up+[0., 1., 0., 0.]),[1]+f(up+up),[2,0],[2,1],[6]]
        add(1,[0]+curves+[len(commands)]+[w for c in commands for w in c],'degenerate axes/retained tilt and reset recovery',commands=[c[0] for c in commands])
    return struct.pack('<I', len(records))+b''.join(records), cases


def build_probes(output):
    root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], cwd=PLUGIN, text=True).strip())
    relative = (PLUGIN / 'ThirdParty/skate-runtime/crates/skate-core/src').relative_to(root).as_posix()
    revision = subprocess.check_output(['git', 'rev-parse', REFERENCE_REVISION], cwd=root, text=True).strip()
    archive = subprocess.check_output(['git', 'archive', f'{revision}:{relative}'], cwd=root)
    source = output / 'reference-source'
    if source.exists():
        shutil.rmtree(source)
    source.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        stream.extractall(source, filter='data')
    originals = {p.relative_to(source).as_posix(): digest(p) for p in sorted(source.rglob('*.rs'))}
    probe = PLUGIN / 'Tests/Reference/reckoning_frames_probe.rs'
    main = source / 'reckoning-frames-oracle.rs'
    main.write_text((source / 'lib.rs').read_text() + probe.read_text().replace('//!', '//'))
    reference = output / 'reckoning-frames-reference'
    subprocess.run(['rustc', '+1.97.1', '--edition=2024', '-O', '-A', 'dead_code', str(main), '-o', str(reference)], check=True)
    for name, expected in originals.items():
        if digest(source / name) != expected:
            raise AssertionError(f'Frozen original module changed: {name}')
    snapshot = output / 'simulation-source'
    if snapshot.exists():
        shutil.rmtree(snapshot)
    snapshot.mkdir()
    simulation = PLUGIN / 'Source/AtelierSkate/Private/Simulation'
    units = ('SimulationMath', 'RigidBody', 'SkeletonPoseFrames', 'BoardGroundAngle', 'RidingAngles', 'ReckoningFrames')
    for name in [f'{unit}.{ext}' for unit in units for ext in ('h', 'cpp')]:
        shutil.copy2(simulation / name, snapshot / name)
    shutil.copy2(PLUGIN / 'Tests/Simulation/reckoning_frames_probe.cpp', snapshot / 'reckoning_frames_probe.cpp')
    cpp = output / 'reckoning-frames-cpp'
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math', '-fno-exceptions', '-Wall', '-Wextra', '-Werror', '-I', str(snapshot), *[str(snapshot / f'{unit}.cpp') for unit in units], str(snapshot / 'reckoning_frames_probe.cpp'), '-o', str(cpp)], check=True)
    provenance = dict(reference_revision=revision, source_archive_sha256=hashlib.sha256(archive).hexdigest(), original_source_sha256=originals, probe_sha256=digest(probe), reference_binary_sha256=digest(reference), cpp_binary_sha256=digest(cpp), simulation_source_sha256={p.name: digest(p) for p in sorted(snapshot.iterdir())}, rust_compiler=subprocess.check_output(['rustc', '+1.97.1', '-vV'], text=True).strip(), cpp_compiler=subprocess.check_output(['clang++', '--version'], text=True).strip())
    (output / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    return cpp, reference


def decode(data, cases):
    if len(data) % 4:
        raise AssertionError('Partial reckoning output word')
    words = struct.unpack('<' + 'I' * (len(data) // 4), data)
    at, rows = 0, []
    for case in cases:
        index, op, count = words[at:at + 3]
        if index != case['index'] or OPERATIONS[op] != case['operation']:
            raise AssertionError('Reckoning output identity changed')
        rows.append(words[at + 3:at + 3 + count])
        case.update(first_output_word=at, output_words=count + 3)
        at += count + 3
    if at != len(words):
        raise AssertionError('Trailing reckoning output words')
    return rows


def coverage(rows, cases):
    counts=Counter();leans=set();tilts=set();systems=set()
    for row,case in zip(rows,cases):
        op=case['operation'];counts[op]+=1
        if op=='signed_angle':
            if len(row)!=1:raise AssertionError('Signed angle framing changed')
            counts['zero_angles' if row[0]==0 else 'nonzero_angles']+=1
            if scalar(row[0])>math.pi:counts['clockwise_angles']+=1
        else:
            if row[0]!=len(case['commands']) or len(row)!=1+(row[0]+1)*FRAME_WIDTH:raise AssertionError('Reckoning stream framing changed')
            before=row[1:1+FRAME_WIDTH]
            for tick,cmd in enumerate(case['commands']):
                after=row[1+(tick+1)*FRAME_WIDTH:1+(tick+2)*FRAME_WIDTH]
                counts[f'command_{cmd}']+=1
                if cmd==0:
                    if after[12:16]!=before[12:16] or after[64:80]!=before[64:80]:raise AssertionError('Transform calculation mutated retained ground translation/body flip')
                    if after[48:64]==before[48:64]:counts['unchanged_inverses']+=1
                    else:counts['changed_inverses']+=1
                elif cmd==1:
                    if after[:84]!=before[:84] or after[85:]!=before[85:]:raise AssertionError('Lean calculation changed matrix/heading/tilt')
                    counts['zero_lean_frames' if after[84]==0 else 'dynamic_lean_frames']+=1
                elif cmd==2:
                    if after[:85]!=before[:85]:raise AssertionError('Tilt calculation changed matrix/heading/lean')
                    counts['retained_lateral_tilts' if after[85:89]==before[85:89] else 'updated_lateral_tilts']+=1
                elif cmd==3:
                    if after[:64]!=before[:64] or after[80:]!=before[80:]:raise AssertionError('Body flip assignment updated derived frames early')
                elif cmd==4:
                    if after[:12]!=before[:12] or after[16:]!=before[16:]:raise AssertionError('Ground position assignment mutated other fields')
                elif cmd==5:
                    if after[:28]!=before[:28] or after[32:]!=before[32:]:raise AssertionError('System position assignment mutated other fields')
                elif cmd==6:
                    if after[80:]==tuple(f([1.,0.,0.,0.,0.,0.,0.,0.,0.])):counts['complete_resets']+=1
                    else:raise AssertionError('Reckoning reset defaults changed')
                leans.add(after[84]);tilts.add(after[85:89]);systems.add(after[16:32]);before=after
    counts['distinct_lean_angles']=len(leans);counts['distinct_lateral_tilts']=len(tilts);counts['distinct_system_matrices']=len(systems)
    for key in ('zero_angles','nonzero_angles','clockwise_angles','changed_inverses','zero_lean_frames','dynamic_lean_frames','retained_lateral_tilts','updated_lateral_tilts','complete_resets'):
        if not counts[key]:raise AssertionError(f'Uncovered reckoning branch: {key}')
    if min(len(leans),len(tilts),len(systems))<16:raise AssertionError('Reckoning derived state insufficiently observable')
    return dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name in ('result.json', 'first-divergence.json', 'provenance.json'):
        (output / name).unlink(missing_ok=True)
    inputs, cases = corpus()
    (output / 'input.bin').write_bytes(inputs)
    cpp, reference = build_probes(output)
    expected = subprocess.check_output([str(reference)], input=inputs)
    actual = subprocess.check_output([str(cpp)], input=inputs)
    (output / 'reference.bin').write_bytes(expected)
    (output / 'cpp.bin').write_bytes(actual)
    rows = decode(expected, cases)
    (output / 'cases.json').write_text(json.dumps(cases, indent=2) + '\n')
    if expected != actual:
        first = next((i for i, (a, b) in enumerate(zip(expected, actual)) if a != b), min(len(expected), len(actual)))
        aligned = first // 4 * 4
        case = next((c for c in cases if c['first_output_word'] * 4 <= first < (c['first_output_word'] + c['output_words']) * 4), None)
        report = dict(passed=False, first_word=first // 4, case=case, reference_length=len(expected), cpp_length=len(actual), reference_hex=expected[max(0, aligned - 16):aligned + 32].hex(), cpp_hex=actual[max(0, aligned - 16):aligned + 32].hex())
        (output / 'first-divergence.json').write_text(json.dumps(report, indent=2) + '\n')
        raise AssertionError(report)
    counts = coverage(rows, cases)
    report = dict(passed=True, cases=len(cases), coverage=counts, exact_words=len(expected) // 4, input_sha256=hashlib.sha256(inputs).hexdigest(), output_sha256=hashlib.sha256(expected).hexdigest(), comparison='All persistent reckoning matrices, heading/lean/tilt, signed angles and retained translations exact; no tolerance; original numerical source unchanged; actual frame producers and gameplay scheduling separate')
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
