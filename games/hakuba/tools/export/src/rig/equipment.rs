//! The `equipment` kind: something a character holds in both hands above it, such as the paraglider, written as
//! `<folder name>.glb` with its one clip under the folder's name.
//!
//! It comes from the motion library with the skeleton that held it there, posed as it held it. Its export is placed in
//! that skeleton's body frame between its hands: the origin halfway between the wrists, the axes those of the body
//! (left +X, up +Y, forward +Z). A node `holder` carries, in its extras, how high the skeleton's hips stand at rest
//! (`{"hips_m": 0.97}`), so a character can hold it between its own hands, scaled to its own size.

use std::path::{Path, PathBuf};

use anyhow::{Result, bail};
use glam::{DMat3, DMat4, DVec3};
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::glb::{Glb, Trs};
use crate::rig::pose::{UP, level, rig_nodes, rig_pose};
use crate::rig::{self, Bones};

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
    let (Some(left), Some(right), Some(thigh_l), Some(thigh_r)) =
        (at("hand_l"), at("hand_r"), at("thigh_l"), at("thigh_r"))
    else {
        bail!("the holder needs both hands and both thighs")
    };
    let side = level(thigh_l - thigh_r).normalize();
    let body = DMat4::from_mat3_translation(DMat3::from_cols(side, UP, side.cross(UP)), (left + right) * 0.5);
    let held = body.inverse() * worlds[holder.node(&settings.held_at)?];

    let mut glb = Glb::read(&folder.join(&settings.source))?;
    glb.keep_animation(&settings.clip, &name)?;
    let locals = glb.rest()?;
    for root in glb.roots() {
        let world = held * DMat4::from_scale(DVec3::splat(settings.scale)) * locals[root].matrix();
        let (scale, rotation, translation) = world.to_scale_rotation_translation();
        glb.set_transform(root, &Trs { translation, rotation: rotation.normalize(), scale });
    }
    glb.add_data("holder", json!({ "hips_m": (hips * 1000.0).round() / 1000.0 }));
    glb.write(output)
}
