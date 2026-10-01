#!/usr/bin/env python3
"""Complete pinned selector, owned-pointer lifecycle and pre/state/post wrappers.

All numerical/control methods execute unchanged original modules. Mandatory
services record actual arguments; world/state-body/controller producers are
explicit external boundaries, not a proof of the later concrete player owner.
Only the coordinator compiles/runs this through the shared render guard.
"""
import argparse
from collections import Counter,OrderedDict
import copy
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
import player_input_protocol as protocol
import check_animation_trees_parity as trees
from check_animation_playback_parity import Stream as BaseStream
from check_gesture_parity import PLUGIN
from reference_build import build_probe

CORE='crates/skate-core/src/player/'
TYPE_FILES=('selector/conditions.rs','selector/input.rs','selector/mod.rs','lifecycle.rs','pre_state.rs','state_phase.rs')
TYPES={'BoardBodyState','TwoStageThresholds','SkeletonAnimationState','ProcessedStateInput','StateSelectionInput','StateSelector','StateBinding','PlayerStateChangeFields','ProcessedStateChangeFields','SkateboardControllerFields','StateChangeData','StateCall','PreStatePacket','PreStatePlayerFields','PreStateSkeletonFields','StatePhaseFields'}

class Stream(BaseStream):
    def float(self,value):
        if isinstance(value,dict):self.word(value['bits'])
        else:super().float(value)

def declarations():
    defs=OrderedDict();sources={}
    for suffix in TYPE_FILES:
        path=CORE+suffix;source=trees.source_at_reference(path);sources[path]=source
        for m in re.finditer(r'\bstruct (\w+)\s*\{',source):
            if m[1] not in TYPES:continue
            body=re.sub(r'//[^\n]*','',source[m.end():source.index('\n}',m.end())]);defs[m[1]]=[(f,re.sub(r'\s+','',kind)) for f,kind in re.findall(r'^\s*pub\s+(\w+)\s*:\s*([^,\n]+),',body,re.M)]
    assert set(defs)==TYPES and all(defs.values())
    state=trees.source_at_reference(CORE+'state.rs');sources[CORE+'state.rs']=state
    body=state[state.index('pub enum PhysicalStateId {'):state.index('\n}',state.index('pub enum PhysicalStateId {'))];ids=[(name,int(raw)) for name,raw in re.findall(r'(\w+)\s*=\s*(\d+)',body)]
    assert len(ids)==26
    for suffix in ('selector/ground.rs','selector/air.rs','selector/offboard.rs','post_state.rs'):
        sources[CORE+suffix]=trees.source_at_reference(CORE+suffix)
    return defs,sources,ids

def plain(defs):return OrderedDict((name,[(f,k.replace('PhysicalStateId','u32')) for f,k in fields]) for name,fields in defs.items())

def helpers(defs):
    def read(kind,lang):
        a=protocol.array(kind);o=protocol.option(kind)
        if a:
            child=read(a[0],lang)
            return f'i.Array<{protocol.cpp_kind(a[0])},{a[1]}>([](Input& i){{return {child};}})' if lang=='cpp' else f'std::array::from_fn(|_|{child})'
        if o:
            child=read(o,lang)
            return f'i.Optional<{protocol.cpp_kind(o)}>([](Input& i){{return {child};}})' if lang=='cpp' else f'if i.word()!=0 {{Some({child})}} else {{None}}'
        if kind=='PhysicalStateId':return 'PhysicalStateId(i.Word())' if lang=='cpp' else 'PhysicalStateId::try_from(i.word()).unwrap()'
        return protocol.read_expr(kind,lang)
    def observe(kind,expr,lang):
        a=protocol.array(kind);o=protocol.option(kind)
        if a:return f'for(const auto& v:{expr}) {{{observe(a[0],"v",lang)}}}' if lang=='cpp' else f'for v in &{expr} {{{observe(a[0],"*v",lang)}}}'
        if o:return f'o.Word(bool({expr}));if({expr}) {{{observe(o,"*"+expr,lang)}}}' if lang=='cpp' else f'o.word({expr}.is_some() as u32);if let Some(v)=&{expr} {{{observe(o,"*v",lang)}}}'
        if kind=='PhysicalStateId':return f'o.Word(std::uint32_t({expr}));' if lang=='cpp' else f'o.word({expr} as u32);'
        return protocol.observe_expr(kind,expr,lang)
    cpp=[f'void Observe(Output&,const {name}&);{name} Read{name}(Input&);' for name in defs];rust=[]
    for name,fields in defs.items():
        cpp.append(f'void Observe(Output& o,const {name}& s) {{'+''.join(observe(k,'s.'+f,'cpp') for f,k in fields)+'}')
        cpp.append(f'{name} Read{name}(Input& i) {{{name} s;'+''.join('s.'+f+'='+read(k,'cpp')+';' for f,k in fields)+'return s;}')
        rust.append(f'fn observe_{name}(o:&mut Output,s:&{name}) {{'+''.join(observe(k,'s.'+f,'rust') for f,k in fields)+'}')
        rust.append(f'fn read_{name}(i:&mut Input)->{name} {{'+name+'{'+''.join(f+':'+read(k,'rust')+',' for f,k in fields)+'}}')
    return '\n'.join(cpp),'\n'.join(rust)

def base_input():
    return dict(processed=dict(grind_type_1248=0,grind_candidate_1488=False,field_1776=0,flags_2468=0,flags_2472=0,flags_2476=0,flags_2480=0,flags_2484=0,flags_2488=0,category_2512=100,wheel_contact_count_2556=0,field_2572=0,state_timer_2664=.137,field_2732=0.,field_2744=0.,trajectory_collision_time_2772=1.,grind_investigation_flags_1516=0),skateboard_contact_count_869=0,board_body=dict(field_856=0.,field_7692=0.),skeleton=dict(mode_16420=1,back_chain_lane_12656=0.,threshold_800=.5),skitching_off_ground=dict(field_856_primary=1.,field_856_secondary=.5,field_7692=1.),normal_off_ground=dict(field_856_primary=1.,field_856_secondary=.5,field_7692=1.))

def selection(current,**updates):
    value=base_input();value['processed']['category_2512']=(current//100)*100
    for key,item in updates.items():
        if key in value['processed']:value['processed'][key]=item
        else:value[key]=item
    return dict(op=1,current=current,value=value)

def corpus(defs,ids):
    programs=[];values=[raw for _,raw in ids]
    def program(label,commands,initial=100,selector=None):
        s={f:(None if f=='current_state' else False if k=='bool' else 0) for f,k in defs['StateSelector']};s.update(selector or {})
        programs.append(dict(label=label,initial=initial,selector=s,data=protocol.default('StateChangeData',plain(defs),len(programs)),player=dict(frame_counter_1312=0xffffffff,component_1840_present=len(programs)%2==0),skeleton=dict(predicted_position_16112=[0x12345678,2,3,0xdeadbeef],predicted_position_set_16416=False,nested_flag_3184=True),phase=dict(elapsed_1344=.137,timestep_2604=1/60,controller_state_448=2,controller_system_on_452=True),commands=commands))
    for raw in values:
        commands=[selection(raw)]
        for field in ('flags_2468','flags_2472','flags_2476','flags_2480','flags_2484','flags_2488'):
            commands.extend(selection(raw,**{field:1<<bit}) for bit in range(32))
        for gt in range(8):commands.append(selection(raw,grind_candidate_1488=True,grind_type_1248=gt))
        for wheel in (-1,0,1,2,4):
            for board in (0,1,2,3,255):commands.append(selection(raw,wheel_contact_count_2556=wheel,skateboard_contact_count_869=board))
        program('every state/flag lane/grind kind/contact gate',commands,initial=raw)
    # Authored witnesses deliberately reach every concrete output; these are
    # inputs only. Expected results always come from untouched original code.
    witnesses=[selection(100),selection(100,field_2732=.25),selection(100,field_2744=.25),selection(100,skeleton=dict(mode_16420=2,back_chain_lane_12656=0.,threshold_800=.5)),selection(100,flags_2476=0x200000,flags_2480=0x400000),selection(100,field_1776=-2147483648),selection(100,board_body=dict(field_856=2.,field_7692=0.)),selection(100,field_2572=1,flags_2468=0x400),selection(400,flags_2484=0x100000),selection(100,flags_2468=0x40000),*[selection(100,grind_candidate_1488=True,grind_type_1248=t) for t in range(6)],selection(100,flags_2476=0x8000),selection(100,flags_2476=0x80),selection(500,flags_2476=0x200000),selection(100,flags_2480=0x1000),selection(100,flags_2476=1),selection(201,flags_2480=0x2000000),selection(103,flags_2480=0x4000),selection(700),selection(400),selection(100,flags_2468=2)]
    program('all concrete decision witnesses',[dict(op=0,value={f:(None if f=='current_state' else False if k=='bool' else 0) for f,k in defs['StateSelector']}),*witnesses])
    for initial in values:
        commands=[]
        for requested in values:
            commands.extend([dict(op=3,requested=requested,reported=initial),dict(op=3,requested=initial,reported=200 if initial//100!=2 else 100)])
        program('every owned pointer pair and reported-type category edge',commands,initial=initial)
    for on in (False,True):
        for mode in (0,1,2,3,4,0xffffffff):
            for flags in (0,0x80,0x100,0x180,0xffffffff):
                commands=[]
                for requested in (500,501,502,100,300):
                    data=protocol.default('StateChangeData',plain(defs),mode);data['processed']['flags_2480']=flags;data['skateboard_controller']=dict(word_444=0xdeadbeef,state_448=mode,system_on_452=on)
                    commands.extend([dict(op=2,value=data),dict(op=3,requested=requested,reported=400),dict(op=3,requested=requested,reported=requested)])
                program('controller held/free/stopped/repeated entry',commands)
    for counter in (-2147483648,-1,0,1,2,9,10,29,30,59,60,299,300,2147483647):
        seed={f:counter for f,k in defs['StateSelector'] if k=='i32'}
        commands=[selection(701) for _ in range(64)]+[selection(701,wheel_contact_count_2556=1,flags_2484=0x200000) for _ in range(32)]+[selection(104,flags_2476=0x200000),*[selection(100) for _ in range(12)],*[selection(200) for _ in range(304)],selection(200,flags_2468=8),selection(100,field_1776=-1),selection(100,flags_2468=2)]
        program('persistent exact wrapping/countdown/air timeout history',commands,selector=seed)
    boundary_words=[0,0x80000000,1,0x80000001,0x3d23d709,0x3d23d70a,0x3d23d70b,0x3d4ccccc,0x3d4ccccd,0x3d4cccce,0x3da3d709,0x3da3d70a,0x3da3d70b,0x3e4ccccc,0x3e4ccccd,0x3e4cccce,0xbe4ccccc,0xbe4ccccd,0xbe4cccce,0x7f800000,0xff800000,0x7fc00001,0xffc12345]
    for word in boundary_words:
        f=dict(bits=word);commands=[]
        for current in (100,101,102,103,104,200,201,600,701):
            for field in ('state_timer_2664','trajectory_collision_time_2772','field_2732','field_2744'):
                commands.append(selection(current,**{field:f},wheel_contact_count_2556=1,grind_candidate_1488=True))
            for mode in (0,1,2,3):commands.append(selection(current,skeleton=dict(mode_16420=mode,back_chain_lane_12656=f,threshold_800=.5),board_body=dict(field_856=f,field_7692=f)))
        program('strict boundary and IEEE predicate observations',commands)
    rng=random.Random(46513);commands=[]
    for _ in range(512):
        current=rng.choice(values);item=selection(current);p=item['value']['processed']
        for field in ('flags_2468','flags_2472','flags_2476','flags_2480','flags_2484','flags_2488'):p[field]=rng.getrandbits(32)
        p.update(grind_type_1248=rng.randrange(8),grind_candidate_1488=bool(rng.randrange(2)),field_1776=rng.getrandbits(32)-0x80000000,wheel_contact_count_2556=rng.randrange(-1,5),state_timer_2664=rng.uniform(-.25,.75));item['value']['skateboard_contact_count_869']=rng.randrange(5);commands.append(item)
    program('generated overlapping priority inputs',commands)
    for raw in (0,99,106,199,203,399,406,499,504,603,699,703,0xffffffff):program('unknown rejects before any write or callback',[selection(raw),dict(op=3,requested=raw,reported=201)])
    commands=[]
    for present in (False,True):
        for count in (0,1,0x7fffffff,0xffffffff):
            commands.extend([dict(op=8,player=dict(frame_counter_1312=count,component_1840_present=present),skeleton=dict(predicted_position_16112=[9,8,7,6],predicted_position_set_16416=False,nested_flag_3184=True)),dict(op=4,value=dict(words=[rng.getrandbits(32) for _ in range(18)])),dict(op=4,value=dict(words=[rng.getrandbits(32) for _ in range(18)])),dict(op=7)])
    for elapsed in (0.,-.0,.137,dict(bits=0x7fc12345),dict(bits=0x7f800000)):
        commands.append(dict(op=6,value=dict(elapsed_1344=elapsed,timestep_2604=0.,controller_state_448=0,controller_system_on_452=False)))
        for on in (False,True):
            for mode in (0,1,2,3,4,7,0xffffffff):
                for dt in (0.,1/60,-.125,dict(bits=0x7fc00001)):commands.append(dict(op=5,timestep=dt,mode=mode,on=on))
    program('complete wrapper calls/packet/phase accumulation',commands)
    commands=[]
    arithmetic_words=(0,0x80000000,1,0x80000001,0x3f800000,0xbf800000,0x7f800000,0xff800000,
        0x7fc00001,0xffc12345,0x7fc12345,0x7f800001,0xff800001,0x7fa12345,0xffa54321)
    for elapsed in arithmetic_words:
        for timestep in arithmetic_words:
            commands.extend([dict(op=6,value=dict(elapsed_1344=dict(bits=elapsed),timestep_2604=0.,controller_state_448=0,controller_system_on_452=False)),
                dict(op=5,timestep=dict(bits=timestep),mode=0,on=False)])
    program('independent elapsed/timestep IEEE operand ordering and signaling payloads',commands)
    return programs

def encode(cases,defs):
    w=Stream();d=plain(defs);w.word(len(cases))
    for c in cases:
        protocol.encode(w,'StateSelector',c['selector'],d);w.word(c['initial'])
        for kind,key in (('StateChangeData','data'),('PreStatePlayerFields','player'),('PreStateSkeletonFields','skeleton'),('StatePhaseFields','phase')):protocol.encode(w,kind,c[key],d)
        w.word(len(c['commands']))
        for s in c['commands']:
            op=s['op'];w.word(op)
            if op in (0,2,4,6):protocol.encode(w,{0:'StateSelector',2:'StateChangeData',4:'PreStatePacket',6:'StatePhaseFields'}[op],s['value'],d)
            elif op==1:w.word(s['current']);protocol.encode(w,'StateSelectionInput',s['value'],d)
            elif op==3:w.word(s['requested']);w.word(s['reported'])
            elif op==5:w.float(s['timestep']);w.word(s['mode']);w.word(s['on'])
            elif op==8:protocol.encode(w,'PreStatePlayerFields',s['player'],d);protocol.encode(w,'PreStateSkeletonFields',s['skeleton'],d)
    return bytes(w.data)

def snapshot(r,defs):return dict(selector=r.value('StateSelector',defs),active=r.value('StateBinding',defs),data=r.value('StateChangeData',defs),player=r.value('PreStatePlayerFields',defs),skeleton=r.value('PreStateSkeletonFields',defs),phase=r.value('StatePhaseFields',defs))

def decode(data,cases,defs):
    r=protocol.Reader(data);d=plain(defs);catalog=[]
    for _ in range(r.word()):catalog.append(dict(id=r.word(),offset=r.word(),category=r.word(),grind=r.word(),name=r.string()))
    programs=[]
    for ci,c in enumerate(cases):
        assert r.word()==ci;initial=snapshot(r,d);rows=[]
        for n,command in enumerate(c['commands']):
            assert [r.word(),r.word(),r.word()]==[ci,n,command['op']];ok=r.word();result=r.word();unknown=r.word();trace=[r.word() for _ in range(r.word())];rows.append(dict(ok=ok,result=result,unknown=unknown,trace=trace,snapshot=snapshot(r,d)))
        programs.append(dict(initial=initial,rows=rows))
    assert r.at==len(data)
    return catalog,programs

def coverage(catalog,frames,cases,ids):
    values={raw for _,raw in ids};assert [s['id'] for s in catalog]==[raw for _,raw in ids];assert len({s['offset'] for s in catalog})==26
    counts=Counter();selected=set();pairs=set();predicate=[set(),set(),set()];controller=set();phase_modes=set();unknowns=0;wraps=0;teleports=0;reverts=0;pre=0;post=0;reported_edges=0
    for frame,c in zip(frames,cases):
        previous=frame['initial']
        for row,command in zip(frame['rows'],c['commands']):
            op=command['op'];counts[op]+=1;s=row['snapshot'];trace=row['trace']
            if op==1:
                for group,v in zip(predicate,trace):group.add(v)
                if not row['ok']:assert command['current'] not in values and row['unknown']==command['current'] and s==previous;unknowns+=1
                else:
                    selected.add(row['result']);assert s['selector']['current_state']==command['current'];teleports+=s['selector']['request_teleport'];reverts+=s['selector']['revert_exited_normally'];wraps+=any(previous['selector'][f]==0x7fffffff and s['selector'][f]==0x80000000 for f in ('air_frames','two_wheel_counter','three_wheel_counter','post_grind_jump_counter','something_colliding_frames','nonspecific_collision_free_frames','nonspecific_collision_frames'))
            elif op==3:
                if not row['ok']:assert command['requested'] not in values and row['unknown']==command['requested'] and s==previous and not trace;unknowns+=1
                else:
                    old=previous['active'];new=s['active'];pairs.add((old['state'],new['state']));controller.update(v for v in trace[:1] if v in (1,2));call=trace[1:] if trace[0] in (1,2) else trace
                    assert call==[3,old['state'],old['owner_offset'],4,old['state'],old['owner_offset'],old['state'],old['owner_offset'],5,new['state'],new['owner_offset'],new['state'],new['owner_offset']]
                    assert new['state']==command['requested'] and s['data']['processed']['previous_state_2504']==command['reported'];reported_edges+=command['reported']!=old['state']
                    assert s['data']['player']['word_1312']==0 and s['data']['processed']['word_2564']==0 and s['data']['player']['scalar_1344']==0 and s['data']['processed']['scalar_2664']==0
            elif op==4:
                expected=[10,*([0]*18),*([11] if previous['player']['component_1840_present'] else []),12];assert trace==expected and s['skeleton']['predicted_position_16112']==command['value']['words'][12:16];assert s['player']['frame_counter_1312']==(previous['player']['frame_counter_1312']+1)&0xffffffff;assert s['skeleton']['predicted_position_set_16416']==1 and s['skeleton']['nested_flag_3184']==0;pre+=1
            elif op==5:
                expected=[20]
                if command['on']:
                    expected.append(21)
                    if command['mode'] in (1,2,3,4):expected.append(21+command['mode']);phase_modes.add(command['mode'])
                expected.extend([26,27,28]);assert trace==expected
            elif op==7:assert trace==[30];post+=1
            previous=s
    assert set(counts)=={0,1,2,3,4,5,6,7,8},counts
    assert selected==values,(selected,values-selected)
    assert pairs=={(a,b) for a in values for b in values},len(pairs)
    assert predicate==[{0,1}]*3 and controller=={1,2} and phase_modes=={1,2,3,4}
    assert unknowns==26 and wraps>0 and teleports>0 and reverts>0 and pre==16 and post==8 and reported_edges>0,(unknowns,wraps,teleports,reverts,pre,post,reported_edges)
    return dict(opcodes=dict(counts),selected_states=sorted(selected),lifecycle_pairs=len(pairs),predicate_values=[sorted(v) for v in predicate],controller_actions=sorted(controller),controller_phase_modes=sorted(phase_modes),unknown_rejections=unknowns,counter_wrap_observations=wraps,air_timeout_requests=teleports,revert_exits=reverts,pre_state_calls=pre,post_state_calls=post,reported_type_edges=reported_edges)

def prepare_sources(output,defs,sources):
    cpp,rust=helpers(defs);c=output/'player-state-native.cpp';r=output/'player-state-reference.rs';c.write_text((PLUGIN/'Tests/Native/player_state_probe.cpp').read_text().replace('// GENERATED_PROTOCOL',cpp));r.write_text((PLUGIN/'Tests/Reference/player_state_probe.rs').read_text().replace('// GENERATED_PROTOCOL',rust));(output/'source-provenance.json').write_text(json.dumps(dict(original_modules={p:hashlib.sha256(s.encode()).hexdigest() for p,s in sources.items()},boundary='Required services supply completed external state/controller observations only; all selector/lifecycle/wrapper methods execute untouched original core modules.'),indent=2)+'\n');return c,r

def build_native(output,probe):
    n=PLUGIN/'Source/AtelierSkate/Private/Native';snapshot_dir=output/'native-source';snapshot_dir.mkdir(exist_ok=True);sources=['PhysicalPhase','PlayerStateMachine','PlayerStateSelector','PlayerStateLifecycle'];files=[*n.glob('*.h'),*(n/(s+'.cpp') for s in sources)];provenance={}
    for p in files:raw=p.read_bytes();(snapshot_dir/p.name).write_bytes(raw);provenance[p.name]=hashlib.sha256(raw).hexdigest()
    shutil.copy2(probe,snapshot_dir/probe.name);binary=output/'player-state-native';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot_dir),*[str(snapshot_dir/(s+'.cpp')) for s in sources],str(snapshot_dir/probe.name),'-o',str(binary)],check=True);(output/'native-source-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return binary

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);a=p.parse_args();output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    defs,sources,ids=declarations();cases=corpus(defs,ids);blob=encode(cases,defs);(output/'input.bin').write_bytes(blob);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');cpp,rust=prepare_sources(output,defs,sources);reference=build_probe(output,'player-state-reference',rust,a.target_dir);native=build_native(output,cpp);expected=subprocess.check_output([str(reference)],input=blob);actual=subprocess.check_output([str(native)],input=blob);(output/'reference.bin').write_bytes(expected);(output/'native.bin').write_bytes(actual);catalog,frames=decode(expected,cases,defs)
    if expected!=actual:
        at=next((i for i,(x,y) in enumerate(zip(expected,actual)) if x!=y),min(len(expected),len(actual)));(output/'first-divergence.json').write_text(json.dumps(dict(byte=at),indent=2)+'\n');raise AssertionError(f'Physical state core differs at byte {at}')
    proof=coverage(catalog,frames,cases,ids);result=dict(passed=True,programs=len(cases),commands=sum(len(c['commands']) for c in cases),output_bytes=len(expected),output_sha256=hashlib.sha256(expected).hexdigest(),coverage=proof,comparison='Whole unchanged core player state identities/selector predicates and decision tree/lifecycle/PreState/State/PostState.',limitations='Mandatory state bodies, controller physical operations, world producers and actual active host/global-frame scheduling remain explicit external boundaries. No concrete player-owner proof is claimed.');(output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()
