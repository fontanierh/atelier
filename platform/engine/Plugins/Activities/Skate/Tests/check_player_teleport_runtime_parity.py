#!/usr/bin/env python3
"""Complete original reset_player over the actual canonical mutable owners.

Build/run only through the root coordinator's render guard. --preflight performs
framing/source/helper inspection without compiling or executing either probe.
"""
import argparse
from collections import Counter,OrderedDict
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
import check_footplant_parity as foot
import check_player_input_runtime_parity as player
import check_ground_runtime_parity as ground
import check_physics_animation_input_parity as attributes
import player_input_protocol as protocol
from camera_reference_build import frozen_sources
from check_animation_playback_parity import Stream,attribute,bits
from check_graph_parity import element,original_graph
from session_parity import REFERENCE_REVISION,digest
PLUGIN=foot.PLUGIN
CODE=foot.CODE
UNITS=tuple(dict.fromkeys((*foot.UNITS,*player.UNITS,*ground.UNITS,'PlayerTeleportRuntime')))
OPS=('initial_packets','reset_player','initial_retained_history','horizontal_spawn','submit_real_wheel_query','invalid_imported_ik_bone','actual_solve_feedback')
BLOCKS=('packets','ground','controller_dispatcher','collision','grab','plant_latches','shared','riding','query_batches')
HOST='crates/skate-host/src/physics/'

def source(path):return player.source(path)
def extract(path,marker):return foot.extraction(path,marker)
def block(raw,marker):return player.block(raw,marker)
def canonical_helpers():return player.skeleton.helpers()
def ground_defs():
 d=ground.schema();return OrderedDict((n,d[n])for n in('PhysicsGroundState','PumpingState','TruckSteeringState','SpeedModelState','ManualState'))
def ground_helpers():
 cpp=[];rust=[]
 for name,fields in ground_defs().items():
  cpp.append(f'void Observe(Output& o,const {name}& s){{'+''.join(protocol.observe_expr(k,'s.'+f,'cpp')for f,k in fields)+'}')
  rust.append(f'fn observe_{name}(o:&mut Output,s:&{name}){{'+''.join(protocol.observe_expr(k,'s.'+f,'rust')for f,k in fields)+'}')
 return '\n'.join(cpp),'\n'.join(rust)

def callback_literal(raw):
 start=raw.index('    let mut callbacks = Callbacks {');end=raw.index('\n    };',start)+len('\n    }');return raw[start:end]

def generated_observer():
 p=PLUGIN/'Tests/Reference/player_teleport_runtime_observer.rs';raw=p.read_text();coll=(PLUGIN/'Tests/Reference/skeleton_collision_probe.rs').read_text();physical=(PLUGIN/'Tests/Reference/physical_simulation_runtime_probe.rs').read_text()
 funcs='\n'.join(block(coll,'fn '+n+'(')for n in('collision_settings_out','collision_flags','collision_feedback','collision_mode'))
 raw=raw.replace('// GENERATED_COLLISION_OBSERVERS',funcs).replace('// GENERATED_RIDING_OBSERVER',block(physical,'fn riding_out('))
 original=source(HOST+'input_phase.rs');literal=callback_literal(original)
 literal=literal[literal.index('{')+1:literal.rindex('}')]
 literal=re.sub(r'\bphysics\b','p',literal);literal=re.sub(r'\bskater\b','s',literal)
 literal=literal.replace('        collision,','        collision: c,').replace('globals: &s.animation.packet.hierarchy,','globals: &globals,').replace('attributes: s.animation.attributes.entries(),','attributes: &attrs,').replace('        actions,','        actions: &mut actions,').replace('        packet,','        packet: &packet,').replace('teleported: false,','teleported,')
 raw=raw.replace('// GENERATED_ORIGINAL_CALLBACK_BINDINGS',literal)
 world=block((PLUGIN/'Tests/Reference/footplant_observer.rs').read_text(),'fn world(')
 raw=raw.replace('fn loaded(',world+'\nfn loaded(')
 return raw,dict(original_callback_binding_sha256=hashlib.sha256(callback_literal(original).encode()).hexdigest(),observer_template_sha256=digest(p),collision_observer_sha256=digest(PLUGIN/'Tests/Reference/skeleton_collision_probe.rs'),riding_observer_sha256=digest(PLUGIN/'Tests/Reference/physical_simulation_runtime_probe.rs'))

def reference_plan(output):
 original,report=frozen_sources(output);observed=output/'observed-source'
 if observed.exists():shutil.rmtree(observed)
 shutil.copytree(original,observed);crate=observed/'atelier-host';host=original/'crates/skate-host/src'
 hprefix,hmeta=extract(PLUGIN/'Tests/Reference/handplant_observer.rs','pub(super) fn run(')
 lprefix,lmeta=extract(PLUGIN/'Tests/Reference/handplant_lifecycle_observer.rs','pub(super) fn run(')
 aprefix,ameta=extract(PLUGIN/'Tests/Reference/air_reckoning_observer.rs','fn core_input(')
 fprefix,fmeta=extract(PLUGIN/'Tests/Reference/footplant_observer.rs','pub(super) fn run(')
 htail=b'\npub(super) fn shared(o:&mut Output,p:&GamePhysics,s:&SkaterRuntime){snapshot(o,p,s)}\n}\npub(crate) fn migration_footplant_shared_snapshot(o:&mut crate::Output,p:&super::GamePhysics,s:&super::SkaterRuntime){migration::shared(o,p,s)}\n'
 atail=b'\npub(super) fn observe(o:&mut Output,a:&AirReckoning,r:&RidingOutputs){out_state(o,&a.state);for w in *r.body_spin.words(){o.word(w)}for w in r.reckoning.migration_air_reckoning_words(){o.word(w)}out_frames(o,&r.reckoning_frames);}\n}\npub(crate) fn migration_lifecycle_observe(o:&mut crate::Output,a:&AirReckoning,r:&RidingOutputs){migration::observe(o,a,r)}\n'
 ftail=b'\npub(super) fn observe(o:&mut Output,f:&Footplant){owner(o,f)}\n}\npub(crate) fn migration_teleport_observe(o:&mut crate::Output,f:&Footplant){migration::observe(o,f)}\npub(crate) fn migration_teleport_start(f:&mut Footplant,c:[f32;4],v:[f32;4])->u32{ground::migration_footplant_start(f,c,v)}\n'
 _,proto=canonical_helpers();_,gproto=ground_helpers();observer,meta=generated_observer()
 animation_observer=block(source(HOST+'animation_input.rs'),'    pub fn finish_output_publication(') # source-preservation audit; method itself is never replaced
 anim='\npub(crate) fn migration_teleport_observe(o:&mut crate::Output,s:&AnimationInput){crate::observe_ScalarAttributeInputs(o,&s.fields);crate::observe_ExtendedAttributes(o,&s.extra);crate::observe_ContactEventState(o,&s.contacts);crate::observe_AnimationControlOutput(o,&s.output);crate::observe_JumpAttributeState(o,&s.cached_jump);crate::observe_FinalizationInput(o,&s.settings);for v in s.height_overrides{o.word(v as u32)}o.word(s.right_toe as u32);o.word(s.bone_names.len()as u32);for n in &s.bone_names{o.words(n.0)}}\n'
 gstate='\npub(super) fn migration_teleport_observe(o:&mut crate::Output,s:&GroundState){crate::observe_PhysicsGroundState(o,&s.state);crate::observe_PumpingState(o,&s.pumping);o.words(s.wobble.0);crate::observe_TruckSteeringState(o,&s.steering);crate::observe_SpeedModelState(o,&s.speed);crate::observe_ManualState(o,&s.manual);o.float(s.heading_previous);o.word(s.entered as u32)}\n'
 groot='\npub(crate) fn migration_teleport_observe(o:&mut crate::Output,s:&GroundState,r:&GroundRuntime){state::migration_teleport_observe(o,s);o.floats(r.retained_board_normal)}\n'
 cache= re.search(r'// CACHE_PRIVACY_BEGIN\n(.*?)// CACHE_PRIVACY_END',(PLUGIN/'Tests/Reference/ground_runtime_probe.rs').read_text(),re.S).group(1)
 # The existing wire adapter captures explicit initial cache state only; its
 # retained geometry cannot act as a completed scene query in this proof.
 cache=cache.replace('pub fn seed(','pub fn migration_teleport_initial(').replace('pub fn observe(','pub fn migration_teleport_observe(')
 cache+='\nimpl Owner{pub(crate) fn migration_teleport_initial(&mut self,seed:u32,flags:u8){migration_teleport_initial(self,seed,flags)}}\n'
 extensions={
 'physics/handplant.rs':b'\n'+hprefix+lprefix+htail+b'\npub(crate) fn migration_teleport_start(f:&mut Handplant){let c=contact::Candidate{point:[0.137,0.731,-0.317,0.],edge:skate_core::physics::grind_contact::Primitive{start:[-2.,0.731,-0.317,0.],end:[2.,0.731,-0.317,0.],owner:17},side:1};f.launch(c,[0.137,0.731,-0.317,0.],[2.731,0.137,0.317,0.],[0.,0.,1.,0.],[0.,0.,1.,0.],[0.,0.,1.,0.]);}\n',
 'physics/air_reckoning.rs':b'\n'+aprefix+atail,
 'physics/footplant.rs':b'\n'+fprefix+ftail,
 'physics/foot_ik.rs':b'\npub(crate) fn migration_teleport_bone(f:&mut FootIk,part:usize,value:usize)->usize{std::mem::replace(&mut f.bone_indices[part],value)}\n',
 'physics/footplant/ground.rs':b'\npub(crate) fn migration_footplant_start(f:&mut Footplant,c:[f32;4],v:[f32;4])->u32{f.start(c,v)}\n',
 'physics/air_trajectory/mod.rs':b'\n'+(PLUGIN/'Tests/Reference/footplant_trajectory_observer.rs').read_bytes(),
 'physics/input_phase.rs':b'\n'+observer.encode(),
 'physics/input_teleport.rs':b'\npub(crate) fn migration_player_teleport_horizontal(m:NativeMatrix)->NativeMatrix{horizontal_spawn(m)}\n',
 'physics/animation_input.rs':anim.encode(),
 'physics/ground_runtime/state.rs':gstate.encode(),
 'physics/ground_runtime/mod.rs':groot.encode(),
 'physics/biped_ground/grab_runtime.rs':cache.encode(),
 'physics/riding_outputs.rs':b'\nimpl RidingOutputs{pub(crate) fn migration_teleport_queries(&self,o:&mut crate::Output){o.word(self.pending_wheel_queries.is_some()as u32);if let Some(v)=self.pending_wheel_queries{for h in v{o.word(h.is_some()as u32);if let Some(h)=h{o.float(h.fraction);o.floats([h.normal.x,h.normal.y,h.normal.z]);o.word(h.surface_tag);}}}self.probes.migration_teleport_queries(o)}}\n',
 'physics/riding_outputs/probes.rs':b'\nimpl BoardProbes{pub(crate) fn migration_teleport_queries(&self,o:&mut crate::Output){fn vector(o:&mut crate::Output,v:Vector3){o.floats([v.x,v.y,v.z]);}fn hit(o:&mut crate::Output,h:Option<BoardProbeHit>){o.word(h.is_some()as u32);if let Some(h)=h{vector(o,h.point);vector(o,h.normal);o.word(h.surface_tag);}}o.word(self.wall_line.is_some()as u32);if let Some(l)=self.wall_line{vector(o,l.start);vector(o,l.end);}o.word(self.pending.is_some()as u32);if let Some(p)=&self.pending{hit(o,p.deck);o.word(p.wall.is_some()as u32);if let Some(h)=p.wall{hit(o,h)}}}}\n',
 'physics.rs':b'\npub(crate) fn migration_player_teleport_run(a:&std::path::Path,f:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{input_phase::migration_player_teleport_run(a,f,i,o)}\n'}
 staged={}
 for p in sorted(host.rglob('*.rs')):
  rel=p.relative_to(host).as_posix()
  if rel in('lib.rs','main.rs'):continue
  raw=p.read_bytes();extra=extensions.get(rel,b'');dest=crate/'src'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw+extra);assert dest.read_bytes()[:len(raw)]==raw
  staged[rel]=dict(original_prefix_bytes=len(raw),original_prefix_sha256=digest(p),append_sha256=hashlib.sha256(extra).hexdigest(),generated_sha256=digest(dest))
 core={'crates/skate-core/src/riding/ground_orientation.rs':foot.lifecycle.air.CORE_OBSERVER.encode(),
 'crates/skate-core/src/air/trajectory/selector.rs':b'\nimpl TrajectorySelector{pub fn migration_footplant_stage(&self)->[u32;2]{[u32::from(self.pass),u32::from(self.adjusted_on_vert)]}}\n',
 'crates/skate-core/src/physics/skeleton_motion.rs':b'\nimpl SkeletonMotion{pub fn migration_lifecycle_previous(&self)->f32{self.previous_board_at_y}}\n',
 'crates/skate-core/src/physics/skeleton_output/wobble.rs':b'\nimpl Wobble{pub fn migration_teleport_selected(&self)->bool{self.selected_landing_curves}}\n',
 'crates/skate-core/src/physics/grind_air.rs':b'\nimpl GrindAir{pub fn migration_teleport_words(&self)->[u32;30]{let mut w=[0;30];let mut n=0;for v in [self.offset_delta,self.offset,self.angle_delta,self.angles]{for x in v{w[n]=x.to_bits();n+=1;}}w[16]=self.selected_kind.is_some()as u32;w[17]=self.selected_kind.unwrap_or(0)as u32;for i in 0..12{w[18+i]=self.headings[i].to_bits();}w}}\n'}
 for rel,extra in core.items():p=observed/rel;raw=(original/rel).read_bytes();p.write_bytes(raw+extra);assert p.read_bytes()[:len(raw)]==raw
 template=PLUGIN/'Tests/Reference/player_teleport_runtime_probe.rs';code=template.read_text().replace('// GENERATED_CANONICAL_PROTOCOL',proto+'\n'+gproto)
 imports='use skate_core::{animation::skeleton_input::{scalar_attributes::{ScalarAttributeInputs,AnimationControlOutput},extended_attributes::ExtendedAttributes,attribute_finalization::{JumpAttributeState,FinalizationInput},contact_events::ContactEventState},physics::manual::state::ManualState,riding::{grounded::state::data::PhysicsGroundState,pumping::state::PumpingState,steering::TruckSteeringState,speed_model::SpeedModelState}};\n'
 code=code.replace('use std::io::{Read,Write};',imports+'use std::io::{Read,Write};');(crate/'src/migration_probe.rs').write_text(code)
 cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text()+'''
skate-core={path="../crates/skate-core"}
skate-data={path="../crates/skate-data"}
skate-net={path="../crates/skate-net"}
half="2.7.1"
bevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}
[[bin]]
name="player-teleport-reference"
path="src/migration_probe.rs"
''')
 report.update(staged_host_original_prefixes=staged,extracted_observer_prefixes=[hmeta,lmeta,ameta,fmeta],appended_core_observers={rel:dict(original_prefix_sha256=digest(original/rel),generated_sha256=digest(observed/rel),observer_sha256=hashlib.sha256(extra).hexdigest())for rel,extra in core.items()},probe_sha256=digest(template),generated_probe_sha256=digest(crate/'src/migration_probe.rs'),reset_original_sha256=digest(original/(HOST+'input_teleport.rs')),observer_binding=meta,scope='Complete unchanged original host/core; actual Callbacks::reset_player, all GamePhysics/SkaterRuntime stock owner constructors. Append-only wire, read-only observers and original private method access wrappers. No numeric method replacement.')
 return original,observed,crate,cargo,report

def build_reference(output,target):
 original,observed,crate,cargo,report=reference_plan(output)
 subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(cargo),'--target-dir',str(target.resolve()),'--bin','player-teleport-reference'],check=True)
 for rel,sha in report['original_source_sha256'].items():assert digest(original/rel)==sha;raw=(original/rel).read_bytes();assert(observed/rel).read_bytes()[:len(raw)]==raw
 binary=output/'player-teleport-reference';shutil.copy2(target.resolve()/'release/player-teleport-reference',binary);report['binary_sha256']=digest(binary);(output/'reference-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return binary

def simulation_plan(output):
 snapshot=output/'simulation-source'
 if snapshot.exists():shutil.rmtree(snapshot)
 snapshot.mkdir();hashes={}
 for p in[*sorted(CODE.glob('*.h')),*[CODE/(u+'.cpp')for u in UNITS]]:shutil.copy2(p,snapshot/p.name);hashes[p.name]=digest(snapshot/p.name)
 numeric=PLUGIN/'Tests/Simulation/handplant_probe.cpp';raw=numeric.read_text();at='  float Float() { return plant_math::Float(Word()); }'
 wire='''template<std::size_t N>std::array<std::uint32_t,N> Words(){std::array<std::uint32_t,N> v;for(auto& x:v)x=Word();return v;}
 template<class T,std::size_t N,class F>std::array<T,N> Array(F f){std::array<T,N> v;for(auto& x:v)x=f(*this);return v;}
 template<class T,class F>std::optional<T> Optional(F f){return Word()?std::optional<T>{f(*this)}:std::nullopt;}
 AnimationAttribute Attribute(){AnimationAttribute a;a.name=Words<5>();a.kind=std::uint8_t(Word());a.status=std::uint8_t(Word());a.sequence_id=std::int32_t(Word());a.begin_time=Float();a.end_time=Float();for(auto& v:a.payload){if(Word())v=Word();else v.reset();}return a;}
'''
 assert at in raw;raw=raw.replace(at,wire+at);(snapshot/'handplant_probe.cpp').write_text(raw)
 life,lmeta=extract(PLUGIN/'Tests/Simulation/handplant_lifecycle_probe.cpp','int main(');(snapshot/'handplant_lifecycle_helpers.inc').write_bytes(life)
 fp,fmeta=extract(PLUGIN/'Tests/Simulation/footplant_probe.cpp','int main(');(snapshot/'footplant_helpers.inc').write_bytes(fp)
 cpp,_=canonical_helpers();gcpp,_=ground_helpers();p=PLUGIN/'Tests/Simulation/player_teleport_runtime_probe.cpp';probe=p.read_text().replace('// GENERATED_CANONICAL_PROTOCOL',cpp).replace('// GENERATED_GROUND_PROTOCOL',gcpp)
 collision=(PLUGIN/'Tests/Simulation/skeleton_collision_probe.cpp').read_text();coll=[]
 for n in('OutSettings','OutFlags','OutFeedback','OutMode'):
  fn=block(collision,'void '+n+'(');fn=fn.replace('void '+n+'(','void Reset'+n+'(Output& o,');fn=re.sub(r'\bOutSettings\(','ResetOutSettings(o,',fn);fn=re.sub(r'\bOutFlags\(','ResetOutFlags(o,',fn);fn=re.sub(r'\bOut\(','ResetOut(o,',fn);coll.append(fn)
 probe=probe.replace('// GENERATED_COLLISION_OBSERVERS','\n'.join(coll))
 riding=block((PLUGIN/'Tests/Simulation/physical_simulation_runtime_probe.cpp').read_text(),'void OutGround(').replace('void OutGround(','void ResetOutGround(Output& o,');riding=re.sub(r'\bOut\(','ResetOut(o,',riding);probe=probe.replace('// GENERATED_RIDING_OBSERVER',riding)
 cache=(PLUGIN/'Tests/Simulation/ground_runtime_probe.cpp').read_text();functions=[]
 for n in('GroundGrabRecord','SeedGroundGrab','OutGroundGrabRecord','OutGroundGrab'):
  prefix='OffboardGrabRecord 'if n=='GroundGrabRecord'else 'void ';fn=block(cache,prefix+n+'(')
  if n.startswith('Out'):
   fn=fn.replace('void '+n+'(','void '+n+'(Output& o,');fn=fn.replace('OutGroundGrabRecord(r)','OutGroundGrabRecord(o,r)').replace('OutGroundGrabRecord(*r)','OutGroundGrabRecord(o,*r)');fn=re.sub(r'\bOut\(','ResetOut(o,',fn)
  functions.append(fn)
 probe=probe.replace('// GENERATED_GRAB_OBSERVER','\n'.join(functions));(snapshot/'player_teleport_runtime_probe.cpp').write_text(probe)
 hashes.update({p.name:digest(p),'handplant_probe.original':digest(numeric)})
 return snapshot,dict(immutable_simulation_sources=hashes,generated_probe_sha256=digest(snapshot/'player_teleport_runtime_probe.cpp'),generated_wire_helper_sha256=digest(snapshot/'handplant_probe.cpp'),extracted_helper_prefixes=[lmeta,fmeta],units=UNITS)

def build_simulation(output):
 snapshot,report=simulation_plan(output);binary=output/'player-teleport-simulation'
 subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'player_teleport_runtime_probe.cpp'),'-o',str(binary)],check=True)
 report['binary_sha256']=digest(binary);(output/'simulation-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return binary

def zero(kind,defs):
 if kind.startswith('&'):return zero(kind[1:],defs)
 a=protocol.array(kind)
 if a:return[zero(a[0],defs)for _ in range(a[1])]
 if protocol.option(kind):return None
 if kind in('RawVector','AttributeName'):return[0]*(4 if kind=='RawVector'else 5)
 if kind=='RawMatrix':return[[0]*4 for _ in range(4)]
 if kind in('bool','f32','u8','u16','u32','i32','u64','NativeReferenceBase'):return 0
 return{f:zero(t,defs)for f,t in defs[kind]}

def corpus():
 defs,_=protocol.declarations();cases=[];records=[]
 def attr(name,value=.137,kind=0,payload=None):
  a=attribute(kind=kind,status=5);a['name']=attributes.trees.name(name);a['payload']=[bits(value),None,None,None,None,None]if payload is None else payload;return a
 def packets(seed,mode=0,state=201):
  q=zero('PlayerInputState',defs);p=zero('PhysicalPlayerInput',defs);v=zero('ProcessedPhysicsInput',defs)
  q.update(flags_1296=0xffffffff,previous_spin_input_1360=.731,spin_same_direction_frames_1324=seed+3,dismount_request_frames_1332=seed+7,time_on_ground_1352=.137,signed_ground_time_1356=-.317,manager_1856_counter_320=seed+11)
  q['queued_vector_1280']=[bits(x)for x in(.137,.317,.731,-.0)]
  p['state'].update(state_16=state,category_12=state//100*100,identifier_8=1000+seed,flag_61=1)
  p['state']['surface_height_32']=.731
  v.update(flags_2468=(0x2000,0x02002000,0x20002000,0x8102000)[seed%4],flags_2472=0,flags_2476=0,flags_2480=0,flags_2484=0,flags_2488=0,state_2508=state,category_2512=state//100*100,filtered_state_2524=1,state_variant_index_2528=mode,timestep_2604=(1/60,1/120,1/30)[seed%3],gravity_2648=9.81,scalar_2612=.317,scalar_2616=.731,scalar_2652=.137,wheel_count_2556=4)
  for idx in(0,4):v['vectors_464_480_496_512_528'][idx]=[bits(x)for x in(0,1,0,0)]
  v['vectors_544_560_592_608'][0]=[bits(x)for x in(0,1,0,0)]
  for idx in(2,3):v['vectors_544_560_592_608'][idx]=[bits(x)for x in(.137,.317,.731,0)]
  v['flags_2472']=(0,0x180,1,0x400)[seed%4]
  return dict(op=0,player=q,physical=p,processed=v)
 def reset(seed,k=0,pose=None,attrs=None,initial=False,target=None):
  packet=zero('AnimationInputPacket',defs);packet['publication'].update(timestep=(1/60,1/120,1/30)[seed%3],stance_byte=seed%2,truck_tightness=.35)
  packet['publication']['flags_10375_10496_10784'][1]=seed%2;packet['flags_10932']=(0,0x08800000,0x12000000)[k%3]
  angle=.137*(seed+k);c,s=math.cos(angle),math.sin(angle)
  target=target or [[c,.317,-s,.731],[0,1,0,-.317],[s,.731,c,-.137],[.137*k,.317*(seed%3-1),-.731*k,-.0 if seed%2 else 1]]
  attrs=attrs if attrs is not None else[attr('Balance',(-.35,0,.35)[k%3]),attr('BodySpin',.03),attr('Crouch',.2),attr('Turn',-.317)]
  if k%3==0:attrs=attrs+[attr('push_contact',kind=3,payload=attributes.trees.name('RightToeBase')+[bits(.731)])]
  return dict(op=1,target=target,packet=packet,pose=seed%4 if pose is None else pose,attributes=attrs,actions=[-.25,.25,0,0,.75]+[0]*13,initial_teleported=initial)
 def add(label,commands):
  cases.append(dict(index=len(cases),label=label,commands=commands))
 for seed in range(24):
  commands=[]
  for k in range(8):commands += [packets(seed+k,mode=k%5,state=(201,500,702,601)[k%4]),dict(op=2,seed=seed+k,override=seed%2==1)] + ([dict(op=4)]if k%2==0 else[]) + [reset(seed,k)]
  add('actual reset across stock poses/modes; retained histories are independent initial state',commands)
 for seed in range(6):add('real solved contact/feedback collision snapshot refresh',[packets(seed,state=500 if seed%2 else 201),dict(op=2,seed=seed+3,override=False),dict(op=6),reset(seed,k=1),packets(seed,mode=99),dict(op=6),reset(seed,k=1,initial=seed%2==1)])
 for mode in(5,99,0xffffffff):add('real early SelectPhysicsMode failure',[packets(1,mode),dict(op=2,seed=9,override=False),reset(1)])
 for tag,pose,attrs in [('missing scalar',0,[attr('Balance',.5),attr('Brake',payload=[None]*6)]),('missing event',0,[attr('Balance',.5),attr('push_contact',kind=3,payload=[None]*6)]),('missing hierarchy',4,[]),('truncated hierarchy',5,[])]:
  for initial in(False,True):add('real ProcessData partial failure: '+tag,[packets(1),dict(op=2,seed=11,override=True),reset(1,pose=pose,attrs=attrs,initial=initial)])
 for initial in(False,True):add('real UpdateTeleport GeneralUpdate/IK failure after completed ProcessData',[packets(1),dict(op=2,seed=7,override=False),dict(op=5,part=23,value=0xffffffff),reset(1,k=1,initial=initial)])
 for x,z in((0,0),(-0.,0),(.001,0),(.0010000001639127731,0),(.0009999999310821295,0),(.0007,.0007),(1e-20,-1e-20),(1,1),(-1,-1),(float('inf'),1),(float('nan'),1)):
  m=[[.137,.317,.731,-.0],[0,1,0,.731],[x,.731,z,-.317],[.137,-.317,.731,-.0]];add('original horizontal spawn exact boundary',[dict(op=3,target=m)])
 w=Stream();w.word(len(cases))
 for case in cases:
  world=foot.lifecycle.numeric.world(0);case['world_words']=world
  for word in world:w.word(word)
  w.word(len(case['commands']))
  for cmd in case['commands']:
   w.word(cmd['op'])
   if cmd['op']==0:
    for name,key in(('PlayerInputState','player'),('PhysicalPlayerInput','physical'),('ProcessedPhysicsInput','processed')):protocol.encode(w,name,cmd[key],defs)
   elif cmd['op']==1:
    for v in cmd['target']:
     for x in v:w.float(x)
    packet=cmd['packet'];protocol.encode(w,'AnimationPacketFields',packet['publication'],defs);protocol.encode(w,'ExternalPhysicsInput',packet['external_physics_10512'],defs)
    for field,kind in defs['AnimationInputPacket']:
     if not kind.startswith('&'):protocol.encode(w,kind,packet[field],defs)
    w.word(cmd['pose']);w.word(len(cmd['attributes']))
    for a in cmd['attributes']:
     for x in a['name']+[a['kind'],a['status'],a['sequence'],a['begin'],a['end']]:w.word(x)
     for v in a['payload']:
      w.word(v is not None)
      if v is not None:w.word(v)
    for x in cmd['actions']:w.float(x)
    w.word(cmd['initial_teleported'])
   elif cmd['op']==2:w.word(cmd['seed']);w.word(cmd['override'])
   elif cmd['op']==5:w.word(cmd['part']);w.word(cmd['value'])
   elif cmd['op']==3:
    for v in cmd['target']:
     for x in v:w.float(x)
 return bytes(w.data),cases

class Reader(foot.lifecycle.Reader):
 def state(self):
  assert self.word()==len(BLOCKS);v={};self.sections={}
  for n in BLOCKS:size=self.word();at=self.at;v[n]=self.take(size);self.sections[n]=[at,self.at]
  return v

def decode(raw,cases):
 r=Reader(raw);assert r.word()==len(cases);frames=[]
 for c in cases:
  c['first_word']=r.at;assert r.word()==len(c['commands']);previous=r.state();rows=[]
  for cmd in c['commands']:
   at=r.at;assert r.word()==cmd['op'];error=r.status();extra=r.take(r.word());s=r.state();rows.append(dict(op=cmd['op'],error=error,extra=extra,state=s,previous=previous,sections=r.sections.copy(),first_word=at,last_word=r.at));previous=s
  c['last_word']=r.at;frames.append(rows)
 assert r.at==len(r.words);return frames

def packet_observation(words):
 defs,_=protocol.declarations();r=protocol.Reader(struct.pack('<'+'I'*len(words),*words));return {n:r.value(n,defs)for n in('PlayerInputState','PhysicalPlayerInput','ProcessedPhysicsInput')}

def ground_observation(words):
 d=ground_defs();r=protocol.Reader(struct.pack('<'+'I'*len(words),*words));v={n:r.value(n,d)for n in('PhysicsGroundState','PumpingState')};v['wobble']=[r.word()for _ in range(8)]
 for n in('TruckSteeringState','SpeedModelState','ManualState'):v[n]=r.value(n,d)
 v['heading']=r.word();v['entered']=r.word();v['retained_normal']=[r.word()for _ in range(4)];assert r.at==len(words)*4;return v

def coverage(frames,cases):
 counts=Counter();errors=Counter();successful=0;late=0;initial_true=0;activation=set();headings=set();fullreset=0;requests=set();queryretained=0;refreshed_collision=0;entered=set();late_ik=0
 for rows,case in zip(frames,cases):
  for row,cmd in zip(rows,case['commands']):
   counts[OPS[cmd['op']]]+=1
   if cmd['op']!=1:continue
   s=row['state'];old=row['previous'];pack=packet_observation(s['packets']);q,p,v=(pack[n]for n in('PlayerInputState','PhysicalPlayerInput','ProcessedPhysicsInput'))
   assert q['previous_spin_input_1360']==0 and q['manager_1856_counter_320']==0 and q['queued_vector_1280']==[0]*4
   assert q['spin_same_direction_frames_1324']==0 and q['dismount_request_frames_1332']==0
   assert s['controller_dispatcher'][:5]==[0]*5 and s['controller_dispatcher'][5:7]==[1,0]
   # Wobble cached-curve selection survives reset independently of landing flag.
   assert s['controller_dispatcher'][8:13]==[0,0,0,0,bits(1)] and s['controller_dispatcher'][13]==old['controller_dispatcher'][13]
   assert s['controller_dispatcher'][14:17]==[int(bool(row['error'])and row['error']!='IK original joint is absent from the current pose'),0,0]
   assert s['controller_dispatcher'][17:49]==[0]*32
   assert s['query_batches']==old['query_batches'];queryretained+=old['query_batches'][0]
   current=ground_observation(s['ground']);previous=ground_observation(old['ground']);assert current['TruckSteeringState']['activation_time']==previous['TruckSteeringState']['activation_time'];assert current['TruckSteeringState']['deck_tilt']==0 and current['TruckSteeringState']['targets']==[0,0]
   for key in('PhysicsGroundState','PumpingState','wobble','SpeedModelState','ManualState','heading','entered'):assert current[key]==previous[key],key
   activation.add(tuple(current['TruckSteeringState']['activation_time']));entered.add(current['entered'])
   now=s['plant_latches'][-9:-1];before=old['plant_latches'][-9:-1];assert now[2:6]==before[2:6];refreshed_collision+=now!=before
   assert now[:2]==[0,0] and now[-1]==0
   late_ik+=row['error']=='IK original joint is absent from the current pose'
   # Footplant 139 words: genuine Start produced the curve before this reset;
   # FullReset clears readiness and retains that curve/result/selected geometry.
   footwords=s['plant_latches'][:139];prior=old['plant_latches'][:139]
   assert footwords[0]==0 and footwords[1:33]==prior[1:33] and footwords[81:97]==prior[81:97]
   assert footwords[-13:]==prior[-13:];fullreset+=1
   assert s['plant_latches'][-1]==(1 if row['error']is None or cmd['initial_teleported']else 0)
   requests.add(tuple(s['plant_latches'][139:173]));headings.add(tuple(s['riding'][-9:-2]))
   if row['error']:
    errors[row['error']]+=1;late+=s['shared']!=old['shared'];initial_true+=cmd['initial_teleported']
   else:
    successful+=1;assert s['plant_latches'][139+34+34+1]==bits(.4)
    assert p['teleport_output']is None
 assert successful>=100 and fullreset>=100 and late>=8 and initial_true>=4
 assert len(errors)>=4 and any('physics mode' in e for e in errors)
 assert queryretained>=20 and len(requests)>=1 and refreshed_collision>=6 and entered=={0,1} and len(activation)>=1 and late_ik==2
 return dict(operations=dict(counts),successes=successful,partial_owner_failures=late,retained_true_latch_failures=initial_true,real_error_counts=dict(errors),retained_query_batches=queryretained,fullplant_resets=fullreset,actual_collision_refreshes=refreshed_collision,entered_states_retained=sorted(entered),late_ik_failures=late_ik)

def preflight(raw,cases):
 defs,_=protocol.declarations();r=protocol.Reader(raw);assert r.word()==len(cases)
 for c in cases:
  n=r.word();[r.word()for _ in range(n*18)];assert r.word()==len(c['commands'])
  for cmd in c['commands']:
   assert r.word()==cmd['op']
   if cmd['op']==0:
    for name in('PlayerInputState','PhysicalPlayerInput','ProcessedPhysicsInput'):r.value(name,defs)
   elif cmd['op']==1:
    for _ in range(16):r.word()
    r.value('AnimationPacketFields',defs);r.value('ExternalPhysicsInput',defs)
    for field,kind in defs['AnimationInputPacket']:
     if not kind.startswith('&'):r.value(kind,defs)
    assert r.word()==cmd['pose'];assert r.word()==len(cmd['attributes'])
    for a in cmd['attributes']:
     for _ in range(10):r.word()
     for _ in range(6):
      if r.word():r.word()
    for _ in range(19):r.word()
   elif cmd['op']in(2,5):r.word();r.word()
   elif cmd['op']==3:
    for _ in range(16):r.word()
 assert r.at==len(raw)
 for u in UNITS:assert(CODE/(u+'.cpp')).is_file(),u
 observer,_=generated_observer();assert 'callbacks.reset_player('in observer and 'GENERA'not in observer


def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in('assets','samples','output','target-dir'):p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 for name in('result.json','first-divergence.json'):(out/name).unlink(missing_ok=True)
 raw,cases=corpus();preflight(raw,cases);(out/'input.bin').write_bytes(raw);(out/'cases.json').write_text(json.dumps(cases,indent=2,allow_nan=True)+'\n')
 if a.preflight:
  snapshot,report=simulation_plan(out);original,observed,crate,cargo,proof=reference_plan(out/'reference');(out/'simulation-preflight.json').write_text(json.dumps(report,indent=2)+'\n');(out/'reference-preflight.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(dict(histories=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(raw),units=len(UNITS)),indent=2));return
 fixtures=out/'fixtures';fixtures.mkdir(exist_ok=True);stock=a.assets.resolve()/'private/stock';(fixtures/'settings.simulation').write_bytes(foot.converter.encode_settings(stock/'skater-collections.json'));(fixtures/'physics.simulation').write_bytes(foot.converter.encode_physics_skeletons(stock/'physics-skeletons.json'))
 for k in('action','motion'):(fixtures/f'actor.{k}.reference').write_bytes(original_graph(element('state','idle')))
 identity=json.loads((stock/'physics-skeletons.json').read_text())['source_sha256'];reference=build_reference(out/'reference',a.target_dir);simulation=build_simulation(out)
 expected=subprocess.check_output([str(reference),str(a.assets.resolve()),str(fixtures)],input=raw);actual=subprocess.check_output([str(simulation),str(fixtures/'settings.simulation'),str(fixtures/'physics.simulation'),str(a.samples.resolve()/'simulation/rig.skate'),identity,str(a.assets.resolve())],input=raw)
 (out/'reference.bin').write_bytes(expected);(out/'simulation.bin').write_bytes(actual);frames=decode(expected,cases)
 if expected!=actual:
  at=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));word=at//4;case=next((c for c in cases if c['first_word']<=word<c['last_word']),None);row=next((r for rows in frames for r in rows if r['first_word']<=word<r['last_word']),None);section=next(((n,word-a)for n,(a,b)in(row['sections'].items()if row else[])if a<=word<b),None)
  failure=dict(byte=at,reference_bytes=len(expected),simulation_bytes=len(actual),case=case['index']if case else None,operation=row['op']if row else'initial',section=section,reference_hex=expected[max(0,at-16):at+32].hex(),simulation_hex=actual[max(0,at-16):at+32].hex());(out/'first-divergence.json').write_text(json.dumps(failure,indent=2)+'\n');raise AssertionError(failure)
 result=dict(passed=True,reference_revision=REFERENCE_REVISION,histories=len(cases),commands=sum(len(c['commands'])for c in cases),bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),input_sha256=hashlib.sha256(raw).hexdigest(),coverage=coverage(frames,cases),scope='Entire source reset_player composition over real stock physical board/skeleton/adjusted pose/IK/Ground/Footplant/Handplant/SkeletonAir/riding/wipeout/input owners; mutable callback collision and success latch; pure horizontal spawn boundaries; real attribute/mode/hierarchy error prefixes.',boundaries='Canonical player/physical/processed/animation packets and prior mutable histories are explicit initial/caller inputs. Actual authored hierarchy, stock settings and flat world are real owner constructors. Source global input coordinator/possession stop and complete scene respawn Observe/Request scheduling remain separate. No Ground.Enter or fabricated completed producer is used. Info logging is not asserted.')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
