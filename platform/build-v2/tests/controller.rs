use atelier_build_v2::controller::{
    ControllerRequest, ExecutionContext, Finalization, execute, prepare,
};
use atelier_build_v2::failure_policy::Limits;
use atelier_build_v2::guard_adapter::GuardedLauncher;
use atelier_build_v2::leases::ProcessIdentity;
use atelier_build_v2::scheduler::Control;
use atelier_build_v2::schema::Provenance;
use serde_json::{Value, json};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

static NEXT: AtomicU64 = AtomicU64::new(0);
struct Space(PathBuf);
impl Space {
    fn new() -> Self {
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "atelier-v2-controller-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        Self(root)
    }
    fn set(&self, name: &str, bytes: &[u8]) {
        let path = self.0.join(name);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, bytes).unwrap();
    }
}
impl Drop for Space {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}

fn request(root: &Path) -> Value {
    json!({
        "version": 1, "checkout": root, "project": "controllerfixture",
        "allowed_install_roots": ["Game"], "targets": ["data.copy"],
        "data_contract": {"content_slots": {"raw": true}},
        "staged_inputs": {"data.copy": {"raw": "inputs/raw.json"}},
        "declaration": {"schema_version": 2, "cache_version": "v2-1", "units": [{
            "id": "data.copy", "op": {"kind": "py_data", "version": "1"},
            "script": "ops/copy.py", "code": ["ops/copy.py"],
            "inputs": [{"role": "content", "name": "raw", "source": {
                "kind": "file", "path": "data/source.json"}, "whole": "Exact byte copy."}],
            "outputs": [{"id": "copy", "logical_path": "/Game/Data/copy.json", "class": "JsonData",
                "destination": "checkout", "files": [{"path": "copy.json", "install_path": "Game/copy.json"}]}]
        }]}
    })
}

fn parse(value: &Value) -> Result<ControllerRequest, String> {
    ControllerRequest::parse(&serde_json::to_vec(value).unwrap())
}

#[test]
fn strict_request_refuses_unknown_fields_and_unsupported_ops() {
    let mut registry = Default::default();
    atelier_build_v2::recipe_ops::register(
        &mut registry,
        &std::collections::BTreeMap::from([("native".into(), true)]),
    )
    .unwrap();
    for kind in ["recipe.python", "recipe.blender"] {
        let op = &registry[&(kind.into(), "1".into())];
        for class in [
            "StaticMesh",
            "SkeletalMesh",
            "Skeleton",
            "PhysicsAsset",
            "Animation",
            "Texture",
            "Sound",
            "Material",
            "MaterialInstance",
            "MaterialParameterCollection",
            "Map",
        ] {
            assert!(op.inputs["native"].item_classes.contains(class));
            assert!(!op.output_classes.contains(class));
        }
        assert!(!op.inputs["native"].item_classes.contains("CookedPackage"));
        assert!(
            !op.inputs["native"]
                .item_classes
                .contains("ExternalCookedPackage")
        );
    }
    let space = Space::new();
    let base = request(&space.0);
    assert!(parse(&base).is_ok());
    for (pointer, fields) in [
        (
            "",
            vec![
                "version",
                "checkout",
                "project",
                "allowed_install_roots",
                "declaration",
                "targets",
                "data_contract",
                "staged_inputs",
            ],
        ),
        ("/data_contract", vec!["content_slots"]),
        (
            "/declaration",
            vec!["schema_version", "cache_version", "units"],
        ),
        (
            "/declaration/units/0",
            vec![
                "id",
                "op",
                "script",
                "code",
                "inputs",
                "params",
                "outputs",
                "output_groups",
                "conditional",
            ],
        ),
        ("/declaration/units/0/op", vec!["kind", "version"]),
        (
            "/declaration/units/0/inputs/0/source",
            vec!["kind", "path", "selector", "optional"],
        ),
        (
            "/declaration/units/0/outputs/0",
            vec!["id", "logical_path", "class", "files", "destination"],
        ),
        (
            "/declaration/units/0/outputs/0/files/0",
            vec!["path", "install_path", "required"],
        ),
    ] {
        let mut value = base.clone();
        let target = value.pointer_mut(pointer).unwrap();
        *target = Value::Array(
            fields
                .iter()
                .map(|field| target.get(*field).cloned().unwrap_or(Value::Null))
                .collect(),
        );
        assert!(
            parse(&value).unwrap_err().contains("must be a JSON object"),
            "positional record {pointer}"
        );
    }
    for mutation in [
        "unknown",
        "version",
        "op",
        "class",
        "params",
        "staged_alias",
        "missing_slot",
    ] {
        let mut value = base.clone();
        match mutation {
            "unknown" => value["environment"] = json!({"SECRET": "not an input"}),
            "version" => value["version"] = json!(2),
            "op" => value["declaration"]["units"][0]["op"]["kind"] = json!("audio"),
            "class" => value["declaration"]["units"][0]["outputs"][0]["class"] = json!("Data"),
            "params" => {
                value["declaration"]["units"][0]["params"] = json!({"engine_id": "platform"})
            }
            "staged_alias" => value["staged_inputs"]["data.copy"]["raw"] = json!("ops/copy.py"),
            "missing_slot" => value["staged_inputs"]["data.copy"] = json!({}),
            _ => unreachable!(),
        }
        assert!(parse(&value).is_err(), "accepted {mutation}");
    }
    let mut raw = serde_json::to_vec(&base).unwrap();
    let duplicate = String::from_utf8(raw.clone())
        .unwrap()
        .replace("\"raw\":true", "\"raw\":true,\"raw\":false");
    assert!(
        ControllerRequest::parse(duplicate.as_bytes()).is_err(),
        "duplicate nested control field accepted"
    );
    raw.resize(2 * 1024 * 1024 + 1, b' ');
    assert!(ControllerRequest::parse(&raw).is_ok());
    raw.resize(atelier_build_v2::controller::MAX_CONTROL_BYTES + 1, b' ');
    assert!(ControllerRequest::parse(&raw).is_err());
    let mut malformed_template = base.clone();
    malformed_template["templates"] = json!([[]]);
    assert!(
        parse(&malformed_template)
            .unwrap_err()
            .contains("must be a JSON object")
    );
    malformed_template["templates"] = json!([{"producer":"data.copy", "unknown":true}]);
    assert!(parse(&malformed_template).is_err());
}

#[test]
fn prepare_plan_has_no_state_writes_and_uses_existing_worker_identity() {
    let space = Space::new();
    space.set(
        "ops/copy.py",
        b"def run(c): c.output('copy.json').write_bytes(c.input('raw').read_bytes())\n",
    );
    space.set("data/source.json", b"{\"valid\":true}\n");
    for name in ["protocol.py", "python_job.py", "python_worker.py"] {
        space.set(
            &format!("platform/studio/atelier/build_v2/{name}"),
            format!("# fixture {name}\n").as_bytes(),
        );
    }
    let parsed = parse(&request(&space.0)).unwrap();
    let prepared = prepare(&parsed).unwrap();
    let plan = prepared.plan().unwrap();
    assert_eq!(plan.selected, ["data.copy"]);
    assert_eq!(plan.reuse, "unknown_readonly_store_unavailable");
    assert_eq!(
        prepared.runtimes["data.copy"].worker.digest,
        prepared.worker.identity().digest
    );
    for absent in [
        "Game", "cache", "build", ".atelier", "roots", "leases", "jobs",
    ] {
        assert!(!space.0.join(absent).exists(), "planning created {absent}");
    }
    assert_eq!(
        fs::read(space.0.join("data/source.json")).unwrap(),
        b"{\"valid\":true}\n"
    );
    for name in atelier_build_v2::native_tools::NATIVE_TOOL_FILES {
        space.set(
            &format!("platform/studio/atelier/build_v2/{name}"),
            format!("# fixed fixture {name}\n").as_bytes(),
        );
    }
    let mut native = request(&space.0);
    let unit = &mut native["declaration"]["units"][0];
    unit["op"]["kind"] = json!("unreal.compile");
    unit["script"] = json!(atelier_build_v2::native_tool_ops::ENTRY);
    unit["code"] = json!([atelier_build_v2::native_tool_ops::ENTRY]);
    unit["params"] = json!({"project":"game/Game.uproject", "target":"GameEditor", "recipe":{
        "version":1,"commands":[],"paths":{"game/Game.uproject":"inputs/raw.json"},
        "outputs":[{"path":"game/Binaries/Mac","kind":"tree","file":"binary.tree.tar","required":true}],
        "verify":null,"deferred":[]}});
    unit["outputs"][0]["class"] = json!("Data");
    let prepared = prepare(&parse(&native).unwrap()).unwrap();
    assert_eq!(
        prepared.runtimes["data.copy"].worker.version,
        atelier_build_v2::native_tools::NATIVE_TOOL_VERSION
    );
    assert!(prepared.native_tool_worker.is_some());
    assert!(!space.0.join("cache").exists());
    assert!(!space.0.join("build").exists());
    native["declaration"]["units"][0]["params"]["project"] = json!("../outside.uproject");
    assert!(parse(&native).is_err());
}

#[test]
fn selected_source_capture_excludes_unrelated_units_without_weakening_global_structure() {
    let space = Space::new();
    space.set("ops/copy.py", b"# selected code\n");
    space.set("data/source.json", b"{}\n");
    space.set("ops/unrelated.py", b"# unrelated code\n");
    space.set("data/unrelated.json", b"{\"must_not_read\":true}\n");
    for name in ["protocol.py", "python_job.py", "python_worker.py"] {
        space.set(
            &format!("platform/studio/atelier/build_v2/{name}"),
            b"# worker\n",
        );
    }
    let mut value = request(&space.0);
    let mut other = value["declaration"]["units"][0].clone();
    other["id"] = json!("unrelated");
    other["script"] = json!("ops/unrelated.py");
    other["code"] = json!(["ops/unrelated.py"]);
    other["inputs"][0]["source"]["path"] = json!("data/unrelated.json");
    other["outputs"][0]["logical_path"] = json!("/Game/Data/unrelated.json");
    other["outputs"][0]["files"][0]["install_path"] = json!("Game/unrelated.json");
    value["declaration"]["units"]
        .as_array_mut()
        .unwrap()
        .push(other);
    value["staged_inputs"]["unrelated"] = json!({"raw": "inputs/raw.json"});
    let prepared = prepare(&parse(&value).unwrap()).unwrap();
    assert_eq!(prepared.sources.files_read, 2);
    assert!(
        !prepared
            .sources
            .snapshot
            .contains_key("data/unrelated.json")
    );
    fs::remove_file(space.0.join("data/unrelated.json")).unwrap();
    assert_eq!(
        prepare(&parse(&value).unwrap())
            .unwrap()
            .plan()
            .unwrap()
            .selected,
        ["data.copy"]
    );
    value["targets"] = json!(["unrelated"]);
    assert!(prepare(&parse(&value).unwrap()).is_err());
    value["targets"] = json!(["data.copy"]);
    value["declaration"]["units"][1]["outputs"][0]["files"][0]["install_path"] =
        json!("Game/copy.json");
    assert!(
        prepare(&parse(&value).unwrap()).is_err(),
        "unselected ownership collision was ignored"
    );
}

#[test]
fn controller_cancelled_before_run_keeps_state_absent() {
    struct Cancelled;
    impl Control for Cancelled {
        fn cancelled(&self) -> bool {
            true
        }
    }
    let space = Space::new();
    let parsed = parse(&request(&space.0)).unwrap();
    let result = execute(
        &parsed,
        ExecutionContext {
            cache_root: space.0.join("cache"),
            blender: None,
            node: None,
            ffmpeg: None,
            ffprobe: None,
            unreal: None,
            native_export_project: None,
            unreal_memory_gib: None,
            blender_memory_gib: None,
            unreal_job_seconds: None,
            interpreter: PathBuf::from("/fixture/not-executed-python"),
            // No lease is opened or identity authority claimed in this early-cancellation case.
            owner: ProcessIdentity {
                pid: std::process::id(),
                boot: "fixture".into(),
                started: "fixture".into(),
            },
            provenance: Provenance {
                checkout: "fixture".into(),
                branch: "fixture".into(),
                commit: "fixture".into(),
                dirty: false,
                built_at: "fixture".into(),
            },
            worktree_id: "a".repeat(64),
            memory_gib: 1,
            limits: Limits {
                job: Duration::from_secs(5),
                cleanup: Duration::from_secs(2),
                overall: Some(Duration::from_secs(10)),
            },
        },
        GuardedLauncher { bridge: vec![] },
        &Cancelled,
    )
    .unwrap();
    assert!(result.cancellation_requested);
    assert!(!result.final_requirements_satisfied);
    assert!(!result.scheduler_error);
    assert!(result.summary.is_none());
    assert_eq!(result.io.observed_worker_attempts, 0);
    assert_eq!(result.io.cache_opens, 0);
    assert_eq!(result.io.receipt_writes, 0);
    assert!(matches!(
        result.source_finalization,
        Finalization::NotOpened
    ));
    assert!(matches!(result.root_finalization, Finalization::NotOpened));
    assert_eq!(fs::read_dir(&space.0).unwrap().count(), 0);
}


#[test]
fn game_finish_bodies_use_the_registered_native_contract() {
    let space = Space::new();
    let mut value = request(&space.0);
    let unit = &mut value["declaration"]["units"][0];
    unit["script"] = json!("games/fixture/finish.py");
    unit["code"] = json!(["games/fixture/finish.py"]);
    unit["op"]["kind"] = json!("unreal.finish");
    assert!(parse(&value).is_ok());
    value["declaration"]["units"][0]["op"]["kind"] = json!("unreal.author");
    assert!(parse(&value).is_ok());
    value["declaration"]["units"][0]["op"]["kind"] = json!("unreal.raw_import");
    assert!(parse(&value).is_err());
}
