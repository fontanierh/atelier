//! Execution-only native verification context issued from current source-cook evidence.
use crate::keys::PreparedUnit;
use crate::results::zen_cook::{CookLocator, SourceCookEvidence};
use crate::schema::{ResultRecord, StoredFile};
use crate::source_hashes::{sha256, valid_digest};
use serde_json::{Value, json};
use std::fs::{self, OpenOptions};
use std::io::{Read, Seek, SeekFrom};
use std::os::unix::fs::OpenOptionsExt;
use std::path::Path;

pub struct NativeVerifyContext {
    request: Value,
    record_sha256: String,
    producer_key: String,
}

fn text<'a>(value: &'a Value, field: &str) -> Result<&'a str, String> {
    value
        .get(field)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("native metadata omits {field}"))
}
fn native_hash(value: &str) -> bool {
    value.len() == 40
        && value
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
        && value.bytes().any(|c| c != b'0')
}

/// The fixed producer archives its native transport report with the complete cooked root.
pub(crate) fn metadata_file(record: &ResultRecord) -> Result<StoredFile, String> {
    let root = record
        .ingredients
        .params
        .get("cook_root")
        .and_then(Value::as_str)
        .ok_or("cook producer has no metadata root")?;
    let rows = record
        .ingredients
        .params
        .get("recipe")
        .and_then(|v| v.get("outputs"))
        .and_then(Value::as_array)
        .ok_or("cook producer has no output mapping")?;
    let rows = rows
        .iter()
        .filter(|row| row.get("path").and_then(Value::as_str) == Some(root))
        .collect::<Vec<_>>();
    if rows.len() != 1 {
        return Err("ambiguous native metadata root".into());
    }
    let name = text(rows[0], "file")?;
    let files = record
        .outputs
        .iter()
        .filter(|item| item.item.class == "Data" && item.external_locator.is_none())
        .flat_map(|item| &item.files)
        .filter(|file| file.path == name)
        .collect::<Vec<_>>();
    if files.len() != 1 {
        return Err("native metadata root is not a certified Data output".into());
    }
    Ok(files[0].clone())
}

fn header(input: &mut impl Read) -> Result<Option<(String, u64, u8)>, String> {
    let mut bytes = [0; 512];
    input.read_exact(&mut bytes).map_err(|e| e.to_string())?;
    if bytes.iter().all(|b| *b == 0) {
        return Ok(None);
    }
    let string = |slice: &[u8]| {
        std::str::from_utf8(slice)
            .map(|v| v.trim_end_matches('\0').to_string())
            .map_err(|e| e.to_string())
    };
    let check = u64::from_str_radix(
        string(&bytes[148..156])?.trim_matches(|c| c == ' ' || c == '\0'),
        8,
    )
    .map_err(|e| e.to_string())?;
    let actual = bytes
        .iter()
        .enumerate()
        .map(|(i, byte)| {
            if (148..156).contains(&i) {
                32
            } else {
                u64::from(*byte)
            }
        })
        .sum::<u64>();
    if actual != check {
        return Err("native metadata archive header checksum differs".into());
    }
    let name = string(&bytes[..100])?;
    let prefix = string(&bytes[345..500])?;
    let name = if prefix.is_empty() {
        name
    } else {
        format!("{prefix}/{name}")
    };
    if name.contains('\\') || name.split('/').any(|p| p == "..") || name.starts_with('/') {
        return Err("unsafe metadata archive member".into());
    }
    let size = u64::from_str_radix(
        string(&bytes[124..136])?.trim_matches(|c| c == ' ' || c == '\0'),
        8,
    )
    .map_err(|e| e.to_string())?;
    Ok(Some((name, size, bytes[156])))
}
fn report_from_archive(path: &Path, expected: &StoredFile) -> Result<Value, String> {
    let mut input = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)
        .map_err(|e| e.to_string())?;
    if !input.metadata().map_err(|e| e.to_string())?.is_file() {
        return Err("metadata archive is not regular".into());
    }
    let mut hash = sha2::Sha256::new();
    use sha2::Digest;
    let mut block = [0u8; 65536];
    let mut size = 0u64;
    loop {
        let n = input.read(&mut block).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        hash.update(&block[..n]);
        size += n as u64;
    }
    if size != expected.size || format!("{:x}", hash.finalize()) != expected.digest {
        return Err("native metadata archive differs from certified producer bytes".into());
    }
    input.seek(SeekFrom::Start(0)).map_err(|e| e.to_string())?;
    let mut manifest = None;
    let mut report = None;
    while let Some((name, length, kind)) = header(&mut input)? {
        if !matches!(kind, 0 | b'0' | b'5') {
            return Err("native metadata archive contains a link/special member".into());
        }
        if name == "atelier-root.json" || name == "root/atelier-native-cook.json" {
            if !matches!(kind, 0 | b'0') || length > 16 * 1024 * 1024 {
                return Err("native metadata member exceeds its finite bound".into());
            }
            let mut bytes = vec![0; usize::try_from(length).map_err(|e| e.to_string())?];
            input.read_exact(&mut bytes).map_err(|e| e.to_string())?;
            crate::py_data::validate_py_data_payload("JsonData", "native metadata", &bytes)?;
            if name == "atelier-root.json" {
                if manifest.is_some() {
                    return Err("duplicate native root manifest".into());
                }
                manifest =
                    Some(serde_json::from_slice::<Value>(&bytes).map_err(|e| e.to_string())?);
            } else {
                if report.is_some() {
                    return Err("duplicate native metadata report".into());
                }
                report = Some(bytes);
            }
        } else {
            input
                .seek(SeekFrom::Current(
                    i64::try_from(length).map_err(|e| e.to_string())?,
                ))
                .map_err(|e| e.to_string())?;
        }
        input
            .seek(SeekFrom::Current(((512 - length % 512) % 512) as i64))
            .map_err(|e| e.to_string())?;
    }
    let manifest = manifest.ok_or("missing native root manifest")?;
    let report = report.ok_or("missing native cook transport report")?;
    if manifest.get("version").and_then(Value::as_u64) != Some(1)
        || manifest.get("kind").and_then(Value::as_str) != Some("directory")
    {
        return Err("unsupported native metadata root".into());
    }
    let entries = manifest
        .get("entries")
        .and_then(Value::as_array)
        .ok_or("native metadata has no membership")?;
    let rows = entries
        .iter()
        .filter(|row| row.get(0).and_then(Value::as_str) == Some("atelier-native-cook.json"))
        .collect::<Vec<_>>();
    if rows.len() != 1
        || rows[0].get(1).and_then(Value::as_str) != Some("file")
        || rows[0].get(2).and_then(Value::as_u64) != Some(report.len() as u64)
        || rows[0].get(4).and_then(Value::as_str) != Some(sha256(&report).as_str())
    {
        return Err("native report differs from complete root membership".into());
    }
    serde_json::from_slice(&report).map_err(|e| e.to_string())
}

impl NativeVerifyContext {
    pub(crate) fn from_source(
        source: &SourceCookEvidence<'_>,
        unit: &PreparedUnit,
        metadata_archive: &Path,
        store_root: &Path,
        candidate: Option<&CookLocator>,
    ) -> Result<Self, String> {
        source.check()?;
        let record_sha256 = source.consumed_record_digest(unit)?.to_string();
        let producer = &source.result().result;
        let metadata = report_from_archive(metadata_archive, &metadata_file(producer)?)?;
        if metadata.get("version").and_then(Value::as_u64) != Some(1)
            || text(&metadata, "source_key")? != producer.key
        {
            return Err("native metadata source differs from current producer evidence".into());
        }
        let package = unit
            .ingredients()
            .params
            .get("package")
            .and_then(Value::as_str)
            .ok_or("native verifier omits package")?;
        let mode = unit
            .ingredients()
            .params
            .get("mode")
            .and_then(Value::as_str)
            .ok_or("native verifier omits mode")?;
        if !matches!(mode, "verify" | "restore") {
            return Err("unsupported native verification mode".into());
        }
        let rows = metadata
            .get("packages")
            .and_then(Value::as_array)
            .ok_or("native metadata omits packages")?;
        let matches = rows
            .iter()
            .filter(|row| row.get("source_package").and_then(Value::as_str) == Some(package))
            .collect::<Vec<_>>();
        if matches.len() != 1 {
            return Err("native report package is missing or ambiguous".into());
        }
        let row = matches[0];
        if text(row, "record_sha256")? != record_sha256
            || text(row, "input_key")? != producer.key
            || text(row, "status")? != "verified"
            || !native_hash(text(row, "native_stored_key")?)
            || !native_hash(text(row, "root_hash")?)
        {
            return Err("native report differs from certified CB/source".into());
        }
        let locator = if let Some(candidate) = candidate {
            if candidate.record_sha256 != record_sha256 || candidate.package != package {
                return Err("native candidate represents another certified CB".into());
            }
            candidate.clone()
        } else {
            CookLocator {
                version: 2,
                project: text(row, "project")?.into(),
                oplog: "Mac".into(),
                package: package.into(),
                source_key: producer.key.clone(),
                dependency_key: text(row, "native_stored_key")?.into(),
                entry_hash: text(row, "root_hash")?.into(),
                installed_entry_hash: text(row, "root_hash")?.into(),
                lifetime_marker: text(row, "marker_path")?.into(),
                record_path: text(row, "record_path")?.into(),
                project_file: text(row, "project_file")?.into(),
                record_sha256: record_sha256.clone(),
            }
        };
        locator.validate()?;
        let root = store_root.join("zen-cook");
        let record = Path::new(&locator.record_path);
        let project = Path::new(&locator.project_file);
        let marker = Path::new(&locator.lifetime_marker);
        if !store_root.is_absolute()
            || !record.starts_with(root.join("records"))
            || !project.starts_with(root.join("projects").join(&locator.source_key).join("view"))
            || marker
                != project
                    .parent()
                    .ok_or("missing native project parent")?
                    .join("Saved/Cooked/Mac/ue.projectstore")
        {
            return Err("native verifier namespace escapes owned store roles".into());
        }
        for path in [record, project, marker] {
            if path.canonicalize().map_err(|e| e.to_string())? != path
                || !fs::symlink_metadata(path)
                    .map_err(|e| e.to_string())?
                    .is_file()
            {
                return Err("native namespace contains an alias/special file".into());
            }
        }
        // The native call independently validates these expected hashes against the complete CB.
        let request = json!({"version":1,"mode":mode,"project":locator.project,"oplog":"Mac","source_package":package,"expected_stored_key":locator.dependency_key,"expected_root_hash":locator.entry_hash,"record_path":locator.record_path,"project_file":locator.project_file,"marker_path":locator.lifetime_marker,"input_key":locator.source_key,"runtime_project_file":""});
        Ok(Self {
            request,
            record_sha256,
            producer_key: producer.key.clone(),
        })
    }
    /// Only the verified owned scratch descriptor is late-bound; source authority stays sealed.
    pub fn carrier(&self, runtime_project_file: &Path) -> Result<Value, String> {
        if !runtime_project_file.is_absolute()
            || !valid_digest(&self.record_sha256)
            || !valid_digest(&self.producer_key)
        {
            return Err("invalid native verification carrier".into());
        }
        let mut request = self.request.clone();
        request["runtime_project_file"] =
            runtime_project_file.to_string_lossy().into_owned().into();
        Ok(
            json!({"version":1,"request":request,"record_sha256":self.record_sha256,"producer_key":self.producer_key}),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};
    static NEXT: AtomicU64 = AtomicU64::new(0);
    fn member(out: &mut Vec<u8>, name: &str, body: &[u8]) {
        let mut header = [0u8; 512];
        header[..name.len()].copy_from_slice(name.as_bytes());
        header[100..108].copy_from_slice(b"0000644\0");
        header[124..136].copy_from_slice(format!("{:011o}\0", body.len()).as_bytes());
        header[148..156].fill(b' ');
        header[156] = b'0';
        let checksum: u64 = header.iter().map(|b| u64::from(*b)).sum();
        header[148..156].copy_from_slice(format!("{checksum:06o}\0 ").as_bytes());
        out.extend(header);
        out.extend(body);
        out.resize(out.len() + (512 - body.len() % 512) % 512, 0);
    }
    #[test]
    fn native_transport_metadata_requires_certified_archive_and_exact_root_membership() {
        let report = br#"{"version":1,"source_key":"fixture","packages":[]}"#;
        let manifest = serde_json::to_vec(&json!({"version":1,"kind":"directory","entries":[
            ["","directory",0,493,null],["atelier-native-cook.json","file",report.len(),420,sha256(report)]]})).unwrap();
        let mut bytes = Vec::new();
        member(&mut bytes, "atelier-root.json", &manifest);
        member(&mut bytes, "root/atelier-native-cook.json", report);
        bytes.extend([0; 1024]);
        let path = std::env::temp_dir().join(format!(
            "atelier-native-metadata-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::write(&path, &bytes).unwrap();
        let stored = StoredFile {
            path: "metadata.tree.tar".into(),
            digest: sha256(&bytes),
            size: bytes.len() as u64,
            mode: 0o644,
        };
        assert_eq!(
            report_from_archive(&path, &stored).unwrap()["source_key"],
            "fixture"
        );
        let mut changed = bytes.clone();
        changed[1024] ^= 1;
        fs::write(&path, changed).unwrap();
        assert!(report_from_archive(&path, &stored).is_err());
        let mut bad = Vec::new();
        member(&mut bad, "atelier-root.json", &manifest);
        member(&mut bad, "root/atelier-native-cook.json", b"{}");
        bad.extend([0; 1024]);
        fs::write(&path, &bad).unwrap();
        let stored = StoredFile {
            digest: sha256(&bad),
            size: bad.len() as u64,
            ..stored
        };
        assert!(report_from_archive(&path, &stored).is_err());
        fs::remove_file(path).unwrap();
    }
}
