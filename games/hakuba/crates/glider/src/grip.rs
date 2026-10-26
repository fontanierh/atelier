//! Putting a character's hand on a handle exactly as the paraglider's holder held it. The holder's palm frame, from its
//! export, is the truth: the hand is turned so its own palm frame (the same definition, from its own bones) matches it,
//! the arm bends with two bones so the wrist lands at its origin, the elbow bending toward where the clip has it, and
//! then each finger but the thumb curls until it lies on the handle's tube. It works on the pose the animation has just
//! written, in the body's frame, before that pose is carried to the screen, so the hands never trail the paraglider by
//! a frame. It reads only bones every character has.

use bevy::math::Affine3A;
use bevy::prelude::*;
use hakuba_characters::Arm;

/// The fingers' skin round their bones, in metres, for a character the size of the paraglider's holder.
const SKIN_M: f32 = 0.009;

/// How far the last finger bone reaches past its joint, as a share of the bone before it.
const FINGERTIP: f32 = 0.8;

/// The most a finger joint bends from the clip's pose to meet the handle.
const MOST_CURL_DEG: f32 = 60.0;

/// A handle in the body's frame: the stretch of tube a fist closes round, and the tube's radius.
pub(crate) struct Handle {
    pub from: Vec3,
    pub to: Vec3,
    pub radius: f32,
}

impl Handle {
    /// The point of the stretch nearest `point`.
    fn nearest(&self, point: Vec3) -> Vec3 {
        let span = self.to - self.from;
        self.from + span * ((point - self.from).dot(span) / span.length_squared()).clamp(0.0, 1.0)
    }
}

/// A palm's frame in the body's frame: its origin at the wrist, its Y axis from the wrist toward the knuckles, its Z
/// axis from the index finger's knuckle toward the little finger's.
pub(crate) struct Palm {
    pub wrist: Vec3,
    pub rotation: Quat,
}

/// How far a closed hand is from where the holder's was: the middle of the space its fingers close round from the
/// handle's axis, and its wrist from the holder's, in metres, and its palm's turn from the holder's, in degrees.
pub(crate) struct Fit {
    pub cavity_off_m: f32,
    pub wrist_off_m: f32,
    pub palm_off_deg: f32,
}

/// The nodes of a character's model, each with its place relative to its parent.
pub(crate) type Nodes<'w, 's> = Query<'w, 's, (&'static mut Transform, &'static ChildOf)>;

/// Where `node` is in the frame of `body`, one of its ancestors, from the transforms as they are now.
pub(crate) fn in_body(node: Entity, body: Entity, nodes: &Nodes) -> Option<Affine3A> {
    let mut place = Affine3A::IDENTITY;
    let mut node = node;
    while node != body {
        let (transform, parent) = nodes.get(node).ok()?;
        place = transform.compute_affine() * place;
        node = parent.parent();
    }
    Some(place)
}

/// The rotation of a place, without its scale.
fn turn_of(place: &Affine3A) -> Quat {
    place.to_scale_rotation_translation().1
}

/// `vector` without its part along `axis`, a unit vector.
fn across(vector: Vec3, axis: Vec3) -> Vec3 {
    vector - axis * vector.dot(axis)
}

/// The palm's rotation from the wrist and the index and little fingers' knuckles, as the exporter's `pose::palm`.
fn palm_turn(wrist: Vec3, index: Vec3, pinky: Vec3) -> Quat {
    let y = ((index + pinky) * 0.5 - wrist).normalize();
    let z = across(pinky - index, y).normalize();
    Quat::from_mat3(&Mat3::from_cols(y.cross(z), y, z)).normalize()
}

/// Puts `arm`'s hand on `handle` as `palm` says, `weight` of the way from the clip's pose (0 leaves the clip's), and
/// curls its fingers onto the handle. `size` is the character's size as a share of the holder's. Returns how far the
/// closed hand is from the holder's, or `None` if a bone is missing.
pub(crate) fn close(
    arm: &Arm,
    body: Entity,
    handle: &Handle,
    palm: &Palm,
    size: f32,
    weight: f32,
    nodes: &mut Nodes,
) -> Option<Fit> {
    if weight <= 0.0 {
        return None;
    }
    let place = |node: Entity| in_body(node, body, nodes);
    let (shoulder, elbow, wrist) = (place(arm.upper_arm)?, place(arm.forearm)?, place(arm.hand)?);
    let (index, pinky) = (place(arm.fingers[0][0])?, place(arm.fingers[3][0])?);
    let (s, e, w) = (Vec3::from(shoulder.translation), Vec3::from(elbow.translation), Vec3::from(wrist.translation));

    // The hand turned so its palm's frame is the holder's: the palm's frame is fixed in the hand's, so the hand turns
    // by the turn from its palm's frame now to the holder's.
    let hand_turn = turn_of(&wrist);
    let palm_now = palm_turn(w, Vec3::from(index.translation), Vec3::from(pinky.translation));
    let fist_turn = hand_turn.slerp(palm.rotation * palm_now.inverse() * hand_turn, weight);
    let target = w.lerp(palm.wrist, weight);

    // Two bones from the shoulder to the wrist, the elbow bending toward where the clip has it.
    let (upper, lower) = ((e - s).length(), (w - e).length());
    let to_target = target - s;
    let reach = to_target.length().clamp((upper - lower).abs() + 1e-4, upper + lower - 1e-4);
    let toward = to_target.normalize_or_zero();
    let pole = across(e - s, toward).try_normalize().unwrap_or_else(|| toward.any_orthonormal_vector());
    let cos = ((upper * upper + reach * reach - lower * lower) / (2.0 * upper * reach)).clamp(-1.0, 1.0);
    let new_elbow = s + toward * upper * cos + pole * upper * (1.0 - cos * cos).sqrt();
    let new_wrist = s + toward * reach;
    let swing_upper = Quat::from_rotation_arc((e - s).normalize(), (new_elbow - s).normalize());
    let swing_lower = Quat::from_rotation_arc((swing_upper * (w - e)).normalize(), (new_wrist - new_elbow).normalize());
    let upper_turn = swing_upper * turn_of(&shoulder);
    let forearm_turn = swing_lower * upper_turn * turn_of(&shoulder).inverse() * turn_of(&elbow);
    let parent_turn =
        turn_of(&shoulder) * nodes.get(arm.upper_arm).map_or(Quat::IDENTITY, |(t, _)| t.rotation).inverse();
    set_rotation(nodes, arm.upper_arm, parent_turn.inverse() * upper_turn);
    set_rotation(nodes, arm.forearm, upper_turn.inverse() * forearm_turn);
    set_rotation(nodes, arm.hand, forearm_turn.inverse() * fist_turn);

    // Each finger's three joints, from the knuckle out, bent about the handle's axis until the segment beyond reaches
    // the handle's surface, the skin's width off it.
    let hand = Affine3A::from_scale_rotation_translation(wrist.to_scale_rotation_translation().0, fist_turn, new_wrist);
    let along = (handle.to - handle.from).normalize_or_zero();
    let surface = handle.radius + SKIN_M * size;
    let mut joints = Vec::with_capacity(12);
    for finger in &arm.fingers {
        let mut locals = finger.map(|bone| nodes.get(bone).map_or(Transform::IDENTITY, |(t, _)| *t));
        let mut parent = hand;
        for joint in 0..3 {
            let at = parent * locals[joint].compute_affine();
            let next = if joint < 2 {
                at.transform_point3(locals[joint + 1].translation)
            } else {
                at.transform_point3(locals[2].translation * FINGERTIP)
            };
            let p = Vec3::from(at.translation);
            let (bone, axis) = (across(next - p, along), across(handle.from - p, along));
            let (length, distance) = (bone.length(), axis.length());
            if length > 1e-5 && distance > 1e-5 {
                // The turn about the handle's axis from the bone to the handle's centre now, and the one the bone must
                // keep from it to end on the surface; of the two bends that do, the smaller.
                let now = bone.cross(axis).dot(along).atan2(bone.dot(axis));
                let keep = ((length * length + distance * distance - surface * surface) / (2.0 * length * distance))
                    .clamp(-1.0, 1.0)
                    .acos();
                let bend = [now - keep, now + keep].into_iter().min_by(|a, b| a.abs().total_cmp(&b.abs())).unwrap();
                let most = MOST_CURL_DEG.to_radians();
                let bend = bend.clamp(-most, most) * weight;
                let parent_turn = turn_of(&parent);
                locals[joint].rotation =
                    parent_turn.inverse() * Quat::from_axis_angle(along, bend) * parent_turn * locals[joint].rotation;
            }
            joints.push(p);
            parent *= locals[joint].compute_affine();
        }
        for (bone, local) in finger.iter().zip(&locals) {
            set_rotation(nodes, *bone, local.rotation);
        }
    }

    // How far the closed hand is from the holder's.
    let palm_then = palm_turn(new_wrist, joints[0], joints[9]);
    let cavity = cavity(new_wrist, palm_then, &joints);
    Some(Fit {
        cavity_off_m: cavity.distance(handle.nearest(cavity)),
        wrist_off_m: new_wrist.distance(palm.wrist),
        palm_off_deg: palm_then.angle_between(palm.rotation).to_degrees(),
    })
}

/// The middle of the space a fist closes round: the centre of the circle its fingers' joints lie on, seen along the
/// knuckles (the palm's Z axis), halfway along them. `palm` is the palm's rotation and `wrist` its origin.
fn cavity(wrist: Vec3, palm: Quat, joints: &[Vec3]) -> Vec3 {
    let (x, y, z) = (palm * Vec3::X, palm * Vec3::Y, palm * Vec3::Z);
    // The circle u² + v² + a u + b v + c = 0 nearest the joints' (u, v), by least squares.
    let (mut normal, mut right) = (Mat3::ZERO, Vec3::ZERO);
    let mut along = 0.0;
    for joint in joints {
        let from = *joint - wrist;
        let (u, v) = (from.dot(x), from.dot(y));
        let row = Vec3::new(u, v, 1.0);
        normal += Mat3::from_cols(row * u, row * v, row);
        right -= row * (u * u + v * v);
        along += from.dot(z);
    }
    let [a, b, _] = (normal.inverse() * right).to_array();
    wrist + x * (-a / 2.0) + y * (-b / 2.0) + z * (along / joints.len() as f32)
}

fn set_rotation(nodes: &mut Nodes, node: Entity, rotation: Quat) {
    if let Ok((mut transform, _)) = nodes.get_mut(node) {
        transform.rotation = rotation.normalize();
    }
}
