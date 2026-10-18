#!/usr/bin/env python3
"""Suno client using the web refresh cookie.

Config (mode 0600):
  ~/.cache/suno/refresh.json  {"client": "...", "client_uat": "..."}
Outputs:
  ~/.cache/suno/out/
"""
import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import requests
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

CACHE = Path.home() / ".cache/suno"
REFRESH = CACHE / "refresh.json"
SESSION = CACHE / "session.json"
OUT = CACHE / "out"
ENV = Path(os.environ.get("ATELIER_ENV", Path(__file__).resolve().parents[3] / ".env"))
API = "https://studio-api-prod.suno.com"
AUTH = "https://auth.suno.com"
PARAMS = {"__clerk_api_version": "2025-11-10", "_clerk_js_version": "5.117.0"}
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/155.0.8059.82 Safari/537.36")
TURNSTILE_SITEKEY = "0x4AAAAAADI7xDNyj-3LcIbi"


def write_private(path, data):
    path.write_text(data)
    os.chmod(path, 0o600)


def read_env_refresh():
    if not ENV.exists():
        return None
    values = {}
    for line in ENV.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, value = s.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    client = values.get("SUNO_CLIENT_COOKIE")
    uat = values.get("SUNO_CLIENT_UAT")
    if client and uat:
        return client, uat
    return None


def save_env_refresh(client, uat):
    lines = ENV.read_text().splitlines() if ENV.exists() else []
    keys = {"SUNO_CLIENT_COOKIE": client, "SUNO_CLIENT_UAT": uat}
    out = []
    seen = set()
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if key in keys:
            out.append(key + "=" + keys[key])
            seen.add(key)
        else:
            out.append(line)
    for key, value in keys.items():
        if key not in seen:
            out.append(key + "=" + value)
    ENV.write_text("\n".join(out).rstrip() + "\n")
    os.chmod(ENV, 0o600)


def read_refresh():
    env = read_env_refresh()
    if env:
        return env
    ref = json.loads(REFRESH.read_text())
    return ref["client"], ref["client_uat"]


def save_refresh(client, uat):
    write_private(REFRESH, json.dumps({"client": client, "client_uat": uat}))
    try:
        save_env_refresh(client, uat)
    except OSError:
        pass


def refresh_access_token():
    """Exchange the long-lived __client refresh cookie for a one-hour JWT."""
    client, uat = read_refresh()
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Origin": "https://suno.com"})
    s.cookies.set("__client", client, domain="auth.suno.com", path="/")
    s.cookies.set("__client_uat", uat, domain=".suno.com", path="/")

    def persist():
        got_client = None
        got_uat = None
        for c in s.cookies:
            if c.name == "__client" and c.domain.endswith("auth.suno.com"):
                got_client = c.value
            elif c.name == "__client_uat" and c.domain.endswith("suno.com"):
                got_uat = c.value
        if got_client and got_uat:
            save_refresh(got_client, got_uat)

    r = s.get(AUTH + "/v1/client", params=PARAMS, timeout=30)
    r.raise_for_status()
    persist()
    data = r.json().get("response", {})
    sid = data.get("last_active_session_id")
    if not sid:
        active = [x for x in data.get("sessions", []) if x.get("status") == "active"]
        if not active:
            raise SystemExit("No active Suno session. Re-copy __client from the browser.")
        sid = active[0]["id"]
    r = s.post(AUTH + f"/v1/client/sessions/{sid}/tokens", params=PARAMS, timeout=30)
    r.raise_for_status()
    persist()
    jwt = r.json()["jwt"]
    exp = time.time() + 3600
    try:
        part = jwt.split(".")[1]
        part += "=" * (-len(part) % 4)
        exp = json.loads(base64.urlsafe_b64decode(part)).get("exp", exp)
    except Exception:
        pass
    write_private(SESSION, json.dumps({"session": jwt, "session_exp": exp}))
    return jwt


def turnstile_token():
    """Render Suno's generation Turnstile widget in the local Chrome on :9223."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("Playwright is required for generation: pip install playwright")
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9223")
        except Exception as e:
            raise RuntimeError(
                "Chrome debug port 9223 is not available. Start "
                "'Google Chrome --remote-debugging-port=9223 --user-data-dir=~/.cache/suno/chrome-profile'."
            ) from e
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if "suno.com" not in page.url:
            page.goto("https://suno.com/create", wait_until="domcontentloaded", timeout=60000)
            time.sleep(2)
        wid = "ts-" + uuid.uuid4().hex[:8]
        page.evaluate("""(args) => {
          const [wid, sitekey] = args;
          window.__tsToken = null; window.__tsError = null;
          const d = document.createElement('div');
          d.id = wid;
          d.style.position = 'fixed'; d.style.top = '10px'; d.style.left = '10px';
          d.style.zIndex = '2147483647';
          document.body.appendChild(d);
          const start = () => { window.__tsWidget = window.turnstile.render('#' + wid, {
            sitekey: sitekey,
            callback: t => { window.__tsToken = t; },
            'error-callback': e => { window.__tsError = String(e); },
            size: 'normal', theme: 'light', appearance: 'always'
          }); };
          if (window.turnstile) start();
          else {
            const s = document.createElement('script');
            s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
            s.async = true; s.defer = true; s.onload = start;
            s.onerror = () => { window.__tsError = 'script_load_failed'; };
            document.head.appendChild(s);
          }
        }""", [wid, TURNSTILE_SITEKEY])
        for _ in range(30):
            time.sleep(1)
            state = page.evaluate("() => ({t: window.__tsToken, e: window.__tsError})")
            if state.get("t"):
                try:
                    page.evaluate("(wid) => { if (window.__tsWidget) { turnstile.remove(window.__tsWidget); window.__tsWidget = null; } const d = document.getElementById(wid); if (d) d.remove(); }", wid)
                except Exception:
                    pass
                return state["t"]
            if state.get("e"):
                try:
                    page.goto("https://suno.com/create", wait_until="domcontentloaded", timeout=60000)
                except Exception:
                    pass
                raise RuntimeError(f"Turnstile failed: {state['e']}")
        try:
            page.goto("https://suno.com/create", wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass
        raise RuntimeError("Turnstile did not issue a token")


class Suno:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA, "Origin": "https://suno.com",
            "Referer": "https://suno.com/", "Accept": "application/json, text/plain, */*",
        })
        self.token = None
        try:
            saved = json.loads(SESSION.read_text())
            if saved.get("session_exp", 0) > time.time() + 300:
                self.token = saved["session"]
        except Exception:
            pass

    def auth(self):
        self.token = refresh_access_token()
        return self.token

    def api(self, method, path, **kwargs):
        if not self.token:
            self.auth()
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {self.token}"
        timeout = kwargs.pop("timeout", 60)
        r = self.session.request(method, API + path, headers=headers, timeout=timeout, **kwargs)
        if r.status_code == 401:
            self.auth()
            headers["Authorization"] = f"Bearer {self.token}"
            r = self.session.request(method, API + path, headers=headers, timeout=timeout, **kwargs)
        return r

    def billing(self):
        r = self.api("GET", "/api/billing/info/")
        r.raise_for_status()
        return r.json()

    def feed(self, ids=None):
        params = {"ids": ",".join(ids)} if ids else {}
        r = self.api("GET", "/api/feed/v2", params=params)
        r.raise_for_status()
        return r.json().get("clips", [])

    def clip(self, clip_id):
        r = self.api("GET", f"/api/clip/{clip_id}")
        r.raise_for_status()
        return r.json()

    def generate(self, prompt, instrumental=False, model="chirp-hawk",
                 title="", tags="", lyrics="", duration=480, negative_tags=""):
        captcha = turnstile_token()
        body = {
            "prompt": lyrics, "title": title,
            "gpt_description_prompt": "" if lyrics else prompt,
            "make_instrumental": instrumental, "mv": model,
            "generation_type": "TEXT", "metadata": {},
            "negative_tags": negative_tags,
            "token": captcha, "token_provider": 2,
            "task": None, "project_id": None, "override_fields": [],
            "duration": duration, "edit_session_id": None,
            "transaction_uuid": str(uuid.uuid4()),
        }
        if lyrics:
            body["tags"] = tags
        r = self.api("POST", "/api/generate/v2-web/", json=body, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"generate failed {r.status_code}: {r.text[:500]}")
        return r.json()

    def wait(self, ids, timeout=300, interval=5):
        deadline = time.time() + timeout
        last = []
        while time.time() < deadline:
            last = self.feed(ids)
            print("status:", [c.get("status") for c in last], flush=True)
            if last and all(c.get("status") in ("complete", "error") for c in last):
                return last
            time.sleep(interval)
        return last

    def download(self, clip_id, to_mp3=True):
        c = self.clip(clip_id)
        title = c.get("title") or clip_id
        media = c.get("media_urls") or []
        if not media:
            raise RuntimeError("clip has no media_urls (download may be locked)")
        url = media[0]["url"]
        encrypted = self.session.get(url, timeout=120)
        encrypted.raise_for_status()
        rights = self.api("POST", "/api/mango/rights", json={
            "content_params": {"content_id": clip_id, "content_type": "clip"}
        }, timeout=30)
        rights.raise_for_status()
        d = rights.json()
        gkey = AESGCM(hashlib.sha256(self.token.encode()).digest())

        def unwrap(b64):
            raw = base64.b64decode(b64)
            return gkey.decrypt(raw[:12], raw[12:], clip_id.encode())

        key = unwrap(d["key"])
        iv = unwrap(d["iv"])
        dec = Cipher(algorithms.AES(key), modes.CTR(iv)).decryptor()
        plain = dec.update(encrypted.content) + dec.finalize()
        OUT.mkdir(parents=True, exist_ok=True)
        safe = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in title)[:60].strip()
        m4a = OUT / f"{safe or clip_id}-{clip_id}.m4a"
        m4a.write_bytes(plain)
        result = [str(m4a)]
        if to_mp3 and shutil.which("ffmpeg"):
            mp3 = m4a.with_suffix(".mp3")
            r = subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-i", str(m4a),
                 "-codec:a", "libmp3lame", "-q:a", "2", str(mp3)],
                capture_output=True, text=True,
            )
            if r.returncode == 0:
                result.append(str(mp3))
        return result


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("billing")
    sub.add_parser("feed")
    p_dl = sub.add_parser("download")
    p_dl.add_argument("ids", nargs="+")
    p_gen = sub.add_parser("generate")
    p_gen.add_argument("prompt")
    p_gen.add_argument("--instrumental", action="store_true")
    p_gen.add_argument("--model", default="chirp-hawk")
    p_gen.add_argument("--title", default="")
    p_gen.add_argument("--tags", default="")
    p_gen.add_argument("--lyrics", default="")
    p_gen.add_argument("--duration", type=int, default=480)
    p_gen.add_argument("--negative-tags", default="")
    p_gen.add_argument("--wait", action="store_true")
    p_gen.add_argument("--download", action="store_true")
    args = ap.parse_args()

    s = Suno()
    if args.cmd == "billing":
        b = s.billing()
        keep = {k: b.get(k) for k in (
            "is_active", "credits", "total_credits_left", "monthly_limit",
            "monthly_usage", "download_usage", "plan", "renews_on",
        )}
        print(json.dumps(keep, indent=2))
    elif args.cmd == "feed":
        for c in s.feed():
            print(c.get("id"), c.get("status"), c.get("title"), c.get("created_at"))
    elif args.cmd == "download":
        for cid in args.ids:
            for p in s.download(cid):
                print("saved", p)
    elif args.cmd == "generate":
        data = s.generate(args.prompt, args.instrumental, args.model,
                          args.title, args.tags, args.lyrics, args.duration,
                          args.negative_tags)
        clips = data.get("clips", [])
        for c in clips:
            print(c.get("id"), c.get("status"), c.get("model_name"))
        if args.wait:
            clips = s.wait([c["id"] for c in clips])
            for c in clips:
                print(c.get("id"), c.get("status"), c.get("title"))
        if args.download:
            for c in clips:
                if c.get("status") == "complete":
                    for p in s.download(c["id"]):
                        print("saved", p)


if __name__ == "__main__":
    main()
