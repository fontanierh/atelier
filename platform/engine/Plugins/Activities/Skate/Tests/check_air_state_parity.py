#!/usr/bin/env python3
"""Exact unchanged PhysicsAir state/math with required recorded runtime effects.

The active host input module is staged byte-identically with all consumed owner
fields explicitly bound. Core callback ordering and active host scheduling are
separate contracts: this check does not replace the full trajectory selector,
AirReckoning, SkeletonInput, collision controller or physical scheduler.
Run builds and probes only through the shared render lock/memory guard.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
from check_gesture_parity import converter,PLUGIN
from check_pumping_ground_force_parity import bits,scalar,floats
from reference_build import build_probe
from session_parity import REFERENCE_REVISION,digest

LENGTHS={0:34,1:130,2:150,3:101,4:0,5:130,6:35,7:13,8:128,9:0}
OPERATIONS=('seed','enter','update','post','exit','board','math','integrate','host_bindings','construct')
EVENT_LENGTHS={1:1,2:1,3:1,4:0,5:1,6:0,7:1,8:0,9:0,10:1,11:70,12:70,13:70,14:0,16:1,17:9,18:17,19:4,20:1,21:1,22:21,23:9,24:4,25:0,26:4,27:1,100:4,101:4,102:4,103:4,104:2,105:2,106:1,107:1,108:1,110:3,111:5,112:5,113:9}
IDENTITY=floats((1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,0))


def corpus():
 rng=random.Random(0x82d346c0);rows=[]
 def add(op,words=(),**meta):
  words=list(words);assert len(words)==LENGTHS[op],(op,len(words));rows.append(dict(index=len(rows),operation=op,words=words,**meta))
 def frame(tick,state=300,category=200,flags=0,frames=12,timer=.731,trajectory_offset=0):
  return floats((.317+tick*.137,-.317,.731,.113,-.137,.517+trajectory_offset,.731,.113,.719,1.137,3.517,-.317,.113,.719,.317,.137,.731))+[flags,state&0xffffffff,category&0xffffffff,frames&0xffffffff]+floats(((0,1/120,1/60,.1)[tick%4],((tick%9)-4)*.137,-9.8,timer))
 def launch(tick):
  return floats([((n+tick)%17-8)*.137 for n in range(64)]+[13.137+tick*.03125,24.719,1/60])+[tick%2,(tick//2)%2,(tick%8)+1]
 def runtime(tick,collision=False,query=False,normal=True,ready=False,vertical=None):
  return launch(tick)+floats((.517+tick*.03125,.137,-.317 if vertical is None else vertical,.731,.113))+[int(query),int(normal)]+floats(((0,1,0,.113) if tick%2==0 else (0,-1,0,-.317)))+[int(ready)]+floats((.137,.919,.317,.731,.719+tick*.03125,-.137,.517,-.317,.113,.731))+[int(collision)]+floats((.137,.317,-.731,.113,.719,-.317,.517,.973))
 def seed(com=False,latch=False,apex=False,countdown=0):
  return floats((10,20,30,.113,4,5,6,.719,1,-8,2,-.317,-1,.137,.731,.317,.113,.517,1.137,3.517))+[int(apex),int(com),int(latch),countdown&0xffffffff]+floats((0,1,0,.113,7,8,9,.731,.517,.137))
 acc=floats((.137,-9.8,.731,-.317));settings=floats((0,.1,.2,.3,.4,.5,.6,.7,0,.137,.317,.731,1.137,.719,.517,.113,.317,60,.731))
 add(9,proof='construct')
 for previous in (0,100,103,201,300,500,701,0xffffffff):
  for category in (200,400):
   for flags in (0,0x4000):
    for correction in (-1,11,12):
     add(0,seed(com=True,latch=True,apex=True,countdown=-7))
     add(1,frame(11,previous,category,flags,correction)+acc+runtime(11),proof='entry',previous=previous,category=category,flags=flags,correction=correction)
     add(4,proof='exit')
 for stream in range(24):
  add(0,seed(com=stream%2==1,latch=stream%5==0,countdown=(0,1,7,-2147483648)[stream%4]))
  for tick in range(12):
   flags=(0,0x4000,0x8000)[(tick+stream)%3];timer=(0,-.137,.731)[(tick+stream//2)%3];correction=(0,11,12,20)[(tick+stream)%4]
   add(2,frame(tick,0 if (tick+stream)%11==0 else 300,200,flags,correction,timer,trajectory_offset=stream*.125)+acc+runtime(tick+stream,collision=tick%3==0,query=tick%5==0,normal=tick%3!=0,ready=tick>=2)+[stream%2]+settings,proof='progression',stream=stream,tick=tick)
   if tick in (2,5,9):add(3,runtime(tick,vertical=-.137 if tick==9 else .317),proof='post')
  add(4,proof='exit')
 for com in (False,True):
  for correction in (0,11,12,100):
   for collision in (False,True):
    add(0,seed(com=com));add(5,frame(3,frames=correction)+acc+runtime(3,collision=collision),proof='board',com=com,correction=correction,collision=collision)
 for velocity_bits in (0x80000000,0x7fc01234,bits(-.137)):
  add(0,seed());data=runtime(7);data[72]=velocity_bits;add(3,data,proof='apex_edge',vertical=velocity_bits);add(3,runtime(8,vertical=-1),proof='apex_after_edge')
 add(0,seed(apex=True));add(3,runtime(9),proof='apex_already')
 special=((0,0,0,-0.),(-0.,-0.,-0.,-0.),(1e-5,0,0,.137),(1.52587890625e-5,0,0,-.317),(1,2,3,.719),(-1,-2,-3,-.731))
 for tick in range(160):
  left=special[tick%len(special)] if tick<36 else tuple(rng.uniform(-8,8) for _ in range(4));right=special[(tick+2)%len(special)] if tick<36 else tuple(rng.uniform(-8,8) for _ in range(4))
  add(6,frame(tick,frames=tick%17)+[(0,11,12,0xffffffff,0x80000000,0x7fffffff)[tick%6]]+floats(left+right)+[bits((-.137,-0.,0.,.137,3.1415927,6.2831855,7.137)[tick%7])])
 for tick in range(64):add(7,floats([rng.uniform(-8,8) for _ in range(12)]+[-1]),proof='four_lane_integrate')
 for tick in range(48):
  raw=floats([((n+tick)%29-14)*.137 for n in range(52)])
  mode=tick%5 if tick<40 else (5,0xffffffff)[tick%2];toolkit=tick%7!=0
  raw += [0x2000 if tick%2 else 0,0xabcdef01,0x12345678,0xffffffff if tick%3==0 else 300,400,mode,0xffffffff if tick%4==0 else tick,0x5371abcd]
  raw += floats((1/60,.731,-9.8,.137,-.317))
  raw += floats((.137,-9.8,.317,.731))+floats([((n+tick)%23-11)*.113 for n in range(32)])+floats((.137,.317,.731,.113,.719,-.137,.517,-.317))+[int(toolkit)]+floats([((n+tick)%11-5)*.317 for n in range(16)])+floats((13.137,24.719))
  add(8,raw,proof='host_binding',mode=mode,toolkit=toolkit)
 encoded=struct.pack('<I',len(rows))+b''.join(struct.pack('<'+'I'*(len(row['words'])+1),row['operation'],*row['words']) for row in rows)
 return encoded,rows


def validate_input(data,rows):
 words=struct.unpack('<'+'I'*(len(data)//4),data);assert words[0]==len(rows);at=1
 for row in rows:
  n=LENGTHS[row['operation']];assert words[at]==row['operation'];assert list(words[at+1:at+1+n])==row['words'];at+=1+n
 assert at==len(words)


class Reader:
 def __init__(self,data):self.data=data;self.at=0
 def word(self):v=struct.unpack_from('<I',self.data,self.at)[0];self.at+=4;return v
 def words(self,n):return [self.word() for _ in range(n)]
 def string(self):n=self.word();v=self.data[self.at:self.at+n].decode();self.at+=((n+3)//4)*4;return v
 def status(self):return None if self.word() else self.string()


def trace_events(words):
 at=0;result=[]
 while at<len(words):
  op=words[at];at+=1
  if op==15:
   count=1+(4 if words[at] else 0)
  else:count=EVENT_LENGTHS[op]
  result.append((op,words[at:at+count]));at+=count
 assert at==len(words);return result


def coverage(data,rows):
 r=Reader(data);stock=r.words(25);assert r.words(4)==floats((0,scalar(0xc11ccccd),0,0));assert r.word()==len(rows);counts=Counter();events=Counter();proof=Counter();decoded=[];prior=None;prior_reck=None;blend_values=set();trajectory_values=set();errors=Counter()
 for row in rows:
  assert r.words(2)==[row['index'],row['operation']];assert r.status() is None;state=r.words(24);reck=r.words(10);output=r.words(7);write=r.word() if output[-1] else None
  assert output[0]==state[20] and output[2:6]==state[13:17] and output[-1]==state[22]
  assert write==(bits(4) if state[22] else None)
  calls=trace_events(r.words(r.word()));extra=r.words(r.word());ops=[op for op,_ in calls];events.update(ops);counts[OPERATIONS[row['operation']]]+=1
  if row['operation']==1:
   assert ops[:7]==[1,2,3,2,4,5,6] and [v for op,v in calls if op==2]==[[7],[6]]
   selected=(row['flags']&0x4000)==0 if row['category']==400 or row['previous']==701 else row['previous'] not in (100,103,201)
   heading=selected and row['category']!=400 and row['previous']!=701
   assert state[21]==selected and (8 in ops)==heading
   assert state[20]==0 and state[22:24]==[0,0] and state[17]==0
   if not selected:assert prior is not None and state[:13]==prior[:13];proof['entry_preserves_trajectory']+=1
   else:proof['entry_com']+=1
  elif row['operation']==2:
   assert ops[0]==9 and 14 in ops and ops.index(14)<ops.index(18)<ops.index(21)<ops.index(22)<ops.index(25)<len(ops)-1
   assert ops[-1]==7 and (19 in ops)!=(20 in ops)
   completed=[v for op,v in calls if op==18][0];collision=[v for op,v in calls if op==22][0]
   assert collision[:4]==completed[11:15] and collision[4:12]==[0]*8
   assert prior_reck is not None and collision[:4]!=prior_reck[4:8],(row['index'],'completed collision normal did not differ from entry snapshot')
   blend_values.add(completed[4]);proof['fresh_reckoning_normal']+=1
   if 13 in ops:
    writes=[v[0] for op,v in calls if op==106];assert writes[-1]==0
    fills=ops.count(12)
    if fills==2:assert writes==[1,0];assert ops.index(101)<ops.index(102)<ops.index(103)<ops.index(107)<ops.index(108)<ops.index(104)<ops.index(105);proof['com_double_fill']+=1
    else:assert fills==1;proof['single_fill_launch']+=1
   if 23 in ops:assert [v[0] for op,v in calls if op==23]==[15]
   if 19 in ops:trajectory_values.add(tuple(state[:4]))
  elif row['operation']==3:
   assert ops[-1]==27 and calls[-1][1]==[0]
   assert (26 in ops)==(prior[20]==0)
   if row.get('proof')=='apex_edge':assert state[20]==(scalar(row['vertical'])<0);proof['apex_edges']+=1
   if row.get('proof')=='apex_already':assert ops==[27];proof['apex_latched_skips_velocity']+=1
  elif row['operation']==4:
   assert state[21]==0 and reck[-2:]==[0,0]
   assert prior is not None and state[:21]==prior[:21] and state[22:]==prior[22:];proof['exit_selective']+=1
  elif row['operation']==5:
   assert ops[:2]==[21,22]
   if row['collision']:assert ops==[21,22,23] and calls[-1][1][0]==15;proof['collision_suppresses_velocity']+=1
   elif not row['com'] and row['correction']<12:assert 24 in ops;proof['jump_board_velocity']+=1
   else:assert ops==[21,22];proof['board_no_velocity_write']+=1
  elif row['operation']==7:
   assert state[12]==row['words'][12] and state[8:12]==row['words'][8:12];proof['ballistic_four_lanes']+=1
  elif row['operation']==8:
   e=Reader(struct.pack('<'+'I'*len(extra),*extra));e.words(25);error=e.status()
   if row['mode']<5:assert error is None;e.words(27)
   else:assert error==f"Invalid trajectory physics mode {row['mode']}";errors[error]+=1
   error=e.status()
   if row['toolkit']:assert error is None;record=e.words(70);assert record[67:69]==[0,0] and record[69] in (1,7)
   else:assert error=='Air launch requires current BoardToolkit';errors[error]+=1
   assert e.at==len(e.data);proof['bound_host_fields']+=1
  elif row['operation']==9:
   assert state==[0]*12+[bits(-1)]+floats((0,1,0,0))+[0]*7
   assert extra[:32]==IDENTITY*2 and extra[32:]==[0]*38;proof['constructor']+=1
  prior=state;prior_reck=reck;decoded.append(dict(row=row,state=state,reckoning=reck,output=output,scalar_write=write,events=calls,extra=extra))
 assert r.at==len(data),(r.at,len(data));assert proof['entry_preserves_trajectory']>=40 and proof['entry_com']>=40
 assert proof['com_double_fill']>4 and proof['single_fill_launch']>4 and proof['fresh_reckoning_normal']==288
 assert proof['apex_edges']==3 and proof['apex_latched_skips_velocity']==1
 assert proof['collision_suppresses_velocity']==8 and proof['jump_board_velocity']==2 and proof['board_no_velocity_write']==6
 assert len(blend_values)>1 and bits(0) in blend_values and len(trajectory_values)>32
 assert events[19]>32 and events[20]>32 and events[23]>32 and events[24]>2 and events[16]==30
 return dict(records=len(rows),operations=dict(counts),event_counts=dict(events),proofs=dict(proof),normal_blend_variants=len(blend_values),integrated_position_variants=len(trajectory_values),source_binding_errors=dict(errors)),decoded


def provenance(output):
 root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip());base=PLUGIN/'ThirdParty/skate-runtime/crates/skate-host/src/physics/air_phase/input.rs';relative=base.relative_to(root).as_posix();original=subprocess.check_output(['git','show',f'{REFERENCE_REVISION}:{relative}'],cwd=root)
 source=original.decode();anchors=('    pub fn load(data: &Collections)','pub(super) fn frame(','pub(crate) fn selector_input(','pub(crate) fn launch_info(')
 from check_pumping_ground_force_parity import extract
 boundaries=[]
 for anchor in anchors:
  body,start,end=extract(source,anchor);assert source[start:end]==body;boundaries.append(dict(anchor=anchor,start_byte=start,end_byte=end,body_sha256=hashlib.sha256(body.encode()).hexdigest()))
 phase=base.parent.parent/'air_phase.rs';phase_relative=phase.relative_to(root).as_posix();phase_bytes=subprocess.check_output(['git','show',f'{REFERENCE_REVISION}:{phase_relative}'],cwd=root);phase_source=phase_bytes.decode();constant='const COM_ACCELERATION: [f32; 4] = [0.0, f32::from_bits(0xc11c_cccd), 0.0, 0.0];';assert phase_source.count(constant)==1;start=phase_source.index(constant);assert phase_source[start+len(constant):start+len(constant)+1]=='\n'
 (output/'air-state-stock-constant.rs').write_text(constant+'\npub fn acceleration()->[f32;4] {COM_ACCELERATION}\n')
 report=dict(source=relative,source_sha256=hashlib.sha256(original).hexdigest(),methods=boundaries,host_com_acceleration=dict(source=phase_relative,source_sha256=hashlib.sha256(phase_bytes).hexdigest(),start_byte=start,end_byte=start+len(constant),body_sha256=hashlib.sha256(constant.encode()).hexdigest()),boundary='Entire unchanged production input.rs module is staged as a byte-identical alias. Data-only owner shell contains every field consumed by load/frame/selector_input/launch_info; all fields are protocol-bound. No method/producer callbacks are substituted in these binding paths. Core runtime adapters record mandatory service arguments/reads and provide explicit fixture-completed outputs, with real original AirMath. Full active host scheduling and production service implementations remain separate.')
 (output/'host-bindings-provenance.json').write_text(json.dumps(report,indent=2)+'\n')
 return {'atelier-host/src/bindings/input.rs':'crates/skate-host/src/physics/air_phase/input.rs'}


def build_simulation(output):
 live=PLUGIN/'Source/AtelierSkate/Private/Simulation';snapshot=output/'simulation-source'
 if snapshot.exists():shutil.rmtree(snapshot)
 snapshot.mkdir();units=('SimulationMath','NameId','Settings','StockSettingsReader','AirMath','AirState','AirStateSettings')
 for p in list(live.glob('*.h'))+[live/(name+'.cpp') for name in units]:shutil.copyfile(p,snapshot/p.name)
 shutil.copyfile(PLUGIN/'Tests/Simulation/air_state_probe.cpp',snapshot/'air_state_probe.cpp');report={p.name:digest(p) for p in sorted(snapshot.iterdir())};(output/'simulation-source-provenance.json').write_text(json.dumps(report,indent=2)+'\n')
 binary=output/'air-state-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(unit+'.cpp')) for unit in units],str(snapshot/'air_state_probe.cpp'),'-o',str(binary)],check=True);return binary


def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('assets','output','target-dir'):p.add_argument('--'+name,type=Path,required=True)
 args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
 for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
 commands,rows=corpus();validate_input(commands,rows);(output/'input.bin').write_bytes(commands);aliases=provenance(output)
 original=build_probe(output,'air-state-reference',PLUGIN/'Tests/Reference/air_state_probe.rs',args.target_dir,extra_sources=aliases);simulation=build_simulation(output);settings=output/'settings.skate';settings.write_bytes(converter.encode_settings(args.assets/'private/stock/skater-collections.json'))
 expected=subprocess.check_output([str(original),str(args.assets.resolve())],input=commands);actual=subprocess.check_output([str(simulation),str(settings)],input=commands)
 (output/'reference.bin').write_bytes(expected);(output/'simulation.bin').write_bytes(actual)
 if expected!=actual:
  byte=next((i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b),min(len(actual),len(expected)));(output/'first-divergence.json').write_text(json.dumps(dict(byte=byte,expected_bytes=len(expected),actual_bytes=len(actual)),indent=2)+'\n');raise AssertionError(f'PhysicsAir differs at byte {byte}')
 proof,decoded=coverage(expected,rows);(output/'original-trace.json').write_text(json.dumps(decoded,indent=2)+'\n')
 report=dict(passed=True,coverage=proof,output_bytes=len(actual),output_sha256=hashlib.sha256(actual).hexdigest(),comparison='Unchanged original PhysicsAir Enter/Exit/Update/Board/Post/output/constructor and AirMath, with every required callback read/argument/order and launch setter write; unchanged original active-host stock load/frame/selector/launch bindings.',limitations='Full active-host schedule and real selector launch/update, collision-controller, AirReckoning, SkeletonInput/board/wipeout producer implementations are explicit future integration dependencies. Core generic COM repeated Fill and active-host prepared-launch ordering remain distinct. Runtime callbacks receive fixture-completed observations, not substitutes for full producers. Simulation error return on engine failure is outside the original infallible generic-core parity domain. Valid stock setting values are compared; malformed-setting diagnostics are not.',stock_data_format='Simulation ATATTR01; original collection parsing exists only in tooling/oracle.',reference_provenance_sha256=digest(output/'air-state-reference-provenance.json'),host_bindings_provenance_sha256=digest(output/'host-bindings-provenance.json'),simulation_source_provenance_sha256=digest(output/'simulation-source-provenance.json'))
 (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
