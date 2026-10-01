#!/usr/bin/env python3
"""Complete unchanged Climbing ledge queries over real authored BoardWorld.

Canonical world numerical modules execute unchanged, with complete mesh/pool/
metadata transport. This proves ledge admission only; global Climbing scheduling
and dropped-board state are separate. Root alone compiles/runs the probes.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tarfile
import check_animation_trees_parity as frozen
import check_climbing_core_parity as core
import check_world_geometry_parity as world
from session_parity import PLUGIN, REFERENCE_REVISION, digest
CODE=core.CODE
UNITS=('NativeMath','Geometry','GeometrySweep','WorldGeometry','ClimbingMath','ClimbingLedge')
def triangle(a,b,c,tag):return core.floats([*a,*b,*c,0,1,1,1])+[0]+core.floats([.8,.6,.1])+[tag]
def quad(a,b,c,d,tag):return [triangle(a,b,c,tag),triangle(b,d,c,tag+1)]
def block(height=2,width=2,depth=3,slope=0,wall_tilt=0,obstacle=0):
    z=1.5;back=z+depth;cap=lambda x,z:[x,height+slope*x,z]
    entries=quad([-width,0,z],[-width,height,z+wall_tilt],[width,0,z],[width,height,z+wall_tilt],100)
    entries+=quad(cap(-width,z),cap(-width,back),cap(width,z),cap(width,back),200)
    if obstacle==1:entries+=quad([-2,height+.8,1.5],[-2,height+.8,5],[2,height+.8,1.5],[2,height+.8,5],300)
    if obstacle==2:entries+=quad([-.6,.8,.9],[-.6,.8,1.45],[.6,.8,.9],[.6,.8,1.45],400)
    return entries
def metadata(entries):
    if not entries:return dict(surfaces=[],meshes=[],edges=[],island=0)
    points=[world.value(w)for entry in entries for w in entry[:9]]
    bounds=[min(points[a::3])for a in range(3)]+[max(points[a::3])for a in range(3)]
    return dict(surfaces=[1]*len(entries),meshes=[dict(start=0,end=len(entries),forward=list(world.IDENTITY),inverse=list(world.IDENTITY),bounds=bounds,group=-1,rejection=0,geometry=17,pool=0)],edges=[],island=0)
def transport(entries,meta,enabled=True):
    words=[len(entries),*[w for t in entries for w in t],int(enabled),len(meta['surfaces']),*meta['surfaces'],len(meta['meshes'])]
    for m in meta['meshes']:words += [m['start'],m['end'],*core.floats(m['forward']+m['inverse']+m['bounds']),m['group']&0xffffffff,m['rejection'],m['geometry'],m['pool']]
    words += [len(meta['edges'])]
    for edge in meta['edges']:words += core.floats(edge)
    return words+[meta['island']]
def ledge(height=2):return [0,height+.025,1.555,0,height+.015,2.12,0,0,1,-.3,height+.005,1.58,.3,height+.005,1.58,0,1,0,0,1,0]
def corpus():
    rng=random.Random(0x4c454447);cases=[]
    def add(entries,label,enabled=True,invalid=None):
        meta=metadata(entries)
        if invalid:invalid(meta)
        queries=[]
        def query(op,args,label):queries.append(dict(op=op,args=args,label=label))
        for x in(-1.731,-.317,0,.317,1.731):
            for y in(-.137,0,.731):
                for op in(0,1):query(op,core.floats([x,y,0,0,0,1]),'ground/air wall admission and all source clearance probes')
        for facing in((0,0,0),(0,1,0),(0,0,-1),(.317,.731,1),(.999,0,.137),(float('nan'),0,1)):
            query(1,core.floats([0,0,0,*facing]),'normalization/facing/invalid-query miss')
        for shift in(-.731,0,.317,1.731):
            l=ledge();l[0]+=shift;l[3]+=shift;query(2,core.floats(l),'explicit typed ledge clearance input with real world queries')
        query(3,core.floats([0,3,2.12,0,1,2.12,0]),'actual cap hit observer')
        query(3,core.floats([0,1,0,0,1,3,0]),'actual front hit observer')
        query(3,core.floats([float('nan'),1,0,0,1,3,0]),'source invalid query diagnostic')
        cases.append(dict(index=len(cases),label=label,world=transport(entries,meta,enabled),queries=queries,metadata=enabled))
    add([], 'empty authored world');add(block(),'legacy metadata intentionally missing',False)
    add(block(),'full broad top and vertical face')
    for height in(1.0,1.24999988,1.25,1.25000012,1.6,1.89999986,1.9,1.9000001,2,2.74999976,2.75,2.75000024,3):add(block(height=height),'height gate '+str(height))
    for width in(.12,.29999998,.3,.30000004,.317,.731,2):add(block(width=width),'both palm/top width '+str(width))
    for depth in(.1,.317,.36999997,.37,.37000003,.62,.87,3):add(block(depth=depth),'landing platform depth '+str(depth))
    for slope in(-.4,-.21,-.137,-.0317,0,.0317,.137,.21,.4):add(block(slope=slope),'independent top normals/palm height '+str(slope))
    for tilt in(-1,-.731,-.317,0,.317,.731,1):add(block(wall_tilt=tilt),'wall normal '+str(tilt))
    add(block(obstacle=1),'live body/head clearance rejection');add(block(obstacle=2),'live outside torso clearance rejection')
    add(block(),'metadata surface count error',invalid=lambda m:m['surfaces'].pop())
    add(block(),'metadata nonfinite mesh bounds error',invalid=lambda m:m['meshes'][0]['bounds'].__setitem__(0,float('nan')))
    for n in range(24):add(block(height=rng.uniform(1.5,2.6),width=rng.uniform(.5,2),depth=rng.uniform(1.1,4),slope=rng.uniform(-.1,.1)), 'generated valid authored ledge '+str(n))
    return cases
def encode(cases):return core.word(len(cases))+b''.join(b''.join(core.word(w)for w in c['world']+[len(c['queries'])]+[w for q in c['queries']for w in [q['op'],*q['args']]])for c in cases)
class Reader:
    def __init__(self,raw):self.words=struct.unpack('<'+'I'*(len(raw)//4),raw);self.at=0
    def word(self):v=self.words[self.at];self.at+=1;return v
    def take(self,n):v=self.words[self.at:self.at+n];self.at+=n;assert len(v)==n;return v
    def error(self):return ''.join(chr(w)for w in self.take(self.word()))
def coverage(raw,cases):
    r=Reader(raw);assert r.word()==len(cases);counts=Counter();found=Counter();clear=Counter();hits=Counter();errors=Counter();ledges=set();legacy=False;failed_build=0
    for c in cases:
        assert r.word()==c['index'];end=r.word()+r.at;error=r.error();failed_build+=bool(error);assert r.word()==len(c['queries'])
        for q in c['queries']:
            op=r.word();assert op==q['op'];counts[op]+=1
            if op in(0,1):
                yes=r.word();found[(op,yes)]+=1
                if yes:ledges.add(r.take(21));assert r.word()==1,'found source ledge must revalidate clear'
                if not c['metadata']:assert not yes;legacy=True
            elif op==2:clear[r.word()]+=1
            else:
                error=r.error();errors[error]+=1;yes=r.word();hits[yes]+=1;r.take(11)
        assert r.at==end,c['label']
    assert r.at==len(r.words)
    assert found[(0,1)]>5 and found[(1,1)]>20 and found[(0,0)]>100 and found[(1,0)]>100
    assert clear[0]>50 and clear[1]>10 and len(ledges)>15 and legacy and failed_build==2
    assert hits[0]>50 and hits[1]>50 and sum(n for e,n in errors.items()if e)>len(cases)
    return dict(operations=dict(counts),find={str(k):v for k,v in found.items()},clear=dict(clear),actual_swept_hits=dict(hits),source_query_errors=dict(errors),distinct_real_ledges=len(ledges),invalid_metadata_constructors=failed_build,legacy_missing_metadata_is_intentional_miss=legacy)
def prepare(output,cases):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip());relative=(PLUGIN/'ThirdParty/skate-runtime').relative_to(root).as_posix();archive=subprocess.check_output(['git','archive',f'{REFERENCE_REVISION}:{relative}'],cwd=root)
    original=output/'reference-source';snapshot=output/'native-source'
    for path in(original,snapshot):
        if path.exists():shutil.rmtree(path)
        path.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive))as stream:stream.extractall(original,filter='data')
    originals={p.relative_to(original).as_posix():digest(p)for p in sorted(original.rglob('*.rs'))};crate=original/'climbing-world';(crate/'src/climbing').mkdir(parents=True)
    (crate/'Cargo.toml').write_text('[package]\nname="climbing-world-reference"\nversion="0.1.0"\nedition="2024"\n[workspace]\n[dependencies]\nskate-core={path="../crates/skate-core"}\nbevy={version="=0.19.1",default-features=false,features=["std"]}\n')
    shutil.copy2(original/'atelier-host/Cargo.lock',crate/'Cargo.lock');shutil.copy2(original/'crates/skate-host/src/physics/climbing/ledge.rs',crate/'src/climbing/ledge.rs')
    cpp=(PLUGIN/'Tests/Native/world_geometry_probe.cpp').read_text();cpp_prefix=cpp[:cpp.index('int main()')]
    rust=(PLUGIN/'Tests/Reference/world_geometry_probe.rs').read_text();rust_prefix=rust[:rust.index('struct Query')].replace('//!','//')
    (crate/'src/main.rs').write_text((PLUGIN/'Tests/Reference/climbing_world_probe.rs').read_text().replace('// GENERATED_WORLD_HELPERS','use skate_core::{math,physics};\n'+rust_prefix))
    headers=('NativeMath.h','Geometry.h','GeometrySweep.h','GeometryTypes.h','WorldGeometry.h','ClimbingMath.h','ClimbingTypes.h','ClimbingLedge.h')
    for p in [CODE/h for h in headers]+[CODE/(u+'.cpp')for u in UNITS]:shutil.copy2(p,snapshot/p.name)
    (snapshot/'climbing_world_probe.cpp').write_text((PLUGIN/'Tests/Native/climbing_world_probe.cpp').read_text().replace('// GENERATED_WORLD_HELPERS',cpp_prefix))
    (output/'input.bin').write_bytes(encode(cases));(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    report=dict(reference_revision=REFERENCE_REVISION,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,complete_ledge_module_sha256=digest(crate/'src/climbing/ledge.rs'),immutable_native_sources={p.name:digest(p)for p in sorted(snapshot.iterdir())},native_world_transport_prefix_sha256=hashlib.sha256(cpp_prefix.encode()).hexdigest(),original_world_transport_prefix_sha256=hashlib.sha256(rust_prefix.encode()).hexdigest(),probe_sha256=digest(crate/'src/main.rs'),input_sha256=digest(output/'input.bin'),cases=len(cases),queries=sum(len(c['queries'])for c in cases),scope='Complete original ledge.rs plus canonical unchanged BoardWorld execute. Test adapters supply authored triangle/mesh/pool/metadata inputs; no completed line-hit values are supplied. Original query diagnostics are observed independently; source .ok()?? intentionally converts those errors to ledge misses. This is a real world leaf proof; no physical/player/global manager is substituted.')
    (output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');return original,crate,snapshot,report
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);p.add_argument('--preflight',action='store_true');a=p.parse_args();output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    cases=corpus();original,crate,snapshot,report=prepare(output,cases)
    if a.preflight:print(json.dumps(dict(preflight='PASS',cases=len(cases),queries=report['queries'],input_bytes=len(encode(cases)),input_sha256=report['input_sha256'])));return
    subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(crate/'Cargo.toml'),'--target-dir',str(a.target_dir.resolve()),'--bin','climbing-world-reference'],check=True);reference=output/'climbing-world-reference';shutil.copy2(a.target_dir.resolve()/'release/climbing-world-reference',reference)
    candidate=output/'climbing-world-native';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'climbing_world_probe.cpp'),'-o',str(candidate)],check=True)
    for relative,expected in report['original_source_sha256'].items():assert digest(original/relative)==expected
    raw=(output/'input.bin').read_bytes();values=[]
    for binary,label in((reference,'reference'),(candidate,'native')):
        run=subprocess.run([str(binary)],input=raw,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True);(output/(label+'.bin')).write_bytes(run.stdout);(output/(label+'.stderr')).write_bytes(run.stderr);values.append(run.stdout)
    if values[0]!=values[1]:
        offset=next((i for i,(x,y)in enumerate(zip(*values))if x!=y),min(map(len,values)));(output/'first-divergence.json').write_text(json.dumps(dict(byte_offset=offset,reference_bytes=len(values[0]),native_bytes=len(values[1])),indent=2)+'\n');raise AssertionError('Climbing world first mismatch at '+str(offset))
    proof=coverage(values[0],cases);result=dict(result='PASS',histories=len(cases),queries=report['queries'],exact_bytes=len(values[0]),sha256=hashlib.sha256(values[0]).hexdigest(),coverage=proof);(output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
