#!/usr/bin/env python3
"""Original active BipedGround entry/input/job/sync over actual deferred geometry.

Only root may build/run. Controllers and input packets are explicit consumed
producer inputs; geometry submission/retention and every state mutation are real.
This does not establish the later full Biped phase schedule or physical solving.
"""
import argparse
from collections import OrderedDict,Counter
import copy,hashlib,json,math,re,shutil,struct,subprocess
from pathlib import Path
import player_input_protocol as wire
from check_animation_playback_parity import Stream
from check_skeleton_input_runtime_parity import source
import check_offboard_controller_parity as controller
import check_offboard_ground_geometry_parity as geometry
from check_offboard_contact_parity import PLUGIN,make_world,encode_world,quad
CORE='crates/skate-core/src/player/offboard/'
HOST='crates/skate-host/src/physics/'
CODE=PLUGIN/'Source/AtelierSkate/Private/Simulation'
UNITS=tuple(dict.fromkeys(controller.UNITS+geometry.UNITS+('BipedGroundState','BipedGroundInput','BipedGroundJob')))
TYPES=OrderedDict([
 ('BipedContactPrefix',('contact_toolkit/prefix.rs','ContactPrefix','contact_toolkit::ContactPrefix')),
 ('BipedGroundState',('ground_entry.rs','State','ground_entry::State')),
 ('BipedGroundEntryInput',('ground_entry.rs','Input','ground_entry::Input')),
 ('BipedGroundPlacement',('ground_entry.rs','Placement','ground_entry::Placement')),
 ('BipedGroundControlInput',('ground_input.rs','GroundInput','ground_input::GroundInput')),
 ('BipedGroundControlOutput',('ground_input.rs','GroundInputOutput','ground_input::GroundInputOutput')),
 ('BipedGroundContactSnapshot',('ground_job.rs','ContactSnapshot','ground_job::ContactSnapshot')),
 ('BipedGroundPrepareInput',('ground_job.rs','Input','ground_job::Input')),
 ('BipedGroundJob',('controller.rs','GroundJob','controller::GroundJob')),
 ('BipedGroundResult',('controller/output.rs','GroundResult','controller::GroundResult')),
])
def definitions():
 d=OrderedDict();aliases={'ContactPrefix':'BipedContactPrefix','ContactSnapshot':'BipedGroundContactSnapshot','GroundInputOutput':'BipedGroundControlOutput'}
 for name,(path,typename,_)in TYPES.items():
  text=source(CORE+path);start=re.search(r'pub struct '+typename+r'\s*\{',text);assert start,name
  body=text[start.end():text.index('\n}',start.end())];fields=re.findall(r'^\s*pub (\w+): ([^,\n]+),',body,re.M);assert fields,name
  d[name]=[]
  for f,k in fields:
   k=re.sub(r'\s+','',k);k=re.sub(r'\bVector\b','[f32;4]',k);k=re.sub(r'\bFrame\b','[[f32;4];4]',k);k=aliases.get(k,k);d[name].append((f,k))
 return d

def helpers(d):
 cpp=[];rust=[]
 for n in d:cpp += [f'void Observe(Output&,const {n}&);',f'{n} Read{n}(Input&);'];rust.append(f'type {n}={TYPES[n][2]};')
 for n,fields in d.items():
  cpp.append(f'void Observe(Output& o,const {n}& s){{'+''.join(wire.observe_expr(k,'s.'+f,'cpp')for f,k in fields)+'}')
  rust.append(f'fn observe_{n}(o:&mut Output,s:&{n}){{'+''.join(wire.observe_expr(k,'s.'+f,'rust')for f,k in fields)+'}')
  cpp.append(f'{n} Read{n}(Input& i){{{n} s;'+''.join('s.'+f+'='+wire.read_expr(k,'cpp')+';'for f,k in fields)+'return s;}')
  rust.append(f'fn read_{n}(i:&mut Input)->{n}{{{n}{{'+''.join(f+':'+wire.read_expr(k,'rust')+','for f,k in fields)+'}}')
 return '\n'.join(cpp),'\n'.join(rust)
def frame(a=0,h=0,w=0):return [[math.cos(a),0,-math.sin(a),0],[0,1,0,0],[math.sin(a),0,math.cos(a),0],[.137,h,.317,w]]
def zero(k,d):
 a=wire.array(k);o=wire.option(k)
 if a:return [zero(a[0],d)for _ in range(a[1])]
 if o:return None
 if k in('f32','u32','i32','bool'):return 0
 return {f:zero(t,d)for f,t in d[k]}
def prefix(n,k,d):
 v=zero('BipedContactPrefix',d);v.update(position=[.137,(-.3,0,.2,.7)[k%4],.317,-.0],normal=[0,(1,.7)[n%2],(0,.7)[n%2],(-.0,.317)[k%2]],support_frame=frame(k*.013,.017),target_position=[.137,.03,.731,.137],target_normal=[0,1,0,-.0],edge_position=[.137,.02,.517,.731],edge_normal=[.137,.917,0,-.0],scalar_160=.317,kind_164=n%4,distance_168=.1,distance_172=(.001,.7,2,4)[k%4],flags_176=(0,1,8,9,0x11,0x21,0x31)[(n+k)%7],support_180=0x71230000+n);return v

def corpus(d):
 floor=quad(-5,5,-5,5,0,0);ramp=quad(-5,5,-2,2,.7,-.3);edge=[([-1,0,0],[1,0,0])]
 worlds=[make_world([(floor,0,-1,0)],edge),make_world([(ramp,0,-1,0)],edge),make_world([],edge),make_world([]),make_world([(floor,0,-1,0)],edge,enabled=False)]
 curve=[0,.05,.12,.25,.4,.65,.8,1]+[1,.97,.91,.8,.71,.57,.35,.1];turn=[0,.05,.12,.25,.4,.65,.8,1]+[0,.11,.21,.35,.57,.8,.97,1]
 programs=[]
 for n in range(112):
  commands=[];world=worlds[n%len(worlds)]
  entry=zero('BipedGroundEntryInput',d);entry.update(animation_frame=frame(n*.037,.01,-.0),processed_velocity_608=[.137,(-3,0,3)[n%3],(.001,.07,.1,2)[n%4],.317],processed_flags_2484=0x4000 if n%3 else 0,processed_flags_2476=4 if n%2 else 0,requested_angle_2936=(-3.4,-1.571,-.1,0,.1,1.571,3.4)[n%7],requested_duration_2896=(.001,.05,.3,1.7)[n%4],previous_state_2504=(500,501,502)[n%3],previous_frame_up_208=[0,(.71,.709,.731)[n%3],.317,-.0],body_position_15872=[.137,1.7,.317,-.0]);commands.append((0,entry))
  for k in range(48):
   control=zero('BipedGroundControlInput',d);control.update(processed_flags_2472=0x10000000 if k%6==0 else 0,processed_direct_2684=(-.7,0,.9)[k%3],processed_direct_2680=(-.9,0,.7)[n%3],processed_stick_2692=(-1,-.01,-.0,0,.01,1)[k%6],processed_stick_2688=(-1,-.0,0,.3,1)[(n+k)%5],processed_scale_2912=(0,.3,1,2)[n%4],processed_scale_2908=(0,.7,1,2)[k%4],frame_forward_112=([0,0,1],[.3,.8,.5],[0,1,0],[.1,-1,.1])[k%4]);commands.append((1,control,curve,turn))
   if k%3==0:commands.append((4,frame(k*.037,(0,.01,-.01,.19)[k%4],.137),[0,0,(0,.9,1,1.01,3)[(n+k)%5],.517],n%4,-1,(0,0x08000000)[k%2]))
   p=zero('BipedGroundPrepareInput',d);p.update(contact=dict(readiness=(-1,0,1,2)[(n+k)%4],prefix=prefix(n,k,d)),frame=frame(k*.017,.01,-.0),previous_state=(500,501,502)[(n+k)%3],third_line_position=None if k%3 else [.137,-.01,.317,.731],frames_since_teleport=(0,19,20,21,0x7fffffff,0x80000000,0xffffffff)[(n+k)%7],processed_position=[.137,.03,.317,-.0],processed_velocity=[.137,(-1,0,1)[k%3],.731,.317],controls=dict(state_708=(0,.7,1)[k%3],state_712=(-1,0,1)[n%3],state_656=[.137,0,.731,-.0]),collision_displacements=[[.001,0,.03,.137],[-.001,0,-.03,-.137]],animation_motion=[.001,0,.137,-.0],animation_velocity=[.137,0,.731,.317],requested_duration=.317,requested_phase=(0,.5,1)[k%3],override_duration=(0,.3)[k%2],flags_2472=0x10000000 if k%3 else 0,flags_2476=4 if n%2 else 0,flags_2480=0x80 if n%3 else 0,flags_2484=0x20000 if k%3 else 0,flags_2488=0x08000000 if k%2 else 0);commands.append((2,p))
   result=zero('BipedGroundResult',d);result.update(physical_frame=frame(k*.01,-.13,-.0),animation_frame=frame(k*.013,.03,-.0),sliding=bool(k%2));commands.append((3,result))
   if k in(11,31):commands.append((7,worlds[(n+k)%len(worlds)]))
   if k in(17,38):commands.append((6,))
   if k%11==0:commands.append((8,frame(k*.073,.137,-.0),4 if k%2 else 0))
  programs.append((world,.317,commands,'actual entry, input, deferred query, ready/fallback prefix and directed sync retention'))
 # Explicit retained states ensure counters and unused bytes remain unchanged.
 for n in range(8):
  state=zero('BipedGroundState',d);state.update(frame_80=frame(.137,.317,-.0),flags_144_to_150=[True,False,True,False,True,False,True],counter_152=0xffffffff,counter_156=0x80000000,elapsed_160=.137,distance_164=.731,elapsed_168=-.317,angle_172=(-.0,.137)[n%2],angular_velocity_176=(-3,.0,3)[n%3],duration_180=(.001,.05,.17,.731)[n%4]);p=prefix(n,n,d);commands=[(5,state,p)]
  for k in range(80):
   r=zero('BipedGroundResult',d);r.update(physical_frame=frame(.017*k,-.137,-.0),animation_frame=frame(.023*k,.137,-.0),sliding=bool(k%2));commands.append((3,r))
  programs.append((worlds[0],.137,commands,'persistent directed-angle expiry, decay and inactive fields'))
 stream=Stream();stream.word(len(programs));cases=[]
 for index,(world,offset,commands,label)in enumerate(programs):
  for w in encode_world(world):stream.word(w)
  stream.float(offset);stream.word(len(commands))
  for c in commands:
   op=c[0];stream.word(op)
   if op in(0,1,2,3):wire.encode(stream,('BipedGroundEntryInput','BipedGroundControlInput','BipedGroundPrepareInput','BipedGroundResult')[op],c[1],d)
   if op==1:
    for x in c[2]+c[3]:stream.float(x)
   elif op==4:
    wire.encode(stream,'[[f32;4];4]',c[1],d);wire.encode(stream,'[f32;4]',c[2],d);stream.word(c[3]);stream.word(c[4]);stream.word(c[5])
   elif op==5:wire.encode(stream,'BipedGroundState',c[1],d);wire.encode(stream,'BipedContactPrefix',c[2],d)
   elif op==7:
    for w in encode_world(c[1]):stream.word(w)
   elif op==8:wire.encode(stream,'[[f32;4];4]',c[1],d);stream.word(c[2])
  cases.append(dict(index=index,label=label,commands=[c[0]for c in commands]))
 return bytes(stream.data),cases

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def aliases():return geometry.aliases()
def prepare(out,d):
 snapshot=out/'simulation-source'
 if snapshot.exists():shutil.rmtree(snapshot)
 snapshot.mkdir()
 for p in CODE.glob('*.h'):shutil.copy2(p,snapshot/p.name)
 for n in UNITS:shutil.copy2(CODE/(n+'.cpp'),snapshot/(n+'.cpp'))
 cpp_world=(PLUGIN/'Tests/Simulation/world_geometry_probe.cpp').read_text().split('int main()')[0];rust_world=(PLUGIN/'Tests/Reference/world_geometry_probe.rs').read_text().split('struct Query {')[0]
 cpp_geometry=(PLUGIN/'Tests/Simulation/offboard_ground_geometry_probe.cpp').read_text().split('// WORLD_PROTOCOL')[1].split('struct Registry')[0]+'\n}\n'
 rust_geometry=(PLUGIN/'Tests/Reference/offboard_ground_geometry_probe.rs').read_text().split('// WORLD_PROTOCOL')[1].split('struct BodyData')[0].replace('// ORIGINAL_STATE',source(HOST+'offboard/ground_geometry.rs')+'\npub fn migration_new(offset:f32)->State{State{pending:None,collision_offset:offset}}\n')
 cpp,rust=helpers(d);simulation=snapshot/'biped_ground_state_probe.cpp';simulation.write_text((PLUGIN/'Tests/Simulation/biped_ground_state_probe.cpp').read_text().replace('// WORLD_PROTOCOL',cpp_world).replace('// GEOMETRY_PROTOCOL',cpp_geometry).replace('// GENERATED_PROTOCOL',cpp))
 bridge=source(HOST+'biped_ground/entry.rs')+'\npub fn migration_effective(frame:Frame,flags:u32)->Frame{effective_root(frame,flags)}\n'
 reference=out/'biped-ground-state-reference.rs';reference.write_text((PLUGIN/'Tests/Reference/biped_ground_state_probe.rs').read_text().replace('// WORLD_PROTOCOL',rust_world).replace('// GEOMETRY_PROTOCOL',rust_geometry).replace('// GENERATED_PROTOCOL',rust).replace('mod ground_entry_bridge;','mod ground_entry_bridge{\n'+bridge+'\n}'))
 sources={CORE+p for p,_,_ in TYPES.values()}|{CORE+'ground_input/math.rs',CORE+'ground_entry/math.rs',HOST+'biped_ground/entry.rs',HOST+'offboard/ground_geometry.rs',*aliases().values()}
 report=dict(simulation_source_sha256={p.name:digest(p)for p in snapshot.iterdir()},original_sources={p:hashlib.sha256(source(p).encode()).hexdigest()for p in sorted(sources)},protocol=d,boundary='Full actual original entry/input/job/sync and retained geometry; consumed controller result, input and source engine-authored world are explicit boundaries. No fabricated queries.')
 (out/'simulation-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return simulation,snapshot,reference

def audit(raw,cases,d):
 r=wire.Reader(raw);assert r.word()==len(cases)
 def world():
  r.value(f'[u32;{18*r.word()}]',d);r.word();r.value(f'[u32;{r.word()}]',d);r.value(f'[u32;{36*r.word()}]',d);r.value(f'[u32;{12*r.word()}]',d);r.word()
 for c in cases:
  world();r.word();assert r.word()==len(c['commands'])
  for op in c['commands']:
   assert r.word()==op
   if op in(0,1,2,3):r.value(('BipedGroundEntryInput','BipedGroundControlInput','BipedGroundPrepareInput','BipedGroundResult')[op],d)
   if op==1:r.value('[u32;32]',d)
   elif op==4:r.value('[u32;23]',d)
   elif op==5:r.value('BipedGroundState',d);r.value('BipedContactPrefix',d)
   elif op==7:world()
   elif op==8:r.value('[u32;17]',d)
 assert r.at==len(raw),(r.at,len(raw))
def inspect(raw,cases,d):
 r=wire.Reader(raw);ops=Counter();pending=Counter();flags=Counter();adjustments=Counter();timers=set();directed=Counter();assert r.word()==len(cases)
 def status():okay=r.word();text=''.join(chr(r.word())for _ in range(r.word()));return okay,text
 def adjustment():a=r.value('[u32;18]',d);adjustments[tuple(a[:3])]+=1
 def snapshot():
  size=r.word();end=r.at+size*4;state=r.value('BipedGroundState',d);p=r.value('BipedContactPrefix',d);flags[p['flags_176']]+=1;timers.add(state['distance_164']);directed[state['flags_144_to_150'][6]]+=1;r.word();some=r.word();pending[some]+=1
  if some:
   r.value('[u32;60]',d)
   for _ in range(7):
    if r.word():r.value('[u32;8]',d)
  assert r.at==end,(r.at,end,size)
 for c in cases:
  assert(r.word(),r.word())==(c['index'],len(c['commands']));snapshot()
  for op in c['commands']:
   assert r.word()==op;ops[op]+=1
   if op==0:r.value('BipedGroundPlacement',d)
   elif op==1:r.value('BipedGroundControlOutput',d)
   elif op==2:r.value('BipedGroundJob',d);adjustment()
   elif op in(3,8):r.value('[u32;16]',d)
   elif op in(4,7):status()
   snapshot()
 assert r.at==len(raw);assert all(ops[n]for n in range(9));assert pending[0]and pending[1]and directed[0]and directed[1];assert len(flags)>4 and len(adjustments)>2 and len(timers)>40
 return dict(operations=dict(ops),pending=dict(pending),contact_flags=dict(flags),directed_state=dict(directed),adjustments={str(k):v for k,v in adjustments.items()},timer_states=len(timers))
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--target-dir',required=True,type=Path);p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);d=definitions();blob,cases=corpus(d);audit(blob,cases,d);(out/'input.bin').write_bytes(blob);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');probe,snapshot,generated=prepare(out,d);summary=dict(histories=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(blob),input_sha256=hashlib.sha256(blob).hexdigest(),units=UNITS)
 if a.preflight:print(json.dumps(summary,indent=2));return
 simulation=out/'biped-ground-state-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(probe),'-o',str(simulation)],check=True);reference=build_probe(out,'biped-ground-state-reference',generated,a.target_dir,extra_sources=aliases());expected=subprocess.check_output([str(reference)],input=blob);actual=subprocess.check_output([str(simulation)],input=blob);(out/'reference.bin').write_bytes(expected);(out/'cpp.bin').write_bytes(actual)
 if expected!=actual:
  first=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)))//4;report=dict(first_word=first,reference_bytes=len(expected),cpp_bytes=len(actual));(out/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
 result=dict(passed=True,**summary,exact_words=len(expected)//4,output_sha256=hashlib.sha256(expected).hexdigest(),coverage=inspect(expected,cases,d),limitations=__doc__);(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
