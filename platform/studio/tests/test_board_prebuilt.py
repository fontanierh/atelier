"""Verified board startup with isolated Python stand-ins; never cargo or a live board service."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
from types import SimpleNamespace

import pytest

from atelier import board_cli, board_web


@pytest.fixture
def startup(tmp_path, monkeypatch):
    binary = tmp_path / 'server'
    binary.write_text(f'#!{sys.executable}\nimport json, os, sys\n'
                      "open(os.environ['BOARD_TEST_ARGV'], 'w').write(json.dumps(sys.argv))\n"
                      'raise SystemExit(7)\n')
    binary.chmod(0o700)
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    args = SimpleNamespace(port=8890, public_origin=['https://board.example.test'],
                           allowed_user='owner@example.test', sender='operator',
                           remote_status=tmp_path / 'remote.json',
                           prebuilt_server=binary, prebuilt_sha256=digest)
    events, handlers = [], {}
    @contextmanager
    def database():
        events.append('database')
        yield
    class Presence:
        def start(self):
            events.append('presence')
    monkeypatch.setattr(board_web.board, 'database', database)
    monkeypatch.setattr(board_web.board_presence, 'Presence', Presence)
    monkeypatch.setattr(board_web.signal, 'signal', lambda signum, handler: handlers.update({signum: handler}))
    def no_build():
        pytest.fail('prebuilt startup must not invoke cargo/build or fall back')
    monkeypatch.setattr(board_web, 'build', no_build)
    record = tmp_path / 'argv.json'
    monkeypatch.setenv('BOARD_TEST_ARGV', str(record))
    return SimpleNamespace(binary=binary, digest=digest, args=args, events=events, handlers=handlers, record=record)


def test_prebuilt_cli_and_actual_python_child_keep_normal_command_and_presence(startup):
    state = startup
    parser = argparse.ArgumentParser()
    board_cli.configure(parser.add_subparsers(dest='command'))
    args = parser.parse_args(['board', 'serve', '--prebuilt-server', str(state.binary),
                             '--prebuilt-sha256', state.digest.upper(), '--port', '8891',
                             '--public-origin', 'https://board.example.test', '--allowed-user', 'owner@example.test',
                             '--sender', 'operator', '--remote-status', str(state.args.remote_status)])
    assert board_web.serve(args) == 7
    assert state.events == ['database', 'presence']
    assert json.loads(state.record.read_text()) == board_web.command(state.binary, args)
    assert signal.SIGTERM in state.handlers


@pytest.mark.parametrize('stop', ['sigterm', 'keyboard'])
def test_prebuilt_retains_child_termination_and_wait_lifecycle(startup, monkeypatch, stop):
    state = startup
    waits = []
    class Child:
        def terminate(self):
            state.events.append('terminate')
        def wait(self):
            waits.append(True)
            if len(waits) == 1:
                if stop == 'keyboard':
                    raise KeyboardInterrupt
                state.handlers[signal.SIGTERM](signal.SIGTERM, None)
            return 0
    def launch(argv):
        assert state.events == ['database', 'presence']
        assert argv == board_web.command(state.binary, state.args)
        state.events.append('launch')
        return Child()
    monkeypatch.setattr(board_web.subprocess, 'Popen', launch)
    assert board_web.serve(state.args) == 0
    assert state.events == ['database', 'presence', 'launch', 'terminate']
    assert len(waits) == (2 if stop == 'keyboard' else 1)


@pytest.mark.parametrize('invalid', ['path-only', 'hash-only', 'empty-hash', 'short-hash', 'nonhex-hash',
                                     'relative', 'missing', 'directory', 'symlink', 'ancestor-link',
                                     'not-executable', 'not-owned', 'empty', 'oversized', 'fifo', 'mismatch'])
def test_invalid_prebuilt_refuses_before_any_startup_without_fallback(startup, monkeypatch, invalid, tmp_path):
    state = startup
    if invalid == 'path-only':
        state.args.prebuilt_sha256 = None
    elif invalid == 'hash-only':
        state.args.prebuilt_server = None
    elif invalid in ('empty-hash', 'short-hash', 'nonhex-hash'):
        state.args.prebuilt_sha256 = {'empty-hash': '', 'short-hash': 'a' * 63, 'nonhex-hash': 'x' * 64}[invalid]
    elif invalid == 'relative':
        state.args.prebuilt_server = Path('server')
    elif invalid == 'missing':
        state.binary.unlink()
    elif invalid == 'directory':
        state.binary.unlink()
        state.binary.mkdir()
    elif invalid == 'symlink':
        target = tmp_path / 'actual-server'
        state.binary.rename(target)
        state.binary.symlink_to(target)
    elif invalid == 'ancestor-link':
        link = tmp_path / 'linked'
        link.symlink_to(tmp_path, target_is_directory=True)
        state.args.prebuilt_server = link / 'server'
    elif invalid == 'not-executable':
        state.binary.chmod(0o400)
    elif invalid == 'not-owned':
        monkeypatch.setattr(board_web.os, 'getuid', lambda: state.binary.stat().st_uid + 1)
    elif invalid == 'empty':
        state.binary.write_bytes(b'')
    elif invalid == 'oversized':
        monkeypatch.setattr(board_web, 'MAX_PREBUILT_BYTES', state.binary.stat().st_size - 1)
    elif invalid == 'fifo':
        state.binary.unlink()
        os.mkfifo(state.binary)
    else:
        state.args.prebuilt_sha256 = '0' * 64
    monkeypatch.setattr(board_web.subprocess, 'Popen', lambda *args, **kwargs: pytest.fail('must not launch'))
    with pytest.raises(ValueError):
        board_web.serve(state.args)
    assert state.events == [] and not state.handlers and not state.record.exists()


@pytest.mark.parametrize('change', ['bytes', 'replacement', 'growth'])
def test_prebuilt_changed_during_hashing_refuses(startup, monkeypatch, change):
    state = startup
    original = hashlib.sha256
    class ChangedDigest:
        def __init__(self):
            self.digest = original()
            self.changed = False
        def update(self, data):
            self.digest.update(data)
            if not self.changed:
                self.changed = True
                if change == 'replacement':
                    replacement = state.binary.with_name('replacement')
                    replacement.write_bytes(state.binary.read_bytes())
                    replacement.chmod(0o700)
                    replacement.replace(state.binary)
                elif change == 'growth':
                    state.binary.write_bytes(data + b'x' * 100)
                else:
                    state.binary.write_bytes(b'x' * len(data))
        def hexdigest(self):
            return self.digest.hexdigest()
    monkeypatch.setattr(board_web.hashlib, 'sha256', ChangedDigest)
    if change == 'growth':
        monkeypatch.setattr(board_web, 'MAX_PREBUILT_BYTES', state.binary.stat().st_size + 1)
    with pytest.raises(ValueError, match='changed|grew'):
        board_web.serve(state.args)
    assert state.events == [] and not state.handlers


def test_default_serve_still_builds_and_uses_normal_lifecycle(startup, monkeypatch):
    state = startup
    del state.args.prebuilt_server
    del state.args.prebuilt_sha256
    def build():
        assert state.events == ['database']
        state.events.append('build')
        return state.binary
    monkeypatch.setattr(board_web, 'build', build)
    assert board_web.serve(state.args) == 7
    assert state.events == ['database', 'build', 'presence']
    assert json.loads(state.record.read_text()) == board_web.command(state.binary, state.args)
