//! The `equipment` kind: something a character holds in its right hand, such as the paraglider, written as
//! `<folder name>.glb` with its one clip under the folder's name.
//!
//! It comes from the motion library with the skeleton that held it there. Its export is placed in that skeleton's
//! right palm frame (`pose::palm`), the frame a character's `grip_r` node gives, so a character that holds it at its
//! grip holds it as the library's skeleton did, wherever its own hand is.

use std::path::{Path, PathBuf};

use anyhow::{Result, bail};
use glam::{DMat4, DQuat, DVec3};
use serde::{Deserialize, Serialize};

use crate::glb::{Glb, Trs};
use crate::rig::pose::{palm, rig_nodes, rig_pose};
use crate::rig::{self, Bones};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    /// The equipment, with its clip, relative to the asset folder.
    source: PathBuf,
    /// The clip's name in that file.
    clip: String,
    /// The motion library's skeleton at rest, relative to the asset folder.
    holder: PathBuf,
    /// The holder's bone the equipment's root sits at.
    held_at: String,
    /// How much larger it is drawn than its source.
    scale: f64,
}

pub fn export(folder: &Path, settings: &Settings, output: &Path) -> Result<()> {
    let name = folder.file_name().unwrap().to_string_lossy();
    let holder = Glb::read(&folder.join(&settings.holder))?;
    let worlds = holder.worlds(&holder.rest()?);
    let rest = rig_pose(&worlds, &rig_nodes(&holder, &Bones::library())?);
    let Some(palm) = palm(&rest, "r") else { bail!("the holder's right hand needs an index and a little finger") };
    let wrist = rest[rig::index("hand_r")].unwrap().position;
    let grip = DMat4::from_rotation_translation(DQuat::from_mat3(&palm), wrist);
    let held = grip.inverse() * worlds[holder.node(&settings.held_at)?];

    let mut glb = Glb::read(&folder.join(&settings.source))?;
    glb.keep_animation(&settings.clip, &name)?;
    let locals = glb.rest()?;
    for root in glb.roots() {
        let world = held * DMat4::from_scale(DVec3::splat(settings.scale)) * locals[root].matrix();
        let (scale, rotation, translation) = world.to_scale_rotation_translation();
        glb.set_transform(root, &Trs { translation, rotation: rotation.normalize(), scale });
    }
    glb.write(output)
}
