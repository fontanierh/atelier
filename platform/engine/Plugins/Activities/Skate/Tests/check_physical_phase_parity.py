#!/usr/bin/env python3
"""Exact whole phase buffers/exchange and retained COM filter comparison.

Compile and execute under the parent render guard. Both probes retain complete
source data, all command/event variants, tick failure side effects and all four
COM lanes. Original implementation bytes are independently frozen and hashed.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
from reference_build import build_probe
from session_parity import PLUGIN,REFERENCE_REVISION,digest

STATES=(100,101,102,103,104,105,200,201,202,300,400,401,402,403,404,405,500,501,502,503,600,601,602,700,701,702)
CODE=PLUGIN/'Source/AtelierSkate/Private/Simulation'
class Writer:
    def __init__(self):self.data=bytearray()
    def word(self,v):self.data.extend(struct.pack('<I',int(v)&0xffffffff))
    def u64(self,v):self.word(v);self.word(v>>32)
    def float(self,v):self.data.extend(struct.pack('<f',v))
    def floats(self,v):
        for x in v:self.float(x)
    def command(self,kind,index):
        self.word(kind)
        if kind in (0,1):self.word(index%2);self.floats((index*.137,-index*.071,3.17,.731,-.137,index*.317))
        elif kind==2:self.word(STATES[index%26])
        else:self.word(index%2);self.word((index//2)%2)
    def event(self,kind,index):
        self.word(kind)
        if kind==0:self.word(STATES[index%26]);self.word(STATES[(index+1)%26])
        elif kind==3:self.word(index%2)
    def snapshot(self,tick,index):
        self.u64(tick);self.word(STATES[index%26]);self.floats((.137,-.731,index*.017)*5);self.word(index%7);self.floats((.317,index*.03,-.113));self.word(index%2);self.word(index%3==0);self.word(index%5==0);self.word(4)
        for kind in range(4):self.event(kind,index)


def corpus():
    out=Writer();cases=[]
    for case,tick in enumerate((0,1,7,31,0xffffffff,0x100000000,0x8000000000000000,0xffffffffffffffff)):
        rows=[]
        def row(kind):w=Writer();w.word(kind);rows.append(w);return w
        for i in range(384):
            if i%11==0 or i%79==0:row(7)
            w=row(6);w.floats(((-1 if (i//17)%2 else 1)*(case+.137+i*.01731),.731+(i%13)*.131,(i%19)*.317,(-.0 if i==0 else (case+1)*.137+i*.01731)));w.floats((.317-(i%17)*.0371,-.731+(i%11)*.1731,.137*(i%23),(.0,-.317,1.731,-7.137)[i%4]+case*.071+i*.0137))
            if i%5==0:
                w=row(0);w.u64(tick if i%3 else (tick+1)&0xffffffffffffffff);w.command((i//5)%4,i)
            if i%7==0:
                w=row(1);w.u64(tick if i%3 else (tick-1)&0xffffffffffffffff)
            if i%11==0:
                for op in (2,3):w=row(op);w.u64(tick if i%3 else (tick+7)&0xffffffffffffffff);w.event((i//11)%4,i)
            if i%13==0:row(5).word(STATES[i%26])
            if i%17==0:
                # Exchange stores publication exactly without a synthetic tick
                # validation; the source camera validates it at consumption.
                w=row(4);w.snapshot((tick+i)&0xffffffffffffffff,i)
        for state in (*STATES,0,203,499,703,0xffffffff):row(8).word(state)
        cases.append((tick,[bytes(w.data) for w in rows]))
    out.word(len(cases))
    for tick,rows in cases:
        out.u64(tick);out.word(len(rows))
        for row in rows:out.data.extend(row)
    return bytes(out.data),cases


class Reader:
    def __init__(self,data):self.data,self.at=data,0
    def word(self):assert self.at+4<=len(self.data);v=struct.unpack_from('<I',self.data,self.at)[0];self.at+=4;return v
    def u64(self):return self.word()|(self.word()<<32)
    def words(self,n):return tuple(self.word() for _ in range(n))
    def string(self):n=self.word();v=self.data[self.at:self.at+n].decode();self.at+=n;return v
    def event(self):
        tag=self.word();assert tag<4;return (tag,*self.words(2 if tag==0 else 1 if tag==3 else 0))
    def command(self):
        tag=self.word();assert tag<4;return (tag,*self.words(7 if tag<2 else 1 if tag==2 else 2))
    def events(self):return [self.event() for _ in range(self.word())]
    def commands(self):return [self.command() for _ in range(self.word())]
    def snapshot(self):return dict(tick=self.u64(),state=self.word(),vectors=self.words(15),contacts=self.word(),prediction=self.words(3),flags=self.words(3),events=self.events())
    def owner(self):
        out=dict(command_tick=self.u64(),empty=self.word(),commands=self.commands(),event_tick=self.u64(),events=self.events(),exchange_tick=self.u64(),exchange_commands=self.commands(),exchange_events=self.events())
        out['output']=self.snapshot() if self.word() else None;out['com']=self.words(17);out['last']=self.words(12) if self.word() else None;return out


def coverage(data,cases):
    r=Reader(data);assert r.word()==len(cases);counts=Counter();positions=set();fourth=set();states=set();failures=[]
    for tick,rows in cases:
        assert r.u64()==tick and r.word()==len(rows);prior=r.owner()
        assert prior['empty'] and not prior['commands'] and not prior['events'] and prior['output'] is None and prior['com']==(0,)*17
        for raw in rows:
            kind=r.word();assert kind==struct.unpack_from('<I',raw)[0];okay=r.word();assert okay<2
            error=None if okay else r.string();counts[kind]+=1
            if kind==8:
                present=r.word();value=r.word()
                if present:
                    offset,category,grind=r.words(3);name=r.string();states.add(value)
                    assert value in STATES and offset%4==0 and category==(value//100)*100 and grind==(400<=value<=405) and name
                else:assert value not in STATES
            current=r.owner();assert current['command_tick']==current['event_tick']==current['exchange_tick']==tick
            if not okay:
                assert kind in (0,1,2,3);assert current==prior;failures.append(error)
            if kind==6:positions.add(current['com'][4:8]);fourth.add(current['com'][7]);assert current['com'][16]==1 and current['last'] is not None
            if kind==7:assert current['com']==(0,)*17
            if kind==0 and okay:assert len(current['commands'])==len(prior['commands'])+1 and current['commands'][:-1]==prior['commands'];counts[('command',current['commands'][-1][0])]+=1
            if kind==1 and okay:assert not current['commands'] and current['empty']
            if kind==2 and okay:assert current['events'][:-1]==prior['events'];counts[('event',current['events'][-1][0])]+=1
            if kind==3 and okay:assert current['exchange_events'][:-1]==prior['exchange_events']
            if kind==4:assert okay and current['output'] is not None;counts['unvalidated_tick_publications']+=current['output']['tick']!=tick
            if kind==5:assert okay and current['exchange_commands'][:-1]==prior['exchange_commands'] and current['exchange_commands'][-1][0]==2
            prior=current
    assert r.at==len(data),(r.at,len(data));assert states==set(STATES);assert len(failures)>128;assert len(positions)>128 and len(fourth)>128,(len(positions),len(fourth))
    assert all(counts[('command',i)]>0 and counts[('event',i)]>0 for i in range(4));assert counts['unvalidated_tick_publications']>64
    return dict(operation_counts={str(k):v for k,v in counts.items()},tick_failures=len(failures),position_variants=len(positions),fourth_lane_variants=len(fourth),all_state_identities=sorted(states))


def frozen_text(path):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip());relative=(PLUGIN/'ThirdParty/skate-runtime'/path).relative_to(root).as_posix()
    return subprocess.check_output(['git','show',f'{REFERENCE_REVISION}:{relative}'],cwd=root).decode()


def build_reference(output,target):
    cm_path='crates/skate-core/src/physics/centre_of_mass_filter.rs';cm=frozen_text(cm_path)
    arithmetic_path='crates/skate-core/src/physics/native_arithmetic.rs';arithmetic=frozen_text(arithmetic_path)
    host_path='crates/skate-host/src/physics.rs';host=frozen_text(host_path);begin=host.index('pub(crate) struct SimulationExchange {');end=host.index('\n#[cfg(test)]\nmod exchange_tests',begin);exchange=host[begin:end]
    assert exchange.count('impl SimulationExchange {')==1 and all(('fn '+name+'(') in exchange for name in ('new','emit_event','publish_output','output','events','request_state'))
    template=PLUGIN/'Tests/Reference/physical_phase_probe.rs';raw=template.read_text()
    assert raw.count('// @COMPLETE_COM_SOURCE@')==raw.count('// @COMPLETE_EXCHANGE_SOURCE@')==raw.count('// @COM_OBSERVER@')==raw.count('// @COMPLETE_ARITHMETIC_SOURCE@')==1
    observer='pub(super) fn observe(v:&CentreOfMassFilter,o:&mut super::Output){o.vector(v.velocity);o.vector(v.position);o.vector(v.position_velocity);o.vector(v.accumulated_error);o.word(v.position_valid as u32);}'
    generated=output/'physical-phase-reference.rs';generated.write_text(raw.replace('// @COMPLETE_ARITHMETIC_SOURCE@',arithmetic).replace('// @COMPLETE_COM_SOURCE@',cm).replace('// @COMPLETE_EXCHANGE_SOURCE@',exchange).replace('pub fn migration_observe(&self_not_used: &()) {} // @COM_OBSERVER@',observer))
    report=[]
    for path,whole,slice_,start,stop in ((cm_path,cm,cm,0,len(cm)),(arithmetic_path,arithmetic,arithmetic,0,len(arithmetic)),(host_path,host,exchange,begin,end)):
        assert whole[start:stop]==slice_;report.append(dict(source=path,original_sha256=hashlib.sha256(whole.encode()).hexdigest(),begin_byte=len(whole[:start].encode()),end_byte=len(whole[:stop].encode()),extracted_sha256=hashlib.sha256(slice_.encode()).hexdigest(),complete_production_methods=True))
    (output/'extraction-provenance.json').write_text(json.dumps(dict(extractions=report,template_sha256=digest(template),generated_sha256=digest(generated),boundary='Unchanged entire COM source including all methods; exact complete host SimulationExchange struct/impl. Core phase/state implementations are independently frozen linked originals; complete unchanged native_arithmetic source is compiled within the probe because its upstream module is private. Only representation observers are appended; no numerical methods or callbacks are substituted.'),indent=2)+'\n')
    return build_probe(output/'reference-build','physical-phase-reference',generated,target)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--target-dir',required=True,type=Path);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    reference=build_reference(output,args.target_dir);snapshot=output/'simulation-source';snapshot.mkdir(exist_ok=True)
    files=('SimulationMath.h','SimulationMath.cpp','PhysicalPhase.h','PhysicalPhase.cpp','CentreOfMassFilter.h','CentreOfMassFilter.cpp')
    hashes={}
    for name in files:shutil.copy2(CODE/name,snapshot/name);hashes[name]=digest(snapshot/name)
    probe=PLUGIN/'Tests/Simulation/physical_phase_probe.cpp';shutil.copy2(probe,snapshot/probe.name);hashes[probe.name]=digest(probe)
    simulation=output/'physical-phase-simulation';subprocess.run(['clang++','-std=c++17','-O2','-fno-exceptions','-ffp-contract=off','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/name) for name in ('SimulationMath.cpp','PhysicalPhase.cpp','CentreOfMassFilter.cpp','physical_phase_probe.cpp')],'-o',str(simulation)],check=True)
    data,cases=corpus();(output/'input.bin').write_bytes(data);expected=subprocess.check_output([str(reference)],input=data);actual=subprocess.check_output([str(simulation)],input=data)
    (output/'reference.bin').write_bytes(expected);(output/'simulation.bin').write_bytes(actual)
    if expected!=actual:
        at=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));failure=dict(byte=at,reference_bytes=len(expected),simulation_bytes=len(actual),reference_hex=expected[max(0,at-16):at+32].hex(),simulation_hex=actual[max(0,at-16):at+32].hex());(output/'first-divergence.json').write_text(json.dumps(failure,indent=2)+'\n');raise AssertionError(failure)
    proof=coverage(expected,cases)
    for name,sha in hashes.items():assert digest(snapshot/name)==sha
    report=dict(passed=True,reference_revision=REFERENCE_REVISION,cases=len(cases),operations=sum(len(rows) for _,rows in cases),bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),input_sha256=hashlib.sha256(data).hexdigest(),immutable_simulation_sha256=hashes,coverage=proof,boundary='Whole original phase buffers and host exchange, all four command/event variants, complete output snapshots, all26 state identities/helpers and full COM retained-state lifecycle. Coordinator, player state selection and physical-output production remain their own concrete owners.')
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':main()
