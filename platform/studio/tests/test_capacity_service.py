from concurrent.futures import ThreadPoolExecutor
import json
import os
import sqlite3
import subprocess
import sys
import threading

import pytest

from atelier.capacity_service import Observation, ShadowService, main


class World:
    def __init__(self):
        self.now = 10
        self.processes = {f'{pid}:1': 'alive' for pid in range(10, 100)}
        self.edges = []
        self.measured = {}
        self.allocated = {}
        self.healthy = self.complete = True
        self.available = self.disk = 100_000
        self.at = None

    def observe(self, now):
        return Observation(now if self.at is None else self.at, self.healthy, self.complete,
                           self.available, self.disk, self.processes.copy(), tuple(self.edges),
                           self.measured.copy(), self.allocated.copy())


class Client:
    def __init__(self, path, world):
        self.world = world
        self.service = ShadowService(path, observe=world.observe)
        self.sequence = 0
        self.epoch = 1

    def call(self, action, **arguments):
        self.sequence += 1
        result = self.service.apply(dict(id=f'op-{self.sequence}', action=action, epoch=self.epoch, **arguments),
                                    now=self.world.now)
        assert result['admission'] is False and result['mode'] == 'shadow'
        return result

    def submit(self, rid, memory=1000, *, pid=10, owner=None, **kwargs):
        return self.call('submit', request_id=rid, owner=owner or rid, checkout='checkout-' + rid,
                         resources={'memory_mib': memory, **kwargs.pop('resources', {})},
                         launcher=[pid, 1], **kwargs)

    def schedule(self):
        return self.call('schedule')['decisions']

    def records(self):
        return {r['request_id']: r for r in self.call('status')['requests']}


@pytest.fixture
def client(tmp_path):
    world = World()
    client = Client(tmp_path / 'shadow.sqlite', world)
    client.call('init', total=dict(memory_mib=10000, cpu_millis=4000, temp_mib=10000, io_slots=2, gpu_mib=3000),
                reserve=dict(memory_mib=1000, temp_mib=1000))
    return client


def allocate(client, rid='job', **kwargs):
    client.submit(rid, **kwargs)
    decisions = client.schedule()
    return next(d['token'] for d in decisions if d['request_id'] == rid)


def register(client, token, rid='job'):
    client.world.edges = [('10:1', '20:1')]
    client.call('register', request_id=rid, token=token, child=[20, 1])
    client.world.measured[rid] = 500
    client.world.allocated[rid] = 0
    client.call('running', request_id=rid, token=token, guard_ready=True)


def test_durable_full_lifecycle_and_shadow_tokens(client):
    token = allocate(client)
    assert token.startswith('shadow.')
    with pytest.raises(ValueError, match='registration'):
        client.call('running', request_id='job', token=token, guard_ready=True)
    register(client, token)
    # Reopening is a client reconnect; only explicit restart changes the service epoch.
    client.service = ShadowService(client.service.database, observe=client.world.observe)
    assert client.records()['job']['state'] == 'running'
    assert 'token_hash' not in client.records()['job']
    client.world.processes.update({'10:1': 'dead', '20:1': 'dead'})
    assert client.call('release', request_id='job', token=token)['result'] == 'released'
    client.world.now += 10
    client.call('ready', request_id='job', launcher=[30, 1])
    assert client.records()['job']['ready_at'] == 10
    assert client.records()['job']['identities'] == []


@pytest.mark.parametrize('child_state', ['unknown', None])
def test_missing_retained_child_freezes_new_reservations(client, child_state):
    token = allocate(client, locks=['checkout-one'])
    register(client, token)
    if child_state is None:
        client.world.processes.pop('20:1')
        client.world.edges = []
    else:
        client.world.processes['20:1'] = child_state
    client.submit('next', pid=30)
    result = client.call('schedule')
    assert result['result'] == 'wait' and result['reasons'] == ['ownership reconciliation required']
    records = client.records()
    assert records['job']['state'] == 'uncertain'
    assert records['job']['resources']['memory_mib'] == 1000 and records['job']['locks'] == ['checkout-one']
    assert records['next']['state'] == 'queued'


def test_reserved_replacement_cannot_reduce_below_observed_usage(client):
    token = allocate(client, locks=['checkout-one'])
    client.world.measured['job'] = 500
    client.world.allocated['job'] = 0
    previous = client.records()['job']
    result = client.call('replace', request_id='job', token=token,
                         resources=dict(memory_mib=100), locks=['replacement'])
    assert result['result'] == 'wait'
    assert 'replacement ceiling lacks observed memory headroom' in result['reasons']
    assert client.records()['job'] == previous


def test_cancelling_released_request_cannot_hide_its_launcher_reset(client):
    token = allocate(client)
    client.world.processes['10:1'] = 'dead'
    assert client.call('release', request_id='job', token=token)['result'] == 'released'
    with pytest.raises(ValueError, match='already terminal'):
        client.call('cancel', request_id='job')
    client.call('ready', request_id='job', launcher=[30, 1])
    assert client.records()['job']['launcher'] == '30:1'
    decision, = client.schedule()
    assert decision['result'] == 'reserved'


@pytest.mark.parametrize('resources,reason', [
    ({'cpu_millis': 4001}, 'cpu_millis'), ({'temp_mib': 9001}, 'temp_mib'),
    ({'io_slots': 3}, 'io_slots'), ({'gpu_mib': 3001, 'memory_mib': 4000}, 'gpu_mib'),
])
def test_every_resource_dimension_is_accounted(client, resources, reason):
    client.submit('oversized', resources=resources)
    decision, = client.schedule()
    assert decision['result'] == 'cannot-fit' and reason in decision['reasons']
    assert client.records()['oversized']['state'] == 'queued'


def test_named_locks_and_performance_exclude_otherwise_fitting_work(client):
    allocate(client, 'one', locks=['checkout-shared'])
    client.submit('two', pid=11, locks=['checkout-shared'])
    client.submit('performance', pid=12, performance=True)
    decisions = {d['request_id']: d for d in client.schedule()}
    assert decisions['two']['reasons'] == ['lock:checkout-shared']
    assert 'performance window must drain first' in decisions['performance']['reasons']


@pytest.mark.parametrize('memory,locks', [(7000, []), (1000, ['exclusive-checkout'])])
def test_actual_concurrent_sqlite_clients_cannot_double_allocate(client, memory, locks):
    client.submit('one', memory=memory, locks=locks)
    client.submit('two', memory=memory, pid=11, locks=locks)
    barrier = threading.Barrier(2)

    def schedule(index):
        service = ShadowService(client.service.database, observe=client.world.observe)
        barrier.wait(timeout=5)
        return service.apply(dict(id=f'parallel-{index}', epoch=1, action='schedule'), now=10)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(schedule, range(2)))
    assert sum(d['result'] == 'reserved' for r in results for d in r['decisions']) == 1
    assert sum(r['state'] == 'reserved' for r in client.records().values()) == 1


def test_atomic_refused_upgrade_cannot_queue_while_holding(client):
    token = allocate(client, 'one', locks=['checkout-a'])
    allocate(client, 'two', pid=11, locks=['compiler'])
    result = client.call('replace', request_id='one', token=token,
                         resources=dict(memory_mib=8000), locks=['checkout-a', 'compiler'])
    assert result['result'] == 'wait' and 'lock:compiler' in result['reasons']
    before = client.records()['one']
    assert before['resources']['memory_mib'] == 1000 and before['locks'] == ['checkout-a']
    for action in ('ready', 'cancel'):
        with pytest.raises(ValueError, match='release all'):
            client.call(action, request_id='one')
    assert client.records()['one'] == before


def test_successful_replacement_changes_vector_and_locks_together(client):
    token = allocate(client, locks=['old'])
    client.call('replace', request_id='job', token=token, resources=dict(memory_mib=2000), locks=['new'])
    record = client.records()['job']
    assert record['resources']['memory_mib'] == 2000 and record['locks'] == ['new']


def test_crash_rolls_back_allocations_locks_fairness_and_receipt(client):
    client.submit('job', locks=['checkout'])
    operation = dict(id='crash', action='schedule', epoch=1)

    def crash():
        raise RuntimeError('injected before commit')

    client.service.before_commit = crash
    with pytest.raises(RuntimeError):
        client.service.apply(operation, now=10)
    client.service.before_commit = None
    assert client.records()['job']['state'] == 'queued'
    first = client.service.apply(operation, now=10)
    assert first == client.service.apply(operation, now=999)
    assert first['decisions'][0]['result'] == 'reserved'
    with pytest.raises(ValueError, match='different content'):
        client.service.apply({**operation, 'action': 'restart'}, now=10)


def test_process_death_inside_transaction_recovers_without_a_partial_grant(client):
    client.submit('job', locks=['checkout'])
    script = '''
import os, sys
from atelier.capacity_service import Observation, ShadowService
service = ShadowService(sys.argv[1], observe=lambda now: Observation(
    now, True, True, 100000, 100000, {'10:1': 'alive'}), before_commit=lambda: os._exit(71))
service.apply(dict(id='killed', action='schedule', epoch=1), now=10)
'''
    result = subprocess.run([sys.executable, '-c', script, str(client.service.database)])
    assert result.returncode == 71
    assert client.records()['job']['state'] == 'queued'
    assert client.schedule()[0]['result'] == 'reserved'


def test_restart_fences_client_and_retains_detached_child_charge(client):
    token = allocate(client)
    register(client, token)
    client.world.edges.append(('20:1', '30:1'))
    client.call('heartbeat', request_id='job', token=token)
    client.epoch = client.call('restart')['epoch']
    client.world.processes.update({'10:1': 'dead', '20:1': 'dead'})
    with pytest.raises(ValueError, match='epoch'):
        client.service.apply(dict(id='stale', epoch=1, action='release', request_id='job', token=token), now=10)
    assert client.call('reconcile')['result'] == 'wait'
    record = client.records()['job']
    assert record['state'] == 'uncertain' and '30:1' in record['identities']
    client.world.processes['30:1'] = 'dead'
    assert client.call('reconcile')['result'] == 'reconciled'
    assert client.records()['job']['state'] == 'released'


def test_pid_reuse_and_unknown_observations_never_prove_exit(client):
    token = allocate(client)
    register(client, token)
    client.world.processes.pop('20:1')
    client.world.edges = []
    client.world.processes.update({'10:1': 'dead', '20:2': 'alive'})
    assert client.call('release', request_id='job', token=token)['result'] == 'wait'
    assert client.records()['job']['state'] == 'uncertain'
    client.world.processes['20:1'] = 'dead'
    assert client.call('release', request_id='job', token=token)['result'] == 'released'


def test_unrelated_reused_pid_cannot_register_as_the_actual_child(client):
    token = allocate(client)
    client.world.edges = [('10:1', '20:1')]
    client.world.processes['20:2'] = 'alive'
    with pytest.raises(ValueError, match='ownership'):
        client.call('register', request_id='job', token=token, child=[20, 2])


@pytest.mark.parametrize('change', ['stale', 'future', 'pressure', 'incomplete', 'disk'])
def test_missing_stale_or_unsafe_pressure_fails_closed(client, change):
    client.submit('job')
    if change == 'stale': client.world.now = 100; client.world.at = 1
    if change == 'future': client.world.at = 11
    if change == 'pressure': client.world.healthy = False
    if change == 'incomplete': client.world.complete = False
    if change == 'disk': client.world.disk = 0
    result = client.call('schedule')
    assert result['result'] == 'wait' or result['decisions'][0]['result'] == 'wait'
    assert client.records()['job']['state'] == 'queued'


def test_heartbeat_expiry_retains_every_charge_and_named_lock(client):
    token = allocate(client, locks=['checkout'])
    client.world.now += 31
    client.submit('other', pid=11)
    assert client.call('schedule')['reasons'] == ['ownership reconciliation required']
    record = client.records()['job']
    assert record['state'] == 'uncertain' and record['locks'] == ['checkout']
    assert client.call('heartbeat', request_id='job', token=token)['result'] == 'wait'


def test_live_memory_accounts_remaining_growth_without_double_subtraction(client):
    token = allocate(client, memory=5000)
    register(client, token)
    client.world.measured['job'] = 4000
    client.world.available = 3500  # candidate 1000 + existing growth 1000 + host 1000
    client.submit('other', memory=1000, pid=11)
    assert client.schedule()[0]['result'] == 'reserved'


def test_downgrade_requires_observed_headroom(client):
    token = allocate(client, memory=5000)
    register(client, token)
    client.world.measured['job'] = 4000
    result = client.call('replace', request_id='job', token=token, resources=dict(memory_mib=3000))
    assert result['result'] == 'wait'
    assert client.records()['job']['resources']['memory_mib'] == 5000


def test_two_bypasses_protect_oldest_long_within_one_batch_and_across_reopen(client):
    allocate(client, 'holder', memory=2000)
    client.submit('long', memory=8000, pid=11, seconds=900)
    original = client.records()['long']['ready_at']
    for i in range(3):
        client.world.now += 1
        client.submit(f'short-{i}', memory=1000, pid=12 + i)
    decisions = {d['request_id']: d for d in client.schedule()}
    assert [decisions[f'short-{i}']['result'] for i in range(3)] == ['reserved', 'reserved', 'wait']
    client.service = ShadowService(client.service.database, observe=client.world.observe)
    record = client.records()['long']
    assert record['bypasses'] == 2 and record['ready_at'] == original
    assert all(d['result'] == 'wait' for d in client.schedule())


def test_splitting_requests_cannot_give_one_owner_multiple_active_phases(client):
    client.submit('a', owner='same')
    client.submit('b', owner='same', pid=11)
    assert [d['result'] for d in client.schedule()] == ['reserved', 'wait']


def test_cli_driver_is_bounded_explicit_and_retains_database(tmp_path):
    fixture = tmp_path / 'fixture.json'
    fixture.write_text(json.dumps(dict(schema=1, operations=[dict(now=1, operation=dict(
        id='init', action='init', total=dict(memory_mib=100), reserve={})),
        dict(now=2, operation=dict(id='status', action='status', epoch=1))])))
    output = []
    assert main(tmp_path / 'offline.sqlite', fixture, echo=output.append) == 0
    report = json.loads(output[0])
    assert report['admission'] is False and report['results'][1]['requests'] == []
    with pytest.raises(ValueError, match='absolute'):
        ShadowService('relative.sqlite')


def test_cli_routes_shadow_lazily_and_requires_explicit_state(tmp_path, capsys):
    from atelier.cli import main as cli_main
    fixture = tmp_path / 'fixture.json'
    fixture.write_text(json.dumps(dict(schema=1, operations=[dict(now=1, operation=dict(
        id='init', action='init', total=dict(memory_mib=100), reserve={}))])))
    with pytest.raises(SystemExit, match='requires --state'):
        cli_main(['capacity', 'shadow', str(fixture)])
    assert cli_main(['capacity', 'shadow', str(fixture), '--state', str(tmp_path / 'shadow.sqlite')]) == 0
    assert json.loads(capsys.readouterr().out)['admission'] is False


@pytest.mark.parametrize('kind', ['unrelated', 'symlink', 'hardlink', 'public', 'ancestor'])
def test_storage_refuses_unknown_or_unsafe_files_without_mutation(tmp_path, kind):
    original = tmp_path / 'unrelated.sqlite'
    with sqlite3.connect(original) as connection:
        connection.execute('CREATE TABLE valuable (value TEXT)')
        connection.execute("INSERT INTO valuable VALUES ('keep')")
    original.chmod(0o600)
    path = original
    if kind == 'symlink':
        path = tmp_path / 'link.sqlite'
        path.symlink_to(original)
    if kind == 'hardlink':
        path = tmp_path / 'hard.sqlite'
        os.link(original, path)
    if kind == 'public': original.chmod(0o644)
    if kind == 'ancestor':
        linked = tmp_path / 'linked'
        linked.symlink_to(tmp_path, target_is_directory=True)
        path = linked / 'unrelated.sqlite'
    before = original.read_bytes()
    with pytest.raises(ValueError):
        ShadowService(path).apply(dict(id='init', action='init', total={}, reserve={}), now=1)
    assert original.read_bytes() == before


def test_unknown_fields_and_clock_regression_are_rejected_without_mutation(client):
    with pytest.raises(ValueError, match='fields'):
        client.call('submit', unexpected=True)
    client.world.now = 9
    with pytest.raises(ValueError, match='backwards'):
        client.call('status')
    client.world.now = 10
    assert client.records() == {}


@pytest.mark.parametrize('change', ['version', 'schema'])
def test_unknown_database_versions_and_schema_are_refused_before_writing(client, change):
    with sqlite3.connect(client.service.database) as connection:
        connection.execute('PRAGMA user_version=2' if change == 'version' else 'CREATE TABLE extra (value TEXT)')
    before = client.service.database.read_bytes()
    with pytest.raises(ValueError, match='supported'):
        client.call('status')
    assert client.service.database.read_bytes() == before


def test_service_import_does_not_load_native_safety_modules():
    subprocess.run([sys.executable, '-c', 'import sys; import atelier.capacity_service; '
                    'assert not any(n.startswith("atelier.safety") for n in sys.modules)'], check=True)
