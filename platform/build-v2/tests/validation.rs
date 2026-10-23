use atelier_build_v2::{schema::*, validate::*};
use std::collections::{BTreeMap, BTreeSet};

fn fixture() -> (Declaration, OpRegistry, SourceSnapshot, Vec<String>) {
    let declaration = parse_declaration(include_str!("../examples/units.toml")).unwrap();
    let registry = BTreeMap::from([(
        ("py_data".into(), "1".into()),
        OpDefinition {
            inputs: BTreeMap::from([
                (
                    "shape".into(),
                    InputRule {
                        role: InputRole::Content,
                        required: false,
                        allow_absent_file: true,
                        allow_selector: true,
                        require_whole_reason: false,
                        item_classes: BTreeSet::from(["StaticMeshSource".into()]),
                    },
                ),
                (
                    "material".into(),
                    InputRule {
                        role: InputRole::Reference,
                        required: false,
                        allow_absent_file: false,
                        allow_selector: false,
                        require_whole_reason: false,
                        item_classes: BTreeSet::from(["Material".into()]),
                    },
                ),
            ]),
            output_classes: BTreeSet::from(["StaticMeshSource".into(), "Material".into()]),
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
    let snapshot = BTreeMap::from([
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
            SnapshotEntry::File(br#"{"triangle":[1,2,3],"a/b":{"~":null}}"#.to_vec()),
        ),
    ]);
    (declaration, registry, snapshot, vec!["Content".into()])
}

fn rejected(
    declaration: &Declaration,
    registry: &OpRegistry,
    snapshot: &SourceSnapshot,
    roots: &[String],
    text: &str,
) {
    let error = validate(declaration, registry, snapshot, roots)
        .unwrap_err()
        .to_string();
    assert!(error.contains(text), "expected {text:?}, got {error:?}");
}

#[test]
fn validates_frozen_inputs_and_dependency_first_order() {
    let (declaration, registry, snapshot, roots) = fixture();
    let result = validate(&declaration, &registry, &snapshot, &roots).unwrap();
    assert_eq!(result.order, ["sample.material", "sample.geometry"]);
    assert_eq!(
        result.files[0].selection,
        FileSelection::Json(serde_json::json!([1, 2, 3]))
    );
    // Caller input is unchanged; validation has no filesystem or publishing API.
    assert_eq!(declaration.units[0].script, "ops/geometry.py");
}

#[test]
fn optional_absence_empty_file_and_missing_selector_are_distinct() {
    let (mut declaration, registry, mut snapshot, roots) = fixture();
    let Input::Content {
        source: ContentSource::File {
            selector, optional, ..
        },
        ..
    } = &mut declaration.units[0].inputs[0]
    else {
        panic!()
    };
    *optional = true;
    *selector = None;
    snapshot.remove("data/shape.json");
    assert_eq!(
        validate(&declaration, &registry, &snapshot, &roots)
            .unwrap()
            .files[0]
            .selection,
        FileSelection::Absent
    );
    snapshot.insert("data/shape.json".into(), SnapshotEntry::File(vec![]));
    assert_eq!(
        validate(&declaration, &registry, &snapshot, &roots)
            .unwrap()
            .files[0]
            .selection,
        FileSelection::Whole
    );
    let Input::Content {
        source: ContentSource::File { selector, .. },
        ..
    } = &mut declaration.units[0].inputs[0]
    else {
        panic!()
    };
    *selector = Some("/missing".into());
    rejected(&declaration, &registry, &snapshot, &roots, "not JSON");
    snapshot.insert(
        "data/shape.json".into(),
        SnapshotEntry::File(b"{}".to_vec()),
    );
    rejected(
        &declaration,
        &registry,
        &snapshot,
        &roots,
        "missing selector node",
    );
}

#[test]
fn selectors_decode_escapes_and_preserve_null() {
    let (mut declaration, registry, snapshot, roots) = fixture();
    let Input::Content {
        source: ContentSource::File { selector, .. },
        ..
    } = &mut declaration.units[0].inputs[0]
    else {
        panic!()
    };
    *selector = Some("/a~1b/~0".into());
    assert_eq!(
        validate(&declaration, &registry, &snapshot, &roots)
            .unwrap()
            .files[0]
            .selection,
        FileSelection::Json(serde_json::Value::Null)
    );
    for invalid in ["triangle", "/~2", "/triangle~"] {
        let Input::Content {
            source: ContentSource::File { selector, .. },
            ..
        } = &mut declaration.units[0].inputs[0]
        else {
            panic!()
        };
        *selector = Some(invalid.into());
        assert!(validate(&declaration, &registry, &snapshot, &roots).is_err());
    }
}

#[test]
fn missing_sources_and_nonregular_entries_fail_even_when_optional() {
    let (mut declaration, registry, mut snapshot, roots) = fixture();
    snapshot.remove("data/shape.json");
    rejected(
        &declaration,
        &registry,
        &snapshot,
        &roots,
        "missing required source",
    );
    let Input::Content {
        source: ContentSource::File { optional, .. },
        ..
    } = &mut declaration.units[0].inputs[0]
    else {
        panic!()
    };
    *optional = true;
    for entry in [
        SnapshotEntry::Directory,
        SnapshotEntry::Symlink,
        SnapshotEntry::Unreadable,
    ] {
        snapshot.insert("data/shape.json".into(), entry);
        rejected(
            &declaration,
            &registry,
            &snapshot,
            &roots,
            "not a readable regular file",
        );
    }
    snapshot.remove("ops/common.py");
    rejected(
        &declaration,
        &registry,
        &snapshot,
        &roots,
        "missing required source",
    );
}

#[test]
fn unknown_versions_ops_and_classes_fail() {
    let (declaration, registry, snapshot, roots) = fixture();
    let mut changed = declaration.clone();
    changed.schema_version += 1;
    rejected(&changed, &registry, &snapshot, &roots, "schema version");
    for (kind, version) in [("other", "1"), ("py_data", "2")] {
        changed = declaration.clone();
        changed.units[0].op = Op {
            kind: kind.into(),
            version: version.into(),
        };
        rejected(
            &changed,
            &registry,
            &snapshot,
            &roots,
            "unsupported op/version",
        );
    }
    changed = declaration.clone();
    changed.units[0].outputs[0].class = "Unknown".into();
    rejected(&changed, &registry, &snapshot, &roots, "output class");
}

#[test]
fn duplicate_unit_item_input_and_code_names_fail() {
    let (declaration, registry, snapshot, roots) = fixture();
    let mut changed = declaration.clone();
    let duplicate = changed.units[0].clone();
    changed.units.push(duplicate);
    rejected(&changed, &registry, &snapshot, &roots, "duplicate unit");
    changed = declaration.clone();
    let duplicate = changed.units[0].outputs[0].clone();
    changed.units[0].outputs.push(duplicate);
    rejected(&changed, &registry, &snapshot, &roots, "duplicate item");
    changed = declaration.clone();
    let duplicate = changed.units[0].inputs[0].clone();
    changed.units[0].inputs.push(duplicate);
    rejected(&changed, &registry, &snapshot, &roots, "duplicate input");
    changed = declaration.clone();
    let duplicate = changed.units[0].script.clone();
    changed.units[0].code.push(duplicate);
    rejected(&changed, &registry, &snapshot, &roots, "duplicate code");
}

#[test]
fn op_rules_require_named_inputs_and_correct_roles() {
    let (declaration, mut registry, snapshot, roots) = fixture();
    let mut changed = declaration.clone();
    let Input::Content { name, .. } = &mut changed.units[0].inputs[0] else {
        panic!()
    };
    *name = "unexpected".into();
    rejected(&changed, &registry, &snapshot, &roots, "unknown op input");
    let rule = registry
        .values_mut()
        .next()
        .unwrap()
        .inputs
        .get_mut("shape")
        .unwrap();
    rule.role = InputRole::Reference;
    rejected(&declaration, &registry, &snapshot, &roots, "wrong role");
    let rule = registry
        .values_mut()
        .next()
        .unwrap()
        .inputs
        .get_mut("shape")
        .unwrap();
    rule.role = InputRole::Content;
    rule.required = true;
    // The same op on sample.material does not supply shape.
    rejected(
        &declaration,
        &registry,
        &snapshot,
        &roots,
        "missing required op input",
    );
}

#[test]
fn op_rules_control_optional_files_and_selectors() {
    let (mut declaration, mut registry, snapshot, roots) = fixture();
    registry
        .values_mut()
        .next()
        .unwrap()
        .inputs
        .get_mut("shape")
        .unwrap()
        .allow_selector = false;
    rejected(
        &declaration,
        &registry,
        &snapshot,
        &roots,
        "does not allow selector",
    );
    registry
        .values_mut()
        .next()
        .unwrap()
        .inputs
        .get_mut("shape")
        .unwrap()
        .allow_selector = true;
    registry
        .values_mut()
        .next()
        .unwrap()
        .inputs
        .get_mut("shape")
        .unwrap()
        .allow_absent_file = false;
    let Input::Content {
        source: ContentSource::File { optional, .. },
        ..
    } = &mut declaration.units[0].inputs[0]
    else {
        panic!()
    };
    *optional = true;
    rejected(
        &declaration,
        &registry,
        &snapshot,
        &roots,
        "does not allow absent",
    );
}

#[test]
fn missing_producer_items_and_reference_identity_fail() {
    let (declaration, registry, snapshot, roots) = fixture();
    let mut changed = declaration.clone();
    let Input::Reference { producer, .. } = &mut changed.units[0].inputs[1] else {
        panic!()
    };
    producer.as_mut().unwrap().item = "unknown".into();
    rejected(
        &changed,
        &registry,
        &snapshot,
        &roots,
        "missing producer item",
    );
    changed = declaration.clone();
    let Input::Reference { logical_path, .. } = &mut changed.units[0].inputs[1] else {
        panic!()
    };
    *logical_path = "/Game/Materials/Other".into();
    rejected(&changed, &registry, &snapshot, &roots, "reference identity");
    changed = declaration.clone();
    let Input::Reference { proof, .. } = &mut changed.units[0].inputs[1] else {
        panic!()
    };
    proof.clear();
    rejected(&changed, &registry, &snapshot, &roots, "reference proof");
}

#[test]
fn content_and_scheduling_cycles_fail() {
    let (mut declaration, registry, snapshot, roots) = fixture();
    declaration.units[1].inputs.push(Input::Content {
        name: "shape".into(),
        source: ContentSource::Item {
            unit: "sample.geometry".into(),
            item: "triangle".into(),
        },
        whole: Some("consumes complete geometry".into()),
        conditional: None,
    });
    rejected(
        &declaration,
        &registry,
        &snapshot,
        &roots,
        "dependency cycle",
    );
    declaration.units[1].inputs.clear();
    declaration.units[0].inputs[0] = Input::Content {
        name: "shape".into(),
        source: ContentSource::Item {
            unit: "sample.geometry".into(),
            item: "triangle".into(),
        },
        whole: Some("entire selected source item".into()),
        conditional: None,
    };
    rejected(
        &declaration,
        &registry,
        &snapshot,
        &roots,
        "dependency cycle",
    );
}

#[test]
fn invalid_owned_and_source_paths_fail_without_normalizing_them() {
    let (declaration, registry, snapshot, roots) = fixture();
    for invalid in [
        "/absolute",
        "../escape",
        "a/./b",
        "a//b",
        "a\\b",
        "C:drive",
        "trailing.",
        "trailing ",
        "a\0b",
    ] {
        let mut changed = declaration.clone();
        changed.units[0].outputs[0].files[0].path = invalid.into();
        rejected(&changed, &registry, &snapshot, &roots, "invalid owned path");
        changed = declaration.clone();
        changed.units[0].script = invalid.into();
        rejected(
            &changed,
            &registry,
            &snapshot,
            &roots,
            "invalid source path",
        );
    }
}

#[test]
fn install_paths_require_allowed_roots_and_cannot_overwrite_sources() {
    let (declaration, registry, snapshot, roots) = fixture();
    let mut changed = declaration.clone();
    changed.units[1].outputs[0].files[0].install_path = None;
    rejected(
        &changed,
        &registry,
        &snapshot,
        &roots,
        "missing checkout install",
    );
    changed.units[1].outputs[0].files[0].install_path = Some("Source/new.py".into());
    rejected(
        &changed,
        &registry,
        &snapshot,
        &roots,
        "outside allowed roots",
    );
    changed.units[1].outputs[0].files[0].install_path = Some("ops/geometry.py".into());
    rejected(
        &changed,
        &registry,
        &snapshot,
        &["ops".into()],
        "overlaps declared code",
    );
    changed.units[1].outputs[0].files[0].install_path = Some("data/shape.json".into());
    rejected(
        &changed,
        &registry,
        &snapshot,
        &["data".into()],
        "overlaps source input",
    );
}

#[test]
fn unicode_case_and_ancestor_output_conflicts_fail() {
    let (declaration, registry, snapshot, roots) = fixture();
    for (a, b) in [
        ("Asset", "asset"),
        ("Caf\u{e9}", "Cafe\u{301}"),
        ("Straße", "STRASSE"),
        ("Asset", "ASSET/child"),
    ] {
        let mut changed = declaration.clone();
        let mut second = changed.units[1].clone();
        second.id = "sample.second".into();
        second.outputs[0].logical_path = "/Game/Materials/Other".into();
        changed.units[1].outputs[0].files[0].install_path = Some(format!("Content/{a}"));
        second.outputs[0].files[0].install_path = Some(format!("Content/{b}"));
        changed.units.push(second);
        rejected(
            &changed,
            &registry,
            &snapshot,
            &roots,
            "overlapping output owners",
        );
    }
}

#[test]
fn optional_sidecar_and_job_output_overlaps_fail() {
    let (mut declaration, registry, snapshot, roots) = fixture();
    let file = declaration.units[0].outputs[0].files[0].clone();
    declaration.units[0].outputs[0].files.push(OutputFile {
        required: false,
        ..file
    });
    rejected(
        &declaration,
        &registry,
        &snapshot,
        &roots,
        "overlapping output owners",
    );
}

#[test]
fn unicode_source_and_distinct_unicode_output_names_remain_usable() {
    let (mut declaration, registry, mut snapshot, roots) = fixture();
    let bytes = snapshot.remove("ops/common.py").unwrap();
    snapshot.insert("ops/共通.py".into(), bytes);
    declaration.units[0].code[1] = "ops/共通.py".into();
    declaration.units[0].outputs[0].files[0].path = "山.glb".into();
    declaration.units[1].outputs[0].files[0].install_path = Some("Content/海.json".into());
    assert!(validate(&declaration, &registry, &snapshot, &roots).is_ok());
}

#[test]
fn op_parameters_reject_typos_wrong_types_and_missing_requirements() {
    let (declaration, mut registry, snapshot, roots) = fixture();
    let mut changed = declaration.clone();
    changed.units[0]
        .params
        .insert("typo".into(), serde_json::json!(true));
    rejected(
        &changed,
        &registry,
        &snapshot,
        &roots,
        "unknown op parameter",
    );
    changed = declaration.clone();
    changed.units[0]
        .params
        .insert("seed".into(), serde_json::json!("42"));
    rejected(&changed, &registry, &snapshot, &roots, "wrong type");
    registry
        .values_mut()
        .next()
        .unwrap()
        .params
        .get_mut("seed")
        .unwrap()
        .required = true;
    rejected(
        &declaration,
        &registry,
        &snapshot,
        &roots,
        "missing required op parameter",
    );
}

#[test]
fn loader_combines_strict_toml_shape_and_semantic_validation() {
    let (_, registry, snapshot, roots) = fixture();
    assert!(
        load(
            include_str!("../examples/units.toml"),
            &registry,
            &snapshot,
            &roots
        )
        .is_ok()
    );
    assert!(
        load("units=[]\nunknown=true", &registry, &snapshot, &roots)
            .unwrap_err()
            .to_string()
            .contains("invalid TOML")
    );
}

#[test]
fn bounded_items_need_no_whole_note_but_broad_slots_require_one() {
    let (mut declaration, mut registry, snapshot, roots) = fixture();
    // A non-root selector narrows even a generally broad slot.
    registry
        .values_mut()
        .next()
        .unwrap()
        .inputs
        .get_mut("shape")
        .unwrap()
        .require_whole_reason = true;
    assert!(validate(&declaration, &registry, &snapshot, &roots).is_ok());
    registry
        .values_mut()
        .next()
        .unwrap()
        .inputs
        .get_mut("shape")
        .unwrap()
        .require_whole_reason = false;
    declaration.units[0].inputs[0] = Input::Content {
        name: "shape".into(),
        source: ContentSource::Item {
            unit: "sample.material".into(),
            item: "plain".into(),
        },
        whole: None,
        conditional: None,
    };
    let rule = registry
        .values_mut()
        .next()
        .unwrap()
        .inputs
        .get_mut("shape")
        .unwrap();
    rule.item_classes.insert("Material".into());
    assert!(validate(&declaration, &registry, &snapshot, &roots).is_ok());
    registry
        .values_mut()
        .next()
        .unwrap()
        .inputs
        .get_mut("shape")
        .unwrap()
        .require_whole_reason = true;
    rejected(
        &declaration,
        &registry,
        &snapshot,
        &roots,
        "broad op input requires a whole reason",
    );
    let Input::Content { whole, .. } = &mut declaration.units[0].inputs[0] else {
        panic!()
    };
    *whole = Some("consumes the complete chosen material set".into());
    assert!(validate(&declaration, &registry, &snapshot, &roots).is_ok());
}

#[test]
fn ancestor_conflicts_survive_lexically_adjacent_sibling_claims() {
    let (mut declaration, registry, snapshot, roots) = fixture();
    let mut adjacent = declaration.units[1].clone();
    adjacent.id = "sample.adjacent".into();
    adjacent.outputs[0].logical_path = "/Game/Materials/Adjacent".into();
    adjacent.outputs[0].files[0].install_path = Some("Content/Asset-".into());
    let mut descendant = adjacent.clone();
    descendant.id = "sample.child".into();
    descendant.outputs[0].logical_path = "/Game/Materials/Descendant".into();
    descendant.outputs[0].files[0].install_path = Some("Content/Asset/child".into());
    declaration.units[1].outputs[0].files[0].install_path = Some("Content/Asset".into());
    declaration.units.extend([adjacent, descendant]);
    rejected(
        &declaration,
        &registry,
        &snapshot,
        &roots,
        "overlapping output owners",
    );
}

#[test]
fn output_sets_and_entry_code_must_be_declared_completely() {
    let (declaration, registry, snapshot, roots) = fixture();
    let mut changed = declaration.clone();
    changed.units[0].code.remove(0);
    rejected(
        &changed,
        &registry,
        &snapshot,
        &roots,
        "entry script absent",
    );
    changed = declaration.clone();
    changed.units[0].outputs.clear();
    rejected(
        &changed,
        &registry,
        &snapshot,
        &roots,
        "unit has no outputs",
    );
    changed = declaration.clone();
    changed.units[0].outputs[0].files[0].required = false;
    rejected(
        &changed,
        &registry,
        &snapshot,
        &roots,
        "no required file output",
    );
    changed = declaration.clone();
    changed.units[0].outputs[0].files.push(OutputFile {
        path: "triangle.uexp".into(),
        required: false,
        install_path: None,
    });
    assert!(validate(&changed, &registry, &snapshot, &roots).is_ok());
}
