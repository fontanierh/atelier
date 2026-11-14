"""End-to-end security, Tailscale UserProfile auth, and SSE DM push tests for `slack_board`."""
from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from atelier.harness.slack_board import (
    EventHub,
    PermissionDenied,
    SlackBoardStore,
    TailnetConfig,
    WhoisIdentity,
    _csrf_token_for,
    ensure_local_secret,
    make_handler,
    resolve_request_caller,
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


def test_tailscale_user_login_resolves_owner_across_devices_and_guests_by_account(tmp_path: Path) -> None:
    store = SlackBoardStore(tmp_path / "board.sqlite3")
    secret = ensure_local_secret(tmp_path / "local.secret")

    whois_table = {
        "100.64.0.1": WhoisIdentity("node-owner-mac", f"owner-macbook{TEST_SUFFIX}", False, "6163001", "owner@example.test", "Henry Fontanier"),
        "100.64.0.2": WhoisIdentity("node-owner-lap2", f"owner-laptop2{TEST_SUFFIX}", False, "6163001", "owner@example.test", "Henry Fontanier"),
        "100.64.0.10": WhoisIdentity("node-paul-air", f"macbook-air{TEST_SUFFIX}", False, "1139002", "paul@example.test", "Paul"),
        "100.64.0.11": WhoisIdentity("node-paul2-pro", f"other-laptop{TEST_SUFFIX}", False, "9999003", "paul.other@example.test", "Paul"),
        "100.64.0.99": WhoisIdentity("node-tagged-vm", f"bot-vm{TEST_SUFFIX}", True, "", "", ""),
    }

    # 1. Owner connecting from two different personal devices gets the same Tailscale human principal ('henry')
    for ip in ("100.64.0.1", "100.64.0.2"):
        vid, sec = resolve_request_caller(
            store,
            client_ip="127.0.0.1",
            headers={
                "Host": f"owner-macbook{TEST_SUFFIX}",
                "X-Forwarded-For": ip,
                "Tailscale-User-Login": "owner@example.test",
                "Tailscale-User-Name": "Henry Fontanier",
            },
            qs={},
            local_secret=secret,
            ts_cfg=TEST_TS_CFG,
            whois_fn=whois_table.get,
        )
        assert vid == "henry"
        assert sec["tier"] == "owner_device"
        assert store.get_bootstrap(vid)["viewer"]["display_name"] == "Henry Fontanier"

    # 1b. By default (before owner designates an external guest channel), external Tailscale accounts are denied!
    with pytest.raises(PermissionDenied):
        resolve_request_caller(
            store,
            client_ip="127.0.0.1",
            headers={
                "Host": f"owner-macbook{TEST_SUFFIX}",
                "X-Forwarded-For": "100.64.0.10",
                "Tailscale-User-Login": "paul@example.test",
                "Tailscale-User-Name": "Paul",
            },
            qs={},
            local_secret=secret,
            ts_cfg=TEST_TS_CFG,
            whois_fn=whois_table.get,
        )

    # Owner designates a custom external guest channel ('partner-bridge')
    store.configure_guest_channel("henry", "partner-bridge")

    # 2. External collaborator ('paul@example.test' / 'Paul') automatically logs in as Single-Channel Guest 'guest:paul' in #partner-bridge
    vid_paul, sec_paul = resolve_request_caller(
        store,
        client_ip="127.0.0.1",
        headers={
            "Host": f"owner-macbook{TEST_SUFFIX}",
            "X-Forwarded-For": "100.64.0.10",
            "Tailscale-User-Login": "paul@example.test",
            "Tailscale-User-Name": "Paul",
        },
        qs={},
        local_secret=secret,
        ts_cfg=TEST_TS_CFG,
        whois_fn=whois_table.get,
    )
    assert vid_paul == "guest:paul"
    assert sec_paul["tier"] == "tailnet_guest"
    assert sec_paul["guest_jailed"] is True
    paul_boot = store.get_bootstrap(vid_paul)
    assert paul_boot["viewer"]["display_name"] == "Paul"
    assert [c["id"] for c in paul_boot["channels"]] == ["partner-bridge"]

    # 3. Agent on Paul's machine gets 'guest:paul/train-agent' jailed to #partner-bridge
    vid_ag, _ = resolve_request_caller(
        store,
        client_ip="127.0.0.1",
        headers={
            "Host": f"owner-macbook{TEST_SUFFIX}",
            "X-Forwarded-For": "100.64.0.10",
            "X-Atelier-Agent": "train-agent",
        },
        qs={},
        local_secret=secret,
        ts_cfg=TEST_TS_CFG,
        whois_fn=whois_table.get,
    )
    assert vid_ag == "guest:paul/train-agent"

    # 4. A DIFFERENT Tailscale user also named Paul never overwrites 'guest:paul'
    vid_paul2, _ = resolve_request_caller(
        store,
        client_ip="127.0.0.1",
        headers={
            "Host": f"owner-macbook{TEST_SUFFIX}",
            "X-Forwarded-For": "100.64.0.11",
            "Tailscale-User-Login": "paul.other@example.test",
            "Tailscale-User-Name": "Paul",
        },
        qs={},
        local_secret=secret,
        ts_cfg=TEST_TS_CFG,
        whois_fn=whois_table.get,
    )
    assert vid_paul2 != vid_paul and vid_paul2.startswith("guest:paul-")

    # 5. Spoofed Tailscale-User-Login header mismatching whois UserProfile fails closed!
    with pytest.raises(PermissionDenied):
        resolve_request_caller(
            store,
            client_ip="127.0.0.1",
            headers={
                "Host": f"owner-macbook{TEST_SUFFIX}",
                "X-Forwarded-For": "100.64.0.10",
                "Tailscale-User-Login": "owner@example.test",
            },
            qs={},
            local_secret=secret,
            ts_cfg=TEST_TS_CFG,
            whois_fn=whois_table.get,
        )

    # 6. ACL-tagged server/VM node cannot claim human board access
    with pytest.raises(PermissionDenied):
        resolve_request_caller(
            store,
            client_ip="127.0.0.1",
            headers={"Host": f"owner-macbook{TEST_SUFFIX}", "X-Forwarded-For": "100.64.0.99"},
            qs={},
            local_secret=secret,
            ts_cfg=TEST_TS_CFG,
            whois_fn=whois_table.get,
        )


def test_csrf_and_origin_validation() -> None:
    secret = "s" * 44
    valid_csrf = _csrf_token_for(secret, "henry")

    with pytest.raises(PermissionDenied):
        validate_post_security(
            {"Content-Type": "text/plain"},
            tier="owner_device",
            viewer_id="henry",
            local_secret=secret,
            port=8890,
            ts_cfg=TEST_TS_CFG,
        )

    with pytest.raises(PermissionDenied):
        validate_post_security(
            {
                "Content-Type": "application/json",
                "Origin": "https://evil.example",
                "X-Atelier-CSRF": valid_csrf,
            },
            tier="owner_device",
            viewer_id="henry",
            local_secret=secret,
            port=8890,
            ts_cfg=TEST_TS_CFG,
        )

    with pytest.raises(PermissionDenied):
        validate_post_security(
            {
                "Content-Type": "application/json",
                "Origin": f"https://owner-macbook{TEST_SUFFIX}",
            },
            tier="owner_device",
            viewer_id="henry",
            local_secret=secret,
            port=8890,
            ts_cfg=TEST_TS_CFG,
        )

    validate_post_security(
        {
            "Content-Type": "application/json",
            "Origin": f"https://owner-macbook{TEST_SUFFIX}",
            "X-Atelier-CSRF": valid_csrf,
        },
        tier="owner_device",
        viewer_id="henry",
        local_secret=secret,
        port=8890,
        ts_cfg=TEST_TS_CFG,
    )


def test_live_http_sse_guest_isolation_and_dm_browser_notification_payload(tmp_path: Path) -> None:
    store = SlackBoardStore(tmp_path / "e2e.sqlite3")
    secret = ensure_local_secret(tmp_path / "local.secret")
    assets = Path(__file__).resolve().parent.parent / "harness" / "board_web_assets"
    hub = EventHub()

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
    srv_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    srv_thread.start()

    guest_events: list[dict] = []
    owner_events: list[dict] = []

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
        def req(method: str, path: str, headers: dict[str, str], body: dict | None = None) -> tuple[int, dict]:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            raw = json.dumps(body).encode("utf-8") if body is not None else None
            c.request(method, path, body=raw, headers=headers)
            r = c.getresponse()
            data = json.loads(r.read().decode("utf-8") or "{}")
            c.close()
            return r.status, data

        # Direct loopback bootstrap resolves owner ('henry')
        st_lb, lb_boot = req("GET", "/api/bootstrap", {"Host": f"127.0.0.1:{port}"})
        assert st_lb == 200 and lb_boot["viewer"]["id"] == "henry"
        owner_csrf = lb_boot["csrf_token"]

        # Human opts in to native DM browser notifications
        st_pref, pref_res = req(
            "POST",
            "/api/preferences/notifications",
            {
                "Host": f"127.0.0.1:{port}",
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{port}",
                "X-Atelier-CSRF": owner_csrf,
            },
            {"dm_browser_notify": True},
        )
        assert st_pref == 200 and pref_res["dm_browser_notify"] is True

        guest_hdrs = {
            "Host": f"owner-macbook{TEST_SUFFIX}:{port}",
            "X-Forwarded-For": "100.64.0.22",
            "Tailscale-User-Login": "paul@example.test",
            "Tailscale-User-Name": "Paul",
        }
        owner_hdrs = {
            "Host": f"owner-macbook{TEST_SUFFIX}:{port}",
            "X-Forwarded-For": "100.64.0.1",
            "Tailscale-User-Login": "owner@example.test",
            "Tailscale-User-Name": "Henry Fontanier",
        }

        # Enable custom guest channel 'partner-bridge' via owner API
        st_cfg, cfg_res = req(
            "POST",
            "/api/settings/guest-channel",
            {
                "Host": f"127.0.0.1:{port}",
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{port}",
                "X-Atelier-CSRF": owner_csrf,
            },
            {"channel_id": "partner-bridge"},
        )
        assert st_cfg == 200 and cfg_res["default_guest_channel_id"] == "partner-bridge"
        store.create_channel("henry", "lead-ops", "private", topic="Private ops", member_ids=["front-man"])

        st_g, g_boot = req("GET", "/api/bootstrap", guest_hdrs)
        assert st_g == 200 and g_boot["viewer"]["id"] == "guest:paul"
        assert [c["id"] for c in g_boot["channels"]] == ["partner-bridge"]

        # Open SSE sockets for both Guest and Owner
        threading.Thread(target=sse_reader, args=(guest_hdrs, guest_events), daemon=True).start()
        threading.Thread(target=sse_reader, args=(owner_hdrs, owner_events), daemon=True).start()
        time.sleep(0.15)

        # Local agent posts an internal message in #lead-ops -> Owner receives SSE, Guest receives ZERO!
        st_p1, _ = req(
            "POST",
            "/api/messages",
            {
                "Host": f"127.0.0.1:{port}",
                "Authorization": f"Bearer {secret}",
                "X-Atelier-Agent": "front-man",
                "Content-Type": "application/json",
            },
            {"channel_id": "lead-ops", "body": "Internal release key stays private."},
        )
        assert st_p1 == 201

        # Local agent sends a scarce Direct Message to human owner -> Owner SSE gets `channel_kind == 'dm'` + message!
        st_dm, _ = req(
            "POST",
            "/api/messages",
            {
                "Host": f"127.0.0.1:{port}",
                "Authorization": f"Bearer {secret}",
                "X-Atelier-Agent": "carbon-god",
                "Content-Type": "application/json",
            },
            {"channel_id": "", "dm_peer": "henry", "body": "Need keychain approval to notarize macOS bundle."},
        )
        assert st_dm == 201
        time.sleep(0.15)

        assert guest_events == []
        dm_sse = [ev for ev in owner_events if ev.get("channel_kind") == "dm"]
        assert len(dm_sse) == 1
        assert dm_sse[0]["kind"] == "message.created"
        assert dm_sse[0]["message"]["author_id"] == "carbon-god"
        assert "notarize" in dm_sse[0]["message"]["body"]

        # Guest cannot read internal channel or post outside #partner-bridge
        st_forb, _ = req("GET", "/api/channels/lead-ops/messages", guest_hdrs)
        assert st_forb == 403
    finally:
        httpd.shutdown()
        httpd.server_close()
