//! Session feel multipliers. Stock values leave authored controllers unchanged.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct FeelTuning {
    pub flick_radius: f32,
    pub flick_window: f32,
    pub flick_pace: f32,
    pub gravity: f32,
    pub boneless: f32,
    pub hippy: f32,
    pub rail_magnetism: f32,
    pub grind_pop: f32,
    pub grind_friction: f32,
    pub grind_tolerance: f32,
    pub camera_follow: f32,
    pub camera_pullback: f32,
    pub wall_follow: f32,
    pub braking: f32,
    pub steering: f32,
    pub carve: f32,
    pub grip: f32,
    pub powerslide: f32,
    pub rolling_friction: f32,
    pub hill_speed: f32,
    pub pump: f32,
    pub wobble: f32,
    pub wobble_onset: f32,
    pub manual_drift: f32,
    pub landing: f32,
    pub impact: f32,
    /// None retains the active difficulty's authored choice.
    pub auto_push: Option<bool>,
    pub assisted_air: Option<bool>,
    pub tight_flicks: bool,
    pub flick_120hz: bool,
    pub drift_powerslide: bool,
    pub powerslide_turn: f32,
    pub drift_grip: f32,
    pub drift_full_grip: f32,
    pub bowl_boost: f32,
}
impl Default for FeelTuning {
    fn default() -> Self {
        Self {
            flick_radius: 1.0,
            flick_window: 1.0,
            flick_pace: 1.0,
            gravity: 1.0,
            boneless: 1.0,
            hippy: 1.0,
            rail_magnetism: 1.0,
            grind_pop: 1.0,
            grind_friction: 1.0,
            grind_tolerance: 1.0,
            camera_follow: 1.0,
            camera_pullback: 0.0,
            wall_follow: 0.0,
            braking: 1.0,
            steering: 1.0,
            carve: 1.0,
            grip: 1.0,
            powerslide: 1.0,
            rolling_friction: 1.0,
            hill_speed: 1.0,
            pump: 1.0,
            wobble: 1.0,
            wobble_onset: 1.0,
            manual_drift: 1.0,
            landing: 1.0,
            impact: 1.0,
            auto_push: None,
            assisted_air: None,
            tight_flicks: false,
            flick_120hz: false,
            drift_powerslide: false,
            powerslide_turn: 1.0,
            drift_grip: 0.3,
            drift_full_grip: 0.6,
            bowl_boost: 1.0,
        }
    }
}
impl FeelTuning {
    pub fn validate(self) -> Result<(), String> {
        let in_range = |v: f32, low: f32, high: f32| v.is_finite() && (low..=high).contains(&v);
        for (v, low, high) in [
            (self.flick_radius, 0.5, 2.0),
            (self.flick_window, 0.5, 3.0),
            (self.flick_pace, 0.5, 2.0),
            (self.gravity, 0.5, 1.5),
            (self.boneless, 0.5, 3.0),
            (self.hippy, 0.5, 3.0),
            (self.rail_magnetism, 0.25, 3.0),
            (self.grind_pop, 0.5, 2.0),
            (self.grind_friction, 0.0, 3.0),
            (self.grind_tolerance, 0.5, 3.0),
            (self.camera_follow, 1.0, 3.0),
            (self.camera_pullback, 0.0, 1.5),
            (self.wall_follow, 0.0, 1.0),
            (self.braking, 0.25, 3.0),
            (self.steering, 0.5, 2.0),
            (self.carve, 0.5, 2.0),
            (self.grip, 0.5, 2.0),
            (self.powerslide, 0.25, 3.0),
            (self.rolling_friction, 0.0, 3.0),
            (self.hill_speed, 0.0, 2.0),
            (self.pump, 0.0, 3.0),
            (self.bowl_boost, 0.0, 2.0),
            (self.wobble, 0.0, 3.0),
            (self.wobble_onset, 0.5, 3.0),
            (self.manual_drift, 0.0, 3.0),
            (self.landing, 0.5, 3.0),
            (self.impact, 0.5, 3.0),
            (self.powerslide_turn, 0.25, 1.5),
            (self.drift_grip, 0.0, 1.5),
            (self.drift_full_grip, 0.0, 1.5),
        ] {
            if !in_range(v, low, high) {
                return Err("Invalid skating feel".into());
            }
        }
        Ok(())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn stock_and_extremes_validate_without_accepting_nan() {
        assert!(FeelTuning::default().validate().is_ok());
        assert!(FeelTuning { gravity: f32::NAN, ..Default::default() }.validate().is_err());
        assert!(FeelTuning { drift_grip: 1.6, ..Default::default() }.validate().is_err());
    }
}
