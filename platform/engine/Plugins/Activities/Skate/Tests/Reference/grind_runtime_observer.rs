// Read-only observers and explicit caller/transport adapters appended to input_phase.
// All original Grind and shared-owner numerical/scheduling bodies stay unchanged.
mod migration_grind_runtime {
// GENERATED_ORIGINAL_OWNER_PREFIX
// GENERATED_PROVIDER_READER
// GENERATED_GRIND_WORLD
fn live_snapshot(o:&mut Output,p:&GamePhysics,s:&SkaterRuntime,c:&CollisionInput,teleported:bool,actions:&Actions){
 o.word(4);block(o,|o|snapshot(o,p,s,c,teleported,actions));block(o,|o|super::super::grind::migration_owner(o,&s.grind,&s.player_input.grind.jumper));
 block(o,|o|super::super::grind_camera::migration_observe(o,&s.grind_camera));block(o,|o|super::super::grind::migration_settings(o,&s.grind));
}
fn read_family(i:&mut Input)->super::super::grind::Family{use super::super::grind::Family;match i.word(){0=>Family::FiftyFifty,1=>Family::Boardslide,2=>Family::Tipslide,3=>Family::FiveO,4=>Family::Backslash,5=>Family::Darkslide,_=>panic!("family transport")}}
fn read_manager(i:&mut Input)->super::super::grind::ManagerObservation{use super::super::grind::observation::*;ManagerObservation{geometry:GeometryObservation{point_1120:i.floats(),direction_1136:i.floats(),normal_1152:i.floats(),target_up_1168:i.floats(),primitive_start_1264:i.floats(),primitive_end_1280:i.floats(),spline_guids_1296:if i.word()!=0{Some([i.wide(),i.wide()])}else{None},upmost_normal_1408:i.floats(),high_side_1440:i.floats(),kind_1464:i.word(),flags_1476:i.word(),impact_speed_1492:i.float()},surface:SurfaceObservation{audio_surface_1468:i.word(),material_1472:i.word(),friction_vs_time_1496:i.float(),reckon_blend_selector_1500:i.float(),gravity_relief_1512:i.float()},control:ControlObservation{family:read_family(i),flags_1516:i.word(),flags_2468:i.word(),flags_2488:i.word(),translation_2796:i.float(),balance_2800:i.float(),exit_lean:i.float()},engagement:EngagementObservation{velocity_1184:i.floats(),kind_1248:i.word()},jumper:JumperObservation{geometry_kind_16:i.word(),family_20:read_family(i),energy_24:i.float(),high_side_32:i.floats(),normal_48:i.floats(),direction_64:i.floats(),upmost_normal_80:i.floats(),point_96:i.floats()}}}
fn read_jumper(i:&mut Input)->skate_core::physics::grind_contact::manager::Jumper{use skate_core::physics::grind_contact::manager::{Jumper,JumpGeometry};Jumper{launched:i.word()!=0,cooldown:i.word(),family:i.word(),energy:i.float(),geometry:JumpGeometry{geometry_kind:i.word(),high_side:i.floats(),normal:i.floats(),direction:i.floats(),upmost:i.floats(),point:i.floats()}}}
fn text(o:&mut Output,t:&str){o.word(t.len()as u32);o.0.extend(t.bytes().map(u32::from));}
fn names(o:&mut Output){for n in 0..384{let mut k=n;let mut c=[0;6];for i in(0..6).rev(){let b=if i==5{6}else if i==4{4}else{2};c[i]=k%b;k/=b;}let name=super::super::grind_chromosome::names::lookup(c).unwrap();o.word(name.skating_id as u32);text(o,name.attribute);text(o,name.display);o.word(name.scorable_id as u32);o.words(skate_core::animation::skeleton_input::name::encode(name.attribute.as_bytes()).0);}for lane in 0..6{let mut c=[0;6];c[lane]=if lane==5{6}else if lane==4{4}else{2};o.word(super::super::grind_chromosome::names::lookup(c).is_some()as u32);}}
pub(super) fn run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut Input,o:&mut Output)->Result<(),String>{
 let graphs=crate::graph_runtime::StockGraphs{action:loaded(&fixtures.join("actor.action.reference"))?,motion:loaded(&fixtures.join("actor.motion.reference"))?};let count=i.word();o.word(count);
 for _ in 0..count{let mut p=GamePhysics::load_with_terrain(assets,super::super::ground::Terrain::Flat)?;p.world=fixture_world(i.word());let provider=read_provider(i);let mut s=SkaterRuntime::load(assets,&graphs,&p,"normal")?;let rows=i.word();o.word(rows);let mut c=collision(&s);let mut teleported=false;let mut actions=Actions::default();live_snapshot(o,&p,&s,&c,teleported,&actions);
 for _ in 0..rows{let op=i.word();o.word(op);let mut extra=Vec::new();let result=match op{
// GENERATED_ORIGINAL_PACKET_RESET_CASES
 6=>{super::super::solve::advance(&mut p,&mut s,[0.;2]).map(|_|super::super::skeleton_feedback::publish(&p,&mut s,false))},
 10=>{let state=skate_core::player::state::PhysicalStateId::try_from(i.word()).unwrap();s.player_state.lifecycle=skate_core::player::lifecycle::PhysicalPlayerStateLifecycle::new(state);super::super::grind::enter(&mut p,&mut s)},
 11=>super::super::grind::exit(&mut p,&mut s),
 12=>{s.player_input.toolkit=Some(s.ground_runtime.prepare_toolkit(&p.board,&s.player_input.processed));Ok(())},
 13=>super::super::grind::advance(&mut p,&mut s),
 14=>super::super::grind::fill(&p,&mut s),
 15=>super::super::grind::condition(&p,&mut s),
 16=>{s.grind_camera.condition_fields(&mut s.player_input.physical.grinds);Ok(())},
 17=>super::super::grind::post(&p,&mut s),
 18=>{s.player_input.toolkit=None;Ok(())},
 19=>{s.grind.migration_grind_clear_manager();Ok(())},
 20=>{s.grind.observe(read_manager(i));Ok(())},
 21=>{s.player_input.grind.jumper=read_jumper(i);Ok(())},
 22=>{let pose=i.word();s.animation.packet.riding_fakie=i.word()!=0;s.player_state.post.jump_fix_frames=i.word();p.trainer.grind_pop=i.float();s.animation.packet.hierarchy=globals(&s,pose)?;Ok(())},
 23=>{for k in 0..i.word(){p.board.forces_mut().append(skate_core::physics::force_queue::QueuedPointForce{tag:k,force_world:Vector3::new(0.137,0.317,0.731),point_body:Vector3::new(-0.731,0.137,0.317)});}Ok(())},
 24=>{let part=i.word()as usize;let value=i.word()as usize;extra.push(super::super::foot_ik::migration_teleport_bone(&mut s.foot_ik,part,value)as u32);Ok(())},
 25=>match super::super::grind::Runtime::filtered_output(&s.player_input.physical.grinds){Err(e)=>Err(e),Ok(output)=>{extra.extend([output.kind as u32,output.scorable_id as u32]);extra.extend(output.name.0);extra.extend(output.scoring_name.0);extra.extend([output.on_front as u32,output.crouch.to_bits(),output.pathed_guid as u32,(output.pathed_guid>>32)as u32,output.local_guid as u32,(output.local_guid>>32)as u32]);Ok(())}},
 26=>{let mut output=Output(Vec::new());super::super::grind::migration_vertical(i,&mut output,&s.grind);extra=output.0;Ok(())},
 27=>{let mut output=Output(Vec::new());names(&mut output);extra=output.0;Ok(())},
 28=>{s.air_reckoning.state.spin_angle=i.float();s.air_reckoning.state.spin_speed=i.float();s.air_reckoning.state.secondary_lean_angle=i.float();Ok(())},
 30=>{let air_counter=i.word()as i32;let air_target=i.word()!=0;let x=&s.animation_input.extra;let frame=super::super::solve::deck_frame(&p.board);let pre=super::super::player_input::grind::PreContext{board:frame,air_counter,tip_state:s.player_input.processed.state_2504,air_targeting_grind_9653:air_target,balance_2720:s.animation_input.fields.balance,translation_2796:x.grind_translation,stability_nudge_2800:x.grind_stability_nudge,up_down_2804:x.grind_up_down,grab_min_height_2808:x.grind_grab_min_height};let post=super::super::player_input::grind::PostContext{board:frame,balance_2720:s.animation_input.fields.balance,translation_2796:x.grind_translation,stability_nudge_2800:x.grind_stability_nudge,up_down_2804:x.grind_up_down,grab_min_height_2808:x.grind_grab_min_height};let mut live=super::super::grind_host::LiveHost{board:&mut p.board,settings:&mut p.settings,materials:&p.grind_materials};s.player_input.grind.pre_update(&s.player_input.processed,&provider,&p.world,pre,&mut live).and_then(|pending|s.player_input.grind.post_update(&mut s.player_input.processed,&p.world,pending,post,&mut live)).map(|result|{s.player_input.grind_observation=Some(result.observation);s.grind.observe(result.observation);extra.push(result.wipeout_reasons.len()as u32);for reason in result.wipeout_reasons{extra.push(reason as u32);s.wipeout.state.request(reason,0.);}})},
 31=>{p.world=fixture_world(i.word());Ok(())},
 34=>p.riding.start_wheel_queries(&p.board,&p.world).and_then(|_|p.riding.finish_wheel_queries()).and_then(|_|p.riding.finish_post_physics(&mut p.board,p.board_wiping_out,s.player_input.processed.flags_2468,s.player_input.processed.timestep_2604)),
 32=>{p.board.forces_mut().clear();Ok(())},
 _=>panic!("grind runtime operation")};c=collision(&s);o.status(result);o.word(extra.len()as u32);o.0.extend(extra);live_snapshot(o,&p,&s,&c,teleported,&actions);
 }
 }Ok(())
}
}
pub(crate) fn migration_grind_runtime_run(a:&std::path::Path,f:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{migration_grind_runtime::run(a,f,i,o)}
