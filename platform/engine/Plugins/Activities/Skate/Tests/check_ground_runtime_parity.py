#!/usr/bin/env python3
"""Concrete original Ground owner composition over live pose, IK and body owners.

Only the root coordinator may compile or execute this guarded proof. Handplant,
trajectory continuation and the later SkeletonAir capture are explicit pending
phase boundaries; no ground collision/force/geometry result is fabricated.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import random
import shutil
import struct
import subprocess
import check_skeleton_input_runtime_parity as dispatcher
import check_ground_board_parity as board
import check_ground_control_settings_parity as controls
from reference_build import build_probe
from check_animation_playback_parity import Stream,attribute
PLUGIN=dispatcher.PLUGIN
GROUND_UNITS=('GroundRuntime','GroundStateRuntime','GroundInput','GroundPumpingRuntime','GroundHangGeometry','GroundMotion','GroundOutput','GroundSettings','GroundBoard','GroundTorqueSettings','GroundControlSettings','Steering','SteeringWobbleSettings','SpeedWobble','GroundForce','Manual','Braking','Push','GroundPropulsion','SpeedModel','GroundDrag','GroundState','GroundStateCorrections','GroundCorrections','SlideFriction','Straighten','Heading','AntiFlip','GroundLaunchInfo','Pumping','WipeoutRequests','AirMath','AirStateSettings','SkeletonController','OffboardGrabCache')
UNITS=tuple(dict.fromkeys((*dispatcher.UNITS,*GROUND_UNITS,
                          'DeckAngularCorrections','GroundContactResponse',
                          'RidingCollisionResponse')))
OPERATIONS=('tick','exit','select_profile','seed_ground_state','seed_grab_cache','invalidate_grab','enter_reset_grab','replace_world','reset_board_fields','revert_pumping','seed_lifecycle')
CORE='crates/skate-core/src/'
HOST='crates/skate-host/src/physics/'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def source(path):return dispatcher.source(path)
def schema():
 definitions,sources=board.schema()
 for name,path in {'PumpingState':CORE+'riding/pumping/state.rs','PumpingSettings':CORE+'riding/pumping/settings.rs','PumpingMode':CORE+'riding/pumping/settings.rs','SelectorInput':CORE+'air/trajectory/types.rs'}.items():
  s=source(path);match=re.search(r'\bstruct '+name+r'\s*\{',s);assert match,name;body=re.sub(r'//[^\n]*','',s[match.end():s.index('\n}',match.end())]);definitions[name]=[(f,re.sub(r'\s+','',k))for f,k in re.findall(r'^\s*(?:pub(?:\([^)]*\))?\s+)?(\w+)\s*:\s*([^,\n]+),',body,re.M)]
 return definitions

def helpers():
 d=copy.deepcopy(schema())
 # u8 is widened only in the observation transport. The original declaration
 # and all owner arithmetic remain unchanged; restore the reader's Rust cast.
 d['PumpingState']=[(f,'u32'if k=='u8'else k)for f,k in d['PumpingState']]
 cpp,rust,settings=board.protocol_helpers(d)
 cpp=re.sub(r'\bInput\b','GroundInputReader',cpp);cpp=re.sub(r'\bOutput\b','GroundOutputWriter',cpp)
 cpp=re.sub(r'\bSelectorInput\b','AirSelectorInput',cpp)
 rust=rust.replace('intentional_pumping:i.word(),','intentional_pumping:i.word() as u8,')
 return cpp,rust,settings

def aliases():
 result=dispatcher.aliases()
 for name in ('corrections','update','input','services','launch','surface'):
  result[f'atelier-host/src/physics/ground_runtime/{name}.rs']=HOST+f'ground_runtime/{name}.rs'
 result['atelier-host/src/physics/offboard/grab-scene/mod.rs']=HOST+'offboard/grab_scene.rs'
 result['atelier-host/src/physics/offboard/grab-scene/collision.rs']=HOST+'offboard/grab_scene/collision.rs'
 result['atelier-host/src/physics/biped_ground/grab_runtime/selection.rs']=HOST+'biped_ground/grab_runtime/selection.rs'
 return result

# Additional observation/seed transports live in their original privacy scope;
# each numerical source prefix remains the complete frozen byte sequence.
def prepare_oracle(probe):
 base=dispatcher.prepare_oracle(PLUGIN/'Tests/Reference/skeleton_input_runtime_probe.rs').split('fn main(){',1)[0]
 cpp,rust,settings=helpers()
 ground=source(HOST+'ground_runtime/mod.rs')
 for name in ('settings','state','entry','pumping'):
  extra=settings if name=='settings'else ''
  if name=='state':extra='\npub(super) fn observe(o:&mut crate::Output,s:&GroundState){crate::observe_PhysicsGroundState(o,&s.state);crate::observe_PumpingState(o,&s.pumping);o.words(s.wobble.0);crate::observe_TruckSteeringState(o,&s.steering);crate::observe_SpeedModelState(o,&s.speed);crate::observe_ManualState(o,&s.manual);o.float(s.heading_previous);o.word(s.entered as u32);o.floats(s.output_settings.pushable_speed_terms_4_8);o.float(s.output_settings.mode_speed_threshold_0);o.words(s.auto_push_enabled.map(u32::from));super::entry::observe(o,&s.entry_settings);super::pumping::observe(o,&s.pumping_settings);}\n'
  if name=='entry':extra='\npub(super) fn observe(o:&mut crate::Output,s:&EntrySettings){o.floats([s.deck_angular_drag,s.powerslide_exit,s.landing_strength,s.landing_offset]);}\n'
  if name=='pumping':extra='\npub(super) fn observe(o:&mut crate::Output,s:&GroundPumping){crate::observe_PumpingSettings(o,&s.settings);for m in s.modes{crate::observe_PumpingMode(o,&m.controller);o.float(m.unintentional_scalar);}}\n'
  ground=ground.replace('mod '+name+';', 'mod '+name+'{\n'+source(HOST+'ground_runtime/'+name+'.rs')+'\n'+extra+'}\n')
 ground+='\npub fn observe_settings(o:&mut crate::Output,s:&GroundSettings){settings::observe_GroundSettings(o,s);}pub fn observe_state(o:&mut crate::Output,s:&GroundState){state::observe(o,s);}pub fn retained_normal(s:&GroundRuntime)->[f32;4]{s.retained_board_normal}pub fn runtime_settings(s:&GroundRuntime)->(&WallRideSettings,&CollisionResponseSettings,[f32;3]){(&s.wall_ride,&s.collision,[s.deck_center_to_truck,s.launch_cone_x,s.launch_cone_z])}\n'
 grab=source(HOST+'biped_ground/grab_runtime.rs')+'\n// GROUNDED_CACHE_TRANSPORT\n'
 modules='\npub mod ground_runtime{\n'+ground+'}\npub mod skeleton_controller{\n'+source(HOST+'skeleton_controller.rs')+'}\npub mod biped_ground{pub mod grab_runtime{\n'+grab+'}}\n'
 # Existing offboard possession owners coexist with the full original grab scene.
 base=base.replace('pub mod offboard{','pub mod offboard{#[path="grab-scene/mod.rs"]pub mod grab_scene;')
 where=base.index(' pub fn deck_frame(');base=base[:where]+modules+base[where:]
 # The shared output transport now retains the actual core wobble. Its single
 # trigger forwarding method is the unchanged host method82BF2F18.
 base=base.replace('pub struct Output{pub correction:', 'pub struct Output{pub wobble:skate_core::physics::skeleton_output::wobble::Wobble,pub correction:')
 base=base.replace('skeleton_output:physics::Output{correction:', 'skeleton_output:physics::Output{wobble:Default::default(),correction:')
 trigger,_=controls.trees.extract_block(source(HOST+'skeleton_output.rs'),'    pub fn trigger_wobble(')
 base=base.replace(' pub struct FrameNames{',' impl Output{'+trigger+'}\n pub mod skeleton_output{pub(crate) type SkeletonOutput=super::Output;}\n pub struct FrameNames{')
 # Add only actual loaded Ground owners to the physical transport. The histories
 # already owned by Animated/Physical/SkeletonInput remain authoritative.
 fields='pub ground:ground_runtime::GroundState,pub ground_runtime:ground_runtime::GroundRuntime,pub ground_settings:std::sync::Arc<ground_runtime::GroundSettings>,'
 base=base.replace('pub struct SkaterRuntime{','pub struct SkaterRuntime{'+fields)
 base=base.replace('let s=SkaterRuntime{','let s=SkaterRuntime{ground:physics::ground_runtime::GroundState::load(data,"normal",true).unwrap(),ground_runtime:physics::ground_runtime::GroundRuntime::load(data).unwrap(),ground_settings:physics::ground_runtime::GroundProfiles::load(data).unwrap().select(1,1).unwrap(),')
 # Ground Exit executes against those same bodies/materials/state owners.
 base=base.replace(' pub fn deck_frame(', ' pub mod ground_exit{\n'+source(HOST+'ground_exit.rs')+'}\n pub(crate) fn migration_ground_exit(p:&mut GamePhysics,s:&mut SkaterRuntime){ground_exit::exit(p,s)}\n pub fn deck_frame(')
 phase=source(HOST+'ground_phase.rs')
 phase_blocks=[]
 for marker in ('pub(crate) struct GroundEdge','pub(crate) struct GroundLifecycle','impl GroundLifecycle','pub(crate) fn reset_board_state(','pub(crate) fn enter_components('):
  block,_=controls.trees.extract_block(phase,marker);phase_blocks.append(block)
 phase_module='\npub mod ground_phase{use super::ground_runtime::{GroundEntryTargets,GroundLaunchInfo};use super::skeleton_controller::SkeletonControllerState;use skate_core::{math::Vector3,physics::skeleton_body::SkeletonCollisionMode};\n'+ '\n'.join(phase_blocks)+'}\n'
 base=base.replace(' pub struct GroundLifecycle{pub board_animated_290:u8}',' pub(crate) use ground_phase::GroundLifecycle;'+phase_module)
 base=base.replace('ground_lifecycle:physics::GroundLifecycle{board_animated_290:0}','ground_lifecycle:physics::GroundLifecycle::new()')
 # The selector input is an unchanged field adapter. Other Air owners remain
 # explicit phase boundaries; only its actual stock GrindLockDist is needed.
 selector,_=controls.trees.extract_block(source(HOST+'air_phase/input.rs'),'pub(crate) fn selector_input(')
 air='pub mod air_phase{use super::{GamePhysics,SkaterRuntime};use skate_core::air::trajectory::SelectorInput;'+selector+'}\n'
 base=base.replace(' pub fn deck_frame(',air+' pub fn deck_frame(')
 base=base.replace('pub struct SkaterRuntime{','pub struct SkaterRuntime{pub air_settings:crate::GroundAirDistances,')
 base=base.replace('let s=SkaterRuntime{','let s=SkaterRuntime{air_settings:crate::GroundAirDistances{grind_lock_distance:crate::difficulty::NATIVE_MODES.map(|m|data.float("physics_mode",m,"GrindLockDist").unwrap())},')
 own=probe.read_text().replace('// GENERATED_GROUND_PROTOCOL',rust)
 cache=re.search(r'// CACHE_PRIVACY_BEGIN\n(.*?)// CACHE_PRIVACY_END',own,re.S).group(1)
 own=re.sub(r'// CACHE_PRIVACY_BEGIN\n.*?// CACHE_PRIVACY_END','',own,flags=re.S)
 tuning='\nmod tuning {\n'+source('crates/skate-host/src/tuning.rs')+'\n}\n'
 return (base+tuning+own).replace('// GROUNDED_CACHE_TRANSPORT',cache)

def default(kind,definitions):
 if kind=='u8':return 0
 if board.primitive(kind):return board.default_value(kind,definitions)
 return {field:default(child,definitions)for field,child in definitions[kind]}

def encode_value(stream,kind,value,definitions):
 if kind=='u8':stream.word(value)
 elif board.primitive(kind):board.encode_value(stream,kind,value,definitions)
 else:
  for field,child in definitions[kind]:encode_value(stream,child,value[field],definitions)

def value_words(kind,definitions):
 if kind=='u8':return 1
 if board.primitive(kind):return board.word_count(kind,definitions)
 return sum(value_words(child,definitions)for _,child in definitions[kind])

def corpus():
 definitions=schema();records=[];cases=[];rng=random.Random(0x82d37c88)
 fs=dispatcher.adjusted.f;bits=dispatcher.adjusted.bits
 def attr(name,value=.1,payload=None,kind=0):
  a=attribute(kind=kind,status=5);a['name']=dispatcher.animation_input.trees.name(name);a['payload']=[bits(value),None,None,None,None,None]if payload is None else payload
  words=a['name']+[a['kind'],a['status'],a['sequence']&0xffffffff,a['begin'],a['end']]
  for word in a['payload']:words+=[int(word is not None)]+([word]if word is not None else [])
  return words
 def affine(seed):
  angle=.11*seed;c,s=math.cos(angle),math.sin(angle)
  return fs([c,0,-s,0,1,0,s,0,c,0,(0,.03,.2,.45)[seed%4],0])
 def world(seed):
  slope=(0,.1,-.15,.35)[seed%4];points=[(-4,-4*slope-.025,-4),(4,4*slope-.025,-4),(4,4*slope-.025,4),(-4,-4*slope-.025,4)];words=[2]
  for ids,tag in (((0,2,1),1),((0,3,2),12)):words+=fs([v for n in ids for v in points[n]])+[0,0x10,tag]
  if seed%3==2:
   # Actual vertical faces and a raised ledge reach wall/swept geometry through
   # original BoardWorld queries, independently of any retained Ground seed.
   triangles=[[(.35,-.1,-1),(.35,1.8,-1),(.35,1.8,1)],[(.35,-.1,-1),(.35,1.8,1),(.35,-.1,1)]]
   for n,triangle in enumerate(triangles):words+=fs([v for p in triangle for v in p])+[0,0x10,40+n]
   words[0]+=2
  return words
 def tick(seed,k,enter=False,mode=None,pose=None,missing=False,solve=True):
  mode=seed%5 if mode is None else mode;pose=(seed+k//5)%4 if pose is None else pose
  flags2468=(0x2000,0x02002000,0x20002000,0x1002000,0x8102000)[k%5]
  flags2472=(0,0x800,0x1000,0x0c000000,0x00800000)[(seed+k)%5]
  flags2476=(0,2,0x40000000,0x00400000)[k%4]
  attrs=[attr('Balance',(-.35,0,.35,1)[k%4]),attr('Turn',(-.5,.25,.75)[k%3]),attr('BodySpin',.04),attr('Brake',.2 if k%5==2 else 0)]
  if k%3==0:attrs.append(attr('push_contact',kind=3,payload=dispatcher.animation_input.trees.name('RightToeBase')+[bits(3.5)]))
  if missing:attrs.insert(1,attr('Balance',payload=[None]*6))
  words=[0,pose,bits((1/60,1/120,1/30)[seed%3]),201,200,1,flags2468,flags2472,flags2476,0,0,0,0x8800000,int(k%4==0),len(attrs)]
  words+=[v for a in attrs for v in a]+fs([-.25,.15,0,0,.4]+[0]*13)+[3,0]
  previous=(201,101,503,702)[(seed+k)%4];category=500 if previous==503 else 700 if previous==702 else 200
  words += [pose,int(enter),previous,category,mode]+fs([k/60,.5,(seed%5)*.25,.2 if k%4 else .8,(-.02,.02)[k%2],.125,.05])+[k+2]+fs([.125 if seed%2 else 0])+[(0,0x80000000)[k%5==0],(0,0x08000000)[seed%2]]+fs([.35,.025,0,0])+fs([-.5,0,-1,.5,0,1])+[int(k%7!=6),int(seed%4==3),int(solve)]
  return words
 def encoded(kind,value):
  stream=Stream();encode_value(stream,kind,value,definitions);return list(struct.unpack('<'+'I'*(len(stream.data)//4),stream.data))
 def seed_state(seed,entered=True):
  state=board.initial_state(definitions,seed);state.update(flag_2708=bool(seed%2),vector_2688=[.25,.5,.75,0],collision_countdown_2652=(0,.25,.5)[seed%3],hang_detection_frames_2740=(0,19,20)[seed%3],hung_wipeout_frames_2748=(0,20,21)[seed%3],anti_flip_nudge_frames_2752=(0,13,14)[seed%3]);pump=default('PumpingState',definitions);pump.update(record_valid=True,intentional_pumping=seed%3,pumping=.2,pump_acceleration=.125,absorption=.1)
  return [3]+encoded('PhysicsGroundState',state)+encoded('PumpingState',pump)+[int(entered)]
 def add(label,commands,seed=0,mode=1,surface=1):
  tuning=default('TrainerTuning',definitions)
  for field,kind in definitions['TrainerTuning']:tuning[field]=(1,.75,1.25)[seed%3]if kind=='f32'else bool(seed%2)
  raw=affine(seed)+world(seed)+[seed%2,mode,surface]+encoded('TrainerTuning',tuning)+[len(commands)]+[v for command in commands for v in command]
  records.append(struct.pack('<'+'I'*len(raw),*raw));cases.append(dict(index=len(cases),label=label,mode=mode,surface=surface,commands=[command[0]for command in commands]))
 for mode in range(5):
  for surface in range(1,6):
   seed=mode*5+surface;commands=[[4,seed,0xff],[10,0,6,0,int(seed%2),1,1,1]+fs([.4,-.25])+[2]+fs([.6])+[1]]
   for k in range(18):
    if k==5:commands.append(seed_state(seed))
    if k==7:commands.extend([[9]+fs([0]),[7]+world(seed+1)])
    if k==10:commands.extend([[1],[6],[8]])
    if k==12:commands.append([2,(mode+1)%5,surface%5+1])
    commands.append(tick(seed,k,enter=k in(0,11),mode=mode))
   commands.extend([[1],[5],[6]])
   add('all25 stock profiles: actual pose/world/IK, entry/update/exit, force/material/pumping and retained owner histories',commands,seed,mode,surface)
 for seed in range(36):
  commands=[[4,seed,seed*7%256],seed_state(seed),tick(seed,0,enter=True)]+[tick(seed,k)for k in range(1,12)]+[[1],[9]+fs([(-.5,0,.5)[seed%3]])]
  add('sloped and vertical-world geometry with retained Ground controller/correction/pump histories',commands,seed,seed%5,seed%5+1)
 for seed in range(12):
  add('Ground before-entry failure preserves actual ProcessData/body/pose prefix',[tick(seed,0,enter=False)],seed)
  add('Invalid trajectory selector mode preserves Ground entry and pose prefix',[tick(seed,0,enter=True,mode=0xffffffff)],seed)
  add('Missing processed attribute preserves concrete source partial publication',[tick(seed,0,enter=True,missing=True)],seed)
  add('Missing actual hierarchy preserves concrete source wake/collision prefix',[tick(seed,0,enter=True,pose=4)],seed)
 for mode,surface in ((5,1),(0xffffffff,1),(1,0),(1,6),(1,0xffffffff)):
  add('Invalid profile selection retains active stock settings',[[2,mode,surface],tick(0,0,enter=True)],0)
 for seed in range(12):
  add('Complete grab cache Invalidate/EnterReset preserve source record payloads and nested completions',[[4,seed,flags]for flags in(0,0x3f,0x40,0x80,0xff)]+[[5],[6],[4,seed,0xff],[6],[5]],seed)
 return struct.pack('<I',len(records))+b''.join(records),cases

def preflight():
 raw,cases=corpus();words=struct.unpack('<'+'I'*(len(raw)//4),raw);at=1;definitions=schema()
 def world():
  nonlocal at
  count=words[at];at+=1+12*count
 for case in cases:
  at+=12;world();at+=3+value_words('TrainerTuning',definitions);count=words[at];at+=1;assert count==len(case['commands'])
  for op in case['commands']:
   assert words[at]==op,(case,at);at+=1
   if op==0:
    at+=13;attrs=words[at];at+=1
    for _ in range(attrs):
     at+=10
     for _ in range(6):present=words[at];at+=1+bool(present)
    at+=20+29
   elif op==3:at+=value_words('PhysicsGroundState',definitions)+value_words('PumpingState',definitions)+1
   elif op==7:world()
   else:at+={1:0,2:2,4:2,5:0,6:0,8:0,9:1,10:12}[op]
 assert at==len(words),(at,len(words))
 for unit in UNITS:assert(PLUGIN/f'Source/AtelierSkate/Private/Simulation/{unit}.cpp').is_file(),unit
 return raw,cases

def build(output,target):
 live=PLUGIN/'Source/AtelierSkate/Private/Simulation';simulation_source=output/'simulation-source'
 if simulation_source.exists():shutil.rmtree(simulation_source)
 simulation_source.mkdir()
 for path in live.glob('*.h'):shutil.copy2(path,simulation_source/path.name)
 for unit in UNITS:shutil.copy2(live/f'{unit}.cpp',simulation_source/f'{unit}.cpp')
 prefixes=[PLUGIN/f'Tests/Simulation/skeleton_{name}_probe.cpp'for name in('body','collision','constraint')]+[PLUGIN/f'Tests/Simulation/{name}_probe.cpp'for name in('physical_simulation_runtime','adjusted_skeleton','skeleton_input_runtime')]
 dispatcher_helpers,_=dispatcher.helpers();ground_helpers,_,_=helpers()
 prefix=''.join(path.read_text().split('int main(',1)[0].split('int main()',1)[0].replace('// GENERATED_PROTOCOL',dispatcher_helpers)for path in prefixes)
 own=PLUGIN/'Tests/Simulation/ground_runtime_probe.cpp';combined=simulation_source/own.name
 combined.write_text('#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wunused-function"\n'+prefix+'\n#pragma clang diagnostic pop\n'+own.read_text().replace('// GENERATED_GROUND_PROTOCOL',ground_helpers))
 binary=output/'ground-runtime-cpp'
 subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(simulation_source),*[str(simulation_source/f'{unit}.cpp')for unit in UNITS],str(combined),'-o',str(binary)],check=True)
 rust_prefixes=[PLUGIN/f'Tests/Reference/skeleton_{name}_probe.rs'for name in('body','collision','constraint')]
 prefix=''.join(path.read_text().split('fn main(){',1)[0]for path in rust_prefixes).replace('use crate::{','use skate_core::{').replace('skeleton_root::inverse_rigid,','').replace('solver::{packed,JointConstraint}','solver::{JointConstraint}').replace('#[path="physics/solver/packing.rs"] mod skeleton_constraint_packing;','mod skeleton_constraint_packing{use skate_core::physics::solver::{packed,JointConstraint};use crate::{RetailDriveRows,RetailContactJacobian};use skate_core::physics::rigid_body::RetailReactionCorrections;#[path="packing.rs"]mod original;pub fn drive(r:&RetailDriveRows)->packed::Drive{original::drive(r)}}')
 own_rs=PLUGIN/'Tests/Reference/ground_runtime_probe.rs';generated=output/'ground-runtime-combined.rs';generated.write_text(prefix+prepare_oracle(own_rs));reference=build_probe(output,'ground-runtime-reference',generated,target,bevy=True,extra_sources=aliases())
 (output/'simulation-provenance.json').write_text(json.dumps(dict(simulation_source_sha256={path.name:digest(path)for path in simulation_source.iterdir()},probe_sha256={path.name:digest(path)for path in[*prefixes,*rust_prefixes,own,own_rs]}),indent=2)+'\n')
 return binary,reference

def observe_ground(words,definitions):
 reader=board.Words(words);result={}
 def value(kind):
  if kind=='u8':return reader.word()
  if board.primitive(kind):return reader.value(kind,definitions)
  return {field:value(child)for field,child in definitions[kind]}
 result['state']=value('PhysicsGroundState');result['pumping']=value('PumpingState');result['wobble']=reader.take(8)
 for name,kind in (('steering','TruckSteeringState'),('speed','SpeedModelState'),('manual','ManualState')):result[name]=value(kind)
 result['heading']=reader.word();result['entered']=reader.word();result['output_settings']=reader.take(3);result['auto_push']=reader.take(5);result['entry_settings']=reader.take(4);result['pumping_settings']=value('PumpingSettings');result['pumping_modes']=[dict(controller=value('PumpingMode'),unintentional=reader.word())for _ in range(5)]
 result['settings']=value('GroundSettings');result['retained_normal']=reader.take(4);result['wall_ride']=reader.take(23);result['collision_settings']=value('CollisionResponseSettings');result['runtime_scalars']=reader.take(3);result['contact']=reader.take(14);result['collision_force']=reader.take(12)if reader.word()else None
 result['lifecycle']=reader.take(10);result['skeleton_wobble']=reader.take(5);result['wipeout']=reader.take(34+34+5);result['launch']=value('GroundLaunchInfo')if reader.word()else None
 cache={};cache['queries']=[reader.take(4+4+16+4+3+5)for _ in range(reader.word())]
 def records():
  result=[]
  for _ in range(reader.word()):result.append(dict(words=reader.take(72),id=reader.word(),points=reader.take(4*reader.word()),approach=reader.take(4*reader.word()),word60=reader.word()))
  return result
 cache['query_result']=records()if reader.word()else None;cache['pending']=records();cache['validated']=records()
 cache['validation']=[dict(fraction=reader.word(),assembly=reader.word()if reader.word()else None)if reader.word()else None for _ in range(reader.word())]if reader.word()else None
 cache['requests']=[reader.take(2)if reader.word()else None for _ in range(2)]
 cache['data']=[]
 for _ in range(2):
  if reader.word():cache['data'].append(dict(words=reader.take(72),id=reader.word(),points=reader.take(4*reader.word()),approach=reader.take(4*reader.word()),word60=reader.word()))
  else:cache['data'].append(None)
 cache['ready']=reader.take(2);cache['interactable_request']=reader.take(5*13)if reader.word()else None
 cache['interactable_result']=(reader.word()if reader.word()else None)if reader.word()else 'unset';cache['latched']=reader.word();cache['flags']=reader.word();cache['query_position']=reader.take(4);cache['validation_position']=reader.take(4);result['grab']=cache
 trace=board.Words(reader.take(reader.word()));result['trace']=[]
 while trace.at<len(trace.words):result['trace'].append(dict(id=trace.word(),args=trace.take(trace.word())))
 trace.done();reader.done();return result

def decode(data,cases):
 words=struct.unpack('<'+'I'*(len(data)//4),data);at=0;coverage=Counter();definitions=schema();frames=[]
 for case in cases:
  index,count,size=words[at:at+3];assert index==case['index']and count==len(case['commands']);case['first_output_word']=at;case['output_words']=size+3;end=at+size+3;cursor=at+3;initial_end=cursor+1+words[cursor];ground_words=words[initial_end-1];initial=observe_ground(words[initial_end-1-ground_words:initial_end-1],definitions);cursor=initial_end;case['outputs']=[]
  for op in case['commands']:
   assert words[cursor]==op;length=words[cursor+1];payload=words[cursor+2];assert payload<=length-1;row_end=cursor+length+2;ground_words=words[row_end-1];owner=observe_ground(words[row_end-1-ground_words:row_end-1],definitions)
   row=dict(operation=OPERATIONS[op],first_output_word=cursor,output_words=length+2,owner_output_words=payload,ground=owner)
   if op==0:
    row['success']=bool(words[cursor+3]);coverage['tick_success'if row['success']else'tick_failure']+=1
    for trace in owner['trace']:
     coverage[f'trace_{trace["id"]}']+=1
     if trace['id']==9:coverage[('Animated','Collision','Ordinary')[trace['args'][0]]]+=1
    if 'before-entry failure'in case['label']or'Invalid trajectory selector mode'in case['label']or'Missing processed attribute'in case['label']or'Missing actual hierarchy'in case['label']:assert not row['success'],case
   coverage[OPERATIONS[op]]+=1;case['outputs'].append({key:value for key,value in row.items()if key!='ground'});frames.append(dict(case=index,**row));cursor=row_end
  assert cursor==end,(cursor,end,case);at=end
 assert at==len(words)
 assert coverage['tick_success']and coverage['tick_failure']and coverage['Ordinary']and coverage['trace_3']and coverage['trace_4']and coverage['exit']
 return dict(coverage),frames

def loader_fixtures(original):
 # These new concrete host loaders supplement the accepted full Ground profile
 # loader proof. Each changed field is still resolved by original Collections.
 queries=[]
 for kind,names in (('curve',('PumpVsVel','PumpVsTime','MinCrouchVsGroundAngle','CompressionVsGroundAngle','CompressionVsDeckAngle')),('float',('PumpEffectDamping','MinChangeInCOMBeforePumping','MaxDeltaHeightAllowedPerFrame','CompressionGroundScalar','CompressionDeckScalar','AngularSpeedDamping'))):queries += [(0,('physics_pumping','default',name,kind))for name in names]
 for mode in controls.MODES:
  queries += [(0,('physics_mode',mode,name,'float'))for name in('Hash_9D1AEE3D7D8A4A7','Hash_D77AFD320B6241C5','PumpEffectFactorAbsorption','PumpEffectFactor','UnintentionalPumpScalar')]
  queries.append((0,('physics_mode',mode,'AutoPushEnabled','bool')))
 queries += [(0,(category,'default',name,'float'))for category,names in [('physics_push',('MaxPushableSpeed_CameraDelta','MaxPushableSpeed','Hash_501D5581043D7D3C')),('physicsdeck',('DeckAngularDrag',)),('physics_manual',('PowerslideExitScalar',)),('physics_feet',('LandingOnDeckEffectScalar','LandingOnDeckOffset'))]for name in names]
 queries += [(1,query)for query in controls.fields(5)]
 queries += [(1,(category,'default',name,'float'))for category,names in [('physics_trajectory',('ConeAngleX','ConeAngleZ')),('physics_grinds',('DeckCenterToTruck',)),('physics_collision',('MaxVelDelta','ForceYOffset','CollisionForceScalar','TargetDisplacementVel'))]for name in names]
 queries.append((1,('physics_collision','default','CollisionTorqueVsAngle','fixed_curve')))
 fixtures=[dict(label=f'stock loader {stage}',stage=stage,data=original)for stage in range(3)]
 for stage,query in queries:
  for mutation in('missing','type'):
   data=copy.deepcopy(original);chain,name=controls.resolve(data,query)
   if mutation=='missing':
    for record in chain:record['fields'].pop(name,None)
    # Remove readable and hashed inherited copies, retaining all unrelated data.
    for record in data['collections']:
     if controls.identity(record['class'])==controls.identity(query[0]):
      for field in list(record['fields']):
       if controls.identity(field)==controls.identity(query[2]):record['fields'].pop(field)
   else:chain[-1]['fields'][name]=controls.invalid(query)
   fixtures.append(dict(label=f'{stage}:{query[0]}/{query[1]}/{query[2]}:{mutation}',stage=stage,data=data,query=query,mutation=mutation))
 # Exercise full profile load failure through its actual first reader as well.
 for query in (('physics_steering','default','HardTurnIncrease','float'),('physics_mode','test','MotorEnabled','bool'),('physics_surfaces','veryslow','FrictionVsSpeedNew','curve')):
  data=copy.deepcopy(original);chain,name=controls.resolve(data,query);chain[-1]['fields'][name]=controls.invalid(query);fixtures.append(dict(label=f'full profiles:{query}',stage=2,data=data,query=query,mutation='type'))
 return fixtures

def run_loaders(output,cpp,reference,assets):
 original=json.loads((assets/'private/stock/skater-collections.json').read_text());results=[];root=output/'loader-fixtures';root.mkdir(exist_ok=True)
 for index,fixture in enumerate(loader_fixtures(original)):
  fixture_root=root/str(index);path=fixture_root/'private/stock/skater-collections.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(fixture['data'],separators=(',',':'))+'\n');simulation=fixture_root/'settings.simulation';simulation.write_bytes(dispatcher.adjusted.physical.converter.encode_settings(path));input_bytes=struct.pack('<I',fixture['stage']);expected=subprocess.check_output([str(reference),str(fixture_root),'--load-only'],input=input_bytes);actual=subprocess.check_output([str(cpp),str(simulation),'--load-only'],input=input_bytes)
  (fixture_root/'reference.bin').write_bytes(expected);(fixture_root/'cpp.bin').write_bytes(actual)
  if expected!=actual:raise AssertionError(dict(loader_fixture=fixture['label'],reference=expected.hex(),cpp=actual.hex()))
  success=bool(struct.unpack_from('<I',expected)[0]);assert success==('stock loader'in fixture['label']),fixture['label'];results.append(dict(label=fixture['label'],success=success,bytes=len(expected),output_sha256=hashlib.sha256(expected).hexdigest(),collections_sha256=digest(path),input_sha256=hashlib.sha256(input_bytes).hexdigest()))
 return results

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--assets',type=Path,required=True);parser.add_argument('--samples',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--target-dir',type=Path,required=True);parser.add_argument('--preflight',action='store_true');args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True);inputs,cases=preflight();(output/'input.bin').write_bytes(inputs)
 for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
 own=PLUGIN/'Tests/Reference/ground_runtime_probe.rs';generated=prepare_oracle(own)
 (output/'original-source-preflight.rs').write_text(generated)
 if args.preflight:
  print(json.dumps(dict(streams=len(cases),commands=sum(len(case['commands'])for case in cases),ticks=sum(case['commands'].count(0)for case in cases),input_bytes=len(inputs),input_sha256=hashlib.sha256(inputs).hexdigest(),units=len(UNITS),aliases=len(aliases()),generated_original_bytes=len(generated.encode())),indent=2));return
 assets=args.assets.resolve();stock=assets/'private/stock';settings=output/'settings.simulation';physical=output/'physics.simulation';settings.write_bytes(dispatcher.adjusted.physical.converter.encode_settings(stock/'skater-collections.json'));physical.write_bytes(dispatcher.adjusted.physical.converter.encode_physics_skeletons(stock/'physics-skeletons.json'));identity=json.loads((stock/'physics-skeletons.json').read_text())['source_sha256'];cpp,reference=build(output,args.target_dir)
 expected=subprocess.check_output([str(reference),str(assets)],input=inputs);actual=subprocess.check_output([str(cpp),str(settings),str(physical),str(args.samples.resolve()/'simulation/rig.skate'),identity],input=inputs);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual);coverage,frames=decode(expected,cases);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');(output/'ground-state-trace.json').write_text(json.dumps(frames,indent=2)+'\n')
 if expected!=actual:
  first=next((n for n,(a,b)in enumerate(zip(expected,actual))if a!=b),min(len(expected),len(actual)))//4;case=next((case for case in cases if case['first_output_word']<=first<case['first_output_word']+case['output_words']),None);report=dict(passed=False,first_word=first,case=case,reference_bytes=len(expected),cpp_bytes=len(actual));(output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
 loaders=run_loaders(output,cpp,reference,assets);result=dict(passed=True,streams=len(cases),commands=sum(len(case['commands'])for case in cases),exact_words=len(expected)//4,coverage=coverage,loaders=loaders,input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),comparison='Full original GroundState entry/update/exit, stock profiles, pumping/input/corrections and concrete GroundRuntime forces/world geometry over actual hierarchy, FootIK, collision feedback, persistent bodies/targets and shared solver. All owner fields/publication/partial writes compared exactly.',limitations='GroundPhase Handplant dispatch, Air trajectory Launch/Update continuation and later SkeletonAir capture are explicitly ordered pending owner boundaries with argument observations, not neutral results. Processed flags/actions/edge observations and world triangles are supplied producer boundaries. Complete PlayerInput/coordinator/grab Scene query/selection execution remain separate integration proofs.',simulation_provenance_sha256=digest(output/'simulation-provenance.json'))
 (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()
