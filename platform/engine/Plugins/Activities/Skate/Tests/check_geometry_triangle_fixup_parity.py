#!/usr/bin/env python3
"""Exact triangle adjacency classification, acceptance, normal bending and pair reprojection."""
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
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def word(value):return struct.unpack('<I',struct.pack('<f',value))[0]
def value(bits):return struct.unpack('<f',struct.pack('<I',bits))[0]
def f(values):return [word(v) for v in values]
def corpus():
    rng=random.Random(0x82ad3130);records=[];cases=[];output_words=0
    edges=[[0.,1.,0.],[2**-.5,-2**-.5,0.],[-1.,0.,0.]]
    def feature(flags=0,cosines=(.5,.5,.5),angle=0.):
        c=math.cos(angle);s=math.sin(angle)
        rotated=[[c*x-s*y,s*x+c*y,z] for x,y,z in edges]
        return f([0.,0.,1.])+f([v for e in rotated for v in e])+[flags]+f(cosines)
    def add(op,t,normal,label,reverse=False,obj=False,bend=.95,epsilon=0.,n=1):
        nonlocal output_words
        payload=[op]+t+f(normal);size=3 if op==0 else 102
        extra={}
        if op:
            pairs=f([rng.uniform(-10.,10.) for _ in range(n*6)])+[rng.getrandbits(32) for _ in range((16-n)*6)]
            payload+=[int(reverse),word(bend),word(epsilon),int(obj),n]+pairs
            extra=dict(initial_normal=f(normal),initial_pairs=pairs,count=n,flags=t[12],reverse=reverse,is_object=obj)
        cases.append(dict(index=len(cases),operation='fixup' if op else 'classify',label=label,first_output_word=output_words,output_words=size,**extra))
        records.append(struct.pack('<'+'I'*len(payload),*payload));output_words+=size
    threshold=(0x3d4ccccb,0x3d4ccccc,0x3d4ccccd,0x3d4cccce,0x3d4ccccf)
    for axis in range(3):
        for bits in threshold:
            for sign in (-1.,1.):
                for other in (-1.,0.,1.):
                    direction=[other,other,other];direction[axis]=sign*value(bits);add(0,feature(),direction,'classification compare threshold/equality')
    for _ in range(2048):add(0,feature(angle=rng.uniform(-math.pi,math.pi)),[rng.uniform(-1.,1.) for _ in range(3)],'random in-plane classification')
    normals=[[0.,0.,1.],[0.,0.,-1.],[1.,0.,0.],[-1.,0.,0.],[0.,1.,0.],[0.,-1.,0.],[0.,0.,0.]]
    for az in (0.,math.pi/4,math.pi/2,math.pi,3*math.pi/2):
        normals.append([.8*math.cos(az),.8*math.sin(az),.6])
    normals.extend(([.8,-.4,.2],[-.8,.4,.2],[.4,.8,-.2]))
    for one in range(2):
        for cos in range(2):
            for convex in range(8):
                for disabled in range(8):
                    flags=(one<<4)|(cos<<8)|(convex<<5)|(disabled<<9)
                    for normal in normals:
                        for reverse in (False,True):
                            for obj in (False,True):
                                add(1,feature(flags),normal,'all one-sided/cosine/convex/disabled flags',reverse,obj,n=rng.choice((0,1,2,4,16)))
    for normal_z in (0x3f7ff629,0x3f7ff62a,0x3f7ff62b,0x3f7ff62c,0x3f7ff62d,0,0x80000000):
        for sign in (-1.,1.):
            for flags in (0,0x10,0x100,0x110,0x1f0,0xff0):
                add(1,feature(flags),[.05,.02,sign*value(normal_z)],'face tolerance exact neighbors',n=16)
    cosines=(0x3a83126e,0x3a83126f,0x3a831270,0x3f7851eb,0x3f7851ec,0x3f7851ed,0x3f7fffe9,0x3f7fffea,0x3f7fffeb,0x3f800000,0x3f800001,0,0xbf800000)
    for cosine in cosines:
        for flags in (0x110,0x130,0x150,0x190,0x530,0x950,0x390,0x510):
            for normal in ([.8,-.4,.2],[.8,-.4,.9],[-.8,.4,.6],[.4,.8,-.2]):
                for reverse in (False,True):
                    for obj in (False,True):
                        add(1,feature(flags,[value(cosine)]*3),normal,'cosine recovery/bending/near-flat boundaries',reverse,obj,bend=.95,epsilon=value(0x3727c5ac),n=16)
    for _ in range(4096):
        angle=rng.uniform(-math.pi,math.pi);normal=[rng.uniform(-1.,1.) for _ in range(3)];length=math.sqrt(sum(v*v for v in normal));normal=[v/length for v in normal]
        flags=rng.randrange(2)<<4|rng.randrange(2)<<8|rng.randrange(8)<<5|rng.randrange(8)<<9
        add(1,feature(flags,[rng.uniform(-1.,1.) for _ in range(3)],angle),normal,'random rotated triangle adjacency',bool(rng.randrange(2)),bool(rng.randrange(2)),rng.uniform(0.,1.),rng.uniform(0.,.1),rng.randrange(17))
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
    probe=PLUGIN/'Tests/Reference/geometry_triangle_fixup_probe.rs';main=source/'geometry-triangle-fixup-oracle.rs'
    main.write_text((source/'lib.rs').read_text()+probe.read_text().replace('//!','//'));reference=output/'geometry-triangle-fixup-reference'
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():
        if digest(source/name)!=expected:raise AssertionError(f'Frozen reference module changed: {name}')
    snapshot=output/'simulation-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();simulation=PLUGIN/'Source/AtelierSkate/Private/Simulation'
    sources=('SimulationMath.h','SimulationMath.cpp','GeometryTypes.h','GeometryTriangleFixup.h','GeometryTriangleFixup.cpp')
    for name in sources:shutil.copy2(simulation/name,snapshot/name)
    shutil.copy2(PLUGIN/'Tests/Simulation/geometry_triangle_fixup_probe.cpp',snapshot/'geometry_triangle_fixup_probe.cpp');cpp=output/'geometry-triangle-fixup-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),
        *[str(snapshot/name) for name in ('SimulationMath.cpp','GeometryTriangleFixup.cpp','geometry_triangle_fixup_probe.cpp')],'-o',str(cpp)],check=True)
    provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,
        probe_sha256=digest(probe),reference_binary_sha256=digest(reference),cpp_binary_sha256=digest(cpp),
        simulation_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},
        rust_compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),cpp_compiler=subprocess.check_output(['clang++','--version'],text=True).strip())
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return cpp,reference

def coverage(data,cases):
    counts=Counter();regions=Counter()
    for case in cases:
        row=struct.unpack_from('<'+'I'*case['output_words'],data,case['first_output_word']*4)
        if case['operation']=='classify':regions[str(row[2])]+=1;continue
        counts['accepted' if row[2] else 'rejected']+=1
        counts['normal_bends']+=list(row[3:6])!=case['initial_normal']
        n=case['count'];pairs=row[6:]
        if list(pairs[n*6:])!=case['initial_pairs'][n*6:]:raise AssertionError('Inactive pair slots overwritten')
        counts['pair_reprojections']+=list(pairs[:n*6])!=case['initial_pairs'][:n*6]
        if list(row[3:6])!=case['initial_normal'] and case['flags']&0xe00:counts['disabled_vertex_bends']+=1
    if len(regions)!=7:raise AssertionError('Not all seven triangle regions exercised')
    for key in ('accepted','rejected','normal_bends','pair_reprojections','disabled_vertex_bends'):
        if not counts[key]:raise AssertionError(f'Unexercised fixup branch: {key}')
    return dict(counts),dict(regions)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json','provenance.json'):(output/name).unlink(missing_ok=True)
    inputs,cases=corpus();(output/'input.bin').write_bytes(inputs);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    cpp,reference=build_probes(output);expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(cpp)],input=inputs)
    (output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
    if len(expected)!=sum(c['output_words'] for c in cases)*4:raise AssertionError('Incomplete original triangle fixup output')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));aligned=first//4*4
        case=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None)
        report=dict(passed=False,first_word=first//4,case=case,reference_length=len(expected),cpp_length=len(actual),
            reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex())
        (output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    counts,regions=coverage(expected,cases)
    report=dict(passed=True,cases=len(cases),operations=dict(Counter(c['operation'] for c in cases)),coverage=counts,regions=regions,
        exact_words=len(expected)//4,output_sha256=hashlib.sha256(expected).hexdigest(),input_sha256=hashlib.sha256(inputs).hexdigest(),
        comparison='All words exact; no tolerance or NaN canonicalization; original numerical modules unchanged')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
