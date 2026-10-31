//! Per-session gravity for physical bodies and their predicted movement.
use super::Session;

impl Session {
    /// Apply from captured authored gravity, never from the previous multiplier.
    /// Every controller keeps its own scale; independent sessions share no mutable gravity.
    pub fn set_gravity(&mut self, scale: f32) -> Result<(), String> {
        if !scale.is_finite() || !(0.5..=1.5).contains(&scale) {
            return Err("Invalid skating gravity".into());
        }
        let settings = &mut self.physics.settings;
        if settings.gravity_scale == scale {
            return Ok(());
        }
        let previous = settings.step.simulation.gravity_acceleration;
        settings.gravity_scale = scale;
        let g = settings.authored_gravity;
        settings.step.simulation.gravity_acceleration =
            crate::core::math::Vector3::new(g.x * scale, g.y * scale, g.z * scale);
        // DynamicUpdate retains gravity in each body for the next integration.
        // Update that seed too so the first tick does not use the old setting.
        let next = settings.step.simulation.gravity_acceleration;
        let delta = crate::core::math::Vector3::new(next.x - previous.x, next.y - previous.y, next.z - previous.z);
        for body in self.physics.board.bodies_mut().iter_mut().chain(self.skater.skeleton.bodies_mut()) {
            if body.inertia.inverse_mass != 0.0 {
                body.rates.force_acceleration.x += delta.x;
                body.rates.force_acceleration.y += delta.y;
                body.rates.force_acceleration.z += delta.z;
            }
        }
        self.skater.handplant.gravity_scale = scale;
        self.skater.landing_deck.manager.gravity_scale = scale;
        self.skater.biped_ground.set_gravity(scale);
        self.skater.player_input.processed.gravity_2648 = f32::from_bits(0xc11c_cccd) * scale;
        Ok(())
    }
}
