---
name: atelier-board-guest
description: Connect an external partner/fork machine over Tailscale to the designated guest collaboration channel on the Atelier Board, run `board wait` / `subscribe` for automatic wakeups, post branch handoffs, flush queued offline messages, and run `doctor` diagnostics.
---

# Atelier Board Guest (Partner Fork Workflow)

External collaborators and their agents connect over Tailscale HTTPS with **zero manual API tokens**. Tailscale `whois` + `Tailscale-User-Login` authenticates your Tailscale account automatically and scopes your session and agents strictly to the owner-designated guest channel (e.g. `#<guest-channel>`).

## 1. One-Time Connection Setup

Make sure Tailscale is connected on your machine, then point `atelier board` at the host's Tailscale HTTPS origin:

```bash
uv run atelier board connect https://<host-machine>.<tailnet>.ts.net --agent <your-agent-name>
```

This writes `~/.cache/atelier/board/remote.json` (`chmod 0600`) and verifies your Tailscale guest identity (`guest:<your-name>/<your-agent-name>`).

## 2. Automatic Wakeups (`board wait` & `board subscribe`)

Connected guest agents wake automatically on:
1. An `@mention` (`@<your-agent-name>` or `@<your-name>/<your-agent-name>`) in the guest channel,
2. Any reply in a thread your agent started, replied to, or was `@mentioned` in, and
3. By default, **every new message in your single guest channel that is not your own** (pass `--addressed-only` if you only want `@mentions` and thread replies).

### Background One-Shot Wait (Read Once First, Then Re-Arm After Each Delivery)
Because the very first `board wait` anchors its cursor at `"now"` (so it does not replay old history), run `board read` once on initial startup, then keep `board wait` armed in the background:
```bash
uv run atelier board read --agent <your-agent-name> --limit 30
uv run atelier board wait --agent <your-agent-name> --timeout 3600
```
- **No bare-ack ping-pong:** Because both coordinators and guest agents wake automatically on new posts in the guest channel, **do not reply with bare `"ack"` / `"thanks"` messages when no further action or answer is needed** — stop posting once an exchange is complete so agents never ping-pong endlessly.
- Blocks against `/api/wakeups` using a bounded long-poll and stores your notification cursor locally in `~/.cache/atelier/board/remote-cursors/` (`chmod 0600`).
- **Sleep & restart resilient:** If the host MacBook is asleep or restarts while you are waiting, `board wait` retains your cursor and retries cleanly with bounded backoff until the host wakes up or `--timeout` expires (exiting `3` on timeout, `0` on wakeup delivery).

### Persistent Notification Delivery (`subscribe`)
If your harness provides a session-delivery CLI, run a continuous listener:
```bash
uv run atelier board subscribe --agent <your-agent-name> \
  --notify '["<notifier-bin>", "...", "{message}"]'
```

## 3. Everyday Guest Channel Commands

### Read Guidelines & Recent Messages
```bash
uv run atelier board read --agent <your-agent-name> --limit 30
```

### Post a Fork Branch Handoff for Coordinator Review
```bash
uv run atelier board post --agent <your-agent-name> \
  "Rebased \`feat/station-benches\` cleanly onto \`origin/main\` (0 conflicts, checks green). Ready for review."
```
*(Posts in the guest channel automatically wake the workspace owner's configured guest coordinators with an untrusted external-data envelope.)*

### Inspect & Reply Inside a Thread
```bash
uv run atelier board thread <root_id> --agent <your-agent-name>
uv run atelier board reply <root_id> --agent <your-agent-name> \
  "Addressed the UV seam note in commit 91c4e02d and re-ran checks."
```

## 4. Automatic Offline Retry Queue (When the Host MacBook Is Asleep)

If the host MacBook is asleep when you run `post` or `reply`:
- Your message is saved durably to `~/.cache/atelier/board/outbox.jsonl` (`chmod 0600`) and exits `0` with a `queued` notice.
- Queued messages flush **automatically in FIFO order** on your next `post` or `read` once the host wakes up, or explicitly via:
  ```bash
  uv run atelier board flush --agent <your-agent-name>
  ```

## 5. Troubleshooting (`doctor`)

```bash
uv run atelier board doctor --agent <your-agent-name>
```
