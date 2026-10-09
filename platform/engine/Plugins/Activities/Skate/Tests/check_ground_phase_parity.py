#!/usr/bin/env python3
"""Complete unchanged original GroundPhase over real retained physical owners.

Only root runs guarded compilers and binaries. --preflight stages exact original
prefixes, immutable simulation units and validates every wire byte without compiling.
"""
import argparse
from collections import Counter
from functools import lru_cache
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
import check_ground_animation_parity as animation
import check_ground_runtime_parity as ground
import check_player_grind_input_parity as grind
import check_animation_trees_parity as trees
from camera_reference_build import frozen_sources
from check_gesture_parity import PLUGIN,converter
from check_graph_parity import element,original_graph
from session_parity import REFERENCE_REVISION,digest
foot=animation.foot
CODE=foot.CODE
UNITS=tuple(dict.fromkeys((*foot.UNITS,*ground.UNITS,'GroundPhaseRuntime')))
OPS=('publish','authored_pose','toolkit','enter','advance','reset_board','handplant_ground_update','skeleton_ground_update','clear_forces','append_force','seed_ground','seed_lifecycle','seed_grab','edge','pending_wall_jump','select_profile','reload_trajectory','bind_provider','ground_reckoning','collision_inputs','board_probes','start_probes','publish_probes','reset_probes')
SECTIONS=('state','runtime','lifecycle','board','grab','processed','settings','probes')
fs,bits=animation.fs,animation.bits

@lru_cache(maxsize=1)
def schema():return ground.schema()

def extract(path,boundary):return foot.extraction(path,boundary)
def block(path,marker):
    raw=path.read_text();text,metadata=trees.extract_block(raw,marker)
    assert raw.count(marker)==1 and text.startswith(marker)
    return text,dict(path=str(path.relative_to(PLUGIN)),marker=marker,source_sha256=digest(path),extracted_sha256=hashlib.sha256(text.encode()).hexdigest(),bytes=len(text.encode()))

def transport_helpers():
    cpp,rust,settings=ground.helpers();proof=[]
    ga=PLUGIN/'Tests/Reference/ground_animation_observer.rs'
    rhelpers=[]
    for marker in ('fn world(','fn loaded(','fn publish('):
        text,meta=block(ga,marker);rhelpers.append(text);proof.append(meta)
    query_world,meta=block(PLUGIN/'Tests/Reference/handplant_observer.rs','fn authored_query_world(');proof.append(meta);rhelpers.append(query_world)
    provider,meta=block(PLUGIN/'Tests/Reference/player_grind_input_probe.rs','fn read_provider(');proof.append(meta)
    rhelpers.append(provider)
    nhelpers=[]
    publish,meta=block(PLUGIN/'Tests/Simulation/ground_animation_probe.cpp','void GroundPublish(');nhelpers.append(publish);proof.append(meta)
    reader,meta=block(PLUGIN/'Tests/Simulation/player_grind_input_probe.cpp','PlayerGrindStaticProvider ReadProvider(');proof.append(meta)
    # Only a transport adapter changes: shared Input has Floats/Word and the
    # fixture constructor returns a checked optional rather than calling Fail.
    reader=reader.replace('i.Text()','Text(i)').replace('i.Vector()','i.Floats<3>()')
    reader=reader.replace('i.Array<float,4>([](Input& r){return r.Float();})','i.Floats<4>()').replace('i.Array<float,3>([](Input& r){return r.Float();})','i.Floats<3>()')
    reader=reader.replace('if(!provider)Fail(error.c_str());','if(!provider)std::abort();')
    nhelpers += ['std::string Text(Input& i){const auto n=i.Word();std::string value;for(unsigned k=0;k<n;++k)value+=char(i.Word());return value;}',reader]
    cached=PLUGIN/'Tests/Reference/ground_runtime_probe.rs';raw=cached.read_text();a='// CACHE_PRIVACY_BEGIN\n';b='// CACHE_PRIVACY_END';assert raw.count(a)==raw.count(b)==1;cache=raw.split(a,1)[1].split(b,1)[0]
    proof.append(dict(path=str(cached.relative_to(PLUGIN)),start=a,end=b,source_sha256=digest(cached),extracted_sha256=hashlib.sha256(cache.encode()).hexdigest(),bytes=len(cache.encode())))
    cache=cache.replace('pub fn seed(','pub fn migration_seed(').replace('pub fn observe(','pub fn migration_observe(')
    for marker in ('OffboardGrabRecord GroundGrabRecord(','void SeedGroundGrab(','void OutGroundGrabRecord(','void OutGroundGrab('):
        text,meta=block(PLUGIN/'Tests/Simulation/ground_runtime_probe.cpp',marker);proof.append(meta)
        if marker.startswith('void Out'):
            text=text.replace('void OutGroundGrabRecord(','void OutGroundGrabRecord(GroundOutputWriter& o,').replace('void OutGroundGrab(','void OutGroundGrab(GroundOutputWriter& o,').replace('Out(', 'o.Value(').replace('OutGroundGrabRecord(r)','OutGroundGrabRecord(o,r)').replace('OutGroundGrabRecord(*r)','OutGroundGrabRecord(o,*r)')
        nhelpers.append(text)
    state="""
pub(super) fn migration_observe(o:&mut crate::Output,s:&GroundState){crate::observe_PhysicsGroundState(o,&s.state);crate::observe_PumpingState(o,&s.pumping);o.words(s.wobble.0);crate::observe_TruckSteeringState(o,&s.steering);crate::observe_SpeedModelState(o,&s.speed);crate::observe_ManualState(o,&s.manual);o.float(s.heading_previous);o.word(s.entered as u32);o.floats(s.output_settings.pushable_speed_terms_4_8);o.float(s.output_settings.mode_speed_threshold_0);o.words(s.auto_push_enabled.map(u32::from));super::entry::migration_observe(o,&s.entry_settings);super::pumping::migration_observe(o,&s.pumping_settings);}
"""
    append={'physics/riding_outputs/probes.rs':b'\nimpl BoardProbes {pub(crate) fn migration_observe(&self,o:&mut crate::Output){fn state(o:&mut crate::Output,s:&BoardProbeState){o.vector(s.start);o.vector(s.point);o.vector(s.normal);o.word(s.surface_tag);o.word(s.hit as u32)}fn hit(o:&mut crate::Output,h:Option<BoardProbeHit>){o.word(h.is_some()as u32);if let Some(h)=h{o.vector(h.point);o.vector(h.normal);o.word(h.surface_tag)}}state(o,&self.deck);state(o,&self.wall);o.word(self.wall_line.is_some()as u32);if let Some(l)=self.wall_line{o.vector(l.start);o.vector(l.end)}o.word(self.pending.is_some()as u32);if let Some(p)=&self.pending{hit(o,p.deck);o.word(p.wall.is_some()as u32);if let Some(w)=p.wall{hit(o,w)}}}}\n',
        'physics/ground_runtime/state.rs':state.encode(),
        'physics/ground_runtime/entry.rs':b'\npub(super) fn migration_observe(o:&mut crate::Output,s:&EntrySettings){o.floats([s.deck_angular_drag,s.powerslide_exit,s.landing_strength,s.landing_offset]);}\n',
        'physics/ground_runtime/pumping.rs':b'\npub(super) fn migration_observe(o:&mut crate::Output,s:&GroundPumping){crate::observe_PumpingSettings(o,&s.settings);for m in s.modes{crate::observe_PumpingMode(o,&m.controller);o.float(m.unintentional_scalar);}}\n',
        'physics/ground_runtime/settings.rs':settings.encode(),
        'physics/biped_ground/grab_runtime.rs':cache.encode(),
        'physics/ground_runtime/mod.rs':b'\npub(crate) fn migration_observe_state(o:&mut crate::Output,s:&GroundState){state::migration_observe(o,s);}pub(crate) fn migration_observe_settings(o:&mut crate::Output,s:&GroundSettings){settings::observe_GroundSettings(o,s);}pub(crate) fn migration_observe_runtime(o:&mut crate::Output,s:&GroundRuntime){o.floats(s.retained_board_normal);let c=s.contact;o.word(c.active_2731 as u32);o.word(c.tag_16_force.tag);o.vector(c.tag_16_force.force_world);o.vector(c.tag_16_force.point_body);o.floats(c.vector_2688);o.float(c.scalar_2704);o.word(c.animated_board_2708 as u32);o.word(s.collision_force.is_some()as u32);if let Some(c)=s.collision_force{o.floats(c.force_2528);o.floats(c.point_2544);o.floats(c.vector_2592);}}\n'}
    return dict(phase_helpers='\n'.join(rhelpers).encode(),simulation_helpers='\n'.join(nhelpers).encode(),host_append=append),proof,cpp,rust

def build_reference(output, target, *, compile=True):
    original, report = frozen_sources(output); observed = output / 'observed-source'
    if observed.exists(): shutil.rmtree(observed)
    shutil.copytree(original, observed); crate = observed / 'atelier-host'; host = original / 'crates/skate-host/src'
    hprefix, hmeta = extract(PLUGIN / 'Tests/Reference/handplant_observer.rs', 'pub(super) fn run(')
    lprefix, lmeta = extract(PLUGIN / 'Tests/Reference/handplant_lifecycle_observer.rs', 'pub(super) fn run(')
    aprefix, ameta = extract(PLUGIN / 'Tests/Reference/air_reckoning_observer.rs', 'fn core_input(')
    fprefix, fmeta = extract(PLUGIN / 'Tests/Reference/footplant_observer.rs', 'pub(super) fn run(')
    htail = b'\npub(super) fn shared(o:&mut Output,p:&GamePhysics,s:&SkaterRuntime){snapshot(o,p,s)}\n}\npub(crate) fn migration_footplant_shared_snapshot(o:&mut crate::Output,p:&super::GamePhysics,s:&super::SkaterRuntime){migration::shared(o,p,s)}\n'
    atail = b'\npub(super) fn observe(o:&mut Output,a:&AirReckoning,r:&RidingOutputs){out_state(o,&a.state);for w in *r.body_spin.words(){o.word(w)}for w in r.reckoning.migration_air_reckoning_words(){o.word(w)}out_frames(o,&r.reckoning_frames);}\n}\npub(crate) fn migration_lifecycle_observe(o:&mut crate::Output,a:&AirReckoning,r:&RidingOutputs){migration::observe(o,a,r)}\n'
    ftail = b'\npub(super) fn observe(o:&mut Output,p:&GamePhysics,s:&SkaterRuntime,f:&skate_core::player::input_phase::AirOutputFields){snapshot(o,p,s,f)}\n}\npub(crate) fn migration_ground_snapshot(o:&mut crate::Output,p:&super::GamePhysics,s:&super::SkaterRuntime,f:&skate_core::player::input_phase::AirOutputFields){migration::observe(o,p,s,f)}\n'
    observer = PLUGIN / 'Tests/Reference/ground_phase_observer.rs'
    ext, adapter_proof, generated_cpp, generated_rust = transport_helpers()
    observer_bytes = observer.read_bytes().replace(b'// GENERATED_TRANSPORT_HELPERS', ext['phase_helpers'])
    additions = {'physics/handplant.rs': b'\n' + hprefix + lprefix + htail,
                 'physics/air_reckoning.rs': b'\n' + aprefix + atail,
                 'physics/footplant.rs': b'\n' + fprefix + ftail,
                 'physics/ground_phase.rs': b'\n' + observer_bytes, **ext['host_append'],
                 'physics/air_trajectory/mod.rs': b'\n' + (PLUGIN / 'Tests/Reference/footplant_trajectory_observer.rs').read_bytes(),
                 'physics.rs': b'\npub(crate) use ground_runtime::{GroundSettings,GroundLaunchInfo,GroundLaunchPhysical};\npub(crate) fn migration_ground_phase_run(a:&std::path::Path,f:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{ground_phase::migration_ground_phase_run(a,f,i,o)}\n'}
    staged = {}
    for path in sorted(host.rglob('*.rs')):
        relative = path.relative_to(host).as_posix()
        if relative in ('lib.rs', 'main.rs'): continue
        raw = path.read_bytes(); extra = additions.get(relative, b''); destination = crate / 'src' / relative
        destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(raw + extra)
        assert destination.read_bytes()[:len(raw)] == raw
        staged[relative] = dict(original_prefix_bytes=len(raw), original_prefix_sha256=digest(path),
                                append_sha256=hashlib.sha256(extra).hexdigest(), generated_sha256=digest(destination))
    core = {'crates/skate-core/src/riding/ground_orientation.rs': foot.lifecycle.air.CORE_OBSERVER.encode(),
            'crates/skate-core/src/physics/skeleton_motion.rs': b'\nimpl SkeletonMotion {pub fn migration_lifecycle_previous(&self)->f32{self.previous_board_at_y}}\n',
            'crates/skate-core/src/air/trajectory/selector.rs': b'\nimpl TrajectorySelector {pub fn migration_footplant_stage(&self)->[u32;2]{[u32::from(self.pass),u32::from(self.adjusted_on_vert)]}}\n'}
    for relative, extra in core.items():
        raw = (original / relative).read_bytes(); (observed / relative).write_bytes(raw + extra)
        assert (observed / relative).read_bytes()[:len(raw)] == raw
    template = PLUGIN / 'Tests/Reference/ground_phase_probe.rs'; (crate / 'src/migration_probe.rs').write_bytes(template.read_bytes().replace(b'// GENERATED_GROUND_PROTOCOL', generated_rust.encode()))
    cargo = crate / 'Cargo.toml'; cargo.write_text(cargo.read_text() + '''
skate-core={path="../crates/skate-core"}
skate-data={path="../crates/skate-data"}
skate-net={path="../crates/skate-net"}
half="2.7.1"
bevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}
[[bin]]
name="ground-phase-reference"
path="src/migration_probe.rs"
''')
    binary = output / 'ground-phase-reference'
    if compile:
        subprocess.run(['cargo', '+1.97.1', 'build', '--release', '--offline', '--jobs', '2', '--manifest-path', str(cargo), '--target-dir', str(target.resolve()), '--bin', 'ground-phase-reference'], check=True)
        shutil.copy2(target.resolve() / 'release/ground-phase-reference', binary)
        report['binary_sha256'] = digest(binary)
    for relative, sha in report['original_source_sha256'].items():
        assert digest(original / relative) == sha
        raw = (original / relative).read_bytes(); assert (observed / relative).read_bytes()[:len(raw)] == raw
    for relative, row in staged.items(): assert digest(crate / 'src' / relative) == row['generated_sha256']
    report.update(staged_host_original_prefixes=staged, extracted_observer_prefixes=[hmeta, lmeta, ameta, fmeta],
        appended_core_observers={relative: dict(original_prefix_sha256=digest(original / relative), generated_sha256=digest(observed / relative), observer_sha256=hashlib.sha256(extra).hexdigest()) for relative, extra in core.items()},
        probe_sha256=digest(template), observer_sha256=digest(observer), transport_helper_extractions=adapter_proof, scope='Whole original host/core prefixes remain byte-for-byte unchanged. Appended methods only supply explicit upstream caller fields and observe private owners. Complete GroundPhase Enter/Advance/reset and later input_phase::update_ground execute with original skeleton, board, world, trajectory, settings and simulation helpers. No numerical method or callback is replaced.')
    (output / 'reference-provenance.json').write_text(json.dumps(report, indent=2) + '\n'); return binary

def build_simulation(output, *, compile=True):
    snapshot = output / 'simulation-source'
    if snapshot.exists(): shutil.rmtree(snapshot)
    snapshot.mkdir(); hashes = {}
    for path in [*sorted(CODE.glob('*.h')), *[CODE / (u + '.cpp') for u in UNITS]]:
        shutil.copy2(path, snapshot / path.name); hashes[path.name] = digest(snapshot / path.name)
    for name in ('handplant_probe.cpp', 'ground_phase_probe.cpp'):
        path = PLUGIN / 'Tests/Simulation' / name; shutil.copy2(path, snapshot / name); hashes[name] = digest(snapshot / name)
    hprefix, hmeta = extract(PLUGIN / 'Tests/Simulation/handplant_lifecycle_probe.cpp', 'int main(')
    fprefix, fmeta = extract(PLUGIN / 'Tests/Simulation/footplant_probe.cpp', 'KnownAirFootplantInput Packet(')
    (snapshot / 'handplant_lifecycle_helpers.inc').write_bytes(hprefix)
    (snapshot / 'ground_phase_helpers.inc').write_bytes(fprefix + b'\n} // namespace\n')
    ext, adapter_proof, generated_cpp, generated_rust = transport_helpers()
    probe = snapshot / 'ground_phase_probe.cpp'
    probe.write_bytes(probe.read_bytes().replace(b'// GENERATED_GROUND_PROTOCOL', generated_cpp.encode()).replace(b'// GENERATED_TRANSPORT_HELPERS', ext['simulation_helpers']))
    hashes[probe.name] = digest(probe)
    binary = output / 'ground-phase-simulation'
    if compile:
        subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math', '-fno-exceptions', '-fno-rtti', '-Wall', '-Wextra', '-Werror', '-I', str(snapshot), *[str(snapshot / (u + '.cpp')) for u in UNITS], str(snapshot / 'ground_phase_probe.cpp'), '-o', str(binary)], check=True)
    for name, sha in hashes.items(): assert digest(snapshot / name) == sha
    (output / 'simulation-provenance.json').write_text(json.dumps(dict(immutable_simulation_sources=hashes, extracted_helper_prefixes=[hmeta, fmeta], transport_helper_extractions=adapter_proof, units=UNITS), indent=2) + '\n'); return binary


def encoded(kind,value):
    definitions=schema();stream=ground.Stream();ground.encode_value(stream,kind,value,definitions)
    return list(struct.unpack('<'+'I'*(len(stream.data)//4),stream.data))

def publication(n, *, wall=False, held=False, mode=None):
    words=animation.publish(n,jump=False,mode=mode,collision=(n%5==0))
    words[1]|=0x2000
    # Explicit canonical processed records: GrabWorld(2476 bit22),
    # previous/current state and the physical wall normal/up used by BoardProbes.
    words[3]=(1<<22) if held else 0
    words[4]=(1<<28) if held else 0
    words[5]=0
    words[8]=(101,503,201,100)[n%4]
    words[9]=100 if wall else 200
    if held and not wall:
        words[30:34]=fs([(-1 if n%2 else 1)*(1.137+(n%5)*.137),4.731+(n%7)*.137,.0317,.1731])
        words[38:42]=fs([0,.6,.8,.317])
        words[66:70]=fs([math.sin(n*.137)*.137,.731,0,.137])
    if wall:
        words[38:42]=fs([1,.137,0,.317])
        words[58:62]=fs([1,.137,0,.1731])
        words[12]=1
    extra=[(200,500,200,100)[n%4],n+2]+fs([.5,.137+(n%5)*.0317,(-.5,.1731)[n%2],.731,.2,-.02,.125])+[0,0xffffffff]+fs([.137,.731,-.317,.1731])+fs([(-.5,.25,.75)[n%3],(.137,.731)[n%2]])
    return words+extra

def state_seed(n,entered=True):
    d=schema();v=ground.board.initial_state(d,n)
    v.update(flag_2708=False,vector_2688=[.317,.137,.731,.1731],collision_countdown_2652=(0,.25,.5)[n%3],hang_detection_frames_2740=(0,19,20)[n%3],hung_wipeout_frames_2748=(0,20,21)[n%3],anti_flip_nudge_frames_2752=(0,13,14)[n%3])
    pump=ground.default('PumpingState',d);pump.update(record_valid=True,intentional_pumping=n%3,pumping=.2,pump_acceleration=.125,absorption=.1)
    return [10]+encoded('PhysicsGroundState',v)+encoded('PumpingState',pump)+[int(entered)]

def lifecycle_seed(n):
    return [11,n%7,6,n%2,(n//2)%2,1,1,(0,1,255)[n%3]]+fs([.731,-.317])+[n%3]+fs([.137])+[1]

def authored_world(geometry,n):
    # Explicit real scene metadata, separate from rendering tags. Preserve
    # supplied canonical triangles and all primitive occurrence order.
    count=geometry[0];packed=[0x203+(k%3)*0x80 for k in range(count)];mesh=[0]
    if count:
        points=[[float_(geometry[1+k*18+v*3+d])for d in range(3)]for k in range(count)for v in range(3)]
        minimum=[min(p[d]for p in points)for d in range(3)];maximum=[max(p[d]for p in points)for d in range(3)]
        mesh=[1,0,count]+fs(minimum+maximum)+[0xffffffff,0xffffffff,0x82d38800+n,n%3]
    return geometry+[count]+packed+mesh+[3]

def corpus():
    cases=[];records=[]
    for n in range(4):
        world=foot.lifecycle.numeric.world(0 if n!=3 else 2)
        for k in range(world[0]):
            for v in range(3):world[1+k*18+v*3+1]=bits(-.75+(n%3)*.137)
        world=authored_world(world,n)
        provider=grind.authored_provider([[-2,.944+(n%3)*.113,-.317],[2,.944+(n%3)*.113,-.317]],name=f'ground-phase-authored-{n}')
        commands=[publication(n,held=True),[1,n],[2,1],[4],lifecycle_seed(n),[12,17+n,255],[3],[5]]
        for k in range(96):
            j=n*96+k;wall=k%4==1
            commands += [publication(j,wall=wall,held=k%3!=0),[1,(n+k//12)%4],[2,1],[15,j%5,k%5+1]]
            if k%12==0:commands += [state_seed(j),lifecycle_seed(j),[3]]
            commands += [[18],[20],[8],[4],[6],[7]]
            if k%17==0:commands += [[12,j+1,255],[5]]
        # Ordered early errors must retain the actual Handplant submission.
        for mode,toolkit,pending in ((9,0,0),(1,0,0),(1,1,1)):
            commands += [publication(n+1,held=True,mode=mode),[1,n],[2,toolkit]]
            if pending:
                v=ground.default('GroundLaunchInfo',schema());commands += [[14,1]+encoded('GroundLaunchInfo',v)]
            commands += [[4],[14,0],[2,1]]
        # Actual animated wall jump reaches selector Update and its retained
        # provider error after the real upstream launch writes.
        commands += [publication(n+1,wall=True,held=True),[1,n],[2,1],[3],[20],[16],[4],[17],[4],[6],[7]]
        for kind in (4,5):commands += [publication(n+1),[1,kind],[2,1],[7],[1,n]]
        # Queue capacity retains the original prefix, while calculations and
        # subsequent future-deck/skeleton publications still execute.
        commands += [publication(n,held=False),[1,n],[2,1],[3],[8]]
        commands += [[9,0x100+k]+fs([.137*k,-.317,.731,.137,-.317,.731])for k in range(24)]
        commands += [[4],[7],[8],[5],[21],[21],[23],[22],[22]]
        stream=grind.Stream();grind.encode_provider(stream,provider)
        raw=struct.pack('<'+'I'*len(world),*world)+bytes(stream.data)+struct.pack('<I',len(commands))+b''.join(struct.pack('<'+'I'*len(c),*c)for c in commands)
        cases.append(dict(index=n,world=n,provider=provider,commands=commands,label='full original GroundPhase on real floor/empty world and authored provider; exact entry/query/controller/trajectory/plant/skeleton ordering'))
        records.append(raw)
    return struct.pack('<I',len(records))+b''.join(records),cases

class Reader(foot.Reader):
    def phase(self):
        assert self.word()==len(SECTIONS);values={};self.phase_spans={}
        for name in SECTIONS:
            size=self.word();at=self.at;values[name]=self.take(size);self.phase_spans[name]=[at,self.at]
        assert len(values['processed'])==14
        assert len(values['runtime'])in (19,31)
        return values

def decode(raw,cases):
    r=Reader(raw);assert r.word()==len(cases);frames=[]
    for case in cases:
        case['first_output_word']=r.at;assert r.word()==len(case['commands']);p=r.phase();f=r.foot();s=r.snapshot();rows=[]
        for cmd in case['commands']:
            at=r.at;assert r.word()==cmd[0];error=r.status();extra=r.take(r.word());phase=r.phase();spans=r.phase_spans.copy();foot_=r.foot();shared=r.snapshot()
            rows.append(dict(operation=cmd[0],error=error,extra=extra,phase=phase,prior=p,foot=foot_,foot_prior=f,shared=shared,shared_prior=s,first_word=at,last_word=r.at,spans={**spans,**{"foot_"+k:v for k,v in r.foot_spans.items()},**r.spans}));p,f,s=phase,foot_,shared
        case['last_output_word']=r.at;frames.append(rows)
    assert r.at==len(r.words);return frames

def ground_state(raw):
    definitions=schema();reader=ground.board.Words(raw)
    s=reader.value('PhysicsGroundState',definitions);pump={field:reader.word()if kind=='u8'else reader.value(kind,definitions)for field,kind in definitions['PumpingState']}
    wobble=reader.take(8);steering=reader.value('TruckSteeringState',definitions);speed=reader.value('SpeedModelState',definitions);manual=reader.value('ManualState',definitions);heading=reader.word();entered=reader.word()
    return dict(state=s,pumping=pump,wobble=wobble,steering=steering,speed=speed,manual=manual,heading=heading,entered=entered)

def board(raw):
    r=ground.board.Words(raw);wiping=r.word();group=r.word();volumes=r.take(3);children=r.take(r.word());materials=r.take(12);drag=r.take(14);queue=[r.take(7)for _ in range(r.word())];r.done()
    return dict(wiping=wiping,group=group,volumes=volumes,children=children,materials=materials,drag=drag,queue=queue)

def probes(raw):
    r=ground.board.Words(raw);deck=r.take(11);wall=r.take(11);line=r.take(6)if r.word()else None;pending=None
    if r.word():
        pending=dict(deck=r.take(7)if r.word()else None,wall=None)
        if r.word():pending['wall']=(r.take(7)if r.word()else [])
    r.done();return dict(deck=deck,wall=wall,line=line,pending=pending)

def grab(raw):
    # The wire contains the complete source-private owner. This decoder is
    # observation only; it checks Ground's source selective invalidation mask.
    r=ground.board.Words(raw)
    def record():
        words=r.take(72);identity=r.word();points=[r.take(4)for _ in range(r.word())];vectors=[r.take(4)for _ in range(r.word())];word60=r.word()
        return dict(words=words,identity=identity,points=points,vectors=vectors,word60=word60)
    def records():return [record()for _ in range(r.word())]
    queries=[r.take(36)for _ in range(r.word())];query=records()if r.word()else None;pending=records();validated=records();validation=None
    if r.word():
        validation=[]
        for _ in range(r.word()):
            if r.word():
                fraction=r.word();assembly=r.word()if r.word()else None;validation.append((fraction,assembly))
            else:validation.append(None)
    requests=[r.take(2)if r.word()else None for _ in range(2)];data=[record()if r.word()else None for _ in range(2)];ready=r.take(2);interactable_request=r.take(65)if r.word()else None;interactable_result=None
    if r.word():interactable_result=(r.word()if r.word()else [])
    latched=r.word();flags=r.word();positions=r.take(8);r.done()
    return dict(queries=queries,query=query,pending=pending,validated=validated,validation=validation,requests=requests,data=data,ready=ready,interactable_request=interactable_request,interactable_result=interactable_result,latched=latched,flags=flags,positions=positions)

def float_(word):return struct.unpack('<f',struct.pack('<I',word))[0]

def coverage(frames,cases):
    counts=Counter();paths=Counter();outcomes=Counter();short_poses=Counter();variants=set();roots=set();launches=set();candidates=set();blends=set();partial=0;predictions=0;processed=None;pose_kind=None
    prevalidation={"Ground::Enter must finish before Ground::Update","Ground update requires PlayerInput's current board toolkit",'Invalid trajectory physics mode 9','Ground wall jump is pending its trajectory selector continuation'}
    provider_error='Native Ground board update: Service { stage: CommitExternalPlayer, source: "Trajectory static grind provider was not registered" }'
    for rows,case in zip(frames,cases):
        for row,cmd in zip(rows,case['commands']):
            op=cmd[0];counts[OPS[op]]+=1;p=row['phase'];old=row['prior'];state=ground_state(p['state']);before=ground_state(old['state']);b=board(p['board']);prior_b=board(old['board']);h=foot.lifecycle.handplant(row['shared']['handplant']);old_h=foot.lifecycle.handplant(row['shared_prior']['handplant'])
            if op==0:processed=cmd
            if op==1:pose_kind=cmd[1]
            if op==3:
                assert row['error']is None and state['entered']==1
                assert p['lifecycle'][5:7]==[0,0] and b['group']==4 and b['wiping']==0
                assert b['volumes']==[1,1,1] and all(b['children'])
                assert state['wobble']==[0]*8 and state['state']['elapsed_2648']==0
                assert state['state']['straighten_scale_2672']==(0x3e23d70a if processed[8]==101 else bits(1))
                assert p['grab']==old['grab'], 'Ground entry does not retire offboard grab caches'
                assert row['foot']['wipeout'][-1]==1
                assert row['foot']['wipeout'][-2]==(row['foot_prior']['wipeout'][-2]if row['foot_prior']['wipeout'][-1]==1 else 0)
                paths['entry_real_owners']+=1
            if op==5:
                assert row['error']is None
                expected=copy.deepcopy(before['steering']);expected['deck_tilt']=0;expected['targets']=[0,0]
                assert state['steering']==expected
                assert p['runtime'][:4]==fs([0,1,0,0]) and p['runtime'][4:]==old['runtime'][4:]
                assert p['lifecycle'][:6]==old['lifecycle'][:6] and p['lifecycle'][7:]==old['lifecycle'][7:] and p['lifecycle'][6]==0
                assert state['state']==before['state'] and state['pumping']==before['pumping'] and state['wobble']==before['wobble'] and state['speed']==before['speed'] and state['manual']==before['manual'] and state['heading']==before['heading'] and state['entered']==before['entered']
                assert b['wiping']==0 and {k:v for k,v in b.items()if k!='wiping'}=={k:v for k,v in prior_b.items()if k!='wiping'}
                assert p['grab']==old['grab'] and p['probes']==old['probes'] and row['foot']==row['foot_prior'] and row['shared']==row['shared_prior']
                paths['selective_reset']+=1
            if op==4:
                variants.add(tuple(p['state']));roots.add(tuple(row['shared']['roots']))
                if h['candidate']:candidates.add(tuple(h['candidate']))
                # Query runs first even if selector/toolkit/continuation fails.
                if h['pending']:
                    assert h['pending'][15:]==processed[66:70]+processed[30:34]+processed[38:42]+processed[62:66]
                    paths['real_handplant_submission_before_ground']+=1
                    if row['error']in prevalidation:paths['submission_retained_on_early_error']+=1
                if not processed[3]&(1<<22):
                    assert h['pending']is None and h['candidate']is None and h['phase']==0x7f7fffff
                    paths['released_world_grab_full_reset']+=1
                if row['error']:
                    paths[row['error']]+=1
                    if row['error']in prevalidation:
                        assert p==old and b==prior_b
                        assert row['foot']==row['foot_prior']
                    else:
                        assert row['error']==provider_error, row['error']
                        assert state['state']['flag_2708']==1 and state['state']['flag_2720']==0
                        assert p['processed'][:4]==state['state']['vector_2688']
                        assert b['queue']==prior_b['queue'] and all(b['drag'][k]==0 for k in range(0,14,2))
                        a=foot.trajectory_observation(row['foot']['trajectory']);assert a['provider']==0 and a['launch']is not None
                    partial+=row['shared']!=row['shared_prior']or p!=old or row['foot']!=row['foot_prior']
                else:
                    assert len(row['extra'])==6 and state['entered']==1
                    outcomes[row['extra'][0]]+=1
                    assert row['shared']['publication'][-1]==1, 'Ground finishes by publishing correction pending'
                    assert state['state']['elapsed_2648']==bits(float_(before['state']['elapsed_2648'])+float_(processed[13]))
                    expected=grab(old['grab']);expected.update(queries=[],query=None,validation=None,ready=[0,0],flags=expected['flags']&0x3f)
                    assert grab(p['grab'])==expected
                    if old['grab']!=p['grab']:paths['selective_grab_cache_invalidation']+=1
                    predictions+=row['shared']['roots'][100:104]!=row['shared_prior']['roots'][100:104]
                    if row['extra'][0]==0:
                        assert p['processed'][:4]==state['state']['vector_2688'] and state['state']['flag_2720']==1
                    if row['extra'][0]==1:
                        assert state['state']['collision_countdown_2652']!=0
                        expected_queue=prior_b['queue']+([[15]+state['state']['collision_force_2528'][:3]+state['state']['collision_point_2544'][:3]]if len(prior_b['queue'])<21 else [])
                        assert b['queue']==expected_queue and row['extra'][1]==int(len(prior_b['queue'])<21)
                    if len(prior_b['queue'])==21:assert b['queue']==prior_b['queue'];paths['queue_capacity_preserves_prefix']+=1
                trajectory=foot.trajectory_observation(row['foot']['trajectory'])
                if trajectory['launch']:launches.add(tuple(trajectory['launch']))
            if op==6 and row['error']is None:
                assert h['pending']is None
                if old_h['pending']:paths['consumed_real_handplant_candidate']+=1
                paths['handplant_ground_consume']+=1
            if op==7:
                if row['error']:
                    assert row['error']=='IK original joint is absent from the current pose'
                    assert pose_kind in (4,5);short_poses[pose_kind]+=1
                    # PrepareGround and GeneralUpdate's root derivative run
                    # before FootIK maps the authored joints. FinishGround,
                    # drives/gravity and SkeletonAir capture do not run after
                    # that exact failure. These inputs repeat an unchanged
                    # root position, so the actual derivative becomes zero.
                    assert p==old and row['foot']==row['foot_prior']
                    s=row['shared'];previous=row['shared_prior']
                    assert all(s[k]==previous[k]for k in s if k!='publication')
                    assert s['publication'][:11]+s['publication'][15:]==previous['publication'][:11]+previous['publication'][15:]
                    assert previous['publication'][15:19]==s['roots'][60:64]
                    assert s['publication'][15:19]==s['roots'][60:64]
                    assert s['publication'][11:15]==[0]*4
                    if s['publication']!=previous['publication']:
                        assert pose_kind==4
                        assert all(previous['publication'][i]!=0 for i in (11,12,13))
                        paths['short_pose_root_velocity_cleared']+=1
                    else:paths['short_pose_idempotent_prefix']+=1
                    paths['short_hierarchy']+=1
                else:
                    paths['ground_skeleton_capture']+=1
                    blends.add(tuple(row['shared']['bodies_blend'][:5]))
                    if row['shared']['bodies_blend'][:4]!=row['shared_prior']['bodies_blend'][:4]:paths['captured_board_animation_error_changes']+=1
            if op==9:assert b['queue']==prior_b['queue']+([cmd[1:]]if len(prior_b['queue'])<21 else [])
            if op==20:
                assert row['error']is None
                observation=probes(p['probes']);assert observation['pending']is None
                if observation['wall'][10]:paths['actual_wall_query_hit']+=1
                if observation['deck'][10]:paths['actual_deck_query_hit']+=1
            if op==21:
                observation=probes(p['probes']);previous=probes(old['probes'])
                if previous['pending']is not None:
                    assert row['error']=='Board probes submitted twice without publication' and observation==previous
                    paths['duplicate_probe_submission_rejected']+=1
                else:assert row['error']is None and observation['pending']is not None
            if op==22:
                observation=probes(p['probes']);previous=probes(old['probes'])
                if previous['pending']is None:
                    assert row['error']=='Board probe publication requires a submitted batch' and observation==previous
                    paths['missing_probe_batch_rejected']+=1
                else:assert row['error']is None and observation['pending']is None
            if op==23:
                observation=probes(p['probes']);expected=probes(old['probes']);expected.update(deck=[0]*11,wall=[0]*11)
                assert row['error']is None and observation==expected;paths['reset_preserves_live_probe_batch']+=1
    assert paths['entry_real_owners']>24 and paths['selective_reset']>=24
    assert all(paths[error]==4 for error in prevalidation), dict(paths)
    assert paths[provider_error]==3
    assert paths['short_hierarchy']==8 and partial>=12
    assert short_poses=={4:4,5:4}
    assert paths['short_pose_root_velocity_cleared']==3 and paths['short_pose_idempotent_prefix']==5
    assert paths['submission_retained_on_early_error']>=8 and paths['real_handplant_submission_before_ground']>64
    assert paths['consumed_real_handplant_candidate']>64 and paths['released_world_grab_full_reset']>64
    assert paths['handplant_ground_consume']>128 and paths['ground_skeleton_capture']>128
    assert paths['selective_grab_cache_invalidation']>16 and paths['queue_capacity_preserves_prefix']==4
    assert paths['actual_wall_query_hit']>64 and paths['actual_deck_query_hit']>16
    assert paths['duplicate_probe_submission_rejected']==paths['missing_probe_batch_rejected']==paths['reset_preserves_live_probe_batch']==4
    assert outcomes[2]>128 and outcomes[1]>16 and outcomes[0]>16
    assert len(variants)>128 and len(roots)>64 and len(candidates)>32 and len(launches)>16 and predictions>32
    assert len(blends)>16 and paths['captured_board_animation_error_changes']>32
    return dict(operations=dict(counts),paths=dict(paths),outcomes=dict(outcomes),short_pose_failures=dict(short_poses),partial_failures=partial,ground_state_variants=len(variants),root_variants=len(roots),candidate_variants=len(candidates),launch_packet_variants=len(launches),future_deck_predictions=predictions,captured_rotation_error_variants=len(blends))

def prepare(assets,output):
    fixtures=output/'fixtures';fixtures.mkdir(exist_ok=True)
    settings=assets/'private/stock/skater-collections.json'
    skeletons=assets/'private/stock/physics-skeletons.json'
    (fixtures/'settings.simulation').write_bytes(converter.encode_settings(settings))
    (fixtures/'physics.simulation').write_bytes(converter.encode_physics_skeletons(skeletons))
    for kind in ('action','motion'):
        (fixtures/f'actor.{kind}.reference').write_bytes(original_graph(element('state','idle')))
    (fixtures/'fixture-provenance.json').write_text(json.dumps(dict(
        settings_original_sha256=digest(settings),settings_simulation_sha256=digest(fixtures/'settings.simulation'),
        physics_original_sha256=digest(skeletons),physics_simulation_sha256=digest(fixtures/'physics.simulation'),
        graphs={kind:digest(fixtures/f'actor.{kind}.reference')for kind in ('action','motion')},
        boundary='Stock settings/physics are independently loaded by the original; only converted project data enters C++. Caller-authored engine triangles and exact query metadata (surfaces/mesh ranges/bounds/groups/pools), plus rail source records, are transported independently from converted rail primitives/metadata.'),indent=2)+'\n')
    return fixtures,json.loads(skeletons.read_text())['source_sha256']

def preflight(raw,cases):
    assert len(raw)%4==0
    words=struct.unpack('<'+'I'*(len(raw)//4),raw);at=1;ranges=[];definitions=schema()
    assert words[0]==len(cases)
    lengths=(103,2,2,1,1,1,1,1,1,8,
        2+ground.value_words('PhysicsGroundState',definitions)+ground.value_words('PumpingState',definitions),
        13,3,None,None,3,1,1,1,1,1,1,1,1)
    for case in cases:
        start=at*4;triangles=words[at];at+=1+18*triangles
        assert words[at]==triangles;at+=1+triangles;meshes=words[at];at+=1+12*meshes;assert words[at]==3;at+=1
        provider=grind.Stream();grind.encode_provider(provider,case['provider']);assert raw[at*4:at*4+len(provider.data)]==bytes(provider.data);at+=len(provider.data)//4
        assert words[at]==len(case['commands']);at+=1
        for cmd in case['commands']:
            expected=lengths[cmd[0]]
            if cmd[0]==13:expected=13 if cmd[1]else 2
            if cmd[0]==14:expected=2+ground.value_words('GroundLaunchInfo',definitions)if cmd[1]else 2
            assert len(cmd)==expected,(case['index'],cmd[0],len(cmd),expected)
            assert list(words[at:at+len(cmd)])==cmd;at+=len(cmd)
        ranges.append((start,at*4))
    assert at==len(words)
    assert b''.join(raw[start:end]for start,end in ranges)==raw[4:]
    for unit in UNITS:assert(CODE/(unit+'.cpp')).is_file(),unit
    transport_helpers()
    for path,boundary in (
        ('Tests/Reference/handplant_observer.rs','pub(super) fn run('),
        ('Tests/Reference/handplant_lifecycle_observer.rs','pub(super) fn run('),
        ('Tests/Reference/air_reckoning_observer.rs','fn core_input('),
        ('Tests/Reference/footplant_observer.rs','pub(super) fn run('),
        ('Tests/Simulation/handplant_lifecycle_probe.cpp','int main('),
        ('Tests/Simulation/footplant_probe.cpp','KnownAirFootplantInput Packet(')):
        extract(PLUGIN/path,boundary)
    return ranges

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('assets','samples','output','target-dir'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--preflight',action='store_true')
    parser.add_argument('--reference-case-runner',action='store_true')
    parser.add_argument('--reference-workers',type=int,choices=(1,2,3,4),default=1)
    args=parser.parse_args()
    if not args.reference_case_runner and args.reference_workers!=1:parser.error('--reference-workers requires --reference-case-runner')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    inputs,cases=corpus();ranges=preflight(inputs,cases)
    (output/'input.bin').write_bytes(inputs);(output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    fixtures,identity=prepare(args.assets.resolve(),output)
    if args.preflight:
        build_reference(output/'reference',args.target_dir,compile=False);build_simulation(output,compile=False)
        print(json.dumps(dict(cases=len(cases),commands=sum(len(case['commands'])for case in cases),input_bytes=len(inputs),units=len(UNITS),input_sha256=hashlib.sha256(inputs).hexdigest()),indent=2));return
    reference=build_reference(output/'reference',args.target_dir);simulation=build_simulation(output)
    if args.reference_case_runner:
        from reference_case_runner import run_reference_cases
        expected=run_reference_cases(reference,[args.assets.resolve(),fixtures],inputs,ranges,
            output/'reference-cases',workers=args.reference_workers,
            validate_output=lambda index,raw:decode(raw,[copy.deepcopy(cases[index])]))
    else:expected=subprocess.check_output([str(reference),str(args.assets.resolve()),str(fixtures)],input=inputs)
    actual=subprocess.check_output([str(simulation),str(fixtures/'settings.simulation'),str(fixtures/'physics.simulation'),str(args.samples.resolve()/'simulation/rig.skate'),identity,str(args.assets.resolve()),str(fixtures)],input=inputs)
    (output/'reference.bin').write_bytes(expected);(output/'simulation.bin').write_bytes(actual);frames=decode(expected,cases)
    if expected!=actual:
        at=next((k for k,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));word=at//4
        case=next((case for case in cases if case['first_output_word']<=word<case['last_output_word']),None)
        row=next((row for rows in frames for row in rows if row['first_word']<=word<row['last_word']),None)
        section=next(((name,word-span[0])for name,span in (row['spans'].items()if row else[])if span[0]<=word<span[1]),None)
        failure=dict(byte=at,reference_bytes=len(expected),simulation_bytes=len(actual),case=case['index']if case else None,operation=row['operation']if row else'initial',section=section,reference_hex=expected[max(0,at-16):at+32].hex(),simulation_hex=actual[max(0,at-16):at+32].hex())
        (output/'first-divergence.json').write_text(json.dumps(failure,indent=2)+'\n');raise AssertionError(failure)
    result=dict(passed=True,reference_revision=REFERENCE_REVISION,cases=len(cases),commands=sum(len(case['commands'])for case in cases),bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),input_sha256=hashlib.sha256(inputs).hexdigest(),coverage=coverage(frames,cases),
        scope='Complete original GroundPhase Enter/Advance/reset_board_state and input_phase::update_ground, with actual Ground retained controllers/settings/services, Handplant GroundQuery/GroundUpdate, real BoardProbes geometry batches, selector Launch/Update, body-force queue, future-deck prediction, source selective cache invalidation, FootIK/AnimatedSkeleton/GeneralUpdate and SkeletonAir capture.',
        boundaries='Caller supplies completed processed fields, source state/category, animation attributes, optional current BoardToolkit, stock authored pose, initial retained state and engine triangle/rail fixtures. The original StaticProvider::new consumes the authored rail source/WMET and C++ independently consumes converted primitives/metadata in exact source order. Each original case performs the complete real GamePhysics/SkaterRuntime constructors. No numerical method, callback, completed hit/trajectory/up or skeleton target is substituted. Global state-selection/input/solve/publication scheduling remains a separate coordinator integration; info logging is unclaimed.')
    if args.reference_case_runner:result['reference_execution']=dict(strategy='exact independent outer cases; unchanged original constructors per case',workers=args.reference_workers,worker_limit_bytes=2*1024**3,report='reference-cases/result.json')
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
