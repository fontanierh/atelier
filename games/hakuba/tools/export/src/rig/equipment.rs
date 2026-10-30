//! The `equipment` kind: a held library clip, or independent scenes driven by solved skeleton bones.
//! Each articulated scene has one identity root whose mesh is baked into that bone's local game frame.
//! Its holder names the same-frame attachment targets; the runtime must not add a second grip offset.
//! Held clips are written as `<folder name>.glb` with their one clip under the folder's name.
//!
//! It comes from the motion library with the skeleton that held it there, posed as it held it, and is drawn at its
//! source's size, the size that skeleton held it at. Its export is placed in that skeleton's body frame between its
//! fists: the origin halfway between them, each the middle of its wrist and its middle finger's three bones, where a
//! fist closes on what it holds, between the palm and the curled fingers; the axes those of the body (left +X, up +Y,
//! forward +Z). A node `holder` carries, in its extras, in the export's frame, left then right:
//!
//! - `hips_m`: how high the skeleton's hips stand at rest;
//! - `handles`: each the stretch of tube a fist closes round, from its back end to its front end, and
//!   `handle_radius_m`, the tube's radius;
//! - `palms`: each hand's palm frame as the skeleton held it (`pose::palm`), its origin at the wrist (`wrist_m`) and
//!   its rotation (`rotation`, a quaternion `[x, y, z, w]`).
//!
//! (`{"hips_m": 0.97, "handles": [[[x, y, z], [x, y, z]], ...], "handle_radius_m": 0.03,
//! "palms": [{"wrist_m": [x, y, z], "rotation": [x, y, z, w]}, ...]}`). So a character can hold it on its own body,
//! scaled to its own size, put each of its hands exactly where and as the skeleton's was, and close its fingers round
//! the handle.

use std::path::{Path, PathBuf};

use anyhow::{Result, bail};
use glam::{DMat3, DMat4, DQuat, DVec3};
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::glb::{Glb, Trs};
use crate::rig::pose::{UP, level, palm, rig_nodes, rig_pose};
use crate::rig::{self, Bones};

/// How far outside its handle's surface each joint of the holder's fingers may lie, in metres: further, and the fist
/// does not close round the handle, so the handles are wrong, or on the wrong sides, or the equipment is not where the
/// holder held it. No joint may lie inside the tube by more than the same.
const MOST_FINGER_OFF_HANDLE_M: f64 = 0.02;

/// The fingers but the thumb, whose three joints each must lie on the handle.
const FINGERS: [&str; 4] = ["index", "middle", "ring", "pinky"];

/// Held equipment has one library clip; articulated equipment has independent driven scenes.
#[derive(Serialize, Deserialize)]
#[serde(untagged)]
pub enum Settings {
    Held(Held),
    Articulated(Articulated),
}

/// A source whose named scenes follow the matching solved skeleton bones.
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Articulated {
    source: PathBuf,
    parts: Vec<String>,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Held {
    /// The equipment, with its clip, relative to the asset folder.
    source: PathBuf,
    /// The clip's name in that file.
    clip: String,
    /// The motion library's skeleton, with the clip it held the equipment in, relative to the asset folder.
    holder: PathBuf,
    /// That clip's name: the skeleton's pose in its first frame places the equipment.
    pose: String,
    /// The holder's bone the equipment's root sits at.
    held_at: String,
    /// The left hand's handle in the source's frame, in metres: the stretch of tube its fist closes round, from its back
    /// end to its front end.
    handle_left_m: [[f64; 3]; 2],
    /// The right hand's.
    handle_right_m: [[f64; 3]; 2],
    /// The handles' tube's radius in the source, in metres.
    handle_radius_m: f64,
}

pub fn export(folder: &Path, settings: &Settings, output: &Path) -> Result<()> {
    match settings {
        Settings::Held(settings) => export_held(folder, settings, output),
        Settings::Articulated(settings) => {
            let glb = Glb::read(&folder.join(&settings.source))?;
            let scenes = glb.scenes();
            if settings.parts.is_empty() || scenes.len() != settings.parts.len() {
                bail!("articulated equipment needs exactly one scene per part");
            }
            let rest = glb.rest()?;
            let unique: std::collections::BTreeSet<_> = settings.parts.iter().collect();
            if unique.len() != settings.parts.len() {
                bail!("articulated equipment part names must be unique");
            }
            for part in &settings.parts {
                let node = glb.node(part)?;
                if scenes.iter().filter(|(name, roots)| name == part && roots == &[node]).count() != 1 {
                    bail!("part {part} needs its own matching single-root scene");
                }
                if !rest[node].matrix().abs_diff_eq(DMat4::IDENTITY, 1e-8) {
                    bail!("part {part} must be baked into its driven bone frame");
                }
                if glb.extras(part)?["bone"].as_str() != Some(part.as_str()) {
                    bail!("part {part} must name the bone that drives it");
                }
            }
            let holder = glb.extras("holder")?;
            if holder["frame"].as_str() != Some("solved-bone-local")
                || holder["reference_pose"].as_str().is_none_or(str::is_empty)
                || holder["reference_bank"].as_u64().is_none()
                || holder["attachment_targets"].as_array().is_none_or(|targets| {
                    targets.is_empty() || targets.iter().any(|target| target.as_str().is_none_or(str::is_empty))
                })
            {
                bail!("articulated equipment must declare its solved frame, source reference and attachment targets");
            }
            glb.write(output)
        }
    }
}

fn export_held(folder: &Path, settings: &Held, output: &Path) -> Result<()> {
    let name = folder.file_name().unwrap().to_string_lossy();
    let holder = Glb::read(&folder.join(&settings.holder))?;
    let nodes = rig_nodes(&holder, &Bones::library())?;
    let hips = rig_pose(&holder.worlds(&holder.rest()?), &nodes)[rig::index("pelvis")].unwrap().position.y;
    let (_, frames) = holder.sample(&settings.pose)?;
    let worlds = holder.worlds(&frames[0]);
    let pose = rig_pose(&worlds, &nodes);
    let at = |bone: &str| pose[rig::index(bone)].map(|joint| joint.position);
    let fist = |side: &str| {
        let bones = ["hand", "middle_1", "middle_2", "middle_3"].map(|bone| at(&format!("{bone}_{side}")));
        Some(bones.into_iter().sum::<Option<DVec3>>()? / 4.0)
    };
    let (Some(left), Some(right), Some(thigh_l), Some(thigh_r)) = (fist("l"), fist("r"), at("thigh_l"), at("thigh_r"))
    else {
        bail!("the holder needs both hands, with their middle fingers' three bones, and both thighs")
    };
    let side = level(thigh_l - thigh_r).normalize();
    let body = DMat4::from_mat3_translation(DMat3::from_cols(side, UP, side.cross(UP)), (left + right) * 0.5);
    let into_body = body.inverse();
    let placed = into_body * worlds[holder.node(&settings.held_at)?];

    let mut glb = Glb::read(&folder.join(&settings.source))?;
    glb.keep_animation(&settings.clip, &name)?;
    let locals = glb.rest()?;
    for root in glb.roots() {
        let world = placed * locals[root].matrix();
        let (scale, rotation, translation) = world.to_scale_rotation_translation();
        glb.set_transform(root, &Trs { translation, rotation: rotation.normalize(), scale });
    }

    // Each handle and palm in the export's frame, the handle checked against the fingers that closed round it.
    let (mut handles, mut palms) = (Vec::new(), Vec::new());
    for (handle, side) in [(settings.handle_left_m, "l"), (settings.handle_right_m, "r")] {
        let [from, to] = handle.map(|end| placed.transform_point3(DVec3::from_array(end)));
        let (along, length) = ((to - from).normalize(), (to - from).length());
        // How far a point is from the handle's stretch of axis, between its ends.
        let off_axis = |point: DVec3| (point - (from + along * (point - from).dot(along).clamp(0.0, length))).length();
        for finger in FINGERS {
            for joint in 1..=3 {
                let bone = format!("{finger}_{joint}_{side}");
                let Some(point) = at(&bone) else { bail!("the holder needs its {bone} bone") };
                let off = off_axis(into_body.transform_point3(point)) - settings.handle_radius_m;
                if off.abs() > MOST_FINGER_OFF_HANDLE_M {
                    bail!("the holder's {bone} lies {:.1} cm off its handle's surface", off * 100.0);
                }
            }
        }
        let (Some(frame), Some(wrist)) = (palm(&pose, side), at(&format!("hand_{side}"))) else {
            bail!("the holder's {side} hand needs an index and a little finger")
        };
        let rotation = DQuat::from_mat3(&(DMat3::from_mat4(into_body) * frame)).normalize();
        palms.push(json!({
            "wrist_m": round(into_body.transform_point3(wrist), 10000.0),
            "rotation": rotation.to_array().map(|v| (v * 1e6).round() / 1e6),
        }));
        handles.push([from, to].map(|end| round(end, 10000.0)));
    }
    glb.add_data(
        "holder",
        json!({
            "hips_m": (hips * 1000.0).round() / 1000.0,
            "handles": handles,
            "handle_radius_m": (settings.handle_radius_m * 10000.0).round() / 10000.0,
            "palms": palms,
        }),
    );
    glb.write(output)
}

/// `point`'s coordinates rounded to `1 / per` metres.
fn round(point: DVec3, per: f64) -> [f64; 3] {
    point.to_array().map(|v| (v * per).round() / per)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn articulated_parts_preserve_their_frames_and_reject_unbound_sources() {
        let folder = std::env::temp_dir().join(format!("hakuba-equipment-{}", std::process::id()));
        fs::create_dir_all(&folder).unwrap();
        let source = json!({
            "asset": { "version": "2.0" },
            "scene": 0,
            "scenes": [{ "name": "body", "nodes": [0] }],
            "nodes": [
                { "name": "body", "extras": { "bone": "body" }, "children": [1] },
                { "name": "holder", "extras": {
                    "frame": "solved-bone-local", "reference_pose": "rest", "reference_bank": 0,
                    "attachment_targets": ["hand_target"]
                } }
            ]
        });
        let settings = Settings::Articulated(Articulated { source: "source.glb".into(), parts: vec!["body".into()] });
        Glb::from_json(source.clone()).write(&folder.join("source.glb")).unwrap();
        export(&folder, &settings, &folder.join("out.glb")).unwrap();
        let result = Glb::read(&folder.join("out.glb")).unwrap();
        assert_eq!(result.scenes(), vec![("body".into(), vec![0])]);
        assert_eq!(result.extras("holder").unwrap()["attachment_targets"], json!(["hand_target"]));

        let mut moved = source.clone();
        moved["nodes"][0]["translation"] = json!([0.1, 0.0, 0.0]);
        Glb::from_json(moved).write(&folder.join("source.glb")).unwrap();
        assert!(export(&folder, &settings, &folder.join("out.glb")).is_err());

        let mut unbound = source;
        unbound["nodes"][1]["extras"]["attachment_targets"] = json!([]);
        Glb::from_json(unbound).write(&folder.join("source.glb")).unwrap();
        assert!(export(&folder, &settings, &folder.join("out.glb")).is_err());
        fs::remove_dir_all(folder).unwrap();
    }
}
