#!/usr/bin/env python3
"""Exact frozen Ground entry, future-deck, manual body writes and output leaves.

Compile only through the shared render lock/memory guard. Full original modules
remain unchanged; manual bodies resolve each read/write, including shared slots.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import random
import re
import shutil
import struct
import subprocess
import tarfile
from check_ground_state_parity import FIELDS,STATE_WORDS
PLUGIN=Path(__file__).resolve().parents[1]
REFERENCE_REVISION='46513a6'
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def floats(values):return list(map(bits,values))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def corpus():
    rng=random.Random(0x82d37604);records=[];cases=[]
    def vec(n=4,scale=3):return [rng.uniform(-scale,scale) for _ in range(n)]
    def add(op,values,label,**meta):
        cases.append(dict(index=len(cases),op=op,label=label,**meta));records.append([op]+values)
    for _ in range(768):
        normal=vec();velocity=vec();forward=vec()
        add(0,floats(normal+velocity),'entry angular actual vector projection')
        add(1,floats(velocity[:3]+normal+forward),'entry speed normal rejection and ordered minimum')
        add(2,floats(velocity+vec()+normal+[rng.uniform(.1,100),rng.uniform(-2,2),rng.uniform(-3,3)]),'landing force exact tag19 producer')
    for normal in ([0.,1.,0.,0.],[0.,0.,0.,0.],[-0.,0.,-0.,1.],[.5,.5,.5,-.5]):
        for word in (0,0x80000000,1,0x80000001,0x00800000,0x80800000,0x3f800000,0xbf800000):
            value=struct.unpack('<f',struct.pack('<I',word))[0]
            add(0,floats(normal+[value,-value,value,-value]),'entry signed zero and subnormal lanes')
            add(1,floats([value,-value,value]+normal+[1.,0.,0.,-1.]),'entry speed signed zero and subnormal lanes')
    for count in (0,1,2,20,21):
        for pushing in (0,1):
            for manual in (0,1):
                for dt in (0.,-0.,1/60,.137):
                    q=[]
                    for j in range(count):q+=[100+j]+floats(vec(6,1000))
                    add(3,[count]+q+floats([8.137,dt]+vec())+[pushing,manual],'future deck ordered force sum retained queue',queue=count,pushing=pushing,manual=manual)
    for alias in (False,True):
        for previous in (100,200,503):
            for reversed in (0,1):
                for contacts in range(4):
                    for balance in (0.,-0.,.137,-.731):
                        for fail in range(8):
                            mapping=[0,1,2,3,4,5,6] if not alias else [0,0,0,0,0,0,0]
                            v=floats(vec(28));state=floats(vec(5));flags=(reversed<<20);contact_flags=((contacts&1)<<26)|((contacts>>1)<<27)
                            data=state+[previous]+floats([.317,balance,.25,1.,-.5,.137])+[flags,contact_flags]+mapping+v+[fail,1]
                            add(4,data,'manual entry partial writes and live aliased bodies',previous=previous,balance_bits=bits(balance),contacts=contacts,reversed=reversed,fail=fail,alias=alias,entry=1)
    for reversed in (0,1):
        for contacts in range(4):
            data=floats([1.,2.,3.,4.,5.])+[100]+floats([.317,.731,.25,1.,-.5,.137])+[reversed<<20,((contacts&1)<<26)|((contacts>>1)<<27)]+list(range(7))+floats(vec(28))+[0,0]
            add(4,data,'direct manual removal independent of entry branch',previous=100,balance_bits=bits(.731),contacts=contacts,reversed=reversed,fail=0,alias=False,entry=0)
    def state(seed):
        words=[]
        for kind,name in FIELDS:
            if kind=='v':words+=floats(vec())
            elif kind=='f':words+=floats(vec(1))
            elif kind=='b':words.append((seed>>(len(words)%10))&1)
            else:words.append(rng.getrandbits(32))
        assert len(words)==STATE_WORDS
        return words
    # Relevant boolean changes, both conditional-write branches and
    # exact threshold equality around the strict push/mode speed comparisons.
    for seed in range(1024):
        timer=(0.,-0.,.137,-.731)[seed%4]
        speed=(3.,struct.unpack('<f',struct.pack('<I',bits(3.)-1))[0],struct.unpack('<f',struct.pack('<I',bits(3.)+1))[0])[seed%3]
        axis=([0.,1.,0.,.137],[.25,-.5,.731,-.137],[0.,0.,0.,0.])[seed%3]
        flags=((seed&1)*0x00400000,(seed&2)*0x1000,(seed>>2)&1)
        add(5,state(seed)+floats(axis+vec()+[speed,speed,timer,.731])+list(flags)+floats([1.,2.,3.]),'complete output flags conditional writes strict equality',timer_bits=bits(timer))
    for word in (0,0x80000000,1,0x80000001,0x007fffff,0x807fffff,0x00800000,0x80800000):
        for lane in range(4):
            velocity=floats([1.,2.,3.,4.]);velocity[lane]=word
            add(5,state(lane)+floats([0.,1.,0.,0.])+velocity+floats([1.,1.,-0.,.137])+[0x00400000,0x2000,1]+floats([1.,2.,3.]),'output signed zero/subnormal per lane',timer_bits=bits(-0.))
    words=[len(records)]+[w for record in records for w in record]
    return struct.pack('<'+'I'*len(words),*words),cases

def build(output):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip());relative=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-core/src').relative_to(root).as_posix()
    revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip();archive=subprocess.check_output(['git','archive',f'{revision}:{relative}'],cwd=root);source=output/'reference-source'
    if source.exists():shutil.rmtree(source)
    source.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:stream.extractall(source,filter='data')
    originals={p.relative_to(source).as_posix():digest(p) for p in sorted(source.rglob('*.rs'))};probe=PLUGIN/'Tests/Reference/ground_lifecycle_helpers_probe.rs';main=source/'ground-lifecycle-helpers.rs';main.write_text((source/'lib.rs').read_text()+probe.read_text());reference=output/'reference'
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():assert digest(source/name)==expected,name
    simulation=PLUGIN/'Source/AtelierSkate/Private/Simulation';snapshot=output/'simulation-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();units=('SimulationMath','RigidBody','ForceQueue','Manual','GroundState','GroundMotion','GroundOutput')
    for unit in units:
        for ext in ('h','cpp'):shutil.copy2(simulation/f'{unit}.{ext}',snapshot/f'{unit}.{ext}')
    pending=list(snapshot.iterdir());seen=set()
    while pending:
        path=pending.pop()
        if path.name in seen:continue
        seen.add(path.name)
        for name in re.findall(r'^#include "([^"\n]+)"',path.read_text(),re.M):
            target=snapshot/name
            if not target.exists():shutil.copy2(simulation/name,target)
            pending.append(target)
    cpp_probe=PLUGIN/'Tests/Simulation/ground_lifecycle_helpers_probe.cpp';shutil.copy2(cpp_probe,snapshot/cpp_probe.name);cpp=output/'cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{u}.cpp') for u in units],str(snapshot/cpp_probe.name),'-o',str(cpp)],check=True)
    (output/'provenance.json').write_text(json.dumps(dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,simulation_source_sha256={p.name:digest(p) for p in snapshot.iterdir()},probe_sha256={p.name:digest(p) for p in (probe,cpp_probe)},reference_binary_sha256=digest(reference),cpp_binary_sha256=digest(cpp)),indent=2)+'\n')
    return cpp,reference

def coverage(data,cases):
    w=struct.unpack('<'+'I'*(len(data)//4),data);at=0;counts=Counter();partial=Counter();orders=set();gates=Counter();output_flags={}
    for c in cases:
        index,op,n=w[at:at+3];assert (index,op)==(c['index'],c['op']);c.update(first_word=at,output_words=n+3);payload=w[at+3:at+3+n];at+=3+n;counts[op]+=1
        if op==2:assert n==7 and payload[0]==19
        elif op==3:
            present=bool(payload[0]);assert present==(not c['pushing'] and not c['manual']);cursor=4 if present else 1
            assert payload[cursor]==c['queue'] and n==cursor+1+7*c['queue'];gates['future_present' if present else 'future_preserved']+=1
        elif op==4:
            ok=bool(payload[0]);calls=payload[6];size=payload[7];cursor=8;end=cursor+size;sequence=[];writes=[]
            while cursor<end:
                event=payload[cursor];cursor+=1
                if event in (0,2):part=payload[cursor];cursor+=5;sequence.append((event,part));writes.extend([part] if event==2 else [])
                else:assert event==1;cursor+=8;sequence.append((event,))
            assert cursor==end and n==end+28
            bypass=c['balance_bits'] in (0,0x80000000) or (c['entry'] and c['previous']==100)
            if bypass:assert calls==0 and not sequence and ok;gates['manual_bypass']+=1
            else:
                first,second=((c['contacts']&1),(c['contacts']>>1)) if c['reversed'] else ((c['contacts']>>1),(c['contacts']&1))
                expected=[6]+([0,1,4] if first else [])+([2,3,5] if second else [])
                if c['fail'] and c['fail']<=len(expected):
                    assert not ok and calls==c['fail'] and writes==expected[:calls-1];partial[c['fail']]+=1
                else:assert ok and calls==len(expected) and writes==expected
                orders.add(tuple(writes));gates['manual_alias' if c['alias'] else 'manual_distinct']+=1
        elif op==5:
            projection=payload[2];assert bool(projection)==(c['timer_bits'] in (0,0x80000000));gates['output_projected' if projection else 'output_untouched']+=1
            cursor=3+(5 if projection else 0)
            flags=list(payload[:2])+list(payload[cursor:cursor+3])+[payload[cursor+10]]
            cursor+=11
            flags+=list(payload[cursor+2:cursor+5]);manual_present=payload[cursor+4]
            cursor+=5+(1 if manual_present else 0)
            flags+=list(payload[cursor:cursor+5]);assert cursor+5==n
            for k,v in enumerate(flags):output_flags.setdefault(k,set()).add(v)
    assert at==len(w) and set(counts)==set(range(6))
    assert set(partial)==set(range(1,8)) and len(orders)>=5,(partial,orders)
    assert all(gates[key]>0 for key in ('future_present','future_preserved','manual_bypass','manual_alias','manual_distinct','output_projected','output_untouched'))
    assert all(values=={0,1} for values in output_flags.values()),output_flags
    return dict(operations=dict(counts),partial_failures=dict(partial),write_orders=len(orders),gates=dict(gates),output_boolean_variants={k:len(v) for k,v in output_flags.items()})
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    inputs,cases=corpus();(output/'input.bin').write_bytes(inputs);cpp,reference=build(output);expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(cpp)],input=inputs);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual)
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));report=dict(passed=False,first_word=first//4,reference_size=len(expected),cpp_size=len(actual));(output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    proof=coverage(expected,cases);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');result=dict(passed=True,cases=len(cases),exact_words=len(expected)//4,coverage=proof,input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),comparison='Every helper result, complete conditional output record, retained force queue, five manual fields, ordered per-body reads/projections/writes, aliases and partial-failure storage; exact words; unchanged original modules.',limitations='Finite authored/random frames plus signed zero/subnormal lanes. Manual projection uses the original required shared numerical adapter. Full active Ground input/state/physical lifecycle remains separate.')
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
