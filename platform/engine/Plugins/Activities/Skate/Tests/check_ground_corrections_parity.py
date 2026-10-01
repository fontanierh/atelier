#!/usr/bin/env python3
"""Compare grounded numerical corrections and wall-ride responses against frozen Rust.

The oracle runs unchanged skate-core source from 46513a6. Actual shared body
accumulators and retained wall-ride partial publications are compared.
Physical producers and state scheduling are separate.
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
OPERATIONS = ('com_height','force_projection','edge_direction','edge_up','hang_force','wheel_catch','pinning_velocity','scale_magnitude','apply_world_force','wall_ride')


def bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def scalar(word):
    return struct.unpack('<f', struct.pack('<I', word))[0]


def f(values):
    return list(map(bits, values))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def corpus():
    rng=random.Random(0x82d38800);records=[];cases=[]
    def add(op,words,label,**meta):
        cases.append(dict(index=len(cases),operation=OPERATIONS[op],label=label,**meta))
        records.append(struct.pack('<'+'I'*(len(words)+1),op,*words))
    def vector(scale=10.):return [rng.uniform(-scale,scale) for _ in range(4)]
    for seed in range(1536):
        a,b,c=vector(),vector(),vector()
        for op,values in ((0,a),(1,a+b),(2,a+b),(3,a),(4,a+b+c),(5,a+b),
                          (6,a+[c[0],c[2],(1/60,1/120,1/30)[seed%3]]),
                          (7,a+[sum(x*x for x in a[:3]),rng.uniform(-100.,100.)])):
            add(op,f(values),'all4-lane physical vectors and exact FMA/division ordering')
    zero=[0.]*4
    special=(zero,[-0.]*4,[0.,1.,0.,0.],[0.,-1.,0.,.25],
             [1.,0.,0.,.25],[0.,0.,1.,-.5],[1e-20,-1e-20,1e-20,0.],
             [1e-6,0.,0.,0.],[1.0000001e-6,0.,0.,0.])
    for a in special:
        for b in special:
            for op,values in ((0,a),(1,a+b),(2,a+b),(3,a),(4,a+b+[1.,2.,3.,.25]),(5,a+b)):
                add(op,f(values),'degenerate edges, signed zero, native epsilon and fourth lanes')
    for dt in (-1.,-0.,0.,1e-20,1/120,1/60,1.):
        for a in special:add(6,f(a+[2.,-3.,dt]),'dt reciprocal and current vertical coordinate retained')
    for squared in (0.,1e-40,1e-20,1e-12,1.,100.):
        for magnitude in (-50.,-0.,0.,50.):add(7,f([1.,-0.,-3.,.25,squared,magnitude]),'scalar divide and zero length nonfinite words retained')
    def body(seed):
        values=f([0.,0.,0.,1.]+[rng.uniform(-1.,1.) for _ in range(18)]+[rng.uniform(-10.,10.) for _ in range(15)]+[.5])
        result=[(1,2,4,6,12)[seed%5]]+values+[seed%120]+f([1.,2.,3.,(0.,.1,1.,2.)[seed%4],1.,100.,20.,.1,.2])
        assert len(result)==49;return result
    for seed in range(96):
        b=body(seed);deck=vector()[:3];commands=[f(vector(500.)[:3]+vector()[:3]) for _ in range(24)]
        add(8,b+f(deck)+[len(commands)]+[w for c in commands for w in c],
            'persistent actual body force/torque accumulators, deck origin distinct from COM',initial_body=b,steps=len(commands))
    curve=[0.,.05,.1,.2,.5,1.,2.,4.]+[.05,.1,.2,.4,.7,1.,.5,0.]
    def wall(normal,up,velocity,t0,t1,speed,contacts,flag=True,floor=(0.,1.,0.,0.),height=.2,settings=None):
        s=settings or [.5,.09,.6,1.,.25,.66,3.]
        previous=[9.,8.,7.,.25]
        words=f(curve+s+normal+up+velocity+[8.,9.81,speed])+[contacts&0xffffffff]+f([0.,0.,0.,0.,0.,height,0.,.5]+list(floor))+[0xabcdef01,int(flag)]+f([t0,t1]+previous)
        add(9,words,'wall force gates versus auto-jump gates and retained velocity',previous=f(previous))
    for t0 in (0.,.01,.010000001,.09,.09000001,.2):
        for t1 in (-1.0000001,-1.,-.99999994,-.1,-0.,0.,.1,.10000001,1.,1.0000001):
            for speed in (2.9999998,3.,8.):
                for contacts in (-1,0,1):wall([1.,0.,0.,.25],[1.,0.,0.,-.5],[2.,-2.,4.,.25],t0,t1,speed,contacts)
    for ny in (.49999997,.5,-.49999997,-.5):
        for dot in (.70999998,.71,.71000004,.8):
            for flag in (False,True):wall([1.,ny,0.,.25],[dot,0.,0.,.5],[2.,-2.,4.,.25],.2,-.1,5.,1,flag)
    for vy in (-6.0000005,-6.,-5.9999995,-.0001,-0.,0.,.1):
        for height in (.59999996,.6,.6000001,4.):
            for floor in ([.49999997,0.,0.,0.],[.5,0.,0.,.25],[.50000006,0.,0.,-.5]):
                wall([1.,0.,0.,.25],[1.,0.,0.,-.5],[2.,vy,4.,.25],.2,0.,5.,1,floor=floor,height=height)
    for seed in range(512):
        normal=[1.,rng.uniform(-.49,.49),rng.uniform(-.1,.1),rng.choice((0.,.25,-.5))]
        wall(normal,normal,vector(),rng.uniform(0.,3.),rng.uniform(-2.,3.),rng.uniform(0.,10.),seed%4,
             flag=seed%8!=0,floor=vector(1.),height=rng.uniform(0.,2.))
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
    probe = PLUGIN / 'Tests/Reference/ground_corrections_probe.rs'
    main = source / 'ground-corrections-oracle.rs'
    main.write_text((source / 'lib.rs').read_text() + probe.read_text().replace('//!', '//'))
    reference = output / 'ground-corrections-reference'
    subprocess.run(['rustc', '+1.97.1', '--edition=2024', '-O', '-A', 'dead_code', str(main), '-o', str(reference)], check=True)
    for name, expected in originals.items():
        if digest(source / name) != expected:
            raise AssertionError(f'Frozen original module changed: {name}')
    snapshot = output / 'native-source'
    if snapshot.exists():
        shutil.rmtree(snapshot)
    snapshot.mkdir()
    native = PLUGIN / 'Source/AtelierSkate/Private/Native'
    units = ('NativeMath', 'GroundCorrections', 'GroundContactResponse')
    for name in [f'{unit}.{ext}' for unit in units for ext in ('h', 'cpp')]:
        shutil.copy2(native / name, snapshot / name)
    # Snapshot transitive headers as well as compiled numerical units.
    import re
    pending=list(snapshot.glob('*'));seen=set()
    while pending:
        path=pending.pop()
        if path.name in seen:continue
        seen.add(path.name)
        for name in re.findall(r'^#include "([^"\n]+)"',path.read_text(),re.M):
            target=snapshot/name
            if not target.exists():shutil.copy2(native/name,target)
            pending.append(target)
    shutil.copy2(PLUGIN / 'Tests/Native/ground_corrections_probe.cpp', snapshot / 'ground_corrections_probe.cpp')
    cpp = output / 'ground-corrections-cpp'
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math', '-fno-exceptions', '-Wall', '-Wextra', '-Werror', '-I', str(snapshot), *[str(snapshot / f'{unit}.cpp') for unit in units], str(snapshot / 'ground_corrections_probe.cpp'), '-o', str(cpp)], check=True)
    provenance = dict(reference_revision=revision, source_archive_sha256=hashlib.sha256(archive).hexdigest(), original_source_sha256=originals, probe_sha256=digest(probe), reference_binary_sha256=digest(reference), cpp_binary_sha256=digest(cpp), native_source_sha256={p.name: digest(p) for p in sorted(snapshot.iterdir())}, rust_compiler=subprocess.check_output(['rustc', '+1.97.1', '-vV'], text=True).strip(), cpp_compiler=subprocess.check_output(['clang++', '--version'], text=True).strip())
    (output / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    return cpp, reference


def decode(data, cases):
    if len(data) % 4:
        raise AssertionError('Partial ground output word')
    words = struct.unpack('<' + 'I' * (len(data) // 4), data)
    at, rows = 0, []
    for case in cases:
        index, op, count = words[at:at + 3]
        if index != case['index'] or OPERATIONS[op] != case['operation']:
            raise AssertionError('Ground output identity changed')
        rows.append(words[at + 3:at + 3 + count])
        case.update(first_output_word=at, output_words=count + 3)
        at += count + 3
    if at != len(words):
        raise AssertionError('Trailing ground output words')
    return rows


def coverage(rows,cases):
    counts=Counter();observed={op:set() for op in OPERATIONS}
    for row,c in zip(rows,cases):
        op=c['operation'];counts[op]+=1;observed[op].add(row)
        if op=='apply_world_force':
            initial=tuple(c['initial_body']);steps=c['steps']
            if row[:49]!=initial or row[49]!=steps or len(row)!=50+steps*49:raise AssertionError('Body framing changed')
            for n in range(steps):
                b=row[50+n*49:50+(n+1)*49]
                if b[:32]!=initial[:32] or b[38]!=initial[38] or b[39]!=0 or b[40:]!=initial[40:]:raise AssertionError('Force application changed untouched body lanes')
                counts['force_applications']+=1
                counts['changed_force_accumulators']+=b[32:35]!=initial[32:35]
                counts['changed_torque_accumulators']+=b[35:38]!=initial[35:38]
        elif op=='wall_ride':
            if len(row)!=14 or row[1]!=16 or row[5:8]!=(0,0,0) or row[12]!=0:raise AssertionError('Wall response framing/tag/defaults changed')
            counts['wall_active' if row[0] else 'wall_inactive']+=1
            if row[0] and not row[13]:counts['wall_force_only']+=1
            if row[13]:counts['wall_auto_jump']+=1
            else:
                if row[8:12]!=tuple(c['previous']):raise AssertionError('Unpublished auto-jump overwrote retained velocity')
                counts['retained_velocity']+=1
            if not row[0] and any(row[2:5]):raise AssertionError('Inactive wall ride emitted force')
    for op,values in observed.items():
        if len(values)<8:raise AssertionError(f'Unobserved ground correction outputs: {op}')
    for key in ('wall_active','wall_inactive','wall_force_only','wall_auto_jump','retained_velocity','changed_force_accumulators','changed_torque_accumulators'):
        if not counts[key]:raise AssertionError(f'Uncovered ground branch: {key}')
    counts['distinct_outputs']={op:len(values) for op,values in observed.items()}
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
    report = dict(passed=True, cases=len(cases), coverage=counts, exact_words=len(expected) // 4, input_sha256=hashlib.sha256(inputs).hexdigest(), output_sha256=hashlib.sha256(expected).hexdigest(), comparison='All grounded corrections, actual shared-body accumulator histories and wall-ride partial publications exact; no tolerance; original numerical source unchanged; live producer/state scheduling separate')
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
