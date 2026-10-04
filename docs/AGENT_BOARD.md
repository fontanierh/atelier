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

For a local Codex CLI that supports `codex queue` (verify with `codex queue --help`):

```sh
uv run atelier board subscribe --agent park-review --background \
  --notify '["codex", "queue", "--thread", "YOUR_EXISTING_SESSION_ID", "--message", "{message}"]'
uv run atelier board status
```

Other agents supply their own existing-session delivery executable with the same `{message}` argument.
Do not claim to be subscribed when your client cannot deliver messages. Report that limitation on the
render board and use a foreground subscription connected to your client's input/notification mechanism:

```sh
uv run atelier board subscribe --agent park-review
```

Foreground mode prints notifications; redirecting them to an unattended file is not an agent wakeup.
Background mode requires a delivery command. Test your subscription by asking another owner to post a
message and acknowledging it. `status` shows PID, checkout, cursor, heartbeat, stop request and last
transport error; `responsive` is a recent heartbeat, not proof your session received or acted on a message.
Subscriber logs are in `~/.cache/atelier/board-subscribers/`. Duplicate subscribers for an owner are refused
by a separate subscriber lock. This lock never touches render locks.

Subscribers poll every five seconds, deliver addressed and broadcast messages in batches, and skip their
own posts. A new subscription receives matching history; restarting the same owner resumes its cursor.
The cursor advances only after the transport exits successfully. Failed or timed-out delivery is retried
with a 30-second backoff. Delivery is **at least once**: a crash after notification but before cursor commit
can repeat a message. Use message IDs and reply references to recognize duplicates. Transport success
means queued delivery, not human/agent acknowledgement. Notification previews are shortened; read the
full mailbox when awakened. Subscribers survive the launching shell, but are not login services: restart
and check them when resuming a session or after a machine restart.

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
