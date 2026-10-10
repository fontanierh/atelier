#!/usr/bin/env python3
"""Complete original Biped ground-controller leaf and actual stock loader.

Ground jobs and placement are explicit producer inputs in this focused proof.
The connected offboard world/query/feet/physical owners have a separate proof.
Only the root render guard compiles or executes; --preflight is source-only.
"""
import argparse
from collections import OrderedDict,Counter
import copy
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import random
import re
import shutil
import struct
import subprocess
import check_skeleton_input_runtime_parity as original
import player_input_protocol as wire
from check_animation_playback_parity import Stream
from check_gesture_parity import PLUGIN,converter
from reference_build import build_probe
CORE='crates/skate-core/src/player/offboard/'
HOST='crates/skate-host/src/physics/offboard/'
CODE=PLUGIN/'Source/AtelierSkate/Private/Simulation'
UNITS=('SimulationMath','RigidBody','BoardGroundAngle','SkeletonPoseFrames','SkeletonRoot','NameId','Settings','StockSettingsReader','AnimationMetadata','OffboardSettings','OffboardMovementIntent','OffboardMovementVelocity','OffboardSurface','OffboardCadence','OffboardGroundMotion','OffboardController')
STRUCTS=OrderedDict([
 ('BipedIntentState',('movement_intent.rs','State','movement_intent::State')),
 ('BipedSurfaceState',('surface_frame.rs','State','surface_frame::State')),
 ('BipedContactCorrection',('contact_correction.rs','ContactCorrection','contact_correction::ContactCorrection')),
 ('BipedSpecialMode',('slide.rs','SpecialMode','slide::SpecialMode')),
 ('BipedSliding',('slide.rs','Sliding','slide::Sliding')),
 ('BipedGroundMotionState',('ground_motion.rs','GroundMotionState','ground_motion::GroundMotionState')),
 ('BipedFrameOutput',('position_output.rs','FrameOutput','position_output::FrameOutput')),
 ('BipedPhase',('cadence.rs','BipedPhase','cadence::BipedPhase')),
 ('BipedCadence',('cadence.rs','BipedCadence','cadence::BipedCadence')),
 ('BipedControllerState',('controller/state.rs','State','controller::State')),
 ('BipedGroundResult',('controller/output.rs','GroundResult','output_bridge::original::GroundResult')),
 ('BipedPlacementInput',('controller/placement.rs','PlacementInput','controller::PlacementInput')),
 ('BipedGroundJob',('controller.rs','GroundJob','controller::GroundJob')),
])
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def schema():
 result=OrderedDict()
 aliases={'Vector':'[f32;4]','Frame':'[[f32;4];4]','Matrix':'[[f32;4];4]','movement_intent::State':'BipedIntentState','surface_frame::State':'BipedSurfaceState','ContactCorrection':'BipedContactCorrection','SpecialMode':'BipedSpecialMode','Sliding':'BipedSliding','GroundMotionState':'BipedGroundMotionState','FrameOutput':'BipedFrameOutput','BipedCadence':'BipedCadence','CadenceThresholds':'[f32;4]'}
 for name,(path,type_name,_)in STRUCTS.items():
  source=original.source(CORE+path);match=re.search(r'pub struct '+type_name+r'\s*\{',source);assert match,name
  body=source[match.end():source.index('\n}',match.end())];fields=re.findall(r'^\s*pub (\w+): ([^,\n]+),',body,re.M)
  normalized=[]
  for field,kind in fields:
   kind=re.sub(r'\s+','',kind);kind=aliases.get(kind,kind);kind=re.sub(r'\bVector\b','[f32;4]',kind);kind=re.sub(r'\bFrame\b','[[f32;4];4]',kind);normalized.append((field,kind))
  result[name]=normalized;assert fields,name
 return result
def helpers(defs):
 cpp=[];rust=[]
 for name,fields in defs.items():
  rust.append('type '+name+'='+STRUCTS[name][2]+';')
  cpp.append(f'void Observe(Output& o,const {name}& s){{'+''.join(wire.observe_expr(k,'s.'+f,'cpp')for f,k in fields)+'}')
  rust.append(f'fn observe_{name}(o:&mut Output,s:&{name}){{'+''.join(wire.observe_expr(k,'s.'+f+('.0'if name=='BipedControllerState'and f=='thresholds'else''),'rust')for f,k in fields)+'}')
  if name in('BipedGroundJob','BipedPlacementInput','BipedPhase'):
   cpp.append(f'{name} Read{name}(Input& i){{{name} s;'+''.join('s.'+f+'='+wire.read_expr(k,'cpp')+';'for f,k in fields)+'return s;}')
   rust.append(f'fn read_{name}(i:&mut Input)->{name}{{'+name+'{'+''.join(f+':'+wire.read_expr(k,'rust')+','for f,k in fields)+'}}')
 return '\n'.join(cpp),'\n'.join(rust)
def frame(angle=0,height=0):
 c,s=math.cos(angle),math.sin(angle);return [[c,0,-s,0],[0,1,0,0],[s,0,c,0],[.137,height,.317,0]]
def zero(kind,defs):
 a=wire.array(kind);o=wire.option(kind)
 if a:return [zero(a[0],defs)for _ in range(a[1])]
 if o:return None
 if kind in('f32','u32','bool'):return 0
 return {f:zero(k,defs)for f,k in defs[kind]}
def corpus(defs):
 rng=random.Random(0x82d7c818);cases=[];stream=Stream();stream.word(64)
 for c in range(64):
  commands=[]
  def place(k,state=500,previous=501):
   v=zero('BipedPlacementInput',defs);v.update(frame=frame(c*.071,.2),velocity=[.137,(0,-3,3)[c%3],c%9+.137,(-0.0,.317)[c%2]],body_position=[.137,1.2,.317,0],current_state=state,previous_state=previous,previous_frame=frame(c*.071,.19));return (1,'BipedPlacementInput',v)
  commands.append(place(0))
  for k in range(96):
   if k in(19,43,71):
    phase=dict(phase=(.125,.5,.875)[k%3],rate=(0,1,7)[c%3],target=(-1,0,.5)[c%3],duration=None if c%2 else .317,forward_target=bool(c%3))
    commands.append((3,'seed',dict(correction=[.137,.317,-.731,(-0.0,.517)[c%2]],target=[.5,.7,1.2,0],enabled=c%2,phase=phase,index=c%4)));commands.append((2,'reset',None));commands.append(place(k,(500,501,502)[c%3],501));continue
   if k%13==0:commands.append((4,'advance',None));continue
   job=zero('BipedGroundJob',defs);job.update(contact_position=[.137,(0,.2,-.2)[k%3],.317,0],contact_normal=[0,1,0,0],support_frame=frame(k*.003,.03*(k%3)),target_position=[.137,0,.317+(0,.001,.2,1.2)[(k+c)%4],0],target_normal=[0,1,0,0],edge_position=[.317,.2,.731,.137],edge_normal=[0,1,0,0],flags=(0,1,3,5,9,0x181,0x101,0x201,0x209)[(c+k)%9],support_id=(1,1,1,2,2,0)[k%6],collision_displacements=[[0,0,0,0],[0,0,0,0]],animation_motion=[.01,0,(0,.137,.731)[(k+c)%3],(-0.0,.317)[c%2]],animation_velocity=[.137,0,(0,1,3)[k%3],.317],desired_direction=frame(k*.041)[2],animation_position=[.137,1.1,.317+k*.013,0],requested_duration=(.05,.1,.2,.731)[k%4],mirrored=bool(k%2),requested_phase=(-1,-1,.125,.5,.9)[(c+k)%5],override_duration=(0,.001,.137,.5)[k%4],animation_directed=(k%11==0),movement=(0,.25,.5,.75,1)[(k+c)%5],steering=(-1,-.5,0,.5,1)[k%5],sprint_pressed=k%5<2,suppress_lean=c%8==0,suppress_minimum=c%7==0,target_frame_present=k%3==0,edge_active=k%7==0,target_frame=frame(k*.021,.037),ignore_obstacle=c%3==0)
   if k%6==0:job['collision_displacements']=[[.137,0,.071,.517],[-.137,0,-.071,-.517]]
   if c%4==0:job['contact_normal']=[0,.8,.6,0];job['target_normal']=[0,.8,.6,0]
   if c%16==0 and k==2:job['animation_motion']=[0,0,0,0]
   if c%7==0:job['animation_velocity']=[rng.uniform(-4,4),rng.uniform(-.2,.2),rng.uniform(-4,4),rng.uniform(-1,1)]
   commands.append((0,'BipedGroundJob',job))
  stream.word(len(commands))
  for op,kind,value in commands:
   stream.word(op)
   if kind in defs:wire.encode(stream,kind,value,defs)
   elif kind=='seed':
    for v in value['correction']+value['target']:stream.float(v)
    stream.word(value['enabled']);wire.encode(stream,'BipedPhase',value['phase'],defs);stream.word(value['index'])
  cases.append(dict(index=c,commands=commands,label='complete retained ground controller, placement/reset/cadence/support/edge/obstacle/slide'))
 return bytes(stream.data),cases
def aliases():
 result={}
 for name in('settings.rs','settings/board.rs','settings/curves.rs','settings/metrics.rs'):
  dest='mod.rs'if name=='settings.rs'else name.split('/')[-1];result['atelier-host/src/offboard_settings/'+dest]=HOST+name
 result['atelier-host/src/output_bridge/original.rs']=CORE+'controller/output.rs';return result
def prepare(out,defs):
 cpp,rust=helpers(defs);snapshot=out/'simulation-source'
 if snapshot.exists():shutil.rmtree(snapshot)
 snapshot.mkdir()
 for p in [*CODE.glob('*.h'),*[CODE/(u+'.cpp')for u in UNITS]]:shutil.copy2(p,snapshot/p.name)
 cp=(PLUGIN/'Tests/Simulation/offboard_controller_probe.cpp').read_text().replace('// GENERATED_PROTOCOL',cpp);(snapshot/'offboard_controller_probe.cpp').write_text(cp)
 constants=original.source(CORE+'controller/state.rs');constants=constants[constants.index('pub(super) const ZERO:'):constants.index('#[derive(Clone, Copy, Debug)]')]
 bridge='mod output_bridge {use super::controller::{Frame,State,Vector};mod state{use super::{Frame,Vector};'+constants+'}\npub(super) mod original;pub(super) fn export(s:&State)->original::GroundResult{original::export(s)}}'
 rp=(PLUGIN/'Tests/Reference/offboard_controller_probe.rs').read_text().replace('// GENERATED_PROTOCOL',rust).replace('// ORIGINAL_OUTPUT_FORWARDING',bridge);path=out/'offboard-controller-reference.rs';path.write_text(rp)
 (out/'simulation-provenance.json').write_text(json.dumps({p.name:digest(p)for p in sorted(snapshot.iterdir())},indent=2)+'\n')
 (out/'protocol-provenance.json').write_text(json.dumps(dict(types=defs,original_source_sha256={CORE+p:hashlib.sha256(original.source(CORE+p).encode()).hexdigest()for p,_,_ in STRUCTS.values()},settings_aliases=aliases(),boundary='Complete unmodified original core controller and full unmodified host Offboard settings loader. Actual frozen ABIN bank metadata; ground jobs and placement remain explicit consumed producer inputs.'),indent=2)+'\n')
 return snapshot,path
def inspect(raw,cases):
 words=struct.unpack('<'+'I'*(len(raw)//4),raw);at=0;assert words[at:at+2]==(1,0);at+=2
 # Settings observation: 200 graph words + cap + metrics presence/values + board + launch.
 at+=16*2+8+32+1+6*16
 for _ in range(3):present=words[at];at+=1+2*present
 at+=12+5+32+2;assert words[at]==len(cases);at+=1;ops=Counter();distinct=set();changed=0
 for case in cases:
  assert words[at:at+2]==(case['index'],len(case['commands']));at+=2
  n=words[at];previous=words[at+1:at+1+n];at+=1+n
  for command in case['commands']:
   assert words[at]==command[0];ops[command[0]]+=1;at+=1;n=words[at];current=words[at+1:at+1+n];at+=1+n
   distinct.add(current);changed+=current!=previous;previous=current
 assert at==len(words),(at,len(words));assert set(ops)==set(range(5));assert changed>1000 and len(distinct)>1000
 return dict(operations=dict(ops),changed_snapshots=changed,distinct_full_states=len(distinct))
def loader_fixtures(assets):
 identity=lru_cache(maxsize=None)(converter.name_id)
 data=json.loads((assets/'private/stock/skater-collections.json').read_text());graphs=[('physics_biped',name,n)for name,n in [('Hash_6B93C51256A30FB4',8),('Hash_7209DCFDF3015EBF',4),('SpeedVsInput',16),('AutoTurnVsAngle',8),('Hash_31309236050A8F09',8),('Hash_CE45C724B30F9134',8),('TurnVsSpeed',8),('TurnDeltaVsSpeed',8),('SlideVsSlope',8),('SlideVsSpeed',8)]]
 fields=[(c,n,'graph',size)for c,n,size in graphs]+[('physics_state_offboard',n,'vector',4)for n in('GrabBoxSizeGrabbing','GrabBoxSize','GrabBoxOffset')]+[('physics_state_offboard',n,'float',1)for n in('GrabSplineMaxAngleToHorizontalGrabbing','GrabSplineMaxAngleToHorizontal','GrabSplineEndExclusion','GrabSplineAngleLimitGrabbing','GrabSplineAngleLimit')]+[('physics_state_offboard',n,'graph',8)for n in('Hash_DF759B46440F16E9','TurnVsStickAngle')]+[('physics_biped',n,'float',1)for n in('JumpSpeedScalar','JumpHeight')]
 def resolve(d,c,n):
  key='default'
  for _ in range(len(d['collections'])+1):
   record=next(r for r in d['collections']if identity(r['class'])==identity(c)and identity(r['key'])==identity(key));actual=next((f for f in record['fields']if identity(f)==identity(n)),None)
   if actual is not None:return record['fields'][actual]
   key=record['parent'];assert key
  raise AssertionError('inheritance cycle')
 result=[]
 for c,n,kind,size in fields:
  for failure in('missing','type','width','nonfinite')+(('unordered','duplicates')if kind=='graph'else()):
   d=copy.deepcopy(data);field=resolve(d,c,n)
   if failure=='missing':
    for r in d['collections']:
     if identity(r['class'])==identity(c):
      for f in list(r['fields']):
       if identity(f)==identity(n):del r['fields'][f]
   elif failure=='type':field['type']='EA::Reflection::Bool'
   elif failure=='width':field['data']='DEADBEEFCAFEBABE'if kind!='graph'else'DEADBEEF'
   else:
    values=re.sub(r'\s+','',field['data']);words=[values[k:k+8]for k in range(0,len(values),8)]
    if failure=='nonfinite':words[0]='7FC12345'
    elif failure=='duplicates':words[5]=words[4]
    else:words[4]='501502F9'
    field['data']=''.join(words)
   result.append((f'{c}/{n}/{failure}',d,failure=='duplicates'))
 # Every consecutive read position retains both invalid fields. The reported
 # original error must identify the first field, before any later read occurs.
 for first,second in zip(fields,fields[1:]):
  d=copy.deepcopy(data)
  for c,n,kind,size in(first,second):resolve(d,c,n)['type']='EA::Reflection::Bool'
  result.append((f'compound/{first[1]}/{second[1]}',d,False))
 return result
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',required=True,type=Path);p.add_argument('--metadata',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--target-dir',required=True,type=Path);p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 defs=schema();raw,cases=corpus(defs);(out/'input.bin').write_bytes(raw);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');snapshot,rust=prepare(out,defs)
 fixtures=loader_fixtures(a.assets);report=dict(cases=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(raw),input_sha256=hashlib.sha256(raw).hexdigest(),units=len(UNITS),loader_fixtures=len(fixtures))
 if a.preflight:print(json.dumps(report,indent=2));return
 reference=build_probe(out,'offboard-controller-reference',rust,a.target_dir,extra_sources=aliases());simulation=out/'offboard-controller-cpp'
 subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'offboard_controller_probe.cpp'),'-o',str(simulation)],check=True)
 bank=out/'settings.simulation';bank.write_bytes(converter.encode_settings(a.assets/'private/stock/skater-collections.json'))
 metadata=a.metadata.resolve();assert (metadata/'bank-0.skate').is_file()
 expected=subprocess.check_output([str(reference),str(a.assets.resolve())],input=raw);actual=subprocess.check_output([str(simulation),str(bank),str(metadata/'bank-0.skate'),str(metadata/'bank-1.skate')],input=raw);(out/'reference.bin').write_bytes(expected);(out/'cpp.bin').write_bytes(actual)
 if expected!=actual:
  first=next((n for n,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)))//4
  (out/'first-divergence.json').write_text(json.dumps(dict(first_word=first,reference_bytes=len(expected),simulation_bytes=len(actual)),indent=2)+'\n');raise AssertionError('Complete controller output differs')
 coverage=inspect(expected,cases);loader_results=[]
 for k,(label,data,success)in enumerate(fixtures):
  folder=out/'loader-fixtures'/str(k);path=folder/'private/stock/skater-collections.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data));converted=folder/'settings.simulation';converted.write_bytes(converter.encode_settings(path))
  e=subprocess.check_output([str(reference),str(a.assets.resolve()),str(folder)]);v=subprocess.check_output([str(simulation),str(bank),str(metadata/'bank-0.skate'),str(metadata/'bank-1.skate'),str(converted)]);(folder/'reference.bin').write_bytes(e);(folder/'cpp.bin').write_bytes(v)
  if e!=v:raise AssertionError(dict(loader=label,reference_bytes=len(e),simulation_bytes=len(v)))
  status=2+32+8+32+1+6*16
  ew=struct.unpack('<'+'I'*(len(e)//4),e)
  for _ in range(3):status+=1+2*ew[status]
  status+=12+5+32+2;assert bool(ew[status])==success,label
  loader_results.append(dict(label=label,success=success,exact_words=len(e)//4))
 report.update(passed=True,exact_words=len(expected)//4+sum(r['exact_words']for r in loader_results),output_sha256=hashlib.sha256(expected).hexdigest(),coverage=coverage,loaders=loader_results);(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
