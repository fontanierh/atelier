use atelier_build_v2::{graph::*, schema::*, validate::*};
use std::collections::{BTreeMap, BTreeSet};

fn unit(id: &str) -> Unit {
    Unit {
        id: id.into(),
        op: Op {
            kind: "data".into(),
            version: "1".into(),
        },
        script: "ops/run.py".into(),
        code: vec!["ops/run.py".into()],
        inputs: vec![],
        params: BTreeMap::new(),
        conditional: None,
        output_groups: vec![],
        outputs: vec![Item {
            id: "result".into(),
            logical_path: format!("/Game/Data/{}", id.replace('.', "_")),
            class: "Data".into(),
            destination: Destination::Store,
            files: vec![OutputFile {
                path: "result.json".into(),
                install_path: None,
                required: true,
            }],
        }],
    }
}

fn content(producer: &str) -> Input {
    Input::Content {
        name: "data".into(),
        source: ContentSource::Item {
            unit: producer.into(),
            item: "result".into(),
        },
        whole: None,
        conditional: None,
    }
}
fn reference(producer: &Unit) -> Input {
    Input::Reference {
        name: "reference".into(),
        logical_path: producer.outputs[0].logical_path.clone(),
        class: "Data".into(),
        proof: "data.reference-invariance".into(),
        producer: Some(ItemRef {
            unit: producer.id.clone(),
            item: "result".into(),
        }),
    }
}
fn fixture() -> (Declaration, OpRegistry, SourceSnapshot) {
    let a = unit("leaf.alpha");
    let b = unit("leaf.beta");
    let mut mid = unit("middle");
    mid.inputs = vec![content(&a.id), reference(&b)];
    let mut final_unit = unit("final");
    final_unit.inputs = vec![content(&mid.id)];
    let rule = |role| InputRule {
        role,
        required: false,
        allow_absent_file: true,
        allow_selector: true,
        require_whole_reason: false,
        item_classes: BTreeSet::from(["Data".into()]),
    };
    (
        Declaration {
            schema_version: SCHEMA_VERSION,
            cache_version: "1".into(),
            units: vec![final_unit, mid, b, a, unit("leafish"), unit("unrelated")],
        },
        BTreeMap::from([(
            ("data".into(), "1".into()),
            OpDefinition {
                inputs: BTreeMap::from([
                    ("data".into(), rule(InputRole::Content)),
                    ("reference".into(), rule(InputRole::Reference)),
                ]),
                output_classes: BTreeSet::from(["Data".into()]),
                params: BTreeMap::new(),
            },
        )]),
        BTreeMap::from([("ops/run.py".into(), SnapshotEntry::File(b"code".to_vec()))]),
    )
}
fn graph(declaration: Declaration, registry: &OpRegistry) -> BuildGraph {
    BuildGraph::validate(declaration, registry, &[]).unwrap()
}

#[test]
fn target_closure_includes_content_and_reference_producers_only() {
    let (declaration, registry, snapshot) = fixture();
    let graph = graph(declaration, &registry);
    let selected = graph
        .select(&[Target::Unit("final".into())], &snapshot)
        .unwrap();
    assert_eq!(selected.roots(), &BTreeSet::from(["final".into()]));
    assert_eq!(
        selected.order(),
        ["leaf.alpha", "leaf.beta", "middle", "final"]
    );
    assert_eq!(
        selected.dependencies(),
        [
            Dependency {
                producer: "leaf.alpha".into(),
                consumer: "middle".into(),
                output: DependencyOutput::Item("result".into()),
                input: "data".into(),
                role: EdgeRole::Content
            },
            Dependency {
                producer: "leaf.beta".into(),
                consumer: "middle".into(),
                output: DependencyOutput::Item("result".into()),
                input: "reference".into(),
                role: EdgeRole::Reference
            },
            Dependency {
                producer: "middle".into(),
                consumer: "final".into(),
                output: DependencyOutput::Item("result".into()),
                input: "data".into(),
                role: EdgeRole::Content
            },
        ]
    );
}

#[test]
fn prefix_targets_respect_namespace_boundaries_and_union_without_duplicates() {
    let (declaration, registry, snapshot) = fixture();
    let graph = graph(declaration, &registry);
    let selected = graph
        .select(
            &[
                Target::Prefix("leaf".into()),
                Target::Unit("leaf.alpha".into()),
            ],
            &snapshot,
        )
        .unwrap();
    assert_eq!(selected.order(), ["leaf.alpha", "leaf.beta"]);
    assert_eq!(selected.roots().len(), 2);
    assert!(selected.dependencies().is_empty());
    let all = graph
        .select(&[Target::All, Target::Unit("final".into())], &snapshot)
        .unwrap();
    assert_eq!(all.order().len(), 6);
    assert_eq!(all.roots().len(), 6);
}

#[test]
fn unknown_empty_or_partial_targets_refuse() {
    let (declaration, registry, snapshot) = fixture();
    let graph = graph(declaration, &registry);
    for targets in [
        vec![],
        vec![Target::Unit("missing".into())],
        vec![Target::Prefix("lea".into())],
        vec![Target::Prefix("".into())],
        vec![Target::All, Target::Unit("missing".into())],
    ] {
        assert!(graph.select(&targets, &snapshot).is_err());
    }
}

#[test]
fn declaration_and_target_order_do_not_change_selected_graph() {
    let (declaration, registry, snapshot) = fixture();
    let mut reversed = declaration.clone();
    reversed.units.reverse();
    let first = graph(declaration, &registry)
        .select(
            &[Target::Unit("final".into()), Target::Unit("leafish".into())],
            &snapshot,
        )
        .unwrap();
    let second = graph(reversed, &registry)
        .select(
            &[Target::Unit("leafish".into()), Target::Unit("final".into())],
            &snapshot,
        )
        .unwrap();
    assert_eq!(first.order(), second.order());
    assert_eq!(first.dependencies(), second.dependencies());
    assert_eq!(first.roots(), second.roots());
}

#[test]
fn external_references_add_no_fabricated_producer_or_content_edge() {
    let (mut declaration, registry, snapshot) = fixture();
    let Input::Reference { producer, .. } = &mut declaration.units[1].inputs[1] else {
        panic!()
    };
    *producer = None;
    let selected = graph(declaration, &registry)
        .select(&[Target::Unit("final".into())], &snapshot)
        .unwrap();
    assert_eq!(selected.order(), ["leaf.alpha", "middle", "final"]);
    assert!(
        selected
            .dependencies()
            .iter()
            .all(|edge| edge.role == EdgeRole::Content)
    );
}

#[test]
fn unrelated_missing_sources_and_selectors_do_not_gate_selected_closure() {
    let (mut declaration, registry, mut snapshot) = fixture();
    declaration
        .units
        .last_mut()
        .unwrap()
        .inputs
        .push(Input::Content {
            name: "data".into(),
            source: ContentSource::File {
                path: "data/unfetched.json".into(),
                selector: Some("/required".into()),
                optional: false,
            },
            whole: None,
            conditional: None,
        });
    declaration
        .units
        .last_mut()
        .unwrap()
        .code
        .push("ops/unfetched.py".into());
    let graph = graph(declaration, &registry);
    assert!(
        graph
            .select(&[Target::Unit("final".into())], &snapshot)
            .is_ok()
    );
    assert!(
        graph
            .select(&[Target::Unit("unrelated".into())], &snapshot)
            .is_err()
    );
    snapshot.insert(
        "ops/unfetched.py".into(),
        SnapshotEntry::File(b"code".to_vec()),
    );
    snapshot.insert(
        "data/unfetched.json".into(),
        SnapshotEntry::File(b"{}".to_vec()),
    );
    assert!(
        graph
            .select(&[Target::Unit("final".into())], &snapshot)
            .is_ok()
    );
    assert!(
        graph
            .select(&[Target::Unit("unrelated".into())], &snapshot)
            .unwrap_err()
            .contains("missing selector node")
    );
    snapshot.insert(
        "data/unfetched.json".into(),
        SnapshotEntry::File(br#"{"required":null}"#.to_vec()),
    );
    let selected = graph
        .select(&[Target::Unit("unrelated".into())], &snapshot)
        .unwrap();
    assert_eq!(
        selected.validation().files[0].selection,
        FileSelection::Json(serde_json::Value::Null)
    );
    snapshot.remove("ops/run.py");
    assert!(
        graph
            .select(&[Target::Unit("final".into())], &snapshot)
            .is_err()
    );
}

#[test]
fn structural_errors_refuse_globally_before_any_selection() {
    let (declaration, registry, _) = fixture();
    let mut cycle = declaration.clone();
    cycle.units[3].inputs.push(content("final"));
    assert!(BuildGraph::validate(cycle, &registry, &[]).is_err());
    let mut missing = declaration.clone();
    missing.units[4].inputs.push(content("missing"));
    assert!(BuildGraph::validate(missing, &registry, &[]).is_err());
    let mut duplicate = declaration.clone();
    duplicate.units.push(declaration.units[0].clone());
    assert!(BuildGraph::validate(duplicate, &registry, &[]).is_err());
}
