"""Exercise fixture lifetime and readiness with small HTTP children, without compiling Rust."""
import json
import os
import subprocess
import sys
import warnings
from contextlib import nullcontext
from urllib.error import HTTPError

import pytest

import board_server


@pytest.fixture
def child(tmp_path, monkeypatch):
    processes = []
    popen = subprocess.Popen

    def spawn(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(board_server.subprocess, 'Popen', spawn)
    executable = tmp_path / 'server'
    executable.write_text(f'#!{sys.executable}\n' + '''
import json, os, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

Path(__file__).with_suffix('.pid').write_text(str(os.getpid()))
mode = os.environ['STARTUP_CASE']
print('starting test server', flush=True)
if mode == 'exit':
    raise SystemExit(7)
if mode == 'silent':
    time.sleep(10)

class Handler(BaseHTTPRequestHandler):
    requests = 0

    def do_GET(self):
        Handler.requests += 1
        if mode == 'hang':
            time.sleep(10)
        status = 503 if mode == 'busy' and Handler.requests == 1 else 403 if mode == 'forbidden' else 200
        body = b'not json' if mode == 'bad-json' else json.dumps({'csrf': 'test-token'}).encode()
        self.send_response(status)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
print(f'Agent board listening on http://127.0.0.1:{server.server_port}', flush=True)
server.serve_forever()
''')
    executable.chmod(0o755)
    monkeypatch.setattr(board_server, 'binary', lambda: executable)
    monkeypatch.setattr(board_server, 'STARTUP_TIMEOUT', 2.)
    monkeypatch.setattr(board_server, 'STARTUP_REQUEST_TIMEOUT', .25)
    monkeypatch.setattr(board_server.shutil, 'which', lambda name: None)
    try:
        yield executable
    finally:
        # Assertions below must detect leaks before this cleanup. A regression must not leave
        # the test's own stand-in running after the failing test, either.
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def assert_reaped(child):
    pid = int(child.with_suffix('.pid').read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.parametrize('mode,requests', [('ready', 1), ('busy', 2)])
def test_ready_waits_for_a_successful_state_read_and_stops_cleanly(tmp_path, child, mode, requests):
    warning = pytest.warns(RuntimeWarning, match='2 readiness requests') if mode == 'busy' else nullcontext()
    with warning:
        server = board_server.Server(tmp_path, env={'STARTUP_CASE': mode})
    try:
        assert server.csrf == 'test-token'
        assert server.requests == requests
        assert 0 < server.startup_seconds < board_server.STARTUP_TIMEOUT
    finally:
        server.stop()
    server.stop()  # Teardown is safe even if a failed caller already stopped the fixture.
    assert_reaped(child)


def test_warning_promoted_to_error_still_reaps_child(tmp_path, child):
    with warnings.catch_warnings():
        warnings.simplefilter('error', RuntimeWarning)
        with pytest.raises(RuntimeWarning, match='2 readiness requests'):
            board_server.Server(tmp_path, env={'STARTUP_CASE': 'busy'})
    assert_reaped(child)


@pytest.mark.parametrize('mode,error', [('exit', RuntimeError), ('forbidden', HTTPError), ('bad-json', json.JSONDecodeError)])
def test_failed_construction_reaps_child_and_keeps_diagnostics(tmp_path, child, mode, error):
    with pytest.raises(error) as caught:
        board_server.Server(tmp_path, env={'STARTUP_CASE': mode})
    assert_reaped(child)
    notes = '\n'.join(caught.value.__notes__)
    assert 'Board startup:' in notes
    assert 'starting test server' in notes
    if mode == 'forbidden':
        assert '1 requests' in notes  # A permission error is not retried as transient readiness.


@pytest.mark.parametrize('mode,stage', [('silent', 'listening announcement'), ('hang', 'first /api/state')])
def test_startup_deadline_covers_listener_and_http_without_leaking(tmp_path, child, monkeypatch, mode, stage):
    monkeypatch.setattr(board_server, 'STARTUP_REQUEST_TIMEOUT', .05)
    with pytest.raises(TimeoutError, match=stage) as caught:
        board_server.Server(tmp_path, env={'STARTUP_CASE': mode})
    assert_reaped(child)
    assert any('Board server log:' in note for note in caught.value.__notes__)
