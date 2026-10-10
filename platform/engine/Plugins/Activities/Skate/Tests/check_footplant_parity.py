#!/usr/bin/env python3
"""Whole-original Footplant retained/prediction/ground/IK/plant/launch proof.

Only the parent runs builds and comparisons under the render guard. --preflight
checks transport/declarations without compiling or invoking either executable.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import check_handplant_lifecycle_parity as lifecycle
import check_air_trajectory_runtime_parity as trajectory
from camera_reference_build import frozen_sources
from check_gesture_parity import PLUGIN, converter
from check_graph_parity import element, original_graph
from session_parity import REFERENCE_REVISION, digest
CODE = lifecycle.CODE
UNITS = tuple(dict.fromkeys((*lifecycle.UNITS, *trajectory.UNITS,
    'AirStateSettings', 'FootplantRuntime', 'FootplantSettings', 'FootplantPrediction', 'FootplantGround', 'WipeoutRequests')))
OPS = ('publish', 'authored_pose', 'known_packet', 'candidate', 'launch_prediction',
       'consume_submit', 'ground_enter', 'ground_update', 'postphysics', 'reset',
       'selective_publish', 'start', 'adjust', 'caller_selected_toe', 'filter_edges',
       'pose', 'toolkit', 'air_mode', 'selector_reset')
FOOT = ('owner', 'settings', 'air_output', 'wipeout', 'trajectory', 'collision_groups')
fs, bits = lifecycle.fs, lifecycle.bits

def publication(n):
    c = lifecycle.publish(n)
    c[4] |= 1 << 23
    return c + fs([0,1,0,0])

def packet(n, negative=False):
    speed = (.731, 1.731, 2.137, 3.137, 4.731, 6.137)[n % 6]
    v = [(.137, .731, -.317)[n % 3], -speed, (.317, -.137)[n % 2], 0]
    return [2] + fs([.137, 1.731, -.317, 0, *v, 0, -9.8, 0, 0, -1,
                      (.09,.137,.173,.237,.317)[n % 5], 0, -.25, 0, 0,
                      0, 1, 0, 0]) if not negative else [2] + fs([.137,1.731,-.317,0]) + [0x7fc00000] + fs(v[1:] + [0,-9.8,0,0,-1,.173,0,-.25,0,0,0,1,0,0])

def sentinels(n):
    return [10] + fs([.13+n*.0173,.317,.731]) + [0x12340000+n, 0x71,0x72,0x73,0x74]

def filtered(n):
    edges = []
    for k in range((1,8,48,65)[n % 4]):
        y = -.25 + (k % 5) * .0137
        z = (k % 6) * .0137
        # Opposed parallel/overlap/reference-distance and degenerate domains.
        a, b = [-2,y,z], [2,y,z]
        if k % 9 == 0: a = b.copy()
        if k % 7 == 0: a, b = b, a
        edges += fs(a + b)
    return [14, len(edges)//6] + edges + fs([.137,.731,.317,0])

def corpus():
    cases=[]; records=[]
    def add(n, commands):
        w=lifecycle.numeric.world(0 if n != 3 else 2)
        if n != 3:
            height=(-.75,-.25,.25)[n]
            for k in range(w[0]):
                for v in range(3): w[1+k*18+v*3+1]=bits(height)
        e=lifecycle.numeric.edges(n)
        for k in range(e[0]):
            e[1+k*10+3]=e[1+k*10+7]=0
            e[1+k*10+1]=e[1+k*10+5]=bits((-.75,-.25,.25,-.25)[n])
        raw=w+e+[len(commands)]+[v for c in commands for v in c]
        cases.append(dict(index=n,world=n,commands=commands,label='real triangle query, retained prediction/lock/reset and source ground lifecycle'))
        records.append(struct.pack('<'+'I'*len(raw),*raw))
    for n in range(4):
        commands=[publication(n),[1,n],[16,1],packet(n),[5]]
        for k in range(72):
            commands += [publication(n+k),[1,(n+k//12)%4],[16,1],packet(n+k),[3],[4],[5],[15],sentinels(k)]
            if k%13==0: commands += [[9,k%2]]
            if k%17==0: commands += [[14,0]+fs([0,0,0,0]),filtered(k)]
        # Start is an original caller-domain helper with real retained contact;
        # it constructs every curve/release direction, never a seeded result.
        for k in range(24):
            commands += [[13,1,(15,19)[k%2]], [11]+fs([.137,.731,-.317,0,
                (.731,2.137,4.731)[k%3],(0,.137,1.137)[k%3],.317,0])]
            commands += [[12]+fs([(-.13,.17,.73,1.13)[k%4],.731,-.317])]
        # Independent source-valid caller positions/velocities use the real
        # retained contact from prior world queries. Negative horizontal motion
        # reaches the unclamped interval between stock .08/.25 durations.
        height=(-.75,-.25,.25,-.25)[n]
        for k in range(128):
            x=.317+(k%17)*.0317
            y=height+.517+(k//17)*.02317
            z=-.137+(k%11)*.01731
            speed=2.137+(k%23)*.317
            commands += [[13,1,(15,19)[k%2]], [11]+fs([x,y,z,0,
                -speed,-.137+(k%7)*.0317,.01731*(k%5-2),0])]
        commands += [publication(n),[1,n],[16,1],[17,1,200,0]+fs([.317,.137,4.731,.317,0]),[6]]
        for k in range(32): commands += [[7]+fs([.317*(k%3-1),.137*(k%5-2)])]
        # Actual zero-angular Start returns early after writing only its prefix.
        commands += [[11]+fs([.137,.731,-.317,0,0,0,0,0])]
        post = publication(n); post[26:30] = fs([12,-11,.317,0])
        commands += [post,[8],sentinels(100+n)]
        for missing in (4,5):
            commands += [[1,missing],[7]+fs([.317,-.137]),[1,n]]
        # NaN-X poisons the XYZ segment square, so original query skips its
        # checked world line leaf and completes successfully as a miss.
        commands += [packet(n,True),[4],[5],packet(n),[4],[5]]
        # W is excluded from core segment gates but included in world's
        # finite endpoint validation: this reaches a genuine query failure.
        invalid_w=packet(n);invalid_w[8]=0x7fc00000
        commands += [invalid_w,[4],[5],packet(n),[4],[5]]
        # Launch reads toolkit before mode; separate real failures preserve
        # completed PlantSkeleton mutations on the error path.
        commands += [[11]+fs([.137,.731,-.317,0,2.731,.137,.317,0]),[16,0]]
        commands += [[7]+fs([.317,-.137]) for _ in range(20)]
        commands += [[16,1],[17,9,200,0]+fs([.317,.137,4.731,.317,0])]
        commands += [[7]+fs([-.317,.137]) for _ in range(4)]
        commands += [[17,1,200,0]+fs([.317,.137,4.731,.317,0]),[16,1],[18],
                     [9,0],sentinels(200+n),[9,1],sentinels(300+n)]
        add(n,commands)
    return struct.pack('<I',len(records))+b''.join(records),cases

# Exact extraction boundaries of observation/wire helpers only. Production
# methods always remain complete byte-preserved source prefixes.
def extraction(path,boundary): return lifecycle.extraction(path,boundary)

def build_reference(output,target):
    original,report=frozen_sources(output); observed=output/'observed-source'
    if observed.exists():shutil.rmtree(observed)
    shutil.copytree(original,observed);crate=observed/'atelier-host';host=original/'crates/skate-host/src'
    hprefix,hmeta=extraction(PLUGIN/'Tests/Reference/handplant_observer.rs','pub(super) fn run(')
    lprefix,lmeta=extraction(PLUGIN/'Tests/Reference/handplant_lifecycle_observer.rs','pub(super) fn run(')
    aprefix,ameta=extraction(PLUGIN/'Tests/Reference/air_reckoning_observer.rs','fn core_input(')
    htail=b'\npub(super) fn shared(o:&mut Output,p:&GamePhysics,s:&SkaterRuntime){snapshot(o,p,s)}\n}\npub(crate) fn migration_footplant_shared_snapshot(o:&mut crate::Output,p:&super::GamePhysics,s:&super::SkaterRuntime){migration::shared(o,p,s)}\n'
    atail=b'\npub(super) fn observe(o:&mut Output,a:&AirReckoning,r:&RidingOutputs){out_state(o,&a.state);for w in *r.body_spin.words(){o.word(w)}for w in r.reckoning.migration_air_reckoning_words(){o.word(w)}out_frames(o,&r.reckoning_frames);}\n}\npub(crate) fn migration_lifecycle_observe(o:&mut crate::Output,a:&AirReckoning,r:&RidingOutputs){migration::observe(o,a,r)}\n'
    extensions={'physics/handplant.rs':b'\n'+hprefix+lprefix+htail,
        'physics/air_reckoning.rs':b'\n'+aprefix+atail,
        'physics/footplant.rs':b'\n'+(PLUGIN/'Tests/Reference/footplant_observer.rs').read_bytes(),
        'physics/footplant/ground.rs':b'\npub(crate) fn migration_footplant_start(f:&mut Footplant,c:[f32;4],v:[f32;4])->u32{f.start(c,v)}\npub(crate) fn migration_footplant_adjust(f:&mut Footplant,t:f32,a:[f32;2]){f.adjust(t,a)}\n',
        'physics/air_trajectory/mod.rs':b'\n'+(PLUGIN/'Tests/Reference/footplant_trajectory_observer.rs').read_bytes(),
        'physics.rs':b'\npub(crate) fn migration_footplant_run(a:&std::path::Path,f:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{footplant::migration_footplant_run(a,f,i,o)}\n'}
    staged={}
    for p in sorted(host.rglob('*.rs')):
        rel=p.relative_to(host).as_posix()
        if rel in ('lib.rs','main.rs'):continue
        raw=p.read_bytes();extra=extensions.get(rel,b'');dest=crate/'src'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw+extra);assert dest.read_bytes()[:len(raw)]==raw
        staged[rel]=dict(original_prefix_bytes=len(raw),original_prefix_sha256=digest(p),append_sha256=hashlib.sha256(extra).hexdigest(),generated_sha256=digest(dest))
    core={'crates/skate-core/src/riding/ground_orientation.rs':lifecycle.air.CORE_OBSERVER.encode(),
          'crates/skate-core/src/physics/skeleton_motion.rs':b'\nimpl SkeletonMotion {pub fn migration_lifecycle_previous(&self)->f32{self.previous_board_at_y}}\n',
          'crates/skate-core/src/air/trajectory/selector.rs':b'\nimpl TrajectorySelector {pub fn migration_footplant_stage(&self)->[u32;2]{[u32::from(self.pass),u32::from(self.adjusted_on_vert)]}}\n'}
    for rel,extra in core.items():p=observed/rel;raw=(original/rel).read_bytes();p.write_bytes(raw+extra);assert p.read_bytes()[:len(raw)]==raw
    template=PLUGIN/'Tests/Reference/footplant_probe.rs';shutil.copy2(template,crate/'src/migration_probe.rs')
    cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text()+'''
skate-core={path="../crates/skate-core"}
skate-data={path="../crates/skate-data"}
skate-net={path="../crates/skate-net"}
half="2.7.1"
bevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}
[[bin]]
name="footplant-reference"
path="src/migration_probe.rs"
''')
    subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(cargo),'--target-dir',str(target.resolve()),'--bin','footplant-reference'],check=True)
    for rel,sha in report['original_source_sha256'].items():
        assert digest(original/rel)==sha
        raw=(original/rel).read_bytes();assert (observed/rel).read_bytes()[:len(raw)]==raw
    for rel,row in staged.items():assert digest(crate/'src'/rel)==row['generated_sha256']
    binary=output/'footplant-reference';shutil.copy2(target.resolve()/'release/footplant-reference',binary)
    report.update(staged_host_original_prefixes=staged,extracted_observer_prefixes=[hmeta,lmeta,ameta],
        appended_core_observers={rel:dict(original_prefix_sha256=digest(original/rel),generated_sha256=digest(observed/rel),observer_sha256=hashlib.sha256(extra).hexdigest())for rel,extra in core.items()},
        probe_sha256=digest(template),binary_sha256=digest(binary),scope='Whole unchanged original host and core. Only wire/explicit upstream caller input, read-only owner observations and original private-method accessibility wrappers append. No numerical method is replaced or stubbed.')
    (output/'reference-provenance.json').write_text(json.dumps(report,indent=2)+'\n');return binary

def build_simulation(output):
    snapshot=output/'simulation-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir();hashes={}
    for p in [*sorted(CODE.glob('*.h')),*[CODE/(u+'.cpp')for u in UNITS]]:shutil.copy2(p,snapshot/p.name);hashes[p.name]=digest(snapshot/p.name)
    for name in ('handplant_probe.cpp','footplant_probe.cpp'):
        p=PLUGIN/'Tests/Simulation'/name;shutil.copy2(p,snapshot/name);hashes[name]=digest(snapshot/name)
    prefix,meta=extraction(PLUGIN/'Tests/Simulation/handplant_lifecycle_probe.cpp','int main(')
    (snapshot/'handplant_lifecycle_helpers.inc').write_bytes(prefix)
    binary=output/'footplant-simulation';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'footplant_probe.cpp'),'-o',str(binary)],check=True)
    (output/'simulation-provenance.json').write_text(json.dumps(dict(immutable_simulation_sources=hashes,extracted_helper_prefix=meta,units=UNITS),indent=2)+'\n');return binary

class Reader(lifecycle.Reader):
    def foot(self):
        assert self.word()==len(FOOT);v={};self.foot_spans={}
        for n in FOOT:
            size=self.word();at=self.at;v[n]=self.take(size);self.foot_spans[n]=[at,self.at]
        assert len(v['owner'])==139 and len(v['settings'])==33 and len(v['air_output'])==8 and len(v['wipeout'])==73 and len(v['collision_groups'])==26
        return v

def decode(raw,cases):
    r=Reader(raw);assert r.word()==len(cases);frames=[]
    for c in cases:
        c['first_output_word']=r.at;assert r.word()==len(c['commands']);foot=r.foot();shared=r.snapshot();rows=[]
        for cmd in c['commands']:
            at=r.at;assert r.word()==cmd[0];error=r.status();extra=r.take(r.word());f=r.foot();foot_spans=r.foot_spans.copy();s=r.snapshot()
            rows.append(dict(operation=cmd[0],error=error,extra=extra,foot=f,prior=foot,shared=s,shared_prior=shared,first_word=at,last_word=r.at,spans={**foot_spans,**r.spans}));foot,shared=f,s
        c['last_output_word']=r.at;frames.append(rows)
    assert r.at==len(r.words);return frames

def trajectory_observation(raw):
    r=lifecycle.numeric.Reader(struct.pack('<'+'I'*len(raw),*raw));flags=r.take(8);launch=r.take(70)if r.word()else None
    requests=[r.take(16)for _ in range(r.word())];selection=None
    if r.word():selection=r.take(81)
    pending=[r.take(32)for _ in range(r.word())]if r.word()else None
    provider=r.word();nearby=r.take(r.word());assert r.at==len(raw)
    return dict(flags=flags,launch=launch,requests=requests,selection=selection,pending=pending,provider=provider,nearby=nearby)

def coverage(frames,cases):
    c=Counter();durations=set();curves=set();queries=set();targets=set();roots=set();partial=0;real_hits=0;active=0;query_errors=0;toolkit_errors=0;mode_errors=0;started=0;ground_success=0;launched=0;filter_counts=set();nan_x_misses=0;nan_w_errors=0
    for rows,case in zip(frames,cases):
      known_packet=None
      for row,cmd in zip(rows,case['commands']):
        op=cmd[0];c[OPS[op]]+=1;f=row['foot'];old=row['prior'];s=f['owner'];before=old['owner'];a=trajectory_observation(f['trajectory'])
        # Owner offsets: enabled0,result1..32,toe33,booleans34..41,
        # scalars42..47,surface48,retained vectors49..80,curve81..96,
        # com/animation/launch/lock97..112,request113..125,completed126..138.
        # The actual checked record length below is derived from field widths.
        if op==2:known_packet=cmd
        if op==5:
            if known_packet[5]==0x7fc00000:
                assert row['error']is None and s[13]==bits(-1) and s[-9]==0x7fc00000
                nan_x_misses+=1
            if known_packet[8]==0x7fc00000:
                assert row['error']=='Non-finite trajectory collision request or invalid radius'
                nan_w_errors+=1
            queries.add(tuple(s[1:33]));real_hits+=s[35];active+=s[40]
            if row['error']:
                query_errors+=1;assert s[1:33]==before[1:33];assert s[-13:]==before[-13:];assert s[0]==before[0]
        if op in (6,11):
            durations.add(s[43]);curves.add(tuple(s[81:97]))
            if op==11:
                frames_count=row['extra'][0]
                if frames_count==0:assert s[43]==before[43] and s[81:97]==before[81:97]
                else:started+=1;assert frames_count>=4
            else:
                assert row['error']is None
                for part in (15,16,19,20):assert f['collision_groups'][part]==4
        if op in (5,15):targets.add(tuple(row['shared']['ik']))
        if op==7:
            roots.add(tuple(row['shared']['roots']))
            if row['error']:
                partial+=row['shared']['roots']!=row['shared_prior']['roots'] or row['shared']['publication']!=row['shared_prior']['publication']
                toolkit_errors+=row['error']=='Air launch requires current BoardToolkit'
                mode_errors+=row['error']=='Invalid trajectory physics mode 9'
            else:ground_success+=1
            if a['launch']:
                launched+=1;assert a['launch'][67:69]==[1,1]
        if op==9:
            # Fields surviving Reset: result,current-up/selected/leg,curve,
            # completed trajectory,surface,enabled except FullReset.
            assert s[1:33]==before[1:33] and s[48]==before[48]
            assert s[57:73]==before[57:73] and s[81:97]==before[81:97] and s[-13:]==before[-13:]
            assert s[33]==0xffffffff and s[34:42]==[0]*8
            assert s[42:48]==fs([-1,-1,0,0,0,0]);assert s[0]==(0 if cmd[1]else before[0])
        if op==10:
            if s[35]:assert f['air_output'][:3]==[s[42],s[43],s[50]] and f['air_output'][3]==s[48]
            else:assert f['air_output']==cmd[1:]
        if op==14:filter_counts.add(row['extra'][0]);assert row['extra'][0]<=40
    assert started>=80 and ground_success>40 and launched>20
    assert len(durations)>16 and len(curves)>32 and len(queries)>16
    assert len(targets)>32 and len(roots)>64
    assert real_hits>8 and active>8, 'actual world query must create usable retained contact/IK'
    assert query_errors==nan_w_errors==nan_x_misses==4 and toolkit_errors>8 and mode_errors>=4 and partial>=8
    assert len(filter_counts)>2 and 0 in filter_counts
    for rows in frames:
        wipeout=rows[-1]['foot']['wipeout'];assert wipeout[6]==wipeout[23]==1 and wipeout[34+6]==bits(11) and wipeout[34+23]==0 and wipeout[68]>=2
    return dict(operations=dict(c),successful_starts=started,successful_ground_updates=ground_success,live_launch_rows=launched,distinct_durations=len(durations),distinct_curves=len(curves),distinct_queries=len(queries),distinct_ik=len(targets),distinct_roots=len(roots),retained_hits=real_hits,active_contact_rows=active,query_errors=query_errors,nan_x_successful_misses=nan_x_misses,nan_w_world_leaf_rejections=nan_w_errors,toolkit_errors=toolkit_errors,mode_errors=mode_errors,partial_failures=partial,filter_counts=sorted(filter_counts))

def preflight(raw,cases):
    words=struct.unpack('<'+'I'*(len(raw)//4),raw);at=1;ranges=[]
    lengths=(38,2,23,1,1,1,1,3,1,2,9,9,4,None,None,1,2,9,1)
    for c in cases:
        start=at*4
        n=words[at];at+=1+18*n;n=words[at];at+=1+10*n;assert words[at]==len(c['commands']);at+=1
        for cmd in c['commands']:
            expected=lengths[cmd[0]]
            if cmd[0]==13:expected=3 if cmd[1]else 2
            if cmd[0]==14:expected=6*cmd[1]+6
            assert len(cmd)==expected,(c['index'],cmd,len(cmd),expected)
            assert list(words[at:at+len(cmd)])==cmd;at+=len(cmd)
        ranges.append((start,at*4))
    assert at==len(words)
    for u in UNITS:assert (CODE/(u+'.cpp')).is_file(),u
    for p,boundary in (('Tests/Reference/handplant_observer.rs','pub(super) fn run('),('Tests/Reference/handplant_lifecycle_observer.rs','pub(super) fn run('),('Tests/Reference/air_reckoning_observer.rs','fn core_input('),('Tests/Simulation/handplant_lifecycle_probe.cpp','int main(')):extraction(PLUGIN/p,boundary)
    return ranges

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('assets','samples','output','target-dir'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--preflight',action='store_true')
    p.add_argument('--reference-case-runner',action='store_true',help='Run unchanged independent original cases under their own identified 2 GiB guards')
    p.add_argument('--reference-workers',type=int,choices=(1,2,3,4),default=1,help='Root-selected measured capacity; used only with --reference-case-runner')
    a=p.parse_args()
    if not a.reference_case_runner and a.reference_workers!=1:p.error('--reference-workers requires --reference-case-runner')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);inputs,cases=corpus();ranges=preflight(inputs,cases)
    (out/'input.bin').write_bytes(inputs);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    if a.preflight:print(json.dumps(dict(cases=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(inputs),units=len(UNITS)),indent=2));return
    fixtures=out/'fixtures';fixtures.mkdir(exist_ok=True);stock=a.assets.resolve()/'private/stock'
    (fixtures/'settings.simulation').write_bytes(converter.encode_settings(stock/'skater-collections.json'));(fixtures/'physics.simulation').write_bytes(converter.encode_physics_skeletons(stock/'physics-skeletons.json'))
    for k in ('action','motion'):(fixtures/f'actor.{k}.reference').write_bytes(original_graph(element('state','idle')))
    identity=json.loads((stock/'physics-skeletons.json').read_text())['source_sha256'];reference=build_reference(out/'reference',a.target_dir);simulation=build_simulation(out)
    if a.reference_case_runner:
        from copy import deepcopy
        from reference_case_runner import run_reference_cases
        expected=run_reference_cases(reference,[a.assets.resolve(),fixtures],inputs,ranges,
            out/'reference-cases',workers=a.reference_workers,
            validate_output=lambda index,raw:decode(raw,[deepcopy(cases[index])]))
    else:expected=subprocess.check_output([str(reference),str(a.assets.resolve()),str(fixtures)],input=inputs)
    actual=subprocess.check_output([str(simulation),str(fixtures/'settings.simulation'),str(fixtures/'physics.simulation'),str(a.samples.resolve()/'simulation/rig.skate'),identity,str(a.assets.resolve())],input=inputs)
    (out/'reference.bin').write_bytes(expected);(out/'simulation.bin').write_bytes(actual);frames=decode(expected,cases)
    if expected!=actual:
        at=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));word=at//4
        case=next((c for c in cases if c['first_output_word']<=word<c['last_output_word']),None);row=next((r for rows in frames for r in rows if r['first_word']<=word<r['last_word']),None)
        section=next(((n,word-span[0])for n,span in(row['spans'].items()if row else[])if span[0]<=word<span[1]),None)
        failure=dict(byte=at,reference_bytes=len(expected),simulation_bytes=len(actual),case=case['index']if case else None,operation=row['operation']if row else'initial',section=section,reference_hex=expected[max(0,at-16):at+32].hex(),simulation_hex=actual[max(0,at-16):at+32].hex());(out/'first-divergence.json').write_text(json.dumps(failure,indent=2)+'\n');raise AssertionError(failure)
    result=dict(passed=True,reference_revision=REFERENCE_REVISION,cases=len(cases),commands=sum(len(c['commands'])for c in cases),bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),input_sha256=hashlib.sha256(inputs).hexdigest(),coverage=coverage(frames,cases),scope='Complete Footplant stock settings/retained reset/publication, actual candidate/launch/real world-query prediction, nearby-edge filter, lock/IK/collision, ground Enter/Update/PostPhysics and concrete PlantSkeleton→air launch/update with source errors/partial writes.',boundaries='KnownAir trajectory/player packets, authored primitive endpoints and selected-toe caller helper cases are explicit upstream inputs. Queries, hits, curves, release velocities, IK, plant pose, and selector Launch/Update are actual original/simulation producers. Ground trajectory admission uses a genuinely empty StaticProvider domain on both sides; full stock grind admission and global frame scheduling remain separate. No completed hit/trajectory/up or callback is substituted. Info logging is not asserted.')
    if a.reference_case_runner:result['reference_execution']=dict(strategy='exact independent outer cases, original constructors per case',workers=a.reference_workers,worker_limit_bytes=2*1024**3,report='reference-cases/result.json')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
