//! Normal-caller request preparation. This composes existing declaration/source/worker
//! mechanisms; cache lookup, scheduling and publication stay in their existing owners.
use crate::graph::{BuildGraph, Target};
use crate::py_data::{ContentSlotSpec, PyDataClass, PyDataSpec, py_data_validator_identity};
use crate::python_sources::{CapturedSources, capture_sources};
use crate::python_worker::{PYTHON_WORKER_FILES, PythonWorkerBundle};
use crate::scheduler::{Demand, FinalDemands, Runtime};
use crate::schema::{ContentSource, Declaration, Input};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;

pub const CONTROL_VERSION: u32 = 1;
pub const MAX_CONTROL_BYTES: usize = 2 * 1024 * 1024;
const WORKER_DIRECTORY: &str = "platform/studio/atelier/build_v2";

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DataContract {
    /// Explicit implementation-owned slot rules, never guessed from observed files.
    pub content_slots: BTreeMap<String, bool>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ControllerRequest {
    pub version: u32,
    pub checkout: PathBuf,
    pub project: String,
    pub allowed_install_roots: Vec<String>,
    pub declaration: Declaration,
    pub targets: Vec<String>,
    pub data_contract: DataContract,
    pub staged_inputs: BTreeMap<String, BTreeMap<String, String>>,
}

impl ControllerRequest {
    /// @cc [owner:fontanierh,label:correctness] bounded-normal-controller-request
    /// Requests MUST be bounded, versioned and strict before any state creation. The
    /// initial caller MUST accept only explicit fixed JsonData/py_data declarations;
    /// unsupported formats/groups MUST refuse, never be silently relabeled. Installed
    /// tool facts MUST NOT be supplied as semantic parameters by this controller.
    /// See tests/controller.rs strict_request_refuses_unknown_fields_and_unsupported_ops.
    pub fn parse(bytes: &[u8]) -> Result<Self, String> {
        if bytes.len() > MAX_CONTROL_BYTES {
            return Err("controller request exceeds its size bound".into());
        }
        let request: Self = serde_json::from_slice(bytes)
            .map_err(|_| "invalid controller request shape".to_string())?;
        request.check()?;
        Ok(request)
    }

    pub fn check(&self) -> Result<(), String> {
        if self.version != CONTROL_VERSION || !self.checkout.is_absolute() {
            return Err("unsupported controller version or checkout locator".into());
        }
        if self.project.is_empty()
            || self.targets.is_empty()
            || self.targets.len() > 256
            || self.declaration.units.is_empty()
            || self.declaration.units.len() > 256
            || self.allowed_install_roots.is_empty()
        {
            return Err("controller declaration/target bounds are invalid".into());
        }
        let units: BTreeSet<_> = self.declaration.units.iter().map(|unit| &unit.id).collect();
        if self.staged_inputs.keys().collect::<BTreeSet<_>>() != units {
            return Err("controller staged names must cover exactly the declared units".into());
        }
        for unit in &self.declaration.units {
            if unit.op.kind != "py_data"
                || unit.op.version != "1"
                || !unit.output_groups.is_empty()
                || unit.outputs.iter().any(|item| item.class != "JsonData")
                || !unit.params.is_empty()
                || unit
                    .inputs
                    .iter()
                    .any(|input| !matches!(input, Input::Content { .. }))
            {
                return Err("unsupported normal-controller data contract".into());
            }
            let slots: BTreeSet<_> = unit
                .inputs
                .iter()
                .map(|input| match input {
                    Input::Content { name, .. } | Input::Reference { name, .. } => name,
                })
                .collect();
            let staged = &self.staged_inputs[&unit.id];
            if staged.keys().collect::<BTreeSet<_>>() != slots {
                return Err(
                    "controller staged paths must cover exactly the unit input slots".into(),
                );
            }
            crate::keys::safe_staged_paths(staged, &unit.code)?;
        }
        Ok(())
    }
}

pub struct PreparedController {
    pub graph: BuildGraph,
    pub sources: CapturedSources,
    pub worker: PythonWorkerBundle,
    pub runtimes: BTreeMap<String, Runtime>,
    pub targets: Vec<Target>,
    pub demands: BTreeMap<String, FinalDemands>,
}

#[derive(Clone, Debug, Serialize)]
pub struct PlanObservation {
    pub version: u32,
    pub selected: Vec<String>,
    /// No readonly store accessor is assumed. This is never a fabricated miss/hit.
    pub reuse: &'static str,
}

/// @cc [owner:fontanierh,label:correctness] normal-controller-shared-preparation
/// Preparation MUST use A4 structural/selected validation, explicit nofollow source
/// capture and the exact frozen Python worker bundle. It MUST NOT create checkout,
/// cache, root, lease, job or helper state, or perform output materialization. Plan
/// reuse status MUST remain unknown without authoritative readonly lookup. See
/// tests/controller.rs prepare_plan_has_no_state_writes_and_uses_existing_worker_identity.
pub fn prepare(request: &ControllerRequest) -> Result<PreparedController, String> {
    request.check()?;
    let mut spec = PyDataSpec::new().with_output_classes([PyDataClass::JsonData]);
    for (slot, required) in &request.data_contract.content_slots {
        spec = spec.with_content_slot(slot, ContentSlotSpec::broad(*required));
    }
    let mut registry = BTreeMap::new();
    spec.register(&mut registry)?;
    let graph = BuildGraph::validate(
        request.declaration.clone(),
        &registry,
        &request.allowed_install_roots,
    )
    .map_err(|error| error.to_string())?;
    let targets: Vec<_> = request.targets.iter().cloned().map(Target::Unit).collect();
    let source_scope = graph.source_scope(&targets)?;
    let mut names = BTreeSet::new();
    for unit in request
        .declaration
        .units
        .iter()
        .filter(|unit| source_scope.contains(&unit.id))
    {
        names.extend(unit.code.iter().map(String::as_str));
        for input in &unit.inputs {
            if let Input::Content {
                source: ContentSource::File { path, .. },
                ..
            } = input
            {
                names.insert(path.as_str());
            }
        }
    }
    let sources = capture_sources(&request.checkout, names)?;
    let selected = graph.select(&targets, &sources.snapshot)?;
    let worker_sources = capture_sources(
        &request.checkout.join(WORKER_DIRECTORY),
        PYTHON_WORKER_FILES,
    )?;
    let worker = PythonWorkerBundle::from_snapshot(&worker_sources.snapshot)?;
    let mut runtimes = BTreeMap::new();
    for id in selected.order() {
        runtimes.insert(
            id.clone(),
            Runtime {
                worker: worker.identity(),
                validator: py_data_validator_identity(),
                staged_inputs: request.staged_inputs[id].clone(),
                profile: "normal-python-data".into(),
            },
        );
    }
    let demands = selected
        .roots()
        .iter()
        .map(|id| (id.clone(), BTreeSet::from([Demand::Checkout])))
        .collect();
    Ok(PreparedController {
        graph,
        sources,
        worker,
        runtimes,
        targets,
        demands,
    })
}

impl PreparedController {
    pub fn plan(&self) -> Result<PlanObservation, String> {
        let selected = self.graph.select(&self.targets, &self.sources.snapshot)?;
        Ok(PlanObservation {
            version: CONTROL_VERSION,
            selected: selected.order().to_vec(),
            reuse: "unknown_readonly_store_unavailable",
        })
    }
}

pub fn source_identity() -> Option<&'static str> {
    option_env!("ATELIER_CONTROLLER_SOURCE_SHA256")
        .filter(|value| crate::source_hashes::valid_digest(value))
}
