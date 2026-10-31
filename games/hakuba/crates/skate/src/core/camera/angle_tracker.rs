//! TU3 angular-tracking candidates; exceptional wrap conversion is unavailable.
use super::{ScalarTracker, ScalarTrackerParameters};

/// Angular state has the same six-word layout as the scalar tracker. Angles
/// and angular rates use radians; effective settings are explicitly supplied.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct AngleTracker(pub ScalarTracker);

impl AngleTracker {
    pub fn update(&mut self, dt: f32, target: f32, parameters: ScalarTrackerParameters) {
        let state = &mut self.0;
        let position = state.position;
        state.target = target;
        let delta = normalize_angle(target - position);
        if parameters.overshoot_zeroes_velocity && state.velocity * delta < 0.0 {
            state.velocity *= 0.0;
        }
        let velocity = state.velocity;
        let inverse_dt = 1.0 / dt;
        state.acceleration = inverse_dt.mul_add(delta, -velocity) * inverse_dt;
        let magnitude = delta.abs();
        let fraction = if magnitude < parameters.delta_umbra {
            1.0
        } else if magnitude < parameters.delta_penumbra {
            1.0 - (magnitude - parameters.delta_umbra) / (parameters.delta_penumbra - parameters.delta_umbra)
        } else {
            0.0
        };
        if state.acceleration * delta > 0.0 {
            state.acceleration_clamp = super::tracker::interpolate(
                parameters.acceleration_clamp_min,
                parameters.acceleration_clamp_max,
                fraction,
            );
            let magnitude = state.acceleration.abs();
            if magnitude > state.acceleration_clamp {
                state.acceleration = (state.acceleration / magnitude) * state.acceleration_clamp;
            }
        }
        state.velocity = state.acceleration.mul_add(dt, velocity);
        let magnitude = state.velocity.abs();
        if magnitude > parameters.speed_clamp {
            state.velocity = (state.velocity / magnitude) * parameters.speed_clamp;
        }
        // Native normalizes each intermediate separately. Combining these into
        // a single wrap, or fusing the position addition, changes boundary cases.
        let next = normalize_angle(normalize_angle(state.velocity * dt) + position);
        state.smoothing = super::tracker::interpolate(parameters.smoothing_min, parameters.smoothing_max, fraction);
        let displacement = normalize_angle(next - position);
        let smoothed = normalize_angle(displacement * (1.0 - state.smoothing));
        state.position = normalize_angle(smoothed + position);
    }
}

/// The input whose exceptional wrap conversion was reached, raised as a panic payload on native unwinding builds. Only
/// `CameraRuntime::advance` catches it, as a terminal error; no angle is substituted.
#[cfg(all(not(target_family = "wasm"), panic = "unwind"))]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct ExceptionalAngleConversion {
    pub angle_bits: u32,
}

/// Candidate 8258DB98 wrapping sequence. Its fast interval is [-pi, pi), and
/// its reduction uses truncation followed by one correction, not rem_euclid.
pub fn normalize_angle(angle: f32) -> f32 {
    const PI: f32 = f32::from_bits(0x40490fdb);
    const NEG_PI: f32 = f32::from_bits(0xc0490fdb);
    const INV_TAU: f32 = f32::from_bits(0x3e22f983);
    const TAU: f32 = f32::from_bits(0x40c90fdb);
    if angle >= NEG_PI && angle < PI {
        return angle;
    }
    let turns = angle * INV_TAU;
    // Ordinary finite truncation follows the native fctiwz operation. Its
    // exceptional/overflow results are unresolved; do not borrow host rules.
    if !turns.is_finite() || turns < i32::MIN as f32 || turns as f64 > i32::MAX as f64 {
        // Native builds raise a typed payload that the camera owner turns into a terminal skating error; the browser
        // build keeps the original panic.
        #[cfg(all(not(target_family = "wasm"), panic = "unwind"))]
        std::panic::panic_any(ExceptionalAngleConversion { angle_bits: angle.to_bits() });
        #[cfg(not(all(not(target_family = "wasm"), panic = "unwind")))]
        panic!("Skate 3 exceptional angle integer conversion is unavailable: independent implementation required");
    }
    let count = turns as i32;
    let count = count as f32;
    let reduced = -((count as f64).mul_add(TAU as f64, -(angle as f64))) as f32;
    if reduced >= PI {
        reduced - TAU
    } else if reduced < NEG_PI {
        reduced + TAU
    } else {
        reduced
    }
}

#[cfg(all(test, not(target_family = "wasm"), panic = "unwind"))]
mod tests {
    use super::*;

    #[test]
    fn supported_wraps_keep_their_exact_words() {
        // Words from the unchanged truncate-then-correct sequence, not a modulo oracle.
        for (input, output) in [
            (0x0000_0000, 0x0000_0000),
            (0x8000_0000, 0x8000_0000),
            (0x4049_0fdb, 0xc049_0fdb),
            (0xc049_0fdb, 0xc049_0fdb),
            (0x40e0_0000, 0x3f37_8128),
            (0xc0e0_0000, 0xbf37_8128),
            (0x4060_0000, 0xc032_1fb6),
            (0xc060_0000, 0x4032_1fb6),
            (0x42c8_0000, 0xbf07_ed80),
            (0xc2c8_0000, 0x3f07_ed80),
            (0x4974_2400, 0xbec5_5210),
            (0x4e6e_6b28, 0xc1da_0049),
            (0xce6e_6b28, 0x41da_0049),
        ] {
            assert_eq!(normalize_angle(f32::from_bits(input)).to_bits(), output, "input {input:#010x}");
        }
    }

    #[test]
    fn exceptional_conversions_raise_their_exact_input() {
        for angle in [
            f32::from_bits(0x7fc0_0001),
            f32::from_bits(0xffc0_0000),
            f32::INFINITY,
            f32::NEG_INFINITY,
            f32::MAX,
            f32::MIN,
            1.5e10,
            -1.5e10,
        ] {
            let payload = std::panic::catch_unwind(|| normalize_angle(angle)).unwrap_err();
            let raised = payload.downcast::<ExceptionalAngleConversion>().expect("typed payload");
            assert_eq!(raised.angle_bits, angle.to_bits());
        }
        // The zero-state, zero-step tracker reaches the conversion with a NaN rate.
        let zero = super::super::ScalarTracker {
            target: 0.0,
            position: 0.0,
            velocity: 0.0,
            acceleration: 0.0,
            acceleration_clamp: 0.0,
            smoothing: 0.0,
        };
        let parameters = ScalarTrackerParameters {
            delta_umbra: 1.0,
            delta_penumbra: 2.0,
            speed_clamp: 1.0,
            acceleration_clamp_min: 1.0,
            acceleration_clamp_max: 1.0,
            smoothing_min: 0.0,
            smoothing_max: 0.0,
            overshoot_zeroes_velocity: false,
        };
        let mut tracker = AngleTracker(zero);
        let payload = std::panic::catch_unwind(move || tracker.update(0.0, 0.0, parameters));
        assert!(payload.unwrap_err().is::<ExceptionalAngleConversion>());
    }
}
