//! Production C3 preparation. C5 retains admission, owned children and cleanup.
use crate::guard_adapter::WorkerCommand;
use crate::keys::{ImplementationIdentity, InputPayload, PreparedUnit};
use crate::source_hashes::sha256;
use crate::staging::StagedJob;
use crate::unreal::{self, ImportEvidence, ScratchProject, UnrealContext, UnrealWorkerBundle};
use crate::validate::{
    InputRole, InputRule, OpDefinition, OpRegistry, ParamKind, ParamRule, SnapshotEntry,
    SourceSnapshot,
};
use std::cell::Cell;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::Read;
use std::os::unix::fs::PermissionsExt;
use std::path::Path;
use std::path::PathBuf;

pub const RAW_IMPORT: &str = "unreal.raw_import";
pub const FINISH: &str = "unreal.finish";
pub const AUTHOR: &str = "unreal.author";
pub const VERIFY: &str = crate::results::zen_cook::VERIFY_OP;
pub const OP_VERSION: &str = "1";
pub const ENTRY: &str = "platform/studio/atelier/build_v2/unreal_ops.py";

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct UnrealLocations {
    pub engine_root: PathBuf,
    pub build_id: String,
    /// Late-bound produced native folder; omitted for engine-only asset operations.
    pub editor_binaries: Option<PathBuf>,
    #[serde(default)]
    pub modules: Vec<unreal::Module>,
    #[serde(default)]
    pub engine_plugins: BTreeMap<String, PathBuf>,
    pub plugins: BTreeMap<String, PathBuf>,
    #[serde(default)]
    pub config_sources: BTreeMap<String, String>,
}

impl UnrealLocations {
    pub fn build(
        &self,
        unit: &PreparedUnit,
        staged: &StagedJob,
        sources: &SourceSnapshot,
        cache_root: &Path,
    ) -> Result<UnrealExecutionContext, String> {
        let worker = frozen_worker(sources)?;
        if worker_identity(&worker).digest != unit.ingredients().worker_digest {
            return Err("native context worker differs from A3".into());
        }
        let editor_dir = if let Some(path) = &self.editor_binaries {
            path.clone()
        } else {
            if !self.modules.is_empty() {
                return Err("project modules need produced native binaries".into());
            }
            let path = staged
                .job_dir()
                .parent()
                .ok_or("missing job scope")?
                .join(format!("native-empty-{}", unit.key()));
            match fs::create_dir(&path) {
                Ok(()) => {}
                Err(error)
                    if error.kind() == std::io::ErrorKind::AlreadyExists
                        && fs::symlink_metadata(&path)
                            .map_err(|e| e.to_string())?
                            .is_dir()
                        && fs::read_dir(&path)
                            .map_err(|e| e.to_string())?
                            .next()
                            .is_none() => {}
                Err(error) => return Err(error.to_string()),
            }
            path
        };
        let plugins = |values: &BTreeMap<String, PathBuf>| {
            values
                .iter()
                .map(|(name, dir)| {
                    Ok(unreal::Plugin {
                        name: name.clone(),
                        dir: dir.clone(),
                        identity: unreal::tree_identity(dir, Some(name))
                            .map_err(|e| e.to_string())?,
                    })
                })
                .collect::<Result<Vec<_>, String>>()
        };
        let store = crate::store::ObjectStore::open(cache_root).map_err(|e| e.to_string())?;
        let settings = unit
            .ingredients()
            .params
            .get("settings")
            .map(|value| serde_json::from_value(value.clone()))
            .transpose()
            .map_err(|e| e.to_string())?
            .unwrap_or_default();
        let produced = crate::native_modules::prepare(unit, staged,
            &staged.job_dir().parent().ok_or("missing native module scope")?.join("native-modules"),
            &self.build_id)?;
        let mut project_plugins = plugins(&self.plugins)?;
        let (editor, modules) = if let Some(produced) = produced {
            if self.editor_binaries.is_some() || !self.modules.is_empty() {
                return Err("native modules have two distinct binary authorities".into());
            }
            for plugin in produced.plugins {
                if project_plugins.iter().any(|existing| existing.name == plugin.name) {
                    return Err("native plugin has two distinct binary authorities".into());
                }
                project_plugins.push(plugin);
            }
            (produced.editor, produced.modules)
        } else {
            (unreal::Binaries {identity: unreal::tree_identity(&editor_dir, None)
                .map_err(|e| e.to_string())?, dir: editor_dir}, self.modules.clone())
        };
        Ok(UnrealExecutionContext {
            context: UnrealContext {
                engine_root: self.engine_root.clone(),
                build_id: self.build_id.clone(),
                editor,
                modules,
                engine_plugins: plugins(&self.engine_plugins)?,
                plugins: project_plugins,
                settings,
                ddc: unreal::UnrealDdc::open(&store, &self.build_id).map_err(|e| e.to_string())?,
                worker,
            },
            config_sources: self.config_sources.clone(),
            platform_plugins: BTreeSet::from([unreal::WORKER_PLUGIN.into()]),
        })
    }
}

fn frozen_worker(sources: &SourceSnapshot) -> Result<UnrealWorkerBundle, String> {
    let files = unreal::UNREAL_WORKER_FILES
        .iter()
        .map(|name| {
            let path = format!("platform/studio/atelier/build_v2/{name}");
            let Some(SnapshotEntry::File(bytes)) = sources.get(&path) else {
                return Err(format!("missing frozen native worker {path}"));
            };
            Ok((name.to_string(), bytes.clone()))
        })
        .collect::<Result<BTreeMap<_, _>, String>>()?;
    UnrealWorkerBundle::from_files(files).map_err(|e| e.to_string())
}

/// Physical execution locations never become automatic item-key ingredients.
pub struct UnrealExecutionContext {
    pub context: UnrealContext,
    /// Scratch-relative Config filename -> project-relative frozen source filename.
    pub config_sources: BTreeMap<String, String>,
    /// Platform plugins are fixed installed implementation, not project content.
    pub platform_plugins: BTreeSet<String>,
}

pub struct PreparedUnrealLaunch {
    pub command: WorkerCommand,
    pub worker: ImplementationIdentity,
    pub profile: String,
    /// Retained through terminal reply, positive owned cleanup and output freeze.
    pub keepalive: ScratchProject,
    /// Keyed settings configure the native context; op bodies receive their own fields.
    pub request: crate::protocol::JobRequest,
    packages: BTreeSet<String>,
    context_verified: Cell<bool>,
    native_source_digest: String,
}

impl PreparedUnrealLaunch {
    /// Restrict the already-started editor before Hello; only fixed native jobs share it.
    pub fn enable_resident(&mut self) -> Result<(), String> {
        if !matches!(self.request.op.kind.as_str(), RAW_IMPORT | FINISH | AUTHOR | VERIFY) {
            return Err("only registered import/finish/author/verify operations may share an editor".into());
        }
        if self.request.op.kind == VERIFY {
            use std::os::unix::fs::OpenOptionsExt;
            use std::io::Write;
            if !self.profile.ends_with("-native-store") {
                return Err("resident verifier lacks its private native-store preparation".into());
            }
            let path = self.keepalive.root().join("Atelier/native-store-startup.json");
            let mut file = fs::OpenOptions::new().write(true).create_new(true).mode(0o400)
                .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC).open(path).map_err(|e| e.to_string())?;
            file.write_all(&serde_json::to_vec(&serde_json::json!({"version":1,
                "job_dir":self.request.job_dir,"native_source_digest":self.native_source_digest}))
                .map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
            file.sync_all().map_err(|e| e.to_string())?;
        }
        self.command.args.push("--resident-no-fork".into());
        Ok(())
    }

    /// A fresh job may borrow only the exact native context already checked in this session.
    pub fn bind_resident_context(&self, owner: &Self) -> Result<(), String> {
        if !owner.context_verified.get()
            || self.profile != owner.profile
            || self.worker.version != owner.worker.version
            || self.worker.digest != owner.worker.digest
            || self.native_source_digest != owner.native_source_digest
            || self.keepalive.expected() != owner.keepalive.expected()
            || !matches!(self.request.op.kind.as_str(), RAW_IMPORT | FINISH | VERIFY)
        {
            return Err("resident job differs from verified native session".into());
        }
        self.keepalive.verify().map_err(|e| e.to_string())?;
        self.context_verified.set(true);
        Ok(())
    }

    pub fn verify_reset(&self, job_dir: &Path) -> Result<(), String> {
        use std::io::Read;
        use std::os::unix::fs::OpenOptionsExt;
        let path = job_dir.join(".unreal-runtime/reset.json");
        let mut file = fs::OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&path)
            .map_err(|e| e.to_string())?;
        let info = file.metadata().map_err(|e| e.to_string())?;
        if !info.is_file() || info.len() > 1024 {
            return Err("invalid native reset receipt".into());
        }
        let mut bytes = Vec::new();
        file.by_ref()
            .take(1025)
            .read_to_end(&mut bytes)
            .map_err(|e| e.to_string())?;
        let value: serde_json::Value = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
        if value != serde_json::json!({"version":1,"job_id":self.request.job_id}) {
            return Err("native worker did not positively reset this job".into());
        }
        Ok(())
    }

    /// C5 must call after Hello, BEFORE the first Run; missing evidence refuses.
    pub fn verify_context(&self) -> Result<(), String> {
        let report = self
            .keepalive
            .verify_context_report()
            .map_err(|e| e.to_string())?;
        if report.native_worker_source_digest.as_deref() != Some(&self.native_source_digest) {
            return Err("loaded native worker differs from keyed project implementation".into());
        }
        self.context_verified.set(true);
        Ok(())
    }

    /// Call after Completed and positive guard cleanup, BEFORE CAS publication.
    pub fn verify_completed(&self, staged: &StagedJob) -> Result<ImportEvidence, String> {
        if !self.context_verified.get() {
            return Err("native startup context was not verified before Run".into());
        }
        self.keepalive.verify().map_err(|e| e.to_string())?;
        let evidence = unreal::read_import_evidence(staged.job_dir(), &self.packages)
            .map_err(|e| e.to_string())?;
        let mut permitted = self.packages.clone();
        for input in &self.request.inputs {
            let root = staged.job_dir().join(&input.path);
            if root.is_dir() {
                native_input_packages(&root, &root, &mut permitted)?;
            }
        }
        for output in &evidence.packages {
            for (path, _) in &output.imports {
                let name = path.split('.').next().unwrap_or(path);
                if name.starts_with("/Game/") && !permitted.contains(name) {
                    return Err(format!("native output imports undeclared package {name}"));
                }
            }
        }
        Ok(evidence)
    }
}

fn native_input_packages(
    root: &Path,
    directory: &Path,
    into: &mut BTreeSet<String>,
) -> Result<(), String> {
    for entry in fs::read_dir(directory).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();
        let kind = entry.file_type().map_err(|e| e.to_string())?;
        if kind.is_symlink() {
            return Err("linked native input".into());
        }
        if kind.is_dir() {
            native_input_packages(root, &path, into)?;
        } else if kind.is_file() {
            let relative = path
                .strip_prefix(root)
                .map_err(|e| e.to_string())?
                .to_str()
                .ok_or("nonutf8 input")?;
            if let Some(relative) = relative.strip_prefix("content/Game/") {
                if relative.ends_with(".uasset") || relative.ends_with(".umap") {
                    into.insert(format!(
                        "/Game/{}",
                        relative.rsplit_once('.').ok_or("invalid package file")?.0
                    ));
                }
            }
        } else {
            return Err("special native input".into());
        }
    }
    Ok(())
}

#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct RootManifest {
    version: u32,
    kind: String,
    entries: Vec<(String, String, u64, u32, Option<String>)>,
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
    let name = if prefix.is_empty() {
        name
    } else {
        format!("{prefix}/{name}")
    };
    let size = u64::from_str_radix(
        text(&header[124..136])?.trim_matches(|c| c == '\0' || c == ' '),
        8,
    )
    .map_err(|e| e.to_string())?;
    let claimed = u64::from_str_radix(
        text(&header[148..156])?.trim_matches(|c| c == '\0' || c == ' '),
        8,
    )
    .map_err(|e| e.to_string())?;
    let actual: u64 = header
        .iter()
        .enumerate()
        .map(|(i, b)| {
            if (148..156).contains(&i) {
                32
            } else {
                *b as u64
            }
        })
        .sum();
    if claimed != actual {
        return Err("invalid native root tar checksum".into());
    }
    Ok((header, name, size))
}

fn tar_padding(input: &mut impl Read, size: u64) -> Result<(), String> {
    let mut padding = [0; 512];
    let count = ((512 - size % 512) % 512) as usize;
    input
        .read_exact(&mut padding[..count])
        .map_err(|e| e.to_string())?;
    if padding[..count].iter().any(|b| *b != 0) {
        return Err("invalid tar padding".into());
    }
    Ok(())
}

fn archive_digests(path: &Path) -> Result<BTreeSet<String>, String> {
    use sha2::{Digest, Sha256};
    let mut input = fs::File::open(path).map_err(|e| e.to_string())?;
    let (header, name, size) = tar_header(&mut input)?;
    if name != "atelier-root.json" || !matches!(header[156], 0 | b'0') || size > 16 * 1024 * 1024 {
        return Err("invalid fixed native root manifest".into());
    }
    let mut bytes = vec![0; size as usize];
    input.read_exact(&mut bytes).map_err(|e| e.to_string())?;
    tar_padding(&mut input, size)?;
    let manifest: RootManifest = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
    if manifest.version != 1 || !matches!(manifest.kind.as_str(), "file" | "directory" | "absent") {
        return Err("unsupported root manifest".into());
    }
    let mut result = BTreeSet::new();
    let mut seen = BTreeSet::new();
    for (index, (relative, kind, size, mode, digest)) in manifest.entries.iter().enumerate() {
        if (index == 0 && !relative.is_empty())
            || (index > 0 && relative.is_empty())
            || relative.split('/').any(|p| p == ".." || p == ".")
            || relative.starts_with('/')
            || relative.contains('\\')
            || !seen.insert(relative.clone())
            || !matches!(*mode, 0o644 | 0o755)
        {
            return Err("invalid native root member".into());
        }
        let (header, name, actual_size) = tar_header(&mut input)?;
        let expected = if relative.is_empty() {
            "root".into()
        } else {
            format!("root/{relative}")
        };
        if name.trim_end_matches('/') != expected
            || actual_size != *size
            || header[157..257].iter().any(|b| *b != 0)
        {
            return Err("root member differs from manifest".into());
        }
        if kind == "directory" {
            if header[156] != b'5' || *size != 0 || digest.is_some() {
                return Err("invalid root directory".into());
            }
        } else if kind == "file" {
            if !matches!(header[156], 0 | b'0') {
                return Err("invalid root file".into());
            }
            let mut hasher = Sha256::new();
            let mut left = *size;
            let mut buffer = [0; 64 * 1024];
            while left > 0 {
                let take = left.min(buffer.len() as u64) as usize;
                input
                    .read_exact(&mut buffer[..take])
                    .map_err(|e| e.to_string())?;
                hasher.update(&buffer[..take]);
                left -= take as u64;
            }
            let actual = format!("{:x}", hasher.finalize());
            if digest.as_deref() != Some(actual.as_str()) {
                return Err("native root payload differs from keyed manifest".into());
            }
            result.insert(actual);
            tar_padding(&mut input, *size)?;
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
    Ok(result)
}

pub fn validator_identity() -> ImplementationIdentity {
    ImplementationIdentity {
        version: "atelier-unreal-controller-1".into(),
        digest: sha256(include_bytes!("unreal_controller.rs")),
    }
}

pub fn worker_identity(bundle: &UnrealWorkerBundle) -> ImplementationIdentity {
    ImplementationIdentity {
        version: unreal::UNREAL_JOB_LOOP_VERSION.into(),
        digest: bundle.digest().into(),
    }
}

fn keyed_digests(unit: &PreparedUnit, staged: &StagedJob) -> Result<BTreeSet<String>, String> {
    let mut result: BTreeSet<_> = unit.ingredients().code.values().cloned().collect();
    for input in unit.inputs() {
        match &input.payload {
            InputPayload::Bytes(value) => {
                result.insert(sha256(value));
            }
            InputPayload::Item { files, .. } => {
                for file in files {
                    result.insert(file.digest.clone());
                    if !file.path.ends_with(".tree.tar") {
                        continue;
                    }
                    let path = staged.job_dir().join(&input.wire.path).join(&file.path);
                    result.extend(archive_digests(&path)?);
                }
            }
            InputPayload::NativeCooked(_) => {
                return Err("native cooked inputs require the fixed packaging adapter".into());
            }
            InputPayload::Absent => {}
        }
    }
    Ok(result)
}

fn package(path: &str) -> Result<String, String> {
    let parts: Vec<_> = path.split('/').collect();
    if parts.len() < 3
        || parts[0] != ""
        || parts[1] != "Game"
        || parts[2..].iter().any(|part| {
            part.is_empty()
                || !part
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || b"_-".contains(&c))
        })
    {
        return Err(format!("invalid native package {path}"));
    }
    Ok(path.into())
}

fn finish_data_output(item: &crate::schema::Item) -> Result<(), String> {
    if item.class != "Data" || item.files.is_empty() || matches!(item.destination, crate::schema::Destination::External) {
        return Err("finish data needs explicit ordinary file outputs".into());
    }
    for file in &item.files {
        crate::paths::relative_path(&file.path, false)?;
        if !file.path.starts_with("data/") { return Err("finish data must stay in data/".into()); }
    }
    Ok(())
}

fn declared_packages(unit: &PreparedUnit) -> Result<BTreeSet<String>, String> {
    let mut result = BTreeSet::new();
    for item in &unit.ingredients().logical_outputs {
        if item.class == "JsonData" || (unit.ingredients().op.kind == FINISH && item.class == "Data") { continue; }
        package(&item.logical_path)?;
        for file in &item.files {
            let Some(relative) = file.path.strip_prefix("content/Game/") else {
                return Err("native file outside C3 content namespace".into());
            };
            if relative.ends_with(".uasset") || relative.ends_with(".umap") {
                result.insert(package(&format!(
                    "/Game/{}",
                    relative
                        .rsplit_once('.')
                        .ok_or("native file has no suffix")?
                        .0
                ))?);
            }
        }
    }
    Ok(result)
}

pub const NATIVE_SOURCE_ROOT: &str = "platform/build-v2/unreal/AtelierBuildWorker/";

/// Match the exact raw-source manifest compiled by AtelierBuildWorker.Build.cs.
fn native_source_digest(unit: &PreparedUnit) -> Result<String, String> {
    let mut files = BTreeMap::new();
    for (path, digest) in &unit.ingredients().code {
        if let Some(relative) = path.strip_prefix(NATIVE_SOURCE_ROOT) {
            if relative == "AtelierBuildWorker.uplugin"
                || (relative.starts_with("Source/")
                    && (relative.ends_with(".cs")
                        || relative.ends_with(".cpp")
                        || relative.ends_with(".h")))
            {
                files.insert(relative, digest);
            }
        }
    }
    for required in [
        "AtelierBuildWorker.uplugin",
        "Source/AtelierBuildWorker/AtelierBuildWorker.Build.cs",
        "Source/AtelierBuildWorker/Private/AtelierBuildWorkerLibrary.cpp",
        "Source/AtelierBuildWorker/Private/AtelierBuildWorkerModule.cpp",
        "Source/AtelierBuildWorker/Public/AtelierBuildWorkerLibrary.h",
    ] {
        if !files.contains_key(required) {
            return Err(format!(
                "native implementation source not keyed: {required}"
            ));
        }
    }
    let manifest = files
        .into_iter()
        .map(|(path, digest)| format!("{path}\0{digest}\n"))
        .collect::<String>();
    Ok(sha256(manifest.as_bytes()))
}

pub fn check_unit(unit: &PreparedUnit) -> Result<(), String> {
    let value = unit.ingredients();
    native_source_digest(unit)?;
    if value.op.kind == VERIFY {
        let expected = crate::results::zen_cook::validator_identity();
        if value.op.version != OP_VERSION
            || value.validator_version != expected.version
            || value.validator_digest != expected.digest
            || value.script != crate::results::zen_cook::VERIFY_SCRIPT
            || value.code != crate::results::zen_cook::verifier_code_digests()
            || !value.output_groups.is_empty()
            || value.logical_outputs.len() != 1
            || value.logical_outputs[0].class != "JsonData"
            || value.logical_outputs[0].files.len() != 1
            || value.logical_outputs[0].files[0].path != crate::results::zen_cook::VERIFY_REPORT
            || !value.logical_outputs[0].files[0].required
            || !matches!(
                value.logical_outputs[0].destination,
                crate::schema::Destination::Store
            )
        {
            return Err(
                "native verifier differs from its fixed implementation/report contract".into(),
            );
        }
        return Ok(());
    }
    let expected = validator_identity();
    if value.validator_version != expected.version || value.validator_digest != expected.digest {
        return Err("native validator identity differs from registered implementation".into());
    }
    if value.op.kind == AUTHOR && value.op.version == OP_VERSION {
        if !value.code.contains_key(&value.script)
            || !value.output_groups.is_empty()
            || value.logical_outputs.len() != 1
            || !value.params.contains_key("args")
        {
            return Err("authored native asset needs one keyed body and exact output item".into());
        }
        let item = &value.logical_outputs[0];
        if item.class == "JsonData" {
            if item.files.len() != 1 || !item.files[0].required
                || !item.files[0].path.starts_with("data/") || !item.files[0].path.ends_with(".json") {
                return Err("native data author needs one required explicit data JSON file".into());
            }
            return Ok(());
        }
        if !matches!(
            item.class.as_str(),
            "Material" | "MaterialInstance" | "MaterialParameterCollection" | "Map" | "Blueprint"
                | "BlendSpace1D" | "AdventureMoveSet" | "Animation" | "AnimBoneCompressionSettings" | "AnimCurveCompressionSettings" | "MirrorDataTable" | "WandererDefinition" | "SoundAttenuation" | "DataAsset"
        ) {
            return Err("unsupported authored native asset class".into());
        }
        package(&item.logical_path)?;
        let primary = format!(
            "content/Game/{}.{}",
            item.logical_path
                .strip_prefix("/Game/")
                .ok_or("nonGame asset")?,
            if item.class == "Map" {
                "umap"
            } else {
                "uasset"
            }
        );
        if !item
            .files
            .iter()
            .any(|file| file.required && file.path == primary)
        {
            return Err("authored native asset omits required primary".into());
        }
        return Ok(());
    }
    let action = match (value.op.kind.as_str(), value.op.version.as_str()) {
        (RAW_IMPORT, OP_VERSION) => "raw_import",
        (FINISH, OP_VERSION) => "finish",
        _ => return Err("unsupported native operation/version".into()),
    };
    if (value.op.kind == RAW_IMPORT && value.script != ENTRY)
        || !value.code.contains_key(&value.script) || !value.output_groups.is_empty() {
        return Err("native unit has an unsupported body/group contract".into());
    }
    if value.params.get("op").and_then(|v| v.as_str()) != Some(action) {
        return Err("native body action differs from declared operation".into());
    }
    let kind = value
        .params
        .get("kind")
        .and_then(|v| v.as_str())
        .ok_or("native asset kind is missing")?;
    let class = match (action, kind) {
        ("raw_import", "static_mesh") => "RawStaticMesh",
        ("finish", "static_mesh") => "StaticMesh",
        ("raw_import", "skeletal_mesh") => "RawSkeletalMesh",
        ("finish", "skeletal_mesh") => "SkeletalMesh",
        ("raw_import", "animation") => "RawAnimation",
        ("finish", "animation") => "Animation",
        ("raw_import", "texture") => "RawTexture",
        ("finish", "texture") => "Texture",
        ("raw_import", "sound") => "RawSound",
        ("finish", "sound") => "Sound",
        _ => return Err("unsupported native asset kind".into()),
    };
    let allowed = |actual: &str| {
        actual == class
            || (action == "finish" && actual == "Data")
            || (kind == "skeletal_mesh" && matches!(actual, "Skeleton" | "PhysicsAsset"))
    };
    if value.logical_outputs.is_empty()
        || value
            .logical_outputs
            .iter()
            .any(|item| !allowed(&item.class))
    {
        return Err("native output class differs from typed body operation".into());
    }
    let destination = value
        .params
        .get("destination")
        .and_then(|v| v.as_str())
        .ok_or("native destination missing")?;
    if !declared_packages(unit)?.contains(&package(destination)?) {
        return Err("native destination is not a declared package".into());
    }
    for item in &value.logical_outputs {
        if item.class == "Data" {
            finish_data_output(item)?;
            continue;
        }
        let stem = format!(
            "content/Game/{}",
            item.logical_path
                .strip_prefix("/Game/")
                .ok_or("invalid native output")?
        );
        if !item
            .files
            .iter()
            .any(|file| file.required && file.path == format!("{stem}.uasset"))
        {
            return Err("native item omits its required primary package".into());
        }
        if action == "raw_import" && !matches!(item.destination, crate::schema::Destination::Store)
        {
            return Err("raw native packages must remain store-only".into());
        }
        for file in &item.files {
            if ![
                ".uasset",
                ".umap",
                ".uexp",
                ".m.ubulk",
                ".ubulk",
                ".uptnl",
                ".upayload",
            ]
            .iter()
            .any(|suffix| file.path.ends_with(suffix))
            {
                return Err("native package contains an unsupported companion".into());
            }
        }
    }
    for name in ["source", "skeleton", "physics_asset"] {
        if let Some(slot) = value.params.get(name).and_then(|v| v.as_str()) {
            if !unit.inputs().iter().any(|input| {
                input.wire.name == slot && !matches!(input.payload, InputPayload::Absent)
            }) {
                return Err(format!("native body names undeclared content slot {slot}"));
            }
        }
    }
    Ok(())
}

/// B2 validates the exact frozen native files; live decoding/save/import evidence is
/// separately checked by the fixed keyed C3 worker and verify_completed, after drain.
pub fn validate_outputs(
    unit: &PreparedUnit,
    outputs: &[crate::results::FrozenOutput<'_>],
) -> Result<(), String> {
    check_unit(unit)?;
    if outputs.is_empty() {
        return Err("native unit produced no package files".into());
    }
    let declared: BTreeSet<_> = unit
        .ingredients()
        .logical_outputs
        .iter()
        .flat_map(|item| {
            item.files
                .iter()
                .filter(|f| f.required)
                .map(move |file| (item.id.as_str(), file.path.as_str()))
        })
        .collect();
    let actual: BTreeSet<_> = outputs
        .iter()
        .map(|output| (output.item.id.as_str(), output.path))
        .collect();
    if !declared.is_subset(&actual) {
        return Err("native frozen output omits required package files".into());
    }
    for output in outputs {
        if !unit.ingredients().logical_outputs.iter().any(|item| {
            item == output.item && item.files.iter().any(|file| file.path == output.path)
        }) {
            return Err("unowned native frozen output".into());
        }
        if output.object.size() == 0 && output.item.class != "Data" {
            return Err("empty native package output".into());
        }
        if output.item.class == "JsonData" {
            let mut bytes = Vec::new();
            output.object.reader().map_err(|e| e.to_string())?.read_to_end(&mut bytes).map_err(|e| e.to_string())?;
            serde_json::from_slice::<serde_json::Value>(&bytes).map_err(|e| e.to_string())?;
        }
        if output.item.class != "Data" && (output.path.ends_with(".uasset") || output.path.ends_with(".umap")) {
            let mut magic = [0; 4];
            output
                .object
                .reader()
                .map_err(|e| e.to_string())?
                .read_exact(&mut magic)
                .map_err(|e| e.to_string())?;
            if magic != [0xc1, 0x83, 0x2a, 0x9e] {
                return Err("native primary is not an Unreal package".into());
            }
        }
    }
    Ok(())
}

/// @cc [owner:fontanierh,label:correctness] production-unreal-keyed-context
/// Native sessions MUST use the keyed frozen worker and project binary/config bytes,
/// clone their own scratch project, and verify actual startup evidence before Run.
/// Installed engine/tool locations and DDC paths MUST stay execution-only. No caller
/// report or semantic-parameter boolean may substitute for matching keyed bytes.
pub fn prepare(
    unit: &PreparedUnit,
    staged: &StagedJob,
    sources: &SourceSnapshot,
    scope: &Path,
    execution: &UnrealExecutionContext,
) -> Result<PreparedUnrealLaunch, String> {
    if unit.ingredients().op.kind == VERIFY {
        return Err("native verification requires source-backed execution custody".into());
    }
    prepare_inner(unit, staged, sources, scope, execution)
}

/// Source-backed custody is private execution metadata, never a semantic parameter.
pub fn prepare_verify(
    unit: &PreparedUnit,
    staged: &StagedJob,
    sources: &SourceSnapshot,
    scope: &Path,
    execution: &UnrealExecutionContext,
    authority: &crate::native_verify::NativeVerifyContext,
) -> Result<PreparedUnrealLaunch, String> {
    prepare_verify_in_session(unit, staged, sources, scope, execution, authority, None)
}

pub(crate) fn prepare_verify_in_session(
    unit: &PreparedUnit,
    staged: &StagedJob,
    sources: &SourceSnapshot,
    scope: &Path,
    execution: &UnrealExecutionContext,
    authority: &crate::native_verify::NativeVerifyContext,
    owner: Option<&PreparedUnrealLaunch>,
) -> Result<PreparedUnrealLaunch, String> {
    if unit.ingredients().op.kind != VERIFY {
        return Err("verification context used for another operation".into());
    }
    let mut launch = prepare_inner(unit, staged, sources, scope, execution)?;
    native_store_transport(&mut launch.command.args)?;
    launch.profile.push_str("-native-store");
    let runtime = if let Some(owner) = owner {
        if owner.request.op.kind != VERIFY || owner.profile != launch.profile
            || owner.keepalive.expected() != launch.keepalive.expected()
            || owner.native_source_digest != launch.native_source_digest {
            return Err("resident verifier differs from the issued native session".into());
        }
        owner.keepalive.root()
    } else { launch.keepalive.root() };
    let carrier = authority.carrier(&runtime.join("Atelier.uproject"))?;
    let directory = staged.job_dir().join(".unreal-runtime");
    fs::create_dir_all(&directory).map_err(|e| e.to_string())?;
    if fs::symlink_metadata(&directory)
        .map_err(|e| e.to_string())?
        .file_type()
        .is_symlink()
    {
        return Err("linked native runtime scope".into());
    }
    use std::io::Write;
    use std::os::unix::fs::OpenOptionsExt;
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o400)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(directory.join("native-verify.json"))
        .map_err(|e| e.to_string())?;
    file.write_all(&serde_json::to_vec(&carrier).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    file.sync_all().map_err(|e| e.to_string())?;
    Ok(launch)
}

/// Only the fixed, privately authorized native restore operation uses the SDK's
/// normal Zen lifetime. Its DDC graph stays exactly filesystem/pak, not Zen-backed.
fn native_store_transport(args: &mut Vec<std::ffi::OsString>) -> Result<(), String> {
    if args.iter().filter(|arg| *arg == "-NoZenAutoLaunch").count() != 1
        || !args.iter().any(|arg| {
            arg.to_string_lossy()
                .starts_with("-DDC=(InstalledEnginePak,V2Local=(Type=FileSystem,Path=")
        })
    {
        return Err("native store session lacks the fixed isolated DDC command".into());
    }
    args.retain(|arg| arg != "-NoZenAutoLaunch");
    Ok(())
}

fn prepare_inner(
    unit: &PreparedUnit,
    staged: &StagedJob,
    sources: &SourceSnapshot,
    scope: &Path,
    execution: &UnrealExecutionContext,
) -> Result<PreparedUnrealLaunch, String> {
    let ingredients = unit.ingredients();
    if !matches!(
        ingredients.op.kind.as_str(),
        RAW_IMPORT | FINISH | AUTHOR | VERIFY
    ) || ingredients.op.version != OP_VERSION
        || (ingredients.op.kind == RAW_IMPORT && ingredients.script != ENTRY)
    {
        return Err("unsupported fixed native operation".into());
    }
    check_unit(unit)?;
    let bundle = frozen_worker(sources)?;
    let worker = worker_identity(&bundle);
    if ingredients.worker_digest != worker.digest
        || ingredients.worker_version != worker.version
        || execution.context.worker != bundle
    {
        return Err("native launch worker differs from keyed frozen worker".into());
    }
    let declared_settings = ingredients
        .params
        .get("settings")
        .map(|value| serde_json::from_value::<Vec<String>>(value.clone()))
        .transpose()
        .map_err(|_| "native settings must be a string array")?
        .unwrap_or_default();
    if declared_settings != execution.context.settings {
        return Err("loaded native settings differ from keyed settings".into());
    }
    let verification = ingredients.op.kind == VERIFY;
    let packages = if verification {
        BTreeSet::new()
    } else {
        declared_packages(unit)?
    };
    let data_author = ingredients.op.kind == AUTHOR && ingredients.logical_outputs.iter().all(|item| item.class == "JsonData");
    let data_files: BTreeSet<_> = ingredients.logical_outputs.iter()
        .filter(|item| ingredients.op.kind == FINISH && item.class == "Data")
        .flat_map(|item| item.files.iter().map(|file| file.path.as_str())).collect();
    if (!verification && !data_author && packages.is_empty())
        || ingredients
            .logical_outputs
            .iter()
            .any(|item| item.files.is_empty())
    {
        return Err("native unit needs complete explicit package outputs".into());
    }
    for output in &staged.request().outputs {
        if !verification && !data_author && !output.path.starts_with("content/Game/") && !data_files.contains(output.path.as_str()) {
            return Err("native outputs must use the fixed C3 content namespace".into());
        }
    }
    let scratch = ScratchProject::prepare(scope, &execution.context).map_err(|e| e.to_string())?;
    let keyed = keyed_digests(unit, staged)?;
    if execution
        .platform_plugins
        .iter()
        .any(|name| name != unreal::WORKER_PLUGIN)
    {
        return Err("only the fixed worker plugin is an execution-platform exception".into());
    }
    // The clone, not the live locator, must match a byte identity already in A3.
    for (relative, file) in &scratch.receipt().files {
        let platform = execution
            .platform_plugins
            .iter()
            .any(|name| relative.starts_with(&format!("Plugins/{name}/")));
        if !platform && !keyed.contains(&file.sha256) {
            return Err(format!(
                "native project binary is not a keyed content input: {}",
                file.source.display()
            ));
        }
    }
    for (destination, source) in &execution.config_sources {
        if !destination.starts_with("Config/")
            || !destination.ends_with(".ini")
            || destination
                .split('/')
                .any(|part| part.is_empty() || part == "." || part == "..")
            || destination.contains('\\')
        {
            return Err("native configuration must be a declared Config ini file".into());
        }
        let Some(SnapshotEntry::File(bytes)) = sources.get(source) else {
            return Err("native config source was not frozen".into());
        };
        if !keyed.contains(&sha256(bytes)) {
            return Err("native config bytes are not keyed".into());
        }
        let path = scratch.root().join(destination);
        fs::create_dir_all(path.parent().ok_or("missing config parent")?)
            .map_err(|e| e.to_string())?;
        use std::io::Write;
        let mut file = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)
            .map_err(|e| e.to_string())?;
        file.write_all(bytes).map_err(|e| e.to_string())?;
        fs::set_permissions(path, fs::Permissions::from_mode(0o444)).map_err(|e| e.to_string())?;
    }
    let command =
        unreal::job_loop_command(&execution.context, &scratch).map_err(|e| e.to_string())?;
    let command = WorkerCommand {
        program: command.program,
        args: command.args.into_iter().map(Into::into).collect(),
        env: command.env,
        cwd: command.cwd,
    };
    let request = body_request(staged.request().clone())?;
    Ok(PreparedUnrealLaunch {
        command,
        worker,
        profile: execution.context.profile(),
        keepalive: scratch,
        request,
        packages,
        context_verified: Cell::new(false),
        native_source_digest: native_source_digest(unit)?,
    })
}

fn body_request(mut request: crate::protocol::JobRequest) -> Result<crate::protocol::JobRequest, String> {
    // Raw/finish and the fixed Zen body receive their own schema; author bodies
    // also validate their declared startup settings alongside authored arguments.
    if request.op.kind != AUTHOR {
        request.params.remove("settings");
    }
    // The expanded closure is already keyed and staged as ordinary input Items.
    // The fixed importer receives no custom callback arguments.
    if request.op.kind == RAW_IMPORT
        && request.params.get("args").and_then(serde_json::Value::as_object)
            .is_some_and(|args| args.len() == 1 && args.contains_key("closure"))
    {
        request.params.remove("args");
    }
    if let Some(modules) = request.params.remove("native_modules") {
        // Locations::build already materialized and verified these exact context inputs.
        // Keep complete keyed/staged verification; only the authored body's view omits them.
        let slots = crate::native_modules::body_input_slots(&modules)?;
        request.inputs.retain(|input| !slots.contains(&input.name));
    }
    Ok(request)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn finish_opaque_data_is_canonical_and_never_native_or_external() {
        let valid: crate::schema::Item = serde_json::from_value(serde_json::json!({
            "id":"geometry","logical_path":"/Internal/ImportedGeometry/A","class":"Data","destination":"store",
            "files":[{"path":"data/imported-geometry/A.bin","required":true}]})).unwrap();
        assert!(finish_data_output(&valid).is_ok());
        for path in ["content/Game/A.uasset", "data/../A.bin", "data//A.bin", "/data/A.bin"] {
            let mut item = valid.clone(); item.files[0].path = path.into();
            assert!(finish_data_output(&item).is_err(), "accepted {path}");
        }
        let mut external = valid.clone(); external.destination = crate::schema::Destination::External;
        assert!(finish_data_output(&external).is_err());
        let mut native = valid.clone(); native.class = "StaticMesh".into();
        assert!(finish_data_output(&native).is_err());
        let mut empty = valid; empty.files.clear(); assert!(finish_data_output(&empty).is_err());
    }

    #[test]
    fn native_package_names_refuse_aliases_and_non_game_names() {
        assert_eq!(package("/Game/Raw/Mesh_01").unwrap(), "/Game/Raw/Mesh_01");
        let ordinary: Vec<std::ffi::OsString> = [
            "-nowrite",
            "-NoZenAutoLaunch",
            "-DDC=(InstalledEnginePak,V2Local=(Type=FileSystem,Path=/owned/ddc))",
        ]
        .into_iter()
        .map(Into::into)
        .collect();
        let mut native = ordinary.clone();
        native_store_transport(&mut native).unwrap();
        assert!(ordinary.iter().any(|arg| arg == "-NoZenAutoLaunch"));
        assert!(!native.iter().any(|arg| arg == "-NoZenAutoLaunch"));
        assert_eq!(native, vec![ordinary[0].clone(), ordinary[2].clone()]);
        assert!(native_store_transport(&mut native).is_err());
        assert!(native_store_transport(&mut vec!["-NoZenAutoLaunch".into()]).is_err());
        for value in [
            "/Engine/Foo",
            "/Game/../Foo",
            "/Game/Foo.Bar",
            "/Game//Foo",
            "/Game/Foo/",
        ] {
            assert!(package(value).is_err(), "{value}");
        }
    }

    #[test]
    fn native_registry_is_fixed_and_never_replaces_an_existing_definition() {
        let mut registry = OpRegistry::new();
        register(&mut registry, &BTreeMap::from([("source".into(), false)])).unwrap();
        assert_eq!(registry.len(), 4);
        assert!(registry[&(RAW_IMPORT.into(), OP_VERSION.into())].params["destination"].required);
        for class in ["AnimCurveCompressionSettings", "MirrorDataTable"] {
            assert!(registry[&(AUTHOR.into(), OP_VERSION.into())].output_classes.contains(class));
            assert!(registry[&(AUTHOR.into(), OP_VERSION.into())].inputs["source"].item_classes.contains(class));
        }
        assert!(register(&mut registry, &BTreeMap::new()).is_err());
        let request: crate::protocol::JobRequest = serde_json::from_value(serde_json::json!({
            "job_id":"job", "unit":"material", "op":{"kind":AUTHOR,"version":"1"},
            "job_dir":"/job", "script":"game/material.py", "code":["game/material.py"],
            "inputs":[], "outputs":[], "params":{"args":{"asset":"M"},"settings":[]}
        })).unwrap();
        let authored = body_request(request.clone()).unwrap();
        assert_eq!(authored.params, request.params);
        for kind in [RAW_IMPORT, FINISH, VERIFY] {
            let mut typed = request.clone();
            typed.op.kind = kind.into();
            assert!(!body_request(typed).unwrap().params.contains_key("settings"));
        }
        assert!(request.params.contains_key("settings"));
        let mut raw_closure = request.clone();
        raw_closure.op.kind = RAW_IMPORT.into();
        raw_closure.params.insert("args".into(), serde_json::json!({"closure":{"materials":[]}}));
        let raw_body = body_request(raw_closure.clone()).unwrap();
        assert!(!raw_body.params.contains_key("args"));
        assert!(raw_closure.params.contains_key("args"));
        let mut bound = request.clone();
        bound.params.insert("native_modules".into(), serde_json::json!({
            "editor":{"slot":"compiled_editor","archive":"binaries.tree.tar",
                "modules":[{"name":"Game","kind":"Runtime","loading_phase":"Default"}]},
            "plugins":[{"name":"Owned","slot":"compiled_plugin_Owned","archive":"binaries.tree.tar",
                "descriptor_slot":"compiled_descriptor_Owned"}]}));
        for name in ["source", "compiled_editor", "compiled_plugin_Owned", "compiled_descriptor_Owned", "compiled_semantic_asset"] {
            bound.inputs.push(crate::protocol::StagedInput { name:name.into(), path:format!("inputs/{name}"),
                identity:crate::schema::ContentIdentity::Digest{digest:crate::source_hashes::sha256(name.as_bytes())} });
        }
        let body = body_request(bound.clone()).unwrap();
        assert_eq!(body.inputs.iter().map(|input| input.name.as_str()).collect::<Vec<_>>(), ["source", "compiled_semantic_asset"]);
        assert!(!body.params.contains_key("native_modules"));
        assert!(body.params.contains_key("settings"));
        assert_eq!(bound.inputs.len(), 5);
        bound.params.insert("native_modules".into(), serde_json::json!({"editor":{},"unknown":true}));
        assert!(body_request(bound).is_err());
    }
}

pub fn register(registry: &mut OpRegistry, slots: &BTreeMap<String, bool>) -> Result<(), String> {
    if [RAW_IMPORT, FINISH, AUTHOR, VERIFY]
        .iter()
        .any(|kind| registry.contains_key(&(kind.to_string(), OP_VERSION.into())))
    {
        return Err("native operation already registered".into());
    }
    let classes: BTreeSet<String> = [
        "Data",
        "StaticMeshSource",
        "RawStaticMesh",
        "StaticMesh",
        "RawSkeletalMesh",
        "SkeletalMesh",
        "Skeleton",
        "PhysicsAsset",
        "RawAnimation",
        "Animation",
        "RawTexture",
        "Texture",
        "RawSound",
        "Sound",
        "Material",
        "MaterialInstance",
        "MaterialParameterCollection",
        "Blueprint",
        "BlendSpace1D",
        "AdventureMoveSet",
        "WandererDefinition",
        "AnimBoneCompressionSettings",
                "AnimCurveCompressionSettings",
                "MirrorDataTable",
                "SoundAttenuation",
                "DataAsset",
        "JsonData",
        "Map",
    ]
    .into_iter()
    .map(Into::into)
    .collect();
    registry.insert(
        (VERIFY.into(), OP_VERSION.into()),
        OpDefinition {
            inputs: slots
                .iter()
                .map(|(name, broad)| {
                    (
                        name.clone(),
                        InputRule {
                            role: InputRole::Content,
                            required: false,
                            allow_absent_file: false,
                            allow_selector: true,
                            require_whole_reason: *broad,
                            item_classes: BTreeSet::from(["NativeCookRecord".into()]),
                        },
                    )
                })
                .collect(),
            output_classes: BTreeSet::from(["JsonData".into()]),
            params: BTreeMap::from([
                (
                    "package".into(),
                    ParamRule {
                        kind: ParamKind::String,
                        required: true,
                    },
                ),
                (
                    "mode".into(),
                    ParamRule {
                        kind: ParamKind::String,
                        required: true,
                    },
                ),
                (
                    "settings".into(),
                    ParamRule {
                        kind: ParamKind::Array,
                        required: false,
                    },
                ),
            ]),
        },
    );
    registry.insert(
        (AUTHOR.into(), OP_VERSION.into()),
        OpDefinition {
            inputs: slots
                .iter()
                .map(|(name, broad)| {
                    (
                        name.clone(),
                        InputRule {
                            role: InputRole::Content,
                            required: false,
                            allow_absent_file: false,
                            allow_selector: true,
                            require_whole_reason: *broad,
                            item_classes: classes.clone(),
                        },
                    )
                })
                .collect(),
            output_classes: classes.clone(),
            params: BTreeMap::from([
                (
                    "args".into(),
                    ParamRule {
                        kind: ParamKind::Object,
                        required: true,
                    },
                ),
                (
                    "settings".into(),
                    ParamRule {
                        kind: ParamKind::Array,
                        required: false,
                    },
                ),
                (
                    "input_roots".into(),
                    ParamRule {
                        kind: ParamKind::Object,
                        required: false,
                    },
                ),
                ("native_modules".into(), ParamRule {kind: ParamKind::Object, required: false}),
            ]),
        },
    );
    for (kind, action) in [(RAW_IMPORT, "raw_import"), (FINISH, "finish")] {
        let inputs = slots
            .iter()
            .map(|(name, broad)| {
                (
                    name.clone(),
                    InputRule {
                        role: InputRole::Content,
                        required: false,
                        allow_absent_file: false,
                        allow_selector: true,
                        require_whole_reason: *broad,
                        item_classes: classes.clone(),
                    },
                )
            })
            .collect();
        let mut params = BTreeMap::new();
        for name in ["op", "kind", "source", "destination"] {
            params.insert(
                name.into(),
                ParamRule {
                    kind: ParamKind::String,
                    required: true,
                },
            );
        }
        for name in [
            "properties",
            "args",
            "fbx",
            "package_sources",
            "partners",
            "input_roots",
            "native_modules",
        ] {
            params.insert(
                name.into(),
                ParamRule {
                    kind: ParamKind::Object,
                    required: false,
                },
            );
        }
        params.insert("create_physics_asset".into(), ParamRule {kind: ParamKind::Bool, required: false});
        for name in ["skeleton", "physics_asset", "source_member"] {
            params.insert(
                name.into(),
                ParamRule {
                    kind: ParamKind::String,
                    required: false,
                },
            );
        }
        for name in ["materials", "lod_build_settings", "settings"] {
            params.insert(
                name.into(),
                ParamRule {
                    kind: ParamKind::Array,
                    required: false,
                },
            );
        }
        let key = (kind.into(), OP_VERSION.into());
        if registry
            .insert(
                key,
                OpDefinition {
                    inputs,
                    output_classes: classes.clone(),
                    params,
                },
            )
            .is_some()
        {
            return Err(format!("native op already registered: {action}"));
        }
    }
    Ok(())
}
