//! Deterministic readable simulation data to compact, indexed runtime bytes.

mod motion;
mod runtime;

use anyhow::{Context, Result, bail, ensure};
use hakuba_skate_schema::{Package, Reader, safe_path};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, fs, path::Path};

/// Paths are asset-relative choices. No source path may escape the asset's `src/`.
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    pub descriptor: String,
}

pub(super) fn array(v: &Value) -> Result<&Vec<Value>> {
    v.as_array().context("expected array")
}
pub(super) fn text(v: &Value) -> Result<&str> {
    v.as_str().context("expected string")
}
pub(super) fn uint(v: &Value) -> Result<u32> {
    u32::try_from(wide(v)?).context("expected u32")
}
pub(super) fn wide(v: &Value) -> Result<u64> {
    v.as_u64().context("expected unsigned integer")
}
pub(super) fn version(v: &Value) -> Result<()> {
    ensure!(v["version"] == 1, "unsupported simulation source version");
    Ok(())
}
/// JSON decimals pass through f64 before rounding to binary32, including negative zero.
pub(super) fn bits(v: &Value) -> Result<u32> {
    if let Some(s) = v.as_str() {
        ensure!(
            s.len() == 10
                && s.starts_with("0x")
                && s[2..].bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
            "invalid raw float word"
        );
        return Ok(u32::from_str_radix(&s[2..], 16)?);
    }
    let number = v.as_f64().context("expected finite number or raw word")?;
    ensure!(number.is_finite(), "nonfinite number must use its raw word");
    Ok((number as f32).to_bits())
}

pub(super) struct Writer {
    pub data: Vec<u8>,
}
impl Writer {
    pub fn new(magic: &[u8; 8]) -> Self {
        Self { data: magic.to_vec() }
    }
    pub fn word(&mut self, v: u32) {
        self.data.extend(v.to_le_bytes());
    }
    pub fn wide(&mut self, v: u64) {
        self.data.extend(v.to_le_bytes());
    }
    pub fn string(&mut self, v: &str) {
        self.word(v.len().try_into().expect("source text fits u32"));
        self.data.extend(v.as_bytes());
    }
    pub fn words(&mut self, words: &[u32], counted: bool) {
        if counted {
            self.word(words.len().try_into().expect("source array fits u32"));
        }
        for &word in words {
            self.word(word);
        }
    }
    pub fn strings(&mut self, v: &Value) -> Result<()> {
        let values = array(v)?;
        self.word(values.len().try_into()?);
        for value in values {
            self.string(text(value)?);
        }
        Ok(())
    }
}

/// JSON object order is meaningful; duplicate keys must not silently replace earlier source records.
struct UniqueValue(Value);
impl<'de> Deserialize<'de> for UniqueValue {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> std::result::Result<Self, D::Error> {
        struct Visitor;
        impl<'de> serde::de::Visitor<'de> for Visitor {
            type Value = UniqueValue;
            fn expecting(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                formatter.write_str("JSON without duplicate object keys")
            }
            fn visit_bool<E: serde::de::Error>(self, value: bool) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(Value::Bool(value)))
            }
            fn visit_i64<E: serde::de::Error>(self, value: i64) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(value.into()))
            }
            fn visit_u64<E: serde::de::Error>(self, value: u64) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(value.into()))
            }
            fn visit_f64<E: serde::de::Error>(self, value: f64) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(Value::Number(
                    serde_json::Number::from_f64(value).ok_or_else(|| E::custom("nonfinite JSON number"))?,
                )))
            }
            fn visit_str<E: serde::de::Error>(self, value: &str) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(value.into()))
            }
            fn visit_string<E: serde::de::Error>(self, value: String) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(value.into()))
            }
            fn visit_none<E: serde::de::Error>(self) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(Value::Null))
            }
            fn visit_unit<E: serde::de::Error>(self) -> std::result::Result<Self::Value, E> {
                Ok(UniqueValue(Value::Null))
            }
            fn visit_seq<A: serde::de::SeqAccess<'de>>(
                self,
                mut sequence: A,
            ) -> std::result::Result<Self::Value, A::Error> {
                let mut values = Vec::new();
                while let Some(UniqueValue(value)) = sequence.next_element()? {
                    values.push(value);
                }
                Ok(UniqueValue(Value::Array(values)))
            }
            fn visit_map<A: serde::de::MapAccess<'de>>(self, mut map: A) -> std::result::Result<Self::Value, A::Error> {
                let mut values = serde_json::Map::new();
                while let Some((key, UniqueValue(value))) = map.next_entry::<String, UniqueValue>()? {
                    if values.insert(key.clone(), value).is_some() {
                        return Err(serde::de::Error::custom(format!("duplicate JSON key: {key}")));
                    }
                }
                Ok(UniqueValue(Value::Object(values)))
            }
        }
        deserializer.deserialize_any(Visitor)
    }
}
fn parse(bytes: &[u8]) -> Result<Value> {
    Ok(serde_json::from_slice::<UniqueValue>(bytes)?.0)
}
fn load(path: &Path) -> Result<Value> {
    let bytes = fs::read(path).with_context(|| format!("reading {}", path.display()))?;
    parse(&bytes).with_context(|| format!("reading {}", path.display()))
}
fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn source(root: &Path, path: &str) -> Result<std::path::PathBuf> {
    ensure!(safe_path(path), "unsafe simulation source path");
    Ok(root.join(path))
}

const FORMATS: [&str; 8] =
    ["ATATTR01", "ATGEST01", "ATGRPH01", "ATPHYS01", "ATSKEL01", "ATCLIP01", "ATMETA01", "ATCAM001"];
const RUNTIME: [(&str, &str); 7] = [
    ("settings.json", "settings.skate"),
    ("action-graph.json", "action.graph"),
    ("motion-graph.json", "motion.graph"),
    ("camera-graph.json", "camera.graph"),
    ("camera.json", "camera.skate"),
    ("gestures.json", "gestures.skate"),
    ("physics-skeletons.json", "physics-skeletons.skate"),
];
fn magic(name: &str) -> Result<&'static [u8; 8]> {
    Ok(match name {
        "settings.skate" => b"ATATTR01",
        "gestures.skate" => b"ATGEST01",
        "physics-skeletons.skate" => b"ATPHYS01",
        "action.graph" | "motion.graph" | "camera.graph" => b"ATGRPH01",
        "animation/rig.skate" => b"ATSKEL01",
        "metadata/bank-0.skate" | "metadata/bank-1.skate" => b"ATMETA01",
        "camera.skate" => b"ATCAM001",
        _ if name.starts_with("animation/clips/") && name.ends_with(".skate") => b"ATCLIP01",
        _ => bail!("unsupported simulation payload: {name}"),
    })
}

/// Every generated payload must match the supplied integrity manifest before it can be published.
fn verify(root: &Path, settings: &Settings, package: &Package<'_>) -> Result<()> {
    let descriptor = load(&source(root, &settings.descriptor)?)?;
    ensure!(descriptor["version"] == 4, "unsupported simulation descriptor");
    let manifest_name = text(&descriptor["manifest"])?;
    let manifest_raw = package.get(manifest_name)?;
    ensure!(sha(manifest_raw) == text(&descriptor["manifest_sha256"])?, "simulation manifest checksum differs");
    let manifest = parse(manifest_raw)?;
    ensure!(manifest["version"] == 1, "unsupported simulation manifest");
    for value in [&descriptor, &manifest] {
        ensure!(
            array(&value["formats"])?.iter().map(text).collect::<Result<Vec<_>>>()? == FORMATS,
            "simulation formats differ"
        );
    }
    let identity = text(&manifest["source_identity"])?;
    ensure!(
        identity.len() == 64 && identity.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "invalid source identity"
    );
    ensure!(text(&descriptor["source_identity"])? == identity, "simulation source identity differs");
    let expected = &descriptor["expected"];
    let entries = manifest["files"].as_object().context("missing payload manifest")?;
    ensure!(
        entries.len() as u64 == wide(&expected["payloads"])? && package.len() == entries.len() + 1,
        "simulation payload count differs"
    );
    for required in [
        "settings.skate",
        "gestures.skate",
        "physics-skeletons.skate",
        "action.graph",
        "motion.graph",
        "camera.graph",
        "camera.skate",
        "animation/rig.skate",
        "metadata/bank-0.skate",
        "metadata/bank-1.skate",
    ] {
        ensure!(entries.contains_key(required), "missing required simulation payload: {required}");
    }
    let mut total = 0u64;
    for (name, record) in entries {
        ensure!(safe_path(name), "unsafe simulation payload path");
        let bytes = package.get(name)?;
        ensure!(
            !bytes.is_empty() && bytes.len() as u64 == wide(&record["bytes"])?,
            "simulation payload size differs: {name}"
        );
        ensure!(sha(bytes) == text(&record["sha256"])?, "simulation payload digest differs: {name}");
        Reader::new(bytes, magic(name)?)?;
        total += bytes.len() as u64;
    }
    let mut rig = Reader::new(package.get("animation/rig.skate")?, b"ATSKEL01")?;
    let bones = rig.word()?;
    ensure!(bones > 0 && bones <= 255 && rig.word()? <= 1, "invalid simulation rig header");
    let mut clips = 0u64;
    let mut frames = 0u64;
    for (name, bytes) in package.entries().filter(|(name, _)| name.starts_with("animation/clips/")) {
        let mut r = Reader::new(bytes, b"ATCLIP01")?;
        let clip = r.string()?;
        let bank = r.word()?;
        ensure!(bank <= 1 && name == format!("animation/clips/{bank}/{clip}.skate"), "invalid clip identity");
        r.take(8 + 4 + 7 * 4)?;
        ensure!(r.word()? <= 1 && r.word()? == bones, "invalid clip weights");
        r.take(bones as usize * 4)?;
        let frame_count = r.word()?;
        ensure!(frame_count > 0 && r.word()? == bones, "invalid clip dimensions");
        for _ in 0..bones * 10 {
            let samples = r.word()?;
            ensure!(samples == 1 || samples == frame_count, "invalid compact clip track");
            r.take(samples as usize * 4)?;
        }
        r.end()?;
        clips += 1;
        frames += frame_count as u64;
    }
    let mut gestures = Reader::new(package.get("gestures.skate")?, b"ATGEST01")?;
    let sets = gestures.word()?;
    ensure!(sets > 0, "empty gesture sets");
    let mut patterns = 0u64;
    let mut set_names = std::collections::BTreeSet::new();
    for _ in 0..sets {
        let name = gestures.string()?;
        ensure!(!name.is_empty() && set_names.insert(name) && gestures.word()? <= 1, "invalid gesture set");
        let count = gestures.word()?;
        patterns += count as u64;
        for _ in 0..count {
            ensure!(!gestures.string()?.is_empty(), "empty gesture pattern");
            gestures.take(4)?;
            let points = gestures.word()?;
            ensure!((2..=15).contains(&points), "invalid gesture points");
            gestures.take(points as usize * 8)?;
        }
    }
    gestures.end()?;
    let banks = package.entries().filter(|(name, _)| name.starts_with("metadata/")).count() as u64;
    ensure!(banks == 2, "simulation requires both metadata banks");
    for (key, actual) in [
        ("bytes", total),
        ("clips", clips),
        ("animation_frames", frames),
        ("patterns", patterns),
        ("metadata_banks", banks),
    ] {
        ensure!(
            actual > 0 && actual == wide(&manifest[key])? && actual == wide(&expected[key])?,
            "simulation count differs: {key}"
        );
    }
    let mut physics = Reader::new(package.get("physics-skeletons.skate")?, b"ATPHYS01")?;
    ensure!(physics.string()? == identity, "physics source identity differs");
    let mut metadata = Reader::new(package.get("metadata/bank-0.skate")?, b"ATMETA01")?;
    metadata.string()?;
    ensure!(metadata.string()? == identity, "animation source identity differs");
    Ok(())
}

pub fn export(folder: &Path, settings: &Settings, output: &Path) -> Result<()> {
    let root = folder.join("src");
    let rig = load(&root.join("motion/rig.json"))?;
    let names = array(&rig["bones"])?.iter().map(|b| Ok(text(&b["name"])?.to_owned())).collect::<Result<Vec<_>>>()?;
    let mut built = BTreeMap::new();
    built.insert("animation/rig.skate".into(), motion::rig(&rig)?);
    for bank in 0..2 {
        built.insert(
            format!("metadata/bank-{bank}.skate"),
            motion::metadata(&load(&root.join(format!("motion/metadata/bank-{bank}.json")))?, &names)?,
        );
    }
    for path in crate::files(&root.join("motion/clips"))? {
        ensure!(path.extension().is_some_and(|e| e == "json"), "unknown clip source");
        let v = load(&path)?;
        let name = text(&v["name"])?;
        let bank = uint(&v["bank"])?;
        ensure!(
            bank <= 1 && path == root.join(format!("motion/clips/{bank}/{name}.json")),
            "clip path differs from identity"
        );
        let key = format!("animation/clips/{bank}/{name}.skate");
        ensure!(built.insert(key, motion::clip(&v, &names)?).is_none(), "duplicate clip");
    }
    let found = crate::files(&root.join("runtime"))?;
    ensure!(
        found.len() == RUNTIME.len()
            && found.iter().all(|path| RUNTIME.iter().any(|(name, _)| path == &root.join("runtime").join(name))),
        "runtime source files differ"
    );
    for (json, binary) in RUNTIME {
        let v = load(&root.join("runtime").join(json))?;
        let bytes = match binary {
            "settings.skate" => runtime::settings(&v)?,
            "camera.skate" => runtime::camera(&v)?,
            "gestures.skate" => runtime::gestures(&v)?,
            "physics-skeletons.skate" => runtime::physics(&v)?,
            _ => runtime::graph(&v)?,
        };
        built.insert(binary.into(), bytes);
    }
    let descriptor = load(&source(&root, &settings.descriptor)?)?;
    let manifest_name = text(&descriptor["manifest"])?;
    built.insert(manifest_name.into(), fs::read(source(&root, manifest_name)?)?);
    let bytes = hakuba_skate_schema::encode(&built)?;
    verify(&root, settings, &Package::parse(&bytes)?)?;
    fs::write(output, bytes)?;
    Ok(())
}

pub fn output_problems(settings: &Settings, output: &Path) -> Vec<String> {
    let check = || -> Result<()> {
        let bytes = fs::read(output)?;
        let package = Package::parse(&bytes)?;
        verify(&output.parent().context("simulation output has no folder")?.join("src"), settings, &package)
    };
    match check() {
        Ok(()) => Vec::new(),
        Err(error) => vec![format!("invalid simulation export: {error:#}")],
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn source_json_rejects_duplicate_keys_without_losing_order_or_negative_zero() {
        assert!(parse(br#"{"a":1,"a":2}"#).is_err());
        assert!(parse(br#"{"nested":{"a":1,"a":2}}"#).is_err());
        let value = parse(br#"{"z":-0.0,"a":1}"#).unwrap();
        assert_eq!(value.as_object().unwrap().keys().map(String::as_str).collect::<Vec<_>>(), ["z", "a"]);
        assert_eq!(bits(&value["z"]).unwrap(), 0x80000000);
    }
    #[test]
    fn decimal_float_rounding_and_raw_words() {
        assert_eq!(bits(&serde_json::from_str::<Value>("-0.0").unwrap()).unwrap(), 0x80000000);
        assert_eq!(bits(&serde_json::json!("0x7fc01234")).unwrap(), 0x7fc01234);
        assert_eq!(bits(&serde_json::json!(0.1)).unwrap(), 0.1f32.to_bits());
        assert!(bits(&serde_json::json!(true)).is_err());
        assert!(bits(&serde_json::json!("0xFFFFFFFF")).is_err());
    }
}
