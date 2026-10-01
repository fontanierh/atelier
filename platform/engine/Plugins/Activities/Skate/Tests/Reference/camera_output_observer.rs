// Appended after the entire original physics.rs production prefix. Fixture
// writes target its concrete live owners; publish/snapshot/advance execute the
// complete original production methods, including Ground.output/StaticWorld.
mod migration_camera_output {
use super::*;
use crate::{Input,ReadValue,Observe};
use crate::camera::{CameraAirOutput,CameraOffboardOutput,CameraGrindOutput,CameraPreferences};
use skate_core::{math::{Basis3,Vector3},physics::{drive_frames::RetailAffineTransform,phase::PhysicalOutputSnapshot,board_toolkit::BoardToolkit},player::{state::PhysicalStateId,lifecycle::PhysicalPlayerStateLifecycle}};
// @OWNER_FIXTURE@
// @OWNER_FIXTURE_READ@
fn read_world(input:&mut Input)->skate_core::physics::board_world::BoardWorld {
    let triangles=(0..input.word()).map(|_| {
        let vertices=core::array::from_fn(|_|Vector3::new(input.float(),input.float(),input.float()));
        let fatness=input.float();let edge_cosines=ReadValue::read(input);let flags=input.word();
        let material=skate_core::physics::contact::RetailContactMaterial{static_friction:input.float(),dynamic_friction:input.float(),restitution:input.float()};
        skate_core::physics::board_world::WorldTriangle{triangle:skate_core::physics::world_contact::triangle_from_volume(vertices,fatness,edge_cosines,flags),material,tag:input.word()}
    }).collect();
    skate_core::physics::board_world::BoardWorld::new(triangles)
}

fn vector(value:[f32;3])->Vector3{Vector3::new(value[0],value[1],value[2])}
fn affine(value:[[f32;4];4])->RetailAffineTransform{RetailAffineTransform{basis:Basis3{columns:core::array::from_fn(|c|core::array::from_fn(|j|value[c][j]))},translation:Vector3::new(value[3][0],value[3][1],value[3][2])}}
fn status(output:&mut Vec<u8>,result:Result<(),String>){match result{Ok(())=>1u32.observe(output),Err(error)=>{0u32.observe(output);error.observe(output);}}}
fn loaded(path:&std::path::Path)->Result<crate::graph_runtime::LoadedGraph,String>{
    let source=skate_data::state_graph::StateGraph::load(path).map_err(|e|e.to_string())?;
    let binding=skate_data::state_graph::binding::Binding::from_graph(&source).map_err(|e|e.to_string())?;
    let runtime=crate::graph_runtime::CompiledGraph::from_binding(&binding).map_err(|e|e.to_string())?;
    Ok(crate::graph_runtime::LoadedGraph{source,binding,runtime})
}
fn install(f:&CameraOwnerFixture,p:&mut GamePhysics,s:&mut SkaterRuntime){
    p.ticks=f.ticks;p.board.set_transform(affine(f.board_transform));p.riding.motion.effective_basis=Basis3{columns:f.effective_basis};
    s.animated_skeleton.roots.animation_to_world=f.skeleton_root;
    for (matrix,position) in s.skeleton.record.pose.iter_mut().zip(f.bone_positions){matrix[3]=position;}
    s.player_state.lifecycle=PhysicalPlayerStateLifecycle::new(PhysicalStateId::try_from(f.selected_state).unwrap());s.player_state.state_flags[29]=f.state_flag_81;
    s.player_input.toolkit=f.toolkit_present.then(||BoardToolkit::from_board(&p.board,f.flags_2468,f.deck_speed,f.axis_464,[0.,1.,0.,0.]));
    let processed=&mut s.player_input.processed;processed.flags_2468=f.flags_2468;processed.flags_2472=f.flags_2472;processed.flags_2476=f.flags_2476;processed.flags_2480=f.flags_2480;processed.flags_2484=f.flags_2484;
    processed.state_2508=f.processed_state;processed.category_2512=f.processed_category;processed.state_variant_index_2528=f.state_variant;
    processed.spin_input_2672=f.spin;processed.time_since_last_input_2748=f.input_age;processed.scalar_2652=f.deck_speed;processed.state_timer_2664=f.state_timer;
    processed.vectors_464_480_496_512_528[0]=f.axis_464.map(f32::to_bits);processed.vectors_544_560_592_608[3]=f.velocity_608.map(f32::to_bits);
    let physical=&mut s.player_input.physical;physical.state.state_16=f.physical_state;physical.state.category_12=f.physical_category;physical.state.surface_height_32=f.surface_height;
    physical.reckoning.vector_64=f.centre_of_mass.map(f32::to_bits);physical.reckoning.vector_96=f.reckoning_up.map(f32::to_bits);
    physical.skateboard.vector_80=f.board_velocity.map(f32::to_bits);physical.skateboard.vector_64=f.board_angular_velocity.map(f32::to_bits);physical.ground.vector_96=f.last_ground_up.map(f32::to_bits);
    physical.air.trajectory_apex_0=f.air.apex_0.map(f32::to_bits);physical.air.collision_position_16=f.air.landing_position_16.map(f32::to_bits);physical.air.landing_normal_32=f.air.landing_normal_32.map(f32::to_bits);physical.air.selector_vector_48=f.air.launch_position_48.map(f32::to_bits);physical.air.landing_heading_80=f.air.heading_80.map(f32::to_bits);
    physical.air.time_in_state_176=f.air.time_176;physical.air.collision_time_180=f.air.duration_180;physical.air.time_to_apex_196=f.air.apex_time_196;physical.air.known_air_valid_437=f.air_valid;physical.air.use_air_reckoning_452=f.air_reckoning;physical.air.scalar_184=f.slow_motion_air_duration;
    let off=&mut physical.off_board;off.scalar_92=f.offboard.duration_92;off.scalar_152=f.offboard.time_152;off.scalar_156=f.offboard.apex_time_156;
    off.vector_160=f.offboard.launch_normal_160.map(f32::to_bits);off.vector_176=f.offboard.launch_position_176.map(f32::to_bits);off.vector_192=f.offboard.landing_normal_192.map(f32::to_bits);off.vector_208=f.offboard.landing_position_208.map(f32::to_bits);off.vector_224=f.offboard.heading_224.map(f32::to_bits);off.vector_240=f.offboard.apex_240.map(f32::to_bits);
    off.flag_308=f.offboard.object_held_304;off.hippy_hurdling_317=f.offboard.hurdle_317;off.trajectory_valid_331=f.offboard.use_trajectory_331;off.flag_334=f.offboard.dropping_in_334;
    physical.grinds.direction_0=f.grinds.direction_0.map(f32::to_bits);physical.grinds.camera_target_96=f.grinds.camera_target_96.map(f32::to_bits);physical.grinds.grinding_316=f.grinds.grinding_316;
    physical.scoring.capabilities_204=f.capabilities;physical.animation.profile_148=f.profile;physical.ground.hippy_jumping_322=f.hippy_jump;
    s.animation.migration_set_camera_fixture_flags(f.animation_flags);s.animation.packet.riding_fakie=f.packet_fakie;
    s.animation_input.fields.balance=f.balance;s.animation_input.fields.turn=f.turn;s.animation_input.extra.look_x=f.look[0];s.animation_input.extra.look_y=f.look[1];s.animation_input.output.flags=f.intents;
    s.physical_feedback.conditioned_turn=f.conditioned_turn;s.ground.pumping.pump_acceleration=f.pumping;
    if f.com_reset{s.centre_of_mass_filter.reset();}s.centre_of_mass_output=s.centre_of_mass_filter.update(f.com_input_position,f.com_input_velocity);
    p.exchange=SimulationExchange::new(f.output_tick);
    if f.output_present{p.exchange.publish_output(PhysicalOutputSnapshot{tick:f.output_tick,state:PhysicalStateId::try_from(f.output_state).unwrap(),board_position:vector(f.board_transform[3][..3].try_into().unwrap()),board_linear_velocity:vector(f.board_velocity[..3].try_into().unwrap()),rider_root_position:vector(f.skeleton_root[3][..3].try_into().unwrap()),rider_linear_velocity:Vector3::new(0.,0.,0.),ground_normal:vector(f.ground_normal),contact_count:7,predicted_position:vector(f.predicted_position),grounded:f.physical_category==100,wiping_out:f.flags_2468&(1<<18)!=0,landed:false,events:Vec::new()});}
}
pub(super) fn run(assets:&std::path::Path,fixtures:&std::path::Path,input:&mut Input,output:&mut Vec<u8>,log:&crate::LogSink)->Result<(),String>{
    let graphs=crate::graph_runtime::StockGraphs{action:loaded(&fixtures.join("actor.action.reference"))?,motion:loaded(&fixtures.join("actor.motion.reference"))?};
    let count=input.word();count.observe(output);
    for _ in 0..count{
        let world=read_world(input);let camera_id=input.word();
        let mut physics=GamePhysics::load_with_terrain(assets,ground::Terrain::Flat)?;physics.world=world;
        let mut skater=SkaterRuntime::load(assets,&graphs,&physics,"normal")?;
        let mut camera=crate::camera::CameraRuntime::load(&fixtures.join(format!("camera-{camera_id}")))?;
        let rows=input.word();rows.observe(output);
        for _ in 0..rows{
            let operation=input.word();operation.observe(output);let fixture=CameraOwnerFixture::read(input);install(&fixture,&mut physics,&mut skater);
            let output_snapshot=PhysicalOutputSnapshot{tick:fixture.publication_tick,state:PhysicalStateId::try_from(fixture.selected_state).unwrap(),board_position:Vector3::new(0.,0.,0.),board_linear_velocity:Vector3::new(0.,0.,0.),rider_root_position:Vector3::new(0.,0.,0.),rider_linear_velocity:Vector3::new(0.,0.,0.),ground_normal:vector(fixture.ground_normal),contact_count:0,predicted_position:vector(fixture.predicted_position),grounded:false,wiping_out:false,landed:false,events:Vec::new()};
            let pref=&fixture.preferences;
            let mut publication=camera_output::publish(&skater,&output_snapshot,&skater.physical_feedback,skater.centre_of_mass_output,CameraPreferences{invert_look:pref.invert_look,shake_variant:pref.shake_variant,value_32:pref.value_32},u8::from(skater.animation.stance().1),fixture.context,fixture.publication_tick)?;
            if operation==2{publication.events.broken_bone_duration_200=fixture.override_broken_duration;publication.ground_scalar_288=fixture.override_ground_scalar;}
            publication.observe(output);
            match crate::camera::publish_camera_subject(&physics,&skater,&publication){Ok(snapshot)=>{status(output,Ok(()));snapshot.observe(output);},Err(error)=>status(output,Err(error))};
            if operation==1{status(output,camera_output::advance(&physics,&skater,&skater.physical_feedback,&mut camera));}
            crate::camera::migration_output_observe(&camera,output,log);
            skater.centre_of_mass_output.velocity.observe(output);skater.centre_of_mass_output.acceleration.observe(output);skater.centre_of_mass_output.position.observe(output);
        }
        log.0.lock().unwrap().clear();
    }Ok(())
}
}
pub(crate) fn migration_camera_output_run(assets:&std::path::Path,fixtures:&std::path::Path,input:&mut crate::Input,output:&mut Vec<u8>,log:&crate::LogSink)->Result<(),String>{migration_camera_output::run(assets,fixtures,input,output,log)}
