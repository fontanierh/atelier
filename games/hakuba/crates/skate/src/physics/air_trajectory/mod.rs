//! Real stock-settings and BoardWorld adapter for the player trajectory selector.
pub(crate) mod grind;
mod settings;
mod vert_departure;
use crate::grind_world::StaticProvider;
pub(crate) use grind::GrindContext;
use std::sync::Arc;
use vert_departure::vert_departure;
mod world;
use crate::core::{
    air::trajectory::{
        LaunchInfo, QueryRequest, QueryResult, SelectorInput, SelectorSettings, TrajectorySelector, query_trajectory,
    },
    physics::board_world::BoardWorld,
};
use crate::data::collections::Collections;

pub struct AirTrajectoryRuntime {
    pub selector: TrajectorySelector,
    pub settings: SelectorSettings,
    pending_results: Option<Vec<QueryResult>>,
    pub(crate) grind_settings: grind::Settings,
    grind_world: Option<Arc<StaticProvider>>,
    nearby_grinds: Vec<usize>,
    /// Host: how far below vertical a quarter's lip still launches a vert air (0 is stock, see `vert_departure`).
    pub vert_assist: f32,
    /// Local authored cap; zero disables vert alignment for neutral departures.
    pub vert_assist_limit: f32,
    pub wall_follow: crate::core::wall_follow::WallFollowAir,
}
impl AirTrajectoryRuntime {
    pub fn set_wall_follow(&mut self, strength: f32) {
        if strength != self.wall_follow.strength {
            self.wall_follow.reset();
            self.wall_follow.strength = strength;
            self.selector.set_wall_follow(0.0, 0.0);
        }
    }
    ///Full82E099A0 query shared by trajectory and Footplant callers.
    pub fn query(world: &BoardWorld, request: QueryRequest) -> Result<QueryResult, String> {
        query_trajectory(
            request,
            |start, end, radius| world::line(world, start, end, radius),
            |position, radius| world::nearby(world, position, radius),
        )
    }
    pub fn load(collections: &Collections) -> Result<Self, String> {
        Ok(Self {
            selector: TrajectorySelector::new(),
            settings: settings::load(collections)?,
            pending_results: None,
            grind_settings: grind::Settings::load(collections)?,
            grind_world: None,
            nearby_grinds: Vec::new(),
            vert_assist: 0.,
            vert_assist_limit: 1.0,
            wall_follow: Default::default(),
        })
    }
    pub fn launch(&mut self, mut info: LaunchInfo, input: SelectorInput, world: &BoardWorld) -> Result<bool, String> {
        // A rounded coping shoulder can leave a nearly vertical *averaged* contact
        // normal. Its small Y component leaks upward speed into the stock launch
        // calculation's horizontal residual and sends a neutral air onto the deck.
        // Interpret an upward departure from this near-vertical band as a vert air.
        // Pushing towards a transfer retains the original trajectory calculation.
        let mut input = input;
        (input.ground_normal, info.start_velocity) =
            vert_departure(input.ground_normal, info.start_velocity, input.directional_input, self.vert_assist);
        // A zero-assist region flies ballistically unless the player requests a transfer.
        let plain;
        let settings = if self.vert_assist_limit <= 0.0 && input.directional_input < 0.5 {
            plain = {
                let mut s = self.settings.clone();
                s.vert_jump_align_max_ground_normal_y = -2.0;
                s
            };
            &plain
        } else {
            &self.settings
        };
        let mut latch = 0.0;
        if self.wall_follow.strength > 0.0 {
            let w = &self.wall_follow;
            if w.pending || w.active {
                self.selector.set_wall_follow(w.curvature, w.remaining());
            } else {
                let mut probe = info;
                let aligned = crate::core::air::trajectory::launch::adjust_velocity(&mut probe, input, settings);
                latch = w.launch_curvature(
                    aligned,
                    self.vert_assist,
                    self.vert_assist_limit,
                    input.directional_input,
                    info.start_velocity,
                    input.ground_normal,
                );
                self.selector
                    .set_wall_follow(latch, if latch != 0.0 { crate::core::wall_follow::MAXIMUM_TIME } else { 0.0 });
            }
        }
        let launched = self.selector.launch(info, input, settings)?;
        if launched && latch != 0.0 {
            let w = &mut self.wall_follow;
            w.pending = true;
            w.pending_ticks = 0;
            w.curvature = latch;
            w.elapsed = 0.0;
            let h = (input.ground_normal[0].powi(2) + input.ground_normal[2].powi(2)).sqrt();
            w.inward_x = input.ground_normal[0] / h;
            w.inward_z = input.ground_normal[2] / h;
        }
        if launched {
            self.submit(world)?;
        }
        Ok(launched)
    }
    pub fn bind_grind_world(&mut self, provider: Arc<StaticProvider>) {
        self.grind_world = Some(provider);
        self.nearby_grinds.clear();
    }
    pub fn update(&mut self, input: SelectorInput, world: &BoardWorld, context: GrindContext) -> Result<bool, String> {
        let Some(results) = self.pending_results.take() else {
            return Ok(self.selector.update_without_completion());
        };
        let provider = self.grind_world.as_deref().ok_or("Trajectory static grind provider was not registered")?;
        let valid = self.selector.complete_batch(
            &results,
            input,
            &self.settings,
            |prediction, acquire| {
                self.grind_settings.evaluate(
                    prediction,
                    acquire,
                    world,
                    provider,
                    &mut self.nearby_grinds,
                    input.grind_lock_distance,
                    context,
                )
            },
            |start, end, radius| world::line(world, start, end, radius),
        )?;
        if self.selector.pending() {
            self.submit(world)?;
        }
        Ok(valid)
    }
    fn submit(&mut self, world: &BoardWorld) -> Result<(), String> {
        let results = self
            .selector
            .requests()
            .iter()
            .map(|&request| Self::query(world, request))
            .collect::<Result<Vec<_>, _>>()?;
        self.pending_results = Some(results);
        Ok(())
    }
}
