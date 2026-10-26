//! Closing a character's fists round the paraglider's handles. Each arm is bent so its fist closes round its handle,
//! the elbow bending the way the clip bends it, the fist turned to run along the handle, thumb forward; then each
//! finger curls onto the handle. It works on the pose the animation has just written, in the body's frame, before
//! that pose is carried to the screen, so the hands never trail the paraglider by a frame. It reads only bones every
//! character has.

use bevy::math::Affine3A;
use bevy::prelude::*;
use hakuba_characters::Arm;

/// How thick the palm is under the knuckles, and the fingers' skin round their bones, in metres, for a character the
/// size of the paraglider's holder.
const PALM_M: f32 = 0.012;
const SKIN_M: f32 = 0.009;

/// How far the last finger bone reaches past its joint, as a share of the bone before it.
const FINGERTIP: f32 = 0.8;

/// The most a finger joint bends from the clip's pose to meet the handle.
const MOST_CURL_DEG: f32 = 60.0;

/// A handle in the body's frame: the stretch of tube a fist closes round, and the tube's radius.
pub(crate) struct Bar {
    pub from: Vec3,
    pub to: Vec3,
    pub radius: f32,
}

impl Bar {
    /// The point of the stretch nearest `point`.
    fn nearest(&self, point: Vec3) -> Vec3 {
        let span = self.to - self.from;
        self.from + span * ((point - self.from).dot(span) / span.length_squared()).clamp(0.0, 1.0)
    }
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

/// Bends `arm` so its fist closes round `handle`, `weight` of the way from the clip's pose (0 leaves the clip's).
/// `forward` is the body's front, the way the thumb points along the handle, and `size` the character's size as a
/// share of the paraglider's holder's.
pub(crate) fn close(arm: &Arm, body: Entity, handle: &Bar, forward: Vec3, size: f32, weight: f32, nodes: &mut Nodes) {
    if weight <= 0.0 {
        return;
    }
    let place = |node: Entity| in_body(node, body, nodes);
    let (Some(shoulder), Some(elbow), Some(wrist)) = (place(arm.upper_arm), place(arm.forearm), place(arm.hand)) else {
        return;
    };
    let Some(knuckles) = arm
        .fingers
        .iter()
        .map(|finger| place(finger[0]).map(|k| Vec3::from(k.translation)))
        .collect::<Option<Vec<_>>>()
    else {
        return;
    };
    let Some(ends) = arm
        .fingers
        .iter()
        .map(|finger| place(finger[2]).map(|k| Vec3::from(k.translation)))
        .collect::<Option<Vec<_>>>()
    else {
        return;
    };
    let (s, e, w) = (Vec3::from(shoulder.translation), Vec3::from(elbow.translation), Vec3::from(wrist.translation));
    let hand_turn = turn_of(&wrist);

    // Where the fist closes: in front of the knuckles, on the side the fingers curl to, by the handle's radius and the
    // palm's thickness. The knuckles stay put as the fingers curl, so the handle does too. The fist's axis runs along
    // the knuckles toward the thumb.
    let middle = knuckles.iter().sum::<Vec3>() / 4.0;
    let thumbward = (knuckles[0] - knuckles[3]).normalize_or_zero();
    let mut palm = (middle - w).cross(thumbward).normalize_or_zero();
    if palm.dot(ends.iter().sum::<Vec3>() / 4.0 - middle) < 0.0 {
        palm = -palm;
    }
    let cavity = middle + palm * (handle.radius + PALM_M * size);

    // The fist turned so its axis runs along the handle, thumb forward, and rolled about the handle so the wrist lies
    // between it and the elbow; the wrist then goes where that puts the cavity on the handle.
    let mut along = (handle.to - handle.from).normalize_or_zero();
    if along.dot(forward) < 0.0 {
        along = -along;
    }
    let on_handle = handle.nearest(cavity);
    let reach = cavity - w;
    let onto = Quat::from_rotation_arc(thumbward, along);
    let turned = onto * across(reach, thumbward).normalize_or_zero();
    let want = across(on_handle - e, along).normalize_or_zero();
    let roll = Quat::from_axis_angle(along, turned.cross(want).dot(along).atan2(turned.dot(want)));
    let fist_turn = hand_turn.slerp(roll * onto * hand_turn, weight);
    let target = w.lerp(on_handle - (roll * onto) * reach, weight);

    // Two bones from the shoulder to the wrist, the elbow bending toward where the clip has it.
    let (upper, lower) = ((e - s).length(), (w - e).length());
    let to_target = target - s;
    let reach_m = to_target.length().clamp((upper - lower).abs() + 1e-4, upper + lower - 1e-4);
    let toward = to_target.normalize_or_zero();
    let pole = across(e - s, toward).try_normalize().unwrap_or_else(|| toward.any_orthonormal_vector());
    let cos = ((upper * upper + reach_m * reach_m - lower * lower) / (2.0 * upper * reach_m)).clamp(-1.0, 1.0);
    let new_elbow = s + toward * upper * cos + pole * upper * (1.0 - cos * cos).sqrt();
    let new_wrist = s + toward * reach_m;
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
    let surface = handle.radius + SKIN_M * size;
    for finger in &arm.fingers {
        let Some(mut locals) =
            finger.iter().map(|bone| nodes.get(*bone).ok().map(|(t, _)| *t)).collect::<Option<Vec<_>>>()
        else {
            continue;
        };
        for joint in 0..3 {
            let mut parent = hand;
            for local in &locals[..joint] {
                parent *= local.compute_affine();
            }
            let at = parent * locals[joint].compute_affine();
            let next = if joint < 2 {
                at.transform_point3(locals[joint + 1].translation)
            } else {
                at.transform_point3(locals[2].translation * FINGERTIP)
            };
            let p = Vec3::from(at.translation);
            let (bone, axis) = (across(next - p, along), across(on_handle - p, along));
            let (length, distance) = (bone.length(), axis.length());
            if length < 1e-5 || distance < 1e-5 {
                continue;
            }
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
        for (bone, local) in finger.iter().zip(&locals) {
            set_rotation(nodes, *bone, local.rotation);
        }
    }
}

fn set_rotation(nodes: &mut Nodes, node: Entity, rotation: Quat) {
    if let Ok((mut transform, _)) = nodes.get_mut(node) {
        transform.rotation = rotation.normalize();
    }
}
