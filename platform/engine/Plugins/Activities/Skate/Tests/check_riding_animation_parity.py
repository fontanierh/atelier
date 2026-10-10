#!/usr/bin/env python3
"""Compare exact riding-animation core owners and completed feedback publication.

Persistent crouch/auto-pump, tilt, fakie and pump channels run original core
methods; ground and physical feedback call untouched original publishers.
Stock settings are decoded independently by the original loaders. Compile/run
only through atelier.safety. This does not yet establish graph registration.
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
import check_animation_trees_parity as trees
from check_animation_playback_parity import Stream,bits
from check_gesture_parity import converter,PLUGIN
from reference_build import build_probe


class Writer(Stream):
    def vector(self,values):
        for value in values:self.float(value)
    def optional(self,value):
        self.word(value is not None)
        if value is not None:self.float(value)
    def curve(self,n,ys,step=1):self.vector([i*step for i in range(n)]);self.vector(ys)
    def crouch_settings(self,variant):
        self.curve(8,[1.137+i*.03125 for i in range(8)]);self.curve(8,[.137+i*.019 for i in range(8)],step=.137);self.curve(8,[.317+i*.03125 for i in range(8)],step=.137)
        self.vector((.137,.731,.03125,.113,(.5,1,0,-.2,1.2)[variant%5],.317,.731,.9,3,2,.317))
        self.curve(4,[.731]*4,step=3);self.vector((.5,.113,.03125,.113,.317,.5,.2,.3,.137,.113))
    def crouch_physical(self,case,tick):self.vector((((tick+case)%7-3)*.113,(tick%17)*.317,(tick%23)*.137,(tick%13-6)*.317,(tick%11-5)*.317,.113,(tick%5)*.137,.317+case*.03125))
    def crouch_intents(self,case,tick):
        self.optional(0 if tick%23<12 else None);self.optional(1 if tick%23 in (2,3,4) else 0)
        self.optional((0,.137,.731,1,-.113)[(tick//9+case)%5] if tick%7 else None)
        self.optional(.517 if tick%17<7 else None);self.optional(-.317 if tick%29<11 else None);self.word((tick//13+case)%2)
    def tilt_settings(self,variant):self.curve(4,(.317,.517,.731,1.137));self.vector((.113,.03125,.317,.019+variant*.003))
    def pump_settings(self,variant):self.curve(8,[i*.173 for i in range(8)],step=1/7);self.vector(((.137,.5,1,1.2)[variant%4],3,.317,.137,.317))


def corpus():
    rng=random.Random(0x82bac1b0);cases=[];records=[]
    def new(op,steps=1):s=Writer();s.word(op);cases.append(s);records.append(dict(op=op,steps=steps));return s
    new(0)
    for case in range(16):
        n=192;s=new(1,n);stock=case%2;s.word(stock)
        if not stock:s.crouch_settings(case)
        s.vector((.137,.731,.731,0,0,.113,.137,(.137,.731,1.137,-.137)[case%4]));s.word(n)
        for tick in range(n):
            if tick>=128:
                s.vector((0,.731,0,0,0,.113,0,.317))
                for _ in range(5):s.optional(None)
                s.word(0)
            else:s.crouch_physical(case,tick);s.crouch_intents(case,tick)
            s.float((0,1/60,.03125,.137)[tick%4])
    for case in range(16):
        n=128;s=new(2,n);s.word(case%2)
        if not case%2:s.tilt_settings(case)
        s.word(n)
        for tick in range(n):
            action=2 if tick%23==0 else 0 if tick%17==0 else 1;s.word(action)
            if action!=2:s.word((tick//7+case)%2);s.float((tick%13-6)*.137);s.float((tick%9)*.317);s.word((1,2,5)[(tick//5+case)%3])
    for case in range(24):
        n=256;s=new(3,n);s.vector((2,1,.137,(0,.03125,.317,.731)[case%4]));s.word(n)
        for tick in range(n):
            category=(1,1,2,6,5,3,2,1)[(tick//17+case)%8];s.word(category);s.word(503 if tick%11 else 500);s.word(tick%19<3);s.vector((0,0,1,0));s.vector((.137,.317,(-1,.5,-.5,0)[(tick//9)%4],.731));s.vector((.317,.137,(-1,.5,-.5,0)[(tick//11)%4],.113));s.float((.5,1.5,2.5)[(tick//13+case)%3]);s.float((0,1/60,.03125,.137)[tick%4])
    for case in range(16):
        n=128;s=new(4,n);s.word(case%2)
        if not case%2:s.pump_settings(case)
        s.word(n)
        for tick in range(n):
            s.float((0,.317,1.973,3.137,1.137,0,-.137)[(tick//7+case)%7]);mask=(tick//13+case)%32
            for i in range(5):s.word((mask>>i)&1)
    for case in range(513):
        s=new(5);s.vector(((-2,-.137,0,.731,1,2)[case%6],(.137,.731,2,4)[case%4]));s.vector([rng.uniform(-2,2) for _ in range(32)]);s.vector([rng.uniform(-3,4) for _ in range(4)])
    for case in range(8):
        n=256;s=new(6,n);s.vector([rng.uniform(-.137,.137) for _ in range(35)]);s.word(n)
        for tick in range(n):
            s.vector((abs((tick%19-9)*.317),(tick%11-5)*.317,abs((tick%23-11)*.137),(tick%13-6)*.137));s.vector((tick*.001,.137,-.317,.113,.731,.517));s.float((tick%9-4)*.03125)
            positions=[.137+tick*.03125,.317,.731,0,1,0,.113,.137,.317,.731]
            if tick%37==0:positions[:3]=[1e-40,-1e-40,-0.0];positions[6:9]=[-1e-40,1e-40,0.0]
            s.vector(positions);s.word((0x00100000 if tick%2 else 0)|(0x80000000 if tick%3 else 0));s.float((tick%17-8)*.113);s.word((tick//7+case)%2);s.vector((.137,.317,.731,.113));s.word(tick%5==0)
    return cases,records


def encode(cases):return b'ATRIDE01'+len(cases).to_bytes(4,'little')+b''.join(s.data for s in cases)


def validate_corpus(cases,records):
    """Check every input field boundary before spending a guarded build slot."""
    for case,record in zip(cases,records):
        at=0
        def word():
            nonlocal at
            assert at+4<=len(case.data),(record,at,len(case.data))
            value=struct.unpack_from('<I',case.data,at)[0];at+=4;return value
        def words(n):
            for _ in range(n):word()
        op=word();assert op==record['op']
        if op==1:
            if not word():words(77)
            words(8);n=word()
            for _ in range(n):
                words(8)
                for _ in range(5):
                    if word():word()
                words(2)
        elif op==2:
            if not word():words(12)
            n=word()
            for _ in range(n):
                if word()!=2:words(4)
        elif op==3:words(4);n=word();words(n*17)
        elif op==4:
            if not word():words(21)
            n=word();words(n*6)
        elif op==5:words(38)
        elif op==6:words(35);n=word();words(n*29)
        else:assert op==0
        assert at==len(case.data),(op,at,len(case.data))
        if op in (1,2,3,4,6):assert n==record['steps']


def prepare_source(output):
    source=trees.source_at_reference('crates/skate-host/src/graph_host/motion_riding.rs');method,record=trees.extract_block(source,'pub fn body_tilt_settings(')
    probe=output/'riding-animation-oracle.rs';probe.write_text((PLUGIN/'Tests/Reference/riding_animation_probe.rs').read_text()+'\n'+method+'\n')
    provenance=dict(original_source_sha256=hashlib.sha256(source.encode()).hexdigest(),settings_extraction=record,probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(),callback_boundary='All tested numerical/stateful paths call original core functions. BoardMotion unused fields, SpeedWobble words other than 36, and unconsumed Pumping fields have explicit fixture sentinels/reset state; the original tested publishers do not read them. No producer callbacks are replaced.')
    (output/'extraction-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return probe


def build_simulation(output):
    live=PLUGIN/'Source/AtelierSkate/Private/Simulation';code=output/'simulation-source'
    if code.exists():shutil.rmtree(code)
    code.mkdir();files=('SimulationMath','AnimationName','Intents','Input','InputIntentions','NameId','Settings','RidingAnimation','RidingAnimationSettings')
    for p in list(live.glob('*.h'))+[live/(f+'.cpp') for f in files]:shutil.copyfile(p,code/p.name)
    probe=code/'riding_animation_probe.cpp';shutil.copyfile(PLUGIN/'Tests/Simulation/riding_animation_probe.cpp',probe);(output/'simulation-source-provenance.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(code.iterdir())},indent=2)+'\n')
    simulation=output/'riding-animation-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(code),*[str(code/(f+'.cpp')) for f in files],str(probe),'-o',str(simulation)],check=True);return simulation


def coverage(data,records):
    at=0;counts=Counter();branches={name:Counter() for name in ('auto_pump','player_pump','fakie','pump_start','pump_influence','bumped')}
    def word():
        nonlocal at
        w=struct.unpack_from('<I',data,at)[0];at+=4;return w
    for record in records:
        op,n=record['op'],record['steps'];counts[op]+=n
        if op==0:at+=358*4
        elif op==1:
            word()
            for _ in range(n):word();branches['auto_pump'][word()]+=1;branches['player_pump'][word()]+=1;word()
        elif op==2:
            for _ in range(n):
                if word():word()
        elif op==3:
            for _ in range(n):branches['fakie'][word() if word() else 'absent']+=1
        elif op==4:
            for _ in range(n):
                started=word();branches['pump_start'][started]+=1
                if started:word()
                influenced=word();branches['pump_influence'][influenced]+=1
                if influenced:word();word()
        elif op==5:at+=16;branches['bumped'][word()]+=1
        elif op==6:at+=n*63*4
    assert at==len(data),(at,len(data))
    for name in ('auto_pump','player_pump','pump_start','pump_influence','bumped'):assert branches[name][0] and branches[name][1],(name,branches[name])
    assert all(branches['fakie'][key] for key in (0,1,'absent')),branches['fakie']
    return dict(commands_by_type=dict(counts),branches={key:dict(value) for key,value in branches.items()})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    cases,records=corpus();validate_corpus(cases,records);commands=encode(cases);(output/'input.bin').write_bytes(commands)
    reference=build_probe(output,'riding-animation-reference',prepare_source(output),args.target_dir);simulation=build_simulation(output);settings=output/'settings.simulation';settings.write_bytes(converter.encode_settings(args.assets/'private/stock/skater-collections.json'))
    def expected(data):return subprocess.check_output([str(reference),str(args.assets.resolve())],input=data)
    def actual(data):return subprocess.check_output([str(simulation),str(settings)],input=data)
    oracle=expected(commands);candidate=actual(commands);(output/'reference.bin').write_bytes(oracle);(output/'simulation.bin').write_bytes(candidate)
    if candidate!=oracle:
        lo=0;hi=len(cases)
        while hi-lo>1:
            mid=(lo+hi)//2;part=encode(cases[lo:mid])
            if expected(part)==actual(part):lo=mid
            else:hi=mid
        (output/'first-divergence-input.bin').write_bytes(encode(cases[lo:hi]));first=next((i for i,(a,b) in enumerate(zip(candidate,oracle)) if a!=b),min(len(candidate),len(oracle)));raise AssertionError(f'Riding animation differs at byte {first}, case {lo}; isolated input saved')
    result=dict(passed=True,cases=len(cases),coverage=coverage(oracle,records),output_bytes=len(candidate),output_sha256=hashlib.sha256(candidate).hexdigest(),comparison='Exact core persistent crouch/auto-pump, tilt, fakie and pump-channel outputs, stock settings, ground projection/bump and completed physical-feedback/turn-conditioner state.',limitations='Core boundary; graph operation registration, full MotionHost order, gameplay producers and full session scheduling are checked separately.',extraction_provenance_sha256=hashlib.sha256((output/'extraction-provenance.json').read_bytes()).hexdigest(),simulation_source_provenance_sha256=hashlib.sha256((output/'simulation-source-provenance.json').read_bytes()).hexdigest())
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
