"""Full-mode compatibility uses private temporary inodes only; no machine activation."""
from dataclasses import asdict
import fcntl
import json
import os
from pathlib import Path
import sys
import subprocess
import threading
import tempfile
from types import SimpleNamespace
import time

import pytest

from atelier import capacity_compat as compat, capacity_protocol as wire, capacity_runtime as runtime
from atelier import capacity_broker as broker
from atelier.capacity import Resources
from atelier.safety import render_lock as locks
from atelier.safety import guarded

BOOT_A = '11111111-1111-4111-8111-111111111111'
BOOT_B = '22222222-2222-4222-8222-222222222222'
actual_boot_id = wire.boot_id


def test_unremovable_diagnostics_do_not_change_guarded_result(tmp_path, monkeypatch):
    report = tmp_path / 'execution-timings.json'
    report.mkdir()
    def finished(*args, **kwargs):
        kwargs['_timings']['ready'] = True
        return 17
    monkeypatch.setattr(guarded, '_run', finished)
    assert guarded.run(['ordinary-command'], tmp_path) == 17
    assert report.is_dir()


@pytest.fixture
def short_path():
    with tempfile.TemporaryDirectory(prefix='acs-', dir='/tmp') as directory:
        yield Path(directory)


@pytest.fixture
def barrier(short_path, monkeypatch):
    if os.getuid() == 0:
        pytest.skip('The real same-UID write denial requires an unprivileged test user')
    tmp_path = short_path
    tmp_path.chmod(0o700)
    monkeypatch.setattr(compat, 'DEFAULT_RECORD', tmp_path / 'cutover.json')
    monkeypatch.setattr(locks, 'DEFAULT_LOCK', tmp_path / 'render.lock')
    monkeypatch.delenv('ATELIER_RENDER_LOCK', raising=False)
    monkeypatch.delenv('ATELIER_RENDER_LOCK_SCAN', raising=False)
    boot = [BOOT_A]
    monkeypatch.setattr(wire, 'boot_id', lambda: boot[0])
    paths = locks.lock_paths()
    for name, path in paths.items():
        path.write_text('unchanged ' + name)
    total = Resources(memory_mib=32768, cpu_millis=12000, temp_mib=32768, io_slots=4, gpu_mib=32768)
    reserve = Resources(memory_mib=4096, cpu_millis=1000)
    value = dict(schema=2, mode='capacity', cutover=str(compat.DEFAULT_RECORD),
                 state_directory=str(tmp_path / 'broker'), disk_pool=str(tmp_path),
                 total=asdict(total), reserve=asdict(reserve))
    config = tmp_path / 'broker.json'
    config.write_text(json.dumps(value))
    config.chmod(0o600)
    yield SimpleNamespace(config=config, boot=boot, paths=paths, value=value, root=tmp_path)
    for path in paths.values():
        if path.is_file() and not path.is_symlink():
            path.chmod(0o600)  # Test-owned files only; production never auto-unseals.


def activated(barrier):
    compat.prepare(barrier.config)
    barrier.boot[0] = BOOT_B
    return compat.activate(barrier.config)


def test_seal_preserves_inodes_and_bytes_then_requires_positive_boot_change(barrier):
    before = {key: (path.stat().st_ino, path.read_bytes()) for key, path in barrier.paths.items()}
    result = compat.prepare(barrier.config)
    assert result['state'] == 'sealed'
    for key, path in barrier.paths.items():
        assert (path.stat().st_ino, path.read_bytes()) == before[key]
        with pytest.raises(PermissionError):
            path.open('a+')
    with pytest.raises(wire.CapacityError, match='new OS boot'):
        compat.activate(barrier.config)
    assert compat.read()['state'] == 'sealed'
    barrier.boot[0] = BOOT_B
    assert compat.activate(barrier.config)['state'] == 'active'
    assert compat.verify()['seal_boot_id'] == BOOT_A
    with pytest.raises(wire.CapacityError, match='already exists'):
        compat.prepare(barrier.config)


def test_preopened_writer_is_not_a_same_boot_closure_proof(barrier):
    with barrier.paths['big'].open('a+b') as preopened:
        compat.prepare(barrier.config)
        with pytest.raises(wire.CapacityError, match='new OS boot'):
            compat.activate(barrier.config)
        preopened.write(b'old descriptor')
        preopened.flush()
        os.fsync(preopened.fileno())
    barrier.boot[0] = BOOT_B
    with pytest.raises(wire.CapacityError, match='modified'):
        compat.activate(barrier.config)


@pytest.mark.parametrize('mutation', ['permission', 'replace', 'hardlink', 'symlink'])
def test_changed_sealed_inode_never_falls_back(barrier, mutation):
    activated(barrier)
    path = barrier.paths['small']
    if mutation == 'permission':
        path.chmod(0o644)
    elif mutation == 'replace':
        path.unlink()
        path.write_text('replacement')
        path.chmod(0o444)
    elif mutation == 'hardlink':
        os.link(path, barrier.root / 'second-link')
    else:
        path.unlink()
        path.symlink_to(barrier.paths['big'])
    with pytest.raises((OSError, wire.CapacityError)):
        compat.verify()
    assert compat.read()['state'] == 'active'
    with pytest.raises(wire.CapacityError, match='no full-capacity lifecycle'):
        compat.refuse_unmanaged('raw fixture')


def test_partial_seal_is_durable_refusal_and_never_auto_unseals(barrier, monkeypatch):
    monkeypatch.setattr(compat, '_write_denied', lambda path: (_ for _ in ()).throw(wire.CapacityError('ACL permits write')))
    with pytest.raises(wire.CapacityError, match='ACL'):
        compat.prepare(barrier.config)
    assert compat.read()['state'] == 'preparing'
    assert all(path.stat().st_mode & 0o222 == 0 for path in barrier.paths.values())
    with pytest.raises(wire.CapacityError):
        compat.refuse_unmanaged('raw fixture')


def test_shared_contexts_overlap_without_rewriting_holder_records(barrier, monkeypatch):
    proof = activated(barrier)
    before = {key: (path.read_bytes(), path.stat().st_ctime_ns) for key, path in barrier.paths.items()}
    admission = SimpleNamespace(mode='capacity', cutover=compat.DEFAULT_RECORD,
                                activation_id=proof['activation_id'], owned=lambda pins: set())
    monkeypatch.setattr(locks, 'native_candidates', lambda: [])
    monkeypatch.setattr(locks, '_write', lambda *a, **kw: pytest.fail('shared context wrote legacy record'))
    monkeypatch.setattr(locks, '_release', lambda *a, **kw: pytest.fail('shared context truncated legacy record'))
    with locks.render_lock('first', capacity=admission):
        with locks.render_lock('second', capacity=admission):
            for path in barrier.paths.values():
                with path.open('rb') as other:
                    with pytest.raises(BlockingIOError):
                        fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert {key: (path.read_bytes(), path.stat().st_ctime_ns) for key, path in barrier.paths.items()} == before
    for path in barrier.paths.values():
        with path.open('rb') as other:
            fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_shared_attempt_releases_partial_locks_and_refuses_unknown_native(barrier, monkeypatch):
    proof = activated(barrier)
    admission = SimpleNamespace(mode='capacity', cutover=compat.DEFAULT_RECORD,
                                activation_id=proof['activation_id'], owned=lambda pins: set())
    monkeypatch.setattr(locks, 'native_candidates', lambda: [[654, 987]])
    with barrier.paths['fitting'].open('rb') as blocker:
        fcntl.flock(blocker, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(locks.RenderBusy, match='legacy exclusive'):
            with locks.render_lock('blocked', capacity=admission):
                pytest.fail('entered')
        with barrier.paths['big'].open('rb') as freed:
            fcntl.flock(freed, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with pytest.raises(locks.RenderBusy, match='unregistered'):
        with locks.render_lock('unknown', capacity=admission):
            pytest.fail('entered')
    with pytest.raises(ValueError, match='normal foreign scan'):
        with locks.render_lock('skip', capacity=admission, scan=False):
            pytest.fail('entered')


@pytest.mark.parametrize('listing', ['', 'malformed\n', '12 1 Blender\n',
                                    '{self} 1 Python', '{self} 1 Python\n42 1 Bl\x00ender\n',
                                    '{self} 1 Python\n{self} 1 Python\n',
                                    '{self} 1 Python\npartial\n'])
def test_full_scan_refuses_empty_partial_and_malformed_observations(monkeypatch, listing):
    monkeypatch.setattr(locks, '_bounded_process_listing', lambda timeout: listing.format(self=os.getpid()))
    with pytest.raises(OSError):
        locks.process_table(timeout=2.)


def test_full_scan_requires_stable_native_identity(monkeypatch):
    monkeypatch.setattr(locks, '_bounded_process_listing', lambda timeout: f'{os.getpid()} 1 Python\n42 1 Blender\n')
    monkeypatch.setattr(wire, 'live', lambda pin: True)
    starts = iter([111, 112])
    monkeypatch.setattr(wire, 'process_start', lambda pid: next(starts))
    with pytest.raises(wire.CapacityError, match='identity'):
        locks.native_candidates()


@pytest.mark.parametrize('failure', ['nonzero', 'oversized', 'wait-timeout'])
def test_bounded_ps_failures_are_observation_errors(monkeypatch, failure):
    class Ready:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def register(self, *args):
            pass
        def select(self, timeout):
            return [True]
    def wait(**kwargs):
        if failure == 'wait-timeout':
            raise subprocess.TimeoutExpired('ps', 2)
        return 1 if failure == 'nonzero' else 0
    process = SimpleNamespace(stdout=SimpleNamespace(fileno=lambda: 123, close=lambda: None),
                              wait=wait, poll=lambda: 0)
    monkeypatch.setattr(locks.subprocess, 'Popen', lambda *args, **kwargs: process)
    monkeypatch.setattr(locks.selectors, 'DefaultSelector', Ready)
    monkeypatch.setattr(locks.os, 'read', lambda *args: b'x' * (1024 * 1024 + 1) if failure == 'oversized' else b'')
    with pytest.raises(OSError, match='observation'):
        locks._bounded_process_listing(2.)


@pytest.mark.parametrize('kind,command,cpu,exclusive', [
    ('job', ['/Applications/Blender.app/Contents/MacOS/Blender', '-b', '--threads', '6'], 6000, False),
    ('job', ['blender', '-b', '--threads', '3'], 3000, False),
    ('job', ['blender', '-b'], 11000, True),
    ('job', ['sh', '-c', 'blender --threads 3'], 11000, True),
    ('compile', ['UnrealBuildTool', '-MaxParallelActions=3'], 11000, True),
    ('game', ['UnrealEditor'], 11000, True),
])
def test_profiles_cover_unchanged_workers_and_actual_guard(barrier, monkeypatch, kind, command, cpu, exclusive):
    activated(barrier)
    profile = dict(resources=asdict(Resources(memory_mib=10240, cpu_millis=1000, io_slots=1)), locks=[])
    config = barrier.root / 'client.json'
    config.write_text(json.dumps(dict(schema=2, cutover=str(compat.DEFAULT_RECORD),
        socket=compat.read()['socket'], profiles={key: profile for key in ('job', 'game', 'compile')})))
    config.chmod(0o600)
    monkeypatch.setitem(sys.modules, 'atelier.capacity_client', SimpleNamespace(AdmissionSession=lambda socket, request, **kw: request))
    result = runtime.configured_session(kind=kind, command=command, limit_gib=10, timeout=60, config=config)
    assert result['resources']['cpu_millis'] == cpu
    assert result['resources']['memory_mib'] == 10240
    assert result['performance'] is exclusive
    assert command[-1] != '1000'  # Profiling never substitutes narrower worker arguments.
    with pytest.raises(ValueError, match='actual guard ceiling'):
        runtime.configured_session(kind=kind, command=command, limit_gib=14, timeout=60, config=config)


def test_missing_client_cannot_restore_slots_after_seal(barrier, monkeypatch):
    compat.prepare(barrier.config)
    monkeypatch.setattr(runtime, 'DEFAULT_CONFIG', barrier.root / 'absent.json')
    monkeypatch.delenv('ATELIER_CAPACITY_CLIENT', raising=False)
    with pytest.raises(ValueError, match='cannot fall back'):
        runtime.configured_session(kind='job', limit_gib=10, timeout=60)


@pytest.mark.parametrize('command,workers,cpu,performance,message', [
    (['/bin/sh', '-c', 'Blender --threads 3'], 1, 1000, False, 'unknown commands'),
    (['/bin/sh', '-c', 'Blender --threads 3'], 1, 11000, True, 'cannot declare bounded'),
    (['Blender', '--threads', '6'], 3, 3000, False, 'actual unchanged Blender'),
    (['Blender', '--threads', '3'], 3, 1000, False, 'actual unchanged Blender'),
])
def test_explicit_session_cannot_bypass_actual_command_profile(tmp_path, command, workers, cpu, performance, message):
    folder = tmp_path / 'must-not-create'
    admission = SimpleNamespace(mode='capacity', request=dict(phase='job', workers=workers,
        checkout=str(runtime.REPO), locks=['checkout:' + str(runtime.REPO)], performance=performance,
        resources=asdict(Resources(memory_mib=10240, cpu_millis=cpu, io_slots=1))))
    with pytest.raises(ValueError, match=message):
        guarded.run(command, folder, admission=admission)
    assert not folder.exists()


@pytest.mark.parametrize('changes', [dict(locks=[]), dict(checkout='/different'),
    dict(resources=asdict(Resources(memory_mib=10240, cpu_millis=3000)))])
def test_explicit_session_requires_checkout_lock_and_io(tmp_path, changes):
    request = dict(phase='job', workers=3, checkout=str(runtime.REPO), locks=['checkout:' + str(runtime.REPO)],
                   performance=False, resources=asdict(Resources(memory_mib=10240, cpu_millis=3000, io_slots=1)))
    admission = SimpleNamespace(mode='capacity', request=request | changes)
    with pytest.raises(ValueError, match='checkout named lock|CPU and I/O'):
        guarded.run(['Blender', '--threads', '3'], tmp_path / 'absent', admission=admission)


def test_broker_binds_sealed_budget_and_exact_verified_ownership(barrier):
    activated(barrier)
    settings = broker.load_config(barrier.config)
    with pytest.raises(wire.CapacityError, match='sealed policy'):
        broker.CapacityBroker(**(settings | {'total': Resources(memory_mib=32769, cpu_millis=12000,
                                                              temp_mib=32768, io_slots=4, gpu_mib=32768)}))
    instance = broker.CapacityBroker(**settings, started=lambda pid: {10: 100, 11: 111}.get(pid), alive=lambda pin: True)
    try:
        held = dict(state='running', verified_roster=[[10, 100]], roster=[[10, 100], [11, 111]], exited=[])
        state = dict(records={'held': held})
        assert instance._owned(state, [[10, 100], [10, 99], [11, 111]]) == [[10, 100]]
        held['state'] = 'uncertain'
        with pytest.raises(wire.CapacityError, match='unavailable'):
            instance._owned(state, [[10, 100]])
        held['state'] = 'running'
        instance.foreign = lambda: [[11, 111]]
        with pytest.raises(wire.CapacityError, match='Unregistered'):
            instance._foreign_check(state)
        instance.foreign = lambda: [[10, 100]]
        instance._foreign_check(state)
    finally:
        instance.close()


@pytest.fixture
def actor(barrier):
    activated(barrier)
    healthy = [True]
    def guards(*args):
        if not healthy[0]:
            raise wire.CapacityError('Guard exited during scan')
        return wire.GuardFacts((), 0)
    class Watch:
        def __init__(self, pin):
            pass
        def poll(self):
            return False
        def close(self):
            pass
    instance = broker.CapacityBroker(**broker.load_config(barrier.config), started=lambda pid: pid * 100,
        alive=lambda pin: True, watch=Watch, guards=guards, child_of=lambda *args: True,
        parent=lambda pin: None, boot=lambda: BOOT_B, foreign=lambda: [],
        observe=lambda: dict(observed_monotonic=time.monotonic(), available_memory_mib=99999,
                             available_temp_mib=99999))
    yield instance, healthy
    instance.close()


def offer(instance, owner, name, *, checkout=None, **changes):
    checkout = instance.directory.parent / (checkout or name)
    request = dict(id=name, owner='fixture', phase='job', workers=3,
                   resources=asdict(Resources(memory_mib=1024, cpu_millis=3000, io_slots=1)),
                   locks=['checkout:' + str(checkout)], checkout=str(checkout), seconds=60)
    response, _ = instance.handle(dict(namespace=wire.NAMESPACE, action='offer', activation_id=instance.activation_id,
                                       request=request | changes), owner)
    return dict(namespace=wire.NAMESPACE, activation_id=instance.activation_id, boot_id=instance.boot,
                id=name, nonce=response['nonce'], epoch=response['epoch']), response


def gate_start(instance, owner, message, child):
    _, fd = instance.handle(message | dict(action='gate'), owner)
    try:
        response, _ = instance.handle(message | dict(action='start', child=[child, child * 100],
            process_guard={}, tree_guard={}, limit_bytes=1024 * 1024**2), owner)
        assert os.read(fd, 1) == b'1'
        return response
    finally:
        os.close(fd)


def test_full_actor_allows_only_resources_and_named_lock_compatible_overlap(actor):
    instance, _ = actor
    owner_a, owner_b = (101, 10100), (102, 10200)
    first, offered = offer(instance, owner_a, 'a')
    assert offered['selected']
    assert gate_start(instance, owner_a, first, 201)['admission']
    second, offered = offer(instance, owner_b, 'b')
    assert offered['selected']
    assert gate_start(instance, owner_b, second, 202)['admission']
    status, _ = instance.handle(dict(namespace=wire.NAMESPACE, action='status'), owner_a)
    assert status['mode'] == 'capacity' and status['cutover'] and status['charged_count'] == 2
    assert status['charged_resources']['cpu_millis'] == 6000
    _, offered = offer(instance, (103, 10300), 'same-checkout', checkout='a')
    assert not offered['selected']
    _, offered = offer(instance, (104, 10400), 'compile', phase='compile', performance=True)
    assert not offered['selected']
    with pytest.raises(wire.CapacityError, match='exclusive'):
        offer(instance, (105, 10500), 'unsafe-game', phase='game')


@pytest.mark.parametrize('failure,stage', [('guard', 'scan'), ('owner', 'scan'), ('guard', 'pressure'),
                                         ('seal', 'scan'), ('seal', 'pressure')])
def test_existing_holder_failure_during_slow_observations_refuses_other_go(actor, barrier, failure, stage):
    instance, _ = actor
    first, _ = offer(instance, (101, 10100), 'a')
    gate_start(instance, (101, 10100), first, 201)
    second, _ = offer(instance, (102, 10200), 'b')
    lost = [False]
    original_guards, original_started = instance.guards, instance.started
    def guards(guards, child, *args):
        if child == (201, 20100) and failure == 'guard' and lost[0]:
            raise wire.CapacityError('Existing holder guard lost during observation')
        return original_guards(guards, child, *args)
    instance.guards = guards
    instance.started = lambda pid: None if pid == 101 and failure == 'owner' and lost[0] else original_started(pid)
    def scan():
        if stage == 'scan':
            lost[0] = True
            if failure == 'seal':
                barrier.paths['small'].chmod(0o600)
        return []
    instance.foreign = scan
    original_pressure = instance._pressure
    def pressure(state, candidate):
        original_pressure(state, candidate)
        if stage == 'pressure':
            lost[0] = True
            if failure == 'seal':
                barrier.paths['small'].chmod(0o600)
    instance._pressure = pressure
    with pytest.raises(wire.CapacityError, match='Existing holder|compatibility changed'):
        gate_start(instance, (102, 10200), second, 202)
    # The failed candidate's rollback must not erase a positively observed enforcement loss.
    with instance._lock:
        state = instance._load()
        assert state['records']['a']['state'] == 'uncertain'
        assert state['records']['b']['state'] == 'queued'
        instance.connection.rollback()
    status, _ = instance.handle(dict(namespace=wire.NAMESPACE, action='status'), (102, 10200))
    assert status['charged_count'] == 1 and status['recovering']


def test_refused_replacement_retains_old_vector_and_other_holder_enforcement_loss(actor):
    instance, _ = actor
    first, _ = offer(instance, (101, 10100), 'a')
    gate_start(instance, (101, 10100), first, 201)
    second, _ = offer(instance, (102, 10200), 'b')
    gate_start(instance, (102, 10200), second, 202)
    original = instance.guards
    lost = [False]
    def guards(guards, child, *args):
        if child == (201, 20100) and lost[0]:
            raise wire.CapacityError('Other holder failed during phase pressure')
        return original(guards, child, *args)
    instance.guards = guards
    observe = instance.observe
    def pressure():
        lost[0] = True
        return observe()
    instance.observe = pressure
    with pytest.raises(wire.CapacityError, match='Existing holder'):
        instance.handle(second | dict(action='replace',
            resources=asdict(Resources(memory_mib=2048, cpu_millis=4000, io_slots=1)),
            locks=['checkout:' + str(instance.directory.parent / 'b')]), (102, 10200))
    with instance._lock:
        state = instance._load()
        assert state['records']['a']['state'] == 'uncertain'
        assert state['records']['b']['request']['resources']['memory_mib'] == 1024
        assert state['records']['b']['request']['resources']['cpu_millis'] == 3000
        instance.connection.rollback()


@pytest.mark.parametrize('failure', ['guard', 'owner', 'lease', 'seal'])
def test_initial_refresh_loss_survives_early_candidate_refusal_and_transient_recovery(actor, monkeypatch, failure):
    instance, healthy = actor
    first, _ = offer(instance, (101, 10100), 'a')
    gate_start(instance, (101, 10100), first, 201)
    second, _ = offer(instance, (102, 10200), 'b')
    _, fd = instance.handle(second | dict(action='gate'), (102, 10200))
    original_started, original_verify = instance.started, compat.verify
    lost = [True]
    if failure == 'guard':
        healthy[0] = False
    elif failure == 'owner':
        instance.started = lambda pid: None if pid == 101 and lost[0] else original_started(pid)
    elif failure == 'lease':
        state = instance._load()
        state['records']['a']['heartbeat'] -= instance.lease_seconds + 1
        instance._save(state)
    else:
        def verify(*args, **kwargs):
            if lost[0]:
                raise wire.CapacityError('Temporary compatibility observation failed')
            return original_verify(*args, **kwargs)
        monkeypatch.setattr(compat, 'verify', verify)
    try:
        with pytest.raises(wire.CapacityError, match='no longer selected|compatibility'):
            instance.handle(second | dict(action='start', child=[202, 20200], process_guard={},
                tree_guard={}, limit_bytes=1024 * 1024**2), (102, 10200))
        assert os.read(fd, 1) == b''  # No GO; the refused gate is closed.
    finally:
        os.close(fd)
    state = instance._load()
    try:
        assert state['records']['a']['state'] == 'uncertain'
        assert state['records']['b']['state'] == 'queued'
        assert state['records']['a']['request']['resources']['memory_mib'] == 1024
    finally:
        instance.connection.rollback()
    lost[0], healthy[0] = False, True
    with pytest.raises(wire.CapacityError, match='no longer selected'):
        gate_start(instance, (102, 10200), second, 202)


def test_observed_root_exit_survives_malformed_candidate_without_committing_its_roster(actor):
    instance, _ = actor
    first, _ = offer(instance, (101, 10100), 'a')
    gate_start(instance, (101, 10100), first, 201)
    second, _ = offer(instance, (102, 10200), 'b')
    _, fd = instance.handle(second | dict(action='gate'), (102, 10200))
    instance._watches[(first['nonce'], (201, 20100))].poll = lambda: True
    try:
        with pytest.raises(wire.CapacityError):
            instance.handle(second | dict(action='start', child=[], process_guard={},
                tree_guard={}, limit_bytes=1024 * 1024**2), (102, 10200))
        assert os.read(fd, 1) == b''
    finally:
        os.close(fd)
    state = instance._load()
    try:
        assert state['records']['a']['state'] == 'draining'
        assert state['records']['b']['state'] == 'queued'
        assert state['records']['b']['roster'] == []
        assert 'child' not in state['records']['b']
    finally:
        instance.connection.rollback()


def test_draining_peer_with_unwitnessed_helper_cannot_authorize_another_go(actor):
    instance, _ = actor
    first, _ = offer(instance, (101, 10100), 'a')
    gate_start(instance, (101, 10100), first, 201)
    with instance._lock:
        state = instance._load()
        held = state['records']['a']
        held.update(state='draining', roster=[[201, 20100], [301, 30100]], exited=[[201, 20100]])
        instance._save(state)
    second, _ = offer(instance, (102, 10200), 'b')
    with pytest.raises(wire.CapacityError, match='Existing holder'):
        gate_start(instance, (102, 10200), second, 202)
    status, _ = instance.handle(dict(namespace=wire.NAMESPACE, action='status'), (102, 10200))
    assert status['charged_count'] == 1 and status['records'][0]['state'] == 'uncertain'


@pytest.mark.parametrize('failure', ['unknown-native', 'guard-during-scan', 'barrier-lost'])
def test_failed_final_observations_never_release_gate(actor, barrier, failure):
    instance, healthy = actor
    owner = (101, 10100)
    message, _ = offer(instance, owner, 'a')
    _, fd = instance.handle(message | dict(action='gate'), owner)
    if failure == 'unknown-native':
        instance.foreign = lambda: [[999, 99900]]
    elif failure == 'guard-during-scan':
        def scan():
            healthy[0] = False
            return []
        instance.foreign = scan
    else:
        barrier.paths['big'].chmod(0o600)
    try:
        with pytest.raises(wire.CapacityError):
            instance.handle(message | dict(action='start', child=[201, 20100], process_guard={},
                tree_guard={}, limit_bytes=1024 * 1024**2), owner)
        assert os.read(fd, 1) == b''
        status, _ = instance.handle(dict(namespace=wire.NAMESPACE, action='status'), owner)
        assert status['charged_count'] == 0
    finally:
        os.close(fd)


def test_lost_shared_descriptors_cannot_release_uncertain_grant(actor, barrier):
    instance, _ = actor
    owner = (101, 10100)
    message, _ = offer(instance, owner, 'a')
    gate_start(instance, owner, message, 201)
    # No shared flock is retained by this synthetic controller. Durable accounting still fences GO.
    barrier.paths['big'].chmod(0o600)
    status, _ = instance.handle(dict(namespace=wire.NAMESPACE, action='status'), owner)
    assert status['recovering'] and not status['compatibility_healthy']
    assert status['charged_count'] == 1 and status['records'][0]['state'] == 'uncertain'
    with pytest.raises(wire.CapacityError, match='compatibility'):
        offer(instance, (102, 10200), 'b')


def test_missing_boot_observation_retains_charge_and_status_remains_usable(actor, monkeypatch):
    instance, _ = actor
    owner = (101, 10100)
    message, _ = offer(instance, owner, 'a')
    gate_start(instance, owner, message, 201)
    monkeypatch.setattr(wire, 'boot_id', actual_boot_id)
    monkeypatch.setattr(wire.sys, 'platform', 'darwin')
    def unavailable(*args, **kwargs):
        raise subprocess.TimeoutExpired('sysctl', .5)
    monkeypatch.setattr(wire.subprocess, 'check_output', unavailable)
    status, _ = instance.handle(dict(namespace=wire.NAMESPACE, action='status'), owner)
    assert status['recovering'] and status['charged_count'] == 1
    assert status['records'][0]['state'] == 'uncertain'
    with pytest.raises(wire.CapacityError, match='compatibility'):
        offer(instance, (102, 10200), 'b')
    status, _ = instance.handle(dict(namespace=wire.NAMESPACE, action='reconcile'), owner)
    assert status['charged_count'] == 1


def test_full_socket_configured_python_runs_under_real_guards_and_releases(barrier, monkeypatch):
    from atelier import capacity_client
    activated(barrier)
    instance = broker.CapacityBroker(**broker.load_config(barrier.config), boot=lambda: BOOT_B,
        observe=lambda: dict(observed_monotonic=time.monotonic(), available_memory_mib=99999,
                             available_temp_mib=99999))
    errors = []
    def serve():
        try:
            instance.serve_forever()
        except BaseException as error:
            errors.append(error)
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    profile = dict(resources=asdict(Resources(memory_mib=256, cpu_millis=1000, temp_mib=16, io_slots=1)), locks=[])
    config = barrier.root / 'client.json'
    config.write_text(json.dumps(dict(schema=2, cutover=str(compat.DEFAULT_RECORD), socket=str(instance.socket_path),
        profiles={kind: profile for kind in ('job', 'game', 'compile')})))
    config.chmod(0o600)
    monkeypatch.setenv('ATELIER_CAPACITY_CLIENT', str(config))
    # Only native inventory is injected; real Python, socket, SQLite, SH flocks, exec gate and both monitors run.
    monkeypatch.setattr(locks, 'native_candidates', lambda: [])
    folder = barrier.root / 'real-guard'
    try:
        assert guarded.run([sys.executable, '-c', 'print("full capacity executed")'], folder,
                           limit_gib=.25, timeout=10, invocation_id='33333333333343338333333333333333') == 0
        assert 'full capacity executed' in (folder / 'stdout.log').read_text()
        assert json.loads((folder / 'memory-health-tree.json').read_text())['state'] == 'child_exited'
        status = capacity_client.status(instance.socket_path)
        assert status['mode'] == 'capacity' and status['cutover'] and status['charged_count'] == 0
        assert status['records'][0]['state'] == 'released'
        assert all(path.stat().st_mode & 0o777 == 0o400 for path in barrier.paths.values())
        diagnostics = json.loads((folder / 'execution-timings.json').read_text())
        assert diagnostics['schema'] == 1 and diagnostics['invocation_id'] == '33333333333343338333333333333333'
        assert diagnostics['admission_seconds'] >= 0 and diagnostics['child_lifetime_seconds'] > 0
        assert diagnostics['execution_seconds'] is None
        with pytest.raises(ValueError, match='guard ceiling'):
            guarded.run([sys.executable, '-c', 'pass'], folder, limit_gib=1.)
        assert not (folder / 'execution-timings.json').exists()
    finally:
        instance._stop.set()
        thread.join(timeout=3)
        instance.close()
        assert not thread.is_alive() and not errors, errors
