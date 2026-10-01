#!/usr/bin/env python3
"""Whole unchanged active Biped Ground/Air owners over live canonical producers.

Only root builds or executes. --preflight stages source and audits the transport.
Processed/animation attribute packets are upstream inputs; actual pose, body,
feet/hips tests, queries, selection, correction, shared solve and feedback are not.
"""
import argparse
from collections import OrderedDict, Counter
from functools import lru_cache
import copy, hashlib, json, re, shutil, struct, subprocess
from pathlib import Path
import check_air_phase_runtime_parity as phase
import check_biped_ground_state_parity as ground_state
import check_biped_feet_parity as feet
import check_offboard_controller_parity as controller
import check_offboard_contact_parity as contact
import check_offboard_ground_geometry_parity as geometry
import check_offboard_air_selector_parity as selector
import check_offboard_grab_parity as grab
import check_landing_deck_parity as landing
import check_biped_skeleton_parity as skeleton
import player_input_protocol as wire
import check_player_state_runtime_parity as state_runtime
from check_animation_playback_parity import Stream
from check_skeleton_input_runtime_parity import source
from session_parity import REFERENCE_REVISION, digest
PLUGIN, CODE = phase.PLUGIN, phase.CODE
CORE='crates/skate-core/src/player/offboard/'
HOST='crates/skate-host/src/physics/'
FAMILY=('BipedGroundLifecycle','BipedAirState','BipedAirHeight','BipedAirOrientation','BipedAirCollision','BipedAirPost','BipedRuntimeOwners','BipedGroundRuntime','BipedGroundEntry','BipedGroundUpdate','BipedGroundGrab','BipedGroundPublication','BipedAirRuntime','BipedAirInput','BipedAirUpdate','BipedAirRuntimePost')
UNITS=tuple(dict.fromkeys((*phase.UNITS,*state_runtime.UNITS,*controller.UNITS,*contact.UNITS,*geometry.UNITS,*selector.UNITS,*grab.UNITS,*landing.UNITS,*feet.UNITS,*ground_state.UNITS,*skeleton.UNITS,*FAMILY,'SkeletonLineQueries','CameraTracking','CameraWorld')))
OPS=('packet','pose','toolkit','early_selector','begin_contact','ground_enter','ground_update','ground_submit','ground_post','ground_fill','ground_exit','air_enter','air_update','air_post','air_fill','air_exit','wheel_queries','solve_feedback','skeleton_lines','execute_grab','sync_grab','publish_grab','world','selector_reset','ground_reset','collision_override','packet_flags','capture_board','contact_refresh','feet_reset','landing_reset')
SECTIONS=('ground','air','contact','selector','landing','grab','feet','publication','processed','lifecycle','forces','feedback','frame','last_toolkit','line_tests','possession')

def block(path,marker):
 # Several legacy wire helpers place two complete functions on one line.
 # Extract the exact balanced function bytes without requiring a newline.
 text=(PLUGIN/'Tests'/path).read_text();start=text.index(marker);opening=text.index('{',start);depth=0
 for n in range(opening,len(text)):
  if text[n]=='{':depth+=1
  elif text[n]=='}':
   depth-=1
   if depth==0:return text[start:n+1]
 raise AssertionError((path,marker))

def fields(path,name,aliases=None):
 text=source(path);m=re.search(r'pub struct '+name+r'\s*\{',text);assert m,(path,name)
 body=text[m.end():text.index('\n}',m.end())]
 result=[]
 for f,k in re.findall(r'^\s*pub (\w+): ([^,\n]+),',body,re.M):
  k=re.sub(r'\s+','',k);k=(aliases or{}).get(k,k);k=re.sub(r'\bVector\b','[f32;4]',k);k=re.sub(r'\bFrame\b','[[f32;4];4]',k);result.append((f,k))
 assert result,(path,name);return result

def declarations():
 defs=controller.schema();aliases={n:'skate_core::player::offboard::'+row[2] for n,row in controller.STRUCTS.items()};aliases['BipedGroundResult']='skate_core::player::offboard::controller::GroundResult'
 for n,f in ground_state.definitions().items():
  if n not in defs:defs[n]=f;aliases[n]='skate_core::player::offboard::'+ground_state.TYPES[n][2]
 defs['BipedAirTrajectoryResult']=fields(CORE+'biped_air/result.rs','TrajectoryResult');aliases['BipedAirTrajectoryResult']='skate_core::player::offboard::biped_air::recovered::TrajectoryResult'
 defs['BipedAirState']=fields(CORE+'biped_air/recovered.rs','State',{'TrajectoryResult':'BipedAirTrajectoryResult'});aliases['BipedAirState']='skate_core::player::offboard::biped_air::recovered::State'
 for n in('BoardManagerHand','BoardPossessionManager'):defs[n]=feet.definitions()[n];aliases[n]='skate_core::player::offboard::board_possession::manager::'+('Hand' if n=='BoardManagerHand'else'State')
 all_defs,_=wire.declarations()
 def retain(n):
  if n in defs:return
  for _,k in all_defs[n]:
   while wire.array(k)or wire.option(k):k=wire.array(k)[0]if wire.array(k)else wire.option(k)
   if k in all_defs:retain(k)
  defs[n]=all_defs[n];kind=wire.rust_kind(n);aliases[n]='skate_core::player::input_phase::'+n if kind==n else kind
 for n in('PhysicalPlayerInput','PlayerInputState'):retain(n)
 return defs,aliases

def protocol():
 defs,aliases=declarations();cpp=['using BipedContactPrefix=OffboardContactPrefix;'];rust=[]
 # Air's shared generated transport already declares these output children.
 existing=OrderedDict();all_defs,_=wire.declarations()
 def retained(n):
  if n in existing:return
  for _,k in all_defs[n]:
   while wire.array(k)or wire.option(k):k=wire.array(k)[0]if wire.array(k)else wire.option(k)
   if k in all_defs:retained(k)
  existing[n]=all_defs[n]
 for n in('ProcessedPhysicsInput','AirOutputFields'):retained(n)
 defs=OrderedDict((n,f)for n,f in defs.items()if n not in existing)
 for n in defs:cpp.append(f'void Observe(BipedOutput&,const {n}&);');rust.append(f'type {n}={aliases[n]};')
 for n,fs in defs.items():
  cpp.append(f'void Observe(BipedOutput& o,const {n}& s){{'+''.join(wire.observe_expr(k,'s.'+f,'cpp')for f,k in fs)+'}')
  rust.append(f'fn observe_{n}(o:&mut Output,s:&{n}){{'+''.join(wire.observe_expr(k,'s.'+f+('.0'if n=='BipedControllerState'and f=='thresholds'else''),'rust')for f,k in fs)+'}')
 cp,rp=phase.helpers();fc,fr=phase.feedback_helpers();cp+='\n'+fc.replace('AirOutput','Output');rp+='\n'+fr
 # Source protocol observations only. The consumed Processed packet reader
 # remains the same generator used by the actual Air proof.
 cp=re.sub(r'\bInput\b','BipedInput',cp);cp=re.sub(r'\bOutput\b','BipedOutput',cp)
 return '\n'.join(cpp)+'\n'+cp,'\n'.join(rust)+'\n'+rp

def owner_helpers():
 cpp=[];rust=[];appends={}
 def functions(file,markers,lang):
  text='\n'.join(block(('Native/'if lang=='cpp'else'Reference/')+file,m)for m in markers)
  if lang=='cpp':return re.sub(r'\bWriter\b','BipedOutput',re.sub(r'\bReader\b','BipedInput',text))
  return text.replace('Writer','Output').replace('Reader','Input').replace('.scalar(','.float(').replace('.words','.0')
 cm=('void V(','void M(','void LineOut(','void DescriptorOut(','void DescriptorsOut(','void LayoutOut(','void RequestOut(','void BatchOut(','void QueryOut(','void HitOut(','void LinesOut(','void ResultsOut(','void PrefixOut(','void OwnerOut(')
 rm=('fn v(','fn matrix_out(','fn line_out(','fn descriptors_out(','fn layout_out(','fn request_out(','fn batch_out(','fn query_out(','fn hit_out(','fn results_out(','fn prefix_out(')
 cpp.append('namespace biped_contact{'+functions('offboard_contact_probe.cpp',cm,'cpp')+'}')
 rr=functions('offboard_contact_probe.rs',rm,'rust').replace('fn ','pub(crate)fn ')
 rust.append('mod biped_contact{use crate::Output;use skate_core::air::trajectory::{QueryRequest,QueryResult};use skate_core::player::offboard::contact_toolkit as toolkit;\n'+rr+'}')
 obs=block('Reference/offboard_contact_probe.rs','pub fn migration_observe(').replace('crate::Writer','Vec<u32>')
 # Core cannot depend on the host observer. This append snapshots the complete
 # retained owner with typed original records; encoding stays in the host.
 appends['crates/skate-core/src/player/offboard/contact_toolkit.rs']='''
impl Owner{pub fn migration_biped_parts(&self)->(&ProbeLayout,&Option<(Batch,QueryResults)>,u32,ContactPrefix,[Vector;3],[u32;3],[f32;3],[u32;5]){let c=self.candidate;let text=format!("{:?}",self.history);let words:Vec<u32>=text.split(|c:char|!c.is_ascii_digit()).filter(|s|!s.is_empty()).map(|s|s.parse().unwrap()).collect();assert_eq!(words.len(),5);(&self.layout,&self.pending,self.readiness,self.prefix,[c.position,c.normal,c.direction],[c.flags,c.segment as u32,c.kind],[c.low,c.high,c.order],words.try_into().unwrap())}}
'''
 rust.append('''fn biped_contact_out(o:&mut Output,s:&skate_core::player::offboard::contact_toolkit::Owner){let(l,p,r,f,v,w,x,h)=s.migration_biped_parts();biped_contact::layout_out(o,l);o.word(p.is_some()as u32);if let Some((b,r))=p{biped_contact::batch_out(o,b);biped_contact::results_out(o,r)}o.word(r);biped_contact::prefix_out(o,f);for v in v{o.floats(v)}o.word(w[0]);for x in x{o.float(x)}o.word(w[1]);o.word(w[2]);o.words(h);}
''')
 cm=('void FrameOut(','void ContextOut(','void LineOut(','void PacketOut(','void HitOut(','void HitsOut(','void AdjustmentOut(','void OwnerOut(')
 rm=('fn frame_out(','fn context_out(','fn packet_out(','fn hits_out(','fn adjustment_out(')
 cpp.append('namespace biped_geometry{'+functions('offboard_ground_geometry_probe.cpp',cm,'cpp')+'}')
 rust.append('mod biped_geometry{use crate::Output;use skate_core::player::offboard::ground_query as q;'+functions('offboard_ground_geometry_probe.rs',rm,'rust').replace('fn ','pub(crate)fn ')+'}')
 appends[HOST+'offboard/ground_geometry.rs']='''
pub(crate)fn migration_biped_observe(o:&mut crate::Output,s:&State){o.float(s.collision_offset);o.word(s.pending.is_some()as u32);if let Some((p,h))=&s.pending{crate::biped_geometry::packet_out(o,p);crate::biped_geometry::hits_out(o,h)}}
'''
 cm=('void VO(','void MO(','void TO(','void QO(','void RequestOut(','void PredictionOut(','void PacketOut(','void CandidateOut(','void SamplingOut(','void ResultOut(','void OwnerOut(','void SettingsOut(')
 rm=('fn vo(','fn mo(','fn to(','fn qo(','fn request_out(','fn prediction_out(','fn packet_out(','fn candidate_out(','fn sampling_out(','fn result_out(','fn owner_out(','fn settings_out(')
 cpp.append('namespace biped_selector{'+functions('offboard_air_selector_probe.cpp',cm,'cpp')+'}')
 rr=functions('offboard_air_selector_probe.rs',rm,'rust').replace('offboard::air_selector::','crate::physics::offboard::air_selector::').replace('fn ','pub(crate)fn ')
 rust.append('mod biped_selector{use crate::Output;use skate_core::{air::trajectory::{Trajectory,QueryRequest,QueryResult,Prediction},player::offboard::{air_launch,biped_air::recovered::{TrajectoryResult,sampling::SelectorState,selection::Candidate}}};'+rr+'}')
 appends[HOST+'offboard/air_selector.rs']='\n'+block('Reference/offboard_air_selector_probe.rs','pub fn migration_completions').replace('pub fn','pub(crate)fn')+'\n'
 # Shared Landing68 only; the State503 facade is deliberately not constructed.
 cm=('void VO(','void MO(','void TO(','void QO(')
 cpp.append('namespace biped_landing{'+functions('landing_deck_probe.cpp',cm,'cpp')+'''
void OwnerOut(BipedOutput& o,const LandingDeck& owner){const auto& m=owner.manager;TO(o,m.trajectory_32);TO(o,m.proposed_96);o.Float(m.elapsed_160);o.Word(m.trajectory_valid_164);for(const auto& v:{m.ik_offset_176,m.vector_192,m.moving_contact_208,m.vector_224})VO(o,v);for(auto f:{m.obstruction_height_240,m.time_to_land_244,m.proposed_time_248})o.Float(f);o.Word(m.completed_queries_252);for(auto b:{m.can_land_256,m.force_257,m.blocked_258,m.tested_259,m.hippy_hurdling_260,m.publish_moving_contact_261,m.pending_262})o.Word(b);o.Word(owner.Completion().has_value());if(owner.Completion())QO(o,*owner.Completion());o.Float(owner.settings.deck_min_uprightness);o.Float(owner.settings.approximate_com_height);}
}''')
 rm=('fn vo(','fn mo(','fn to(','fn qo(')
 rust.append('mod biped_landing{use crate::Output;use skate_core::air::trajectory::{Trajectory,QueryResult};'+functions('landing_deck_probe.rs',rm,'rust').replace('fn ','pub(crate)fn ')+'}')
 appends[HOST+'offboard/landing_deck.rs']='''
pub(crate)fn migration_biped_observe(o:&mut crate::Output,s:&Owner){let m=s.manager;crate::biped_landing::to(o,m.trajectory_32);crate::biped_landing::to(o,m.proposed_96);o.float(m.elapsed_160);o.word(m.trajectory_valid_164 as u32);for v in [m.ik_offset_176,m.vector_192,m.moving_contact_208,m.vector_224]{o.floats(v)}for f in [m.obstruction_height_240,m.time_to_land_244,m.proposed_time_248]{o.float(f)}o.word(m.completed_queries_252);for b in [m.can_land_256,m.force_257,m.blocked_258,m.tested_259,m.hippy_hurdling_260,m.publish_moving_contact_261,m.pending_262]{o.word(b as u32)}o.word(s.completion.is_some()as u32);if let Some(q)=s.completion{crate::biped_landing::qo(o,q)}o.float(s.settings.deck_min_uprightness);o.float(s.settings.approximate_com_height);}
'''
 cm=('void VO(','void MO(','void RecordOut(','void RecordsOut(','void RecordOption(','void QueryOut(','void LineOut(','void HitOut(','void ObjectOption(','void OwnerOut(','std::shared_ptr<const OffboardGrabGeometry> Geometry(','GrabObject Object(')
 rm=('fn vo(','fn mo(','fn record_out(','fn records_out(','fn record_option(','fn query_out(','fn line_out(','fn hit_out(','fn object_option(','fn v(','fn m(','fn descriptor(','fn geometry(','fn object(')
 cpp.append('namespace biped_grab{'+functions('offboard_grab_probe.cpp',('Vec4 V(','Mat4 M(','OffboardGrabDescriptor Descriptor('),'cpp')+functions('offboard_grab_probe.cpp',cm,'cpp')+'}')
 rr=functions('offboard_grab_probe.rs',rm,'rust').replace('fn ','pub(crate)fn ')
 rust.append('mod biped_grab{use crate::{Input,Output};use skate_core::player::offboard::grab_scene as native;'+rr+'}')
 obs=block('Reference/offboard_grab_probe.rs','pub fn migration_observe(').replace('crate::Writer','crate::Output').replace('crate::{query_out,records_out,record_option,line_out,hit_out,object_option,vo}','crate::biped_grab::{query_out,records_out,record_option,line_out,hit_out,object_option,vo}').replace('.words','.0')
 appends[HOST+'biped_ground/grab_runtime.rs']='\n'+obs.replace('pub fn','pub(crate)fn')+'\n'
 appends[HOST+'offboard/skeleton_ground/state.rs']='''
pub(super)fn migration_biped_observe(o:&mut crate::Output,s:&State){o.matrix(s.retained_board);o.floats(s.ground_normal_smoothing);for g in [s.tilt_vs_rotation,s.tilt_vs_slope]{o.floats(g.x);o.floats(g.y)}}
'''
 appends[HOST+'offboard/skeleton_ground.rs']='\npub(crate)fn migration_biped_observe(o:&mut crate::Output,s:&State){state::migration_biped_observe(o,s)}\n'
 appends[HOST+'offboard/board_manager/runtime.rs']='''
pub(crate)fn migration_biped_live(o:&mut crate::Output,s:&LiveState){let v=&s.volumes;o.word(v.deck as u32);o.word(v.trucks as u32);o.word(v.wheels as u32);o.word(v.deck_children.len()as u32);for &b in &v.deck_children{o.word(b as u32)}o.floats(s.alignment.first_1008);o.floats(s.alignment.second_1024);o.float(s.alignment.factor_1040);o.word(s.alignment.flag_1044 as u32);o.word(s.alignment_active as u32);}
'''
 return '\n'.join(cpp),'\n'.join(rust),appends

def prepare(output):
 original,observed,snapshot,report=phase.prepare(output);crate=observed/'atelier-host'
 cpp,rust=protocol();ch,rh,appends=owner_helpers();extensions={**appends,HOST+'biped_ground.rs':(PLUGIN/'Tests/Reference/biped_runtime_ground_observer.rs').read_text(),HOST+'biped_air.rs':(PLUGIN/'Tests/Reference/biped_runtime_air_observer.rs').read_text(),HOST+'physics-unused':'', 'crates/skate-host/src/physics.rs':(PLUGIN/'Tests/Reference/biped_runtime_observer.rs').read_text()};extensions.pop(HOST+'physics-unused')
 for rel,extra in extensions.items():
  dest=crate/'src'/rel.removeprefix('crates/skate-host/src/')if rel.startswith('crates/skate-host/src/')else observed/rel
  dest.write_bytes(dest.read_bytes()+extra.encode());raw=(original/rel).read_bytes();assert dest.read_bytes()[:len(raw)]==raw,rel
  report.setdefault('biped_appended_observers',{})[rel]=dict(original_prefix_bytes=len(raw),original_prefix_sha256=digest(original/rel),append_sha256=hashlib.sha256(extra.encode()).hexdigest(),generated_sha256=digest(dest))
 worldcpp=(PLUGIN/'Tests/Native/world_geometry_probe.cpp').read_text().split('int main(')[0]
 worldrust=(PLUGIN/'Tests/Reference/world_geometry_probe.rs').read_text().split('fn main(')[0]
 worldcpp=worldcpp[worldcpp.index('namespace\n{'):];worldrust=worldrust.replace('use math::','use skate_core::math::').replace('use physics::','use skate_core::physics::')
 # This is the established full triangle/query-metadata wire, wrapped in a
 # namespace so its legacy Reader/Writer do not replace actual owner helpers.
 worldcpp=worldcpp.replace('namespace\n{','namespace biped_world\n{',1)
 # Read only world transport helpers; neither standalone world main is run.
 cpworld=worldcpp
 rpworld=worldrust
 # Native factory below uses an independent adapter around the wire Reader.
 cpworld += '\n'+(PLUGIN/'Tests/Native/biped_runtime_world.inc').read_text()
 rpworld=(PLUGIN/'Tests/Reference/biped_runtime_world.inc').read_text().replace('// GENERATED_WORLD',worldrust)
 rs=(PLUGIN/'Tests/Reference/biped_runtime_probe.rs').read_text().replace('// GENERATED_PROTOCOL',rust+'\n'+rh).replace('// GENERATED_WORLD',rpworld)
 # Keep phase's original wrapper consumers declared: they are unused by this
 # program but their complete source is still compiled with unchanged prefixes.
 pc,pr=phase.providers();rs=rs.replace('// GENERATED_PROVIDER',pr+'\n'+phase.extract(PLUGIN/'Tests/Reference/player_grind_input_probe.rs','fn fixture_world(kind:u32)'))
 (crate/'src/migration_probe.rs').write_text(rs)
 cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text().replace('name="air-phase-runtime-reference"','name="biped-runtime-reference"'))
 for u in UNITS:shutil.copy2(CODE/(u+'.cpp'),snapshot/(u+'.cpp'));report['native_source_sha256'][u+'.cpp']=digest(CODE/(u+'.cpp'))
 # phase.prepare snapshots every Native header already, including the new
 # Biped declarations; the immutable stock helper prefix remains unchanged.
 prefix,_=phase.foot.extraction(PLUGIN/'Tests/Native/footplant_probe.cpp','int main(')
 pc,_=phase.providers();pc=re.sub(r'\bInput\b','BipedInput',pc)
 body=(PLUGIN/'Tests/Native/biped_runtime_probe.cpp').read_text().replace('// GENERATED_PROTOCOL',cpp+'\n'+ch).replace('// GENERATED_WORLD',cpworld).replace('// GENERATED_PROVIDER',pc)
 (snapshot/'biped_runtime_probe.cpp').write_bytes(b'#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wunused-function"\n'+prefix+b'\n#pragma clang diagnostic pop\n'+body.encode())
 report.update(generated_native_probe_sha256=digest(snapshot/'biped_runtime_probe.cpp'),generated_reference_probe_sha256=digest(crate/'src/migration_probe.rs'),probe_sha256={p.name:digest(p)for p in OWNED_TESTS})
 # Final hashes cover all appended records and observers, without loosening
 # the frozen source hash checks performed by phase.prepare.
 for rel,row in report['staged_host_original_prefixes'].items():row['generated_sha256']=digest(crate/'src'/rel)
 (output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');return original,observed,snapshot,report

OWNED_TESTS=tuple(PLUGIN/'Tests'/p for p in('Native/biped_runtime_probe.cpp','Native/biped_runtime_world.inc','Reference/biped_runtime_probe.rs','Reference/biped_runtime_observer.rs','Reference/biped_runtime_ground_observer.rs','Reference/biped_runtime_air_observer.rs','Reference/biped_runtime_world.inc'))
OWNED_PRODUCTION=tuple(dict.fromkeys([CODE/(u+'.cpp')for u in FAMILY]+[CODE/(n+'.h')for n in('BipedGroundLifecycle','BipedAirState','BipedAirMath','BipedRuntimeOwners','BipedGroundRuntime','BipedAirRuntime')]))

def loader_fixtures(assets):
 """Actual Ground constructor followed by Air, including raw-word readers.

 The first 133 cases are byte-identical controller fixtures. Raw Skeleton
 settings intentionally accept reflection-type changes and non-finite bits;
 scalar readers reject them. Destination snapshots retain both prior owners
 if either fresh constructor fails, matching the explicit fixture transaction.
 """
 data=json.loads((assets/'private/stock/skater-collections.json').read_text());result=[('controller/'+label,d,success)for label,d,success in controller.loader_fixtures(assets)]
 raw=[('physics_reckoning','GroundNormalSmoothing',4),('physics_reckoning','TiltVsRotGround',16),('physics_reckoning','TiltVsSlopeGround',16)]
 scalar=[('physics_grinds','DeckCenterToTruck')]+[('physics_wipeout',n)for n in('Wipeout_OB_VehicleScalar','Wipeout_OB_VehicleContact','Wipeout_OB_SkeletonMaxDisp','Wipeout_OB_SkeletonMaxContactArms','Wipeout_OB_SkeletonMaxContact','Wipeout_OB_MinSpeed','Wipeout_OB_MaxSquash','Hash_472174920C68FBE3','Wipeout_AirMaxSquash','Wipeout_AirSkeletonMaxDisp','Wipeout_AirSkeletonMaxContact','Wipeout_AirSkeletonMaxContactArms','Wipeout_OB_MaxSquash','Wipeout_OB_Air_SkelMaxDisp','Wipeout_OB_Air_SkelMaxContact','Wipeout_OB_SkeletonMaxContactArms','Wipeout_OB_Air_MinSpeed')]
 identity=lru_cache(maxsize=None)(phase.converter.name_id)
 def resolve(d,c,n):
  key='default'
  for _ in range(len(d['collections'])+1):
   row=next(r for r in d['collections']if identity(r['class'])==identity(c)and identity(r['key'])==identity(key));actual=next((f for f in row['fields']if identity(f)==identity(n)),None)
   if actual is not None:return row['fields'][actual]
   key=row['parent'];assert key
  raise AssertionError('cycle')
 def missing(d,c,n):
  for r in d['collections']:
   if identity(r['class'])==identity(c):
    for f in list(r['fields']):
     if identity(f)==identity(n):del r['fields'][f]
 for c,n,size in raw:
  for failure in('missing','short','long','reflection-type-valid','nonfinite-valid','signed-zero-valid'):
   d=copy.deepcopy(data)
   if failure=='missing':missing(d,c,n)
   else:
    f=resolve(d,c,n);hex=re.sub(r'\s+','',f['data']);assert len(hex)==size*8
    if failure=='short':f['data']=hex[:-8]
    elif failure=='long':f['data']=hex+'DEADBEEF'
    elif failure=='reflection-type-valid':f['type']='EA::Reflection::Bool'
    else:f['data']=('7FC12345'if failure=='nonfinite-valid'else'80000000')+hex[8:]
   result.append((c+'/'+n+'/'+failure,d,failure.endswith('valid')))
 # Every exact read position receives its own failure, even the shared squash
 # field which appears in both Ground and Air constructors.
 for index,(c,n)in enumerate(scalar):
  for failure in('missing','type','empty','short','long','nonfinite','negative-valid'):
   d=copy.deepcopy(data)
   if failure=='missing':missing(d,c,n)
   else:
    f=resolve(d,c,n)
    if failure=='type':f['type']='EA::Reflection::Bool'
    else:f['data']={'empty':'','short':'DEAD','long':'DEADBEEFCAFEBABE','nonfinite':'7FC12345','negative-valid':'BE4CCCCD'}[failure]
   result.append((f'read-{index}/{c}/{n}/{failure}',d,failure.endswith('valid')))
 # Source constructor boundaries and consecutive fields preserve both errors.
 order=[('physics_biped','JumpHeight')]+[(c,n)for c,n,_ in raw]+scalar
 for index,((c,n),(d,m))in enumerate(zip(order,order[1:])):
  case=copy.deepcopy(data);missing(case,c,n);resolve(case,d,m)['data']='DEAD'
  result.append((f'compound-{index}/{c}/{n}/before/{d}/{m}',case,False))
 for category in('physics_biped','physics_state_offboard','physics_reckoning','physics_grinds','physics_wipeout'):
  d=copy.deepcopy(data);d['collections']=[r for r in d['collections']if identity(r['class'])!=identity(category)];result.append(('missing-collection/'+category,d,False))
 assert len({label for label,_,_ in result})==len(result)
 return result

def decode_loader(raw,success,label):
 r=Reader(raw);assert r.status()is None,label;prior=[r.take(r.word()),r.take(r.word())];error=r.status();current=[r.take(r.word()),r.take(r.word())]
 assert r.at==len(r.words),(label,r.at,len(r.words));assert (error is None)==success,(label,error,success)
 if not success:assert current==prior,(label,'failed fresh constructors changed retained owners')
 return dict(label=label,success=success,error=error,exact_words=len(r.words))

def corpus():
 defs,_=wire.declarations();worlds=[];programs=[]
 floor=contact.quad(-20,20,-20,20,0,0);ramp=contact.quad(-20,20,-20,20,.3,-.3)
 edges=[([-3,0,.45],[3,0,.45]),([-3,.08,.75],[3,.08,.75])]
 worlds=[contact.make_world([(floor,0,-1,0)],edges),contact.make_world([(ramp,0,-1,0)],edges),contact.make_world([(floor,0,-1,0)]),contact.make_world([],edges),contact.make_world([]),contact.make_world([(floor,0,-1,0)],edges,enabled=False)]
 def packet(n,k,state=500,previous=500,mode=1,variant=0):
  p=phase.zero('ProcessedPhysicsInput',defs)
  p.update(flags_2468=0x2000,flags_2472=(0,0x10000000,0)[(n+k)%3],flags_2476=4 if n%2 else 0,flags_2480=(0,0x8000,0x80)[(n+k)%3],flags_2484=(0,1,0x4000,0x80000000)[(n+k)%4],flags_2488=0,state_2508=state,category_2512=500,state_2504=previous,category_2516=500,state_variant_index_2528=mode,timestep_2604=1/60,gravity_2648=9.81,frames_since_teleport_2584=(0,19,20,21)[k%4],state_timer_2664=k/60,transition_2636=.317,scalar_2612=3.137,scalar_2652=3.137,scalar_2616=3.137,actor_query_2948=(0,2)[n%2],actor_query_2952=0xffffffff,secondary_ground_timer_2852=k/60)
  if variant==1:p['flags_2480']=0;p['flags_2484']=2|0x400;p['flags_2488']=0x80000
  p['vectors_464_480_496_512_528']=[phase.foot.fs(v)for v in([0,1,0,0],[0,0,0,0],[0,0,0,0],[0,0,1,0],[0,1,0,0])]
  p['vectors_544_560_592_608'][0]=phase.foot.fs([0,1,0,0]);p['prepared_jump_704']=phase.foot.fs([.137,4.137,3.137,0]);p['vectors_880_896_912_928_944'][2]=phase.foot.fs([.137,3.137,1.137,0])
  p['grind']['point_1120']=phase.foot.fs([0,0,0,0]);p['grind']['direction_1136']=phase.foot.fs([0,0,1,0])
  s=Stream();s.word(0);wire.encode(s,'ProcessedPhysicsInput',p,defs)
  floats=[.003,0,.137,-.0, .01,0,.317,-.0, .317,1,1, (.125,.5,.875)[k%3],0, (.137,.731,1)[n%3],(-.317,0,.317)[k%3],(-.731,0,.731)[n%3],1,(-.317,0,.317)[n%3],(0,.137)[k%2],(0,.317)[n%2],0]
  for f in floats:s.float(f)
  return list(struct.unpack('<'+'I'*(len(s.data)//4),s.data))
 def history(n,error=False):
  commands=[packet(n,0,previous=(100,500,501,502)[n%4]),[1,n%4],[2,1],[18],[27],[16],[5],[9]]
  for k in range(6):
   # Earlier selector completion and contact refresh precede current input.
   commands += [[3],[4],packet(n,k),[1,(n+k)%4],[2,1],[19],[20],[6],[7],[18],[16],[17],[8],[9],[21]]
   if k==2:commands += [[30],[28],[24],[5]]
  commands += [[10],packet(n,6,state=501),[11]]
  for k in range(8):
   commands += [[3],[4],packet(n,6+k,state=501,previous=500,variant=k%2),[1,(n+k)%4],[2,1],[19],[20],[12],[18],[16],[17],[13],[14],[21]]
   if k==3:commands += [[30]]
  commands += [[15],[23],[29],packet(n,0,state=502,previous=501),[5],[6],[7],[18],[16],[17],[8],[9],[10]]
  if error:
   commands += [[2,0],[5],[6],[11],[12],[13],[2,1],[1,4],[6],[12],[1,n%4],[25,1],[5],[11],[12],[25,0]]
   commands += [packet(n,4,state=501,mode=9),[12],[13],[14],packet(n,4,state=501),[22]+contact.encode_world(worlds[-1]),[6],[7],[12],[19],[20],[22]+contact.encode_world(worlds[0]),[3],[6],[7],[12],[26,0xffffffff,0xffffffff],[12],[26,0,0]]
  return commands
 for n in range(24):
  w=worlds[n%5];objects=[grab.obj(1,100,count=2),grab.obj(2,200,kind=1,curve=True,count=1)]if n%3 else[]
  for obj in objects:
   obj['frame']=grab.frame(z=.4);obj['splines'][0]['geometry']['points']=[[-1,1,0,0],[0,1,.1,0],[1,1,0,0]]
  programs.append(dict(index=len(programs),world=w,registry=grab.registry(objects),commands=history(n),label='actual canonical Ground/Air/feet/grab/landing/possession and deferred contact geometry'))
 for n in range(6):programs.append(dict(index=len(programs),world=worlds[n],registry=grab.registry([grab.obj()]),commands=history(n,True),label='actual ordered partial failures and retained completions across world replacement'))
 stream=Stream();stream.word(len(programs));ranges=[]
 for p in programs:
  start=len(stream.data)
  for w in contact.encode_world(p['world'])+grab.encode_registry(p['registry']):stream.word(w)
  stream.word(len(p['commands']))
  for c in p['commands']:
   for w in c:stream.word(w)
  ranges.append([start,len(stream.data)])
 return bytes(stream.data),programs,ranges

class Reader(phase.Reader):
 def biped(self):
  assert self.word()==len(SECTIONS);values={};spans={}
  for name in SECTIONS:
   n=self.word();at=self.at;values[name]=self.take(n);spans[name]=[at,self.at]
  return values,spans

def decode(raw,cases):
 r=Reader(raw);assert r.word()==len(cases);frames=[]
 def snapshot():
  records,spans=r.biped();f=r.foot();spans.update(r.foot_spans);s=r.snapshot();spans.update(r.spans);return dict(owner=records,foot=f,shared=s,spans=spans)
 for case in cases:
  case['first_output_word']=r.at;assert r.word()==len(case['commands']);prior=snapshot();rows=[]
  for command in case['commands']:
   start=r.at;assert r.word()==command[0];publication=[]
   if command[0]==21:publication=r.take(r.word())
   error=r.status();current=snapshot();rows.append(dict(operation=command[0],error=error,first_word=start,last_word=r.at,grab_publication=publication,prior=prior,**current));prior=current
  case['last_output_word']=r.at;frames.append(rows)
 assert r.at==len(r.words),(r.at,len(r.words));return frames

def coverage(frames,cases):
 counts=Counter();errors=Counter();success=Counter();changed=Counter();partial=0;valid_samples=0;pending_contact=0;feet_changes=0;line_hits=0
 for case,rows in zip(cases,frames):
  for command,row in zip(case['commands'],rows):
   op=command[0];counts[OPS[op]]+=1
   if row['error']:errors[row['error']]+=1
   else:success[OPS[op]]+=1
   old=row['prior'];now=row['owner']
   for name in SECTIONS:changed[name]+=list(now[name])!=list(old['owner'][name])
   if row['error']:partial+=any(list(now[n])!=list(old['owner'][n])for n in ('ground','air','feet','lifecycle','landing','selector'))
   feet_changes+=list(now['feet'])!=list(old['owner']['feet'])
   # Entire typed Air record: trajectory result starts after three frames.
   valid_samples+=bool(now['air'][48+33])
   pending_contact+=row['operation']==7 and row['error']is None
   if op==18 and row['error']is None:line_hits+=sum(int(v!=0)for v in now['line_tests'])
 assert success['ground_update']>10 and success['air_update']>10 and success['solve_feedback']>20
 assert changed['feet']>20 and changed['ground']>30 and changed['air']>30 and changed['possession']>0
 assert changed['selector']>10 and valid_samples>10 and pending_contact>10
 assert changed['grab']>10 and changed['landing']>10 and partial>0
 assert any('BoardToolkit'in e for e in errors)and any('metadata'in e.lower()for e in errors)
 assert set(counts)==set(OPS)
 return dict(operations=dict(counts),success=dict(success),errors=dict(errors),changed_owner_records=dict(changed),partial_error_mutations=partial,valid_sample_snapshots=valid_samples,successful_contact_submissions=pending_contact,feet_changes=feet_changes,line_observation_nonzero_words=line_hits)

def preflight(raw,cases,ranges):
 assert struct.unpack_from('<I',raw)[0]==len(cases);assert ranges[0][0]==4 and ranges[-1][1]==len(raw)
 for c,(start,end)in zip(cases,ranges):
  words=contact.encode_world(c['world'])+grab.encode_registry(c['registry'])+[len(c['commands'])]+[w for cmd in c['commands']for w in cmd]
  assert raw[start:end]==b''.join(struct.pack('<I',w&0xffffffff)for w in words)
 for u in UNITS:assert (CODE/(u+'.cpp')).is_file(),u
 defs,_=declarations();assert len(defs['BipedAirTrajectoryResult'])==14 and len(defs['BipedAirState'])==19
 return dict(cases=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(raw),input_sha256=hashlib.sha256(raw).hexdigest(),units=list(UNITS),source_state_fields={n:len(f)for n,f in defs.items()})

def build(output,target):
 original,observed,snapshot,report=prepare(output);crate=observed/'atelier-host'
 subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(crate/'Cargo.toml'),'--target-dir',str(target.resolve()),'--bin','biped-runtime-reference'],check=True)
 reference=output/'biped-runtime-reference';shutil.copy2(target.resolve()/'release/biped-runtime-reference',reference);native=output/'biped-runtime-native'
 subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'biped_runtime_probe.cpp'),'-o',str(native)],check=True)
 for rel,sha in report['original_source_sha256'].items():assert digest(original/rel)==sha;assert (observed/rel).read_bytes()[:(original/rel).stat().st_size]==(original/rel).read_bytes(),rel
 for rel,row in report['staged_host_original_prefixes'].items():assert digest(crate/'src'/rel)==row['generated_sha256'],rel
 report.update(reference_binary_sha256=digest(reference),native_binary_sha256=digest(native));(output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');return native,reference

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 for n in('assets','samples','metadata','output','target-dir'):parser.add_argument('--'+n,type=Path,required=True)
 parser.add_argument('--preflight',action='store_true');a=parser.parse_args();output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
 raw,cases,ranges=corpus();fixtures=loader_fixtures(a.assets.resolve());summary=preflight(raw,cases,ranges);summary.update(loader_fixture_count=len(fixtures),invalid_loader_fixture_count=sum(not s for _,_,s in fixtures));(output/'input.bin').write_bytes(raw);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
 if a.preflight:
  prepare(output);(output/'owner-freeze.json').write_text(json.dumps(dict(**summary,production={p.name:digest(p)for p in OWNED_PRODUCTION},proof={p.name:digest(p)for p in OWNED_TESTS},checker_sha256=digest(Path(__file__))),indent=2)+'\n');print(json.dumps(summary,indent=2));return
 bank=output/'fixtures';bank.mkdir(exist_ok=True);stock=a.assets.resolve()/'private/stock';(bank/'settings.native').write_bytes(phase.converter.encode_settings(stock/'skater-collections.json'));(bank/'physics.native').write_bytes(phase.converter.encode_physics_skeletons(stock/'physics-skeletons.json'))
 for n in('action','motion'):(bank/f'actor.{n}.reference').write_bytes(phase.original_graph(phase.element('state','idle')))
 identity=json.loads((stock/'physics-skeletons.json').read_text())['source_sha256'];native,reference=build(output,a.target_dir)
 expected=subprocess.check_output([str(reference),str(a.assets.resolve()),str(bank)],input=raw);actual=subprocess.check_output([str(native),str(bank/'settings.native'),str(bank/'physics.native'),str(a.samples.resolve()/'native/rig.skate'),identity,str(a.assets.resolve()),str(a.metadata.resolve())],input=raw)
 (output/'reference.bin').write_bytes(expected);(output/'native.bin').write_bytes(actual);frames=decode(expected,cases)
 if expected!=actual:
  byte=next((n for n,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));word=byte//4;case=next((c for c in cases if c['first_output_word']<=word<c['last_output_word']),None);row=next((r for rows in frames for r in rows if r['first_word']<=word<r['last_word']),None);section=next(((n,word-s[0])for n,s in(row['spans'].items()if row else[])if s[0]<=word<s[1]),None)
  divergence=dict(first_byte=byte,first_word=word,reference_bytes=len(expected),native_bytes=len(actual),case=case['index']if case else None,operation=OPS[row['operation']]if row else'initial',section=section,reference_hex=expected[max(0,byte-16):byte+32].hex(),native_hex=actual[max(0,byte-16):byte+32].hex());(output/'first-divergence.json').write_text(json.dumps(divergence,indent=2)+'\n');raise AssertionError(divergence)
 covered=coverage(frames,cases);loader_reports=[]
 for index,(label,data,success)in enumerate(fixtures):
  folder=output/'loader-fixtures'/str(index);path=folder/'private/stock/skater-collections.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data));converted=folder/'settings.native';converted.write_bytes(phase.converter.encode_settings(path))
  ref=subprocess.check_output([str(reference),str(a.assets.resolve()),str(bank),str(folder)]);cpp=subprocess.check_output([str(native),str(bank/'settings.native'),str(bank/'physics.native'),str(a.samples.resolve()/'native/rig.skate'),identity,str(a.assets.resolve()),str(a.metadata.resolve()),str(converted)]);(folder/'reference.bin').write_bytes(ref);(folder/'native.bin').write_bytes(cpp)
  assert ref==cpp,dict(loader=label,reference_bytes=len(ref),native_bytes=len(cpp));loader_reports.append(decode_loader(ref,success,label))
 result=dict(**summary,passed=True,reference_revision=REFERENCE_REVISION,bytes=len(expected),exact_words=len(expected)//4+sum(r['exact_words']for r in loader_reports),output_sha256=hashlib.sha256(expected).hexdigest(),coverage=covered,loader_fixtures=loader_reports,scope='Whole unchanged active Ground/Air Biped core+host, actual shared controller, corrected pose/body/IK/drives, retained world queries/grab/landing and shared solve feedback.',boundaries='Completed canonical processed and animation-attribute packets, authored pose selection, engine triangle/query metadata and registry objects are explicit upstream inputs. This proof schedules concrete source callbacks individually; whole global state selection, mounting503 host, animation graph and source-hang/unsupported provider domains are separate. The loader fixture retains both prior owners until both fresh constructors succeed. No pose, hit, prediction or callback success is seeded.')
 (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
