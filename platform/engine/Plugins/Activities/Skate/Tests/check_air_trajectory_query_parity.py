#!/usr/bin/env python3
"""Full original trajectory walk, contact time, normal average and real world leaves.

Compile and execute through the shared render lock and memory guard. Whole core
source and the complete host world adapter are copied unchanged from the pinned
reference. Explicit callback failures separately observe propagation order.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tarfile
from session_parity import PLUGIN, REFERENCE_REVISION

UNITS=('NativeMath','Geometry','GeometrySweep','WorldGeometry','AirTrajectoryQuery','AirTrajectoryRuntime')
WORLD='crates/skate-host/src/physics/air_trajectory/world.rs'
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def fs(v):return list(map(bits,v))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def corpus():
 rng=random.Random(0x82770910);records=[];cases=[]
 def triangle(v,tag=1,fat=0,flags=0x10):return fs([x for p in v for x in p]+[fat])+[flags,tag]
 floor=[triangle([(-12,0,-12),(12,0,12),(12,0,-12)],11),triangle([(-12,0,-12),(-12,0,12),(12,0,12)],12)]
 wall=[triangle([(-4,0,1),(4,4,1),(4,0,1)],21),triangle([(-4,0,1),(-4,4,1),(4,4,1)],22)]
 ramp=[triangle([(-12,-2,-12),(12,2,12),(12,2,-12)],31),triangle([(-12,-2,-12),(-12,2,12),(12,2,12)],32)]
 def world(triangles):return [len(triangles)]+sum(triangles,[])
 def add(label,op,args,triangles=floor):
  raw=world(triangles)+[op]+args;cases.append(dict(index=len(cases),label=label,operation=op));records.append(struct.pack('<'+'I'*len(raw),*raw))
 def request(seed,gravity=-9.81):
  return fs([.017*(seed%7),.5+.1*(seed%5),-.03*(seed%3),.517,
             .1*(seed%4),(-2.,0.,3.,7.)[seed%4],.05*(seed%3),.137,
             .013*(seed%2),gravity,.017*(seed%3),.071,
             (.25,.75,1.5,3.)[seed%4],(.025,.1,.25,.75)[seed%4],
             (.05,.125,.5,1.)[seed%4],(.125,.25,1.,2.)[seed%4]])
 for seed in range(144):
  triangles=(floor,ramp,floor+wall,wall,[])[seed%5]
  add('full authored collision walk and normal averaging',0,request(seed,(-9.81,-1.,0.,2.)[seed%4])+[0],triangles)
  add('actual world and plant caller composition',5,request(seed),triangles)
 for seed in range(192):
  start=[rng.uniform(-3,3),rng.uniform(-2,3),rng.uniform(-3,3),(0.,-.0,.137)[seed%3]]
  end=[rng.uniform(-3,3),rng.uniform(-2,3),rng.uniform(-3,3),(0.,-.0,.517)[seed%3]]
  add('thin/rounded world query and authored equal-distance order',1,fs(start+end+[(0.,.025,.1,.75,2.)[seed%5]]),(floor,ramp,floor+wall)[seed%3])
 for seed in range(160):
  add('actual SAT triangle collector',2,fs([rng.uniform(-4,4),rng.uniform(-2,2),rng.uniform(-4,4),.137,(0.,.01,.5,1.,3.)[seed%5]]),(floor,ramp,floor+wall)[seed%3])
 add('SAT rejects broadphase-only overlap',2,fs([0,0,0,0,1.5]),[triangle([(1,4,0),(4,1,0),(4,4,0)])])
 add('nearby collector retains first64 authored triangles',2,fs([0,0,0,0,1]),floor*48)
 add('duplicate nearest triangle retains first geometry and surface',1,fs([0,2,0,0,0,-2,0,0,.1]),[floor[0],triangle([(-12,0,-12),(12,0,12),(12,0,-12)],99)])
 for seed in range(128):
  t=request(seed,(-9.81,-.00001,0.,2.)[seed%4])[:13]
  add('complete prediction position velocity and apex four lanes',3,t+fs([(-1.,-.0,0.,.017,3.)[seed%5]]),[])
 for lane in range(4):
  for invalid in (0x7fc12345,0x7f800000,0xff800000):
   args=fs([0,2,0,0,0,-2,0,0,.1]);args[lane]=invalid
   add('line rejects every nonfinite carried lane',1,args)
 for radius in (-1.,float('nan'),float('inf')):
  add('world radius failure retains absent result',1,fs([0,2,0,0,0,-2,0,0,radius]))
  add('nearby radius failure retains empty result',2,fs([0,0,0,0,radius]))
 for duration in (-1.,-.0,0.,float('nan')):
  args=request(1);args[12]=bits(duration);add('nonpositive or unordered horizon returns original miss',0,args+[0])
 for gravity in (-9.81,0.):
  args=fs([0,.5,0,0,0,-3,0,0,0,gravity,0,0,1,.1,.25,.25])
  for failure in (1,2):add('explicit producer failure and retained caller output',4,args+[failure])
 return struct.pack('<I',len(records))+b''.join(records),cases
def build(out):
 root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip())
 relative=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-core/src').relative_to(root).as_posix()
 archive=subprocess.check_output(['git','archive',f'{REFERENCE_REVISION}:{relative}'],cwd=root)
 source=out/'reference-source'
 if source.exists():shutil.rmtree(source)
 source.mkdir()
 with tarfile.open(fileobj=io.BytesIO(archive))as stream:stream.extractall(source,filter='data')
 original={p.relative_to(source).as_posix():digest(p)for p in source.rglob('*.rs')}
 world_path=(PLUGIN/'ThirdParty/skate-runtime'/WORLD).relative_to(root).as_posix()
 world=subprocess.check_output(['git','show',f'{REFERENCE_REVISION}:{world_path}'],cwd=root)
 assert world==(PLUGIN/'ThirdParty/skate-runtime'/WORLD).read_bytes()
 (source/'air-host-world.rs').write_bytes(world)
 rust=PLUGIN/'Tests/Reference/air_trajectory_query_probe.rs';main=source/'air-trajectory-query-oracle.rs'
 main.write_text((source/'lib.rs').read_text()+rust.read_text());reference=out/'air-trajectory-query-reference'
 subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
 assert all(digest(source/p)==sha for p,sha in original.items())
 assert (source/'air-host-world.rs').read_bytes()==world
 live=PLUGIN/'Source/AtelierSkate/Private/Native';snapshot=out/'native-source'
 if snapshot.exists():shutil.rmtree(snapshot)
 snapshot.mkdir()
 for p in list(live.glob('*.h'))+[live/(u+'.cpp')for u in UNITS]:shutil.copy2(p,snapshot/p.name)
 cpp=PLUGIN/'Tests/Native/air_trajectory_query_probe.cpp';shutil.copy2(cpp,snapshot/cpp.name);native=out/'air-trajectory-query-native'
 subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/cpp.name),'-o',str(native)],check=True)
 (out/'provenance.json').write_text(json.dumps(dict(reference_revision=REFERENCE_REVISION,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=original,host_world_sha256=hashlib.sha256(world).hexdigest(),native_source_sha256={p.name:digest(p)for p in snapshot.iterdir()},probe_sha256={p.name:digest(p)for p in(rust,cpp)}),indent=2)+'\n')
 return native,reference
def inspect(raw,cases):
 w=struct.unpack('<'+'I'*(len(raw)//4),raw);at=0;coverage=Counter();queries=Counter()
 for case in cases:
  index,op,size=w[at:at+3];assert index==case['index']and op==case['operation'];at+=3;end=at+size;coverage[f'operation_{op}']+=1
  if op==3:assert size==13;at=end;continue
  okay,count=w[at:at+2];at+=2;error=bytes(w[at:at+count]).decode();at+=count;coverage['success'if okay else'failure']+=1
  if op in(0,4,5):
   result=w[at:at+32];at+=32;assert len(result)==32
   if not okay:assert result[12]==bits(17.) and error
   else:coverage['miss'if result[12]==bits(-1.)else'contact']+=1
   if op==5:
    other_okay,other_count=w[at:at+2];at+=2;other_error=bytes(w[at:at+other_count]).decode();at+=other_count
    assert (okay,error,result)==(other_okay,other_error,w[at:at+32]);at+=32
   else:
    length=w[at];at+=1;trace_end=at+length
    while at<trace_end:
     kind=w[at];at+=1;assert kind in(1,2);queries[f'callback_{kind}']+=1;at+=9 if kind==1 else 5
    assert at==trace_end
  elif op==1:
   present=w[at];at+=1;assert present<2
   if present:at+=26;coverage['line_hit']+=1
   if 'duplicate nearest'in case['label']:assert present and w[at-2:at]==(11,0)
  elif op==2:
   n=w[at];at+=1+n*12;assert n<=64
   coverage['nearby_triangles']+=n
   if 'SAT rejects'in case['label']:assert n==0
   if 'first64'in case['label']:assert n==64
  assert at==end,(case,at,end)
 assert at==len(w)
 assert all(coverage[f'operation_{op}']for op in range(6))
 assert coverage['contact']>32 and coverage['miss']>32 and coverage['line_hit']>32
 assert coverage['failure']>=20 and queries['callback_1']>100 and queries['callback_2']>32
 return dict(operations=dict(coverage),callbacks=dict(queries))
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);data,cases=corpus();(out/'input.bin').write_bytes(data);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
 if a.preflight:print(json.dumps(dict(cases=len(cases),input_bytes=len(data)),indent=2));return
 for name in('result.json','first-divergence.json'):(out/name).unlink(missing_ok=True)
 native,reference=build(out);expected=subprocess.check_output([str(reference)],input=data,timeout=60);actual=subprocess.check_output([str(native)],input=data,timeout=60);(out/'reference.bin').write_bytes(expected);(out/'native.bin').write_bytes(actual)
 if expected!=actual:
  byte=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));(out/'first-divergence.json').write_text(json.dumps(dict(byte=byte,reference_bytes=len(expected),native_bytes=len(actual)),indent=2)+'\n');raise AssertionError('Complete trajectory/world query differs')
 result=dict(passed=True,cases=len(cases),exact_words=len(expected)//4,sha256=hashlib.sha256(expected).hexdigest(),coverage=inspect(expected,cases),boundary='Whole unchanged core trajectory query/prediction and complete host world leaves. Real triangle broadphase, rounded line tests and full triangle/AABB SAT collector execute. Explicit callback failures separately check propagation and retained caller output. Selection/scoring/grind admission and complete gameplay scheduling remain separate. Original nonadvancing/hanging query inputs are outside this parity corpus; the native nonadvancing guard is not claimed as an original error.')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
