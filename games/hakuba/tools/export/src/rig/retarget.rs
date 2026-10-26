//! Copies a clip from one skeleton onto another, whose bones can have other lengths and other rest rotations.
//!
//! Both skeletons rest in a T-pose. Each target bone turns away from its rest pose as its source bone does, adjusted
//! by comparing the two rest poses:
//! - a limb or finger points where the source's points;
//! - a hand keeps the source palm's facing, and a foot its level heading, at its own rest tilt;
//! - the pelvis, spine, neck and head keep the target's own rest posture.
//!
//! When the source has no `spine_mid`, the target's takes half the turn from spine to chest; any other bone the source
//! lacks follows its parent. The pelvis moves as the source's does, scaled by the ratio of the two hip heights. Then
//! each leg bends so its ankle goes where the source's does. Near the ground, the ankle moves as the source's does,
//! scaled the same way, from the target's own stance, so planted feet stay planted. Higher up, it goes where the
//! target's leg reaches when bent like the source's. Where a leg cannot reach its goal, as when a long stride meets
//! shorter legs, the whole body lowers just enough. Each knee keeps the direction it bends in.

use anyhow::{Result, bail};
use glam::{DMat3, DVec3};

use crate::rig::pose::{Joint, Pose, UP, frame, halfway, level, palm, place, smoothstep, swing};
use crate::rig::pose_edit::{Leg, bend, lower_to_reach};
use crate::rig::{self, RIG};

/// The bones that keep the target's own rest posture.
const POSTURE: [&str; 6] = ["pelvis", "spine", "spine_mid", "chest", "neck", "head"];

/// Between these heights of the source's ankle above its rest height, in source hip heights, the leg goal fades from
/// following the source's ankle to following the leg's shape.
const GROUND: (f64, f64) = (0.25, 0.5);

/// The furthest a solved ankle may sit from its goal, in metres.
const ANKLE_TOLERANCE: f64 = 0.001;

/// The lowest a standing skeleton's hips may be above its floor, in metres.
const MIN_HIPS_M: f64 = 0.3;

/// The bone after each limb or finger bone, which gives its direction.
fn next(bone: &str) -> Option<String> {
    let (base, side) = bone.rsplit_once('_')?;
    let after = match base {
        "clavicle" => "upper_arm",
        "upper_arm" => "forearm",
        "forearm" => "hand",
        "thigh" => "shin",
        "shin" => "foot",
        _ => {
            let (digit, k) = base.rsplit_once('_')?;
            return matches!(k, "1" | "2").then(|| format!("{digit}_{}_{side}", k.parse::<u8>().unwrap() + 1));
        }
    };
    Some(format!("{after}_{side}"))
}

/// Retargets `clip`, frames of the source skeleton's world pose, onto the target skeleton. Every rig bone the target
/// has gets a joint in every frame.
pub fn retarget(source_rest: &Pose, clip: &[Pose], target_rest: &Pose) -> Result<Vec<Pose>> {
    let bone = |name: &str| rig::index(name);
    let s = |name: &str| source_rest[bone(name)].map(|joint| joint.position);
    let t = |name: &str| target_rest[bone(name)].map(|joint| joint.position);
    for name in RIG.iter().map(|bone| bone.name) {
        let optional = name == "spine_mid" || is_finger(name);
        if !optional && (s(name).is_none() || t(name).is_none()) {
            bail!("both skeletons need a {name} bone");
        }
    }
    let both = |name: &str| s(name).is_some() && t(name).is_some();

    // C turns the source's facing into the target's: both bodies' (forward, left, up) frames.
    let body = |left: DVec3| {
        let left = level(left).normalize();
        DMat3::from_cols(left.cross(UP).normalize(), left, UP)
    };
    let left = |p: &dyn Fn(&str) -> Option<DVec3>| p("upper_arm_l").unwrap() - p("upper_arm_r").unwrap();
    let c = body(left(&t)) * body(left(&s)).transpose();
    let ci = c.transpose();
    let source_hips = s("pelvis").unwrap().y;
    // Every move scales by the ratio of the hip heights: a skeleton standing off its floor would scale them wildly.
    for (whose, hips) in [("source", source_hips), ("target", t("pelvis").unwrap().y)] {
        if hips < MIN_HIPS_M {
            bail!(
                "the {whose}'s hips are {hips:.3} m above its floor; a standing skeleton's are at least {MIN_HIPS_M} m"
            );
        }
    }
    let scale = t("pelvis").unwrap().y / source_hips;

    // Each bone's rest calibration X: the target bone turns by C S S_rest^-1 X T_rest.
    let mut x: Vec<Option<DMat3>> = vec![None; RIG.len()];
    for side in ["l", "r"] {
        let name = |part: &str| format!("{part}_{side}");
        if let (Some(source), Some(target)) = (palm(source_rest, side), palm(target_rest, side)) {
            x[bone(&name("hand"))] = Some(source * target.transpose());
        }
        let foot =
            |p: &dyn Fn(&str) -> Option<DVec3>| frame(level(p(&name("toe")).unwrap() - p(&name("foot")).unwrap()), UP);
        let feet = foot(&s) * foot(&t).transpose();
        x[bone(&name("foot"))] = Some(feet);
        x[bone(&name("toe"))] = Some(feet);
    }
    for (i, rig_bone) in RIG.iter().enumerate() {
        let name = rig_bone.name;
        if x[i].is_some() || POSTURE.contains(&name) || !both(name) {
            continue;
        }
        if let Some(child) = next(name).filter(|child| both(child)) {
            let q = swing(t(&child).unwrap() - t(name).unwrap(), c * (s(&child).unwrap() - s(name).unwrap()));
            x[i] = Some(ci * q);
        }
    }
    for (i, rig_bone) in RIG.iter().enumerate() {
        if POSTURE.contains(&rig_bone.name) {
            x[i] = Some(ci);
        } else if x[i].is_none() {
            x[i] = rig::parent(i).and_then(|parent| x[parent]);
        }
    }

    let rest_rotation = |i: usize| target_rest[i].unwrap().rotation;
    let rest_position = |i: usize| target_rest[i].unwrap().position;
    let mut frames = Vec::with_capacity(clip.len());
    let mut worst_ankle: f64 = 0.0;
    for source in clip {
        let mut rotation: Vec<Option<DMat3>> = vec![None; RIG.len()];
        for (i, rig_bone) in RIG.iter().enumerate() {
            if both(rig_bone.name) {
                let (now, rest) = (source[i].unwrap(), source_rest[i].unwrap());
                rotation[i] = Some(c * now.rotation * rest.rotation.transpose() * x[i].unwrap() * rest_rotation(i));
            }
        }
        let spine_mid = bone("spine_mid");
        if target_rest[spine_mid].is_some() && rotation[spine_mid].is_none() {
            let turn = |i: usize| rotation[i].unwrap() * rest_rotation(i).transpose();
            rotation[spine_mid] = Some(halfway(turn(bone("spine")), turn(bone("chest"))) * rest_rotation(spine_mid));
        }
        for i in 0..RIG.len() {
            if target_rest[i].is_some() && rotation[i].is_none() {
                let parent = rig::parent(i).unwrap();
                rotation[i] = Some(rotation[parent].unwrap() * rest_rotation(parent).transpose() * rest_rotation(i));
            }
        }

        // Forward kinematics, the pelvis first.
        let mut pose: Pose = rotation
            .iter()
            .map(|rotation| rotation.map(|rotation| Joint { rotation, position: DVec3::ZERO }))
            .collect();
        let pelvis = bone("pelvis");
        let source_move = |i: usize| c * (source[i].unwrap().position - source_rest[i].unwrap().position) * scale;
        pose[pelvis].as_mut().unwrap().position = rest_position(pelvis) + source_move(pelvis);
        for i in 0..RIG.len() {
            if i != pelvis && pose[i].is_some() {
                let position = place(i, &pose, target_rest);
                pose[i].as_mut().unwrap().position = position;
            }
        }

        // The legs: each ankle to its goal, the body lowered if a leg cannot reach it, and the knee kept in its
        // current bend plane.
        let goals: Vec<(Leg, DVec3)> = [Leg::on("l"), Leg::on("r")]
            .into_iter()
            .map(|leg| {
                let foot = leg.foot;
                let rise = (source[foot].unwrap().position.y - source_rest[foot].unwrap().position.y) / source_hips;
                let ground = rest_position(foot) + source_move(foot);
                let w = 1.0 - smoothstep(GROUND.0, GROUND.1, rise.abs());
                (leg, ground * w + pose[foot].unwrap().position * (1.0 - w))
            })
            .collect();
        lower_to_reach(&mut pose, target_rest, &goals);
        for &(leg, goal) in &goals {
            let hip = pose[leg.thigh].unwrap().position;
            let (axis, bent) = ((goal - hip).normalize(), pose[leg.shin].unwrap().position - hip);
            let straight = (bent - axis * bent.dot(axis)).length() < 1e-6;
            let pole = if straight { pose[pelvis].unwrap().rotation.x_axis } else { bent };
            worst_ankle = worst_ankle.max(bend(&mut pose, target_rest, leg, goal, pole));
        }
        frames.push(pose);
    }
    if worst_ankle > ANKLE_TOLERANCE {
        bail!("an ankle misses its goal by {:.1} mm", worst_ankle * 1000.0);
    }
    Ok(frames)
}

fn is_finger(name: &str) -> bool {
    ["thumb_", "index_", "middle_", "ring_", "pinky_"].iter().any(|digit| name.starts_with(digit))
}
