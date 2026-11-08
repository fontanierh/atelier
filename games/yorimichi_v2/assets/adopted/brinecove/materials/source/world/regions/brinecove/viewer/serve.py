#!/usr/bin/env python3
"""Serve the Brinecove review viewer on the machine's Tailscale address.

    uv run python games/yorimichi/world/regions/brinecove/viewer/serve.py [--port 8842] [--host HOST]

The default directory is build/yorimichi/brinecove-review/viewer. It is a plain static server; the page makes no
external requests and loads its modules from the same folder.
"""
import argparse
import functools
import http.server
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import yori  # noqa: E402,F401
from brinecove.paths import REVIEW  # noqa: E402

DEFAULT = REVIEW / 'viewer'


def tailscale_ip():
    for command in (['tailscale', 'ip', '-4'],
                    ['/Applications/Tailscale.app/Contents/MacOS/Tailscale', 'ip', '-4']):
        try:
            out = subprocess.run(command, capture_output=True, text=True, timeout=4)
            value = out.stdout.strip().splitlines()[0]
            if out.returncode == 0 and value:
                return value
        except (OSError, IndexError, subprocess.SubprocessError):
            continue
    return '127.0.0.1'


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stdout.write('%s - %s\n' % (self.address_string(), fmt % args))
        sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default=None)
    ap.add_argument('--port', type=int, default=8842)
    ap.add_argument('--dir', type=Path, default=DEFAULT)
    args = ap.parse_args()
    host = args.host or tailscale_ip()
    root = args.dir.resolve()
    if not (root / 'index.html').is_file():
        raise SystemExit(f'no viewer at {root}; build it first')
    handler = functools.partial(Handler, directory=str(root))
    server = http.server.ThreadingHTTPServer((host, args.port), handler)
    print(f'Brinecove viewer: http://{host}:{args.port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
