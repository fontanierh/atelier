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
    snapshots = tmp_path / 'snapshots'
    snapshots.mkdir()
    temporary = board_web.tempfile.TemporaryDirectory
    monkeypatch.setattr(board_web.tempfile, 'TemporaryDirectory',
                        lambda *args, **kwargs: temporary(*args, dir=snapshots, **kwargs))
    return SimpleNamespace(binary=binary, digest=digest, args=args, events=events, handlers=handlers,
                           record=record, snapshots=snapshots)


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
    argv = json.loads(state.record.read_text())
    snapshot = Path(argv[0])
    assert snapshot != state.binary and argv == board_web.command(snapshot, args)
    assert not snapshot.exists() and not list(state.snapshots.iterdir())
    assert signal.SIGTERM in state.handlers


@pytest.mark.parametrize('stop', ['sigterm', 'keyboard'])
def test_prebuilt_retains_child_termination_and_wait_lifecycle(startup, monkeypatch, stop):
    state = startup
    waits = []
    launched = []
    class Child:
        exited = False
        def terminate(self):
            assert launched[0].exists()
            state.events.append('terminate')
        def wait(self):
            assert launched[0].exists()
            waits.append(True)
            if len(waits) == 1:
                if stop == 'keyboard':
                    raise KeyboardInterrupt
                state.handlers[signal.SIGTERM](signal.SIGTERM, None)
            self.exited = True
            return 0
        def poll(self):
            return 0 if self.exited else None
    def launch(argv):
        assert state.events == ['database', 'presence']
        snapshot = Path(argv[0])
        assert snapshot != state.binary and snapshot.read_bytes() == state.binary.read_bytes()
        assert snapshot.stat().st_mode & 0o777 == 0o500
        assert snapshot.parent.stat().st_mode & 0o777 == 0o700
        assert argv == board_web.command(snapshot, state.args)
        launched.append(snapshot)
        state.events.append('launch')
        return Child()
    monkeypatch.setattr(board_web.subprocess, 'Popen', launch)
    assert board_web.serve(state.args) == 0
    assert state.events == ['database', 'presence', 'launch', 'terminate']
    assert len(waits) == (2 if stop == 'keyboard' else 1)
    assert not launched[0].exists() and not list(state.snapshots.iterdir())


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
    assert not list(state.snapshots.iterdir())


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
    assert not list(state.snapshots.iterdir())


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
    assert not list(state.snapshots.iterdir())


@pytest.mark.parametrize('during', ['database', 'presence'])
def test_replacing_source_after_verification_executes_only_verified_bytes(startup, monkeypatch, during):
    state = startup
    def replace_source():
        replacement = state.binary.with_name('replacement')
        replacement.write_text(f'#!{sys.executable}\nraise SystemExit(19)\n')
        replacement.chmod(0o700)
        replacement.replace(state.binary)
    if during == 'database':
        @contextmanager
        def database():
            state.events.append('database')
            replace_source()
            yield
        monkeypatch.setattr(board_web.board, 'database', database)
    else:
        class Presence:
            def start(self):
                state.events.append('presence')
                replace_source()
        monkeypatch.setattr(board_web.board_presence, 'Presence', Presence)
    assert board_web.serve(state.args) == 7
    assert state.events == ['database', 'presence']
    assert state.record.exists()
    snapshot = Path(json.loads(state.record.read_text())[0])
    assert snapshot != state.binary and not snapshot.exists() and not list(state.snapshots.iterdir())


@pytest.mark.parametrize('failure', ['database', 'presence', 'launch', 'wait'])
def test_private_snapshot_lives_through_child_cleanup_and_is_removed_on_failure(startup, monkeypatch, failure):
    state = startup
    observed, waits, terminated = [], [], []
    def snapshot():
        value = next(state.snapshots.iterdir()) / 'atelier-board-server'
        assert value.exists() and hashlib.sha256(value.read_bytes()).hexdigest() == state.digest
        observed.append(value)
        return value
    if failure == 'database':
        @contextmanager
        def database():
            snapshot()
            raise RuntimeError('isolated database failure')
            yield
        monkeypatch.setattr(board_web.board, 'database', database)
    elif failure == 'presence':
        class Presence:
            def start(self):
                snapshot()
                raise RuntimeError('isolated presence failure')
        monkeypatch.setattr(board_web.board_presence, 'Presence', Presence)
    class Child:
        exited = False
        def poll(self):
            return 0 if self.exited else None
        def terminate(self):
            snapshot()
            terminated.append(True)
        def wait(self):
            snapshot()
            waits.append(True)
            if len(waits) == 1:
                raise RuntimeError('isolated wait failure')
            self.exited = True
            return 0
    def launch(argv):
        assert Path(argv[0]) == snapshot()
        if failure == 'launch':
            raise RuntimeError('isolated launch failure')
        return Child()
    monkeypatch.setattr(board_web.subprocess, 'Popen', launch)
    with pytest.raises(RuntimeError, match='isolated'):
        board_web.serve(state.args)
    assert observed and all(not value.exists() for value in observed) and not list(state.snapshots.iterdir())
    if failure == 'wait':
        assert len(waits) == 2 and len(terminated) == 1


def test_snapshot_copy_fsync_failure_refuses_and_cleans_private_files(startup, monkeypatch):
    state = startup
    def failed_sync(descriptor):
        assert next(state.snapshots.iterdir()).is_dir()
        raise OSError('isolated sync failure')
    monkeypatch.setattr(board_web.os, 'fsync', failed_sync)
    with pytest.raises(ValueError, match='could not be verified'):
        board_web.serve(state.args)
    assert state.events == [] and not state.handlers and not list(state.snapshots.iterdir())
