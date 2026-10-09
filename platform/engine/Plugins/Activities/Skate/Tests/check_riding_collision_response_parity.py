#!/usr/bin/env python3
"""Compare riding collision response publication against frozen Rust.

The oracle runs unchanged skate-core source from 46513a6. This checks early absence versus late false publication, force clamps, target
velocity and angular correction. Physical producers and state scheduling are separate.
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
OPERATIONS = ('collision_response',)


def bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def scalar(word):
    return struct.unpack('<f', struct.pack('<I', word))[0]


def f(values):
    return list(map(bits, values))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def corpus():
    rng=random.Random(0x82d944e8);records=[];cases=[]
    def add(settings,flags,displacement,velocity,forward,up,normal,dt,mass,label):
        words=settings+[flags]+f(displacement+velocity+forward+up+normal+[dt,mass])
        cases.append(dict(index=len(cases),operation=OPERATIONS[0],label=label,flags=flags,point_y=settings[1]))
        records.append(struct.pack('<'+'I'*(len(words)+1),0,*words))
    def normal():
        v=[rng.uniform(-1.,1.) for _ in range(3)];length=math.sqrt(sum(x*x for x in v));return [x/length for x in v]+[rng.choice((0.,-.0,.25,-1.))]
    def values():return [rng.uniform(-20.,20.) for _ in range(4)]
    for seed in range(4096):
        settings=f([rng.uniform(0.,20.),rng.uniform(-1.,1.),rng.uniform(0.,2.),rng.uniform(-3.,3.)]+[0.,.1,.25,.5,.75,1.,2.,3.]+[rng.uniform(0.,.5) for _ in range(8)])
        flags=rng.getrandbits(32);flags=flags|0x20000 if seed%4 else flags&~0x20000
        n=normal();d=n if seed%13==0 else values()
        if seed%17==0:d=[0.]*4
        add(settings,flags,d,values(),normal(),normal(),n,(1/60,1/120,1/30)[seed%3],rng.uniform(.1,100.),'ordered projection/force/torque curves with four carried lanes')
    settings=f([8.,-.05,1.,1.]+[0.,.1,.25,.5,.75,1.,2.,3.]+[.03]*8)
    for speed in (-20.,-2.,0.,.98999995,.99,.99000007,1.,1.00000012,2.,20.):
        for distance in (0.,1.e-7,.000015258788,.0000152587890625,.000015258791,1.,10.):
            for flags in (0,0x20000):
                add(settings,flags,[distance,0.,0.,.25],[speed,-.0,4.,-.5],[0.,0.,1.,0.],[0.,1.,0.,0.],[0.,1.,0.,0.],1/60,8.,'early distance gate, late false target/angle and clamp boundaries')
    for direction in ([0.,0.,0.,0.],[1.,0.,0.,0.],[-1.,0.,0.,0.],[0.,0.,1.,0.],[0.,0.,-1.,0.]):
        for axis in ([0.,1.,0.,0.],[0.,-1.,0.,0.],[0.,0.,0.,0.]):
            add(settings,0x20000,[1.,0.,0.,0.],[-20.,0.,4.,0.],direction,axis,[0.,1.,0.,0.],1/60,8.,'signed-angle wrap and degenerate forward/axis')
    return struct.pack('<I',len(records))+b''.join(records),cases


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
    probe = PLUGIN / 'Tests/Reference/riding_collision_response_probe.rs'
    main = source / 'riding-collision-response-oracle.rs'
    main.write_text((source / 'lib.rs').read_text() + probe.read_text().replace('//!', '//'))
    reference = output / 'riding-collision-response-reference'
    subprocess.run(['rustc', '+1.97.1', '--edition=2024', '-O', '-A', 'dead_code', str(main), '-o', str(reference)], check=True)
    for name, expected in originals.items():
        if digest(source / name) != expected:
            raise AssertionError(f'Frozen original module changed: {name}')
    snapshot = output / 'simulation-source'
    if snapshot.exists():
        shutil.rmtree(snapshot)
    snapshot.mkdir()
    simulation = PLUGIN / 'Source/AtelierSkate/Private/Simulation'
    units = ('SimulationMath', 'BoardGroundAngle', 'RidingAngles', 'RidingCollisionResponse')
    for name in [f'{unit}.{ext}' for unit in units for ext in ('h', 'cpp')]:
        shutil.copy2(simulation / name, snapshot / name)
    shutil.copy2(PLUGIN / 'Tests/Simulation/riding_collision_response_probe.cpp', snapshot / 'riding_collision_response_probe.cpp')
    cpp = output / 'riding-collision-response-cpp'
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math', '-fno-exceptions', '-Wall', '-Wextra', '-Werror', '-I', str(snapshot), *[str(snapshot / f'{unit}.cpp') for unit in units], str(snapshot / 'riding_collision_response_probe.cpp'), '-o', str(cpp)], check=True)
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


def coverage(rows,cases):
    counts=Counter();targets=set();angulars=set()
    for row,case in zip(rows,cases):
        if row[0]==0:
            if len(row)!=1:raise AssertionError('Absent response emitted fields')
            counts['early_no_publication']+=1
            if not case['flags']&0x20000:counts['disabled_collision_flag']+=1
        else:
            if len(row)!=18:raise AssertionError('Collision response framing changed')
            if not case['flags']&0x20000:raise AssertionError('Disabled response was published')
            if row[6:10]!=(0,case['point_y'],0,0):raise AssertionError('Published force point changed')
            counts['applied_force' if row[1] else 'late_false_publication']+=1
            if not row[1] and any(row[2:6]):raise AssertionError('Late false retained a force')
            if any(row[10:14]):counts['angular_corrections']+=1
            targets.add(row[14:18]);angulars.add(row[10:14])
    counts['distinct_targets']=len(targets);counts['distinct_angular_corrections']=len(angulars)
    for key in ('early_no_publication','disabled_collision_flag','applied_force','late_false_publication','angular_corrections'):
        if not counts[key]:raise AssertionError(f'Uncovered riding collision branch: {key}')
    if min(len(targets),len(angulars))<16:raise AssertionError('Collision responses insufficiently observable')
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
    report = dict(passed=True, cases=len(cases), coverage=counts, exact_words=len(expected) // 4, input_sha256=hashlib.sha256(inputs).hexdigest(), output_sha256=hashlib.sha256(expected).hexdigest(), comparison='All optional response publications, force/point/angular/target words exact; no tolerance; original numerical source unchanged; live physical producers and riding scheduling separate')
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
