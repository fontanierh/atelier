//! Static ready-frontier scheduling over A4 graphs and A3 identities.
//! Concrete cache/install authority and execution lifecycle belong to their existing adapters.
use crate::graph::{BuildGraph, SelectedGraph, Target};
use crate::groups::ValidatedGroup;
use crate::integrity::NonHitReason;
use crate::keys::{
    self, ImplementationIdentity, KeyContext, PreparedUnit, ProducedGroups, ProducedItems,
    SourceVersions,
};
use crate::schema::{Destination, StoredItem};
use crate::source_hashes::SourceHashCache;
use crate::validate::SourceSnapshot;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum Demand {
    Stored,
    Checkout,
}

/// Explicit final requirements only. Empty means internal identity resolution, not Stored.
pub type FinalDemands = BTreeSet<Demand>;

/// Runtime declarations supply only execution identity and explicit staged names.
/// `profile` groups compatible work; semantic worker options must already be keyed.
#[derive(Clone, Debug)]
pub struct Runtime {
    pub worker: ImplementationIdentity,
    pub validator: ImplementationIdentity,
    pub staged_inputs: BTreeMap<String, String>,
    pub profile: String,
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct Compatibility {
    pub worker_version: String,
    pub worker_digest: String,
    pub op_kind: String,
    pub op_version: String,
    pub profile: String,
}

pub struct Request<'a> {
    graph: &'a BuildGraph,
    selected: SelectedGraph,
    snapshot: &'a SourceSnapshot,
    versions: &'a SourceVersions,
    runtimes: &'a BTreeMap<String, Runtime>,
    /// Every selected root states final requirements; internal units have none.
    demands: &'a BTreeMap<String, FinalDemands>,
}
impl<'a> Request<'a> {
    /// Selection and the immutable snapshot are bound together; callers cannot pair
    /// validation from another graph/snapshot with this scheduling request.
    pub fn select(
        graph: &'a BuildGraph,
        targets: &[Target],
        snapshot: &'a SourceSnapshot,
        versions: &'a SourceVersions,
        runtimes: &'a BTreeMap<String, Runtime>,
        demands: &'a BTreeMap<String, FinalDemands>,
    ) -> Result<Self, String> {
        let selected = graph.select(targets, snapshot)?;
        for id in selected.order() {
            if !runtimes.contains_key(id) {
                return Err(format!("missing selected runtime: {id}"));
            }
        }
        Ok(Self {
            graph,
            selected,
            snapshot,
            versions,
            runtimes,
            demands,
        })
    }
    pub fn selected(&self) -> &SelectedGraph {
        &self.selected
    }
}

/// A view of backend-owned authority, not a new constructor for StoredHit/group seals.
pub struct CheckedView<'a> {
    pub key: &'a str,
    pub items: &'a [StoredItem],
    pub groups: &'a BTreeMap<String, ValidatedGroup>,
}

pub enum Lookup<C, T> {
    /// Exact identity observation only; never available bytes or a final demand.
    Recorded(C),
    Current(C),
    Hit(C),
    Miss {
        ticket: T,
        reason: NonHitReason,
    },
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Effects {
    pub staged_units: usize,
    pub installed_units: usize,
    pub receipt_writes: usize,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Publication {
    Cached,
    NotCached(String),
}

pub struct Published<C> {
    pub checked: C,
    pub publication: Publication,
}

/// Real adapters must use existing A5/B2/B7 sealed handles as Checked/Ticket.
/// Fake test authority is a distinct type and cannot turn into production StoredHit.
/// Publication must validate/freeze/root per unit; failure never erases earlier results.
pub trait Backend {
    type Checked;
    type Ticket;
    /// Independent staged files, with no retained CurrentSources guard or descriptors.
    type Inputs: 'static;
    type Completion;

    fn lookup(
        &mut self,
        unit: &PreparedUnit,
        demand: &FinalDemands,
    ) -> Result<Lookup<Self::Checked, Self::Ticket>, String>;
    /// Current identity is observed under short custody, released BEFORE lookup returns.
    /// Do not keep CurrentSources guards alive for identity-only consumers that may hit.
    fn view<'a>(&'a self, checked: &'a Self::Checked) -> CheckedView<'a>;
    /// Called only for an actual consumer miss immediately before dispatch. Reacquire and
    /// revalidate selected sources here; release all CurrentSources guards/FDs before return.
    /// Unsupported/changed sources refuse here, without rerunning an identity-known producer.
    fn prepare_inputs(
        &mut self,
        unit: &PreparedUnit,
        ticket: &mut Self::Ticket,
    ) -> Result<StagedInputs<Self::Inputs>, InputFailure>;
    /// Move sealed outputs into the scheduling identity context; tokens are never cloned or deserialized here.
    fn into_outputs(
        &mut self,
        checked: Self::Checked,
    ) -> (Vec<StoredItem>, BTreeMap<String, ValidatedGroup>);
    fn publish(
        &mut self,
        work: Work<Self::Ticket, Self::Inputs>,
        completion: Self::Completion,
    ) -> Result<Published<Self::Checked>, String>;
    /// Apply only this explicit demand and retain required roots/claims through existing APIs.
    /// Current must not rewrite output/receipt/index files. Stored never installs checkout files.
    fn settle(
        &mut self,
        unit: &PreparedUnit,
        checked: &mut Self::Checked,
        demand: &FinalDemands,
    ) -> Result<Effects, String>;
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum InputFailure {
    Unavailable(String),
    Changed(String),
    Invalid(String),
}

/// Independent input files issued by the backend staging adapter, never by receipt parsing.
pub struct StagedInputs<I> {
    pub inputs: I,
    pub staged_units: usize,
}

struct Pending<T> {
    unit: String,
    prepared: PreparedUnit,
    ticket: T,
    compatibility: Compatibility,
}

/// The original miss ticket plus independent staged input capability for one prepared unit.
/// Only this module constructs work; executors return that same owned handle in an event.
pub struct Work<T, I> {
    unit: String,
    prepared: PreparedUnit,
    ticket: T,
    inputs: I,
    compatibility: Compatibility,
}
impl<T, I> Work<T, I> {
    pub fn unit(&self) -> &str {
        &self.unit
    }
    pub fn prepared(&self) -> &PreparedUnit {
        &self.prepared
    }
    pub fn ticket(&self) -> &T {
        &self.ticket
    }
    pub fn ticket_mut(&mut self) -> &mut T {
        &mut self.ticket
    }
    pub fn inputs(&self) -> &I {
        &self.inputs
    }
    pub fn compatibility(&self) -> &Compatibility {
        &self.compatibility
    }
    pub fn into_parts(self) -> (T, I) {
        (self.ticket, self.inputs)
    }
}

pub enum Event<T, I, C> {
    Completed { work: Work<T, I>, completion: C },
    Failed { work: Work<T, I>, reason: String },
    Cancelled { work: Work<T, I> },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Flow {
    Continue,
    Stop,
}

pub trait Control {
    fn cancelled(&self) -> bool;
}

/// Admission, worker sessions, retries, deadlines and cleanup belong to C5/C7.
/// Every submitted handle MUST return one terminal event, including queued cancellation.
/// Flow::Stop forbids starting more work; it does not waive settlement of owned handles.
/// A returned error or omitted outcome does not certify cleanup; scheduling stops with unresolved work blocked.
pub trait Executor<T, I, C> {
    fn batch(
        &mut self,
        work: Vec<Work<T, I>>,
        control: &dyn Control,
        emit: &mut dyn FnMut(Event<T, I, C>) -> Flow,
    ) -> Result<(), String>;
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum State {
    Waiting,
    Miss(NonHitReason),
    Identity,
    Current,
    Hit,
    Executed(Publication),
    Failed(String),
    InputRefused(InputFailure),
    Blocked(Vec<String>),
    Cancelled,
}
impl State {
    fn resolved(&self) -> bool {
        matches!(
            self,
            Self::Identity | Self::Current | Self::Hit | Self::Executed(_)
        )
    }
    fn unsuccessful(&self) -> bool {
        matches!(
            self,
            Self::Failed(_) | Self::InputRefused(_) | Self::Blocked(_) | Self::Cancelled
        )
    }
}

#[derive(Default)]
pub struct Report {
    pub states: BTreeMap<String, State>,
    pub keys: BTreeMap<String, String>,
    /// Validated complete discovery tokens; identities alone never populate this map.
    pub groups: ProducedGroups,
    pub lookups: Vec<String>,
    pub batches: Vec<Vec<String>>,
    pub publications: Vec<String>,
    pub effects: Effects,
    /// Explicit final requirements not fulfilled; semantic output identity may still be usable.
    pub unsatisfied: BTreeMap<String, FinalDemands>,
    pub fatal: Option<String>,
}

fn demand(request: &Request<'_>, unit: &str) -> FinalDemands {
    request.demands.get(unit).cloned().unwrap_or_default()
}

fn integrate<B: Backend>(
    backend: &mut B,
    unit_id: &str,
    prepared: &PreparedUnit,
    mut checked: B::Checked,
    requested: &FinalDemands,
    current: bool,
    items: &mut ProducedItems,
    groups: &mut ProducedGroups,
    report: &mut Report,
) -> Result<(), String> {
    let view = backend.view(&checked);
    if view.key != prepared.key() {
        return Err("backend returned authority for another prepared key".into());
    }
    // Borrowed metadata is copied only after the backend's exact-key check. The concrete
    // adapter, not raw deserialization here, owns manifest/projection validation and pins.
    let effects = backend.settle(prepared, &mut checked, requested)?;
    if current && (effects.installed_units != 0 || effects.receipt_writes != 0) {
        return Err("Current settlement unexpectedly rewrote checkout state".into());
    }
    if !requested.contains(&Demand::Checkout)
        && (effects.installed_units != 0 || effects.receipt_writes != 0)
    {
        return Err("No Checkout demand authorized installed files".into());
    }
    if effects.staged_units != 0 {
        return Err("final settlement cannot stage job inputs".into());
    }
    report.effects.installed_units += effects.installed_units;
    report.effects.receipt_writes += effects.receipt_writes;
    let view = backend.view(&checked);
    if view.key != prepared.key() {
        return Err("settlement changed prepared-key authority".into());
    }
    let (owned_items, owned_groups) = backend.into_outputs(checked);
    for item in owned_items {
        items.insert((unit_id.into(), item.item.id.clone()), item);
    }
    for (id, group) in owned_groups {
        groups.insert((unit_id.into(), id.clone()), group);
    }
    Ok(())
}

/// @cc [owner:fontanierh,label:correctness] static-frontier-lookup-before-dispatch
/// Scheduling MUST use A4 membership/order and A3 exact output-content identities, never
/// upstream input keys. Every currently ready lookup MUST finish before any miss is sent
/// to an executor; only compatible misses share a batch. Original miss tickets MUST be
/// preserved, and each completion MUST publish independently before downstream preparation.
/// Identity/Current/hit units MUST not launch jobs. Internal identity resolution MUST NOT require Stored.
/// Recorded/Current MUST NOT certify explicit Stored availability. Selected bytes MUST be staged
/// only for actual consumer misses, with independent inputs and no retained checkout read custody.
/// Failure/cancellation MUST retain prior publication.
/// See tests/scheduler.rs; real lifecycle, dynamic targets and A6 integration remain pending.
pub fn run<B: Backend, E: Executor<B::Ticket, B::Inputs, B::Completion>>(
    request: Request<'_>,
    backend: &mut B,
    executor: &mut E,
    control: &dyn Control,
    hashes: &mut SourceHashCache,
) -> Result<Report, String> {
    let membership: BTreeSet<_> = request.selected.order().iter().cloned().collect();
    if !request.selected.roots().iter().all(|id| {
        request
            .demands
            .get(id)
            .is_some_and(|flags| !flags.is_empty())
    }) || !request
        .demands
        .keys()
        .all(|id| request.selected.roots().contains(id))
    {
        return Err("explicit root demands must belong to the selected graph".into());
    }
    for (id, mode) in request.demands {
        if mode.contains(&Demand::Checkout)
            && !request
                .graph
                .unit(id)
                .unwrap()
                .outputs
                .iter()
                .any(|item| item.destination == Destination::Checkout)
        {
            return Err(format!(
                "Checkout demand has no declared checkout item: {id}"
            ));
        }
    }
    let mut parents: BTreeMap<String, BTreeSet<String>> = membership
        .iter()
        .map(|id| (id.clone(), BTreeSet::new()))
        .collect();
    for edge in request.selected.dependencies() {
        parents
            .get_mut(&edge.consumer)
            .unwrap()
            .insert(edge.producer.clone());
    }
    let mut report = Report {
        states: membership
            .iter()
            .map(|id| (id.clone(), State::Waiting))
            .collect(),
        ..Report::default()
    };
    let mut items = ProducedItems::new();
    let mut groups = ProducedGroups::new();
    // Undispatched misses keep their original lookup tickets while new ready hits resolve.
    let mut pending = Vec::new();
    loop {
        // Follow hit-unlocked frontiers to a fixed point before dispatching accumulated misses.
        loop {
            let mut progress = false;
            for id in request.selected.order() {
                if report.states[id] != State::Waiting {
                    continue;
                }
                let failed: Vec<_> = parents[id]
                    .iter()
                    .filter(|p| report.states[*p].unsuccessful())
                    .cloned()
                    .collect();
                if !failed.is_empty() {
                    report.states.insert(id.clone(), State::Blocked(failed));
                    progress = true;
                    continue;
                }
                if control.cancelled() {
                    report.states.insert(id.clone(), State::Cancelled);
                    progress = true;
                    continue;
                }
                if !parents[id].iter().all(|p| report.states[p].resolved()) {
                    continue;
                }
                progress = true;
                let unit = request
                    .graph
                    .unit(id)
                    .ok_or("selected unit missing from graph")?;
                let runtime = request
                    .runtimes
                    .get(id)
                    .ok_or_else(|| format!("missing selected runtime: {id}"))?;
                let prepared = match keys::prepare(
                    request.graph.declaration(),
                    request.selected.validation(),
                    id,
                    &KeyContext {
                        snapshot: request.snapshot,
                        versions: request.versions,
                        produced: &items,
                        produced_groups: &groups,
                        staged_inputs: &runtime.staged_inputs,
                        worker: &runtime.worker,
                        validator: &runtime.validator,
                    },
                    hashes,
                ) {
                    Ok(prepared) => prepared,
                    Err(error) => {
                        report.states.insert(id.clone(), State::Failed(error));
                        continue;
                    }
                };
                report.keys.insert(id.clone(), prepared.key().into());
                report.lookups.push(id.clone());
                let mode = demand(&request, id);
                match backend.lookup(&prepared, &mode) {
                    Ok(reused @ (Lookup::Recorded(_) | Lookup::Current(_) | Lookup::Hit(_))) => {
                        // Retain the distinction without asking the backend to look up twice.
                        let (checked, state) = match reused {
                            Lookup::Recorded(checked) => (checked, State::Identity),
                            Lookup::Current(checked) => (checked, State::Current),
                            Lookup::Hit(checked) => (checked, State::Hit),
                            Lookup::Miss { .. } => unreachable!(),
                        };
                        if (state == State::Current && mode.contains(&Demand::Stored))
                            || (state == State::Identity && !mode.is_empty())
                        {
                            report.states.insert(
                                id.clone(),
                                State::Failed(
                                    "Identity/Current does not satisfy explicit final requirements"
                                        .into(),
                                ),
                            );
                            continue;
                        }
                        let result = integrate(
                            backend,
                            id,
                            &prepared,
                            checked,
                            &mode,
                            state == State::Current,
                            &mut items,
                            &mut groups,
                            &mut report,
                        );
                        match result {
                            Ok(()) => {
                                report.states.insert(id.clone(), state);
                            }
                            Err(error) => {
                                report.states.insert(id.clone(), State::Failed(error));
                            }
                        }
                    }
                    Ok(Lookup::Miss { ticket, reason }) => {
                        report.states.insert(id.clone(), State::Miss(reason));
                        pending.push(Pending {
                            unit: id.clone(),
                            prepared,
                            ticket,
                            compatibility: Compatibility {
                                worker_version: runtime.worker.version.clone(),
                                worker_digest: runtime.worker.digest.clone(),
                                op_kind: unit.op.kind.clone(),
                                op_version: unit.op.version.clone(),
                                profile: runtime.profile.clone(),
                            },
                        });
                    }
                    Err(error) => {
                        report.states.insert(id.clone(), State::Failed(error));
                    }
                }
            }
            if !progress {
                break;
            }
        }
        if pending.is_empty() {
            break;
        }
        let mut batches: BTreeMap<Compatibility, Vec<Pending<B::Ticket>>> = BTreeMap::new();
        for work in pending.drain(..) {
            batches
                .entry(work.compatibility.clone())
                .or_default()
                .push(work);
        }
        // Submit one compatibility batch, then refresh the ready frontier before the next.
        // A completed producer may unlock a hit that must not wait behind unrelated work.
        if let Some((_, batch)) = batches.pop_first() {
            pending.extend(batches.into_values().flatten());
            if control.cancelled() {
                for work in batch {
                    report.states.insert(work.unit, State::Cancelled);
                }
                continue;
            }
            let mut ready = Vec::new();
            for Pending {
                unit,
                prepared,
                mut ticket,
                compatibility,
            } in batch
            {
                match backend.prepare_inputs(&prepared, &mut ticket) {
                    Ok(staged) => {
                        report.effects.staged_units += staged.staged_units;
                        ready.push(Work {
                            unit,
                            prepared,
                            ticket,
                            inputs: staged.inputs,
                            compatibility,
                        });
                    }
                    Err(reason) => {
                        report.states.insert(unit, State::InputRefused(reason));
                    }
                }
            }
            if ready.is_empty() {
                continue;
            }
            if control.cancelled() {
                for work in ready {
                    report.states.insert(work.unit, State::Cancelled);
                }
                continue;
            }
            let batch = ready;
            report
                .batches
                .push(batch.iter().map(|work| work.unit.clone()).collect());
            let mut expected: BTreeMap<_, _> = batch
                .iter()
                .map(|work| (work.unit.clone(), work.prepared.key().to_string()))
                .collect();
            let executed = executor.batch(batch, control, &mut |event| {
                let work = match &event {
                    Event::Completed { work, .. }
                    | Event::Failed { work, .. }
                    | Event::Cancelled { work } => work,
                };
                if expected.remove(&work.unit).as_deref() != Some(work.prepared.key()) {
                    report.fatal = Some("executor returned unexpected or duplicate work".into());
                    return Flow::Stop;
                }
                match event {
                    Event::Completed { work, completion } => {
                        let id = work.unit.clone();
                        let prepared = work.prepared.clone();
                        match backend.publish(work, completion) {
                            Ok(published) => match integrate(
                                backend,
                                &id,
                                &prepared,
                                published.checked,
                                &demand(&request, &id),
                                false,
                                &mut items,
                                &mut groups,
                                &mut report,
                            ) {
                                Ok(()) => {
                                    report.publications.push(id.clone());
                                    report
                                        .states
                                        .insert(id, State::Executed(published.publication));
                                }
                                Err(error) => {
                                    report.states.insert(id, State::Failed(error));
                                }
                            },
                            Err(error) => {
                                report.states.insert(id, State::Failed(error));
                            }
                        }
                    }
                    Event::Failed { work, reason } => {
                        report.states.insert(work.unit, State::Failed(reason));
                    }
                    Event::Cancelled { work } => {
                        report.states.insert(work.unit, State::Cancelled);
                    }
                }
                if control.cancelled() || report.fatal.is_some() {
                    Flow::Stop
                } else {
                    Flow::Continue
                }
            });
            if let Err(error) = executed {
                report.fatal = Some(error);
            }
            if !expected.is_empty() {
                report.fatal.get_or_insert_with(|| {
                    "executor omitted terminal outcome; cleanup unresolved".into()
                });
            }
            for (id, _) in expected {
                report.states.insert(
                    id,
                    State::Failed("executor omitted terminal outcome".into()),
                );
            }
            if report.fatal.is_some() {
                break;
            }
        }
        if report.fatal.is_some() {
            break;
        }
    }
    if report.fatal.is_some() {
        for state in report.states.values_mut() {
            if *state == State::Waiting || matches!(state, State::Miss(_)) {
                *state = State::Blocked(vec!["executor lifecycle unresolved".into()]);
            }
        }
    }
    for (id, requested) in request.demands {
        let mut unmet = requested.clone();
        match &report.states[id] {
            State::Hit | State::Executed(Publication::Cached) => unmet.clear(),
            State::Current | State::Executed(Publication::NotCached(_)) => {
                unmet.remove(&Demand::Checkout);
            }
            _ => {}
        }
        if !unmet.is_empty() {
            report.unsatisfied.insert(id.clone(), unmet);
        }
    }
    report.groups = groups;
    Ok(report)
}
