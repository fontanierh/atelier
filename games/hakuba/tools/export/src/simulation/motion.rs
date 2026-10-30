//! Deterministic binary motion encoders for readable rig, clip and metadata sources.

use std::collections::HashMap;

use anyhow::{Context, Result, bail, ensure};
use serde_json::Value;

use super::{Writer, array, bits, text, uint, version, wide};

const COMPONENTS: [&str; 10] = [
    "scale_x",
    "scale_y",
    "scale_z",
    "rotation_x",
    "rotation_y",
    "rotation_z",
    "rotation_w",
    "translation_x",
    "translation_y",
    "translation_z",
];

fn sample(value: &Value) -> Result<Value> {
    let fields = value.as_object().context("a sample must be an object")?;
    ensure!(fields.len() == 3, "a sample has scale[3], rotation[4] and translation[3]");
    let mut values = Vec::with_capacity(10);
    for (key, size) in [("scale", 3), ("rotation", 4), ("translation", 3)] {
        let row = array(&value[key])?;
        ensure!(row.len() == size, "a sample has scale[3], rotation[4] and translation[3]");
        values.extend(row.iter().cloned());
    }
    Ok(Value::Array(values))
}

fn ordered_bones(value: &Value, names: &[&str]) -> Result<()> {
    let bones = value.as_object().context("bones must be an object")?;
    ensure!(bones.keys().map(String::as_str).eq(names.iter().copied()), "must list every rig bone in rig order");
    Ok(())
}

fn boolean(value: &Value) -> Result<u32> {
    Ok(u32::from(value.as_bool().context("expected a boolean")?))
}

fn number(value: &Value) -> Result<u32> {
    ensure!(value.is_number(), "motion values must be finite numbers");
    bits(value)
}

fn numbers(w: &mut Writer, value: &Value, counted: bool) -> Result<()> {
    let words = array(value)?.iter().map(number).collect::<Result<Vec<_>>>()?;
    w.words(&words, counted);
    Ok(())
}

/// Encode a rig and its named reference poses, keeping the rig's bone order.
pub fn rig(value: &Value) -> Result<Vec<u8>> {
    version(value)?;
    let bones = array(&value["bones"])?;
    let names = bones.iter().map(|bone| text(&bone["name"])).collect::<Result<Vec<_>>>()?;
    let mut index = HashMap::with_capacity(names.len());
    for (i, name) in names.iter().enumerate() {
        ensure!(index.insert(*name, i as u32).is_none(), "duplicate rig bone {name}");
    }
    let mut w = Writer::new(b"ATSKEL01");
    w.word(names.len() as u32);
    w.word(boolean(&value["trajectory"])?);
    for bone in bones {
        w.string(text(&bone["name"])?);
        for key in ["parent", "mirror"] {
            let link = bone.get(key).with_context(|| format!("missing bone {key}"))?;
            w.word(if link.is_null() {
                u32::MAX
            } else {
                *index.get(text(link)?).with_context(|| format!("unknown rig bone {link}"))?
            });
        }
    }
    let poses = array(&value["reference_poses"])?;
    w.word(poses.len() as u32);
    for pose in poses {
        w.word(uint(&pose["bank"])?);
        w.string(text(&pose["name"])?);
        w.wide(wide(&pose["record"])?);
        ordered_bones(&pose["bones"], &names)?;
        w.word(names.len() as u32);
        for name in &names {
            numbers(&mut w, &sample(&pose["bones"][*name])?, false)?;
        }
    }
    Ok(w.data)
}

/// Encode scalar or per-frame component tracks in rig order.
pub fn clip(value: &Value, names: &[String]) -> Result<Vec<u8>> {
    version(value)?;
    let names = names.iter().map(String::as_str).collect::<Vec<_>>();
    ordered_bones(&value["bones"], &names)?;
    let mut w = Writer::new(b"ATCLIP01");
    w.string(text(&value["name"])?);
    w.word(uint(&value["bank"])?);
    w.wide(wide(&value["record"])?);
    w.word(number(&value["frame_rate"])?);
    numbers(&mut w, &value["loop"]["translation"], false)?;
    numbers(&mut w, &value["loop"]["rotation"], false)?;
    w.word(boolean(&value["channel_animation"])?);
    w.word(names.len() as u32);
    for name in &names {
        w.word(number(&value["bones"][*name]["weight"])?);
    }
    let frames = uint(&value["frames"])?;
    w.word(frames);
    w.word(names.len() as u32);
    for name in names {
        for component in COMPONENTS {
            let track = &value["bones"][name][component];
            if let Some(values) = track.as_array() {
                ensure!(
                    values.len() == 1 || values.len() as u64 == u64::from(frames),
                    "{name}.{component}: one value or one per frame"
                );
                numbers(&mut w, track, true)?;
            } else {
                w.word(1);
                w.word(number(track)?);
            }
        }
    }
    Ok(w.data)
}

// Names are packed as signed UTF-8 bytes in five six-character base-38 chunks.
fn encode_name(name: &str) -> [u32; 5] {
    let mut words = [0u32; 5];
    let mut weight = 79_235_168i64;
    for (at, byte) in name.bytes().take(30).take_while(|byte| *byte != 0).enumerate() {
        if at % 6 == 0 {
            weight = 79_235_168;
        }
        let byte = i64::from(byte as i8);
        let digit = if byte >= 97 {
            byte - 86
        } else if byte > 90 {
            byte - 58
        } else if byte > 57 {
            byte - 54
        } else {
            byte - 47
        };
        words[at / 6] = words[at / 6].wrapping_add((digit * weight) as u32);
        weight /= 38;
    }
    words
}

fn identity(w: &mut Writer, value: &Value) -> Result<()> {
    w.string(text(&value["name"])?);
    w.wide(wide(&value["source_offset"])?);
    Ok(())
}

/// Encode attributes and all metadata tree kinds without changing their source order.
pub fn metadata(value: &Value, names: &[String]) -> Result<Vec<u8>> {
    version(value)?;
    let mut w = Writer::new(b"ATMETA01");
    w.string(text(&value["source_bank"])?);
    w.string(text(&value["source_sha256"])?);
    w.wide(wide(&value["source_bytes"])?);
    let clips = array(&value["clips"])?;
    w.word(clips.len() as u32);
    for clip in clips {
        identity(&mut w, clip)?;
        for key in ["frame_rate", "frames", "base_speed"] {
            w.word(number(&clip[key])?);
        }
        w.word(uint(&clip["flags"])?);
        let attributes = array(&clip["attributes"])?;
        w.word(attributes.len() as u32);
        for a in attributes {
            let kind = match text(&a["kind"])? {
                "scalar" => 0,
                "bone_contact" => 3,
                other => bail!("unsupported attribute kind {other}"),
            };
            w.string(text(&a["name"])?);
            w.word(kind);
            w.word(number(&a["begin"])?);
            w.word(number(&a["end"])?);
            w.wide(wide(&a["source_offset"])?);
            if kind == 3 {
                let target = text(&a["target_bone"])?;
                ensure!(names.iter().any(|name| name == target), "attribute targets an unknown bone {target}");
                let mut payload = encode_name(target).to_vec();
                payload.extend([number(&a["value"])?, 0, 0]);
                w.words(&payload, true);
            } else {
                w.words(&[number(&a["value"])?, 0, 0, 0], true);
            }
        }
    }
    let trees = array(&value["phase_blends"])?;
    w.word(trees.len() as u32);
    for tree in trees {
        identity(&mut w, tree)?;
        w.string(text(&tree["parameter"])?);
        w.strings(&tree["children"])?;
    }
    let trees = array(&value["blend_spaces"])?;
    w.word(trees.len() as u32);
    for tree in trees {
        identity(&mut w, tree)?;
        w.strings(&tree["parameters"])?;
        w.strings(&tree["children"])?;
        let simplexes = array(&tree["simplexes"])?;
        w.word(simplexes.len() as u32);
        for simplex in simplexes {
            let children = array(&simplex["children"])?.iter().map(uint).collect::<Result<Vec<_>>>()?;
            w.words(&children, true);
            for key in ["vertices", "normals"] {
                let rows = array(&simplex[key])?;
                w.word(rows.len() as u32);
                for row in rows {
                    numbers(&mut w, row, true)?;
                }
            }
            numbers(&mut w, &simplex["scales"], true)?;
        }
    }
    let trees = array(&value["selectors"])?;
    w.word(trees.len() as u32);
    for tree in trees {
        identity(&mut w, tree)?;
        w.string(text(&tree["parameter"])?);
        w.string(text(&tree["default"])?);
        w.strings(&tree["children"])?;
        w.strings(&tree["values"])?;
    }
    let trees = array(&value["selection_spaces"])?;
    w.word(trees.len() as u32);
    for tree in trees {
        identity(&mut w, tree)?;
        let parameters = array(&tree["parameters"])?;
        w.word(parameters.len() as u32);
        for p in parameters {
            w.string(text(&p["name"])?);
            w.word(uint(&p["mode"])?);
            for key in ["weight", "minimum", "maximum"] {
                w.word(number(&p[key])?);
            }
        }
        let candidates = array(&tree["candidates"])?;
        w.word(candidates.len() as u32);
        for c in candidates {
            w.string(text(&c["child"])?);
            numbers(&mut w, &c["values"], true)?;
        }
    }
    let trees = array(&value["unsupported_trees"])?;
    w.word(trees.len() as u32);
    for tree in trees {
        identity(&mut w, tree)?;
        w.word(uint(&tree["kind"])?);
    }
    Ok(w.data)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn from_hex(value: &str) -> Vec<u8> {
        value
            .as_bytes()
            .chunks_exact(2)
            .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
            .collect()
    }

    fn rig_source() -> Value {
        json!({
            "version": 1, "trajectory": true,
            "bones": [
                {"name": "z", "parent": null, "mirror": "a"},
                {"name": "a", "parent": "z", "mirror": "z"}
            ],
            "reference_poses": [{
                "bank": 7, "name": "rest", "record": 1099511627779u64,
                "bones": {
                    "z": {"scale": [1, 1, 1], "rotation": [0, 0, 0, 1], "translation": [-0.0, 0.1, 3]},
                    "a": {"scale": [1, 1, 1], "rotation": [0, 0, 0, 1], "translation": [4, 5, 6]}
                }
            }]
        })
    }

    fn clip_source() -> Value {
        let mut tracks = serde_json::Map::new();
        tracks.insert("weight".into(), json!(0.5));
        for component in COMPONENTS {
            tracks.insert(component.into(), if component == "translation_x" { json!([0.1, -0.0]) } else { json!(1) });
        }
        json!({
            "version": 1, "name": "turn", "bank": 2, "record": 1099511627779u64,
            "frame_rate": 29.97, "frames": 2, "channel_animation": false,
            "loop": {"translation": [-0.0, 0, 1], "rotation": [0, 0, 0, 1]},
            "bones": {"z": tracks}
        })
    }

    fn metadata_source() -> Value {
        json!({
            "version": 1, "source_bank": "bank", "source_sha256": "hash", "source_bytes": 1099511627779u64,
            "clips": [{
                "name": "turn", "source_offset": 1099511627780u64,
                "frame_rate": 29.97, "frames": 2, "base_speed": -0.0, "flags": 7,
                "attributes": [
                    {"name": "speed", "kind": "scalar", "begin": 0, "end": 1, "source_offset": 5, "value": 0.1},
                    {"name": "contact", "kind": "bone_contact", "target_bone": "z", "begin": 0, "end": 1, "source_offset": 6, "value": -0.0}
                ]
            }],
            "phase_blends": [{"name": "phase", "source_offset": 7, "parameter": "p", "children": ["turn"]}],
            "blend_spaces": [{
                "name": "space", "source_offset": 8, "parameters": ["x", "y"], "children": ["turn"],
                "simplexes": [{"children": [0], "vertices": [[0.1, -0.0]], "normals": [[1, 0]], "scales": [2]}]
            }],
            "selectors": [{"name": "selector", "source_offset": 9, "parameter": "p", "default": "turn", "children": ["turn"], "values": ["yes"]}],
            "selection_spaces": [{
                "name": "selection", "source_offset": 10,
                "parameters": [{"name": "p", "mode": 3, "weight": 0.1, "minimum": -0.0, "maximum": 1}],
                "candidates": [{"child": "turn", "values": [0.1]}]
            }],
            "unsupported_trees": [{"name": "opaque", "source_offset": 11, "kind": 42}]
        })
    }

    // These independent fixture bytes cover ordering, binary32 rounding, negative zero and wide offsets.
    #[test]
    fn rig_binary_layout() {
        assert_eq!(
            rig(&rig_source()).unwrap(),
            from_hex(
                "4154534b454c30310200000001000000010000007affffffff0100000001000000610000000000000000010000000700000004000000726573740300000000010000020000000000803f0000803f0000803f0000000000000000000000000000803f00000080cdcccc3d000040400000803f0000803f0000803f0000000000000000000000000000803f000080400000a0400000c040"
            )
        );
    }

    #[test]
    fn clip_binary_layout() {
        assert_eq!(
            clip(&clip_source(), &["z".into()]).unwrap(),
            from_hex(
                "4154434c49503031040000007475726e0200000003000000000100008fc2ef4100000080000000000000803f0000000000000000000000000000803f00000000010000000000003f0200000001000000010000000000803f010000000000803f010000000000803f010000000000803f010000000000803f010000000000803f010000000000803f02000000cdcccc3d00000080010000000000803f010000000000803f"
            )
        );
    }

    #[test]
    fn metadata_binary_layout() {
        assert_eq!(
            metadata(&metadata_source(), &["z".into()]).unwrap(),
            from_hex(
                "41544d45544130310400000062616e6b0400000068617368030000000001000001000000040000007475726e04000000000100008fc2ef410000004000000080070000000200000005000000737065656400000000000000000000803f050000000000000004000000cdcccc3d00000000000000000000000007000000636f6e7461637403000000000000000000803f060000000000000008000000802d05aa00000000000000000000000000000000000000800000000000000000010000000500000070686173650700000000000000010000007001000000040000007475726e010000000500000073706163650800000000000000020000000100000078010000007901000000040000007475726e0100000001000000000000000100000002000000cdcccc3d0000008001000000020000000000803f000000000100000000000040010000000800000073656c6563746f7209000000000000000100000070040000007475726e01000000040000007475726e0100000003000000796573010000000900000073656c656374696f6e0a0000000000000001000000010000007003000000cdcccc3d000000800000803f01000000040000007475726e01000000cdcccc3d01000000060000006f70617175650b000000000000002a000000"
            )
        );
    }

    #[test]
    fn rig_rejects_bad_bones_and_samples() {
        let mut value = rig_source();
        value["bones"][1]["name"] = json!("z");
        assert!(rig(&value).is_err());
        let mut value = rig_source();
        value["bones"][0]["parent"] = json!("missing");
        assert!(rig(&value).is_err());
        let mut value = rig_source();
        let bones = value["reference_poses"][0]["bones"].as_object_mut().unwrap();
        let first = bones.shift_remove("z").unwrap();
        bones.insert("z".into(), first);
        assert!(rig(&value).is_err());
        let mut value = rig_source();
        value["reference_poses"][0]["bones"]["z"]["scale"] = json!([1, 1]);
        assert!(rig(&value).is_err());
        let mut value = rig_source();
        value["reference_poses"][0]["bones"]["z"]["extra"] = json!(0);
        assert!(rig(&value).is_err());
    }

    #[test]
    fn clip_rejects_wrong_order_and_invalid_tracks() {
        assert!(clip(&clip_source(), &["a".into(), "z".into()]).is_err());
        let mut value = clip_source();
        value["bones"]["z"]["translation_x"] = json!([1, 2, 3]);
        assert!(clip(&value, &["z".into()]).is_err());
        value["bones"]["z"]["translation_x"] = json!(true);
        assert!(clip(&value, &["z".into()]).is_err());
        value["bones"]["z"]["translation_x"] = json!([null]);
        assert!(clip(&value, &["z".into()]).is_err());
        value["bones"]["z"]["translation_x"] = json!(["0x3f800000"]);
        assert!(clip(&value, &["z".into()]).is_err());
    }

    #[test]
    fn metadata_rejects_unknown_attributes_and_targets() {
        let mut value = metadata_source();
        assert!(metadata(&value, &[]).is_err());
        value["clips"][0]["attributes"][0]["kind"] = json!(9);
        assert!(metadata(&value, &["z".into()]).is_err());
        value["clips"][0]["attributes"][0]["kind"] = json!("other");
        assert!(metadata(&value, &["z".into()]).is_err());
    }

    #[test]
    fn name_encoding_uses_signed_bytes_wrapping_and_thirty_byte_limit() {
        assert_eq!(encode_name("abcdefg"), [897342618, 1346997856, 0, 0, 0]);
        assert_eq!(encode_name("é😀"), [4044424735, 0, 0, 0, 0]);
        assert_eq!(
            encode_name("abcdefghijklmnopqrstuvwxyz123456789"),
            [897342618, 1385602572, 1873862526, 2362122480, 2848410009]
        );
        assert_eq!(encode_name("abc\0def"), [897321816, 0, 0, 0, 0]);
    }
}
