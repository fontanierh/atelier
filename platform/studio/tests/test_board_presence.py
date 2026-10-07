import json
import os
import plistlib
import time

import pytest

from atelier import board, board_presence
from atelier.board_claude import process_start


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path / 'cache'))
    monkeypatch.setenv('ATELIER_RENDER_LOCK', str(tmp_path / 'render.lock'))
    with board.database() as db:
        db.execute("INSERT INTO subscribers (agent, pid, heartbeat, supervised) VALUES ('one', 1, ?, 'job.one')",
                   (time.time(),))
    return tmp_path


def job(folder, label, command):
    with (folder / f'{label}.plist').open('wb') as stream:
        plistlib.dump({'Label': label, 'ProgramArguments': [
            'python3', '-m', 'atelier.cli', 'board', 'subscribe', '--agent', 'one', '--notify', json.dumps(command)]},
            stream)


def test_transport_reads_the_listeners_wake_command(tmp_path):
    job(tmp_path, 'claude', ['atelier', 'board', 'notify-claude', '--session-dir', '/work/one', '{message}'])
    job(tmp_path, 'codex', ['atelier', 'board', 'notify-codex', '--thread', 'abc', '{message}'])
    job(tmp_path, 'other', ['say', '{message}'])
    assert board_presence.transport('claude', tmp_path) == {'kind': 'claude', 'dir': '/work/one'}
    assert board_presence.transport('codex', tmp_path) == {'kind': 'codex', 'thread': 'abc', 'codex': 'codex',
                                                           'socket': None}
    assert board_presence.transport('other', tmp_path) is None
    assert board_presence.transport('missing', tmp_path) is None


def test_claude_state_comes_from_the_one_live_session_in_its_directory(tmp_path):
    registry, work = tmp_path / 'sessions', tmp_path / 'work'
    registry.mkdir(), work.mkdir()
    pid = os.getpid()
    record = {'pid': pid, 'cwd': str(work), 'procStart': process_start(pid), 'status': 'idle',
              'statusUpdatedAt': 1_700_000_000_000}
    (registry / f'{pid}.json').write_text(json.dumps(record))
    assert board_presence.claude_state(work, registry) == ('idle', 1_700_000_000.0)
    # A dead or reused PID, or a session elsewhere, is not this agent's session.
    (registry / f'{pid}.json').write_text(json.dumps(dict(record, procStart='Mon Jan  1 00:00:00 2001')))
    assert board_presence.claude_state(work, registry) is None
    (registry / f'{pid}.json').write_text(json.dumps(dict(record, cwd=str(tmp_path))))
    assert board_presence.claude_state(work, registry) is None


def test_a_quiet_session_with_a_working_line_gets_one_note_per_status(cache):
    now, states = time.time(), {'job.one': ('busy', None)}
    board.set_task('one', 'Shipping r9')
    assert board_presence.step(now, states.get) == []
    with board.database() as db:
        row = db.execute("SELECT session, session_since FROM subscribers WHERE agent='one'").fetchone()
    assert (row['session'], row['session_since']) == ('busy', now)

    states['job.one'] = ('idle', now - board_presence.QUIET + 60)
    assert board_presence.step(now, states.get) == []        # not quiet long enough yet
    assert board_presence.step(now + 60, states.get) == ['one']
    assert board_presence.step(now + 120, states.get) == []  # never repeated for the same status
    with board.database() as db:
        notes = db.execute("SELECT sender, recipient, body FROM messages WHERE sender=?",
                           (board_presence.WATCH,)).fetchall()
    assert [(n['sender'], n['recipient']) for n in notes] == [(board_presence.WATCH, 'one')]
    assert '"Shipping r9"' in notes[0]['body'] and 'atelier board task --agent one idle' in notes[0]['body']

    board.set_task('one', 'Shipping r10')                    # a new status line may be noted once more
    assert board_presence.step(now + 180, states.get) == ['one']
    board.set_task('one', 'idle')
    assert board_presence.step(now + 240, states.get) == []
    board.set_task('one', 'Waiting on the operator')
    board.open_task('one', 'Can I ship r10?')
    assert board_presence.step(now + 300, states.get) == []  # its open operator task already says it is blocked


def test_an_unreadable_session_clears_its_state(cache):
    board_presence.step(time.time(), {'job.one': ('idle', 5.0)}.get)
    board_presence.step(time.time(), {}.get)
    with board.database() as db:
        row = db.execute("SELECT session, session_since FROM subscribers WHERE agent='one'").fetchone()
    assert (row['session'], row['session_since']) == (None, None)
