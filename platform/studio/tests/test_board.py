"""Machine-local coordination: concurrent posts, durable delivery and advisory-only monitoring."""
import json
import os
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import board
from atelier.cli import parse_args
from atelier.safety import render_lock
from atelier.safety import memory_guard


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path / 'cache'))
    monkeypatch.setenv('ATELIER_RENDER_LOCK', str(tmp_path / 'render.lock'))
    return tmp_path


def register(agent, cursor=0):
    with board.database() as db:
        db.execute('INSERT INTO subscribers (agent, cursor) VALUES (?, ?)', (agent, cursor))


def test_concurrent_posts_and_reply_history(cache):
    board.post('setup', 'initial')
    with ThreadPoolExecutor(max_workers=8) as executor:
        ids = list(executor.map(lambda i: board.post(f'owner-{i}', f'job {i}', 'review'), range(32)))
    assert len(set(ids)) == 32
    assert [m['id'] for m in board.messages()] == sorted([1, *ids])
    reply = board.post('review', 'accepted', 'owner-0', 'ack', ids[0])
    assert board.messages(after=reply-1)[0]['reply_to'] == ids[0]
    with pytest.raises(sqlite3.IntegrityError, match='FOREIGN KEY'):
        board.post('review', 'unknown reference', reply_to=10000)
    assert len(board.messages()) == 34


def test_addressing_retry_and_resume(cache, monkeypatch):
    register('review')
    board.post('other', 'private', 'elsewhere')
    board.post('review', 'own broadcast')
    first = board.post('other', 'handoff', 'review')
    board.post('other', 'broadcast')
    delivered = []
    def fail(*_):
        raise RuntimeError('offline')
    monkeypatch.setattr(board, 'deliver', fail)
    with pytest.raises(RuntimeError):
        board.poll('review')
    with board.database() as db:
        assert db.execute('SELECT cursor FROM subscribers').fetchone()['cursor'] == 0
    monkeypatch.setattr(board, 'deliver', lambda batch, _: delivered.extend(batch))
    assert board.poll('review') == 2
    assert [m['id'] for m in delivered] == [first, first+1]
    assert board.poll('review') == 0
    board.post('other', 'next', 'review')
    assert board.poll('review') == 1


def test_delivery_uses_literal_argv_and_bounded_previews(cache, monkeypatch):
    sent = []
    monkeypatch.setattr(subprocess, 'run', lambda argv, **kw: sent.append((argv, kw)) or SimpleNamespace(returncode=0))
    batch = [dict(id=i, sender='sender', recipient='*', topic='info', body='$(do not execute)'+ 'x'*7900)
             for i in range(20)]
    board.deliver(batch, ['notify', '{message}'])
    assert len(sent[0][0][1]) < 16000
    assert '$(do not execute)' in sent[0][0][1]
    assert 'shell' not in sent[0][1]
    assert sent[0][1]['timeout'] == 30
    with pytest.raises(ValueError):
        board.notify_command('["notify"]')
    assert board.main(parse_args(['board', 'post', '--agent', '../bad', 'test'])) == 1


def test_legacy_board_changes_bridge_once_without_telemetry_noise(cache):
    board.root().joinpath('render-board.md').write_text(
        '<!-- atelier-coordinator:start -->sample 1<!-- atelier-coordinator:end -->\n## Handoffs\nReview next.\n')
    board.render_board_changes()
    assert board.messages() == []  # Baseline is not a new message.
    path = board.root() / 'render-board.md'
    path.write_text(path.read_text().replace('sample 1', 'sample 2'))
    board.render_board_changes()
    assert board.messages() == []
    path.write_text(path.read_text().replace('Review next.', 'Owner released; review now.'))
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: board.render_board_changes(), range(4)))
    assert len(board.messages()) == 1
    assert board.messages()[0]['recipient'] == '*'
    assert '(Handoffs)' in board.messages()[0]['body']


def test_stall_notices_require_own_fresh_live_guard_and_deduplicate(cache, monkeypatch):
    checkout = cache / 'checkout';checkout.mkdir()
    folder = checkout / 'build' / 'sandbox' / 'logs' / 'compile.guard';folder.mkdir(parents=True)
    log = folder / 'stdout.log';log.write_text('starting');os.utime(log, (100, 100))
    health = dict(pid=12, process_start=222, time=1090, state='running')
    report = folder / 'memory-health.json';report.write_text(json.dumps(health))
    holder = dict(pid=11, started=111, repo=str(checkout), time=100, purpose='compile')
    monkeypatch.setattr(render_lock, 'read_holder', lambda _: holder)
    monkeypatch.setattr(render_lock, 'family', lambda _: {11, 12})
    monkeypatch.setattr(memory_guard, 'usage', lambda _: SimpleNamespace(started=222))
    board.stalled_logs('owner', checkout, 900, now=1100)
    board.stalled_logs('owner', checkout, 900, now=1110)
    assert len(board.messages()) == 1
    assert board.messages()[0]['recipient'] == 'owner'
    monkeypatch.setattr(memory_guard, 'usage', lambda _: SimpleNamespace(started=333))
    os.utime(log, (150, 150));board.stalled_logs('owner', checkout, 900, now=1100)
    assert len(board.messages()) == 1
    monkeypatch.setattr(memory_guard, 'usage', lambda _: SimpleNamespace(started=222))
    health['time'] = 500;report.write_text(json.dumps(health))
    board.stalled_logs('owner', checkout, 900, now=1100)
    assert len(board.messages()) == 1
    health['time'] = 1090;report.write_text(json.dumps(health))
    holder['repo'] = str(cache / 'another-checkout')
    board.stalled_logs('owner', checkout, 900, now=1100)
    assert len(board.messages()) == 1


def test_wait_prints_full_batch_and_timeout_preserves_cursor(cache, capsys):
    register('review')
    broadcast = board.post('other', 'broadcast')
    args = parse_args(['board', 'wait', '--agent', 'review', '--timeout', '0', '--addressed-only'])
    assert board.main(args) == 3
    with board.database() as db:
        row = db.execute('SELECT cursor, pid FROM subscribers').fetchone()
        assert (row['cursor'], row['pid']) == (0, None)
    body = 'full body ' + 'z'*1200
    addressed = board.post('other', body, 'review')
    assert board.main(args) == 0
    output = capsys.readouterr().out
    assert body in output and f'#{addressed} ' in output and f'#{broadcast} ' not in output
    assert board.main(args) == 3
    with board.database() as db:
        assert db.execute('SELECT cursor FROM subscribers').fetchone()['cursor'] == addressed


def test_wait_monitors_owner_checkout_and_delivers_alert(cache, monkeypatch, capsys):
    monitored = []
    checkout = cache / 'owned-worktree'
    monkeypatch.setattr(board, 'render_board_changes', lambda: monitored.append('board'))
    def alert(agent, path, seconds):
        monitored.append(path)
        board.post('board-watch', 'inspect stalled compile', agent, 'alert')
    monkeypatch.setattr(board, 'stalled_logs', alert)
    args = parse_args(['board', 'wait', '--agent', 'review', '--timeout', '0',
                       '--addressed-only', '--checkout', str(checkout)])
    assert board.main(args) == 0
    assert monitored == ['board', checkout.resolve()]
    assert 'inspect stalled compile' in capsys.readouterr().out


def until(predicate, timeout=8):
    end = time.monotonic()+timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.1)
    raise AssertionError('subscriber did not reach the expected state')


def test_background_subscriber_duplicate_stop_and_restart(cache):
    target = cache / 'received.txt'
    # Local inert notification receiver: no agent wakeups or heavy jobs in tests.
    receiver = cache / 'receive.py'
    receiver.write_text('import sys\nfrom pathlib import Path\n'
                        'with Path(sys.argv[1]).open("a") as f: f.write(sys.argv[2]+"\\n")\n')
    command = json.dumps([sys.executable, str(receiver), str(target), '{message}'])
    args = parse_args(['board', 'subscribe', '--agent', 'review', '--background', '--interval', '1', '--notify', command])
    def stopped():
        with board.database() as db:
            row = db.execute('SELECT pid FROM subscribers WHERE agent="review"').fetchone()
            return row and row['pid'] is None
    try:
        assert board.main(args) == 0
        assert board.main(args) == 1  # Refuse a duplicate without disturbing the first subscriber.
        first = board.post('other', 'first handoff', 'review')
        until(lambda: target.exists() and 'first handoff' in target.read_text())
        assert board.main(parse_args(['board', 'unsubscribe', '--agent', 'review'])) == 0
        until(stopped)
        board.post('other', 'second handoff', 'review')
        assert board.main(args) == 0
        until(lambda: 'second handoff' in target.read_text())
        assert target.read_text().count(f'#{first} ') == 1
    finally:
        board.main(parse_args(['board', 'unsubscribe', '--agent', 'review']))
        until(stopped)
    assert not (cache / 'render.lock').exists()


def test_wait_heartbeat_exclusion_and_background_task_completion(cache):
    env = dict(os.environ, PYTHONPATH=str(board.paths.STUDIO))
    process = subprocess.Popen([sys.executable, '-m', 'atelier.cli', 'board', 'wait', '--agent', 'review',
                                '--timeout', '5', '--interval', '1'], env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    def armed():
        with board.database() as db:
            row = db.execute('SELECT pid, heartbeat FROM subscribers WHERE agent="review"').fetchone()
            return row and row['pid'] == process.pid and time.time()-row['heartbeat'] < 2
    try:
        until(armed)
        # The continuous subscriber and wait use exactly the same exclusion lock.
        with pytest.raises(ValueError, match='already has a subscriber'):
            with board.subscriber('review', board.paths.REPO):
                pass
        board.post('other', 'background task wakes on exit', 'review')
        out, err = process.communicate(timeout=6)
        assert process.returncode == 0 and 'background task wakes on exit' in out and not err
    finally:
        board.main(parse_args(['board', 'unsubscribe', '--agent', 'review']))
        process.communicate(timeout=6)
    with board.database() as db:
        assert db.execute('SELECT pid FROM subscribers').fetchone()['pid'] is None


def test_cli_attaches_files_and_reads_whole_threads(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path / 'cache'))
    clip = tmp_path / 'ramp clip.mp4'; clip.write_bytes(b'\0' * 2048)
    notes = tmp_path / 'notes.txt'; notes.write_text('left side first')
    root = board.post('review', 'Can someone check the ramp?', recipient='move-sets', topic='request')
    assert board.main(parse_args(['board', 'post', '--agent', 'move-sets', '--to', 'review', '--reply-to', str(root),
                                  '--attach', str(clip), '--attach', str(notes), 'Checked; clip attached.'])) == 0
    reply = int(capsys.readouterr().out)
    body = board.messages()[-1]['body']
    assert body.startswith('Checked; clip attached.\n\nAttachments (files on this machine):\n- ramp clip.mp4 (video/mp4, 2.0 KB): ')
    # The trailer names the stored copy, which agents can open directly.
    stored = Path(body.splitlines()[-2].rsplit(': ', 1)[1])
    assert stored.read_bytes() == clip.read_bytes() and stored.parent.parent.name == 'board-attachments'
    assert board.main(parse_args(['board', 'post', '--agent', 'review', '--attach', str(notes)])) == 0
    later = board.post('review', 'Thanks!', recipient='move-sets', reply_to=reply)
    capsys.readouterr()
    assert board.main(parse_args(['board', 'thread', str(later)])) == 0
    assert [json.loads(line)['id'] for line in capsys.readouterr().out.splitlines()] == [root, reply, later]
    assert board.main(parse_args(['board', 'thread', '99999'])) == 1
    assert board.main(parse_args(['board', 'post', '--agent', 'review', '--reply-to', '99999', 'x'])) == 1
    assert board.main(parse_args(['board', 'post', '--agent', 'review', '--attach', str(tmp_path / 'missing.png')])) == 1


def test_post_to_all_agents_is_one_grouped_broadcast_for_addressed_listeners(cache, capsys):
    register('one'); register('two'); register('poster')
    assert board.main(parse_args(['board', 'post', '--agent', 'poster', '--all-agents', 'Freeze canonical.'])) == 0
    ids = [int(x) for x in capsys.readouterr().out.split()]
    rows = board.messages()
    assert [row['recipient'] for row in rows] == ['one', 'two'] and [row['id'] for row in rows] == ids
    # Addressed-only listeners get their copy, and every copy knows the whole audience.
    assert board.messages(agent='one', addressed_only=True)[0]['audience'] == ['one', 'two']
    assert board.main(parse_args(['board', 'post', '--agent', 'poster', '--all-agents', '--to', 'one', 'x'])) == 1


def test_board_modules_import_in_any_order():
    import subprocess, sys
    for first, second in (('board', 'board_cli'), ('board_cli', 'board'), ('board_store', 'board_cli')):
        code = f'import atelier.{first}, atelier.{second}; import atelier.board; assert atelier.board.main is atelier.board_cli.main'
        result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
