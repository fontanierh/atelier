// Append-only observation and caller transport. All original bodies unchanged.
mod migration_wipeout_physical {
// GENERATED_ORIGINAL_OWNER_PREFIX
fn wipeout_world(i:&mut Input)->BoardWorld{use skate_core::physics::{board_world::query_metadata::{QueryMetadata,QueryMesh,QueryPool,Bounds},drive_frames::RetailAffineTransform};let mut triangles=Vec::new();let mut surfaces=Vec::new();for _ in 0..i.word(){let vertices=std::array::from_fn(|_|Vector3::new(i.float(),i.float(),i.float()));let fatness=i.float();let edges=i.floats();let flags=i.word();let material=RetailContactMaterial{static_friction:i.float(),dynamic_friction:i.float(),restitution:i.float()};let tag=i.word();surfaces.push(i.word()as u16);triangles.push(WorldTriangle{triangle:triangle_from_volume(vertices,fatness,edges,flags),material,tag});}let mut meshes=Vec::new();if !triangles.is_empty(){meshes.push(QueryMesh{triangle_range:0..triangles.len(),local_to_world:RetailAffineTransform::IDENTITY,world_to_local:RetailAffineTransform::IDENTITY,local_bounds:Bounds{min:Vector3::new(-100.,-100.,-100.),max:Vector3::new(100.,100.,100.)},matching_group:-1,rejection_flags:u32::MAX,geometry:77,pool:QueryPool::Ground});}BoardWorld::with_query_metadata(triangles,QueryMetadata{packed_surfaces:surfaces,meshes,static_edges:Vec::new(),island_flags:3}).unwrap()}
fn live_snapshot(o:&mut Output,p:&GamePhysics,s:&SkaterRuntime,c:&CollisionInput,teleported:bool,actions:&Actions){o.word(3);block(o,|o|snapshot(o,p,s,c,teleported,actions));block(o,|o|super::super::wipeout_states::migration_owner(o,&s.wipeout_state));block(o,|o|super::super::wipeout_states::migration_settings(o,&s.wipeout_state));}
pub(super) fn run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut Input,o:&mut Output)->Result<(),String>{
 let graphs=crate::graph_runtime::StockGraphs{action:loaded(&fixtures.join("actor.action.reference"))?,motion:loaded(&fixtures.join("actor.motion.reference"))?};let count=i.word();o.word(count);
 for _ in 0..count{let mut p=GamePhysics::load_with_terrain(assets,super::super::ground::Terrain::Flat)?;p.world=wipeout_world(i);let mut s=SkaterRuntime::load(assets,&graphs,&p,"normal")?;let rows=i.word();o.word(rows);let mut c=collision(&s);let mut teleported=false;let mut actions=Actions::default();live_snapshot(o,&p,&s,&c,teleported,&actions);
 for _ in 0..rows{let op=i.word();o.word(op);let mut extra=Vec::new();let result=match op{
// GENERATED_ORIGINAL_PACKET_RESET_CASES
 6=>super::super::solve::advance(&mut p,&mut s,[0.;2]).map(|_|super::super::skeleton_feedback::publish(&p,&mut s,false)),
 10=>super::super::wipeout_states::enter(&mut p,&mut s),11=>{super::super::wipeout_states::exit(&mut p,&mut s);Ok(())},
 12=>{s.player_input.toolkit=Some(s.ground_runtime.prepare_toolkit(&p.board,&s.player_input.processed));Ok(())},
 13=>super::super::wipeout_states::advance(&mut p,&mut s),
 14=>{let mut e=Output(Vec::new());crate::observe_wipeout_Output(&mut e,&super::super::wipeout_states::fill(&s));extra=e.0;Ok(())},
 17=>{super::super::wipeout_states::post_physics(&mut s);Ok(())},18=>{s.player_input.toolkit=None;Ok(())},
 21=>{s.wipeout_state.state=crate::read_wipeout_State(i);Ok(())},
 22=>{let pose=i.word();s.animation.packet.hierarchy=globals(&s,pose)?;s.animation_input.extra.wipeout_control=i.floats();s.animation_input.extra.wipeout_gesture=i.floats();Ok(())},
 24=>{let part=i.word()as usize;let value=i.word()as usize;extra.push(super::super::foot_ik::migration_teleport_bone(&mut s.foot_ik,part,value)as u32);Ok(())},
 31=>{p.world=wipeout_world(i);Ok(())},
 34=>p.riding.start_wheel_queries(&p.board,&p.world).and_then(|_|p.riding.finish_wheel_queries()).and_then(|_|p.riding.finish_post_physics(&mut p.board,p.board_wiping_out,s.player_input.processed.flags_2468,s.player_input.processed.timestep_2604)),
 35=>{let request=i.word();s.ground_lifecycle.skeleton_controller.override_enabled=i.word()!=0;s.wipeout_state.ragdoll.request(&mut s.ground_lifecycle.skeleton_controller,request,&mut s.skeleton,&mut s.skeleton_joints,&mut s.skeleton_collision)},
 36=>{s.wipeout_state.ragdoll.restore_normal(&mut s.skeleton,&mut s.skeleton_joints,&mut s.skeleton_collision,&mut s.collision_feedback);Ok(())},
 37=>{let part=i.word()as usize;let v=i.floats::<3>();s.skeleton.bodies_mut()[part].rates.linear_velocity=Vector3::new(v[0],v[1],v[2]);Ok(())},
 38=>{s.wipeout.state.request(i.word()as usize,i.float());Ok(())},
 39=>{let v=i.floats::<3>();for part in s.skeleton.bodies_mut(){part.rates.position.x+=v[0];part.rates.position.y+=v[1];part.rates.position.z+=v[2];}s.skeleton.publish_physical_record(super::super::solve::deck_frame(&p.board));Ok(())},
 _=>panic!("wipeout physical operation")};c=collision(&s);o.status(result);o.word(extra.len()as u32);o.0.extend(extra);live_snapshot(o,&p,&s,&c,teleported,&actions);
 }
 }Ok(())
}
}
pub(crate) fn migration_wipeout_physical_run(a:&std::path::Path,f:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{migration_wipeout_physical::run(a,f,i,o)}
