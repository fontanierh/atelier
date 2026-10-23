use atelier_build_v2::controller::{ControllerRequest, prepare};
use serde_json::{Value, json};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

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
    let space = Space::new();
    let base = request(&space.0);
    assert!(parse(&base).is_ok());
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
    raw.resize(2 * 1024 * 1024 + 1, b' ');
    assert!(ControllerRequest::parse(&raw).is_err());
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
