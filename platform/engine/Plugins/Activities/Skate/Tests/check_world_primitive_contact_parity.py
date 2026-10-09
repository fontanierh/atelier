#!/usr/bin/env python3
"""Original typed sphere/capsule/triangle/box world contacts, transformation and prediction."""
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
OPERATIONS=('limit','transform','contact')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def word(value):return struct.unpack('<I',struct.pack('<f',value))[0]
def value(bits):return struct.unpack('<f',struct.pack('<I',bits))[0]
def f(values):return [word(v) for v in values]
def corpus():
    rng=random.Random(0x8277bc58);records=[];cases=[];output_words=0
    def add(op,payload,label,**extra):
        nonlocal output_words
        size=(3,31,103)[op];cases.append(dict(index=len(cases),operation=OPERATIONS[op],label=label,first_output_word=output_words,output_words=size,**extra))
        records.append(struct.pack('<'+'I'*(len(payload)+1),op,*payload));output_words+=size
    def basis(y=0.,x=0.):
        cy=math.cos(y);sy=math.sin(y);cx=math.cos(x);sx=math.sin(x)
        return (cy,sx*sy,-cx*sy,0.,cx,sx,sy,-sx*cy,cx*cy)
    def triangle(center=(0.,0.,0.),size=3.,fat=0.,flags=0xe0,cosines=(.5,.5,.5),angle=0.,tilt=0.,reverse=False):
        columns=basis(angle,tilt);local=[(-size,0.,-size),(0.,0.,size),(size,0.,-size)];points=[]
        for p in local:points.extend([center[j]+sum(columns[i*3+j]*p[i] for i in range(3)) for j in range(3)])
        if reverse:points=points[:3]+points[6:9]+points[3:6]
        return f(points+[fat,*cosines])+[flags]
    def primitive(kind,center=(0.,.2,0.),radius=.2,angle=0.,tilt=0.,half=(.5,.1,.3)):
        if kind==0:return [kind]+f([*center,radius])
        if kind==1:
            columns=basis(angle,tilt);return [kind]+f([*center,*columns[:3],half[0],radius])
        if kind==2:return [kind]+triangle(size=half[0],fat=radius)+f([*basis(angle,tilt),*center])
        return [kind]+f([*center,*basis(angle,tilt),*half,radius])
    def contact(kind,primitive_words,t,label,velocity=(0.,0.,0.),padding=.01,maximum=.1,bend=.95,epsilon=.0001,obj=False):
        add(2,primitive_words+t+f([*velocity,padding,maximum,bend,epsilon])+[int(obj)],label,kind=kind)
    scalars=(0.,-0.,1.e-8,.001,.01,.1,1.,60.,100000.)
    for velocity_y in (-100000.,-60.,-1.,-0.,0.,1.,60.,100000.):
        for padding in scalars[:6]:
            for maximum in scalars[:7]:add(0,f([1.,velocity_y,-2.,0.,1.,0.,padding,maximum]),'fixed 1/60 prediction clamp boundaries')
    for _ in range(1024):add(0,f([*[rng.uniform(-1.e5,1.e5) for _ in range(3)],*[rng.uniform(-1.,1.) for _ in range(3)],rng.uniform(-.1,1.),rng.uniform(-.1,1.)]),'random prediction')
    for angle in (0.,math.pi/4,math.pi/2,math.pi):
        for tilt in (0.,math.pi/4,-math.pi/2):
            for size in (.0001,1.,1000.):
                for translation in ((0.,0.,0.),(1.,2.,3.),(1.e5,-1.e5,1.e5)):
                    add(1,triangle(size=size,flags=0xff2)+f([*basis(angle,tilt),*translation]),'local normal before transform/cache rebuild')
    for _ in range(1024):
        vertices=f([rng.uniform(-10.,10.) for _ in range(9)]+[rng.uniform(0.,.2)]+[rng.uniform(-1.,1.) for _ in range(3)])+[rng.getrandbits(12)]
        add(1,vertices+f([*basis(rng.uniform(-math.pi,math.pi),rng.uniform(-math.pi,math.pi)),*[rng.uniform(-100.,100.) for _ in range(3)]]),'random rigid transformed triangles')
    for kind in range(4):
        for x,z in ((0.,0.),(-3.,-3.),(3.,-3.),(0.,3.),(-1.5,0.),(1.5,0.),(0.,-3.),(4.,4.)):
            for height in (-1.,-.2,-0.,0.,1.e-7,.1,.2,.3,1.,4.):
                for fat in (0.,.01,.2):contact(kind,primitive(kind,(x,height,z)),triangle(fat=fat),'face/edge/vertex/overlap/miss and world fatness')
        for radius in (0.,1.e-8,.001,.01,.1,.2,1.):
            for height in (.09999999,.1,.10000001,.19999999,.2,.20000001):
                contact(kind,primitive(kind,(0.,height,0.),radius),triangle(),'radius/limit exact neighbors')
    for flags in range(256):
        tflags=((flags&1)<<4)|((flags&2)<<7)|((flags&0x1c)<<3)|((flags&0xe0)<<4)
        for kind in range(4):
            for center in ((0.,.1,0.),(2.9,.2,-2.9),(0.,-.1,0.)):
                contact(kind,primitive(kind,center),triangle(flags=tflags),'all triangle adjacency flags',obj=bool(flags&4))
    for kind in range(4):
        for angle in (0.,1.e-8,.01,math.pi/4,math.pi/2,math.pi):
            for tilt in (0.,.1,.5,math.pi/2):
                contact(kind,primitive(kind,angle=angle,tilt=tilt),triangle(),'axis/edge parallel crosses and rotated primitive')
        for velocity_y in (-1000.,-6.,-1.,0.,1.,1000.):
            for padding in (0.,.01,.1):
                contact(kind,primitive(kind,(0.,.5,0.)),triangle(),'approach extends world query only to maximum',velocity=(0.,velocity_y,0.),padding=padding)
    for _ in range(8192):
        kind=rng.randrange(4);center=[rng.uniform(-4.,4.),rng.uniform(-.5,.8),rng.uniform(-4.,4.)];radius=rng.uniform(0.,.5)
        p=primitive(kind,center,radius,rng.uniform(-math.pi,math.pi),rng.uniform(-.3,.3),[rng.uniform(.01,1.) for _ in range(3)])
        flags=rng.choice((0,0xe0,0x10,0xf0,0x110,0x1f0,0xff0));t=triangle(size=rng.uniform(1.,5.),fat=rng.uniform(0.,.05),flags=flags,cosines=[rng.uniform(.01,1.) for _ in range(3)],angle=rng.uniform(-.3,.3),tilt=rng.uniform(-.2,.2),reverse=bool(rng.randrange(2)))
        contact(kind,p,t,'random typed primitive/world dispatch',velocity=[rng.uniform(-10.,10.) for _ in range(3)],padding=rng.uniform(0.,.1),maximum=rng.uniform(0.,.2),obj=bool(rng.randrange(2)))
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
    probe=PLUGIN/'Tests/Reference/world_primitive_contact_probe.rs';main=source/'world-primitive-contact-oracle.rs'
    main.write_text((source/'lib.rs').read_text()+probe.read_text().replace('//!','//'));reference=output/'world-primitive-contact-reference'
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():
        if digest(source/name)!=expected:raise AssertionError(f'Frozen reference module changed: {name}')
    snapshot=output/'simulation-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();simulation=PLUGIN/'Source/AtelierSkate/Private/Simulation'
    sources=('SimulationMath.h','SimulationMath.cpp','GeometryTypes.h','Geometry.h','Geometry.cpp','GeometrySweep.h','GeometrySweep.cpp','WorldGeometry.h','WorldGeometry.cpp','GeometryFeatures.h','GeometryFeatures.cpp','GeometryPrism.h','GeometryPrism.cpp','GeometryTriangleFixup.h','GeometryTriangleFixup.cpp','WorldPrimitiveContact.h','WorldPrimitiveContact.cpp','PrimitiveGeometry.h')
    for name in sources:shutil.copy2(simulation/name,snapshot/name)
    shutil.copy2(PLUGIN/'Tests/Simulation/world_primitive_contact_probe.cpp',snapshot/'world_primitive_contact_probe.cpp');cpp=output/'world-primitive-contact-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),
        *[str(snapshot/name) for name in ('SimulationMath.cpp','Geometry.cpp','GeometrySweep.cpp','WorldGeometry.cpp','GeometryFeatures.cpp','GeometryPrism.cpp','GeometryTriangleFixup.cpp','WorldPrimitiveContact.cpp','world_primitive_contact_probe.cpp')],'-o',str(cpp)],check=True)
    provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,
        probe_sha256=digest(probe),reference_binary_sha256=digest(reference),cpp_binary_sha256=digest(cpp),
        simulation_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},
        rust_compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),cpp_compiler=subprocess.check_output(['clang++','--version'],text=True).strip())
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return cpp,reference

def coverage(data,cases):
    counts=Counter();kinds={str(i):Counter() for i in range(4)}
    for case in cases:
        if case['operation']!='contact':continue
        row=struct.unpack_from('<103I',data,case['first_output_word']*4);present=row[2];n=row[6]
        counts['hits' if present else 'misses']+=1;kinds[str(case['kind'])]['hits' if present else 'misses']+=1
        if present:
            if not 1<=n<=16:raise AssertionError('Invalid manifold count')
            counts[f'point_count_{n}']+=1
            if any(row[7+n*6:]):raise AssertionError('Unused manifold slots not zero')
            if not all(math.isfinite(value(v)) for v in row[3:6]+row[7:7+n*6]):raise AssertionError('Valid simulation inputs produced nonfinite contacts')
    for kind,entries in kinds.items():
        if not entries['hits'] or not entries['misses']:raise AssertionError(f'Unexercised primitive hits/misses: {kind}')
    if not counts['point_count_1'] or not counts['point_count_2'] or not any(counts[f'point_count_{n}'] for n in range(3,17)):raise AssertionError('Point/segment/face contact paths unexercised')
    return dict(counts),{k:dict(v) for k,v in kinds.items()}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json','provenance.json'):(output/name).unlink(missing_ok=True)
    inputs,cases=corpus();(output/'input.bin').write_bytes(inputs);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    cpp,reference=build_probes(output);expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(cpp)],input=inputs)
    (output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
    if len(expected)!=sum(c['output_words'] for c in cases)*4:raise AssertionError('Incomplete original primitive contact output')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));aligned=first//4*4
        case=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None)
        report=dict(passed=False,first_word=first//4,case=case,reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex())
        (output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    counts,kinds=coverage(expected,cases)
    report=dict(passed=True,cases=len(cases),operations=dict(Counter(c['operation'] for c in cases)),coverage=counts,primitives=kinds,exact_words=len(expected)//4,
        output_sha256=hashlib.sha256(expected).hexdigest(),input_sha256=hashlib.sha256(inputs).hexdigest(),comparison='All words exact; no tolerance or NaN canonicalization; frozen numerical modules unchanged',
        indirect_coverage='GP packing and private triangle/box SAT are exercised through the original public typed contact query')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
