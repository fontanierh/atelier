//! Reject a lost session before it is shown. Landing allowance follows actual solved ticks, not host cadence.
use bevy::prelude::*;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Verdict {
    #[default]
    Kept,
    Teleport,
    Jump,
    ThroughFloor,
}
#[derive(Clone, Copy, Debug, Default)]
pub struct HeldFloor {
    at: Vec3,
    normal: Vec3,
    held: bool,
}
pub struct Step {
    pub state: u32,
    pub tick: u64,
    pub ticks: u64,
    pub from: Vec3,
    pub to: Vec3,
    pub velocity: Vec3,
    pub speed: f32,
}
const TRACE_ABOVE: f32 = 0.3;
const THROUGH_DEPTH: f32 = 0.25;
const FLOOR_UP: f32 = 0.5;
fn board_air(state: u32) -> bool {
    matches!(state, 200..=202)
}
fn under(to: Vec3, at: Vec3, normal: Vec3) -> f32 {
    (at - to).dot(normal)
}

pub fn observe(
    step: &Step,
    held: &mut HeldFloor,
    mut trace: impl FnMut(Vec3, Vec3) -> Option<(Vec3, Vec3)>,
) -> Verdict {
    let mut crossing = None;
    if board_air(step.state) && step.to.y < step.from.y {
        let mut start = step.from + Vec3::Y * TRACE_ABOVE;
        if held.held && held.normal.y > FLOOR_UP {
            let floor = held.at.y
                - ((step.from.x - held.at.x) * held.normal.x + (step.from.z - held.at.z) * held.normal.z)
                    / held.normal.y;
            start.y = start.y.max(floor + TRACE_ABOVE);
        }
        if let Some((at, normal)) = trace(start, step.to) {
            let over = Vec3::new(step.to.x, step.to.y.max(at.y) + TRACE_ABOVE, step.to.z);
            if trace(step.to, over).is_some() {
                crossing = Some((at, normal));
            }
        }
    }
    let verdict = judge(step, crossing);
    if verdict != Verdict::Kept || !board_air(step.state) {
        *held = HeldFloor::default();
    } else if let Some((at, normal)) = crossing.filter(|(at, n)| n.y > FLOOR_UP && under(step.to, *at, *n) > 0.) {
        *held = HeldFloor { at, normal, held: true };
    } else if !held.held || under(step.to, held.at, held.normal) <= 0. {
        *held = HeldFloor::default();
    }
    verdict
}
fn judge(step: &Step, crossing: Option<(Vec3, Vec3)>) -> Verdict {
    if step.tick < 30 {
        return Verdict::Kept;
    }
    if step.state == 702 {
        return Verdict::Teleport;
    }
    if step.from.distance(step.to) > 0.5 + 2. * step.speed * (1. / 60.) * step.ticks.max(2) as f32 {
        return Verdict::Jump;
    }
    if let Some((at, normal)) = crossing {
        if board_air(step.state) && step.to.y < step.from.y && normal.y > FLOOR_UP && step.velocity.dot(normal) < 0. {
            let threshold =
                if step.from.y >= at.y { THROUGH_DEPTH + step.speed * (1. / 60.) * 1.5 } else { THROUGH_DEPTH };
            if under(step.to, at, normal) > threshold {
                return Verdict::ThroughFloor;
            }
        }
    }
    Verdict::Kept
}
#[cfg(test)]
mod tests {
    use super::*;
    fn step(from: Vec3, to: Vec3) -> Step {
        Step { state: 200, tick: 100, ticks: 1, from, to, velocity: Vec3::new(40., -40., 0.), speed: 50. }
    }
    #[test]
    fn legal_fast_first_touchdown_is_kept_but_continued_fall_is_caught() {
        let first = step(Vec3::new(0., 0.1, 0.), Vec3::new(0.7, -0.6, 0.));
        assert_eq!(judge(&first, Some((Vec3::ZERO, Vec3::Y))), Verdict::Kept);
        let next = step(first.to, Vec3::new(1.4, -1.2, 0.));
        assert_eq!(judge(&next, Some((Vec3::ZERO, Vec3::Y))), Verdict::ThroughFloor);
    }
    #[test]
    fn catchup_uses_solved_ticks_and_recovery_teleport_is_never_shown() {
        let mut s = step(Vec3::ZERO, Vec3::new(5., 0., 0.));
        s.ticks = 6;
        assert_eq!(judge(&s, None), Verdict::Kept);
        s.ticks = 1;
        assert_eq!(judge(&s, None), Verdict::Jump);
        s.to = s.from;
        s.state = 702;
        assert_eq!(judge(&s, None), Verdict::Teleport);
    }
    #[test]
    fn held_floor_trace_starts_above_previous_allowed_penetration() {
        let mut held = HeldFloor { at: Vec3::ZERO, normal: Vec3::Y, held: true };
        let s = step(Vec3::new(0., -0.6, 0.), Vec3::new(0.7, -1.2, 0.));
        let mut calls = 0;
        let verdict = observe(&s, &mut held, |start, end| {
            calls += 1;
            if calls == 1 {
                assert!(start.y >= 0.3);
            }
            Some((Vec3::ZERO, if end.y < start.y { Vec3::Y } else { Vec3::NEG_Y }))
        });
        assert_eq!(verdict, Verdict::ThroughFloor);
    }
}
