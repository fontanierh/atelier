#!/usr/bin/env python3
"""Exact board+rider initialization, active contacts, shared solve and feedback.

Run compilation/execution through the render lock and memory guard. The oracle
stages the complete unchanged original active host owners and actual stock
animation evaluator. Engine triangles, current controller requests and incoming
remote wire requests are explicit inputs. Pose adjustment/FootIK scheduling is
an upstream integration boundary; this test evaluates real authored hierarchies
and does not install a substitute IK callback.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import historical_oracle as historical
import random
import shutil
import struct
import subprocess
from check_gesture_parity import PLUGIN, converter
from reference_build import build_probe

OPERATIONS=('tick','begin_queries','finish_queries','reset_board_outputs','replace_world','select_driven','apply_prediction_correction','controller_fields','append_remote','clear_remote','hold_board')
UNITS=('NativeMath','RigidBody','BodyMass','AggregateMass','DeckGeometry','DriveFrames','ConstraintFrames','ConstraintSolver','JointBuild','DriveBuild','JointRecords','TruckDriveFrames','DrivePreparation','HookDrive','BoardAssembly','ContactBuild','ContactGeneration','BoardPose','ForceQueue','CollisionBody','BoardContactFeedback','BoardStep','BoardRuntime','Geometry','GeometrySweep','WorldGeometry','GeometryFeatures','GeometryPrism','GeometryTriangleFixup','WorldPrimitiveContact','GeometryPrimitivePair','ContactRetention','WorldContactProducer','BoardPhysicsSettings','BoardColliders','BoardGroundAngle','BoardGround','BoardProbes','BoardMotionOutput','BoardToolkit','SkeletonPoseFrames','SkeletonAnimationRecord','SkeletonPhysicalRecord','SkeletonBodyDefinition','SkeletonBody','SkeletonJoints','SkeletonDriveDynamics','SkeletonDriveFrames','SkeletonTargets','SkeletonDrives','SkeletonCollisionMode','SkeletonCollisionFeedback','SkeletonPoseErrors','SkeletonColliders','AssemblyContacts','SkeletonContactReports','SkeletonPhysicsSettings','SkeletonRoot','SkeletonBoardFrames','Settings','NameId','PhysicsSkeleton','NetworkProxies','BoardPossession','BoardPossessionDrives','BoardPossessionRuntime','BoardPossessionSettings','BoardPossessionManager','ReckoningFrames','RidingAngles','AnimationPose','AnimationPoseAuthored','AnimationPoseJson','AnimationPlayback','AnimationSamples','AnimationName','PhysicalSimulationSettings','PhysicalSimulationRuntime')

def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def floats(v):return list(map(bits,v))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def aliases():
    names=('settings.rs','skeleton_body.rs','skeleton_body_collision_settings.rs','skeleton_body_drive_settings.rs','colliders.rs','skeleton_colliders.rs','riding_outputs.rs','riding_outputs/ground_input.rs','riding_outputs/probes.rs','solve.rs','solve/assembly_contacts.rs','solve/diagnostics.rs','skeleton_feedback.rs','network.rs')
    result={f'atelier-host/src/physics/physical-host/{n[:-3]+"/mod.rs" if n in ("riding_outputs.rs","solve.rs") else n}':f'crates/skate-host/src/physics/{n}' for n in names}
    for n in ('board_possession.rs','board_possession/drives.rs','board_possession/settings.rs','board_manager.rs','board_manager/runtime.rs'):
        result[f'atelier-host/src/physics/offboard/{n[:-3]+"/mod.rs" if n in ("board_possession.rs","board_manager.rs") else n}']=f'crates/skate-host/src/physics/offboard/{n}'
    result['crates/skate-host/src/authored_clips.rs']='crates/skate-host/src/animation_pose/authored_clips.rs'
    result['atelier-host/src/skeleton_constraint_packing/packing.rs']='crates/skate-core/src/physics/solver/packing.rs'
    return result

def corpus():
    rng=random.Random(0x82be5094);records=[];cases=[]
    def affine(angle,position):
        c,s=math.cos(angle),math.sin(angle)
        return floats([c,0.,-s,0.,1.,0.,s,0.,c,*position])
    def world(slope=0.,height=-.035,wall=False,holes=False):
        corners=[(-12.,-12*slope+height,-12.),(12.,12*slope+height,-12.),(12.,12*slope+height,12.),(-12.,-12*slope+height,12.)]
        triangles=[([corners[j] for j in ids],0.,0x10,tag) for ids,tag in (((0,2,1),1),((0,3,2),12))]
        if holes:triangles=triangles[:1]
        if wall:
            triangles += [([(-3.,0.,1.),(3.,0.,1.),(3.,3.,1.)],0.,0,10),([(-3.,0.,1.),(3.,3.,1.),(-3.,3.,1.)],0.,0,11)]
        raw=[len(triangles)]
        for vertices,fat,flags,tag in triangles:raw+=floats([v for p in vertices for v in p])+[bits(fat),flags,tag]
        return raw
    def tick(seed,k,*,flags2476=0,flags2480=0,pose=None):
        states=(201,202,601,602,501,503,500,702);state=states[(seed+k//4)%len(states)];category=500 if state in (501,503,500) else 600 if state in (601,602) else 200
        flags2472=(0,0x400,0x8000,0x10000000)[(seed+k)%4]
        processed_dt=(1/60,1/120,1/30)[seed%3]
        raw=[0,(seed%4 if pose is None else pose),bits(processed_dt),(1,8,25)[seed%3],(0x2000,0x2100,0x800)[(seed+k)%3],state,category,flags2472,flags2480,flags2476,0]
        raw+=floats([.08*math.sin(k*.2),0. if k%3 else .15])+[int(seed%5==0)]+floats([(-.08,0.,.08,.3)[(seed+k)%4]])
        raw+=floats([.08*math.sin(k*.31),0.,.12 if k%5==0 else 0.,.01,.0,-.015,.05*math.sin(k*.13),-.04*math.cos(k*.17),9.81])
        assert len(raw)==24
        return raw
    def add(label,spawn,geometry,commands,seams=False,**meta):
        raw=spawn+geometry+[int(seams),len(commands)]+[w for c in commands for w in c]
        cases.append(dict(index=len(cases),label=label,commands=[c[0] for c in commands],**meta));records.append(struct.pack('<'+'I'*len(raw),*raw))
    for seed in range(80):
        slope=(0.,.12,-.12,.35)[seed%4];height=(.0,.05,.3,.8)[seed%4]
        spawn=affine(seed*.173,(rng.uniform(-.2,.2),height,rng.uniform(-.2,.2)))
        commands=[]
        for k in range(20):
            if k==2:commands+=[[5,(1,3,5,6)[seed%4]]]
            if k==5:commands+=[[6,1,(0,1<<18)[seed%2],0,0]]
            if k==8:commands+=[[4]+world(-slope,height=-.02,wall=seed%3==0)]
            if k==12:commands+=[[5,5],[3]]
            commands.append(tick(seed,k,pose=seed%4 if k<10 else (seed+1)%4))
        add('actual stock hierarchy, live rider/deck targets, changing terrain, retained feedback and filter histories',spawn,world(slope,wall=seed%4==3),commands,seams=seed%2,slope=slope,pose=seed%4)
    for seed in range(16):
        commands=[tick(seed,0),[7,0,0,1],[10],tick(seed,1),tick(seed,2,flags2476=0x3000),tick(seed,3),[7,0,2,1],tick(seed,4,flags2476=0x800),tick(seed,5,flags2476=0x800),[7,0,0,0]]+[tick(seed,k) for k in range(6,14)]
        add('concrete held hand drives, throw/retrieve effects and completed possession publication share the rider solve',affine(seed*.13,(0.,.3,0.)),world(),commands,seams=seed%2)
    for seed in range(16):
        mask=(1<<0)|(1<<4)|(1<<6)|(1<<(7+3))|(1<<(7+7))|(1<<(7+23))
        if seed%2:mask|=1<<63
        proxy=[8]+floats([.06 if seed%3 else 9.,.0,.04,.02,0.,0.,0.,1.])+[mask&0xffffffff,mask>>32]
        commands=[tick(seed,0),proxy,tick(seed,1),tick(seed,2),[9],tick(seed,3),[8]+floats([.0,.1,.0,0.,0.,0.,0.,1.])+[1<<6,0],tick(seed,4),[9],tick(seed,5)]
        add('actual remote registration, distant rejection, ragdoll owners and shared contact ordering',affine(seed*.2,(0.,.08,0.)),world(.12 if seed%2 else 0.),commands)
    for seed in range(8):
        commands=[[2],[1],[1],[4]+world(.2),[3],[2],[2],tick(seed,0),[5,0],[5,2],[5,4],[5,0xffffffff],[5,5],tick(seed,1)]
        add('pending query error domains, preserved handles across reset and terrain replacement, driven-mode rejection',affine(seed*.11,(0.,.1,0.)),world(),commands)
    return struct.pack('<I',len(records))+b''.join(records),cases

def preflight():
    native=PLUGIN/'Source/AtelierSkate/Private/Native';missing=[str(native/f'{n}.cpp') for n in UNITS if not(native/f'{n}.cpp').is_file()]
    if missing:raise AssertionError(missing)
    for relative in aliases().values():historical.source_bytes(relative)
    data,cases=corpus();words=struct.unpack('<'+'I'*(len(data)//4),data);at=1
    def skip_world():
        nonlocal at
        n=words[at];at+=1+12*n
    for c in cases:
        at+=12;skip_world();at+=1;n=words[at];at+=1
        if n!=len(c['commands']):raise AssertionError('Input command header')
        for op in c['commands']:
            if words[at]!=op:raise AssertionError((c,op,at));
            at+=1
            if op==4:skip_world()
            else:at+={0:23,1:0,2:0,3:0,5:1,6:4,7:3,8:10,9:0,10:0}[op]
    if at!=len(words):raise AssertionError('Input framing')
    return data,cases

def build(output,target_dir):
    native=PLUGIN/'Source/AtelierSkate/Private/Native';snapshot=output/'native-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir()
    for p in sorted(native.glob('*.h')):shutil.copy2(p,snapshot/p.name)
    for n in UNITS:shutil.copy2(native/f'{n}.cpp',snapshot/f'{n}.cpp')
    names=('body','collision','constraint');cpp_prefixes=[PLUGIN/f'Tests/Native/skeleton_{n}_probe.cpp' for n in names];cpp_probe=PLUGIN/'Tests/Native/physical_simulation_runtime_probe.cpp';combined=snapshot/cpp_probe.name
    combined.write_text('#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wunused-function"\n'+''.join(p.read_text().split('int main()',1)[0] for p in cpp_prefixes)+'\n#pragma clang diagnostic pop\n'+cpp_probe.read_text())
    cpp=output/'physical-simulation-runtime-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{n}.cpp') for n in UNITS],str(combined),'-o',str(cpp)],check=True)
    rust_prefixes=[PLUGIN/f'Tests/Reference/skeleton_{n}_probe.rs' for n in names];rust_probe=PLUGIN/'Tests/Reference/physical_simulation_runtime_probe.rs'
    prefix=''.join(p.read_text().split('fn main(){',1)[0] for p in rust_prefixes).replace('use crate::{','use skate_core::{').replace('skeleton_root::inverse_rigid,','').replace('solver::{packed,JointConstraint}','solver::{JointConstraint}').replace('#[path="physics/solver/packing.rs"] mod skeleton_constraint_packing;', 'mod skeleton_constraint_packing{use skate_core::physics::solver::{packed,JointConstraint};use crate::{RetailDriveRows,RetailContactJacobian};use skate_core::physics::rigid_body::RetailReactionCorrections;#[path="packing.rs"]mod original;pub fn drive(r:&RetailDriveRows)->packed::Drive{original::drive(r)}}')
    generated=output/'physical-simulation-runtime-combined.rs';generated.write_text(prefix+rust_probe.read_text())
    reference=build_probe(output,'physical-simulation-runtime-reference',generated,target_dir,bevy=True,extra_sources=aliases())
    (output/'native-provenance.json').write_text(json.dumps(dict(native_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},probe_sha256={p.name:digest(p) for p in (*cpp_prefixes,cpp_probe,*rust_prefixes,rust_probe)},cpp_binary_sha256=digest(cpp)),indent=2)+'\n');return cpp,reference

def decode(data,cases):
    words=struct.unpack('<'+'I'*(len(data)//4),data);at=0;coverage=Counter()
    for c in cases:
        index,n,size=words[at:at+3]
        if index!=c['index'] or n!=len(c['commands']):raise AssertionError('Physical owner stream identity')
        c.update(first_output_word=at,output_words=size+3);cursor=at+3;initial=words[cursor];cursor+=1+initial;c['initial_words']=initial;c['outputs']=[]
        for op in c['commands']:
            if words[cursor]!=op:raise AssertionError('Physical owner command order')
            nwords=words[cursor+1];start=cursor+2;end=start+nwords;payload=words[start:end];coverage[OPERATIONS[op]]+=1
            if op in (0,1,2,5):
                status=payload[0];coverage[f'{OPERATIONS[op]}_success' if status else f'{OPERATIONS[op]}_error']+=1
                if op==0 and status!=1:raise AssertionError(f'Actual original physical tick failed in stream {index}: '+str(payload[:80]))
            if nwords<8:raise AssertionError('Missing physical owner counters')
            contacts,remote,solved,drives,proxies,ground,wheels,animated=payload[-8:]
            coverage['generated_contacts']+=contacts;coverage['remote_contacts']+=remote;coverage['compiled_contact_rows']+=solved;coverage['retained_rider_drive_rows']+=drives;coverage['proxy_body_snapshots']+=proxies;coverage['ground_part_snapshots']+=ground;coverage['wheel_contact_snapshots']+=wheels;coverage[f'animated_{animated}']+=1
            c['outputs'].append(dict(operation=OPERATIONS[op],first_output_word=cursor,output_words=nwords+2,generated_contacts=contacts,remote_contacts=remote,solved_contacts=solved,drive_rows=drives,proxy_bodies=proxies,wheel_contacts=wheels));cursor=end
        if cursor!=at+size+3:raise AssertionError('Physical owner snapshot size')
        at=cursor
    if at!=len(words):raise AssertionError('Trailing physical owner output')
    for name in ('generated_contacts','remote_contacts','compiled_contact_rows','retained_rider_drive_rows','ground_part_snapshots','wheel_contact_snapshots'):
        if not coverage[name]:raise AssertionError('Actual connected producer was not exercised: '+name)
    return dict(coverage)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--samples',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);p.add_argument('--preflight',action='store_true');args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    inputs,cases=preflight();(output/'input.bin').write_bytes(inputs)
    if args.preflight:print(json.dumps(dict(streams=len(cases),commands=sum(len(c['commands']) for c in cases),ticks=sum(c['commands'].count(0) for c in cases),input_bytes=len(inputs),source_units=len(UNITS),forward_aliases=len(aliases())),indent=2));return
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    assets=args.assets.resolve();samples=args.samples.resolve();stock=assets/'private/stock';settings=output/'settings.native';physical=output/'physics.native';settings.write_bytes(converter.encode_settings(stock/'skater-collections.json'));physical.write_bytes(converter.encode_physics_skeletons(stock/'physics-skeletons.json'));identity=json.loads((stock/'physics-skeletons.json').read_text())['source_sha256']
    cpp,reference=build(output,args.target_dir);expected=subprocess.check_output([str(reference),str(assets)],input=inputs);actual=subprocess.check_output([str(cpp),str(settings),str(physical),str(samples/'native/rig.skate'),identity],input=inputs)
    (output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual);coverage=decode(expected,cases);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));aligned=first//4*4;c=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None);command=next((o for o in c['outputs'] if o['first_output_word']*4<=first<(o['first_output_word']+o['output_words'])*4),None) if c else None
        report=dict(passed=False,first_word=first//4,case=c,command=command,reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex());(output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    result=dict(passed=True,streams=len(cases),exact_words=len(expected)//4,groups=dict(Counter(c['label'] for c in cases)),coverage=coverage,input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),settings_source_sha256=digest(stock/'skater-collections.json'),physics_source_sha256=digest(stock/'physics-skeletons.json'),native_rig_sha256=digest(samples/'native/rig.skate'),comparison='All actual board/rider/target/proxy bodies, physical/animation/COM histories, root predictions, contact and retained drive rows, collision feedback, pose errors, wheel/probe/orientation/filter/motion state and live possession/material publications exact; no tolerance; full original host producer modules unchanged',limitations='Current gameplay Processed fields and engine triangles are explicit inputs. Actual authored pose hierarchy is evaluated in both backends; upstream pose adjustment/FootIK and complete gameplay lifecycle scheduling remain separate integration work. Remote body/wire requests are explicit; fingerprint construction/capture format remains a separately documented boundary. Finite valid simulation and original query/collision-selector diagnostics covered; Rust Debug text for invalid physical diagnostics is not reproduced byte-for-byte by the typed native diagnostic.')
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':historical.run_cli(main)
