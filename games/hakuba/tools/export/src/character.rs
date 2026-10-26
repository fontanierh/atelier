//! The `character` kind: a character's model, scaled to its height, with smaller textures and no morph targets, its
//! rig bones renamed to the rig's names, and every animation fitted to it.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use glam::DQuat;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::animation::{self, continuous};
use crate::animations::{self, ANIMATIONS};
use crate::characters::{self, Character};
use crate::glb::{Glb, Track, Trs};
use crate::pose::{Joint, Pose, rig_nodes, rig_pose, rig_rest};
use crate::retarget::retarget;
use crate::rig::{self, RIG};

/// The furthest a bone may sit from where the fitted animation places it, in metres.
const PLACEMENT_TOLERANCE: f64 = 0.001;

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    /// The model, relative to the asset folder.
    source: PathBuf,
    /// How tall the character stands in the game, in metres.
    height_m: f64,
    /// The largest side of any texture, in pixels.
    texture_size: u32,
    /// The character's changes to each animation, by animation name, in the form that animation reads.
    #[serde(default)]
    animations: BTreeMap<String, Value>,
}

pub fn export(folder: &Path, settings: &Settings, output: &Path) -> Result<()> {
    let mut glb = Glb::read(&folder.join(&settings.source))?;
    glb.remove_morph_targets();
    glb.scale_to_height(settings.height_m);
    glb.resize_images(settings.texture_size)?;
    let name = folder.file_name().unwrap().to_string_lossy();
    let Some(character) = characters::named(&name) else {
        bail!("there is no character named {name} in characters.rs")
    };
    if let Some(name) = settings.animations.keys().find(|name| animations::named(name).is_none()) {
        bail!("animations.{name}: there is no animation named {name}");
    }
    animate(&mut glb, character, &settings.animations)?;
    glb.write(output)
}

/// Fits every animation to `character`, with its `changes` to each, and adds it to its model, then renames its rig
/// bones to the rig's names.
fn animate(glb: &mut Glb, character: &dyn Character, changes: &BTreeMap<String, Value>) -> Result<()> {
    let nodes = rig_nodes(glb, &character.bones())?;
    let rest_locals = glb.rest()?;
    let rest = rig_pose(&glb.worlds(&rest_locals), &nodes);

    for animation in ANIMATIONS {
        let (fps, clip) = animation::read(animation)?;
        let mut frames = retarget(&rig_rest(), &clip, &rest)?;
        let name = animation.name();
        animation.change(changes.get(name), &rest, &mut frames).with_context(|| format!("animations.{name}"))?;
        let tracks = tracks(glb, &nodes, &rest_locals, &frames)?;
        glb.add_animation(animation.name(), fps, &tracks);
    }

    for (bone, node) in RIG.iter().zip(&nodes) {
        if let Some(node) = node {
            glb.rename_node(*node, bone.name);
        }
    }
    Ok(())
}

/// The model's keys for a fitted animation: each rig bone's rotation relative to its parent node, and the pelvis's
/// position. Bones outside the rig keep their rest transform and follow their parents.
fn tracks(glb: &Glb, nodes: &[Option<usize>], rest: &[Trs], frames: &[Pose]) -> Result<Vec<(usize, Track)>> {
    let parents = glb.parents();
    let pelvis = rig::index("pelvis");
    let bone_of = |node: usize| nodes.iter().position(|&n| n == Some(node));
    let order = depth_order(&parents);
    let mut rotations: Vec<Vec<DQuat>> = vec![Vec::new(); RIG.len()];
    let mut pelvis_positions = Vec::new();
    let mut worst: f64 = 0.0;
    for frame in frames {
        let mut locals = rest.to_vec();
        let mut worlds = vec![glam::DMat4::IDENTITY; rest.len()];
        for &node in &order {
            let parent_world = parents[node].map_or(glam::DMat4::IDENTITY, |parent| worlds[parent]);
            if let Some(bone) = bone_of(node) {
                let joint: Joint = frame[bone].expect("the fitted animation poses every mapped bone");
                let (_, parent_rotation, _) = parent_world.to_scale_rotation_translation();
                let rotation = (parent_rotation.inverse() * DQuat::from_mat3(&joint.rotation)).normalize();
                locals[node].rotation = rotation;
                rotations[bone].push(rotation);
                if bone == pelvis {
                    locals[node].translation = parent_world.inverse().transform_point3(joint.position);
                    pelvis_positions.push(locals[node].translation);
                }
            }
            worlds[node] = parent_world * locals[node].matrix();
            if let Some(bone) = bone_of(node) {
                worst = worst.max(Joint::of(worlds[node]).position.distance(frame[bone].unwrap().position));
            }
        }
    }
    if worst > PLACEMENT_TOLERANCE {
        bail!("a bone sits {:.1} mm from where the fitted animation places it", worst * 1000.0);
    }
    let mut tracks = vec![(nodes[pelvis].unwrap(), Track::Translation(pelvis_positions))];
    for (bone, keys) in rotations.into_iter().enumerate() {
        if let Some(node) = nodes[bone] {
            tracks.push((node, Track::Rotation(continuous(keys))));
        }
    }
    Ok(tracks)
}

/// Every node, each after its parent.
fn depth_order(parents: &[Option<usize>]) -> Vec<usize> {
    let depth = |mut node: usize| {
        let mut depth = 0;
        while let Some(parent) = parents[node] {
            node = parent;
            depth += 1;
        }
        depth
    };
    let mut order: Vec<usize> = (0..parents.len()).collect();
    order.sort_by_key(|&node| depth(node));
    order
}
