#!/usr/bin/env python3
"""Differential graph execution test, including every callback and timer bit.

The generated host has visible side effects. Comparing only the final selected
state would miss reordered, skipped or extra callbacks. Run under atelier.safety.
"""
import argparse
import hashlib
import json
from pathlib import Path
import historical_oracle as historical
import random
import shutil
import struct
import subprocess

PLUGIN=Path(__file__).resolve().parents[1]


def corpus():
    rng=random.Random(0x434f4e54)
    result=bytearray(); descriptions=[]
    def word(value): result.extend(struct.pack('<I',0xffffffff if value is None else value))
    def indices(values):
        word(len(values))
        for value in values: word(value)
    cases=128; word(cases)
    for case in range(cases):
        ns=rng.randrange(3,18); nt=rng.randrange(0,ns*2); ne=rng.randrange(2,18); nc=rng.randrange(3,24)
        nb=ns*2; commands=162
        parents=[None]+[rng.randrange(i) for i in range(1,ns)]
        children=[[] for _ in range(ns)]; transitions=[[] for _ in range(ns)]
        for i,parent in enumerate(parents):
            if parent is not None: children[parent].append(i)
        owners=[rng.randrange(ns) for _ in range(nt)]
        for i,owner in enumerate(owners): transitions[owner].append(i)
        for value in (ns,nt,ne,nc,nb,0): word(value)
        for i in range(ns):
            ancestors=[i]; current=parents[i]
            while current is not None: ancestors.append(current); current=parents[current]
            interrupt=(case+i)%4
            word(parents[i]); word(int(rng.randrange(8)!=0)); word(int(rng.randrange(8)!=0))
            word(interrupt); word(rng.choice(ancestors) if interrupt==2 else None)
            indices(children[i]); indices(transitions[i])
            word(None if rng.randrange(4)==0 else rng.randrange(ne)); indices([i*2,i*2+1])
        for i in range(nt):
            word(int(rng.randrange(8)!=0))
            # Self and ancestor transitions require re-entry, including old timers.
            target=owners[i] if i%4==0 else parents[owners[i]] if i%4==1 and parents[owners[i]] is not None else rng.randrange(ns)
            word(target); word(i%5); word(None if rng.randrange(4)==0 else rng.randrange(ne))
            indices([i*2,i*2+1] if i%3 else [])
        for i in range(ne):
            operation=(case+i)%6; word(operation)
            count=1 if operation==3 else rng.randrange(5); word(count)
            for _ in range(count):
                condition=i==0 or rng.randrange(3)!=0; word(int(condition)); word(rng.randrange(nc if condition else i))
        for i in range(nc): word(int(rng.randrange(6)!=0)); word((case+i)%8)
        for i in range(nb): word(i//2); word(int(i%5!=case%5))
        word(commands)
        for tick in range(commands):
            word(1 if tick in (80,161) else 0)
            dt=(0.,-0.,1/60,1/120,.1,.007)[tick%6]
            result.extend(struct.pack('<f',dt))
            values=([0]*nc if tick%19<3 else [1]*nc if tick%19<6 else
                    [rng.choice((0,1,2,3,255,256,257,511,0xffffffff,0x80000000,0x80000001)) for _ in range(nc)])
            indices(values)
        descriptions.append(dict(case=case,states=ns,transitions=nt,expressions=ne,conditions=nc,behaviors=nb,commands=commands))
    return bytes(result),descriptions


def trace_coverage(data):
    at=0; commands=0; events=[0]*7
    def word():
        nonlocal at
        value=struct.unpack_from('<I',data,at)[0]; at+=4; return value
    def frame():
        nonlocal at
        word(); word(); word(); count=word(); at+=count*8
    while at<len(data):
        if word()!=0xfffffffe: raise AssertionError('Missing command marker')
        word(); word(); commands+=1
        while (kind:=word())!=0xfffffffd:
            if kind>=len(events): raise AssertionError('Invalid callback type')
            events[kind]+=1
            for _ in range(9): word()  # id, result, memory and six context words
            if word(): frame()
        frame(); count=word(); at+=count*8; word(); word()
    if at!=len(data) or any(count==0 for count in events):
        raise AssertionError('Truncated trace or an unexercised callback kind')
    return dict(commands=commands,callbacks=dict(zip(('condition','allocate','begin','update','end','hook','release'),events)))


def build_probes(output):
    output.mkdir(parents=True,exist_ok=True)
    code=PLUGIN/'Source/AtelierSkate/Private/Simulation'; cpp=output/'controller-cpp'; rust=output/'controller-reference'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-Wall','-Wextra','-Werror',
                    '-I',str(code),str(code/'GraphController.cpp'),str(PLUGIN/'Tests/Simulation/controller_probe.cpp'),'-o',str(cpp)],check=True)
    oracle=output/'oracle'; (oracle/'graph').mkdir(parents=True,exist_ok=True)
    modules=('activation','controller','expression','selection')
    source=historical.stage_source_files(output, (
        'crates/skate-core/src/graph/'+name+'.rs' for name in modules))/'crates/skate-core/src/graph'
    (oracle/'graph/mod.rs').write_text(''.join(f'pub mod {name};\n' for name in modules))
    for name in modules: shutil.copyfile(source/f'{name}.rs',oracle/'graph'/f'{name}.rs')
    shutil.copyfile(PLUGIN/'Tests/Reference/controller_probe.rs',oracle/'main.rs')
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O',str(oracle/'main.rs'),'-o',str(rust)],check=True)
    return cpp,rust


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); output=args.output.resolve(); output.mkdir(parents=True,exist_ok=True)
    cpp,rust=build_probes(output)
    inputs,cases=corpus(); (output/'input.bin').write_bytes(inputs)
    (output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    expected=subprocess.check_output([str(rust)],input=inputs)
    actual=subprocess.check_output([str(cpp)],input=inputs)
    (output/'reference.bin').write_bytes(expected); (output/'cpp.bin').write_bytes(actual)
    if actual!=expected:
        first=next((i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b),min(len(actual),len(expected)))
        report=dict(passed=False,first_byte=first,reference_length=len(expected),cpp_length=len(actual),
                    reference_hex=expected[max(0,first-16):first+32].hex(),cpp_hex=actual[max(0,first-16):first+32].hex())
        (output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n'); raise AssertionError(report)
    coverage=trace_coverage(expected)
    if coverage['commands']!=sum(case['commands'] for case in cases): raise AssertionError('Incomplete controller trace')
    report=dict(passed=True,cases=len(cases),**coverage,output_bytes=len(expected),
                comparison='every callback, context, timer, state, active instance and side effect; exact bits',
                inputs_sha256=hashlib.sha256(inputs).hexdigest(),outputs_sha256=hashlib.sha256(expected).hexdigest(),
                reference_sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in sorted((output/'oracle/graph').glob('*.rs'))})
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__': historical.run_cli(main)
