#!/usr/bin/env python3
"""Whole unchanged input_phase::advance over the sole canonical owner set.

Root alone compiles/runs. Incoming animation packet/attributes/actions are
explicit upstream records. Pose, world, contact, board, IK, plant and full reset
remain actual producers; the global frame/transition schedule is separate.
"""
import argparse
from collections import Counter
import copy,hashlib,json,re,shutil,struct,subprocess
from pathlib import Path
import check_player_state_publication_parity as common
import check_player_input_runtime_parity as player
import check_player_teleport_runtime_parity as reset
import player_input_protocol as wire
import check_animation_trees_parity as trees
import check_air_trajectory_runtime_parity as trajectory_proof
from check_animation_playback_parity import Stream
from session_parity import digest,REFERENCE_REVISION
PLUGIN,CODE=common.PLUGIN,common.CODE
UNITS=tuple(dict.fromkeys((*common.UNITS,'PlayerInputHostPhase','PlayerTeleportRuntime')))
OWNED=(PLUGIN/'Tests/Simulation/player_input_host_phase_probe.cpp',PLUGIN/'Tests/Reference/player_input_host_phase_observer.rs',Path(__file__))
PRODUCTION=(CODE/'PlayerInputHostPhase.h',CODE/'PlayerInputHostPhase.cpp')
OPS={**common.OPS,90:'complete_input_host',91:'initial_player',92:'request_teleport',93:'pending_geometry',94:'actual_grind_post',95:'retained_caller_result',96:'missing_reset_output',97:'actual_state61_publication',98:'actual_trajectory_launch',99:'actual_trajectory_update',100:'actual_trajectory_provider',101:'actual_trajectory_world',102:'actual_trajectory_reset',103:'actual_trajectory_poll',104:'actual_trajectory_cancel'}

def readers(cpp,rs):
    defs,_=wire.declarations();selected={}
    def retain(kind):
        if kind.startswith('&'):kind=kind[1:]
        while wire.array(kind)or wire.option(kind):kind=wire.array(kind)[0]if wire.array(kind)else wire.option(kind)
        if kind not in defs or kind in selected:return
        for _,k in defs[kind]:retain(k)
        selected[kind]=defs[kind]
    for name in('AnimationPacketFields','ExternalPhysicsInput','PlayerInputState'):retain(name)
    cp=[];rp=[]
    for name,fields in selected.items():
        if not re.search(r'\b'+name+r'\s+Read'+name+r'\(',cpp):
            body=name+' Read'+name+'(BipedInput& i){'+name+' s;'+''.join('s.'+f+'='+wire.read_expr(k,'cpp')+';'for f,k in fields)+'return s;}'
            cp.append(body.replace('Input&','BipedInput&').replace('BipedBipedInput&','BipedInput&'))
        if not re.search(r'\bfn\s+read_'+name+r'\(',rs):
            rp.append('fn read_'+name+'(i:&mut Input)->'+name+'{'+name+'{'+''.join(f+':'+wire.read_expr(k,'rust')+','for f,k in fields)+'}}')
    fields=[(f,k)for f,k in defs['AnimationInputPacket']if not k.startswith('&')]
    cp.append('AnimationInputPacket ReadPacket(BipedInput& i,const AnimationPacketFields& publication,const ExternalPhysicsInput& external){AnimationInputPacket s{publication,external};'+''.join('s.'+f+'='+wire.read_expr(k,'cpp')+';'for f,k in fields)+'return s;}')
    rp.append("fn read_packet<'a>(i:&mut Input,publication:&'a AnimationPacketFields,external:&'a ExternalPhysicsInput)->AnimationInputPacket<'a>{AnimationInputPacket{publication,external_physics_10512:external,"+''.join(f+':'+wire.read_expr(k,'rust')+','for f,k in fields)+'}}')
    return '\n'.join(cp),'type AnimationPacketFields=skate_core::input::animation_packet::AnimationPacketFields;\n'+'\n'.join(rp)

def observers():
    grind=common.grind.input_grind;defs,state=grind.declarations();canonical,_=wire.declarations()
    cp=[]
    for name in defs:cp.append('using '+name+'='+grind.ALIASES[name]+';void HostObserve(BipedOutput&,const '+name+'&);')
    cp.append('void HostObserve(BipedOutput&,const GrindInvestigationFields&);')
    for name,fields in dict(defs,GrindInvestigationFields=canonical['GrindInvestigationFields']).items():
        body=''.join(wire.observe_expr(k,'s.'+f,'cpp')if not(name=='GrindSurface'and f=='kind')else'o.Word(std::uint32_t(s.kind));'for f,k in fields)
        cp.append('void HostObserve(BipedOutput& o,const '+name+'& s){'+body.replace('Observe(','HostObserve(')+'}')
    cp.append('void HostObserveState(BipedOutput& o,const PlayerGrindInputState& s){'+''.join(wire.observe_expr(k,'s.'+f,'cpp')for f,k in state).replace('Observe(','HostObserve(')+'}')
    raw=(PLUGIN/'Tests/Simulation/player_grind_input_probe.cpp').read_text()
    for marker in('void ObservePlan(','void ObservePending('):
        cp.append(common.grind.block(raw,marker).replace('Output&','BipedOutput&').replace('ObservePlan','HostObservePlan').replace('ObservePending','HostObservePending').replace('Observe(','HostObserve('))
    pre=grind.struct_fields(grind.source(grind.HOST+'physics/player_input/pre_input.rs'),'PreInputResult')
    pre=[(f,k.replace('AnimationPartTransform','[[f32;4];4]'))for f,k in pre]
    cp.append('void HostObserve(BipedOutput& o,const PlayerPreInputResult& s){'+''.join(wire.observe_expr(k,'s.'+f,'cpp')for f,k in pre)+'}')
    _,rust,private=grind.helpers(defs,state)
    private=private[:private.index('pub fn seed_state')]+private[private.index('pub fn observe_pending'):]
    private=private.replace('crate::observe_','crate::input_host_protocol::observe_')
    imports=(PLUGIN/'Tests/Reference/player_grind_input_probe.rs').read_text().split('type Input=Reader;',1)[0]
    imports=imports[imports.index('use skate_core::'):].replace('use physics::player_input::grind::{','use crate::physics::migration_input_host_grind::{')
    functions=[common.grind.block(rust,'fn observe_'+name+'(').replace('fn observe_','pub(crate)fn observe_',1)for name in defs]
    functions.append('pub(crate)fn observe_GrindInvestigationFields(o:&mut Output,s:&GrindInvestigationFields){'+''.join(wire.observe_expr(k,'s.'+f,'rust')for f,k in canonical['GrindInvestigationFields'])+'}')
    plan=common.grind.block((PLUGIN/'Tests/Reference/player_grind_input_probe.rs').read_text(),'fn observe_plan(').replace('fn observe_plan(','pub(crate)fn observe_plan(',1)
    return '\n'.join(cp),'mod input_host_protocol{use super::{Input,Output};'+imports+'\n'+'\n'.join(functions)+'\n'+plan+'}',private,pre

def trajectory_readers():
    # Exact borrowed proof transport, not numerical owner implementation.
    raw=(PLUGIN/'Tests/Simulation/air_trajectory_selector_probe.cpp').read_text()
    cp=[]
    for marker,name in(('AirLaunchInfo ReadLaunch()','ReadLaunch'),('AirSelectorInput ReadSelectorInput()','ReadSelectorInput')):
        body=common.grind.block(raw,marker).replace(name+'()',name+'(BipedInput& i)',1)
        body=re.sub(r'\bMatrix\(\)',r'i.Matrix()',body)
        body=re.sub(r'\bVector\(\)',r'i.Floats<4>()',body)
        body=re.sub(r'\bFloat\(\)',r'i.Float()',body)
        body=re.sub(r'\bWord\(\)',r'i.Word()',body);cp.append(body)
    raw=(PLUGIN/'Tests/Simulation/player_grind_input_probe.cpp').read_text()
    world=common.grind.block(raw,'WorldGeometry World(unsigned kind)').replace('World(unsigned kind)','TrajectoryWorldBase(unsigned kind)',1)
    runtime=common.grind.block((PLUGIN/'Tests/Simulation/air_trajectory_runtime_probe.cpp').read_text(),'WorldGeometry RuntimeWorld(unsigned kind)')
    runtime=runtime.replace('RuntimeWorld(unsigned kind)','TrajectoryWorld(unsigned kind)',1);runtime=re.sub(r'\bWorld\(',r'TrajectoryWorldBase(',runtime)
    cp.extend((world,runtime))
    raw=(PLUGIN/'Tests/Reference/air_trajectory_runtime_probe.rs').read_text();rp=[]
    for marker,name in(('fn launch(&mut self)','launch'),('fn input(&mut self)','selector_input')):
        body=common.grind.block(raw,' '+marker).replace(marker,'fn read_'+name+'(i:&mut Input)',1).replace('self.','i.').replace('i.vector()','i.floats()')
        rp.append(body)
    raw=(PLUGIN/'Tests/Reference/player_grind_input_probe.rs').read_text();rp.append(common.grind.block(raw,'fn fixture_world(kind:u32)'))
    raw=(PLUGIN/'Tests/Reference/air_trajectory_runtime_probe.rs').read_text();rp.append(common.grind.block(raw,'fn runtime_world(kind:u32)').replace('fn runtime_world(','pub(super)fn runtime_world(',1))
    return '\n'.join(cp),'use skate_core::air::trajectory::{LaunchInfo,SelectorInput};use crate::{BoardWorld,WorldTriangle,QueryMetadata,QueryMesh,QueryPool,Bounds,Vector3,triangle_from_volume,RetailContactMaterial,RetailAffineTransform};\n'+'\n'.join(rp)

def owner_observer(pre):
    return '''
pub(crate)fn migration_input_host_observe(o:&mut crate::Output,r:&PlayerInputRuntime,g:&GroundRuntime,skater:&super::SkaterRuntime){
 o.word(skater.trajectory.selector.grind_locked_to_middle()as u32);o.word(skater.trajectory.selector.valid()as u32);o.word(grind::migration_input_host_target(&r.grind) as u32);o.word(r.physical.state.flag_61 as u32);
 o.word(r.toolkit.is_some()as u32);if let Some(t)=r.toolkit{for m in[t.deck,t.effective,t.inverse_effective]{o.matrix(m)}for v in[t.side,t.up,t.forward,t.horizontal_forward,t.transverse_up,t.forward_velocity,t.travel_direction,t.filtered_normal]{o.floats(v)}o.floats([t.absolute_speed,t.control_sign,t.total_mass]);}
 o.word(r.pending_teleport.is_some()as u32);if let Some(m)=r.pending_teleport{o.matrix(m)}
 for v in[r.dynamic_normal.normal,r.dynamic_normal.delta,r.dynamic_normal.acceleration,r.dynamic_normal.last_contact_normal]{o.floats([v.x,v.y,v.z])}
 let s=&r.normal_settings;o.floats([s.speed_damping,s.up_vector_damping,s.maximum_delta,s.speed_scale]);o.floats(s.maximum_delta_vs_speed.x);o.floats(s.maximum_delta_vs_speed.y);
 o.word(r.pre_input.pending_geometry as u32);let s=&r.pre_input.result;
 '''+''.join(wire.observe_expr(k,'s.'+f,'rust')for f,k in pre)+'''
 o.words(r.pre_input.result_counts);grind::observe_state(o,&r.grind);o.word(r.pending_grind.is_some()as u32);if let Some(p)=&r.pending_grind{grind::observe_pending(o,p)}
 o.word(r.grind_observation.is_some()as u32);if let Some(m)=&r.grind_observation{super::grind::migration_input_host_manager(o,m)}o.floats(g.migration_input_host_normal());
}
'''

def prepare(out):
    original,observed,snapshot,report=common.prepare(out);crate=observed/'atelier-host'
    cpp=(snapshot/'player_state_publication_probe.cpp').read_text();main=crate/'src/migration_probe.rs';rs=main.read_text()
    cp,rp=readers(cpp,rs);co,ro,private,pre=observers();trajectory_cp,trajectory_rp=trajectory_readers()
    helper=OWNED[0].read_text().replace('// GENERATED_READERS',cp).replace('// GENERATED_INPUT_OBSERVERS',co).replace('// GENERATED_GRIND_OBSERVERS','').replace('// GENERATED_TRAJECTORY_READERS',trajectory_cp)
    cpp=common.replace_once(cpp,'int main(int argc,char** argv)',helper+'\nint main(int argc,char** argv)')
    bind='''
        PlayerTeleportRuntime actual_teleport({ground,life.skeleton_controller,*sair,f,h,grab,wipeout.state,wobble,life.skeleton_elapsed_16505,life.board_animated_290});
        const PlayerInputOwners input_owners{p,ground_runtime,*input,animated,*ik,anim,materials};
        const PlayerInputHostPhaseOwners host_owners{shared,input_owners,contact,selector,landing,trajectory,actual_teleport,*provider};bool host_teleported=false;
'''
    cpp=common.replace_once(cpp,'const auto snapshot=[&]{common_publication::Snapshot',bind+'const auto snapshot=[&]{input_host_detail::Snapshot(o,*player_owner,ground_runtime,trajectory);common_publication::Snapshot')
    cases='''case 90:okay=input_host_detail::Advance(i,o,host_owners,pose,host_teleported,error);break;
            case 91:line_state=input_host_detail::ReadPlayerInputState(i);break;case 92:okay=player_owner->RequestTeleport(i.Matrix(),error);break;
            case 93:player_owner->pre_input.pending_geometry=i.Word()!=0;break;case 94:okay=input_host_detail::ConsumePending(common,materials,error);break;
            case 95:host_teleported=i.Word()!=0;break;case 96:publication.teleport_output.reset();publication.state.flag_61=1;break;case 97:teleport.PublishOutput(publication);break;
            case 98:{const auto info=input_host_detail::ReadLaunch(i);const auto in=input_host_detail::ReadSelectorInput(i);bool launched=false;okay=trajectory.Launch(info,in,p.world,launched,error);break;}
            case 99:{const auto in=input_host_detail::ReadSelectorInput(i);const auto board=i.Floats<4>(),body=i.Floats<4>();const auto actor=i.Word(),matching=i.Word();ProcessedPhysicsInput context;for(unsigned n=0;n<4;++n)std::memcpy(&context.vectors_544_560_592_608[2][n],&body[n],4);context.actor_query_2948=actor;context.actor_query_2952=matching;bool valid=false;okay=trajectory.Update(in,p.world,AirTrajectoryGrindContext::FromProcessed(context,board),valid,error);break;}
            case 100:trajectory.BindGrindWorld(std::make_shared<PlayerGrindStaticProvider>(ReadProvider(i)));break;
            case 101:p.world=input_host_detail::TrajectoryWorld(i.Word());break;case 102:trajectory.selector.Reset();break;case 103:trajectory.selector.UpdateWithoutCompletion();break;case 104:trajectory.selector.CancelPending();break;
            default:return 2;'''
    cpp=common.replace_once(cpp,'            default:return 2;',cases);(snapshot/'player_input_host_phase_probe.cpp').write_text(cpp)
    for unit in UNITS:shutil.copy2(CODE/(unit+'.cpp'),snapshot/(unit+'.cpp'))
    physics=crate/'src/physics.rs';r=physics.read_text()
    r=common.replace_once(r,'super::migration_common_publication::snapshot(o,p,s);','super::migration_input_host::snapshot(o,s);super::migration_common_publication::snapshot(o,p,s);')
    r=common.replace_once(r,'s.trajectory.bind_grind_world(provider);let mut last=None;','s.trajectory.bind_grind_world(provider);let mut host_teleported=false;let mut last=None;')
    cases='''90=>super::migration_input_host::advance(i,o,&mut p,&mut s,&mut host_teleported),91=>{s.player_input.player=crate::read_PlayerInputState(i);Ok(())},
92=>s.player_input.request_teleport(i.matrix()),93=>{s.player_input.pre_input.pending_geometry=i.word()!=0;Ok(())},
94=>super::migration_input_host::consume_pending(&mut p,&mut s),95=>{host_teleported=i.word()!=0;Ok(())},96=>{s.player_input.physical.teleport_output=None;s.player_input.physical.state.flag_61=1;Ok(())},97=>{s.teleport_state.publish_output(&mut s.player_input.physical);Ok(())},
98=>super::migration_input_host::launch(i,&mut p,&mut s),99=>super::migration_input_host::update(i,&mut p,&mut s),
100=>{s.trajectory.bind_grind_world(std::sync::Arc::new(crate::read_provider(i)));Ok(())},101=>{p.world=super::migration_input_host::runtime_world(i.word());Ok(())},102=>{s.trajectory.selector.reset();Ok(())},103=>{s.trajectory.selector.update_without_completion();Ok(())},104=>{s.trajectory.selector.cancel_pending();Ok(())},
_=>panic!("Biped owner operation")'''
    r=common.replace_once(r,'_=>panic!("Biped owner operation")',cases);r+='\n'+OWNED[1].read_text().replace('// GENERATED_TRAJECTORY_READERS',trajectory_rp)+'\npub(crate)use player_input::grind as migration_input_host_grind;\n';physics.write_text(r)
    extensions={'physics/player_input/mod.rs':owner_observer(pre),'physics/player_input/grind.rs':'\n'+private+'\npub(crate)fn migration_input_host_target(s:&GrindInputState)->bool{s.previous_air_target}\n',
        'physics/ground_runtime/mod.rs':'\nimpl GroundRuntime{pub(crate)fn migration_input_host_normal(&self)->[f32;4]{self.retained_board_normal}}\n',
        'physics/grind/runtime.rs':'\npub(crate)fn migration_input_host_manager(o:&mut crate::Output,m:&ManagerObservation){migration_manager(o,m)}\n',
        'physics/grind.rs':'\npub(crate)use runtime::migration_input_host_manager;\n'}
    for rel,append in extensions.items():p=crate/'src'/rel;p.write_bytes(p.read_bytes()+append.encode())
    rs=rs[:rs.index('fn main(){')]+rp+'\n'+ro+'\n'+rs[rs.index('fn main(){'):];main.write_text(rs)
    cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text().replace('name="player-state-publication-reference"','name="player-input-host-phase-reference"'))
    prefixes={}
    for p in sorted((original/'crates/skate-host/src').rglob('*.rs')):
        rel=p.relative_to(original/'crates/skate-host/src').as_posix()
        if rel in('lib.rs','main.rs'):continue
        dest=crate/'src'/rel;raw=p.read_bytes();assert dest.read_bytes()[:len(raw)]==raw,rel
        prefixes[rel]=dict(original_sha256=digest(p),original_bytes=len(raw),generated_sha256=digest(dest))
    report.update(input_host_original_prefixes=prefixes,input_host_production={p.name:digest(p)for p in PRODUCTION},input_host_proof={p.name:digest(p)for p in OWNED},
        input_host_extensions={rel:hashlib.sha256(v.encode()).hexdigest()for rel,v in extensions.items()},input_host_simulation_sha256=digest(snapshot/'player_input_host_phase_probe.cpp'),
        input_host_reference_sha256=digest(main),input_host_middle_lock_witness=dict(case=1,world=1,commands=81,stock_settings=True,source_proof_sha256=digest(Path(trajectory_proof.__file__))),input_host_units=UNITS,input_host_boundary=__doc__,input_host_simulation_source_sha256={p.name:digest(p)for p in snapshot.iterdir()},input_host_borrowed_trajectory_transport={p.name:digest(p)for p in(PLUGIN/'Tests/Simulation/air_trajectory_selector_probe.cpp',PLUGIN/'Tests/Simulation/player_grind_input_probe.cpp',PLUGIN/'Tests/Reference/air_trajectory_runtime_probe.rs',PLUGIN/'Tests/Reference/player_grind_input_probe.rs',PLUGIN/'Tests/Simulation/air_trajectory_runtime_probe.cpp')})
    (out/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');return original,observed,snapshot,report

def corpus():
    defs,_=wire.declarations();_,baseline,_=common.landing.corpus();input_cases,_,_=player.corpus();cases=[]
    source_ticks=[c for case in input_cases for c in case['commands']if c['op']==0]
    def phase(c):
        w=Stream();w.word(90);wire.encode(w,'AnimationInputPacket',c['packet'],defs);w.word(len(c['attributes']))
        for a in c['attributes']:
            for v in a['name']+[a['kind'],a['status'],a['sequence'],a['begin'],a['end']]:w.word(v)
            for v in a['payload']:w.word(v is not None);w.word(v)if v is not None else None
        for v in c['actions']:w.float(v)
        w.word(c['available']);return list(struct.unpack('<'+'I'*(len(w.data)//4),w.data))
    def initial(seed,request=False):
        p=reset.zero('PlayerInputState',defs);p.update(flags_1296=0xe0040000|(1<<19 if request else 0),manager_1856_counter_320=seed+3,
            previous_spin_input_1360=.317,spin_same_direction_frames_1324=seed+7,dismount_request_frames_1332=seed+11,time_on_ground_1352=.137,signed_ground_time_1356=-.731)
        w=Stream();w.word(91);wire.encode(w,'PlayerInputState',p,defs);return list(struct.unpack('<'+'I'*(len(w.data)//4),w.data))
    def add(label,cmds,index=0):
        c=copy.deepcopy(baseline[index%len(baseline)]);c.update(index=len(cases),label=label,commands=cmds,provider=common.landing.biped.phase.provider.authored_provider([[-3,-.015,0],[3,-.015,0]]));cases.append(c)
    for seed in range(12):
        cmds=copy.deepcopy(baseline[seed]['commands'][:8])+[initial(seed)]
        for tick in range(12):
            c=copy.deepcopy(source_ticks[(seed*12+tick)%len(source_ticks)]);c['packet']['state_variant_10928']=tick%5
            cmds+=[[31,seed%4],phase(c),[94],[16],[17],[79]]
            if tick%3==0:cmds+=[initial(seed+tick,True)]
            if tick%4==1:
                target=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[.137*tick,.317,-.731*tick,0]]
                cmds+=[[92]+[common.landing.biped.phase.foot.bits(x)for row in target for x in row]]
        add('whole actual input/reset and pending Grind history '+str(seed),cmds,seed)
    for seed,kind in enumerate(('missing State61 output','pending geometry','invalid state variant','missing hierarchy','late attribute payload','late IK')):
        c=copy.deepcopy(source_ticks[seed]);c['packet']['state_variant_10928']=0
        cmds=copy.deepcopy(baseline[0]['commands'][:8])+[initial(seed,True),[95,1]]
        if kind=='missing State61 output':cmds+=[[96]]
        elif kind=='pending geometry':cmds+=[[93,1]]
        elif kind=='invalid state variant':c['packet']['state_variant_10928']=99
        elif kind=='missing hierarchy':cmds+=[[38]]
        elif kind=='late attribute payload':
            a=copy.deepcopy(c['attributes'][0]);a['name']=trees.name('Brake');a['payload']=[None]*6;c['attributes'].append(a)
        elif kind=='late IK':cmds+=[[78,23,0xffffffff]]
        add('actual source error prefix: '+kind,cmds+[phase(c)],seed)
    # State702 captures the real deferred checkpoint reply, then supplies the
    # State61 transform consumed by input_phase. No output/flag is seeded.
    for seed in range(4):
        c=copy.deepcopy(source_ticks[seed]);c['packet']['state_variant_10928']=0
        cmds=copy.deepcopy(baseline[seed]['commands'][:8])+[initial(seed),[75],[76],[80],[76],[97],phase(c),[94],phase(c),[94]]
        add('actual checkpoint reply -> State61 reset continuation '+str(seed),cmds,seed)
    # Reproduce the proven full real-provider/real-world prefix that reaches a
    # stock-settings middle lock; then input_phase reads that SAME selector.
    _,programs=trajectory_proof.corpus();witness=programs[1]
    assert witness['world']==1 and witness['commands'][80][0]==1
    prefix=copy.deepcopy(witness['commands'][:81]);assert not any(c[0]==6 for c in prefix)
    remap={0:98,1:99,2:102,3:104,4:103,5:100,7:101}
    for seed in range(4):
        c=copy.deepcopy(source_ticks[seed]);c['packet']['state_variant_10928']=0
        cmds=copy.deepcopy(baseline[seed]['commands'][:8])+[initial(seed),[40,201],[50],[41],[101,witness['world']]]
        cmds += [[remap[q[0]]]+q[1:]for q in prefix]
        cmds += [phase(c),[94],phase(c),[94],[102],phase(c),[94]]
        add('actual stock middle-lock producer consumed by full input phase '+str(seed),cmds,seed)
    return (*common.encode(cases),cases)

def protocol_audit(raw,ranges,cases):
    defs,_=wire.declarations();counts=Counter()
    def span(kind,cmd,at):
        if kind.startswith('&'):kind=kind[1:]
        a=wire.array(kind);o=wire.option(kind)
        if o:return 1+(span(o,cmd,at+1)if cmd[at]else 0)
        if a:
            begin=at
            for _ in range(a[1]):at+=span(a[0],cmd,at)
            return at-begin
        if kind=='RawVector':return 4
        if kind=='RawMatrix':return 16
        if kind=='u64':return 2
        if kind in('u8','u16','u32','i32','f32','bool','NativeReferenceBase'):return 1
        begin=at
        for _,t in defs[kind]:at+=span(t,cmd,at)
        return at-begin
    def world_span(cmd,at):
        begin=at;n=cmd[at];at+=1+18*n;at+=1
        n=cmd[at];at+=1+n;n=cmd[at];at+=1+36*n
        n=cmd[at];at+=1+12*n;return at+1-begin
    fixed={**{n:1 for n in OPS},**{n:2 for n in(1,2,25,31,40,55,63,93,95)},26:3,39:3,43:8,44:3,57:3,63:3,64:5,65:4,77:3,78:3,92:17,98:98,99:38,101:2}
    assert struct.unpack_from('<I',raw)[0]==len(cases)
    for c,(start,end)in zip(cases,ranges):
        stream=common.landing.biped.phase.provider.Stream()
        for w in common.landing.biped.landing.encode_world(c['world']):stream.word(w)
        common.landing.biped.phase.provider.encode_provider(stream,c['provider'])
        for w in common.landing.biped.grab.encode_registry(c['registry'])+[len(c['commands'])]:stream.word(w)
        for cmd in c['commands']:
            op=cmd[0];counts[OPS[op]]+=1
            if op==90:
                at=1+span('AnimationInputPacket',cmd,1);n=cmd[at];at+=1
                for _ in range(n):
                    at+=10
                    for _ in range(6):at+=1+(1 if cmd[at]else 0)
                length=at+19
            elif op in(0,42,91):length=1+span({0:'ProcessedPhysicsInput',42:'PhysicalPlayerInput',91:'PlayerInputState'}[op],cmd,1)+(21 if op==0 else 0)
            elif op==22:length=1+world_span(cmd,1)
            elif op==100:
                at=1
                def text():
                    nonlocal at
                    at+=1+cmd[at]
                n=cmd[at];at+=1
                for _ in range(n):
                    text();at+=1;points=cmd[at];at+=1+3*points
                    yes=cmd[at];at+=1
                    if yes:text()
                text();n=cmd[at];at+=1+24*n;n=cmd[at];at+=1+4*n
                n=cmd[at];at+=1
                for _ in range(n):text();text();at+=5;text()
                length=at
            else:length=fixed[op]
            assert len(cmd)==length,(c['index'],op,len(cmd),length)
            for w in cmd:stream.word(w)
        assert raw[start:end]==bytes(stream.data),c['index']
    return dict(roundtrip_bytes=len(raw),operations=dict(counts),upstream_packet_boundary='Complete AnimationInputPacket, fresh packet attributes, and sampled ActionMap records are explicit caller inputs; no numerical callback producer is replaced.')

class Reader(common.Reader):
    def input_owner(self):
        assert self.word()==1;n=self.word();at=self.at;v=self.take(n);return v,{'input_host':(at,self.at)}
def decode(raw,cases):
    r=Reader(raw);assert r.word()==len(cases);frames=[]
    def snap():
        extra,spans=r.input_owner();c,more=r.common();spans.update(more);l,more=r.landing();spans.update(more);o,more=r.biped();spans.update(more)
        f=r.foot();spans.update(r.foot_spans);s=r.snapshot();spans.update(r.spans);return dict(input_owner=extra,common=c,landing=l,owner=o,foot=f,shared=s,spans=spans)
    for c in cases:
        c['first_output_word']=r.at;assert r.word()==len(c['commands']);prior=snap();rows=[]
        for cmd in c['commands']:
            at=r.at;assert r.word()==cmd[0];teleported=None;calls=[]
            if cmd[0]==21:r.take(r.word())
            if cmd[0]==90:teleported=r.word();calls=r.take(r.word())
            error=r.status();next_=snap();rows.append(dict(operation=cmd[0],error=error,teleported=teleported,actions=calls,first_word=at,last_word=r.at,prior=prior,**next_));prior=next_
        c['last_output_word']=r.at;frames.append(rows)
    assert r.at==len(r.words),(r.at,len(r.words));return frames

def coverage(frames):
    counts=Counter();errors=Counter();teleports=0;partial=0;calls=Counter();changed=Counter();targeting=Counter();consumed_target=0;state61_resets=0;retained_failed_results=0
    for rows in frames:
        for r in rows:
            counts[OPS[r['operation']]]+=1
            if r['error']:errors[r['error']]+=1
            for k in('input_owner','common','owner','foot','shared'):changed[k]+=r[k]!=r['prior'][k]
            if r['operation']!=90:continue
            targeting[int(r['prior']['input_owner'][0])]+=1
            consumed_target+=not r['error'] and bool(r['input_owner'][2])
            state61_resets+=not r['error'] and bool(r['prior']['input_owner'][3]) and bool(r['teleported'])
            retained_failed_results+=bool(r['error']) and bool(r['teleported'])
            calls.update(r['actions']);teleports+=bool(r['teleported'])and not r['error']
            partial+=bool(r['error'])and(r['input_owner']!=r['prior']['input_owner']or r['owner']!=r['prior']['owner'])
    assert counts['complete_input_host']>100 and teleports>20 and partial>=4,(counts,teleports,partial)
    assert 71 in calls and len(calls)>5,calls
    assert targeting[0]>0 and targeting[1]>=8,targeting
    assert consumed_target>=8,consumed_target
    assert state61_resets>=4,state61_resets
    assert retained_failed_results>=6,retained_failed_results
    assert counts['actual_state61_publication']==4
    assert all(changed.values()),changed
    assert any('Teleport State61' in e for e in errors),errors
    assert any('Pending82D811C8' in e for e in errors),errors
    assert any('InvalidStateVariant' in e for e in errors),errors
    assert any('bone' in e.lower()or'hierarchy'in e.lower()for e in errors),errors
    assert any('payload' in e.lower()for e in errors),errors
    return dict(operations=dict(counts),errors=dict(errors),successful_teleports=teleports,error_partial_mutations=partial,action_calls=dict(calls),changed_records=dict(changed),actual_trajectory_targeting=dict(targeting),consumed_real_middle_lock=consumed_target,successful_state61_resets=state61_resets,error_preserved_caller_boolean=retained_failed_results)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in('assets','samples','metadata','output','target-dir'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    for name in('result.json','first-divergence.json'):(out/name).unlink(missing_ok=True)
    raw,ranges,cases=corpus();assert common.encode(cases)[0]==raw;protocol=protocol_audit(raw,ranges,cases)
    (out/'input.bin').write_bytes(raw);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');original,observed,snapshot,report=prepare(out)
    summary=dict(histories=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(raw),input_sha256=hashlib.sha256(raw).hexdigest(),units=len(UNITS),protocol=protocol)
    if a.preflight:
        (out/'owner-freeze.json').write_text(json.dumps(dict(**summary,production={p.name:digest(p)for p in PRODUCTION},proof={p.name:digest(p)for p in OWNED}),indent=2)+'\n');print(json.dumps(summary,indent=2));return
    crate=observed/'atelier-host';subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(crate/'Cargo.toml'),'--target-dir',str(a.target_dir.resolve()),'--bin','player-input-host-phase-reference'],check=True)
    reference=out/'player-input-host-phase-reference';shutil.copy2(a.target_dir.resolve()/'release/player-input-host-phase-reference',reference)
    simulation=out/'player-input-host-phase-simulation';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'player_input_host_phase_probe.cpp'),'-o',str(simulation)],check=True)
    bank=out/'fixtures';bank.mkdir(exist_ok=True);stock=a.assets.resolve()/'private/stock';converter=common.landing.biped.phase.converter
    (bank/'settings.simulation').write_bytes(converter.encode_settings(stock/'skater-collections.json'));(bank/'physics.simulation').write_bytes(converter.encode_physics_skeletons(stock/'physics-skeletons.json'))
    for name in('action','motion'):(bank/f'actor.{name}.reference').write_bytes(common.landing.biped.phase.original_graph(common.landing.biped.phase.element('state','idle')))
    identity=json.loads((stock/'physics-skeletons.json').read_text())['source_sha256'];expected=subprocess.check_output([str(reference),str(a.assets.resolve()),str(bank)],input=raw)
    actual=subprocess.check_output([str(simulation),str(bank/'settings.simulation'),str(bank/'physics.simulation'),str(a.samples.resolve()/'simulation/rig.skate'),identity,str(a.assets.resolve()),str(a.metadata.resolve())],input=raw)
    (out/'reference.bin').write_bytes(expected);(out/'simulation.bin').write_bytes(actual);frames=decode(expected,cases)
    if expected!=actual:
        byte=next((n for n,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));word=byte//4
        c=next((c for c in cases if c['first_output_word']<=word<c['last_output_word']),None);r=next((r for rows in frames for r in rows if r['first_word']<=word<r['last_word']),None)
        div=dict(first_byte=byte,first_word=word,case=c['index']if c else None,operation=OPS[r['operation']]if r else'initial',section=next(((n,word-b)for n,(b,e)in(r['spans'].items()if r else[])if b<=word<e),None),reference_bytes=len(expected),simulation_bytes=len(actual),reference_hex=expected[max(0,byte-16):byte+32].hex(),simulation_hex=actual[max(0,byte-16):byte+32].hex())
        (out/'first-divergence.json').write_text(json.dumps(div,indent=2)+'\n');raise AssertionError(div)
    result=dict(**summary,passed=True,reference_revision=REFERENCE_REVISION,exact_bytes=len(expected),output_sha256=hashlib.sha256(expected).hexdigest(),coverage=coverage(frames),limitations=__doc__)
    report.update(reference_binary_sha256=digest(reference),simulation_binary_sha256=digest(simulation));(out/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
