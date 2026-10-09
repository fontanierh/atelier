#!/usr/bin/env python3
"""Unchanged Slide core and whole verbatim actual host stock constructor.

The separate Slide runtime producer/board schedule has its own comparison.
Only compile/run under the parent-owned render/memory guard.
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
import check_animation_trees_parity as trees
from check_animation_playback_parity import Stream,bits
from check_gesture_parity import converter,PLUGIN
from reference_build import build_probe


class Writer(Stream):
    def vector(self,values):
        for value in values:self.float(value)
    def curve(self,ys,maximum=1):self.vector([i*maximum/7 for i in range(8)]);self.vector(ys)
    def settings(self,case):
        self.curve([.137+i*.113 for i in range(8)]);self.curve([.113+i*.03125 for i in range(8)],maximum=10);self.curve([.317+i*.173 for i in range(8)],maximum=180);self.curve([.731+i*.03125 for i in range(8)],maximum=15);self.vector((.317,.731,.137,-.113))
        self.curve([(1,-1,0)[case%3]*(.317+i*.137) for i in range(8)],maximum=20);self.vector((.731,-.137))


def corpus():
    rng=random.Random(0x82d3ab14);cases=[];records=[]
    def new(op,label,steps=1):s=Writer();s.word(op);cases.append(s);records.append(dict(op=op,label=label,steps=steps));return s
    new(0,'stock_owner_all_five_materials')
    for case in range(24):
        n=32;s=new(1,f'lifecycle_{case}',n);s.vector(((-0.0,.731,13.7)[case%3],.137,-.317));s.word(1);s.word(1);s.word(n)
        for tick in range(n):s.word((1,2,2,1,0,2,1,2)[tick%8]);s.float((tick%7-3)*.317)
    for case in range(12):
        n=128;s=new(2,f'math_{case}',n);selected=case%6;s.word(selected)
        if not selected:s.settings(case)
        s.word(n)
        for tick in range(n):
            values=[[rng.uniform(-3,3) for _ in range(4)] for _ in range(6)]
            values[1]=[.137,.731,-.317,(-.5,0,.25)[tick%3]]
            for vector in values:s.vector(vector)
            s.vector((abs((tick%31-15)*.731),(tick%23-11)*.517,(-1,-.75,-.137,-0.0,0,.137,.75,1)[(tick+case)%8],(-.137,0,.49999997,.5,.50000006,1,1.5,1.5000001,2)[(tick//3+case)%9],(-.137,0,.317,1,1.137)[(tick//7+case)%5]))
    special=([0.,0.,0.,0.],[-0.,-0.,-0.,-0.],[0.,0.,1.,.25],[1e-20,-1e-20,1e-20,-.5],[.00001,0,0,.137],[1,2,3,.317])
    for case in range(3):
        n=len(special)*len(special)*5;s=new(2,f'degenerate_{case}',n);s.word(0);s.settings(case);s.word(n)
        for velocity in special:
            for forward in special:
                for slide in (-1,-.75,-0.0,.75,1):
                    for vector in (velocity,[0,1,0,.137],[1,0,0,.317],forward,[0,0,1,-.5],[.137,-.317,.731,.113]):s.vector(vector)
                    s.vector((5,3.137,slide,1.137,.731))
    for lane in range(6):
        s=new(2,f'unordered_{lane}');s.word(0);s.settings(1);s.word(1);values=[[.137,.317,.731,.113],[0,1,0,.137],[1,0,0,.317],[0,0,1,-.5],[0,0,1,.113],[.137,.317,.731,.113]];values[lane][0]=float('nan')
        for vector in values:s.vector(vector)
        s.vector((5,3.137,.731,.317,.731))
    return cases,records


def encode(cases):return len(cases).to_bytes(4,'little')+b''.join(s.data for s in cases)


def validate_corpus(cases,records):
    for case,record in zip(cases,records):
        words=struct.unpack('<'+'I'*(len(case.data)//4),case.data);op=words[0];at=1
        if op==1:at+=5;n=words[at];at+=1+2*n
        elif op==2:
            selected=words[at];at+=1
            if not selected:at+=86
            n=words[at];at+=1+29*n
        else:assert op==0
        assert at==len(words) and op==record['op'],(record,at,len(words))
        if op:assert n==record['steps']


def prepare_source(output):
    relative='crates/skate-host/src/physics/slide_state/settings.rs';source=trees.source_at_reference(relative)
    # Only the owner's declaration/accessibility is supplied. The entire original
    # settings module, including impl load and fixed20 curve decoder, is untouched.
    appended='\nmod stock {\nuse super::*;\npub struct SlideState {pub state:slide_state::SlideState,pub settings:SlideSettings,pub surfaces:Vec<(SlideSurface,RetailContactMaterial)>,pub manual_scalar:f32}\nmod settings {\n'+source+'\n}\n}\n'
    probe=output/'slide-state-oracle.rs';probe.write_text((PLUGIN/'Tests/Reference/slide_state_probe.rs').read_text()+appended)
    (output/'extraction-provenance.json').write_text(json.dumps(dict(original_path=relative,whole_verbatim_module_sha256=hashlib.sha256(source.encode()).hexdigest(),probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(),boundary='Original public Slide core/state and whole original host settings module. Owner declaration exposes fields for observation; no numerical constructor/decoder method is replaced. Runtime producers and host board scheduling are separate.'),indent=2)+'\n');return probe


def build_simulation(output):
    live=PLUGIN/'Source/AtelierSkate/Private/Simulation';code=output/'simulation-source'
    if code.exists():shutil.rmtree(code)
    code.mkdir();files=('SimulationMath','RidingAngles','BoardGroundAngle','NameId','Settings','StockSettingsReader','SlideState','SlideStateSettings')
    for p in list(live.glob('*.h'))+[live/(name+'.cpp') for name in files]:shutil.copyfile(p,code/p.name)
    probe=code/'slide_state_probe.cpp';shutil.copyfile(PLUGIN/'Tests/Simulation/slide_state_probe.cpp',probe);(output/'simulation-source-provenance.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(code.iterdir())},indent=2)+'\n')
    simulation=output/'slide-state-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(code),*[str(code/(name+'.cpp')) for name in files],str(probe),'-o',str(simulation)],check=True);return simulation


def coverage(data,records):
    words=struct.unpack('<'+'I'*(len(data)//4),data);at=0;counts=Counter();math_frames=[];lifecycle=0
    for index,record in enumerate(records):
        c,op,size=words[at:at+3];at+=3;assert (c,op)==(index,record['op']);payload=words[at:at+size];at+=size;counts[op]+=record['steps']
        if op==0:assert size==179 and payload[:5]==(0,bits(1),0,0,0)
        elif op==1:
            assert size==record['steps']*5
            for tick in range(record['steps']):
                row=payload[tick*5:tick*5+5];assert row[1:]==(bits(1),0,0,0)
                if tick%8 in (1,2,7):assert row[0]==payload[(tick-1)*5]
                lifecycle+=1
        else:
            assert size==record['steps']*11
            for tick in range(record['steps']):
                row=payload[tick*11:tick*11+11];assert row[4]==9 and row[8]==0 and row[10]==0;math_frames.append(row)
    assert at==len(words)
    def scalar(word):return struct.unpack('<f',struct.pack('<I',word))[0]
    nonfinite=sum(any(not math.isfinite(scalar(word)) for word in row[:4]) for row in math_frames);assert nonfinite>0
    finite=[row for row in math_frames if all(math.isfinite(scalar(word)) for word in row[:4]+row[5:])];assert len(finite)>1000
    assert any(scalar(row[9])<0 for row in finite) and any(scalar(row[9])>0 for row in finite)
    assert len({row[5:8] for row in finite})>1000
    return dict(commands_by_type=dict(counts),lifecycle_reset_and_speed_retention=lifecycle,finite_force_and_angle_frames=len(finite),nonfinite_angular_frames=nonfinite,distinct_finite_forces=len({row[5:8] for row in finite}),stock_profiles=5,point_force_tag=9)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    cases,records=corpus();validate_corpus(cases,records);commands=encode(cases);(output/'input.bin').write_bytes(commands);(output/'cases.json').write_text(json.dumps(records,indent=2)+'\n');reference=build_probe(output,'slide-state-reference',prepare_source(output),args.target_dir);simulation=build_simulation(output);settings=output/'settings.simulation';settings.write_bytes(converter.encode_settings(args.assets/'private/stock/skater-collections.json'))
    def expected(data):return subprocess.check_output([str(reference),str(args.assets.resolve())],input=data)
    def actual(data):return subprocess.check_output([str(simulation),str(settings)],input=data)
    oracle=expected(commands);candidate=actual(commands);(output/'reference.bin').write_bytes(oracle);(output/'simulation.bin').write_bytes(candidate)
    if candidate!=oracle:
        lo=0;hi=len(cases)
        while hi-lo>1:
            mid=(lo+hi)//2;part=encode(cases[lo:mid])
            if expected(part)==actual(part):lo=mid
            else:hi=mid
        (output/'first-divergence-input.bin').write_bytes(encode(cases[lo:hi]));first=next((i for i,(a,b) in enumerate(zip(candidate,oracle)) if a!=b),min(len(candidate),len(oracle)));(output/'first-divergence.json').write_text(json.dumps(dict(case=lo,record=records[lo],byte=first),indent=2)+'\n');raise AssertionError(f'Slide core/settings differs at byte {first}, case {lo}')
    result=dict(passed=True,cases=len(cases),coverage=coverage(oracle,records),output_bytes=len(oracle),output_sha256=hashlib.sha256(oracle).hexdigest(),comparison='Unchanged original Slide core lifecycle/angular correction/sliding force and entire actual host stock constructor, including all five wheel materials.',limitations='Core/settings comparison; actual producer-boundary host board/lifecycle schedule is a separate harness, with concrete physical producer binding owned by the coordinator.',extraction_provenance_sha256=hashlib.sha256((output/'extraction-provenance.json').read_bytes()).hexdigest(),simulation_source_provenance_sha256=hashlib.sha256((output/'simulation-source-provenance.json').read_bytes()).hexdigest())
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
