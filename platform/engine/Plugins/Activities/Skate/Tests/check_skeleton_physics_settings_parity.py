#!/usr/bin/env python3
"""Compare actual original stock physical skeleton loaders with simulation settings bindings.

Run through the render lock/memory guard. Original JSON is oracle/conversion
input only; C++ consumes verified ATATTR01/ATPHYS01 banks and typed hierarchy.
"""
import argparse
import copy
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
from check_gesture_parity import converter,PLUGIN
from reference_build import build_probe
OPERATIONS=('body','collision','hierarchy')
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def f(v):return list(map(bits,v))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def corpus(collections,small=False):
    rng=random.Random(0x82bd6c40);records=[];cases=[]
    def add(op,payload,label,**meta):cases.append(dict(index=len(cases),operation=OPERATIONS[op],label=label,**meta));records.append(struct.pack('<'+'I'*(len(payload)+1),op,*payload))
    def text(s):raw=s.encode();return [len(raw),*raw]
    def matrix(angle=0.,xyz=(0.,.5,0.),carry=True):
        c,s=math.cos(angle),math.sin(angle);return f([c,0.,-s,.25 if carry else 0.,0.,1.,0.,.0,s,0.,c,.25 if carry else 0.,*xyz,.25 if carry else 0.])
    def matrices(n,phase=0.):return [w for i in range(n) for w in matrix(phase+i*.01,(i*.01,.5,0.))]
    def sim():return f([1/60,60.])+[30]+f([.001,0.,-9.81,0.])
    hats=[r['key'] for r in collections['collections'] if converter.name_id(r['class'])==converter.name_id('physics_hat')]
    if small:hats=[]
    for seed in range(2 if small else 64):add(0,[0]+text('')+matrices(24,seed*.03)+matrix(seed*.01,(seed*.01,.4,0.))+sim(),'stock simulation body and all cached mass/physical histories',hat=False)
    for key in hats:add(0,[1]+text(key)+matrices(24,.2)+matrix(.3)+sim(),'every authored hat geometry and head compound mass',hat=True,hat_key=key)
    if not small:add(0,[1]+text('absent_harness_hat')+matrices(24)+matrix()+sim(),'missing hat collection diagnostic',hat=True,hat_key='absent_harness_hat',valid=False)
    for all_pairs in (0,1):add(1,[all_pairs],'stock per-bone collision priorities/compliance and feedback configuration',cull_all=bool(all_pairs))
    def hierarchy(seed,mode=0,with_drives=True,drive_mode=0):
        n=48 if seed%2 else 24;indices=[2*i if n==48 else i for i in range(24)];parents=[-1]*n
        for child in range(1,23):
            i=indices[child];physical_parent=23 if child%4==0 or child==22 else child+1
            if n==48:parents[i]=i+1;parents[i+1]=indices[physical_parent]
            else:parents[i]=indices[physical_parent]
        pn=n
        if mode==1:pn=n-1
        elif mode==2:indices[0]=n
        elif mode==3:parents[indices[3]]=-2
        elif mode==4:parents[indices[3]]=n+1
        elif mode==5:
            # Only unmapped nodes can reach the traversal cycle gate.
            n=49;pn=n;indices=list(range(24));parents=[-1]*n
            for child in range(1,23):parents[child]=23
            parents[3]=24;parents[24]=24
        elif mode==6:parents[indices[1]]=-1
        payload=[n]+matrices(n,seed*.005)+[pn]+[v&0xffffffff for v in parents[:pn]]+indices+[int(with_drives)]
        if with_drives:
            dn=n if drive_mode==0 else 0;di=indices.copy()
            if drive_mode==2:dn=n;di[2]=n
            payload+=[dn]+matrices(dn,seed*.007)+di+matrices(24,seed*.003)+matrix(seed*.01)+matrix(seed*.03)+sim()
        return payload,dict(valid=mode==0,mode=mode,drives=with_drives,drive_mode=drive_mode)
    for seed in range(2 if small else 96):
        data,meta=hierarchy(seed);add(2,data,'closest mapped ancestor through real ordered hierarchy and stock22 joint/drive definitions',**meta)
    if not small:
        for mode in range(1,7):
            data,meta=hierarchy(1,mode);add(2,data,'initial rig/index/negative/cyclic/missing parent error contracts',**meta)
        for mode in (1,2):
            data,meta=hierarchy(0,0,True,mode);add(2,data,'drive hierarchy/index rejection after successful joint binding',**meta)
    return struct.pack('<I',len(records))+b''.join(records),cases

def build(output,target_dir):
    simulation=PLUGIN/'Source/AtelierSkate/Private/Simulation';snapshot=output/'simulation-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir()
    units=('SimulationMath','RigidBody','BodyMass','AggregateMass','DeckGeometry','DriveFrames','ConstraintFrames','ConstraintSolver','JointBuild','DriveBuild','JointRecords',
        'TruckDriveFrames','DrivePreparation','HookDrive','BoardAssembly','ContactBuild','ContactGeneration','BoardPose','ForceQueue','CollisionBody','BoardContactFeedback','BoardStep','BoardRuntime',
        'SkeletonPoseFrames','SkeletonAnimationRecord','SkeletonPhysicalRecord','SkeletonBodyDefinition','SkeletonBody','SkeletonJoints','SkeletonDriveDynamics','SkeletonDriveFrames','SkeletonTargets','SkeletonDrives',
        'BoardGroundAngle','SkeletonCollisionMode','SkeletonCollisionFeedback','SkeletonPoseErrors','Settings','NameId','PhysicsSkeleton','SkeletonPhysicsSettings')
    for name in [f'{n}.{e}' for n in units for e in ('h','cpp')]+['GeometryTypes.h','BoardTypes.h','ContactRetention.h','DataReader.h']:shutil.copy2(simulation/name,snapshot/name)
    prefixes=[PLUGIN/f'Tests/Simulation/skeleton_{name}_probe.cpp' for name in ('body','collision','constraint')];probe=PLUGIN/'Tests/Simulation/skeleton_physics_settings_probe.cpp';combined=snapshot/probe.name
    combined.write_text('#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wunused-function"\n'+''.join(p.read_text().split('int main()',1)[0] for p in prefixes)+'\n#pragma clang diagnostic pop\n'+probe.read_text())
    cpp=output/'skeleton-physics-settings-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{n}.cpp') for n in units],str(combined),'-o',str(cpp)],check=True)
    shared=PLUGIN/'Tests/Reference/skeleton_body_probe.rs';rust_probe=PLUGIN/'Tests/Reference/skeleton_physics_settings_probe.rs';generated=output/'skeleton-physics-settings-combined.rs'
    generated.write_text(shared.read_text().split('fn main(){',1)[0].replace('use crate::{','use skate_core::{').replace('skeleton_root::inverse_rigid,','')+rust_probe.read_text())
    reference=build_probe(output,'skeleton-physics-settings-reference',generated,target_dir)
    (output/'simulation-provenance.json').write_text(json.dumps(dict(simulation_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},probe_sha256={p.name:digest(p) for p in (*prefixes,probe,shared,rust_probe)},cpp_binary_sha256=digest(cpp)),indent=2)+'\n')
    return cpp,reference

def decode(data,cases):
    w=struct.unpack('<'+'I'*(len(data)//4),data);at=0;rows=[]
    for c in cases:
        index,op,n=w[at:at+3]
        if index!=c['index'] or OPERATIONS[op]!=c['operation']:raise AssertionError('Settings output identity changed')
        rows.append(w[at+3:at+3+n]);c.update(first_output_word=at,output_words=n+3);at+=n+3
    if at!=len(w):raise AssertionError('Trailing settings output')
    return rows

def compare(output,label,cpp,reference,assets,collections,cases_input,cases,identity):
    source=assets/'private/stock';settings=output/f'{label}-settings.simulation';physical=output/f'{label}-physics.simulation';settings.write_bytes(converter.encode_settings(source/'skater-collections.json'));physical.write_bytes(converter.encode_physics_skeletons(source/'physics-skeletons.json'))
    expected=subprocess.check_output([str(reference),str(assets),identity],input=cases_input);actual=subprocess.check_output([str(cpp),str(settings),str(physical),identity],input=cases_input);(output/f'{label}-input.bin').write_bytes(cases_input);(output/f'{label}-reference.bin').write_bytes(expected);(output/f'{label}-cpp.bin').write_bytes(actual)
    rows=decode(expected,cases);(output/f'{label}-cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));aligned=first//4*4;case=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None)
        report=dict(passed=False,fixture=label,first_word=first//4,case=case,reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex());(output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    counts=Counter()
    for row,c in zip(rows,cases):
        counts[c['operation']]+=1;counts['successful_bindings' if row[0]==1 else 'errors']+=1
        if c['operation']=='hierarchy' and row[0]==1:
            at=1+22*38
            if c['drives'] and row[at]==1:counts['drive_owners']+=1
            elif c['drives']:counts['drive_errors']+=1
        if c['operation']=='body' and c.get('hat') and row[0]==1:counts['hat_bodies']+=1
    return dict(label=label,cases=len(cases),exact_words=len(expected)//4,coverage=dict(counts),input_sha256=hashlib.sha256(cases_input).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest())

def fixtures(output,assets,collections,physical):
    def setting(data,category,name):
        for r in data['collections']:
            if converter.name_id(r['class'])==converter.name_id(category) and converter.name_id(r['key'])==converter.name_id('default'):
                for key in r['fields']:
                    if converter.name_id(key)==converter.name_id(name):return r['fields'],key
        raise AssertionError(f'Missing authored fixture setting {category}/{name}')
    variants=[]
    for label,category,name,kind in (('missing_density','physics_skeleton','MassOfSkeleton','missing'),('density_wrong_type','physics_skeleton','MassOfSkeleton','type'),('density_nonfinite','physics_skeleton','MassOfSkeleton','nan'),('density_word_count','physics_skeleton','MassOfSkeleton','words'),('invalid_collision_bool','physics_skeleton','EnableCollision','bool'),('missing_drive_transition','physics_skeleton_drives','Hash_E1B89BB09D725EEC','missing'),('drive_scalar_wrong_type','physics_skeleton_drives','CollisionDriveScalar','type')):
        data=copy.deepcopy(collections);fields,key=setting(data,category,name)
        if kind=='missing':del fields[key]
        elif kind=='type':fields[key]['type']='EA::Reflection::UInt32'
        elif kind=='nan':fields[key]['data']='7FC00000'
        elif kind=='words':fields[key]['data']='3F80000000000000'
        elif kind=='bool':fields[key]['data']='02000000'
        variants.append((label,data,physical))
    shortened=copy.deepcopy(physical)
    for record in shortened['skeletons']:
        if record['name'].lower()=='phys_tpose':record['bones']=record['bones'][:23]
    variants.append(('short_physical_bone_count',collections,shortened))
    for label,data,phys in variants:
        root=output/'asset-fixtures'/label;stock=root/'private/stock';stock.mkdir(parents=True,exist_ok=True);(stock/'skater-collections.json').write_text(json.dumps(data));(stock/'physics-skeletons.json').write_text(json.dumps(phys));yield label,root,data

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True);assets=args.assets.resolve()
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    collections=json.loads((assets/'private/stock/skater-collections.json').read_text());physical=json.loads((assets/'private/stock/physics-skeletons.json').read_text());identity=physical['source_sha256'];cpp,reference=build(output,args.target_dir)
    inputs,cases=corpus(collections);reports=[compare(output,'stock',cpp,reference,assets,collections,inputs,cases,identity)]
    for label,fixture,data in fixtures(output,assets,collections,physical):
        inputs,cases=corpus(data,small=True);reports.append(compare(output,label,cpp,reference,fixture,data,inputs,cases,identity))
    if not reports[0]['coverage'].get('drive_owners') or not reports[0]['coverage'].get('errors'):raise AssertionError('Missing stock hierarchy success/error coverage')
    result=dict(passed=True,cases=sum(r['cases'] for r in reports),exact_words=sum(r['exact_words'] for r in reports),fixtures=reports,settings_source_sha256=digest(assets/'private/stock/skater-collections.json'),physics_source_sha256=digest(assets/'private/stock/physics-skeletons.json'),comparison='All original stock body/hat/mass/history, joint ancestors/frames, drive owners, collision/feedback and tested hierarchy/setting diagnostics exact; C++ simulation banks only',limitations='Initial hierarchy/pose matrices are explicit caller fixtures; animation hierarchy evaluation has its own comparator. Simulation bank loading/identity diagnostics are covered separately.')
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
