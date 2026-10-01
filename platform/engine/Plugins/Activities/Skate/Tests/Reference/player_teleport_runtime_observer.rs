// Appended in input_phase's original privacy scope. Calls the complete unchanged
// Callbacks::reset_player. Fixtures are initial state / caller packet inputs.
mod migration_player_teleport {
use super::*;
use crate::{Input,Output};
use skate_core::{math::{Vector3,Basis3},physics::{skeleton_animation_record::IDENTITY,skeleton_body::{SkeletonCollisionSettings,SkeletonContactFlags},board_world::{BoardWorld,WorldTriangle},world_contact::triangle_from_volume,contact::RetailContactMaterial}};
fn block(o:&mut Output,f:impl FnOnce(&mut Output)){let at=o.0.len();o.word(0);f(o);o.0[at]=(o.0.len()-at-1)as u32;}
fn probe_floats<const N:usize>(out:&mut Vec<u32>,v:[f32;N]){out.extend(v.map(f32::to_bits));}
fn probe_vector(out:&mut Vec<u32>,v:Vector3){probe_floats(out,[v.x,v.y,v.z]);}
fn probe_matrix(out:&mut Vec<u32>,m:[[f32;4];4]){for v in m{probe_floats(out,v)}}
fn probe_basis(out:&mut Vec<u32>,b:Basis3){for v in b.columns{probe_floats(out,v)}}
// GENERATED_COLLISION_OBSERVERS
// GENERATED_RIDING_OBSERVER
fn toolkit(o:&mut Output,t:&BoardToolkit){for m in [t.deck,t.effective,t.inverse_effective]{o.matrix(m)}for v in [t.side,t.up,t.forward,t.horizontal_forward,t.transverse_up,t.forward_velocity,t.travel_direction,t.filtered_normal]{o.floats(v)}o.floats([t.absolute_speed,t.control_sign,t.total_mass]);}
fn collision_out(o:&mut Output,c:&CollisionInput){o.word(c.contact_4070 as u32);o.word(c.has_pose_error_4077 as u32);o.floats(c.pose_error_16272);o.word(c.partial_ragdoll as u32);o.float(c.drive_weight_4028);}
fn snapshot(o:&mut Output,p:&GamePhysics,s:&SkaterRuntime,c:&CollisionInput,teleported:bool,actions:&Actions){
 o.word(9);
 block(o,|o|{crate::observe_PlayerInputState(o,&s.player_input.player);crate::observe_PhysicalPlayerInput(o,&s.player_input.physical);crate::observe_ProcessedPhysicsInput(o,&s.player_input.processed);o.word(s.player_input.toolkit.is_some()as u32);if let Some(t)=s.player_input.toolkit{toolkit(o,&t)}});
 block(o,|o|super::super::ground_runtime::migration_teleport_observe(o,&s.ground,&s.ground_runtime));
 block(o,|o|{let l=&s.ground_lifecycle;let a=&l.skeleton_controller;o.words([a.effective,a.requested,a.has_request as u32,a.override_enabled as u32,a.flag_18 as u32,l.skeleton_elapsed_16505 as u32,l.board_animated_290 as u32]);o.float(l.manual_drag_2724);let w=&s.skeleton_output.wobble;o.words([w.active as u32,w.landing as u32]);o.floats([w.time,w.amplitude,w.direction]);o.word(w.migration_teleport_selected()as u32);let a=&s.skeleton_input;o.words([a.reenable_requested as u32,a.teleporting as u32,a.force_mode]);for v in a.head_tracking_history{o.floats(v)}o.words([a.head_tracking_active as u32,a.grind_air_started as u32,a.grind_air_active as u32,a.grind_air_adjusting as u32]);o.words(a.grind_air.migration_teleport_words());super::super::animation_input::migration_teleport_observe(o,&s.animation_input);o.word(actions.calls.len()as u32);o.0.extend(&actions.calls);});
 block(o,|o|{collision_mode(&mut o.0,&s.skeleton_collision);collision_feedback(&mut o.0,&s.collision_feedback);});
 block(o,|o|super::super::biped_ground::grab_runtime::migration_teleport_observe(&mut o.0,&s.offboard_grab));
 block(o,|o|{super::super::footplant::migration_teleport_observe(o,&s.footplant);let w=&s.wipeout.state;o.words(w.reasons.map(u32::from));o.floats(w.values);o.word(w.count);o.float(w.cooldown);o.word(w.contact_frames as u32);o.float(w.balance);o.word(w.mode);collision_out(o,c);o.word(teleported as u32);});
 block(o,|o|super::super::handplant::migration_footplant_shared_snapshot(o,p,s));
 block(o,|o|{riding_out(&mut o.0,&p.riding);o.word(p.board_wiping_out as u32);o.word(p.board.collision_group());o.word(p.board.forces().entries().len()as u32);for f in p.board.forces().entries(){o.word(f.tag);probe_vector(&mut o.0,f.force_world);probe_vector(&mut o.0,f.point_body)}});
 block(o,|o|p.riding.migration_teleport_queries(o));
}
#[derive(Default)]struct Actions{values:[f32;18],calls:Vec<u32>}
impl skate_core::input::controller::ActionMap for Actions{fn value(&mut self,a:u32)->f32{self.calls.push(a);self.values[(a-64)as usize]}fn state(&mut self,a:u32)->u8{(self.value(a)!=0.)as u8}}
fn loaded(path:&std::path::Path)->Result<crate::graph_runtime::LoadedGraph,String>{let source=skate_data::state_graph::StateGraph::load(path).map_err(|e|e.to_string())?;let binding=skate_data::state_graph::binding::Binding::from_graph(&source).map_err(|e|e.to_string())?;let runtime=crate::graph_runtime::CompiledGraph::from_binding(&binding).map_err(|e|e.to_string())?;Ok(crate::graph_runtime::LoadedGraph{source,binding,runtime})}
fn globals(s:&SkaterRuntime,kind:u32)->Result<Vec<NativeMatrix>,String>{if kind==4{return Ok(Vec::new())}let names=["RIG_TPOSE","POSTURE_STIFF_POSE","POSTURE_SLOUCH_POSE","POSTURE_BUFF_POSE"];let e=&s.animation.evaluator;let mut result=e.hierarchy(&e.evaluate(&[skate_core::animation::playback_tree::PoseCommand::Pose{name:names[if kind==5{0}else{kind as usize}].into()}])?)?;if kind==5{result.truncate(1)}Ok(result)}
pub(super) fn run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut Input,o:&mut Output)->Result<(),String>{
 let graphs=crate::graph_runtime::StockGraphs{action:loaded(&fixtures.join("actor.action.reference"))?,motion:loaded(&fixtures.join("actor.motion.reference"))?};let count=i.word();o.word(count);
 for _ in 0..count{let mut p=GamePhysics::load_with_terrain(assets,super::super::ground::Terrain::Flat)?;p.world=world(i);let mut s=SkaterRuntime::load(assets,&graphs,&p,"normal")?;let rows=i.word();o.word(rows);let mut c=collision(&s);let mut teleported=false;let mut actions=Actions::default();snapshot(o,&p,&s,&c,teleported,&actions);
 for _ in 0..rows{let op=i.word();o.word(op);let mut extra=Vec::new();let result=match op{
 0=>{s.player_input.player=crate::read_PlayerInputState(i);s.player_input.physical=crate::read_PhysicalPlayerInput(i);s.player_input.processed=crate::read_ProcessedPhysicsInput(i);Ok(())},
 1=>{let requested=i.matrix();let publication=crate::read_AnimationPacketFields(i);let external=crate::read_ExternalPhysicsInput(i);let packet=crate::read_packet(i,&publication,&external);let kind=i.word();let n=i.word();let attrs=(0..n).map(|_|i.attribute()).collect::<Vec<_>>();actions.values=i.floats();actions.calls.clear();teleported=i.word()!=0;let globals=globals(&s,kind)?;c=collision(&s);let mut callbacks=Callbacks{
 // GENERATED_ORIGINAL_CALLBACK_BINDINGS
 };let r=callbacks.reset_player(&mut p.board,&mut s.ground_runtime,requested,&mut s.player_input.player,&mut s.player_input.physical,&mut s.player_input.processed);c=callbacks.collision;teleported=callbacks.teleported;r},
 2=>{let seed=i.word();let override_enabled=i.word()!=0;let life=&mut s.ground_lifecycle;life.skeleton_controller.override_enabled=override_enabled;life.skeleton_controller.requested=3;life.skeleton_controller.has_request=true;life.skeleton_controller.effective=if seed%3==0{5}else{3};life.skeleton_controller.flag_18=true;life.skeleton_elapsed_16505=false;life.board_animated_290=173;life.manual_drag_2724=0.317;s.ground.entered=seed&1!=0;s.ground.steering.update(0.731,0.137,0x2000,0);s.ground.steering.activation_time=[0.317,0.731];s.ground_runtime.retained_board_normal=[0.317,0.731,-0.137,-0.];p.board_wiping_out=true;s.skeleton_output.wobble.trigger(seed&1!=0,seed&2!=0);s.skeleton_input.reenable_requested=false;s.skeleton_input.force_mode=seed+7;s.skeleton_input.head_tracking_active=true;s.skeleton_input.head_tracking_history=[[0.137,0.317,0.731,-0.];8];s.collision_pose_error=[0.137,0.317,0.731,-0.];s.wipeout.state.enter_ground();s.wipeout.state.request(2,0.137);s.wipeout.state.request(24,0.731);s.offboard_grab.migration_teleport_initial(seed,0xc0);let v=[0.137,0.731,-0.317,0.];let velocity=[2.731,0.137,0.317,0.];s.footplant.enabled=true;super::super::footplant::migration_teleport_start(&mut s.footplant,v,velocity);super::super::handplant::migration_teleport_start(&mut s.handplant);p.board.forces_mut().append(skate_core::physics::force_queue::QueuedPointForce{tag:seed,force_world:Vector3::new(0.137,0.317,0.731),point_body:Vector3::new(-0.731,0.137,0.317)});s.player_input.toolkit=Some(s.ground_runtime.prepare_toolkit(&p.board,&s.player_input.processed));c=collision(&s);Ok(())},
 6=>{super::super::solve::advance(&mut p,&mut s,[0.;2]).map(|_|{super::super::skeleton_feedback::publish(&p,&mut s,false);c=collision(&s);})},
 5=>{let part=i.word()as usize;let value=i.word()as usize;extra.push(super::super::foot_ik::migration_teleport_bone(&mut s.foot_ik,part,value)as u32);Ok(())},
 3=>{let requested=i.matrix();extra.extend(teleport::migration_player_teleport_horizontal(requested).into_iter().flatten().map(f32::to_bits));Ok(())},
 4=>{p.riding.start_wheel_queries(&p.board,&p.world).and_then(|_|p.riding.probes.start(&p.board,&p.world))},
 _=>panic!("teleport operation")};o.status(result);o.word(extra.len()as u32);o.0.extend(extra);snapshot(o,&p,&s,&c,teleported,&actions);
 }
 }Ok(())
}
}
pub(crate) fn migration_player_teleport_run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{migration_player_teleport::run(assets,fixtures,i,o)}
