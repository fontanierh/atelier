//! Importing a self-contained static prop, including an optional separate collision mesh.

use std::fs;
use std::path::{Component, Path, PathBuf};

use anyhow::{Context, Result, bail, ensure};
use glam::{DQuat, DVec3};
use serde_json::{Value, json};

use crate::glb::{Glb, Mesh, y_up};

/// @cc [owner:fontanierh,label:correctness] static-source-prop
/// A source prop preserves its bind-pose geometry and only uses declared texture assets and its own declared textures
/// (`own`, each named by its file beside the export). Painted motion weights MUST have valid explicit motion
/// parameters; the exporter MUST preserve those weights and parameters.
pub(super) fn export(
    source: &str,
    solid: bool,
    textures: &[String],
    own: &[String],
    anchors: &[[f64; 3]],
    output: &Path,
) -> Result<()> {
    export_inner(source, solid, textures, own, anchors, None, output)
}

pub(super) fn export_foliage(
    source: &str,
    textures: &[String],
    profile: Value,
    surface_height: Option<f32>,
    shadow_distance: Option<f32>,
    output: &Path,
) -> Result<()> {
    export_inner(
        source,
        false,
        textures,
        &[],
        &[],
        Some(FoliageExport { profile, surface_height, shadow_distance }),
        output,
    )
}

struct FoliageExport {
    profile: Value,
    surface_height: Option<f32>,
    shadow_distance: Option<f32>,
}

fn export_inner(
    source: &str,
    solid: bool,
    textures: &[String],
    own: &[String],
    anchors: &[[f64; 3]],
    profile: Option<FoliageExport>,
    output: &Path,
) -> Result<()> {
    let path = Path::new(source);
    ensure!(path.extension().is_some_and(|ext| ext == "glb"), "source must be a GLB in src/");
    let mut parts = path.components();
    ensure!(matches!(parts.next(), Some(Component::Normal(p)) if p == "src"), "source must be in src/");
    ensure!(parts.all(|part| matches!(part, Component::Normal(_))), "source path must stay in src/");
    ensure!(
        path.components().all(|part| match part {
            Component::Normal(name) => name.to_str().is_some_and(|name| !name.starts_with('.') && name != "target"),
            _ => false,
        }),
        "source path must be covered by the asset checksum"
    );
    let folder = output.parent().context("source model has no asset folder")?;
    let asset = folder.canonicalize().context("reading asset folder")?;
    let root = folder.join("src").canonicalize().context("reading source folder")?;
    ensure!(root.starts_with(&asset), "source folder must stay in the asset folder");
    let file = folder.join(path).canonicalize().context("reading source model")?;
    ensure!(file.starts_with(root), "source path must stay in src/");
    let bytes = fs::read(&file).context("reading source model")?;
    let mut allowed: Vec<String> = textures
        .iter()
        .map(|name| {
            ensure!(
                !name.is_empty() && name.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-'),
                "texture name must be kebab case"
            );
            crate::uri_of_texture(name)
        })
        .collect::<Result<_>>()?;
    allowed.extend(own.iter().cloned());
    let foliage = profile.as_ref().map(|_| allowed.as_slice());
    let surface_height = profile.as_ref().and_then(|p| p.surface_height);
    let (value, collision) = validate_kind(&bytes, foliage, surface_height, &allowed)?;
    ensure!(!collision || solid, "a collision mesh requires solid = true");
    let mut glb = Glb::read(&file)?;
    let full = glb.node("full")?;
    let mut extras = value["nodes"][full]["extras"].as_object().cloned().unwrap_or_default();
    extras.remove("solid");
    if solid && !collision {
        extras.insert("solid".into(), json!(true));
    }
    if foliage.is_some() {
        let settings = profile.as_ref().context("missing foliage profile")?;
        extras.insert("source_foliage".into(), settings.profile.clone());
        if let Some(distance) = settings.shadow_distance {
            extras.insert("shadow_distance_m".into(), json!(distance));
        }
    }
    glb.set_extras(full, extras.into());
    for level in ["middle", "far"] {
        if foliage.is_none() || !value["nodes"].as_array().is_some_and(|nodes| nodes.iter().any(|n| n["name"] == level))
        {
            continue;
        }
        let node = glb.node(level)?;
        let mut extras = value["nodes"][node]["extras"].as_object().cloned().unwrap_or_default();
        let settings = profile.as_ref().context("missing foliage profile")?;
        extras.insert("source_foliage".into(), settings.profile.clone());
        // Only a full tile casts the middle version's shadow; a far version is seen and casts its own.
        if level == "middle" {
            extras.insert("shadow_alpha_textures".into(), shadow_alpha_textures(&value, node)?);
        }
        if let Some(distance) = settings.shadow_distance {
            extras.insert("shadow_distance_m".into(), json!(distance));
        }
        glb.set_extras(node, extras.into());
    }
    for (k, &anchor) in anchors.iter().enumerate() {
        ensure!(
            anchor.iter().all(|v| v.is_finite() && (*v as f32).is_finite()),
            "source anchor must be finite at stored precision"
        );
        glb.add_marker(&format!("anchor {k}"), y_up(DVec3::from_array(anchor)), DQuat::IDENTITY);
    }
    glb.write(output)?;
    if foliage.is_none() {
        let mut extras = value["nodes"][full]["extras"].as_object().cloned().unwrap_or_default();
        extras.remove("solid");
        write_middle(&value, binary(&bytes), full, extras.into(), &middle_path(output))?;
    }
    Ok(())
}

/// Where a source prop's middle version is written: beside its export, as `<name>.middle.glb`.
pub(crate) fn middle_path(output: &Path) -> PathBuf {
    output.with_extension("middle.glb")
}

/// How many triangles a middle version keeps in all, for a model `size_m` across: enough for its outline from the
/// distance where full detail ends.
fn middle_triangles(size_m: f32) -> usize {
    (16.0 * size_m).clamp(48.0, 1500.0) as usize
}

/// Writes the version a middle tile shows: a node `middle`, the `full` node's parts each simplified, regardless of
/// their topology, to its share of [`middle_triangles`], with the source's materials and `extras`. It holds no
/// collision, so nothing far away is solid.
fn write_middle(value: &Value, binary: &[u8], full: usize, extras: Value, path: &Path) -> Result<()> {
    let mesh = value["nodes"][full]["mesh"].as_u64().context("the full node has no mesh")? as usize;
    let parts = value["meshes"][mesh]["primitives"]
        .as_array()
        .context("the full mesh has no primitives")?
        .iter()
        .map(|primitive| part(value, binary, primitive))
        .collect::<Result<Vec<_>>>()?;
    let (low, high) = parts
        .iter()
        .flat_map(|part| &part.positions)
        .fold((glam::Vec3::splat(f32::MAX), glam::Vec3::splat(f32::MIN)), |(low, high), &p| {
            (low.min(p.into()), high.max(p.into()))
        });
    let budget = middle_triangles((high - low).max_element());
    let total: usize = parts.iter().map(|part| part.indices.len() / 3).sum();
    let mut simplified: Vec<Mesh> =
        parts.iter().map(|part| simplify(part, budget * part.indices.len() / 3 / total)).collect();
    simplified.retain(|part| !part.indices.is_empty());
    if simplified.is_empty() {
        simplified = parts;
    }
    let mut document = json!({ "asset": { "version": "2.0" } });
    for key in ["materials", "textures", "images", "samplers", "extensionsUsed"] {
        if let Some(entry) = value.get(key) {
            document[key] = entry.clone();
        }
    }
    let mut glb = Glb::from_json(document);
    let node = glb.add_mesh("middle", &simplified.iter().collect::<Vec<_>>());
    glb.set_extras(node, extras);
    glb.write(path)
}

/// A validated source primitive's vertices and triangles.
fn part(value: &Value, binary: &[u8], primitive: &Value) -> Result<Mesh> {
    let floats = |key: &str| -> Result<Option<(Vec<f32>, &str)>> {
        let Some(index) = primitive["attributes"][key].as_u64() else { return Ok(None) };
        let (data, _, (_, kind)) = accessor(value, binary, index as usize)?;
        Ok(Some((data.chunks_exact(4).map(|v| f32::from_le_bytes(v.try_into().unwrap())).collect(), kind)))
    };
    let triples = |values: Vec<f32>| values.chunks_exact(3).map(|v| [v[0], v[1], v[2]]).collect::<Vec<_>>();
    let (positions, _) = floats("POSITION")?.context("a source primitive has no positions")?;
    let (normals, _) = floats("NORMAL")?.context("a source primitive has no normals")?;
    let uvs = floats("TEXCOORD_0")?.map_or_else(Vec::new, |(v, _)| v.chunks_exact(2).map(|v| [v[0], v[1]]).collect());
    let colours = match floats("COLOR_0")? {
        Some((v, "VEC3")) => v.chunks_exact(3).map(|v| [v[0], v[1], v[2], 1.0]).collect(),
        Some((v, _)) => v.chunks_exact(4).map(|v| [v[0], v[1], v[2], v[3]]).collect(),
        None => Vec::new(),
    };
    let index = primitive["indices"].as_u64().context("a source primitive has no indices")? as usize;
    let (data, _, (component, _)) = accessor(value, binary, index)?;
    let indices = if component == 5123 {
        data.chunks_exact(2).map(|v| u32::from(u16::from_le_bytes(v.try_into().unwrap()))).collect()
    } else {
        data.chunks_exact(4).map(|v| u32::from_le_bytes(v.try_into().unwrap())).collect()
    };
    let material = primitive["material"].as_u64().unwrap_or(0) as usize;
    Ok(Mesh {
        positions: triples(positions),
        normals: triples(normals),
        uvs,
        colours,
        sway: Vec::new(),
        indices,
        material,
    })
}

/// `part` with at most `triangles` triangles, its unused vertices dropped.
fn simplify(part: &Mesh, triangles: usize) -> Mesh {
    if part.indices.len() / 3 <= triangles {
        return part.clone();
    }
    let bytes: Vec<u8> = part.positions.iter().flatten().flat_map(|v| v.to_le_bytes()).collect();
    let Ok(vertices) = meshopt::VertexDataAdapter::new(&bytes, 12, 0) else { return part.clone() };
    let kept = meshopt::simplify_sloppy(&part.indices, &vertices, triangles * 3, f32::MAX, None);
    let mut remap = vec![u32::MAX; part.positions.len()];
    let mut out = Mesh { material: part.material, ..Mesh::default() };
    for &i in &kept {
        let i = i as usize;
        if remap[i] == u32::MAX {
            remap[i] = out.positions.len() as u32;
            out.positions.push(part.positions[i]);
            out.normals.push(part.normals[i]);
            if !part.uvs.is_empty() {
                out.uvs.push(part.uvs[i]);
            }
            if !part.colours.is_empty() {
                out.colours.push(part.colours[i]);
            }
        }
        out.indices.push(remap[i]);
    }
    out
}

/// A validated source GLB's binary chunk.
fn binary(bytes: &[u8]) -> &[u8] {
    let json_len = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
    &bytes[20 + json_len + 8..]
}

/// Each masked primitive of a plant's middle version names its exported alpha companion relative to the asset root.
pub(super) fn shadow_alpha_textures(value: &Value, node: usize) -> Result<Value> {
    let mesh = value["nodes"][node]["mesh"].as_u64().context("lower foliage detail needs a mesh")? as usize;
    let primitives = value["meshes"][mesh]["primitives"].as_array().context("foliage needs primitives")?;
    let mut result = Vec::with_capacity(primitives.len());
    for primitive in primitives {
        let material = primitive["material"].as_u64().context("foliage needs a material")? as usize;
        let material = &value["materials"][material];
        if material["alphaMode"] != "MASK" {
            result.push(Value::Null);
            continue;
        }
        let texture = material["pbrMetallicRoughness"]["baseColorTexture"]["index"]
            .as_u64()
            .context("masked foliage needs a base colour texture")? as usize;
        let image = value["textures"][texture]["source"].as_u64().context("texture needs an image")? as usize;
        let uri = value["images"][image]["uri"].as_str().context("texture needs a URI")?;
        let relative = uri
            .strip_prefix("../../textures/")
            .and_then(|s| s.strip_suffix(".ktx2"))
            .context("shadow texture URI must name an exported texture")?;
        ensure!(
            relative.split('/').count() == 2 && relative.split('/').all(|s| !s.is_empty() && s != "." && s != ".."),
            "invalid shadow texture URI"
        );
        result.push(json!(format!("textures/{relative}.alpha.ktx2")));
    }
    Ok(Value::Array(result))
}

/// Reads the restricted static GLB layout accepted by source props, and checks actual bytes, not just bounds metadata.
#[cfg(test)]
fn validate(bytes: &[u8]) -> Result<(Value, bool)> {
    validate_kind(bytes, None, None, &[])
}

#[cfg(test)]
fn validate_with_textures(bytes: &[u8], allowed: &[String]) -> Result<(Value, bool)> {
    validate_kind(bytes, None, None, allowed)
}

fn validate_kind(
    bytes: &[u8],
    foliage: Option<&[String]>,
    surface_height: Option<f32>,
    allowed: &[String],
) -> Result<(Value, bool)> {
    let u32_at = |offset: usize| -> Result<usize> {
        let b = bytes.get(offset..offset + 4).context("truncated source GLB")?;
        Ok(u32::from_le_bytes(b.try_into().unwrap()) as usize)
    };
    ensure!(
        bytes.get(0..4) == Some(b"glTF") && u32_at(4)? == 2 && u32_at(8)? == bytes.len(),
        "invalid source GLB header"
    );
    let json_len = u32_at(12)?;
    ensure!(bytes.get(16..20) == Some(b"JSON"), "source GLB needs a JSON chunk");
    let json_end = 20usize.checked_add(json_len).context("invalid JSON size")?;
    let value: Value = serde_json::from_slice(bytes.get(20..json_end).context("truncated JSON")?)?;
    let bin_len = u32_at(json_end)?;
    ensure!(bytes.get(json_end + 4..json_end + 8) == Some(b"BIN\0"), "source GLB needs embedded binary data");
    let start = json_end.checked_add(8).context("invalid binary offset")?;
    let end = start.checked_add(bin_len).context("invalid binary size")?;
    ensure!(end == bytes.len(), "source GLB must have only JSON and binary chunks");
    let binary = &bytes[start..end];
    let array =
        |key: &str| -> Result<&Vec<Value>> { value[key].as_array().with_context(|| format!("source GLB needs {key}")) };
    let buffers = array("buffers")?;
    ensure!(buffers.len() == 1 && buffers[0].get("uri").is_none(), "source buffers must be embedded");
    let buffer_len = buffers[0]["byteLength"].as_u64().context("source buffer needs a length")? as usize;
    ensure!(buffer_len <= binary.len() && binary.len() - buffer_len <= 3, "invalid source buffer length");
    let binary = &binary[..buffer_len];
    if allowed.is_empty() {
        ensure!(value.get("images").is_none() && value.get("textures").is_none(), "source textures are not supported");
    } else {
        let images = array("images")?;
        ensure!(!images.is_empty(), "source needs named textures");
        for image in images {
            let uri = image["uri"].as_str().context("source texture needs an asset URI")?;
            ensure!(image.get("bufferView").is_none(), "source texture must not embed image data");
            ensure!(allowed.iter().any(|name| name == uri), "undeclared source texture: {uri}");
        }
        for texture in array("textures")? {
            ensure!(texture["source"].as_u64().is_some_and(|i| (i as usize) < images.len()), "invalid source texture");
        }
    }
    ensure!(value.get("animations").is_none() && value.get("skins").is_none(), "source must be static");
    let nodes = array("nodes")?;
    let meshes = array("meshes")?;
    let materials = value.get("materials").and_then(Value::as_array);
    if let Some(materials) = materials {
        for material in materials {
            let mut other = material.clone();
            if let Some(pbr) = other["pbrMetallicRoughness"].as_object_mut() {
                let base = pbr.remove("baseColorTexture");
                if foliage.is_some() {
                    ensure!(base.is_some(), "foliage material needs a named base color texture");
                }
                if let Some(base) = base {
                    let i = base["index"].as_u64().context("source texture needs an index")? as usize;
                    ensure!(i < value["textures"].as_array().map_or(0, Vec::len), "invalid source material texture");
                    ensure!(base.get("texCoord").is_none_or(|v| v.as_u64() == Some(0)), "source texture needs UV0");
                }
            } else {
                ensure!(foliage.is_none(), "foliage material needs a named base color texture");
            }
            ensure!(!has_texture(&other), "unsupported source texture channel");
        }
    }
    let scenes = array("scenes")?;
    ensure!(scenes.len() == 1 && value["scene"].as_u64().unwrap_or(0) == 0, "source must have one scene");
    let roots = scenes[0]["nodes"].as_array().context("source scene has no roots")?;
    // A prop has `full` and an optional `collision`; a plant `full` and an optional `middle` and `far`.
    let most = if foliage.is_some() { 3 } else { 2 };
    ensure!(
        nodes.len() == roots.len() && (1..=most).contains(&nodes.len()),
        "source needs full and optional collision roots, or a plant's optional middle and far"
    );
    let mut seen = Vec::new();
    let mut seen_meshes = Vec::new();
    let mut lowest = f64::INFINITY;
    for root in roots {
        let index = root.as_u64().context("invalid source root")? as usize;
        let node = nodes.get(index).context("invalid source root")?;
        ensure!(node.get("extras").is_none_or(Value::is_object), "source extras must be an object");
        let name = node["name"].as_str().context("source root needs a name")?;
        let vertex_paint = name == "full" && node["extras"].get("vertex_paint").is_some();
        let motion = node["extras"].get("vertex_motion");
        if let Some(motion) = motion {
            ensure!(vertex_paint && valid_motion(motion), "painted motion needs valid parameters on the full node");
        }
        if vertex_paint {
            ensure!(node["extras"]["vertex_paint"].is_object(), "vertex paint extras must be an object");
        }
        ensure!(
            (name == "full"
                || (foliage.is_none() && name == "collision")
                || (foliage.is_some() && matches!(name, "middle" | "far")))
                && !seen.contains(&name),
            "source roots must be full and optional collision, or a plant's optional middle and far"
        );
        seen.push(name);
        ensure!(
            ["children", "translation", "rotation", "scale", "matrix", "skin"]
                .iter()
                .all(|key| node.get(key).is_none()),
            "source roots must use the identity frame"
        );
        let mesh_index = node["mesh"].as_u64().context("source root needs a mesh")? as usize;
        ensure!(!seen_meshes.contains(&mesh_index), "source roots must have separate meshes");
        seen_meshes.push(mesh_index);
        let mesh = meshes.get(mesh_index).context("invalid source mesh")?;
        let primitives = mesh["primitives"].as_array().context("source mesh needs primitives")?;
        ensure!(!primitives.is_empty(), "source mesh has no primitives");
        for primitive in primitives {
            ensure!(
                primitive["mode"].as_u64().unwrap_or(4) == 4 && primitive.get("targets").is_none(),
                "source must contain static triangles"
            );
            ensure!(primitive.get("extensions").is_none(), "compressed source primitives are unsupported");
            if let Some(material) = primitive.get("material") {
                let index = material.as_u64().context("invalid source material")? as usize;
                ensure!(materials.is_some_and(|m| index < m.len()), "invalid source material");
                let mode = materials.unwrap()[index]["alphaMode"].as_str().unwrap_or("OPAQUE");
                ensure!(
                    foliage.is_some() || name != "full" || mode == "OPAQUE" || mode == "BLEND",
                    "source cut-outs are unsupported"
                );
                if foliage.is_some() {
                    ensure!(mode == "OPAQUE" || mode == "MASK", "foliage must be opaque or masked");
                    if mode == "MASK" {
                        let mat = &materials.unwrap()[index];
                        ensure!(
                            mat["alphaCutoff"].as_f64().is_some_and(|x| x.is_finite() && x > 0.0 && x <= 1.0),
                            "masked foliage needs a valid alpha cutoff"
                        );
                        ensure!(mat["doubleSided"].as_bool() == Some(true), "masked foliage must be double sided");
                    }
                }
                if vertex_paint {
                    ensure!(mode == "OPAQUE", "static vertex paint needs an opaque material");
                }
            } else {
                ensure!(!vertex_paint && foliage.is_none(), "source profile needs a material");
            }
            let attributes = primitive["attributes"].as_object().context("source needs vertex attributes")?;
            if let Some(index) = primitive["material"].as_u64() {
                let textured =
                    materials.unwrap()[index as usize]["pbrMetallicRoughness"].get("baseColorTexture").is_some();
                ensure!(!textured || attributes.contains_key("TEXCOORD_0"), "textured source needs UV0");
            }
            ensure!(!vertex_paint || attributes.contains_key("COLOR_0"), "vertex paint requires source colors");
            if foliage.is_some() {
                ensure!(
                    ["POSITION", "NORMAL", "TEXCOORD_0", "COLOR_0"].iter().all(|key| attributes.contains_key(*key)),
                    "foliage needs position, normal, UV and colors"
                );
            }
            ensure!(
                attributes.keys().all(|key| matches!(key.as_str(), "POSITION" | "NORMAL" | "TEXCOORD_0" | "COLOR_0")),
                "unsupported source attribute"
            );
            let pos = attributes.get("POSITION").and_then(Value::as_u64).context("source needs positions")? as usize;
            let (positions, count, kind) = accessor(&value, binary, pos)?;
            ensure!(kind == (5126, "VEC3") && count > 0, "source positions must be floats");
            let mut points = Vec::with_capacity(count);
            for p in positions.chunks_exact(12) {
                let f = |at: usize| f32::from_le_bytes(p[at..at + 4].try_into().unwrap());
                let point = [f(0), f(4), f(8)];
                ensure!(point.iter().all(|x| x.is_finite()), "source positions must be finite");
                points.push(DVec3::new(point[0] as f64, point[1] as f64, point[2] as f64));
            }
            for (key, index) in attributes {
                if key == "POSITION" {
                    continue;
                }
                let (data, n, kind) = accessor(&value, binary, index.as_u64().context("invalid attribute")? as usize)?;
                ensure!(
                    n == count
                        && kind.0 == 5126
                        && match key.as_str() {
                            "NORMAL" => kind.1 == "VEC3",
                            "TEXCOORD_0" => kind.1 == "VEC2",
                            "COLOR_0" => kind.1 == "VEC4" || (foliage.is_none() && kind.1 == "VEC3"),
                            _ => false,
                        },
                    "unsupported source attribute format"
                );
                ensure!(
                    data.chunks_exact(4).all(|v| f32::from_le_bytes(v.try_into().unwrap()).is_finite()),
                    "source attributes must be finite"
                );
                if key == "COLOR_0" && vertex_paint {
                    ensure!(
                        kind.1 == "VEC4"
                            && data.chunks_exact(16).all(|v| {
                                let channel = |at: usize| f32::from_le_bytes(v[at..at + 4].try_into().unwrap());
                                let weight = channel(12);
                                [0, 4, 8].iter().all(|&at| (0.0..=1.0).contains(&channel(at)))
                                    && weight.is_finite()
                                    && (0.0..=1.0).contains(&weight)
                                    && (motion.is_some() || weight == 0.0)
                            }),
                        "vertex paint needs colours in [0, 1], valid alpha weights and an explicit motion profile"
                    );
                }
            }
            let idx = primitive["indices"].as_u64().context("source needs triangle indices")? as usize;
            let (indices, n, kind) = accessor(&value, binary, idx)?;
            ensure!(
                kind.1 == "SCALAR" && (kind.0 == 5123 || kind.0 == 5125) && n > 0 && n % 3 == 0,
                "source needs unsigned triangle indices"
            );
            let indices: Vec<usize> = if kind.0 == 5123 {
                indices.chunks_exact(2).map(|v| u16::from_le_bytes(v.try_into().unwrap()) as usize).collect()
            } else {
                indices.chunks_exact(4).map(|v| u32::from_le_bytes(v.try_into().unwrap()) as usize).collect()
            };
            ensure!(indices.iter().all(|&i| i < count), "source index is outside its positions");
            for triangle in indices.chunks_exact(3) {
                let [a, b, c] = [points[triangle[0]], points[triangle[1]], points[triangle[2]]];
                ensure!((b - a).cross(c - a).length_squared() > 0.0, "source triangles must have area");
                if name == "full" {
                    lowest = lowest.min(a.y).min(b.y).min(c.y);
                }
            }
        }
    }
    ensure!(seen.contains(&"full"), "source requires a full mesh");
    if let Some(height) = surface_height {
        ensure!(foliage.is_some() && height.is_finite() && height >= 0.0, "invalid surface height");
        ensure!(lowest == f64::from(height), "source surface does not match its declared height");
    } else {
        ensure!(lowest < 0.0, "full mesh must reach below its foot");
    }
    ensure!(seen_meshes.len() == meshes.len(), "source cannot contain unused meshes");
    let collision = seen.contains(&"collision");
    Ok((value, collision))
}

fn valid_motion(value: &Value) -> bool {
    let Some(object) = value.as_object() else { return false };
    if object.len() != 4 {
        return false;
    }
    let finite = |v: &Value| v.as_f64().is_some_and(|x| x.is_finite() && x.abs() <= 10_000.0);
    let array = |name: &str, size: usize| {
        object.get(name).and_then(Value::as_array).is_some_and(|v| v.len() == size && v.iter().all(finite))
    };
    object.get("rate").is_some_and(finite) && array("spatial", 2) && array("amplitude", 3) && array("harmonic", 3)
}

fn accessor<'a>(value: &'a Value, binary: &'a [u8], index: usize) -> Result<(&'a [u8], usize, (u64, &'a str))> {
    let a = value["accessors"].as_array().and_then(|items| items.get(index)).context("invalid source accessor")?;
    ensure!(a.get("sparse").is_none(), "sparse source accessors are unsupported");
    let count = a["count"].as_u64().context("source accessor needs a count")? as usize;
    let component = a["componentType"].as_u64().context("source accessor needs a component type")?;
    let kind = a["type"].as_str().context("source accessor needs a type")?;
    let width = match kind {
        "SCALAR" => 1,
        "VEC2" => 2,
        "VEC3" => 3,
        "VEC4" => 4,
        _ => bail!("unsupported source accessor type"),
    };
    let size = match component {
        5123 => 2,
        5125 | 5126 => 4,
        _ => bail!("unsupported source accessor component"),
    };
    let view = value["bufferViews"]
        .as_array()
        .and_then(|v| a["bufferView"].as_u64().and_then(|i| v.get(i as usize)))
        .context("invalid source buffer view")?;
    ensure!(
        view["buffer"].as_u64() == Some(0) && view.get("byteStride").is_none(),
        "source buffer views must be tightly packed"
    );
    let offset = view["byteOffset"].as_u64().unwrap_or(0) as usize;
    let length = view["byteLength"].as_u64().context("source view needs a length")? as usize;
    ensure!(offset.checked_add(length).is_some_and(|end| end <= binary.len()), "source view exceeds its buffer");
    let start = a["byteOffset"].as_u64().unwrap_or(0) as usize;
    let needed = count.checked_mul(width * size).context("source accessor size overflow")?;
    ensure!(start.checked_add(needed).is_some_and(|end| end <= length), "source accessor exceeds its view");
    let first = offset.checked_add(start).context("source accessor offset overflow")?;
    ensure!(first % size == 0, "source accessor is not aligned");
    let last = first.checked_add(needed).context("source accessor offset overflow")?;
    Ok((binary.get(first..last).context("source accessor exceeds its buffer")?, count, (component, kind)))
}

/// Whether a material contains any texture channel.
fn has_texture(value: &Value) -> bool {
    match value {
        Value::Object(fields) => fields.iter().any(|(key, value)| key.ends_with("Texture") || has_texture(value)),
        Value::Array(values) => values.iter().any(has_texture),
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::glb::{Material, Mesh};
    use crate::shapes::cuboid;
    use glam::DVec3;
    use std::sync::atomic::{AtomicUsize, Ordering};

    #[test]
    fn shadow_alpha_metadata_tracks_each_masked_primitive() {
        let mut value = json!({
            "nodes": [{"mesh": 0}],
            "meshes": [{"primitives": [{"material": 0}, {"material": 1}]}],
            "materials": [{"alphaMode": "OPAQUE"}, {"alphaMode": "MASK", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
            "textures": [{"source": 0}],
            "images": [{"uri": "../../textures/leaf/leaf.ktx2"}]
        });
        assert_eq!(shadow_alpha_textures(&value, 0).unwrap(), json!([null, "textures/leaf/leaf.alpha.ktx2"]));
        value["images"][0]["uri"] = json!("../../outside/leaf.ktx2");
        assert!(shadow_alpha_textures(&value, 0).is_err());
    }

    fn fixture(collision: bool) -> Vec<u8> {
        let mut glb = Glb::from_json(json!({"asset": {"version": "2.0"}}));
        let mut mesh = Mesh::default();
        cuboid(&mut mesh, DVec3::ZERO, DVec3::splat(2.0));
        mesh.colours = vec![[0.2, 0.3, 0.4, 0.0]; mesh.positions.len()];
        mesh.material = glb.add_material(&Material {
            name: "paint",
            texture: None,
            colour: [0.2, 0.3, 0.4],
            cut_out: false,
            two_sided: false,
        });
        let node = glb.add_mesh("full", &[&mesh]);
        glb.set_extras(node, json!({"vertex_paint": {"fill": 0.06}}));
        if collision {
            glb.add_mesh("collision", &[&mesh]);
        }
        static NEXT_FIXTURE: AtomicUsize = AtomicUsize::new(0);
        let id = NEXT_FIXTURE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!("hakuba-source-fixture-{}-{id}.glb", std::process::id()));
        glb.write(&path).unwrap();
        let bytes = fs::read(&path).unwrap();
        fs::remove_file(path).unwrap();
        bytes
    }

    #[test]
    fn foliage_needs_declared_textures_and_preserves_every_version() {
        let mut glb = Glb::from_json(json!({"asset": {"version": "2.0"}}));
        let mut mesh = Mesh::default();
        cuboid(&mut mesh, DVec3::ZERO, DVec3::splat(2.0));
        mesh.colours = vec![[0.25, 0.5, 0.0, 1.0]; mesh.positions.len()];
        mesh.material = glb.add_material(&Material::textured("leaf", "../../textures/a/a.ktx2"));
        glb.add_mesh("full", &[&mesh]);
        glb.add_mesh("middle", &[&mesh]);
        glb.add_mesh("far", &[&mesh]);
        static NEXT_FOLIAGE: AtomicUsize = AtomicUsize::new(0);
        let id = NEXT_FOLIAGE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!("hakuba-foliage-fixture-{}-{id}.glb", std::process::id()));
        glb.write(&path).unwrap();
        let bytes = fs::read(&path).unwrap();
        fs::remove_file(path).unwrap();
        let allowed = vec!["../../textures/a/a.ktx2".to_string()];
        assert!(validate_kind(&bytes, Some(&allowed), None, &allowed).is_ok());
        assert!(validate_kind(&bytes, Some(&[]), None, &[]).is_err());
        assert!(validate(&bytes).is_err());
    }

    #[test]
    fn full_only_surface_requires_declared_stored_height() {
        let mut glb = Glb::from_json(json!({"asset": {"version": "2.0"}}));
        let mut mesh = Mesh::default();
        cuboid(&mut mesh, DVec3::ZERO, DVec3::splat(2.0));
        for point in &mut mesh.positions {
            point[1] = if point[1] < 0.0 { 0.02 } else { 2.02 };
        }
        mesh.colours = vec![[0.0, 1.0, 0.0, 1.0]; mesh.positions.len()];
        mesh.material = glb.add_material(&Material::textured("surface", "../../textures/a/a.ktx2"));
        glb.add_mesh("full", &[&mesh]);
        let path = std::env::temp_dir().join(format!("hakuba-foliage-surface-{}.glb", std::process::id()));
        glb.write(&path).unwrap();
        let bytes = fs::read(&path).unwrap();
        fs::remove_file(path).unwrap();
        let allowed = vec!["../../textures/a/a.ktx2".to_string()];
        assert!(validate_kind(&bytes, Some(&allowed), None, &allowed).is_err());
        assert!(validate_kind(&bytes, Some(&allowed), Some(0.02), &allowed).is_ok());
        assert!(validate_kind(&bytes, Some(&allowed), Some(0.03), &allowed).is_err());
    }

    #[test]
    fn source_export_preserves_mesh_and_extras_with_separate_collision() {
        let root = std::env::temp_dir().join(format!("hakuba-source-export-{}", std::process::id()));
        fs::create_dir_all(root.join("src")).unwrap();
        let input = fixture(true);
        fs::write(root.join("src/model.glb"), &input).unwrap();
        let output = root.join("out.glb");
        assert!(export("src/model.glb", false, &[], &[], &[], &output).is_err());
        export("src/model.glb", true, &[], &[], &[], &output).unwrap();
        let result = Glb::read(&output).unwrap();
        assert_eq!(result.extras("full").unwrap()["vertex_paint"]["fill"], 0.06);
        assert!(result.extras("full").unwrap().get("solid").is_none());
        assert!(result.node("collision").is_ok());
        let out = fs::read(&output).unwrap();
        let (before, _) = validate(&input).unwrap();
        let (after, _) = validate(&out).unwrap();
        assert_eq!(before["meshes"], after["meshes"]);
        assert_eq!(before["materials"], after["materials"]);
        for attribute in ["POSITION", "NORMAL", "TEXCOORD_0", "COLOR_0"] {
            let a = before["meshes"][0]["primitives"][0]["attributes"][attribute].as_u64().unwrap() as usize;
            let b = after["meshes"][0]["primitives"][0]["attributes"][attribute].as_u64().unwrap() as usize;
            assert_eq!(accessor(&before, binary(&input), a).unwrap().0, accessor(&after, binary(&out), b).unwrap().0);
        }
        // The middle version: its own file, the full node's extras, never solid and no collision.
        let middle = Glb::read(&middle_path(&output)).unwrap();
        assert_eq!(middle.extras("middle").unwrap()["vertex_paint"]["fill"], 0.06);
        assert!(middle.extras("middle").unwrap().get("solid").is_none());
        assert!(middle.node("full").is_err() && middle.node("collision").is_err());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn simplify_keeps_at_most_its_budget_and_only_used_vertices() {
        // A 100 m square of 100 by 100 cells, 20 000 triangles.
        let mut grid = Mesh::default();
        for y in 0..=100 {
            for x in 0..=100 {
                grid.positions.push([x as f32, 0.0, y as f32]);
                grid.normals.push([0.0, 1.0, 0.0]);
                grid.colours.push([0.5, 0.5, 0.5, 0.0]);
            }
        }
        for y in 0..100 {
            for x in 0..100 {
                let i = y * 101 + x;
                grid.indices.extend([i, i + 101, i + 1, i + 1, i + 101, i + 102]);
            }
        }
        let simple = simplify(&grid, 500);
        assert!(!simple.indices.is_empty() && simple.indices.len() / 3 <= 500);
        assert!(simple.indices.iter().all(|&i| (i as usize) < simple.positions.len()));
        assert_eq!(simple.positions.len(), simple.colours.len());
        assert_eq!(middle_triangles(1.0), 48);
        assert_eq!(middle_triangles(500.0), 1500);
    }

    #[test]
    fn source_texture_must_be_declared_and_anchor_uses_model_frame() {
        let mut glb = Glb::from_json(json!({"asset": {"version": "2.0"}}));
        let mut mesh = Mesh::default();
        cuboid(&mut mesh, DVec3::ZERO, DVec3::splat(2.0));
        let uri = "../../textures/test-texture/test-texture.ktx2";
        mesh.material = glb.add_material(&Material::textured("texture", uri));
        glb.add_mesh("full", &[&mesh]);
        let root = std::env::temp_dir().join(format!("hakuba-source-texture-{}", std::process::id()));
        fs::create_dir_all(root.join("src")).unwrap();
        let input = root.join("src/model.glb");
        glb.write(&input).unwrap();
        let bytes = fs::read(&input).unwrap();
        assert!(validate_with_textures(&bytes, &[uri.into()]).is_ok());
        assert!(validate_with_textures(&bytes, &["../../textures/other/other.ktx2".into()]).is_err());
        assert!(validate(&bytes).is_err());
        // A texture only this prop shows is named by its file beside the export, and must be declared too.
        let mut own = Glb::from_json(json!({"asset": {"version": "2.0"}}));
        mesh.material = own.add_material(&Material::textured("texture", "parasol.ktx2"));
        own.add_mesh("full", &[&mesh]);
        own.write(&input).unwrap();
        let own = fs::read(&input).unwrap();
        assert!(validate_with_textures(&own, &["parasol.ktx2".into()]).is_ok());
        assert!(validate_with_textures(&own, &[uri.into()]).is_err());
        let mut missing_uv = Glb::from_json(json!({"asset": {"version": "2.0"}}));
        mesh.uvs.clear();
        mesh.material = missing_uv.add_material(&Material::textured("texture", uri));
        missing_uv.add_mesh("full", &[&mesh]);
        missing_uv.write(&input).unwrap();
        assert!(validate_with_textures(&fs::read(&input).unwrap(), &[uri.into()]).is_err());
        // An untextured source isolates the normal model-frame to glTF-frame anchor conversion.
        fs::write(&input, fixture(false)).unwrap();
        let output = root.join("out.glb");
        export("src/model.glb", false, &[], &[], &[[1.0, 2.0, 3.0]], &output).unwrap();
        let result = fs::read(&output).unwrap();
        let len = u32::from_le_bytes(result[12..16].try_into().unwrap()) as usize;
        let json: Value = serde_json::from_slice(&result[20..20 + len]).unwrap();
        let anchor = json["nodes"].as_array().unwrap().iter().find(|n| n["name"] == "anchor 0").unwrap();
        assert_eq!(anchor["translation"], json!([1.0, 3.0, -2.0]));
        assert!(export("src/model.glb", false, &[], &[], &[[f64::MAX, 0.0, 0.0]], &output).is_err());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn static_vertex_paint_rejects_motion_weight_and_colour_past_one() {
        // The first corner's alpha weight without a motion profile, then its red past 1.
        for (channel, value) in [(12, 0.2_f32), (0, 1.5)] {
            let mut bytes = fixture(false);
            let (json, _) = validate(&bytes).unwrap();
            let json_len = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
            let index = json["meshes"][0]["primitives"][0]["attributes"]["COLOR_0"].as_u64().unwrap() as usize;
            let accessor = &json["accessors"][index];
            let view = &json["bufferViews"][accessor["bufferView"].as_u64().unwrap() as usize];
            let offset = 20
                + json_len
                + 8
                + view["byteOffset"].as_u64().unwrap_or(0) as usize
                + accessor["byteOffset"].as_u64().unwrap_or(0) as usize
                + channel;
            bytes[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
            assert!(validate(&bytes).is_err());
        }
    }

    #[test]
    fn painted_weights_require_a_valid_explicit_motion_profile() {
        let mut glb = Glb::from_json(json!({"asset": {"version": "2.0"}}));
        let mut mesh = Mesh::default();
        cuboid(&mut mesh, DVec3::ZERO, DVec3::splat(2.0));
        mesh.colours = vec![[0.2, 0.3, 0.4, 0.5]; mesh.positions.len()];
        mesh.material = glb.add_material(&Material {
            name: "paint",
            texture: None,
            colour: [1.0; 3],
            cut_out: false,
            two_sided: false,
        });
        let node = glb.add_mesh("full", &[&mesh]);
        let profile = json!({"spatial": [0.2, 0.3], "rate": 1.7, "amplitude": [0.022, 0.004, 0.013], "harmonic": [1.0, 1.3, 0.81]});
        glb.set_extras(node, json!({"vertex_paint": {"fill": 0.06}, "vertex_motion": profile}));
        static NEXT_MOTION: AtomicUsize = AtomicUsize::new(0);
        let id = NEXT_MOTION.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!("hakuba-source-motion-{}-{id}.glb", std::process::id()));
        glb.write(&path).unwrap();
        assert!(validate(&fs::read(&path).unwrap()).is_ok());
        glb.set_extras(node, json!({"vertex_paint": {"fill": 0.06}, "vertex_motion": {"rate": 1.7}}));
        glb.write(&path).unwrap();
        assert!(validate(&fs::read(&path).unwrap()).is_err());
        fs::remove_file(path).unwrap();
    }

    #[test]
    fn source_rejects_external_paths_and_invalid_geometry() {
        let mut bytes = fixture(false);
        assert!(validate(&bytes).is_ok());
        assert!(validate(&bytes[..bytes.len() - 1]).is_err());
        let (json, _) = validate(&bytes).unwrap();
        let json_len = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
        let position = json["meshes"][0]["primitives"][0]["attributes"]["POSITION"].as_u64().unwrap() as usize;
        let accessor = &json["accessors"][position];
        let view = &json["bufferViews"][accessor["bufferView"].as_u64().unwrap() as usize];
        let offset = 20
            + json_len
            + 8
            + view["byteOffset"].as_u64().unwrap_or(0) as usize
            + accessor["byteOffset"].as_u64().unwrap_or(0) as usize;
        bytes[offset..offset + 4].copy_from_slice(&f32::NAN.to_le_bytes());
        assert!(validate(&bytes).is_err());
        let root = std::env::temp_dir().join(format!("hakuba-source-path-{}", std::process::id()));
        fs::create_dir_all(root.join("src")).unwrap();
        assert!(export("src/../model.glb", true, &[], &[], &[], &root.join("out.glb")).is_err());
        for path in ["src/.hidden.glb", "src/target/model.glb", "src/.hidden/model.glb"] {
            let error = export(path, true, &[], &[], &[], &root.join("out.glb")).unwrap_err();
            assert!(error.to_string().contains("checksum"));
        }
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn unreferenced_vertex_cannot_ground_a_floating_mesh() {
        let mut glb = Glb::from_json(json!({"asset": {"version": "2.0"}}));
        let mut mesh = Mesh::default();
        cuboid(&mut mesh, DVec3::new(0.0, 2.0, 0.0), DVec3::splat(1.0));
        mesh.positions.push([0.0, -1.0, 0.0]);
        mesh.normals.push([0.0, 1.0, 0.0]);
        mesh.uvs.push([0.0, 0.0]);
        glb.add_mesh("full", &[&mesh]);
        let path = std::env::temp_dir().join(format!("hakuba-floating-source-{}.glb", std::process::id()));
        glb.write(&path).unwrap();
        assert!(validate(&fs::read(&path).unwrap()).is_err());
        fs::remove_file(path).unwrap();
    }

    #[test]
    fn source_rejects_cutout_material() {
        let bytes = fixture(false);
        let (mut json, _) = validate(&bytes).unwrap();
        json["nodes"][0]["extras"] = json!({});
        json["materials"][0]["alphaMode"] = json!("MASK");
        let old_len = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
        let mut text = serde_json::to_vec(&json).unwrap();
        text.resize(text.len().next_multiple_of(4), b' ');
        let tail = &bytes[20 + old_len..];
        let mut rebuilt = b"glTF".to_vec();
        rebuilt.extend(2_u32.to_le_bytes());
        rebuilt.extend(((20 + text.len() + tail.len()) as u32).to_le_bytes());
        rebuilt.extend((text.len() as u32).to_le_bytes());
        rebuilt.extend(b"JSON");
        rebuilt.extend(text);
        rebuilt.extend(tail);
        assert!(validate(&rebuilt).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn source_rejects_a_src_symlink_outside_its_asset() {
        use std::os::unix::fs::symlink;
        let root = std::env::temp_dir().join(format!("hakuba-source-link-{}", std::process::id()));
        fs::create_dir_all(root.join("asset")).unwrap();
        fs::create_dir_all(root.join("outside")).unwrap();
        fs::write(root.join("outside/model.glb"), fixture(false)).unwrap();
        symlink(root.join("outside"), root.join("asset/src")).unwrap();
        assert!(export("src/model.glb", true, &[], &[], &[], &root.join("asset/out.glb")).is_err());
        fs::remove_dir_all(root).unwrap();
    }
}
