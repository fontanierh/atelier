use atelier_build_v2::{keys::*, schema::*, source_hashes::*, validate::*};
use std::collections::{BTreeMap, BTreeSet};

struct Fixture {
    declaration: Declaration,
    registry: OpRegistry,
    snapshot: SourceSnapshot,
    versions: SourceVersions,
    staged: BTreeMap<String, String>,
    produced: ProducedItems,
    worker: ImplementationIdentity,
    validator: ImplementationIdentity,
}

impl Fixture {
    fn new() -> Self {
        let declaration = parse_declaration(include_str!("../examples/units.toml")).unwrap();
        let rule = |role, classes| InputRule {
            role,
            required: false,
            allow_absent_file: true,
            allow_selector: true,
            require_whole_reason: false,
            item_classes: classes,
        };
        let registry = BTreeMap::from([(
            ("py_data".into(), "1".into()),
            OpDefinition {
                inputs: BTreeMap::from([
                    (
                        "shape".into(),
                        rule(
                            InputRole::Content,
                            BTreeSet::from(["Material".into(), "StaticMeshSource".into()]),
                        ),
                    ),
                    (
                        "material".into(),
                        rule(InputRole::Reference, BTreeSet::from(["Material".into()])),
                    ),
                ]),
                output_classes: BTreeSet::from(["Material".into(), "StaticMeshSource".into()]),
                params: BTreeMap::from([
                    (
                        "seed".into(),
                        ParamRule {
                            kind: ParamKind::Integer,
                            required: false,
                        },
                    ),
                    (
                        "enabled".into(),
                        ParamRule {
                            kind: ParamKind::Bool,
                            required: false,
                        },
                    ),
                    (
                        "label".into(),
                        ParamRule {
                            kind: ParamKind::String,
                            required: false,
                        },
                    ),
                ]),
            },
        )]);
        let snapshot: SourceSnapshot = BTreeMap::from([
            (
                "ops/geometry.py".into(),
                SnapshotEntry::File(b"geometry".to_vec()),
            ),
            (
                "ops/common.py".into(),
                SnapshotEntry::File(b"common".to_vec()),
            ),
            (
                "ops/material.py".into(),
                SnapshotEntry::File(b"material".to_vec()),
            ),
            (
                "data/shape.json".into(),
                SnapshotEntry::File(br#"{"triangle":[1,2,3],"same":[1,2,3],"unused":0}"#.to_vec()),
            ),
        ]);
        let versions = snapshot
            .iter()
            .enumerate()
            .map(|(index, (path, entry))| {
                let SnapshotEntry::File(bytes) = entry else {
                    unreachable!()
                };
                (
                    path.clone(),
                    FileVersion {
                        device: 1,
                        inode: index as u64 + 1,
                        size: bytes.len() as u64,
                        mtime_ns: 1,
                        ctime_ns: 1,
                    },
                )
            })
            .collect();
        Self {
            declaration,
            registry,
            snapshot,
            versions,
            staged: BTreeMap::from([
                ("shape".into(), "inputs/shape/data.json".into()),
                ("material".into(), "inputs/material/reference.json".into()),
            ]),
            produced: BTreeMap::new(),
            worker: ImplementationIdentity {
                version: "worker-1".into(),
                digest: sha256(b"worker implementation"),
            },
            validator: ImplementationIdentity {
                version: "validator-1".into(),
                digest: sha256(b"validator implementation"),
            },
        }
    }
    fn prepared(&self, cache: &mut SourceHashCache) -> Result<PreparedUnit, String> {
        let validated = validate(
            &self.declaration,
            &self.registry,
            &self.snapshot,
            &["Content".into()],
        )
        .map_err(|error| error.to_string())?;
        prepare(
            &self.declaration,
            &validated,
            &self.declaration.units[0].id,
            &KeyContext {
                snapshot: &self.snapshot,
                versions: &self.versions,
                produced: &self.produced,
                produced_groups: &BTreeMap::new(),
                staged_inputs: &self.staged,
                worker: &self.worker,
                validator: &self.validator,
            },
            cache,
        )
    }
    fn key(&self) -> String {
        self.prepared(&mut SourceHashCache::default())
            .unwrap()
            .key()
            .into()
    }
    fn change(&mut self, path: &str, bytes: &[u8]) {
        self.snapshot
            .insert(path.into(), SnapshotEntry::File(bytes.to_vec()));
        let version = self.versions.get_mut(path).unwrap();
        version.size = bytes.len() as u64;
        version.ctime_ns += 1;
    }
    fn content_item(&mut self) {
        self.declaration.units[0].inputs[0] = Input::Content {
            name: "shape".into(),
            source: ContentSource::Item {
                unit: "sample.material".into(),
                item: "plain".into(),
            },
            whole: None,
            conditional: None,
        };
        self.staged.insert("shape".into(), "inputs/shape".into());
        self.produced.insert(
            ("sample.material".into(), "plain".into()),
            StoredItem {
                item: self.declaration.units[1].outputs[0].clone(),
                files: vec![StoredFile {
                    path: "plain.json".into(),
                    digest: sha256(b"material output"),
                    size: 15,
                    mode: 0o644,
                }],
                external_locator: None,
            },
        );
    }
}

#[test]
fn sha256_and_typed_canonical_encoding_are_unambiguous() {
    assert_eq!(
        sha256(b"hello"),
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    );
    assert_eq!(
        canonical_bytes(&serde_json::json!({"b":2,"a":{"z":0,"x":1}})).unwrap(),
        br#"{"a":{"x":1,"z":0},"b":2}"#
    );
    assert_ne!(
        canonical_bytes(&serde_json::json!({"a":"bc"})).unwrap(),
        canonical_bytes(&serde_json::json!({"ab":"c"})).unwrap()
    );
    assert_ne!(
        canonical_bytes(&serde_json::json!(1)).unwrap(),
        canonical_bytes(&serde_json::json!("1")).unwrap()
    );
}

#[test]
fn declared_code_settings_and_logical_identity_change_keys() {
    let mut fixture = Fixture::new();
    let before = fixture.key();
    fixture.change("ops/common.py", b"common # comment-only edit");
    assert_ne!(before, fixture.key());
    let mut fixture = Fixture::new();
    fixture.change("data/shape.json", br#"{"triangle":[1,2,4]}"#);
    assert_ne!(before, fixture.key());
    let mut fixture = Fixture::new();
    fixture.declaration.units[0]
        .params
        .insert("seed".into(), serde_json::json!(43));
    assert_ne!(before, fixture.key());
    let mut fixture = Fixture::new();
    fixture.declaration.units[0].outputs[0].logical_path = "/Game/Meshes/Other".into();
    assert_ne!(before, fixture.key());
    let mut fixture = Fixture::new();
    fixture.declaration.units[0].outputs[0].id = "other".into();
    assert_ne!(before, fixture.key());
    let mut fixture = Fixture::new();
    fixture.declaration.units[0].script = "ops/common.py".into();
    assert_ne!(before, fixture.key());
}

#[test]
fn explicit_op_cache_worker_and_validator_versions_invalidate() {
    let before = Fixture::new().key();
    let mut fixture = Fixture::new();
    fixture.declaration.cache_version = "v2-2".into();
    assert_ne!(before, fixture.key());
    let mut fixture = Fixture::new();
    let definition = fixture.registry.values().next().unwrap().clone();
    fixture
        .registry
        .insert(("py_data".into(), "2".into()), definition);
    fixture.declaration.units[0].op.version = "2".into();
    assert_ne!(before, fixture.key());
    let mut fixture = Fixture::new();
    fixture.worker.version = "worker-2".into();
    assert_ne!(before, fixture.key());
    let mut fixture = Fixture::new();
    fixture.validator.version = "validator-2".into();
    assert_ne!(before, fixture.key());
    let mut fixture = Fixture::new();
    fixture.worker.digest = sha256(b"new worker code");
    assert_ne!(before, fixture.key());
    let mut fixture = Fixture::new();
    fixture.validator.digest = sha256(b"new validator code");
    assert_ne!(before, fixture.key());
}

#[test]
fn ambient_platform_and_provenance_are_not_implicit_inputs() {
    let mut fixture = Fixture::new();
    let before = fixture.key();
    for path in [
        "uv.lock",
        "installed/python",
        "installed/blender",
        "installed/unreal",
        "installed/xcode-sdk-clang",
        "provenance/checkout-branch-commit-dirty",
    ] {
        fixture.snapshot.insert(
            path.into(),
            SnapshotEntry::File(b"changed ambient evidence".to_vec()),
        );
    }
    assert_eq!(before, fixture.key());
    for version in fixture.versions.values_mut() {
        version.device += 10;
        version.inode += 100;
        version.mtime_ns += 99;
        version.ctime_ns += 99;
    }
    assert_eq!(before, fixture.key());
}

#[test]
fn selector_hashes_only_selected_data_and_preserves_shape() {
    let mut fixture = Fixture::new();
    let before = fixture.key();
    fixture.change(
        "data/shape.json",
        br#"{"triangle":[1,2,3],"same":[1,2,3],"unused":"completely different"}"#,
    );
    assert_eq!(before, fixture.key());
    let Input::Content {
        source: ContentSource::File { selector, .. },
        ..
    } = &mut fixture.declaration.units[0].inputs[0]
    else {
        panic!()
    };
    *selector = Some("/same".into());
    assert_eq!(before, fixture.key());
    let prepared = fixture.prepared(&mut SourceHashCache::default()).unwrap();
    assert_eq!(
        prepared
            .inputs()
            .iter()
            .find(|input| input.wire.name == "shape")
            .unwrap()
            .payload,
        InputPayload::Bytes(b"[1,2,3]".to_vec())
    );
    fixture.change("data/shape.json", br#"{"same":{"0":1,"1":2,"2":3}}"#);
    assert_ne!(before, fixture.key());
}

#[test]
fn locator_rename_keeps_key_but_visible_staged_path_changes_it() {
    let mut fixture = Fixture::new();
    let before = fixture.prepared(&mut SourceHashCache::default()).unwrap();
    let bytes = fixture.snapshot.remove("data/shape.json").unwrap();
    let version = fixture.versions.remove("data/shape.json").unwrap();
    fixture.snapshot.insert("other/renamed.json".into(), bytes);
    fixture
        .versions
        .insert("other/renamed.json".into(), version);
    let Input::Content {
        source: ContentSource::File { path, .. },
        ..
    } = &mut fixture.declaration.units[0].inputs[0]
    else {
        panic!()
    };
    *path = "other/renamed.json".into();
    let after = fixture.prepared(&mut SourceHashCache::default()).unwrap();
    assert_eq!(before.key(), after.key());
    assert_eq!(
        before.request("job", "private-job"),
        after.request("job", "private-job")
    );
    assert!(
        !String::from_utf8(canonical_bytes(&after.request("job", "private-job")).unwrap())
            .unwrap()
            .contains("renamed.json")
    );
    fixture
        .staged
        .insert("shape".into(), "inputs/shape/visible.glb".into());
    assert_ne!(before.key(), fixture.key());
}

#[test]
fn exact_safe_collision_free_slot_mapping_is_required() {
    let mut fixture = Fixture::new();
    fixture.staged.remove("shape");
    assert!(fixture.prepared(&mut SourceHashCache::default()).is_err());
    let mut fixture = Fixture::new();
    fixture.staged.insert("extra".into(), "inputs/extra".into());
    assert!(fixture.prepared(&mut SourceHashCache::default()).is_err());
    for invalid in [
        "/absolute",
        "../escape",
        "a//b",
        "a\\b",
        "C:drive",
        "trailing.",
    ] {
        let mut fixture = Fixture::new();
        fixture.staged.insert("shape".into(), invalid.into());
        assert!(fixture.prepared(&mut SourceHashCache::default()).is_err());
    }
    for (a, b) in [
        ("inputs/Shape", "inputs/shape"),
        ("inputs/Café", "inputs/Cafe\u{301}"),
        ("inputs/shape", "inputs/shape/child"),
    ] {
        let mut fixture = Fixture::new();
        fixture.staged.insert("shape".into(), a.into());
        fixture.staged.insert("material".into(), b.into());
        assert!(fixture.prepared(&mut SourceHashCache::default()).is_err());
    }
    let prepared = Fixture::new()
        .prepared(&mut SourceHashCache::default())
        .unwrap();
    for wire in prepared.request("job", "job-dir").inputs {
        assert_eq!(prepared.ingredients().staged_inputs[&wire.name], wire.path);
    }
}

#[test]
fn optional_absence_differs_from_empty_and_selected_null() {
    let mut fixture = Fixture::new();
    let Input::Content {
        source: ContentSource::File {
            optional, selector, ..
        },
        ..
    } = &mut fixture.declaration.units[0].inputs[0]
    else {
        panic!()
    };
    *optional = true;
    *selector = None;
    fixture.snapshot.remove("data/shape.json");
    fixture.versions.remove("data/shape.json");
    let absent = fixture.key();
    fixture
        .snapshot
        .insert("data/shape.json".into(), SnapshotEntry::File(vec![]));
    let empty = fixture.key();
    assert_ne!(absent, empty);
    fixture.snapshot.insert(
        "data/shape.json".into(),
        SnapshotEntry::File(b"null".to_vec()),
    );
    let Input::Content {
        source: ContentSource::File { selector, .. },
        ..
    } = &mut fixture.declaration.units[0].inputs[0]
    else {
        panic!()
    };
    *selector = Some(String::new());
    let present_null = fixture.key();
    assert_ne!(absent, present_null);
    assert_ne!(empty, present_null);
}

#[test]
fn reference_bytes_and_producer_input_history_do_not_propagate() {
    let mut fixture = Fixture::new();
    fixture.content_item();
    let before = fixture.key();
    // The upstream implementation/input identity changes while its exact result stays unchanged.
    fixture.change("ops/material.py", b"different upstream implementation");
    assert_eq!(before, fixture.key());
    let mut reference_only = Fixture::new();
    let reference_key = reference_only.key();
    reference_only.produced = fixture.produced.clone();
    reference_only.produced.values_mut().next().unwrap().files[0].digest =
        sha256(b"changed referenced material bytes");
    assert_eq!(reference_key, reference_only.key());
    fixture.produced.values_mut().next().unwrap().files[0].digest =
        sha256(b"new actual output bytes");
    assert_ne!(before, fixture.key());
}

#[test]
fn semantic_modes_and_complete_result_membership_are_content() {
    let mut fixture = Fixture::new();
    fixture.content_item();
    let before = fixture.key();
    fixture.produced.values_mut().next().unwrap().files[0].mode = 0o755;
    assert_ne!(before, fixture.key());
    fixture.produced.values_mut().next().unwrap().files[0].mode = 0o777;
    assert!(fixture.prepared(&mut SourceHashCache::default()).is_err());
    fixture.produced.values_mut().next().unwrap().files.clear();
    assert!(fixture.prepared(&mut SourceHashCache::default()).is_err());
    assert_eq!(normalized_mode(0o600), 0o644);
    assert_eq!(normalized_mode(0o710), 0o755);
}

#[test]
fn declaration_order_and_dispatch_metadata_do_not_change_semantic_request() {
    let mut fixture = Fixture::new();
    let before = fixture.prepared(&mut SourceHashCache::default()).unwrap();
    fixture.declaration.units[0].inputs.reverse();
    fixture.declaration.units[0].code.reverse();
    fixture.declaration.units[0].id = "renamed.scheduler.label".into();
    let after = fixture.prepared(&mut SourceHashCache::default()).unwrap();
    assert_eq!(before.key(), after.key());
    let mut a = serde_json::to_value(before.request("job-a", "checkout-a/private-job")).unwrap();
    let mut b = serde_json::to_value(after.request("job-b", "checkout-b/private-job")).unwrap();
    for field in ["job_id", "job_dir", "unit"] {
        a.as_object_mut().unwrap().remove(field);
        b.as_object_mut().unwrap().remove(field);
    }
    assert_eq!(a, b); // Encoding/Run mapping only: C1 must prove semantic output independence.
}

#[test]
fn source_version_memo_reuses_hashes_and_same_size_mtime_edit_invalidates() {
    let mut cache = SourceHashCache::default();
    let mut version = FileVersion {
        device: 1,
        inode: 7,
        size: 3,
        mtime_ns: 50,
        ctime_ns: 1,
    };
    let old = cache.digest(Some(&version), b"one").unwrap();
    assert_eq!(cache.digest(Some(&version), b"one").unwrap(), old);
    assert_eq!(cache.stats.versions_hashed, 1);
    assert_eq!(cache.stats.memo_hits, 1);
    version.ctime_ns += 1;
    let new = cache.digest(Some(&version), b"two").unwrap();
    assert_ne!(old, new);
    assert_eq!(cache.stats.versions_hashed, 2);
    assert!(cache.digest(Some(&version), b"longer").is_err());
    let fixture = Fixture::new();
    let mut cache = SourceHashCache::default();
    fixture.prepared(&mut cache).unwrap();
    let stats = cache.stats.clone();
    fixture.prepared(&mut cache).unwrap();
    assert_eq!(cache.stats.versions_hashed, stats.versions_hashed);
    assert_eq!(cache.stats.memo_hits, 3);
}

#[test]
fn damaged_or_missing_hash_indexes_fall_back_to_source_bytes() {
    let version = FileVersion {
        device: 1,
        inode: 2,
        size: 5,
        mtime_ns: 1,
        ctime_ns: 1,
    };
    let mut cache = SourceHashCache::default();
    let expected = cache.digest(Some(&version), b"hello").unwrap();
    let encoded = cache.to_bytes();
    let mut restored = SourceHashCache::from_bytes(Some(&encoded));
    assert_eq!(restored.load_status, LoadStatus::Restored);
    assert_eq!(restored.digest(Some(&version), b"hello").unwrap(), expected);
    assert_eq!(restored.stats.memo_hits, 1);
    let mut corrupted: serde_json::Value = serde_json::from_slice(&encoded).unwrap();
    corrupted["payload"]["entries"][0]["digest"] = serde_json::json!("a".repeat(64));
    let damaged = serde_json::to_vec(&corrupted).unwrap();
    let mut restored = SourceHashCache::from_bytes(Some(&damaged));
    assert_eq!(restored.load_status, LoadStatus::Discarded);
    assert_eq!(restored.digest(Some(&version), b"hello").unwrap(), expected);
    assert_eq!(restored.stats.versions_hashed, 1);
    assert_eq!(
        SourceHashCache::from_bytes(None).load_status,
        LoadStatus::Empty
    );
    assert_eq!(
        SourceHashCache::from_bytes(Some(b"not json")).load_status,
        LoadStatus::Discarded
    );
}

#[test]
fn implementation_identity_rejects_unversioned_or_noncanonical_digests() {
    let mut fixture = Fixture::new();
    fixture.worker.version.clear();
    assert!(fixture.prepared(&mut SourceHashCache::default()).is_err());
    let mut fixture = Fixture::new();
    fixture.validator.digest = "A".repeat(64);
    assert!(fixture.prepared(&mut SourceHashCache::default()).is_err());
}

#[test]
fn reference_logical_path_and_class_remain_key_ingredients() {
    let mut fixture = Fixture::new();
    let before = fixture.key();
    fixture.declaration.units[1].outputs[0].logical_path = "/Game/Materials/New".into();
    let Input::Reference { logical_path, .. } = &mut fixture.declaration.units[0].inputs[1] else {
        panic!()
    };
    *logical_path = "/Game/Materials/New".into();
    assert_ne!(before, fixture.key());
    let after_path = fixture.key();
    fixture.declaration.units[1].outputs[0].class = "StaticMeshSource".into();
    fixture
        .registry
        .values_mut()
        .next()
        .unwrap()
        .inputs
        .get_mut("material")
        .unwrap()
        .item_classes
        .insert("StaticMeshSource".into());
    let Input::Reference { class, .. } = &mut fixture.declaration.units[0].inputs[1] else {
        panic!()
    };
    *class = "StaticMeshSource".into();
    assert_ne!(after_path, fixture.key());
}

#[test]
fn optional_result_membership_changes_content_without_producer_key_noise() {
    let mut fixture = Fixture::new();
    fixture.content_item();
    let before = fixture.key();
    fixture.declaration.units[1].outputs[0]
        .files
        .push(OutputFile {
            path: "plain.ubulk".into(),
            install_path: Some("Content/Data/plain.ubulk".into()),
            required: false,
        });
    fixture.produced.values_mut().next().unwrap().item =
        fixture.declaration.units[1].outputs[0].clone();
    assert_eq!(before, fixture.key()); // A declaration-only change reproduced the same actual bytes/set.
    fixture
        .produced
        .values_mut()
        .next()
        .unwrap()
        .files
        .push(StoredFile {
            path: "plain.ubulk".into(),
            digest: sha256(b"bulk"),
            size: 4,
            mode: 0o644,
        });
    assert_ne!(before, fixture.key());
}

#[test]
fn selected_view_memo_binds_its_encoding_version() {
    let version = FileVersion {
        device: 1,
        inode: 2,
        size: 5,
        mtime_ns: 1,
        ctime_ns: 1,
    };
    let mut cache = SourceHashCache::default();
    let first = cache
        .digest_selected(Some(&version), 5, "/value", 1, b"[1]")
        .unwrap();
    assert_eq!(
        cache
            .digest_selected(Some(&version), 5, "/value", 1, b"[1]")
            .unwrap(),
        first
    );
    let changed = cache
        .digest_selected(Some(&version), 5, "/value", 2, b"[ 1 ]")
        .unwrap();
    assert_ne!(first, changed);
    assert_eq!(cache.stats.versions_hashed, 2);
}

#[test]
fn staged_namespace_separates_code_inputs_and_writable_outputs() {
    for path in [
        "ops/geometry.py",
        "OPS/Geometry.PY",
        "ops",
        "ops/common.py/child",
        "output",
        "OUTPUT/triangle.glb",
    ] {
        let mut fixture = Fixture::new();
        fixture.staged.insert("shape".into(), path.into());
        assert!(
            fixture.prepared(&mut SourceHashCache::default()).is_err(),
            "{path}"
        );
    }
    let mut fixture = Fixture::new();
    fixture.declaration.units[0].code.push("ops/Café.py".into());
    fixture
        .snapshot
        .insert("ops/Café.py".into(), SnapshotEntry::File(b"code".to_vec()));
    fixture
        .staged
        .insert("shape".into(), "OPS/Cafe\u{301}.py".into());
    assert!(fixture.prepared(&mut SourceHashCache::default()).is_err());
    let mut fixture = Fixture::new();
    fixture.declaration.units[0]
        .code
        .push("OUTPUT/utility.py".into());
    fixture.snapshot.insert(
        "OUTPUT/utility.py".into(),
        SnapshotEntry::File(b"code".to_vec()),
    );
    assert!(fixture.prepared(&mut SourceHashCache::default()).is_err());
}

#[test]
fn equal_content_digests_do_not_alias_file_and_item_shapes() {
    let mut fixture = Fixture::new();
    fixture.content_item();
    let before = fixture.prepared(&mut SourceHashCache::default()).unwrap();
    let stored = fixture.produced.values().next().unwrap();
    let bytes = canonical_bytes(&serde_json::json!({
        "domain": "atelier-item-content", "version": 1,
        "logical_path": stored.item.logical_path, "class": stored.item.class,
        "files": stored.files,
    }))
    .unwrap();
    let expected = ContentIdentity::Digest {
        digest: sha256(&bytes),
    };
    assert_eq!(before.ingredients().content["shape"], expected);
    fixture.declaration.units[0].inputs[0] = Input::Content {
        name: "shape".into(),
        source: ContentSource::File {
            path: "data/shape.json".into(),
            selector: None,
            optional: false,
        },
        whole: None,
        conditional: None,
    };
    fixture.change("data/shape.json", &bytes);
    let after = fixture.prepared(&mut SourceHashCache::default()).unwrap();
    assert_eq!(after.ingredients().content["shape"], expected);
    assert_eq!(
        before.ingredients().staged_inputs,
        after.ingredients().staged_inputs
    );
    assert_eq!(before.ingredients().input_kinds["shape"], InputKind::Item);
    assert_eq!(after.ingredients().input_kinds["shape"], InputKind::File);
    assert_ne!(before.key(), after.key());
}
