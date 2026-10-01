#!/usr/bin/env python3
"""Whole original Boneless over actual plant, pose, IK, board and trajectory owners.

Only root builds or executes under the shared render guard. --preflight audits
source/corpus staging without compiling or invoking either probe.
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
import check_air_phase_runtime_parity as air
import check_ground_control_settings_parity as stock
from session_parity import digest, REFERENCE_REVISION
from check_graph_parity import element, original_graph
PLUGIN=air.PLUGIN;CODE=air.CODE
UNITS=tuple(dict.fromkeys((*air.UNITS,'BonelessRuntime')))
FIELDS=('Hash_6D781EFAF01E707D','Hash_C9112CCD0BCB1850','Hash_88D0CDEFA38A36D6','Hash_9228B7F18C223F9C')

def prepare(output):
    original,observed,snapshot,report=air.prepare(output)
    crate=observed/'atelier-host'
    native=(snapshot/'air_phase_runtime_probe.cpp').read_text()
    prefix=native[:native.index('int main(')]
    construction=native[native.index('    const auto* definition='):native.index('        const auto snapshot=')]
    first=native[native.index('            case 0:'):native.index('            case 3:')]
    rest=native[native.index('            case 13:'):native.index('            case 20:')]
    source=(PLUGIN/'Tests/Native/boneless_runtime_probe.cpp').read_text().replace('// GENERATED_COMPLETE_OWNER_HELPERS',prefix).replace('// GENERATED_COMPLETE_OWNER_CONSTRUCTION',construction).replace('// GENERATED_ORIGINAL_CALLER_CASES',first+rest)
    shutil.copy2(CODE/'BonelessRuntime.cpp',snapshot/'BonelessRuntime.cpp')
    probe=snapshot/'boneless_runtime_probe.cpp';probe.write_text(source)
    observer=(PLUGIN/'Tests/Reference/air_phase_runtime_observer.rs').read_text()
    prefix=observer[:observer.index('pub(super)fn load(')].replace('mod migration_air {','mod migration_boneless {')
    construction=observer[observer.index(' let graphs='):observer.index('snapshot(o,&p,&s,&last);')]
    first=observer[observer.index(' 0=>'):observer.index(' 3=>')]
    rest=observer[observer.index(' 13=>'):observer.index('20=>')]
    run=(PLUGIN/'Tests/Reference/boneless_runtime_probe.rs').read_text().replace('// GENERATED_COMPLETE_OWNER_OBSERVATIONS',prefix).replace('// GENERATED_COMPLETE_OWNER_CONSTRUCTION',construction).replace('// GENERATED_ORIGINAL_CALLER_CASES',first+rest)
    private=(PLUGIN/'Tests/Reference/boneless_runtime_observer.rs').read_bytes()
    for rel,extra in [('physics.rs',run.encode()),('physics/boneless.rs',private)]:
        path=crate/'src'/rel;path.write_bytes(path.read_bytes()+b'\n'+extra)
        row=report['staged_host_original_prefixes'][rel]
        raw=(original/'crates/skate-host/src'/rel).read_bytes();assert path.read_bytes()[:len(raw)]==raw
        row['generated_sha256']=digest(path)
        row['boneless_append_sha256']=hashlib.sha256(extra).hexdigest()
    path=crate/'src/migration_probe.rs'
    path.write_text(path.read_text().replace('physics::migration_air_load','physics::migration_boneless_load').replace('physics::migration_air_run','physics::migration_boneless_run'))
    cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text().replace('name="air-phase-runtime-reference"','name="boneless-runtime-reference"'))
    report.update(units=UNITS,derived_original_observer_prefix_sha256=hashlib.sha256(prefix.encode()).hexdigest(),owner_observer_derivation=dict(native_source=digest(PLUGIN/'Tests/Native/air_phase_runtime_probe.cpp'),original_source=digest(PLUGIN/'Tests/Reference/air_phase_runtime_observer.rs')),immutable_native_sources={p.name:digest(p)for p in sorted(snapshot.glob('*.h'))+sorted(snapshot.glob('*.cpp'))},generated_native_probe_sha256=digest(probe),generated_reference_probe_sha256=digest(path),boneless_original_sha256=digest(original/'crates/skate-host/src/physics/boneless.rs'),proof_files={p.name:digest(p)for p in [Path(__file__),PLUGIN/'Tests/Native/boneless_runtime_probe.cpp',PLUGIN/'Tests/Reference/boneless_runtime_probe.rs',PLUGIN/'Tests/Reference/boneless_runtime_observer.rs']},scope='Complete unchanged Boneless and host/core producers. Actual stock constructors, plant roots/general update/hold IK, shared solve, real world/provider queries and trajectory Launch/Update execute unchanged. Only explicit canonical upstream packet/pose selection and read-only/accessibility observers are authored.')
    (output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n')
    return original,observed,snapshot,report

def packet(n,mode=1):
    defs,_=air.packet.declarations();p=air.zero('ProcessedPhysicsInput',defs)
    p.update(flags_2468=0x2000|((n%2)<<26),flags_2472=0,flags_2476=0,flags_2480=0,state_2508=602,category_2512=600,state_2504=100,category_2516=100,state_variant_index_2528=mode,timestep_2604=1/60,gravity_2648=9.81,state_timer_2664=.137,transition_2636=.317,scalar_2612=3.137,actor_query_2948=17,actor_query_2952=0xffffffff)
    p['vectors_464_480_496_512_528']=[air.foot.fs([0,1,0,0]),air.foot.fs([0,-.03,0,0]),air.foot.fs([0,-.03,0,0]),air.foot.fs([0,0,1,0]),air.foot.fs([0,1,0,0])]
    p['vectors_544_560_592_608'][0]=air.foot.fs([0,1,0,0]);p['prepared_jump_704']=air.foot.fs([.137,4.137,3.137,0])
    s=air.Stream();s.word(0);air.packet.encode(s,'ProcessedPhysicsInput',p,defs)
    for w in air.foot.fs([.137,4.137,3.137,0]):s.word(w)
    s.word(100);s.float(.137);s.float(.317);s.float(.731)
    return list(struct.unpack('<'+'I'*(len(s.data)//4),s.data))

def arithmetic(n):
    up=[(.137,0,-.317)[n%3],(0,.137,.731,1,1.137)[n%5],(.317,0,-.137)[n%3],0]
    current=[(.137,0,-.317)[n%3],(-2,0,1.137)[n%3],(0,.317,1.9199999,1.92,1.9200001,3.137,9.999999,10,10.000001,15)[n%10],0]
    prepared=[(.731,0,-.731)[n%3],(0,1.137,4.731)[n%3],(0,.137,2.137,4.731,12.137)[n%5],0]
    return [33]+air.foot.fs(up+current+prepared+[.137,.731,-.317,0]+[0,0,1,0])

def corpus():
    cases=[];records=[]
    empty=dict(rails=[],segments=[],guids=[],assets=[],manifest={})
    providers=(empty,air.provider.authored_provider([[0,-.03,-3],[0,-.03,3]],name='boneless-rail'),air.provider.stock_provider())
    def add(n,commands,label):
        s=air.provider.Stream();air.provider.encode_provider(s,providers[n%3]);transport=list(struct.unpack('<'+'I'*(len(s.data)//4),s.data))
        record=[(1,2,3)[n%3],*transport,len(commands),*[w for c in commands for w in c]]
        cases.append(dict(index=len(cases),label=label,commands=commands));records.append(record)
    for n in range(12):
        commands=[packet(n),[1,n%4],[2,1],[13],[14],[19],[30]]
        for k in range(24):
            flags=0x2000|((n%2)<<26)
            commands += [arithmetic(n+k),[35,flags,(1<<13)if k%3 else 0],[31]]
            if k%4==0:commands += [[13],[14],[19],[30]]
            if k%6==0:commands += [[16],[32]]
        commands += [[35,0x2000|(((n+1)%2)<<26),0],[30],[31]]
        add(n,commands,'real physical toe anchor, repeated authored FootJump and actual plant/IK/trajectory histories')
    for n in range(4):
        commands=[packet(n),[1,n],[2,1],[13],[14],[19],[30],arithmetic(n),[35,0x2000|((n%2)<<26),1<<13],[31]]
        commands += [[2,0],arithmetic(n+3),[31],[32],[2,1]]
        commands += [packet(n,9),[35,0x2000|((n%2)<<26),1<<13],[31],[32],packet(n)]
        commands += [[1,4],[31],[1,n],[31]]
        # Invalid caller W reaches the actual source trajectory query error;
        # plant and held-foot writes preceding Launch remain observable.
        bad=arithmetic(n);bad[8]=0x7fc00000
        commands += [bad,[31],[32],arithmetic(n),[16],[31]]
        add(n,commands,'source ordered missing-toolkit/mode/hierarchy/query failures and partial writes')
    out=air.Stream();out.word(len(records))
    for record in records:
        for word in record:out.word(word)
    return bytes(out.data),cases

class Reader(air.Reader):
    def snapshot_boneless(self):
        n=self.word();owner=list(self.take(n));assert len(owner)==70
        n=self.word();toes=list(self.take(n));assert len(toes)==8
        phases,spans=self.phases();foot=self.foot();shared=self.snapshot()
        return dict(owner=owner,toes=toes,phase=phases,foot=foot,shared=shared,spans=spans)

def decode(raw,cases):
    r=Reader(raw);assert r.word()==len(cases);frames=[]
    for case in cases:
        case['first_output_word']=r.at;assert r.word()==len(case['commands']);prior=r.snapshot_boneless();rows=[]
        for command in case['commands']:
            at=r.at;assert r.word()==command[0];error=r.status();current=r.snapshot_boneless();rows.append(dict(operation=command[0],error=error,first_word=at,last_word=r.at,**current,prior=prior));prior=current
        case['last_output_word']=r.at;frames.append(rows)
    assert r.at==len(r.words);return frames

def coverage(frames,cases):
    counts=Counter();errors=Counter();sides=set();anchors=set();velocities=set();positions=set();pending=set();roots=set();repeated=0;launches=0;partial=0;held=0
    for rows,case in zip(frames,cases):
        jump=False
        for row,cmd in zip(rows,case['commands']):
            op=cmd[0];counts[op]+=1;b=row['owner'];old=row['prior'];before=old['owner']
            assert b[6:]==before[6:],'runtime must not mutate stock curves'
            if op==35:jump=bool(cmd[2]&(1<<13))
            if op==0:jump=False
            if op==30:
                sides.add(b[5]);anchors.add(tuple(b[1:5]));assert b[0]==(19 if b[5]else 15)
                assert b[1:5]==row['toes'][4*b[5]:4*b[5]+4]
                assert row['phase']['lifecycle'][6]==1
            if op in(31,32):
                assert b==before,'updates retain captured physical toe/anchor/right'
                trace=air.foot.trajectory_observation(row['foot']['trajectory'])
                if trace['launch']:
                    launches+=1;assert trace['launch'][67:69]==[1,1]
                    velocities.add(tuple(trace['launch'][32:36]));positions.add(tuple(trace['launch'][56:64]))
                pending.add(tuple(trace['flags']));roots.add(tuple(row['shared']['roots']))
                if op==31 and not row['error']:held+=1
                if op==31 and jump and not row['error']and trace['launch']:repeated+=1
            if op==31 and not jump and not row['error']:
                assert row['foot']['trajectory']==old['foot']['trajectory'],'no host timer may request an un-authored launch'
            if row['error']:
                errors[row['error']]+=1
                partial+=row['shared']['roots']!=old['shared']['roots']or row['shared']['publication']!=old['shared']['publication']or row['shared']['ik']!=old['shared']['ik']
    assert sides=={0,1}and len(anchors)>8 and held>100 and repeated>100 and launches>100
    assert len(velocities)>20 and len(positions)>8 and len(roots)>20
    assert any('BoardToolkit'in e for e in errors)and any('mode 9'in e for e in errors)and partial>=4
    return dict(operations=dict(counts),errors=dict(errors),toe_sides=sorted(sides),distinct_physical_anchors=len(anchors),successful_held_foot_updates=held,authored_repeated_launch_rows=repeated,launch_rows=launches,distinct_velocities=len(velocities),distinct_positions=len(positions),distinct_roots=len(roots),partial_failures=partial,selector_flags=len(pending))

def loader_fixtures(assets):
    data=json.loads((assets/'private/stock/skater-collections.json').read_text());fixtures=[]
    queries=[('Hash_CCB95A83C78B4FF9','default',name,'words')for name in FIELDS]
    for n,q in enumerate(queries):
        for kind,payload,okay in [('missing',None,False),('width19',{'type':'EA::Reflection::Text','data':'00000000'*19},False),('width21',{'type':'EA::Reflection::UInt32','data':'00000000'*21},False),('hex',{'type':'EA::Reflection::Text','data':'G'*160},False),('typeignored',{'type':'EA::Reflection::Bool','data':'00000000'*20},True),('IEEE',{'type':'EA::Reflection::Int32','data':''.join(f'{w:08x}'for w in [0xdeadbeef]*4+[0,0x80000000,0x7f800000,0xff800000,0x7fc12345,0x7fa12345,0x3f800000,0xbf800000]*2)},True)]:
            d=copy.deepcopy(data)
            if payload is None:
                chain,name=stock.resolve(d,q);del chain[-1]['fields'][name];chain[-1]['parent']=''
            else:stock.mutate(d,q,payload)
            fixtures.append(dict(label=f'{n}-{kind}',data=d,success=okay))
        for later in queries[n+1:]:
            d=copy.deepcopy(data);stock.mutate(d,q,dict(type='EA::Reflection::Text',data='0'*8));stock.mutate(d,later,dict(type='EA::Reflection::Text',data='G'*160));fixtures.append(dict(label=f'ordered-{n}-before-{FIELDS.index(later[2])}',data=d,success=False))
    return fixtures

def build(output,target):
    original,observed,snapshot,report=prepare(output);crate=observed/'atelier-host'
    subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(crate/'Cargo.toml'),'--target-dir',str(target.resolve()),'--bin','boneless-runtime-reference'],check=True)
    reference=output/'boneless-runtime-reference';shutil.copy2(target.resolve()/'release/boneless-runtime-reference',reference);native=output/'boneless-runtime-native'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'boneless_runtime_probe.cpp'),'-o',str(native)],check=True)
    for rel,sha in report['original_source_sha256'].items():
        assert digest(original/rel)==sha;raw=(original/rel).read_bytes();assert(observed/rel).read_bytes()[:len(raw)]==raw
    for rel,row in report['staged_host_original_prefixes'].items():assert digest(crate/'src'/rel)==row['generated_sha256']
    report.update(reference_binary_sha256=digest(reference),native_binary_sha256=digest(native));(output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');return native,reference

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in('assets','samples','output','target-dir'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    for name in('result.json','first-divergence.json'):(out/name).unlink(missing_ok=True)
    raw,cases=corpus();ranges=air.preflight(raw,cases);fixtures=loader_fixtures(a.assets.resolve())
    (out/'input.bin').write_bytes(raw);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    if a.preflight:
        prepare(out);print(json.dumps(dict(histories=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(raw),input_sha256=hashlib.sha256(raw).hexdigest(),loader_fixtures=len(fixtures),units=len(UNITS)),indent=2));return
    bank=out/'fixtures';bank.mkdir(exist_ok=True);path=a.assets.resolve()/'private/stock'
    (bank/'settings.native').write_bytes(air.converter.encode_settings(path/'skater-collections.json'));(bank/'physics.native').write_bytes(air.converter.encode_physics_skeletons(path/'physics-skeletons.json'))
    for kind in('action','motion'):(bank/f'actor.{kind}.reference').write_bytes(original_graph(element('state','idle')))
    identity=json.loads((path/'physics-skeletons.json').read_text())['source_sha256'];native,reference=build(out,a.target_dir)
    args=[str(bank/'settings.native'),str(bank/'physics.native'),str(a.samples.resolve()/'native/rig.skate'),identity,str(a.assets.resolve())]
    expected=subprocess.check_output([str(reference),str(a.assets.resolve()),str(bank)],input=raw);actual=subprocess.check_output([str(native),*args],input=raw)
    (out/'reference.bin').write_bytes(expected);(out/'native.bin').write_bytes(actual);frames=decode(expected,cases)
    if expected!=actual:
        at=next((k for k,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));word=at//4;case=next((c for c in cases if c['first_output_word']<=word<c['last_output_word']),None);row=next((r for rows in frames for r in rows if r['first_word']<=word<r['last_word']),None)
        failure=dict(byte=at,word=word,reference_bytes=len(expected),native_bytes=len(actual),case=case['index']if case else None,operation=row['operation']if row else'initial',reference_hex=expected[max(0,at-16):at+32].hex(),native_hex=actual[max(0,at-16):at+32].hex());(out/'first-divergence.json').write_text(json.dumps(failure,indent=2)+'\n');raise AssertionError(failure)
    covered=coverage(frames,cases);old=None;loaders=[];total=len(expected)
    for n,f in enumerate(fixtures):
        folder=out/'loader-fixtures'/f'{n:03d}-{f["label"]}';j=folder/'private/stock/skater-collections.json';j.parent.mkdir(parents=True,exist_ok=True);j.write_text(json.dumps(f['data'])+'\n');transport=folder/'settings.native';transport.write_bytes(air.converter.encode_settings(j))
        ref=subprocess.check_output([str(reference),str(a.assets.resolve()),str(bank),str(folder)],input=b'');cpp=subprocess.check_output([str(native),*args,str(transport)],input=b'');(folder/'reference.bin').write_bytes(ref);(folder/'native.bin').write_bytes(cpp);assert ref==cpp,f['label'];total+=len(ref)
        r=Reader(ref);error=r.status();owner=list(r.take(70));assert r.at==len(r.words)and(error is None)==f['success'];assert owner[:6]==[15,0,0,0,0,0]
        if error:
            if old is None:old=owner
            assert owner==old,'failed load must preserve every previously loaded owner/curve field'
        loaders.append(dict(label=f['label'],error=error,bytes=len(ref),sha256=hashlib.sha256(ref).hexdigest()))
    result=dict(passed=True,reference_revision=REFERENCE_REVISION,histories=len(cases),commands=sum(len(c['commands'])for c in cases),exact_output_bytes=total,sha256=hashlib.sha256(expected).hexdigest(),coverage=covered,loader_fixtures=loaders,input_sha256=hashlib.sha256(raw).hexdigest(),scope='Complete original Boneless load/enter/update/private launch and actual canonical plant/pose/IK/board/trajectory/query producers, complete retained observations and ordered loader failures.',boundaries='Explicit source upstream Processed/post packets, authored pose selection and raw world/provider transport. Direct private Launch wrapper additionally explores arithmetic/control boundaries; successful Update always executes actual PlantSkeleton/HoldFoot/Launch order. No complete global frame, retail-behavior invention or seeded accepted trajectory is claimed.')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='loader_fixtures'},indent=2))
if __name__=='__main__':main()
