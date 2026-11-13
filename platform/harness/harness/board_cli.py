"""Unified CLI for the Slack-style Atelier Board (local agents + Tailscale fork guests)."""
from __future__ import annotations

import json
import math
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Any

from atelier import paths
from atelier.harness.slack_board import (
    DEFAULT_PORT,
    GUEST_BRIDGE_CHANNEL,
    PermissionDenied,
    SlackBoardStore,
    cache_root,
    default_db_path,
    default_secret_path,
    discover_tailnet_config,
    enqueue_outbox_item,
    flush_outbox,
    http_json,
    load_remote_config,
    outbox_path,
    post_via_local_or_store,
    remote_config_path,
    save_remote_config,
    valid_agent_name,
)

LEGACY_TOPICS = ("info", "request", "ack", "handoff", "blocked", "evidence", "alert")


def watch_options(parser: Any) -> None:
    parser.add_argument("--interval", type=float, default=2.5)
    parser.add_argument("--stall-after", type=float, default=900.0)
    parser.add_argument("--addressed-only", action="store_true", help="wake only on @mention, DM, or subscribed thread")
    parser.add_argument("--checkout", default=str(paths.REPO))


def configure(sub: Any) -> None:
    p = sub.add_parser("board", help="Slack-style workspace channels, threads, DMs, and #fork-sync guest bridge")
    actions = p.add_subparsers(dest="action", required=True)

    # post
    q = actions.add_parser("post", help="post to a channel (#world-build, #fork-sync) or scarce DM (--dm <peer>)")
    q.add_argument("--agent", required=True, help="caller agent handle")
    q.add_argument("--channel", "-c", default=None, help="target channel name, e.g. world-build or #fork-sync")
    q.add_argument("--dm", default=None, help="Direct Message recipient (USE SCARCELY for humans — triggers browser alert!)")
    q.add_argument("--to", default=None, help="mention handle or channel compatibility target")
    q.add_argument("--all-agents", action="store_true", help="compat flag: post announcement to #general")
    q.add_argument("--topic", choices=LEGACY_TOPICS, default="info", help="optional message tag")
    q.add_argument("--reply-to", type=int, default=None, help="reply inside thread of root message ID")
    q.add_argument("--notify-operator", action="store_true", help="scarce urgent DM escalation to workspace owner")
    q.add_argument("--attach", action="append", default=[], metavar="FILE", help="append file path reference(s)")
    q.add_argument("message", nargs="?", default="", help="Markdown message text (or '-' for stdin)")

    # reply (clean ergonomic shorthand for thread replies)
    q = actions.add_parser("reply", help="reply inside an existing thread")
    q.add_argument("root_id", type=int, help="root or parent message ID")
    q.add_argument("--agent", required=True, help="caller agent handle")
    q.add_argument("--channel", "-c", default=None, help="optional channel hint (required for offline remote queue)")
    q.add_argument("--also-channel", action="store_true", help="also broadcast reply to the parent channel")
    q.add_argument("message", help="Markdown reply text (or '-' for stdin)")

    # read
    q = actions.add_parser("read", help="read messages in a channel or pending notifications for an agent")
    q.add_argument("--channel", "-c", default=None, help="channel to read (default: #general locally, #fork-sync for guests)")
    q.add_argument("--agent", default=None, help="agent identity")
    q.add_argument("--after", type=int, default=0, help="only messages with id > AFTER")
    q.add_argument("--limit", type=int, default=50, help="max messages (1..500)")
    q.add_argument("--notifications", action="store_true", help="list wakeups/mentions for --agent")

    # thread
    q = actions.add_parser("thread", help="print a root message and all of its thread replies in order")
    q.add_argument("id", type=int, help="message ID in thread")
    q.add_argument("--agent", default=None, help="viewer agent identity")

    # channels & create-channel
    q = actions.add_parser("channels", help="list accessible channels")
    q.add_argument("--agent", default=None)

    q = actions.add_parser("create-channel", help="create a public or private workspace channel")
    q.add_argument("name", help="channel slug, e.g. belmonte-art")
    q.add_argument("--agent", required=True)
    q.add_argument("--private", action="store_true", help="create a private invite-only channel")
    q.add_argument("--topic", default="", help="channel topic")

    # task
    q = actions.add_parser("task", help="set your concise status line (<= 160 chars, or 'idle')")
    q.add_argument("--agent", required=True)
    q.add_argument("text", help="status text (or 'idle')")

    # claim
    q = actions.add_parser("claim", help="record an advisory scope claim on the board")
    q.add_argument("scope", help="file/path glob")
    q.add_argument("--agent", required=True)
    q.add_argument("--channel", default="world-build")
    q.add_argument("--branch", default="")
    q.add_argument("--note", default="")

    # connect / flush / doctor (Partner & Guest Fork Workflow)
    q = actions.add_parser("connect", help="connect a partner fork machine over Tailscale HTTPS")
    q.add_argument("origin", help="Tailscale HTTPS URL, e.g. https://host.example.ts.net")
    q.add_argument("--agent", default=None, help="optional default agent name on this fork machine")

    q = actions.add_parser("flush", help="flush queued offline messages from ~/.cache/atelier/board/outbox.jsonl")
    q.add_argument("--agent", default=None)

    q = actions.add_parser("doctor", help="diagnose Tailscale identity, HTTPS connectivity, and offline outbox")
    q.add_argument("--agent", default=None)

    # subscribe / wait / supervise / retire / unsubscribe / status
    q = actions.add_parser("subscribe", help="run persistent wakeup listener (@mentions, DMs, subscribed threads)")
    q.add_argument("--agent", required=True)
    q.add_argument("--background", action="store_true")
    q.add_argument("--notify", help="JSON argv with '{message}' placeholder")
    watch_options(q)
    q.add_argument("--managed", action="store_true")

    q = actions.add_parser("supervise", help="install persistent macOS launchd wakeup listener")
    q.add_argument("--agent", required=True)
    q.add_argument("--notify", required=True)
    q.add_argument("--checkout", default=str(paths.REPO))
    q.add_argument("--addressed-only", action="store_true")

    q = actions.add_parser("retire", help="retire persistent launchd listener")
    q.add_argument("--agent", required=True)

    q = actions.add_parser("wait", help="block until next wakeup (@mention, DM, or subscribed thread) and print it")
    q.add_argument("--agent", required=True)
    q.add_argument("--timeout", type=float, default=3600.0)
    watch_options(q)

    q = actions.add_parser("unsubscribe", help="stop an unsupervised background listener")
    q.add_argument("--agent", required=True)

    actions.add_parser("status", help="list active agent wakeup listeners and responsiveness")

    # serve
    q = actions.add_parser("serve", help="run the Slack-style Atelier Board HTTP/SSE server on loopback")
    q.add_argument("--host", default="127.0.0.1")
    q.add_argument("--port", type=int, default=DEFAULT_PORT)
    q.add_argument("--db", type=Path, default=None)
    q.add_argument("--owner-login", default=None, help="Tailscale LoginName of workspace owner (auto-discovered if omitted)")
    q.add_argument("--allowed-user", default=None, help="alias for --owner-login")
    q.add_argument("--public-origin", action="append", default=[], help="additional allowed HTTPS Origin(s)")
    q.add_argument("--seed", action="store_true", help="seed sample channels/messages on startup")
    # Graceful compatibility flags so existing launchd plists start without error before plist refresh:
    q.add_argument("--sender", default=None, help="deprecated compatibility flag")
    q.add_argument("--remote-status", type=Path, default=None, help="deprecated compatibility flag")
    q.add_argument("--prebuilt-server", type=Path, default=None, help="deprecated compatibility flag")
    q.add_argument("--prebuilt-sha256", default=None, help="deprecated compatibility flag")

    # Preserved session transport & Claude hook helpers
    q = actions.add_parser("notify-codex", help="steer an existing active Codex session from a board subscription")
    q.add_argument("--thread", required=True)
    q.add_argument("--codex", default="codex")
    q.add_argument("--socket", type=Path)
    q.add_argument("--codex-home", type=Path)
    q.add_argument("message")

    q = actions.add_parser("remote-watch", help="bounded recovery for explicitly owned macOS Claude remote services")
    q.add_argument("--config", type=Path, required=True)

    actions.add_parser("guard-claude", help="PreToolUse hook: bound foreground commands and job output checks")

    q = actions.add_parser("notify-claude", help="deliver to an existing native Claude inbox without a second writer")
    q.add_argument("--session-dir", type=Path, required=True)
    q.add_argument("--permission-class", choices=("prompting", "bypass"), default="prompting")
    q.add_argument("message")


def _read_body_arg(raw: str) -> str:
    text = sys.stdin.read(8001) if raw == "-" else raw
    return text.strip()


def _remote_post_or_queue(
    remote: dict[str, Any],
    *,
    agent: str,
    channel_id: str,
    body: str,
    root_id: int | None = None,
    also_channel: bool = False,
) -> int:
    origin = remote["origin"]
    # Try flushing any earlier queued items first
    flush_outbox(origin, agent=agent)
    payload = {
        "channel_id": channel_id,
        "body": body,
        "root_id": root_id,
        "also_channel": also_channel,
    }
    try:
        st, resp = http_json(
            origin,
            "POST",
            "/api/messages",
            payload=payload,
            headers={"X-Atelier-Agent": agent},
            timeout=5.0,
        )
        if st in (200, 201) and "message" in resp:
            print(resp["message"]["id"])
            return 0
        if st in (408, 429, 500, 502, 503, 504):
            depth = enqueue_outbox_item({"agent": agent, "payload": payload, "queued_at": time.time()})
            print(f"queued (host HTTP {st}; {depth} item(s) in offline outbox — run `atelier board flush` when host wakes)")
            return 0
        raise PermissionDenied(resp.get("error") or f"HTTP {st}")
    except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError):
        depth = enqueue_outbox_item({"agent": agent, "payload": payload, "queued_at": time.time()})
        print(f"queued (host unreachable/asleep; {depth} item(s) in offline outbox — will auto-flush when reachable)")
        return 0


def main(args: Any) -> int:
    from atelier.harness.board import background, notify_command, subscribe
    from atelier.harness.board_store import database

    try:
        remote = load_remote_config()

        if args.action == "connect":
            cfg = save_remote_config(args.origin, args.agent)
            hdrs = {"X-Atelier-Agent": cfg["agent"]} if cfg.get("agent") else {}
            try:
                st, info = http_json(cfg["origin"], "GET", "/api/whoami", headers=hdrs, timeout=6.0)
                if st != 200:
                    raise PermissionDenied(info.get("error") or f"HTTP {st}")
                v = info["viewer"]
                print(
                    f"Connected to {cfg['origin']} as {v['display_name']} (id={v['id']}, role={v['role']}, "
                    f"channel=#{v.get('guest_channel_id') or 'workspace'})"
                )
            except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError) as exc:
                print(
                    f"Saved remote {cfg['origin']} to {remote_config_path()}, but host is currently unreachable ({exc}). "
                    f"Posts will queue offline until the host wakes."
                )
            return 0

        if args.action == "flush":
            if not remote:
                print("No remote board configured (`atelier board connect <url>`).", file=sys.stderr)
                return 1
            sent, rem = flush_outbox(remote["origin"], agent=args.agent or remote.get("agent"))
            print(json.dumps({"flushed": sent, "remaining": rem, "origin": remote["origin"]}))
            return 0

        if args.action == "doctor":
            report: dict[str, Any] = {
                "mode": "remote" if remote else "local",
                "db_path": str(default_db_path()),
                "local_secret_present": default_secret_path().is_file(),
                "remote_config": remote,
                "outbox_queued": (
                    sum(1 for ln in outbox_path().read_text().splitlines() if ln.strip())
                    if outbox_path().is_file()
                    else 0
                ),
            }
            ts_cfg = discover_tailnet_config()
            report["tailscale"] = {
                "host_dns": ts_cfg.host_dns,
                "suffix": ts_cfg.suffix,
                "owner_login": ts_cfg.owner_login,
                "owner_display_name": ts_cfg.owner_display_name,
            }
            if remote:
                hdrs = {"X-Atelier-Agent": args.agent or remote["agent"]} if (args.agent or remote.get("agent")) else {}
                try:
                    st, who = http_json(remote["origin"], "GET", "/api/whoami", headers=hdrs, timeout=5.0)
                    report["remote_status"] = st
                    report["whoami"] = who
                except Exception as exc:
                    report["remote_status"] = "unreachable"
                    report["remote_error"] = str(exc)
            print(json.dumps(report, indent=2))
            return 0

        if args.action == "post":
            ag = valid_agent_name(args.agent)
            text = _read_body_arg(args.message)
            if args.attach:
                att_lines = [f"[attachment: {Path(p).expanduser().resolve()}]" for p in args.attach]
                text = (text + "\n" + "\n".join(att_lines)).strip()
            if not text:
                raise ValueError("Message text cannot be empty")

            if remote:
                ch = (args.channel or GUEST_BRIDGE_CHANNEL).lstrip("#")
                return _remote_post_or_queue(
                    remote,
                    agent=ag,
                    channel_id=ch,
                    body=text,
                    root_id=args.reply_to,
                )

            store = SlackBoardStore()
            dm_peer: str | None = args.dm.lstrip("@").lower() if args.dm else None
            channel_id = (args.channel or "").lstrip("#")

            if args.notify_operator and not dm_peer and not channel_id:
                ts_cfg = discover_tailnet_config()
                owner = store.ensure_owner_principal(ts_cfg.owner_handle, ts_cfg.owner_display_name, tailscale_login=ts_cfg.owner_login)
                dm_peer = owner["id"]

            if not channel_id and not dm_peer:
                if args.reply_to is not None:
                    th = store.get_thread("front-man", args.reply_to)
                    channel_id = th["channel"]["id"]
                elif args.to and args.to not in ("*", "operator"):
                    target = args.to.lstrip("@#").lower()
                    # Check if target is an existing channel; otherwise post in #general with @mention
                    boot_ch_ids = {c["id"] for c in store.get_bootstrap("front-man")["explorable_channels"]}
                    if target in boot_ch_ids:
                        channel_id = target
                    else:
                        channel_id = "general"
                        if f"@{target}" not in text.lower():
                            text = f"@{target} {text}"
                else:
                    channel_id = "general"

            msg = post_via_local_or_store(
                store,
                agent_id=ag,
                channel_id=channel_id,
                body=text,
                root_id=args.reply_to,
                dm_peer=dm_peer,
            )
            print(msg["id"])
            return 0

        if args.action == "reply":
            ag = valid_agent_name(args.agent)
            text = _read_body_arg(args.message)
            if remote:
                ch = (args.channel or GUEST_BRIDGE_CHANNEL).lstrip("#")
                return _remote_post_or_queue(
                    remote,
                    agent=ag,
                    channel_id=ch,
                    body=text,
                    root_id=args.root_id,
                    also_channel=args.also_channel,
                )
            store = SlackBoardStore()
            store.register_principal(ag, ag, "agent", "worker", title="Local MacBook Agent", hue="teal")
            th = store.get_thread(ag, args.root_id)
            msg = post_via_local_or_store(
                store,
                agent_id=ag,
                channel_id=th["channel"]["id"],
                body=text,
                root_id=args.root_id,
            )
            print(msg["id"])
            return 0

        if args.action == "read":
            if args.after < 0 or not (1 <= args.limit <= 500):
                raise ValueError("--after must be >= 0 and --limit must be 1..500")
            if remote:
                ag = valid_agent_name(args.agent or remote.get("agent") or "fork-agent")
                flush_outbox(remote["origin"], agent=ag)
                ch = (args.channel or GUEST_BRIDGE_CHANNEL).lstrip("#")
                st, resp = http_json(
                    remote["origin"],
                    "GET",
                    f"/api/channels/{urllib.parse.quote(ch)}/messages?after={args.after}&limit={args.limit}",
                    headers={"X-Atelier-Agent": ag},
                    timeout=6.0,
                )
                if st != 200:
                    raise PermissionDenied(resp.get("error") or f"HTTP {st}")
                for row in resp.get("messages", []):
                    print(json.dumps(row))
                return 0

            store = SlackBoardStore()
            viewer = valid_agent_name(args.agent) if args.agent else "front-man"
            if args.agent:
                store.register_principal(viewer, viewer, "agent", "worker", title="Local MacBook Agent", hue="teal")
            if args.notifications and args.agent:
                for row in store.pending_agent_wakeups(viewer, after_notif_id=args.after):
                    print(json.dumps(row))
                return 0
            ch = (args.channel or "general").lstrip("#")
            for row in store.get_channel_messages(viewer, ch, after_id=args.after, limit=args.limit):
                print(json.dumps(row))
            return 0

        if args.action == "thread":
            if remote:
                ag = valid_agent_name(args.agent or remote.get("agent") or "fork-agent")
                st, resp = http_json(
                    remote["origin"],
                    "GET",
                    f"/api/threads/{args.id}",
                    headers={"X-Atelier-Agent": ag},
                    timeout=6.0,
                )
                if st != 200:
                    raise PermissionDenied(resp.get("error") or f"HTTP {st}")
                print(json.dumps(resp["root"]))
                for rep in resp.get("replies", []):
                    print(json.dumps(rep))
                return 0

            store = SlackBoardStore()
            viewer = valid_agent_name(args.agent) if args.agent else "front-man"
            if args.agent:
                store.register_principal(viewer, viewer, "agent", "worker", title="Local MacBook Agent", hue="teal")
            th = store.get_thread(viewer, args.id)
            print(json.dumps(th["root"]))
            for rep in th["replies"]:
                print(json.dumps(rep))
            return 0

        if args.action == "channels":
            store = SlackBoardStore()
            viewer = valid_agent_name(args.agent) if args.agent else "front-man"
            if args.agent:
                store.register_principal(viewer, viewer, "agent", "worker", title="Local MacBook Agent", hue="teal")
            boot = store.get_bootstrap(viewer)
            for ch in boot["explorable_channels"]:
                print(json.dumps(ch))
            return 0

        if args.action == "create-channel":
            ag = valid_agent_name(args.agent)
            store = SlackBoardStore()
            store.register_principal(ag, ag, "agent", "worker", title="Local MacBook Agent", hue="teal")
            ch = store.create_channel(ag, args.name, "private" if args.private else "public", topic=args.topic)
            print(json.dumps(ch))
            return 0

        if args.action == "task":
            ag = valid_agent_name(args.agent)
            store = SlackBoardStore()
            txt = store.set_agent_task(ag, args.text)
            print(f"{ag}: {txt}" if txt else f"{ag}: idle")
            return 0

        if args.action == "claim":
            ag = valid_agent_name(args.agent)
            store = SlackBoardStore()
            store.register_principal(ag, ag, "agent", "worker", title="Local MacBook Agent", hue="teal")
            row = store.claim_scope(ag, args.scope, args.channel.lstrip("#"), branch=args.branch, note=args.note)
            print(json.dumps(row))
            return 0

        if args.action in ("subscribe", "wait"):
            ag = valid_agent_name(args.agent)
            if not getattr(args, "managed", False):
                with database() as db:
                    row = db.execute("SELECT supervised FROM subscribers WHERE agent=?", (ag,)).fetchone()
                    if row and row["supervised"]:
                        raise ValueError("This owner already has a persistent listener; do not re-arm a fallback wait")
            if not (0.25 <= args.interval <= 60) or not math.isfinite(args.stall_after) or args.stall_after < 60:
                raise ValueError("--interval must be 0.25..60 seconds; --stall-after must be at least 60")
            if args.action == "wait":
                if not math.isfinite(args.timeout) or args.timeout < 0:
                    raise ValueError("--timeout must be finite and nonnegative")
                return subscribe(
                    ag,
                    None,
                    args.interval,
                    args.stall_after,
                    timeout=args.timeout,
                    addressed_only=args.addressed_only,
                    checkout=args.checkout,
                )
            command = notify_command(args.notify) if args.notify else None
            if args.managed and command is None:
                raise ValueError("managed listeners require an existing-session notification transport")
            if args.managed and args.background:
                raise ValueError("managed listeners are started by the service manager, without --background")
            if args.background:
                return background(args)
            return subscribe(
                ag,
                command,
                args.interval,
                args.stall_after,
                addressed_only=args.addressed_only,
                checkout=args.checkout,
                managed=args.managed,
            )

        if args.action in ("supervise", "retire"):
            from atelier.harness import board_service
            return board_service.install(args) if args.action == "supervise" else board_service.retire(args.agent)

        if args.action == "unsubscribe":
            ag = valid_agent_name(args.agent)
            with database() as db:
                row = db.execute("SELECT supervised FROM subscribers WHERE agent=?", (ag,)).fetchone()
                if row and row["supervised"]:
                    print("Persistent listener remains armed; use board retire only when permanently retiring this session")
                    return 0
                db.execute("UPDATE subscribers SET stop=1 WHERE agent=?", (ag,))
            print("stop requested; subscriber exits after its current poll")
            return 0

        if args.action == "status":
            store = SlackBoardStore()
            for item in store.list_subscribers():
                print(json.dumps(item))
            return 0

        if args.action == "serve":
            from atelier.harness import board_web
            return board_web.serve(args)

        if args.action == "notify-codex":
            from atelier.harness import board_codex
            try:
                with board_codex.connect(args.thread, args.codex, args.socket, args.codex_home) as client:
                    print(board_codex.notify(client, args.thread, args.message))
            except (OSError, board_codex.TransportError) as error:
                print(str(error), file=sys.stderr)
                return 1
            return 0

        if args.action == "notify-claude":
            from atelier.harness import board_claude
            try:
                print(board_claude.notify(args.session_dir, args.message, args.permission_class))
            except (OSError, ValueError, subprocess.SubprocessError, board_claude.TransportError) as error:
                print(
                    str(error) if isinstance(error, board_claude.TransportError) else "Claude inbox unavailable; delivery remains pending",
                    file=sys.stderr,
                )
                return 1
            return 0

        if args.action == "remote-watch":
            from atelier.harness import board_remote
            return board_remote.main(args.config)

        if args.action == "guard-claude":
            from atelier.harness import board_toolguard
            return board_toolguard.main()

    except (ValueError, LookupError, PermissionDenied, sqlite3.Error) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0
