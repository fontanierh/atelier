#!/usr/bin/env python3
"""Full original PlayerInput owner with actual board, skeleton, IK and grind producers.

Only the root coordinator compiles/runs this through the shared guard. The global
teleport implementation and completed trajectory-selector continuation remain
upstream boundaries; the former is observed as a mandatory failed callback.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import check_skeleton_input_runtime_parity as skeleton
import check_player_grind_input_parity as grind
import check_animation_trees_parity as trees
import check_player_input_phase_parity as phase
import check_ground_control_settings_parity as settings_probe
import player_input_protocol as protocol
from check_animation_playback_parity import attribute,bits
Stream=grind.Stream
from reference_build import build_probe
PLUGIN=skeleton.PLUGIN
HOST='crates/skate-host/src/physics/'
OWN_UNITS=('PlayerGroundPosition','PlayerInputPublication','PlayerPreInput','PlayerInputRuntime','PlayerInputPhase')
UNITS=tuple(dict.fromkeys(skeleton.UNITS+grind.UNITS+OWN_UNITS))
OPERATIONS=('live_input','pending_geometry','request_teleport','clear_toolkit','publish_board','publish_grind_false','wheel_ground_position','reset_pre_input','published_state_reset')

def source(p):return grind.source(p)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def block(raw,marker):return trees.extract_block(raw,marker)[0]

def aliases():
    out=skeleton.aliases();out.update(grind.aliases())
    for name in('dynamic_normal','grind_output','ground_position','initial','output_reset','pre_input','reset','services'):
        out[f'atelier-host/src/physics/player_input/{name}.rs']=HOST+f'player_input/{name}.rs'
    return out

def pre_helpers(pre):
    # This isolated declaration has no AnimationInputPacket factory. Keep its
    # field order from the original type rather than extending shared helpers.
    cpp='void Observe(Output& o,const PreInputResult& s){'+''.join(protocol.observe_expr(k,'s.'+f,'cpp')for f,k in pre)+'}\n'
    cpp+='PreInputResult ReadPreInputResult(Input& i){PreInputResult s;'+''.join('s.'+f+'='+protocol.read_expr(k,'cpp')+';'for f,k in pre)+'return s;}'
    rust='fn observe_PreInputResult(o:&mut Output,s:&physics::player_input::PreInputResult){'+''.join(protocol.observe_expr(k,'s.'+f,'rust')for f,k in pre)+'}\n'
    rust+='fn read_PreInputResult(i:&mut Input)->physics::player_input::PreInputResult{physics::player_input::PreInputResult{'+''.join(f+':'+protocol.read_expr(k,'rust')+','for f,k in pre)+'}}'
    return cpp,rust

def helpers():
    cpp,rust=skeleton.helpers();defs,state=grind.declarations();a,b,private=grind.helpers(defs,state)
    pre=grind.struct_fields(source(HOST+'player_input/pre_input.rs'),'PreInputResult')
    pre=[(f,k.replace('AnimationPartTransform','[[f32;4];4]'))for f,k in pre]
    c,d=pre_helpers(pre)
    return cpp+'\n'+a+'\nusing PreInputResult=PlayerPreInputResult;\n'+c,rust+'\n'+b+'\n'+d,private,pre

def source_callbacks():
    raw=source(HOST+'input_phase.rs')
    methods='\n'.join(block(raw,'    fn '+name+'(')for name in('prepare_grind','process_skeleton'))
    declaration='''pub mod player_input_callbacks {
use super::{PlayerInput,SkeletonInput,Animated,Output,settings::PhysicsSettings,foot_ik::FootIk,skeleton_input_runtime::{SkeletonOwners,SkeletonPoseInput,CollisionInput}};
use super::ground_runtime::GroundRuntime;
use skate_core::{input::controller::ActionMap,animation::output::attributes::AnimationAttribute,physics::{board_runtime::BoardRuntime,board_toolkit::BoardToolkit,skeleton_animation_record::AnimationPartTransform as NativeMatrix,skeleton_body::{SkeletonBody,SkeletonDrives,SkeletonPoseErrors}},player::input_phase::{AnimationInputPacket,PhysicalPlayerInput,ProcessedPhysicsInput,PlayerInputState}};
use super::player_input::PlayerInputCallbacks;
pub struct Callbacks<'a>{pub skeleton_input:&'a mut SkeletonInput,pub animated:&'a mut Animated,pub body:&'a mut SkeletonBody,pub drives:&'a mut SkeletonDrives,pub ik:&'a mut FootIk,pub animation_input:&'a mut super::animation_input::AnimationInput,pub output:&'a mut Output,pub pose_errors:&'a mut SkeletonPoseErrors,pub collision:CollisionInput,pub settings:&'a mut PhysicsSettings,pub grind_materials:&'a super::grind_materials::GrindMaterials,pub air_targeting_grind:bool,pub globals:&'a [NativeMatrix],pub attributes:&'a [AnimationAttribute],pub actions:&'a mut dyn ActionMap,pub teleport_trace:&'a mut Vec<NativeMatrix>,pub teleport_error:&'a str}
impl PlayerInputCallbacks for Callbacks<'_>{
'''
    # The two actual source methods above are unchanged. The global reset is
    # intentionally a failing mandatory callback, with its exact arguments.
    return declaration+methods+'''
fn teleport(&mut self,_board:&mut BoardRuntime,_ground:&mut GroundRuntime,target:NativeMatrix,_player:&mut PlayerInputState,_physical:&mut PhysicalPlayerInput,_processed:&mut ProcessedPhysicsInput)->Result<(),String>{self.teleport_trace.push(target);Err(self.teleport_error.into())}
}}
'''

def prepare_oracle():
    base=skeleton.prepare_oracle(PLUGIN/'Tests/Reference/skeleton_input_runtime_probe.rs').split('fn main(){',1)[0]
    # Replace the old declaration facade with the complete actual source owner.
    nominal=next(line for line in base.splitlines()if line.startswith(' pub struct PlayerInput{'))
    cpp,rust,private,pre=helpers()
    manager=source(HOST+'player_input/grind.rs')+'\n'+private
    owner=source(HOST+'player_input/mod.rs').replace('pub(crate) mod grind;','pub(crate) mod grind{\n'+manager+'\n}')
    owner=owner.replace('mod ground_position;','mod ground_position{\n'+source(HOST+'player_input/ground_position.rs')+'\npub(crate) fn observe_wheels(wheels:[[f32;4];4],ground:&[[f32;4];4])->[f32;4]{wheel_ground_position(wheels,ground)}\n}')
    owner+='\npub(crate) use pre_input::PreInputResult;\n'+'''
pub fn observe_owner(o:&mut crate::Output,r:&PlayerInputRuntime){crate::observe_PlayerInputState(o,&r.player);crate::observe_PhysicalPlayerInput(o,&r.physical);crate::observe_ProcessedPhysicsInput(o,&r.processed);o.word(r.toolkit.is_some()as u32);if let Some(t)=r.toolkit{crate::observe_toolkit(o,&t);}for v in[r.dynamic_normal.normal,r.dynamic_normal.delta,r.dynamic_normal.acceleration,r.dynamic_normal.last_contact_normal]{o.float(v.x);o.float(v.y);o.float(v.z);}let s=&r.normal_settings;for v in[s.speed_damping,s.up_vector_damping,s.maximum_delta,s.speed_scale]{o.float(v);}for v in s.maximum_delta_vs_speed.x.into_iter().chain(s.maximum_delta_vs_speed.y){o.float(v);}o.word(r.pre_input.pending_geometry as u32);crate::observe_PreInputResult(o,&r.pre_input.result);for w in r.pre_input.result_counts{o.word(w);}grind::observe_state(o,&r.grind);o.word(r.pending_teleport.is_some()as u32);if let Some(m)=r.pending_teleport{for v in m{for x in v{o.float(x);}}}o.word(r.pending_grind.is_some()as u32);if let Some(p)=&r.pending_grind{grind::observe_pending(o,p);}o.word(r.grind_observation.is_some()as u32);if let Some(p)=&r.grind_observation{crate::observe_observation(o,p);}}
'''
    method=block(source(HOST+'ground_runtime/input.rs'),'    pub fn prepare_toolkit(')
    ground='pub mod ground_runtime{use skate_core::{physics::{board_runtime::BoardRuntime,board_toolkit::BoardToolkit},player::input_phase::ProcessedPhysicsInput};pub struct GroundRuntime{pub retained_board_normal:[f32;4]}fn raw(v:[u32;4])->[f32;4]{v.map(f32::from_bits)}impl GroundRuntime{'+method+'}}'
    family=block(source(HOST+'grind.rs'),'pub(crate) enum Family {')
    constants='\n'.join(line for line in source(HOST+'ground.rs').splitlines()if re.match(r'pub\(crate\) const (HEIGHT|FLOOR_HEIGHT):',line))
    owner+='\npub(crate) fn observe_wheels(wheels:[[f32;4];4],ground:&[[f32;4];4])->[f32;4]{ground_position::observe_wheels(wheels,ground)}\n'
    modules='pub mod player_input{\n'+owner+'\n}\npub use player_input::PlayerInputRuntime as PlayerInput;\n'+ground+'\npub mod ground{'+constants+'}\npub mod grind{#[derive(Clone,Copy,Debug,PartialEq,Eq)]#[repr(u32)]'+family+'pub mod observation{'+source(HOST+'grind/observation.rs')+'}pub use observation::ManagerObservation;}\npub mod grind_materials{'+source(HOST+'grind_materials.rs')+'}\npub mod grind_host{'+source(HOST+'grind_host.rs')+'}\n'+source_callbacks()
    base=base.replace(nominal,modules)
    initializer='physics::PlayerInput{processed:Default::default(),toolkit:None,physical:Default::default()}'
    assert initializer in base;base=base.replace(initializer,'physics::PlayerInput::load(data).unwrap()')
    # Keep the accepted observation/adapter declarations, not their tick driver.
    base=base.split('fn process_dispatcher(',1)[0]
    base=base.replace('// GENERATED_PROTOCOL',rust)
    # skeleton.prepare_oracle has already generated the canonical helpers.
    # Additional grind/pre-input declarations are appended exactly once.
    defs,state=grind.declarations();_,extra,_=grind.helpers(defs,state);_,pre_rust=pre_helpers(pre)
    base+='\n'+extra+'\n'+pre_rust+'\nmod grind_world{'+source('crates/skate-host/src/grind_world.rs')+'}\n'
    first=(PLUGIN/'Tests/Reference/player_grind_input_probe.rs').read_text()
    for marker in('fn geometry_kind(','fn read_provider(','fn observe_plan(','fn observe_observation('):base+='\n'+block(first,marker)
    return base+(PLUGIN/'Tests/Reference/player_input_runtime_probe.rs').read_text()

def prepare_native():
    prefixes=[PLUGIN/f'Tests/Native/skeleton_{n}_probe.cpp'for n in('body','collision','constraint')]+[PLUGIN/'Tests/Native/physical_simulation_runtime_probe.cpp',PLUGIN/'Tests/Native/adjusted_skeleton_probe.cpp',PLUGIN/'Tests/Native/skeleton_input_runtime_probe.cpp']
    cpp,_,_,_=helpers();base='#include "PlayerInputRuntime.h"\n#include "PlayerGroundPosition.h"\n'+''.join(p.read_text().split('int main(',1)[0].split('int main()',1)[0]for p in prefixes)
    base=base.replace('// GENERATED_PROTOCOL',cpp)
    # Add word-oriented string transport to the existing declarations only.
    base=base.replace('AnimationAttribute Attribute(){','Vec3 Vector(){return ::Vector();}std::string Text(){const auto n=Word();std::string s;for(unsigned j=0;j<n;++j)s+=char(Word());return s;}\n    AnimationAttribute Attribute(){')
    base=base.replace('void Float(float v){std::uint32_t w;std::memcpy(&w,&v,4);Word(w);}','void Float(float v){std::uint32_t w;std::memcpy(&w,&v,4);Word(w);}void Error(const char* s){std::string_view v(s?s:"");Word(std::uint32_t(v.size()));for(unsigned char c:v)Word(c);}')
    base+='\n[[noreturn]]void Fail(const char* error){std::cerr<<error;std::exit(2);}\n'
    first=(PLUGIN/'Tests/Native/player_grind_input_probe.cpp').read_text()
    for marker in('PlayerGrindStaticProvider ReadProvider(','void ObserveProvider(','void ObservePlan(','void ObservePending(','void ObserveObservation('):base+='\n'+block(first,marker)
    return '#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wunused-function"\n'+base+'\n#pragma clang diagnostic pop\n'+(PLUGIN/'Tests/Native/player_input_runtime_probe.cpp').read_text(),prefixes

def corpus():
    defs,_=protocol.declarations();_,_,_,pre=helpers();cases=[]
    def zero(k):
        if k.startswith('&'):return zero(k[1:])
        a=protocol.array(k)
        if a:return [zero(a[0])for _ in range(a[1])]
        if protocol.option(k):return None
        if k=='RawVector':return [0]*4
        if k=='RawMatrix':return [[0]*4 for _ in range(4)]
        if k=='AttributeName':return [0]*5
        if k=='bool':return False
        if k in('f32','u8','u16','u32','i32','u64','NativeReferenceBase'):return 0
        return {f:zero(t)for f,t in defs[k]}
    def matrix(angle=0,offset=(0,0,0),fourth=0):
        import math
        c,s=math.cos(angle),math.sin(angle)
        return [[c,0,-s,fourth],[0,1,0,fourth],[s,0,c,fourth],[*offset,1]]
    def attr(name,value=.137,kind=0,payload=None):
        a=attribute(kind=kind,status=5);a['name']=trees.name(name);a['payload']=[bits(value),None,None,None,None,None]if payload is None else payload;return a
    def packet(seed,n,variant=None):
        v=zero('AnimationInputPacket');v['publication'].update(timestep=(1/60,1/120,1/30)[seed%3],stance_byte=(seed+n)%2,flags_10375_10496_10784=[0,int(n%4==0),0],flag_10371=seed%2,truck_tightness=.35,scalar_10388=.3)
        v['publication']['matrix_10704']=[[bits(x)for x in row]for row in matrix(.03*n)]
        v.update(state_variant_10928=(seed+n)%5 if variant is None else variant,flags_10932=(0,0x08800000,0x12000000)[n%3],flag_10370=(seed+n)%2,force_braking_10796=int(n%3==0),use_external_physics_10688=int(n%4==1))
        v['external_physics_10512']['flags']=0x0c000000;v['external_physics_10512']['vectors']=[[bits(x)for x in(0,.013,.021,0)]for _ in range(10)];return v
    def tick(seed,n,**kw):
        state=(100,201,401,400,403,500,601,702)[(seed+n//3)%8]
        c=dict(op=0,state=state,category=state//100*100,filtered=(1,2,3,6)[(seed+n)%4],flags=0x00000000,pending=False,air_target=n%3==1,surface=(1,3,5,13)[seed%4],pose=(seed+n//4)%4,attributes=[attr('Balance',.1),attr('BodySpin',.03),attr('Crouch',.2)],actions=[0]*18,packet=packet(seed,n),query56=91+seed,query44=0xffffffff,available=True,transition=(0,.25,-.25)[n%3],air_counter=20)
        if n%4==0:c['attributes'].append(attr('push_contact',kind=3,payload=trees.name('RightToeBase')+[bits(.75)]))
        c['actions'][0]=-.25;c['actions'][1]=.25;c['actions'][4]=.75;c.update(kw);return c
    def add(label,cmds,seed=0,provider=None):
        import math
        angle=.17*seed;c,s=math.cos(angle),math.sin(angle);spawn=[c,0,-s,0,1,0,s,0,c,0,(0,.06,.35,.8)[seed%4],0];slope=(0,.12,-.12,.35)[seed%4];points=[[-4,-4*slope-.025,-4],[4,4*slope-.025,-4],[4,4*slope-.025,4],[-4,-4*slope-.025,4]]
        world=dict(triangles=[dict(vertices=[points[j]for j in ids],fat=0.,flags=0x10,tag=tag,surface=0x20b if seed%4 else 0x40c)for ids,tag in(((0,2,1),1),((0,3,2),12))],pool=seed%3,group=0xffffffff,island_flags=3)
        cases.append(dict(index=len(cases),label=label,spawn=spawn,world=world,provider=provider or grind.authored_provider([[0,-.08,-3],[0,-.08,3]]),commands=cmds))
    for seed in range(32):
        commands=[]
        for n in range(12):
            if n==4:commands.append(dict(op=4))
            if n==8:commands+=[dict(op=3),dict(op=4),dict(op=5)]
            commands.append(tick(seed,n))
        add('actual canonical owner -> toolkit -> scalar/contact/pose/IK -> grind -> shared solve -> retained publication',commands,seed,grind.authored_provider([[-3,-.015,0],[3,-.015,0]])if seed%2 else None)
    for branch in('pending geometry','invalid variant','missing hierarchy','missing scalar','missing contact'):
        cmd=tick(0,0)
        if branch=='pending geometry':cmd['pending']=True
        elif branch=='invalid variant':cmd['packet']['state_variant_10928']=5
        elif branch=='missing hierarchy':cmd['pose']=4
        elif branch=='missing scalar':cmd['attributes']=[attr('Balance',.1),attr('Brake',payload=[None]*6)]
        else:cmd['attributes']=[attr('Balance',.1),attr('push_contact',kind=3,payload=[None]*6)]
        add('actual source partial failure: '+branch,[cmd])
    for kind in('state reset bit','pending host target'):
        cmd=tick(0,0)
        if kind=='state reset bit':cmd['flags']=1<<19
        commands=[cmd]if kind=='state reset bit'else[dict(op=2,target=matrix(.37,(1,2,3))),dict(op=2,target=matrix(.73,(4,5,6))),cmd]
        add('mandatory global teleport callback failure: '+kind,commands)
    for simultaneous in(False,True):
        target=matrix(.529,(7,-2,3));reset=dict(transform=[[bits(x)for x in row]for row in target],next_state=100,state_61=1,board_272=1)
        commands=[dict(op=8,reset=reset)]
        if simultaneous:commands.append(dict(op=2,target=matrix(.173,(1,4,9))))
        commands.append(tick(0,0,flags=1<<19 if simultaneous else 0))
        add('mandatory global teleport callback failure: published State61 precedes explicit requests',commands)
    add('absent toolkit publication errors retain every physical packet field',[dict(op=4),dict(op=5),tick(0,0),dict(op=3),dict(op=4),dict(op=5)])
    for pending in(False,True):
        value={f:protocol.default(k,defs,seed=73)for f,k in pre}
        add('actual pre manager result reset before explicit pending error',[dict(op=1,pending=pending),dict(op=7,counts=[0x12345678,0xffffffff,0x80000000],result=value)])
    for seed in range(24):
        wheels=[[.137*j,.25*(j%3)+.03*seed,-.731*j,.517]for j in range(4)]
        if seed%6==1:wheels[0][1]=float('nan')
        if seed%6==2:wheels[1][1]=float('inf')
        if seed%6==3:wheels[2][1]=-float('inf')
        if seed%6==4:wheels[2][1]=wheels[1][1]
        if seed%6==5:wheels[0][1]=-0.;wheels[1][1]=0.
        add('source four-wheel minimum/transposed frame IEEE branch',[dict(op=6,wheels=wheels,frame=matrix(.137*seed,(99,-37,17),fourth=.517))])
    return cases,defs,pre

def encode(cases,defs,pre):
    w=Stream();w.word(len(cases))
    def fs(v):[w.float(x)for x in v]
    def attrs(values):
        w.word(len(values))
        for a in values:
            for x in a['name']+[a['kind'],a['status'],a['sequence']&0xffffffff,a['begin'],a['end']]:w.word(x)
            for v in a['payload']:w.word(v is not None);w.word(v)if v is not None else None
    for c in cases:
        fs(c['spawn']);world=c['world'];w.word(len(world['triangles']))
        for t in world['triangles']:
            fs([x for v in t['vertices']for x in v]);w.float(t['fat']);[w.word(t[k])for k in('flags','tag','surface')]
        for k in('pool','group','island_flags'):w.word(world[k])
        grind.encode_provider(w,c['provider']);w.word(len(c['commands']))
        for cmd in c['commands']:
            op=cmd['op'];w.word(op)
            if op==0:
                for k in('state','category','filtered','flags','pending','air_target','surface','pose'):w.word(cmd[k])
                attrs(cmd['attributes']);fs(cmd['actions']);protocol.encode(w,'AnimationInputPacket',cmd['packet'],defs)
                for k in('query56','query44','available'):w.word(cmd[k])
                w.float(cmd['transition']);w.word(cmd['air_counter'])
            elif op==1:w.word(cmd['pending'])
            elif op==2:fs([v for row in cmd['target']for v in row])
            elif op==6:fs([v for row in cmd['wheels']+cmd['frame']for v in row])
            elif op==7:
                for v in cmd['counts']:w.word(v)
                for f,k in pre:protocol.encode(w,k,cmd['result'][f],defs)
            elif op==8:protocol.encode(w,'TeleportOutputFields',cmd['reset'],defs)
    return bytes(w.data)

def preflight():
    cases,defs,pre=corpus();blob=encode(cases,defs,pre);r=protocol.Reader(blob);assert r.word()==len(cases)
    def provider():
        for _ in range(r.word()):
            for _ in range(r.word()):r.word()
            r.word()
            for _ in range(r.word()*3):r.word()
            if r.word():
                for _ in range(r.word()):r.word()
        for _ in range(r.word()):r.word()
        for _ in range(r.word()):
            for _ in range(8):r.word()
            r.wide();r.wide();r.wide();r.word();r.word()
            for _ in range(6):r.word()
            r.wide()
        for _ in range(r.word()):r.wide();r.wide()
        for _ in range(r.word()):
            for _ in range(r.word()):r.word()
            for _ in range(r.word()):r.word()
            r.wide();r.wide();r.word()
            for _ in range(r.word()):r.word()
    for c in cases:
        for _ in range(12):r.word()
        for _ in range(r.word()*13+3):r.word()
        provider();assert r.word()==len(c['commands'])
        for cmd in c['commands']:
            op=r.word();assert op==cmd['op']
            if op==0:
                for _ in range(8):r.word()
                for _ in range(r.word()):
                    for _ in range(10):r.word()
                    for _ in range(6):
                        if r.word():r.word()
                for _ in range(18):r.word()
                r.value('AnimationInputPacket',defs)
                for _ in range(5):r.word()
            elif op==1:r.word()
            elif op==2:
                for _ in range(16):r.word()
            elif op==6:
                for _ in range(32):r.word()
            elif op==7:
                for _ in range(3):r.word()
                for _,kind in pre:r.value(kind,defs)
            elif op==8:r.value('TeleportOutputFields',defs)
    assert r.at==len(blob),(r.at,len(blob))
    for u in UNITS:assert(PLUGIN/f'Source/AtelierSkate/Private/Native/{u}.cpp').is_file(),u
    return blob,cases

def build(output,target):
    live=PLUGIN/'Source/AtelierSkate/Private/Native';snapshot=output/'native-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir()
    for p in live.glob('*.h'):shutil.copy2(p,snapshot/p.name)
    for u in UNITS:shutil.copy2(live/f'{u}.cpp',snapshot/f'{u}.cpp')
    cpp,prefixes=prepare_native();generated=snapshot/'player-input-runtime-combined.cpp';generated.write_text(cpp)
    rust_prefixes=[PLUGIN/f'Tests/Reference/skeleton_{n}_probe.rs'for n in('body','collision','constraint')]
    prefix=''.join(p.read_text().split('fn main(){',1)[0]for p in rust_prefixes).replace('use crate::{','use skate_core::{').replace('skeleton_root::inverse_rigid,','').replace('solver::{packed,JointConstraint}','solver::{JointConstraint}').replace('#[path="physics/solver/packing.rs"] mod skeleton_constraint_packing;','mod skeleton_constraint_packing{use skate_core::physics::solver::{packed,JointConstraint};use crate::{RetailDriveRows,RetailContactJacobian};use skate_core::physics::rigid_body::RetailReactionCorrections;#[path="packing.rs"]mod original;pub fn drive(r:&RetailDriveRows)->packed::Drive{original::drive(r)}}')
    original=output/'player-input-runtime-combined.rs';original.write_text(prefix+prepare_oracle())
    reference=build_probe(output,'player-input-runtime-reference',original,target,bevy=True,extra_sources=aliases())
    native=output/'player-input-runtime-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{u}.cpp')for u in UNITS],str(generated),'-o',str(native)],check=True)
    (output/'native-provenance.json').write_text(json.dumps(dict(native_source_sha256={p.name:digest(p)for p in sorted(snapshot.iterdir())},probe_sha256={p.name:digest(p)for p in[*prefixes,*rust_prefixes,PLUGIN/'Tests/Native/player_input_runtime_probe.cpp',PLUGIN/'Tests/Reference/player_input_runtime_probe.rs']},original_host_callbacks='Verbatim prepare_grind/process_skeleton methods from input_phase.rs; mandatory global teleport fails explicitly. GroundRuntime prepare_toolkit is verbatim original; full ground lifecycle is outside this proof.'),indent=2)+'\n')
    return native,reference

def decode(data,cases):
    defs,_=protocol.declarations();gdefs,state=grind.declarations();defs.update(gdefs);_,_,_,pre=helpers();r=protocol.Reader(data);frames=[]
    def text(reader):return bytes(reader.word()for _ in range(reader.word())).decode()
    def status(reader):
        ok=reader.word();assert ok in(0,1),ok
        return dict(ok=bool(ok),error=text(reader))
    def owner(end):
        result={kind:r.value(kind,defs)for kind in('PlayerInputState','PhysicalPlayerInput','ProcessedPhysicsInput')}
        if r.word():
            result['toolkit']=dict(matrices=[r.value('[[f32;4];4]',defs)for _ in range(3)],vectors=[r.value('[f32;4]',defs)for _ in range(8)],scalars=r.value('[f32;3]',defs))
        else:result['toolkit']=None
        result['normal']=[r.value('[f32;3]',defs)for _ in range(4)];result['normal_settings']=r.value('[f32;20]',defs)
        result['pending_geometry']=bool(r.word());result['pre_result']={f:r.value(k,defs)for f,k in pre};result['pre_counts']=r.value('[u32;3]',defs)
        result['grind']={f:r.value(k,defs)for f,k in state};result['teleport']=r.value('[[f32;4];4]',defs)if r.word()else None
        pending=None
        if r.word():
            pending=dict(fields=r.value('GrindInvestigationFields',defs),metadata=None,geometry=None)
            if r.word():pending['metadata']=[r.wide(),r.wide()]if r.word()else None
            if r.word():
                geometry=dict(input=r.value('InvestigationInput',defs),plan=None)
                if r.word():geometry['plan']=dict(center=r.value('[f32;4]',defs),up=r.value('[f32;4]',defs),direction=r.value('[f32;4]',defs),probes=[r.value('Probe',defs)for _ in range(r.word())])
                geometry['hits']=[r.value('ProbeHit',defs)if r.word()else None for _ in range(7)];pending['geometry']=geometry
        result['pending_grind']=pending;observation=None
        if r.word():
            observation=dict(vectors=[r.value('[f32;4]',defs)for _ in range(6)],guids=[r.wide(),r.wide()]if r.word()else None,up=r.value('[f32;4]',defs),high=r.value('[f32;4]',defs))
            observation['geometry_surface_control']=r.value('[u32;15]',defs);observation['engagement_velocity']=r.value('[f32;4]',defs);observation['engagement_kind']=r.word();observation['jumper']=r.value('[u32;23]',defs)
        result['observation']=observation;result['retained_ground']=r.value('[f32;4]',defs);assert r.at==end,(r.at,end)
        return result
    def frame():
        size=r.word()*4;physical=r.data[r.at:r.at+size];r.at+=size
        size=r.word()*4;end=r.at+size;result=owner(end);result['physical_sha256']=hashlib.sha256(physical).hexdigest();return result
    def effects(raw,op):
        e=protocol.Reader(raw);result={}
        if op==0:
            result['ok']=bool(e.word());result['stages']=[status(e)for _ in range(3)]
            if result['stages'][1]['ok']and result['stages'][2]['ok']:
                result['post']=status(e)
                if result['post']['ok']:
                    result['wipeout_reasons']=e.value('[u32;'+str(e.word())+']',defs)
                    # After a successful post, a complete tick has two row counts
                    # and three publication statuses. Failed GeneralUpdate/solve
                    # retains its original error instead of these row counts.
                    saved=e.at
                    try:
                        contacts=e.word();drives=e.word();publications=[status(e)for _ in range(3)]
                        assert e.at==len(raw)
                        result.update(contacts=contacts,drives=drives,publications=publications)
                    except(AssertionError,struct.error,UnicodeDecodeError,ValueError):
                        e.at=saved;result['final_failure']=status(e)
        else:
            if op==6:result['ground_position']=e.value('[f32;4]',defs)
            result.update(status(e))
        assert e.at==len(raw),(op,e.at,len(raw));return result
    for case in cases:
        first=r.at;assert r.word()==case['index'];assert r.word()==len(case['commands']);size=r.word()*4;end=r.at+size
        size=r.word()*4;initial_end=r.at+size;initial=frame();assert r.at==initial_end
        rows=[]
        for command in case['commands']:
            op=r.word();assert op==command['op'];size=r.word()*4;row_end=r.at+size;size=r.word()*4;effect_end=r.at+size;raw=r.data[r.at:effect_end];r.at=effect_end
            row=dict(op=op,effects=effects(raw,op),teleports=[r.value('[[f32;4];4]',defs)for _ in range(r.word())],owner=frame());assert r.at==row_end,(case['index'],op,r.at,row_end);rows.append(row)
        assert r.at==end,(case['index'],r.at,end);case['first_output_byte']=first;case['output_bytes']=r.at-first;frames.append(dict(initial=initial,rows=rows))
    assert r.at==len(data),(r.at,len(data));return frames

def coverage(data,cases):
    frames=decode(data,cases);counts=Counter();states=Counter();modes=Counter();errors=Counter();normal=set();toolkit=set();packets=set();contacts=drives=observations=partial=0
    for case,f in zip(cases,frames):
        previous=f['initial'];reset=f['initial']['pre_result']
        for cmd,row in zip(case['commands'],f['rows']):
            own=row['owner'];effect=row['effects'];counts[OPERATIONS[cmd['op']]]+=1
            normal.add(tuple(own['normal'][0]));packets.add(json.dumps(own['PhysicalPlayerInput'],sort_keys=True))
            if own['toolkit']:
                t=own['toolkit'];toolkit.add(json.dumps(t,sort_keys=True));assert t['matrices'][0][3][3]==bits(1.)
            if cmd['op']==0:
                counts['tick_success'if effect['ok']else'tick_failure']+=1
                if effect['ok']:
                    assert all(s['ok']and not s['error']for s in effect['stages'])and effect['post']['ok']and all(s['ok']for s in effect['publications'])
                    states[own['ProcessedPhysicsInput']['state_2508']]+=1;modes[own['ProcessedPhysicsInput']['state_variant_index_2528']]+=1
                    contacts+=effect['contacts'];drives+=effect['drives'];observations+=own['observation']is not None
                    assert own['pending_grind']is None and own['observation']is not None
                    # A fresh actual TrajectorySelector::new has no lock; the
                    # completed true continuation is a declared future proof.
                    assert own['PhysicalPlayerInput']['air']['flag_443']==0
                else:
                    for s in effect['stages']+[effect.get('post',{}),effect.get('final_failure',{})]:
                        if s.get('error'):errors[s['error']]+=1
                    partial+=own!=previous
                if 'actual source partial failure'in case['label']or'mandatory global teleport callback'in case['label']:assert not effect['ok'],case['label']
                if 'mandatory global teleport callback'in case['label']:
                    assert len(row['teleports'])==1 and effect['stages'][0]['error']=='Player input: Service("complete global teleport owner is required")'
                    if 'pending host target'in case['label']:assert own['teleport']is not None
                    elif 'published State61'in case['label']:
                        assert own['PhysicalPlayerInput']['state']['flag_61']==1
                        target=own['PhysicalPlayerInput']['teleport_output']['transform'];assert row['teleports'][0]==target
                        if own['teleport']is not None:assert own['PlayerInputState']['flags_1296']&(1<<19)
                        counts['published_state61_precedence']+=1
                    else:assert own['PlayerInputState']['flags_1296']&(1<<19)
                    counts['required_global_teleport_failure']+=1
            elif cmd['op']in(4,5)and previous['toolkit']is None:
                assert not effect['ok']and own['PhysicalPlayerInput']==previous['PhysicalPlayerInput'];counts['absent_toolkit_preserved_packet']+=1;errors[effect['error']]+=1
            elif cmd['op']==2 and previous['teleport']is not None:
                assert not effect['ok']and own['teleport']==previous['teleport'];counts['pending_teleport_refused_replacement']+=1
            elif cmd['op']==7:
                assert own['pre_result']==reset and own['pre_counts']==[0,0,0]and own['PlayerInputState']['manager_1856_counter_320']==30
                assert effect['ok']==(not own['pending_geometry']);counts['pre_reset_before_pending_error']+=1
            previous=own
    assert counts['tick_success']>100 and counts['tick_failure']>=7,counts
    assert contacts>0 and drives>0 and observations>100,(contacts,drives,observations)
    assert set(modes)==set(range(5)),modes
    assert len(states)>=6 and len(normal)>1 and len(toolkit)>8 and len(packets)>8,(states,len(normal),len(toolkit),len(packets))
    assert counts['required_global_teleport_failure']==4 and counts['published_state61_precedence']==2 and counts['pending_teleport_refused_replacement']==1 and counts['pre_reset_before_pending_error']==2,counts
    assert counts['absent_toolkit_preserved_packet']>=64 and partial>=5,(counts,partial)
    assert len(errors)>=7,errors
    return dict(counts=dict(counts),source_states=dict(states),physics_modes=dict(modes),solved_contact_rows=contacts,solved_drive_rows=drives,completed_grind_observations=observations,partial_owner_writes=partial,distinct_dynamic_normals=len(normal),distinct_toolkits=len(toolkit),distinct_physical_packets=len(packets),errors=dict(errors))

def settings_failures(original):
    import copy
    queries=[('physics_reckoning','default','DynamicSpeedMaxDeltaGraphZ','words')]+[('physics_reckoning','default',n,'float')for n in('DynamicSpeedDamping','DynamicUpVectorDamping','DynamicSpeedMaxDelta','DynamicSpeedMaxDeltaXScale')]
    # Corrupt every later read as well. The full original owner must report the
    # first normal-settings read before entering its grind settings loader.
    for at,query in enumerate(queries):
        fixture=copy.deepcopy(original)
        for q in queries[at:]:settings_probe.mutate(fixture,q,dict(type='EA::Reflection::Int32',data='00000000')if q[3]=='float'else dict(type='EA::Reflection::Float',data='00000000'))
        settings_probe.mutate(fixture,('physics_grinds','default','ExitLeanAngleVsTime','words'),dict(type='EA::Reflection::Float',data='00000000'))
        yield query,fixture

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--samples',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    for n in('result.json','first-divergence.json'):(out/n).unlink(missing_ok=True)
    blob,cases=preflight();(out/'input.bin').write_bytes(blob);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    if a.preflight:print(json.dumps(dict(histories=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(blob),units=len(UNITS),module_aliases=len(aliases())),indent=2));return
    stock=a.assets.resolve()/'private/stock';settings=out/'settings.native';physical=out/'physics.native';settings.write_bytes(grind.converter.encode_settings(stock/'skater-collections.json'));physical.write_bytes(grind.converter.encode_physics_skeletons(stock/'physics-skeletons.json'));identity=json.loads((stock/'physics-skeletons.json').read_text())['source_sha256'];native,reference=build(out,a.target_dir)
    expected=subprocess.check_output([str(reference),str(a.assets.resolve())],input=blob);actual=subprocess.check_output([str(native),str(settings),str(physical),str(a.samples.resolve()/'native/rig.skate'),identity],input=blob);(out/'reference.bin').write_bytes(expected);(out/'native.bin').write_bytes(actual)
    if expected!=actual:
        first=next((n for n,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));(out/'first-divergence.json').write_text(json.dumps(dict(byte=first,reference_bytes=len(expected),native_bytes=len(actual)),indent=2)+'\n');raise AssertionError('PlayerInputRuntime differs')
    proof=coverage(expected,cases);negative=[];original=json.loads((stock/'skater-collections.json').read_text())
    for n,(query,fixture)in enumerate(settings_failures(original)):
        root=out/f'settings-failure-{n}';path=root/'private/stock/skater-collections.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(fixture));settings.write_bytes(grind.converter.encode_settings(path))
        x=subprocess.check_output([str(reference),str(root),'--settings-only']);y=subprocess.check_output([str(native),str(settings),'--settings-only']);assert x==y,(query,x,y);r=protocol.Reader(x);assert r.word()==0;error=bytes(r.word()for _ in range(r.word())).decode();assert error and r.at==len(x);negative.append(dict(query=query,error=error))
    (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');result=dict(passed=True,histories=len(cases),commands=sum(len(c['commands'])for c in cases),exact_bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),coverage=proof,negative_settings=negative,boundary='Complete canonical input owner and verbatim source prepare_grind/process_skeleton callbacks, actual static grind queries/materials, actual loaded physical/pose/IK/shared solve/toolkit/publication. Full global coordinator and successful whole-player teleport reset remain external. Fresh source TrajectorySelector false publication is checked; actual CompleteBatch true publication is still pending its separately assigned producer.');(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
