#!/usr/bin/env python3
"""Exact board/part pose normalization, optional records, cache writes and common board delta."""
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
OPERATIONS=('rotation','part_basis','part','board')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def word(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def value(v):return struct.unpack('<f',struct.pack('<I',v))[0]
def f(v):return [word(x) for x in v]
def corpus():
    rng=random.Random(0x82c0b2c8);records=[];cases=[]
    def opaque(n):return [rng.getrandbits(32) for _ in range(n)]
    def add(op,payload,label,**extra):
        cases.append(dict(index=len(cases),operation=OPERATIONS[op],label=label,**extra));records.append(struct.pack('<'+'I'*(len(payload)+1),op,*payload))
    def unit():
        a=[rng.uniform(-1.,1.) for _ in range(3)];length=math.sqrt(sum(v*v for v in a));return [v/length for v in a]
    def matrix(angle=0.,axis=(1.,0.,0.),position=None,scale=(1.,1.,1.),shear=0.,carry=False):
        if position is None:position=[rng.uniform(-100.,100.) for _ in range(3)]
        c=math.cos(angle);s=math.sin(angle);x,y,z=axis;t=1-c
        b=[t*x*x+c,t*x*y+s*z,t*x*z-s*y,t*x*y-s*z,t*y*y+c,t*y*z+s*x,t*x*z+s*y,t*y*z-s*x,t*z*z+c]
        out=[]
        for i in range(3):
            out.extend([scale[i]*(b[3*i+j]+(shear*b[j] if i==1 else 0.)) for j in range(3)])
            out.append(rng.choice((0.,-0.,1.,-1.,.25)) if carry else 0.)
        return f(out+list(position)+[rng.choice((0.,-0.,1.,-1.,.25)) if carry else 1.])
    def part(mask,carry=False):
        transform=matrix(rng.uniform(-math.pi,math.pi),unit(),carry=carry);local=matrix(rng.uniform(-math.pi,math.pi),unit());body=opaque(44)
        live=matrix(rng.uniform(-math.pi,math.pi),unit(),carry=carry);body[:4]=f([.1,.2,.3,.4]);body[4:8]=live[12:16];body[16:28]=live[:12]
        inertia=opaque(10);inertia[:3]=f([rng.uniform(.001,10.) for _ in range(3)]);inertia[4]=word(rng.uniform(0.,10.))
        return [mask]+transform+local+body+inertia
    for axis in ((1.,0.,0.),(0.,1.,0.),(0.,0.,1.),(2**-.5,2**-.5,0.)):
        for angle in (0.,-0.,1.e-8,.1,math.pi/4,math.pi/2,math.pi,2*math.pi):
            for scale in ((1.,1.,1.),(.01,1.,100.),(-1.,1.,1.)):
                for shear in (0.,.01,.9):
                    row=matrix(angle,axis,scale=scale,shear=shear,carry=True)
                    for op in (0,1):add(op,row,'normalizer axis order/handedness/scale/shear/packed W',initial_matrix=row)
    for absent in range(3):
        row=matrix(position=(0.,0.,0.));row[absent*4:absent*4+4]=[0]*4
        for op in (0,1):add(op,row,'zero-axis magnitude selection without repair',initial_matrix=row)
    for _ in range(2048):
        row=matrix(rng.uniform(-math.pi,math.pi),unit(),scale=[rng.uniform(.01,10.) for _ in range(3)],shear=rng.uniform(-.9,.9),carry=True)
        for op in (0,1):add(op,row,'random input axes and packed fourth lanes',initial_matrix=row)
    for mask in range(8):
        for carry in (False,True):
            for angle in (0.,math.pi/2,math.pi):
                p=part(mask,carry);requests=[matrix(angle,(0.,1.,0.),carry=carry),matrix(-angle,(0.,0.,1.),scale=(.5,2.,3.),carry=carry),matrix(.3,(1.,0.,0.),shear=.3,carry=carry)]
                add(2,p+[len(requests)]+[w for row in requests for w in row],'all optional part references, local mass and live cache/carry',initial_part=p,requests=requests)
    for _ in range(1024):
        p=part(rng.randrange(8),bool(rng.randrange(2)));requests=[matrix(rng.uniform(-math.pi,math.pi),unit(),scale=[rng.uniform(.1,3.) for _ in range(3)],carry=bool(rng.randrange(2))) for _ in range(rng.randrange(1,5))]
        add(2,p+[len(requests)]+[w for row in requests for w in row],'random reused part body/local/inertia references',initial_part=p,requests=requests)
    for mask in range(8):
        for hook_mask in range(8):
            parts=[part(mask,True) for _ in range(7)];hook=part(hook_mask,True);requests=[matrix(.3,(0.,1.,0.),scale=(.5,2.,3.),carry=True),matrix(-.8,(1.,0.,0.),carry=True)]
            add(3,[w for p in parts for w in p]+hook+[len(requests)]+[w for r in requests for w in r],'board optional-reference states and original hook request',initial_parts=parts+[hook],requests=requests)
    for _ in range(256):
        parts=[part(rng.randrange(8),bool(rng.randrange(2))) for _ in range(8)];requests=[matrix(rng.uniform(-math.pi,math.pi),unit(),scale=[rng.uniform(.5,2.) for _ in range(3)],carry=bool(rng.randrange(2))) for _ in range(rng.randrange(1,5))]
        add(3,[w for p in parts for w in p]+[len(requests)]+[w for r in requests for w in r],'random common board delta and independent hook/local mass frames',initial_parts=parts,requests=requests)
    return struct.pack('<I',len(records))+b''.join(records),cases

def build_probes(output):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip())
    relative=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-core/src').relative_to(root).as_posix()
    revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip()
    archive=subprocess.check_output(['git','archive',f'{revision}:{relative}'],cwd=root);source=output/'reference-source'
    if source.exists():shutil.rmtree(source)
    source.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:stream.extractall(source,filter='data')
    originals={p.relative_to(source).as_posix():digest(p) for p in sorted(source.rglob('*.rs'))}
    probe=PLUGIN/'Tests/Reference/board_pose_probe.rs';main=source/'board-pose-oracle.rs'
    main.write_text((source/'lib.rs').read_text()+probe.read_text().replace('//!','//'));reference=output/'board-pose-reference'
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():
        if digest(source/name)!=expected:raise AssertionError(f'Frozen reference module changed: {name}')
    snapshot=output/'native-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();native=PLUGIN/'Source/AtelierSkate/Private/Native'
    sources=('NativeMath.h','NativeMath.cpp','GeometryTypes.h','RigidBody.h','DriveFrames.h','ConstraintFrames.h','ConstraintSolver.h','DriveBuild.h','HookDrive.h','HookDrive.cpp','BoardPose.h','BoardPose.cpp')
    for name in sources:shutil.copy2(native/name,snapshot/name)
    shutil.copy2(PLUGIN/'Tests/Native/board_pose_probe.cpp',snapshot/'board_pose_probe.cpp');cpp=output/'board-pose-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),
        *[str(snapshot/name) for name in ('NativeMath.cpp','HookDrive.cpp','BoardPose.cpp','board_pose_probe.cpp')],'-o',str(cpp)],check=True)
    provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,
        probe_sha256=digest(probe),reference_binary_sha256=digest(reference),cpp_binary_sha256=digest(cpp),
        native_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},
        rust_compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),cpp_compiler=subprocess.check_output(['clang++','--version'],text=True).strip())
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return cpp,reference

def decode(data,cases):
    words=struct.unpack('<'+'I'*(len(data)//4),data);at=0;rows=[]
    for case in cases:
        if at+3>len(words):raise AssertionError('Missing board pose frame')
        index,op,n=words[at:at+3]
        if index!=case['index'] or OPERATIONS[op]!=case['operation']:raise AssertionError('Board pose frame identity changed')
        rows.append(words[at+3:at+3+n]);case.update(first_output_word=at,output_words=n+3);at+=n+3
    if at!=len(words):raise AssertionError('Trailing board pose frame')
    return rows

def coverage(rows,cases):
    counts=Counter()
    def part(before,after,requested):
        mask=before[0]
        if after[0]!=mask:raise AssertionError('Part reference presence changed')
        if requested is not None and list(after[1:17])!=requested:raise AssertionError('Part cache did not retain original requested pose')
        if mask&1 and list(after[17:33])!=before[17:33]:raise AssertionError('Local mass frame mutated')
        if mask&4 and list(after[77:87])!=before[77:87]:raise AssertionError('Local inertia record mutated')
        if mask&2:
            body=after[33:77];old=before[33:77];written=set(range(4))|{4,5,6,16,17,18,20,21,22,24,25,26}
            if mask&4:written|={28,29,30,31,32,33,34}
            for i in range(44):
                if i not in written and body[i]!=old[i]:raise AssertionError('Part setter overwrote carried body lanes/rates/forces')
            counts['live_body_updates']+=1
        else:counts['cache_only_updates']+=1
        counts[f'optional_mask_{mask}']+=1
    for row,case in zip(rows,cases):
        op=case['operation']
        if op in ('rotation','part_basis'):
            if list(row[12:16])!=case['initial_matrix'][12:16]:raise AssertionError('Normalizer translation overwritten')
        elif op=='part':
            n=row[16];at=17;before=case['initial_part']
            if n!=len(case['requests']):raise AssertionError('Part request count changed')
            for requested in case['requests']:
                after=row[at:at+87];at+=103;part(before,after,requested);before=list(after)
            if at!=len(row):raise AssertionError('Part output framing changed')
        else:
            n=row[0];at=1;before=case['initial_parts']
            if n!=len(case['requests']):raise AssertionError('Board request count changed')
            for requested in case['requests']:
                next_parts=[]
                for i in range(8):
                    after=row[at:at+87];at+=103;part(before[i],after,requested if i==7 else None);next_parts.append(list(after))
                before=next_parts;counts['board_requests']+=1
            if at!=len(row):raise AssertionError('Board output framing changed')
    for key in ('live_body_updates','cache_only_updates','board_requests'):
        if not counts[key]:raise AssertionError(f'Unexercised board pose branch: {key}')
    return dict(counts)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json','provenance.json'):(output/name).unlink(missing_ok=True)
    inputs,cases=corpus();(output/'input.bin').write_bytes(inputs);cpp,reference=build_probes(output)
    expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(cpp)],input=inputs);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
    rows=decode(expected,cases);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));aligned=first//4*4;case=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None)
        report=dict(passed=False,first_word=first//4,case=case,reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex());(output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    counts=coverage(rows,cases);report=dict(passed=True,cases=len(cases),operations=dict(Counter(c['operation'] for c in cases)),coverage=counts,exact_words=len(expected)//4,input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),comparison='All raw matrix, part/body/inertia and hook state words exact; no repair or tolerance; original numerical modules unchanged')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
