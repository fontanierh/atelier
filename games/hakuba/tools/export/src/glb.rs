//! Reading, editing and writing binary glTF (.glb) files.
//!
//! Edits change the JSON and record new bytes for buffer views; [`Glb::write`] packs only what is still referenced,
//! so removed accessors and replaced images leave nothing behind in the file.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs;
use std::io::Cursor;
use std::path::Path;

use anyhow::{Context, Result, bail};
use glam::{DMat4, DQuat, DVec3};
use image::codecs::png::{CompressionType, FilterType, PngEncoder};
use image::{ImageFormat, ImageReader, imageops};
use serde_json::{Value, json};

const MAGIC: &[u8; 4] = b"glTF";
const VERSION: u32 = 2;
const JSON_CHUNK: &[u8; 4] = b"JSON";
const BIN_CHUNK: &[u8; 4] = b"BIN\0";

pub struct Glb {
    json: Value,
    bin: Vec<u8>,
    /// Buffer view index -> its new bytes.
    replaced: HashMap<usize, Vec<u8>>,
}

impl Glb {
    pub fn read(path: &Path) -> Result<Self> {
        let data = fs::read(path).with_context(|| format!("reading {}", path.display()))?;
        if data.len() < 12 || &data[0..4] != MAGIC || u32_at(&data, 4) != VERSION {
            bail!("{}: not a glTF 2 binary", path.display());
        }
        let (mut json, mut bin, mut offset) = (None, Vec::new(), 12);
        while offset + 8 <= data.len() {
            let length = u32_at(&data, offset) as usize;
            let chunk = data.get(offset + 8..offset + 8 + length).context("a chunk runs past the end")?;
            match &data[offset + 4..offset + 8] {
                kind if kind == JSON_CHUNK => json = Some(serde_json::from_slice(chunk)?),
                kind if kind == BIN_CHUNK => bin = chunk.to_vec(),
                _ => {}
            }
            offset += 8 + length;
        }
        let json = json.with_context(|| format!("{}: no JSON chunk", path.display()))?;
        Ok(Self { json, bin, replaced: HashMap::new() })
    }

    pub fn write(&self, path: &Path) -> Result<()> {
        let (gltf, mut data) = self.repack()?;
        let mut text = serde_json::to_vec(&gltf)?;
        text.resize(text.len().next_multiple_of(4), b' ');
        let mut body = chunk(JSON_CHUNK, &text);
        if !data.is_empty() {
            data.resize(data.len().next_multiple_of(4), 0);
            body.extend(chunk(BIN_CHUNK, &data));
        }
        let mut file = MAGIC.to_vec();
        file.extend(VERSION.to_le_bytes());
        file.extend((12 + body.len() as u32).to_le_bytes());
        file.extend(body);
        fs::write(path, file).with_context(|| format!("writing {}", path.display()))
    }

    /// The height of the meshes in their bind pose, from their primitives' position bounds.
    fn scene_height(&self) -> f64 {
        let (mut low, mut high) = (f64::INFINITY, f64::NEG_INFINITY);
        for mesh in items(&self.json, "meshes") {
            for primitive in items(mesh, "primitives") {
                let accessor = &self.json["accessors"][primitive["attributes"]["POSITION"].as_u64().unwrap() as usize];
                low = low.min(accessor["min"][1].as_f64().unwrap());
                high = high.max(accessor["max"][1].as_f64().unwrap());
            }
        }
        high - low
    }

    /// Scales every root node of the default scene so the meshes stand `height` metres tall.
    pub fn scale_to_height(&mut self, height: f64) {
        let factor = height / self.scene_height();
        let scene = self.json["scene"].as_u64().unwrap_or(0) as usize;
        let roots: Vec<usize> = items(&self.json["scenes"][scene], "nodes").map(index).collect();
        for root in roots {
            let node = &mut self.json["nodes"][root];
            let scale: Vec<f64> = match node.get("scale") {
                Some(scale) => scale.as_array().unwrap().iter().map(|s| s.as_f64().unwrap() * factor).collect(),
                None => vec![factor; 3],
            };
            node["scale"] = json!(scale);
            if let Some(translation) = node.get_mut("translation") {
                let moved: Vec<f64> =
                    translation.as_array().unwrap().iter().map(|t| t.as_f64().unwrap() * factor).collect();
                *translation = json!(moved);
            }
        }
    }

    /// Makes every material matte, as [`Glb::add_material`] does: no metal and no mirror-like reflection, whatever the
    /// source asked. A model generator's strong specular otherwise shows the sky as a white sheen, over dark hair most.
    pub fn make_matte(&mut self) {
        let Some(materials) = self.json.get_mut("materials").and_then(Value::as_array_mut) else { return };
        for material in materials {
            material["pbrMetallicRoughness"]["metallicFactor"] = json!(0.0);
            material["pbrMetallicRoughness"]["roughnessFactor"] = json!(1.0);
            material["extensions"]["KHR_materials_specular"] = json!({ "specularFactor": 0.0 });
        }
        let used = self.json.get("extensionsUsed").and_then(Value::as_array);
        if !used.is_some_and(|used| used.contains(&json!("KHR_materials_specular"))) {
            push(&mut self.json, "extensionsUsed", json!("KHR_materials_specular"));
        }
    }

    pub fn remove_morph_targets(&mut self) {
        for mesh in items_mut(&mut self.json, "meshes") {
            let mesh = mesh.as_object_mut().unwrap();
            mesh.remove("weights");
            if let Some(extras) = mesh.get_mut("extras").and_then(Value::as_object_mut) {
                extras.remove("targetNames");
            }
            for primitive in mesh.get_mut("primitives").and_then(Value::as_array_mut).into_iter().flatten() {
                primitive.as_object_mut().unwrap().remove("targets");
            }
        }
        for node in items_mut(&mut self.json, "nodes") {
            node.as_object_mut().unwrap().remove("weights");
        }
    }

    /// Shrinks every embedded PNG larger than `size` pixels on a side, keeping its aspect ratio.
    pub fn resize_images(&mut self, size: u32) -> Result<()> {
        let views: Vec<usize> =
            items(&self.json, "images").filter_map(|image| image.get("bufferView")).map(index).collect();
        for view in views {
            let reader = ImageReader::new(Cursor::new(self.view(view))).with_guessed_format()?;
            if reader.format() != Some(ImageFormat::Png) {
                bail!("buffer view {view}: only PNG images are resized");
            }
            let picture = reader.decode()?;
            if picture.width().max(picture.height()) <= size {
                continue;
            }
            let resized = picture.resize(size, size, imageops::FilterType::Lanczos3);
            let mut out = Vec::new();
            resized.write_with_encoder(PngEncoder::new_with_quality(
                &mut out,
                CompressionType::Best,
                FilterType::Adaptive,
            ))?;
            self.replaced.insert(view, out);
        }
        Ok(())
    }

    /// A file holding only `json`, such as a skeleton built in code.
    pub fn from_json(json: Value) -> Self {
        Self { json, bin: Vec::new(), replaced: HashMap::new() }
    }

    /// The index of the node named `name`.
    pub fn node(&self, name: &str) -> Result<usize> {
        items(&self.json, "nodes")
            .position(|node| node["name"].as_str() == Some(name))
            .with_context(|| format!("no node is named {name}"))
    }

    /// Read the actual position values of a named static mesh, in the glTF frame.
    pub fn node_triangles(&self, name: &str) -> Result<Vec<[DVec3; 3]>> {
        let node = &self.json["nodes"][self.node(name)?];
        let mesh = node["mesh"].as_u64().context("node needs a mesh")? as usize;
        let primitives = self.json["meshes"]
            .as_array()
            .and_then(|meshes| meshes.get(mesh))
            .and_then(|mesh| mesh["primitives"].as_array())
            .context("mesh needs primitives")?;
        let mut triangles = Vec::new();
        for primitive in primitives {
            let mut positions = Vec::new();
            let index = primitive["attributes"]["POSITION"].as_u64().context("mesh needs positions")? as usize;
            let accessor = self.json["accessors"]
                .as_array()
                .and_then(|accessors| accessors.get(index))
                .context("invalid position accessor")?;
            if accessor["componentType"].as_u64() != Some(5126)
                || accessor["type"].as_str() != Some("VEC3")
                || accessor.get("sparse").is_some()
            {
                bail!("positions must be non-sparse float vectors");
            }
            let count = accessor["count"].as_u64().context("positions need a count")? as usize;
            let view_index = accessor["bufferView"].as_u64().context("positions need a buffer view")? as usize;
            let view = self.json["bufferViews"]
                .as_array()
                .and_then(|views| views.get(view_index))
                .context("invalid position buffer view")?;
            if view["buffer"].as_u64() != Some(0) {
                bail!("positions must use the embedded buffer");
            }
            let start = view["byteOffset"].as_u64().unwrap_or(0) as usize;
            let length = view["byteLength"].as_u64().context("position view needs a length")? as usize;
            let bytes = self
                .bin
                .get(start..start.checked_add(length).context("position view overflow")?)
                .context("position view exceeds buffer")?;
            let offset = accessor["byteOffset"].as_u64().unwrap_or(0) as usize;
            let stride = view["byteStride"].as_u64().unwrap_or(12) as usize;
            if stride < 12 {
                bail!("invalid position stride");
            }
            for n in 0..count {
                let at =
                    n.checked_mul(stride).and_then(|n| n.checked_add(offset)).context("position offset overflow")?;
                let b = bytes
                    .get(at..at.checked_add(12).context("position offset overflow")?)
                    .context("positions exceed their buffer view")?;
                let value = DVec3::new(
                    f32::from_le_bytes(b[0..4].try_into().unwrap()) as f64,
                    f32::from_le_bytes(b[4..8].try_into().unwrap()) as f64,
                    f32::from_le_bytes(b[8..12].try_into().unwrap()) as f64,
                );
                if !value.is_finite() {
                    bail!("position must be finite");
                }
                positions.push(value);
            }
            let idx = primitive["indices"].as_u64().context("mesh needs triangle indices")? as usize;
            let indices = self.json["accessors"]
                .as_array()
                .and_then(|accessors| accessors.get(idx))
                .context("invalid index accessor")?;
            if indices["type"].as_str() != Some("SCALAR") || indices.get("sparse").is_some() {
                bail!("indices must be non-sparse scalars");
            }
            let width = match indices["componentType"].as_u64() {
                Some(5123) => 2usize,
                Some(5125) => 4usize,
                _ => bail!("unsupported index component type"),
            };
            let count = indices["count"].as_u64().context("indices need a count")? as usize;
            if !count.is_multiple_of(3) {
                bail!("indices must form triangles");
            }
            let view_index = indices["bufferView"].as_u64().context("indices need a buffer view")? as usize;
            let view = self.json["bufferViews"]
                .as_array()
                .and_then(|views| views.get(view_index))
                .context("invalid index buffer view")?;
            if view["buffer"].as_u64() != Some(0) {
                bail!("indices must use the embedded buffer");
            }
            let start = view["byteOffset"].as_u64().unwrap_or(0) as usize;
            let len = view["byteLength"].as_u64().context("index view needs a length")? as usize;
            let bytes = self
                .bin
                .get(start..start.checked_add(len).context("index view overflow")?)
                .context("index view exceeds buffer")?;
            let offset = indices["byteOffset"].as_u64().unwrap_or(0) as usize;
            let stride = view["byteStride"].as_u64().unwrap_or(width as u64) as usize;
            if stride < width {
                bail!("invalid index stride");
            }
            let mut corners = Vec::with_capacity(count);
            for n in 0..count {
                let at = n.checked_mul(stride).and_then(|x| x.checked_add(offset)).context("index offset overflow")?;
                let bytes = bytes
                    .get(at..at.checked_add(width).context("index offset overflow")?)
                    .context("indices exceed their view")?;
                let index = if width == 2 {
                    u16::from_le_bytes(bytes.try_into().unwrap()) as usize
                } else {
                    u32::from_le_bytes(bytes.try_into().unwrap()) as usize
                };
                corners.push(*positions.get(index).context("index exceeds positions")?);
            }
            triangles.extend(corners.chunks_exact(3).map(|c| [c[0], c[1], c[2]]));
        }
        if triangles.is_empty() {
            bail!("mesh needs triangles");
        }
        Ok(triangles)
    }

    pub fn rename_node(&mut self, node: usize, name: &str) {
        self.json["nodes"][node]["name"] = json!(name);
    }

    /// The extras of the node named `name`, data an export left for the next.
    pub fn extras(&self, name: &str) -> Result<&Value> {
        Ok(&self.json["nodes"][self.node(name)?]["extras"])
    }

    /// Adds an empty node named `name` under `parent`, at `transform` from it, and returns its index.
    pub fn add_child(&mut self, parent: usize, name: &str, transform: &Trs) -> usize {
        let node = json!({
            "name": name,
            "translation": transform.translation.to_array(),
            "rotation": transform.rotation.to_array(),
            "scale": transform.scale.to_array(),
        });
        let node = push(&mut self.json, "nodes", node);
        push(&mut self.json["nodes"][parent], "children", json!(node));
        node
    }

    /// The default scene's root nodes.
    pub fn roots(&self) -> Vec<usize> {
        let scene = self.json["scene"].as_u64().unwrap_or(0) as usize;
        items(&self.json["scenes"][scene], "nodes").map(index).collect()
    }

    /// Sets `node`'s transform relative to its parent.
    pub fn set_transform(&mut self, node: usize, transform: &Trs) {
        let node = self.json["nodes"][node].as_object_mut().unwrap();
        node.remove("matrix");
        node.insert("translation".into(), json!(transform.translation.to_array()));
        node.insert("rotation".into(), json!(transform.rotation.to_array()));
        node.insert("scale".into(), json!(transform.scale.to_array()));
    }

    /// Keeps only the animation named `name`, renamed `new_name`.
    pub fn keep_animation(&mut self, name: &str, new_name: &str) -> Result<()> {
        let animations = self.json.get_mut("animations").and_then(Value::as_array_mut).context("no animations")?;
        animations.retain(|animation| animation["name"].as_str() == Some(name));
        let animation = animations.first_mut().with_context(|| format!("no animation is named {name}"))?;
        animation["name"] = json!(new_name);
        Ok(())
    }

    /// Each node's parent.
    pub fn parents(&self) -> Vec<Option<usize>> {
        let mut parents = vec![None; items(&self.json, "nodes").count()];
        for (i, node) in items(&self.json, "nodes").enumerate() {
            for child in items(node, "children") {
                parents[index(child)] = Some(i);
            }
        }
        parents
    }

    /// Each node's rest transform, relative to its parent.
    pub fn rest(&self) -> Result<Vec<Trs>> {
        items(&self.json, "nodes")
            .map(|node| {
                if node.get("matrix").is_some() {
                    bail!("node {} has a matrix; only translation, rotation and scale are read", node["name"]);
                }
                let numbers = |key: &str, default: &[f64]| -> Vec<f64> {
                    node.get(key).map_or(default.to_vec(), |v| v.as_array().unwrap().iter().map(number).collect())
                };
                let (t, r, s) = (
                    numbers("translation", &[0.0; 3]),
                    numbers("rotation", &[0., 0., 0., 1.]),
                    numbers("scale", &[1.0; 3]),
                );
                Ok(Trs {
                    translation: DVec3::from_slice(&t),
                    rotation: DQuat::from_slice(&r).normalize(),
                    scale: DVec3::from_slice(&s),
                })
            })
            .collect()
    }

    /// Each node's world matrix, given every node's transform relative to its parent.
    pub fn worlds(&self, locals: &[Trs]) -> Vec<DMat4> {
        let parents = self.parents();
        let mut worlds: Vec<Option<DMat4>> = vec![None; locals.len()];
        fn world(i: usize, locals: &[Trs], parents: &[Option<usize>], worlds: &mut [Option<DMat4>]) -> DMat4 {
            if let Some(known) = worlds[i] {
                return known;
            }
            let parent = parents[i].map_or(DMat4::IDENTITY, |p| world(p, locals, parents, worlds));
            let result = parent * locals[i].matrix();
            worlds[i] = Some(result);
            result
        }
        (0..locals.len()).map(|i| world(i, locals, &parents, &mut worlds)).collect()
    }

    /// The animation named `name`, one frame per key from its first: its frame rate, and every node's transform in each
    /// frame.
    pub fn sample(&self, name: &str) -> Result<(f64, Vec<Vec<Trs>>)> {
        let animation = items(&self.json, "animations")
            .find(|animation| animation["name"].as_str() == Some(name))
            .with_context(|| format!("no animation is named {name}"))?;
        let rest = self.rest()?;
        let mut frames: Vec<Vec<Trs>> = Vec::new();
        let mut fps = 0.0;
        for channel in items(animation, "channels") {
            let sampler = &animation["samplers"][index(&channel["sampler"])];
            if sampler["interpolation"].as_str().unwrap_or("LINEAR") != "LINEAR" {
                bail!("{name}: only linear keys are read");
            }
            let times = self.floats(index(&sampler["input"]))?;
            let values = self.floats(index(&sampler["output"]))?;
            if frames.is_empty() {
                fps = ((times.len() - 1) as f64 / (times[times.len() - 1] - times[0]) as f64).round();
                frames = vec![rest.clone(); times.len()];
            }
            let evenly =
                times.iter().enumerate().all(|(k, &time)| ((time - times[0]) as f64 - k as f64 / fps).abs() < 1e-4);
            if times.len() != frames.len() || !evenly {
                bail!("{name}: every channel needs one key per frame");
            }
            let node = index(&channel["target"]["node"]);
            let width = values.len() / times.len();
            for (frame, value) in frames.iter_mut().zip(values.chunks(width)) {
                let value: Vec<f64> = value.iter().map(|&v| v as f64).collect();
                let trs = &mut frame[node];
                match channel["target"]["path"].as_str() {
                    Some("translation") => trs.translation = DVec3::from_slice(&value),
                    Some("rotation") => trs.rotation = DQuat::from_slice(&value).normalize(),
                    Some("scale") => trs.scale = DVec3::from_slice(&value),
                    path => bail!("{name}: cannot read {path:?} channels"),
                }
            }
        }
        if frames.is_empty() {
            bail!("{name} has no channels");
        }
        Ok((fps, frames))
    }

    /// Adds an animation keyed once per frame at `fps`.
    pub fn add_animation(&mut self, name: &str, fps: f64, tracks: &[(usize, Track)]) {
        let count = tracks.first().map_or(0, |(_, track)| track.len());
        let times: Vec<f32> = (0..count).map(|k| (k as f64 / fps) as f32).collect();
        let input = self.add_floats(&times, "SCALAR", true);
        let (mut samplers, mut channels) = (Vec::new(), Vec::new());
        for (node, track) in tracks {
            let (path, kind, values): (&str, &str, Vec<f32>) = match track {
                Track::Translation(v) => {
                    ("translation", "VEC3", v.iter().flat_map(|p| p.to_array()).map(|x| x as f32).collect())
                }
                Track::Rotation(v) => {
                    ("rotation", "VEC4", v.iter().flat_map(|q| q.to_array()).map(|x| x as f32).collect())
                }
            };
            let output = self.add_floats(&values, kind, false);
            channels.push(json!({ "sampler": samplers.len(), "target": { "node": node, "path": path } }));
            samplers.push(json!({ "input": input, "output": output, "interpolation": "LINEAR" }));
        }
        let animation = json!({ "name": name, "samplers": samplers, "channels": channels });
        match self.json.get_mut("animations").and_then(Value::as_array_mut) {
            Some(animations) => animations.push(animation),
            None => self.json["animations"] = json!([animation]),
        }
    }

    /// Adds `material` and returns its index. Every material is matte: it reflects no light as a mirror would, even
    /// seen at a low angle, so a far road keeps its colour rather than showing the sky. Images repeat across their
    /// mesh's texture positions and are smoothed between their mipmap levels.
    pub fn add_material(&mut self, material: &Material) -> usize {
        if self.json.get("extensionsUsed").is_none() {
            push(&mut self.json, "extensionsUsed", json!("KHR_materials_specular"));
        }
        let mut colour = json!({});
        if let Some(uri) = material.texture {
            if self.json.get("samplers").is_none() {
                // Repeat both ways; linear magnification, and linear between and within mipmap levels.
                push(
                    &mut self.json,
                    "samplers",
                    json!({ "wrapS": 10497, "wrapT": 10497, "magFilter": 9729, "minFilter": 9987 }),
                );
            }
            let image = push(&mut self.json, "images", json!({ "uri": uri }));
            let texture = push(&mut self.json, "textures", json!({ "source": image, "sampler": 0 }));
            colour["baseColorTexture"] = json!({ "index": texture });
        }
        if material.colour != [1.0; 3] {
            let [r, g, b] = material.colour;
            colour["baseColorFactor"] = json!([r, g, b, 1.0]);
        }
        colour["metallicFactor"] = json!(0.0);
        colour["roughnessFactor"] = json!(1.0);
        let mut json = json!({
            "name": material.name,
            "pbrMetallicRoughness": colour,
            "extensions": { "KHR_materials_specular": { "specularFactor": 0.0 } },
        });
        if material.cut_out {
            json["alphaMode"] = json!("MASK");
        }
        if material.two_sided {
            json["doubleSided"] = json!(true);
        }
        push(&mut self.json, "materials", json)
    }

    /// Adds a mesh made of `parts`, each its own triangles and material, and a node named `name` in the default scene
    /// showing it, and returns the node's index.
    pub fn add_mesh(&mut self, name: &str, parts: &[&Mesh]) -> usize {
        let primitives: Vec<Value> = parts.iter().map(|part| self.add_primitive(part)).collect();
        let index = push(&mut self.json, "meshes", json!({ "name": name, "primitives": primitives }));
        let node = push(&mut self.json, "nodes", json!({ "name": name, "mesh": index }));
        self.add_to_scene(node);
        node
    }

    /// Gives `node` `extras`, data for the game.
    pub fn set_extras(&mut self, node: usize, extras: Value) {
        self.json["nodes"][node]["extras"] = extras;
    }

    fn add_primitive(&mut self, mesh: &Mesh) -> Value {
        let mut attributes = json!({
            "POSITION": self.add_floats(&flat(&mesh.positions), "VEC3", true),
            "NORMAL": self.add_floats(&flat(&mesh.normals), "VEC3", false),
        });
        if !mesh.uvs.is_empty() {
            attributes["TEXCOORD_0"] = json!(self.add_floats(&flat(&mesh.uvs), "VEC2", false));
        }
        if !mesh.colours.is_empty() {
            attributes["COLOR_0"] = json!(self.add_floats(&flat(&mesh.colours), "VEC4", false));
        }
        if !mesh.sway.is_empty() {
            attributes["TEXCOORD_1"] = json!(self.add_floats(&flat(&mesh.sway), "VEC2", false));
        }
        let indices = self.add_indices(&mesh.indices);
        json!({ "attributes": attributes, "indices": indices, "material": mesh.material })
    }

    /// Adds an empty node named `name` carrying `extras`, data for the game, to the default scene.
    pub fn add_data(&mut self, name: &str, extras: Value) {
        let node = push(&mut self.json, "nodes", json!({ "name": name, "extras": extras }));
        self.add_to_scene(node);
    }

    /// Adds an empty node named `name` at `translation`, turned by `rotation`, to the default scene.
    pub fn add_marker(&mut self, name: &str, translation: DVec3, rotation: DQuat) {
        let node = json!({ "name": name, "translation": translation.to_array(), "rotation": rotation.to_array() });
        let node = push(&mut self.json, "nodes", node);
        self.add_to_scene(node);
    }

    fn add_to_scene(&mut self, node: usize) {
        if self.json.get("scenes").is_none() {
            self.json["scenes"] = json!([{ "nodes": [] }]);
            self.json["scene"] = json!(0);
        }
        self.json["scenes"][0]["nodes"].as_array_mut().unwrap().push(json!(node));
    }

    fn add_indices(&mut self, indices: &[u32]) -> usize {
        let bytes: Vec<u8> = indices.iter().flat_map(|i| i.to_le_bytes()).collect();
        let view =
            push(&mut self.json, "bufferViews", json!({ "buffer": 0, "byteLength": bytes.len(), "target": 34963 }));
        self.replaced.insert(view, bytes);
        push(
            &mut self.json,
            "accessors",
            json!({ "bufferView": view, "componentType": 5125, "count": indices.len(), "type": "SCALAR" }),
        )
    }

    fn floats(&self, accessor: usize) -> Result<Vec<f32>> {
        let accessor = &self.json["accessors"][accessor];
        let width = match accessor["type"].as_str() {
            Some("SCALAR") => 1,
            Some("VEC3") => 3,
            Some("VEC4") => 4,
            kind => bail!("cannot read {kind:?} accessors"),
        };
        let view = &self.json["bufferViews"][index(&accessor["bufferView"])];
        if accessor["componentType"] != 5126 || view.get("byteStride").is_some_and(|stride| stride != width * 4) {
            bail!("only tightly packed float accessors are read");
        }
        let start = accessor["byteOffset"].as_u64().unwrap_or(0) as usize;
        let bytes = &self.view(index(&accessor["bufferView"]))[start..start + index(&accessor["count"]) * width * 4];
        Ok(bytes.chunks(4).map(|b| f32::from_le_bytes(b.try_into().unwrap())).collect())
    }

    fn add_floats(&mut self, values: &[f32], kind: &str, bounds: bool) -> usize {
        let views = self.json.as_object_mut().unwrap().entry("bufferViews").or_insert(json!([]));
        let view = views.as_array().unwrap().len();
        views.as_array_mut().unwrap().push(json!({ "buffer": 0, "byteLength": values.len() * 4 }));
        self.replaced.insert(view, values.iter().flat_map(|v| v.to_le_bytes()).collect());
        let width = match kind {
            "SCALAR" => 1,
            "VEC2" => 2,
            "VEC3" => 3,
            _ => 4,
        };
        let mut accessor =
            json!({ "bufferView": view, "componentType": 5126, "count": values.len() / width, "type": kind });
        if bounds {
            let columns = |pick: fn(f32, f32) -> f32| -> Vec<f32> {
                (0..width).map(|c| values.iter().skip(c).step_by(width).copied().reduce(pick).unwrap()).collect()
            };
            accessor["min"] = json!(columns(f32::min));
            accessor["max"] = json!(columns(f32::max));
        }
        let accessors = self.json.as_object_mut().unwrap().entry("accessors").or_insert(json!([]));
        accessors.as_array_mut().unwrap().push(accessor);
        accessors.as_array().unwrap().len() - 1
    }

    fn view(&self, index: usize) -> &[u8] {
        if let Some(bytes) = self.replaced.get(&index) {
            return bytes;
        }
        let view = &self.json["bufferViews"][index];
        let start = view["byteOffset"].as_u64().unwrap_or(0) as usize;
        &self.bin[start..start + view["byteLength"].as_u64().unwrap() as usize]
    }

    /// The JSON without unreferenced accessors and buffer views, and one fresh buffer holding the rest.
    fn repack(&self) -> Result<(Value, Vec<u8>)> {
        let mut gltf = self.json.clone();

        let mut kept = BTreeSet::new();
        for_each_accessor_ref(&mut gltf, |reference| {
            kept.insert(index(reference));
        });
        let accessors = gltf.get("accessors").and_then(Value::as_array).cloned().unwrap_or_default();
        if kept.iter().any(|&i| accessors[i].get("sparse").is_some()) {
            bail!("sparse accessors are not supported");
        }
        let accessor_map: BTreeMap<usize, usize> = kept.iter().enumerate().map(|(new, &old)| (old, new)).collect();
        for_each_accessor_ref(&mut gltf, |reference| *reference = json!(accessor_map[&index(reference)]));
        gltf["accessors"] = Value::Array(kept.iter().map(|&i| accessors[i].clone()).collect());

        let old_views: BTreeSet<usize> = view_holders(&mut gltf).map(|holder| index(&holder["bufferView"])).collect();
        let (mut views, mut data, mut view_map) = (Vec::new(), Vec::new(), BTreeMap::new());
        for old in old_views {
            data.resize(data.len().next_multiple_of(4), 0);
            let bytes = self.view(old);
            let mut view = gltf["bufferViews"][old].clone();
            let fields = view.as_object_mut().unwrap();
            fields.remove("byteOffset");
            fields.insert("buffer".into(), json!(0));
            fields.insert("byteOffset".into(), json!(data.len()));
            fields.insert("byteLength".into(), json!(bytes.len()));
            view_map.insert(old, views.len());
            views.push(view);
            data.extend_from_slice(bytes);
        }
        for holder in view_holders(&mut gltf) {
            holder["bufferView"] = json!(view_map[&index(&holder["bufferView"])]);
        }
        gltf["bufferViews"] = Value::Array(views);
        gltf["buffers"] = if data.is_empty() { json!([]) } else { json!([{ "byteLength": data.len() }]) };
        Ok((gltf, data))
    }
}

/// Calls `visit` on every value that is an accessor index.
fn for_each_accessor_ref(gltf: &mut Value, mut visit: impl FnMut(&mut Value)) {
    for mesh in items_mut(gltf, "meshes") {
        for primitive in items_mut(mesh, "primitives") {
            primitive["attributes"].as_object_mut().unwrap().values_mut().for_each(&mut visit);
            if let Some(indices) = primitive.get_mut("indices") {
                visit(indices);
            }
            for target in items_mut(primitive, "targets") {
                target.as_object_mut().unwrap().values_mut().for_each(&mut visit);
            }
        }
    }
    for skin in items_mut(gltf, "skins") {
        if let Some(matrices) = skin.get_mut("inverseBindMatrices") {
            visit(matrices);
        }
    }
    for animation in items_mut(gltf, "animations") {
        for sampler in items_mut(animation, "samplers") {
            visit(&mut sampler["input"]);
            visit(&mut sampler["output"]);
        }
    }
}

/// The accessors and images that store their bytes in a buffer view.
fn view_holders(gltf: &mut Value) -> impl Iterator<Item = &mut Value> {
    let object = gltf.as_object_mut().unwrap();
    let mut holders = Vec::new();
    for (key, value) in object.iter_mut() {
        if key == "accessors" || key == "images" {
            holders
                .extend(value.as_array_mut().unwrap().iter_mut().filter(|holder| holder.get("bufferView").is_some()));
        }
    }
    holders.into_iter()
}

/// Appends `item` to the array `key` of `gltf`, making the array if needed, and returns its index.
fn push(gltf: &mut Value, key: &str, item: Value) -> usize {
    let array = gltf.as_object_mut().unwrap().entry(key).or_insert(json!([])).as_array_mut().unwrap();
    array.push(item);
    array.len() - 1
}

fn flat<const N: usize>(values: &[[f32; N]]) -> Vec<f32> {
    values.iter().flatten().copied().collect()
}

/// Triangles to add with [`Glb::add_mesh`]: per vertex a position, a normal, and optionally texture coordinates and
/// a linear colour that multiplies the material's; three indices per triangle, counter-clockwise seen from the front.
#[derive(Clone, Default)]
pub struct Mesh {
    pub positions: Vec<[f32; 3]>,
    pub normals: Vec<[f32; 3]>,
    pub uvs: Vec<[f32; 2]>,
    pub colours: Vec<[f32; 4]>,
    /// How each vertex moves in the wind, for a mesh that sways: how far it bends, in metres, and the phase of its
    /// part (a leaf card or a blade), from 0 to 1, so neighbouring parts flutter out of step, or -1 for wood, which
    /// does not flutter. Written as a second set
    /// of texture coordinates, which the game's wind material reads.
    pub sway: Vec<[f32; 2]>,
    pub indices: Vec<u32>,
    pub material: usize,
}

/// How a surface looks, for [`Glb::add_material`].
pub struct Material<'a> {
    pub name: &'a str,
    /// The image it shows, by its URI relative to the file.
    pub texture: Option<&'a str>,
    /// Its linear colour, which multiplies the image.
    pub colour: [f64; 3],
    /// Whether it is cut out where its image is less than half opaque.
    pub cut_out: bool,
    /// Whether it shows from both sides.
    pub two_sided: bool,
}

impl<'a> Material<'a> {
    /// A material showing the image at `uri`, opaque and seen from the front.
    pub fn textured(name: &'a str, uri: &'a str) -> Self {
        Self { name, texture: Some(uri), colour: [1.0; 3], cut_out: false, two_sided: false }
    }
}

/// A vector of a frame with z up (x east, y north) in glTF's, with y up (x east, z south).
pub fn y_up(v: DVec3) -> DVec3 {
    DVec3::new(v.x, v.z, -v.y)
}

fn items<'a>(value: &'a Value, key: &str) -> impl Iterator<Item = &'a Value> {
    value.get(key).and_then(Value::as_array).into_iter().flatten()
}

fn items_mut<'a>(value: &'a mut Value, key: &str) -> impl Iterator<Item = &'a mut Value> {
    value.get_mut(key).and_then(Value::as_array_mut).into_iter().flatten()
}

fn index(value: &Value) -> usize {
    value.as_u64().expect("a glTF index") as usize
}

fn u32_at(data: &[u8], offset: usize) -> u32 {
    u32::from_le_bytes(data[offset..offset + 4].try_into().unwrap())
}

fn chunk(kind: &[u8; 4], content: &[u8]) -> Vec<u8> {
    let mut out = (content.len() as u32).to_le_bytes().to_vec();
    out.extend_from_slice(kind);
    out.extend_from_slice(content);
    out
}

fn number(value: &Value) -> f64 {
    value.as_f64().expect("a glTF number")
}

/// A node's transform relative to its parent.
#[derive(Clone, Copy)]
pub struct Trs {
    pub translation: DVec3,
    pub rotation: DQuat,
    pub scale: DVec3,
}

impl Trs {
    pub fn matrix(&self) -> DMat4 {
        DMat4::from_scale_rotation_translation(self.scale, self.rotation, self.translation)
    }
}

/// One node's keys in an animation, one per frame.
pub enum Track {
    Translation(Vec<DVec3>),
    Rotation(Vec<DQuat>),
}

impl Track {
    fn len(&self) -> usize {
        match self {
            Track::Translation(keys) => keys.len(),
            Track::Rotation(keys) => keys.len(),
        }
    }
}
