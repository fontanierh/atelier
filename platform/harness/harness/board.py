"""The `atelier board` package entry point, subscriber wakeup loop, and launchd helpers."""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from atelier.harness.board_store import agent_name, database, root
from atelier.harness.slack_board import (
    GUEST_DATA_BANNER,
    SlackBoardStore,
    default_db_path,
)


def notify_command(spec: str) -> list[str]:
    try:
        argv = json.loads(spec)
    except ValueError as exc:
        raise ValueError("--notify must be a JSON string array containing '{message}'") from exc
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
        raise ValueError("--notify must be a non-empty JSON string array")
    if argv.count("{message}") != 1:
        raise ValueError("--notify must have exactly one '{message}' placeholder argument")
    base = Path(argv[0]).name
    if base in {"claude", "claude-code"} and any(f in argv for f in ("-p", "--print", "--resume", "--continue")):
        raise ValueError("never invoke 'claude --resume/--continue' from a notifier; use 'atelier board notify-claude'")
    return argv


def format_wakeup_batch(agent: str, items: list[dict[str, Any]]) -> str:
    lines: list[str] = [f"[atelier-board wakeup for @{agent} — {len(items)} new notification(s)]"]
    for it in items:
        kind = it["kind"]
        ch = it["channel_name"] if it["channel_kind"] == "dm" else f"#{it['channel_id']}"
        loc = f"{ch} (thread #{it['root_id']}, msg #{it['message_id']})"
        prefix = f"- [{kind.upper()}] from @{it['author_id']} in {loc}:"
        lines.append(prefix)
        if it.get("untrusted_envelope") or it.get("author_role") == "guest":
            lines.append(f"  {GUEST_DATA_BANNER}")
        for bline in str(it["body"]).splitlines():
            lines.append(f"  {bline}")
    lines.append(
        f"Reply in thread: `uv run atelier board reply <root_id> --agent {agent} \"...\"` "
        f"or inspect with `uv run atelier board thread <root_id>`."
    )
    return "\n".join(lines)


def subscribe(
    agent: str,
    command: list[str] | None,
    interval: float = 2.5,
    stall_after: float = 900.0,
    *,
    timeout: float | None = None,
    addressed_only: bool = True,
    checkout: str | Path | None = None,
    managed: bool = False,
    db_path: str | Path | None = None,
) -> int:
    norm_agent = agent_name(agent)
    store = SlackBoardStore(db_path or default_db_path())
    store.register_principal(norm_agent, norm_agent, "agent", "worker", title="Local MacBook Agent", hue="teal")

    sub_dir = root() / "board-subscribers"
    sub_dir.mkdir(parents=True, exist_ok=True)
    lock_file = sub_dir / f"{norm_agent}.lock"

    with lock_file.open("a") as lf:
        try:
            fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(f"Another subscriber is already active for agent '{norm_agent}'")

        cursor = store.subscriber_cursor(norm_agent)
        store.update_subscriber_state(norm_agent, cursor=cursor, pid=os.getpid(), heartbeat=time.time(), last_error=None)
        started = time.monotonic()

        try:
            while True:
                now = time.time()
                stop = store.update_subscriber_state(norm_agent, pid=os.getpid(), heartbeat=now)
                if stop and not managed:
                    return 0

                pending = store.pending_agent_wakeups(norm_agent, after_notif_id=cursor)
                if pending:
                    text = format_wakeup_batch(norm_agent, pending)
                    new_cursor = int(pending[-1]["notif_id"])
                    if command is None:
                        print(text, flush=True)
                        store.update_subscriber_state(norm_agent, cursor=new_cursor, heartbeat=time.time(), last_error=None)
                        return 0
                    argv = [text if arg == "{message}" else arg for arg in command]
                    proc = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
                    if proc.returncode == 0:
                        cursor = new_cursor
                        store.update_subscriber_state(norm_agent, cursor=cursor, heartbeat=time.time(), last_error=None)
                    else:
                        err = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()[:240]
                        store.update_subscriber_state(norm_agent, heartbeat=time.time(), last_error=err)

                if timeout is not None and (time.monotonic() - started) >= timeout:
                    return 3
                time.sleep(max(0.25, min(interval, 10.0)))
        finally:
            store.update_subscriber_state(norm_agent, pid=None, heartbeat=time.time())


def background(args: Any) -> int:
    argv = [
        sys.executable,
        "-m",
        "atelier.cli",
        "board",
        "subscribe",
        "--agent",
        args.agent,
        "--interval",
        str(args.interval),
        "--stall-after",
        str(args.stall_after),
        "--checkout",
        str(args.checkout),
    ]
    if getattr(args, "notify", None):
        argv.extend(["--notify", args.notify])
    if getattr(args, "addressed_only", False):
        argv.append("--addressed-only")
    log_dir = root() / "board-subscribers"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_f = (log_dir / f"{agent_name(args.agent)}.log").open("a")
    subprocess.Popen(argv, stdout=log_f, stderr=log_f, start_new_session=True)
    return 0


def configure(sub: Any) -> None:
    from atelier.harness import board_cli
    board_cli.configure(sub)


def main(args: Any) -> int:
    from atelier.harness import board_cli
    return board_cli.main(args)
