//! Poses in world space, and the rotation maths the retarget and pose editing share.

use anyhow::Result;
use glam::{DMat3, DMat4, DQuat, DVec3};

use crate::glb::Glb;
use crate::rig::{self, Bones, RIG};

/// The world's up.
pub const UP: DVec3 = DVec3::Y;

/// One bone in world space: its rotation and its position.
#[derive(Clone, Copy)]
pub struct Joint {
    pub rotation: DMat3,
    pub position: DVec3,
}

impl Joint {
    /// The rotation and position of a world matrix, without its scale.
    pub fn of(world: DMat4) -> Self {
        let (_, rotation, position) = world.to_scale_rotation_translation();
        Self { rotation: DMat3::from_quat(rotation), position }
    }
}

/// A pose of the rig's bones, indexed as [`crate::rig::RIG`]: `None` for a bone the skeleton does not have.
pub type Pose = Vec<Option<Joint>>;

/// Bone `i`'s position: its parent's in `pose`, plus its rest offset from the parent turned with the parent.
pub fn place(i: usize, pose: &Pose, rest: &Pose) -> DVec3 {
    let parent = rig::parent(i).expect("only the pelvis has no parent");
    let (bone_rest, parent_rest, parent_now) = (rest[i].unwrap(), rest[parent].unwrap(), pose[parent].unwrap());
    parent_now.position
        + parent_now.rotation * parent_rest.rotation.transpose() * (bone_rest.position - parent_rest.position)
}

/// The rotation whose Y axis is `y` and whose Z axis is `z`, made perpendicular to it.
pub fn frame(y: DVec3, z: DVec3) -> DMat3 {
    let y = y.normalize();
    let z = (z - y * z.dot(y)).normalize();
    DMat3::from_cols(y.cross(z), y, z)
}

/// The frame of the palm on `side` (`"l"` or `"r"`) in `pose`: its Y axis from the wrist toward the knuckles, its Z
/// axis from the index finger's knuckle toward the little finger's. None for a hand without those fingers.
pub fn palm(pose: &Pose, side: &str) -> Option<DMat3> {
    let at = |part: &str| pose[rig::index(&format!("{part}_{side}"))].map(|joint| joint.position);
    let (index, pinky, hand) = (at("index_1")?, at("pinky_1")?, at("hand")?);
    Some(frame((index + pinky) * 0.5 - hand, pinky - index))
}

/// The rotation whose Y axis is `direction` and whose X axis is perpendicular to it and to `hinge`.
pub fn hinge_frame(direction: DVec3, hinge: DVec3) -> DMat3 {
    let y = direction.normalize();
    let x = y.cross(hinge).normalize();
    DMat3::from_cols(x, y, x.cross(y).normalize())
}

/// The shortest rotation taking direction `a` onto direction `b`.
pub fn swing(a: DVec3, b: DVec3) -> DMat3 {
    DMat3::from_quat(DQuat::from_rotation_arc(a.normalize(), b.normalize()))
}

/// The rotation by `degrees` about `axis`, counter-clockwise looking down the axis.
pub fn turn(axis: DVec3, degrees: f64) -> DMat3 {
    DMat3::from_axis_angle(axis.normalize(), degrees.to_radians())
}

/// The rotation halfway from `a` to `b`.
pub fn halfway(a: DMat3, b: DMat3) -> DMat3 {
    DMat3::from_quat(DQuat::from_mat3(&a).slerp(DQuat::from_mat3(&b), 0.5))
}

/// 0 below `low`, 1 above `high`, and a smooth step between.
pub fn smoothstep(low: f64, high: f64, value: f64) -> f64 {
    let t = ((value - low) / (high - low)).clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}

/// `vector` without its up component.
pub fn level(vector: DVec3) -> DVec3 {
    DVec3::new(vector.x, 0.0, vector.z)
}

/// The node that plays each rig bone, by [`crate::rig::RIG`] index.
pub fn rig_nodes(glb: &Glb, bones: &Bones) -> Result<Vec<Option<usize>>> {
    let mut nodes = vec![None; RIG.len()];
    for (rig_bone, name) in bones.pairs() {
        nodes[rig_bone] = Some(glb.node(name)?);
    }
    Ok(nodes)
}

/// The rig bones' joints, from every node's world matrix.
pub fn rig_pose(worlds: &[DMat4], nodes: &[Option<usize>]) -> Pose {
    nodes.iter().map(|node| node.map(|node| Joint::of(worlds[node]))).collect()
}

/// The rig's rest pose.
pub fn rig_rest() -> Pose {
    RIG.iter().map(|bone| Some(Joint { rotation: DMat3::IDENTITY, position: DVec3::from_array(bone.rest) })).collect()
}
