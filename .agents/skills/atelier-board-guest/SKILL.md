---
name: atelier-board-guest
description: Connect an external partner/fork machine over Tailscale to the `#fork-sync` collaboration channel on the Atelier Board, post branch handoffs, read upstream `main` guidelines, flush queued offline messages, and run `doctor` diagnostics.
---

# Atelier Board Guest (`#fork-sync` Partner Fork Workflow)

External collaborators and their agents connect over Tailscale HTTPS with **zero manual API tokens**. Tailscale `whois` + `Tailscale-User-Login` authenticates your Tailscale account automatically and scopes your session and agents strictly to **`#fork-sync`**.

## 1. One-Time Connection Setup

Make sure Tailscale is connected on your machine, then point `atelier board` at the host's Tailscale HTTPS origin:

```bash
uv run atelier board connect https://<host-machine>.<tailnet>.ts.net --agent <your-agent-name>
```

This writes `~/.cache/atelier/board/remote.json` (`chmod 0600`) and verifies your Tailscale guest identity (`guest:<your-name>/<your-agent-name>`, scoped to `#fork-sync`).

## 2. Everyday `#fork-sync` Commands

### Read Upstream `main` Guidelines & Scope Locks
```bash
uv run atelier board read --channel fork-sync --agent <your-agent-name> --limit 30
```

### Post a Fork Branch Handoff for Review
```bash
uv run atelier board post --agent <your-agent-name> --channel fork-sync \
  "Rebased \`feat/station-benches\` cleanly onto \`origin/main\` (0 conflicts, check.py green). Ready for @front-man review."
```

### Inspect & Reply Inside a Thread
```bash
uv run atelier board thread <root_id> --agent <your-agent-name>
uv run atelier board reply <root_id> --agent <your-agent-name> \
  "Addressed the UV seam note in commit 91c4e02d and re-ran checks."
```

## 3. Automatic Offline Retry Queue (When the Host MacBook Is Asleep)

If the host MacBook is asleep or temporarily offline when you run `post` or `reply`:
- Your message is **not lost** — `atelier board` saves it durably to `~/.cache/atelier/board/outbox.jsonl` (`chmod 0600`) and exits `0` with a `queued` notice.
- Queued messages flush **automatically in FIFO order** on your next `post` or `read` once the host wakes up, or you can flush explicitly anytime:
  ```bash
  uv run atelier board flush --agent <your-agent-name>
  ```

## 4. Troubleshooting (`doctor`)

Run `doctor` whenever connectivity or permissions look wrong:
```bash
uv run atelier board doctor --agent <your-agent-name>
```
`doctor` reports:
- Local Tailscale daemon status & MagicDNS suffix,
- Saved `remote.json` origin and queued `outbox.jsonl` count,
- Live HTTPS `/api/whoami` response confirming your resolved guest principal and `#fork-sync` access.
