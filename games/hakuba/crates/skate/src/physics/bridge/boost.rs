//! Zone boost timing and speed caps, independent of the physical pump controller.
#[derive(Clone, Copy, Debug, Default)]
pub(super) struct BowlBoost {
    pub zone: f32,
    pub entry: f32,
    pub inside: bool,
    pub total: f32,
    crouched: f32,
    stand: f32,
}
impl BowlBoost {
    pub const CROUCH: f32 = 30.0 / 255.0;
    pub fn reset_input(&mut self) {
        self.crouched = 0.0;
        self.stand = 0.0;
    }
    pub fn trigger(&mut self, pulled: bool, grounded: bool, dt: f32) {
        if pulled {
            self.stand = 0.0;
            self.crouched = if grounded { self.crouched + dt } else { 0.0 };
            return;
        }
        self.stand = if self.crouched >= 0.15 { 0.7 } else { (self.stand - dt).max(0.0) };
        self.crouched = 0.0;
    }
    pub fn standing(&self) -> bool {
        self.stand > 1.0e-4
    }
    pub fn tick(
        &mut self,
        zone: f32,
        feel: f32,
        grounded: bool,
        up_cos: f32,
        pumping: bool,
        sliding: bool,
        before: f32,
        after: f32,
        dt: f32,
    ) -> f32 {
        if !(zone > 0.0) {
            self.inside = false;
            return 0.0;
        }
        if !before.is_finite() || !after.is_finite() {
            return 0.0;
        }
        if !self.inside {
            self.inside = true;
            self.entry = before;
        }
        let scale = if grounded { zone * feel } else { 0.0 };
        if !(scale > 0.0) || !(up_cos < 0.978) {
            return 0.0;
        }
        let mut gain = if pumping { 6.0 * dt * scale } else { 0.0 };
        if sliding {
            gain += ((before - after).max(0.0).min(6.0 * dt) + 5.0 * dt) * scale;
        }
        let cap = (self.entry * (1.0 + 0.8 * scale)).max(24.0);
        (cap - after).clamp(0.0, gain)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn pump_requires_ground_crouch_then_release_and_stops_on_repull() {
        let mut b = BowlBoost::default();
        let dt = 1.0 / 60.0;
        b.trigger(true, false, 0.3);
        b.trigger(false, false, dt);
        assert!(!b.standing());
        b.trigger(true, true, 0.2);
        b.trigger(false, true, dt);
        assert!(b.standing());
        b.trigger(true, true, dt);
        assert!(!b.standing());
    }
    #[test]
    fn air_retains_entry_cap_and_flat_ground_never_boosts() {
        let mut b = BowlBoost::default();
        let dt = 1.0 / 60.0;
        assert_eq!(b.tick(1.0, 1.0, true, 1.0, true, false, 20.0, 20.0, dt), 0.0);
        assert_eq!(b.entry, 20.0);
        assert_eq!(b.tick(1.0, 1.0, false, 0.5, true, false, 32.0, 32.0, dt), 0.0);
        assert_eq!(b.entry, 20.0);
        assert!((b.tick(1.0, 1.0, true, 0.5, true, false, 35.99, 35.99, dt) - 0.01).abs() < 1.0e-4);
        b.tick(0.0, 1.0, false, 0.5, false, false, 0.0, 0.0, dt);
        assert!(!b.inside);
    }
    #[test]
    fn slide_gain_keeps_only_bounded_loss() {
        let mut b = BowlBoost::default();
        let gain = b.tick(1.0, 1.0, true, 0.5, false, true, 14.0, 13.0, 1.0 / 60.0);
        assert!((gain - 11.0 / 60.0).abs() < 1.0e-6);
    }
}
