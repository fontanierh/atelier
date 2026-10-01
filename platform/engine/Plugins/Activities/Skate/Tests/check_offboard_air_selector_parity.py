#!/usr/bin/env python3
"""Whole original offboard AirSelector and launch/candidate/sampling/ledge leaves.

Only the root coordinator builds/runs. World metadata and launch-controller
observations are explicit upstream inputs. Every trajectory/line/edge result is
produced by the actual original/native scene, never supplied as a completed hit.
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
import check_offboard_contact_parity as contact
import check_offboard_controller_parity as controller
import check_offboard_ground_geometry_parity as ground
PLUGIN=contact.PLUGIN
HOST='crates/skate-host/src/physics/offboard/'
FAMILY=('OffboardAirLaunch','OffboardAirLaunchJump','OffboardAirSelector','OffboardAirSelectorCore','OffboardAirSelectorCandidates','OffboardAirSelectorCompletion','OffboardAirSelectorSampling','OffboardAirSelectorLedge','OffboardAirSelectorAdjustment','OffboardAirSelectorSettings')
UNITS=tuple(dict.fromkeys(controller.UNITS+contact.UNITS+ground.UNITS+FAMILY))
bits,fs,Reader=contact.bits,contact.fs,contact.Reader
IDENTITY4=[1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,0.]
def context(group=-1,flags=0,forward=(0,0,1,0),up=(0,1,0,0)):
 return [flags,group&0xffffffff]+fs(list(up)+list(forward))
def packet(position=(0,1,0,0),velocity=(0,4,3,0),primary=6,secondary=3,has_board=False):
 return fs(list(velocity)+[0,0,3,0]+list(position)+[0,1,0,0]+[0,0,1,0]+[0,.1,0,0]+[.087,.87,.698])+[primary,secondary,int(has_board),1]
def launch(p=None,ctx=None,gravity=-9.81):return [0]+(p or packet())+fs([0,gravity,0,0])+(ctx or context())
def consume(ctx=None,half=.3,op=1):return [op]+(ctx or context())+fs([half])
def requery(ctx=None,a=0,b=0):return [4]+(ctx or context())+[a,b]
def sample(frame=1,dt=1/60):return [3,frame&0xffffffff,bits(dt)]
def adjust(frame=0,end=(0,.3,.4,0),axes=IDENTITY4):return [2,frame&0xffffffff]+fs(list(end)+axes)
def inspect_ledge(ctx=None,half=.3,hits=6):return [11]+(ctx or context())+fs([half])+[hits]
def launch_mode(mode,current,k):
 # Every consumed controller field is an explicit snapshot from that owner.
 # The whole Biped proof later produces these via the real walking schedule.
 categories=(100,400,200,500,500,500,900);category=categories[mode];state=(503 if mode==3 else 500)
 f2476=(0x80000 if mode==4 else 0)|(4 if k%2 else 0);f2480=0x80 if mode==3 and k%2 else 0;f2472=0x10000000 if k%5==0 else 0
 velocity=(0,-3,0,0)if k%4==0 else(.15,2,2.5+k*.1,0);slow=(.01,0,.02,0)if k%3==0 else(1,0,2,0)
 words=fs([0,.05,0,.13]+[0,0,1,.19]+[0,1,0,.29]+[0,1,0,.31]+list(velocity)+list(slow))
 geometry=mode==1 and k%3!=0;words+=[int(geometry)]
 if geometry:words+=fs([0,0,0,.23,1,0,0,.17])
 words += [f2472,f2476,f2480,state if not current else 900,state if current else 900,category if current else 900,category if not current else 900]+fs([(.9,-.9,0)[k%3],(.2,-.9,0)[k%3]])
 state_view=fs([0,1,0,.11]+[0,1,0,.17]+[1+k*.25,(-1,0,1)[k%3],(.2,-.2,0)[k%3]])+[k%2]
 curve=fs([i*2 for i in range(8)]+[10-i for i in range(8)])
 retained=packet(velocity=velocity,primary=2,secondary=1,has_board=k%2);retained[24:27]=fs([.12,.29,.7])
 return [12]+retained+words+state_view+curve+fs([1.1,.7])+[int(current)]
def corpus():
 rng=random.Random(0x82d6b870);floor=contact.quad(-8,8,-8,8,0,0);ramp=contact.quad(-8,8,-8,8,-.5,1);step=contact.quad(-8,8,-8,2,0,0)+contact.quad(-8,8,2,8,.4,.4)
 edges=[([-2,.2,2],[2,.2,2]),([-2,.22,2],[2,.22,2]),([-2,.19,2],[2,.19,2]),([0,.2,1],[0,.2,6])]
 worlds=[contact.make_world([(faces,0,-1,0)],edges)for faces in(floor,ramp,step)]
 worlds += [contact.make_world([(floor,2,-1,0)],edges,island=n)for n in(0,1,3)]
 worlds += [contact.make_world([(floor,0,1,0),(ramp,1,2,0)],edges),contact.make_world([(floor,0,-1,0x6000),(ramp,1,-1,0)],edges),contact.make_world([]),contact.make_world([(floor,0,-1,0)],enabled=False)]
 many=contact.make_world([(floor,0,-1,0)],[(a,b)for a,b in edges]*16);worlds.append(many)
 material=contact.make_world([(floor,0,-1,0)],edges);material['surfaces']=[0x300]*len(material['surfaces']);worlds.append(material)
 programs=[]
 for n in range(64):
  cmds=[];world=copy.deepcopy(worlds[n%len(worlds)])
  for k in range(4):
   primary,secondary=((1,0),(6,3),(9,7),(6,0))[(n+k)%4];velocity=(rng.uniform(-.15,.15),(2,4,5.8)[k%3],(2,3,5)[n%3],(.0,.19)[n%2]);pos=(rng.uniform(-.2,.2),(1,1.4,2)[n%3],rng.uniform(-.15,.15),.17)
   ctx=context(group=(-1,1,2)[(n+k)%3],flags=n%4);p=packet(pos,velocity,primary,secondary,k%2==1)
   cmds += [launch(p,ctx),sample(k+1),inspect_ledge(ctx,hits=(5,6,7)[k%3]),[16,1],requery(ctx,0x10000000),consume(ctx,op=9 if k%2 else 1),sample(10+k),adjust(k,axes=IDENTITY4),sample(16+k),requery(ctx),[5],consume(ctx),[8]+contact.encode_world(worlds[(n+1+k)%len(worlds)]),requery(ctx),consume(ctx),sample(25+k)]
  cmds += [[7],sample(40),[14],sample(2),[15],[6],sample(0)];programs.append(dict(label='actual launch/candidate/ledge/commit/sample/requery replacement histories',world=world,commands=cmds))
 for mode in range(7):
  for current in (False,True):
   for k in range(6):
    ctx=context();cmds=[launch_mode(mode,current,k),[13]+fs([0,-9.81,0,0])+ctx,sample(1),inspect_ledge(ctx),consume(ctx),sample(16),requery(ctx),consume(ctx),[7],[15]]
    programs.append(dict(label=f'complete retained launch mode{mode}/current{current}/case{k}',world=worlds[0],commands=cmds))
 for label in('zero-count','count-cap','overflow','packet-nan','gravity-nan','gravity-W-nan','cone-nan'):
  p=packet();g=fs([0,-9.81,0,0])
  if label=='zero-count':p[27]=0
  elif label=='count-cap':p[27]=17
  elif label=='overflow':p[27]=0xffffffff;p[28]=3
  elif label=='packet-nan':p[3]=0x7fc12345
  elif label=='gravity-nan':g[1]=0x7fc12345
  elif label=='gravity-W-nan':g[3]=0x7f800000
  else:p[24]=0x7fc12345
  cmds=[launch(),[0]+p+g+context(),sample(2),consume(),[16,0],[7],[5]];programs.append(dict(label='source failure with retained outstanding batch/'+label,world=worlds[0],commands=cmds))
 for half in (0,-.1,float('nan'),.3):
  cmds=[launch(packet(velocity=(0,4,3,0),primary=1,secondary=0)),inspect_ledge(),consume(half=half),consume(),requery(),consume(),sample(30)]
  programs.append(dict(label='actual admitted ledge clearance/half-wheelbase failure prefix',world=worlds[0],commands=cmds))
 for a in (-9.81,-1,0,1):
  cmds=[]
  for normal in ((0,1,0,0),(1,0,0,0),(0,0,1,0)):
   for v in (-4,0,4):
    for y in(-1,0,1):cmds.append([10]+fs([0,y,0,.19,0,v,3,.17,0,a,0,.23,2,0,0,0,.31]+list(normal)))
  programs.append(dict(label='plane discriminant/two-root/zero-gravity boundaries',world=worlds[0],commands=cmds))
 for height,radius,start in ((.9,.1,-2),(.9,.1,0),(.9,.1,2),(.9,.1,0x7fffffff),(.9,0,2),(.9,-.1,2),(float('nan'),.1,2),(.9,float('inf'),2)):
  cmds=[launch(),[18]+fs([height,radius])+[start&0xffffffff]+packet()+fs([0,-9.81,0,0]),sample(2),[14],[7]]
  programs.append(dict(label='complete core candidate request/authored setting domain and retained reset',world=worlds[0],commands=cmds))
 records=[];cases=[]
 for n,p in enumerate(programs):
  words=contact.encode_world(p['world'])+[len(p['commands'])]+sum(p['commands'],[]);records.append(struct.pack('<'+'I'*len(words),*words));cases.append(dict(index=n,label=p['label'],commands=[c[0]for c in p['commands']]))
 return struct.pack('<I',len(records))+b''.join(records),cases

def aliases():
 result={'atelier-host/src/offboard/contact_toolkit.rs':HOST+'contact_toolkit.rs','atelier-host/src/offboard/contact_toolkit/world.rs':HOST+'contact_toolkit/world.rs','atelier-host/src/offboard/air_selector/settings.rs':HOST+'air_selector/settings.rs','atelier-host/src/offboard/settings/curves.rs':HOST+'settings/curves.rs'}
 result.update({d:s for d,s in ground.aliases().items()if 'ground_sync'not in d});return result

def prepare(output):
 native=PLUGIN/'Source/AtelierSkate/Private/Native';snapshot=output/'native-source'
 if snapshot.exists():shutil.rmtree(snapshot)
 snapshot.mkdir()
 for p in native.glob('*.h'):shutil.copy2(p,snapshot/p.name)
 for unit in UNITS:shutil.copy2(native/f'{unit}.cpp',snapshot/f'{unit}.cpp')
 cpp_world=(PLUGIN/'Tests/Native/world_geometry_probe.cpp').read_text().split('int main()')[0];rust_world=(PLUGIN/'Tests/Reference/world_geometry_probe.rs').read_text().split('struct Query {')[0];host=source(HOST+'air_selector.rs')
 probe=snapshot/'offboard_air_selector_probe.cpp';probe.write_text((PLUGIN/'Tests/Native/offboard_air_selector_probe.cpp').read_text().replace('// WORLD_PROTOCOL',cpp_world));generated=output/'offboard-air-selector-reference.rs';generated.write_text((PLUGIN/'Tests/Reference/offboard_air_selector_probe.rs').read_text().replace('// WORLD_PROTOCOL',rust_world).replace('// ORIGINAL_HOST',host))
 report=dict(native_source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in snapshot.iterdir()},original_host_body_sha256=hashlib.sha256(host.encode()).hexdigest(),original_alias_sha256={d:hashlib.sha256(source(s).encode()).hexdigest()for d,s in aliases().items()},boundary='Complete original host AirSelector and original public core launch/candidate/sampling/ledge functions. Actual unchanged StaticScene + GroundQueryScene compute every result; launch controller observations are explicit upstream producer inputs.')
 (output/'native-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return probe,snapshot,generated

def audit_input(raw,cases):
 r=Reader(raw);assert r.word()==len(cases)
 def world():r.skip(18*r.word());r.skip(1);r.skip(r.word());r.skip(36*r.word());r.skip(12*r.word());r.skip(1)
 for c in cases:
  world();assert r.word()==len(c['commands'])
  for op in c['commands']:
   assert r.word()==op
   if op==0:r.skip(45)
   elif op in(1,9):r.skip(11)
   elif op==2:r.skip(21)
   elif op==3:r.skip(2)
   elif op==4:r.skip(12)
   elif op==8:world()
   elif op==10:r.skip(21)
   elif op==11:r.skip(12)
   elif op==12:r.skip(31+24);present=r.word();r.skip(8*present+7+2+12+16+2+1)
   elif op==13:r.skip(14)
   elif op==16:r.skip(1)
   elif op==18:r.skip(38)
   else:assert op in(5,6,7,14,15)
 assert r.at==len(r.words),(r.at,len(r.words))

def loader_fixtures(assets):
 data=json.loads((assets/'private/stock/skater-collections.json').read_text());fixtures=[]
 fields=[('physics_state_offboard_air','Hash_AB0D9EAEBFC584E9','float'),('physics_state_offboard_air','TrajectorySphereRadius','float'),('physics_state_offboard_air','TrajectoryStartIndex','integer'),('physics_state_offboard_air','TrajBlendAmountVsTime','graph'),('physics_grinds','DeckCenterToTruck','float')]
 def edit(d,c,n):
  key='default'
  for _ in range(len(d['collections'])+1):
   record=next(r for r in d['collections']if converter.name_id(r['class'])==converter.name_id(c)and converter.name_id(r['key'])==converter.name_id(key));name=next((k for k in record['fields']if converter.name_id(k)==converter.name_id(n)),None)
   if name is not None:return record['fields'][name]
   key=record['parent'];assert key
  raise AssertionError('cycle')
 def missing(d,c,n):
  for r in d['collections']:
   if converter.name_id(r['class'])==converter.name_id(c):
    for name in list(r['fields']):
     if converter.name_id(name)==converter.name_id(n):del r['fields'][name]
 for c,n,kind in fields:
  edits=['missing','type','width','short','invalid-hex','unicode-space']+(['nonfinite']if kind!='integer'else['signed-type-valid','arbitrary-word-valid'])
  if kind=='graph':edits+=['duplicate-x-valid','unordered-x']
  if kind=='float':edits+=['zero','negative']
  for label in edits:
   d=copy.deepcopy(data);success=label in('unicode-space','signed-type-valid','arbitrary-word-valid','duplicate-x-valid')or(label in('zero','negative')and n=='Hash_AB0D9EAEBFC584E9')
   if label=='missing':missing(d,c,n)
   else:
    f=edit(d,c,n)
    if label=='type':f['type']='EA::Reflection::Bool'
    elif label=='width':f['data']+='CAFEBABE'
    elif label=='short':f['data']=f['data'][:-1]
    elif label=='invalid-hex':f['data']='Z'+f['data'][1:]
    elif label=='unicode-space':f['data']='\u2003'.join(f['data'][i:i+8]for i in range(0,len(f['data']),8))
    elif label=='nonfinite':f['data']='7FC12345'+f['data'][8:]
    elif label=='signed-type-valid':f['type']='EA::Reflection::Int32';f['data']='FFFFFFFE'
    elif label=='arbitrary-word-valid':f['data']='DEADBEEF'
    elif label=='duplicate-x-valid':f['data']=f['data'][:40]+f['data'][32:40]+f['data'][48:]
    elif label=='unordered-x':f['data']=f['data'][:32]+'7F000000'+f['data'][40:]
    elif label=='zero':f['data']='00000000'
    else:f['data']='BE4CCCCD'
   fixtures.append((c+'/'+n+'/'+label,d,success))
 for c in ('physics_state_offboard_air','physics_grinds'):
  d=copy.deepcopy(data);d['collections']=[r for r in d['collections']if converter.name_id(r['class'])!=converter.name_id(c)];fixtures.append((c+'/missing-collection',d,False))
 for first in range(len(fields)):
  for second in range(first+1,len(fields)):
   d=copy.deepcopy(data);c,n,_=fields[first];edit(d,c,n)['type']='EA::Reflection::Bool';c,n,_=fields[second];missing(d,c,n);fixtures.append((f'ordered compound failure {first} before{second}',d,False))
 return fixtures

def fixture_bank(data):
 # The production converter intentionally rejects malformed typed hexadecimal
 # before loading. Preserve those literal source strings in ATATTR01's existing
 # text storage, retaining reflection types so the actual readers diagnose them.
 # For ordinary typed payloads this is byte-identical to encode_settings.
 records=data['collections'];strings=set()
 for record in records:
  strings.update((record['class'],record['key'],record['parent']));strings.update(record['fields']);strings.update(f['type']for f in record['fields'].values())
 strings=sorted(strings);ids={v:n for n,v in enumerate(strings)};raw=bytearray(b'ATATTR01')
 def word(n):raw.extend(struct.pack('<I',n))
 word(len(strings));word(len(records))
 for s in strings:b=s.encode();word(len(b));raw.extend(b)
 for record in records:
  for key in ('class','key','parent'):word(ids[record[key]])
  word(len(record['fields']))
  for name,f in sorted(record['fields'].items()):
   word(ids[name]);word(ids[f['type']]);literal=f['type']=='EA::Reflection::Text'
   if not literal:
    try:payload=bytes.fromhex(f['data'])
    except ValueError:literal=True
   if literal:payload=f['data'].encode()
   word(int(literal));word(len(payload))
   if literal:raw.extend(payload)
   else:
    for at in range(0,len(payload),4):word(int.from_bytes(payload[at:at+4],'big'))
 return bytes(raw)

def inspect(raw,cases):
 r=Reader(raw);ops=Counter();errors=Counter();flags=Counter();queries=Counter();modes=Counter();samples=Counter();ledges=Counter()
 def status():okay=r.word();message=''.join(map(chr,r.take(r.word())));errors[message]+=not okay;return okay
 def owner():
  end=r.word()+r.at;s=r.take(54);flags[tuple(s[:3])]+=1;r.skip(31);nc=r.word();assert nc<=16;candidates=[r.take(29)for _ in range(nc)];queries['valid-candidate-observations']+=sum(c[-2]for c in candidates);np=r.word();r.skip(48*np);ns=r.word();r.skip(ns);has=r.word();
  if has:queries['selected-observations']+=1;r.skip(1)
  r.skip(29);tail=r.take(24);ledges['selected-observations']+=tail[12];queries['requery-pending-observations']+=tail[14];queries['retained-requery-hit-observations']+=tail[15]>0
  if r.word():n=r.word();results=[r.take(32)for _ in range(n)];queries['completed-hit-observations']+=sum(struct.unpack('<f',struct.pack('<I',q[12]))[0]>=0 for q in results);queries['completed-miss-observations']+=sum(struct.unpack('<f',struct.pack('<I',q[12]))[0]<0 for q in results)
  if r.word():r.skip(48)
  r.skip(31);sample=r.take(35);samples[sample[-2]]+=1;assert r.at==end,(r.at,end)
 def edges():n=r.word();r.skip(n*6);return n
 assert status();r.skip(20);assert r.word()==len(cases)
 for case in cases:
  assert r.word()==case['index'];end=r.word()+r.at;status();owner();assert r.word()==len(case['commands'])
  for op in case['commands']:
   assert r.word()==op;ops[op]+=1
   if op in(0,8,13,16):status()
   elif op in(1,9):
    if status():
     if r.word():r.skip(1)
   elif op==3:r.skip(35)
   elif op in(4,5):
    if status():queries['operation-'+str(op)+'-true']+=r.word()
   elif op==10:
    if r.word():r.skip(1);ledges['plane-roots']+=1
   elif op==11:
    if status()and r.word():
     r.skip(21)
     if status():
      ledges['authored-edges']+=edges();ledges['filtered-edges']+=edges()
      if r.word():
       ledges['chosen']+=1;r.skip(25+29)
       if r.word():r.skip(42);ledges['six-line-batches']+=1
       status()
   elif op==12:modes[r.word()]+=1;status();r.skip(31)
   elif op==18:
    if status():r.skip(16*r.word())
   else:assert op in(2,6,7,14,15)
   owner()
  assert r.at==end,(case['index'],r.at,end)
 assert r.at==len(r.words);assert all(ops[n]for n in list(range(17))+[18]);assert all(modes[n]for n in range(7));assert samples[0]and samples[1];assert queries['completed-hit-observations']and queries['completed-miss-observations']and queries['operation-4-true']and queries['operation-5-true'];assert len([x for x,n in errors.items()if x and n])>=5
 # The source deliberately consumes six real line misses as a completed batch.
 assert ledges['chosen']and ledges['six-line-batches']and ledges['selected-observations']
 return dict(operations=dict(ops),errors=dict(errors),sampling_flags={str(k):v for k,v in flags.items()},queries=dict(queries),modes=dict(modes),sample_validity=dict(samples),ledges=dict(ledges))

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--target-dir',required=True,type=Path);p.add_argument('--preflight',action='store_true');a=p.parse_args();output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
 blob,cases=corpus();audit_input(blob,cases);(output/'input.bin').write_bytes(blob);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');probe,snapshot,generated=prepare(output);fixtures=loader_fixtures(a.assets.resolve());bank=output/'settings.native';bank.write_bytes(converter.encode_settings(a.assets.resolve()/'private/stock/skater-collections.json'));summary=dict(histories=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(blob),input_sha256=hashlib.sha256(blob).hexdigest(),loader_fixture_count=len(fixtures),units=UNITS)
 if a.preflight:print(json.dumps(summary,indent=2));return
 native=output/'offboard-air-selector-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{u}.cpp')for u in UNITS],str(probe),'-o',str(native)],check=True);reference=build_probe(output,'offboard-air-selector-reference',generated,a.target_dir,extra_sources=aliases(),bevy=True)
 expected=subprocess.check_output([str(reference),str(a.assets.resolve())],input=blob);actual=subprocess.check_output([str(native),str(bank)],input=blob);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
 if expected!=actual:
  first=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)))//4;divergence=dict(first_word=first,reference_bytes=len(expected),cpp_bytes=len(actual));(output/'first-divergence.json').write_text(json.dumps(divergence,indent=2)+'\n');raise AssertionError(divergence)
 coverage=inspect(expected,cases);reports=[]
 for k,(label,data,success)in enumerate(fixtures):
  folder=output/'loader-fixtures'/str(k);path=folder/'private/stock/skater-collections.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data));invalid=folder/'settings.native';invalid.write_bytes(fixture_bank(data));ref=subprocess.check_output([str(reference),str(a.assets.resolve()),str(folder)]);cpp=subprocess.check_output([str(native),str(bank),str(invalid)]);(folder/'reference.bin').write_bytes(ref);(folder/'cpp.bin').write_bytes(cpp);assert ref==cpp,dict(label=label,reference_bytes=len(ref),native_bytes=len(cpp));r=Reader(ref);assert r.word();r.skip(r.word()+20);assert bool(r.word())==success,label;reports.append(dict(label=label,success=success,exact_words=len(ref)//4))
 result=dict(passed=True,**summary,exact_words=len(expected)//4+sum(r['exact_words']for r in reports),output_sha256=hashlib.sha256(expected).hexdigest(),coverage=coverage,loader_fixtures=reports,comparison='Complete unchanged original AirSelector host, launch producer, candidate/commit/ledge/sampling helpers and actual StaticScene/GroundQueryScene world work exactly.',limitations='This leaf receives launch/controller packet inputs and authored world metadata; complete Biped Ground/Air physical, feet, grab, landing and global phase scheduling remain separate owner proofs.')
 (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
