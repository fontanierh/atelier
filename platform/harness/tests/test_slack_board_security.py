import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from harness.slack_board import (
    TailnetConfig,
    PermissionDenied,
    SlackBoardStore,
    make_csrf_token,
    make_handler,
    resolve_request_caller,
    seed_workspace,
    )

TEST_CFG = TailnetConfig(
    suffix=".net.example.test",
    host_dns="jims-macbook-pro.net.example.test",
    owner_stable_ids=frozenset({"nBtkCH518d11CNTRL"}),
    owner_nodes=frozenset({"jims-macbook-pro.net.example.test"}),
)
ASSETS_DIR = Path(__file__).resolve().parent.parent / "harness/board_web_assets"

FAKE_PEERS = {
    "100.121.116.92": {
        "stable_id": "nBtkCH518d11CNTRL",
        "node_name": "jims-macbook-pro.net.example.test",
        "ok": True,
    },
    "100.88.1.1": {
        "stable_id": "ngmyv2RqAS11CNTRL",
        "node_name": "henrys-macbook-pro.net.example.test",
        "ok": True,
    },
    "100.88.1.2": {
        "stable_id": "nBWngVD9EW11CNTRL",
        "node_name": "henrys-macbook-pro-rex.net.example.test",
        "ok": True,
    },
    "100.88.1.3": {
        "stable_id": "nAkjPRbNSg11CNTRL",
        "node_name": "carbon-god.net.example.test",  # Hostname colliding with internal worker 'carbon-god'!
        "ok": True,
    },
}


def fake_whois(ip: str) -> dict:
    return FAKE_PEERS.get(ip, {"stable_id": "", "node_name": "", "ok": False})


@pytest.fixture()
def store(tmp_path):
    s = SlackBoardStore(tmp_path / "board.sqlite3")
    seed_workspace(s)
    return s


@pytest.fixture()
def live_http(store):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), lambda *a, **kw: None)
    port = srv.server_address[1]
    srv.RequestHandlerClass = make_handler(store, ASSETS_DIR, port=port, ts_cfg=TEST_CFG, whois_fn=fake_whois)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield port
    finally:
        srv.shutdown()
        srv.server_close()


def test_unresolved_or_missing_stable_id_fails_closed(store):
    with pytest.raises(PermissionDenied, match="Unverified Tailscale peer"):
        resolve_request_caller(
            client_ip="127.0.0.1",
            headers={"Host": "jims-macbook-pro.net.example.test:8142", "X-Forwarded-For": "100.64.99.99"},
            qs={"viewer": ["jim"]},
            local_secret="s" * 40,
            port=8142,
            store=store,
            ts_cfg=TEST_CFG,
            whois_fn=fake_whois,
        )

    # Even if node_name matches owner DNS, missing/mismatched StableID cannot gain owner role!
    caller_id, sec = resolve_request_caller(
        client_ip="127.0.0.1",
        headers={"Host": "jims-macbook-pro.net.example.test:8142", "X-Forwarded-For": "100.88.9.9"},
        qs={"viewer": ["jim"]},
        local_secret="s" * 40,
        port=8142,
        store=store,
        ts_cfg=TEST_CFG,
        whois_fn=lambda _ip: {
            "stable_id": "nSPOOFED9999CNTRL",
            "node_name": "jims-macbook-pro.net.example.test",
            "ok": True,
        },
    )
    assert caller_id == "guest:nSPOOFED9999CNTRL"
    assert sec["caller_tier"] == "tailnet_guest"


def test_namespace_separation_and_collision_rejection(store):
    # 1. Internal enrollment rejects reserved 'guest*' or ':' identifiers
    with pytest.raises(PermissionDenied, match="Reserved or invalid"):
        store.ensure_internal_agent("guest:ngmyv2RqAS11CNTRL")
    with pytest.raises(PermissionDenied, match="Reserved or invalid"):
        store.ensure_internal_agent("guest-foo")

    # 2. External node named 'carbon-god' (colliding with existing internal worker 'carbon-god')
    # maps into disjoint 'guest:nAkjPRbNSg11CNTRL' and NEVER inherits internal worker role!
    caller_id, sec = resolve_request_caller(
        client_ip="127.0.0.1",
        headers={"Host": "jims-macbook-pro.net.example.test:8142", "X-Forwarded-For": "100.88.1.3"},
        qs={},
        local_secret="s" * 40,
        port=8142,
        store=store,
        ts_cfg=TEST_CFG,
        whois_fn=fake_whois,
    )
    assert caller_id == "guest:nAkjPRbNSg11CNTRL"
    assert sec["caller_tier"] == "tailnet_guest"
    assert store.principal("carbon-god")["role"] == "worker"
    assert store.principal(caller_id)["role"] == "guest"

    # 3. Direct DB tamper test: if a non-guest row ever squatted on a 'guest:<id>' key, ensure_guest_principal refuses!
    with store._connect() as conn:
        conn.execute(
            """INSERT INTO principals (id, display_name, kind, role, host, status, status_text, guest_channel_id, stable_node_id, hue)
               VALUES ('guest:nCOLLIDE123', 'Squatter', 'agent', 'worker', 'jim-mbp', 'active', '', NULL, NULL, 'ice')"""
        )
    with pytest.raises(PermissionDenied, match="collision rejected"):
        store.ensure_guest_principal(stable_id="nCOLLIDE123", short_host="bad")


def test_two_henry_nodes_get_distinct_stable_id_principals(store):
    c1, _ = resolve_request_caller(
        client_ip="127.0.0.1",
        headers={"Host": "jims-macbook-pro.net.example.test:8142", "X-Forwarded-For": "100.88.1.1"},
        qs={},
        local_secret="s" * 40,
        port=8142,
        store=store,
        ts_cfg=TEST_CFG,
        whois_fn=fake_whois,
    )
    c2, _ = resolve_request_caller(
        client_ip="127.0.0.1",
        headers={"Host": "jims-macbook-pro.net.example.test:8142", "X-Forwarded-For": "100.88.1.2"},
        qs={},
        local_secret="s" * 40,
        port=8142,
        store=store,
        ts_cfg=TEST_CFG,
        whois_fn=fake_whois,
    )
    assert c1 == "guest:ngmyv2RqAS11CNTRL"
    assert c2 == "guest:nBWngVD9EW11CNTRL"
    assert c1 != c2


def test_end_to_end_http_and_sse_guest_isolation(live_http, store):
    port = live_http
    ts_host = f"jims-macbook-pro.net.example.test:{port}"
    ts_origin = f"https://{ts_host}"

    def req(method: str, path: str, headers: dict, body: bytes = b"") -> tuple[int, dict]:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            return resp.status, json.loads(raw.decode("utf-8")) if raw else {}
        finally:
            conn.close()

    # 1. Guest bootstrap over HTTP (even when passing ?viewer=jim!) is forced into guest:ngmyv2RqAS11CNTRL in #fork-sync only
    st, g_boot = req("GET", "/api/bootstrap?viewer=jim", {"Host": ts_host, "X-Forwarded-For": "100.88.1.1"})
    assert st == 200
    assert g_boot["viewer"]["id"] == "guest:ngmyv2RqAS11CNTRL"
    assert g_boot["viewer"]["role"] == "guest"
    assert [c["id"] for c in g_boot["channels"]] == ["fork-sync"]
    assert g_boot["explorable_channels"] == []
    guest_csrf = g_boot["csrf_token"]

    # 2. Guest HTTP read on #lead-ops and #world-build -> 403 Forbidden
    st_priv, _ = req("GET", "/api/channels/lead-ops/messages", {"Host": ts_host, "X-Forwarded-For": "100.88.1.1"})
    st_pub, _ = req("GET", "/api/channels/world-build/messages", {"Host": ts_host, "X-Forwarded-For": "100.88.1.1"})
    assert st_priv == 403 and st_pub == 403

    # 3. Cross-origin POST & wrong Content-Type POST over HTTP -> 403 Forbidden
    st_cors, _ = req(
        "POST",
        "/api/messages",
        {
            "Host": ts_host,
            "X-Forwarded-For": "100.121.116.92",
            "Origin": "https://evil.example",
            "Content-Type": "application/json",
            "X-Atelier-CSRF": make_csrf_token("owner_device", "jim"),
        },
        json.dumps({"author_id": "jim", "channel_id": "general", "body": "csrf"}).encode(),
    )
    assert st_cors == 403
    st_plain, _ = req(
        "POST",
        "/api/messages",
        {
            "Host": ts_host,
            "X-Forwarded-For": "100.121.116.92",
            "Origin": ts_origin,
            "Content-Type": "text/plain",
            "X-Atelier-CSRF": make_csrf_token("owner_device", "jim"),
        },
        json.dumps({"author_id": "jim", "channel_id": "general", "body": "csrf"}).encode(),
    )
    st_nocsrf, _ = req(
        "POST",
        "/api/messages",
        {
            "Host": ts_host,
            "X-Forwarded-For": "100.121.116.92",
            "Origin": ts_origin,
            "Content-Type": "application/json",
        },
        json.dumps({"author_id": "jim", "channel_id": "general", "body": "csrf"}).encode(),
    )
    assert st_plain == 403 and st_nocsrf == 403

    # 4. End-to-End Live TCP SSE Stream Isolation:
    # Open live SSE stream as Guest (100.88.1.1) and Owner (100.121.116.92) simultaneously!
    guest_sse = http.client.HTTPConnection("127.0.0.1", port, timeout=1.2)
    owner_sse = http.client.HTTPConnection("127.0.0.1", port, timeout=1.2)
    try:
        guest_sse.request("GET", "/api/events", headers={"Host": ts_host, "X-Forwarded-For": "100.88.1.1"})
        owner_sse.request("GET", "/api/events", headers={"Host": ts_host, "X-Forwarded-For": "100.121.116.92"})
        g_resp = guest_sse.getresponse()
        o_resp = owner_sse.getresponse()
        assert g_resp.status == 200 and o_resp.status == 200
        assert b": connected" in g_resp.fp.readline()
        assert b": connected" in o_resp.fp.readline()

        # Owner posts in private #lead-ops via real HTTP POST -> Owner SSE gets event, Guest SSE MUST NOT!
        _, o_boot = req("GET", "/api/bootstrap", {"Host": ts_host, "X-Forwarded-For": "100.121.116.92"})
        st_post_priv, _ = req(
            "POST",
            "/api/messages",
            {
                "Host": ts_host,
                "X-Forwarded-For": "100.121.116.92",
                "Origin": ts_origin,
                "Content-Type": "application/json",
                "X-Atelier-CSRF": o_boot["csrf_token"],
            },
            json.dumps({"author_id": "jim", "channel_id": "lead-ops", "body": "Top secret merge gate"}).encode(),
        )
        assert st_post_priv == 201
        def read_sse_frame(resp):
            lines = []
            while True:
                ln = resp.fp.readline()
                if not ln:
                    break
                if ln == b"\n":
                    if lines:
                        break
                    continue
                lines.append(ln)
            return b"".join(lines)

        o_frame = read_sse_frame(o_resp)
        assert b"event: sync" in o_frame and b"lead-ops" in o_frame

        # Guest posts in #fork-sync attempting author_id='jim' & @carbon-god wakeup:
        # -> Author forced to guest:ngmyv2RqAS11CNTRL, untrusted_guest=True, 0 worker wakeups, and Guest SSE ONLY sees #fork-sync!
        st_gpost, gpost_res = req(
            "POST",
            "/api/messages",
            {
                "Host": ts_host,
                "X-Forwarded-For": "100.88.1.1",
                "Origin": ts_origin,
                "Content-Type": "application/json",
                "X-Atelier-CSRF": guest_csrf,
            },
            json.dumps({"author_id": "jim", "channel_id": "fork-sync", "body": "Hi @carbon-god"}).encode(),
        )
        assert st_gpost == 201
        assert gpost_res["message"]["author_id"] == "guest:ngmyv2RqAS11CNTRL"
        assert gpost_res["message"]["untrusted_guest"] is True

        g_frame = read_sse_frame(g_resp)
        assert b"event: sync" in g_frame
        assert b"lead-ops" not in g_frame and b"fork-sync" in g_frame
    finally:
        guest_sse.close()
        owner_sse.close()
