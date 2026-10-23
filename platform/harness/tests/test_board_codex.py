"""Active-turn routing and races must never degrade into an invisible queue."""
import json
import tempfile
import threading
import time
from pathlib import Path

import pytest
from websockets.sync.server import unix_serve

from atelier.harness import board_codex


class Fake:
    def __init__(self, replies, reopened=(), deadline=None):
        self.replies = iter(replies)
        self.calls = []
        self.reopened = list(reopened)
        self.deadline = time.monotonic() + 30 if deadline is None else deadline

    def call(self, method, params):
        self.calls.append((method, params))
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def reopen(self, budget=None):
        if not self.reopened:
            raise board_codex.TransportError('no fake connection')
        return self.reopened.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


ACTIVE = {'thread': {'status': {'type': 'active'}}}
IDLE = {'thread': {'status': {'type': 'idle'}}}
NOT_LOADED = {'thread': {'status': {'type': 'notLoaded'}}}
TURN = {'data': [{'id': 'turn-1', 'status': 'inProgress'}]}


def test_busy_codex_steers_current_turn_and_never_queues():
    fake = Fake([ACTIVE, TURN, {'turnId': 'turn-1'}])
    assert board_codex.notify(fake, 'existing', 'new handoff') == 'steered'
    assert [method for method, _ in fake.calls] == ['thread/read', 'thread/turns/list', 'turn/steer']
    steer = fake.calls[-1][1]
    assert steer['expectedTurnId'] == 'turn-1'
    assert steer['input'][0]['text'] == 'new handoff'
    assert set(steer) == {'threadId', 'expectedTurnId', 'input', 'clientUserMessageId'}
    retry = Fake([ACTIVE, TURN, {'turnId': 'turn-1'}])
    board_codex.notify(retry, 'existing', 'new handoff')
    assert retry.calls[-1][1]['clientUserMessageId'] == steer['clientUserMessageId']


def test_idle_session_wakes_in_same_thread_without_settings_override():
    fake = Fake([IDLE, {}])
    assert board_codex.notify(fake, 'existing', 'handoff') == 'woke_idle'
    assert fake.calls[-1][0] == 'turn/start'
    assert fake.calls[-1][1]['threadId'] == 'existing'
    assert set(fake.calls[-1][1]) == {'threadId', 'input', 'clientUserMessageId'}


def test_turn_ending_race_refreshes_status_before_waking_idle():
    fake = Fake([ACTIVE, TURN, board_codex.RpcError({'code': -1}), IDLE, {}])
    assert board_codex.notify(fake, 'existing', 'handoff') == 'woke_idle'
    assert [method for method, _ in fake.calls] == ['thread/read', 'thread/turns/list', 'turn/steer', 'thread/read', 'turn/start']


def test_idle_becoming_busy_race_steers_new_turn():
    fake = Fake([IDLE, board_codex.RpcError({'code': -1}), ACTIVE, TURN, {}])
    assert board_codex.notify(fake, 'existing', 'handoff') == 'steered'


def test_not_loaded_thread_resumes_polls_and_delivers_on_fresh_connections(monkeypatch):
    monkeypatch.setattr(board_codex, 'WAKE_POLL_SECONDS', 0.)
    delivery = Fake([IDLE, {}])
    probe = Fake([IDLE])
    first_probe = Fake([NOT_LOADED])
    resume = Fake([{}])
    initial = Fake([NOT_LOADED], reopened=[resume, first_probe, probe, delivery])
    assert board_codex.notify(initial, 'existing', 'handoff') == 'woke_idle'
    assert resume.calls == [('thread/resume', {'threadId': 'existing'})]
    assert [method for method, _ in delivery.calls] == ['thread/read', 'turn/start']
    assert all('thread/resume' not in method for method, _ in delivery.calls)


def test_not_loaded_resume_connection_drop_still_delivers(monkeypatch):
    monkeypatch.setattr(board_codex, 'WAKE_POLL_SECONDS', 0.)
    delivery = Fake([IDLE, {}])
    probe = Fake([IDLE])
    resume = Fake([board_codex.TransportError('dropped after load')])
    initial = Fake([NOT_LOADED], reopened=[resume, probe, delivery])
    assert board_codex.notify(initial, 'existing', 'handoff') == 'woke_idle'


def test_not_loaded_thread_that_stays_unloaded_is_failure_not_queue():
    delivery = Fake([NOT_LOADED])
    resume = Fake([{}])
    initial = Fake([NOT_LOADED], reopened=[resume, delivery],
                   deadline=time.monotonic() + .5)
    with pytest.raises(board_codex.TransportError, match='retained'):
        board_codex.notify(initial, 'existing', 'handoff')
    assert all('queue' not in method for method, _ in initial.calls + delivery.calls)


def test_unavailable_or_racing_session_is_failure_not_queue_success():
    fake = Fake([{'thread': {'status': {'type': 'error'}}}])
    with pytest.raises(board_codex.TransportError):
        board_codex.notify(fake, 'existing', 'handoff')
    fake = Fake([ACTIVE, {'data': []}, ACTIVE, {'data': []}])
    with pytest.raises(board_codex.TransportError):
        board_codex.notify(fake, 'existing', 'handoff')
    assert all('queue' not in method for method, _ in fake.calls)


def test_actual_unix_websocket_rpc_initializes_ignores_notifications_and_steers():
    calls = []
    def handle(connection):
        for raw in connection:
            request = json.loads(raw)
            method = request['method']; calls.append(method)
            if 'id' not in request:
                continue
            result = {'initialize': {}, 'thread/read': ACTIVE, 'thread/turns/list': TURN,
                      'turn/steer': {'turnId': 'turn-1'}}[method]
            connection.send(json.dumps({'method': 'test/notification', 'params': {}}))
            connection.send(json.dumps({'id': request['id'], 'result': result}))
    # Short socket path also works under macOS's Unix socket path-length limit.
    with tempfile.TemporaryDirectory(prefix='board-rpc-') as directory:
        path = str(Path(directory) / 'rpc.sock')
        with unix_serve(handle, path=path) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with board_codex.Client(sock=path) as client:
                    assert board_codex.notify(client, 'existing', 'handoff') == 'steered'
            finally:
                server.shutdown(); thread.join(timeout=3)
    assert calls == ['initialize', 'initialized', 'thread/read', 'thread/turns/list', 'turn/steer']


class Daemons:
    """Fake running daemons per Codex home: each knows its own threads, like separate app-server homes."""
    def __init__(self, directory, owned):
        self.servers, self.sockets, self.reads, self.steers, self.timeouts = [], {}, [], [], []
        self.lookup_delay = 0.
        for home, threads in owned.items():
            if threads is None:   # an installed home whose daemon isn't running
                continue
            path = str(Path(directory) / f'{home}.sock')
            self.sockets[home] = path
            server = unix_serve(self.handler(home, threads), path=path)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.servers.append(server)

    def handler(self, home, threads):
        def handle(connection):
            for raw in connection:
                request = json.loads(raw)
                if 'id' not in request:
                    continue
                method, params = request['method'], request['params']
                if method == 'initialize':
                    reply = {'result': {}}
                elif threads == 'hang':   # accepts the connection, then never answers
                    continue
                elif params['threadId'] not in threads:
                    reply = {'error': {'code': -32600, 'message': 'thread not loaded'}}
                elif method == 'thread/read':
                    self.reads.append(home)
                    reply = {'result': ACTIVE}
                elif method == 'thread/turns/list':
                    reply = {'result': TURN}
                else:
                    self.steers.append((home, method))
                    reply = {'result': {'turnId': 'turn-1'}}
                connection.send(json.dumps({'id': request['id'], **reply}))
        return handle

    def version(self, command, **options):
        self.timeouts.append(options['timeout'])
        time.sleep(min(self.lookup_delay, options['timeout']))
        home = Path(options['env']['CODEX_HOME']).name
        status = {'status': 'running', 'socketPath': self.sockets[home]} if home in self.sockets else {'status': 'stopped'}
        return type('Done', (), {'stdout': json.dumps(status)})()

    def close(self):
        for server in self.servers:
            server.shutdown()


@pytest.fixture
def daemons(monkeypatch):
    made = []
    def make(owned):
        directory = tempfile.mkdtemp(prefix='board-d-')
        fakes = Daemons(directory, owned)
        monkeypatch.setattr(board_codex.subprocess, 'run', fakes.version)
        made.append(fakes)
        return fakes
    yield make
    for fakes in made:
        fakes.close()


def test_discovery_routes_each_thread_to_its_owning_daemon(daemons):
    fakes = daemons({'main': ['main-thread'], 'opencodex': ['ocx-thread']})
    homes = [Path('/h/main'), Path('/h/opencodex')]
    for thread, home in (('ocx-thread', 'opencodex'), ('main-thread', 'main')):
        with board_codex.connect(thread, homes=homes) as client:
            assert board_codex.notify(client, thread, 'handoff') == 'steered'
        assert fakes.steers[-1] == (home, 'turn/steer')
    assert len(fakes.steers) == 2   # one delivery each, never a second writer


def test_ambiguous_or_missing_owner_fails_and_never_writes(daemons):
    fakes = daemons({'main': ['shared'], 'opencodex': ['shared']})
    homes = [Path('/h/main'), Path('/h/opencodex')]
    with pytest.raises(board_codex.TransportError, match='more than one daemon.*retained'):
        board_codex.connect('shared', homes=homes)
    with pytest.raises(board_codex.TransportError, match='No running Codex daemon.*retained'):
        board_codex.connect('elsewhere', homes=homes)
    assert fakes.steers == []


def test_unreachable_candidate_without_owner_is_retained_not_misrouted(daemons):
    fakes = daemons({'main': ['main-thread'], 'opencodex': None})
    with pytest.raises(board_codex.TransportError, match='owner unavailable.*retained'):
        board_codex.connect('ocx-thread', homes=[Path('/h/main'), Path('/h/opencodex')])
    assert fakes.steers == []
    # A stopped second home doesn't block delivery to a thread the running daemon owns.
    with board_codex.connect('main-thread', homes=[Path('/h/main'), Path('/h/opencodex')]) as client:
        assert board_codex.notify(client, 'main-thread', 'handoff') == 'steered'


def test_explicit_socket_then_home_take_precedence_over_discovery(daemons):
    fakes = daemons({'main': ['main-thread'], 'opencodex': ['ocx-thread']})
    with board_codex.connect('ocx-thread', sock=fakes.sockets['opencodex'], homes=[]) as client:
        board_codex.notify(client, 'ocx-thread', 'handoff')
    assert fakes.reads == ['opencodex']   # no probe of the main daemon
    with board_codex.connect('ocx-thread', home=Path('/h/opencodex'), homes=[]) as client:
        board_codex.notify(client, 'ocx-thread', 'handoff')
    assert fakes.reads == ['opencodex', 'opencodex']
    # A pinned home is honoured even when it is the wrong one: the daemon refuses, cursor retained.
    with pytest.raises(board_codex.RpcError):
        with board_codex.connect('ocx-thread', home=Path('/h/main'), homes=[]) as client:
            board_codex.notify(client, 'ocx-thread', 'handoff')


def test_cli_failure_exit_retains_the_subscriber_cursor(daemons, capsys):
    from atelier.cli import parse_args
    from atelier.harness import board_cli
    daemons({'main': ['main-thread'], 'opencodex': ['ocx-thread']})
    pinned = parse_args(['board', 'notify-codex', '--thread', 'ocx-thread', '--codex-home', '/h/main', 'hi'])
    assert board_cli.main(pinned) == 1
    assert 'retry' in capsys.readouterr().err
    assert board_cli.main(parse_args(['board', 'notify-codex', '--thread', 'nowhere', 'hi'])) == 1
    assert 'cursor retained' in capsys.readouterr().err


def test_candidate_homes_include_inherited_default_and_daemon_homes(tmp_path, monkeypatch):
    monkeypatch.setattr(board_codex.Path, 'home', lambda: tmp_path)
    (tmp_path / '.codex-opencodex' / 'app-server-daemon').mkdir(parents=True)
    (tmp_path / '.codex-notes').mkdir()   # no daemon: not a candidate
    monkeypatch.setenv('CODEX_HOME', str(tmp_path / 'custom'))
    assert board_codex.codex_homes() == [(tmp_path / p).resolve() for p in ('custom', '.codex', '.codex-opencodex')]
    monkeypatch.delenv('CODEX_HOME')
    assert board_codex.codex_homes() == [(tmp_path / p).resolve() for p in ('.codex', '.codex-opencodex')]


def test_hung_candidate_spends_only_the_shared_discovery_budget(daemons):
    daemons({'stuck': 'hang', 'opencodex': ['ocx-thread']})
    started = time.monotonic()
    with pytest.raises(board_codex.TransportError, match='owner unavailable.*retained'):
        board_codex.locate('ocx-thread', homes=[Path('/h/stuck'), Path('/h/opencodex')], budget=1.)
    assert time.monotonic()-started < 1.6
    # An owner found before the hung daemon is still used once the budget ends.
    started = time.monotonic()
    found = board_codex.locate('ocx-thread', homes=[Path('/h/opencodex'), Path('/h/stuck')], budget=1.)
    assert found.endswith('opencodex.sock') and time.monotonic()-started < 1.6


def test_many_slow_lookups_stay_inside_budget_and_retain_cursor(daemons):
    fakes = daemons({f'home{i}': None for i in range(12)})
    fakes.lookup_delay = .3
    started = time.monotonic()
    with pytest.raises(board_codex.TransportError, match='retained'):
        board_codex.locate('thread', homes=[Path(f'/h/home{i}') for i in range(12)], budget=1.)
    assert time.monotonic()-started < 1.6
    assert len(fakes.timeouts) < 12 and all(t <= 1. for t in fakes.timeouts)


def test_delivery_keeps_its_reserved_budget_after_discovery(daemons, monkeypatch):
    fakes = daemons({'stuck': 'hang', 'opencodex': ['ocx-thread']})
    asked = []
    real = board_codex.locate
    monkeypatch.setattr(board_codex, 'locate', lambda *a, budget: asked.append(budget) or real(*a, budget=budget))
    started = time.monotonic()
    with board_codex.connect('ocx-thread', homes=[Path('/h/opencodex'), Path('/h/stuck')], budget=3.) as client:
        assert board_codex.notify(client, 'ocx-thread', 'handoff') == 'steered'
        assert client.deadline-started > 3.*(1-board_codex.DISCOVERY_SHARE)-.05   # reserved share kept
    assert asked == [pytest.approx(1.2)] and fakes.steers == [('opencodex', 'turn/steer')]
    assert time.monotonic()-started < 3.5
    board_codex.connect('x', sock=fakes.sockets['opencodex']).close()
    assert board_codex.DELIVERY_BUDGET*(1-board_codex.DISCOVERY_SHARE) >= 15 and board_codex.DELIVERY_BUDGET < 30


def test_connection_cleanup_never_outlives_the_client_deadline(daemons):
    fakes = daemons({'stuck': 'hang'})
    spent = board_codex.Client(sock=fakes.sockets['stuck'], budget=.2)
    time.sleep(.25)
    spent.close()
    assert spent.socket.close_timeout == 0.
    fresh = board_codex.Client(sock=fakes.sockets['stuck'], budget=20)
    fresh.close()
    assert 0. < fresh.socket.close_timeout <= 1.
