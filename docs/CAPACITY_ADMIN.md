# Capacity administration

This reference is for operators maintaining machine admission. Agents running builds use
[the capacity guide](BUILD_CAPACITY.md). Installation, compatibility checks and mode changes do not
happen as part of an ordinary build. A merged PR does not activate or reconfigure a machine.

Use only the installed configuration and an explicitly authorized maintenance window. Drain complete
callers and retained reservations before service changes; never change a running job's source or guards.
The broker and guards remain the authority in every mode. There is no automatic fallback after refusal.

## Sealed exclusive maintenance

This explicit interim mode permits ordinary guarded work without another reboot after a reviewed stable-volume
reseal. It does not establish closure of old preopened descriptors or authorize full concurrency. The cutover
record remains schema2 `sealed` with its original full-policy digest and a verified seal from the **current** boot.
Eligibility additionally requires the migration-recorded SHA256 of the exact private archived schema1 seal, a
verified boot change since that original seal, matching activation/policy/resources and unchanged old inode pins.
A fresh same-boot prepare or missing historical archive does not qualify; no proof is invented retrospectively.
All three unchanged lane inodes remain write-denied. Each job takes read-only **exclusive** flocks on every lane,
uses the same broker/SQLite history and normal pressure, foreign-process, exec-gate, process and aggregate guards.
It reserves all managed CPU with performance exclusion. Worker arguments, GPU reservations and nominal
memory ceilings stay unchanged. Disk stays telemetry only; automatic SMALL/4 GiB selection is disabled.

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

## Broker and client configuration

New full-mode starts require independent guard process groups and an aggregate receipt binding the
controller. Install this requirement at a child-free caller boundary and update active launch checkouts.
Already running jobs retain their original guards; old clients refuse their next start before GO.

The production broker uses its own private Unix socket and SQLite namespace. Offline planner output never
grants admission. `atelier capacity serve ABSOLUTE_CONFIG` runs it; `atelier capacity status ABSOLUTE_SOCKET`
reads its state. `atelier capacity supervise ABSOLUTE_CONFIG` installs macOS login/crash supervision. Installing
the service does **not** enable clients. Do not create a second broker to work around an outage or an uncertain grant.
If a controller is interrupted, normal broker refresh automatically releases its reservation once every retained
process has a verified exit and ancestry is known. Bridge grants and performance-exclusive grants in full
or sealed-maintenance mode also accept a
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
The same exclusive policy also releases a guard-stopped job after a `memory_limit`, `test_duration` or `controller_exited` receipt
with explicit `cleanup_processes: []`, zero `cleanup_footprint_bytes` and completed cleanup. A controller-loss receipt must bind the original controller, which must no longer be live. The positively
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

### Interrupted compiler with lost monitors

If an external session timeout kills the controller and both monitors, no terminal cleanup report may
survive. Never manufacture one or mark the build successful. An operator may explicitly direct
`atelier capacity abandon-interrupted SOCKET --administrative-evidence ABSOLUTE_JSON` after independent
review. Ordinary agents and automatic `close`/`reconcile` do not use this action.

The private evidence JSON binds `id`, `nonce`, `epoch`, `boot_id`, `administrator`, `operator_reference`
and `services`. Use the current retained record, not a truncated public status row. The administrator
must differ from the job owner. The reference records the operator instruction; it is an audit reference,
not a cryptographic authorization boundary between processes running as the same OS user.

The broker itself requires healthy full-mode compatibility, an uncertain performance-exclusive compile,
a recorded positive root exit, no other charged job, and strictly absent controller, monitors and retained
PID/start identities. Permission or observation errors refuse. Two complete same-user kernel censuses
must exclude live build/render/compiler processes and unexplained processes born after the compile.
Current positive ancestry to a process older than the compile excludes independent work. Recent orphans
refuse except the OS Spotlight/help workers at their exact system paths, or explicitly reviewed live
launchd services. Each service exemption binds its exact PID/start, label and plist SHA256, rechecked
against launchd. Never exempt a compiler, UBT/Turnkey helper, or an unexplained Python process.

Release records `administrative-interruption`, the original report hashes, census digest, service
exceptions, administrator and operator reference, and missing historical exit count. It proves current
observed quiescence under this explicit administrative policy; it does not reconstruct historical exit
events or claim complete descendant discovery. Original reports and failure remain intact. The nonce
is one-use; a repeated action or stale binding refuses. No outputs, stamps or build completion are
certified. Rerun the interrupted step normally after release. Games, imports and nonexclusive jobs are
not eligible. Do not edit SQLite, compatibility files or profiles to recover a reservation.

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
is refused. In full mode, a game profile covering 10 GiB grows its reservation for a supported 10–14 GiB
per-session ceiling before this check. Other profiles do not grow automatically. CPU reservations must be nonzero. I/O slots are
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
as an empty pool. Offline planner advice must never appear as a live grant. Slot labels disappear only at cutover.

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
   that still owns charged grants. These machine operations require an explicit maintenance task.
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
They are **unsupported until migrated**, rather than counted as admitted jobs. Direct legacy render-lock
entry points also refuse full cutover. `atelier reuse` uses guarded admission. An absent or invalid client file
cannot restore legacy slots while
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


## Legacy slot mode

These settings apply only to machines that have not activated full capacity admission. They are not
additional lanes alongside a full broker. Do not enable or change them during ordinary work.

- The render lock has one big slot. A small slot sits beside it when `~/.cache/atelier/render-slots.json` says
  `{"slots": 2}` (`ATELIER_RENDER_SLOTS` overrides the file; no file means one slot). The small slot takes a job
  expected to peak at 3 GiB or less, never a game or a compile, when at least 10 GiB is free and the big slot's job is
  in another checkout; its memory ceiling is 4 GiB. `atelier build` sends a heavy step there when the step's last
  guard report allows it, and says which slot each step used. A compile waits for a small job to finish.
- A checkout whose code predates the slots refuses to start while a small job runs: merge main into
  every checkout before switching to two slots.
- A machine may reserve an additional Blender fitting lane with `fitting_checkout` in `render-slots.json`, keeping
  `slots` at 2. Before enabling it, update every active build/play client to the guard that understands all three
  mutexes; a fitting job refuses live holders with older guards. Only that checkout may request it, through
  `atelier.harness.safety.guarded --fitting GIB`, with one background Blender child expected to peak at most 3 GiB.
  It needs at least 10 GiB available and retains the 4 GiB actual-child memory ceiling. It never falls back to BIG,
  and compiles wait for all three lanes. Set `fitting_paused` to true for performance or filming windows and wait
  for any admitted fitting job to exit. The reservation grants capacity only; take its lock only while working.
