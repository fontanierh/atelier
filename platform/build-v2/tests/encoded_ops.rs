//! Fixed encoded-source contracts; actual project export execution is separate evidence.
use atelier_build_v2::{encoded_ops::*, source_hashes::sha256, validate::*};
use serde_json::json;
use std::collections::BTreeMap;

#[test]
fn receipt_requires_exact_selected_packet_glb_role_owner_and_bounded_facts() {
    let glb = sha256(b"original GLB");
    let packet = sha256(b"selected .mesh packet");
    let value = json!({"schema":1,"asset":"Piece","primary":"Piece.glb","sha256":glb,
      "triangles":8,"bounds":[[0,0,0],[1,1,1]],"metadata":{"geometry_sha256":glb,"payload_sha256":packet,"role":"render"}});
    validate_receipt(&value, "Piece", "Piece.glb", &glb, &packet, "render").unwrap();
    for path in [
        "/asset",
        "/primary",
        "/sha256",
        "/metadata/geometry_sha256",
        "/metadata/payload_sha256",
        "/metadata/role",
    ] {
        let mut bad = value.clone();
        *bad.pointer_mut(path).unwrap() = "foreign".into();
        assert!(
            validate_receipt(&bad, "Piece", "Piece.glb", &glb, &packet, "render").is_err(),
            "{path}"
        );
    }
    for count in [0, 32769] {
        let mut bad = value.clone();
        bad["triangles"] = count.into();
        assert!(validate_receipt(&bad, "Piece", "Piece.glb", &glb, &packet, "render").is_err());
    }
    let mut bad = value;
    bad["bounds"][0][0] = "unknown".into();
    assert!(validate_receipt(&bad, "Piece", "Piece.glb", &glb, &packet, "render").is_err());
}
#[test]
fn fixed_encoded_decoder_identity_and_registry_bind_actual_required_code() {
    let snapshot: SourceSnapshot = CODE
        .into_iter()
        .map(|name| {
            (
                name.into(),
                SnapshotEntry::File(format!("declared {name}").into_bytes()),
            )
        })
        .collect();
    let expected = identity(&snapshot).unwrap();
    for name in CODE {
        let mut changed = snapshot.clone();
        changed.insert(name.into(), SnapshotEntry::File(b"changed".to_vec()));
        assert_ne!(identity(&changed).unwrap().digest, expected.digest);
        changed.remove(name);
        assert!(identity(&changed).is_err());
    }
    let mut registry = BTreeMap::new();
    register(&mut registry);
    let spec = &registry[&(KIND.into(), "1".into())];
    assert_eq!(spec.inputs.len(), 1);
    assert!(spec.inputs["payload"].required);
    assert!(!spec.inputs["payload"].allow_absent_file);
    assert_eq!(
        spec.output_classes.iter().cloned().collect::<Vec<_>>(),
        vec!["StaticMeshSource"]
    );
}
