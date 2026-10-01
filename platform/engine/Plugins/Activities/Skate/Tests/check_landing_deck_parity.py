#!/usr/bin/env python3
"""Shared LandingDeck owner, actual world completions and State503 numeric leaves.

Only the root coordinator builds or executes. Canonical processed/toolkit and
animation root/COM observations are explicit upstream transport in this leaf;
every obstruction result is produced by the real original/native static scene.
The complete mounting/biped scheduling proof follows with the physical owners.
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
PLUGIN=contact.PLUGIN
HOST='crates/skate-host/src/physics/'
FAMILY=('LandingDeck','LandingDeckTrajectory','LandingDeckUpdate','LandingDeckQuery','LandingDeckRuntime','LandingOnDeckState','LandingOnDeckSettings')
UNITS=tuple(dict.fromkeys(contact.UNITS+('Settings','NameId','StockSettingsReader','RigidBody','SkeletonPoseFrames','SkeletonRoot','BoardGroundAngle','SkeletonBoardOffset','SkeletonLanding')+FAMILY))
bits,fs,Reader=contact.bits,contact.fs,contact.Reader
IDENTITY=[1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,0.]
def frame(y=0,x=0,z=0,angle=0,tilt=0):
 s,c=math.sin(angle),math.cos(angle);st,ct=math.sin(tilt),math.cos(tilt)
 return [c,0,-s,0,s*st,ct,c*st,0,s*ct,-st,c*ct,0,x,y,z,1]
def player(position=(0,1,0,.13),velocity=(0,4,1,.11),deck=None,bvel=(0,0,0,.07),up=(0,1,0,.17),height=1.2,support=-1,flags=0,mode=0,wheels=4,group=-1,hippy_flag=0,present=True):
 return [0,int(present)]+fs((deck or frame())+list(bvel)+list(up)+list(position)+list(velocity)+[height])+[support&0xffffffff,flags,mode,wheels,group&0xffffffff,hippy_flag]
def entry(category=400,hippy=False,strength=.5,up=(0,1,0,.19),right=(1,0,0,.31),reverse=False):return [1,category,int(hippy)]+fs([strength]+list(up)+list(right))+[int(reverse)]
def request(y=2,x=0,z=0,velocity=(0,-1,0,.0),radius=.3,duration=1):return fs([x,y,z,0]+list(velocity)+[0,-9.8,0,0,duration,radius,.5,.5])
def submit(**kwargs):return [13]+request(**kwargs)
def moving_world(x,platform=.6):
 w=contact.make_world([(contact.quad(-8,8,-8,8,platform,platform),0,-1,0)]);w['mesh_transform_x']=x;return w
def encode_world(w):
 words=contact.encode_world(w)
 if 'mesh_transform_x'in w:
  # Every triangle and authored bound remains local to this actual translated
  # mesh. Forward/inverse affine translations are lossless geometry inputs.
  at=1+18*len(w['triangles'])+1+1+len(w['surfaces'])+1
  for _ in w['meshes']:
   words[at+11]=bits(w['mesh_transform_x']);words[at+23]=bits(-w['mesh_transform_x']);at+=36
 return words
def corpus():
 rng=random.Random(0x82d78b28);floor=contact.quad(-8,8,-8,8,0,0);ramp=contact.quad(-8,8,-8,8,-.3,.4);wall=[[-8,0,1,-8,3,1,8,3,1],[-8,0,1,8,3,1,8,0,1]]
 worlds=[contact.make_world([(faces,0,-1,0)])for faces in(floor,ramp,wall,floor+wall)]
 worlds += [contact.make_world([(floor,2,-1,0)],island=k)for k in(0,1,3)]
 worlds += [contact.make_world([(floor,0,1,0),(ramp,1,2,0)]),contact.make_world([(floor,0,-1,0x6000)]),contact.make_world([]),contact.make_world([(floor,0,-1,0)],enabled=False),moving_world(0)]
 programs=[]
 for n in range(96):
  cmds=[]
  for k in range(7):
   x=rng.uniform(-.2,.2);z=rng.uniform(-.15,.15);vy=(5,1,0,-1,-4)[(n+k)%5];p=player((x,(1,1.4,2)[n%3],z,.13),(rng.uniform(-.1,.1),vy,(0,.8,2)[k%3],.11),frame(y=(0,.1)[n%2],angle=n*.017,tilt=(0,.06,-.06)[n%3]),support=(-1,0)[n%2],flags=(0,0x8000)[(n+k)%2],mode=(0,6,9,12)[(n+k)%4],wheels=(0,4)[k%2],group=(-1,1,2)[(n+k)%3])
   cmds += [p,entry(500 if k>0 and k%2 else 400,k%3==0,(0,.5,1)[k%3],reverse=n%2),[2,bits((.1,5,20)[k%3])],[3],[4]+fs([0,0,1,.17]+[math.sin(n*.1),0,math.cos(n*.1),.19]+[k*.06,vy,(-1,0,1)[k%3]]),[5],[7,bits(vy)],[8]+fs([x,.9,z,.13]),[9]+fs(frame(1,.03,.02,n*.01,.1)+[0,.55,0,.17]+[0,.2,.1,.13]+[(0,.1,.6)[k%3]]),[10],[17]]
   if k in(2,4):cmds += [[12]+encode_world(worlds[(n+k)%len(worlds)]),[3],[11],[10],[17]]
  cmds += [[11],[10],[5],[17]];programs.append(dict(label='shared real assistance/update/ordered completion/alignment/IK/reset histories',world=worlds[n%len(worlds)],commands=cmds))
 # True moving mesh result+112, not a supplied completed contact. The same
 # manager survives 501/503-style transitions and every query is executed.
 for n in range(12):
  cmds=[player((0,1,0,0),(0,1,0,0),height=1.5,hippy_flag=0x04000000),entry(400,False)]
  for k in range(5):cmds += [[12]+encode_world(moving_world(.03*k)),submit(),[10],[17]]
  cmds += [player(present=False,hippy_flag=0x04000000),[12]+encode_world(moving_world(.3)),submit(),[10],[17],player(hippy_flag=0x04000000),[10],[11],[17]]
  programs.append(dict(label='actual moving mesh completion histories and publication retention',world=moving_world(0),commands=cmds))
 for n in range(4):
  cmds=[player((0,1,0,0),(0,1,0,0),height=1.5,hippy_flag=0x04000000),entry(400,False),submit(),[10],[17],player(present=False,hippy_flag=0x04000000),[12]+encode_world(moving_world(.03)),submit(),[10],[17],player(hippy_flag=0x04000000),[10],[17],[11]]
  programs.append(dict(label='real second moving completion invokes mandatory toolkit provider, fails, retries unchanged',world=moving_world(0),commands=cmds))
 for n in range(32):
  vy=(-50,5,1)[n%3];angle=n*.23;cmds=[player(velocity=(0,vy,.7,.0)),entry(400,n%2==0),[2,bits(20)]]
  for k in range(24):
   cmds += [[3],[4]+fs([math.sin(angle),0,math.cos(angle),.17]+[0,0,1,.19]+[k*.016,vy,(-1,0,1)[(k+n)%3]]),[5],[7,bits(vy)],[10],[17]]
   if k==11:cmds += [entry(500,False),[8]+fs([0,1,0,.13])]
  programs.append(dict(label='retained State503 automatic/input alignment, spin accumulation and dangerous landing histories',world=worlds[0],commands=cmds))
 for category in(400,500):
  for hippy in(False,True):
   cmds=[player(),entry(400),[2,bits(20)],[3],entry(category,hippy),[3],[5],[10],[17]]
   programs.append(dict(label='shared manager preserve category and forced hippy source entry',world=worlds[0],commands=cmds))
 for failed in('toolkit','zero-duration','negative-radius','nan-radius','nan-error','nan-W-velocity','empty-scene-metadata'):
  cmds=[player(),entry(),submit(),[17]];q=request()
  if failed=='toolkit':cmds += [player(present=False),[2,bits(10)],[3],[9]+fs(IDENTITY+[0,.5,0,0]+[0,0,0,0]+[.1])]
  elif failed=='empty-scene-metadata':cmds += [[12]+encode_world(worlds[-2]),[3]]
  else:
   if failed=='zero-duration':q[12]=bits(0)
   elif failed=='negative-radius':q[13]=bits(-.1)
   elif failed=='nan-radius':q[13]=0x7fc12345
   elif failed=='nan-error':q[14]=0x7fc12345
   else:q[7]=0x7fc12345
   cmds += [[13]+q]
  cmds += [[10],[17],player(),[3],[5],[10],[17]];programs.append(dict(label='actual query/mandatory producer rejection with retained completion/'+failed,world=worlds[0],commands=cmds))
 for n in range(24):
  cmds=[player(),entry(400,n%2==0)]
  for k in range(12):
   cmds += [[6]+fs([(-.1,0,.1,.5)[k%4],(-2,0,2)[k%3],(-5,-.1,0,5)[(n+k)%4],(0,.1,1)[k%3],(0,.1,1)[(k+1)%3]])+[k%2],
            [14]+fs(frame(y=.2,angle=n*.1,tilt=k*.01)+[.1,1,.2,.31])+[k%2]+fs([(-1,.3,3)[k%3]]),
            [15]+fs([.1,1,.2,.19]+[0,.5,.1,.17]+[(k-6)*.07])+[k%2]+([1+k]if k%2 else[])+[n%2],
            [16]+fs(IDENTITY+frame(y=.4,angle=.3)+frame(y=.2,angle=.1)+[.1,.2,.3,.17]+[(-2,0,2)[k%3]])+[k%4]+fs([k*.07]+[i*.1 for i in range(8)]+[1-i*.1 for i in range(8)])]
  programs.append(dict(label='physical-toe time/root COM/upright degeneracy/spin/revert/pose gates',world=worlds[0],commands=cmds))
 records=[];cases=[]
 for index,p in enumerate(programs):
  words=encode_world(p['world'])+[len(p['commands'])]+sum(p['commands'],[]);records.append(struct.pack('<'+'I'*len(words),*words));cases.append(dict(index=index,label=p['label'],commands=[c[0]for c in p['commands']]))
 return struct.pack('<I',len(records))+b''.join(records),cases
def aliases():
 out={'atelier-host/src/physics/offboard/contact_toolkit.rs':HOST+'offboard/contact_toolkit.rs','atelier-host/src/physics/offboard/contact_toolkit/world.rs':HOST+'offboard/contact_toolkit/world.rs'}
 for name in('input','query','output'):out[f'atelier-host/src/physics/offboard/landing_deck/{name}.rs']=HOST+f'offboard/landing_deck/{name}.rs'
 return out
def prepare(output):
 native=PLUGIN/'Source/AtelierSkate/Private/Native';snapshot=output/'native-source'
 if snapshot.exists():shutil.rmtree(snapshot)
 snapshot.mkdir()
 for p in native.glob('*.h'):shutil.copy2(p,snapshot/p.name)
 for u in UNITS:shutil.copy2(native/f'{u}.cpp',snapshot/f'{u}.cpp')
 cpp_world=(PLUGIN/'Tests/Native/world_geometry_probe.cpp').read_text().split('int main()')[0];rust_world=(PLUGIN/'Tests/Reference/world_geometry_probe.rs').read_text().split('struct Query {')[0]
 host=source(HOST+'offboard/landing_deck.rs');mount=source(HOST+'landing_on_deck.rs');begin=mount.index('pub(crate) struct Runtime {');end=mount.index('\nfn clear_ik(',begin);configuration=mount[begin:end]
 assert configuration.endswith('\n}')and configuration in mount
 probe=snapshot/'landing_deck_probe.cpp';probe.write_text((PLUGIN/'Tests/Native/landing_deck_probe.cpp').read_text().replace('// WORLD_PROTOCOL',cpp_world))
 generated=output/'landing-deck-reference.rs';generated.write_text((PLUGIN/'Tests/Reference/landing_deck_probe.rs').read_text().replace('// WORLD_PROTOCOL',rust_world).replace('// ORIGINAL_MANAGER_HOST',host).replace('// ORIGINAL_MOUNTING_CONFIGURATION',configuration))
 report=dict(native_source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in snapshot.iterdir()},original_host_body_sha256=hashlib.sha256(host.encode()).hexdigest(),mounting_whole_source_sha256=hashlib.sha256(mount.encode()).hexdigest(),mounting_configuration_exact_slice_sha256=hashlib.sha256(configuration.encode()).hexdigest(),mounting_configuration_bytes=[len(mount[:begin].encode()),len(mount[:end].encode())],original_alias_sha256={d:hashlib.sha256(source(s).encode()).hexdigest()for d,s in aliases().items()},boundary='Whole original LandingDeck host plus unchanged public core manager/state/root functions. Processed fields/toolkit/animation root/COM are explicit upstream producer transports; no scene result is provided by transport. Mounting loader is an exact contiguous original full Runtime+Load declaration, with whole-source and slice hashes.')
 (output/'native-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return probe,snapshot,generated
def audit_input(blob,cases):
 r=Reader(blob);assert r.word()==len(cases)
 def world():r.skip(18*r.word());r.skip(1);r.skip(r.word());r.skip(36*r.word());r.skip(12*r.word());r.skip(1)
 for c in cases:
  world();assert r.word()==len(c['commands'])
  for op in c['commands']:
   assert r.word()==op
   if op==0:r.skip(40)
   elif op==1:r.skip(12)
   elif op in(2,7):r.skip(1)
   elif op==4:r.skip(11)
   elif op==6:r.skip(6)
   elif op==8:r.skip(4)
   elif op==9:r.skip(25)
   elif op==12:world()
   elif op==13:r.skip(16)
   elif op==14:r.skip(22)
   elif op==15:r.skip(9);present=r.word();r.skip(present+1)
   elif op==16:r.skip(71)
   else:assert op in(3,5,10,11,17)
 assert r.at==len(r.words),(r.at,len(r.words))
FIELDS=[('physics_landingondeck',n)for n in('DeckMinUprightness','ApproxCOMHeightOnLanding','MinAngleToAutoTurn','BodySpinSpeedAuto','BodySpinSpeed','BodySpinDeltaInput','BodySpinDeltaAuto')]+[('physics_wipeout','MaxSpeedLandingOnBoard')]+[('physics_skeleton',n)for n in('SkateRootYOffset','SkateRootCapsuleRadius','SkateRootCapsuleLength')]
def loader_fixtures(assets):
 data=json.loads((assets/'private/stock/skater-collections.json').read_text());fixtures=[]
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
 for c,n in FIELDS:
  for failure in('missing','wrong-type','empty','two-words','nan','infinite','negative-valid'):
   d=copy.deepcopy(data)
   if failure=='missing':missing(d,c,n)
   else:
    f=edit(d,c,n)
    if failure=='wrong-type':f['type']='EA::Reflection::Int32'
    else:f['data']={'empty':'','two-words':f['data']+'00000000','nan':'7FC12345','infinite':'7F800000','negative-valid':'BF800000'}[failure]
   fixtures.append(dict(label=c+'/'+n+'/'+failure,data=d,success=failure=='negative-valid'))
 for i,(c,n)in enumerate(FIELDS):
  d=copy.deepcopy(data);missing(d,c,n)
  for later_c,later_n in FIELDS[i+1:]:edit(d,later_c,later_n)['type']='EA::Reflection::Text'
  fixtures.append(dict(label='ordered compound read'+str(i)+'/'+c+'/'+n,data=d,success=False))
 for c in dict.fromkeys(c for c,n in FIELDS):
  d=copy.deepcopy(data);d['collections']=[r for r in d['collections']if converter.name_id(r['class'])!=converter.name_id(c)];fixtures.append(dict(label='missing collection/'+c,data=d,success=False))
 return fixtures
def inspect(blob,cases):
 r=Reader(blob);ops=Counter();errors=Counter();qcount=Counter();states=Counter();publication=Counter()
 def status():okay=r.word();text=''.join(map(chr,r.take(r.word())));errors[text]+=not okay;return okay
 def query():q=r.take(32);qcount['hit'if struct.unpack('<f',struct.pack('<I',q[12]))[0]>=0 else'miss']+=1
 def output():r.skip(38);present=r.word();r.skip(16*present);qcount['numeric-requests']+=present
 def owner():
  end=r.word()+r.at;manager=r.take(55);states['hippy-observations']+=manager[52];states['pending-observations']+=manager[54];qcount['completed-count-max']=max(qcount['completed-count-max'],manager[47])
  if r.word():query()
  r.skip(2)
  if r.word():r.skip(4);publication['source-write-enabled']+=1
  if r.word():output()
  state=r.take(14);states['turning-observations']+=state[3];states['hippy-entry-observations']+=state[4];r.skip(40);pred=r.word();r.skip(4*pred+65);pub=r.take(7);publication['persistent-contact-flag']+=pub[-1]==1;assert r.at==end,(r.at,end)
 assert status();r.skip(11);assert r.word()==len(cases)
 for c in cases:
  assert r.word()==c['index'];end=r.word()+r.at;status();owner();assert r.word()==len(c['commands'])
  for op in c['commands']:
   assert r.word()==op;ops[op]+=1
   if op in(2,3,5,9,10,12,13):
    okay=status()
    if okay and op==3:output()
    if okay and op==9:r.skip(4)
   elif op==6:r.skip(1)
   elif op==14:r.skip(16)
   elif op==16:
    if r.word():r.skip(16);states['pose-adjustment-writes']+=1
    else:states['pose-adjustment-retained']+=1
   owner()
  assert r.at==end,(c['index'],r.at,end)
 assert r.at==len(r.words);assert all(ops[i]for i in range(18));assert qcount['hit']and qcount['miss']and qcount['completed-count-max']>=3;assert states['hippy-observations']and publication['source-write-enabled'];assert len([k for k,v in errors.items()if k and v])>=4
 return dict(operations=dict(ops),query_results=dict(qcount),state_observations=dict(states),publication=dict(publication),errors=dict(errors))
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--target-dir',required=True,type=Path);p.add_argument('--preflight',action='store_true');a=p.parse_args();output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
 blob,cases=corpus();audit_input(blob,cases);(output/'input.bin').write_bytes(blob);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');probe,snapshot,generated=prepare(output);assets=a.assets.resolve();fixtures=loader_fixtures(assets);bank=output/'settings.native';bank.write_bytes(converter.encode_settings(assets/'private/stock/skater-collections.json'));summary=dict(histories=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(blob),input_sha256=hashlib.sha256(blob).hexdigest(),loader_fixture_count=len(fixtures),units=UNITS)
 if a.preflight:print(json.dumps(summary,indent=2));return
 native=output/'landing-deck-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{u}.cpp')for u in UNITS],str(probe),'-o',str(native)],check=True);reference=build_probe(output,'landing-deck-reference',generated,a.target_dir,extra_sources=aliases(),bevy=True)
 expected=subprocess.check_output([str(reference),str(assets)],input=blob);actual=subprocess.check_output([str(native),str(bank)],input=blob);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
 if expected!=actual:
  first=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)))//4;words=struct.unpack('<'+'I'*(len(expected)//4),expected);at=2+words[1]+11+1
  for c in cases:
   end=at+2+words[at+1]
   if first<end:break
   at=end
  report=dict(first_word=first,case=c,case_first_word=at,reference_bytes=len(expected),cpp_bytes=len(actual));(output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
 coverage=inspect(expected,cases);reports=[];fixture_root=output/'loader-fixtures';fixture_root.mkdir(exist_ok=True)
 for i,f in enumerate(fixtures):
  dest=fixture_root/str(i)/'private/stock';dest.mkdir(parents=True,exist_ok=True);src=dest/'skater-collections.json';src.write_text(json.dumps(f['data']));encoded=fixture_root/str(i)/'settings.native';encoded.write_bytes(converter.encode_settings(src));ref=subprocess.check_output([str(reference),str(assets),str(fixture_root/str(i))]);cpp=subprocess.check_output([str(native),str(bank),str(encoded)])
  assert ref==cpp,(i,f['label'],ref,cpp);rd=Reader(ref);assert rd.word();rd.skip(rd.word()+11);okay=bool(rd.word());assert okay==f['success'],(i,f['label'],okay);reports.append(dict(index=i,label=f['label'],success=okay,output_sha256=hashlib.sha256(ref).hexdigest()))
 result=dict(passed=True,**summary,exact_words=len(expected)//4,output_sha256=hashlib.sha256(expected).hexdigest(),coverage=coverage,loader_fixtures=reports,comparison='Whole unchanged original LandingDeck host and actual static world queries, all manager/completion/publication/state/root observations exact; full original mounting loader body and unchanged core numerical leaves.',limitations='This leaf observes explicit completed upstream player/toolkit and animation root/COM transport. Full Biped/mounting ownership/skeleton general update/reckoning/feet/possession/Wipeout scheduling is not established by this leaf; those use the same manager in the following connected composition.')
 (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
