#!/usr/bin/env python3
"""Exact static-world queries against unmodified frozen public BoardWorld APIs.

Run through atelier.safety. Evidence and compiler snapshots belong in the given
game build directory. PrimitiveBounds has no public direct oracle in this slice.
"""
import argparse
from collections import Counter
import copy
import hashlib
import io
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tarfile

from session_parity import PLUGIN, REFERENCE_REVISION, digest

OPERATIONS=('triangle_constructor','bounds','world')
IDENTITY=(1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.)


def bits(value):
    try:return struct.unpack('<I',struct.pack('<f',value))[0]
    except OverflowError:return 0xff800000 if value<0 else 0x7f800000


def value(word):return struct.unpack('<f',struct.pack('<I',word))[0]


def corpus():
    rng=random.Random(0x8277b720);records=[];cases=[]
    def add(op,words,label,**fields):
        records.append(struct.pack('<I',op)+struct.pack('<'+'I'*len(words),*words))
        cases.append(dict(case=len(cases),operation=OPERATIONS[op],label=label,**fields))
    def f(values):return [bits(v) for v in values]
    def triangle(vertices,tag=0,fatness=0.,flags=0,cosines=(1.,1.,1.),material=(.8,.6,.1)):
        return f(vertices)+[bits(fatness)]+f(cosines)+[flags]+f(material)+[tag]
    def points(vertices):return [value(v) for v in vertices[:9]]
    def bounds_of(entries):
        flat=sum((points(t) for t in entries),[])
        return [min(flat[axis::3]) for axis in range(3)]+[max(flat[axis::3]) for axis in range(3)]
    def mesh(start,end,bounds,index):
        return dict(start=start,end=end,forward=list(IDENTITY),inverse=list(IDENTITY),bounds=bounds,
                    group=(index%7)-3,rejection=rng.getrandbits(32),geometry=rng.getrandbits(32),pool=index%3)
    def metadata(triangles,partitions):
        meshes=[];start=0
        for index,count in enumerate(partitions):
            end=start+count;meshes.append(mesh(start,end,bounds_of(triangles[start:end]),index));start=end
        assert start==len(triangles)
        edges=[]
        for entry in triangles[:3]:
            vertices=points(entry);edge=vertices[:3]+vertices[3:6]
            edges.append(edge+[min(edge[a],edge[a+3]) for a in range(3)]+[max(edge[a],edge[a+3]) for a in range(3)])
        return dict(surfaces=[rng.getrandbits(16) for _ in triangles],meshes=meshes,edges=edges,island=rng.getrandbits(32))
    def query(start,end,radius=0.,bounds=None):return dict(start=list(start),end=list(end),radius=radius,bounds=bounds)
    def world(entries,meta,queries,label,enabled=True,**fields):
        words=[len(entries)]
        for entry in entries:words+=entry
        words+=[int(enabled),len(meta['surfaces'])]+meta['surfaces']+[len(meta['meshes'])]
        for m in meta['meshes']:
            words += [m['start'],m['end']]+f(m['forward'])+f(m['inverse'])+f(m['bounds'])
            words += [m['group']&0xffffffff,m['rejection'],m['geometry'],m['pool']]
        words += [len(meta['edges'])]
        for edge in meta['edges']:words+=f(edge)
        words += [meta['island'],len(queries)]
        for q in queries:words += f(q['start']+q['end']+[q['radius']])+[int(q['bounds'] is not None)]+f(q['bounds'] or [0.]*6)
        add(2,words,label,triangles=len(entries),meshes=len(meta['meshes']),queries=len(queries),
            metadata_enabled=enabled,**fields)

    seeds=([0.,0.,0.,0.,0.,2.,2.,0.,0.],[0.,0.,0.,2.,0.,0.,0.,0.,2.],
           [1.,2.,3.,-3.,4.,2.,2.,-1.,5.],[0.]*9,[0.,0.,0.,1.,0.,0.,2.,0.,0.],
           [0.,0.,0.,1.e-6,0.,0.,0.,1.e-6,0.])
    for vertices in seeds:
        for flags in (0,2,0x10,0x100,0xffffffff):
            for fatness in (0.,-0.,.05,-.05,float('inf')):
                add(0,triangle(vertices,0xabcdef01,fatness,flags,(-1.,.5,1.)), 'constructor/winding/dirty-flag/degenerate')
    for word in (0x7f800000,0xff800000,0x7fc12345,0xff812345):
        entry=triangle(seeds[0]);entry[rng.randrange(9)]=word;add(0,entry,'nonfinite vertex rejection')
    for _ in range(2048):
        scale=rng.choice((.001,.1,1.,100.,10000.))
        vertices=[rng.uniform(-4.,4.)*scale for _ in range(9)]
        add(0,triangle(vertices,rng.getrandbits(32),rng.uniform(-.1,.1)*scale,rng.getrandbits(32),
                       [rng.uniform(-1.,1.) for _ in range(3)],[rng.uniform(-1.,2.) for _ in range(3)]),'random cached triangle')

    boundary_points=([],[0.]*3,[-0.,-0.,-0.,0.,0.,0.],[-1.,-2.,-3.,1.,2.,3.],
                     [float('inf'),0.,0.],[float('nan'),1.,2.])
    for p in boundary_points:
        for padding in (0.,-0.,.1,-1.,float('inf')):
            add(1,[len(p)//3]+f(p+[padding,-1.,-1.,-1.,1.,1.,1.]),'bounds boundary')
    for _ in range(1024):
        p=[rng.uniform(-10000.,10000.) for _ in range(3*rng.randrange(1,12))]
        other=sorted((rng.uniform(-10000.,10000.),rng.uniform(-10000.,10000.)))
        add(1,[len(p)//3]+f(p+[rng.uniform(-10.,10.)]+[other[0]]*3+[other[1]]*3),'random bounds')

    empty=dict(surfaces=[],meshes=[],edges=[],island=0)
    simple_queries=[query([.5,1.,.5],[.5,-1.,.5],radius,bounds)
        for radius in (0.,-0.,.05,-.1,float('inf'),float('nan'))
        for bounds in (None,[-1.,-1.,-1.,1.,1.,1.],[1.,1.,1.,-1.,-1.,-1.])]
    world([],empty,simple_queries,'empty authored world')
    world([],empty,simple_queries,'empty legacy world',False)
    duplicate=[triangle(seeds[0],900+i,0.) for i in range(17)]
    tied=[query([.5,1.,.5],[.5,-1.,.5],0.,[-1.]*3+[3.]*3)]
    world(duplicate,metadata(duplicate,[1]*17),tied,'equal-hit authored source order',tie_tag=900)
    world(list(reversed(duplicate)),metadata(duplicate,[17]),tied,'reversed equal-hit authored source order',tie_tag=916)
    face=triangle([-2.,0.,-2.,-2.,0.,2.,2.,0.,-2.],7)
    margin_queries=[query([-1.,1.,-1.],[-1.,.000005,-1.],0.,[-1.,0.,-1.,-1.,1.,-1.]),
                    query([-1.,-.000005,-1.],[-1.,-1.,-1.],0.,[-1.,-1.,-1.,-1.,-.000005,-1.]),
                    query([-2.00002,1.,-1.],[-2.00002,-1.,-1.],0.,[-2.00002,-1.,-1.,-2.00002,1.,-1.])]
    world([face],metadata([face],[1]),margin_queries,'thin endpoint and barycentric broadphase margins',tie_tag=7)
    tiled=[]
    for i in range(1024):
        x=((i*37)%1024)*10.
        tiled.append(triangle([x-2.,0.,-2.,x-2.,0.,2.,x+2.,0.,-2.],i))
    tile_queries=[query([x,2.,-1.],[x,-2.,-1.],radius,[x-radius,-radius,-radius,x+radius,radius,radius])
                  for x in (-100.,-2.,0.,2.,8.,10.,155.,509.,10229.,10300.) for radius in (0.,.03,.5,31.,20000.)]
    world(tiled,metadata(tiled,[1]*1024),tile_queries,'deep source-shuffled tiled mesh hierarchy')
    for fatness in (0.,.005,.05,.5,-.005,float('inf')):
        entries=[triangle(seeds[0],5,fatness),triangle([v+10. if i%3==0 else v for i,v in enumerate(seeds[0])],7,fatness)]
        meta=metadata(entries,[1,1])
        world(entries,meta,simple_queries,'radius/maximum-fatness conservative bounds')
        world(entries,meta,simple_queries,'legacy unculled world',False)

    # Every validation diagnostic is triggered without repairing authored data.
    base=[triangle(seeds[0],1),triangle(seeds[1],2)];valid=metadata(base,[1,1])
    invalid=[]
    m=copy.deepcopy(valid);m['surfaces'].pop();invalid.append(('surface count',m))
    m=copy.deepcopy(valid);m['meshes'][0]['start']=1;invalid.append(('mesh partition start',m))
    m=copy.deepcopy(valid);m['meshes'][0]['end']=0;invalid.append(('mesh partition empty',m))
    m=copy.deepcopy(valid);m['meshes'][1]['end']=3;invalid.append(('mesh partition overrun',m))
    m=copy.deepcopy(valid);m['meshes'][0]['forward'][9]=1.;invalid.append(('forward nonidentity transform',m))
    m=copy.deepcopy(valid);m['meshes'][0]['inverse'][0]=float('nan');invalid.append(('inverse nonidentity transform',m))
    m=copy.deepcopy(valid);m['meshes'][0]['bounds'][0]=float('inf');invalid.append(('invalid mesh bounds',m))
    m=copy.deepcopy(valid);m['meshes'][0]['bounds'][3]=.5;invalid.append(('mesh bounds exclude geometry',m))
    m=copy.deepcopy(valid);m['meshes'].pop();invalid.append(('unassigned triangles',m))
    m=copy.deepcopy(valid);m['edges'][0][6]=3.;invalid.append(('invalid edge bounds',m))
    m=copy.deepcopy(valid);m['edges'][0][0]=float('inf');invalid.append(('invalid edge endpoint',m))
    for label,m in invalid:world(base,m,tied,'metadata rejection/'+label)

    for world_id in range(384):
        mesh_count=rng.choice((1,4,8,9,17,33))
        partitions=[rng.randrange(1,4) for _ in range(mesh_count)]
        entries=[]
        # Spatial order is deliberately independent of authored source order.
        centers=[(rng.uniform(-50.,50.),rng.uniform(-2.,2.),rng.uniform(-50.,50.)) for _ in partitions]
        if world_id%8==0:centers=[(0.,0.,0.)]*mesh_count
        for center,count in zip(centers,partitions):
            x,y,z=center
            for _ in range(count):
                size=rng.uniform(.01,5.)
                vertices=[x,y,z,x,y,z+size,x+size,y,z]
                if rng.randrange(2):vertices=vertices[:3]+vertices[6:9]+vertices[3:6]
                entries.append(triangle(vertices,rng.getrandbits(32),rng.choice((0.,.005,.05)),rng.getrandbits(32)))
        meta=metadata(entries,partitions);queries=[]
        for x,y,z in centers[:8]:
            start=[x+.001,y+5.,z+.001];end=[x+.001,y-5.,z+.001]
            queries.append(query(start,end,rng.choice((0.,.02,.5)),[x-1.,y-1.,z-1.,x+1.,y+1.,z+1.]))
        for _ in range(16):
            start=[rng.uniform(-60.,60.) for _ in range(3)];end=[rng.uniform(-60.,60.) for _ in range(3)]
            box=[min(start[i],end[i]) for i in range(3)]+[max(start[i],end[i]) for i in range(3)]
            queries.append(query(start,end,rng.choice((0.,.02,.5,2.)),rng.choice((None,box))))
        # Geometry loader defaults are identity, including signed zero aliases.
        if world_id%9==0:
            meta['meshes'][0]['forward'][1]=-0.;meta['meshes'][0]['inverse'][10]=-0.
        world(entries,meta,queries,'random authored mesh hierarchy',enabled=world_id%7!=0)
    return struct.pack('<I',len(records))+b''.join(records),cases


def build_probes(output):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip())
    relative=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-core/src').relative_to(root).as_posix()
    revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip()
    archive=subprocess.check_output(['git','archive',f'{revision}:{relative}'],cwd=root)
    source=output/'reference-source'
    if source.exists():shutil.rmtree(source)
    source.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:stream.extractall(source,filter='data')
    originals={p.relative_to(source).as_posix():digest(p) for p in sorted(source.rglob('*.rs'))}
    probe=PLUGIN/'Tests/Reference/world_geometry_probe.rs';main=source/'world-geometry-oracle.rs'
    main.write_text((source/'lib.rs').read_text()+probe.read_text().replace('//!','//'))
    reference=output/'world-geometry-reference'
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():
        if digest(source/name)!=expected:raise AssertionError(f'Frozen reference module changed: {name}')
    snapshot=output/'native-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir()
    native=PLUGIN/'Source/AtelierSkate/Private/Native'
    for name in ('NativeMath.h','NativeMath.cpp','Geometry.h','Geometry.cpp','GeometrySweep.h','GeometrySweep.cpp',
                 'GeometryTypes.h','WorldGeometry.h','WorldGeometry.cpp'):shutil.copy2(native/name,snapshot/name)
    shutil.copy2(PLUGIN/'Tests/Native/world_geometry_probe.cpp',snapshot/'world_geometry_probe.cpp')
    cpp=output/'world-geometry-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),
        *[str(snapshot/name) for name in ('NativeMath.cpp','Geometry.cpp','GeometrySweep.cpp','WorldGeometry.cpp','world_geometry_probe.cpp')],'-o',str(cpp)],check=True)
    provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),
        original_source_sha256=originals,probe_sha256=digest(probe),reference_binary_sha256=digest(reference),cpp_binary_sha256=digest(cpp),
        native_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},
        rust_compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),
        cpp_compiler=subprocess.check_output(['clang++','--version'],text=True).strip())
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    return cpp,reference


class Reader:
    def __init__(self,data):self.words=struct.unpack('<'+'I'*(len(data)//4),data);self.at=0
    def word(self):word=self.words[self.at];self.at+=1;return word
    def skip(self,count):self.at+=count
    def error(self):return ''.join(chr(self.word()) for _ in range(self.word()))
    def hit(self):
        error=self.error();found=self.word();tag=self.word();self.skip(10);return error,found,tag


def frames(data,cases):
    reader=Reader(data);result=[]
    for case in cases:
        index=reader.word();op=reader.word();size=reader.word();start=reader.at
        if index!=case['case'] or OPERATIONS[op]!=case['operation']:raise AssertionError('Invalid world output marker')
        if start+size>len(reader.words):raise AssertionError('Truncated world output')
        result.append((start,size));reader.skip(size)
    if reader.at!=len(reader.words):raise AssertionError('Trailing world output')
    return result


def coverage(data,cases,offsets):
    summary=Counter();errors=Counter()
    for case,(start,size) in zip(cases,offsets):
        reader=Reader(data[start*4:(start+size)*4])
        if case['operation']=='triangle_constructor':summary['constructor_accepted' if reader.word() else 'constructor_rejected']+=1
        elif case['operation']=='bounds':summary['bounds_finite' if reader.word() else 'bounds_rejected']+=1
        else:
            error=reader.error()
            if error:errors[error]+=1;continue
            summary['worlds']+=1
            if case['meshes']>8 and case['metadata_enabled']:summary['hierarchy_worlds']+=1
            count=reader.word();reader.skip(count*33);error=reader.error();has_metadata=reader.word()
            summary['authored_worlds' if has_metadata else 'legacy_worlds']+=1
            if has_metadata:
                reader.skip(reader.word());meshes=reader.word();reader.skip(meshes*36)
                edges=reader.word();reader.skip(edges*12);reader.word()
            queries=reader.word();summary['queries']+=queries
            for _ in range(queries):
                if reader.word():summary['finite_line_bounds']+=1
                reader.skip(6);ranges=reader.word();reader.skip(ranges*2)
                candidates=reader.word();indices=[reader.word() for _ in range(candidates)]
                if indices!=sorted(set(indices)):raise AssertionError('Oracle candidates lost authored order')
                summary['candidate_triangles']+=candidates
                if has_metadata and candidates<count:summary['culled_queries']+=1
                reader.error();meshes=reader.word();indices=[reader.word() for _ in range(meshes)]
                if indices!=sorted(set(indices)):raise AssertionError('Oracle mesh candidates lost authored order')
                for kind in ('thin','swept'):
                    error,found,tag=reader.hit();summary[kind+'_hits' if found else kind+'_misses']+=1
                    if error:summary['line_radius_errors']+=1
                    if 'tie_tag' in case and (not found or tag!=case['tie_tag']):raise AssertionError('Reference equal-hit selection changed')
            if reader.at!=len(reader.words):raise AssertionError('Coverage parser missed a world field')
    if len(errors)!=7 or not summary['hierarchy_worlds'] or not summary['culled_queries'] or not summary['thin_hits'] or not summary['swept_hits']:
        raise AssertionError('World validation/culling/hits were unexercised')
    return dict(summary),dict(errors)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json','provenance.json'):(output/name).unlink(missing_ok=True)
    inputs,cases=corpus();(output/'input.bin').write_bytes(inputs);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    cpp,reference=build_probes(output)
    expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(cpp)],input=inputs)
    (output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
    offsets=frames(expected,cases)
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)))
        index=next((i for i,(start,size) in enumerate(offsets) if (start-3)*4<=first<(start+size)*4),None)
        aligned=first//4*4
        report=dict(passed=False,first_byte=first,first_word=first//4,case=cases[index] if index is not None else None,
            reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,aligned-16):aligned+32].hex(),
            cpp_hex=actual[max(0,aligned-16):aligned+32].hex())
        (output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    counts,errors=coverage(expected,cases,offsets)
    report=dict(passed=True,cases=len(cases),groups=dict(Counter(c['label'] for c in cases)),coverage=counts,metadata_errors=errors,
        output_words=len(expected)//4,comparison='all authored cache/metadata, bounds, candidate order, hit payload and diagnostic words; exact bits',
        limitations=['PrimitiveBounds direct helper and primitive-contact integration await a public original oracle; this result covers static world line queries only'],
        inputs_sha256=hashlib.sha256(inputs).hexdigest(),outputs_sha256=hashlib.sha256(expected).hexdigest())
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
