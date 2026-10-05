"""Persistent listeners outlive turns and cannot be disarmed by a legacy unsubscribe."""
import json
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from atelier import board, board_service


def test_service_uses_existing_transport_without_shell_and_survives_login_and_crashes(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path))
    args = SimpleNamespace(agent='test-owner', notify=json.dumps(['/local/atelier', 'notify', '{message}']),
                           checkout=str(tmp_path), addressed_only=True)
    service = board_service.configuration(args)
    assert service['RunAtLoad'] is True and service['KeepAlive'] is True
    assert service['Label'] == 'com.atelier.board.test-owner'
    assert '--managed' in service['ProgramArguments'] and '--addressed-only' in service['ProgramArguments']
    assert args.notify in service['ProgramArguments']
    assert 'sh' not in service['ProgramArguments']


def test_managed_listener_resists_legacy_stop_flag_and_keeps_cursor(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path))
    calls = []
    monkeypatch.setattr(board, 'render_board_changes', lambda: None)
    monkeypatch.setattr(board, 'stalled_logs', lambda *args: None)
    monkeypatch.setattr(board.time, 'sleep', lambda *_: None)

    def poll(agent, *args, **kwargs):
        with board.database() as db:
            row = db.execute('SELECT stop,cursor FROM subscribers WHERE agent=?', (agent,)).fetchone()
            calls.append((row['stop'], row['cursor']))
            if len(calls) == 1:
                db.execute('UPDATE subscribers SET stop=1,cursor=17 WHERE agent=?', (agent,))
        if len(calls) == 2:
            raise KeyboardInterrupt()
        return 0

    monkeypatch.setattr(board, 'poll', poll)
    with pytest.raises(KeyboardInterrupt):
        board.subscribe('owner', ['/notify', '{message}'], checkout=tmp_path, managed=True)
    assert calls == [(0, 0), (0, 17)]


def test_unsubscribe_keeps_managed_service_armed(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path))
    with board.database() as db:
        db.execute("INSERT INTO subscribers (agent,supervised) VALUES ('owner','com.atelier.board.owner')")
    assert board.main(SimpleNamespace(action='unsubscribe', agent='owner')) == 0
    with board.database() as db:
        assert db.execute("SELECT stop FROM subscribers WHERE agent='owner'").fetchone()['stop'] == 0
    assert 'remains armed' in capsys.readouterr().out


def test_install_recovers_stale_fallback_without_resetting_history(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path / 'cache'))
    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(board_service, 'command', lambda argv: SimpleNamespace(
        returncode=1 if 'print' in argv else 0, stderr=''))
    with board.database() as db:
        db.execute("INSERT INTO subscribers (agent,cursor,pid) VALUES ('owner',42,999999)")
    args = SimpleNamespace(agent='owner', notify=json.dumps(['/notify', '{message}']),
                           checkout=str(tmp_path), addressed_only=True)
    assert board_service.install(args) == 0
    with board.database() as db:
        row = db.execute("SELECT * FROM subscribers WHERE agent='owner'").fetchone()
        assert row['cursor'] == 42 and row['pid'] is None and row['stop'] == 0
        assert row['supervised'] == 'com.atelier.board.owner'
