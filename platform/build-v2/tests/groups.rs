use atelier_build_v2::{groups::*, schema::StoredFile, source_hashes::sha256};

fn contract() -> OutputGroupContract {
    OutputGroupContract {
        id: "geometry".into(),
        root: "geometry".into(),
        root_param: "output_root".into(),
        manifest: "plan.json".into(),
        adapter_version: "d2.mesh-plan/1".into(),
        parent: "Village_Edges".into(),
        encoding: PlanEncoding::MeshIr,
        class: "GeometryPayload".into(),
        logical_namespace: "/Internal/Plans/Village_Edges".into(),
        max_pieces: 1024,
        max_manifest_bytes: 4 * 1024 * 1024,
        max_member_bytes: 128 * 1024 * 1024,
        max_total_bytes: 1024 * 1024 * 1024,
    }
}
fn files(bytes: &[u8]) -> Vec<StoredFile> {
    vec![
        StoredFile {
            path: "plan.json".into(),
            digest: sha256(bytes),
            size: bytes.len() as u64,
            mode: 0o644,
        },
        StoredFile {
            path: "Village_Edges.npz".into(),
            digest: "020a2216fd56fea8992dec94acc335b33704a3c8464c9e8691ab4909272cc539".into(),
            size: 138217,
            mode: 0o644,
        },
    ]
}
fn real_plan() -> &'static [u8] {
    include_bytes!("../examples/plans/village_edges.plan.json")
}
fn parsed(
    value: &serde_json::Value,
    contract: &OutputGroupContract,
    files: &[StoredFile],
) -> Result<PlanRoster, String> {
    let bytes = serde_json::to_vec(value).unwrap();
    let mut files = files.to_vec();
    files[0].digest = sha256(&bytes);
    files[0].size = bytes.len() as u64;
    parse_manifest(contract, &bytes, &files)
}

#[test]
fn retained_plan_maps_exact_flat_membership_without_geometry_reinterpretation() {
    assert_eq!(
        sha256(real_plan()),
        "eb4841549dd0be004afcc4f268867933dd5c0e2075ada34d1fd388372e911697"
    );
    let roster = parse_manifest(&contract(), real_plan(), &files(real_plan())).unwrap();
    assert_eq!(roster.stored().projections.len(), 1);
    assert_eq!(
        roster.stored().projections["Village_Edges"].payload,
        "Village_Edges.npz"
    );
    assert_eq!(roster.raw()["source_collision_hulls"], 89);
    assert_eq!(roster.raw()["pieces"][0]["triangles"], 7860);
    // This is actual plan metadata plus an exact retained payload identity, not native validation.
}

#[test]
fn fixed_and_group_roots_have_one_owner_under_shared_path_policy() {
    let group = contract();
    validate_ownership(&[group.clone()], &["queries/edges.json".into()]).unwrap();
    for fixed in [
        "geometry",
        "geometry/plan.json",
        "GEOMETRY/Village_Edges.npz",
    ] {
        assert!(validate_ownership(&[group.clone()], &[fixed.into()]).is_err());
    }
    let mut other = group.clone();
    other.id = "other".into();
    other.root = "geometry/child".into();
    assert!(validate_ownership(&[group.clone(), other], &[]).is_err());
    let mut first = group.clone();
    first.root = "Café".into();
    let mut second = group;
    second.id = "other".into();
    second.root = "Cafe\u{301}".into();
    assert!(validate_ownership(&[first, second], &[]).is_err());
}

#[test]
fn malformed_foreign_or_incomplete_discovery_refuses() {
    let value: serde_json::Value = serde_json::from_slice(real_plan()).unwrap();
    for (field, replacement) in [
        ("schema", serde_json::json!(2)),
        ("complete", serde_json::json!(false)),
        ("parent", serde_json::json!("Other")),
        ("triangle_limit", serde_json::json!(32769)),
        ("source_triangles", serde_json::json!(7859)),
        ("pieces", serde_json::json!([])),
    ] {
        let mut changed = value.clone();
        changed[field] = replacement;
        assert!(
            parsed(&changed, &contract(), &files(real_plan())).is_err(),
            "{field}"
        );
    }
    for (field, replacement) in [
        ("triangles", serde_json::json!(32769)),
        ("triangles", serde_json::json!(0)),
        ("name", serde_json::json!("../escape")),
        ("payload", serde_json::json!("other.npz")),
        ("sha256", serde_json::json!("a".repeat(64))),
        ("collision_hulls", serde_json::json!(88)),
    ] {
        let mut changed = value.clone();
        changed["pieces"][0][field] = replacement;
        assert!(
            parsed(&changed, &contract(), &files(real_plan())).is_err(),
            "{field}"
        );
    }
}

#[test]
fn missing_extra_alias_members_and_invalid_modes_refuse() {
    let base = files(real_plan());
    assert!(parse_manifest(&contract(), real_plan(), &base[..1]).is_err());
    for path in [
        "foreign.bin",
        "VILLAGE_EDGES.NPZ",
        "Village_Edges.npz/child",
        "../escape",
    ] {
        let mut changed = base.clone();
        let mut extra = changed[1].clone();
        extra.path = path.into();
        changed.push(extra);
        assert!(
            parse_manifest(&contract(), real_plan(), &changed).is_err(),
            "{path}"
        );
    }
    let mut changed = base;
    changed[1].mode = 0o777;
    assert!(parse_manifest(&contract(), real_plan(), &changed).is_err());
}

#[test]
fn declared_limits_and_payload_encoding_are_enforced() {
    let mut group = contract();
    group.max_manifest_bytes = 1;
    assert!(parse_manifest(&group, real_plan(), &files(real_plan())).is_err());
    let mut group = contract();
    group.max_member_bytes = 100000;
    group.max_manifest_bytes = 50000;
    assert!(parse_manifest(&group, real_plan(), &files(real_plan())).is_err());
    let mut group = contract();
    group.max_total_bytes = 150000;
    group.max_member_bytes = 140000;
    group.max_manifest_bytes = 50000;
    assert!(parse_manifest(&group, real_plan(), &files(real_plan())).is_err());
    let mut group = contract();
    group.encoding = PlanEncoding::EncodedGlb;
    assert!(parse_manifest(&group, real_plan(), &files(real_plan())).is_err());
    let mut group = contract();
    group.max_pieces = 0;
    assert!(parse_manifest(&group, real_plan(), &files(real_plan())).is_err());
}

#[test]
fn group_root_must_match_explicit_keyed_worker_param() {
    let group = contract();
    let mut params = std::collections::BTreeMap::from([(
        "output_root".into(),
        serde_json::json!("output/geometry"),
    )]);
    group.validate_root_param(&params).unwrap();
    params.insert("output_root".into(), serde_json::json!("geometry"));
    assert!(group.validate_root_param(&params).is_err());
    params.clear();
    assert!(group.validate_root_param(&params).is_err());
}

#[cfg(target_os = "macos")]
#[test]
fn source_validator_reads_the_same_frozen_objects_and_failure_issues_no_token() {
    use atelier_build_v2::store::ObjectStore;
    use std::{collections::BTreeMap, fs, io::Read, path::PathBuf};
    struct Workspace(PathBuf);
    impl Drop for Workspace {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
    let root = std::env::temp_dir().join(format!(
        "atelier-v2-groups-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir(&root).unwrap();
    let workspace = Workspace(root);
    let store = ObjectStore::open(workspace.0.join("store")).unwrap();
    let payload = b"opaque fixture payload";
    let plan = serde_json::json!({"schema":1,"parent":"Village_Edges","complete":true,"triangle_limit":32768,
        "source_triangles":3,"source_collision_hulls":0,"pieces":[{"name":"Village_Edges","payload":"Village_Edges.npz",
        "sha256":sha256(payload),"triangles":3,"collision_hulls":0}]});
    fs::write(workspace.0.join("payload"), payload).unwrap();
    fs::write(workspace.0.join("plan"), serde_json::to_vec(&plan).unwrap()).unwrap();
    let frozen_payload = store.prepare(workspace.0.join("payload")).unwrap();
    let frozen_plan = store.prepare(workspace.0.join("plan")).unwrap();
    fs::write(workspace.0.join("payload"), b"changed live source").unwrap();
    let objects = BTreeMap::from([
        ("Village_Edges.npz".into(), &frozen_payload),
        ("plan.json".into(), &frozen_plan),
    ]);
    assert!(
        validate_frozen(&contract(), &objects, |_, _| Err(
            "source validator refused".into()
        ))
        .is_err()
    );
    let token = validate_frozen(&contract(), &objects, |roster, members| {
        assert_eq!(roster.raw()["source_triangles"], 3);
        let mut bytes = Vec::new();
        members["Village_Edges.npz"]
            .reader()
            .unwrap()
            .read_to_end(&mut bytes)
            .unwrap();
        assert_eq!(bytes, payload);
        Ok(())
    })
    .unwrap();
    assert_eq!(
        token.project("Village_Edges").unwrap().files[0].digest,
        sha256(payload)
    );
    assert!(token.project("missing").is_err());
    assert_eq!(
        fs::read(workspace.0.join("payload")).unwrap(),
        b"changed live source"
    );
}

#[test]
fn encoded_discovery_keeps_roles_and_complete_render_collision_totals() {
    let mut group = contract();
    group.parent = "Encoded".into();
    group.encoding = PlanEncoding::EncodedGlb;
    let value = serde_json::json!({"schema":1,"kind":"encoded_glb","parent":"Encoded","complete":true,"triangle_limit":32768,
        "source_triangles":12,"source_render_triangles":8,"source_collision_triangles":4,"pieces":[
        {"name":"Render","payload":"Render.mesh","sha256":"a".repeat(64),"triangles":8,"role":"render","bounds":[[0,0,0],[1,1,1]]},
        {"name":"Collision","payload":"Collision.mesh","sha256":"b".repeat(64),"triangles":4,"role":"collision","bounds":[[0,0,0],[1,1,1]]}]});
    let bytes = serde_json::to_vec(&value).unwrap();
    let members = vec![
        StoredFile {
            path: "plan.json".into(),
            digest: sha256(&bytes),
            size: bytes.len() as u64,
            mode: 0o644,
        },
        StoredFile {
            path: "Render.mesh".into(),
            digest: "a".repeat(64),
            size: 1,
            mode: 0o644,
        },
        StoredFile {
            path: "Collision.mesh".into(),
            digest: "b".repeat(64),
            size: 1,
            mode: 0o644,
        },
    ];
    let roster = parse_manifest(&group, &bytes, &members).unwrap();
    assert_eq!(roster.stored().projections.len(), 2);
    assert_eq!(
        roster.stored().projections["Render"].role,
        Some(EncodedRole::Render)
    );
    assert_eq!(
        roster.stored().projections["Collision"].role,
        Some(EncodedRole::Collision)
    );
    for field in ["source_render_triangles", "source_collision_triangles"] {
        let mut changed = value.clone();
        changed[field] = 9.into();
        assert!(parsed(&changed, &group, &members).is_err());
    }
    let mut changed = value;
    changed["pieces"][1]["role"] = "unknown".into();
    assert!(parsed(&changed, &group, &members).is_err());
}
