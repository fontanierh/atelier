#!/usr/bin/env python3
"""Whole unchanged animation_phase.rs over the sole canonical live owners.

Root alone builds/runs under the render lock. --preflight only stages source,
transport and corpus. The six Action physical-condition families use the same live host member
published by the full phase; direct and controller callbacks observe it.
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
import check_state_conditioning_runtime_parity as conditioning
import check_skater_animation_complete_parity as facade
import check_animation_phase_input_parity as packet
import player_input_protocol as protocol
from check_graph_parity import attribute,element,original_graph
from session_parity import digest
PLUGIN=conditioning.PLUGIN;CODE=conditioning.CODE;TESTS=PLUGIN/'Tests';HOST=conditioning.HOST
UNITS=tuple(dict.fromkeys((*conditioning.UNITS,*facade.UNITS,'PlayerStateRuntime','AnimationFeedbackRuntime','AnimationPhaseRuntime','GraphActionPhysicalConditions','AnimationPhaseInput','OffboardSettings','OffboardController','AnimationPhaseInput','TeleportStateRuntime')))
BLOCKS=('shared','conditioning','actor','publication')
QUERIES=facade.QUERIES

def block(raw,marker):return conditioning.grind.block(raw,marker)
def append(path,text):path.write_bytes(path.read_bytes()+text.encode())

def actor_helpers():
    simulation=(TESTS/'Simulation/skater_animation_probe.cpp').read_text();simulation=simulation[:simulation.index('int main(')]
    cpp_body='\n'.join(line for line in simulation.splitlines()if not line.startswith('#include'))+'\n'
    includes='\n'.join(line for line in simulation.splitlines()if line.startswith('#include'))+'\n'
    complete=block((TESTS/'Simulation/skater_animation_complete_probe.cpp').read_text(),'void CompleteSnapshot(')
    cpp=includes+'namespace phase_actor_wire {\n'+cpp_body+complete+'\n}\n'
    rust=(TESTS/'Reference/skater_animation_probe.rs').read_text();rust=rust[:rust.index('fn run()')]
    lines=[line for line in rust.splitlines()if not(line.startswith('//!')or line.startswith('#!')or line.startswith('mod ')or line.startswith('pub use physics::'))]
    rbody='\n'.join(lines)+'\n';complete_r=block((TESTS/'Reference/skater_animation_complete_probe.rs').read_text(),'fn complete_snapshot(')
    wrapper='\npub(crate)fn observe(actor:&SkaterAnimation,reset:&AdditionalResetFields)->Vec<u8>{let mut out=Output(Vec::new(),true,true);let names:Vec<String>=QUERIES.iter().map(|n|(*n).to_string()).collect();complete_snapshot(&mut out,actor,reset,&names);out.0}\n'
    rust='\nmod phase_actor_wire {\nuse crate::{physics,graph_host,graph_runtime,skater_animation};\n'+rbody+complete_r+'\nconst QUERIES:&[&str]=&'+json.dumps(QUERIES)+';'+wrapper+'}\n'
    report=dict(simulation_facade_prefix_sha256=hashlib.sha256(simulation.encode()).hexdigest(),simulation_complete_snapshot_sha256=hashlib.sha256(complete.encode()).hexdigest(),rust_facade_prefix_sha256=hashlib.sha256((TESTS/'Reference/skater_animation_probe.rs').read_text().split('fn run()')[0].encode()).hexdigest(),rust_complete_snapshot_sha256=hashlib.sha256(complete_r.encode()).hexdigest(),scope='Read-only complete actor observation methods copied byte-identically; only includes/module declarations are relocated to avoid collisions with the physical transport types. No callbacks/factories/numeric body changes.')
    return cpp,rust,report

# Each tuple is one actual retained producer record. Types drive ONLY read-only
# observation; field mappings are explicit and hashes included in provenance.
RECORDS=[
 ('manual_exit','h.physical.manual_exit','h.manual_exit',[('','', 'w')]),
 ('yaw_pitch','h.deck_yaw_pitch','h.deck_yaw_pitch',[('','', 'v2')]),
 ('cadence','cp.offboard_cadence_phase','h.offboard_cadence_phase',[('','', 'f')]),
 ('locomotion','h.physical.offboard_locomotion_state','h.offboard_locomotion_state',[('','', 'w')]),
 ('slope','h.physical.ground_slope_type','h.ground_slope_type',[('','', 'w')]),
 ('thin','h.physical.biped_ground_thin','h.biped_ground_thin',[('','', 'w')]),
 ('holding','h.physical.holding_board','h.holding_board',[('','', 'w')]),
 ('free','h.physical.free_board','h.free_board',[('','', 'w')]),
 ('action_dropping','action.dropping_in','s.animation.action.dropping_in',[('','', 'w')]),
 ('action_state','a.action.condition_inputs.physics_requests_dismount','s.animation.action.physical_conditions',[('','requests_dismount','w'),('a.action.condition_inputs.physical_state_16.value()','state','outsidew')]),
 ('bump','cp.bump_acceleration','h.bump_acceleration',[('','', 'v4')]),
 ('runout','cp.runout','h.runout_physical',[('offboard_flag_331','offboard_flag_331','w'),('offboard_velocity_128','offboard_velocity_128','v4'),('reckoning_velocity_16','reckoning_velocity_16','v4'),('reckoning_up_96','reckoning_up_96','v4'),('skeleton_vector_0','skeleton_vector_0','v4'),('animation_mirrored','animation_mirrored','w')]),
 ('toggle','cp.toggle_board','h.toggle_board_physical',[(n,n,t)for n,t in [('grabbing_object','w'),('holding_board','w'),('free_board','w'),('retrieval_blocked','w'),('retrieval_active','w'),('yaw_radians','f'),('pitch_radians','f')]]),
 ('landing','h.landing_inputs','h.landing_physical',[(n,n,t)for n,t in [('height','f'),('spin','f'),('kind','w'),('last_good_landing_velocity','f')]]),
 ('prelanding','h.prelanding_inputs','h.prelanding_physical',[(n,n,t)for n,t in [('air_444','w'),('air_normal_144_y','f'),('animation_16_x','f'),('com_velocity_y','f'),('offboard_316','w'),('offboard_319','w'),('offboard_time_32','f'),('air_437','w'),('air_normal_36','f'),('air_remaining_184','f'),('animation_height_72','f')]]),
 ('air_leg','cp.air_leg','h.air_leg_physical',[(n,n,t)for n,t in [('com_velocity','v4'),('com_position','v4'),('system_up','v4'),('right_toe','v4'),('left_toe','v4'),('animation_height','f'),('offboard_316','w'),('remaining_air_time','f')]]),
 ('simulation_velocity','cp.landing_velocity','h.native_physical',[('com_velocity','centre_of_mass_velocity','v4'),('system_up','system_up','v4'),('h.reckoning_z.value()','board_reckoning_z','outside4'),('h.reckoning_ground.value()','board_reckoning','outside16')]),
 ('shove','h.shove_physical','h.shove_physical',[(n,n,t)for n,t in [('interaction_trigger','w'),('direction','v4'),('in_biped_category','w'),('board_on_ground','w'),('animation_height','f')]]),
 ('riding','h.riding_condition_inputs','h.riding_conditions',[(n,n,t)for n,t in [('com_velocity','v4'),('skeleton_x','v4'),('skeleton_z','v4'),('skate_up_y','f'),('surface_up_y','f')]]),
]
GAMEPLAY=[(n,t)for n,t in [('state','w'),('wants_runout','w'),('physics_wiping','w'),('body_flipping','w'),('wants_wipeout','w'),('bumped','w'),('grabbing_object','w'),('retrieving_board','w'),('dropping_board','w'),('in_biped_air','w'),('hippy_hurdling','w'),('handplant_flags','w'),('handplant_time','f'),('handplant_thresholds','v3'),('footplant_active','w'),('footplant_duration','f'),('footplant_contact_time','f'),('time_to_skitch','f'),('skitch_transition_time','f'),('time_to_land','f'),('time_to_land_valid','w'),('offboard_time_to_land','f'),('offboard_air_scalar_92','f'),('offboard_air_translation','v4'),('offboard_landing_normal','v4'),('offboard_committed_to_motion','w'),('offboard_obstacle_distance','f'),('offboard_edge_distance','f'),('offboard_trajectory_time','f'),('offboard_trajectory_valid','w'),('reached_apex','w'),('can_land_on_board','w'),('landing_turning','w'),('grind_contact','w'),('wheel_contact','w'),('trucks_or_deck_contact','w'),('moving_object','w'),('tricks_blocked_on_stairs','w')]]
RECORDS += [('grind','cp.grind','h.grind_physical',[('grinding','grinding','w'),('grind_name','grind_name','w5'),('deck_velocity','ground_axis','xyz'),('effective_board_forward','board_axis','xyz'),('processed_bit20','ground_flag_273','w'),('h.physical.conditions.mirrored.value()','animation_mirrored','outsidew'),('animation_height','height','f'),('physical_crouch','crouch','f'),('raw_skeleton_twist','twist','f')]),('motion_gameplay','h.physical.gameplay','h.gameplay_conditions',[(n,n,t)for n,t in GAMEPLAY]),('action_gameplay','action.gameplay_conditions','s.animation.action.gameplay_conditions',[(n,n,t)for n,t in GAMEPLAY])]

def emit(cpp,rust,kind):
    if kind=='w':return f'o.Word(std::uint32_t({cpp}));',f'o.word({rust} as u32);'
    if kind=='f':return f'o.Float({cpp});',f'o.float({rust});'
    if kind.startswith('v'):return f'o.Floats({cpp});',f'o.floats({rust});'
    if kind=='outsidew':return f'o.Word(std::uint32_t({cpp}));',f'o.word({rust} as u32);'
    if kind=='xyz':return f'o.Floats(std::array<float,3>{{{cpp}.x,{cpp}.y,{cpp}.z}});',f'o.floats({rust});'
    if kind=='w5':return f'for(auto w:{cpp})o.Word(w);',f'o.words({rust}.0);'
    if kind=='outside4':return f'o.Floats({cpp});',f'o.floats({rust});'
    if kind=='outside16':return f'o.Matrix({cpp});',f'o.matrix({rust});'
    raise ValueError(kind)

def publication_helpers():
    cpp=['void PhasePublicationOut(Output& o,const SkaterAnimation& a,const GraphActionPhysicalInputs& action,const AnimationFeedbackRuntime& f,const AnimationPhysicalFeedback& feedback,const AnimationPhaseOutput& output,const TeleportStateRuntime& teleport){const auto& h=a.motion;const auto& cp=a.complete_motion.physical;']
    rust=['pub(crate)fn migration_phase_observe(o:&mut crate::Output,s:&SkaterRuntime,output:&AnimationPhaseOutput){let h=&s.animation.motion;']
    for index,(name,n,r,fields)in enumerate(RECORDS):
        cpp.append(f'o.Word({index});o.Word(bool({n}));if({n}){{const auto& v=*{n};')
        rust.append(f'o.word({index});o.word({r}.is_some()as u32);if let Some(v)={r}{{')
        for cn,rn,kind in fields:
            ce=cn if kind.startswith('outside')else ('v.'+cn if cn else 'v');re='v.'+rn if rn else 'v';c,rs=emit(ce,re,kind);cpp.append(c);rust.append(rs)
        cpp.append('}');rust.append('}')
    owner=block((TESTS/'Simulation/animation_feedback_runtime_probe.cpp').read_text(),'  void Owner(')
    owner=owner[owner.index('{')+1:owner.rindex('}')].replace('Floats(','o.Floats(').replace('Float(','o.Float(')
    cpp.append('{const auto& o=f;'+owner+'}')
    # Avoid shadowing the output named o in the verbatim observer body.
    cpp[-1]=cpp[-1].replace('const auto& o=f;','const auto& owner=f;').replace('o.settings','owner.settings').replace('o.bump_settings','owner.bump_settings').replace('o.state','owner.state').replace('o.previous','owner.previous').replace('o.published','owner.published')
    feed=block((TESTS/'Simulation/animation_feedback_runtime_probe.cpp').read_text(),'  void Feedback(')
    feed=feed[feed.index('{')+1:feed.rindex('}')].replace('Floats(','o.Floats(').replace('Float(','o.Float(').replace('Word(','o.Word(')
    cpp.append('{const auto& v=feedback;'+feed+'}');rust.append('s.animation_feedback.migration_observe(o);migration_phase_feedback(o,s.physical_feedback);')
    cpp.append('Observe(o,output.Packet());o.Word(bool(teleport.PendingReply()));if(teleport.PendingReply()){for(auto v:teleport.PendingReply()->transform)for(auto w:v)o.Word(w);o.Word(teleport.PendingReply()->on_board);}}')
    rust.append('output.migration_phase_packet(o);s.teleport_state.migration_phase_reply(o);}')
    rust.append('pub(crate)fn migration_phase_feedback(o:&mut crate::Output,v:PhysicalFeedback){let t=v.turning;o.floats([t.field_32,t.field_36,t.field_52,t.field_56,t.field_60,t.body_168]);let c=v.crouching;o.floats([c.body_84,c.body_164,c.body_188,c.force_516,c.ground_force_520,c.minimum_crouch_528,c.deck_angle_532,c.animation_height_72]);o.float(v.pumping_acceleration);o.floats(v.ground_acceleration);o.word(v.bumped as u32);o.floats(v.conditioned_turn);}')
    return '\n'.join(cpp),'\n'.join(rust)

PACKET_OBSERVER='''
impl AnimationPhaseOutput{
 pub(crate)fn migration_phase_reset(&self)->&AdditionalResetFields{&self.reset}
 pub(crate)fn migration_phase_packet(&self,o:&mut crate::Output){crate::observe_AnimationInputPacket(o,&self.packet());}
}
'''
TELEPORT_OBSERVER='''
impl Runtime{pub(crate)fn migration_phase_reply(&self,o:&mut crate::Output){o.word(self.pending_reply.is_some()as u32);if let Some(reply)=self.pending_reply{for v in reply.transform{o.words(v)}o.word(reply.on_board as u32)}}}
'''

def simulation_plan(output):
    snapshot,report=conditioning.simulation_plan(output)
    for unit in UNITS:shutil.copy2(CODE/(unit+'.cpp'),snapshot/(unit+'.cpp'))
    raw=(snapshot/'state_conditioning_runtime_probe.cpp').read_text();prefix=raw[:raw.index('int main(')]
    initialization=raw[raw.index(' if(argc!=6)'):raw.index(' Input i{{')].replace('argc!=6','argc!=9')
    register='for(const auto& name:clips){auto clip=std::make_shared<AnimationClipSamples>();if(!clip->Load(File(std::filesystem::path(argv[7])/"clips"/(name+".skate")),error)||!frames.RegisterClip(clip,error))return 2;}\n'
    initialization=initialization.replace(' const auto* definition=', ' '+register+' const auto* definition=')
    construction=raw[raw.index(' for(unsigned c=0;c<count;++c){')+len(' for(unsigned c=0;c<count;++c){'):raw.index(' const auto provider=')]
    cases=raw[raw.index(' case 0:'):raw.index(' case 1:')]
    c,r,helpers_report=actor_helpers();(snapshot/'phase_actor_helpers.inc').write_text(c)
    observations,_=publication_helpers()
    source=(TESTS/'Simulation/animation_phase_runtime_probe.cpp').read_text().replace('// GENERATED_SIMULATION_OWNER_PREFIX',prefix).replace('// GENERATED_SIMULATION_OWNER_INITIALIZATION',initialization).replace('// GENERATED_SIMULATION_OWNER_CONSTRUCTION',construction).replace('// GENERATED_SIMULATION_PACKET_RESET_CASES',cases).replace('// GENERATED_PHASE_PUBLICATION_OBSERVERS',observations).replace('PHASE_QUERY_NAMES','{'+','.join(json.dumps(n)for n in QUERIES)+'}')
    (snapshot/'animation_phase_runtime_probe.cpp').write_text(source)
    report.update(units=UNITS,actor_helpers=helpers_report,publication_schema_sha256=hashlib.sha256(json.dumps(RECORDS).encode()).hexdigest(),immutable_simulation_sources={p.name:digest(p)for p in sorted(snapshot.iterdir())if p.is_file()})
    return snapshot,report

def reference_plan(output):
    original,observed,crate,cargo,report=conditioning.reference_plan(output)
    generated,_=conditioning.grind.reset.generated_observer();prefix=generated[generated.index('use super::*;'):generated.index('pub(super) fn run(')]
    cases=generated[generated.index(' 0=>'):generated.index(' 1=>')]
    observer=(TESTS/'Reference/animation_phase_runtime_observer.rs').read_text().replace('// GENERATED_ORIGINAL_OWNER_PREFIX',prefix).replace('// GENERATED_ORIGINAL_PACKET_CASE',cases).replace('// GENERATED_PROVIDER_READER',conditioning.grind.provider_helpers()[1]).replace('// GENERATED_GRIND_WORLD',conditioning.grind.world_helpers()[1])
    _,r,helpers_report=actor_helpers();source=(crate/'src/migration_probe.rs').read_text();source=source[:source.index('fn main()')]+r+'\n'+(TESTS/'Reference/animation_phase_runtime_probe.rs').read_text();(crate/'src/migration_probe.rs').write_text(source)
    _,publication=publication_helpers()
    completed=(TESTS/'Reference/skater_animation_complete_observer.rs').read_text();m=completed.split('// [motion]\n')[1].split('// [animation]\n')[0];a=completed.split('// [animation]\n')[1]
    extensions={'physics/input_phase.rs':'\n'+observer,'physics.rs':'\npub(crate)fn migration_animation_phase_run(a:&std::path::Path,f:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{input_phase::migration_animation_phase_run(a,f,i,o)}\n','physics/animation_phase.rs':'\npub(crate)fn migration_phase_new()->AnimationPhaseOutput{AnimationPhaseOutput::new()}\n'+publication,'physics/animation_phase_packet.rs':PACKET_OBSERVER,'physics/teleport_state.rs':TELEPORT_OBSERVER,'physics/animation_feedback.rs':'\n'+(TESTS/'Reference/animation_feedback_runtime_observer.rs').read_text(),'graph_host/motion.rs':'\n'+m,'graph_host/motion_animation.rs':'\n'+a}
    for rel,extra in extensions.items():append(crate/'src'/rel,extra)
    cargo.write_text(cargo.read_text().replace('name="state-conditioning-runtime-reference"','name="animation-phase-runtime-reference"'))
    report.update(phase_extensions={rel:dict(append_sha256=hashlib.sha256(extra.encode()).hexdigest(),generated_sha256=digest(crate/'src'/rel))for rel,extra in extensions.items()},actor_helpers=helpers_report,publication_schema_sha256=hashlib.sha256(json.dumps(RECORDS).encode()).hexdigest(),scope='Whole untouched host animation_phase.rs advance/publish_feedback/initial_feedback and original constructors. All observation extensions are append-only. Already-sampled controller/intents and completed canonical physical packets are required source inputs, not replacement computation.')
    return original,observed,crate,cargo,report

def graph_pair(kind):
    if kind==3:
        action,motion=facade.fixtures(6)
        names=('IsGrabbingObject','IsHandPlanting','IsFootPlanting','IsDroppingIn','DisableDismount','TimeToLand')
        for name in names:
            attrs=[attribute('state','air'),attribute('dir','any')]if name=='IsHandPlanting'else [attribute('greater',bits=facade.scheduler.bits(.25))]if name=='TimeToLand'else []
            action['children'].append(element('state',name,children=[facade.scheduler.expression([facade.scheduler.condition(name,attrs)]),facade.scheduler.behavior('CreateConstMGIntent',[attribute('MGIntent','PH_'+name),attribute('float',bits=facade.scheduler.bits(.731))])]))
        return action,motion
    if kind==0:return facade.fixtures(5)
    if kind==1:
        action,motion=facade.fixtures(6)
        motion=element('state','root',children=[facade.play('ACTUAL_MISSING_CLIP'),facade.scheduler.behavior('UpdateTimeSinceTeleport')])
        return action,motion
    return facade.fixtures(6)

def corpus():
    _,base=conditioning.grind.corpus();packet0=base[0]['commands'][0];provider=base[0]['provider'];cases=[]
    def completed(t,state):
        v=copy.deepcopy(packet0);v['physical']['state'].update(state_16=state,category_12=state//100*100)
        p=v['processed'];p.update(state_2508=state,category_2512=state//100*100,flags_2468=0x2000|((t%2)<<20),flags_2476=(4 if t%3==0 else 0)|(0x400000 if t%5==0 else 0),flags_2480=0x1000 if t%2 else 0,flags_2484=0x40000 if t%2 else 0,time_since_last_input_2748=.0137*t)
        p['probe_1792']['bytes_72_73']=[int(t%5==0),0];p['probe_1792']['vectors_16_32_48']=[[facade.scheduler.bits(x)for x in (t*.017,.731,-.317,.137)],[facade.scheduler.bits(x)for x in(-.137*t,.517,.113,.731)],[0]*4]
        q=v['physical'];q['filtered_state_0']=0;g=q['grinds'];g['words_136_140']=[0xffffffff,0];g['animation_name_156']=g['scoring_name_176']=None;g['grinding_316']=0;g['dropping_in_324']=int(t%2==0)
        q['animation'].update(manual_opposition_168=t%2,collision_time_144=.017*t,profile_148=1)
        q['skeleton'].update(deck_yaw_536=.00731*t,deck_pitch_540=-.00317*t,twist_504=.00137*t,no_support_time_548=.017*t,over_599=t%2)
        q['off_board'].update(flag_304=t%2,flag_311=int(state<500 or state>=600),free_board_312=t%3,returning_board_313=t%2,retrieving_board_323=t%3,dropping_board_322=t%2,flag_328=int(state==501),hippy_hurdling_317=t%2,flag_316=t%2,flag_319=t%3,flag_318=t%2,flag_329=t%2,cadence_phase_80=(t%37)*.027,locomotion_state_84=t%3,kind_88=t%3,flag_330=t%2,angle_36=.0137*t,angle_40=-.00317*t,scalar_32=.37+(t%7)*.17,scalar_92=.731,scalar_112=.371+t*.0137,distance_116=.173+t*.00731,trajectory_time_120=.517,trajectory_valid_331=t%2)
        q['air'].update(flag_444=t%2,known_air_valid_437=t%2,scalar_184=.173+(t%7)*.137,flag_441=t%2,flag_448=t%2,handplant_flags_324=t%8,handplant_time_320=(t%17)*.037,footplant_contact_time_208=.317,footplant_duration_212=.731,use_air_reckoning_452=t%2)
        for k,value in [('vector_16',(t*.037,-.317 if t%2 else .517,3+t*.0137,.137)),('vector_64',(.137,1.731,.317,.731)),('vector_96',(.0,1.0,.0,.137))]:q['reckoning'][k]=[facade.scheduler.bits(x)for x in value]
        for k,value in [('vector_64',(.137,0,3,.731)),('vector_96',(.137,0,.731,.317)),('vector_192',(0,1,0,.137))]:q['off_board'][k]=[facade.scheduler.bits(x)for x in value]
        for k in ('landing_normal_32','landing_normal_144'):q['air'][k]=[0,facade.scheduler.bits(.731),0,facade.scheduler.bits(.137)]
        return v
    def controls(t,enabled=True):
        words=[0]*26;words[16:20]=[0x7effffff]*4
        for at,val in ((0,.317),(1,-.731),(3,.137),(4,.517),(7,.137*(t%5)),(8,-.317),(10,.517),(11,.731),(21,.173*(t%5)),(22,.137),(23,.317),(24,.731),(25,.137*t)):words[at]=facade.scheduler.bits(val)
        return dict(op=50,words=words,actor_flags=(t%2)*4,values=[['A',.137],['X',-.317],['Crouch',.371],['Spin',.113],['GrindTwist',.137],['enable',1]]if enabled else [['A',.137],['exit',1]])
    def add(label,graph,rows):cases.append(dict(index=len(cases),label=label,graph=graph,world=1,provider=provider,commands=rows))
    for state in (100,201,500,501,601,701):
        rows=[]
        for t in range(32):
            rows += [completed(t,state),dict(op=40,state=state),dict(op=12),dict(op=41),controls(t),dict(op=51,flags=[int((t+i)%7==0)for i in range(36)])]
            if t%8==0:rows+=[dict(op=54,matrix=packet.pose(t)['hierarchy'][0],on_board=t%16==0)]
            rows += [dict(op=52),dict(op=53)]
        add('actual completed publication and sole graph owners '+str(state),0,rows)
    rows=[completed(1,100),dict(op=40,state=100),dict(op=12),dict(op=41),controls(1),dict(op=52),dict(op=53)]
    for n in range(12):rows += [dict(op=48,velocity=[.137*n,.017*n,3+.317*n]),dict(op=6),dict(op=34),dict(op=47),dict(op=41),controls(n),dict(op=52),dict(op=53)]
    add('actual shared solver/board/contact feedback publications',2,rows)
    for failure in ('missing_filtered','inconsistent_filtered','late_motion'):
        graph=1 if failure=='late_motion'else 2;rows=[completed(2,100),dict(op=40,state=100),dict(op=12),dict(op=41),controls(2),dict(op=54,matrix=packet.pose(9)['hierarchy'][0],on_board=False)]
        if failure=='missing_filtered':rows+=[dict(op=55)]
        elif failure=='inconsistent_filtered':rows+=[dict(op=56,word=3)]
        rows += [dict(op=52),dict(op=53),completed(3,100),dict(op=41),dict(op=52)]
        add('fallible ordered prefix / retained reply '+failure,graph,rows)
    rows=[dict(op=58)]
    for t in range(32):
        state=(100,201,500,501,600,601,701,503)[t%8]
        rows += [completed(t,state),dict(op=40,state=state),dict(op=12),dict(op=41),controls(t),dict(op=52),dict(op=58),dict(op=53)]
    rows += [dict(op=55),dict(op=52),dict(op=58)]
    add('six physical Action families on the SAME published ActionHost',3,rows)
    return cases

def encode(cases,samples):
    definitions,_=protocol.declarations();w=conditioning.grind.input_grind.Stream();manifest=json.loads((samples/'samples-manifest.json').read_text());w.word(len(manifest['clips']))
    def text(value):w.word(len(value.encode()));[w.word(c)for c in value.encode()]
    for clip in manifest['clips']:text(clip['name'])
    w.word(len(cases))
    for c in cases:
        w.word(c['graph']);w.word(c['world']);conditioning.grind.input_grind.encode_provider(w,c['provider']);w.word(len(c['commands']))
        for row in c['commands']:
            op=row['op'];w.word(op)
            if op==0:
                for name,key in (('PlayerInputState','player'),('PhysicalPlayerInput','physical'),('ProcessedPhysicsInput','processed')):protocol.encode(w,name,row[key],definitions)
            elif op==40:w.word(row['state'])
            elif op==45:w.word(row['lane']);w.word(row['word'])
            elif op==48:
                for v in row['velocity']:w.float(v)
            elif op==50:
                for v in row['words']:w.word(v)
                w.word(row['actor_flags']);w.word(len(row['values']))
                for name,v in row['values']:text(name);w.float(v)
            elif op==51:
                for v in row['flags']:w.word(v)
            elif op==54:
                for c_ in row['matrix']:
                    for v in c_:w.float(v)
                w.word(row['on_board'])
            elif op==56:w.word(row['word'])
    return bytes(w.data)

def validate_input(raw,cases,samples):
    # Independent declaration-based parsing checks every count/opcode boundary,
    # all source fields and exact re-encoding, including optional/raw-bit lanes.
    definitions,_=protocol.declarations();r=protocol.Reader(raw)
    def take(n):return [r.word()for _ in range(n)]
    def text():return bytes(take(r.word())).decode()
    manifest=json.loads((samples/'samples-manifest.json').read_text())
    assert r.word()==len(manifest['clips'])
    for clip in manifest['clips']:assert text()==clip['name']
    assert r.word()==len(cases);spans=[]
    for c in cases:
        begin=r.at;assert r.word()==c['graph']and r.word()==c['world']
        provider_begin=r.at
        rails=r.word()
        for _ in range(rails):
            text();r.word();take(r.word()*3)
            if r.word():take(r.word())
        text();take(r.word()*24)
        assert r.word()==rails;take(rails*4)
        for _ in range(r.word()):
            text();text();take(5);take(r.word())
        provider=conditioning.grind.input_grind.Stream();conditioning.grind.input_grind.encode_provider(provider,c['provider'])
        assert raw[provider_begin:r.at]==bytes(provider.data)
        assert r.word()==len(c['commands']);rows=[]
        for cmd in c['commands']:
            start=r.at;op=r.word();assert op==cmd['op']
            if op==0:
                for name,key in (('PlayerInputState','player'),('PhysicalPlayerInput','physical'),('ProcessedPhysicsInput','processed')):
                    field_start=r.at;r.value(name,definitions)
                    w=conditioning.grind.input_grind.Stream();protocol.encode(w,name,cmd[key],definitions)
                    assert raw[field_start:r.at]==bytes(w.data)
            elif op in (40,56):r.word()
            elif op==45:take(2)
            elif op==48:take(3)
            elif op==50:
                take(27)
                for _ in range(r.word()):text();r.word()
            elif op==51:take(36)
            elif op==54:take(17)
            else:assert op in (6,12,28,34,41,47,52,53,55,58),op
            if op==28:take(3)
            rows.append(dict(op=op,start_byte=start,end_byte=r.at,sha256=hashlib.sha256(raw[start:r.at]).hexdigest()))
        spans.append(dict(index=c['index'],start_byte=begin,end_byte=r.at,rows=rows))
    assert r.at==len(raw),(r.at,len(raw))
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),case_spans=spans)

class Reader(conditioning.Reader):
    def state(self):
        assert self.word()==len(BLOCKS);out={}
        for name in BLOCKS:out[name]=self.take(self.word())
        return out

def decode(raw,cases):
    r=Reader(raw);assert r.word()==len(cases);result=[]
    for c in cases:
        assert r.word()==len(c['commands']);prior=r.state();rows=[]
        for command in c['commands']:
            assert r.word()==command['op'];error=r.status();extra=r.take(r.word());state=r.state();rows.append(dict(op=command['op'],error=error,extra=extra,state=state,previous=prior));prior=state
        result.append(rows)
    assert r.at==len(r.words);return result

def record_size(kind):return {'w':1,'f':1,'xyz':3,'w5':5,'outsidew':1,'outside4':4,'outside16':16}.get(kind,int(kind[1:])if kind.startswith('v')else 0)
def publication(words):
    r=Reader(struct.pack('<'+'I'*len(words),*words));out={}
    for index,(name,_,__,fields)in enumerate(RECORDS):
        assert r.word()==index;out[name]=r.take(sum(record_size(f[2])for f in fields))if r.word()else None
    out['feedback_owner']=r.take(126);out['feedback']=r.take(28)
    definitions,_=protocol.declarations();transport=protocol.Reader(struct.pack('<'+'I'*(len(words)-r.at),*words[r.at:]));out['packet']=transport.value('AnimationInputPacket',definitions);r.at+=transport.at//4
    out['reply']=r.take(17)if r.word()else None;assert r.at==len(words),(r.at,len(words));return out

def actor(words):
    size=words[0];raw=struct.pack('<'+'I'*(len(words)-1),*words[1:])[:size];r=facade.Reader(raw);out=r.snapshot();assert r.at==len(raw);return out

def coverage(frames,cases):
    counts=Counter();errors=Counter();variants={n:set()for n,_,__,_ in RECORDS};feedbacks=set();packets=set();shoves=set();partial=Counter();consumed=0;retained=0;action_truth=[set()for _ in range(6)];action_errors=[set()for _ in range(6)]
    for rows,c in zip(frames,cases):
        for row,cmd in zip(rows,c['commands']):
            p=publication(row['state']['publication']);old=publication(row['previous']['publication']);a=actor(row['state']['actor']);before=actor(row['previous']['actor']);counts[row['op']]+=1
            if row['error']:errors[row['error']]+=1
            if row['op']==58:
                trace=Reader(struct.pack('<'+'I'*len(row['extra']),*row['extra']));assert trace.word()==6
                for n in range(6):
                    assert trace.word()==1;value=trace.word();message=bytes(trace.take(trace.word())).decode()
                    if message:action_errors[n].add(message);assert value==0
                    else:action_truth[n].add(value)
                assert trace.at==len(trace.words)
                assert p['packet']==old['packet']and p['reply']==old['reply']and p['feedback']==old['feedback']and p['feedback_owner']==old['feedback_owner']
                assert a['ag']==before['ag']and a['mg']==before['mg']and a['ticks']==before['ticks']
                partial['same-host physical Action callbacks']+=6
            if row['op']==52:
                for name in variants:
                    if p[name]is not None:variants[name].add(tuple(p[name]))
                if row['error']:
                    assert p['packet']==old['packet']and p['reply']==old['reply'];retained+=1
                    assert a['ticks']==before['ticks']
                    if 'Grind graph' in row['error']:
                        assert a['pose_sha256']==before['pose_sha256'] and a['hierarchy']==before['hierarchy'] and a['local']==before['local']and a['packet']==before['packet']and a['ag']==before['ag']and a['mg']==before['mg']
                        assert p['runout']is not None and p['toggle']is not None and p['action_gameplay']is not None
                        partial['fallible grind retains early actual publications']+=1
                    else:
                        assert a['mg']!=before['mg']or a['errors']!=before['errors'];partial['actual later graph prefix']+=1
                else:
                    assert a['ticks']==before['ticks']+1 and a['pose_count']==36
                    assert p['packet']['flags_10932']==a['packet'][3]&~((1<<24)|(1<<22))
                    packets.add(tuple(p['packet']['publication']['flags_10375_10496_10784']))
                    assert p['reply']is None
                    if old['reply']is not None:
                        assert p['packet']['publication']['matrix_10704']==[old['reply'][i:i+4]for i in range(0,16,4)]
                        assert p['packet']['publication']['byte_10768']==old['reply'][16];consumed+=1
                    partial['successful full facade and publication']+=1
                if p['shove']is not None:shoves.add(tuple(p['shove'][1:5]))
            if row['op']==53:
                assert p['packet']==old['packet']and p['reply']==old['reply'];feedbacks.add(tuple(p['feedback']));partial['after-physical feedback retains actor packet and reply']+=1
    assert counts[52]>200 and counts[53]>200 and counts[6]>=12 and counts[54]>=24
    assert consumed>=24 and retained>=4 and len(feedbacks)>4 and len(shoves)>4,(consumed,retained,len(feedbacks),len(shoves))
    assert partial['fallible grind retains early actual publications']>=2 and partial['actual later graph prefix']>=2
    assert partial['successful full facade and publication']>150
    for name in ('cadence','yaw_pitch','runout','toggle','prelanding','air_leg','motion_gameplay','action_gameplay'):assert len(variants[name])>8,(name,len(variants[name]))
    assert partial['same-host physical Action callbacks']==204
    assert all(action_truth)and all(action_errors), (action_truth,action_errors)
    for n in (0,1,2,3,5):assert action_truth[n]=={0,1},(n,action_truth[n])
    assert any('completed filtered state owner'in e for e in errors)and any('inconsistent completed filtered outputs'in e for e in errors)
    return dict(opcodes=dict(counts),errors=dict(errors),proofs=dict(partial),successful_reply_consumptions=consumed,failed_phase_reply_and_packet_retention=retained,distinct_feedbacks=len(feedbacks),distinct_shove_directions=len(shoves),record_variants={n:len(v)for n,v in variants.items()},same_action_host_condition_truth=[sorted(v)for v in action_truth],same_action_host_condition_errors=[sorted(v)for v in action_errors])

def prepare(output,assets,samples):
    stock=assets/'private/stock';fixtures=output/'fixtures';fixtures.mkdir(parents=True,exist_ok=True)
    converter=facade.converter
    (fixtures/'settings.simulation').write_bytes(converter.encode_settings(stock/'skater-collections.json'));(fixtures/'physics.simulation').write_bytes(converter.encode_physics_skeletons(stock/'physics-skeletons.json'))
    for k in range(4):
        for kind,graph in zip(('action','motion'),graph_pair(k)):
            path=fixtures/f'actor-{k}.{kind}.reference';path.write_bytes(original_graph(graph));(fixtures/f'actor-{k}.{kind}.simulation').write_bytes(converter.encode_graph(converter.read_graph(path)))
    cases=corpus();raw=encode(cases,samples);framing=validate_input(raw,cases,samples);(output/'input-framing.json').write_text(json.dumps(framing,indent=2)+'\n');(output/'input.bin').write_bytes(raw);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');return fixtures,cases,raw

def build_simulation(output):
    snapshot,report=simulation_plan(output);binary=output/'animation-phase-runtime-simulation'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'animation_phase_runtime_probe.cpp'),'-o',str(binary)],check=True)
    report['binary_sha256']=digest(binary);(output/'simulation-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return binary

def build_reference(output,target):
    original,observed,crate,cargo,report=reference_plan(output);subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(cargo),'--target-dir',str(target.resolve()),'--bin','animation-phase-runtime-reference'],check=True)
    for rel,sha in report['original_source_sha256'].items():assert digest(original/rel)==sha;raw=(original/rel).read_bytes();assert(observed/rel).read_bytes()[:len(raw)]==raw
    binary=output/'animation-phase-runtime-reference';shutil.copy2(target.resolve()/'release/animation-phase-runtime-reference',binary);report['binary_sha256']=digest(binary);(output/'reference-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return binary

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('assets','samples','metadata','output','target-dir'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--preflight',action='store_true');args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    fixtures,cases,raw=prepare(output,args.assets.resolve(),args.samples.resolve()/'simulation')
    if args.preflight:
        snapshot,simulation=simulation_plan(output);original,observed,crate,cargo,reference=reference_plan(output/'reference')
        for path in (snapshot/'animation_phase_runtime_probe.cpp',crate/'src/migration_probe.rs',crate/'src/physics/input_phase.rs'):assert 'GENERATED_'not in path.read_text(),path
        for rel,sha in reference['original_source_sha256'].items():assert digest(original/rel)==sha;prefix=(original/rel).read_bytes();assert(observed/rel).read_bytes()[:len(prefix)]==prefix
        files=[CODE/(u+ext)for u in ('AnimationFeedbackRuntime','AnimationPhaseRuntime','GraphActionPhysicalConditions','GraphIntentOperations')for ext in('.h','.cpp')]+[TESTS/'check_animation_phase_runtime_parity.py',TESTS/'Simulation/animation_phase_runtime_probe.cpp',TESTS/'Reference/animation_phase_runtime_probe.rs',TESTS/'Reference/animation_phase_runtime_observer.rs']
        report=dict(preflight=True,histories=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(raw),input_sha256=hashlib.sha256(raw).hexdigest(),units=len(UNITS),frozen_files={p.relative_to(PLUGIN).as_posix():digest(p)for p in files},simulation=simulation,reference=reference)
        (output/'preflight.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items()if k not in('simulation','reference')},indent=2));return
    stock=args.assets.resolve()/'private/stock';identity=json.loads((stock/'physics-skeletons.json').read_text())['source_sha256'];reference=build_reference(output/'reference',args.target_dir);simulation=build_simulation(output)
    expected=subprocess.check_output([str(reference),str(args.assets.resolve()),str(fixtures)],input=raw);actual=subprocess.check_output([str(simulation),str(fixtures/'settings.simulation'),str(fixtures/'physics.simulation'),str(args.samples.resolve()/'simulation/rig.skate'),identity,str(args.assets.resolve()),str(args.metadata.resolve()),str(args.samples.resolve()/'simulation'),str(fixtures)],input=raw)
    (output/'reference.bin').write_bytes(expected);(output/'simulation.bin').write_bytes(actual)
    if expected!=actual:
        at=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));report=dict(byte=at,reference_bytes=len(expected),simulation_bytes=len(actual),reference_hex=expected[max(0,at-32):at+64].hex(),simulation_hex=actual[max(0,at-32):at+64].hex());(output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    proof=coverage(decode(expected,cases),cases);report=dict(passed=True,histories=len(cases),commands=sum(len(c['commands'])for c in cases),exact_bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),coverage=proof,scope='Entire untouched animation_phase.rs advance, publish_feedback and initial_feedback with actual same physical/board/skeleton/IK/plant/input/conditioning/animation/graph owners. Source order, seven continuation records, earlier producer writes, packet/reply retention, actual full actor callbacks and ordered output publication are exact.',boundaries='The six physical Action families are registered and evaluated through the same host publication member. The global frame/state coordinator, preceding selected-state Fill, sampled controls/gestures and completed canonical input packets are caller-owned producer boundaries. Walking contact borrows the accepted canonical OffboardController constructed from actual simulation stock clip metadata; full BipedGround scheduling is separate.',reference_provenance='reference/reference-provenance.json',simulation_provenance='simulation-provenance.json')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
