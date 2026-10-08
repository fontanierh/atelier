"""The board's Rust web server, run for one test against that test's isolated mailbox."""
import json
import os
import subprocess
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from atelier import board_web

ORIGIN = 'https://board.example.ts.net'
USER = 'owner@example.test'
_built = []


def binary():
    """The server, built once per test run (an incremental build when nothing changed)."""
    if not _built:
        if board_web.cargo() is None and not board_web.BINARY.is_file():
            pytest.skip('the board server needs Rust (https://rustup.rs)')
        _built.append(board_web.build())
    return _built[0]


class Server:
    """A running board server. Its HOME is the test's, and launchctl is a stand-in that records what it was asked."""

    def __init__(self, tmp_path, origins=(), allowed_user=None, env=None):
        home = tmp_path / 'home'
        home.mkdir(exist_ok=True)
        self.launchctl = tmp_path / 'launchctl'
        self.launchctl.write_text('#!/bin/sh\necho "$@" >> "$0.log"\n')
        self.launchctl.chmod(0o755)
        self.world = tmp_path / 'world-build'
        argv = [str(binary()), '--port', '0', '--assets', str(board_web.ASSETS), '--world-build', str(self.world)]
        for origin in origins:
            argv += ['--public-origin', origin]
        if allowed_user:
            argv += ['--allowed-user', allowed_user]
        environ = {**os.environ, 'HOME': str(home), 'ATELIER_BOARD_LAUNCHCTL': str(self.launchctl), **(env or {})}
        self.process = subprocess.Popen(argv, stdout=subprocess.PIPE, env=environ, text=True)
        line = self.process.stdout.readline()
        assert 'listening on' in line, f'the board server did not start: {line!r}'
        self.server_port = int(line.rsplit(':', 1)[1])
        self.server_address = ('127.0.0.1', self.server_port)
        with urlopen(f'http://127.0.0.1:{self.server_port}/api/state?limit=1', timeout=5) as response:
            self.csrf = json.loads(response.read())['csrf']

    def retired(self):
        """What launchctl was asked to do, one call per line."""
        log = self.launchctl.with_name('launchctl.log')
        return log.read_text().splitlines() if log.exists() else []

    def stop(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process.stdout.close()


def call(server, path, payload=None, headers=None):
    """One request as the board's own page makes it: same origin, with the CSRF token. Returns status, body, headers."""
    url = f'http://127.0.0.1:{server.server_port}'
    values = {'Origin': url, 'Content-Type': 'application/json', 'X-Board-CSRF': server.csrf}
    values.update(headers or {})
    data = None if payload is None else json.dumps(payload).encode()
    try:
        response = urlopen(Request(url + path, data=data, headers=values), timeout=5)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.read(), response.headers


def view(server, path, **query):
    """A GET of a JSON view; a refused query raises ValueError with the server's reason."""
    status, body, _ = call(server, f'{path}?{urlencode(query)}' if query else path)
    if status == 400:
        raise ValueError(json.loads(body)['error'])
    assert status == 200, body
    return json.loads(body)


def snapshot(server, **query):
    return view(server, '/api/state', **query)
