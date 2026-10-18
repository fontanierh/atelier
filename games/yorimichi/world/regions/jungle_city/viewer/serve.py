"""Serve the Jungle City viewer on loopback; Tailscale Serve publishes the same page."""
from __future__ import annotations

import argparse
import functools
import http.server
from pathlib import Path
import socketserver
from urllib.parse import unquote, urlparse


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
MODELS = ROOT / "build" / "yorimichi" / "jungle-city" / "models"
VENDOR = ROOT / "games" / "yorimichi" / "tools" / "character_review_web" / "vendor"


class Quiet(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        route = unquote(urlparse(path).path)
        prefix = "/jungle-city/"
        if not route.startswith(prefix):
            return str(ROOT / "nonexistent")
        rel = route[len(prefix):]
        if rel == "":
            rel = "index.html"
        if rel.startswith("models/"):
            return str(MODELS / rel.removeprefix("models/"))
        if rel.startswith("vendor/"):
            return str(VENDOR / rel.removeprefix("vendor/"))
        return str(HERE / rel)

    def log_message(self, fmt: str, *args) -> None:
        print(f"viewer {self.address_string()} {fmt % args}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8899)
    args = parser.parse_args()
    handler = functools.partial(Quiet, directory=str(ROOT))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", args.port), handler) as server:
        path = "/jungle-city/"
        print(f"Jungle City viewer: http://127.0.0.1:{args.port}{path}", flush=True)
        print(f"Tailnet publish: tailscale serve --bg --set-path /jungle-city http://127.0.0.1:{args.port}{path}", flush=True)
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
