//! Applies the persisted feel to a live session. The settings crate owns defaults and preset resolution.
use crate::{FeelTuning, Session};
use hakuba_settings::SkatePreferences;

pub(super) fn apply(session: &mut Session, saved: &SkatePreferences) -> Result<(), String> {
    saved.validate()?;
    let p = saved.effective();
    session.configure(p.difficulty.name(), p.goofy, p.trucks)?;
    session.tune(p.pop, p.spin, p.push_speed, p.push_power, p.vert_assist)?;
    session.set_control_feel(p.stick_dead_zone, p.stick_reach, p.get_up_delay)?;
    session.set_feel(FeelTuning {
        flick_radius: p.flick_radius,
        flick_window: p.flick_window,
        flick_pace: p.flick_pace,
        gravity: p.gravity,
        boneless: p.boneless,
        hippy: p.hippy,
        rail_magnetism: p.rail_magnetism,
        grind_pop: p.grind_pop,
        grind_friction: p.grind_friction,
        grind_tolerance: p.grind_tolerance,
        camera_follow: p.camera_follow,
        camera_pullback: p.camera_pullback,
        wall_follow: p.wall_follow,
        braking: p.braking,
        steering: p.steering,
        carve: p.carve,
        grip: p.grip,
        powerslide: p.powerslide,
        rolling_friction: p.rolling_friction,
        hill_speed: p.hill_speed,
        pump: p.pump,
        wobble: p.wobble,
        wobble_onset: p.wobble_onset,
        manual_drift: p.manual_drift,
        landing: p.landing,
        impact: p.impact,
        auto_push: p.auto_push,
        assisted_air: p.assisted_air,
        tight_flicks: p.tight_flicks,
        drift_powerslide: p.drift_powerslide,
        powerslide_turn: p.powerslide_turn,
        drift_grip: p.drift_grip,
        drift_full_grip: p.drift_full_grip,
        bowl_boost: p.bowl_boost,
    })
}
