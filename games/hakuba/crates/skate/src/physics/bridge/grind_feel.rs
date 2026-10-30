//! Captured authored grind settings make live tolerance edits noncompounding.
use super::{Session, SkaterRuntime};
use crate::core::physics::grind_forces::post;

#[derive(Clone, Copy)]
pub(super) struct GrindFeelStock {
    post: post::Settings,
    max_grind_speed: f32,
}
impl GrindFeelStock {
    pub(super) fn capture(skater: &SkaterRuntime) -> Self {
        Self { post: skater.grind.post_settings(), max_grind_speed: skater.wipeout.settings.air.max_grind_speed }
    }
    fn apply(self, skater: &mut SkaterRuntime, tolerance: f32) {
        let entry = (1. + tolerance) * 0.5;
        skater.grind.set_tolerance(self.post, tolerance);
        skater.wipeout.settings.air.max_grind_speed = self.max_grind_speed * entry;
        skater.player_input.grind.entry_tolerance = entry;
        skater.player_input.grind.slide_hold = (2. * tolerance - 1.).max(1.);
    }
}
impl Session {
    /// Caller validates the public feel range .5..3 before changing the session.
    pub(super) fn apply_grind_tolerance(&mut self, tolerance: f32) {
        self.grind_stock.apply(&mut self.skater, tolerance);
    }
}
