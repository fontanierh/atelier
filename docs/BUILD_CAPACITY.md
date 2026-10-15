# Capacity admission

Atelier should admit work against available memory and CPU capacity, with additional constraints for GPU use,
temporary disk space and resources that require exclusive access. Agents request a workload profile; the machine
admits it when all requirements fit. A small job need not wait for a particular lane to become free.

**Status: the supervised broker supports the conservative legacy-lock bridge and a sealed, boot-bound full
capacity path. Actual full-mode machine activation and concurrency trials remain separate rollout gates.** The separate
`atelier capacity plan snapshot.json` command still evaluates only supplied snapshots; it never grants admission.
Until clients are explicitly configured, the current render slots, live locks, memory guards and machine board
remain authoritative. This design complements the [incremental build proposal](INCREMENTAL_BUILDS.md):
small products reduce the work, and capacity admission schedules the remaining work safely.

## Broker and guarded-launch migration

The production broker uses its own private Unix socket and SQLite namespace. It is separate from every shadow
database and token below. `atelier capacity serve ABSOLUTE_CONFIG` runs it; `atelier capacity status ABSOLUTE_SOCKET`
reads its state. `atelier capacity supervise ABSOLUTE_CONFIG` installs macOS login/crash supervision. Installing
the service does **not** enable clients. Do not create a second broker to work around an outage or an uncertain grant.
`atelier capacity reconcile ABSOLUTE_SOCKET` releases only reservations whose retained identities have affirmative
exit evidence; it cannot clear an unknown exit. Same-boot recovery rearms live registered identities and permits
the original controller's fenced session to report exit only. A verified OS boot change proves prior local jobs
ended; ordinary daemon restart does not.

The broker configuration is an owner-only JSON file in an owner-only directory, with exactly these fields:

```json
{
  "schema": 1,
  "mode": "legacy-bridge",
  "state_directory": "/absolute/private/capacity-state",
  "disk_pool": "/absolute/build-filesystem",
  "total": {"memory_mib": 32768, "cpu_millis": 10000, "temp_mib": 200000, "io_slots": 2, "gpu_mib": 16000},
  "reserve": {"memory_mib": 8192, "cpu_millis": 2000, "temp_mib": 20000, "io_slots": 0, "gpu_mib": 0}
}
```

These values are illustrative, not this machine's calibrated budget. Disk reservations apply to the one explicit
filesystem; multi-filesystem actions still need profiles and enforcement for each pool. Preserve the installed
service's checkout and Python environment. Drain before changing its service configuration; supervision never
replaces an already running broker with different settings.

Upgraded `guarded.run` clients read the private `~/.cache/atelier/capacity/client.json` only when it exists. An explicit
`ATELIER_CAPACITY_CLIENT` selects another absolute file. The client file contains `schema: 1`, an absolute `socket`,
and `profiles` for `job`, `game` and `compile`. Each profile contains a complete `resources` vector and a `locks`
list. The common launcher always adds its checkout lock. A reservation smaller than the actual guard ceiling
is refused, including a session using a higher game limit. Missing CPU or I/O capacity is refused. Profiles do
not alter worker settings or provide kernel CPU quotas; initial budgets must conservatively cover unchanged workers.
The common launcher can request a performance window with `guarded.run(..., performance=True)`; the configured
broker requires other grants to drain before admission and excludes new grants until release. The benchmark tool requests this window
and still rejects observed render overlap. Benchmark, cinematic capture and sailboat QA each use the common
actual-child guard and admission lifecycle; they do not add a second lock or reservation around it.

An absent default client file keeps legacy behavior. Once configured, a missing broker, invalid profile or
rejected request fails closed. There is no silent fallback. The initial adapter acquires **all three existing
lane mutexes together, nonblocking**, so legacy clients cannot race into an uncharged second lane. If any lane
is busy it releases everything; it never waits with a partial grant. This bridge adds the capacity check while
permitting no additional native overlap. Unsupported fitting requests and callers bypassing the existing lock
are refused; those harnesses need explicit migration before machine activation.

The broker owns the exec gate's only writer. The launcher pins its child and attaches its existing process and
aggregate memory guards before asking for a grant. The broker checks fresh guard receipts, the full resource
vector, named locks, pressure and service epoch, commits accounting, then releases the gate. An offered or queued
request holds no resources. Its logical identity survives an uncharged retry; a separate run nonce fences old gates.

Capacity release concerns the **retained registered process roster**, using pinned kernel exit events and the
controller's actual direct-child wait. It does not turn a failed process lookup or aggregate guard report into
proof that every possible descendant was discovered or exited. Unwitnessed exits, lost guards and crashes retain
uncertain charges. Output certification remains the build system's separate responsibility. The legacy bridge
and foreign-process scan remain necessary while stronger ownership coverage and client migration are validated.

The agent board rollout must show the real machine mode: legacy slots, capacity migration bridge, or full capacity.
It should show reserved resources separately from measured usage, ready age and wait reasons, named locks, and
uncertain reservations that still consume capacity. An unavailable broker must be visible rather than displayed
as an empty pool. Shadow advice below must never appear as a live grant. Slot labels disappear only at cutover.

## Full capacity cutover

**Current overlap eligibility is limited to literal Blender commands with explicit unchanged worker counts.**
Editors, games, compiles, performance windows and unknown commands stay exclusive. These conservative profiles
are not calibrated or learned by phase/input scale; richer estimation and throughput measurements remain follow-up work.

Schema 1 bridge configuration remains usable without a reboot and retains exclusive legacy lanes. Full mode
uses broker configuration `schema: 2`, `mode: "capacity"`, and one additional `cutover` field pointing to the
machine's default `~/.cache/atelier/capacity/cutover.json`. Its remaining fields match the bridge configuration.
The client uses `schema: 2` and the same additional `cutover` field alongside `socket` and `profiles`.
Budgets, disk pool, endpoint and the exact broker configuration hash are bound into the cutover record.
Changing them requires a separately reviewed transition; neither service recovery nor clients rewrite that proof.

Full jobs retain one `render_lock` context. It opens the same three existing legacy lane inodes read-only and
takes all three shared flocks nonblocking, releasing any partial acquisition on refusal. It never writes or
truncates the legacy holder records. Resource vectors and named locks then decide compatible overlap in the
serialized broker, while actual-child and aggregate guards remain mandatory. Games, compiles and performance
windows remain exclusive initially. An explicit bounded Blender thread argument reserves at least that many
CPU units: the build default remains six, and an explicit three remains three. Unknown commands and compound
wrappers reserve the entire managed CPU budget and require exclusion; compiles also reserve at least the unchanged
three compiler workers. These are conservative scheduling units, not kernel quotas. Every reservation covers the
actual guard ceiling, even when a previous step measured only 3 GiB. Neither threads nor guard limits are changed.
Explicit sessions undergo the same command, checkout-lock and resource checks as configured sessions.

The compatibility proof is deliberately stronger than an agent acknowledgement or an empty process scan:

1. Upgrade or explicitly refuse every known native launcher and drain live jobs. Preserve the existing three
   mutex files, with no inode replacement, hard links or ACL write permission. Stop/reap unmanaged persistent workers.
2. In a separately approved machine maintenance window, `atelier capacity prepare-cutover ABSOLUTE_FULL_CONFIG`
   takes admission exclusion plus all three exclusive legacy mutexes and records `preparing` durably before sealing
   those exact owned, single-link files to mode `0400`. It verifies same-UID write-open denial, then records `sealed`.
   A partial failure remains a refusal state; no command automatically unseals or removes the record.
3. A verified new OS boot **after sealing** closes preopened writable descriptors, including inherited or transferred
   ones. Permission changes alone cannot revoke them. Neither a process/lsof scan, two stable scans, an operator
   boolean nor immutable flags establish closure. Without a positive boot UUID change, activation refuses.
4. `atelier capacity activate-cutover ABSOLUTE_FULL_CONFIG` verifies the new boot and all recorded inode/device,
   change-time and permission pins under exclusive flocks, then records `active`. Install the reviewed full broker
   and client settings through the existing explicit service procedure; do not run a second broker or interrupt one
   that still owns charged grants. This source change does not execute any of these machine operations.
5. Validate one guarded job and crash/recovery negatives before controlled overlap trials. Do not infer useful
   throughput or safe new coexistence combinations merely from full-mode availability.

Every full startup and GO checks the seal. A replaced inode, writable ACL, changed policy or unavailable boot
observation refuses new work; held allocations become uncertain and stay charged. A controller/broker crash may
drop shared descriptors but cannot remove the seal or durable charges. Restart fences clients; unknown ownership
does not become free capacity. Foreign-scan exclusions use exact PID/start identities from verified charged
rosters, with no family expansion or truncated public status list. Failed, partial or oversized process observations
refuse. The broker repeats that check before final pressure, guard and child-identity validation and GO commit.
It rechecks the seal and every charged peer's controller/guard health after slow observations. A refused candidate
cannot erase a positively observed enforcement loss; that peer stays charged while candidate vector/lock changes roll back.

Preparing, sealed and active records refuse unsupported raw launchers: stream startup, engine setup's unmanaged
inner bootstrap, animation-lab persistent model/backend processes, and the direct character/kit laboratory helpers.
They are **unsupported until migrated**, rather than counted as admitted jobs. Direct legacy render-lock users
such as artifact reuse also refuse full cutover. An absent or invalid client file cannot restore legacy slots while
any cutover marker exists. Old `a+` launchers fail their mandatory holder-record write/open against the seal after
the boot boundary; all active agents still need reviewed migrated code or explicit refusal before activation.
Rollback is an explicit maintenance operation after positively drained/reaped work; there is no automatic unseal.

The board accepts only the bridge pair `(legacy-bridge, false)` or full pair `(capacity, true)`. In full mode it
shows broker reservations instead of legacy holder rows. Compatibility or ownership recovery pauses grants and
does not assert a healthy seal. Missing or stale observations retain unknown availability, never a free pool.

`guarded.run` also writes bounded atomic `execution-timings.json` diagnostics with `schema: 1`, an invocation UUID,
nullable `admission_seconds` (entry through GO acknowledgement), and nullable `child_lifetime_seconds` (spawn
observation through observed child exit). Lifetime includes gated startup. `execution_seconds` is currently null
without a pinned child gate-consumption event. A caller can supply `invocation_id=UUID_HEX`; the prior report is
cleared before the attempt; inability to clear disables publication without changing the guarded result, and a
rejected argument/profile may leave no report. These diagnostics never certify
outputs or substitute for exit/guard receipts, and absent reports mean unknown durations.

## Try the shadow planner

```sh
uv run atelier capacity plan docs/examples/capacity.json --json
```

The example is synthetic, not a live resource snapshot. Quantities are integer MiB, thousandths of a CPU core,
and I/O slots. On the unified-memory model, `memory_mib` includes GPU allocations; `gpu_mib` is an additional
subset ceiling and cannot exceed it. Total capacity includes the host reserve. Existing holders and queued
requests must have distinct IDs; queue entries carry their original `ready_at` and `bypasses` values.

The implementation checks complete resource sets and named locks, models immediate atomic phase replacement,
excludes overlapping performance windows, and protects waiters after two short bypasses. Advice can say
`would-admit`, but always carries `admission: false`. It does not observe processes, maintain leases, update queue
ages or enforce worker limits. Those belong to the proposed supervised service and its rollout tests below.

A ready request whose resources plus the host reserve exceed total capacity even with no holders receives
`cannot-fit`, with the exceeded dimensions named. This is terminal advice for the supplied snapshot, not a claim
about future machine configurations. Such requests neither protect the queue nor consume virtual capacity;
the next feasible waiter keeps its original age and fairness protection. A request that fits an empty snapshot
can still `wait` for active holders, named locks or a performance window to drain.

## Exercise durable shadow lifecycles

```sh
experiment=$(mktemp -d)
uv run atelier capacity shadow docs/examples/capacity-shadow.json --state "$experiment/capacity.sqlite"
```

This applies supplied operations and synthetic observations to an explicit absolute database path. It never reads
live processes, render locks or supervisor telemetry, and never launches or signals a workload. Every response
says `mode: shadow` and `admission: false`. A `shadow.` token controls only a simulated lifecycle; no native
launcher accepts it. The existing `capacity plan` command remains side-effect free.

The database directory must already exist, belong to the user and have owner-only permissions, as `mktemp -d`
provides. Database files and SQLite sidecars must be private, owned, regular and single-link; symlinks and unknown
existing SQLite files are refused. The database has its own application identity and schema version. These checks
protect against accidental reuse of unrelated files; this is not a boundary against a hostile process running as
the same account. Databases larger than 64 MiB are refused before opening for mutation; an accepted transaction
can grow the file past that threshold, so it is not a disk quota. Fixtures are limited to 4 MiB and 1000 operations.

`ShadowService(database, observe=...)` exposes `apply(operation, now=...)`. The injected observation is an
`Observation`: sample time, healthy/complete flags, available memory and disk, pinned process states and ownership
edges, and per-request measured memory/allocated temporary disk. All facts are supplied by the experiment. A
`complete` flag is not proof of native process coverage. Missing, stale, future-dated or unhealthy observations
refuse new allocations. A clock regression is rejected; timestamps and stable first-ready sequences are retained.

Operations carry a unique `id`, an `action` and, after initialization, the current `epoch`:

| Action | Additional fields and behavior |
| --- | --- |
| `init` | `total`, `reserve`: initialize the full resource vector, including host headroom |
| `submit` | `request_id`, `owner`, `checkout`, `resources`, `launcher: [pid, start]`; optional `locks`, `seconds`, `performance`, `ready` |
| `ready`, `cancel` | `request_id`; an active holder cannot queue or cancel; requeue after release also requires a new `launcher` |
| `schedule` | Atomically allocate complete resource vectors and exclusive named-lock sets, or retain the request in the queue |
| `register` | `request_id`, `token`, `child: [pid, start]`; requires an observed live pinned launcher/child edge |
| `running` | `request_id`, `token`, `guard_ready: true`; only after child registration |
| `heartbeat` | `request_id`, `token`; cannot renew an uncertain lease |
| `replace` | `request_id`, `token`, complete `resources` and `locks`; optional `performance`; refusal leaves the old grant intact and never queues an upgrade |
| `release` | `request_id`, `token`; requires fresh complete observations proving the launcher and all retained descendants exited |
| `restart`, `reconcile` | Fence old leases, retain their charges, and drain observed survivors before scheduling resumes |
| `status` | Return a retained snapshot without lease tokens; this driver operation records its retry receipt |

`BEGIN IMMEDIATE` serializes the complete state change and its idempotent result. Retrying the same operation ID
and content returns the original receipt; changed content is rejected. First-ready time and bypass counts survive
refusals, database reopening and requeue. At most one phase per owner may be active. Two committed short-job
bypasses protect the oldest feasible long waiter, including inside a single scheduling batch. Impossible requests
do not protect the queue. `ready: false` denotes a request still waiting for prerequisites.

Reopening the database is a client reconnect; `restart` explicitly models service failure and advances the epoch.
Heartbeat expiry or incomplete ownership makes a lease uncertain without freeing memory or named locks. Recorded
descendants remain owned after their parent exits. PID reuse does not establish either ownership or exit. Recovery
conservatively drains all old allocations; guard reattachment and continued execution across restart are outside
this first protocol. No scheduler process or startup service is installed.

The pressure check charges a candidate plus existing holders' unconsumed growth and host headroom against observed
availability, separately from the total reservation ceiling. It does not subtract complete reservations from free
memory that already reflects their allocations. Temporary disk is one explicitly modeled pool; multi-filesystem
accounting, shared named locks, queue deadlines and supported worker controls remain future protocol work.

Focused tests exercise concurrent SQLite clients, process death during a transaction, restart fencing, PID reuse,
detached descendants, refused upgrades, queue age and pressure failures without native imports or render admission.
They do not validate a native child launch barrier or a real guard-ready receipt. Native integration must block
useful child work until registration and independent guard readiness are established; current guarded launchers
are unchanged. The migration and native acceptance gates below still apply.

## Exercise a closed launch barrier

```sh
experiment=$(mktemp -d)
uv run atelier capacity probe "$experiment/probe.sqlite"
```

This explicit one-shot experiment launches only two fixed, harmless Python programs. A controller owns a launcher;
that launcher owns one worker, which waits on a private inherited socket before writing its single useful byte.
The controller submits the launcher to a fresh `ShadowService`, registers the worker's pinned identity, records
**synthetic** guard readiness, and checks a current-epoch heartbeat before opening the gate. Readiness, gate and
wait messages bind the epoch, a per-run nonce and the relevant OS process-start identities. macOS uses the existing
libproc birth identity and Linux uses process start ticks; unsupported platforms refuse. No process-table scan,
native program, render lock, live guard or scheduler state participates.

The roster is complete only by construction: both programs are fixed, and only the launcher creates a child.
Resource amounts, availability and guard readiness are fixtures, not measurements. The launcher must report its
exact worker wait result over the inherited socket, and the controller must itself wait for the launcher. Only
those two facts allow release. An absent or malformed worker wait receipt or an unproven wait retains uncertainty
and shadow charges; a missing PID or detached parent is never evidence of exit. Readiness or gate identity
mismatches refuse useful work. EOF refuses
the useful byte, and channel waits and owned-child cleanup have finite timeouts. The explicit database remains
for inspection on failure; the command never automatically reconciles a fenced lease or retries an experiment.

Use a fresh database in an owner-only directory with one controller and no other service clients. This is a local
lifecycle experiment, not hostile-code isolation or a concurrent service-to-launcher fencing protocol: it does not
make the heartbeat and gate write atomic with another client's restart. Every report says `admission: false` and
`native_eligible: false`. No arbitrary argv, recipe or workload is accepted, and the native migration gates remain open.

## Inspect retained resource history

```sh
uv run atelier capacity history build/sandbox/logs/unreal.compile.guard --json
```

This reads existing `memory-health.json`, `memory-health.jsonl` and the rotated `memory-health.previous.jsonl`,
plus separately watched process reports in that directory. It does not start a process, query live usage, change
guard settings or grant admission. Missing files produce unknown history. Reads and report sizes are bounded;
invalid, changing or truncated data is reported without copying raw records or private error text into the result.

Histories distinguish PID/start identities and sampling sessions. A restarted monitor's elapsed-time reset starts
a new session, and a final sample already in the history is counted once. Reports show observed footprint peaks,
guard-reported peaks, sampled spans, limit changes, the last recorded state and raw CPU counter deltas when valid.
Unknown values stay unknown. CPU counter units are not translated into a worker budget.

These are retained observations, not proof of command success or current liveness. A normal process exit may leave
the last state as `running`; a sampled span is not the command's full duration. A launcher and its watched children
remain separate: summing their individual peaks does not measure a simultaneous process-tree peak. Historical logs
also cannot reliably assign measurements to instrumented phases, prove complete descendant coverage or estimate
temporary disk demand. Calibrated resource profiles and admission still require the migration evidence below.
The separate `owned_tree` section reads the latest `memory-health-tree.json` receipt when present. Its footprint
and guard-reported peak describe the sampled simultaneous owned tree, without adding any per-process peaks.
It records the owner's pinned identity, last state and cleanup flag; missing or invalid values stay unknown.
This single retained receipt provides no CPU utilization, phase history or calibrated reservation. Older guards
without that file still have their per-process history; an absent aggregate receipt is reported explicitly.

Compile-kind commands, including editor compilation, UAT packaging and the build-tool bootstrap, also run an
independent aggregate descendant guard under the same admission and memory ceiling (normally 10 GiB). The
launcher waits for a matching live guard receipt before executing. The guard samples the wrapper plus owned
descendants every quarter second, retains observed ownership across intermediate exits, and excludes shared
Zen/Trace services and their descendants. Its `memory-health-tree.json` records the simultaneous sampled sum
and its peak; this is distinct from summing separate process peaks. Per-process guards and helper cleanup remain.
Missing, stale or failed monitor receipts fail the command, including after a zero launcher exit. Sampling can
miss short-lived processes or allocation spikes between observations; this is not a whole-host memory measure
or a throughput benchmark. Compound network QA retains its existing separate aggregate guard protocol.

## What replaces a slot

A request describes one runnable phase, its owner and checkout, expected duration, resource requirements and
exclusive resources. Recipes supply defaults; measured history refines them. An agent may request a budget,
but cannot obtain admission by understating a known workload or exceeding machine/session policy.

| Requirement | Meaning |
| --- | --- |
| Memory reservation | A conservative ceiling for the owned process tree during this phase, including a margin |
| CPU budget | A configured amount of sustained worker capacity, translated to supported tool worker limits |
| GPU requirement | A compatibility class or exclusive graphics reservation until concurrent use is characterized |
| Temporary disk | Expected additional unique bytes on each affected filesystem, with recovery headroom |
| Named locks | Exclusive or shared access to a checkout, compiler mutex, output inventory or other real resource |
| Profile identity | Tool, phase, input scale, renderer and worker settings used to interpret past measurements |

Memory and CPU are separate dimensions. They are never added into one score for admission. For illustration,
suppose the configured build pool has 16 GiB and six CPU worker units after headroom is deducted:

| Ready phase | Memory | CPU units | Can coexist if named/GPU constraints also allow it? |
| --- | --- | --- | --- |
| Import batch | 8 GiB | 3 | Yes, with the two jobs below |
| Mesh generation | 3 GiB | 1 | Yes |
| Artifact compression | 4 GiB | 2 | Yes; combined total is 15 GiB and 6 units |
| Additional mesh generation | 3 GiB | 1 | Waits: both budgets would be exceeded |

These are illustrative requests, not calibrated settings for this machine. CPU units are a scheduling convention,
not a promise of dedicated physical cores; performance and efficiency cores have different throughput. Memory
reservation is admission accounting, not physical preallocation or an OS-enforced partition.

## One authority and an atomic grant

Use a machine-local capacity service shared by all checkouts. Durable state and a single writer transaction
cover the entire request: memory, CPU, disk and named locks are granted together or none are. Two agents cannot
both observe the same free memory and launch. The advisory board displays the result; it does not grant capacity.

The service issues an unforgeable local lease tied to the request, launcher identity and process start identity.
The existing guarded launcher registers the actual child and descendants before useful work begins. It keeps
its independent guard and resource-policy setup. CLI, build, play and custom guarded harnesses use this one
admission API. Expensive Python generation and archive/restore jobs also declare resources; cheap metadata
lookups should not require an Unreal-sized reservation.

Separate two safeguards:

1. **Accounting:** total reservations cannot exceed configured budgets, including phase headroom.
2. **Live pressure:** current available memory, compression/swap pressure, CPU load and disk availability must
   also permit admission. Unmanaged applications and shared services can consume capacity outside the ledger.

Do not subtract an active job's whole reservation from an available-memory reading that already includes its
current usage. The extra risk is its remaining growth: a candidate needs its reservation plus the sum of existing
reservations' unconsumed headroom, and host safety headroom. Reconcile this conservative check with the total
reservation limit. If sampling is stale, missing or contradictory, refuse new heavy work rather than guess.

Disk reservations are conservative estimates, not exact predictions of APFS copy-on-write allocation. Check the
live filesystem free-space floor at admission, every phase boundary and during large transfers/cooks. Charge
remaining expected growth without double-counting bytes already allocated, and preserve completion/recovery
headroom. Do not credit another job's planned deletion or assume a clone will remain cheap after modification.

Count shared Zen/Trace services once in host/service accounting, not once per job. Track their observed growth
and reserve service headroom. On unified-memory hardware, GPU allocation also competes for memory; do not count
it as a separate physical pool. Use measured physical-footprint accounting and host pressure together, acknowledging
sampling delay and shared-page accounting limits. Swap space is not extra build capacity.

## Reservation, enforcement and estimates

Use separate fields for expected peak and reserved ceiling. Admission charges the ceiling, and the aggregate
owned-tree guard enforces it; never reserve 3 GiB while allowing an unaccounted 10 GiB peak. Leave burst margin
inside the reservation and machine headroom for sampling delay. A lower existing per-process or game limit still
applies. Capacity admission must not silently raise the current game limits or authorize new memory exceptions.

Reuse pinned PID/start-time ownership tracking. Validate and integrate the existing aggregate tree-guard
machinery across capacity-managed launches before cutover; ordinary guarded launches currently use separate
per-process monitors. Account for compiler and
shader workers, SDK helpers and subprocesses that outlive their immediate parent. Shared engine services remain
excluded from job-owned termination. Stopping or releasing an agent session does not prove that its job exited.

CPU requests must produce real settings for Blender threads, compiler/shader workers and numerical thread pools
where supported. Include editor and parent-process overhead in profiles. On macOS these controls and measured
utilization are best-effort bounds, not kernel CPU quotas. A tool that cannot honor a narrower budget needs a
conservative profile. Preserve the existing worker tuning until concurrency measurements support a change;
do not multiply three workers by every admitted job and call that a three-worker machine budget.

Learn profiles by tool/context, phase and input scale, including mesh counts, triangle counts or texture sizes
where they predict cost. Keep peak, duration and uncertainty, not just the last successful sample. Start unknown
or substantially changed workloads with a conservative reservation and restricted coexistence. Underestimation
raises the next estimate and records a failed admission model; it must not trigger an automatic retry loop.

If a job approaches its ceiling, it may request an atomic increase before consuming it, subject to policy and
available capacity. If no increase is available, finish a safe small unit and checkpoint/exit where possible;
otherwise the existing guard ends that owned job at its limit. The scheduler cannot rely on cooperative progress
inside a blocked engine allocation, so it must preserve an independent enforcement path. Never take another
owner's capacity or signal its process to make a request fit.
Keep increase requests cheap and record refused increases as profile evidence, alongside observed peaks, so
spiky workloads can improve their estimates without permanently reserving an unnecessarily large budget.

## Phases, locks and fairness

Reserve only the current phase when there is a safe transition. A build might perform a small cache transfer,
a memory-heavy import, a CPU-heavy compile and a disk-heavy package. It should not hold its worst-case request
for all four. A cache hit may avoid the import reservation entirely.

Do not infer a phase change from a quiet log. Transition at an explicit recipe boundary, and lower a memory
reservation only after observed usage has fallen and the next phase's ceiling is sufficient. If Unreal retains
allocations, that memory remains reserved until it is released or the process ends.

Avoid upgrade deadlocks across the entire resource vector, including named locks. An upgrade atomically requests
all additions and never blocks while retaining a partial grant. On refusal, the job can continue only within its
existing grant; it must finish or checkpoint/exit and release **all** reservations and named locks before queueing
again. A queued phase holds neither memory/CPU/disk reservations nor a checkout lock. This prevents a checkout
owner waiting for memory while that memory's owner waits for the checkout.

A job that cannot release a checkout between phases declares all locks it must retain and its maximum resource
budget together at first admission, with a deadline. It executes within that grant instead of queueing while
holding it; only proven reductions are possible without a fresh admission. Queueing has a deadline, cancellation
and a visible reason. Phase transitions and cleanup must test for leaked locks as well as leaked memory charges.

Named locks describe actual incompatibilities:

- A checkout's Content/Binaries mutation lease conflicts with its editor/game readers. A restore cannot run
  behind a live editor's back just because memory is available. Compatibility may become finer only with proof.
- Native builds respect the real UBT mutex scope. Retain the current conservative compile exclusion initially;
  permit compile plus unrelated work only after measuring both safety and throughput.
- Any play or playtest judging FPS or feel defaults to an exclusive performance window. It excludes competing
  CPU-heavy, GPU-heavy, substantial disk and memory-pressure work, including encodes and compiles; spare CPU
  units or background QoS do not make those safe companions. The window starts after incompatible work drains,
  never by interrupting another owner. Other GPU-heavy jobs still need measured compatibility rules.
- Output installation and cache garbage collection respect artifact ownership, snapshot leases and pins.

Use a durable ready queue with first-ready time preserved across refusals and retries. Allow bounded short-job
backfill, then protect the oldest compatible large request by stopping admissions that would postpone it. Keep
the current short-job preference and two-bypass limit as the initial fairness policy; use per-owner fairness so
splitting one build into hundreds of requests does not monopolize the queue. Distinguish a ready job from one
waiting for inputs. A request that exceeds all allowed machine configurations fails with a useful explanation.

Duration estimates inform backfill but are not reliable promises. Aging must eventually reserve enough capacity
for large requests without forcibly preempting other owners. Approved interactive/performance windows have
explicit scope and expiry; agents cannot assign themselves a priority that defeats fairness.

## Failure and recovery

Heartbeat expiry alone never releases a live job's reservation. Pin process identities and retain ownership of
surviving descendants. On launcher/service failure, preserve guards, stop new admission, reconstruct live leases
and reconcile named locks before resuming. A restarted service fences stale clients from making new grants;
it does not assume their running children vanished. Unknown heavy processes remain a reason to refuse until
their ownership and resource use are understood, following the current foreign-process safety rule.

If the service is unavailable, no new heavy work starts. The machine's configured service supervisor owns normal
restart and recovery; the operator can request a restart through supported administration. Agents may report the
failure but may not create a second scheduler or bypass it. Recovery reconciles live jobs before accepting grants.

Release accounting only after the tracked job tree exits or after a verified phase downgrade. Report orphaned
helpers and use the existing owner-aware reaper. Retain evidence for an overrun, guard exit, cancellation and
incomplete artifact transaction. A resource failure never certifies an output or publishes a success receipt.

If external activity creates memory pressure, freeze new admissions and use only supported worker reductions or
cooperative checkpoints for existing jobs. Preserve independent job limits and their stop authority. Do not promise
that reservations can prevent every system-wide OOM caused by unmanaged applications.

## Observable behavior

The board should display requested, reserved and measured resources, active phase, estimate confidence, queue
age, wait reason, named locks and next safe boundary. Example explanations are "needs 6 GiB; 4 GiB unreserved"
or "capacity fits; checkout is in use." Report queue time separately from execution and wasted/retried work.

Operators configure machine headroom and allowed policies once. Recipes and measured profiles handle routine
requests. Agents retain the familiar `atelier build`, `play` and guarded entry points; no manual slot negotiation
should be needed for ordinary eligible jobs. The board still carries task coordination and performance windows.

## Migration and acceptance

1. Collect per-phase owned-tree memory, CPU and disk measurements under today's slots. Establish machine
   headroom and supported worker controls. Add pure scheduler tests with fake processes and clocks.
2. Run the capacity service in shadow mode: explain hypothetical grants while current locks remain the sole
   admission authority. Compare decisions against pressure and observed peaks without adding concurrency.
3. Install a common compatibility gate in every active launcher, including build/play, package, guarded harnesses,
   streams, fitting and custom tooling. Verify client protocol versions; drain legacy holders and use a controlled
   cutover. Two independent schedulers must never grant the same machine capacity. Unknown legacy clients fail
   closed. Document and test rollback to slots only after capacity-held jobs drain.
4. Enable conservative capacity admission with current exclusions, guards and worker limits. Validate leases,
   process ownership and crash recovery first. Allow new coexistence combinations one at a time on measurements.
5. Adopt phase requests and bounded memory-sized import batches. Replace slot-specific board UI, command help,
   setup examples, agent instructions and obsolete lane configuration together. Remove the old admission path
   once migration support ends; leave one documented authority.

Acceptance covers simultaneous requests, stale telemetry, service restart, PID reuse, detached children,
shared-service growth, underestimated memory, locks held across refused phase upgrades, phase-upgrade deadlock,
disk-floor changes during a cook/clone, service outage and restart, performance-window contention and starvation. Native
concurrency trials use ordinary guarded admission and include negative controls. Measure useful throughput,
interactive responsiveness, p50/p95 queue delay and peak pressure. More concurrent processes is not itself success.
