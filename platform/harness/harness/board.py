"""The `atelier board` package entry point, local & remote subscriber wakeup loops, and launchd helpers."""
from __future__ import annotations

import fcntl
import hashlib
import http.client
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Any

from atelier.harness.board_store import agent_name, database, root
from atelier.harness.slack_board import (
    GUEST_DATA_BANNER,
    PermissionDenied,
    SlackBoardStore,
    board_dir,
    default_db_path,
    http_json,
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
        if it.get("untrusted_envelope") or (it.get("author_role") == "guest" and kind == "guest_triage"):
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
    addressed_only: bool = False,
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

                pending = store.pending_agent_wakeups(norm_agent, after_notif_id=cursor, addressed_only=addressed_only)
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


# ----------------- REMOTE GUEST WAIT & SUBSCRIBE -----------------


def _remote_cursors_dir() -> Path:
    d = board_dir() / "remote-cursors"
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


def remote_cursor_file(origin: str, agent: str) -> Path:
    norm_origin = origin.strip().rstrip("/").lower()
    digest = hashlib.sha256(norm_origin.encode("utf-8")).hexdigest()[:12]
    return _remote_cursors_dir() / f"{digest}__{agent_name(agent)}.json"


def read_remote_cursor_state(origin: str, agent: str) -> dict[str, Any] | None:
    p = remote_cursor_file(origin, agent)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def write_remote_cursor_state(origin: str, agent: str, state: dict[str, Any]) -> None:
    p = remote_cursor_file(origin, agent)
    tmp = p.with_suffix(".json.tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(state, f, indent=2)
    tmp.replace(p)


def request_remote_unsubscribe(origin: str, agent: str) -> None:
    st = read_remote_cursor_state(origin, agent) or {"origin": origin, "agent": agent_name(agent), "cursor": None}
    st["stop"] = True
    write_remote_cursor_state(origin, agent, st)


def list_remote_subscribers(origin: str) -> list[dict[str, Any]]:
    now = time.time()
    out: list[dict[str, Any]] = []
    for p in sorted(_remote_cursors_dir().glob("*.json")):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        if d.get("origin", "").rstrip("/").lower() != origin.rstrip("/").lower():
            continue
        d["responsive"] = bool(d.get("pid") and d.get("heartbeat") and (now - float(d["heartbeat"])) < 90.0)
        out.append(d)
    return out


def remote_subscribe(
    remote: dict[str, Any],
    agent: str,
    command: list[str] | None,
    interval: float = 2.0,
    *,
    timeout: float | None = None,
    addressed_only: bool = False,
    managed: bool = False,
    longpoll_hold: float = 20.0,
) -> int:
    """Block against remote `/api/wakeups` with local cursor persistence and clean sleep/restart retry."""
    norm_agent = agent_name(agent)
    origin = str(remote["origin"]).rstrip("/")

    sub_dir = root() / "board-subscribers"
    sub_dir.mkdir(parents=True, exist_ok=True)
    lock_file = sub_dir / f"remote-{norm_agent}.lock"

    with lock_file.open("a") as lf:
        try:
            fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(f"Another remote subscriber/waiter is already active for agent '{norm_agent}'")

        existing = read_remote_cursor_state(origin, norm_agent) or {}
        cursor: int | None = existing.get("cursor") if isinstance(existing.get("cursor"), int) else None
        db_epoch: str = str(existing.get("db_epoch") or "")
        state: dict[str, Any] = {
            "origin": origin,
            "agent": norm_agent,
            "cursor": cursor,
            "db_epoch": db_epoch,
            "pid": os.getpid(),
            "heartbeat": time.time(),
            "stop": False,
            "last_error": None,
        }
        write_remote_cursor_state(origin, norm_agent, state)

        started = time.monotonic()
        backoff = 0.5

        try:
            while True:
                cur_disk = read_remote_cursor_state(origin, norm_agent) or {}
                if cur_disk.get("stop") and not managed:
                    return 0

                if timeout is not None:
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        return 3
                else:
                    remaining = longpoll_hold

                hold = 0.0 if cursor is None else max(0.0, min(longpoll_hold, remaining))
                after_param = -1 if cursor is None else cursor
                addr_param = "1" if addressed_only else "0"
                path = f"/api/wakeups?after={after_param}&timeout={hold:.2f}&addressed_only={addr_param}"

                state["pid"] = os.getpid()
                state["heartbeat"] = time.time()
                write_remote_cursor_state(origin, norm_agent, state)

                try:
                    st_code, data = http_json(
                        origin,
                        "GET",
                        path,
                        headers={"X-Atelier-Agent": norm_agent},
                        timeout=hold + 8.0,
                    )
                except (
                    urllib.error.URLError,
                    TimeoutError,
                    socket.timeout,
                    ConnectionError,
                    http.client.HTTPException,
                    OSError,
                ) as exc:
                    # Host MacBook is asleep or restarting: retain cursor and retry cleanly with bounded backoff
                    state["last_error"] = f"host unreachable ({exc})"
                    state["heartbeat"] = time.time()
                    write_remote_cursor_state(origin, norm_agent, state)
                    if timeout is not None:
                        rem = timeout - (time.monotonic() - started)
                        if rem <= 0:
                            return 3
                        time.sleep(min(backoff, rem))
                    else:
                        time.sleep(backoff)
                    backoff = min(5.0, backoff * 1.8)
                    continue

                if st_code in (408, 429, 500, 502, 503, 504):
                    state["last_error"] = f"HTTP {st_code}"
                    state["heartbeat"] = time.time()
                    write_remote_cursor_state(origin, norm_agent, state)
                    if timeout is not None:
                        rem = timeout - (time.monotonic() - started)
                        if rem <= 0:
                            return 3
                        time.sleep(min(backoff, rem))
                    else:
                        time.sleep(backoff)
                    backoff = min(5.0, backoff * 1.8)
                    continue

                if st_code != 200:
                    raise PermissionDenied(data.get("error") or f"HTTP {st_code}")

                backoff = 0.5
                state["last_error"] = None
                if data.get("viewer_id"):
                    state["viewer_id"] = data["viewer_id"]

                resp_epoch = str(data.get("db_epoch") or "")
                if cursor is None:
                    cursor = int(data.get("cursor", 0))
                    db_epoch = resp_epoch
                    state["cursor"] = cursor
                    state["db_epoch"] = db_epoch
                    state["heartbeat"] = time.time()
                    write_remote_cursor_state(origin, norm_agent, state)
                    continue

                # If host DB was recreated from scratch (`db_epoch` changed), re-anchor cleanly via `after=-1`
                if resp_epoch and db_epoch and resp_epoch != db_epoch:
                    cursor = None
                    db_epoch = resp_epoch
                    state["cursor"] = None
                    state["db_epoch"] = db_epoch
                    write_remote_cursor_state(origin, norm_agent, state)
                    continue
                if resp_epoch and not db_epoch:
                    db_epoch = resp_epoch
                    state["db_epoch"] = db_epoch

                wakeups = data.get("wakeups") or []
                if wakeups:
                    text = format_wakeup_batch(norm_agent, wakeups)
                    new_cursor = int(wakeups[-1]["notif_id"])
                    if command is None:
                        print(text, flush=True)
                        cursor = new_cursor
                        state["cursor"] = cursor
                        state["heartbeat"] = time.time()
                        write_remote_cursor_state(origin, norm_agent, state)
                        return 0
                    argv = [text if arg == "{message}" else arg for arg in command]
                    proc = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
                    if proc.returncode == 0:
                        cursor = new_cursor
                        state["cursor"] = cursor
                        state["heartbeat"] = time.time()
                        state["last_error"] = None
                        write_remote_cursor_state(origin, norm_agent, state)
                    else:
                        err = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()[:240]
                        state["last_error"] = err
                        state["heartbeat"] = time.time()
                        write_remote_cursor_state(origin, norm_agent, state)
                        time.sleep(max(0.5, min(interval, 5.0)))
        finally:
            state["pid"] = None
            state["heartbeat"] = time.time()
            write_remote_cursor_state(origin, norm_agent, state)


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
