//! Applies feel from a captured authored baseline, so edits never compound.
use super::Session;
use crate::feel::FeelTuning;
use crate::physics::{air_reckoning::settings::Mode, ground_runtime::GroundPumpingMode};
pub(super) struct FeelStock {
    grind_lock: [f32; 5],
    grind: crate::physics::air_trajectory::grind::Settings,
    pumping: [GroundPumpingMode; 5],
    auto_push: [bool; 5],
    reckoning: [Mode; 5],
    known_flips: [bool; 5],
    wipeout: crate::core::player::wipeout::Settings,
    wipeout_modes: [crate::core::player::wipeout::Mode; 5],
    slide_force: Vec<crate::core::point_graph::PointGraph<8>>,
    camera_speed: f32,
}
impl FeelStock {
    pub fn capture(skater: &crate::physics::SkaterRuntime, camera: &crate::camera::CameraRuntime) -> Self {
        Self {
            grind_lock: skater.air_settings.grind_lock_distance,
            grind: skater.trajectory.grind_settings.clone(),
            pumping: skater.ground.pumping_settings.modes,
            auto_push: skater.ground.auto_push_enabled,
            reckoning: skater.air_reckoning.modes,
            known_flips: skater.known_air.modes.map(|m| m.perfect_body_flips_28),
            wipeout: skater.wipeout.settings.clone(),
            wipeout_modes: skater.wipeout.modes,
            slide_force: skater.slide_state.surfaces.iter().map(|s| s.0.speed_to_force).collect(),
            camera_speed: camera.anchor_speed(),
        }
    }
}
impl Session {
    pub fn feel(&self) -> FeelTuning {
        self.feel
    }
    pub fn set_feel(&mut self, t: FeelTuning) -> Result<(), String> {
        t.validate()?;
        self.controls.tune_gestures(t)?;
        self.set_gravity(t.gravity)?;
        let trainer = &mut self.physics.trainer;
        trainer.grind_pop = t.grind_pop;
        trainer.grind_friction = t.grind_friction;
        trainer.hippy = t.hippy;
        trainer.braking = t.braking;
        trainer.steering = t.steering;
        trainer.turn_power = t.carve;
        trainer.grip = t.grip;
        trainer.rolling_friction = t.rolling_friction;
        trainer.hill_speed = t.hill_speed;
        trainer.wobble = t.wobble;
        trainer.wobble_onset = t.wobble_onset;
        trainer.manual_drift = t.manual_drift;
        self.skater.boneless.height_scale = t.boneless;
        self.controls.preferences.drift_powerslide = t.drift_powerslide;
        self.controls.preferences.drift_hold = false;
        self.drift_hold = 0;
        self.skater.slide_state.settings.turn_scale = t.powerslide_turn;
        self.skater.slide_state.settings.friction_scale = 1.0;
        let stock = &self.feel_stock;
        let m = t.rail_magnetism;
        self.skater.air_settings.grind_lock_distance = stock.grind_lock.map(|v| v * m);
        self.skater.trajectory.grind_settings = stock.grind.clone();
        let grind = &mut self.skater.trajectory.grind_settings;
        grind.maximum_adjust *= m;
        grind.limits.maximum_adjust_angle *= m;
        grind.limits.max_downward_speed *= m;
        grind.limits.max_speed_squared_ledge *= m * m;
        grind.limits.max_speed_squared_rail *= m * m;
        for i in 0..5 {
            let mode = &mut self.skater.ground.pumping_settings.modes[i];
            *mode = stock.pumping[i];
            mode.controller.acceleration_factor *= t.pump;
            mode.controller.maximum_acceleration_per_second *= t.pump;
            self.skater.ground.auto_push_enabled[i] = t.auto_push.unwrap_or(stock.auto_push[i]);
            self.skater.air_reckoning.modes[i] = stock.reckoning[i];
            self.skater.known_air.modes[i].perfect_body_flips_28 = stock.known_flips[i];
            if let Some(on) = t.assisted_air {
                self.skater.air_reckoning.modes[i].easy_body_spins = on;
                self.skater.air_reckoning.modes[i].perfect_body_flips = on;
                self.skater.known_air.modes[i].perfect_body_flips_28 = on;
            }
            self.skater.wipeout.modes[i] = stock.wipeout_modes[i];
            self.skater.wipeout.modes[i].bad_landing_scale *= t.landing;
            self.skater.wipeout.modes[i].ground_xz *= t.impact;
            let force = &mut self.skater.slide_state.surfaces[i].0.speed_to_force;
            *force = stock.slide_force[i];
            for y in &mut force.y {
                *y *= t.powerslide;
            }
        }
        self.skater.wipeout.settings = stock.wipeout.clone();
        let w = &mut self.skater.wipeout.settings;
        w.ground.y_acceleration *= t.impact;
        w.air.xz_acceleration *= t.impact;
        w.air.y_acceleration *= t.impact;
        w.air.xz_trick *= t.impact;
        w.air.y_trick *= t.impact;
        self.camera.tune_follow(stock.camera_speed, t.camera_follow);
        self.apply_grind_tolerance(t.grind_tolerance);
        self.skater.trajectory.set_wall_follow(t.wall_follow);
        self.feel = t;
        Ok(())
    }
}
