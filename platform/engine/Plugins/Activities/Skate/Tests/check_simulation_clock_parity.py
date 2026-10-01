#!/usr/bin/env python3
"""Complete unchanged host clock.rs, ordered requests and exact error strings.

Only root builds/executes under atelier.safety. --preflight stages/hash-audits
without compiling or running either numerical probe.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
import math
from pathlib import Path
import random
import re
import shutil
import struct
import subprocess
import tarfile
import check_climbing_core_parity as wire
from session_parity import PLUGIN,REFERENCE_REVISION,digest
CODE=wire.CODE
NORMAL=0x3c888889
def value(w):return struct.unpack('<f',wire.word(w))[0]
def corpus():
    rng=random.Random(0x82857ec8);histories=[]
    def add(label):
        row=dict(label=label,commands=[]);histories.append(row);return row['commands']
    def command(c,op,words=(),label=''):c.append(dict(op=op,words=list(words),label=label))
    slow=wire.bits(1/35.4);fast=wire.bits(1/90)
    c=add('canonical default/End/Begin order and expiration')
    command(c,2,label='default wrapping decrement');command(c,0)
    command(c,1,[slow,1]);command(c,2);command(c,2);command(c,2)
    for n in range(32):
        command(c,3,[2,NORMAL,n,slow,1],'End then new Begin');command(c,2);command(c,2)
        command(c,3,[2,slow,17,NORMAL,17],'Begin then End');command(c,2)
        command(c,3,[3,slow,17,0,0,fast,2],'first failed request retains prior ordered writes');command(c,2)
        command(c,3,[0], 'empty ordered queue')
    for ticks in(0,1,2,17,178,179,180,181,0x7ffffffe,0x7fffffff,0x80000000,0x80000001,0xfffffffe,0xffffffff):
        c=add('ticks raw bits '+hex(ticks));command(c,1,[slow,ticks]);command(c,2)
        command(c,4,[178]);command(c,2);command(c,2);command(c,2)
        command(c,1,[NORMAL,ticks]);command(c,2)
    c=add('reciprocal rounding frequency/timer saturation boundaries')
    for frequency in(1,2,3,35,60,90,100,100000,9999999,10000000,10000001,10000002,2147483520,2147483647,2147483648,2147483904):
        midpoint=wire.bits(1/frequency)
        for raw in range(midpoint-3,midpoint+4):command(c,1,[raw,rng.getrandbits(32)],'frequency '+str(frequency))
    for raw in range(wire.bits(2)-4,wire.bits(2)+8):command(c,1,[raw,1],'lower frequency .5 reciprocal boundary')
    c=add('exact Display invalid timestep raw bits, prior owner retention')
    raw_values=[0,0x80000000,1,0x80000001,0x007fffff,0x807fffff,0x00800000,0x80800000,0x7f7fffff,0xff7fffff,0x7f800000,0xff800000,0x7fc12345,0xffc01234,0x7f812345,0xff812345]
    for f in(2.000001,3,7.137,99.731,1e5,1e6,1e7,1e10,1e20,1e30,1e-10,1e-15,1e-30,-.1,-.137,-.317,-.731,-1.137,-9.999999,-10,-100000.137,-10000000.731):
        w=wire.bits(f)
        for delta in(-2,-1,0,1,2):raw_values.append((w+delta)&0xffffffff)
    raw_values += [rng.getrandbits(32)|0x80000000 for _ in range(2048)]
    raw_values += [wire.bits(10**rng.uniform(1,38)*(1+rng.random()))for _ in range(256)]
    for raw in raw_values:
        command(c,1,[slow,17],'retained prior actual request');command(c,1,[raw,rng.getrandbits(32)],'independent original f32 Display oracle')
    c=add('source 180 hardcoded default and signed tick interpretation')
    for raw in(0,0x80000000,0xffffffff):
        command(c,1,[slow,raw]);command(c,4,[179]);command(c,2);command(c,2)
    c=add('appended genuine integer frequencies and FinishTick reset witnesses')
    for frequency in(5,7,11,24,30,59,61,120,360,1000):
        midpoint=wire.bits(1/frequency)
        for raw in range(midpoint-1,midpoint+2):
            command(c,1,[raw,1],'appended frequency '+str(frequency))
            command(c,2,label='appended retained nonnormal period')
            command(c,2,label='appended expiration restores original normal period')
    return histories
def encode(histories):return wire.word(len(histories))+b''.join(wire.word(len(h['commands']))+b''.join(wire.word(c['op'])+b''.join(wire.word(w)for w in c['words'])for c in h['commands'])for h in histories)
class Reader:
    def __init__(self,b):self.b=b;self.at=0
    def word(self):w=struct.unpack_from('<I',self.b,self.at)[0];self.at+=4;return w
    def owner(self):ticks=self.word();period=self.word()|(self.word()<<32);return ticks,period
    def status(self):okay=self.word();n=self.word();error=self.b[self.at:self.at+n].decode();self.at+=n;return okay,error
def coverage(raw,histories):
    r=Reader(raw);assert r.word()==len(histories);counts=Counter();errors=Counter();periods=set();counters=set();partial=0;failure_retention=0;negative=0;finite_text=0;expiry=0;default_wrap=0;order=0
    for h in histories:
        old=r.owner();assert old==(0,16666600);assert r.word()==len(h['commands'])
        for c in h['commands']:
            op=r.word();assert op==c['op'];okay,error=r.status();current=r.owner();counts[op]+=1;periods.add(current[1]);counters.add(current[0]);errors[error]+=1
            if not okay:
                assert error
                if op==1:assert current==old;failure_retention+=1
                elif op==3:assert current==(18,28571400);partial+=1
                if error.startswith('Invalid simulation-rate request: '):
                    text=error.split(': ',1)[1];negative+=text.startswith('-');finite_text+=text not in('NaN','inf','-inf')
                    assert 'e'not in text,'Rust Display uses decimal notation'
            else:assert not error
            if op==2:
                assert current[0]==(old[0]-1)&0xffffffff
                if old[0]==0:default_wrap+=1;assert current[0]==0xffffffff
                if current[0]==0:expiry+=1;assert current[1]==16666600
            if c['label']=='End then new Begin':order+=1;assert current==(2,28571400)
            if c['label']=='Begin then End':order+=1;assert current==(0,16666600)
            old=current
    assert r.at==len(raw)
    assert set(counts)=={0,1,2,3,4}and partial==32 and order==64 and failure_retention>1800
    assert default_wrap>30 and expiry>40 and len(periods)>12 and len(counters)>12
    assert finite_text>1800 and negative>1800 and any('NaN'in e for e in errors)and any('zero timer period'in e for e in errors)
    return dict(operations=dict(counts),errors=dict(errors),ordered_prior_writes_retained_at_failure=partial,failed_apply_retained_all_owner_fields=failure_retention,ordered_End_Begin_witnesses=order,default_counter_wrapping=default_wrap,normal_period_reset=expiry,distinct_integer_periods=len(periods),distinct_counter_values=len(counters),finite_exact_Display_diagnostics=finite_text,negative_Display_diagnostics=negative)
def prepare(output,histories):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip());relative=(PLUGIN/'ThirdParty/skate-runtime').relative_to(root).as_posix();archive=subprocess.check_output(['git','archive',f'{REFERENCE_REVISION}:{relative}'],cwd=root)
    original=output/'reference-source';snapshot=output/'native-source'
    for path in(original,snapshot):
        if path.exists():shutil.rmtree(path)
        path.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive))as stream:stream.extractall(original,filter='data')
    originals={p.relative_to(original).as_posix():digest(p)for p in sorted(original.rglob('*.rs'))};crate=original/'simulation-clock';(crate/'src').mkdir(parents=True)
    (crate/'Cargo.toml').write_text('[package]\nname="simulation-clock-reference"\nversion="0.1.0"\nedition="2024"\n[workspace]\n[dependencies]\nskate-core={path="../crates/skate-core"}\n')
    shutil.copy2(original/'atelier-host/Cargo.lock',crate/'Cargo.lock');body=(original/'crates/skate-host/src/physics/clock.rs').read_bytes();getter=b'\nimpl SimulationClock{pub(super)fn migration_ticks(&self)->u32{self.ticks_until_reset}}\n';(crate/'src/clock.rs').write_bytes(body+getter);assert(crate/'src/clock.rs').read_bytes()[:len(body)]==body
    shutil.copy2(PLUGIN/'Tests/Reference/simulation_clock_probe.rs',crate/'src/main.rs')
    pending=['SimulationClock.h'];visited=set()
    while pending:
        name=pending.pop()
        if name in visited:continue
        visited.add(name);text=(CODE/name).read_text();shutil.copy2(CODE/name,snapshot/name)
        pending += re.findall(r'^#include "([^\"]+)"',text,flags=re.M)
    shutil.copy2(CODE/'SimulationClock.cpp',snapshot/'SimulationClock.cpp');shutil.copy2(PLUGIN/'Tests/Native/simulation_clock_probe.cpp',snapshot/'simulation_clock_probe.cpp')
    raw=encode(histories);prior=encode(histories[:-1])
    assert len(histories[:-1])==18 and sum(len(h['commands'])for h in histories[:-1])==5370
    assert hashlib.sha256(prior).hexdigest()=='02a37fabfc0ca7fe339ec16cb89b7927fb63c56c4da17424688a0c464e86b629'
    assert raw[4:len(prior)]==prior[4:],'All original eighteen records/5,370 command bytes must remain verbatim'
    (output/'input.bin').write_bytes(raw);(output/'cases.json').write_text(json.dumps(histories,indent=2)+'\n')
    report=dict(preserved_original_corpus=dict(histories=18,commands=5370,input_bytes=len(prior),input_sha256=hashlib.sha256(prior).hexdigest(),verbatim_record_bytes=len(prior)-4,verbatim_record_prefix_sha256=hashlib.sha256(raw[4:len(prior)]).hexdigest(),outer_count_only_changed_for_append=True),reference_revision=REFERENCE_REVISION,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,whole_original_clock_sha256=hashlib.sha256(body).hexdigest(),original_clock_prefix_bytes=len(body),read_only_ticks_observer_sha256=hashlib.sha256(getter).hexdigest(),generated_clock_sha256=digest(crate/'src/clock.rs'),immutable_native_sources={p.name:digest(p)for p in sorted(snapshot.iterdir())},reference_probe_sha256=digest(crate/'src/main.rs'),input_sha256=digest(output/'input.bin'),histories=len(histories),commands=sum(len(h['commands'])for h in histories),scope='Complete unchanged original clock.rs executes; only a read-only private tick-counter observer is appended. Ordered ApplyRequests oracle invokes original Apply in order and stops at the first original error. Exact f32 Display strings, integer period arithmetic, Rust saturating cast edge, signed tick interpretation and all retained fields are compared. No frame/physics clock is simulated in parallel.')
    (output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');return original,crate,snapshot,report
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);p.add_argument('--preflight',action='store_true');a=p.parse_args();output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    histories=corpus();original,crate,snapshot,report=prepare(output,histories)
    if a.preflight:print(json.dumps(dict(preflight='PASS',histories=len(histories),commands=report['commands'],input_bytes=len(encode(histories)),input_sha256=report['input_sha256'])));return
    subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(crate/'Cargo.toml'),'--target-dir',str(a.target_dir.resolve()),'--bin','simulation-clock-reference'],check=True);reference=output/'simulation-clock-reference';shutil.copy2(a.target_dir.resolve()/'release/simulation-clock-reference',reference)
    candidate=output/'simulation-clock-native';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),str(snapshot/'SimulationClock.cpp'),str(snapshot/'simulation_clock_probe.cpp'),'-o',str(candidate)],check=True)
    for relative,expected in report['original_source_sha256'].items():assert digest(original/relative)==expected
    assert digest(crate/'src/clock.rs')==report['generated_clock_sha256'];raw=(output/'input.bin').read_bytes();values=[]
    for binary,label in((reference,'reference'),(candidate,'native')):
        run=subprocess.run([str(binary)],input=raw,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True);(output/(label+'.bin')).write_bytes(run.stdout);(output/(label+'.stderr')).write_bytes(run.stderr);values.append(run.stdout)
    if values[0]!=values[1]:
        offset=next((i for i,(x,y)in enumerate(zip(*values))if x!=y),min(map(len,values)));(output/'first-divergence.json').write_text(json.dumps(dict(byte_offset=offset,reference_bytes=len(values[0]),native_bytes=len(values[1])),indent=2)+'\n');raise AssertionError('SimulationClock first mismatch at '+str(offset))
    proof=coverage(values[0],histories);result=dict(result='PASS',histories=len(histories),commands=report['commands'],exact_bytes=len(values[0]),sha256=hashlib.sha256(values[0]).hexdigest(),coverage=proof);(output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
