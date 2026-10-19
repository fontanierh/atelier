# Capacity admission

The broker decides when heavy jobs may run. Memory and ownership guards supervise the actual processes
and keep a reservation until cleanup is verified. Board messages describe work; they do not grant capacity.
Disk space is reported for monitoring and never reserves or locks capacity.

## Agent workflow

On a machine configured for full capacity admission, use its installed default client and your board name:

```sh
ATELIER_AGENT=OWNER nice -n 10 uv run atelier build GAME
ATELIER_AGENT=OWNER nice -n 10 uv run atelier play GAME
```

Leave `ATELIER_CAPACITY_CLIENT` unset. Normal commands request resources, wait their turn and release after
verified cleanup. Do not send a pre-build message, ask a coordinator for permission, edit Holding/Waiting,
or add another lock or guard. Keep your persistent board listener active for incidents and owner instructions.
A specific release priority, quiet capture or maintenance window still applies when announced.

Use a separate worktree. Before updating it, finish its native child and stop the caller at a boundary where
it cannot start another child. Then merge and run `uv sync`. Preserve Content, Binaries, stamps, Zen and DDC.
Use [verified reuse](INCREMENTAL_BUILDS.md#reuse-a-completed-build) for a fresh worktree; never link mutable
build directories or manufacture stamps.

Check the installed client's socket with `atelier capacity status ABSOLUTE_SOCKET`. Fresh `(capacity, true)`
means full admission. Missing or stale status means unknown availability. Legacy bridge and sealed maintenance
are operator-managed compatibility modes, described in [capacity administration](CAPACITY_ADMIN.md).
Agents must not select another client, edit profiles, lower reserves, unseal files or restart a live broker
to bypass a refusal. Protected compatibility files must never be removed, replaced or chmodded.

### Waiting and cancellation

A positively queued request waits for up to 30 minutes. It holds no resources or child, preserves its ready
age and prints progress. Run long or queued commands in the client's background job facility. Cancellation
closes the uncharged request. Policy, ownership, protocol and fencing errors stop the command.

Use Atelier's execution deadline for bounded work. Do not wrap a queued multi-step build in a shorter
session or shell deadline that kills its entire process tree. Cancel with Ctrl-C or SIGTERM and allow
cleanup to finish. Guards run in separate sessions; if the controller is killed, the aggregate guard
stops its pinned workload, writes an interruption/cleanup receipt and exits. The interrupted step
fails and must rerun; it never receives a successful build stamp. Full admission refuses older clients
that lack independent guard sessions and controller-loss monitoring; update the launching checkout. Losing the independent guard itself
can still require the explicit administrative recovery described in the operator guide.

A selected request that loses its turn before execution may requeue at most twice within that same deadline.
The launcher first proves its gate child exited, the guarded tree is empty and the request is uncharged.
It never replays a start or treats missing timing data as proof that a child did not execute.

`offer`, `owned`, `check` and `close` may replay one identical request after a transient transport failure.
Their per-call deadlines stay unchanged. Start, gate and replacement operations never replay. A second
transport failure or incomplete cleanup fails the command rather than starting work through another path.

### Refusal and cleanup

Keep the command, source revision, error and guard directory. Read `stdout.log`, `memory-health.json`,
`memory-health-tree.json` and execution timings before retrying. Low memory usage, a missing PID or an
expired heartbeat does not prove release. A retained reservation is **locked** until the broker accepts
its process-exit and cleanup evidence. The board shows **Open** only with fresh healthy full-mode status;
missing or stale data is unavailable, not free capacity.

Do not delete state or mutexes, signal another owner's process, or retry through a raw launcher. Report an
incident when normal cleanup cannot resolve it. An authorized operator can reconcile preserved terminal
reports under the same ownership checks; see [the administration reference](CAPACITY_ADMIN.md).

## Choosing resources for a job

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

### Standalone native tool builds

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

## Worker settings and reservations

Tool workers, reserved CPU and performance exclusion are separate. UAT's three-action compiler cap does
not cap shader compilation, mesh distance fields, imports or the engine task graph. Reserving fewer CPU
units does not throttle those processes; leaving exclusion enabled still prevents overlap.

For a new non-rendering Blender generator, specify `threads=3`, or an established smaller value. Increase
only after same-input timing and output checks show a useful gain. Existing recipes keep their settings
until measured. The launcher charges the explicit worker count; never run six workers while declaring three.
The measured city tile/tree generators use three workers. This result does not calibrate every Blender job.

Keep memory ceilings above measured peaks with room for growth. Reservations cover both process and tree
guards; do not add the machine's host reserve again. A game normally uses 10 GiB.
`atelier play GAME --memory-gib 12` requests and reserves a larger ceiling for that session; the supported range is 10–14 GiB.
Do not edit machine profiles to use it. Quit test games promptly.

An explicit package cook can select its own invocation ceiling without changing source or compiled outputs:
`atelier build GAME unreal.package --cook-memory-gib 12` (also `unreal.cook`), within 10–24 GiB.
Only the UAT package command receives that ceiling; prerequisite compiles/imports retain their normal limits.
The selected cook uses full-capacity compile admission and reserves at least its entire child/tree ceiling,
with the existing CPU exclusion and fresh host-headroom check. Other compile requests do not resize.
The default stays 10 GiB. This execution policy does not change UAT argv, command identity or build keys,
and does not force an already-current cook. It cannot combine with `--touch` or certification-only recovery.
A read-only plan accepts the option and records the selected ceiling without acquiring capacity.

Disk is telemetry only. Jobs can still fail when disk fills; admission does not protect against that.
The Content installer checks staging space before installation, but ordinary package/cook jobs have no
additional broker disk limit. Optional I/O tokens describe contention, not free space.

## Inspect retained resource history

`atelier capacity history GUARD_DIRECTORY --json` reads retained process memory reports without launching
work. Whole-tree peaks differ from the sum of individual process peaks. Missing samples remain unknown.

For a focused CPU observation of an existing guarded job on macOS:

```sh
uv run atelier capacity observe-cpu GUARD_DIRECTORY --seconds 60 --interval 1 --output NEW_DIRECTORY
```

Run the observer in the background. It samples the fresh owned PID/birth roster, starts no workload and
takes no reservation. Gaps and short-lived processes can be missed, so its sampled maximum is not a hard
bound or permission to reduce a profile. Keep the command, tool version, worker settings and source identity.
Whole-machine percentages and a shell wrapper's CPU counter cannot establish a job's complete CPU need.

The board's active waiting count includes current queued requests only. Historical retry-required records
hold no capacity. GPU memory is part of unified memory; its separate budget is not extra physical RAM.
