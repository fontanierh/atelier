"""Full-mode compatibility uses private temporary inodes only; no machine activation."""
from contextlib import closing
from dataclasses import asdict
import fcntl
import json
import os
import stat
from pathlib import Path
import sys
import subprocess
import threading
import tempfile
from types import SimpleNamespace
import time

import pytest

from atelier.harness import capacity_compat as compat
from atelier.harness import capacity_protocol as wire
from atelier.harness import capacity_runtime as runtime
from atelier.harness import capacity_broker as broker
from atelier.harness.capacity import Resources
from atelier.harness.safety import render_lock as locks
from atelier.harness.safety import guarded

BOOT_A = '11111111-1111-4111-8111-111111111111'
BOOT_B = '22222222-2222-4222-8222-222222222222'
BOOT_C = '44444444-4444-4444-8444-444444444444'
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
    monkeypatch.setattr(compat, '_volume_uuid', lambda path: '33333333-3333-4333-8333-333333333333')
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


def legacy_seal(barrier):
    value = compat.prepare(barrier.config)
    value['schema'] = 1
    for item in value['locks'].values():
        item.pop('volume_uuid')
        item['device'] += 100  # Darwin's device number can change after a boot.
    compat._save(compat.DEFAULT_RECORD, value)
    return value


def test_stable_volume_seal_accepts_new_boot_device_number(barrier):
    value = compat.prepare(barrier.config)
    assert value['schema'] == 2
    for item in value['locks'].values():
        item['device'] += 100
    compat._save(compat.DEFAULT_RECORD, value)
    barrier.boot[0] = BOOT_B
    assert compat.activate(barrier.config)['state'] == 'active'
    barrier.boot[0] = BOOT_C
    assert compat.verify()['state'] == 'active'


def test_volume_mismatch_refuses_even_with_unchanged_inode(barrier, monkeypatch):
    activated(barrier)
    monkeypatch.setattr(compat, '_volume_uuid', lambda path: BOOT_C)
    with pytest.raises(wire.CapacityError, match='modified'):
        compat.verify()


def test_shared_handle_requires_current_device_even_after_boot(barrier, monkeypatch):
    activated(barrier)
    with barrier.paths['big'].open('rb') as handle:
        actual_fstat = os.fstat
        def changed_device(fd):
            info = actual_fstat(fd)
            if fd == handle.fileno():
                return SimpleNamespace(st_dev=info.st_dev + 1, st_ino=info.st_ino,
                    st_ctime_ns=info.st_ctime_ns, st_mode=info.st_mode,
                    st_uid=info.st_uid, st_nlink=info.st_nlink)
            return info
        monkeypatch.setattr(compat.os, 'fstat', changed_device)
        with pytest.raises(wire.CapacityError, match='replaced lane'):
            compat.verify(handles={'big': handle})


def test_forward_migration_preserves_old_seal_and_requires_another_boot(barrier):
    old = legacy_seal(barrier)
    original = compat.DEFAULT_RECORD.read_bytes()
    before = {name: (path.stat().st_ino, path.stat().st_ctime_ns, path.read_bytes())
              for name, path in barrier.paths.items()}
    barrier.boot[0] = BOOT_B
    with pytest.raises(wire.CapacityError, match='explicit volume migration'):
        compat.activate(barrier.config)
    value = compat.migrate_volume_seal(barrier.config)
    assert value['schema'] == 2 and value['state'] == 'sealed' and value['seal_boot_id'] == BOOT_B
    assert value['activation_id'] == old['activation_id']
    archive = compat.DEFAULT_RECORD.with_name(f'cutover.schema1.{old["activation_id"]}.json')
    assert archive.read_bytes() == original and archive.stat().st_mode & 0o777 == 0o600
    assert before == {name: (path.stat().st_ino, path.stat().st_ctime_ns, path.read_bytes())
                      for name, path in barrier.paths.items()}
    with pytest.raises(wire.CapacityError, match='new OS boot'):
        compat.activate(barrier.config)
    barrier.boot[0] = BOOT_C
    assert compat.activate(barrier.config)['state'] == 'active'
    with pytest.raises(wire.CapacityError, match='exactly a schema-1 sealed'):
        compat.migrate_volume_seal(barrier.config)


def test_migration_resumes_only_matching_durable_archive(barrier, monkeypatch):
    legacy_seal(barrier)
    barrier.boot[0] = BOOT_B
    original = compat.DEFAULT_RECORD.read_bytes()
    save = compat._save
    events = []
    fsync = os.fsync
    def sync(fd):
        events.append('directory' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file')
        return fsync(fd)
    def fail_save(*args):
        assert events[-2:] == ['file', 'directory']
        raise OSError('simulated replacement failure')
    monkeypatch.setattr(compat.os, 'fsync', sync)
    monkeypatch.setattr(compat, '_save', fail_save)
    with pytest.raises(OSError, match='replacement failure'):
        compat.migrate_volume_seal(barrier.config)
    assert compat.DEFAULT_RECORD.read_bytes() == original
    monkeypatch.setattr(compat, '_save', save)
    assert compat.migrate_volume_seal(barrier.config)['schema'] == 2


@pytest.mark.parametrize('failure', ['same-boot', 'preparing', 'active', 'schema2', 'inode',
                                     'ctime', 'permission', 'hardlink', 'symlink', 'path',
                                     'policy', 'archive', 'busy', 'uuid'])
def test_migration_refusals_leave_old_record_and_never_unseal(barrier, monkeypatch, failure):
    value = legacy_seal(barrier)
    barrier.boot[0] = BOOT_B
    path = barrier.paths['fitting']
    if failure == 'same-boot':
        barrier.boot[0] = BOOT_A
    elif failure in ('preparing', 'active'):
        value['state'] = failure
    elif failure == 'schema2':
        value['schema'] = 2
        for item in value['locks'].values():
            item['volume_uuid'] = BOOT_C
    elif failure == 'inode':
        value['locks']['fitting']['inode'] += 1
    elif failure == 'ctime':
        value['locks']['fitting']['ctime_ns'] += 1
    elif failure == 'permission':
        path.chmod(0o600)
    elif failure == 'hardlink':
        os.link(path, barrier.root / 'extra')
    elif failure == 'symlink':
        path.unlink()
        path.symlink_to(barrier.paths['big'])
    elif failure == 'path':
        value['locks']['fitting']['path'] = str(barrier.root / 'wrong')
    elif failure == 'policy':
        value['policy_sha256'] = '0' * 64
    elif failure == 'archive':
        archive = compat.DEFAULT_RECORD.with_name(f'cutover.schema1.{value["activation_id"]}.json')
        archive.write_text('must preserve')
        archive.chmod(0o600)
    elif failure == 'uuid':
        def unavailable(path):
            raise wire.CapacityError('UUID unavailable')
        monkeypatch.setattr(compat, '_volume_uuid', unavailable)
    compat._save(compat.DEFAULT_RECORD, value)
    original = compat.DEFAULT_RECORD.read_bytes()
    with path.open('rb') as handle:
        if failure == 'busy':
            fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        with pytest.raises((wire.CapacityError, OSError)):
            compat.migrate_volume_seal(barrier.config)
    assert compat.DEFAULT_RECORD.read_bytes() == original
    assert all(p.stat().st_mode & 0o777 == (0o600 if failure == 'permission' and p == path else 0o400)
               for p in barrier.paths.values())
    if failure == 'archive':
        assert archive.read_text() == 'must preserve'


@pytest.mark.parametrize('value', ['', 'invalid', '0' * 32, '00000000-0000-0000-0000-000000000000', None])
def test_unusable_volume_uuids_are_refused(value):
    with pytest.raises(wire.CapacityError, match='volume UUID'):
        compat._uuid(value)


def test_volume_observation_never_falls_back_to_device_number(monkeypatch):
    monkeypatch.setattr(compat.sys, 'platform', 'linux')
    with pytest.raises(wire.CapacityError, match='unavailable'):
        compat._volume_uuid('/')


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
    monkeypatch.setattr(locks, 'native_candidates', lambda **kwargs: [])
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
    def unregistered(*, retry):
        assert retry is True  # Only the launcher opts into the bounded preflight retry.
        return [[654, 987]]
    monkeypatch.setattr(locks, 'native_candidates', unregistered)
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
    monkeypatch.setitem(sys.modules, 'atelier.harness.capacity_client', SimpleNamespace(AdmissionSession=lambda socket, request, **kw: request))
    result = runtime.configured_session(kind=kind, command=command, limit_gib=10, timeout=60, config=config)
    assert result['resources']['cpu_millis'] == cpu
    assert result['resources']['memory_mib'] == 10240
    assert result['performance'] is exclusive
    assert command[-1] != '1000'  # Profiling never substitutes narrower worker arguments.
    if kind == 'game':
        larger = runtime.configured_session(kind=kind, command=command, limit_gib=14, timeout=60, config=config)
        assert larger['resources'] == result['resources'] | {'memory_mib': 14336}
        assert larger['locks'] == result['locks']
        assert larger['performance'] is exclusive
    else:
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
    dict(resources=asdict(Resources(memory_mib=10240, cpu_millis=0)))])
def test_explicit_session_requires_checkout_lock_and_cpu(tmp_path, changes):
    request = dict(phase='job', workers=3, checkout=str(runtime.REPO), locks=['checkout:' + str(runtime.REPO)],
                   performance=False, resources=asdict(Resources(memory_mib=10240, cpu_millis=3000, io_slots=1)))
    admission = SimpleNamespace(mode='capacity', request=request | changes)
    with pytest.raises(ValueError, match='checkout named lock|CPU capacity'):
        guarded.run(['Blender', '--threads', '3'], tmp_path / 'absent', admission=admission)


@pytest.mark.parametrize('io_slots', [0, 1])
def test_explicit_session_accepts_optional_io(io_slots):
    admission = SimpleNamespace(request=dict(phase='job', workers=3, checkout=str(runtime.REPO),
        locks=['checkout:' + str(runtime.REPO)], performance=False,
        resources=asdict(Resources(memory_mib=10240, cpu_millis=3000, io_slots=io_slots))))
    runtime.validate_session_profile(admission, kind='job', command=['Blender', '--threads', '3'], limit_gib=10)


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


@pytest.fixture
def optional_io_actor(short_path, monkeypatch, request):
    """An isolated actor with mocked compatibility, identities, guards and exit watches."""
    total = Resources(memory_mib=16384, cpu_millis=16000, temp_mib=32768,
                      io_slots=getattr(request, 'param', 1))
    reserve = Resources(memory_mib=4096, cpu_millis=1000)
    proof = dict(activation_id='optional-io-fixture', socket=str(short_path / 'broker/broker.sock'),
                 disk_pool=str(short_path), total=asdict(total), reserve=asdict(reserve))
    monkeypatch.setattr(compat, 'verify', lambda *args, **kwargs: proof)
    class Watch:
        def __init__(self, pin):
            pass
        def poll(self):
            return False
        def close(self):
            pass
    instance = broker.CapacityBroker(short_path / 'broker', total=total, reserve=reserve,
        disk_pool=short_path, mode='capacity', cutover=compat.DEFAULT_RECORD, policy_sha256='0' * 64,
        started=lambda pid: pid * 100, alive=lambda pin: True, watch=Watch,
        guards=lambda *args: wire.GuardFacts((), 0), child_of=lambda *args: True,
        parent=lambda pin: None, boot=lambda: BOOT_B, foreign=lambda: [],
        observe=lambda: dict(observed_monotonic=time.monotonic(), available_memory_mib=99999,
                             available_temp_mib=99999))
    yield instance
    instance.close()


@pytest.mark.parametrize('optional_io_actor', [0, 1], indirect=True)
def test_full_actor_admits_zero_io_jobs_without_a_universal_charge(optional_io_actor):
    instance = optional_io_actor
    resources = asdict(Resources(memory_mib=1024, cpu_millis=3000))
    for index in (1, 2):
        owner = (100 + index, (100 + index) * 100)
        message, response = offer(instance, owner, str(index), resources=resources)
        assert response['selected']
        assert gate_start(instance, owner, message, 200 + index)['admission']
    status, _ = instance.handle(dict(namespace=wire.NAMESPACE, action='status'), (101, 10100))
    assert status['charged_count'] == 2
    assert status['charged_resources'] == asdict(Resources(memory_mib=2048, cpu_millis=6000))


@pytest.mark.parametrize('changes', [
    dict(resources=asdict(Resources(memory_mib=1024, cpu_millis=13000))),
    dict(resources=asdict(Resources(memory_mib=12288, cpu_millis=3000))),
    dict(checkout='holder'), dict(performance=True),
])
def test_zero_io_does_not_relax_cpu_memory_locks_or_exclusion(optional_io_actor, changes):
    instance = optional_io_actor
    resources = asdict(Resources(memory_mib=1024, cpu_millis=3000))
    message, _ = offer(instance, (101, 10100), 'holder', resources=resources)
    gate_start(instance, (101, 10100), message, 201)
    _, response = offer(instance, (102, 10200), 'candidate', **(dict(resources=resources) | changes))
    assert not response['selected']


def test_explicit_io_exhaustion_still_blocks_nonzero_claims(optional_io_actor):
    instance = optional_io_actor
    message, _ = offer(instance, (101, 10100), 'io-holder')  # Explicitly claims the one I/O token.
    gate_start(instance, (101, 10100), message, 201)
    _, blocked = offer(instance, (102, 10200), 'io-waiter')
    assert not blocked['selected']
    _, selected = offer(instance, (103, 10300), 'zero-io',
                        resources=asdict(Resources(memory_mib=1024, cpu_millis=3000)))
    assert selected['selected']


def test_zero_io_full_request_still_requires_cpu_and_checkout_lock(optional_io_actor):
    instance = optional_io_actor
    with pytest.raises(wire.CapacityError, match='nonzero CPU'):
        offer(instance, (101, 10100), 'no-cpu', resources=asdict(Resources(memory_mib=1024)))
    with pytest.raises(wire.CapacityError, match='checkout named lock'):
        offer(instance, (101, 10100), 'no-lock', locks=[],
              resources=asdict(Resources(memory_mib=1024, cpu_millis=3000)))
    with pytest.raises(wire.CapacityError, match='exclusive'):
        offer(instance, (101, 10100), 'game', phase='game',
              resources=asdict(Resources(memory_mib=1024, cpu_millis=3000)))


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


def test_two_shared_editors_fit_but_third_and_same_checkout_do_not(actor):
    instance, _ = actor
    cpu = (instance.total.cpu_millis - instance.reserve.cpu_millis + 1) // 2
    options = dict(workers=None, shared_editor=True, performance=False,
                   resources=asdict(Resources(memory_mib=1024, cpu_millis=cpu)))
    for index in (1, 2):
        owner = (100 + index, (100 + index) * 100)
        message, response = offer(instance, owner, f'editor-{index}', **options)
        assert response['selected']
        gate_start(instance, owner, message, 200 + index)
        if index == 1:
            _, locked = offer(instance, (103, 10300), 'same-checkout', checkout='editor-1', **options)
            assert not locked['selected']
    _, third = offer(instance, (104, 10400), 'third-editor', **options)
    assert not third['selected']
    _, exclusive = offer(instance, (105, 10500), 'capture', workers=None, performance=True,
                         resources=asdict(Resources(memory_mib=1024, cpu_millis=cpu * 2)))
    assert not exclusive['selected']


@pytest.mark.parametrize('changes', [dict(workers=3), dict(phase='game'), dict(phase='compile'),
    dict(performance=True), dict(shared_editor=1),
    dict(resources=asdict(Resources(memory_mib=1024, cpu_millis=5499)))])
def test_broker_refuses_mislabelled_or_undersized_shared_editors(actor, changes):
    instance, _ = actor
    with pytest.raises(wire.CapacityError, match='editor'):
        offer(instance, (101, 10100), 'bad-editor', **(dict(workers=None, shared_editor=True,
            resources=asdict(Resources(memory_mib=1024, cpu_millis=5500))) | changes))


def test_shared_editor_retains_existing_nonexclusive_release_rule(actor):
    instance, _ = actor
    assert instance._terminal_tree_exit({'request': {'shared_editor': True, 'performance': False}}) is None


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


@pytest.mark.parametrize('mode', ['capacity', 'sealed-maintenance'])
def test_full_socket_configured_python_runs_under_real_guards_and_releases(barrier, monkeypatch, mode):
    from atelier.harness import capacity_client
    if mode == 'capacity':
        proof = activated(barrier)
        settings = broker.load_config(barrier.config)
    else:
        settings, proof = maintenance_settings(barrier)
    instance = broker.CapacityBroker(**settings,
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
    client_settings = dict(schema=2, cutover=str(compat.DEFAULT_RECORD), socket=str(instance.socket_path),
        profiles={kind: profile for kind in ('job', 'game', 'compile')})
    if mode == 'sealed-maintenance':
        client_settings.update(schema=3, mode=mode, seal_policy_sha256=proof['policy_sha256'])
    config.write_text(json.dumps(client_settings))
    config.chmod(0o600)
    monkeypatch.setenv('ATELIER_CAPACITY_CLIENT', str(config))
    # Only native inventory is injected; real Python, socket, SQLite, SH flocks, exec gate and both monitors run.
    monkeypatch.setattr(locks, 'native_candidates', lambda **kwargs: [])
    folder = barrier.root / 'real-guard'
    try:
        assert guarded.run([sys.executable, '-c', 'print("full capacity executed")'], folder,
                           limit_gib=.25, timeout=10, invocation_id='33333333333343338333333333333333') == 0
        assert 'full capacity executed' in (folder / 'stdout.log').read_text()
        assert json.loads((folder / 'memory-health-tree.json').read_text())['state'] == 'child_exited'
        status = capacity_client.status(instance.socket_path)
        assert status['mode'] == mode and status['cutover'] is (mode == 'capacity') and status['charged_count'] == 0
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


def maintenance_settings(barrier):
    legacy_seal(barrier)
    barrier.boot[0] = BOOT_B
    proof = compat.migrate_volume_seal(barrier.config)
    value = dict(barrier.value, schema=3, mode='sealed-maintenance', seal_policy_sha256=proof['policy_sha256'])
    path = barrier.root / 'maintenance.json'
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    return broker.load_config(path), proof


def test_maintenance_preserves_seal_policy_and_requires_explicit_schema(barrier):
    settings, proof = maintenance_settings(barrier)
    assert settings['policy_sha256'] == proof['policy_sha256']
    assert settings['mode'] == 'sealed-maintenance'
    assert compat.verify_maintenance(policy_sha256=proof['policy_sha256']) == proof
    with pytest.raises(wire.CapacityError, match='new OS boot'):
        compat.activate(barrier.config)
    with closing(broker.CapacityBroker(**settings)) as service:
        status = service._status(service._load())
        assert status['mode'] == 'sealed-maintenance' and status['cutover'] is False
        assert status['compatibility_healthy'] is True
    assert compat.read() == proof


@pytest.mark.parametrize('change', ['boot', 'active', 'schema1', 'policy', 'volume', 'write'])
def test_maintenance_refuses_unproven_or_changed_seals(barrier, monkeypatch, change):
    settings, proof = maintenance_settings(barrier)
    if change == 'boot':
        barrier.boot[0] = BOOT_C
    elif change == 'active':
        proof['state'] = 'active'
        compat._save(compat.DEFAULT_RECORD, proof)
    elif change == 'schema1':
        proof['schema'] = 1
        for item in proof['locks'].values():
            item.pop('volume_uuid')
        compat._save(compat.DEFAULT_RECORD, proof)
    elif change == 'policy':
        settings['policy_sha256'] = 'a' * 64
    elif change == 'volume':
        monkeypatch.setattr(compat, '_volume_uuid', lambda path: BOOT_C)
    else:
        barrier.paths['small'].chmod(0o600)
    with pytest.raises((wire.CapacityError, OSError)):
        broker.CapacityBroker(**settings)


@pytest.mark.parametrize('lane', ['big', 'small', 'fitting'])
def test_maintenance_takes_every_readonly_lane_exclusively_and_releases_partial(barrier, monkeypatch, lane):
    settings, proof = maintenance_settings(barrier)
    admission = SimpleNamespace(mode='sealed-maintenance', cutover=compat.DEFAULT_RECORD,
        seal_policy_sha256=settings['policy_sha256'], activation_id=proof['activation_id'], owned=lambda pins: set())
    monkeypatch.setattr(locks, 'native_candidates', lambda **kwargs: [])
    before = {name: (path.read_bytes(), path.stat().st_ino, path.stat().st_ctime_ns)
              for name, path in barrier.paths.items()}
    with barrier.paths[lane].open('rb') as shared:
        fcntl.flock(shared, fcntl.LOCK_SH | fcntl.LOCK_NB)
        with pytest.raises(locks.RenderBusy):
            with locks.render_lock('blocked maintenance', capacity=admission):
                pytest.fail('shared holder must exclude maintenance')
    with locks.render_lock('maintenance', capacity=admission):
        for path in barrier.paths.values():
            with path.open('rb') as other:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(other, fcntl.LOCK_SH | fcntl.LOCK_NB)
        # Full activation's future-boot verification can pass, but its EX acquisition still refuses.
        barrier.boot[0] = BOOT_C
        with pytest.raises(BlockingIOError):
            compat.activate(barrier.config)
        barrier.boot[0] = BOOT_B
    assert before == {name: (path.read_bytes(), path.stat().st_ino, path.stat().st_ctime_ns)
                      for name, path in barrier.paths.items()}
    for path in barrier.paths.values():
        with path.open('rb') as other:
            fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)


@pytest.mark.parametrize('performance,cpu,accepted', [(False, 11000, False), (True, 3000, False),
                                                    (True, 12000, False), (True, 11000, True)])
def test_maintenance_broker_requires_full_cpu_and_exclusion_even_bounded(barrier, performance, cpu, accepted):
    settings, _ = maintenance_settings(barrier)
    with closing(broker.CapacityBroker(**settings)) as service:
        request = dict(id='test', resources=asdict(Resources(memory_mib=10240, cpu_millis=cpu)),
            workers=3, phase='job', checkout=str(barrier.root), locks=['checkout:' + str(barrier.root)],
            performance=performance)
        if accepted:
            assert service._request(request)['performance'] is True
        else:
            with pytest.raises(wire.CapacityError, match='Maintenance requires'):
                service._request(request)


def test_maintenance_rejects_changed_service_resources_and_endpoint(barrier):
    settings, _ = maintenance_settings(barrier)
    for changes in [dict(total=Resources(**(asdict(settings['total']) | {'memory_mib': 65536}))), dict(state_directory=barrier.root / 'different')]:
        with pytest.raises(wire.CapacityError, match='differ from the sealed policy'):
            broker.CapacityBroker(**(settings | changes))


def test_maintenance_client_fences_exact_mode_and_activation(barrier):
    from atelier.harness.capacity_client import AdmissionSession
    settings, proof = maintenance_settings(barrier)
    session = AdmissionSession(proof['socket'], {}, cutover=compat.DEFAULT_RECORD,
        mode='sealed-maintenance', seal_policy_sha256=settings['policy_sha256'])
    assert session._fence() == {'activation_id': proof['activation_id']}
    for response in [dict(mode='capacity', activation_id=proof['activation_id']),
                     dict(mode='sealed-maintenance', activation_id='different')]:
        with pytest.raises(wire.CapacityError, match='mode or compatibility epoch'):
            session._response(response, None)


@pytest.mark.parametrize('failure', ['guard', 'seal'])
def test_maintenance_lost_enforcement_retains_charge_and_blocks_other_go(barrier, failure):
    settings, _ = maintenance_settings(barrier)
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
    with closing(broker.CapacityBroker(**settings, started=lambda pid: pid * 100,
            alive=lambda pin: True, watch=Watch, guards=guards, child_of=lambda *args: True,
            parent=lambda pin: None, foreign=lambda: [],
            observe=lambda: dict(observed_monotonic=time.monotonic(), available_memory_mib=99999,
                                 available_temp_mib=99999))) as instance:
        envelope = dict(performance=True, resources=asdict(Resources(memory_mib=1024, cpu_millis=11000)))
        first, _ = offer(instance, (101, 10100), 'a', **envelope)
        gate_start(instance, (101, 10100), first, 201)
        second, offered = offer(instance, (102, 10200), 'b', **envelope)
        assert not offered['selected']
        with pytest.raises(wire.CapacityError, match='Maintenance requires'):
            instance.handle(first | dict(action='replace', resources=asdict(Resources(memory_mib=1024, cpu_millis=3000)),
                                         locks=['checkout:' + str(instance.directory.parent / 'a')]), (101, 10100))
        if failure == 'guard':
            healthy[0] = False
        else:
            barrier.paths['small'].chmod(0o600)
        status, _ = instance.handle(dict(namespace=wire.NAMESPACE, action='status'), (102, 10200))
        assert status['charged_count'] == 1 and status['recovering']
        assert next(r for r in status['records'] if r['id'] == 'a')['state'] == 'uncertain'
        with pytest.raises(wire.CapacityError):
            gate_start(instance, (102, 10200), second, 202)


@pytest.mark.parametrize('failure', ['fresh-prepare', 'missing', 'changed-bytes', 'same-boot', 'activation', 'inode'])
def test_maintenance_requires_hash_bound_prior_boot_migration(barrier, failure):
    if failure == 'fresh-prepare':
        proof = compat.prepare(barrier.config)
    else:
        _, proof = maintenance_settings(barrier)
        archive = compat.DEFAULT_RECORD.with_name(f'cutover.schema1.{proof["activation_id"]}.json')
        if failure == 'missing':
            archive.unlink()
        else:
            old = json.loads(archive.read_bytes())
            if failure == 'changed-bytes':
                archive.write_bytes(archive.read_bytes() + b' ')
            else:
                if failure == 'same-boot':
                    old['seal_boot_id'] = BOOT_B
                elif failure == 'activation':
                    old['activation_id'] = '5' * 32
                else:
                    old['locks']['big']['inode'] += 1
                archive.write_text(json.dumps(old))
                # Even a matching claimed hash cannot hide contradictory original migration facts.
                import hashlib
                proof['migration_archive_sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
                compat._save(compat.DEFAULT_RECORD, proof)
    with pytest.raises((wire.CapacityError, OSError)):
        compat.verify_maintenance(policy_sha256=proof['policy_sha256'])



def maintenance_with_eight_gib_sealed_reserve(barrier):
    barrier.value['reserve']['memory_mib'] = 8192
    barrier.config.write_text(json.dumps(barrier.value))
    return maintenance_settings(barrier)


@pytest.mark.parametrize('memory,accepted', [(4095, False), (4096, True), (6144, True), (8192, True), (8193, False)])
def test_maintenance_host_memory_reserve_has_explicit_floor_and_sealed_ceiling(barrier, memory, accepted):
    settings, proof = maintenance_with_eight_gib_sealed_reserve(barrier)
    settings['reserve'] = Resources(**(asdict(settings['reserve']) | {'memory_mib': memory}))
    if accepted:
        with closing(broker.CapacityBroker(**settings)) as instance:
            assert instance.reserve.memory_mib == memory
            assert compat.read() == proof and proof['reserve']['memory_mib'] == 8192
    else:
        with pytest.raises(wire.CapacityError, match='differ from the sealed policy'):
            broker.CapacityBroker(**settings)


@pytest.mark.parametrize('dimension', ['cpu_millis', 'temp_mib', 'io_slots', 'gpu_mib'])
def test_maintenance_reduced_memory_reserve_never_changes_other_dimensions(barrier, dimension):
    settings, _ = maintenance_with_eight_gib_sealed_reserve(barrier)
    values = asdict(settings['reserve']) | {'memory_mib': 4096}
    values[dimension] += 1
    settings['reserve'] = Resources(**values)
    with pytest.raises(wire.CapacityError, match='differ from the sealed policy'):
        broker.CapacityBroker(**settings)


@pytest.mark.parametrize('available,accepted', [(14335, False), (14336, True), (14337, True)])
def test_maintenance_ten_gib_job_requires_exact_fourteen_gib_pressure_floor(barrier, available, accepted):
    settings, _ = maintenance_with_eight_gib_sealed_reserve(barrier)
    settings['reserve'] = Resources(**(asdict(settings['reserve']) | {'memory_mib': 4096}))
    with closing(broker.CapacityBroker(**settings, observe=lambda: dict(observed_monotonic=time.monotonic(),
            available_memory_mib=available, available_temp_mib=99999))) as instance:
        request = instance._request(dict(id='normal', resources=asdict(Resources(memory_mib=10240, cpu_millis=11000)),
            workers=3, phase='job', checkout=str(barrier.root), locks=['checkout:' + str(barrier.root)], performance=True))
        candidate = dict(state='queued', request=request)
        if accepted:
            instance._pressure({'records': {'normal': candidate}}, candidate)
        else:
            with pytest.raises(wire.CapacityError, match='pressure refuses the complete reservation'):
                instance._pressure({'records': {'normal': candidate}}, candidate)
        assert request['resources']['memory_mib'] == 10240


def test_full_mode_refuses_reduced_host_memory_reserve(barrier):
    settings, _ = maintenance_with_eight_gib_sealed_reserve(barrier)
    barrier.boot[0] = BOOT_C
    compat.activate(barrier.config)
    settings.update(mode='capacity', reserve=Resources(**(asdict(settings['reserve']) | {'memory_mib': 4096})))
    with pytest.raises(wire.CapacityError, match='differ from the sealed policy'):
        broker.CapacityBroker(**settings)


def calibrated_full_settings(barrier, memory=4096):
    settings, _ = maintenance_with_eight_gib_sealed_reserve(barrier)
    barrier.boot[0] = BOOT_C
    proof = compat.activate(barrier.config)
    value = dict(barrier.value, schema=4, seal_policy_sha256=proof['policy_sha256'])
    value['reserve'] = dict(value['reserve'], memory_mib=memory)
    path = barrier.root / 'full-calibrated.json'
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    return path, proof


@pytest.mark.parametrize('memory,accepted', [(0, False), (475, False), (476, True), (500, True),
                                           (4095, True), (4096, True), (6144, True), (8192, True), (8193, False)])
def test_explicit_full_calibration_preserves_seal_and_memory_bounds(barrier, memory, accepted):
    path, proof = calibrated_full_settings(barrier, memory)
    before = compat.DEFAULT_RECORD.read_bytes()
    settings = broker.load_config(path)
    assert settings['calibrated_memory_reserve'] is True
    if accepted:
        with closing(broker.CapacityBroker(**settings)) as instance:
            assert instance.mode == 'capacity' and instance.reserve.memory_mib == memory
            assert instance.policy_sha256 == proof['policy_sha256']
    else:
        with pytest.raises(wire.CapacityError, match='differ from the sealed policy'):
            broker.CapacityBroker(**settings)
    assert compat.DEFAULT_RECORD.read_bytes() == before
    assert proof['reserve']['memory_mib'] == 8192


@pytest.mark.parametrize('dimension', ['cpu_millis', 'temp_mib', 'io_slots', 'gpu_mib'])
def test_calibrated_full_never_changes_other_reserves(barrier, dimension):
    path, _ = calibrated_full_settings(barrier)
    settings = broker.load_config(path)
    settings['reserve'] = Resources(**(asdict(settings['reserve']) | {dimension: 1 + getattr(settings['reserve'], dimension)}))
    with pytest.raises(wire.CapacityError, match='differ from the sealed policy'):
        broker.CapacityBroker(**settings)


@pytest.mark.parametrize('available,accepted', [(14335, False), (14336, True), (14337, True)])
def test_calibrated_full_still_requires_entire_job_guard_plus_host_reserve(barrier, available, accepted):
    path, _ = calibrated_full_settings(barrier)
    with closing(broker.CapacityBroker(**broker.load_config(path), observe=lambda: dict(
            observed_monotonic=time.monotonic(), available_memory_mib=available, available_temp_mib=99999))) as instance:
        request = instance._request(dict(id='normal', resources=asdict(Resources(memory_mib=10240, cpu_millis=11000)),
            workers=3, phase='job', checkout=str(barrier.root), locks=['checkout:' + str(barrier.root)], performance=True))
        candidate = dict(state='queued', request=request)
        if accepted:
            instance._pressure({'records': {'normal': candidate}}, candidate)
        else:
            with pytest.raises(wire.CapacityError, match='pressure refuses the complete reservation'):
                instance._pressure({'records': {'normal': candidate}}, candidate)
        assert request['resources']['memory_mib'] == 10240


@pytest.mark.parametrize('available,accepted', [(11263, False), (11264, True)])
def test_calibrated_full_keeps_a_running_peers_entire_remaining_growth(barrier, available, accepted):
    path, _ = calibrated_full_settings(barrier)
    with closing(broker.CapacityBroker(**broker.load_config(path),
            guards=lambda *args: wire.GuardFacts((), 1024**3), observe=lambda: dict(
                observed_monotonic=time.monotonic(), available_memory_mib=available, available_temp_mib=99999))) as instance:
        request = dict(id='new', resources=asdict(Resources(memory_mib=4096, cpu_millis=1000)))
        candidate = dict(state='queued', request=request)
        peer = dict(state='running', request=request, child=[99, 999], principal=[88, 888],
                    guards={}, limit_bytes=4 * 1024**3)
        if accepted:
            instance._pressure({'records': {'new': candidate, 'peer': peer}}, candidate)
        else:
            with pytest.raises(wire.CapacityError, match='pressure refuses the complete reservation'):
                instance._pressure({'records': {'new': candidate, 'peer': peer}}, candidate)


def test_calibrated_full_pins_its_config_original_seal_and_totals(barrier):
    import hashlib
    path, proof = calibrated_full_settings(barrier)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    settings = broker.load_config(path, expected_sha256=digest)
    assert settings['policy_sha256'] == proof['policy_sha256']
    with pytest.raises(wire.CapacityError, match='policy changed'):
        broker.load_config(path, expected_sha256='f' * 64)
    settings['total'] = Resources(**(asdict(settings['total']) | {'memory_mib': 65536}))
    with pytest.raises(wire.CapacityError, match='differ from the sealed policy'):
        broker.CapacityBroker(**settings)
    settings = broker.load_config(path)
    settings['policy_sha256'] = 'f' * 64
    with pytest.raises(wire.CapacityError):
        broker.CapacityBroker(**settings)


@pytest.mark.parametrize('digest', [None, '', 'f' * 63, 'g' * 64])
def test_calibrated_full_refuses_missing_or_invalid_original_seal_digest(barrier, digest):
    path, _ = calibrated_full_settings(barrier)
    value = json.loads(path.read_bytes())
    if digest is None:
        value.pop('seal_policy_sha256')
    else:
        value['seal_policy_sha256'] = digest
    path.write_text(json.dumps(value))
    with pytest.raises(wire.CapacityError, match='Unsupported capacity broker configuration'):
        broker.load_config(path)


@pytest.mark.parametrize('value,mode', [(True, 'legacy-bridge'), (True, 'sealed-maintenance'),
                                      (1, 'capacity'), (None, 'capacity')])
def test_reserve_calibration_flag_is_typed_and_full_mode_only(barrier, value, mode):
    settings, _ = maintenance_with_eight_gib_sealed_reserve(barrier)
    settings.update(mode=mode, calibrated_memory_reserve=value)
    with pytest.raises(wire.CapacityError, match='calibration requires explicit full capacity'):
        broker.CapacityBroker(**settings)


def test_calibrated_full_cannot_select_a_subfloor_unchanged_seal(barrier):
    barrier.value['reserve']['memory_mib'] = 475
    barrier.config.write_text(json.dumps(barrier.value))
    activated(barrier)
    settings = broker.load_config(barrier.config)
    # The normal unchanged policy is valid, but it must not enter the explicit calibrated schema.
    with closing(broker.CapacityBroker(**settings)) as instance:
        assert instance.reserve.memory_mib == 475
    settings['calibrated_memory_reserve'] = True
    with pytest.raises(wire.CapacityError, match='differ from the sealed policy'):
        broker.CapacityBroker(**settings)


@pytest.mark.parametrize('mode', ['maintenance', 'calibrated-full'])
def test_serve_requires_an_own_configuration_pin_before_starting_calibrated_broker(barrier, monkeypatch, mode):
    if mode == 'maintenance':
        maintenance_with_eight_gib_sealed_reserve(barrier)
        path = barrier.root / 'maintenance.json'
    else:
        path, _ = calibrated_full_settings(barrier)
    monkeypatch.delenv('ATELIER_CAPACITY_SERVICE_CONFIG_SHA256', raising=False)
    monkeypatch.setattr(broker, 'CapacityBroker', lambda **kwargs: pytest.fail('unbound broker started'))
    with pytest.raises(wire.CapacityError, match='supervised configuration digest'):
        broker.main(path)


def test_supervised_calibrated_configuration_binds_own_bytes_before_serve(barrier, monkeypatch):
    import hashlib
    path, _ = calibrated_full_settings(barrier)
    from atelier.harness import capacity_supervision
    recipe = capacity_supervision.configuration(path)
    digest = recipe['EnvironmentVariables']['ATELIER_CAPACITY_SERVICE_CONFIG_SHA256']
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setenv('ATELIER_CAPACITY_SERVICE_CONFIG_SHA256', digest)
    calls = []
    class Service:
        def __init__(self, **settings): calls.append(settings)
        def serve_forever(self): calls.append('serve')
        def close(self): calls.append('close')
    monkeypatch.setattr(broker, 'CapacityBroker', Service)
    assert broker.main(path) == 0
    assert calls[0]['calibrated_memory_reserve'] is True and calls[1:] == ['serve', 'close']
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(wire.CapacityError, match='policy changed'):
        broker.main(path)
    assert calls[1:] == ['serve', 'close']


def test_reduced_maintenance_reserve_still_pins_total_and_own_configuration(barrier):
    import hashlib
    settings, proof = maintenance_with_eight_gib_sealed_reserve(barrier)
    path = barrier.root / 'maintenance.json'
    value = json.loads(path.read_bytes())
    value['reserve']['memory_mib'] = 4096
    raw = json.dumps(value).encode()
    path.write_bytes(raw)
    selected = broker.load_config(path, expected_sha256=hashlib.sha256(raw).hexdigest())
    assert selected['reserve'].memory_mib == 4096 and selected['policy_sha256'] == proof['policy_sha256']
    with pytest.raises(wire.CapacityError, match='policy changed'):
        broker.load_config(path, expected_sha256='f' * 64)
    selected['total'] = Resources(**(asdict(settings['total']) | {'memory_mib': 65536}))
    with pytest.raises(wire.CapacityError, match='differ from the sealed policy'):
        broker.CapacityBroker(**selected)



def test_bounded_public_status_keeps_active_and_queue_order_then_newest_released(barrier):
    settings, _ = maintenance_settings(barrier)
    with closing(broker.CapacityBroker(**settings)) as instance:
        records = {}
        for sequence in range(1, 39):
            state = 'released' if sequence <= 35 else 'running' if sequence == 36 else 'queued'
            name = str(sequence)
            request = dict(id=name, resources=asdict(Resources(memory_mib=1024, cpu_millis=11000)),
                locks=['checkout:' + name], seconds=60, performance=True)
            records[name] = dict(request=request, state=state, sequence=sequence, first_ready=1., bypasses=0)
        status = instance._status(dict(epoch=1, records=records))
        visible = status['records']
        assert [row['id'] for row in visible[:3]] == ['36', '37', '38']
        assert [row['id'] for row in visible[3:]] == [str(number) for number in range(35, 6, -1)]
        assert status['truncated'] and status['returned_records'] == 32 and status['total_records'] == 38
        assert status['charged_count'] == 1 and status['waiting_count'] == 2
        assert status['charged_resources']['memory_mib'] == 1024
        assert len(records) == 38 and records['1']['state'] == 'released'


@pytest.mark.parametrize('blocked_cleanup', [None, 'aggregate', 'close', 'memory_limit', 'test_duration'])
@pytest.mark.parametrize('denial_reason', ['selection-changed', 'pressure-wait'])
def test_automatic_full_launch_requeues_only_after_real_no_go_cleanup(barrier, monkeypatch, blocked_cleanup, denial_reason):
    """Real socket, gate children, sealed flocks and both monitors; payload executes once."""
    from atelier.harness import capacity_client
    activated(barrier)
    instance = broker.CapacityBroker(**broker.load_config(barrier.config),
        observe=lambda: dict(observed_monotonic=time.monotonic(), available_memory_mib=99999))
    errors = []
    def serve():
        try:
            instance.serve_forever()
        except BaseException as error:
            errors.append(error)
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    profile = dict(resources=asdict(Resources(memory_mib=256, cpu_millis=1000)), locks=[])
    config = barrier.root / 'requeue-client.json'
    config.write_text(json.dumps(dict(schema=2, cutover=str(compat.DEFAULT_RECORD),
        socket=str(instance.socket_path), profiles={kind: profile for kind in ('job', 'game', 'compile')})))
    config.chmod(0o600)
    monkeypatch.setenv('ATELIER_CAPACITY_CLIENT', str(config))
    monkeypatch.setattr(locks, 'native_candidates', lambda **kwargs: [])
    original = capacity_client.AdmissionSession.start
    starts, ready = [], []
    folder, marker = barrier.root / 'requeue-guard', barrier.root / 'useful-work'
    def interleave(admission, **kwargs):
        starts.append((kwargs['child_pid'], kwargs['child_start']))
        row = next(r for r in capacity_client.status(instance.socket_path)['records']
                   if r['id'] == admission.request['id'])
        ready.append(row['first_ready'])
        if len(starts) != 1:
            assert not marker.exists()
            archive, = folder.glob('lost-offer-*/no-go.json')
            proof = json.loads(archive.read_text())
            assert tuple(proof['child']) == starts[0]
            assert proof['no_go'] and proof['uncharged_close'] and proof['reason'] == denial_reason
            assert proof['terminal']['processes'] == [] and proof['terminal']['footprint_bytes'] == 0
            return original(admission, **kwargs)
        if denial_reason == 'pressure-wait':
            observe = instance.observe
            instance.observe = lambda: dict(observed_monotonic=time.monotonic(), available_memory_mib=0)
            try:
                return original(admission, **kwargs)
            finally:
                instance.observe = observe
        short = capacity_client.AdmissionSession(instance.socket_path,
            {**admission.request, 'id': 'intervening-short', 'seconds': 1}, cutover=compat.DEFAULT_RECORD)
        assert short.offer()['selected']
        try:
            return original(admission, **kwargs)
        finally:
            short.close()
    monkeypatch.setattr(capacity_client.AdmissionSession, 'start', interleave)
    if blocked_cleanup in ('memory_limit', 'test_duration'):
        settle = guarded.settle_completion_guards
        def stopped(monitor, tree):
            settle(monitor, tree)
            assert monitor.poll() == 0  # The real monitor's zero status cannot certify no stop.
            path = folder / 'memory-health.json'
            value = json.loads(path.read_text())
            value['state'] = blocked_cleanup
            path.write_text(json.dumps(value))
        monkeypatch.setattr(guarded, 'settle_completion_guards', stopped)
    elif blocked_cleanup == 'aggregate':
        from atelier.harness.safety.guard import TreeMonitor
        finish = TreeMonitor.finish
        def failed_finish(monitor, *args, **kwargs):
            finish(monitor, *args, **kwargs)
            raise RuntimeError('injected failed aggregate settlement')
        monkeypatch.setattr(TreeMonitor, 'finish', failed_finish)
    elif blocked_cleanup == 'close':
        close = capacity_client.AdmissionSession.close
        def failed_close(admission, **kwargs):
            response = close(admission, **kwargs)
            if admission.request['id'] != 'intervening-short':
                raise capacity_client.CapacityError('injected unconfirmed close')
            return response
        monkeypatch.setattr(capacity_client.AdmissionSession, 'close', failed_close)
    try:
        command = [sys.executable, '-c',
            'import pathlib,sys; pathlib.Path(sys.argv[1]).open("a").write("executed\\n")', str(marker)]
        if blocked_cleanup:
            error = SystemExit if blocked_cleanup in ('memory_limit', 'test_duration') else (RuntimeError, capacity_client.CapacityError)
            message = 'memory guard stopped the child' if isinstance(error, type) else 'injected'
            with pytest.raises(error, match=message):
                guarded.run(command, folder, limit_gib=.25, timeout=600)
            assert len(starts) == 1 and not marker.exists()
            assert not list(folder.glob('lost-offer-*'))
            assert capacity_client.status(instance.socket_path)['charged_count'] == 0
            return
        assert guarded.run(command, folder, limit_gib=.25, timeout=600) == 0
        assert marker.read_text() == 'executed\n'
        assert len(starts) == 2 and starts[0] != starts[1] and ready[0] == ready[1]
        report = capacity_client.status(instance.socket_path)
        assert report['charged_count'] == report['waiting_count'] == 0
        assert not instance._gates
    finally:
        instance._stop.set()
        thread.join(timeout=3)
        instance.close()
        assert not thread.is_alive() and not errors, errors


@pytest.mark.parametrize('available,accepted', [(10715, False), (10716, True), (10717, True)])
def test_operator_small_reserve_keeps_full_guard_and_fresh_pressure(barrier, available, accepted):
    path, proof = calibrated_full_settings(barrier, 476)
    before = compat.DEFAULT_RECORD.read_bytes()
    with closing(broker.CapacityBroker(**broker.load_config(path), observe=lambda: dict(
            observed_monotonic=time.monotonic(), available_memory_mib=available))) as instance:
        candidate = dict(state='queued', request=dict(resources=asdict(Resources(memory_mib=10240))))
        if accepted:
            instance._pressure({'records': {'normal': candidate}}, candidate)
        else:
            with pytest.raises(broker.PressureWait):
                instance._pressure({'records': {'normal': candidate}}, candidate)
        instance.observe = lambda: dict(observed_monotonic=0, available_memory_mib=999999)
        with pytest.raises(wire.CapacityError, match='Fresh capacity pressure'):
            instance._pressure({'records': {'normal': candidate}}, candidate)
        assert candidate['request']['resources']['memory_mib'] == 10240
    assert compat.DEFAULT_RECORD.read_bytes() == before and proof['reserve']['memory_mib'] == 8192


@pytest.mark.parametrize('available,accepted', [(11739, False), (11740, True)])
def test_operator_small_reserve_still_counts_entire_remaining_peer_growth(barrier, available, accepted):
    path, _ = calibrated_full_settings(barrier, 476)
    with closing(broker.CapacityBroker(**broker.load_config(path),
            guards=lambda *args: wire.GuardFacts((), 1024**3), observe=lambda: dict(
                observed_monotonic=time.monotonic(), available_memory_mib=available))) as instance:
        candidate = dict(state='queued', request=dict(resources=asdict(Resources(memory_mib=4096))))
        peer = dict(state='running', request=dict(resources=asdict(Resources(memory_mib=8192))),
                    child=[99, 999], principal=[88, 888], guards={}, limit_bytes=8 * 1024**3)
        if accepted:
            instance._pressure({'records': {'new': candidate, 'peer': peer}}, candidate)
        else:
            with pytest.raises(broker.PressureWait):
                instance._pressure({'records': {'new': candidate, 'peer': peer}}, candidate)


@pytest.mark.parametrize('count,cpu_reserve,accepted', [(12, 0, True), (11, 0, False), (None, 0, False),
    (10, 1000, True), (10, 0, False), (20, 1001, False)])
def test_explicit_cpu_reserve_is_bounded_by_seal_and_actual_host(barrier, monkeypatch, count, cpu_reserve, accepted):
    path, proof = calibrated_full_settings(barrier, 476)
    settings = broker.load_config(path)
    settings['reserve'] = Resources(**(asdict(settings['reserve']) | {'cpu_millis': cpu_reserve}))
    monkeypatch.setattr(broker.os, 'cpu_count', lambda: count)
    before = compat.DEFAULT_RECORD.read_bytes()
    if accepted:
        with closing(broker.CapacityBroker(**settings)) as instance:
            assert instance.total.cpu_millis == 12000 and instance.reserve.cpu_millis == cpu_reserve
    else:
        with pytest.raises(wire.CapacityError, match='differ from the sealed policy'):
            broker.CapacityBroker(**settings)
    assert compat.DEFAULT_RECORD.read_bytes() == before and proof['reserve']['cpu_millis'] == 1000


def test_ten_cpu_host_calibration_requires_whole_pool_profiles_without_changing_workers(barrier, monkeypatch):
    barrier.value['total']['cpu_millis'] = 10000
    barrier.value['reserve']['cpu_millis'] = 2000
    path, proof = calibrated_full_settings(barrier, 476)
    settings = broker.load_config(path)
    settings['reserve'] = Resources(**(asdict(settings['reserve']) | {'cpu_millis': 0}))
    monkeypatch.setattr(broker.os, 'cpu_count', lambda: 10)
    with closing(broker.CapacityBroker(**settings)) as instance:
        assert instance.total.cpu_millis == 10000 and instance.reserve.cpu_millis == 0
        request = dict(id='whole', resources=asdict(Resources(memory_mib=10240, cpu_millis=10000)),
                       checkout=str(barrier.root), locks=['checkout:' + str(barrier.root)],
                       phase='game', performance=True)
        assert instance._request(request)['resources']['cpu_millis'] == 10000
        request['resources']['cpu_millis'] = 8000
        with pytest.raises(wire.CapacityError, match='complete managed CPU'):
            instance._request(request)
        request.update(phase='job', workers=3, performance=False)
        request['resources']['cpu_millis'] = 3000
        assert instance._request(request)['workers'] == 3
        assert proof['reserve']['cpu_millis'] == 2000
