//! Verbatim actual Slide host functions and numerical GroundRuntime methods are
//! inserted by the checker. Producer shells take explicit completed input frames.
use skate_core::{math::{Basis3,Vector3},physics::{assembly::*,board::BodyId,board_runtime::*,rigid_body::*,contact::RetailContactMaterial,manual::{state::ManualState,controller::ManualInput,settings::{ManualSettings,ManualMode,ManualGains}},force_queue::QueuedPointForce},point_graph::PointGraph,player::slide_state::{SlideSettings,SlideSurface,SlideInput},riding::{steering::{SteeringSettings,SteeringInput,TruckSteeringState},ground_force::GroundForceSettings,ground_contact_response::{WallRideSettings,WallRidePhysical},grounded::state::board_types::{GroundContactFrame,GroundContactResponse,CollisionForceResponse},collision_response::{CollisionResponseSettings,CollisionResponsePhysical}}};
use std::{io::{Read,Write},rc::Rc,cell::RefCell};
use skate_core::physics::drive_frames::{RetailAffineTransform,AuthoredTransformInputs,authored_body_transforms};
#[derive(Default)]
struct Trace {events:Vec<u32>,fail:u32,toolkit_calls:u32,mode:u32,collision:Option<CollisionResponsePhysical>,launch:Option<[f32;4]>}
type Shared=Rc<RefCell<Trace>>;
fn stage(trace:&Shared,code:u32)->Result<(),String> {let mut t=trace.borrow_mut();t.events.push(code);if t.fail==code {Err(format!("Slide fixture producer failure {code}"))}else {Ok(())}}
struct Input {bytes:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn four(&mut self)->[f32;4] {std::array::from_fn(|_|self.float())}
    fn three(&mut self)->Vector3 {Vector3::new(self.float(),self.float(),self.float())}
    fn curve(&mut self)->PointGraph<8> {PointGraph{x:std::array::from_fn(|_|self.float()),y:std::array::from_fn(|_|self.float())}}
    fn slide(&mut self)->SlideInput {SlideInput{velocity:self.four(),normal:self.four(),side:self.four(),effective_forward:self.four(),reference_forward:self.four(),angular_velocity:self.four(),absolute_speed:self.float(),surface_speed:self.float(),slide:self.float(),elapsed:self.float(),wheel_hardness:self.float()}}
    fn steering(&mut self)->SteeringInput {SteeringInput{turn:self.float(),hard_turn:self.float(),absolute_body_speed:self.float(),flipped_controls_scalar:self.float(),balance:self.float(),truck_tightness:self.float(),pushing:self.word()!=0}}
    fn manual(&mut self)->ManualInput {ManualInput{balance:self.float(),flipped_controls:self.float(),procedural_noise_time:self.float(),absolute_speed:self.float(),animation_noise:self.float(),timestep:self.float(),powersliding:self.word()!=0,braking:self.word()!=0,positive_balance_contact:self.word()!=0,negative_balance_contact:self.word()!=0,reversed_point_selection:self.word()!=0,reference_x:self.four(),reference_z:self.four(),deck_z:self.four(),velocity_frame_z:self.four(),angular_velocity_world:self.four(),correction_point_7888:self.four(),correction_point_7952:self.four()}}
    fn contact(&mut self)->GroundContactFrame {GroundContactFrame{vector_8032:self.four(),vector_8048:self.four(),vector_8064:self.four(),word_8080:self.word(),flag_8084:self.word()!=0,scalar_2752:self.float(),scalar_2756:self.float()}}
    fn force(&mut self)->ForceFrame {ForceFrame{argument_1_2752:self.float(),ground_scalar_1216:self.float(),ground_scalar_1240:self.float(),ground_scalar_1236:self.float(),balance_2720:self.float(),surface_speed_2656:self.float(),axis_384:self.four(),velocity_400:self.four(),axis_544:self.four()}}
}
#[derive(Clone)]
struct ForceFrame {argument_1_2752:f32,ground_scalar_1216:f32,ground_scalar_1240:f32,ground_scalar_1236:f32,balance_2720:f32,surface_speed_2656:f32,axis_384:[f32;4],velocity_400:[f32;4],axis_544:[f32;4]}
#[derive(Clone)]
struct GroundInput {steering:SteeringInput,manual:ManualInput,contact:GroundContactFrame,ground_force:ForceFrame}
struct Toolkit {deck:[[f32;4];4],effective:[[f32;4];4],forward:[f32;4],travel_direction:[f32;4],total_mass:f32,absolute_speed:f32}
struct ToolkitSlot {value:Option<Toolkit>,trace:Shared}
impl ToolkitSlot {fn as_ref(&self)->Option<&Toolkit> {let mut t=self.trace.borrow_mut();t.toolkit_calls+=1;let code=match t.toolkit_calls {1=>1,2=>5,_=>13};t.events.push(code);if code==13&&t.fail==13 {None}else {self.value.as_ref()}}}
struct Processed {category_2516:u32,scalar_2656:f32,surface_mode_2540:u32,state_variant_index_2528:u32,flags_2468:u32,flags_2472:u32,wheel_count_2556:u32,vectors_464_480_496_512_528:[[u32;4];5],vectors_544_560_592_608:[[u32;4];4],vectors_400_416:[[u32;4];2],vectors_720_784_800_816_832_864:[[u32;4];6],gravity_2648:f32,scalar_2652:f32,state_timer_2664:f32,scalar_2764:f32,collision_pose_error_736:[u32;4],timestep_2604:f32,external_physics_1616:External}
struct External {flags:u32}
struct PlayerInput {processed:Processed,toolkit:ToolkitSlot}
#[derive(Clone,Copy)]
struct Edge {flags:u32,point:[f32;4]}
struct Lifecycle {skeleton_elapsed_16505:bool,board_animated_290:u8,edge:Option<Edge>,manual_drag_2724:f32}
struct Spin {spin_angle:f32,spin_speed:f32}
struct AirReckoning {state:Spin}
struct WipeoutState {mode:u32,balance:f32}
struct Wipeout {state:WipeoutState}
struct Fields {slide:f32,balance:f32}
struct Extra {physical_body_spin:f32}
struct AnimationInput {fields:Fields,extra:Extra}
struct BoardFrames {animation_target:[f32;4]}
struct AnimatedSkeleton {board_frames:BoardFrames}
struct SkeletonAir {trace:Shared}
impl SkeletonAir {fn capture_physics_error(&mut self,_:&BoardRuntime,_:&[f32;4]) {self.trace.borrow_mut().events.push(4);}}
struct PumpingMode {unintentional_scalar:f32}
struct PumpingSettings {trace:Shared}
impl PumpingSettings {fn mode(&self,index:u32)->Result<PumpingMode,String> {let mut t=self.trace.borrow_mut();t.events.push(6);t.mode=index;if index>4 {Err(format!("Invalid pumping physics mode {index}"))}else {Ok(PumpingMode{unintentional_scalar:[0.137,0.317,0.731,0.113,0.517][index as usize]})}}}
struct Ground {manual:ManualState,steering:TruckSteeringState,pumping:(),pumping_settings:PumpingSettings}
struct GroundSettings {steering:SteeringSettings,manual:ManualSettings,manual_mode:ManualMode,ground_force:GroundForceSettings,input:GroundInput,trace:Shared}
struct BoardSettings<'a> {steering:&'a SteeringSettings,manual:&'a ManualSettings,manual_mode:ManualMode,ground_force:&'a GroundForceSettings}
impl GroundSettings {
    fn input(&self,_:&Toolkit,_:&Processed,_:&AnimationInput,_:&(),_:f32,_:&Riding,_:&AnimatedSkeleton,_:(),_:physics::ground_runtime::GroundInputObservations)->GroundInput {self.trace.borrow_mut().events.push(7);self.input.clone()}
    fn board(&self)->BoardSettings<'_> {BoardSettings{steering:&self.steering,manual:&self.manual,manual_mode:self.manual_mode,ground_force:&self.ground_force}}
}
struct Reckoning {ground_normal:Vector3}
struct Riding {reckoning:Reckoning,trace:Shared}
impl Riding {fn update_slide_reckoning(&mut self,_:&Processed,_:&Toolkit,_:f32,_:f32) {self.trace.borrow_mut().events.push(2);}}
struct Step {base_truck_transforms:()}
struct PhysicsSettings {wheel_material:RetailContactMaterial,standard_wheel_material:RetailContactMaterial,step:Step}
struct ActualGroundRuntime {wall_ride:WallRideSettings,collision:CollisionResponseSettings,collision_force:Option<CollisionForceResponse>}
impl ActualGroundRuntime {
// ORIGINAL_GROUND_RUNTIME_METHODS
}
use skate_core::{physics::deck_angular_correction,riding::{ground_contact_response::wall_ride_response,collision_response::collision_response}};
fn xyz(v:[f32;4])->Vector3 {Vector3::new(v[0],v[1],v[2])}
struct GroundRuntime {actual:ActualGroundRuntime,trace:Shared}
impl GroundRuntime {
    fn contact_response_with_previous(&self,f:GroundContactFrame,p:WallRidePhysical,v:[f32;4])->GroundContactResponse {self.actual.contact_response_with_previous(f,p,v)}
    fn apply_angular_displacement(&mut self,b:&mut BoardRuntime,v:[f32;4]) {self.actual.apply_angular_displacement(b,v)}
    fn set_animated_velocity(&mut self,b:&mut BoardRuntime,v:[f32;4]) {self.trace.borrow_mut().launch=Some(v);self.actual.set_animated_velocity(b,v)}
    fn calculate_collision_force(&mut self,p:CollisionResponsePhysical)->Option<CollisionForceResponse> {let mut t=self.trace.borrow_mut();t.events.push(9);t.collision=Some(p);drop(t);self.actual.calculate_collision_force(p)}
}
struct Launch {start_velocity:[f32;4],player_jumped:bool}
struct Trajectory {trace:Shared}
impl Trajectory {
    fn launch(&mut self,launch:Launch,_:(),_:&())->Result<(),String> {self.trace.borrow_mut().launch=Some(launch.start_velocity);stage(&self.trace,12)}
    fn update(&mut self,_:(),_:&(),_:physics::air_trajectory::GrindContext)->Result<(),String> {stage(&self.trace,15)}
}
mod physics {
    use super::*;
    pub struct GamePhysics {pub board:BoardRuntime,pub settings:PhysicsSettings,pub riding:Riding,pub world:()}
    pub struct SkaterRuntime {pub player_input:PlayerInput,pub ground_lifecycle:Lifecycle,pub air_reckoning:AirReckoning,pub ground:Ground,pub wipeout:Wipeout,pub slide_state:slide_state::SlideState,pub animation_input:AnimationInput,pub animated_skeleton:AnimatedSkeleton,pub skeleton_air:SkeletonAir,pub ground_settings:GroundSettings,pub ground_runtime:GroundRuntime,pub trajectory:Trajectory,pub trace:Shared}
    pub mod ground_runtime {pub struct GroundInputObservations {pub manual_drag_2724:f32,pub trajectory_state_bits:u32,pub edge_flags:u32,pub edge_point:[f32;4]}}
    pub mod input_phase {use super::*;pub fn update_ground(_:&mut GamePhysics,s:&mut SkaterRuntime)->Result<(),String> {stage(&s.trace,3)?;if s.trace.borrow().fail==5 {s.player_input.toolkit.value=None;}Ok(())}}
    pub mod air_phase {use super::*;pub fn launch_info(_:&mut GamePhysics,s:&mut SkaterRuntime)->Result<Launch,String> {stage(&s.trace,10)?;Ok(Launch{start_velocity:[0.137,0.317,0.731,0.113],player_jumped:false})}pub fn selector_input(_:&mut GamePhysics,s:&mut SkaterRuntime)->Result<(),String> {stage(&s.trace,11)}}
    pub mod air_trajectory {use super::*;pub struct GrindContext;impl GrindContext {pub fn from_processed(_:&Processed,_:[f32;4])->Self {ACTIVE_TRACE.with(|t|t.borrow().as_ref().unwrap().borrow_mut().events.push(14));Self}}}
    pub mod slide_state {
        use super::{GamePhysics,SkaterRuntime};
        use skate_core::{math::Vector3,physics::contact::RetailContactMaterial,player::slide_state::{SlideSettings,SlideSurface}};
        pub struct SlideState {pub state:skate_core::player::slide_state::SlideState,pub settings:SlideSettings,pub surfaces:Vec<(SlideSurface,RetailContactMaterial)>,pub manual_scalar:f32}
        mod settings {
// ORIGINAL_SLIDE_SETTINGS
        }
// ORIGINAL_SLIDE_FUNCTIONS
        mod update {
// ORIGINAL_SLIDE_BOARD
        }
    }
}
thread_local! {static ACTIVE_TRACE:RefCell<Option<Shared>>=const {RefCell::new(None)};}
struct Output(Vec<u8>);
impl Output {
    fn word(&mut self,v:u32) {self.0.extend(v.to_le_bytes());}
    fn floats(&mut self,values:impl IntoIterator<Item=f32>) {for v in values {self.word(v.to_bits());}}
    fn vector(&mut self,v:Vector3) {self.floats([v.x,v.y,v.z]);}
    fn string(&mut self,v:&str) {self.word(v.len() as u32);self.0.extend(v.as_bytes());}
    fn body(&mut self,b:BodySnapshot) {let r=b.rates;let d=b.inertia;self.word(b.state_flags);self.floats([r.orientation.x,r.orientation.y,r.orientation.z,r.orientation.w]);for matrix in [r.basis,r.world_inverse_inertia] {for col in matrix.columns {self.floats(col);}}for v in [r.position,r.linear_velocity,r.angular_velocity,r.force_acceleration,r.torque_acceleration] {self.vector(v);}self.floats([r.kinetic_energy]);self.word(r.cool_down);self.vector(d.inverse_tensor);self.floats([d.inverse_mass,d.spherical,d.maximum_linear_velocity,d.maximum_angular_velocity,d.linear_drag,d.angular_drag]);}
    fn snapshot(&mut self,p:&physics::GamePhysics,s:&physics::SkaterRuntime) {
        let state=&s.slide_state.state;self.floats([state.start_speed,state.steering_push,state.damped_turn]);self.word(state.flag48 as u32);self.word(state.wall_riding as u32);let m=s.ground.manual;let t=s.ground.steering;self.floats([m.filtered_angle_error,m.target_angle,m.measured_angle,m.angular_correction,m.elapsed,t.deck_tilt,t.targets[0],t.targets[1],t.activation_time[0],t.activation_time[1]]);self.word(s.ground_lifecycle.skeleton_elapsed_16505 as u32);self.floats([s.air_reckoning.state.spin_angle,s.air_reckoning.state.spin_speed]);self.word(s.ground_lifecycle.board_animated_290 as u32);self.word(s.wipeout.state.mode);self.floats([s.wipeout.state.balance]);let m=p.settings.wheel_material;self.floats([m.static_friction,m.dynamic_friction,m.restitution]);for b in p.board.bodies() {self.body(*b);}for w in p.board.hook().drive.frames {self.word(w);}for w in p.board.hook().drive.dynamics {self.word(w);}self.word(p.board.forces().entries().len() as u32);for f in p.board.forces().entries() {self.word(f.tag);self.vector(f.force_world);self.vector(f.point_body);}self.word(s.ground_runtime.actual.collision_force.is_some() as u32);if let Some(f)=s.ground_runtime.actual.collision_force {self.floats(f.force_2528);self.floats(f.point_2544);self.floats(f.vector_2592);}let trace=s.trace.borrow();self.word(trace.events.len() as u32);for e in &trace.events {self.word(*e);}self.word(trace.mode);self.word(trace.collision.is_some() as u32);if let Some(c)=trace.collision {self.word(c.flags_2472);for v in [c.collision_displacement,c.velocity,c.forward,c.up,c.ground_normal] {self.floats(v);}self.floats([c.time_step,c.mass]);}self.word(trace.launch.is_some() as u32);if let Some(v)=trace.launch {self.floats(v);}
    }
}
fn read_update(i:&mut Input,p:&mut physics::GamePhysics,s:&mut physics::SkaterRuntime) {
    let fail=i.word();let valid=i.word()!=0;let surface=i.word();let mode=i.word();let fa=i.word();let fb=i.word();let count=i.word();let slide=i.slide();let up=i.four();let displacement=i.four();let velocity=i.four();let forward=i.four();let normal=i.three();let mass=i.float();let gravity=i.float();let scalar=i.float();let dt=i.float();let steering=i.steering();let manual=i.manual();let contact=i.contact();let force=i.force();
    let processed=&mut s.player_input.processed;processed.surface_mode_2540=surface;processed.state_variant_index_2528=mode;processed.flags_2468=fa;processed.flags_2472=fb;processed.wheel_count_2556=count;processed.vectors_464_480_496_512_528[0]=slide.normal.map(f32::to_bits);processed.vectors_544_560_592_608[0]=up.map(f32::to_bits);processed.vectors_400_416=[slide.velocity.map(f32::to_bits),velocity.map(f32::to_bits)];processed.vectors_720_784_800_816_832_864[0]=slide.angular_velocity.map(f32::to_bits);processed.gravity_2648=gravity;processed.scalar_2652=scalar;processed.scalar_2656=slide.surface_speed;processed.state_timer_2664=slide.elapsed;processed.scalar_2764=slide.wheel_hardness;processed.collision_pose_error_736=displacement.map(f32::to_bits);processed.timestep_2604=dt;
    s.player_input.toolkit.value=valid.then_some(Toolkit{deck:[slide.side,[0.,1.,0.,0.137],[0.,0.,1.,0.317],[0.137,0.317,0.731,1.]],effective:[[1.,0.,0.,0.],[0.,1.,0.,0.],slide.effective_forward,[0.137,0.317,0.731,1.]],forward:slide.reference_forward,travel_direction:forward,total_mass:mass,absolute_speed:slide.absolute_speed});p.riding.reckoning.ground_normal=normal;s.animation_input.fields.slide=slide.slide;s.animation_input.fields.balance=manual.balance;s.ground_settings.input=GroundInput{steering,manual,contact,ground_force:force};let mut t=s.trace.borrow_mut();*t=Trace{fail,mode:0xffffffff,..Trace::default()};
}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let data=skate_data::collections::Collections::load(std::path::Path::new(&args[1]))?;let steering=stock::steering(&data)?;let manual=stock::manual(&data)?;let manual_mode=stock::manual_mode(&data,"normal")?;let force=stock::force(&data)?;let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).map_err(|e|e.to_string())?;let mut i=Input{bytes,at:0};let cases=i.word();let mut out=Output(Vec::new());
    for c in 0..cases {
        let wall=WallRideSettings{anti_gravity_vs_time:i.curve(),max_dot_floor_wall:i.float(),foot_force_time:i.float(),auto_jump_height:i.float(),max_time:i.float(),velocity_time_to_consider:i.float(),auto_jump_y_down_scalar:i.float(),auto_jump_force:i.float()};let collision=CollisionResponseSettings{maximum_velocity_delta:i.float(),force_y_offset:i.float(),force_scalar:i.float(),target_displacement_velocity:i.float(),torque_vs_angle:i.curve()};let state=skate_core::player::slide_state::SlideState{start_speed:i.float(),steering_push:i.float(),damped_turn:i.float(),flag48:i.word()!=0,wall_riding:i.word()!=0};let m=ManualState{filtered_angle_error:i.float(),target_angle:i.float(),measured_angle:i.float(),angular_correction:i.float(),elapsed:i.float()};let t=TruckSteeringState{deck_tilt:i.float(),targets:[i.float(),i.float()],activation_time:[i.float(),i.float()]};let elapsed=i.word()!=0;let angle=i.float();let speed=i.float();let animated=i.word() as u8;let mode=i.word();let balance=i.float();let trace=Rc::new(RefCell::new(Trace{mode:0xffffffff,..Trace::default()}));ACTIVE_TRACE.with(|t|*t.borrow_mut()=Some(trace.clone()));
        let simulation=RetailSimulationStep{time_step:1./60.,frequency:60.,cool_down:9,minimum_energy:0.001,gravity_acceleration:Vector3::new(0.,-9.81,0.)};let mut board=BoardRuntime::new(skate_core::physics::mass::default_skateboard_mass_properties(),authored_body_transforms(AuthoredTransformInputs::STOCK),RetailAffineTransform{basis:Basis3{columns:[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]},translation:Vector3::new(0.,2.,0.)},simulation,BoardMotion::Active);board.hook_mut().drive.enable_angular_soft();for b in board.bodies_mut() {b.rates.linear_velocity=i.three();b.rates.angular_velocity=i.three();b.rates.force_acceleration=i.three();b.rates.torque_acceleration=i.three();b.inertia.linear_drag=i.float();}let preseed=i.word();for _ in 0..preseed {board.forces_mut().append(QueuedPointForce{tag:i.word(),force_world:i.three(),point_body:i.three()});}
        let mut stock=physics::slide_state::SlideState::load(&data)?;stock.state=state;let first_input=GroundInput{steering:SteeringInput::default(),manual:ManualInput{balance:0.,flipped_controls:1.,procedural_noise_time:0.,absolute_speed:1.,animation_noise:0.,timestep:1./60.,powersliding:false,braking:false,positive_balance_contact:false,negative_balance_contact:false,reversed_point_selection:false,reference_x:[1.,0.,0.,0.],reference_z:[0.,0.,1.,0.],deck_z:[0.,0.,1.,0.],velocity_frame_z:[0.,0.,1.,0.],angular_velocity_world:[0.,0.,0.,0.],correction_point_7888:[0.,0.,0.,0.],correction_point_7952:[0.,0.,0.,0.]},contact:GroundContactFrame{vector_8032:[0.;4],vector_8048:[0.;4],vector_8064:[0.;4],word_8080:0,flag_8084:false,scalar_2752:0.,scalar_2756:0.},ground_force:ForceFrame{argument_1_2752:0.,ground_scalar_1216:0.,ground_scalar_1240:0.,ground_scalar_1236:0.,balance_2720:0.,surface_speed_2656:0.,axis_384:[0.;4],velocity_400:[0.;4],axis_544:[0.;4]}};
        let mut p=physics::GamePhysics{board,settings:PhysicsSettings{wheel_material:RetailContactMaterial{static_friction:0.137,dynamic_friction:0.317,restitution:0.731},standard_wheel_material:RetailContactMaterial{static_friction:0.113,dynamic_friction:0.517,restitution:0.173},step:Step{base_truck_transforms:()}},riding:Riding{reckoning:Reckoning{ground_normal:Vector3::ZERO},trace:trace.clone()},world:()};
        let mut s=physics::SkaterRuntime{player_input:PlayerInput{processed:Processed{category_2516:100,scalar_2656:0.,surface_mode_2540:1,state_variant_index_2528:0,flags_2468:0,flags_2472:0,wheel_count_2556:0,vectors_464_480_496_512_528:[[0;4];5],vectors_544_560_592_608:[[0;4];4],vectors_400_416:[[0;4];2],vectors_720_784_800_816_832_864:[[0;4];6],gravity_2648:0.,scalar_2652:0.,state_timer_2664:0.,scalar_2764:0.,collision_pose_error_736:[0;4],timestep_2604:0.,external_physics_1616:External{flags:0}},toolkit:ToolkitSlot{value:None,trace:trace.clone()}},ground_lifecycle:Lifecycle{skeleton_elapsed_16505:elapsed,board_animated_290:animated,edge:None,manual_drag_2724:0.},air_reckoning:AirReckoning{state:Spin{spin_angle:angle,spin_speed:speed}},ground:Ground{manual:m,steering:t,pumping:(),pumping_settings:PumpingSettings{trace:trace.clone()}},wipeout:Wipeout{state:WipeoutState{mode,balance}},slide_state:stock,animation_input:AnimationInput{fields:Fields{slide:0.,balance:0.},extra:Extra{physical_body_spin:0.}},animated_skeleton:AnimatedSkeleton{board_frames:BoardFrames{animation_target:[0.137,0.317,0.731,0.113]}},skeleton_air:SkeletonAir{trace:trace.clone()},ground_settings:GroundSettings{steering,manual:manual.clone(),manual_mode,ground_force:force.clone(),input:first_input,trace:trace.clone()},ground_runtime:GroundRuntime{actual:ActualGroundRuntime{wall_ride:wall,collision,collision_force:None},trace:trace.clone()},trajectory:Trajectory{trace:trace.clone()},trace:trace.clone()};
        let count=i.word();for tick in 0..count {let op=i.word();*trace.borrow_mut()=Trace{mode:0xffffffff,..Trace::default()};let result=match op {0=>{s.player_input.processed.category_2516=i.word();s.player_input.processed.scalar_2656=i.float();physics::slide_state::enter(&mut p,&mut s)},1=>physics::slide_state::exit(&mut p,&mut s),2=>{read_update(&mut i,&mut p,&mut s);physics::slide_state::update(&mut p,&mut s)},3=>{p.board.clear_forces();Ok(())},4=>{p.board.forces_mut().append(QueuedPointForce{tag:i.word(),force_world:i.three(),point_body:i.three()});Ok(())},_=>return Err("Invalid Slide runtime operation".into())};out.word(c);out.word(tick);out.word(op);out.word(result.is_ok() as u32);out.string(result.as_ref().err().map_or("",String::as_str));let mut row=Output(Vec::new());row.snapshot(&p,&s);out.word((row.0.len()/4) as u32);out.0.extend(row.0);}
    }
    assert_eq!(i.at,i.bytes.len());std::io::stdout().write_all(&out.0).map_err(|e|e.to_string())?;Ok(())
}
fn main() {if let Err(error)=run() {eprintln!("{error}");std::process::exit(2);}}
