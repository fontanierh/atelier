//! Full original core board composition. Protocol helpers use type declarations
//! only. Whole original host launch/settings/tuning modules are appended.
#![allow(non_snake_case,dead_code,unused_imports)]
use skate_core::{math::{Basis3,Vector3},point_graph::PointGraph,physics::{assembly::*,drive_frames::{RetailAffineTransform,AuthoredTransformInputs,authored_body_transforms},board_runtime::*,rigid_body::*,contact::RetailContactMaterial,manual::{controller::{ManualAngleMeasurement,ManualInput,ManualError},state::ManualState,settings::{ManualSettings,ManualMode,ManualGains}},force_queue::{BoardForceQueue,QueuedPointForce},deck_angular_correction},riding::{steering::{SteeringInput,SteeringSettings,TruckSteeringState},speed_wobble::{SpeedWobbleInput,SpeedWobbleSettings,SpeedWobbleState},ground_force::GroundForceSettings,ground_contact_response::{WallRideSettings,WallRidePhysical,wall_ride_response},collision_response::{CollisionResponseSettings,CollisionResponsePhysical,collision_response,signed_angle},ground_correction_math as geometry,grounded::{propulsion::{GroundPropulsionInput,GroundPropulsionSettings},drag::{BodyInertias,DragBindingError,GroundDragInput},state::{board::{self,GroundBoardOutcome},data::PhysicsGroundState,board_types::*,corrections::*}},braking::{BrakeSettings,LinearDragSettings},speed_model::{SpeedModelInput,SpeedModelSettings,SpeedModelState},slide_friction::{SlideFrictionInput,SlideFrictionSettings},straighten::{StraightenInput,StraightenSettings},heading::{HeadingInput,HeadingSettings},anti_flip::{AntiFlipInput,AntiFlipSettings},pumping::PumpForceInput},air::trajectory::LaunchInfo};
use skate_core::physics::skeleton_animation_record::AnimationPartTransform;
use launch::{GroundLaunchInfo,GroundLaunchPhysical};
use tuning::TrainerTuning;
use std::io::{Read,Write};
struct Input {bytes:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn floats<const N:usize>(&mut self)->[f32;N] {std::array::from_fn(|_|self.float())}
    fn words<const N:usize>(&mut self)->[u32;N] {std::array::from_fn(|_|self.word())}
    fn three(&mut self)->Vector3 {Vector3::new(self.float(),self.float(),self.float())}
    fn matrix(&mut self)->[[f32;4];4] {std::array::from_fn(|_|self.floats())}
    fn curve<const N:usize>(&mut self)->PointGraph<N> {PointGraph{x:self.floats(),y:self.floats()}}
}
struct Output(Vec<u8>);
impl Output {
    fn word(&mut self,v:u32) {self.0.extend(v.to_le_bytes());}
    fn float(&mut self,v:f32) {self.word(v.to_bits());}
    fn floats(&mut self,v:impl IntoIterator<Item=f32>) {for x in v {self.float(x);}}
    fn words(&mut self,v:impl IntoIterator<Item=u32>) {for x in v {self.word(x);}}
    fn vector(&mut self,v:Vector3) {self.floats([v.x,v.y,v.z]);}
    fn string(&mut self,v:&str) {self.word(v.len() as u32);self.0.extend(v.as_bytes());}
    fn block(&mut self,o:&Output) {self.word((o.0.len()/4) as u32);self.0.extend(&o.0);}
    fn body(&mut self,b:BodySnapshot) {let r=b.rates;let d=b.inertia;self.word(b.state_flags);self.floats([r.orientation.x,r.orientation.y,r.orientation.z,r.orientation.w]);for b in [r.basis,r.world_inverse_inertia] {for c in b.columns {self.floats(c);}}for v in [r.position,r.linear_velocity,r.angular_velocity,r.force_acceleration,r.torque_acceleration] {self.vector(v);}self.float(r.kinetic_energy);self.word(r.cool_down);self.vector(d.inverse_tensor);self.floats([d.inverse_mass,d.spherical,d.maximum_linear_velocity,d.maximum_angular_velocity,d.linear_drag,d.angular_drag]);}
}
// GENERATED_PROTOCOL
fn xyz(v:[f32;4])->Vector3 {Vector3::new(v[0],v[1],v[2])}
fn four(v:Vector3)->[f32;4] {[v.x,v.y,v.z,0.]}
fn arguments(v:impl IntoIterator<Item=[f32;4]>)->Output {let mut o=Output(Vec::new());for x in v {o.floats(x);}o}
fn authored_packet(seed:u32)->GroundLaunchInfo {GroundLaunchInfo{vector_224:[seed as f32*0.125,0.25,-0.5,0.125],vector_240:[-0.125,0.5,seed as f32*0.25,0.25],flag_269:true,flags_270:0x1234,wall_jump:false,..GroundLaunchInfo::default()}}
struct Services<'a> {board:&'a mut BoardRuntime,settings:&'a stock::GroundSettings,seed:u32,fail:u32,calls:u32,branch:u32,wipeouts:u32,commits:u32,trace:Output,contact:Option<GroundContactResponse>,retained_collision:Option<CollisionForceResponse>,launch:Option<GroundLaunchInfo>,processed_velocity:[f32;4],material:RetailContactMaterial,reckoning:skate_core::riding::reckoning_frames::ReckoningFrames}
impl Services<'_> {
    fn gate(&mut self,id:u32,args:Output)->Result<(),String> {self.calls+=1;self.trace.word(id);self.trace.block(&args);if self.calls==self.fail {Err(format!("Ground fixture failure {}",self.calls))}else {Ok(())}}
    fn empty(&mut self,id:u32)->Result<(),String> {self.gate(id,Output(Vec::new()))}
    fn physical(&self)->GroundLaunchPhysical<'_> {GroundLaunchPhysical{reckoning:&self.reckoning,skeleton_vector_16208:[0.125,0.25,0.5,0.75],skeleton_vector_16240:[-0.125,0.5,0.25,0.125],board_position:[0.5,2.,0.25,1.],physical_center_of_mass:[0.5,3.,0.25,1.],velocity:[1.,2.,3.,0.125],angular_velocity:[0.25,0.5,0.75,0.25],flags_2468:if self.seed%2!=0 {0x2000}else {0},time_step:1./60.}}
}
impl ManualAngleMeasurement for Services<'_> {
    type Error=String;
    fn angle_between(&mut self,a:[f32;4],b:[f32;4],axis:[f32;4])->Result<f32,String> {self.gate(15,arguments([a,b,axis]))?;Ok(signed_angle(xyz(a),xyz(b),xyz(axis)))}
}
impl AntiFlipNudgeMath for Services<'_> {
    type Error=String;
    fn dot3(&mut self,a:[f32;4],b:[f32;4])->Result<f32,String> {self.gate(16,arguments([a,b]))?;Ok(geometry::dot_product(a,b))}
    fn scale_to_magnitude(&mut self,v:[f32;4],square:f32,size:f32)->Result<[f32;4],String> {let mut a=arguments([v]);a.floats([square,size]);self.gate(17,a)?;Ok(geometry::scale_to_magnitude(v,square,size))}
}
impl HangUpServices for Services<'_> {
    type Error=String;
    fn build_hang_force(&mut self)->Result<[f32;4],String> {let p=self.board.part_transforms()[6].translation;let start=[0.,0.,0.,0.];let end=[0.,0.,2.,0.];self.gate(18,arguments([start,end,four(p)]))?;Ok(geometry::hang_force(start,end,four(p)))}
    fn apply_hang_force(&mut self,f:[f32;4])->Result<(),String> {self.gate(19,arguments([f]))?;let p=self.board.part_transforms()[6].translation;geometry::apply_world_force(&mut self.board.bodies_mut()[6],p,xyz(f),p);Ok(())}
    fn detect_hung_up_geometry(&mut self)->Result<bool,String> {let mut a=Output(Vec::new());a.word(self.seed%2);self.gate(20,a)?;Ok(self.seed%2!=0)}
    fn request_wipeout(&mut self)->Result<(),String> {self.empty(21)?;self.wipeouts+=1;Ok(())}
}
impl HalfpipeWheelCatchServices for Services<'_> {
    type Error=String;
    fn angular_displacement(&mut self)->Result<[f32;4],String> {self.empty(22)?;let b=self.board.part_transforms()[6].basis.columns;Ok(geometry::wheel_catch_displacement([b[1][0],b[1][1],b[1][2],0.],[b[2][0],b[2][1],b[2][2],0.]))}
    fn apply_angular_displacement(&mut self,v:[f32;4])->Result<(),String> {self.gate(23,arguments([v]))?;deck_angular_correction::apply_angular_displacement(&mut self.board.bodies_mut()[6].rates,xyz(v));Ok(())}
}
impl PinningServices for Services<'_> {
    type Error=String;
    fn pin_to_captured_position(&mut self,x:f32,z:f32)->Result<(),String> {let mut a=Output(Vec::new());a.floats([x,z]);self.gate(24,a)?;let v=geometry::pinning_velocity(four(self.board.part_transforms()[6].translation),x,z,1./60.);for b in self.board.bodies_mut() {b.rates.linear_velocity=xyz(v);}Ok(())}
}
impl GroundBoardServices for Services<'_> {
    type BoardError=String;
    type AnimatedPose=GroundLaunchInfo;
    fn center_of_mass_height_82d38838(&mut self)->Result<f32,String> {let c=[0.25,0.5,1.,0.125];self.gate(0,arguments([c]))?;Ok(geometry::center_of_mass_height(c))}
    fn set_contact_wheel_materials(&mut self)->Result<(),String> {let mut a=Output(Vec::new());observe_RetailContactMaterial(&mut a,&self.settings.wheel_material);self.gate(1,a)?;self.material=self.settings.wheel_material;Ok(())}
    fn contact_response_82d93df0(&mut self,f:GroundContactFrame,previous:[f32;4])->Result<GroundContactResponse,String> {let mut a=Output(Vec::new());observe_GroundContactFrame(&mut a,&f);a.floats(previous);self.gate(2,a)?;let settings=WallRideSettings{anti_gravity_vs_time:PointGraph{x:std::array::from_fn(|i|i as f32),y:[0.125;8]},max_dot_floor_wall:0.5,foot_force_time:0.09,auto_jump_height:0.6,max_time:1.,velocity_time_to_consider:0.25,auto_jump_y_down_scalar:0.66,auto_jump_force:3.};let normal=if self.branch==1 {[1.,0.,0.,0.]}else {[0.,1.,0.,0.]};let contact=wall_ride_response(&settings,WallRidePhysical{board_normal:normal,up:normal,velocity:[2.,-2.,4.,0.125],board_mass:8.,gravity:9.81,speed:5.,contact_count:1},f,previous);self.contact=Some(contact);Ok(contact)}
    fn update_body_accumulator_82d389dc(&mut self)->Result<(),String> {self.empty(3)?;deck_angular_correction::apply_ground_body_torque(&mut self.board.bodies_mut()[6].rates);Ok(())}
    fn set_animated_velocity_82c04168(&mut self,v:[f32;4])->Result<(),String> {self.gate(4,arguments([v]))?;for b in self.board.bodies_mut() {b.rates.linear_velocity=xyz(v);}Ok(())}
    fn write_processed_velocity_400(&mut self,v:[f32;4])->Result<(),String> {self.gate(5,arguments([v]))?;self.processed_velocity=v;Ok(())}
    fn build_animated_pose_82d33448(&mut self)->Result<GroundLaunchInfo,String> {self.empty(6)?;Ok(authored_packet(self.seed))}
    fn publish_animated_pose_82be33d0(&mut self,p:&GroundLaunchInfo)->Result<(),String> {let mut a=Output(Vec::new());observe_GroundLaunchInfo(&mut a,p);self.gate(7,a)?;let mut p=p.clone();p.fill(&self.physical(),0.125,0.25);self.launch=Some(p);Ok(())}
    fn update_external_player_82d67848(&mut self,p:&GroundLaunchInfo,v:[f32;4])->Result<(),String> {let mut a=Output(Vec::new());observe_GroundLaunchInfo(&mut a,p);a.floats(v);self.gate(8,a)?;self.launch.as_mut().ok_or("Ground launch packet was not filled")?.wall_jump(v);Ok(())}
    fn commit_external_player_82d68800(&mut self)->Result<(),String> {let mut a=Output(Vec::new());if let Some(p)=&self.launch {observe_GroundLaunchInfo(&mut a,p);observe_LaunchInfo(&mut a,&p.selector_launch());}self.gate(9,a)?;self.commits+=1;Ok(())}
    fn finalize_animated_board_sk83_na_f_01a4(&mut self)->Result<(),String> {self.empty(10)}
    fn collision_force_82d944e8(&mut self,normal:[f32;4])->Result<Option<CollisionForceResponse>,String> {self.gate(11,arguments([normal]))?;let settings=CollisionResponseSettings{maximum_velocity_delta:0.75,force_y_offset:-0.125,force_scalar:0.75,target_displacement_velocity:0.75,torque_vs_angle:PointGraph{x:std::array::from_fn(|i|i as f32),y:[0.125;8]}};let physical=CollisionResponsePhysical{flags_2472:if self.branch==2 {0x20000}else {0},collision_displacement:[1.,0.,0.,0.125],velocity:[-0.25,0.,1.,0.25],forward:[0.,0.,1.,0.],up:[0.,1.,0.,0.],ground_normal:normal,time_step:1./60.,mass:8.};if let Some(r)=collision_response(&settings,physical) {if r.applied {let output=CollisionForceResponse{force_2528:r.force,point_2544:r.point,vector_2592:r.angular_displacement};self.retained_collision=Some(output);return Ok(Some(output));}}Ok(None)}
    fn collision_force_dot_velocity_82d38e18(&mut self,f:[f32;4],v:[f32;4])->Result<f32,String> {self.gate(12,arguments([f,v]))?;Ok(geometry::collision_force_projection(f,v))}
    fn apply_vector_82c07000(&mut self,v:[f32;4])->Result<(),String> {self.gate(13,arguments([v]))?;deck_angular_correction::apply_limited_displacement(&mut self.board.bodies_mut()[6].rates,xyz(v));Ok(())}
    fn apply_angular_displacement_82c075b8(&mut self,v:[f32;4])->Result<(),String> {self.gate(14,arguments([v]))?;deck_angular_correction::apply_angular_displacement(&mut self.board.bodies_mut()[6].rates,xyz(v));Ok(())}
}
fn snapshot(o:&mut Output,state:&PhysicsGroundState,wobble:&SpeedWobbleState,truck:&TruckSteeringState,speed:&SpeedModelState,manual:&ManualState,heading:f32,detached:&[RetailInertiaDynamics],indices:&[usize],s:&Services<'_>) {
    observe_PhysicsGroundState(o,state);o.words(wobble.0);observe_TruckSteeringState(o,truck);observe_SpeedModelState(o,speed);observe_ManualState(o,manual);o.float(heading);for b in s.board.bodies() {o.body(*b);}o.word(detached.len() as u32);for d in detached {o.vector(d.inverse_tensor);o.floats([d.inverse_mass,d.spherical,d.maximum_linear_velocity,d.maximum_angular_velocity,d.linear_drag,d.angular_drag]);}o.word(indices.len() as u32);o.words(indices.iter().map(|i|*i as u32));o.word(s.board.forces().entries().len() as u32);for f in s.board.forces().entries() {o.word(f.tag);o.vector(f.force_world);o.vector(f.point_body);}o.floats(s.processed_velocity);observe_RetailContactMaterial(o,&s.material);o.word(s.retained_collision.is_some() as u32);if let Some(c)=s.retained_collision {o.floats(c.force_2528);o.floats(c.point_2544);o.floats(c.vector_2592);}o.word(s.launch.is_some() as u32);if let Some(p)=&s.launch {observe_GroundLaunchInfo(o,p);observe_LaunchInfo(o,&p.selector_launch());}o.word(s.wipeouts);o.word(s.commits);o.word(s.calls);o.block(&s.trace);
}
fn error_result(error:GroundBoardError<String>)->([u32;6],String) {
    match error {
        GroundBoardError::Service{stage,source}=>{let stage=match stage {GroundBoardStage::CenterOfMassHeight=>0,GroundBoardStage::SetWheelMaterials=>1,GroundBoardStage::ContactResponse=>2,GroundBoardStage::UpdateBodyAccumulator=>3,GroundBoardStage::SetAnimatedVelocity=>4,GroundBoardStage::WriteProcessedVelocity=>5,GroundBoardStage::BuildAnimatedPose=>6,GroundBoardStage::PublishAnimatedPose=>7,GroundBoardStage::UpdateExternalPlayer=>8,GroundBoardStage::CommitExternalPlayer=>9,GroundBoardStage::FinalizeAnimatedBoard=>10,GroundBoardStage::CollisionForce=>11,GroundBoardStage::ApplyCollisionVector=>12,GroundBoardStage::CollisionProjection=>13,GroundBoardStage::ManualEffect=>14,GroundBoardStage::PushForceSquared=>15,GroundBoardStage::AntiFlipNudge=>16,GroundBoardStage::ApplyCollisionDecay=>17,GroundBoardStage::ApplyStraighten=>18,GroundBoardStage::ApplyHeading=>19,GroundBoardStage::ApplyAntiFlip=>20,GroundBoardStage::ApplyManual=>21,GroundBoardStage::HangUps=>22,GroundBoardStage::HalfpipeWheelCatch=>23,GroundBoardStage::Pinning=>24,GroundBoardStage::StrongForceSquared=>25};([u32::MAX,0,stage,0,0,0],source)},
        GroundBoardError::Manual(ManualError::Angle(_))=>([u32::MAX,1,0,0,0,0],"Ground manual angle unavailable".into()),
        GroundBoardError::Manual(ManualError::Measurement(error))=>([u32::MAX,1,0,1,0,0],error),
        GroundBoardError::Drag(error)=>{let code=match error {DragBindingError::PartOutsideAssembly=>0,DragBindingError::InertiaOutsideStorage=>1};([u32::MAX,2,0,code,0,0],format!("Ground drag binding {code}"))},
    }
}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let data=skate_data::collections::Collections::load(std::path::Path::new(&args[1]))?;let profiles=stock::GroundProfiles::load(&data)?;let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).map_err(|e|e.to_string())?;let mut i=Input{bytes,at:0};let count=i.word();let mut out=Output(Vec::new());
    for c in 0..count {
        let mode=i.word();let surface=i.word();let tuning=read_TrainerTuning(&mut i);let settings=profiles.select(mode,surface)?.tuned(tuning);let mut state=read_PhysicsGroundState(&mut i);let seed=i.word();let preseed=i.word();let mut wobble=SpeedWobbleState([0,0x12340000+seed,0,0,0,0,0,0x00123456]);let mut truck=TruckSteeringState{deck_tilt:0.125,targets:[0.25,-0.125],activation_time:[0.05,0.125]};let mut speed=SpeedModelState{target_speed:2.,flags_1360:0x80000000};let mut manual=ManualState{filtered_angle_error:0.125,target_angle:0.25,measured_angle:0.375,angular_correction:0.5,elapsed:0.};let mut heading=0.125;
        let mut board=BoardRuntime::new(skate_core::physics::mass::default_skateboard_mass_properties(),authored_body_transforms(AuthoredTransformInputs::STOCK),RetailAffineTransform{basis:Basis3{columns:[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]},translation:Vector3::new(0.,2.,0.)},RetailSimulationStep{time_step:1./60.,frequency:60.,cool_down:9,minimum_energy:0.001,gravity_acceleration:Vector3::new(0.,-9.81,0.)},BoardMotion::Active);for (n,b) in board.bodies_mut().iter_mut().enumerate() {b.rates.angular_velocity=Vector3::new(0.125,0.25,0.375);b.rates.torque_acceleration=Vector3::new(n as f32*0.125,0.25,-0.125);b.inertia.linear_drag=0.125+n as f32*0.03125;}for n in 0..preseed {board.forces_mut().append(QueuedPointForce{tag:100+n,force_world:Vector3::new(n as f32,0.25,-0.125),point_body:Vector3::new(0.125,0.25,0.375)});}
        let mut reckoning=skate_core::riding::reckoning_frames::ReckoningFrames::new();reckoning.system[3]=[0.125,0.25,0.5,1.];reckoning.inverse_system[3]=[-0.125,-0.25,-0.5,1.];let mut services=Services{board:&mut board,settings:&settings,seed,fail:0,calls:0,branch:0,wipeouts:0,commits:0,trace:Output(Vec::new()),contact:None,retained_collision:None,launch:None,processed_velocity:[0.125,0.25,0.5,0.75],material:RetailContactMaterial{static_friction:0.125,dynamic_friction:0.25,restitution:0.5},reckoning};
        let mut config=Output(Vec::new());stock::observe(&mut config,&settings);let mut packet=GroundLaunchInfo::default();observe_GroundLaunchInfo(&mut config,&packet);observe_LaunchInfo(&mut config,&packet.selector_launch());packet=authored_packet(seed);observe_GroundLaunchInfo(&mut config,&packet);observe_LaunchInfo(&mut config,&packet.selector_launch());packet.fill(&services.physical(),0.125,0.25);observe_GroundLaunchInfo(&mut config,&packet);observe_LaunchInfo(&mut config,&packet.selector_launch());packet.wall_jump([2.,4.,-3.,0.125]);observe_GroundLaunchInfo(&mut config,&packet);observe_LaunchInfo(&mut config,&packet.selector_launch());out.word(c);out.block(&config);
        let ticks=i.word();for tick in 0..ticks {
            services.branch=i.word();services.fail=i.word();let clear=i.word()!=0;let binding=i.word();let frame=read_GroundBoardInput(&mut i);if clear {services.board.clear_forces();}services.calls=0;services.trace.0.clear();let mut detached:Vec<_>=services.board.bodies().iter().map(|b|b.inertia).collect();let mut indices=vec![0,1,2,3,4,5,6];if binding==1 {indices[3]=7;}else if binding==2 {detached.truncate(6);}let mut queue=std::mem::take(services.board.forces_mut());let mut inertias=BodyInertias{part_inertia_indices:&indices,inertias:&mut detached};let result=board::update(&mut state,GroundBoardComponents{speed_wobble:&mut wobble,truck_steering:&mut truck,speed_model:&mut speed,manual:&mut manual,heading_previous:&mut heading,force_queue:&mut queue,inertias:&mut inertias},settings.board(),frame,&mut services);
            for (b,d) in services.board.bodies_mut().iter_mut().zip(&detached) {b.inertia.linear_drag=d.linear_drag;}*services.board.forces_mut()=queue;out.word(c);out.word(tick);out.word(result.is_ok() as u32);let (status,text)=match result {Ok(GroundBoardOutcome::Animated)=>([0,0,0,0,0,0],String::new()),Ok(GroundBoardOutcome::Collision{tag_15_queued})=>([1,tag_15_queued as u32,0,0,0,0],String::new()),Ok(GroundBoardOutcome::Ordinary(r))=>([2,0,r.manual_correction as u32,r.terminal_force_tag,r.terminal_force_queued as u32,r.speed_model_reset as u32],String::new()),Err(error)=>error_result(error)};out.words(status);out.string(&text);let mut row=Output(Vec::new());snapshot(&mut row,&state,&wobble,&truck,&speed,&manual,heading,&detached,&indices,&services);out.block(&row);
        }
    }
    assert_eq!(i.at,i.bytes.len());std::io::stdout().write_all(&out.0).map_err(|e|e.to_string())?;Ok(())
}
fn main() {if let Err(error)=run() {eprintln!("{error}");std::process::exit(2);}}
