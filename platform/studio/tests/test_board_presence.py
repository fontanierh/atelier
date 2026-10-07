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


def empty():
    return {}, {}


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
    assert board_presence.step(floor=empty, now=now, read=states.get) == []
    with board.database() as db:
        row = db.execute("SELECT session, session_since FROM subscribers WHERE agent='one'").fetchone()
    assert (row['session'], row['session_since']) == ('busy', now)

    states['job.one'] = ('idle', now - board_presence.QUIET + 60)
    assert board_presence.step(floor=empty, now=now, read=states.get) == []        # not quiet long enough yet
    assert board_presence.step(floor=empty, now=now + 60, read=states.get) == ['one']
    assert board_presence.step(floor=empty, now=now + 120, read=states.get) == []  # never repeated for the same status
    with board.database() as db:
        notes = db.execute("SELECT sender, recipient, body FROM messages WHERE sender=?",
                           (board_presence.WATCH,)).fetchall()
    assert [(n['sender'], n['recipient']) for n in notes] == [(board_presence.WATCH, 'one')]
    assert '"Shipping r9"' in notes[0]['body'] and 'atelier board task --agent one idle' in notes[0]['body']

    board.set_task('one', 'Shipping r10')                    # a new status line may be noted once more
    assert board_presence.step(floor=empty, now=now + 180, read=states.get) == ['one']
    board.set_task('one', 'idle')
    assert board_presence.step(floor=empty, now=now + 240, read=states.get) == []
    board.set_task('one', 'Waiting on the operator')
    board.open_task('one', 'Can I ship r10?')
    # Its open operator task already says it is blocked.
    assert board_presence.step(floor=empty, now=now + 300, read=states.get) == []


def test_an_unreadable_session_clears_its_state(cache):
    board_presence.step(floor=empty, now=time.time(), read={'job.one': ('idle', 5.0)}.get)
    board_presence.step(floor=empty, now=time.time(), read={}.get)
    with board.database() as db:
        row = db.execute("SELECT session, session_since FROM subscribers WHERE agent='one'").fetchone()
    assert (row['session'], row['session_since']) == (None, None)


LINES = {
    'Holding': '- 2026-10-07 13:37:12 CEST one, ~/dev/atelier: RUNNING world.communitypark, actual small slot',
    'Waiting': '- 2026-10-07 13:35:11 CEST two ~/dev/atelier-two: READY compile only\n'
               '- 2026-10-07 13:40 three (branch x): READY one game, after one',
    'Log': '- 2026-10-07 13:00:00 CEST four: finished',
}


def test_render_work_in_flight_is_not_idle():
    holders = {'big': {'checkout': 'atelier-five'}, 'small': {'checkout': ''}}
    checkouts = {'one': 'atelier', 'four': 'atelier-four', 'five': 'atelier-five', 'six': None}
    assert board_presence.engaged(LINES, holders, checkouts) == {'one', 'two', 'three', 'five'}
    assert board_presence.engaged({}, {}, checkouts) == set()


def test_an_agent_on_the_render_board_gets_no_note(cache):
    now = time.time()
    board.set_task('one', 'Importing the park')
    read = {'job.one': ('idle', now - 2 * board_presence.QUIET)}.get
    assert board_presence.step(floor=lambda: (LINES, {}), now=now, read=read) == []
    assert board_presence.step(floor=empty, now=now, read=read) == ['one']
