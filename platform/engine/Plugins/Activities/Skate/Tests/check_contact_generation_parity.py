#!/usr/bin/env python3
"""Exact typed contact tangents/workspaces, raw encoding and compiled constraint facade."""
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
OPERATIONS=('generate','typed_compile','raw_compile')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def word(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def value(v):return struct.unpack('<f',struct.pack('<I',v))[0]
def f(v):return [word(x) for x in v]
def corpus():
    rng=random.Random(0x8277a828);records=[];cases=[];output_words=0
    def add(op,payload,label,**extra):
        nonlocal output_words
        size=(66,132,68)[op];cases.append(dict(index=len(cases),operation=OPERATIONS[op],label=label,first_output_word=output_words,output_words=size,**extra));records.append(struct.pack('<'+'I'*(len(payload)+1),op,*payload));output_words+=size
    def body(state=4,linear=(0.,0.,0.),angular=(0.,0.,0.),center=(0.,0.,0.),inv=1.):
        return [rng.getrandbits(32)]+f(center)+[rng.getrandbits(32)]+f([1.,0.,0.,inv,1.,1.,0.])+[state]+f([1.,-9.8,2.,.1,3.,4.,5.])+[rng.getrandbits(32)]+f([*linear,*angular])
    def input(normal=(0.,1.,0.),a=(0.,0.,0.),b=(0.,0.,0.)):
        return f([*a,*b,*normal,.2,.8,.6])+[rng.getrandbits(32)]
    def typed(data,a,b,label,dt=1./60):
        extra=dict(input=data,body_a=a,body_b=b);add(0,data+a+b,label,**extra);add(1,data+a+b+[word(dt)],label,**extra)
    normals=[(1.,0.,0.),(-1.,0.,0.),(0.,1.,0.),(0.,-1.,0.),(0.,0.,1.),(0.,0.,-1.)]
    for bits in (0x3f3504f1,0x3f3504f2,0x3f3504f3,0x3f3504f4,0x3f3504f5):
        x=value(bits);normals.extend(((x,math.sqrt(1-x*x),0.),(-x,math.sqrt(1-x*x),0.)))
    for normal in normals:
        for state_a in (0,4,12):
            for state_b in (0,4,12):
                typed(input(normal),body(state_a),body(state_b),'normal-only X/Z fallback and active-body states')
        for vel in ((1.,2.,3.),(0.,0.,0.),(-0.,-0.,-0.),normal):typed(input(normal),body(),body(linear=vel),'parallel/nonparallel relative velocity tangent')
    for bits in (0,0x80000000,0x1ffffffe,0x1fffffff,0x20000000,0x20000001,0x20000002):
        for sign in (-1.,1.):typed(input((0.,0.,1.)),body(),body(linear=(0.,sign*value(bits),0.)),'minimum-positive squared tangent boundary')
    for dt in (1.e-6,1./120,1./60,.1,1.):
        for inv_a in (0.,1.e-6,1.,100.):
            for inv_b in (0.,1.e-6,1.,100.):typed(input(a=(.1,.2,.3),b=(.2,.1,.4)),body(inv=inv_a,angular=(1.,2.,3.)),body(inv=inv_b,angular=(3.,2.,1.)),'rate arms/force copies/inverse mass/time',dt)
    for _ in range(4096):
        n=[rng.uniform(-1.,1.) for _ in range(3)];length=math.sqrt(sum(v*v for v in n));n=[v/length for v in n]
        data=input(n,[rng.uniform(-10.,10.) for _ in range(3)],[rng.uniform(-10.,10.) for _ in range(3)])
        a=body(rng.choice((0,4,12)),[rng.uniform(-100.,100.) for _ in range(3)],[rng.uniform(-100.,100.) for _ in range(3)],[rng.uniform(-10.,10.) for _ in range(3)],rng.uniform(.001,10.))
        b=body(rng.choice((0,4,12)),[rng.uniform(-100.,100.) for _ in range(3)],[rng.uniform(-100.,100.) for _ in range(3)],[rng.uniform(-10.,10.) for _ in range(3)],rng.uniform(.001,10.))
        typed(data,a,b,'random typed current-body contact generation/compilation',rng.uniform(.0001,.1))
    for _ in range(1024):
        row=f([rng.uniform(-10.,10.) for _ in range(64)])
        row[8:11]=f([0.,1.,0.]);row[12:15]=f([1.,0.,0.]);row[16:19]=f([0.,0.,1.])
        for i in (3,7,23,27,31,43,47,59,63):row[i]=rng.getrandbits(32)
        row[35]=word(rng.uniform(.001,10.));row[39]=word(rng.uniform(.001,10.));row[43]=rng.choice((0,4,12));row[47]=rng.choice((0,4,12))
        add(2,row+[word(rng.uniform(.0001,.1))],'raw compiled facade reaction IDs captured before mutation',reaction_ids=[row[27],row[31]])
    invalid=[]
    for dt in (0,0x80000000,0xbf800000,0x7f800000,0xff800000,0x7fc12345):
        payload=[1]+input()+body()+body()+[dt];invalid.append(struct.pack('<'+'I'*(len(payload)+1),1,*payload))
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
    probe=PLUGIN/'Tests/Reference/contact_generation_probe.rs';main=source/'contact-generation-oracle.rs'
    main.write_text((source/'lib.rs').read_text()+probe.read_text().replace('//!','//'));reference=output/'contact-generation-reference'
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():
        if digest(source/name)!=expected:raise AssertionError(f'Frozen reference module changed: {name}')
    snapshot=output/'simulation-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();simulation=PLUGIN/'Source/AtelierSkate/Private/Simulation'
    sources=('SimulationMath.h','SimulationMath.cpp','GeometryTypes.h','ContactRetention.h','ConstraintSolver.h','ContactBuild.h','ContactBuild.cpp','ContactGeneration.h','ContactGeneration.cpp')
    for name in sources:shutil.copy2(simulation/name,snapshot/name)
    shutil.copy2(PLUGIN/'Tests/Simulation/contact_generation_probe.cpp',snapshot/'contact_generation_probe.cpp');cpp=output/'contact-generation-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),
        *[str(snapshot/name) for name in ('SimulationMath.cpp','ContactBuild.cpp','ContactGeneration.cpp','contact_generation_probe.cpp')],'-o',str(cpp)],check=True)
    provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,
        probe_sha256=digest(probe),reference_binary_sha256=digest(reference),cpp_binary_sha256=digest(cpp),
        simulation_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},
        rust_compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),cpp_compiler=subprocess.check_output(['clang++','--version'],text=True).strip())
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return cpp,reference

def coverage(data,cases):
    counts=Counter()
    for case in cases:
        row=struct.unpack_from('<'+'I'*case['output_words'],data,case['first_output_word']*4);op=case['operation']
        if op!='raw_compile':
            contact=row[2:66];a=case['body_a'];b=case['body_b'];source=case['input']
            if list(contact[:3])!=source[:3] or list(contact[4:7])!=source[3:6] or list(contact[8:11])!=source[6:9]:raise AssertionError('Published geometry changed in contact generator')
            for side,body in enumerate((a,b)):
                expected=body[1:21]
                if body[0]!=contact[3+side*4]:raise AssertionError('Contact body ID changed')
                for vector in range(5):
                    actual=contact[24+side*4+vector*8:28+side*4+vector*8]
                    if list(actual)!=expected[vector*4:vector*4+4]:raise AssertionError('Current-body workspace copy changed')
            counts['nonzero_relative_velocity']+=any(value(v)!=0. for v in contact[20:23]);counts['zero_relative_velocity']+=all(value(v)==0. for v in contact[20:23])
            if op=='typed_compile' and list(row[-2:])!=[a[4],b[4]]:raise AssertionError('Compiled typed reaction ID changed')
        elif list(row[-2:])!=case['reaction_ids']:raise AssertionError('Raw compiled reaction ID changed')
    if not counts['nonzero_relative_velocity'] or not counts['zero_relative_velocity']:raise AssertionError('Fallback/velocity contact tangents unexercised')
    return dict(counts)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json','provenance.json'):(output/name).unlink(missing_ok=True)
    inputs,cases,invalid=corpus();(output/'input.bin').write_bytes(inputs);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');cpp,reference=build_probes(output)
    expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(cpp)],input=inputs);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
    if len(expected)!=sum(c['output_words'] for c in cases)*4:raise AssertionError('Incomplete original contact generation output')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));aligned=first//4*4;case=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None)
        report=dict(passed=False,first_word=first//4,case=case,reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex());(output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    counts=coverage(expected,cases);rejections=[]
    for index,packet in enumerate(invalid):
        (output/f'invalid-time-{index}.bin').write_bytes(packet);a=subprocess.run([str(reference)],input=packet,stdout=subprocess.PIPE,stderr=subprocess.PIPE);b=subprocess.run([str(cpp)],input=packet,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if a.returncode==0 or b'time_step.is_finite()' not in a.stderr:raise AssertionError('Original timestep rejection changed')
        if b.returncode==0 or b'Contact timestep must be positive and finite' not in b.stderr:raise AssertionError('Candidate timestep rejection changed')
        rejections.append(dict(index=index,reference_exit=a.returncode,cpp_exit=b.returncode))
    report=dict(passed=True,cases=len(cases),operations=dict(Counter(c['operation'] for c in cases)),coverage=counts,timestep_rejections=rejections,exact_words=len(expected)//4,input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),comparison='All uncompiled/compiled contact words and reaction IDs exact; original generator, compiler and numerical modules unchanged')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
