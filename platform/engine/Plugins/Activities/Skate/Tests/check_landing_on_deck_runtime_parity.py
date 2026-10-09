#!/usr/bin/env python3
"""Whole unchanged State503 host over the SAME Biped/landing/physical owners.

Only root builds or executes. The canonical processed/attribute packet and
authored evaluated pose are explicit upstream producers. Real world queries,
shared Manager68, Biped reckoning16016, IK, board ownership and solves remain
actual source owners. --preflight stages source and audits wire bytes only.
"""
import argparse
from collections import Counter
from functools import lru_cache
import copy,hashlib,json,re,shutil,struct,subprocess
from pathlib import Path
import check_biped_runtime_parity as biped
from check_animation_playback_parity import Stream
from session_parity import digest,REFERENCE_REVISION
PLUGIN,CODE=biped.PLUGIN,biped.CODE
FAMILY=('LandingOnDeckRuntime','LandingOnDeckSkeleton','LandingOnDeckPublication')
UNITS=tuple(dict.fromkeys((*biped.UNITS,*FAMILY)))
OPS=(*biped.OPS,'pose_local','landing_enter','landing_advance','landing_post','landing_fill','landing_exit','clear_local','clear_hierarchy','landing_attributes')
SECTIONS=('landing_runtime','pose','wobble')
OWNED=tuple(PLUGIN/'Tests'/p for p in('Simulation/landing_on_deck_runtime_probe.cpp','Reference/landing_on_deck_runtime_probe.rs','Reference/landing_on_deck_runtime_observer.rs'))
PRODUCTION=tuple([CODE/(u+'.cpp')for u in FAMILY]+[CODE/'LandingOnDeckRuntime.h'])

def replace_once(text,old,new):
 assert text.count(old)==1,(old,text.count(old));return text.replace(old,new)

# Decode only the requested wire after a genuine constructor rejection. These
# adapters call no player callback and construct no replacement world/owner.
REJECTED_CPP='''
void LandingSkipWorld(BipedInput& input)
{
    biped_world::Reader r{input.data,input.at};
    for(auto n=r.Word();n;--n)(void)biped_world::ReadTriangle(r);
    (void)r.Word();(void)biped_world::Metadata(r);input.at=r.at;
}
std::uint32_t LandingSkipCommands(BipedInput& i)
{
    const auto count=i.Word();
    for(std::uint32_t n=0;n<count;++n){const auto op=i.Word();switch(op){
    case 0:(void)ReadProcessedPhysicsInput(i);for(unsigned k=0;k<21;++k)(void)i.Word();break;
    case 1:case 2:case 25:case 31:(void)i.Word();break;
    case 26:case 39:(void)i.Word();(void)i.Word();break;
    case 22:LandingSkipWorld(i);break;
    default:if((op>=3&&op<=21)||op==23||op==24||(op>=27&&op<=30)||(op>=32&&op<=38))break;
        Fail("Unknown requested Landing operation after construction rejection");
    }}return count;
}
'''
REJECTED_RUST_WORLD='''
pub(super)fn skip(input:&mut crate::Input){
 let mut r=Reader{bytes:input.data.clone(),at:input.at};
 for _ in 0..r.word(){let _=triangle(&mut r);}let _=r.word();let _=metadata(&mut r);input.at=r.at;
}
'''
REJECTED_RUST='''
fn migration_landing_skip_commands(i:&mut Input)->u32{
 let count=i.word();for _ in 0..count{match i.word(){
  0=>{let _=read_ProcessedPhysicsInput(i);for _ in 0..21{let _=i.word();}},
  1|2|25|31=>{let _=i.word();},26|39=>{let _=i.word();let _=i.word();},
  22=>biped_world::skip(i),3..=21|23|24|27..=30|32..=38=>{},
  _=>panic!("Unknown requested Landing operation after construction rejection")
 }}count
}
'''

def audit_command_skip(cases):
 """Independently check every generated skip branch consumes its full wire."""
 defs,_=biped.wire.declarations();counts=Counter()
 for case in cases:
  raw=b''.join(struct.pack('<I',w&0xffffffff)for w in [len(case['commands'])]+[w for c in case['commands']for w in c]);r=biped.wire.Reader(raw)
  assert r.word()==len(case['commands'])
  def take(n):
   for _ in range(n):r.word()
  for command in case['commands']:
   at=r.at;op=r.word();assert op==command[0];counts[op]+=1
   if op==0:r.value('ProcessedPhysicsInput',defs);take(21)
   elif op in(1,2,25,31):take(1)
   elif op in(26,39):take(2)
   elif op==22:take(r.word()*18);take(1);take(r.word());take(r.word()*36);take(r.word()*12);take(1)
   else:assert 3<=op<=21 or op in(23,24)or 27<=op<=30 or 32<=op<=38,op
   assert r.at-at==len(command)*4,(case['index'],op,r.at-at,len(command)*4)
  assert r.at==len(raw)
 return dict(requested_commands=sum(counts.values()),operations=dict(counts),all_command_boundaries_exact=True,no_host_callbacks=True)

def prepare(output):
 original,observed,snapshot,report=biped.prepare(output);crate=observed/'atelier-host'
 # Declaration-only adapters stay local to this proof. Distinct aliases avoid
 # duplicate exports when Publication later extends the same staged source.
 descriptor_rel='crates/skate-core/src/player/offboard/contact_toolkit.rs'
 descriptor_append='\npub use probes::Descriptor as MigrationLandingDescriptor;\n'
 descriptor=observed/descriptor_rel;descriptor.write_bytes(descriptor.read_bytes()+descriptor_append.encode())
 descriptor_original=(original/descriptor_rel).read_bytes();assert descriptor.read_bytes()[:len(descriptor_original)]==descriptor_original
 report['biped_appended_observers'][descriptor_rel]['generated_sha256']=digest(descriptor)
 selector_append='\npub(crate)use offboard::air_selector as migration_landing_air_selector;\n'
 report['landing_visibility_adapters']={descriptor_rel:dict(original_prefix_sha256=digest(original/descriptor_rel),append_sha256=hashlib.sha256(descriptor_append.encode()).hexdigest(),generated_sha256=digest(descriptor)),'crates/skate-host/src/physics.rs':dict(original_prefix_sha256=digest(original/'crates/skate-host/src/physics.rs'),append_sha256=hashlib.sha256(selector_append.encode()).hexdigest())}
 cpp=(snapshot/'biped_runtime_probe.cpp').read_text()
 # The source force observer includes all21 retained slots even after Clear.
 # Count is an independent active prefix; mirror the full stored-array wire.
 force_loop='for(std::size_t n=0;n<p.board.Forces().Count();++n)'
 assert cpp.count(force_loop)==1
 cpp=replace_once(cpp,force_loop,'for(std::size_t n=0;n<ForceCapacity;++n)')
 # Original Flat GamePhysics constructs StaticProvider::new(None), and
 # SkaterRuntime::load binds that same real empty provider to trajectory.
 # The world-only fixture replacement does not replace physics.grind_world.
 provider_boundary='        auto bground=BipedGroundRuntime::Load'
 provider_binding='        auto trajectory_grind=PlayerGrindStaticProvider::FromConverted(PlayerGrindConvertedData{},error);if(!trajectory_grind)Fail(error.c_str());\n        trajectory.BindGrindWorld(std::make_shared<const PlayerGrindStaticProvider>(std::move(*trajectory_grind)));\n'
 cpp=replace_once(cpp,provider_boundary,provider_binding+provider_boundary)
 # The copied Biped observer calls four shared child overloads before their
 # definitions. Declare those exact overloads locally; all observed fields and
 # their order remain byte-for-byte the frozen shared protocol.
 child_observers=('AirOutputFields','ProbeFields','ExternalPhysicsInput','LineTestFields')
 observer_declarations=''.join(f'void Observe(BipedOutput&,const {name}&);\n'for name in child_observers)
 for name in child_observers:
  assert cpp.count(f'void Observe(BipedOutput& o,const {name}& s){{')==1,name
  assert f'void Observe(BipedOutput&,const {name}&);'not in cpp,name
 observer_anchor='void Observe(BipedOutput&,const BipedIntentState&);'
 before_declarations=cpp
 cpp=replace_once(cpp,observer_anchor,observer_declarations+observer_anchor)
 assert cpp.replace(observer_declarations,'',1)==before_declarations
 report['landing_observer_declaration_adapter']=dict(types=child_observers,inserted_sha256=hashlib.sha256(observer_declarations.encode()).hexdigest(),frozen_biped_cpp_sha256=hashlib.sha256(before_declarations.encode()).hexdigest(),declaration_only=True,wire_order_unchanged=True)
 update='\n'.join(biped.block('Simulation/landing_deck_probe.cpp',p)for p in('void RequestOut(','void Output(')).replace('Writer','BipedOutput').replace('void Output(','void UpdateOut(')
 extension=(PLUGIN/'Tests/Simulation/landing_on_deck_runtime_probe.cpp').read_text().replace('// GENERATED_UPDATE_OBSERVER',update)
 cpp=replace_once(cpp,'int main(int argc,char** argv)',extension+'\nint main(int argc,char** argv)')
 # Only fixture-owner initialization is inserted: source SkaterAnimation::load
 # initializes actual packet storage at this same rig-count/reset boundary.
 cpp=replace_once(cpp,'PhysicsPosePacket pose;', 'PhysicsPosePacket pose;pose.bone_count=std::uint32_t(evaluator.frames.rig.bones.size());pose.hierarchy.assign(pose.bone_count,AnimationResetPose);pose.local.assign(pose.bone_count,AnimationResetPose);pose.timestep=landing_host_detail::PhysicalStep();')
 cpp=replace_once(cpp,'OffboardContactToolkit contact;OffboardAirSelector selector(selected);','LandingOnDeckRuntime landed;SkeletonWobble wobble;if(!landed.Load(data,error))Fail(error.c_str());OffboardContactToolkit contact;OffboardAirSelector selector(selected);')
 cpp=replace_once(cpp,'const auto snapshot=[&]{BipedSnapshot','const LandingOnDeckOwners landing_owners{owners,*bground,pose,wobble};const auto snapshot=[&]{landing_host_detail::Snapshot(o,landed,pose,wobble);BipedSnapshot')
 extra='''case 31:okay=landing_host_detail::Pose(i,evaluator,pose,owners,error);break;
            case 32:okay=landed.Enter(landing_owners,error);break;case 33:okay=landed.Advance(landing_owners,error);break;
            case 34:{WipeoutFrame frame;okay=Observations(owners,trajectory,*player_state).Frame(frame,error);if(okay)okay=landed.PostPhysics(landing_owners,frame,error);break;}
            case 35:okay=landed.Fill(landing_owners,error);break;case 36:landed.Exit(landing_owners);break;
            case 37:pose.local.clear();break;case 38:pose.hierarchy.clear();break;
            case 39:anim.extra.jump_strength=i.Float();anim.extra.physical_body_spin=i.Float();break;
            default:return 2;'''
 cpp=replace_once(cpp,'case 30:landing.Reset();break;default:return 2;','case 30:landing.Reset();break;'+extra)
 cpp=replace_once(cpp,'int main(int argc,char** argv)',REJECTED_CPP+'\nint main(int argc,char** argv)')
 cpp=replace_once(cpp,'if(!registry)Fail(error.c_str());','if(!registry){o.Status(false,error);o.Word(LandingSkipCommands(i));continue;}')
 cpp=replace_once(cpp,'const auto n=i.Word();o.Word(n);snapshot();for(unsigned k=0;k<n;++k)','o.Status(true,"");const auto n=i.Word();o.Word(n);snapshot();for(unsigned k=0;k<n;++k)')
 # The focused constructor observer uses complete original constructors and
 # retains both previous owners until both fresh constructors succeed.
 begin=cpp.index('    if(argc==8)\n');end=cpp.index('    if(!skeletons.Load',begin)
 cpp=cpp[:begin]+'''    if(argc==8)
    {
        LandingDeck manager;LandingOnDeckRuntime owner;BipedOutput o;if(!manager.Load(data,error)||!owner.Load(data,error))return 2;
        o.Status(true,"");Block(o,[&]{biped_landing::OwnerOut(o,manager);});Block(o,[&]{landing_host_detail::OwnerOut(o,owner);});
        SettingsDatabase invalid;if(!invalid.Load(File(argv[7]),error))return 2;LandingDeck next;LandingOnDeckRuntime next_owner;bool okay=next.Load(invalid,error);if(okay)okay=next_owner.Load(invalid,error);if(okay){manager=std::move(next);owner=std::move(next_owner);}o.Status(okay,error);
        Block(o,[&]{biped_landing::OwnerOut(o,manager);});Block(o,[&]{landing_host_detail::OwnerOut(o,owner);});for(const auto w:o.words)for(unsigned n=0;n<4;++n)std::cout.put(char(w>>(n*8)));return std::cout?0:2;
    }
'''+cpp[end:]
 (snapshot/'landing_on_deck_runtime_probe.cpp').write_text(cpp)
 for u in FAMILY:shutil.copy2(CODE/(u+'.cpp'),snapshot/(u+'.cpp'));report['simulation_source_sha256'][u+'.cpp']=digest(CODE/(u+'.cpp'))
 # Extend only our copied fixture observer, never an original owner body.
 physics=crate/'src/physics.rs';data=physics.read_text();fixture=(PLUGIN/'Tests/Reference/biped_runtime_observer.rs').read_text();modified=replace_once(fixture,' o.word(16);block(o,|o|biped_ground::',' super::migration_landing_host::snapshot(o,s);o.word(16);block(o,|o|biped_ground::')
 extra='''31=>super::migration_landing_host::pose(i,&p,&mut s),32=>landing_on_deck::enter(&mut p,&mut s),33=>landing_on_deck::advance(&mut p,&mut s),
   34=>match observations!(p,s).frame(){Ok(f)=>landing_on_deck::post(&mut s,f),Err(e)=>Err(e)},35=>landing_on_deck::fill(&mut s),36=>landing_on_deck::exit(&mut p,&mut s),37=>{s.animation.packet.local.clear();Ok(())},38=>{s.animation.packet.hierarchy.clear();Ok(())},39=>{s.animation_input.extra.jump_strength=i.float();s.animation_input.extra.physical_body_spin=i.float();Ok(())},_=>panic!("Biped owner operation")'''
 modified=replace_once(modified,'_=>panic!("Biped owner operation")',extra)
 modified=replace_once(modified,'p.offboard_grab_scene=offboard::grab_scene::Registry::new(&p.world,objects,bindings)?;',
  'match offboard::grab_scene::Registry::new(&p.world,objects,bindings){Ok(registry)=>p.offboard_grab_scene=registry,Err(error)=>{o.status(Err(error));o.word(crate::migration_landing_skip_commands(i));continue;}}')
 modified=replace_once(modified,'let n=i.word();o.word(n);snapshot(o,&p,&s,&last,returned);','o.status(Ok(()));let n=i.word();o.word(n);snapshot(o,&p,&s,&last,returned);')
 data=replace_once(data,fixture,modified)+(PLUGIN/'Tests/Reference/landing_on_deck_runtime_probe.rs').read_text()+'''
pub(crate)fn migration_landing_load(assets:&std::path::Path,invalid:&std::path::Path,o:&mut crate::Output)->Result<(),String>{
 let stock=skate_data::collections::Collections::load(assets)?;let mut manager=offboard::landing_deck::Owner::load(&stock)?;let mut owner=landing_on_deck::Runtime::load(&stock)?;
 o.status(Ok(()));let at=o.0.len();o.word(0);offboard::landing_deck::migration_biped_observe(o,&manager);o.0[at]=(o.0.len()-at-1)as u32;let at=o.0.len();o.word(0);landing_on_deck::migration_landing_observe(o,&owner);o.0[at]=(o.0.len()-at-1)as u32;
 let data=skate_data::collections::Collections::load(invalid)?;let result=offboard::landing_deck::Owner::load(&data).and_then(|m|landing_on_deck::Runtime::load(&data).map(|s|(m,s)));match result{Ok((m,s))=>{manager=m;owner=s;o.status(Ok(()))},Err(e)=>o.status(Err(e))}
 let at=o.0.len();o.word(0);offboard::landing_deck::migration_biped_observe(o,&manager);o.0[at]=(o.0.len()-at-1)as u32;let at=o.0.len();o.word(0);landing_on_deck::migration_landing_observe(o,&owner);o.0[at]=(o.0.len()-at-1)as u32;Ok(())}
'''
 physics.write_text(data+selector_append)
 report['landing_visibility_adapters']['crates/skate-host/src/physics.rs']['generated_sha256']=digest(physics)
 appends={'crates/skate-host/src/physics/landing_on_deck.rs':(PLUGIN/'Tests/Reference/landing_on_deck_runtime_observer.rs').read_text(),'crates/skate-core/src/physics/skeleton_output/wobble.rs':'\nimpl Wobble{pub fn migration_landing_selected(&self)->bool{self.selected_landing_curves}}\n'}
 for rel,extra in appends.items():
  p=crate/'src'/rel.removeprefix('crates/skate-host/src/')if rel.startswith('crates/skate-host/src/')else observed/rel;p.write_bytes(p.read_bytes()+extra.encode());assert p.read_bytes()[:(original/rel).stat().st_size]==(original/rel).read_bytes();report.setdefault('landing_appended_observers',{})[rel]=dict(original_prefix_sha256=digest(original/rel),append_sha256=hashlib.sha256(extra.encode()).hexdigest(),generated_sha256=digest(p))
 rs=crate/'src/migration_probe.rs';r=rs.read_text();up='\n'.join(biped.block('Reference/landing_deck_probe.rs',p)for p in('fn request_out(','fn output(')).replace('Writer','Output').replace('fn output(','fn landing_update_out(').replace('request_out(o,q)','landing_request_out(o,q)').replace('fn request_out(','fn landing_request_out(').replace('.scalar(','.float(').replace('native::UpdateOutput','skate_core::player::offboard::landing_deck::UpdateOutput').replace('q:QueryRequest','q:skate_core::air::trajectory::QueryRequest').replace('vo(o,v)','biped_landing::vo(o,v)').replace('to(o,q.trajectory)','biped_landing::to(o,q.trajectory)')
 r=r.replace('physics::migration_biped_load(','physics::migration_landing_load(');r=r.replace('fn main(){',up+'\nfn main(){',1)
 r=replace_once(r,'pub(super)fn read(input:&mut crate::Input)->Result<BoardWorld,String>{',REJECTED_RUST_WORLD+'\npub(super)fn read(input:&mut crate::Input)->Result<BoardWorld,String>{')
 r=replace_once(r,'fn main(){',REJECTED_RUST+'\nfn main(){')
 r=r.replace('toolkit::Descriptor','toolkit::MigrationLandingDescriptor').replace('crate::physics::offboard::air_selector','crate::physics::migration_landing_air_selector');rs.write_text(r)
 cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text().replace('name="biped-runtime-reference"','name="landing-on-deck-runtime-reference"'))
 for rel,row in report['staged_host_original_prefixes'].items():row['generated_sha256']=digest(crate/'src'/rel)
 report['biped_appended_observers']['crates/skate-host/src/physics.rs']['generated_sha256']=digest(physics)
 constructor=(original/'crates/skate-host/src/skater_animation.rs').read_text();start=constructor.index('packet: PhysicsPosePacket {');end=constructor.index('\n            },',start)+len('\n            },');fragment=constructor[start:end]
 report['packet_constructor_transport']=dict(original_source_sha256=digest(original/'crates/skate-host/src/skater_animation.rs'),exact_constructor_slice_sha256=hashlib.sha256(fragment.encode()).hexdigest(),exact_constructor_slice_bytes=[len(constructor[:start].encode()),len(constructor[:end].encode())],simulation_accepted_constructor_sha256=digest(CODE/'SkaterAnimation.cpp'),boundary='Only the authoritative incoming packet storage initialization is reproduced at the explicit upstream boundary: actual rig count, RESET_POSE arrays and fixed-step word0x3c888889. Authored hierarchy/local matrices are produced by the actual evaluator. The mutable graph actor is not duplicated.')
 report.update(landing_fixture_adapter_sha256=dict(frozen_biped_cpp=digest(snapshot/'biped_runtime_probe.cpp'),simulation_generated=digest(snapshot/'landing_on_deck_runtime_probe.cpp'),frozen_biped_reference_observer=hashlib.sha256(fixture.encode()).hexdigest(),extended_fixture_observer=hashlib.sha256(modified.encode()).hexdigest()),landing_production={p.name:digest(p)for p in PRODUCTION},landing_proof={p.name:digest(p)for p in OWNED},generated_reference_probe_sha256=digest(rs),boundary=__doc__)
 report['landing_constructor_rejection_adapter']=dict(simulation_skip_sha256=hashlib.sha256(REJECTED_CPP.encode()).hexdigest(),reference_skip_sha256=hashlib.sha256((REJECTED_RUST_WORLD+REJECTED_RUST).encode()).hexdigest(),initial_construction_status=True,rejected_owner_snapshot=False,rejected_host_callbacks=False,transport='Canonical ProcessedPhysicsInput decoder, all scalar/opcode lanes, and original triangle/metadata readers; no world construction or query runs while skipping requested commands.',actual_source_gate='physics/offboard/grab_scene.rs Registry::new first reads world.query_metadata; simulation OffboardGrabRegistry::Create mirrors this before object validation.')
 (output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');return original,observed,snapshot,report

def corpus():
 _,all_cases,_=biped.corpus();defs,_=biped.wire.declarations();cases=[]
 for index,prior in enumerate(all_cases[:14]+all_cases[-6:]):
  c=copy.deepcopy(prior);c['index']=index;c['label']='Actual501→503→500/501, shared landing queries, late packet failures and shared body/pose/possession histories';commands=c['commands']
  if index in(2,3):c['world']=biped.landing.moving_world(0,platform=.0 if index==2 else .6)
  # Incoming upstream fields are explicit packets. ActualPacket replaces
  # COM/root/velocities with the same physical owner's current observations.
  def packet(k,previous=500):
   p=biped.phase.zero('ProcessedPhysicsInput',defs);p.update(flags_2468=0x2000,flags_2476=4 if index%2 else 0,flags_2480=(0x1000 if index%3==0 else 0)|(0x8000 if k%2 else 0),flags_2484=2 if index%5==0 else 0,flags_2488=0x04000000 if index in(2,3)else 0,state_2508=503,category_2512=500,state_2504=501,category_2516=previous,state_variant_index_2528=1,timestep_2604=1/60,gravity_2648=9.81,state_timer_2664=k/60,scalar_2612=3.137,scalar_2652=3.137,scalar_2616=3.137,actor_query_2952=0xffffffff,frames_since_teleport_2584=21,wheel_count_2556=4 if k%2 else 0)
   p['vectors_544_560_592_608'][0]=biped.phase.foot.fs([0,1,0,0]);p['vectors_464_480_496_512_528'][0]=biped.phase.foot.fs([0,1,0,0]);p['vectors_880_896_912_928_944'][2]=biped.phase.foot.fs([.137,3.137,1.137,0]);p['vectors_880_896_912_928_944'][0]=biped.phase.foot.fs([0,.137,0,0]);s=Stream();s.word(0);biped.wire.encode(s,'ProcessedPhysicsInput',p,defs)
   for f in [0,0,.137,0,0,0,.317,0,.317,1,1,.5,0,.731,0,0,1,0,0,0,0]:s.float(f)
   return list(struct.unpack('<'+'I'*(len(s.data)//4),s.data))
  commands += [packet(0,previous=(400,500,700)[index%3]),[31,index%4],[2,1],[39,biped.phase.foot.bits((0,.5,1)[index%3]),biped.phase.foot.bits((-.731,0,.731)[index%3])],[35],[32],[35]]
  for k in range(12):
   commands += [packet(k),[31,(index+k//3)%4],[2,1],[39,biped.phase.foot.bits((0,.5,1)[index%3]),biped.phase.foot.bits((-.731,0,.731)[k%3])],[33],[16],[18],[17],[34],[35]]
   if index in(2,3)and k%3==0:commands += [[22]+biped.landing.encode_world(biped.landing.moving_world(.03*(k+1),platform=.0 if index==2 else .6))]
   if k in(3,7):commands += [[30],[32]]
  commands += [[36],[35],[31,index%4],[32],[37],[33],[35],[31,index%4],[33],[38],[33],[35],[31,index%4],[33],[34],[35],[2,0],[32],[33],[34],[35],[2,1],[25,1],[32],[25,0],[31,index%4],[32],[33],[36],[11],[12],[13],[14]]
  cases.append(c)
 stream=Stream();stream.word(len(cases));ranges=[]
 for c in cases:
  start=len(stream.data)
  for w in biped.landing.encode_world(c['world'])+biped.grab.encode_registry(c['registry'])+[len(c['commands'])]+[w for cmd in c['commands']for w in cmd]:stream.word(w)
  ranges.append([start,len(stream.data)])
 return bytes(stream.data),cases,ranges

class Reader(biped.Reader):
 def status(self):
  okay=self.word()
  # The wire stores each UTF-8 byte as one u32; bytes(memoryview('I'))
  # copies its raw four-byte storage rather than converting the words.
  return None if okay else bytes(list(self.take(self.word()))).decode()
 def landing(self):
  assert self.word()==len(SECTIONS);records={};spans={}
  for name in SECTIONS:n=self.word();at=self.at;records[name]=self.take(n);spans[name]=[at,self.at]
  return records,spans

def decode_loader(raw,success,label):
 r=Reader(raw);assert r.status()is None,label;prior=[r.take(r.word()),r.take(r.word())];error=r.status();current=[r.take(r.word()),r.take(r.word())]
 assert r.at==len(r.words),(label,r.at,len(r.words));assert (error is None)==success,(label,error,success)
 if not success:assert current==prior,(label,'failed fresh constructors changed retained owners')
 return dict(label=label,success=success,error=error,exact_words=len(r.words))

def decode(raw,cases):
 r=Reader(raw);assert r.word()==len(cases);all_rows=[]
 def snapshot():
  landing,spans=r.landing();owner,more=r.biped();spans.update(more);foot=r.foot();spans.update(r.foot_spans);shared=r.snapshot();spans.update(r.spans);return dict(landing=landing,owner=owner,foot=foot,shared=shared,spans=spans)
 for c in cases:
  c['first_output_word']=r.at;c['construction_error']=r.status();assert r.word()==len(c['commands']);rows=[]
  if c['construction_error']:c['last_output_word']=r.at;all_rows.append(rows);continue
  prior=snapshot()
  for command in c['commands']:
   start=r.at;assert r.word()==command[0];grab=[]
   if command[0]==21:grab=r.take(r.word())
   error=r.status();next=snapshot();rows.append(dict(operation=command[0],error=error,first_word=start,last_word=r.at,grab_publication=grab,prior=prior,**next));prior=next
  c['last_output_word']=r.at;all_rows.append(rows)
 assert r.at==len(r.words),(r.at,len(r.words));return all_rows

def coverage(frames):
 counts=Counter();success=Counter();errors=Counter();changed=Counter();partial=0;outputs=0;hippy=0;wobble=0
 for rows in frames:
  for row in rows:
   name=OPS[row['operation']];counts[name]+=1
   if row['error']:errors[row['error']]+=1
   else:success[name]+=1
   for section in SECTIONS:changed[section]+=list(row['landing'][section])!=list(row['prior']['landing'][section])
   if row['error']:partial+=any(list(row['owner'][n])!=list(row['prior']['owner'][n])for n in('landing','processed','forces','lifecycle'))or any(list(row['landing'][n])!=list(row['prior']['landing'][n])for n in SECTIONS)
   outputs+=bool(row['landing']['landing_runtime'][0]);wobble+=bool(row['landing']['wobble'][0])
 assert success['landing_enter']>10 and success['landing_advance']>10 and success['solve_feedback']>50
 assert changed['landing_runtime']>20 and changed['pose']>20 and changed['wobble']>0 and outputs>20 and wobble>0 and partial>0
 assert any('no local trajectory bone'in e for e in errors)and any('no trajectory bone'in e for e in errors)and any('completed board toolkit'in e for e in errors)
 assert all(counts[op]for op in OPS)
 return dict(operations=dict(counts),success=dict(success),errors=dict(errors),changed_records=dict(changed),partial_error_mutations=partial,output_snapshots=outputs,wobble_active_snapshots=wobble)

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in('assets','samples','metadata','output','target-dir'):p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--preflight',action='store_true');a=p.parse_args();output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
 raw,cases,ranges=corpus();assert ranges[0][0]==4 and ranges[-1][1]==len(raw);skip_audit=audit_command_skip(cases)
 for c,(start,end)in zip(cases,ranges):assert raw[start:end]==b''.join(struct.pack('<I',w&0xffffffff)for w in biped.landing.encode_world(c['world'])+biped.grab.encode_registry(c['registry'])+[len(c['commands'])]+[w for cmd in c['commands']for w in cmd])
 identity=biped.landing.converter.name_id;biped.landing.converter.name_id=lru_cache(maxsize=None)(identity)
 try:fixtures=biped.landing.loader_fixtures(a.assets.resolve())
 finally:biped.landing.converter.name_id=identity
 summary=dict(histories=len(cases),requested_callbacks=sum(len(c['commands'])for c in cases),input_bytes=len(raw),input_sha256=hashlib.sha256(raw).hexdigest(),loader_fixture_count=len(fixtures),invalid_loader_fixture_count=sum(not f['success']for f in fixtures),units=UNITS,command_skip_audit=skip_audit)
 (output/'input.bin').write_bytes(raw);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');original,observed,snapshot,report=prepare(output)
 if a.preflight:
  freeze=dict(**summary,production={p.name:digest(p)for p in PRODUCTION},proof={p.name:digest(p)for p in OWNED},checker_sha256=digest(Path(__file__)));(output/'owner-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n');print(json.dumps(summary,indent=2));return
 for u in UNITS:assert (snapshot/(u+'.cpp')).is_file(),u
 crate=observed/'atelier-host';subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(crate/'Cargo.toml'),'--target-dir',str(a.target_dir.resolve()),'--bin','landing-on-deck-runtime-reference'],check=True);reference=output/'landing-on-deck-runtime-reference';shutil.copy2(a.target_dir.resolve()/'release/landing-on-deck-runtime-reference',reference)
 simulation=output/'landing-on-deck-runtime-simulation';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'landing_on_deck_runtime_probe.cpp'),'-o',str(simulation)],check=True)
 for rel,sha in report['original_source_sha256'].items():assert digest(original/rel)==sha;assert (observed/rel).read_bytes()[:(original/rel).stat().st_size]==(original/rel).read_bytes(),rel
 for rel,row in report['staged_host_original_prefixes'].items():assert digest(crate/'src'/rel)==row['generated_sha256'],rel
 bank=output/'fixtures';bank.mkdir(exist_ok=True);stock=a.assets.resolve()/'private/stock';(bank/'settings.simulation').write_bytes(biped.phase.converter.encode_settings(stock/'skater-collections.json'));(bank/'physics.simulation').write_bytes(biped.phase.converter.encode_physics_skeletons(stock/'physics-skeletons.json'))
 for n in('action','motion'):(bank/f'actor.{n}.reference').write_bytes(biped.phase.original_graph(biped.phase.element('state','idle')))
 identity=json.loads((stock/'physics-skeletons.json').read_text())['source_sha256'];simulation_args=[str(simulation),str(bank/'settings.simulation'),str(bank/'physics.simulation'),str(a.samples.resolve()/'simulation/rig.skate'),identity,str(a.assets.resolve()),str(a.metadata.resolve())]
 expected=subprocess.check_output([str(reference),str(a.assets.resolve()),str(bank)],input=raw);actual=subprocess.check_output(simulation_args,input=raw);(output/'reference.bin').write_bytes(expected);(output/'simulation.bin').write_bytes(actual);frames=decode(expected,cases)
 if expected!=actual:
  byte=next((n for n,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));word=byte//4;c=next((c for c in cases if c['first_output_word']<=word<c['last_output_word']),None);row=next((r for rows in frames for r in rows if r['first_word']<=word<r['last_word']),None);section=next(((name,word-begin)for name,(begin,end)in(row['spans'].items()if row else[])if begin<=word<end),None);divergence=dict(first_word=word,reference_bytes=len(expected),simulation_bytes=len(actual),case=c['index']if c else None,operation=OPS[row['operation']]if row else'initial',section=section,reference_hex=expected[max(0,byte-16):byte+32].hex(),simulation_hex=actual[max(0,byte-16):byte+32].hex());(output/'first-divergence.json').write_text(json.dumps(divergence,indent=2)+'\n');raise AssertionError(divergence)
 rejected=[dict(index=c['index'],error=c['construction_error'],requested_callbacks=len(c['commands']),executed_callbacks=0)for c in cases if c['construction_error']]
 assert rejected==[dict(index=19,error='Canonical world has no authored query metadata',requested_callbacks=430,executed_callbacks=0)],rejected
 assert sum(not c['construction_error']for c in cases)==19
 covered=coverage(frames);loaders=[]
 for index,f in enumerate(fixtures):
  folder=output/'loader-fixtures'/str(index);path=folder/'private/stock/skater-collections.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(f['data']));converted=folder/'settings.simulation';converted.write_bytes(biped.phase.converter.encode_settings(path));ref=subprocess.check_output([str(reference),str(a.assets.resolve()),str(bank),str(folder)]);cpp=subprocess.check_output([*simulation_args,str(converted)]);(folder/'reference.bin').write_bytes(ref);(folder/'simulation.bin').write_bytes(cpp);assert ref==cpp,f['label'];loaders.append(decode_loader(ref,f['success'],f['label']))
 result=dict(**summary,passed=True,reference_revision=REFERENCE_REVISION,callbacks_executed=sum(len(rows)for rows in frames),successful_constructions=19,rejected_constructions=rejected,stock_exact_words=len(expected)//4,output_sha256=hashlib.sha256(expected).hexdigest(),coverage=covered,loader_fixtures=loaders,limitations='Actual whole unchanged landing503 host/core and shared501/500 owners. Completed canonical processed/attribute packets, authored evaluated poses, engine triangles/metadata and grab registry are upstream fixture boundaries. Packet storage follows the exact SkaterAnimation constructor boundary; local/hierarchy are evaluated by the real canonical pose evaluator. Full graph actor, global transition, render and FootPhysical publication are separate. Both fresh constructor owners are retained transactionally by the explicit loader fixture until both succeed. The disabled-metadata initial world is genuinely rejected before any landing callback or owner snapshot; its 430 requested commands are decoded without invoking callbacks or fabricating an owner snapshot.')
 report.update(reference_binary_sha256=digest(reference),simulation_binary_sha256=digest(simulation));(output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');(output/'result.json').write_text(json.dumps(result,indent=2)+'\n');(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
