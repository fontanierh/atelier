#!/usr/bin/env python3
"""Exact shared contact/joint/drive iteration comparison against frozen Rust.

Compile and run through the shared render lock and memory guard.
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
from reference_build import build_probe
from session_parity import PLUGIN


def bits(value):
    return struct.unpack('<I',struct.pack('<f',value))[0]


def corpus():
    rng=random.Random(0x82ae27d0)
    cases=[];offsets=[];labels=Counter();total=0
    def floats(n,scale):
        return [bits(rng.choice((0.0,-0.0,rng.uniform(-scale,scale)))) for _ in range(n)]
    def constraint(n,nr,scale=0.07):
        a=rng.randrange(nr);b=(a+rng.randrange(1,nr))%nr
        words=floats(n,scale)
        if n==64:
            words[15]=bits(rng.choice((0.0,0.3,0.8,1.0)));words[19]=bits(rng.choice((0.0,0.1,0.4,0.9)))
            words[20]=bits(rng.uniform(0,0.5));words[23]=bits(rng.uniform(0,0.5))
        else:
            for i in (27,31,35,39,43,47):words[i]=bits(rng.uniform(0,0.5))
        return [a,b,*words]
    def add(label,reactions,contacts=(),joints=(),drives=(),iterations=1,repeat=1):
        nonlocal total
        cmd=[len(reactions),len(contacts),len(joints),len(drives),iterations,repeat]
        for group in (reactions,contacts,joints,drives):
            for record in group:cmd.extend(record)
        words=repeat*(1+len(reactions)*16+len(contacts)*64+(len(joints)+len(drives))*96)
        offsets.append(dict(case=len(cases),label=label,first=total,last=total+words));total+=words
        cases.append(cmd);labels[label]+=1
    for family in range(3):
        for index in range(2048):
            nr=rng.randrange(2,6);reactions=[floats(16,0.1) for _ in range(nr)]
            record=constraint(64 if family==0 else 96,nr)
            groups=[[],[],[]];groups[family]=[record]
            add(('contact','joint','drive')[family],reactions,*groups,iterations=rng.choice((0,1,2,4,8)),repeat=4 if index<256 else 1)
    # Shared connected/reversed indices and retained correction lanes. Each
    # repeated result is emitted; testing families independently misses order.
    for index in range(1536):
        nr=rng.randrange(2,10);reactions=[floats(16,0.1) for _ in range(nr)]
        groups=[[constraint(n,nr) for _ in range(rng.randrange(1,7))] for n in (64,96,96)]
        add('mixed shared reactions',reactions,*groups,iterations=rng.choice((0,1,2,4,12)),repeat=8 if index<128 else 1)
    # Static friction branches use the preceding normal impulse, not the new
    # normal from this same iteration. Boundary equality must select static.
    for old_normal in (0.0,0.5,1.0,2.0):
        for friction in (0.0,0.25,0.5,1.0):
            for candidate in (-2.0,-1.0,-0.5,-0.25,-0.0,0.0,0.25,0.5,1.0,2.0):
                record=[0,1,*([0]*64)];w=record[2:]
                w[15]=bits(friction);w[19]=bits(friction/2);w[20]=bits(old_normal)
                w[24:28]=[bits(v) for v in (1,candidate,candidate,1)]
                for offset,axis in ((28,0),(40,1),(52,2)):w[offset+axis]=bits(1)
                w[35]=w[39]=bits(0.5)
                add('friction boundaries',[[0]*16,[0]*16],[[0,1,*w]],iterations=1,repeat=4)
    for drive in (False,True):
        for candidate in (-2,-1,-0.5,-0.0,0.0,0.5,1,2):
            for limit in (-1,-0.0,0.0,0.5,1):
                w=[0]*96
                w[8:12]=[bits(candidate)]*3+[bits(0.5)]
                w[12:16]=[bits(-candidate)]*3+[bits(0.25)]
                for i in (27,31,35,39,43,47):w[i]=bits(limit)
                for i in range(3):
                    w[40+i]=bits(limit if drive else -limit);w[44+i]=bits(limit)
                    w[48+4*i+i]=bits(1);w[60+4*i+i]=bits(1)
                    w[72+4*i+i]=bits(0.5);w[84+4*i+i]=bits(0.25)
                w[75]=bits(1);w[87]=bits(0.5)
                groups=[[],[],[]];groups[2 if drive else 1]=[[1,0,*w]]
                # Unused reaction lanes carry arbitrary words, including NaNs.
                # Joint/drive passes must leave these pose corrections intact.
                reactions=[[0]*16,[0]*16]
                for r in reactions:r[4:8]=[rng.getrandbits(32) for _ in range(4)];r[12:16]=[rng.getrandbits(32) for _ in range(4)]
                add('drive limit boundaries' if drive else 'joint limit boundaries',reactions,*groups,iterations=1,repeat=4)
    # No-work and rejection records verify validation before every mutation,
    # including a malformed later family after an otherwise valid contact.
    add('empty world',[],iterations=0);add('empty world',[],iterations=12)
    for family in range(3):
        for invalid in ((0,0),(0,3),(3,0),(3,3),(2**32-1,0)):
            for iterations in (0,1,8):
                groups=[[constraint(n,3)] for n in (64,96,96)]
                groups[family].append([*invalid,*floats(64 if family==0 else 96,1)])
                add('invalid indices', [floats(16,1) for _ in range(3)],*groups,iterations=iterations,repeat=2)
    words=[len(cases)]
    for case in cases:words.extend(case)
    return struct.pack(f'<{len(words)}I',*words),offsets,dict(labels),total


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--target-dir',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    reference=build_probe(output,'constraint-solver-reference',PLUGIN/'Tests/Reference/constraint_solver_probe.rs',args.target_dir)
    source_code=PLUGIN/'Source/AtelierSkate/Private/Simulation';code=output/'simulation-source'
    if code.exists():shutil.rmtree(code)
    code.mkdir()
    for name in ('ConstraintSolver.h','ConstraintSolver.cpp'):shutil.copy2(source_code/name,code/name)
    candidate=output/'constraint-solver-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-Wall','-Wextra','-Werror','-I',str(code),str(code/'ConstraintSolver.cpp'),str(PLUGIN/'Tests/Simulation/constraint_solver_probe.cpp'),'-o',str(candidate)],check=True)
    source,offsets,counts,words=corpus();(output/'inputs.bin').write_bytes(source)
    expected=subprocess.check_output([str(reference)],input=source);actual=subprocess.check_output([str(candidate)],input=source)
    (output/'reference.bin').write_bytes(expected);(output/'candidate.bin').write_bytes(actual)
    if len(expected)!=words*4:raise AssertionError(f'Oracle output size {len(expected)} differs from corpus specification {words*4}')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)))//4
        record=next((r for r in offsets if r['first']<=first<r['last']),None)
        raise AssertionError(f'First word differs at {first}: reference={expected[first*4:first*4+4].hex()} cpp={actual[first*4:first*4+4].hex()}, {record}')
    result=dict(passed=True,cases=len(offsets),groups=counts,output_words=words,output_bytes=len(actual),sha256=hashlib.sha256(actual).hexdigest(),comparison='exact words after every repeated solve; contacts/joints/drives exchange shared reactions each iteration; friction and limits, opaque retained lanes, invalid indices reject before mutation')
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
