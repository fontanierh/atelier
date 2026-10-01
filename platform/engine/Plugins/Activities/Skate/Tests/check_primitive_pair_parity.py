#!/usr/bin/env python3
"""Exact original simulation GP-pair manifolds, including specialized sphere/box dispatch.

Original numeric Rust modules remain unchanged; run through the render lock and memory guard.
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
OPERATIONS=('defaults','pair')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def word(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def value(w):return struct.unpack('<f',struct.pack('<I',w))[0]
def f(v):return list(map(word,v))
def corpus():
    rng=random.Random(0x82ad43a8);records=[];cases=[];at=0
    def add(op,payload,label,**meta):
        nonlocal at
        n=(7,103)[op];cases.append(dict(index=len(cases),operation=OPERATIONS[op],label=label,first_output_word=at,output_words=n,**meta));at+=n
        records.append(struct.pack('<'+'I'*(len(payload)+1),op,*payload))
    def basis(y=0.,x=0.):
        cy,sy,cx,sx=math.cos(y),math.sin(y),math.cos(x),math.sin(x)
        return (cy,sx*sy,-cx*sy,0.,cx,sx,sy,-sx*cy,cx*cy)
    def primitive(kind,center=(0.,0.,0.),radius=.1,y=0.,x=0.,half=(.5,.3,.4),flags=0xe0,cosines=(.5,.5,.5),reverse=False):
        axes=basis(y,x)
        if kind==0:return [kind]+f([*center,radius])
        if kind==1:return [kind]+f([*center,*axes[6:9],half[2],radius])
        if kind==2:
            size=half[0];points=[-size,0.,-size,0.,0.,size,size,0.,-size]
            if reverse:points=points[:3]+points[6:9]+points[3:6]
            return [kind]+f(points+[radius,*cosines])+[flags]+f([*axes,*center])
        return [kind]+f([*center,*axes,*half,radius])
    stock=[0x3d4ccccd,0x3d4ccccd,0,0x3f7fbe77,0x3c23d70a]
    def pair(ak,bk,a,b,label,s=None,degenerate=False):add(1,a+b+(stock if s is None else s),label,kind_a=ak,kind_b=bk,degenerate=degenerate)
    add(0,[],'frozen original self collision constants')
    centers=((0.,.1,0.),(0.,.3,0.),(.5,0.,0.),(0.,0.,.5),(-.5,.1,.2),(2.,0.,0.),(20.,0.,0.))
    angles=(0.,1.e-8,.01,math.pi/4,math.pi/2,math.pi)
    for ak in range(4):
        for bk in range(4):
            for center in centers:
                for angle in angles:
                    for radius in (0.,.05,.3):
                        a=primitive(ak,radius=radius,flags=0xe0);b=primitive(bk,center,radius,y=angle,x=.15 if angle else 0.,flags=0xe0)
                        pair(ak,bk,a,b,'all ordered GP dispatches, parallel axes, overlap, separated gaps')
                        pair(bk,ak,b,a,'reversed pair point ownership and normal selection')
    # Sphere-pair axis cannot use generic no-edge Z fallback. Exact neighbors
    # cover every ordered scalar addition, plus coincident and tiny centers.
    for pa,pb,extra in ((0.,0.,0.),(.125,.125,0.),(.01,.1,.2),(.1,.01,.2),(-.01,.1,0.),(.05,.05,-.01)):
        radius=.5;limit=((pb+pa)+extra)+radius+radius
        for bits in range(word(limit)-3,word(limit)+4):
            for axis in ((1.,0.,0.),(0.,1.,0.),(0.,0.,1.),(.6,.8,0.)):
                b=primitive(0,[value(bits)*v for v in axis],radius);pair(0,0,primitive(0,radius=radius),b,'sphere scalar padding and shape-fatness exact neighbors',f([pa,pb,extra,.999,.01]))
    for distance in (0.,1.e-12,1.e-8,value(0x34000000),.001):
        for radius in (0.,.1):pair(0,0,primitive(0,radius=radius),primitive(0,(distance,0.,0.),radius),'coincident/tiny sphere normalization and refinement threshold',degenerate=distance==0.)
    # Both triangles are corrected: A precedes B, with opposite reverse bits.
    for flags in range(256):
        tflags=((flags&1)<<4)|((flags&2)<<7)|((flags&0x1c)<<3)|((flags&0xe0)<<4)
        for kind in range(4):
            for center in ((0.,.1,0.),(.49,.1,-.49),(0.,-.1,0.)):
                a=primitive(kind,center,radius=.15);b=primitive(2,radius=.025,flags=tflags,cosines=(.01,.5,.999))
                pair(kind,2,a,b,'triangle B classification/sidedness/convexity/disabled vertices')
                pair(2,kind,b,a,'triangle A correction and sequential both-triangle fixes')
    for _ in range(8192):
        ak,bk=rng.randrange(4),rng.randrange(4);center=[rng.uniform(-1.5,1.5) for _ in range(3)]
        a=primitive(ak,[rng.uniform(-.25,.25) for _ in range(3)],rng.uniform(.001,.3),rng.uniform(-math.pi,math.pi),rng.uniform(-.6,.6),[rng.uniform(.05,.7) for _ in range(3)],rng.choice((0,0xe0,0x10,0x110,0xff0)),[rng.uniform(.01,.999) for _ in range(3)],bool(rng.randrange(2)))
        b=primitive(bk,center,rng.uniform(.001,.3),rng.uniform(-math.pi,math.pi),rng.uniform(-.6,.6),[rng.uniform(.05,.7) for _ in range(3)],rng.choice((0,0xe0,0x10,0x110,0xff0)),[rng.uniform(.01,.999) for _ in range(3)],bool(rng.randrange(2)))
        pair(ak,bk,a,b,'random native dispatch/SAT/feature/prism/fixup/padding',f([rng.uniform(0.,.15),rng.uniform(0.,.15),rng.uniform(0.,.15),rng.uniform(.8,.9999),rng.uniform(0.,.02)]))
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
    probe=PLUGIN/'Tests/Reference/primitive_pair_probe.rs';main=source/'primitive-pair-oracle.rs'
    main.write_text((source/'lib.rs').read_text()+probe.read_text().replace('//!','//'));reference=output/'primitive-pair-reference'
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():
        if digest(source/name)!=expected:raise AssertionError(f'Frozen reference module changed: {name}')
    snapshot=output/'native-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();native=PLUGIN/'Source/AtelierSkate/Private/Native'
    sources=('NativeMath.h','NativeMath.cpp','GeometryTypes.h','Geometry.h','Geometry.cpp','GeometrySweep.h','GeometrySweep.cpp','WorldGeometry.h','WorldGeometry.cpp','GeometryFeatures.h','GeometryFeatures.cpp','GeometryPrism.h','GeometryPrism.cpp','GeometryTriangleFixup.h','GeometryTriangleFixup.cpp','WorldPrimitiveContact.h','WorldPrimitiveContact.cpp','PrimitiveGeometry.h','GeometryPrimitivePair.h','GeometryPrimitivePair.cpp')
    for name in sources:shutil.copy2(native/name,snapshot/name)
    shutil.copy2(PLUGIN/'Tests/Native/primitive_pair_probe.cpp',snapshot/'primitive_pair_probe.cpp');cpp=output/'primitive-pair-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),
        *[str(snapshot/name) for name in ('NativeMath.cpp','Geometry.cpp','GeometrySweep.cpp','WorldGeometry.cpp','GeometryFeatures.cpp','GeometryPrism.cpp','GeometryTriangleFixup.cpp','WorldPrimitiveContact.cpp','GeometryPrimitivePair.cpp','primitive_pair_probe.cpp')],'-o',str(cpp)],check=True)
    provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,
        probe_sha256=digest(probe),reference_binary_sha256=digest(reference),cpp_binary_sha256=digest(cpp),
        native_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},
        rust_compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),cpp_compiler=subprocess.check_output(['clang++','--version'],text=True).strip())
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return cpp,reference

def coverage(data,cases):
    counts=Counter();kinds={f'{a}/{b}':Counter() for a in range(4) for b in range(4)}
    for case in cases:
        row=struct.unpack_from('<'+'I'*case['output_words'],data,case['first_output_word']*4)
        if row[0]!=case['index'] or OPERATIONS[row[1]]!=case['operation']:raise AssertionError('Pair frame identity changed')
        if case['operation']=='defaults':
            if list(row[2:])!=[0x3d4ccccd,0x3d4ccccd,0,0x3f7fbe77,0x3c23d70a]:raise AssertionError('Original pair constants changed')
            continue
        hit,n=row[2],row[6];key=f'{case["kind_a"]}/{case["kind_b"]}'
        counts['hits' if hit else 'misses']+=1;kinds[key]['hits' if hit else 'misses']+=1
        if hit:
            if not 1<=n<=16:raise AssertionError('Pair contact capacity changed')
            if any(row[7+n*6:]):raise AssertionError('Unused manifold slots not zero')
            counts[f'point_count_{n}']+=1
            if not case['degenerate'] and not all(math.isfinite(value(v)) for v in row[3:6]+row[7:7+n*6]):raise AssertionError(f'Nonfinite valid primitive pair: {case}')
        elif any(row[3:]):raise AssertionError('Absent manifold payload changed')
    for key,c in kinds.items():
        if not c['hits'] or not c['misses']:raise AssertionError(f'Uncovered native pair dispatch hits/misses: {key} {c}')
    if not counts['point_count_1'] or not counts['point_count_2'] or not any(counts[f'point_count_{n}'] for n in range(3,17)):raise AssertionError('Missing point/edge/face paths')
    return dict(counts),{key:dict(c) for key,c in kinds.items()}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json','provenance.json'):(output/name).unlink(missing_ok=True)
    inputs,cases=corpus();(output/'input.bin').write_bytes(inputs);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');cpp,reference=build_probes(output)
    expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(cpp)],input=inputs);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
    if len(expected)!=sum(c['output_words'] for c in cases)*4:raise AssertionError('Incomplete original pair query output')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));aligned=first//4*4
        case=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None)
        report=dict(passed=False,first_word=first//4,case=case,reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex())
        (output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    counts,kinds=coverage(expected,cases)
    report=dict(passed=True,cases=len(cases),exact_words=len(expected)//4,coverage=counts,dispatches=kinds,input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),
        comparison='All ordered pair manifolds and native self-collision constants exact; no tolerance; original numerical modules unchanged',
        indirect_coverage='GP packing, maximum features and specialized box SAT are compared through original public pair contacts; coincident sphere fixtures preserve exact original nonfinite bits')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
