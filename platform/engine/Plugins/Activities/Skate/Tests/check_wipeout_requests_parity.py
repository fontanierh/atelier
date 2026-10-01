#!/usr/bin/env python3
"""Compare actual retained wipeout/runout requests with untouched Rust.

Run compilations and execution under the shared render lock and memory guard.
Request eligibility and the 34 reason/value histories are observed after every
operation; a request counter is not substituted by a count of unique reasons.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
from check_input_parity import Record,fbits,PLUGIN
from reference_build import build_probe

WORDS=73


def corpus():
    rng=random.Random(0x82d8f9e0)
    programs=[]
    def seed(count=0,mode=0,reasons=None):
        return [0,*(reasons or [rng.randrange(2) for _ in range(34)]),
                *[rng.choice((0,0x80000000,fbits(.731),0x7fc12345,0x7f800000)) for _ in range(34)],
                count,fbits(.317),0xfffffff9,fbits(-.731),mode]
    def query(up,flags=0,flag2476=0,flag2480=0,flag2484=0,category=200):
        return [7,flags,flag2476,flag2480,flag2484,up,category]
    for reason in range(34):
        rows=[seed(mode=reason),[5],[1],[4,reason,fbits(.731)]]
        for up in (0,0x80000000,0x3f4f5c28,0x3f4f5c29,0x3f4f5c2a,0xbf4f5c2a,fbits(1),0x7fc12345,0x7f800000):
            rows.extend(query(up,*flags) for flags in ((0,0,0,0),(1<<5,0,0,0),(0,1<<26,0,0),(0,0,1<<3,0),(0,0,0,1<<12)))
        rows.extend([[4,reason,0x80000000],query(fbits(1)),[6],query(fbits(1)),[2],[3],[3],[5],query(fbits(1))])
        programs.append(dict(label=f'reason {reason} boundaries and retained lifecycle',commands=rows))
    for count in (0,1,2,0xfffffffe,0xffffffff):
        for mode in (0,1,2,0xffffffff):
            reasons=[0]*34;reasons[2]=1
            rows=[seed(count,mode,reasons),query(fbits(1)),[3],[4,2,fbits(1)],query(fbits(1)),[4,2,0x7fc12345],query(fbits(1)),[6],query(fbits(1)),[5]]
            rows.extend(query(up,flag2484=1<<12,category=category) for up in (fbits(0),fbits(1),0x7fc12345) for category in (0,200,400,500,0xffffffff))
            programs.append(dict(label='wrapping count, repeated reasons and forced runout',commands=rows))
    for n in range(200):
        rows=[seed(rng.choice((0,1,2,0xffffffff)),rng.randrange(4))]
        for k in range(64):
            op=rng.randrange(1,8)
            if op==4:rows.append([4,rng.randrange(34),rng.choice((0,0x80000000,fbits(k*.13),0x7fc00000))])
            elif op==7:rows.append(query(rng.choice((fbits(1),fbits(-1),fbits(.5),0x7fc12345)),*(rng.getrandbits(32) for _ in range(4)),category=rng.choice((200,400,500))))
            else:rows.append([op])
        programs.append(dict(label='retained mixed lifecycle',commands=rows))
    return programs


def encode(programs):
    out=Record();out.word(len(programs))
    for program in programs:
        out.word(len(program['commands']))
        for row in program['commands']:out.words(row)
    return bytes(out.data)


def decode(data,programs):
    words=struct.unpack('<'+'I'*(len(data)//4),data);at=1;assert words[0]==len(programs)
    snapshots=[];queries=Counter();calls=Counter();overflow=0;duplicate=0
    for program in programs:
        previous=words[at:at+WORDS];at+=WORDS;assert previous==tuple([0]*WORDS)
        assert words[at]==len(program['commands']);at+=1
        for row in program['commands']:
            op=row[0];assert words[at]==op;at+=1;calls[op]+=1
            if op==7:
                result=words[at:at+2];at+=2;assert result in ((0,0),(0,1),(1,0));queries[result]+=1
            current=words[at:at+WORDS];at+=WORDS;snapshots.append(current)
            if op==4:
                assert current[68]==(previous[68]+1)&0xffffffff
                overflow+=previous[68]==0xffffffff;duplicate+=previous[row[1]]!=0
            if op in (1,2):
                assert current[:69]==previous[:69] and current[70:]==previous[70:]
            if op==3:
                assert current[:71]==previous[:71]
                assert current[71:]==previous[71:] if previous[72]==1 else current[71:]==(0,1)
            if op==5:assert current[:69]==tuple([0]*69) and current[69:]==previous[69:]
            if op==6:assert current[:68]==previous[:68] and current[68]==0 and current[69:72]==previous[69:72] and current[72]==0
            previous=current
    assert at==len(words)
    assert set(calls)==set(range(8)) and set(queries)=={(0,0),(0,1),(1,0)} and overflow>0 and duplicate>0
    assert len(set(snapshots))>500
    return dict(commands=sum(calls.values()),operations=dict(calls),queries={str(k):v for k,v in queries.items()},overflow_requests=overflow,repeated_reasons=duplicate,snapshot_variants=len(set(snapshots)))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--target-dir',required=True,type=Path);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    programs=corpus();blob=encode(programs);(out/'input.bin').write_bytes(blob);(out/'cases.json').write_text(json.dumps(programs,indent=2)+'\n')
    rust=build_probe(out,'wipeout-requests-reference',PLUGIN/'Tests/Reference/wipeout_requests_probe.rs',a.target_dir)
    live=PLUGIN/'Source/AtelierSkate/Private/Native';source=out/'native-source';source.mkdir(exist_ok=True)
    for name in ('WipeoutRequests.h','WipeoutRequests.cpp','NativeMath.h','DataReader.h'):shutil.copy2(live/name,source/name)
    probe=source/'wipeout_requests_probe.cpp';shutil.copy2(PLUGIN/'Tests/Native/wipeout_requests_probe.cpp',probe)
    (out/'native-provenance.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()},indent=2)+'\n')
    native=out/'wipeout-requests-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(source),str(source/'WipeoutRequests.cpp'),str(probe),'-o',str(native)],check=True)
    expected=subprocess.check_output([str(rust)],input=blob);actual=subprocess.check_output([str(native)],input=blob)
    (out/'reference.bin').write_bytes(expected);(out/'native.bin').write_bytes(actual)
    if expected!=actual:
        index=next((i for i,(x,y) in enumerate(zip(expected,actual)) if x!=y),min(len(expected),len(actual)))
        raise AssertionError(f'Wipeout requests differ at byte {index}')
    proof=decode(expected,programs);contracts=[]
    for index in (34,0xffffffff):
        data=encode([dict(commands=[[4,index,0]])]);r=subprocess.run([str(rust)],input=data,capture_output=True);c=subprocess.run([str(native)],input=data,capture_output=True)
        assert r.returncode==101 and c.returncode==-6,(index,r.returncode,c.returncode)
        contracts.append(index)
    result=dict(passed=True,programs=len(programs),output_words=len(expected)//4,output_sha256=hashlib.sha256(expected).hexdigest(),coverage=proof,invalid_index_contracts=contracts,comparison='Complete unchanged request owner, every retained field and query after each command. Full collision/pose wipeout checks and the shared gameplay frame remain separate integration work.')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
