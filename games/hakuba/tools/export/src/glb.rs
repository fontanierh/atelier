//! Reading, editing and writing binary glTF (.glb) files.
//!
//! Edits change the JSON and record new bytes for buffer views; [`Glb::write`] packs only what is still referenced,
//! so removed accessors and replaced images leave nothing behind in the file.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs;
use std::io::Cursor;
use std::path::Path;

use anyhow::{Context, Result, bail};
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
                let moved: Vec<f64> = translation.as_array().unwrap().iter().map(|t| t.as_f64().unwrap() * factor).collect();
                *translation = json!(moved);
            }
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
        let views: Vec<usize> = items(&self.json, "images").filter_map(|image| image.get("bufferView")).map(index).collect();
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
            resized.write_with_encoder(PngEncoder::new_with_quality(&mut out, CompressionType::Best, FilterType::Adaptive))?;
            self.replaced.insert(view, out);
        }
        Ok(())
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
        let accessors = gltf["accessors"].as_array().unwrap().clone();
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
            holders.extend(value.as_array_mut().unwrap().iter_mut().filter(|holder| holder.get("bufferView").is_some()));
        }
    }
    holders.into_iter()
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
