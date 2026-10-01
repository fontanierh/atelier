#!/usr/bin/env python3
"""Complete original board animation history and air/plant root producers.

Compile and execute only through the shared render/memory guard. Every original
core file remains byte-identical. Whole host SkeletonAir/GeneralUpdate and
concrete physical producers remain separately verified composition boundaries.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tarfile
import check_skeleton_root_frames_parity as roots

PLUGIN=roots.PLUGIN
UNITS=('NativeMath','RigidBody','BodyMass','AggregateMass','DeckGeometry','DriveFrames','ConstraintFrames','SkeletonPoseFrames','BoardGroundAngle','SkeletonRoot','SkeletonBoardFrames','BoardAnimation','SkeletonAirFrames')
OPERATIONS=('reset','capture','apply','velocity','prepare_animated','known_roots','prepare_known','finish_known','plant_roots','seed_error')
STATE_WORDS=roots.STATE_WORDS+5
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def f(values):return list(map(bits,values))
def corpus():
 rng=random.Random(0x82c04368);records=[];cases=[]
 def matrix(t=0,carry=0):
  s,c=math.sin(t),math.cos(t)
  return f([c,0,-s,carry,0,1,0,-carry,s,0,c,carry,t*.137,.317,t*.731,carry])
 def root(seed):
  return matrix(seed*.13)+matrix(-seed*.17)+f([.137,.317,.731,.517]*2)+[seed%2]+f([11,12,13,14])+matrix(seed*.11)+matrix(seed*.21)+matrix(-seed*.21)+matrix(seed*.31)+[int(seed%3!=0)]
 def board(seed):return sum((matrix(seed*.013*(i+1))for i in range(5)),[])+f([.137,.317,.731,.517]*5+[.05])
 def add(label,commands,seed=0,y=.13,active=True,error=None):
  error=f([.03,.07,-.11,.991]) if error is None else error
  settings=f([0,.02,.05,.1,.2,.5,1,math.pi]+[y]*8+[0,.02,.05,.1,.2,.5,1,math.pi]+[y*.73]*8)
  raw=root(seed)+board(seed)+settings+error+[int(active),len(commands)]+[v for c in commands for v in c]
  assert len(root(seed))==roots.ROOT_WORDS and len(board(seed))==roots.BOARD_WORDS
  cases.append(dict(index=len(cases),label=label,commands=[c[0]for c in commands]));records.append(struct.pack('<'+'I'*len(raw),*raw))
 for seed in range(96):
  commands=[]
  for tick in range(32):
   if tick%7==0:commands.append([1]+matrix(seed*.11+tick*.03,.137)+matrix(seed*.13-tick*.07,-.517))
   if tick%11==0:commands.append([0])
   commands += [[2]+matrix(tick*.031,.731)+[tick%2],[4]+matrix(tick*.041,.317)+[rng.getrandbits(32)],
    [5]+matrix(tick*.017)+f([tick*.137,.317,tick*.731,.517,.071,.137,.731,.317])+[tick%3==0,(1,2,6,99,0x80000000,0xffffffff)[tick%6],seed%2],
    [6]+matrix(tick*.013,.137)+[rng.getrandbits(32)],[7]+matrix(tick*.037,.517),
    [8]+matrix(tick*.053)+f([.137*tick,.317,.731*tick,.517,.031,.071,.137,.317]),
    [3]+f([tick*.137,.317,tick*.731,.517,.031,-.071,.137,-.317,(1/60,1/120,1/30)[tick%3]])]
  add('retained capture/reset/air/plant histories including unsigned revert count',commands,seed)
 for seed,y in enumerate((0.,-.137,.949999988079071,.9500000476837158,1.,1.137)):
  for active in (False,True):
   for q in ([0,0,0,1],[0,0,0,-1],[.137,.317,.731,.517],[0,0,0,.999],[0,0,0,-.999]):
    add('active gate, quaternion sign, linear/spherical branch and exact completion threshold',[[2]+matrix(.731,.317)+[0],[0],[2]+matrix(.517,-.137)+[1]],seed,y,active,f(q))
 for payload in (0x7fc00001,0x7fc12345):
  y=roots.value(payload)
  add('unordered graph output completes without changing target',[[2]+matrix(.731,.317)+[0]],y=y)
 for seed in range(20):
  dt=(0.,-0.,.0001,-.125,.033)[seed%5]
  add('target velocity exact division and fourth lanes',[[3]+f([.137,.317,.731,.517,-.071,.131,-.317,.517,dt])],seed)
 return struct.pack('<I',len(records))+b''.join(records),cases
def build(out):
 root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip());relative=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-core/src').relative_to(root).as_posix()
 archive=subprocess.check_output(['git','archive',f'{roots.REFERENCE_REVISION}:{relative}'],cwd=root);source=out/'reference-source'
 if source.exists():shutil.rmtree(source)
 source.mkdir()
 with tarfile.open(fileobj=io.BytesIO(archive))as stream:stream.extractall(source,filter='data')
 original={p.relative_to(source).as_posix():roots.digest(p)for p in source.rglob('*.rs')}
 rust_prefix=PLUGIN/'Tests/Reference/skeleton_root_frames_probe.rs';rust_probe=PLUGIN/'Tests/Reference/skeleton_air_frames_probe.rs';main=source/'air-frames-oracle.rs'
 main.write_text((source/'lib.rs').read_text()+rust_prefix.read_text().split('fn main(){',1)[0]+rust_probe.read_text());reference=out/'air-frames-reference'
 subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
 assert all(roots.digest(source/p)==sha for p,sha in original.items())
 live=PLUGIN/'Source/AtelierSkate/Private/Native';snapshot=out/'native-source'
 if snapshot.exists():shutil.rmtree(snapshot)
 snapshot.mkdir()
 for p in list(live.glob('*.h'))+[live/(n+'.cpp')for n in UNITS]:shutil.copy2(p,snapshot/p.name)
 cpp_prefix=PLUGIN/'Tests/Native/skeleton_root_frames_probe.cpp';cpp_probe=PLUGIN/'Tests/Native/skeleton_air_frames_probe.cpp';combined=snapshot/cpp_probe.name
 combined.write_text(cpp_prefix.read_text().split('int main()',1)[0]+cpp_probe.read_text());native=out/'air-frames-native'
 subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(n+'.cpp'))for n in UNITS],str(combined),'-o',str(native)],check=True)
 (out/'provenance.json').write_text(json.dumps(dict(reference_revision=roots.REFERENCE_REVISION,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=original,native_source_sha256={p.name:roots.digest(p)for p in snapshot.iterdir()},probe_sha256={p.name:roots.digest(p)for p in (rust_prefix,rust_probe,cpp_prefix,cpp_probe)}),indent=2)+'\n')
 return native,reference
def inspect(raw,cases):
 words=struct.unpack('<'+'I'*(len(raw)//4),raw);at=0;coverage=Counter();errors=set();roots_seen=set()
 for case in cases:
  index,n,size=words[at:at+3];assert index==case['index']and n==len(case['commands']);cursor=at+3;end=cursor+size
  previous=words[cursor:cursor+STATE_WORDS];cursor+=STATE_WORDS
  for op in case['commands']:
   assert words[cursor]==op;cursor+=1;extra={2:16,3:4,4:17,6:17}.get(op,0);result=words[cursor:cursor+extra];cursor+=extra
   current=words[cursor:cursor+STATE_WORDS];cursor+=STATE_WORDS;assert len(current)==STATE_WORDS;coverage[OPERATIONS[op]]+=1
   if op==0:assert current[-5:-1]==tuple(f([0,0,0,1]))and current[-1]==previous[-1];coverage['reset_retains_blending']+=current[-1]
   if op==1:assert current[-1]==1;coverage['captures']+=1
   if op in (4,6):assert result[-1]&(1<<19);coverage['flags_preserved']+=1
   if op==7:assert current[40]==1 and current[41:45]==current[36:40] and current[110:126]==current[126:142];coverage['predictions_published']+=1
   if op==8:assert current[:61]==previous[:61]and current[93:]==previous[93:];coverage['plant_retains_heading_prediction']+=1
   if op in (0,1,2,3,9):assert current[:roots.STATE_WORDS]==previous[:roots.STATE_WORDS]
   if op==2:coverage['completed_blends']+=previous[-1]and not current[-1];coverage['inactive_applies']+=not previous[-1]
   errors.add(current[-5:-1]);roots_seen.add(current[77:93]);previous=current
  assert cursor==end;at=end
 assert at==len(words)and all(coverage[n]>0 for n in OPERATIONS if n!='seed_error')
 assert coverage['completed_blends']>0 and coverage['reset_retains_blending']>0 and len(errors)>20 and len(roots_seen)>20
 return dict(operations=dict(coverage),rotation_histories=len(errors),root_histories=len(roots_seen))
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 data,cases=corpus();(out/'input.bin').write_bytes(data);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
 if a.preflight:print(json.dumps(dict(histories=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(data)),indent=2));return
 for name in ('result.json','first-divergence.json'):(out/name).unlink(missing_ok=True)
 native,reference=build(out);expected=subprocess.check_output([str(reference)],input=data);actual=subprocess.check_output([str(native)],input=data);(out/'reference.bin').write_bytes(expected);(out/'native.bin').write_bytes(actual)
 if expected!=actual:
  byte=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));(out/'first-divergence.json').write_text(json.dumps(dict(byte=byte,reference_bytes=len(expected),native_bytes=len(actual)),indent=2)+'\n');raise AssertionError('Board animation/air frames differ')
 result=dict(passed=True,histories=len(cases),commands=sum(len(c['commands'])for c in cases),exact_words=len(expected)//4,sha256=hashlib.sha256(expected).hexdigest(),coverage=inspect(expected,cases),boundary='Whole unchanged original board_animation and skeleton_air_frames including all reset/capture/apply/target velocity and animated/known/plant root producers. Configured curves and input transforms are explicit. Complete host SkeletonAir/GeneralUpdate/physical producer scheduling remains separate.')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
