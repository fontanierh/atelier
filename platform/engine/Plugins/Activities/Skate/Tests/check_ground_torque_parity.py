#!/usr/bin/env python3
"""Actual frozen slide friction/straighten/heading/anti-flip and stock profiles.

Every numeric kernel runs unchanged in the Rust oracle. Its valid settings
expressions/helpers are extracted verbatim with hashes and boundary assertions.
Run builds/probes through the shared render lock/memory guard.
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
from check_gesture_parity import converter,PLUGIN
from check_pumping_ground_force_parity import bits,floats,scalar,extract
from reference_build import build_probe
from session_parity import REFERENCE_REVISION,digest

OPERATIONS=('slide_friction','straighten','heading','anti_flip','heading_history')
LENGTHS=(15,15,36,14,1)


def corpus():
    rng=random.Random(0x82d92970);rows=[]
    def add(op,profile,values,**meta):
        assert len(values)==LENGTHS[op];rows.append(dict(index=len(rows),operation=op,profile=profile,words=values,**meta))
    def vector():return [rng.uniform(-2,2) for _ in range(4)]
    def frame(angle):
        c,s=math.cos(angle),math.sin(angle)
        return [c,s,.137,.317,-s,c,.731,-.113,.137,-.317,.719,.517,4.,3.,2.,1.]
    for profile in range(5):
        for tick in range(96):
            normal,velocity,side=vector(),vector(),vector()
            add(0,profile,floats([rng.uniform(-.5,3)]+normal+velocity+side+[rng.uniform(-3,30),rng.uniform(-1,2)]))
            # Stock Straighten's window is 0.1..0.5s for scalar2764 in0..1;
            # its response is zero after that window. Keep the same three RNG
            # draws while exercising positive curve/turn response on every row.
            add(1,profile,floats([rng.uniform(.003,.063),rng.uniform(0,1),rng.uniform(-.517,.517)]+side+velocity+normal),proof='active_straighten_window')
            balance=(0.,.137,-.137)[tick%3];manual=(0.,.731,-.731)[tick%3]
            heading=floats([balance,manual])+[(0,0x08000000,0x04000000,0x0c000000)[tick%4]]+floats([rng.choice((1/120,1/60,.05)),rng.uniform(-30,30),rng.uniform(-3,30),rng.uniform(-2,2),rng.uniform(-1,2)]+velocity+normal+side+frame((tick-48)*.05))
            add(2,profile,heading)
            add(3,profile,[0x20000000 if tick%7==0 else 0]+floats([balance]+normal+side+velocity))
        for normal_y in (-1.0000001,-1.,-.731,-0.,0.,.731,1.,1.0000001):
            for heading_time in (-.137,-0.,0.,.137,1.,10.):
                add(0,profile,floats([heading_time,0.,normal_y,0.,.317,1.,-.137,2.,.731,.137,.317,.731,-.113,3.137,.517]))
        for turn in (-2.,-.137,-0.,0.,.137,2.):
            for speed in (-3.,-0.,0.,3.):
                add(1,profile,floats([.03125,.517,turn,0.,0.,1.,.317,1.,0.,speed,.731,0.,1.,0.,.137]))
        for balance in (-.137,0.,.137):
            for flag in (0,0x20000000):
                for axis in ((0.,0.,0.,0.),(1e-6,0.,0.,.731),(1.0000001e-6,0.,0.,-.137),(1.,0.,0.,.137)):
                    add(3,profile,[flag]+floats([balance]+list(axis)+[0.,0.,1.,.731]+[.137,.919,.317,-.517]))
        # Manual wrong-wheel gates have both wheel flags, both balance signs,
        # and shared live history, followed by a general branch clearing it.
        for balance in (-.137,.137):
            for flag in (0,0x08000000,0x04000000,0x0c000000):
                add(4,profile,[bits(.731)])
                for tick in range(8):
                    add(2,profile,floats([balance,.731])+[flag]+floats([1/60,3.137,tick*.731,.137,.517]+[1.,2.,3.,.317]+[0.,1.,0.,.731]+[.317,.731,.137,.517]+frame(.317)),proof='manual',group=(balance,flag))
                add(2,profile,floats([0.,.731])+[flag]+floats([1/60,3.137,4.,.137,.517]+[1.,2.,3.,.317]+[0.,1.,0.,.731]+[.317,.731,.137,.517]+frame(.317)),proof='history_clear')
        # Matrix fourth lanes/translation are source-ignored; keep them raw.
        base=frame(.517);changed=base[:]
        for index in (3,7,11,12,13,14,15):changed[index]=rng.uniform(-10,10)
        for key,matrix in (('ignored_a',base),('ignored_b',changed)):
            add(2,profile,floats([0.,0.])+[0]+floats([1/60,5.,3.,.731,.517]+[1.,2.,3.,.317]+[0.,1.,0.,.731]+[.317,.731,.137,.517]+matrix),proof=key)
    encoded=struct.pack('<I',len(rows))+b''.join(struct.pack('<'+'I'*(len(r['words'])+2),r['operation'],r['profile'],*r['words']) for r in rows)
    return encoded,rows


def validate_input(data,rows):
    words=struct.unpack('<'+'I'*(len(data)//4),data);assert words[0]==len(rows);at=1
    for row in rows:
        n=LENGTHS[row['operation']];assert words[at:at+2]==(row['operation'],row['profile']);assert list(words[at+2:at+n+2])==row['words'];at+=n+2
    assert at==len(words)


def stock_bindings(output):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip());path=(PLUGIN/'ThirdParty/skate-runtime/crates/skate-host/src/physics/ground_runtime/settings.rs').relative_to(root).as_posix()
    source=subprocess.check_output(['git','show',f'{REFERENCE_REVISION}:{path}'],cwd=root).decode();slices={}
    for key,anchor in (('curve8','pub(super) fn curve8('),('curve16','fn curve16('),('slide','SlideFrictionSettings {\n                angle_response:'),('straighten','StraightenSettings {\n                time_response:'),('heading','HeadingSettings {\n                manual_wrong_wheel_scalar:'),('anti_flip','AntiFlipSettings {\n                axis_96_response:')):
        body,start,end=extract(source,anchor);assert body==source[start:end];slices[key]=dict(start_byte=start,end_byte=end,body_sha256=hashlib.sha256(body.encode()).hexdigest(),body=body)
    threshold='        let threshold = [f32::from_bits(0x3586_37bd); 4];';assert source.count(threshold)==1
    generated='''use skate_core::{point_graph::PointGraph,riding::{slide_friction::SlideFrictionSettings,straighten::StraightenSettings,heading::HeadingSettings,anti_flip::AntiFlipSettings}};
use skate_data::collections::Collections;
pub struct GroundTorqueSettings {pub slide:SlideFrictionSettings,pub straighten:StraightenSettings,pub heading:HeadingSettings,pub anti_flip:AntiFlipSettings}
'''+slices['curve8']['body']+'\n'+slices['curve16']['body']+'''
pub fn load(data:&Collections,surface:&str)->Result<GroundTorqueSettings,String> {
let f=|class,field|data.float(class,"default",field);
let s=|field|data.float("physics_surfaces",surface,field);
let c8=|class,field|curve8(data,class,"default",field);
let c16=|class,field|curve16(data,class,"default",field);
'''+threshold+'\nOk(GroundTorqueSettings {\n'+',\n'.join(key+':'+slices[key]['body'] for key in ('slide','straighten','heading','anti_flip'))+'\n})\n}\n'
    destination=output/'ground-torque-stock-bindings.rs';destination.write_text(generated)
    for key,value in slices.items():assert generated.count(value['body'])==1;del value['body']
    report=dict(reference_revision=REFERENCE_REVISION,source=path,source_sha256=hashlib.sha256(source.encode()).hexdigest(),extractions=slices,threshold_sha256=hashlib.sha256(threshold.encode()).hexdigest(),generated_sha256=digest(destination),boundary='Only stock value binding shell. Original helper methods and all four settings initializers are verbatim; numerical methods and state run in untouched skate-core. No stubbed callbacks.')
    (output/'stock-bindings-provenance.json').write_text(json.dumps(report,indent=2)+'\n')


def build_native(output):
    live=PLUGIN/'Source/AtelierSkate/Private/Native';snapshot=output/'native-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();units=('NativeMath','NameId','Settings','GroundForce','SlideFriction','Straighten','Heading','AntiFlip','GroundTorqueSettings')
    for unit in units:
        for ext in ('h','cpp'):shutil.copy2(live/f'{unit}.{ext}',snapshot/f'{unit}.{ext}')
    shutil.copy2(live/'DataReader.h',snapshot/'DataReader.h');shutil.copy2(PLUGIN/'Tests/Native/ground_torque_probe.cpp',snapshot/'ground_torque_probe.cpp')
    (output/'native-source-provenance.json').write_text(json.dumps({p.name:digest(p) for p in sorted(snapshot.iterdir())},indent=2)+'\n');binary=output/'ground-torque-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/f'{unit}.cpp') for unit in units],str(snapshot/'ground_torque_probe.cpp'),'-o',str(binary)],check=True);return binary


def coverage(data,rows):
    at=0
    def word():
        nonlocal at
        v=struct.unpack_from('<I',data,at)[0];at+=4;return v
    def words(n):return [word() for _ in range(n)]
    assert word()==5;profiles=[]
    for _ in range(5):assert word()==228;profiles.append(words(228))
    assert word()==len(rows);counts=Counter();variants=[set() for _ in range(4)];fourth=[0]*4;proof={};manual=0;clear=0;disabled=0;trace=[]
    for row in rows:
        assert word()==row['index'];op=word();assert op==row['operation'];values=words(word());assert len(values)==(8,4,5,4,1)[op];counts[OPERATIONS[op]]+=1
        trace.append(dict(row=row,values=values))
        if op<4:variants[op].add(tuple(values[:4]));fourth[op]+=scalar(values[3])!=0
        if op==0:assert values[4:]==[0]*4
        elif op==2:
            is_manual=scalar(row['words'][0])!=0 and scalar(row['words'][1])!=0
            if not is_manual:assert values[4]==bits(0.)
            if row.get('proof')=='manual':assert values[4]!=bits(0.);manual+=1
            if row.get('proof')=='history_clear':assert values[4]==bits(0.);clear+=1
            if row.get('proof') in ('ignored_a','ignored_b'):proof[(row['profile'],row['proof'])]=values
        elif op==3 and row['words'][0]&0x20000000:assert values==[0]*4;disabled+=1
    assert at==len(data),(at,len(data));assert manual==320 and clear==40 and disabled>=60
    assert all(len(v)>128 for v in variants) and all(n>128 for n in fourth),(list(map(len,variants)),fourth)
    for profile in range(5):assert proof[(profile,'ignored_a')]==proof[(profile,'ignored_b')]
    assert len({tuple(p[80:83]+p[115:119]) for p in profiles})>1,'Surface profiles did not change source settings'
    return dict(records=len(rows),operations=dict(counts),settings_words=5*228,torque_force_variants=list(map(len,variants)),nonzero_fourth_lanes=fourth,manual_retained_history_updates=manual,general_branch_history_clears=clear,anti_flip_disabled_early_returns=disabled,source_ignored_matrix_lanes=5),trace


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('assets','output','target-dir'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    commands,rows=corpus();validate_input(commands,rows);(output/'input.bin').write_bytes(commands);stock_bindings(output)
    reference=build_probe(output,'ground-torque-reference',PLUGIN/'Tests/Reference/ground_torque_probe.rs',args.target_dir);native=build_native(output)
    settings=output/'settings.skate';settings.write_bytes(converter.encode_settings(args.assets/'private/stock/skater-collections.json'))
    expected=subprocess.check_output([str(reference),str(args.assets.resolve())],input=commands);actual=subprocess.check_output([str(native),str(settings)],input=commands)
    (output/'reference.bin').write_bytes(expected);(output/'native.bin').write_bytes(actual)
    if actual!=expected:
        first=next((i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b),min(len(actual),len(expected)))
        (output/'first-divergence.json').write_text(json.dumps(dict(byte=first,expected_bytes=len(expected),actual_bytes=len(actual)),indent=2)+'\n');raise AssertionError(f'Ground torque differs at byte {first}')
    proof,trace=coverage(expected,rows);(output/'original-trace.json').write_text(json.dumps(trace,indent=2)+'\n')
    result=dict(passed=True,coverage=proof,output_bytes=len(actual),output_sha256=hashlib.sha256(actual).hexdigest(),comparison='Exact unchanged original SlideFriction/Straighten/Heading/AntiFlip calls, retained actual heading history, four lanes and all five actual surface profiles. Settings helper/initializer extractions are hash-verified.',limitations='Valid stock-setting values; malformed-loader diagnostics are not compared. Actual ground force ordering/queue ownership, board-state scheduling, and whole-session parity remain separate.',stock_data_format='Project-native ATATTR01; original collection reader exists only in tooling/oracle.',reference_provenance_sha256=digest(output/'ground-torque-reference-provenance.json'),stock_bindings_provenance_sha256=digest(output/'stock-bindings-provenance.json'),native_source_provenance_sha256=digest(output/'native-source-provenance.json'))
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
