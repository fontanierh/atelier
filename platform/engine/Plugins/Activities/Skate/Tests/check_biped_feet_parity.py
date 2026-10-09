#!/usr/bin/env python3
"""Active recovered feet kernel and whole original Ground/Air host adapters.

This focused owner proof borrows canonical pose/root/processed contacts as
explicit upstream fixture inputs. Feet targets, retained State56 histories and
all FootIK mutations/publication are computed by unchanged original sources.
It does not establish the later connected offboard phase scheduling or queries.
Only the root coordinator compiles or executes; --preflight is source-only.
"""
import argparse
from collections import OrderedDict,Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
import player_input_protocol as wire
from check_animation_playback_parity import Stream
from check_skeleton_input_runtime_parity import source
from reference_build import build_probe
from session_parity import PLUGIN
CORE='crates/skate-core/src/'
HOST='crates/skate-host/src/physics/'
CODE=PLUGIN/'Source/AtelierSkate/Private/Simulation'
UNITS=('SimulationMath','RigidBody','SkeletonPoseFrames','SkeletonAnimationRecord','BoardPossessionManager','BipedFeet','BipedFeetGround','BipedFeetAir')
ALIAS={'BoardManagerHand':'manager::Hand','BoardPossessionManager':'manager::State','BipedFootLine':'feet::Line','BipedFeetInput':'feet::Input','BipedFootTarget':'feet::Target','BipedExternalTarget':'ExternalTarget','OffBoardOutputFields':'OffBoardOutputFields'}
def definitions():
 vector='[f32;4]';matrix='[[f32;4];4]';d=OrderedDict()
 d['BoardManagerHand']=[('vectors_0_to_64',f'[{vector};5]'),('word_80','u32'),('flag_84','bool'),('scalars_96_100','[f32;2]'),('flags_104_to_107','[bool;4]')]
 d['BoardPossessionManager']=[('hands','[BoardManagerHand;2]'),('vectors_224_to_272',f'[{vector};4]'),('scalars_288_to_296','[f32;3]'),('word_300','u32'),('flags_304_to_307','[bool;4]'),('words_308_to_316','[u32;3]')]
 d['BipedFootLine']=[('position',vector),('normal',vector),('surface','u32'),('valid','bool')]
 d['BipedFeetInput']=[('lines','[BipedFootLine;2]'),('local_foot_pairs',f'[[{vector};2];2]'),('world_foot_pairs',f'[[{vector};2];2]'),('root',matrix),('inverse_root',matrix),('effective_root',matrix),('position',vector),('velocity',vector),('flags_2476','u32'),('flags_2480','u32'),('flags_2484','u32'),('state','u32')]
 d['BipedFootTarget']=[('position',vector),('world','bool'),('blend','f32'),('normal',f'Option<{vector}>')]
 d['BipedExternalTarget']=[('world_position',vector),('animation_position',vector),('normal',vector),('normal_set','bool'),('normal_blend','f32')]
 d['OffBoardOutputFields']=wire.declarations()[0]['OffBoardOutputFields']
 return d

def generated(d):
 cpp=['using BipedExternalTarget=foot_ik::ExternalTarget;'];rust=[]
 for name in d:
  if name!='OffBoardOutputFields':rust.append(f'type {name}={ALIAS[name]};')
  cpp.append(f'void Observe(Output&,const {name}&);');rust.append('')
 for name,fields in d.items():
  cpp.append(f'void Observe(Output& o,const {name}& s){{'+''.join(wire.observe_expr(k,'s.'+f,'cpp')for f,k in fields)+'}')
  rust.append(f'fn observe_{name}(o:&mut Output,s:&{name}){{'+''.join(wire.observe_expr(k,'s.'+f,'rust')for f,k in fields)+'}')
  if name not in('BipedFootTarget','OffBoardOutputFields'):
   cpp.append(f'{name} Read{name}(Input& i){{{name} s;'+''.join('s.'+f+'='+wire.read_expr(k,'cpp')+';'for f,k in fields)+'return s;}')
   rust.append(f'fn read_{name}(i:&mut Input)->{name}{{{name}{{'+''.join(f+':'+wire.read_expr(k,'rust')+','for f,k in fields)+'}}')
 return '\n'.join(cpp),'\n'.join(rust)

def frame(angle=0,position=(0,0,0),w=0):
 c,s=math.cos(angle),math.sin(angle);return [[c,0,-s,0],[0,1,0,0],[s,0,c,0],list(position)+[w]]
def default(kind,d):
 a=wire.array(kind);o=wire.option(kind)
 if a:return [default(a[0],d)for _ in range(a[1])]
 if o:return None
 if kind in('f32','u32','bool'):return 0
 return {f:default(k,d)for f,k in d[kind]}
def input_packet(n,k,d,rng):
 value=default('BipedFeetInput',d);root=frame((n%9)*.071,(.137,1.1+k*.003,.317),(-0.0,.137)[n%2]);inverse=frame(-(n%9)*.071,(-.137,-1.1-k*.003,-.317),(-0.0,.317)[n%2]);effective=copy.deepcopy(root)
 if(n+k)%2:
  for axis in(0,2):effective[axis]=[-x for x in effective[axis]]
 value.update(root=root,inverse_root=inverse,effective_root=effective,position=[.137,(.3,.7,1.5,3)[k%4],.317,.517],velocity=[.137,(-8,-.3,0,3)[(n+k)%4],.731,-.517],flags_2476=4 if(n+k)%2 else 0,flags_2480=(0,1<<5,1<<6,(1<<5)|(1<<6))[k%4],flags_2484=(0,0x80000000,4,8,64,128,0xcc)[(n+k)%7],state=(500,501,502,503)[(n+k)%4])
 for f in range(2):
  h=(.01,.089,.09,.091,.2,.4)[(n+k+f)%6];wx=(.001,.08,.081,.3,1.2)[(n+k+f)%5];y=(0,.089,.09,.199,.2,.4,1.2)[(n+k+f)%7]
  value['local_foot_pairs'][f]=[[f*.13,h,.137,-.0],[f*.13,h+(0,.04)[k%2],.317,.137]]
  value['world_foot_pairs'][f]=[[wx,y,k*.037,-.0],[wx,y+(.001,.1)[k%2],k*.037+.2,.317]]
  normal=([0,1,0,0],[0,.9,.1,.137],[.137,.899,.517,.317],[1,0,0,.137],[0,0,0,0],[.317,.599,.517,-.731])[(n+k+f)%6]
  value['lines'][f]=dict(position=[wx,(-.4,0,.07,.317,.7)[(n+k+f)%5],k*.037,.137],normal=normal,surface=0x8a001234+n*37+f,valid=(n+k+f)%4!=0)
 if n%11==0:
  for pair in value['world_foot_pairs']:
   for p in pair:p[0]+=rng.uniform(-.3,.3);p[2]+=rng.uniform(-.3,.3)
 return value

def corpus(d):
 rng=random.Random(0x82d773f8);cases=[];programs=[]
 for n in range(144):
  commands=[]
  for k in range(100):
   if k in(0,36,79):commands.append((3,(0,1,500,501,502,503)[(n+k)%6],(500,501,502,503)[(n+k)%4]))
   value=input_packet(n,k,d,rng);op=(0,1,1,2)[(n+k)%4]
   if op==2:
    pose=[frame((part+n)*.017,(.137+part*.03,(.01,.09,.2)[part%3],k*.037+part*.01),(.0,.137,-.0)[part%3])for part in range(24)]
    commands.append((op,pose,value))
   else:commands.append((op,value))
   if k%7==0:commands.append((4,(n+k)%4,([0,1,0,.0],[.137,.731,.517,.317],[0,0,0,-.0],[0,-1,0,.137])[(n+k)%4]))
   if k in(18,61):
    manager=default('BoardPossessionManager',d);manager['word_300']=(0,1,2,3)[n%4];manager['flags_304_to_307']=[bool(n%2),True,True,False];manager['words_308_to_316']=[(0,1,0xffffffff)[n%3],(19,20,21,0xffffffff,0x7fffffff,0x80000000)[n%6],(39,40,41,0xffffffff)[n%4]];manager['scalars_288_to_296']=[.731,.317,.137];manager['vectors_224_to_272']=[[.137,.731,.317,-.0]for _ in range(4)]
    for f in range(2):
     h=manager['hands'][f];h.update(vectors_0_to_64=[[.137,.731,.317,-.0]for _ in range(5)],word_80=0x7a123456,flag_84=True,scalars_96_100=[(-.137,.317)[f],(.1,.3)[f]],flags_104_to_107=[True,True,False,True])
    limbs=[]
    for f in range(4):limbs += [f]+[(.137,.317,-.0)[(n+f)%3],.731,.517]+[1,0]+[.137,.317,.731,-.0]*2
    external=[dict(world_position=[.137,.731,.317,-.0],animation_position=[.137,.731,.317,.517],normal=[.137,.731,.517,.317],normal_set=bool(f%2),normal_blend=(-.2,0,.137,1)[f])for f in range(4)]
    commands.append((5,manager,[bool(n%2)]+limbs,external))
   if k in(28,72):commands += [(6,),(7,)]
  programs.append(('full retained support/height/normal/history and active Ground/Air adapters',commands))
 # Long invalid-contact runs, with valid seeds, exercise21/41-frame latches.
 for good in(False,True):
  commands=[(3,500,502)]
  for k in range(80):
   value=input_packet(2,k,d,rng);value['flags_2480']=0;value['flags_2484']=0;value['state']=500
   for f in range(2):value['lines'][f]['valid']=good;value['lines'][f]['position'][1]=-2;value['lines'][f]['normal']=[0,1,0,0]
   commands.append((1,value))
  programs.append(('bad contact21/41-frame retained latch and all-invalid316 retention',commands))
 stream=Stream();stream.word(len(programs))
 for index,(label,commands)in enumerate(programs):
  stream.word(len(commands))
  for c in commands:
   op=c[0];stream.word(op)
   if op in(0,1):wire.encode(stream,'BipedFeetInput',c[1],d)
   elif op==2:
    wire.encode(stream,'[[[f32;4];4];24]',c[1],d);v=c[2]
    for kind,val in(('[[f32;4];4]',v['root']),('[[f32;4];4]',v['inverse_root']),('[BipedFootLine;2]',v['lines']),('[f32;4]',v['position']),('[f32;4]',v['velocity'])):wire.encode(stream,kind,val,d)
    for name in('flags_2476','flags_2480','flags_2484','state'):stream.word(v[name])
   elif op==3:stream.word(c[1]);stream.word(c[2])
   elif op==4:stream.word(c[1]);wire.encode(stream,'[f32;4]',c[2],d)
   elif op==5:
    wire.encode(stream,'BoardPossessionManager',c[1],d);stream.word(c[2][0]);at=1
    for _ in range(4):
     stream.word(c[2][at]);at+=1
     for _ in range(3):stream.float(c[2][at]);at+=1
     for _ in range(2):stream.word(c[2][at]);at+=1
     for _ in range(8):stream.float(c[2][at]);at+=1
    wire.encode(stream,'[BipedExternalTarget;4]',c[3],d)
  cases.append(dict(index=index,label=label,commands=[c[0]for c in commands]))
 return bytes(stream.data),cases

def aliases():return {'atelier-host/src/ground_feet.rs':HOST+'biped_ground/feet.rs','atelier-host/src/air_feet.rs':HOST+'offboard/air_feet.rs'}
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def prepare(out,d):
 snapshot=out/'simulation-source'
 if snapshot.exists():shutil.rmtree(snapshot)
 snapshot.mkdir()
 for p in CODE.glob('*.h'):shutil.copy2(p,snapshot/p.name)
 for unit in UNITS:shutil.copy2(CODE/(unit+'.cpp'),snapshot/(unit+'.cpp'))
 cpp,rust=generated(d);simulation=snapshot/'biped_feet_probe.cpp';simulation.write_text((PLUGIN/'Tests/Simulation/biped_feet_probe.cpp').read_text().replace('// GENERATED_PROTOCOL',cpp));reference=out/'biped-feet-reference.rs';reference.write_text((PLUGIN/'Tests/Reference/biped_feet_probe.rs').read_text().replace('// GENERATED_PROTOCOL',rust))
 sources={CORE+'player/offboard/biped_air/feet.rs',CORE+'player/offboard/biped_air/recovered.rs',CORE+'player/offboard/board_possession/manager.rs',CORE+'player/offboard/air_launch/math.rs',CORE+'player/wipeout_state/math.rs',*aliases().values()}
 report=dict(simulation_source_sha256={p.name:digest(p)for p in snapshot.iterdir()},original_sources={p:hashlib.sha256(source(p).encode()).hexdigest()for p in sorted(sources)},protocol=d,boundary='Complete actual core feet and unchanged full host ground/air adapters; canonical incoming contacts, pose matrices and root frames are explicit borrowed upstream inputs. No query, body/drive or phase scheduling result is fabricated.')
 (out/'simulation-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return simulation,snapshot,reference

def audit(raw,cases,d):
 r=wire.Reader(raw);assert r.word()==len(cases)
 for case in cases:
  assert r.word()==len(case['commands'])
  for op in case['commands']:
   assert r.word()==op
   if op in(0,1):r.value('BipedFeetInput',d)
   elif op==2:
    for kind in('[[[f32;4];4];24]','[[f32;4];4]','[[f32;4];4]','[BipedFootLine;2]','[f32;4]','[f32;4]','u32','u32','u32','u32'):r.value(kind,d)
   elif op==3:r.word();r.word()
   elif op==4:assert r.word()<4;r.value('[f32;4]',d)
   elif op==5:r.value('BoardPossessionManager',d);r.value('[u32;57]',d);r.value('[BipedExternalTarget;4]',d)
   else:assert op in(6,7)
 assert r.at==len(raw),(r.at,len(raw))
def inspect(raw,cases,d):
 r=wire.Reader(raw);assert r.word()==len(cases);ops=Counter();support=Counter();latches=Counter();normals=Counter();targets=Counter();modes=Counter();publications=Counter();changed=0;previous=None
 def state():
  nonlocal changed,previous
  count=r.word();end=r.at+count*4;s=r.value('BoardPossessionManager',d);support[s['word_300']]+=1;latches[tuple(s['flags_304_to_307'])]+=1
  r.word()
  for _ in range(4):modes[r.word()]+=1;r.value('[u32;13]',d)
  r.value('[u32;452]',d)
  for _ in range(4):t=r.value('BipedExternalTarget',d);normals[(t['normal_set'],t['normal_blend'])]+=1
  r.value('[u32;16]',d);p=r.value('OffBoardOutputFields',d);publications[tuple(p['flags_306_307'])]+=1;assert p['flag_329']==171 and p['vector_160']==[1,2,3,4]
  assert r.at==end,(count,r.at,end);payload=raw[end-count*4:end];changed+=previous is not None and payload!=previous;previous=payload
 for c in cases:
  assert(r.word(),r.word())==(c['index'],len(c['commands']));state()
  for op in c['commands']:
   assert r.word()==op;ops[op]+=1
   if op==0:
    for _ in range(2):t=r.value('BipedFootTarget',d);targets[(t['world'],t['blend'],t['normal']is not None)]+=1
   state()
 assert r.at==len(raw);assert all(ops[n]for n in range(8));assert set(support)=={0,1,2,3};assert len(publications)>=3 and len(normals)>4 and changed>len(cases)
 return dict(operations=dict(ops),support_modes=dict(support),latches={str(k):v for k,v in latches.items()},normal_history_states=len(normals),target_types={str(k):v for k,v in targets.items()},ik_modes=dict(modes),publications={str(k):v for k,v in publications.items()},changed_states=changed)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--target-dir',required=True,type=Path);p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);d=definitions();blob,cases=corpus(d);audit(blob,cases,d);(out/'input.bin').write_bytes(blob);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');probe,snapshot,generated=prepare(out,d);summary=dict(histories=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(blob),input_sha256=hashlib.sha256(blob).hexdigest(),units=UNITS)
 if a.preflight:print(json.dumps(summary,indent=2));return
 simulation=out/'biped-feet-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(probe),'-o',str(simulation)],check=True);reference=build_probe(out,'biped-feet-reference',generated,a.target_dir,extra_sources=aliases())
 expected=subprocess.check_output([str(reference)],input=blob);actual=subprocess.check_output([str(simulation)],input=blob);(out/'reference.bin').write_bytes(expected);(out/'cpp.bin').write_bytes(actual)
 if expected!=actual:
  first=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)))//4;divergence=dict(first_word=first,reference_bytes=len(expected),cpp_bytes=len(actual));(out/'first-divergence.json').write_text(json.dumps(divergence,indent=2)+'\n');raise AssertionError(divergence)
 result=dict(passed=True,**summary,exact_words=len(expected)//4,output_sha256=hashlib.sha256(expected).hexdigest(),coverage=inspect(expected,cases,d),comparison='All source feet/State56 and all FootIK fields/publication exact; full original active Ground/Air wrappers unchanged.',limitations='Canonical processed contacts, actual incoming24 pose matrices and root frames are explicit upstream fixtures. This leaf does not establish complete Biped phase/controller/geometry/physical integration.')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
