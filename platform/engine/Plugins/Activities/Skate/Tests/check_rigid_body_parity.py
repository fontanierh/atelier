#!/usr/bin/env python3
"""Compare every body/force integration output word with the frozen Rust source.

Run through the shared render lock and memory guard; no game or engine is needed.
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
from reference_build import build_probe
from session_parity import PLUGIN


def bits(value):
    return struct.unpack('<I',struct.pack('<f',value))[0]


def corpus():
    rng=random.Random(0x82ae6590)
    commands=[];description=[];output_words=[]
    def add(op,values,label,size):
        commands.append([op,*values]);description.append(label);output_words.append(size)
    def floats(values):return [bits(v) for v in values]
    def vector(scale=1):return [rng.uniform(-scale,scale) for _ in range(3)]
    def quaternion():
        q=[rng.uniform(-1,1) for _ in range(4)];length=math.sqrt(sum(v*v for v in q));return floats(v/length for v in q)
    for index in range(3072):
        body=[rng.getrandbits(32) for _ in range(44)];body[:4]=quaternion()
        for offset,scale in ((4,500),(8,60),(12,30),(36,100),(40,100)):
            body[offset:offset+3]=floats(vector(scale))
        inverse_mass=rng.uniform(0.01,5)
        body[31]=bits(inverse_mass);body[39]=bits(rng.uniform(0,500));body[43]=rng.choice((0,1,30,2**32-1,rng.getrandbits(32)))
        dt=rng.choice((1/60,1/120,1/30,0.0,1/240))
        frequency=1/dt if dt else rng.choice((0,60,120))
        minimum_energy=rng.choice((0,0.01,100,10000))
        sim=[bits(dt),bits(frequency),rng.choice((0,1,30,120,2**32-1)),bits(minimum_energy),*floats((0,-9.81,0))]
        inertia=floats([rng.uniform(0.01,10) for _ in range(3)]+[0,inverse_mass,rng.uniform(0.1,8),rng.choice((0,1,12,90,1e10)),rng.choice((0,1,6,20,1e10)),rng.choice((0,0.1,60,120,300)),rng.choice((0,0.1,60,120,300))])
        reactions=floats(rng.uniform(-0.2,0.2) for _ in range(16))
        if index%4==0:reactions=[rng.choice((0,0x80000000)) for _ in range(16)]
        if index%7==0:
            body[8:15]=[0]*7;body[36:39]=[0]*3;body[40:43]=[0]*3;body[39]=bits(10000);sim[3]=bits(1);reactions=[0]*16
        steps=120 if index<128 else (8 if index%5==0 else 1)
        values=[*body,*inertia,*sim,*reactions,steps]
        add(0,values,f'packed evolving body {index}',steps*65)
        if index<768:add(5,values,f'typed evolving body {index}',steps*44)
    # Signed zeros and exact speed caps/sleep boundaries are explicit, rather
    # than relying on random floating point values to encounter them.
    for velocity in (-1.0,-0.0,0.0,1.0,2.0):
        for previous in (0,1,4):
            for cooldown in (0,29,30,2**32-1):
                body=[0]*44;body[3]=bits(1);body[8]=bits(velocity);body[31]=bits(1);body[39]=bits(previous);body[43]=cooldown
                inertia=floats((1,1,1,0,1,1,1,1,0,0))
                sim=[bits(1),bits(1),30,bits(1),0,0,0]
                add(0,[*body,*inertia,*sim,*([0]*16),4],f'cap/sleep v={velocity} prev={previous} cool={cooldown}',4*65)
    for index in range(4096):
        q=quaternion();v=floats(vector(0 if index%13==0 else 4))
        add(1,[*q,*v],f'orientation+basis {index}',13)
        matrix=floats(rng.uniform(-2,2) for _ in range(9));tensor=floats(rng.uniform(0.01,20) for _ in range(3))
        add(2,[*matrix,*tensor],f'inertia transform {index}',9)
        add(3,[*matrix,*v],f'packed inertia multiplication {index}',9)
        acc=floats(vector(100)+vector(100));force=floats(vector(10000));point=floats(vector(2));inverse=floats(rng.uniform(-5,5) for _ in range(9))
        add(4,[*acc,rng.getrandbits(32),*force,*point,*matrix,bits(rng.uniform(0.001,4)),*inverse],f'point force {index}',7)
    for index in range(256):
        add(6,[rng.getrandbits(32),bits(rng.uniform(-1,100)),*floats(vector(100))],f'fixed step {index}',7)
    for index in range(4096):
        radius=rng.choice((0.0,-0.0,1e-9,0.03,1.0,rng.uniform(0.01,100)))
        length=rng.choice((0.0,-0.0,1e-8,0.02,1.0,rng.uniform(0.01,100)))
        values=floats((radius,length,rng.uniform(0,0.1),*vector(10)))
        for kind in range(5):add(7,[kind,*values],f'primitive shape {kind} sample {index}',1 if kind==4 else 5)
    words=[len(commands)];offsets=[];offset=0
    for command,label,size in zip(commands,description,output_words):
        words.extend(command);offsets.append(dict(first=offset,last=offset+size,description=label,operation=command[0]));offset+=size
    return struct.pack(f'<{len(words)}I',*words),offsets,Counter(c[0] for c in commands),offset


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--target-dir',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    reference=build_probe(output,'rigid-body-reference',PLUGIN/'Tests/Reference/rigid_body_probe.rs',args.target_dir)
    source_code=PLUGIN/'Source/AtelierSkate/Private/Simulation';code=output/'simulation-source'
    if code.exists():shutil.rmtree(code)
    code.mkdir()
    for name in ('SimulationMath.h','SimulationMath.cpp','RigidBody.h','RigidBody.cpp','BodyMass.h','BodyMass.cpp'):shutil.copy2(source_code/name,code/name)
    candidate=output/'rigid-body-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-Wall','-Wextra','-Werror','-I',str(code),str(code/'SimulationMath.cpp'),str(code/'RigidBody.cpp'),str(code/'BodyMass.cpp'),str(PLUGIN/'Tests/Simulation/rigid_body_probe.cpp'),'-o',str(candidate)],check=True)
    source,offsets,counts,words=corpus();(output/'inputs.bin').write_bytes(source)
    expected=subprocess.check_output([str(reference)],input=source);actual=subprocess.check_output([str(candidate)],input=source)
    (output/'reference.bin').write_bytes(expected);(output/'candidate.bin').write_bytes(actual)
    if len(expected)!=words*4:raise AssertionError(f'Oracle output size {len(expected)} differs from corpus specification {words*4}')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)))//4
        record=next((r for r in offsets if r['first']<=first<r['last']),None)
        a=expected[first*4:first*4+4].hex();b=actual[first*4:first*4+4].hex()
        raise AssertionError(f'First word differs at {first}: reference={a} cpp={b}, {record}')
    result=dict(passed=True,records=sum(counts.values()),operations=dict(sorted(counts.items())),output_words=words,output_bytes=len(actual),sha256=hashlib.sha256(actual).hexdigest(),comparison='exact words; packed opaque lanes, force accumulation, typed state, caps, cooldowns, pose, evolving integration and primitive shape moments')
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
