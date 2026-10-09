#!/usr/bin/env python3
"""Actual bridge Session, raw host cadence and unchanged marker update.

Only root compiles/executes under the render guard. --preflight stages immutable
source and verifies wire/hashes. External inputs are authored triangle/rail
snapshots, spawn/preferences, raw platform packets and host dt. No completed
input, state, trajectory, pose, camera, contacts or scoring record is injected.
OS polling and asynchronous world-builder thread timing are external boundaries.
"""
import argparse
from collections import Counter,defaultdict
import copy,hashlib,json,math,re,shutil,struct,subprocess
from pathlib import Path
import check_gameplay_runtime_parity as frame
import check_gameplay_world_input_parity as world_input
from session_parity import REFERENCE_REVISION,digest
PLUGIN,CODE,TESTS=frame.PLUGIN,frame.CODE,frame.TESTS
UNITS=tuple(dict.fromkeys((*frame.UNITS,*world_input.UNITS,'GameplaySession','SessionMarkerRuntime','DebugString')))
OWNED=(TESTS/'Simulation/gameplay_session_probe.cpp',TESTS/'Reference/gameplay_session_probe.rs',TESTS/'Reference/gameplay_session_observer.rs',Path(__file__))
PRODUCTION=tuple(CODE/(name+ext)for name in('GameplaySession','SessionMarkerRuntime')for ext in('.h','.cpp'))
SECTIONS=('pose','reference','marker','controller','host','gameplay')
OPS={0:'activate',1:'tick',2:'collect',3:'advance',4:'suspend',5:'host_step',6:'configure',7:'tune',8:'launch',9:'aspect',10:'install_collision',11:'observe'}
bits,fs=world_input.bits,world_input.fs

def sections(text):
 p=re.split(r'^// @SECTION (.+)$',text,flags=re.M);assert len(p)%2==1;return dict(zip(p[1::2],p[2::2]))

def once(text,old,new):
 assert text.count(old)==1,(old,text.count(old));return text.replace(old,new)

def append(path,extra):path.write_bytes(path.read_bytes()+extra.encode())

def build_reference(out,target,compile=False):
 frame.build_reference(out,target,compile=False);crate=out/'observed-source/atelier-host';source=out/'reference-source'
 if not source.exists():source=out/'original-source'
 report=json.loads((out/'reference-provenance.json').read_text());extracts=[]
 raw=(TESTS/'Reference/gameplay_world_input_observer.rs').read_text();a=raw.index('// BEGIN CONTROLLERS\n')+len('// BEGIN CONTROLLERS\n');b=raw.index('// END CONTROLLERS',a);controller=raw[a:b]
 methods=('fn migration_gameplay_raw(','fn migration_gameplay_actions(','fn migration_gameplay_observe(','fn migration_gameplay_sample(')
 helpers='\n'.join(frame.function(controller,m)for m in methods)
 a=raw.index('// BEGIN CORE_HISTORY\n')+len('// BEGIN CORE_HISTORY\n');b=raw.index('// END CORE_HISTORY',a);history=raw[a:b]
 append(crate/'src/input/controllers.rs','\n'+helpers+'\n');append(out/'observed-source/crates/skate-core/src/input/history.rs','\n'+history)
 extracts.append(dict(file='Tests/Reference/gameplay_world_input_observer.rs',full_sha256=digest(TESTS/'Reference/gameplay_world_input_observer.rs'),controller_methods_sha256=hashlib.sha256(helpers.encode()).hexdigest(),history_section_sha256=hashlib.sha256(history.encode()).hexdigest()))
 original_main=source/'atelier-host/src/main.rs'
 # This pipe adapter is shipped outside the host crate; retain exact original
 # revision bytes separately rather than substituting an accumulator kernel.
 if not original_main.exists():
  data=frame.source_at_reference('atelier-host/src/main.rs');original_main=out/'session-pipe-main.rs';original_main.write_text(data)
 else:data=original_main.read_text()
 at=data.index('                elapsed = (elapsed + dt).min(0.1);');end=data.index('                // Also acknowledge sub-tick',at);step=data[at:end]
 valid=frame.function(data,'fn publish(');start=valid.index('    if !p.root.is_finite()');end=valid.index('    let (score, reward, trick)',start);finite=valid[start:end]
 declaration='if !dt.is_finite() || dt < 0. { return Err("Invalid frame interval".into()); }\n'
 observer=(TESTS/'Reference/gameplay_session_observer.rs').read_text();observer=once(observer,' // @ORIGINAL_HOST_STEP',declaration+step);observer=once(observer,' // @ORIGINAL_PUBLISH_FINITE_GATE',finite)
 for rel,extra in sections(observer).items():append(crate/'src'/rel,'\n'+extra)
 template=(TESTS/'Reference/gameplay_session_probe.rs').read_text();parent=(TESTS/'Reference/gameplay_runtime_probe.rs').read_text();prefix=parent[:parent.index('fn main()->Result<(),String>{')]
 # Inner crate attributes must stay at the beginning of the generated file.
 template=once(template,'//! Actual unchanged bridge Session and marker runtime; no completed producers.\n// @GAMEPLAY_PROBE_PREFIX',prefix)
 (crate/'src/migration_probe.rs').write_text(template)
 cargo=crate/'Cargo.toml';cargo.write_text(once(cargo.read_text(),'name="gameplay-runtime-reference"','name="gameplay-session-reference"'))
 prefixes={}
 for rel,sha in report['original_source_sha256'].items():
  p=source/rel;dest=crate/'src'/rel.removeprefix('crates/skate-host/src/')if rel.startswith('crates/skate-host/src/')else out/'observed-source'/rel
  if rel.endswith(('/lib.rs','/main.rs'))and rel.startswith('crates/skate-host/'):continue
  assert dest.read_bytes()[:p.stat().st_size]==p.read_bytes(),rel;prefixes[rel]=dict(original_sha256=sha,original_bytes=p.stat().st_size,generated_sha256=digest(dest))
 extracts += [dict(file='atelier-host/src/main.rs',full_sha256=digest(original_main),cadence_sha256=hashlib.sha256(step.encode()).hexdigest(),pose_finite_gate_sha256=hashlib.sha256(finite.encode()).hexdigest()),dict(file='Tests/Reference/gameplay_runtime_probe.rs',full_sha256=digest(TESTS/'Reference/gameplay_runtime_probe.rs'),prefix_sha256=hashlib.sha256(prefix.encode()).hexdigest())]
 report.update(session_original_prefixes=prefixes,session_borrowed_observers=extracts,session_proof={p.name:digest(p)for p in OWNED},session_generated_sha256=digest(crate/'src/migration_probe.rs'),scope=__doc__)
 (out/'reference-provenance.json').write_text(json.dumps(report,indent=2)+'\n');binary=out/'gameplay-session-reference'
 if compile:
  subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(cargo),'--target-dir',str(target.resolve()),'--bin','gameplay-session-reference'],check=True);shutil.copy2(target.resolve()/'release/gameplay-session-reference',binary)
 return binary

def build_simulation(out,compile=False):
 frame.build_simulation(out,compile=False);snapshot=out/'simulation-source';raw=(TESTS/'Simulation/gameplay_runtime_probe.cpp').read_bytes();prefix=raw[:raw.index(b'int main(')]
 (snapshot/'gameplay_session_helpers.inc').write_bytes(prefix);shutil.copy2(OWNED[0],snapshot/OWNED[0].name)
 raw=(TESTS/'Simulation/gameplay_world_input_probe.cpp').read_text();helper=frame.function(raw,'struct GameplayWorldInputObserver')+';'
 (snapshot/'gameplay_session_controller.inc').write_text('namespace atelier::skate{\n'+helper+'\n}\n')
 friends={}
 for filename,name in(('Input.h','PadHistory'),('ControllerInputRuntime.h','ControllerInputRuntime')):
  p=snapshot/filename;old=p.read_text();new=world_input.add_friend(old,name);assert new.replace(world_input.FRIEND,'')==old;p.write_text(new);friends[filename]=dict(original_sha256=hashlib.sha256(old.encode()).hexdigest(),snapshot_sha256=digest(p))
 for name in UNITS:shutil.copy2(CODE/(name+'.cpp'),snapshot/(name+'.cpp'))
 report=json.loads((out/'simulation-provenance.json').read_text());report.update(session_friends=friends,session_snapshot_sources={p.name:digest(p)for p in sorted(snapshot.glob('*.h'))+sorted(snapshot.glob('*.cpp'))},session_production={p.name:digest(p)for p in PRODUCTION},session_borrowed_cpp=dict(gameplay_full_sha256=digest(TESTS/'Simulation/gameplay_runtime_probe.cpp'),gameplay_prefix_sha256=hashlib.sha256(prefix).hexdigest(),controller_file_sha256=digest(TESTS/'Simulation/gameplay_world_input_probe.cpp'),controller_struct_sha256=hashlib.sha256(helper.encode()).hexdigest()),units=UNITS)
 (out/'simulation-provenance.json').write_text(json.dumps(report,indent=2)+'\n');binary=out/'gameplay-session-simulation'
 if compile:subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(name+'.cpp'))for name in UNITS],str(snapshot/OWNED[0].name),'-o',str(binary)],check=True)
 return binary

def text(v):return [len(v.encode()),*v.encode()]
def xbox(**values):return world_input.xbox(**values)
def tick(**values):return [1,*xbox(**values)]
def collect(number,dt=1/60,slot=0,**values):
 samples=[world_input.error()for _ in range(4)];samples[slot]=world_input.packet(number,**values);return [2,bits(dt),*world_input.encode_samples(samples)]
def activate(x=0,y=1,z=0,heading=0,generation=0):return [0,*fs([x,y,z,heading]),generation]
def configure(goofy=0,difficulty='normal',trucks=.5):return [6,*text(difficulty),goofy,bits(trucks)]
def world(height=0,wall=False,empty=False):
 triangles=[]if empty else world_input.floor(size=50,height=height)
 if wall:triangles += [[[-8,0,3],[-8,3,3],[8,3,3]],[[-8,0,3],[8,3,3],[8,0,3]]]
 return dict(triangles=triangles,rails=[]if empty else[[[-3,height+.25,1],[3,height+.25,1]]])
def install(snapshot):return [10,*world_input.encode_snapshot(snapshot)]

def corpus():
 cases=[]
 for goofy in(0,1):
  for scenario in('cadence-held-flick','marker-place-return','collision-activation-errors','air-period'):
   rows=[configure(goofy),activate(generation=1+goofy),*[tick()for _ in range(20)]]
   if scenario=='cadence-held-flick':
    for dt in(0.,1/240,1/120,1/60,.1,.5):rows.append([5,bits(dt),*xbox(buttons=0x1000,left=(1000,-1000))])
    for k in range(32):
     rows += [collect(k//3,slot=k%4,buttons=(0,0x1000,0x2000,0x100)[k%4],left=(0,32767)if k%2 else(-32768,0),right=(0,-32768)if k%4<2 else(32767,32767)),[3]]
     if k%5==0:rows += [[3],[3]]
    for raw in(-32768,-30000,-1000,0,1000,30000,32767):rows += [tick(right=(raw,-raw if raw!=-32768 else 32767)),tick(right=(raw,raw)),tick()]
    rows += [[4],[3],collect(7,buttons=0x1000),[3],[5,0x7fc12345,*xbox()],[5,bits(-.1),*xbox()]]
   elif scenario=='marker-place-return':
    rows += [collect(1,buttons=0x100|0x2),[3],[3],collect(1,buttons=0x100|0x2),[3],collect(2),[3],[8,*fs([8,0,0])]]
    rows += [tick()for _ in range(48)]
    for k in range(28):rows += [collect(3+k,dt=1/60,buttons=0x100|0x1),[3]]
    rows += [collect(80),[3],collect(81,dt=.5,buttons=0x100|0x1),[3],[4],collect(82,buttons=0x100|0x2),[3],collect(83),[3]]
    rows += [install(world(wall=True)),activate(z=2.9,generation=2),collect(84),[3],collect(85,buttons=0x100|0x2),[3]]
   elif scenario=='collision-activation-errors':
    rows += [install(world(.2)),*[tick()for _ in range(12)],install(dict(triangles=world_input.floor(),rails=[[]])),install(world(empty=True)),*[tick()for _ in range(4)],install(world()),activate(x=1,heading=.317,generation=3),activate(x=2,heading=-.731,generation=4)]
    rows += [[7,*fs([1.5,2.,1.5,2.])],[7,*fs([0.,1.,1.,1.])],configure(goofy,'EASY',.7),configure(goofy,'bad\n\0'),configure(goofy,'\u0085'),[9,bits(4/3)],[9,bits(16/9)],[9,0x7fc12345],*[tick()for _ in range(12)]]
   else:
    rows += [[8,*fs([0,15,10])]]
    for k in range(140):rows += [[5,bits((1/120,1/60,.04)[k%3]),*xbox(right=(0,-32768)if k<4 else(0,32767)if k<8 else(0,0),triggers=(255,255)if k<30 else(0,0))]]
    rows += [activate(x=.5,generation=5),[8,*fs([0,-20,30])],*[tick()for _ in range(24)]]
   cases.append(dict(index=len(cases),scenario=scenario,goofy=goofy,world=world(),spawn=[0,0,0],heading=(0,.317)[goofy],rows=rows))
 # Retain every prior history. The original trace reaches valid four-wheel
 # support at this prefix; its earlier set edges correctly occur in the air.
 # Add a fresh set edge there, move on actual retained velocity, then return.
 marker_case=dict(cases[1]);marker_case.update(index=len(cases),scenario='marker-reachable-ground-return')
 rows=list(marker_case['rows'][:134])
 rows += [collect(1000,buttons=0x102),[3],[3]]
 for k in range(4):rows += [collect(1001+k),[3]]
 rows += [tick()for _ in range(60)]
 for k in range(28):rows += [collect(1100+k,buttons=0x101),[3]]
 for k in range(4):rows += [collect(1200+k),[3]]
 marker_case['rows']=rows;cases.append(marker_case)
 return cases

def encode(cases):
 words=[len(cases)];ranges=[]
 for c in cases:
  start=len(words);words += world_input.encode_snapshot(c['world'])+fs(c['spawn']+[c['heading']])+[len(c['rows'])]+[w for row in c['rows']for w in row];ranges.append([start*4,len(words)*4])
 return struct.pack('<'+'I'*len(words),*words),ranges

def protocol_audit(raw,cases,ranges):
 words=struct.unpack('<'+'I'*(len(raw)//4),raw);at=0;counts=Counter()
 def take(n):
  nonlocal at
  assert at+n<=len(words);v=words[at:at+n];at+=n;return v
 def word():return take(1)[0]
 def snapshot():
  n=word();take(n*9);r=word()
  for _ in range(r):take(word()*3)
 assert word()==len(cases)
 for c,(start,end)in zip(cases,ranges):
  assert at*4==start;snapshot();take(4);assert word()==len(c['rows'])
  for row in c['rows']:
   begin=at;op=word();assert op in OPS;counts[OPS[op]]+=1
   if op==0:take(5)
   elif op==1:take(7)
   elif op==2:
    take(1)
    for _ in range(4):
     kind=word();counts['ready_device_packets'if kind==0 else'device_errors']+=1;take(9 if kind==0 else 1)
   elif op==5:take(8)
   elif op==6:take(word());take(2)
   elif op==7:take(4)
   elif op==8:take(3)
   elif op==9:take(1)
   elif op==10:snapshot()
   assert list(words[begin:at])==row,(c['index'],op)
  assert at*4==end
 assert at==len(words)
 return dict(counts)

class Reader(frame.Reader):
 def snapshot(self):
  assert self.word()==len(SECTIONS);sections={};spans={}
  for name in SECTIONS:n=self.word();at=self.at;sections[name]=self.take(n);spans[name]=[at,self.at]
  return sections,spans

def decode(raw,cases):
 r=Reader(raw);assert r.word()==len(cases);traces=[]
 for c in cases:
  assert r.word()==len(c['rows']);loaded=r.status();frames=[];initial=None
  if loaded['okay']:
   initial,_=r.snapshot()
   for cmd in c['rows']:
    at=r.at;assert r.word()==cmd[0];status=r.status();snapshot,spans=r.snapshot();frames.append(dict(op=cmd[0],status=status,sections=snapshot,spans=spans,begin=at,end=r.at))
  else:assert not c['rows']
  traces.append(dict(loaded=loaded,initial=initial,frames=frames))
 assert r.at==len(raw),(r.at,len(raw));return traces

def coverage(traces,cases):
 counts=Counter();periods=set();markers=set();poses=set();states=set();cameras=set();scores=set()
 for trace,c in zip(traces,cases):
  assert trace['loaded']['okay'],trace['loaded'];prior=trace['initial']
  for row,cmd in zip(trace['frames'],c['rows']):
   after=row['sections'];okay=row['status']['okay'];counts[OPS[row['op']]]+=1;counts['successes'if okay else'failures']+=1
   pose=after['pose'];poses.add(tuple(pose));periods.add(pose[-1]);marker=after['marker'];markers.add(tuple(marker));counts['marker_observations']+=marker[0]
   # Complete immutable source/simulation snapshots are compared before assertions.
   if row['op']in(6,7,10)and not okay:assert after==prior,('rejected public mutation changed owners',c['index'],cmd)
   if row['op']==5 and cmd[1]in(0x7fc12345,bits(-.1)):assert row['status']['error']=='Invalid frame interval'and after==prior
   world_input.read_input_snapshot(after['controller'],counts)
   g=frame.Reader(struct.pack('<'+'I'*len(after['gameplay']),*after['gameplay']));inner,_=g.snapshot();assert g.at==len(g.data);states.add(inner['state'][0]);cameras.add(tuple(inner['camera']));scores.add(tuple(inner['scoring']))
   if row['op']==4:assert after['host'][0]==bits(0);counts['suspends']+=1
   if row['op']==0 and okay:assert after['host']==[bits(0),cmd[-1]];counts['activation_resets']+=1
   if marker[0]:
    at=21;elapsed,fired,tail=marker[at:at+3];counts['marker_fired']+=fired;counts['marker_tail']+=tail>0
   prior=after
 assert counts['successes']>256 and counts['failures']>4,counts
 assert len(poses)>128 and len(cameras)>32 and len(scores)>8,(len(poses),len(cameras),len(scores))
 assert counts['marker_observations']>0 and counts['marker_fired']>0,counts
 assert counts['activation_resets']>4 and counts['suspends']>0,counts
 # The original Session fixes camera_type=1 and special_effect=0. Its stock
 # CameraHigh graph contains no rate requester. Dynamic camera-driven cadence
 # is tested separately with an explicitly authored camera-resource fixture.
 stock_period=traces[0]['initial']['pose'][-1]
 assert periods=={stock_period},('Stock CameraHigh cadence changed',periods,stock_period)
 return dict(counts,periods=sorted(periods),states=sorted(states),distinct_pose_snapshots=len(poses),distinct_marker_snapshots=len(markers),distinct_camera_snapshots=len(cameras),distinct_score_snapshots=len(scores),cadence_scope='Stock Session CameraHigh remains at its initial period; authored-camera resource proof covers dynamic requests separately.')

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in('assets','simulation-package','output','target-dir'):p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 for name in('result.json','first-divergence.json'):(out/name).unlink(missing_ok=True)
 cases=corpus();raw,ranges=encode(cases);protocol=protocol_audit(raw,cases,ranges);(out/'input.bin').write_bytes(raw);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
 reference=build_reference(out,a.target_dir,compile=not a.preflight);simulation=build_simulation(out,compile=not a.preflight)
 summary=dict(histories=len(cases),commands=sum(len(c['rows'])for c in cases),input_bytes=len(raw),input_sha256=hashlib.sha256(raw).hexdigest(),units=len(UNITS),protocol=protocol,proof_sha256={str(p.relative_to(PLUGIN)):digest(p)for p in OWNED},production_sha256={p.name:digest(p)for p in PRODUCTION},ranges=ranges,limitations=__doc__)
 if a.preflight:(out/'owner-freeze.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2));return
 expected=subprocess.check_output([str(reference),str(a.assets.resolve())],input=raw);(out/'reference.bin').write_bytes(expected)
 actual=subprocess.check_output([str(simulation),str(a.simulation_package.resolve())],input=raw);(out/'simulation.bin').write_bytes(actual)
 if expected!=actual:
  at=next((n for n,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));report=dict(first_byte=at,first_word=at//4,reference_bytes=len(expected),simulation_bytes=len(actual),reference_hex=expected[max(0,at-16):at+32].hex(),simulation_hex=actual[max(0,at-16):at+32].hex());(out/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
 covered=coverage(decode(expected,cases),cases);result=dict(**summary,passed=True,reference_revision=REFERENCE_REVISION,exact_bytes=len(expected),output_sha256=hashlib.sha256(expected).hexdigest(),coverage=covered);(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
