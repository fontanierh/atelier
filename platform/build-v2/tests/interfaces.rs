use atelier_build_v2::{fixture::*, protocol::*, schema::*};
use std::collections::BTreeMap;

fn declaration() -> Declaration {
    parse_declaration(include_str!("../examples/units.toml")).unwrap()
}

fn job() -> JobRequest {
    JobRequest {
        job_id: "job-1".into(),
        unit: "sample.geometry".into(),
        op: Op {
            kind: "py_data".into(),
            version: "1".into(),
        },
        job_dir: "staged-job".into(),
        script: "ops/geometry.py".into(),
        code: vec!["ops/geometry.py".into()],
        inputs: vec![],
        params: BTreeMap::new(),
        outputs: vec![OutputFile {
            path: "triangle.glb".into(),
            install_path: None,
            required: true,
        }],
    }
}

#[test]
fn declaration_roundtrips_toml_and_json() {
    let original = declaration();
    assert_eq!(original.schema_version, SCHEMA_VERSION);
    assert_eq!(original.units.len(), 2);
    let encoded = toml::to_string(&original).unwrap();
    assert_eq!(parse_declaration(&encoded).unwrap(), original);
    assert_eq!(
        serde_json::from_str::<Declaration>(&serde_json::to_string(&original).unwrap()).unwrap(),
        original
    );
    assert!(matches!(
        &original.units[0].inputs[1],
        Input::Reference {
            producer: Some(_),
            ..
        }
    ));
}

#[test]
fn result_roundtrip_keeps_input_key_and_output_content_distinct() {
    let unit = declaration().units.remove(0);
    let record = ResultRecord {
        schema_version: RESULT_SCHEMA_VERSION,
        unit: unit.id.clone(),
        key: "input-key".into(),
        ingredients: IdentityIngredients {
            cache_version: "1".into(),
            op: unit.op,
            script: unit.script,
            code: BTreeMap::new(),
            worker_version: "1".into(),
            worker_digest: "worker-code".into(),
            validator_version: "1".into(),
            validator_digest: "validator-code".into(),
            params: unit.params,
            content: BTreeMap::new(),
            references: BTreeMap::new(),
            staged_inputs: BTreeMap::new(),
            input_kinds: BTreeMap::new(),
            logical_outputs: unit.outputs.clone(),
        },
        outputs: vec![StoredItem {
            item: unit.outputs[0].clone(),
            files: vec![StoredFile {
                path: "triangle.glb".into(),
                digest: "output-bytes".into(),
                size: 12,
                mode: 0o644,
            }],
            external_locator: None,
        }],
        provenance: Provenance {
            checkout: "fixture-checkout".into(),
            branch: "main".into(),
            commit: "fixture-commit".into(),
            dirty: true,
            built_at: "fixture-time".into(),
        },
    };
    let encoded = serde_json::to_value(&record).unwrap();
    assert_eq!(encoded["schema_version"], RESULT_SCHEMA_VERSION);
    assert_eq!(encoded["outputs"][0]["files"][0]["mode"], 0o644);
    assert!(encoded["ingredients"].get("provenance").is_none());
    assert_eq!(encoded["key"], "input-key");
    assert_eq!(encoded["outputs"][0]["files"][0]["digest"], "output-bytes");
    assert_eq!(
        serde_json::from_value::<ResultRecord>(encoded).unwrap(),
        record
    );
}

#[test]
fn declaration_rejects_unknown_shape_but_defers_semantics() {
    assert!(
        parse_declaration("schema_version=1\ncache_version='1'\nunits=[]\nmisspelled=true")
            .is_err()
    );
    let mut value = serde_json::to_value(declaration()).unwrap();
    value["units"][0]["inputs"][0]["typo"] = true.into();
    assert!(serde_json::from_value::<Declaration>(value).is_err());
    // The loader/validator track, not deserialization, owns unsupported versions.
    assert!(parse_declaration("schema_version=999\ncache_version='1'\nunits=[]").is_ok());
}

#[test]
fn mock_returns_multiple_files_then_scripted_failure_and_refuses_extra_work() {
    let mut worker = MockWorker::new([
        MockStep {
            expected_unit: "sample.geometry".into(),
            result: Ok(vec![
                FixtureFile {
                    path: "triangle.glb".into(),
                    bytes: vec![1, 2],
                },
                FixtureFile {
                    path: "plan.json".into(),
                    bytes: b"{}".to_vec(),
                },
            ]),
        },
        MockStep {
            expected_unit: "sample.geometry".into(),
            result: Err(WorkerFailure {
                kind: FailureKind::Crash,
                message: "scripted crash".into(),
            }),
        },
    ]);
    let request = job();
    assert_eq!(
        worker.run(&request).unwrap().files,
        ["triangle.glb", "plan.json"]
    );
    assert_eq!(worker.produced()[0].1[0].bytes, [1, 2]);
    assert_eq!(worker.run(&request).unwrap_err().kind, FailureKind::Crash);
    assert!(worker.is_exhausted());
    assert_eq!(
        worker.run(&request).unwrap_err().kind,
        FailureKind::Protocol
    );
    assert_eq!(worker.calls().len(), 3);
    assert_eq!(worker.produced().len(), 1);
}

#[test]
fn mock_refuses_out_of_order_job() {
    let mut worker = MockWorker::new([MockStep {
        expected_unit: "other".into(),
        result: Ok(vec![]),
    }]);
    assert_eq!(worker.run(&job()).unwrap_err().kind, FailureKind::Protocol);
    assert!(worker.produced().is_empty());
}

#[test]
fn run_job_roundtrips_without_asset_payloads() {
    let request = Request::Run { job: job() };
    let mut bytes = vec![];
    write_frame(&mut bytes, &request).unwrap();
    assert_eq!(
        read_frame::<_, Request>(&mut std::io::Cursor::new(bytes)).unwrap(),
        Some(request)
    );
}

#[test]
fn optional_inputs_sidecars_and_install_mapping_are_representable() {
    let source = ContentSource::File {
        path: "block.override.json".into(),
        selector: None,
        optional: true,
    };
    assert_eq!(
        serde_json::from_value::<ContentSource>(serde_json::to_value(&source).unwrap()).unwrap(),
        source
    );
    let absent = serde_json::to_value(ContentIdentity::Absent {}).unwrap();
    let empty = serde_json::to_value(ContentIdentity::Digest {
        digest: "empty-file-hash".into(),
    })
    .unwrap();
    assert_ne!(absent, empty);
    let file = OutputFile {
        path: "mesh.uexp".into(),
        install_path: Some("Content/Meshes/mesh.uexp".into()),
        required: false,
    };
    assert_eq!(
        serde_json::from_value::<OutputFile>(serde_json::to_value(&file).unwrap()).unwrap(),
        file
    );
    let example = declaration();
    assert!(example.units[1].outputs[0].files[0].required);
    assert_eq!(
        example.units[1].outputs[0].files[0].install_path.as_deref(),
        Some("Content/Data/plain.json")
    );
}

#[test]
fn absent_identity_refuses_unknown_fields() {
    assert!(
        serde_json::from_str::<ContentIdentity>(r#"{"state":"absent","digest":"unexpected"}"#)
            .is_err()
    );
}
