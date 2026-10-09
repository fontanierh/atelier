#!/usr/bin/env python3
"""Exact original-core steering/truck/wobble states and verbatim host settings.

Compile/run only through atelier.safety. Ground scheduling and trainer tuning
remain separate owners; these probes call unchanged public Rust core routines.
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
from check_animation_playback_parity import Stream, bits
from check_gesture_parity import converter, PLUGIN
from reference_build import build_probe


def number(word):return struct.unpack('<f',struct.pack('<I',word))[0]
def rounded(value):return number(bits(value))
def neighbors(value):
    word=bits(value)
    return [number(word-1),number(word),number(word+1)]


class Writer(Stream):
    def vector(self,values):
        for value in values:self.float(value)
    def curve(self,values):self.vector([i/7 for i in range(8)]);self.vector(values)
    def steering(self,case):
        self.vector((.317,(-.2,0,.731,1,1.2)[case%5],(0,.137,7.31)[case%3],.03125,.113,.137,.731,1.137,.317))
        self.curve([.137+i*.173 for i in range(8)]);self.curve([.03125+i*.137 for i in range(8)]);self.float(.317)
    def wobble(self,case,simple=False):
        self.curve([.317+i*.137 for i in range(8)]);self.curve([.731-i*.019 for i in range(8)]);self.curve([.113+i*.03125 for i in range(8)]);self.curve([.517+i*.019 for i in range(8)])
        self.vector((0 if simple else .317,(0,.137,1.137)[case%3],(0,.731,3.137)[case%3],.731,.317,0 if simple else .731,.137,.137 if case%7==0 and not simple else 1.137))


def corpus():
    rng=random.Random(0x82c0dbe8);cases=[];records=[]
    def new(op,label,steps=0):
        s=Writer();s.word(op);cases.append(s);r=dict(op=op,label=label,steps=steps);records.append(r);return s,r
    new(0,'stock_settings_and_all_five_modes')
    for case in range(32):
        n=128;s,r=new(1,f'steering_{case}',n);stock=case%2;s.word(stock)
        if not stock:s.steering(case)
        initial=[(-.317,.137,1.317,-0.0)[case%4],(-.731,0,.317,.731)[case%4]];s.vector(initial);r['initial']=list(map(bits,initial));s.word(n);r['masks']=[]
        for tick in range(n):
            mask=(case+tick//16)%4;r['masks'].append(mask);s.word(mask)
            turn=(-1,-.137,-0.0,0,.137,1,1.317)[(tick+case)%7]
            hard=(-0.0,0,.317,-.137)[(tick//3+case)%4]
            speed=(-.137,0,1e-40,.137,7.31,13.7)[(tick//5+case)%6]
            flip=(-1,0,1)[(tick//7+case)%3];balance=(-0.0,0,.137,-.317)[(tick//11+case)%4];tight=(-.137,0,.317,1,1.137)[(tick//13+case)%5]
            if tick==127:hard=float('nan')
            s.vector((turn,hard,speed,flip,balance,tight));s.word(tick%7<3)
    # Explicit unordered hard-turn and balance branches with no accumulated NaNs.
    for field in range(6):
        s,r=new(1,f'steering_unordered_{field}',1);s.word(0);s.steering(2);s.vector((.517,-.317));r['initial']=[bits(.517),bits(-.317)];s.word(1);s.word(field%4);r['masks']=[field%4];values=[.317,.137,3.137,1,.137,.731];values[field]=float('nan');s.vector(values);s.word(1)
    for case in range(40):
        n=96;s,r=new(2,f'truck_{case}',n);timer=([-0.0,0,.137]+neighbors(.16500001)+[.317,float('nan')])[case%8]
        s.vector((.317,-.731,.517,timer,(0,.137,.317)[case%3]));s.word(n)
        for tick in range(n):
            s.vector((rng.uniform(-2,2),(-.137,0,.317,1,1.137)[(tick//7+case)%5]));s.word((1<<20 if (tick//11+case)%2 else 0)|0x100)
            active=(tick//13+case)%4;s.word(((1<<27) if active&1 else 0)|((1<<26) if active&2 else 0)|0x200)
    s,r=new(2,'truck_first_inactive_hold_then_decay',3);s.vector((.317,-.731,.517,.137,.317));s.word(3)
    for _ in range(3):s.vector((.137,.317));s.word(0);s.word(0)
    for case in range(32):
        n=160;s,r=new(3,f'wobble_{case}',n);stock=case%2;s.word(stock)
        if not stock:s.wobble(case)
        initial=[bits((0,.137,.731)[case%3]),0x7fc12345,0x12345678,0x87654321,bits(.137),bits(.317),bits(.731),((0,1,2,255)[case%4]<<24)|0x005a31c7]
        s.vector([])
        for word in initial:s.word(word)
        r['initial']=initial;s.word(n)
        for tick in range(n):
            s.word(tick%37==0);speed=(-13.7,-.137,0,.137,3.137,13.7,27.31)[(tick//9+case)%7]
            height=(-.317,.137,.731,1.137,1.731)[(tick//11+case)%5];tight=(-.137,0,.731,1,1.317)[(tick//7+case)%5]
            activation=(-1,.317,3.137,13.7)[(tick//17+case)%4];amp=(-.731,0,.317,1,1.137)[(tick//19+case)%5]
            if tick==159:height=float('nan')
            s.vector((rng.uniform(-1,1),speed,height,tight,activation,amp))
    # Exact activation comparison, packed active-byte ownership, and one-frame
    # computed output on deactivation. No host producer has been substituted.
    for active in (0,1,2,255):
        for speed in [-.137,0]+neighbors(1)+[2]:
            s,r=new(3,f'wobble_activation_{active}_{bits(speed):08x}',1);s.word(0);s.wobble(1,True)
            initial=[bits(.137),0x1234abcd,0x45671234,0x76543210,bits(.317),bits(.731),bits(.113),(active<<24)|0x00abcdef]
            for word in initial:s.word(word)
            r['initial']=initial;s.word(1);s.word(0);s.vector((.731,speed,.517,.137,1,.317))
    for field in range(6):
        s,r=new(3,f'wobble_unordered_{field}',1);s.word(0);s.wobble(1,True);initial=[bits(.137),0xdead1234,0,0,bits(.317),0,0,0x025abcde]
        for word in initial:s.word(word)
        r['initial']=initial;s.word(1);s.word(0);values=[.731,3.137,.517,.137,1,.317];values[field]=float('nan');s.vector(values)
    s,r=new(3,'wobble_computed_deactivation_then_passthrough',3);s.word(0);s.wobble(1,True);initial=[0,0x7fa12345,0,0,0,0,0,0x005a1234]
    for word in initial:s.word(word)
    r['initial']=initial;s.word(3)
    for speed in (2,.731,.731):s.word(0);s.vector((.731,speed,.517,.137,1,.317))
    s,r=new(3,'wobble_explicit_reset_preserves_opaque',2);s.word(0);s.wobble(1,True);initial=[bits(.731),0x80000000,0x12345678,0x87654321,bits(.317),bits(.517),bits(.137),0xffabcdef]
    for word in initial:s.word(word)
    r['initial']=initial;s.word(2)
    for _ in range(2):s.word(1);s.vector((-.137,-3,.517,.137,1,.317))
    return cases,records


def encode(cases):return b'ATSTWB01'+len(cases).to_bytes(4,'little')+b''.join(s.data for s in cases)


def validate_corpus(cases,records):
    for case,record in zip(cases,records):
        words=struct.unpack('<'+'I'*(len(case.data)//4),case.data);at=1;op=words[0]
        if op in (1,3):
            stock=words[at];at+=1
            if not stock:at+=42 if op==1 else 72
            at+=2 if op==1 else 8;n=words[at];at+=1
            at+=n*(8 if op==1 else 7)
        elif op==2:at+=5;n=words[at];at+=1+n*4
        else:assert op==0
        assert op==record['op'] and at==len(words),(record,at,len(words))
        if op:assert n==record['steps']


def prepare_source(output):
    relative='crates/skate-host/src/physics/ground_runtime/settings.rs';source=trees.source_at_reference(relative)
    decoder,record=trees.extract_block(source,'pub(super) fn curve8(')
    def literal(field,typename):
        marker=f'            {field}: {typename} {{';assert source.count(marker)==1
        start=source.index(marker)+len(f'            {field}: ');begin=source.index('{',start);depth=1;at=begin+1
        # These binding expressions contain strings and no braces within them.
        # Keep the entire original initializer, including all field ordering.
        quoted=False;escaped=False
        while depth:
            char=source[at]
            if quoted:
                if escaped:escaped=False
                elif char=='\\':escaped=True
                elif char=='"':quoted=False
            elif char=='"':quoted=True
            elif char=='{':depth+=1
            elif char=='}':depth-=1
            at+=1
        text=source[start:at];assert source[at:at+2]==',\n'
        return text,dict(start_line=source[:start].count('\n')+1,end_line=source[:at].count('\n')+1,sha256=hashlib.sha256(text.encode()).hexdigest())
    steering,srecord=literal('steering','SteeringSettings');wobble,wrecord=literal('wobble','SpeedWobbleSettings')
    mode_lines=[]
    for field in ('wobble_activation','wobble_amplitude'):
        marker=f'            {field}: ';assert source.count(marker)==1;line=next(line for line in source.splitlines() if line.startswith(marker));mode_lines.append(line)
    mode_expressions=[line.split(': ',1)[1][:-1] for line in mode_lines]
    appended='\nmod stock {\nuse super::{PointGraph,SteeringSettings,SpeedWobbleSettings};\nuse skate_data::collections::Collections;\n'+decoder+'\n'
    for name,typename,value in (('steering','SteeringSettings',steering),('wobble','SpeedWobbleSettings',wobble)):
        appended+=f'pub fn {name}(data:&Collections)->Result<{typename},String> {{\nlet f=|class,field|data.float(class,"default",field);\nlet c8=|class,field|curve8(data,class,"default",field);\nOk('+value+')\n}\n'
    appended+='pub fn mode(data:&Collections,mode:&str)->Result<[f32;2],String> {\nlet m=|field|data.float("physics_mode",mode,field);\nOk(['+','.join(mode_expressions)+'])\n}\n}\n'
    probe=output/'steering-wobble-oracle.rs';probe.write_text((PLUGIN/'Tests/Reference/steering_wobble_probe.rs').read_text()+appended)
    provenance=dict(original_path=relative,original_source_sha256=hashlib.sha256(source.encode()).hexdigest(),verbatim_curve8=record,verbatim_steering_initializer=srecord,verbatim_wobble_initializer=wrecord,verbatim_mode_expressions=mode_lines,probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(),boundary='All numerical/state methods call unchanged original skate-core. Declaration-only wrappers surround verbatim original stock setting initializers and curve decoder; host Ground update/tuning are outside this probe.')
    (output/'extraction-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return probe


def build_simulation(output):
    live=PLUGIN/'Source/AtelierSkate/Private/Simulation';code=output/'simulation-source'
    if code.exists():shutil.rmtree(code)
    code.mkdir();files=('SimulationMath','NameId','Settings','StockSettingsReader','Steering','SpeedWobble','SteeringWobbleSettings')
    for p in list(live.glob('*.h'))+[live/(name+'.cpp') for name in files]:shutil.copyfile(p,code/p.name)
    probe=code/'steering_wobble_probe.cpp';shutil.copyfile(PLUGIN/'Tests/Simulation/steering_wobble_probe.cpp',probe)
    (output/'simulation-source-provenance.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(code.iterdir())},indent=2)+'\n')
    binary=output/'steering-wobble-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(code),*[str(code/(name+'.cpp')) for name in files],str(probe),'-o',str(binary)],check=True);return binary


def coverage(data,records):
    all_words=struct.unpack('<'+'I'*(len(data)//4),data);at=0;counts=Counter();traces={};pointer_updates=Counter();active=Counter();tilts=set();nonzero=0
    for index,record in enumerate(records):
        c,op,size=all_words[at:at+3];at+=3;assert (c,op)==(index,record['op']);words=all_words[at:at+size];at+=size;counts[op]+=record['steps'] or 1
        assert size==({0:124,1:3*record['steps'],2:5*record['steps'],3:9*record['steps']}[op]),(record,size)
        traces[record['label']]=[words[j:j+{0:124,1:3,2:5,3:9}[op]] for j in range(0,size,{0:124,1:3,2:5,3:9}[op])]
        if op==1:
            previous=record['initial']
            for tick,frame in enumerate(traces[record['label']]):
                mask=record['masks'][tick]
                for lane in range(2):
                    if not mask&(1<<lane):assert frame[lane+1]==previous[lane],(record,tick,lane)
                    elif frame[lane+1]!=previous[lane]:pointer_updates[lane]+=1
                previous=list(frame[1:]);tilts.add(frame[0]);nonzero+=math.isfinite(number(frame[0])) and number(frame[0])!=0
        elif op==3:
            initial=record['initial']
            for frame in traces[record['label']]:
                assert frame[2]==initial[1] and frame[8]&0xffffff==initial[7]&0xffffff,(record,frame)
                active[frame[8]>>24]+=1
    assert at==len(all_words)
    assert all(pointer_updates[lane]>100 for lane in (0,1)),pointer_updates
    assert len(tilts)>500 and nonzero>1000,(len(tilts),nonzero)
    hold=traces['truck_first_inactive_hold_then_decay'];assert hold[0][1:3]==(bits(-.731),bits(.517));assert hold[0][3:]==(0,0);assert hold[1][1:3]!=hold[0][1:3] and hold[2][1:3]!=hold[1][1:3]
    assert all(active[value]>0 for value in (0,1,2,255)),active
    deactivate=traces['wobble_computed_deactivation_then_passthrough'];assert deactivate[0][8]>>24==1 and deactivate[1][8]>>24==0;assert deactivate[1][0]!=bits(.731) and deactivate[2][0]==bits(.731)
    for frame in traces['wobble_explicit_reset_preserves_opaque']:assert frame[1:]==(0,0x80000000,0,0,0,0,0,0x00abcdef)
    for speed in neighbors(1):
        frame=traces[f'wobble_activation_0_{bits(speed):08x}'][0];assert frame[8]>>24==int(speed>1)
    return dict(commands_by_type=dict(counts),optional_pointer_updates=dict(pointer_updates),distinct_steering_tilts=len(tilts),nonzero_finite_steering_outputs=nonzero,wobble_active_bytes=dict(active),opaque_word_and_packed_bytes='Every wobble callback asserted unchanged',deactivation='Computed tilt then reset; subsequent inactive tilt passes through',truck_deactivation='First inactive callback holds, subsequent callbacks decay')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    cases,records=corpus();validate_corpus(cases,records);commands=encode(cases);(output/'input.bin').write_bytes(commands);(output/'cases.json').write_text(json.dumps(records,indent=2)+'\n')
    reference=build_probe(output,'steering-wobble-reference',prepare_source(output),args.target_dir);simulation=build_simulation(output);settings=output/'settings.simulation';settings.write_bytes(converter.encode_settings(args.assets/'private/stock/skater-collections.json'))
    def expected(data):return subprocess.check_output([str(reference),str(args.assets.resolve())],input=data)
    def actual(data):return subprocess.check_output([str(simulation),str(settings)],input=data)
    oracle=expected(commands);candidate=actual(commands);(output/'reference.bin').write_bytes(oracle);(output/'simulation.bin').write_bytes(candidate)
    if oracle!=candidate:
        lo=0;hi=len(cases)
        while hi-lo>1:
            mid=(lo+hi)//2;part=encode(cases[lo:mid])
            if expected(part)==actual(part):lo=mid
            else:hi=mid
        (output/'first-divergence-input.bin').write_bytes(encode(cases[lo:hi]));first=next((i for i,(a,b) in enumerate(zip(candidate,oracle)) if a!=b),min(len(candidate),len(oracle)));(output/'first-divergence.json').write_text(json.dumps(dict(case=lo,record=records[lo],byte=first),indent=2)+'\n');raise AssertionError(f'Steering/wobble differs at byte {first}, case {lo}; isolated input saved')
    result=dict(passed=True,cases=len(cases),coverage=coverage(oracle,records),output_bytes=len(oracle),output_sha256=hashlib.sha256(oracle).hexdigest(),comparison='Exact output and all mutable steering pointers, truck state fields and opaque eight-word wobble state; verbatim original host stock curves/scalars and five selected modes.',limitations='Pure core/settings boundary. Full Ground scheduling, trainer tuning, processed physical producers and live gameplay remain separate tests.',extraction_provenance_sha256=hashlib.sha256((output/'extraction-provenance.json').read_bytes()).hexdigest(),simulation_source_provenance_sha256=hashlib.sha256((output/'simulation-source-provenance.json').read_bytes()).hexdigest())
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
