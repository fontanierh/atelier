#!/usr/bin/env python3
"""Exact live skeleton volumes, assembly pair ordering and completed-contact reports.

Compile only through the render lock/memory guard. Whole original Rust producer
modules retain their source bytes; a forwarding adapter exposes the private
collector. Its transport context supplies completed rows and current snapshots.
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
OPERATIONS=('colliders','assembly','reports')
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def value(w):return struct.unpack('<f',struct.pack('<I',w))[0]
def f(v):return list(map(bits,v))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def corpus():
    rng=random.Random(0x8276556c);records=[];cases=[]
    def add(op,payload,label,**meta):
        cases.append(dict(index=len(cases),operation=OPERATIONS[op],label=label,**meta));records.append(struct.pack('<'+'I'*(len(payload)+1),op,*payload))
    def numbers(n,scale=1.):return [rng.uniform(-scale,scale) for _ in range(n)]
    def basis(y=0.,x=0.):
        cy,sy,cx,sx=math.cos(y),math.sin(y),math.cos(x),math.sin(x);return (cy,sx*sy,-cx*sy,0.,cx,sx,sy,-sx*cy,cx*cy)
    def matrix(phase=0.,position=(0.,.5,0.)):
        b=basis(phase);out=[]
        for i in range(3):out+=list(b[i*3:i*3+3])+[rng.choice((0.,.25))]
        return f(out+list(position)+[rng.choice((0.,1.,.25))])
    def matrices(n):return [w for i in range(n) for w in matrix(i*.01,(i*.01,.5,0.))]
    def definition(seed):return [w for n in range(24) for w in f([.12+.001*n,.2,.4+.005*n])]+[w for n in range(24) for w in [bits(1.),bits(.5),1,0,n%3,bits(1.),1]]+f([200.,.15,.2,.7,.9,.6])+[seed%3,bits(5.)]+[0]
    def simulation():return f([1/60,60.])+[30]+f([.001,0.,-9.81,0.])
    def settings(seed):return [seed%2]+f([.5,.3,.4])+[1]*24+f([float(n%3) for n in range(24)]+[.1])
    def body(seed):
        state=(1,2,4,6,12)[seed%5];inverse=0. if state==1 else (.2,1.,2.)[seed%3]
        raw=[state]+f([0.,0.,0.,1.,*basis(seed*.01),*basis(.0),*numbers(3),*numbers(12,3.),.2])+[seed%60]+f([1.,2.,3.,inverse,1.,100.,20.,.1,.2]);assert len(raw)==49;return raw
    def primitive(kind,center=(0.,0.,0.),angle=0.):
        axes=basis(angle,.13)
        if kind==0:return [0]+f([*center,.2])
        if kind==1:return [1]+f([*center,*axes[6:9],.3,.15])
        if kind==2:return [2]+f([-.4,0.,-.4,0.,0.,.4,.4,0.,-.4,.02,.5,.5,.5])+[0xe0]+f([*axes,*center])
        return [3]+f([*center,*axes,.3,.2,.4,.02])
    def volume(id,kind,center=(0.,0.,0.),angle=0.):return [id]+primitive(kind,center,angle)+f([1.,.2,-.3,.5,.3,.4])
    def collider(seed):
        commands=[]
        for part in (0,1,3,7,23,24,25):commands.append([0,part,1,(0,4)[(seed+part)%2],5,*f([.5,.3,.4])])
        for part in (1,3,7,23,24,25):commands.append([3,part]+matrix(seed*.07+part*.01,tuple(numbers(3))))
        commands.append([4,1]+body(seed))
        commands.append([0,3,1,12,5,*f([.5,.3,.4])]);commands.append([0,3,1,0,5,*f([.5,.3,.4])])
        commands.append([1,1,4,*f([.125,.5,0.,.1,.2,.3])]);commands.append([1,1,3,*f([.125,.5,0.,.1,.2,.3])]);commands.append([1,1,0,*f([.125,.5,0.,.1,.2,.3])])
        commands.append([2,1,1,*f([.1,.2,*basis(.3),.01,.02,.03])]);commands.append([2,1,0]);commands.append([0,1,0,0,5,*f([.5,.3,.4])])
        return definition(seed)+matrices(24)+matrix(seed*.1)+simulation()+settings(seed)+[seed%2,len(commands)]+[w for c in commands for w in c],dict(commands=[c[0] for c in commands])
    for seed in range(96):
        data,meta=collider(seed);add(0,data,'actual part poses, root/extras, static body retention, world group4 and explicit unsupported errors',**meta)
    def assembly(seed,group,assembly_group,part_group,invalid=0):
        groups=[part_group]*26
        if invalid==1:groups[seed%26]=21
        culling=[int(a==b or (seed+a+b)%3!=0) for a in range(26) for b in range(26)]
        board=[volume(4,3,(0.,0.,0.),seed*.01),volume(0,0,(0.,.3,0.))]
        rider=[volume(8+p,p%4,(.05*p,.05*(p%2),.01*p),seed*.023) for p in (1,3,7,23)]
        initial=[0,0xffffffff]+f([0.,0.,0.,0.,0.,0.,0.,1.,0.,.3,.5,.2])+[0x87654321]
        payload=settings(seed)+[seed%2,assembly_group]+groups+culling+[group,len(board)]+[w for v in board for w in v]+[len(rider)]+[w for v in rider for w in v]+[1]+initial
        return payload,dict(initial=1,group=group,assembly_group=assembly_group,part_group=part_group,invalid=bool(invalid or group>=21 or assembly_group>=21))
    for group in range(21):
        for assembly_group in range(21):
            data,meta=assembly(group+assembly_group,group,assembly_group,(group+assembly_group)%21);add(1,data,'complete original21x21 assembly and per-part table, directed self pairs',**meta)
    for seed in range(128):
        group=(4,5,6,7,8,11,17,18,20)[seed%9];ag=(5,6,7)[seed%3];pg=(5,17,18,20)[seed%4]
        if seed%16==0:group=21
        elif seed%16==1:ag=21
        data,meta=assembly(seed,group,ag,pg,invalid=int(seed%16==2));add(1,data,'biped/skater/ragdoll filters and pre-mutation invalid group errors',**meta)
    def row(seed,a,b):
        w=f(numbers(64,.3));w[11]=8 if seed%7 else 0;w[20:24]=f([(.0,-.1,.1,1.,2.)[seed%5],.2,-.3,.1]);w[31]=a;w[43]=b;w[35]=bits((.25,1.,2.)[seed%3]);w[39]=bits((.25,1.,2.)[(seed+1)%3]);w[55]=0x43211234;return w
    for seed in range(256):
        attached=34 if seed%3 else 30;local=30;nr=(0,1,8,16,17,40,80)[seed%7]
        rows=[]
        ids=((9,0xffffffff),(0xffffffff,9),(8+23,8+30),(8+30,8+23),(9,4),(4,9),(9,8+7),(8+7,9),(8+24,0xffffffff),(8+60,9),(9,8+60),(4,0xffffffff))
        for n in range(nr):
            a,b=ids[(seed+n)%len(ids)];rows+=row(seed+n,a,b)
        add(2,[w for n in range(7) for w in body(seed+n)]+[attached]+[w for n in range(attached) for w in body(seed+n+7)]+[local,(4,6,7)[seed%3],(5,8,11)[seed%3],bits((0.,30.,60.,120.)[seed%4]),nr]+rows,'original in-place spy arithmetic, owner suppression, missing proxy defaults, side tags and16 report cap',rows=nr)
    # Saturate with eligible external contacts to pin the capacity and order.
    for side in (False,True):
        for frequency in (0.,30.,60.,120.):
            rows=[]
            for n in range(40):
                a,b=(9+n%23,0xffffffff) if side else (0xffffffff,9+n%23);w=row(n+1,a,b);w[11]=8;w[20]=bits(1.);rows+=w
            add(2,[w for n in range(7) for w in body(n)]+[30]+[w for n in range(30) for w in body(n+7)]+[30,4,5,bits(frequency),40]+rows,'report buffer saturation and original side loop order',rows=40)
    return struct.pack('<I',len(records))+b''.join(records),cases
def build_probes(output):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip());relative=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-core/src').relative_to(root).as_posix()
    revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip();archive=subprocess.check_output(['git','archive',f'{revision}:{relative}'],cwd=root);source=output/'reference-source'
    if source.exists():shutil.rmtree(source)
    source.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:stream.extractall(source,filter='data')
    originals={p.relative_to(source).as_posix():digest(p) for p in sorted(source.rglob('*.rs'))}
    shared=PLUGIN/'Tests/Reference/skeleton_body_probe.rs';collision=PLUGIN/'Tests/Reference/skeleton_collision_probe.rs';probe=PLUGIN/'Tests/Reference/skeleton_contact_provider_probe.rs';prefix=shared.read_text().split('fn main(){',1)[0]+collision.read_text().split('fn main(){',1)[0]
    (source/'provider_oracle').mkdir()
    host=source/'host-source';host.mkdir()
    host_relative=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-host/src/physics').relative_to(root).as_posix()
    host_hashes={}
    for name,original in (('skeleton_colliders.rs','skeleton_colliders.rs'),('assembly_contacts.rs','solve/assembly_contacts.rs'),('skeleton_feedback.rs','skeleton_feedback.rs')):
        raw=subprocess.check_output(['git','show',f'{revision}:{host_relative}/{original}'],cwd=root);(host/name).write_bytes(raw);host_hashes[name]=hashlib.sha256(raw).hexdigest()
    feedback=(host/'skeleton_feedback.rs').read_bytes();adapter=b'\npub(super) fn migration_collect(physics: &GamePhysics, skater: &SkaterRuntime) -> Vec<SkeletonContactReport> { collect(physics, skater) }\n';(host/'skeleton_feedback_forward.rs').write_bytes(feedback+adapter)
    main=source/'skeleton-contact-provider-oracle.rs';main.write_text((source/'lib.rs').read_text()+prefix+probe.read_text());reference=output/'skeleton-contact-provider-reference'
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():
        if digest(source/name)!=expected:raise AssertionError(f'Frozen reference module changed: {name}')
    snapshot=output/'core-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();core=PLUGIN/'Source/AtelierSkate/Private/Simulation'
    units=('SimulationMath','RigidBody','BodyMass','AggregateMass','DeckGeometry','DriveFrames','ConstraintFrames','ConstraintSolver','JointBuild','DriveBuild','JointRecords',
        'TruckDriveFrames','DrivePreparation','HookDrive','BoardAssembly','ContactBuild','ContactGeneration','BoardPose','ForceQueue','CollisionBody','BoardContactFeedback','BoardStep','BoardRuntime',
        'SkeletonPoseFrames','SkeletonAnimationRecord','SkeletonPhysicalRecord','SkeletonBodyDefinition','SkeletonBody','BoardGroundAngle','SkeletonCollisionMode','SkeletonCollisionFeedback','SkeletonPoseErrors','Geometry','GeometrySweep','WorldGeometry','GeometryFeatures','GeometryPrism','GeometryTriangleFixup','WorldPrimitiveContact','GeometryPrimitivePair','ContactRetention','WorldContactProducer','SkeletonColliders','AssemblyContacts','SkeletonContactReports')
    for name in [f'{unit}.{ext}' for unit in units for ext in ('h','cpp')]+['GeometryTypes.h','BoardTypes.h','ContactRetention.h','SkeletonTargets.h','SkeletonDriveFrames.h','PrimitiveGeometry.h']:shutil.copy2(core/name,snapshot/name)
    cpp_shared=PLUGIN/'Tests/Simulation/skeleton_body_probe.cpp';cpp_collision=PLUGIN/'Tests/Simulation/skeleton_collision_probe.cpp';cpp_probe=PLUGIN/'Tests/Simulation/skeleton_contact_provider_probe.cpp';prefix=cpp_shared.read_text().split('int main()',1)[0]+cpp_collision.read_text().split('int main()',1)[0]
    combined=snapshot/'skeleton_contact_provider_probe.cpp';combined.write_text('#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wunused-function"\n'+prefix+'\n#pragma clang diagnostic pop\n'+cpp_probe.read_text())
    cpp=output/'skeleton-contact-provider-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{unit}.cpp') for unit in units],str(combined),'-o',str(cpp)],check=True)
    provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,
        probe_sha256={p.name:digest(p) for p in (shared,collision,probe,cpp_shared,cpp_collision,cpp_probe)},host_source_sha256=host_hashes,collector_forward_adapter_sha256=hashlib.sha256(adapter).hexdigest(),reference_binary_sha256=digest(reference),cpp_binary_sha256=digest(cpp),simulation_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},
        rust_compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),cpp_compiler=subprocess.check_output(['clang++','--version'],text=True).strip())
    for name,expected in host_hashes.items():
        if digest(host/name)!=expected:raise AssertionError(f'Original host provider changed: {name}')
    if (host/'skeleton_feedback_forward.rs').read_bytes()!=feedback+adapter:raise AssertionError('Original collector prefix changed')
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return cpp,reference

def decode(data,cases):
    w=struct.unpack('<'+'I'*(len(data)//4),data);at=0;rows=[]
    for c in cases:
        index,op,n=w[at:at+3]
        if index!=c['index'] or OPERATIONS[op]!=c['operation']:raise AssertionError('Provider frame identity changed')
        rows.append(w[at+3:at+3+n]);c.update(first_output_word=at,output_words=n+3);at+=n+3
    if at!=len(w):raise AssertionError('Trailing provider output')
    return rows
def coverage(rows,cases):
    counts=Counter()
    def volumes(row,at):
        n=row[at];at+=1;out=[]
        for _ in range(n):
            id,kind=row[at:at+2];nwords=(4,8,29,16)[kind];counts[f'primitive_{kind}']+=1;out.append(id);at+=8+nwords
        return at,out
    def result(row,at):
        ok=row[at];at+=1
        if ok:return volumes(row,at)
        n=row[at];text=bytes(row[at+1:at+1+n]).decode();counts['errors']+=1
        if 'volume group' in text:counts['volume_group_errors']+=1
        elif 'equipped hat' in text:counts['hat_errors']+=1
        elif 'Unsupported' in text:counts['unsupported_errors']+=1
        elif 'Cylinder' in text:counts['cylinder_errors']+=1
        else:raise AssertionError(text)
        return at+n+1,None
    for row,c in zip(rows,cases):
        counts[c['operation']]+=1
        if c['operation']=='colliders':
            n=row[0];at=1
            if n!=len(c['commands']):raise AssertionError('Collider command count changed')
            for cmd in c['commands']:
                if row[at]!=cmd:raise AssertionError('Collider command order changed')
                at+=1;at,enabled=result(row,at);at,world=result(row,at)
                if enabled is not None:
                    if world is None or any(id not in enabled for id in world):raise AssertionError('World filtering added volume')
                    if world!=[id for id in enabled if id in world]:raise AssertionError('World filter reordered volumes')
                    counts['filtered_volumes']+=len(enabled)-len(world);counts['enabled_volumes']+=len(enabled);counts['world_volumes']+=len(world)
                at+=2443+913
            if at!=len(row):raise AssertionError('Collider framing changed')
        elif c['operation']=='assembly':
            ok=row[0];at=1
            if not ok:n=row[at];error=bytes(row[at+1:at+1+n]).decode();at+=1+n;counts['group_errors']+=1;assert error=='Skater collision group is outside the original21x21 table'
            if bool(ok)==c['invalid']:raise AssertionError('Assembly group domain changed')
            n=row[at];at+=1
            if n<c['initial'] or (not ok and n!=c['initial']):raise AssertionError('Assembly append mutated existing rows on rejection')
            counts['pair_contacts']+=n-c['initial'];counts['self_contacts']+=sum(row[at+i*15]>=8 and row[at+i*15+1]>=8 for i in range(c['initial'],n));counts['board_rider_contacts']+=sum(row[at+i*15]<7 and row[at+i*15+1]>=8 for i in range(c['initial'],n))
            if any(row[at+i*15+14] for i in range(c['initial'],n)):raise AssertionError('Stock pair tags changed')
            if at+n*15!=len(row):raise AssertionError('Assembly contact framing changed')
        else:
            n=row[0]
            if n>16 or len(row)!=1+n*30:raise AssertionError('Skeleton report capacity/framing changed')
            counts['reports_produced']+=n;counts['report_full_buffers']+=n==16
            for i in range(n):
                r=row[1+i*30:1+(i+1)*30]
                if r[0]>=24 or r[11]!=0:raise AssertionError('Report owner/entity changed')
                counts['side_a' if r[25] else 'side_b']+=1;counts['world_reports']+=r[10]==0;counts['proxy_reports']+=r[10]!=0
    for key in ('filtered_volumes','pair_contacts','self_contacts','board_rider_contacts','group_errors','volume_group_errors','hat_errors','unsupported_errors','cylinder_errors','reports_produced','report_full_buffers','side_a','side_b','world_reports','proxy_reports'):
        if not counts[key]:raise AssertionError(f'Uncovered skeleton provider branch: {key}')
    if any(not counts[f'primitive_{kind}'] for kind in (0,1,3)):raise AssertionError('Missing real skeleton primitive shapes')
    return dict(counts)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json','provenance.json'):(output/name).unlink(missing_ok=True)
    inputs,cases=corpus();(output/'input.bin').write_bytes(inputs);cpp,reference=build_probes(output);expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(cpp)],input=inputs);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual);rows=decode(expected,cases);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));aligned=first//4*4;case=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None)
        report=dict(passed=False,first_word=first//4,case=case,reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex());(output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    report=dict(passed=True,cases=len(cases),coverage=coverage(rows,cases),exact_words=len(expected)//4,input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),comparison='All live volumes, ordered pair seeds and16-entry completed-contact reports exact; no tolerance; all original numerical modules unchanged',limitations='World contacts/solver/animation timing are validated separately; complete original host collector runs against explicit snapshot/row transports, not a full host GamePhysics.')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
