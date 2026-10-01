#!/usr/bin/env python3
"""Frozen real pumping geometry/control and two grounded force kernels.

Settings loader methods are extracted verbatim with exact-boundary assertions
and hashes. No geometry trait or production callback is replaced. Ground/revert
scheduling and actual board/skeleton sample preparation remain separate owners.
Run builds and probes through the shared render lock/memory guard.
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
from check_gesture_parity import converter, PLUGIN
from reference_build import build_probe
from session_parity import REFERENCE_REVISION, digest

OPERATIONS=('reset','update','calculate','pump_force','stock_ground_force','ground_force','geometry','mode','seed')
LENGTHS={0:21,1:17,2:15,3:13,4:18,5:25,6:23,7:1,8:21}


def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def scalar(w):return struct.unpack('<f',struct.pack('<I',w))[0]
def floats(values):return [bits(v) for v in values]


def corpus():
    rng=random.Random(0x82d8f228);rows=[]
    def add(op,words,**meta):
        assert len(words)==LENGTHS[op],(op,len(words),LENGTHS[op]);rows.append(dict(index=len(rows),operation=op,words=words,**meta))
    def sample(tick,stream):
        angle=(tick-16)*.037*(1 if stream%2 else -1)
        normal=(math.sin(angle),math.cos(angle),.137*(stream%3-1),.113)
        height=.137+(tick%9)*.21
        position=(tick*.137,math.sin(tick*.317)*.113,stream*.03125+tick*.517,.719)
        com=(.137,height,.317,.731)
        return floats(position+normal+com+(abs(angle)*2,))+[(tick+stream)%2]
    seeded=floats([.137,-.317,.731,.113,.137,.919,.317,.719]+[.731,.113,3.,-2.,8.,.731,6.,5.,4.,3.,2.])+[0,0x91]
    for mode in (0,1,2,3,4,5,0xffffffff):add(7,[mode])
    add(0,seeded,proof='reset')
    for stream in range(32):
        add(8,seeded,proof='seed',stream=stream)
        add(1,[stream%2,stream%5,bits(.137)]+sample(0,stream),proof='first',stream=stream)
        for tick in range(1,49):
            fixed=tick%3!=0;dt=(1/120,1/60,1/30,.05)[(stream+tick)%4]
            add(1,[int(fixed),(tick+stream)%5,bits(dt)]+sample(tick,stream),stream=stream,tick=tick,fixed=fixed,dt=bits(dt))
            if tick%12==0:add(2,[bits(dt)]+sample(tick,stream),proof='calculate_prefix',stream=stream)
        add(0,seeded,proof='reset',stream=stream)
    # Independent large retained angular values force both selected-mode limits.
    # Ground and revert still use distinct controller timesteps.
    for mode in range(5):
        for sign in (-1,1):
            for fixed in (0,1):
                bounded=seeded[:];bounded[13]=bits(sign*1e8);bounded[19]=1
                add(8,bounded)
                add(1,[fixed,mode,bits(.137)]+sample(1,mode),proof='mode_bound',mode=mode,sign=sign,fixed=fixed,dt=bits(.137))
    threshold=floats([1e-6]*4)
    special=((0.,0.,0.,0.),(-0.,-0.,-0.,-0.),(1e-6,0.,0.,.25),(1.0000001e-6,0.,0.,-.5),(1.,2.,3.,.25),(-1.,-.5,-2.,-.5))
    for flags in (0,2,0xabcdef01,0xabcdef03):
        for v in special:
            for pumping in (-3.,-0.,0.,.731):
                add(3,[flags]+floats([.317,pumping,1.137,1/60])+floats(v)+threshold,proof='pump_flag_pair')
    for _ in range(192):
        v=[rng.uniform(-5,5) for _ in range(4)]
        add(3,[rng.randrange(4)]+floats([rng.uniform(-2,2),rng.uniform(-2,2),rng.uniform(-4,4),rng.choice((1/120,1/60,.05))]+v)+floats([0.,1e-6,.01,10.]))
    def ground(arg,balance,velocity):
        return floats([arg,.317,.731,-1.137,balance,3.137]+[.137,-.317,.731,.113])+floats(velocity)+floats([-.517,.719,1.137,-.317])
    for arg in (-2.,-0.,0.,1e-7,.01,.1,1.,20.):
        for balance in (-.137,-0.,0.,.137):
            for velocity in special:add(4,ground(arg,balance,velocity))
    for _ in range(192):
        values=[rng.uniform(-2,2) for _ in range(18)]
        settings=[rng.choice((.01,.137,.731,2.)),rng.uniform(-4,4),rng.uniform(-4,4)]+[rng.choice((0.,1e-6,.01,10.)) for _ in range(4)]
        add(5,floats(settings+values))
    for velocity in special:
        for old_normal in ((0.,1.,0.,.25),(1.,0.,0.,-.5),(-1.,-.5,0.,0.)):
            for dt in (1/120,1/60,.05):
                current=floats(velocity)+floats((.137,.919,.317,.731))+floats((.317,.731,.113,-.137))+[bits(.517),1]
                add(6,floats((0.,0.,0.,-.317)+old_normal)+current+[bits(dt)])
    encoded=struct.pack('<I',len(rows))+b''.join(struct.pack('<'+'I'*(len(r['words'])+1),r['operation'],*r['words']) for r in rows)
    return encoded,rows


def validate_input(data,rows):
    words=struct.unpack('<'+'I'*(len(data)//4),data);assert words[0]==len(rows);at=1
    for row in rows:
        n=LENGTHS[row['operation']];assert words[at]==row['operation'];assert list(words[at+1:at+n+1])==row['words'];at+=n+1
    assert at==len(words)


def extract(source,anchor):
    assert source.count(anchor)==1,(anchor,source.count(anchor));start=source.index(anchor);opening=source.index('{',start);depth=0
    for index in range(opening,len(source)):
        if source[index]=='{':depth+=1
        elif source[index]=='}':
            depth-=1
            if depth==0:
                end=index+1;assert source[end:end+1] in ('\n',',');return source[start:end],start,end
    raise AssertionError('Unclosed original extraction')


def stock_bindings(output):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip());base=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-host/src/physics/ground_runtime').relative_to(root)
    sources={name:subprocess.check_output(['git','show',f'{REFERENCE_REVISION}:{(base/name).as_posix()}'],cwd=root).decode() for name in ('pumping.rs','settings.rs')}
    extracts={}
    for key,file,anchor in (('load','pumping.rs','    pub fn load(data: &Collections)'),('mode','pumping.rs','    pub fn mode(&self, index: u32)'),('curve8','settings.rs','pub(super) fn curve8('),('ground_force','settings.rs','GroundForceSettings {\n                range_1220:')):
        body,start,end=extract(sources[file],anchor);assert body==sources[file][start:end]
        extracts[key]=dict(source=(base/file).as_posix(),start_byte=start,end_byte=end,body_sha256=hashlib.sha256(body.encode()).hexdigest(),source_sha256=hashlib.sha256(sources[file].encode()).hexdigest(),body=body)
    threshold='        let threshold = [f32::from_bits(0x3586_37bd); 4];'
    assert sources['settings.rs'].count(threshold)==1;extracts['threshold']=dict(source=(base/'settings.rs').as_posix(),body_sha256=hashlib.sha256(threshold.encode()).hexdigest(),body=threshold)
    generated='''use skate_core::{point_graph::PointGraph,riding::ground_force::GroundForceSettings};
use skate_data::collections::Collections;
mod settings {
use super::*;
'''+extracts['curve8']['body']+'''
}
pub mod pumping {
use skate_core::riding::pumping::settings::{PumpingSettings,PumpingMode};
use skate_data::collections::Collections;
pub struct GroundPumping {pub settings:PumpingSettings,pub modes:[GroundPumpingMode;5]}
#[derive(Clone,Copy)]
pub struct GroundPumpingMode {pub controller:PumpingMode,pub unintentional_scalar:f32}
impl GroundPumping {
'''+extracts['load']['body']+'\n'+extracts['mode']['body']+'''
}
}
pub fn ground_force(data:&Collections)->Result<GroundForceSettings,String> {
let f=|class,field|data.float(class,"default",field);
'''+threshold+'\nOk('+extracts['ground_force']['body']+')\n}\n'
    path=output/'stock-bindings.rs';path.write_text(generated)
    for key,value in extracts.items():
        assert generated.count(value['body'])==1,(key,'body was changed or duplicated');del value['body']
    report=dict(extractions=extracts,generated_sha256=digest(path),boundary='Only unused GroundPumping dependencies are omitted from the settings shell; tested load/mode/curve8 methods and ground-force settings expression remain byte-identical. All runtime geometry/control/force/state calls use the original compiled skate-core module; there are no stub callbacks.')
    (output/'stock-bindings-provenance.json').write_text(json.dumps(report,indent=2)+'\n')


def build_native(output):
    live=PLUGIN/'Source/AtelierSkate/Private/Native';snapshot=output/'native-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();units=('NativeMath','NameId','Settings','StockSettingsReader','GroundForce','Pumping')
    for unit in units:
        for ext in ('h','cpp'):shutil.copy2(live/f'{unit}.{ext}',snapshot/f'{unit}.{ext}')
    shutil.copy2(live/'DataReader.h',snapshot/'DataReader.h');shutil.copy2(PLUGIN/'Tests/Native/pumping_ground_force_probe.cpp',snapshot/'pumping_ground_force_probe.cpp')
    (output/'native-source-provenance.json').write_text(json.dumps({p.name:digest(p) for p in sorted(snapshot.iterdir())},indent=2)+'\n');binary=output/'pumping-ground-force-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{unit}.cpp') for unit in units],str(snapshot/'pumping_ground_force_probe.cpp'),'-o',str(binary)],check=True);return binary


def coverage(data,rows):
    at=0
    def word():
        nonlocal at
        v=struct.unpack_from('<I',data,at)[0];at+=4;return v
    def words(n):return [word() for _ in range(n)]
    def string():
        nonlocal at
        n=word();s=data[at:at+n].decode();at+=n;return s
    assert word()==118;settings=words(118);assert word()==len(rows);decoded=[];counts=Counter();updates=[];last_state=None;errors=Counter();first=0;calculations=0;bounds=0
    for row in rows:
        assert word()==row['index'];assert word()==row['operation'];counts[OPERATIONS[row['operation']]]+=1
        if not word():
            error=string();errors[error]+=1;assert row['operation']==7 and row['words'][0] in (5,0xffffffff);decoded.append(dict(row=row,error=error));continue
        values=words(word());decoded.append(dict(row=row,values=values));op=row['operation']
        if op in (0,1,2,8):
            state=values[-28:];assert len(state)==28
            assert state[21]==bits(0.) and state[22:27]==[state[i] for i in (14,15,16,17,12)] and state[27]==state[20]
            if op==0:assert state==[0]*28
            if row.get('proof')=='first':
                # Source first Update caches pose/height and clears acceleration,
                # but deliberately retains caller-supplied intentional byte.
                assert state[19]==1 and state[20]==0x91 and state[12]==bits(0.)
                assert state[:8]==row['words'][3:11];first+=1
            if row.get('proof')=='calculate_prefix':
                assert last_state is not None
                for index in list(range(13))+[18,19,20]:assert state[index]==last_state[index],(row,index,'Calculate changed Update-owned state')
                calculations+=1
            if row.get('proof')=='mode_bound':
                dt=scalar(0x3c888889 if row['fixed'] else row['dt']);mode=settings[86+row['mode']*5:91+row['mode']*5]
                limit=scalar(mode[1 if row['sign']>0 else 0])*dt
                assert state[12]==bits(limit if row['sign']>0 else -limit),(row,'selected pumping mode bound did not execute')
                bounds+=1
            if op==1:updates.append(state)
            last_state=state
        elif op in (3,4,5):
            assert len(values)==8 and values[4:6]==[0,0] and values[7]==0
            assert values[6]==(0 if op==3 else row['words'][1 if op==4 else 8])
    assert at==len(data),(at,len(data));assert first==32 and calculations==128 and bounds==20
    accelerations={u[12] for u in updates};assert len(accelerations)>32,'Pumping acceleration never responds to actual trajectory/mode'
    assert any(scalar(v)>0 for v in accelerations) and any(scalar(v)<0 for v in accelerations),'Both acceleration and absorption branches are required'
    assert len({u[9] for u in updates})>16 and len({tuple(u[14:18]) for u in updates})>64
    assert {u[20] for u in updates if u[20]!=0x91}=={0,1}
    assert errors=={'Invalid pumping physics mode 5':1,'Invalid pumping physics mode 4294967295':1}
    return dict(records=len(rows),operations=dict(counts),settings_words=len(settings),first_update_preserves_intentional_byte=first,calculate_preserves_update_owned_prefix=calculations,selected_mode_upper_lower_bounds=bounds,pump_acceleration_variants=len(accelerations),missing_mode_errors=dict(errors)),decoded


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('assets','output','target-dir'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    commands,rows=corpus();validate_input(commands,rows);(output/'input.bin').write_bytes(commands);stock_bindings(output)
    reference=build_probe(output,'pumping-ground-force-reference',PLUGIN/'Tests/Reference/pumping_ground_force_probe.rs',args.target_dir)
    native=build_native(output);settings=output/'settings.skate';settings.write_bytes(converter.encode_settings(args.assets/'private/stock/skater-collections.json'))
    expected=subprocess.check_output([str(reference),str(args.assets.resolve())],input=commands);actual=subprocess.check_output([str(native),str(settings)],input=commands)
    (output/'reference.bin').write_bytes(expected);(output/'native.bin').write_bytes(actual)
    if actual!=expected:
        first=next((i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b),min(len(actual),len(expected)))
        (output/'first-divergence.json').write_text(json.dumps(dict(byte=first,expected_bytes=len(expected),actual_bytes=len(actual)),indent=2)+'\n');raise AssertionError(f'Pumping/ground force differ at byte {first}')
    proof,decoded=coverage(expected,rows);(output/'original-trace.json').write_text(json.dumps(decoded,indent=2)+'\n')
    report=dict(passed=True,coverage=proof,output_bytes=len(actual),output_sha256=hashlib.sha256(actual).hexdigest(),comparison='Exact bytes for unchanged original NativePumpingGeometry + controller Update/Calculate/reset/output, native pump force and GroundForce; stock bindings extracted verbatim with hashed boundaries.',limitations='Ground/revert state scheduling, caller deck-angle/sample preparation, queue tags/timing and whole gameplay/session parity are separate. Stock setting error diagnostics are not compared; valid values, both eight-point graph representations, modes and explicit invalid-mode errors are covered.',stock_data_format='Project-native ATATTR01; original collection parsing exists only in tooling/oracle.',reference_provenance_sha256=digest(output/'pumping-ground-force-reference-provenance.json'),stock_bindings_provenance_sha256=digest(output/'stock-bindings-provenance.json'),native_source_provenance_sha256=digest(output/'native-source-provenance.json'))
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
