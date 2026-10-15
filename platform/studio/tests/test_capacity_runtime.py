"""Machine configuration cannot silently weaken a guarded launch's reservation."""
import copy
import json
import sys
from types import SimpleNamespace

import pytest

from atelier import capacity_runtime as runtime


@pytest.fixture
def client(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    path = tmp_path / 'client.json'
    profile = dict(resources=dict(memory_mib=10240, cpu_millis=4000, temp_mib=2048, io_slots=1, gpu_mib=10240),
                   locks=['graphics'])
    value = dict(schema=1, socket=str(tmp_path / 'broker.sock'),
                 profiles={kind: copy.deepcopy(profile) for kind in ('job', 'game', 'compile')})
    monkeypatch.setattr(runtime, 'DEFAULT_CONFIG', path)
    monkeypatch.delenv('ATELIER_CAPACITY_CLIENT', raising=False)
    calls = []

    def session(socket, request):
        calls.append((socket, request))
        return request
    monkeypatch.setitem(sys.modules, 'atelier.capacity_client', SimpleNamespace(AdmissionSession=session))

    def write():
        path.write_text(json.dumps(value))
        path.chmod(0o600)
    return path, value, write, calls


def test_unconfigured_machine_uses_existing_launcher(client):
    assert runtime.configured_session(kind='job', limit_gib=10, timeout=0) is None
    assert client[3] == []


def test_configured_missing_file_refuses_instead_of_falling_back(client, monkeypatch):
    monkeypatch.setenv('ATELIER_CAPACITY_CLIENT', str(client[0]))
    with pytest.raises(ValueError, match='missing'):
        runtime.configured_session(kind='job', limit_gib=10, timeout=0)


def test_configured_profiles_preserve_guard_ceiling_and_checkout_lock(client):
    path, value, write, calls = client
    write()
    result = runtime.configured_session(kind='compile', limit_gib=10, timeout=120)
    assert calls[0][0] == value['socket']
    assert result['resources'] == value['profiles']['compile']['resources']
    assert result['locks'] == sorted(['graphics', 'checkout:' + str(runtime.REPO)])
    assert result['seconds'] == 120
    assert result['performance'] is False


def test_performance_window_reaches_configured_broker_request(client):
    client[2]()
    request = runtime.configured_session(kind='game', limit_gib=10, timeout=330, performance=True)
    assert request['performance'] is True
    assert request['resources'] == client[1]['profiles']['game']['resources']


@pytest.mark.parametrize('value', [None, 0, 1, 'true'])
def test_performance_flag_must_be_boolean_even_without_configuration(client, value):
    with pytest.raises(ValueError, match='performance.*boolean'):
        runtime.configured_session(kind='game', limit_gib=10, timeout=0, performance=value)
    assert client[3] == []


def test_retry_keeps_logical_identity_while_unrelated_actions_are_distinct(client):
    client[2]()
    first = runtime.configured_session(kind='job', limit_gib=10, timeout=120, folder='logs/mesh.guard')
    retry = runtime.configured_session(kind='job', limit_gib=10, timeout=120, folder='logs/mesh.guard')
    other = runtime.configured_session(kind='job', limit_gib=10, timeout=120, folder='logs/cook.guard')
    assert first == retry
    assert first['id'] != other['id']


def test_profile_cannot_hide_a_larger_actual_guard(client):
    client[2]()
    with pytest.raises(ValueError, match='smaller than the actual guard'):
        runtime.configured_session(kind='game', limit_gib=14, timeout=0)
    assert client[3] == []


@pytest.mark.parametrize('field', ['cpu_millis', 'io_slots'])
def test_capacity_profile_must_reserve_cpu_and_io(client, field):
    client[1]['profiles']['job']['resources'][field] = 0
    client[2]()
    with pytest.raises(ValueError, match='CPU and I/O'):
        runtime.configured_session(kind='job', limit_gib=10, timeout=0)


def test_client_configuration_is_not_read_through_a_symlink(client):
    path, _, write, _ = client
    write()
    other = path.with_name('target.json')
    path.rename(other)
    path.symlink_to(other)
    with pytest.raises(OSError):
        runtime.configured_session(kind='job', limit_gib=10, timeout=0)


def test_public_configuration_is_refused(client):
    client[2]()
    client[0].chmod(0o644)
    with pytest.raises(ValueError, match='private owned regular file'):
        runtime.configured_session(kind='job', limit_gib=10, timeout=0)


def test_incomplete_profile_set_cannot_fall_back_for_other_work(client):
    del client[1]['profiles']['compile']
    client[2]()
    with pytest.raises(ValueError, match='job, game and compile'):
        runtime.configured_session(kind='job', limit_gib=10, timeout=0)
