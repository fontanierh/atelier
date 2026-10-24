//! The explicit project worker implementation, independent of installed Python/platform identity.
use crate::keys::{ImplementationIdentity, canonical_bytes};
use crate::launch::{BLENDER_JOB_LOOP_VERSION, PYTHON_JOB_LOOP_VERSION, WorkerCommand};
use crate::source_hashes::sha256;
use crate::validate::{SnapshotEntry, SourceSnapshot};
use std::collections::BTreeMap;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::Path;

pub const PYTHON_WORKER_FILES: [&str; 3] = ["protocol.py", "python_job.py", "python_worker.py"];
pub const BLENDER_WORKER_FILES: [&str; 5] = [
    "protocol.py",
    "python_job.py",
    "python_worker.py",
    "blender_job.py",
    "blender_worker.py",
];

enum WorkerKind {
    Python,
    Blender,
}

/// Private bytes and their implementation identity; never a locator or a caller's digest claim.
pub struct PythonWorkerBundle {
    files: BTreeMap<String, Vec<u8>>,
    identity: ImplementationIdentity,
    kind: WorkerKind,
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};
    static NEXT: AtomicU64 = AtomicU64::new(0);
    #[test]
    fn command_loads_private_readonly_worker_bytes_bound_before_locator_changes() {
        let mut snapshot: SourceSnapshot = PYTHON_WORKER_FILES
            .into_iter()
            .map(|name| {
                (
                    name.into(),
                    SnapshotEntry::File(format!("# frozen {name}\n").into_bytes()),
                )
            })
            .collect();
        let bundle = PythonWorkerBundle::from_snapshot(&snapshot).unwrap();
        let identity = bundle.identity();
        snapshot.insert(
            "python_job.py".into(),
            SnapshotEntry::File(b"# later live edit".to_vec()),
        );
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "atelier-v2-worker-bundle-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        let interpreter = Path::new("/platform/python");
        let command = bundle.command(interpreter, &root).unwrap();
        assert_eq!(command.program, interpreter);
        assert_eq!(bundle.identity().digest, identity.digest);
        assert_eq!(
            fs::read(root.join("worker/python_job.py")).unwrap(),
            b"# frozen python_job.py\n"
        );
        for name in PYTHON_WORKER_FILES {
            assert_eq!(
                fs::metadata(root.join("worker").join(name))
                    .unwrap()
                    .permissions()
                    .mode()
                    & 0o777,
                0o444
            );
        }
        assert!(
            command
                .args
                .iter()
                .any(|arg| arg == &root.join("worker/python_worker.py").into_os_string())
        );
        assert!(bundle.command(interpreter, &root).is_err());
        fs::set_permissions(root.join("worker"), fs::Permissions::from_mode(0o755)).unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn blender_bundle_binds_all_five_files_and_uses_original_three_thread_command() {
        let mut snapshot: SourceSnapshot = BLENDER_WORKER_FILES
            .into_iter()
            .map(|name| {
                (
                    name.into(),
                    SnapshotEntry::File(format!("# frozen {name}\n").into_bytes()),
                )
            })
            .collect();
        let bundle = PythonWorkerBundle::from_blender_snapshot(&snapshot).unwrap();
        assert_eq!(bundle.identity().version, BLENDER_JOB_LOOP_VERSION);
        assert_eq!(bundle.file_count(), 5);
        let identity = bundle.identity();
        for name in BLENDER_WORKER_FILES {
            let mut changed = snapshot.clone();
            changed.insert(
                name.into(),
                SnapshotEntry::File(b"changed implementation".to_vec()),
            );
            assert_ne!(
                PythonWorkerBundle::from_blender_snapshot(&changed)
                    .unwrap()
                    .identity()
                    .digest,
                identity.digest,
                "unbound worker source {name}"
            );
            changed.remove(name);
            assert!(PythonWorkerBundle::from_blender_snapshot(&changed).is_err());
        }
        snapshot.insert("extra.py".into(), SnapshotEntry::File(vec![]));
        assert!(PythonWorkerBundle::from_blender_snapshot(&snapshot).is_err());
        assert!(PythonWorkerBundle::from_snapshot(&snapshot).is_err());
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "atelier-v2-blender-bundle-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        let command = bundle
            .command(Path::new("/installed/Blender"), &root)
            .unwrap();
        let expected = WorkerCommand::blender_job_loop(
            "/installed/Blender".into(),
            root.join("worker/blender_worker.py"),
        )
        .unwrap();
        assert_eq!(command.program, expected.program);
        assert_eq!(
            command.args,
            expected
                .args
                .iter()
                .map(std::ffi::OsString::from)
                .collect::<Vec<_>>()
        );
        assert_eq!(command.env, expected.env);
        assert_eq!(command.cwd, expected.cwd);
        for name in BLENDER_WORKER_FILES {
            let path = root.join("worker").join(name);
            assert_eq!(
                fs::read(&path).unwrap(),
                format!("# frozen {name}\n").as_bytes()
            );
            assert_eq!(
                fs::metadata(path).unwrap().permissions().mode() & 0o777,
                0o444
            );
        }
        fs::set_permissions(root.join("worker"), fs::Permissions::from_mode(0o755)).unwrap();
        fs::remove_dir_all(root).unwrap();
    }
}

impl PythonWorkerBundle {
    /// @cc [owner:fontanierh,label:correctness] frozen-python-worker-implementation
    /// Worker identity MUST bind every explicitly frozen worker/job/protocol source byte and
    /// stable relative name. Launch MUST load those same read-only materialized bytes, never a
    /// live checkout worker path. Installed interpreter/dependencies and source locator/stat
    /// metadata MUST NOT automatically enter this identity. See tests/python_worker_bundle.rs;
    /// A6 guards source epoch acceptance separately.
    pub fn from_snapshot(snapshot: &SourceSnapshot) -> Result<Self, String> {
        if snapshot.len() != PYTHON_WORKER_FILES.len() {
            return Err(
                "worker snapshot must contain exactly the three declared implementation files"
                    .into(),
            );
        }
        let mut files = BTreeMap::new();
        for name in PYTHON_WORKER_FILES {
            let Some(SnapshotEntry::File(bytes)) = snapshot.get(name) else {
                return Err(format!(
                    "worker implementation is not frozen regular data: {name}"
                ));
            };
            files.insert(name.to_string(), bytes.clone());
        }
        let digests: BTreeMap<_, _> = files
            .iter()
            .map(|(name, bytes)| (name, sha256(bytes)))
            .collect();
        let digest = sha256(&canonical_bytes(&serde_json::json!({
            "domain":"atelier-static-python-worker", "version":1, "files":digests,
        }))?);
        Ok(Self {
            files,
            identity: ImplementationIdentity {
                version: PYTHON_JOB_LOOP_VERSION.into(),
                digest,
            },
            kind: WorkerKind::Python,
        })
    }

    /// @cc [owner:fontanierh,label:correctness;safety] frozen-blender-worker-implementation
    /// The native bundle MUST contain exactly the existing five Blender/Python job-loop
    /// sources and bind every byte/name to the Blender worker identity. Launch MUST use
    /// those readonly materialized bytes through the original three-thread Blender
    /// command, not a live source path or caller-defined worker. Installed tool paths
    /// MUST remain execution context rather than source identity ingredients.
    pub fn from_blender_snapshot(snapshot: &SourceSnapshot) -> Result<Self, String> {
        if snapshot.len() != BLENDER_WORKER_FILES.len() {
            return Err("Blender worker requires exactly its five implementation files".into());
        }
        let mut files = BTreeMap::new();
        for name in BLENDER_WORKER_FILES {
            let Some(SnapshotEntry::File(bytes)) = snapshot.get(name) else {
                return Err(format!(
                    "Blender worker implementation is not frozen regular data: {name}"
                ));
            };
            files.insert(name.to_string(), bytes.clone());
        }
        let digests: BTreeMap<_, _> = files
            .iter()
            .map(|(name, bytes)| (name, sha256(bytes)))
            .collect();
        let digest = sha256(&canonical_bytes(&serde_json::json!({
            "domain":"atelier-static-blender-worker", "version":1, "files":digests,
        }))?);
        Ok(Self {
            files,
            identity: ImplementationIdentity {
                version: BLENDER_JOB_LOOP_VERSION.into(),
                digest,
            },
            kind: WorkerKind::Blender,
        })
    }

    pub(crate) fn file_count(&self) -> usize {
        self.files.len()
    }

    pub fn identity(&self) -> ImplementationIdentity {
        self.identity.clone()
    }

    pub(crate) fn command(
        &self,
        interpreter: &Path,
        owned_scope: &Path,
    ) -> Result<crate::guard_adapter::WorkerCommand, String> {
        let directory = owned_scope.join("worker");
        fs::create_dir(&directory)
            .map_err(|error| format!("cannot reserve worker folder: {error}"))?;
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
        let command = match self.kind {
            WorkerKind::Python => WorkerCommand::python_job_loop(
                interpreter.to_path_buf(),
                directory.join("python_worker.py"),
            ),
            WorkerKind::Blender => WorkerCommand::blender_job_loop(
                interpreter.to_path_buf(),
                directory.join("blender_worker.py"),
            ),
        }
        .map_err(|error| error.to_string())?;
        Ok(crate::guard_adapter::WorkerCommand {
            program: command.program,
            args: command.args.into_iter().map(Into::into).collect(),
            env: command.env,
            cwd: command.cwd,
        })
    }
}
