//! Importing a self-contained static prop, including an optional separate collision mesh.

use std::fs;
use std::path::{Component, Path};

use anyhow::{Context, Result, bail, ensure};
use glam::DVec3;
use serde_json::{Value, json};

use crate::glb::Glb;

/// @cc [owner:fontanierh,label:correctness] static-source-prop
/// A source prop MUST contain only embedded, finite static geometry in identity-frame full and optional collision
/// nodes. The exporter MUST preserve the full mesh's attributes and extras and never make its collision mesh visible.
pub(super) fn export(source: &str, solid: bool, output: &Path) -> Result<()> {
    let path = Path::new(source);
    ensure!(path.extension().is_some_and(|ext| ext == "glb"), "source must be a GLB in src/");
    let mut parts = path.components();
    ensure!(matches!(parts.next(), Some(Component::Normal(p)) if p == "src"), "source must be in src/");
    ensure!(parts.all(|part| matches!(part, Component::Normal(_))), "source path must stay in src/");
    let folder = output.parent().context("source model has no asset folder")?;
    let asset = folder.canonicalize().context("reading asset folder")?;
    let root = folder.join("src").canonicalize().context("reading source folder")?;
    ensure!(root.starts_with(&asset), "source folder must stay in the asset folder");
    let file = folder.join(path).canonicalize().context("reading source model")?;
    ensure!(file.starts_with(root), "source path must stay in src/");
    let bytes = fs::read(&file).context("reading source model")?;
    let (value, collision) = validate(&bytes)?;
    ensure!(!collision || solid, "a collision mesh requires solid = true");
    let mut glb = Glb::read(&file)?;
    let full = glb.node("full")?;
    let mut extras = value["nodes"][full]["extras"].as_object().cloned().unwrap_or_default();
    extras.remove("solid");
    if solid && !collision {
        extras.insert("solid".into(), json!(true));
    }
    glb.set_extras(full, extras.into());
    glb.write(output)
}

/// Reads the restricted static GLB layout accepted by source props, and checks actual bytes, not just bounds metadata.
fn validate(bytes: &[u8]) -> Result<(Value, bool)> {
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
    ensure!(value.get("images").is_none() && value.get("textures").is_none(), "source textures are not supported");
    ensure!(value.get("animations").is_none() && value.get("skins").is_none(), "source must be static");
    let nodes = array("nodes")?;
    let meshes = array("meshes")?;
    let materials = value.get("materials").and_then(Value::as_array);
    if let Some(materials) = materials {
        for material in materials {
            ensure!(!has_texture(material), "source materials cannot refer to textures");
        }
    }
    let scenes = array("scenes")?;
    ensure!(scenes.len() == 1 && value["scene"].as_u64().unwrap_or(0) == 0, "source must have one scene");
    let roots = scenes[0]["nodes"].as_array().context("source scene has no roots")?;
    ensure!(
        nodes.len() == roots.len() && (nodes.len() == 1 || nodes.len() == 2),
        "source needs full and optional collision roots"
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
        if vertex_paint {
            ensure!(node["extras"]["vertex_paint"].is_object(), "vertex paint extras must be an object");
        }
        ensure!(
            (name == "full" || name == "collision") && !seen.contains(&name),
            "source roots must be full and optional collision"
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
                ensure!(name != "full" || mode == "OPAQUE" || mode == "BLEND", "source cut-outs are unsupported");
                if vertex_paint {
                    ensure!(mode == "OPAQUE", "static vertex paint needs an opaque material");
                }
            } else {
                ensure!(!vertex_paint, "vertex paint needs a material");
            }
            let attributes = primitive["attributes"].as_object().context("source needs vertex attributes")?;
            ensure!(!vertex_paint || attributes.contains_key("COLOR_0"), "vertex paint requires source colors");
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
                            "COLOR_0" => kind.1 == "VEC3" || kind.1 == "VEC4",
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
                            && data.chunks_exact(16).all(|v| f32::from_le_bytes(v[12..16].try_into().unwrap()) == 0.0),
                        "static vertex paint needs zero motion weight in its alpha channel"
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
    ensure!(seen.contains(&"full") && lowest < 0.0, "full mesh must reach below its foot");
    ensure!(seen_meshes.len() == meshes.len(), "source cannot contain unused meshes");
    let collision = seen.contains(&"collision");
    Ok((value, collision))
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

/// Materials may describe color and factors, but source textures are not yet part of this format.
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
    fn source_export_preserves_mesh_and_extras_with_separate_collision() {
        let root = std::env::temp_dir().join(format!("hakuba-source-export-{}", std::process::id()));
        fs::create_dir_all(root.join("src")).unwrap();
        let input = fixture(true);
        fs::write(root.join("src/model.glb"), &input).unwrap();
        let output = root.join("out.glb");
        assert!(export("src/model.glb", false, &output).is_err());
        export("src/model.glb", true, &output).unwrap();
        let result = Glb::read(&output).unwrap();
        assert_eq!(result.extras("full").unwrap()["vertex_paint"]["fill"], 0.06);
        assert!(result.extras("full").unwrap().get("solid").is_none());
        assert!(result.node("collision").is_ok());
        let out = fs::read(&output).unwrap();
        let (before, _) = validate(&input).unwrap();
        let (after, _) = validate(&out).unwrap();
        assert_eq!(before["meshes"], after["meshes"]);
        assert_eq!(before["materials"], after["materials"]);
        fn binary(bytes: &[u8]) -> &[u8] {
            let len = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
            &bytes[20 + len + 8..]
        }
        for attribute in ["POSITION", "NORMAL", "TEXCOORD_0", "COLOR_0"] {
            let a = before["meshes"][0]["primitives"][0]["attributes"][attribute].as_u64().unwrap() as usize;
            let b = after["meshes"][0]["primitives"][0]["attributes"][attribute].as_u64().unwrap() as usize;
            assert_eq!(accessor(&before, binary(&input), a).unwrap().0, accessor(&after, binary(&out), b).unwrap().0);
        }
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn static_vertex_paint_rejects_nonzero_motion_weight() {
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
            + 12;
        bytes[offset..offset + 4].copy_from_slice(&0.2_f32.to_le_bytes());
        assert!(validate(&bytes).is_err());
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
        assert!(export("src/../model.glb", true, &root.join("out.glb")).is_err());
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
        assert!(export("src/model.glb", true, &root.join("asset/out.glb")).is_err());
        fs::remove_dir_all(root).unwrap();
    }
}
