// Deterministic encoders for settings, graphs, cameras, gestures and physical skeletons.
use std::collections::{BTreeMap, BTreeSet};

use anyhow::{Context, Result, bail, ensure};
use serde_json::{Map, Value};

use super::{Writer, array, bits, text, uint, wide};

fn object(value: &Value) -> Result<&Map<String, Value>> {
    value.as_object().context("expected an object")
}

fn count(value: usize) -> Result<u32> {
    value.try_into().context("count exceeds a word")
}

fn scalar(kind: &str) -> bool {
    matches!(
        kind,
        "Float" | "Bool" | "Text" | "Int8" | "Int16" | "Int32" | "Int64" | "UInt8" | "UInt16" | "UInt32" | "UInt64"
    )
}

fn long_type(kind: &str) -> String {
    if scalar(kind) { format!("EA::Reflection::{kind}") } else { kind.to_owned() }
}

fn pack(data: &[u8]) -> Vec<u32> {
    data.chunks(4).map(|chunk| chunk.iter().fold(0, |word, byte| (word << 8) | u32::from(*byte))).collect()
}

struct Field<'a> {
    name: &'a str,
    kind: String,
    size: u32,
    words: Vec<u32>,
    text: Option<&'a str>,
}

fn field<'a>(name: &'a str, value: &'a Value) -> Result<Field<'a>> {
    let values = array(value)?;
    ensure!((2..=3).contains(&values.len()), "a field holds type, value and optional Bool byte count");
    let kind = text(&values[0])?;
    let value = &values[1];
    let explicit_size = values.get(2).map(uint).transpose()?;
    if let Some(size) = explicit_size {
        ensure!(kind == "Bool" && value.is_boolean() && size >= 2, "only a Bool names its byte count");
    }
    let mut out = Field { name, kind: long_type(kind), size: 0, words: Vec::new(), text: None };
    if kind == "Text" {
        let value = text(value)?;
        out.size = count(value.len())?;
        out.text = Some(value);
    } else if let Some(packed) = value.as_object() {
        ensure!(
            packed.len() == 2 && packed.contains_key("words") && packed.contains_key("bytes"),
            "a packed field holds words and bytes"
        );
        out.size = uint(&packed["bytes"])?;
        out.words = array(&packed["words"])?.iter().map(bits).collect::<Result<_>>()?;
        ensure!(
            !out.size.is_multiple_of(4) && out.words.len() as u64 == u64::from(out.size).div_ceil(4),
            "packed field word count differs from its byte count"
        );
    } else if let Some(values) = value.as_array() {
        out.size = count(values.len())?.checked_mul(4).context("field byte count exceeds a word")?;
        out.words = values.iter().map(bits).collect::<Result<_>>()?;
    } else if let Some(value) = value.as_bool() {
        ensure!(kind == "Bool", "boolean in a {kind} field");
        out.size = explicit_size.unwrap_or(1);
        let mut data = vec![0; out.size as usize];
        data[0] = u8::from(value);
        out.words = pack(&data);
    } else if let Some((width, signed)) = match kind {
        "Int8" => Some((8, true)),
        "Int16" => Some((16, true)),
        "Int32" => Some((32, true)),
        "Int64" => Some((64, true)),
        "UInt8" => Some((8, false)),
        "UInt16" => Some((16, false)),
        "UInt32" => Some((32, false)),
        "UInt64" => Some((64, false)),
        _ => None,
    } {
        let value = value
            .as_i64()
            .map(i128::from)
            .or_else(|| value.as_u64().map(i128::from))
            .context("integer field requires an integer")?;
        let (low, high) =
            if signed { (-(1_i128 << (width - 1)), (1_i128 << (width - 1)) - 1) } else { (0, (1_i128 << width) - 1) };
        ensure!((low..=high).contains(&value), "value does not fit type {kind}");
        out.size = width / 8;
        out.words = pack(&value.to_be_bytes()[16 - out.size as usize..]);
    } else if kind == "Float" {
        out.size = 4;
        out.words.push(bits(value)?);
    } else {
        bail!("value does not fit type {kind}");
    }
    Ok(out)
}

/// Encode ordered reflected settings with a sorted, unique string table.
pub fn settings(value: &Value) -> Result<Vec<u8>> {
    let mut records = Vec::new();
    let mut strings = BTreeSet::new();
    for category in array(value)? {
        let category_name = text(&category["category"])?;
        for row in array(&category["records"])? {
            let key = text(&row["key"])?;
            let parent = row.get("parent").map(text).transpose()?.unwrap_or("");
            let fields =
                object(&row["fields"])?.iter().map(|(name, value)| field(name, value)).collect::<Result<Vec<_>>>()?;
            strings.extend([category_name.to_owned(), key.to_owned(), parent.to_owned()]);
            for field in &fields {
                strings.insert(field.name.to_owned());
                strings.insert(field.kind.clone());
            }
            records.push((category_name, key, parent, fields));
        }
    }
    let index: BTreeMap<_, _> =
        strings.iter().enumerate().map(|(i, s)| Ok((s.as_str(), count(i)?))).collect::<Result<_>>()?;
    let mut w = Writer::new(b"ATATTR01");
    w.word(count(strings.len())?);
    w.word(count(records.len())?);
    for string in &strings {
        w.string(string);
    }
    for (category, key, parent, fields) in records {
        for string in [category, key, parent] {
            w.word(index[string]);
        }
        w.word(count(fields.len())?);
        for field in fields {
            for word in [index[field.name], index[field.kind.as_str()], u32::from(field.text.is_some()), field.size] {
                w.word(word);
            }
            if let Some(text) = field.text {
                w.data.extend_from_slice(text.as_bytes());
            } else {
                w.words(&field.words, false);
            }
        }
    }
    Ok(w.data)
}

// Only decimal text contributes a numeric attribute word; other text contributes zero.
fn attribute_float(text: &str) -> Result<u32> {
    let bytes = text.as_bytes();
    let mut at = usize::from(matches!(bytes.first(), Some(b'+' | b'-')));
    let start = at;
    while bytes.get(at).is_some_and(u8::is_ascii_digit) {
        at += 1;
    }
    let mut digits = at - start;
    if bytes.get(at) == Some(&b'.') {
        at += 1;
        let start = at;
        while bytes.get(at).is_some_and(u8::is_ascii_digit) {
            at += 1;
        }
        digits += at - start;
    }
    if digits == 0 {
        return Ok(0);
    }
    if matches!(bytes.get(at), Some(b'e' | b'E')) {
        at += 1;
        if matches!(bytes.get(at), Some(b'+' | b'-')) {
            at += 1;
        }
        let start = at;
        while bytes.get(at).is_some_and(u8::is_ascii_digit) {
            at += 1;
        }
        if at == start {
            return Ok(0);
        }
    }
    if at != bytes.len() {
        return Ok(0);
    }
    let value: f64 = text.parse().context("invalid decimal graph attribute")?;
    ensure!(value.is_finite(), "graph attribute must be a finite number");
    Ok((value as f32).to_bits())
}

struct Element<'a> {
    offset: u32,
    tag: &'a str,
    attributes: &'a Map<String, Value>,
    children: Vec<u32>,
}

fn visit<'a>(value: &'a Value, elements: &mut Vec<Element<'a>>, offset: &mut u32) -> Result<()> {
    let node = object(value)?;
    let mut tags = node.iter().filter(|(key, _)| key.as_str() != "children");
    let (tag, attributes) = tags.next().context("a graph element needs one tag")?;
    ensure!(tags.next().is_none(), "a graph element has only one tag");
    let attributes = object(attributes)?;
    let mut size = tag.len() as u64 + 9;
    for (name, value) in attributes {
        size += name.len() as u64 + text(value)?.len() as u64 + 7;
    }
    let index = elements.len();
    elements.push(Element { offset: *offset, tag, attributes, children: Vec::new() });
    *offset = offset
        .checked_add(size.try_into().context("graph element is too large")?)
        .context("graph offset exceeds a word")?;
    if let Some(children) = node.get("children") {
        for child in array(children)? {
            let next = count(elements.len())?;
            elements[index].children.push(next);
            visit(child, elements, offset)?;
        }
    }
    Ok(())
}

/// Encode a graph in depth-first order, preserving the order of each tag's attributes.
pub fn graph(value: &Value) -> Result<Vec<u8>> {
    let mut elements = Vec::new();
    visit(value, &mut elements, &mut 0)?;
    let mut strings = BTreeSet::new();
    for element in &elements {
        strings.insert(element.tag);
        for (name, value) in element.attributes {
            strings.insert(name.as_str());
            strings.insert(text(value)?);
        }
    }
    let index: BTreeMap<_, _> = strings.iter().enumerate().map(|(i, s)| Ok((*s, count(i)?))).collect::<Result<_>>()?;
    let mut w = Writer::new(b"ATGRPH01");
    w.word(count(strings.len())?);
    w.word(count(elements.len())?);
    for string in &strings {
        w.string(string);
    }
    for element in elements {
        for word in
            [element.offset, index[element.tag], count(element.attributes.len())?, count(element.children.len())?]
        {
            w.word(word);
        }
        for (name, value) in element.attributes {
            let value = text(value)?;
            for word in [index[name.as_str()], index[value], attribute_float(value)?, u32::from(value == "true")] {
                w.word(word);
            }
        }
        w.words(&element.children, false);
    }
    Ok(w.data)
}

const SHOT: &[(&str, usize, bool)] = &[
    ("distance", 1, false),
    ("lens_length", 1, false),
    ("smoothing", 4, false),
    ("reference_weights", 10, false),
    ("board_offset", 1, false),
    ("position_heading", 1, false),
    ("position_elevation", 1, false),
    ("framing", 3, false),
    ("follow_subject_in_air", 1, true),
    ("mirror_for_stance", 1, true),
    ("snap_to_reference_point", 1, true),
    ("use_previous_shot", 1, true),
    ("use_drop_predictor", 1, true),
    ("use_free_camera_stick", 1, true),
    ("avoidance_override", 1, true),
    ("blur", 1, false),
    ("transition_blur", 1, false),
    ("subject_opacity", 1, false),
    ("collision_hint", 1, true),
    ("anchor", 1, true),
    ("compass_north", 1, true),
    ("world_heading", 1, false),
    ("arm_orientation", 4, false),
    ("camera_orientation", 4, false),
];
const SHOT_TAIL: &[&str] = &[
    "transition_time",
    "transition_units",
    "children",
    "blend_points",
    "blend_value",
    "blend_type",
    "blend_smoothing",
];

fn sized_words(w: &mut Writer, value: &Value, size: usize) -> Result<()> {
    let values = array(value)?;
    ensure!(values.len() == size, "expected {size} float words");
    for value in values {
        w.word(bits(value)?);
    }
    Ok(())
}

/// Encode camera shots and the two sampled camera shakes.
pub fn camera(value: &Value) -> Result<Vec<u8>> {
    let mut w = Writer::new(b"ATCAM001");
    w.string(text(&value["source_identity"])?);
    let shots = array(&value["shots"])?;
    w.word(count(shots.len())?);
    for shot in shots {
        let expected = ["name", "shot_type"]
            .into_iter()
            .chain(SHOT.iter().map(|(name, _, _)| *name))
            .chain(SHOT_TAIL.iter().copied());
        ensure!(object(shot)?.keys().map(String::as_str).eq(expected), "camera shot fields must be in format order");
        w.string(text(&shot["name"])?);
        w.word(uint(&shot["shot_type"])?);
        for &(name, size, integer) in SHOT {
            if size == 1 {
                w.word(if integer { uint(&shot[name])? } else { bits(&shot[name])? });
            } else {
                sized_words(&mut w, &shot[name], size)?;
            }
        }
        w.word(bits(&shot["transition_time"])?);
        w.word(uint(&shot["transition_units"])?);
        let children = array(&shot["children"])?;
        ensure!(children.len() == 3, "a camera shot has three child slots");
        for child in children {
            w.word(u32::from(!child.is_null()));
            if !child.is_null() {
                w.string(text(child)?);
            }
        }
        sized_words(&mut w, &shot["blend_points"], 3)?;
        w.word(bits(&shot["blend_value"])?);
        w.word(uint(&shot["blend_type"])?);
        w.word(bits(&shot["blend_smoothing"])?);
    }
    let shakes = array(&value["shakes"])?;
    ensure!(shakes.len() == 2, "camera data has two shakes");
    for shake in shakes {
        let rotations = array(&shake["rotations"])?;
        let translations = array(&shake["translations"])?;
        ensure!(rotations.len() == translations.len(), "a shake has one translation per rotation");
        w.word(count(rotations.len())?);
        for (rotation, translation) in rotations.iter().zip(translations) {
            sized_words(&mut w, rotation, 4)?;
            sized_words(&mut w, translation, 4)?;
        }
    }
    Ok(w.data)
}

/// Encode gesture sets and their ordered two-dimensional stick patterns.
pub fn gestures(value: &Value) -> Result<Vec<u8>> {
    let mut w = Writer::new(b"ATGEST01");
    let sets = array(value)?;
    w.word(count(sets.len())?);
    for gesture in sets {
        w.string(text(&gesture["name"])?);
        w.word(uint(&gesture["stick"])?);
        let patterns = array(&gesture["patterns"])?;
        w.word(count(patterns.len())?);
        for pattern in patterns {
            w.string(text(&pattern["name"])?);
            w.word(bits(&pattern["tolerance_squared"])?);
            let points = array(&pattern["points"])?;
            w.word(count(points.len())?);
            for point in points {
                sized_words(&mut w, point, 2)?;
            }
        }
    }
    Ok(w.data)
}

/// Encode physical skeleton records with their source offsets and 28-word bones.
pub fn physics(value: &Value) -> Result<Vec<u8>> {
    let mut w = Writer::new(b"ATPHYS01");
    w.string(text(&value["source_sha256"])?);
    let skeletons = array(&value["skeletons"])?;
    w.word(count(skeletons.len())?);
    for skeleton in skeletons {
        w.string(text(&skeleton["name"])?);
        w.wide(wide(&skeleton["source_offset"])?);
        let bones = array(&skeleton["bones"])?;
        w.word(count(bones.len())?);
        for bone in bones {
            w.string(text(&bone["name"])?);
            w.wide(wide(&bone["source_offset"])?);
            sized_words(&mut w, &bone["words"], 28)?;
        }
    }
    Ok(w.data)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn words(data: &[u8]) -> Vec<u32> {
        data.chunks_exact(4).map(|word| u32::from_le_bytes(word.try_into().unwrap())).collect()
    }

    fn shot() -> Value {
        let mut shot = Map::new();
        shot.insert("name".into(), json!("view"));
        shot.insert("shot_type".into(), json!(7));
        for &(name, size, integer) in SHOT {
            let value = if integer { json!(2) } else { json!(1.5) };
            shot.insert(name.into(), if size == 1 { value } else { Value::Array(vec![value; size]) });
        }
        for (name, value) in [
            ("transition_time", json!(-0.0)),
            ("transition_units", json!(3)),
            ("children", json!([null, "next", null])),
            ("blend_points", json!([1, 2, 3])),
            ("blend_value", json!("0x7fc01234")),
            ("blend_type", json!(4)),
            ("blend_smoothing", json!(0.5)),
        ] {
            shot.insert(name.into(), value);
        }
        Value::Object(shot)
    }

    #[test]
    fn reflected_fields_pack_big_endian_bytes_inside_little_endian_words() {
        for (value, size, expected) in [
            (json!(["Int8", -128]), 1, vec![0x80]),
            (json!(["Int16", -2]), 2, vec![0xfffe]),
            (json!(["Int32", -2]), 4, vec![0xffff_fffe]),
            (json!(["UInt64", u64::MAX]), 8, vec![u32::MAX, u32::MAX]),
            (json!(["Int64", i64::MIN]), 8, vec![0x8000_0000, 0]),
            (json!(["Bool", true]), 1, vec![1]),
            (json!(["Bool", true, 5]), 5, vec![0x0100_0000, 0]),
            (json!(["Float", -0.0]), 4, vec![0x8000_0000]),
            (json!(["Float", "0x7fc01234"]), 4, vec![0x7fc0_1234]),
            (json!(["Custom", {"words": ["0x11223344", "0x00000055"], "bytes": 5}]), 5, vec![0x1122_3344, 0x55]),
        ] {
            let field = field("value", &value).unwrap();
            assert_eq!(field.size, size);
            assert_eq!(field.words, expected);
        }
        let source = json!(["Text", "雪"]);
        let field = field("name", &source).unwrap();
        assert_eq!((field.size, field.text), (3, Some("雪")));
        assert_eq!(field.kind, "EA::Reflection::Text");
        for invalid in [
            json!(["UInt8", 256]),
            json!(["Int8", -129]),
            json!(["UInt64", -1]),
            json!(["Int64", u64::MAX]),
            json!(["Int32", 1.0]),
            json!(["Float", true]),
            json!(["Text", 7]),
            json!(["Float", 1, 4]),
            json!(["Bool", true, 1]),
            json!(["Custom", {"words": [0], "bytes": 4}]),
        ] {
            assert!(super::field("value", &invalid).is_err(), "{invalid}");
        }
    }

    #[test]
    fn settings_sort_strings_but_preserve_record_field_order() {
        let value: Value = serde_json::from_str(
            r#"[
            {"category":"C","records":[{"key":"R","fields":{"z":["Text","é"],"a":["UInt16",258]}}]}
        ]"#,
        )
        .unwrap();
        let bytes = settings(&value).unwrap();
        let mut expected = b"ATATTR01".to_vec();
        expected.extend(7_u32.to_le_bytes());
        expected.extend(1_u32.to_le_bytes());
        for string in ["", "C", "EA::Reflection::Text", "EA::Reflection::UInt16", "R", "a", "z"] {
            expected.extend((string.len() as u32).to_le_bytes());
            expected.extend(string.as_bytes());
        }
        for word in [1_u32, 4, 0, 2, 6, 2, 1, 2] {
            expected.extend(word.to_le_bytes());
        }
        expected.extend("é".as_bytes());
        for word in [5_u32, 3, 0, 2, 0x0102] {
            expected.extend(word.to_le_bytes());
        }
        assert_eq!(bytes, expected);
    }

    #[test]
    fn graph_offsets_follow_source_text_and_children_follow_depth_first_order() {
        let value: Value = serde_json::from_str(
            r#"{
            "root":{"x":"-0.0","flag":"true"},"children":[
                {"leaf":{"n":"1.25"}}, {"leaf":{}}
            ]
        }"#,
        )
        .unwrap();
        let bytes = graph(&value).unwrap();
        let mut expected = b"ATGRPH01".to_vec();
        for word in [8_u32, 3] {
            expected.extend(word.to_le_bytes());
        }
        for string in ["-0.0", "1.25", "flag", "leaf", "n", "root", "true", "x"] {
            expected.extend((string.len() as u32).to_le_bytes());
            expected.extend(string.as_bytes());
        }
        for word in
            [0_u32, 5, 2, 2, 7, 0, 0x8000_0000, 0, 2, 6, 0, 1, 1, 2, 40, 3, 1, 0, 4, 1, 0x3fa0_0000, 0, 65, 3, 0, 0]
        {
            expected.extend(word.to_le_bytes());
        }
        assert_eq!(bytes, expected);
        for (text, expected) in [
            ("+1.", 1_f32.to_bits()),
            ("-.5e+1", (-5_f32).to_bits()),
            ("1e-45", 1),
            (" 1", 0),
            ("NaN", 0),
            ("1e", 0),
            ("true", 0),
        ] {
            assert_eq!(attribute_float(text).unwrap(), expected, "{text}");
        }
        assert!(attribute_float("1e999").is_err());
        assert!(graph(&json!({"one": {}, "two": {}})).is_err());
        assert!(graph(&json!({"tag": {"number": 1}})).is_err());
    }

    #[test]
    fn camera_preserves_integer_words_child_slots_and_interleaved_shake_samples() {
        let mut value = json!({
            "source_identity": "id", "shots": [],
            "shakes": [
                {"rotations": [[1,2,3,4]], "translations": [[5,6,7,8]]},
                {"rotations": [], "translations": []}
            ]
        });
        value["shots"] = Value::Array(vec![shot()]);
        let bytes = camera(&value).unwrap();
        let mut expected = b"ATCAM001".to_vec();
        expected.extend(2_u32.to_le_bytes());
        expected.extend(b"id");
        for word in [1_u32, 4] {
            expected.extend(word.to_le_bytes());
        }
        expected.extend(b"view");
        expected.extend(7_u32.to_le_bytes());
        let shot_words: [u32; 44] = [
            0x3fc00000, 0x3fc00000, 0x3fc00000, 0x3fc00000, 0x3fc00000, 0x3fc00000, 0x3fc00000, 0x3fc00000, 0x3fc00000,
            0x3fc00000, 0x3fc00000, 0x3fc00000, 0x3fc00000, 0x3fc00000, 0x3fc00000, 0x3fc00000, 0x3fc00000, 0x3fc00000,
            0x3fc00000, 0x3fc00000, 0x3fc00000, 0x3fc00000, 2, 2, 2, 2, 2, 2, 2, 0x3fc00000, 0x3fc00000, 0x3fc00000, 2,
            2, 2, 0x3fc00000, 0x3fc00000, 0x3fc00000, 0x3fc00000, 0x3fc00000, 0x3fc00000, 0x3fc00000, 0x3fc00000,
            0x3fc00000,
        ];
        for word in shot_words {
            expected.extend(word.to_le_bytes());
        }
        for word in [0x80000000_u32, 3, 0, 1, 4] {
            expected.extend(word.to_le_bytes());
        }
        expected.extend(b"next");
        for word in [0_u32, 0x3f800000, 0x40000000, 0x40400000, 0x7fc01234, 4, 0x3f000000, 1] {
            expected.extend(word.to_le_bytes());
        }
        for value in 1..=8 {
            expected.extend((value as f32).to_bits().to_le_bytes());
        }
        expected.extend(0_u32.to_le_bytes());
        assert_eq!(bytes, expected);
        value["shots"][0]["children"] = json!([null]);
        assert!(camera(&value).is_err());
        value["shots"][0] = shot();
        value["shakes"][0]["translations"] = json!([]);
        assert!(camera(&value).is_err());
        value["shakes"][0]["translations"] = json!([[5, 6, 7, 8]]);
        let shot = value["shots"][0].as_object_mut().unwrap();
        let name = shot.shift_remove("name").unwrap();
        shot.insert("name".into(), name);
        assert!(camera(&value).is_err());
    }

    #[test]
    fn gestures_and_physics_keep_raw_words_and_wide_offsets() {
        let value = json!([{"name":"g","stick":1,"patterns":[
            {"name":"p","tolerance_squared":"0x7fc01234","points":[[-0.0,1]]}
        ]}]);
        let bytes = gestures(&value).unwrap();
        let mut expected = b"ATGEST01".to_vec();
        for word in [1_u32, 1] {
            expected.extend(word.to_le_bytes());
        }
        expected.extend(b"g");
        for word in [1_u32, 1, 1] {
            expected.extend(word.to_le_bytes());
        }
        expected.extend(b"p");
        for word in [0x7fc01234_u32, 1, 0x80000000, 0x3f800000] {
            expected.extend(word.to_le_bytes());
        }
        assert_eq!(bytes, expected);
        assert!(gestures(&json!([{"name":"g","stick":true,"patterns":[]}])).is_err());
        let mut physics_value = json!({"source_sha256":"s","skeletons":[
            {"name":"k","source_offset":4294967297_u64,"bones":[
                {"name":"b","source_offset":u64::MAX,"words":vec!["0x80000000"; 28]}
            ]}
        ]});
        let bytes = physics(&physics_value).unwrap();
        let mut expected = b"ATPHYS01".to_vec();
        expected.extend(1_u32.to_le_bytes());
        expected.extend(b"s");
        for word in [1_u32, 1] {
            expected.extend(word.to_le_bytes());
        }
        expected.extend(b"k");
        expected.extend(4294967297_u64.to_le_bytes());
        for word in [1_u32, 1] {
            expected.extend(word.to_le_bytes());
        }
        expected.extend(b"b");
        expected.extend(u64::MAX.to_le_bytes());
        expected.extend((0..28).flat_map(|_| 0x80000000_u32.to_le_bytes()));
        assert_eq!(bytes, expected);
        assert_eq!(words(&bytes[bytes.len() - 112..]), vec![0x80000000; 28]);
        physics_value["skeletons"][0]["bones"][0]["words"] = json!([0]);
        assert!(physics(&physics_value).is_err());
    }
}
