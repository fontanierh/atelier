//! Produced game-native editor modules and plugins, materialized from a unit's own keyed inputs.
//!
//! A unit that loads game-native classes declares `params.native_modules`:
//! `{editor: {slot, archive, modules: [{name, kind, loading_phase}]},
//!   plugins: [{name, slot, archive, descriptor_slot}]}`. Each `slot` names one of the unit's
//! content Items and `archive` the exact `.tree.tar` member of it: a complete deterministic
//! directory ROOT archive (the same format `unreal_controller::archive_digests` reads) holding a
//! produced `Binaries/Mac` folder. Each plugin's `descriptor_slot` is its own declared input file
//! (or a single-file Item) holding its `.uplugin`. Nothing is looked up in a checkout, the engine
//! or any global location; the archives are decoded into a new caller-owned scope, never linked.
//! This module makes no key, cache or launch decisions.

use crate::keys::{InputPayload, PreparedUnit};
use crate::staging::StagedJob;
use crate::unreal::{self, Binaries, Module, Plugin};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::{Read, Write};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};

/// The editor's module manifest inside a produced `Binaries/Mac` folder.
pub const MODULES_FILE: &str = "UnrealEditor.modules";
const MAX_MANIFEST: u64 = 16 * 1024 * 1024;
const MAX_DESCRIPTOR: u64 = 4 * 1024 * 1024;

/// An independent physical context: owned copies whose identities were computed from the copies.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PreparedNativeModules {
    pub editor: Binaries,
    pub modules: Vec<Module>,
    pub plugins: Vec<Plugin>,
}

#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    editor: EditorRequest,
    #[serde(default)]
    plugins: Vec<PluginRequest>,
}

#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct EditorRequest {
    slot: String,
    archive: String,
    modules: Vec<Module>,
}

#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct PluginRequest {
    name: String,
    slot: String,
    archive: String,
    descriptor_slot: String,
}

#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct RootManifest {
    version: u32,
    kind: String,
    entries: Vec<(String, String, u64, u32, Option<String>)>,
}

/// One staged content input: where the job holds it and its keyed payload.
struct Staged<'a> {
    path: PathBuf,
    payload: &'a InputPayload,
}

/// @cc [owner:fontanierh,label:correctness] keyed-produced-native-modules
/// A unit's game-native editor modules and plugins MUST come only from its own declared content
/// inputs: exact keyed `.tree.tar` members and descriptor files, verified against their keyed
/// digests, decoded completely into a new owned scope with no links, special files, traversal,
/// unlisted members or overwrites. The editor manifest MUST carry this engine's BuildId and
/// exactly the requested modules with their binaries; each plugin MUST be its own descriptor plus
/// its produced Binaries. Identities MUST be computed from the materialized copies.
pub fn prepare(
    unit: &PreparedUnit,
    staged: &StagedJob,
    scope: &Path,
    build_id: &str,
) -> Result<Option<PreparedNativeModules>, String> {
    let Some(value) = unit.ingredients().params.get("native_modules") else {
        return Ok(None);
    };
    let request: Request = serde_json::from_value(value.clone())
        .map_err(|e| format!("invalid native_modules parameters: {e}"))?;
    let content = &unit.ingredients().content;
    let inputs: BTreeMap<&str, Staged<'_>> = unit
        .inputs()
        .iter()
        .filter(|input| content.contains_key(&input.wire.name))
        .map(|input| {
            (
                input.wire.name.as_str(),
                Staged {
                    path: staged.job_dir().join(&input.wire.path),
                    payload: &input.payload,
                },
            )
        })
        .collect();
    materialize(&request, &inputs, scope, build_id).map(Some)
}

fn materialize(
    request: &Request,
    inputs: &BTreeMap<&str, Staged<'_>>,
    scope: &Path,
    build_id: &str,
) -> Result<PreparedNativeModules, String> {
    if build_id.is_empty() || build_id.chars().any(char::is_control) {
        return Err("native modules need the engine BuildId".into());
    }
    if !scope.is_absolute() {
        return Err("native module scope must be absolute".into());
    }
    fs::create_dir(scope).map_err(|e| format!("native module scope must be new: {e}"))?;
    let result = materialize_into(request, inputs, scope, build_id);
    if result.is_err() {
        let _ = fs::remove_dir_all(scope);
    }
    result
}

fn materialize_into(
    request: &Request,
    inputs: &BTreeMap<&str, Staged<'_>>,
    scope: &Path,
    build_id: &str,
) -> Result<PreparedNativeModules, String> {
    let editor = &request.editor;
    let mut names = BTreeSet::new();
    for module in &editor.modules {
        if !name_ok(&module.name) || !name_ok(&module.kind) || !name_ok(&module.loading_phase) {
            return Err(format!("invalid native module {:?}", module.name));
        }
        if !names.insert(module.name.as_str()) {
            return Err(format!("native module {} is requested twice", module.name));
        }
    }
    if names.is_empty() {
        return Err("native editor binaries need at least one requested module".into());
    }
    let dir = scope.join("editor");
    let files = extract(&archive(inputs, &editor.slot, &editor.archive)?, &dir)?;
    let libraries = module_libraries(&dir, &files, build_id)?;
    if libraries.keys().map(String::as_str).collect::<BTreeSet<_>>() != names {
        return Err("produced editor modules differ from the requested modules".into());
    }
    let identity = unreal::tree_identity(&dir, None).map_err(|e| e.to_string())?;
    let mut plugins = vec![];
    let mut seen = BTreeSet::new();
    for plugin in &request.plugins {
        if !name_ok(&plugin.name) || !seen.insert(plugin.name.as_str()) {
            return Err(format!("invalid or repeated native plugin {:?}", plugin.name));
        }
        let descriptor = descriptor(inputs, &plugin.descriptor_slot)?;
        let declared = descriptor_modules(&descriptor)?;
        let folder = scope.join("plugins").join(&plugin.name);
        fs::create_dir_all(folder.parent().expect("plugins folder")).map_err(|e| e.to_string())?;
        fs::create_dir(&folder).map_err(|e| e.to_string())?;
        write_new(&folder.join(format!("{}.uplugin", plugin.name)), &descriptor, 0o644)?;
        fs::create_dir(folder.join("Binaries")).map_err(|e| e.to_string())?;
        let binaries = folder.join("Binaries/Mac");
        let files = extract(&archive(inputs, &plugin.slot, &plugin.archive)?, &binaries)?;
        let built = module_libraries(&binaries, &files, build_id)?;
        if built.keys().any(|name| !declared.contains(name)) {
            return Err(format!("plugin {} produced a module its descriptor does not declare", plugin.name));
        }
        plugins.push(Plugin {
            name: plugin.name.clone(),
            identity: unreal::tree_identity(&folder, Some(&plugin.name)).map_err(|e| e.to_string())?,
            dir: folder,
        });
    }
    Ok(PreparedNativeModules {
        editor: Binaries { identity, dir },
        modules: editor.modules.clone(),
        plugins,
    })
}

fn name_ok(text: &str) -> bool {
    !text.is_empty() && text.len() <= 128 && text.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'_')
}

fn relative_ok(text: &str) -> bool {
    !text.is_empty()
        && !text.starts_with('/')
        && !text.contains('\\')
        && !text.contains('\0')
        && text.split('/').all(|part| !part.is_empty() && part != "." && part != "..")
}

fn input<'a>(inputs: &'a BTreeMap<&str, Staged<'a>>, slot: &str) -> Result<&'a Staged<'a>, String> {
    inputs
        .get(slot)
        .ok_or_else(|| format!("native module slot {slot} is not a declared content input"))
}

fn regular(path: &Path) -> Result<fs::Metadata, String> {
    let metadata = fs::symlink_metadata(path).map_err(|e| format!("{}: {e}", path.display()))?;
    if !metadata.file_type().is_file() {
        return Err(format!("{} is not a regular staged file", path.display()));
    }
    Ok(metadata)
}

fn digest_file(path: &Path) -> Result<String, String> {
    let mut file = fs::File::open(path).map_err(|e| e.to_string())?;
    let mut hasher = Sha256::new();
    let mut buffer = [0; 64 * 1024];
    loop {
        let count = file.read(&mut buffer).map_err(|e| e.to_string())?;
        if count == 0 {
            break;
        }
        hasher.update(&buffer[..count]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

/// The exact keyed `.tree.tar` member of an Item input, checked against its keyed digest.
fn archive(inputs: &BTreeMap<&str, Staged<'_>>, slot: &str, member: &str) -> Result<PathBuf, String> {
    let staged = input(inputs, slot)?;
    let InputPayload::Item { files, .. } = staged.payload else {
        return Err(format!("native module slot {slot} is not an Item"));
    };
    if !relative_ok(member) || !member.ends_with(".tree.tar") {
        return Err(format!("native module archive {member:?} is not an exact ROOT archive member"));
    }
    let file = files
        .iter()
        .find(|file| file.path == member)
        .ok_or_else(|| format!("native module slot {slot} has no member {member}"))?;
    if fs::symlink_metadata(&staged.path).map_err(|e| e.to_string())?.file_type().is_symlink() {
        return Err(format!("native module slot {slot} is linked"));
    }
    let path = staged.path.join(member);
    let mut parent = path.parent();
    while let Some(folder) = parent {
        if folder == staged.path {
            break;
        }
        if fs::symlink_metadata(folder).map_err(|e| e.to_string())?.file_type().is_symlink() {
            return Err("native module archive path traverses a link".into());
        }
        parent = folder.parent();
    }
    if regular(&path)?.len() != file.size || digest_file(&path)? != file.digest {
        return Err(format!("staged native archive {member} differs from its keyed bytes"));
    }
    Ok(path)
}

/// A plugin descriptor: a declared file input, or an Item holding exactly one `.uplugin` file.
fn descriptor(inputs: &BTreeMap<&str, Staged<'_>>, slot: &str) -> Result<Vec<u8>, String> {
    let staged = input(inputs, slot)?;
    let (path, digest, size) = match staged.payload {
        InputPayload::Bytes(bytes) => (
            staged.path.clone(),
            format!("{:x}", Sha256::digest(bytes)),
            bytes.len() as u64,
        ),
        InputPayload::Item { files, .. } => match files.as_slice() {
            [file] if file.path.ends_with(".uplugin") && relative_ok(&file.path) && !file.path.contains('/') => {
                if fs::symlink_metadata(&staged.path).map_err(|e| e.to_string())?.file_type().is_symlink() {
                    return Err(format!("plugin descriptor slot {slot} is linked"));
                }
                (staged.path.join(&file.path), file.digest.clone(), file.size)
            }
            _ => return Err(format!("plugin descriptor slot {slot} is not one .uplugin file")),
        },
        InputPayload::Absent => return Err(format!("plugin descriptor slot {slot} is absent")),
    };
    if size > MAX_DESCRIPTOR || regular(&path)?.len() != size {
        return Err(format!("plugin descriptor slot {slot} differs from its keyed size"));
    }
    let bytes = fs::read(&path).map_err(|e| e.to_string())?;
    if format!("{:x}", Sha256::digest(&bytes)) != digest {
        return Err(format!("plugin descriptor slot {slot} differs from its keyed bytes"));
    }
    Ok(bytes)
}

fn descriptor_modules(bytes: &[u8]) -> Result<BTreeSet<String>, String> {
    let value: serde_json::Value =
        serde_json::from_slice(bytes).map_err(|e| format!("invalid plugin descriptor: {e}"))?;
    let modules = value
        .get("Modules")
        .and_then(|v| v.as_array())
        .ok_or("plugin descriptor declares no Modules")?;
    modules
        .iter()
        .map(|module| {
            module
                .get("Name")
                .and_then(|v| v.as_str())
                .filter(|name| name_ok(name))
                .map(str::to_owned)
                .ok_or_else(|| "plugin descriptor module has no valid Name".to_string())
        })
        .collect()
}

/// `UnrealEditor.modules` of a materialized `Binaries/Mac`: this engine's BuildId and, per module,
/// a library the folder actually holds.
fn module_libraries(
    dir: &Path,
    files: &BTreeSet<String>,
    build_id: &str,
) -> Result<BTreeMap<String, String>, String> {
    if !files.contains(MODULES_FILE) {
        return Err(format!("produced binaries have no {MODULES_FILE}"));
    }
    let path = dir.join(MODULES_FILE);
    if regular(&path)?.len() > MAX_MANIFEST {
        return Err(format!("{MODULES_FILE} is too large"));
    }
    let value: serde_json::Value = serde_json::from_slice(&fs::read(&path).map_err(|e| e.to_string())?)
        .map_err(|e| format!("invalid {MODULES_FILE}: {e}"))?;
    if value.get("BuildId").and_then(|v| v.as_str()) != Some(build_id) {
        return Err(format!("produced {MODULES_FILE} was built for another engine BuildId"));
    }
    let modules = value
        .get("Modules")
        .and_then(|v| v.as_object())
        .filter(|modules| !modules.is_empty())
        .ok_or_else(|| format!("{MODULES_FILE} lists no modules"))?;
    let mut result = BTreeMap::new();
    for (name, library) in modules {
        let library = library.as_str().unwrap_or_default();
        if !name_ok(name) || !relative_ok(library) || library.contains('/') || !files.contains(library) {
            return Err(format!("produced module {name} has no binary in its folder"));
        }
        result.insert(name.clone(), library.to_owned());
    }
    Ok(result)
}

fn write_new(path: &Path, bytes: &[u8], mode: u32) -> Result<(), String> {
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(mode)
        .open(path)
        .map_err(|e| format!("{}: {e}", path.display()))?;
    file.write_all(bytes).map_err(|e| e.to_string())?;
    file.set_permissions(fs::Permissions::from_mode(mode)).map_err(|e| e.to_string())
}

fn tar_header(input: &mut impl Read) -> Result<([u8; 512], String, u64), String> {
    let mut header = [0; 512];
    input.read_exact(&mut header).map_err(|e| e.to_string())?;
    let text = |bytes: &[u8]| -> Result<String, String> {
        std::str::from_utf8(bytes)
            .map(|s| s.trim_end_matches('\0').to_owned())
            .map_err(|e| e.to_string())
    };
    let name = text(&header[..100])?;
    let prefix = text(&header[345..500])?;
    let name = if prefix.is_empty() { name } else { format!("{prefix}/{name}") };
    let octal = |bytes: &[u8]| -> Result<u64, String> {
        u64::from_str_radix(text(bytes)?.trim_matches(|c| c == '\0' || c == ' '), 8).map_err(|e| e.to_string())
    };
    let size = octal(&header[124..136])?;
    let claimed = octal(&header[148..156])?;
    let actual: u64 = header
        .iter()
        .enumerate()
        .map(|(i, b)| if (148..156).contains(&i) { 32 } else { *b as u64 })
        .sum();
    if claimed != actual {
        return Err("invalid native root tar checksum".into());
    }
    Ok((header, name, size))
}

fn tar_padding(input: &mut impl Read, size: u64) -> Result<(), String> {
    let mut padding = [0; 512];
    let count = ((512 - size % 512) % 512) as usize;
    input.read_exact(&mut padding[..count]).map_err(|e| e.to_string())?;
    if padding[..count].iter().any(|b| *b != 0) {
        return Err("invalid native root tar padding".into());
    }
    Ok(())
}

/// Decode one complete directory ROOT archive into the new folder `target`, verifying every member
/// against its manifest. Returns the relative paths of the regular files it wrote.
fn extract(archive: &Path, target: &Path) -> Result<BTreeSet<String>, String> {
    let mut input = std::io::BufReader::new(fs::File::open(archive).map_err(|e| e.to_string())?);
    let (header, name, size) = tar_header(&mut input)?;
    if name != "atelier-root.json" || !matches!(header[156], 0 | b'0') || size > MAX_MANIFEST {
        return Err("invalid fixed native root manifest".into());
    }
    let mut bytes = vec![0; size as usize];
    input.read_exact(&mut bytes).map_err(|e| e.to_string())?;
    tar_padding(&mut input, size)?;
    let manifest: RootManifest = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
    if manifest.version != 1 {
        return Err("unsupported root manifest".into());
    }
    if manifest.kind != "directory" {
        return Err(format!("native binaries must be a directory ROOT, not {:?}", manifest.kind));
    }
    let mut files = BTreeSet::new();
    let mut seen = BTreeSet::new();
    for (index, (relative, kind, size, mode, digest)) in manifest.entries.iter().enumerate() {
        if (index == 0) != relative.is_empty()
            || (index > 0 && !relative_ok(relative))
            || !seen.insert(relative.clone())
            || !matches!(*mode, 0o644 | 0o755)
            || (index == 0 && kind != "directory")
        {
            return Err("invalid native root member".into());
        }
        let (header, name, actual_size) = tar_header(&mut input)?;
        let expected = if relative.is_empty() { "root".to_owned() } else { format!("root/{relative}") };
        if name.trim_end_matches('/') != expected || actual_size != *size || header[157..257].iter().any(|b| *b != 0) {
            return Err("root member differs from manifest".into());
        }
        let destination = if relative.is_empty() { target.to_path_buf() } else { target.join(relative) };
        if kind == "directory" {
            if header[156] != b'5' || *size != 0 || digest.is_some() {
                return Err("invalid root directory".into());
            }
            // create_dir refuses an existing path and a missing parent: no overwrite, parents first.
            fs::create_dir(&destination).map_err(|e| format!("{}: {e}", destination.display()))?;
            fs::set_permissions(&destination, fs::Permissions::from_mode(*mode)).map_err(|e| e.to_string())?;
        } else if kind == "file" {
            if !matches!(header[156], 0 | b'0') {
                return Err("invalid root file".into());
            }
            let mut file = fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .mode(0o600)
                .open(&destination)
                .map_err(|e| format!("{}: {e}", destination.display()))?;
            let mut hasher = Sha256::new();
            let mut left = *size;
            let mut buffer = [0; 64 * 1024];
            while left > 0 {
                let take = left.min(buffer.len() as u64) as usize;
                input.read_exact(&mut buffer[..take]).map_err(|e| e.to_string())?;
                hasher.update(&buffer[..take]);
                file.write_all(&buffer[..take]).map_err(|e| e.to_string())?;
                left -= take as u64;
            }
            if digest.as_deref() != Some(format!("{:x}", hasher.finalize()).as_str()) {
                return Err("native root payload differs from keyed manifest".into());
            }
            file.set_permissions(fs::Permissions::from_mode(*mode)).map_err(|e| e.to_string())?;
            tar_padding(&mut input, *size)?;
            files.insert(relative.clone());
        } else {
            return Err("invalid root kind".into());
        }
    }
    let mut tail = [0; 8192];
    loop {
        let count = input.read(&mut tail).map_err(|e| e.to_string())?;
        if count == 0 {
            break;
        }
        if tail[..count].iter().any(|b| *b != 0) {
            return Err("unlisted native root member".into());
        }
    }
    Ok(files)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::schema::StoredFile;

    struct Space(PathBuf);
    impl Space {
        fn new(label: &str) -> Self {
            let path = std::env::temp_dir().join(format!(
                "atelier-native-modules-{label}-{}-{}",
                std::process::id(),
                std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()
            ));
            fs::create_dir_all(&path).unwrap();
            Space(path.canonicalize().unwrap())
        }
    }
    impl Drop for Space {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    fn header(name: &str, size: u64, kind: u8, mode: u32) -> [u8; 512] {
        let mut header = [0u8; 512];
        header[..name.len()].copy_from_slice(name.as_bytes());
        header[100..108].copy_from_slice(format!("{mode:07o}\0").as_bytes());
        header[108..116].copy_from_slice(b"0000000\0");
        header[116..124].copy_from_slice(b"0000000\0");
        header[124..136].copy_from_slice(format!("{size:011o}\0").as_bytes());
        header[136..148].copy_from_slice(b"00000000000\0");
        header[156] = kind;
        header[257..263].copy_from_slice(b"ustar\0");
        header[263..265].copy_from_slice(b"00");
        header[148..156].copy_from_slice(b"        ");
        let sum: u64 = header.iter().map(|b| *b as u64).sum();
        header[148..156].copy_from_slice(format!("{sum:06o}\0 ").as_bytes());
        header
    }

    fn pad(out: &mut Vec<u8>) {
        while out.len() % 512 != 0 {
            out.push(0);
        }
    }

    /// A directory ROOT archive: `None` contents are folders.
    fn root_tar(members: &[(&str, Option<&[u8]>)]) -> Vec<u8> {
        let mut entries = vec![serde_json::json!(["", "directory", 0, 0o755, null])];
        for (path, bytes) in members {
            entries.push(match bytes {
                None => serde_json::json!([path, "directory", 0, 0o755, null]),
                Some(bytes) => serde_json::json!([path, "file", bytes.len(), if path.ends_with(".dylib") { 0o755 } else { 0o644 },
                                                   format!("{:x}", Sha256::digest(bytes))]),
            });
        }
        let manifest = serde_json::to_vec(&serde_json::json!({"version": 1, "kind": "directory", "entries": entries})).unwrap();
        let mut out = vec![];
        out.extend(header("atelier-root.json", manifest.len() as u64, b'0', 0o644));
        out.extend(&manifest);
        pad(&mut out);
        out.extend(header("root/", 0, b'5', 0o755));
        for (path, bytes) in members {
            match bytes {
                None => out.extend(header(&format!("root/{path}/"), 0, b'5', 0o755)),
                Some(bytes) => {
                    out.extend(header(&format!("root/{path}"), bytes.len() as u64, b'0', 0o644));
                    out.extend(*bytes);
                    pad(&mut out);
                }
            }
        }
        out.extend([0u8; 1024]);
        out
    }

    fn item(space: &Space, name: &str, files: &[(&str, Vec<u8>)]) -> (PathBuf, InputPayload) {
        let root = space.0.join("job/inputs").join(name);
        fs::create_dir_all(&root).unwrap();
        let mut stored = vec![];
        for (path, bytes) in files {
            fs::write(root.join(path), bytes).unwrap();
            stored.push(StoredFile {
                path: (*path).into(),
                digest: format!("{:x}", Sha256::digest(bytes)),
                size: bytes.len() as u64,
                mode: 0o644,
            });
        }
        (root, InputPayload::Item { logical_path: name.into(), class: "Data".into(), files: stored })
    }

    const ARCHIVE: &str = "products/0-0.tree.tar";

    struct Case {
        space: Space,
        payloads: BTreeMap<String, (PathBuf, InputPayload)>,
        request: serde_json::Value,
    }

    impl Case {
        fn new(label: &str) -> Self {
            Self::with(label, "b1", br#"{"Modules": [{"Name": "GameTools", "Type": "Editor"}]}"#.to_vec(), vec![])
        }
        fn with(label: &str, build: &str, descriptor: Vec<u8>, extra: Vec<(&str, Option<&[u8]>)>) -> Self {
            let space = Space::new(label);
            fs::create_dir_all(space.0.join("job/inputs/editor/products")).unwrap();
            fs::create_dir_all(space.0.join("job/inputs/plugin/products")).unwrap();
            let modules = format!(r#"{{"BuildId": "{build}", "Modules": {{"Yorigame": "libUnrealEditor-Yorigame.dylib"}}}}"#);
            let mut members: Vec<(&str, Option<&[u8]>)> = vec![
                (MODULES_FILE, Some(modules.as_bytes())),
                ("libUnrealEditor-Yorigame.dylib", Some(&b"editor module"[..])),
            ];
            members.extend(extra);
            let editor = item(&space, "editor", &[(ARCHIVE, root_tar(&members))]);
            let plugin_modules = format!(r#"{{"BuildId": "{build}", "Modules": {{"GameTools": "libUnrealEditor-GameTools.dylib"}}}}"#);
            let plugin = item(&space, "plugin", &[(ARCHIVE, root_tar(&[
                (MODULES_FILE, Some(plugin_modules.as_bytes())),
                ("libUnrealEditor-GameTools.dylib", Some(&b"plugin module"[..])),
            ]))]);
            let path = space.0.join("job/inputs/descriptor");
            fs::write(&path, &descriptor).unwrap();
            let payloads = BTreeMap::from([
                ("editor".to_owned(), editor),
                ("plugin".to_owned(), plugin),
                ("descriptor".to_owned(), (path, InputPayload::Bytes(descriptor))),
            ]);
            let request = serde_json::json!({
                "editor": {"slot": "editor", "archive": ARCHIVE,
                           "modules": [{"name": "Yorigame", "kind": "Runtime", "loading_phase": "Default"}]},
                "plugins": [{"name": "GameTools", "slot": "plugin", "archive": ARCHIVE, "descriptor_slot": "descriptor"}],
            });
            Case { space, payloads, request }
        }
        fn run(&self) -> Result<PreparedNativeModules, String> {
            let inputs: BTreeMap<&str, Staged<'_>> = self
                .payloads
                .iter()
                .map(|(name, (path, payload))| (name.as_str(), Staged { path: path.clone(), payload }))
                .collect();
            let request: Request = serde_json::from_value(self.request.clone()).map_err(|e| e.to_string())?;
            materialize(&request, &inputs, &self.space.0.join("scope"), "b1")
        }
        fn scope(&self) -> PathBuf {
            self.space.0.join("scope")
        }
    }

    #[test]
    fn materializes_independent_editor_and_plugin_context() {
        let case = Case::new("ok");
        let prepared = case.run().unwrap();
        let scope = case.scope();
        assert_eq!(prepared.editor.dir, scope.join("editor"));
        assert_eq!(prepared.editor.identity, unreal::tree_identity(&scope.join("editor"), None).unwrap());
        assert_eq!(prepared.modules[0].name, "Yorigame");
        assert_eq!(fs::read(scope.join("editor/libUnrealEditor-Yorigame.dylib")).unwrap(), b"editor module");
        let mode = fs::metadata(scope.join("editor/libUnrealEditor-Yorigame.dylib")).unwrap().permissions().mode();
        assert_eq!(mode & 0o777, 0o755);
        let plugin = &prepared.plugins[0];
        assert_eq!(plugin.dir, scope.join("plugins/GameTools"));
        assert!(plugin.dir.join("GameTools.uplugin").is_file());
        assert!(plugin.dir.join("Binaries/Mac/libUnrealEditor-GameTools.dylib").is_file());
        assert_eq!(plugin.identity, unreal::tree_identity(&plugin.dir, Some("GameTools")).unwrap());
        // The copies are independent of the staged inputs.
        assert!(!fs::symlink_metadata(scope.join("editor/UnrealEditor.modules")).unwrap().file_type().is_symlink());
    }

    #[test]
    fn an_existing_scope_refuses_and_is_kept() {
        let case = Case::new("scope");
        fs::create_dir(case.scope()).unwrap();
        let error = case.run().unwrap_err();
        assert!(error.contains("must be new"), "{error}");
        assert!(case.scope().is_dir(), "an existing scope is never removed");
    }

    #[test]
    fn wrong_build_modules_or_slots_refuse_and_clean_the_scope() {
        let mut cases = vec![];
        cases.push(("build", Case::with("build", "b2", br#"{"Modules": [{"Name": "GameTools"}]}"#.to_vec(), vec![])));
        let mut case = Case::new("modules");
        case.request["editor"]["modules"][0]["name"] = "Other".into();
        cases.push(("modules", case));
        let mut case = Case::new("extra");
        case.request["editor"]["modules"].as_array_mut().unwrap().push(
            serde_json::json!({"name": "Second", "kind": "Editor", "loading_phase": "Default"}));
        cases.push(("extra", case));
        let mut case = Case::new("slot");
        case.request["editor"]["slot"] = "missing".into();
        cases.push(("slot", case));
        let mut case = Case::new("member");
        case.request["editor"]["archive"] = "products/1-0.tree.tar".into();
        cases.push(("member", case));
        let mut case = Case::new("traverse");
        case.request["editor"]["archive"] = "../editor/products/0-0.tree.tar".into();
        cases.push(("traverse", case));
        let mut case = Case::new("descslot");
        case.request["plugins"][0]["descriptor_slot"] = "editor".into();
        cases.push(("descslot", case));
        cases.push(("undeclared", Case::with("undeclared", "b1", br#"{"Modules": [{"Name": "Other"}]}"#.to_vec(), vec![])));
        let mut case = Case::new("unknown");
        case.request["editor"]["global"] = "/Users".into();
        cases.push(("unknown", case));
        let mut case = Case::new("repeat");
        let plugin = case.request["plugins"][0].clone();
        case.request["plugins"].as_array_mut().unwrap().push(plugin);
        cases.push(("repeat", case));
        for (label, case) in cases {
            assert!(case.run().is_err(), "{label} must refuse");
            assert!(!case.scope().exists(), "{label} must remove its partial scope");
        }
    }

    #[test]
    fn staged_bytes_must_equal_keyed_digests() {
        let case = Case::new("tamper");
        let archive = case.space.0.join("job/inputs/editor").join(ARCHIVE);
        let mut bytes = fs::read(&archive).unwrap();
        let last = bytes.iter().rposition(|b| *b == b'e').unwrap();
        bytes[last] = b'E';
        fs::write(&archive, bytes).unwrap();
        assert!(case.run().unwrap_err().contains("differs from its keyed bytes"));
        let case = Case::new("descriptor");
        fs::write(case.space.0.join("job/inputs/descriptor"), b"{\"Modules\": []}").unwrap();
        assert!(case.run().is_err());
    }

    #[test]
    fn archive_members_cannot_escape_overwrite_or_go_unlisted() {
        // A member path that leaves its root refuses before any write outside the scope.
        let space = Space::new("escape");
        let target = space.0.join("out");
        let evil = root_tar(&[("../escaped", Some(&b"x"[..]))]);
        fs::write(space.0.join("evil.tar"), &evil).unwrap();
        assert!(extract(&space.0.join("evil.tar"), &target).is_err());
        assert!(!space.0.join("escaped").exists());
        // Parents must precede children; a file under an unlisted folder refuses.
        let orphan = root_tar(&[("missing/child", Some(&b"x"[..]))]);
        fs::write(space.0.join("orphan.tar"), &orphan).unwrap();
        assert!(extract(&space.0.join("orphan.tar"), &space.0.join("out2")).is_err());
        // Bytes after the listed members refuse.
        let mut extra = root_tar(&[("a", Some(&b"x"[..]))]);
        let end = extra.len() - 1024;
        extra.truncate(end);
        extra.extend(header("root/b", 1, b'0', 0o644));
        extra.push(b'y');
        pad(&mut extra);
        extra.extend([0u8; 1024]);
        fs::write(space.0.join("extra.tar"), &extra).unwrap();
        assert!(extract(&space.0.join("extra.tar"), &space.0.join("out3")).unwrap_err().contains("unlisted"));
        // An existing target is never overwritten.
        let good = root_tar(&[("a", Some(&b"x"[..]))]);
        fs::write(space.0.join("good.tar"), &good).unwrap();
        fs::create_dir(space.0.join("out4")).unwrap();
        assert!(extract(&space.0.join("good.tar"), &space.0.join("out4")).is_err());
        assert_eq!(extract(&space.0.join("good.tar"), &space.0.join("out5")).unwrap(), BTreeSet::from(["a".to_owned()]));
    }

    #[test]
    fn nested_folders_materialize_in_order() {
        let case = Case::with("nested", "b1", br#"{"Modules": [{"Name": "GameTools"}]}"#.to_vec(),
                              vec![("Shaders", None), ("Shaders/extra.bin", Some(&b"data"[..]))]);
        let prepared = case.run().unwrap();
        assert_eq!(fs::read(prepared.editor.dir.join("Shaders/extra.bin")).unwrap(), b"data");
    }
}
