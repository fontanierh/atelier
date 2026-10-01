#!/usr/bin/env python3
"""Entire pinned physical grind host over actual shared owners.

The root coordinator exclusively builds/runs this proof. --preflight performs
only corpus/source staging and framing audits, with no compiler or probe calls.
"""
import argparse
import ast
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import check_player_teleport_runtime_parity as reset
import check_player_grind_input_parity as input_grind
import player_input_protocol as protocol
from check_animation_playback_parity import Stream,bits
from check_graph_parity import element,original_graph
from session_parity import REFERENCE_REVISION,digest
PLUGIN=reset.PLUGIN
CODE=reset.CODE
HOST=reset.HOST
_actor=ast.parse((PLUGIN/'Tests/check_skater_animation_parity.py').read_text())
_actor_build=next(f for f in _actor.body if isinstance(f,ast.FunctionDef)and f.name=='build_native')
# Include the actor's later continuation extension as well as its first tuple.
ACTOR_UNITS=tuple(dict.fromkeys(v.value for n in ast.walk(_actor_build)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='files'for t in n.targets)for v in ast.walk(n.value)if isinstance(v,ast.Constant)and isinstance(v.value,str)))
ACTOR_UNITS=tuple(dict.fromkeys((*ACTOR_UNITS,'GraphActionPhysicalConditions')))
GRIND_UNITS=('GrindForces','GrindReckoning','GrindPost','GrindRuntimeSettings','GrindNames','GrindChromosome','GrindCamera','GrindRuntime','GrindRuntimeOutput','GrindRuntimeExecute','GrindRuntimeContact')
UNITS=tuple(dict.fromkeys((*reset.UNITS,*ACTOR_UNITS,*GRIND_UNITS,'WipeoutSettings','WipeoutObservations','WipeoutRuntime','PlayerStateSelector','PhysicalPhase')))
BLOCKS=('shared','grind','camera','settings')
OPS={0:'completed_packets',1:'real_reset',6:'real_solve_feedback',10:'enter',11:'exit',12:'real_toolkit',13:'advance',14:'fill',15:'chromosome',16:'camera',17:'post',18:'remove_toolkit',19:'remove_manager',20:'completed_manager',21:'jumper_cache',22:'actual_pose_and_publication',23:'queue_capacity',24:'invalid_ik_bone',25:'filtered',26:'stock_vertical_and_side',27:'all384_names',28:'retained_air_spin',30:'real_manager_world',31:'actual_world',32:'clear_queue',34:'real_wheel_publication'}

def block(raw,marker):return reset.block(raw,marker)
def reset_observer_cpp(prefix):
 # Repair only the copied observer's local writer/record name collision.
 # The original output order and every observed retained lane stay unchanged.
 lines=[line for line in prefix.splitlines()if 'const auto& o=r.reckoning;'in line]
 assert len(lines)==1
 old=lines[0];new=old.replace('const auto& o=r.reckoning;','const auto& reckoning=r.reckoning;').replace('o.','reckoning.')
 prefix=prefix.replace(old,new)
 marker='void ResetOutGround(Output& o,const PhysicalRidingOutputs& r)'
 assert prefix.count(marker)==1
 overload='void ResetOut(Output& o,const Basis3& value){for(const auto& column:value.columns)ResetOut(o,column);}\n'
 return prefix.replace(marker,overload+marker)
def provider_helpers():
 cpp=block((PLUGIN/'Tests/Native/player_grind_input_probe.cpp').read_text(),'PlayerGrindStaticProvider ReadProvider(')
 cpp=cpp.replace('i.Text()','TextRead(i)').replace('i.Vector()','Vec3{i.Float(),i.Float(),i.Float()}')
 cpp=re.sub(r'i.Array<float,(\d+)>\(\[\]\(Input& r\)\{return r.Float\(\);\}\)',r'i.Floats<\1>()',cpp).replace('Fail(error.c_str())','std::abort()')
 cpp='std::string TextRead(Input& i){std::string s;for(auto n=i.Word();n;--n)s+=char(i.Word());return s;}\n'+cpp
 rust=block((PLUGIN/'Tests/Reference/player_grind_input_probe.rs').read_text(),'fn read_provider(')
 return cpp,rust

def world_helpers():
 cpp=block((PLUGIN/'Tests/Native/player_grind_input_probe.cpp').read_text(),'WorldGeometry World(').replace('WorldGeometry World(','WorldGeometry GrindWorld(').replace('Fail(error)','std::abort()')
 rust=block((PLUGIN/'Tests/Reference/player_grind_input_probe.rs').read_text(),'fn fixture_world(')
 rust=rust.replace('fn fixture_world(kind:u32)->BoardWorld{','fn fixture_world(kind:u32)->BoardWorld{use skate_core::physics::{board_world::query_metadata::{QueryMetadata,QueryMesh,Bounds,QueryPool},drive_frames::RetailAffineTransform};')
 return cpp,rust

def native_plan(output):
 snap,report=reset.native_plan(output)
 for u in UNITS:shutil.copy2(CODE/(u+'.cpp'),snap/(u+'.cpp'))
 raw=(snap/'player_teleport_runtime_probe.cpp').read_text();prefix=reset_observer_cpp(raw[:raw.index('int main(')])
 initialization=raw[raw.index(' if(argc!=6)'):raw.index(' Input i{{')]
 construction=raw[raw.index(' for(unsigned c=0;c<count;++c){')+len(' for(unsigned c=0;c<count;++c){'):raw.index('const auto rows=i.Word();')]
 construction=construction.replace('World(i)','GrindWorld(i.Word())').replace('SkeletonControllerState controller;bool elapsed=false;std::uint8_t animated=0;','GroundPhaseLifecycle life;auto& controller=life.skeleton_controller;auto& elapsed=life.skeleton_elapsed_16505;auto& animated=life.board_animated_290;')
 cases=raw[raw.index(' case 0:'):raw.index(' case 2:')]
 solve=raw[raw.index(' case 6:'):raw.index(' case 5:')]
 template=PLUGIN/'Tests/Native/grind_runtime_probe.cpp';code=template.read_text().replace('// GENERATED_NATIVE_OWNER_PREFIX',prefix).replace('// GENERATED_NATIVE_OWNER_INITIALIZATION',initialization).replace('// GENERATED_NATIVE_OWNER_CONSTRUCTION',construction).replace('// GENERATED_NATIVE_PACKET_RESET_CASES',cases+solve).replace('// GENERATED_PROVIDER_READER',provider_helpers()[0]).replace('// GENERATED_GRIND_WORLD',world_helpers()[0])
 code=code.replace('std::uint32_t jump_fix=1000;GroundPhaseLifecycle life;','std::uint32_t jump_fix=1000;')
 # The reset bootstrap receives the SAME lifecycle aliases consumed by Grind.
 assert code.count('GroundPhaseLifecycle life;')==1
 (snap/'grind_runtime_probe.cpp').write_text(code)
 report.update(units=UNITS,immutable_native_sources={p.name:digest(p)for p in sorted(snap.glob('*.h'))+sorted(snap.glob('*.cpp'))},generated_probe_sha256=digest(snap/'grind_runtime_probe.cpp'))
 # Authorized declaration-only extraction; reconstruct the complete previous
 # frozen header and verify every byte, independent of its new include layout.
 transport=(snap/'GrindFilteredOutput.h').read_text();start=transport.index('struct GrindFilteredOutput\n{');end=transport.index('\n};',start)+3;declaration=transport[start:end]
 assert hashlib.sha256(declaration.encode()).hexdigest()=='0a4bdb6d4792e87633638ce03405c10e018edd3fe0b30b2b8307041fe3c0c78c'
 reconstructed=(snap/'GrindRuntime.h').read_text().replace('#include "GrindFilteredOutput.h"\n','').replace('class GrindRuntime\n',declaration+'\nclass GrindRuntime\n')
 assert hashlib.sha256(reconstructed.encode()).hexdigest()=='4e5ba1d484067134c644719482f5daf8ea6a0483017e2b40183c9bc3f55885f7'
 report['grind_transport_extraction']=dict(header_sha256=digest(snap/'GrindFilteredOutput.h'),declaration_sha256=hashlib.sha256(declaration.encode()).hexdigest(),previous_complete_header_sha256=hashlib.sha256(reconstructed.encode()).hexdigest(),scope='Identical transport declaration moved once; no fields/defaults/layout/methods/protocol/corpus change.')
 return snap,report

CHROMOSOME_OBSERVER='''
impl Chromosome{pub(crate) fn migration_grind_observe(&self,o:&mut crate::Output){fn pose(o:&mut crate::Output,p:ApproachPose){o.floats(p.right);o.floats(p.position);for v in p.feet{o.floats(v)}o.word(p.fakie as u32)}fn comp(o:&mut crate::Output,c:Option<Components>){o.word(c.is_some()as u32);if let Some(c)=c{o.words(c.0)}}o.word(self.history.len()as u32);for &p in &self.history{pose(o,p)}pose(o,self.saved);o.word(self.saved_fakie_initialized as u32);o.word(self.approach);o.word(self.previous_category);o.word(self.previous_kind.is_some()as u32);if let Some(v)=self.previous_kind{o.word(v as u32)}o.word(self.away_frames as u32);o.word(self.reversed as u32);o.word(self.orientation.is_some()as u32);if let Some(v)=self.orientation{o.word(v)}comp(o,self.pending);o.word(self.pending_frames as u32);comp(o,self.animation);comp(o,self.scoring);}}
'''
SUBSTATE_OBSERVER='''
impl Settings{pub(crate) fn migration_grind_observe(&self,o:&mut crate::Output){o.float(self.animated_board_threshold);let c=&self.collision;o.floats([c.maximum_velocity_delta,c.force_y_offset,c.force_scalar,c.target_displacement_velocity]);o.floats(c.torque_vs_angle.x);o.floats(c.torque_vs_angle.y);for mode in self.vertical{for family in mode{o.floats(family)}}}}
'''
RUNTIME_OBSERVER='''
pub(crate) fn migration_owner(o:&mut crate::Output,r:&Runtime,j:&skate_core::physics::grind_contact::manager::Jumper){for s in r.states{let a=s.output;for v in[a.direction,a.normal,a.across]{o.floats(v)}o.float(a.crouch);o.word(a.leaving as u32);o.word(a.substate);o.word(a.classification_104);o.word(a.just_jumped as u32);o.floats(a.jump_velocity);o.word(a.slide_wipeout as u32);o.floats(a.slide_impulse);o.words(a.tipslide_97_98_99.map(u32::from));o.matrix(s.frame);o.word(s.already_jumped as u32);o.word(s.updates as u32);o.word(s.leaving_updates as u32);o.word(s.preparing_jump as u32);}o.word(r.active.is_some()as u32);if let Some(f)=r.active{o.word(f as u32)}o.word(r.nonspecific_active as u32);o.word(r.nonspecific_jumped as u32);o.floats(r.nonspecific_jump_velocity);o.words(r.orientation_random.migration_words());o.word(r.manager.is_some()as u32);if let Some(m)=r.manager{migration_manager(o,&m)}o.word(r.pending_wipeout_impulse.is_some()as u32);if let Some(v)=r.pending_wipeout_impulse{o.floats(v)}r.chromosome.migration_grind_observe(o);o.word(j.launched as u32);o.word(j.cooldown);o.word(j.family);o.float(j.energy);o.word(j.geometry.geometry_kind);for v in[j.geometry.high_side,j.geometry.normal,j.geometry.direction,j.geometry.upmost,j.geometry.point]{o.floats(v)}}
pub(crate) fn migration_settings(o:&mut crate::Output,r:&Runtime){let s=&r.settings;o.float(s.standard_angular_drag);o.floats(s.pin_vs_slope.x);o.floats(s.pin_vs_slope.y);o.float(s.look_ahead);o.floats(s.exit_assist.x);o.floats(s.exit_assist.y);let p=s.post;o.floats([p.max_arm_contact_164,p.max_body_contact_168,p.xz_acceleration_204,p.max_displacement_208,p.max_angular_deck_error_212]);o.floats(s.reckoning.ground_normal_smoothing);o.floats(s.reckoning.tilt_vs_rotation.x);o.floats(s.reckoning.tilt_vs_rotation.y);o.floats(s.reckoning.tilt_vs_slope.x);o.floats(s.reckoning.tilt_vs_slope.y);s.substate.migration_grind_observe(o);}
'''

def reference_plan(output):
 original,observed,crate,cargo,report=reset.reference_plan(output)
 # Repair only the appended, borrowed reset fixture. Its private retained
 # normal belongs to GroundRuntime; preserve the original module prefix and
 # put the exact fixture write behind an accessor in that owning scope.
 phase=crate/'src/physics/input_phase.rs';phase_original=(original/(HOST+'input_phase.rs')).read_bytes()
 phase_raw=phase.read_bytes();assert phase_raw[:len(phase_original)]==phase_original
 appended=phase_raw[len(phase_original):].decode()
 old='s.ground_runtime.retained_board_normal=[0.317,0.731,-0.137,-0.];'
 new='s.ground_runtime.migration_grind_seed_board_normal([0.317,0.731,-0.137,-0.]);'
 assert appended.count(old)==1
 phase.write_bytes(phase_original+appended.replace(old,new).encode())
 generated,_=reset.generated_observer();prefix=generated[generated.index('use super::*;'):generated.index('pub(super) fn run(')]
 cases=generated[generated.index(' 0=>'):generated.index(' 2=>')]
 observer=(PLUGIN/'Tests/Reference/grind_runtime_observer.rs').read_text().replace('// GENERATED_ORIGINAL_OWNER_PREFIX',prefix).replace('// GENERATED_ORIGINAL_PACKET_RESET_CASES',cases).replace('// GENERATED_PROVIDER_READER',provider_helpers()[1]).replace('// GENERATED_GRIND_WORLD',world_helpers()[1])
 manager=block((PLUGIN/'Tests/Reference/player_grind_input_probe.rs').read_text(),'fn observe_observation(').replace('fn observe_observation(','fn migration_manager(').replace('physics::grind::ManagerObservation','crate::physics::grind::ManagerObservation').replace('o:&mut Output','o:&mut crate::Output')
 extensions={
 'physics/input_phase.rs':'\nuse crate::{physics,grind_world};\n'+observer,
 'physics.rs':'\npub(crate) fn migration_grind_runtime_run(a:&std::path::Path,f:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{input_phase::migration_grind_runtime_run(a,f,i,o)}\npub(crate) fn migration_grind_runtime_load(a:&std::path::Path,o:&mut crate::Output){grind::migration_load(a,o)}\n',
 'physics/grind/runtime.rs':'\nimpl Runtime{pub(crate) fn migration_grind_clear_manager(&mut self){self.manager=None;}}\n'+manager+RUNTIME_OBSERVER,
 'physics/ground_runtime/mod.rs':'\nimpl GroundRuntime{pub(crate) fn migration_grind_seed_board_normal(&mut self,value:[f32;4]){self.retained_board_normal=value;}}\n',
 'physics/grind/rng.rs':'\nimpl OrientationRandom{pub(super) fn migration_words(&self)->[u32;8]{self.words}}\n',
 'physics/grind.rs':'\npub(crate) use runtime::{migration_owner,migration_settings};\npub(crate) fn migration_vertical(i:&mut crate::Input,o:&mut crate::Output,r:&Runtime){substate::migration_vertical(i,o,r)}\npub(crate) fn migration_load(a:&std::path::Path,o:&mut crate::Output){let data=skate_data::collections::Collections::load(a).unwrap();match Runtime::load(&data){Ok(r)=>{o.status(Ok(()));migration_settings(o,&r)},Err(e)=>o.status(Err(e))}}\n',
 'physics/grind/substate/settings.rs':SUBSTATE_OBSERVER,
 'physics/grind/substate.rs':'''\npub(super) fn migration_vertical(i:&mut crate::Input,o:&mut crate::Output,r:&super::Runtime){use super::Family;for _ in 0..i.word(){let f=match i.word(){0=>Family::FiftyFifty,1=>Family::Boardslide,2=>Family::Tipslide,3=>Family::FiveO,4=>Family::Backslash,5=>Family::Darkslide,_=>panic!("family")};let mode=i.word();let strength=i.float();match r.settings.substate.vertical(f,mode,strength){Ok(v)=>{o.status(Ok(()));o.float(v)},Err(e)=>o.status(Err(e))}o.float(settings::side(f,i.word()));}}\n''',
 'physics/grind_chromosome.rs':CHROMOSOME_OBSERVER,
 'physics/grind_camera.rs':'\npub(crate) fn migration_observe(o:&mut crate::Output,c:&GrindCamera){for v in[c.current,c.previous,c.error,c.midpoint]{o.floats(v)}o.word(c.family);o.word(c.active as u32)}\n'}
 hashes={}
 for rel,extra in extensions.items():
  p=crate/'src'/rel;p.write_bytes(p.read_bytes()+extra.encode());hashes[rel]=dict(original_prefix_sha256=digest(original/('crates/skate-host/src/'+rel)),generated_sha256=digest(p),append_sha256=hashlib.sha256(extra.encode()).hexdigest())
 template=PLUGIN/'Tests/Reference/grind_runtime_probe.rs';code=(crate/'src/migration_probe.rs').read_text();code=code[:code.index('fn main()')]+template.read_text();code=code.replace('fn word(&mut self)->u32','fn text(&mut self)->String{let n=self.word();String::from_utf8((0..n).map(|_|self.word()as u8).collect()).unwrap()}\n fn word(&mut self)->u32');(crate/'src/migration_probe.rs').write_text(code)
 cargo.write_text(cargo.read_text().replace('name="player-teleport-reference"','name="grind-runtime-reference"'))
 # Inherited records name files that the Grind append step also extends.
 # Refresh their final generated hashes so the immutable report describes the
 # actual compiled observer files, while retaining every original prefix hash.
 for rel,row in report['staged_host_original_prefixes'].items():
  path=crate/'src'/rel
  if path.is_file():row['generated_sha256']=digest(path)
 report.update(grind_extensions=hashes,generated_probe_sha256=digest(crate/'src/migration_probe.rs'),observer_sha256=digest(PLUGIN/'Tests/Reference/grind_runtime_observer.rs'),grind_fixture_visibility=dict(borrowed_reset_replacement=dict(old=old,new=new,original_prefix_sha256=hashlib.sha256(phase_original).hexdigest()),bindings=['crate::physics and crate::grind_world imports in appended input_phase scope','parent physics loader forwarding into private grind module','GroundRuntime retained_board_normal exact owning-scope fixture setter','Runtime manager exact owning-scope fixture clear','AttributeName.0 five-word observation','GamePhysics.grind_materials authoritative material table']),scope='Full untouched host: real GamePhysics/SkaterRuntime constructors; six grind states/Nonspecific, all original core forces/reckoning/chromosome/camera/settings and original skeleton/world/IK/solve owners. Append-only read observers and explicit caller/transport adapters.')
 return original,observed,crate,cargo,report

def build_native(output):
 snap,report=native_plan(output);binary=output/'grind-runtime-native'
 subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snap),*[str(snap/(u+'.cpp'))for u in UNITS],str(snap/'grind_runtime_probe.cpp'),'-o',str(binary)],check=True)
 report['binary_sha256']=digest(binary);(output/'native-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return binary

def build_reference(output,target):
 original,observed,crate,cargo,report=reference_plan(output);subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(cargo),'--target-dir',str(target.resolve()),'--bin','grind-runtime-reference'],check=True)
 for rel,sha in report['original_source_sha256'].items():
  assert digest(original/rel)==sha;raw=(original/rel).read_bytes();assert(observed/rel).read_bytes()[:len(raw)]==raw
 binary=output/'grind-runtime-reference';shutil.copy2(target.resolve()/'release/grind-runtime-reference',binary);report['binary_sha256']=digest(binary);(output/'reference-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return binary

def manager(family,kind=0,direction=(1.,0.,0.,0.),point=(0.,0.,0.,0.),flags=0,controls=0,relief=0,blend=0):
 return dict(geometry=dict(point_1120=list(point),direction_1136=list(direction),normal_1152=[0,1,0,0],target_up_1168=[0,1,0,0],primitive_start_1264=[-3,-.015,0,0],primitive_end_1280=[3,-.015,0,0],spline_guids_1296=[0x1122334455667788,0x8877665544332211],upmost_normal_1408=[.137,.731,-.317,0],high_side_1440=[0,0,1,0],kind_1464=kind,flags_1476=flags,impact_speed_1492=3.731),surface=dict(audio_surface_1468=0x12345678,material_1472=13,friction_vs_time_1496=.731,reckon_blend_selector_1500=blend,gravity_relief_1512=relief),control=dict(family=family,flags_1516=controls,flags_2468=0x2000,flags_2488=0,translation_2796=.317,balance_2800=.137,exit_lean=17),engagement=dict(velocity_1184=[1,0,3,.731],kind_1248=0),jumper=dict(geometry_kind_16=kind,family_20=family,energy_24=.731,high_side_32=[0,0,1,0],normal_48=[0,1,0,0],direction_64=list(direction),upmost_normal_80=[0,1,0,0],point_96=list(point)))

def write_manager(w,m):
 g=m['geometry']
 for f in('point_1120','direction_1136','normal_1152','target_up_1168','primitive_start_1264','primitive_end_1280'):
  for v in g[f]:w.float(v)
 w.word(g['spline_guids_1296']is not None)
 if g['spline_guids_1296']is not None:
  for v in g['spline_guids_1296']:w.wide(v)
 for f in('upmost_normal_1408','high_side_1440'):
  for v in g[f]:w.float(v)
 w.word(g['kind_1464']);w.word(g['flags_1476']);w.float(g['impact_speed_1492'])
 s=m['surface'];w.word(s['audio_surface_1468']);w.word(s['material_1472'])
 for f in('friction_vs_time_1496','reckon_blend_selector_1500','gravity_relief_1512'):w.float(s[f])
 c=m['control']
 for f in('family','flags_1516','flags_2468','flags_2488'):w.word(c[f])
 for f in('translation_2796','balance_2800','exit_lean'):w.float(c[f])
 for v in m['engagement']['velocity_1184']:w.float(v)
 w.word(m['engagement']['kind_1248']);j=m['jumper'];w.word(j['geometry_kind_16']);w.word(j['family_20']);w.float(j['energy_24'])
 for f in('high_side_32','normal_48','direction_64','upmost_normal_80','point_96'):
  for v in j[f]:w.float(v)

def jumper(family,kind,energy,balance=0):
 return dict(launched=False,cooldown=7,family=family,energy=energy,geometry=dict(geometry_kind=kind,high_side=[0,0,1,.137],normal=[0,1,0,-.0],direction=[1,0,0,.317],upmost=[0,1,0,.731],point=[0,0,0,.137]))

def corpus():
 defs,_=protocol.declarations();_,baseline=reset.corpus();packets=copy.deepcopy(baseline[0]['commands'][0]);reset_cmd=copy.deepcopy(next(c for c in baseline[0]['commands']if c['op']==1));cases=[]
 ids=(401,400,402,403,404,405)
 def packet(state=401,flags=0x2000,mode=1,speed=3.,collision=0,velocity=(.137,0,3.,0),investigation=0):
  cmd=copy.deepcopy(packets);p=cmd['processed'];q=cmd['physical'];p.update(flags_2468=flags,flags_2472=collision,flags_2476=0,flags_2480=0,flags_2484=0,flags_2488=0,state_2504=100,state_2508=state,category_2512=state//100*100,state_variant_index_2528=mode,timestep_2604=1/60,scalar_2652=speed)
  p['grind'].update(flags_1516=investigation,geometry_kind_1464=1,point_1120=[bits(x)for x in(0.,.137,0.,.731)],entry_velocity_1184=[bits(x)for x in(1.,0.,3.,.731)])
  p['vectors_400_416']=[[bits(x)for x in velocity],[bits(x)for x in velocity]];p['vectors_544_560_592_608'][0]=[0,bits(1),0,0]
  p['collision_pose_error_736']=[bits(x)for x in(.317,0.,.137,0.)];q['state'].update(state_16=state,category_12=state//100*100);return cmd
 def setup(state=401):
  r=copy.deepcopy(reset_cmd);r.update(pose=0,attributes=[],actions=[0.]*18,target=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,-.035,0.,0.]])
  return[packet(state),r,packet(state),dict(op=22,pose=0,fakie=False,jump_fix=1000,pop=1.),dict(op=12),dict(op=34),dict(op=28,spin=[.317,.731,-.137])]
 def step():return[dict(op=13),dict(op=14),dict(op=15),dict(op=16),dict(op=25)]
 def add(label,commands,provider=None,world=1):cases.append(dict(index=len(cases),label=label,provider=provider or input_grind.authored_provider([[-3,-.015,0],[3,-.015,0]]),world=world,commands=commands))
 for family,state in enumerate(ids):
  for kind in(0,1,2):
   m=manager(family,kind,flags=0x40000000 if kind==2 else 0,controls=0x20000000 if family%2 else 0,relief=.731 if kind==1 else 0,blend=.317 if kind==2 else 0)
   if family==2 and kind==1:m['geometry']['flags_1476']|=0x08000000
   commands=setup(state)+[dict(op=20,manager=m),dict(op=10,state=state)]+step()*3
   commands += [packet(state,flags=0x00202000)]+step()+[packet(state,flags=0x2000)]
   # Original common user-exit bit29; the slide-family gate requires ledge2.
   v=packet(state);v['processed']['flags_2476']=0x20000000
   if family in(1,5)and kind!=2:m=copy.deepcopy(m);m['control']['flags_1516']|=0x80000000;commands.append(dict(op=20,manager=m))
   commands += [v]+step()*38+[dict(op=6),dict(op=17),dict(op=11),dict(op=15),dict(op=16)]
   add('six-family original contact/involuntary lifetime '+str(family)+'/'+str(kind),commands)
 # True collision force precedes pop; full queue still selects prediction-only.
 for capacity in(0,20,21,29):
  commands=setup()+[dict(op=20,manager=manager(0)),dict(op=10,state=401),dict(op=23,count=capacity),packet(flags=0x00402000,collision=0x20000,velocity=(-3.,0.,-.731,0.))]+step()+[dict(op=32),dict(op=11)]
  add('collision-before-pop with native queue '+str(capacity),commands)
 # Low-energy geometry cache, balance clamp and trainer scale. All five stock modes.
 for family in range(6):
  commands=setup(ids[family])+[dict(op=20,manager=manager(family,1)),dict(op=10,state=ids[family])]
  for k,(energy,velocity)in enumerate(((.30999997,(0,0,3,0)),(.31,(0,0,-3,0)),(.6,(1,0,3,0)))):
   commands += [dict(op=21,jumper=jumper(family,k,energy)),dict(op=22,pose=k%4,fakie=bool(k%2),jump_fix=7,pop=(.731,1.,1.137)[k]),packet(ids[family],flags=0x00402000,mode=(family+k)%5,velocity=velocity)]+step()+[dict(op=6),dict(op=12)]
  commands += [dict(op=11)];add('seven-body source pop/cache/energy family '+str(family),commands)
 for state in(701,401):
  commands=setup(state)+[dict(op=20,manager=manager(0)),dict(op=10,state=state),packet(state)]+step()[:2]
  commands += [packet(state,flags=0x00402000)]+step()[:2]+[packet(state,collision=0x00400000),dict(op=13),dict(op=14),dict(op=11)]
  add('Nonspecific distinct update and latched Fill '+str(state),commands)
 # Faithful missing-owner errors and real late hierarchy/IK writes.
 for missing in('toolkit_enter','manager_fill','toolkit_update','invalid_mode','missing_hierarchy','invalid_ik'):
  commands=setup()+[dict(op=20,manager=manager(0)),dict(op=10,state=401)]
  if missing=='toolkit_enter':commands += [dict(op=11),dict(op=18),dict(op=10,state=401)]
  elif missing=='manager_fill':commands += [dict(op=19),dict(op=14),dict(op=13)]
  elif missing=='toolkit_update':commands += [dict(op=18),dict(op=13)]
  elif missing=='invalid_mode':commands += [packet(flags=0x00402000,mode=99),dict(op=13)]
  elif missing=='missing_hierarchy':commands += [dict(op=22,pose=4,fakie=False,jump_fix=1000,pop=1.),dict(op=13)]
  else:commands += [dict(op=24,part=23,value=0xffffffff),dict(op=13)]
  add('actual error and partial-write prefix '+missing,commands)
 # Original completed-publication chromosome history, every frame including nongrind.
 for forward in(1.,-1.):
  for fakie in(False,True):
   m=manager(0,direction=(forward,0,0,0));commands=setup()+[dict(op=22,pose=0,fakie=fakie,jump_fix=1000,pop=1.)]
   ground_packet=packet(100);ground_packet['physical']['grinds']['words_136_140']=[0xffffffff,0]
   commands += [ground_packet,dict(op=15)]*35+[packet(),dict(op=20,manager=m),dict(op=10,state=401)]+step()*15
   m2=copy.deepcopy(m);m2['geometry']['direction_1136'][0]*=-1;commands += [dict(op=20,manager=m2)]+step()*15+[dict(op=11),ground_packet,dict(op=15),dict(op=16)]*1
   add('30 ground samples and delayed independent names '+str(forward)+'/'+str(fakie),commands)
 # The real accepted manager, original authored StaticProvider and world query.
 producer_programs,_,_=input_grind.corpus()
 for program in producer_programs:
  if not program['label'].startswith('explicit authored'):continue
  cmd=next(c for c in program['commands']if c['op']==0);state=cmd['p']['state_2508'];commands=setup(state)
  for _ in range(5):
   p=packet(state);p['processed']=copy.deepcopy(cmd['p']);commands += [p,dict(op=30,air_counter=20,target=False),dict(op=12)]
  commands += [dict(op=10,state=state)]+step()+[dict(op=11)]
  add('actual provider/admission/material/balance/control publication '+program['label'],commands,program['provider'],program['world'])
 # Complete names and exact authored jump sector/mode/strength scalar boundaries.
 vertical=[]
 for family in range(6):
  for mode in(0,1,2,3,4,5,99,0xffffffff):
   for strength in(-.317,-0.,0.,.5,1.,1.137):vertical.append(dict(family=family,mode=mode,strength=strength,kind=mode%4))
 add('all 384 S3 names and stock getter unclamped boundaries',[dict(op=27),dict(op=26,values=vertical)])
 # Invalid active output-family diagnostics preserve the earlier grinding write.
 for names in('animation','scoring','family'):
  p=packet();out=p['physical']['grinds'];out['words_136_140']=[999 if names=='family'else 0,1]
  if names!='family':out[names+'_name_156'if names=='animation'else'scoring_name_176']=None
  add('completed filtered/condition error '+names,[p,dict(op=15 if names=='family'else 25)])
 # Append the accepted 50-50 acquisition at its actual physical deck height.
 # horizontal_spawn adds .1 to the requested Y: the earlier -.035 reset
 # leaves depth .145 above the -.08 rail, outside the source's <.13 gate.
 # Requesting -.1 gives the accepted identity frame through the REAL reset.
 witness=next(p for p in producer_programs if p['label']=='explicit authored fifty-fifty witness')
 p=packet(401);p['processed']=copy.deepcopy(witness['commands'][0]['p'])
 def empty(value):
  if isinstance(value,dict):return {k:empty(v)for k,v in value.items()}
  if isinstance(value,list):return [empty(v)for v in value]
  return None if value is None else 0
 p['processed']['grind']=empty(p['processed']['grind'])
 r=copy.deepcopy(reset_cmd);r.update(pose=0,attributes=[],actions=[0.]*18,target=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,-.1,0.,0.]])
 commands=[copy.deepcopy(p),r,copy.deepcopy(p),dict(op=22,pose=0,fakie=False,jump_fix=1000,pop=1.),dict(op=12),dict(op=34)]
 # Only PreUpdate/PostUpdate can construct the admitted manager. No op20/21,
 # contact, query-result, velocity/body or force-queue observer is installed.
 for _ in range(4):commands += [dict(op=30,air_counter=20,target=False),dict(op=12)]
 commands += [dict(op=10,state=401)]+step()+[dict(op=17),dict(op=11)]
 add('actual 50-50 provider admission through source horizontal reset',commands,witness['provider'],witness['world'])
 # Keep every preceding history intact. Condition first observes category400
 # without an active grind, so the next active publication starts its pending
 # chromosome at0 rather than the first-entry13. Repeating that same actual
 # Condition raises it to1: source publishes animation (>0), while scoring
 # (>12) and its missing caller name remain unwritten. Filter therefore reaches
 # the second name check using the canonical name produced by the real owner.
 p=packet();p['physical']['grinds']['words_136_140']=[0,0]
 p['physical']['grinds']['animation_name_156']=None
 p['physical']['grinds']['scoring_name_176']=None
 active=copy.deepcopy(p);active['physical']['grinds']['words_136_140']=[0,1]
 add('actual delayed animation publication with missing scoring name',
     [p,dict(op=15),active,dict(op=15),dict(op=15),dict(op=25)])
 w=input_grind.Stream();w.word(len(cases))
 for case in cases:
  w.word(case['world']);input_grind.encode_provider(w,case['provider']);w.word(len(case['commands']))
  for cmd in case['commands']:
   op=cmd['op'];w.word(op)
   if op==0:
    for name,key in(('PlayerInputState','player'),('PhysicalPlayerInput','physical'),('ProcessedPhysicsInput','processed')):protocol.encode(w,name,cmd[key],defs)
   elif op==1:
    for v in cmd['target']:
     for x in v:w.float(x)
    packet_=cmd['packet'];protocol.encode(w,'AnimationPacketFields',packet_['publication'],defs);protocol.encode(w,'ExternalPhysicsInput',packet_['external_physics_10512'],defs)
    for field,kind in defs['AnimationInputPacket']:
     if not kind.startswith('&'):protocol.encode(w,kind,packet_[field],defs)
    w.word(cmd['pose']);w.word(len(cmd['attributes']))
    for a in cmd['attributes']:
     for x in a['name']+[a['kind'],a['status'],a['sequence'],a['begin'],a['end']]:w.word(x)
     for v in a['payload']:
      w.word(v is not None)
      if v is not None:w.word(v)
    for x in cmd['actions']:w.float(x)
    w.word(cmd['initial_teleported'])
   elif op==10:w.word(cmd['state'])
   elif op==20:write_manager(w,cmd['manager'])
   elif op==21:
    j=cmd['jumper'];w.word(j['launched']);w.word(j['cooldown']);w.word(j['family']);w.float(j['energy']);w.word(j['geometry']['geometry_kind'])
    for f in('high_side','normal','direction','upmost','point'):
     for v in j['geometry'][f]:w.float(v)
   elif op==22:w.word(cmd['pose']);w.word(cmd['fakie']);w.word(cmd['jump_fix']);w.float(cmd['pop'])
   elif op==23:w.word(cmd['count'])
   elif op==24:w.word(cmd['part']);w.word(cmd['value'])
   elif op==26:
    w.word(len(cmd['values']))
    for v in cmd['values']:w.word(v['family']);w.word(v['mode']);w.float(v['strength']);w.word(v['kind'])
   elif op==28:
    for v in cmd['spin']:w.float(v)
   elif op==30:w.word(cmd['air_counter']);w.word(cmd['target'])
   elif op==31:w.word(cmd['world'])
 return bytes(w.data),cases

class Reader(reset.Reader):
 def state(self):
  assert self.word()==len(BLOCKS);values={};self.sections={}
  for name in BLOCKS:
   n=self.word();at=self.at;values[name]=self.take(n);self.sections[name]=(at,self.at)
  return values

def decode(raw,cases):
 r=Reader(raw);assert r.word()==len(cases);frames=[]
 for c in cases:
  c['first_word']=r.at;assert r.word()==len(c['commands']);previous=r.state();rows=[]
  for cmd in c['commands']:
   at=r.at;assert r.word()==cmd['op'];error=r.status();extra=r.take(r.word());s=r.state();rows.append(dict(op=cmd['op'],error=error,extra=extra,state=s,previous=previous,sections=r.sections.copy(),first_word=at,last_word=r.at));previous=s
  c['last_word']=r.at;frames.append(rows)
 assert r.at==len(r.words);return frames

def shared(words):
 r=reset.Reader(struct.pack('<'+'I'*len(words),*words));s=r.state();assert r.at==len(words);return s

def retained(words):
 r=Reader(struct.pack('<'+'I'*len(words),*words));states=[r.take(49)for _ in range(6)];active=r.word();family=r.word()if active else None;nonspecific=r.word();jumped=r.word();jump=r.take(4);random=r.take(8);manager_=r.word();manager_words=[]
 if manager_:
  start=r.at;r.take(24)
  if r.word():r.take(4)
  r.take(8+3+5+7+5+3+20);manager_words=r.words[start:r.at]
 pending=r.word();impulse=r.take(4)if pending else None;history=[r.take(17)for _ in range(r.word())];saved=r.take(17);initialized=r.word();approach=r.word();previous_category=r.word();kind=r.word();previous_kind=r.word()if kind else None;away=r.word();reversed_=r.word();orientation=r.word();orientation=r.word()if orientation else None
 def components():return r.take(6)if r.word()else None
 candidate=components();pending_frames=r.word();animation=components();scoring=components();jumper_=r.take(25);assert r.at==len(words),(r.at,len(words))
 return dict(states=states,active=family,nonspecific=nonspecific,jumped=jumped,jump=jump,random=random,manager=manager_words,pending=impulse,history=history,saved=saved,initialized=initialized,approach=approach,previous_category=previous_category,previous_kind=previous_kind,away=away,reversed=reversed_,orientation=orientation,candidate=candidate,pending_frames=pending_frames,animation=animation,scoring=scoring,jumper=jumper_)

def coverage(frames,cases):
 # All 384 table entries are required; many intentionally share a trick name.
 # Derive their ordered attributes from the pinned original tables rather than
 # requiring an invented minimum number of unique names.
 source_names=[name for table in range(8)for name in re.findall(r'attribute:\s*"([^"]+)"',protocol.trees.source_at_reference(f'crates/skate-host/src/physics/grind_names/table{table}.rs'))]
 assert len(source_names)==384
 counts=Counter();errors=Counter();families=Counter();substates=Counter();noise_changes=0;body_writes=0;tip=set();slide=0;air_pops=0;partial=0;queue_counts=set();queue_proofs=0;collision_precedence=0;history=set();orientations=set();camera_changes=0;published_names=set();actual_manager=0;post_success=0;wheel_publication=0
 for rows,case in zip(frames,cases):
  # The original read observer ends its fixed RidingOutputs block with the
  # source queue count followed by exactly seven words per queued point force.
  initial=shared(rows[0]['previous']['shared'])['riding'];assert initial[-1]==0;queue_at=len(initial)-1
  for row,cmd in zip(rows,case['commands']):
   counts[OPS[cmd['op']]]+=1;errors.update([row['error']]if row['error']else[])
   g=retained(row['state']['grind']);old=retained(row['previous']['grind']);s=shared(row['state']['shared']);before=shared(row['previous']['shared']);p=reset.packet_observation(s['packets']);out=p['PhysicalPlayerInput']['grinds']
   history.add(len(g['history']));orientations.add(g['orientation']);queue_count=s['riding'][queue_at];assert len(s['riding'])==queue_at+1+queue_count*7;assert queue_count<=21;queue_counts.add(queue_count)
   if row['op']==23:
    assert queue_count==min(cmd['count'],21);queue_proofs+=1
   if row['op']==13 and case['label'].startswith('collision-before-pop')and not row['error']:
    requested=next(c['count']for c in case['commands']if c['op']==23);assert queue_count==min(requested+1,21)
    assert g['states'][0][16]==0 and g['jumper'][0]==0;collision_precedence+=1
   if row['op']==10 and not row['error']:
    if cmd['state']!=701:families[g['active']]+=1;state=g['states'][g['active']];assert state[14]==1 and state[45:49]==[0,0,0,0]and state[26:29]==[0,0,0]
    else:assert g['nonspecific']==1 and g['jumped']==0 and g['jump']==[0]*4
   if row['op']==13:
    noise_changes+=g['random']!=old['random'];body_writes+=s['shared']!=before['shared'];partial+=bool(row['error'])and row['state']!=row['previous']
    if g['active']is not None:
     state=g['states'][g['active']];substates[state[14]]+=1;tip.add(tuple(state[26:29]));slide+=state[21];air_pops+=state[16]
   if row['op']==14 and not row['error']:
    if g['active']is not None:
     state=g['states'][g['active']];assert out['words_136_140']==[g['active'],state[14]] and out['crouch_132']==state[12];assert g['pending']is None
     assert out['direction_0']==state[:4]and out['normal_32']==state[4:8]and out['across_48']==state[8:12]
   if row['op']==15 and not row['error']:
    assert out['grinding_316']==int(out['words_136_140'][1]in(1,2));published_names.add(tuple(out['animation_chromosome_268']))
   if row['op']==16:camera_changes+=row['state']['camera']!=row['previous']['camera']
   if row['op']==30 and not row['error']:
    actual_manager+=p['ProcessedPhysicsInput']['grind']['valid_1488']!=0;assert g['manager']
   if row['op']==17:post_success+=not row['error']
   if row['op']==34:wheel_publication+=not row['error']
   if row['op']==27:
    r=Reader(struct.pack('<'+'I'*len(row['extra']),*row['extra']));records=[]
    for _ in range(384):
     skating=r.word();attribute=bytes(r.take(r.word())).decode();display=bytes(r.take(r.word())).decode();scorable=r.word();encoded=r.take(5);records.append((skating,attribute,display,scorable,encoded))
    assert r.take(6)==[0]*6 and r.at==len(r.words)
    assert [n[1]for n in records]==source_names
 assert all(families[f]>0 for f in range(6)),families
 assert noise_changes>0 and body_writes>0 and slide>0 and air_pops>0,(noise_changes,body_writes,slide,air_pops)
 assert substates[1]>0 and substates[2]>0 and any(t[0]for t in tip)and any(t[1]for t in tip),(substates,tip)
 assert {0,30}<=history and len(published_names)>4 and camera_changes>0,(history,published_names,camera_changes)
 assert actual_manager>0 and post_success>0 and wheel_publication>0,(actual_manager,post_success,wheel_publication)
 for e in('Grind Enter requires current board toolkit','Grind Fill requires completed manager observation','Grind Update requires BoardToolkit','Invalid grind jump physics mode 99','IK original joint is absent from the current pose','Missing native grind name reset/publication','Missing native scoring grind name reset/publication','Active grind has invalid native family 999'):
  assert errors[e]>0,(e,errors)
 assert partial>0
 assert queue_proofs==4 and collision_precedence==4 and {0,20,21}<=queue_counts,(queue_proofs,collision_precedence,queue_counts)
 return dict(operations=dict(counts),errors=dict(errors),families=dict(families),substates=dict(substates),orientation_rng_changed=noise_changes,actual_body_writes=body_writes,tipslide_latches=[list(t)for t in sorted(tip)],slide_wipeout_frames=slide,pop_latches=air_pops,partial_writes=partial,force_queue_counts=sorted(queue_counts),capacity_proofs=queue_proofs,collision_precedes_pop=collision_precedence,chromosome_history_lengths=sorted(history),orientations=sorted(o for o in orientations if o is not None),distinct_name_chromosomes=len(published_names),original_name_entries=len(source_names),distinct_original_names=len(set(source_names)),camera_history_writes=camera_changes,real_provider_admissions=actual_manager,completed_post_frames=post_success,real_wheel_publications=wheel_publication)

def settings_queries():
 q=[('physics_grinds','default',n,'words')for n in('PinVsSlope','ExitAssistVsLeanAngle')]
 q += [('physicsdeck','default','DeckAngularDrag','float'),('physics_grinds','default','GrindLookAheadScalar','float')]
 q += [('physics_wipeout','default',n,'float')for n in('Wipeout_GroundSkeletonMaxContactArms','Wipeout_GroundSkeletonMaxContact','Wipeout_GrindXZDeck','Wipeout_GrindSkeletonMaxDisp','Wipeout_GrindMaxAngularDeckError')]
 q += [('physics_reckoning','default',n,'words')for n in('GroundNormalSmoothing','TiltVsRotGround','TiltVsSlopeGround')]
 q += [('physics_collision','default','CollisionTorqueVsAngle','words')]
 q += [('physics_mode',mode,n,'float')for mode in('easy','normal','hardcore','motorized','test')for n in('Hash_3097A69281990652','Hash_FA4CDBAE0DFD1FAD','Hash_B2B1170AFFC8AC69','Hash_1B3E9F9C836D287D','Hash_703829BD711E54DE','Hash_F2473E9125079F0')]
 q += [('physics_animation','default','MaxDeckZAxisYForAnimatedDeck','float')]
 q += [('physics_collision','default',n,'float')for n in('MaxVelDelta','ForceYOffset','CollisionForceScalar','TargetDisplacementVel')]
 return q

def check_settings(output,path,native,reference):
 import check_ground_control_settings_parity as stock
 original=json.loads(path.read_text());fixtures=[original];labels=['stock'];queries=settings_queries();independent=copy.deepcopy(original)
 # Materialize the source-resolved inherited values in each queried collection,
 # so a later mode's invalid field cannot corrupt an earlier inherited read.
 # These are real stock payloads; the original Collections loader still executes.
 for query in queries:
  chain,name=stock.resolve(original,query);record=stock.record(independent,query[0],query[1]);assert record is not None;record['fields'][name]=copy.deepcopy(chain[-1]['fields'][name])
 for at,q in enumerate(queries):
  value=copy.deepcopy(independent)
  for later in queries[at:]:stock.mutate(value,later,dict(type='EA::Reflection::Int32',data='00000000')if later[3]=='float'else dict(type='EA::Reflection::Float',data='00000000'))
  fixtures.append(value);labels.append('first failed read '+str(q))
 output.mkdir(parents=True,exist_ok=True)
 folder=stock.prepare_fixtures(output,fixtures,path);errors=Counter();records=[]
 for n,label in enumerate(labels):
  expected=subprocess.check_output([str(reference),str(folder/str(n)),'--settings-only']);actual=subprocess.check_output([str(native),str(folder/str(n)/'settings.native'),'--settings-only'])
  (output/f'settings-{n}-reference.bin').write_bytes(expected);(output/f'settings-{n}-native.bin').write_bytes(actual)
  if expected!=actual:raise AssertionError(('Grind settings mismatch',n,label,expected.hex(),actual.hex()))
  r=Reader(expected);error=r.status();values=r.take(110)if not error else[];assert r.at==len(r.words);assert bool(error)==(n!=0),(label,error)
  if n:
   category,key,name,kind=queries[n-1];length={'PinVsSlope':8,'ExitAssistVsLeanAngle':12,'GroundNormalSmoothing':4,'TiltVsRotGround':16,'TiltVsSlopeGround':16,'CollisionTorqueVsAngle':20}.get(name)
   wanted='Expected float at '+category+'/'+key+'/'+name if kind=='float'else 'Expected '+str(length)+' big-endian words, found 8 bytes of hex';assert error==wanted,(label,wanted,error)
  errors.update([error]if error else[]);records.append(dict(fixture=n,label=label,error=error,values=values))
 assert len(records)==49 and len(errors)>=20,(len(records),errors)
 return dict(fixtures=len(records),first_failed_reads=len(queries),errors=dict(errors),records=records)

def preflight(raw,cases):
 defs,_=protocol.declarations();r=protocol.Reader(raw);assert r.word()==len(cases)
 def take(n):
  for _ in range(n):r.word()
 def text():take(r.word())
 def provider():
  for _ in range(r.word()):
   text();r.word();take(r.word()*3)
   if r.word():take(r.word())
  text();take(r.word()*24);take(r.word()*4)
  for _ in range(r.word()):text();text();take(5);take(r.word())
 def manager_():
  take(24)
  if r.word():take(4)
  take(8+3+5+7+5+3+20)
 for case in cases:
  assert r.word()==case['world'];provider();assert r.word()==len(case['commands'])
  for cmd in case['commands']:
   op=r.word();assert op==cmd['op']
   if op==0:
    for name in('PlayerInputState','PhysicalPlayerInput','ProcessedPhysicsInput'):r.value(name,defs)
   elif op==1:
    take(16);r.value('AnimationPacketFields',defs);r.value('ExternalPhysicsInput',defs)
    for field,kind in defs['AnimationInputPacket']:
     if not kind.startswith('&'):r.value(kind,defs)
    assert r.word()==cmd['pose'];assert r.word()==len(cmd['attributes'])
    for _ in cmd['attributes']:
     take(10)
     for _ in range(6):
      if r.word():r.word()
    take(19)
   elif op in(10,23,31):r.word()
   elif op==20:manager_()
   elif op==21:take(25)
   elif op==22:take(4)
   elif op in(24,30):take(2)
   elif op==26:assert r.word()==len(cmd['values']);take(len(cmd['values'])*4)
   elif op==28:take(3)
 assert r.at==len(raw),(r.at,len(raw))
 assert len(settings_queries())==48
 for u in UNITS:assert(CODE/(u+'.cpp')).is_file(),u

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in('assets','samples','output','target-dir'):p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 for name in('result.json','first-divergence.json'):(out/name).unlink(missing_ok=True)
 raw,cases=corpus();preflight(raw,cases);(out/'input.bin').write_bytes(raw);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
 if a.preflight:
  snap,native=native_plan(out);original,observed,crate,cargo,reference=reference_plan(out/'reference')
  for source in(snap/'grind_runtime_probe.cpp',crate/'src/migration_probe.rs',crate/'src/physics/input_phase.rs'):
   assert 'GENERATED_'not in source.read_text(),source
  for rel,sha in reference['original_source_sha256'].items():
   assert digest(original/rel)==sha;source=(original/rel).read_bytes();assert(observed/rel).read_bytes()[:len(source)]==source
  (out/'native-preflight.json').write_text(json.dumps(native,indent=2)+'\n');(out/'reference-preflight.json').write_text(json.dumps(reference,indent=2)+'\n')
  print(json.dumps(dict(histories=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(raw),units=len(UNITS),settings_first_failed_reads=len(settings_queries())),indent=2));return
 fixtures=out/'fixtures';fixtures.mkdir(exist_ok=True);stock=a.assets.resolve()/'private/stock';(fixtures/'settings.native').write_bytes(reset.foot.converter.encode_settings(stock/'skater-collections.json'));(fixtures/'physics.native').write_bytes(reset.foot.converter.encode_physics_skeletons(stock/'physics-skeletons.json'))
 for kind in('action','motion'):(fixtures/f'actor.{kind}.reference').write_bytes(original_graph(element('state','idle')))
 identity=json.loads((stock/'physics-skeletons.json').read_text())['source_sha256'];reference=build_reference(out/'reference',a.target_dir);native=build_native(out)
 expected=subprocess.check_output([str(reference),str(a.assets.resolve()),str(fixtures)],input=raw);actual=subprocess.check_output([str(native),str(fixtures/'settings.native'),str(fixtures/'physics.native'),str(a.samples.resolve()/'native/rig.skate'),identity,str(a.assets.resolve())],input=raw)
 (out/'reference.bin').write_bytes(expected);(out/'native.bin').write_bytes(actual);frames=decode(expected,cases)
 if expected!=actual:
  at=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));word=at//4;case=next((c for c in cases if c['first_word']<=word<c['last_word']),None);row=next((r for rows in frames for r in rows if r['first_word']<=word<r['last_word']),None);section=next(((n,word-a)for n,(a,b)in(row['sections'].items()if row else[])if a<=word<b),None)
  failure=dict(byte=at,reference_bytes=len(expected),native_bytes=len(actual),case=case['index']if case else None,operation=row['op']if row else'initial',section=section,reference_hex=expected[max(0,at-16):at+32].hex(),native_hex=actual[max(0,at-16):at+32].hex());(out/'first-divergence.json').write_text(json.dumps(failure,indent=2)+'\n');raise AssertionError(failure)
 settings=check_settings(out/'settings',stock/'skater-collections.json',native,reference)
 result=dict(passed=True,reference_revision=REFERENCE_REVISION,histories=len(cases),commands=sum(len(c['commands'])for c in cases),bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),input_sha256=hashlib.sha256(raw).hexdigest(),coverage=coverage(frames,cases),settings=settings,scope='Full original physical Grind host: six retained states and Nonspecific; actual stock GamePhysics/SkaterRuntime construction; original force/reckoning/skeleton/IK/solve owners, StaticProvider Pre/Post, names/chromosome/camera and stock loader order.',boundaries='Canonical completed player/physical/animation packet inputs, manager snapshots for focused family cases, selected lifecycle state, jump-fix counter and trainer pop are explicit upstream/caller publications. Actual provider admission is separately executed and required by coverage. Entire global state/physics schedule and source actor logging remain separate; no completed query/contact/force observation is fabricated.')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
