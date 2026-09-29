"""Serve Git-tracked character review assets through a persistent macOS service.

Install with --root and --entry, then point Tailscale Serve at localhost:8790.
Only a manifest of Git-tracked review files is exposed; private API responses,
untracked work, directory listings and files outside the asset root are excluded.
Reinstall after adding new review files to Git to refresh the manifest.
"""

import argparse
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import subprocess
import sys
from urllib.parse import quote, unquote, urlsplit


LABEL = 'com.atelier.asset-review'
TARGET = f'gui/{os.getuid()}/{LABEL}'
PLIST = Path.home() / 'Library/LaunchAgents' / f'{LABEL}.plist'
STATE = Path.home() / '.local/share/atelier/asset-review'
MANIFEST = STATE / 'manifest.json'
EXTENSIONS = {'.html', '.css', '.js', '.png', '.jpg', '.jpeg', '.webp',
              '.mp4', '.glb', '.blend', '.fbx', '.md', '.json', '.txt'}


def loaded():
    return subprocess.run(['launchctl', 'print', TARGET], capture_output=True).returncode == 0


def manifest_for(root, entry):
    repo = Path(subprocess.check_output(
        ['git', '-C', str(root), 'rev-parse', '--show-toplevel'], text=True).strip())
    tracked = subprocess.check_output(
        ['git', '-C', str(repo), 'ls-files', '-z', '--', root.relative_to(repo).as_posix()])
    files = []
    for name in tracked.decode().split('\0'):
        if not name:
            continue
        path = repo / name
        relative = path.relative_to(root)
        if (path.suffix.lower() not in EXTENSIONS
                or any(part.startswith('.') or part == 'api-private'
                       or part == 'diagnostics' or part.endswith('-frames')
                       for part in relative.parts)
                or not path.resolve().is_relative_to(root)
                or not path.is_file()):
            continue
        files.append(relative.as_posix())
    if entry not in files:
        raise ValueError('Entry must be an existing Git-tracked review file inside --root')
    return {'root': str(root), 'entry': entry, 'files': sorted(files)}


class ReviewHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, manifest, **kwargs):
        self.root = Path(manifest['root'])
        self.entry = manifest['entry']
        self.files = frozenset(manifest['files'])
        super().__init__(*args, **kwargs)

    def do_HEAD(self):
        self.serve_file(head=True)

    def do_GET(self):
        self.serve_file(head=False)

    def serve_file(self, head):
        requested = unquote(urlsplit(self.path).path)
        if requested == '/':
            self.send_response(302)
            self.send_header('Location', '/' + quote(self.entry, safe='/'))
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        relative = requested.removeprefix('/')
        if ('\x00' in relative or '\\' in relative
                or any(p in {'.', '..'} for p in relative.split('/'))
                or relative not in self.files):
            self.send_error(404)
            return
        path = (self.root / PurePosixPath(relative)).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            self.send_error(404)
            return
        try:
            source = path.open('rb')
        except OSError:
            self.send_error(404)
            return
        with source:
            size = os.fstat(source.fileno()).st_size
            start, end, partial_response = 0, size - 1, False
            # Single byte ranges let Safari seek and stream the review videos.
            byte_range = self.headers.get('Range')
            if byte_range and not self.headers.get('If-Range'):
                match = re.fullmatch(r'bytes=(\d*)-(\d*)', byte_range)
                if match and any(match.groups()):
                    first, last = match.groups()
                    start = int(first) if first else max(0, size - int(last))
                    end = min(int(last), size - 1) if first and last else size - 1
                    if start > end or start >= size:
                        self.send_response(416)
                        self.send_header('Content-Range', f'bytes */{size}')
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        return
                    partial_response = True
            length = end - start + 1
            self.send_response(206 if partial_response else 200)
            mime = {'glb': 'model/gltf-binary', 'js': 'text/javascript'}.get(
                path.suffix[1:], mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(length))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if partial_response:
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            if not head:
                source.seek(start)
                try:
                    while length > 0:
                        block = source.read(min(length, 256 * 1024))
                        if not block:
                            break
                        self.wfile.write(block)
                        length -= len(block)
                except (BrokenPipeError, ConnectionResetError):
                    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'status', 'stop', 'serve'))
    parser.add_argument('--root', type=Path)
    parser.add_argument('--entry', default='tripo-rig-r02/review.html')
    parser.add_argument('--port', type=int, default=8790)
    args = parser.parse_args()
    if args.action == 'status':
        raise SystemExit(subprocess.run(['launchctl', 'print', TARGET]).returncode)
    if args.action == 'serve':
        manifest = json.loads(MANIFEST.read_text())
        handler = partial(ReviewHandler, manifest=manifest)
        with ThreadingHTTPServer(('127.0.0.1', args.port), handler) as server:
            server.serve_forever()
        return
    if args.action == 'stop':
        if loaded():
            subprocess.run(['launchctl', 'bootout', TARGET], check=True)
        PLIST.unlink(missing_ok=True)
        print(f'Stopped {LABEL}; Tailscale configuration unchanged.')
        return
    if not args.root:
        parser.error('install requires --root')
    root = args.root.resolve()
    manifest = manifest_for(root, args.entry)
    STATE.mkdir(parents=True, exist_ok=True)
    logs = Path.home() / 'Library/Logs/Atelier/asset-review'
    logs.mkdir(parents=True, exist_ok=True)
    spec = {
        'Label': LABEL,
        'ProgramArguments': [sys.executable, str(Path(__file__).resolve()),
                             'serve', '--port', str(args.port)],
        'WorkingDirectory': str(root),
        'EnvironmentVariables': {'PYTHONUNBUFFERED': '1'},
        'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 5,
        'ProcessType': 'Background', 'ExitTimeOut': 10,
        'StandardOutPath': str(logs / 'server.log'),
        'StandardErrorPath': str(logs / 'error.log'),
    }
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    temporary = PLIST.with_suffix('.tmp')
    temporary.write_bytes(plistlib.dumps(spec))
    temporary.chmod(0o600)
    if loaded():
        subprocess.run(['launchctl', 'bootout', TARGET], check=True)
    manifest_tmp = MANIFEST.with_suffix('.tmp')
    manifest_tmp.write_text(json.dumps(manifest, indent=2) + '\n')
    manifest_tmp.replace(MANIFEST)
    temporary.replace(PLIST)
    subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(PLIST)], check=True)
    print(f'Installed {LABEL}: http://127.0.0.1:{args.port}; {len(manifest["files"])} review files')


if __name__ == '__main__':
    main()
