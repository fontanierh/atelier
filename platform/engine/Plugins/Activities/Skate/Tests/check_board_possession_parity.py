#!/usr/bin/env python3
"""Exact physical possession lifecycle and numerical producer comparison.

Run through the render lock/guard. Original full core modules remain unchanged.
The separate live-owner comparator verifies actual body/material/volume writes.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
import math
from pathlib import Path
import random
import shutil
import signal
import struct
import subprocess
import tarfile
PLUGIN=Path(__file__).resolve().parents[1]
REFERENCE_REVISION='46513a6'
OPERATIONS=('fields','observe','update','hold','let_go','stop','hide','retrieve','update_state','drive_frames','disable_hand','fill','numerics','opaque_state','reset_teleport','manager_enter','manager_reset')
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def value(w):return struct.unpack('<f',struct.pack('<I',w))[0]
def f(v):return list(map(bits,v))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def corpus(include_rejections=False):
    rng=random.Random(0x82d74dd8);records=[];cases=[];rejections=[]
    def numbers(n,scale=1.):return [rng.uniform(-scale,scale) for _ in range(n)]
    def matrix(phase=0.,position=None,carry=True):
        c,s=math.cos(phase),math.sin(phase);return f([c,0.,-s,rng.choice((0.,-0.,.25)) if carry else 0.,0.,1.,0.,0.,s,0.,c,rng.choice((0.,-0.,.5)) if carry else 0.,*(numbers(3,2.) if position is None else position),0.])
    def graph(xs,ys):return f(xs+ys)
    def settings(seed):return f([30.,1000.,30.,5.,.1])+graph([i*10. for i in range(8)],[.15+i*.03 for i in range(8)])+graph([i/7 for i in range(8)],[(i/7)**1.5 for i in range(8)])+f([(-18.,0.,18.,90.)[seed%4]])+graph([i*5. for i in range(8)],[2.+i*.2 for i in range(8)])+f([20.,.1,.1,.2])
    def state(seed,selected=2,progress=None):
        raw=matrix(seed*.03)+matrix(seed*.05)+matrix(seed*.07)+f([.13,.4,rng.uniform(0.,.9) if progress is None else progress,.3])
        for hand in range(2):raw+=matrix(seed*.01+hand)+matrix(seed*.02+hand)+[bits(1.+hand),bits(.5),bits(300.),rng.randrange(3)]*2
        raw+=[selected];assert len(raw)==133;return raw
    def observation(seed,flags=0,mount=0,flags2488=0,collision=0,surface=1,contacts=(0,0),board=(.2,.3,-.1),player=(0.,0.,0.)):
        raw=matrix(seed*.03,board)+matrix(seed*.02,player)+f([*player,0.])+f(numbers(4,5.))+f([0.,0.,1.,.25])+f([0.,0.,1.,0.])+[flags,mount,flags2488,collision,surface,*contacts]+f(numbers(8,1.))+matrix(seed*.01)+matrix(seed*.013)+matrix(seed*.017)+matrix(seed*.02,(.1,.8,.2));assert len(raw)==127;return raw
    def manager(seed):
        raw=[]
        for _ in range(2):raw+=f(numbers(20))+[rng.getrandbits(32),seed%2]+f(numbers(2))+[rng.randrange(2) for _ in range(4)]
        raw+=f(numbers(19))+[rng.getrandbits(32)]+[rng.randrange(2) for _ in range(4)]+[rng.getrandbits(32) for _ in range(3)];assert len(raw)==83;return raw
    def add(label,commands,seed=0,initial=None,fields=(0,0,1),obs=None,config=None,**meta):
        raw=(settings(seed) if config is None else config)+list(fields)+([0] if initial is None else [1]+initial)+(observation(seed) if obs is None else obs)+[len(commands)]+[w for c in commands for w in c]
        cases.append(dict(index=len(cases),label=label,commands=[c[0] for c in commands],**meta));records.append(struct.pack('<'+'I'*len(raw),*raw))
    for seed in range(512):
        o=observation(seed,flags=seed&4);throw=observation(seed,flags=0x3000|(seed&4));recall=observation(seed,flags=0x800,mount=0x80000 if seed%3==0 else 0)
        commands=[[3],[9],[11]+matrix(seed*.03),[1]+throw,[2]]+[[2] for _ in range(8)]+[[12]+f(numbers(8))+f([3.,.2,.1,0.,.2,2.,.3,0.,.1,.3,1.,0.]),[1]+recall,[2]]+[[2] for _ in range(10)]+[[0,0,4,1],[13]+state(seed,2,1.),[2],[1]+observation(seed,collision=0x4000000),[2],[0,7,2,1],[1]+observation(seed,board=(50.,0.,0.)),[2],[11]+matrix(),[1]+recall,[2],[0,0,4,1],[1]+observation(seed,contacts=(1,1)),[2],[5],[14],[14],[10],[16]+manager(seed)]
        add('connected held throw countdown, return completion/contact, hidden recall and teleport lifecycle',commands,seed,initial=state(seed) if seed%2 else None,obs=o)
    for mode in range(8):
        for flags in (0,4,0x800,0x1000,0x2000,0x3000,0x600):
            for mount in (0,0x80000):
                for collision in (0,0x4000000):
                    selected=mode%2 if mode==1 else 2
                    o=observation(mode,flags,mount,0x8000000 if flags==0x600 else 0,collision,6 if flags==0x800 else 1,(1,0))
                    add('every controller state, drop/free permission, recall precedence and contact completion',[[8],[2],[11]+matrix()],mode,initial=state(mode,selected,1. if flags==0x3000 else .5),fields=(8,mode,1),obs=o,state=mode,flags=flags,mount=mount,collision=collision)
    for seed in range(256):
        initial=state(seed,seed%2);commands=[[3],[9],[12]+f(numbers(8))+f([1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.]),[4],[10],[6],[7],[11]+matrix(),[0,0,4,1],[8],[5]]
        add('direct lifecycle functions preserve selected/offhand allocation and ordered effects',commands,seed,initial=initial,fields=(seed,4,True),obs=observation(seed,flags=(0x1000 if seed%2 else 0)))
    for x,y in ((0.,0.),(-0.,0.),(0.,-0.),(-0.,-0.),(1.,0.),(-1.,0.),(0.,1.),(0.,-1.),(1.,1.),(-1.,-1.)):
        for mode in range(6):
            # Identity player frame makes board x the angular y coordinate.
            obs=observation(0,board=(y,0.,x));obs[16:32]=matrix(0.,(0.,0.,0.),False)
            add('Fill quadrant axes, signed zero and half-pi instead of atan2',[[11]+matrix(0.,(0.,0.,0.),False)],initial=state(0,0),fields=(0,mode,False),obs=obs)
    for seed in range(64):
        for previous in (0,56,500,501,502,503):
            current=(500,501,502)[seed%3];commands=[[15]+manager(seed)+[previous,current,seed%2]+f(numbers(8))+[rng.getrandbits(32) for _ in range(4)]]
            add('offboard hand manager preserved-family enter and exclusive skeleton reset fields',commands,seed,previous=previous,current=current)
    for old in (0,1,2,3,4):
        for mounting in (0,0x80000):
            for distance in (0.,value(0x3a83126e),value(0x3a83126f),value(0x3a831270),4.9999995,5.,5.0000005,29.999998,30.,30.000002):
                obs=observation(0,mount=mounting,board=(distance,0.,0.));obs[111:127]=matrix(0.,(0.,0.,0.),False)
                add('retrieval tiny fallback, ordinary/mounted distance equality and hidden retained translation',[[7],[0,0,4,1],[2],[11]+matrix()],initial=state(0),fields=(0,old,1),obs=obs)
    for selected in (2,3,0xffffffff):
        raw=settings(0)+[0,1,1]+[1]+state(0,selected,.5)+observation(0)+[1,2]
        rejections.append(dict(selected_hand=selected,input=struct.pack('<'+'I'*(len(raw)+1),1,*raw)))
    result=(struct.pack('<I',len(records))+b''.join(records),cases)
    return (*result,rejections) if include_rejections else result
def build_probes(output):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip());relative=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-core/src').relative_to(root).as_posix()
    revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip();archive=subprocess.check_output(['git','archive',f'{revision}:{relative}'],cwd=root);source=output/'reference-source'
    if source.exists():shutil.rmtree(source)
    source.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:stream.extractall(source,filter='data')
    originals={p.relative_to(source).as_posix():digest(p) for p in sorted(source.rglob('*.rs'))}
    probe=PLUGIN/'Tests/Reference/board_possession_probe.rs';main=source/'board-possession-oracle.rs';main.write_text((source/'lib.rs').read_text()+probe.read_text());reference=output/'board-possession-reference'
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O','-A','dead_code',str(main),'-o',str(reference)],check=True)
    for name,expected in originals.items():
        if digest(source/name)!=expected:raise AssertionError(f'Frozen reference producer changed: {name}')
    snapshot=output/'native-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();native=PLUGIN/'Source/AtelierSkate/Private/Native';units=('NativeMath','RigidBody','SkeletonPoseFrames','BoardPossession','BoardPossessionManager')
    for name in [f'{unit}.{ext}' for unit in units for ext in ('h','cpp')]:shutil.copy2(native/name,snapshot/name)
    cpp_probe=PLUGIN/'Tests/Native/board_possession_probe.cpp';shutil.copy2(cpp_probe,snapshot/cpp_probe.name);cpp=output/'board-possession-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{unit}.cpp') for unit in units],str(snapshot/cpp_probe.name),'-o',str(cpp)],check=True)
    provenance=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,
        probe_sha256={p.name:digest(p) for p in (probe,cpp_probe)},reference_binary_sha256=digest(reference),cpp_binary_sha256=digest(cpp),native_source_sha256={p.name:digest(p) for p in sorted(snapshot.iterdir())},
        rust_compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip(),cpp_compiler=subprocess.check_output(['clang++','--version'],text=True).strip())
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return cpp,reference

def decode(data,cases):
    words=struct.unpack('<'+'I'*(len(data)//4),data);at=0;coverage=Counter()
    for case in cases:
        index,n,size=words[at:at+3];assert index==case['index'] and n==len(case['commands']);case.update(first_output_word=at,output_words=size+3)
        cursor=at+3+136;before=words[at+3:cursor]
        for op in case['commands']:
            actual_op,command_size=words[cursor:cursor+2];assert actual_op==op;cursor+=2;payload=words[cursor:cursor+command_size];cursor+=command_size;coverage[OPERATIONS[op]]+=1
            extra={11:9,12:20,15:96,16:83}.get(op,0);events=payload[extra];event_words=payload[extra+1:extra+1+events];e=0;sequence=[]
            while e<len(event_words):
                code,n=event_words[e:e+2];e+=2+n;sequence.append(code);coverage[f'effect_{code}']+=1
            assert e==len(event_words) and len(payload)==extra+1+events+136
            after=payload[-136:];coverage[f'state_{after[1]}']+=1
            if op==3 and sequence!=[0,4,6]:raise AssertionError('Hold effect order changed')
            if op==4 and sequence[:4]!=[2,5,6,7]:raise AssertionError('LetGo effect order changed')
            if op==14 and (after[3:51]!=tuple(f([1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,0.])*3) or after[51:55]!=(0,0,0,0)):raise AssertionError('Teleport retrieval reset changed')
            if op in (11,12,15,16) and after!=before:raise AssertionError('Read-only producer changed possession state')
            before=after
        assert cursor==at+size+3;at=cursor
    assert at==len(words);return words,dict(coverage)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    inputs,cases,rejections=corpus(True);(output/'input.bin').write_bytes(inputs);cpp,reference=build_probes(output)
    expected=subprocess.check_output([str(reference)],input=inputs);actual=subprocess.check_output([str(cpp)],input=inputs);(output/'reference.bin').write_bytes(expected);(output/'cpp.bin').write_bytes(actual);words,coverage=decode(expected,cases);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    if expected!=actual:
        first=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));aligned=first//4*4;case=next((c for c in cases if c['first_output_word']*4<=first<(c['first_output_word']+c['output_words'])*4),None)
        report=dict(passed=False,first_word=first//4,case=case,reference_length=len(expected),cpp_length=len(actual),reference_hex=expected[max(0,aligned-16):aligned+32].hex(),cpp_hex=actual[max(0,aligned-16):aligned+32].hex());(output/'first-divergence.json').write_text(json.dumps(report,indent=2)+'\n');raise AssertionError(report)
    rejection_results=[]
    for fixture in rejections:
        name=f"invalid-held-hand-{fixture['selected_hand']}";(output/f'{name}.bin').write_bytes(fixture['input'])
        checks={}
        for label,binary in (('original',reference),('candidate',cpp)):
            run=subprocess.run([str(binary)],input=fixture['input'],capture_output=True);checks[label]=dict(returncode=run.returncode,stderr=run.stderr.decode(errors='replace'))
            if run.returncode==0:raise AssertionError(f'{label} accepted invalid held hand {fixture["selected_hand"]}')
        if 'index out of bounds' not in checks['original']['stderr']:raise AssertionError(checks)
        if checks['candidate']['returncode']!=-signal.SIGABRT:raise AssertionError('Native invalid-hand contract did not abort: '+str(checks))
        rejection_results.append(dict(selected_hand=fixture['selected_hand'],**checks))
    (output/'rejections.json').write_text(json.dumps(rejection_results,indent=2)+'\n')
    result=dict(passed=True,cases=len(cases),exact_words=len(words),contract_rejections=len(rejection_results),groups=dict(Counter(c['label'] for c in cases)),coverage=coverage,input_sha256=hashlib.sha256(inputs).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),comparison='All retained retrieval/hand records, controller fields, numerical outputs, fill bytes and ordered effect publications exact; no tolerance; original modules unchanged',limitations='Explicit completed physical/animation observations and settings; actual active host Owner/live body/material/volume bindings are a separate comparator. Numerical requests use finite nonsingular inertia; Invalid held selected-hand indices 2, 3 and UINT_MAX are checked separately as original panics and native contract aborts.')
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
