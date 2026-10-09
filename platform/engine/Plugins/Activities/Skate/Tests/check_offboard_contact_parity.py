#!/usr/bin/env python3
"""Complete offboard contact owner over the unchanged original static scene.

Only the root coordinator builds/runs this proof. Geometry is authored fixture
input; all queries, samples, candidates, publications and retained histories are
computed by the original and simulation owners, with exact word comparison.
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
from session_parity import PLUGIN
UNITS=('SimulationMath','Geometry','GeometrySweep','WorldGeometry','AirTrajectoryQuery','OffboardContactToolkit','OffboardContactProbes','OffboardContactCollection','OffboardContactCandidates','OffboardStaticScene')
CORE='crates/skate-core/src/player/offboard/contact_toolkit'
IDENTITY=[1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.]
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def fs(v):return list(map(bits,v))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def quad(x0,x1,z0,z1,y0,y1):
 a=[x0,y0,z0];b=[x0,y1,z1];c=[x1,y1,z1];d=[x1,y0,z0];return [a+b+c,a+c+d]
def make_world(groups,edges=(),island=3,enabled=True):
 triangles=[];meshes=[]
 for index,entry in enumerate(groups):
  vertices,pool,group,reject=entry;start=len(triangles)
  for v in vertices:triangles.append(fs(v+[0.,1.,1.,1.])+[0]+fs([.8,.6,.1])+[100+len(triangles)])
  flat=sum(vertices,[]);bounds=[min(flat[a::3])for a in range(3)]+[max(flat[a::3])for a in range(3)]
  meshes.append(dict(start=start,end=len(triangles),bounds=bounds,pool=pool,group=group,reject=reject,geometry=700+index))
 authored=[]
 for start,end in edges:authored.append(start+end+[min(start[a],end[a])for a in range(3)]+[max(start[a],end[a])for a in range(3)])
 return dict(triangles=triangles,surfaces=[(0x1234+n*13)&0xffff for n in range(len(triangles))],meshes=meshes,edges=authored,island=island,enabled=enabled)
def encode_world(w):
 words=[len(w['triangles'])]+sum(w['triangles'],[])+[int(w['enabled']),len(w['surfaces'])]+w['surfaces']+[len(w['meshes'])]
 for m in w['meshes']:words += [m['start'],m['end']]+fs(IDENTITY+IDENTITY+m['bounds'])+[m['group']&0xffffffff,m['reject'],m['geometry'],m['pool']]
 words += [len(w['edges'])]+sum((fs(e)for e in w['edges']),[])+[w['island']];return words
def packet(position=(0,0,0),speed=3,angle=0,slope=0):
 s,c=math.sin(angle),math.cos(angle);sy,cy=math.sin(slope),math.cos(slope)
 return list(position)+[0]+[s*cy,sy,c*cy,0]+[-s*sy,cy,-c*sy,0]+[c,0,-s,0]+[s*speed,0,c*speed,0]+[0,1,0,0]+[c,0,-s,0]
def request(position=(0,2,0),velocity=(0,-3,0),gravity=-9.81,duration=1):return fs(list(position)+[0]+list(velocity)+[0]+[0,gravity,0,0]+[duration,.05,.125,.25])
def corpus():
 rng=random.Random(0x82d81068);programs=[]
 floor=quad(-5,5,-5,5,0,0);ramp=quad(-5,5,-5,5,-1,1)
 wall=[[-5,0,.8,-5,1.2,.8,5,1.2,.8],[-5,0,.8,5,1.2,.8,5,0,.8]]
 step=quad(-5,5,-5,.6,0,0)+quad(-5,5,.6,5,.35,.35)+[[-5,0,.6,-5,.35,.6,5,.35,.6],[-5,0,.6,5,.35,.6,5,0,.6]]
 drop=quad(-5,5,-5,.5,0,0)+quad(-5,5,.5,5,-.65,-.65)
 edges=[([-1,0,.6],[1,0,.6]),([0,.2,-1],[0,.2,2]),([-.01,.4,-1],[-.01,.4,2])]
 worlds=[make_world([(faces,0,-1,0)],edges)for faces in (floor,ramp,wall,step,drop,floor+wall)]
 worlds += [make_world([(floor,2,-1,0)],edges,island=flags)for flags in(0,1,3)]
 worlds += [make_world([(floor,1,2,0),(floor,0,1,0),(floor,2,0,0)],edges),make_world([(floor,0,-1,0x6000),(ramp,1,-1,0)],edges)]
 worlds += [make_world([(floor*48,0,-1,0)],[([-.1,0,.3+i*.001],[.1,0,.3+i*.001])for i in range(70)])]
 worlds += [make_world([]),make_world([(floor,0,-1,0)],enabled=False)]
 for n in range(96):
  commands=[[3],[0]];world=copy.deepcopy(worlds[n%len(worlds)])
  for k in range(10):
   p=packet((rng.uniform(-.5,.5),(0,.05,.2,-.1)[(n+k)%4],rng.uniform(-.4,.4)),(0,.01,1,3,6,10)[(n+k)%6],(0,.07,-.1)[k%3],(0,.05,-.05)[n%3]);group=(-1,0,1,2)[(n+k)%4]
   commands += [[4]+fs(p)+[group&0xffffffff],[2]+fs(p)+[group&0xffffffff],[0]if k%2==0 else[3]]
   if k in(3,7):commands += [[1],[3]]
   if k==5:commands += [[2]+fs(p)+[group&0xffffffff],[7]+encode_world(worlds[(n+1)%len(worlds)]),[3]]
  lines=[fs([0,2,.2,0,0,-2,.2,0,r])for r in(0,.01,.2)]
  commands += [[5,len(lines)]+sum(lines,[])+[0xffffffff],[6]+request()+[0xffffffff,0],[6]+request((0,.5,0),(0,2,2))+[0xffffffff,0x6000]]
  programs.append(dict(label='retained actual static batches, seam replacement, samples/candidates/classification',world=world,commands=commands))
 # Exact source error gates, with a retained successful submission preceding
 # each rejected packet. No callback returns fabricated hits or normals.
 for failure in ('negative-radius','nonfinite-xyz','empty-line','subthreshold-line','trajectory-duration','trajectory-radius','trajectory-error','trajectory-lane','valid-nonfinite-W-line'):
  commands=[[2]+fs(packet())+[0xffffffff]]
  line=fs([0,2,0,0,0,-2,0,0,.05]);q=request()
  if failure=='negative-radius':line[8]=bits(-.01)
  elif failure=='nonfinite-xyz':line[1]=0x7fc12345
  elif failure=='empty-line':line[4:8]=line[:4]
  elif failure=='subthreshold-line':line[4:8]=line[:4];line[4]=bits(1.e-6)
  elif failure=='valid-nonfinite-W-line':line[3]=0x7f800000;line[7]=0x7f800000
  elif failure=='trajectory-duration':q[12]=bits(0)
  elif failure=='trajectory-radius':q[13]=bits(0)
  elif failure=='trajectory-error':q[14]=0x7f800000
  elif failure=='trajectory-lane':q[3]=0x7fc12345
  commands += [[6]+q+[0xffffffff,0]]if failure.startswith('trajectory')else[[5,1]+line+[0xffffffff]]
  commands += [[3],[0],[1]];programs.append(dict(label='actual query validation/'+failure,world=worlds[0],commands=commands))
 records=[];cases=[]
 for index,p in enumerate(programs):
  words=encode_world(p['world'])+[len(p['commands'])]+sum(p['commands'],[]);records.append(struct.pack('<'+'I'*len(words),*words));cases.append(dict(index=index,label=p['label'],triangles=len(p['world']['triangles']),commands=[c[0]for c in p['commands']]))
 return struct.pack('<I',len(records))+b''.join(records),cases
def aliases():
 out={'atelier-host/src/offboard_contact_world.rs':'crates/skate-host/src/physics/offboard/contact_toolkit/world.rs'}
 for name in ('analyzer_math','candidate','classification','collection','generation','infill','prefix','probes','profile','publication','samples','sweep'):
  out[f'atelier-host/src/toolkit/{name}.rs']=f'{CORE}/{name}.rs'
 for name in ('native_arithmetic','reciprocal_sqrt'):out[f'atelier-host/src/physics/{name}.rs']=f'crates/skate-core/src/physics/{name}.rs'
 return out
def prepare(output):
 simulation=PLUGIN/'Source/AtelierSkate/Private/Simulation';snapshot=output/'simulation-source'
 if snapshot.exists():shutil.rmtree(snapshot)
 snapshot.mkdir()
 for p in simulation.glob('*.h'):shutil.copy2(p,snapshot/p.name)
 for unit in UNITS:shutil.copy2(simulation/f'{unit}.cpp',snapshot/f'{unit}.cpp')
 cpp_world=(PLUGIN/'Tests/Simulation/world_geometry_probe.cpp').read_text().split('int main()')[0]
 rust_world=(PLUGIN/'Tests/Reference/world_geometry_probe.rs').read_text().split('struct Query {')[0]
 core=source(CORE+'.rs');probe=snapshot/'offboard_contact_probe.cpp';probe.write_text((PLUGIN/'Tests/Simulation/offboard_contact_probe.cpp').read_text().replace('// WORLD_PROTOCOL',cpp_world))
 generated=output/'offboard-contact-reference.rs';generated.write_text((PLUGIN/'Tests/Reference/offboard_contact_probe.rs').read_text().replace('// WORLD_PROTOCOL',rust_world).replace('// ORIGINAL_TOOLKIT',core))
 report=dict(simulation_source_sha256={p.name:digest(p)for p in snapshot.iterdir()},original_toolkit_body_sha256=hashlib.sha256(core.encode()).hexdigest(),original_alias_sha256={d:hashlib.sha256(source(s).encode()).hexdigest()for d,s in aliases().items()},cpp_world_transport_sha256=hashlib.sha256(cpp_world.encode()).hexdigest(),rust_world_transport_sha256=hashlib.sha256(rust_world.encode()).hexdigest())
 (output/'simulation-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return probe,snapshot,generated
class Reader:
 def __init__(self,raw):self.words=struct.unpack('<'+'I'*(len(raw)//4),raw);self.at=0
 def word(self):v=self.words[self.at];self.at+=1;return v
 def skip(self,n):self.at+=n;assert self.at<=len(self.words)
 def take(self,n):v=self.words[self.at:self.at+n];self.skip(n);return v
def audit_input(raw,cases):
 r=Reader(raw);assert r.word()==len(cases)
 def world():
  r.skip(18*r.word());r.skip(1);r.skip(r.word());r.skip(36*r.word());r.skip(12*r.word());r.skip(1)
 for case in cases:
  world();assert r.word()==len(case['commands'])
  for expected in case['commands']:
   op=r.word();assert op==expected
   if op in(2,4):r.skip(29)
   elif op==5:r.skip(9*r.word());r.skip(1)
   elif op==6:r.skip(18)
   elif op==7:world()
   else:assert op in(0,1,3)
 assert r.at==len(r.words)
def inspect(raw,cases):
 r=Reader(raw);coverage=Counter();flags=Counter();kinds=Counter();queries=Counter();samples=Counter();errors=Counter()
 def status():
  okay=r.word();size=r.word();text=''.join(map(chr,r.take(size)));errors[text]+=not okay;return okay
 def descriptors():r.skip(12*r.word())
 def layout():r.skip(27);descriptors();descriptors()
 def batch():r.skip(78);r.skip(9*r.word());descriptors();descriptors()
 def prefix():
  p=r.take(46);flags[p[44]]+=1;kinds[p[41]]+=1
 def query():
  q=r.take(32);queries['hit'if q[12]&0x80000000==0 else'miss']+=1
 def results():
  for _ in range(3):query()
  for _ in range(r.word()):
   if r.word():r.skip(27);queries['line-hit']+=1
  edges=r.word();assert edges<=40;queries['edges']+=edges;r.skip(edges*8)
 def sample_out():
  ground=r.word();assert ground<=64;samples['ground']+=ground;r.skip(ground*12);other=r.word();samples['other']+=other;r.skip(other*12);original=r.word();assert original<=64
 def collected():
  if r.word():batch();results();prefix();sample_out();coverage['completed']+=1
 def owner():
  layout()
  if r.word():batch();results();coverage['pending-observed']+=1
  readiness=r.word();assert readiness in(0,30);prefix();r.skip(18);r.skip(5)
 for case in cases:
  assert r.word()==case['index'];end=r.word()+r.at;status();owner();assert r.word()==len(case['commands'])
  for op in case['commands']:
   assert r.word()==op;coverage[op]+=1
   if op in(2,4):
    okay=status()
    if op==4 and okay:results()
   elif op==3:collected()
   elif op==5:
    if status():
     for _ in range(r.word()):
      if r.word():r.skip(8);queries['ground-line-hit']+=1
   elif op==6:
    if status():query()
   elif op==7:status()
   owner()
  assert r.at==end,(case,r.at,end)
 assert r.at==len(r.words);assert all(coverage[n]for n in range(8));assert queries['hit']and queries['miss']and samples['ground']and samples['other'];assert any(count for name,count in errors.items()if name)
 return dict(operations={str(k):v for k,v in coverage.items()},prefix_flags={str(k):v for k,v in flags.items()},classification_kinds={str(k):v for k,v in kinds.items()},queries=dict(queries),samples=dict(samples),errors=dict(errors))
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--target-dir',required=True,type=Path);p.add_argument('--preflight',action='store_true');a=p.parse_args();output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
 blob,cases=corpus();audit_input(blob,cases);(output/'input.bin').write_bytes(blob);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');probe,snapshot,generated=prepare(output);summary=dict(histories=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(blob),input_sha256=hashlib.sha256(blob).hexdigest(),units=UNITS)
 if a.preflight:print(json.dumps(summary,indent=2));return
 simulation=output/'offboard-contact-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{u}.cpp')for u in UNITS],str(probe),'-o',str(simulation)],check=True)
 reference=build_probe(output,'offboard-contact-reference',generated,a.target_dir,bevy=True,extra_sources=aliases())
 expected=subprocess.check_output([str(reference)],input=blob);actual=subprocess.check_output([str(simulation)],input=blob);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
 if expected!=actual:
  first=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)))//4;at=0;words=struct.unpack('<'+'I'*(len(expected)//4),expected)
  for case in cases:
   end=at+2+words[at+1]
   if first<end:break
   at=end
  divergence=dict(first_word=first,case=case,case_first_word=at,reference_bytes=len(expected),cpp_bytes=len(actual));(output/'first-divergence.json').write_text(json.dumps(divergence,indent=2)+'\n');raise AssertionError(divergence)
 coverage=inspect(expected,cases);result=dict(passed=True,**summary,exact_words=len(expected)//4,output_sha256=hashlib.sha256(expected).hexdigest(),coverage=coverage,comparison='Full original analyzer and concrete authored static-world scene; every retained batch, candidate, history, prefix, sample and actual query result is compared exactly.',limitations='This family proves Stock probe layout and its complete actual scene/analyzer; Biped Ground/Air scheduling, feet, grab and selector owners are separate following families.')
 (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
