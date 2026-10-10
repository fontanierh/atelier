#!/usr/bin/env python3
"""Whole authored grab scene and retained query/validation/publication owner.

Only the root builds or executes. Actual world triangles and authored provider
objects/physical associations are explicit inputs. No completed grab/collision
record is supplied; all records and line hits are produced by original owners.
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
import check_offboard_contact_parity as contact
PLUGIN=contact.PLUGIN
HOST='crates/skate-host/src/physics/'
FAMILY=('OffboardGrabRecord','OffboardGrabRegistry','OffboardGrabPolyline','OffboardGrabQualify','OffboardGrabQuery','OffboardGrabCollision','OffboardGrabRuntime')
UNITS=tuple(dict.fromkeys(contact.UNITS+('OffboardGrabCache',)+FAMILY))
bits,fs,Reader=contact.bits,contact.fs,contact.Reader
IDENTITY=[1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.]
def frame(x=0,y=0,z=0,angle=0):
 s,c=math.sin(angle),math.cos(angle);return [c,0,-s,0,0,1,0,0,s,0,c,0,x,y,z,1]
def geometry(identity=1,y=.3,z=1,curve=False,points=None,approach=None):
 return dict(id=identity,points=points or([[-1,y,z,0],[0,y+.07,z+.06,0],[1,y,z,0]]if curve else[[-1,y,z,0],[0,y,z,0],[1,y,z,0]]),approach=approach if approach is not None else[[0,0,-1,0]],word60=0x12345678)
def obj(identity=1,assembly=100,kind=0,variant=0,group=-1,curve=False,count=2):
 return dict(id=identity,provider=kind,variant=variant,group=group,enabled=True,disabled=False,ready=True,assembly=None if assembly is None else dict(id=assembly,part=dict(id=assembly+1000,rates=dict(id=assembly+2000,velocity=[.1,.2,.3,.17],position=[.11,.22,.33,1]),coefficients=[.13+i*.11 for i in range(10)])),frame=frame(),vector=[.13,.17,.19,.23],splines=[dict(kind=2,id=identity*100+i,geometry=geometry(identity*100+i,curve=curve,z=1+i*.04),word272=0x11223344+i)for i in range(count)])
def encode_geometry(g):return [g['id'],len(g['points'])]+sum((fs(p)for p in g['points']),[])+[len(g['approach'])]+sum((fs(p)for p in g['approach']),[])+[g['word60']]
def encode_object(o):
 words=[o['id'],o['provider'],o['variant'],o['group']&0xffffffff,int(o['enabled']),int(o['disabled']),int(o['ready']),int(o['assembly']is not None)]
 if o['assembly']is not None:
  a=o['assembly'];words += [a['id'],int(a['part']is not None)]
  if a['part']is not None:
   p=a['part'];words += [p['id'],int(p['rates']is not None)]
   if p['rates']is not None:r=p['rates'];words += [r['id']]+fs(r['velocity']+r['position'])
   words += fs(p['coefficients'])
 words += fs(o['frame']+o['vector'])+[len(o['splines'])]
 for s in o['splines']:words += [s['kind'],s['id']]+encode_geometry(s['geometry'])+[s['word272']]
 return words
def registry(objects=None,bindings=None):return dict(objects=objects or[],bindings=bindings or[])
def encode_registry(r):return [len(r['objects'])]+sum((encode_object(o)for o in r['objects']),[])+[len(r['bindings'])]+sum((list(b)for b in r['bindings']),[])
def query(op=0,position=(0,.3,0,.17),sort=None,axes=None,extent=(2,1,2,.19),margin=.05,a=1.6,b=.8,mode=4,cap=5,flags=0,group=-1):
 return [op]+fs(list(position)+list(sort or position)+(axes or frame(y=.3,z=.8))+list(extent)+[margin,a,b])+[mode,cap,flags,group&0xffffffff]
def lines(start=(0,.3,0,.17),end=(0,.3,2,.19),radius=.2,group=-1,reject=0,mask=7,flags=0):return [11]+fs(list(start)+list(end)+[radius])+[group&0xffffffff,reject,mask,flags]
def interact(axes=None,flags=0,group=-1):return [2]+fs(axes or frame(y=.3))+[flags,group&0xffffffff]
def sync(flags=0,group=-1):return [4,flags,group&0xffffffff]
def qualify(descriptor=(2,100),position=(0,.3,0,.17),axes=None,extent=(2,1,2,0),margin=.05,a=1.6,b=.8):return [15]+list(descriptor)+fs(list(position)+(axes or frame(y=.3,z=.8))+list(extent)+[margin,a,b])
def corpus():
 rng=random.Random(0x82d73fc0);floor=contact.quad(-8,8,-8,8,0,0);wall=[[-8,-1,.5,-8,3,.5,8,3,.5],[-8,-1,.5,8,3,.5,8,-1,.5]]
 worlds=[contact.make_world([(floor,0,-1,0)]),contact.make_world([(wall,1,-1,0)]),contact.make_world([(wall,0,-1,0)]),contact.make_world([(wall,2,-1,0)],island=3),contact.make_world([(wall,2,-1,0)],island=1),contact.make_world([(wall,1,1,0),(floor,0,2,0)]),contact.make_world([(wall,1,-1,4)]),contact.make_world([]),contact.make_world([(floor,0,-1,0)],enabled=False)]
 one=registry([obj()],[(700,100)]);two=registry([obj(),obj(2,200,kind=1,curve=True)],[(700,100)]);unbound=registry([obj()]);many=registry([obj(i+1,100+i,kind=i%2,variant=(i//2)%2,curve=i%3==0)for i in range(40)],[(700,100)])
 groups=[one,two,unbound,many];programs=[]
 for n in range(64):
  w=worlds[n%7];reg=copy.deepcopy(groups[n%4]);commands=[]
  for k in range(8):
   flags=2*(k%2);group=(-1,1,2)[(n+k)%3];q=query(flags=flags,group=group,position=(rng.uniform(-.25,.25),.3,rng.uniform(-.05,.05),.17),sort=(rng.uniform(-1,1),.3,0,.13),cap=(0,5,32)[k%3])
   commands += [q,query(flags=flags,group=group,op=9),[1,2,100+(k%2)],interact(flags=flags,group=group),[3],sync(flags,group),[8]+fs([0,.3,0,.17]),[5],sync(flags,group),[8]+fs([0,.3,0,.17]),[5]]
   if k in(2,5):
    changed=copy.deepcopy(reg);changed['objects'][0]['frame']=frame(x=.03*(k+1));changed['objects'][0]['splines'][0]['geometry']['points'][1][1]+=.03
    commands += [[13]+encode_registry(changed),q,[3],sync(flags,group),[8]+fs([0,.3,0,.17]),sync(flags,group),[5]]
   if k==3:commands += [interact(frame(z=.2)),interact(frame(z=.5)),[6],[3],sync(),[5]]
  commands += [[10,1,100],[10,2,100],[10,9,100],[10,2,99999],qualify(),lines(),lines(mask=2),[16]+fs([0,.3,0,.17,-1,.3,1,.11,1,.3,1,.19]),[7],[5]]
  programs.append(dict(label='actual provider queries, deferred validation, moving descriptor refresh, ordered publication',world=w,registry=reg,commands=commands))
 for mode,cap in((3,5),(4,33),(4,0xffffffff)):
  commands=[query(),query(mode=mode,cap=cap),[1,2,100],interact(),[3],sync(),[5],query(),[6],[3],sync(),[5]]
  programs.append(dict(label='bounded queued failure retains prior result and descriptors',world=worlds[0],registry=one,commands=commands))
 for failure in('W-position','negative-radius','nan-radius','W-line','short-line','zero-line','query-position','query-frame','query-margin-nan','query-angle-nan'):
  q=query(op=9);line=lines()
  if failure=='W-position':q[4]=0x7fc12345
  elif failure=='negative-radius':line[9]=bits(-.01)
  elif failure=='nan-radius':line[9]=0x7fc12345
  elif failure=='W-line':line[4]=0x7f800000
  elif failure=='short-line':line[5:9]=line[1:5];line[5]=bits(1.e-7)
  elif failure=='zero-line':line[5:9]=line[1:5]
  elif failure=='query-position':q[2]=0x7fc12345
  elif failure=='query-frame':q[9]=0x7fc12345
  elif failure=='query-margin-nan':q[29]=0x7fc12345
  else:q[30]=0x7fc12345
  commands=[query(),[3],sync(),sync(),q,line,[5],qualify(),[7]];programs.append(dict(label='exact query/line scalar/W/degeneracy contracts/'+failure,world=worlds[0],registry=one,commands=commands))
 # Real Resolve re-reads the current physical transform; request.take occurs
 # before its error and the query prefix remains committed.
 invalid=frame();invalid[15]=float('nan')
 commands=[query(flags=2),[1,2,100],interact(),[14,0]+fs(invalid),[3],[5],[14,0]+fs(frame(x=.1)),[3],sync(),[5],[1,2,100],[3],[5],[12]+contact.encode_world(worlds[-1]),query(),[3],sync(),[5],[12]+contact.encode_world(worlds[0]),sync(),[5]]
 programs.append(dict(label='current transform resolve and source take-before-error/old-validation partial prefixes',world=worlds[0],registry=one,commands=commands))
 for domain in('single-kind1','single-kind2','identical-points','empty-approach','maximum-point-count','maximum-approach-count'):
  r=copy.deepcopy(one);s=r['objects'][0]['splines'][0];g=s['geometry']
  if domain.startswith('single'):g['points']=[[0,.3,1,0]];s['kind']=1 if domain=='single-kind1'else 2
  elif domain=='identical-points':g['points']=[[0,.3,1,0]]*3
  elif domain=='empty-approach':g['approach']=[]
  elif domain=='maximum-point-count':g['points']=[[-1+i/127,.3,1,0]for i in range(255)]
  else:g['approach']=[[0,0,-1,0]]*255
  commands=[[10,s['kind'],100],[1,s['kind'],100],query(),[3],sync(),sync(),[5],qualify((s['kind'],100)),[16]+fs([0,.3,0,.17,0,.3,1,0,0,.3,1,0]),[7],[5]]
  programs.append(dict(label='original-valid simulation byte point/approach-count and zero-straight-length record domain/'+domain,world=worlds[0],registry=r,commands=commands))
 failures=('object-id','variant','descriptor','geometry-id','empty-points','point-count','approach-count','nonfinite-point','nonfinite-approach','nonfinite-frame','nonfinite-vector','assembly-id','part-id','rates-id','duplicate-object','binding-zero','binding-missing','binding-duplicate')
 for failure in failures:
  r=copy.deepcopy(one);o=r['objects'][0];g=o['splines'][0]['geometry']
  if failure=='object-id':o['id']=0
  elif failure=='variant':o['variant']=2
  elif failure=='descriptor':o['splines'][0]['kind']=3
  elif failure=='geometry-id':g['id']=0
  elif failure=='empty-points':g['points']=[]
  elif failure=='point-count':g['points']=[[0,0,0,0]]*256
  elif failure=='approach-count':g['approach']=[[0,0,-1,0]]*256
  elif failure=='nonfinite-point':g['points'][0][3]=float('nan')
  elif failure=='nonfinite-approach':g['approach'][0][3]=float('nan')
  elif failure=='nonfinite-frame':o['frame'][15]=float('nan')
  elif failure=='nonfinite-vector':o['vector'][3]=float('nan')
  elif failure=='assembly-id':o['assembly']['id']=0
  elif failure=='part-id':o['assembly']['part']['id']=0
  elif failure=='rates-id':o['assembly']['part']['rates']['id']=0
  elif failure=='duplicate-object':r['objects'].append(copy.deepcopy(o))
  elif failure=='binding-zero':r['bindings']=[(700,0)]
  elif failure=='binding-missing':r['bindings']=[(99999,100)]
  else:r['bindings']=[(700,100),(700,200)]
  commands=[query(),[1,2,100],interact(),[3],sync(),[13]+encode_registry(r),[3],sync(),[5],[13]+encode_registry(one),sync(),[3],[5],[7]];programs.append(dict(label='full original registry/record/binding rejection and retained owner recovery/'+failure,world=worlds[0],registry=one,commands=commands))
 for n in range(24):
  r=copy.deepcopy(two);o=r['objects'][0]
  if n%6==0:o['disabled']=True
  elif n%6==1:o['ready']=False
  elif n%6==2:o['assembly']=None
  elif n%6==3:o['assembly']['part']=None
  elif n%6==4:o['assembly']['part']['rates']=None
  else:o['enabled']=False
  r['objects'][1]['frame']=frame(x=(0,14.9,15,18)[n%4]);o['splines'][0]['geometry']['points']=[[-1,.3,1,0],[-1,.3,1,0],[0,.5,1,0],[1,.3,1,0]]
  commands=[]
  for k in range(8):
   commands += [query(flags=2*(k%2),group=(-1,1,2)[k%3],op=9,cap=(0,1,5,32)[k%4]),qualify(position=((-.9,0,.9)[k%3],(.3,1,-1)[k%3],0,.17),margin=(0,.1,1,3)[k%4],a=(0,.01,.5,3.2)[k%4],b=(0,.01,.5,3.2)[k%4]),[10,2,100],[8]+fs([0,(.3,1,-1)[k%3],0,.13]),[16]+fs([0,0,0,.11,0,0,0,.19,(0,1.e-7,.1,1)[k%4],0,0,.17])]
  programs.append(dict(label='provider eligibility, physical optional parts/rates, full curved/duplicate polyline and qualify boundaries',world=worlds[0],registry=r,commands=commands))
 records=[];cases=[]
 for index,p in enumerate(programs):
  words=contact.encode_world(p['world'])+encode_registry(p['registry'])+[len(p['commands'])]+sum(p['commands'],[]);records.append(struct.pack('<'+'I'*len(words),*words));cases.append(dict(index=index,label=p['label'],commands=[c[0]for c in p['commands']]))
 return struct.pack('<I',len(records))+b''.join(records),cases
def aliases():return {'atelier-host/src/physics/offboard/grab_scene/collision.rs':HOST+'offboard/grab_scene/collision.rs','atelier-host/src/physics/biped_ground/grab_runtime/selection.rs':HOST+'biped_ground/grab_runtime/selection.rs'}
def prepare(output):
 simulation=PLUGIN/'Source/AtelierSkate/Private/Simulation';snapshot=output/'simulation-source'
 if snapshot.exists():shutil.rmtree(snapshot)
 snapshot.mkdir()
 for p in simulation.glob('*.h'):shutil.copy2(p,snapshot/p.name)
 for u in UNITS:shutil.copy2(simulation/f'{u}.cpp',snapshot/f'{u}.cpp')
 cpp_world=(PLUGIN/'Tests/Simulation/world_geometry_probe.cpp').read_text().split('int main()')[0];rust_world=(PLUGIN/'Tests/Reference/world_geometry_probe.rs').read_text().split('struct Query {')[0]
 bodies={name:source(HOST+path)for name,path in(('SCENE','offboard/grab_scene.rs'),('OWNER','biped_ground/grab_runtime.rs'))};probe=snapshot/'offboard_grab_probe.cpp';probe.write_text((PLUGIN/'Tests/Simulation/offboard_grab_probe.cpp').read_text().replace('// WORLD_PROTOCOL',cpp_world));text=(PLUGIN/'Tests/Reference/offboard_grab_probe.rs').read_text().replace('// WORLD_PROTOCOL',rust_world)
 for name,body in bodies.items():text=text.replace('// ORIGINAL_'+name,body)
 generated=output/'offboard-grab-reference.rs';generated.write_text(text);report=dict(simulation_source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in snapshot.iterdir()},original_host_body_sha256={n:hashlib.sha256(b.encode()).hexdigest()for n,b in bodies.items()},original_alias_sha256={d:hashlib.sha256(source(s).encode()).hexdigest()for d,s in aliases().items()},boundary='Whole unchanged host authored Registry/Scene and retained PlayerGrabSpline Owner, complete unchanged core record/registry/query/qualify/polyline/best modules. Geometry/provider/assembly data are explicit actual producer transports; all numeric records and collision/validation results are computed by original/simulation owners.')
 (output/'simulation-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return probe,snapshot,generated
def audit_input(blob,cases):
 r=Reader(blob);assert r.word()==len(cases)
 def world():r.skip(18*r.word());r.skip(1);r.skip(r.word());r.skip(36*r.word());r.skip(12*r.word());r.skip(1)
 def registry():
  for _ in range(r.word()):
   r.skip(7)
   if r.word():
    r.skip(1)
    if r.word():
     r.skip(1)
     if r.word():r.skip(9)
     r.skip(10)
   r.skip(20)
   for _ in range(r.word()):r.skip(3);r.skip(4*r.word());r.skip(4*r.word());r.skip(2)
  r.skip(2*r.word())
 for c in cases:
  world();registry();assert r.word()==len(c['commands'])
  for op in c['commands']:
   assert r.word()==op
   if op in(0,9):r.skip(35)
   elif op in(1,4,10):r.skip(2)
   elif op==2:r.skip(18)
   elif op==8:r.skip(4)
   elif op==11:r.skip(13)
   elif op==12:world()
   elif op==13:registry()
   elif op==14:r.skip(17)
   elif op==15:r.skip(29)
   elif op==16:r.skip(12)
   else:assert op in(3,5,6,7)
 assert r.at==len(r.words),(r.at,len(r.words))
def inspect(blob,cases):
 r=Reader(blob);ops=Counter();errors=Counter();counts=Counter();ready=Counter();hits=Counter()
 def status():okay=r.word();text=''.join(map(chr,r.take(r.word())));errors[text]+=not okay;return okay
 def record():words=r.take(72);r.skip(2);np=r.word();r.skip(4*np);na=r.word();r.skip(4*na);counts['record-observations']+=1;counts['geometry-points-max']=max(counts['geometry-points-max'],np);return words
 def records(label):n=r.word();counts[label]=max(counts[label],n);return [record()for _ in range(n)]
 def record_option():present=r.word();return record()if present else None
 def hit():
  if r.word():r.skip(1);hits['actual-hit-observations']+=1;asm=r.word();r.skip(asm);hits['associated-hit-observations']+=asm
  else:hits['actual-miss-observations']+=1
 def object():
  if r.word():present=r.word();r.skip(present);counts['completed-interactable-observations']+=1;counts['eligible-interactable-observations']+=present
 def owner():
  end=r.word()+r.at;queries=r.word();r.skip(35*queries);counts['pending-query-max']=max(counts['pending-query-max'],queries)
  if r.word():records('query-result-max')
  records('pending-record-max');records('validated-record-max')
  if r.word():
   n=r.word();counts['completed-validation-max']=max(counts['completed-validation-max'],n)
   for _ in range(n):hit()
  for _ in range(2):r.skip(2*r.word())
  for _ in range(2):record_option()
  bits=r.take(2);ready[tuple(bits)]+=1;r.skip(65*r.word());object();r.skip(1);flags=r.word();ready['flags-'+str(flags)]+=1;r.skip(8);assert r.at==end,(r.at,end)
 assert r.word()==len(cases)
 for c in cases:
  assert r.word()==c['index'];end=r.word()+r.at;status();status();owner();assert r.word()==len(c['commands'])
  for op in c['commands']:
   assert r.word()==op;ops[op]+=1
   if op in(3,4,9,10,11,12,13,14,15):
    okay=status()
    if okay:
     if op==9:records('direct-query-max')
     elif op==10:record_option()
     elif op==11:hit();n=r.word();r.skip(n);counts['eligible-line-observations']+=n
     elif op==15:
      if r.word():counts['qualify-'+str(r.word())]+=1
   elif op==5:
    for _ in range(2):record_option()
    object()
   elif op==8:record_option()
   elif op==16:r.skip(4)
   owner()
  assert r.at==end,(c['index'],r.at,end)
 assert r.at==len(r.words);assert all(ops[i]for i in range(17));assert counts['direct-query-max']>=5 and counts['query-result-max']and counts['validated-record-max'];assert counts['completed-validation-max']>=3 and hits['actual-hit-observations']and hits['actual-miss-observations'];assert counts['eligible-interactable-observations']and counts['qualify-0']and counts['qualify-1'];assert len([k for k,v in errors.items()if k and v])>=12
 return dict(operations=dict(ops),records_and_completions=dict(counts),readiness={str(k):v for k,v in ready.items()},hits=dict(hits),errors=dict(errors))
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--target-dir',required=True,type=Path);p.add_argument('--preflight',action='store_true');a=p.parse_args();output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
 blob,cases=corpus();audit_input(blob,cases);(output/'input.bin').write_bytes(blob);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');probe,snapshot,generated=prepare(output);summary=dict(histories=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(blob),input_sha256=hashlib.sha256(blob).hexdigest(),units=UNITS)
 if a.preflight:print(json.dumps(summary,indent=2));return
 simulation=output/'offboard-grab-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{u}.cpp')for u in UNITS],str(probe),'-o',str(simulation)],check=True);reference=build_probe(output,'offboard-grab-reference',generated,a.target_dir,extra_sources=aliases(),bevy=True)
 expected=subprocess.check_output([str(reference)],input=blob);actual=subprocess.check_output([str(simulation)],input=blob);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
 if expected!=actual:
  first=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)))//4;words=struct.unpack('<'+'I'*(len(expected)//4),expected);at=1
  for c in cases:
   end=at+2+words[at+1]
   if first<end:break
   at=end
  report=dict(first_word=first,case=c,case_first_word=at,reference_bytes=len(expected),cpp_bytes=len(actual));(output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
 coverage=inspect(expected,cases);result=dict(passed=True,**summary,exact_words=len(expected)//4,output_sha256=hashlib.sha256(expected).hexdigest(),coverage=coverage,comparison='Whole unchanged original actual authored grab registry/scene and retained query/validation/readiness/publication owner; every288-byte record plus actual spline geometry, query, line hit, readiness flag and partial write is exact.',limitations='Authored object/assembly/frame transports are explicit upstream inputs here. This leaf does not establish global live-object registration, BipedGround grab decision timing or full physical/player scheduling; those later bind this same cache and actual scene.')
 (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
