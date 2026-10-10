#!/usr/bin/env python3
"""Compare simulation animation clocks/attributes/fades/pose kernels bit for bit.

Both probes consume the same generated command stream. Expected values execute
the unmodified frozen Rust core. Authored sampling uses every independently
decoded stock clip from check_animation_samples_parity.py's export directory.
Run this compiler/sampling job through atelier.safety's render lock and guard.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import subprocess
from check_gesture_parity import PLUGIN
from reference_build import build_probe


def bits(value):return struct.unpack('<I',struct.pack('<f',value))[0]


class Stream:
    def __init__(self):self.data=bytearray()
    def word(self,value):self.data.extend(struct.pack('<I',value&0xffffffff))
    def wide(self,value):self.data.extend(struct.pack('<Q',value))
    def float(self,value):self.word(bits(value))
    def string(self,value):
        raw=value.encode('utf-8');self.word(len(raw));self.data.extend(raw)
    def words(self,values):
        self.word(len(values))
        for value in values:self.word(value)
    def name(self,value):
        for word in value:self.word(word)
    def attr(self,a):
        self.name(a['name']);self.word(a['kind']);self.word(a['status']);self.word(a['sequence']);self.word(a['begin']);self.word(a['end'])
        for p in a['payload']:
            self.word(p is not None)
            if p is not None:self.word(p)
    def attrs(self,values):
        self.word(len(values))
        for value in values:self.attr(value)
    def sqt(self,values):
        for value in values:self.float(value)
    def settings(self,s):
        self.word(s['priority']);self.word(s['keep']);self.word(s['mirror']);self.float(s['speed']);self.float(s['in']);self.word(s['holdin']);self.float(s['out']);self.word(s['holdout']);self.word(s['attributes'])
    def clip(self,frames=61,fps=30,base=1,flags=0,attrs=(),time=0,previous=0,loops=0):
        self.float(frames);self.float(fps);self.float(base);self.word(flags);self.word(len(attrs))
        for a in attrs:
            self.name(a['name']);self.word(a['kind']);self.word(a['begin']);self.word(a['end']);self.words(a['payload'])
        self.float(time);self.float(previous);self.word(loops)


def attribute(name=1,kind=0,status=5,seed=0):
    payload=[bits((seed+i+1)/7) for i in range(6)]
    return dict(name=[name,0,0,0,0],kind=kind,status=status,sequence=seed-2,begin=bits(0.125*seed),end=bits(1+0.5*seed),payload=payload)


def corpus(samples):
    rng=random.Random(0x46513a6);cases=[];counts=Counter()
    def new(kind):
        stream=Stream();stream.word(kind);cases.append((kind,stream));counts[kind]+=1;return stream
    # Timing updates intentionally retain/overwrite AdvanceResult sentinel
    # fields in the same branches as the simulation clock. Wrap counters include
    # u32 overflow; equality with end and phase rollback are separate cases.
    for flags in (0,0x10000000,0x40000000,0x50000000):
        for frames,fps,base in ((61,30,1),(47,29.97,0.731),(3,60,1.77),(1001,24,0.3333)):
            for loops in (0,0xffffffff):
                s=new(1);s.clip(frames,fps,base,flags,loops=loops);commands=[]
                for op,values in [(0,(0,0)),(0,(1/60,0.5)),(3,()),(1,(0.731,)),(0,(5.333,0.99999)),(1,(1.931,)),(2,(0,)),(0,(-0.0,-0.1)),(0,(1,2)),(3,()),(0,(8.75,0.1))]:commands.append((op,values))
                for _ in range(80):
                    op=rng.choice([0,0,0,0,1,2,3]);values=(rng.uniform(0,0.2),rng.uniform(-0.2,1.2)) if op==0 else (rng.uniform(0.15,3.5),) if op==1 else (rng.uniform(0,0.02),) if op==2 else ()
                    commands.append((op,values))
                s.word(len(commands))
                for i,(op,values) in enumerate(commands):
                    s.word(i%2);s.float(77.125+i);s.float(-55.25-i);s.word(op)
                    for value in values:s.float(value)
    for flags in (0,0x10000000,0x40000000):
        for dt in (0,1,2,2.000000238418579,6,-0.0001):
            s=new(1);s.clip(flags=flags,time=0,previous=1);s.word(2)
            for op in (0,3):
                s.word(1);s.float(7);s.float(9);s.word(op)
                if op==0:s.float(dt);s.float(1)
    # Invalid elapsed looping clocks preserve the same mutations as Rust's
    # panic, while the exceptions-disabled simulation module returns an error.
    for length,time,dt in ((0,0,1),(-1,0,1),(1,0,math.inf),(1e-20,1e20,1),(1,1e30,1),(0,-1,0)):
        s=new(13);s.clip(flags=0x10000000,time=time,previous=0.731,loops=7);s.float(length);s.word(True);s.float(17);s.float(19);s.float(dt);s.float(0)
    # Curve searches keep crossed binary bounds, exact-match endpoints and
    # explicit malformed handling. Opaque padding words survive conversion.
    for count in (1,2,3,4,9,17):
        points=[(i*1.73,rng.uniform(-3,4)) for i in range(count)];words=[0xfeed0012,count]
        for x,y in points:words.extend([bits(x),bits(y)])
        words.extend([0x7fc01234,0x80000000]);s=new(2);s.words(words)
        times=[-10,0,points[-1][0]+10]+[p[0] for p in points]+[rng.uniform(-1,points[-1][0]+1) for _ in range(100)]
        s.word(len(times))
        for time in times:s.float(time)
    for words in ([],[0],[0,0],[0,3,0,0],[0,2,0,0,0,0]):
        s=new(2);s.words(words);s.word(3)
        for value in (-1,0,1):s.float(value)
    # Clip bulk attributes force untimed status 4, direct queries status 6.
    authored=[dict(name=[i%3+1,0,0,0,0],kind=kind,begin=bits(begin),end=bits(end),payload=payload)
              for i,(kind,begin,end,payload) in enumerate([(0,-1,-1,[0x7fc01234]),(1,0,1,[bits(v) for v in (1,-0.0,3,4)]),(3,0.25,0.75,[1,2,3,4,5,bits(0.731)]),(2,-1,-1,[0,3,bits(0),bits(1),bits(30),bits(2),bits(60),bits(3)]),(99,0.5,0.5,[]),(0,0.5,1,[bits(1.234)]),(0,-1,0,[bits(7)]),(2,0,1,[0,0])])]
    for time,previous,loops in ((0,0,0),(0.5,0,0),(1,0.5,0),(1.5,1,0),(2,1.5,0),(0.2,1.8,1),(0.2,0,2),(3,2,0)):
        s=new(3);s.clip(attrs=authored,time=time,previous=previous,loops=loops);queries=[(mask,name) for mask in range(32) for name in range(1,5)];s.word(len(queries))
        for mask,name in queries:s.word(mask);s.name([name,0,0,0,0])
    # Arithmetic sees retained initialized/inactive lanes, partial failure
    # writes, unsigned name comparison, sequence IDs and opaque nonfinite bits.
    for kind in (0,1,2,3,4,99):
        for status in (4,5,6,9,17):
            for op in range(5):
                for weight in (0,0.0317,0.5,1,1.25,-0.25):
                    a=attribute(kind=kind,status=status,seed=3);b=attribute(name=2,kind=kind,status=status,seed=7)
                    a['payload'][:5]=[1,2,3,4,5] if kind==3 else a['payload'][:5]
                    s=new(4);s.word(op);s.attr(a);s.attr(b);s.float(weight);s.word(1);s.name([1,2,3,4,5]);s.name([9,8,7,6,5])
    for op in range(5):
        for lane in range(6):
            a=attribute(kind=3);a['payload'][lane]=None;b=attribute(kind=3)
            s=new(4);s.word(op);s.attr(a);s.attr(b);s.float(0.731);s.word(0)
    for _ in range(64):
        s=new(11);left=[attribute(name=i,seed=3) for i in rng.sample(range(1,9),6)];right=[attribute(name=i,seed=7) for i in rng.sample(range(1,9),6)]
        if rng.choice([True,False]):left.sort(key=lambda a:a['name']);right.sort(key=lambda a:a['name'])
        s.attrs(left);s.attrs(right);s.float(rng.uniform(-0.25,1.25))
    # Packet slots remain after clear, so an appended scalar retains old vector
    # lanes. Copying an unknown kind retains every previous lane in the slot.
    s=new(9);s.word(12)
    for kind in (3,0,1,99):
        s.word(0);s.word(1);s.attr(attribute(kind=kind,seed=kind))
        s.word(2);s.word(2)
        for name,value in ((1,0.731),(1,-0.0)):s.name([name,0,0,0,0]);s.float(value)
        s.attrs([attribute(kind=2,seed=2),attribute(kind=99,seed=99)])
    s=new(12);commands=[(1,1,1,True,-1),(1,2,3,False,-1),(1,1,2,False,2),(1,1,4,False,-1),(0,0,0,False,0),(1,2,5,True,-1)]
    s.word(len(commands))
    for op,name,value,normalized,sequence in commands:
        s.word(op)
        if op:s.name([name,0,0,0,0]);s.float(value);s.word(normalized);s.word(sequence)
    # All 32 flag combinations, preincrement fades, early termination,
    # resurrection and union ordering. Influence includes clamping boundaries.
    for flags in range(32):
        settings=dict(priority=-3,keep=bool(flags&1),mirror=True,speed=0.731,**{'in':0.5,'holdin':bool(flags&2),'out':0.5 if flags&4 else 0,'holdout':bool(flags&8),'attributes':bool(flags&16)})
        commands=[]
        for i in range(30):
            commands.append((0,(0.125,2,i*0.125,(-0.25,0,0.5,1,1.5)[i%5])))
            if i in (5,14):commands.append((1,()))
            if i==9:commands.append((2,(0.25,True)))
            if i in (8,18):commands.append((3,(dict(settings,keep=False,out=0.731,attributes=True),True)))
            commands.append((4,(i%3==0,)))
        s=new(5);s.settings(settings);s.word(len(commands))
        for op,values in commands:
            s.word(op)
            if op==0:
                for v in values:s.float(v)
            elif op==2:s.float(values[0]);s.word(values[1])
            elif op==3:s.settings(values[0]);s.word(values[1])
            elif op==4:s.word(values[0])
        s.attrs([attribute(name=i,seed=1) for i in (1,2,4,4,9)]);s.attrs([attribute(name=i,seed=9) for i in (2,3,4,8)])
    for n in range(11):
        for _ in range(100):
            s=new(6);s.word(n)
            for i in range(n):
                s.word(rng.randrange(4));s.float(rng.uniform(0.01,3));minimum=rng.choice([0,-1,0.2]);s.float(minimum);s.float(minimum+rng.choice([0,1e-7,1/65536,0.731,1,3]))
                s.float(rng.uniform(-2,3));s.float(rng.uniform(-2,3))
    for frames in (0,1,2,8,9,61,32769):
        for blend in (False,True):
            for time in (-1,-0.0,0,1/60,7/30,7.99999/30,8/30,2,1000):
                for offset in (0,0.5,1):
                    s=new(7);s.float(time);s.float(30);s.wide(frames);s.word(blend);s.float(offset)
    for time,fps,frames,blend,offset in ((0,0,1,True,0),(0,-1,1,True,0),(math.nan,30,1,True,0),(math.inf,30,1,True,0),(0,30,61,False,math.nan),(0,30,61,False,math.inf)):
        s=new(7);s.float(time);s.float(fps);s.wide(frames);s.word(blend);s.float(offset)
    def pose():
        q=[rng.uniform(-1,1) for _ in range(4)];return [rng.uniform(0.1,3) for _ in range(4)]+q+[rng.uniform(-2,2) for _ in range(4)]
    for op in range(3):
        for _ in range(400):
            s=new(8);s.word(op);s.float(rng.choice([0,0.01,0.5,1,1.5,-0.25]));s.word(rng.choice([False,True]));n=rng.randrange(1,6) if op==2 else 2;s.word(n);bones=rng.randrange(0,6) if op==2 else 1
            for _ in range(n):
                s.float(rng.uniform(0.001,1));s.word(bones)
                for _ in range(bones):s.sqt(pose())
    # Weighted errors are returned explicitly; no quiet pose substitution.
    for variant in ('empty','shape','nanweight','zeroquat'):
        s=new(8);s.word(2);s.float(0);s.word(False);n=0 if variant=='empty' else 2;s.word(n)
        for i in range(n):
            s.float(math.nan if variant=='nanweight' else 0 if variant=='zeroquat' else 1);bones=i+1 if variant=='shape' else 1;s.word(bones)
            for _ in range(bones):s.sqt([1,1,1,1,0,0,0,1,0,0,0,1])
    manifest=json.loads((samples/'simulation/samples-manifest.json').read_text())
    for clip in manifest['clips']:
        raw=Path(clip['name']);name=clip['name']
        # Converter reports names as bank/name paths, as clips.txt does.
        if '/' not in name:
            name=f'{clip["bank"]}/{name}'
        s=new(10);s.string(name);times=[-1,-0.0,0,1/60,7.25/30,8/30,0.731,10000]
        s.word(len(times))
        for time in times:s.float(time)
    return cases,dict(counts)


def encoded(cases):
    return b'ATPLAY01'+struct.pack('<I',len(cases))+b''.join(s.data for _,s in cases)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--target-dir',required=True,type=Path);parser.add_argument('--samples',required=True,type=Path)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True);samples=args.samples.resolve()
    reference=build_probe(output,'animation-playback-reference',PLUGIN/'Tests/Reference/animation_playback_probe.rs',args.target_dir)
    code=PLUGIN/'Source/AtelierSkate/Private/Simulation';binary=output/'animation-playback-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-fno-exceptions','-ffp-contract=off','-Wall','-Wextra','-Werror','-I',str(code),str(code/'AnimationPlayback.cpp'),str(code/'AnimationName.cpp'),str(code/'AnimationSamples.cpp'),str(code/'SimulationMath.cpp'),str(PLUGIN/'Tests/Simulation/animation_playback_probe.cpp'),'-o',str(binary)],check=True)
    cases,counts=corpus(samples);commands=encoded(cases);(output/'input.bin').write_bytes(commands)
    expected=subprocess.check_output([str(reference),str(samples/'decoded')],input=commands);actual=subprocess.check_output([str(binary),str(samples/'simulation')],input=commands)
    (output/'reference.bin').write_bytes(expected);(output/'simulation.bin').write_bytes(actual)
    if actual!=expected:
        # Isolate the first failing case without deriving expected data from C++.
        lo=0;hi=len(cases)
        while hi-lo>1:
            middle=(lo+hi)//2;data=encoded(cases[lo:middle]);e=subprocess.check_output([str(reference),str(samples/'decoded')],input=data);a=subprocess.check_output([str(binary),str(samples/'simulation')],input=data)
            if a==e:lo=middle
            else:hi=middle
        (output/'first-divergence-input.bin').write_bytes(encoded(cases[lo:hi]))
        first=next((i for i,(a,e) in enumerate(zip(actual,expected)) if a!=e),min(len(actual),len(expected)))
        raise AssertionError(f'Animation playback differs at byte {first}, case {lo}, kind {cases[lo][0]}; isolated command saved')
    result=dict(passed=True,comparison='exact bits, ordering, initialized payload lanes, failures and per-update results',cases=len(cases),case_types=counts,
                output_bytes=len(actual),output_sha256=hashlib.sha256(actual).hexdigest(),clips=counts[10],sample_times_per_clip=8)
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
