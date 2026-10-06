# Working rules

Atelier builds 3D games with Unreal Engine 5.8 and Blender from scripts and AI tools. [README.md](README.md) says what
is here and how to build it; [ARCHITECTURE.md](ARCHITECTURE.md) says how the parts fit.

## Layout

- `platform/`: `studio/` (the `atelier` command, Python), `engine/Plugins/` (Unreal plugins), `web/` (stream pages,
  motion helpers), `conventions/` (units, bone contract, clip roles, sound cues). Platform files never name a game.
- `games/<game>/`: `game.toml` (play profiles, fetches, stream), `build.py` (build steps), `unreal/`, `world/`,
  `assets/`, `scenarios/`, `docs/`. `yorimichi` is the full game; `sandbox` is the template for `atelier new`.

```sh
uv run atelier build <game> [step ...]   # incremental; --list shows the steps
uv run atelier play <game> [--profile P]
uv run atelier qa <game> <scenario>      # scripted checks against the running game
uv run atelier live state|py "..."|shot  # talk to the running game
uv run atelier lint                      # public-repository checks
uv run pytest                            # studio and game Python tests
```

## Repository

- The repository is **public**. Never commit credentials, tokens, personal hostnames or home-directory paths, and
  never commit third-party files whose licence forbids redistribution (Sonniss sounds, raw Mixamo downloads, licensed
  music). `atelier lint` checks the common cases; run it before pushing.
- Before every commit, run `atelier lint` and read `git diff`. The Unreal editor rewrites `Config/*.ini` when it starts
  (it can add the Android file server's generated token): keep only the changes you meant.
- Commit and push completed work at task boundaries, before starting the next task.
- Never prefix pull request titles with `[codex]` unless explicitly asked.
- Generated files go in `build/<game>/` or the game's ignored `unreal/Content/`, never next to sources. The tracked
  `unreal/Content/Data/SkateNative` bundle is source data: keep it when clearing `Content/`.
- Keep only the current revision of a source in git. Older revisions, captures and evidence go to the archive.

## Credentials and paid calls

- API keys live in the ignored repository-root `.env` (`OPENAI_API_KEY`, `AI_GATEWAY_API_KEY`, `TRIPO_API_KEY`;
  template in `.env.example`). `atelier.env.load()` reads them into the environment. Never print their values.
- Every paid call goes through `atelier.ai.ledger`: it is recorded before and after, and never retried blindly.

## Images

- Use **GPT Image 2.5 Sunburst** (`gpt-image-2.5-sunburst`) with `quality=high` for new concepts, reference sheets,
  textures and map paintings, unless the task calls for another quality. Never silently substitute another model.
- Record the model and prompt of every generated image in its provenance file.

## Animation reference videos

- Prefer **H3 Max at 480p** (`minimax/minimax-h3-max` through the Vercel AI Gateway) for cost; use Seedance only when
  its quality justifies it. Both clients are in `platform/studio/node/`.
- An H3 prompt states the appearance and camera, ordered and timed phases, support contacts, airborne impulses,
  rotation direction and count, and the recovery. Always require **constant framing** (no zoom, the character stays
  the same size) and **real-time speed** (no slow motion). Inspect the motion before accepting a take.
- Generated video is a reference for animation authored locally in Blender, never the animation itself.

## Agent messaging and subscriptions

- At the start of every agent session, choose a unique stable owner name and **verify a persistent board
  listener before starting work**. On macOS use `atelier board supervise --agent OWNER --addressed-only
  --notify '<JSON argv>' --checkout "$PWD"`, or verify the existing service with `atelier board status`.
  launchd owns delivery and restarts the listener at login and after crashes, independently of the agent's
  turns, tools, compaction and background task completion. Codex uses `board notify-codex` to steer its
  existing thread; Claude uses `board notify-claude --session-dir DIR` to reach its existing native inbox.
  The sender's permission class must be accurate; do not evade an explicit inbound hold/refusal. See
  [the guide](docs/AGENT_BOARD.md) for setup. Never use `claude -p --resume` or `claude --continue` as a notifier:
  that starts a separate writer on the same transcript rather than notifying the live session.
- Verify delivery and `atelier board status`; keep the supervised listener armed while working, waiting,
  idle and between turns. Check its heartbeat, transport error and pending messages on resume. Use
  `--addressed-only` if broadcast wakeups are too noisy, while still
  reading the render ledger at admission/step boundaries. See [the guide](docs/AGENT_BOARD.md) for adapters,
  timeout/re-arm behavior and shared-tool `--checkout` usage. Remote/ephemeral clients that cannot keep a
  background task alive must report this limitation on the render board rather than claim a subscription;
  an unattended log is not delivery. A NULL status PID means no wait/subscriber is currently armed.
  A detached subscriber or one-shot background wait is a fallback when supervision/inbox delivery is
  unavailable, not a persistent listener: report that limitation and immediately re-arm every completed wait.
- Use `atelier board post/read` for addressed requests, acknowledgements, handoffs, blocked notices and evidence.
  Preserve the Markdown render board's Holding/Waiting/Handoffs/Log entries as the scheduling ledger. Messages are
  durable across worktrees and advisory: the live lock and memory guard still decide admission.
- Write readable Markdown messages: lead with the result or request, then use short paragraphs, **bold**
  labels, bullets, inline code for commands/paths, and fenced blocks only when useful. Include evidence links,
  the next step and an ETA; keep updates concise. Address one owner with `--to OWNER`; use a broadcast only
  when everyone needs it. Do not wrap a whole prose update in a code fence or print JSON instead of a message.
- Proactively coordinate render turns with the current owner and other waiters. Acknowledge actionable requests
  within 60 seconds of receiving them using `--topic ack --reply-to ID`, before lengthy work; acknowledgement
  is receipt plus a next step/ETA, not completion. Keep each conversation in one thread: reply to a request,
  question or follow-up with `--reply-to ID`, and read the context with `atelier board thread ID`. Attach
  evidence (screenshots, films, logs) with `--attach FILE` rather than pasting long paths. To tell every agent,
  post once with `--all-agents` (not a loop of `--to`), and check a message's `audience` before treating it as yours alone. Attached files appear
  as absolute paths at the end of a message. Do not acknowledge routine telemetry or acknowledgements;
  state a concrete next safe boundary and revised ETA when late. Recheck messages and Waiting between heavy
  steps, and yield an agreed turn before per-step reacquisition or a game session. Retain first-ready time on
  refusals/requeues, distinguish blocked from ready, and never reserve a slot while idle. Prefer ready jobs under
  five minutes; after two short bypasses offer the oldest compatible ready long job the next turn.
- Subscribers send advisory lack-of-stdout-progress notices for their own validated live jobs. On an alert,
  inspect stdout, memory-health.json and supervisor telemetry, publish diagnosis/ETA, and safely end only your
  own blocked job if needed. Never signal another owner's process, remove shared mutexes, steal locks or bypass
  safety. On release, post exit/duration/evidence and send a named handoff; credit reuse and prompt releases.
- Persistent sessions keep their listener between tasks and idle turns. Only when permanently retiring the
  session, use `atelier board retire --agent OWNER`; keep messages/evidence history. `unsubscribe` stops
  unsupervised fallbacks; it does not retire a service-owned listener. Never run a one-shot wait alongside
  a supervised listener for the same owner.

## Session responsiveness and progress

- **A lengthy job must never block the whole session, prevent steering, interrupt board delivery, or leave the
  agent silent for long periods.** Run any job expected to exceed 30 seconds, or whose duration is uncertain, in
  the client's native background/job facility. In Claude Code, use `run_in_background`; in Codex, yield the
  running command and retain its session ID. Poll in bounded calls of at most 10 seconds, returning control
  between checks. Never sit in a foreground sleep loop, blocking join, or oversized tool timeout. If the client
  cannot keep the existing session responsive, do not launch a lengthy job through it.
- Persistent Claude sessions must install the `atelier board guard-claude` PreToolUse hook described
  in [the board guide](docs/AGENT_BOARD.md). It enforces 30-second foreground Bash timeouts and 10-second
  output checks; background jobs keep their timeouts and guards. Launch lengthy jobs in the background
  from the start, rather than relying on a foreground timeout to stop them.
- Keep the persistent board listener armed throughout jobs and waits. Process notifications and user steering
  promptly; if using a fallback wait, re-arm it immediately before starting or checking another job. Run the job
  independently so acknowledging a message does not require waiting for the job to finish or restarting the agent.
- Long-running scripts must flush meaningful stdout progress at least every 30 seconds, including while waiting
  for prerequisites. Report the current stage, observed completed units or frames, elapsed time, and the condition
  being awaited. For quiet external tools, monitor their logs/artifacts and emit an honest status line. Preserve
  streaming output in a log; do not hide it behind a pipeline such as `tail` that produces nothing until exit.
  Distinguish a status heartbeat from actual progress, and explicitly say when no progress has occurred.
- Before launch, tell the user what is running, its expected duration, and the next check. While a job is running
  or waiting, send a concrete user-facing progress update at least every 60 seconds, and immediately on important
  stage changes, blockers, or completion. Include observed progress, the next step, and a revised ETA when needed;
  stdout alone does not replace these updates.
- Every prerequisite wait needs an explicit deadline and an observable exit condition. When progress stops,
  inspect the current logs, runtime state, and guard telemetry at the next check; report the cause and next safe
  action. Correct the prerequisite or safely end only your own blocked job, preserving evidence. Background
  execution and heartbeats never replace stall diagnosis, render admission, or the existing lock/memory guards.

## Heavy jobs

- Yorimichi's normal play defaults to forward lighting and optimized city trees. Use `atelier play yorimichi`
  for the native 1440 window, or `--profile fullscreen` / `--profile desktop-1440` for fullscreen. Honor saved
  `renderer` and `tree_optimization` preferences; do not silently force Lumen or disable tree optimization for
  routine development. The menu warns before enabling Lumen (higher GPU and memory use, restart required), and
  before disabling tree optimization. The launcher handles the confirmed renderer restart. Keep normal memory
  guards unless the user explicitly authorizes an exception for that session. See
  [desktop performance](games/yorimichi/docs/DESKTOP_PERFORMANCE.md) for the launch and readiness contract.
- Heavy jobs (Unreal, Blender renders) run under the render lock and memory guard (`atelier.safety`). `atelier play`
  and `atelier build` do this for you. A game's guard stops it above 10 GiB; `atelier play --memory-gib N` (10 to 14)
  raises that for one session that needs it (Quality graphics at 1080p, for example). Say so in your Holding entry.
- On macOS, the shared process launcher gives builds and games application resource policies instead of an
  inherited background launchd role. It keeps normal thread QoS and at least nice 10; explicit `taskpolicy -b`
  or `-c background` policies are separate and are not cleared by it.
  Use `atelier.safety.process.spawn` (`spawn_game` for Unreal games) for a harness
  that owns its launch, together with its existing lock and actual-child memory guard. Do not add a second lock.
  When diagnosing slow work, check the actual child PID in `memory-health.json`, not just the lock owner's PID:
  `ps -o pid,ni,pri -p PID`. A child still in the background band invalidates normal-performance comparisons.
  Preserve caches and measure CPU throughput before changing memory limits or worker counts.
- The memory guard records an owned Unreal's descendants in `memory-health.helpers.json`. Once the game has exited,
  `guard.reap` (and the end of `guard.attach`) ends the recorded SDK helpers (`dotnet`, `mono`, `bash`, `sh`) that
  are still the same processes and still orphaned: a Turnkey `VerifySdk` left behind otherwise holds UnrealBuildTool's
  mutex and the next game waits in `SDKSetup`. Shared services (Zen, Trace) are never ended; never end another
  agent's helpers by name.
- The render lock has one big slot. A small slot sits beside it when `~/.cache/atelier/render-slots.json` says
  `{"slots": 2}` (`ATELIER_RENDER_SLOTS` overrides the file; no file means one slot). The small slot takes a job
  expected to peak at 3 GiB or less, never a game or a compile, when at least 10 GiB is free and the big slot's job is
  in another checkout; its memory ceiling is 4 GiB. `atelier build` sends a heavy step there when the step's last
  guard report allows it, and says which slot each step used. A compile waits for a small job to finish.
- A checkout whose code predates the slots stays safe but refuses to start while a small job runs: merge main into
  every checkout before switching to two slots.
- The live bridge (Unreal plugin, port 8830) stays loopback-only.
- Every machine has its own `~/.cache/atelier/render-board.md`. Read its Holding, Waiting and latest Log entries
  before a heavy job. Post the task, checkout, requested slot and estimated duration under Waiting; while actually
  running, record the holder and expected finish under Holding. Take the lock per job, never while idle. Prefer
  ready jobs under five minutes when several agents are waiting, and remove your entry when the job finishes.
  The live lock record is authoritative when the board is stale; never start a competing job or signal its owner.
- Check the current job's render log (`build/<game>/logs/<step>.guard/stdout.log`, or a play run's `stdout.log`) and
  `memory-health.json` before retrying or diagnosing a stall. When installed, the machine's resource log is
  `~/.cache/atelier/render-supervisor/latest.json` with history in `telemetry.jsonl`. Add the command, exit status
  and evidence paths to the board's Log when releasing a slot. Quit test games promptly and use only your own
  live bridge port; choose another loopback port with `-liveport=N` when needed.

## Reusing builds

- Concurrent agents use separate Git worktrees for code changes. Share the machine's render board, lock and
  installed engine, while each agent owns its source checkout, generated assets and live game session.
- Start with `atelier build <game>` or the specific steps needed. Keep build stamps, generated Content, compiled
  Binaries and Unreal's shared derived-data cache so unchanged steps remain up to date. Do not routinely use
  `--force`, clear caches or regenerate the world for a code-only change.
- Before building a fresh checkout, look for a completed build of the same source revision and engine version on
  the machine. Reuse verified artifacts as independent copies (APFS clones are cheap); never share mutable Content,
  Binaries or Intermediate folders between agents. Keep the same installed engine across checkouts.
  Use `uv run atelier reuse <game> --from <completed-checkout> --to <fresh-worktree>`; it verifies fingerprints,
  required outputs and engine build IDs before carrying over successful stamps. Run the incremental build afterward
  to confirm every unchanged step is up to date. It leaves absolute-path-dependent Intermediate files behind.
- Reuse only outputs whose source fingerprints and required files match. `--touch` records existing outputs as
  built: use it only after verifying those outputs, never to hide a failed or incomplete build. A source change
  must still invalidate its affected steps and compile when required.
