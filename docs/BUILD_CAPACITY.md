# Capacity admission

Atelier should admit work against available memory and CPU capacity, with additional constraints for GPU use
and resources that require exclusive access. Disk space is telemetry, not an admission budget or lock.
Agents request a workload profile; the machine
admits it when all requirements fit. A small job need not wait for a particular lane to become free.

**Status: the supervised broker supports the conservative legacy-lock bridge and a sealed, boot-bound full
capacity path, plus explicit sealed exclusive maintenance. Actual full-mode machine activation and concurrency trials remain separate rollout gates.** The separate
`atelier capacity plan snapshot.json` command still evaluates only supplied snapshots; it never grants admission.
Until clients are explicitly configured, the current render slots, live locks, memory guards and machine board
remain authoritative. This design complements the [incremental build proposal](INCREMENTAL_BUILDS.md):
small products reduce the work, and capacity admission schedules the remaining work safely.

## Agent workflow

This is the operational runbook for agents. Use only the mode announced by the operator and confirmed by
fresh broker status. An explicit maintenance announcement is separate from full-mode cutover. Merging implementation PRs, installing a broker or
seeing a quiet machine does not change its live mode. Check the actual broker status and the board's fresh
observation: `(legacy-bridge, false)` means bridge; `(sealed-maintenance, false)` means exclusive maintenance;
`(capacity, true)` means full capacity. Maintenance is one guarded job at a time, not full concurrency. Use the socket selected
by the installed client when running `uv run atelier capacity status ABSOLUTE_SOCKET`. Missing or stale status
means availability is unknown. The launcher enforces live admission and guard checks at every heavy boundary.

In confirmed full capacity mode, normal builds and plays **self-admit**. Run the ordinary command with
`ATELIER_AGENT` and the default client: no pre-announcement, acknowledgement, coordinator permission,
manual Holding/Waiting edit or hold/release handshake is required per build or step. Keep the listener active
for real incidents and owner steering. Read current maintenance/incident instructions; report an actual refusal
or failure when help is needed. Coordinators collect routine timings from logs, receipts and cook observations
instead of asking builders to post them. A deliberately quiet capture or a bounded service maintenance remains
an explicit exception, with a stated end condition; it must not become a standing gate for future normal work.

Before adopting main, finish the checkout's current native child and stop its enclosing caller at a child-free
boundary so it cannot automatically launch another child. Only then merge and run `uv sync`. Keep generated
Content, Binaries, build stamps and caches; use the verified [reuse procedure](../AGENTS.md#reusing-builds) for a
fresh checkout instead of rebuilding everything or sharing mutable directories. Do not change a running job's
source, Python environment or installed engine underneath it.

Inspect `uv run atelier build yorimichi --plan` before a large run. Separate genuine source changes and the first
adoption of new product owners from repeated invalidation of unchanged work. A real ownership or input-contract
migration may require one refresh; report repeated broad rebuilds with the plan and source revisions. Keep real
inputs and output verification intact: do not manufacture stamps, use `--touch` to hide a required build, or
force regeneration to make the plan look simpler. Prefer the specific required steps and retain reusable outputs.

Only on a machine explicitly announced as a bridge pilot, use your registered board owner and its pilot client:

```sh
ATELIER_AGENT=YOUR_OWNER ATELIER_CAPACITY_CLIENT="$HOME/.cache/atelier/capacity/pilot-client.json" nice -n 10 uv run atelier build yorimichi
ATELIER_AGENT=YOUR_OWNER ATELIER_CAPACITY_CLIENT="$HOME/.cache/atelier/capacity/pilot-client.json" nice -n 10 uv run atelier play yorimichi
```

Keep the existing worker counts, memory ceilings and saved play preferences. The bridge requires both a broker
grant and all legacy lane locks; it authorizes no extra overlap. Quit test games promptly. Only after the operator's
maintenance or full-mode announcement and fresh matching status, remove the explicit pilot override
(`unset ATELIER_CAPACITY_CLIENT`) and use the installed default client. Continue identifying each ordinary command,
for example `ATELIER_AGENT=YOUR_OWNER nice -n 10 uv run atelier build yorimichi` (or `play yorimichi`).
Agents do not edit client profiles, broker configuration, service settings or cutover records to change modes.
Removing the override is a rollout step, never a fallback after a refusal.

If admission or a running grant is refused, retain the command, source revision, guard directory, stdout,
`memory-health.json`, `memory-health-tree.json` and any execution timings. Report the broker's reason, owner,
phase and the next safe boundary. A charged or uncertain reservation still holds capacity even when measured
memory is small. Recovery accepts complete known-ancestry retained exits, or, for bridge and sealed-mode
performance-exclusive grants, a positively exited root plus its matching bound aggregate guard's successful
terminal empty-tree cleanup receipt. Older monitors could retain their pre-cleanup sample despite successful
cleanup; that sample is accepted only when every reported tail identity is retained and has an affirmative
exit witness, no tail is live, and its nonnegative footprint sum exactly matches the receipt within the guard
ceiling. Names, missing PIDs and elapsed time never substitute for those exits. The latter witnesses the monitored owned tree rather than inventing
individual historical exits. Neither policy certifies outputs; uncertainty remains charged without its required
evidence. PID absence or heartbeat expiry alone never establishes release. If a later invocation overwrote the
bound report, authorized recovery can attest the preserved original with
`atelier capacity reconcile ABSOLUTE_SOCKET --request-id REQUEST_ID --preserved-terminal ABSOLUTE_ARCHIVE`;
the broker applies the same scoped checks and records the evidence hash and preservation provenance.
Do not clear the database or locks, restart a live broker, drop the client environment, or launch through another
path. Ask the operator for help when the documented recovery cannot establish a safe next step.

Before the launcher's start RPC, a transient process-observation error retries once automatically. The
broker actor keeps its existing single-shot observation and never performs this retry. Each complete
snapshot attempt retains its two-second bound and owned-observer cleanup; if the first observer's exit is
pending, one additional one-second wait must positively settle it before another observer starts. An attempt
can also spend at most one second reaping its own killed observer, so the worst-case preflight is bounded
by seven seconds. No useful child starts during this retry. The second observation must be fresh, complete
and parseable, and native identity/ownership checks still apply without retry. An unsettled observer,
persistent observation failure or unregistered native process refuses admission. Job durations, resource
budgets, broker RPC deadlines and both memory guards are unchanged.

Normal guarded commands wait automatically when the broker positively queues them. They refresh the
same uncharged request once a second, retain its first-ready age, and print progress at least every 25 seconds.
No child, launch gate, resources or legacy locks are held while waiting. The wait ends when selected,
on cancellation, or after 30 minutes; rerunning the same job after the deadline retains its ready age.
Policy, protocol, ownership and fencing failures still refuse immediately without fallback.
The queue wait happens before the normal launch/guard lifecycle and does not extend any RPC or child
execution deadline. No board announcement or coordinator permission is required.

A session may reconcile one transient connection/timeout failure for `offer`, `owned`, `check` or `close`
by resending the identical request once. Each call retains its two-second deadline (at most four seconds
for both attempts with the normal client). Offers remain uncharged; checks retain the same process delta,
epoch and nonce; close still requires an affirmative released response after normal cleanup. A second
transport failure refuses normally. Gate creation, launch/start and phase replacement never replay, because
a lost response can conceal a state change. A broker restart or changed session identity still fences the
caller; reconciliation never clears an uncertain reservation or grants local fallback admission.

On an admitted launch failure, the launcher reaps its owned workload, waits once for its existing
aggregate monitor's bounded terminal settlement, and only then asks the broker to close the reservation.
This keeps a late post-drain receipt from racing the close. A failed command remains failed, and a failed
monitor still fails the job. A refused broker release retains its reservation. Cleanup authorizes no new launch.

Read board reservations as scheduling budgets, separately from measured process memory and host availability.
Recovery pauses new grants; inspect the uncertain jobs and their owners, or the compatibility reason, rather than
treating the warning as spare capacity. Optional I/O tokens are a contention budget, not disk-space protection.
The queue includes only current `queued` requests. `waiting` records require a fresh retry, hold no capacity,
and remain in durable history without counting as active waiters.

### Choosing resources for a job

Choose the command and its supported worker setting, then use ordinary `atelier build`/`play` or the shared
guarded launcher. The launcher derives the reservation; agents do not edit `client.json`, broker settings or
resource fields to fit the current free budget. A CPU unit is a scheduling budget, not a dedicated core or a
kernel throttle. A low average CPU reading alone does not establish a lower safe worker envelope.

| Job | CPU request | Memory request | Exclusion |
| --- | --- | --- | --- |
| Board commands, planning and other lightweight metadata work | No heavy reservation | No heavy reservation | None |
| Headless Blender generation with explicit `--threads N` | Exactly N CPU units; e.g. 3 threads requests 3 | Nominal guard ceiling, normally 10 GiB; automatic 4 GiB only with valid prior peak at most 3 GiB and a compatible GPU envelope | Ordinary bounded generation can share capacity when all budgets and named locks fit |
| Blender rendering, baking or simulation | Explicit supported worker setting justified by that workload's measurements | Guard ceiling covering its measured peak and growth margin | Quiet window only when its capture/measurement contract requires one |
| Editor compile | Currently the complete managed CPU pool, despite the existing three-action UBT cap | Normally 10 GiB, covering both guards | Currently automatic; compile classification is conservative |
| Unreal imports, UAT cook/package, game and unclassified compound commands | Currently the complete managed CPU pool | Normal configured guard ceiling; an explicitly larger supported game limit must also fit its reservation | Currently automatic until a bounded profile has been validated |
| Benchmark or capture that requires an otherwise quiet machine | Its normal command envelope | Its normal guard ceiling | Explicit performance window; do not use this for routine generation |

The complete managed pool is the live CPU total minus host reserve: for example 10 minus 2 is 8 CPU units.
The full-pool entries above describe the current fallback, not evidence that every such process consumes eight
cores. Lowering only that number does not remove the separate exclusion flag. Known bounded workloads should
get a measured profile instead of keeping a broad classification indefinitely.

#### Standalone native tool builds

CPU-heavy tool and dependency builds need the same admission as game builds, even when their source is
outside Atelier. This includes CMake, Cargo, Make and Ninja commands. Run them from your own current-main
Atelier worktree after `uv sync`, leaving `ATELIER_CAPACITY_CLIENT` unset. For example:

```sh
ATELIER_AGENT=OWNER nice -n 10 uv run python -m atelier.harness.safety.guarded \
  --kind compile --report build/tool-compile.guard --timeout 1800 \
  --purpose "compile local tool" -- cmake --build /absolute/tool-build -j 3
```

Use a fresh report directory per invocation and a timeout that covers the intended work. Substitute the
actual tool command and its supported worker cap; keep the existing three-worker tuning on this Mac.
Run a potentially long or queued command in the client's background job facility and retain its logs.
The compile guard covers the owned process tree and uses the installed compile profile: currently the
full managed CPU budget, performance exclusion and the normal 10 GiB memory ceiling. A profile that
cannot accommodate the work must be investigated rather than bypassed or privately reduced.

`nice -n 10` and `-j 3` control priority and tool parallelism; they do not acquire admission or protect an
active game's performance window. Admission is cooperative: the broker cannot prevent every arbitrary
compiler launched outside the guarded entry points. All agents must use them. Do not add a guard around
`atelier build/play`, which already owns its lifecycle, or request a second legacy lock. Ordinary admission
queues this compile when necessary; it needs no pre-announcement, coordinator ACK or release message.

#### Compiler workers are not the whole build

Treat these as separate measurements and policy choices:

- **Actual tool settings:** editor compilation uses the machine's capped `Build.sh`; UAT explicitly passes
  `-ubtargs=-MaxParallelActions=3`. That limits concurrent build actions, not every thread in UAT or its
  descendants. Shader workers, mesh distance-field construction, engine task graphs, SDK helpers and staging
  have their own behavior. A three-action compiler cap does not establish a three-CPU cook/import envelope.
- **Reserved CPU:** the current full-pool fallback is a conservative scheduling charge. CPU units are soft
  budgets, not a kernel CPU limit. Five or six is a calibration candidate for a specific phase, not a default
  agents may select privately. Bounded Blender generation remains charged from its explicit worker count.
- **Exclusion:** the performance flag is separate from the vector. Lowering an eight-unit charge to five
  while leaving exclusion enabled still prevents overlap; it must not be presented as increased concurrency.
  Existing exclusive terminal-cleanup rules must also be respected when validating a shareable profile.

Guard history inspected on 2026-10-16 included Unreal import roots with brief sampled intervals around
6.6 CPU units, before counting helpers. These are attributed process observations from warm, uncontrolled
builds, not benchmark results or a hard upper bound. They rule out assuming every unchanged import fits five
or six just because its mean is much lower. Whole-machine compile percentiles likewise cannot establish a
per-job limit: they include the broker, other tools and unrelated background work.

For the next calibrated profile, retain the exact command, tool version, worker settings and source/input
identity, and measure the **whole owned process tree**. Use PID plus birth identity when taking CPU deltas;
record missing samples, helper births/exits and incomplete coverage rather than treating them as idle time.
`memory-health.jsonl` describes only its pinned process: a `bash` launcher's low counter says nothing about
its compiler children. Watched-process reports are separate and must not be double-counted. Darwin's raw
`proc_pid_rusage` CPU counters require the host's `mach_timebase_info` conversion before comparison with
wall-clock seconds.

For a focused observation of an already-running guarded job on macOS:

```sh
uv run atelier capacity observe-cpu build/sandbox/logs/unreal.compile.guard \
  --seconds 60 --interval 1 --output build/cpu-observation-1
```

Run the observer in the normal background job facility. It reads the fresh aggregate guard roster and
samples only matching PID/birth identities. It starts no workload, takes no admission reservation and never
signals a process. The new output directory retains interval samples and a summary; existing evidence refuses
overwrite. Observation ends at its deadline or the bound guard's terminal report. A changed invocation, stale
report or read failure stops observation with partial evidence preserved. The default duration is 60 seconds;
the maximum is 900, with sampling intervals from 0.25 to 5 seconds.

The reported CPU units sum paired counters from the sampled owned tree. First observations, unavailable
processes, counter resets and departed identities are explicit gaps, never zero usage or an inferred exit tail.
Processes that live entirely between polls can be missed. A sampled maximum is therefore not a hard bound,
complete lifetime accounting or permission to lower a reservation. Keep the command, tool version, worker
settings and source identity alongside the observation; watched root-process histories must not be added again.
The installed UE5.8 Mac core-count getters read hardware counts directly rather than the generic `-corelimit`
parser. That flag alone does not establish a smaller Mac job envelope. Verify the actual platform/tool controls
and helper pools before comparing a lower-worker profile.

Compare useful work per elapsed second, memory peaks, host responsiveness and output equivalence under
normal guards. Keep all existing memory ceilings and the host reserve. Validate command recognition and
matching launcher/broker enforcement, then verify overlap and cleanup with the real intended neighboring
workload before changing a phase's default or removing exclusion. Keep unknown commands conservative;
never claim that lower reservations alone made the underlying tool faster.

For a **new non-rendering Blender generator**, start with `Blender(script, threads=3)` (or an established smaller
setting). Do not omit `threads` and accidentally inherit six. Existing recipes retain their declared settings
until the worker-count comparison passes; never retune a running build. Compare 3, 4 and 6 only where relevant,
using the same source, inputs and tool version, separate output folders, normal guards, and a quiet native turn.
Compare wall time and output equivalence as well as observed CPU. Adopt more workers only for a repeatable,
useful throughput gain. Change the actual tool setting and reservation together, rather than understating the
same six-worker command. Worker-setting changes still follow ordinary fingerprinting and incremental rebuilds.

The city generators were compared on 2026-10-16 with the same frozen input files and installed Blender,
two runs per worker count in reversed order, separate output folders and normal guarded performance windows.
Median generator wall times (seconds) were:

| Generator | 3 workers | 4 workers | 6 workers |
| --- | ---: | ---: | ---: |
| City surface tiles | 10.381 | 10.158 | 10.083 |
| City-tree LODs | 1.641 | 1.628 | 1.684 |

All 83 tile and 6 tree-LOD FBXs per run had identical parsed nodes/properties with deterministic export
metadata applied uniformly; no path normalization was needed. Three workers cost about 3% on the tile case
and halved its CPU request; the tree times were similar. These two recipes explicitly use three workers.
This small historical-input comparison does not calibrate other generators, rendering, imports or compiles.

Memory protects the laptop and must be a comfortable **ceiling**, not mean usage. The reservation must cover
both actual-child and owned-tree guard limits. The normal launcher selects its 4 GiB Blender envelope only from
valid small-history eligibility; unknown, larger or unbounded work keeps the nominal ceiling. Do not manually
shrink a profile to a recent low sample, or treat old measurements as proof after a substantial input-scale change.
Host headroom and every active peer's remaining growth are added centrally; do not charge host reserve twice.
GPU allocation is already part of unified memory and also has its own subset constraint.

Reserve only while the child is admitted. Queueing, offline preparation, source checks, review gates and uploads
must not retain a heavy reservation. Lightweight work can be active while the board correctly shows zero
reservations. Heavy archive/hash/restore work still uses its normal guarded path; calling a large job metadata
does not make it lightweight. Keep checkout/engine ownership locks required by the actual command, without
adding an unrelated global lock. When a profile appears excessive, retain the exact command, input identity,
wall time, explicit workers and guard observations for a focused classification or worker-count correction.

### Disk is telemetry only

Temporary-disk estimates do not constrain the planner, shadow service, production selection, start, phase
replacement or pressure checks. No fixed temporary-space pool or free-space threshold delays admission.
The board's Disk card shows real free space and folder usage. `temp_mib` wire/configuration fields are
compatibility inputs; public admission totals report zero for disk and the admission UI omits it.

Memory, CPU, GPU, configured I/O tokens, named ownership locks, fairness and native guards remain enforced.
Build/play admission has no independent low-disk guard. The Content package installer checks that its staging
filesystem has room for two complete package copies plus 64 MiB before starting its atomic transaction.
That transaction check does not reserve disk capacity or serialize other jobs. Tools can fail with ENOSPC
if the filesystem fills; a failed tool never produces a successful build certificate.

When asked to stop or yield, let the current owned child finish normally and arrange for its caller to stop before
another heavy admission. First check `uv run atelier build --help`: if this checkout offers
`--max-heavy-commands`, use `--max-heavy-commands 1` for the handoff. Exit status `75` means the build yielded;
recheck Waiting and resume from its existing stamps when your next turn is agreed. If the option is unavailable,
choose a bounded step or another supported caller boundary before launching; do not invent a pause mechanism.
A whole-build wrapper may continue into
another build step, still capture or upload after a child exits. State explicitly which of those stages remain and
wait for the agreed caller boundary before an update, service change or reboot. If the caller cannot safely stop
there, report that limitation and keep maintenance pending. A momentarily empty native process list is not proof
that the chain is finished. Schedule approved reboot/cutover work only after all owners confirm their complete
chains have drained and retained reservations have resolved.

### Diagnosing transport refusals

A capacity transport error names its operation, endpoint/connect/send/receive phase, error type,
errno and elapsed/deadline seconds. It does not print request data, credentials or raw OS error text.
Keep that message with the guard reports. The supervised broker log records the same safe operation
and phase metadata on errors, and elapsed time for operations taking at least 250 ms. These diagnostics
do not retry an operation, extend its deadline or authorize work after a refusal. A staging/tool stall
and an RPC timeout can coincide; establish their timing and cause before retrying either.

## Sealed exclusive maintenance

This explicit interim mode permits ordinary guarded work without another reboot after a reviewed stable-volume
reseal. It does not establish closure of old preopened descriptors or authorize full concurrency. The cutover
record remains schema2 `sealed` with its original full-policy digest and a verified seal from the **current** boot.
Eligibility additionally requires the migration-recorded SHA256 of the exact private archived schema1 seal, a
verified boot change since that original seal, matching activation/policy/resources and unchanged old inode pins.
A fresh same-boot prepare or missing historical archive does not qualify; no proof is invented retrospectively.
All three unchanged lane inodes remain write-denied. Each job takes read-only **exclusive** flocks on every lane,
uses the same broker/SQLite history and normal pressure, foreign-process, exec-gate, process and aggregate guards.
It reserves all managed CPU with performance exclusion. Actual worker arguments, GPU reservations, temporary-disk
checks and nominal memory ceilings remain unchanged; automatic SMALL/4 GiB selection is disabled in this mode.

Only an authorized operator installs the reviewed mode change after draining callers and retained reservations.
Agents use the installed default client after the announcement, keep `ATELIER_AGENT`, and run the same ordinary
`nice -n 10 uv run atelier build/play` commands. A refusal has no legacy fallback. Missing, stale or incompatible
status means unknown availability. Maintenance failure or restart retains uncertainty under the existing policies;
an old nonexclusive record never gains terminal-tree release eligibility merely because the mode changed.

The maintenance broker configuration is schema3: the schema2 broker keys with `mode: "sealed-maintenance"` and
an additional `seal_policy_sha256` containing the unchanged original sealed full-policy SHA256. The service pins
the new configuration's own digest independently. Its socket, resource totals, non-memory reserve dimensions
and disk pool must exactly match the sealed policy. The unchanged original sealed reserve remains valid.
This maintenance configuration permits a deliberately reviewed **reduction** of the host memory reserve, with
the selected value between 4096 MiB and the original sealed reserve. The 4096 MiB floor applies to reductions;
it does not silently raise an unchanged originally sealed reserve. The original full-policy bytes
remain unchanged; ordinary schema2 full mode requires its exact original reserve. This maintenance calibration
policy does not lower a job's actual memory guard or reservation, change available-memory measurement, relax
pressure admission, or enable overlap. A normal 10 GiB job with a 4 GiB host reserve still requires at least
14 GiB freshly observed available memory; any lower observation refuses. Operators validate the tail under the
normal guards and an independent host-headroom abort before handing off production work. Agents do not lower
this floor or tune the buffer to fit a particular snapshot. The client has exactly `schema: 3`, `mode: "sealed-maintenance"`, `socket`, `profiles`,
`cutover` and `seal_policy_sha256`. No environment flag enables this mode or bypasses the seal. Both client and
broker fence the exact mode and activation identity; board status shows **Exclusive maintenance**, `cutover: false`.

A later full-mode activation still requires positive boot closure and an explicit drained transition. Eligible
historical seals can use the supported prior-boot promotion below without another reboot. Full activation takes all three lanes exclusively and refuses while
maintenance owns any of them. Neither an implementation merge nor maintenance operation activates that path.
Do not reboot, edit sealed files, replace lane inodes or change service configuration as an agent workaround.

## Broker and guarded-launch migration

The production broker uses its own private Unix socket and SQLite namespace. It is separate from every shadow
database and token below. `atelier capacity serve ABSOLUTE_CONFIG` runs it; `atelier capacity status ABSOLUTE_SOCKET`
reads its state. `atelier capacity supervise ABSOLUTE_CONFIG` installs macOS login/crash supervision. Installing
the service does **not** enable clients. Do not create a second broker to work around an outage or an uncertain grant.
If a controller is interrupted, normal broker refresh automatically releases its reservation once every retained
process has a verified exit and ancestry is known. Bridge and sealed-mode performance-exclusive grants also accept a
positively exited root plus its previously bound aggregate guard's final `child_exited` receipt: matching root
identity and limit, invocation time, completed cleanup, no processes and zero footprint, with no retained identity
still verifiably live. This deliberately permits historical discovery gaps under the exclusive guard policy.
The monitor now refreshes its terminal sample after draining helpers. For a preserved older pre-drain sample,
every listed tail must have its exact retained affirmative exit, must no longer be live, and must contribute
to the receipt's exact nonnegative footprint sum within its unchanged ceiling. The root cannot appear in that
tail. A partial exit set, reused identity, duplicate, inconsistent sum or live survivor still refuses
that release. Recovery does not rewrite the original monitor receipt or invent historical exits.
The witness is `guarded-tree-exit`, covering the **monitored owned tree**; it does not manufacture individual
kernel exit evidence or claim universal descendant discovery. It releases capacity only, never certifies outputs.
The same exclusive policy also releases a guard-stopped job after a `memory_limit` or `test_duration` receipt
with explicit `cleanup_processes: []`, zero `cleanup_footprint_bytes` and completed cleanup. The positively
exited root, original report binding, limit, time and no-live-retained-identity checks still apply. The offending
sample and failure remain intact. This distinct `guarded-tree-stop` witness releases resources only: it cannot
produce `finish_required`, a successful terminal response or a build certificate.
`atelier capacity reconcile ABSOLUTE_SOCKET` applies the same two policies. Without either witness, uncertainty
remains charged. Same-boot recovery rearms live registered identities and permits
the original controller's fenced session to report exit only. A verified OS boot change proves prior local jobs
ended; ordinary daemon restart does not.

If a later invocation overwrote the bound aggregate report, an authorized administrator can attest a preserved
original terminal JSON file explicitly:

```sh
uv run atelier capacity reconcile ABSOLUTE_SOCKET --request-id REQUEST_ID --preserved-terminal ABSOLUTE_ARCHIVE
```

Both options are required together and apply only to reconciliation. The broker reads the bounded owned regular
archive without following links and applies the same root-exit, identity, limit, time, exclusivity and empty-tree
checks. Its durable witness records `operator-preserved` provenance, the exact evidence SHA256, and the original
bound report-path hash and monitor identity. This is an explicit preservation attestation over the authenticated
same-user administrative socket, not cryptographic proof of the archive's origin. It never invents historical
per-process exits, replaces the current report, or certifies build outputs. Missing or invalid archives refuse.

The broker configuration is an owner-only JSON file in an owner-only directory, with exactly these fields:

```json
{
  "schema": 1,
  "mode": "legacy-bridge",
  "state_directory": "/absolute/private/capacity-state",
  "disk_pool": "/absolute/build-filesystem",
  "total": {"memory_mib": 32768, "cpu_millis": 10000, "temp_mib": 200000, "io_slots": 0, "gpu_mib": 16000},
  "reserve": {"memory_mib": 8192, "cpu_millis": 2000, "temp_mib": 20000, "io_slots": 0, "gpu_mib": 0}
}
```

These values are illustrative, not this machine's calibrated budget. The legacy disk pool and temp_mib
values remain part of sealed configuration identity, but they do not enforce disk admission. Preserve the installed
service's checkout and Python environment. Drain before changing its service configuration; supervision never
replaces an already running broker with different settings.

Upgraded `guarded.run` clients read the private `~/.cache/atelier/capacity/client.json` only when it exists. An explicit
`ATELIER_CAPACITY_CLIENT` selects another absolute file. The client file contains `schema: 1`, an absolute `socket`,
and `profiles` for `job`, `game` and `compile`. Each profile contains a complete `resources` vector and a `locks`
list. The common launcher always adds its checkout lock. A reservation smaller than the actual guard ceiling
is refused, including a session using a higher game limit. CPU reservations must be nonzero. I/O slots are
optional calibrated scheduling tokens, defaulting to zero: there is no automatic universal I/O charge per job.
Use a nonzero I/O reservation only for an identified workload whose measured contention warrants a limit.
Existing configured nonzero I/O reservations and their limits remain enforced; this does not change machine
settings. I/O tokens are not disk bandwidth or free-space enforcement. Legacy `temp_mib` estimates are ignored
by admission. Profiles do not alter worker settings or provide kernel CPU quotas;
initial budgets must conservatively cover unchanged workers. For a literal Blender job with an explicit
thread limit, the request charges exactly that many CPU units in bridge and full mode, even when the generic
profile reserves more; a three-thread job charges 3000 `cpu_millis`. The launch arguments remain unchanged.
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

Exact capacity release concerns the **retained registered process roster**, using pinned kernel exit events and the
controller's actual direct-child wait. The exclusive terminal-cleanup policy above instead witnesses the monitored
owned tree, with positive root exit essential. Neither policy turns a failed process lookup into exit proof or
claims that every possible descendant was discovered. Missing, mismatched, failed or incomplete cleanup receipts
retain uncertainty when exact exit evidence is unavailable. Output certification remains separate. The legacy bridge
and foreign-process scan remain necessary while stronger ownership coverage and client migration are validated.

Process tracking distinguishes the live guard/RPC batch bound (512 identities) from a grant's cumulative
history (8192 identities). Clients send newly observed identities in discovery order, and suppress a repeat only
after a healthy, epoch-fenced acknowledgement. Close is a single atomic bounded message: an oversized unsent tail
refuses close and retains the reservation. Missing identities and failed watch registration remain unknown.
The broker retains exact historical identities and positive exits, but stops polling positively exited processes.

To bound the active SQLite record, released histories move to private immutable SHA-256-named JSON files in the
broker's `process-history/` directory once state exceeds 2 MiB. File and directory sync precede the SQLite commit;
failed publication preserves the previous database. Active or uncertain histories are never compacted. Archives
retain the request ID, nonce generation, exact rosters, counts and release witness; public status keeps the counts.
They are audit evidence, never ownership or release authority. Reoffering or pruning a released summary does not
delete its archive. Archive cleanup requires a separate explicit evidence-retention decision. The 4 MiB active
state ceiling still refuses further mutations if held histories alone exceed it.

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
For `atelier play` and `atelier playtest`, an explicit `--memory-gib N` within the documented 10–14 GiB
range raises only that session's memory reservation to at least the selected guard ceiling. The game
profile must already cover the default 10 GiB ceiling. The default guard and profile, other resources,
exclusion, named locks and host reserve remain unchanged; the broker still checks whether the request fits.
This does not resize job/compile profiles, explicit admission sessions, bridge or sealed-maintenance clients.
Budgets, disk pool, endpoint and the exact broker configuration hash are bound into the cutover record.
Changing them requires a separately reviewed transition; neither service recovery nor clients rewrite that proof.

### Explicit full-mode memory calibration

The ordinary schema2 full configuration remains exact. A separately installed **schema4** broker configuration
can select only a calibrated host memory reserve between 4096 MiB and the original sealed reserve. It uses
`mode: "capacity"`, the same schema2 keys and `seal_policy_sha256` naming the unchanged original full policy.
Its own complete configuration digest is pinned independently by service supervision. The original sealed
policy, boot proof, lane identities, totals, endpoint, disk pool and every other reserve dimension remain exact.
No agent environment flag enables calibration, and adopting maintenance never carries its buffer into full mode.
Both calibrated full and maintenance service startup refuse a missing own-configuration digest; prepare and
install supervision rather than starting either with an unpinned manual `capacity serve` command.

This controls host headroom, not job limits: a 10 GiB job still reserves and enforces 10 GiB. With a 4 GiB host
reserve it requires at least 14 GiB of fresh available memory, plus the full remaining memory growth of every
charged peer. Unknown or failed observations still refuse. Worker counts, exclusive jobs, foreign-process checks,
CPU/GPU accounting and both memory guards are unchanged. The full default client remains schema2.

Install a reviewed calibration only at a coordinated child-free, uncharged boundary. Keep the original full
policy and seal bytes; never edit or re-seal them to fit a memory snapshot. Require measured host-pressure and
cleanup acceptance under the selected reserve before advertising useful overlap. The board shows the actual
selected headroom from live status. This source capability alone does not change the machine policy.

Full jobs retain one `render_lock` context. It opens the same three existing legacy lane inodes read-only and
takes all three shared flocks nonblocking, releasing any partial acquisition on refusal. It never writes or
truncates the legacy holder records. Resource vectors and named locks then decide compatible overlap in the
serialized broker, while actual-child and aggregate guards remain mandatory. Games, compiles and performance
windows remain exclusive initially. An explicit bounded Blender thread argument reserves at least that many
CPU units: the build default remains six, and an explicit three remains three. Unknown commands and compound
wrappers reserve the entire managed CPU budget and require exclusion; compiles also reserve at least the unchanged
three compiler workers. These are conservative scheduling units, not kernel quotas. Every reservation covers the
actual guard ceiling. Full-mode automatic, non-performance Blender jobs with explicit bounded threads retain
the existing legacy SMALL eligibility: a valid previous peak of at most 3 GiB selects a guard ceiling of
`min(nominal, 4 GiB)` and a memory reservation equal to that ceiling. Both actual-child and aggregate guards
use it. The configured profile must still cover the nominal ceiling, and an unchanged GPU reservation larger
than the selected envelope keeps the nominal guard and reservation. CPU, arguments and GPU
reservations are unchanged. Legacy temporary-disk estimates do not constrain admission. Unknown or first-run work, games, compiles, performance windows and explicit
sessions retain their nominal ceilings; the migration bridge is unchanged. A stop at 4 GiB fails the invocation
without raising the limit or retrying automatically. Its recorded peak informs the next invocation and removes
SMALL eligibility when above 3 GiB. Explicit sessions undergo the same command, checkout-lock and resource
checks as configured sessions.

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
4. `atelier capacity activate-cutover ABSOLUTE_FULL_CONFIG` verifies the new boot and all recorded stable volume UUID,
   inode, change-time and permission pins under exclusive flocks, then records `active`. Darwin device numbers
   can change across boots, so they bind current open handles to current paths rather than identify a volume
   across boots. Install the reviewed full broker
   and client settings through the existing explicit service procedure; do not run a second broker or interrupt one
   that still owns charged grants. This source change does not execute any of these machine operations.
5. Validate one guarded job and crash/recovery negatives before controlled overlap trials. Do not infer useful
   throughput or safe new coexistence combinations merely from full-mode availability.

New cutover records use seal schema 2 (separate from broker/client configuration schemas). Each lane pins the
filesystem UUID read through Darwin's `fgetattrlist` for its held descriptor and `getattrlist` for its path.
Missing, zero or unsupported UUID observations refuse; there is no device-number fallback.

A schema 1 seal has no stable volume evidence and cannot activate. During an explicitly approved maintenance
window, `atelier capacity migrate-volume-seal ABSOLUTE_FULL_CONFIG` supports only the forward transition from
schema 1 `sealed` to schema 2 `sealed`. It requires a verified boot change after the old seal, unchanged policy,
the fixed lane paths, admission exclusion and all three exclusive lane handles. It checks ownership, single links,
inode, change time, mode `0400` and actual write-open denial, allowing only the old transient device numbers to
differ. It binds the current volume UUIDs, preserves the original record bytes in the private sibling
`cutover.schema1.ACTIVATION_ID.json`, and resets `seal_boot_id` to the current boot. The archive and its directory
are synced before the new record replaces the old one. An interrupted migration can reuse only an owned,
private, single-link archive whose bytes exactly match the original; differing archives refuse.
**Ordinary schema2 activation requires another real OS reboot after migration.** Migration does not establish the old
volume's identity, activate capacity, alter lane files or unseal them. Other states and schemas refuse migration;
do not edit records, delete archives or substitute files to force the transition.

An explicit `atelier capacity promote-prior-boot ABSOLUTE_FULL_CONFIG` can instead preserve the completed earlier
reboot's descriptor-closure proof. It is eligible only for a current-boot schema2 migration backed by the unchanged
private schema1 sealed archive from an earlier boot. It holds admission and all three read-only lane mutexes
exclusively, then fetches fresh broker state itself and requires healthy maintenance mode, matching activation/boot,
zero charged resources and no recovery hold. A saved status JSON or an empty process scan cannot substitute.

Promotion preserves both seal dates and every lane inode, byte, permission and change-time pin. It durably archives
the exact schema2 bytes before publishing a distinct schema3 `active` record that binds both archive hashes and the
actual promotion boot. Verification rechecks both archived seals, the earlier boot change and current stable-volume
identity/write denial. Fresh same-boot prepares cannot qualify. The original full policy, including its host reserve,
stays exact; maintenance calibration does not silently carry into full mode. This is an explicit source-supported
transition, never permission to edit a record or relax a failed check.

Coordinate a child-free owner boundary before promotion. After publication, restart the single reviewed broker
with its original full policy and the same SQLite history, verify a fresh healthy full-mode epoch, and only then
install the full default client. Old maintenance clients refuse the active record; no automatic fallback exists.
If interrupted after ACTIVE publication, repeat the promotion command to revalidate and sync the already-published
proof under all three exclusive mutexes, then complete the same service/client transition. It never rewrites ACTIVE
as SEALED or clears retained grants. Keep native launches held through recovery controls and measured overlap proof;
neither a merged PR nor successful provenance publication alone demonstrates useful or safe concurrency.

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
and optional calibrated I/O tokens (`io_slots`, zero unless explicitly needed). On the unified-memory model,
`memory_mib` includes GPU allocations; `gpu_mib` is an additional
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
memory that already reflects their allocations. Disk availability and allocated disk estimates do not participate
in this check. Shared named locks, queue deadlines and supported worker controls remain future protocol work.

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
| Disk space | Observed free space only; no disk reservation, quota or admission lock |
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
cover the entire request: memory, CPU, GPU, configured I/O tokens and named locks are granted together or none are. Two agents cannot
both observe the same free memory and launch. The advisory board displays the result; it does not grant capacity.

The service issues an unforgeable local lease tied to the request, launcher identity and process start identity.
The existing guarded launcher registers the actual child and descendants before useful work begins. It keeps
its independent guard and resource-policy setup. CLI, build, play and custom guarded harnesses use this one
admission API. Expensive Python generation and archive/restore jobs also declare resources; cheap metadata
lookups should not require an Unreal-sized reservation.

Separate two safeguards:

1. **Accounting:** total reservations cannot exceed configured budgets, including phase headroom.
2. **Live pressure:** fresh available memory must cover the candidate, remaining peer growth and host headroom. Unmanaged applications and shared services can consume capacity outside the ledger.

Do not subtract an active job's whole reservation from an available-memory reading that already includes its
current usage. The extra risk is its remaining growth: a candidate needs its reservation plus the sum of existing
reservations' unconsumed headroom, and host safety headroom. Reconcile this conservative check with the total
reservation limit. If sampling is stale, missing or contradictory, refuse new heavy work rather than guess.

Disk observations inform cleanup and diagnosis only. They do not reserve bytes, serialize jobs or impose
a free-space admission floor. APFS clone sizes can change as files are modified; the Disk card reports actual
filesystem availability separately from folder estimates.

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
again. A queued phase holds neither memory/CPU reservations nor a checkout lock. This prevents a checkout
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

A guard can finish naturally while its controller is sending the last heartbeat. One shutdown-only
reconciliation waits at most half a second for the positive root event or aggregate publication,
keeping the reservation charged throughout. A fresh, bound,
empty aggregate terminal receipt can now return `finish_required` with `admission: false` while
the reservation remains charged. This is an instruction to finish checking the current child,
not permission to continue running or launch another one. The controller must wait for its exact
owned child within two seconds, wait naturally at most three seconds for a successful process guard
exit, pass both final guards, obtain a fenced terminal response backed
by positive release evidence, and complete normal affirmative close. An already released request
can return that terminal response directly. Neither response acknowledges process batches or
certifies build outputs. Validated new process observations are retained even on an unhealthy
heartbeat; a released request refuses unknown new identities. At most one bounded final batch is
retained for terminal retransmission across audit compaction; it cannot grant or release capacity.
A surviving child, failed guard, stale/mismatched terminal receipt, expired lease,
seal loss, broker restart or transport failure still fails; never bypass it or clear the record.

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
