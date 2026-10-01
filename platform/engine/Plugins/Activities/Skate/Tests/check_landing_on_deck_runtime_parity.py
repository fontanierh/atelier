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
OWNED=tuple(PLUGIN/'Tests'/p for p in('Native/landing_on_deck_runtime_probe.cpp','Reference/landing_on_deck_runtime_probe.rs','Reference/landing_on_deck_runtime_observer.rs'))
PRODUCTION=tuple([CODE/(u+'.cpp')for u in FAMILY]+[CODE/'LandingOnDeckRuntime.h'])

def replace_once(text,old,new):
 assert text.count(old)==1,(old,text.count(old));return text.replace(old,new)

def prepare(output):
 original,observed,snapshot,report=biped.prepare(output);crate=observed/'atelier-host'
 cpp=(snapshot/'biped_runtime_probe.cpp').read_text()
 update='\n'.join(biped.block('Native/landing_deck_probe.cpp',p)for p in('void RequestOut(','void Output(')).replace('Writer','BipedOutput').replace('void Output(','void UpdateOut(')
 extension=(PLUGIN/'Tests/Native/landing_on_deck_runtime_probe.cpp').read_text().replace('// GENERATED_UPDATE_OBSERVER',update)
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
 for u in FAMILY:shutil.copy2(CODE/(u+'.cpp'),snapshot/(u+'.cpp'));report['native_source_sha256'][u+'.cpp']=digest(CODE/(u+'.cpp'))
 # Extend only our copied fixture observer, never an original owner body.
 physics=crate/'src/physics.rs';data=physics.read_text();fixture=(PLUGIN/'Tests/Reference/biped_runtime_observer.rs').read_text();modified=replace_once(fixture,' o.word(16);block(o,|o|biped_ground::',' super::migration_landing_host::snapshot(o,s);o.word(16);block(o,|o|biped_ground::')
 extra='''31=>super::migration_landing_host::pose(i,&p,&mut s),32=>landing_on_deck::enter(&mut p,&mut s),33=>landing_on_deck::advance(&mut p,&mut s),
   34=>match observations!(p,s).frame(){Ok(f)=>landing_on_deck::post(&mut s,f),Err(e)=>Err(e)},35=>landing_on_deck::fill(&mut s),36=>landing_on_deck::exit(&mut p,&mut s),37=>{s.animation.packet.local.clear();Ok(())},38=>{s.animation.packet.hierarchy.clear();Ok(())},39=>{s.animation_input.extra.jump_strength=i.float();s.animation_input.extra.physical_body_spin=i.float();Ok(())},_=>panic!("Biped owner operation")'''
 modified=replace_once(modified,'_=>panic!("Biped owner operation")',extra)
 data=replace_once(data,fixture,modified)+(PLUGIN/'Tests/Reference/landing_on_deck_runtime_probe.rs').read_text()+'''
pub(crate)fn migration_landing_load(assets:&std::path::Path,invalid:&std::path::Path,o:&mut crate::Output)->Result<(),String>{
 let stock=skate_data::collections::Collections::load(assets)?;let mut manager=offboard::landing_deck::Owner::load(&stock)?;let mut owner=landing_on_deck::Runtime::load(&stock)?;
 o.status(Ok(()));let at=o.0.len();o.word(0);offboard::landing_deck::migration_biped_observe(o,&manager);o.0[at]=(o.0.len()-at-1)as u32;let at=o.0.len();o.word(0);landing_on_deck::migration_landing_observe(o,&owner);o.0[at]=(o.0.len()-at-1)as u32;
 let data=skate_data::collections::Collections::load(invalid)?;let result=offboard::landing_deck::Owner::load(&data).and_then(|m|landing_on_deck::Runtime::load(&data).map(|s|(m,s)));match result{Ok((m,s))=>{manager=m;owner=s;o.status(Ok(()))},Err(e)=>o.status(Err(e))}
 let at=o.0.len();o.word(0);offboard::landing_deck::migration_biped_observe(o,&manager);o.0[at]=(o.0.len()-at-1)as u32;let at=o.0.len();o.word(0);landing_on_deck::migration_landing_observe(o,&owner);o.0[at]=(o.0.len()-at-1)as u32;Ok(())}
'''
 physics.write_text(data)
 appends={'crates/skate-host/src/physics/landing_on_deck.rs':(PLUGIN/'Tests/Reference/landing_on_deck_runtime_observer.rs').read_text(),'crates/skate-core/src/physics/skeleton_output/wobble.rs':'\nimpl Wobble{pub fn migration_landing_selected(&self)->bool{self.selected_landing_curves}}\n'}
 for rel,extra in appends.items():
  p=crate/'src'/rel.removeprefix('crates/skate-host/src/')if rel.startswith('crates/skate-host/src/')else observed/rel;p.write_bytes(p.read_bytes()+extra.encode());assert p.read_bytes()[:(original/rel).stat().st_size]==(original/rel).read_bytes();report.setdefault('landing_appended_observers',{})[rel]=dict(original_prefix_sha256=digest(original/rel),append_sha256=hashlib.sha256(extra.encode()).hexdigest(),generated_sha256=digest(p))
 rs=crate/'src/migration_probe.rs';r=rs.read_text();up='\n'.join(biped.block('Reference/landing_deck_probe.rs',p)for p in('fn request_out(','fn output(')).replace('Writer','Output').replace('fn output(','fn landing_update_out(').replace('request_out(o,q)','landing_request_out(o,q)').replace('fn request_out(','fn landing_request_out(').replace('.scalar(','.float(').replace('native::UpdateOutput','skate_core::player::offboard::landing_deck::UpdateOutput').replace('q:QueryRequest','q:skate_core::air::trajectory::QueryRequest').replace('vo(o,v)','biped_landing::vo(o,v)').replace('to(o,q.trajectory)','biped_landing::to(o,q.trajectory)')
 r=r.replace('physics::migration_biped_load(','physics::migration_landing_load(');r=r.replace('fn main(){',up+'\nfn main(){',1);rs.write_text(r)
 cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text().replace('name="biped-runtime-reference"','name="landing-on-deck-runtime-reference"'))
 for rel,row in report['staged_host_original_prefixes'].items():row['generated_sha256']=digest(crate/'src'/rel)
 report['biped_appended_observers']['crates/skate-host/src/physics.rs']['generated_sha256']=digest(physics)
 constructor=(original/'crates/skate-host/src/skater_animation.rs').read_text();start=constructor.index('packet: PhysicsPosePacket {');end=constructor.index('\n            },',start)+len('\n            },');fragment=constructor[start:end]
 report['packet_constructor_transport']=dict(original_source_sha256=digest(original/'crates/skate-host/src/skater_animation.rs'),exact_constructor_slice_sha256=hashlib.sha256(fragment.encode()).hexdigest(),exact_constructor_slice_bytes=[len(constructor[:start].encode()),len(constructor[:end].encode())],native_accepted_constructor_sha256=digest(CODE/'SkaterAnimation.cpp'),boundary='Only the authoritative incoming packet storage initialization is reproduced at the explicit upstream boundary: actual rig count, RESET_POSE arrays and fixed-step word0x3c888889. Authored hierarchy/local matrices are produced by the actual evaluator. The mutable graph actor is not duplicated.')
 report.update(landing_fixture_adapter_sha256=dict(frozen_biped_cpp=digest(snapshot/'biped_runtime_probe.cpp'),native_generated=digest(snapshot/'landing_on_deck_runtime_probe.cpp'),frozen_biped_reference_observer=hashlib.sha256(fixture.encode()).hexdigest(),extended_fixture_observer=hashlib.sha256(modified.encode()).hexdigest()),landing_production={p.name:digest(p)for p in PRODUCTION},landing_proof={p.name:digest(p)for p in OWNED},generated_reference_probe_sha256=digest(rs),boundary=__doc__)
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
 def landing(self):
  assert self.word()==len(SECTIONS);records={};spans={}
  for name in SECTIONS:n=self.word();at=self.at;records[name]=self.take(n);spans[name]=[at,self.at]
  return records,spans

def decode(raw,cases):
 r=Reader(raw);assert r.word()==len(cases);all_rows=[]
 def snapshot():
  landing,spans=r.landing();owner,more=r.biped();spans.update(more);foot=r.foot();spans.update(r.foot_spans);shared=r.snapshot();spans.update(r.spans);return dict(landing=landing,owner=owner,foot=foot,shared=shared,spans=spans)
 for c in cases:
  c['first_output_word']=r.at;assert r.word()==len(c['commands']);prior=snapshot();rows=[]
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
 raw,cases,ranges=corpus();assert ranges[0][0]==4 and ranges[-1][1]==len(raw)
 for c,(start,end)in zip(cases,ranges):assert raw[start:end]==b''.join(struct.pack('<I',w&0xffffffff)for w in biped.landing.encode_world(c['world'])+biped.grab.encode_registry(c['registry'])+[len(c['commands'])]+[w for cmd in c['commands']for w in cmd])
 identity=biped.landing.converter.name_id;biped.landing.converter.name_id=lru_cache(maxsize=None)(identity)
 try:fixtures=biped.landing.loader_fixtures(a.assets.resolve())
 finally:biped.landing.converter.name_id=identity
 summary=dict(histories=len(cases),callbacks=sum(len(c['commands'])for c in cases),input_bytes=len(raw),input_sha256=hashlib.sha256(raw).hexdigest(),loader_fixture_count=len(fixtures),invalid_loader_fixture_count=sum(not f['success']for f in fixtures),units=UNITS)
 (output/'input.bin').write_bytes(raw);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');original,observed,snapshot,report=prepare(output)
 if a.preflight:
  freeze=dict(**summary,production={p.name:digest(p)for p in PRODUCTION},proof={p.name:digest(p)for p in OWNED},checker_sha256=digest(Path(__file__)));(output/'owner-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n');print(json.dumps(summary,indent=2));return
 for u in UNITS:assert (snapshot/(u+'.cpp')).is_file(),u
 crate=observed/'atelier-host';subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(crate/'Cargo.toml'),'--target-dir',str(a.target_dir.resolve()),'--bin','landing-on-deck-runtime-reference'],check=True);reference=output/'landing-on-deck-runtime-reference';shutil.copy2(a.target_dir.resolve()/'release/landing-on-deck-runtime-reference',reference)
 native=output/'landing-on-deck-runtime-native';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'landing_on_deck_runtime_probe.cpp'),'-o',str(native)],check=True)
 for rel,sha in report['original_source_sha256'].items():assert digest(original/rel)==sha;assert (observed/rel).read_bytes()[:(original/rel).stat().st_size]==(original/rel).read_bytes(),rel
 for rel,row in report['staged_host_original_prefixes'].items():assert digest(crate/'src'/rel)==row['generated_sha256'],rel
 bank=output/'fixtures';bank.mkdir(exist_ok=True);stock=a.assets.resolve()/'private/stock';(bank/'settings.native').write_bytes(biped.phase.converter.encode_settings(stock/'skater-collections.json'));(bank/'physics.native').write_bytes(biped.phase.converter.encode_physics_skeletons(stock/'physics-skeletons.json'))
 for n in('action','motion'):(bank/f'actor.{n}.reference').write_bytes(biped.phase.original_graph(biped.phase.element('state','idle')))
 identity=json.loads((stock/'physics-skeletons.json').read_text())['source_sha256'];native_args=[str(native),str(bank/'settings.native'),str(bank/'physics.native'),str(a.samples.resolve()/'native/rig.skate'),identity,str(a.assets.resolve()),str(a.metadata.resolve())]
 expected=subprocess.check_output([str(reference),str(a.assets.resolve()),str(bank)],input=raw);actual=subprocess.check_output(native_args,input=raw);(output/'reference.bin').write_bytes(expected);(output/'native.bin').write_bytes(actual);frames=decode(expected,cases)
 if expected!=actual:
  byte=next((n for n,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));word=byte//4;c=next((c for c in cases if c['first_output_word']<=word<c['last_output_word']),None);row=next((r for rows in frames for r in rows if r['first_word']<=word<r['last_word']),None);section=next(((name,word-begin)for name,(begin,end)in(row['spans'].items()if row else[])if begin<=word<end),None);divergence=dict(first_word=word,reference_bytes=len(expected),native_bytes=len(actual),case=c['index']if c else None,operation=OPS[row['operation']]if row else'initial',section=section,reference_hex=expected[max(0,byte-16):byte+32].hex(),native_hex=actual[max(0,byte-16):byte+32].hex());(output/'first-divergence.json').write_text(json.dumps(divergence,indent=2)+'\n');raise AssertionError(divergence)
 covered=coverage(frames);loaders=[]
 for index,f in enumerate(fixtures):
  folder=output/'loader-fixtures'/str(index);path=folder/'private/stock/skater-collections.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(f['data']));converted=folder/'settings.native';converted.write_bytes(biped.phase.converter.encode_settings(path));ref=subprocess.check_output([str(reference),str(a.assets.resolve()),str(bank),str(folder)]);cpp=subprocess.check_output([*native_args,str(converted)]);(folder/'reference.bin').write_bytes(ref);(folder/'native.bin').write_bytes(cpp);assert ref==cpp,f['label'];loaders.append(biped.decode_loader(ref,f['success'],f['label']))
 result=dict(**summary,passed=True,reference_revision=REFERENCE_REVISION,stock_exact_words=len(expected)//4,output_sha256=hashlib.sha256(expected).hexdigest(),coverage=covered,loader_fixtures=loaders,limitations='Actual whole unchanged landing503 host/core and shared501/500 owners. Completed canonical processed/attribute packets, authored evaluated poses, engine triangles/metadata and grab registry are upstream fixture boundaries. Packet storage follows the exact SkaterAnimation constructor boundary; local/hierarchy are evaluated by the real canonical pose evaluator. Full graph actor, global transition, render and FootPhysical publication are separate. Both fresh constructor owners are retained transactionally by the explicit loader fixture until both succeed.')
 report.update(reference_binary_sha256=digest(reference),native_binary_sha256=digest(native));(output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');(output/'result.json').write_text(json.dumps(result,indent=2)+'\n');(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
