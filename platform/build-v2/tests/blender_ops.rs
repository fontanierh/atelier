//! D2 contract/identity facts only. These are not real Blender or APFS execution proof.
use atelier_build_v2::{
    blender_ops::*, groups::*, keys::*, schema::*, source_hashes::*, validate::*,
};
use std::collections::{BTreeMap, BTreeSet};

fn group() -> OutputGroupContract {
    OutputGroupContract {
        id: "geometry".into(),
        root: "geometry".into(),
        root_param: "output_root".into(),
        manifest: "plan.json".into(),
        adapter_version: "d2.mesh-plan/1".into(),
        parent: "Whole".into(),
        encoding: PlanEncoding::MeshIr,
        class: MESH_PAYLOAD_CLASS.into(),
        logical_namespace: "/Internal/Whole".into(),
        max_pieces: 16,
        max_manifest_bytes: 1024 * 1024,
        max_member_bytes: MAX_MESH_IR_BYTES,
        max_total_bytes: 512 * 1024 * 1024,
    }
}
fn output(id: &str) -> Item {
    Item {
        id: "asset".into(),
        logical_path: format!("/Sources/{id}"),
        class: MESH_EXPORT_CLASS.into(),
        destination: Destination::Store,
        files: vec![
            OutputFile {
                path: "asset.fbx".into(),
                install_path: None,
                required: true,
            },
            OutputFile {
                path: "export.json".into(),
                install_path: None,
                required: true,
            },
        ],
    }
}
fn payload(id: &str) -> Item {
    Item {
        id: id.into(),
        logical_path: format!("/Internal/{id}"),
        class: MESH_PAYLOAD_CLASS.into(),
        destination: Destination::Store,
        files: vec![OutputFile {
            path: format!("{id}.npz"),
            install_path: None,
            required: true,
        }],
    }
}
fn prepared(planner_code: &[u8], a: &[u8], b: &[u8]) -> (PreparedUnit, PreparedUnit, PreparedUnit) {
    let producer = Unit {
        id: "plan".into(),
        op: Op {
            kind: "fixture".into(),
            version: "1".into(),
        },
        script: "plan.py".into(),
        code: vec!["plan.py".into()],
        inputs: vec![],
        params: BTreeMap::new(),
        outputs: vec![payload("A"), payload("B")],
        output_groups: vec![],
        conditional: None,
    };
    let child = |id: &str| Unit {
        id: id.into(),
        op: Op {
            kind: BLENDER_EXPORT_KIND.into(),
            version: BLENDER_OP_VERSION.into(),
        },
        script: "export.py".into(),
        code: std::iter::once("export.py".to_string())
            .chain(
                blender_code_files(BLENDER_EXPORT_KIND)
                    .unwrap()
                    .into_iter()
                    .map(str::to_owned),
            )
            .collect(),
        conditional: None,
        output_groups: vec![],
        inputs: vec![Input::Content {
            name: "payload".into(),
            source: ContentSource::Item {
                unit: "plan".into(),
                item: id.into(),
            },
            whole: None,
            conditional: None,
        }],
        params: BTreeMap::from([
            ("format".into(), "fbx".into()),
            ("payload_member".into(), format!("{id}.npz").into()),
            ("payload_encoding".into(), "mesh_ir".into()),
            ("payload_role".into(), "geometry".into()),
        ]),
        outputs: vec![output(id)],
    };
    let declaration = Declaration {
        schema_version: SCHEMA_VERSION,
        cache_version: "1".into(),
        units: vec![producer, child("A"), child("B")],
    };
    let mut registry = BTreeMap::from([(
        ("fixture".into(), "1".into()),
        OpDefinition {
            inputs: BTreeMap::new(),
            output_classes: BTreeSet::from([MESH_PAYLOAD_CLASS.into()]),
            params: BTreeMap::new(),
        },
    )]);
    BlenderExportSpec::default()
        .register(&mut registry)
        .unwrap();
    let mut snapshot = BTreeMap::from([
        ("plan.py".into(), SnapshotEntry::File(planner_code.to_vec())),
        (
            "export.py".into(),
            SnapshotEntry::File(b"declared exporter".to_vec()),
        ),
    ]);
    for path in blender_code_files(BLENDER_EXPORT_KIND).unwrap() {
        snapshot.insert(
            path.into(),
            SnapshotEntry::File(b"declared helper".to_vec()),
        );
    }
    let validated = validate(&declaration, &registry, &snapshot, &[]).unwrap();
    let produced = [("A", a), ("B", b)]
        .into_iter()
        .map(|(id, bytes)| {
            (
                ("plan".into(), id.into()),
                StoredItem {
                    item: payload(id),
                    files: vec![StoredFile {
                        path: format!("{id}.npz"),
                        digest: sha256(bytes),
                        size: bytes.len() as u64,
                        mode: 0o644,
                    }],
                    external_locator: None,
                },
            )
        })
        .collect();
    let worker = ImplementationIdentity {
        version: atelier_build_v2::launch::BLENDER_JOB_LOOP_VERSION.into(),
        digest: sha256(b"frozen worker"),
    };
    let validator = blender_validator_identity(&snapshot).unwrap();
    let prepare_one = |id: &str| {
        prepare(
            &declaration,
            &validated,
            id,
            &KeyContext {
                snapshot: &snapshot,
                versions: &BTreeMap::new(),
                produced: &produced,
                produced_groups: &BTreeMap::new(),
                staged_inputs: &if id == "plan" {
                    BTreeMap::new()
                } else {
                    BTreeMap::from([("payload".into(), "inputs/payload".into())])
                },
                worker: &worker,
                validator: &validator,
            },
            &mut SourceHashCache::default(),
        )
        .unwrap()
    };
    (prepare_one("plan"), prepare_one("A"), prepare_one("B"))
}

#[test]
fn selected_payload_keys_cut_off_planner_and_sibling_changes_without_group_authority_forgery() {
    let (plan, a, b) = prepared(b"planner1", b"pieceA", b"pieceB");
    let (changed_plan, same_a, same_b) = prepared(b"planner2", b"pieceA", b"pieceB");
    assert_ne!(plan.key(), changed_plan.key());
    assert_eq!(a.key(), same_a.key());
    assert_eq!(b.key(), same_b.key());
    let (_, changed_a, unchanged_b) = prepared(b"planner2", b"new pieceA", b"pieceB");
    assert_ne!(a.key(), changed_a.key());
    assert_eq!(b.key(), unchanged_b.key());
    BlenderExportSpec::default()
        .validate_ingredients(a.ingredients())
        .unwrap();
    assert_eq!(selected_payload(&a).unwrap().digest, sha256(b"pieceA"));
    let validator = ImplementationIdentity {
        version: a.ingredients().validator_version.clone(),
        digest: a.ingredients().validator_digest.clone(),
    };
    check_blender_identity(&a, BLENDER_EXPORT_KIND, &validator).unwrap();
    let unrelated = ImplementationIdentity {
        version: BLENDER_VALIDATOR_VERSION.into(),
        digest: sha256(b"unrelated claim"),
    };
    assert!(check_blender_identity(&a, BLENDER_EXPORT_KIND, &unrelated).is_err());

    // This establishes selected Item key semantics. Dynamic group expansion itself reuses A4b;
    // no available ValidatedGroup or runtime publication token is manufactured by this fixture.
}

#[test]
fn planner_contract_reserves_worker_visible_root_parent_and_bounds() {
    let spec = BlenderPlanSpec::new(group());
    let (_, a, _) = prepared(b"planner", b"A", b"B");
    let mut i = a.ingredients().clone();
    i.logical_outputs.clear();
    i.output_groups = vec![group()];
    i.params = BTreeMap::from([
        ("output_root".into(), "output/geometry".into()),
        ("parent".into(), "Whole".into()),
        (
            "plan_limits".into(),
            serde_json::json!({"max_pieces":16,"max_manifest_bytes":1024*1024,
            "max_member_bytes":MAX_MESH_IR_BYTES,"max_total_bytes":512*1024*1024}),
        ),
    ]);
    spec.validate_ingredients(&i).unwrap();
    i.params.insert("parent".into(), "Foreign".into());
    assert!(spec.validate_ingredients(&i).is_err());
    i.params.insert("parent".into(), "Whole".into());
    i.params.get_mut("plan_limits").unwrap()["max_pieces"] = 17.into();
    assert!(spec.validate_ingredients(&i).is_err());
    let mut invalid = spec.clone();
    invalid.group.encoding = PlanEncoding::MeshSet;
    assert!(invalid.definition().is_ok());
    invalid.group.encoding = PlanEncoding::EncodedGlb;
    assert!(invalid.definition().is_err());
    invalid = spec.clone();
    invalid.group.max_member_bytes = MAX_MESH_IR_BYTES + 1;
    assert!(invalid.definition().is_err());
    invalid = spec;
    invalid.params.insert(
        "output_root".into(),
        ParamRule {
            kind: ParamKind::String,
            required: true,
        },
    );
    assert!(invalid.definition().is_err());
}

#[test]
fn piece_contract_refuses_broad_extra_inputs_wrong_roles_formats_and_incomplete_auxiliary_sets() {
    let (_, unit, _) = prepared(b"planner", b"A", b"B");
    let spec = BlenderExportSpec::default();
    let mut mesh_set = unit.ingredients().clone();
    mesh_set
        .params
        .insert("payload_encoding".into(), "mesh_set".into());
    mesh_set.params.insert(
        "payload_metadata".into(),
        serde_json::json!({"collision":true}),
    );
    assert!(spec.validate_ingredients(&mesh_set).is_ok());
    let mut glb = unit.ingredients().clone();
    glb.params.insert("format".into(), "glb".into());
    glb.logical_outputs[0].files[0].path = "asset.glb".into();
    assert!(spec.validate_ingredients(&glb).is_ok());
    glb.params.insert("format".into(), "fbx".into());
    assert!(spec.validate_ingredients(&glb).is_err());
    for (field, value) in [
        ("format", "glb"),
        ("payload_encoding", "encoded_glb"),
        ("payload_role", "collision"),
    ] {
        let mut i = unit.ingredients().clone();
        i.params.insert(field.into(), value.into());
        assert!(spec.validate_ingredients(&i).is_err());
    }
    let mut i = unit.ingredients().clone();
    i.content.insert(
        "roster".into(),
        ContentIdentity::Digest {
            digest: sha256(b"whole roster"),
        },
    );
    assert!(spec.validate_ingredients(&i).is_err());
    let mut item = output("A");
    item.files.pop();
    assert!(validate_export_item(&item).is_err());
    item = output("A");
    item.files[1].required = false;
    assert!(validate_export_item(&item).is_err());
    item = output("A");
    item.files[0].path = "../A.fbx".into();
    assert!(validate_export_item(&item).is_err());
    item = output("A");
    item.destination = Destination::Checkout;
    assert!(validate_export_item(&item).is_err());
}

fn plan_metadata() -> serde_json::Value {
    serde_json::json!({"schema":1,"parent":"Whole","complete":true,"triangle_limit":32768,"source_triangles":2,
        "source_polygons":2,"source_collision_hulls":1,"collision_owner":"Whole_A","partition":"logical",
        "slots":["One","Two"],"matrix":[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]],
        "pieces":[{"name":"Whole_A","payload":"Whole_A.npz","sha256":sha256(b"A"),"triangles":1,"collision_hulls":1,
            "polygons":1,"source_faces":[0],"slots":["One"],"source_material_indices":[0],"min":[0,0,0],"max":[1,1,0]},
            {"name":"Whole_B","payload":"Whole_B.npz","sha256":sha256(b"B"),"triangles":1,"collision_hulls":0,
            "polygons":1,"source_faces":[1],"slots":["Two"],"source_material_indices":[1],"min":[2,0,0],"max":[3,1,0]}]})
}

#[test]
fn frozen_metadata_conserves_faces_material_mapping_collision_owner_and_finite_bounds() {
    let value = plan_metadata();
    let raw = serde_json::to_vec(&value).unwrap();
    parse_blender_plan_metadata(&raw, 1024 * 1024).unwrap();
    let text = String::from_utf8(raw).unwrap();
    for (from, to) in [
        ("\"schema\":1", "\"schema\":1,\"schema\":1"),
        (
            "\"name\":\"Whole_A\"",
            "\"name\":\"Whole_A\",\"name\":\"Whole_A\"",
        ),
    ] {
        assert!(
            parse_blender_plan_metadata(text.replacen(from, to, 1).as_bytes(), 1024 * 1024)
                .is_err()
        );
    }
    for field in ["unknown", "role"] {
        let mut bad = value.clone();
        bad["pieces"][0][field] = "collision".into();
        assert!(validate_plan_metadata(&bad).is_err());
    }
    let mut bad = value.clone();
    bad["unknown_policy"] = true.into();
    assert!(validate_plan_metadata(&bad).is_err());
    validate_plan_metadata(&value).unwrap();
    for fault in 0..5 {
        let mut broken = value.clone();
        match fault {
            0 => broken["pieces"][1]["source_faces"] = serde_json::json!([0]),
            1 => broken["pieces"][1]["source_material_indices"] = serde_json::json!([0]),
            2 => broken["collision_owner"] = "Whole_B".into(),
            3 => broken["pieces"][0]["min"] = serde_json::json!([2, 0, 0]),
            _ => broken["partition"] = "whole".into(),
        }
        assert!(validate_plan_metadata(&broken).is_err(), "fault {fault}");
    }
}

#[test]
fn validator_identity_binds_frozen_decoder_bytes_and_versions_but_not_installed_platform() {
    let mut snapshot: SourceSnapshot = DECODER_FILES
        .into_iter()
        .map(|p| (p.into(), SnapshotEntry::File(b"decoder".to_vec())))
        .collect();
    let first = blender_validator_identity(&snapshot).unwrap();
    snapshot.insert(
        "uv.lock".into(),
        SnapshotEntry::File(b"new installed dependency resolution".to_vec()),
    );
    assert_eq!(
        first.digest,
        blender_validator_identity(&snapshot).unwrap().digest
    );
    snapshot.insert(
        DECODER_FILES[3].into(),
        SnapshotEntry::File(b"changed decoder implementation".to_vec()),
    );
    assert_ne!(
        first.digest,
        blender_validator_identity(&snapshot).unwrap().digest
    );
    snapshot.insert(DECODER_FILES[3].into(), SnapshotEntry::Symlink);
    assert!(blender_validator_identity(&snapshot).is_err());
}

#[test]
fn receipt_binding_uses_selected_output_content_digest_and_complete_fixed_ownership() {
    let item = output("A");
    let primary = sha256(b"FBX bytes");
    let payload = sha256(b"selected geometry");
    let value = serde_json::json!({"schema":1,"asset":"A","primary":"asset.fbx","triangles":1,"bounds":[[0,0,0],[1,1,0]],
        "sha256":primary,"metadata":{"geometry_sha256":payload,"slots":["One"],"polygons":1,"collision_hulls":0,"uv_channels":[]}});
    validate_receipt_metadata(&value, &item, "A", &primary, &payload).unwrap();
    assert_eq!(item.id, "asset"); // existing A4b template's stable local output slot
    assert!(validate_receipt_metadata(&value, &item, "AnotherPiece", &primary, &payload).is_err());
    let raw = serde_json::to_vec(&value).unwrap();
    assert_eq!(parse_export_receipt(&raw).unwrap(), value);
    let duplicate =
        String::from_utf8(raw)
            .unwrap()
            .replacen("\"schema\":1", "\"schema\":1,\"schema\":1", 1);
    assert!(parse_export_receipt(duplicate.as_bytes()).is_err());
    assert!(parse_export_receipt(b"[1,2,3]").is_err());

    let mut wrong = value.clone();
    wrong["sha256"] = sha256(b"producer input key").into();
    assert!(validate_receipt_metadata(&wrong, &item, "A", &primary, &payload).is_err());
    wrong = value;
    wrong["metadata"]["foreign"] = "unowned metadata".into();
    assert!(validate_receipt_metadata(&wrong, &item, "A", &primary, &payload).is_err());
}

#[test]
fn explicit_authored_partitions_still_require_complete_disjoint_face_ownership() {
    let mut value = plan_metadata();
    value["partition"] = "explicit".into();
    validate_plan_metadata(&value).unwrap();
    for fault in 0..3 {
        let mut broken = value.clone();
        match fault {
            0 => broken["pieces"][1]["source_faces"] = serde_json::json!([0]),
            1 => broken["pieces"][1]["source_faces"] = serde_json::json!([]),
            _ => broken["partition"] = "implicit".into(),
        }
        assert!(validate_plan_metadata(&broken).is_err(), "fault {fault}");
    }
}

#[test]
fn mesh_set_metadata_preserves_heterogeneous_slots_and_exact_runtime_membership() {
    let mut value = plan_metadata();
    value.as_object_mut().unwrap().remove("partition");
    value.as_object_mut().unwrap().remove("collision_owner");
    value["kind"] = "mesh_set".into();
    value["source_collision_hulls"] = 0.into();
    value["metadata"] =
        serde_json::json!({"Whole_A":{"collision":true},"Whole_B":{"collision":false}});
    value["diagnostics"] = serde_json::json!({"count":2});
    for row in value["pieces"].as_array_mut().unwrap() {
        row.as_object_mut().unwrap().remove("source_faces");
        row.as_object_mut()
            .unwrap()
            .remove("source_material_indices");
        row["collision_hulls"] = 0.into();
    }
    let bytes = serde_json::to_vec(&value).unwrap();
    assert_eq!(
        parse_mesh_set_plan_metadata(&bytes, 1024 * 1024).unwrap(),
        value
    );
    for fault in 0..6 {
        let mut bad = value.clone();
        match fault {
            0 => {
                bad["metadata"].as_object_mut().unwrap().remove("Whole_B");
            }
            1 => bad["slots"] = serde_json::json!(["One"]),
            2 => bad["pieces"][0]["source_faces"] = serde_json::json!([0]),
            3 => bad["pieces"][0]["collision_hulls"] = 1.into(),
            4 => bad["source_polygons"] = 3.into(),
            _ => bad["pieces"][0]["name"] = "Foreign".into(),
        }
        assert!(validate_mesh_set_metadata(&bad).is_err(), "fault {fault}");
    }
}

#[test]
fn selected_policy_receipt_matches_exact_keyed_object_and_types() {
    let item = output("A");
    let primary = sha256(b"FBX bytes");
    let payload = sha256(b"selected geometry");
    let policy =
        serde_json::json!({"collision":true,"lods":false,"material_kinds":{"One":"opaque"}});
    let mut value = serde_json::json!({"schema":1,"asset":"A","primary":"asset.fbx","triangles":1,"bounds":[[0,0,0],[1,1,0]],
        "sha256":primary,"metadata":{"geometry_sha256":payload,"slots":["One"],"polygons":1,"collision_hulls":0,"uv_channels":[],"native_policy":policy}});
    validate_receipt_metadata_with_policy(&value, &item, "A", &primary, &payload, Some(&policy))
        .unwrap();
    parse_export_receipt(&serde_json::to_vec(&value).unwrap()).unwrap();
    assert!(validate_receipt_metadata(&value, &item, "A", &primary, &payload).is_err());
    value["metadata"]["native_policy"]["collision"] = 1.into();
    assert!(
        validate_receipt_metadata_with_policy(
            &value,
            &item,
            "A",
            &primary,
            &payload,
            Some(&policy)
        )
        .is_err()
    );
    value["metadata"]
        .as_object_mut()
        .unwrap()
        .remove("native_policy");
    assert!(
        validate_receipt_metadata_with_policy(
            &value,
            &item,
            "A",
            &primary,
            &payload,
            Some(&policy)
        )
        .is_err()
    );
}
