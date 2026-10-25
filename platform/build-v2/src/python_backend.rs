//! Concrete fixed-output Python authority for the static A9 scheduler.
//! Lifecycle, key encoding, snapshots, publication and installation remain owned by their adapters.
#[cfg(all(test, target_os = "macos"))]
#[path = "../tests/support/python_backend_cases.rs"]
mod tests;
use crate::blender_ops::{self, BLENDER_EXPORT_KIND, BLENDER_PLAN_KIND, BlenderPlanSpec};
use crate::checkout_locks::BuildGuard;
use crate::completion::{CompletionWork, FrozenCompletion};
use crate::graph::{BuildGraph, SelectedGraph};
use crate::groups::ValidatedGroup;
use crate::install::{
    CheckoutInstaller, CurrentIdentities, InstallError, LeaseIdentity, OwnershipSnapshot,
    ReceiptReader, RestoreLookup, RestorePlan,
};
use crate::integrity::{
    CompletionDecision, LocalOutputStatus, LookupDecision, NonHitReason, classify_completion,
    classify_lookup_result,
};
use crate::keys::{InputPayload, PreparedInput, PreparedUnit};
use crate::leases::ProcessIdentity;
use crate::py_data::{check_py_data_unit_identity, validate_py_data_unit_outputs};
use crate::results::{
    RecordedIdentities, ResultEnvelope, ResultError, ResultStore, WriteTransaction,
};
use crate::scheduler::{
    Backend, CheckedView, Demand, Effects, FinalDemands, InputFailure, Lookup, Publication,
    Published, StagedInputs, Work,
};
use crate::schema::{ContentSource, Destination, Input, Provenance, StoredItem};
use crate::staging::{self, ObjectSource, SourceError, SourceErrorKind, StageError, StagedJob};
use crate::store::ObjectDigest;
use crate::validate::SourceSnapshot;
use std::cell::RefCell;
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;
use std::rc::Rc;

/// Counters describe real adapter operations, separate from the scheduler's semantic counters.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct PythonIo {
    pub cache_opens: usize,
    pub cache_lookups: usize,
    pub staged_jobs: usize,
    pub input_clones: usize,
    pub launches: usize,
    /// Complete lifecycle worker-attempt observations only; a missing submitted unit is unknown.
    pub launches_by_unit: BTreeMap<String, usize>,
    pub worker_files_written: usize,
    pub publications: usize,
    pub installs: usize,
    pub receipt_writes: usize,
}

fn validator_identity(unit: &PreparedUnit) -> crate::keys::ImplementationIdentity {
    crate::keys::ImplementationIdentity {
        version: unit.ingredients().validator_version.clone(),
        digest: unit.ingredients().validator_digest.clone(),
    }
}
fn check_unit_identity(unit: &PreparedUnit) -> Result<(), String> {
    match unit.ingredients().op.kind.as_str() {
        "recipe.python" | "recipe.blender" => crate::recipe_ops::check(unit),
        crate::encoded_ops::KIND => crate::encoded_ops::check(unit),
        crate::unreal_controller::RAW_IMPORT
        | crate::unreal_controller::FINISH
        | crate::unreal_controller::AUTHOR => crate::unreal_controller::check_unit(unit),
        kind if crate::native_tool_ops::supports(kind) => crate::native_tool_ops::check(unit),
        "py_data" => check_py_data_unit_identity(unit),
        kind @ (BLENDER_PLAN_KIND | BLENDER_EXPORT_KIND) => {
            blender_ops::check_blender_identity(unit, kind, &validator_identity(unit))?;
            if kind == BLENDER_PLAN_KIND {
                let contract = unit
                    .ingredients()
                    .output_groups
                    .first()
                    .ok_or("missing Blender group")?;
                BlenderPlanSpec::new(contract.clone()).validate_ingredients(unit.ingredients())
            } else {
                blender_ops::BlenderExportSpec::default().validate_ingredients(unit.ingredients())
            }
        }
        _ => Err("unregistered executable op".into()),
    }
}
fn validate_fixed_outputs(
    unit: &PreparedUnit,
    outputs: &[crate::results::FrozenOutput<'_>],
    staged: &StagedJob,
) -> Result<(), String> {
    match unit.ingredients().op.kind.as_str() {
        "recipe.python" | "recipe.blender" => crate::recipe_ops::validate_outputs(unit, outputs),
        crate::encoded_ops::KIND => crate::encoded_ops::validate_outputs(unit, outputs, staged),
        crate::unreal_controller::RAW_IMPORT
        | crate::unreal_controller::FINISH
        | crate::unreal_controller::AUTHOR => {
            crate::unreal_controller::validate_outputs(unit, outputs)
        }
        kind if crate::native_tool_ops::supports(kind) => {
            crate::native_tool_ops::validate_outputs(unit, outputs)
        }
        "py_data" => validate_py_data_unit_outputs(unit, outputs),
        BLENDER_EXPORT_KIND => {
            blender_ops::validate_blender_export_outputs(unit, &validator_identity(unit), outputs)
        }
        BLENDER_PLAN_KIND if outputs.is_empty() => check_unit_identity(unit),
        _ => Err("fixed output set outside registered op".into()),
    }
}

/// Only this backend constructs a checked view. The origin remains private and sealed.
pub struct PythonChecked {
    unit: String,
    key: String,
    items: Vec<StoredItem>,
    current: bool,
    groups: BTreeMap<String, ValidatedGroup>,
}

/// Caller-owned cache and checkout policy; opening either stays lazy behind Current.
pub struct CacheAccess {
    pub results: ResultStore,
    pub checkout: CheckoutInstaller,
}

enum Origin {
    Current(CurrentIdentities),
    Recorded {
        transaction: WriteTransaction,
        record: RecordedIdentities,
        current: Option<CurrentIdentities>,
    },
    Cached {
        transaction: WriteTransaction,
        envelope: ResultEnvelope,
    },
    Local(FrozenCompletion),
    Installed(RestorePlan),
}

struct SelectedSource {
    group: Option<String>,
    producer: String,
    item: String,
    input: PreparedInput,
}

struct PythonSources<'a> {
    origins: RefCell<&'a mut BTreeMap<String, Origin>>,
    prepared: &'a BTreeMap<String, PreparedUnit>,
    reader: &'a ReceiptReader,
    guard: &'a BuildGuard,
    selected: BTreeMap<String, SelectedSource>,
    io: &'a Rc<RefCell<PythonIo>>,
}

fn same_view(input: &PreparedInput, stored: &StoredItem) -> Result<(), String> {
    let InputPayload::Item {
        logical_path,
        class,
        files,
    } = &input.payload
    else {
        return Err("selected source is not an item input".into());
    };
    let mut expected = files.clone();
    let mut actual = stored.files.clone();
    expected.sort_by(|a, b| a.path.cmp(&b.path));
    actual.sort_by(|a, b| a.path.cmp(&b.path));
    if *logical_path != stored.item.logical_path
        || *class != stored.item.class
        || expected != actual
    {
        return Err("selected source differs from prepared input view".into());
    }
    Ok(())
}

fn agree_current(current: &CurrentIdentities, outputs: &[StoredItem]) -> Result<(), String> {
    for old in current.items() {
        let new = outputs
            .iter()
            .find(|item| item.item.id == old.item.id)
            .ok_or("Current item missing from complete output manifest")?;
        let mut before = old.files.clone();
        let mut after = new.files.clone();
        before.sort_by(|a, b| a.path.cmp(&b.path));
        after.sort_by(|a, b| a.path.cmp(&b.path));
        if old.item != new.item || before != after || new.external_locator.is_some() {
            return Err("same-key Current and produced output content disagree".into());
        }
    }
    Ok(())
}

impl PythonSources<'_> {
    fn access(
        &self,
        selected: &SelectedSource,
        digest: &ObjectDigest,
        destination: Option<&Path>,
    ) -> Result<(), SourceError> {
        let refusal = |kind, message: String| SourceError {
            kind,
            digest: digest.clone(),
            message,
        };
        let use_source = |source: &dyn ObjectSource| match destination {
            Some(path) => source.clone_object(digest, path),
            None => Ok(()),
        };
        let mut origins = self.origins.borrow_mut();
        let origin = origins.get_mut(&selected.producer).ok_or_else(|| {
            refusal(
                SourceErrorKind::Unavailable,
                "producer source authority absent".into(),
            )
        })?;
        let stored = |envelope: &ResultEnvelope| {
            if let Some(group) = &selected.group {
                let contract = envelope
                    .result
                    .ingredients
                    .output_groups
                    .iter()
                    .find(|c| &c.id == group)
                    .ok_or_else(|| {
                        refusal(
                            SourceErrorKind::Changed,
                            "selected group contract absent".into(),
                        )
                    })?;
                let stored = envelope
                    .result
                    .output_groups
                    .iter()
                    .find(|g| &g.id == group)
                    .ok_or_else(|| {
                        refusal(
                            SourceErrorKind::Changed,
                            "selected group metadata absent".into(),
                        )
                    })?;
                let identity = crate::groups::recorded_identity(contract, stored)
                    .map_err(|message| refusal(SourceErrorKind::Changed, message))?;
                let item = identity
                    .project(&selected.item)
                    .map_err(|message| refusal(SourceErrorKind::Changed, message))?;
                same_view(&selected.input, &item)
                    .map_err(|message| refusal(SourceErrorKind::Changed, message))
            } else {
                let item = envelope
                    .result
                    .outputs
                    .iter()
                    .find(|item| item.item.id == selected.item)
                    .ok_or_else(|| {
                        refusal(SourceErrorKind::Unavailable, "selected item absent".into())
                    })?;
                same_view(&selected.input, item)
                    .map_err(|message| refusal(SourceErrorKind::Changed, message))
            }
        };
        let outcome =
            match origin {
                Origin::Current(observed) => {
                    let producer = self.prepared.get(&selected.producer).ok_or_else(|| {
                        refusal(
                            SourceErrorKind::Unavailable,
                            "prepared producer absent".into(),
                        )
                    })?;
                    if observed.key() != producer.key() {
                        return Err(refusal(
                            SourceErrorKind::Changed,
                            "Current identity changed".into(),
                        ));
                    }
                    let current = self
                        .reader
                        .pin_current_sources(self.guard, producer)
                        .map_err(|error| refusal(SourceErrorKind::Changed, error.to_string()))?
                        .ok_or_else(|| {
                            refusal(
                                SourceErrorKind::Changed,
                                "producer is no longer Current".into(),
                            )
                        })?;
                    use_source(
                        &current.objects_for(&[&selected.input]).map_err(|error| {
                            refusal(SourceErrorKind::Changed, error.to_string())
                        })?,
                    )
                }
                Origin::Recorded {
                    transaction,
                    record,
                    current,
                } => {
                    stored(record.result())?;
                    if current.as_ref().is_some_and(|current| {
                        current
                            .items()
                            .iter()
                            .any(|item| item.item.id == selected.item)
                    }) {
                        let producer = self.prepared.get(&selected.producer).ok_or_else(|| {
                            refusal(
                                SourceErrorKind::Unavailable,
                                "prepared producer absent".into(),
                            )
                        })?;
                        let pinned = self
                            .reader
                            .pin_current_sources(self.guard, producer)
                            .map_err(|error| refusal(SourceErrorKind::Changed, error.to_string()))?
                            .ok_or_else(|| {
                                refusal(
                                    SourceErrorKind::Changed,
                                    "producer is no longer Current".into(),
                                )
                            })?;
                        use_source(&pinned.objects_for(&[&selected.input]).map_err(|error| {
                            refusal(SourceErrorKind::Changed, error.to_string())
                        })?)
                    } else {
                        use_source(
                            &transaction
                                .pin_recorded_items(record, &[selected.item.as_str()])
                                .map_err(|error| {
                                    refusal(SourceErrorKind::Unavailable, error.to_string())
                                })?,
                        )
                    }
                }
                Origin::Cached {
                    transaction,
                    envelope,
                } => {
                    stored(envelope)?;
                    use_source(&transaction.pinned_objects())
                }
                Origin::Local(completion) => use_source(
                    &completion
                        .objects_for(&[&selected.input])
                        .map_err(|message| {
                            refusal(SourceErrorKind::Changed, message.to_string())
                        })?,
                ),
                Origin::Installed(plan) => {
                    stored(plan.result())?;
                    if let Some(completion) = plan.local_completion() {
                        use_source(&completion.objects_for(&[&selected.input]).map_err(
                            |message| refusal(SourceErrorKind::Changed, message.to_string()),
                        )?)
                    } else {
                        use_source(&plan.cached_sources().ok_or_else(|| {
                            refusal(
                                SourceErrorKind::Unavailable,
                                "installed source custody already finished".into(),
                            )
                        })?)
                    }
                }
            };
        if outcome.is_ok() && destination.is_some() {
            self.io.borrow_mut().input_clones += 1;
        }
        outcome
    }
}

impl ObjectSource for PythonSources<'_> {
    fn clone_object(&self, digest: &ObjectDigest, destination: &Path) -> Result<(), SourceError> {
        let selected = self
            .selected
            .get(digest.as_hex())
            .ok_or_else(|| SourceError {
                kind: SourceErrorKind::Unavailable,
                digest: digest.clone(),
                message: "digest outside selected input views".into(),
            })?;
        self.access(selected, digest, Some(destination))
    }
}

/// The original optional CAS miss ticket; local write custody starts before staging, not at Run.
pub struct PythonTicket {
    transaction: Option<WriteTransaction>,
    local: Option<CompletionWork>,
    cache_failure: Option<ResultError>,
    current: Option<CurrentIdentities>,
}

pub struct PythonInputs {
    // Same open description as the existing build guard; monitor custody only.
    pub(crate) custody: std::fs::File,
    pub(crate) staged: StagedJob,
    pub(crate) io: Rc<RefCell<PythonIo>>,
}

/// Only the lifecycle adapter issues this after a completed reply AND confirmed cleanup.
pub struct PythonCompletion {
    pub(crate) reported: Vec<String>,
}
impl PythonTicket {
    pub(crate) fn register(&mut self, process: &ProcessIdentity) -> Result<(), String> {
        let local = self
            .local
            .as_mut()
            .ok_or("local lease missing before Run")?;
        register_python_worker(local, self.transaction.as_mut(), process)
    }
}

/// @cc [owner:fontanierh,label:safety] python-worker-lease-registration
/// The caller MUST bind the matching current unit's original leases and the actual
/// guard-observed identity. This only appends retention claims (local first, then the optional
/// CAS lease) and validates no identity, cleanup or availability. An Err MUST forbid Run and
/// keeps any earlier local success or CAS failure claims. See
/// tests/support/python_backend_cases.rs
/// (`actual_python_first_build_and_current_noop_have_real_zero_launch_and_write_evidence`) and
/// examples/resident_window.rs.
pub fn register_python_worker(
    local: &mut CompletionWork,
    transaction: Option<&mut WriteTransaction>,
    process: &ProcessIdentity,
) -> Result<(), String> {
    local
        .add_worker(process.clone())
        .map_err(|error| error.to_string())?;
    if let Some(transaction) = transaction {
        transaction
            .add_worker(process.clone())
            .map_err(|error| error.to_string())?;
    }
    Ok(())
}

pub struct PythonBackend<'a> {
    graph: &'a BuildGraph,
    snapshot: &'a SourceSnapshot,
    reader: &'a ReceiptReader,
    guard: &'a BuildGuard,
    ownership: &'a OwnershipSnapshot,
    owner: ProcessIdentity,
    provenance: Provenance,
    open_cache: Box<dyn FnMut() -> Result<CacheAccess, InstallError> + 'a>,
    root: Box<dyn FnMut(&str, &ResultEnvelope) -> Result<(), String> + 'a>,
    origins: BTreeMap<String, Origin>,
    prepared: BTreeMap<String, PreparedUnit>,
    needed_items: BTreeMap<String, BTreeSet<String>>,
    io: Rc<RefCell<PythonIo>>,
}

impl<'a> PythonBackend<'a> {
    /// @cc [owner:fontanierh,label:correctness] current-recorded-selected-identity
    /// Selected content needs MUST come from A4's selected edges. Current covers Checkout items
    /// only; needed store-only sibling identities MUST come from exact recorded metadata or the
    /// ordinary producer. Unneeded siblings MUST NOT force cache availability. Combined final
    /// Root callbacks MUST receive the current scheduling unit ID separately from a reused winner
    /// record label; see renamed_unit_roots_current_scheduling_name_with_old_winner_label.
    /// Stored/Checkout requirements MUST independently prove strict storage and revalidated Current,
    /// refuse same-key content disagreement, and avoid rewriting healthy checkout files.
    /// See mixed_current_and_recorded_identity_resolves_final_hit_without_store_sibling_bytes and
    /// dual_explicit_stored_checkout_hit_preserves_healthy_current_files_and_receipts in tests/support/python_backend_cases.rs.
    pub fn new(
        graph: &'a BuildGraph,
        selected: &SelectedGraph,
        snapshot: &'a SourceSnapshot,
        reader: &'a ReceiptReader,
        guard: &'a BuildGuard,
        ownership: &'a OwnershipSnapshot,
        owner: ProcessIdentity,
        provenance: Provenance,
        open_cache: impl FnMut() -> Result<CacheAccess, InstallError> + 'a,
        root: impl FnMut(&str, &ResultEnvelope) -> Result<(), String> + 'a,
    ) -> Self {
        let mut needed_items: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
        for edge in selected.dependencies() {
            if matches!(edge.role, crate::graph::EdgeRole::Content) {
                if let crate::graph::DependencyOutput::Item(item) = &edge.output {
                    needed_items
                        .entry(edge.producer.clone())
                        .or_default()
                        .insert(item.clone());
                }
            }
        }
        Self {
            graph,
            snapshot,
            reader,
            guard,
            ownership,
            owner,
            provenance,
            open_cache: Box::new(open_cache),
            root: Box::new(root),
            origins: BTreeMap::new(),
            prepared: BTreeMap::new(),
            needed_items,
            io: Rc::new(RefCell::new(PythonIo::default())),
        }
    }

    fn unit_id(unit: &PreparedUnit) -> String {
        unit.request("identity", "").unit
    }

    pub fn io(&self) -> PythonIo {
        self.io.borrow().clone()
    }

    /// End source custody after every dependent's staging has finished. A failed root keeps claims.
    /// Local not-cached proofs remain independent artifacts; this never upgrades them to Stored.
    pub fn finish(mut self) -> Result<PythonIo, Vec<String>> {
        let mut failures = vec![];
        for (id, origin) in std::mem::take(&mut self.origins) {
            let outcome = match origin {
                Origin::Recorded {
                    transaction,
                    record,
                    ..
                } => transaction
                    .retain_recorded(&record, |result| (self.root)(&id, result))
                    .map(|_| ())
                    .map_err(|error| error.to_string()),
                Origin::Cached { transaction, .. } => transaction
                    .retain_hit(|result| (self.root)(&id, result))
                    .map(|_| ())
                    .map_err(|error| error.to_string()),
                Origin::Installed(mut plan) => plan
                    .finish_sources(|result| (self.root)(&id, result))
                    .map_err(|error| error.to_string()),
                Origin::Current(_) | Origin::Local(_) => Ok(()),
            };
            if let Err(error) = outcome {
                failures.push(format!("{id}: {error}"));
            }
        }
        if failures.is_empty() {
            Ok(self.io())
        } else {
            Err(failures)
        }
    }

    fn identity(&self, unit: &PreparedUnit) -> Result<LeaseIdentity, String> {
        let id = Self::unit_id(unit);
        let declaration = self
            .graph
            .unit(&id)
            .ok_or("prepared unit outside backend graph")?;
        let mut upstream = BTreeSet::new();
        for input in &declaration.inputs {
            let producer = match input {
                Input::Content {
                    source:
                        ContentSource::Item { unit, .. } | ContentSource::GroupMember { unit, .. },
                    ..
                } => Some(unit),
                Input::Reference {
                    producer: Some(producer),
                    ..
                } => Some(&producer.unit),
                _ => None,
            };
            if let Some(producer) = producer {
                upstream.insert(
                    self.prepared
                        .get(producer)
                        .ok_or_else(|| format!("missing protected producer identity: {producer}"))?
                        .key()
                        .to_string(),
                );
            }
        }
        Ok(LeaseIdentity {
            provenance: self.provenance.clone(),
            owner: self.owner.clone(),
            workers: vec![],
            upstream_result_keys: upstream,
        })
    }

    fn checked(&self, unit: &PreparedUnit, items: Vec<StoredItem>, current: bool) -> PythonChecked {
        PythonChecked {
            unit: Self::unit_id(unit),
            key: unit.key().into(),
            items,
            current,
            groups: BTreeMap::new(),
        }
    }

    /// Exact declared identity lookup, with no implicit upstream materialization.
    fn resolve(
        &mut self,
        unit: &PreparedUnit,
        final_demands: &FinalDemands,
    ) -> Result<Lookup<PythonChecked, PythonTicket>, String> {
        check_unit_identity(unit)?;
        let id = Self::unit_id(unit);
        if self.prepared.contains_key(&id) {
            return Err(format!("duplicate backend lookup: {id}"));
        }
        self.prepared.insert(id.clone(), unit.clone());
        // Current is deliberately a checkout subset, never an assertion that store-only siblings exist.
        let mut current = if unit
            .ingredients()
            .logical_outputs
            .iter()
            .any(|item| item.destination == Destination::Checkout)
        {
            self.reader
                .current_identities(self.guard, unit)
                .map_err(|error| error.to_string())?
        } else {
            None
        };
        let complete_needed_identity = current.as_ref().is_some_and(|current| {
            self.needed_items.get(&id).is_none_or(|needed| {
                needed
                    .iter()
                    .all(|id| current.items().iter().any(|item| item.item.id == *id))
            })
        });
        if !final_demands.contains(&Demand::Stored) && complete_needed_identity {
            if let Some(current) = current.take() {
                let checked = self.checked(unit, current.items().to_vec(), true);
                self.origins.insert(id, Origin::Current(current));
                return Ok(Lookup::Current(checked));
            }
        }
        let identity = self.identity(unit)?;
        self.io.borrow_mut().cache_opens += 1;
        let cache = match (self.open_cache)() {
            Ok(cache) => cache,
            Err(InstallError::Cache(error)) => return Ok(Self::miss(error, None, current)),
            Err(error) => return Err(error.to_string()),
        };
        if final_demands.contains(&Demand::Checkout) && current.is_none() {
            self.io.borrow_mut().cache_lookups += 1;
            return match cache.checkout.lookup_restore(
                self.guard,
                unit,
                identity,
                self.ownership,
                vec![],
            ) {
                Ok(RestoreLookup::Hit(plan)) => {
                    let checked = self.checked(unit, plan.result().result.outputs.clone(), false);
                    self.origins.insert(id, Origin::Installed(plan));
                    Ok(Lookup::Hit(checked))
                }
                Ok(RestoreLookup::Miss(transaction)) => Ok(Lookup::Miss {
                    reason: NonHitReason::MissingRecord,
                    ticket: PythonTicket {
                        transaction: Some(transaction),
                        local: None,
                        cache_failure: None,
                        current,
                    },
                }),
                Err(InstallError::Cache(error)) => Ok(Self::miss(error, None, current)),
                Err(error) => Err(error.to_string()),
            };
        }
        let mut transaction = match cache.results.begin(
            unit,
            identity.provenance,
            identity.owner,
            identity.workers,
            identity.upstream_result_keys,
        ) {
            Ok(transaction) => transaction,
            Err(error) => return Ok(Self::miss(error, None, current)),
        };
        self.io.borrow_mut().cache_lookups += 1;
        if unit.ingredients().output_groups.is_empty()
            && (final_demands.is_empty()
                || (current.is_some() && !final_demands.contains(&Demand::Stored)))
        {
            match transaction.lookup_recorded() {
                Ok(Some(record)) => {
                    if let Some(observed) = &current {
                        agree_current(observed, &record.result().result.outputs)?;
                    }
                    let is_current = current.is_some();
                    let checked =
                        self.checked(unit, record.result().result.outputs.clone(), is_current);
                    self.origins.insert(
                        id,
                        Origin::Recorded {
                            transaction,
                            record,
                            current,
                        },
                    );
                    return Ok(if is_current {
                        Lookup::Current(checked)
                    } else {
                        Lookup::Recorded(checked)
                    });
                }
                Ok(None) => {}
                Err(error) => return Ok(Self::miss(error, Some(transaction), current)),
            }
        } else {
            match transaction.lookup_groups() {
                Ok(Some((envelope, groups))) => {
                    if let Some(observed) = &current {
                        agree_current(observed, &envelope.result.outputs)?;
                    }
                    let mut checked =
                        self.checked(unit, envelope.result.outputs.clone(), current.is_some());
                    checked.groups = groups;
                    self.origins.insert(
                        id,
                        Origin::Cached {
                            transaction,
                            envelope,
                        },
                    );
                    return Ok(Lookup::Hit(checked));
                }
                Ok(None) => {}
                Err(error) => return Ok(Self::miss(error, Some(transaction), current)),
            }
        }
        Ok(Lookup::Miss {
            reason: NonHitReason::MissingRecord,
            ticket: PythonTicket {
                transaction: Some(transaction),
                local: None,
                cache_failure: None,
                current,
            },
        })
    }

    fn miss(
        error: ResultError,
        transaction: Option<WriteTransaction>,
        current: Option<CurrentIdentities>,
    ) -> Lookup<PythonChecked, PythonTicket> {
        let outcome: Result<Option<()>, ResultError> = Err(error);
        let LookupDecision::Miss(reason) = classify_lookup_result(&outcome) else {
            unreachable!()
        };
        Lookup::Miss {
            reason,
            ticket: PythonTicket {
                transaction,
                local: None,
                cache_failure: outcome.err(),
                current,
            },
        }
    }
}

impl Backend for PythonBackend<'_> {
    type Checked = PythonChecked;
    type Ticket = PythonTicket;
    type Inputs = PythonInputs;
    type Completion = PythonCompletion;

    fn lookup(
        &mut self,
        unit: &PreparedUnit,
        demand: &FinalDemands,
    ) -> Result<Lookup<PythonChecked, PythonTicket>, String> {
        self.resolve(unit, demand)
    }

    fn view<'a>(&'a self, checked: &'a PythonChecked) -> CheckedView<'a> {
        CheckedView {
            key: &checked.key,
            items: &checked.items,
            groups: &checked.groups,
        }
    }

    fn into_outputs(
        &mut self,
        checked: PythonChecked,
    ) -> (Vec<StoredItem>, BTreeMap<String, ValidatedGroup>) {
        (checked.items, checked.groups)
    }

    /// @cc [owner:fontanierh,label:correctness] conditional-python-input-authority
    /// Only an actual miss MUST stage selected input views, using its original cache ticket and
    /// local pre-write lease. Current sources MUST be reacquired/revalidated and all read guards/FDs
    /// dropped before returning independent StagedJob files. Recorded metadata MUST not authorize
    /// bytes without selected named-object checks/durable pins. Equal-digest logical views MUST
    /// each independently revalidate before physical byte reuse; see
    /// equal_digest_current_sources_each_revalidate_before_staging. Source changes MUST refuse before
    /// dispatch, never invent a Stored hit or rerun a healthy identity-known producer.
    /// See python_backend::tests (T1a pending); dynamic source materialization remains separate.
    fn prepare_inputs(
        &mut self,
        unit: &PreparedUnit,
        ticket: &mut PythonTicket,
    ) -> Result<StagedInputs<PythonInputs>, InputFailure> {
        if ticket.local.is_some() {
            return Err(InputFailure::Invalid("job already staged".into()));
        }
        let custody = self.guard.duplicate_for_custodian().map_err(|error| {
            InputFailure::Invalid(format!("cannot duplicate build custody: {error}"))
        })?;
        let identity = self.identity(unit).map_err(InputFailure::Invalid)?;
        ticket.local = Some(
            self.reader
                .begin_completion(self.guard, unit, identity)
                .map_err(|error| InputFailure::Invalid(error.to_string()))?,
        );
        let declaration = self
            .graph
            .unit(&Self::unit_id(unit))
            .ok_or_else(|| InputFailure::Invalid("missing declared unit".into()))?;
        let mut selected = BTreeMap::new();
        let mut logical_views = Vec::new();
        for input in unit.inputs() {
            let InputPayload::Item { files, .. } = &input.payload else {
                continue;
            };
            let source = declaration
                .inputs
                .iter()
                .find_map(|declared| match declared {
                    Input::Content { name, source, .. } if *name == input.wire.name => Some(source),
                    _ => None,
                })
                .ok_or_else(|| InputFailure::Invalid("missing declared item source".into()))?;
            let (producer, item, group) = match source {
                ContentSource::Item { unit, item } => (unit, item, None),
                ContentSource::GroupMember { unit, group, piece } => {
                    (unit, piece, Some(group.clone()))
                }
                _ => return Err(InputFailure::Invalid("unsupported item source".into())),
            };
            for file in files {
                logical_views.push((
                    file.digest.clone(),
                    SelectedSource {
                        group: group.clone(),
                        producer: producer.clone(),
                        item: item.clone(),
                        input: input.clone(),
                    },
                ));
                selected
                    .entry(file.digest.clone())
                    .or_insert_with(|| SelectedSource {
                        group: group.clone(),
                        producer: producer.clone(),
                        item: item.clone(),
                        input: input.clone(),
                    });
            }
        }
        let local = ticket.local.as_ref().unwrap();
        let sources = PythonSources {
            origins: RefCell::new(&mut self.origins),
            prepared: &self.prepared,
            reader: self.reader,
            guard: self.guard,
            selected,
            io: &self.io,
        };
        // Digest reuse is physical only: every logical producer/item must independently
        // authorize its selected view, including equal-byte Current producers.
        for (digest, selected) in &logical_views {
            let digest = ObjectDigest::from_hex(digest)
                .map_err(|error| InputFailure::Invalid(error.to_string()))?;
            sources
                .access(selected, &digest, None)
                .map_err(|error| match error.kind {
                    SourceErrorKind::Changed => InputFailure::Changed(error.to_string()),
                    _ => InputFailure::Unavailable(error.to_string()),
                })?;
        }
        let staged = staging::stage(
            unit,
            self.snapshot,
            &sources,
            &local.job_dir(),
            &local.lease().id,
        )
        .map_err(|error| match error {
            StageError::Source(error) if error.kind == SourceErrorKind::Changed => {
                InputFailure::Changed(error.to_string())
            }
            StageError::Source(error) => InputFailure::Unavailable(error.to_string()),
            StageError::Staging(message) => InputFailure::Invalid(message),
        })?;
        drop(sources);
        self.io.borrow_mut().staged_jobs += 1;
        Ok(StagedInputs {
            inputs: PythonInputs {
                custody,
                staged,
                io: self.io.clone(),
            },
            staged_units: 1,
        })
    }

    fn publish(
        &mut self,
        work: Work<PythonTicket, PythonInputs>,
        completed: PythonCompletion,
    ) -> Result<Published<PythonChecked>, String> {
        let unit = work.prepared().clone();
        let id = work.unit().to_string();
        let (mut ticket, inputs) = work.into_parts();
        let actual = staging::collect_outputs(&inputs.staged, &completed.reported)?;
        let mut frozen = ticket
            .local
            .take()
            .ok_or("completed work has no local lease")?
            .freeze(
                actual,
                |outputs| validate_fixed_outputs(&unit, outputs, &inputs.staged),
                |contract, _, objects| {
                    if matches!(
                        unit.ingredients().op.kind.as_str(),
                        "recipe.blender" | "recipe.python"
                    ) {
                        crate::recipe_ops::check(&unit)?;
                        return blender_ops::validate_geometry_outputs(contract, objects)
                            .map(|_| ());
                    }
                    if unit.ingredients().op.kind != BLENDER_PLAN_KIND {
                        return Err("output group outside registered Blender planner".into());
                    }
                    let spec = BlenderPlanSpec::new(contract.clone());
                    blender_ops::validate_blender_plan_outputs(
                        &unit,
                        &spec,
                        &validator_identity(&unit),
                        objects,
                    )
                    .map(|_| ())
                },
            )
            .map_err(|error| error.to_string())?;
        let observed_current = ticket.current.take();
        if let Some(current) = &observed_current {
            agree_current(current, &frozen.result().result.outputs)?;
        }
        let publication = match ticket.transaction.take() {
            Some(transaction) => {
                frozen.publish_with(transaction, |result| (self.root)(&id, result))
            }
            None => Err(ticket
                .cache_failure
                .unwrap_or_else(|| ResultError::Io(std::io::Error::other("cache unavailable")))),
        };
        let decision = classify_completion(LocalOutputStatus::Valid, publication);
        let publication = match decision {
            CompletionDecision::Cached => Publication::Cached,
            CompletionDecision::CompletedNotCached(reason) => {
                Publication::NotCached(format!("{reason:?}"))
            }
            CompletionDecision::FailUnit(reason) => {
                return Err(format!("Python output refused: {reason:?}"));
            }
        };
        let still_current = if observed_current.is_some() {
            match self
                .reader
                .current_identities(self.guard, &unit)
                .map_err(|error| error.to_string())?
            {
                Some(current) => {
                    agree_current(&current, &frozen.result().result.outputs)?;
                    true
                }
                None => false,
            }
        } else {
            false
        };
        let mut checked =
            self.checked(&unit, frozen.result().result.outputs.clone(), still_current);
        checked.groups = frozen
            .available_groups()
            .map_err(|error| error.to_string())?;
        self.origins.insert(id, Origin::Local(frozen));
        self.io.borrow_mut().publications += 1;
        Ok(Published {
            checked,
            publication,
        })
    }

    fn settle(
        &mut self,
        unit: &PreparedUnit,
        checked: &mut PythonChecked,
        demand: &FinalDemands,
    ) -> Result<Effects, String> {
        if !demand.contains(&Demand::Checkout) {
            return Ok(Effects::default());
        }
        if checked.current {
            let current = self
                .reader
                .current_identities(self.guard, unit)
                .map_err(|error| error.to_string())?
                .ok_or("Current changed before Checkout fulfillment")?;
            agree_current(&current, &checked.items)?;
            return Ok(Effects::default());
        }
        let origin = self
            .origins
            .remove(&checked.unit)
            .ok_or("checked source authority missing")?;
        let mut plan = match origin {
            Origin::Installed(plan) => plan,
            Origin::Local(completion) => self
                .reader
                .prepare_local(self.guard, completion, self.ownership, vec![])
                .map_err(|error| error.to_string())?,
            _ => {
                return Err(
                    "Checkout requires an original restore plan or sealed local completion".into(),
                );
            }
        };
        plan.commit_with_sources(self.guard, |result| (self.root)(&checked.unit, result))
            .map_err(|error| error.to_string())?;
        let receipts = unit
            .ingredients()
            .logical_outputs
            .iter()
            .filter(|item| item.destination == Destination::Checkout)
            .count();
        self.origins
            .insert(checked.unit.clone(), Origin::Installed(plan));
        let mut io = self.io.borrow_mut();
        io.installs += 1;
        io.receipt_writes += receipts;
        Ok(Effects {
            installed_units: 1,
            receipt_writes: receipts,
            staged_units: 0,
        })
    }
}
