//! Per-tick host assists on the complete physical assembly.
use super::Session;
use crate::core::{math::Vector3, physics::board::BodyId, player::state::PhysicalStateId};
impl Session {
    pub(super) fn deck_speed(&self) -> f32 {
        let v = self.physics.board.bodies()[BodyId::Deck.index()].rates.linear_velocity;
        (v.x * v.x + v.y * v.y + v.z * v.z).sqrt()
    }
    pub(super) fn drift_across(&self) -> bool {
        let deck = self.physics.board.part_transforms()[BodyId::Deck.index()];
        let u = deck.basis.columns[1];
        let f = deck.basis.columns[2];
        let v = self.physics.board.bodies()[BodyId::Deck.index()].rates.linear_velocity;
        let vu = v.x * u[0] + v.y * u[1] + v.z * u[2];
        let fu = f[0] * u[0] + f[1] * u[1] + f[2] * u[2];
        let tv = [v.x - u[0] * vu, v.y - u[1] * vu, v.z - u[2] * vu];
        let tf = [f[0] - u[0] * fu, f[1] - u[1] * fu, f[2] - u[2] * fu];
        let vv = tv.iter().map(|x| x * x).sum::<f32>();
        let ff = tf.iter().map(|x| x * x).sum::<f32>();
        vv > 1.0 && ff > 0.0 && (tv[0] * tf[0] + tv[1] * tf[1] + tv[2] * tf[2]).abs() < 0.978 * (vv * ff).sqrt()
    }
    pub(super) fn prepare_assists(&mut self) -> f32 {
        let state = self.skater.player_state.current();
        let sliding = state == PhysicalStateId::SlideGround;
        if self.feel.drift_powerslide {
            self.controls.preferences.drift_hold = sliding && self.drift_hold < 30 && self.drift_across();
        }
        self.deck_speed()
    }
    pub(super) fn sampled_assists(&mut self) {
        let words = self.controls.controller.words();
        let state = self.skater.player_state.current();
        let sliding = state == PhysicalStateId::SlideGround;
        if self.feel.drift_powerslide {
            let left = [f32::from_bits(words[7]), f32::from_bits(words[8])];
            let asking = crate::core::input::riding_intentions::asks_powerslide(left, self.controls.preferences);
            let holding = self.controls.preferences.drift_hold && !asking;
            self.drift_hold = if sliding && !asking { self.drift_hold + 1 } else { 0 };
            let depth = ((-left[1] - 0.5) / (0.95 - 0.5)).clamp(0.0, 1.0);
            let s = &mut self.skater.slide_state.settings;
            s.turn_scale = if holding { 0.0 } else { self.feel.powerslide_turn };
            s.friction_scale = if holding {
                self.feel.drift_grip
            } else {
                self.feel.drift_grip + (self.feel.drift_full_grip - self.feel.drift_grip) * depth
            };
        }
    }
    pub(super) fn finish_assists(&mut self, before: f32) {
        let state = self.skater.player_state.current();
        let sliding = state == PhysicalStateId::SlideGround;
        let ground = state == PhysicalStateId::PhysicsGround || state == PhysicalStateId::RevertGround;
        let grounded = sliding || ground;
        let words = self.controls.controller.words();
        let dt = self.period();
        self.boost.trigger(
            f32::from_bits(words[11]) > super::boost::BowlBoost::CROUCH
                || f32::from_bits(words[12]) > super::boost::BowlBoost::CROUCH,
            grounded,
            dt,
        );
        let deck = self.physics.board.part_transforms()[BodyId::Deck.index()];
        let after = self.deck_speed();
        let gain = self.boost.tick(
            self.boost.zone,
            self.feel.bowl_boost,
            grounded,
            deck.basis.columns[1][1],
            ground && self.boost.standing(),
            sliding,
            before,
            after,
            dt,
        );
        if gain > 0.0 && after > 0.5 {
            let v = self.physics.board.bodies()[BodyId::Deck.index()].rates.linear_velocity;
            let dv = Vector3::new(v.x * (gain / after), v.y * (gain / after), v.z * (gain / after));
            for b in self.physics.board.bodies_mut() {
                b.rates.linear_velocity.x += dv.x;
                b.rates.linear_velocity.y += dv.y;
                b.rates.linear_velocity.z += dv.z;
            }
            for b in self.skater.skeleton.bodies_mut() {
                b.rates.linear_velocity.x += dv.x;
                b.rates.linear_velocity.y += dv.y;
                b.rates.linear_velocity.z += dv.z;
            }
            self.boost.total += gain;
        }
        let target = if state == PhysicalStateId::WipeoutGround {
            0.0
        } else {
            let t = ((self.deck_speed() - 25.0) / 20.0).clamp(0.0, 1.0);
            self.feel.camera_pullback * t * t * (3.0 - 2.0 * t)
        };
        self.camera_pull += (target - self.camera_pull) * (1.0 - (-self.period() / 0.8).exp());
    }
}
