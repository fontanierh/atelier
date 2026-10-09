#!/usr/bin/env python3
"""Whole unchanged Slide host bound to real pose/world/controller/solve owners.

Only the root render guard compiles or executes. --preflight validates source
prefixes, lossless upstream wire and the complete named simulation closure only.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import check_air_phase_runtime_parity as air
import check_ground_runtime_parity as ground
import check_ground_board_parity as board
import player_input_protocol as packet
from check_animation_playback_parity import Stream,bits
from check_gesture_parity import PLUGIN,converter
from check_graph_parity import element,original_graph
from session_parity import REFERENCE_REVISION,digest
CODE=air.CODE
UNITS=tuple(dict.fromkeys((*air.UNITS,'SlideState','SlideStateSettings','SlideStateRuntime','SlidePhaseRuntime','SlidePhaseBindings')))
SECTIONS=('slide_owner','ground_controllers','processed','lifecycle','forces','collision_feedback','wipeout_frame')
OPS={0:'caller_packet',1:'actual_authored_pose',2:'actual_toolkit',3:'enter_slide',4:'advance_slide',5:'exit_slide',6:'post_slide',13:'actual_board_queries',14:'shared_solve_feedback',15:'replace_world',16:'reset_selector',17:'controller_override',18:'packet_flags',19:'capture_board_error',20:'rebind_grind_world',22:'clear_requests',23:'select_ground_profile',24:'animation_scalar_inputs',25:'physical_board_transform_rates',26:'reset_pumping',27:'queue_external_point_force',28:'packet_surface_mode',29:'reload_trajectory_without_registered_provider',30:'register_same_actual_provider'}
HOST='crates/skate-host/src/physics/'
SLIDE_OBSERVER=r'''
impl SlideState{pub(crate)fn migration_slide_observe(&self,o:&mut crate::Output){let s=&self.state;o.floats([s.start_speed,s.steering_push,s.damped_turn]);o.word(s.flag48 as u32);o.word(s.wall_riding as u32);let t=&self.settings;for c in [&t.input_remap,&t.remap_vs_speed,&t.force_vs_angle,&t.force_vs_speed]{o.floats(c.x);o.floats(c.y);}o.floats([t.softest_wheel_force,t.softest_wheel_spin,t.angular_force,t.force_y_offset]);o.word(self.surfaces.len()as u32);for(s,m)in &self.surfaces{o.floats(s.speed_to_force.x);o.floats(s.speed_to_force.y);o.floats([s.yaw_strength,s.yaw_damping,m.static_friction,m.dynamic_friction,m.restitution]);}o.float(self.manual_scalar);}}
'''
GROUND_OBSERVER=r'''
impl GroundRuntime{pub(crate)fn migration_slide_observe(&self,o:&mut crate::Output){o.floats(self.retained_board_normal);let c=self.contact;o.word(c.active_2731 as u32);o.word(c.tag_16_force.tag);o.floats([c.tag_16_force.force_world.x,c.tag_16_force.force_world.y,c.tag_16_force.force_world.z]);o.floats([c.tag_16_force.point_body.x,c.tag_16_force.point_body.y,c.tag_16_force.point_body.z]);o.floats(c.vector_2688);o.float(c.scalar_2704);o.word(c.animated_board_2708 as u32);o.word(self.collision_force.is_some()as u32);if let Some(f)=self.collision_force{o.floats(f.force_2528);o.floats(f.point_2544);o.floats(f.vector_2592);}}}
'''

def slide_protocol():
 defs=ground.schema();selected={name:defs[name]for name in ('SteeringSettings','ManualGains','ManualSettings','ManualMode','GroundForceSettings','TruckSteeringState','ManualState','PumpingState')}
 selected['PumpingState']=[(f,'u32'if k=='u8'else k)for f,k in selected['PumpingState']]
 cp,rp,_=board.protocol_helpers(selected)
 cp=re.sub(r'\bInput\b','AirInput',cp);cp=re.sub(r'\bOutput\b','AirOutput',cp)
 rp=rp.replace('intentional_pumping:i.word(),','intentional_pumping:i.word()as u8,')
 uses='use skate_core::{physics::manual::{state::ManualState,settings::{ManualSettings,ManualGains,ManualMode}},riding::{steering::{SteeringSettings,TruckSteeringState},ground_force::GroundForceSettings,pumping::state::PumpingState}};\n'
 return cp,uses+rp

def prepare(output):
 original,observed,snapshot,report=air.prepare(output);crate=observed/'atelier-host';host=original/'crates/skate-host/src'
 # Replace only generated observation appendices. Complete source prefixes and
 # every numerical method remain byte-identical to the frozen original.
 for rel,extra in {'physics.rs':(PLUGIN/'Tests/Reference/slide_phase_runtime_observer.rs').read_bytes(),'physics/slide_state.rs':SLIDE_OBSERVER.encode(),'physics/ground_runtime/mod.rs':GROUND_OBSERVER.encode()}.items():
  source=host/rel;raw=source.read_bytes();target=crate/'src'/rel;target.write_bytes(raw+b'\n'+extra);assert target.read_bytes()[:len(raw)]==raw
  report['staged_host_original_prefixes'][rel]=dict(original_prefix_bytes=len(raw),original_prefix_sha256=digest(source),append_sha256=hashlib.sha256(b'\n'+extra).hexdigest(),generated_sha256=digest(target))
 cp,rp=slide_protocol();ac,ar=air.helpers();fc,fr=air.feedback_helpers();pc,pr=air.providers()
 world_cpp=air.extract(PLUGIN/'Tests/Simulation/player_grind_input_probe.cpp','WorldGeometry World(unsigned kind)').replace('World(unsigned kind)','FixtureWorld(unsigned kind)')
 world_rs=air.extract(PLUGIN/'Tests/Reference/player_grind_input_probe.rs','fn fixture_world(kind:u32)');world_rs=re.sub(r'(?<![\w.])\.(\d)',r'0.\1',world_rs)
 # Added vector transport is read-only; no original arithmetic is rewritten.
 rust_probe=PLUGIN/'Tests/Reference/slide_phase_runtime_probe.rs';rs=rust_probe.read_text().replace('// GENERATED_PROTOCOL',ar+'\n'+fr).replace('// GENERATED_PROVIDER',pr+'\n'+world_rs).replace('// GENERATED_SLIDE_PROTOCOL',rp)
 rs=rs.replace('struct Output(Vec<u32>);','struct Output(Vec<u32>);').replace(' fn float(&mut self,v:f32)', ' fn vector(&mut self,v:Vector3){self.floats([v.x,v.y,v.z]);}\n fn float(&mut self,v:f32)')
 (crate/'src/migration_probe.rs').write_text(rs)
 cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text().replace('name="air-phase-runtime-reference"','name="slide-phase-runtime-reference"'))
 prefix,meta=air.foot.extraction(PLUGIN/'Tests/Simulation/footplant_probe.cpp','int main(')
 for name in UNITS:
  path=CODE/(name+'.cpp');assert path.is_file(),name;shutil.copy2(path,snapshot/path.name);report['simulation_source_sha256'][path.name]=digest(path)
 ac=re.sub(r'\bInput\b','AirInput',ac);ac=re.sub(r'\bOutput\b','AirOutput',ac);pc=re.sub(r'\bInput\b','AirInput',pc);pc=re.sub(r'\bOutput\b','AirOutput',pc)
 probe=PLUGIN/'Tests/Simulation/slide_phase_runtime_probe.cpp';simulation=probe.read_text().replace('// GENERATED_PROTOCOL',ac+'\n'+fc).replace('// GENERATED_PROVIDER',pc+'\n'+world_cpp).replace('// GENERATED_SLIDE_PROTOCOL',cp).replace('// GENERATED_COLLISION_OBSERVER','ObserveFeedback(o,p.collision_feedback);')
 simulation=simulation.replace('void Value(Vec4 v){Floats(v);}', 'void Value(Vec3 v){VectorOut(*this,v);}void Value(Vec4 v){Floats(v);}')
 (snapshot/probe.name).write_bytes(b'#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wunused-function"\n'+prefix+b'\n#pragma clang diagnostic pop\n'+simulation.encode())
 report.update(scope='Whole unchanged host slide_state.rs/settings.rs/update.rs and all actual upstream physical/skeleton/controller/trajectory owners.',generated_simulation_probe_sha256=digest(snapshot/probe.name),generated_reference_probe_sha256=digest(crate/'src/migration_probe.rs'),probe_sha256={p.name:digest(p)for p in(probe,rust_probe,PLUGIN/'Tests/Reference/slide_phase_runtime_observer.rs')},simulation_units=list(UNITS),slide_original_source_sha256={HOST+rel:digest(original/HOST/rel)for rel in ('slide_state.rs','slide_state/settings.rs','slide_state/update.rs','input_phase.rs','riding_outputs.rs','air_phase/input.rs')})
 for rel,row in report['staged_host_original_prefixes'].items():raw=(host/rel).read_bytes();assert (crate/'src'/rel).read_bytes()[:len(raw)]==raw,rel
 (output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');return original,observed,snapshot,report

def corpus():
 defs,_=packet.declarations();out=Stream();cases=[];records=[]
 def words(s):return list(struct.unpack('<'+'I'*(len(s.data)//4),s.data))
 def caller(n,mode,surface,*,wall=False,balance=None):
  p=air.zero('ProcessedPhysicsInput',defs)
  p.update(flags_2468=0x2000|(0x8000000 if n%3==0 else 0)|(0x100000 if n%2 else 0),flags_2472=(0x8000000 if n%4<2 else 0)|(0x4000000 if n%4 in(0,2)else 0)|(0x20000 if n%5<2 else 0),flags_2476=(0,1<<30)[n%2],state_2508=101,category_2512=100,state_2504=100,category_2516=(100,200)[n%2],state_variant_index_2528=mode,surface_mode_2540=surface,timestep_2604=(1/60,.003,.033)[n%3],gravity_2648=9.81,scalar_2612=(1.137,-2.137,4.137)[n%3],scalar_2616=4.137,scalar_2652=4.137,scalar_2656=(-4.137,-0.0,0.0,3.137)[n%4],state_timer_2664=(0,.137,.731,1.137)[n%4],time_on_ground_2752=(.009,.015,.137,.731)[n%4],signed_ground_time_2756=(0,-.731,.137)[n%3],truck_tightness_2760=(0,.517,1)[n%3],scalar_2764=(0,.49999997,.5,1.5,1.5000001,2)[n%6],crouch_2776=.317,crouch_delta_2780=.137,spin_input_2672=.317,time_since_last_input_2748=.137,actor_query_2948=17,actor_query_2952=0xffffffff)
  normal=[1,0,0,0]if wall else[0,1,0,0]
  p['vectors_464_480_496_512_528']=[air.foot.fs(normal),air.foot.fs([0,-.05,0,0]),air.foot.fs([0,-.05,0,0]),air.foot.fs([0,0,1,0]),air.foot.fs(normal)]
  p['vectors_544_560_592_608'][0]=air.foot.fs(normal);p['prepared_jump_704']=air.foot.fs([.137,4.137,3.137,0]);p['animation_com_to_deck_752']=air.foot.fs([0,.8,0,0])
  s=Stream();s.word(0);packet.encode(s,'ProcessedPhysicsInput',p,defs)
  for w in air.foot.fs([.137,4.137,3.137,0]):s.word(w)
  s.word(12);s.float((-.317,0,.317)[n%3]);s.float((0,.137)[n%2]);s.float(0)
  return words(s)
 def attributes(n,balance=None):return [24,*map(bits,((-.731,-.0,0,.317,.731)[n%5],(-1,0,.137,1)[n%4],(-.731,-.137,-0.0,0,.317,.731)[n%6]if balance is None else balance,(-1,0,.137,.731,1)[n%5]))]
 def transform(n):return [25,*map(bits,([1,0,0,0,1,0,0,0,1,0,.137,0]+[(.137,1.137,3.137)[n%3],-2.137 if n%2 else .137,4.137,.137,.317,-.731]))]
 empty=dict(rails=[],segments=[],guids=[],assets=[],manifest={});rail=air.provider.authored_provider([[0,-.03,-3],[0,-.03,3]],name='slide-real-rail')
 def add(n,commands,label,mode,surface):
  s=air.provider.Stream();s.word((1,2,3,0)[n%4]);air.provider.encode_provider(s,(empty,rail)[n%2]);s.word(len(commands))
  for c in commands:
   assert c[0]in OPS,c[0]
   for v in c:s.word(v)
  records.append(bytes(s.data));cases.append(dict(index=len(cases),label=label,mode=mode,surface=surface,commands=commands))
 for mode in range(5):
  for surface in range(1,6):
   n=mode*5+surface-1;commands=[[23,mode,surface],caller(n,mode,surface),transform(n),[1,n%4],[2,1],attributes(n),[3],[13]]
   for tick in range(10):
    commands += [caller(n+tick,mode,surface,wall=tick%3==1),attributes(n+tick),[2,1],[13],[4],[14],[6]]
    if tick%3==0:commands += [[15,(1,3,0)[tick//3%3]],[2,1],[13]]
    if tick%4==0:commands += [[26],[16]]
    if tick==6:commands += [[5],[3]]
   commands += [[5],[28,0,mode],[4],[28,surface,mode],[3],[4]]
   add(n,commands,'all25 ground profiles, real Slide skeleton/world/trajectory/force histories',mode,surface)
 for n in range(8):
  mode=n%5;surface=n%5+1;commands=[[23,mode,surface],caller(n,mode,surface),transform(n),[1,0],[2,1],attributes(n,.317),[3],[13],[4],[14],[6]]
  commands += [[2,0],[4],[2,1],[1,4],[4],[1,0],[17,1],[4],[17,0],[4]]
  commands += [[28,0,mode],[4],[28,6,mode],[4],[28,surface,9],[4],[28,surface,mode],attributes(n,float('nan')),[4],attributes(n,.317)]
  commands += [[23,5,surface],[23,mode,0],[23,mode,6],[23,mode,surface]]
  commands += [[13]]+[[27,100+k,*map(bits,[.137,.317,.731,-.137,.173,.113])]for k in range(24)]+[[4],[14],[6],[5]]
  commands += [caller(70+n,mode,surface,wall=True),attributes(n,.317),[15,1],[2,1],[13],[29],[4],[30],[4],[14],[6],[5]]
  add(n+25,commands,'actual early/late failures, retained controllers/materials, force capacity and actual missing-provider launch continuation',mode,surface)
 out.word(len(records))
 for r in records:out.data.extend(r)
 return bytes(out.data),cases

def loader_fixtures(assets):
 data=json.loads((assets/'private/stock/skater-collections.json').read_text());order=[]
 for key in('smooth','rough','slow','slippery','veryslow'):
  order += [('physics_surfaces',key,'Powerslide_SpeedToForce','words'),*[('physics_surfaces',key,f,'f32')for f in('Powerslide_YawStrength','Powerslide_YawDamping','WheelStaticFriction','WheelDynamicFriction')],('physicswheels','default','WheelRestitution','f32')]
 order += [('physics_slide','default',f,'words')for f in('slide_input_remap','Hash_DE162591FD9D91D7','Hash_91282E2CC4252731','Hash_2AD93E5ABA231D2')]+[('physicswheels','default',f,'f32')for f in('SoftestWheelPowerslideFactor','SoftestWheelPowerslideSpinFactor')]+[('physics_slide','default',f,'f32')for f in('AngularForceScalar','PowerSlideForceYOffset')]+[('physics_manual','default','PowerSlideScalar','f32')]
 def resolve(d,f):
  c,k,n,_=f;r=next(r for r in d['collections']if converter.name_id(r['class'])==converter.name_id(c)and converter.name_id(r['key'])==converter.name_id(k));name=next(x for x in r['fields']if converter.name_id(x)==converter.name_id(n));return r,name
 def clone(d):return {**d,'collections':list(d['collections'])}
 def mutate(d,f,kind):
  prior,n=resolve(d,f);at=d['collections'].index(prior);r={**prior,'fields':dict(prior['fields'])};d['collections'][at]=r;old=r['fields'][n]
  if kind=='missing':del r['fields'][n]
  elif kind=='collection':d['collections'].remove(r)
  elif kind=='type':r['fields'][n]={**old,'type':'EA::Reflection::Boolean'}
  elif kind=='width':r['fields'][n]={**old,'data':old['data']+'cafebabe'}
  elif kind=='short':r['fields'][n]={**old,'data':'deadbeef'if f[3]=='words'else ''}
  elif kind=='nan':r['fields'][n]={**old,'data':'7fc01234'+(old['data'][8:]if f[3]=='words'else '')}
  elif kind=='inf':r['fields'][n]={**old,'data':'7f800000'+(old['data'][8:]if f[3]=='words'else '')}
  elif kind in('sample_nan','sample_inf','y_nan','y_inf'):
   at=(12 if kind.startswith('y_')else 4)*8;word='7fc01234'if kind.endswith('nan')else '7f800000';r['fields'][n]={**old,'data':old['data'][:at]+word+old['data'][at+8:]}
  else:raise AssertionError(kind)
 result=[];seen=set()
 for pos,f in enumerate(order):
  if f[:3]in seen:continue
  seen.add(f[:3])
  for kind in('missing','collection','type','width','short','nan','inf'):
   d=clone(data);mutate(d,f,kind);result.append(dict(label=f'{pos:02d}-{f[0]}-{f[1]}-{f[2]}-{kind}',data=d,success=f[3]=='words'and kind in('type','nan','inf'),first_position=pos))
  if f[3]=='words':
   for kind in('sample_nan','sample_inf','y_nan','y_inf'):
    d=clone(data);mutate(d,f,kind);result.append(dict(label=f'{pos:02d}-{f[0]}-{f[1]}-{f[2]}-{kind}',data=d,success=True,first_position=pos))
  later=next((j for j in range(pos+1,len(order))if order[j][:2]!=f[:2]),None)
  if later is not None:
   d=clone(data);mutate(d,f,'width');mutate(d,order[later],'width');result.append(dict(label=f'compound-{pos:02d}-before-{later:02d}',data=d,success=False,first_position=pos,second_position=later))
 return result

class Reader(air.Reader):
 def phases(self):
  assert self.word()==len(SECTIONS);v={};spans={}
  for name in SECTIONS:n=self.word();at=self.at;v[name]=self.take(n);spans[name]=[at,self.at]
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
 counts=Counter();errors=Counter();updates=solves=changed=partial=wall=launches=collision=ordinary=0;profiles=set()
 for rows,case in zip(frames,cases):
  for row,cmd in zip(rows,case['commands']):
   op=cmd[0];counts[OPS[op]]+=1;new=row['phase'];old=row['prior']['phase'];shared=row['shared'];before=row['prior']['shared'];s=new['slide_owner'];assert len(s)==180,len(s)
   if row['error']:errors[row['error']]+=1;partial+=new['ground_controllers']!=old['ground_controllers']or shared['roots']!=before['roots']or shared['bodies_blend']!=before['bodies_blend']
   if op==23 and row['error']is None:profiles.add(tuple(cmd[1:]))
   if op==4 and row['error']is None:
    updates+=1;wall+=s[4]!=0;changed+=shared['bodies_blend']!=before['bodies_blend']or shared['roots']!=before['roots']
    trace=air.foot.trajectory_observation(row['foot']['trajectory']);previous=air.foot.trajectory_observation(row['prior']['foot']['trajectory']);launches+=row['foot']['trajectory']!=row['prior']['foot']['trajectory']and s[4]!=0
    # Actual queue tags distinguish the replacement collision tail from four
    # ordinary forces. Source queue capacity may drop a complete later tail.
    q=new['forces'];n=q[0];tags=[q[1+7*k]for k in range(n)];collision+=15 in tags;ordinary+=4 in tags and 5 in tags
   if op==14 and row['error']is None:solves+=1
   if op==5:assert s[1]==bits(1)and list(s[2:5])==[0,0,0]
 assert len(profiles)==25 and updates>100 and solves>100 and changed>16
 assert ordinary>32 and collision>0 and any('BoardToolkit'in e for e in errors)and any('pumping physics mode 9'in e for e in errors)
 assert any('Invalid Slide surface mode 6'in e for e in errors)and any('selected SurfacePhysics'in e for e in errors)
 assert any('IntegerConversionUnavailable'in e for e in errors)
 assert wall>0 and launches>0,'Slide wall launch must use actual world probe and trajectory owners'
 assert any('Trajectory static grind provider was not registered'in e for e in errors),'Missing provider must fail inside the actual launched Slide continuation'
 return dict(operations=dict(counts),errors=dict(errors),profiles=len(profiles),successful_updates=updates,successful_solves=solves,physical_mutations=changed,partial_error_mutations=partial,wall_riding_updates=wall,trajectory_mutations_on_wall=launches,collision_force_tails=collision,ordinary_force_tails=ordinary)

def preflight(raw,cases):
 ranges=air.preflight(raw,cases)
 for u in UNITS:assert (CODE/(u+'.cpp')).is_file(),u
 return ranges

def build(output,target):
 original,observed,snapshot,report=prepare(output);crate=observed/'atelier-host';subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(crate/'Cargo.toml'),'--target-dir',str(target.resolve()),'--bin','slide-phase-runtime-reference'],check=True)
 reference=output/'slide-phase-runtime-reference';shutil.copy2(target.resolve()/'release/slide-phase-runtime-reference',reference);simulation=output/'slide-phase-runtime-simulation'
 subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'slide_phase_runtime_probe.cpp'),'-o',str(simulation)],check=True)
 for rel,sha in report['original_source_sha256'].items():assert digest(original/rel)==sha;raw=(original/rel).read_bytes();assert (observed/rel).read_bytes()[:len(raw)]==raw,rel
 for rel,row in report['staged_host_original_prefixes'].items():assert digest(crate/'src'/rel)==row['generated_sha256'],rel
 report.update(reference_binary_sha256=digest(reference),simulation_binary_sha256=digest(simulation));(output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');return simulation,reference

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in('assets','samples','output','target-dir'):p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 raw,cases=corpus();preflight(raw,cases);(out/'input.bin').write_bytes(raw);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');fixtures=loader_fixtures(a.assets.resolve())
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
 reports=[]
 for n,f in enumerate(fixtures):
  folder=out/'loader-fixtures'/f'{n:03d}-{f["label"]}';(folder/'private/stock').mkdir(parents=True,exist_ok=True);path=folder/'private/stock/skater-collections.json';path.write_text(json.dumps(f['data'])+'\n');bankfile=folder/'settings.simulation';bankfile.write_bytes(converter.encode_settings(path))
  ref=subprocess.check_output([str(reference),str(a.assets.resolve()),str(bank),str(folder)],input=b'');cpp=subprocess.check_output([str(simulation),*simulation_args,str(bankfile)],input=b'');(folder/'reference.bin').write_bytes(ref);(folder/'simulation.bin').write_bytes(cpp);assert ref==cpp,(f['label'],ref.hex(),cpp.hex());success=bool(struct.unpack_from('<I',ref)[0]);assert success==f['success'],f['label'];reports.append(dict(label=f['label'],success=success,sha256=hashlib.sha256(ref).hexdigest(),first_position=f['first_position']))
 result=dict(passed=True,reference_revision=REFERENCE_REVISION,cases=len(cases),commands=sum(len(c['commands'])for c in cases),bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),input_sha256=hashlib.sha256(raw).hexdigest(),coverage=covered,loader_fixtures=reports,scope='Complete unchanged active Slide host lifecycle/update/settings with concrete reckoning, skeleton Ground, both captures, original controllers/materials/force queue/collision response and real trajectory Launch/Update.',boundaries='Canonical processed/animation scalar producer packets and explicit initial board transforms/rates/external forces, authored pose choice and raw rails/world metadata remain upstream inputs. World hits, skeleton targets, IK/drives/body reactions/collision feedback and trajectory predictions are actual owners. Overall session/state selection/scoring/render publication remains root coordinator scope; no result or callback success is supplied.')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='loader_fixtures'},indent=2))
if __name__=='__main__':main()
