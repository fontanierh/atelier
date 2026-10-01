#!/usr/bin/env python3
"""Actual authored hierarchy, adjusted pose, retained world queries and complete FootIK/shared-body path.

Only the root scheduler runs this guarded compile. Original host owners and
all core numeric files stay byte-identical; forwarding observers expose private
loader values without rewriting them. Current processed gameplay fields and
engine triangles are explicit producer boundaries, not prerecorded pose input.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
import check_physical_simulation_runtime_parity as physical
from reference_build import build_probe, REFERENCE_REVISION
PLUGIN=physical.PLUGIN
OWN_UNITS=('SkeletonMotion','SkeletonBoardOffset','SkeletonLanding','AnimatedSkeleton','FootIkState','FootIkSolve','FootIk','SkeletonLineQueries','OffboardPoseAdjustment','GrindAir','GrindAirPoseAdjustment')
UNITS=physical.UNITS+OWN_UNITS+('CameraTracking','CameraWorld')
OPERATIONS=('tick','feet','reset_ik','refresh_offset','refresh_height','finish_ground','reset_motion','external_target','start_grind','replace_world','prediction','two_bone','geometry','owner_error')
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def f(v):return list(map(bits,v))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def corpus():
 rng=random.Random(0x82bdd630);records=[];cases=[]
 def affine(angle,height):
  import math
  c,s=math.cos(angle),math.sin(angle);return f([c,0,-s,0,1,0,s,0,c,0,height,0])
 def world(slope,holes=False):
  p=[(-3,-3*slope-.025,-3),(3,3*slope-.025,-3),(3,3*slope-.025,3),(-3,-3*slope-.025,3)]
  indices=((0,2,1),(0,3,2))[:1 if holes else 2];v=[len(indices)]
  for k,ids in enumerate(indices):v+=f([x for i in ids for x in p[i]])+[0,0x10,1 if k==0 else 12]
  return v
 def transform(angle=0,offset=(0,0,0)):
  import math
  c,s=math.cos(angle),math.sin(angle);return f([c,0,-s,0,0,1,0,0,s,0,c,0,*offset,0])
 def add(label,commands,seed=0):
  payload=affine(seed*.17,(.0,.06,.35,.8)[seed%4])+world((0,.12,-.12,.35)[seed%4])+[seed%2,len(commands)]+[x for c in commands for x in c]
  cases.append(dict(index=len(cases),label=label,commands=[c[0] for c in commands]));records.append(struct.pack('<'+'I'*len(payload),*payload))
 def tick(seed,k,grind=False):
  states=(201,202,702,503,500,601,602);state=states[(seed+k//3)%7];category=500 if state in (503,500) else 600 if state in(601,602) else 200
  filtered=(1,2,3,4,5,6)[(seed+k//4)%6]
  flags2468=(0x2000,0x42002000,0x1802000,0x40000)[(seed+k)%4]
  flags2472=(0,0x180,1,0x800)[(seed+k)%4]
  flags2476=(0,4,0x10000000,0x40000000)[(seed+k)%4]
  flags2480=(0,0x8000000,0x4000000)[(seed+k)%3]
  flags2484=(0,1<<20,1<<21)[(seed+k)%3]
  raw=[0,(seed+k//5)%4,bits((1/60,1/120,1/30)[seed%3]),state,category,filtered,flags2468,flags2472,flags2476,flags2480,flags2484,(seed+k)%3]
  raw+=f([.1 if k%3 else 0,.03*(k%3-1),.02*(k%4-1),.01*(k%8)])+[int(seed%5==0),int(k%4==0)]+f([.02,-.03,.01,0,.1*k])
  raw+=[int(grind)]
  assert len(raw)==24
  return raw
 for seed in range(72):
  commands=[]
  for k in range(18):
   if k==2:commands+=[[1,int(seed%3!=0)]]
   if k==4:commands+=[[4]+f([-.08,15.])]
   if k==6:commands+=[[3]+transform(.14,(.03,-.02,.05))]
   if k==8:commands+=[[9]+world(-.12 if seed%2 else .12,seed%4==0)]
   if k==10:commands+=[[5],[6]]
   if k==12:commands+=[[2]]
   if k==14:commands+=[[10]+f([.03,.04,-.02,0])]
   if k in(1,5,9,13):
    limb=(seed+k)%4;mode=(seed+k)%3
    commands+=[[7,limb,mode]+f([.25+.05*(seed%3),.1,.0,.2,0.,.8,.2,0.])]
   commands+=[tick(seed,k)]
  add('authored pose/world/IK/drive/body histories and 503/702 branches',commands,seed)
 for seed in range(24):
  target=[8]+f([-2,.0,0,0,2,.0,0,0])+[seed,0,1,0]+f([0,1,0,0,0,1,0,0,0,0,1,0,0,1,0,0])
  add('complete grind-air selection/prediction offsets with actual pose refresh',[target]+[tick(seed,k,True)for k in range(12)],seed)
 for budget in (0,1,2,3):
  for scale in (0,.0004,.5,1.,2.):
   for end in (.2,.7,1.2,3.):
    cmd=[11]+f([0,0,0,0,.3*scale,.4*scale,0,0,.6*scale,0,0,0,9,8,7,6,end,0,0,0,5,175])+[1,budget]
    add('two-bone reachable, limited, extended, degenerate and recursion writes',[cmd])
 for seed in range(48):
  parents=[0xffffffff if n==0 else n-1 for n in range(24)]
  if seed%6==1:parents[0]=0
  if seed%6==2:parents[9]=24
  if seed%6==3:parents[13]=14;parents[14]=13
  if seed%6==4:parents=[0xffffffff]*24
  frames=[]
  for n in range(24):
   m=transform(.02*(n+seed),(.01*n,-.04*n,.003*n))
   if seed%6==5:m[0]=bits(1.05);m[5]=bits(.95);m[8]=bits(.06)
   frames+=m
  add('physical ancestor validation and nonorthogonal original cofactor inverse',[[12]+parents+frames])
 for mode in range(11):
  add('actual owner loader/pose/IK/offboard/grind error with retained partial state',[[13,mode]])
 return struct.pack('<I',len(records))+b''.join(records),cases

def aliases():
 result=physical.aliases()
 for n in ('animated_skeleton','foot_ik','foot_ik_queries','skeleton_grind_air','grind_air_settings'):
  result[f'atelier-host/src/physics/pose-host/{n}.rs']=f'crates/skate-host/src/physics/{n}.rs'
 result['atelier-host/src/physics/pose-host/offboard_pose_adjust.rs']='crates/skate-host/src/physics/offboard/pose_adjust.rs'
 return result

def prepare_oracle(probe):
 # The physical facade's nominal Animated record is replaced by the real
 # unchanged host owner. No original numeric module is patched.
 original=(PLUGIN/'Tests/Reference/physical_simulation_runtime_probe.rs').read_text().split('fn main(){',1)[0]
 line=next(line for line in original.splitlines()if line.startswith(' pub struct Animated{'))
 # Inline the complete byte-identical original host modules so forwarding
 # observers share their privacy scope. Textual inclusion preserves the original
 # inner module documentation; Rust include! would reject those inner docs.
 frozen={}
 for name in ('animated_skeleton','foot_ik'):
  source=PLUGIN/f'ThirdParty/skate-runtime/crates/skate-host/src/physics/{name}.rs'
  root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip())
  relative=source.relative_to(root).as_posix()
  raw=subprocess.check_output(['git','show',f'{REFERENCE_REVISION}:{relative}'],cwd=root)
  assert raw==source.read_bytes(),f'{name} differs from frozen source'
  frozen[name]=raw.decode()
 module=' pub mod animated_skeleton{\n'+frozen['animated_skeleton']+\
  '\npub fn observer(a:&AnimatedSkeleton)->(&PointGraph<8>,&[usize;4],&LandingSettings){(&a.landing_on_board_blend,&a.target_bones,&a.landing_settings)}pub fn replace_target(a:&mut AnimatedSkeleton,v:usize)->usize{std::mem::replace(&mut a.target_bones[0],v)}\n}\n'+\
  ' pub(crate) use animated_skeleton::AnimatedSkeleton as Animated;\n pub mod foot_ik{\n'+frozen['foot_ik']+\
  '\npub fn observer(f:&FootIk)->(Geometry,Settings,SettingsPost,[usize;24]){(f.geometry.clone(),f.settings,f.post_settings,f.bone_indices)}\n}\n'+\
  ' #[path="pose-host/foot_ik_queries.rs"]pub mod foot_ik_queries;\n #[path="pose-host/offboard_pose_adjust.rs"]pub mod offboard_pose_adjust;\n #[path="pose-host/skeleton_grind_air.rs"]pub mod skeleton_grind_air;\n #[path="pose-host/grind_air_settings.rs"]pub mod grind_air_settings;\n'+\
  ' pub fn pose_grind_settings(d:&skate_data::collections::Collections)->Result<skate_core::physics::grind_air::Settings,String>{grind_air_settings::load(d)}\n'+\
  ' pub fn pose_grind_update(g:&mut skate_core::physics::grind_air::GrindAir,c:&skate_core::physics::grind_air::Settings,b:AnimationPartTransform,p:&skate_core::player::input_phase::ProcessedPhysicsInput,a:&mut Animated,m:&[AnimationPartTransform])->Result<bool,String>{skeleton_grind_air::update(g,c,b,p,a,m)}'
 original=original.replace(line,module)
 record='physics::Animated{roots,board_frames,record:Default::default(),bone_indices,physics_frames}'
 original=original.replace('let s=SkaterRuntime{','let mut animated=physics::Animated::load(assets,data,&e.frames,false).unwrap();animated.roots=roots;animated.board_frames=board_frames;let s=SkaterRuntime{').replace(record,'animated')
 assert record not in original
 return original+probe.read_text()

def build(output,target_dir):
 native=PLUGIN/'Source/AtelierSkate/Private/Native';snapshot=output/'native-source'
 if snapshot.exists():shutil.rmtree(snapshot)
 snapshot.mkdir()
 for p in sorted(native.glob('*.h')):shutil.copy2(p,snapshot/p.name)
 for n in UNITS:shutil.copy2(native/f'{n}.cpp',snapshot/f'{n}.cpp')
 names=('body','collision','constraint');cpp_prefixes=[PLUGIN/f'Tests/Native/skeleton_{n}_probe.cpp'for n in names]
 cpp_probe=PLUGIN/'Tests/Native/adjusted_skeleton_probe.cpp';physical_cpp=PLUGIN/'Tests/Native/physical_simulation_runtime_probe.cpp';combined=snapshot/cpp_probe.name
 combined.write_text('#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wunused-function"\n'+''.join(p.read_text().split('int main()',1)[0]for p in cpp_prefixes)+physical_cpp.read_text().split('int main(',1)[0]+'\n#pragma clang diagnostic pop\n'+cpp_probe.read_text())
 cpp=output/'adjusted-skeleton-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{n}.cpp')for n in UNITS],str(combined),'-o',str(cpp)],check=True)
 rust_prefixes=[PLUGIN/f'Tests/Reference/skeleton_{n}_probe.rs'for n in names];rust_probe=PLUGIN/'Tests/Reference/adjusted_skeleton_probe.rs'
 prefix=''.join(p.read_text().split('fn main(){',1)[0]for p in rust_prefixes).replace('use crate::{','use skate_core::{').replace('skeleton_root::inverse_rigid,','').replace('solver::{packed,JointConstraint}','solver::{JointConstraint}').replace('#[path="physics/solver/packing.rs"] mod skeleton_constraint_packing;','mod skeleton_constraint_packing{use skate_core::physics::solver::{packed,JointConstraint};use crate::{RetailDriveRows,RetailContactJacobian};use skate_core::physics::rigid_body::RetailReactionCorrections;#[path="packing.rs"]mod original;pub fn drive(r:&RetailDriveRows)->packed::Drive{original::drive(r)}}')
 generated=output/'adjusted-skeleton-combined.rs';generated.write_text(prefix+prepare_oracle(rust_probe));reference=build_probe(output,'adjusted-skeleton-reference',generated,target_dir,bevy=True,extra_sources=aliases())
 (output/'native-provenance.json').write_text(json.dumps(dict(source_sha256={p.name:digest(p)for p in snapshot.iterdir()},probe_sha256={p.name:digest(p)for p in (*cpp_prefixes,cpp_probe,physical_cpp,*rust_prefixes,rust_probe)}),indent=2)+'\n');return cpp,reference

def preflight():
 data,cases=corpus();w=struct.unpack('<'+'I'*(len(data)//4),data);at=1
 def world():
  nonlocal at
  n=w[at];at+=1+12*n
 for c in cases:
  at+=12;world();at+=1;n=w[at];at+=1;assert n==len(c['commands'])
  for op in c['commands']:
   assert w[at]==op,(c['index'],op,at);at+=1
   if op==9:world()
   else:at+={0:23,1:1,2:0,3:16,4:2,5:0,6:0,7:10,8:28,10:4,11:24,12:408,13:1}[op]
 assert at==len(w),(at,len(w))
 for n in UNITS:assert (PLUGIN/f'Source/AtelierSkate/Private/Native/{n}.cpp').is_file(),n
 for n in aliases().values():assert (PLUGIN/'ThirdParty/skate-runtime'/n).is_file(),n
 return data,cases

def decode(raw,cases):
 w=struct.unpack('<'+'I'*(len(raw)//4),raw);at=0;coverage=Counter()
 for c in cases:
  index,n,size=w[at:at+3];assert index==c['index']and n==len(c['commands']);c['first_output_word']=at;c['output_words']=size+3;cursor=at+3;initial=w[cursor];cursor+=1+initial;c['outputs']=[]
  for op in c['commands']:
   assert w[cursor]==op;length=w[cursor+1];c['outputs'].append(dict(operation=OPERATIONS[op],first_output_word=cursor,output_words=length+2));coverage[OPERATIONS[op]]+=1;cursor+=length+2
  assert cursor==at+size+3;(at:=cursor)
 assert at==len(w)
 return dict(coverage)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--samples',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);p.add_argument('--preflight',action='store_true');a=p.parse_args();o=a.output.resolve();o.mkdir(parents=True,exist_ok=True);inputs,cases=preflight();(o/'input.bin').write_bytes(inputs)
 if a.preflight:print(json.dumps(dict(streams=len(cases),commands=sum(len(c['commands'])for c in cases),ticks=sum(c['commands'].count(0)for c in cases),input_bytes=len(inputs),units=len(UNITS),aliases=len(aliases())),indent=2));return
 stock=a.assets.resolve()/'private/stock';settings=o/'settings.native';physical_file=o/'physics.native';settings.write_bytes(physical.converter.encode_settings(stock/'skater-collections.json'));physical_file.write_bytes(physical.converter.encode_physics_skeletons(stock/'physics-skeletons.json'));identity=json.loads((stock/'physics-skeletons.json').read_text())['source_sha256']
 cpp,reference=build(o,a.target_dir);expected=subprocess.check_output([str(reference),str(a.assets.resolve())],input=inputs);actual=subprocess.check_output([str(cpp),str(settings),str(physical_file),str(a.samples.resolve()/'native/rig.skate'),identity],input=inputs)
 (o/'reference.bin').write_bytes(expected);(o/'cpp.bin').write_bytes(actual);coverage=decode(expected,cases);(o/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
 if expected!=actual:
  first=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)))//4;c=next((c for c in cases if c['first_output_word']<=first<c['first_output_word']+c['output_words']),None);command=next((x for x in c['outputs']if x['first_output_word']<=first<x['first_output_word']+x['output_words']),None)if c else None
  report=dict(passed=False,first_word=first,case=c,command=command,reference_bytes=len(expected),cpp_bytes=len(actual));(o/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
 result=dict(passed=True,streams=len(cases),exact_words=len(expected)//4,coverage=coverage,input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),comparison='Complete source authored hierarchy→offset/landing/COM→world foot queries→all FootIK stages→shared body solve→post-IK physical setters and final owner histories; full numeric source unchanged, no tolerance',limitations='Gameplay processed scalar/flag requests, external IK target events, selected GrindAir target/orientation and engine triangles are explicit upstream fixtures. Full lifecycle dispatcher, Wipeout/FootPhysical/render output remains separately owned; pose hierarchy, contacts, IK, drives and bodies are produced live.')
 (o/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
