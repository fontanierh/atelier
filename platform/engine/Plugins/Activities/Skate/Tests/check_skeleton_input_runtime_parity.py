#!/usr/bin/env python3
"""Complete original ProcessData/GeneralUpdate/Ground/Teleport/reset proof.

Builds and executions are reserved for the coordinator's guarded job. Physical
owners, stock pose hierarchy and collision feedback are produced live. Ordered
attributes, action-map values, processed flags and world triangles are explicit
external producer inputs.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import struct
import subprocess
import check_adjusted_skeleton_parity as adjusted
import check_physics_animation_input_parity as animation_input
import player_input_protocol as protocol
from check_animation_playback_parity import Stream,attribute
from reference_build import build_probe
PLUGIN=adjusted.PLUGIN
UNITS=adjusted.UNITS+('StockSettingsReader','PlayerInputTypes','WipeoutOrientation','SkeletonAttributeDispatch','PhysicsAnimationInput','SkeletonInputRuntime','SkeletonWobble')
OPERATIONS=('process_and_update','reset_teleport','trigger_wobble','seed_lifecycle','external_ik','grind_target','replace_world','finish_attributes','select_mode','seed_sleeping_bodies')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def source(path):
 root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip())
 p=PLUGIN/'ThirdParty/skate-runtime'/path
 raw=subprocess.check_output(['git','show',f'{adjusted.REFERENCE_REVISION}:{p.relative_to(root).as_posix()}'],cwd=root)
 assert raw==p.read_bytes(),path
 return raw.decode()
def declarations():
 definitions,_=protocol.declarations()
 return definitions
def helpers():
 definitions=declarations();cpp,rust=protocol.helpers(definitions)
 a,b=animation_input.helpers(animation_input.schema())
 return cpp+'\n'+a,rust+'\n'+b

def aliases():
 result=adjusted.aliases()
 for name in ('general','teleport'):
  result[f'atelier-host/src/physics/skeleton_input_runtime/skeleton_input_{name}.rs']=f'crates/skate-host/src/physics/skeleton_input_{name}.rs'
 return result

def prepare_oracle(probe):
 base=adjusted.prepare_oracle(PLUGIN/'Tests/Reference/adjusted_skeleton_probe.rs').split('fn main(){',1)[0]
 nominal=next(line for line in base.splitlines()if line.startswith(' pub struct SkeletonInput{'))
 runtime=source('crates/skate-host/src/physics/skeleton_input_runtime.rs')
 anim=source(animation_input.HOST)
 private='''\npub fn observe(o:&mut crate::Output,s:&AnimationInput){crate::observe_ScalarAttributeInputs(o,&s.fields);crate::observe_ExtendedAttributes(o,&s.extra);crate::observe_ContactEventState(o,&s.contacts);crate::observe_AnimationControlOutput(o,&s.output);crate::observe_JumpAttributeState(o,&s.cached_jump);crate::observe_FinalizationInput(o,&s.settings);for v in s.height_overrides{o.word(v as u32);}o.word(s.right_toe as u32);o.word(s.bone_names.len()as u32);for n in &s.bone_names{for v in n.0{o.word(v);}}}\n'''
 modules=' pub mod animation_input{\n'+anim+private+'}\n pub mod skeleton_input_runtime{\n'+runtime+'\n}\n pub(crate) use skeleton_input_runtime::SkeletonInputRuntime as SkeletonInput;'
 base=base.replace(nominal,modules)
 # The full unchanged dispatcher resolves the existing pose-adjust owner at
 # the original offboard privacy path; this is a forwarding alias only.
 base=base.replace('pub mod offboard{','pub mod offboard{pub(crate) use super::offboard_pose_adjust as pose_adjust;')
 field=re.search(r'skeleton_input:physics::SkeletonInput\{[^{}]+\}',base).group()
 base=base.replace('let s=SkaterRuntime{','let mut runtime=physics::SkeletonInput::load(data).unwrap();runtime.extra_target_positions=target_positions;runtime.drive_frames=initial;let s=SkaterRuntime{').replace(field,'skeleton_input:runtime')
 assert 'pub struct SkeletonInput{'not in base and field not in base
 _,rust=helpers()
 return base+probe.read_text().replace('// GENERATED_PROTOCOL',rust)

def corpus():
 w=Stream();cases=[];records=[];rng=random.Random(0x82bd8918)
 def bits(v):return adjusted.bits(v)
 def fs(values):return adjusted.f(values)
 def affine(seed):
  import math
  angle=.17*seed;c,s=math.cos(angle),math.sin(angle)
  return fs([c,0,-s,0,1,0,s,0,c,0,(0,.04,.2,.6)[seed%4],0])
 def world(seed):
  slope=(0,.12,-.12,.35)[seed%4];points=[(-4,-4*slope-.025,-4),(4,4*slope-.025,-4),(4,4*slope-.025,4),(-4,-4*slope-.025,4)];raw=[2]
  for ids,tag in (((0,2,1),1),((0,3,2),12)):raw+=fs([x for j in ids for x in points[j]])+[0,0x10,tag]
  return raw
 def attr(name,value=.137,kind=0,payload=None):
  a=attribute(kind=kind,status=5);a['name']=animation_input.trees.name(name);a['payload']=[bits(value),None,None,None,None,None]if payload is None else payload;return a
 def encode_attr(a):
  raw=a['name']+[a['kind'],a['status'],a['sequence']&0xffffffff,a['begin'],a['end']]
  for p in a['payload']:raw+=[p is not None]+([p]if p is not None else [])
  return list(map(int,raw))
 def tick(seed,k,attrs=(),branch=None,solve=True,pose=None):
  state=(201,202,702,503,500,601,602)[(seed+k//3)%7];category=500 if state in(500,503)else 600 if state in(601,602)else 200
  raw=[0,(seed+k//4)%4 if pose is None else pose,bits((1/60,1/120,1/30)[seed%3]),state,category,(1,2,3,6)[(seed+k//4)%4],(0x2000,0x2100,0x42002000)[k%3],(0,0x180,1,0x400)[(seed+k)%4],(0,4,0x100,0x10000000)[(seed+k)%4],(0,0x08000000,2)[k%3],(0,1<<20,1<<21)[k%3],0,(0,0x08800000,0x12000000)[k%3],int(k%5==0),len(attrs)]
  for a in attrs:raw+=encode_attr(a)
  raw+=fs([-.3,.25,.0,.0,.75]+[0]*13)+[(seed+k)%3 if branch is None else branch,int(solve)]
  return raw
 def add(label,cmds,seed=0):
  raw=affine(seed)+world(seed)+[seed%2,len(cmds)]+[x for cmd in cmds for x in cmd]
  records.append(struct.pack('<'+'I'*len(raw),*raw));cases.append(dict(index=len(cases),label=label,commands=[cmd[0]for cmd in cmds],command_inputs=[dict(operation=cmd[0],branch=cmd[-2],solve=bool(cmd[-1]),pose=cmd[1])if cmd[0]==0 else dict(operation=cmd[0])for cmd in cmds]))
 catalog=re.findall(r'entry\("([^\"]+)"',animation_input.trees.source_at_reference(animation_input.CORE+'catalog.rs').split('pub const EVENT_COMPARISONS')[0])
 assert len(catalog)==151
 for seed in range(48):
  commands=[]
  for k in range(16):
   if k==2:commands.append([3,1,seed+1,1,0,0]+fs([.1,.2,.3,0]*8))
   if k==4:commands.append([1])
   if k in(1,5,9):commands.append([4,(seed+k)%4,(seed+k)%3]+fs([.4,.1,.2,.3,0,1,0,0]))
   if k==6:commands.append([2,seed%2,(seed//2)%2])
   if k==8:commands.append([6]+world(seed+1))
   if k==12:commands.extend([[7],[8,seed%5]])
   if k==13:commands.append([9,2|(8 if seed%2 else 0),seed+23])
   attrs=[attr('Balance',.15),attr('BodySpin',.03),attr(catalog[(seed*16+k)%151],.317)]
   if k%4==0:attrs.append(attr('push_contact',kind=3,payload=animation_input.trees.name('RightToeBase')+[bits(.75)]))
   commands.append(tick(seed,k,attrs))
  add('live authored hierarchy, ordered attributes, retained roots/drives/contact feedback and ground/teleport lifecycle',commands,seed)
 for n,name in enumerate(catalog):add('all original scalar catalog through ProcessData',[tick(n%12,0,[attr('Balance',.5),attr(name)],branch=3,solve=False)])
 for name in catalog:add('missing scalar payload preserves original partial state',[tick(0,0,[attr('Balance',.5),attr(name,payload=[None]*6),attr('Brake',.1)],branch=3,solve=False)])
 for k in range(6):
  payload=animation_input.trees.name('RightToeBase')+[bits(1.)];payload[k]=None
  add('missing contact payload and prefix attribute publication',[tick(0,0,[attr('Balance',.5),attr('push_contact',kind=3,payload=payload)],branch=3,solve=False)])
 for branch in range(4):add('actual missing hierarchy failure preserves earlier wake/scalar/flags',[tick(0,0,[],branch,False,4)])
 for seed in range(12):
  target=[5]+fs([-2,0,0,0,2,0,0,0])+[seed,0,1,0]+fs([0,1,0,0,0,1,0,0,0,0,1,0,0,1,0,0])
  commands=[target,[3,0,seed,0,1,1]+fs([0]*32)]+[tick(seed,k,[attr('Balance',.1)])for k in range(10)]
  add('actual retained GrindAir owner in full ProcessData before landing/offset',commands,seed)
 return struct.pack('<I',len(records))+b''.join(records),cases

def preflight():
 raw,cases=corpus();words=struct.unpack('<'+'I'*(len(raw)//4),raw);at=1
 def world():
  nonlocal at
  n=words[at];at+=1+12*n
 for c in cases:
  at+=12;world();at+=1;n=words[at];at+=1;assert n==len(c['commands'])
  for op in c['commands']:
   assert words[at]==op,(c,at);at+=1
   if op==0:
    at+=13;attrs=words[at];at+=1
    for _ in range(attrs):
     at+=10
     for _ in range(6):present=words[at];at+=1+bool(present)
    at+=20
   elif op==6:world()
   else:at+={1:0,2:2,3:37,4:10,5:28,7:0,8:1,9:2}[op]
 assert at==len(words),(at,len(words))
 for unit in UNITS:assert(PLUGIN/f'Source/AtelierSkate/Private/Native/{unit}.cpp').is_file(),unit
 return raw,cases

def build(output,target):
 live=PLUGIN/'Source/AtelierSkate/Private/Native';n=output/'native-source'
 if n.exists():shutil.rmtree(n)
 n.mkdir()
 for p in live.glob('*.h'):shutil.copy2(p,n/p.name)
 for u in UNITS:shutil.copy2(live/f'{u}.cpp',n/f'{u}.cpp')
 prefixes=[PLUGIN/f'Tests/Native/skeleton_{name}_probe.cpp'for name in('body','collision','constraint')]+[PLUGIN/'Tests/Native/physical_simulation_runtime_probe.cpp',PLUGIN/'Tests/Native/adjusted_skeleton_probe.cpp']
 own=PLUGIN/'Tests/Native/skeleton_input_runtime_probe.cpp';cpp_helpers,_=helpers();combined=n/own.name
 combined.write_text('#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wunused-function"\n'+''.join(p.read_text().split('int main(',1)[0].split('int main()',1)[0]for p in prefixes)+'\n#pragma clang diagnostic pop\n'+own.read_text().replace('// GENERATED_PROTOCOL',cpp_helpers))
 binary=output/'skeleton-input-runtime-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(n),*[str(n/f'{u}.cpp')for u in UNITS],str(combined),'-o',str(binary)],check=True)
 rust_prefixes=[PLUGIN/f'Tests/Reference/skeleton_{name}_probe.rs'for name in('body','collision','constraint')];prefix=''.join(p.read_text().split('fn main(){',1)[0]for p in rust_prefixes).replace('use crate::{','use skate_core::{').replace('skeleton_root::inverse_rigid,','').replace('solver::{packed,JointConstraint}','solver::{JointConstraint}').replace('#[path="physics/solver/packing.rs"] mod skeleton_constraint_packing;','mod skeleton_constraint_packing{use skate_core::physics::solver::{packed,JointConstraint};use crate::{RetailDriveRows,RetailContactJacobian};use skate_core::physics::rigid_body::RetailReactionCorrections;#[path="packing.rs"]mod original;pub fn drive(r:&RetailDriveRows)->packed::Drive{original::drive(r)}}')
 own_rs=PLUGIN/'Tests/Reference/skeleton_input_runtime_probe.rs';generated=output/'skeleton-input-runtime-combined.rs';generated.write_text(prefix+prepare_oracle(own_rs));reference=build_probe(output,'skeleton-input-runtime-reference',generated,target,bevy=True,extra_sources=aliases());(output/'native-provenance.json').write_text(json.dumps(dict(native_source_sha256={p.name:digest(p)for p in n.iterdir()},probe_sha256={p.name:digest(p)for p in[*prefixes,*rust_prefixes,own,own_rs]},toolkit_transport='Original BoardToolkit::from_board receives the actual board, flags, speed and normals; its translation.W=1 is retained through GrindAir. Raw solve::deck_frame is not used as a substitute toolkit.'),indent=2)+'\n');return binary,reference

def decode(data,cases):
 words=struct.unpack('<'+'I'*(len(data)//4),data);at=0;coverage=Counter()
 for c in cases:
  index,n,size=words[at:at+3];assert index==c['index']and n==len(c['commands']);c['first_output_word']=at;c['output_words']=size+3;cursor=at+3;cursor+=1+words[cursor];c['outputs']=[]
  for spec in c['command_inputs']:
   op=spec['operation'];assert words[cursor]==op;length=words[cursor+1];payload=words[cursor+2];assert payload<=length-1
   row=dict(operation=OPERATIONS[op],first_output_word=cursor,output_words=length+2,owner_output_words=payload)
   if op==0:
    assert words[cursor+3]in(0,1);row['success']=bool(words[cursor+3]);coverage['process_data_success'if row['success']else'process_data_failure']+=1
    if row['success']and spec['solve']:
     where=cursor+4+(16 if spec['branch']!=3 else 0);row['solved_contact_rows']=words[where];row['solved_drive_rows']=words[where+1];coverage['shared_solve_ticks']+=1;coverage['solved_contact_rows']+=words[where];coverage['solved_drive_rows']+=words[where+1]
    if 'missing hierarchy'in c['label']:assert not row['success']
   c['outputs'].append(row);coverage[OPERATIONS[op]]+=1;cursor+=length+2
  assert cursor==at+size+3;at=cursor
 assert at==len(words)
 assert coverage['process_data_success']and coverage['process_data_failure']
 assert coverage['shared_solve_ticks']and coverage['solved_contact_rows']and coverage['solved_drive_rows']
 return dict(coverage)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--samples',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);p.add_argument('--preflight',action='store_true');a=p.parse_args();o=a.output.resolve();o.mkdir(parents=True,exist_ok=True);inputs,cases=preflight();(o/'input.bin').write_bytes(inputs)
 if a.preflight:print(json.dumps(dict(streams=len(cases),commands=sum(len(c['commands'])for c in cases),process_data=sum(c['commands'].count(0)for c in cases),input_bytes=len(inputs),units=len(UNITS),aliases=len(aliases())),indent=2));return
 stock=a.assets.resolve()/'private/stock';settings=o/'settings.native';physical=o/'physics.native';settings.write_bytes(adjusted.physical.converter.encode_settings(stock/'skater-collections.json'));physical.write_bytes(adjusted.physical.converter.encode_physics_skeletons(stock/'physics-skeletons.json'));identity=json.loads((stock/'physics-skeletons.json').read_text())['source_sha256'];cpp,ref=build(o,a.target_dir);expected=subprocess.check_output([str(ref),str(a.assets.resolve())],input=inputs);actual=subprocess.check_output([str(cpp),str(settings),str(physical),str(a.samples.resolve()/'native/rig.skate'),identity],input=inputs);(o/'reference.bin').write_bytes(expected);(o/'cpp.bin').write_bytes(actual);coverage=decode(expected,cases);(o/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
 if expected!=actual:
  first=next((n for n,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)))//4;case=next((c for c in cases if c['first_output_word']<=first<c['first_output_word']+c['output_words']),None);report=dict(passed=False,first_word=first,case=case,reference_bytes=len(expected),cpp_bytes=len(actual));(o/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
 result=dict(passed=True,streams=len(cases),exact_words=len(expected)//4,coverage=coverage,input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),comparison='Complete frozen ProcessData/GeneralUpdate/Ground/Teleport/reset with actual AnimationInput, AnimatedSkeleton, FootIK, loaded physical owners and shared solve. No numerical source modifications or tolerance.',limitations='Ordered authored attributes/action maps and current processed gameplay requests/flags are explicit producer inputs. World triangles are engine geometry inputs. Full session/ground lifecycle dispatch remains separate.');(o/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
