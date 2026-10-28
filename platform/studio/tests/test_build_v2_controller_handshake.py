"""Linux-hosted control handoff only: fixture helper never runs an op or claims Stored/Current."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

from atelier.build_v2 import controller_client as client
from atelier.build_v2.controller_recipe import ControllerTarget

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='portable helper handoff runs in hosted Linux; MAC1 deferred')


def fixture(tmp_path, mode='normal'):
    checkout = tmp_path / 'checkout'
    names = ['platform/build-v2/Cargo.toml', 'platform/build-v2/Cargo.lock',
             'platform/build-v2/.cargo/config.toml', 'platform/build-v2/src/lib.rs',
             'platform/build-v2/src/bin/atelier-build-v2.rs']
    for name in names:
        path = checkout / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'# fixture\n')
    (checkout / names[0]).write_text('[package]\nname="fixture"\nversion="0.1.0"\n')
    (checkout / names[2]).write_text('[build]\njobs=3\n')
    (checkout / client.SOURCE_MANIFEST).write_text(json.dumps({'version': 1, 'files': names}))
    source = client.capture_controller(checkout).digest
    script = f'''#!{sys.executable}
import json, os, sys
SOURCE = {source!r}
MODE = {mode!r}
if sys.argv[1:] == ['--identity']:
    print(SOURCE)
    raise SystemExit(0)
args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
request, report, live = [int(args[name]) for name in ('--request-fd', '--report-fd', '--liveness-fd')]
if os.read(live, 1) != b'G':
    raise SystemExit(2)
with os.fdopen(request) as stream:
    invocation = json.load(stream)
assert invocation['execution']['owner']['pid'] == os.getpid()
assert invocation['controller_source'] == SOURCE
io = dict.fromkeys(('cache_opens','cache_lookups','staged_jobs','input_clones','observed_worker_attempts',
                    'worker_files_written','publications','installs','receipt_writes'), 0)
io['worker_attempts_by_unit'] = {{}}
observation = dict(version=1, summary=None, io=io, final_requirements_satisfied=False,
                   cancellation_requested=False, scheduler_error=False,
                   source_finalization='not_opened', root_finalization='not_opened')
result = dict(version=1, nonce=invocation['nonce'], controller_source=SOURCE, observation=observation)
if MODE == 'wrong_nonce': result['nonce'] = '0' * 32
raw = json.dumps(result).encode() if MODE != 'partial' else b'{{"version":1,'
os.write(report, raw)
os.fsync(report)
if MODE == 'replace_report':
    path = os.readlink('/proc/self/fd/' + str(report))
    with open(path + '.foreign', 'xb') as stream:
        stream.write(raw)
    os.chmod(path + '.foreign', 0o600)
    os.replace(path + '.foreign', path)
'''
    binary = tmp_path / 'fixture-helper'
    binary.write_text(script)
    binary.chmod(0o500)
    executable = client.ControllerExecutable(binary, source, hashlib.sha256(binary.read_bytes()).hexdigest())
    marker = ControllerTarget(unit='data.copy', project='fixture', declaration={'schema_version': 2,
        'cache_version': 'v2-1', 'units': []}, staged_inputs={}, content_slots={}, allowed_install_roots=('Game',))
    execution = {'cache_root': str(tmp_path / 'cache'), 'interpreter': sys.executable,
                 'worktree_id': 'a' * 64, 'memory_gib': 1, 'job_seconds': 5,
                 'cleanup_seconds': 2, 'overall_seconds': 10,
                 'provenance': {'checkout': 'fixture', 'branch': 'fixture', 'commit': 'fixture',
                                'dirty': False, 'built_at': 'fixture'}}
    return checkout, executable, marker, execution


def test_owned_helper_startup_records_actual_child_and_preserves_no_op_claim_boundary(tmp_path):
    checkout, executable, marker, execution = fixture(tmp_path)
    result = client.invoke_controller(checkout, executable, marker, tmp_path / 'runs', execution, echo=lambda _: None)
    assert result['diagnostic_log'] == str(next((tmp_path / 'runs').iterdir()) / 'controller.log')
    assert result['state'] == 'observed'
    assert result['returncode'] == 0
    assert result['report']['observation']['final_requirements_satisfied'] is False
    assert result['report']['observation']['summary'] is None  # Not a fabricated real backend proof.
    run = next((tmp_path / 'runs').iterdir())
    spawn = client.read_control(run, 'spawn.json')
    request = client.read_control(run, 'request.json')
    assert spawn['child'] == request['execution']['owner']
    assert spawn['child']['pid'] > 0 and int(spawn['child']['started']) > 0
    assert spawn['binary_sha256'] == executable.binary
    assert spawn['controller_source'] == executable.source
    assert spawn['request_sha256'] == hashlib.sha256((run / 'request.json').read_bytes()).hexdigest()
    assert not (tmp_path / 'cache').exists()
    assert not (checkout / 'Game').exists()


@pytest.mark.parametrize('mode', ['partial', 'wrong_nonce', 'replace_report'])
def test_partial_foreign_or_wrong_identity_helper_reports_stay_incomplete(tmp_path, mode):
    checkout, executable, marker, execution = fixture(tmp_path, mode)
    result = client.invoke_controller(checkout, executable, marker, tmp_path / 'runs', execution, echo=lambda _: None)
    assert result['state'] == 'incomplete'
    assert result['report'] is None
    run = next((tmp_path / 'runs').iterdir())
    assert (run / 'spawn.json').is_file()
    assert client.read_control(run, 'client.json')['verified_report'] is False
    assert not (tmp_path / 'cache').exists()


@pytest.mark.parametrize('fault', ['provider', 'source'])
def test_provider_or_source_change_closes_unreleased_pipe_and_reaps_helper(tmp_path, monkeypatch, fault):
    checkout, executable, marker, execution = fixture(tmp_path)
    actual_probe = client._probe_child
    calls = 0
    def changed(process):
        nonlocal calls
        calls += 1
        owner = actual_probe(process)
        if calls == 2:
            if fault == 'provider':
                owner['started'] = str(int(owner['started']) + 1)
            else:
                (checkout / 'platform/build-v2/src/lib.rs').write_bytes(b'changed controller source')
        return owner
    monkeypatch.setattr(client, '_probe_child', changed)
    with pytest.raises(ValueError, match='changed'):
        client.invoke_controller(checkout, executable, marker, tmp_path / 'runs', execution, echo=lambda _: None)
    run = next((tmp_path / 'runs').iterdir())
    receipt = client.read_control(run, 'client.json')
    assert receipt['state'] == 'incomplete'
    assert receipt['gate_released'] is False
    assert receipt['returncode'] is not None
    assert (run / 'report.json').read_bytes() == b''
    assert not (tmp_path / 'cache').exists()
