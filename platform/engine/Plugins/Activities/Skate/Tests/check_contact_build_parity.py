#!/usr/bin/env python3
"""Compare contact preparation and compiled rows with the original Rust builder.

Run compilation and comparison through the shared render lock/memory guard.
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
    rng=random.Random(0x82ae10c8);cases=[];labels=[]
    for index in range(4096):
        record=[bits(rng.choice((0.0,-0.0,rng.uniform(-2,2)))) for _ in range(64)]
        states=((4,0),(0,4),(4,4),(0,0))[index%4]
        for body,state in enumerate(states):
            # Symmetric positive diagonal inverse inertia keeps the simulation
            # reciprocal path inside its documented finite arithmetic domain.
            record[(8+body)*4:(9+body)*4]=[bits(rng.uniform(0.01,4)),0,0,bits(rng.uniform(0.01,2))]
            record[(10+body)*4:(11+body)*4]=[bits(rng.uniform(0.01,4)),bits(rng.uniform(0.01,4)),0,state|(8 if index%3==0 else 0)]
            record[(6+body)*4+3]=rng.getrandbits(32);record[body*4+3]=rng.getrandbits(32)
        if index%3==0:
            for axis in range(3):record[(2+axis)*4:(2+axis)*4+3]=[bits(float(i==axis)) for i in range(3)]
        record[11]=bits(rng.choice((0.0,-0.0,0.1,0.5,1.0)))
        for lane in (15,19,23):record[lane]=rng.getrandbits(32)
        dt=bits(rng.choice((0.0,-0.0,1/60,1/120,0.02,0.1)))
        inverse=[bits(rng.choice((0.0,-0.0,1.0,rng.uniform(0.01,5)))) for _ in range(3)]
        for kind in (0,1,2):
            if kind==0 and not any(state&4 for state in states):continue
            cases.append([kind,*record,dt,*inverse]);labels.append(dict(case=len(cases)-1,source=index,kind=kind,states=states))
    words=[len(cases)]
    for case in cases:words.extend(case)
    return struct.pack(f'<{len(words)}I',*words),labels,dict(Counter(c[0] for c in cases))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--target-dir',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    reference=build_probe(output,'contact-build-reference',PLUGIN/'Tests/Reference/contact_build_probe.rs',args.target_dir)
    code=output/'simulation-source'
    if code.exists():shutil.rmtree(code)
    code.mkdir()
    for name in ('ContactBuild.h','ContactBuild.cpp','SimulationMath.h'):shutil.copy2(PLUGIN/'Source/AtelierSkate/Private/Simulation'/name,code/name)
    candidate=output/'contact-build-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(code),str(code/'ContactBuild.cpp'),str(PLUGIN/'Tests/Simulation/contact_build_probe.cpp'),'-o',str(candidate)],check=True)
    source,labels,counts=corpus();(output/'inputs.bin').write_bytes(source)
    expected=subprocess.check_output([str(reference)],input=source);actual=subprocess.check_output([str(candidate)],input=source)
    (output/'reference.bin').write_bytes(expected);(output/'candidate.bin').write_bytes(actual)
    if len(expected)!=len(labels)*130*4:raise AssertionError(f'Wrong oracle output size: {len(expected)}')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)))//4
        report=dict(passed=False,first_word=first,case=labels[first//130],field_word=first%130,reference=expected[first*4:first*4+4].hex(),cpp=actual[first*4:first*4+4].hex())
        (output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    result=dict(passed=True,cases=len(labels),operations=counts,output_words=len(actual)//4,output_bytes=len(actual),sha256=hashlib.sha256(actual).hexdigest(),comparison='exact contact preparation, active/inactive bodies, default/custom reciprocal response, ordered target publication, opaque identifiers/friction, failure before mutation')
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
