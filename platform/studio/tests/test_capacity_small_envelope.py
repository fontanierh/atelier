"""Retain the established SMALL envelope without native jobs, machine locks or activation."""
from contextlib import contextmanager
from dataclasses import asdict
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import capacity_compat as compat, capacity_protocol as wire, capacity_runtime as runtime
from atelier.capacity import Resources, Request, conflicts
from atelier.capacity_broker import CapacityBroker
from atelier.safety import guarded

GiB = 1024**3
BLENDER = ['Blender', '-b', '--threads', '3']


@pytest.fixture
def configured(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    path = tmp_path / 'client.json'
    profile = dict(resources=asdict(Resources(memory_mib=10240, cpu_millis=6000, temp_mib=2048)), locks=[])
    value = dict(schema=2, socket=str(tmp_path / 'broker.sock'), cutover=str(tmp_path / 'cutover.json'),
                 profiles={kind: json.loads(json.dumps(profile)) for kind in ('job', 'game', 'compile')})
    monkeypatch.delenv('ATELIER_CAPACITY_CLIENT', raising=False)
    monkeypatch.setattr(runtime, 'DEFAULT_CONFIG', path)
    monkeypatch.setattr(compat, 'DEFAULT_RECORD', tmp_path / 'cutover.json')
    monkeypatch.setattr(compat, 'read', lambda: None)
    monkeypatch.setattr(compat, 'verify', lambda *args, **kwargs: dict(socket=value['socket'], activation_id='fixture',
        total=dict(cpu_millis=10000), reserve=dict(cpu_millis=2000)))
    def make(*, schema=2, kind='job', command=None, small_gib=2, performance=False, limit_gib=10, gpu_mib=0):
        settings = dict(value)
        settings['schema'] = schema
        if schema == 1:
            settings.pop('cutover')
        settings['profiles'][kind]['resources']['gpu_mib'] = gpu_mib
        path.write_text(json.dumps(settings))
        path.chmod(0o600)
        return runtime.configured_session(kind=kind, command=BLENDER if command is None else command,
            small_gib=small_gib, performance=performance, limit_gib=limit_gib, timeout=60)
    return make, value


@pytest.mark.parametrize('peak', [0, 1, 3])
def test_full_known_small_job_reserves_exact_existing_guard_envelope(configured, peak):
    session = configured[0](small_gib=peak)
    assert session.guard_limit_gib == 4
    assert session.request['resources'] == dict(memory_mib=4096, cpu_millis=3000, temp_mib=2048, io_slots=0, gpu_mib=0)
    assert session.request['workers'] == 3 and session.request['performance'] is False
    with pytest.raises(AttributeError):
        session.guard_limit_gib = 1


@pytest.mark.parametrize('options', [
    dict(small_gib=None), dict(small_gib=3.1), dict(small_gib=-1), dict(small_gib=float('nan')),
    dict(small_gib=float('inf')), dict(small_gib=True), dict(small_gib='2'),
    dict(performance=True), dict(kind='game'), dict(kind='compile'),
    dict(command=['Blender', '-b']), dict(command=['sh', '-c', 'Blender --threads 3']), dict(gpu_mib=8192),
])
def test_other_full_jobs_retain_nominal_guard_and_reservation(configured, options):
    session = configured[0](**options)
    assert session.guard_limit_gib == 10 and session.request['resources']['memory_mib'] == 10240
    assert session.request['resources']['gpu_mib'] == options.get('gpu_mib', 0)


def test_bridge_remains_nominal_even_for_previously_small_work(configured):
    session = configured[0](schema=1)
    assert session.guard_limit_gib is None
    assert session.request['resources']['memory_mib'] == 10240


def test_profile_must_still_cover_nominal_ceiling_before_selection(configured):
    configured[1]['profiles']['job']['resources']['memory_mib'] = 4096
    with pytest.raises(ValueError, match='smaller than the actual guard'):
        configured[0]()


def test_selection_never_raises_a_lower_nominal_limit(configured):
    session = configured[0](limit_gib=3)
    assert session.guard_limit_gib == 3 and session.request['resources']['memory_mib'] == 3072


def test_guard_stop_peak_removes_small_eligibility_for_next_invocation(configured, tmp_path):
    from atelier.build import expected_peak_gib
    (tmp_path / 'memory-health.json').write_text(json.dumps(dict(state='memory_limit', peak_bytes=4.1 * GiB)))
    session = configured[0](small_gib=expected_peak_gib(tmp_path))
    assert session.guard_limit_gib == 10 and session.request['resources']['memory_mib'] == 10240


@pytest.fixture
def handshake(monkeypatch):
    seen = dict(process=[], tree=[], ready=[], start=[], locks=[], spawned=[], offered=[])
    @contextmanager
    def lock(purpose, **options):
        seen['locks'].append(options)
        assert options['small_gib'] is None  # No second lane or lock is introduced.
        options['on_slot']('capacity' if 'capacity' in options else 'big', 'fixture')
        yield
    @contextmanager
    def process(*args, **options):
        seen['process'].append(options['limit_gib'])
        yield SimpleNamespace(pid=200, poll=lambda: None)
    @contextmanager
    def tree(*args, **options):
        seen['tree'].append(options['limit_gib'])
        yield SimpleNamespace(process=SimpleNamespace(pid=201), ready=lambda: None,
                              finish=lambda: None, check=lambda: None)
    child = SimpleNamespace(pid=100, returncode=0, poll=lambda: 0)
    def spawn(command, **kwargs):
        seen['spawned'].append(command)
        return child
    monkeypatch.setattr(guarded, 'render_lock', lock)
    monkeypatch.setattr(guarded, 'attach_memory_guard', process)
    monkeypatch.setattr(guarded, 'attach_tree', tree)
    monkeypatch.setattr(guarded, 'spawn', spawn)
    monkeypatch.setattr(guarded, 'reap', lambda *args, **kwargs: None)
    monkeypatch.setattr(guarded.process_tree, 'started', lambda pid: pid * 10)
    monkeypatch.setattr(guarded, 'Descendants', lambda *args: SimpleNamespace(depth={}, shared_now=lambda: set(),
                                                                          unwind=lambda **kwargs: None))
    monkeypatch.setattr(guarded, 'wait_ready', lambda monitor, pid, start, report, limit: seen['ready'].append(limit))
    def bind(session):
        session.offer = lambda: seen['offered'].append(True)
        def gate():
            reader, writer = os.pipe()
            os.close(writer)
            return reader
        session.gate = gate
        session.start = lambda **binding: seen['start'].append(binding)
        session.close = lambda **kwargs: None
        return session
    return seen, bind


@pytest.mark.parametrize('options,expected', [
    ({}, 4), ({'schema': 1}, 10), ({'small_gib': None}, 10), ({'small_gib': 4}, 10),
    ({'command': ['Blender', '-b']}, 10), ({'command': ['sh', '-c', 'Blender --threads 3']}, 10),
    ({'kind': 'game'}, 10), ({'kind': 'compile'}, 10), ({'performance': True}, 10), ({'gpu_mib': 8192}, 10),
])
def test_both_actual_guard_calls_and_broker_binding_match_selection(configured, handshake, monkeypatch, tmp_path, options, expected):
    seen, bind = handshake
    make = configured[0]
    session = bind(make(**options))
    selected = []
    def automatic(**kwargs):
        selected.append(kwargs)
        return session
    monkeypatch.setattr(runtime, 'configured_session', automatic)
    command = options.get('command', BLENDER)
    assert guarded.run(command, tmp_path / 'run', kind=options.get('kind', 'job'),
                       small_gib=options.get('small_gib', 2), performance=options.get('performance', False)) == 0
    assert seen['process'] == seen['tree'] == [expected]
    assert seen['ready'] == [expected * GiB]
    assert seen['start'][0]['limit_bytes'] == expected * GiB
    assert seen['spawned'][0][3:] == command  # Only the existing gate wraps the unchanged argv.
    assert selected[0]['small_gib'] == options.get('small_gib', 2)
    assert len(seen['locks']) == len(seen['offered']) == 1


def test_injected_session_metadata_cannot_lower_the_explicit_limit(configured, handshake, tmp_path):
    session = handshake[1](configured[0]())
    with pytest.raises(ValueError, match='actual guard ceiling'):
        guarded.run(BLENDER, tmp_path / 'run', admission=session, small_gib=2, limit_gib=10)
    assert handshake[0]['process'] == []


def test_injected_nominal_session_retains_both_actual_guard_limits(configured, handshake, tmp_path):
    seen, bind = handshake
    session = bind(configured[0](small_gib=None))
    assert guarded.run(BLENDER, tmp_path / 'run', admission=session, small_gib=2, limit_gib=10) == 0
    assert seen['process'] == seen['tree'] == [10]
    assert seen['start'][0]['limit_bytes'] == 10 * GiB


def test_two_small_envelopes_pass_32gib_host_pressure_where_nominal_envelopes_refuse(configured, monkeypatch, tmp_path):
    total = Resources(memory_mib=32768, cpu_millis=10000, temp_mib=200000, gpu_mib=16000)
    reserve = Resources(memory_mib=8192, cpu_millis=2000)
    broker = object.__new__(CapacityBroker)
    broker.reserve = reserve
    broker._clock = lambda: 100
    # A 32 GiB host with 8 GiB already used by the host and 2 GiB by the first job has 22 GiB available.
    broker.observe = lambda: dict(observed_monotonic=100, available_memory_mib=22528, available_temp_mib=200000)
    broker.guards = lambda *args: wire.GuardFacts((), 2 * GiB)
    for peak, allowed in [(2, True), (None, False)]:
        sessions = []
        for name in ('first', 'second'):
            monkeypatch.setattr(runtime, 'REPO', tmp_path / name)
            sessions.append(configured[0](small_gib=peak))
        first, second = sessions
        holder = dict(state='running', request=first.request, guards={}, child=[100, 1000], principal=[99, 990],
                      limit_bytes=first.guard_limit_gib * GiB)
        candidate = dict(state='queued', request=second.request)
        models = [Request(s.request['id'], wire.resources(s.request['resources']), tuple(s.request['locks'])) for s in sessions]
        assert conflicts(models[1], models[:1], total, reserve) == []
        state = {'records': {'first': holder, 'second': candidate}}
        if allowed:
            broker._pressure(state, candidate)
        else:
            with pytest.raises(wire.CapacityError, match='pressure refuses'):
                broker._pressure(state, candidate)
