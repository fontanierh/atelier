#[derive(Clone, Copy, Debug, PartialEq)]
pub struct TrainerTuning {
    pub pop: f32,
    pub grind_pop: f32,
    pub push_speed: f32,
    pub push_power: f32,
    pub braking: f32,
    pub steering: f32,
    pub wobble: f32,
    pub offboard_jump: f32,
    pub grip: f32,
    pub turn_power: f32,
    pub manual_drag: f32,
    pub hold_fakie: bool,
    pub rolling_friction: f32,
    pub hill_speed: f32,
    pub wobble_onset: f32,
    pub manual_drift: f32,
    pub grind_friction: f32,
    pub hippy: f32,
}
impl Default for TrainerTuning {
    fn default() -> Self {
        Self {
            pop: 1.,
            grind_pop: 1.,
            push_speed: 1.,
            push_power: 1.,
            braking: 1.,
            steering: 1.,
            wobble: 1.,
            offboard_jump: 1.,
            grip: 1.,
            turn_power: 1.,
            manual_drag: 1.,
            hold_fakie: false,
            rolling_friction: 1.0,
            hill_speed: 1.0,
            wobble_onset: 1.0,
            manual_drift: 1.0,
            grind_friction: 1.0,
            hippy: 1.0,
        }
    }
}
