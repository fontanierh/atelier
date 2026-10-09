#!/usr/bin/env python3
"""Complete pinned Wipeout300 host over canonical physical/pose/IK owners.

Only the root coordinator compiles/runs this proof. --preflight stages the
unchanged reference and immutable simulation snapshot without compiler/probe calls.
"""
import argparse
from collections import Counter,OrderedDict
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import check_player_teleport_runtime_parity as reset
import check_grind_runtime_parity as grind
import check_ground_control_settings_parity as stock
import player_input_protocol as protocol
from check_animation_playback_parity import Stream,bits
from check_graph_parity import element,original_graph
from session_parity import REFERENCE_REVISION,digest
PLUGIN=reset.PLUGIN
CODE=reset.CODE
HOST=reset.HOST
CORE='crates/skate-core/src/player/wipeout_state/'
WIPEOUT_UNITS=('WipeoutPhysicalState','WipeoutDrives','WipeoutPhysicalSettings','WipeoutRagdoll','WipeoutPrediction','WipeoutContactResponse','WipeoutBody','WipeoutControls','WipeoutResponse','WipeoutPhysicalRuntime','WipeoutSkeleton','WipeoutPhysicalUpdate')
UNITS=tuple(dict.fromkeys((*reset.UNITS,*grind.ACTOR_UNITS,'WipeoutSettings','WipeoutObservations','WipeoutRuntime','PlayerStateSelector','PhysicalPhase',*WIPEOUT_UNITS)))
BLOCKS=('shared','wipeout','settings')
OPS={0:'completed_packets',1:'actual_reset',6:'actual_solve_feedback',10:'enter',11:'exit',12:'actual_toolkit',13:'advance',14:'output',17:'post_physics',18:'remove_toolkit',21:'explicit_initial_retained_state',22:'authored_pose_attributes',24:'invalid_imported_ik_bone',31:'authored_query_world',34:'actual_wheel_publication',35:'ragdoll_request',36:'restore_normal',37:'actual_body_initial_velocity',38:'actual_request_history',39:'actual_body_initial_position'}
OLD_HISTORIES=43
OLD_INPUT_BYTES=2630912
OLD_INPUT_SHA256='2da5b3814d473f0f96011fae71c9272354970dd3704ac7edb8ac7eac06e0eb54'

def source_fields(path,struct_name):
 raw=reset.source(path);body=reset.block(raw,'pub struct '+struct_name+' {')
 fields=re.findall(r'pub\s+(\w+):\s*([^,\n]+)',body)
 fields=[(f,k.strip().replace('usize','u32').replace('V','[f32;4]').replace(' ','').replace('PointGraph<8>','Graph8'))for f,k in fields]
 assert fields,(path,struct_name);return fields

def schemas():
 return OrderedDict(State=source_fields(CORE+'data.rs','State'),Output=source_fields(CORE+'output.rs','Output'),Profile=source_fields(CORE+'profiles.rs','Profile'))

def observers():
 d=schemas();cpp=[];rust=[]
 simulation={'State':'WipeoutPhysicalState','Output':'WipeoutPhysicalOutput','Profile':'WipeoutControlProfile'}
 original={'State':'skate_core::player::wipeout_state::State','Output':'skate_core::player::wipeout_state::output::Output','Profile':'skate_core::player::wipeout_state::profiles::Profile'}
 for name,fields in d.items():
  def observe(f,k,lang):
   if k=='Graph8':return ('o.Floats(s.'+f+'.x);o.Floats(s.'+f+'.y);')if lang=='cpp'else('o.floats(s.'+f+'.x);o.floats(s.'+f+'.y);')
   return protocol.observe_expr(k,'s.'+f,lang)
  cpp.append('void ObserveWipeout'+name+'(Output& o,const '+simulation[name]+'& s){'+''.join(observe(f,k,'cpp')for f,k in fields)+'}')
  rust.append('fn observe_wipeout_'+name+'(o:&mut Output,s:&'+original[name]+'){'+''.join(observe(f,k,'rust')for f,k in fields)+'}')
 fields=d['State'];cpp.append('WipeoutPhysicalState ReadWipeoutState(Input& i){WipeoutPhysicalState s;'+''.join('s.'+f+'='+protocol.read_expr(k,'cpp')+';'for f,k in fields)+'return s;}')
 rust.append('fn read_wipeout_State(i:&mut Input)->'+original['State']+'{'+original['State']+'{'+''.join(f+':'+protocol.read_expr(k,'rust')+(' as usize'if f=='profile'else'')+','for f,k in fields)+'}}')
 return '\n'.join(cpp),'\n'.join(rust)

def simulation_plan(output):
 snap,report=reset.simulation_plan(output)
 for u in UNITS:shutil.copy2(CODE/(u+'.cpp'),snap/(u+'.cpp'))
 raw=(snap/'player_teleport_runtime_probe.cpp').read_text();prefix=grind.reset_observer_cpp(raw[:raw.index('int main(')])
 initialization=raw[raw.index(' if(argc!=6)'):raw.index(' Input i{{')]
 construction=raw[raw.index(' for(unsigned c=0;c<count;++c){')+len(' for(unsigned c=0;c<count;++c){'):raw.index('const auto rows=i.Word();')]
 construction=construction.replace('World(i)','WipeoutWorld(i)').replace('SkeletonControllerState controller;bool elapsed=false;std::uint8_t animated=0;','GroundPhaseLifecycle life;auto& controller=life.skeleton_controller;auto& elapsed=life.skeleton_elapsed_16505;auto& animated=life.board_animated_290;').replace('WipeoutRequests wipeout;','WipeoutRuntime checks;auto& wipeout=checks.state;')
 cases=raw[raw.index(' case 0:'):raw.index(' case 2:')]+raw[raw.index(' case 6:'):raw.index(' case 5:')]
 template=PLUGIN/'Tests/Simulation/wipeout_physical_runtime_probe.cpp';code=template.read_text().replace('// GENERATED_SIMULATION_OWNER_PREFIX',prefix).replace('// GENERATED_SIMULATION_OWNER_INITIALIZATION',initialization).replace('// GENERATED_SIMULATION_OWNER_CONSTRUCTION',construction).replace('// GENERATED_SIMULATION_PACKET_RESET_CASES',cases).replace('// GENERATED_WIPEOUT_PROTOCOL',observers()[0])
 assert code.count('GroundPhaseLifecycle life;')==1
 (snap/'wipeout_physical_runtime_probe.cpp').write_text(code)
 report.update(units=UNITS,immutable_simulation_sources={p.name:digest(p)for p in sorted(snap.glob('*.h'))+sorted(snap.glob('*.cpp'))},generated_probe_sha256=digest(snap/'wipeout_physical_runtime_probe.cpp'))
 return snap,report

MATERIAL10='''
impl Response{pub(super) fn migration_words(&self)->Vec<u32>{let mut o=Vec::new();for v in[self.previous_velocity,self.normal,self.target_velocity]{o.extend(v.map(f32::to_bits))}o.extend([self.time.to_bits(),self.phase,self.finished as u32]);o}}
'''
MATERIAL11='''
impl Response{pub(super) fn migration_words(&self)->Vec<u32>{let mut o=Vec::new();for v in[self.normal,self.previous_velocity,self.velocity]{o.extend(v.map(f32::to_bits))}o.extend([self.frames_since_contact as u32,self.active_frames as u32,self.contact_latched as u32,self.active as u32]);o}}
'''
PREDICTION='''
pub(super) fn migration_observe(o:&mut crate::Output,p:&Prediction){fn result(o:&mut crate::Output,r:QueryResult){o.floats(r.contact_position);o.floats(r.contact_normal);o.floats(r.landing_normal);o.float(r.contact_time);o.matrix(r.contact_transform);o.word(r.contact_frame as u32);o.word(r.surface);o.word(r.geometry);}result(o,p.result);o.word(p.pending.is_some()as u32);if let Some((r,t,surface))=p.pending{result(o,r);o.floats(t.position);o.floats(t.velocity);o.floats(t.acceleration);o.float(t.duration);o.word(surface as u32)}}
'''
RAGDOLL='''
pub(super) fn migration_settings(o:&mut crate::Output,r:&RagdollSetup){let s=&r.settings;for a in s.normal_limits{for v in a{o.word(v)}}for a in s.ragdoll_limits{for v in a{o.word(v)}}o.word(s.inverse_mass as u32);o.word(s.inverse_inertia as u32);o.floats(s.drag);for m in s.materials{o.floats([m.static_friction,m.dynamic_friction,m.restitution])}}
'''
RUNTIME='''
pub(crate) fn migration_owner(o:&mut crate::Output,w:&WipeoutState){crate::observe_wipeout_State(o,&w.state);o.0.extend(w.contact.migration_words());prediction::migration_observe(o,&w.prediction);}
pub(crate) fn migration_settings(o:&mut crate::Output,w:&WipeoutState){ragdoll::migration_settings(o,&w.ragdoll);let s=&w.settings;let r=s.recovery;o.floats([r.minimum_time,r.minimum_settled,r.maximum_time,r.fade_time,r.over_speed,r.over_minimum_time]);o.floats([s.remove_target_time,s.remove_drives_time,s.controlled_weight_step,s.collision_weight_step,s.board_restitution,s.board_friction,s.deck_angular_drag,s.push_force]);for m in s.standard_materials{o.floats([m.static_friction,m.dynamic_friction,m.restitution])}let d=&w.drives;for b in d.bone{o.floats(b)}o.floats(d.root);o.floats(d.strength);o.floats([d.hook_spring,d.hook_strength,d.hook_damping]);for p in &w.profiles{crate::observe_wipeout_Profile(o,p)}}
pub(crate) fn migration_load(a:&std::path::Path,settings:&std::path::Path,o:&mut crate::Output){let data=skate_data::collections::Collections::load(settings).unwrap();let banks=skate_data::animation_banks::AnimationBanks::load(a).unwrap();match WipeoutState::load(&data,a,&banks.identities[0]){Ok(w)=>{o.status(Ok(()));migration_settings(o,&w)},Err(e)=>o.status(Err(e))}}
'''

def reference_plan(output):
 original,observed,crate,cargo,report=reset.reference_plan(output)
 # Local privacy/type declarations for borrowed reset observations. Neither
 # the shared observer template nor any original production prefix is edited.
 # Both nested appended observer modules inherit this root-module alias.
 input_phase=crate/'src/physics/input_phase.rs';before=input_phase.read_bytes()
 original_prefix=(original/(HOST+'input_phase.rs')).read_bytes()
 assert before.startswith(original_prefix)
 initial=b's.ground_runtime.retained_board_normal=[0.317,0.731,-0.137,-0.];'
 setter=b's.ground_runtime.migration_wipeout_initial_retained_normal([0.317,0.731,-0.137,-0.]);'
 borrowed=before[len(original_prefix):];assert borrowed.count(initial)==1
 borrowed=borrowed.replace(initial,setter)
 input_phase.write_bytes(original_prefix+borrowed)
 local=dict(input_phase_before_sha256=hashlib.sha256(before).hexdigest(),input_phase_after_sha256=digest(input_phase),original_prefix_bytes=len(original_prefix),original_prefix_sha256=hashlib.sha256(original_prefix).hexdigest(),initial_assignment_sha256=hashlib.sha256(initial).hexdigest(),setter_call_sha256=hashlib.sha256(setter).hexdigest(),boundary='Declaration/access repair only in the inherited appended test fixture; exact initial four lanes unchanged. The original input_phase implementation prefix is byte-identical.')
 generated,_=reset.generated_observer();prefix=generated[generated.index('use super::*;'):generated.index('pub(super) fn run(')]
 cases=generated[generated.index(' 0=>'):generated.index(' 2=>')]
 observer=(PLUGIN/'Tests/Reference/wipeout_physical_runtime_observer.rs').read_text().replace('// GENERATED_ORIGINAL_OWNER_PREFIX',prefix).replace('// GENERATED_ORIGINAL_PACKET_RESET_CASES',cases)
 extensions={'physics/input_phase.rs':'\nuse crate::physics;\n'+observer,'physics/ground_runtime/mod.rs':'\nimpl GroundRuntime{pub(crate) fn migration_wipeout_initial_retained_normal(&mut self,value:[f32;4]){self.retained_board_normal=value;}}\n','physics.rs':'\npub(crate) fn migration_wipeout_physical_run(a:&std::path::Path,f:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{input_phase::migration_wipeout_physical_run(a,f,i,o)}\npub(crate) fn migration_wipeout_physical_load(a:&std::path::Path,f:&std::path::Path,o:&mut crate::Output){wipeout_states::migration_load(a,f,o)}\n','physics/wipeout_states/mod.rs':RUNTIME,'physics/wipeout_states/ragdoll.rs':RAGDOLL,'physics/wipeout_states/prediction.rs':PREDICTION}
 hashes={}
 for rel,extra in extensions.items():
  p=crate/'src'/rel;p.write_bytes(p.read_bytes()+extra.encode());hashes[rel]=dict(original_prefix_sha256=digest(original/('crates/skate-host/src/'+rel)),generated_sha256=digest(p),append_sha256=hashlib.sha256(extra.encode()).hexdigest())
 core={CORE+'contact_response/material10.rs':MATERIAL10,CORE+'contact_response/material11.rs':MATERIAL11,CORE+'contact_response.rs':'\nimpl ContactResponse{pub fn migration_words(&self)->Vec<u32>{let mut o=self.material10.migration_words();o.extend(self.material11.migration_words());o}}\n'}
 for rel,extra in core.items():
  p=observed/rel;p.write_bytes(p.read_bytes()+extra.encode());hashes[rel]=dict(original_prefix_sha256=digest(original/rel),generated_sha256=digest(p),append_sha256=hashlib.sha256(extra.encode()).hexdigest())
 template=PLUGIN/'Tests/Reference/wipeout_physical_runtime_probe.rs';code=(crate/'src/migration_probe.rs').read_text();code=code[:code.index('fn main()')]+observers()[1]+'\n'+template.read_text();(crate/'src/migration_probe.rs').write_text(code)
 cargo.write_text(cargo.read_text().replace('name="player-teleport-reference"','name="wipeout-physical-reference"'))
 report.update(wipeout_extensions=hashes,wipeout_local_declaration_adapters=local,generated_probe_sha256=digest(crate/'src/migration_probe.rs'),observer_sha256=digest(PLUGIN/'Tests/Reference/wipeout_physical_runtime_observer.rs'),scope='Complete untouched original Wipeout300 host/core, actual stock GamePhysics/SkaterRuntime constructors, original ragdoll/IK/solve/contact/query bodies. Append-only data observations and caller/wire adapters.')
 return original,observed,crate,cargo,report

def build_simulation(output):
 snap,report=simulation_plan(output);binary=output/'wipeout-physical-simulation'
 subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snap),*[str(snap/(u+'.cpp'))for u in UNITS],str(snap/'wipeout_physical_runtime_probe.cpp'),'-o',str(binary)],check=True)
 report['binary_sha256']=digest(binary);(output/'simulation-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return binary

def build_reference(output,target):
 original,observed,crate,cargo,report=reference_plan(output);subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(cargo),'--target-dir',str(target.resolve()),'--bin','wipeout-physical-reference'],check=True)
 for rel,sha in report['original_source_sha256'].items():assert digest(original/rel)==sha;raw=(original/rel).read_bytes();assert(observed/rel).read_bytes()[:len(raw)]==raw
 binary=output/'wipeout-physical-reference';shutil.copy2(target.resolve()/'release/wipeout-physical-reference',binary);report['binary_sha256']=digest(binary);(output/'reference-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return binary

def initial_state(**fields):
 s={f:reset.zero(k,{})for f,k in schemas()['State']};s.update(extra_weight=1.,maximum_speed=10.,response_frames=-1,airborne_frames=-1,teleport_countdown=-1,allow_retained_velocity=True,predicted_time=struct.unpack('<f',struct.pack('<I',0x7f7fffff))[0]);s.update(fields);return dict(op=21,state=s)

def world(material=0,height=-.05,slope=0):
 corners=[[-20,height-20*slope,-20],[20,height+20*slope,-20],[20,height+20*slope,20],[-20,height-20*slope,20]]
 return[dict(vertices=[corners[j]for j in ids],fatness=.25,edges=[1.,1.,1.],flags=0x10,material=[.8,.6,.1],tag=material<<7|11,surface=material<<7|11)for ids in((0,2,1),(0,3,2))]

def write_world(w,triangles):
 w.word(len(triangles))
 for t in triangles:
  for v in t['vertices']:
   for x in v:w.float(x)
  w.float(t['fatness'])
  for x in t['edges']:w.float(x)
  w.word(t['flags'])
  for x in t['material']:w.float(x)
  w.word(t['tag']);w.word(t['surface'])

def corpus():
 defs,_=protocol.declarations();_,baseline=reset.corpus();base=copy.deepcopy(baseline[0]['commands'][0]);rc=copy.deepcopy(next(c for c in baseline[0]['commands']if c['op']==1));cases=[]
 def packet(velocity=(.137,0.,3.,0.),position=(0.,1.,0.,0.),flags=0x2000,secondary=0,response=0,special=0,timer=0.):
  c=copy.deepcopy(base);p=c['processed'];p.update(flags_2468=flags,flags_2472=secondary,flags_2476=0,flags_2480=0,flags_2484=response,flags_2488=special,state_2508=300,category_2512=300,state_variant_index_2528=1,timestep_2604=1/60,state_timer_2664=timer,collision_scalar_2924=.25)
  p['effective_anim_transform_192']=[[bits(x)for x in r]for r in((1.,0.,0.,0.),(0.,1.,0.,0.),(0.,0.,1.,0.),(0.,0.,0.,1.))]
  p['vectors_544_560_592_608'][0]=[0,bits(1.),0,0];p['vectors_544_560_592_608'][2]=[bits(x)for x in position];p['vectors_544_560_592_608'][3]=[bits(x)for x in velocity];p['vectors_720_784_800_816_832_864'][3]=[bits(x)for x in(.137,.317,.731,0.)];p['probe_1792']['byte_104']=0
  c['physical']['state'].update(state_16=300,category_12=300);return c
 def setup(**kw):
  r=copy.deepcopy(rc);r.update(target=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,-.035,0.,0.]],pose=0,attributes=[],actions=[0.]*18)
  return[packet(**kw),r,packet(**kw),dict(op=22,pose=0,control=[.137,-.317],gesture=[0.,0.]),dict(op=12)]
 def tick(solve=False):return[dict(op=13)]+([dict(op=6),dict(op=17)]if solve else[])+[dict(op=14)]
 def add(label,commands,triangles=None):cases.append(dict(index=len(cases),label=label,world=world()if triangles is None else triangles,commands=commands))
 gestures=((0.,0.),(.2,.2),(.731,0.),(0.,-.731),(-.731,0.))
 for profile,g in enumerate(gestures):
  for material in(0,10,11,12):
   commands=setup(velocity=(3.,-4.,.731,0.),response=(profile%4)*16)+[dict(op=10),dict(op=22,pose=profile%4,control=[.731,-.317],gesture=list(g))]
   commands += [dict(op=37,part=n,velocity=[3.,-4.,.731])for n in range(1,24)]
   commands += tick()*4+[dict(op=39,delta=[0.,-.75,0.])]
   for k in range(24):commands += [packet(velocity=(3.,-4.,.731,0.),timer=(k+1)/60,response=(profile%4)*16),dict(op=6),dict(op=17)]+tick()
   commands += [dict(op=11),dict(op=36),dict(op=14),dict(op=10),dict(op=6),dict(op=17),dict(op=14)]+tick()*2
   add('all five profiles with actual solved material '+str(material),commands,world(material,slope=.15 if material==11 else 0))
 commands=setup(velocity=(0.,0.,3.,0.))+[dict(op=10)]+[dict(op=37,part=n,velocity=[0.,-4.,3.])for n in range(1,24)]+[dict(op=6),dict(op=17)]+tick()*4
 add('actual contact with constructor-retained velocity selects material10 phase4',commands,world(10))
 # Real synchronous hit consumed next update; miss retains predicted seconds.
 for material in(0,12):
  commands=setup(velocity=(0.,-2.,0.,0.),position=(0.,.37,0.,0.))+[dict(op=10)]+tick()*3+[dict(op=31,world=[])]+tick()*3+[dict(op=31,world=world(material))]+tick()*2
  add('actual prediction completion then miss retention '+str(material),commands,world(material))
 add('real late query failure consumes pending completion',setup(velocity=(0.,-2.,0.,0.),position=(0.,.37,0.,0.))+[dict(op=10)]+tick()+[packet(position=(0.,float('inf'),0.,0.))]+tick()*2)
 for special in(False,True):
  commands=setup(position=(0.,-.5,0.,0.),special=0x40000000 if special else 0)+[dict(op=10)]
  commands += [initial_state(time=2.,response_time=1.,special_surface=True,surface_height=.25,velocity=[0.,-1.,0.,0.])]+tick()*3+[dict(op=31,world=world(0))]+tick()*3
  add('actual special-surface probe completion and release',commands,world(12))
 # Focused caller-retained state inputs exercise complete source branches.
 for label,state,flags,response in(
  ('response pulse',dict(time=1.,response_time=.09,maximum_speed=17.,response_count=1),0x2000,0x100),
  ('zero-strength response',dict(time=2.,response_time=.5,slow_time=1.1,response_count=7),0x2000,0x100),
  ('retained air then release',dict(time=.5,airborne_frames=20),0x2008,0),
  ('over air control',dict(time=2.,over=True,slow=True),0x2000,0),
  ('settled manual reset',dict(time=2.,over=True,slow=True,response_time=2.,maximum_speed=0.,slow_time=2.,extra_weight=0.,extra_weight_zero_time=1.),0x2000,0),
  ('impaled countdown',dict(time=2.,ever_impaled=True,impaled_time=.49),0x2000,0x400000),
  ('automatic fade',dict(time=20.,response_time=20.,slow_time=2.),0x2000,0),
 ):
  commands=setup(flags=flags,response=response)+[dict(op=10),initial_state(**state)]+tick()*12
  commands += [packet(flags=flags&~8,secondary=0x00100000 if label=='settled manual reset'else 0,response=response)]+tick()*5+[dict(op=17),dict(op=14)]
  add(label,commands,[])
 # Enter transformations operate on real body rates and the sole request history.
 for flags,special in((0x2004,0),(0x2008,0),(0x2000,0x200000),(0x2008,0x40000000)):
  p=packet(flags=flags,special=special);p['processed']['vector_1520']=[bits(x)for x in(.137,.731,.317,0.)];p['processed']['probe_1792']['byte_104']=1;p['processed']['probe_1792']['vector_80']=[bits(x)for x in(.731,.317,.137,0.)]
  commands=setup()+[p,dict(op=38,reason=6,value=.731)]+[dict(op=37,part=n,velocity=[3.+n,-2.,.731])for n in(1,12,23)]+[dict(op=10),dict(op=14),dict(op=11)]
  add('complete Enter body/board/IK/material writes '+str(flags)+'/'+str(special),commands)
 # Simulation source partial failures after earlier state/skeleton stores.
 for missing in('board_toolkit','ik_bone','empty_hierarchy','truncated_hierarchy'):
  commands=setup(secondary=0x800)+[dict(op=10)]
  if missing=='board_toolkit':commands += [dict(op=18)]
  elif missing=='ik_bone':commands += [dict(op=24,part=23,value=0xffffffff)]
  else:commands += [dict(op=22,pose=4 if missing=='empty_hierarchy'else 5,control=[.731,.317],gesture=[0.,0.])]
  commands += [dict(op=13),dict(op=14),dict(op=11)];add('actual late failure '+missing,commands)
 for override in(False,True):
  commands=setup()+[dict(op=10)]
  for request in(8,9,10,11,6,7,0,99):commands += [dict(op=35,request=request,override=override),dict(op=14)]
  commands += [dict(op=36),dict(op=11),dict(op=14)];add('full requested/effective controller transition '+str(override),commands)
 # The continuously asserted response flag in the old pulse histories resets
 # response_frames every six updates. Clear that real upstream publication
 # after one trigger so the unchanged counter can reach eight and then clear
 # its one-tick completion. No retained state or completed result is supplied.
 commands=setup(response=0x100)+[dict(op=10)]+[dict(op=13)]*6
 commands += [packet(response=0,timer=6/60)]+[dict(op=13)]*8
 commands += [dict(op=14),dict(op=13),dict(op=14)]
 add('one actual response pulse completes after upstream release',commands,[])
 # The original query gates use XYZ only, while the host line adapter validates
 # all four lanes. Keep finite XYZ motion and make only the supplied position W
 # nonfinite, so the actual line callback rejects after consuming completion.
 commands=setup(velocity=(0.,-2.,0.,0.),position=(0.,.37,0.,0.))+[dict(op=10)]+tick()
 commands += [packet(velocity=(0.,-2.,0.,0.),position=(0.,.37,0.,float('inf')),timer=1/60)]+tick()
 add('actual nonfinite fourth position lane reaches line after consuming completion',commands)
 w=Stream();w.word(len(cases))
 for case in cases:
  write_world(w,case['world']);w.word(len(case['commands']))
  for cmd in case['commands']:
   op=cmd['op'];w.word(op)
   if op==0:
    for name,key in(('PlayerInputState','player'),('PhysicalPlayerInput','physical'),('ProcessedPhysicsInput','processed')):protocol.encode(w,name,cmd[key],defs)
   elif op==1:
    for v in cmd['target']:
     for x in v:w.float(x)
    p=cmd['packet'];protocol.encode(w,'AnimationPacketFields',p['publication'],defs);protocol.encode(w,'ExternalPhysicsInput',p['external_physics_10512'],defs)
    for f,k in defs['AnimationInputPacket']:
     if not k.startswith('&'):protocol.encode(w,k,p[f],defs)
    w.word(cmd['pose']);w.word(len(cmd['attributes']))
    for a in cmd['attributes']:
     for x in a['name']+[a['kind'],a['status'],a['sequence'],a['begin'],a['end']]:w.word(x)
     for v in a['payload']:
      w.word(v is not None)
      if v is not None:w.word(v)
    for x in cmd['actions']:w.float(x)
    w.word(cmd['initial_teleported'])
   elif op==21:
    for f,k in schemas()['State']:protocol.encode(w,k,cmd['state'][f],{})
   elif op==22:
    w.word(cmd['pose'])
    for v in cmd['control']+cmd['gesture']:w.float(v)
   elif op==24:w.word(cmd['part']);w.word(cmd['value'])
   elif op==31:write_world(w,cmd['world'])
   elif op==35:w.word(cmd['request']);w.word(cmd['override'])
   elif op==37:
    w.word(cmd['part'])
    for v in cmd['velocity']:w.float(v)
   elif op==38:w.word(cmd['reason']);w.float(cmd['value'])
   elif op==39:
    for v in cmd['delta']:w.float(v)
 raw=bytes(w.data)
 # All prior worlds, commands and per-history framing remain byte-for-byte
 # identical. The sole old-prefix change is the outer history count word.
 preserved=struct.pack('<I',OLD_HISTORIES)+raw[4:OLD_INPUT_BYTES]
 assert len(cases)==OLD_HISTORIES+2 and hashlib.sha256(preserved).hexdigest()==OLD_INPUT_SHA256
 assert hashlib.sha256(struct.pack('<I',44)+raw[4:2644960]).hexdigest()=='bfd8cc6e3cc2141145b412bc32ae08d84bb4e98b7c3c990250a3458af79f72f8'
 return raw,cases

class Reader(grind.Reader):
 def state(self):
  assert self.word()==len(BLOCKS);v={};self.sections={}
  for name in BLOCKS:n=self.word();at=self.at;v[name]=self.take(n);self.sections[name]=[at,self.at]
  return v

def decode(raw,cases):
 r=Reader(raw);assert r.word()==len(cases);frames=[]
 for c in cases:
  c['first_word']=r.at;assert r.word()==len(c['commands']);previous=r.state();rows=[]
  for cmd in c['commands']:
   at=r.at;assert r.word()==cmd['op'];error=r.status();extra=r.take(r.word());s=r.state();rows.append(dict(op=cmd['op'],error=error,extra=extra,state=s,previous=previous,sections=r.sections.copy(),first_word=at,last_word=r.at));previous=s
  c['last_word']=r.at;frames.append(rows)
 assert r.at==len(r.words);return frames

def owner(words):
 raw=struct.pack('<'+'I'*len(words),*words);r=protocol.Reader(raw);s={f:r.value(k,{})for f,k in schemas()['State']};a=[r.word()for _ in range(15)];b=[r.word()for _ in range(16)];query=[r.word()for _ in range(32)];has_pending=r.word();pending=[r.word()for _ in range(46)]if has_pending else[];assert r.at==len(raw);return s,a,b,query,pending

def shared(words):
 r=reset.Reader(struct.pack('<'+'I'*len(words),*words));return r.state()

def coverage(frames,cases):
 counts=Counter();errors=Counter();profiles=set();phases=set();controllers=set();real_material=Counter();pending=0;hits=0;misses=0;below=0;retained=0;finished=0;countdown=set();partial=0;enter=0;exit=0;normal=0;writes=0;resets=0
 response_progress=[];response_outputs=[]
 for rows,case in zip(frames,cases):
  for row,cmd in zip(rows,case['commands']):
   counts[OPS[cmd['op']]]+=1;errors.update([row['error']]if row['error']else[]);s,a,b,q,p=owner(row['state']['wipeout']);old=owner(row['previous']['wipeout']);same=shared(row['state']['shared']);before=shared(row['previous']['shared'])
   profiles.add(s['profile']);phases.add(a[13]);controllers.add(same['controller_dispatcher'][0]);pending+=bool(p);hits+=struct.unpack('<f',struct.pack('<I',q[12]))[0]>=0;misses+=struct.unpack('<f',struct.pack('<I',q[12]))[0]<0;below+=s['below_surface'];retained+=s['retained_velocity_active'];finished+=s['response_finished'];countdown.add(s['teleport_countdown'])
   if cmd['op']==6:
    # Feedback layout is decoded from the independent accepted observer, never
    # from a presumed contact count or the fixture's requested material tag.
    flag_values=feedback_flags(same['collision']);real_material.update(name for name in('material_10','material_11','material_12')if flag_values[name]);writes+=same['shared']!=before['shared']
   if cmd['op']==13:
    partial+=bool(row['error'])and(row['state']['wipeout']!=row['previous']['wipeout']or same['shared']!=before['shared'])
   if cmd['op']==10 and not row['error']:
    assert s['time']==0 and s['predicted_time']==0x7f7fffff and s['airborne_frames']==15;enter+=1
   if cmd['op']==11:
    assert s['prevent_manual']==0;assert same['collision']==before['collision'];exit+=1
   if cmd['op']==36:normal+=same['collision']!=before['collision']
   if cmd['op']==10 and b[-1]:resets+=1
   if case['index']==OLD_HISTORIES:
    assert not row['error'],row['error']
    assert cmd['op'] not in(21,24)
    if cmd['op']==13:response_progress.append((s['response_frames'],s['response_finished']))
    if cmd['op']==14:
     output=protocol.Reader(struct.pack('<'+'I'*len(row['extra']),*row['extra']))
     values={f:output.value(k,{})for f,k in schemas()['Output']}
     assert output.at==len(output.data)
     assert values['response_change_588']==(s['response_change']if s['response_finished']else None)
     response_outputs.append(values['response_change_588'])
 assert set(range(5))<=profiles,profiles
 assert {0,1,2,3,4}<=phases,phases
 assert real_material['material_10']>0 and real_material['material_11']>0 and real_material['material_12']>0,real_material
 assert {0,7,8,9,10}<=controllers,controllers
 assert pending>0 and hits>0 and misses>0 and below>0 and retained>0 and finished>0,(pending,hits,misses,below,retained,finished)
 assert {0,1,0xffffffff}<=countdown,countdown
 assert errors['Wipeout board force requires the current BoardToolkit']>0 and errors['IK original joint is absent from the current pose']>0,errors
 assert errors['Non-finite trajectory collision request or invalid radius']>0,errors
 assert partial>0 and enter>0 and exit>0 and normal>0 and writes>0 and resets>0,(partial,enter,exit,normal,writes,resets)
 assert [v[0]for v in response_progress]==[0xffffffff]*5+[0]+list(range(1,8))+[0xffffffff]*2,response_progress
 assert [v[1]for v in response_progress]==[0]*13+[1,0],response_progress
 assert len(response_outputs)==2 and response_outputs[0]is not None and response_outputs[1]is None,response_outputs
 return dict(operations=dict(counts),errors=dict(errors),profiles=sorted(profiles),material10_phases=sorted(phases),effective_controllers=sorted(controllers),real_solved_material_frames=dict(real_material),pending_predictions=pending,real_query_hits=hits,real_query_misses=misses,below_surface_frames=below,retained_velocity_frames=retained,response_finished_frames=finished,actual_response_counter_progress=response_progress,response_completion_outputs=response_outputs,preserved_histories=OLD_HISTORIES,preserved_input_sha256=OLD_INPUT_SHA256,teleport_countdowns=sorted(countdown),partial_failure_writes=partial,successful_enters=enter,exits=exit,actual_restore_normal_writes=normal,solved_body_writes=writes,material11_active_preserved_on_enter=resets)

def feedback_flags(collision):
 # The independent accepted collision observer ends with collision_flags. Its
 # order is read from that exact observer rather than a simulation object layout.
 observer=reset.block((PLUGIN/'Tests/Reference/skeleton_collision_probe.rs').read_text(),'fn collision_flags(')
 names=re.findall(r'\bf\.(\w+)',observer);assert len(names)==15 and len(set(names))==15
 return dict(zip(names,collision[-len(names):]))

def settings_queries():
 def group(c,n,k='float',key='default'):return[(c,key,x,k)for x in n]
 # Profiles are eagerly evaluated first but propagated after all three owners.
 r=group('physics_skeleton_joints',['SwingRagdollScalar','TwistRagdollScalar'])
 raw=reset.source(HOST+'wipeout_states/ragdoll/settings.rs');names=re.search(r'let names = \[(.*?)\];',raw,re.S).group(1);r+=group('physics_skeleton_joints',re.findall(r'"([^"]+)"',names),'words5')
 r+=group('physics_wipeout',['DoInverseMass','DoInverseInertia'],'bool')+group('physics_wipeout',['LinearDrag','AngularDrag'])+group('physics_skeleton',['FrictionRagdoll','RestitutionRagdoll','FrictionRagdollHead','RestitutionRagdollHead'])
 r+=group('physics_wipeout',['TeleportMinTimeForAutoReset','TeleportMinTimeAfterSettlingForAutoReset','TeleportMaxTime','TeleportAutoResetFadeOutTime','WipeoutOverSpeed','WipeoutOverMinTime','TimeToRemoveHook','TimeToRemoveDrives','DynamicDriveWeightVelControlled','DynamicDriveWeightVelCollision','SkateboardRestitution','SkateboardFriction'])+group('physicsdeck',['DeckAngularDrag'])+group('physics_wipeout',['LivingWorldPushForce'])
 for c,p in(('physicswheels','Wheel'),('physicstrucks','Truck'),('physicsdeck','Deck')):r+=group(c,[p+'StaticFriction',p+'DynamicFriction',p+'Restitution'])
 return r

def profile_queries(key):
 r=[('physics_wipeout_control',key,n,'words'+str(size))for n,size in(('SpinVsTime',20),('RollOnGroundAxis',4),('HorizAlignAxis',4),('AlignAxisEuler',4))]
 n=[('Hash_1BC908CDB3520A8E','float'),('TorqueVelScalar','float'),('TorqueDistScalar','float'),('SpinInertia','float'),('RollOnGround','bool'),('RollingOnGroundTorqueVelScalar','float'),('Hash_40B2B3C1A87A4D76','float'),('Hash_9047531918285FC3','float'),('Hash_6009FD75F9EDC436','bool'),('DriftMaxSpeed','float'),('DriftFactorZ','float'),('DriftFactorX','float'),('AlignWithVel','bool'),('Hash_9626703A9939FE36','bool'),('AlignOnGroundTorqueVelScalar','float'),('Hash_B65276A8CC7FB760','float'),('Hash_7E6B3A99C0A33ABC','float')]
 return r+[('physics_wipeout_control',key,name,kind)for name,kind in n]

def check_settings(output,path,physics_simulation,identity,assets,simulation,reference):
 original=json.loads(path.read_text());pbank=json.loads((assets/'private/stock/physics-skeletons.json').read_text());bank=next(s for s in pbank['skeletons']if s['name'].casefold()=='phys_tpose');bones=bank['bones'];queries=settings_queries()
 queries += [('physics_skeleton_drives','default','PART_'+b['name'],'words9')for b in bones[1:24]]
 queries += [('physics_skeleton_drives','default',n,'float')for n in('root_drive_start_scalar','root_drive_scalar','root_drive_controlled_scalar','root_drive_end_scalar')]+[('animation','default','DriveStrengthLocal','float'),('animation','default','DriveStrengthRootLocal','float')]+[('physics_animation','default',n,'float')for n in('HookSoftDsp','HookSoftStr','HookSoftDmp')]
 queries += [q for key in('free_fall','cannon_ball','judo_kick','swan_dive','torpedo')for q in profile_queries(key)]
 independent=copy.deepcopy(original)
 for q in queries:
  chain,name=stock.resolve(original,q);record=stock.record(independent,q[0],q[1]);record['fields'][name]=copy.deepcopy(chain[-1]['fields'][name])
 fixtures=[original];labels=['stock']
 for at,q in enumerate(queries):
  v=copy.deepcopy(independent)
  for later in queries[at:]:stock.mutate(v,later,dict(type='EA::Reflection::Int32',data='00000000')if later[3]in('float','bool')else dict(type='EA::Reflection::Float',data='00000000'))
  fixtures.append(v);labels.append('first-failed '+str(q))
 output.mkdir(parents=True,exist_ok=True)
 folder=stock.prepare_fixtures(output,fixtures,path);errors=Counter();records=[]
 for n,label in enumerate(labels):
  expected=subprocess.check_output([str(reference),str(assets),str(folder/str(n)),'--settings-only']);actual=subprocess.check_output([str(simulation),str(folder/str(n)/'settings.simulation'),str(physics_simulation),identity,'--settings-only'])
  (output/f'{n}-reference.bin').write_bytes(expected);(output/f'{n}-simulation.bin').write_bytes(actual)
  assert expected==actual,(n,label,expected.hex(),actual.hex());r=Reader(expected);error=r.status();values=r.take(len(r.words)-r.at);assert bool(error)==(n!=0),(label,error)
  if n:
   c,k,name,kind=queries[n-1];wanted='Expected '+('boolean'if kind=='bool'else'float')+' at '+c+'/'+k+'/'+name if kind in('float','bool')else 'Expected '+kind[5:]+' big-endian words, found 8 bytes of hex';assert error==wanted,(label,wanted,error)
  errors.update([error]if error else[]);records.append(dict(fixture=n,label=label,error=error,values=values))
 return dict(fixtures=len(records),first_failed_reads=len(queries),errors=dict(errors),records=records)

def preflight(raw,cases):
 defs,_=protocol.declarations();r=protocol.Reader(raw);assert r.word()==len(cases)
 def take(n):
  for _ in range(n):r.word()
 def world_():take(r.word()*19)
 for c in cases:
  world_();assert r.word()==len(c['commands'])
  for cmd in c['commands']:
   op=r.word();assert op==cmd['op']
   if op==0:
    for n in('PlayerInputState','PhysicalPlayerInput','ProcessedPhysicsInput'):r.value(n,defs)
   elif op==1:
    take(16);r.value('AnimationPacketFields',defs);r.value('ExternalPhysicsInput',defs)
    for f,k in defs['AnimationInputPacket']:
     if not k.startswith('&'):r.value(k,defs)
    assert r.word()==cmd['pose'];assert r.word()==len(cmd['attributes'])
    for _ in cmd['attributes']:
     take(10)
     for _ in range(6):
      if r.word():r.word()
    take(19)
   elif op==21:
    for f,k in schemas()['State']:r.value(k,{})
   elif op==22:take(5)
   elif op in(24,35,38):take(2)
   elif op==31:world_()
   elif op==37:take(4)
   elif op==39:take(3)
 assert r.at==len(raw),(r.at,len(raw))
 for u in UNITS:assert(CODE/(u+'.cpp')).is_file(),u
 assert len(schemas()['State'])==59 and len(schemas()['Output'])==24

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in('assets','samples','output','target-dir'):p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 for n in('result.json','first-divergence.json'):(out/n).unlink(missing_ok=True)
 raw,cases=corpus();preflight(raw,cases);(out/'input.bin').write_bytes(raw);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
 if a.preflight:
  snap,simulation=simulation_plan(out);original,observed,crate,cargo,reference=reference_plan(out/'reference')
  for s in(snap/'wipeout_physical_runtime_probe.cpp',crate/'src/migration_probe.rs',crate/'src/physics/input_phase.rs'):assert 'GENERATED_'not in s.read_text(),s
  for rel,sha in reference['original_source_sha256'].items():assert digest(original/rel)==sha;v=(original/rel).read_bytes();assert(observed/rel).read_bytes()[:len(v)]==v
  (out/'simulation-preflight.json').write_text(json.dumps(simulation,indent=2)+'\n');(out/'reference-preflight.json').write_text(json.dumps(reference,indent=2)+'\n');print(json.dumps(dict(histories=len(cases),callbacks=sum(len(c['commands'])for c in cases),input_bytes=len(raw),units=len(UNITS)),indent=2));return
 fixtures=out/'fixtures';fixtures.mkdir(exist_ok=True);assets=a.assets.resolve();stockpath=assets/'private/stock';(fixtures/'settings.simulation').write_bytes(reset.foot.converter.encode_settings(stockpath/'skater-collections.json'));(fixtures/'physics.simulation').write_bytes(reset.foot.converter.encode_physics_skeletons(stockpath/'physics-skeletons.json'))
 for kind in('action','motion'):(fixtures/f'actor.{kind}.reference').write_bytes(original_graph(element('state','idle')))
 identity=json.loads((stockpath/'physics-skeletons.json').read_text())['source_sha256'];reference=build_reference(out/'reference',a.target_dir);simulation=build_simulation(out)
 expected=subprocess.check_output([str(reference),str(assets),str(fixtures)],input=raw);actual=subprocess.check_output([str(simulation),str(fixtures/'settings.simulation'),str(fixtures/'physics.simulation'),str(a.samples.resolve()/'simulation/rig.skate'),identity,str(assets)],input=raw)
 (out/'reference.bin').write_bytes(expected);(out/'simulation.bin').write_bytes(actual);frames=decode(expected,cases)
 if expected!=actual:
  at=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));word=at//4;case=next((c for c in cases if c['first_word']<=word<c['last_word']),None);row=next((r for rows in frames for r in rows if r['first_word']<=word<r['last_word']),None);section=next(((n,word-a)for n,(a,b)in(row['sections'].items()if row else[])if a<=word<b),None);failure=dict(byte=at,reference_bytes=len(expected),simulation_bytes=len(actual),case=case['index']if case else None,operation=row['op']if row else'initial',section=section,reference_hex=expected[max(0,at-16):at+32].hex(),simulation_hex=actual[max(0,at-16):at+32].hex());(out/'first-divergence.json').write_text(json.dumps(failure,indent=2)+'\n');raise AssertionError(failure)
 verified=coverage(frames,cases);settings=check_settings(out/'settings',stockpath/'skater-collections.json',fixtures/'physics.simulation',identity,assets,simulation,reference)
 result=dict(passed=True,reference_revision=REFERENCE_REVISION,histories=len(cases),callbacks=sum(len(c['commands'])for c in cases),bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),coverage=verified,settings=settings,scope='Complete original active physical Wipeout300: State300/profile/material/prediction/ragdoll owners, real shared physical/pose/IK and original solve/contact/query kernels.',boundaries='Completed canonical input/animation attributes and explicit prior retained State300 are caller publications. World triangles/tags/metadata are authored source transport; actual contact feedback and trajectory results are never seeded. Full global scheduling, conditional publication of the returned Output into the coordinator state flags and source logging remain separate.')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
