#!/usr/bin/env python3
"""Whole original Biped Ground/Air skeleton updates with actual shared pose/IK/body owners.

External processed flags/attributes, engine triangles and the incoming Biped
controller/trajectory frame are explicit producer boundaries. Pose, COM, world
contacts, target/drives, reckoning and physical solve are computed live. Only
root may compile/execute. --preflight performs source/transport checks only.
"""
import argparse
from collections import Counter
import copy,hashlib,json,math,shutil,struct,subprocess
from pathlib import Path
import check_skeleton_input_runtime_parity as dispatcher
import check_physical_simulation_runtime_parity as physical
import check_physics_animation_input_parity as animation_input
from check_animation_playback_parity import attribute
from check_gesture_parity import converter
from camera_reference_build import frozen_sources
PLUGIN=dispatcher.PLUGIN;CODE=PLUGIN/'Source/AtelierSkate/Private/Simulation';HOST='crates/skate-host/src/physics/'
OWN=('SkeletonBiped','SkeletonBipedGround','SkeletonBipedAir','SkeletonBipedReckoning')
UNITS=tuple(dict.fromkeys(dispatcher.UNITS+('BodySpin','BodyFlip','AirReckoning','BoardAnimation','SkeletonAirFrames','SkeletonAirRuntime','BipedGroundState','BipedGroundInput','BipedGroundJob')+tuple(n for n in OWN if(CODE/(n+'.cpp')).exists())+tuple(__import__('check_biped_ground_state_parity').UNITS)))
STATE_OBSERVER='''
pub(super) fn migration_observe(out:&mut Vec<u32>,s:&State){crate::probe_matrix(out,s.retained_board);crate::probe_floats(out,s.ground_normal_smoothing);for g in [&s.tilt_vs_rotation,&s.tilt_vs_slope]{crate::probe_floats(out,g.x);crate::probe_floats(out,g.y);}}
pub(super) fn migration_fixture_default()->State{State{retained_board:IDENTITY,ground_normal_smoothing:[0.;4],tilt_vs_rotation:PointGraph{x:[0.;8],y:[0.;8]},tilt_vs_slope:PointGraph{x:[0.;8],y:[0.;8]}}}
pub(super) fn migration_update(s:&State,riding:&mut RidingOutputs,air:&mut AirReckoning,input:ground_reckoning::Input)->ground_reckoning::Output{ground_reckoning::update(&mut riding.reckoning,&mut riding.reckoning_frames,&mut riding.body_spin,&mut air.state,ground_reckoning::Settings{ground_normal_smoothing:s.ground_normal_smoothing,tilt_vs_rotation:&s.tilt_vs_rotation,tilt_vs_slope:&s.tilt_vs_slope},input)}
impl State{pub(crate) fn migration_reckoning_settings(&self)->State{State{retained_board:IDENTITY,ground_normal_smoothing:self.ground_normal_smoothing,tilt_vs_rotation:self.tilt_vs_rotation,tilt_vs_slope:self.tilt_vs_slope}}}
'''
GROUND_OBSERVER='''
pub(crate) fn migration_observe(out:&mut Vec<u32>,s:&State){state::migration_observe(out,s)}
pub(crate) fn migration_fixture_default()->State{state::migration_fixture_default()}
pub(crate) fn migration_update(s:&State,riding:&mut crate::physics::riding_outputs::RidingOutputs,air:&mut crate::physics::air_reckoning::AirReckoning,input:skate_core::player::offboard::ground_reckoning::Input)->skate_core::player::offboard::ground_reckoning::Output{state::migration_update(s,riding,air,input)}
pub(crate) fn migration_set_board(s:&mut State,frame:Transform){s.retained_board=frame;}
'''
AIR_OBSERVER='''
pub(crate) fn migration_biped_observe(out:&mut Vec<u32>,s:&AirReckoning){let a=&s.state;crate::probe_floats(out,[a.spin_angle,a.spin_speed,a.secondary_lean_angle,a.flip_angle,a.flip_speed,a.flip_requested_speed]);crate::probe_matrix(out,a.spin_transform);crate::probe_floats(out,a.flip_axis);out.extend([a.flip_active as u32,a.flip_side as u32]);}
pub(crate) fn migration_biped_settings(out:&mut Vec<u32>,s:&AirReckoning){let p=&s.settings;crate::probe_floats(out,p.ground_normal_smoothing);for g in [&p.max_up_angle_delta,&p.tilt_vs_rotation,&p.tilt_vs_slope]{crate::probe_floats(out,g.x);crate::probe_floats(out,g.y);}crate::probe_floats(out,[p.body_spin.derivative_floor,p.body_spin.acceleration_limit]);for g in &p.body_spin.curves{crate::probe_floats(out,g.x);crate::probe_floats(out,g.y);}crate::probe_floats(out,p.body_spin.input_fade_threshold);for v in [p.body_flip.smoothing,p.body_flip.maximum_speed,p.body_flip.spin_scale]{out.push(v.is_some()as u32);if let Some(v)=v{out.push(v.to_bits());}}out.push(p.body_flip.missing_attribute_value.to_bits());for m in s.modes{out.extend([m.easy_body_spins as u32,m.perfect_body_flips as u32]);}for g in s.stock_spin_curves{crate::probe_floats(out,g.x);crate::probe_floats(out,g.y);}out.push(s.stock_spin_acceleration.to_bits());}
'''
BOARD_OBSERVER='''
pub(crate) fn migration_biped_observe(out:&mut Vec<u32>,s:&SkeletonAir){crate::probe_floats(out,s.board_animation.rotation_error);out.push(s.board_animation.blending as u32);for g in [&s.settings.slow,&s.settings.fast]{crate::probe_floats(out,g.x);crate::probe_floats(out,g.y);}}
'''
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def source(p):return dispatcher.source(p)
def aliases():
 a=dispatcher.aliases()
 for n in ('skeleton_air.rs','air_reckoning.rs','air_reckoning/settings.rs','offboard/skeleton_ground.rs','offboard/skeleton_ground/frames.rs','offboard/skeleton_ground/state.rs','offboard/skeleton_air.rs'):a['atelier-host/src/physics/'+n]=HOST+n
 return a

def prepare(out):
 n=out/'simulation-source'
 if n.exists():shutil.rmtree(n)
 n.mkdir()
 for p in CODE.glob('*.h'):shutil.copy2(p,n/p.name)
 for u in UNITS:shutil.copy2(CODE/(u+'.cpp'),n/(u+'.cpp'))
 prefixes=[PLUGIN/f'Tests/Simulation/skeleton_{v}_probe.cpp'for v in('body','collision','constraint')]+[PLUGIN/'Tests/Simulation/physical_simulation_runtime_probe.cpp',PLUGIN/'Tests/Simulation/adjusted_skeleton_probe.cpp',PLUGIN/'Tests/Simulation/skeleton_input_runtime_probe.cpp']
 cpp_helpers,_=dispatcher.helpers();prefix=''.join(p.read_text().split('int main(',1)[0].split('int main()',1)[0]for p in prefixes).replace('// GENERATED_PROTOCOL',cpp_helpers);probe=n/'biped_skeleton_probe.cpp';probe.write_text('#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wunused-function"\n'+prefix+'\n#pragma clang diagnostic pop\n'+(PLUGIN/'Tests/Simulation/biped_skeleton_probe.cpp').read_text())
 rust_prefixes=[PLUGIN/f'Tests/Reference/skeleton_{v}_probe.rs'for v in('body','collision','constraint')];prefix=''.join(p.read_text().split('fn main(){',1)[0]for p in rust_prefixes).replace('use crate::{','use skate_core::{').replace('skeleton_root::inverse_rigid,','').replace('solver::{packed,JointConstraint}','solver::{JointConstraint}').replace('#[path="physics/solver/packing.rs"] mod skeleton_constraint_packing;','mod skeleton_constraint_packing{use skate_core::physics::solver::{packed,JointConstraint};use crate::{RetailDriveRows,RetailContactJacobian};use skate_core::physics::rigid_body::RetailReactionCorrections;#[path="packing.rs"]mod original;pub fn drive(r:&RetailDriveRows)->packed::Drive{original::drive(r)}}')
 base=dispatcher.prepare_oracle(PLUGIN/'Tests/Reference/skeleton_input_runtime_probe.rs').split('fn main(){',1)[0]
 base=base.replace(' pub struct PlayerInput{',' pub(crate) mod skeleton_air;pub(crate) mod air_reckoning;\n pub struct PlayerInput{').replace(' pub mod offboard{',' pub mod offboard{pub(crate) mod skeleton_ground;pub(crate) mod skeleton_air;')
 reference=out/'biped-skeleton-reference.rs';reference.write_text(prefix+base+(PLUGIN/'Tests/Reference/biped_skeleton_probe.rs').read_text())
 frozen,report=frozen_sources(out);observed=out/'observed-source'
 if observed.exists():shutil.rmtree(observed)
 shutil.copytree(frozen,observed);appends={'atelier-host/src/physics/offboard/skeleton_ground/state.rs':STATE_OBSERVER,'atelier-host/src/physics/offboard/skeleton_ground.rs':GROUND_OBSERVER,'atelier-host/src/physics/skeleton_air.rs':BOARD_OBSERVER,'atelier-host/src/physics/air_reckoning.rs':AIR_OBSERVER}
 staged={}
 for destination,origin in aliases().items():
  p=observed/destination;raw=(frozen/origin).read_bytes();append=appends.get(destination,'').encode();assert not p.exists(),destination;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw+append);assert p.read_bytes()[:len(raw)]==raw;staged[destination]=dict(source=origin,original_prefix_bytes=len(raw),original_prefix_sha256=hashlib.sha256(raw).hexdigest(),append_sha256=hashlib.sha256(append).hexdigest(),generated_sha256=digest(p))
 report.update(staged_module_aliases=staged,simulation_source_sha256={p.name:digest(p)for p in n.iterdir()},probe_sha256={p.name:digest(p)for p in prefixes+rust_prefixes+[PLUGIN/'Tests/Simulation/biped_skeleton_probe.cpp',PLUGIN/'Tests/Reference/biped_skeleton_probe.rs']},boundary=__doc__,callback_transport='Ground callback captures only unchanged immutable reckoning settings and the processed/physical-spin input values. It invokes original State::finish_reckoning on the actual shared riding/air/body-spin owners; original retained_board is mutated only by actual update_biped_ground. No neutral service or completed pose/query result is supplied.')
 (out/'simulation-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return probe,n,reference,observed,report

def corpus():
 bits=physical.bits;fs=physical.floats;cases=[];programs=[]
 def world(seed):
  slope=(0,.12,-.12,.35)[seed%4];p=[(-4,-4*slope-.025,-4),(4,4*slope-.025,-4),(4,4*slope-.025,4),(-4,-4*slope-.025,4)];v=[2]
  for ids,tag in(((0,2,1),1),((0,3,2),12)):v+=fs([x for j in ids for x in p[j]])+[0,0x10,tag]
  return v
 def matrix(seed,height=0):
  a=seed*.0317;c,s=math.cos(a),math.sin(a);return [[c,0,-s,0],[0,1,0,0],[s,0,c,0],[.137,height,.317,-.0]]
 def attrs(seed,k):
  values=[]
  for name,value in [('BodySpin',(-.7,0,.7)[(seed+k)%3]),('Turn',(.0,.137)[k%2]),('Balance',(-.317,0,.317)[(seed+k)%3])]:
   a=attribute(kind=0,status=5);a['name']=animation_input.trees.name(name);a['payload']=[bits(value),None,None,None,None,None];values.append(a)
  return values
 def encoded_attrs(values):
  out=[]
  for a in values:
   out+=a['name']+[a['kind'],a['status'],a['sequence']&0xffffffff,a['begin'],a['end']]
   for p in a['payload']:out+=[p is not None]+([p]if p is not None else [])
  return list(map(int,out))
 def tick(seed,k,branch,*,missing_process=False,missing_update=False,solve=True):
  a=attrs(seed,k);pose=(seed+k//4)%4;state=500 if branch==0 else 501
  raw=[0,4 if missing_process else pose,bits((1/60,1/120,1/30)[seed%3]),state,500,(1,2,3,6)[(seed+k)%4],(0x2000,0x102000,0x42002000)[(seed+k)%3],(0,0x180,0x400)[k%3],4 if(seed+k)%2 else 0,(0,0x8000)[k%2],(0,1,0x100000)[(seed+k)%3],0,(0,0x08800000)[k%2],int(k%5==0),len(a)]+encoded_attrs(a)+fs([(.137 if j==seed%18 else -.0)for j in range(18)])+[3,0]
  # Consumed source controller/trajectory and target fields, not pose outputs.
  raw+=[branch]+fs(sum(matrix(seed+k,(.0,.04,.3)[k%3]),[]))+fs([.137,(.6,1.3,2)[k%3],.317,-.0])+fs([.137,1.2,.317,0])+[bits((.0,.02,.24)[(seed+k)%3])]+fs([.137,0,.991,-.0])+[4 if missing_update else pose,int(solve)]
  return raw,dict(operation=0,branch=branch,solve=solve,missing_process=missing_process,missing_update=missing_update)
 for seed in range(72):
  commands=[];specs=[]
  for k in range(16):
   if k%6==0:
    commands.append([8]+fs([.137*seed,-.317,.731]));specs.append(dict(operation=8));commands.append([7]+fs([0,1,0,(-.0,.137)[seed%2]])+fs(([0,1,0,.137],[0,-1,0,.731],[0,0,0,-.0])[(seed+k)%3])+fs([.137,0,.991,-.0])+[bits((0,.5,1,1.7)[(seed+k)%4]),seed%2,int(k%2),bits(.317)]);specs.append(dict(operation=7))
   if k in(2,7):commands.append([1]+fs(sum(matrix(seed+k,.017),[])));specs.append(dict(operation=1))
   if k==5:commands.append([3]+fs(sum(matrix(seed+31,.317),[])));specs.append(dict(operation=3))
   if k==9:commands.append([4]+world(seed+1));specs.append(dict(operation=4))
   if k==11:commands.append([2]);specs.append(dict(operation=2))
   if k==13:commands.append([5]);specs.append(dict(operation=5))
   command,spec=tick(seed,k,(seed+k//3)%2);commands.append(command);specs.append(spec)
  programs.append((seed,commands,specs,'full actual pose/IK/roots/shared solve, Ground/Air switch, blend capture/reset and retained16016'))
 for seed in range(12):
  commands=[];specs=[]
  for k in range(6):
   c,s=tick(seed,k,seed%2,missing_process=k==2,missing_update=k==3,solve=k not in(2,3));commands.append(c);specs.append(s)
  programs.append((seed,commands,specs,'missing hierarchy before ProcessData and after original root/board mutation; recovery'))
 for seed in range(8):
  commands=[[6,(0x02,0x07,0x12,0x17)[seed%4],23]];specs=[dict(operation=6)]
  for k in range(8):c,s=tick(seed,k,(seed+k)%2);commands.append(c);specs.append(s)
  programs.append((seed,commands,specs,'actual sleeping bodies, reenabling histories and phase switching'))
 payload=[len(programs)]
 for index,(seed,commands,specs,label)in enumerate(programs):
  a=seed*.17;c,s=math.cos(a),math.sin(a);payload+=fs([c,0,-s,0,1,0,s,0,c,0,(.0,.06,.35,.8)[seed%4],0])+world(seed)+[seed%2,len(commands)]+sum(commands,[]);cases.append(dict(index=index,label=label,commands=[c[0]for c in commands],command_inputs=specs))
 return struct.pack('<'+'I'*len(payload),*payload),cases

def audit(raw,cases):
 words=struct.unpack('<'+'I'*(len(raw)//4),raw);at=1
 def world():
  nonlocal at
  n=words[at];at+=1+12*n
 assert words[0]==len(cases)
 for c in cases:
  at+=12;world();at+=1;assert words[at]==len(c['commands']);at+=1
  for op in c['commands']:
   assert words[at]==op;at+=1
   if op==0:
    at+=13;n=words[at];at+=1
    for _ in range(n):
     at+=10
     for _ in range(6):present=words[at];at+=1+bool(present)
    at+=20;assert words[at]in(0,1);at+=32
   elif op in(1,3):at+=16
   elif op==4:world()
   elif op==6:at+=2
   elif op==7:at+=16
   elif op==8:at+=3
   else:assert op in(2,5)
 assert at==len(words),(at,len(words))

def variants(out,assets):
 data=json.loads((assets/'private/stock/skater-collections.json').read_text());fixtures=[];names=('GroundNormalSmoothing','TiltVsRotGround','TiltVsSlopeGround')
 def field(d,name):
  key='default'
  for _ in range(len(d['collections'])+1):
   record=next(r for r in d['collections']if converter.name_id(r['class'])==converter.name_id('physics_reckoning')and converter.name_id(r['key'])==converter.name_id(key));n=next((n for n in record['fields']if converter.name_id(n)==converter.name_id(name)),None)
   if n is not None:return record['fields'],n
   key=record['parent'];assert key
  raise AssertionError('cycle')
 def absent(d,name):
  for r in d['collections']:
   if converter.name_id(r['class'])==converter.name_id('physics_reckoning'):
    for n in list(r['fields']):
     if converter.name_id(n)==converter.name_id(name):del r['fields'][n]
 for index,name in enumerate(names):
  for failure in('missing','width-short','width-long','nonfinite-valid','reflection-type-valid'):
   d=copy.deepcopy(data)
   if failure=='missing':absent(d,name)
   else:
    fields,n=field(d,name)
    if failure=='width-short':fields[n]['data']=fields[n]['data'][:-8]
    elif failure=='width-long':fields[n]['data']+='DEADBEEF'
    elif failure=='nonfinite-valid':fields[n]['data']='7FC12345'+fields[n]['data'][8:]
    else:fields[n]['type']='EA::Reflection::Bool'
   fixtures.append((name+'-'+failure,d,failure.endswith('valid')))
  if index+1<len(names):
   d=copy.deepcopy(data);absent(d,name);fields,n=field(d,names[index+1]);fields[n]['data']='DEADBEEF';fixtures.append((name+'-before-malformed-'+names[index+1],d,False))
 d=copy.deepcopy(data);d['collections']=[r for r in d['collections']if converter.name_id(r['class'])!=converter.name_id('physics_reckoning')];fixtures.append(('missing-collection',d,False));result=[]
 for label,d,success in fixtures:
  folder=out/'asset-fixtures'/label/'private/stock';folder.mkdir(parents=True,exist_ok=True);p=folder/'skater-collections.json';p.write_text(json.dumps(d));bank=folder.parents[1]/'settings.simulation';bank.write_bytes(converter.encode_settings(p));result.append(dict(label=label,bank=bank,assets=folder.parents[1],success=success))
 return result

def build_reference(out,target,generated,observed,report):
 crate=observed/'atelier-host';cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text()+'\nskate-core={path="../crates/skate-core"}\nskate-data={path="../crates/skate-data"}\nbevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}\n[[bin]]\nname="biped-skeleton-reference"\npath="src/migration_probe.rs"\n');shutil.copy2(generated,crate/'src/migration_probe.rs');subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(cargo),'--target-dir',str(target.resolve()),'--bin','biped-skeleton-reference'],check=True)
 for relative,expected in report['original_source_sha256'].items():assert digest(observed/relative)==expected,relative
 for relative,info in report['staged_module_aliases'].items():assert digest(observed/relative)==info['generated_sha256'],relative
 binary=out/'biped-skeleton-reference';shutil.copy2(target.resolve()/'release/biped-skeleton-reference',binary);return binary

def decode(raw,cases):
 w=struct.unpack('<'+'I'*(len(raw)//4),raw);assert w[0]==1;at=54+w[1];assert w[at]==len(cases);at+=1;coverage=Counter()
 for c in cases:
  assert w[at:at+2]==(c['index'],len(c['commands']));end=at+3+w[at+2];cur=at+3;cur+=1+w[cur];rows=[]
  for spec in c['command_inputs']:
   op=spec['operation'];assert w[cur]==op;length=w[cur+1];payload=w[cur+2];assert payload<length;row=dict(operation=op,first_word=cur,words=length+2,payload_words=payload);coverage['op'+str(op)]+=1
   if op==0:
    prepared=bool(w[cur+3]);row['process_success']=prepared;coverage['process_success'if prepared else'process_failure']+=1;row['branch']=spec['branch'];coverage['ground'if spec['branch']==0 else'air']+=1
    cursor=cur+4;process_status=w[cursor];message_count=w[cursor+1];assert bool(process_status)==prepared;cursor+=2+message_count;target_at=cur+3+payload-16;possible=[]
    for solved_words in(0,6):
     status_at=cursor+solved_words
     if status_at+2<=target_at and w[status_at]in(0,1) and status_at+2+w[status_at+1]==target_at:possible.append((status_at,solved_words))
    assert len(possible)==1,(c['index'],spec,possible,payload)
    status_at,solved_words=possible[0];success=bool(w[status_at]);row['update_success']=success;row['error']=''.join(chr(v)for v in w[status_at+2:target_at]);coverage['update_success'if success else'update_failure']+=1
    if solved_words:
     assert prepared and spec['solve'];row['actual_contact_rows']=w[cursor];row['actual_drive_rows']=w[cursor+1];coverage['actual_solves']+=1;coverage['actual_contact_rows']+=w[cursor];coverage['actual_drive_rows']+=w[cursor+1]
    row['has_failure_input']=spec['missing_process']or spec['missing_update'];coverage['explicit_failure_inputs']+=row['has_failure_input']
   rows.append(row);cur+=length+2
  assert cur==end,(c['index'],cur,end);c['outputs']=rows;at=end
 assert at==len(w);assert coverage['process_success']and coverage['process_failure']and coverage['ground']and coverage['air']and coverage['actual_solves'] and coverage['actual_contact_rows'] and coverage['actual_drive_rows'] and coverage['update_failure'];assert all(coverage['op'+str(n)]for n in range(9));return dict(coverage)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',required=True,type=Path);p.add_argument('--samples',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--target-dir',required=True,type=Path);p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);raw,cases=corpus();audit(raw,cases);(out/'input.bin').write_bytes(raw);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');probe,n,generated,observed,report=prepare(out);fixtures=variants(out,a.assets.resolve());bank=out/'settings.simulation';bank.write_bytes(converter.encode_settings(a.assets.resolve()/'private/stock/skater-collections.json'));phys=out/'physical.simulation';phys.write_bytes(converter.encode_physics_skeletons(a.assets.resolve()/'private/stock/physics-skeletons.json'));identity=json.loads((a.assets.resolve()/'private/stock/physics-skeletons.json').read_text())['source_sha256'];summary=dict(histories=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(raw),input_sha256=hashlib.sha256(raw).hexdigest(),loader_fixture_count=len(fixtures),units=UNITS)
 if a.preflight:print(json.dumps(summary,indent=2));return
 simulation=out/'biped-skeleton-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(n),*[str(n/(u+'.cpp'))for u in UNITS],str(probe),'-o',str(simulation)],check=True);reference=build_reference(out,a.target_dir,generated,observed,report);expected=subprocess.check_output([str(reference),str(a.assets.resolve())],input=raw);actual=subprocess.check_output([str(simulation),str(bank),str(phys),str(a.samples.resolve()/'simulation/rig.skate'),identity],input=raw);(out/'reference.bin').write_bytes(expected);(out/'cpp.bin').write_bytes(actual)
 if expected!=actual:
  first=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)))//4;divergence=dict(first_word=first,reference_bytes=len(expected),cpp_bytes=len(actual));(out/'first-divergence.json').write_text(json.dumps(divergence,indent=2)+'\n');raise AssertionError(divergence)
 coverage=decode(expected,cases);loader=[]
 for f in fixtures:
  ref=subprocess.check_output([str(reference),str(f['assets']),'--load-only']);cpp=subprocess.check_output([str(simulation),str(f['bank']),'--load-only']);assert ref==cpp,f['label'];assert bool(struct.unpack_from('<I',ref)[0])==f['success'],f['label'];loader.append(dict(label=f['label'],success=f['success'],exact_words=len(ref)//4))
 result=dict(passed=True,**summary,stock_exact_words=len(expected)//4,output_sha256=hashlib.sha256(expected).hexdigest(),coverage=coverage,loader_fixtures=loader,limitations=__doc__);(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
