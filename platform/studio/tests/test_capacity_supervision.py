"""Preparing a supervisor never enables clients or replaces an active service."""
from dataclasses import asdict
import json
from pathlib import Path
import plistlib
import tempfile
from types import SimpleNamespace

import pytest

from atelier.capacity import Resources
from atelier import capacity_supervision as service


@pytest.fixture
def config():
    with tempfile.TemporaryDirectory(prefix='acs-', dir='/tmp') as directory:
        folder = Path(directory)
        path = folder / 'broker.json'
        path.write_text(json.dumps(dict(schema=1, mode='legacy-bridge', state_directory=str(folder / 'state'),
                                        disk_pool=str(folder), total=asdict(Resources(2048, 4000, 4096, 2, 2048)),
                                        reserve=asdict(Resources(64, 1000, 64)))))
        path.chmod(0o600)
        yield path


def test_manifest_pins_policy_without_creating_state_or_activation(config):
    value = service.configuration(config)
    assert value['ProgramArguments'][-3:] == ['capacity', 'serve', str(config)]
    assert len(value['EnvironmentVariables']['ATELIER_CAPACITY_SERVICE_CONFIG_SHA256']) == 64
    assert value['KeepAlive'] is True
    assert not (config.parent / 'state').exists()
    assert not (config.parent / 'client.json').exists()
    original = value['EnvironmentVariables']['ATELIER_CAPACITY_SERVICE_CONFIG_SHA256']
    config.write_text(config.read_text() + '\n')
    assert service.configuration(config)['EnvironmentVariables']['ATELIER_CAPACITY_SERVICE_CONFIG_SHA256'] != original


def test_supervise_refuses_to_replace_running_configuration(config, monkeypatch):
    monkeypatch.setattr(service.sys, 'platform', 'darwin')
    monkeypatch.setattr(service.Path, 'home', lambda: config.parent)
    path = config.parent / 'Library/LaunchAgents' / (service.LABEL + '.plist')
    path.parent.mkdir(parents=True)
    path.write_bytes(plistlib.dumps(service.configuration(config)))
    config.write_text(config.read_text() + '\n')
    calls = []

    def launchctl(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stderr='')
    monkeypatch.setattr(service.subprocess, 'run', launchctl)
    with pytest.raises(ValueError, match='drain and retire'):
        service.install(config)
    assert len(calls) == 1 and calls[0][1] == 'print'
    assert not (config.parent / 'state').exists()


@pytest.mark.parametrize('linked', ['symlink', 'hardlink'])
def test_supervision_refuses_linked_log_before_bootstrap(config, monkeypatch, linked):
    monkeypatch.setattr(service.sys, 'platform', 'darwin')
    monkeypatch.setattr(service.Path, 'home', lambda: config.parent)
    state = config.parent / 'state'
    state.mkdir(mode=0o700)
    target = config.parent / 'unrelated'
    target.write_text('keep')
    target.chmod(0o600)
    log = state / 'broker.log'
    log.symlink_to(target) if linked == 'symlink' else log.hardlink_to(target)
    calls = []

    def launchctl(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=1, stderr='not installed')
    monkeypatch.setattr(service.subprocess, 'run', launchctl)
    with pytest.raises((OSError, ValueError)):
        service.install(config)
    assert target.read_text() == 'keep'
    assert len(calls) == 1 and calls[0][1] == 'print'
