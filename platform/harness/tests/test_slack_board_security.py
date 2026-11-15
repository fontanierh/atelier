"""End-to-end security, Tailscale UserProfile auth, SSE backpressure, and regression tests for `slack_board`."""
from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest

from atelier.harness.slack_board import (
    MAX_POST_BYTES,
    EventHub,
    PermissionDenied,
    SlackBoardStore,
    TailnetConfig,
    WhoisIdentity,
    _csrf_token_for,
    ensure_local_secret,
    make_handler,
    post_via_local_or_store,
    resolve_request_caller,
    serve_board,
    validate_post_security,
)

TEST_SUFFIX = ".example.test"
TEST_TS_CFG = TailnetConfig(
    suffix=TEST_SUFFIX,
    host_dns=f"owner-macbook{TEST_SUFFIX}",
    owner_user_id="6163001",
    owner_login="owner@example.test",
    owner_display_name="Henry Fontanier",
    owner_handle="henry",
    owner_nodes=frozenset({f"owner-macbook{TEST_SUFFIX}", f"owner-iphone{TEST_SUFFIX}", f"owner-laptop2{TEST_SUFFIX}"}),
    owner_stable_ids=frozenset({"node-owner-mac", "node-owner-phone", "node-owner-lap2"}),
)


def test_tailscale_user_login_host_allowlist_and_guest_isolation(tmp_path: Path) -> None:
    store = SlackBoardStore(tmp_path / "board.sqlite3")
    secret = ensure_local_secret(tmp_path / "local.secret")

    whois_table = {
        "100.64.0.1": WhoisIdentity("node-owner-mac", f"owner-macbook{TEST_SUFFIX}", False, "6163001", "owner@example.test", "Henry Fontanier"),
        "100.64.0.2": WhoisIdentity("node-owner-lap2", f"owner-laptop2{TEST_SUFFIX}", False, "6163001", "owner@example.test", "Henry Fontanier"),
        "100.64.0.10": WhoisIdentity("node-paul-air", f"macbook-air{TEST_SUFFIX}", False, "1139002", "paul@example.test", "Paul"),
        "100.64.0.11": WhoisIdentity("node-paul2-pro", "shared-peer.other-tailnet.example", False, "9999003", "paul.other@example.test", "Paul"),
        "100.64.0.99": WhoisIdentity("node-tagged-vm", f"bot-vm{TEST_SUFFIX}", True, "", "", ""),
    }

    # Blocker 5a: DNS rebinding / unallowlisted Host is rejected immediately even with forged XFF!
    with pytest.raises(PermissionDenied):
        resolve_request_caller(
            store,
            client_ip="127.0.0.1",
            headers={"Host": "evil.example", "X-Forwarded-For": "100.64.0.1"},
            qs={},
            local_secret=secret,
            port=8890,
            ts_cfg=TEST_TS_CFG,
            whois_fn=whois_table.get,
        )

    # Blocker 5b: Loopback Host carrying forged X-Forwarded-For is rejected!
    with pytest.raises(PermissionDenied):
        resolve_request_caller(
            store,
            client_ip="127.0.0.1",
            headers={"Host": "127.0.0.1:8890", "X-Forwarded-For": "100.64.0.1"},
            qs={},
            local_secret=secret,
            port=8890,
            ts_cfg=TEST_TS_CFG,
            whois_fn=whois_table.get,
        )

    # Unauthenticated loopback browser without Bearer is rejected by default!
    with pytest.raises(PermissionDenied):
        resolve_request_caller(
            store,
            client_ip="127.0.0.1",
            headers={"Host": "127.0.0.1:8890"},
            qs={},
            local_secret=secret,
            port=8890,
            ts_cfg=TEST_TS_CFG,
            allow_loopback_browser=False,
            whois_fn=whois_table.get,
        )

    # Owner connecting from multiple personal devices gets 'henry'
    for ip in ("100.64.0.1", "100.64.0.2"):
        vid, sec = resolve_request_caller(
            store,
            client_ip="127.0.0.1",
            headers={
                "Host": f"owner-macbook{TEST_SUFFIX}",
                "X-Forwarded-For": ip,
                "Tailscale-User-Login": "owner@example.test",
            },
            qs={},
            local_secret=secret,
            port=8890,
            ts_cfg=TEST_TS_CFG,
            whois_fn=whois_table.get,
        )
        assert vid == "henry" and sec["tier"] == "owner_device"

    # Blocker 5c: Proxied owner request attempting X-Atelier-Agent downgrade without Bearer is rejected!
    with pytest.raises(PermissionDenied):
        resolve_request_caller(
            store,
            client_ip="127.0.0.1",
            headers={
                "Host": f"owner-macbook{TEST_SUFFIX}",
                "X-Forwarded-For": "100.64.0.1",
                "X-Atelier-Agent": "front-man",
            },
            qs={},
            local_secret=secret,
            port=8890,
            ts_cfg=TEST_TS_CFG,
            whois_fn=whois_table.get,
        )

    # Default disabled external guest access -> 403
    with pytest.raises(PermissionDenied):
        resolve_request_caller(
            store,
            client_ip="127.0.0.1",
            headers={"Host": f"owner-macbook{TEST_SUFFIX}", "X-Forwarded-For": "100.64.0.10"},
            qs={},
            local_secret=secret,
            port=8890,
            ts_cfg=TEST_TS_CFG,
            whois_fn=whois_table.get,
        )

    # Enable custom guest channel 'partner-bridge'
    store.configure_guest_channel("henry", "partner-bridge")

    vid_paul, sec_paul = resolve_request_caller(
        store,
        client_ip="127.0.0.1",
        headers={"Host": f"owner-macbook{TEST_SUFFIX}", "X-Forwarded-For": "100.64.0.10"},
        qs={},
        local_secret=secret,
        port=8890,
        ts_cfg=TEST_TS_CFG,
        whois_fn=whois_table.get,
    )
    assert vid_paul == "guest:paul" and sec_paul["guest_jailed"] is True
    # Should-Fix: Guest security & bootstrap never leak owner emails/node IDs!
    assert sec_paul["owner_login"] == "" and sec_paul["owner_nodes"] == []
    g_boot = store.get_bootstrap(vid_paul)
    for p_info in g_boot["principals"].values():
        assert "tailscale_login" not in p_info
        assert "tailscale_user_id" not in p_info
        assert "stable_node_id" not in p_info
        assert p_info["tailnet_node"] == ""

    # Shared-in node from another tailnet suffix (`100.64.0.11`) also resolves cleanly via whois UserProfile without colliding on guest:paul!
    vid_paul2, _ = resolve_request_caller(
        store,
        client_ip="127.0.0.1",
        headers={"Host": f"owner-macbook{TEST_SUFFIX}", "X-Forwarded-For": "100.64.0.11"},
        qs={},
        local_secret=secret,
        port=8890,
        ts_cfg=TEST_TS_CFG,
        whois_fn=whois_table.get,
    )
    assert vid_paul2 != vid_paul and vid_paul2.startswith("guest:paul-")


def test_blocker_1_4_6_pagination_channel_upsert_and_fail_closed_startup(tmp_path: Path) -> None:
    store = SlackBoardStore(tmp_path / "pag.sqlite3")
    store.ensure_owner_principal("henry", "Henry Fontanier", tailscale_login="owner@example.test")
    store.register_principal("worker-a", "worker-a", "agent", "worker")
    store.register_principal("worker-b", "worker-b", "agent", "worker")

    # Blocker 1: 260 messages in #general -> get_bootstrap returns NEWEST 200 (61..260), plus `before` paging gets 1..60!
    first_id = None
    last_id = None
    for i in range(1, 261):
        m = store.post_message("worker-a", "general", f"msg-{i}")
        if i == 1:
            first_id = m["id"]
        if i == 260:
            last_id = m["id"]
    boot = store.get_bootstrap("henry")
    gen_msgs = boot["channels_messages"]["general"]
    assert len(gen_msgs) == 200
    assert gen_msgs[-1]["id"] == last_id and gen_msgs[-1]["body"] == "msg-260"
    gen_meta = next(c for c in boot["channels"] if c["id"] == "general")
    assert gen_meta["has_more"] is True

    older = store.get_channel_messages("henry", "general", before_id=gen_msgs[0]["id"], limit=100)
    assert len(older) == 60
    assert older[0]["id"] == first_id and older[-1]["body"] == "msg-60"

    # Blocker 4: Private channel & DM read bypass via create_channel is completely blocked!
    store.create_channel("henry", "secret-plans", "private", topic="Top secret")
    store.post_message("henry", "secret-plans", "Launch codes")
    with pytest.raises(PermissionDenied):
        store.get_channel_messages("worker-b", "secret-plans")
    with pytest.raises(ValueError, match="already exists"):
        store.create_channel("worker-b", "secret-plans", "public")
    with pytest.raises(PermissionDenied):
        store.get_channel_messages("worker-b", "secret-plans")
    with pytest.raises(ValueError):
        store.create_channel("worker-b", "dm-henry-worker-a", "dm")
    with pytest.raises(ValueError):
        store.create_channel("worker-b", "dm-henry-worker-a", "public")

    # Should-fix: Guest display_name matching an internal agent handle NEVER hijacks @mentions!
    store.configure_guest_channel("henry", "partner-bridge")
    store.register_principal("guest:sneaky", "worker-a", "human", "guest", guest_channel_id="partner-bridge", tailscale_user_id="8888")
    store.post_message("henry", "partner-bridge", "Ping @worker-a")
    assert store.pending_agent_wakeups("guest:sneaky", addressed_only=True) == []
    assert [w["kind"] for w in store.pending_agent_wakeups("guest:sneaky")] == ["channel_post"]

    # Blocker 6: serve_board exits non-zero (RuntimeError) if Tailscale owner_login discovery is empty!
    empty_ts = TailnetConfig(".ts.net", "localhost.ts.net", "", "", "Owner", "owner", frozenset(), frozenset())
    with patch("atelier.harness.slack_board.discover_tailnet_config", return_value=empty_ts), patch("time.sleep", return_value=None):
        with pytest.raises(RuntimeError, match="owner_login discovery failed"):
            serve_board(db_path=tmp_path / "fail.sqlite3", port=0, allow_loopback_browser=False)

    # Blocker 2b: post_via_local_or_store NEVER writes a second copy to SQLite on TimeoutError!
    with patch("atelier.harness.slack_board.default_db_path", return_value=store.db_path), \
         patch("atelier.harness.slack_board.default_secret_path", return_value=tmp_path / "s.sec"), \
         patch("atelier.harness.slack_board.http_json", side_effect=TimeoutError("timed out")):
        ensure_local_secret(tmp_path / "s.sec")
        before_cnt = len(store.get_channel_messages("henry", "world-build", limit=500))
        with pytest.raises(TimeoutError):
            post_via_local_or_store(store, agent_id="worker-a", channel_id="world-build", body="No duplicate!")
        after_cnt = len(store.get_channel_messages("henry", "world-build", limit=500))
        assert after_cnt == before_cnt


def test_live_http_stalled_sse_body_cap_and_dm_push(tmp_path: Path) -> None:
    store = SlackBoardStore(tmp_path / "e2e.sqlite3")
    secret = ensure_local_secret(tmp_path / "local.secret")
    assets = Path(__file__).resolve().parent.parent / "harness" / "board_web_assets"
    hub = EventHub(max_subscribers=16, queue_size=8)

    whois_map = {
        "100.64.0.1": WhoisIdentity("node-owner-mac", f"owner-macbook{TEST_SUFFIX}", False, "6163001", "owner@example.test", "Henry Fontanier"),
        "100.64.0.22": WhoisIdentity("node-paul-air", f"macbook-air{TEST_SUFFIX}", False, "1139002", "paul@example.test", "Paul"),
    }

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    handler = make_handler(
        store,
        assets,
        hub,
        local_secret=secret,
        port=port,
        ts_cfg=TEST_TS_CFG,
        whois_fn=whois_map.get,
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    guest_events: list[dict] = []
    owner_events: list[dict] = []
    stalled_sock: socket.socket | None = None

    def sse_reader(headers: dict[str, str], sink: list[dict]) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1.0)
        try:
            conn.request("GET", "/api/events", headers=headers)
            resp = conn.getresponse()
            assert resp.status == 200
            buf = ""
            while True:
                chunk = resp.fp.readline()
                if not chunk:
                    break
                line = chunk.decode("utf-8", errors="replace")
                if line.startswith("data:"):
                    buf = line[5:].strip()
                elif line.strip() == "" and buf:
                    sink.append(json.loads(buf))
                    buf = ""
        except (OSError, TimeoutError):
            pass
        finally:
            conn.close()

    try:
        def req(method: str, path: str, headers: dict[str, str], body: dict | str | None = None) -> tuple[int, dict, dict[str, str]]:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            raw = body.encode("utf-8") if isinstance(body, str) else (json.dumps(body).encode("utf-8") if body is not None else None)
            c.request(method, path, body=raw, headers=headers)
            r = c.getresponse()
            resp_hdrs = {k.lower(): v for k, v in r.getheaders()}
            data = json.loads(r.read().decode("utf-8") or "{}")
            c.close()
            return r.status, data, resp_hdrs

        owner_hdrs = {
            "Host": f"owner-macbook{TEST_SUFFIX}:{port}",
            "X-Forwarded-For": "100.64.0.1",
            "Tailscale-User-Login": "owner@example.test",
        }
        guest_hdrs = {
            "Host": f"owner-macbook{TEST_SUFFIX}:{port}",
            "X-Forwarded-For": "100.64.0.22",
            "Tailscale-User-Login": "paul@example.test",
        }

        st_boot, o_boot, o_rhdrs = req("GET", "/api/bootstrap", owner_hdrs)
        assert st_boot == 200 and o_boot["viewer"]["id"] == "henry"
        assert "content-security-policy" in o_rhdrs and o_rhdrs.get("x-frame-options") == "DENY"
        owner_csrf = o_boot["csrf_token"]

        # Blocker 3: Oversized Content-Length rejected with 413, non-numeric Content-Length -> 400!
        st_413, _, _ = req(
            "POST",
            "/api/messages",
            {
                "Host": f"127.0.0.1:{port}",
                "Authorization": f"Bearer {secret}",
                "X-Atelier-Agent": "front-man",
                "Content-Type": "application/json",
            },
            {"channel_id": "general", "body": "x" * (MAX_POST_BYTES + 100)},
        )
        assert st_413 == 413

        raw_bad_cl = socket.create_connection(("127.0.0.1", port), timeout=3)
        raw_bad_cl.sendall(
            f"POST /api/messages HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nAuthorization: Bearer {secret}\r\n"
            f"X-Atelier-Agent: front-man\r\nContent-Type: application/json\r\nContent-Length: notanumber\r\n\r\n".encode()
        )
        bad_cl_resp = raw_bad_cl.recv(512).decode("utf-8", errors="replace")
        raw_bad_cl.close()
        assert "400" in bad_cl_resp.splitlines()[0]

        # Configure guest channel
        st_cfg, _, _ = req(
            "POST",
            "/api/settings/guest-channel",
            {
                **owner_hdrs,
                "Content-Type": "application/json",
                "Origin": f"https://owner-macbook{TEST_SUFFIX}:{port}",
                "X-Atelier-CSRF": owner_csrf,
            },
            {"channel_id": "partner-bridge"},
        )
        assert st_cfg == 200
        store.create_channel("henry", "lead-ops", "private", member_ids=["front-man"])

        # Blocker 2a: Connect a STALLED guest SSE socket that NEVER reads a single byte after handshake!
        stalled_sock = socket.create_connection(("127.0.0.1", port), timeout=3)
        stalled_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        stalled_sock.sendall(
            f"GET /api/events HTTP/1.1\r\nHost: owner-macbook{TEST_SUFFIX}:{port}\r\n"
            f"X-Forwarded-For: 100.64.0.22\r\nTailscale-User-Login: paul@example.test\r\n\r\n".encode()
        )
        threading.Thread(target=sse_reader, args=(guest_hdrs, guest_events), daemon=True).start()
        threading.Thread(target=sse_reader, args=(owner_hdrs, owner_events), daemon=True).start()
        time.sleep(0.15)

        # Rapidly post 90 messages into #partner-bridge while stalled_sock never reads -> must finish fast without hanging!
        t0 = time.monotonic()
        for idx in range(90):
            st_m, _, _ = req(
                "POST",
                "/api/messages",
                {
                    "Host": f"127.0.0.1:{port}",
                    "Authorization": f"Bearer {secret}",
                    "X-Atelier-Agent": "front-man",
                    "Content-Type": "application/json",
                },
                {"channel_id": "partner-bridge", "body": f"update {idx} " + ("z" * 400)},
            )
            assert st_m == 201
        assert (time.monotonic() - t0) < 4.0

        # Internal message in #lead-ops + DM to henry -> Guest SSE never sees #lead-ops or DM!
        req(
            "POST",
            "/api/messages",
            {"Host": f"127.0.0.1:{port}", "Authorization": f"Bearer {secret}", "X-Atelier-Agent": "front-man", "Content-Type": "application/json"},
            {"channel_id": "lead-ops", "body": "Internal secret"},
        )
        req(
            "POST",
            "/api/messages",
            {"Host": f"127.0.0.1:{port}", "Authorization": f"Bearer {secret}", "X-Atelier-Agent": "carbon-god", "Content-Type": "application/json"},
            {"channel_id": "", "dm_peer": "henry", "body": "Need keychain approval"},
        )
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not any(ev.get("channel_kind") == "dm" for ev in owner_events):
            time.sleep(0.05)
        assert any(ev.get("channel_kind") == "dm" for ev in owner_events)
        leaked = [ev for ev in guest_events if ev.get("channel_id") not in (None, "partner-bridge")]
        assert leaked == [], f"Guest SSE leaked internal events: {leaked}"

        # Blocker A Regression: Raw-socket HTTP/1.1 keep-alive smuggling via GET-with-body and early-403 POST!
        smuggled_req = (
            f"GET /api/bootstrap HTTP/1.1\r\n"
            f"Host: owner-macbook{TEST_SUFFIX}:{port}\r\n"
            f"X-Forwarded-For: 100.64.0.1\r\n"
            f"Tailscale-User-Login: owner@example.test\r\n\r\n"
        ).encode()

        # Probe 1: GET /api/whoami carrying smuggled owner request as body -> rejected 400 and connection CLOSED (1 response only!)
        s1 = socket.create_connection(("127.0.0.1", port), timeout=3)
        s1.sendall(
            f"GET /api/whoami HTTP/1.1\r\n"
            f"Host: owner-macbook{TEST_SUFFIX}:{port}\r\n"
            f"X-Forwarded-For: 100.64.0.22\r\n"
            f"Content-Length: {len(smuggled_req)}\r\n\r\n".encode()
            + smuggled_req
        )
        chunks1 = []
        while part := s1.recv(4096):
            chunks1.append(part)
        s1.close()
        raw1 = b"".join(chunks1).decode("utf-8", errors="replace")
        assert raw1.count("HTTP/1.1 ") == 1, f"Expected exactly 1 HTTP response on GET smuggling probe, got:\n{raw1}"
        assert "400" in raw1.splitlines()[0] and "csrf_token" not in raw1

        # Probe 2: Early-rejected 403 POST (missing CSRF) carrying smuggled owner request as body -> 1 response only, connection CLOSED!
        s2 = socket.create_connection(("127.0.0.1", port), timeout=3)
        s2.sendall(
            f"POST /api/messages HTTP/1.1\r\n"
            f"Host: owner-macbook{TEST_SUFFIX}:{port}\r\n"
            f"X-Forwarded-For: 100.64.0.22\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(smuggled_req)}\r\n\r\n".encode()
            + smuggled_req
        )
        chunks2 = []
        while part := s2.recv(4096):
            chunks2.append(part)
        s2.close()
        raw2 = b"".join(chunks2).decode("utf-8", errors="replace")
        assert raw2.count("HTTP/1.1 ") == 1, f"Expected exactly 1 HTTP response on POST smuggling probe, got:\n{raw2}"
        assert "403" in raw2.splitlines()[0] and "csrf_token" not in raw2

        # Probe 3: Transfer-Encoding header is rejected immediately with 400 and closed!
        s3 = socket.create_connection(("127.0.0.1", port), timeout=3)
        s3.sendall(
            f"POST /api/messages HTTP/1.1\r\n"
            f"Host: owner-macbook{TEST_SUFFIX}:{port}\r\n"
            f"X-Forwarded-For: 100.64.0.22\r\n"
            f"Transfer-Encoding: chunked\r\n\r\n0\r\n\r\n".encode()
            + smuggled_req
        )
        chunks3 = []
        while part := s3.recv(4096):
            chunks3.append(part)
        s3.close()
        raw3 = b"".join(chunks3).decode("utf-8", errors="replace")
        assert raw3.count("HTTP/1.1 ") == 1 and "400" in raw3.splitlines()[0]

        # Should-fix D: Per-viewer SSE cap prevents a single guest from starving owner SSE connections!
        held_subs = [hub.subscribe("guest:paul") for _ in range(8)]
        assert sum(1 for x in held_subs if x is not None) <= 6
        owner_sub = hub.subscribe("henry")
        assert owner_sub is not None
        hub.unsubscribe(owner_sub)
        for hs in held_subs:
            hub.unsubscribe(hs)
    finally:
        if stalled_sock:
            stalled_sock.close()
        httpd.shutdown()
        httpd.server_close()


def test_guest_wakeups_principal_isolation_framing_and_coordinators(tmp_path: Path) -> None:
    # 0. Verify pre-existing legacy notifications CHECK schema upgrades cleanly to allow 'channel_post'
    import sqlite3 as _sq
    legacy_db = tmp_path / "legacy_check.sqlite3"
    with _sq.connect(str(legacy_db)) as raw_c:
        raw_c.executescript(
            """
            CREATE TABLE principals (id TEXT PRIMARY KEY, display_name TEXT NOT NULL, kind TEXT NOT NULL, role TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', tailnet_node TEXT NOT NULL DEFAULT '', stable_node_id TEXT NOT NULL DEFAULT '', tailscale_user_id TEXT NOT NULL DEFAULT '', tailscale_login TEXT NOT NULL DEFAULT '', hue TEXT NOT NULL DEFAULT 'amber', guest_channel_id TEXT, status TEXT NOT NULL DEFAULT 'active', status_text TEXT NOT NULL DEFAULT 'idle', dm_browser_notify INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL, updated_at REAL NOT NULL);
            CREATE TABLE channels (id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, topic TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '', guest_allowed INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0, created_by TEXT NOT NULL, created_at REAL NOT NULL);
            CREATE TABLE notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_id TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                channel_id TEXT NOT NULL,
                root_id INTEGER NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('mention', 'dm', 'thread_reply', 'guest_triage')),
                untrusted_envelope INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                read_at REAL,
                delivered_at REAL
            );
            """
        )
    store = SlackBoardStore(legacy_db)
    secret = ensure_local_secret(tmp_path / "local.secret")

    # 1. Default coordinators list is ['front-man'] only!
    assert store.get_guest_coordinators() == ["front-man"]

    owner = store.ensure_owner_principal("henry", "Henry Fontanier", tailscale_login="owner@example.test")
    store.register_principal("front-man", "front-man", "agent", "worker")
    store.register_principal("jim-macbook-1", "jim-macbook-1", "agent", "worker")
    store.register_principal("carbon-god", "carbon-god", "agent", "worker")
    store.configure_guest_channel(owner["id"], "fork-sync")

    # Non-owner worker cannot change guest_coordinators
    with pytest.raises(PermissionDenied):
        store.configure_guest_coordinators("carbon-god", ["carbon-god"])

    # Owner configures ['front-man', 'jim-macbook-1']
    coords = store.configure_guest_coordinators("henry", ["front-man", "jim-macbook-1"])
    assert coords == ["front-man", "jim-macbook-1"]

    # Register two guest agents on Paul's account
    store.register_principal("guest:paul/agent-a", "paul/agent-a", "agent", "guest", guest_channel_id="fork-sync", tailscale_user_id="1139")
    store.register_principal("guest:paul/agent-b", "paul/agent-b", "agent", "guest", guest_channel_id="fork-sync", tailscale_user_id="1139")

    # 2. Guest posts attempting to wake @carbon-god, @jim-macbook-1, and @front-man:
    #    - front-man and jim-macbook-1 BOTH wake with untrusted_envelope == 1
    #    - non-listed worker carbon-god gets ZERO wakeups!
    #    - guest:paul/agent-a does NOT wake on its own post, while guest:paul/agent-b wakes via 'channel_post'!
    g_msg = store.post_message("guest:paul/agent-a", "fork-sync", "@carbon-god @jim-macbook-1 @front-man branch ready")
    assert store.pending_agent_wakeups("carbon-god") == []
    fm_w = store.pending_agent_wakeups("front-man")
    jm1_w = store.pending_agent_wakeups("jim-macbook-1")
    assert len(fm_w) == 1 and fm_w[0]["kind"] == "guest_triage" and fm_w[0]["untrusted_envelope"] == 1
    assert len(jm1_w) == 1 and jm1_w[0]["kind"] == "guest_triage" and jm1_w[0]["untrusted_envelope"] == 1
    assert store.pending_agent_wakeups("guest:paul/agent-a") == []
    ab_w = store.pending_agent_wakeups("guest:paul/agent-b")
    assert len(ab_w) == 1 and ab_w[0]["kind"] == "channel_post"
    assert store.pending_agent_wakeups("guest:paul/agent-b", addressed_only=True) == []

    # 3. Coordinator replies in guest's thread -> guest:paul/agent-a wakes with 'thread_reply',
    #    and @mentioning `@agent-b` by short handle wakes guest:paul/agent-b with 'mention'!
    store.post_message("jim-macbook-1", "fork-sync", "Reviewed — @agent-b please check LODs too", root_id=g_msg["id"])
    aa_w = store.pending_agent_wakeups("guest:paul/agent-a")
    assert len(aa_w) == 1 and aa_w[0]["kind"] == "thread_reply"
    ab_w2 = store.pending_agent_wakeups("guest:paul/agent-b", after_notif_id=ab_w[-1]["notif_id"], addressed_only=True)
    assert len(ab_w2) == 1 and ab_w2[0]["kind"] == "mention"

    # 4. Live HTTP check: a guest CANNOT read another principal's wakeups via /api/wakeups,
    #    framing smuggling on /api/wakeups gets 400 + close, and long-poll stream cap returns 429!
    # Also create an internal mention for front-man in #general
    store.post_message("henry", "general", "Secret internal ping @front-man")

    whois_map = {
        "100.64.0.1": WhoisIdentity("node-owner-mac", f"owner-macbook{TEST_SUFFIX}", False, "6163001", "owner@example.test", "Henry Fontanier"),
        "100.64.0.22": WhoisIdentity("node-paul-air", f"macbook-air{TEST_SUFFIX}", False, "1139", "paul@example.test", "Paul"),
    }
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    hub = EventHub(max_subscribers=16, max_per_viewer=2, queue_size=8)
    handler = make_handler(store, Path(__file__).resolve().parent.parent / "harness" / "board_web_assets", hub, local_secret=secret, port=port, ts_cfg=TEST_TS_CFG, whois_fn=whois_map.get)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        # Guest agent-a tries ?viewer=front-man&recipient=henry -> STILL only gets guest:paul/agent-a's own wakeups!
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request(
            "GET",
            "/api/wakeups?after=0&timeout=0&viewer=front-man&recipient=henry",
            headers={
                "Host": f"owner-macbook{TEST_SUFFIX}:{port}",
                "X-Forwarded-For": "100.64.0.22",
                "X-Atelier-Agent": "agent-a",
            },
        )
        r = c.getresponse()
        body = json.loads(r.read().decode("utf-8"))
        c.close()
        assert r.status == 200
        assert body["viewer_id"] == "guest:paul/agent-a"
        assert all(w["channel_id"] == "fork-sync" for w in body["wakeups"])
        assert not any("Secret internal ping" in w["body"] for w in body["wakeups"])

        # GET /api/wakeups with a body is rejected with 400 and Connection: close (1 response only!)
        s_smug = socket.create_connection(("127.0.0.1", port), timeout=3)
        s_smug.sendall(
            f"GET /api/wakeups?after=0 HTTP/1.1\r\nHost: owner-macbook{TEST_SUFFIX}:{port}\r\n"
            f"X-Forwarded-For: 100.64.0.22\r\nContent-Length: 4\r\n\r\ntest".encode()
        )
        raw_smug = s_smug.recv(2048).decode("utf-8", errors="replace")
        s_smug.close()
        assert raw_smug.count("HTTP/1.1 ") == 1 and "400" in raw_smug.splitlines()[0]

        # Exceeding max_per_viewer=2 concurrent blocking long-polls returns 429 for guest while owner still gets 200!
        assert hub.acquire_longpoll("guest:paul/agent-a") is True
        assert hub.acquire_longpoll("guest:paul/agent-a") is True
        c429 = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c429.request(
            "GET",
            "/api/wakeups?after=9999&timeout=1",
            headers={
                "Host": f"owner-macbook{TEST_SUFFIX}:{port}",
                "X-Forwarded-For": "100.64.0.22",
                "X-Atelier-Agent": "agent-a",
            },
        )
        r429 = c429.getresponse()
        r429.read()
        c429.close()
        assert r429.status == 429
        hub.release_longpoll("guest:paul/agent-a")
        hub.release_longpoll("guest:paul/agent-a")
    finally:
        httpd.shutdown()
        httpd.server_close()
