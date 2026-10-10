#!/usr/bin/env python3
"""Live Slide host composition with unchanged core leaves and explicit producers.

Only run under the coordinator's render/memory guard. This proves source call
order, lifecycle and real board/controller mutations across producer boundaries;
concrete skeleton/world/trajectory producers are separate owner comparisons.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
import check_ground_control_settings_parity as ground
import check_animation_trees_parity as trees
from check_animation_playback_parity import Stream,bits
from check_gesture_parity import converter,PLUGIN
from reference_build import build_probe


class Writer(Stream):
    def vector(self,values):
        for value in values:self.float(value)
    def curve(self,ys):self.vector(range(8));self.vector(ys)


def frame(w,tick,*,fail=0,valid=True,surface=1,mode=0,wall=0,collision=0,manual_error=False,balance=None):
    w.word(fail);w.word(valid);w.word(surface);w.word(mode);w.word((1<<20 if tick%3==0 else 0)|(1<<29 if tick%5==0 else 0));flags=((1<<27) if tick%4<2 else 0)|((1<<26) if tick%4 in (0,2) else 0)|(0x20000 if collision else 0);w.word(flags);w.word(tick%5)
    velocity=[2,-2,4,.137] if wall else [(.317*(tick%7-3)),.137,(tick%11-5)*.731,.113];normal=[1,0,0,.137] if wall else [0,1,0,.137];up=[1,0,0,.317] if wall else [0,1,0,.317]
    for v in (velocity,normal,[1,0,0,.173],[0,0,1,.317],[.137,0,1,.113],[.137,.317,.731,.113]):w.vector(v)
    w.vector((abs((tick%13-6)*.731)+.137,(tick%11-5)*.517,(-1,-.731,-0.0,0,.137,.731,1)[tick%7],(.0,.49999997,.5,1,1.5,1.5000001,2)[tick%7],(.0,.317,.731,1,1.137)[tick%5]))
    for v in (up,[1e-8 if collision==3 else 1,0,0,.517],[2 if collision==2 else -.317,.137,1.137,.113],[0,0,1,.173]):w.vector(v)
    w.vector((0,1,0));w.vector((8.137,9.81,5.137,(0,.003,1/60,.033)[tick%4]))
    manual_balance=float('nan') if manual_error else ((-.731,-.137,-0.0,0,.317,.731)[tick%6] if balance is None else balance)
    w.vector(((-.731,-.137,0,.317,.731)[tick%5],(-1,-.0,0,.137,1)[tick%5],(tick%11)*.731,1,manual_balance,(tick%7)/6));w.word(tick%3==0)
    w.vector((manual_balance,1,tick*.03125,abs(tick%13-6)*.731,.137,(0,.003,1/60,.033)[tick%4]));w.word(0);w.word(tick%5==0);w.word(tick%4<2);w.word(tick%4 in (0,2));w.word(tick%3==0)
    for v in ([1,0,0,.137],[0,0,1,.173],[.137,0,1,.317],[0,0,1,.113],[0,.137,-.317,.731],[.137,-.03125,.731,.113],[-.137,.03125,-.731,.173]):w.vector(v)
    for v in ([.137,0,.317,.113],[.731,.2,.517,.173],[0,1,0,.137]):w.vector(v)
    w.word(0x12345678);w.word(wall!=0);w.vector((.137 if wall==2 else 0,(-.5,0,.137)[tick%3]))
    w.vector((.137,.731,.317,(-0.0,.137,.731)[tick%3],manual_balance,(tick%11-5)*.731))
    for v in ([1,0,0,.137],velocity,[0,1,0,.317]):w.vector(v)


def corpus():
    rng=random.Random(0x82d3a900);cases=[];records=[]
    def new(label,seed,preseed=0):
        w=Writer();w.curve([.1+i*.03125 for i in range(8)]);w.vector((.5,.09,.6,1,.25,.66,3));w.vector((.731,-.137,.731,.731));w.curve([.137+i*.03125 for i in range(8)]);w.vector((13.7,.137,-.317));w.word(1);w.word(1);w.vector((.113,.173,.317,.517,.731));w.vector((.137,.317,-.173,.05,.137));w.word(seed%2);w.vector((.731,-.317));w.word(3);w.word((0,1,2)[seed%3]);w.float(.731)
        for body in range(7):w.vector([rng.uniform(-1,1) for _ in range(12)]+[.137+body*.03125])
        w.word(preseed)
        for n in range(preseed):w.word(100+n);w.vector((.137*n,.317,.731,-.137,.173,.113))
        rows=[];cases.append(w);records.append(dict(label=label,commands=rows,preseed=preseed));return w,rows
    def emit(w,rows,op,**info):rows.append(dict(op=op,**info));w.word(op)
    for case in range(12):
        w,rows=new('mixed live histories',case,(0,18,20,21)[case%4]);w.word(40)
        for tick in range(40):
            if tick in (0,20):emit(w,rows,0,category=100 if tick==0 else 101);w.word(100 if tick==0 else 101);w.float((tick+1)*.317)
            elif tick in (10,30):emit(w,rows,1)
            elif tick in (11,31):emit(w,rows,3)
            else:
                collision=(0,1,2,3)[(tick+case)%4];wall=(0,0,1,2)[(tick//3+case)%4];emit(w,rows,2,tick=tick,fail=0,valid=True,surface=case%5+1,mode=(tick+case)%5,wall=wall,collision=collision);frame(w,tick,surface=case%5+1,mode=(tick+case)%5,wall=wall,collision=collision)
    failures=[dict(valid=False),dict(fail=3),dict(fail=5),dict(surface=0),dict(surface=6),dict(surface=0xffffffff),dict(mode=5),dict(mode=0xffffffff),dict(manual_error=True),*[dict(fail=code,wall=2,balance=.317) for code in (10,11,12,13,15)]]
    for seed,failure in enumerate(failures):
        w,rows=new('source failure partial writes',seed,18);w.word(5);emit(w,rows,2,wall=0,collision=1);frame(w,seed+1,collision=1,balance=.317);emit(w,rows,3);emit(w,rows,2,**failure);frame(w,seed+2,**failure);emit(w,rows,2,wall=0,collision=2);frame(w,seed+3,collision=2,balance=.317);emit(w,rows,1)
    # Applied -> late false -> early flag false -> early tiny projection. The
    # real GroundRuntime keeps the last successful force through all three.
    for case in range(4):
        w,rows=new('retained collision, all force branches',case);w.word(9)
        for tick,collision in enumerate((1,2,0,3,1,2,0,3,1)):
            emit(w,rows,2,collision=collision,wall=0);frame(w,tick+11,collision=collision,balance=.317)
    return cases,records


def encode(cases):return struct.pack('<I',len(cases))+b''.join(w.data for w in cases)


def validate_corpus(cases,records):
    for w,r in zip(cases,records):
        words=struct.unpack('<'+'I'*(len(w.data)//4),w.data);at=23+20+5+5+5+6+7*13;preseed=words[at];at+=1+7*preseed;count=words[at];at+=1;assert count==len(r['commands'])
        for row in r['commands']:
            assert words[at]==row['op'];at+=1+(2 if row['op']==0 else 139 if row['op']==2 else 7 if row['op']==4 else 0)
        assert at==len(words),(r,at,len(words))


def prepare_source(output):
    lifecycle_path='crates/skate-host/src/physics/slide_state.rs';life=trees.source_at_reference(lifecycle_path);board_path='crates/skate-host/src/physics/slide_state/update.rs';board=trees.source_at_reference(board_path);settings_path='crates/skate-host/src/physics/slide_state/settings.rs';settings=trees.source_at_reference(settings_path);runtime_path='crates/skate-host/src/physics/ground_runtime/mod.rs';runtime=trees.source_at_reference(runtime_path);source=trees.source_at_reference('crates/skate-host/src/physics/ground_runtime/settings.rs');records=[];functions=[]
    for name in ('enter','exit','update'):
        text,record=trees.extract_block(life,'pub(crate) fn '+name+'(');records.append(record);functions.append(text)
    methods=[]
    for name in ('contact_response_with_previous','apply_angular_displacement','set_animated_velocity','calculate_collision_force'):
        text,record=trees.extract_block(runtime,'    pub fn '+name+'(');records.append(record);methods.append(text)
    decoder,record=trees.extract_block(source,'pub(super) fn curve8(');records.append(record);manual,record=trees.extract_block(source,'fn manual_settings(');records.append(record)
    appended='\nmod stock {use super::*;use skate_data::collections::Collections;\n'+decoder+'\n'+manual+'\npub fn manual(data:&Collections)->Result<ManualSettings,String> {manual_settings(data)}\n'
    for field,typename,function in (('steering','SteeringSettings','steering'),('manual_mode','ManualMode','manual_mode'),('force','GroundForceSettings','force')):
        literal,record=ground.extract_literal(source,f'            {field}: {typename} {{');records.append(record);appended+=f'pub fn {function}(data:&Collections'+(',mode:&str' if function=='manual_mode' else '')+f')->Result<{typename},String> {{\nlet f=|class,field|data.float(class,"default",field);\nlet c8=|class,field|curve8(data,class,"default",field);\n'+('let m=|field|data.float("physics_mode",mode,field);\n' if function=='manual_mode' else '')+'let threshold=[f32::from_bits(0x3586_37bd);4];\nOk('+literal+')\n}\n'
    appended+='}\n';template=(PLUGIN/'Tests/Reference/slide_state_runtime_probe.rs').read_text()
    for marker,text in (('// ORIGINAL_GROUND_RUNTIME_METHODS','\n'.join(methods)),('// ORIGINAL_SLIDE_SETTINGS',settings),('// ORIGINAL_SLIDE_FUNCTIONS','\n'.join(functions)),('// ORIGINAL_SLIDE_BOARD',board)):
        assert template.count(marker)==1;template=template.replace(marker,text)
    probe=output/'slide-state-runtime-oracle.rs';probe.write_text(template+appended)
    (output/'extraction-provenance.json').write_text(json.dumps(dict(verbatim_functions=records,whole_module_sha256={board_path:hashlib.sha256(board.encode()).hexdigest(),settings_path:hashlib.sha256(settings.encode()).hexdigest()},source_sha256={lifecycle_path:hashlib.sha256(life.encode()).hexdigest(),runtime_path:hashlib.sha256(runtime.encode()).hexdigest()},probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(),boundary='Actual Slide enter/exit/update and whole board update module, whole constructor, exact GroundRuntime contact/animated velocity/deck correction/retained collision methods, all unchanged core leaves. Completed Ground inputs and skeleton/world/trajectory calls are explicit producer shells with recorded order/results; concrete producers are not replaced in production and are outside this composition proof.'),indent=2)+'\n');return probe


def build_simulation(output):
    live=PLUGIN/'Source/AtelierSkate/Private/Simulation';code=output/'simulation-source'
    if code.exists():shutil.rmtree(code)
    code.mkdir();files=('SimulationMath','RigidBody','BodyMass','AggregateMass','DeckGeometry','DriveFrames','ConstraintFrames','ConstraintSolver','JointBuild','DriveBuild','JointRecords','TruckDriveFrames','DrivePreparation','HookDrive','BoardAssembly','ContactBuild','ContactGeneration','BoardPose','ForceQueue','CollisionBody','BoardContactFeedback','BoardStep','BoardRuntime','DeckAngularCorrections','NameId','Settings','GroundControlSettings','Steering','SteeringWobbleSettings','SpeedWobble','GroundForce','Manual','BoardGroundAngle','RidingAngles','RidingCollisionResponse','GroundContactResponse','StockSettingsReader','SlideState','SlideStateSettings','SlideStateRuntime')
    for p in list(live.glob('*.h'))+[live/(name+'.cpp') for name in files]:shutil.copyfile(p,code/p.name)
    probe=code/'slide_state_runtime_probe.cpp';shutil.copyfile(PLUGIN/'Tests/Simulation/slide_state_runtime_probe.cpp',probe);(output/'simulation-source-provenance.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(code.iterdir())},indent=2)+'\n')
    simulation=output/'slide-state-runtime-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(code),*[str(code/(name+'.cpp')) for name in files],str(probe),'-o',str(simulation)],check=True);return simulation


def decode(data,records):
    at=0;cases=[]
    def word():
        nonlocal at
        value=struct.unpack_from('<I',data,at)[0];at+=4;return value
    for c,record in enumerate(records):
        frames=[]
        for tick,row in enumerate(record['commands']):
            assert (word(),word(),word())==(c,tick,row['op']);ok=word();n=word();error=data[at:at+n].decode();at+=n;size=word();w=[word() for _ in range(size)];cursor=391;count=w[cursor];cursor+=1;queue=[w[cursor+7*i:cursor+7*i+7] for i in range(count)];cursor+=7*count;retained=w[cursor];cursor+=1;collision=w[cursor:cursor+12] if retained else None;cursor+=12 if retained else 0;n=w[cursor];cursor+=1;trace=w[cursor:cursor+n];cursor+=n;mode=w[cursor];cursor+=1;observed=w[cursor];cursor+=1;physical=w[cursor:cursor+23] if observed else None;cursor+=23 if observed else 0;launched=w[cursor];cursor+=1;launch=w[cursor:cursor+4] if launched else None;cursor+=4 if launched else 0;assert cursor==len(w),(record,tick,cursor,len(w));frames.append(dict(ok=ok,error=error,slide=w[:5],manual=w[5:10],steering=w[10:15],lifecycle=w[15:21],material=w[21:24],bodies=[w[24+49*i:24+49*(i+1)] for i in range(7)],hook=w[367:391],queue=queue,retained_collision=collision,trace=trace,mode=mode,physical=physical,launch=launch))
        cases.append(frames)
    assert at==len(data),(at,len(data));return cases


def coverage(cases,records):
    counts=Counter();errors=Counter();branches=Counter();retention=0;partial=0;hashes=set();launch_failures=set()
    for frames,r in zip(cases,records):
        previous=None;hashes.add(hashlib.sha256(json.dumps(frames,sort_keys=True).encode()).hexdigest())
        for frame,row in zip(frames,r['commands']):
            counts[row['op']]+=1;assert len(frame['queue'])<=21
            if not frame['ok']:errors[frame['error']]+=1
            if row['op']==0:
                assert frame['slide'][1:]==[bits(1),0,0,0];assert frame['lifecycle'][:4]==[1,0,0,0];assert all(b[47]==0 for b in frame['bodies']);assert frame['bodies'][6][29:32]==[0,0,0]
                if row['category']!=100:assert frame['manual']==[0]*5
                elif previous:assert frame['manual']==previous['manual']
            elif row['op']==1:assert frame['slide'][1:]==[bits(1),0,0,0] and frame['material']==[bits(.113),bits(.517),bits(.173)]
            elif row['op']==2:
                trace=frame['trace'];assert trace and trace[0]==1
                if not row.get('valid',True):assert trace==[1] and frame['error']=='Slide requires current BoardToolkit'
                elif row.get('fail')==3:assert trace==[1,2,3]
                else:assert trace[:5]==[1,2,3,4,5]
                if frame['ok']:
                    if frame['launch'] is not None:
                        branches['launch']+=1;assert trace==[1,2,3,4,5,6,7,10,11,12,13,14,15];assert all(b[47]==0 and b[26:29]==frame['launch'][:3] for b in frame['bodies']);assert previous is None or frame['queue']==previous['queue']
                    else:
                        assert trace==[1,2,3,4,5,6,7,9] and frame['physical'] is not None
                        added=frame['queue'][len(previous['queue']) if previous else r['preseed']:];tags=[q[0] for q in added]
                        if tags and tags[0]==15:branches['collision']+=1;assert tags==[15]
                        elif tags:branches['ordinary']+=1;assert tags==[4,5,16,9][:len(tags)]
                        else:branches['full_queue']+=1
                        assert frame['physical'][17:21]==[0,bits(1),0,0],frame['physical']
                if previous and previous['retained_collision'] and frame['retained_collision']==previous['retained_collision'] and 9 in trace:retention+=1
                if row.get('manual_error'):
                    assert not frame['ok'] and frame['error']=='Slide manual controller: Angle(IntegerConversionUnavailable)' and trace==[1,2,3,4,5,6,7];assert frame['steering']!=previous['steering'];assert frame['queue']==previous['queue'];partial+=1
                if row.get('fail') in (10,11,12,13,15):
                    launch_failures.add(row['fail']);assert not frame['ok'] and frame['launch'] is not None;assert all(b[47]==0 and b[26:29]==frame['launch'][:3] for b in frame['bodies']);assert frame['queue']==previous['queue'];partial+=1
            previous=frame
    assert len(hashes)==len(records);assert all(branches[key]>0 for key in ('launch','collision','ordinary','full_queue')),branches;assert retention>20;assert partial==6;assert launch_failures=={10,11,12,13,15};assert len(errors)>=11
    return dict(commands_by_type=dict(counts),branches=dict(branches),distinct_histories=len(hashes),retained_collision_through_false=retention,partial_failure_observations=partial,errors=dict(errors),launch_failure_stages=sorted(launch_failures),board_lanes_per_frame=343,capacity=21)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    cases,records=corpus();validate_corpus(cases,records);commands=encode(cases);(output/'input.bin').write_bytes(commands);(output/'cases.json').write_text(json.dumps(records,indent=2)+'\n');reference=build_probe(output,'slide-state-runtime-reference',prepare_source(output),args.target_dir);simulation=build_simulation(output);settings=output/'settings.simulation';settings.write_bytes(converter.encode_settings(args.assets/'private/stock/skater-collections.json'))
    def expected(data):return subprocess.check_output([str(reference),str(args.assets.resolve())],input=data)
    def actual(data):return subprocess.check_output([str(simulation),str(settings)],input=data)
    oracle=expected(commands);candidate=actual(commands);(output/'reference.bin').write_bytes(oracle);(output/'simulation.bin').write_bytes(candidate);frames=decode(oracle,records);(output/'reference-trace.json').write_text(json.dumps(frames,indent=2)+'\n')
    if oracle!=candidate:
        lo=0;hi=len(cases)
        while hi-lo>1:
            mid=(lo+hi)//2
            if expected(encode(cases[lo:mid]))==actual(encode(cases[lo:mid])):lo=mid
            else:hi=mid
        (output/'first-divergence-input.bin').write_bytes(encode(cases[lo:hi]));(output/'first-divergence.json').write_text(json.dumps(dict(case=lo,record=records[lo]),indent=2)+'\n');raise AssertionError(f'Slide runtime differs in case {lo}')
    result=dict(passed=True,cases=len(cases),commands=sum(len(r['commands']) for r in records),coverage=coverage(frames,records),output_bytes=len(oracle),output_sha256=hashlib.sha256(oracle).hexdigest(),comparison='Actual Slide host enter/exit/update/board call order with real core steering/manual/WallRide/Slide/CollisionResponse/deck accumulation and BoardRuntime state/queue.',limitations='Explicit completed Ground inputs and producer result/error boundaries; concrete skeleton/reckoning/trajectory/world generation and Slide post/shared coordinator binding are separate proofs.')
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
