#!/usr/bin/env python3
"""Complete canonical core input phase with frozen host initial/reset modules.

Tests explicit mandatory-service results and traces every source argument. This
proves scheduling/composition; concrete physical/skeleton/world services remain
separate owners. Only the coordinator may compile/run through the shared guard.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import player_input_protocol as protocol
import check_animation_trees_parity as trees
from check_animation_playback_parity import Stream,bits
from check_gesture_parity import PLUGIN,converter
from reference_build import build_probe

HOST='crates/skate-host/src/physics/player_input/'
FRAME_FIELDS=[('fail','u32'),('manager','u32'),('pre_state','u32'),('pre_category','u32'),('teleport','u32'),('teleport_state','u32'),('teleport_category','u32'),('query56','u32'),('query44','u32'),('available','bool'),('transition','f32'),('position','RawVector'),('body_speed','f32'),('skeleton_a','u32'),('skeleton_b','u32'),('skeleton_c','u32'),('spin','f32'),('crouch','f32'),('grind','[u32;2]')]

def source_player(defs,seed=0):
    p=protocol.default('PlayerInputState',defs,seed);p.update(flags_1296=0xe00c0000|0x00120000,ground_history_frames_1304=100,manager_1856_counter_320=0,state_count_1312=6,grounded_frames_1300=5,frames_since_teleport_1328=4,spin_same_direction_frames_1324=0xffffffff)
    p['state_variants_1408']=[dict(surface_override_enabled_60=x) for x in (0,1,2,255,1)];return p

def physical(defs,tick=0,category=100):
    f=protocol.default('PhysicalPlayerInput',defs,tick);f['state'].update(category_12=category,state_16=(100,104,300,500)[tick%4],identifier_8=0x12340000+tick,signed_ground_step_84=tick%2,skitch_value_40=123+tick);f['collision'].update(wheel_count_0=4,wheel_contact_3296_3299=[0,1,2,255]);f['skateboard'].update(vector_80=[bits(v) for v in (.137,.317,2+tick*.25,.731)],vector_96=[bits(v) for v in (tick*.125,.25,2+tick*.5,.517)],scalar_160=(.05,.25,-.05)[tick%3]);f['ground'].update(scalar_276=(0,-.125,.25)[tick%3],scalar_292=(0,.125,.5)[tick%3],scalar_296=(0,.125,.5)[(tick+1)%3]);f['off_board']['scalar_32']=(0,-.125,.25)[tick%3];return f

def packet(defs,tick=0,mode=1):
    p=protocol.default('AnimationInputPacket',defs,tick);p.update(state_variant_10928=mode,suppress_transition_10376=0,use_external_physics_10688=tick%2,force_braking_10796=1,flags_10932=(0,0xffffffff,0xc0400000)[tick%3]);p['publication'].update(timestep=(1/60,.033,.003)[tick%3],stance_byte=tick%2,flag_10371=(tick//2)%2,flags_10375_10496_10784=[1,2,255]);p['external_physics_10512']['flags']=(0x0c000000,0x08000000,0xffffffff)[tick%3];return p

def frame(tick=0,fail=0):
    return dict(fail=fail,manager=0,pre_state=333,pre_category=100,teleport=0,teleport_state=500,teleport_category=500,query56=0xabcdef01+tick,query44=0xffffffff-tick,available=True,transition=(-1.5,-1,0,.731,1.5)[tick%5],position=[bits(v) for v in (tick*.137,.317,1+tick*.731,.517)],body_speed=3+tick*.5,skeleton_a=(1<<21 if tick%2 else 0),skeleton_b=(1<<23)|(1<<21),skeleton_c=1<<22,spin=(-.5,.5,0)[tick%3],crouch=(.5,-.5,0)[tick%3],grind=[tick%6,tick%4])

def command(defs,tick=0,category=100,mode=1,op=0,fail=0):return dict(op=op,tick=tick,physical=physical(defs,tick,category),packet=packet(defs,tick,mode),frame=frame(tick,fail))

def corpus(defs):
    cases=[]
    def add(label,commands,seed=0):cases.append(dict(label=label,player=source_player(defs,seed),physical=physical(defs),processed=protocol.default('ProcessedPhysicsInput',defs,seed),commands=commands));return cases[-1]
    for mode in range(5):
        for category in (100,200,500,600,300):
            commands=[command(defs,t,category,mode) for t in range(8)];commands.insert(3,dict(op=3));commands.insert(7,dict(op=4));add('persistent category/mode history',commands,mode)
    for switched in (0,1):
        for wheel in range(16):
            c=command(defs,0);c['packet']['publication']['flag_10371']=switched;c['physical']['collision']['wheel_contact_3296_3299']=[255 if wheel&(1<<i) else 0 for i in range(4)];add('wheel pairs and stance',[c])
    for enabled in (0,1):
        for requested in (0,1,2,3,4,5,6,7,13,0xffffffff):
            c=command(defs);c['physical']['surface_default_mode']=requested;case=add('surface normalization',[c]);case['player']['state_variants_1408'][1]['surface_override_enabled_60']=enabled
    for fail in range(1,14):add('failure prefix',[command(defs,fail=fail)])
    for variant in (5,99,0xffffffff):add('invalid state variant retains previous completion',[command(defs),command(defs,1,mode=variant),dict(op=3)])
    for initial in (0,1,0x7fffffff,0x80000000,0x80000001,0xffffffff):
        case=add('wrapping counters',[command(defs,t) for t in range(3)]);case['player'].update(manager_1856_counter_320=initial,grounded_frames_1300=initial,frames_since_teleport_1328=initial,state_count_1312=initial)
    for available in (False,True):
        for suppress in (0,1,2,255):
            c=command(defs);c['frame']['available']=available;c['packet']['suppress_transition_10376']=suppress;add('transition availability and full byte suppression',[c])
    for value in (-0.,-1.,1.,1.0000001192092896,float('nan'),float('inf'),float('-inf')):
        c=command(defs);c['frame']['transition']=value;add('transition IEEE boundary',[c])
    for prior_category in (100,200,500,600):
        for new_category in (100,500):
            c=command(defs,category=prior_category);c['frame'].update(manager=1,pre_state=104,pre_category=prior_category,teleport=1,teleport_state=600,teleport_category=new_category);add('captured observations survive teleport',[c,dict(op=3)])
            start=command(defs,category=prior_category,op=1);start['frame'].update(manager=1,pre_state=104,pre_category=prior_category);finish=command(defs,1,category=new_category,op=2);add('split continuation across released borrows',[start,finish,dict(op=3)])
    for dt in (0.,-0.,.0000000001,-.125,.033):
        c=command(defs,2);c['packet']['publication']['timestep']=dt;add('ground-history dt boundary',[c,dict(op=3)])
    for flipped in (False,True):
        for x in (-1,-0.,0.,1,.137,.317,.731,1.973):
            for z in (-1,-0.,0.,1):add('deck-angle exact zero/quadrants',[dict(op=5,forward=[x,.317,z,.731],flipped=flipped)])
    for across in ((1,0,0,0),(0,0,1,.731),(0,0,0,0),(1e-19,.125,0,.731),(-1,.125,.317,-.731)):
        for forward in ((0,0,1,0),(1,0,0,0),(0,1,0,0),(-1,.125,-.317,.731)):
            add('completed physical twist wrap',[dict(op=6,left=[.137,.317,.731,.517],right=[.137+across[0],.317+across[1],.731+across[2],.517+across[3]],forward=list(forward),up=[0,1,0,0])])
    add('external reset names and option identity',[dict(op=7,grind=None,surface=None),dict(op=7,grind=[1,2,3,4,5],surface=[5,4,3,2,1]),dict(op=7,grind=None,surface=[0]*5)])
    return cases

def encode(cases,defs):
    w=Stream();w.word(len(cases))
    for case in cases:
        for name,key in [('PlayerInputState','player'),('PhysicalPlayerInput','physical'),('ProcessedPhysicsInput','processed')]:protocol.encode(w,name,case[key],defs)
        w.word(len(case['commands']))
        for c in case['commands']:
            op=c['op'];w.word(op)
            if op<=2:
                w.wide(c['tick']);protocol.encode(w,'PhysicalPlayerInput',c['physical'],defs);protocol.encode(w,'AnimationInputPacket',c['packet'],defs)
                for name,kind in FRAME_FIELDS:protocol.encode(w,kind,c['frame'][name],defs)
            elif op==5:
                for v in c['forward']:w.float(v)
                w.word(c['flipped'])
            elif op==6:
                for key in ('left','right','forward','up'):
                    for v in c[key]:w.float(v)
            elif op==7:
                for key in ('grind','surface'):protocol.encode(w,'Option<AttributeName>',c[key],defs)
    return bytes(w.data)


def decode(data,cases,defs):
    r=protocol.Reader(data);frames=[]
    for ci,case in enumerate(cases):
        assert r.word()==ci;initial=r.value('PlayerInputState',defs);rows=[]
        for n,c in enumerate(case['commands']):
            assert [r.word(),r.word(),r.word()]==[ci,n,c['op']];row=dict(ok=r.word(),kind=r.word(),variant=r.word(),error=r.string());end=r.at+4+r.word()*4
            row['player']=r.value('PlayerInputState',defs);row['physical']=r.value('PhysicalPlayerInput',defs);row['processed']=r.value('ProcessedPhysicsInput',defs);row['continuation']=r.word();row['completed']=dict(tick=r.wide(),input=r.value('ProcessedPhysicsInput',defs)) if r.word() else None;row['calls']=r.word();trace_end=r.at+4+r.word()*4;events=[]
            while r.at<trace_end:
                event_end=r.at+4+r.word()*4;event=dict(id=r.word());mask=r.word()
                for bit,kind in [(1,'PlayerInputState'),(2,'PhysicalPlayerInput'),(4,'ProcessedPhysicsInput'),(8,'AnimationInputPacket')]:
                    if mask&bit:event[kind]=r.value(kind,defs)
                assert r.at==event_end;events.append(event)
            assert r.at==trace_end==end;row['events']=events;rows.append(row)
        frames.append(dict(initial=initial,rows=rows))
    assert r.at==len(data);return frames


def coverage(frames,cases):
    services=Counter();opcodes=Counter();errors=Counter();surfaces=set();states=set();categories=set();completed=0;immutable=0;captures=0;partial=0;failures=[];deck=set();twist=set();external=set();wheel=set()
    for frame,case in zip(frames,cases):
        initial=frame['initial'];assert initial['flags_1296']==0xe00c0000 and initial['ground_history_frames_1304']==100 and initial['external_physics_cache_1008']['vectors'][8]==[0xbf800000]*4
        previous_complete=None
        for row,c in zip(frame['rows'],case['commands']):
            opcodes[c['op']]+=1;services.update(e['id'] for e in row['events']);o=row['processed'];f=row['physical'];surfaces.add(o['surface_mode_2540']);states.add(o['state_2504']);categories.add(o['category_2516']);deck.add(f['skeleton']['deck_yaw_536']);twist.add(f['skeleton']['twist_504']);external.add(o['external_physics_1616']['flags']);wheel.add((o['flags_2472']>>24)&15)
            if row['completed']:
                completed+=1
                if c['op']==3:assert row['completed']==previous_complete;immutable+=row['completed']['input']!=o
                if c['op'] in (0,2) and row['ok']:assert row['completed']==dict(tick=c['tick'],input=o)
            if not row['ok']:errors[row['kind']]+=1
            if case['label']=='captured observations survive teleport' and c['op']==0:
                assert row['ok'] and o['state_2504']==c['physical']['state']['state_16'] and o['category_2516']==c['frame']['teleport_category'];captures+=1
            if case['label']=='split continuation across released borrows' and c['op']==2:
                first=case['commands'][0];assert o['state_2504']==first['physical']['state']['state_16'] and o['category_2516']==c['physical']['state']['category_12'];captures+=1
            if case['label']=='failure prefix':failures.append(row)
            previous_complete=row['completed']
    full=next(r for r in failures if r['ok'] and r['calls']==12);assert full['ok'] and full['calls']==12
    failed=[r for r in failures if not r['ok']];assert {r['calls'] for r in failed}==set(range(1,13))
    for r in failed:
        assert r['events']==full['events'][:r['calls']]
        if r['player']!=failed[0]['player'] or r['processed']!=failed[0]['processed']:partial+=1
    assert set(services)==set(range(1,13)) and set(opcodes)==set(range(8)) and surfaces>={1,2,3,4,5}
    assert errors[1]>0 and errors[2]>0 and completed>0 and immutable>0 and captures==16 and partial>0
    # Four wheel-pair ORs have ten realizable masks: diagonal pairs produce
    # the same full mask. All sixteen authored contact combinations still run.
    assert len(deck)>16 and len(twist)>4 and len(external)>2 and wheel>={0,5,6,7,9,10,11,13,14,15},(len(deck),len(twist),len(external),wheel)
    return dict(required_services=dict(services),opcodes=dict(opcodes),failure_kinds=dict(errors),surface_modes=sorted(surfaces),completed_snapshots=completed,immutable_snapshots_after_reset=immutable,captured_teleport_split_proofs=captures,partial_write_failures=partial,distinct_deck_angles=len(deck),distinct_physical_twists=len(twist),wheel_pair_masks=sorted(wheel),external_flag_words=sorted(external))


def prepare_sources(output,defs,sources):
    cpp,rust=protocol.helpers(defs);c=output/'player-input-phase-native.cpp';r=output/'player-input-phase-reference.rs';c.write_text((PLUGIN/'Tests/Native/player_input_phase_probe.cpp').read_text().replace('// GENERATED_PROTOCOL',cpp));body=(PLUGIN/'Tests/Reference/player_input_phase_probe.rs').read_text().replace('// GENERATED_PROTOCOL',rust);records={}
    for marker,path in [('ORIGINAL_INITIAL','initial.rs'),('ORIGINAL_RESET','reset.rs'),('ORIGINAL_OUTPUT_RESET','output_reset.rs')]:
        source=trees.source_at_reference(HOST+path);body=body.replace('// '+marker,source);records[HOST+path]=hashlib.sha256(source.encode()).hexdigest()
    r.write_text(body);(output/'source-provenance.json').write_text(json.dumps(dict(host_modules=records,declaration_modules={p:hashlib.sha256(s.encode()).hexdigest() for p,s in sources.items()},expected_methods='Full unchanged original player::input_phase runtime/publication/motion_math and pose/grind output methods; callback data and mutations are explicit supplied subsystem boundaries.'),indent=2)+'\n');return c,r


def build_native(output,probe):
    live=PLUGIN/'Source/AtelierSkate/Private/Native';n=output/'native-source';binary=output/'player-input-phase-native';sources=['NameId','Settings','StockSettingsReader','NativeMath','AnimationName','Input','InputIntentions','WipeoutOrientation','SkeletonPhysicalRecord','PlayerInputTypes','PlayerInputPhase']
    if n.exists():shutil.rmtree(n)
    n.mkdir()
    for path in list(live.glob('*.h'))+[live/(s+'.cpp') for s in sources]:shutil.copy2(path,n/path.name)
    copied_probe=n/probe.name;shutil.copy2(probe,copied_probe)
    (output/'native-provenance.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(n.iterdir())},indent=2)+'\n')
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(n),*[str(n/(s+'.cpp')) for s in sources],str(copied_probe),'-o',str(binary)],check=True);return binary


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);a=p.parse_args();output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    defs,sources=protocol.declarations();cases=corpus(defs);blob=encode(cases,defs);(output/'input.bin').write_bytes(blob);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');cpp,rust=prepare_sources(output,defs,sources);reference=build_probe(output,'player-input-phase-reference',rust,a.target_dir);native=build_native(output,cpp);settings=output/'settings.native';settings.write_bytes(converter.encode_settings(a.assets/'private/stock/skater-collections.json'));expected=subprocess.check_output([str(reference),str(a.assets.resolve())],input=blob);actual=subprocess.check_output([str(native),str(settings)],input=blob);(output/'reference.bin').write_bytes(expected);(output/'native.bin').write_bytes(actual);frames=decode(expected,cases,defs);(output/'reference-trace.json').write_text(json.dumps(frames,indent=2)+'\n')
    if expected!=actual:
        at=next((i for i,(x,y) in enumerate(zip(expected,actual)) if x!=y),min(len(expected),len(actual)));(output/'first-divergence.json').write_text(json.dumps(dict(byte=at),indent=2)+'\n');raise AssertionError(f'Complete canonical input phase differs at byte {at}')
    result=dict(passed=True,histories=len(cases),commands=sum(len(c['commands']) for c in cases),output_bytes=len(expected),output_sha256=hashlib.sha256(expected).hexdigest(),coverage=coverage(frames,cases),comparison='Entire unchanged canonical core input phase, actual host stock initialization/selective reset/output reset, completed snapshot copies and pose/grind output leaves.',limitations='Mandatory world/toolkit/skeleton/grind services use explicit supplied observations/mutations; this proves their original ordering and arguments, not the separate concrete physical producers. Overall Skeleton::ProcessData/FootIK/GroundInput bindings remain other owner comparisons.');(output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()
