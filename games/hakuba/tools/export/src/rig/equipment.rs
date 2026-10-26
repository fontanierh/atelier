//! The `equipment` kind: something a character holds in both hands above it, such as the paraglider, written as
//! `<folder name>.glb` with its one clip under the folder's name.
//!
//! It comes from the motion library with the skeleton that held it there, posed as it held it. Its export is placed in
//! that skeleton's body frame between its fists: the origin halfway between them, each the middle of its wrist and its
//! middle finger's three bones, where a fist closes on what it holds, between the palm and the curled fingers; the axes
//! those of the body (left +X, up +Y, forward +Z). A node `holder` carries, in its extras, how high the skeleton's hips
//! stand at rest and its two handles in the export's frame, left then right, each the stretch of tube a fist closes
//! round, from its back end to its front end, and the tube's radius
//! (`{"hips_m": 0.97, "handles": [[[x, y, z], [x, y, z]], [[x, y, z], [x, y, z]]], "handle_radius_m": 0.03}`). So a
//! character can hold it on its own body, scaled to its own size, and close each of its own fists round a handle.

use std::path::{Path, PathBuf};

use anyhow::{Result, bail};
use glam::{DMat3, DMat4, DVec3};
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::glb::{Glb, Trs};
use crate::rig::pose::{UP, level, rig_nodes, rig_pose};
use crate::rig::{self, Bones};

/// How far from its handle the holder's fist may close, in metres: further, and the handles are on the wrong sides or
/// in the wrong frame.
const MOST_FIST_TO_HANDLE_M: f64 = 0.1;

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Settings {
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
    /// How much larger it is drawn than its source.
    scale: f64,
    /// The left hand's handle in the source's frame, in metres: the stretch of tube its fist closes round, from its back
    /// end to its front end.
    handle_left_m: [[f64; 3]; 2],
    /// The right hand's.
    handle_right_m: [[f64; 3]; 2],
    /// The handles' tube's radius in the source, in metres.
    handle_radius_m: f64,
}

pub fn export(folder: &Path, settings: &Settings, output: &Path) -> Result<()> {
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
    let held = body.inverse() * worlds[holder.node(&settings.held_at)?];
    let placed = held * DMat4::from_scale(DVec3::splat(settings.scale));

    let mut glb = Glb::read(&folder.join(&settings.source))?;
    glb.keep_animation(&settings.clip, &name)?;
    let locals = glb.rest()?;
    for root in glb.roots() {
        let world = placed * locals[root].matrix();
        let (scale, rotation, translation) = world.to_scale_rotation_translation();
        glb.set_transform(root, &Trs { translation, rotation: rotation.normalize(), scale });
    }

    // Each handle in the export's frame, checked against the fist that held it.
    let mut handles = Vec::new();
    for (handle, fist, side) in [(settings.handle_left_m, left, "left"), (settings.handle_right_m, right, "right")] {
        let [from, to] = handle.map(|end| placed.transform_point3(DVec3::from_array(end)));
        let fist = body.inverse().transform_point3(fist);
        let along = (to - from).normalize();
        let nearest = from + along * (fist - from).dot(along).clamp(0.0, (to - from).length());
        if nearest.distance(fist) > MOST_FIST_TO_HANDLE_M {
            bail!("the holder's {side} fist closes {:.0} cm from its handle", nearest.distance(fist) * 100.0);
        }
        handles.push([from, to].map(|end| end.to_array().map(|v| (v * 10000.0).round() / 10000.0)));
    }
    let radius = settings.handle_radius_m * settings.scale;
    glb.add_data(
        "holder",
        json!({
            "hips_m": (hips * 1000.0).round() / 1000.0,
            "handles": handles,
            "handle_radius_m": (radius * 10000.0).round() / 10000.0,
        }),
    );
    glb.write(output)
}
