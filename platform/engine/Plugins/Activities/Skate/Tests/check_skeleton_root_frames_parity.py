#!/usr/bin/env python3
"""Exact retained skeleton root prediction and board-relative COM producers.

Run only through the render lock/memory guard. Frozen Rust module bytes remain
unchanged, including the root's reverse-axis Gram-Schmidt and COM lift fsel.
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

PLUGIN=Path(__file__).resolve().parents[1]
REFERENCE_REVISION='46513a6'
OPERATIONS=('update','teleport','reset_alignment','prediction','heading','reset_board','local_observations','publish_com','prepare_ground','prepare_teleport','lift','orthonormalize_inverse')
ROOT_WORDS=110
BOARD_WORDS=101
STATE_WORDS=ROOT_WORDS+BOARD_WORDS
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def value(w):return struct.unpack('<f',struct.pack('<I',w))[0]
def f(values):return list(map(bits,values))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def corpus():
    rng=random.Random(0x82be0318);records=[];cases=[]
    def numbers(n,scale=1.):return [rng.uniform(-scale,scale) for _ in range(n)]
    def matrix(y=0.,x=0.,position=None,carry=True,scale=False):
        c,s,cx,sx=math.cos(y),math.sin(y),math.cos(x),math.sin(x)
        columns=((c,sx*s,-cx*s),(0.,cx,sx),(s,-sx*c,cx*c));out=[]
        for col in columns:
            scalar=rng.uniform(.25,4.) if scale else 1.
            out.extend([v*scalar for v in col]+[rng.choice((0.,-0.,.25,-.5,1.)) if carry else 0.])
        return f(out+list(position if position is not None else numbers(3,30.))+[rng.choice((0.,-0.,.25,1.)) if carry else 0.])
    def mat():return matrix(rng.uniform(-math.pi,math.pi),rng.uniform(-1.,1.))
    def root(seed):
        raw=mat()+mat()+f(numbers(8,10.))+[seed%2]+f(numbers(4,100.))+mat()+mat()+mat()+mat()+[int(seed%3!=0)]
        assert len(raw)==ROOT_WORDS;return raw
    def board(seed,lift=None):
        raw=[w for _ in range(5) for w in mat()]+f(numbers(20,5.))+[bits(rng.uniform(-1.,1.) if lift is None else lift)]
        assert len(raw)==BOARD_WORDS;return raw
    def add(label,commands=(),initial=None,**meta):
        payload=[0] if initial is None else [1]+initial
        payload+=[len(commands)]+[w for cmd in commands for w in cmd]
        cases.append(dict(index=len(cases),label=label,commands=[cmd[0] for cmd in commands],**meta));records.append(struct.pack('<'+'I'*len(payload),*payload))
    add('default retained seeds')
    for seed in range(96):add('explicit opaque retained histories',initial=root(seed)+board(seed))
    headings=((0.,0.),(0.,1.),(1.,0.),(0.,-1.),(-1.,0.),(1.,1.),(-1.,1.),(1.,-1.),(-1.,-1.))
    threshold=bits(math.sqrt(value(0x38d1b717)))
    for w in range(threshold-3,threshold+4):headings+=((value(w),0.),(-value(w),0.),(0.,value(w)))
    for seed,(x,z) in enumerate(headings):
        authored=mat();authored[8]=bits(x);authored[10]=bits(z)
        actual=mat();reckoning=mat();velocity=f(numbers(4,10.))
        commands=[[0]+actual+velocity+f([1/60])+authored+reckoning,[0]+mat()+velocity+f([0.])+mat()+mat(),[1]+actual+authored+reckoning]
        add('heading quadrants, strict small-vector threshold and retained heading',commands,heading=[bits(x),bits(z)])
    for seed in range(1024):
        actual,mapped,reckoning=mat(),mat(),mat();dt=(1/240,1/120,1/60,1/30,.1)[seed%5]
        commands=[[5]+mat(),[2]+mat(),[3,1]+f(numbers(4,100.)),[0]+actual+f(numbers(4,20.))+f([dt])+mapped+reckoning,
            [8]+mapped+actual+[rng.getrandbits(32)],[6]+actual,[7]+f(numbers(4,20.))+f([dt])+[rng.getrandbits(32)],
            [6]+mat(),[7]+f(numbers(4,20.))+f([dt])+[0x400],
            [0]+mat()+f(numbers(4,20.))+f([dt])+mat()+mat(),[5]+mat(),[9]+mapped+actual+[0xffffffff],
            [1]+mat()+mat()+mat(),[3,0]+f(numbers(4)),[4,seed%2]+mat(),[0]+mat()+f(numbers(4,20.))+f([dt])+mat()+mat(),
            [10]+matrix(seed*.13,seed*.07,scale=True)+f(numbers(4,30.))+f([rng.uniform(-2.,2.)])]
        add('connected ground/teleport, COM publication order, resets and supplied prediction',commands,initial=root(seed)+board(seed) if seed%2 else None)
    step=value(0x3d23d70a)
    def neighbors(v):
        word=bits(v)
        return (value(word-1),value(word+1)) if word&0x7fffffff else (value(0x80000001),value(1))
    for lift in (-1.,-.3,-step,-0.,0.,step,.3,1.):
        lift=value(bits(lift));low=value(bits(lift-step));high=value(bits(lift+step))
        for requested in (low,*neighbors(low),lift,high,*neighbors(high),-100.,100.):
            commands=[[10]+mat()+f(numbers(4,5.))+f([requested]),[10]+mat()+f(numbers(4,5.))+f([requested]),[8]+mat()+mat()+[0x80000],[9]+mat()+mat()+[0]]
            add('lift low/high equality, ordered limiter and .3 world-axis FMA',commands,initial=root(0)+board(0,lift=lift),lift_bits=bits(lift),requested_bits=bits(requested))
    for seed in range(512):
        source=matrix(rng.uniform(-3.,3.),rng.uniform(-1.5,1.5),scale=True)
        # Shear the first two axes without allowing zero-length Gram-Schmidt.
        source[0]=bits(value(source[0])+rng.uniform(-.1,.1));source[4]=bits(value(source[4])+rng.uniform(-.1,.1))
        add('reverse axis Gram-Schmidt, source-axis projection, two estimates and rigid translation FMA',[[11]+source])
    return struct.pack('<I',len(records))+b''.join(records),cases

def build_probes(output):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip());relative=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-core/src').relative_to(root).as_posix()
    revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip();archive=subprocess.check_output(['git','archive',f'{revision}:{relative}'],cwd=root);source=output/'reference-source'
    if source.exists():shutil.rmtree(source)
    source.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:stream.extractall(source,filter='data')
    originals={p.relative_to(source).as_posix():digest(p) for p in sorted(source.rglob('*.rs'))}
    probe=PLUGIN/'Tests/Reference/skeleton_root_frames_probe.rs';main=source/'skeleton-root-frames-oracle.rs';main.write_text((source/'lib.rs').read_text()+probe.read_text());reference=output/'skeleton-root-frames-reference'
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():
        if digest(source/name)!=expected:raise AssertionError(f'Frozen reference producer changed: {name}')
    snapshot=output/'simulation-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();simulation=PLUGIN/'Source/AtelierSkate/Private/Simulation';units=('SimulationMath','RigidBody','SkeletonPoseFrames','BoardGroundAngle','SkeletonRoot','SkeletonBoardFrames')
    for name in [f'{unit}.{ext}' for unit in units for ext in ('h','cpp')]:shutil.copy2(simulation/name,snapshot/name)
    cpp_probe=PLUGIN/'Tests/Simulation/skeleton_root_frames_probe.cpp';shutil.copy2(cpp_probe,snapshot/cpp_probe.name);cpp=output/'skeleton-root-frames-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{unit}.cpp') for unit in units],str(snapshot/cpp_probe.name),'-o',str(cpp)],check=True)
    provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,
        probe_sha256={p.name:digest(p) for p in (probe,cpp_probe)},reference_binary_sha256=digest(reference),cpp_binary_sha256=digest(cpp),simulation_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},
        rust_compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),cpp_compiler=subprocess.check_output(['clang++','--version'],text=True).strip())
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return cpp,reference

def decode(data,cases):
    words=struct.unpack('<'+'I'*(len(data)//4),data);at=0;rows=[]
    for case in cases:
        index,count,n=words[at:at+3]
        if index!=case['index'] or count!=len(case['commands']):raise AssertionError('Root frame stream identity changed')
        case.update(first_output_word=at,output_words=n+3);rows.append(words[at+3:at+3+n]);at+=n+3
    if at!=len(words):raise AssertionError('Trailing root frame output')
    return rows

def coverage(rows,cases):
    counts=Counter()
    for row,case in zip(rows,cases):
        counts['streams']+=1;before=row[:STATE_WORDS];at=STATE_WORDS
        for cmd in case['commands']:
            if row[at]!=cmd:raise AssertionError('Root frame command order changed')
            counts[OPERATIONS[cmd]]+=1;at+=1
            if cmd in (8,9):
                if row[at]&0x80000:raise AssertionError('Prepare did not clear exact publication flag')
                target=row[at+1:at+17];at+=17
            elif cmd==11:at+=32
            after=row[at:at+STATE_WORDS];at+=STATE_WORDS
            if len(after)!=STATE_WORDS:raise AssertionError('Missing retained producer state')
            if cmd in (0,1):
                if after[40]:raise AssertionError('Supplied prediction was not consumed')
                counts['consumed_predictions']+=before[40]!=0
                if cmd==1 and after[32:36]!=after[12:16]:raise AssertionError('Teleport previous position is not current deck')
            if cmd==2:
                if after[:61]!=before[:61] or after[93:]!=before[93:]:raise AssertionError('Reset alignment replaced independent root histories')
            if cmd==5:
                # Reset writes only COM matrices, COM itself and local COM.
                for a,b in ((0,110),(110,158),(194,202),(206,211)):
                    if after[a:b]!=before[a:b]:raise AssertionError('Board reset replaced retained history')
            if cmd in (8,9) and after[110+32:110+48]!=target:raise AssertionError('Prepared target output differs from stored matrix')
            if cmd==11 and after!=before:raise AssertionError('Pure frame helpers mutated state')
            before=after
        if at!=len(row):raise AssertionError('Root frame state framing changed')
    for op in OPERATIONS:
        if not counts[op]:raise AssertionError(f'Uncovered root producer: {op}')
    if not counts['consumed_predictions']:raise AssertionError('No supplied prediction consumed')
    return dict(counts)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json','provenance.json'):(output/name).unlink(missing_ok=True)
    inputs,cases=corpus();(output/'input.bin').write_bytes(inputs);cpp,reference=build_probes(output);expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(cpp)],input=inputs);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual);rows=decode(expected,cases);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));aligned=first//4*4;case=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None)
        report=dict(passed=False,first_word=first//4,case=case,reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex());(output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    report=dict(passed=True,cases=len(cases),groups=dict(Counter(c['label'] for c in cases)),coverage=coverage(rows,cases),exact_words=len(expected)//4,input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),comparison='All root and board histories, optional prediction, stored W lanes, target publications and flags exact; no tolerance; original producer modules unchanged',limitations='Explicit animation/reckoning/physical frame inputs and finite nondegenerate normalization fixtures; full host animation scheduling and attached-board/rider solve integration are separate checks.')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
