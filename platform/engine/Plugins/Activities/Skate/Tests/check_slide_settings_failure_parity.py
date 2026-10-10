#!/usr/bin/env python3
"""Slide's whole frozen host constructor: ordered failures and immutable output.

Run only through the coordinator's render/memory guard.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import check_ground_control_settings_parity as ground
import check_animation_trees_parity as trees
from check_gesture_parity import converter,PLUGIN
from reference_build import build_probe


def fields():
    result=[]
    for surface in ground.SURFACES:
        result += [('physics_surfaces',surface,'Powerslide_SpeedToForce','fixed_curve')]
        result += [('physics_surfaces',surface,name,'float') for name in ('Powerslide_YawStrength','Powerslide_YawDamping','WheelStaticFriction','WheelDynamicFriction')]
        result += [('physicswheels','default','WheelRestitution','float')]
    result += [('physics_slide','default',name,'fixed_curve') for name in ('slide_input_remap','Hash_DE162591FD9D91D7','Hash_91282E2CC4252731','Hash_2AD93E5ABA231D2')]
    result += [('physicswheels','default',name,'float') for name in ('SoftestWheelPowerslideFactor','SoftestWheelPowerslideSpinFactor')]
    result += [('physics_slide','default',name,'float') for name in ('AngularForceScalar','PowerSlideForceYOffset')]
    result += [('physics_manual','default','PowerSlideScalar','float')]
    return result


def corpus(original):
    queries=fields();selected={};allowed={}
    for query in queries:
        chain,name=ground.resolve(original,query)
        for r in chain:selected[(r['class'],r['key'])]=r
        allowed.setdefault((chain[-1]['class'],chain[-1]['key']),set()).add(name)
    minimal=dict(version=1,collections=[])
    for key,r in selected.items():
        r=copy.deepcopy(r);r['fields']={n:v for n,v in r['fields'].items() if n in allowed.get(key,set())};minimal['collections'].append(r)
    fixtures=[original,minimal];rows=[dict(fixture=0,tag='stock'),dict(fixture=1,tag='minimal-stock')]
    def add(data,tag,error=None):fixtures.append(data);rows.append(dict(fixture=len(fixtures)-1,tag=tag,expected_error=error))
    unique=list(dict.fromkeys(queries))
    for index,query in enumerate(unique):
        data=copy.deepcopy(minimal)
        for remaining in unique[index:]:ground.mutate(data,remaining,ground.invalid(remaining))
        add(data,f'read-order-{index}',ground.expected_invalid(query))
        data=copy.deepcopy(minimal);chain,name=ground.resolve(data,query);del chain[-1]['fields'][name];chain[-1]['parent']='';add(data,'missing-field','Missing stock field '+f'{query[0]}/{query[1]}/{query[2]}')
        if query[3]=='float':
            for word in ('7FC00000','7F800000','FF800000'):
                data=copy.deepcopy(minimal);ground.mutate(data,query,dict(type='EA::Reflection::Float',data=word));add(data,'non-finite','Non-finite stock float '+f'{query[0]}/{query[1]}/{query[2]}')
            data=copy.deepcopy(minimal);ground.mutate(data,query,dict(type='EA::Reflection::Float',data='3F8000003F800000'));add(data,'scalar-size','Expected 1 big-endian words, found 16 bytes of hex')
        else:
            for length in (16,20,18):
                payload=('DEADBEEF123456787FC0000080000000' if length==20 else '')+''.join(f'{struct.unpack("<I",struct.pack("<f",i*.137))[0]:08X}' for i in range(16 if length!=18 else 18))
                data=copy.deepcopy(minimal);ground.mutate(data,query,dict(type='EA::Reflection::Int32',data=payload));add(data,'curve-layout',f'Expected 20 big-endian words, found {length*8} bytes of hex' if length!=20 else None)
            for payload in ('0'*128,'0'*160,'G'*160,'0'*159,'\u00a0'+'0'*160+'\u3000','\u2007'+'0'*160+'\n'):
                data=copy.deepcopy(minimal);ground.mutate(data,query,dict(type='EA::Reflection::Text',data=payload));add(data,'curve-text')
    for category,key in dict.fromkeys((q[0],q[1]) for q in queries):
        data=copy.deepcopy(minimal);data['collections']=[r for r in data['collections'] if (ground.identity(r['class']),ground.identity(r['key']))!=(ground.identity(category),ground.identity(key))];add(data,'missing-collection','Missing stock collection '+f'{category}/{key}')
    data=copy.deepcopy(minimal)
    for r in data['collections']:
        r['class']=f'Hash_{converter.name_id(r["class"]):016X}';r['key']=f'Hash_{converter.name_id(r["key"]):016X}'
        if r['parent']:r['parent']=f'Hash_{converter.name_id(r["parent"]):016X}'
        r['fields']={f'Hash_{converter.name_id(n):016X}':v for n,v in r['fields'].items()}
    add(data,'numeric-alias')
    data=copy.deepcopy(minimal);q=unique[1];chain,name=ground.resolve(data,q);r=chain[-1];r['fields'][f'Hash_{converter.name_id(q[2]):016X}']=dict(type='EA::Reflection::Float',data='3E123456');add(data,'direct-name-priority')
    data=copy.deepcopy(minimal);r=ground.record(data,'physics_slide','default');child=copy.deepcopy(r);child.update(key='parent-slide',parent=r['parent']);r.update(parent='parent-slide',fields={});data['collections'].append(child);add(data,'inheritance')
    data=copy.deepcopy(minimal);r=ground.record(data,'physics_slide','default');chain,name=ground.resolve(data,unique[-3]);del chain[-1]['fields'][name];r['parent']='cycle';child=copy.deepcopy(r);child.update(key='cycle',parent='default',fields={});data['collections'].append(child);add(data,'inheritance-cycle','Cyclic stock collection inheritance physics_slide/default')
    return fixtures,rows


def encode(rows):return struct.pack('<I',len(rows))+b''.join(struct.pack('<I',r['fixture']) for r in rows)


def prepare_source(output):
    relative='crates/skate-host/src/physics/slide_state/settings.rs';source=trees.source_at_reference(relative)
    appended='\nmod stock {use super::*;pub struct SlideState {pub state:slide_state::SlideState,pub settings:SlideSettings,pub surfaces:Vec<(SlideSurface,RetailContactMaterial)>,pub manual_scalar:f32}\nmod settings {\n'+source+'\n}}\n'
    probe=output/'slide-settings-failure-oracle.rs';probe.write_text((PLUGIN/'Tests/Reference/slide_settings_failure_probe.rs').read_text()+appended)
    (output/'extraction-provenance.json').write_text(json.dumps(dict(original_path=relative,whole_verbatim_module_sha256=hashlib.sha256(source.encode()).hexdigest(),probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(),boundary='Entire original host settings module and original Collections readers; only owner declaration exposes immutable successful results.'),indent=2)+'\n');return probe


def build_simulation(output):
    live=PLUGIN/'Source/AtelierSkate/Private/Simulation';code=output/'simulation-source'
    if code.exists():shutil.rmtree(code)
    code.mkdir();files=('NameId','Settings','StockSettingsReader','SlideStateSettings')
    for p in list(live.glob('*.h'))+[live/(name+'.cpp') for name in files]:shutil.copyfile(p,code/p.name)
    probe=code/'slide_settings_failure_probe.cpp';shutil.copyfile(PLUGIN/'Tests/Simulation/slide_settings_failure_probe.cpp',probe);(output/'simulation-source-provenance.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(code.iterdir())},indent=2)+'\n')
    simulation=output/'slide-settings-failure-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(code),*[str(code/(name+'.cpp')) for name in files],str(probe),'-o',str(simulation)],check=True);return simulation


def decode(data,rows):
    at=0;frames=[]
    def word():
        nonlocal at
        value=struct.unpack_from('<I',data,at)[0];at+=4;return value
    for index,row in enumerate(rows):
        assert word()==index;ok=word();frame=dict(ok=ok)
        if ok:frame['words']=[word() for _ in range(174)]
        else:
            n=word();frame['error']=data[at:at+n].decode();at+=n;frame['unchanged']=word()
        frames.append(frame)
    assert at==len(data),(at,len(data));return frames


def coverage(frames,rows):
    tags=Counter();statuses=Counter();errors=Counter();ordered=0;stock=frames[0]['words']
    assert frames[0]['ok'] and frames[1]['words']==stock
    for frame,row in zip(frames,rows):
        tags[row['tag']]+=1;statuses[frame['ok']]+=1
        if row.get('expected_error') is not None:assert not frame['ok'] and frame['error']==row['expected_error'],(row,frame)
        if not frame['ok']:assert frame['unchanged']==1;errors[frame['error'].split(' physics_',1)[0].split(' at physics_',1)[0]]+=1
        if row['tag'].startswith('read-order-'):ordered+=1
        if row['tag'] in ('numeric-alias','direct-name-priority','inheritance'):assert frame['ok'] and frame['words']==stock,(row,frame)
    assert ordered==len(dict.fromkeys(fields())) and all(statuses.values())
    assert all(any(frame['ok']==ok for frame,row in zip(frames,rows) if row['tag']==tag) for tag in ('curve-layout','curve-text') for ok in (0,1))
    return dict(tags=dict(tags),statuses=dict(statuses),distinct_first_failed_fields=ordered,original_reads=len(fields()),repeated_restitution_reads=5,error_classes=dict(errors),failure_output_preserved=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    source=args.assets/'private/stock/skater-collections.json';fixtures,rows=corpus(json.loads(source.read_text()));root=ground.prepare_fixtures(output,fixtures,source);commands=encode(rows);(output/'input.bin').write_bytes(commands);(output/'cases.json').write_text(json.dumps(rows,indent=2)+'\n');reference=build_probe(output,'slide-settings-failure-reference',prepare_source(output),args.target_dir);simulation=build_simulation(output)
    def expected(data):return subprocess.check_output([str(reference),str(root)],input=data)
    def actual(data):return subprocess.check_output([str(simulation),str(root)],input=data)
    oracle=expected(commands);candidate=actual(commands);(output/'reference.bin').write_bytes(oracle);(output/'simulation.bin').write_bytes(candidate);frames=decode(oracle,rows);(output/'reference-trace.json').write_text(json.dumps(frames,indent=2)+'\n')
    if oracle!=candidate:
        lo=0;hi=len(rows)
        while hi-lo>1:
            mid=(lo+hi)//2
            if expected(encode(rows[lo:mid]))==actual(encode(rows[lo:mid])):lo=mid
            else:hi=mid
        (output/'first-divergence-input.bin').write_bytes(encode(rows[lo:hi]));(output/'first-divergence.json').write_text(json.dumps(dict(case=lo,record=rows[lo]),indent=2)+'\n');raise AssertionError(f'Slide settings failure differs in case {lo}')
    result=dict(passed=True,cases=len(rows),fixtures=len(fixtures),coverage=coverage(frames,rows),output_bytes=len(oracle),output_sha256=hashlib.sha256(oracle).hexdigest(),comparison='Whole original Slide constructor: all surface/material/core reads, first-failed field ordering, scalar/curve/raw Text errors, aliases/inheritance and immutable output on failure.',limitations='Decoded simulation settings boundary; malformed raw JSON and invalid numeric hex rejected by converter are outside this reader comparison.')
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
