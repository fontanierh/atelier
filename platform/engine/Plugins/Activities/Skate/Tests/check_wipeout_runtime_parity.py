#!/usr/bin/env python3
"""Complete shared wipeout checks and original ordered settings read.

Only the root coordinator compiles/runs this proof. Completed observation frames
are this leaf's explicit input boundary. Actual frame production is covered by
a separate Air/KnownAir composition check; not established by this leaf.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import re
import shutil
import struct
import subprocess
import check_ground_board_parity as protocol
import check_skeleton_input_runtime_parity as dispatcher
from check_gesture_parity import PLUGIN,converter
from check_animation_playback_parity import Stream
from reference_build import build_probe
CORE='crates/skate-core/src/player/wipeout/'
HOST='crates/skate-host/src/physics/wipeout/'
UNITS=('NativeMath','NameId','Settings','StockSettingsReader','WipeoutRequests','WipeoutSettings','WipeoutObservations','WipeoutRuntime')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def schema():
 s=dispatcher.source(CORE+'data.rs');defs={}
 for name in ('Frame','Mode','GroundSettings','AirSettings','Settings'):
  body=re.search(r'pub struct '+name+r' \{(.*?)\n\}',s,re.S).group(1)
  defs['Wipeout'+name]=[(f,('Vector'if t=='V'else'Wipeout'+t if t in('GroundSettings','AirSettings')else re.sub(r'\s+','',t)))for f,t in re.findall(r'pub (\w+): ([^,\n]+),',body)]
 return defs
def helpers(defs):return protocol.protocol_helpers(defs)[:2]
def corpus(defs):
 rng=random.Random(0x82d90358);programs=[]
 def seed(n):
  return [5]+[int((n+k)%9==0)for k in range(34)]+[struct.unpack('<I',struct.pack('<f',k*.137))[0]for k in range(34)]+[(0,1,0xffffffff)[n%3],struct.unpack('<I',struct.pack('<f',(0,.02,.04,-.1)[n%4]))[0],(0,1,4,0xffffffff)[n%4],0,n%4]
 for mode in range(5):
  for n in range(64):
   commands=[seed(n)];frames=[]
   for k in range(32):
    f=protocol.default_value('WipeoutFrame',defs);f.update(flags_2468=(0,8,1<<5,1<<20)[k%4],flags_2472=(0,1<<15,1<<28,1<<6)[(n+k)%4],flags_2476=(0,8,1<<26,1<<30,1<<23)[(n+k)%5],flags_2480=0,flags_2484=(0,1<<21,1<<12)[k%3],category=(200,400,500)[k%3],timestep=(1/60,1/120,.033)[n%3],time_on_ground=(0,.05,.051,.5)[k%4],speed=(-10,0,1,10,100)[k%5],animation_up=[.6,(0,.5,.71,1)[k%4],.8,0],landing_angle=(-3,-.5,0,.5,3)[k%5],deck_velocity=[(-10,0,10)[k%3],(-100,-1,0,1,100)[k%5],.317,0],com_velocity=[0,(-100,0,100)[k%3],.731,0],jump_fix_frames=(0,5,20,100)[k%4],closing_velocity=[(-100,0,100)[k%3],(-100,0,100)[(k+1)%3],.137,0],board_material_flags=(0,1<<29,1<<30,1<<31)[k%4],board_contact=bool(k%3),wheel_contact=bool(k%4==0),board_contact_normal=[0,1,0,0],opposing_contact=(0,1,100000)[k%3],regions_force=[(0,1,20,100000)[(n+k+j)%4]for j in range(8)],maximum_skater_force=(0,100000)[k%2],vehicle_force=(0,100000)[(k//3)%2],group_8=bool(k%2),conflicting=bool(k%7==0),compliant=bool(k%3==0),highest_normal=[0,(.5,.71,1)[k%3],0,0],pose_error=[(0,.01,1,1000)[k%4],.0,0,0],maximum_pose_error=(0,.01,1,1000)[(k//4)%4],flip_active=bool(k%4==0),flip_requested_speed=(0,1)[k%2],system_up_y=(-1,0,1)[k%3],grind_selected=bool(k%3==1),grind_normal_valid=bool(k%2),grind_normal=[0,1,0,0])
    angle=(0,.4,1.5,3)[n%4];c,s=math.cos(angle),math.sin(angle);f['deck']=[[c,s,0,0],[-s,c,0,0],[0,0,1,0],[0,.137,0,1]];f['input_board']=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,.137,0,1]];f['world_to_animation']=[[c,s,0,0],[-s,c,0,0],[0,0,1,0],[0,0,0,0]]
    if n%8==0:f['regions_force']=[0]*8;f['maximum_pose_error']=0;f['pose_error']=[0]*4
    op=(n+k)%5;commands.append((op,f,(0,.5,1,2)[k%4]));frames.append(f)
    if k in(5,13,21):commands.append([6])
    if k==8:commands.append([8])
    if k==16:commands.extend([[9],[7]])
   programs.append(dict(mode=mode,label='persistent checks, cooldown, regional forces, landing and request priority',commands=commands))
 out=Stream();out.word(len(programs))
 for p in programs:
  out.word(p['mode']);out.word(len(p['commands']))
  for c in p['commands']:
   if isinstance(c,list):
    for w in c:out.word(w)
   else:out.word(c[0]);protocol.encode_value(out,'WipeoutFrame',c[1],defs);out.float(c[2])
 blob=bytes(out.data);words=struct.unpack('<'+'I'*(len(blob)//4),blob);at=1
 for p in programs:
  assert words[at:at+2]==(p['mode'],len(p['commands']));at+=2
  for c in p['commands']:
   op=c[0];assert words[at]==op;at+=1
   at+=protocol.word_count('WipeoutFrame',defs)+1 if op<=4 else 73 if op==5 else 0
 assert at==len(words),(at,len(words))
 return blob,programs
def prepare(out):
 defs=schema();cpp,rust=helpers(defs);native=PLUGIN/'Source/AtelierSkate/Private/Native';snapshot=out/'native-source'
 if snapshot.exists():shutil.rmtree(snapshot)
 snapshot.mkdir()
 for p in native.glob('*.h'):shutil.copy2(p,snapshot/p.name)
 for unit in UNITS:shutil.copy2(native/f'{unit}.cpp',snapshot/f'{unit}.cpp')
 probe=snapshot/'wipeout_runtime_probe.cpp';probe.write_text((PLUGIN/'Tests/Native/wipeout_runtime_probe.cpp').read_text().replace('// GENERATED_PROTOCOL',cpp))
 settings=dispatcher.source(HOST+'settings.rs');generated=out/'wipeout-runtime-reference.rs'
 source=(PLUGIN/'Tests/Reference/wipeout_runtime_probe.rs').read_text().replace('// GENERATED_PROTOCOL',rust).replace('// ORIGINAL_SETTINGS','mod original_settings{\n'+settings+'\n}')
 generated.write_text(source)
 provenance=dict(native_source_sha256={p.name:digest(p)for p in snapshot.iterdir()},original_settings_sha256=hashlib.sha256(settings.encode()).hexdigest(),original_core_sha256={n:hashlib.sha256(dispatcher.source(CORE+n+'.rs').encode()).hexdigest()for n in('data','common','ground','air','requests','mod')})
 (out/'native-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return probe,generated
def variants(out,assets):
 data=json.loads((assets/'private/stock/skater-collections.json').read_text());source=dispatcher.source(HOST+'settings.rs');ordered=[('physics_wipeout','default','Hash_4F08D9BAE6831524','graph')]
 for key in('easy','normal','hardcore','motorized','test'):
  ordered += [('physics_mode',key,'Hash_CC890A3BDCF6290A','boolean'),('physics_mode',key,'WipeoutCheckForBadLanding','boolean'),('physics_mode',key,'Wipeout_GroundXZAcceleration','scalar'),('physics_mode',key,'Hash_D978550D6DB4E6F7','scalar')]
 ordered += [('physics_wipeout','default',n,'scalar')for n in re.findall(r'f\("([^"]+)"\)',source)]
 ordered += [('physics_wipeout','default','FramesAtStartOfAirToIgnoreDangerZone','integer')];result=[]
 def resolve(d,category,key,name):
  for _ in range(len(d['collections'])+1):
   record=next(r for r in d['collections']if converter.name_id(r['class'])==converter.name_id(category)and converter.name_id(r['key'])==converter.name_id(key))
   actual=next((k for k in record['fields']if converter.name_id(k)==converter.name_id(name)),None)
   if actual is not None:return record['fields'],actual
   key=record['parent'];assert key,(category,name)
  raise AssertionError('cycle')
 for category,key,name,kind in ordered:
  failures=('missing','type','width','nan')if kind=='scalar'else('missing','type','width','invalid-byte','short','empty')if kind=='boolean'else('missing','type','width')if kind!='graph'else('missing','width','type','nonfinite')
  for failure in failures:
   d=copy.deepcopy(data);f,actual=resolve(d,category,key,name)
   if failure=='missing':
    for record in d['collections']:
     if converter.name_id(record['class'])==converter.name_id(category):
      for field in list(record['fields']):
       if converter.name_id(field)==converter.name_id(name):del record['fields'][field]
   elif failure=='type':f[actual]['type']='EA::Reflection::Bool'if kind!='boolean'else'EA::Reflection::Float'
   elif failure=='width':f[actual]['data']='DEADBEEF'if kind=='graph'else f[actual]['data']+'CAFEBABE'
   elif failure=='invalid-byte':f[actual]['data']='02'+f[actual]['data'][2:]
   elif failure=='short':f[actual]['data']=f[actual]['data'][:2]
   elif failure=='empty':f[actual]['data']=''
   elif failure=='nan':f[actual]['data']='7FC12345'
   elif failure=='nonfinite':f[actual]['data']=f[actual]['data'][:32]+'7FC12345'+f[actual]['data'][40:]
   label=f'{category}-{key}-{name}-{failure}';folder=out/'asset-fixtures'/label/'private/stock';folder.mkdir(parents=True,exist_ok=True);path=folder/'skater-collections.json';path.write_text(json.dumps(d));bank=folder.parents[1]/'settings.native';bank.write_bytes(converter.encode_settings(path));result.append(dict(label=label,bank=bank,assets=folder.parents[1],success=(kind=='graph'and failure in('type','nonfinite'))or(kind=='boolean'and failure in('width','short'))))
 # A compound error proves graph-before-modes and modes-before-scalar order.
 for first,second in((ordered[0],ordered[1]),(ordered[1],ordered[21])):
  d=copy.deepcopy(data)
  for category,key,name,kind in(first,second):f,actual=resolve(d,category,key,name);f[actual]['data']='DEADBEEFCAFEBABE'
  label='compound-'+first[2]+'-'+second[2];folder=out/'asset-fixtures'/label/'private/stock';folder.mkdir(parents=True,exist_ok=True);path=folder/'skater-collections.json';path.write_text(json.dumps(d));bank=folder.parents[1]/'settings.native';bank.write_bytes(converter.encode_settings(path));result.append(dict(label=label,bank=bank,assets=folder.parents[1],success=False))
 return result
def inspect(raw,programs,defs):
 words=struct.unpack('<'+'I'*(len(raw)//4),raw);at=0;assert words[at]==1;at+=1;at+=1+words[at]
 at+=protocol.word_count('WipeoutSettings',defs)+5*protocol.word_count('WipeoutMode',defs)+73
 assert words[at]==len(programs);at+=1;coverage=Counter();reason_counts=Counter();query_counts=Counter()
 for p in programs:
  assert words[at:at+2]==(p['mode'],len(p['commands']));at+=2
  for c in p['commands']:
   op=c[0];assert words[at]==op;at+=1;coverage[op]+=1
   if op<=4:query_counts[words[at:at+2]]+=1;at+=2
   current=words[at:at+73];at+=73
   for i,v in enumerate(current[:34]):reason_counts[i]+=bool(v)
 assert at==len(words);assert set(coverage)==set(range(10));assert any(reason_counts[n]for n in(0,1,2,3,5,6,7,11,16,18,19,20,21))
 return dict(operations=dict(coverage),retained_reason_observations=dict(reason_counts),request_queries={str(k):v for k,v in query_counts.items()})
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--target-dir',required=True,type=Path);p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);defs=schema();inputs,programs=corpus(defs);(out/'input.bin').write_bytes(inputs);probe,generated=prepare(out);fixtures=variants(out,a.assets.resolve());bank=out/'settings.native';bank.write_bytes(converter.encode_settings(a.assets.resolve()/'private/stock/skater-collections.json'))
 summary=dict(programs=len(programs),commands=sum(len(x['commands'])for x in programs),input_bytes=len(inputs),frame_words=protocol.word_count('WipeoutFrame',defs),loader_fixture_count=len(fixtures),units=UNITS,input_sha256=hashlib.sha256(inputs).hexdigest())
 if a.preflight:print(json.dumps(summary,indent=2));return
 native=out/'wipeout-runtime-cpp';snapshot=out/'native-source';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{u}.cpp')for u in UNITS],str(probe),'-o',str(native)],check=True)
 reference=build_probe(out,'wipeout-runtime-reference',generated,a.target_dir)
 expected=subprocess.check_output([str(reference),str(a.assets.resolve())],input=inputs);actual=subprocess.check_output([str(native),str(bank)],input=inputs);(out/'reference.bin').write_bytes(expected);(out/'cpp.bin').write_bytes(actual)
 if expected!=actual:
  first=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)))//4;raise AssertionError(dict(first_word=first,reference_bytes=len(expected),cpp_bytes=len(actual)))
 coverage=inspect(expected,programs,defs);reports=[]
 for fixture in fixtures:
  ref=subprocess.check_output([str(reference),str(fixture['assets']),'--load-only']);cpp=subprocess.check_output([str(native),str(fixture['bank']),'--load-only']);assert ref==cpp,fixture['label'];assert bool(struct.unpack_from('<I',ref)[0])==fixture['success'],fixture['label'];reports.append(dict(label=fixture['label'],success=fixture['success'],exact_words=len(ref)//4))
 result=dict(passed=True,**summary,exact_words=len(expected)//4+sum(r['exact_words']for r in reports),output_sha256=hashlib.sha256(expected).hexdigest(),coverage=coverage,loader_fixtures=reports,comparison='Complete original shared wipeout checks and retained request histories, every mode/setting, source exact loader errors and read order; no tolerance or numerical source edits.',limitations='Completed frame observations are explicit leaf inputs. Actual body/pose/collision observation production is covered by a separate Air/KnownAir composition check; not established by this leaf. Physical ragdoll wipeout states and global session coordinator are separate owners.');(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
