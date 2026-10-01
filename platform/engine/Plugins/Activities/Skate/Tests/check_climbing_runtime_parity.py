#!/usr/bin/env python3
"""Actual optional Climbing retained runtime and original physical/camera prefix.

Only root compiles/runs under the render guard. --preflight stages immutable
original/native sources and corpus without compiling or running either probe.
The actual missing-exchange camera failure is the reachable prefix boundary;
no completed camera/physics snapshot, successful clock tick or resume is seeded.
"""
import argparse
import copy
from collections import Counter,OrderedDict
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import check_air_phase_runtime_parity as air
import check_boneless_runtime_parity as boneless
import check_camera_output_parity as camera
import check_climbing_core_parity as core
import check_climbing_world_parity as ledge
import check_player_input_runtime_parity as player
import check_biped_feet_parity as feet
import check_offboard_air_selector_parity as selector
import check_motion_graph_continuation_parity as continuation
import player_input_protocol as wire
from session_parity import digest,REFERENCE_REVISION
PLUGIN=air.PLUGIN;CODE=air.CODE
UNITS=tuple(dict.fromkeys((*air.UNITS,*camera.UNITS,*player.UNITS,*selector.UNITS,*continuation.UNITS,'PlayerStateLifecycle','BoardPossessionManager','SimulationClock','ClimbingMath','ClimbingClips','ClimbingContacts','ClimbingLedge','ClimbingRuntime','ClimbingApproach')))

def additional_observers(cpp_prefix,rust_prefix):
    defs,_=wire.declarations();definitions=OrderedDict();existing_cpp=set(re.findall(r'void Observe\([^\n{]*const (\w+)&',cpp_prefix));existing_rust=set(re.findall(r'fn observe_(\w+)\(',rust_prefix))
    def retain(name):
        if name in definitions:return
        for _,kind in defs[name]:
            while wire.array(kind)or wire.option(kind):kind=wire.array(kind)[0]if wire.array(kind)else wire.option(kind)
            if kind in defs:retain(kind)
        definitions[name]=defs[name]
    for name in('PlayerInputState','PhysicalPlayerInput'):retain(name)
    definitions.update({n:fields for n,fields in feet.definitions().items()if n in('BoardManagerHand','BoardPossessionManager')})
    cpp=[];rust=['type BoardManagerHand=skate_core::player::offboard::board_possession::manager::Hand;type BoardPossessionManager=skate_core::player::offboard::board_possession::manager::State;']
    for name,fields in definitions.items():
        if name not in existing_cpp:cpp.append(f'void Observe(AirOutput& o,const {name}& s){{'+''.join(wire.observe_expr(k,'s.'+f,'cpp')for f,k in fields)+'}')
        if name not in existing_rust:rust.append(f'fn observe_{name}(o:&mut Output,s:&{wire.rust_kind(name)}){{'+''.join(wire.observe_expr(k,'s.'+f,'rust')for f,k in fields)+'}')
    # Complete accepted selector observation helpers; only wire/type spelling
    # changes are made. They never implement a numerical selector method.
    cp=(PLUGIN/'Tests/Native/offboard_air_selector_probe.cpp').read_text();cp=cp[cp.index('void VO('):cp.index('void SettingsOut(')]
    cp=cp.replace('Writer&','AirOutput&').replace('.Scalar(','.Float(')
    start=cp.index('void OwnerOut(');cp=cp[:start]+cp[start:].replace('void OwnerOut(AirOutput& o,const OffboardAirSelector& owner,const OffboardAirLaunchPacket& p,const BipedAirTrajectoryResult& r)','void OwnerOut(AirOutput& o,const OffboardAirSelector& owner)',1)
    cp=cp.replace('PacketOut(o,p);ResultOut(o,r);','')
    cpp.append('namespace climb_selector_obs{\n'+cp+'\n}\nvoid SelectorOut(AirOutput& o,const OffboardAirSelector& s){climb_selector_obs::OwnerOut(o,s);}')
    rp=(PLUGIN/'Tests/Reference/offboard_air_selector_probe.rs').read_text();rp=rp[rp.index('fn vo('):rp.index('fn settings_out(')]
    rp=rp.replace('Writer','Output').replace('.scalar(','.float(').replace('o.words','o.0').replace('fn owner_out(o:&mut Output,owner:&offboard::air_selector::AirSelector,p:air_launch::Packet,r:TrajectoryResult)','pub(super)fn owner_out(o:&mut Output,owner:&super::super::offboard::air_selector::AirSelector)').replace('offboard::air_selector::migration_completions(owner)','super::super::offboard::air_selector::migration_climbing_completions(owner)').replace('packet_out(o,p);result_out(o,r);','')
    rp='mod selector_obs{use crate::Output;use skate_core::{air::trajectory::{Trajectory,QueryResult,QueryRequest,Prediction},player::offboard::{air_launch,biped_air::recovered::{TrajectoryResult,sampling::SelectorState,selection::Candidate}}};\n'+rp+'\n}'
    return '\n'.join(cpp),'\n'.join(rust),rp

def world_input():
    cpp=(PLUGIN/'Tests/Native/world_geometry_probe.cpp').read_text();cpp=cpp[cpp.index('struct TriangleInput'):cpp.index('struct Query {')]
    cpp='namespace climb_world_wire{\nstruct Reader{AirInput& i;std::uint32_t Word(){return i.Word();}float Scalar(){return i.Float();}Vec3 Vector(){return i.Vector();}Bounds Box(){return {Vector(),Vector()};}AffineTransform Transform(){AffineTransform t;for(auto& c:t.basis.columns)for(auto& v:c)v=Scalar();t.translation=Vector();return t;}};\n'+cpp+'\n}\nWorldGeometry ReadClimbWorld(AirInput& i){climb_world_wire::Reader r{i};std::vector<WorldTriangle> triangles;const auto n=r.Word();for(unsigned k=0;k<n;++k)triangles.push_back(climb_world_wire::Cached(climb_world_wire::ReadTriangle(r)));const bool enabled=r.Word()!=0;auto metadata=climb_world_wire::Metadata(r);const char* error=nullptr;if(!enabled)return WorldGeometry(std::move(triangles));auto world=WorldGeometry::WithQueryMetadata(std::move(triangles),std::move(metadata),error);if(!world)Fail(error);return std::move(*world);}'
    rust=(PLUGIN/'Tests/Reference/world_geometry_probe.rs').read_text();rust=rust[rust.index('struct TriangleInput'):rust.index('struct Query {')]
    rust=rust.replace('Reader','Input').replace('reader.scalar()','reader.float()').replace('reader.vector()','vector(reader)').replace('reader.transform()','transform(reader)').replace('reader.bounds()','bounds(reader)')
    rust='mod climb_world_wire{use crate::Input;use skate_core::{math::Vector3,physics::{board_world::{BoardWorld,WorldTriangle,query_metadata::{Bounds,QueryMetadata,QueryMesh,QueryPool,EdgeSegment}},contact::RetailContactMaterial,drive_frames::RetailAffineTransform,world_contact::triangle_from_volume}};fn vector(i:&mut Input)->Vector3{Vector3::new(i.float(),i.float(),i.float())}fn bounds(i:&mut Input)->Bounds{Bounds{min:vector(i),max:vector(i)}}fn transform(i:&mut Input)->RetailAffineTransform{RetailAffineTransform{basis:skate_core::math::Basis3{columns:std::array::from_fn(|_|std::array::from_fn(|_|i.float()))},translation:vector(i)}}\n'+rust+'\npub(super)fn read(i:&mut Input)->BoardWorld{let n=i.word();let triangles=(0..n).map(|_|cached(triangle(i))).collect();let enabled=i.word()!=0;let meta=metadata(i);if enabled{BoardWorld::with_query_metadata(triangles,meta).unwrap()}else{BoardWorld::new(triangles)}}\n}'
    return cpp,rust

def riding_observers():
    native=(PLUGIN/'Tests/Native/physical_simulation_runtime_probe.cpp').read_text()
    body=native[native.index('void OutGround('):native.index('void OutBatch(')].replace('void OutGround(const PhysicalRidingOutputs& r)','void RidingOut(AirOutput& o,const PhysicalRidingOutputs& r)')
    body=re.sub(r'\bOut\(', 'Out(o,',body)
    native='namespace climb_riding_obs{\nvoid Out(AirOutput& o,float v){o.Float(v);}void Out(AirOutput& o,std::uint32_t v){o.Word(v);}void Out(AirOutput& o,Vec3 v){o.Float(v.x);o.Float(v.y);o.Float(v.z);}void Out(AirOutput& o,Basis3 v){for(auto c:v.columns)for(auto x:c)o.Float(x);}template<class T,std::size_t N>void Out(AirOutput& o,const std::array<T,N>& v){for(const auto& x:v)Out(o,x);}\n'+body+r'''
void PendingOut(AirOutput& o,const PhysicalRidingOutputs& r){
 const auto vector=[&](Vec3 v){o.Float(v.x);o.Float(v.y);o.Float(v.z);};const auto hit=[&](const std::optional<BoardProbeHit>& h){o.Word(bool(h));if(h){vector(h->point);vector(h->normal);o.Word(h->surface_tag);}};
 o.Word(bool(r.pending_wheel_queries));if(r.pending_wheel_queries)for(const auto& h:*r.pending_wheel_queries){o.Word(bool(h));if(h){o.Float(h->fraction);vector(h->normal);o.Word(h->surface_tag);}}
 o.Word(bool(r.probes.wall_line));if(r.probes.wall_line){vector(r.probes.wall_line->start);vector(r.probes.wall_line->end);}
 o.Word(bool(r.probes.pending));if(r.probes.pending){hit(r.probes.pending->deck);o.Word(bool(r.probes.pending->wall));if(r.probes.pending->wall)hit(*r.probes.pending->wall);}
}
} // namespace climb_riding_obs
'''
    original=(PLUGIN/'Tests/Reference/physical_simulation_runtime_probe.rs').read_text()
    body=original[original.index('fn riding_out('):original.index('fn batch_out(')]
    body=body.replace('fn riding_out(out:&mut Vec<u32>,r:&physics::riding_outputs::RidingOutputs)','pub(crate)fn migration_climber_observe(out:&mut crate::Output,r:&RidingOutputs)').replace('probe_vector(out,','vector(out,').replace('probe_floats(out,','floats(out,').replace('probe_matrix(out,','matrix(out,').replace('probe_basis(out,','basis(out,').replace('out.push(', 'out.word(').replace('out.extend(', 'out.0.extend(')
    pos=body.rindex('}')
    body=body[:pos]+r'''
 out.word(r.pending_wheel_queries.is_some()as u32);if let Some(values)=r.pending_wheel_queries{for h in values{out.word(h.is_some()as u32);if let Some(h)=h{out.float(h.fraction);vector(out,h.normal);out.word(h.surface_tag);}}}
 r.probes.migration_climber_observe(out);
'''+body[pos:]
    rust='\nfn vector(o:&mut crate::Output,v:Vector3){o.floats([v.x,v.y,v.z])}fn floats<const N:usize>(o:&mut crate::Output,v:[f32;N]){o.floats(v)}fn matrix(o:&mut crate::Output,m:[[f32;4];4]){o.matrix(m)}fn basis(o:&mut crate::Output,m:skate_core::math::Basis3){for c in m.columns{o.floats(c)}}\n'+body
    probes=r'''
impl BoardProbes{pub(super)fn migration_climber_observe(&self,o:&mut crate::Output){
 let vector=|o:&mut crate::Output,v:Vector3|o.floats([v.x,v.y,v.z]);let hit=|o:&mut crate::Output,h:Option<BoardProbeHit>|{o.word(h.is_some()as u32);if let Some(h)=h{vector(o,h.point);vector(o,h.normal);o.word(h.surface_tag)}};
 o.word(self.wall_line.is_some()as u32);if let Some(line)=self.wall_line{vector(o,line.start);vector(o,line.end)}o.word(self.pending.is_some()as u32);if let Some(p)=&self.pending{hit(o,p.deck);o.word(p.wall.is_some()as u32);if let Some(h)=p.wall{hit(o,h)}}
}}
'''
    return native,rust,probes

def prepare(output):
    original,observed,snapshot,report=air.prepare(output);crate=observed/'atelier-host'
    native=(snapshot/'air_phase_runtime_probe.cpp').read_text();prefix=native[:native.index('int main(')]
    observer=(PLUGIN/'Tests/Reference/air_phase_runtime_observer.rs').read_text();rp=observer[:observer.index('pub(super)fn load(')].replace('mod migration_air {','mod migration_climbing {')
    cpp,rust,selector_rust=additional_observers(prefix,(crate/'src/migration_probe.rs').read_text());cw,rw=world_input();riding_cpp,riding_rust,probes_rust=riding_observers()
    cp=(PLUGIN/'Tests/Native/climbing_runtime_probe.cpp').read_text().replace('// GENERATED_COMPLETE_OWNER_HELPERS',prefix).replace('// GENERATED_ADDITIONAL_OBSERVERS',cpp).replace('// GENERATED_WORLD_INPUT',cw).replace('// GENERATED_RIDING_OBSERVERS',riding_cpp);(snapshot/'climbing_runtime_probe.cpp').write_text(cp)
    construction=observer[observer.index(' let graphs='):observer.index('snapshot(o,&p,&s,&last);')].replace('p.world=crate::fixture_world(i.word())','p.world=crate::climb_world_wire::read(i)')
    run=(PLUGIN/'Tests/Reference/climbing_runtime_probe.rs').read_text().replace('// GENERATED_COMPLETE_OWNER_OBSERVATIONS',rp+'\n'+selector_rust).replace('// GENERATED_COMPLETE_OWNER_CONSTRUCTION',construction)
    additions={'physics.rs':run,'physics/riding_outputs.rs':riding_rust,'physics/riding_outputs/probes.rs':probes_rust,'physics/climbing/mod.rs':(PLUGIN/'Tests/Reference/climbing_runtime_observer.rs').read_text(),'physics/climbing/approach.rs':'\npub(super)fn migration_climber_observe(o:&mut crate::Output,a:&Approach){super::migration_ledge(o,a.ledge);o.float(a.weight);}\n','physics/clock.rs':'\nimpl SimulationClock{pub(crate)fn migration_climber_ticks(&self)->u32{self.ticks_until_reset}}\n','physics/offboard/air_selector.rs':'\npub(crate)fn migration_climbing_completions(s:&AirSelector)->(&Option<Vec<QueryResult>>,&Option<Prediction>){(&s.completed_launch,&s.completed_requery)}\n'}
    for rel,extra in additions.items():
        p=crate/'src'/rel;p.write_bytes(p.read_bytes()+b'\n'+extra.encode());raw=(original/'crates/skate-host/src'/rel).read_bytes();assert p.read_bytes()[:len(raw)]==raw;report['staged_host_original_prefixes'][rel].update(generated_sha256=digest(p),climbing_append_sha256=hashlib.sha256(extra.encode()).hexdigest())
    rel='crates/skate-core/src/physics/centre_of_mass_filter.rs';p=observed/rel;extra='\nimpl CentreOfMassFilter{pub fn migration_climber_words(&self)->[u32;17]{let mut out=[0;17];for (k,v)in[self.velocity,self.position,self.position_velocity,self.accumulated_error].into_iter().flatten().enumerate(){out[k]=v.to_bits()}out[16]=self.position_valid as u32;out}}\n';p.write_bytes(p.read_bytes()+extra.encode());report['appended_core_observers'][rel]=dict(original_prefix_sha256=digest(original/rel),generated_sha256=digest(p),append_sha256=hashlib.sha256(extra.encode()).hexdigest())
    main=crate/'src/migration_probe.rs';s=main.read_text();s=s.replace('physics::migration_air_run','physics::migration_climbing_run');s=s[:s.index('fn main()')]+rust+'\n'+rw+'\n'+s[s.index('fn main()'):];main.write_text(s)
    cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text().replace('name="air-phase-runtime-reference"','name="climbing-runtime-reference"'))
    for u in UNITS:shutil.copy2(CODE/(u+'.cpp'),snapshot/(u+'.cpp'))
    report.update(units=UNITS,climbing_owned_sources={p.name:digest(p)for p in [CODE/'ClimbingRuntime.h',CODE/'ClimbingRuntime.cpp',CODE/'ClimbingApproach.cpp']},read_only_helper_sources={p.name:digest(p)for p in [PLUGIN/'Tests/Native/physical_simulation_runtime_probe.cpp',PLUGIN/'Tests/Reference/physical_simulation_runtime_probe.rs',PLUGIN/'Tests/Native/offboard_air_selector_probe.cpp',PLUGIN/'Tests/Reference/offboard_air_selector_probe.rs',PLUGIN/'Tests/Native/world_geometry_probe.cpp',PLUGIN/'Tests/Reference/world_geometry_probe.rs',PLUGIN/'Tests/check_biped_feet_parity.py']},immutable_native_sources={p.name:digest(p)for p in sorted(snapshot.glob('*.h'))+sorted(snapshot.glob('*.cpp'))},generated_native_probe_sha256=digest(snapshot/'climbing_runtime_probe.cpp'),generated_reference_probe_sha256=digest(main),proof_files={p.name:digest(p)for p in [Path(__file__),PLUGIN/'Tests/Native/climbing_runtime_probe.cpp',PLUGIN/'Tests/Reference/climbing_runtime_probe.rs',PLUGIN/'Tests/Reference/climbing_runtime_observer.rs']},scope='Entire unchanged optional Climbing mod/approach/ledge/contacts/clip and canonical stock constructors, physical board/wheel/contact/riding, animated pose/body/target/input/COM/IK owners execute. Only upstream controller/selected-state/retained attachment fixtures and raw authored world are supplied. Every attachment uses a real original ledge query. Actual camera-output missing-exchange failure bounds the executed prefix; finish_clock/resume are asserted unreachable, not supplied completed observations.')
    (output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');return original,observed,snapshot,report

def control(pressed=False,held=False,n=0):
    words=[0]*26;words[6]=(1<<23)if held else 0;words[13]=(1<<23)if pressed else 0
    words[9:11]=core.floats([.137*(n%7-3),-.0731*(n%11-5)])
    return [32,*words]
def selected(state=500,velocity=(.137,0,.731,0),flags=0,direction=(0,0,1,0)):
    return [30,state,*core.floats(velocity),flags,int(direction is not None),*core.floats(direction or (0,0,0,0))]
def attachment(phase,carry,time=0,feet_point=(0,0,0),facing=(0,0,1)):
    return [31,phase,int(carry),core.bits(time),*core.floats((*feet_point,*facing))]
def hang_pose(feet_point=(0,0,0),facing=(0,0,1)):return [41,*core.floats((*feet_point,*facing))]
def load_command(index,names=()):
    words=[40,index,len(names)]
    for name in names:
        encoded=name.encode();words += [len(encoded),*encoded]
    return words

def runtime_loaders():
    good=clip_package();rows=[dict(label='optional absent package',data=None),dict(label='stock real rig remap',data=good)]
    for label,mutate in [('version before clips',lambda d:d.update(version=2)),('missing reach',lambda d:d['clips'].pop(0)),('missing mantle',lambda d:d['clips'].pop(1)),('invalid unused clip before selecting',lambda d:d['clips'].append(dict(core.clip('unused'),fps=0)))]:
        value=copy.deepcopy(good);mutate(value);rows.append(dict(label=label,data=value))
    return rows

def corpus():
    cases=[];records=[];empty=dict(rails=[],segments=[],guids=[],assets=[],manifest={})
    s=air.provider.Stream();air.provider.encode_provider(s,empty);provider=list(struct.unpack('<'+'I'*(len(s.data)//4),s.data))
    def add(commands,label,height=2,slope=0,obstacle=0):
        entries=ledge.block(height=height,slope=slope,obstacle=obstacle)
        entries+=ledge.quad([-20,-.035,-20],[-20,-.035,20],[20,-.035,-20],[20,-.035,20],500)
        transport=ledge.transport(entries,ledge.metadata(entries))
        case=dict(index=len(cases),label=label,world=transport,provider=provider,commands=commands)
        records.append([*transport,*provider,len(commands),*[w for cmd in commands for w in cmd]]);cases.append(case)
    # Direct retained attachments use an actual independent ledge query, while
    # every update invokes the full original physical/pose/camera path.
    for n in range(12):
        carry=n%2;commands=[boneless.packet(n),selected(),[34],control(n=n),attachment(0,carry)]
        for k in range(40):commands += [control(n=n+k),[33]]
        # Holding X is distinct from its rising edge; the latter enters mantle.
        commands += [control(pressed=True,held=True,n=n),[33],control(pressed=True,n=n),[33]]
        for k in range(30):commands += [control(n=n+k+40),[33]]
        for phase in(1,2,3):
            commands += [attachment(phase,carry,(0,.0731,.137,.25)[(n+phase)%4]),[33],[33]]
        commands += [[44,0xffffffff,0xffffffff,0xffffffff],hang_pose(),[33]]
        # Missing active returns false and decrements the retained cooldown.
        commands += [[37,core.bits(.0371)],[33],[33],[33]]
        # Actual pending teleport overrides both owners before cooldown math.
        commands += [attachment(0,carry),[38,*core.floats(core.matrix((.137,.731,-.317),.137))],[33],[33]]
        add(commands,'all retained phases, genuine camera failure prefix, carry '+str(carry),height=(1.6,2,2.6)[n%3],slope=(-.0137,0,.0137)[n%3])
    for n in range(4):
        commands=[boneless.packet(n),selected(),[34],attachment(0,False),[33]]
        for y in(-.075,-.035,0,.0317,.137,.317):
            commands += [[36,*core.floats(core.matrix((.137*n,y,.317*n),.0317*n))],[33],[33]]
        # Source validates actual wheel-query endpoints. Board state and clear
        # force writes preceding that failure remain observable, then recover.
        for bad in(float('nan'),float('inf')):
            commands += [[36,*core.floats(core.matrix((bad,-.035,0)))],[33],
                         [36,*core.floats(core.matrix((0,-.035,0)))],[33]]
        for size in(0,1):
            commands += [[35,*core.floats(core.matrix((.137,.731,-.317),.137)),size],[33]]
        add(commands,'live dropped board contacts and ordered genuine wheel/pose failures '+str(n))
    # Approach starts from a complete authored hang pose published through the
    # actual MapAnimationParts/physical/COM owner. It must catch from real world
    # probes, reset the sole selector/State56/IK and preserve ground return pose.
    for n in range(8):
        commands=[boneless.packet(n),hang_pose(),selected(500,velocity=(0,0,0,0)),[34],
                  [42,n%2],[43,0x12340000+n],selected(501,velocity=(0,0,.731,0))]
        commands += [[34]for _ in range(48)]
        commands += [control(n=n),[33],control(pressed=True,n=n),[33]]
        commands += [[33]for _ in range(32)]
        # Other physical state and backwards/absent/weak direction reject the
        # overlay without installing an invented attachment.
        commands += [[37,0],selected(100),[34],selected(500,direction=None),[34],
                     selected(500,flags=4,direction=(.137,0,.0731,0)),[34],
                     selected(501,velocity=(0,0,-.731,0),direction=(0,0,-1,0))]
        commands += [[34]for _ in range(40)]
        commands += [[37,core.bits(.3)],selected(501),[34],[39],[34]]
        add(commands,'real airborne catch, sole selector/feet/IK reset and overlay rejection '+str(n),height=(1.6,2,2.6)[n%3])
    commands=[attachment(1,True,.137)]
    for index in range(len(runtime_loaders())):
        commands += [load_command(1),attachment(1,True,.137),load_command(index)]
    for pos in range(13):
        names=list(core.NAMES[:13]);names[pos]='missing_'+str(pos)
        commands += [load_command(1),attachment(1,True,.137),load_command(1,names)]
    commands += [load_command(1,[n.lower()for n in core.NAMES[:13]]),load_command(1,['hIpS',*core.NAMES[:13]]),load_command(1),load_command(0)]
    add(commands,'whole Runtime load/rig-remap/ordered validation and retained owner on failure')
    raw=core.word(len(records))+b''.join(core.word(w)for row in records for w in row)
    return raw,cases

def preflight(raw,cases):
    r=air.Reader(raw);assert r.word()==len(cases);ranges=[]
    for c in cases:
        start=r.at;assert list(r.take(len(c['world'])))==c['world'];assert list(r.take(len(c['provider'])))==c['provider'];assert r.word()==len(c['commands'])
        for cmd in c['commands']:assert list(r.take(len(cmd)))==cmd
        ranges.append([start*4,r.at*4])
    assert r.at==len(r.words)
    for unit in UNITS:assert(CODE/(unit+'.cpp')).is_file(),unit
    return ranges

class Reader(air.Reader):
    def climbing(self):
        values={};spans={}
        for name in('climber','player_records','render_com_clock','feet','offboard_selector','riding_board'):
            n=self.word();at=self.at;values[name]=self.take(n);spans[name]=[at,self.at]
        phases,ps=self.phases();f=self.foot();fs=self.foot_spans.copy();shared=self.snapshot();spans.update(ps);spans.update(fs);spans.update(self.spans)
        return dict(**values,phase=phases,foot=f,shared=shared,spans=spans)

def decode(raw,cases):
    r=Reader(raw);assert r.word()==len(cases);frames=[]
    for case in cases:
        case['first_output_word']=r.at;assert r.word()==len(case['commands']);prior=r.climbing();case['initial_spans']=prior['spans'];rows=[]
        for command in case['commands']:
            at=r.at;assert r.word()==command[0];error=r.status();present=r.word();handled=r.word()if present else None
            row=dict(operation=command[0],error=error,handled=handled,first_word=at,**r.climbing(),prior=prior);row['last_word']=r.at;rows.append(row);prior=row
        case['last_output_word']=r.at;frames.append(rows)
    assert r.at==len(r.words),(r.at,len(r.words));return frames

def climber(raw):
    r=air.Reader(struct.pack('<'+'I'*len(raw),*raw));clips=r.word();indices=list(r.take(r.word()));cooldown=r.word();active=None;approach=None
    if r.word():
        phase=r.word();time=r.word();l=list(r.take(21));root=list(r.take(10));entry=list(r.take(10*r.word()));fallback=list(r.take(16*r.word()));boards=list(r.take(32));carry=r.word()
        active=dict(phase=phase,time=time,ledge=l,start_root=root,entry=entry,fallback=fallback,boards=boards,carry=carry)
    if r.word():approach=dict(ledge=list(r.take(21)),weight=r.word())
    ground=list(r.take(10*r.word()));assert r.at==len(r.words)
    return dict(clips=clips,indices=indices,cooldown=cooldown,active=active,approach=approach,ground_entry=ground)

def publication(raw):
    r=air.Reader(struct.pack('<'+'I'*len(raw),*raw));pose=list(r.take(16*r.word()));generation=r.word()|(r.word()<<32);state=r.word();controller=r.word();com=list(r.take(17));output=list(r.take(12));look=list(r.take(2));clock=list(r.take(3));camera_state=list(r.take(3));assert r.at==len(r.words)
    return dict(pose=pose,generation=generation,state=state,controller=controller,com=com,output=output,look=look,clock=clock,camera=camera_state)

def coverage(frames,cases):
    operations=Counter();errors=Counter();phases=set();carry=set();ledges=set();poses=set();roots=set();com=set();weights=set();camera_prefix=partial_pose=partial_board=live_contacts=wrapped=catch=settle_retained=0;cooldown=0;false=0;selectors_reset=feet_reset=0
    for rows,case in zip(frames,cases):
        for row,cmd in zip(rows,case['commands']):
            op=cmd[0];operations[op]+=1;now=climber(row['climber']);old=climber(row['prior']['climber']);p=publication(row['render_com_clock']);before=publication(row['prior']['render_com_clock'])
            assert p['camera']==[0,0,0]and p['clock']==before['clock'],'missing completed exchange must precede camera mutation and clock/resume'
            assert row['phase']['forces'][-3:-1]==row['prior']['phase']['forces'][-3:-1],'physical tick must not advance before successful camera output'
            poses.add(tuple(p['pose']));roots.add(tuple(row['shared']['roots']));com.add(tuple(p['com']))
            if now['active']:
                a=now['active'];phases.add(a['phase']);carry.add(a['carry']);ledges.add(tuple(a['ledge']))
            if now['approach']:weights.add(now['approach']['weight'])
            if row['error']:
                errors[row['error']]+=1;assert row['handled']is None
                partial_pose+=p['generation']!=before['generation'];partial_board+=row['shared']['bodies_blend']!=row['prior']['shared']['bodies_blend']
            if op==33:
                if row['error']=='Camera requires the completed physical output snapshot':
                    camera_prefix+=1;assert p['generation']==(before['generation']+1)&0xffffffffffffffff
                    assert row['player_records'][9]==(row['prior']['player_records'][9]+1)&0xffffffff,'same actual pose publication wraps canonical PlayerInput count'
                    assert now['active']is not None and old['active']is not None
                    if now['active']['phase']==3 and core_value(now['active']['time'])>=.25:settle_retained+=1
                    if not now['active']['carry']:
                        # Force block ends contact/network counts,tick64,failed.
                        live_contacts+=bool(row['phase']['forces'][-5])
                elif row['error']is None:
                    false+=row['handled']==0
                if old['cooldown']!=now['cooldown']:cooldown+=1
            if op==34 and old['active']is None and now['active']is not None:
                catch+=1;assert now['active']['phase']==0 and now['active']['time']==0
                assert now['approach']is None and now['ground_entry']
                assert row['shared']['ik'][0]==0,'actual catch disables the canonical FootIK feet'
                selectors_reset+=row['offboard_selector']!=row['prior']['offboard_selector']
                feet_reset+=row['feet']!=row['prior']['feet']
            if op in(33,41)and p['generation']==0 and before['generation']==0xffffffffffffffff:wrapped+=1
            if op==40 and row['error']:assert row['climber']==row['prior']['climber'],'failed actual Runtime loader preserves prior retained owner'
            if op==35 and row['error']:
                assert row['render_com_clock']==row['prior']['render_com_clock'],'MapAnimationParts fails before publication writes'
            if op==38:assert row['error']is None
    assert sum(n for e,n in errors.items()if e.startswith('Climbing rig bone '))==13
    assert phases=={0,1,2,3}and carry=={0,1}and len(ledges)>3
    assert camera_prefix>300 and partial_pose>300 and partial_board>100 and live_contacts>8
    assert catch>=4 and feet_reset>=4,'real source Approach must catch and reset the sole retained State56 owner'
    assert settle_retained>30 and false>24 and cooldown>24 and wrapped>=12
    assert len(poses)>100 and len(roots)>100 and len(com)>100 and len(weights)>32
    assert any('finite'in e.lower()for e in errors)and any('pose'in e.lower()or'bone'in e.lower()for e in errors)
    return dict(operations=dict(operations),errors=dict(errors),phases=sorted(phases),carry_modes=sorted(carry),real_ledges=len(ledges),camera_failure_after_complete_pose=camera_prefix,partial_pose_writes=partial_pose,partial_board_writes=partial_board,live_dropped_contact_rows=live_contacts,actual_approach_catches=catch,retained_feet_resets=feet_reset,changed_selector_resets=selectors_reset,complete_settle_retained_after_camera_error=settle_retained,false_handled_rows=false,changed_cooldowns=cooldown,wrapping_generation_rows=wrapped,distinct_render_poses=len(poses),distinct_roots=len(roots),distinct_com_histories=len(com),approach_weights=len(weights),camera_clock_resume_tail_reached=False)

def core_value(word):return struct.unpack('<f',struct.pack('<I',word))[0]

def clip_package():
    clips=[core.clip('reach'),core.clip('mantle',1)]
    for c in clips:
        c['names']=c['names'][:13];c['parents']=c['parents'][:13];c['frames']=[f[:13]for f in c['frames']]
    return dict(version=1,clips=clips)

def build(output,target):
    original,observed,snapshot,report=prepare(output);crate=observed/'atelier-host'
    subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(crate/'Cargo.toml'),'--target-dir',str(target.resolve()),'--bin','climbing-runtime-reference'],check=True)
    reference=output/'climbing-runtime-reference';shutil.copy2(target.resolve()/'release/climbing-runtime-reference',reference);native=output/'climbing-runtime-native'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'climbing_runtime_probe.cpp'),'-o',str(native)],check=True)
    for rel,sha in report['original_source_sha256'].items():
        assert digest(original/rel)==sha;raw=(original/rel).read_bytes();assert(observed/rel).read_bytes()[:len(raw)]==raw
    for rel,row in report['staged_host_original_prefixes'].items():assert digest(crate/'src'/rel)==row['generated_sha256'],rel
    for name,sha in report['immutable_native_sources'].items():assert digest(snapshot/name)==sha,name
    report.update(reference_binary_sha256=digest(reference),native_binary_sha256=digest(native));(output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');return native,reference

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in('assets','samples','metadata','output','target-dir'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    for name in('result.json','first-divergence.json'):(out/name).unlink(missing_ok=True)
    raw,cases=corpus();ranges=preflight(raw,cases);(out/'input.bin').write_bytes(raw);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');clips=clip_package();(out/'climbing-clips.json').write_text(json.dumps(clips)+'\n');(out/'climbing.native').write_bytes(core.native(clips));(out/'runtime-loader-fixtures.json').write_text(json.dumps(runtime_loaders(),indent=2)+'\n')
    if a.preflight:
        prepare(out);print(json.dumps(dict(preflight='PASS',histories=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(raw),input_sha256=hashlib.sha256(raw).hexdigest(),units=len(UNITS),native_clips_sha256=digest(out/'climbing.native')),indent=2));return
    data_probe=camera.camera_reference.build_data_probe(out/'data',a.target_dir);base=out/'stock-camera'
    subprocess.run([str(data_probe),str(a.assets.resolve()),str(base),'climbing-stock:'+digest(a.assets/camera.camera.COLLECTION)],check=True)
    spec=importlib.util.spec_from_file_location('climbing_camera_conversion',PLUGIN/'Tools/convert_camera_data.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);package=module.pack_camera(json.loads(base.with_suffix('.json').read_text()));assert package==base.with_suffix('.raw').read_bytes()
    bank=camera.fixtures(a.assets.resolve(),out,package)
    for index,fixture in enumerate(runtime_loaders()):
        folder=bank/'climbing-loaders'/str(index);folder.mkdir(parents=True,exist_ok=True)
        if fixture['data']:
            path=folder/'private/custom/climbing.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(fixture['data'])+'\n');(folder/'climbing.native').write_bytes(core.native(fixture['data']))
    clip_path=bank/'private/custom/climbing.json';clip_path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(out/'climbing-clips.json',clip_path);shutil.copy2(out/'climbing.native',bank/'climbing.native')
    identity=json.loads((a.assets.resolve()/'private/stock/physics-skeletons.json').read_text())['source_sha256'];native,reference=build(out,a.target_dir)
    args=[str(bank/'settings.native'),str(bank/'physics.native'),str(a.samples.resolve()/'native/rig.skate'),identity,str(a.assets.resolve()),str(bank),str(a.metadata.resolve())]
    expected=subprocess.check_output([str(reference),str(a.assets.resolve()),str(bank)],input=raw);actual=subprocess.check_output([str(native),*args],input=raw);(out/'reference.bin').write_bytes(expected);(out/'native.bin').write_bytes(actual)
    frames=decode(expected,cases)
    if expected!=actual:
        at=next((k for k,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));word=at//4;case=next((c for c in cases if c['first_output_word']<=word<c['last_output_word']),None);row=next((r for rows in frames for r in rows if r['first_word']<=word<r['last_word']),None);section=next(((n,word-span[0])for n,span in(row['spans'].items()if row else[])if span[0]<=word<span[1]),None)
        failure=dict(byte=at,word=word,reference_bytes=len(expected),native_bytes=len(actual),case=case['index']if case else None,operation=row['operation']if row else'initial',section=section,reference_hex=expected[max(0,at-16):at+32].hex(),native_hex=actual[max(0,at-16):at+32].hex());(out/'first-divergence.json').write_text(json.dumps(failure,indent=2)+'\n');raise AssertionError(failure)
    proof=coverage(frames,cases);result=dict(passed=True,reference_revision=REFERENCE_REVISION,histories=len(cases),commands=sum(len(c['commands'])for c in cases),exact_bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),input_sha256=hashlib.sha256(raw).hexdigest(),coverage=proof,scope='Whole original retained Climbing/Approach and actual world/board/wheel/contact/riding/pose/target/input/COM/selector/feet/IK constructors and prefix publication.',boundaries='Explicit authored world/custom clip/controller/selected-state/retained attachment inputs; original real ledge queries independently construct every attachment. Actual camera output missing-exchange error occurs before physical tick/clock/resume. Completed camera output, successful global resume and whole frame scheduling remain unexecuted and unproved. No completed camera/physics observations or successful resume are fabricated.')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
