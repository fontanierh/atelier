// Full original active host Owner/Effects/runtime source is aliased unchanged.
use skate_core::{math::{Vector3,Basis3},physics::{assembly::BodySnapshot,contact::RetailContactMaterial,board::BodyId,board_runtime::{BoardRuntime,BoardMotion},rigid_body::*,drive_frames::*,mass::{default_skateboard_mass_properties,DeckGeometry,DeckGeometrySettings},board_ground::{BoardGroundState,WheelLineState},skeleton_animation_record::{compose_affine,AnimationPartTransform},drive_solver::RetailDriveRows}};
use skate_core::player::lifecycle::SkateboardControllerActions;
use skate_core::physics::{solver::{packed,JointConstraint},contact_solver::RetailContactJacobian};
mod math {pub use skate_core::math::*;}
#[path="../../crates/skate-core/src/physics/solver/packing.rs"]mod packing;
mod physics {
 pub use skate_core::physics::*;
 use super::*;
 pub struct ProbeSettings{pub standard_wheel_material:RetailContactMaterial,pub wheel_material:RetailContactMaterial,pub truck_material:RetailContactMaterial,pub deck_material:RetailContactMaterial,pub truck_collisions:bool,pub deck_geometry:DeckGeometry}
 pub struct Riding{pub ground:BoardGroundState,pub wheel_lines:WheelLineState}
 pub struct GamePhysics{pub settings:ProbeSettings,pub board:BoardRuntime,pub board_wiping_out:bool,pub riding:Riding}
 pub struct ProbeProcessed{pub effective_anim_transform_192:[[u32;4];4],pub vectors_544_560_592_608:[[u32;4];4],pub vectors_880_896_912_928_944:[[u32;4];5],pub vectors_400_416:[[u32;4];2],pub vectors_464_480_496_512_528:[[u32;4];5],pub flags_2476:u32,pub flags_2480:u32,pub flags_2488:u32,pub timestep_2604:f32}
 pub struct Toolkit{pub deck:Frame}
 #[derive(Default)]pub struct Offboard{pub angle_36:f32,pub angle_40:f32,pub flag_311:u8,pub free_board_312:u8,pub returning_board_313:u8,pub hiding_board_321:u8,pub dropping_board_322:u8,pub retrieving_board_323:u8,pub flag_324:u8}
 pub struct Physical{pub off_board:Offboard}
 pub struct PlayerInput{pub processed:ProbeProcessed,pub toolkit:Option<Toolkit>,pub physical:Physical}
 pub struct SkeletonInput{pub drive_frames:[Frame;24]}
 pub struct Skeleton{pub record:skate_core::physics::skeleton_body::SkeletonPhysicalRecord,pub bodies:[BodySnapshot;26]}
 #[derive(Clone,Copy,Default)]pub struct Bone{pub groups:[bool;4]}
 pub struct Feedback{pub bones:[Bone;24]}
 pub struct Animated{pub roots:skate_core::physics::skeleton_root::SkeletonRootFrames}
 pub struct Controller{pub fields:SkateboardControllerFields}
 pub struct GroundLifecycle{pub board_animated_290:u8}
 pub struct SkaterRuntime{pub player_input:PlayerInput,pub skeleton_input:SkeletonInput,pub skeleton:Skeleton,pub collision_feedback:Feedback,pub animated_skeleton:Animated,pub skateboard_controller:Controller,pub ground_lifecycle:GroundLifecycle,pub board_possession:offboard::board_manager::Owner,pub board_possession_live:offboard::board_manager::runtime::LiveState}
 pub mod solve {
  use super::*;
  // The checker inserts the unchanged original deck_frame function here.
  __DECK_FRAME__
 }
 pub mod offboard{
  #[path="board_possession/mod.rs"]pub mod board_possession;
  #[path="board_manager/mod.rs"]pub mod board_manager;
 }
}
use physics::{GamePhysics,SkaterRuntime,offboard::{board_manager::{self,Owner,Transition},board_possession::{self,Effects as LiveEffects}}};
const MATERIAL:RetailContactMaterial=RetailContactMaterial{static_friction:0.,dynamic_friction:0.,restitution:0.};
impl Input {
 fn v3(&mut self)->Vector3{Vector3::new(self.float(),self.float(),self.float())}
 fn b3(&mut self)->Basis3{Basis3{columns:std::array::from_fn(|_|std::array::from_fn(|_|self.float()))}}
 fn affine(&mut self)->RetailAffineTransform{RetailAffineTransform{basis:self.b3(),translation:self.v3()}}
 fn simulation(&mut self)->RetailSimulationStep{RetailSimulationStep{time_step:self.float(),frequency:self.float(),cool_down:self.word(),minimum_energy:self.float(),gravity_acceleration:self.v3()}}
 fn material(&mut self)->RetailContactMaterial{RetailContactMaterial{static_friction:self.float(),dynamic_friction:self.float(),restitution:self.float()}}
 fn body(&mut self)->BodySnapshot{BodySnapshot{state_flags:self.word(),rates:RetailBodyRates{orientation:RetailQuaternion{x:self.float(),y:self.float(),z:self.float(),w:self.float()},basis:self.b3(),world_inverse_inertia:self.b3(),position:self.v3(),linear_velocity:self.v3(),angular_velocity:self.v3(),force_acceleration:self.v3(),torque_acceleration:self.v3(),kinetic_energy:self.float(),cool_down:self.word()},inertia:RetailInertiaDynamics{inverse_tensor:self.v3(),inverse_mass:self.float(),spherical:self.float(),maximum_linear_velocity:self.float(),maximum_angular_velocity:self.float(),linear_drag:self.float(),angular_drag:self.float()}}}
 fn observe(&mut self,p:&mut GamePhysics,s:&mut SkaterRuntime){
  let o=self.observation();let v=o.processed;let input=&mut s.player_input.processed;input.effective_anim_transform_192=v.player_frame_192.map(|v|v.map(f32::to_bits));input.vectors_544_560_592_608[2]=v.position_592.map(f32::to_bits);input.vectors_880_896_912_928_944[2]=v.velocity_912.map(f32::to_bits);input.vectors_400_416[0]=v.direction_400.map(f32::to_bits);input.vectors_464_480_496_512_528[0]=v.hide_direction_464.map(f32::to_bits);input.flags_2476=v.flags_2476;input.flags_2480=v.flags_2480;input.flags_2488=v.flags_2488;
  p.riding.ground.collision_flags=o.board_collision_flags_872;s.skeleton.record.pose[3][3]=o.physical_hand_positions[0];s.skeleton.record.pose[7][3]=o.physical_hand_positions[1];s.collision_feedback.bones[3].groups[3]=o.hand_contacts[0];s.collision_feedback.bones[7].groups[3]=o.hand_contacts[1];s.skeleton_input.drive_frames[0]=o.animation_board_frame_12624;s.skeleton_input.drive_frames[3]=o.animation_hand_frames[0];s.skeleton_input.drive_frames[7]=o.animation_hand_frames[1];s.animated_skeleton.roots.animation_to_world=self.matrix();s.skeleton_input.drive_frames[11]=self.matrix();s.player_input.toolkit=if self.word()!=0{Some(physics::Toolkit{deck:self.matrix()})}else{None};
  p.riding.wheel_lines.physics_surfaces=std::array::from_fn(|_|self.word());for part in &mut p.riding.ground.parts{part.in_contact=self.word()!=0;part.normal=self.v3();}
 }
}
fn vector3(out:&mut Vec<u32>,v:Vector3){floats(out,[v.x,v.y,v.z]);}
fn basis3(out:&mut Vec<u32>,b:Basis3){for c in b.columns{floats(out,c);}}
fn affine(out:&mut Vec<u32>,a:RetailAffineTransform){basis3(out,a.basis);vector3(out,a.translation);}
fn material(out:&mut Vec<u32>,m:RetailContactMaterial){floats(out,[m.static_friction,m.dynamic_friction,m.restitution]);}
fn body(out:&mut Vec<u32>,b:BodySnapshot){let r=b.rates;let d=b.inertia;out.push(b.state_flags);floats(out,[r.orientation.x,r.orientation.y,r.orientation.z,r.orientation.w]);basis3(out,r.basis);basis3(out,r.world_inverse_inertia);for v in [r.position,r.linear_velocity,r.angular_velocity,r.force_acceleration,r.torque_acceleration]{vector3(out,v);}out.extend([r.kinetic_energy.to_bits(),r.cool_down]);vector3(out,d.inverse_tensor);floats(out,[d.inverse_mass,d.spherical,d.maximum_linear_velocity,d.maximum_angular_velocity,d.linear_drag,d.angular_drag]);}
fn observation(out:&mut Vec<u32>,o:Observation){let p=o.processed;matrix(out,p.board_frame_64);matrix(out,p.player_frame_192);for v in [p.position_592,p.velocity_912,p.direction_400,p.hide_direction_464]{floats(out,v);}out.extend([p.flags_2476,p.flags_2480,p.flags_2488,o.board_collision_flags_872,o.board_state_840]);out.extend(o.hand_contacts.map(|v|v as u32));for v in o.physical_hand_positions{floats(out,v);}matrix(out,o.animation_board_frame_12624);for m in o.animation_hand_frames{matrix(out,m);}matrix(out,o.attachment_frame_0);}
fn settings(out:&mut Vec<u32>,s:Settings){floats(out,[s.hide_distance,s.hide_offset,s.return_distance,s.mounted_return_distance,s.mounting_time]);floats(out,s.retrieval_time.x);floats(out,s.retrieval_time.y);floats(out,s.retrieval_weight.x);floats(out,s.retrieval_weight.y);out.push(s.throw_pitch.to_bits());floats(out,s.throw_velocity.x);floats(out,s.throw_velocity.y);floats(out,[s.throw_target_pitch,s.throw_pitch_scalar,s.throw_roll_scalar,s.throw_yaw_scalar]);}
fn error(out:&mut Vec<u32>,s:&str){out.push(s.len() as u32);out.extend(s.bytes().map(u32::from));}
fn live_state(out:&mut Vec<u32>,p:&mut GamePhysics,l:&mut board_manager::runtime::LiveState,animated:&mut u8,dt:f32){
 out.extend([l.volumes.deck as u32,l.volumes.trucks as u32,l.volumes.wheels as u32,l.volumes.deck_children.len() as u32]);out.extend(l.volumes.deck_children.iter().map(|v|*v as u32));
 let (a,active,standard,released,drag)={let e=l.effects(p,animated,dt);(*e.alignment,*e.alignment_active,e.standard_materials,e.released_material,e.standard_angular_drag)};
 floats(out,a.first_1008);floats(out,a.second_1024);out.extend([a.factor_1040.to_bits(),a.flag_1044 as u32,active as u32]);for m in standard{material(out,m);}material(out,released);out.push(drag.to_bits());out.push(l.output.is_some() as u32);if let Some(f)=l.output{fill(out,f);}
}
fn live(out:&mut Vec<u32>,p:&mut GamePhysics,s:&mut SkaterRuntime){live_state(out,p,&mut s.board_possession_live,&mut s.ground_lifecycle.board_animated_290,s.player_input.processed.timestep_2604);}
fn physical(out:&mut Vec<u32>,p:&physics::Offboard){floats(out,[p.angle_36,p.angle_40]);out.extend([p.flag_311,p.free_board_312,p.returning_board_313,p.hiding_board_321,p.dropping_board_322,p.retrieving_board_323,p.flag_324].map(u32::from));}
fn snapshot(out:&mut Vec<u32>,p:&mut GamePhysics,s:&mut SkaterRuntime){
 fields(out,s.skateboard_controller.fields);state(out,&s.board_possession.state);out.extend([s.ground_lifecycle.board_animated_290 as u32,p.board_wiping_out as u32]);for b in *p.board.bodies(){body(out,b);}body(out,p.board.hook().body);out.extend(p.board.hook().drive.frames);out.extend(p.board.hook().drive.dynamics);for t in p.board.part_transforms(){affine(out,t);}affine(out,p.board.hook_transform());out.push(p.board.collision_group());
 let c=&p.settings;for m in [c.wheel_material,c.truck_material,c.deck_material]{material(out,m);}out.extend([c.truck_collisions as u32,c.deck_geometry.children.len() as u32]);out.extend(c.deck_geometry.children.iter().map(|v|v.collision_enabled as u32));live(out,p,s);physical(out,&s.player_input.physical.off_board);out.push(p.riding.ground.collision_flags);observation(out,board_manager::runtime::observe(p,s));for b in s.skeleton.bodies{body(out,b);}
}
fn config()->physics::ProbeSettings{physics::ProbeSettings{standard_wheel_material:MATERIAL,wheel_material:MATERIAL,truck_material:MATERIAL,deck_material:MATERIAL,truck_collisions:false,deck_geometry:DeckGeometry::new(DeckGeometrySettings::STOCK)}}
fn make(p:GamePhysics,data:&skate_data::collections::Collections,dt:f32)->(GamePhysics,SkaterRuntime){
 let live=board_manager::runtime::LiveState::load(data,&p).unwrap();let seed=p.board.bodies()[6];let s=SkaterRuntime{player_input:physics::PlayerInput{processed:physics::ProbeProcessed{effective_anim_transform_192:[[0;4];4],vectors_544_560_592_608:[[0;4];4],vectors_880_896_912_928_944:[[0;4];5],vectors_400_416:[[0;4];2],vectors_464_480_496_512_528:[[0;4];5],flags_2476:0,flags_2480:0,flags_2488:0,timestep_2604:dt},toolkit:None,physical:physics::Physical{off_board:Default::default()}},skeleton_input:physics::SkeletonInput{drive_frames:[IDENTITY;24]},skeleton:physics::Skeleton{record:Default::default(),bodies:[seed;26]},collision_feedback:physics::Feedback{bones:[physics::Bone::default();24]},animated_skeleton:physics::Animated{roots:Default::default()},skateboard_controller:physics::Controller{fields:SkateboardControllerFields{word_444:0,state_448:0,system_on_452:false}},ground_lifecycle:physics::GroundLifecycle{board_animated_290:0},board_possession:Owner::load(data).unwrap(),board_possession_live:live};(p,s)
}
fn effect(i:&mut Input,e:&mut LiveEffects<'_>,op:u32){match op{0=>e.enable_animation_soft(),1=>e.enable_animation_angular_only(),2=>e.disable_animation(),3=>e.disable_linear_drive(),4=>e.standard_board(),5=>e.released_board(),6=>e.collision_volumes(i.word()!=0),7=>e.clear_alignment(),8=>e.alignment(Alignment{first_1008:i.vector(),second_1024:i.vector(),factor_1040:i.float(),flag_1044:i.word()!=0}),9=>e.velocity(i.vector()),10=>e.position(i.vector()),11=>e.hook_frame(i.matrix()),12=>e.target_position_velocity(i.vector()),13=>e.torque(i.vector()),_=>panic!("Effect")}}
fn main(){
 let args=std::env::args().collect::<Vec<_>>();let data=skate_data::collections::Collections::load(std::path::Path::new(&args[1])).unwrap();let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut i=Input{words:bytes.chunks_exact(4).map(|v|u32::from_le_bytes(v.try_into().unwrap())).collect(),at:0};let mut out=Vec::new();let count=i.word();
 for index in 0..count{let op=i.word();out.extend([index,op,0]);let mark=out.len()-1;let start=out.len();match op{
 1=>{
  match board_possession::settings::load(&data){Ok(s)=>{out.push(1);settings(&mut out,s)},Err(e)=>{out.push(0);error(&mut out,&e)}}match board_possession::settings::standard_angular_drag(&data){Ok(s)=>out.extend([1,s.to_bits()]),Err(e)=>{out.push(0);error(&mut out,&e)}}
  let board=BoardRuntime::new(default_skateboard_mass_properties(),authored_body_transforms(AuthoredTransformInputs::STOCK),RetailAffineTransform::IDENTITY,RetailSimulationStep::fixed_60_hz(30,0.001,Vector3::ZERO),BoardMotion::Active);let mut p=GamePhysics{settings:config(),board,board_wiping_out:false,riding:physics::Riding{ground:Default::default(),wheel_lines:Default::default()}};
  match board_manager::runtime::LiveState::load(&data,&p){Ok(mut l)=>{out.push(1);live_state(&mut out,&mut p,&mut l,&mut 0,1./60.);},Err(e)=>{out.push(0);error(&mut out,&e)}}
 },
 0=>{
  let spawn=i.affine();let simulation=i.simulation();let mut masses=default_skateboard_mass_properties();if i.word()!=0{for mass in &mut masses{let frame=i.affine();mass.local_mass_frame=RetailLocalMassFrame{basis:frame.basis,translation:frame.translation};}}
  let board=BoardRuntime::new(masses,authored_body_transforms(AuthoredTransformInputs::STOCK),spawn,simulation,BoardMotion::Active);let mut c=config();c.standard_wheel_material=i.material();c.truck_material=i.material();c.deck_material=i.material();c.wheel_material=i.material();c.truck_collisions=i.word()!=0;let n=i.word();c.deck_geometry.children.resize(n as usize,c.deck_geometry.children[0]);for child in &mut c.deck_geometry.children{child.collision_enabled=i.word()!=0;}
  let p=GamePhysics{settings:c,board,board_wiping_out:false,riding:physics::Riding{ground:Default::default(),wheel_lines:Default::default()}};let fields=i.fields();let retained=if i.word()!=0{Some(i.state())}else{None};let dt=i.float();let animated=i.word() as u8;let wiping=i.word()!=0;let(mut p,mut s)=make(p,&data,dt);s.skateboard_controller.fields=fields;if let Some(retained)=retained{s.board_possession.state=retained;}s.ground_lifecycle.board_animated_290=animated;p.board_wiping_out=wiping;i.observe(&mut p,&mut s);let commands=i.word();out.push(commands);snapshot(&mut out,&mut p,&mut s);
  for _ in 0..commands{let op=i.word();out.extend([op,0]);let command_mark=out.len()-1;let command_start=out.len();match op{
   0=>i.observe(&mut p,&mut s),1=>s.skateboard_controller.fields=i.fields(),2=>board_manager::runtime::update(&mut p,&mut s),
   3|4|5=>{let o=board_manager::runtime::observe(&p,&s);let mut e=s.board_possession_live.effects(&mut p,&mut s.ground_lifecycle.board_animated_290,dt);match op{3=>s.board_possession.hold(&mut s.skateboard_controller.fields,&o,&mut e),4=>s.board_possession.let_go(&mut s.skateboard_controller.fields,&o,&mut e),_=>s.board_possession.stop(&mut s.skateboard_controller.fields,&o,&mut e)}},
   6=>board_manager::runtime::reset_for_teleport(&mut p,&mut s),7=>board_manager::runtime::finish_teleport(&mut p,&mut s),8=>fill(&mut out,board_manager::runtime::publish(&mut p,&mut s)),
   9=>{let dt=i.float();let deck=i.word() as usize;let a=i.word() as usize;let b=i.word() as usize;let mut rows=Vec::new();s.board_possession.append_drives(p.board.bodies()[6],[s.skeleton.bodies[3],s.skeleton.bodies[7]],deck,[a,b],dt,&mut rows);out.push(rows.len() as u32);for row in rows{let pack=packing::drive(&row);out.extend(pack.words);out.extend([pack.reaction_a as u32,pack.reaction_b as u32]);}},
   10=>s.board_possession_live.publish_volumes(&mut p),11=>{let id=i.word() as usize;let body=i.body();if id<7{p.board.bodies_mut()[id]=body}else if id==7{p.board.hook_mut().body=body}else{s.skeleton.bodies[id-8]=body}},
   12=>{let o=board_manager::runtime::observe(&p,&s);let mut e=s.board_possession_live.effects(&mut p,&mut s.ground_lifecycle.board_animated_290,dt);let mut t=Transition::new(&mut s.board_possession,&o,&mut e,s.skateboard_controller.fields);let n=i.word();for _ in 0..n{if i.word()!=0{t.let_go_of_skateboard()}else{t.hold_skateboard()}}s.skateboard_controller.fields=i.fields();t.finish(&mut s.skateboard_controller.fields);},
   13=>s.board_possession.state=i.state(),14=>{let deck=i.word()!=0;let trucks=i.word()!=0;let wheels=i.word()!=0;let n=i.word();let children=(0..n).map(|_|i.word()!=0).collect();let alignment=Alignment{first_1008:i.vector(),second_1024:i.vector(),factor_1040:i.float(),flag_1044:i.word()!=0};let active=i.word()!=0;s.board_possession_live.volumes=board_possession::VolumeFlags{deck,trucks,wheels,deck_children:children};let e=s.board_possession_live.effects(&mut p,&mut s.ground_lifecycle.board_animated_290,dt);*e.alignment=alignment;*e.alignment_active=active;},
   15=>observation(&mut out,board_manager::runtime::observe(&p,&s)),17=>{let n=i.word();let seed=DeckGeometry::new(DeckGeometrySettings::STOCK).children[0];p.settings.deck_geometry.children.resize(n as usize,seed);for c in &mut p.settings.deck_geometry.children{c.collision_enabled=i.word()!=0;}},18=>{let hand=i.word() as usize;s.board_possession.state.hands[hand].dynamics=std::array::from_fn(|_|std::array::from_fn(|_|i.word()));},19=>{let op=i.word();let mut e=s.board_possession_live.effects(&mut p,&mut s.ground_lifecycle.board_animated_290,dt);effect(&mut i,&mut e,op);},20=>out.push(s.board_possession_live.volume_enabled(skate_core::physics::board_step::CollisionBody::from_contact_id(i.word())) as u32),_=>panic!("Live command")}
   snapshot(&mut out,&mut p,&mut s);out[command_mark]=(out.len()-command_start) as u32;
  }
 },_=>panic!("Live operation")};out[mark]=(out.len()-start) as u32;}
 assert_eq!(i.at,i.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for w in out{stdout.write_all(&w.to_le_bytes()).unwrap();}
}
