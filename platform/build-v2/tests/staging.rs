//! C1b: frozen-input staging, output collection and real Python jobs over inherited pipes.
use atelier_build_v2::launch::*;
use atelier_build_v2::protocol::FailureKind;
use atelier_build_v2::staging::*;
use atelier_build_v2::store::ObjectDigest;
use atelier_build_v2::{keys::*, schema::*, source_hashes::*, validate::*};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

static SERIAL: AtomicU64 = AtomicU64::new(0);

const UNITS: &str = r#"
schema_version = 1
cache_version = "v2-1"

[[units]]
id = "demo.piece"
op = { kind = "py_data", version = "1" }
script = "ops/piece.py"
code = ["ops/piece.py", "ops/helper.py"]
params = { seed = 7, scale = 2 }
inputs = [
  { role = "content", name = "shape", source = { kind = "file", path = "SOURCE/shape.json", selector = "/triangle" } },
  { role = "content", name = "extra", source = { kind = "file", path = "SOURCE/extra.txt", optional = true } },
  { role = "content", name = "mesh", source = { kind = "item", unit = "demo.mesh", item = "mesh" } },
]
outputs = [
  { id = "piece", logical_path = "/Game/Demo/Piece", class = "StaticMeshSource", files = [{ path = "piece.txt", install_path = "Content/Demo/piece.txt" }, { path = "notes/extra.txt", install_path = "Content/Demo/notes.txt", required = false }], destination = "checkout" },
]

[[units]]
id = "demo.mesh"
op = { kind = "py_data", version = "1" }
script = "ops/mesh.py"
code = ["ops/mesh.py"]
outputs = [
  { id = "mesh", logical_path = "/Game/Demo/Mesh", class = "StaticMeshSource", files = [{ path = "mesh.bin" }, { path = "bin/tool.sh" }], destination = "store" },
]
"#;

const PIECE: &str = r#"
import os, random
import helper

def run(context):
    mesh = context.input('mesh')
    members = sorted(str(path.relative_to(mesh)) for path in mesh.rglob('*'))
    # The staged mode bits, not os.access: the sandbox lets jobs execute nothing but the interpreter.
    tool = bool(os.stat(mesh / 'bin/tool.sh').st_mode & 0o111)
    data = bool(os.stat(mesh / 'mesh.bin').st_mode & 0o111)
    text = helper.render(context.input('shape').read_text(), (mesh / 'mesh.bin').read_text(), members, tool,
                         data, context.inputs['extra'], dict(context.params), random.random())
    context.output('piece.txt').write_text(text)
    if context.params.get('notes'):
        context.output('notes/extra.txt').write_text('notes')
    for attempt in context.params.get('attempts', []):
        exec(attempt)
"#;

const HELPER: &str = "def render(*parts):\n    return repr(parts)\n";

struct Workspace(PathBuf);
impl Workspace {
    fn new() -> Self {
        let path = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "atelier-v2-staging-{}-{}",
            std::process::id(),
            SERIAL.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
    fn path(&self, name: &str) -> PathBuf {
        self.0.join(name)
    }
}
impl Drop for Workspace {
    fn drop(&mut self) {
        for entry in fs::read_dir(&self.0).unwrap() {
            let path = entry.unwrap().path();
            if path.join("output").is_dir() {
                remove_job(&path).unwrap();
            }
        }
        fs::remove_dir_all(&self.0).unwrap();
    }
}

/// Test object bytes by digest; written read-only like a clone.
#[derive(Default)]
struct MemoryObjects(BTreeMap<String, Vec<u8>>);
impl MemoryObjects {
    fn add(&mut self, bytes: &[u8]) -> String {
        let digest = sha256(bytes);
        self.0.insert(digest.clone(), bytes.to_vec());
        digest
    }
}
impl ObjectSource for MemoryObjects {
    fn clone_object(&self, digest: &ObjectDigest, destination: &Path) -> Result<(), SourceError> {
        let refuse = |kind, message: String| SourceError {
            kind,
            digest: digest.clone(),
            message,
        };
        let bytes = self.0.get(digest.as_hex()).ok_or_else(|| {
            refuse(
                SourceErrorKind::Unavailable,
                "object is not in the store".into(),
            )
        })?;
        fs::write(destination, bytes)
            .and_then(|()| fs::set_permissions(destination, fs::Permissions::from_mode(0o444)))
            .map_err(|error| refuse(SourceErrorKind::Io, error.to_string()))
    }
}

/// A source whose certified bytes changed after certification: it refuses every object.
struct ChangedObjects;
impl ObjectSource for ChangedObjects {
    fn clone_object(&self, digest: &ObjectDigest, _: &Path) -> Result<(), SourceError> {
        Err(SourceError {
            kind: SourceErrorKind::Changed,
            digest: digest.clone(),
            message: "the certified source file was replaced".into(),
        })
    }
}

struct Fixture {
    declaration: Declaration,
    snapshot: SourceSnapshot,
    staged: BTreeMap<String, String>,
    produced: ProducedItems,
    objects: MemoryObjects,
}

fn registry() -> OpRegistry {
    let rule = || InputRule {
        role: InputRole::Content,
        required: false,
        allow_absent_file: true,
        allow_selector: true,
        require_whole_reason: false,
        item_classes: BTreeSet::from(["StaticMeshSource".into()]),
    };
    let integer = || ParamRule {
        kind: ParamKind::Integer,
        required: false,
    };
    BTreeMap::from([(
        ("py_data".into(), "1".into()),
        OpDefinition {
            inputs: BTreeMap::from([
                ("shape".into(), rule()),
                ("extra".into(), rule()),
                ("mesh".into(), rule()),
            ]),
            output_classes: BTreeSet::from(["StaticMeshSource".into()]),
            params: BTreeMap::from([
                ("seed".into(), integer()),
                ("scale".into(), integer()),
                (
                    "notes".into(),
                    ParamRule {
                        kind: ParamKind::Bool,
                        required: false,
                    },
                ),
                (
                    "attempts".into(),
                    ParamRule {
                        kind: ParamKind::Array,
                        required: false,
                    },
                ),
            ]),
        },
    )])
}

impl Fixture {
    /// `source` is where this checkout keeps the unit's data files: a locator, never staged.
    fn new(source: &str) -> Self {
        let declaration = parse_declaration(&UNITS.replace("SOURCE", source)).unwrap();
        let snapshot = BTreeMap::from([
            (
                "ops/piece.py".into(),
                SnapshotEntry::File(PIECE.as_bytes().to_vec()),
            ),
            (
                "ops/helper.py".into(),
                SnapshotEntry::File(HELPER.as_bytes().to_vec()),
            ),
            (
                "ops/mesh.py".into(),
                SnapshotEntry::File(b"unused".to_vec()),
            ),
            (
                format!("{source}/shape.json"),
                SnapshotEntry::File(br#"{"triangle":[1,2,3],"unused":0}"#.to_vec()),
            ),
        ]);
        let mut objects = MemoryObjects::default();
        let mesh = objects.add(b"mesh bytes");
        let tool = objects.add(b"#!/bin/sh\n");
        let produced = BTreeMap::from([(
            ("demo.mesh".into(), "mesh".into()),
            StoredItem {
                item: declaration.units[1].outputs[0].clone(),
                files: vec![
                    StoredFile {
                        path: "mesh.bin".into(),
                        digest: mesh,
                        size: 10,
                        mode: 0o644,
                    },
                    StoredFile {
                        path: "bin/tool.sh".into(),
                        digest: tool,
                        size: 10,
                        mode: 0o755,
                    },
                ],
                external_locator: None,
            },
        )]);
        Self {
            declaration,
            snapshot,
            staged: BTreeMap::from([
                ("shape".into(), "in/shape.json".into()),
                ("extra".into(), "in/extra.txt".into()),
                ("mesh".into(), "in/mesh".into()),
            ]),
            produced,
            objects,
        }
    }

    fn params(&mut self, params: serde_json::Value) {
        self.declaration.units[0].params = serde_json::from_value(params).unwrap();
    }

    fn prepared(&self) -> PreparedUnit {
        self.prepared_with_worker(PYTHON_JOB_LOOP_VERSION)
    }

    fn prepared_with_worker(&self, worker: &str) -> PreparedUnit {
        let validated = validate(
            &self.declaration,
            &registry(),
            &self.snapshot,
            &["Content".into()],
        )
        .unwrap();
        let identity = |version: &str| ImplementationIdentity {
            version: version.into(),
            digest: sha256(version.as_bytes()),
        };
        prepare(
            &self.declaration,
            &validated,
            "demo.piece",
            &KeyContext {
                snapshot: &self.snapshot,
                versions: &BTreeMap::new(),
                produced: &self.produced,
                produced_groups: &BTreeMap::new(),
                staged_inputs: &self.staged,
                worker: &identity(worker),
                validator: &identity("validator-1"),
            },
            &mut SourceHashCache::default(),
        )
        .unwrap()
    }
}

fn mode(path: &Path) -> u32 {
    fs::symlink_metadata(path).unwrap().permissions().mode() & 0o7777
}

fn files_below(root: &Path) -> Vec<String> {
    let mut found = vec![];
    let mut pending = vec![root.to_path_buf()];
    while let Some(directory) = pending.pop() {
        for entry in fs::read_dir(directory).unwrap() {
            let path = entry.unwrap().path();
            found.push(
                path.strip_prefix(root)
                    .unwrap()
                    .to_str()
                    .unwrap()
                    .to_string(),
            );
            if path.is_dir() {
                pending.push(path);
            }
        }
    }
    found.sort();
    found
}

#[test]
fn only_keyed_blender_worker_receives_empty_private_runtime_scratch() {
    let space = Workspace::new();
    let fixture = Fixture::new("assets/demo");
    let plain = stage(
        &fixture.prepared(),
        &fixture.snapshot,
        &fixture.objects,
        &space.path("plain"),
        "plain",
    )
    .unwrap();
    assert!(!plain.job_dir().join(".blender-runtime").exists());
    let native = stage(
        &fixture.prepared_with_worker(BLENDER_JOB_LOOP_VERSION),
        &fixture.snapshot,
        &fixture.objects,
        &space.path("native"),
        "native",
    )
    .unwrap();
    let scratch = native.job_dir().join(".blender-runtime");
    assert!(fs::read_dir(&scratch).unwrap().next().is_none());
    assert_eq!(mode(&scratch), 0o700);
    assert_eq!(mode(native.job_dir()), 0o555);
    assert_eq!(mode(&native.job_dir().join("ops/piece.py")), 0o444);
    let mut poisoned = Fixture::new("assets/demo");
    let name = ".blender-runtime/seed.py";
    poisoned.declaration.units[0].code.push(name.into());
    poisoned
        .snapshot
        .insert(name.into(), SnapshotEntry::File(b"# preseeded".to_vec()));
    assert!(
        stage(
            &poisoned.prepared_with_worker(BLENDER_JOB_LOOP_VERSION),
            &poisoned.snapshot,
            &poisoned.objects,
            &space.path("poisoned"),
            "poisoned"
        )
        .is_err()
    );
}

#[test]
fn stages_exact_read_only_view_with_selected_bytes_items_and_no_locators() {
    let space = Workspace::new();
    let fixture = Fixture::new("assets/demo");
    let prepared = fixture.prepared();
    let job = stage(
        &prepared,
        &fixture.snapshot,
        &fixture.objects,
        &space.path("job"),
        "job-1",
    )
    .unwrap();
    let root = job.job_dir();
    assert_eq!(
        files_below(root),
        [
            "in",
            "in/mesh",
            "in/mesh/bin",
            "in/mesh/bin/tool.sh",
            "in/mesh/mesh.bin",
            "in/shape.json",
            "ops",
            "ops/helper.py",
            "ops/piece.py",
            "output"
        ]
    );
    // The selected view, not the whole source file; the optional absent input creates nothing.
    assert_eq!(fs::read(root.join("in/shape.json")).unwrap(), b"[1,2,3]");
    assert!(!root.join("in/extra.txt").exists());
    assert_eq!(
        fs::read(root.join("ops/piece.py")).unwrap(),
        PIECE.as_bytes()
    );
    for (path, expected) in [
        ("ops/piece.py", 0o444),
        ("in/shape.json", 0o444),
        ("in/mesh/mesh.bin", 0o444),
        ("in/mesh/bin/tool.sh", 0o555),
        ("in/mesh", 0o555),
        ("ops", 0o555),
        ("", 0o555),
        ("output", 0o755),
    ] {
        assert_eq!(mode(&root.join(path)), expected, "{path}");
    }
    assert!(fs::write(root.join("in/shape.json"), b"changed").is_err());
    assert!(fs::write(root.join("in/new.txt"), b"new").is_err());
    let request = job.request();
    assert_eq!(request.job_id, "job-1");
    assert_eq!(Path::new(&request.job_dir), root);
    assert!(
        request
            .outputs
            .iter()
            .all(|output| output.install_path.is_none())
    );
    let wire = serde_json::to_string(request).unwrap();
    for locator in ["assets/demo", "Content/Demo", "/Game/Demo", "demo.mesh"] {
        assert!(!wire.contains(locator), "{locator} leaked into {wire}");
    }
    let paths: Vec<_> = request
        .inputs
        .iter()
        .map(|input| (input.name.as_str(), input.path.as_str()))
        .collect();
    assert_eq!(
        paths,
        [
            ("extra", "in/extra.txt"),
            ("mesh", "in/mesh"),
            ("shape", "in/shape.json")
        ]
    );
}

#[test]
fn staging_refuses_code_changed_after_keying_and_leaves_no_folder() {
    let space = Workspace::new();
    let mut fixture = Fixture::new("assets");
    let prepared = fixture.prepared();
    fixture.snapshot.insert(
        "ops/helper.py".into(),
        SnapshotEntry::File(b"def render(*parts):\n    return 'edited'\n".to_vec()),
    );
    let error = stage(
        &prepared,
        &fixture.snapshot,
        &fixture.objects,
        &space.path("job"),
        "job-1",
    )
    .unwrap_err();
    assert!(matches!(error, StageError::Staging(_)), "{error:?}");
    let error = String::from(error);
    assert!(error.contains("changed after keying"), "{error}");
    assert!(!space.path("job").exists());
    fixture
        .snapshot
        .insert("ops/helper.py".into(), SnapshotEntry::Directory);
    assert!(
        stage(
            &prepared,
            &fixture.snapshot,
            &fixture.objects,
            &space.path("job"),
            "job-1"
        )
        .is_err()
    );
    assert!(!space.path("job").exists());
}

#[test]
fn object_source_refusals_reach_the_controller_typed_and_leave_no_folder() {
    let space = Workspace::new();
    let fixture = Fixture::new("assets");
    let prepared = fixture.prepared();
    let mesh_digest = sha256(b"mesh bytes");
    for (source, kind) in [
        (
            &MemoryObjects::default() as &dyn ObjectSource,
            SourceErrorKind::Unavailable,
        ),
        (
            &ChangedObjects as &dyn ObjectSource,
            SourceErrorKind::Changed,
        ),
    ] {
        let error = stage(
            &prepared,
            &fixture.snapshot,
            source,
            &space.path("job"),
            "job-1",
        )
        .unwrap_err();
        let StageError::Source(refusal) = &error else {
            panic!("expected a typed source refusal, got {error:?}")
        };
        assert_eq!(refusal.kind, kind);
        // Staging asks for a recorded member's digest; which one comes first is staging's order.
        let recorded = [mesh_digest.clone(), sha256(b"#!/bin/sh\n")];
        assert!(
            recorded.contains(&refusal.digest.as_hex().to_string()),
            "{refusal:?}"
        );
        let text = String::from(error.clone());
        assert_eq!(text, error.to_string());
        assert!(
            text.starts_with(&format!("cannot clone object {}: ", refusal.digest)),
            "{text}"
        );
        assert!(!space.path("job").exists());
    }
}

#[test]
fn pinned_objects_report_a_missing_object_as_io_with_the_same_text() {
    use atelier_build_v2::leases::ProcessIdentity;
    use atelier_build_v2::results::ResultStore;
    use atelier_build_v2::store::ObjectStore;
    let space = Workspace::new();
    let fixture = Fixture::new("assets");
    let prepared = fixture.prepared();
    let objects = ObjectStore::open(space.path("store")).unwrap();
    let identity = ProcessIdentity {
        pid: std::process::id(),
        boot: "boot".into(),
        started: "start".into(),
    };
    let provenance = Provenance {
        checkout: "test".into(),
        branch: "test".into(),
        commit: "test".into(),
        dirty: false,
        built_at: "now".into(),
    };
    let results = ResultStore::open(space.path("store")).unwrap();
    let pin = results
        .begin(
            &prepared,
            provenance,
            identity,
            vec![],
            BTreeSet::from([sha256(b"producer")]),
        )
        .unwrap();
    let digest = ObjectDigest::from_hex(&sha256(b"never stored")).unwrap();
    let error = PinnedObjects::new(&objects, &pin)
        .clone_object(&digest, &space.path("clone.bin"))
        .unwrap_err();
    assert_eq!(error.kind, SourceErrorKind::Io);
    assert_eq!(error.digest, digest);
    // The text is the one staging reported before the typed error existed.
    assert!(
        error
            .to_string()
            .starts_with(&format!("cannot clone object {digest}: ")),
        "{error}"
    );
    assert!(!space.path("clone.bin").exists());
}

#[test]
fn staging_refuses_incomplete_items_reused_folders_and_relative_roots() {
    let space = Workspace::new();
    let fixture = Fixture::new("assets");
    let prepared = fixture.prepared();
    let error = stage(
        &prepared,
        &fixture.snapshot,
        &MemoryObjects::default(),
        &space.path("job"),
        "job-1",
    )
    .unwrap_err()
    .to_string();
    assert!(error.contains("not in the store"), "{error}");
    assert!(!space.path("job").exists());
    let mut short = MemoryObjects::default();
    for (_, bytes) in &fixture.objects.0 {
        short.0.insert(sha256(bytes), bytes[..4].to_vec());
    }
    let error = stage(
        &prepared,
        &fixture.snapshot,
        &short,
        &space.path("job"),
        "job-1",
    )
    .unwrap_err()
    .to_string();
    assert!(error.contains("recorded 10-byte file"), "{error}");
    fs::create_dir(space.path("used")).unwrap();
    fs::write(space.path("used/stale"), b"stale").unwrap();
    assert!(
        stage(
            &prepared,
            &fixture.snapshot,
            &fixture.objects,
            &space.path("used"),
            "job-1"
        )
        .is_err()
    );
    assert_eq!(fs::read(space.path("used/stale")).unwrap(), b"stale");
    assert!(
        stage(
            &prepared,
            &fixture.snapshot,
            &fixture.objects,
            Path::new("relative/job"),
            "job-1"
        )
        .is_err()
    );
}

#[test]
fn collected_outputs_are_every_actual_file_and_fixed_mapping_refuses_others() {
    let space = Workspace::new();
    let fixture = Fixture::new("assets");
    let prepared = fixture.prepared();
    let job = stage(
        &prepared,
        &fixture.snapshot,
        &fixture.objects,
        &space.path("job"),
        "job-1",
    )
    .unwrap();
    let output = job.output_dir();
    fs::write(output.join("piece.txt"), b"piece").unwrap();
    let actual = collect_outputs(&job, &["piece.txt".into()]).unwrap();
    let found: Vec<_> = actual
        .iter()
        .map(|file| (file.path.as_str(), file.source.clone()))
        .collect();
    assert_eq!(found, [("piece.txt", output.join("piece.txt"))]);
    assert_eq!(
        fixed_sources(&prepared, &actual).unwrap(),
        BTreeMap::from([(
            ("piece".to_string(), "piece.txt".to_string()),
            output.join("piece.txt")
        )])
    );
    assert!(collect_outputs(&job, &[]).is_err());
    assert!(collect_outputs(&job, &["piece.txt".into(), "piece.txt".into()]).is_err());
    assert!(collect_outputs(&job, &["piece.txt".into(), "ghost.txt".into()]).is_err());
    // Every actual file is reported, declared or not, including files under a would-be group root.
    fs::create_dir_all(output.join("pieces/a")).unwrap();
    fs::write(output.join("pieces/a/member.glb"), b"member").unwrap();
    fs::write(output.join("stray.txt"), b"stray").unwrap();
    let all = [
        "pieces/a/member.glb".to_string(),
        "piece.txt".into(),
        "stray.txt".into(),
    ];
    let actual = collect_outputs(&job, &all).unwrap();
    let paths: Vec<_> = actual.iter().map(|file| file.path.as_str()).collect();
    assert_eq!(paths, ["piece.txt", "pieces/a/member.glb", "stray.txt"]);
    let error = fixed_sources(&prepared, &actual).unwrap_err();
    assert!(error.contains("not declared"), "{error}");
    std::os::unix::fs::symlink("/etc/hosts", output.join("pieces/link")).unwrap();
    let mut with_link = all.to_vec();
    with_link.push("pieces/link".into());
    let error = collect_outputs(&job, &with_link).unwrap_err();
    assert!(error.contains("not a regular file"), "{error}");
}

fn python() -> PathBuf {
    std::env::split_paths(&std::env::var_os("PATH").unwrap())
        .map(|directory| directory.join("python3"))
        .find(|path| path.is_file())
        .expect("python3 on PATH runs the job loop")
}

/// The version an unsandboxed loop announces; only test controllers ever expect it.
const UNSANDBOXED_TEST_VERSION: &str = "atelier-python-job-1+unsandboxed-test";

/// The production loop (always sandboxed), or the test-only unsandboxed entry for portable tests.
fn job_loop(sandboxed: bool) -> WorkerCommand {
    let script = Path::new(env!("CARGO_MANIFEST_DIR")).join(if sandboxed {
        "../studio/atelier/build_v2/python_worker.py"
    } else {
        "tests/fixtures/unsandboxed_job_loop.py"
    });
    WorkerCommand::python_job_loop(python(), script.canonicalize().unwrap()).unwrap()
}

fn loop_version(sandboxed: bool) -> &'static str {
    if sandboxed {
        PYTHON_JOB_LOOP_VERSION
    } else {
        UNSANDBOXED_TEST_VERSION
    }
}

/// Stage `fixture` into `space/<name>` and run it with the real Python job loop.
fn run(space: &Workspace, fixture: &Fixture, name: &str, sandboxed: bool) -> (JobOutcome, PathBuf) {
    let prepared = fixture.prepared();
    let job = stage(
        &prepared,
        &fixture.snapshot,
        &fixture.objects,
        &space.path(name),
        name,
    )
    .unwrap();
    let outcome = run_staged(
        &DirectChild,
        &job_loop(sandboxed),
        loop_version(sandboxed),
        &job,
    )
    .unwrap();
    (outcome, job.output_dir())
}

#[test]
fn an_unsandboxed_loop_never_passes_a_production_keyed_handshake() {
    let space = Workspace::new();
    let fixture = Fixture::new("assets");
    let prepared = fixture.prepared();
    // The unit is keyed with the production worker version; the unsandboxed entry announces another.
    assert_eq!(
        prepared.ingredients().worker_version,
        PYTHON_JOB_LOOP_VERSION
    );
    let job = stage(
        &prepared,
        &fixture.snapshot,
        &fixture.objects,
        &space.path("job"),
        "job-1",
    )
    .unwrap();
    let error = run_staged(
        &DirectChild,
        &job_loop(false),
        PYTHON_JOB_LOOP_VERSION,
        &job,
    )
    .unwrap_err();
    assert!(error.contains(UNSANDBOXED_TEST_VERSION), "{error}");
    assert!(fs::read_dir(job.output_dir()).unwrap().next().is_none());
}

fn completed(outcome: JobOutcome) -> BTreeSet<String> {
    match outcome {
        JobOutcome::Completed(actual) => actual.into_iter().map(|file| file.path).collect(),
        JobOutcome::Failed(failure) => panic!("job failed: {failure:?}"),
    }
}

fn piece() -> BTreeSet<String> {
    BTreeSet::from(["piece.txt".to_string()])
}

fn same_bytes_under_other_ids_folders_and_source_locations(sandboxed: bool) {
    let space = Workspace::new();
    let (first, first_output) = run(&space, &Fixture::new("assets/demo"), "job-a", sandboxed);
    let (second, second_output) = run(&space, &Fixture::new("elsewhere/data"), "job-b", sandboxed);
    assert_eq!(completed(first), piece());
    assert_eq!(completed(second), piece());
    let bytes = fs::read_to_string(first_output.join("piece.txt")).unwrap();
    assert_eq!(
        bytes,
        fs::read_to_string(second_output.join("piece.txt")).unwrap()
    );
    assert!(
        bytes.starts_with(
            "('[1,2,3]', 'mesh bytes', ['bin', 'bin/tool.sh', 'mesh.bin'], True, False, None, {"
        ),
        "{bytes}"
    );
    for leaked in ["job-a", "assets", space.0.to_str().unwrap()] {
        assert!(!bytes.contains(leaked), "{leaked} in {bytes}");
    }
}

#[test]
fn python_job_gives_the_same_bytes_under_other_ids_folders_and_source_locations() {
    same_bytes_under_other_ids_folders_and_source_locations(false);
}

#[test]
fn python_job_output_changes_with_only_seed_or_params() {
    let space = Workspace::new();
    let mut texts = BTreeSet::new();
    for (index, params) in [
        serde_json::json!({"seed": 7, "scale": 2}),
        serde_json::json!({"seed": 8, "scale": 2}),
        serde_json::json!({"seed": 7, "scale": 3}),
    ]
    .into_iter()
    .enumerate()
    {
        let mut fixture = Fixture::new("assets");
        fixture.params(params);
        let (outcome, output) = run(&space, &fixture, &format!("job-{index}"), false);
        assert_eq!(completed(outcome), piece());
        texts.insert(fs::read_to_string(output.join("piece.txt")).unwrap());
    }
    assert_eq!(texts.len(), 3);
}

#[test]
fn python_job_failures_yield_no_outputs_and_undeclared_files_are_reported() {
    let space = Workspace::new();
    for (index, (attempt, kind)) in [
        ("raise ValueError('bad mesh')", FailureKind::Job),
        ("os.mkfifo('output/pipe')", FailureKind::Job),
        (
            "os.symlink('/etc/hosts', 'output/link')",
            FailureKind::Dependency,
        ),
        (
            "os.path.exists('/nonexistent-build-v2-probe')",
            FailureKind::Dependency,
        ),
        ("os.urandom(1)", FailureKind::Dependency),
    ]
    .into_iter()
    .enumerate()
    {
        let mut fixture = Fixture::new("assets");
        fixture.params(serde_json::json!({"seed": 7, "scale": 2, "attempts": [attempt]}));
        match run(&space, &fixture, &format!("job-{index}"), false).0 {
            JobOutcome::Failed(failure) => assert_eq!(failure.kind, kind, "{attempt}: {failure:?}"),
            JobOutcome::Completed(sources) => panic!("{attempt} completed with {sources:?}"),
        }
    }
    let mut optional = Fixture::new("assets");
    optional.params(serde_json::json!({"seed": 7, "scale": 2, "notes": true}));
    assert_eq!(completed(run(&space, &optional, "notes", false).0).len(), 2);
    // An undeclared file is reported, not hidden; the fixed-result mapping then refuses it.
    let mut stray = Fixture::new("assets");
    stray.params(serde_json::json!({"seed": 7, "scale": 2,
        "attempts": ["open('output/stray.txt', 'w').write('x')"]}));
    let (outcome, _) = run(&space, &stray, "stray", false);
    let JobOutcome::Completed(actual) = outcome else {
        panic!("the stray job did not complete")
    };
    let paths: Vec<_> = actual.iter().map(|file| file.path.as_str()).collect();
    assert_eq!(paths, ["piece.txt", "stray.txt"]);
    assert!(fixed_sources(&stray.prepared(), &actual).is_err());
}

#[cfg(target_os = "macos")]
mod sandboxed {
    use super::*;
    use atelier_build_v2::leases::ProcessIdentity;
    use atelier_build_v2::results::ResultStore;
    use atelier_build_v2::store::ObjectStore;

    #[test]
    fn sandboxed_python_job_gives_the_same_bytes_under_other_ids_folders_and_source_locations() {
        same_bytes_under_other_ids_folders_and_source_locations(true);
    }

    #[test]
    fn sandboxed_python_job_fails_on_undeclared_reads_checks_listings_and_network() {
        let space = Workspace::new();
        fs::write(space.path("secret.txt"), b"secret").unwrap();
        let secret = space.path("secret.txt");
        let missing = space.path("missing.txt");
        for (index, attempt) in [
            format!("open({secret:?}).read()"),
            format!("os.path.exists({missing:?})"),
            format!("import posix; posix.stat({secret:?})"),
            format!("os.listdir({:?})", space.0),
            "import socket; socket.socket().connect(('127.0.0.1', 9))".to_string(),
            // A missing undeclared import path: hermetic, and caught by the guard, not the kernel.
            format!(
                "import sys; sys.path.append({:?}); __import__('not_declared_module')",
                space.path("no-such-lib")
            ),
        ]
        .into_iter()
        .enumerate()
        {
            let mut fixture = Fixture::new("assets");
            fixture.params(serde_json::json!({"seed": 7, "scale": 2, "attempts": [attempt]}));
            match run(&space, &fixture, &format!("job-{index}"), true).0 {
                JobOutcome::Failed(failure) => {
                    assert_eq!(
                        failure.kind,
                        FailureKind::Dependency,
                        "{attempt}: {failure:?}"
                    )
                }
                JobOutcome::Completed(sources) => panic!("{attempt} completed with {sources:?}"),
            }
        }
    }

    #[test]
    fn pinned_item_clones_run_sandboxed_and_stage_into_the_result_store() {
        let space = Workspace::new();
        let mut fixture = Fixture::new("assets");
        let objects = ObjectStore::open(space.path("store")).unwrap();
        for item in fixture.produced.values_mut() {
            for file in &mut item.files {
                let bytes = &fixture.objects.0[&file.digest];
                let source = space.path("source.bin");
                fs::write(&source, bytes).unwrap();
                fs::set_permissions(&source, fs::Permissions::from_mode(file.mode)).unwrap();
                let published = objects.publish(objects.prepare(&source).unwrap()).unwrap();
                assert_eq!(published.digest.as_hex(), file.digest);
                fs::remove_file(source).unwrap();
            }
        }
        let prepared = fixture.prepared();
        let identity = ProcessIdentity {
            pid: std::process::id(),
            boot: "boot".into(),
            started: "start".into(),
        };
        let provenance = Provenance {
            checkout: "test".into(),
            branch: "test".into(),
            commit: "test".into(),
            dirty: false,
            built_at: "now".into(),
        };
        let results = ResultStore::open(space.path("store")).unwrap();
        let pin = results
            .begin(
                &prepared,
                provenance,
                identity,
                vec![],
                BTreeSet::from([sha256(b"producer")]),
            )
            .unwrap();
        let job = stage(
            &prepared,
            &fixture.snapshot,
            &PinnedObjects::new(&objects, &pin),
            &space.path("job"),
            "job-1",
        )
        .unwrap();
        let mesh = job.job_dir().join("in/mesh");
        assert_eq!(fs::read(mesh.join("mesh.bin")).unwrap(), b"mesh bytes");
        assert_eq!(mode(&mesh.join("mesh.bin")), 0o444);
        assert_eq!(mode(&mesh.join("bin/tool.sh")), 0o555);
        let outcome =
            run_staged(&DirectChild, &job_loop(true), PYTHON_JOB_LOOP_VERSION, &job).unwrap();
        let JobOutcome::Completed(actual) = outcome else {
            panic!("the sandboxed job did not complete")
        };
        // The complete actual list is exactly what A4b's stage_groups consumes.
        let staged = pin
            .stage_groups(actual, |_| Ok(()), |_, _, _| Ok(()))
            .unwrap();
        let files: Vec<_> = staged
            .envelope()
            .result
            .outputs
            .iter()
            .flat_map(|item| item.files.iter().map(|file| file.path.as_str()))
            .collect();
        assert_eq!(files, ["piece.txt"]);
    }
}
