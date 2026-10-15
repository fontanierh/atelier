"""The explicit bundle command forwards policy inputs and keeps validation failures nonzero."""
import argparse
import json
from pathlib import Path

import pytest

from atelier import artifact_bundle, artifact_remote, cache_admin


def arguments(argv):
    parser = argparse.ArgumentParser()
    cache_admin.configure(parser.add_subparsers())
    return parser.parse_args(['cache', *argv])


def test_import_requires_explicit_trust_file():
    with pytest.raises(SystemExit) as error:
        arguments(['import-bundle', 'bundle'])
    assert error.value.code == 2


@pytest.mark.parametrize('dry', [False, True])
def test_import_passes_exact_bundle_trust_and_dry_run(monkeypatch, capsys, dry):
    store = object()
    monkeypatch.setattr(cache_admin, 'Store', lambda: store)
    calls = []
    def import_bundle(directory, trust, **kwargs):
        calls.append((directory, trust, kwargs))
        return {'imported': not dry, 'dry_run': dry}
    monkeypatch.setattr(artifact_bundle, 'import_bundle', import_bundle)
    args = arguments(['import-bundle', 'bundle', '--trust', 'publishers.json', *(['--dry-run'] if dry else [])])
    assert cache_admin.main(args) == 0
    assert calls == [(Path('bundle'), Path('publishers.json'), {'store': store, 'dry_run': dry})]
    assert json.loads(capsys.readouterr().out) == {'imported': not dry, 'dry_run': dry}


def test_import_refusal_is_failure_not_a_successful_cache_command(monkeypatch, capsys):
    def refuse(*args, **kwargs):
        raise ValueError('Unknown publisher')
    monkeypatch.setattr(artifact_bundle, 'import_bundle', refuse)
    assert cache_admin.main(arguments(['import-bundle', 'bundle', '--trust', 'publishers.json'])) == 1
    assert capsys.readouterr().out == 'cache: Unknown publisher\n'


def test_fetch_requires_explicit_trust():
    with pytest.raises(SystemExit) as error:
        arguments(['fetch-bundle', 'https://cache.example.test/', 'a' * 64])
    assert error.value.code == 2


def test_fetch_forwards_key_trust_deadline_and_dry_run(monkeypatch, capsys):
    store, calls = object(), []
    monkeypatch.setattr(cache_admin, 'Store', lambda: store)
    def fetch(*args, **kwargs):
        calls.append((args, kwargs))
        return {'dry_run': True}
    monkeypatch.setattr(artifact_remote, 'fetch_bundle', fetch)
    args = arguments(['fetch-bundle', 'https://cache.example.test/', 'a' * 64,
                      '--trust', 'trust.json', '--timeout', '12', '--dry-run'])
    assert cache_admin.main(args) == 0
    assert calls == [(('https://cache.example.test/', 'a' * 64, Path('trust.json')),
                      {'store': store, 'dry_run': True, 'timeout': 12, 'echo': artifact_remote.stderr_progress})]
    assert json.loads(capsys.readouterr().out) == {'dry_run': True}
