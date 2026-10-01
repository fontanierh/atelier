// Appended after the complete frozen physics/handplant.rs prefix. The fixture
// setter writes actual owner fields; every invoked numerical body is original.
mod migration {
use super::*;
use crate::{Input,Output};
use skate_core::physics::{grind_contact::Primitive,board_world::{BoardWorld,WorldTriangle},world_contact::triangle_from_volume,contact::RetailContactMaterial};
use skate_core::math::Vector3;
fn trajectory(i:&mut Input)->Trajectory{Trajectory{position:i.floats(),velocity:i.floats(),acceleration:i.floats(),duration:i.float()}}
fn candidate(i:&mut Input)->contact::Candidate{contact::Candidate{point:i.floats(),edge:Primitive{start:i.floats(),end:i.floats(),owner:i.wide()},side:i.word()as i32}}
fn out_candidate(o:&mut Output,c:contact::Candidate){o.floats(c.point);o.floats(c.edge.start);o.floats(c.edge.end);o.wide(c.edge.owner);o.word(c.side as u32)}
fn out_trajectory(o:&mut Output,t:Trajectory){o.floats(t.position);o.floats(t.velocity);o.floats(t.acceleration);o.float(t.duration)}
fn settings(o:&mut Output,s:&Settings){for g in &s.window{o.floats(g.x);o.floats(g.y)}o.floats([s.depth,s.window_drop]);for g in [&s.time_warp,&s.out_heading,&s.into_rotation,&s.out_rotation]{o.floats(g.x);o.floats(g.y)}o.floats(s.hand_radius.x);o.floats(s.hand_radius.y);o.floats([s.curve_half_time,s.entry_blend,s.hand_out,s.hand_into,s.hand_release,s.minimum_speed,s.minimum_slope,s.rotation_time,s.committed_time,s.minimum_out_speed,s.hand_approach]);o.word(s.direction_frames as u32);o.floats([s.apex_radius,s.apex_angle]);o.floats(s.animation);o.float(s.truck_distance)}
fn seed(i:&mut Input,h:&mut Handplant){h.flags=i.word();h.phase=i.float();h.anchor=i.floats();h.previous_candidate_point=i.floats();h.pending=if i.word()!=0{Some((candidate(i),i.floats(),i.floats(),i.floats(),i.floats()))}else{None};h.candidate=if i.word()!=0{Some(candidate(i))}else{None};h.initial=trajectory(i);h.entry=trajectory(i);h.outgoing=core::array::from_fn(|_|trajectory(i));h.curve=core::array::from_fn(|_|i.floats());h.rotations=core::array::from_fn(|_|i.matrix());h.direction=i.floats();h.travel_sign=i.float();h.elapsed=i.float();h.warped=i.float();h.apex=i.float();h.estimated_phase=i.float();h.out_duration=i.float();h.continuation=i.word()!=0;h.direction_hint=i.word()as i32;h.direction_count=i.word()as i32;h.ik_blend=i.float();h.ik_distance=i.float();h.ik_released=i.word()!=0;h.ik_latched=i.word()!=0;}
fn owner(o:&mut Output,h:&Handplant){o.word(h.flags);o.float(h.phase);o.floats(h.anchor);o.floats(h.previous_candidate_point);o.word(h.pending.is_some()as u32);if let Some((c,a,b,d,e))=h.pending{out_candidate(o,c);for v in [a,b,d,e]{o.floats(v)}}o.word(h.candidate.is_some()as u32);if let Some(c)=h.candidate{out_candidate(o,c)}for t in [h.initial,h.entry,h.outgoing[0],h.outgoing[1]]{out_trajectory(o,t)}for v in h.curve{o.floats(v)}for m in h.rotations{o.matrix(m)}o.floats(h.direction);o.floats([h.travel_sign,h.elapsed,h.warped,h.apex,h.estimated_phase,h.out_duration]);o.word(h.continuation as u32);o.word(h.direction_hint as u32);o.word(h.direction_count as u32);o.floats([h.ik_blend,h.ik_distance]);o.word(h.ik_released as u32);o.word(h.ik_latched as u32);}
fn effects(o:&mut Output,s:&SkaterRuntime){for limb in s.foot_ik.state.limbs{o.word(limb.external_target_set as u32);o.float(limb.target_blend);}for target in s.foot_ik.state.external_targets{o.floats(target.world_position);}o.word(s.skeleton_collision.pending_reenable as u32);for n in s.skeleton_collision.disable_count{o.word(n)}for p in s.skeleton_collision.parts{o.word(p.enabled as u32)}o.word(s.ground_lifecycle.board_animated_290 as u32);}
fn world(i:&mut Input)->BoardWorld{let triangles=(0..i.word()).map(|_|{let vertices=core::array::from_fn(|_|Vector3::new(i.float(),i.float(),i.float()));let fatness=i.float();let edge_cosines=i.floats();let flags=i.word();let material=RetailContactMaterial{static_friction:i.float(),dynamic_friction:i.float(),restitution:i.float()};WorldTriangle{triangle:triangle_from_volume(vertices,fatness,edge_cosines,flags),material,tag:i.word()}}).collect();BoardWorld::new(triangles)}
// Explicit caller-authored static scene metadata, not inferred from tags.
fn authored_query_world(i:&mut Input)->BoardWorld{
 use skate_core::physics::board_world::query_metadata::{Bounds,QueryMesh,QueryMetadata,QueryPool};
 use skate_core::physics::drive_frames::RetailAffineTransform;
 let source=world(i);
 let packed_surfaces=(0..i.word()).map(|_|i.word()as u16).collect();
 let meshes=(0..i.word()).map(|_|{let start=i.word()as usize;let end=i.word()as usize;let min=i.floats::<3>();let max=i.floats::<3>();let matching_group=i.word()as i32;let rejection_flags=i.word();let geometry=i.word();let pool=match i.word(){0=>QueryPool::Ground,1=>QueryPool::Island,2=>QueryPool::Conditional,_=>panic!("fixture pool")};QueryMesh{triangle_range:start..end,local_to_world:RetailAffineTransform::IDENTITY,world_to_local:RetailAffineTransform::IDENTITY,local_bounds:Bounds{min:Vector3::new(min[0],min[1],min[2]),max:Vector3::new(max[0],max[1],max[2])},matching_group,rejection_flags,geometry,pool}}).collect();
 BoardWorld::with_query_metadata(source.triangles().to_vec(),QueryMetadata{packed_surfaces,meshes,static_edges:vec![],island_flags:i.word()}).unwrap()
}
fn loaded(path:&std::path::Path)->Result<crate::graph_runtime::LoadedGraph,String>{let source=skate_data::state_graph::StateGraph::load(path).map_err(|e|e.to_string())?;let binding=skate_data::state_graph::binding::Binding::from_graph(&source).map_err(|e|e.to_string())?;let runtime=crate::graph_runtime::CompiledGraph::from_binding(&binding).map_err(|e|e.to_string())?;Ok(crate::graph_runtime::LoadedGraph{source,binding,runtime})}
pub(super) fn run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut Input,o:&mut Output)->Result<(),String>{
 let graphs=crate::graph_runtime::StockGraphs{action:loaded(&fixtures.join("actor.action.reference"))?,motion:loaded(&fixtures.join("actor.motion.reference"))?};let count=i.word();o.word(count);
 for _ in 0..count{
  let mut physics=GamePhysics::load_with_terrain(assets,super::super::ground::Terrain::Flat)?;physics.world=world(i);
  let edges=(0..i.word()).map(|_|Primitive{start:i.floats(),end:i.floats(),owner:i.wide()}).collect();physics.grind_world=std::sync::Arc::new(crate::grind_world::migration_handplant_primitives(edges));
  let mut skater=SkaterRuntime::load(assets,&graphs,&physics,"normal")?;settings(o,&skater.handplant.settings);let rows=i.word();o.word(rows);owner(o,&skater.handplant);effects(o,&skater);
  for _ in 0..rows{let op=i.word();o.word(op);match op{
   0=>seed(i,&mut skater.handplant),1=>skater.handplant.reset(),2=>skater.handplant.full_reset(),
   3=>{let p=&mut skater.player_input.processed;p.flags_2476=i.word();p.flags_2480=i.word();p.actor_query_2948=i.word();p.actor_query_2952=i.word();p.vectors_544_560_592_608[2]=i.floats::<4>().map(f32::to_bits);p.vectors_400_416[0]=i.floats::<4>().map(f32::to_bits);p.vectors_464_480_496_512_528[0]=i.floats::<4>().map(f32::to_bits);p.vectors_544_560_592_608[1]=i.floats::<4>().map(f32::to_bits);physics.riding.reckoning_frames.heading=i.floats();ground_query(&physics,&mut skater);},
   4=>o.status(ground_update(&mut physics,&mut skater)),
   5=>{let c=candidate(i);let com=i.floats();let v=i.floats();let n=i.floats();let body=i.floats();let heading=i.floats();skater.handplant.launch(c,com,v,n,body,heading)},
   6=>{let pose:[[V;4];24]=core::array::from_fn(|_|i.matrix());let com=i.floats();let(a,b,c)=skater.handplant.values(&pose,com);o.floats(a);o.floats(b);o.floats(c)},
   7=>{let ground=i.word()!=0;skater.player_input.processed.flags_2476=i.word();skater.player_input.processed.flags_2480=i.word();skater.animated_skeleton.roots.animation_to_world=i.matrix();skater.animated_skeleton.record.pose=core::array::from_fn(|_|i.matrix());skater.animated_skeleton.targets=core::array::from_fn(|_|i.matrix());ik::update(&mut skater,ground)},
   8=>{skater.handplant.settings.time_warp.x=i.floats();skater.handplant.settings.time_warp.y=i.floats()},
   9=>{let right=i.word()!=0;let position=i.floats();let frames=i.word();plant_skeleton::hold_foot(&mut skater,right,position,frames)},
   10=>skater.handplant.migration_build_curve(),11=>skater.handplant.estimate_apex(),
   12=>{let heading=i.floats();let up=i.floats();o.matrix(rotation::frame(heading,up))},
   13=>{let a=i.matrix();let b=i.matrix();let weight=i.float();o.matrix(rotation::blend(a,b,weight))},
   14=>{assert!(skater.handplant.candidate.is_none());o.status(enter(&mut physics,&mut skater))},
   15=>{let a=i.floats();let b=i.floats();let s=i.float();let maximum=i.float();let m=i.matrix();o.float(dot(a,b));o.floats(cross(a,b));o.floats(add(a,b));o.floats(sub(a,b));o.floats(scale(a,s));o.floats(madd(a,s,b));o.float(reciprocal(s));o.float(length(a));o.floats(normalize(a));o.floats(point(&m,a));o.floats(rotate(&m,a));o.floats(clamp_length(a,maximum));o.float(clamp01(s));},
   16=>physics.world=authored_query_world(i),
   _=>panic!("handplant operation")
  }owner(o,&skater.handplant);effects(o,&skater);}
 }Ok(())
}
}
pub(crate) fn migration_handplant_run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{migration::run(assets,fixtures,i,o)}
