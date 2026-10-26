//! The `animation` kind: a clip retargeted once onto the rig, written as `<folder name>.glb`, the rig's skeleton
//! playing that one clip under the folder's name.

use std::path::{Path, PathBuf};

use anyhow::{Result, bail};
use glam::DQuat;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::glb::{Glb, Track};
use crate::rig::animations::{self, Animation};
use crate::rig::pose::{Pose, rig_nodes, rig_pose, rig_rest};
use crate::rig::retarget::retarget;
use crate::rig::{self, Bones, RIG};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    /// The file holding the source clip, relative to the asset folder.
    source: PathBuf,
    /// The source clip's name in that file.
    clip: String,
}

pub fn export(folder: &Path, settings: &Settings, output: &Path) -> Result<()> {
    let name = folder.file_name().unwrap().to_string_lossy();
    let Some(animation) = animations::named(&name) else {
        bail!("there is no animation named {name} in animations.rs")
    };
    let glb = Glb::read(&folder.join(&settings.source))?;
    let nodes = rig_nodes(&glb, &animation.source())?;
    let rest = rig_pose(&glb.worlds(&glb.rest()?), &nodes);
    let (fps, frames) = glb.sample(&settings.clip)?;
    let clip: Vec<Pose> = frames.iter().map(|locals| rig_pose(&glb.worlds(locals), &nodes)).collect();
    let frames = retarget(&rest, &clip, &rig_rest())?;
    write(output, &name, fps, &frames)
}

/// The animation's clip on the rig: its frame rate and the rig's pose in each frame.
pub fn read(animation: &dyn Animation) -> Result<(f64, Vec<Pose>)> {
    let glb = Glb::read(&animations::output(animation))?;
    let nodes = rig_nodes(&glb, &Bones::rig())?;
    let (fps, frames) = glb.sample(animation.name())?;
    Ok((fps, frames.iter().map(|locals| rig_pose(&glb.worlds(locals), &nodes)).collect()))
}

/// Writes the rig's skeleton at rest, playing `frames` as the animation `name`.
fn write(output: &Path, name: &str, fps: f64, frames: &[Pose]) -> Result<()> {
    let nodes: Vec<Value> = RIG
        .iter()
        .enumerate()
        .map(|(i, bone)| {
            let parent = rig::parent(i).map_or([0.0; 3], |parent| RIG[parent].rest);
            let offset: Vec<f64> = (0..3).map(|k| bone.rest[k] - parent[k]).collect();
            let children: Vec<usize> = (0..RIG.len()).filter(|&child| rig::parent(child) == Some(i)).collect();
            let mut node = json!({ "name": bone.name, "translation": offset });
            if !children.is_empty() {
                node["children"] = json!(children);
            }
            node
        })
        .collect();
    let pelvis = rig::index("pelvis");
    let mut glb = Glb::from_json(json!({
        "asset": { "version": "2.0" },
        "scene": 0,
        "scenes": [{ "nodes": [pelvis] }],
        "nodes": nodes,
    }));
    let joint = |frame: &Pose, i: usize| frame[i].expect("the rig has every bone");
    let mut tracks = vec![(pelvis, Track::Translation(frames.iter().map(|f| joint(f, pelvis).position).collect()))];
    for i in 0..RIG.len() {
        let local = |frame: &Pose| {
            let parent = rig::parent(i).map_or(glam::DMat3::IDENTITY, |parent| joint(frame, parent).rotation);
            DQuat::from_mat3(&(parent.transpose() * joint(frame, i).rotation)).normalize()
        };
        tracks.push((i, Track::Rotation(continuous(frames.iter().map(local).collect()))));
    }
    glb.add_animation(name, fps, &tracks);
    glb.write(output)
}

/// The rotations with their signs flipped where needed, so each key takes the short way from the last.
pub fn continuous(mut keys: Vec<DQuat>) -> Vec<DQuat> {
    for k in 1..keys.len() {
        if keys[k].dot(keys[k - 1]) < 0.0 {
            keys[k] = -keys[k];
        }
    }
    keys
}
