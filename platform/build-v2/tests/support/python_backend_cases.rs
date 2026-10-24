//! T1a: real sandboxed Python/filesystem work with explicitly scripted admission evidence.
use super::*;
use crate::failure_policy::Limits;
use crate::graph::{BuildGraph, Target};
use crate::guard_adapter::GuardedLauncher;
use crate::install::{InstallPolicy, ProjectNamespace};
use crate::keys::SourceVersions;
use crate::py_data::{ContentSlotSpec, PyDataSpec, py_data_validator_identity};
use crate::python_executor::{PythonExecution, PythonExecutor};
use crate::python_sources::capture_sources;
use crate::python_worker::{PYTHON_WORKER_FILES, PythonWorkerBundle};
use crate::scheduler::{self, Control, Runtime, State};
use crate::schema::*;
use crate::source_hashes::SourceHashCache;
use crate::validate::*;
use std::fs;
use std::io::{Read, Write};
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;
static NEXT: AtomicU64 = AtomicU64::new(0);

struct Space(PathBuf);
impl Space {
    fn new() -> Self {
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "atelier-v2-static-python-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        for name in ["checkout", "roots"] {
            fs::create_dir(root.join(name)).unwrap();
        }
        Self(root)
    }
    fn path(&self, name: &str) -> PathBuf {
        self.0.join(name)
    }
    fn set(&self, name: &str, bytes: &[u8]) {
        let path = self.path(&format!("checkout/{name}"));
        if fs::read(&path).is_ok_and(|old| old == bytes) {
            return;
        }
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, bytes).unwrap();
    }
}
impl Drop for Space {
    fn drop(&mut self) {
        fn writable(path: &Path) {
            if !fs::symlink_metadata(path).unwrap().is_dir() {
                return;
            }
            fs::set_permissions(path, fs::Permissions::from_mode(0o700)).unwrap();
            for child in fs::read_dir(path).unwrap() {
                writable(&child.unwrap().path());
            }
        }
        writable(&self.0);
        fs::remove_dir_all(&self.0).unwrap();
    }
}

fn policy() -> InstallPolicy {
    InstallPolicy {
        project: ProjectNamespace::new("pythonfixture").unwrap(),
        allowed_install_roots: vec!["Game".into()],
    }
}

fn implementation() -> PythonWorkerBundle {
    let directory = Path::new(env!("CARGO_MANIFEST_DIR")).join("../studio/atelier/build_v2");
    let captured = capture_sources(&directory, PYTHON_WORKER_FILES).unwrap();
    PythonWorkerBundle::from_snapshot(&captured.snapshot).unwrap()
}

fn interpreter() -> PathBuf {
    std::env::split_paths(&std::env::var_os("PATH").unwrap())
        .map(|path| path.join("python3"))
        .find(|path| {
            path.metadata().is_ok_and(|metadata| {
                metadata.is_file() && metadata.permissions().mode() & 0o111 != 0
            })
        })
        .expect("hosted fixture needs python3")
}

fn owner() -> ProcessIdentity {
    ProcessIdentity {
        pid: std::process::id(),
        boot: "fixture-boot".into(),
        started: "fixture-controller".into(),
    }
}
fn provenance() -> Provenance {
    Provenance {
        checkout: "fixture".into(),
        branch: "fixture".into(),
        commit: "fixture".into(),
        dirty: false,
        built_at: "fixture".into(),
    }
}

const A: &str = "def run(c):\n    c.output('a.bin').write_bytes(c.inputs['raw'].read_bytes())\n";
const B: &str =
    "def run(c):\n    c.output('b.bin').write_bytes((c.inputs['a'] / 'a.bin').read_bytes())\n";

fn unit(id: &str, inputs: Vec<Input>) -> Unit {
    Unit {
        id: id.into(),
        op: Op {
            kind: "py_data".into(),
            version: "1".into(),
        },
        script: format!("ops/{id}.py"),
        code: vec![format!("ops/{id}.py")],
        inputs,
        params: BTreeMap::from([("seed".into(), serde_json::json!(0))]),
        outputs: vec![Item {
            id: "out".into(),
            logical_path: format!("/Game/{id}"),
            class: "Data".into(),
            destination: Destination::Checkout,
            files: vec![OutputFile {
                path: format!("{id}.bin"),
                install_path: Some(format!("Game/{id}.bin")),
                required: true,
            }],
        }],
        output_groups: vec![],
        conditional: None,
    }
}

fn chain(selector: Option<&str>) -> Declaration {
    Declaration {
        schema_version: SCHEMA_VERSION,
        cache_version: "python-fixture-1".into(),
        units: vec![
            unit(
                "a",
                vec![Input::Content {
                    name: "raw".into(),
                    source: ContentSource::File {
                        path: "data/raw".into(),
                        selector: selector.map(Into::into),
                        optional: false,
                    },
                    whole: None,
                    conditional: None,
                }],
            ),
            unit(
                "b",
                vec![Input::Content {
                    name: "a".into(),
                    source: ContentSource::Item {
                        unit: "a".into(),
                        item: "out".into(),
                    },
                    whole: None,
                    conditional: None,
                }],
            ),
        ],
    }
}

const MIXED_A: &str = "def run(c):\n    data = c.inputs['raw'].read_bytes()\n    c.output('a.bin').write_bytes(data)\n    c.output('extra.bin').write_bytes(data + b'/extra')\n";
const MIXED_B: &str = "def run(c):\n    c.output('b.bin').write_bytes((c.inputs['a'] / 'extra.bin').read_bytes() + b'/final')\n";
fn mixed_chain() -> Declaration {
    let mut declaration = chain(None);
    declaration.units[0].outputs.push(Item {
        id: "extra".into(),
        logical_path: "/Data/extra".into(),
        class: "Data".into(),
        destination: Destination::Store,
        files: vec![OutputFile {
            path: "extra.bin".into(),
            install_path: None,
            required: true,
        }],
    });
    let Input::Content {
        source: ContentSource::Item { item, .. },
        ..
    } = &mut declaration.units[1].inputs[0]
    else {
        unreachable!()
    };
    *item = "extra".into();
    declaration
}

fn graph(space: &Space, declaration: Declaration) -> (BuildGraph, SourceSnapshot, SourceVersions) {
    let mut names = BTreeSet::new();
    for unit in &declaration.units {
        names.extend(unit.code.iter().map(String::as_str));
        for input in &unit.inputs {
            if let Input::Content {
                source: ContentSource::File { path, .. },
                ..
            } = input
            {
                names.insert(path.as_str());
            }
        }
    }
    let captured = capture_sources(&space.path("checkout"), names).unwrap();
    let spec = PyDataSpec::new()
        .with_content_slot("raw", ContentSlotSpec::bounded(false))
        .with_content_slot("a", ContentSlotSpec::bounded(false));
    let registry = BTreeMap::from([(("py_data".into(), "1".into()), spec.build().unwrap())]);
    let graph = BuildGraph::validate(declaration, &registry, &["Game".into()]).unwrap();
    (graph, captured.snapshot, captured.versions)
}

#[derive(Clone, Copy)]
enum StoreMode {
    Ready,
    ReadyWithMissingBridge,
    Unavailable,
    UnavailableAndChangeCurrent,
    UnavailableAndChangeLaterCurrent,
}
struct Running;
impl Control for Running {
    fn cancelled(&self) -> bool {
        false
    }
}

struct Run {
    report: scheduler::Report,
    summary: crate::explain::BuildSummary,
    io: PythonIo,
    items: BTreeMap<(String, String), StoredItem>,
    fresh_bytes: BTreeMap<String, Vec<u8>>,
    rooted_units: Vec<(String, String)>,
}

fn build(space: &Space, declaration: Declaration, roots: &[&str], mode: StoreMode) -> Run {
    let flags: Vec<_> = roots
        .iter()
        .map(|id| (*id, BTreeSet::from([Demand::Checkout])))
        .collect();
    build_flags(space, declaration, &flags, mode)
}

fn build_flags(
    space: &Space,
    declaration: Declaration,
    roots: &[(&str, FinalDemands)],
    mode: StoreMode,
) -> Run {
    let (graph, snapshot, versions) = graph(space, declaration);
    let bundle = implementation();
    let worker = bundle.identity();
    let runtimes = graph
        .declaration()
        .units
        .iter()
        .map(|unit| {
            let staged_inputs = unit
                .inputs
                .iter()
                .map(|input| {
                    let name = match input {
                        Input::Content { name, .. } | Input::Reference { name, .. } => name,
                    };
                    (name.clone(), format!("inputs/{name}"))
                })
                .collect();
            (
                unit.id.clone(),
                Runtime {
                    worker: worker.clone(),
                    validator: py_data_validator_identity(),
                    staged_inputs,
                    profile: "scripted-sandbox-fixture".into(),
                },
            )
        })
        .collect();
    let targets: Vec<_> = roots
        .iter()
        .map(|(id, _)| Target::Unit((*id).into()))
        .collect();
    let demands = roots
        .iter()
        .map(|(id, flags)| ((*id).into(), flags.clone()))
        .collect();
    run_graph(
        space, &graph, &snapshot, &versions, &runtimes, &targets, &demands, bundle, mode,
    )
}

fn run_graph(
    space: &Space,
    graph: &BuildGraph,
    snapshot: &SourceSnapshot,
    versions: &SourceVersions,
    runtimes: &BTreeMap<String, Runtime>,
    targets: &[Target],
    demands: &BTreeMap<String, FinalDemands>,
    bundle: PythonWorkerBundle,
    mode: StoreMode,
) -> Run {
    let reader = ReceiptReader::open(space.path("checkout"), policy()).unwrap();
    let guard = reader.locks().try_build_exclusive().unwrap();
    let ownership = OwnershipSnapshot::from_projects([(policy().project, graph)]).unwrap();
    let request =
        scheduler::Request::select(graph, targets, snapshot, versions, runtimes, demands).unwrap();
    let rooted_units = RefCell::new(Vec::new());
    let mut backend = PythonBackend::new(
        graph,
        request.selected(),
        snapshot,
        &reader,
        &guard,
        &ownership,
        owner(),
        provenance(),
        || {
            if matches!(mode, StoreMode::UnavailableAndChangeCurrent) {
                fs::write(
                    space.path("checkout/Game/a.bin"),
                    b"changed after identity observation",
                )
                .unwrap();
            }
            if matches!(mode, StoreMode::UnavailableAndChangeLaterCurrent) {
                fs::write(space.path("checkout/Game/c.bin"), b"changed later origin").unwrap();
            }
            if !matches!(mode, StoreMode::Ready | StoreMode::ReadyWithMissingBridge) {
                return Err(InstallError::Cache(ResultError::Io(std::io::Error::new(
                    std::io::ErrorKind::PermissionDenied,
                    "fixture cache deliberately unavailable",
                ))));
            }
            let results = ResultStore::open(space.path("cache")).map_err(InstallError::Cache)?;
            let checkout =
                CheckoutInstaller::open(space.path("checkout"), space.path("cache"), policy())?;
            Ok(CacheAccess { results, checkout })
        },
        |current_unit, result| {
            assert!(graph.unit(current_unit).is_some());
            rooted_units
                .borrow_mut()
                .push((current_unit.into(), result.result.unit.clone()));
            let path = space
                .path("roots")
                .join(format!("{}.json", result.result.key));
            if let Ok(bytes) = fs::read(&path) {
                let old: ResultEnvelope =
                    serde_json::from_slice(&bytes).map_err(|error| error.to_string())?;
                if old.result.key != result.result.key
                    || old.result.ingredients != result.result.ingredients
                    || old.result.outputs != result.result.outputs
                    || old.result.output_groups != result.result.output_groups
                {
                    return Err("fixture root semantic conflict".into());
                }
                return Ok(());
            }
            let mut file = fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(path)
                .map_err(|error| error.to_string())?;
            file.write_all(&serde_json::to_vec(result).unwrap())
                .map_err(|error| error.to_string())?;
            file.sync_all().map_err(|error| error.to_string())?;
            fs::File::open(space.path("roots"))
                .unwrap()
                .sync_all()
                .map_err(|error| error.to_string())
        },
    );
    let bridge = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/fake_bridge.py");
    let launcher = GuardedLauncher {
        bridge: if matches!(mode, StoreMode::ReadyWithMissingBridge) {
            vec![space.path("missing-admission-bridge").into_os_string()]
        } else {
            vec![
                interpreter().into_os_string(),
                bridge.into_os_string(),
                "normal".into(),
            ]
        },
    };
    let config = PythonExecution {
        interpreter: interpreter(),
        bundle,
        profile: "scripted-sandbox-fixture".into(),
        memory_gib: 1,
        limits: Limits {
            job: Duration::from_secs(5),
            cleanup: Duration::from_secs(2),
            overall: Some(Duration::from_secs(10)),
        },
    };
    let mut executor = PythonExecutor::scripted_fixture(launcher, config);
    let recorder = crate::explain::Recorder::default();
    let report = scheduler::run(
        request,
        &mut recorder.backend(&mut backend),
        &mut recorder.executor(&mut executor),
        &Running,
        &mut SourceHashCache::default(),
    )
    .unwrap();
    if report.states.values().any(|state| {
        matches!(
            state,
            State::Failed(_) | State::InputRefused(_) | State::Cancelled
        )
    }) {
        eprintln!(
            "static Python states: {:?}; fatal: {:?}; unsatisfied: {:?}; I/O: {:?}",
            report.states,
            report.fatal,
            report.unsatisfied,
            backend.io()
        );
    }
    let mut items = BTreeMap::new();
    let mut fresh_bytes = BTreeMap::new();
    // Observation only: no source capability is reconstructed from this archive. Cached/recorded
    // payloads are not read on hits; the independent harness may remember prior observed bytes.
    for (unit, origin) in &backend.origins {
        let (stored, frozen) = match origin {
            Origin::Current(observation) => (observation.items(), None),
            Origin::Recorded { record, .. } => (record.result().result.outputs.as_slice(), None),
            Origin::Cached { envelope, .. } => (envelope.result.outputs.as_slice(), None),
            Origin::Local(completion) => (
                completion.result().result.outputs.as_slice(),
                Some(completion),
            ),
            Origin::Installed(plan) => (
                plan.result().result.outputs.as_slice(),
                plan.local_completion(),
            ),
        };
        for item in stored {
            items.insert((unit.clone(), item.item.id.clone()), item.clone());
        }
        if let Some(frozen) = frozen {
            for object in &frozen.objects {
                let mut bytes = vec![];
                object.reader().unwrap().read_to_end(&mut bytes).unwrap();
                fresh_bytes.insert(object.digest().as_hex().into(), bytes);
            }
        }
    }
    let io = backend.finish().unwrap();
    let summary = recorder
        .summarize(&report, &BTreeMap::new(), Some(&io.launches_by_unit))
        .unwrap();
    assert_eq!(
        summary.counts.cached + summary.counts.not_cached,
        io.publications
    );
    assert_eq!(summary.counts.installed_units, io.installs);
    assert_eq!(summary.counts.receipt_writes, io.receipt_writes);
    if let Some(launches) = summary.counts.launched_attempts {
        assert_eq!(launches, io.launches);
    }
    Run {
        report,
        summary,
        io,
        items,
        fresh_bytes,
        rooted_units: rooted_units.into_inner(),
    }
}

type ObservedFiles = BTreeMap<PathBuf, (u64, u64, u64, u32, (i64, i64), (i64, i64), Vec<u8>)>;
fn observations(root: &Path) -> ObservedFiles {
    fn visit(root: &Path, out: &mut ObservedFiles) {
        for entry in fs::read_dir(root).unwrap() {
            let path = entry.unwrap().path();
            let metadata = fs::symlink_metadata(&path).unwrap();
            if metadata.is_dir() {
                visit(&path, out);
            } else if metadata.is_file() {
                out.insert(
                    path.clone(),
                    (
                        metadata.dev(),
                        metadata.ino(),
                        metadata.len(),
                        metadata.mode(),
                        (metadata.mtime(), metadata.mtime_nsec()),
                        (metadata.ctime(), metadata.ctime_nsec()),
                        fs::read(path).unwrap(),
                    ),
                );
            }
        }
    }
    let mut output = BTreeMap::new();
    visit(root, &mut output);
    output
}

#[test]
fn failed_submission_keeps_abort_reason_without_claiming_user_cancellation() {
    let space = Space::new();
    space.set("ops/a.py", A.as_bytes());
    space.set("data/raw", b"not executed");
    let mut declaration = chain(None);
    declaration.units.truncate(1);
    let result = build(
        &space,
        declaration,
        &["a"],
        StoreMode::ReadyWithMissingBridge,
    );
    assert!(result.report.fatal.is_none());
    assert!(
        matches!(&result.report.states["a"], State::Failed(reason)
        if reason.starts_with("launch failed:") && reason.len() > "launch failed:".len()),
        "{:?}",
        result.report.states
    );
    assert_eq!(result.io.launches, 0);
    assert_eq!(result.summary.counts.launched_attempts, Some(0));
    assert_eq!(result.summary.counts.worker_completed, 0);
    assert_eq!(result.io.worker_files_written, 3);
    assert_eq!(result.io.publications, 0);
    assert_eq!(result.io.installs, 0);
    assert!(!space.path("checkout/Game/a.bin").exists());
    assert!(result.rooted_units.is_empty());
}

#[test]
fn actual_python_first_build_and_current_noop_have_real_zero_launch_and_write_evidence() {
    let space = Space::new();
    space.set("ops/a.py", A.as_bytes());
    space.set("ops/b.py", B.as_bytes());
    space.set("data/raw", b"first");
    let first = build(&space, chain(None), &["a", "b"], StoreMode::Ready);
    assert!(first.report.fatal.is_none(), "{:?}", first.report.states);
    assert_eq!(first.io.launches, 2);
    assert_eq!(first.summary.counts.launched_attempts, Some(2));
    assert_eq!(first.summary.counts.cached, 2);
    assert_eq!(first.io.input_clones, 1);
    assert_eq!(first.io.installs, 2);
    assert_eq!(first.io.receipt_writes, 2);
    assert_eq!(
        fs::read(space.path("checkout/Game/b.bin")).unwrap(),
        b"first"
    );
    let before = observations(&space.0);
    let noop = build(&space, chain(None), &["a", "b"], StoreMode::Ready);
    assert!(
        noop.report
            .states
            .values()
            .all(|state| *state == State::Current)
    );
    assert_eq!(noop.io, PythonIo::default());
    assert_eq!(noop.summary.counts.current, 2);
    assert_eq!(noop.summary.counts.launched_attempts, Some(0));
    assert_eq!(noop.summary.counts.receipt_writes, 0);
    assert_eq!(observations(&space.0), before);
}

#[test]
fn actual_python_current_source_survives_unavailable_cache_without_producer_rerun() {
    let space = Space::new();
    space.set("ops/a.py", A.as_bytes());
    space.set("ops/b.py", B.as_bytes());
    space.set("data/raw", b"current bytes");
    build(&space, chain(None), &["a", "b"], StoreMode::Ready);
    space.set(
        "ops/b.py",
        format!("{B}# changed consumer implementation\n").as_bytes(),
    );
    let result = build(&space, chain(None), &["b"], StoreMode::Unavailable);
    assert_eq!(result.report.states["a"], State::Current);
    assert!(matches!(
        result.report.states["b"],
        State::Executed(Publication::NotCached(_))
    ));
    assert_eq!(result.io.launches, 1);
    assert_eq!(result.io.input_clones, 1);
    assert_eq!(result.io.installs, 1);
    assert_eq!(result.io.receipt_writes, 1);
    assert_eq!(
        fs::read(space.path("checkout/Game/b.bin")).unwrap(),
        b"current bytes"
    );
}

#[test]
fn changed_current_source_refuses_before_dispatch_and_preserves_existing_consumer() {
    let space = Space::new();
    space.set("ops/a.py", A.as_bytes());
    space.set("ops/b.py", B.as_bytes());
    space.set("data/raw", b"before");
    build(&space, chain(None), &["a", "b"], StoreMode::Ready);
    space.set("ops/b.py", format!("{B}# force consumer miss\n").as_bytes());
    let result = build(
        &space,
        chain(None),
        &["b"],
        StoreMode::UnavailableAndChangeCurrent,
    );
    assert_eq!(result.report.states["a"], State::Current);
    assert!(matches!(
        result.report.states["b"],
        State::InputRefused(InputFailure::Changed(_))
    ));
    assert_eq!(result.io.launches, 0);
    assert_eq!(result.io.publications, 0);
    assert_eq!(result.io.installs, 0);
    assert_eq!(
        fs::read(space.path("checkout/Game/b.bin")).unwrap(),
        b"before"
    );
    assert_eq!(
        fs::read(space.path("checkout/Game/a.bin")).unwrap(),
        b"changed after identity observation"
    );
}

#[test]
fn equal_digest_current_sources_each_revalidate_before_staging() {
    let space = Space::new();
    space.set("ops/a.py", A.as_bytes());
    space.set(
        "ops/c.py",
        b"def run(c):\n    c.output('c.bin').write_bytes(c.inputs['raw'].read_bytes())\n",
    );
    space.set("ops/b.py", b"def run(c):\n    c.output('b.bin').write_bytes((c.inputs['a'] / 'a.bin').read_bytes() + (c.inputs['raw'] / 'c.bin').read_bytes())\n");
    space.set("data/raw", b"equal");
    let mut declaration = chain(None);
    declaration
        .units
        .push(unit("c", declaration.units[0].inputs.clone()));
    declaration.units[1].inputs.push(Input::Content {
        name: "raw".into(),
        source: ContentSource::Item {
            unit: "c".into(),
            item: "out".into(),
        },
        whole: None,
        conditional: None,
    });
    build(
        &space,
        declaration.clone(),
        &["a", "c", "b"],
        StoreMode::Ready,
    );
    space.set("ops/b.py", b"def run(c):\n    c.output('b.bin').write_bytes((c.inputs['a'] / 'a.bin').read_bytes() + (c.inputs['raw'] / 'c.bin').read_bytes())\n# changed code\n");
    let result = build(
        &space,
        declaration,
        &["b"],
        StoreMode::UnavailableAndChangeLaterCurrent,
    );
    assert_eq!(result.report.states["a"], State::Current);
    assert_eq!(result.report.states["c"], State::Current);
    assert!(matches!(
        result.report.states["b"],
        State::InputRefused(InputFailure::Changed(_))
    ));
    assert_eq!(result.io.launches, 0);
    assert_eq!(result.io.input_clones, 0);
    assert_eq!(result.io.publications, 0);
    assert_eq!(result.io.installs, 0);
    assert_eq!(
        fs::read(space.path("checkout/Game/b.bin")).unwrap(),
        b"equalequal"
    );
}

#[test]
fn renamed_unit_roots_current_scheduling_name_with_old_winner_label() {
    let space = Space::new();
    space.set("ops/a.py", A.as_bytes());
    space.set("data/raw", b"stable");
    let mut declaration = chain(None);
    declaration.units.truncate(1);
    let first = build(&space, declaration.clone(), &["a"], StoreMode::Ready);
    assert_eq!(first.io.launches, 1);
    declaration.units[0].id = "renamed".into();
    let result = build_flags(
        &space,
        declaration,
        &[("renamed", BTreeSet::from([Demand::Stored]))],
        StoreMode::Ready,
    );
    assert_eq!(result.io.launches, 0);
    assert!(!result.rooted_units.is_empty());
    assert!(
        result
            .rooted_units
            .iter()
            .all(|(current, winner)| current == "renamed" && winner == "a")
    );
}

#[test]
fn actual_python_selected_source_and_equal_output_content_cut_off_unaffected_consumer() {
    let space = Space::new();
    space.set("ops/a.py", A.as_bytes());
    space.set("ops/b.py", B.as_bytes());
    space.set("data/raw", br#"{"selected":"one","unused":0}"#);
    build(
        &space,
        chain(Some("/selected")),
        &["a", "b"],
        StoreMode::Ready,
    );
    space.set("data/raw", br#"{"selected":"one","unused":99}"#);
    let unselected = build(
        &space,
        chain(Some("/selected")),
        &["a", "b"],
        StoreMode::Ready,
    );
    assert_eq!(unselected.io.launches, 0);
    space.set(
        "ops/a.py",
        format!("{A}# relevant producer code identity; same output\n").as_bytes(),
    );
    let cutoff = build(
        &space,
        chain(Some("/selected")),
        &["a", "b"],
        StoreMode::Ready,
    );
    assert!(matches!(cutoff.report.states["a"], State::Executed(_)));
    assert_eq!(cutoff.report.states["b"], State::Current);
    assert_eq!(cutoff.io.launches, 1);
    assert_eq!(cutoff.io.input_clones, 0);
    space.set("data/raw", br#"{"selected":"two","unused":99}"#);
    let selected = build(
        &space,
        chain(Some("/selected")),
        &["a", "b"],
        StoreMode::Ready,
    );
    assert_eq!(selected.io.launches, 2);
    assert_eq!(selected.io.input_clones, 1);
    assert_eq!(
        fs::read(space.path("checkout/Game/b.bin")).unwrap(),
        br#""two""#
    );
}

#[test]
fn actual_python_not_cached_local_output_feeds_a_consumer_and_finishes_checkout() {
    let space = Space::new();
    space.set("ops/a.py", A.as_bytes());
    space.set("ops/b.py", B.as_bytes());
    space.set("data/raw", b"local-only bytes");
    let result = build(&space, chain(None), &["b"], StoreMode::Unavailable);
    assert!(result.report.fatal.is_none());
    assert!(result.report.unsatisfied.is_empty());
    for id in ["a", "b"] {
        assert!(matches!(
            result.report.states[id],
            State::Executed(Publication::NotCached(_))
        ));
    }
    assert_eq!(result.io.launches, 2);
    assert_eq!(result.summary.counts.not_cached, 2);
    assert_eq!(result.io.input_clones, 1);
    assert_eq!(result.io.installs, 1);
    assert!(!space.path("cache").exists());
    assert!(!space.path("checkout/Game/a.bin").exists());
    assert_eq!(
        fs::read(space.path("checkout/Game/b.bin")).unwrap(),
        b"local-only bytes"
    );
}

#[test]
fn mixed_local_producer_retains_store_only_sibling_after_checkout_settlement() {
    let space = Space::new();
    space.set("ops/a.py", MIXED_A.as_bytes());
    space.set("ops/b.py", MIXED_B.as_bytes());
    space.set("data/raw", b"mixed local");
    let result = build(&space, mixed_chain(), &["a", "b"], StoreMode::Unavailable);
    assert!(result.report.unsatisfied.is_empty());
    assert!(result.report.fatal.is_none());
    assert_eq!(result.io.launches, 2);
    assert_eq!(result.io.input_clones, 1);
    assert_eq!(result.io.installs, 2);
    assert!(!space.path("cache").exists());
    assert_eq!(
        fs::read(space.path("checkout/Game/a.bin")).unwrap(),
        b"mixed local"
    );
    assert_eq!(
        fs::read(space.path("checkout/Game/b.bin")).unwrap(),
        b"mixed local/extra/final"
    );
}

#[test]
fn mixed_current_and_recorded_identity_resolves_final_hit_without_store_sibling_bytes() {
    let space = Space::new();
    space.set("ops/a.py", MIXED_A.as_bytes());
    space.set("ops/b.py", MIXED_B.as_bytes());
    space.set("data/raw", b"mixed identity");
    let first = build(&space, mixed_chain(), &["a", "b"], StoreMode::Ready);
    let record: ResultEnvelope = serde_json::from_slice(
        &fs::read(
            space
                .path("cache/results")
                .join(format!("{}.json", first.report.keys["a"])),
        )
        .unwrap(),
    )
    .unwrap();
    let digest = &record
        .result
        .outputs
        .iter()
        .find(|item| item.item.id == "extra")
        .unwrap()
        .files[0]
        .digest;
    let missing = space.path("cache/objects/sha256").join(digest);
    // Explicit partial-store corruption, not a claim about normal B5 lineage collection.
    fs::remove_file(&missing).unwrap();
    fs::remove_file(space.path("checkout/Game/b.bin")).unwrap();
    let before = fs::metadata(space.path("checkout/Game/a.bin")).unwrap();
    let hit = build(&space, mixed_chain(), &["b"], StoreMode::Ready);
    assert_eq!(hit.report.states["a"], State::Current);
    assert_eq!(hit.report.states["b"], State::Hit);
    assert_eq!(hit.io.launches, 0);
    assert_eq!(hit.io.staged_jobs, 0);
    assert_eq!(hit.io.input_clones, 0);
    assert_eq!(hit.io.installs, 1);
    assert!(!missing.exists());
    let after = fs::metadata(space.path("checkout/Game/a.bin")).unwrap();
    assert_eq!(
        (
            before.dev(),
            before.ino(),
            before.mtime(),
            before.mtime_nsec()
        ),
        (after.dev(), after.ino(), after.mtime(), after.mtime_nsec())
    );
    assert_eq!(
        fs::read(space.path("checkout/Game/b.bin")).unwrap(),
        b"mixed identity/extra/final"
    );
}

#[test]
fn unneeded_store_only_sibling_does_not_block_current_source_when_cache_is_unavailable() {
    let space = Space::new();
    space.set("ops/a.py", MIXED_A.as_bytes());
    space.set("ops/b.py", B.as_bytes());
    space.set("data/raw", b"selected checkout only");
    let mut declaration = mixed_chain();
    let Input::Content {
        source: ContentSource::Item { item, .. },
        ..
    } = &mut declaration.units[1].inputs[0]
    else {
        unreachable!()
    };
    *item = "out".into();
    build(&space, declaration.clone(), &["a", "b"], StoreMode::Ready);
    space.set("ops/b.py", format!("{B}# consumer miss\n").as_bytes());
    let result = build(&space, declaration, &["b"], StoreMode::Unavailable);
    assert_eq!(result.report.states["a"], State::Current);
    assert!(matches!(
        result.report.states["b"],
        State::Executed(Publication::NotCached(_))
    ));
    assert_eq!(result.io.cache_opens, 1);
    assert_eq!(result.io.launches, 1);
    assert_eq!(result.io.input_clones, 1);
    assert_eq!(
        fs::read(space.path("checkout/Game/b.bin")).unwrap(),
        b"selected checkout only"
    );
}

#[test]
fn actual_final_hit_uses_recorded_parent_identity_without_ancestor_clone_or_rerun() {
    let space = Space::new();
    space.set("ops/a.py", A.as_bytes());
    space.set("ops/b.py", b"def run(c):\n    c.output('b.bin').write_bytes((c.inputs['a'] / 'a.bin').read_bytes() + b'/final')\n");
    space.set("data/raw", b"ancestor bytes");
    let first = build(&space, chain(None), &["a", "b"], StoreMode::Ready);
    let record_path = space
        .path("cache/results")
        .join(format!("{}.json", first.report.keys["a"]));
    let record: ResultEnvelope = serde_json::from_slice(&fs::read(record_path).unwrap()).unwrap();
    let digest = &record.result.outputs[0].files[0].digest;
    let parent_object = space.path("cache/objects/sha256").join(digest);
    fs::remove_file(&parent_object).unwrap();
    fs::remove_file(space.path("checkout/Game/a.bin")).unwrap();
    fs::remove_file(space.path("checkout/Game/b.bin")).unwrap();
    let hit = build(&space, chain(None), &["b"], StoreMode::Ready);
    assert_eq!(hit.report.states["a"], State::Identity);
    assert_eq!(hit.report.states["b"], State::Hit);
    assert_eq!(hit.io.launches, 0);
    assert_eq!(hit.io.staged_jobs, 0);
    assert_eq!(hit.io.input_clones, 0);
    assert_eq!(hit.io.worker_files_written, 0);
    assert_eq!(hit.io.installs, 1);
    assert!(!parent_object.exists());
    assert!(!space.path("checkout/Game/a.bin").exists());
    assert_eq!(
        fs::read(space.path("checkout/Game/b.bin")).unwrap(),
        b"ancestor bytes/final"
    );
}

#[test]
fn dual_explicit_stored_checkout_hit_preserves_healthy_current_files_and_receipts() {
    let space = Space::new();
    space.set("ops/a.py", A.as_bytes());
    space.set("ops/b.py", B.as_bytes());
    space.set("data/raw", b"both requirements");
    build(&space, chain(None), &["a", "b"], StoreMode::Ready);
    let before = observations(&space.path("checkout"));
    let result = build_flags(
        &space,
        chain(None),
        &[("b", BTreeSet::from([Demand::Stored, Demand::Checkout]))],
        StoreMode::Ready,
    );
    assert_eq!(result.report.states["a"], State::Current);
    assert_eq!(result.report.states["b"], State::Hit);
    assert!(result.report.unsatisfied.is_empty());
    assert_eq!(result.io.launches, 0);
    assert_eq!(result.io.staged_jobs, 0);
    assert_eq!(result.io.installs, 0);
    assert_eq!(result.io.receipt_writes, 0);
    assert_eq!(observations(&space.path("checkout")), before);
}

#[test]
fn dual_explicit_targets_report_unavailable_stored_without_rewriting_valid_checkout() {
    let space = Space::new();
    space.set("ops/a.py", A.as_bytes());
    space.set("ops/b.py", B.as_bytes());
    space.set("data/raw", b"checkout remains usable");
    build(&space, chain(None), &["a", "b"], StoreMode::Ready);
    let before = fs::metadata(space.path("checkout/Game/b.bin")).unwrap();
    let result = build_flags(
        &space,
        chain(None),
        &[("b", BTreeSet::from([Demand::Stored, Demand::Checkout]))],
        StoreMode::Unavailable,
    );
    assert_eq!(result.report.states["a"], State::Current);
    assert!(matches!(
        result.report.states["b"],
        State::Executed(Publication::NotCached(_))
    ));
    assert_eq!(
        result.report.unsatisfied["b"],
        BTreeSet::from([Demand::Stored])
    );
    assert_eq!(result.io.installs, 0);
    assert_eq!(result.io.receipt_writes, 0);
    let after = fs::metadata(space.path("checkout/Game/b.bin")).unwrap();
    assert_eq!(
        (
            before.dev(),
            before.ino(),
            before.mtime(),
            before.mtime_nsec(),
            before.ctime(),
            before.ctime_nsec()
        ),
        (
            after.dev(),
            after.ino(),
            after.mtime(),
            after.mtime_nsec(),
            after.ctime(),
            after.ctime_nsec()
        )
    );
    assert_eq!(
        fs::read(space.path("checkout/Game/b.bin")).unwrap(),
        b"checkout remains usable"
    );
}

#[test]
fn same_key_cached_and_current_content_disagreement_refuses_dual_fulfillment() {
    let space = Space::new();
    space.set("ops/a.py", A.as_bytes());
    space.set("ops/b.py", b"def run(c):\n    c.output('b.bin').write_bytes((c.inputs['a'] / 'a.bin').read_bytes() + b'/final')\n");
    space.set("data/raw", b"original");
    let first = build(&space, chain(None), &["a", "b"], StoreMode::Ready);
    let parent: ResultEnvelope = serde_json::from_slice(
        &fs::read(
            space
                .path("cache/results")
                .join(format!("{}.json", first.report.keys["a"])),
        )
        .unwrap(),
    )
    .unwrap();
    let path = space
        .path("cache/results")
        .join(format!("{}.json", first.report.keys["b"]));
    let mut record: ResultEnvelope = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    // Explicit metadata corruption: reference another real verified blob while keeping the old key.
    // No fake cache capability is minted; the backend must reject contradictory existing proofs.
    record.result.outputs[0].files[0].digest = parent.result.outputs[0].files[0].digest.clone();
    record.result.outputs[0].files[0].size = parent.result.outputs[0].files[0].size;
    fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
    fs::write(&path, serde_json::to_vec(&record).unwrap()).unwrap();
    fs::set_permissions(&path, fs::Permissions::from_mode(0o444)).unwrap();
    let result = build_flags(
        &space,
        chain(None),
        &[("b", BTreeSet::from([Demand::Stored, Demand::Checkout]))],
        StoreMode::Ready,
    );
    assert!(
        matches!(&result.report.states["b"], State::Failed(reason) if reason.contains("same-key Current"))
    );
    assert_eq!(result.io.launches, 0);
    assert_eq!(result.io.installs, 0);
    assert_eq!(result.io.publications, 0);
    assert_eq!(
        fs::read(space.path("checkout/Game/b.bin")).unwrap(),
        b"original/final"
    );
}

#[test]
fn actual_python_later_independent_failure_preserves_completed_publication_and_checkout() {
    let space = Space::new();
    space.set("ops/a.py", A.as_bytes());
    space.set(
        "ops/z.py",
        b"def run(c):\n    raise RuntimeError('later independent failure')\n",
    );
    space.set("data/raw", b"retained successful output");
    let mut declaration = chain(None);
    declaration.units.truncate(1);
    declaration.units.push(unit("z", vec![]));
    let result = build(&space, declaration, &["a", "z"], StoreMode::Ready);
    assert!(result.report.fatal.is_none());
    assert!(matches!(
        result.report.states["a"],
        State::Executed(Publication::Cached)
    ));
    assert!(matches!(result.report.states["z"], State::Failed(_)));
    assert_eq!(result.io.launches, 2);
    assert_eq!(result.io.publications, 1);
    assert_eq!(result.io.installs, 1);
    assert_eq!(
        fs::read(space.path("checkout/Game/a.bin")).unwrap(),
        b"retained successful output"
    );
    assert!(
        space
            .path("cache/results")
            .join(format!("{}.json", result.report.keys["a"]))
            .is_file()
    );
    assert!(
        !space
            .path("cache/results")
            .join(format!("{}.json", result.report.keys["z"]))
            .exists()
    );
    assert!(!space.path("checkout/Game/z.bin").exists());
}

#[test]
fn production_submission_failure_preserves_no_worker_or_publication() {
    let space = Space::new();
    space.set("ops/a.py", A.as_bytes());
    space.set("data/raw", b"must not execute");
    let (graph, snapshot, versions) = graph(&space, chain(None));
    let reader = ReceiptReader::open(space.path("checkout"), policy()).unwrap();
    let guard = reader.locks().try_build_exclusive().unwrap();
    let ownership = OwnershipSnapshot::from_projects([(policy().project, &graph)]).unwrap();
    let bundle = implementation();
    let runtimes = BTreeMap::from([(
        "a".into(),
        Runtime {
            worker: bundle.identity(),
            validator: py_data_validator_identity(),
            staged_inputs: BTreeMap::from([("raw".into(), "inputs/raw".into())]),
            profile: "production-refusal".into(),
        },
    )]);
    let demands = BTreeMap::from([("a".into(), BTreeSet::from([Demand::Checkout]))]);
    let request = scheduler::Request::select(
        &graph,
        &[Target::Unit("a".into())],
        &snapshot,
        &versions,
        &runtimes,
        &demands,
    )
    .unwrap();
    let mut backend = PythonBackend::new(
        &graph,
        request.selected(),
        &snapshot,
        &reader,
        &guard,
        &ownership,
        owner(),
        provenance(),
        || {
            Err(InstallError::Cache(ResultError::Io(std::io::Error::other(
                "fixture unavailable",
            ))))
        },
        |_, _| panic!("no output may root before custodian registration"),
    );
    let launcher = GuardedLauncher {
        bridge: vec!["must-not-launch-a-process".into()],
    };
    let mut executor = PythonExecutor::new(
        launcher,
        PythonExecution {
            interpreter: interpreter(),
            bundle,
            profile: "production-refusal".into(),
            memory_gib: 1,
            limits: Limits {
                job: Duration::from_secs(1),
                cleanup: Duration::from_secs(1),
                overall: Some(Duration::from_secs(2)),
            },
        },
    );
    let report = scheduler::run(
        request,
        &mut backend,
        &mut executor,
        &Running,
        &mut SourceHashCache::default(),
    )
    .unwrap();
    assert!(report.fatal.is_none());
    assert!(matches!(&report.states["a"], State::Failed(reason) if !reason.is_empty()));
    let io = backend.finish().unwrap();
    assert_eq!(io.launches, 0);
    assert_eq!(io.worker_files_written, PYTHON_WORKER_FILES.len());
    assert_eq!(io.publications, 0);
    assert!(!space.path("checkout/Game/a.bin").exists());
}

mod judgement {
    use super::*;
    use crate::support::{
        adapter::{
            AdapterError, BuildAdapter, BuildOutcome, BuildRequest, FakeAdapter, Observation,
        },
        check::{Scenario, Step, run_scenario},
        snapshot::FrozenSnapshot,
        spec::{
            self, Edge, EdgeRole, InputSpec, OutputSpec, Plan, SavedUnit, StoreHealth, UnitSpec,
        },
        work::{MemberFile, ProducedItem, ProducedItems, resolve_input, unit_identity},
    };

    struct Adapter {
        space: Space,
        observed: BTreeMap<String, Vec<u8>>,
        executions: usize,
        overbuild: bool,
    }
    impl Adapter {
        fn new(overbuild: bool) -> Self {
            Self {
                space: Space::new(),
                observed: BTreeMap::new(),
                executions: 0,
                overbuild,
            }
        }
    }
    fn error(message: impl ToString) -> AdapterError {
        AdapterError {
            message: message.to_string(),
        }
    }

    impl BuildAdapter for Adapter {
        fn execute(&mut self, request: &BuildRequest<'_>) -> Result<BuildOutcome, AdapterError> {
            self.executions += 1;
            if request.store != StoreHealth::Available {
                return Err(error("bounded harness fixture uses available store"));
            }
            let mut units = vec![];
            let mut spec = PyDataSpec::new()
                .with_param("fixture_params", ParamKind::String, true)
                .with_param("fixture_inputs", ParamKind::Object, true)
                .with_param("fixture_outputs", ParamKind::Array, true);
            let mut staged = BTreeMap::new();
            for unit in request
                .units
                .iter()
                .filter(|unit| request.plan.contains(&unit.id))
            {
                if unit.op_kind != "py_data" || unit.op_version != "1" {
                    return Err(error("bounded py_data fixture op"));
                }
                let script = format!("ops/{}.py", unit.id);
                let mut code = include_bytes!("../fixtures/static_data_op.py").to_vec();
                code.extend_from_slice(
                    format!("\n# explicit code identity: {:?}\n", unit.code).as_bytes(),
                );
                if self.overbuild && unit.id == "b" {
                    code.extend_from_slice(
                        format!(
                            "# deliberately wrong extra invalidation {}\n",
                            self.executions
                        )
                        .as_bytes(),
                    );
                }
                self.space.set(&script, &code);
                let mut inputs = vec![];
                let mut views = serde_json::Map::new();
                let mut names = BTreeMap::new();
                for input in &unit.inputs {
                    names.insert(input.name().into(), input.staged_path());
                    let source = match input {
                        InputSpec::File {
                            name,
                            path,
                            optional,
                            ..
                        } => {
                            if let Some(file) = request.snapshot.get(path) {
                                self.space.set(path, &file.bytes);
                            } else if self.space.path(&format!("checkout/{path}")).exists() {
                                fs::remove_file(self.space.path(&format!("checkout/{path}")))
                                    .map_err(error)?;
                            }
                            spec = spec.with_content_slot(name, ContentSlotSpec::bounded(false));
                            views.insert(name.clone(), serde_json::json!({"role":"file"}));
                            Input::Content {
                                name: name.clone(),
                                source: ContentSource::File {
                                    path: path.clone(),
                                    selector: None,
                                    optional: *optional,
                                },
                                whole: None,
                                conditional: None,
                            }
                        }
                        InputSpec::Item {
                            name,
                            unit: producer,
                            item,
                            ..
                        } => {
                            spec = spec.with_content_slot(name, ContentSlotSpec::bounded(false));
                            let output = request
                                .units
                                .iter()
                                .find(|unit| unit.id == *producer)
                                .and_then(|unit| {
                                    unit.outputs.iter().find(|output| output.item == *item)
                                })
                                .ok_or_else(|| error("missing declared fixture item"))?;
                            views.insert(name.clone(), serde_json::json!({"role":"item",
                                "files":output.files.iter().map(|file| file.path.clone()).collect::<Vec<_>>()}));
                            Input::Content {
                                name: name.clone(),
                                source: ContentSource::Item {
                                    unit: producer.clone(),
                                    item: item.clone(),
                                },
                                whole: None,
                                conditional: None,
                            }
                        }
                        InputSpec::Reference {
                            name,
                            logical_path,
                            class,
                            producer,
                            ..
                        } => {
                            spec = spec.with_reference_slot(name, false, [class.as_str()]);
                            views.insert(name.clone(), serde_json::json!({"role":"reference"}));
                            Input::Reference {
                                name: name.clone(),
                                logical_path: logical_path.clone(),
                                class: class.clone(),
                                proof: "independent fixture reads declared descriptor only".into(),
                                producer: producer.as_ref().map(|(unit, item)| ItemRef {
                                    unit: unit.clone(),
                                    item: item.clone(),
                                }),
                            }
                        }
                    };
                    inputs.push(source);
                }
                let output_params: Vec<_> = unit.outputs.iter().flat_map(|output| output.files.iter().map(|file|
                    serde_json::json!({"logical_path":output.logical_path,"class":output.class,"path":file.path,"mode":file.mode}))).collect();
                units.push(Unit {
                    id: unit.id.clone(),
                    op: Op {
                        kind: unit.op_kind.clone(),
                        version: unit.op_version.clone(),
                    },
                    script: script.clone(),
                    code: vec![script],
                    inputs,
                    params: BTreeMap::from([
                        ("seed".into(), serde_json::json!(0)),
                        ("fixture_params".into(), serde_json::json!(unit.params)),
                        ("fixture_inputs".into(), serde_json::Value::Object(views)),
                        ("fixture_outputs".into(), serde_json::json!(output_params)),
                    ]),
                    outputs: unit
                        .outputs
                        .iter()
                        .map(|output| Item {
                            id: output.item.clone(),
                            logical_path: output.logical_path.clone(),
                            class: output.class.clone(),
                            destination: Destination::Store,
                            files: output
                                .files
                                .iter()
                                .map(|file| OutputFile {
                                    path: file.path.clone(),
                                    install_path: None,
                                    required: file.required,
                                })
                                .collect(),
                        })
                        .collect(),
                    output_groups: vec![],
                    conditional: None,
                });
                staged.insert(unit.id.clone(), names);
            }
            let declaration = Declaration {
                schema_version: SCHEMA_VERSION,
                cache_version: request.config.cache_version.clone(),
                units,
            };
            let registry =
                BTreeMap::from([(("py_data".into(), "1".into()), spec.build().map_err(error)?)]);
            let graph =
                BuildGraph::validate(declaration, &registry, &["Game".into()]).map_err(error)?;
            let mut names = BTreeSet::new();
            for unit in &graph.declaration().units {
                names.extend(unit.code.iter().map(String::as_str));
                for input in &unit.inputs {
                    if let Input::Content {
                        source: ContentSource::File { path, .. },
                        ..
                    } = input
                    {
                        names.insert(path.as_str());
                    }
                }
            }
            let captured = capture_sources(&self.space.path("checkout"), names).map_err(error)?;
            let bundle = implementation();
            let runtimes = graph
                .declaration()
                .units
                .iter()
                .map(|unit| {
                    (
                        unit.id.clone(),
                        Runtime {
                            worker: bundle.identity(),
                            validator: py_data_validator_identity(),
                            staged_inputs: staged.remove(&unit.id).unwrap(),
                            profile: "scripted-sandbox-fixture".into(),
                        },
                    )
                })
                .collect();
            let targets: Vec<_> = request
                .targets
                .iter()
                .map(|target| match target {
                    spec::Target::Unit(id) => Target::Unit(id.clone()),
                    spec::Target::All => Target::All,
                })
                .collect();
            let selected = graph.select(&targets, &captured.snapshot).map_err(error)?;
            let demands = selected
                .roots()
                .iter()
                .map(|id| (id.clone(), BTreeSet::from([Demand::Stored])))
                .collect();
            let run = run_graph(
                &self.space,
                &graph,
                &captured.snapshot,
                &captured.versions,
                &runtimes,
                &targets,
                &demands,
                bundle,
                StoreMode::Ready,
            );
            self.observed.extend(run.fresh_bytes);
            if run.report.states.values().any(|state| {
                !matches!(
                    state,
                    State::Identity | State::Hit | State::Executed(Publication::Cached)
                )
            }) {
                return Err(error(format!(
                    "real backend incomplete: {:?}",
                    run.report.states
                )));
            }
            let expected_clones: usize = request
                .units
                .iter()
                .filter(|unit| matches!(run.report.states.get(&unit.id), Some(State::Executed(_))))
                .flat_map(|unit| &unit.inputs)
                .filter_map(|input| match input {
                    InputSpec::Item { unit, item, .. } => Some(
                        request
                            .units
                            .iter()
                            .find(|source| source.id == *unit)
                            .and_then(|source| {
                                source.outputs.iter().find(|output| output.item == *item)
                            })
                            .unwrap()
                            .files
                            .len(),
                    ),
                    _ => None,
                })
                .sum();
            if run.io.input_clones != expected_clones
                || run.io.worker_files_written != run.io.launches * PYTHON_WORKER_FILES.len()
            {
                return Err(error(
                    "actual selected input/worker file operations disagree with executed workload",
                ));
            }
            let mut outputs = ProducedItems::new();
            for (key, stored) in run.items {
                let files = stored
                    .files
                    .iter()
                    .map(|file| {
                        Ok(MemberFile {
                            path: file.path.clone(),
                            mode: file.mode,
                            bytes: self
                                .observed
                                .get(&file.digest)
                                .ok_or_else(|| error("observer has no prior actual bytes"))?
                                .clone(),
                        })
                    })
                    .collect::<Result<Vec<_>, AdapterError>>()?;
                outputs.insert(
                    key,
                    ProducedItem {
                        logical_path: stored.item.logical_path,
                        class: stored.item.class,
                        files,
                    },
                );
            }
            let mut saved_after = request.saved.clone();
            for id in selected.order() {
                let unit = request.units.iter().find(|unit| unit.id == *id).unwrap();
                let resolved = unit
                    .inputs
                    .iter()
                    .map(|input| resolve_input(input, request.snapshot, &outputs))
                    .collect::<Result<Vec<_>, _>>()
                    .map_err(error)?;
                saved_after.insert(
                    id,
                    SavedUnit {
                        identity: unit_identity(request.config, unit, &resolved),
                        outputs: unit
                            .outputs
                            .iter()
                            .map(|output| {
                                (
                                    output.item.clone(),
                                    outputs[&(id.clone(), output.item.clone())].clone(),
                                )
                            })
                            .collect(),
                    },
                );
            }
            let edges = selected
                .dependencies()
                .iter()
                .map(|edge| Edge {
                    producer: edge.producer.clone(),
                    consumer: edge.consumer.clone(),
                    item: match &edge.output {
                        crate::graph::DependencyOutput::Item(item) => item.clone(),
                        _ => unreachable!(),
                    },
                    input: edge.input.clone(),
                    role: match edge.role {
                        crate::graph::EdgeRole::Content => EdgeRole::Content,
                        crate::graph::EdgeRole::Reference => EdgeRole::Reference,
                    },
                })
                .collect();
            Ok(BuildOutcome {
                observation: Observation {
                    roots: selected.roots().iter().cloned().collect(),
                    order: selected.order().to_vec(),
                    edges,
                    runs: selected
                        .order()
                        .iter()
                        .filter(|id| matches!(run.report.states[*id], State::Executed(_)))
                        .cloned()
                        .collect(),
                    current: selected
                        .order()
                        .iter()
                        .filter(|id| !matches!(run.report.states[*id], State::Executed(_)))
                        .cloned()
                        .collect(),
                    requested: outputs
                        .iter()
                        .filter(|((id, _), _)| selected.roots().contains(id))
                        .map(|(key, value)| (key.clone(), value.clone()))
                        .collect(),
                    outputs,
                    removal_intent: BTreeMap::new(),
                    worker_events: run.io.launches,
                },
                saved_after,
            })
        }
    }

    fn scenario() -> Scenario {
        let output = |name: &str| {
            let mut output =
                OutputSpec::new("out", format!("/Game/{name}")).file(format!("{name}.bin"));
            output.class = "Data".into();
            output
        };
        let units = vec![
            UnitSpec::new("a")
                .file_input("raw", "data/raw")
                .output(output("a")),
            UnitSpec::new("b")
                .item_input("a", "a", "out")
                .reference_from("ref", "/Game/ref", "Data", "ref", "out")
                .output(output("b")),
            UnitSpec::new("ref")
                .file_input("raw", "data/ref")
                .output(output("ref")),
        ];
        let source = FrozenSnapshot::builder()
            .file("data/raw", b"first bytes".to_vec())
            .file("data/ref", b"reference bytes".to_vec())
            .build();
        let mut edited = units.clone();
        edited[0].code = "code-2".into();
        let mut scenario = Scenario::new(
            "real static Python backend against independent judgement",
            vec![
                Step::new(
                    "first",
                    units.clone(),
                    source.clone(),
                    Plan::all(&units),
                    [spec::Target::Unit("b".into())],
                )
                .expect_runs(["a", "ref", "b"]),
                Step::new(
                    "no-op",
                    units.clone(),
                    source.clone(),
                    Plan::all(&units),
                    [spec::Target::Unit("b".into())],
                )
                .expect_runs(Vec::<String>::new()),
                Step::new(
                    "producer code changes; output unchanged",
                    edited.clone(),
                    source.clone(),
                    Plan::all(&edited),
                    [spec::Target::Unit("b".into())],
                )
                .expect_runs(["a"]),
                Step::new(
                    "reference bytes change without consumer read",
                    edited.clone(),
                    source.with_file("data/ref", b"changed reference bytes".to_vec()),
                    Plan::all(&edited),
                    [spec::Target::Unit("b".into())],
                )
                .expect_runs(["ref"]),
                Step::new(
                    "selected content changes",
                    edited.clone(),
                    source
                        .with_file("data/raw", b"next bytes".to_vec())
                        .with_file("data/ref", b"changed reference bytes".to_vec()),
                    Plan::all(&edited),
                    [spec::Target::Unit("b".into())],
                )
                .expect_runs(["a", "b"]),
            ],
        );
        scenario.config.worker_version = implementation().identity().version;
        scenario.config.validator_version = py_data_validator_identity().version;
        scenario
    }

    #[test]
    fn real_backend_matches_independent_model_and_clean_oracle_and_rejects_overbuilding_adapter() {
        let scenario = scenario();
        run_scenario(
            &scenario,
            || Box::new(Adapter::new(false)),
            || Box::new(FakeAdapter::new()),
        )
        .unwrap();
        assert!(
            run_scenario(
                &scenario,
                || Box::new(Adapter::new(true)),
                || Box::new(FakeAdapter::new())
            )
            .is_err()
        );
    }
}
