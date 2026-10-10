#!/usr/bin/env python3
"""Whole original common player-state publication over one canonical owner set.

Only root builds/executes. --preflight stages source, checks protocol and hashes.
Initial processed/physical packets and selected-state bindings are explicit
upstream boundaries. Phase Fill receives actual retained owners; no Fill result
or trajectory selection is injected. The whole frame/transition/render schedule
is separate. Original unsupported states remain observable diagnostic paths.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import check_landing_on_deck_runtime_parity as landing
import check_grind_runtime_parity as grind
import check_wipeout_physical_runtime_parity as wipeout
import check_player_state_runtime_parity as state
import check_motion_graph_continuation_parity as continuation
import player_input_protocol as wire
from check_animation_playback_parity import Stream
from session_parity import digest, REFERENCE_REVISION

PLUGIN,CODE=landing.PLUGIN,landing.CODE
FAMILY=('PlayerStatePublication',)
UNITS=tuple(dict.fromkeys((*landing.UNITS,*grind.UNITS,*wipeout.UNITS,*continuation.UNITS,
    'FilteredState','LandingQuality','PlayerStateConditioning','PlayerStateRegistry',
    'PlayerStateRuntime','PlayerStateCoordinator','PlayerStateLifecycle','PlayerStateMachine',
    'PlayerStateSelector','RevertRuntime','RevertState','TeleportStateRuntime','GroundSurfaceRuntime','GroundJump','GroundPhaseRuntime','GroundAnimationSettings',
    'GroundAnimationRuntime','GroundAnimationBoard','GroundAnimationSkeleton',
    'SlideState','SlideStateSettings','SlideStateRuntime','SlidePhaseRuntime','SlidePhaseBindings',
    'GraphActionPhysicalConditions','GraphMotionPhysicalConditions',*FAMILY)))
PRODUCTION=(CODE/'PlayerStatePublication.h',CODE/'PlayerStatePublication.cpp')
OWNED=(PLUGIN/'Tests/Simulation/player_state_publication_probe.cpp',PLUGIN/'Tests/Reference/player_state_publication_observer.rs',Path(__file__))
SECTIONS=('state','air','grind','wipeout','other_phases')
OPS={**dict(enumerate(landing.OPS)),40:'selected_state_boundary',41:'common_publication',42:'initial_physical_packet',
    43:'upstream_common_inputs',44:'invalid_completed_grind_name',45:'clear_manager',46:'clear_grind_names',
    50:'enter_air',51:'advance_air',52:'enter_known',53:'update_known',54:'post_known',55:'enter_grind',
    56:'advance_grind',57:'manager_producer',58:'exit_grind',60:'enter_wipeout',61:'advance_wipeout',
    62:'post_wipeout',63:'request_wipeout',64:'initial_body_velocity',65:'initial_body_displacement',
    70:'enter_ground',71:'enter_revert',72:'enter_ground_animation',73:'enter_slide',74:'advance_slide',
    75:'teleport_enter',76:'teleport_update',77:'restore_ik_bone',78:'invalid_ik_bone',79:'wheel_riding_publication',80:'actual_teleport_reply_transport'}

def replace_once(text,old,new):
    assert text.count(old)==1,(old,text.count(old));return text.replace(old,new)

def ground_observers():
    _,defs=state.declarations();cpp=[];rust=[]
    for name,fields in defs.items():
        simulation=state.RENAMES.get(name,name)
        cp='void GroundObserve(BipedOutput& o,const '+simulation+'& s){'+''.join(wire.observe_expr(k,'s.'+f,'cpp')for f,k in fields)+'}'
        rp='fn common_ground_observe_'+name+'(o:&mut Output,s:&skate_core::riding::grounded::state::output::'+name+'){'+''.join(wire.observe_expr(k,'s.'+f,'rust')for f,k in fields)+'}'
        # Nested record observation must call these separate observer names.
        cp=re.sub(r'\bObserve\(', 'GroundObserve(',cp)
        for child in defs:rp=re.sub(r'\bobserve_'+re.escape(child)+r'\(', 'common_ground_observe_'+child+'(',rp)
        cpp.append(cp);rust.append(rp)
    return '\n'.join(cpp),'\n'.join(rust)

def cache_observer():
    fields=['self.category as u32','self.previous_category as u32','self.previous_physics_state as u32','self.air_count as u32','self.nonspecific_count as u32','self.nonspecific_collision_free_count as u32','self.nonspecific_collision_count as u32','self.frames_since_ground_stairs as u32','self.must_change as u32','g.kind as u32','g.scorable_id as u32']
    fields += [f'g.name.0[{n}]'for n in range(5)]+[f'g.scoring_name.0[{n}]'for n in range(5)]
    fields += ['g.on_front as u32','g.crouch.to_bits()','g.pathed_guid as u32','(g.pathed_guid>>32)as u32','g.local_guid as u32','(g.local_guid>>32)as u32']
    return '\nimpl FilteredState{pub fn migration_common_words(&self)->[u32;27]{let g=self.cached_grind;['+','.join(fields)+']}}\n'

PLAYER_OBSERVER='''
pub(crate)fn migration_common_observe(o:&mut crate::Output,s:&SkaterRuntime){
 let p=&s.player_state;o.words([p.current()as u32,p.requested_state as u32,p.state_count,p.update_count]);o.words(p.state_flags.map(u32::from));
 o.words(p.filtered.migration_common_words());o.word(p.filtered_output.is_some()as u32);
 if let Some(f)=p.filtered_output{o.words([f.category as u32,f.previous_category as u32,f.grinding as u32]);let g=f.grind;o.words([g.kind as u32,g.scorable_id as u32]);o.words(g.name.0);o.words(g.scoring_name.0);o.word(g.on_front as u32);o.float(g.crouch);o.wide(g.pathed_guid);o.wide(g.local_guid);o.float(f.last_grind_distance);}
 o.word(p.ground_output.is_some()as u32);if let Some(g)=p.ground_output.as_ref(){crate::common_ground_observe_PhysicsGroundOutput(o,g)}
 let l=s.landing_quality;o.floats([l.landing_adjust_80,l.sideways_speed_84,l.forward_speed_88,l.spin_92]);o.words([l.landing_type_96,l.landing_data_167 as u32]);
}
'''

SIMULATION_CONSTRUCTION='''
        auto player_owner=PlayerInputRuntime::Load(data,error);auto state_owner=PlayerStateRuntime::Load(data,"normal",error);
        GroundRuntime ground_runtime;GroundSettings gs;TrainerTuning trainer;GrindRuntime grind;WipeoutPhysicalRuntime wphysical;
        KnownAirRuntime known;AirPhaseRuntime air_phase;RevertRuntime revert;GroundAnimationRuntime ground_animation;SlidePhaseRuntime slide;
        PlayerGrindMaterials materials(p.settings.board);SimulationExchange exchange(0);
        if(!player_owner||!state_owner||!state_owner->conditioning.Load(data,error)||!ground_runtime.Load(data,error)
            ||!gs.Load(data,"normal","smooth",error)||!grind.Load(data,error)||!wphysical.Load(data,*definition,error)
            ||!known.Load(data,error)||!revert.Load(data,error)||!slide.Load(data,error))Fail(error.c_str());
        auto& processed=player_owner->processed;auto& publication=player_owner->physical;auto& line_state=player_owner->player;
        auto& toolkit=player_owner->toolkit;PhysicsPosePacket pose;pose.bone_count=std::uint32_t(evaluator.frames.rig.bones.size());pose.hierarchy.assign(pose.bone_count,AnimationResetPose);pose.local.assign(pose.bone_count,AnimationResetPose);pose.timestep=landing_host_detail::PhysicalStep();
        TeleportStateRuntime teleport({p.DeckFrame(),true});std::optional<OffboardToolkitInput> last;BipedStatePublication returned{};
'''
SIMULATION_VIEWS='''
        const PlayerStateCoordinatorOwners shared{p,*player_owner,*state_owner,life,*input,anim,*ik,wipeout.state,grab_runtime,exchange};
        const AirPhaseOwners air_owners{p,processed,toolkit,ground,ground_runtime,life,animated,*ik,anim,*input,*sair,reckoning,f,wipeout,*provider,trajectory,air_settings,{state_owner->post.jump_reference,state_owner->post.jump_fix_frames},pose};
        const GrindRuntimeOwners grind_owners{p,*player_owner,ground,ground_runtime,life,animated,*ik,anim,*input,*sair,reckoning,wipeout.state,trajectory,gs,air_settings,trainer,pose.hierarchy};
        const WipeoutPhysicalOwners wipeout_owners{p,*player_owner,ground,life,animated,*ik,anim,*input,wipeout,air_settings,pose.hierarchy};
        const GroundPhaseOwners ground_owners{p,processed,toolkit,ground,ground_runtime,life,animated,*ik,anim,reckoning,wobble,grab,wipeout.state,h,*provider,trajectory,air_settings};
        const GroundAnimationOwners animation_owners{p,processed,toolkit,ground,ground_runtime,life,animated,*ik,anim,*input,*sair,wipeout.state,trajectory,air_settings,pose,trainer};
        const SlidePhaseOwners slide_owners{p,processed,toolkit,ground,ground_runtime,life,animated,*ik,anim,*input,*sair,reckoning,wipeout,trajectory,air_settings,gs,pose,state_owner->post.jump_fix_frames};
        const PlayerStatePublicationOwners common{shared,air_owners,owners,landing_owners,grind_owners,wipeout_owners,air_phase,known,*bground,bair,landed,grind,wphysical,revert,slide.state,h,ground_animation,teleport};
'''
SIMULATION_CASES='''
            case 40:{const auto id=ParsePhysicalStateId(i.Word());if(!id)return 2;state_owner->lifecycle=PhysicalPlayerStateLifecycle(*id);break;}
            case 41:okay=PublishPlayerPhysicalState(common,error);break;
            case 42:publication=ReadPhysicalPlayerInput(i);break;
            case 43:line_state.flags_1296=i.Word();line_state.state_count_1312=i.Word();line_state.update_count_1316=i.Word();line_state.dismount_request_frames_1332=i.Word();anim.fields.balance=i.Float();state_owner->selector.request_teleport=i.Word()!=0;pose.riding_fakie=i.Word()!=0;break;
            case 44:publication.grinds.words_136_140={i.Word(),i.Word()};break;
            case 45:grind.manager.reset();break;case 46:publication.grinds.animation_name_156.reset();publication.grinds.scoring_name_176.reset();break;
            case 50:okay=air_phase.Enter(air_owners,error);break;case 51:okay=air_phase.Advance(air_owners,error);break;
            case 52:okay=known.Enter(air_owners,error);break;case 53:okay=known.Update(air_owners,error);break;case 54:okay=known.PostPhysics(air_owners,error);break;
            case 55:{const auto id=ParsePhysicalStateId(i.Word());if(!id)return 2;state_owner->lifecycle=PhysicalPlayerStateLifecycle(*id);okay=grind.Enter(*id,grind_owners,error);break;}
            case 56:okay=grind.Advance(grind_owners,error);break;case 57:okay=common_publication::GrindProducer(i,common,materials,error);break;case 58:okay=grind.Exit(grind_owners,error);break;
            case 60:okay=wphysical.Enter(wipeout_owners,error);break;case 61:okay=wphysical.Advance(wipeout_owners,error);break;case 62:wphysical.PostPhysics(wipeout_owners);break;
            case 63:{const auto reason=i.Word();wipeout.state.Request(reason,i.Float());break;}
            case 64:{const auto part=i.Word();const auto v=i.Floats<3>();p.skeleton.BodiesMut()[part].rates.linear_velocity={v[0],v[1],v[2]};break;}
            case 65:{const auto v=i.Floats<3>();for(auto& b:p.skeleton.BodiesMut()){b.rates.position.x+=v[0];b.rates.position.y+=v[1];b.rates.position.z+=v[2];}p.skeleton.PublishPhysicalRecord(p.DeckFrame());break;}
            case 70:okay=EnterGroundPhase(ground_owners,error);break;case 71:revert.Enter(ground_owners);break;
            case 72:okay=ground_animation.Enter(animation_owners,error);break;case 73:slide.Enter(slide_owners);break;case 74:okay=slide.Advance(slide_owners,error);break;
            case 75:teleport.Enter();break;case 76:if(teleport.Update(processed))teleport.RequestCheckpoint();break;
            case 77:{const auto part=i.Word();ik->bone_indices[part]=i.Word();break;}
            case 78:{const auto part=i.Word();ik->bone_indices[part]=i.Word();break;}
            case 79:p.processed_flags_2468=processed.flags_2468;okay=p.riding.StartWheelQueries(p.board,p.world,error)&&p.riding.FinishWheelQueries(error);if(okay)p.riding.FinishPostPhysics(p.board,p.board_wiping_out,processed.flags_2468,processed.timestep_2604);break;
            case 80:{const auto reply=teleport.TakeReply();if(reply){processed.matrix_1536=reply->transform;processed.byte_1600=reply->byte64;processed.flags_2468|=2u;}break;}
            default:return 2;
'''
REFERENCE_CASES='''
40=>{let id=skate_core::player::state::PhysicalStateId::try_from(i.word()).map_err(|e|format!("{e:?}"))?;s.player_state.lifecycle=skate_core::player::lifecycle::PhysicalPlayerStateLifecycle::new(id);Ok(())},
41=>player_state::publish(&mut p,&mut s),42=>{s.player_input.physical=crate::read_PhysicalPlayerInput(i);Ok(())},
43=>{s.player_input.player.flags_1296=i.word();s.player_input.player.state_count_1312=i.word();s.player_input.player.update_count_1316=i.word();s.player_input.player.dismount_request_frames_1332=i.word();s.animation_input.fields.balance=i.float();s.player_state.selector.request_teleport=i.word()!=0;s.animation.packet.riding_fakie=i.word()!=0;Ok(())},
44=>{s.player_input.physical.grinds.words_136_140=i.words();Ok(())},45=>{grind::migration_common_clear_manager(&mut s.grind);Ok(())},46=>{s.player_input.physical.grinds.animation_name_156=None;s.player_input.physical.grinds.scoring_name_176=None;Ok(())},
50=>air_phase::enter(&mut p,&mut s),51=>air_phase::advance(&mut p,&mut s),52=>known_air::enter(&mut p,&mut s),53=>known_air::update(&mut p,&mut s),54=>known_air::post_physics(&mut p,&mut s),
55=>{let id=skate_core::player::state::PhysicalStateId::try_from(i.word()).map_err(|e|format!("{e:?}"))?;s.player_state.lifecycle=skate_core::player::lifecycle::PhysicalPlayerStateLifecycle::new(id);grind::enter(&mut p,&mut s)},56=>grind::advance(&mut p,&mut s),57=>super::migration_common_publication::grind_producer(i,&mut p,&mut s),58=>grind::exit(&mut p,&mut s),
60=>wipeout_states::enter(&mut p,&mut s),61=>wipeout_states::advance(&mut p,&mut s),62=>{wipeout_states::post_physics(&mut s);Ok(())},63=>{s.wipeout.state.request(i.word()as usize,i.float());Ok(())},
64=>{let part=i.word()as usize;let v=i.floats::<3>();s.skeleton.bodies_mut()[part].rates.linear_velocity=skate_core::math::Vector3::new(v[0],v[1],v[2]);Ok(())},
65=>{let v=i.floats::<3>();for b in s.skeleton.bodies_mut(){b.rates.position.x+=v[0];b.rates.position.y+=v[1];b.rates.position.z+=v[2];}s.skeleton.publish_physical_record(solve::deck_frame(&p.board));Ok(())},
70=>ground_phase::enter(&mut p,&mut s),71=>revert_state::enter(&mut p,&mut s),72=>ground_animation::enter(&mut p,&mut s),73=>slide_state::enter(&mut p,&mut s),74=>slide_state::update(&mut p,&mut s),
75=>{s.teleport_state.enter();Ok(())},76=>{if s.teleport_state.update(&s.player_input.processed){s.teleport_state.request_checkpoint()}Ok(())},
77|78=>{let part=i.word()as usize;let value=i.word()as usize;foot_ik::migration_common_bone(&mut s.foot_ik,part,value);Ok(())},
79=>{p.processed_flags_2468=s.player_input.processed.flags_2468;p.riding.start_wheel_queries(&p.board,&p.world).and_then(|_|p.riding.finish_wheel_queries()).and_then(|_|p.riding.finish_post_physics(&mut p.board,p.board_wiping_out,s.player_input.processed.flags_2468,s.player_input.processed.timestep_2604))},
80=>{if let Some(reply)=s.teleport_state.take_reply(){s.player_input.processed.matrix_1536=reply.transform;s.player_input.processed.byte_1600=reply.byte64;s.player_input.processed.flags_2468|=2;}Ok(())},
_=>panic!("Biped owner operation")
'''

def prepare(output):
    original,observed,snapshot,report=landing.prepare(output);crate=observed/'atelier-host'
    cpp=(snapshot/'landing_on_deck_runtime_probe.cpp').read_text();cpground,rpground=ground_observers()
    helpers=grind.PLUGIN/'Tests/Simulation/grind_runtime_probe.cpp';raw=helpers.read_text()
    names=('void JumperOut(','void ManagerOut(','void PoseOut(','void ComponentsOut(','void GrindOwnerOut(')
    cgrind='\n'.join(grind.block(raw,name)for name in names)
    cwipe,rwipe=wipeout.observers();cwipe=re.sub(r'\bOutput&','BipedOutput&',cwipe);cwipe=re.sub(r'\bInput&','BipedInput&',cwipe)
    extra=OWNED[0].read_text().replace('// GENERATED_GROUND_OBSERVERS',cpground).replace('// GENERATED_GRIND_OBSERVERS',cgrind).replace('// GENERATED_WIPEOUT_OBSERVERS',cwipe)
    # Read only the initial physical packet transport; inherited Biped helpers
    # already observe it but intentionally have no reader for this record.
    defs,_=wire.declarations();selected={}
    def retain(name):
        if name in selected:return
        for _,kind in defs[name]:
            while wire.array(kind)or wire.option(kind):kind=wire.array(kind)[0]if wire.array(kind)else wire.option(kind)
            if kind in defs:retain(kind)
        selected[name]=defs[name]
    retain('PhysicalPlayerInput');readers=[];rreaders=[]
    for name,fields in selected.items():
        if not re.search(r'\b'+re.escape(name)+r'\s+Read'+re.escape(name)+r'\(',cpp):
            readers.append((name+' Read'+name+'(BipedInput& i){'+name+' s;'+''.join('s.'+f+'='+wire.read_expr(k,'cpp')+';'for f,k in fields)+'return s;}').replace('Input&','BipedInput&').replace('BipedBipedInput&','BipedInput&'))
        rreaders.append('fn read_'+name+'(i:&mut Input)->'+wire.rust_kind(name)+'{'+wire.rust_kind(name)+'{'+''.join(f+':'+wire.read_expr(k,'rust')+','for f,k in fields)+'}}')
    extra='\n'.join(readers)+'\n'+extra
    # Declaration-only ordering: original schema places some leaf records after
    # records that contain them. Keep every generated observation body intact.
    struct=cpp.index('struct BipedOutput:Output');begin=cpp.index('{',struct);at=begin+1;depth=1
    while depth:
        depth+=(cpp[at]=='{')-(cpp[at]=='}');at+=1
    assert cpp[at]==';';at+=1
    declarations='\n'+''.join('void Observe(BipedOutput&,const '+name+'&);\n'for name in('AirOutputFields','ProbeFields','ExternalPhysicsInput','StateVariantFields','LineTestFields'))
    cpp=cpp[:at]+declarations+cpp[at:]
    cpp=replace_once(cpp,'int main(int argc,char** argv)',extra+'\nint main(int argc,char** argv)')
    # The inherited fixture now observes the actual constructor-backed PostInput
    # owner. Rebind its calls to this proof's SAME canonical state owner.
    assert 'state.post.jump_fix_frames' in cpp
    cpp=cpp.replace('Observations(owners,trajectory,*player_state)','Observations(owners,trajectory,*state_owner)')
    old='ProcessedPhysicsInput processed{};ResetProcessedPhysicsInput(processed);PhysicalPlayerInput publication{};ResetPhysicalPlayerOutputs(publication);PlayerInputState line_state{};if(!LoadPlayerInputState(data,line_state,error))Fail(error.c_str());'
    begin=cpp.index(old);end=cpp.index('\n        const BipedRuntimeOwners owners',begin);cpp=cpp[:begin]+SIMULATION_CONSTRUCTION+cpp[end:]
    cpp=replace_once(cpp,'const auto snapshot=[&]{landing_host_detail::Snapshot',SIMULATION_VIEWS+'const auto snapshot=[&]{common_publication::Snapshot(o,common);landing_host_detail::Snapshot')
    cpp=replace_once(cpp,'owners,trajectory,grab,last,returned,line_state,*player_state);','owners,trajectory,grab,last,returned,line_state,*state_owner);')
    cpp=replace_once(cpp,'auto world=ReadBipedWorld(i);','auto world=ReadBipedWorld(i);auto provider=std::make_shared<PlayerGrindStaticProvider>(ReadProvider(i));')
    cpp=replace_once(cpp,'OffboardContactToolkit contact;OffboardAirSelector selector(selected);','trajectory.BindGrindWorld(provider);OffboardContactToolkit contact;OffboardAirSelector selector(selected);')
    cpp=replace_once(cpp,'            default:return 2;',SIMULATION_CASES)
    # Always use the shared canonical Slide owner, even when its initial state
    # supplies a source zero. No local wall-riding output packet is invented.
    (snapshot/'player_state_publication_probe.cpp').write_text(cpp)
    for u in UNITS:assert(CODE/(u+'.cpp')).is_file(),u;shutil.copy2(CODE/(u+'.cpp'),snapshot/(u+'.cpp'))
    physics=crate/'src/physics.rs';rs=physics.read_text()
    old='super::migration_landing_host::snapshot(o,s);o.word(16);';new='super::migration_common_publication::snapshot(o,p,s);super::migration_landing_host::snapshot(o,s);o.word(16);'
    rs=replace_once(rs,old,new)
    rs=replace_once(rs,'let mut p=GamePhysics::load_with_terrain(assets,ground::Terrain::Flat)?;p.world=crate::read_biped_world(i)?;','let mut p=GamePhysics::load_with_terrain(assets,ground::Terrain::Flat)?;p.world=crate::read_biped_world(i)?;let provider=std::sync::Arc::new(crate::read_provider(i));p.grind_world=provider.clone();')
    rs=replace_once(rs,'let mut s=SkaterRuntime::load(assets,&graphs,&p,"normal")?;let mut last=None;','let mut s=SkaterRuntime::load(assets,&graphs,&p,"normal")?;s.trajectory.bind_grind_world(provider);let mut last=None;')
    rs=replace_once(rs,'_=>panic!("Biped owner operation")',REFERENCE_CASES)
    rs += '\n'+OWNED[1].read_text()+'\npub(crate)use offboard::air_selector as migration_common_air_selector;\n';physics.write_text(rs)
    manager=grind.block((PLUGIN/'Tests/Reference/player_grind_input_probe.rs').read_text(),'fn observe_observation(').replace('fn observe_observation(','fn migration_manager(').replace('physics::grind::ManagerObservation','crate::physics::grind::ManagerObservation').replace('o:&mut Output','o:&mut crate::Output')
    extensions={'physics/player_state.rs':PLAYER_OBSERVER,
        'physics/grind/runtime.rs':'\n'+manager+grind.RUNTIME_OBSERVER+'\npub(crate)fn migration_common_clear_manager(s:&mut Runtime){s.manager=None;}\n',
        'physics/grind/rng.rs':'\nimpl OrientationRandom{pub(super)fn migration_words(&self)->[u32;8]{self.words}}\n',
        'physics/grind.rs':'\npub(crate)use runtime::{migration_owner,migration_settings,migration_common_clear_manager};\n',
        'physics/grind_chromosome.rs':grind.CHROMOSOME_OBSERVER,
        'physics/grind/substate/settings.rs':grind.SUBSTATE_OBSERVER,
        'physics/foot_ik.rs':'\npub(crate)fn migration_common_bone(f:&mut FootIk,p:usize,v:usize){f.bone_indices[p]=v;}\n',
        'physics/teleport_state.rs':'\npub(crate)fn migration_common_observe(o:&mut crate::Output,s:&Runtime){o.words(s.state.migration_common_words());}\n'}
    for rel,extra in extensions.items():
        dest=crate/'src'/rel;dest.write_bytes(dest.read_bytes()+extra.encode())
        report.setdefault('common_appended_observers',{})[rel]=dict(append_sha256=hashlib.sha256(extra.encode()).hexdigest(),generated_sha256=digest(dest))
    core={'crates/skate-core/src/physics/filtered_state.rs':cache_observer(),
        'crates/skate-core/src/player/offboard/contact_toolkit.rs':'\npub use probes::Descriptor;\n',
        'crates/skate-core/src/player/teleport_state.rs':'\nimpl TeleportState{pub fn migration_common_words(&self)->[u32;19]{let mut w=[0;19];w[0]=self.ready as u32;w[1]=self.received as u32;w[2]=self.on_board as u32;for r in 0..4{for c in 0..4{w[3+r*4+c]=self.target[r][c]}}w}}\n'}
    core_prefixes={}
    for rel,extra in core.items():
        dest=observed/rel;dest.write_bytes(dest.read_bytes()+extra.encode());raw=(original/rel).read_bytes()
        assert dest.read_bytes()[:len(raw)]==raw,rel
        core_prefixes[rel]=dict(original_sha256=digest(original/rel),original_bytes=len(raw),generated_sha256=digest(dest))
    main=crate/'src/migration_probe.rs';r=main.read_text();r=r.replace('crate::physics::offboard::air_selector','crate::physics::migration_common_air_selector');rreaders=[reader for reader in rreaders if not re.search(r'\bfn\s+'+re.escape(reader.split('(')[0].removeprefix('fn '))+r'\(',r)]
    r=r[:r.index('fn main(){')]+rpground+'\n'+rwipe+'\n'+'\n'.join(rreaders)+'\n'+r[r.index('fn main(){'):];main.write_text(r)
    cargo=crate/'Cargo.toml';cargo.write_text(cargo.read_text().replace('name="landing-on-deck-runtime-reference"','name="player-state-publication-reference"'))
    for rel,row in report['staged_host_original_prefixes'].items():row['generated_sha256']=digest(crate/'src'/rel)
    # Every full original host module remains a byte-identical prefix, including
    # the complete publication and late Wipeout writer under direct comparison.
    originals={};prefixes={}
    for p in sorted((original/'crates/skate-host/src').rglob('*.rs')):
        rel=p.relative_to(original/'crates/skate-host/src').as_posix()
        if rel in('lib.rs','main.rs'):continue
        dest=crate/'src'/rel;raw=p.read_bytes();assert dest.read_bytes()[:len(raw)]==raw,rel
        prefixes[rel]=dict(original_sha256=digest(p),original_bytes=len(raw),generated_sha256=digest(dest))
    for rel,sha in report['original_source_sha256'].items():
        assert digest(original/rel)==sha;raw=(original/rel).read_bytes();assert(observed/rel).read_bytes()[:len(raw)]==raw,rel;originals[rel]=sha
    report.update(units=UNITS,common_original_prefixes=prefixes,common_core_observers={rel:hashlib.sha256(v.encode()).hexdigest()for rel,v in core.items()},common_core_original_prefixes=core_prefixes,
        immutable_simulation_sources={p.name:digest(p)for p in sorted(snapshot.glob('*.h'))+sorted(snapshot.glob('*.cpp'))},
        simulation_generated_sha256=digest(snapshot/'player_state_publication_probe.cpp'),reference_generated_sha256=digest(main),
        common_production={p.name:digest(p)for p in PRODUCTION},common_proof={p.name:digest(p)for p in OWNED},boundary=__doc__,
        borrowed_grind_observer_file_sha256=digest(helpers),borrowed_grind_observer_block_sha256=hashlib.sha256(cgrind.encode()).hexdigest())
    (output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');return original,observed,snapshot,report

def encode(cases):
    s=landing.biped.phase.provider.Stream();s.word(len(cases));ranges=[]
    for c in cases:
        start=len(s.data)
        for w in landing.biped.landing.encode_world(c['world']):s.word(w)
        landing.biped.phase.provider.encode_provider(s,c['provider'])
        for w in landing.biped.grab.encode_registry(c['registry'])+[len(c['commands'])]+[w for cmd in c['commands']for w in cmd]:s.word(w)
        ranges.append([start,len(s.data)])
    return bytes(s.data),ranges

def corpus():
    _,baseline,_=landing.corpus();defs,_=wire.declarations();cases=[]
    provider=landing.biped.phase.provider.authored_provider([[-3,-.015,0],[3,-.015,0]])
    def physical(seed):
        p=landing.biped.phase.zero('PhysicalPlayerInput',defs);p['grinds']['words_136_140']=[0xffffffff,0]
        p['air'].update(handplant_flags_324=0x0badcafe|((seed%16)<<28),scalar_184=.731,flag_441=7,use_air_reckoning_452=1)
        p['state'].update(counter_36=seed+17,flag_61=1,flag_69=1,flag_74=1)
        p['skeleton'].update(response_change_588=.137,response_changed_605=1)
        p['reckoning']['vector_144']=landing.biped.phase.foot.fs([.137,.317,.731,0]);p['reckoning']['flag_164']=1
        s=Stream();s.word(42);wire.encode(s,'PhysicalPlayerInput',p,defs);return list(struct.unpack('<'+'I'*(len(s.data)//4),s.data))
    def packet(old,state_id,n=0):
        # Preserve authored incoming fields, replacing only explicit state and
        # source control bitsets at the caller packet boundary.
        words=copy.deepcopy(old)
        # The wire has stable schema; derive field word positions independently.
        at=1
        for field,kind in defs['ProcessedPhysicsInput']:
            size=wire_span(kind,words,at,defs)
            if field=='state_2508':words[at]=state_id
            elif field=='category_2512':words[at]=state_id//100*100
            elif field=='state_identifier_2496':words[at]=500 if n==0 else 0
            elif field=='flags_2468':words[at]=0x2000|((n%2)*0x7e040000)
            elif field=='flags_2472':words[at]|=0x400 if n%2 else 0
            elif field=='flags_2476':words[at]|=0x1000000 if n%3 else 0
            elif field=='flags_2480':words[at]|=0x80000 if n%2 else 0
            elif field=='flags_2484':words[at]|=(0x200000 if n%2 else 0)|(0x400 if n%3 else 0)
            elif field=='state_variant_index_2528':words[at]=n%5
            at+=size
        assert at+21==len(words),(at,len(words))
        return words
    def add(label,commands,base=0,p=provider):
        c=copy.deepcopy(baseline[base]);c.update(index=len(cases),label=label,commands=commands,provider=p);cases.append(c)
    # Genuine Biped/Landing producer histories retain every previous command;
    # common publication is appended immediately after each real phase Fill.
    for n,prior in enumerate(baseline[:12]):
        commands=[physical(n),[43,1<<24,n+17,n+31,0,landing.biped.phase.foot.bits(.137),n%2,n%2]]
        selected=500
        for cmd in prior['commands']:
            commands.append(copy.deepcopy(cmd))
            if cmd[0]==9:selected=500 if n%2 else 502
            elif cmd[0]==14:selected=501
            elif cmd[0]==35:selected=503
            else:continue
            commands += [[40,selected],[41]]
        add('actual shared500/501/503 producer and publication '+str(n),commands,n)
    setup=copy.deepcopy(baseline[0]['commands'][:8]);base_packet=next(c for c in setup if c[0]==0)
    for st in(100,101,102,103,200,201,300,600,601,602,701,702):
        commands=[physical(st),packet(base_packet,st),[31,st%4],[2,1],[16],[79],[40,st],[43,1<<24,st,st+1,0,landing.biped.phase.foot.bits(.317),st%2,st%2]]
        if st==100:commands += [[70]]
        elif st==101:commands += [[73],[74]]
        elif st==102:commands += [[71]]
        elif st==103:commands += [[72]]
        elif st==200:commands += [[50],[51]]
        elif st==201:commands += [[50],[51],[52],[53],[54]]
        elif st==300:commands += [[63,15,landing.biped.phase.foot.bits(.137)],[60],[61],[62]]
        elif st==701:commands += [[55,701],[56]]
        elif st==702:commands += [[75],[76]]
        for n in range(12):commands += [packet(base_packet,st,n),[41]]
        commands += [[2,0],[41],[2,1],[41]]
        if st==702:commands += [[75],[76],[41],[80],[76],[41]]
        add('source supported'+str(st)+' actual retained Fill and common counters',commands)
    # Source unsupported Fill has real preceding possession/Biped writes.
    for st in(104,105,202,700):add('original unsupported publication '+str(st),[physical(st),packet(base_packet,st),[40,st],[41]])
    # Complete real StaticProvider -> surface/admission/material/balance/control
    # input producers from the accepted independent grind corpus.
    programs,_,_=grind.input_grind.corpus()
    grind_ids=(401,400,402,403,404,405);family_index=0
    for program in programs:
        if not program['label'].startswith('explicit authored'):continue
        cmd=next(c for c in program['commands']if c['op']==0);x=copy.deepcopy(cmd['p']);st=grind_ids[family_index];family_index+=1;x['state_2508']=st;x['category_2512']=400;s=Stream();s.word(0);wire.encode(s,'ProcessedPhysicsInput',x,defs)
        for f in [0,0,.137,0,0,0,.317,0,.317,1,1,.5,0,.731,0,0,1,0,0,0,0]:s.float(f)
        original_packet=list(struct.unpack('<'+'I'*(len(s.data)//4),s.data))
        commands=[physical(st),original_packet,[31,st%4],[2,1],[16],[79],[40,st]]
        for _ in range(5):commands += [original_packet,[57,20,0],[2,1]]
        commands += [[55,st]]
        for _ in range(12):commands += [[56],[41],[17],[79]]
        commands += [[45],physical(st),[41],[58],[40,100],[41]]
        add('real provider→manager→physical Grind→common '+program['label'],commands,p=program['provider'])
    # A malformed prior completed packet is an explicit upstream failure
    # boundary; actual chromosome still writes grinding before its error.
    for st in(100,200,300):
        add('late actual conditioner failure '+str(st),[physical(st),packet(base_packet,st),[31,0],[2,1],[40,st],[41],[43,0,st+31,st+7,3,landing.biped.phase.foot.bits(.731),1,1],[44,999,1],[41],[44,0xffffffff,0],[41]])
    return (*encode(cases),cases)

def wire_span(kind,words,at,defs):
    a=wire.array(kind);o=wire.option(kind)
    if o:return 1+(wire_span(o,words,at+1,defs)if words[at]else 0)
    if a:
        begin=at
        for _ in range(a[1]):at+=wire_span(a[0],words,at,defs)
        return at-begin
    if kind=='RawVector':return 4
    if kind=='RawMatrix':return 16
    if kind=='u64':return 2
    if kind in('u8','u16','u32','i32','f32','bool','NativeReferenceBase'):return 1
    begin=at
    for _,t in defs[kind]:at+=wire_span(t,words,at,defs)
    return at-begin

def protocol_audit(raw,ranges,cases):
    """Check actual reader consumption and untouched inherited command bytes."""
    defs,_=wire.declarations();counts=Counter()
    def world_span(words,at):
        begin=at;n=words[at];at+=1+18*n;at+=1
        n=words[at];at+=1+n;n=words[at];at+=1+36*n
        n=words[at];at+=1+12*n;return at+1-begin
    fixed={**{n:1 for n in OPS},**{n:2 for n in(1,2,25,31,40,55,63)},
        26:3,39:3,43:8,44:3,57:3,63:3,64:5,65:4,77:3,78:3}
    assert struct.unpack_from('<I',raw)[0]==len(cases)
    assert ranges[0][0]==4 and ranges[-1][1]==len(raw)
    for c,(start,end)in zip(cases,ranges):
        stream=landing.biped.phase.provider.Stream()
        for w in landing.biped.landing.encode_world(c['world']):stream.word(w)
        landing.biped.phase.provider.encode_provider(stream,c['provider'])
        for w in landing.biped.grab.encode_registry(c['registry'])+[len(c['commands'])]:stream.word(w)
        for cmd in c['commands']:
            op=cmd[0];assert op in OPS,op;counts[OPS[op]]+=1
            length=(1+wire_span('ProcessedPhysicsInput',cmd,1,defs)+21 if op==0 else
                1+wire_span('PhysicalPlayerInput',cmd,1,defs)if op==42 else
                1+world_span(cmd,1)if op==22 else fixed[op])
            assert len(cmd)==length,(c['index'],op,len(cmd),length)
            for w in cmd:stream.word(w)
        assert raw[start:end]==bytes(stream.data),c['index']
    _,baseline,_=landing.corpus();preserved=[]
    for old,new in zip(baseline[:12],cases[:12]):
        commands=[c for c in new['commands'][2:]if c[0]not in(40,41)]
        assert commands==old['commands'],old['index']
        original=b''.join(struct.pack('<I',w&0xffffffff)for c in old['commands']for w in c)
        preserved.append(dict(index=old['index'],commands=len(commands),bytes=len(original),sha256=hashlib.sha256(original).hexdigest()))
    return dict(roundtrip_bytes=len(raw),operations=dict(counts),inherited_original_commands=preserved)

class Reader(landing.Reader):
    def common(self):
        assert self.word()==len(SECTIONS);records={};spans={}
        for name in SECTIONS:n=self.word();at=self.at;records[name]=self.take(n);spans['common/'+name]=[at,self.at]
        return records,spans

def decode(raw,cases):
    r=Reader(raw);assert r.word()==len(cases);frames=[]
    def snap():
        common,spans=r.common();land,more=r.landing();spans.update(more);owner,more=r.biped();spans.update(more)
        foot=r.foot();spans.update(r.foot_spans);shared=r.snapshot();spans.update(r.spans)
        return dict(common=common,landing=land,owner=owner,foot=foot,shared=shared,spans=spans)
    for c in cases:
        c['first_output_word']=r.at;assert r.word()==len(c['commands']);prior=snap();rows=[]
        for cmd in c['commands']:
            start=r.at;assert r.word()==cmd[0]
            if cmd[0]==21:r.take(r.word())
            error=r.status();next_=snap();rows.append(dict(operation=cmd[0],error=error,first_word=start,last_word=r.at,prior=prior,**next_));prior=next_
        c['last_output_word']=r.at;frames.append(rows)
    assert r.at==len(r.words),(r.at,len(r.words));return frames

def coverage(frames,cases):
    success=Counter();errors=Counter();states=Counter();changed=Counter();flags=set();partial=0;rejected_worlds=0
    for rows,c in zip(frames,cases):
        for row in rows:
            op=OPS[row['operation']]
            if row['error']:errors[row['error']]+=1
            else:success[op]+=1
            for section in SECTIONS:changed[section]+=row['common'][section]!=row['prior']['common'][section]
            if row['operation']==22 and row['error']=='BoardWorld static query meshes require identity transforms':
                # Rejected constructor candidates consume their complete wire
                # packet but cannot replace the current canonical world/owners.
                for key in('common','landing','owner','foot','shared'):
                    assert row[key]==row['prior'][key],(c['index'],key,'rejected world mutated retained owners')
                rejected_worlds+=1
            if row['operation']!=41:continue
            state_words=row['common']['state'];st=state_words[0]
            if not row['error']:states[st]+=1
            flags.update(n+52 for n,b in enumerate(state_words[4:40])if b)
            # The full canonical physical packet and input histories are already
            # serialized by the inherited owner observer, before/after errors.
            partial+=bool(row['error'])and row['owner']['publication']!=row['prior']['owner']['publication']
    assert all(states[s]>0 for s in(100,101,102,103,200,201,300,400,401,402,403,404,405,500,501,502,503,600,601,602,701,702)),states
    assert sum(states[s]for s in range(400,406))>6,states
    assert success['common_publication']>100 and success['manager_producer']>5 and success['advance_grind']>5
    assert all(changed[s]>0 for s in SECTIONS),changed
    assert any('State output requires actual board toolkit'in e for e in errors)
    assert any('Active grind has invalid native family 999'in e for e in errors)
    assert any('Grind Fill requires completed manager observation'in e for e in errors)
    assert all(any('FillPhysOut requires the actual '+n+' output owner'in e for e in errors)for n in('Skitching','FollowPath','PhysicsAirSecondary','Sleeping'))
    assert partial>4 and len(flags)>15,(partial,flags)
    assert rejected_worlds>0,rejected_worlds
    return dict(successful_operations=dict(success),successful_selected_states=dict(states),errors=dict(errors),changed_sections=dict(changed),true_flag_offsets=sorted(flags),partial_error_physical_writes=partial,rejected_worlds_retained=rejected_worlds)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in('assets','samples','metadata','output','target-dir'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--preflight',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    for n in('result.json','first-divergence.json'):(out/n).unlink(missing_ok=True)
    raw,ranges,cases=corpus();assert encode(cases)[0]==raw;protocol=protocol_audit(raw,ranges,cases)
    (out/'input.bin').write_bytes(raw);(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');original,observed,snapshot,report=prepare(out)
    summary=dict(histories=len(cases),commands=sum(len(c['commands'])for c in cases),input_bytes=len(raw),input_sha256=hashlib.sha256(raw).hexdigest(),units=len(UNITS),protocol=protocol)
    if a.preflight:
        (out/'owner-freeze.json').write_text(json.dumps(dict(**summary,production={p.name:digest(p)for p in PRODUCTION},proof={p.name:digest(p)for p in OWNED}),indent=2)+'\n');print(json.dumps(summary,indent=2));return
    crate=observed/'atelier-host';subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(crate/'Cargo.toml'),'--target-dir',str(a.target_dir.resolve()),'--bin','player-state-publication-reference'],check=True)
    reference=out/'player-state-publication-reference';shutil.copy2(a.target_dir.resolve()/'release/player-state-publication-reference',reference)
    simulation=out/'player-state-publication-simulation';subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'player_state_publication_probe.cpp'),'-o',str(simulation)],check=True)
    bank=out/'fixtures';bank.mkdir(exist_ok=True);stock=a.assets.resolve()/'private/stock';converter=landing.biped.phase.converter
    (bank/'settings.simulation').write_bytes(converter.encode_settings(stock/'skater-collections.json'));(bank/'physics.simulation').write_bytes(converter.encode_physics_skeletons(stock/'physics-skeletons.json'))
    for name in('action','motion'):(bank/f'actor.{name}.reference').write_bytes(landing.biped.phase.original_graph(landing.biped.phase.element('state','idle')))
    identity=json.loads((stock/'physics-skeletons.json').read_text())['source_sha256']
    expected=subprocess.check_output([str(reference),str(a.assets.resolve()),str(bank)],input=raw)
    actual=subprocess.check_output([str(simulation),str(bank/'settings.simulation'),str(bank/'physics.simulation'),str(a.samples.resolve()/'simulation/rig.skate'),identity,str(a.assets.resolve()),str(a.metadata.resolve())],input=raw)
    (out/'reference.bin').write_bytes(expected);(out/'simulation.bin').write_bytes(actual);frames=decode(expected,cases)
    if expected!=actual:
        byte=next((n for n,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));word=byte//4
        c=next((c for c in cases if c['first_output_word']<=word<c['last_output_word']),None);r=next((r for rows in frames for r in rows if r['first_word']<=word<r['last_word']),None)
        div=dict(first_byte=byte,first_word=word,case=c['index']if c else None,operation=OPS[r['operation']]if r else'initial',section=next(((n,word-b)for n,(b,e)in(r['spans'].items()if r else[])if b<=word<e),None),reference_bytes=len(expected),simulation_bytes=len(actual),reference_hex=expected[max(0,byte-16):byte+32].hex(),simulation_hex=actual[max(0,byte-16):byte+32].hex())
        (out/'first-divergence.json').write_text(json.dumps(div,indent=2)+'\n');raise AssertionError(div)
    covered=coverage(frames,cases)
    result=dict(**summary,passed=True,reference_revision=REFERENCE_REVISION,exact_bytes=len(expected),output_sha256=hashlib.sha256(expected).hexdigest(),coverage=covered,limitations=__doc__)
    report.update(reference_binary_sha256=digest(reference),simulation_binary_sha256=digest(simulation));(out/'provenance.json').write_text(json.dumps(report,indent=2)+'\n');(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');(out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
