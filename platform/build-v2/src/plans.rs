//! Typed child expansion over private validated D2 member tokens. No scheduling or I/O.
use crate::graph::BuildGraph;
use crate::groups::{EncodedRole, OutputGroupContract, PlanEncoding, ValidatedGroup};
use crate::schema::*;
use crate::validate::OpRegistry;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

/// Authored executable/output contract. Plans supply only piece/member metadata.
/// Every child uses the same code, op, staged slot and bounded output shape.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ChildTemplate {
    pub producer: String,
    pub group: String,
    pub unit_prefix: String,
    pub op: Op,
    pub script: String,
    pub code: Vec<String>,
    pub params: Params,
    pub payload_slot: String,
    pub staged_path: String,
    pub output_class: String,
    pub logical_namespace: String,
    pub files: Vec<OutputFile>,
    #[serde(default)]
    pub followers: Vec<crate::native_chains::FollowerTemplate>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ChildTarget {
    NotMine,
    NeedsPlanner { producer: String, group: String },
    Ready { unit: String },
    UnknownChild { unit: String },
}

pub struct RegisteredTemplate {
    template: ChildTemplate,
    contract: OutputGroupContract,
}

/// An in-process ownership receipt, issued only after complete expansion validation.
/// Raw deserialization must not grant authority to retire another unit's outputs.
#[derive(Clone, Debug, Serialize)]
pub struct ExpansionReceipt {
    scope: OwnershipScope,
    children: BTreeMap<String, Unit>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
struct OwnershipScope {
    producer: String,
    group: String,
    unit_prefix: String,
    logical_namespace: String,
}

#[derive(Clone, Debug)]
pub struct RemovalIntent {
    unit: String,
    outputs: Vec<Item>,
}
impl RemovalIntent {
    pub fn unit(&self) -> &str {
        &self.unit
    }
    pub fn outputs(&self) -> &[Item] {
        &self.outputs
    }
}

pub struct Expansion {
    graph: BuildGraph,
    receipt: ExpansionReceipt,
    removals: Vec<RemovalIntent>,
}
impl Expansion {
    pub fn graph(&self) -> &BuildGraph {
        &self.graph
    }
    pub fn receipt(&self) -> &ExpansionReceipt {
        &self.receipt
    }
    pub fn removals(&self) -> &[RemovalIntent] {
        &self.removals
    }
    pub fn children(&self) -> impl Iterator<Item = &str> {
        self.receipt.children.keys().map(String::as_str)
    }
}

impl ChildTemplate {
    fn ownership(&self) -> OwnershipScope {
        OwnershipScope {
            producer: self.producer.clone(),
            group: self.group.clone(),
            unit_prefix: self.unit_prefix.clone(),
            logical_namespace: self.logical_namespace.clone(),
        }
    }

    fn child(
        &self,
        piece: &str,
        payload: &str,
        encoding: &PlanEncoding,
        role: Option<&EncodedRole>,
    ) -> Unit {
        let mut params = self.params.clone();
        params.insert(
            "payload_role".into(),
            match role {
                Some(EncodedRole::Render) => "render",
                Some(EncodedRole::Collision) => "collision",
                None => "geometry",
            }
            .into(),
        );
        params.insert("payload_member".into(), payload.into());
        params.insert(
            "payload_encoding".into(),
            match encoding {
                PlanEncoding::MeshIr => "mesh_ir",
                PlanEncoding::MeshSet => "mesh_set",
                PlanEncoding::EncodedGlb => "encoded_glb",
            }
            .into(),
        );
        Unit {
            id: format!("{}.{piece}", self.unit_prefix),
            op: self.op.clone(),
            script: self.script.clone(),
            code: self.code.clone(),
            params,
            inputs: vec![Input::Content {
                name: self.payload_slot.clone(),
                source: ContentSource::GroupMember {
                    unit: self.producer.clone(),
                    group: self.group.clone(),
                    piece: piece.into(),
                },
                whole: None,
                conditional: None,
            }],
            outputs: vec![Item {
                id: "asset".into(),
                logical_path: format!("{}/{piece}", self.logical_namespace),
                class: self.output_class.clone(),
                files: self
                    .files
                    .iter()
                    .map(|file| OutputFile {
                        path: file.path.replace("$piece", piece),
                        install_path: file
                            .install_path
                            .as_ref()
                            .map(|p| p.replace("$piece", piece)),
                        required: file.required,
                    })
                    .collect(),
                destination: Destination::Store,
            }],
            output_groups: vec![],
            conditional: None,
        }
    }
}

impl RegisteredTemplate {
    /// Check the fixed authoring interface without claiming any runtime child exists.
    /// The temporary structural witness is discarded; no graph/receipt/hit is exported.
    pub fn register(
        base: &BuildGraph,
        template: ChildTemplate,
        registry: &OpRegistry,
        allowed_install_roots: &[String],
    ) -> Result<Self, String> {
        let producer = base.unit(&template.producer).ok_or("unknown planner")?;
        let contract = producer
            .output_groups
            .iter()
            .find(|g| g.id == template.group)
            .ok_or("unknown planner group")?
            .clone();
        if template.params.contains_key("payload_member")
            || template.params.contains_key("payload_encoding")
            || template.params.contains_key("payload_role")
        {
            return Err("template overrides derived member parameters".into());
        }
        if template.unit_prefix.is_empty() || template.unit_prefix.ends_with('.') {
            return Err("invalid child unit prefix".into());
        }
        crate::paths::logical_path(&template.logical_namespace)?;
        crate::keys::safe_staged_paths(
            &BTreeMap::from([(template.payload_slot.clone(), template.staged_path.clone())]),
            &template.code,
        )?;
        let mut declaration = base.declaration().clone();
        declaration.schema_version = SCHEMA_VERSION;
        let child = template.child(
            "TemplateValidation",
            "TemplateValidation.npz",
            &contract.encoding,
            None,
        );
        let followers = crate::native_chains::instantiate(
            &template.followers,
            "TemplateValidation",
            &child.id,
        )?;
        for follower in &followers.units {
            let stage = &followers.staged_inputs[&follower.id];
            let names = follower
                .inputs
                .iter()
                .map(|input| match input {
                    Input::Content { name, .. } | Input::Reference { name, .. } => name.as_str(),
                })
                .collect::<BTreeSet<_>>();
            if stage.keys().map(String::as_str).collect::<BTreeSet<_>>() != names {
                return Err("native follower staged paths omit/introduce an input".into());
            }
            crate::keys::safe_staged_paths(stage, &follower.code)?;
        }
        declaration.units.push(child);
        declaration.units.extend(followers.units);
        crate::validate::validate_structure(&declaration, registry, allowed_install_roots)
            .map_err(|e| e.to_string())?;
        Ok(Self { template, contract })
    }

    pub fn staged_inputs(&self) -> BTreeMap<String, String> {
        BTreeMap::from([(
            self.template.payload_slot.clone(),
            self.template.staged_path.clone(),
        )])
    }

    pub fn staged_inputs_for(
        &self,
        piece: &str,
    ) -> Result<BTreeMap<String, BTreeMap<String, String>>, String> {
        let export = format!("{}.{piece}", self.template.unit_prefix);
        let mut all = crate::native_chains::instantiate(&self.template.followers, piece, &export)?
            .staged_inputs;
        all.insert(export, self.staged_inputs());
        Ok(all)
    }

    fn check_group(&self, group: &ValidatedGroup) -> Result<(), String> {
        if group.contract() != &self.contract {
            return Err("planner group contract changed".into());
        }
        Ok(())
    }

    /// Cold selection is a prerequisite request, never a placeholder export or cache hit.
    pub fn resolve(
        &self,
        target: &str,
        group: Option<&ValidatedGroup>,
    ) -> Result<ChildTarget, String> {
        let prefix = format!("{}.", self.template.unit_prefix);
        let Some(piece) = target.strip_prefix(&prefix) else {
            return Ok(ChildTarget::NotMine);
        };
        crate::groups::name(piece)?;
        let Some(group) = group else {
            return Ok(ChildTarget::NeedsPlanner {
                producer: self.template.producer.clone(),
                group: self.template.group.clone(),
            });
        };
        self.check_group(group)?;
        if group.stored().projections.contains_key(piece) {
            Ok(ChildTarget::Ready {
                unit: target.into(),
            })
        } else {
            Ok(ChildTarget::UnknownChild {
                unit: target.into(),
            })
        }
    }

    /// @cc [owner:fontanierh,label:correctness] validated-child-batch-and-retirement
    /// Expansion MUST validate the complete batch before exposing any child graph.
    /// Child op/script/code MUST come only from the registered template, with one
    /// GroupMember dependency per piece. Removal intents MUST contain only exact
    /// prior receipt-owned outputs; they MUST NOT delete files or infer prefix ownership.
    /// See plans::tests. Actual dispatch remains D2/A9; downstream installed ownership and
    /// safe native removals remain D4/A5/B3. These intents identify prior export Items only.
    pub fn expand(
        &self,
        base: &BuildGraph,
        group: &ValidatedGroup,
        prior: Option<&ExpansionReceipt>,
        registry: &OpRegistry,
        allowed_install_roots: &[String],
    ) -> Result<Expansion, String> {
        self.check_group(group)?;
        let current = base
            .unit(&self.template.producer)
            .ok_or("planner removed")?;
        if !current.output_groups.contains(&self.contract) {
            return Err("planner declaration changed".into());
        }
        let mut declaration = base.declaration().clone();
        let mut previous = BTreeMap::new();
        if let Some(prior) = prior {
            if prior.scope != self.template.ownership() {
                return Err("foreign expansion receipt".into());
            }
            previous = prior.children.clone();
            for (id, owned) in &previous {
                if declaration
                    .units
                    .iter()
                    .any(|unit| &unit.id == id && unit != owned)
                {
                    return Err("prior child ownership changed".into());
                }
            }
            declaration
                .units
                .retain(|unit| !previous.contains_key(&unit.id));
        }
        let mut children = BTreeMap::new();
        for (piece, projection) in &group.stored().projections {
            let child = self.template.child(
                piece,
                &projection.payload,
                &projection.encoding,
                projection.role.as_ref(),
            );
            let followers =
                crate::native_chains::instantiate(&self.template.followers, piece, &child.id)?;
            if children.insert(child.id.clone(), child).is_some() {
                return Err("duplicate expanded export child".into());
            }
            for follower in followers.units {
                if children.insert(follower.id.clone(), follower).is_some() {
                    return Err("duplicate expanded native follower".into());
                }
            }
        }
        declaration.schema_version = SCHEMA_VERSION;
        declaration.units.extend(children.values().cloned());
        let graph = BuildGraph::validate(declaration, registry, allowed_install_roots)
            .map_err(|e| e.to_string())?;
        let current_ids: BTreeSet<_> = children.keys().collect();
        let removals = previous
            .into_iter()
            .filter(|(id, _)| !current_ids.contains(id))
            .map(|(unit, old)| RemovalIntent {
                unit,
                outputs: old.outputs,
            })
            .collect();
        Ok(Expansion {
            graph,
            receipt: ExpansionReceipt {
                scope: self.template.ownership(),
                children,
            },
            removals,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::graph::Target;
    use crate::groups::{MemberProjection, StoredOutputGroup, restore_recorded};
    use crate::validate::*;

    fn fixture() -> (BuildGraph, OpRegistry, ChildTemplate, OutputGroupContract) {
        let contract = OutputGroupContract {
            id: "geometry".into(),
            root: "geometry".into(),
            root_param: "output_root".into(),
            manifest: "plan.json".into(),
            adapter_version: "fixture/1".into(),
            parent: "Village".into(),
            encoding: PlanEncoding::MeshIr,
            class: "Payload".into(),
            logical_namespace: "/Internal/Village".into(),
            max_pieces: 20,
            max_manifest_bytes: 1024,
            max_member_bytes: 2048,
            max_total_bytes: 4096,
        };
        let registry = BTreeMap::from([(
            ("fixture".into(), "1".into()),
            OpDefinition {
                inputs: BTreeMap::from([(
                    "payload".into(),
                    InputRule {
                        role: InputRole::Content,
                        required: false,
                        allow_absent_file: false,
                        allow_selector: false,
                        require_whole_reason: false,
                        item_classes: BTreeSet::from(["Payload".into()]),
                    },
                )]),
                output_classes: BTreeSet::from(["Payload".into(), "Mesh".into()]),
                params: [
                    "output_root",
                    "payload_member",
                    "payload_encoding",
                    "payload_role",
                ]
                .into_iter()
                .map(|name| {
                    (
                        name.into(),
                        ParamRule {
                            kind: ParamKind::String,
                            required: false,
                        },
                    )
                })
                .collect(),
            },
        )]);
        let planner = Unit {
            id: "planner".into(),
            op: Op {
                kind: "fixture".into(),
                version: "1".into(),
            },
            script: "ops/plan.py".into(),
            code: vec!["ops/plan.py".into()],
            inputs: vec![],
            params: BTreeMap::from([("output_root".into(), "output/geometry".into())]),
            outputs: vec![],
            output_groups: vec![contract.clone()],
            conditional: None,
        };
        let template = ChildTemplate {
            followers: vec![],
            producer: "planner".into(),
            group: "geometry".into(),
            unit_prefix: "export.Village".into(),
            op: planner.op.clone(),
            script: "ops/export.py".into(),
            code: vec!["ops/export.py".into()],
            params: Params::new(),
            payload_slot: "payload".into(),
            staged_path: "inputs/payload".into(),
            output_class: "Mesh".into(),
            logical_namespace: "/Game/Village".into(),
            files: vec![
                OutputFile {
                    path: "mesh.fbx".into(),
                    install_path: None,
                    required: true,
                },
                OutputFile {
                    path: "export.json".into(),
                    install_path: None,
                    required: true,
                },
            ],
        };
        let base = BuildGraph::validate(
            Declaration {
                schema_version: SCHEMA_VERSION,
                cache_version: "fixture".into(),
                units: vec![planner],
            },
            &registry,
            &[],
        )
        .unwrap();
        (base, registry, template, contract)
    }

    fn token(contract: &OutputGroupContract, pieces: &[&str]) -> ValidatedGroup {
        let mut files = vec![StoredFile {
            path: "plan.json".into(),
            digest: "a".repeat(64),
            size: 10,
            mode: 0o644,
        }];
        let projections = pieces
            .iter()
            .map(|piece| {
                let payload = format!("{piece}.npz");
                files.push(StoredFile {
                    path: payload.clone(),
                    digest: "b".repeat(64),
                    size: 20,
                    mode: 0o644,
                });
                (
                    piece.to_string(),
                    MemberProjection {
                        payload,
                        encoding: PlanEncoding::MeshIr,
                        role: None,
                    },
                )
            })
            .collect();
        restore_recorded(
            contract,
            &StoredOutputGroup {
                id: contract.id.clone(),
                files,
                projections,
            },
            |_| Ok(()),
        )
        .unwrap()
    }

    #[test]
    fn cold_child_selection_requires_planner_then_resolves_or_refuses() {
        let (base, registry, template, contract) = fixture();
        let registered = RegisteredTemplate::register(&base, template, &registry, &[]).unwrap();
        assert_eq!(base.declaration().units.len(), 1);
        assert_eq!(
            registered.resolve("export.Village.A", None).unwrap(),
            ChildTarget::NeedsPlanner {
                producer: "planner".into(),
                group: "geometry".into()
            }
        );
        assert_eq!(
            registered.resolve("other.A", None).unwrap(),
            ChildTarget::NotMine
        );
        assert!(registered.resolve("export.Village.A.bad", None).is_err());
        let group = token(&contract, &["A"]);
        assert_eq!(
            registered
                .resolve("export.Village.A", Some(&group))
                .unwrap(),
            ChildTarget::Ready {
                unit: "export.Village.A".into()
            }
        );
        assert_eq!(
            registered
                .resolve("export.Village.Missing", Some(&group))
                .unwrap(),
            ChildTarget::UnknownChild {
                unit: "export.Village.Missing".into()
            }
        );
        assert!(base.unit("export.Village.A").is_none());
        let expanded = registered
            .expand(&base, &group, None, &registry, &[])
            .unwrap();
        let snapshot = BTreeMap::from([
            ("ops/plan.py".into(), SnapshotEntry::File(vec![])),
            ("ops/export.py".into(), SnapshotEntry::File(vec![])),
        ]);
        let selected = expanded
            .graph()
            .select(&[Target::Unit("export.Village.A".into())], &snapshot)
            .unwrap();
        assert_eq!(selected.order(), ["planner", "export.Village.A"]);
        assert_eq!(selected.dependencies().len(), 1);
        assert_eq!(registered.staged_inputs()["payload"], "inputs/payload");

        let (base, mut registry, mut template, contract) = fixture();
        registry
            .get_mut(&("fixture".into(), "1".into()))
            .unwrap()
            .inputs
            .get_mut("payload")
            .unwrap()
            .item_classes
            .insert("Mesh".into());
        let mut raw = template.child("$piece", "unused", &contract.encoding, None);
        raw.id = "raw.Village.$piece".into();
        raw.params.clear();
        raw.inputs = vec![Input::Content {
            name: "payload".into(),
            source: ContentSource::Item {
                unit: "$export".into(),
                item: "asset".into(),
            },
            whole: None,
            conditional: None,
        }];
        raw.outputs[0].logical_path = "/Game/Raw/$piece".into();
        let mut finish = raw.clone();
        finish.id = "finish.Village.$piece".into();
        finish.inputs = vec![Input::Content {
            name: "payload".into(),
            source: ContentSource::Item {
                unit: "$previous".into(),
                item: "asset".into(),
            },
            whole: None,
            conditional: None,
        }];
        finish.outputs[0].logical_path = "/Game/Finished/$piece".into();
        let stage = BTreeMap::from([("payload".into(), "inputs/upstream".into())]);
        template.followers = vec![
            crate::native_chains::FollowerTemplate {
                unit: raw,
                staged_inputs: stage.clone(),
            },
            crate::native_chains::FollowerTemplate {
                unit: finish,
                staged_inputs: stage,
            },
        ];
        let registered =
            RegisteredTemplate::register(&base, template.clone(), &registry, &[]).unwrap();
        let first = registered
            .expand(&base, &token(&contract, &["A"]), None, &registry, &[])
            .unwrap();
        let selected = first
            .graph()
            .select(&[Target::Unit("finish.Village.A".into())], &snapshot)
            .unwrap();
        assert_eq!(
            selected.order(),
            [
                "planner",
                "export.Village.A",
                "raw.Village.A",
                "finish.Village.A"
            ]
        );
        assert_eq!(registered.staged_inputs_for("A").unwrap().len(), 3);
        let next = registered
            .expand(
                first.graph(),
                &token(&contract, &["B"]),
                Some(first.receipt()),
                &registry,
                &[],
            )
            .unwrap();
        assert_eq!(next.removals().len(), 3);
        assert!(next.graph().unit("raw.Village.A").is_none());
        template.followers[0].unit.id = "$unknown".into();
        assert!(RegisteredTemplate::register(&base, template, &registry, &[]).is_err());
    }

    #[test]
    fn complete_expansion_has_stable_children_and_exact_prior_owner_removal_intents() {
        let (base, registry, template, contract) = fixture();
        let registered =
            RegisteredTemplate::register(&base, template.clone(), &registry, &[]).unwrap();
        let first = registered
            .expand(&base, &token(&contract, &["B", "A"]), None, &registry, &[])
            .unwrap();
        assert_eq!(
            first.children().collect::<Vec<_>>(),
            ["export.Village.A", "export.Village.B"]
        );
        let second = registered
            .expand(
                first.graph(),
                &token(&contract, &["C", "B"]),
                Some(first.receipt()),
                &registry,
                &[],
            )
            .unwrap();
        assert_eq!(
            second.children().collect::<Vec<_>>(),
            ["export.Village.B", "export.Village.C"]
        );
        assert_eq!(
            first.graph().unit("export.Village.B"),
            second.graph().unit("export.Village.B")
        );
        assert_eq!(second.removals().len(), 1);
        assert_eq!(second.removals()[0].unit(), "export.Village.A");
        assert_eq!(
            second.removals()[0].outputs(),
            first.graph().unit("export.Village.A").unwrap().outputs
        );
        let child = second.graph().unit("export.Village.C").unwrap();
        assert_eq!(child.script, template.script);
        assert_eq!(child.code, template.code);
        assert_eq!(child.op, template.op);
        assert_eq!(child.params["payload_member"], "C.npz");
        assert_eq!(child.params["payload_encoding"], "mesh_ir");
        assert!(!child.code.contains(&"ops/plan.py".into()));
        assert!(second.graph().unit("export.Village.A").is_none());
    }

    #[test]
    fn expanded_child_key_ignores_roster_and_planner_code_but_binds_exporter_code() {
        use crate::keys::*;
        let (base, registry, template, contract) = fixture();
        let registered = RegisteredTemplate::register(&base, template, &registry, &[]).unwrap();
        let key = |pieces: &[&str], planner_code: &[u8], exporter_code: &[u8]| {
            let group = token(&contract, pieces);
            let expansion = registered
                .expand(&base, &group, None, &registry, &[])
                .unwrap();
            let snapshot = BTreeMap::from([
                (
                    "ops/plan.py".into(),
                    SnapshotEntry::File(planner_code.to_vec()),
                ),
                (
                    "ops/export.py".into(),
                    SnapshotEntry::File(exporter_code.to_vec()),
                ),
            ]);
            let selected = expansion
                .graph()
                .select(&[Target::Unit("export.Village.B".into())], &snapshot)
                .unwrap();
            let groups = BTreeMap::from([(("planner".into(), "geometry".into()), group)]);
            let implementation = ImplementationIdentity {
                version: "fixture/1".into(),
                digest: "c".repeat(64),
            };
            prepare(
                expansion.graph().declaration(),
                selected.validation(),
                "export.Village.B",
                &KeyContext {
                    snapshot: &snapshot,
                    versions: &BTreeMap::new(),
                    produced: &BTreeMap::new(),
                    produced_groups: &groups,
                    staged_inputs: &registered.staged_inputs(),
                    worker: &implementation,
                    validator: &implementation,
                },
                &mut crate::source_hashes::SourceHashCache::default(),
            )
            .unwrap()
            .key()
            .to_owned()
        };
        let first = key(&["A", "B"], b"planner v1", b"exporter v1");
        assert_eq!(
            first,
            key(&["B", "C"], b"planner v2 # comment", b"exporter v1")
        );
        assert_ne!(
            first,
            key(&["B", "C"], b"planner v2 # comment", b"exporter v2")
        );
    }

    #[test]
    fn receipt_ownership_survives_exporter_and_planner_version_evolution() {
        let (base, mut registry, template, contract) = fixture();
        let registered =
            RegisteredTemplate::register(&base, template.clone(), &registry, &[]).unwrap();
        let first = registered
            .expand(&base, &token(&contract, &["A", "B"]), None, &registry, &[])
            .unwrap();
        let mut evolved_contract = contract.clone();
        evolved_contract.adapter_version = "fixture/2".into();
        evolved_contract.max_pieces += 1;
        let mut evolved = first.graph().declaration().clone();
        evolved
            .units
            .iter_mut()
            .find(|u| u.id == "planner")
            .unwrap()
            .output_groups[0] = evolved_contract.clone();
        let version2 = registry[&("fixture".into(), "1".into())].clone();
        registry.insert(("fixture".into(), "2".into()), version2);
        let mut template2 = template.clone();
        template2.op.version = "2".into();
        template2.script = "ops/export_v2.py".into();
        template2.code = vec![template2.script.clone(), "ops/export_helper.py".into()];
        let evolved = BuildGraph::validate(evolved, &registry, &[]).unwrap();
        let registered2 =
            RegisteredTemplate::register(&evolved, template2.clone(), &registry, &[]).unwrap();
        let second = registered2
            .expand(
                &evolved,
                &token(&evolved_contract, &["B", "C"]),
                Some(first.receipt()),
                &registry,
                &[],
            )
            .unwrap();
        let child = second.graph().unit("export.Village.B").unwrap();
        assert_eq!(child.id, first.graph().unit("export.Village.B").unwrap().id);
        assert_eq!(
            child.outputs,
            first.graph().unit("export.Village.B").unwrap().outputs
        );
        assert_eq!(child.op.version, "2");
        assert_eq!(child.script, template2.script);
        assert_eq!(child.code, template2.code);
        assert_eq!(second.removals().len(), 1);
        assert_eq!(second.removals()[0].unit(), "export.Village.A");
        assert_eq!(
            second.removals()[0].outputs(),
            first.graph().unit("export.Village.A").unwrap().outputs
        );
        let mut different_owner = template2;
        different_owner.logical_namespace = "/Game/Other".into();
        let foreign =
            RegisteredTemplate::register(&evolved, different_owner, &registry, &[]).unwrap();
        assert!(
            foreign
                .expand(
                    &evolved,
                    &token(&evolved_contract, &["B"]),
                    Some(first.receipt()),
                    &registry,
                    &[]
                )
                .is_err()
        );
    }

    #[test]
    fn batch_owner_collisions_and_foreign_or_changed_receipts_refuse() {
        let (base, registry, template, contract) = fixture();
        let registered =
            RegisteredTemplate::register(&base, template.clone(), &registry, &[]).unwrap();
        let first = registered
            .expand(&base, &token(&contract, &["A"]), None, &registry, &[])
            .unwrap();
        let mut changed = first.graph().declaration().clone();
        changed
            .units
            .iter_mut()
            .find(|u| u.id == "export.Village.A")
            .unwrap()
            .script = "ops/foreign.py".into();
        changed
            .units
            .iter_mut()
            .find(|u| u.id == "export.Village.A")
            .unwrap()
            .code = vec!["ops/foreign.py".into()];
        let foreign = BuildGraph::validate(changed, &registry, &[]).unwrap();
        assert!(
            registered
                .expand(
                    &foreign,
                    &token(&contract, &["B"]),
                    Some(first.receipt()),
                    &registry,
                    &[]
                )
                .err()
                .unwrap()
                .contains("ownership")
        );
        let mut other_template = template.clone();
        other_template.unit_prefix = "other".into();
        let other = RegisteredTemplate::register(&base, other_template, &registry, &[]).unwrap();
        assert!(
            other
                .expand(
                    &base,
                    &token(&contract, &["A"]),
                    Some(first.receipt()),
                    &registry,
                    &[]
                )
                .is_err()
        );
        // The first new member is valid; the second collides with an existing unit owner.
        let mut decl = base.declaration().clone();
        let mut owner = template.child("C", "C.npz", &contract.encoding, None);
        owner.id = "export.Village.C".into();
        owner
            .params
            .insert("payload_member".into(), "foreign.npz".into());
        decl.units.push(owner);
        let occupied = BuildGraph::validate(decl, &registry, &[]).unwrap();
        assert!(
            registered
                .expand(
                    &occupied,
                    &token(&contract, &["B", "C"]),
                    None,
                    &registry,
                    &[]
                )
                .is_err()
        );
        assert_eq!(occupied.declaration().units.len(), 2);
        assert!(occupied.unit("export.Village.B").is_none());
        let mut wrong = contract.clone();
        wrong.adapter_version = "fixture/2".into();
        assert!(
            registered
                .expand(&base, &token(&wrong, &["A"]), None, &registry, &[])
                .is_err()
        );
    }

    #[test]
    fn template_interface_and_staging_alias_mutations_refuse() {
        let (base, registry, template, _) = fixture();
        for staged in ["ops/export.py", "OPS", "output/payload"] {
            let mut bad = template.clone();
            bad.staged_path = staged.into();
            assert!(RegisteredTemplate::register(&base, bad, &registry, &[]).is_err());
        }
        let mut bad = template.clone();
        bad.params
            .insert("payload_member".into(), "other.npz".into());
        assert!(RegisteredTemplate::register(&base, bad, &registry, &[]).is_err());
        let mut bad = template.clone();
        bad.op.version = "unregistered".into();
        assert!(RegisteredTemplate::register(&base, bad, &registry, &[]).is_err());
        let mut bad = template.clone();
        bad.payload_slot = "unregistered".into();
        assert!(RegisteredTemplate::register(&base, bad, &registry, &[]).is_err());
        let mut bad = template;
        bad.files[1].path = "MESH.FBX".into();
        assert!(RegisteredTemplate::register(&base, bad, &registry, &[]).is_err());
    }
}
