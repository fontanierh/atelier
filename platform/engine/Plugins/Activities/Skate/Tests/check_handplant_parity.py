#!/usr/bin/env python3
"""Frozen whole-host Handplant ground/reset, contact, IK and arithmetic proof.

Only the root coordinator compiles or executes. Successful air entry and the
Handplant Update continuation await root-owned AirTrajectory/AirReckoning.
Their production signatures remain mandatory, with no neutral implementation.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
import check_air_reckoning_parity as air_reckoning
import check_air_trajectory_query_parity as trajectory_query
import check_skeleton_input_runtime_parity as skeleton
from camera_reference_build import frozen_sources
from check_gesture_parity import PLUGIN,converter
from check_graph_parity import element,original_graph
from session_parity import REFERENCE_REVISION,digest
CODE=PLUGIN/'Source/AtelierSkate/Private/Simulation'
UNITS=tuple(dict.fromkeys((*air_reckoning.UNITS,*trajectory_query.UNITS,*skeleton.UNITS,'NameId','Settings','StockSettingsReader','SimulationMath','AnimationName','Input','InputIntentions','WipeoutOrientation','SkeletonPhysicalRecord','PlayerInputTypes','PlayerInputPhase','PlayerGrindSurface','PlayerGrindInputWorld','BoardAnimation','SkeletonAirFrames','SkeletonAirRuntime','HandplantSettings','HandplantContact','HandplantRotation','HandplantTrajectory','Handplant','PlantSkeleton')))
OPS=('seed','reset','full_reset','ground_query','ground_update','launch','values','ik','time_warp','hold_foot','build_curve','estimate_apex','rotation_frame','rotation_blend','missing_entry','plant_math','authored_query_world')
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def fs(values):return [bits(v)for v in values]
def flatten(value):return [x for row in value for x in row]
def matrix(angle=0,position=(0,0,0,0)):
 c,s=math.cos(angle),math.sin(angle);return [[c,0,-s,.0317],[0,1,0,-.071],[s,0,c,.137],list(position)]
def candidate(point=(.731,1.7,-.317,.137),owner=0x1234567800000001,side=1):return fs([*point,-2,point[1],point[2],.137,2,point[1],point[2],.317])+[owner&0xffffffff,owner>>32,side&0xffffffff]
def trajectory(position=(.137,.731,-.317,.517),velocity=(.731,3.17,.137,.317),duration=-1):return fs([*position,*velocity,0,-9.8,0,0,duration])
def seed(n,*,phase=.317,warped=None,flags=None,c=None,pending=None):
 warped=(-.1,.1,.5,.9,1.3,1.9)[n%6]if warped is None else warped
 out=[0,(0xe0000000|(n&0xff))if flags is None else flags,bits(phase)]+fs([.731,1.7,-.317,.137,.517,1.7,-.317,.731])
 out+=[int(pending is not None)]+(pending or [])+[int(c is not None)]+(c or [])
 out+=trajectory()+trajectory(position=(.13,.67,-.37,-.137),velocity=(.31,2.3,.73,.17))
 out+=trajectory(position=(.31,.8,-.37,.317),velocity=(.73,2.7,-.13,.17))+trajectory(position=(-.31,.9,.137,-.731),velocity=(1.3,2.8,-.13,.17))
 for i in range(4):out+=fs([.137+i*.1731,.731+i*.1731,-.317+i*.0317,.137+i*.071])
 for i in range(4):out+=fs(flatten(matrix(i*.317,position=(i*.13,i*.17,i*.07,i*.0317))))
 out+=fs([.317,0,.731,.137,(-1,1)[n%2],(n%7)*.0173,warped,.731,.517,1.137])+[int(n%3!=0),(n%3),n%17]+fs([.137,(.37,-1)[n%2]])+[int(n%5==0),int(n%7==0)]
 return out
def query(n,*,enabled=True,speed=None,normal=None):
 velocity=[(1 if n%2==0 else -1)*(.731+(n%5)*.137),4.731+(n%7)*.137,.0317,.137]if speed is None else speed
 norm=[.0,.6,(-1 if n%2 else 1)*.8,.317]if normal is None else normal
 return [3,(1<<22 if enabled else 0)|(4 if n%3==0 else 0),(1<<28)|(1<<29 if n%13==0 else 0),0,0]+fs([0,.731,0,.137,*velocity,*norm,1,0,0,.317,1,0,0,.731])
def ik(n,ground=False):
 root=matrix(n*.137,position=(.13,.17,-.31,.137));pose=[matrix(position=(.0,.0,.0,.0))for _ in range(24)]
 for side in (0,1):
  pose[3+side*4][3]=[.65+side*.137,.37+(n%5)*.137,-.317,.137]
  pose[6+side*4][3]=[.73+side*.137,1.1+(n%3)*.137,-.317,.317]
 targets=[matrix(position=(.517+i*.137,.37,-.317,.17))for i in range(4)]
 return [7,int(ground),4 if n%2 else 0,(1<<28)|(1<<29 if n%17==0 else 0)]+fs(flatten(root))+fs(flatten([flatten(m)for m in pose]))+fs(flatten([flatten(m)for m in targets]))
def world(kind):
 triangles=[]
 if kind!=2:
  y=-.035;corners=[[-5,y,-5],[5,y,-5],[5,y,5],[-5,y,5]]
  triangles=[([corners[j]for j in ids],1)for ids in ((0,2,1),(0,3,2))]
  if kind==1:
   corners=[[-3,1.7,-3],[3,1.7,-3],[3,1.7,3],[-3,1.7,3]];triangles+=[([corners[j]for j in ids],12)for ids in ((0,2,1),(0,3,2))]
 raw=[len(triangles)]
 for vertices,tag in triangles:raw+=fs(flatten(vertices))+fs([0,1,1,1])+[0x10]+fs([.731,.517,.137])+[tag]
 return raw
def edges(n,cap=False):
 records=[]
 for k in range(70 if cap else 12):
  x=0
  y=.731+.1+(k%5)*.113;z=(-1 if n%2==0 else 1)*(.137+(k%3)*.1731)
  if k%7==0:y+=.0317
  if cap and k<40:z=0 # admitted by broadphase, rejected as coplanar later
  records+=fs([x-2,y,z,.137,x+2,y+(k%4)*.00317,z,.317])+[k+1,0x12345678+n]
 return [70 if cap else 12]+records
def authored_query_world(kind,*,blocked=False,pool=0):
 # Genuine world triangles and independent authored query metadata. Rendering
 # tags remain separate from packed surfaces; mesh ownership/pool are explicit.
 geometry=world(kind)
 if blocked:
  vertices=[[-5,1.284,-5],[5,1.284,-5],[5,1.284,5],[-5,1.284,5]]
  geometry=[2]
  for ids in ((0,2,1),(0,3,2)):
   geometry+=fs(flatten([vertices[j]for j in ids]))+fs([0,1,1,1])+[0x10]+fs([.731,.517,.137])+[0xa510+len(geometry)]
 count=geometry[0];packed=[0x20b+(k%2)*0x180 for k in range(count)]
 mesh=[]
 if count:
  y=[struct.unpack('<f',struct.pack('<I',geometry[1+k*18+v*3+1]))[0]for k in range(count)for v in range(3)]
  mesh=[1,0,count]+fs([-5,min(y),-5,5,max(y),5])+[0xffffffff,0xffffffff,0x82d61040,pool]
 else:mesh=[0]
 return [16]+geometry+[count]+packed+mesh+[3]

def reset_seed(n):
 point=(.731+math.sin(n*.137)*.1731,1.7+(n%5)*.0317,-.317,(n%7)*.0173)
 c=candidate(point,owner=0x1234567800000001+n,side=1+n%2)
 pending=c+fs([.137,.731,-.317,.1731,1,4.7,.13,.317,0,.6,.8,.137,1,0,0,.317])
 words=seed(n,phase=.137+n*.00173,warped=(-.1,.1,.5,.9,1.3,1.9)[n%6],c=c,pending=pending)
 # The first 59 words are the unchanged explicit owner header/options. Vary
 # retained trajectories, curves and matrices before reset, never query output.
 start=12+31+1+15
 assert len(words[start:start+52])==52
 for k in range(52+16+64):words[start+k]=bits((.137+(k%13)*.0173)*(-1 if (n+k)%3==0 else 1)+n*.000137)
 return words

def corpus():
 records=[];cases=[]
 def add(label,commands,n=0,cap=False):
  raw=world(n%3)+edges(n,cap)+[len(commands)]+[word for cmd in commands for word in cmd]
  cases.append(dict(index=len(cases),label=label,commands=commands,operations=[cmd[0]for cmd in commands],cap=cap));records.append(struct.pack('<'+'I'*len(raw),*raw))
 for n in range(16):
  commands=[seed(n),[1],seed(n+1),[2]]
  for k in range(48):
   commands += [query(k+n),[4],ik(k+n,True)]
   if k%7==0:commands += [[4]] # consumed pending is never resubmitted
   if k%11==0:commands += [query(k+n,enabled=False),[4]]
  commands += [query(0,enabled=False),[14]]
  if n%3==1:
   c=candidate();pending=c+fs([0,.731,0,.137,1,4.7,.13,.317,0,.6,.8,.137,1,0,0,.317])
   for k in range(8):commands += [query(k),seed(k,c=c,pending=pending),[4]]
  add('actual ground submission, complete world investigation, consumed pending and IK',commands,n)
 for n in range(4):
  commands=[query(n),[4],query(n+1,speed=[.1,.1,0,.137]),[4],query(n+2,normal=[0,1,0,.137]),[4],query(n+3,normal=[0,-.96,.1,.137]),[4]]
  add('authored primitive broadphase cap40 excludes the later nearby coping',commands,n,True)
 for n in range(8):
  commands=[]
  for k in range(32):
   c=candidate(owner=(0x12345678+n)<<32|k+1,side=1+k%2)
   commands += [[5]+c+fs([0,.731,0,.137,1,4.7,.13,.317,0,.6,.8,.137,1,0,0,.317,1,0,0,.731]),[10]]
   commands += [seed(n*32+k,phase=(.317,-.731)[k%2],c=c),ik(n*32+k)]
   pose=[matrix(position=(.13,b*.0731,.17,.317))for b in range(24)]
   commands += [[6]+fs(flatten([flatten(m)for m in pose]))+fs([.137,.731,.317,.517])]
   commands += [[9,k%2]+fs([.317+(k%7)*.137,.731,-.317,.137])+[k%3]]
  add('launch arcs, Bezier/time domains, rotation states, mirror/release/latch IK and feet',commands,n)
 for n in range(4):
  commands=[]
  for k in range(32):
   c=candidate();pending=c+fs([0,.731,0,.137,1,4.7,.13,.317,0,.6,.8,.137,1,0,0,.317])
   commands += [seed(n*32+k,c=c,pending=pending),[1],seed(n*32+k,c=c,pending=pending),[2]]
  commands += [[8]+fs([0,1,2,3,4,5,6,7]+[-1]*8),seed(n,phase=.731,warped=-.1731),[11]]
  for k in range(32):commands += [reset_seed(2048+n*64+k),[1],reset_seed(4096+n*64+k),[2]]
  add('selective reset preserves all trajectories, curve, rotations and new-position bit; zero mean retains estimate',commands,n)
 rng=random.Random(0x82d61040)
 for n in range(8):
  commands=[]
  for k in range(40):
   a=[rng.uniform(-2,2)for _ in range(4)];b=[rng.uniform(-2,2)for _ in range(4)];s=rng.uniform(.137,2.137);m=matrix(k*.137,position=(.731,-.317,.137,.517))
   commands += [[15]+fs(a+b+[s,.731])+fs(flatten(m)),[12]+fs(a+b),[13]+fs(flatten(m))+fs(flatten(matrix(k*.731,position=(.137,.731,-.317,.137))))+fs([(-.137,0,.0317,.317,.731,1,1.137)[k%7]])]
  add('full plant vector arithmetic and original axis-angle rotation branches',commands,n)
 for n in range(8):
  blocked=n>=6
  commands=[authored_query_world(n%3,blocked=blocked,pool=n%3)]
  for k in range(72):commands += [[1],query(k+n),[4],ik(k+n,True)]
  add('real authored-query world; original candidate selection and '+('blocked cross-section'if blocked else'successful surface admission')+' with actual IK',commands,n)
 return struct.pack('<I',len(records))+b''.join(records),cases

BASELINE_INPUT_SHA256='89f9c477828597b7e79fe979481d845eaaf1cc91800b41bd6eb14baf434769e7'

def validate_corpus(raw,cases):
 # Rebuild the original 40 streams without their additive tails/new streams.
 # This is an exact wire audit, including worlds, retained caller inputs and
 # every old command meaning/error. No old command may be removed or rewritten.
 original=[]
 for c in cases[:40]:
  index=c['index'];n=index if index<16 else index-16 if index<20 else index-20 if index<28 else index-28 if index<32 else index-32
  count=(191 if n%3==1 else 167)if index<16 else 8 if index<20 else 192 if index<28 else 131 if index<32 else 120
  commands=c['commands'][:count]
  words=world(n%3)+edges(n,c['cap'])+[len(commands)]+[v for command in commands for v in command]
  original.append(struct.pack('<'+'I'*len(words),*words))
 baseline=struct.pack('<I',40)+b''.join(original)
 assert hashlib.sha256(baseline).hexdigest()==BASELINE_INPUT_SHA256
 assert sum((191 if n%3==1 else 167)for n in range(16))+4*8+8*192+4*131+8*120==5844
 words=struct.unpack('<'+'I'*(len(raw)//4),raw);at=1;assert words[0]==len(cases)
 lengths=(None,1,1,25,1,36,389,468,17,7,1,1,9,34,1,27,None)
 for c in cases:
  triangles=words[at];at+=1+18*triangles;primitives=words[at];at+=1+10*primitives
  assert words[at]==len(c['commands']);at+=1
  for cmd in c['commands']:
   size=lengths[cmd[0]]
   if cmd[0]==0:
    pending=cmd[11];candidate_at=12+31*pending;size=162+31*pending+15*cmd[candidate_at]
   if cmd[0]==16:
    triangles=cmd[1];cursor=2+18*triangles;surfaces=cmd[cursor];assert surfaces==triangles;cursor+=1+surfaces;meshes=cmd[cursor];size=cursor+1+12*meshes+1
    assert cmd[-1]==3
   assert len(cmd)==size,(c['index'],cmd[0],len(cmd),size)
   assert list(words[at:at+size])==cmd;at+=size
 assert at==len(words)
 return dict(baseline_input_sha256=BASELINE_INPUT_SHA256,preserved_baseline_cases=40,preserved_baseline_commands=5844,added_reset_calls=256,added_real_metadata_worlds=8,wire_bytes=len(raw),wire_sha256=hashlib.sha256(raw).hexdigest())

def validate_probe_extensions():
 # Removing only the new fixture helper and opcode reconstructs the exact
 # accepted baseline adapters; every old wire/numerical invocation is intact.
 rows={}
 definitions=(('Simulation/handplant_probe.cpp','// Explicit caller-authored scene metadata; numerical queries remain production.','class MissingCandidateQuery','      case 16:\n        p.world = AuthoredQueryWorld(i);\n        break;\n','c020c905ef675e5d2371bd6aae25b2fb1749b4cf6141748682de70283dbfdd67'),('Reference/handplant_observer.rs','// Explicit caller-authored static scene metadata, not inferred from tags.','fn loaded(','   16=>physics.world=authored_query_world(i),\n','2f9841166888038dfd6512d3ca07f2803536e23d163a1e5ea25e6a70afbc6545'))
 for rel,start,end,opcode,baseline in definitions:
  path=PLUGIN/'Tests'/rel;current=path.read_text();assert current.count(start)==current.count(opcode)==1
  first=current.index(start);last=current.index(end,first);helper=current[first:last];rest=current[:first]+current[last:];legacy=rest.replace(opcode,'')
  assert hashlib.sha256(legacy.encode()).hexdigest()==baseline,rel
  rows[rel]=dict(baseline_sha256=baseline,current_sha256=digest(path),fixture_helper_bytes=len(helper.encode()),fixture_helper_sha256=hashlib.sha256(helper.encode()).hexdigest(),opcode_bytes=len(opcode.encode()),opcode_sha256=hashlib.sha256(opcode.encode()).hexdigest())
 return rows

def build_reference(output,target):
 source,report=frozen_sources(output);observed=output/'observed-source'
 if observed.exists():shutil.rmtree(observed)
 shutil.copytree(source,observed);crate=observed/'atelier-host';host=source/'crates/skate-host/src';extensions={}
 helper=PLUGIN/'Tests/Reference/handplant_observer.rs';extensions['physics/handplant.rs']='\n'+helper.read_text()
 extensions['physics/handplant/trajectory.rs']='\nimpl Handplant {pub(super) fn migration_build_curve(&mut self){self.build_curve()}}\n'
 extensions['physics.rs']='\npub(crate) fn migration_handplant_run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{handplant::migration_handplant_run(assets,fixtures,i,o)}\n'
 extensions['grind_world/provider.rs']='\npub(super) fn migration_handplant_primitives(primitives:Vec<Primitive>)->StaticProvider{let mut value=StaticProvider::new(None).unwrap();value.primitives=primitives;value}\n'
 extensions['grind_world.rs']='\npub(crate) fn migration_handplant_primitives(primitives:Vec<skate_core::physics::grind_contact::Primitive>)->StaticProvider{provider::migration_handplant_primitives(primitives)}\n'
 staged={}
 for original in sorted(host.rglob('*.rs')):
  rel=original.relative_to(host).as_posix()
  if rel in ('lib.rs','main.rs'):continue
  raw=original.read_bytes();extra=extensions.get(rel,'').encode();p=crate/'src'/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw+extra);assert p.read_bytes()[:len(raw)]==raw
  staged[rel]=dict(original_prefix_bytes=len(raw),original_prefix_sha256=digest(original),append_sha256=hashlib.sha256(extra).hexdigest(),generated_sha256=digest(p))
 template=PLUGIN/'Tests/Reference/handplant_probe.rs';shutil.copy2(template,crate/'src/migration_probe.rs');cargo=crate/'Cargo.toml'
 cargo.write_text(cargo.read_text()+'''\nskate-core={path="../crates/skate-core"}
skate-data={path="../crates/skate-data"}
skate-net={path="../crates/skate-net"}
half="2.7.1"
bevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}
[[bin]]
name="handplant-reference"
path="src/migration_probe.rs"
''')
 subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(cargo),'--target-dir',str(target.resolve()),'--bin','handplant-reference'],check=True)
 for rel,sha in report['original_source_sha256'].items():assert digest(source/rel)==sha and (observed/rel).read_bytes()[:len((source/rel).read_bytes())]==(source/rel).read_bytes(),rel
 for rel,row in staged.items():assert digest(crate/'src'/rel)==row['generated_sha256'],rel
 binary=output/'handplant-reference';shutil.copy2(target.resolve()/'release/handplant-reference',binary)
 report.update(staged_host_original_prefixes=staged,probe_sha256=digest(template),helper_sha256=digest(helper),binary_sha256=digest(binary),scope='All original host production source byte prefixes unchanged. Appended observation/fixture setters and one privacy-only migration_build_curve wrapper, whose complete original trajectory prefix is hashed in staged_host_original_prefixes. Ground/reset/contact/launch/values/IK/hold-foot/math/rotation invoke complete original bodies. Enter is tested only with absent candidate: query cannot run. Successful entry, complete active Update and PlantSkeleton advance remain later concrete AirTrajectory/AirReckoning integration proofs. Authored primitive entries explicitly fill the real world owner; metadata/octree are unused by original Handplant selection.')
 (output/'reference-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return binary

def build_simulation(output):
 snapshot=output/'simulation-source';snapshot.mkdir(exist_ok=True);hashes={}
 for p in sorted(CODE.glob('*.h')):shutil.copy2(p,snapshot/p.name);hashes[p.name]=digest(snapshot/p.name)
 for unit in UNITS:p=CODE/(unit+'.cpp');shutil.copy2(p,snapshot/p.name);hashes[p.name]=digest(snapshot/p.name)
 probe=PLUGIN/'Tests/Simulation/handplant_probe.cpp';shutil.copy2(probe,snapshot/probe.name);hashes[probe.name]=digest(snapshot/probe.name);binary=output/'handplant-simulation'
 subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/probe.name),'-o',str(binary)],check=True)
 (output/'simulation-provenance.json').write_text(json.dumps(dict(immutable_simulation_sources=hashes,units=UNITS),indent=2)+'\n');return binary

class Reader:
 def __init__(self,data):self.words=struct.unpack('<'+'I'*(len(data)//4),data);self.at=0
 def take(self,n):value=list(self.words[self.at:self.at+n]);assert len(value)==n;self.at+=n;return value
 def word(self):return self.take(1)[0]
 def owner(self):
  state=dict(flags=self.word(),phase=self.word(),anchor=self.take(4),previous=self.take(4),pending=None,candidate=None)
  if self.word():state['pending']=self.take(31)
  if self.word():state['candidate']=self.take(15)
  for key,n in [('trajectories',52),('curve',16),('rotations',64),('direction',4),('times',6),('continuation',1),('hint',1),('count',1),('ik',4)]:state[key]=self.take(n)
  state['effects']=self.take(76);return state
 def status(self):okay=self.word();return None if okay else bytes(self.take(self.word())).decode()
def decode(data,cases):
 r=Reader(data);assert r.word()==len(cases);frames=[]
 for c in cases:
  settings=r.take(148);assert r.word()==len(c['commands']);prior=r.owner();rows=[]
  for cmd in c['commands']:
   op=r.word();assert op==cmd[0];value=None;error=None
   if op in(4,14):error=r.status()
   elif op==6:value=r.take(12)
   elif op in(12,13):value=r.take(16)
   elif op==15:value=r.take(40)
   state=r.owner();rows.append(dict(operation=op,state=state,prior=prior,value=value,error=error));prior=state
  frames.append(dict(settings=settings,rows=rows))
 assert r.at==len(r.words),(r.at,len(r.words));return frames
def coverage(frames,cases):
 counts=Counter();candidates=set();sides=set();targets=set();phases=set();launched=0;surface_admitted=surface_blocked=zero_means=missing=reset_preserved=0;surface_errors=retained_flags_after_error=0;metadata_worlds=0;retained_variants=set()
 for frame,c in zip(frames,cases):
  for index,(row,cmd) in enumerate(zip(frame['rows'],c['commands'])):
   op=row['operation'];counts[OPS[op]]+=1;s=row['state'];prior=row['prior']
   if s['candidate']:candidates.add(tuple(s['candidate']));sides.add(s['candidate'][-1])
   if op==3:
    if not(cmd[1]&(1<<22)):assert s['pending']is None and s['candidate']is None and s['ik']==[0,bits(-1),0,0]
    if c['cap']:assert s['candidate']is None,'later primitives bypassed original cap40'
   if op==4 and prior['pending']is not None:
    assert s['pending']is None
    real_query=index>0 and c['commands'][index-1][0]==3
    if row['error']:
     assert row['error']=='Canonical world has no authored query metadata'
     surface_errors+=1;retained_flags_after_error+=bool(s['flags']&0x80000000)
    elif real_query:
     assert not prior['flags']&0x80000000, 'fresh admission requires reset before actual Query'
     if s['flags']&0x80000000:surface_admitted+=1
     else:surface_blocked+=1
    else:assert not s['flags']&0x80000000, 'only source-selected successful queries count as admission'
   if op in(1,2):
    assert s['flags']==prior['flags']&~0xb0000000 and s['phase']==0x7f7fffff and s['anchor']==[0]*4 and s['pending']is None and s['candidate']is None
    for key in('trajectories','curve','rotations','previous'):assert s[key]==prior[key],key
    assert s['times'][0]==prior['times'][0]
    if op==1:assert s['ik']==prior['ik'] and s['hint']==prior['hint'] and s['count']==prior['count']
    else:assert s['ik']==[0,bits(-1),0,0]and s['hint']==s['count']==[0]
    reset_preserved+=1;retained_variants.add(tuple(v for key in('trajectories','curve','rotations','previous')for v in prior[key]))
   if op==5:assert s['flags']&0x80000000;launched+=1
   if op==7:targets.add(tuple(s['effects'][:24]));phases.add(s['phase'])
   if op==11:assert s['phase']==s['times'][4]==prior['times'][4];zero_means+=1
   if op==16:metadata_worlds+=1
   if op==14:assert row['error']=='Handplant entry requires the selected coping' and s['effects'][-1]==1 and s['times'][1:3]==[0,0];missing+=1
 assert len(candidates)>64 and sides=={1,2} and surface_admitted>64 and surface_blocked>16
 assert metadata_worlds==8 and surface_errors>16 and retained_flags_after_error==40
 assert launched>=256 and len(targets)>128 and len(phases)>1 and reset_preserved>512 and len(retained_variants)>225 and zero_means==4 and missing==16
 return dict(operations=dict(counts),distinct_candidates=len(candidates),candidate_sides=sorted(sides),surface_admitted=surface_admitted,surface_blocked=surface_blocked,missing_authored_metadata_errors=surface_errors,error_retains_active_flag=retained_flags_after_error,authored_query_worlds=metadata_worlds,distinct_IK_targets=len(targets),selective_reset_checks=reset_preserved,distinct_retained_reset_payloads=len(retained_variants),zero_mean_retention=zero_means,missing_entry_partial_writes=missing)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--samples',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);inputs,cases=corpus();audit=validate_corpus(inputs,cases);audit['probe_extensions']=validate_probe_extensions();(out/'input.bin').write_bytes(inputs);(out/'wire-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
 for unit in UNITS:assert (CODE/(unit+'.cpp')).is_file(),unit
 if a.preflight:print(json.dumps(dict(cases=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(inputs),units=len(UNITS)),indent=2));return
 fixtures=out/'fixtures';fixtures.mkdir(exist_ok=True);stock=a.assets.resolve()/'private/stock';(fixtures/'settings.simulation').write_bytes(converter.encode_settings(stock/'skater-collections.json'));(fixtures/'physics.simulation').write_bytes(converter.encode_physics_skeletons(stock/'physics-skeletons.json'))
 for kind in('action','motion'):(fixtures/f'actor.{kind}.reference').write_bytes(original_graph(element('state','idle')))
 reference=build_reference(out/'reference',a.target_dir);simulation=build_simulation(out);identity=json.loads((stock/'physics-skeletons.json').read_text())['source_sha256']
 expected=subprocess.check_output([str(reference),str(a.assets.resolve()),str(fixtures)],input=inputs);actual=subprocess.check_output([str(simulation),str(fixtures/'settings.simulation'),str(fixtures/'physics.simulation'),str(a.samples.resolve()/'simulation/rig.skate'),identity,str(a.assets.resolve())],input=inputs)
 (out/'reference.bin').write_bytes(expected);(out/'simulation.bin').write_bytes(actual)
 if expected!=actual:
  at=next((i for i,(a,b)in enumerate(zip(expected,actual))if a!=b),min(len(expected),len(actual)));failure=dict(byte=at,word=at//4,reference_bytes=len(expected),simulation_bytes=len(actual),reference_hex=expected[max(0,at-16):at+32].hex(),simulation_hex=actual[max(0,at-16):at+32].hex());(out/'first-divergence.json').write_text(json.dumps(failure,indent=2)+'\n');raise AssertionError(failure)
 proof=coverage(decode(expected,cases),cases);result=dict(passed=True,reference_revision=REFERENCE_REVISION,cases=len(cases),commands=sum(len(c['commands'])for c in cases),bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),input_sha256=hashlib.sha256(inputs).hexdigest(),wire_audit=audit,coverage=proof,boundary='Complete actual ground_query/full_reset/reset/ground_update with real surface investigation and actual FootIK targets; retained settings/state, contact cap/order/connectivity, launch/curves/values/rotations/IK and full PlantMath original bodies. Successful Enter and whole Update await actual root-owned trajectory and air reckoning. PlantSkeleton is implemented against real SkeletonAir/GeneralUpdate but its full scheduling proof is pending. No substitute callback executes; missing-entry query aborts if reached, and the unchanged Rust owner checks the absent candidate before query.')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
