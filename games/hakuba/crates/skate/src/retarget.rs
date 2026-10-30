//! Reference-pose retargeting. Source model-space turns are fitted to each character's own bind axes.
//! The world reflection exchanges anatomical sides, so the binding explicitly pairs opposite source sides.
//! Limbs retain their authored lengths; feet and near-deck hands are solved from this same shown frame.
use super::frame;
use bevy::prelude::*;
use hakuba_characters::{Rig, SolvedPose};
use serde::Deserialize;

const MAP: &[(&str, &str, Option<&str>)] = &[
    ("pelvis", "HIPS", Some("SPINE")),
    ("spine", "SPINE", Some("SPINE1")),
    ("spine_mid", "SPINE1", Some("SPINE3")),
    ("chest", "SPINE3", Some("NECK")),
    ("neck", "NECK", Some("HEAD")),
    ("head", "HEAD", None),
    ("clavicle_l", "RIGHTSHOULDER", Some("RIGHTARM")),
    ("upper_arm_l", "RIGHTARM", Some("RIGHTFOREARM")),
    ("forearm_l", "RIGHTFOREARM", Some("RIGHTHAND")),
    ("hand_l", "RIGHTHAND", None),
    ("clavicle_r", "LEFTSHOULDER", Some("LEFTARM")),
    ("upper_arm_r", "LEFTARM", Some("LEFTFOREARM")),
    ("forearm_r", "LEFTFOREARM", Some("LEFTHAND")),
    ("hand_r", "LEFTHAND", None),
    ("thigh_l", "RIGHTUPLEG", Some("RIGHTLEG")),
    ("shin_l", "RIGHTLEG", Some("RIGHTFOOT")),
    ("foot_l", "RIGHTFOOT", Some("RIGHTTOEBASE")),
    ("toe_l", "RIGHTTOEBASE", None),
    ("thigh_r", "LEFTUPLEG", Some("LEFTLEG")),
    ("shin_r", "LEFTLEG", Some("LEFTFOOT")),
    ("foot_r", "LEFTFOOT", Some("LEFTTOEBASE")),
    ("toe_r", "LEFTTOEBASE", None),
];

#[derive(Clone, Deserialize)]
pub struct DeckProfile {
    pub length_m: f32,
    pub width_m: f32,
    pub thickness_m: f32,
    pub concave_m: f32,
    pub kick_start_m: f32,
    pub kick_rise_m: f32,
    pub kick_angle_deg: f32,
}

pub struct Retarget {
    source: Vec<usize>,
    fit: Vec<Quat>,
    rest: Vec<Transform>,
    ratio: f32,
    sole: f32,
    deck: usize,
    attachments: [usize; 4],
}

impl Retarget {
    pub fn bind(rig: &Rig, names: &[String], reference: &[Mat4]) -> Result<Self, String> {
        let index =
            |name: &str| names.iter().position(|n| n == name).ok_or_else(|| format!("Missing source bone {name}"));
        let hip = index("HIPS")?;
        let foot = index("RIGHTFOOT")?;
        let target_hip = rig.index("pelvis").ok_or("Missing target pelvis")?;
        let target_foot = rig.index("foot_l").ok_or("Missing target foot_l")?;
        let rest: Vec<_> = reference.iter().map(|m| rigid_rotation(frame::world_transform(*m))).collect();
        let target: Vec<_> = rig.bones.iter().map(|b| Transform::from_matrix(Mat4::from(b.body_rest))).collect();
        let ratio = (target[target_hip].translation.y - target[target_foot].translation.y)
            / (rest[hip].translation.y - rest[foot].translation.y);
        if !ratio.is_finite() || ratio <= 0. {
            return Err("Invalid source/target leg lengths".into());
        }
        let sole = target[target_foot].translation.y - rest[foot].translation.y * ratio;
        let h = index("HEAD")?;
        let up = (rest[h].translation - rest[hip].translation).normalize();
        let toe = index("RIGHTTOEBASE")?;
        let ahead = rest[toe].translation - rest[foot].translation;
        let front = (ahead - up * up.dot(ahead)).normalize();
        let right = up.cross(front).normalize();
        let base = Quat::from_mat3(&Mat3::from_cols(right, front.cross(right).normalize(), front));
        let mut source = vec![usize::MAX; rig.bones.len()];
        let mut fit = vec![base; rig.bones.len()];
        for (i, bone) in rig.bones.iter().enumerate() {
            let Some((_, name, child)) = MAP.iter().find(|(target, _, _)| *target == bone.name) else { continue };
            let s = index(name)?;
            source[i] = s;
            let mut rotation = bone.parent.map_or(base, |p| fit[p]);
            if let Some(child) = child {
                let c = index(child)?;
                let target_child = MAP.iter().find(|(_, n, _)| n == child).and_then(|(n, _, _)| rig.index(n));
                if let Some(target_child) = target_child {
                    let mut a = base * (target[target_child].translation - target[i].translation);
                    let mut b = rest[c].translation - rest[s].translation;
                    if bone.name.starts_with("foot_") {
                        a.y = 0.;
                        b.y = 0.;
                    }
                    if a.length_squared() > 1e-8 && b.length_squared() > 1e-8 {
                        rotation = Quat::from_rotation_arc(a.normalize(), b.normalize()) * base;
                    }
                }
            } else if bone.name == "head" {
                rotation = base;
            }
            fit[i] = rotation;
        }
        Ok(Self {
            source,
            fit,
            rest,
            ratio,
            sole,
            deck: index("SKATEBOARD_ROOT")?,
            attachments: [
                index("RIGHTTOEBASE_REPARENTED")?,
                index("LEFTTOEBASE_REPARENTED")?,
                index("RIGHTHAND_REPARENTED")?,
                index("LEFTHAND_REPARENTED")?,
            ],
        })
    }

    pub fn solve(&self, rig: &Rig, source: &[Mat4], grip: Option<&DeckProfile>, board_blends: [f32; 4]) -> SolvedPose {
        let shown: Vec<_> = source.iter().map(|m| rigid_rotation(frame::world_transform(*m))).collect();
        let mut output: Vec<Transform> = Vec::with_capacity(rig.bones.len());
        let mut goals = vec![Vec3::ZERO; rig.bones.len()];
        for (i, bone) in rig.bones.iter().enumerate() {
            let bind = Transform::from_matrix(Mat4::from(bone.body_rest));
            let mut at = if self.source[i] != usize::MAX {
                let s = self.source[i];
                let turn = shown[s].rotation * self.rest[s].rotation.inverse() * self.fit[i];
                let pos = shown[s].translation * self.ratio + Vec3::Y * self.sole;
                Transform { translation: pos, rotation: (turn * bind.rotation).normalize(), scale: bind.scale }
            } else if let Some(parent) = bone.parent {
                Transform::from_matrix(output[parent].to_matrix() * bone.rest.to_matrix())
            } else {
                Transform::from_matrix(Mat4::from(bone.body_rest))
            };
            goals[i] = at.translation;
            if let Some(parent) = bone.parent {
                at.translation = output[parent].transform_point(bone.rest.translation);
            }
            output.push(at);
        }
        let deck = shown[self.deck];
        let mut contacts = [None; 2];
        for (side_index, side) in ["l", "r"].into_iter().enumerate() {
            // The reflection exchanges sides; the native order is LF, RF, LH, RH.
            let native = 1 - side_index;
            if let (Some(foot), Some(toe)) = (rig.index(&format!("foot_{side}")), rig.index(&format!("toe_{side}"))) {
                let source_toe = self.source[toe];
                let weight = board_blends[native].clamp(0., 1.);
                if source_toe != usize::MAX && weight > 0. {
                    // Final physical toes include native post-IK. Preserve their support plane, not a scaled board.
                    let ankle = foot_goal(rig, toe, &output[foot], &shown[source_toe], &self.rest[source_toe]);
                    goals[foot] = goals[foot].lerp(ankle, weight);
                }
            }
            if let (Some(profile), Some(hand)) = (grip, rig.index(&format!("hand_{side}"))) {
                let weight = board_blends[2 + native].clamp(0., 1.);
                if weight > 0. {
                    // The board-parented helper carries the authored grip location; the final wrist carries its physical correction.
                    let helper = shown[self.attachments[2 + side_index]].translation;
                    let wrist = shown[self.source[hand]].translation;
                    let authored = deck.to_matrix().inverse().transform_point3(helper);
                    let physical = deck.to_matrix().inverse().transform_point3(wrist);
                    let contact = profile.contact(Vec3::new(authored.x, physical.y, authored.z));
                    if let Some((rotation, goal)) = grip_hand(rig, &output, hand, side, &deck, contact) {
                        output[hand].rotation = output[hand].rotation.slerp(rotation, weight);
                        goals[hand] = goals[hand].lerp(goal, weight);
                        contacts[side_index] = Some((contact, weight));
                    }
                }
            }
        }
        // Fit the torso to a reachable grip without changing any segment length or moving the feet's goals.
        let mut lower = 0.0_f32;
        for (side_index, side) in ["l", "r"].into_iter().enumerate() {
            if contacts[side_index].is_none() {
                continue;
            }
            if let (Some(a), Some(b), Some(c)) = (
                rig.index(&format!("upper_arm_{side}")),
                rig.index(&format!("forearm_{side}")),
                rig.index(&format!("hand_{side}")),
            ) {
                let reach = output[a].translation.distance(output[b].translation)
                    + output[b].translation.distance(output[c].translation);
                let delta = output[a].translation - goals[c];
                if delta.y > 0. {
                    let vertical = (reach * reach - delta.with_y(0.).length_squared()).max(0.).sqrt();
                    lower = lower.max((delta.y - vertical).max(0.));
                }
            }
        }
        if lower > 0. {
            for bone in &mut output {
                bone.translation.y -= lower;
            }
        }
        for side in ["l", "r"] {
            if let (Some(a), Some(b), Some(c)) = (
                rig.index(&format!("thigh_{side}")),
                rig.index(&format!("shin_{side}")),
                rig.index(&format!("foot_{side}")),
            ) {
                let pole = goals[b] + (goals[b] - (goals[a] + goals[c]) * 0.5) * 2.;
                limb(&mut output, a, b, c, goals[c], pole);
                if let Some(toe) = rig.index(&format!("toe_{side}")) {
                    let turn = output[toe].rotation;
                    output[toe] = Transform::from_matrix(output[c].to_matrix() * rig.bones[toe].rest.to_matrix());
                    output[toe].rotation = turn;
                }
            }
        }
        for side in ["l", "r"] {
            if let (Some(a), Some(b), Some(c)) = (
                rig.index(&format!("upper_arm_{side}")),
                rig.index(&format!("forearm_{side}")),
                rig.index(&format!("hand_{side}")),
            ) {
                limb(&mut output, a, b, c, goals[c], goals[b]);
            }
        }
        // Fingers are not present in the source rig. Their authored lengths and palm shape belong to the target.
        for i in 0..rig.bones.len() {
            if self.source[i] == usize::MAX
                && let Some(parent) = rig.bones[i].parent
            {
                output[i] = Transform::from_matrix(output[parent].to_matrix() * rig.bones[i].rest.to_matrix());
            }
        }
        for (side_index, side) in ["l", "r"].into_iter().enumerate() {
            if let Some((contact, weight)) = contacts[side_index] {
                close_fingers(rig, &mut output, side, &deck, contact, weight);
            }
        }
        SolvedPose(
            rig.bones
                .iter()
                .enumerate()
                .map(|(i, bone)| {
                    let parent = bone.parent.map_or(Mat4::from(bone.root_parent), |p| output[p].to_matrix());
                    Transform::from_matrix(parent.inverse() * output[i].to_matrix())
                })
                .collect(),
        )
    }
}

fn rigid_rotation(mut transform: Transform) -> Transform {
    transform.rotation = transform.rotation.normalize();
    transform
}

fn foot_goal(rig: &Rig, toe: usize, ankle: &Transform, source_toe: &Transform, reference_toe: &Transform) -> Vec3 {
    let source_up = source_toe.rotation * reference_toe.rotation.inverse() * Vec3::Y;
    let clearance = rig.bones[toe].body_rest.translation.y - reference_toe.translation.y;
    let target_toe = ankle.rotation * (ankle.scale * rig.bones[toe].rest.translation);
    source_toe.translation + source_up * clearance - target_toe
}

/// Analytic two-bone solve, keeping bind segment lengths and the end's requested rotation.
fn limb(pose: &mut [Transform], a: usize, b: usize, c: usize, goal: Vec3, pole: Vec3) {
    let origin = pose[a].translation;
    let ab = pose[b].translation - origin;
    let bc = pose[c].translation - pose[b].translation;
    let l1 = ab.length();
    let l2 = bc.length();
    let delta = goal - origin;
    if l1 < 1e-5 || l2 < 1e-5 || delta.length_squared() < 1e-8 {
        return;
    }
    let axis = delta.normalize();
    let distance = delta.length().clamp((l1 - l2).abs() + 1e-5, l1 + l2 - 1e-5);
    let side = (pole - origin - axis * axis.dot(pole - origin)).normalize_or_zero();
    let side = if side.length_squared() < 0.5 { axis.any_orthonormal_vector() } else { side };
    let along = (l1 * l1 + distance * distance - l2 * l2) / (2. * distance);
    let elbow = origin + axis * along + side * (l1 * l1 - along * along).max(0.).sqrt();
    let end = origin + axis * distance;
    pose[a].rotation =
        (Quat::from_rotation_arc(ab.normalize(), (elbow - origin).normalize()) * pose[a].rotation).normalize();
    pose[b].rotation =
        (Quat::from_rotation_arc(bc.normalize(), (end - elbow).normalize()) * pose[b].rotation).normalize();
    pose[b].translation = elbow;
    pose[c].translation = end;
}

#[derive(Clone, Copy)]
struct DeckContact {
    top: Vec3,
    bottom: Vec3,
    outward: Vec3,
    normal: Vec3,
    tangent: Vec3,
}

impl DeckProfile {
    fn top(&self, x: f32, z: f32) -> (f32, f32) {
        let angle = self.kick_angle_deg.to_radians();
        let run = self.length_m * 0.5 - self.kick_start_m;
        let radius = (run * angle.tan() - self.kick_rise_m) / (angle.sin() * angle.tan() - (1. - angle.cos()));
        let beyond = (x.abs() - self.kick_start_m).max(0.);
        let (kick, slope) = if beyond <= 0. {
            (0., 0.)
        } else if beyond <= radius * angle.sin() {
            let bend = (beyond / radius).asin();
            (radius * (1. - bend.cos()), bend)
        } else {
            (radius * (1. - angle.cos()) + (beyond - radius * angle.sin()) * angle.tan(), angle)
        };
        let fade = 1. - 0.5 * (beyond / run).clamp(0., 1.);
        (kick + self.concave_m * (z / (self.width_m * 0.5)).powi(2) * fade, slope * x.signum())
    }

    fn contact(&self, target: Vec3) -> DeckContact {
        let radius = self.width_m * 0.5;
        let flat_end = self.length_m * 0.5 - radius;
        let center = Vec3::new(target.x.clamp(-flat_end, flat_end), 0., 0.);
        let radial = Vec3::new(target.x - center.x, 0., target.z);
        let outward = if radial.length_squared() > 1e-8 { radial.normalize() } else { Vec3::Z };
        let edge = center + outward * radius;
        let (height, slope) = self.top(edge.x, edge.z);
        let top = Vec3::new(edge.x, height, edge.z);
        let bottom = top + Vec3::new(slope.sin() * self.thickness_m, -slope.cos() * self.thickness_m, 0.);
        let normal = Vec3::new(-slope.sin(), slope.cos(), 0.);
        let outward = (outward - normal * outward.dot(normal)).normalize();
        let tangent = normal.cross(outward).normalize();
        DeckContact { top, bottom, outward, normal, tangent }
    }
}

fn palm_geometry(rig: &Rig, hand: usize, side: &str) -> Option<(Vec3, Vec3)> {
    let first =
        |finger| rig.index(&format!("{finger}_1_{side}")).map(|i| Vec3::from(rig.bones[i].body_rest.translation));
    let knuckles: Option<Vec<_>> = ["index", "middle", "ring", "pinky"].map(first).into_iter().collect();
    let knuckles = knuckles?;
    let wrist = Vec3::from(rig.bones[hand].body_rest.translation);
    let palm = knuckles.iter().copied().sum::<Vec3>() / knuckles.len() as f32 - wrist;
    let across = knuckles[0] - knuckles[3];
    let into_hand = rig.bones[hand].body_rest.matrix3.inverse();
    Some((Vec3::from(into_hand * palm), Vec3::from(into_hand * across)))
}

fn grip_hand(
    rig: &Rig,
    output: &[Transform],
    hand: usize,
    side: &str,
    deck: &Transform,
    contact: DeckContact,
) -> Option<(Quat, Vec3)> {
    let (palm, across) = palm_geometry(rig, hand, side)?;
    let source_forward = (output[hand].scale * palm).normalize();
    let source_across = output[hand].scale * across;
    let source_side = (source_across - source_forward * source_across.dot(source_forward)).normalize();
    let source_basis = Mat3::from_cols(source_side, source_forward, source_side.cross(source_forward));
    let forward = -(deck.rotation * contact.normal);
    let tangent = deck.rotation * contact.tangent;
    // Select the orientation nearest the solved wrist; neither anatomical side is inferred from world axes.
    let target_side = if (output[hand].rotation * source_side).dot(tangent) >= 0. { tangent } else { -tangent };
    let target_basis = Mat3::from_cols(target_side, forward, target_side.cross(forward));
    let rotation = Quat::from_mat3(&(target_basis * source_basis.transpose())).normalize();
    let edge = deck.transform_point((contact.top + contact.bottom) * 0.5);
    let outward = deck.rotation * contact.outward;
    let minimum = ["index", "middle", "ring", "pinky"]
        .into_iter()
        .filter_map(|finger| {
            let bone = rig.index(&format!("{finger}_1_{side}"))?;
            let offset = rig.bones[bone].rest.translation;
            Some((rotation * (output[hand].scale * (offset - palm))).dot(outward))
        })
        .fold(0.0_f32, f32::min);
    let knuckle = edge - outward * minimum;
    let wrist = knuckle - rotation * (output[hand].scale * palm);
    Some((rotation, wrist))
}

/// Close the target's measured phalanges around the exported solid: fingers underneath, thumb above.
fn close_fingers(rig: &Rig, output: &mut [Transform], side: &str, deck: &Transform, contact: DeckContact, weight: f32) {
    let edge_top = deck.transform_point(contact.top);
    let edge_bottom = deck.transform_point(contact.bottom);
    let outward = deck.rotation * contact.outward;
    let normal = deck.rotation * contact.normal;
    let axis = deck.rotation * contact.tangent;
    for finger in ["index", "middle", "ring", "pinky", "thumb"] {
        let ids = [1, 2, 3].map(|joint| rig.index(&format!("{finger}_{joint}_{side}")));
        let [Some(a), Some(b), Some(c)] = ids else { continue };
        let original = [output[a], output[b], output[c]];
        let lower_length = output[c].translation.distance(output[b].translation);
        let upper_length = output[b].translation.distance(output[a].translation);
        let along = axis * (output[a].translation - edge_top).dot(axis);
        let (goal, pole) = if finger == "thumb" {
            (
                edge_top + along - outward * lower_length,
                edge_top + along + outward * upper_length + normal * upper_length,
            )
        } else {
            (
                edge_bottom + along - outward * lower_length,
                edge_bottom + along + outward * upper_length - normal * upper_length,
            )
        };
        limb(output, a, b, c, goal, pole);
        let terminal = if finger == "thumb" { -outward } else { outward };
        let previous = (original[2].translation - original[1].translation).normalize();
        output[c].rotation = Quat::from_rotation_arc(previous, terminal) * original[2].rotation;
        // Blend in local space so every segment keeps its authored length through contact transitions.
        for (i, original) in [a, b, c].into_iter().zip(original) {
            output[i].rotation = original.rotation.slerp(output[i].rotation, weight);
        }
        output[b].translation = output[a].transform_point(rig.bones[b].rest.translation);
        output[c].translation = output[b].transform_point(rig.bones[c].rest.translation);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn limb_preserves_both_lengths_and_reaches_an_asymmetric_goal() {
        let mut p =
            vec![Transform::from_xyz(0., 1., 0.), Transform::from_xyz(0., 0.6, 0.), Transform::from_xyz(0., 0.2, 0.)];
        let goal = Vec3::new(0.2, 0.35, 0.15);
        limb(&mut p, 0, 1, 2, goal, Vec3::new(0., 0.6, 1.));
        assert!((p[1].translation.distance(p[0].translation) - 0.4).abs() < 1e-5);
        assert!((p[2].translation.distance(p[1].translation) - 0.4).abs() < 1e-5);
        assert!(p[2].translation.distance(goal) < 1e-5);
    }

    fn nox() -> Rig {
        use bevy::math::Affine3A;
        use hakuba_characters::Bone;
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../assets/characters/nox/nox.glb");
        let bytes = std::fs::read(path).unwrap();
        let size = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
        let glb: serde_json::Value = serde_json::from_slice(&bytes[20..20 + size]).unwrap();
        let nodes = glb["nodes"].as_array().unwrap();
        let mut parents = vec![None; nodes.len()];
        let mut locals = Vec::new();
        for (i, node) in nodes.iter().enumerate() {
            let values = |key: &str, fallback: &[f32]| {
                node[key]
                    .as_array()
                    .map_or_else(|| fallback.to_vec(), |v| v.iter().map(|x| x.as_f64().unwrap() as f32).collect())
            };
            locals.push(Transform {
                translation: Vec3::from_slice(&values("translation", &[0., 0., 0.])),
                rotation: Quat::from_slice(&values("rotation", &[0., 0., 0., 1.])),
                scale: Vec3::from_slice(&values("scale", &[1., 1., 1.])),
            });
            if let Some(children) = node["children"].as_array() {
                for child in children {
                    parents[child.as_u64().unwrap() as usize] = Some(i);
                }
            }
        }
        let depth = |mut i: usize| {
            let mut depth = 0;
            while let Some(p) = parents[i] {
                depth += 1;
                i = p;
            }
            depth
        };
        let mut selected: Vec<_> = nodes
            .iter()
            .enumerate()
            .filter_map(|(i, n)| {
                let name = n["name"].as_str()?;
                (MAP.iter().any(|(target, _, _)| *target == name)
                    || ["thumb_", "index_", "middle_", "ring_", "pinky_"].iter().any(|p| name.starts_with(p)))
                .then_some((i, name.to_owned()))
            })
            .collect();
        selected.sort_by_key(|(i, name)| (depth(*i), name.clone()));
        let mut bones = Vec::new();
        for (index, name) in &selected {
            let mut body_rest = locals[*index].compute_affine();
            let mut at = parents[*index];
            while let Some(parent) = at {
                body_rest = locals[parent].compute_affine() * body_rest;
                at = parents[parent];
            }
            let parent = parents[*index].and_then(|p| selected.iter().position(|(i, _)| *i == p));
            let root_parent = if parent.is_none() {
                body_rest * locals[*index].compute_affine().inverse()
            } else {
                Affine3A::IDENTITY
            };
            bones.push(Bone {
                name: name.clone(),
                entity: Entity::PLACEHOLDER,
                parent,
                rest: locals[*index],
                body_rest,
                root_parent,
            });
        }
        Rig { bones }
    }

    fn body_pose(rig: &Rig, locals: &SolvedPose) -> Vec<Transform> {
        let mut result: Vec<Transform> = Vec::new();
        for (bone, local) in rig.bones.iter().zip(&locals.0) {
            let parent = bone.parent.map_or(Mat4::from(bone.root_parent), |p| result[p].to_matrix());
            result.push(Transform::from_matrix(parent * local.to_matrix()));
        }
        result
    }

    fn deck_profile() -> DeckProfile {
        DeckProfile {
            length_m: 0.8,
            width_m: 0.205,
            thickness_m: 0.012,
            concave_m: 0.009,
            kick_start_m: 0.27,
            kick_rise_m: 0.045,
            kick_angle_deg: 22.,
        }
    }

    #[test]
    fn nox_palm_keeps_armature_scale_and_fingers_keep_lengths_on_a_tilted_solid() {
        let rig = nox();
        let mut output: Vec<_> = rig.bones.iter().map(|b| Transform::from_matrix(Mat4::from(b.body_rest))).collect();
        let deck =
            Transform::from_xyz(0.2, 0.7, -0.3).with_rotation(Quat::from_rotation_x(0.6) * Quat::from_rotation_z(-0.3));
        let profile = deck_profile();
        let contact = profile.contact(Vec3::new(0.15, 0., 0.1));
        let hand = rig.index("hand_l").unwrap();
        assert!(output[hand].scale.x > 1.6);
        let (rotation, wrist) = grip_hand(&rig, &output, hand, "l", &deck, contact).unwrap();
        output[hand].translation = wrist;
        output[hand].rotation = rotation;
        for i in 0..rig.bones.len() {
            if rig.bones[i].name.ends_with("_l")
                && let Some(p) = rig.bones[i].parent
            {
                if rig.bones[i].name.contains("_1_")
                    || rig.bones[i].name.contains("_2_")
                    || rig.bones[i].name.contains("_3_")
                {
                    output[i] = Transform::from_matrix(output[p].to_matrix() * rig.bones[i].rest.to_matrix());
                }
            }
        }
        let (palm, _) = palm_geometry(&rig, hand, "l").unwrap();
        let knuckle = ["index", "middle", "ring", "pinky"]
            .into_iter()
            .map(|finger| output[rig.index(&format!("{finger}_1_l")).unwrap()].translation)
            .sum::<Vec3>()
            / 4.;
        assert!(output[hand].transform_point(palm).distance(knuckle) < 1e-5);
        for finger in ["index", "middle", "ring", "pinky"] {
            let at = output[rig.index(&format!("{finger}_1_l")).unwrap()].translation;
            let distance = (at - deck.transform_point(contact.top)).dot(deck.rotation * contact.outward);
            assert!(
                distance >= -1e-5,
                "{finger} knuckle rail distance={distance}, hand rotation length={}, scale={:?}",
                output[hand].rotation.length(),
                output[hand].scale
            );
        }
        close_fingers(&rig, &mut output, "l", &deck, contact, 1.);
        for finger in ["index", "middle", "ring", "pinky", "thumb"] {
            let ids = [1, 2, 3].map(|j| rig.index(&format!("{finger}_{j}_l")).unwrap());
            for pair in ids.windows(2) {
                let original = Vec3::from(rig.bones[pair[0]].body_rest.translation)
                    .distance(rig.bones[pair[1]].body_rest.translation.into());
                assert!((output[pair[0]].translation.distance(output[pair[1]].translation) - original).abs() < 1e-5);
            }
            let local_end = deck.to_matrix().inverse().transform_point3(output[ids[2]].translation);
            assert!(local_end.is_finite());
            if finger == "thumb" {
                assert!(
                    (local_end - contact.top).dot(contact.normal) > -0.002,
                    "thumb missed grip tape: {local_end:?}"
                );
            } else {
                assert!(
                    (local_end - contact.bottom).dot(contact.normal) < 0.002,
                    "{finger} missed underside: {local_end:?}"
                );
            }
        }
    }

    #[test]
    fn toe_contact_uses_physical_metres_and_preserves_target_ankle_to_toe_length() {
        let rig = nox();
        let foot = rig.index("foot_l").unwrap();
        let toe = rig.index("toe_l").unwrap();
        let ankle = Transform::from_matrix(Mat4::from(rig.bones[foot].body_rest));
        let reference = Transform::from_xyz(0.1, 0.03, -0.1);
        let turn = Quat::from_rotation_z(0.8);
        let shown = Transform::from_xyz(0.3, 0.5, -0.2).with_rotation(turn);
        let goal = foot_goal(&rig, toe, &ankle, &shown, &reference);
        let toe_offset = ankle.rotation * (ankle.scale * rig.bones[toe].rest.translation);
        let clearance = rig.bones[toe].body_rest.translation.y - reference.translation.y;
        assert!((goal + toe_offset - shown.translation - turn * Vec3::Y * clearance).length() < 1e-5);
        assert!((toe_offset.length() - 0.1459284).abs() < 1e-4);
    }

    #[test]
    fn native_asymmetric_push_retargets_nox_with_complete_finite_locals_and_authored_lengths() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../assets/simulations/skate-simulation/skate-simulation.skatepack");
        let bytes = std::fs::read(path).unwrap();
        let triangles = vec![
            [[-100., 0., -100.], [-100., 0., 100.], [100., 0., -100.]],
            [[100., 0., -100.], [-100., 0., 100.], [100., 0., 100.]],
        ];
        let mut session = crate::Session::from_resources(
            &crate::PreparedResources::from_bytes(bytes).unwrap(),
            triangles,
            vec![129; 2],
            vec![],
            [0., 0.1, 0.],
            0.,
        )
        .unwrap();
        let initial = session.activate([0., 0.1, 0.], 0.).unwrap();
        let rig = nox();
        let retarget = Retarget::bind(&rig, &initial.names, &session.reference_pose().unwrap()).unwrap();
        let mut asymmetric = false;
        let right = initial.names.iter().position(|n| n == "RIGHTFOOT").unwrap();
        let left = initial.names.iter().position(|n| n == "LEFTFOOT").unwrap();
        for tick in 0..90 {
            session
                .tick(crate::Controls { buttons: if tick < 60 { 0x1000 } else { 0 }, ..Default::default() })
                .unwrap();
            let pose = session.pose();
            let left_height = pose.bones[left].w_axis.y;
            let right_height = pose.bones[right].w_axis.y;
            asymmetric |= (left_height - right_height).abs() > 0.02;
            let locals = retarget.solve(&rig, &pose.bones, None, pose.contacts.map(|c| c.board_blend));
            assert_eq!(locals.0.len(), rig.bones.len());
            let body = body_pose(&rig, &locals);
            for (i, bone) in rig.bones.iter().enumerate() {
                assert!(locals.0[i].to_matrix().is_finite());
                if let Some(p) = bone.parent {
                    let expected =
                        Vec3::from(bone.body_rest.translation).distance(rig.bones[p].body_rest.translation.into());
                    assert!(
                        (body[i].translation.distance(body[p].translation) - expected).abs() < 2e-4,
                        "{} changed length tick={tick} actual={} expected={expected} parent_scale={:?} parent_rotation_norm={} local_scale={:?}",
                        bone.name,
                        body[i].translation.distance(body[p].translation),
                        body[p].scale,
                        body[p].rotation.length(),
                        locals.0[i].scale
                    );
                }
            }
            let toe = rig.index("toe_l").unwrap();
            let source = retarget.source[toe];
            assert_eq!(pose.names[source], "RIGHTTOEBASE");
            let expected = frame::world_transform(pose.bones[source]).rotation.normalize()
                * retarget.rest[source].rotation.inverse()
                * retarget.fit[toe]
                * Transform::from_matrix(Mat4::from(rig.bones[toe].body_rest)).rotation;
            assert!(body[toe].rotation.dot(expected).abs() > 0.999);
        }
        assert!(asymmetric, "native push must exercise left/right asymmetry");
    }

    #[test]
    fn reflected_model_binding_keeps_left_roles_on_the_characters_left() {
        // A +Z-facing model's +X left turns to -Z when the world conversion's forward is +X.
        let front = frame::world_point(Vec3::Z);
        let up = Vec3::Y;
        let right = up.cross(front);
        let fit = Quat::from_mat3(&Mat3::from_cols(right, up, front));
        let target_left = fit * Vec3::X;
        let source_right = frame::world_point(Vec3::NEG_X);
        assert!(target_left.dot(source_right) > 0.999);
        assert!((fit * Vec3::Z - front).length() < 1e-5);
        assert!(MAP.iter().any(|(target, source, _)| *target == "foot_l" && *source == "RIGHTFOOT"));
    }
}
