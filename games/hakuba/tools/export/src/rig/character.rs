//! The `character` kind: a character's model, scaled to its height, with smaller textures and no morph targets, its
//! rig bones renamed to the rig's names, and every animation fitted to it.
//!
//! Beside the model, for the game: an empty node `grip_r` under the right hand, where it holds things, and a node
//! `clips` whose extras give, by clip, how fast the character's feet carry it over the ground, in metres a second, and
//! how high its hips stand at rest (`{"speeds": {"run": 5.4, ...}, "hips_m": 0.97}`; clips that stay in place are left
//! out). The rig bones keep the rig's names, so the game finds the hands as `hand_l` and `hand_r`.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use glam::{DMat3, DMat4, DQuat, DVec3, EulerRot};
use hakuba_dye_schema::TextureDye;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};

use crate::glb::{Glb, Track, Trs};
use crate::rig::animation::{self, continuous};
use crate::rig::animations::{self, ANIMATIONS};
use crate::rig::characters::{self, Character};
use crate::rig::pose::{Joint, Pose, palm, rig_nodes, rig_pose, rig_rest};
use crate::rig::retarget::retarget;
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
    /// Preserve these named clips from the source model instead of fitting the shared library.
    #[serde(default)]
    authored_clips: Vec<String>,
    /// The source pelvis node and each moving authored clip's speed in metres a second.
    #[serde(default)]
    authored_pelvis: Option<String>,
    #[serde(default)]
    authored_speeds: BTreeMap<String, f64>,
    /// How much of the vertex-tinted base colour the material emits.
    #[serde(default)]
    vertex_emission: Option<f64>,
    /// Optional texture-sampled dye for a named body mesh.
    #[serde(default)]
    texture_dye: Option<TextureDye>,
    /// Where its right hand holds things, from its palm.
    #[serde(default)]
    hold: Hold,
}

impl Settings {
    /// Authored clips come from the model itself, without reading the shared animation exports.
    pub fn uses_authored_clips(&self) -> bool {
        !self.authored_clips.is_empty()
    }
}

/// Where a hand holds things: its palm's frame, moved and turned. The palm's axes are x, out of the right palm; y,
/// from the wrist toward the knuckles; and z, from the index finger toward the little finger.
#[derive(Serialize, Deserialize, Default)]
#[serde(default, deny_unknown_fields)]
pub struct Hold {
    /// How far it moves along the palm's axes, in centimetres.
    offset_cm: [f64; 3],
    /// How far it turns about the palm's x, y and z axes, in that order, in degrees.
    turn_deg: [f64; 3],
}

/// Speeds below this, in metres a second, are taken as a clip staying in place.
const STILL_SPEED: f64 = 0.01;

pub fn export(folder: &Path, settings: &Settings, output: &Path) -> Result<()> {
    let mut glb = Glb::read(&folder.join(&settings.source))?;
    if let Some(profile) = &settings.texture_dye {
        if !profile.valid() || settings.vertex_emission.is_some() {
            bail!("texture dye must be valid and cannot be combined with vertex emission");
        }
        validate_texture_dye_mesh(glb.document(), &profile.mesh)?;
    }
    glb.remove_morph_targets();
    glb.make_matte();
    glb.scale_to_height(settings.height_m);
    glb.resize_images(settings.texture_size)?;
    let name = folder.file_name().unwrap().to_string_lossy();
    let Some(character) = characters::named(&name) else {
        bail!("there is no character named {name} in characters.rs")
    };
    if let Some(name) = settings.animations.keys().find(|name| animations::named(name).is_none()) {
        bail!("animations.{name}: there is no animation named {name}");
    }
    if !settings.uses_authored_clips() {
        if settings.authored_pelvis.is_some() || !settings.authored_speeds.is_empty() {
            bail!("authored metadata requires authored clips");
        }
        animate(&mut glb, character, &settings.animations, &settings.hold)?;
    } else {
        if character.skeleton().is_some() {
            bail!("an authored character must not provide a shared-library skeleton map");
        }
        if !settings.animations.is_empty() {
            bail!("authored clips cannot have shared animation changes");
        }
        validate_authored(&folder.join(&settings.source), &settings.authored_clips)?;
        if settings
            .authored_speeds
            .iter()
            .any(|(name, speed)| !settings.authored_clips.contains(name) || !speed.is_finite() || *speed <= 0.0)
        {
            bail!("authored speeds must name authored clips and be finite and positive");
        }
        let pelvis = settings.authored_pelvis.as_deref().context("authored clips require a pelvis node")?;
        let hips = glb.worlds(&glb.rest()?)[glb.node(pelvis)?].w_axis.y;
        if !hips.is_finite() || hips <= 0.0 {
            bail!("authored pelvis must stand above the model origin");
        }
        glb.add_data("clips", json!({ "speeds": settings.authored_speeds, "hips_m": hips }));
    }
    if let Some(profile) = &settings.texture_dye {
        glb.add_data("texture_dye", serde_json::to_value(profile)?);
    }
    if let Some(factor) = settings.vertex_emission {
        if !factor.is_finite() || factor < 0.0 {
            bail!("vertex emission must be finite and nonnegative");
        }
        glb.add_data("vertex_emission", json!({ "factor": factor }));
    }
    glb.write(output)
}

/// Checks that every declared clip exists exactly once without resampling the authored interpolation.
fn validate_authored(path: &Path, clips: &[String]) -> Result<()> {
    let bytes = fs::read(path)?;
    let size = u32::from_le_bytes(bytes.get(12..16).context("missing GLB JSON length")?.try_into()?) as usize;
    let json: Value = serde_json::from_slice(bytes.get(20..20 + size).context("truncated GLB JSON")?)?;
    let animations = json["animations"].as_array().context("the source has no authored animations")?;
    for name in clips {
        if name.is_empty() || animations.iter().filter(|clip| clip["name"].as_str() == Some(name)).count() != 1 {
            bail!("authored clip {name:?} must occur exactly once");
        }
    }
    Ok(())
}

/// Fits every animation to `character`, with its `changes` to each, and adds it to its model with how fast each
/// carries it; puts its right hand's grip where it `hold`s things; then renames its rig bones to the rig's names.
fn animate(glb: &mut Glb, character: &dyn Character, changes: &BTreeMap<String, Value>, hold: &Hold) -> Result<()> {
    let skeleton = character.skeleton().context("a character using the shared library needs a skeleton map")?;
    let nodes = rig_nodes(glb, &skeleton.bones())?;
    let rest_locals = glb.rest()?;
    let rest_worlds = glb.worlds(&rest_locals);
    let rest = rig_pose(&rest_worlds, &nodes);
    let hips = rest[rig::index("pelvis")].unwrap().position.y;

    let mut speeds = Map::new();
    for animation in ANIMATIONS {
        let name = animation.name();
        let clip = animation::read(animation)?;
        let mut frames = retarget(&rig_rest(), &clip.frames, &rest).with_context(|| format!("fitting {name}"))?;
        animation.change(changes.get(name), &rest, &mut frames).with_context(|| format!("animations.{name}"))?;
        let tracks = tracks(glb, &nodes, &rest_locals, &frames)?;
        glb.add_animation(animation.name(), clip.fps, &tracks);
        let speed = clip.speed * hips;
        if speed > STILL_SPEED {
            speeds.insert(name.into(), json!((speed * 1000.0).round() / 1000.0));
        }
    }
    glb.add_data("clips", json!({ "speeds": speeds, "hips_m": (hips * 1000.0).round() / 1000.0 }));
    grip(glb, &nodes, &rest, &rest_worlds, hold)?;

    for (bone, node) in RIG.iter().zip(&nodes) {
        if let Some(node) = node {
            glb.rename_node(*node, bone.name);
        }
    }
    Ok(())
}

/// Adds the node `grip_r` under the right hand: its palm's frame at the wrist, moved and turned by `hold`, at the
/// world's scale.
fn grip(glb: &mut Glb, nodes: &[Option<usize>], rest: &Pose, worlds: &[DMat4], hold: &Hold) -> Result<()> {
    let hand = rig::index("hand_r");
    let palm = palm(rest, "r").context("the right hand needs an index and a little finger to hold things")?;
    let [x, y, z] = hold.turn_deg.map(f64::to_radians);
    let rotation = palm * DMat3::from_euler(EulerRot::XYZ, x, y, z);
    let position = rest[hand].unwrap().position + palm * DVec3::from_array(hold.offset_cm) / 100.0;
    let node = nodes[hand].unwrap();
    let local = worlds[node].inverse() * DMat4::from_rotation_translation(DQuat::from_mat3(&rotation), position);
    let (scale, rotation, translation) = local.to_scale_rotation_translation();
    glb.add_child(node, "grip_r", &Trs { translation, rotation: rotation.normalize(), scale });
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

/// Checks the inputs needed to dye a sampled, untinted opaque texture on a unique mesh node.
fn validate_texture_dye_mesh(document: &Value, name: &str) -> Result<()> {
    let nodes: Vec<_> =
        document["nodes"].as_array().into_iter().flatten().filter(|node| node["name"].as_str() == Some(name)).collect();
    if nodes.len() != 1 {
        bail!("texture dye target {name:?} must occur exactly once");
    }
    let mesh = nodes[0]["mesh"].as_u64().context("texture dye target must have a mesh")? as usize;
    let primitives = document["meshes"]
        .get(mesh)
        .and_then(|mesh| mesh["primitives"].as_array())
        .context("texture dye target needs mesh primitives")?;
    if primitives.is_empty() {
        bail!("texture dye target needs mesh primitives");
    }
    for primitive in primitives {
        let attrs = &primitive["attributes"];
        if attrs["TEXCOORD_0"].as_u64().and_then(|i| document["accessors"].get(i as usize)).is_none()
            || attrs.get("COLOR_0").is_some()
        {
            bail!("texture dye needs UV0 and no vertex colours");
        }
        let material = primitive["material"]
            .as_u64()
            .and_then(|i| document["materials"].get(i as usize))
            .context("texture dye needs a material")?;
        let pbr = &material["pbrMetallicRoughness"];
        let texture = &pbr["baseColorTexture"];
        let texture_index = texture["index"].as_u64().context("texture dye needs a base colour texture")? as usize;
        if document["textures"]
            .get(texture_index)
            .and_then(|t| t["source"].as_u64())
            .and_then(|i| document["images"].get(i as usize))
            .is_none()
            || pbr.get("metallicRoughnessTexture").is_some()
            || ["normalTexture", "occlusionTexture", "emissiveTexture"].iter().any(|key| material.get(*key).is_some())
            || material.get("extensions").is_some_and(|v| v.as_object().is_none_or(|o| !o.is_empty()))
            || texture["texCoord"].as_u64().unwrap_or(0) != 0
            || texture.get("extensions").is_some()
            || pbr
                .get("baseColorFactor")
                .is_some_and(|v| v.as_array().is_none_or(|a| a.len() != 4 || a.iter().any(|x| x.as_f64() != Some(1.0))))
            || material["alphaMode"].as_str().unwrap_or("OPAQUE") != "OPAQUE"
            || material["doubleSided"].as_bool().unwrap_or(false)
            || material["extensions"].get("KHR_materials_unlit").is_some()
        {
            bail!("texture dye requires an untinted UV0 texture and opaque, single-sided lit material");
        }
    }
    Ok(())
}

#[cfg(test)]
mod texture_dye_tests {
    use super::*;

    fn source() -> Value {
        json!({"nodes":[{"name":"body","mesh":0}], "meshes":[{"primitives":[{
            "attributes":{"TEXCOORD_0":0}, "material":0
        }]}], "materials":[{"pbrMetallicRoughness":{"baseColorTexture":{"index":0}}}],
        "textures":[{"source":0}], "images":[{}], "accessors":[{}]})
    }

    #[test]
    fn dye_rejects_ambiguous_targets_and_incompatible_inputs() {
        let valid = source();
        assert!(validate_texture_dye_mesh(&valid, "body").is_ok());
        let mut cases = Vec::new();
        let mut v = valid.clone();
        v["nodes"].as_array_mut().unwrap().push(json!({"name":"body"}));
        cases.push(v);
        let mut v = valid.clone();
        v["nodes"][0].as_object_mut().unwrap().remove("mesh");
        cases.push(v);
        let mut v = valid.clone();
        v["meshes"][0]["primitives"][0]["attributes"]["COLOR_0"] = json!(1);
        cases.push(v);
        let mut v = valid.clone();
        v["meshes"][0]["primitives"][0]["attributes"].as_object_mut().unwrap().remove("TEXCOORD_0");
        cases.push(v);
        let mut v = valid.clone();
        v["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"] = json!([0.5, 1, 1, 1]);
        cases.push(v);
        let mut v = valid.clone();
        v["materials"][0]["pbrMetallicRoughness"].as_object_mut().unwrap().remove("baseColorTexture");
        cases.push(v);
        let mut v = valid.clone();
        v["materials"][0]["alphaMode"] = json!("BLEND");
        cases.push(v);
        let mut v = valid.clone();
        v["materials"][0]["extensions"]["KHR_materials_unlit"] = json!({});
        cases.push(v);
        let mut v = valid.clone();
        v["materials"][0]["doubleSided"] = json!(true);
        cases.push(v);
        let mut v = valid.clone();
        v["textures"][0]["source"] = json!(99);
        cases.push(v);
        for key in ["normalTexture", "occlusionTexture", "emissiveTexture"] {
            let mut v = valid.clone();
            v["materials"][0][key] = json!({"index": 0});
            cases.push(v);
        }
        let mut v = valid.clone();
        v["materials"][0]["pbrMetallicRoughness"]["metallicRoughnessTexture"] = json!({"index": 0});
        cases.push(v);
        let mut v = valid.clone();
        v["materials"][0]["extensions"]["KHR_materials_clearcoat"] = json!({});
        cases.push(v);
        for case in cases {
            assert!(validate_texture_dye_mesh(&case, "body").is_err());
        }
    }
}
