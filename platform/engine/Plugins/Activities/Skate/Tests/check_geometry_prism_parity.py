#!/usr/bin/env python3
"""Compare complete feature prisms and mutated headers with frozen public callbacks."""
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
OPERATIONS=('closest','point_face','clamp','clip','segment_segment','segment_face','corner_edge','dispatcher')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def word(value):return struct.unpack('<I',struct.pack('<f',value))[0]
def value(bits):return struct.unpack('<f',struct.pack('<I',bits))[0]
def f(values):return [word(v) for v in values]
def corpus():
    rng=random.Random(0x82ace190);records=[];cases=[];output_words=0;input_words=1
    def opaque(count):return [rng.getrandbits(32) for _ in range(count)]
    def add(op,words,label,**extra):
        nonlocal output_words,input_words
        size=7 if op in (0,2) else 13 if op==3 else 427
        cases.append(dict(index=len(cases),operation=OPERATIONS[op],label=label,first_output_word=output_words,output_words=size,first_input_word=input_words,input_words=len(words)+1,**extra))
        records.append(struct.pack('<'+'I'*(len(words)+1),op,*words));output_words+=size;input_words+=len(words)+1
    def feature(count,center=(0.,0.,0.),radius=1.,angle=0.,tilt=0.,reverse=False):
        row=opaque(144);row[140]=count;row[136:140]=f([*center,1.]);row[132:136]=f([0.,-math.sin(tilt),math.cos(tilt),0.])
        points=[]
        if count==1:points=[(-radius,0.),(radius,0.)]
        elif count:points=[(radius*math.cos(angle+2*math.pi*i/count),radius*math.sin(angle+2*math.pi*i/count)) for i in range(count)]
        if reverse:points.reverse()
        xyz=[(center[0]+x,center[1]+y*math.cos(tilt),center[2]+y*math.sin(tilt),1.) for x,y in points]
        normal=(0.,-math.sin(tilt),math.cos(tilt))
        for i in range(count):
            a=xyz[i];b=xyz[1] if count==1 else xyz[(i+1)%count];delta=[b[j]-a[j] for j in range(3)];length=math.sqrt(sum(v*v for v in delta));direction=[v/length if length else 0. for v in delta]
            # Outward plane is edge cross face normal, matching maximum-feature records.
            plane=[direction[1]*normal[2]-direction[2]*normal[1],direction[2]*normal[0]-direction[0]*normal[2],direction[0]*normal[1]-direction[1]*normal[0]]
            offset=4+i*16;row[offset:offset+4]=f(a);row[offset+4:offset+8]=f([*direction,0.]);row[offset+8:offset+12]=f([*plane,0.]);row[offset+12:offset+16]=f([length]*4)
        return row
    def pair(op,a,b,normal=(0.,0.,1.,0.),label='feature pair',first=True,corner=0,edge=0):
        initial=opaque(136);initial[132]=rng.randrange(17);initial[133]=rng.choice((0,1,0xffffffff))
        payload=initial+a+b+f(normal)
        if op in (1,4,5):payload+=[int(first)]
        elif op==6:payload+=[corner,edge,int(first)]
        add(op,payload,label,initial_prism=initial,initial_headers=[a[0],b[0]],counts=[a[140],b[140]])
    for length in (0.,1.e-9,1.e-4,1.,1000.):
        a=feature(1,radius=length*.5)
        for position in (-100.,-1.e-4,-0.,0.,1.e-8,.5,1.,1.000001,100.):
            for w in (0.,1.,-0.,77.):add(0,a[4:20]+f([length*(position-.5),1.,0.,w]),'closest endpoint/equality/zero/W lanes')
    for _ in range(1024):
        a=feature(1,[rng.uniform(-10.,10.) for _ in range(3)],rng.uniform(.0001,10.))
        if rng.randrange(3)==0:a[16:20]=f([rng.uniform(-1.,10.) for _ in range(4)])
        add(0,a[4:20]+f([rng.uniform(-100.,100.) for _ in range(4)]),'closest random and nonbroadcast lengths')
    for count in (3,4,5,6,8):
        a=feature(count)
        for center in ((0.,0.,.1),(1.,0.,.1),(2.,0.,.1),(0.,2.,-.2),(-2.,-2.,.3)):
            for first in (False,True):pair(1,a,feature(0,center),label='point face interior/outside/corner',first=first)
            add(2,a+f([0.,0.,1.,0.])+f([*center,1.]),'point clamp feature regions')
        for center in ((0.,0.,.1),(0.,2.,.1),(2.,0.,.1),(-1.,1.,.1)):
            for radius in (0.,1.e-4,.001,1.,4.):
                b=feature(1,center,radius);outside=opaque(8)
                add(3,a+b+f([0.,0.,1.,0.])+opaque(2)+outside,'segment clip interior/exterior/zero interval',initial_outside=outside)
                for first in (False,True):pair(5,a,b,label='segment face clipped/projected/normal correction',first=first)
    for _ in range(1024):
        count=rng.choice((3,4,5,6,8));a=feature(count,angle=rng.uniform(-3.,3.),radius=rng.uniform(.1,10.))
        p=[rng.uniform(-10.,10.) for _ in range(3)]
        pair(1,a,feature(0,p),label='random point face',first=bool(rng.randrange(2)))
        add(2,a+f([0.,0.,1.,0.])+f([*p,1.]),'random clamp')
        b=feature(1,p,rng.uniform(0.,10.),tilt=rng.uniform(-.1,.1));outside=opaque(8)
        add(3,a+b+f([0.,0.,1.,0.])+opaque(2)+outside,'random clip',initial_outside=outside)
        pair(5,a,b,label='random segment face',first=bool(rng.randrange(2)))
    threshold=value(0x34000000)**.5
    for rotation in (0.,threshold*.99,threshold,threshold*1.01,.05,.5,math.pi/2,math.pi):
        for offset in (-4.,-2.,-1.,0.,1.,2.,4.):
            for first in (False,True):
                a=feature(1);b=feature(1,(offset,.1,.2));b[8:12]=f([math.cos(rotation),math.sin(rotation),0.,0.])
                pair(4,a,b,label='segment parallel/overlap/disjoint/cross threshold',first=first)
    for _ in range(1024):
        a=feature(1,radius=rng.uniform(.0001,10.));b=feature(1,[rng.uniform(-10.,10.) for _ in range(3)],rng.uniform(.0001,10.))
        for row in (a,b):
            v=[rng.uniform(-1.,1.) for _ in range(3)];length=math.sqrt(sum(t*t for t in v));row[8:12]=f([*[t/length for t in v],0.])
        pair(4,a,b,label='random segment pair',first=bool(rng.randrange(2)))
    for count in (3,4,5,6,8):
        a=feature(count)
        for corner in range(count):
            for edge in range(count):
                b=feature(count,(2.,0.,.1))
                for first in (False,True):pair(6,a,b,label='all corner/edge pointer orders',first=first,corner=corner,edge=edge)
    for _ in range(1024):
        ac=rng.choice((3,4,5,6,8));bc=rng.choice((3,4,5,6,8));a=feature(ac,angle=rng.uniform(-3.,3.));b=feature(bc,[rng.uniform(-5.,5.) for _ in range(3)],angle=rng.uniform(-3.,3.))
        pair(6,a,b,label='random corner edge',first=bool(rng.randrange(2)),corner=rng.randrange(ac),edge=rng.randrange(bc))
    for ac in (0,1,3,4,5,6,8):
        for bc in (0,1,3,4,5,6,8):
            for offset in ((0.,0.,.1),(.5,.2,-.1),(2.,0.,.3),(3.,3.,0.)):
                pair(7,feature(ac),feature(bc,offset),label='dispatcher all count pairs/coincident/overlap/fallback')
    for _ in range(2048):
        ac=rng.choice((0,1,3,4,5,6,8));bc=rng.choice((0,1,3,4,5,6,8));a=feature(ac,radius=rng.uniform(.1,5.),angle=rng.uniform(-3.,3.));b=feature(bc,[rng.uniform(-5.,5.) for _ in range(3)],rng.uniform(.1,5.),rng.uniform(-3.,3.),rng.uniform(-.2,.2))
        pair(7,a,b,label='random dispatcher convex features')
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
    probe=PLUGIN/'Tests/Reference/geometry_prism_probe.rs';main=source/'geometry-prism-oracle.rs'
    main.write_text((source/'lib.rs').read_text()+probe.read_text().replace('//!','//'));reference=output/'geometry-prism-reference'
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():
        if digest(source/name)!=expected:raise AssertionError(f'Frozen reference module changed: {name}')
    snapshot=output/'simulation-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();simulation=PLUGIN/'Source/AtelierSkate/Private/Simulation'
    sources=('SimulationMath.h','SimulationMath.cpp','GeometryTypes.h','GeometryFeatures.h','GeometryFeatures.cpp','GeometryPrism.h','GeometryPrism.cpp')
    for name in sources:shutil.copy2(simulation/name,snapshot/name)
    shutil.copy2(PLUGIN/'Tests/Simulation/geometry_prism_probe.cpp',snapshot/'geometry_prism_probe.cpp');cpp=output/'geometry-prism-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),
        *[str(snapshot/name) for name in ('SimulationMath.cpp','GeometryFeatures.cpp','GeometryPrism.cpp','geometry_prism_probe.cpp')],'-o',str(cpp)],check=True)
    provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,
        probe_sha256=digest(probe),reference_binary_sha256=digest(reference),cpp_binary_sha256=digest(cpp),
        simulation_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},
        rust_compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),cpp_compiler=subprocess.check_output(['clang++','--version'],text=True).strip())
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return cpp,reference

def separate_capacity_rejections(cpp,reference,inputs,cases):
    records=[inputs[c['first_input_word']*4:(c['first_input_word']+c['input_words'])*4] for c in cases]
    remaining=list(zip(records,cases));rejections=[]
    def packet(rows):return struct.pack('<I',len(rows))+b''.join(row[0] for row in rows)
    def oracle(rows):return subprocess.run([str(reference)],input=packet(rows),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    while True:
        result=oracle(remaining)
        if result.returncode==0:break
        if b'feature prism point capacity exceeded' not in result.stderr:raise AssertionError(result.stderr.decode())
        lo=0;hi=len(remaining)
        while lo+1<hi:
            mid=(lo+hi)//2;attempt=oracle(remaining[:mid])
            if attempt.returncode:hi=mid
            else:lo=mid
        record,case=remaining.pop(hi-1);original=oracle([(record,case)])
        candidate=subprocess.run([str(cpp)],input=packet([(record,case)]),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if original.returncode==0 or b'feature prism point capacity exceeded' not in original.stderr:raise AssertionError('Original capacity rejection changed')
        if candidate.returncode==0 or b'Native feature storage contract exceeded' not in candidate.stderr:raise AssertionError('Candidate did not reject the same overcapacity prism')
        rejections.append(dict(case=case,reference_exit=original.returncode,cpp_exit=candidate.returncode,
            reference_error=original.stderr.decode(),cpp_error=candidate.stderr.decode(),input_hex=record.hex()))
    valid=[];output_words=0;input_words=1
    for index,(record,case) in enumerate(remaining):
        revised=dict(case,index=index,original_index=case['index'],first_input_word=input_words,first_output_word=output_words)
        valid.append(revised);output_words+=case['output_words'];input_words+=case['input_words']
    return packet(remaining),valid,result.stdout,rejections

def coverage(data,cases):
    counts=Counter();dispatcher=Counter()
    for case in cases:
        row=struct.unpack_from('<'+'I'*case['output_words'],data,case['first_output_word']*4);op=case['operation'];result=row[2]
        counts[f'{op}_return_{result}']+=1
        if 'initial_prism' in case:
            prism=row[3:139];initial=case['initial_prism']
            if list(prism[134:136])!=initial[134:136]:raise AssertionError('Prism padding overwritten')
            counts['normal_corrections']+=prism[133]!=initial[133]
            counts['header_mutations']+=list((row[139],row[283]))!=case['initial_headers']
            if op!='corner_edge':counts[f'prism_points_{prism[132]}']+=1
            if op=='dispatcher':dispatcher[str(tuple(case['counts']))]+=1
        if op=='clip':counts['outside_scratch_retained']+=list(row[5:13])==case['initial_outside']
    for key in ('normal_corrections','header_mutations','outside_scratch_retained','prism_points_1','prism_points_2'):
        if not counts[key]:raise AssertionError(f'Unexercised prism branch: {key}')
    return dict(counts),dict(dispatcher)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json','provenance.json'):(output/name).unlink(missing_ok=True)
    inputs,cases=corpus();(output/'input.bin').write_bytes(inputs);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    cpp,reference=build_probes(output);inputs,cases,expected,rejections=separate_capacity_rejections(cpp,reference,inputs,cases)
    (output/'valid-input.bin').write_bytes(inputs);(output/'valid-cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    (output/'capacity-rejections.json').write_text(json.dumps(rejections,indent=2)+'\n');actual=subprocess.check_output([str(cpp)],input=inputs)
    (output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
    if len(expected)!=sum(c['output_words'] for c in cases)*4:raise AssertionError('Incomplete original prism output')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));aligned=first//4*4
        case=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None)
        report=dict(passed=False,first_word=first//4,case=case,reference_length=len(expected),cpp_length=len(actual),
            reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex())
        (output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    counts,dispatcher=coverage(expected,cases)
    report=dict(passed=True,cases=len(cases),capacity_rejections=len(rejections),operations=dict(Counter(c['operation'] for c in cases)),coverage=counts,dispatcher_pairs=dispatcher,
        exact_words=len(expected)//4,output_sha256=hashlib.sha256(expected).hexdigest(),input_sha256=hashlib.sha256(inputs).hexdigest(),
        comparison='All words exact; no tolerance or NaN canonicalization; every original numerical module unchanged')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
