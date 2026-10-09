#!/usr/bin/env python3
"""Exact pure selector/launch/scoring/grind and ordered original stock loader.

Only the parent coordinator compiles/executes through atelier.safety. --preflight
stages immutable original source, transport and corpus without compiling.
"""
import argparse
from collections import Counter
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import historical_oracle as historical
import random
import re
import shutil
import struct
import subprocess
import tarfile
from check_gesture_parity import PLUGIN,converter
from session_parity import REFERENCE_REVISION
UNITS=('SimulationMath','Geometry','GeometrySweep','WorldGeometry','AirTrajectoryQuery','PlayerGrindSurface','PlayerGrindInputWorld','Settings','NameId','StockSettingsReader','AirTrajectoryLaunch','AirTrajectoryGrind','AirTrajectoryScoring','AirTrajectorySelector','AirTrajectorySelectorSettings')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def fs(v):return list(map(bits,v))
def fields():
 text=historical.source_text('crates/skate-core/src/air/trajectory/types.rs').split('pub struct SelectorSettings {',1)[1].split('\n}',1)[0]
 return re.findall(r'pub (\w+): (f32|i32|PointGraph<\d+>)',text)
SETTINGS_WORDS=sum(2*int(ty[11:-1])if ty.startswith('PointGraph')else 1 for _,ty in fields())
def matrix(angle=0,translation=(0,0,0,0)):
 c,s=math.cos(angle),math.sin(angle);return fs([c,0,-s,.137,0,1,0,.317,s,0,c,.731,*translation])
def graph(constant=0):return fs([-.5,0,.25,.5,1,2,5,10]+[constant]*8)
def trajectory(position=(.137,3.7,.137,.317),velocity=(.731,2.137,1.137,.137),gravity=-9.81,duration=3):return fs([*position,*velocity,.013,gravity,.017,.071,duration])
def request(n=0):return trajectory(position=(.137,3.7+(n%5)*.317,.137,.317),velocity=((n%3)*.317,(-1,0,2.137,4.731)[n%4],(.137,.731,2.731,5.137)[n%4],.137))+fs([.1,.25,.5])
def launch(n=0,count=7,*,velocity=None,position=None,override=False):
 velocity=velocity or[(n%3)*.317,(-1,0,2.137,4.731)[n%4],(.137,.731,2.731,5.137)[n%4],.137]
 position=position or [.137,3.7+(n%5)*.317,.137,.317]
 raw=matrix(n*.0317)+matrix(-n*.0317)+fs(velocity+[.731,4.137,.317,.731]+[.137,.731,.317,.517]+[.731,.137,.517,.317]+[.137,.317,.731,.137]+position+[.137,5.137,.317,.731]+[.731,3.137,.517,.317])+fs([0 if n%5==0 else 17,0 if n%7==0 else 13,(0,1/60,.0317)[n%3]])+[n%2,int(override),count]
 assert len(raw)==70;return raw
def selector_input(n=0,*,normal=None,direction=None):
 return fs([.013,-9.81,.017,.071]+(normal or([0,1,0,.137]if n%3==0 else[0,.3,.953939,.317]))+[0,0,0,.137]+[.137,0,1,.317]+[0,1,0,.731]+[(-2,0,4.731)[n%3],(-.731,.317,.5,.731)[n%4]if direction is None else direction])+[(0,200,300)[n%3],(0,0x20000000)[n%2],(0,0x02000000)[n%5==0],(0,0x04000000,0x0c000000)[n%3]]+fs([(.317,.5,3.137)[n%3]])
def evaluator(n=0):
 return fs([3.137,100,100,200,1,1,.317,.731,0,180,.6,.2])+graph()+fs([.137,3.137,.731,.137,.731,3.7,.317,.731])+fs([.0317,100,.137,45,5000,1.137,.3])
def world(kind):
 floor=[([-12,0,-12],[12,0,12],[12,0,-12]),([-12,0,-12],[-12,0,12],[12,0,12])]
 wall=[([-12,0,1],[12,8,1],[12,0,1]),([-12,0,1],[-12,8,1],[12,8,1])]
 ramp=[([-12,-2,-12],[12,2,12],[12,2,-12]),([-12,-2,-12],[-12,2,12],[12,2,12])]
 triangles=(floor,floor+wall,ramp,wall,[],floor+floor)[kind%6];raw=[len(triangles)]
 for i,t in enumerate(triangles):raw+=fs([x for v in t for x in v]+[0])+[0x10,(0,6<<7,7<<7,8<<7)[kind//6%4],(1,6<<7,7<<7,8<<7)[kind//6%4]]
 return raw
def edges(n=0,mode=0):
 records=[]
 for k in range((0,1,4,9)[mode%4]):
  y=.731+k*.0137;z=(-.137,.137,.731,1.137)[k%4]
  records+=fs([-4,y,z,.137,4,y+(k%3)*.0317,z,.317])+[k+1,0x12345678+n]
 return [len(records)//10]+records

def corpus():
 rng=random.Random(0x82d67848);records=[];cases=[]
 def add(label,op,args,n=0,mode=0,variant=0,custom_edges=None,**meta):
  raw=world(n)+ (edges(n,mode)if custom_edges is None else custom_edges)+[op,variant]+args
  cases.append(dict(index=len(cases),label=label,operation=op,**meta));records.append(struct.pack('<'+'I'*len(raw),*raw))
 for n in range(256):
  count=(0,1,2,3,4,5,6,7,8,65535)[n%10]
  add('complete launch cone, override, vert adjustment and local four-lane batch',0,launch(n,count,override=n%3==0)+selector_input(n),n,variant=n%16)
 for axis in range(3):
  for length in (0.,-0.,1e-7,1e-6,.001,1,1000):
   velocity=[0.,0.,0.,-.0];velocity[axis]=length
   add('zero/minimum normal and large finite launch kernels',0,launch(axis,7,velocity=velocity)+selector_input(axis),variant=axis%4)
 for n in range(512):
  primitives=[];count=2+n%7
  for k in range(count):
   if n%3==0:dx,dy,dz=4,(k%2)*.0001,0
   else:dx,dy,dz=rng.uniform(.1,4),rng.uniform(-.1,.1),rng.uniform(-1,1)
   start=[rng.uniform(-1,1),k*(.01,.02,.1)[n%3],rng.uniform(-.01,.01),.137];end=[start[0]+dx,start[1]+dy,start[2]+dz,.317]
   primitives+=fs(start+end)+[k+1,0x12345678+n]
  indices=list(range(count));rng.shuffle(indices)
  if n%5==0:indices+=indices[:2]
  add('ordered duplicate/parallel/overlap primitive box filter',1,fs([.137,.731,.317,.137])+[len(indices)]+indices,custom_edges=[count]+primitives)
 for n in range(1024):
  g=(-9.81,-.0001,0,1,9.81)[n%5];v=(-9,-1,-.0,0,1,9)[n%6]
  t=trajectory(position=(.137,(n%7)*.317,.137,.517),velocity=(.731,v,.317,.137),gravity=g)
  normal=[rng.uniform(-1,1)for _ in range(3)]+[.317]
  if n%3==0:normal=[0,1,0,.137]
  add('descending plane quadratic signed zero, double-root and later-root domains',2,t+fs([.317,(n%11)*.137,.731,.317]+normal))
 for n in range(256):
  add('actual world prediction feeds all primitive candidates and stable retry ranking',3,request(n)+fs([(.0,.0317,.5)[n%3],(.1,.317,3.137)[n%3]])+graph((-.731,0,.731)[n%3]),n,mode=1+n%3)
 for n in range(128):
  commands=[]
  inp=selector_input(n);info=launch(n,1 if n%5==0 else 7,override=n%3==0)
  commands+=[[2],[4],[0]+info+inp,[0]+launch(n+1)+selector_input(n+1)]
  commands+=[[5]+inp+[0],[1]+inp+[n%5],[2],[1]+selector_input(n+1)+[0],[2],[4],[2],[1]+inp+[0]]
  commands+=[[0]+launch(n+2,7)+selector_input(n+2),[3],[1]+inp+[0],[0]+launch(n+3,0)+inp]
  commands+=[[0]+launch(n+4,7)+inp,[1]+inp+[0],[1]+inp+[0],[4],[0]+launch(n+5,1)+inp,[1]+inp+[0]]
  add('full retained selector two-pass, duplicate launch, wrong counts, errors, reset and cancellation',4,evaluator(n)+[len(commands)]+[x for c in commands for x in c],n,mode=n%4,variant=n%16,commands=[c[0]for c in commands])
 # Dedicated wall and admitted-grind fixtures establish service mutation/error coverage.
 for n in range(24):
  info=launch(n,7,velocity=[0,3.137,.137,.317],position=[0,3.731,0,.517]);inp=selector_input(2,normal=[0,1,0,.317],direction=.731)
  commands=[[0]+info+inp,[1]+inp+[0],[1]+inp+[0],[4],[0]+info+inp,[1]+inp+[2],[2]]
  add('real surface admission then deliberate failure retains changed prediction',4,evaluator(n)+[len(commands)]+sum(commands,[]),0,mode=2,variant=1,commands=[c[0]for c in commands])
 for n in range(128):
  add('complete scoring with actual queries, wall bonuses, force/transition/material and callback errors',5,launch(n,(1,7,3)[n%3])+selector_input(n)+[(1,2,3)[n%3],n%2]+evaluator(n)+[n%5],n,mode=n%4,variant=n%16)
 return struct.pack('<I',len(records))+b''.join(records),cases

OBSERVER=r'''
impl TrajectorySelector {
 pub(super)fn migration_observe(&self,out:&mut Vec<u32>){use super::migration_probe as o;
 out.push(self.launch_info.is_some()as u32);if let Some(v)=self.launch_info{o::launch_info(out,v);}
 out.push(self.batch.is_some()as u32);if let Some(b)=&self.batch{o::batch(out,b);}
 out.push(self.candidates.len()as u32);for &c in &self.candidates{o::candidate(out,c);}
 out.push(self.selection.is_some()as u32);if let Some(v)=self.selection{o::selection(out,v);}
 out.push(self.selected_index.is_some()as u32);if let Some(v)=self.selected_index{out.push(v as u32);}
 out.push(self.grind_locked_to_middle as u32);o::optional_vector(out,self.grind_normal);
 out.extend([u32::from(self.pass),self.adjusted_on_vert as u32,self.pending as u32,self.valid as u32,self.just_changed as u32,self.all_predictions_missed as u32]);o::optional_vector(out,self.suggested_normal);
 }
}
'''
ENTRY=r'''
use std::io::{Read,Write};
#[path="air-selector-settings.rs"]mod selector_settings;
use skate_core::air::trajectory::migration_probe as probe;
fn main(){let assets=std::path::PathBuf::from(std::env::args().nth(1).unwrap());let data=skate_data::collections::Collections::load(&assets).unwrap();let settings=selector_settings::load(&data);let mut out=Vec::new();match settings{Ok(s)=>{probe::status(&mut out,None);probe::settings(&mut out,&s);let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();out.extend(probe::run(bytes,&s));},Err(e)=>probe::status(&mut out,Some(&e))};let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for w in out{stdout.write_all(&w.to_le_bytes()).unwrap();}}
'''
def prepare(output):
 revision=historical.reference_identity()['reference_commit'];archive=historical.source_archive()
 source=output/'original-source';observed=output/'reference-source'
 for p in (source,observed):
  if p.exists():shutil.rmtree(p)
 source.mkdir()
 with tarfile.open(fileobj=io.BytesIO(archive))as stream:stream.extractall(source,filter='data')
 originals={p.relative_to(source).as_posix():digest(p)for p in sorted(source.rglob('*.rs'))};shutil.copytree(source,observed)
 core=observed/'crates/skate-core/src';appends={'lib.rs':'\nextern crate self as skate_core;\n','air/trajectory/mod.rs':'\npub mod migration_probe;\n','air/trajectory/selector.rs':OBSERVER}
 for path,extra in appends.items():
  p=core/path;original=(source/'crates/skate-core/src'/path).read_bytes();p.write_bytes(original+extra.encode());assert p.read_bytes()[:len(original)]==original
 for destination,origin in (('migration_air_world.rs','physics/air_trajectory/world.rs'),('migration_grind_world.rs','physics/player_input/grind/world.rs')):
  p=core/'air/trajectory'/destination;raw=(source/'crates/skate-host/src'/origin).read_bytes();p.write_bytes(raw);assert p.read_bytes()==raw
 probe=PLUGIN/'Tests/Reference/air_trajectory_selector_probe.rs';shutil.copy2(probe,core/'air/trajectory/migration_probe.rs')
 crate=observed/'atelier-host';(crate/'src/migration_probe.rs').write_text(ENTRY);host_settings=source/'crates/skate-host/src/physics/air_trajectory/settings.rs';shutil.copy2(host_settings,crate/'src/air-selector-settings.rs')
 cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text()+'''\nskate-core={path="../crates/skate-core"}
skate-data={path="../crates/skate-data"}
[[bin]]
name="air-trajectory-selector-reference"
path="src/migration_probe.rs"
''')
 code=PLUGIN/'Source/AtelierSkate/Private/Simulation';snapshot=output/'simulation-source'
 if snapshot.exists():shutil.rmtree(snapshot)
 snapshot.mkdir()
 for p in list(code.glob('*.h'))+[code/(u+'.cpp')for u in UNITS]:shutil.copy2(p,snapshot/p.name)
 cpp=PLUGIN/'Tests/Simulation/air_trajectory_selector_probe.cpp';shutil.copy2(cpp,snapshot/cpp.name)
 provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,source_observer_appends={path:hashlib.sha256(extra.encode()).hexdigest()for path,extra in appends.items()},host_settings_sha256=digest(host_settings),simulation_source_sha256={p.name:digest(p)for p in snapshot.iterdir()},probe_sha256={p.name:digest(p)for p in(probe,cpp)})
 (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
 return source,observed,snapshot,provenance

def build(output,target):
 source,observed,snapshot,report=prepare(output);crate=observed/'atelier-host'
 subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(crate/'Cargo.toml'),'--target-dir',str(target.resolve()),'--bin','air-trajectory-selector-reference'],check=True)
 reference=output/'air-trajectory-selector-reference';shutil.copy2(target.resolve()/'release/air-trajectory-selector-reference',reference)
 simulation=output/'air-trajectory-selector-simulation';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'air_trajectory_selector_probe.cpp'),'-o',str(simulation)],check=True)
 for relative,expected in report['original_source_sha256'].items():
  assert digest(source/relative)==expected
  if relative in ('crates/skate-core/src/lib.rs','crates/skate-core/src/air/trajectory/mod.rs','crates/skate-core/src/air/trajectory/selector.rs'):
   original=(source/relative).read_bytes();assert (observed/relative).read_bytes()[:len(original)]==original
  else:assert digest(observed/relative)==expected,(relative,'numeric source changed')
 report.update(reference_binary_sha256=digest(reference),simulation_binary_sha256=digest(simulation));(output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');return simulation,reference

class Read:
 def __init__(self,words):self.w=words;self.at=0
 def take(self,n):v=self.w[self.at:self.at+n];assert len(v)==n;self.at+=n;return v
 def word(self):return self.take(1)[0]
 def optional(self,n):return self.take(n)if self.word()else None
 def status(self):okay,n=self.take(2);return okay,bytes(self.take(n)).decode()
def read_candidate(r,coverage):
 r.take(67);target=r.optional(38);coverage['candidate_grind_targets']+=int(target is not None)
def read_observation(r,coverage):
 r.optional(70)
 if r.word():
  n=r.word();r.take(n*16);m=r.word();r.take(m*4+20);assert m==n;coverage['batch_requests']+=n
 n=r.word()
 for _ in range(n):read_candidate(r,coverage)
 if r.word():r.take(80);target=r.optional(38);coverage['selected_grind_targets']+=int(target is not None)
 r.optional(1);r.word();r.optional(4);p,adjusted,pending,valid,changed,missed=r.take(6);r.optional(4)
 coverage['pass_'+str(p)]+=1;coverage['adjusted_vert']+=adjusted;coverage['pending']+=pending;coverage['valid']+=valid;coverage['just_changed']+=changed;coverage['all_missed']+=missed
def read_trace(r,coverage):
 n=r.word();end=r.at+n
 while r.at<end:
  kind=r.word();coverage['callback_'+str(kind)]+=1
  if kind==1:
   middle=r.word();before=r.take(48);after=r.take(48);coverage['acquisition_callbacks']+=middle;coverage['callback_prediction_mutations']+=before!=after
  else:assert kind==2;r.take(9)
 assert r.at==end

def inspect(data,cases):
 words=struct.unpack('<'+'I'*(len(data)//4),data);r=Read(words);okay,error=r.status();assert okay and not error;r.take(SETTINGS_WORDS);coverage=Counter()
 for case in cases:
  start=r.at;index,op,n=r.take(3);assert index==case['index']and op==case['operation'];end=r.at+n;case.update(first_output_word=start,output_words=n+3);coverage['operation_'+str(op)]+=1
  if op==0:r.take(71);requests=r.word();r.take(requests*16);velocities=r.word();assert velocities==requests;r.take(velocities*4+20);coverage['launch_requests']+=requests
  elif op==1:count=r.word();r.take(count);coverage['filtered_primitives']+=count
  elif op==2:coverage['plane_roots']+=int(r.optional(1)is not None)
  elif op==3:
   okay,error=r.status();assert okay and not error;r.take(32)
   # One optional candidate for each transported authored primitive.
   # Corpus metadata stores this exact count independently.
   for _ in range(case['primitive_count']):
    present=r.word();coverage['geometric_candidates']+=present
    if present:r.take(21)
   count=r.word();r.take(count*21);assert r.word()==0;coverage['ranked_candidates']+=count
  elif op==4:
   count=r.word();assert count==len(case['commands']);read_observation(r,coverage)
   for command in case['commands']:
    assert r.word()==command;okay,error=r.status();coverage['command_'+str(command)]+=1;coverage['success'if okay else'failure']+=1
    if not okay:assert error;coverage['error_'+error]+=1
    r.word();read_observation(r,coverage);read_trace(r,coverage)
  elif op==5:
   # Query status/result is emitted for every source launch request.
   for _ in range(case['launch_count']):okay,error=r.status();assert okay and not error;r.take(32)
   okay,error=r.status();coverage['success'if okay else'failure']+=1;r.word();count=r.word()
   for _ in range(count):read_candidate(r,coverage)
   read_trace(r,coverage)
  assert r.at==end,(case,r.at,end)
 assert r.at==len(words)
 for key in ('launch_requests','filtered_primitives','plane_roots','geometric_candidates','ranked_candidates','callback_1','callback_2','callback_prediction_mutations','valid','pending','just_changed','adjusted_vert','selected_grind_targets','failure'):
  assert coverage[key]>0,('missing actual branch coverage',key)
 assert coverage['pass_2']>0 and coverage['pass_3']>0
 return dict(coverage)

def annotate_cases(data,cases):
 # Lightweight independent protocol inventory, without invoking either runtime.
 words=struct.unpack('<'+'I'*(len(data)//4),data);r=Read(words);assert r.word()==len(cases)
 for c in cases:
  n=r.word();r.take(n*13);e=r.word();r.take(e*10);op,mode=r.take(2);assert op==c['operation'];c['primitive_count']=e;c['variant']=mode
  if op==0:r.take(97)
  elif op==1:r.take(4);r.take(r.word())
  elif op==2:r.take(21)
  elif op==3:r.take(34)
  elif op==4:
   r.take(43);n=r.word();assert n==len(c['commands'])
   for command in c['commands']:
    assert r.word()==command
    if command==0:r.take(97)
    elif command in(1,5):r.take(28)
  elif op==5:
   launch=r.take(70);c['launch_count']=min(launch[-1],7);r.take(27+2+43+1)
 assert r.at==len(words),(r.at,len(words))

def variants(output,assets):
 data=json.loads((assets/'private/stock/skater-collections.json').read_text());spec=[]
 host=historical.source_text('crates/skate-host/src/physics/air_trajectory/settings.rs')
 # Every field's local failure is checked after all preceding original reads.
 ordered=[('physics_trajectory',name,'scalar')for name in re.findall(r't\("([^"]+)"\)',host)]
 ordered +=[('physics_reckoning',name,'scalar')for name in re.findall(r'r\("([^"]+)"\)',host)]
 ordered +=[('physics_feet','WallRideMaxDotFloorWall','scalar'),('physics_reckoning','MinTrajectorySize','integer')]
 ordered += [('physics_trajectory',name,'graph')for name in ('ConeAngleZVsSpeed','LandingTimeBonus','LandingComScalarVsSlope','LandingForceScalarVsDPVelNorm','GrindPenaltyVsDistToGrind','WallRideBoost')]
 ordered +=[('physics_reckoning',name,'graph')for name in ('TrajectoryDispVsSpeed','TrajectoryDispVsGroundNorm')]
 def field(d,category,name):
  for record in d['collections']:
   if converter.name_id(record['class'])==converter.name_id(category)and converter.name_id(record['key'])==converter.name_id('default'):
    for key in record['fields']:
     if converter.name_id(key)==converter.name_id(name):return record['fields'],key
  raise AssertionError((category,name,'missing fixture field'))
 for category,name,kind in ordered:
  for failure in ('missing','type','words','two_words','nan')if kind=='scalar'else('missing','type','words','nonfinite_graph')if kind=='graph'else('missing','type','words','two_words','negative_bits'):
   d=copy.deepcopy(data);f,key=field(d,category,name)
   if failure=='missing':del f[key]
   elif failure=='type':f[key]['type']='EA::Reflection::Bool'
   elif failure=='words':f[key]['data']='DEADBEEF'
   elif failure=='two_words':f[key]['data']+='CAFEBABE'
   elif failure=='nan':f[key]['data']='7FC12345'
   elif failure=='nonfinite_graph':
    offset=32 if f[key]['type'].startswith('Sk8::PointNegGraph')else 0
    f[key]['data']=f[key]['data'][:offset]+'7FC12345'+f[key]['data'][offset+8:]
   elif failure=='negative_bits':f[key]['data']='FFFFFFFF'
   # Preserve the existing one-word bits fixture: scalar/integer readers accept
   # that width. A separate stock-plus-one-word fixture tests their rejection.
   label=f'{category}-{name}-'+('one_word_bits'if failure=='words'and kind!='graph'else failure);stock=output/'asset-fixtures'/label/'private/stock';stock.mkdir(parents=True,exist_ok=True);path=stock/'skater-collections.json';path.write_text(json.dumps(d));bank=output/'asset-fixtures'/label/'settings.simulation';bank.write_bytes(converter.encode_settings(path));spec.append(dict(label=label,assets=stock.parents[1],bank=bank,success=failure in('nonfinite_graph','negative_bits')or(failure=='words'and kind!='graph')))
 return spec

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);assets=a.assets.resolve();data,cases=corpus();annotate_cases(data,cases);(out/'input.bin').write_bytes(data);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');bank=out/'settings.simulation';bank.write_bytes(converter.encode_settings(assets/'private/stock/skater-collections.json'));fixture_list=variants(out,assets)
 if a.preflight:
  _,_,_,report=prepare(out);print(json.dumps(dict(cases=len(cases),input_bytes=len(data),loader_fixtures=len(fixture_list),settings_words=SETTINGS_WORDS,units=UNITS,input_sha256=hashlib.sha256(data).hexdigest(),source_archive_sha256=report['source_archive_sha256']),indent=2));return
 for name in('result.json','first-divergence.json'):(out/name).unlink(missing_ok=True)
 simulation,reference=build(out,a.target_dir)
 expected=subprocess.check_output([str(reference),str(assets)],input=data,timeout=120);actual=subprocess.check_output([str(simulation),str(bank)],input=data,timeout=120);(out/'reference.bin').write_bytes(expected);(out/'simulation.bin').write_bytes(actual)
 if expected!=actual:
  at=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));report=dict(first_word=at//4,reference_bytes=len(expected),simulation_bytes=len(actual),reference_hex=expected[max(0,at//4*4-16):at//4*4+32].hex(),simulation_hex=actual[max(0,at//4*4-16):at//4*4+32].hex());(out/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
 coverage=inspect(expected,cases);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');fixture_reports=[]
 empty=struct.pack('<I',0)
 for fixture in fixture_list:
  e=subprocess.check_output([str(reference),str(fixture['assets'])],input=empty);v=subprocess.check_output([str(simulation),str(fixture['bank'])],input=empty);assert e==v,fixture['label'];r=Read(struct.unpack('<'+'I'*(len(e)//4),e));okay,error=r.status();assert okay==fixture['success'],(fixture['label'],okay,error)
  if okay:r.take(SETTINGS_WORDS)
  else:assert error
  assert r.at==len(r.w);fixture_reports.append(dict(label=fixture['label'],success=bool(okay),error=error,exact_words=len(e)//4,sha256=hashlib.sha256(e).hexdigest()))
 result=dict(passed=True,cases=len(cases),exact_words=len(expected)//4+sum(r['exact_words']for r in fixture_reports),stock_output_sha256=hashlib.sha256(expected).hexdigest(),coverage=coverage,loader_fixtures=fixture_reports,comparison='All complete retained owner fields, ordered callbacks and loader values/errors exact. Original numerical source prefixes and complete unchanged modules hash verified.',limitations='Pure selector service proof uses explicit canonical primitive-vector provider boundary and real original/simulation geometry surface probes plus candidate/admission. This is not the full host provider broadphase/nearby retention/metadata error or AirTrajectoryRuntime pending-batch scheduling proof; root owns those. No completed trajectory or grind hits are seeded. Nonadvancing original query horizons remain outside the valid source execution corpus.')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':historical.run_cli(main)
