//! Normal-caller request preparation. This composes existing declaration/source/worker
//! mechanisms; cache lookup, scheduling and publication stay in their existing owners.
use crate::blender_ops::{
    self, BLENDER_EXPORT_KIND, BLENDER_PLAN_KIND, BlenderExportSpec, BlenderPlanSpec,
};
use crate::explain::{BuildSummary, Recorder};
use crate::failure_policy::Limits;
use crate::graph::{BuildGraph, Target};
use crate::guard_adapter::WorkerLauncher;
use crate::install::{
    CheckoutInstaller, InstallError, InstallPolicy, OwnershipSnapshot, ProjectNamespace,
    ReceiptReader,
};
use crate::leases::ProcessIdentity;
use crate::py_data::{ContentSlotSpec, PyDataClass, PyDataSpec, py_data_validator_identity};
use crate::python_backend::{CacheAccess, PythonBackend, PythonIo};
use crate::python_executor::{PythonExecution, PythonExecutor};
use crate::python_sources::{CapturedSources, capture_sources};
use crate::python_worker::{BLENDER_WORKER_FILES, PYTHON_WORKER_FILES, PythonWorkerBundle};
use crate::results::ResultStore;
use crate::roots::{BuildSession, RootKind, RootStore};
use crate::scheduler::{self, Control, Demand, FinalDemands, Runtime, State};
use crate::schema::{ContentSource, Declaration, Destination, Input, Provenance, Unit};
use crate::source_hashes::SourceHashCache;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::cell::RefCell;
use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;

pub const CONTROL_VERSION: u32 = 1;
pub const MAX_CONTROL_BYTES: usize = 64 * 1024 * 1024;
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
    #[serde(default)]
    pub templates: Vec<crate::plans::ChildTemplate>,
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
    /// Requests MUST be bounded, versioned, duplicate-free and object-only at every
    /// typed record position before any state creation; real array fields remain arrays. The
    /// caller MUST accept only the explicitly supported typed operation contracts;
    /// unsupported formats/groups MUST refuse, never be silently relabeled. Installed
    /// tool facts MUST NOT be supplied as semantic parameters by this controller.
    /// See tests/controller.rs strict_request_refuses_unknown_fields_and_unsupported_ops.
    pub fn parse(bytes: &[u8]) -> Result<Self, String> {
        if bytes.len() > MAX_CONTROL_BYTES {
            return Err("controller request exceeds its size bound".into());
        }
        crate::py_data::validate_py_data_payload("JsonData", "request.json", bytes)
            .map_err(|_| "invalid controller request JSON".to_string())?;
        let document: Value = serde_json::from_slice(bytes)
            .map_err(|_| "invalid controller request JSON".to_string())?;
        object_records(&document)?;
        let request: Self = serde_json::from_value(document)
            .map_err(|_| "invalid controller request shape".to_string())?;
        request.check()?;
        Ok(request)
    }

    pub fn check(&self) -> Result<(), String> {
        if self.version != CONTROL_VERSION || !self.checkout.is_absolute() {
            return Err("unsupported controller version or checkout locator".into());
        }
        ProjectNamespace::new(&self.project).map_err(|error| error.to_string())?;
        if self.project.is_empty()
            || self.targets.is_empty()
            || self.targets.len() > 32768
            || self.declaration.units.is_empty()
            || self.declaration.units.len() > 32768
            || self.allowed_install_roots.is_empty()
        {
            return Err("controller declaration/target bounds are invalid".into());
        }
        let units: BTreeSet<_> = self.declaration.units.iter().map(|unit| &unit.id).collect();
        if self.staged_inputs.keys().collect::<BTreeSet<_>>() != units {
            return Err("controller staged names must cover exactly the declared units".into());
        }
        for unit in &self.declaration.units {
            if unit.op.version != "1"
                || unit
                    .inputs
                    .iter()
                    .any(|input| !matches!(input, Input::Content { .. }))
            {
                return Err("unsupported normal-controller op/input contract".into());
            }
            match unit.op.kind.as_str() {
                "py_data"
                    if unit.output_groups.is_empty()
                        && unit.outputs.iter().all(|item| item.class == "JsonData")
                        && unit.params.is_empty() => {}
                "recipe.python" | "recipe.blender"
                    if unit.output_groups.len() <= 1
                        && unit.outputs.iter().all(|item| item.class == "Data") =>
                {
                    crate::recipe_ops::validate_params(&unit.params)?;
                }
                crate::native_verify::PACKAGE_OP | crate::unreal_controller::VERIFY
                    if unit.output_groups.is_empty()
                        && unit.script == crate::results::zen_cook::VERIFY_SCRIPT => {}
                crate::unreal_controller::RAW_IMPORT
                | crate::unreal_controller::FINISH
                | crate::unreal_controller::AUTHOR
                    if unit.output_groups.is_empty()
                        && (matches!(
                            unit.op.kind.as_str(),
                            crate::unreal_controller::AUTHOR | crate::unreal_controller::FINISH
                        ) || unit.script == crate::unreal_controller::ENTRY) => {}
                kind if crate::native_tool_ops::supports(kind)
                    && unit.output_groups.is_empty()
                    && unit.script == crate::native_tool_ops::ENTRY =>
                {
                    crate::native_tool_ops::validate_params(kind, &unit.params)?;
                }
                crate::encoded_ops::KIND if unit.output_groups.is_empty() => {}
                BLENDER_PLAN_KIND if unit.output_groups.len() == 1 && unit.outputs.is_empty() => {
                    blender_plan_spec(self, unit)?.definition()?;
                }
                BLENDER_EXPORT_KIND if unit.output_groups.is_empty() => {
                    BlenderExportSpec::default().definition()?;
                }
                _ => return Err("unsupported normal-controller data contract".into()),
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

fn blender_plan_spec(request: &ControllerRequest, unit: &Unit) -> Result<BlenderPlanSpec, String> {
    let group = unit
        .output_groups
        .first()
        .ok_or("missing fixed Blender group")?;
    let mut spec = BlenderPlanSpec::new(group.clone());
    for (name, required) in &request.data_contract.content_slots {
        spec.inputs.insert(
            name.clone(),
            crate::validate::InputRule {
                role: crate::validate::InputRole::Content,
                required: *required,
                allow_absent_file: false,
                allow_selector: false,
                require_whole_reason: true,
                item_classes: BTreeSet::from([
                    "Data".into(),
                    "JsonData".into(),
                    "GeometryPayload".into(),
                ]),
            },
        );
    }
    Ok(spec)
}

pub(crate) fn object(value: &Value) -> Result<&Map<String, Value>, String> {
    value
        .as_object()
        .ok_or_else(|| "control record must be a JSON object".into())
}

fn records(value: Option<&Value>) -> Result<Vec<&Value>, String> {
    let Some(Value::Array(values)) = value else {
        return Ok(vec![]);
    };
    for value in values {
        object(value)?;
    }
    Ok(values.iter().collect())
}

/// serde's struct decoder also accepts positional arrays. Like protocol v1, control
/// data requires object-only record positions before typed decoding; real array fields
/// and arbitrary semantic JSON values are left intact. Wrong/missing field types stay
/// serde errors. No record values are interpreted as identity ingredients here.
pub(crate) fn object_records(document: &Value) -> Result<(), String> {
    let request = object(document)?;
    for template in records(request.get("templates"))? {
        let template = object(template)?;
        if let Some(op) = template.get("op") {
            object(op)?;
        }
        records(template.get("files"))?;
        for follower in records(template.get("followers"))? {
            let follower = object(follower)?;
            if let Some(unit) = follower.get("unit") {
                object_records(&serde_json::json!({"declaration":{"units":[unit]}}))?;
            }
            if let Some(stage) = follower.get("staged_inputs") {
                object(stage)?;
            }
        }
    }
    if let Some(contract) = request.get("data_contract") {
        object(contract)?;
    }
    if let Some(declaration) = request.get("declaration") {
        let declaration = object(declaration)?;
        for unit in records(declaration.get("units"))? {
            let unit = object(unit)?;
            if let Some(op) = unit.get("op") {
                object(op)?;
            }
            for input in records(unit.get("inputs"))? {
                let input = object(input)?;
                for field in ["source", "producer"] {
                    if let Some(value) = input.get(field).filter(|value| !value.is_null()) {
                        object(value)?;
                    }
                }
            }
            for item in records(unit.get("outputs"))? {
                let item = object(item)?;
                records(item.get("files"))?;
            }
            records(unit.get("output_groups"))?;
        }
    }
    Ok(())
}

pub struct PreparedController {
    pub graph: BuildGraph,
    pub sources: CapturedSources,
    pub worker: PythonWorkerBundle,
    pub blender_worker: Option<PythonWorkerBundle>,
    pub recipe_workers: Vec<(PythonWorkerBundle, bool)>,
    pub unreal_worker: Option<crate::unreal::UnrealWorkerBundle>,
    pub native_tool_worker: Option<crate::native_tools::NativeToolBundle>,
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
pub(crate) fn registry(request: &ControllerRequest) -> Result<crate::validate::OpRegistry, String> {
    let mut spec = PyDataSpec::new().with_output_classes([PyDataClass::JsonData]);
    for (slot, required) in &request.data_contract.content_slots {
        spec = spec.with_content_slot(slot, ContentSlotSpec::broad(*required));
    }
    let mut registry = BTreeMap::new();
    spec.register(&mut registry)?;
    crate::encoded_ops::register(&mut registry);
    if request
        .declaration
        .units
        .iter()
        .chain(
            request
                .templates
                .iter()
                .flat_map(|template| template.followers.iter().map(|follower| &follower.unit)),
        )
        .any(|u| {
            matches!(
                u.op.kind.as_str(),
                crate::unreal_controller::RAW_IMPORT
                    | crate::unreal_controller::FINISH
                    | crate::unreal_controller::AUTHOR
                    | crate::unreal_controller::VERIFY
                    | crate::native_verify::PACKAGE_OP
            )
        })
    {
        crate::unreal_controller::register(&mut registry, &request.data_contract.content_slots)?;
    }
    crate::native_verify::register(&mut registry, &request.data_contract.content_slots);
    crate::recipe_ops::register(&mut registry, &request.data_contract.content_slots)?;
    crate::native_tool_ops::register(&mut registry, &request.data_contract.content_slots)?;
    if let Some(unit) = request
        .declaration
        .units
        .iter()
        .find(|unit| unit.op.kind == BLENDER_PLAN_KIND)
    {
        blender_plan_spec(request, unit)?.register(&mut registry)?;
    }
    if request
        .declaration
        .units
        .iter()
        .any(|unit| unit.op.kind == BLENDER_EXPORT_KIND)
        || request
            .templates
            .iter()
            .any(|template| template.op.kind == BLENDER_EXPORT_KIND)
    {
        BlenderExportSpec::default().register(&mut registry)?;
    }
    Ok(registry)
}

pub fn prepare(request: &ControllerRequest) -> Result<PreparedController, String> {
    request.check()?;
    let registry = registry(request)?;
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
    for template in &request.templates {
        names.extend(template.code.iter().map(String::as_str));
        for follower in &template.followers {
            names.extend(follower.unit.code.iter().map(String::as_str));
        }
    }
    let sources = capture_sources(&request.checkout, names)?;
    let selected = graph.select(&targets, &sources.snapshot)?;
    let worker_sources = capture_sources(
        &request.checkout.join(WORKER_DIRECTORY),
        PYTHON_WORKER_FILES,
    )?;
    let worker = PythonWorkerBundle::from_snapshot(&worker_sources.snapshot)?;
    let native = selected.order().iter().any(|id| {
        graph.unit(id).is_some_and(|unit| {
            matches!(
                unit.op.kind.as_str(),
                BLENDER_PLAN_KIND | BLENDER_EXPORT_KIND
            )
        })
    });
    let blender_worker = if native {
        let source = capture_sources(
            &request.checkout.join(WORKER_DIRECTORY),
            BLENDER_WORKER_FILES,
        )?;
        Some(PythonWorkerBundle::from_blender_snapshot(&source.snapshot)?)
    } else {
        None
    };
    let mut recipe_workers = Vec::new();
    for (kind, blender) in [("recipe.python", false), ("recipe.blender", true)] {
        if selected
            .order()
            .iter()
            .any(|id| graph.unit(id).is_some_and(|unit| unit.op.kind == kind))
        {
            let names: &[&str] = if blender {
                &crate::recipe_ops::BLENDER_FILES
            } else {
                &crate::recipe_ops::FILES
            };
            let source = capture_sources(
                &request.checkout.join(WORKER_DIRECTORY),
                names.iter().copied(),
            )?;
            recipe_workers.push((
                PythonWorkerBundle::from_recipe_snapshot(&source.snapshot, blender)?,
                blender,
            ));
        }
    }
    let unreal_worker = if selected.order().iter().any(|id| {
        graph.unit(id).is_some_and(|u| {
            matches!(
                u.op.kind.as_str(),
                crate::unreal_controller::RAW_IMPORT
                    | crate::unreal_controller::FINISH
                    | crate::unreal_controller::AUTHOR
                    | crate::unreal_controller::VERIFY
                    | crate::native_verify::PACKAGE_OP
            )
        })
    }) {
        let source = capture_sources(
            &request.checkout.join(WORKER_DIRECTORY),
            crate::unreal::UNREAL_WORKER_FILES,
        )?;
        let files = crate::unreal::UNREAL_WORKER_FILES
            .into_iter()
            .map(|name| match source.snapshot.get(name) {
                Some(crate::validate::SnapshotEntry::File(bytes)) => {
                    Ok((name.to_string(), bytes.clone()))
                }
                _ => Err("missing frozen Unreal worker source"),
            })
            .collect::<Result<BTreeMap<_, _>, _>>()?;
        Some(crate::unreal::UnrealWorkerBundle::from_files(files).map_err(|e| e.to_string())?)
    } else {
        None
    };
    let native_tool_worker = if selected.order().iter().any(|id| {
        graph
            .unit(id)
            .is_some_and(|unit| crate::native_tool_ops::supports(&unit.op.kind))
    }) {
        let source = capture_sources(
            &request.checkout.join(WORKER_DIRECTORY),
            crate::native_tools::NATIVE_TOOL_FILES,
        )?;
        Some(crate::native_tools::NativeToolBundle::from_snapshot(
            &source.snapshot,
        )?)
    } else {
        None
    };
    let mut runtimes = BTreeMap::new();
    for id in selected.order() {
        let unit = graph.unit(id).ok_or("selected unit missing")?;
        let (worker, validator, profile) = if unit.op.kind.starts_with("recipe.") {
            let blender = unit.op.kind == "recipe.blender";
            let bundle = recipe_workers
                .iter()
                .find(|(_, native)| *native == blender)
                .ok_or("missing recipe worker")?;
            (
                bundle.0.identity(),
                if unit.output_groups.is_empty() {
                    crate::recipe_ops::validator()
                } else {
                    let code = unit
                        .code
                        .iter()
                        .map(|name| match sources.snapshot.get(name) {
                            Some(crate::validate::SnapshotEntry::File(bytes)) => {
                                Ok((name.clone(), crate::source_hashes::sha256(bytes)))
                            }
                            _ => Err("missing recipe group code"),
                        })
                        .collect::<Result<BTreeMap<_, _>, _>>()?;
                    crate::recipe_ops::group_validator(&code, &unit.output_groups[0].encoding)?
                },
                if blender {
                    "recipe-blender"
                } else {
                    "recipe-python"
                },
            )
        } else if crate::native_tool_ops::supports(&unit.op.kind) {
            (
                native_tool_worker
                    .as_ref()
                    .ok_or("missing frozen native tool worker")?
                    .identity(),
                crate::native_tool_ops::validator(),
                "native-tool",
            )
        } else if matches!(
            unit.op.kind.as_str(),
            crate::unreal_controller::RAW_IMPORT
                | crate::unreal_controller::FINISH
                | crate::unreal_controller::AUTHOR
                | crate::unreal_controller::VERIFY
                | crate::native_verify::PACKAGE_OP
        ) {
            (
                crate::unreal_controller::worker_identity(
                    unreal_worker.as_ref().ok_or("missing Unreal worker")?,
                ),
                if matches!(
                    unit.op.kind.as_str(),
                    crate::native_verify::PACKAGE_OP | crate::unreal_controller::VERIFY
                ) {
                    crate::results::zen_cook::validator_identity()
                } else {
                    crate::unreal_controller::validator_identity()
                },
                "normal-unreal",
            )
        } else if unit.op.kind == crate::encoded_ops::KIND {
            (
                worker.identity(),
                crate::encoded_ops::identity(&sources.snapshot)?,
                "normal-python-data",
            )
        } else if unit.op.kind == "py_data" {
            (
                worker.identity(),
                py_data_validator_identity(),
                "normal-python-data",
            )
        } else {
            (
                blender_worker
                    .as_ref()
                    .ok_or("missing Blender worker")?
                    .identity(),
                blender_ops::blender_validator_identity(&sources.snapshot)?,
                "normal-blender",
            )
        };
        runtimes.insert(
            id.clone(),
            Runtime {
                worker,
                validator,
                staged_inputs: request.staged_inputs[id].clone(),
                profile: profile.into(),
            },
        );
    }
    let demands = selected
        .roots()
        .iter()
        .map(|id| {
            (
                id.clone(),
                BTreeSet::from([
                    if graph.unit(id).is_some_and(|unit| {
                        unit.outputs
                            .iter()
                            .any(|item| item.destination == Destination::Checkout)
                    }) {
                        Demand::Checkout
                    } else {
                        Demand::Stored
                    },
                ]),
            )
        })
        .collect();
    Ok(PreparedController {
        graph,
        sources,
        worker,
        blender_worker,
        recipe_workers,
        unreal_worker,
        native_tool_worker,
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

/// Execution/control context only; installed interpreter facts never enter A3 ingredients.
#[derive(Clone)]
pub struct ExecutionContext {
    pub cache_root: PathBuf,
    pub interpreter: PathBuf,
    pub blender: Option<PathBuf>,
    pub node: Option<PathBuf>,
    pub ffmpeg: Option<PathBuf>,
    pub ffprobe: Option<PathBuf>,
    pub unreal: Option<crate::unreal_controller::UnrealLocations>,
    pub native_export_project: Option<PathBuf>,
    pub unreal_memory_gib: Option<u32>,
    pub blender_memory_gib: Option<u32>,
    pub unreal_job_seconds: Option<u64>,
    /// Actual controller identity supplied by the normal caller's authoritative OS probe.
    pub owner: ProcessIdentity,
    pub provenance: Provenance,
    pub worktree_id: String,
    pub memory_gib: u32,
    pub limits: Limits,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Finalization {
    NotOpened,
    Complete,
    Incomplete,
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct IoObservation {
    pub cache_opens: usize,
    pub cache_lookups: usize,
    pub staged_jobs: usize,
    pub input_clones: usize,
    /// Observed guard ChildStarted attempts, not successful Runs or a complete count on uncertainty.
    pub observed_worker_attempts: usize,
    pub worker_attempts_by_unit: BTreeMap<String, usize>,
    pub worker_files_written: usize,
    pub publications: usize,
    pub installs: usize,
    pub receipt_writes: usize,
}
impl From<PythonIo> for IoObservation {
    fn from(io: PythonIo) -> Self {
        Self {
            cache_opens: io.cache_opens,
            cache_lookups: io.cache_lookups,
            staged_jobs: io.staged_jobs,
            input_clones: io.input_clones,
            observed_worker_attempts: io.launches,
            worker_attempts_by_unit: io.launches_by_unit,
            worker_files_written: io.worker_files_written,
            publications: io.publications,
            installs: io.installs,
            receipt_writes: io.receipt_writes,
        }
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct ExecutionObservation {
    pub version: u32,
    pub summary: Option<BuildSummary>,
    pub io: IoObservation,
    pub final_requirements_satisfied: bool,
    pub cancellation_requested: bool,
    pub scheduler_error: bool,
    pub source_finalization: Finalization,
    pub root_finalization: Finalization,
}

impl ExecutionObservation {
    fn cancelled_before_work() -> Self {
        Self {
            version: CONTROL_VERSION,
            summary: None,
            io: IoObservation::default(),
            final_requirements_satisfied: false,
            cancellation_requested: true,
            scheduler_error: false,
            source_finalization: Finalization::NotOpened,
            root_finalization: Finalization::NotOpened,
        }
    }
}

/// @cc [owner:fontanierh,label:correctness] normal-controller-existing-engine
/// Execution MUST compose the existing A9 scheduler, PythonBackend/production executor,
/// B3 checkout locks, A7 observer and lazy B4 session. Current MUST NOT open the cache.
/// Root callbacks MUST bind current scheduling labels; source origins MUST finish before
/// partial-session commit(None). Scheduler fulfillment, cancellation and external finalization
/// MUST remain separate observations. No fixture constructor, second scheduler, key encoder,
/// fallback executor or pruning roster is permitted. See controller_cancelled_before_run_keeps_state_absent;
/// real normal first/warm/edit and cancellation proof remain I1-min/C5c pending.
fn execute_static<L: WorkerLauncher + Send>(
    request: &ControllerRequest,
    context: ExecutionContext,
    launcher: L,
    control: &dyn Control,
    group_output: &mut crate::keys::ProducedGroups,
) -> Result<ExecutionObservation, String> {
    request.check()?;
    if context.owner.pid != std::process::id()
        || context.owner.started.is_empty()
        || context.owner.boot.is_empty()
        || !context.cache_root.is_absolute()
        || !context.interpreter.is_absolute()
        || !crate::source_hashes::valid_digest(&context.worktree_id)
        || context.memory_gib == 0
        || context.limits.job.is_zero()
        || context.limits.cleanup.is_zero()
        || !context.limits.overall.is_some_and(|overall| {
            context
                .limits
                .job
                .checked_add(context.limits.cleanup)
                .is_some_and(|minimum| overall >= minimum)
        })
    {
        return Err("invalid normal controller execution context".into());
    }
    if context.unreal_memory_gib.is_some_and(|n| n == 0 || n > 24)
        || context.blender_memory_gib.is_some_and(|n| n == 0 || n > 24)
        || context.unreal_job_seconds.is_some_and(|n| {
            n == 0
                || context.limits.overall.is_none_or(|overall| {
                    std::time::Duration::from_secs(n)
                        .checked_add(context.limits.cleanup)
                        .is_none_or(|minimum| minimum > overall)
                })
        })
    {
        return Err("invalid typed native execution resources".into());
    }
    if control.cancelled() {
        return Ok(ExecutionObservation::cancelled_before_work());
    }
    let PreparedController {
        graph,
        sources,
        worker,
        blender_worker,
        recipe_workers,
        unreal_worker,
        native_tool_worker,
        runtimes,
        targets,
        demands,
    } = prepare(request)?;
    if (blender_worker.is_some() || recipe_workers.iter().any(|(_, blender)| *blender))
        && !context
            .blender
            .as_ref()
            .is_some_and(|path| path.is_absolute())
    {
        return Err("selected Blender units require an absolute execution.blender locator".into());
    }
    if control.cancelled() {
        return Ok(ExecutionObservation::cancelled_before_work());
    }
    let policy = InstallPolicy {
        project: ProjectNamespace::new(&request.project).map_err(|error| error.to_string())?,
        allowed_install_roots: request.allowed_install_roots.clone(),
    };
    let reader = ReceiptReader::open(&request.checkout, policy.clone())
        .map_err(|error| error.to_string())?;
    let guard = reader
        .locks()
        .try_build_exclusive()
        .map_err(|error| error.to_string())?;
    let ownership = OwnershipSnapshot::from_projects([(policy.project.clone(), &graph)])
        .map_err(|error| error.to_string())?;
    reader
        .recover(&guard, &ownership)
        .map_err(|error| error.to_string())?;
    let schedule = scheduler::Request::select(
        &graph,
        &targets,
        &sources.snapshot,
        &sources.versions,
        &runtimes,
        &demands,
    )?;
    let roots: RefCell<Option<BuildSession>> = RefCell::new(None);
    let mut backend = PythonBackend::new(
        &graph,
        schedule.selected(),
        &sources.snapshot,
        &reader,
        &guard,
        &ownership,
        context.owner.clone(),
        context.provenance.clone(),
        || {
            let results = ResultStore::open(&context.cache_root).map_err(InstallError::Cache)?;
            let checkout =
                CheckoutInstaller::open(&request.checkout, &context.cache_root, policy.clone())?;
            Ok(CacheAccess { results, checkout })
        },
        |unit, envelope| {
            let mut session = roots.borrow_mut();
            if session.is_none() {
                let store = RootStore::open(&context.cache_root, &request.project)
                    .map_err(|error| error.to_string())?;
                *session = Some(
                    store
                        .begin_session(
                            RootKind::Worktree {
                                id: context.worktree_id.clone(),
                            },
                            context.provenance.clone(),
                            context.owner.clone(),
                        )
                        .map_err(|error| error.to_string())?,
                );
            }
            session
                .as_mut()
                .ok_or("retention session unavailable")?
                .use_result(unit, &envelope.result.key)
                .map_err(|error| error.to_string())
        },
    );
    let mut executor = PythonExecutor::new(
        launcher,
        PythonExecution {
            interpreter: context.interpreter.clone(),
            bundle: worker,
            profile: "normal-python-data".into(),
            memory_gib: context.memory_gib,
            limits: context.limits,
        },
    );
    if let Some(path) = &context.node {
        executor = executor.with_node(path.clone());
    }
    executor = executor.with_media(context.ffmpeg.clone(), context.ffprobe.clone());
    if let Some(bundle) = blender_worker {
        executor = executor.with_blender(PythonExecution {
            interpreter: context
                .blender
                .clone()
                .ok_or("missing Blender execution locator")?,
            bundle,
            profile: "normal-blender".into(),
            memory_gib: context.blender_memory_gib.unwrap_or(context.memory_gib),
            limits: context.limits,
        });
    }
    for (bundle, blender) in recipe_workers {
        executor = executor.with_recipe(PythonExecution {
            interpreter: if blender {
                context
                    .blender
                    .clone()
                    .ok_or("missing Blender execution locator")?
            } else {
                context.interpreter.clone()
            },
            bundle,
            profile: if blender {
                "recipe-blender".into()
            } else {
                "recipe-python".into()
            },
            memory_gib: if blender {
                context.blender_memory_gib.unwrap_or(context.memory_gib)
            } else {
                context.memory_gib
            },
            limits: context.limits,
        });
    }
    if let Some(bundle) = unreal_worker {
        let locations = context
            .unreal
            .clone()
            .ok_or("native units require execution.unreal context locations")?;
        let mut native_sources = BTreeMap::new();
        for (name, bytes) in bundle.files() {
            native_sources.insert(
                format!("{WORKER_DIRECTORY}/{name}"),
                crate::validate::SnapshotEntry::File(bytes.clone()),
            );
        }
        for name in locations.config_sources.values() {
            native_sources.insert(
                name.clone(),
                sources
                    .snapshot
                    .get(name)
                    .ok_or("native Config source was not declared")?
                    .clone(),
            );
        }
        executor = executor.with_unreal(crate::python_executor::UnrealExecution {
            locations,
            sources: native_sources,
            cache_root: context.cache_root.clone(),
            worker: crate::unreal_controller::worker_identity(&bundle),
            memory_gib: context.unreal_memory_gib.unwrap_or(context.memory_gib),
            limits: Limits {
                job: context
                    .unreal_job_seconds
                    .map(std::time::Duration::from_secs)
                    .unwrap_or(context.limits.job),
                ..context.limits
            },
        });
    }
    if let Some(bundle) = native_tool_worker {
        let engine_root = context
            .unreal
            .as_ref()
            .ok_or("native tools require execution.unreal.engine_root")?
            .engine_root
            .clone();
        executor = executor.with_native_tool(crate::python_executor::NativeToolExecution {
            interpreter: context.interpreter.clone(),
            engine_root,
            bundle,
            zen_state_root: context.cache_root.join("zen-cook"),
            export_project: context.native_export_project.clone(),
            memory_gib: context.unreal_memory_gib.unwrap_or(context.memory_gib),
            limits: Limits {
                job: context
                    .unreal_job_seconds
                    .map(std::time::Duration::from_secs)
                    .unwrap_or(context.limits.job),
                ..context.limits
            },
        });
    }
    let recorder = Recorder::default();
    let report = scheduler::run(
        schedule,
        &mut recorder.backend(&mut backend),
        &mut recorder.executor(&mut executor),
        control,
        &mut SourceHashCache::default(),
    );
    let before_finish = backend.io();
    let (io, source_finalization) = match backend.finish() {
        Ok(io) => (io, Finalization::Complete),
        Err(_) => (before_finish, Finalization::Incomplete),
    };
    let root_finalization = match roots.into_inner() {
        None => Finalization::NotOpened,
        Some(session) => match session.commit(None) {
            Ok(_) => Finalization::Complete,
            Err(_) => Finalization::Incomplete,
        },
    };
    let (summary, final_requirements_satisfied, scheduler_error) = match report {
        Ok(mut report) => {
            *group_output = std::mem::take(&mut report.groups);
            let fulfilled = report.fatal.is_none()
                && report.unsatisfied.is_empty()
                && report.states.values().all(|state| {
                    matches!(
                        state,
                        State::Identity | State::Current | State::Hit | State::Executed(_)
                    )
                });
            (
                Some(recorder.summarize(&report, &BTreeMap::new(), Some(&io.launches_by_unit))?),
                fulfilled,
                false,
            )
        }
        Err(_) => (None, false, true),
    };
    Ok(ExecutionObservation {
        version: CONTROL_VERSION,
        summary,
        io: io.into(),
        final_requirements_satisfied,
        cancellation_requested: control.cancelled(),
        scheduler_error,
        source_finalization,
        root_finalization,
    })
}

fn unresolved_derived(value: &Value) -> bool {
    match value {
        Value::Object(object) => {
            object
                .get("derived_items")
                .is_some_and(|v| v.get("templates").is_some())
                || object.values().any(unresolved_derived)
        }
        Value::Array(values) => values.iter().any(unresolved_derived),
        _ => false,
    }
}

/// Select a sibling by an authored literal prefix transform, never by a guessed unit ID.
fn selected_derived_piece(value: &Value) -> Result<String, String> {
    if let Some(piece) = value.as_str() {
        crate::groups::name(piece)?;
        return Ok(piece.to_string());
    }
    let object = value.as_object().ok_or("invalid selected derived piece")?;
    if object.len() != 2 || !object.contains_key("value") || !object.contains_key("replace_prefix")
    {
        return Err("invalid selected derived piece mapping".into());
    }
    let piece = object["value"]
        .as_str()
        .ok_or("missing mapped piece value")?;
    let mapping = object["replace_prefix"]
        .as_object()
        .ok_or("invalid piece prefix mapping")?;
    if mapping.len() != 2 || !mapping.contains_key("from") || !mapping.contains_key("to") {
        return Err("invalid piece prefix fields".into());
    }
    let from = mapping["from"]
        .as_str()
        .ok_or("invalid source piece prefix")?;
    let to = mapping["to"]
        .as_str()
        .ok_or("invalid target piece prefix")?;
    for name in [piece, from, to] {
        crate::groups::name(name)?;
    }
    let suffix = piece
        .strip_prefix(from)
        .ok_or("selected piece does not have the declared prefix")?;
    let selected = format!("{to}{suffix}");
    crate::groups::name(&selected)?;
    Ok(selected)
}

fn resolve_derived(
    value: &mut Value,
    expanded: &BTreeMap<
        (String, String, String, Option<usize>),
        Vec<(String, String, Vec<String>)>,
    >,
    additions: &mut Vec<(String, String, String, String)>,
) -> Result<(), String> {
    if let Some(descriptor) = value
        .as_object()
        .and_then(|v| v.get("derived_items"))
        .cloned()
    {
        if let Some(templates) = descriptor.get("templates").and_then(Value::as_array) {
            let root = descriptor
                .get("root")
                .and_then(Value::as_str)
                .ok_or("missing derived logical root")?;
            crate::paths::relative_path(root, false)?;
            let start = additions.len();
            let mut rows = Vec::new();
            for template in templates {
                let get = |key| {
                    template
                        .get(key)
                        .and_then(Value::as_str)
                        .ok_or("invalid derived template binding")
                };
                let key = (
                    get("producer")?.to_string(),
                    get("group")?.to_string(),
                    get("unit_prefix")?.to_string(),
                    template
                        .get("follower")
                        .map(|value| {
                            value
                                .as_u64()
                                .and_then(|n| usize::try_from(n).ok())
                                .ok_or("invalid derived follower index")
                        })
                        .transpose()?,
                );
                let Some(children) = expanded.get(&key) else {
                    additions.truncate(start);
                    return Ok(());
                };
                let selected_piece = template
                    .get("piece")
                    .map(selected_derived_piece)
                    .transpose()?;
                if let Some(piece) = selected_piece.as_deref() {
                    crate::paths::relative_path(piece, false)?;
                    if !children.iter().any(|(name, _, _)| name == piece) {
                        return Err("selected derived piece is absent".into());
                    }
                }
                for (piece, child, items) in children {
                    if selected_piece
                        .as_deref()
                        .is_some_and(|selected| selected != piece)
                    {
                        continue;
                    }
                    let item = if let Some(name) = template.get("item") {
                        let name = name.as_str().ok_or("invalid derived item name")?;
                        if !items.iter().any(|item| item == name) {
                            return Err("unknown derived child item".into());
                        }
                        name.to_string()
                    } else {
                        if items.len() != 1 {
                            return Err("derived child requires an explicit item name".into());
                        }
                        items[0].clone()
                    };
                    let slot = format!("derived_{}", additions.len());
                    let logical = format!("{root}/{piece}");
                    rows.push(serde_json::json!({"piece":piece,"root":logical,"slot":slot}));
                    additions.push((slot, child.clone(), logical, item));
                }
            }
            *value = serde_json::json!({"derived_items":{"root":root,"members":rows}});
            return Ok(());
        }
    }
    match value {
        Value::Object(values) => {
            for child in values.values_mut() {
                resolve_derived(child, expanded, additions)?;
            }
        }
        Value::Array(values) => {
            for child in values {
                resolve_derived(child, expanded, additions)?;
            }
        }
        _ => (),
    }
    Ok(())
}

/// Execute discovery prerequisites and derived members through the same A9 engine.
/// Only complete validated groups supply children; unresolved captured rosters never execute.
pub fn execute<L: WorkerLauncher + Send>(
    request: &ControllerRequest,
    context: ExecutionContext,
    mut launcher: L,
    control: &dyn Control,
) -> Result<ExecutionObservation, String> {
    let mut request = request.clone();
    let mut pending = request.templates.clone();
    let mut previous_io = IoObservation::default();
    let mut expanded = BTreeMap::new();
    if pending.len() > 32768 {
        return Err("too many authored templates".into());
    }
    while !pending.is_empty() {
        let registry = registry(&request)?;
        let graph = BuildGraph::validate(
            request.declaration.clone(),
            &registry,
            &request.allowed_install_roots,
        )
        .map_err(|e| e.to_string())?;
        let mut ready = Vec::new();
        for template in &pending {
            let scope = graph.source_scope(&[Target::Unit(template.producer.clone())])?;
            if scope.iter().all(|id| {
                graph
                    .unit(id)
                    .is_some_and(|u| !u.params.values().any(unresolved_derived))
            }) {
                ready.push(template.clone());
            }
        }
        if ready.is_empty() {
            return Err("dynamic discovery has unresolved or cyclic producer dependencies".into());
        }
        let mut phase = request.clone();
        phase.targets = ready
            .iter()
            .map(|t| t.producer.clone())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect();
        let mut groups = crate::keys::ProducedGroups::new();
        let mut observation =
            execute_static(&phase, context.clone(), &mut launcher, control, &mut groups)?;
        add_io(&mut observation.io, &previous_io);
        previous_io = observation.io.clone();
        if !observation.final_requirements_satisfied
            || control.cancelled()
            || !matches!(observation.source_finalization, Finalization::Complete)
            || !matches!(
                observation.root_finalization,
                Finalization::Complete | Finalization::NotOpened
            )
        {
            return Ok(observation);
        }
        let mut graph = graph;
        for template in ready {
            let key = (
                template.producer.clone(),
                template.group.clone(),
                template.unit_prefix.clone(),
                None,
            );
            let group = groups
                .get(&(template.producer.clone(), template.group.clone()))
                .ok_or("successful planner omitted validated complete group")?;
            let registered = crate::plans::RegisteredTemplate::register(
                &graph,
                template.clone(),
                &registry,
                &request.allowed_install_roots,
            )?;
            let expansion = registered.expand(
                &graph,
                group,
                None,
                &registry,
                &request.allowed_install_roots,
            )?;
            let children = group
                .stored()
                .projections
                .keys()
                .map(|piece| (piece.clone(), format!("{}.{piece}", template.unit_prefix)))
                .collect::<Vec<_>>();
            for (piece, _) in &children {
                request
                    .staged_inputs
                    .extend(registered.staged_inputs_for(piece)?);
            }
            request
                .data_contract
                .content_slots
                .entry(template.payload_slot.clone())
                .or_insert(false);
            for index in 0..template.followers.len() {
                let mut members = Vec::new();
                for (piece, export) in &children {
                    let chain =
                        crate::native_chains::instantiate(&template.followers, piece, export)?;
                    let follower = &chain.units[index];
                    members.push((
                        piece.clone(),
                        follower.id.clone(),
                        follower
                            .outputs
                            .iter()
                            .map(|item| item.id.clone())
                            .collect(),
                    ));
                }
                expanded.insert(
                    (key.0.clone(), key.1.clone(), key.2.clone(), Some(index)),
                    members,
                );
            }
            expanded.insert(
                key,
                children
                    .into_iter()
                    .map(|(piece, child)| (piece, child, vec!["asset".into()]))
                    .collect(),
            );
            graph = BuildGraph::validate(
                expansion.graph().declaration().clone(),
                &registry,
                &request.allowed_install_roots,
            )
            .map_err(|e| e.to_string())?;
            pending.retain(|t| t != &template);
        }
        request.declaration = graph.declaration().clone();
        for unit in &mut request.declaration.units {
            let mut additions = Vec::new();
            for value in unit.params.values_mut() {
                resolve_derived(value, &expanded, &mut additions)?;
            }
            for (slot, child, logical, item) in additions {
                if unit.inputs.iter().any(|i| match i {
                    Input::Content { name, .. } | Input::Reference { name, .. } => name == &slot,
                }) {
                    return Err("derived input slot collision".into());
                }
                let staged = format!("inputs/{slot}");
                unit.inputs.push(Input::Content {
                    name: slot.clone(),
                    source: ContentSource::Item { unit: child, item },
                    whole: Some(
                        "The original assembly consumes this complete validated derived child."
                            .into(),
                    ),
                    conditional: None,
                });
                request
                    .staged_inputs
                    .get_mut(&unit.id)
                    .ok_or("missing derived consumer stage map")?
                    .insert(slot.clone(), staged.clone());
                request.data_contract.content_slots.insert(slot, false);
                if let Some(recipe) = unit.params.get_mut("recipe") {
                    recipe
                        .get_mut("paths")
                        .and_then(Value::as_object_mut)
                        .ok_or("derived recipe consumer has no path map")?
                        .insert(logical, staged.into());
                } else if !matches!(
                    unit.op.kind.as_str(),
                    crate::unreal_controller::RAW_IMPORT
                        | crate::unreal_controller::FINISH
                        | crate::unreal_controller::AUTHOR
                        | crate::unreal_controller::VERIFY
                        | crate::native_verify::PACKAGE_OP
                ) {
                    return Err("unsupported derived consumer runtime".into());
                }
            }
        }
    }
    request.templates.clear();
    if request
        .declaration
        .units
        .iter()
        .any(|u| u.params.values().any(unresolved_derived))
    {
        return Err("unresolved derived consumer after complete expansion".into());
    }
    let mut result = execute_static(
        &request,
        context,
        &mut launcher,
        control,
        &mut crate::keys::ProducedGroups::new(),
    )?;
    add_io(&mut result.io, &previous_io);
    Ok(result)
}

fn add_io(current: &mut IoObservation, previous: &IoObservation) {
    current.cache_opens += previous.cache_opens;
    current.cache_lookups += previous.cache_lookups;
    current.staged_jobs += previous.staged_jobs;
    current.input_clones += previous.input_clones;
    current.observed_worker_attempts += previous.observed_worker_attempts;
    current.worker_files_written += previous.worker_files_written;
    current.publications += previous.publications;
    current.installs += previous.installs;
    current.receipt_writes += previous.receipt_writes;
    for (id, count) in &previous.worker_attempts_by_unit {
        *current
            .worker_attempts_by_unit
            .entry(id.clone())
            .or_default() += count;
    }
}

#[cfg(test)]
mod selected_derived_tests {
    use super::*;

    #[test]
    fn a_named_derived_native_uses_only_the_actual_selected_child() {
        let expanded = BTreeMap::from([(
            ("planner".into(), "clips".into(), "clip".into(), Some(1)),
            vec![
                (
                    "Idle".into(),
                    "actual-idle.finish".into(),
                    vec!["animation".into()],
                ),
                (
                    "Glide".into(),
                    "actual-glide.finish".into(),
                    vec!["animation".into()],
                ),
            ],
        )]);
        let declaration = serde_json::json!({"derived_items":{"root":"derived/reference", "templates":[{
            "producer":"planner", "group":"clips", "unit_prefix":"clip", "follower":1,
            "item":"animation", "piece":"Glide"}]}});
        let mut unresolved = declaration.clone();
        let mut additions = Vec::new();
        resolve_derived(&mut unresolved, &BTreeMap::new(), &mut additions).unwrap();
        assert_eq!(unresolved, declaration);
        assert!(additions.is_empty());
        let mut value = declaration.clone();
        resolve_derived(&mut value, &expanded, &mut additions).unwrap();
        assert_eq!(
            additions,
            vec![(
                "derived_0".into(),
                "actual-glide.finish".into(),
                "derived/reference/Glide".into(),
                "animation".into()
            )]
        );
        assert_eq!(value["derived_items"]["members"][0]["piece"], "Glide");
        let mut missing = declaration;
        missing["derived_items"]["templates"][0]["piece"] = "Missing".into();
        assert!(
            resolve_derived(&mut missing, &expanded, &mut Vec::new())
                .unwrap_err()
                .contains("absent")
        );
    }
    #[test]
    fn a_mapped_derived_member_binds_only_the_observed_sibling() {
        let expanded = BTreeMap::from([(
            (
                "lods".into(),
                "geometry".into(),
                "lod-export".into(),
                Some(1),
            ),
            vec![
                (
                    "Tree_LOD1_West".into(),
                    "actual-lod-west.finish".into(),
                    vec!["mesh".into()],
                ),
                (
                    "Tree_LOD1_East".into(),
                    "actual-lod-east.finish".into(),
                    vec!["mesh".into()],
                ),
            ],
        )]);
        let declaration = serde_json::json!({"derived_items":{"root":"derived/lod1","templates":[{
            "producer":"lods","group":"geometry","unit_prefix":"lod-export","follower":1,"item":"mesh",
            "piece":{"value":"Tree_West","replace_prefix":{"from":"Tree","to":"Tree_LOD1"}}
        }]}});
        let mut value = declaration.clone();
        let mut additions = Vec::new();
        resolve_derived(&mut value, &expanded, &mut additions).unwrap();
        assert_eq!(
            additions,
            vec![(
                "derived_0".into(),
                "actual-lod-west.finish".into(),
                "derived/lod1/Tree_LOD1_West".into(),
                "mesh".into()
            )]
        );
        let mut wrong = declaration.clone();
        wrong["derived_items"]["templates"][0]["piece"]["value"] = "Other_West".into();
        assert!(
            resolve_derived(&mut wrong, &expanded, &mut Vec::new())
                .unwrap_err()
                .contains("prefix")
        );
        let mut missing = declaration.clone();
        missing["derived_items"]["templates"][0]["piece"]["value"] = "Tree_North".into();
        assert!(
            resolve_derived(&mut missing, &expanded, &mut Vec::new())
                .unwrap_err()
                .contains("absent")
        );
        let mut unexpanded = declaration.clone();
        resolve_derived(&mut unexpanded, &BTreeMap::new(), &mut Vec::new()).unwrap();
        assert_eq!(unexpanded, declaration);
        assert!(
            selected_derived_piece(&serde_json::json!({"value":"Tree_West", "replace_prefix":{
            "from":"Tree", "to":"../foreign"}}))
            .is_err()
        );
    }
}
