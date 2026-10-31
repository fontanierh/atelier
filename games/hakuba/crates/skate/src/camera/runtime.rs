//! Complete normal camera owner: subject publications, stock graph, CameraMan,
//! swept world queries and retained query history. The simulation calls advance
//! once per completed physical/animation publication; rendering only presents it.
use super::{
    collision::CameraCollision,
    graph::CameraGraph,
    graph_subject::CameraGraphEnvironment,
    settings,
    shot_data::StockShots,
    subject::{CameraSubjectSnapshot, SubjectPublisher},
    trajectory::{CameraTrajectory, TrajectoryResult},
};
use crate::core::{
    camera::{
        CameraFrame, CameraMan, CompassSettings, ManagerSettings, MovingObstacleProvider, ShakeSamples,
        SimulationRateRequest, SlowMotionSettings,
    },
    physics::board_world::BoardWorld,
    point_graph::PointGraph,
};
use crate::data::collections::Collections;
use bevy::prelude::Resource;

#[derive(Resource)]
pub(crate) struct CameraRuntime {
    manager: CameraMan,
    subject: SubjectPublisher,
    graph: CameraGraph,
    shots: StockShots,
    settings: ManagerSettings,
    compass_settings: CompassSettings,
    shakes: [ShakeSamples; 2],
    trajectories: [TrajectoryResult; 3],
    pub frame: Option<CameraFrame>,
    /// Immutable physical subject publication consumed by the camera graph.
    /// Rendering may inspect this snapshot for diagnostics without rebuilding
    /// subject fields from mutable skater state.
    pub latest_subject: Option<CameraSubjectSnapshot>,
    /// Native message order, including End followed by Begin in one graph tick.
    /// The simulation schedule drains these after advance.
    pub simulation_rate_requests: Vec<SimulationRateRequest>,
    /// Test-only synthetic fault: the next advance reaches the exceptional conversion after preparing the manager.
    #[cfg(test)]
    pub inject_exceptional_angle: bool,
}

// Native skating relies on unwinding to stop an exceptional camera conversion without ending the app.
#[cfg(all(not(target_family = "wasm"), not(panic = "unwind")))]
compile_error!("native Hakuba must be built with panic = \"unwind\" (the camera's exceptional-angle containment)");

/// Turns a caught exceptional angle conversion into the camera's terminal error; resumes every other panic unchanged.
#[cfg(all(not(target_family = "wasm"), panic = "unwind"))]
fn contain_exceptional_angle<T>(caught: std::thread::Result<Result<T, String>>) -> Result<T, String> {
    match caught {
        Ok(result) => result,
        Err(payload) => match payload.downcast::<crate::core::camera::ExceptionalAngleConversion>() {
            Ok(exceptional) => Err(format!(
                "camera error (exceptional angle conversion, angle bits {:#010x}). Pause, then Menu, then World to ride again.",
                exceptional.angle_bits
            )),
            Err(other) => std::panic::resume_unwind(other),
        },
    }
}

#[cfg(test)]
#[path = "tests/runtime.rs"]
mod tests;
impl CameraRuntime {
    pub fn load(root: &crate::resources::Resources) -> Result<Self, String> {
        let data = Collections::load(root)?;
        let values = data.words::<32>("slowmotion_controller", "default", "timescale")?.map(f32::from_bits);
        let slow_motion = SlowMotionSettings {
            timescale: PointGraph {
                x: core::array::from_fn(|i| values[i]),
                y: core::array::from_fn(|i| values[i + 16]),
            },
            fps_at_scale_one: data.float("slowmotion_controller", "default", "fps_at_scale_one")?,
        };
        let graph = CameraGraph::load(root, slow_motion)?;
        Ok(Self {
            manager: CameraMan::new(),
            subject: SubjectPublisher::new(),
            graph,
            shots: root.shots.clone(),
            settings: settings::manager_settings(&data)?,
            compass_settings: settings::compass_settings(&data)?,
            shakes: root.shakes.clone(),
            trajectories: core::array::from_fn(|_| TrajectoryResult::new()),
            frame: None,
            latest_subject: None,
            simulation_rate_requests: Vec::new(),
            #[cfg(test)]
            inject_exceptional_angle: false,
        })
    }

    pub fn set_aspect_ratio(&mut self, value: f32) {
        self.manager.state.aspect_ratio = value;
    }
    pub fn anchor_speed(&self) -> f32 {
        self.settings.rig.anchor.speed_clamp
    }
    pub fn tune_follow(&mut self, authored_speed: f32, follow: f32) {
        self.settings.rig.anchor.speed_clamp = authored_speed * follow;
        let shake = &mut self.settings.shake;
        let keep = follow > 1.0;
        shake.high_speed_start = if keep { 30.0 } else { 0.0 };
        shake.high_speed_end = if keep { 40.0 } else { 0.0 };
        shake.high_speed_amplitude = if keep { 0.25 } else { 1.0 };
        shake.high_speed_frequency = if keep { 0.5 } else { 1.0 };
    }
    pub fn selected_shot(&self) -> &str {
        &self.manager.shots.current().name
    }

    pub fn advance(
        &mut self,
        dt: f32,
        snapshot: CameraSubjectSnapshot,
        world: &BoardWorld,
        query_gravity: [f32; 4],
        environment: &CameraGraphEnvironment,
        moving: &mut impl MovingObstacleProvider,
    ) -> Result<CameraFrame, String> {
        #[cfg(all(not(target_family = "wasm"), panic = "unwind"))]
        {
            // Unwind safety: a caught exceptional conversion becomes a terminal Session error, and the host never
            // advances this partly updated camera again. Any other panic is resumed unchanged.
            contain_exceptional_angle(std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                self.advance_inner(dt, snapshot, world, query_gravity, environment, moving)
            })))
        }
        #[cfg(not(all(not(target_family = "wasm"), panic = "unwind")))]
        self.advance_inner(dt, snapshot, world, query_gravity, environment, moving)
    }

    fn advance_inner(
        &mut self,
        dt: f32,
        snapshot: CameraSubjectSnapshot,
        world: &BoardWorld,
        query_gravity: [f32; 4],
        environment: &CameraGraphEnvironment,
        moving: &mut impl MovingObstacleProvider,
    ) -> Result<CameraFrame, String> {
        if let Some(previous) = self.latest_subject.as_ref()
            && snapshot.tick <= previous.tick
        {
            return Err(format!(
                "Camera received non-monotonic subject tick: previous={}, current={}",
                previous.tick, snapshot.tick,
            ));
        }
        self.latest_subject = Some(snapshot);
        let mut subject = self.subject.publish(snapshot, &self.manager, self.compass_settings)?;
        self.manager.prepare(&subject, self.settings);
        #[cfg(test)]
        if std::mem::take(&mut self.inject_exceptional_angle) {
            crate::core::camera::normalize_angle(f32::NAN);
        }
        let requests = self.graph.update(dt, &mut self.manager, &subject, snapshot.graph, environment, &self.shots)?;
        self.simulation_rate_requests.extend(requests);
        let [a, b, c] = &mut self.trajectories;
        let mut trajectories = [a, b, c].map(|result| CameraTrajectory { world, gravity: query_gravity, result });
        let mut collision = CameraCollision::new(world);
        let frame = self.manager.update(
            dt,
            &mut subject,
            self.settings,
            [&self.shakes[0], &self.shakes[1]],
            &mut trajectories,
            moving,
            &mut collision,
        )?;
        if let Some(error) = collision.error {
            return Err(error);
        }
        if let Some(error) = self.trajectories.iter().find_map(|v| v.error.as_ref()) {
            return Err(error.clone());
        }
        if !frame.position.iter().all(|v| v.is_finite())
            || !frame.basis.columns.iter().flatten().all(|v| v.is_finite())
            || !frame.field_of_view_degrees.is_finite()
        {
            return Err(format!(
                "Normal gameplay camera produced a non-finite frame: frame={frame:?}; lens_length={:?}; aspect_ratio={:?}; subject_transform={:?}; skeleton_root={:?}; ground_normal={:?}; launch_position={:?}; landing_position={:?}",
                self.manager.shots.interpolated.lens_length,
                self.manager.state.aspect_ratio,
                subject.rig.transform,
                subject.rig.skeleton_root,
                subject.ground_normal,
                subject.launch_position,
                subject.landing_position,
            ));
        }
        self.frame = Some(frame);
        Ok(frame)
    }
}
