#!/usr/bin/env python3
"""Actual deferred Biped Ground geometry and complete ordered world/edge scene.

Only the root coordinator builds/runs this proof. The full original state,
SceneService and world/edge/line/transform sources remain unchanged. Engine
authored edge-provider records are explicit borrowed fixture inputs.
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
from reference_build import build_probe
from check_skeleton_input_runtime_parity import source
from check_gesture_parity import converter
from check_offboard_contact_parity import PLUGIN,make_world,encode_world,quad,fs,bits,Reader
HOST='crates/skate-host/src/physics/offboard/'
UNITS=('SimulationMath','Geometry','GeometrySweep','WorldGeometry','NameId','Settings','StockSettingsReader','OffboardGroundQuery','OffboardGroundConsume','OffboardGroundScene','OffboardGroundGeometry')
IDENTITY=[1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.]
def frame(position=(0,0,0),angle=0):
 c,s=math.cos(angle),math.sin(angle);return [c,0,-s,0,1,0,s,0,c]+list(position)
def native_frame(f,w=0):return fs(sum((f[n:n+3]+[w if n==9 else 0]for n in range(0,12,3)),[]))
def submit(f,speed=3,flags=0,selection=0,group=-1):return [0]+native_frame(f,.137)+fs([0,0,speed,.517])+[selection,group&0xffffffff,flags]
def consume(f,contact=(0,0,0),flags=1,reach=2,up=(0,1,0)):return [1]+fs(f+list(contact))+[flags]+fs([reach]+list(up))
def body(f,edges,bounds=None):
 segments=[]
 for a,b in edges:segments.append(a+b+[min(a[n],b[n])for n in range(3)]+[max(a[n],b[n])for n in range(3)])
 flat=sum((a+b for a,b in edges),[]);bounds=bounds or([min(flat[n::3])for n in range(3)]+[max(flat[n::3])for n in range(3)])
 return dict(frame=f,bounds=bounds,segments=segments)
def registry(n):
 bodies=[body(frame(),[([-1,.03,0],[1,.03,0])]),body(frame((0,0,0),.25),[([-1,.01,.15],[1,.01,.15])],[-100,90,-100,-90,100,-90]),body(frame((15,0,0)),[([-16,0,0],[-14,0,0])]),body(frame((14.999,0,0)),[([-16,0,.05],[-14,0,.05])]),body(frame((0,0,0),-.1),[([-1,-.01,.1+i*.002],[1,-.01,.1+i*.002])for i in range(48)])]
 return dict(bodies=bodies,dynamic=[2,3,1,0,4],vehicles=[0,1],alternate=[(False,[(True,0,-1),(True,1,-1)]),(True,[(True,1,n%3),(True,0,(n+1)%3)]),(True,[(False,0,0),(True,4,-1)])],indexed=[(90,False,1),(3,False,0),(3,False,4),(0,True,3)],mode=bool(n%2))
def encode_registry(v):
 words=[len(v['bodies'])]
 for b in v['bodies']:words+=fs(b['frame']+b['bounds'])+[len(b['segments'])]+sum((fs(s)for s in b['segments']),[])
 words += [len(v['dynamic'])]+v['dynamic']+[len(v['vehicles'])]+v['vehicles']+[len(v['alternate'])]
 for enabled,choices in v['alternate']:
  words += [int(enabled)]
  for some,index,group in choices:words += [int(some),index,group&0xffffffff]
 words += [len(v['indexed'])]
 for identity,disabled,index in v['indexed']:words += [identity,int(disabled),index]
 return words+[int(v['mode'])]
def corpus():
 rng=random.Random(0x82d32808);edge=[([-1,0,0],[1,0,0])];floor=quad(-5,5,-5,5,0,0);behind=quad(-5,5,-5,0,0,0);strip=quad(-5,5,-.12,-.06,0,0);ramp=quad(-5,5,-1,1,1,-1)
 worlds=[make_world([(p,0,-1,0)],edge)for p in(floor,behind,strip,ramp)]
 worlds += [make_world([],edge),make_world([(floor,2,-1,0)],edge,island=1),make_world([(floor,2,-1,0)],edge,island=3),make_world([(floor,1,2,0),(floor,0,1,0)],edge),make_world([(floor,0,-1,0)],enabled=False),make_world([])]
 v=make_world([(behind,0,-1,0)],edge);v['surfaces']=[0x400]*len(v['surfaces']);worlds.append(v)
 worlds.append(make_world([(floor,0,-1,0)],[([-1,0,i*.001],[1,0,i*.001])for i in range(64)]))
 programs=[]
 for n in range(128):
  commands=[];world=copy.deepcopy(worlds[n%len(worlds)])
  for k in range(12):
   f=frame((rng.uniform(-.15,.15),(0,.01,-.01,.19)[k%4],rng.uniform(-.1,.1)),(0,.07,-.08)[k%3]);flags=(0,0x08000000)[k%2];speed=(0,.9,1,1.01,3)[(n+k)%5];group=(-1,0,1,2)[(n+k)%4]
   commands += [consume(f,flags=(0,1,0x11,0x21,0x31,8)[k%6],reach=(0,.6,.71,2)[k%4]),submit(f,speed,flags,n%4,group)]
   if k in(2,8):commands += [[3]+encode_world(worlds[(n+1)%len(worlds)]),consume(f)]
   if k==5:commands += [[2],consume(f)]
   if k in(3,9):commands += [[4]+fs(f)+[n%4,group&0xffffffff]+fs([0,0,speed])+[flags]+encode_registry(registry(n+k))]
  commands += [consume(frame(),reach=4),consume(frame())];programs.append(dict(label='actual deferred edge/seven-line state, replacement, contact fallback and all provider orders',world=world,commands=commands))
 for word in(0,0x80000000,1,0x37800000-1,0x37800000,0x37800000+1,bits(.001),bits(1)):
  commands=[]
  for axis in range(3):
   end=[0,0,0];end[axis]=word
   for point in([bits(-1)]*3,[0]*3,[bits(1)]*3):commands.append([5]+point+[0]*3+end)
  programs.append(dict(label='finite-segment tiny edge, equality and signed-zero boundaries',world=worlds[0],commands=commands))
 # A no-edge successful submit retains the preceding pending batch verbatim.
 programs.append(dict(label='no selected edge preserves outstanding batch',world=worlds[0],commands=[submit(frame()),[3]+encode_world(worlds[9]),submit(frame()),consume(frame()),consume(frame())]))
 records=[];cases=[]
 for index,p in enumerate(programs):
  words=encode_world(p['world'])+[len(p['commands'])]+sum(p['commands'],[]);records.append(struct.pack('<'+'I'*len(words),*words));cases.append(dict(index=index,label=p['label'],commands=[c[0]for c in p['commands']]))
 return struct.pack('<I',len(records))+b''.join(records),cases
def aliases():
 v={f'atelier-host/src/offboard/{n}.rs':HOST+n+'.rs'for n in('ground_query','ground_sync')}
 v.update({f'atelier-host/src/offboard/ground_query/{n}.rs':HOST+'ground_query/'+n+'.rs'for n in('edges','lines','transform','world')});return v
def prepare(output):
 simulation=PLUGIN/'Source/AtelierSkate/Private/Simulation';snapshot=output/'simulation-source'
 if snapshot.exists():shutil.rmtree(snapshot)
 snapshot.mkdir()
 for p in simulation.glob('*.h'):shutil.copy2(p,snapshot/p.name)
 for unit in UNITS:shutil.copy2(simulation/f'{unit}.cpp',snapshot/f'{unit}.cpp')
 cpp_world=(PLUGIN/'Tests/Simulation/world_geometry_probe.cpp').read_text().split('int main()')[0];rust_world=(PLUGIN/'Tests/Reference/world_geometry_probe.rs').read_text().split('struct Query {')[0];state=source(HOST+'ground_geometry.rs')
 probe=snapshot/'offboard_ground_geometry_probe.cpp';probe.write_text((PLUGIN/'Tests/Simulation/offboard_ground_geometry_probe.cpp').read_text().replace('// WORLD_PROTOCOL',cpp_world));generated=output/'offboard-ground-geometry-reference.rs';generated.write_text((PLUGIN/'Tests/Reference/offboard_ground_geometry_probe.rs').read_text().replace('// WORLD_PROTOCOL',rust_world).replace('// ORIGINAL_STATE',state))
 report=dict(simulation_source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in snapshot.iterdir()},original_state_body_sha256=hashlib.sha256(state.encode()).hexdigest(),original_alias_sha256={d:hashlib.sha256(source(s).encode()).hexdigest()for d,s in aliases().items()})
 (output/'simulation-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return probe,snapshot,generated
def audit_input(raw,cases):
 r=Reader(raw);assert r.word()==len(cases)
 def world():r.skip(18*r.word());r.skip(1);r.skip(r.word());r.skip(36*r.word());r.skip(12*r.word());r.skip(1)
 def registry():
  bodies=r.word()
  for _ in range(bodies):r.skip(18);r.skip(12*r.word())
  for _ in range(2):
   for _ in range(r.word()):assert r.word()<bodies
  for _ in range(r.word()):
   r.skip(1)
   for _ in range(2):some=r.word();index=r.word();r.skip(1);assert not some or index<bodies
  for _ in range(r.word()):r.skip(2);assert r.word()<bodies
  r.skip(1)
 for c in cases:
  world();assert r.word()==len(c['commands'])
  for op in c['commands']:
   assert r.word()==op
   if op==0:r.skip(23)
   elif op==1:r.skip(20)
   elif op==3:world()
   elif op==4:r.skip(18);registry()
   elif op==5:r.skip(9)
   else:assert op==2
 assert r.at==len(r.words)
def variants(output,assets):
 data=json.loads((assets/'private/stock/skater-collections.json').read_text());fixtures=[]
 def fields(d):
  key='default'
  for _ in range(len(d['collections'])+1):
   record=next(r for r in d['collections']if converter.name_id(r['class'])==converter.name_id('physics_grinds')and converter.name_id(r['key'])==converter.name_id(key));name=next((n for n in record['fields']if converter.name_id(n)==converter.name_id('DeckCenterToTruck')),None)
   if name is not None:return record['fields'],name
   key=record['parent'];assert key
  raise AssertionError('Cycle')
 for label in('missing','type','width','nonfinite','negative-valid','missing-collection'):
  d=copy.deepcopy(data)
  if label=='missing-collection':d['collections']=[r for r in d['collections']if converter.name_id(r['class'])!=converter.name_id('physics_grinds')]
  elif label=='missing':
   for r in d['collections']:
    if converter.name_id(r['class'])==converter.name_id('physics_grinds'):
     for name in list(r['fields']):
      if converter.name_id(name)==converter.name_id('DeckCenterToTruck'):del r['fields'][name]
  else:
   f,n=fields(d)
   if label=='type':f[n]['type']='EA::Reflection::Bool'
   elif label=='width':f[n]['data']+='CAFEBABE'
   elif label=='nonfinite':f[n]['data']='7FC12345'
   else:f[n]['data']='BE4CCCCD'
  folder=output/'asset-fixtures'/label/'private/stock';folder.mkdir(parents=True,exist_ok=True);path=folder/'skater-collections.json';path.write_text(json.dumps(d));bank=folder.parents[1]/'settings.simulation';bank.write_bytes(converter.encode_settings(path));fixtures.append(dict(label=label,bank=bank,assets=folder.parents[1],success=label=='negative-valid'))
 return fixtures
def inspect(raw,cases):
 r=Reader(raw);operations=Counter();adjustments=Counter();pending=Counter();providers=Counter();errors=Counter()
 def status():okay=r.word();text=''.join(map(chr,r.take(r.word())));errors[text]+=not okay;return okay
 def packet():r.skip(60)
 def hits():
  for _ in range(7):
   if r.word():r.skip(8);providers['line-hits']+=1
 def owner():
  r.skip(1);has=r.word();pending[has]+=1
  if has:packet();hits()
 assert status();owner();assert r.word()==len(cases)
 for case in cases:
  assert r.word()==case['index'];end=r.word()+r.at;status();owner();assert r.word()==len(case['commands'])
  for op in case['commands']:
   assert r.word()==op;operations[op]+=1
   if op in(0,3):status()
   elif op==1:a=r.take(18);adjustments[a[:3]]+=1
   elif op==4:
    r.skip(21)
    if status():
     edges=r.word();assert edges<=40;providers['edges']+=edges;providers['cap40-observations']+=edges==40;r.skip(6*edges)
     if r.word():r.skip(9);providers['selected']+=1
     if r.word():packet();assert status();hits();providers['packets']+=1
   elif op==5:r.skip(3)
   owner()
  assert r.at==end,(case,r.at,end)
 assert r.at==len(r.words);assert all(operations[n]for n in range(6));assert pending[0]and pending[1]and providers['edges']and providers['line-hits'];assert len(adjustments)>=3
 return dict(operations=dict(operations),adjustments={str(k):v for k,v in adjustments.items()},pending_observations=dict(pending),provider_observations=dict(providers),errors=dict(errors))
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--target-dir',required=True,type=Path);p.add_argument('--preflight',action='store_true');a=p.parse_args();output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
 blob,cases=corpus();audit_input(blob,cases);(output/'input.bin').write_bytes(blob);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');probe,snapshot,generated=prepare(output);fixtures=variants(output,a.assets.resolve());bank=output/'settings.simulation';bank.write_bytes(converter.encode_settings(a.assets.resolve()/'private/stock/skater-collections.json'));summary=dict(histories=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(blob),input_sha256=hashlib.sha256(blob).hexdigest(),loader_fixture_count=len(fixtures),units=UNITS)
 if a.preflight:print(json.dumps(summary,indent=2));return
 simulation=output/'offboard-ground-geometry-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{u}.cpp')for u in UNITS],str(probe),'-o',str(simulation)],check=True);reference=build_probe(output,'offboard-ground-geometry-reference',generated,a.target_dir,extra_sources=aliases())
 expected=subprocess.check_output([str(reference),str(a.assets.resolve())],input=blob);actual=subprocess.check_output([str(simulation),str(bank)],input=blob);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
 if expected!=actual:
  first=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)))//4;divergence=dict(first_word=first,reference_bytes=len(expected),cpp_bytes=len(actual));(output/'first-divergence.json').write_text(json.dumps(divergence,indent=2)+'\n');raise AssertionError(divergence)
 coverage=inspect(expected,cases);reports=[]
 for fixture in fixtures:
  ref=subprocess.check_output([str(reference),str(fixture['assets']),'--load-only']);cpp=subprocess.check_output([str(simulation),str(fixture['bank']),'--load-only']);assert ref==cpp,fixture['label'];assert bool(struct.unpack_from('<I',ref)[0])==fixture['success'],fixture['label'];reports.append(dict(label=fixture['label'],success=fixture['success'],exact_words=len(ref)//4))
 result=dict(passed=True,**summary,exact_words=len(expected)//4+sum(r['exact_words']for r in reports),output_sha256=hashlib.sha256(expected).hexdigest(),coverage=coverage,loader_fixtures=reports,comparison='Complete original ground_geometry State and SceneService, real authored edge + seven-line query, consume/reset/retention, every provider traversal and helper boundary exactly.',limitations='Scene engine-edge records are explicit fixture inputs; this leaf does not establish Biped Ground/Air scheduling, grab, feet or world provider loading.')
 (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
