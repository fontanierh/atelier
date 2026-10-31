//! Complete normal-camera ShakeEffect update82E05800.
use super::manager_state::clamp;
use super::{ShakeEffect, ShakeSamples, ShakeSettings};
use crate::core::math::Basis3;

impl ShakeEffect {
    pub fn update(
        &mut self,
        dt: f32,
        speed: f32,
        distance: f32,
        basis: Basis3,
        enabled: bool,
        samples: &ShakeSamples,
        settings: ShakeSettings,
    ) -> Basis3 {
        self.weight =
            clamp(if enabled { dt.mul_add(5.0, self.weight) } else { -dt.mul_add(5.0, -self.weight) }, 0.0, 1.0);
        let mut amplitude = if settings.amplitude_top_speed != 0.0 {
            super::shake_curve::sample(settings.amplitude_curve, clamp(speed / settings.amplitude_top_speed, 0.0, 1.0))
                .mul_add(settings.amplitude_maximum - settings.amplitude_minimum, settings.amplitude_minimum)
        } else {
            settings.amplitude_minimum
        };
        let high_speed = if settings.high_speed_end > settings.high_speed_start {
            let t = clamp(
                (speed - settings.high_speed_start) / (settings.high_speed_end - settings.high_speed_start),
                0.0,
                1.0,
            );
            t * t * (3.0 - 2.0 * t)
        } else {
            0.0
        };
        if settings.high_speed_end > settings.high_speed_start {
            amplitude *= 1.0 + high_speed * (settings.high_speed_amplitude - 1.0);
        }
        let amplitude = (self.impulse + amplitude) * self.weight;
        let mut frequency = if settings.frequency_top_speed != 0.0 {
            super::shake_curve::sample(settings.frequency_curve, clamp(speed / settings.frequency_top_speed, 0.0, 1.0))
                .mul_add(settings.frequency_maximum - settings.frequency_minimum, settings.frequency_minimum)
        } else {
            settings.frequency_minimum
        };
        if high_speed > 0.0 {
            frequency *= 1.0 + high_speed * (settings.high_speed_frequency - 1.0);
        }
        if self.impulse > 0.0 {
            frequency = settings.impulse_frequency;
        }
        self.time = (settings.data_frames_per_second * frequency).mul_add(dt, self.time);
        let inverse = super::vector_tracker::refined_reciprocal(1.0);
        let whole = (inverse * self.time).trunc();
        let fraction = (-whole).mul_add(1.0, self.time);
        let left = (self.time - fraction) as u32 as usize % samples.rotations.len();
        let right = (left + 1) % samples.rotations.len();
        let distance_weight = clamp((f32::from_bits(0x4059999a) - distance) * f32::from_bits(0x3fd55552), 0.0, 1.0);
        let inverse_fraction = 1.0 - fraction;
        let mut angles: [f32; 3] = core::array::from_fn(|i| {
            let interpolated =
                samples.rotations[left][i].mul_add(inverse_fraction, samples.rotations[right][i] * fraction);
            ((interpolated * amplitude) * distance_weight) * settings.rotation_multiplier
        });
        // vrlimi mask2 selects Z (Dutch/roll), not Y.
        angles[2] *= settings.dutch_multiplier;
        let rotation = super::orientation_math::basis_from_angles(angles[0], angles[1], angles[2]);
        let local_translation: [f32; 3] = core::array::from_fn(|i| {
            let interpolated =
                samples.translations[left][i].mul_add(inverse_fraction, samples.translations[right][i] * fraction);
            ((interpolated * settings.translation_multiplier) * amplitude) * distance_weight
        });
        self.translation = core::array::from_fn(|i| {
            if i == 3 {
                0.0
            } else {
                basis.columns[2][i].mul_add(
                    local_translation[2],
                    basis.columns[1][i]
                        .mul_add(local_translation[1], basis.columns[0][i].mul_add(local_translation[0], 0.0)),
                )
            }
        });
        let result = Basis3 {
            columns: rotation.columns.map(|column| {
                core::array::from_fn(|i| {
                    column[2].mul_add(
                        basis.columns[2][i],
                        column[1].mul_add(basis.columns[1][i], column[0] * basis.columns[0][i]),
                    )
                })
            }),
        };
        self.impulse = (1.0 - settings.impulse_decay) * self.impulse;
        if self.impulse < f32::from_bits(0x3ba3d70a) {
            self.impulse = 0.0;
        }
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn settings() -> ShakeSettings {
        ShakeSettings {
            amplitude_curve: [[0.0; 4]; 4],
            frequency_curve: [[0.0; 4]; 4],
            impulse_magnitude: 1.0,
            impulse_minimum_velocity: 1.0,
            impulse_maximum_velocity: 10.0,
            impulse_frequency: 3.0,
            impulse_decay: 0.0,
            amplitude_minimum: 1.0,
            amplitude_maximum: 1.0,
            amplitude_top_speed: 0.0,
            frequency_minimum: 1.0,
            frequency_maximum: 1.0,
            frequency_top_speed: 0.0,
            data_frames_per_second: 1.0,
            translation_multiplier: 1.0,
            rotation_multiplier: 0.0,
            dutch_multiplier: 1.0,
            high_speed_start: 0.0,
            high_speed_end: 0.0,
            high_speed_amplitude: 1.0,
            high_speed_frequency: 1.0,
        }
    }
    fn samples() -> ShakeSamples {
        ShakeSamples { rotations: vec![[0.0; 4]], translations: vec![[1.0, 0.0, 0.0, 0.0]] }
    }
    #[test]
    fn camera_follow_eases_only_speed_shake_and_keeps_landing_impulse() {
        let s = settings();
        let mut eased = s;
        eased.high_speed_start = 30.0;
        eased.high_speed_end = 40.0;
        eased.high_speed_amplitude = 0.25;
        eased.high_speed_frequency = 0.5;
        let mut stock = ShakeEffect::new();
        let mut fast = stock;
        stock.update(
            0.2,
            40.0,
            0.0,
            Basis3 { columns: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]] },
            true,
            &samples(),
            s,
        );
        fast.update(
            0.2,
            40.0,
            0.0,
            Basis3 { columns: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]] },
            true,
            &samples(),
            eased,
        );
        assert_eq!(fast.translation[0], stock.translation[0] * 0.25);
        assert_eq!(fast.time, stock.time * 0.5);
        let mut stock = ShakeEffect::new();
        let mut fast = stock;
        stock.impulse = 2.0;
        fast.impulse = 2.0;
        stock.update(
            0.2,
            40.0,
            0.0,
            Basis3 { columns: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]] },
            true,
            &samples(),
            s,
        );
        fast.update(
            0.2,
            40.0,
            0.0,
            Basis3 { columns: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]] },
            true,
            &samples(),
            eased,
        );
        assert_eq!(stock.time, fast.time);
        assert_eq!(fast.translation[0], 2.25);
        assert_eq!(stock.translation[0], 3.0);
    }
    #[test]
    fn disabled_high_speed_range_is_exact_stock_at_all_speeds() {
        let s = settings();
        let mut off = s;
        off.high_speed_start = 50.0;
        off.high_speed_end = 30.0;
        off.high_speed_amplitude = 0.25;
        off.high_speed_frequency = 0.5;
        for speed in [0.0, 20.0, 35.0, 60.0] {
            let mut a = ShakeEffect::new();
            let mut b = a;
            let ra = a.update(
                0.2,
                speed,
                0.0,
                Basis3 { columns: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]] },
                true,
                &samples(),
                s,
            );
            let rb = b.update(
                0.2,
                speed,
                0.0,
                Basis3 { columns: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]] },
                true,
                &samples(),
                off,
            );
            assert_eq!(a, b);
            assert_eq!(ra, rb);
        }
    }
}
