"""Live-session selection without Unreal: fake bridges on loopback answer /identity, /state and /python."""
import json, os, socket, subprocess, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from atelier import live, live_sessions, paths
from atelier.live_sessions import SessionError


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path / 'cache'))
    for name in ('ATELIER_LIVE_SESSION', 'ATELIER_LIVE_GAME', 'ATELIER_LIVE_CHECKOUT', 'ATELIER_LIVE_PORT'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(live, 'URL', None)
    monkeypatch.setattr(live, '_selected', None)
    monkeypatch.setattr(live_sessions, 'revision', lambda root: 'f' * 40)


def checkout(tmp_path, name, game='alpha'):
    """A fake checkout holding games/<game>/unreal/<Project>.uproject."""
    project = tmp_path / name / 'games' / game / 'unreal' / f'{game.title()}.uproject'
    project.parent.mkdir(parents=True)
    project.write_text('{}')
    return tmp_path / name, project


class Bridge:
    """A fake live bridge: answers like the plugin, and records every command it received."""
    def __init__(self, port, identity):
        self.identity, self.received = identity, []
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass

            def reply(self, value, code=200):
                data = json.dumps(value).encode()
                self.send_response(code); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)

            def do_GET(self):
                if self.path == '/identity' and bridge.identity is not None:
                    return self.reply(bridge.identity)
                if self.path == '/state':
                    bridge.received.append('state'); return self.reply({'fps': 60})
                self.reply({}, 404)

            def do_POST(self):
                body = self.rfile.read(int(self.headers['Content-Length'])).decode()
                bridge.received.append(body)
                self.reply({'ok': True, 'output': '', 'result': 'None'})

        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown(); self.server.server_close()


@pytest.fixture
def bridges():
    opened = []
    def start(record, **identity):
        value = dict(session=record['session'], pid=os.getpid(), project=record['project_name'],
                     project_file=str(Path(record['checkout']) / record['project']))
        value.update(identity)
        opened.append(Bridge(record['port'], value))
        return opened[-1]
    yield start
    for bridge in opened:
        bridge.close()


def session(tmp_path, monkeypatch, name='a', game='alpha', **kwargs):
    root = tmp_path / name
    project = root / 'games' / game / 'unreal' / f'{game.title()}.uproject'
    if not project.exists():
        checkout(tmp_path, name, game)
    return live_sessions.create(game, project, checkout=root, **kwargs), root


def test_two_sessions_get_distinct_ports_and_commands_reach_only_the_named_one(tmp_path, monkeypatch, bridges):
    first, root = session(tmp_path, monkeypatch, game='alpha')
    second, _ = session(tmp_path, monkeypatch, game='beta')
    assert first['port'] != second['port'] and live_sessions.LEGACY_PORT not in (first['port'], second['port'])
    assert first['session'] != second['session']
    one, two = bridges(first), bridges(second)
    monkeypatch.setattr(paths, 'REPO', root)
    assert live.main(['--session', second['session'][:8], 'py', 'x = 1']) == 0
    assert live.main(['--game', 'alpha', 'state']) == 0
    assert two.received == [live.python_body('x = 1')] and one.received == ['state']
    # Two live sessions in this checkout and no selection: an error, never a guess.
    monkeypatch.setattr(live, '_selected', None)
    with pytest.raises(SessionError, match='2 live sessions'):
        live.select()
    assert live.main(['state']) == 1


def test_shot_goes_to_the_named_session_only(tmp_path, monkeypatch, bridges):
    first, root = session(tmp_path, monkeypatch, game='alpha')
    second, _ = session(tmp_path, monkeypatch, game='beta')
    one, two = bridges(first), bridges(second)
    monkeypatch.setattr(paths, 'REPO', root)
    out = tmp_path / 'shot.png'
    monkeypatch.setattr(live.time, 'sleep', lambda s: out.write_bytes(b'png'))
    assert live.main(['--session', first['session'], 'shot', str(out)]) == 0
    assert one.received == [live.python_body(f'import unreal\nunreal.LiveLibrary.screenshot(r"{out}")')]
    assert two.received == []


def test_the_one_live_session_of_this_checkout_is_the_default(tmp_path, monkeypatch, bridges):
    record, root = session(tmp_path, monkeypatch)
    other, other_root = session(tmp_path, monkeypatch, name='b')
    bridge = bridges(record); bridges(other)
    monkeypatch.setattr(paths, 'REPO', root)
    assert live.request('/state') == {'fps': 60}
    assert bridge.received == ['state']


def test_stale_record_is_rejected_and_pruned_while_live_records_stay(tmp_path, monkeypatch, bridges):
    record, root = session(tmp_path, monkeypatch)
    alive, _ = session(tmp_path, monkeypatch, game='beta')
    bridges(record)   # even an answering bridge cannot revive a record whose launcher is gone
    stale = dict(record, launcher=dict(record['launcher'], start=-1))
    live_sessions._write(stale)
    monkeypatch.setattr(paths, 'REPO', root)
    with pytest.raises(SessionError, match='stale'):
        live.select(session=record['session'])
    assert [r['session'] for r in live_sessions.prune()] == [record['session']]
    assert [r['session'] for r in live_sessions.records()] == [alive['session']]


def test_a_launcher_pid_reused_by_another_process_is_gone():
    sleeper = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    try:
        start = live_sessions.process_start(sleeper.pid)
        assert live_sessions.launcher_state({'launcher': {'pid': sleeper.pid, 'start': start}}) == 'live'
        assert live_sessions.launcher_state({'launcher': {'pid': sleeper.pid, 'start': 'earlier'}}) == 'gone'
        assert live_sessions.descends(sleeper.pid, os.getpid()) and not live_sessions.descends(os.getpid(), sleeper.pid)
    finally:
        sleeper.kill(); sleeper.wait()
    assert live_sessions.launcher_state({'launcher': {'pid': sleeper.pid, 'start': start}}) == 'gone'


def test_wrong_project_or_checkout_is_rejected(tmp_path, monkeypatch, bridges):
    record, root = session(tmp_path, monkeypatch)
    other_root, other_project = checkout(tmp_path, 'b')
    bridges(record, project_file=str(other_project))   # same session ID, another checkout's project file
    monkeypatch.setattr(paths, 'REPO', root)
    with pytest.raises(SessionError, match='runs project'):
        live.select()
    monkeypatch.setattr(live, '_selected', None)
    second, _ = session(tmp_path, monkeypatch, game='beta')
    bridges(second, project='Alpha')
    with pytest.raises(SessionError, match='runs project'):
        live.select(game='beta')
    # A record launched from another checkout is not selected from this one, even by ID.
    monkeypatch.setattr(paths, 'REPO', other_root)
    with pytest.raises(SessionError, match='was launched from'):
        live.select(session=record['session'])
    with pytest.raises(SessionError, match='no live session'):
        live.select()


def test_an_occupied_port_or_a_missing_identity_is_rejected(tmp_path, monkeypatch, bridges):
    record, root = session(tmp_path, monkeypatch)
    monkeypatch.setattr(paths, 'REPO', root)
    with pytest.raises(SessionError, match='nothing answers'):
        live.select()
    impostor = bridges(record, session='0' * 32)
    with pytest.raises(SessionError, match='held by another process'):
        live.select()
    impostor.identity = None   # an old game: no /identity route
    with pytest.raises(SessionError, match='without a live identity'):
        live.select()
    impostor.identity = dict(session=record['session'], pid=1, project=record['project_name'],
                             project_file=str(root / record['project']))
    with pytest.raises(SessionError, match='not started by the recorded launcher'):
        live.select()
    assert impostor.received == []


def test_explicit_port_is_the_only_legacy_route(tmp_path, monkeypatch, bridges):
    record, root = session(tmp_path, monkeypatch)
    monkeypatch.setattr(paths, 'REPO', root)
    legacy = Bridge(live_sessions.free_port(), None)
    try:
        assert live.main(['--port', str(legacy.server.server_address[1]), 'state']) == 0
        assert legacy.received == ['state']
        # A port a session owns is verified like the session itself.
        with pytest.raises(SessionError, match='nothing answers'):
            live.select(port=record['port'])
    finally:
        legacy.close()


def test_requested_port_already_owned_is_refused(tmp_path, monkeypatch):
    record, root = session(tmp_path, monkeypatch)
    with pytest.raises(SessionError, match='already belongs'):
        session(tmp_path, monkeypatch, game='alpha', port=record['port'])


def test_records_name_the_launch(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_AGENT', 'tester')
    record, root = session(tmp_path, monkeypatch, task='atelier play alpha')
    assert record['project'] == 'games/alpha/unreal/Alpha.uproject' and record['project_name'] == 'Alpha'
    assert record['checkout_id'] == live_sessions.checkout_id(root) and record['revision'] == 'f' * 40
    assert record['launcher']['pid'] == os.getpid() and record['agent'] == 'tester'
    assert live_sessions.launch_args(record) == [f'-liveport={record["port"]}', f'-livesession={record["session"]}']
    live_sessions.remove(record)
    assert live_sessions.records() == []


def test_a_launch_holds_its_record_only_while_the_game_runs(tmp_path, monkeypatch):
    root, project = checkout(tmp_path, 'a')
    with pytest.raises(RuntimeError, match='game crashed'):
        with live_sessions.launched('alpha', project, ['-game', '-liveport=8847'], checkout=root) as (args, record):
            assert args == ['-game', '-liveport=8847', f'-livesession={record["session"]}']
            assert record['port'] == 8847 and live_sessions.records() == [record]
            raise RuntimeError('game crashed')
    assert live_sessions.records() == []
    with live_sessions.launched('alpha', project, ['-nolive'], checkout=root) as (args, record):
        assert args == ['-nolive'] and record is None and live_sessions.records() == []
    with pytest.raises(SessionError, match='assigns'):
        with live_sessions.launched('alpha', project, ['-livesession=abc'], checkout=root):
            pass


def test_qa_environment_selects_the_named_session(tmp_path, monkeypatch, bridges):
    first, root = session(tmp_path, monkeypatch, game='alpha')
    second, _ = session(tmp_path, monkeypatch, game='alpha', port=None)
    one, two = bridges(first), bridges(second)
    monkeypatch.setattr(paths, 'REPO', root)
    monkeypatch.setenv('ATELIER_LIVE_GAME', 'alpha')
    monkeypatch.setenv('ATELIER_LIVE_SESSION', second['session'])
    assert live.request('/state') == {'fps': 60}
    assert two.received == ['state'] and one.received == []
