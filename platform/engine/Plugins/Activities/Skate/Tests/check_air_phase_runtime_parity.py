#!/usr/bin/env python3
"""Whole original PhysicsAir/KnownAir + actual pose/IK/selector/solve proof.

Only the root render guard builds and executes. --preflight performs source,
transport and immutable-prefix checks without compiling or running binaries.
"""
import argparse
from collections import Counter, OrderedDict
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import check_footplant_parity as foot
import check_ground_runtime_parity as ground
import check_air_trajectory_runtime_parity as trajectory
import check_player_grind_input_parity as provider
import check_ground_board_parity as basic
import check_wipeout_runtime_parity as wipeout
import check_skeleton_input_runtime_parity as dispatcher
import player_input_protocol as packet
from camera_reference_build import frozen_sources
from check_gesture_parity import PLUGIN, converter
from check_graph_parity import element, original_graph
from check_animation_playback_parity import Stream
from session_parity import REFERENCE_REVISION, digest
CODE=foot.CODE
UNITS=tuple(dict.fromkeys((*foot.UNITS,*ground.UNITS,'GroundStateRuntimeExit','AirState','AirPhaseRuntime','WipeoutSettings','WipeoutObservations','WipeoutRuntime','KnownAirSettings','KnownAirMath','KnownAirLive','KnownAirTrajectory','KnownAirBody','KnownAirCore','KnownAirOutput','KnownAirRuntime')))
UNITS=tuple(u for u in UNITS if u!='GroundStateRuntimeExit')
OPS=('caller_packet','authored_pose','toolkit','enter_air','advance_air','exit_air','post_air','publish_air','enter_known','update_known','exit_known','post_known','publish_known','begin_queries','solve_feedback','replace_world','selector_reset','controller_override','packet_flags','capture_board_error','grind_rebind','wipeout_check','clear_requests')
SECTIONS=('air_state','air_settings','known_state_settings','publication','processed','lifecycle','forces','collision_feedback','wipeout_frame','known_return')

def extract(path,marker):return trajectory.block(path.read_text(),marker)
def schema():
 definitions=OrderedDict()
 for path,names in [('crates/skate-core/src/air/state/data.rs',('PhysicsAirState','PhysicsAirSettings')),('crates/skate-core/src/air/known/data.rs',('KnownAirTrajectory','KnownAirState','KnownAirSettings','KnownAirModeSettings','KnownAirWipeoutSettings','KnownAirOutput'))]:
  source=dispatcher.source(path)
  for name in names:
   body=re.search(r'pub struct '+name+r'\s*\{(.*?)\n\}',source,re.S).group(1)
   fields=[]
   for f,t in re.findall(r'pub (\w+): ([^,\n]+),',body):
    t=re.sub(r'\s+','',t);t='Vector'if t in('V','[f32;4]')else t
    if t=='AirTrajectory':t='PhysicsAirTrajectory'
    fields.append((f,t))
   definitions[name]=fields
 # Original AirTrajectory and selector's different trajectory are distinct.
 definitions=OrderedDict([('PhysicsAirTrajectory',[('position','Vector'),('velocity','Vector'),('acceleration','Vector'),('scalar_48','f32')]),*definitions.items()])
 return definitions

def helpers():
 defs=schema();defs['WipeoutFrame']=wipeout.schema()['WipeoutFrame'];defs={name:[(f,'Vector'if t=='Vector4'else t)for f,t in fields]for name,fields in defs.items()};cpp,rust,_=basic.protocol_helpers(defs)
 cpp=cpp.replace('PhysicsAirTrajectory','AirTrajectory')
 rust='type PhysicsAirTrajectory=skate_core::air::state::AirTrajectory;\n'+rust
 all_defs,_=packet.declarations();selected=OrderedDict()
 def retain(name):
  if name in selected:return
  for _,kind in all_defs[name]:
   child=kind
   while packet.array(child)or packet.option(child):child=packet.array(child)[0]if packet.array(child)else packet.option(child)
   if child in all_defs:retain(child)
  selected[name]=all_defs[name]
 for name in ('ProcessedPhysicsInput','AirOutputFields'):retain(name)
 # Only read/observe transports. Numerical original source is never translated.
 cp=[];rp=[]
 for name,fields in selected.items():
  cp.append(f'void Observe(Output& o,const {name}& s){{'+''.join(packet.observe_expr(k,'s.'+f,'cpp')for f,k in fields)+'}')
  rp.append(f'fn observe_{name}(o:&mut Output,s:&{packet.rust_kind(name)}){{'+''.join(packet.observe_expr(k,'s.'+f,'rust')for f,k in fields)+'}')
  cp.append(f'{name} Read{name}(Input& i){{{name} s;'+''.join('s.'+f+'='+packet.read_expr(k,'cpp')+';'for f,k in fields)+'return s;}')
  rp.append(f'fn read_{name}(i:&mut Input)->{packet.rust_kind(name)}{{'+packet.rust_kind(name)+'{'+''.join(f+':'+packet.read_expr(k,'rust')+','for f,k in fields)+'}}')
 cp='\n'.join(cp);rp='\n'.join(rp)
 return cpp+'\n'+cp,rust+'\n'+rp

def providers():
 cp=PLUGIN/'Tests/Simulation/player_grind_input_probe.cpp';rp=PLUGIN/'Tests/Reference/player_grind_input_probe.rs'
 cpp='\n'.join(extract(cp,m)for m in('PlayerGrindStaticProvider ReadProvider(Input& i)',))
 rust='\n'.join(extract(rp,m)for m in('fn read_provider(i:&mut Input)',))
 rust=re.sub(r'(?<![\w.])\.(\d)',r'0.\1',rust)
 return cpp,rust

# Independent outer cases each construct the actual stock owners. Every query,
# accepted trajectory, body/target update and contact is produced by those owners.
def zero(kind,defs):
 a=packet.array(kind);o=packet.option(kind)
 if a:return [zero(a[0],defs)for _ in range(a[1])]
 if o:return None
 if kind in ('RawVector','AttributeName'):return [0]*(4 if kind=='RawVector'else 5)
 if kind=='RawMatrix':return [[0]*4 for _ in range(4)]
 if kind=='f32':return 0.0
 if kind in ('u8','u16','u32','u64','i32','bool','NativeReferenceBase'):return 0
 return {f:zero(k,defs)for f,k in defs[kind]}

def corpus():
 defs,_=packet.declarations();cases=[];out=Stream()
 empty=dict(rails=[],segments=[],guids=[],assets=[],manifest={});rail=provider.authored_provider([[0,-.03,-3],[0,-.03,3]],name='air-rail')
 def command_packet(n,previous=300,mode=1,flags=0,frames=12):
  p=zero('ProcessedPhysicsInput',defs)
  p.update(flags_2468=0x2000|flags,flags_2472=0x2000000 if n%5==0 else 0,flags_2476=(0,8,1<<23)[n%3],flags_2480=0,flags_2484=0,flags_2488=0,state_2508=200,category_2512=200,state_2504=previous,category_2516=400 if n%7==0 else 200,state_variant_index_2528=mode,timestep_2604=1/60,gravity_2648=9.81,state_timer_2664=.137 if n%3 else 0,transition_2636=(0,.317,.731)[n%3],scalar_2612=3.137,scalar_2652=3.137,scalar_2616=3.137,actor_query_2948=17,actor_query_2952=0xffffffff)
  p['vectors_464_480_496_512_528']=[foot.fs([0,1,0,0]),foot.fs([0,-.03,0,0]),foot.fs([0,-.03,0,0]),foot.fs([0,0,1,0]),foot.fs([0,1,0,0])]
  p['vectors_544_560_592_608'][0]=foot.fs([0,1,0,0]);p['prepared_jump_704']=foot.fs([.137,4.137,3.137,0])
  s=Stream();s.word(0);packet.encode(s,'ProcessedPhysicsInput',p,defs)
  for w in foot.fs([.137,4.137,3.137,0]):s.word(w)
  s.word(frames);s.float((-.317,0,.317)[n%3]);s.float((0,.137)[n%2]);s.float((0,.317)[n%2])
  return list(struct.unpack('<'+'I'*(len(s.data)//4),s.data))
 def add(n,commands,label):
  w=[(1,2,3)[n%3]];p=(empty,rail,provider.stock_provider())[n%3]
  # Independent raw rail/WMET transport; the original ignores the separately
  # converted C++ segment transport and constructs StaticProvider from SkateMap.
  s=provider.Stream();provider.encode_provider(s,p);pw=list(struct.unpack('<'+'I'*(len(s.data)//4),s.data));raw=w+pw+[len(commands)]+[v for c in commands for v in c]
  cases.append(dict(index=len(cases),label=label,world=n%3,commands=commands));return raw
 records=[]
 for n in range(12):
  commands=[command_packet(n),[1,n%4],[2,1],[13],[14],[19],[3]]
  for k in range(24):
   previous=(100,103,201,300,500,701)[(n+k)%6];flags=(0,0x4000,0x8000,8,0x2000)[(n+k)%5];frames=(0,11,12,24)[(n+k)%4]
   commands += [command_packet(n+k,previous,n%5,flags,frames),[1,(n+k//6)%4],[2,1],[13],[4],[14],[6],[7]]
   # KnownAir reads the genuinely completed selection and preserves missing-
   # selection errors too; no winning result is injected into either owner.
   if k%4==1:commands += [[8],[9],[11],[12],[10,(100,200,201,300,400)[k%5]]]
   if k%8==0:commands += [[5],[3]]
   if k%9==0:commands += [[16],[4]]
  commands += [[5],[22],[21,0],[21,1],[21,2],[21,3],[21,4]]
  records.append(add(n,commands,'real stock pose, actual queries/shared solve/feedback; retained Air and KnownAir publication'))
 # Ordered error prefixes with concrete earlier controller/reset/body effects.
 for n in range(4):
  commands=[command_packet(n),[1,n],[2,1],[13],[14],[19],[3],[4],[14],[6],[7]]
  commands += [[2,0],[4],[8],[9],[10,300],[11],[12],[2,1]]
  commands += [[1,4],[4],[8],[9],[11],[12],[1,n]]
  commands += [command_packet(n,300,9),[4],[8],[9],[11],[12],command_packet(n)]
  commands += [[17,1],[3],[4],[17,0],[3],[4],[18,0xffffffff,0xffffffff],[9],[12],[18,0,0]]
  commands += [[15,2],[13],[4],[14],[6],[7]]
  records.append(add(n,commands,'real partial failures: toolkit, hierarchy, mode, override, packet flags and world lifetimes'))
 out.word(len(records))
 for record in records:
  for word in record:out.word(word)
 return bytes(out.data),cases

def feedback_helpers():
 s=dispatcher.source('crates/skate-core/src/physics/skeleton_body/collision_feedback.rs');names=('BoneContact','ContactRegion','ContactPlane','SpecificContact','SkeletonContactFlags','SkeletonCollisionFeedback');defs={}
 for name in names:
  body=re.search(r'pub struct '+name+r'\s*\{(.*?)\n\}',s,re.S).group(1)
  defs[name]=[(f,re.sub(r'\s+','',k))for f,k in re.findall(r'pub (\w+): ([^,\n]+),',body)if f!='settings']
 aliases={'BoneContact':'SkeletonBoneContact','ContactRegion':'SkeletonContactRegion','ContactPlane':'SkeletonContactPlane','SpecificContact':'SkeletonSpecificContact'}
 def expr(kind,e,lang):
  if kind=='V':kind='[f32;4]'
  arr=packet.array(kind);opt=packet.option(kind)
  if arr or kind.startswith('Vec<'):
   child=arr[0]if arr else kind[4:-1];prefix=''if arr else (f'o.Word(std::uint32_t({e}.size()));'if lang=='cpp'else f'o.word({e}.len()as u32);')
   return prefix+(f'for(const auto& v:{e}){{{expr(child,"v",lang)}}}'if lang=='cpp'else f'for v in &{e}{{{expr(child,"*v",lang)}}}')
  if opt:return f'o.Word(bool({e}));if({e}){{{expr(opt,"*"+e,lang)}}}'if lang=='cpp'else f'o.word({e}.is_some()as u32);if let Some(v)=&{e}{{{expr(opt,"*v",lang)}}}'
  if kind=='usize':kind='u32'
  if kind in defs:return f'ObserveFeedback(o,{e});'if lang=='cpp'else f'observe_{kind}(o,&{e});'
  return packet.observe_expr(kind,e,lang)
 cpp=[];rust=[]
 for name in names:
  cpp.append(f'void ObserveFeedback(AirOutput& o,const {aliases.get(name,name)}& s){{'+''.join(expr(k,'s.'+f,'cpp')for f,k in defs[name])+'}')
  rust.append(f'fn observe_{name}(o:&mut Output,s:&'+('skate_core::physics::skeleton_body::'+name if name in ('SkeletonContactFlags','SkeletonCollisionFeedback')else 'skate_core::physics::skeleton_body::collision_feedback::'+name)+'){'+''.join(expr(k,'s.'+f,'rust')for f,k in defs[name])+'}')
 # Nested public feedback types are reexported by skeleton_body; the original
 # private child module itself is never made public or altered.
 rust=[r.replace('::skeleton_body::collision_feedback::','::skeleton_body::')for r in rust]
 return '\n'.join(cpp),'\n'.join(rust)

FOOT_FORWARD=r'''
pub(crate)fn migration_air_snapshot(o:&mut crate::Output,p:&super::GamePhysics,s:&super::SkaterRuntime){migration::snapshot(o,p,s,&s.player_input.physical.air)}
pub(crate)fn migration_air_world(i:&mut crate::Input)->skate_core::physics::board_world::BoardWorld{migration::world(i)}
pub(crate)fn migration_air_loaded(p:&std::path::Path)->Result<crate::graph_runtime::LoadedGraph,String>{migration::loaded(p)}
'''
KNOWN_OBSERVER=r'''
pub(crate)fn migration_air_empty_output()->KnownAirOutput{output::storage(&skate_core::player::input_phase::AirOutputFields::default())}
impl KnownAir{pub(crate)fn migration_air_observe(&self,o:&mut crate::Output){crate::observe_KnownAirState(o,&self.state);crate::observe_KnownAirSettings(o,&self.settings);for m in self.modes{crate::observe_KnownAirModeSettings(o,&m)}crate::observe_KnownAirWipeoutSettings(o,&self.wipeout);o.floats(self.flip_axis_adjustment)}}
'''
WIPEOUT_PLANT=r'''
impl Wipeout{pub(crate)fn migration_air_check_plant(&mut self,input:&Observations<'_>)->Result<(),String>{let frame=input.frame()?;wipeout::check_plant(&mut self.state,&self.settings,&frame);Ok(())}}
'''
FORCE_OBSERVER=r'''
impl BoardForceQueue{pub fn migration_air_words(&self)->Vec<u32>{let mut out=vec![self.count as u32];for f in self.entries{out.push(f.tag);out.extend([f.force_world.x,f.force_world.y,f.force_world.z,f.point_body.x,f.point_body.y,f.point_body.z].map(f32::to_bits));}out}}
'''

def prepare(output):
 output.mkdir(parents=True,exist_ok=True);original,report=frozen_sources(output);observed=output/'observed-source'
 if observed.exists():shutil.rmtree(observed)
 shutil.copytree(original,observed);crate=observed/'atelier-host';host=original/'crates/skate-host/src'
 hp,hm=foot.extraction(PLUGIN/'Tests/Reference/handplant_observer.rs','pub(super) fn run(');lp,lm=foot.extraction(PLUGIN/'Tests/Reference/handplant_lifecycle_observer.rs','pub(super) fn run(');ap,am=foot.extraction(PLUGIN/'Tests/Reference/air_reckoning_observer.rs','fn core_input(')
 htail=b'\npub(super) fn shared(o:&mut Output,p:&GamePhysics,s:&SkaterRuntime){snapshot(o,p,s)}\n}\npub(crate)fn migration_footplant_shared_snapshot(o:&mut crate::Output,p:&super::GamePhysics,s:&super::SkaterRuntime){migration::shared(o,p,s)}\n'
 atail=b'\npub(super)fn observe(o:&mut Output,a:&AirReckoning,r:&RidingOutputs){out_state(o,&a.state);for w in *r.body_spin.words(){o.word(w)}for w in r.reckoning.migration_air_reckoning_words(){o.word(w)}out_frames(o,&r.reckoning_frames)}\n}\npub(crate)fn migration_lifecycle_observe(o:&mut crate::Output,a:&AirReckoning,r:&RidingOutputs){migration::observe(o,a,r)}\n'
 extensions={'physics/handplant.rs':b'\n'+hp+lp+htail,'physics/air_reckoning.rs':b'\n'+ap+atail,'physics/footplant.rs':b'\n'+(PLUGIN/'Tests/Reference/footplant_observer.rs').read_text().replace('fn snapshot(', 'pub(super) fn snapshot(').replace('fn world(', 'pub(super) fn world(').replace('fn loaded(', 'pub(super) fn loaded(').encode()+FOOT_FORWARD.encode(),'physics/footplant/ground.rs':b'\npub(crate)fn migration_footplant_start(f:&mut Footplant,c:[f32;4],v:[f32;4])->u32{f.start(c,v)}\npub(crate)fn migration_footplant_adjust(f:&mut Footplant,t:f32,a:[f32;2]){f.adjust(t,a)}\n','physics/air_trajectory/mod.rs':b'\n'+(PLUGIN/'Tests/Reference/footplant_trajectory_observer.rs').read_bytes(),'physics/known_air.rs':KNOWN_OBSERVER.encode(),'physics/wipeout.rs':WIPEOUT_PLANT.encode(),'physics.rs':b'\n'+(PLUGIN/'Tests/Reference/air_phase_runtime_observer.rs').read_bytes()}
 staged={}
 for p in sorted(host.rglob('*.rs')):
  rel=p.relative_to(host).as_posix()
  if rel in('lib.rs','main.rs'):continue
  raw=p.read_bytes();extra=extensions.get(rel,b'');dest=crate/'src'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw+extra);assert dest.read_bytes()[:len(raw)]==raw;staged[rel]=dict(original_prefix_bytes=len(raw),original_prefix_sha256=digest(p),append_sha256=hashlib.sha256(extra).hexdigest(),generated_sha256=digest(dest))
 core={'crates/skate-core/src/riding/ground_orientation.rs':foot.lifecycle.air.CORE_OBSERVER.encode(),'crates/skate-core/src/physics/skeleton_motion.rs':b'\nimpl SkeletonMotion{pub fn migration_lifecycle_previous(&self)->f32{self.previous_board_at_y}}\n','crates/skate-core/src/air/trajectory/selector.rs':b'\nimpl TrajectorySelector{pub fn migration_footplant_stage(&self)->[u32;2]{[u32::from(self.pass),u32::from(self.adjusted_on_vert)]}}\n','crates/skate-core/src/physics/force_queue.rs':FORCE_OBSERVER.encode()}
 for rel,extra in core.items():raw=(original/rel).read_bytes();(observed/rel).write_bytes(raw+extra);assert (observed/rel).read_bytes()[:len(raw)]==raw
 cpp,rust=helpers();fc,fr=feedback_helpers();pc,pr=providers()
 # Actual authored metadata fixture is shared declaration/transport source only.
 cpworld=extract(PLUGIN/'Tests/Simulation/player_grind_input_probe.cpp','WorldGeometry World(unsigned kind)').replace('World(unsigned kind)','FixtureWorld(unsigned kind)')
 rpworld=extract(PLUGIN/'Tests/Reference/player_grind_input_probe.rs','fn fixture_world(kind:u32)');rpworld=re.sub(r'(?<![\w.])\.(\d)',r'0.\1',rpworld)
 rust_probe=PLUGIN/'Tests/Reference/air_phase_runtime_probe.rs';rs=rust_probe.read_text().replace('// GENERATED_PROTOCOL',rust+'\n'+fr).replace('// GENERATED_PROVIDER',pr+'\n'+rpworld);(crate/'src/migration_probe.rs').write_text(rs)
 cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text()+'''\nskate-core={path="../crates/skate-core"}\nskate-data={path="../crates/skate-data"}\nskate-net={path="../crates/skate-net"}\nhalf="2.7.1"\nbevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}\n[[bin]]\nname="air-phase-runtime-reference"\npath="src/migration_probe.rs"\n''')
 snapshot=output/'simulation-source'
 if snapshot.exists():shutil.rmtree(snapshot)
 snapshot.mkdir();hashes={}
 for p in [*sorted(CODE.glob('*.h')),*[CODE/(u+'.cpp')for u in UNITS]]:shutil.copy2(p,snapshot/p.name);hashes[p.name]=digest(snapshot/p.name)
 for name in('handplant_probe.cpp',):p=PLUGIN/'Tests/Simulation'/name;shutil.copy2(p,snapshot/name);hashes[name]=digest(p)
 lp,lmeta=foot.extraction(PLUGIN/'Tests/Simulation/handplant_lifecycle_probe.cpp','int main(');(snapshot/'handplant_lifecycle_helpers.inc').write_bytes(lp)
 prefix,fmeta=foot.extraction(PLUGIN/'Tests/Simulation/footplant_probe.cpp','int main(')
 cpp=re.sub(r'\bInput\b','AirInput',cpp);cpp=re.sub(r'\bOutput\b','AirOutput',cpp);pc=re.sub(r'\bInput\b','AirInput',pc);pc=re.sub(r'\bOutput\b','AirOutput',pc)
 probe=PLUGIN/'Tests/Simulation/air_phase_runtime_probe.cpp';simulation=probe.read_text().replace('// GENERATED_PROTOCOL',cpp+'\n'+fc).replace('// GENERATED_PROVIDER',pc+'\n'+cpworld).replace('// GENERATED_COLLISION_OBSERVER','ObserveFeedback(o,p.collision_feedback);')
 (snapshot/probe.name).write_bytes(b'#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wunused-function"\n'+prefix+b'\n#pragma clang diagnostic pop\n'+simulation.encode())
 report.update(staged_host_original_prefixes=staged,extracted_observer_prefixes=[hm,lm,am,lmeta,fmeta],appended_core_observers={rel:dict(original_prefix_sha256=digest(original/rel),generated_sha256=digest(observed/rel),append_sha256=hashlib.sha256(extra).hexdigest())for rel,extra in core.items()},simulation_source_sha256=hashes,generated_simulation_probe_sha256=digest(snapshot/probe.name),generated_reference_probe_sha256=digest(crate/'src/migration_probe.rs'),probe_sha256={p.name:digest(p)for p in(probe,rust_probe,PLUGIN/'Tests/Reference/air_phase_runtime_observer.rs')})
 (output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');return original,observed,snapshot,report

def loader_fixtures(assets):
 data=json.loads((assets/'private/stock/skater-collections.json').read_text())
 order=[('physics_airstates','default','BodySpinInputFilter','words')]+[('physics_mode',m,'GrindLockDist','float')for m in('easy','normal','hardcore','motorized','test')]+[('physics_airstates','default',n,'float')for n in('SpeedToAlignToGround_PhysAir','MaxSpinSpeed','DontAlignAnglePhysicsAir')]+[('physics_steering','default','SteeringTiltBlending','float')]
 def resolve(d,field):
  category,key,name,_=field
  for _ in range(len(d['collections'])+1):
   r=next(r for r in d['collections']if converter.name_id(r['class'])==converter.name_id(category)and converter.name_id(r['key'])==converter.name_id(key));actual=next((n for n in r['fields']if converter.name_id(n)==converter.name_id(name)),None)
   if actual is not None:return r['fields'],actual
   key=r['parent'];assert key
  raise AssertionError(field)
 def change(d,f,kind):
  category,key,name,typ=f;fields,n=resolve(d,f);old=copy.deepcopy(fields[n])
  if kind=='missing':
   record=next(r for r in d['collections']if converter.name_id(r['class'])==converter.name_id(category)and converter.name_id(r['key'])==converter.name_id(key))
   # Stop this one fixture key's inheritance so another mode's independent
   # override survives. All five distance reads keep their distinct errors.
   record['parent']=''
   for field in list(record['fields']):
    if converter.name_id(field)==converter.name_id(name):del record['fields'][field]
  elif kind=='collection':d['collections']=[r for r in d['collections']if not(converter.name_id(r['class'])==converter.name_id(category)and converter.name_id(r['key'])==converter.name_id(key))]
  elif kind=='type':fields[n]={**old,'type':'EA::Reflection::Boolean'}
  elif kind=='width':fields[n]={**old,'data':old['data']+'cafebabe'}
  elif kind=='short':fields[n]={**old,'data':'deadbeef'if typ=='words'else ''}
  elif kind=='nan':fields[n]={**old,'data':('7fc01234'+old['data'][8:])if typ=='words'else '7fc01234'}
  elif kind=='inf':fields[n]={**old,'data':('7f800000'+old['data'][8:])if typ=='words'else '7f800000'}
  else:raise AssertionError(kind)
 result=[]
 for pos,f in enumerate(order):
  for kind in('missing','collection','type','width','short','nan','inf'):
   d=copy.deepcopy(data);change(d,f,kind);success=f[3]=='words'and kind in('type','nan','inf')
   result.append(dict(label=f'{pos:02d}-{f[2]}-{kind}',data=d,success=success,first_position=pos))
  # Every suffix is independently invalid so a changed implementation read
  # order cannot pass by stopping at an unrelated earlier field.
  for later in range(pos+1,len(order)):
   d=copy.deepcopy(data);change(d,f,'width');change(d,order[later],'width');result.append(dict(label=f'compound-{pos:02d}-before-{later:02d}',data=d,success=False,first_position=pos,second_position=later))
 return result

class Reader(foot.Reader):
 def __init__(self,raw):self.words=memoryview(raw).cast('I');self.at=0
 def take(self,n):v=self.words[self.at:self.at+n];self.at+=n;assert len(v)==n;return v
 def phases(self):
  assert self.word()==len(SECTIONS);v={};spans={}
  for name in SECTIONS:
   n=self.word();at=self.at;v[name]=self.take(n);spans[name]=[at,self.at]
  return v,spans

def decode(raw,cases):
 r=Reader(raw);assert r.word()==len(cases);frames=[]
 def snapshot():
  phases,spans=r.phases();f=r.foot();spans.update(r.foot_spans);s=r.snapshot();spans.update(r.spans);return dict(phase=phases,foot=f,shared=s,spans=spans)
 for case in cases:
  case['first_output_word']=r.at;assert r.word()==len(case['commands']);prior=snapshot();rows=[]
  for command in case['commands']:
   at=r.at;assert r.word()==command[0];error=r.status();current=snapshot();rows.append(dict(operation=command[0],error=error,first_word=at,last_word=r.at,**current,prior=prior));prior=current
  case['last_output_word']=r.at;frames.append(rows)
 assert r.at==len(r.words),(r.at,len(r.words));return frames

def coverage(frames,cases):
 counts=Counter();errors=Counter();selections=0;air_updates=known_updates=solves=0;body_changes=pose_changes=partial=0;com_states=set();countdowns=set();known_states=set()
 for rows,case in zip(frames,cases):
  for row,cmd in zip(rows,case['commands']):
   op=cmd[0];counts[OPS[op]]+=1;p=row['phase'];old=row['prior']['phase'];shared=row['shared'];before=row['prior']['shared'];a=p['air_state']
   assert len(a)==24 and len(p['air_settings'])==25
   com_states.add(a[21]);countdowns.add(a[23]);known_states.add(tuple(p['known_state_settings'][:43]))
   if row['error']:errors[row['error']]+=1;partial+=p['lifecycle']!=old['lifecycle']or shared['roots']!=before['roots']or shared['bodies_blend']!=before['bodies_blend']
   if op==4 and row['error']is None:air_updates+=1
   if op==9 and row['error']is None:known_updates+=1
   if op==14 and row['error']is None:solves+=1
   if op==16:assert row['foot']['trajectory'][0]==0
   if op in(4,9):body_changes+=shared['bodies_blend']!=before['bodies_blend'];pose_changes+=shared['roots']!=before['roots']
   trace=foot.trajectory_observation(row['foot']['trajectory']);selections+=trace['selection']is not None
   if op in(8,9,10,11,12)and row['error']:assert p['known_state_settings'][:43]==old['known_state_settings'][:43], 'original retains Known state after failed live adapter'
   if op==10 and row['error']is None:assert a[21]in(0,1)
 assert air_updates>32 and solves>200 and body_changes>16 and pose_changes>16
 assert selections>16 and known_updates>8,'KnownAir must consume actual winning original world queries'
 assert len(com_states)==2 and len(countdowns)>4 and len(known_states)>8
 assert any('BoardToolkit'in e for e in errors)and any('mode 9'in e for e in errors)
 return dict(operations=dict(counts),errors=dict(errors),successful_air_updates=air_updates,successful_known_updates=known_updates,successful_shared_solves=solves,selected_records=selections,body_changes=body_changes,root_changes=pose_changes,partial_error_mutations=partial,com_states=sorted(com_states),countdowns=sorted(countdowns),distinct_known_states=len(known_states))

def preflight(raw,cases):
 r=Reader(raw);assert r.word()==len(cases);ranges=[]
 def provider_wire():
  for _ in range(r.word()):
   r.take(r.word());r.word();r.take(3*r.word());simulation=r.word()
   if simulation:r.take(r.word())
  r.take(r.word());r.take(24*r.word());r.take(4*r.word())
  for _ in range(r.word()):r.take(r.word());r.take(r.word());r.take(5);r.take(r.word())
 for case in cases:
  start=r.at*4;r.word();provider_wire();assert r.word()==len(case['commands'])
  for cmd in case['commands']:assert list(r.take(len(cmd)))==cmd,(case['index'],cmd[0])
  ranges.append((start,r.at*4))
 assert r.at==len(r.words)
 for unit in UNITS:assert (CODE/(unit+'.cpp')).is_file(),unit
 return ranges

def build(output,target):
 original,observed,snapshot,report=prepare(output);crate=observed/'atelier-host';subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(crate/'Cargo.toml'),'--target-dir',str(target.resolve()),'--bin','air-phase-runtime-reference'],check=True)
 reference=output/'air-phase-runtime-reference';shutil.copy2(target.resolve()/'release/air-phase-runtime-reference',reference);simulation=output/'air-phase-runtime-simulation'
 subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'air_phase_runtime_probe.cpp'),'-o',str(simulation)],check=True)
 for rel,sha in report['original_source_sha256'].items():
  assert digest(original/rel)==sha;raw=(original/rel).read_bytes();assert (observed/rel).read_bytes()[:len(raw)]==raw,rel
 for rel,row in report['staged_host_original_prefixes'].items():assert digest(crate/'src'/rel)==row['generated_sha256'],rel
 report.update(reference_binary_sha256=digest(reference),simulation_binary_sha256=digest(simulation));(output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');return simulation,reference

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in('assets','samples','output','target-dir'):p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 raw,cases=corpus();ranges=preflight(raw,cases);(out/'input.bin').write_bytes(raw);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');fixtures=loader_fixtures(a.assets.resolve())
 if a.preflight:
  prepare(out);print(json.dumps(dict(cases=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(raw),loader_fixtures=len(fixtures),units=len(UNITS),input_sha256=hashlib.sha256(raw).hexdigest()),indent=2));return
 bank=out/'fixtures';bank.mkdir(exist_ok=True);stock=a.assets.resolve()/'private/stock';(bank/'settings.simulation').write_bytes(converter.encode_settings(stock/'skater-collections.json'));(bank/'physics.simulation').write_bytes(converter.encode_physics_skeletons(stock/'physics-skeletons.json'))
 for kind in('action','motion'):(bank/f'actor.{kind}.reference').write_bytes(original_graph(element('state','idle')))
 identity=json.loads((stock/'physics-skeletons.json').read_text())['source_sha256'];simulation,reference=build(out,a.target_dir)
 simulation_args=[str(bank/'settings.simulation'),str(bank/'physics.simulation'),str(a.samples.resolve()/'simulation/rig.skate'),identity,str(a.assets.resolve())]
 expected=subprocess.check_output([str(reference),str(a.assets.resolve()),str(bank)],input=raw);actual=subprocess.check_output([str(simulation),*simulation_args],input=raw);(out/'reference.bin').write_bytes(expected);(out/'simulation.bin').write_bytes(actual);frames=decode(expected,cases)
 if expected!=actual:
  at=next((k for k,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));word=at//4;case=next((c for c in cases if c['first_output_word']<=word<c['last_output_word']),None);row=next((r for rows in frames for r in rows if r['first_word']<=word<r['last_word']),None);section=next(((n,word-s[0])for n,s in(row['spans'].items()if row else[])if s[0]<=word<s[1]),None)
  failure=dict(byte=at,word=word,reference_bytes=len(expected),simulation_bytes=len(actual),case=case['index']if case else None,operation=row['operation']if row else'initial',section=section,reference_hex=expected[max(0,at-16):at+32].hex(),simulation_hex=actual[max(0,at-16):at+32].hex());(out/'first-divergence.json').write_text(json.dumps(failure,indent=2)+'\n');raise AssertionError(failure)
 covered=coverage(frames,cases);del frames
 loader_results=[]
 for n,fixture in enumerate(fixtures):
  folder=out/'loader-fixtures'/f'{n:03d}-{fixture["label"]}';(folder/'private/stock').mkdir(parents=True,exist_ok=True);json_path=folder/'private/stock/skater-collections.json';json_path.write_text(json.dumps(fixture['data'])+'\n');simulation_bank=folder/'settings.simulation';simulation_bank.write_bytes(converter.encode_settings(json_path))
  ref=subprocess.check_output([str(reference),str(a.assets.resolve()),str(bank),str(folder)],input=b'');cpp=subprocess.check_output([str(simulation),*simulation_args,str(simulation_bank)],input=b'');(folder/'reference.bin').write_bytes(ref);(folder/'simulation.bin').write_bytes(cpp);assert ref==cpp,(fixture['label'],ref.hex(),cpp.hex());status=struct.unpack_from('<I',ref)[0];assert bool(status)==fixture['success'],fixture['label'];loader_results.append(dict(label=fixture['label'],success=bool(status),sha256=hashlib.sha256(ref).hexdigest(),first_position=fixture['first_position']))
 result=dict(passed=True,reference_revision=REFERENCE_REVISION,cases=len(cases),commands=sum(len(c['commands'])for c in cases),bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),input_sha256=hashlib.sha256(raw).hexdigest(),coverage=covered,loader_fixtures=loader_results,scope='Whole unchanged actual AirPhase and KnownAir core/host, concrete controller/pose/root/FootIK/Footplant/selector/shared solve/collision feedback/wipeout owners, full output and ordered staged Air settings errors.',boundaries='Caller canonical Processed and post-jump packets, authored hierarchy selector and independent raw-rail/WMET/triangle metadata are explicit upstream inputs. Physical records, world hits, winning predictions, targets, drives, correction and forces are actual producers. Global player/state dispatch, scene streaming service, ragdoll wipeout states and source-hang/unsupported query domains remain separately scoped; no accepted prediction or callback success is injected.')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='loader_fixtures'},indent=2))
if __name__=='__main__':main()
