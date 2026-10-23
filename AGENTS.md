# Working rules

Atelier builds 3D games with Unreal Engine 5.8 and Blender from scripts and AI tools. [README.md](README.md) says what
is here and how to build it; [ARCHITECTURE.md](ARCHITECTURE.md) says how the parts fit.

## Layout

- `platform/`: `studio/` (the `atelier` command, Python), `harness/` (agent board, session delivery, capacity/admission and guards), `engine/Plugins/` (Unreal plugins), `web/` (stream pages,
  motion helpers), `conventions/` (units, bone contract, clip roles,
  sound cues). Platform files never name a game.
- `games/<game>/`: `game.toml` (play profiles, fetches, stream), `build.py` (build steps), `unreal/`, `world/`,
  `assets/`, `scenarios/`, `docs/`. `yorimichi` is the full game; `sandbox` is the template for `atelier new`.

```sh
uv run atelier build <game> [step ...]   # incremental; --list shows the steps
uv run atelier play <game> [--profile P]
uv run atelier qa <game> <scenario>      # scripted checks against the running game
uv run atelier live state|py "..."|shot  # talk to the running game
uv run atelier lint                      # public-repository checks
uv run pytest path/to/test_file.py -q     # focused local tests; full suite runs on CI
```

## Repository

- The repository is **public**. Never commit credentials, tokens, personal hostnames or home-directory paths.
  `atelier lint` checks the common cases; run it before pushing.
- Before every commit, run `atelier lint` and read `git diff`. The Unreal editor rewrites `Config/*.ini` when it starts
  (it can add the Android file server's generated token): keep only the changes you meant.
- Commit and push completed work at task boundaries, before starting the next task.
- For an authorized game release, use `uv run atelier release publish GAME PACKAGE_DIR --tag TAG --verification REPORT`
  with the existing independently verified package; add `--notes-file FILE` and `--source CHECKOUT` when needed.
  Follow [the publishing guide](docs/RELEASES.md) for clean source/evidence, bounded uploads and cancellation/resume.
  Preserve completed remote assets and rerun the same command after interruption; never clobber conflicts or publish
  an unfinished draft manually. Uploading an existing verified package does not require another cook.
- Never prefix pull request titles with `[codex]` unless explicitly asked.
- GitHub-hosted CI runs the Python suite on macOS and checks code contracts. Paid advisory review uses
  `gpt-6.1-sol`, medium reasoning, only when a writer posts a new PR comment containing exactly `r? cc`.
  **Agents must request this paid review once every code PR is ready**, after batching intermediate edits.
  Pushes/opening a PR never request it. Request again after substantive changes to reviewed code, not for
  every push or a resolved false positive. Documentation-only PRs are automatically exempt from both the
  request rule and missing-request warning. Formatting-only or trivial non-code PRs are also exempt: a writer
  must post `cc: exempt FULL_HEAD_SHA`, a newline, and a concrete explanation of why behavior is unchanged.
  That declaration applies only to that head; never use it to exempt behavior changes. See
  [the review guide](docs/CODE_CONTRACTS.md#requesting-a-paid-review) for scope and notice behavior.
  The Python suite runs in three isolated jobs (board, other studio, games). The macOS-only board job is
  deferred to final validation (owner 2026-10-23), so CI runs `quality` and the three Linux test jobs
  (studio, games 1/2, games 2/2) under the `Studio Python / Linux (macOS deferred)` check; that aggregate
  fails unless they pass. New tests are partitioned automatically; no per-file CI list needs updating.
  Before merging, run `uv run atelier lint` and `uv run atelier contracts check`, verify a successful
  `Studio Python / Linux (macOS deferred)` CI run on the exact final PR head, put the results in the review
  request, and get one other agent's approval on the
  board. Read [the contract skill](.agents/skills/code-contracts/SKILL.md) before code changes and reviews.
  Check applicable contracts and resolve findings: fix real issues, or explain false positives in the PR.
  Agents may resolve false positives without owner approval. Contract CI is advisory and must not become a
  required merge gate. Every contract owner is `fontanierh`; [the guide](docs/CODE_CONTRACTS.md) covers setup.
  Native validation still uses the machine guards.
  Merge PRs with `gh pr merge --squash --match-head-commit <tested head>`; builds publish their results to the local store as they run.
  A refactor must not change behaviour, and a fresh clone must still install and pass.
- Run focused local Python tests for the changed behavior. Do not repeatedly run the full suite locally or
  duplicate a successful CI run: hosted CI runs the complete suite on every PR head. After focused tests pass,
  repeat or broaden them only for a new change, failure or unresolved concern. Documentation-only changes need
  no local Python run. A full local run is for diagnosing a specific integration failure or unavailable CI;
  record why it was needed and reuse its result for that revision. Tests skipped on CI because they need local
  resources still need a focused local run when the change affects them.
- Python tests need no render lock, but some safety tests briefly start sleeping processes named `Blender` and
  `UnrealEditor-Fake`. These can refuse admission of another agent's next build or play job. Prefer hosted CI
  for these tests; post on the board and check the render board and live locks before running them locally.
  An already running native job is unaffected.
- Production features must include all asset preparation and optimization needed by their runtime budgets in the
  normal build and packaging dependency graph. Do not retain prototype-only opt-ins or silent fallbacks that ship
  unoptimized assets. Keep diagnostic renders and authoring experiments explicit; required production work is
  incremental and must fail on missing, stale or invalid outputs.
- Generated files go in `build/<game>/` or the game's ignored `unreal/Content/`, never next to sources.
- Commit every GLB source a game consumes under its `assets/` library. Record its local path and checksum in the
  source manifest; fresh checkouts must use the committed model without a private fetch or personal cache.
- Keep only the current revision of a source in git. Older revisions, captures and evidence go to the archive.
- When importing or porting work from a contributor fork, never copy workarounds or hacks verbatim into upstream.
  Refactor before opening a PR: never mutate committed source assets in place or add shadow backup folders next to
  `assets/` (all carved, refined or baked outputs belong in `build/<game>/` or `unreal/Content/` in the normal build
  graph); keep mesh subdivision bounded with planar/curvature filtering and LODs; keep region-specific buildings,
  bridges and paths out of shared corridor modules; derive indoor/screen placements from authored building transforms
  rather than hardcoding region coordinates in C++; share existing component gait/contact/material definitions rather
  than duplicating tables; and fold small materials into the owning region's import step instead of adding standalone
  Unreal Editor steps.

## World, region and terrain work

Before writing or reviewing any world geometry, terrain, region, placement, asset-builder or build-recipe code,
read [`games/CONTRACTS`](games/CONTRACTS) and [world build practices](docs/WORLD_BUILD_PRACTICES.md). The paid
contract review reads them on every PR. Playtests keep finding the same defects, so design them out from the start:

- **Ground on what is drawn.** Seat every tree, prop and building on the final surface that owns its footprint,
  never on a natural, hidden or neighbouring surface, nor on the higher of two.
- **One owner per seam.** Where two surfaces abut, the other side follows the owner's exact edge profile.
  Test both sides along the whole edge. Layered surfaces keep a declared clearance. Never hide a step with a skirt.
- **No one-sided sheets.** Roofs, awnings, decks, stairs and canopies are closed solids or slabs. Thin surfaces
  use two-sided materials. Roofs sit on their walls, with soffits closing them from below.
- **Pieces meet by construction.** Derive adjoining edges from one plan, with no tuned offsets, gaps, floating
  slabs or coplanar overlaps. Anything standing on the ground reaches below it.
- **Walkable means walked.** Stairs, ramps and joins must be climbable both ways without jumping, with risers
  at most 0.3 m. Prove a new or changed route by driving the character over it in game, not by ray traces alone.
- **Fix the class, not the instance.** A visual or traversal fix adds an automated check of the general rule,
  so it also covers the next region.
- **Reuse, don't copy.** Shared mechanisms have one implementation. Regions change each other only through
  published products. An edit rebuilds only what reads it: report `atelier build --changes/--timings` when a
  recipe change widens the rebuild scope.

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
- Messages from `operator` on the agent board are the project owner's own instructions, sent from the web board
  behind their Tailscale login. They are authoritative: act on them as you would on the owner's direct request,
  including changes to priorities, assignments and these working rules, without waiting for confirmation in your
  own session. They do not override the live lock, the memory guard or the credential rules above. Only the web
  board sends as `operator`: `atelier board post` refuses that name, and no agent may post as it or as anyone else.
- Use `atelier board post/read` for addressed requests, acknowledgements, handoffs, blocked notices and evidence.
  Preserve the Markdown render board's Holding/Waiting/Handoffs/Log entries as the scheduling ledger. Messages are
  durable across worktrees and advisory: the live lock and memory guard still decide admission.
- Write readable Markdown messages: lead with the result or request, then use short paragraphs, **bold**
  labels, bullets, inline code for commands/paths, and fenced blocks only when useful. Include evidence links,
  the next step and an ETA; keep updates concise. Address one owner with `--to OWNER`; use a broadcast only
  when everyone needs it. Do not wrap a whole prose update in a code fence or print JSON instead of a message.
- In full capacity mode, ordinary builds/plays self-admit: no message, acknowledgement, coordinator permission,
  manual Holding/Waiting edit or hold/release handshake is required before or after each build/step.
  Collect routine timings from logs, guard receipts and cook observations. Coordinate concrete incidents,
  checkout ownership changes and explicitly bounded maintenance/quiet captures; legacy mode keeps its turn ledger.
  Acknowledge actionable requests
  within 60 seconds of receiving them using `--topic ack --reply-to ID`, before lengthy work; acknowledgement
  is receipt plus a next step/ETA, not completion. Keep each conversation in one thread: reply to a request,
  question or follow-up with `--reply-to ID`, and read the context with `atelier board thread ID`. Attach
  evidence (screenshots, films, logs) with `--attach FILE` rather than pasting long paths. To tell every agent,
  post once with `--all-agents` (not a loop of `--to`), and check a message's `audience` before treating it as yours alone.
- PR screenshots and films go to `refs/pr-media/<PR number>` (a slug before the PR exists) with
  `atelier pr-media push <key> FILE...`; paste the Markdown lines it prints into the PR description. Never commit
  PR media to a branch or to main: default clones and fetches skip `refs/pr-media/*` (a `git clone --mirror` takes
  them). Keep these refs: deleting one eventually breaks its links. The repository is public and these refs are
  permanent, and lint never sees pixels or metadata: push only game or render captures and films, never desktop,
  terminal, browser or board screenshots (they can show home paths, hostnames, emails, notifications or tokens).
  Look at every file before pushing.
- When you cannot go on without the operator's guidance, help or confirmation, open **one operator task**:
  `atelier board operator-task open --agent NAME "..."` (the ask first, at most 500 characters). The operator
  answers or dismisses it from the board's Tasks page, and the reply arrives in its thread. You hold one at a time;
  when what you need changes, change its ask with `atelier board operator-task edit --agent NAME ID "..."`. Use it
  sparingly, for real blocks only, and **dismiss it yourself as soon as it no longer applies** with
  `atelier board operator-task dismiss --agent NAME ID`. See [the board guide](docs/AGENT_BOARD.md#operator-tasks).
- Keep your board status line current; it is how the operator sees the team. Once registered, set it with
  `atelier board task --agent NAME "..."` (one line, at most 160 characters). Update it **every time you get a new
  task**, before starting the work, and again when you finish or become blocked. With no current task, set it to
  exactly `idle`, nothing more. The board shows it beside your name, marks `idle` agents as free for new work,
  and treats a session idle for 10 minutes as free whatever the line says (it sends you one reminder then).
- Write board messages that are clear, concise and well formatted, in simple words. The hard limit is 8000
  characters including the attachment trailer. Say what the reader needs, lead with the point or the ask,
  and use short paragraphs or lists when they help. Put bulky
  material (logs, tables, long reasoning) in an attachment, a linked file or a thread reply. `--notify-operator`
  also pushes a phone notification to the operator: use it sparingly, only when the operator asked to be told, or
  for something urgent that needs them now (a decision blocking you, a broken release, a safety issue). Never for
  routine progress or acknowledgements; at most 3 per agent per hour. Attached files appear
  as absolute paths at the end of a message. Do not acknowledge routine telemetry or acknowledgements;
  state a concrete next safe boundary and revised ETA when late. Read incident and maintenance messages between
  heavy steps, and honor an explicitly agreed handoff. Normal full-mode builds need no per-step handoff.
  The broker preserves queue age and schedules compatible work. Never reserve resources while idle.
- Subscribers send advisory lack-of-stdout-progress notices for their own validated live jobs. On an alert,
  inspect stdout, memory-health.json and supervisor telemetry, publish diagnosis/ETA, and safely end only your
  own blocked job if needed. Never signal another owner's process, remove shared mutexes, steal locks or bypass
  safety. For an explicitly coordinated turn, post exit/duration/evidence and its handoff; routine full-mode
  jobs release through the broker without a message.
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
  promptly; if using a fallback wait, re-arm it immediately before starting or checking another job. Set an explicit background job deadline covering queue time, the entire command and cleanup; never inherit
  a short executor default. Use Atelier's own execution deadline; do not put a shorter session/shell deadline around an entire queued
  build that kills its guards before cleanup. Cancel with Ctrl-C or SIGTERM and allow cleanup to finish. Run the job
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
  before disabling tree optimization. The launcher handles the confirmed renderer restart. Larger guarded sessions
  are standing-authorized: choose a supported needed ceiling with its full broker reservation, normal admission,
  memory guards and deadlines. Do not ask for another per-session memory grant. See
  [desktop performance](games/yorimichi/docs/DESKTOP_PERFORMANCE.md) for the launch and readiness contract.
- Heavy jobs (Unreal, Blender renders) run under the render lock and memory guard (`atelier.harness.safety`). `atelier play`
  and `atelier build` do this for you. A game's guard stops it above 10 GiB; `atelier play --memory-gib N` (10 to 24)
  raises that for one session that needs it (Quality graphics at 1080p, for example). In full capacity mode,
  admission automatically reserves at least that selected ceiling for this session; the default stays 10 GiB.
  Do not edit machine profiles to use this flag. Retain the command and reason in its evidence.
- Use the [capacity workflow](docs/BUILD_CAPACITY.md#agent-workflow) and its
  [job resource table](docs/BUILD_CAPACITY.md#choosing-resources-for-a-job). In confirmed full mode,
  run `ATELIER_AGENT=OWNER nice -n 10 uv run atelier build/play` with the installed default client and
  `ATELIER_CAPACITY_CLIENT` unset. Commands queue and release themselves; no per-build board message,
  manual Holding/Waiting edit or coordinator permission is needed. Honor specific release priorities,
  quiet captures and maintenance windows. Keep the persistent listener active.
- Start new non-rendering Blender generators with explicit `threads=3`, or an established smaller setting.
  Increase only after same-input timing and output checks show a useful gain. The launcher charges the
  actual worker count. Memory reservations cover both guard ceilings: normally 10 GiB, or an automatic
  4 GiB Blender envelope backed by valid prior peak evidence. Never understate resources to fit a free budget.
  Compile, UAT, imports, games and unclassified commands currently reserve the managed CPU pool with
  performance exclusion. Three compiler workers do not cap all engine threads; lowering a reservation alone
  does not throttle a tool or remove exclusion. Use the capacity guide for measurements and profile changes.
- Merge and run `uv sync` only after the checkout's native child and its enclosing caller have stopped at a
  boundary where neither can start another child. Preserve generated files and caches. Agents must not edit
  client profiles or broker settings, restart a live broker, clear uncertain reservations, or bypass refusal.
  Protected compatibility files must never be edited, removed, replaced or chmodded. Disk is telemetry only;
  it never reserves or locks capacity.
- Standalone CPU-heavy native builds also need admission, including tools and dependencies outside this
  repository. Run CMake, Cargo, Make or Ninja through the [standalone compile workflow](docs/BUILD_CAPACITY.md#standalone-native-tool-builds)
  with `--kind compile`, from your own current-main checkout after `uv sync`. Keep the supported worker cap
  (normally three); `nice` or `-j 3` alone does not provide admission, memory guards or game isolation.
  Do not wrap `atelier build/play` in another guard. Normal admission decides when the standalone compile
  can run; no pre-build board message, coordinator acknowledgement or manual handoff is required.
- On macOS, the shared process launcher gives builds and games application resource policies instead of an
  inherited background launchd role. It keeps normal thread QoS and at least nice 10; explicit `taskpolicy -b`
  or `-c background` policies are separate and are not cleared by it.
  Use `atelier.harness.safety.process.spawn` (`spawn_game` for Unreal games) for a harness
  that owns its launch, together with its existing lock and actual-child memory guard. Do not add a second lock.
  When diagnosing slow work, check the actual child PID in `memory-health.json`, not just the lock owner's PID:
  `ps -o pid,ni,pri -p PID`. A child still in the background band invalidates normal-performance comparisons.
  Preserve caches and measure CPU throughput before changing memory limits or worker counts.
- The memory guard records an owned Unreal's descendants in `memory-health.helpers.json`. Once the game has exited,
  `guard.reap` (and the end of `guard.attach`) ends the recorded SDK helpers (`dotnet`, `mono`, `bash`, `sh`) that
  are still the same processes and still orphaned: a Turnkey `VerifySdk` left behind otherwise holds UnrealBuildTool's
  mutex and the next game waits in `SDKSetup`. Shared services (Zen, Trace) are never ended; never end another
  agent's helpers by name.
- Machines still using legacy slots follow the [operator reference](docs/CAPACITY_ADMIN.md#legacy-slot-mode).
  Do not add legacy slots or fitting lanes alongside full capacity admission, or change machine modes during a task.
- The live bridge (Unreal plugin, port 8830) stays loopback-only.
- Every machine has its own `~/.cache/atelier/render-board.md`. Read current incident/maintenance instructions
  before heavy work. In full mode, normal build/play submits resources and ownership directly: no manual
  Waiting/Holding entry, per-step post or coordinator handshake. For legacy mode or an explicitly coordinated
  maintenance/capture turn, record the task, checkout, resources/exclusion, duration and first-ready time under
  Waiting, then the active holder under Holding; remove the entry when finished. Never reserve while idle.
  Live broker grants and guard ownership (or legacy lock records) are authoritative when the board is stale;
  never bypass admission or signal another owner.
- Check the current job's render log (`build/<game>/logs/<step>.guard/stdout.log`, or a play run's `stdout.log`) and
  `memory-health.json` before retrying or diagnosing a stall. When installed, the machine's resource log is
  `~/.cache/atelier/render-supervisor/latest.json` with history in `telemetry.jsonl`. Add the command, exit status
  and evidence paths to the board's Log for an incident or explicitly coordinated turn. Quit test games promptly
  and use only your own live bridge port. `atelier live` targets port 8830. A game launched with `-liveport=N` needs a client explicitly
  configured for that loopback port; the CLI currently has no port option.

## Reusing builds

- Concurrent agents use separate Git worktrees for code changes. Share the machine's render board, lock and
  installed engine, while each agent owns its source checkout, generated assets and live game session.
- Start with `atelier build <game>` or the specific steps needed. Keep build stamps, generated Content, compiled
  Binaries and Unreal's shared derived-data cache so unchanged steps remain up to date. Do not routinely use
  `--force`, clear caches or regenerate the world for a code-only change.
- New portable generators should declare named products and complete inputs; `cache=True` enables automatic
  verified local reuse across revisions. Use `atelier build <game> --plan --explain` to inspect rebuild reasons and
  `--verify` when byte corruption is suspected. See [build recipes](docs/BUILD_RECIPES.md). Inspect unique cache
  bytes with `atelier cache status`; preview pruning with `atelier cache gc --dry-run`. Do not enable portable
  caching for Unreal packages or use reference edges to hide reads of bounds, materials or collision.
- Use the normal `atelier build` command in fresh and warm worktrees. It checks input/tool-keyed task results
  locally and in the configured private checkpoint repository before native work, independent of Git HEAD.
  Follow [build checkpoints](docs/BUILD_CHECKPOINTS.md). Keep the same installed engine and independent outputs;
  never share mutable Content, Binaries or Intermediate.
- Configure private storage with `atelier cache configure --repository OWNER/REPOSITORY`; its address belongs
  only in machine-local configuration, never tracked source. Release publication retains an existing verified
  build before publishing the playtest; it does not request another cook. Preserve producers and all caches
  until checkpoint verification and receiving restore are accepted. Keep referenced remote releases/packs.
- Merge PRs with `gh pr merge --squash --match-head-commit <tested head>`; builds publish their results to the local store as they run.
- Unknown or expensive native misses stop before admission. Inspect `--plan --explain`, fix cache access or
  declarations, and use a specific `--rebuild-reason` only for unavoidable work: `STEP=REASON` (repeatable) for a
  task the stop names; a bare reason covers only the requested tasks and those with no result at launch. `--touch` is refused. `--force`
  requires one exact task plus a reason, and must preserve current prerequisites. Never clear caches or stamps.
- New reusable tasks must declare complete disjoint products/output roots and complete inputs. Representative
  legacy outputs cannot become a cache entry by inference; migrate ownership before claiming individual reuse.
  Missing/corrupt outputs must invalidate their stamps. Native compile receipts must include required plugin
  products. Keep guard/journal recovery intact; never manufacture success stamps.
