//! The `animation` kind: a clip retargeted once onto the rig, written as `<folder name>.glb`, the rig's skeleton
//! playing that one clip under the folder's name.
//!
//! The clip loses its root motion: the game moves the character, so a run stays in place and a jump stays on the
//! ground. How fast the root travelled over the ground is kept beside the clip, in hip heights a second, for the
//! game to move the character at the speed its feet step.

use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use glam::{DMat3, DQuat, DVec3};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::glb::{Glb, Track};
use crate::rig::animations::{self, Animation};
use crate::rig::pose::{Joint, Pose, level, rig_nodes, rig_pose, rig_rest};
use crate::rig::retarget::retarget;
use crate::rig::{self, Bones, RIG};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    /// The file holding the source clip, relative to the asset folder.
    source: PathBuf,
    /// The source clip's name in that file.
    clip: String,
    /// How fast it plays, as a share of its source's speed.
    #[serde(default = "full_rate")]
    rate: f64,
    /// The first and last source frames it plays; all of them if left out.
    #[serde(default)]
    frames: Option<[f64; 2]>,
}

fn full_rate() -> f64 {
    1.0
}

/// The node beside the clip's skeleton whose extras say how fast its root travelled.
const DATA: &str = "clip";

pub fn export(folder: &Path, settings: &Settings, output: &Path) -> Result<()> {
    let name = folder.file_name().unwrap().to_string_lossy();
    let Some(animation) = animations::named(&name) else {
        bail!("there is no animation named {name} in animations.rs")
    };
    if settings.rate <= 0.0 {
        bail!("rate must be above 0");
    }
    let glb = Glb::read(&folder.join(&settings.source))?;
    let nodes = rig_nodes(&glb, &animation.source())?;
    let rest_worlds = glb.worlds(&glb.rest()?);
    let rest = rig_pose(&rest_worlds, &nodes);
    let root = root_of(&glb, nodes[rig::index("pelvis")].unwrap());
    let (fps, frames) = glb.sample(&settings.clip)?;
    // Each frame without its root motion, and that motion.
    let mut travel = Vec::with_capacity(frames.len());
    let clip: Vec<Pose> = frames
        .iter()
        .map(|locals| {
            let worlds = glb.worlds(locals);
            let moved = (worlds[root].w_axis - rest_worlds[root].w_axis).truncate();
            travel.push(moved);
            let mut pose = rig_pose(&worlds, &nodes);
            pose.iter_mut().flatten().for_each(|joint| joint.position -= moved);
            pose
        })
        .collect();
    let [first, last] = settings.frames.unwrap_or([0.0, (clip.len() - 1) as f64]);
    if !(0.0 <= first && first < last && last <= (clip.len() - 1) as f64) {
        bail!("frames must be two of the clip's frames, the first before the last");
    }
    let times: Vec<f64> = (0..).map(|k| first + k as f64 * settings.rate).take_while(|&t| t <= last + 1e-9).collect();
    let clip: Vec<Pose> = times.iter().map(|&t| pose_at(&clip, t)).collect();
    let frames = retarget(&rest, &clip, &rig_rest())?;
    let seconds = (last - first) / settings.rate / fps;
    let hips = rest[rig::index("pelvis")].unwrap().position.y;
    let speed = level(at(&travel, last) - at(&travel, first)).length() / hips / seconds;
    write(output, &name, fps, &frames, speed)
}

/// The topmost node above `node`: the source skeleton's root, which carries the clip's root motion.
fn root_of(glb: &Glb, mut node: usize) -> usize {
    let parents = glb.parents();
    while let Some(parent) = parents[node] {
        node = parent;
    }
    node
}

/// `values` at the fractional frame `t`, between its two nearest frames.
fn at(values: &[DVec3], t: f64) -> DVec3 {
    let (k, f) = (t.floor() as usize, t.fract());
    if f < 1e-9 { values[k] } else { values[k].lerp(values[k + 1], f) }
}

/// The pose at the fractional frame `t` of `clip`, between its two nearest frames.
fn pose_at(clip: &[Pose], t: f64) -> Pose {
    let (k, f) = (t.floor() as usize, t.fract());
    if f < 1e-9 {
        return clip[k].clone();
    }
    clip[k]
        .iter()
        .zip(&clip[k + 1])
        .map(|(a, b)| {
            let (a, b) = (a.as_ref()?, b.as_ref()?);
            let rotation = DQuat::from_mat3(&a.rotation).slerp(DQuat::from_mat3(&b.rotation), f);
            Some(Joint { rotation: DMat3::from_quat(rotation), position: a.position.lerp(b.position, f) })
        })
        .collect()
}

/// The animation's clip on the rig.
pub struct Clip {
    pub fps: f64,
    /// The rig's pose in each frame.
    pub frames: Vec<Pose>,
    /// How fast its root travelled over the ground before it was taken off, in hip heights a second.
    pub speed: f64,
}

/// The animation's clip on the rig, as its export holds it.
pub fn read(animation: &dyn Animation) -> Result<Clip> {
    let glb = Glb::read(&output(animation))?;
    let nodes = rig_nodes(&glb, &Bones::rig())?;
    let (fps, frames) = glb.sample(animation.name())?;
    let frames = frames.iter().map(|locals| rig_pose(&glb.worlds(locals), &nodes)).collect();
    let speed = glb.extras(DATA)?["speed"].as_f64().context("the clip's speed")?;
    Ok(Clip { fps, frames, speed })
}

/// Writes the rig's skeleton at rest, playing `frames` as the animation `name`, and the speed its root travelled.
fn write(output: &Path, name: &str, fps: f64, frames: &[Pose], speed: f64) -> Result<()> {
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
    glb.add_data(DATA, json!({ "speed": speed }));
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

/// The animation's asset folder, relative to `assets/`.
pub fn folder(animation: &dyn Animation) -> String {
    format!("animations/{}", animation.name())
}

/// The animation's exported clip on the rig.
pub fn output(animation: &dyn Animation) -> PathBuf {
    Path::new(crate::ASSETS).join(folder(animation)).join(format!("{}.glb", animation.name()))
}

/// Fails if a character changes an animation that takes no changes.
pub fn no_changes(changes: Option<&Value>) -> Result<()> {
    match changes {
        Some(_) => bail!("this animation takes no changes"),
        None => Ok(()),
    }
}

/// A character's changes to one animation, read into the form that animation defines; no change if it has none.
pub fn changes<T: Default + for<'de> Deserialize<'de>>(changes: Option<&Value>) -> Result<T> {
    Ok(changes.map(T::deserialize).transpose()?.unwrap_or_default())
}
