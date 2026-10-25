//! The idle: how a character changes it, and how those changes are applied.

use anyhow::{Result, bail};
use glam::{DMat3, DVec3};

use crate::pose::{Pose, UP, hinge_frame, level, turn};
use crate::retarget::place;
use crate::rig::{self, RIG, Skeleton};

/// A character's changes to the idle.
pub trait Idle: Skeleton {
    /// How the character stands in it.
    fn stance(&self) -> Stance {
        Stance::NONE
    }
}

/// A standing pose laid over the idle, which keeps its breathing. The feet stay where the idle plants them.
/// Distances are in centimetres, angles in degrees.
pub struct Stance {
    /// How far the hips move forward.
    pub hips_forward_cm: f64,
    /// How much wider the feet stand, in total.
    pub foot_spacing_cm: f64,
    /// How far the spine leans forward.
    pub lean_deg: f64,
    /// How far the upper back bends forward, on top of the lean.
    pub upper_back_deg: f64,
    /// How far each knee turns outward.
    pub knees_out_deg: f64,
    /// How far each upper arm swings back: left, then right.
    pub arm_swing_deg: [f64; 2],
}

impl Stance {
    /// No change.
    pub const NONE: Self = Self {
        hips_forward_cm: 0.0,
        foot_spacing_cm: 0.0,
        lean_deg: 0.0,
        upper_back_deg: 0.0,
        knees_out_deg: 0.0,
        arm_swing_deg: [0.0; 2],
    };
}

/// The frame whose pose gives the stance's axes: left, forward, and each knee's bend plane.
const REFERENCE_FRAME: usize = 1;

/// The furthest a solved ankle may sit from its goal, in metres.
const ANKLE_TOLERANCE: f64 = 1e-5;

/// Lays `stance` over the idle `frames` of a skeleton with the rest pose `rest`.
///
/// Each local turn follows its adjusted parent, so the bones below keep the idle's motion. The hips move, and the
/// whole body is lowered as far as the longest leg needs, never stretching a leg. Each leg is then solved so its ankle
/// stays on the idle's (moved apart by the foot spacing), with its knee plane turned outward; each foot keeps the
/// idle's turn.
pub fn apply(stance: &Stance, rest: &Pose, frames: &mut [Pose]) -> Result<()> {
    let controls = [stance.hips_forward_cm, stance.foot_spacing_cm, stance.lean_deg, stance.upper_back_deg];
    if controls.iter().chain(&[stance.knees_out_deg]).chain(&stance.arm_swing_deg).all(|&value| value == 0.0) {
        return Ok(());
    }
    if frames.len() <= REFERENCE_FRAME {
        bail!("the idle is shorter than the stance's reference frame");
    }
    let original = frames.to_vec();
    let bone = rig::index;
    let rotation = |frame: &Pose, i: usize| frame[i].unwrap().rotation;
    let position = |frame: &Pose, i: usize| frame[i].unwrap().position;
    let reference = &original[REFERENCE_FRAME];
    let left = level(position(reference, bone("upper_arm_l")) - position(reference, bone("upper_arm_r"))).normalize();
    let forward = left.cross(UP);
    let deltas = [
        ("spine", stance.lean_deg),
        ("spine_mid", stance.upper_back_deg),
        ("upper_arm_l", stance.arm_swing_deg[0]),
        ("upper_arm_r", stance.arm_swing_deg[1]),
    ];

    for (frame, before) in frames.iter_mut().zip(&original) {
        for i in 0..RIG.len() {
            let Some(joint) = before[i] else { continue };
            let Some(parent) = rig::parent(i) else {
                frame[i].as_mut().unwrap().position = joint.position + forward * stance.hips_forward_cm / 100.0;
                continue;
            };
            let mut local = rotation(before, parent).transpose() * joint.rotation;
            if let Some((_, degrees)) = deltas.iter().find(|(name, _)| bone(name) == i) {
                local = turn(rotation(reference, parent).transpose() * left, *degrees) * local;
            }
            let turned = rotation(frame, parent) * local;
            let rotations: Vec<_> = frame.iter().map(|j| j.map(|j| j.rotation)).collect();
            let positions: Vec<_> = frame.iter().map(|j| j.map(|j| j.position)).collect();
            let placed = place(i, &rotations, &positions, rest);
            frame[i] = Some(crate::pose::Joint { rotation: turned, position: placed });
        }
    }

    // One pelvis height for both legs: lowered as far as either leg needs to reach its goal.
    let sides = [("l", 1.0), ("r", -1.0)];
    let leg = |side: &str| ["thigh", "shin", "foot"].map(|part| bone(&format!("{part}_{side}")));
    let length = |a: usize, b: usize| rest[a].unwrap().position.distance(rest[b].unwrap().position);
    let goals: Vec<Vec<DVec3>> = sides
        .iter()
        .map(|(side, sign)| {
            let foot = leg(side)[2];
            original.iter().map(|f| position(f, foot) + left * *sign * stance.foot_spacing_cm / 200.0).collect()
        })
        .collect();
    let mut lowering = vec![0.0f64; frames.len()];
    for ((side, _), goals) in sides.iter().zip(&goals) {
        let [thigh, shin, foot] = leg(side);
        let longest = (length(thigh, shin) + length(shin, foot)) * 0.99998;
        for (k, frame) in frames.iter().enumerate() {
            let offset = position(frame, thigh) - goals[k];
            let vertical = (longest * longest - level(offset).length_squared()).max(0.0).sqrt();
            lowering[k] = lowering[k].max(offset.y - vertical);
        }
    }
    for (frame, lower) in frames.iter_mut().zip(&lowering) {
        for joint in frame.iter_mut().flatten() {
            joint.position.y -= lower;
        }
    }

    for ((side, sign), goals) in sides.iter().zip(&goals) {
        let [thigh, shin, foot] = leg(side);
        let toe = bone(&format!("toe_{side}"));
        let (upper_length, lower_length) = (length(thigh, shin), length(shin, foot));
        let a0 = (position(reference, foot) - position(reference, thigh)).normalize();
        let v = position(reference, shin) - position(reference, thigh);
        let reference_pole = (v - a0 * v.dot(a0)).normalize();
        for (k, (frame, before)) in frames.iter_mut().zip(&original).enumerate() {
            let pole = rotation(before, bone("pelvis")) * rotation(reference, bone("pelvis")).transpose() * reference_pole;
            let hip = position(frame, thigh);
            let reach = goals[k] - hip;
            let distance = reach.length();
            if distance > upper_length + lower_length + 1e-7 || distance < (upper_length - lower_length).abs() + 1e-8 {
                bail!("the stance puts the {side} ankle out of the leg's reach");
            }
            let axis = reach.normalize();
            let pole = turn(axis, -sign * stance.knees_out_deg) * (pole - axis * pole.dot(axis)).normalize();
            let along = (upper_length.powi(2) - lower_length.powi(2) + distance.powi(2)) / (2.0 * distance);
            let knee = hip + axis * along + pole * (upper_length.powi(2) - along.powi(2)).max(0.0).sqrt();
            let (upper, lower) = ((knee - hip).normalize(), (goals[k] - knee).normalize());
            let hinge = upper.cross(lower).normalize();
            let old_upper = (position(before, shin) - position(before, thigh)).normalize();
            let old_lower = (position(before, foot) - position(before, shin)).normalize();
            let old_hinge = old_upper.cross(old_lower).normalize();
            let bend = |new: DVec3, old: DVec3| hinge_frame(new, hinge) * hinge_frame(old, old_hinge).transpose();
            let joint = |rotation: DMat3, position: DVec3| Some(crate::pose::Joint { rotation, position });
            frame[thigh] = joint(bend(upper, old_upper) * rotation(before, thigh), hip);
            frame[shin] = joint(bend(lower, old_lower) * rotation(before, shin), knee);
            frame[foot] = joint(rotation(before, foot), goals[k]);
            let rotations: Vec<_> = frame.iter().map(|j| j.map(|j| j.rotation)).collect();
            let positions: Vec<_> = frame.iter().map(|j| j.map(|j| j.position)).collect();
            let ankle = place(foot, &rotations, &positions, rest);
            if ankle.distance(goals[k]) > ANKLE_TOLERANCE {
                bail!("the stance's {side} leg misses its ankle by {:.3} mm", ankle.distance(goals[k]) * 1000.0);
            }
            let toe_turn = rotation(frame, foot) * rotation(before, foot).transpose() * rotation(before, toe);
            let positions: Vec<_> = frame.iter().map(|j| j.map(|j| j.position)).collect();
            frame[toe] = joint(toe_turn, place(toe, &rotations, &positions, rest));
        }
    }
    Ok(())
}
