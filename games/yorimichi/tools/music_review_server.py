#!/usr/bin/env python3
"""Serve the generated zone soundtrack for listening and review on the tailnet.

Reads build/yorimichi/music/index.json and the per-zone manifests written by
the Suno batch runner. Reviews are stored in build/yorimichi/music/reviews.json.
"""
import argparse
import json
import mimetypes
import os
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[3]
MUSIC = ROOT / "build" / "yorimichi" / "music"
PAGE = Path(__file__).with_name("music_review.html")
REVIEWS = MUSIC / "reviews.json"


class Handler(BaseHTTPRequestHandler):
    server_version = "YorimichiMusicReview/1.0"

    def log_message(self, fmt, *args):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, content_type, cache="max-age=3600"):
        try:
            handle = path.open("rb")
        except OSError:
            self.send_error(404)
            return
        with handle:
            size = os.fstat(handle.fileno()).st_size
            match = re.match(r"bytes=(\d*)-(\d*)$", (self.headers.get("Range") or "").strip())
            if match:
                start_text, end_text = match.groups()
                if start_text == "":
                    start = max(0, size - int(end_text or 0))
                    end = size - 1
                else:
                    start = int(start_text)
                    end = int(end_text) if end_text else size - 1
                if start >= size or end < start:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                end = min(end, size - 1)
                length = end - start + 1
                self.send_response(206)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(length))
                self.send_header("Cache-Control", cache)
                self.end_headers()
                handle.seek(start)
                remaining = length
                while remaining:
                    chunk = handle.read(min(1 << 16, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", cache)
            self.end_headers()
            while True:
                chunk = handle.read(1 << 16)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path in ("/", "/index.html"):
            self.send_file(PAGE, "text/html; charset=utf-8", "no-store")
        elif path == "/index.json":
            self.send_file(MUSIC / "index.json", "application/json; charset=utf-8", "no-store")
        elif path == "/api/reviews":
            if REVIEWS.exists():
                self.send_file(REVIEWS, "application/json; charset=utf-8", "no-store")
            else:
                self.send_json({})
        elif path.startswith("/music/"):
            target = (MUSIC / path[len("/music/"):]).resolve()
            try:
                target.relative_to(MUSIC.resolve())
            except ValueError:
                self.send_error(403)
                return
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            self.send_file(target, content_type)
        else:
            self.send_error(404)

    def do_POST(self):
        if urlparse(self.path).path != "/api/review":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 100000:
            self.send_error(400)
            return
        try:
            body = json.loads(self.rfile.read(length))
        except Exception:
            self.send_error(400)
            return
        clip_id = str(body.get("clip_id") or "")[:100]
        rating = body.get("rating")
        note = str(body.get("note") or "")[:2000]
        if not clip_id or rating not in (None, "good", "maybe", "no"):
            self.send_error(400)
            return
        reviews = {}
        if REVIEWS.exists():
            try:
                reviews = json.loads(REVIEWS.read_text())
            except Exception:
                reviews = {}
        reviews[clip_id] = {
            "rating": rating,
            "note": note,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        MUSIC.mkdir(parents=True, exist_ok=True)
        tmp = REVIEWS.with_suffix(".tmp")
        tmp.write_text(json.dumps(reviews, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, REVIEWS)
        self.send_json(reviews[clip_id])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8099)
    args = parser.parse_args()
    httpd = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"serving {MUSIC} at http://{args.bind}:{args.port}/", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
