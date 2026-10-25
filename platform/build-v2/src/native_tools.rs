//! Fixed native tool worker source bundle. The existing guard owns its whole child tree.
use crate::keys::{ImplementationIdentity, canonical_bytes};
use crate::source_hashes::sha256;
use crate::validate::{SnapshotEntry, SourceSnapshot};
use std::collections::BTreeMap;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::Path;

pub const NATIVE_TOOL_VERSION: &str = "atelier-native-tool-job-1";
pub const NATIVE_TOOL_FILES: [&str; 5] = [
    "protocol.py",
    "recipe_job.py",
    "unreal_tool_ops.py",
    "native_tool_worker.py",
    "zen_package_finalise.py",
];

pub struct NativeToolBundle {
    files: BTreeMap<String, Vec<u8>>,
    identity: ImplementationIdentity,
}

impl NativeToolBundle {
    /// @cc [owner:fontanierh,label:correctness] frozen-native-tool-source
    /// Identity MUST bind the exact fixed worker, protocol, ROOT codec and command helpers.
    /// Launch MUST execute those read-only bytes. Engine/SDK/interpreter locators MUST
    /// remain execution context, never automatic semantic key ingredients.
    pub fn from_snapshot(snapshot: &SourceSnapshot) -> Result<Self, String> {
        if snapshot.len() != NATIVE_TOOL_FILES.len() {
            return Err("native tool snapshot requires its exact five source files".into());
        }
        let mut files = BTreeMap::new();
        for name in NATIVE_TOOL_FILES {
            let Some(SnapshotEntry::File(bytes)) = snapshot.get(name) else {
                return Err(format!(
                    "native tool source is not frozen regular data: {name}"
                ));
            };
            files.insert(name.to_string(), bytes.clone());
        }
        let digests: BTreeMap<_, _> = files
            .iter()
            .map(|(name, bytes)| (name, sha256(bytes)))
            .collect();
        let digest = sha256(&canonical_bytes(&serde_json::json!({
            "domain":"atelier-native-tool-worker", "version":1, "files":digests,
        }))?);
        Ok(Self {
            files,
            identity: ImplementationIdentity {
                version: NATIVE_TOOL_VERSION.into(),
                digest,
            },
        })
    }

    pub fn identity(&self) -> ImplementationIdentity {
        self.identity.clone()
    }

    /// Bind the actual prepared source key and owned persistence scope as execution
    /// controls. Neither value changes the frozen worker implementation identity.
    pub fn command_for_cook(
        &self,
        interpreter: &Path,
        engine_root: &Path,
        owned_scope: &Path,
        source_key: &str,
        zen_state_root: &Path,
        export_project: &Path,
    ) -> Result<crate::guard_adapter::WorkerCommand, String> {
        if source_key.len() != 64
            || !source_key
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            || !zen_state_root.is_absolute()
            || !export_project.is_absolute()
        {
            return Err(
                "cook execution requires a complete source key and absolute owned Zen scope".into(),
            );
        }
        let mut command = self.command(interpreter, engine_root, owned_scope)?;
        command.args.extend([
            "--source-key".into(),
            source_key.into(),
            "--zen-state-root".into(),
            zen_state_root.as_os_str().to_owned(),
            "--export-project".into(),
            export_project.as_os_str().to_owned(),
        ]);
        Ok(command)
    }

    pub fn command(
        &self,
        interpreter: &Path,
        engine_root: &Path,
        owned_scope: &Path,
    ) -> Result<crate::guard_adapter::WorkerCommand, String> {
        if !interpreter.is_absolute() || !engine_root.is_absolute() || !owned_scope.is_absolute() {
            return Err("native execution locators must be absolute".into());
        }
        let directory = owned_scope.join("native-tool-worker");
        fs::create_dir(&directory).map_err(|error| error.to_string())?;
        for (name, bytes) in &self.files {
            let mut file = OpenOptions::new()
                .write(true)
                .create_new(true)
                .mode(0o444)
                .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(directory.join(name))
                .map_err(|error| error.to_string())?;
            file.write_all(bytes).map_err(|error| error.to_string())?;
            file.set_permissions(fs::Permissions::from_mode(0o444))
                .map_err(|error| error.to_string())?;
            file.sync_all().map_err(|error| error.to_string())?;
        }
        fs::set_permissions(&directory, fs::Permissions::from_mode(0o555))
            .map_err(|error| error.to_string())?;
        Ok(crate::guard_adapter::WorkerCommand {
            program: interpreter.to_path_buf(),
            args: vec![
                "-I".into(),
                "-B".into(),
                directory.join("native_tool_worker.py").into_os_string(),
                "--engine-root".into(),
                engine_root.as_os_str().to_owned(),
            ],
            env: BTreeMap::from([
                ("LC_ALL".into(), "C".into()),
                ("TZ".into(), "UTC".into()),
                ("PATH".into(), "/usr/bin:/bin:/usr/sbin:/sbin".into()),
            ]),
            cwd: "/".into(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn native_worker_identity_binds_exact_project_sources_only() {
        let mut source: SourceSnapshot = NATIVE_TOOL_FILES
            .into_iter()
            .map(|name| {
                (
                    name.into(),
                    SnapshotEntry::File(format!("# frozen {name}\n").into_bytes()),
                )
            })
            .collect();
        let first = NativeToolBundle::from_snapshot(&source).unwrap().identity();
        source.insert(
            "native_tool_worker.py".into(),
            SnapshotEntry::File(b"# changed\n".to_vec()),
        );
        assert_ne!(
            first.digest,
            NativeToolBundle::from_snapshot(&source)
                .unwrap()
                .identity()
                .digest
        );
        source.insert(
            "sdk-version".into(),
            SnapshotEntry::File(b"installed SDK".to_vec()),
        );
        assert!(NativeToolBundle::from_snapshot(&source).is_err());
    }
}
