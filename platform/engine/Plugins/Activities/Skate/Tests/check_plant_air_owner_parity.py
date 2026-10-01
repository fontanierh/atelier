#!/usr/bin/env python3
"""Complete original PlantSkeleton and SkeletonAir owners, direct and composed.

Only root compiles/executes under its render guard. Explicit source caller
inputs and private read-only observations append after immutable originals.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import check_handplant_lifecycle_parity as lifecycle
import check_handplant_parity as numeric
from camera_reference_build import frozen_sources
from check_gesture_parity import PLUGIN,converter
from check_graph_parity import element,original_graph
from session_parity import REFERENCE_REVISION,digest
CODE=numeric.CODE
UNITS=numeric.UNITS
extraction=lifecycle.extraction
air=lifecycle.air
OPS=(*lifecycle.OPS,'load_air','apply_board','capture_caller_target','reckoning_frame')
fs,bits=numeric.fs,numeric.bits

def matrix(n):
    angle=n*.137;c,s=math.cos(angle),math.sin(angle)
    return [[c,.0,-s,.0317],[.0,1.,.0,-.071],[s,.0,c,.137],[.137+n*.00317,.731,-.317,.1731]]

def publication(n):
    raw=lifecycle.publish(n)
    for at,value in ((13,.137),(17,-.1731),(21,.317),(25,-.137),(29,.731),(33,.0317)):raw[at]=bits(value)
    return raw

def loader_fixtures():
    return ('stock','missing_slow','missing_fast','short_slow','short_fast','type_ignored','header_ignored','inherited','missing_both','custom_curves','stock_again')

def corpus():
    records=[];cases=[]
    for n in range(6):
        commands=[]
        for k in range(72):
            j=n*72+k
            commands += [publication(j),[1,j%4],[2],[3],[7,j%2]+fs([.517+j*.00173,.731,-.317,.137])+[(0,1,2,31,0xffffffff)[j%5]],
                [18]+fs(numeric.flatten(matrix(j))),[17]+fs(numeric.flatten(matrix(j+1)))+[j%2],
                [6]+fs([.317+j*.00173,.731,-.137,.137])+[j%24 if j%3 else 0xffffffff],
                lifecycle.pending(j),[10,j%2],lifecycle.pending(j+1),
                [11]+fs([.137+j*.00173,.731,-.317,-.137])+[(1<<28)if j%3 else 0,(1,7,31,360,0x80000000,0xffffffff)[j%6]]]
            if j%7==0:commands += [[8],[9]]
        for bone in range(24):commands += [publication(n+bone),[1,bone%4],[6]+fs([.137+bone*.0173,.731,-.317,.1731])+[bone]]
        for kind in(4,5):
            commands += [publication(n),[1,kind],[6]+fs([.517,.731,-.317,.137])+[0xffffffff],[10,n%2],[11]+fs([.317,.731,-.137,.137])+[1<<28,7],[1,n%4]]
        for index in range(len(loader_fixtures())):commands += [[18]+fs(numeric.flatten(matrix(index))),[16,index],[17]+fs(numeric.flatten(matrix(index+1)))+[index%2]]
        world=numeric.authored_query_world(n%3,pool=n%3)[1:];edges=numeric.edges(n)
        raw=world+edges+[len(commands)]+numeric.flatten(commands)
        records.append(struct.pack('<'+'I'*len(raw),*raw));cases.append(dict(index=n,label='complete owners and settings',commands=commands,operations=[c[0]for c in commands]))
    # Retain the exact source-valid caller prefix that exposed the root's
    # fused negative-parent operand order. KnownAir itself produces the NaNs;
    # no completed exceptional root/frame is supplied to either owner.
    _,old_cases=lifecycle.corpus()
    commands=copy.deepcopy(old_cases[12]['commands'][:71])
    assert commands[-1]==[10,0] and commands[63][-2:]==[1<<28,0]
    raw=numeric.authored_query_world(0)[1:]+numeric.edges(0)+[len(commands)]+numeric.flatten(commands)
    records.append(struct.pack('<'+'I'*len(raw),*raw))
    cases.append(dict(index=len(cases),label='source-produced degenerate KnownAir retained through AnimatedAir',commands=commands,operations=[c[0]for c in commands]))
    return struct.pack('<I',len(records))+b''.join(records),cases

def build_reference(output, target, *, compile=True):
    source, report = frozen_sources(output); observed = output / 'observed-source'
    if observed.exists(): shutil.rmtree(observed)
    shutil.copytree(source, observed); crate = observed / 'atelier-host'
    host = source / 'crates/skate-host/src'
    helper = PLUGIN / 'Tests/Reference/plant_air_owner_observer.rs'
    lprefix, l_extract = extraction(PLUGIN/'Tests/Reference/handplant_lifecycle_observer.rs','pub(super) fn run(')
    prefix, h_extract = extraction(PLUGIN / 'Tests/Reference/handplant_observer.rs', 'pub(super) fn run(')
    aprefix, a_extract = extraction(PLUGIN / 'Tests/Reference/air_reckoning_observer.rs', 'fn core_input(')
    # Only read-only original-owner observers are reused. Their containing
    # migration module is closed below; no old numeric probe entry executes.
    air_view = b'''\npub(super) fn observe(o:&mut Output,a:&AirReckoning,r:&RidingOutputs){out_state(o,&a.state);for w in *r.body_spin.words(){o.word(w)}for w in r.reckoning.migration_air_reckoning_words(){o.word(w)}out_frames(o,&r.reckoning_frames);}\n}\npub(crate) fn migration_lifecycle_observe(o:&mut crate::Output,a:&AirReckoning,r:&RidingOutputs){migration::observe(o,a,r)}\n'''
    extensions = {'physics/handplant.rs': b'\n' + prefix + lprefix + helper.read_bytes(),
        'physics/air_reckoning.rs': b'\n' + aprefix + air_view,
        'physics/skeleton_air.rs': b'\nimpl SkeletonAir {pub(crate) fn migration_plant_air_settings(&self,o:&mut crate::Output){for g in [self.settings.slow,self.settings.fast]{o.floats(g.x);o.floats(g.y);}}}\n',
        'physics.rs': b'\npub(crate) fn migration_plant_air_owner_run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{handplant::migration_plant_air_owner_run(assets,fixtures,i,o)}\n',
        'grind_world/provider.rs': b'\npub(super) fn migration_handplant_primitives(primitives:Vec<Primitive>)->StaticProvider{let mut value=StaticProvider::new(None).unwrap();value.primitives=primitives;value}\n',
        'grind_world.rs': b'\npub(crate) fn migration_handplant_primitives(primitives:Vec<skate_core::physics::grind_contact::Primitive>)->StaticProvider{provider::migration_handplant_primitives(primitives)}\n'}
    staged = {}
    for original in sorted(host.rglob('*.rs')):
        rel = original.relative_to(host).as_posix()
        if rel in ('lib.rs', 'main.rs'): continue
        raw = original.read_bytes(); extra = extensions.get(rel, b'')
        p = crate / 'src' / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(raw + extra)
        assert p.read_bytes()[:len(raw)] == raw
        staged[rel] = dict(original_prefix_bytes=len(raw), original_prefix_sha256=digest(original),
                          append_sha256=hashlib.sha256(extra).hexdigest(), generated_sha256=digest(p))
    core = {'crates/skate-core/src/riding/ground_orientation.rs': air.CORE_OBSERVER.encode(),
            'crates/skate-core/src/physics/skeleton_motion.rs': b'\nimpl SkeletonMotion {pub fn migration_lifecycle_previous(&self)->f32{self.previous_board_at_y}}\n'}
    for rel, extra in core.items():
        original = source / rel; p = observed / rel; p.write_bytes(original.read_bytes() + extra)
        assert p.read_bytes()[:original.stat().st_size] == original.read_bytes()
    template = PLUGIN / 'Tests/Reference/plant_air_owner_probe.rs'
    shutil.copy2(template, crate / 'src/migration_probe.rs')
    cargo = crate / 'Cargo.toml'; cargo.write_text(cargo.read_text() + '''
skate-core={path="../crates/skate-core"}
skate-data={path="../crates/skate-data"}
skate-net={path="../crates/skate-net"}
half="2.7.1"
bevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}
[[bin]]
name="plant-air-owner-reference"
path="src/migration_probe.rs"
''')
    if compile:
        subprocess.run(['cargo', '+1.97.1', 'build', '--release', '--offline', '--jobs', '2',
            '--manifest-path', str(cargo), '--target-dir', str(target.resolve()), '--bin', 'plant-air-owner-reference'], check=True)
    for rel, sha in report['original_source_sha256'].items():
        assert digest(source / rel) == sha
        assert (observed / rel).read_bytes()[:len((source / rel).read_bytes())] == (source / rel).read_bytes(), rel
    for rel, row in staged.items(): assert digest(crate / 'src' / rel) == row['generated_sha256'], rel
    binary = output / 'plant-air-owner-reference'
    if compile: shutil.copy2(target.resolve() / 'release/plant-air-owner-reference', binary)
    report.update(staged_host_original_prefixes=staged,
        extracted_observer_prefixes=[h_extract, l_extract, a_extract],
        appended_core_observers={rel: dict(original_prefix_sha256=digest(source / rel),
            generated_sha256=digest(observed / rel), observer_sha256=hashlib.sha256(extra).hexdigest()) for rel, extra in core.items()},
        probe_sha256=digest(template), helper_sha256=digest(helper), binary_sha256=digest(binary)if compile else None,
        scope='Every production host/core body remains byte-for-byte original. Only explicit caller input setters, authored primitive transport and read-only owner observers append. No geometry/hit/pose/IK/callback substitute is present.')
    (output / 'reference-provenance.json').write_text(json.dumps(report, indent=2) + '\n')
    return binary

def build_native(output,*,compile=True):
    snapshot=output/'native-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();hashes={}
    for p in [*sorted(CODE.glob('*.h')),*[CODE/(unit+'.cpp')for unit in UNITS]]:
        shutil.copy2(p,snapshot/p.name);hashes[p.name]=digest(snapshot/p.name)
    for name in('handplant_probe.cpp','plant_air_owner_probe.cpp'):
        p=PLUGIN/'Tests/Native'/name;shutil.copy2(p,snapshot/name);hashes[name]=digest(snapshot/name)
    prefix,proof=extraction(PLUGIN/'Tests/Native/handplant_lifecycle_probe.cpp','int main(')
    (snapshot/'plant_air_owner_helpers.inc').write_bytes(prefix)
    binary=output/'plant-air-owner-native'
    if compile:subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(unit+'.cpp'))for unit in UNITS],str(snapshot/'plant_air_owner_probe.cpp'),'-o',str(binary)],check=True)
    for name,sha in hashes.items():assert digest(snapshot/name)==sha
    (output/'native-provenance.json').write_text(json.dumps(dict(immutable_native_sources=hashes,reused_helper_prefix=proof,units=UNITS),indent=2)+'\n');return binary

class Reader(lifecycle.Reader):pass

def decode(raw,cases):
    r=Reader(raw);assert r.word()==len(cases);result=[]
    for case in cases:
        assert r.word()==len(case['commands']);settings=r.take(32);prior=r.snapshot();rows=[]
        for command in case['commands']:
            first=r.at;assert r.word()==command[0];error=r.status();target=r.take(16)if r.word()else None
            current_settings=r.take(32);state=r.snapshot()
            rows.append(dict(operation=command[0],error=error,target=target,settings=current_settings,prior_settings=settings,state=state,prior=prior,first_word=first,last_word=r.at,spans=r.spans.copy()))
            prior,settings=state,current_settings
        result.append(rows)
    assert r.at==len(r.words);return result

def coverage(frames,cases):
    counts=Counter();paths=Counter();anchors=set();targets=set();hook_frames=set();blends=set();settings=set();captured=set();loaders={};roots=set()
    board_start=5+16+8+40;identity=fs([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,0])
    for rows,case in zip(frames,cases):
        pose_kind=None
        for row,command in zip(rows,case['commands']):
            op=command[0];counts[OPS[op]]+=1;s=row['state'];old=row['prior'];roots.add(tuple(s['roots']));blends.add(tuple(s['bodies_blend'][:5]));hook_frames.add(tuple(s['bodies_blend'][5:69]));settings.add(tuple(row['settings']))
            h=lifecycle.handplant(s['handplant']);prior=lifecycle.handplant(old['handplant'])
            if op==1:
                pose_kind=command[1]
                if row['error']:
                    assert pose_kind in(4,5)
                    expected='Animation has no trajectory bone'if pose_kind==4 else'physics skeleton bone index is outside the animation hierarchy'
                    assert row['error']==expected
                    paths['short_pose_setup_'+str(pose_kind)]+=1
            if op==3 and prior['pending']:
                assert row['error']is None and h['pending']is None
                if h['flags']&0x80000000:paths['genuine_ground_admission']+=1
            if op==6:
                anchors.add(command[-1])
                if command[-1]!=0xffffffff:assert s['bodies_blend'][board_start:board_start+7*40]==old['bodies_blend'][board_start:board_start+7*40]
                if row['error']is None:
                    assert s['pose_drives'][513:545]==identity+identity and s['pose_drives'][545:561]==identity
                    assert s['publication'][0]&(1<<19)and s['publication'][7]==s['publication'][0]
                    paths['successful_plant']+=1
            if op in(10,11,6)and row['error']:
                # GeneralUpdate mutates roots/targets before FootIK captures
                # originals. Both explicit short hierarchies stop at that
                # first source get(), rather than at a later hierarchy check.
                assert pose_kind in(4,5) and row['error']=='IK original joint is absent from the current pose'
                for section in('roots','bodies_blend','publication'):assert s[section]!=old[section]
                for section in('ik','physical_record','drive_owner','adjustment'):assert s[section]==old[section]
                assert s['pose_drives'][545:561]==old['pose_drives'][545:561]
                if op in(10,11):assert s['pose_drives']==old['pose_drives']
                paths['general_update_partial_failure']+=1
                paths['ik_original_joint_failure_'+str(op)]+=1
            if op==10:
                if row['error']is None:assert s['pose_drives'][545:561]==identity
                else:assert s['pose_drives'][545:561]==old['pose_drives'][545:561]
                paths['animated_fast'if command[1]else'animated_slow']+=1
            if op==11:
                assert s['pose_drives'][545:561]==old['pose_drives'][545:561]
                if s['pose_drives'][545:561]!=identity:paths['known_retains_next_trajectory']+=1
            if op==7:
                side=command[1];start=25
                for part in((19,20,21)if side else(15,16,17)):
                    if command[-1]:assert h['effects'][start+part]==command[-1]and h['effects'][49+part]==0
                    else:assert h['effects'][start+part]==prior['effects'][start+part]
                paths['hold_right'if side else'hold_left']+=1
            if op in(8,18):captured.add(tuple(s['bodies_blend'][:4]));assert s['bodies_blend'][5:]==old['bodies_blend'][5:]
            if op==9:
                assert s['bodies_blend'][:4]==fs([0,0,0,1])and s['bodies_blend'][4:]==old['bodies_blend'][4:]
            if op==17:
                assert row['target']is not None and row['error']is None;targets.add(tuple(row['target']))
                assert s['bodies_blend'][board_start:]==old['bodies_blend'][board_start:]
                assert s['bodies_blend'][5:29]==old['bodies_blend'][5:29]
                # SetHookTransform/CopyPose writes orientation, basis and
                # position only. Inertia, rates, forces and flags persist.
                hook=s['bodies_blend'][29:69];old_hook=old['bodies_blend'][29:69]
                assert hook[0]==old_hook[0] and hook[14:23]==old_hook[14:23] and hook[26:40]==old_hook[26:40]
                paths['direct_fast'if command[-1]else'direct_slow']+=1
            if op==16:
                index=command[1];loaders[index]=row['error']
                if row['error']:
                    assert s==old and row['settings']==row['prior_settings'];paths['loader_failure_retains_owner']+=1
                else:assert s['bodies_blend'][:5]==fs([0,0,0,1])+[0];paths['loader_success']+=1
    assert anchors==set(range(24))|{0xffffffff}and paths['genuine_ground_admission']>64
    assert paths['successful_plant']>256 and paths['general_update_partial_failure']==36
    assert all(paths['ik_original_joint_failure_'+str(op)]==12 for op in(6,10,11))
    assert paths['short_pose_setup_4']==6 and paths['short_pose_setup_5']==6
    assert paths['known_retains_next_trajectory']>=432 and paths['animated_fast']>=216 and paths['animated_slow']>=216
    assert paths['direct_fast']>=216 and paths['direct_slow']>=216 and paths['hold_right']>=216 and paths['hold_left']>=216
    assert len(captured)>32 and len(targets)>64 and len(hook_frames)>64 and len(roots)>128 and len(blends)>32 and len(settings)>=2
    expected_failures={1,2,3,4,8}
    assert {index for index,error in loaders.items()if error}==expected_failures
    assert loaders[1]==loaders[8]and 'PhysToAnimSlow'in loaders[1]and'PhysToAnimFast'in loaders[2]
    assert loaders[3]=='Expected 20 big-endian words, found 152 bytes of hex'and loaders[4]=='Expected 20 big-endian words, found 168 bytes of hex'
    exceptional=frames[-1][-1]
    assert cases[-1]['commands'][-1]==[10,0] and exceptional['error']is None
    assert exceptional['state']['roots'][44:48]==[0xffc00000]*4
    assert exceptional['state']['roots'][60:64]==[0xffc00000]*3+[0x7fc00000]
    paths['source_generated_negative_nan_root_translation']=4
    paths['source_generated_world_translation_nan_operand_order']=4
    return dict(operations=dict(counts),paths=dict(paths),valid_anchor_indices=sorted(anchors),distinct_targets=len(targets),distinct_hook_outputs=len(hook_frames),captured_errors=len(captured),blend_states=len(blends),root_states=len(roots),settings_states=len(settings),loader_results=loaders)

def prepare(assets,output):
    fixtures=output/'fixtures';fixtures.mkdir(exist_ok=True);source=assets/'private/stock/skater-collections.json';stock=json.loads(source.read_text())
    (fixtures/'settings.native').write_bytes(converter.encode_settings(source));skeletons=assets/'private/stock/physics-skeletons.json';(fixtures/'physics.native').write_bytes(converter.encode_physics_skeletons(skeletons));records=[]
    for index,label in enumerate(loader_fixtures()):
        data=copy.deepcopy(stock);record=next(r for r in data['collections']if r['class']=='physics_airstates'and r['key']=='default');fields=record['fields']
        if label in('missing_slow','missing_both'):fields.pop('PhysToAnimSlow')
        if label in('missing_fast','missing_both'):fields.pop('PhysToAnimFast')
        if label=='short_slow':fields['PhysToAnimSlow']['data']=fields['PhysToAnimSlow']['data'][:-8]
        if label=='short_fast':fields['PhysToAnimFast']['data']=fields['PhysToAnimFast']['data']+'00000000'
        if label=='type_ignored':fields['PhysToAnimSlow']['type']='EA::Reflection::String'
        if label=='header_ignored':fields['PhysToAnimFast']['data']='7fc012340000000080000000ffffffff'+fields['PhysToAnimFast']['data'][32:]
        if label=='inherited':
            parent=copy.deepcopy(record);parent['key']='plant_air_parent';data['collections'].append(parent);record['parent']=parent['key'];fields.pop('PhysToAnimSlow');fields.pop('PhysToAnimFast')
        if label=='custom_curves':
            for name,scale in(('PhysToAnimSlow',.1731),('PhysToAnimFast',.317)):
                words=[int(fields[name]['data'][k:k+8],16)for k in range(0,160,8)];words[12:20]=[bits(.137+scale*k)for k in range(8)];fields[name]['data']=''.join(f'{v:08X}'for v in words)
        folder=fixtures/f'case-{index}';original=folder/'private/stock/skater-collections.json';original.parent.mkdir(parents=True,exist_ok=True);original.write_text(json.dumps(data));(folder/'settings.native').write_bytes(converter.encode_settings(original));records.append(dict(index=index,label=label,original_sha256=digest(original),native_sha256=digest(folder/'settings.native')))
    for kind in('action','motion'):(fixtures/f'actor.{kind}.reference').write_bytes(original_graph(element('state','idle')))
    (fixtures/'loader-provenance.json').write_text(json.dumps(records,indent=2)+'\n');return fixtures,json.loads(skeletons.read_text())['source_sha256']

def preflight(raw,cases):
    words=struct.unpack('<'+'I'*(len(raw)//4),raw);at=1;ranges=[];lengths=(34,2,1,1,1,1,6,7,1,1,2,7,2,2,36,17,2,18,17,17)
    assert words[0]==len(cases)
    for case in cases:
        start=at*4;triangles=words[at];at+=1+18*triangles;assert words[at]==triangles;at+=1+triangles;meshes=words[at];at+=1+12*meshes;assert words[at]==3;at+=1
        edges=words[at];at+=1+10*edges;assert words[at]==len(case['commands']);at+=1
        for command in case['commands']:assert len(command)==lengths[command[0]],(command[0],len(command));assert list(words[at:at+len(command)])==command;at+=len(command)
        ranges.append((start,at*4))
    assert at==len(words)and b''.join(raw[start:end]for start,end in ranges)==raw[4:]
    for unit in UNITS:assert(CODE/(unit+'.cpp')).is_file(),unit
    return ranges

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for field in('assets','samples','output','target-dir'):p.add_argument('--'+field,type=Path,required=True)
    p.add_argument('--preflight',action='store_true');p.add_argument('--reference-case-runner',action='store_true');p.add_argument('--reference-workers',type=int,choices=(1,2,3,4),default=1);a=p.parse_args()
    if not a.reference_case_runner and a.reference_workers!=1:p.error('--reference-workers requires --reference-case-runner')
    output=a.output.resolve();output.mkdir(parents=True,exist_ok=True);raw,cases=corpus();ranges=preflight(raw,cases);(output/'input.bin').write_bytes(raw);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');fixtures,identity=prepare(a.assets.resolve(),output)
    if a.preflight:build_reference(output/'reference',a.target_dir,compile=False);build_native(output,compile=False);print(json.dumps(dict(cases=len(cases),commands=sum(len(c['commands'])for c in cases),bytes=len(raw),units=len(UNITS),input_sha256=hashlib.sha256(raw).hexdigest()),indent=2));return
    reference=build_reference(output/'reference',a.target_dir);native=build_native(output)
    if a.reference_case_runner:
        from reference_case_runner import run_reference_cases
        expected=run_reference_cases(reference,[a.assets.resolve(),fixtures],raw,ranges,output/'reference-cases',workers=a.reference_workers,validate_output=lambda index,data:decode(data,[cases[index]]))
    else:expected=subprocess.check_output([str(reference),str(a.assets.resolve()),str(fixtures)],input=raw)
    actual=subprocess.check_output([str(native),str(fixtures/'settings.native'),str(fixtures/'physics.native'),str(a.samples.resolve()/'native/rig.skate'),identity,str(a.assets.resolve()),str(fixtures)],input=raw)
    (output/'reference.bin').write_bytes(expected);(output/'native.bin').write_bytes(actual);frames=decode(expected,cases)
    if expected!=actual:
        at=next((k for k,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));row=next((row for rows in frames for row in rows if row['first_word']<=at//4<row['last_word']),None);section=next(((name,at//4-span[0])for name,span in(row['spans'].items()if row else[])if span[0]<=at//4<span[1]),None);failure=dict(byte=at,operation=row['operation']if row else'initial',section=section,reference_bytes=len(expected),native_bytes=len(actual));(output/'first-divergence.json').write_text(json.dumps(failure,indent=2)+'\n');raise AssertionError(failure)
    result=dict(passed=True,reference_revision=REFERENCE_REVISION,cases=len(cases),commands=sum(len(c['commands'])for c in cases),bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),input_sha256=hashlib.sha256(raw).hexdigest(),coverage=coverage(frames,cases),scope='Complete unchanged PlantSkeleton advance/hold_foot and SkeletonAir load/capture/reset/apply/update_animated/update_known_air using real shared physical board/skeleton, AnimatedSkeleton, FootIK and GeneralUpdate owners. Actual authored world metadata and primitive order generate Handplant contacts. Settings failures/read order, every valid anchor index, four lanes, fast/slow history/hook versus dynamic-body writes and partial hierarchy failures observed. No callback or completed numeric result substituted; whole game coordinator remains separate.')
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
