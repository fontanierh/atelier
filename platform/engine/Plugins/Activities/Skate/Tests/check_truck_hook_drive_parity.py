#!/usr/bin/env python3
"""Exact truck cache/drive order, normalization carries, hook matrix setters and lifecycle."""
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
OPERATIONS=('trucks','normalize','active','setter','hook')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def word(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def value(v):return struct.unpack('<f',struct.pack('<I',v))[0]
def f(v):return [word(x) for x in v]
def corpus():
    rng=random.Random(0x82c0b9c0);records=[];cases=[]
    def opaque(n):return [rng.getrandbits(32) for _ in range(n)]
    def add(op,payload,label,**extra):
        cases.append(dict(index=len(cases),operation=OPERATIONS[op],label=label,**extra));records.append(struct.pack('<'+'I'*(len(payload)+1),op,*payload))
    def basis(angle=0.,axis=(1.,0.,0.)):
        c=math.cos(angle);s=math.sin(angle);x,y,z=axis;t=1-c
        return [t*x*x+c,t*x*y+s*z,t*x*z-s*y,t*x*y-s*z,t*y*y+c,t*y*z+s*x,t*x*z+s*y,t*y*z-s*x,t*z*z+c]
    def transform(angle=0.,axis=(1.,0.,0.)):
        return f(basis(angle,axis)+[rng.uniform(-100.,100.) for _ in range(3)])
    def basis_words(angle=0.,axis=(1.,0.,0.)):
        b=f(basis(angle,axis));return b[:3]+opaque(1)+b[3:6]+opaque(1)+b[6:9]+opaque(1)
    def frame(q=(0.,0.,0.,1.),other=(0.,0.,0.,1.)):
        return f(q)+opaque(4)+f(other)+opaque(4)
    def unit():
        a=[rng.uniform(-1.,1.) for _ in range(3)];length=math.sqrt(sum(v*v for v in a));return [v/length for v in a]
    for axis in ((1.,0.,0.),(0.,1.,0.),(0.,0.,1.),(2**-.5,2**-.5,0.)):
        for angle in (0.,-0.,1.e-8,.1,math.pi/4,math.pi/2,math.pi,2*math.pi):
            for front in (-1.,-.1,-0.,0.,.1,1.):
                for back in (-1.,0.,1.):
                    b=transform(angle,axis)+transform(-angle,axis);add(0,b+f([front,back]),'truck matrix multiply/order/sign and target boundaries')
    for _ in range(2048):add(0,transform(rng.uniform(-math.pi,math.pi),unit())+transform(rng.uniform(-math.pi,math.pi),unit())+f([rng.uniform(-10.,10.),rng.uniform(-10.,10.)]),'random rigid truck bases and targets')
    quaternions=((0.,0.,0.,0.),(-0.,0.,-0.,0.),(0.,0.,0.,1.),(1.,0.,0.,0.),(0.,1.,0.,0.),(0.,0.,1.,0.),(.1,.2,.3,.4),(1.e-20,1.e-20,0.,0.),(1.e10,-1.e10,1.e10,1.e10))
    for q in quaternions:
        for other in quaternions:
            row=frame(q,other);add(1,row,'normalization zero/tiny/finite and opaque translations',initial_frames=row)
    for _ in range(2048):
        row=frame([rng.uniform(-100.,100.) for _ in range(4)],[rng.uniform(-100.,100.) for _ in range(4)]);add(1,row,'random unnormalized drive quaternions',initial_frames=row)
    for n in (0,1,2,7,32):
        rows=[frame([rng.uniform(-1.,1.) for _ in range(4)],[rng.uniform(-1.,1.) for _ in range(4)]) for _ in range(n)]
        for k in (0,1,2,10,100):
            indices=[rng.choice([0xffffffff]+list(range(n))) for _ in range(k)];add(2,[n]+[v for row in rows for v in row]+[k]+indices,'active null/duplicate/insertion order',initial_frames=rows,indices=indices)
    for _ in range(512):
        n=rng.randrange(1,33);rows=[frame([rng.uniform(-100.,100.) for _ in range(4)],[rng.uniform(-100.,100.) for _ in range(4)]) for _ in range(n)];indices=[rng.choice([0xffffffff]+list(range(n))) for _ in range(rng.randrange(1,101))]
        add(2,[n]+[v for row in rows for v in row]+[len(indices)]+indices,'random active normalization registrations',initial_frames=rows,indices=indices)
    for axis in ((1.,0.,0.),(0.,1.,0.),(0.,0.,1.),(2**-.5,2**-.5,0.)):
        for angle in (0.,-0.,1.e-8,.1,math.pi/2,math.pi,2*math.pi):
            for parent in (0,1):
                row=opaque(16);add(3,row+basis_words(angle,axis)+[parent],'hook quaternion branch/sign and carry',initial_frames=row,parent=parent)
    for diag in ((0.,0.,0.),(1.,1.,1.),(-1.,-1.,-1.),(10.,-2.,-2.),(-2.,10.,-2.),(-2.,-2.,10.),(-10.,-10.,-10.),(.1,.1,.1)):
        for parent in (0,1):
            b=opaque(12)
            for i in (0,1,2,4,5,6,8,9,10):b[i]=0
            b[0],b[5],b[10]=f(diag);row=opaque(16);add(3,row+b+[parent],'non-unit diagonal matrix: no normalization fallback',initial_frames=row,parent=parent)
    for _ in range(2048):
        row=opaque(16);parent=rng.randrange(2);add(3,row+basis_words(rng.uniform(-math.pi,math.pi),unit())+[parent],'random authored hook matrix and opaque carries',initial_frames=row,parent=parent)
    def hook(commands,label):
        frames=frame([rng.uniform(-1.,1.) for _ in range(4)],[rng.uniform(-1.,1.) for _ in range(4)]);dynamics=opaque(8);dynamics[3]=rng.choice((0,1,2,3,0xffffffff));dynamics[7]=rng.choice((0,1,2,3,0xffffffff));animated=rng.randrange(256)
        payload=frames+dynamics+[animated,len(commands)]
        for command in commands:payload.extend(command)
        add(4,payload,label,commands=[c[0] for c in commands],initial_frames=frames,initial_animated=animated)
    for first in range(10):
        for second in range(10):
            commands=[]
            for op in (first,second):commands.append([op]+(basis_words(.4,(0.,1.,0.)) if op in (7,8) else []))
            hook(commands,'all hook lifecycle/setter/normalization command pairs')
    for _ in range(512):
        commands=[]
        for _ in range(rng.randrange(1,65)):
            op=rng.randrange(10);commands.append([op]+(basis_words(rng.uniform(-math.pi,math.pi),unit()) if op in (7,8) else []))
        hook(commands,'random live hook state lifecycle')
    invalid=[]
    for n,indices in ((0,[0]),(1,[1]),(1,[0,1]),(2,[0xffffffff,1,0xfffffffe])):
        rows=[frame() for _ in range(n)];payload=[2,n]+[v for row in rows for v in row]+[len(indices)]+indices
        invalid.append(struct.pack('<'+'I'*(len(payload)+1),1,*payload))
    return struct.pack('<I',len(records))+b''.join(records),cases,invalid

def build_probes(output):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip())
    relative=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-core/src').relative_to(root).as_posix()
    revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip()
    archive=subprocess.check_output(['git','archive',f'{revision}:{relative}'],cwd=root);source=output/'reference-source'
    if source.exists():shutil.rmtree(source)
    source.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:stream.extractall(source,filter='data')
    originals={p.relative_to(source).as_posix():digest(p) for p in sorted(source.rglob('*.rs'))}
    probe=PLUGIN/'Tests/Reference/truck_hook_drive_probe.rs';main=source/'truck-hook-drive-oracle.rs'
    main.write_text((source/'lib.rs').read_text()+probe.read_text().replace('//!','//'));reference=output/'truck-hook-drive-reference'
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():
        if digest(source/name)!=expected:raise AssertionError(f'Frozen reference module changed: {name}')
    snapshot=output/'native-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();native=PLUGIN/'Source/AtelierSkate/Private/Native'
    sources=('NativeMath.h','NativeMath.cpp','GeometryTypes.h','RigidBody.h','BodyMass.h','BodyMass.cpp','AggregateMass.h','AggregateMass.cpp','DeckGeometry.h','DeckGeometry.cpp','DriveFrames.h','DriveFrames.cpp','ConstraintFrames.h','ConstraintSolver.h','DriveBuild.h','TruckDriveFrames.h','TruckDriveFrames.cpp','DrivePreparation.h','DrivePreparation.cpp','HookDrive.h','HookDrive.cpp')
    for name in sources:shutil.copy2(native/name,snapshot/name)
    shutil.copy2(PLUGIN/'Tests/Native/truck_hook_drive_probe.cpp',snapshot/'truck_hook_drive_probe.cpp');cpp=output/'truck-hook-drive-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),
        *[str(snapshot/name) for name in ('NativeMath.cpp','BodyMass.cpp','AggregateMass.cpp','DeckGeometry.cpp','DriveFrames.cpp','TruckDriveFrames.cpp','DrivePreparation.cpp','HookDrive.cpp','truck_hook_drive_probe.cpp')],'-o',str(cpp)],check=True)
    provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,
        probe_sha256=digest(probe),reference_binary_sha256=digest(reference),cpp_binary_sha256=digest(cpp),
        native_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},
        rust_compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),cpp_compiler=subprocess.check_output(['clang++','--version'],text=True).strip())
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return cpp,reference

def decode(data,cases):
    words=struct.unpack('<'+'I'*(len(data)//4),data);at=0;rows=[]
    for case in cases:
        if at+3>len(words):raise AssertionError('Missing drive lifecycle output frame')
        index,op,n=words[at:at+3]
        if index!=case['index'] or OPERATIONS[op]!=case['operation']:raise AssertionError('Drive lifecycle frame identity changed')
        rows.append(words[at+3:at+3+n]);case.update(first_output_word=at,output_words=n+3);at+=n+3
    if at!=len(words):raise AssertionError('Trailing drive lifecycle frame')
    return rows

def coverage(rows,cases):
    counts=Counter()
    def translations(row):return list(row[4:8]+row[12:16])
    for row,case in zip(rows,cases):
        op=case['operation']
        if op=='normalize':
            if translations(row)!=translations(case['initial_frames']):raise AssertionError('Normalization translations overwritten')
        elif op=='active':
            initial=case['initial_frames'];active={i for i in case['indices'] if i!=0xffffffff};counts['duplicate_registrations']+=len([i for i in case['indices'] if i!=0xffffffff])-len(active);counts['null_registrations']+=case['indices'].count(0xffffffff)
            for i,before in enumerate(initial):
                after=row[i*16:i*16+16]
                if translations(after)!=translations(before):raise AssertionError('Active normalization translations overwritten')
                if i not in active and list(after)!=before:raise AssertionError('Unregistered frame overwritten')
        elif op=='setter':
            offset=8 if case['parent'] else 0
            for i,v in enumerate(row):
                if not offset<=i<offset+4 and v!=case['initial_frames'][i]:raise AssertionError('Angular setter overwrote carried frame lanes')
            squared=sum(value(row[offset+i])**2 for i in range(4))
            counts['non_unit_setter_results']+=math.isfinite(squared) and abs(squared-1.)>.01
        elif op=='hook':
            if row[0]!=len(case['commands']):raise AssertionError('Hook command count changed')
            before=row[1:34]
            for i,command in enumerate(case['commands']):
                after=row[34+i*33:67+i*33];counts[f'hook_command_{command}']+=1
                if command not in (0,7,8,9) and before[:16]!=after[:16]:raise AssertionError('Dynamics lifecycle rewrote hook frames')
                if command in (2,5,6,7,8,9) and before[24]!=after[24]:raise AssertionError('Caller animated flag was overwritten')
                before=after
    for key in ('duplicate_registrations','null_registrations','non_unit_setter_results'):
        if not counts[key]:raise AssertionError(f'Unexercised drive lifecycle branch: {key}')
    return dict(counts)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json','provenance.json'):(output/name).unlink(missing_ok=True)
    inputs,cases,invalid=corpus();(output/'input.bin').write_bytes(inputs);cpp,reference=build_probes(output)
    expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(cpp)],input=inputs);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
    rows=decode(expected,cases);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));aligned=first//4*4;case=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None)
        report=dict(passed=False,first_word=first//4,case=case,reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex());(output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    rejection_reports=[]
    for index,packet in enumerate(invalid):
        (output/f'invalid-active-{index}.bin').write_bytes(packet);a=subprocess.run([str(reference)],input=packet,stdout=subprocess.PIPE,stderr=subprocess.PIPE);b=subprocess.run([str(cpp)],input=packet,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if a.returncode==0 or b'index out of bounds' not in a.stderr:raise AssertionError('Original invalid registration rejection changed')
        if b.returncode==0 or b'Active drive frame index out of range' not in b.stderr:raise AssertionError('Candidate failed to reject invalid frame registration')
        rejection_reports.append(dict(index=index,reference_exit=a.returncode,cpp_exit=b.returncode))
    counts=coverage(rows,cases);report=dict(passed=True,cases=len(cases),operations=dict(Counter(c['operation'] for c in cases)),coverage=counts,registration_rejections=rejection_reports,exact_words=len(expected)//4,input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),comparison='Every output word exact; carried lanes and repeated normalization retained; frozen numerical modules unchanged')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
