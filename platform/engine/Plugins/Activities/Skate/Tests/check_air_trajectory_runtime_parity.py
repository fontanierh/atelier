#!/usr/bin/env python3
"""Whole original host trajectory/runtime/grind/provider/world differential proof.

Only the parent coordinator builds/runs through the render lock and guard.
--preflight stages source, declarations, actual provider fixtures and histories.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import historical_oracle as historical
import re
import shutil
import struct
import subprocess
import check_air_trajectory_selector_parity as pure
import check_player_grind_input_parity as provider
import check_animation_trees_parity as trees
from check_gesture_parity import PLUGIN,converter
from session_parity import REFERENCE_REVISION
UNITS=(*pure.UNITS,'AirTrajectoryRuntime','AirTrajectoryGrindRuntime','AirTrajectorySelectionRuntime')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def frozen(path):
 return historical.source_text(path)

def block(raw,marker):return trees.extract_block(raw,marker)[0]
CORE_WRAPPERS='''
pub fn runtime_selector_words(s:&super::TrajectorySelector)->Vec<u32>{let mut o=Vec::new();s.migration_observe(&mut o);o}
pub fn runtime_result_words(r:super::QueryResult)->Vec<u32>{let mut o=Vec::new();result(&mut o,r);o}
'''
GRIND_OBSERVER='''
impl Settings{pub(super)fn migration_observe(&self,o:&mut crate::Output){let l=&self.limits;
 for v in[l.lock_distance,l.max_speed_squared_ledge,l.max_speed_squared_rail,l.max_downward_speed]{o.float(v);}for v in l.ledge_scalars{o.float(v);}o.float(l.tip_scalar);o.float(l.maximum_adjust_angle);for v in l.deck_dimensions{o.float(v);}for v in self.height.x.into_iter().chain(self.height.y){o.float(v);}for v in[self.padding,self.maximum_adjust,self.velocity_scalar,self.max_angle,self.score,self.truck_distance,self.penalty_domain]{o.float(v);}
}}
'''
def prepare(output):
 original,observed,snapshot,report=pure.prepare(output);crate=observed/'atelier-host';core=observed/'crates/skate-core/src';core_probe=core/'air/trajectory/migration_probe.rs';core_probe.write_text(core_probe.read_text()+CORE_WRAPPERS)
 simulation_probe=PLUGIN/'Tests/Simulation/air_trajectory_runtime_probe.cpp';rust_probe=PLUGIN/'Tests/Reference/air_trajectory_runtime_probe.rs';observer=PLUGIN/'Tests/Reference/air_trajectory_runtime_observer.rs'
 cpp_provider=(PLUGIN/'Tests/Simulation/player_grind_input_probe.cpp').read_text();rust_provider=(PLUGIN/'Tests/Reference/player_grind_input_probe.rs').read_text()
 cpp_helpers='\n'.join(block(cpp_provider,marker)for marker in ('PlayerGrindStaticProvider ReadProvider(Input& i)','void ObserveProvider(Output& o,const PlayerGrindStaticProvider& p)','WorldGeometry World(unsigned kind)'))
 rust_helpers='\n'.join(block(rust_provider,marker)for marker in ('fn read_provider(i:&mut Input)','fn observe_provider(o:&mut Output','fn fixture_world(kind:u32)'))
 # Borrowed fixture transports use leading-dot literals. Normalize only these
 # generated adapters, preserving every complete original host module byte.
 rust_helpers=re.sub(r'(?<![\w.])\.(\d)',r'0.\1',rust_helpers)
 simulation_prefix=(PLUGIN/'Tests/Simulation/air_trajectory_selector_probe.cpp').read_text().split('int main(',1)[0]
 generated=snapshot/simulation_probe.name;generated.write_text('#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wunused-function"\n'+simulation_prefix+'\n#pragma clang diagnostic pop\n'+simulation_probe.read_text().replace('// GENERATED_PROVIDER_TRANSPORT',cpp_helpers))
 code=PLUGIN/'Source/AtelierSkate/Private/Simulation'
 for unit in UNITS:
  shutil.copy2(code/(unit+'.cpp'),snapshot/(unit+'.cpp'))
 host='crates/skate-host/src/';constants='\n'.join(line for line in frozen(host+'physics/ground.rs').splitlines()if re.match(r'pub\(crate\) const (HEIGHT|FLOOR_HEIGHT):',line))
 module='mod physics{pub mod ground{'+constants+'}pub mod player_input{pub mod grind{pub mod world{'+frozen(host+'physics/player_input/grind/world.rs')+'}}}pub mod air_trajectory{'+frozen(host+'physics/air_trajectory/mod.rs')+'\n'+observer.read_text()+'}}\nmod grind_world{'+frozen(host+'grind_world.rs')+'}\n'
 aliases={}
 for name in ('grind','settings','world','vert_departure'):
  path=host+'physics/air_trajectory/'+name+'.rs';raw=frozen(path);extra=GRIND_OBSERVER if name=='grind'else '';target=crate/'src/physics/air_trajectory'/(name+'.rs');target.parent.mkdir(parents=True,exist_ok=True);assert not target.exists();target.write_text(raw+extra);aliases[target.relative_to(observed).as_posix()]=dict(source=path,prefix_bytes=len(raw.encode()),prefix_sha256=hashlib.sha256(raw.encode()).hexdigest(),append_sha256=hashlib.sha256(extra.encode()).hexdigest())
 for name in ('provider','octree','spline'):
  path=host+'grind_world/'+name+'.rs';raw=frozen(path);target=crate/'src/grind_world'/(name+'.rs');target.parent.mkdir(parents=True,exist_ok=True);assert not target.exists();target.write_text(raw);aliases[target.relative_to(observed).as_posix()]=dict(source=path,prefix_bytes=len(raw.encode()),prefix_sha256=hashlib.sha256(raw.encode()).hexdigest(),append_sha256=hashlib.sha256(b'').hexdigest())
 generated_rs=crate/'src/migration_probe.rs';generated_rs.write_text(rust_probe.read_text().replace('// GENERATED_ORIGINAL_HOST',module).replace('// GENERATED_PROVIDER_TRANSPORT',rust_helpers))
 cargo=crate/'Cargo.toml';text=cargo.read_text().replace('name="air-trajectory-selector-reference"','name="air-trajectory-runtime-reference"');text=text.replace('[[bin]]\nname="air-trajectory-runtime-reference"','bevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}\n[[bin]]\nname="air-trajectory-runtime-reference"');cargo.write_text(text)
 report.update(full_host_sources={path:digest(original/path)for path in(host+'physics/air_trajectory/mod.rs',host+'grind_world.rs',host+'physics/player_input/grind/world.rs')},host_aliases=aliases,core_transport_append_sha256=hashlib.sha256(CORE_WRAPPERS.encode()).hexdigest(),probe_sha256={p.name:digest(p)for p in(simulation_probe,rust_probe,observer)},borrowed_transport_sha256={p.name:digest(p)for p in(PLUGIN/'Tests/Simulation/player_grind_input_probe.cpp',PLUGIN/'Tests/Reference/player_grind_input_probe.rs',PLUGIN/'Tests/Simulation/air_trajectory_selector_probe.cpp',PLUGIN/'Tests/Reference/air_trajectory_selector_probe.rs')},simulation_source_sha256={p.name:digest(p)for p in snapshot.iterdir()},generated_reference_sha256=digest(generated_rs))
 (output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');return original,observed,snapshot,report

def build(output,target):
 original,observed,snapshot,report=prepare(output);crate=observed/'atelier-host';subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(crate/'Cargo.toml'),'--target-dir',str(target.resolve()),'--bin','air-trajectory-runtime-reference'],check=True)
 reference=output/'air-trajectory-runtime-reference';shutil.copy2(target.resolve()/'release/air-trajectory-runtime-reference',reference);simulation=output/'air-trajectory-runtime-simulation';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'air_trajectory_runtime_probe.cpp'),'-o',str(simulation)],check=True)
 for relative,sha in report['original_source_sha256'].items():
  assert digest(original/relative)==sha
  if relative in('crates/skate-core/src/lib.rs','crates/skate-core/src/air/trajectory/mod.rs','crates/skate-core/src/air/trajectory/selector.rs'):
   raw=(original/relative).read_bytes();assert (observed/relative).read_bytes()[:len(raw)]==raw
  else:assert digest(observed/relative)==sha,relative
 for relative,item in report['host_aliases'].items():
  raw=(observed/relative).read_bytes();assert hashlib.sha256(raw[:item['prefix_bytes']]).hexdigest()==item['prefix_sha256'];assert hashlib.sha256(raw[item['prefix_bytes']:]).hexdigest()==item['append_sha256']
 report.update(reference_binary_sha256=digest(reference),simulation_binary_sha256=digest(simulation));(output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');return simulation,reference

def info(n=0,count=7,*,position=(0,3.137,0,1),velocity=(0,-1,3,0),override=True):
 raw=pure.launch(n,count,velocity=list(velocity),position=list(position),override=override)
 # Explicit current physical launch observations, with affine identity lanes.
 raw[:32]=pure.fs([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,0])*2
 raw[32:36]=pure.fs(velocity);raw[36:40]=pure.fs(velocity);raw[48:52]=pure.fs(position);raw[52:56]=pure.fs(position);raw[56:60]=pure.fs(position);raw[60:64]=pure.fs(position);raw[64:67]=pure.fs([0,0,0]);raw[67]=0;return raw

def input_(n=0,*,lock=.731,flags=0,normal=(0,1,0,0),direction=.731,gravity=-9.81):
 raw=pure.selector_input(n,normal=list(normal),direction=direction);raw[:4]=pure.fs([0,gravity,0,0]);raw[4:8]=pure.fs(normal);raw[16:20]=pure.fs([0,1,0,0]);raw[22]=300;raw[23]=flags;raw[24]=0;raw[25]=0;raw[26]=pure.bits(lock);return raw

def context(position=(0,3.137,0,1),body=None,matching=0xffffffff):return pure.fs([*position,*(body or position)])+[17,matching]
def encoded_provider(p):
 w=provider.Stream();provider.encode_provider(w,p);return list(struct.unpack('<'+'I'*(len(w.data)//4),w.data))
def bind(p):return [5]+encoded_provider(p)
def mutate(field,value,integer=False):return [6,field,value&0xffffffff if integer else pure.bits(value)]

def corpus():
 programs=[]
 def add(label,world,commands,**extra):programs.append(dict(index=len(programs),label=label,world=world,commands=commands,**extra))
 # A zero-point rail is invalid in the original reader. An empty provider has
 # no rail records or source sections; both real constructors accept it.
 empty=dict(rails=[],segments=[],guids=[],assets=[],manifest={})
 rail=provider.authored_provider([[0,-.03,-3],[0,-.03,3]],name='actual-rail')
 ledge=provider.authored_provider([[0,-.03,-3],[0,-.03,3]],name='actual-ledge')
 for n in range(72):
  profile=(empty,rail,ledge,provider.stock_provider())[n%4];commands=[bind(profile)]
  for step in range(12):
   x=(-.137,0,.137)[(n+step)%3];z=(-1,0,.731)[step%3];height=(.731,1.7,3.137)[(n+step)%3]
   launch=info(n+step,(1,3,7)[step%3],position=(x,height,z,1),velocity=(.137,(-1,0,3.137)[step%3],(1.137,3.137,5.137)[(n+step)%3],0));inp=input_(n+step,lock=(.1,.317,.731,3.137)[n%4],normal=(0,1,0,0)if step%4 else(0,.137,-.99057,0),direction=(0,.317,.5,.731)[step%4]);ctx=context((x,height,z,1),matching=(0xffffffff,17,31)[step%3])
   # Rebind between submission and completion to witness retention of the
   # actual completed batch, rather than rebinding only after consumption.
   commands += [[0]+launch+inp,bind(profile),[0]+launch+inp,[1]+inp+ctx,[4],[1]+inp+ctx]
   if step%3==0:commands += [[2]]
   if step%4==0:commands += [bind((rail,empty,profile)[step%3])]
   if step%5==0:commands += [[7,(n+step)%9]]
  add('actual stock runtime launch/update, query batches, targets, rebind, actor/pool and world histories',n%9,commands)
 for world in (1,2,3,4,5,6,7,8):
  for lock in (.1,.317,.731,3.137):
   commands=[bind(ledge if world==3 else rail),mutate(1,0),mutate(2,0,True),mutate(3,0)]
   for h in (1.137,2.137,3.137):
    for x in (-.137,0,.137):
     inp=input_(lock=lock);launch=info(count=7,position=(x,h,0,1),velocity=(0,-1,3,0));ctx=context((x,h,0,1));commands += [[0]+launch+inp,[1]+inp+ctx,[1]+inp+ctx,[4],[2]]
   add('actual admitted rail/ledge acquisition and strict lock thresholds; missing world metadata errors',world,commands)
 for n in range(16):
  inp=input_(n);launch=info(n);ctx=context();commands=[[0]+launch+inp,[1]+inp+ctx,[4],[0]+launch+inp,bind(rail),[1]+inp+ctx,[3],[0]+launch+inp,[1]+inp+ctx,bind(empty),[2],[1]+inp+ctx]
  add('missing provider takes completed batch before error and retains selector pending; later binding/cancel',n%6,commands)
 for n in range(16):
  inp=input_(n,normal=(0,.137,-.99057,0),direction=0);launch=info(n,7,velocity=(.38,4.75,.14,0));ctx=context();commands=[bind(empty),mutate(3,0),[0]+launch+inp,[1]+inp+ctx,[4],[1]+inp+ctx,bind(rail),[2],[0]+launch+inp,[1]+inp+ctx,[1]+inp+ctx]
  add('strict vert departure interpretation and complete second-pass submission/completion',n%6,commands)
 # Source Submit collects locally and assigns only on a fully successful batch.
 # A finite maximal carry lane yields a successful centre query followed by an
 # overflowing normalized cone candidate, exercising actual later query errors.
 for n in range(8):
  inp=input_(n);good=info(n,1);bad=info(n,7,velocity=(.1,-.2,.1,struct.unpack('<f',struct.pack('<I',0x7f7fffff))[0]));ctx=context();commands=[bind(rail),[0]+good+inp,[3],[0]+bad+inp,[1]+inp+ctx,[1]+inp+ctx,[2],[3],mutate(0,-.1),[0]+good+input_(gravity=0),[1]+inp+ctx]
  add('partial Submit error preserves old completed batch and exact count-mismatch continuation',1,commands)
 for n in range(24):
  commands=[]
  for y in(.249999,.25,.250001,-.249999):
   for d in(.499999,.5,.500001):commands += [[9]+pure.fs([.01,y,.99,.317,.38,4.75,.14,.137,d])]
  commands += [[8]+pure.request(n),[8]+pure.request(n+1)]
  add('strict departure speed/direction/normal boundaries and actual shared query public leaf',n%9,commands)
 w=provider.Stream();w.word(len(programs))
 for program in programs:
  w.word(program['world']);w.word(len(program['commands']))
  for cmd in program['commands']:
   for word in cmd:w.word(word)
 return bytes(w.data),programs

class Read(pure.Read):pass
def annotate_inputs(raw,cases):
 r=Read(struct.unpack('<'+'I'*(len(raw)//4),raw));assert r.word()==len(cases)
 def text():r.take(r.word())
 def provider_input():
  for _ in range(r.word()):
   text();r.word();r.take(3*r.word())
   if r.word():r.take(r.word())
  text();r.take(24*r.word());r.take(4*r.word())
  for _ in range(r.word()):text();text();r.take(5);r.take(r.word())
 for case in cases:
  assert r.word()==case['world'];assert r.word()==len(case['commands']);case['command_inputs']=[]
  for command in case['commands']:
   start=r.at;op=r.word();assert op==command[0]
   if op==5:provider_input()
   else:r.take({0:97,1:37,2:0,3:0,4:0,6:2,7:1,8:16,9:9}[op])
   assert r.at-start==len(command),(case['index'],op,r.at-start,len(command))
   case['command_inputs'].append(dict(operation=op,first_input_word=start,input_words=r.at-start))
 assert r.at==len(r.w)
def observe_provider(r):
 n=r.word()
 for _ in range(n):
  r.take(10+6+6)
  for _ in range(2):r.take(r.word())
  r.take(6)
 q=r.word();r.take(q);assert q<=40;return n,q

def observe_runtime(r,coverage):
 pure.read_observation(r,coverage);r.take(pure.SETTINGS_WORDS);pending=r.word();count=0
 if pending:count=r.word();r.take(32*count)
 r.take(35);bound=r.word()
 if bound:
  n,q=observe_provider(r);coverage['provider_primitives']+=n;coverage['provider_query_indices']+=q
 nearby=r.word();r.take(nearby);coverage['completed_batches']+=pending;coverage['pending_query_results']+=count;coverage['provider_bound']+=bound;coverage['nearby_indices']+=nearby
 return dict(pending=bool(pending),count=count,bound=bool(bound),nearby=nearby)

def inspect(raw,cases):
 r=Read(struct.unpack('<'+'I'*(len(raw)//4),raw));coverage=Counter()
 for case in cases:
  start=r.at;index,n=r.take(2);assert index==case['index'];end=r.at+n;okay,error=r.status();assert okay and not error;initial=r.word();state_end=r.at+initial;previous=observe_runtime(r,coverage);assert r.at==state_end;commands=r.word();assert commands==len(case['commands']);case['first_output_word']=start;case['output_words']=n+2
  for command in case['commands']:
   op,size=r.take(2);assert op==command[0];command_end=r.at+size;coverage['command_'+str(op)]+=1
   if op==8:okay,error=r.status();r.take(32);coverage['public_query_error']+=not okay
   if op==9:r.take(4)
   okay,error=r.status();value=r.word();coverage['success'if okay else'failure']+=1
   if not okay:coverage['error_'+error]+=1;assert error
   n=r.word();state_end=r.at+n;current=observe_runtime(r,coverage);assert r.at==state_end
   if op==5:
    assert current['nearby']==0;assert current['pending']==previous['pending']and current['count']==previous['count'];coverage['rebind_preserved_batch']+=current['pending']
   if error=='Trajectory static grind provider was not registered':assert previous['pending']and not current['pending'];coverage['missing_provider_take']+=1
   previous=current;assert r.at==command_end,(case['index'],op,r.at,command_end)
  assert r.at==end
 assert r.at==len(r.w)
 for key in('completed_batches','nearby_indices','candidate_grind_targets','selected_grind_targets','valid','pending','missing_provider_take','rebind_preserved_batch'):
  assert coverage[key]>0,('missing actual host branch coverage',key)
 assert coverage['error_Trajectory completion count differs from submitted batch']>0
 assert coverage['error_Non-finite trajectory collision request or invalid radius']>0
 assert coverage['pass_2']and coverage['pass_3']
 return dict(coverage)

def loader_fixtures(output,assets):
 data=json.loads((assets/'private/stock/skater-collections.json').read_text());source=frozen('crates/skate-host/src/physics/air_trajectory/grind.rs').split('    pub fn evaluate(',1)[0];spec=[]
 names=[('physics_trajectory',name)for name in re.findall(r't\("([^"]+)"\)',source)]
 names +=[('physicsdeck','DeckMidLength'),('physicsdeck','DeckFrontEndSize'),('physics_grinds','DeckCenterToTruck'),('physics_trajectory','RequiredAngleVsHeight'),('physics_trajectory','GrindPenaltyVsDistToGrind')]
 def field(d,cat,name):
  for record in d['collections']:
   if converter.name_id(record['class'])==converter.name_id(cat)and converter.name_id(record['key'])==converter.name_id('default'):
    for key in record['fields']:
     if converter.name_id(key)==converter.name_id(name):return record['fields'],key
  raise AssertionError((cat,name))
 for cat,name in names:
  for failure in('missing','type','words'):
   d=copy.deepcopy(data);fields,key=field(d,cat,name)
   if failure=='missing':del fields[key]
   elif failure=='type':fields[key]['type']='EA::Reflection::Bool'
   else:fields[key]['data']+='CAFEBABE'
   label=f'{cat}-{name}-{failure}';stock=output/'asset-fixtures'/label/'private/stock';stock.mkdir(parents=True,exist_ok=True);path=stock/'skater-collections.json';path.write_text(json.dumps(d));bank=stock.parents[1]/'settings.simulation';bank.write_bytes(converter.encode_settings(path));spec.append(dict(label=label,assets=stock.parents[1],bank=bank))
 return spec

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);assets=a.assets.resolve();raw,cases=corpus();annotate_inputs(raw,cases);(out/'input.bin').write_bytes(raw);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');bank=out/'settings.simulation';bank.write_bytes(converter.encode_settings(assets/'private/stock/skater-collections.json'));fixtures=loader_fixtures(out,assets)
 if a.preflight:
  _,_,_,report=prepare(out);print(json.dumps(dict(cases=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(raw),loader_fixtures=len(fixtures),input_sha256=hashlib.sha256(raw).hexdigest(),simulation_units=len(UNITS),source_archive_sha256=report['source_archive_sha256']),indent=2));return
 for name in('result.json','first-divergence.json'):(out/name).unlink(missing_ok=True)
 simulation,reference=build(out,a.target_dir);e=subprocess.check_output([str(reference),str(assets)],input=raw,timeout=180);v=subprocess.check_output([str(simulation),str(bank)],input=raw,timeout=180);(out/'reference.bin').write_bytes(e);(out/'simulation.bin').write_bytes(v)
 if e!=v:
  first=next((i for i,(x,y)in enumerate(zip(e,v))if x!=y),min(len(e),len(v)));report=dict(first_word=first//4,reference_bytes=len(e),simulation_bytes=len(v),reference_hex=e[max(0,first//4*4-16):first//4*4+32].hex(),simulation_hex=v[max(0,first//4*4-16):first//4*4+32].hex());(out/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
 coverage=inspect(e,cases);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');reports=[]
 for fixture in fixtures:
  data=struct.pack('<I',1);expected=subprocess.check_output([str(reference),str(fixture['assets'])],input=data);actual=subprocess.check_output([str(simulation),str(fixture['bank'])],input=data);assert expected==actual,fixture['label'];r=Read(struct.unpack('<'+'I'*(len(expected)//4),expected));assert r.word()==0;size=r.word();end=r.at+size;okay,error=r.status();assert not okay and error;assert r.at==end==len(r.w);reports.append(dict(label=fixture['label'],error=error,exact_words=len(expected)//4,sha256=hashlib.sha256(expected).hexdigest()))
 result=dict(passed=True,cases=len(cases),commands=sum(len(c['commands'])for c in cases),exact_words=len(e)//4+sum(r['exact_words']for r in reports),stock_output_sha256=hashlib.sha256(e).hexdigest(),coverage=coverage,loader_fixtures=reports,comparison='Complete unchanged original active host selector/launch/grind/settings/query/provider owners and all retained state/errors match exact words. Actual original StaticProvider constructs from rails/simulation blob/WMET independently of the simulation-side converted transport.',limitations='Authored triangle/rail/package geometry is the explicit engine input boundary; no completed hits or neutral services are seeded. This proves the active trajectory host family, not whole air-state/session scheduling. Nonadvancing source query inputs are excluded from executable valid-domain histories.')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':historical.run_cli(main)
