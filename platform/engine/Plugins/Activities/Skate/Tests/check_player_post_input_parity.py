#!/usr/bin/env python3
"""Exact complete PostInput kernel/history/candidate copy and service call order.

Independent service results are explicit inputs to both kernels. This proof
does not claim parity for the host Grind/trajectory/grab producers or frame.
Only root invokes either compiler/executable under the shared render guard.
"""
import argparse
from collections import OrderedDict,Counter
import hashlib
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
import player_input_protocol as wire
from reference_build import build_probe
from session_parity import PLUGIN,digest
CODE=PLUGIN/'Source/AtelierSkate/Private/Native'
DEFS=OrderedDict([
 ('PostInputPlayerFields',[('jump_reference_1264','[u32;4]'),('flags_1296','u32'),('state_frames_1304','u32'),('jump_fix_frames_1308','u32'),('latch_frames_1320','u32')]),
 ('PostInputProcessedFields',[('jump_reference_848','[u32;4]'),*[(n,'u32')for n in ('word_2464','flags_2468','flags_2472','flags_2480','flags_2484','current_state_2508','state_frames_2572','jump_fix_frames_2576')],('scalar_2740','f32')]),
 ('PostInputPhysOutFields',[('reset_state_frames_316','bool'),('capture_jump_reference_442','bool'),('jump_reference_128','[u32;4]'),('complete_76','bool')]),
 ('CandidatePublicationFields',[(n,'bool')for n in ('first_object_present_196','first_pending_288','second_object_present_500','second_pending_592')]+[(n,'u32')for n in ('staged_word_12768','staged_valid_12772','staged_latched_12776')]+[('staged_pending_12780','bool')]),
])
def protocol():
 cpp=[];rust=[]
 for name,fields in DEFS.items():
  cpp.append(f'{name} Read{name}(Input& i){{{name} s;'+''.join('s.'+f+'='+wire.read_expr(k,'cpp')+';'for f,k in fields)+'return s;}')
  cpp.append(f'void Observe(Output& o,const {name}& s){{'+''.join(wire.observe_expr(k,'s.'+f,'cpp')for f,k in fields)+'}')
  rust.append(f'fn read_{name}(i:&mut Input)->{name}{{{name}{{'+''.join(f+':'+wire.read_expr(k,'rust')+','for f,k in fields)+'}}')
  rust.append(f'fn observe_{name}(o:&mut Output,s:&{name}){{'+''.join(wire.observe_expr(k,'s.'+f,'rust')for f,k in fields)+'}')
 return '\n'.join(cpp),'\n'.join(rust)
def corpus():
 rng=random.Random(0x82db5588);words=[];cases=[]
 def append(*values):words.extend(int(v)&0xffffffff for v in values)
 append(96)
 for c in range(96):
  player=[rng.getrandbits(32)for _ in range(8)];player[5:]=[(0,19,20,21,0xffffffff,0x7fffffff,0x80000000)[(c+n)%7]for n in range(3)]
  processed=[rng.getrandbits(32)for _ in range(13)];output=[c%2,(c//2)%2]+[rng.getrandbits(32)for _ in range(4)]+[1]
  candidate=[(c>>n)&1 for n in range(4)]+[rng.getrandbits(32),c%3,c%5,(c>>4)&1]
  initial=player+processed+output+candidate;append(*initial);operations=[]
  for t in range(320):
   if t%13==7:
    dest=[rng.getrandbits(32)for _ in range(72)];source=[rng.getrandbits(32)for _ in range(72)];operations.append(dict(op=1,destination=dest,source=source))
   flags=[rng.getrandbits(32)for _ in range(4)];state=(100,101,103,200,400,500,501,702)[(c+t)%8]
   if c%8==0:
    # A real bit21 latch followed by sustained bit15 retains its source
    # history past the21-frame expiry branch, rather than resetting each pass.
    flags[0]=0x00200000 if t==0 else 0;flags[1]=0x8000;flags[2]=0
   physical=[t%17==0,(t+c)%11==0]+[rng.getrandbits(32)for _ in range(4)]+[t%2]
   candidate=[((c+t)>>n)&1 for n in range(4)]+[rng.getrandbits(32),(t%3),(t%5),((c+t)>>4)&1]
   heading=(0,0x80000000,1,0x7f800000,0xff800000,0x7fc12345,0xff812345,0x3e0c49ba)[(c+t)%8]
   operations.append(dict(op=0,values=flags+[state]+physical+candidate+[t%256,heading]))
  append(len(operations))
  for op in operations:append(op['op'],*(op['values']if op['op']==0 else op['destination']+op['source']))
  cases.append(dict(case=c,initial=initial,operations=operations))
 return struct.pack('<'+'I'*len(words),*words),cases
def coverage(raw,cases):
 words=list(struct.unpack('<'+'I'*(len(raw)//4),raw));at=0;proof=Counter();latches=set();headings=set();wraps=0
 def take(n):
  nonlocal at
  out=words[at:at+n];at+=n;assert len(out)==n;return out
 assert take(1)==[len(cases)]
 for case in cases:
  assert take(2)==[case['case'],len(case['operations'])];prior=case['initial'][:8]
  for row in case['operations']:
   assert take(1)==[row['op']]
   if row['op']==1:
    output=take(72);dest=row['destination'];src=row['source'];expected=dest.copy();expected[:50]=src[:50];expected[50]=(dest[50]&0x1fffffff)|(src[50]&0xe0000000);expected[51:55]=src[51:55];expected[56:66]=src[56:66];expected[68]=src[68];assert output==expected;proof['exact record copy and retained padding']+=1
   else:
    values=row['values'];calls=take(take(1)[0]);assert calls==[1,2,3]+([4]if values[12]and values[13]else[])+([5]if values[14]and values[15]else[])
    fields=take(36);player=fields[:8];processed=fields[8:21];output=fields[21:28];candidate=fields[28:]
    assert output[6]==1 and candidate[1]==candidate[3]==candidate[7]==0
    assert processed[12]==values[-1]and processed[:4]==player[:4]and processed[10]==player[5]and processed[11]==player[6]
    if not values[6]:assert player[6]==(prior[6]+1)&0xffffffff
    else:assert player[6]==1 and player[:4]==values[7:11]
    wraps+=player[6]<prior[6]and not values[6];latches.add(player[7]);headings.add(processed[12]);proof['actual ordered service pass']+=1;proof['first candidate callbacks']+=4 in calls;proof['second candidate callbacks']+=5 in calls;prior=player
 assert at==len(words)and proof['actual ordered service pass']==30720 and proof['exact record copy and retained padding']>2000
 assert len(latches)>25 and len(headings)==8 and wraps>0
 return dict(proof,distinct_latch_histories=len(latches),opaque_heading_words=len(headings),retained_unsigned_wraps=wraps)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path);p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 for name in('result.json','first-divergence.json'):(out/name).unlink(missing_ok=True)
 blob,cases=corpus();(out/'input.bin').write_bytes(blob);(out/'cases.json').write_text(json.dumps(cases)+'\n');cpp,rust=protocol();snapshot=out/'native-source';snapshot.mkdir(exist_ok=True)
 for name in('PlayerPostInput.h','PlayerPostInput.cpp'):shutil.copy2(CODE/name,snapshot/name)
 np=PLUGIN/'Tests/Native/player_post_input_probe.cpp';rp=PLUGIN/'Tests/Reference/player_post_input_probe.rs';(snapshot/np.name).write_text(np.read_text().replace('// GENERATED_PROTOCOL',cpp));reference=out/rp.name;reference.write_text(rp.read_text().replace('// GENERATED_PROTOCOL',rust))
 report=dict(histories=len(cases),commands=sum(len(c['operations'])for c in cases),input_bytes=len(blob),input_sha256=hashlib.sha256(blob).hexdigest(),native_source_sha256={q.name:digest(q)for q in snapshot.iterdir()},proof_sha256={q.name:digest(q)for q in(Path(__file__),np,rp)},scope=__doc__);(out/'preflight.json').write_text(json.dumps(report,indent=2)+'\n')
 if a.preflight:print(json.dumps(report,indent=2));return
 assert a.target_dir
 native=out/'player-post-input-native';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),str(snapshot/'PlayerPostInput.cpp'),str(snapshot/np.name),'-o',str(native)],check=True)
 oracle=build_probe(out,'player-post-input-reference',reference,a.target_dir);expected=subprocess.check_output([str(oracle)],input=blob);actual=subprocess.check_output([str(native)],input=blob);(out/'reference.bin').write_bytes(expected);(out/'native.bin').write_bytes(actual)
 if expected!=actual:
  first=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));(out/'first-divergence.json').write_text(json.dumps(dict(byte=first,reference_bytes=len(expected),native_bytes=len(actual)))+'\n');raise AssertionError('PostInput differs')
 result=dict(passed=True,**report,exact_output_bytes=len(expected),output_sha256=hashlib.sha256(expected).hexdigest(),coverage=coverage(expected,cases));(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
