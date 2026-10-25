//! Fake execution exercises the real A3 key/A4 graph loop; it is not production cache authority.
use atelier_build_v2::{
    graph::*, groups::ValidatedGroup, integrity::NonHitReason, keys::*, scheduler::*, schema::*,
    source_hashes::*, validate::*,
};
use std::cell::{Cell, RefCell};
use std::collections::{BTreeMap, BTreeSet};
use std::rc::Rc;

type Trace = Rc<RefCell<Vec<String>>>;
struct Checked {
    key: String,
    items: Vec<StoredItem>,
    groups: BTreeMap<String, ValidatedGroup>,
}
struct Fake {
    cache: BTreeMap<String, Checked>,
    known: BTreeMap<String, Checked>,
    installed: BTreeMap<String, String>,
    recorded: BTreeSet<String>,
    unavailable: BTreeSet<String>,
    changed: BTreeSet<String>,
    source_guard: Rc<Cell<bool>>,
    cancel_on_prepare: Option<Rc<Cell<bool>>>,
    outputs: BTreeMap<String, String>,
    trace: Trace,
    current: BTreeSet<String>,
    fail_publish: BTreeSet<String>,
    not_cached: BTreeSet<String>,
    miss_reason: Option<NonHitReason>,
    fail_settle: BTreeSet<String>,
    bad_publish_key: bool,
    bad_key: bool,
    bad_settle: bool,
}
impl Fake {
    fn new(trace: Trace) -> Self {
        Self {
            cache: BTreeMap::new(),
            known: BTreeMap::new(),
            installed: BTreeMap::new(),
            recorded: BTreeSet::new(),
            unavailable: BTreeSet::new(),
            changed: BTreeSet::new(),
            source_guard: Rc::new(Cell::new(false)),
            cancel_on_prepare: None,
            outputs: BTreeMap::new(),
            trace,
            current: BTreeSet::new(),
            fail_publish: BTreeSet::new(),
            not_cached: BTreeSet::new(),
            miss_reason: None,
            fail_settle: BTreeSet::new(),
            bad_publish_key: false,
            bad_key: false,
            bad_settle: false,
        }
    }
}
impl Clone for Checked {
    fn clone(&self) -> Self {
        assert!(
            self.groups.is_empty(),
            "static fixture does not clone group authority"
        );
        Self {
            key: self.key.clone(),
            items: self.items.clone(),
            groups: BTreeMap::new(),
        }
    }
}
impl Backend for Fake {
    type Checked = Checked;
    type Ticket = String;
    type Inputs = ();
    type Completion = ();
    fn lookup(
        &mut self,
        u: &PreparedUnit,
        d: &FinalDemands,
    ) -> Result<Lookup<Checked, String>, String> {
        let id = &u.ingredients().logical_outputs[0].id;
        self.trace
            .borrow_mut()
            .push(format!("lookup:{id}:{}", label(d)));
        // A separate fake identity observation survives simulated object eviction.
        // This is not a production receipt vector or StoredHit constructor.
        if let Some(c) = self.known.get(u.key()) {
            if self.current.contains(id) {
                return Ok(Lookup::Current(c.clone()));
            }
            if self.recorded.contains(id) {
                return Ok(Lookup::Recorded(c.clone()));
            }
        }
        if let Some(c) = self.cache.get(u.key()) {
            let mut c = c.clone();
            if self.bad_key {
                c.key = "foreign".into();
            }
            return Ok(Lookup::Hit(c));
        }
        Ok(Lookup::Miss {
            ticket: u.key().into(),
            reason: self
                .miss_reason
                .clone()
                .unwrap_or(NonHitReason::MissingRecord),
        })
    }
    fn prepare_inputs(
        &mut self,
        u: &PreparedUnit,
        ticket: &mut String,
    ) -> Result<StagedInputs<()>, InputFailure> {
        assert_eq!(ticket.as_str(), u.key());
        let id = &u.ingredients().logical_outputs[0].id;
        self.trace.borrow_mut().push(format!("inputs:{id}"));
        self.source_guard.set(true); // fake short-lived source custody
        let outcome = if self.unavailable.contains(id) {
            Err(InputFailure::Unavailable(
                "selected source adapter unsupported".into(),
            ))
        } else if self.changed.contains(id) {
            Err(InputFailure::Changed(
                "selected source changed; reprepare required".into(),
            ))
        } else {
            Ok(StagedInputs {
                inputs: (),
                staged_units: 1,
            })
        };
        self.source_guard.set(false); // independent capability only; no custody across executor
        if let Some(flag) = &self.cancel_on_prepare {
            flag.set(true);
        }
        outcome
    }
    fn view<'a>(&'a self, c: &'a Checked) -> CheckedView<'a> {
        CheckedView {
            key: &c.key,
            items: &c.items,
            groups: &c.groups,
        }
    }
    fn into_outputs(
        &mut self,
        checked: Checked,
    ) -> (Vec<StoredItem>, BTreeMap<String, ValidatedGroup>) {
        (checked.items, checked.groups)
    }
    fn publish(&mut self, w: Work<String, ()>, _: ()) -> Result<Published<Checked>, String> {
        assert_eq!(w.ticket(), w.prepared().key());
        let id = w.unit().to_string();
        self.trace.borrow_mut().push(format!("publish:{id}"));
        if self.fail_publish.contains(&id) {
            return Err("invalid result".into());
        }
        let items = w
            .prepared()
            .ingredients()
            .logical_outputs
            .iter()
            .map(|item| StoredItem {
                item: item.clone(),
                files: item
                    .files
                    .iter()
                    .map(|f| StoredFile {
                        path: f.path.clone(),
                        digest: self.outputs.get(&id).cloned().unwrap_or("a".repeat(64)),
                        size: 4,
                        mode: 0o644,
                    })
                    .collect(),
                external_locator: None,
            })
            .collect();
        let mut checked = Checked {
            key: w.prepared().key().into(),
            items,
            groups: BTreeMap::new(),
        };
        self.known.insert(checked.key.clone(), checked.clone());
        let publication = if self.not_cached.contains(&id) {
            Publication::NotCached("fixture store unavailable".into())
        } else {
            self.cache.insert(checked.key.clone(), checked.clone());
            Publication::Cached
        };
        if self.bad_publish_key {
            checked.key = "foreign".into();
        }
        Ok(Published {
            checked,
            publication,
        })
    }
    fn settle(
        &mut self,
        u: &PreparedUnit,
        _: &mut Checked,
        d: &FinalDemands,
    ) -> Result<Effects, String> {
        let id = &u.ingredients().logical_outputs[0].id;
        if self.fail_settle.contains(id) {
            return Err("fixture settlement failed after publication".into());
        }
        self.trace
            .borrow_mut()
            .push(format!("settle:{id}:{}", label(d)));
        let bad = self.bad_settle && (self.current.is_empty() || self.current.contains(id));
        let writes = d.contains(&Demand::Checkout)
            && self.installed.get(id).map(String::as_str) != Some(u.key());
        if writes {
            self.installed.insert(id.clone(), u.key().into());
        }
        Ok(Effects {
            installed_units: usize::from(writes || bad),
            receipt_writes: usize::from(writes || bad),
            staged_units: 0,
        })
    }
}
#[path = "support/explain_scheduler_cases.rs"]
mod explain_cases;
fn label(d: &FinalDemands) -> String {
    if d.is_empty() {
        "Identity".into()
    } else {
        d.iter()
            .map(|d| format!("{d:?}"))
            .collect::<Vec<_>>()
            .join("+")
    }
}
struct Never;
impl Control for Never {
    fn cancelled(&self) -> bool {
        false
    }
}
struct Flag(Rc<Cell<bool>>);
impl Control for Flag {
    fn cancelled(&self) -> bool {
        self.0.get()
    }
}
struct Jobs {
    trace: Trace,
    fail: BTreeSet<String>,
    cancel_after: Option<Rc<Cell<bool>>>,
    omit: bool,
    source_guard: Option<Rc<Cell<bool>>>,
}
impl Jobs {
    fn new(trace: Trace) -> Self {
        Self {
            trace,
            fail: BTreeSet::new(),
            cancel_after: None,
            omit: false,
            source_guard: None,
        }
    }
}
impl Executor<String, (), ()> for Jobs {
    fn batch(
        &mut self,
        work: Vec<Work<String, ()>>,
        _: &dyn Control,
        emit: &mut dyn FnMut(Event<String, (), ()>) -> Flow,
    ) -> Result<(), String> {
        assert!(
            !self.source_guard.as_ref().unwrap().get(),
            "source custody leaked into execution"
        );
        let mut work = work.into_iter();
        while let Some(w) = work.next() {
            let id = w.unit().to_string();
            self.trace.borrow_mut().push(format!("execute:{id}"));
            if self.omit {
                continue;
            }
            let event = if self.fail.contains(&id) {
                Event::Failed {
                    work: w,
                    reason: "worker refusal".into(),
                }
            } else {
                Event::Completed {
                    work: w,
                    completion: (),
                }
            };
            let flow = emit(event);
            if let Some(flag) = &self.cancel_after {
                flag.set(true);
                for work in work {
                    emit(Event::Cancelled { work });
                }
                return Ok(());
            }
            if flow == Flow::Stop {
                for work in work {
                    emit(Event::Cancelled { work });
                }
                return Ok(());
            }
        }
        Ok(())
    }
}
struct Fixture {
    graph: BuildGraph,
    snapshot: SourceSnapshot,
    runtimes: BTreeMap<String, Runtime>,
    versions: SourceVersions,
}
fn fixture(reference: bool) -> Fixture {
    fixture_source(reference, false)
}
fn fixture_source(reference: bool, checkout_source: bool) -> Fixture {
    let role = if reference { "reference" } else { "content" };
    let input = if reference {
        format!(
            r#"{{role="{role}",name="upstream",logical_path="/Game/A",class="Blob",proof="fixture bounded read",producer={{unit="a",item="a"}}}}"#
        )
    } else {
        r#"{role="content",name="upstream",source={kind="item",unit="a",item="a"}}"#.into()
    };
    let text = format!(
        r#"
schema_version=2
cache_version="fixture1"
[[units]]
id="a"
op={{kind="fixture",version="1"}}
script="op.py"
code=["op.py"]
params={{value=1}}
outputs=[{{id="a",logical_path="/Game/A",class="Blob",destination="store",files=[{{path="a.bin"}}]}}]
[[units]]
id="b"
op={{kind="fixture",version="1"}}
script="op.py"
code=["op.py"]
params={{value=1}}
inputs=[{input}]
outputs=[{{id="b",logical_path="/Game/B",class="Blob",destination="checkout",files=[{{path="b.bin",install_path="Content/b.bin"}}]}}]
[[units]]
id="c"
op={{kind="fixture",version="1"}}
script="op.py"
code=["op.py"]
params={{value=1}}
outputs=[{{id="c",logical_path="/Game/C",class="Blob",destination="store",files=[{{path="c.bin"}}]}}]
"#
    );
    let text = if checkout_source {
        text.replace(
            "destination=\"store\",files=[{path=\"a.bin\"}]",
            "destination=\"checkout\",files=[{path=\"a.bin\",install_path=\"Content/a.bin\"}]",
        )
    } else {
        text
    };
    let declaration: Declaration = toml::from_str(&text).unwrap();
    let registry = BTreeMap::from([(
        ("fixture".into(), "1".into()),
        OpDefinition {
            inputs: BTreeMap::from([(
                "upstream".into(),
                InputRule {
                    role: if reference {
                        InputRole::Reference
                    } else {
                        InputRole::Content
                    },
                    required: false,
                    allow_absent_file: false,
                    allow_selector: false,
                    require_whole_reason: false,
                    item_classes: BTreeSet::from(["Blob".into()]),
                },
            )]),
            output_classes: BTreeSet::from(["Blob".into()]),
            params: BTreeMap::from([(
                "value".into(),
                ParamRule {
                    kind: ParamKind::Integer,
                    required: true,
                },
            )]),
        },
    )]);
    let graph = BuildGraph::validate(declaration, &registry, &["Content".into()]).unwrap();
    let implementation = ImplementationIdentity {
        version: "1".into(),
        digest: "d".repeat(64),
    };
    let runtimes = ["a", "b", "c"]
        .into_iter()
        .map(|id| {
            (
                id.into(),
                Runtime {
                    worker: implementation.clone(),
                    validator: implementation.clone(),
                    staged_inputs: if id == "b" {
                        BTreeMap::from([("upstream".into(), "inputs/upstream".into())])
                    } else {
                        BTreeMap::new()
                    },
                    profile: "default".into(),
                },
            )
        })
        .collect();
    Fixture {
        graph,
        snapshot: BTreeMap::from([("op.py".into(), SnapshotEntry::File(b"fixture".to_vec()))]),
        runtimes,
        versions: BTreeMap::new(),
    }
}
fn build(
    f: &Fixture,
    targets: &[&str],
    demands: &BTreeMap<String, Demand>,
    fake: &mut Fake,
    jobs: &mut Jobs,
    control: &dyn Control,
) -> Report {
    let final_demands = demands
        .iter()
        .map(|(id, d)| (id.clone(), BTreeSet::from([*d])))
        .collect();
    build_final(f, targets, &final_demands, fake, jobs, control)
}
fn build_final(
    f: &Fixture,
    targets: &[&str],
    demands: &BTreeMap<String, FinalDemands>,
    fake: &mut Fake,
    jobs: &mut Jobs,
    control: &dyn Control,
) -> Report {
    jobs.source_guard = Some(fake.source_guard.clone());
    let ts = targets
        .iter()
        .map(|s| Target::Unit((*s).into()))
        .collect::<Vec<_>>();
    run(
        Request::select(
            &f.graph,
            &ts,
            &f.snapshot,
            &f.versions,
            &f.runtimes,
            demands,
        )
        .unwrap(),
        fake,
        jobs,
        control,
        &mut SourceHashCache::default(),
    )
    .unwrap()
}
#[test]
fn frontier_lookup_precedes_compatible_dispatch_and_hits_launch_nothing() {
    let f = fixture(false);
    let trace = Trace::default();
    let mut fake = Fake::new(trace.clone());
    let mut jobs = Jobs::new(trace.clone());
    let demands = BTreeMap::from([("a".into(), Demand::Stored), ("c".into(), Demand::Stored)]);
    let first = build(&f, &["a", "c"], &demands, &mut fake, &mut jobs, &Never);
    assert_eq!(first.batches, vec![vec!["a", "c"]]);
    assert_eq!(
        &trace.borrow()[..3],
        &["lookup:a:Stored", "lookup:c:Stored", "inputs:a"]
    );
    trace.borrow_mut().clear();
    let hit = build(&f, &["a", "c"], &demands, &mut fake, &mut jobs, &Never);
    assert!(hit.batches.is_empty());
    assert!(hit.states.values().all(|s| *s == State::Hit));
    assert_eq!(hit.effects, Effects::default());
}
#[test]
fn equal_output_content_cuts_off_changed_producer_input_key() {
    let f = fixture(false);
    let trace = Trace::default();
    let mut fake = Fake::new(trace.clone());
    let mut jobs = Jobs::new(trace);
    let demands = BTreeMap::from([("b".into(), Demand::Checkout)]);
    let first = build(&f, &["b"], &demands, &mut fake, &mut jobs, &Never);
    let mut changed = fixture(false);
    changed.runtimes.get_mut("a").unwrap().worker.version = "2".into();
    let next = build(&changed, &["b"], &demands, &mut fake, &mut jobs, &Never);
    assert_ne!(first.keys["a"], next.keys["a"]);
    assert_eq!(first.keys["b"], next.keys["b"]);
    assert_eq!(next.states["b"], State::Hit);
    assert_eq!(next.batches, vec![vec!["a"]]);
    fake.outputs.insert("a".into(), "b".repeat(64));
    changed.runtimes.get_mut("a").unwrap().worker.version = "3".into();
    let unequal = build(&changed, &["b"], &demands, &mut fake, &mut jobs, &Never);
    assert_ne!(next.keys["b"], unequal.keys["b"]);
    assert!(matches!(unequal.states["b"], State::Executed(_)));
}
#[test]
fn reference_ordering_does_not_hash_producer_payload() {
    let mut f = fixture(true);
    let trace = Trace::default();
    let mut fake = Fake::new(trace.clone());
    let mut jobs = Jobs::new(trace);
    let demands = BTreeMap::from([("b".into(), Demand::Checkout)]);
    let first = build(&f, &["b"], &demands, &mut fake, &mut jobs, &Never);
    fake.outputs.insert("a".into(), "b".repeat(64));
    f.runtimes.get_mut("a").unwrap().worker.version = "2".into();
    let next = build(&f, &["b"], &demands, &mut fake, &mut jobs, &Never);
    assert_ne!(first.keys["a"], next.keys["a"]);
    assert_eq!(first.keys["b"], next.keys["b"]);
    assert_eq!(next.states["b"], State::Hit);
}
#[test]
fn independent_failure_retains_publication_and_blocks_only_dependents() {
    let f = fixture(false);
    let trace = Trace::default();
    let mut fake = Fake::new(trace.clone());
    let mut jobs = Jobs::new(trace);
    jobs.fail.insert("a".into());
    let demands = BTreeMap::from([("b".into(), Demand::Checkout), ("c".into(), Demand::Stored)]);
    let report = build(&f, &["b", "c"], &demands, &mut fake, &mut jobs, &Never);
    assert!(matches!(report.states["a"], State::Failed(_)));
    assert_eq!(report.states["b"], State::Blocked(vec!["a".into()]));
    assert!(matches!(report.states["c"], State::Executed(_)));
    assert_eq!(report.publications, vec!["c"]);
    assert!(fake.cache.contains_key(&report.keys["c"]));
}
#[test]
fn cancellation_preserves_completed_units_and_settles_queued_work() {
    let f = fixture(false);
    let trace = Trace::default();
    let mut fake = Fake::new(trace.clone());
    let mut jobs = Jobs::new(trace);
    let flag = Rc::new(Cell::new(false));
    jobs.cancel_after = Some(flag.clone());
    let demands = BTreeMap::from([("a".into(), Demand::Stored), ("c".into(), Demand::Stored)]);
    let report = build(&f, &["a", "c"], &demands, &mut fake, &mut jobs, &Flag(flag));
    assert_eq!(report.publications, vec!["a"]);
    assert!(matches!(report.states["a"], State::Executed(_)));
    assert_eq!(report.states["c"], State::Cancelled);
    assert!(report.fatal.is_none());
}

#[test]
fn cancellation_during_input_preparation_does_not_stage_remaining_frontier() {
    let f = fixture(false);
    let trace = Trace::default();
    let mut fake = Fake::new(trace.clone());
    let mut jobs = Jobs::new(trace.clone());
    let flag = Rc::new(Cell::new(false));
    fake.cancel_on_prepare = Some(flag.clone());
    let demands = BTreeMap::from([("a".into(), Demand::Stored), ("c".into(), Demand::Stored)]);
    let report = build(&f, &["a", "c"], &demands, &mut fake, &mut jobs, &Flag(flag));
    assert_eq!(
        trace
            .borrow()
            .iter()
            .filter(|v| v.starts_with("inputs:"))
            .count(),
        1
    );
    assert!(!trace.borrow().iter().any(|v| v.starts_with("execute:")));
    assert_eq!(report.states["a"], State::Cancelled);
    assert_eq!(report.states["c"], State::Cancelled);
    assert_eq!(report.effects.staged_units, 1);
    assert!(report.publications.is_empty());
    assert!(report.fatal.is_none());
}
#[test]
fn faulty_backend_key_and_materialization_claims_refuse() {
    let f = fixture(false);
    let trace = Trace::default();
    let mut fake = Fake::new(trace.clone());
    let mut jobs = Jobs::new(trace);
    let demands = BTreeMap::from([("a".into(), Demand::Stored)]);
    build(&f, &["a"], &demands, &mut fake, &mut jobs, &Never);
    fake.bad_key = true;
    let bad = build(&f, &["a"], &demands, &mut fake, &mut jobs, &Never);
    assert!(matches!(&bad.states["a"],State::Failed(s) if s.contains("another prepared key")));
    fake.bad_key = false;
    fake.bad_settle = true;
    let bad = build(&f, &["a"], &demands, &mut fake, &mut jobs, &Never);
    assert!(matches!(&bad.states["a"],State::Failed(s) if s.contains("No Checkout demand")));
}
#[test]
fn target_materialization_is_explicit_and_current_does_not_rewrite() {
    let f = fixture(false);
    let trace = Trace::default();
    let mut fake = Fake::new(trace.clone());
    let mut jobs = Jobs::new(trace);
    let demands = BTreeMap::from([("b".into(), Demand::Checkout)]);
    let first = build(&f, &["b"], &demands, &mut fake, &mut jobs, &Never);
    assert_eq!(first.effects.installed_units, 1);
    assert_eq!(first.effects.receipt_writes, 1);
    assert!(!first.states.contains_key("c"));
    // Fake Current is deliberately a separate tag; this adapter's incorrect rewrite is detected.
    fake.current.insert("b".into());
    let current = build(&f, &["b"], &demands, &mut fake, &mut jobs, &Never);
    assert_eq!(current.states["b"], State::Current);
    assert_eq!(current.effects, Effects::default());
    fake.bad_settle = true;
    let bad = build(&f, &["b"], &demands, &mut fake, &mut jobs, &Never);
    assert!(matches!(&bad.states["b"],State::Failed(s) if s.contains("Current settlement")));
}

#[test]
fn incompatible_profiles_split_batches_and_publication_failure_preserves_sibling() {
    let mut f = fixture(false);
    f.runtimes.get_mut("c").unwrap().profile = "other-admission-custody".into();
    let trace = Trace::default();
    let mut fake = Fake::new(trace.clone());
    let mut jobs = Jobs::new(trace);
    fake.fail_publish.insert("a".into());
    let demands = BTreeMap::from([("a".into(), Demand::Stored), ("c".into(), Demand::Stored)]);
    let report = build(&f, &["a", "c"], &demands, &mut fake, &mut jobs, &Never);
    assert_eq!(report.batches, vec![vec!["a"], vec!["c"]]);
    assert!(matches!(report.states["a"], State::Failed(_)));
    assert!(matches!(report.states["c"], State::Executed(_)));
    assert_eq!(report.publications, vec!["c"]);
    assert!(fake.cache.contains_key(&report.keys["c"]));
}

#[test]
fn missing_executor_terminal_is_failure_and_never_unlocks_dependents() {
    let mut f = fixture(false);
    f.runtimes.get_mut("c").unwrap().profile = "later-profile".into();
    let trace = Trace::default();
    let mut fake = Fake::new(trace.clone());
    let mut jobs = Jobs::new(trace.clone());
    jobs.omit = true;
    let demands = BTreeMap::from([("b".into(), Demand::Checkout), ("c".into(), Demand::Stored)]);
    let report = build(&f, &["b", "c"], &demands, &mut fake, &mut jobs, &Never);
    assert!(
        matches!(&report.states["a"], State::Failed(reason) if reason.contains("omitted terminal"))
    );
    assert!(
        report
            .fatal
            .as_ref()
            .unwrap()
            .contains("cleanup unresolved")
    );
    assert!(matches!(report.states["b"], State::Blocked(_)));
    assert!(matches!(report.states["c"], State::Blocked(_)));
    assert!(!trace.borrow().iter().any(|event| event == "execute:c"));
    assert!(!report.keys.contains_key("b"));
    assert!(fake.cache.is_empty());
}

#[test]
fn completed_batch_refreshes_new_ready_hit_before_unrelated_dispatch() {
    let mut f = fixture(false);
    f.runtimes.get_mut("c").unwrap().profile = "zzz-unrelated".into();
    f.runtimes.get_mut("c").unwrap().worker.version = "2".into();
    let trace = Trace::default();
    let mut fake = Fake::new(trace.clone());
    let mut jobs = Jobs::new(trace.clone());
    let warm = BTreeMap::from([("b".into(), Demand::Checkout)]);
    let before = build(&f, &["b"], &warm, &mut fake, &mut jobs, &Never);
    trace.borrow_mut().clear();
    f.runtimes.get_mut("a").unwrap().worker.version = "2".into();
    let demands = BTreeMap::from([("b".into(), Demand::Checkout), ("c".into(), Demand::Stored)]);
    let next = build(&f, &["b", "c"], &demands, &mut fake, &mut jobs, &Never);
    assert_ne!(before.keys["a"], next.keys["a"]);
    assert_eq!(before.keys["b"], next.keys["b"]);
    assert_eq!(next.states["b"], State::Hit);
    let events = trace.borrow();
    let ready_hit = events
        .iter()
        .position(|s| s == "lookup:b:Checkout")
        .unwrap();
    let unrelated_job = events.iter().position(|s| s == "execute:c").unwrap();
    assert!(ready_hit < unrelated_job, "{events:?}");
    assert_eq!(events.iter().filter(|s| *s == "lookup:c:Stored").count(), 1);
    assert_eq!(next.batches, vec![vec!["a"], vec!["c"]]);
}

#[test]
fn current_checkout_cannot_satisfy_explicit_stored_demand() {
    let f = fixture(false);
    let trace = Trace::default();
    let mut fake = Fake::new(trace.clone());
    let mut jobs = Jobs::new(trace.clone());
    let checkout = BTreeMap::from([("b".into(), Demand::Checkout)]);
    build(&f, &["b"], &checkout, &mut fake, &mut jobs, &Never);
    fake.current.insert("b".into());
    trace.borrow_mut().clear();
    let stored = BTreeMap::from([("b".into(), Demand::Stored)]);
    let report = build(&f, &["b"], &stored, &mut fake, &mut jobs, &Never);
    assert!(
        matches!(&report.states["b"],State::Failed(reason) if reason.contains("does not satisfy explicit final"))
    );
    assert!(
        !trace
            .borrow()
            .iter()
            .any(|event| event == "settle:b:Stored")
    );
    assert!(report.batches.is_empty());
    assert_eq!(report.effects, Effects::default());
}

#[test]
fn mixed_checkout_targets_use_identity_for_hits_and_stage_only_actual_consumer_misses() {
    for scenario in ["hit", "stage", "unsupported", "changed"] {
        let mut f = fixture_source(false, true);
        let trace = Trace::default();
        let mut fake = Fake::new(trace.clone());
        let mut jobs = Jobs::new(trace.clone());
        let finals = BTreeMap::from([
            ("a".into(), Demand::Checkout),
            ("b".into(), Demand::Checkout),
        ]);
        let warm = build(&f, &["a", "b"], &finals, &mut fake, &mut jobs, &Never);
        fake.cache.remove(&warm.keys["a"]); // mock stored-result loss; identity observation remains
        fake.current.insert("a".into());
        if scenario != "hit" {
            f.runtimes.get_mut("b").unwrap().worker.version = "2".into();
        }
        if scenario == "unsupported" || scenario == "hit" {
            fake.unavailable.insert("b".into());
        }
        if scenario == "changed" {
            fake.changed.insert("b".into());
        }
        trace.borrow_mut().clear();
        let report = build(&f, &["a", "b"], &finals, &mut fake, &mut jobs, &Never);
        assert_eq!(report.states["a"], State::Current);
        assert!(
            !trace
                .borrow()
                .iter()
                .any(|s| s == "execute:a" || s == "inputs:a")
        );
        assert!(!fake.source_guard.get());
        match scenario {
            "hit" => {
                assert_eq!(report.states["b"], State::Hit);
                assert!(report.batches.is_empty());
                assert!(!trace.borrow().iter().any(|s| s == "inputs:b"));
                assert_eq!(report.effects, Effects::default());
            }
            "stage" => {
                assert!(matches!(report.states["b"], State::Executed(_)));
                assert_eq!(report.batches, vec![vec!["b"]]);
                assert_eq!(report.effects.staged_units, 1);
                assert_eq!(report.effects.installed_units, 1);
            }
            _ => {
                assert!(matches!(report.states["b"], State::InputRefused(_)));
                if scenario == "changed" {
                    assert!(matches!(
                        report.states["b"],
                        State::InputRefused(InputFailure::Changed(_))
                    ));
                } else {
                    assert!(matches!(
                        report.states["b"],
                        State::InputRefused(InputFailure::Unavailable(_))
                    ));
                }
                assert!(report.batches.is_empty());
                assert!(!trace.borrow().iter().any(|s| s == "execute:b"));
                assert_eq!(report.effects, Effects::default());
            }
        }
    }
}

#[test]
fn internal_recorded_identity_needs_no_stored_availability_or_stage_on_hit() {
    for current in [false, true] {
        let f = fixture_source(false, true);
        let trace = Trace::default();
        let mut fake = Fake::new(trace.clone());
        let mut jobs = Jobs::new(trace.clone());
        let warm_demands = BTreeMap::from([
            ("a".into(), Demand::Checkout),
            ("b".into(), Demand::Checkout),
        ]);
        let warm = build(&f, &["a", "b"], &warm_demands, &mut fake, &mut jobs, &Never);
        fake.cache.remove(&warm.keys["a"]);
        if current {
            fake.current.insert("a".into());
        } else {
            fake.recorded.insert("a".into());
        }
        fake.unavailable.insert("b".into());
        trace.borrow_mut().clear();
        let finals = BTreeMap::from([("b".into(), Demand::Checkout)]);
        let report = build(&f, &["b"], &finals, &mut fake, &mut jobs, &Never);
        assert_eq!(
            report.states["a"],
            if current {
                State::Current
            } else {
                State::Identity
            }
        );
        assert_eq!(report.states["b"], State::Hit);
        assert!(report.batches.is_empty());
        assert_eq!(report.effects, Effects::default());
        assert!(report.unsatisfied.is_empty());
        assert!(!trace.borrow().iter().any(|s| s.starts_with("inputs:")));
        assert!(!fake.source_guard.get());
    }
}

#[test]
fn dual_explicit_requirements_need_stored_proof_and_checkout_settlement() {
    let f = fixture_source(false, true);
    let trace = Trace::default();
    let mut fake = Fake::new(trace.clone());
    let mut jobs = Jobs::new(trace.clone());
    let checkout = BTreeMap::from([("a".into(), Demand::Checkout)]);
    let warm = build(&f, &["a"], &checkout, &mut fake, &mut jobs, &Never);
    let both = BTreeMap::from([(
        "a".into(),
        BTreeSet::from([Demand::Stored, Demand::Checkout]),
    )]);
    let report = build_final(&f, &["a"], &both, &mut fake, &mut jobs, &Never);
    assert_eq!(report.states["a"], State::Hit);
    assert!(report.batches.is_empty());
    assert_eq!(report.effects, Effects::default());
    fake.current.insert("a".into());
    fake.cache.remove(&warm.keys["a"]);
    trace.borrow_mut().clear();
    let current = build_final(&f, &["a"], &both, &mut fake, &mut jobs, &Never);
    assert!(matches!(current.states["a"], State::Failed(_)));
    assert!(!trace.borrow().iter().any(|s| s.starts_with("settle:")));
    fake.current.clear();
    fake.recorded.insert("a".into());
    let recorded = build_final(&f, &["a"], &both, &mut fake, &mut jobs, &Never);
    assert!(matches!(recorded.states["a"], State::Failed(_)));
    assert!(recorded.batches.is_empty());
    let recorded_checkout = build(&f, &["a"], &checkout, &mut fake, &mut jobs, &Never);
    assert!(matches!(recorded_checkout.states["a"], State::Failed(_)));
    assert!(recorded_checkout.batches.is_empty());
}

#[test]
fn local_completion_keeps_identity_usable_without_claiming_stored_final_satisfaction() {
    let f = fixture(false);
    let trace = Trace::default();
    let mut fake = Fake::new(trace.clone());
    let mut jobs = Jobs::new(trace);
    fake.not_cached.insert("a".into());
    let finals = BTreeMap::from([("a".into(), Demand::Stored), ("b".into(), Demand::Checkout)]);
    let report = build(&f, &["a", "b"], &finals, &mut fake, &mut jobs, &Never);
    assert!(matches!(
        report.states["a"],
        State::Executed(Publication::NotCached(_))
    ));
    assert!(matches!(
        report.states["b"],
        State::Executed(Publication::Cached)
    ));
    assert_eq!(
        report.unsatisfied,
        BTreeMap::from([("a".into(), BTreeSet::from([Demand::Stored]))])
    );
    assert_eq!(report.effects.installed_units, 1);
}
