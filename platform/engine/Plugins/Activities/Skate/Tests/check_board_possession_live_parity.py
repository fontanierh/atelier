#!/usr/bin/env python3
"""Exact active physical possession Owner, live effects, publications and stock bindings.

Run through the render lock/memory guard. Full original active host files are
byte-identical aliases; board and drive algorithms run on original BoardRuntime.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import resource
import signal
import shutil
import struct
import subprocess
from reference_build import build_probe
from check_gesture_parity import converter,PLUGIN
REFERENCE_REVISION='46513a6'
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def f(v):return list(map(bits,v))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
UNITS=('SimulationMath','RigidBody','BodyMass','AggregateMass','DeckGeometry','DriveFrames','ConstraintFrames','ConstraintSolver','JointBuild','DriveBuild','JointRecords','TruckDriveFrames','DrivePreparation','HookDrive','BoardAssembly','ContactBuild','ContactGeneration','BoardPose','ForceQueue','CollisionBody','BoardContactFeedback','BoardStep','BoardRuntime','SkeletonPoseFrames','SkeletonAnimationRecord','SkeletonPhysicalRecord','SkeletonBodyDefinition','SkeletonBody','BoardGroundAngle','SkeletonCollisionMode','SkeletonCollisionFeedback','SkeletonPoseErrors','SkeletonDriveFrames','Settings','NameId','BoardPossession','BoardPossessionManager','BoardPossessionDrives','BoardPossessionRuntime','BoardPossessionSettings')
HEADERS=('GeometryTypes.h','BoardTypes.h','ContactRetention.h','DataReader.h','BoardPhysicsSettings.h','BoardGround.h','SkeletonTargets.h')
def corpus():
    rng=random.Random(0x82db6150);records=[];cases=[]
    def numbers(n,scale=1.):return [rng.uniform(-scale,scale) for _ in range(n)]
    def matrix(angle=0.,position=None,carry=True):
        c,s=math.cos(angle),math.sin(angle);return f([c,0.,-s,rng.choice((0.,-0.,.25)) if carry else 0.,0.,1.,0.,0.,s,0.,c,rng.choice((0.,-0.,.5)) if carry else 0.,*(numbers(3,2.) if position is None else position),0.])
    def affine(phase=0.,position=None):
        c,s=math.cos(phase),math.sin(phase);return f([c,0.,-s,0.,1.,0.,s,0.,c,*(numbers(3,2.) if position is None else position)])
    def sim():return f([1/60,60.])+[30]+f([.001,0.,-9.81,0.])
    def state(seed,selected=2,progress=.4):
        raw=matrix(seed*.013)+matrix(seed*.019)+matrix(seed*.021)+f([.13,.4,progress,.3])
        for hand in range(2):raw+=matrix(seed*.003+hand)+matrix(seed*.004+hand)+[bits(1.),bits(.5),bits(300.),hand]*2
        return raw+[selected]
    def observe(seed,flags=0,mount=0,collision=0,contacts=(0,0),toolkit=True,surfaces=None):
        raw=matrix(seed*.01)+matrix(seed*.013,(0.,0.,0.))+f([0.,0.,0.,0.])+f(numbers(4,3.))+f([0.,0.,1.,.25,0.,0.,1.,0.])+[flags,mount,0,collision,1,*contacts]+f(numbers(8,1.))+matrix(seed*.005)+matrix(seed*.007)+matrix(seed*.009)+matrix(seed*.011)
        assert len(raw)==127
        raw+=matrix(seed*.015)+matrix(seed*.017)+[int(toolkit)]
        if toolkit:raw+=matrix(seed*.02,(.2,.3,-.1))
        raw+=list(surfaces if surfaces is not None else (1,2,3,4))
        for part in range(7):raw+=[(seed+part)%2]+f([0.,1.,0.])
        assert len(raw)==192+16*toolkit;return raw
    def body(seed,state=4):
        phase=seed*.031;s,c=math.sin(phase/2),math.cos(phase/2)
        raw=[state]+f([0.,s,0.,c])+affine(phase,(0.,0.,0.))[:9]+f([3.,.2,.1,.2,2.,.3,.1,.3,1.])+f(numbers(15,4.))+f([.2])+[17]+f([1.,2.,3.,.5,1.,100.,20.,.1,.2]);assert len(raw)==49;return raw
    def parameters(seed,n):return [seed%2,(seed>>1)%2,(seed>>2)%2,n]+[(seed+i)%2 for i in range(n)]+f([0.,-1.,0.,0.,0.,1.,0.,0.,.8])+[seed%2,1]
    def add(label,commands,seed=0,obs=None,initial=None,fields=(0,0,1),**meta):
        n=seed%7;custom=seed%2;raw=[0]+affine(seed*.017,(.1,.4,-.2))+sim()+[custom]
        if custom:
            for i in range(7):raw+=affine(.02*i,(i*.01,-.005,.02))
        raw+=f([.5,.4,.1,.6,.45,.2,.7,.5,.3,.8,.6,.4])+[seed%2,n]+[(seed+i)%2 for i in range(n)]+list(fields)+([0] if initial is None else [1]+initial)+f([(1/120,1/60,1/30,.125)[seed%4]])+[seed%256,seed%2]+(observe(seed) if obs is None else obs)+[len(commands)]+[w for cmd in commands for w in cmd]
        cases.append(dict(index=len(cases),operation='live',label=label,commands=[c[0] for c in commands],first_input_word=1+sum(len(r)//4 for r in records),input_words=len(raw),**meta));records.append(struct.pack('<'+'I'*len(raw),*raw))
    records.append(struct.pack('<I',1));cases.append(dict(index=0,operation='settings',label='actual frozen stock constructor, graphs, drag and live material bindings'))
    for seed in range(192):
        commands=[[3],[15],[8],[9]+f([1/60])+[6,11,15],[0]+observe(seed,flags=0x3000|(seed&4)),[2]]+[[2] for _ in range(8)]+[[8],[9]+f([1/120])+[31,100,200],[0]+observe(seed,flags=0x800,mount=0x80000 if seed%3==0 else 0),[2],[2],[8],[1,0,4,1],[13]+state(seed,2,1.),[2],[8],[0]+observe(seed,collision=0x4000000),[2],[1,7,2,1],[0]+observe(seed,toolkit=False),[19,10]+f([80.,0.,0.,.25]),[2],[8],[0]+observe(seed,flags=0x800),[2],[1,0,4,1],[0]+observe(seed,contacts=(1,1)),[2],[6],[7],[6],[7],[8],[9]+f([1/60])+[6,11,15]]
        add('connected actual board hook/material/volume lifecycle, fixed retrieval vs processed dt and8 throw batches',commands,seed,initial=state(seed) if seed%2 else None)
    for seed in range(64):
        commands=[[19,op]+([seed%2] if op==6 else f([0.,-1.,0.,0.,0.,1.,0.,0.,.8])+[1] if op==8 else matrix(seed*.1) if op==11 else f([.1,.2,.3,.25]) if op in(9,10,12,13) else []) for op in range(14)]
        commands += [[8],[9]+f([1/60])+[6,11,15],[14]+parameters(seed,seed%10),[10]]+[[20,body] for body in (0,1,2,3,4,5,6,8,31,0xffffffff)]+[[17,3,1,0,1],[10],[8],[15]]
        add('all live effect methods, actual mass-frame center, material pointers, child zip preservation and alignment release',commands,seed)
    for seed in range(96):
        commands=[[3],[9]+f([1/60])+[6,11,15],[18,0,bits(5.),0,bits(10.),0,bits(5.),0,bits(10.),1],[18,1,bits(3.),0,bits(11.),1,bits(4.),0,bits(12.),0],[9]+f([1/30])+[50,123,456]]
        for a,b,c in ((1,1,1),(2,4,2),(4,1,1),(1,2,4),(6,2,1)):
            commands += [[11,6]+body(seed,a),[11,11]+body(seed+1,b),[11,15]+body(seed+2,c),[9]+f([1/60])+[6,11,15]]
        commands += [[4],[9]+f([1/60])+[6,11,15]]
        add('both persistent hand drives retained hard regardless word3, active OR gating and custom reaction indices',commands,seed)
    for seed in range(96):
        commands=[[3],[1,3,4,1],[12,1,1,0,0,0],[8],[1,9,4,1],[12,1,0,17,5,1],[8],[12,0,99,2,0],[8],[6],[6],[7]]
        add('immediate transition callbacks merge only throw countdown, preserving caller mode/system',commands,seed,obs=observe(seed,flags=0x1000))
    for seed in range(128):
        surfaces=[rng.randrange(32) for _ in range(4)]
        commands=[[15],[14]+parameters(seed,seed%7),[8],[1,5,5,1],[2],[8]]
        add('weighted four-wheel surface vote, ignored14..31, override12 and retained contact alignment',commands,seed,obs=observe(seed,collision=0x2000000 if seed%4==0 else 0,surfaces=surfaces),surfaces=surfaces)
    return struct.pack('<I',len(records))+b''.join(records),cases

def build(output,target_dir):
    simulation=PLUGIN/'Source/AtelierSkate/Private/Simulation';snapshot=output/'simulation-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir()
    for name in [f'{n}.{e}' for n in UNITS for e in ('h','cpp')]+list(HEADERS):shutil.copy2(simulation/name,snapshot/name)
    cpp_prefix=PLUGIN/'Tests/Simulation/board_possession_probe.cpp';cpp_probe=PLUGIN/'Tests/Simulation/board_possession_live_probe.cpp';combined=snapshot/cpp_probe.name
    combined.write_text('#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wunused-function"\n'+cpp_prefix.read_text().split('int main()',1)[0]+'\n#pragma clang diagnostic pop\n'+cpp_probe.read_text())
    cpp=output/'board-possession-live-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{n}.cpp') for n in UNITS],str(combined),'-o',str(cpp)],check=True)
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip());revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip();host=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-host/src/physics').relative_to(root).as_posix()
    solve=subprocess.check_output(['git','show',f'{revision}:{host}/solve.rs'],cwd=root);deck=solve[solve.index(b'pub(super) fn deck_frame('):solve.index(b'\n}\n',solve.index(b'pub(super) fn deck_frame('))+3]
    rust_prefix=PLUGIN/'Tests/Reference/board_possession_probe.rs';rust_probe=PLUGIN/'Tests/Reference/board_possession_live_probe.rs';text=rust_prefix.read_text().split('fn main(){',1)[0].replace('crate::','skate_core::')+rust_probe.read_text();assert text.count('__DECK_FRAME__')==1;text=text.replace('__DECK_FRAME__',deck.decode());generated=output/'board-possession-live-combined.rs';generated.write_text(text)
    aliases={f'atelier-host/src/physics/offboard/{name[:-3]+"/mod.rs" if name in ("board_possession.rs","board_manager.rs") else name}':f'crates/skate-host/src/physics/offboard/{name}' for name in ('board_possession.rs','board_possession/drives.rs','board_possession/settings.rs','board_manager.rs','board_manager/runtime.rs')}
    reference=build_probe(output,'board-possession-live-reference',generated,target_dir,extra_sources=aliases)
    (output/'simulation-provenance.json').write_text(json.dumps(dict(simulation_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},probe_sha256={p.name:digest(p) for p in (cpp_prefix,cpp_probe,rust_prefix,rust_probe)},verbatim_deck_frame_sha256=hashlib.sha256(deck).hexdigest(),original_solve_sha256=hashlib.sha256(solve).hexdigest(),cpp_binary_sha256=digest(cpp)),indent=2)+'\n');return cpp,reference

def parse_snapshot(row,at,coverage):
    start=at;fields=row[at:at+3];coverage[f'state_{fields[1]}']+=1;at+=136+2+392+24+96+1
    at+=9+1;n=row[at];at+=1+n
    volumes=row[at:at+3];coverage['disabled_volume_snapshots']+=not any(volumes);at+=3;n=row[at];at+=1+n
    at+=10+1+9+3+1;present=row[at];at+=1+9*present;coverage['fill_snapshots']+=present
    at+=9+1+127+26*49
    return at,fields

def decode(data,cases):
    w=struct.unpack('<'+'I'*(len(data)//4),data);at=0;coverage=Counter()
    for c in cases:
        index,op,n=w[at:at+3];assert index==c['index'] and op==(1 if c['operation']=='settings' else 0);c.update(first_output_word=at,output_words=n+3);row=w[at+3:at+3+n]
        if op==0:
            commands=row[0];assert commands==len(c['commands']);cursor,_=parse_snapshot(row,1,coverage)
            for cmd in c['commands']:
                actual,size=row[cursor:cursor+2];assert actual==cmd;cursor+=2;end=cursor+size;coverage[f'command_{cmd}']+=1
                if cmd==8:cursor+=9
                elif cmd==9:
                    nr=row[cursor];cursor+=1;coverage[f'drive_rows_{nr}']+=1
                    for _ in range(nr):
                        a,b=row[cursor+96:cursor+98];assert a!=b;coverage['hand_deck_drive_rows']+=1;cursor+=98
                elif cmd==15:cursor+=127
                elif cmd==20:coverage['volume_gate_queries']+=1;assert row[cursor] in (0,1);cursor+=1
                cursor,_=parse_snapshot(row,cursor,coverage);assert cursor==end,(c['index'],cmd,cursor,end)
            assert cursor==len(row)
        else:coverage['settings']+=1
        at+=n+3
    assert at==len(w);return dict(coverage)

def compare(output,label,cpp,reference,assets,inputs,cases):
    bank=output/f'{label}-settings.simulation';bank.write_bytes(converter.encode_settings(assets/'private/stock/skater-collections.json'));expected=subprocess.check_output([str(reference),str(assets)],input=inputs);actual=subprocess.check_output([str(cpp),str(bank)],input=inputs)
    for name,data in (('input',inputs),('reference',expected),('cpp',actual)):(output/f'{label}-{name}.bin').write_bytes(data)
    coverage=decode(expected,cases);(output/f'{label}-cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));aligned=first//4*4;case=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None)
        result=dict(passed=False,fixture=label,first_word=first//4,case=case,reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex());(output/'first-divergence.json').write_text(json.dumps(result,indent=2)+'\n');raise AssertionError(result)
    return dict(label=label,cases=len(cases),exact_words=len(expected)//4,coverage=coverage,input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest())

def fixtures(output,collections):
    def field(data,category,name):
        r=next(r for r in data['collections'] if converter.name_id(r['class'])==converter.name_id(category) and converter.name_id(r['key'])==converter.name_id('default'))
        key=next(k for k in r['fields'] if converter.name_id(k)==converter.name_id(name));return r,key
    requests=[]
    for name in ('MaxDistance','DistanceToHideSkateboard','DistanceForBoardReturn','DistanceForMountedReturn','MinTimeToRetrieveBoardWhileMounting','ThrownSkateboardLaunchPitch','ThrownSkateboardPitchTarget','ThrownSkateboardPitchScalar','ThrownSkateboardRollScalar','ThrownSkateboardYawScalar'):
        for kind in ('missing','type','nan','words'):requests.append(('physics_skatecontroller',name,kind))
    for name in ('RetrievalTimeVsDist','RetrievalSpeedCurve','ThrownSkateboardVelocity'):
        for kind in ('missing','type','words','header_nan','knot_nan','value_nan','unordered','duplicate'):requests.append(('physics_skatecontroller',name,kind))
    for category,name in (('physicsdeck','DeckAngularDrag'),('physics_wipeout','SkateboardFriction'),('physics_wipeout','SkateboardRestitution')):
        for kind in ('missing','type','nan','words'):requests.append((category,name,kind))
    for index,(category,name,kind) in enumerate(requests):
        data=copy.deepcopy(collections);record,key=field(data,category,name);value=record['fields'][key]
        if kind=='missing':del record['fields'][key]
        elif kind=='type':value['type']='EA::Reflection::UInt32'
        elif kind=='nan':value['data']='7FC00000'
        elif kind=='words':value['data']='3F80000000000000'
        else:
            words=[value['data'][i:i+8] for i in range(0,len(value['data']),8)];assert len(words)==20
            if kind.endswith('nan'):words[{'header_nan':0,'knot_nan':4,'value_nan':12}[kind]]='7FC00000'
            elif kind=='unordered':words[4]='42C80000';words[5]='00000000'
            elif kind=='duplicate':words[5]=words[4]
            value['data']=''.join(words)
        label=f'{index}-{name}-{kind}';root=output/'asset-fixtures'/label;stock=root/'private/stock';stock.mkdir(parents=True,exist_ok=True);(stock/'skater-collections.json').write_text(json.dumps(data));yield label,root

def rejection_fixtures(inputs,cases):
    words=list(struct.unpack('<'+'I'*(len(inputs)//4),inputs))
    def header(c):
        raw=words[c['first_input_word']:c['first_input_word']+c['input_words']];at=1+19;custom=raw[at];at+=1+84*custom+13;n=raw[at];at+=1+n+3;present=raw[at];at+=1;retained=raw[at:at+133] if present else None;at+=133*present+3;observation=at;at+=159;toolkit=raw[at];surface=at+1+16*toolkit;at+=1+16*toolkit+4+28
        return raw,at,surface,observation,retained
    valid=next(c for c in cases if c['operation']=='live');raw,at,surface,observation,_=header(valid);base=raw[:at]
    invalid=base.copy();invalid[surface]=32;invalid[observation+51]=0
    yield 'wheel_surface32_contract',struct.pack('<'+'I'*(len(invalid)+2),1,*invalid,0)
    invalid=base+[2,1,0,1,1,2]
    yield 'held_default_hand2_contract',struct.pack('<'+'I'*(len(invalid)+1),1,*invalid)
    retained=next(header(c)[4] for c in cases if c['operation']=='live' and header(c)[4] is not None);retained=retained.copy();retained[-1]=3
    invalid=base+[2,13]+retained+[4]
    yield 'disable_hand3_contract',struct.pack('<'+'I'*(len(invalid)+1),1,*invalid)

def verify_rejections(output,cpp,reference,assets,inputs,cases):
    bank=output/'stock-settings.simulation';reports=[]
    def disable_core_dump():resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    for label,data in rejection_fixtures(inputs,cases):
        (output/f'{label}-input.bin').write_bytes(data);a=subprocess.run([str(reference),str(assets)],input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=output,preexec_fn=disable_core_dump);b=subprocess.run([str(cpp),str(bank)],input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=output,preexec_fn=disable_core_dump)
        if a.returncode!=101 or b'panicked at' not in a.stderr:raise AssertionError(f'{label}: original did not panic at the invalid contract')
        if b.returncode!=-signal.SIGABRT:raise AssertionError(f'{label}: the simulation did not explicitly abort at the invalid contract')
        (output/f'{label}-reference.stderr').write_bytes(a.stderr);(output/f'{label}-cpp.stderr').write_bytes(b.stderr);reports.append(dict(fixture=label,reference_exit=a.returncode,cpp_exit=b.returncode,input_sha256=hashlib.sha256(data).hexdigest()))
    return reports

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True);assets=args.assets.resolve()
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    cpp,reference=build(output,args.target_dir);inputs,cases=corpus();reports=[compare(output,'stock',cpp,reference,assets,inputs,cases)];collections=json.loads((assets/'private/stock/skater-collections.json').read_text())
    for label,fixture in fixtures(output,collections):reports.append(compare(output,label,cpp,reference,fixture,struct.pack('<II',1,1),[dict(index=0,operation='settings',label=label)]))
    rejections=verify_rejections(output,cpp,reference,assets,inputs,cases)
    result=dict(passed=True,cases=sum(r['cases'] for r in reports),exact_words=sum(r['exact_words'] for r in reports),fixtures=reports,rejections=rejections,settings_source_sha256=digest(assets/'private/stock/skater-collections.json'),comparison='Original active Owner/live Effects/runtime/loaders untouched; all retained board bodies/hook/state, current shape/material slots, physical publication bytes, observations and packed hand/deck drive rows exact with no tolerance',limitations='Completed animation/physical feedback frames and standard shape materials are explicit typed caller transports; full host shared scheduling, gameplay transitions and collision filtering integration are root-owned checks. Valid stock and malformed field/curve fixture errors compared; protocol encoding is outside this slice.')
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
