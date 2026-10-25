//! Editing poses: turning bones with everything below them, moving the body, and bending legs to reach a goal. The
//! retarget and every animation's changes share these.

use glam::{DMat3, DVec3};

use crate::pose::{Joint, Pose, hinge_frame, level, place};
use crate::rig::{self, RIG};

/// How far a leg may straighten, as a fraction of its full length: a straight leg has no bend to aim its knee by.
const REACH: f64 = 0.99998;

/// A leg's bones, by rig index.
#[derive(Clone, Copy)]
pub struct Leg {
    pub thigh: usize,
    pub shin: usize,
    pub foot: usize,
    pub toe: usize,
}

impl Leg {
    /// The leg on `side`, `"l"` or `"r"`.
    pub fn on(side: &str) -> Self {
        let bone = |part: &str| rig::index(&format!("{part}_{side}"));
        Self { thigh: bone("thigh"), shin: bone("shin"), foot: bone("foot"), toe: bone("toe") }
    }

    /// The thigh's and the shin's lengths.
    fn lengths(&self, rest: &Pose) -> (f64, f64) {
        let position = |i: usize| rest[i].unwrap().position;
        (position(self.thigh).distance(position(self.shin)), position(self.shin).distance(position(self.foot)))
    }
}

/// `pose` with its pelvis moved by `shift` and each bone in `turns` turned by its rotation, given in the bone's parent
/// frame. Every other bone keeps its turn from its parent, so the bones below a turned one follow it.
pub fn repose(pose: &Pose, rest: &Pose, shift: DVec3, turns: &[(usize, DMat3)]) -> Pose {
    let mut moved = pose.clone();
    for i in 0..RIG.len() {
        let Some(joint) = pose[i] else { continue };
        let Some(parent) = rig::parent(i) else {
            moved[i] = Some(Joint { rotation: joint.rotation, position: joint.position + shift });
            continue;
        };
        let mut local = pose[parent].unwrap().rotation.transpose() * joint.rotation;
        if let Some((_, turn)) = turns.iter().find(|(bone, _)| *bone == i) {
            local = *turn * local;
        }
        let rotation = moved[parent].unwrap().rotation * local;
        moved[i] = Some(Joint { rotation, position: place(i, &moved, rest) });
    }
    moved
}

/// Lowers the whole `pose` as far as the leg that needs it most must go to reach its goal, and no further.
pub fn lower_to_reach(pose: &mut Pose, rest: &Pose, goals: &[(Leg, DVec3)]) {
    let mut drop: f64 = 0.0;
    for (leg, goal) in goals {
        let (upper, lower) = leg.lengths(rest);
        let longest = (upper + lower) * REACH;
        let offset = pose[leg.thigh].unwrap().position - *goal;
        let vertical = (longest * longest - level(offset).length_squared()).max(0.0).sqrt();
        drop = drop.max(offset.y - vertical);
    }
    for joint in pose.iter_mut().flatten() {
        joint.position.y -= drop;
    }
}

/// Bends `leg` so its ankle reaches `goal`, its knee toward `pole`, which must not lie along the line from the hip to
/// the goal. The thigh and shin turn so the knee's hinge follows the bend; the foot keeps its world rotation and the
/// toe its turn from the foot. A goal out of reach is reached as nearly as the leg allows. Returns how far the ankle
/// lands from the goal.
pub fn bend(pose: &mut Pose, rest: &Pose, leg: Leg, goal: DVec3, pole: DVec3) -> f64 {
    let (upper, lower) = leg.lengths(rest);
    let joint = |pose: &Pose, i: usize| pose[i].unwrap();
    let (hip, knee_before) = (joint(pose, leg.thigh).position, joint(pose, leg.shin).position);
    let ankle_before = joint(pose, leg.foot).position;
    let reach = goal - hip;
    let distance = reach.length().clamp((upper - lower).abs() + (upper + lower) * (1.0 - REACH), (upper + lower) * REACH);
    let axis = reach.normalize();
    let pole = (pole - axis * pole.dot(axis)).normalize();
    let along = (upper * upper - lower * lower + distance * distance) / (2.0 * distance);
    let knee = hip + axis * along + pole * (upper * upper - along * along).max(0.0).sqrt();
    let ankle = hip + axis * distance;

    let (new_upper, new_lower) = ((knee - hip).normalize(), (ankle - knee).normalize());
    let (old_upper, old_lower) = ((knee_before - hip).normalize(), (ankle_before - knee_before).normalize());
    let hinge = new_upper.cross(new_lower).normalize();
    // A straight leg has no hinge of its own; it bends about the new one.
    let old_hinge = old_upper.cross(old_lower);
    let old_hinge = if old_hinge.length() > 1e-9 { old_hinge.normalize() } else { hinge };
    let turn = |new: DVec3, old: DVec3| hinge_frame(new, hinge) * hinge_frame(old, old_hinge).transpose();
    let (thigh, shin) = (joint(pose, leg.thigh).rotation, joint(pose, leg.shin).rotation);
    pose[leg.thigh] = Some(Joint { rotation: turn(new_upper, old_upper) * thigh, position: hip });
    pose[leg.shin] = Some(Joint { rotation: turn(new_lower, old_lower) * shin, position: knee });
    for bone in [leg.foot, leg.toe] {
        let rotation = joint(pose, bone).rotation;
        pose[bone] = Some(Joint { rotation, position: place(bone, pose, rest) });
    }
    joint(pose, leg.foot).position.distance(goal)
}
