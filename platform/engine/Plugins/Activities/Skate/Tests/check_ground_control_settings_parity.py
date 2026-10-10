#!/usr/bin/env python3
"""Compare standalone ground settings against verbatim frozen host bindings.

All stock mode/surface combinations and representable simulation-data failure paths
run original Collections readers. Compile/run only under the parent's guard.
"""
import argparse
from collections import Counter
import copy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import check_animation_trees_parity as trees
from check_animation_playback_parity import Stream
from check_gesture_parity import converter, PLUGIN
from reference_build import build_probe

MODES=('easy','normal','hardcore','motorized','test')
SURFACES=('smooth','rough','slow','slippery','veryslow')

@lru_cache(maxsize=None)
def identity(name):return converter.name_id(name)


def fields(op,mode='normal',surface='smooth'):
    def group(category,names,kind='float',key='default'):return [(category,key,name,kind) for name in names]
    if op==0:return group('physics_manual',['NoiseVsSpeed'],'curve')+group('physics_manual',['TorqueScalarWithNoContact','TorqueBleedOffWithNoContact','StartTorqueScalar','ProceduralNoiseScalar','ProceduralNoiseFreq','PowerScalar_P','PowerScalar_I','PowerScalar_D','ManualScalar_P','ManualScalar_I','ManualScalar_D','MaxTiltAngle','MaxAngleDiff','D_Scalar_Limit','BrakeTiltAngle','AnimationNoiseScalar'])
    if op==1:return group('physics_mode',['Hash_84CB2F459F3FC811'],key=mode)+group('physics_mode',['Hash_F8CBC0F5FEF2240E'],'bool',mode)
    if op==2:return group('physics_brakes',['FootBrakeForce','TailBrakeForce','SlowSpeed'])+group('physics_push',['MaxPushableSpeed'])+group('physics_mode',['MaxPushDVStart','MaxPushDVEnd'],key=mode)
    if op==3:return group('physics_brakes',['SlowSpeed','ManualSpinDragSpeed','ManualSpinDragNormal','ManualSpinDrag'])
    if op==4:return group('physics_speed_conservation',['NegativeGeneralAmount','MaxGravityAcceleration','Gravity','GeneralAmount','CoffinAcceleration'])+group('physics_surfaces',['Friction_MaxSpeedChange'],key=surface)+group('physics_surfaces',['FrictionVsSpeedNew'],'curve',surface)+group('physics_manual',['SpinCorrectiveForce','MinSpeedForCorrection','MaxSpeedForCorrection'])+group('physics_friction',['NoInputTime'])+group('physics_friction',['FrictionVsSpeed_NoInput','FrictionVsSpeed_Manual'],'curve')+group('physics_mode',['MotorEnabled'],'bool',mode)+group('physics_mode',['MotorTopSpeed'],key=mode)
    if op==5:return group('physics_feet',['WallRideAntiGravityVsTime'],'fixed_curve')+group('physics_feet',['WallRideMaxDotFloorWall','WallRideFootForceTime','WallRideAutoJumpHeight','WallRideMaxTime','WallRideVelTimeToConsider','WallRideAutoJumpYDownScalar','WallRideAutoJumpForce'])
    raise ValueError(op)


def record(data,category,key):
    return next((r for r in data['collections'] if identity(r['class'])==identity(category) and identity(r['key'])==identity(key)),None)


def resolve(data,query):
    category,key,name,_=query;chain=[]
    for _ in range(len(data['collections'])+1):
        r=record(data,category,key)
        if r is None:raise AssertionError(('missing source fixture record',query,key))
        chain.append(r)
        field=name if name in r['fields'] else next((n for n in r['fields'] if identity(n)==identity(name)),None)
        if field is not None:return chain,field
        assert r['parent'],query;key=r['parent']
    raise AssertionError(('source inheritance cycle',query))


def minimal_fixture(original):
    selected={};allowed={}
    queries={query for op in range(6) for mode in MODES for surface in SURFACES for query in fields(op,mode,surface)}
    for query in sorted(queries):
        chain,name=resolve(original,query)
        for r in chain:selected[(r['class'],r['key'])]=r
        allowed.setdefault((chain[-1]['class'],chain[-1]['key']),set()).add(name)
    out=dict(version=1,collections=[])
    for key,r in selected.items():
        r=copy.deepcopy(r);r['fields']={name:field for name,field in r['fields'].items() if name in allowed.get(key,set())};out['collections'].append(r)
    return out


def mutate(data,query,value):
    chain,name=resolve(data,query);chain[-1]['fields'][name]=value


def invalid(query):
    kind=query[3]
    return dict(type='EA::Reflection::Int32',data='00000000') if kind in ('float','bool') else dict(type='EA::Reflection::Float',data='00000000')


def expected_invalid(query):
    category,key,name,kind=query;path=f'{category}/{key}/{name}'
    if kind=='float':return 'Expected float at '+path
    if kind=='bool':return 'Expected boolean at '+path
    if kind=='fixed_curve':return 'Expected 20 big-endian words, found 8 bytes of hex'
    return 'Invalid native eight-point graph '+path


def corpus(original):
    minimal=minimal_fixture(original);fixtures=[original,minimal];rows=[]
    def add(op,fixture=0,mode='normal',surface='smooth',surface_id=1,tag='',expected_error=None):rows.append(dict(op=op,fixture=fixture,mode=mode,surface=surface,surface_id=surface_id,tag=tag,expected_error=expected_error))
    def fixture(data):fixtures.append(data);return len(fixtures)-1
    for mode in MODES:
        for surface in SURFACES:
            for op in range(6):add(op,mode=mode,surface=surface,tag='stock-mode-surface')
    # Every field is the first failed read while all its successors are invalid.
    # Verbatim host initializers establish which failure must win.
    for op in range(6):
        queries=fields(op)
        for at,query in enumerate(queries):
            data=copy.deepcopy(minimal)
            for remaining in queries[at:]:mutate(data,remaining,invalid(remaining))
            add(op,fixture(data),tag=f'read-order-{op}-{at}',expected_error=expected_invalid(query))
            data=copy.deepcopy(minimal);chain,name=resolve(data,query);del chain[-1]['fields'][name];chain[-1]['parent']=''
            add(op,fixture(data),tag='missing-field',expected_error='Missing stock field '+f'{query[0]}/{query[1]}/{query[2]}')
            if query[3]=='float':
                for word in ('7FC00000','7F800000','FF800000'):
                    data=copy.deepcopy(minimal);mutate(data,query,dict(type='EA::Reflection::Float',data=word));add(op,fixture(data),tag='non-finite',expected_error='Non-finite stock float '+f'{query[0]}/{query[1]}/{query[2]}')
                data=copy.deepcopy(minimal);mutate(data,query,dict(type='EA::Reflection::Float',data='3F8000003F800000'));add(op,fixture(data),tag='scalar-size',expected_error='Expected 1 big-endian words, found 16 bytes of hex')
            elif query[3]=='bool':
                for payload in ('00','01','00000000','0100FF00','00FF0000','02',''):
                    data=copy.deepcopy(minimal);mutate(data,query,dict(type='EA::Reflection::Bool',data=payload));add(op,fixture(data),tag='boolean-first-byte',expected_error='Invalid stock boolean '+f'{query[0]}/{query[1]}/{query[2]}' if payload in ('02','') else None)
            else:
                for length in (16,20,18):
                    payload=('DEADBEEF123456787FC0000080000000' if length==20 else '')+''.join(f'{struct.unpack("<I",struct.pack("<f",i*.137))[0]:08X}' for i in range(16 if length!=18 else 18))
                    data=copy.deepcopy(minimal);mutate(data,query,dict(type='EA::Reflection::Int32',data=payload));error=None
                    if query[3]=='fixed_curve' and length!=20:error=f'Expected 20 big-endian words, found {length*8} bytes of hex'
                    elif length==18:error='Invalid native eight-point graph '+f'{query[0]}/{query[1]}/{query[2]}'
                    add(op,fixture(data),tag='curve-layout',expected_error=error)
                # Curve access ignores reflection type and decodes raw payload.
                # Text fields preserve malformed hex and Unicode whitespace.
                for payload in ('0'*128,'0'*160,'G'*160,'0'*159,'\u00a0'+'0'*160+'\u3000','\u2007'+'0'*160+'\n'):
                    data=copy.deepcopy(minimal);mutate(data,query,dict(type='EA::Reflection::Text',data=payload));add(op,fixture(data),tag='curve-text')
        data=copy.deepcopy(minimal);category,key,_,_=queries[0];data['collections']=[r for r in data['collections'] if not (converter.name_id(r['class'])==converter.name_id(category) and converter.name_id(r['key'])==converter.name_id(key))];add(op,fixture(data),tag='missing-collection',expected_error='Missing stock collection '+f'{category}/{key}')
    # Numeric identities in class, key, parent and field names resolve exactly;
    # readable direct field names keep priority over a colliding numeric alias.
    data=copy.deepcopy(minimal)
    for r in data['collections']:
        r['class']=f'Hash_{converter.name_id(r["class"]):016X}';r['key']=f'Hash_{converter.name_id(r["key"]):016X}'
        if r['parent']:r['parent']=f'Hash_{converter.name_id(r["parent"]):016X}'
        r['fields']={f'Hash_{converter.name_id(name):016X}':value for name,value in r['fields'].items()}
    numeric=fixture(data)
    for op in range(6):add(op,numeric,tag='numeric-alias')
    data=copy.deepcopy(minimal);target=record(data,'physics_manual','default');query=fields(0)[1];chain,name=resolve(data,query);value=copy.deepcopy(chain[-1]['fields'][name]);target['fields'][f'Hash_{converter.name_id(query[2]):016X}']=dict(type='EA::Reflection::Float',data='3E123456');target['fields'][query[2]]=value;add(0,fixture(data),tag='direct-name-priority')
    data=copy.deepcopy(minimal);parent=record(data,'physics_mode','normal');child=copy.deepcopy(parent);child.update(key='inherited',parent=parent['key'],fields={});data['collections'].append(child)
    inherited=fixture(data)
    for op in (1,2,4):add(op,inherited,mode='inherited',tag='inherited-mode')
    data=copy.deepcopy(minimal);r=record(data,'physics_manual','default');chain,name=resolve(data,fields(0)[0]);del chain[-1]['fields'][name];r['parent']='cycle';child=copy.deepcopy(r);child.update(key='cycle',parent=r['key'],fields={});data['collections'].append(child);add(0,fixture(data),tag='inheritance-cycle',expected_error='Cyclic stock collection inheritance physics_manual/default')
    for op in (1,2,4):add(op,1,mode='missing-mode',tag='missing-mode',expected_error='Missing stock collection physics_mode/missing-mode')
    add(4,1,surface='missing-surface',tag='missing-surface',expected_error='Missing stock collection physics_surfaces/missing-surface')
    for value in (0,1,2,3,4,5,6,0xffffffff):add(6,1,surface_id=value,tag='surface-map',expected_error=f'Processed surface mode {value} was not normalized by SurfacePhysics' if value not in range(1,6) else None)
    return fixtures,rows


def encode(rows):
    out=Stream();out.word(len(rows))
    for row in rows:out.word(row['op']);out.word(row['fixture']);out.string(row['mode']);out.string(row['surface']);out.word(row['surface_id'])
    return bytes(out.data)


def prepare_fixtures(output,fixtures,source):
    root=output/'fixtures'
    if root.exists():shutil.rmtree(root)
    root.mkdir();records={}
    for index,data in enumerate(fixtures):
        path=root/str(index)/'private/stock/skater-collections.json';path.parent.mkdir(parents=True);path.write_text(json.dumps(data,separators=(',',':'))+'\n');simulation=path.parents[2]/'settings.simulation';simulation.write_bytes(converter.encode_settings(path));records[index]=dict(collections_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),simulation_sha256=hashlib.sha256(simulation.read_bytes()).hexdigest(),collections=len(data['collections']))
    (output/'fixture-provenance.json').write_text(json.dumps(dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),fixtures=records),indent=2)+'\n');return root


def extract_literal(source,marker):
    assert source.count(marker)==1,marker;start=source.index(marker);start+=marker.index(': ')+2;brace=source.index('{',start);depth=1;at=brace+1;quoted=False;line_comment=False
    while depth:
        char=source[at]
        if line_comment:
            if char=='\n':line_comment=False
        elif quoted:
            if char=='\\':at+=1
            elif char=='"':quoted=False
        elif source[at:at+2]=='//':line_comment=True;at+=1
        elif char=='"':quoted=True
        elif char=='{':depth+=1
        elif char=='}':depth-=1
        at+=1
    text=source[start:at];assert source[at:at+2]==',\n'
    return text,dict(marker=marker,begin=len(source[:start].encode()),end=len(source[:at].encode()),sha256=hashlib.sha256(text.encode()).hexdigest())


def prepare_source(output):
    source=trees.source_at_reference('crates/skate-host/src/physics/ground_runtime/settings.rs');runtime=trees.source_at_reference('crates/skate-host/src/physics/ground_runtime/mod.rs');surface=trees.source_at_reference('crates/skate-host/src/physics/ground_runtime/surface.rs');records=[]
    decoder,record=trees.extract_block(source,'pub(super) fn curve8(');records.append(record);manual,record=trees.extract_block(source,'fn manual_settings(');records.append(record)
    appended='\nmod stock {\nuse super::*;\n'+decoder+'\n'+manual+'\npub fn manual(data:&Collections)->Result<ManualSettings,String> {manual_settings(data)}\n'
    for field,typename,function in (('manual_mode','ManualMode','manual_mode'),('propulsion','GroundPropulsionSettings','propulsion'),('drag','LinearDragSettings','drag'),('speed','SpeedModelSettings','speed')):
        literal,record=extract_literal(source,f'            {field}: {typename} {{');records.append(record)
        appended+=f'pub fn {function}(data:&Collections'+(',mode:&str' if function in ('manual_mode','propulsion','speed') else '')+(',surface:&str' if function=='speed' else '')+f')->Result<{typename},String> {{\n'
        if function!='manual_mode':appended+='let f=|class,field|data.float(class,"default",field);\n'
        if function in ('manual_mode','propulsion','speed'):appended+='let m=|field|data.float("physics_mode",mode,field);\n'
        if function=='speed':
            threshold=next(line.strip() for line in source.splitlines() if line.strip().startswith('let threshold = [f32::from_bits('));records.append(dict(verbatim_threshold=threshold,sha256=hashlib.sha256(threshold.encode()).hexdigest()));appended+='let s=|field|data.float("physics_surfaces",surface,field);\nlet c8=|class,field|curve8(data,class,"default",field);\n'+threshold+'\n'
        appended+='Ok('+literal+')\n}\n'
    appended+='}\nmod stock_wall {\nuse super::*;\n';wall_decoder,record=trees.extract_block(runtime,'fn curve(');records.append(record);literal,record=extract_literal(runtime,'            wall_ride: WallRideSettings {');records.append(record)
    appended+=wall_decoder+'\npub fn wallride(data:&Collections)->Result<WallRideSettings,String> {\nlet feet=|field|data.float("physics_feet","default",field);\nOk('+literal+')\n}\n}\nmod stock_surface {\n';key,record=trees.extract_block(surface,'pub(crate) fn surface_key(');records.append(record);appended+=key+'\n}\n'
    probe=output/'ground-control-settings-oracle.rs';probe.write_text((PLUGIN/'Tests/Reference/ground_control_settings_probe.rs').read_text()+appended)
    (output/'extraction-provenance.json').write_text(json.dumps(dict(settings_source_sha256=hashlib.sha256(source.encode()).hexdigest(),runtime_source_sha256=hashlib.sha256(runtime.encode()).hexdigest(),surface_source_sha256=hashlib.sha256(surface.encode()).hexdigest(),verbatim_extractions=records,probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(),boundary='Declaration-only wrappers around unchanged original manual_settings, curve helpers, leaf struct initializers, threshold constant and surface selector. All lookups/errors are original Collections methods; no original source file is edited.'),indent=2)+'\n');return probe


def build_simulation(output):
    live=PLUGIN/'Source/AtelierSkate/Private/Simulation';code=output/'simulation-source'
    if code.exists():shutil.rmtree(code)
    code.mkdir();files=('NameId','Settings','GroundControlSettings')
    for p in list(live.glob('*.h'))+[live/(name+'.cpp') for name in files]:shutil.copyfile(p,code/p.name)
    probe=code/'ground_control_settings_probe.cpp';shutil.copyfile(PLUGIN/'Tests/Simulation/ground_control_settings_probe.cpp',probe);(output/'simulation-source-provenance.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(code.iterdir())},indent=2)+'\n')
    simulation=output/'ground-control-settings-cpp';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(code),*[str(code/(name+'.cpp')) for name in files],str(probe),'-o',str(simulation)],check=True);return simulation


def decode(data,rows):
    at=0;frames=[]
    def word():
        nonlocal at
        value=struct.unpack_from('<I',data,at)[0];at+=4;return value
    def string():
        nonlocal at
        n=word();value=data[at:at+n].decode();at+=n;return value
    for index,row in enumerate(rows):
        assert word()==index;op=word();assert op==row['op'];ok=word();frame=dict(ok=ok)
        if not ok:frame['error']=string()
        elif op==6:frame['key']=string()
        else:frame['words']=[word() for _ in range((32,2,6,4,68,23)[op])]
        frames.append(frame)
    assert at==len(data),(at,len(data));return frames


def coverage(frames,rows):
    statuses=Counter();errors=Counter();tags=Counter();stock={};read_order=Counter()
    for frame,row in zip(frames,rows):
        statuses[(row['op'],frame['ok'])]+=1;tags[row['tag']]+=1
        if row['expected_error'] is not None:assert not frame['ok'] and frame['error']==row['expected_error'],(row,frame)
        if frame['ok']:
            if row['tag']=='stock-mode-surface':stock[(row['op'],row['mode'],row['surface'])]=frame['words']
            if row['op']==4:assert frame['words'][-8:]==[0x358637bd]*4+[0]*4
            if row['op']==6:assert frame['key']==SURFACES[row['surface_id']-1]
        else:
            errors[frame['error'].split(' physics_',1)[0].split(' at physics_',1)[0]]+=1
            if row['tag'].startswith('read-order-'):read_order[row['op']]+=1
    assert len(stock)==150 and all(statuses[(op,0)] and statuses[(op,1)] for op in range(7)),statuses
    assert all(read_order[op]==len(fields(op)) for op in range(6)),read_order
    assert len({tuple(stock[(4,'normal',surface)]) for surface in SURFACES})>=4
    assert len({tuple(stock[(2,mode,'smooth')]) for mode in MODES})>=3
    by_tag={}
    for frame,row in zip(frames,rows):by_tag.setdefault(row['tag'],[]).append((frame,row))
    for frame,row in by_tag['numeric-alias']:assert frame['words']==stock[(row['op'],'normal','smooth')]
    for frame,row in by_tag['inherited-mode']:assert frame['words']==stock[(row['op'],'normal','smooth')]
    assert by_tag['direct-name-priority'][0][0]['words']==stock[(0,'normal','smooth')]
    assert any(frame['ok'] for frame,_ in by_tag['curve-text']) and any(not frame['ok'] for frame,_ in by_tag['curve-text'])
    assert any(frame['ok'] for frame,_ in by_tag['boolean-first-byte']) and any(not frame['ok'] for frame,_ in by_tag['boolean-first-byte'])
    return dict(load_status_by_operation={f'{op}:{ok}':n for (op,ok),n in sorted(statuses.items())},tags=dict(tags),first_failed_field_by_operation=dict(read_order),error_classes=dict(errors),stock_combinations=25,stock_leaf_loads=150,simulation_threshold='Every successful speed model preserves four 0x358637bd lanes and four zero override-direction lanes',aliases_and_inheritance='Numeric class/key/field, mode inheritance and readable-name priority matched actual stock words')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--target-dir',type=Path,required=True);args=p.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(output/name).unlink(missing_ok=True)
    source=args.assets/'private/stock/skater-collections.json';fixtures,rows=corpus(json.loads(source.read_text()));fixture_root=prepare_fixtures(output,fixtures,source);commands=encode(rows);(output/'input.bin').write_bytes(commands);(output/'cases.json').write_text(json.dumps(rows,indent=2)+'\n')
    reference=build_probe(output,'ground-control-settings-reference',prepare_source(output),args.target_dir);simulation=build_simulation(output)
    def expected(data):return subprocess.check_output([str(reference),str(fixture_root)],input=data)
    def actual(data):return subprocess.check_output([str(simulation),str(fixture_root)],input=data)
    oracle=expected(commands);candidate=actual(commands);(output/'reference.bin').write_bytes(oracle);(output/'simulation.bin').write_bytes(candidate);frames=decode(oracle,rows);(output/'reference-trace.json').write_text(json.dumps(frames,indent=2)+'\n')
    if oracle!=candidate:
        lo=0;hi=len(rows)
        while hi-lo>1:
            mid=(lo+hi)//2;part=encode(rows[lo:mid])
            if expected(part)==actual(part):lo=mid
            else:hi=mid
        (output/'first-divergence-input.bin').write_bytes(encode(rows[lo:hi]));first=next((i for i,(a,b) in enumerate(zip(candidate,oracle)) if a!=b),min(len(candidate),len(oracle)));(output/'first-divergence.json').write_text(json.dumps(dict(case=lo,record=rows[lo],byte=first),indent=2)+'\n');raise AssertionError(f'Ground control settings differ at byte {first}, case {lo}')
    result=dict(passed=True,cases=len(rows),fixtures=len(fixtures),coverage=coverage(frames,rows),output_bytes=len(oracle),output_sha256=hashlib.sha256(oracle).hexdigest(),comparison='All six ground setting leaves, exact constants, 25 stock mode/surface selections, every first failed read, missing/type/nonfinite/size/bool/curve/inheritance errors and exact surface mapping.',limitations='Simulation decoded-data boundary; text fixtures preserve malformed hex/Unicode whitespace. Invalid raw JSON/numeric hex rejected during conversion remains a converter boundary. Full Ground profile order, tuning and gameplay scheduling remain separate owners.',extraction_provenance_sha256=hashlib.sha256((output/'extraction-provenance.json').read_bytes()).hexdigest(),fixture_provenance_sha256=hashlib.sha256((output/'fixture-provenance.json').read_bytes()).hexdigest(),simulation_source_provenance_sha256=hashlib.sha256((output/'simulation-source-provenance.json').read_bytes()).hexdigest())
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
