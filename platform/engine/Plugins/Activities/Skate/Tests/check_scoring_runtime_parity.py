#!/usr/bin/env python3
"""Whole pinned scoring recognition and accounting with retained-owner histories.

The coordinator alone compiles/runs under the shared render guard. Completed
physical/conditioner inputs are explicit; no score result or collector callback
is supplied. The complete original host implementation remains byte identical.
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
from camera_reference_build import frozen_sources
from check_gesture_parity import PLUGIN,converter
from check_scoring_data_parity import schema,SCORABLE,COLLECTOR,TUNING
from check_animation_trees_parity import name
from session_parity import digest,REFERENCE_REVISION

CODE=PLUGIN/'Source/AtelierSkate/Private/Simulation'
UNITS=('SimulationMath','NameId','Settings','StockSettingsReader','AnimationName','ScoringCatalog','ScoringData',
       'ScoringCore','ScoringTimer','ScoringCarrier','ScoringSession','ScoringRuntime','ScoringRuntimeAdvance')
HOST='crates/skate-host/src/scoring_runtime.rs'
CORE='crates/skate-core/src/scoring.rs'
OBSERVER=b'''
impl ScoreHolder {
 pub fn migration_runtime_words(&self)->Vec<u32>{
    let s=&self.snapshot;let mut out=vec![s.completed_lines.to_bits(),s.line.to_bits(),s.accumulated.to_bits(),s.last_reward.to_bits(),s.general_pending.to_bits(),s.fingerflip_pending.to_bits(),s.grind_reward.to_bits()];
    for a in [self.repetitions,self.sequence_history]{out.extend(a.map(|v|v as i32 as u32));}out.extend(self.type_history.map(|v|v as i32 as u32));out.push(self.pending_sequence as u32);out.push(self.suppressed as u32);out
 }
}
'''
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def floats(v):return [bits(x)for x in v]
def frame(tick=0,category=1,state=100,identifier=None,grind=-1,flags=0,position=(0,0,0),velocity=(0,0,5),heading=0,
          switch=False,fakie=False,nollie=False,flip=False,suspend=False,teleport=False,revert=False,landing=False,kind=0,side=0,spin=0,dt=1/60):
    encoded=name(identifier)if identifier else[0]*5
    record=[tick,bits(dt),category,state,int(bool(identifier)),*encoded,grind,flags,*floats(position),*floats(velocity),*floats((math.sin(heading),0,math.cos(heading))),
            switch,fakie,nollie,flip,suspend,teleport,revert,landing,kind,bits(side),bits(spin)]
    assert len(record)==32;return [0,*[int(x)&0xffffffff for x in record]]

def corpus():
    identifiers,_,_=schema();cases=[]
    def add(label,commands):cases.append(dict(label=label,commands=commands))
    for stance in range(4):
        commands=[];tick=0
        for n in range(40):
            for cat in (1,2,3,6,7,0,4,5):
                for k in range(12):
                    identifier=identifiers[(n*13+k)%332][0]
                    commands.append(frame(tick,cat,600 if n%7==0 else{1:100,2:201,3:400,6:500,7:501,0:701,4:300,5:702}[cat],identifier,
                        grind=(n*7+k)%332,flags=(0xc0000000,0x0c000000,0x02000000,0x30000000,0x01000000)[k%5],
                        position=(tick*.0137,math.sin(k*.317),tick*.0317),heading=tick*.137,
                        switch=bool(stance&1),fakie=bool(stance&2),nollie=k%3==0,flip=k%5==0,suspend=k%7==0,teleport=cat==5 and k==0,revert=k%4==0,
                        landing=k==0,kind=n%4,side=3.731,spin=.731));tick=(tick+1)&0xffffffff
        add('every collector transition and stance '+str(stance),commands)
    # Each actual catalog identity is supplied as descriptor and as grind id.
    # Missing authored definitions must fail after source-ordered prior writes.
    for cat in (1,2,3,6,7):
        commands=[]
        for i,(identifier,_,_)in enumerate(identifiers):
            for k in range(4):commands.append(frame(i*10+k,cat,identifier=identifier,grind=i,flags=0xfe000000,position=(i*.317,k*.173,i*.137),heading=k*.317,revert=k==2))
            commands.append(frame(i*10+4,0,teleport=i%7==0))
        add('all 332 catalog identities in category '+str(cat),commands)
    # Full delayed announcement, grab chains/conversions, metric collectors,
    # landing countdown, idle settlement, combo/line timers and suppression.
    grabs=[row[0]for row in identifiers if int(row[1])==2]
    air=[row[0]for row in identifiers if int(row[1])==3]
    commands=[];tick=0
    for n in range(160):
        commands.append([2,int(n%11==0)])
        for k in range(24):
            commands.append(frame(tick,1,identifier=identifiers[60][0],flags=0xe2000000 if k<12 else 0x52000000,position=(tick*.01731,0,tick*.137),revert=k%8==0));tick+=1
        for k in range(48):
            identifier=(grabs[(n+k)%len(grabs)]if k<8 else grabs[n%len(grabs)])if n%2 else air[(n+k//8)%len(air)]
            commands.append(frame(tick,2,201,identifier,position=(tick*.01731,math.sin(k*math.pi/48)*2.731,tick*.137),heading=k*.1731,switch=n%3==0,fakie=n%4==0,flip=n%2!=0,suspend=k%13==0));tick+=1
        for k in range(10):commands.append(frame(tick+k,1,landing=k==0,kind=n%4,side=3.731,spin=.731,position=(tick*.01731,0,(tick+k)*.137)))
        tick+=10
    add('long retained delayed trick sequences and landing timers',commands)
    # Finite positions produce finite headings. Exceptional caller records
    # exercise source propagation and saturating degrees casts independently.
    exceptional=(0,0x80000000,1,0x80000001,0x7f7fffff,0xff7fffff,0x7f800000,0xff800000,0x7fc12345,0xffc12345,0x7f812345,0xff812345)
    commands=[]
    for field in (1,12,13,14,15,17,18,20,30,31):
        for w in exceptional:
            commands.append([1]);commands.append(frame(0,1,flags=0x88000000))
            for k in range(8):
                f=frame(k+1,2,201,grabs[0],position=(.317*k,.731*k,.137*k),heading=k*.317,landing=True,kind=1,side=.731,spin=.731);f[1+field]=w;commands.append(f)
            commands.extend(frame(10+k,1,landing=True,kind=1,side=.731,spin=.731)for k in range(4))
    add('IEEE callers after complete fresh constructors',commands)
    commands=[]
    for first in (0xfffffffc,0xfffffffd,0xfffffffe,0xffffffff):
        commands.append([1])
        for k in range(40):commands.append(frame((first+k)&0xffffffff,2,identifier=grabs[k%len(grabs)],heading=k*.317,suspend=k%5==0))
        commands.extend(frame(k,1)for k in range(5))
    add('tick wrap and retained chained grabs',commands)
    raw=[len(cases)]
    for case in cases:
        raw.append(len(case['commands']))
        for c in case['commands']:
            assert len(c)=={0:33,1:1,2:2}[c[0]];raw.extend(c)
    return struct.pack('<'+'I'*len(raw),*[int(x)&0xffffffff for x in raw]),cases

def build_reference(output,target,compile=True):
    source,report=frozen_sources(output);observed=output/'observed-source'
    if observed.exists():shutil.rmtree(observed)
    shutil.copytree(source,observed);original=source/CORE;p=observed/CORE;p.write_bytes(original.read_bytes()+OBSERVER)
    template=PLUGIN/'Tests/Reference/scoring_runtime_probe.rs';raw=template.read_bytes();assert raw.count(b'// ORIGINAL_SCORING_RUNTIME')==1
    body=(source/HOST).read_bytes();generated=raw.replace(b'// ORIGINAL_SCORING_RUNTIME',body);assert body in generated
    crate=observed/'atelier-host';(crate/'src/migration_probe.rs').write_bytes(generated)
    cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text()+'''\nskate-core={path="../crates/skate-core"}\nskate-data={path="../crates/skate-data"}\n[[bin]]\nname="scoring-runtime-reference"\npath="src/migration_probe.rs"\n''')
    binary=output/'scoring-runtime-reference'
    if compile:
        subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(cargo),'--target-dir',str(target.resolve()),'--bin','scoring-runtime-reference'],check=True)
        shutil.copy2(target.resolve()/'release/scoring-runtime-reference',binary)
    for rel,sha in report['original_source_sha256'].items():
        assert digest(source/rel)==sha;assert(observed/rel).read_bytes()[:(source/rel).stat().st_size]==(source/rel).read_bytes(),rel
    report.update(host_runtime_sha256=hashlib.sha256(body).hexdigest(),generated_probe_sha256=hashlib.sha256(generated).hexdigest(),holder_observer_sha256=hashlib.sha256(OBSERVER).hexdigest(),observed_holder_sha256=digest(p),binary_sha256=digest(binary)if compile else None,
                  scope='Complete original host Runtime and actual original data/core dependencies. Only read-only holder observer appended; all production methods and original source prefixes unchanged.')
    (output/'reference-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return binary

def build_simulation(output,compile=True):
    snapshot=output/'simulation-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir()
    for p in [*CODE.glob('*.h'),*[CODE/(u+'.cpp')for u in UNITS],PLUGIN/'Tests/Simulation/scoring_runtime_probe.cpp']:shutil.copy2(p,snapshot/p.name)
    provenance={p.name:digest(p)for p in snapshot.iterdir()};(output/'simulation-provenance.json').write_text(json.dumps(dict(units=UNITS,source_sha256=provenance),indent=2)+'\n');binary=output/'scoring-runtime-simulation'
    if compile:subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'scoring_runtime_probe.cpp'),'-o',str(binary)],check=True)
    for n,sha in provenance.items():assert digest(snapshot/n)==sha
    return binary

class Reader:
    def __init__(self,raw):assert len(raw)%4==0;self.words=struct.unpack('<'+'I'*(len(raw)//4),raw);self.at=0
    def word(self):v=self.words[self.at];self.at+=1;return v
    def take(self,n):v=self.words[self.at:self.at+n];assert len(v)==n;self.at+=n;return v
    def string(self):return bytes(self.take(self.word())).decode()
    def state(self):
        start=self.at;length=self.word();end=self.at+length;collector=self.word();carriers=[]
        for _ in range(4):carriers.append(self.take(14)if self.word()else None)
        metrics=self.take(12);started=self.take(4);positions=self.take(6);heading=self.take(5);repetition=self.word();chain=self.word();air=self.take(5);timers=self.take(4);revert=self.word()if self.word()else None
        active=self.word();score=self.word();name=self.string();stance=self.take(4);flags=self.take(5);holder=self.take(687);session=self.take(5);assert self.at==end
        return dict(start=start,end=end,collector=collector,carriers=carriers,metrics=metrics,started=started,positions=positions,heading=heading,repetition=repetition,chain=chain,air=air,timers=timers,revert=revert,active=active,score=score,name=name,stance=stance,flags=flags,holder=holder,session=session)

def decode(raw,cases):
    r=Reader(raw);assert r.word()==len(cases);out=[]
    for case in cases:
        assert r.word()==len(case['commands']);prior=r.state();rows=[]
        for command in case['commands']:
            assert r.word()==command[0];error=None if r.word()else r.string();state=r.state();rows.append(dict(error=error,state=state,prior=prior));prior=state
        out.append(rows)
    assert r.at==len(r.words);return out

def coverage(frames,cases):
    counts=Counter();errors=Counter();collectors=set();names=set();scorables=set();paths=Counter()
    for rows,case in zip(frames,cases):
        for row,command in zip(rows,case['commands']):
            s=row['state'];p=row['prior'];counts[command[0]]+=1;collectors.add(s['collector']);names.add(s['name'])
            for c in s['carriers']:
                if c:scorables.add(c[0]);paths['announced']+=bool(c[9]);paths['unannounced']+=bool(c[11])
            paths['new_trick']+=bool(s['flags'][2]);paths['modified_trick']+=bool(s['flags'][3]);paths['closed_on_bail']+=bool(s['flags'][4]);paths['clean_landing']+=bool(s['flags'][0]);paths['sketchy_landing']+=bool(s['flags'][1])
            paths['metric_accumulation']+=any(x!=bits(0)for x in s['metrics']);paths['landing_countdown']+=s['timers'][0]>0
            paths['published_sequence']+=s['holder'][3]!=p['holder'][3];paths['partial_error_writes']+=bool(row['error'])and s!=p
            paths['ground_multiple_slots']+=s['collector']==1 and sum(c is not None for c in s['carriers'])>1
            paths['suspended_air']+=command[0]==0 and command[3]==2 and command[26]!=0
            if row['error']:assert row['error'].startswith('Missing native scorable ');errors[row['error']]+=1
            if command[0]==1:assert s['collector']==0 and not s['active']and not s['name']and sum(s['holder'])==0
            if command[0]==2:assert s['holder'][686]==command[1]
    assert collectors==set(range(6))and set(counts)=={0,1,2}and len(scorables)>200 and len(names)>32
    for key in('announced','new_trick','modified_trick','closed_on_bail','clean_landing','sketchy_landing','metric_accumulation','landing_countdown','published_sequence','partial_error_writes','ground_multiple_slots','suspended_air'):assert paths[key]>0,(key,paths)
    assert errors
    return dict(operations=dict(counts),collectors=sorted(collectors),distinct_carrier_ids=len(scorables),distinct_publications=len(names),paths=dict(paths),exact_errors=dict(errors))

def prepare_settings(assets,output):
    complete=assets/'private/stock/skater-collections.json';data=json.loads(complete.read_text());categories={converter.name_id(v)for v in(SCORABLE,COLLECTOR,TUNING)}
    retained=[r for r in data['collections']if converter.name_id(r['class'])in categories];identities={(converter.name_id(r['class']),converter.name_id(r['key']))for r in retained}
    for r in retained:
        if r['parent']:assert(converter.name_id(r['class']),converter.name_id(r['parent']))in identities
    folder=output/'stock-assets';path=folder/'private/stock/skater-collections.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(dict(version=data['version'],collections=retained))+'\n');bank=output/'stock.simulation';bank.write_bytes(converter.encode_settings(path))
    full=output/'full-stock.simulation';full.write_bytes(converter.encode_settings(complete))
    (output/'settings-provenance.json').write_text(json.dumps(dict(complete_json_sha256=digest(complete),focused_json_sha256=digest(path),complete_simulation_sha256=digest(full),focused_simulation_sha256=digest(bank),complete_records=len(data['collections']),retained_records=len(retained),scope='All scoring definitions, inherited parents, fields and tuning retained unchanged in original order. One complete-bank session comparison audits omission of unrelated classes.'),indent=2)+'\n');return folder,bank,full

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in('assets','output','target-dir'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);raw,cases=corpus();(out/'input.bin').write_bytes(raw);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');folder,bank,full=prepare_settings(a.assets.resolve(),out)
    reference=build_reference(out/'reference',a.target_dir,not a.preflight);simulation=build_simulation(out,not a.preflight)
    if a.preflight:print(json.dumps(dict(histories=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(raw),input_sha256=hashlib.sha256(raw).hexdigest(),units=len(UNITS)),indent=2));return
    expected=subprocess.check_output([str(reference),str(folder)],input=raw);actual=subprocess.check_output([str(simulation),str(bank)],input=raw);(out/'reference.bin').write_bytes(expected);(out/'simulation.bin').write_bytes(actual);frames=decode(expected,cases)
    if expected!=actual:
        byte=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));failure=dict(byte=byte,word=byte//4,reference_bytes=len(expected),simulation_bytes=len(actual));(out/'first-divergence.json').write_text(json.dumps(failure,indent=2)+'\n');raise AssertionError(failure)
    count=len(cases[0]['commands']);subset=struct.pack('<II',1,count)+b''.join(struct.pack('<'+'I'*len(c),*c)for c in cases[0]['commands'])
    baseline_reference=subprocess.check_output([str(reference),str(a.assets.resolve())],input=subset);baseline_simulation=subprocess.check_output([str(simulation),str(full)],input=subset)
    focused_reference=subprocess.check_output([str(reference),str(folder)],input=subset);focused_simulation=subprocess.check_output([str(simulation),str(bank)],input=subset)
    assert baseline_reference==baseline_simulation==focused_reference==focused_simulation,'Complete versus focused bank session differs'
    result=dict(passed=True,reference_revision=REFERENCE_REVISION,histories=len(cases),commands=sum(len(c['commands'])for c in cases),exact_bytes=len(expected),output_sha256=hashlib.sha256(expected).hexdigest(),input_sha256=hashlib.sha256(raw).hexdigest(),full_bank_audit_bytes=len(baseline_reference),full_bank_audit_sha256=hashlib.sha256(baseline_reference).hexdigest(),coverage=coverage(frames,cases),scope='Complete pinned original host scoring recognition/collectors/conversions/metric/air/landing/sequence publication with original loaded data and score holder/carrier/timer/session owners. Every retained state, all 678 private history entries, timer, event and publication observed. Physical conditioner Frame inputs explicit; global frame dispatch remains separate.')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
