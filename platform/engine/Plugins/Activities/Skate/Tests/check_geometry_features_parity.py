#!/usr/bin/env python3
"""Exact GP projection/axis/maximum-feature callbacks against frozen Rust.

Run through atelier.safety. Public original callbacks preserve and compare the
complete native output records, including opaque incoming scratch words.
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

from session_parity import PLUGIN, REFERENCE_REVISION, digest

OPERATIONS=('projection','axes','segment','capsule','triangle','box','edge_planes')
OUTPUT_WORDS=(None,73,16,160,144,144,144)


def bits(value):return struct.unpack('<I',struct.pack('<f',value))[0]
def value(word):return struct.unpack('<f',struct.pack('<I',word))[0]


def corpus():
    rng=random.Random(0x82acea30);records=[];cases=[];output_word=0
    def f(values):return [bits(v) for v in values]
    def opaque(count):return [rng.getrandbits(32) for _ in range(count)]
    def add(op,words,label,output=None,**fields):
        nonlocal output_word
        size=(OUTPUT_WORDS[op] if output is None else output)+2
        records.append(struct.pack('<I',op)+struct.pack('<'+'I'*len(words),*words))
        cases.append(dict(case=len(cases),operation=OPERATIONS[op],label=label,first_output_word=output_word,output_words=size,**fields))
        output_word+=size
    def unit(axis):
        length=sum(v*v for v in axis)**.5
        return [v/length for v in axis] if length else [0.,0.,1.]
    def gp(kind,center=(0.,0.,0.),axis=(0.,0.,1.),half=(1.,2.,3.),basis=None):
        words=[0]*48;words[:4]=f(list(center)+[1.]);words[32]=bits(.02)
        if kind==1:
            words[16:20]=f(list(axis)+[0.]);words[28]=bits(half[0]);words[35]=0x00010000;words[36]=2
        elif kind==2:
            points=(list(center)+[1.],[center[0]+2.,center[1],center[2],1.],[center[0],center[1]+2.,center[2],1.])
            words[:4]=f(points[0]);words[4:8]=f([0.,0.,1.,0.]);words[8:12]=f(points[1]);words[12:16]=f(points[2])
            for i,edge in enumerate(((0.,1.,0.,0.),(2**-.5,-2**-.5,0.,0.),(-1.,0.,0.,0.))):words[16+4*i:20+4*i]=f(edge)
            words[28:31]=f([2.,2*2**.5,2.]);words[35]=0x01030000;words[36]=3;words[37]=0xe0;words[38:41]=f([1.,1.,1.])
        elif kind==3:
            if basis is None:basis=((1.,0.,0.),(0.,1.,0.),(0.,0.,1.))
            for i,column in enumerate(basis):words[4+4*i:8+4*i]=words[16+4*i:20+4*i]=f(list(column)+[0.])
            words[28:31]=f(half);words[35]=0x03030000;words[36]=4
        else:words[36]=1
        return words
    def projection(kind,record,directions,label):
        count=len(directions);outputs=count+3;initial=opaque(outputs*12)
        add(0,[kind]+record+[count,outputs]+sum((f(d) for d in directions),[])+initial,label,
            output=outputs*24,directions=count,intervals=outputs,kind=kind,initial_intervals=initial)
    def axes(a,b,a_kind,b_kind,label):
        initial=opaque(64);add(1,a+b+initial+[a_kind,b_kind],label,initial_axes=initial)
    def segment(origin,end,label):
        initial=opaque(16);add(2,initial+f(origin)+f(end),label,initial_plane=initial[8:12])
    def maximum(op,record,direction,label,mode=0):
        initial=opaque(144)
        if op==3:
            scratch=opaque(16);add(op,record+f(direction)+initial+scratch,label,initial_header=initial[0],scratch_plane=scratch[8:12])
        elif op==4:add(op,record+[mode]+f(direction)+initial,label,initial_header=initial[0])
        else:
            incoming=opaque(4);add(op,record+[mode]+f(direction)+initial+incoming,label,incoming_plane=incoming)

    directions=([1.,0.,0.,0.],[-1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],
                [1.,1.,0.,0.],[1.,1.,1.,0.],[0.,0.,0.,0.],[-0.,0.,0.,1.])
    for kind in range(4):
        for center in ((0.,0.,0.),(-10.,20.,-30.),(1000.,-2000.,3000.)):
            for half in ((0.,0.,0.),(1.,2.,3.),(-1.,2.,-.5),(.0001,1000.,.3)):
                projection(kind,gp(kind,center,half=half),directions,'typed projection/zero/unequal extents')
    projection(3,gp(3),[],'empty projection batch')
    for _ in range(1024):
        kind=rng.randrange(4);center=[rng.uniform(-100.,100.) for _ in range(3)]
        # Rigid Y rotation is offset and non-axis-aligned, with unequal extents.
        angle=rng.uniform(-math.pi,math.pi);c=math.cos(angle);s=math.sin(angle)
        basis=((c,0.,s),(0.,1.,0.),(-s,0.,c))
        record=gp(kind,center,unit([rng.uniform(-1.,1.) for _ in range(3)]),[rng.uniform(.001,100.) for _ in range(3)],basis)
        projection(kind,record,[[rng.uniform(-100.,100.) for _ in range(4)] for _ in range(rng.randrange(1,9))],'random oriented GP projection')

    shapes=[gp(kind) for kind in range(4)]
    for a_kind,a in enumerate(shapes):
        for b_kind,b in enumerate(shapes):
            for offset in ((0.,0.,0.),(1.,2.,3.),(-10.,-20.,-30.),(1.e-8,0.,0.)):
                shifted=list(b);shifted[:4]=f(list(offset)+[1.]);axes(a,shifted,a_kind,b_kind,'typed shape pairs / fallback axes')
    for angle in (0.,1.e-8,1.e-5,.01,.03,.04,.5,1.,math.pi/2):
        for separation in ((0.,0.,0.),(1.,0.,0.),(0.,1.,0.),(0.,0.,1.)):
            axes(gp(1),gp(1,separation,(math.sin(angle),0.,math.cos(angle))),1,1,'parallel/cross/secondary capsule axes')
    for normals_a in range(4):
        for normals_b in range(4):
            for edges_a in range(4):
                for edges_b in range(4):
                    a=gp(3);b=gp(3,(1.,2.,3.),basis=((.6,0.,.8),(0.,1.,0.),(-.8,0.,.6)))
                    a[35]=normals_a<<24|edges_a<<16;b[35]=normals_b<<24|edges_b<<16
                    axes(a,b,3,3,'GP normal/edge header count combinations')
    for _ in range(2048):
        a_kind=rng.randrange(4);b_kind=rng.randrange(4)
        a=gp(a_kind,[rng.uniform(-10.,10.) for _ in range(3)],unit([rng.uniform(-1.,1.) for _ in range(3)]))
        angle=rng.uniform(-math.pi,math.pi);c=math.cos(angle);s=math.sin(angle)
        b=gp(b_kind,[rng.uniform(-10.,10.) for _ in range(3)],unit([rng.uniform(-1.,1.) for _ in range(3)]),basis=((c,0.,s),(0.,1.,0.),(-s,0.,c)))
        axes(a,b,a_kind,b_kind,'random primitive pair axes')

    lengths=(0.,-0.,1.e-8,1.e-5,value(0x34000000)**.5,1.e-3,1.,100.)
    for length in lengths:
        for start_w in (0.,1.,-0.,99.):
            for end_w in (0.,1.,-0.,-99.):segment([0.,0.,0.,start_w],[length,0.,0.,end_w],'segment threshold and fourth lanes')
    for _ in range(2048):segment([rng.uniform(-100.,100.) for _ in range(4)],[rng.uniform(-100.,100.) for _ in range(4)],'random segment geometry')

    boundary_words=(0,0x80000000,0x3d4ccccc,0x3d4ccccd,0x3d4cccce,0xbd4ccccc,0xbd4ccccd,0xbd4cccce,
                    0x3e4ccccc,0x3e4ccccd,0x3e4cccce,0xbe4ccccc,0xbe4ccccd,0xbe4cccce,
                    0x3f733332,0x3f733333,0x3f733334,0xbf733332,0xbf733333,0xbf733334,0x3f800000,0xbf800000)
    for op,kind in ((3,1),(4,2),(5,3)):
        for axis in range(3):
            for word in boundary_words:
                direction=[0.,0.,0.,0.];direction[axis]=value(word)
                for mode in (0,1,2,0xffffffff):maximum(op,gp(kind),direction,'feature threshold/full integer mode',mode)
        for direction in directions:
            for mode in (0,1):maximum(op,gp(kind),direction,'feature face/edge/point branches',mode)
        for _ in range(2048):
            center=[rng.uniform(-10.,10.) for _ in range(3)];axis=unit([rng.uniform(-1.,1.) for _ in range(3)])
            angle=rng.uniform(-math.pi,math.pi);c=math.cos(angle);s=math.sin(angle)
            record=gp(kind,center,axis,[rng.uniform(.001,4.) for _ in range(3)],((c,0.,s),(0.,1.,0.),(-s,0.,c)))
            direction=unit([rng.uniform(-1.,1.) for _ in range(3)])+[rng.choice((0.,1.,-.5))]
            maximum(op,record,direction,'random authored maximum features',rng.randrange(3))

    for count in (0,1,2,3,4,8,0xffffffff,0x80000000):
        for mode in (0,1,2,0xffffffff):
            for direction in directions:
                initial=opaque(144);initial[140]=count
                for i in range(min(count,8)):initial[8+16*i:12+16*i]=f([0.,0.,1.,0.])
                add(6,initial+[mode]+f(direction),'edge plane count/mode/zero threshold')
    for _ in range(1024):
        initial=opaque(144);initial[140]=rng.randrange(9)
        for i in range(initial[140]):initial[8+16*i:12+16*i]=f([rng.uniform(-2.,2.) for _ in range(4)])
        add(6,initial+[rng.randrange(3)]+f([rng.uniform(-2.,2.) for _ in range(4)]),'random edge planes')
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
    probe=PLUGIN/'Tests/Reference/geometry_features_probe.rs';main=source/'geometry-features-oracle.rs'
    main.write_text((source/'lib.rs').read_text()+probe.read_text().replace('//!','//'));reference=output/'geometry-features-reference'
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():
        if digest(source/name)!=expected:raise AssertionError(f'Frozen reference module changed: {name}')
    snapshot=output/'native-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();native=PLUGIN/'Source/AtelierSkate/Private/Native'
    for name in ('NativeMath.h','NativeMath.cpp','GeometryTypes.h','GeometryFeatures.h','GeometryFeatures.cpp'):shutil.copy2(native/name,snapshot/name)
    shutil.copy2(PLUGIN/'Tests/Native/geometry_features_probe.cpp',snapshot/'geometry_features_probe.cpp');cpp=output/'geometry-features-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),
        *[str(snapshot/name) for name in ('NativeMath.cpp','GeometryFeatures.cpp','geometry_features_probe.cpp')],'-o',str(cpp)],check=True)
    provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,
        probe_sha256=digest(probe),reference_binary_sha256=digest(reference),cpp_binary_sha256=digest(cpp),
        native_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},
        rust_compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),cpp_compiler=subprocess.check_output(['clang++','--version'],text=True).strip())
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return cpp,reference


def coverage(data,cases):
    counts=Counter();features={name:Counter() for name in ('capsule','triangle','box')}
    for case in cases:
        at=case['first_output_word']+2;row=struct.unpack_from('<'+'I'*(case['output_words']-2),data,at*4)
        op=case['operation']
        if op=='projection':
            n=case['intervals'];single=row[:n*12];batch=row[n*12:]
            counts['single_batch_differences']+=single!=batch
            for record in (single,batch):
                for i in range(n):
                    if list(record[i*12+8:i*12+12])!=case['initial_intervals'][i*12+8:i*12+12]:raise AssertionError('Projection tail not retained')
                if list(record[case['directions']*12:])!=case['initial_intervals'][case['directions']*12:]:raise AssertionError('Extra projection intervals not retained')
        elif op=='axes':
            count=row[0];counts[f'axes_count_{count}']+=1
            if count<16 and list(row[1+count*4:5+count*4])!=case['initial_axes'][count*4:count*4+4]:counts['speculative_axis_stores']+=1
        elif op=='segment':
            if list(row[8:12])!=case['initial_plane']:raise AssertionError('Segment plane overwritten')
        elif op in features:
            count=row[140];features[op][str(count)]+=1
            if op=='triangle' and count!=3 and row[0]!=case['initial_header']:raise AssertionError('Triangle nonface header overwritten')
            if op=='capsule' and list(row[144+8:144+12])!=case['scratch_plane']:raise AssertionError('Capsule scratch plane overwritten')
            if op=='box' and count==1 and list(row[12:16])!=case['incoming_plane']:raise AssertionError('Box incoming plane not copied')
    if not counts['single_batch_differences'] or not counts['speculative_axis_stores'] or not counts['axes_count_0']:
        raise AssertionError('Projection ordering or rejected-axis mutation was unexercised')
    for name,required in (('capsule',('0','1')),('triangle',('0','1','3')),('box',('0','1','4'))):
        if not all(features[name][key] for key in required):raise AssertionError(f'{name} feature branch unexercised')
    return dict(counts),{name:dict(counts) for name,counts in features.items()}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json','provenance.json'):(output/name).unlink(missing_ok=True)
    inputs,cases=corpus();(output/'input.bin').write_bytes(inputs);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    cpp,reference=build_probes(output);expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(cpp)],input=inputs)
    (output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
    required=sum(c['output_words'] for c in cases)*4
    if len(expected)!=required:raise AssertionError('Incomplete original GP output')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)))
        case=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None);aligned=first//4*4
        report=dict(passed=False,first_word=first//4,case=case,reference_length=len(expected),cpp_length=len(actual),
            reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex())
        (output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    counts,features=coverage(expected,cases)
    report=dict(passed=True,cases=len(cases),operations=dict(Counter(c['operation'] for c in cases)),coverage=counts,maximum_features=features,
        output_words=required//4,comparison='all projection/axis/feature/scratch output bits; opaque words and partial writes retained',
        inputs_sha256=hashlib.sha256(inputs).hexdigest(),outputs_sha256=hashlib.sha256(expected).hexdigest())
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
