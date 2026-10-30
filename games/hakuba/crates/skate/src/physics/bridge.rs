#[cfg(test)]
mod feel_tests;
mod gravity;
mod grind_feel;
#[cfg(test)]
mod marker_tests;
#[cfg(test)]
mod parity_tests;
#[cfg(test)]
mod pump_tests;
#[cfg(test)]
mod rails_tests;
#[cfg(test)]
mod recovery_tests;
#[cfg(test)]
mod session_tests;
#[cfg(test)]
mod surfaces_tests;
#[cfg(test)]
mod terrain_tests;
#[cfg(test)]
mod transition_debug;
#[cfg(test)]
mod wall_follow_tests;
use super::{GamePhysics, PlayerControls, SkaterRuntime};
use crate::data::skate_map::{Collision, Geometry, Rail, SkateMap};
use crate::{camera::CameraRuntime, graph_runtime::StockGraphs, input::ControllerInput};
use bevy::prelude::*;

/// Host button for a transfer (the native pad ignores bit 11): a grab no longer asks for one.
pub const TRANSFER: u16 = 0x0800;
#[derive(Clone, Copy, Default)]
pub struct Controls {
    pub buttons: u16,
    pub triggers: [u8; 2],
    pub left: [i16; 2],
    pub right: [i16; 2],
}
mod places;
pub use places::{MarkerSnapshot, MarkerStatus};
mod assists;
mod audio;
pub use audio::{AudioEvent, AudioEventKind, AudioFrame, AudioMode};
mod boost;
mod feel;
mod telemetry;
pub use telemetry::SkateTelemetry;

pub use super::ground_runtime::surface::GroundSurfaceReport;

pub struct Session {
    feel: crate::feel::FeelTuning,
    feel_stock: feel::FeelStock,
    boost: boost::BowlBoost,
    observer: telemetry::Observer,
    drift_hold: u32,
    audio: audio::Publication,
    vert_assist: f32,
    fine_sticks: Option<Controls>,
    camera_pull: f32,
    physics: GamePhysics,
    skater: SkaterRuntime,
    controls: PlayerControls,
    graphs: StockGraphs,
    input: ControllerInput,
    camera: CameraRuntime,
    markers: crate::session_marker::Runtime,
    stock_spin_speed: f32,
    control_feel: [f32; 2],
    pub(crate) get_up_delay: f32,
    grind_stock: grind_feel::GrindFeelStock,
}
/// Authoritative solved IK contact state in native left-foot/right-foot/left-hand/right-hand order.
/// Blends are the simulation's retained weights, not distances inferred by the renderer.
#[derive(Clone, Copy, Debug)]
pub struct LimbContact {
    pub mode: ContactMode,
    pub board_blend: f32,
    pub external_blend: f32,
    pub target_blend: f32,
    pub target_in_bounds: bool,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ContactMode {
    Disabled,
    OnDeck,
    External,
    Local,
}
#[derive(Clone)]
pub struct Pose {
    pub root: Mat4,
    pub bones: Vec<Mat4>,
    pub names: Vec<String>,
    pub parents: Vec<i32>,
    pub board: Vec<Mat4>,
    pub board_visibility: f32,
    pub surface: GroundSurfaceReport,
    pub camera: Option<(Vec3, Mat3, f32)>,
    /// Mean physical wheel contact origin, in simulation world metres (not a raycast hit).
    pub ground_point: Vec3,
    pub velocity: Vec3,
    pub tick: u64,
    pub state: String,
    pub bailed: bool,
    pub physical_state: u32,
    pub contacts: [LimbContact; 4],
}
impl Session {
    /// Set native stick conditioning and the local bail-settle delay scale. No host pre-deadzone is applied.
    pub fn set_control_feel(&mut self, dead_zone: f32, reach: f32, get_up_delay: f32) -> Result<(), String> {
        if !dead_zone.is_finite()
            || !reach.is_finite()
            || !get_up_delay.is_finite()
            || !(0.25..=0.6).contains(&dead_zone)
            || !(0.6..=1.).contains(&reach)
            || reach <= dead_zone
            || !(0.25..=2.).contains(&get_up_delay)
        {
            return Err("Invalid control feel".into());
        }
        self.control_feel = [dead_zone, reach];
        self.input.set_sticks(dead_zone, reach);
        self.get_up_delay = get_up_delay;
        Ok(())
    }

    /// Enter the original limp physical rider without a checkpoint request.
    pub fn request_bail(&mut self) -> Result<(), String> {
        super::recovery::bail(&mut self.physics, &mut self.skater)
    }
    /// Lost-session safety restores exactly the last displayed assembly before letting it fall.
    pub fn bail_in_place(&mut self, shown: &Pose) -> Result<(), String> {
        super::recovery::restore_and_bail(&mut self.physics, &mut self.skater, shown)
    }
    pub fn recovering(&self) -> bool {
        self.skater.recovery.getting_up()
    }

    /// Current wheel-voted sound and physics profiles, without replacing the ground solver.
    pub fn surface(&self) -> GroundSurfaceReport {
        super::ground_runtime::surface::report(&self.physics.riding)
    }

    pub fn from_resources(
        prepared: &crate::PreparedResources,
        triangles: Vec<[[f32; 3]; 3]>,
        surfaces: Vec<u16>,
        rails: Vec<CollisionRail>,
        spawn: [f32; 3],
        heading: f32,
    ) -> Result<Self, String> {
        let resources = prepared.0.as_ref();
        let graphs = StockGraphs::load(&resources)?;
        let map = collision_map(triangles, surfaces, rails, spawn, heading)?;
        let mut physics = GamePhysics::load_with_map(&resources, Some(&map))?;
        physics.world.enable_imported_floor_seams();
        let mut skater = SkaterRuntime::load(&resources, &graphs, &physics, "easy")?;
        skater.player_state.selector.max_air_frames = 1800;
        let camera = CameraRuntime::load(&resources)?;
        let feel_stock = feel::FeelStock::capture(&skater, &camera);
        Ok(Self {
            feel: Default::default(),
            feel_stock,
            boost: Default::default(),
            observer: Default::default(),
            drift_hold: 0,
            audio: audio::Publication::default(),
            vert_assist: 0.0,
            fine_sticks: None,
            camera_pull: 0.0,
            stock_spin_speed: skater.air_settings.state.body_spin_scale_428,
            control_feel: [0.25, 0.95],
            get_up_delay: 1.,
            grind_stock: grind_feel::GrindFeelStock::capture(&skater),
            physics,
            skater,
            controls: PlayerControls::load(&resources)?,
            graphs,
            input: ControllerInput::default(),
            camera,
            markers: crate::session_marker::Runtime::load(&resources)?,
        })
    }
    /// A builder for collision to swap in later, usable on another thread.
    pub fn collision_builder(&self) -> CollisionBuilder {
        CollisionBuilder { material: self.physics.floor_material() }
    }
    /// Swaps in collision built by `collision_builder`: the world the skater
    /// rides, climbs and grinds from the next tick.
    pub fn install_collision(&mut self, prepared: PreparedCollision) -> Result<(), String> {
        self.physics.install_world(prepared.world, std::sync::Arc::clone(&prepared.grind))?;
        self.skater.trajectory.bind_grind_world(prepared.grind);
        Ok(())
    }
    // Host adapter: expose the stock reference rig and preferences without replacing graph ownership.
    pub fn configure(&mut self, difficulty: &str, goofy: bool, trucks: f32) -> Result<(), String> {
        self.physics.set_difficulty(crate::difficulty::Difficulty::parse(difficulty)?);
        self.observer.goofy = goofy;
        self.physics.set_equipment_preferences(trucks, 0.5);
        self.skater.animation.set_customisation(u32::from(goofy), 0);
        Ok(())
    }
    /// Host preferences scale the stock launch height and air-spin target; constraints remain native.
    /// `vert_assist` (0 is stock) lets quarters short of vertical launch vert airs.
    pub fn tune(
        &mut self,
        pop: f32,
        spin: f32,
        push_speed: f32,
        push_power: f32,
        vert_assist: f32,
    ) -> Result<(), String> {
        if !pop.is_finite()
            || !spin.is_finite()
            || !(0.5..=2.).contains(&pop)
            || !(0.5..=3.).contains(&spin)
            || !push_speed.is_finite()
            || !(0.5..=2.).contains(&push_speed)
            || !push_power.is_finite()
            || !(0.5..=3.).contains(&push_power)
            || !(0. ..=1.).contains(&vert_assist)
        {
            return Err("Invalid skating tuning".into());
        }
        self.vert_assist = vert_assist;
        self.skater.trajectory.vert_assist = vert_assist.min(self.skater.trajectory.vert_assist_limit);
        self.physics.trainer.pop = pop;
        self.physics.trainer.push_speed = push_speed;
        self.physics.trainer.push_power = push_power;
        self.skater.air_settings.state.body_spin_scale_428 = self.stock_spin_speed * spin;
        self.skater.known_air.set_spin_speed(self.stock_spin_speed * spin);
        self.skater.air_reckoning.set_spin_scale(spin);
        Ok(())
    }
    /// Per-tick cap from the world zone; an air latches its launch assistance.
    pub fn limit_vert_assist(&mut self, limit: f32) -> Result<(), String> {
        if !(0.0..=1.0).contains(&limit) {
            return Err("Invalid vert assist limit".into());
        }
        self.skater.trajectory.vert_assist_limit = limit;
        self.skater.trajectory.vert_assist = self.vert_assist.min(limit);
        Ok(())
    }
    pub fn set_boost_zone(&mut self, scale: f32) -> Result<(), String> {
        if !scale.is_finite() || !(0.0..=3.0).contains(&scale) {
            return Err("Invalid boost zone scale".into());
        }
        self.boost.zone = scale;
        Ok(())
    }
    pub fn reference_pose(&self) -> Result<Vec<Mat4>, String> {
        use crate::core::animation::output::Sqt;
        let reference = self.skater.animation.evaluator.frames.named_pose("RIG_TPOSE")?;
        let pose: Vec<_> = reference
            .samples
            .iter()
            .map(|words| {
                let [sx, sy, sz, x, y, z, w, tx, ty, tz] = words.map(f32::from_bits);
                Sqt { scale: [sx, sy, sz, 1.], rotation: [x, y, z, w], translation: [tx, ty, tz, 1.] }
            })
            .collect();
        Ok(self.skater.animation.evaluator.hierarchy(&pose)?.into_iter().map(crate::animation::native_matrix).collect())
    }
    pub fn score(&self) -> (f32, f32, String) {
        let s = &self.skater.scoring.session.holder.snapshot;
        (s.completed_lines + s.line, s.last_reward, self.skater.scoring.current_trick().to_owned())
    }
    pub fn manual_balance(&self) -> f32 {
        self.skater.animation_input.fields.balance
    }
    /// QA/teleport adapter: apply a common translational velocity to the physical assembly.
    pub fn launch(&mut self, velocity: [f32; 3]) {
        let v = crate::core::math::Vector3::new(velocity[0], velocity[1], velocity[2]);
        for body in self.physics.board.bodies_mut() {
            body.rates.linear_velocity = v;
        }
        for body in self.skater.skeleton.bodies_mut() {
            body.rates.linear_velocity = v;
        }
        self.physics.riding.ground.previous_velocities.fill(v);
    }
    pub fn period(&self) -> f32 {
        self.physics.period().as_secs_f32()
    }
    pub fn set_aspect_ratio(&mut self, aspect_ratio: f32) {
        if aspect_ratio.is_finite() && aspect_ratio > 0. {
            self.camera.set_aspect_ratio(aspect_ratio);
        }
    }
    /// Prepare once before readiness, then retain the handle for every session.
    pub fn preload(bytes: Vec<u8>) -> Result<crate::PreparedResources, String> {
        crate::PreparedResources::from_bytes(bytes)
    }
    /// Reuse the complete world and animation session. The original teleport path
    /// resets physical bodies and animation state at the requested world position.
    pub fn activate(&mut self, spawn: [f32; 3], heading: f32) -> Result<Pose, String> {
        self.activate_with_board(spawn, heading, true)
    }
    /// Enter the stock off-board state with the board carried, before native mount input.
    pub fn activate_on_foot(&mut self, spawn: [f32; 3], heading: f32) -> Result<Pose, String> {
        self.activate_with_board(spawn, heading, false)
    }
    fn activate_with_board(&mut self, spawn: [f32; 3], heading: f32, on_board: bool) -> Result<Pose, String> {
        self.input = ControllerInput::default();
        self.input.set_sticks(self.control_feel[0], self.control_feel[1]);
        self.markers.suspend();
        if self.physics.ticks == 0 {
            self.tick(Controls::default())?;
        }
        let mut transform =
            Mat4::from_rotation_translation(Quat::from_rotation_y(heading), Vec3::from_array(spawn)).to_cols_array_2d();
        transform[3][3] = 0.;
        self.skater.travel_to_on_board(transform, on_board)?;
        for _ in 0..4 {
            self.tick(Controls::default())?;
        }
        let deck = super::solve::deck_frame(&self.physics.board);
        self.skater.respawn.reset_start(deck, self.skater.animation.checkpoint_stance());
        self.skater
            .teleport_state
            .set_checkpoint(super::teleport_state::Checkpoint { transform: deck, on_board: true });
        self.input = ControllerInput::default();
        self.input.set_sticks(self.control_feel[0], self.control_feel[1]);
        self.boost.reset_input();
        self.fine_sticks = None;
        self.camera_pull = 0.0;
        self.reset_audio();
        self.observer.reset(self.skater.scoring.announcement().0);
        Ok(self.pose())
    }
    pub fn suspend_input(&mut self) {
        self.input = ControllerInput::default();
        self.input.set_sticks(self.control_feel[0], self.control_feel[1]);
        self.markers.suspend();
        self.boost.reset_input();
        self.fine_sticks = None;
    }
    fn advance_published(&mut self) -> Result<(), String> {
        let published = self.input.tick_input();
        self.markers.advance(&self.input, &self.physics, &mut self.skater);
        let before = self.prepare_assists();
        let mut actions = published.actions();
        self.controls.update_for_physics(&mut actions, &self.physics, &self.skater, &self.camera)?;
        self.sampled_assists();
        self.controls.publish_gestures_fine(
            self.fine_sticks.take().map(|half| self.controls.gesture_axes(half.left, half.right)),
            self.physics.animation_profile.physics_mode,
            self.skater.player_input.physical.state.state_16,
        );
        self.skater.recovery.delay = self.get_up_delay;
        super::frame::advance(
            &mut self.physics,
            &mut self.skater,
            &mut self.controls,
            &self.graphs,
            &mut actions,
            published.controller_available(),
            &mut self.camera,
        )?;
        self.finish_assists(before);
        self.publish_audio();
        self.observe_telemetry();
        Ok(())
    }
    /// Advance exactly one simulation tick from a raw packet. `TRANSFER` is separate from native LB.
    /// LB + DPadDown places a marker; holding LB + DPadUp returns after the native hold delay.
    /// Marker hold time advances by this tick's simulation period, never by rendered-frame time.
    pub fn tick(&mut self, input: Controls) -> Result<(), String> {
        self.physics.transfer = Some(input.buttons & TRANSFER != 0);
        self.markers.collect_time(f64::from(self.period()));
        crate::input::sample(
            &mut self.input,
            crate::core::input::xbox::XboxState {
                buttons: input.buttons & !TRANSFER,
                triggers: input.triggers,
                left: input.left,
                right: input.right,
            },
        );
        self.advance_published()
    }
    /// Genuine midpoint device reading, in the same raw stick frame as the packet.
    /// Inconsistent end readings fall back to one packet with double weight.
    pub fn tick_with_sticks(&mut self, input: Controls, half: Controls, end: Controls) -> Result<(), String> {
        if input.left == end.left && input.right == end.right {
            self.fine_sticks = Some(half);
        } else {
            self.fine_sticks = None;
        }
        self.tick(input)
    }
    pub fn pose(&self) -> Pose {
        let parts = self.physics.board.part_transforms();
        let deck = parts[crate::core::physics::board::BodyId::Deck.index()];
        let mut deck_frame = crate::core::physics::skeleton_animation_record::IDENTITY;
        for (axis, column) in deck.basis.columns.iter().enumerate() {
            deck_frame[axis][..3].copy_from_slice(column);
        }
        deck_frame[3] = [deck.translation.x, deck.translation.y, deck.translation.z, 0.0];
        let physical_board = crate::animation::native_matrix(deck_frame);
        let board_delta =
            self.skater.recovery.shown_board().map_or(Mat4::IDENTITY, |shown| shown * physical_board.inverse());
        let v = self.physics.board.bodies()[crate::core::physics::board::BodyId::Deck.index()].rates.linear_velocity;
        Pose {
            root: crate::animation::native_matrix(self.skater.animated_skeleton.roots.animation_to_world),
            bones: self.skater.render_pose.iter().map(|m| crate::animation::native_matrix(*m)).collect(),
            names: self.skater.animation.evaluator.frames.bone_names.clone(),
            parents: self.skater.animation.evaluator.frames.parents.clone(),
            board: parts
                .iter()
                .map(|t| {
                    board_delta
                        * Mat4::from_mat3_translation(
                            Mat3::from_cols_array_2d(&t.basis.columns),
                            Vec3::new(t.translation.x, t.translation.y, t.translation.z),
                        )
                })
                .collect(),
            camera: self.camera.frame.as_ref().map(|f| {
                (
                    {
                        let root = self.skater.animated_skeleton.roots.animation_to_world[3];
                        let pivot = Vec3::new(root[0], root[1] + 0.9, root[2]);
                        let camera = Vec3::new(f.position[0], f.position[1], f.position[2]);
                        if self.camera_pull != 0.0 {
                            pivot + (camera - pivot) * (1.0 + self.camera_pull)
                        } else {
                            camera
                        }
                    },
                    Mat3::from_cols_array_2d(&f.basis.columns),
                    f.field_of_view_degrees,
                )
            }),
            board_visibility: self.skater.recovery.board_visibility,
            surface: self.surface(),
            ground_point: {
                let center = parts[..4]
                    .iter()
                    .map(|t| Vec3::new(t.translation.x, t.translation.y, t.translation.z))
                    .sum::<Vec3>()
                    * 0.25;
                let up = Vec3::from_array(parts[crate::core::physics::board::BodyId::Deck.index()].basis.columns[1]);
                center - up * self.physics.settings.wheel_radius
            },
            velocity: Vec3::new(v.x, v.y, v.z),
            tick: self.physics.ticks,
            state: format!("{:?}", self.skater.player_state.current()),
            bailed: self.skater.player_state.current() == crate::core::player::state::PhysicalStateId::WipeoutGround,
            physical_state: self.skater.player_state.current() as u32,
            contacts: std::array::from_fn(|i| {
                use crate::core::animation::foot_ik::status::Mode;
                let limb = self.skater.foot_ik.state.limbs[i];
                LimbContact {
                    mode: match limb.mode {
                        Mode::Disabled => ContactMode::Disabled,
                        Mode::OnDeck => ContactMode::OnDeck,
                        Mode::External => ContactMode::External,
                        Mode::Local => ContactMode::Local,
                    },
                    board_blend: limb.board_blend,
                    external_blend: limb.external_blend,
                    target_blend: limb.target_blend,
                    target_in_bounds: self.skater.foot_ik.state.frames[i].within_contact_bounds,
                }
            }),
        }
    }
}

/// An authored grind line in simulation-world metres. Closure is topology, not a duplicate endpoint.
#[derive(Clone, Debug, PartialEq)]
pub struct CollisionRail {
    pub id: String,
    pub points: Vec<[f32; 3]>,
    pub closed: bool,
}

/// Collision for `Session::install_collision`, built off the simulation.
pub struct PreparedCollision {
    world: crate::core::physics::board_world::BoardWorld,
    grind: std::sync::Arc<crate::grind_world::StaticProvider>,
}

#[derive(Clone, Copy)]
pub struct CollisionBuilder {
    material: crate::core::physics::contact::RetailContactMaterial,
}

impl CollisionBuilder {
    pub fn build(
        &self,
        triangles: Vec<[[f32; 3]; 3]>,
        surfaces: Vec<u16>,
        rails: Vec<CollisionRail>,
    ) -> Result<PreparedCollision, String> {
        let map = collision_map(triangles, surfaces, rails, [0.; 3], 0.)?;
        let mut world = crate::skate_world::collision_world(&map, self.material)?;
        world.enable_imported_floor_seams();
        Ok(PreparedCollision {
            world,
            grind: std::sync::Arc::new(crate::grind_world::StaticProvider::new(Some(&map))?),
        })
    }
}

/// The host world collision as a simulation map.
fn collision_map(
    triangles: Vec<[[f32; 3]; 3]>,
    surfaces: Vec<u16>,
    rails: Vec<CollisionRail>,
    spawn: [f32; 3],
    heading: f32,
) -> Result<SkateMap, String> {
    if triangles.len() != surfaces.len() {
        return Err("Collision surface count must equal triangle count".into());
    }
    let mut material_surfaces = Vec::new();
    let mut material_indices = Vec::with_capacity(surfaces.len());
    for &surface in &surfaces {
        if !(1..=5).contains(&((surface >> 7) & 31)) {
            return Err(format!("Invalid imported collision physics profile in {surface}"));
        }
        let index = match material_surfaces.iter().position(|&value| value == surface) {
            Some(index) => index,
            None => {
                material_surfaces.push(surface);
                material_surfaces.len() - 1
            }
        };
        material_indices.push(index as u32 + 1);
    }
    Ok(SkateMap {
        version: 14,
        name: "Hakuba collision".into(),
        spawn,
        heading,
        environment: vec![],
        materials: material_surfaces
            .into_iter()
            .map(|surface| crate::data::skate_map::Material {
                name: "world".into(),
                flags: 0,
                friction: 0.8,
                restitution: 0.,
                color: [1.; 3],
                roughness: 1.,
                emissive: 0.,
                textures: [0; 5],
                indirect_strength: 1.,
                alpha_mode: 0,
                alpha_cutoff: 0.5,
                audio: u32::from(surface & 0x7f),
                physics: u32::from((surface >> 7) & 31),
                pattern: u32::from(surface >> 12),
                depth_layer: None,
                retail_definition: None,
            })
            .collect(),
        textures: vec![],
        geometry: Geometry {
            vertices: vec![],
            indices: vec![],
            collision: triangles
                .into_iter()
                .zip(surfaces)
                .zip(material_indices)
                .map(|((points, surface), material)| Collision {
                    points,
                    surface: u32::from(surface),
                    material,
                    native_edges: None,
                })
                .collect(),
        },
        rails: rails
            .into_iter()
            .map(|rail| Rail { name: rail.id, closed: rail.closed, points: rail.points, native: None })
            .collect(),
        doors: vec![],
        lights: vec![],
        routes: vec![],
        extensions: vec![],
    })
}
