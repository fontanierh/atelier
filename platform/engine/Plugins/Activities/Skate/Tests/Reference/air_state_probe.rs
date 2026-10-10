use skate_core::air::{state::*, trajectory::LaunchInfo};
use skate_core::point_graph::PointGraph;
use skate_data::collections::Collections;
use std::{
    cell::RefCell,
    io::{Read, Write},
    rc::Rc,
};
#[path = "../../../air-state-stock-constant.rs"]
mod stock_constant;
type Trace = Rc<RefCell<Output>>;
#[derive(Default)]
struct Output(Vec<u32>);
impl Output {
    fn word(&mut self, v: u32) {
        self.0.push(v)
    }
    fn float(&mut self, v: f32) {
        self.word(v.to_bits())
    }
    fn vector(&mut self, v: [f32; 4]) {
        for x in v {
            self.float(x)
        }
    }
    fn matrix(&mut self, v: [[f32; 4]; 4]) {
        for x in v {
            self.vector(x)
        }
    }
    fn string(&mut self, v: &str) {
        self.word(v.len() as u32);
        for chunk in v.as_bytes().chunks(4) {
            let mut w = [0; 4];
            w[..chunk.len()].copy_from_slice(chunk);
            self.word(u32::from_le_bytes(w));
        }
    }
    fn status(&mut self, v: Result<(), String>) {
        match v {
            Ok(()) => self.word(1),
            Err(e) => {
                self.word(0);
                self.string(&e);
            }
        }
    }
}
struct Input {
    words: Vec<u32>,
    at: usize,
}
impl Input {
    fn word(&mut self) -> u32 {
        let w = self.words[self.at];
        self.at += 1;
        w
    }
    fn float(&mut self) -> f32 {
        f32::from_bits(self.word())
    }
    fn vector(&mut self) -> [f32; 4] {
        std::array::from_fn(|_| self.float())
    }
    fn matrix(&mut self) -> [[f32; 4]; 4] {
        std::array::from_fn(|_| self.vector())
    }
    fn raw(&mut self) -> [u32; 4] {
        std::array::from_fn(|_| self.word())
    }
    fn frame(&mut self) -> PhysicsAirFrame {
        PhysicsAirFrame {
            current_velocity_400: self.vector(),
            ground_position_y_500: self.float(),
            trajectory_position_592: self.vector(),
            trajectory_velocity_608: self.vector(),
            jump_velocity_848: self.vector(),
            flags_2468: self.word(),
            previous_physics_state_2504: self.word() as i32,
            previous_physics_category_2516: self.word() as i32,
            frames_since_jump_correction_2576: self.word() as i32,
            delta_time_2604: self.float(),
            body_spin_input_2640: self.float(),
            gravity_y_2648: self.float(),
            state_timer_2664: self.float(),
        }
    }
    fn reckoning(&mut self) -> PhysicsAirReckoningFields {
        PhysicsAirReckoningFields {
            current_landing_normal_1152: self.vector(),
            collision_reference_normal_1216: self.vector(),
            body_spin_angle_1568: self.float(),
            body_spin_speed_1572: self.float(),
        }
    }
    fn settings(&mut self) -> PhysicsAirSettings {
        PhysicsAirSettings {
            body_spin_over_time_320: PointGraph {
                x: std::array::from_fn(|_| self.float()),
                y: std::array::from_fn(|_| self.float()),
            },
            landing_normal_blend_388: self.float(),
            body_spin_scale_428: self.float(),
            landing_normal_angle_limit_444: self.float(),
        }
    }
    fn trajectory(&mut self) -> AirTrajectory {
        AirTrajectory {
            position: self.vector(),
            velocity: self.vector(),
            acceleration: self.vector(),
            scalar_48: self.float(),
        }
    }
    fn state(&mut self) -> PhysicsAirState {
        PhysicsAirState {
            centre_of_mass_trajectory: self.trajectory(),
            landing_normal: self.vector(),
            time_in_state: self.float(),
            start_y: self.float(),
            max_y: self.float(),
            reached_apex: self.word() != 0,
            use_centre_of_mass_velocity: self.word() != 0,
            selector_latch_174: self.word() != 0,
            trajectory_query_countdown: self.word() as i32,
        }
    }
    fn info(&mut self) -> LaunchInfo {
        LaunchInfo {
            reckoning_transform: self.matrix(),
            reckoning_inverse: self.matrix(),
            start_velocity: self.vector(),
            com_velocity: self.vector(),
            skeleton_vector_160: self.vector(),
            skeleton_vector_176: self.vector(),
            board_position: self.vector(),
            animation_com_position: self.vector(),
            start_position_override: self.vector(),
            board_position_override: self.vector(),
            cone_angle_x: self.float(),
            cone_angle_z: self.float(),
            timestep: self.float(),
            player_jumped: self.word() != 0,
            use_position_override: self.word() != 0,
            trajectory_count: self.word() as u16,
        }
    }
}
fn frame(o: &mut Output, f: &PhysicsAirFrame) {
    o.vector(f.current_velocity_400);
    o.float(f.ground_position_y_500);
    o.vector(f.trajectory_position_592);
    o.vector(f.trajectory_velocity_608);
    o.vector(f.jump_velocity_848);
    for v in [
        f.flags_2468,
        f.previous_physics_state_2504 as u32,
        f.previous_physics_category_2516 as u32,
        f.frames_since_jump_correction_2576 as u32,
    ] {
        o.word(v)
    }
    for v in [
        f.delta_time_2604,
        f.body_spin_input_2640,
        f.gravity_y_2648,
        f.state_timer_2664,
    ] {
        o.float(v)
    }
}
fn reckoning(o: &mut Output, r: &PhysicsAirReckoningFields) {
    o.vector(r.current_landing_normal_1152);
    o.vector(r.collision_reference_normal_1216);
    o.float(r.body_spin_angle_1568);
    o.float(r.body_spin_speed_1572)
}
fn trajectory(o: &mut Output, t: &AirTrajectory) {
    o.vector(t.position);
    o.vector(t.velocity);
    o.vector(t.acceleration);
    o.float(t.scalar_48)
}
fn state(o: &mut Output, s: &PhysicsAirState) {
    trajectory(o, &s.centre_of_mass_trajectory);
    o.vector(s.landing_normal);
    for v in [s.time_in_state, s.start_y, s.max_y] {
        o.float(v)
    }
    for v in [
        s.reached_apex,
        s.use_centre_of_mass_velocity,
        s.selector_latch_174,
    ] {
        o.word(u32::from(v))
    }
    o.word(s.trajectory_query_countdown as u32)
}
fn info(o: &mut Output, l: &LaunchInfo) {
    o.matrix(l.reckoning_transform);
    o.matrix(l.reckoning_inverse);
    for v in [
        l.start_velocity,
        l.com_velocity,
        l.skeleton_vector_160,
        l.skeleton_vector_176,
        l.board_position,
        l.animation_com_position,
        l.start_position_override,
        l.board_position_override,
    ] {
        o.vector(v)
    }
    for v in [l.cone_angle_x, l.cone_angle_z, l.timestep] {
        o.float(v)
    }
    o.word(u32::from(l.player_jumped));
    o.word(u32::from(l.use_position_override));
    o.word(l.trajectory_count as u32)
}
struct TracedInfo {
    data: LaunchInfo,
    trace: Trace,
}
impl PhysicsAirLaunchInfo for TracedInfo {
    fn set_start_velocity(&mut self, v: [f32; 4]) {
        let mut o = self.trace.borrow_mut();
        o.word(100);
        o.vector(v);
        self.data.start_velocity = v;
    }
    fn centre_of_mass_animation_position(&self) -> [f32; 4] {
        let mut o = self.trace.borrow_mut();
        o.word(101);
        o.vector(self.data.animation_com_position);
        self.data.animation_com_position
    }
    fn set_trajectory_start_position_override(&mut self, v: [f32; 4]) {
        let mut o = self.trace.borrow_mut();
        o.word(102);
        o.vector(v);
        self.data.start_position_override = v;
    }
    fn set_board_position_override(&mut self, v: [f32; 4]) {
        let mut o = self.trace.borrow_mut();
        o.word(103);
        o.vector(v);
        self.data.board_position_override = v;
    }
    fn cone_angles(&self) -> [f32; 2] {
        let mut o = self.trace.borrow_mut();
        o.word(104);
        o.float(self.data.cone_angle_x);
        o.float(self.data.cone_angle_z);
        [self.data.cone_angle_x, self.data.cone_angle_z]
    }
    fn set_cone_angles(&mut self, v: [f32; 2]) {
        let mut o = self.trace.borrow_mut();
        o.word(105);
        o.float(v[0]);
        o.float(v[1]);
        self.data.cone_angle_x = v[0];
        self.data.cone_angle_z = v[1];
    }
    fn set_player_jumped(&mut self, v: bool) {
        let mut o = self.trace.borrow_mut();
        o.word(106);
        o.word(u32::from(v));
        self.data.player_jumped = v;
    }
    fn set_use_trajectory_start_position_override(&mut self, v: bool) {
        let mut o = self.trace.borrow_mut();
        o.word(107);
        o.word(u32::from(v));
        self.data.use_position_override = v;
    }
    fn set_trajectory_count(&mut self, v: u16) {
        let mut o = self.trace.borrow_mut();
        o.word(108);
        o.word(v as u32);
        self.data.trajectory_count = v;
    }
}
struct Runtime {
    trace: Trace,
    fill: LaunchInfo,
    height: f32,
    velocity: [f32; 4],
    query_started: bool,
    normal: Option<[f32; 4]>,
    com_ready: bool,
    reckoning: PhysicsAirReckoningFields,
    collision: bool,
    force: AirBoardForce,
}
impl Runtime {
    fn read(i: &mut Input) -> Self {
        let fill = i.info();
        let height = i.float();
        let velocity = i.vector();
        let query_started = i.word() != 0;
        let has_normal = i.word() != 0;
        let normal = i.vector();
        let com_ready = i.word() != 0;
        let reckoning = i.reckoning();
        let collision = i.word() != 0;
        let force = AirBoardForce {
            force_world: i.vector(),
            point_board_local: i.vector(),
        };
        Self {
            trace: Rc::new(RefCell::new(Output::default())),
            fill,
            height,
            velocity,
            query_started,
            normal: has_normal.then_some(normal),
            com_ready,
            reckoning,
            collision,
            force,
        }
    }
}
impl PhysicsAirMath for Runtime {
    fn minimum_vminfp(&mut self, a: f32, b: f32) -> f32 {
        let v = AirMath.minimum_vminfp(a, b);
        let mut o = self.trace.borrow_mut();
        o.word(110);
        o.float(a);
        o.float(b);
        o.float(v);
        v
    }
    fn length_squared_vmsum3fp(&mut self, a: [f32; 4]) -> f32 {
        let v = AirMath.length_squared_vmsum3fp(a);
        let mut o = self.trace.borrow_mut();
        o.word(111);
        o.vector(a);
        o.float(v);
        v
    }
    fn length_vmsum3fp_vrsqrte(&mut self, a: [f32; 4]) -> f32 {
        let v = AirMath.length_vmsum3fp_vrsqrte(a);
        let mut o = self.trace.borrow_mut();
        o.word(112);
        o.vector(a);
        o.float(v);
        v
    }
    fn clamp_vector_within_max_length(&mut self, a: [f32; 4], m: f32) -> [f32; 4] {
        let v = AirMath.clamp_vector_within_max_length(a, m);
        let mut o = self.trace.borrow_mut();
        o.word(113);
        o.vector(a);
        o.float(m);
        o.vector(v);
        v
    }
}
impl PhysicsAirRuntime for Runtime {
    type LaunchInfo = TracedInfo;
    fn set_air_collision_update_enabled(&mut self, v: bool) {
        let mut o = self.trace.borrow_mut();
        o.word(1);
        o.word(u32::from(v))
    }
    fn set_skeleton_collision_state(&mut self, v: u32) {
        let mut o = self.trace.borrow_mut();
        o.word(2);
        o.word(v)
    }
    fn set_skeleton_inverse_kinematics_enabled(&mut self, v: bool) {
        let mut o = self.trace.borrow_mut();
        o.word(3);
        o.word(u32::from(v))
    }
    fn enable_board_angular_drive_only(&mut self) {
        self.trace.borrow_mut().word(4)
    }
    fn set_footplant_flag_240(&mut self, v: bool) {
        let mut o = self.trace.borrow_mut();
        o.word(5);
        o.word(u32::from(v))
    }
    fn reset_footplants(&mut self) {
        self.trace.borrow_mut().word(6)
    }
    fn board_transform_height(&mut self) -> f32 {
        let mut o = self.trace.borrow_mut();
        o.word(7);
        o.float(self.height);
        self.height
    }
    fn request_skeleton_heading_update(&mut self) {
        self.trace.borrow_mut().word(8)
    }
    fn update_air_collision(&mut self) {
        self.trace.borrow_mut().word(9)
    }
    fn trajectory_query_just_started(&self) -> bool {
        let mut o = self.trace.borrow_mut();
        o.word(10);
        o.word(u32::from(self.query_started));
        self.query_started
    }
    fn construct_trajectory_launch_info(&mut self) -> Self::LaunchInfo {
        let data = LaunchInfo::default();
        let mut o = self.trace.borrow_mut();
        o.word(11);
        info(&mut o, &data);
        TracedInfo {
            data,
            trace: self.trace.clone(),
        }
    }
    fn fill_skeleton_launch_info(&mut self, out: &mut Self::LaunchInfo) {
        let mut o = self.trace.borrow_mut();
        o.word(12);
        info(&mut o, &self.fill);
        out.data = self.fill;
    }
    fn launch_trajectory(&mut self, l: &Self::LaunchInfo) {
        let mut o = self.trace.borrow_mut();
        o.word(13);
        info(&mut o, &l.data);
    }
    fn update_trajectory_selector(&mut self) {
        self.trace.borrow_mut().word(14)
    }
    fn selector_landing_normal(&self) -> Option<[f32; 4]> {
        let mut o = self.trace.borrow_mut();
        o.word(15);
        o.word(u32::from(self.normal.is_some()));
        if let Some(n) = self.normal {
            o.vector(n)
        }
        self.normal
    }
    fn selector_centre_of_mass_trajectory_ready(&self) -> bool {
        let mut o = self.trace.borrow_mut();
        o.word(16);
        o.word(u32::from(self.com_ready));
        self.com_ready
    }
    fn angle_between_vectors(&mut self, a: [f32; 4], b: [f32; 4]) -> f32 {
        let v = angle_between_vectors(a, b);
        let mut o = self.trace.borrow_mut();
        o.word(17);
        o.vector(a);
        o.vector(b);
        o.float(v);
        v
    }
    fn update_reckoning_air_states(
        &mut self,
        n: [f32; 4],
        blend: f32,
        spin: f32,
        flip: f32,
    ) -> PhysicsAirReckoningFields {
        let mut o = self.trace.borrow_mut();
        o.word(18);
        o.vector(n);
        o.float(blend);
        o.float(spin);
        o.float(flip);
        reckoning(&mut o, &self.reckoning);
        self.reckoning
    }
    fn update_known_air_skeleton(&mut self, p: [f32; 4]) {
        let mut o = self.trace.borrow_mut();
        o.word(19);
        o.vector(p)
    }
    fn update_animated_skateboard_skeleton(&mut self, v: bool) {
        let mut o = self.trace.borrow_mut();
        o.word(20);
        o.word(u32::from(v))
    }
    fn update_board_steering_tilt(&mut self, v: f32) {
        let mut o = self.trace.borrow_mut();
        o.word(21);
        o.float(v)
    }
    fn calculate_air_collision_force(&mut self, n: [f32; 4], out: &mut AirBoardForce) -> bool {
        let mut o = self.trace.borrow_mut();
        o.word(22);
        o.vector(n);
        o.vector(out.force_world);
        o.vector(out.point_board_local);
        o.word(u32::from(self.collision));
        o.vector(self.force.force_world);
        o.vector(self.force.point_board_local);
        *out = self.force;
        self.collision
    }
    fn enqueue_board_force(&mut self, tag: u32, f: AirBoardForce) {
        let mut o = self.trace.borrow_mut();
        o.word(23);
        o.word(tag);
        o.vector(f.force_world);
        o.vector(f.point_board_local)
    }
    fn set_board_velocity(&mut self, v: [f32; 4]) {
        let mut o = self.trace.borrow_mut();
        o.word(24);
        o.vector(v)
    }
    fn enable_skateboard_error_on_skeleton(&mut self) {
        self.trace.borrow_mut().word(25)
    }
    fn board_body_velocity(&mut self) -> [f32; 4] {
        let mut o = self.trace.borrow_mut();
        o.word(26);
        o.vector(self.velocity);
        self.velocity
    }
    fn check_for_air_wipeout(&mut self, v: bool) {
        let mut o = self.trace.borrow_mut();
        o.word(27);
        o.word(u32::from(v))
    }
}
// Data-only owner shell for the unchanged active-host input module. Every field
// read by frame/selector_input/launch_info is bound explicitly by the protocol.
// No method or producer implementation is replaced in a tested path.
mod bindings {
    use super::*;
    pub struct External {
        pub flags: u32,
    }
    pub struct Processed {
        pub vectors_400_416: [[u32; 4]; 2],
        pub vectors_464_480_496_512_528: [[u32; 4]; 5],
        pub vectors_544_560_592_608: [[u32; 4]; 4],
        pub prepared_jump_704: [u32; 4],
        pub flags_2468: u32,
        pub flags_2472: u32,
        pub flags_2476: u32,
        pub state_2504: u32,
        pub category_2516: u32,
        pub state_variant_index_2528: u32,
        pub timestep_2604: f32,
        pub transition_2636: f32,
        pub gravity_2648: f32,
        pub state_timer_2664: f32,
        pub external_physics_1616: External,
    }
    pub struct Toolkit {
        pub deck: [[f32; 4]; 4],
    }
    pub struct PlayerInput {
        pub processed: Processed,
        pub toolkit: Option<Toolkit>,
    }
    pub struct Post {
        pub jump_reference: [u32; 4],
        pub jump_fix_frames: u32,
    }
    pub struct PlayerState {
        pub post: Post,
    }
    pub struct Fields {
        pub body_spin: f32,
    }
    pub struct AnimationInput {
        pub fields: Fields,
    }
    pub struct BoardFrames {
        pub local_centre_of_mass: [f32; 4],
        pub local_board_position: [f32; 4],
    }
    pub struct AnimatedSkeleton {
        pub board_frames: BoardFrames,
    }
    pub struct TrajectorySettings {
        pub cone_x: f32,
        pub cone_z: f32,
    }
    pub struct Trajectory {
        pub settings: TrajectorySettings,
    }
    pub struct SkaterRuntime {
        pub player_input: PlayerInput,
        pub player_state: PlayerState,
        pub animation_input: AnimationInput,
        pub air_settings: input::AirSettings,
        pub trajectory: Trajectory,
        pub animated_skeleton: AnimatedSkeleton,
    }
    pub struct Frames {
        pub system: [[f32; 4]; 4],
        pub inverse_system: [[f32; 4]; 4],
    }
    pub struct Riding {
        pub reckoning_frames: Frames,
    }
    #[derive(Clone, Copy, Debug, PartialEq)]
    pub struct Vector3 {
        pub x: f32,
        pub y: f32,
        pub z: f32,
    }
    pub struct Simulation {
        pub gravity_acceleration: Vector3,
    }
    pub struct Step {
        pub simulation: Simulation,
    }
    pub struct Settings {
        pub step: Step,
    }
    pub struct GamePhysics {
        pub settings: Settings,
        pub riding: Riding,
    }
    pub mod input;
    pub fn read(i: &mut Input, data: &Collections) -> (GamePhysics, SkaterRuntime) {
        let vectors_400_416 = std::array::from_fn(|_| i.raw());
        let vectors_464_480_496_512_528 = std::array::from_fn(|_| i.raw());
        let vectors_544_560_592_608 = std::array::from_fn(|_| i.raw());
        let prepared_jump_704 = i.raw();
        let jump_reference = i.raw();
        let flags_2468 = i.word();
        let flags_2472 = i.word();
        let flags_2476 = i.word();
        let state_2504 = i.word();
        let category_2516 = i.word();
        let state_variant_index_2528 = i.word();
        let jump_fix_frames = i.word();
        let external = i.word();
        let timestep_2604 = i.float();
        let transition_2636 = i.float();
        let gravity_2648 = i.float();
        let state_timer_2664 = i.float();
        let body_spin = i.float();
        let gravity = i.vector();
        let system = i.matrix();
        let inverse_system = i.matrix();
        let local_centre_of_mass = i.vector();
        let local_board_position = i.vector();
        let has_toolkit = i.word() != 0;
        let deck = i.matrix();
        let cone_x = i.float();
        let cone_z = i.float();
        let skater = SkaterRuntime {
            player_input: PlayerInput {
                processed: Processed {
                    vectors_400_416,
                    vectors_464_480_496_512_528,
                    vectors_544_560_592_608,
                    prepared_jump_704,
                    flags_2468,
                    flags_2472,
                    flags_2476,
                    state_2504,
                    category_2516,
                    state_variant_index_2528,
                    timestep_2604,
                    transition_2636,
                    gravity_2648,
                    state_timer_2664,
                    external_physics_1616: External { flags: external },
                },
                toolkit: has_toolkit.then_some(Toolkit { deck }),
            },
            player_state: PlayerState {
                post: Post {
                    jump_reference,
                    jump_fix_frames,
                },
            },
            animation_input: AnimationInput {
                fields: Fields { body_spin },
            },
            air_settings: input::AirSettings::load(data).unwrap(),
            trajectory: Trajectory {
                settings: TrajectorySettings { cone_x, cone_z },
            },
            animated_skeleton: AnimatedSkeleton {
                board_frames: BoardFrames {
                    local_centre_of_mass,
                    local_board_position,
                },
            },
        };
        (
            GamePhysics {
                settings: Settings {
                    step: Step {
                        simulation: Simulation {
                            gravity_acceleration: Vector3 {
                                x: gravity[0],
                                y: gravity[1],
                                z: gravity[2],
                            },
                        },
                    },
                },
                riding: Riding {
                    reckoning_frames: Frames {
                        system,
                        inverse_system,
                    },
                },
            },
            skater,
        )
    }
    pub fn evaluate(o: &mut Output, p: &GamePhysics, s: &SkaterRuntime) {
        frame(o, &input::frame(s));
        match input::selector_input(p, s) {
            Ok(v) => {
                o.word(1);
                for n in [
                    v.gravity,
                    v.ground_normal,
                    v.contact_position,
                    v.heading_direction,
                    v.reference_up,
                ] {
                    o.vector(n)
                }
                o.float(v.board_vertical_velocity);
                o.float(v.directional_input);
                for n in [
                    v.previous_physics_state,
                    v.flags_2472,
                    v.flags_2476,
                    v.offboard_flags_1776,
                ] {
                    o.word(n)
                }
                o.float(v.grind_lock_distance);
            }
            Err(e) => o.status(Err(e)),
        };
        match input::launch_info(p, s) {
            Ok(v) => {
                o.word(1);
                info(o, &v)
            }
            Err(e) => o.status(Err(e)),
        };
    }
}
fn main() {
    let args: Vec<_> = std::env::args().collect();
    let data = Collections::load(std::path::Path::new(&args[1])).unwrap();
    let stock = bindings::input::AirSettings::load(&data).unwrap();
    let mut o = Output::default();
    for v in stock.state.body_spin_over_time_320.x {
        o.float(v)
    }
    for v in stock.state.body_spin_over_time_320.y {
        o.float(v)
    }
    for v in [
        stock.state.landing_normal_blend_388,
        stock.state.body_spin_scale_428,
        stock.state.landing_normal_angle_limit_444,
        stock.steering_blend,
    ] {
        o.float(v)
    }
    for v in stock.grind_lock_distance {
        o.float(v)
    }
    o.vector(stock_constant::acceleration());
    let mut bytes = Vec::new();
    std::io::stdin().read_to_end(&mut bytes).unwrap();
    assert_eq!(bytes.len() % 4, 0);
    let mut i = Input {
        words: bytes
            .chunks_exact(4)
            .map(|b| u32::from_le_bytes(b.try_into().unwrap()))
            .collect(),
        at: 0,
    };
    let count = i.word();
    o.word(count);
    let mut s = PhysicsAirState::default();
    let mut r = PhysicsAirReckoningFields {
        current_landing_normal_1152: [0., 1., 0., 0.],
        collision_reference_normal_1216: [0., 1., 0., 0.],
        body_spin_angle_1568: 0.,
        body_spin_speed_1572: 0.,
    };
    for row in 0..count {
        let op = i.word();
        let mut trace = Vec::new();
        let mut extra = Output::default();
        match op {
            0 => {
                s = i.state();
                r = i.reckoning();
            }
            1 | 2 | 5 => {
                let f = i.frame();
                let acceleration = i.vector();
                let mut runtime = Runtime::read(&mut i);
                if op == 1 {
                    enter(&mut s, &f, acceleration, &mut runtime)
                } else if op == 5 {
                    update_skateboard(&s, &f, &r, &mut runtime)
                } else {
                    let use_stock = i.word() != 0;
                    let settings = i.settings();
                    update(
                        &mut s,
                        &f,
                        if use_stock { &stock.state } else { &settings },
                        &mut r,
                        acceleration,
                        &mut runtime,
                    )
                }
                trace = runtime.trace.borrow().0.clone();
            }
            3 => {
                let mut runtime = Runtime::read(&mut i);
                update_post_physics(&mut s, &mut runtime);
                trace = runtime.trace.borrow().0.clone();
            }
            4 => exit(&mut s, &mut r),
            6 => {
                let f = i.frame();
                let frames = i.word() as i32;
                let left = i.vector();
                let right = i.vector();
                let maximum = i.float();
                extra.vector(calculate_velocity_from_jump(&f, frames, &mut AirMath));
                extra.float(AirMath.minimum_vminfp(left[0], right[0]));
                extra.float(AirMath.length_squared_vmsum3fp(left));
                extra.float(AirMath.length_vmsum3fp_vrsqrte(left));
                extra.vector(AirMath.clamp_vector_within_max_length(left, maximum));
                extra.float(angle_between_vectors(left, right));
                extra.float(wrap_signed_angle(maximum));
                extra.vector(clamp_jump_velocity(left, right));
            }
            7 => {
                s.centre_of_mass_trajectory = i.trajectory();
                integrate_trajectory_fixed_step(&mut s.centre_of_mass_trajectory)
            }
            8 => {
                let (p, s) = bindings::read(&mut i, &data);
                bindings::evaluate(&mut extra, &p, &s)
            }
            9 => {
                s = PhysicsAirState::default();
                info(&mut extra, &LaunchInfo::default())
            }
            _ => panic!("Invalid operation"),
        }
        o.word(row);
        o.word(op);
        o.word(1);
        state(&mut o, &s);
        reckoning(&mut o, &r);
        let output = fill_physics_output(&s);
        o.word(u32::from(output.is_at_apex));
        o.float(output.jump_height);
        o.vector(output.landing_normal);
        o.word(u32::from(output.scalar_184_write.is_some()));
        if let Some(v) = output.scalar_184_write {
            o.float(v)
        }
        o.word(trace.len() as u32);
        o.0.extend(trace);
        o.word(extra.0.len() as u32);
        o.0.extend(extra.0);
    }
    assert_eq!(i.at, i.words.len());
    let bytes: Vec<_> = o.0.into_iter().flat_map(u32::to_le_bytes).collect();
    std::io::stdout().write_all(&bytes).unwrap();
}
