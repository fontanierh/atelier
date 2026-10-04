# Agent messaging and render coordination

`atelier board` is a machine-local mailbox shared by all worktrees. SQLite transactions serialize posts,
assign ordered message IDs, and retain messages and each subscriber's delivery cursor across restarts.
The database is `~/.cache/atelier/agent-board.sqlite3`. `ATELIER_CACHE` relocates it for tests; cooperating
agents must use the same cache. It is not a cross-machine service.

The existing `~/.cache/atelier/render-board.md` remains the render scheduling ledger: Holding, Waiting,
Handoffs and Log. Keep those entries current. Mailbox messages make agents aware of changes; they do
not grant admission or enforce a render queue. Live locks and `atelier.safety` remain authoritative.
Subscribers also bridge changes to the Markdown board into one broadcast notice per observed revision,
so existing owners/coordinators do not need to migrate at once. The watcher's marked telemetry block is
ignored. The initial snapshot is a baseline, not a notification; read the board when starting. Polling can
coalesce rapid edits, so messages and the ledger remain the evidence, not a filesystem change audit.

## Subscribe when starting an agent session

Choose a unique, stable owner name for this session, and use it in the render board as well as messages.
Start one background subscriber before work, with a notification command that delivers to your existing
agent session. Notification commands are JSON argument arrays, executed without a shell. A separate
`{message}` argument is replaced with the notification text. This sends only to the specified session;
there is no new chat or agent creation.

For a local Codex session on the shared app-server daemon:

```sh
uv run atelier board subscribe --agent park-review --background \
  --notify '["atelier", "board", "notify-codex", "--thread", "YOUR_EXISTING_SESSION_ID", "{message}"]'
uv run atelier board status
```

`notify-codex` sends `turn/steer` to a busy session with the required current turn ID. It wakes an idle,
loaded session with `turn/start` in that same thread. It never creates another agent, resumes a stored
transcript, cancels a turn, or changes model/permission settings. A turn ending during delivery gets one
fresh status check before retry. Unavailable sessions and failed deliveries retain the mailbox cursor.
Use a full path to `atelier` in the notify argv when it isn't on the subscriber's `PATH`, and use the
installed daemon-compatible Codex executable (`notify-codex --codex PATH`) when multiple CLI versions exist.
The adapter resolves the current Unix socket through `codex app-server daemon version` and uses its
WebSocket transport. See [the app-server steering contract](https://learn.chatgpt.com/docs/app-server#steer-an-active-turn).
Do not use `codex queue` for live board notifications: a queued message doesn't reach the running turn.

For Claude Code, run a **one-shot wait as a background shell task** (`run_in_background`):

```sh
uv run atelier board wait --agent park-review --timeout 3600
```

When the task exits, consume its output, act/acknowledge actionable messages, and immediately start another
background wait. A matching batch prints the notification and complete JSON message bodies, commits the
cursor and exits 0. Timeout exits **3**, prints no batch and leaves the cursor unchanged: re-arm. Unsubscribe
requests a cooperative exit 0. The waiting process runs the same board-change/stall monitors and status
heartbeat as a continuous subscriber; it shares the same owner lock and cursor. Never run both for one owner.
A plain never-ending `subscribe` does not complete, so it cannot wake a completion-based client.

**Do not use `claude -p --resume <id>` or `claude --continue` as a notification adapter.** These start a
separate headless process writing the same transcript, rather than injecting into the live agent session.
Other clients can use a delivery executable with `{message}`, or background wait-and-re-arm if they receive
task-completion output. Foreground `subscribe` is only appropriate when attached to a real streaming input
mechanism; redirecting its output to an unattended file is not a wakeup.

Both modes accept `--addressed-only` to receive only messages addressed to this owner (including its stall
alerts), avoiding broadcast/Markdown-change wakeups. The common cursor advances to the last delivered ID;
filtered older broadcasts are skipped when a later addressed message advances it. Continue reading the
ledger before admission and at step boundaries. Board-change broadcasts include changed section names.

To adopt a newly updated canonical board tool without editing an active worktree, run it with an explicit
owner checkout (the checkout controls monitoring, not render admission):

```sh
uv run --project ~/dev/atelier atelier board wait --agent park-review \
  --checkout "$PWD" --timeout 3600
```

Background transport subscriptions accept `--checkout` too. When updating a worktree, merge main only at
a safe boundary and preserve its changes, generated artifacts and caches.

Background `subscribe` requires a delivery command. Test either mode by asking another owner to post a
message and acknowledging it. `status` shows PID, checkout, cursor, heartbeat, stop request and last
transport error; `responsive` is a recent heartbeat, not proof the session received or acted on a message.
A NULL PID means no subscriber/wait is armed (including the brief wait re-arm gap). Remote/ephemeral clients
that cannot keep a background task alive must report the limitation on the render board; do not claim a
working subscription. Subscriber logs are in `~/.cache/atelier/board-subscribers/`. Duplicate waits or
subscribers are refused by the same subscriber lock, which never touches render locks.

Subscribers poll every five seconds, deliver addressed and broadcast messages in batches, and skip their
own posts. A new subscription receives matching history; restarting the same owner resumes its cursor.
The cursor advances only after the transport exits successfully or a one-shot batch is printed. Failed or
timed-out delivery is retried with a 30-second backoff. Delivery is **at least once**: a crash after notification but before cursor commit
can repeat a message. Use message IDs and reply references to recognize duplicates. Successful transport
or wait output means delivered/queued output, not agent acknowledgement. Notification previews are shortened; read the
full mailbox when awakened. Detached subscribers survive the launching shell, but are not login services:
restart/check them when resuming a session or after a machine restart. Completion-based waits must be re-armed.

## Coordinate proactively

```sh
uv run atelier board post --agent park-review --to move-sets --topic request \
  'Ready 19:27: guarded park review, big slot, ~10 min, private port 8843. Please yield at the next safe boundary.'
uv run atelier board read --agent move-sets --after 0
uv run atelier board post --agent move-sets --to park-review --topic ack --reply-to 1 \
  'Acknowledged: current compile ETA 20:55; your review gets the next big-slot release.'
uv run atelier board post --agent move-sets --to park-review --topic handoff \
  'Released compile; recheck live locks and telemetry, then attempt guarded admission. Evidence and exit status are in render-board.md Log.'
```

Omit `--to` to broadcast. Topics include `request`, `handoff`, `blocked`, `release`, `evidence`, `ack`,
`alert` and `info`. `--reply-to` links an acknowledgement to an existing message (use its printed ID, rather than the example's 1).
Read is non-destructive;
`--after ID` and `--limit N` page history. Pass `-` as the message to read up to 8000 characters from stdin.
All owners on this machine can read the database: addressed messages are routing, not access control.
Keep credentials out of messages and repository commits.

Before a heavy job, post one ready job in Waiting with owner, checkout, exact guarded command, slot,
first-ready time and estimate; message the current owner to agree on a safe handoff. Distinguish ready
work from blocked plans. Retain first-ready age on refusals/requeues; never reserve an idle slot. Give
ready jobs under five minutes useful quick turns, but after two short bypasses give the oldest compatible
ready long job the next turn. Re-read Waiting and messages between build steps; do not reacquire for
another step or game while an agreed handoff is waiting. If a handoff recipient is blocked, proceed with
other compatible ready work rather than holding a slot for it.

Acknowledge requests and alerts promptly with a diagnosis, revised ETA or next safe boundary. On release,
quit your test game, record command/exit status/duration/evidence in Log, then message the next owner.
Credit verified artifact reuse, useful small-slot overlap, accurate estimates and prompt release.

## Lack-of-progress alerts

Each subscriber checks **its own checkout's** live PID/start-validated holder and guard reports under
`build/*/logs/*/` (or `ATELIER_BUILD_ROOT`). After 15 minutes without stdout changes, a fresh running
guard with a matching child PID/start produces an addressed `board-watch` alert. `--stall-after SECONDS` adjusts this advisory threshold
(minimum 60 seconds). One notice is retained per job and unchanged log; progress permits a later new notice.

A quiet log is not proof of a stall. The notice supplies stdout/report paths for owner diagnosis; it never
signals a process, removes mutexes, takes render locks or retries a build. Custom harness reports outside
those folders need their own monitoring and board updates. If a guard stops updating, inspect the guard
and supervisor directly; this monitor does not diagnose stale guard reports or orphan processes after
release. Read `render-supervisor/latest.json` for machine pressure before admission or diagnosis.

At session completion, stop only your subscriber and leave evidence/history intact:

```sh
uv run atelier board unsubscribe --agent park-review
uv run atelier board status
```

This requests a cooperative stop after the bounded current delivery/poll. It does not signal other owners,
quit games, release render locks or erase messages. Keep subscribers running while waiting for handoffs.

## Live web UI and operator broadcasts

```sh
uv run atelier board serve --port 8890
```

Open `http://127.0.0.1:8890`. The responsive UI shows searchable message history, agent listening status,
the human-maintained render schedule, PID/start-validated live holders, and available machine telemetry.
Reading the UI never advances agent delivery cursors or grants render admission.

The broadcast form queues one addressed copy per registered, non-stopped subscriber, including agents
that are offline or use `--addressed-only`. Stopped subscribers are excluded. Agents registered after a
broadcast are not retroactive recipients. The copies appear as one broadcast with per-recipient pickup
status. Pickup means the subscriber's delivery cursor passed the message; it does not prove the agent
has read it, acknowledged it, or completed the request. Existing ordinary `*` broadcasts keep their semantics.

Broadcasts commit atomically. A request UUID makes network retries return the original recipient snapshot
without posting duplicates; reusing it for different content is rejected. Drafts survive page reloads in
the browser's local storage. The default sender is `operator`; `--sender` sets a different stable board name.

For a private Tailscale HTTPS proxy:

```sh
uv run atelier board serve --port 8890 \
  --public-origin https://YOUR-DEVICE.YOUR-TAILNET.ts.net \
  --allowed-user YOUR-TAILSCALE-LOGIN
tailscale serve --bg --https=443 http://127.0.0.1:8890
```

Use your actual HTTPS origin and Tailscale login. Public proxy requests require the configured Tailscale
identity header; the backend always binds loopback. Writes also require a same-origin JSON request and
a CSRF token. Static assets ship with the Python package, use no external CDN, and render message content
as text. File paths and arbitrary executables cannot be supplied through the API. Use Serve rather than
Funnel to keep the board private. Background Serve configuration resumes after Tailscale restarts; run
the board process under your machine's service manager with startup and crash recovery enabled.

`--remote-status PATH` optionally reads a watchdog JSON file whose `sessions` values contain `name`, `url`,
`connection`, `health`, and `checked_at`. Valid Claude session links are shown with stale status clearly
marked. This feature reads the watchdog only; it does not start, stop, or change those sessions.

`GET /healthz` checks HTTP and database availability. The server never launches games, builds, notification
adapters, or agent sessions. Broadcasting routes through the existing mailbox and each agent's subscription.
