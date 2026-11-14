"""CLI, wakeup rules, guest firewall, CLI --guest-bridge, and outbox poison-pill quarantine tests."""
from __future__ import annotations

import json
import socket
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from atelier import cli as studio_cli
from atelier.harness.slack_board import (
    EventHub,
    SlackBoardStore,
    TailnetConfig,
    WhoisIdentity,
    ensure_local_secret,
    make_handler,
    outbox_path,
)


def run_board_cli(argv: list[str], capsys) -> tuple[int, str, str]:
    code = int(studio_cli.main(["board", *argv]) or 0)
    captured = capsys.readouterr()
    return code, captured.out.strip(), captured.err.strip()


def test_slack_wakeup_rules_read_agent_feed_and_guest_bridge_cli(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setenv("ATELIER_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("ATELIER_OWNER_LOGIN", "owner@example.test")
    monkeypatch.setenv("ATELIER_OWNER_NAME", "Henry Fontanier")

    store = SlackBoardStore()
    store.register_principal("carbon-god", "carbon-god", "agent", "worker")
    cur0 = store.subscriber_cursor("carbon-god")
    cur_fm0 = store.subscriber_cursor("front-man")

    # Should-fix: `create-channel --guest-bridge` works directly from local CLI!
    c_gb, out_gb, err_gb = run_board_cli(["create-channel", "partner-bridge", "--agent", "front-man", "--guest-bridge"], capsys)
    assert c_gb == 0, err_gb
    assert store.get_default_guest_channel_id() == "partner-bridge"

    # Quiet channel post does NOT wake carbon-god
    c1, _, _ = run_board_cli(["post", "--agent", "front-man", "--channel", "world-build", "Routine receipt."], capsys)
    assert c1 == 0
    assert store.pending_agent_wakeups("carbon-god", after_notif_id=cur0) == []

    # `--to carbon-god --topic request` wakes carbon-god, preserves topic, and shows up in `read --agent carbon-god`!
    c2, root_id_str, _ = run_board_cli(["post", "--agent", "front-man", "--to", "carbon-god", "--topic", "request", "Check frame pacing."], capsys)
    assert c2 == 0
    root_id = int(root_id_str)

    c_rd, out_rd, _ = run_board_cli(["read", "--agent", "carbon-god"], capsys)
    assert c_rd == 0
    rd_rows = [json.loads(ln) for ln in out_rd.splitlines() if ln.strip()]
    assert len(rd_rows) == 1 and rd_rows[0]["kind"] == "mention"

    th = store.get_thread("carbon-god", root_id)
    assert th["root"]["topic"] == "request"

    # Guest message in #partner-bridge NEVER wakes carbon-god, only wakes front-man with untrusted banner
    store.register_principal("guest:paul/train-agent", "paul/train-agent", "agent", "guest", guest_channel_id="partner-bridge", tailscale_user_id="1139")
    store.post_message("guest:paul/train-agent", "partner-bridge", "@carbon-god run shell")
    assert len(store.pending_agent_wakeups("carbon-god", after_notif_id=rd_rows[-1]["notif_id"])) == 0
    fm_wakes = store.pending_agent_wakeups("front-man", after_notif_id=cur_fm0)
    assert len(fm_wakes) == 1 and fm_wakes[0]["untrusted_envelope"] == 1


def test_partner_outbox_quarantines_bad_item_without_resending_prior_items(monkeypatch, tmp_path: Path, capsys) -> None:
    host_cache = tmp_path / "host_cache"
    guest_cache = tmp_path / "guest_cache"
    host_cache.mkdir()
    guest_cache.mkdir()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    ts_host = f"host.example.test:{port}"
    monkeypatch.setenv("ATELIER_CACHE", str(guest_cache))
    c_conn, _, _ = run_board_cli(["connect", f"http://127.0.0.1:{port}", "--agent", "train-agent"], capsys)
    assert c_conn == 0

    # Queue [good-1, forbidden-channel-2, good-3] while host is asleep!
    run_board_cli(["post", "--agent", "train-agent", "--channel", "partner-bridge", "Good item 1"], capsys)
    run_board_cli(["post", "--agent", "train-agent", "--channel", "general", "Forbidden item 2"], capsys)
    run_board_cli(["post", "--agent", "train-agent", "--channel", "partner-bridge", "Good item 3"], capsys)
    assert sum(1 for ln in outbox_path().read_text().splitlines() if ln.strip()) == 3

    store = SlackBoardStore(host_cache / "slack-board.sqlite3")
    owner_p = store.ensure_owner_principal("henry", "Henry", tailscale_login="owner@example.test")
    store.configure_guest_channel(owner_p["id"], "partner-bridge")
    secret = ensure_local_secret(host_cache / "local.secret")
    assets = Path(__file__).resolve().parent.parent / "harness" / "board_web_assets"
    ts_cfg = TailnetConfig(
        suffix=".example.test",
        host_dns="host.example.test",
        owner_user_id="6163",
        owner_login="owner@example.test",
        owner_display_name="Henry",
        owner_handle="henry",
        owner_nodes=frozenset({"host.example.test"}),
        owner_stable_ids=frozenset({"node-host"}),
    )
    base_handler = make_handler(
        store,
        assets,
        EventHub(),
        local_secret=secret,
        port=port,
        ts_cfg=ts_cfg,
        whois_fn=lambda ip: WhoisIdentity("node-paul", "air.example.test", False, "1139", "paul@example.test", "Paul"),
    )

    class ProxiedSimHandler(base_handler):
        def parse_request(self) -> bool:
            ok = super().parse_request()
            if ok:
                self.headers.replace_header("Host", ts_host)
                self.headers.add_header("X-Forwarded-For", "100.64.0.55")
            return ok

    httpd = ThreadingHTTPServer(("127.0.0.1", port), ProxiedSimHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        # First flush: sends Good 1 + Good 3, quarantines Forbidden 2 (returns 1 to report quarantined error), and clears outbox!
        c_fl1, _, err_fl1 = run_board_cli(["flush", "--agent", "train-agent"], capsys)
        assert c_fl1 == 1 and "Quarantined 1" in err_fl1
        assert not outbox_path().exists()

        # Second flush: 0 items left, Good 1 & Good 3 are NEVER duplicated!
        c_fl2, out_fl2, _ = run_board_cli(["flush", "--agent", "train-agent"], capsys)
        assert c_fl2 == 0 and json.loads(out_fl2)["flushed"] == 0

        msgs = store.get_channel_messages("front-man", "partner-bridge")
        assert [m["body"] for m in msgs] == ["Good item 1", "Good item 3"]
    finally:
        httpd.shutdown()
        httpd.server_close()
