"""The board's Rust web server, run for one test against that test's isolated mailbox."""
import json
import os
import shutil
import subprocess
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from http.client import HTTPConnection
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from atelier import board_web

ORIGIN = 'https://board.example.ts.net'
USER = 'owner@example.test'
_built = []
STARTUP_TIMEOUT = 20.
STARTUP_REQUEST_TIMEOUT = 1.


def binary():
    """The server, built once per test run (an incremental build when nothing changed)."""
    if not _built:
        if board_web.cargo() is None and not board_web.BINARY.is_file():
            pytest.skip('the board server needs Rust (https://rustup.rs)')
        _built.append(board_web.build())
    return _built[0]


class Server:
    """@cc [owner:fontanierh,label:correctness] isolated-board-test-lifetime
    Startup MUST have a deadline. Any failure after launch MUST reap this fixture's child before
    propagating, even when construction fails before pytest can register its teardown.

    The server is isolated: HOME is the test's, launchctl records what it was asked, and the render floor's disk
    breakdown never scans (ATELIER_BOARD_DISK_SCAN=0; its scan is tested in the server's own unit tests).
    """

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
        environ = {**os.environ, 'HOME': str(home), 'ATELIER_BOARD_LAUNCHCTL': str(self.launchctl),
                   'ATELIER_BOARD_DISK_SCAN': '0', **(env or {})}
        self.log = tmp_path / 'board-server.log'
        self.process = None
        readiness = None
        started = time.monotonic()
        self.stage, self.requests = 'listening announcement', 0
        try:
            # A file preserves stderr and cannot fill an unread pipe while a test is running.
            with self.log.open('w') as output:
                self.process = subprocess.Popen(argv, stdout=output, stderr=subprocess.STDOUT, env=environ)
            deadline = started + STARTUP_TIMEOUT
            readiness = ThreadPoolExecutor(max_workers=1, thread_name_prefix='board-readiness')
            ready = readiness.submit(self.ready, deadline)
            try:
                ready.result(timeout=max(0., deadline - time.monotonic()))
            except TimeoutError as error:
                raise TimeoutError(f'Board startup deadline exceeded during {self.stage}') from error
            self.startup_seconds = time.monotonic() - started
            if self.requests > 1 or self.startup_seconds > STARTUP_REQUEST_TIMEOUT:
                warnings.warn(f'Board startup took {self.startup_seconds:.3f}s and {self.requests} readiness requests',
                              RuntimeWarning, stacklevel=2)
        except BaseException as error:
            if self.process is not None:
                try:
                    if isinstance(error, Exception):
                        error.add_note(f'Board startup: {self.stage}, {self.requests} requests, '
                                       f'{time.monotonic() - started:.2f}s elapsed; child exit={self.process.poll()}')
                        self.diagnose(error)
                finally:
                    self.stop()
            raise
        finally:
            if readiness is not None:
                # Failure cleanup stops the server first, closing any trickling response. Joining
                # before stop() would let a blocked HTTP read defeat the constructor's deadline.
                readiness.shutdown(wait=True, cancel_futures=True)

    def ready(self, deadline):
        """The listening socket precedes the first successful database read; wait for both."""
        last_error = None
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f'Board startup deadline exceeded during {self.stage}') from last_error
            if self.process.poll() is not None:
                raise RuntimeError('The board server exited during startup')
            if self.stage == 'listening announcement':
                for line in self.log.read_text(errors='replace').splitlines(keepends=True):
                    if line.startswith('Agent board listening on http://127.0.0.1:') and line.endswith('\n'):
                        self.server_port = int(line.rsplit(':', 1)[1])
                        self.server_address = ('127.0.0.1', self.server_port)
                        self.stage = 'first /api/state'
                        break
            if self.stage == 'first /api/state':
                self.requests += 1
                try:
                    # Connect directly to our child: no inherited proxy or redirect may leave the
                    # worker waiting on another server after failure cleanup reaps this one.
                    with closing(HTTPConnection('127.0.0.1', self.server_port,
                                                timeout=min(STARTUP_REQUEST_TIMEOUT, remaining))) as connection:
                        connection.request('GET', '/api/state?limit=1')
                        with connection.getresponse() as response:
                            if response.status != 200:
                                raise HTTPError('/api/state', response.status, response.reason, response.headers, None)
                            self.csrf = json.loads(response.read())['csrf']
                    return
                except HTTPError as error:
                    error.close()
                    if error.code != 503:
                        raise  # Bad routes, permissions and malformed responses are not startup delays.
                    last_error = error
                except (TimeoutError, ConnectionError) as error:
                    last_error = error
            time.sleep(min(.05, max(0., deadline - time.monotonic())))

    def diagnose(self, error):
        """Keep failure evidence in pytest output; sampling is bounded and only targets our child."""
        try:
            error.add_note('Board server log:\n' + self.log.read_text(errors='replace')[-8000:])
            sampler = shutil.which('sample')
            if isinstance(error, TimeoutError) and sampler and self.process.poll() is None:
                trace = self.log.with_suffix('.sample')
                subprocess.run([sampler, str(self.process.pid), '1', '-file', str(trace)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
                if trace.exists():
                    error.add_note('Board server stack sample:\n' + trace.read_text(errors='replace')[:24000])
        except (OSError, subprocess.TimeoutExpired) as diagnostic_error:
            error.add_note(f'Board diagnostic unavailable: {diagnostic_error}')

    def retired(self):
        """What launchctl was asked to do, one call per line."""
        log = self.launchctl.with_name('launchctl.log')
        return log.read_text().splitlines() if log.exists() else []

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


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
