#!/usr/bin/env python3
"""Exact remote COM geometry, proxy registration and contact production.

Run through the render lock/memory guard. The complete original network.rs is
embedded byte-for-byte with forwarding adapters. The remote contact loop is an
exact source slice from original solve.rs, calling unchanged assembly_contacts.
Wire records and fingerprint identity are explicit boundary transports.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
from reference_build import build_probe

PLUGIN=Path(__file__).resolve().parents[1]
REFERENCE_REVISION='46513a6'
OPERATIONS=('bounds','schema','registration','remote_contacts')
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def value(w):return struct.unpack('<f',struct.pack('<I',w))[0]
def f(v):return list(map(bits,v))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def corpus():
    rng=random.Random(0x46513a6);records=[];cases=[]
    def add(op,payload,label,**meta):cases.append(dict(index=len(cases),operation=OPERATIONS[op],label=label,**meta));records.append(struct.pack('<'+'I'*(len(payload)+1),op,*payload))
    def numbers(n,scale=1.):return [rng.uniform(-scale,scale) for _ in range(n)]
    def basis(y=0.,x=0.):
        c,s,cx,sx=math.cos(y),math.sin(y),math.cos(x),math.sin(x);return (c,sx*s,-cx*s,0.,cx,sx,s,-sx*c,cx*c)
    def quaternion(seed,scale=1.):
        axis=numbers(3);norm=math.sqrt(sum(x*x for x in axis));angle=seed*.073;s=math.sin(angle/2)/norm
        return [v*s*scale for v in axis]+[math.cos(angle/2)*scale]
    def body(seed,position=None):
        state=(1,2,4,6,12)[seed%5];inverse=.0 if state==1 else(.2,1.,2.)[seed%3]
        raw=[state]+f(quaternion(seed,(.999,1.,1.001)[seed%3])+list(basis(seed*.02))+list(basis(-seed*.01))+list(position if position is not None else numbers(3,.5))+numbers(12,5.)+[.2])+[seed%60]+f([1.,2.,3.,inverse,1.,100.,20.,.1,.2]);assert len(raw)==49;return raw
    def definition(seed):return [w for i in range(24) for w in f([.12+.002*i,.2,.4+.003*i])]+[w for i in range(24) for w in [bits(1.+i*.01),bits(.5+i*.03),1,0,i%3,bits(1.),1]]+f([200.,.15,.2,.7,.9,.6])+[seed%3,bits(5.)]+[0]
    def primitive(kind,center=(0.,0.,0.),phase=0.,scale=1.):
        if kind==0:return [0]+f([*center,.2*scale])
        if kind==1:return [1]+f([*center,*basis(phase)[6:9],.3*scale,.15*scale])
        if kind==2:return [2]+f([-.4*scale,0.,-.4*scale,0.,0.,.4*scale,.4*scale,0.,-.4*scale,.02*scale,.5,.6,.7])+[0xe0]+f([*basis(phase,.1),*center])
        return [3]+f([*center,*basis(phase,.1),.3*scale,.2*scale,.4*scale,.02*scale])
    def volume(owner,kind,center=(0.,0.,0.),phase=0.,scale=1.):return [owner]+primitive(kind,center,phase,scale)+f([1.,.2,-.3,.5,.3,.4])
    def volumes(v):return [len(v)]+[w for p in v for w in p]
    def wide(w):return [w&0xffffffff,(w>>32)&0xffffffff]
    def collision():return [0,0xffffffff]+f([0.,0.,0.,0.,0.,0.,0.,1.,0.,.3,.5,.2])+[0x87654321]
    def context(seed,zero_positions=False):
        board=[volume(i,i%4,(.05*i,.1,0.),seed*.031) for i in range(7)];rider=[volume(8+i,i%4,(.025*i,.1,0.),seed*.033) for i in range(26)]
        raw=definition(seed)+[w for i in range(33) for w in body(seed+i,(0.,0.,0.) if zero_positions else None)]+[w for i in range(7) for w in f([i*.1+1.,i*.2+1.,i*.3+1.,.3+i*.04,float(i%2),100.+i,20.+i,.1+i*.01,.2+i*.01])]+[(0,4,12)[seed%3]]+volumes(board)+volumes(rider)+wide(0x123456789abcdef0+seed)
        return raw,board,rider
    def wire(seed,enabled,near=True,specific=None):
        raw=f([*numbers(3,30.),*quaternion(seed)])+wide(enabled)+[33]
        for i in range(33):
            position=list(specific) if i==0 and specific is not None else numbers(3,.6) if near else [100.+i,100.,100.]
            if specific is not None and i:position=[100.+i,100.,100.]
            raw+=f(position+quaternion(seed+i,(.98,1.,1.02)[(seed+i)%3])+numbers(6,5.))
        return raw
    for kind in range(4):
        for scale in (.001,.1,1.,10.,100.):
            for _ in range(64):add(0,primitive(kind,tuple(numbers(3,100.)),rng.uniform(-3.,3.),scale),'conservative sphere/capsule/rotated-box/triangle radii',kind=kind)
    for seed in range(96):
        ctx,_,_=context(seed);add(1,ctx,'all33 COM binding transforms, duplicate normalizations, reconstructed triangle topology and fingerprint transport')
    for seed in range(96):
        ctx,_,_=context(seed);enabled=(1<<33)-1
        initial=[2]+body(seed+100)+body(seed+101)+volumes([volume(8+30,seed%4,(.1,.1,0.))]) if seed%3==0 else [0,0]
        commands=[[0]+wire(seed,enabled,False)+f([.1]),[0]+wire(seed+1,enabled)+f([(.0,.015625,-.03125)[seed%3]]),[2,1]+collision(),
            [0]+wire(seed+2,enabled|(1<<63))+f([.02]),[2,0],[0]+wire(seed+3,(1<<0)|(1<<6)|(1<<7)|(1<<30)|(1<<31)|(1<<32))+f([.05]),[2,0],
            [1],[0]+wire(seed+4,0)+f([.01]),[0]+wire(seed+5,1<<63)+f([.01])]
        add(2,ctx+initial+[len(commands)]+[w for c in commands for w in c],'streamed distant rejection, state/cache copying, ragdoll1..23, proxy base chaining and actual contacts',commands=[c[0] for c in commands],initial_bodies=2 if seed%3==0 else 0,target_count=(0,4,12)[seed%3])
    for x in (value(bits(8.)-1),8.,value(bits(8.)+1),-value(bits(8.)-1),-8.,-value(bits(8.)+1)):
        ctx,_,_=context(0,True);commands=[[0]+wire(0,1,specific=(x,0.,0.))+f([0.]),[2,0]]
        add(2,ctx+[0,0,len(commands)]+[w for c in commands for w in c],'strict nearby distance squared64 and one-ULP neighbors',commands=[c[0] for c in commands],initial_bodies=0,target_count=0,nearby=abs(x)<8.)
    for seed in range(512):
        board=[volume(4,seed%4,(0.,0.,0.),seed*.03),volume(0,(seed+1)%4,(.3,.1,0.))];rider=[volume(8+1,(seed+2)%4,(-.3,.1,0.))];remote=[volume(8+30+i,(seed+i)%4,(rng.uniform(-1.,1.),rng.uniform(-.4,.4),rng.uniform(-1.,1.)),seed*.015) for i in range(seed%5)]
        add(3,volumes(board)+volumes(rider)+volumes(remote)+[1]+collision(),'ordered board then rider remote narrow phase, retained initial rows and unculled external owners')
    # Inclusive broad-phase boundary (.2 + .2 + .05)^2; narrow phase padding
    # admits the equality and adjacent finite inputs, so ordering stays visible.
    radius=value(bits(value(bits(.2+.2))+.05))
    for w in (bits(radius)-1,bits(radius),bits(radius)+1):
        for kind in range(4):
            add(3,volumes([volume(0,0)])+volumes([volume(9,0)])+volumes([volume(8+30,kind,(value(w),0.,0.))])+[0],'inclusive remote sphere bound threshold neighbors',distance_word=w,kind=kind)
    return struct.pack('<I',len(records))+b''.join(records),cases

def original(root,revision,relative):return subprocess.check_output(['git','show',f'{revision}:{relative}'],cwd=root)
def build(output,target_dir):
    simulation=PLUGIN/'Source/AtelierSkate/Private/Simulation';snapshot=output/'simulation-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir()
    units=('SimulationMath','RigidBody','BodyMass','AggregateMass','DeckGeometry','DriveFrames','ConstraintFrames','ConstraintSolver','JointBuild','DriveBuild','JointRecords','TruckDriveFrames','DrivePreparation','HookDrive','BoardAssembly','ContactBuild','ContactGeneration','BoardPose','ForceQueue','CollisionBody','BoardContactFeedback','BoardStep','BoardRuntime','SkeletonPoseFrames','SkeletonAnimationRecord','SkeletonPhysicalRecord','SkeletonBodyDefinition','SkeletonBody','BoardGroundAngle','SkeletonCollisionMode','SkeletonCollisionFeedback','SkeletonPoseErrors','Geometry','GeometrySweep','WorldGeometry','GeometryFeatures','GeometryPrism','GeometryTriangleFixup','WorldPrimitiveContact','GeometryPrimitivePair','ContactRetention','WorldContactProducer','SkeletonColliders','AssemblyContacts','SkeletonContactReports','NetworkProxies')
    for name in [f'{n}.{e}' for n in units for e in ('h','cpp')]+['GeometryTypes.h','BoardTypes.h','SkeletonTargets.h','SkeletonDriveFrames.h','PrimitiveGeometry.h']:shutil.copy2(simulation/name,snapshot/name)
    cpp_prefixes=[PLUGIN/f'Tests/Simulation/skeleton_{n}_probe.cpp' for n in ('body','collision','contact_provider')];cpp_probe=PLUGIN/'Tests/Simulation/network_proxies_probe.cpp';combined=snapshot/cpp_probe.name
    combined.write_text('#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wunused-function"\n'+''.join(p.read_text().split('int main()',1)[0] for p in cpp_prefixes)+'\n#pragma clang diagnostic pop\n'+cpp_probe.read_text());cpp=output/'network-proxies-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{n}.cpp') for n in units],str(combined),'-o',str(cpp)],check=True)
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip());revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip();relative=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-host/src/physics').relative_to(root).as_posix()
    network=original(root,revision,relative+'/network.rs');solve=original(root,revision,relative+'/solve.rs');assembly=original(root,revision,relative+'/solve/assembly_contacts.rs')
    loop=solve[solve.index(b'    let before_remote = contacts.len();'):solve.index(b'    let dt = physics.settings.step.simulation.time_step;')]
    adapter=b'\npub fn migration_schema(p: &GamePhysics, s: &SkaterRuntime, fingerprint: u64) -> Result<Schema,String> { let mut schema=Schema::new(p,s)?; schema.fingerprint=fingerprint; Ok(schema) }\npub fn migration_entries(s: &Schema) -> Vec<(usize,BoardWorldVolume)> { s.volumes.clone() }\n'
    remote=(b'pub mod solve { use super::*;\npub fn remote(physics: &mut GamePhysics, skater: &SkaterRuntime, mut contacts: &mut Vec<BoardCollision>) { let board_volumes=physics.settings.volumes.clone(); let skeleton_volumes=skater.skeleton.volumes.clone();\n'+loop+b'}\n'
        b'pub fn explicit(board: &[BoardWorldVolume], rider: &[BoardWorldVolume], remote: &[BoardWorldVolume], mut contacts: &mut Vec<BoardCollision>) -> usize { struct Physics {network_proxies: network::Proxies,network_contacts:usize,contact_count:usize} let mut physics=Physics{network_proxies:network::Proxies{bodies:Vec::new(),volumes:remote.to_vec()},network_contacts:0,contact_count:0}; let board_volumes=board.to_vec(); let skeleton_volumes=rider.to_vec();\n'+loop+b'physics.network_contacts } }\npub fn remote(p:&mut GamePhysics,s:&SkaterRuntime,c:&mut Vec<BoardCollision>){solve::remote(p,s,c)}\npub fn remote_explicit(b:&[BoardWorldVolume],r:&[BoardWorldVolume],p:&[BoardWorldVolume],c:&mut Vec<BoardCollision>)->usize{solve::explicit(b,r,p,c)}\n')
    rust_prefixes=[PLUGIN/f'Tests/Reference/skeleton_{n}_probe.rs' for n in ('body','collision','contact_provider')];rust_probe=PLUGIN/'Tests/Reference/network_proxies_probe.rs'
    prefix=''.join(p.read_text().split('fn main(){',1)[0] for p in rust_prefixes[:2]).replace('use crate::{','use skate_core::{').replace('use crate::physics::','use skate_core::physics::').replace('skeleton_root::inverse_rigid,','')
    provider=rust_prefixes[2].read_text();prefix+='\nuse skate_core::physics::{board_step::{CollisionBody,BoardCollision},board_world::BoardWorldVolume,contact::RetailContactInput,contact_solver::RetailContactJacobian,drive_frames::RetailAffineTransform};\nuse skate_core::physics::world_contact::{ContactPrimitive,transform_triangle_volume};\n'+provider[provider.index('impl ProbeInput {'):provider.index('fn main(){')].replace('crate::physics::','skate_core::physics::')
    text=rust_probe.read_bytes();needle=b' #[path="../network-source/network_forward.rs"]pub mod network;';assert text.count(needle)==1;text=text.replace(needle,b' pub mod network {\n'+network+adapter+b'}')
    text=text.replace(b' #[path="../network-source/assembly_contacts.rs"]pub mod assembly_contacts;',b' #[path="assembly_contacts.rs"]pub mod assembly_contacts;')
    text=text.replace(b' include!("../network-source/remote_loop.rs");',remote)
    if text.count(network)!=1 or text.count(loop)!=2:raise AssertionError('Original producer or remote loop was modified while forwarding')
    generated=output/'network-proxies-combined.rs';generated.write_bytes(prefix.encode()+text)
    reference=build_probe(output,'network-proxies-reference',generated,target_dir,bevy=True,extra_sources={'atelier-host/src/proxy_oracle/assembly_contacts.rs':'crates/skate-host/src/physics/solve/assembly_contacts.rs'})
    report=dict(simulation_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},probe_sha256={p.name:digest(p) for p in (*cpp_prefixes,cpp_probe,*rust_prefixes,rust_probe)},original_network_sha256=hashlib.sha256(network).hexdigest(),original_solve_sha256=hashlib.sha256(solve).hexdigest(),original_assembly_sha256=hashlib.sha256(assembly).hexdigest(),verbatim_remote_loop_sha256=hashlib.sha256(loop).hexdigest(),network_forward_adapter_sha256=hashlib.sha256(adapter).hexdigest(),cpp_binary_sha256=digest(cpp))
    (output/'simulation-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return cpp,reference

def decode(data,cases):
    words=struct.unpack('<'+'I'*(len(data)//4),data);at=0;rows=[]
    for case in cases:
        index,op,n=words[at:at+3]
        if index!=case['index'] or OPERATIONS[op]!=case['operation']:raise AssertionError('Proxy stream identity changed')
        rows.append(words[at+3:at+3+n]);case.update(first_output_word=at,output_words=n+3);at+=n+3
    if at!=len(words):raise AssertionError('Trailing proxy output')
    return rows

def coverage(rows,cases):
    counts=Counter()
    def volumes(row,at):
        n=row[at];at+=1;ids=[]
        for _ in range(n):
            owner,kind=row[at:at+2];ids.append(owner);counts[f'primitive_{kind}']+=1;at+=8+(4,8,29,16)[kind]
        return at,ids
    def proxies(row,at):
        n=row[at];at+=1;states=row[at:at+n*49];at+=n*49;at,ids=volumes(row,at);return at,n,ids,states
    for row,case in zip(rows,cases):
        op=case['operation'];counts[op]+=1
        if op=='bounds':
            if len(row)!=4:raise AssertionError('Primitive bound shape changed')
        elif op in ('schema','registration'):
            n=row[2];at=3
            for index in range(n):
                source=row[at];at+=1;at,ids=volumes(row,at)
                if source!=index or len(ids)!=1:raise AssertionError('Stock schema source ordering changed')
            if op=='registration':
                at,before,old_ids,old_states=proxies(row,at);n=row[at];at+=1
                if n!=len(case['commands']):raise AssertionError('Proxy command count changed')
                for cmd in case['commands']:
                    if row[at]!=cmd:raise AssertionError('Proxy command order changed')
                    at+=1
                    if cmd==2:
                        added,total=row[at:at+2];at+=2;counts['produced_remote_rows']+=added
                        if added>total:raise AssertionError('Remote contact append counter exceeds rows')
                        at+=total*15
                    at,after,ids,states=proxies(row,at)
                    if cmd==0:
                        if after==before:counts['rejected_distant_frames']+=1
                        else:
                            if after-before!=33:raise AssertionError('Wire/local zip did not publish all33 bodies')
                            counts['registered_frames']+=1
                            if any(states[i*49]!=4 for i in range(before,after)):raise AssertionError('Proxy activation differs from state4')
                            if any(states[i*49+32:i*49+38]!=(0,)*6 for i in range(before,after)):raise AssertionError('Proxy force/torque was not zeroed')
                            if states[:len(old_states)]!=old_states:raise AssertionError('New registration replaced retained proxies')
                            if ids[:len(old_ids)]!=old_ids:raise AssertionError('New registration reordered retained volume owners')
                            if any(owner<8+26+case['target_count'] for owner in ids[len(old_ids):]):raise AssertionError('Remote reaction owner overlaps local skeleton/targets')
                    elif cmd==1:
                        if after or ids:raise AssertionError('Explicit proxy reset did not clear registration')
                    elif after!=before or states!=old_states or ids!=old_ids:raise AssertionError('Remote contact query rewrote proxy ownership')
                    if 'nearby' in case and cmd==0 and bool(after-before)!=case['nearby']:raise AssertionError('Strict nearby threshold changed')
                    before,old_ids,old_states=after,ids,states
            # Definition is26x(6shape+kind+hat flag+14hat+2x21mass+2inv)
            # plus24x7bone and49 normalized animation masses.
            if at+33*49+1933!=len(row):raise AssertionError('Local owner output framing changed')
        else:
            added,n=row[:2];counts['produced_remote_rows']+=added
            if len(row)!=2+n*15 or added>n:raise AssertionError('Remote contact row framing changed')
    for key in ('registered_frames','rejected_distant_frames','produced_remote_rows'):
        if not counts[key]:raise AssertionError(f'Uncovered network producer branch: {key}')
    if any(not counts[f'primitive_{kind}'] for kind in range(4)):raise AssertionError('Missing remote primitive transform')
    return dict(counts)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json','simulation-provenance.json'):(output/name).unlink(missing_ok=True)
    inputs,cases=corpus();(output/'input.bin').write_bytes(inputs);cpp,reference=build(output,args.target_dir);expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(cpp)],input=inputs);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual);rows=decode(expected,cases);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));aligned=first//4*4;case=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None)
        report=dict(passed=False,first_word=first//4,case=case,reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex());(output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    report=dict(passed=True,cases=len(cases),groups=dict(Counter(c['label'] for c in cases)),coverage=coverage(rows,cases),exact_words=len(expected)//4,input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),comparison='All proxy body49-word caches/inertia, COM-bound shapes, repeated registrations, original remote gates and ordered contact rows exact; no tolerance',limitations='Original network.rs uses explicit wire/fingerprint and stock-volume transports; original schema format/hash identity, capture/encode/socket/interpolation and complete shared host scheduling remain separate. Valid nonzero quaternions and33-body snapshots are the registration domain.')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
