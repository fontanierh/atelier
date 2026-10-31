//! TU3 `Skateboard::Toolkit_CalcHippyJumpVel` at `0x82D79F00`.
//!
//! The helper constructs the rider trajectory velocity used by
//! `PhysState_LandingOnDeck::InitTraj`; it does not write board-body velocity.

pub type Vector = [f32; 4];

#[derive(Clone, Copy, Debug)]
pub struct Input {
    pub desired_height: f32,
    pub gravity_scale: f32,
    pub board_position: Vector,
    pub centre_of_mass_position: Vector,
    pub reference_up: Vector,
    pub current_velocity: Vector,
}

pub fn calculate(input: Input) -> Vector {
    let up = input.reference_up;
    let displacement = sub(input.centre_of_mass_position, input.board_position);
    let current_height = dot3(up, displacement);
    let vertical_velocity = dot3(up, input.current_velocity);
    let planar_velocity = sub(input.current_velocity, scale(up, vertical_velocity));
    let launch_speed = ((input.desired_height - current_height) * (19.6 * input.gravity_scale)).sqrt();
    add(planar_velocity, scale(up, launch_speed))
}

fn dot3(a: Vector, b: Vector) -> f32 {
    a[0].mul_add(b[0], a[1].mul_add(b[1], a[2] * b[2]))
}
fn add(a: Vector, b: Vector) -> Vector {
    core::array::from_fn(|i| a[i] + b[i])
}
fn sub(a: Vector, b: Vector) -> Vector {
    core::array::from_fn(|i| a[i] - b[i])
}
fn scale(v: Vector, scalar: f32) -> Vector {
    core::array::from_fn(|i| v[i] * scalar)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn gravity_changes_airtime_not_authored_height_and_is_not_global() {
        let input = Input {
            desired_height: 2.0,
            gravity_scale: 1.0,
            board_position: [0.0; 4],
            centre_of_mass_position: [0.0, 0.5, 0.0, 0.0],
            reference_up: [0.0, 1.0, 0.0, 0.0],
            current_velocity: [3.0, -2.0, 4.0, 0.0],
        };
        let stock = calculate(input);
        let mut previous_apex_time = f32::MAX;
        for gravity_scale in [0.5, 1.0, 1.5] {
            let launch = calculate(Input { gravity_scale, ..input });
            let gravity = 9.8 * gravity_scale;
            let apex_time = launch[1] / gravity;
            let height = 0.5 + launch[1] * apex_time - 0.5 * gravity * apex_time * apex_time;
            assert!((height - 2.0).abs() < 1.0e-6);
            assert!(apex_time < previous_apex_time);
            previous_apex_time = apex_time;
            assert_eq!(launch[0], 3.0);
            assert_eq!(launch[2], 4.0);
        }
        assert_eq!(calculate(input).map(f32::to_bits), stock.map(f32::to_bits));
    }

    #[test]
    fn preserves_planar_velocity_and_replaces_up_component() {
        let output = calculate(Input {
            desired_height: 1.5,
            gravity_scale: 1.0,
            board_position: [0.0, 0.0, 0.0, 0.0],
            centre_of_mass_position: [0.0, 0.5, 0.0, 0.0],
            reference_up: [0.0, 1.0, 0.0, 0.0],
            current_velocity: [3.0, -2.0, 4.0, 0.0],
        });
        assert_eq!(output[0], 3.0);
        assert_eq!(output[2], 4.0);
        assert!((output[1] - 19.6f32.sqrt()).abs() < 1.0e-6);
    }
}
