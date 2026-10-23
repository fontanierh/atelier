//! Pure target closure over an owned, A2-validated declaration. No dispatch or I/O.
use crate::schema::{ContentSource, Declaration, Input, Unit};
use crate::validate::{
    self, OpRegistry, SourceSnapshot, ValidatedDeclaration, ValidatedStructure, ValidationError,
};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Target {
    All,
    Unit(String),
    /// A unit ID or a dot-delimited namespace, never an arbitrary string prefix.
    Prefix(String),
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum EdgeRole {
    Content,
    Reference,
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum DependencyOutput {
    Item(String),
    GroupMember { group: String, piece: String },
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct Dependency {
    pub producer: String,
    pub consumer: String,
    pub output: DependencyOutput,
    pub input: String,
    pub role: EdgeRole,
}

#[derive(Clone, Debug)]
pub struct SelectedGraph {
    /// Explicit target matches, distinct from their transitive prerequisites.
    roots: BTreeSet<String>,
    /// Unique dependency-first unit IDs, deterministic across declaration order.
    validated: ValidatedDeclaration,
    dependencies: Vec<Dependency>,
}

pub struct BuildGraph {
    declaration: Declaration,
    structure: ValidatedStructure,
    dependencies: Vec<Dependency>,
    parents: BTreeMap<String, BTreeSet<String>>,
}

impl BuildGraph {
    /// Own the globally checked structure; source observations wait for target selection.
    pub fn validate(
        declaration: Declaration,
        registry: &OpRegistry,
        allowed_install_roots: &[String],
    ) -> Result<Self, ValidationError> {
        let structure =
            validate::validate_structure(&declaration, registry, allowed_install_roots)?;
        let mut dependencies = Vec::new();
        let mut parents = BTreeMap::new();
        for unit in &declaration.units {
            let mut unit_parents = BTreeSet::new();
            for input in &unit.inputs {
                let (name, producer, output, role) = match input {
                    Input::Content {
                        name,
                        source: ContentSource::Item { unit, item },
                        ..
                    } => (
                        name,
                        unit,
                        DependencyOutput::Item(item.clone()),
                        EdgeRole::Content,
                    ),
                    Input::Content {
                        name,
                        source: ContentSource::GroupMember { unit, group, piece },
                        ..
                    } => (
                        name,
                        unit,
                        DependencyOutput::GroupMember {
                            group: group.clone(),
                            piece: piece.clone(),
                        },
                        EdgeRole::Content,
                    ),
                    Input::Reference {
                        name,
                        producer: Some(producer),
                        ..
                    } => (
                        name,
                        &producer.unit,
                        DependencyOutput::Item(producer.item.clone()),
                        EdgeRole::Reference,
                    ),
                    _ => continue,
                };
                unit_parents.insert(producer.clone());
                dependencies.push(Dependency {
                    producer: producer.clone(),
                    consumer: unit.id.clone(),
                    output,
                    input: name.clone(),
                    role,
                });
            }
            parents.insert(unit.id.clone(), unit_parents);
        }
        dependencies.sort();
        Ok(Self {
            declaration,
            structure,
            dependencies,
            parents,
        })
    }

    pub fn declaration(&self) -> &Declaration {
        &self.declaration
    }
    pub fn unit(&self, id: &str) -> Option<&Unit> {
        self.declaration.units.iter().find(|unit| unit.id == id)
    }

    /// @cc [owner:fontanierh,label:correctness] selected-target-closure
    /// Selection MUST include every transitive content and declared reference producer,
    /// exclude unrelated units, retain role/item identity and order prerequisites first.
    /// Unknown/empty selections MUST refuse. No selection may dispatch/materialise work.
    /// See tests/graph.rs; dynamic expansion and scheduler proof remain A4b/A9.
    pub fn select(
        &self,
        targets: &[Target],
        snapshot: &SourceSnapshot,
    ) -> Result<SelectedGraph, String> {
        if targets.is_empty() {
            return Err("no targets selected".into());
        }
        let mut roots = BTreeSet::new();
        for target in targets {
            let matches: BTreeSet<_> = self
                .parents
                .keys()
                .filter(|id| match target {
                    Target::All => true,
                    Target::Unit(selected) => *id == selected,
                    Target::Prefix(prefix) => {
                        !prefix.is_empty()
                            && (*id == prefix
                                || id
                                    .strip_prefix(prefix.as_str())
                                    .is_some_and(|tail| tail.starts_with('.')))
                    }
                })
                .cloned()
                .collect();
            if matches.is_empty() {
                return Err(format!("target matches no units: {target:?}"));
            }
            roots.extend(matches);
        }
        let mut included = roots.clone();
        let mut pending: Vec<_> = roots.iter().cloned().collect();
        while let Some(id) = pending.pop() {
            for parent in &self.parents[&id] {
                if included.insert(parent.clone()) {
                    pending.push(parent.clone());
                }
            }
        }
        Ok(SelectedGraph {
            roots,
            validated: validate::observe_selected(
                &self.declaration,
                &self.structure,
                snapshot,
                &included,
            )
            .map_err(|error| error.to_string())?,
            dependencies: self
                .dependencies
                .iter()
                .filter(|edge| included.contains(&edge.consumer))
                .cloned()
                .collect(),
        })
    }
}

impl SelectedGraph {
    pub fn roots(&self) -> &BTreeSet<String> {
        &self.roots
    }
    pub fn order(&self) -> &[String] {
        &self.validated.order
    }
    pub fn dependencies(&self) -> &[Dependency] {
        &self.dependencies
    }
    pub fn validation(&self) -> &ValidatedDeclaration {
        &self.validated
    }
}
