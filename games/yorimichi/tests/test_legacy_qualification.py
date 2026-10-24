"""Finite provider capture; real fresh-process Graph proof lives in the Rust T1a case."""
from pathlib import Path
import importlib.util
import signal
import json
import pytest


def test_current_discovery_provider_roster_uses_static_imports_within_capture_bound(monkeypatch):
    from atelier import paths
    from atelier.build_v2.controller_client import capture_named_sources, MAX_NAMED_ISSUER_FILES
    from atelier.build_v2.legacy_qualification import CapturedCode, captured_spec
    writes = []
    def refuse_write(path, *args, **kwargs):
        writes.append(str(path))
        raise AssertionError('captured declaration preflight attempted mkdir')
    monkeypatch.setattr(Path, 'mkdir', refuse_write)
    name = 'games/yorimichi/legacy_qualification.py'
    initial = capture_named_sources(paths.REPO, (name,))
    spec = captured_spec('existing_discovery_profile',
                         CapturedCode(str(paths.REPO / name), dict(initial.files)[name]))
    profile = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(profile)
    source = capture_named_sources(paths.REPO, profile.source_names(paths.REPO))
    names = dict(source.files)
    assert 'games/yorimichi/build.py' in names
    assert 'games/yorimichi/legacy_qualification.py' in names
    assert 'platform/studio/atelier/build.py' in names
    assert 'platform/studio/atelier/build_products.py' in names
    assert 'games/yorimichi/world/regions/belmonte/source.py' in names
    assert 'games/yorimichi/world/regions/belmonte/query_surface.py' in names
    assert 'games/yorimichi/world/regions/belmonte/terrain.py' in names
    assert 'games/yorimichi/world/regions/village/atomic_sources.py' in names
    assert 'games/yorimichi/world/regions/village/catalogue.py' in names
    for package in ('train', 'regions/brinecove', 'regions/ferry',
                    'regions/hidamari_stable', 'regions/swordcamp'):
        assert f'games/yorimichi/world/{package}/__init__.py' in names
    for name in names:
        boundary = (paths.REPO / 'games/yorimichi' if name.startswith('games/') else
                    paths.REPO / ('platform/studio' if name.startswith('platform/studio/')
                                  else 'platform/harness'))
        parent = (paths.REPO / name).parent
        while parent != boundary:
            assert parent.is_relative_to(boundary)
            initializer = parent / '__init__.py'
            if initializer.is_file():
                assert initializer.relative_to(paths.REPO).as_posix() in names
            parent = parent.parent
    assert all((paths.REPO / name).is_file() for name in names)
    assert len(names) <= MAX_NAMED_ISSUER_FILES == 512
    assert not writes


def test_owned_fixture_cleanup_excludes_shared_descendants_and_exec_transitions():
    from atelier import paths
    from atelier.harness.safety.tree_guard import OwnedTree
    spec = importlib.util.spec_from_file_location(
        'owned_entry_fixture', paths.REPO / 'games/yorimichi/tests/legacy_host_entry_case.py')
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)

    class Table:
        def __init__(self):
            self.names = {pid: 'python' for pid in range(1, 7)}
            self.edges = {1: [2, 3, 5], 3: [4], 5: [6]}
            self.unknown = set()
        def started(self, pid):
            return pid * 10 if pid in self.names else None
        def name(self, pid):
            if pid in self.unknown:
                raise OSError('unknown executable observation')
            return self.names[pid]
        def owned_children(self, pid, start):
            return [(child, child * 10) for child in self.edges.get(pid, [])]

    api = Table()
    tree = OwnedTree(api, 1, 10)
    tree.discover()  # All ordinary actors were independently observed before exec.
    api.names[3] = 'zenserver'
    api.names[5] = 'UnrealTraceServer'
    sent = []
    fixture.signal_readonly_owned(tree, signal.SIGTERM, send=lambda pid, number: sent.append((pid, number)))
    assert {pid for pid, _ in sent} == {1, 2}
    assert all(number == signal.SIGTERM for _, number in sent)
    sent.clear()
    fixture.signal_readonly_owned(tree, signal.SIGKILL, send=lambda pid, number: sent.append((pid, number)))
    assert {pid for pid, _ in sent} == {1, 2}
    assert all(number == signal.SIGKILL for _, number in sent)
    api.unknown.add(2)
    sent.clear()
    with pytest.raises(OSError, match='unknown executable'):
        fixture.signal_readonly_owned(tree, signal.SIGTERM, send=lambda pid, number: sent.append((pid, number)))
    assert not sent


def _entry_fixture():
    from atelier import paths
    spec = importlib.util.spec_from_file_location(
        'retained_entry_fixture', paths.REPO / 'games/yorimichi/tests/legacy_host_entry_case.py')
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    return fixture


def test_fixture_retains_only_exact_bounded_control_diagnostics_without_env_or_request_values(tmp_path):
    fixture = _entry_fixture()
    control = tmp_path / 'build/build-v2/legacy-host' / ('a' * 32)
    evidence = tmp_path / 'evidence'
    control.mkdir(parents=True, mode=0o700)
    evidence.mkdir(mode=0o700)
    def private(path, raw):
        path.write_bytes(raw)
        path.chmod(0o600)
    private(evidence / 'stdout.log', f'Managed legacy authority control: {control}\n'.encode())
    private(control / 'startup.json', json.dumps({
        'version': 2, 'nonce': 'a' * 32, 'host': {'pid': 7, 'boot': 'boot', 'started': '9'},
        'operational_environment': {'agent': 'DO_NOT_COPY_PRIVATE_VALUE'},
    }).encode())
    private(control / 'request.json', b'{"private":"DO_NOT_COPY_PRIVATE_VALUE"}')
    raw_log = b'legacy_phase v1 fixed retained diagnostic\n'
    private(control / 'scheduler.log', raw_log)
    result = fixture.retain_control_diagnostics(tmp_path, evidence)
    assert result == {'locator': 'bound', 'retained': ['startup.json', 'request.json', 'scheduler.log']}
    binding = (evidence / 'failed-control-binding.json').read_bytes()
    request = (evidence / 'failed-request-binding.json').read_bytes()
    assert b'DO_NOT_COPY_PRIVATE_VALUE' not in binding + request
    assert (evidence / 'failed-scheduler.log').read_bytes() == raw_log
    assert (evidence / 'failed-scheduler.log').stat().st_mode & 0o777 == 0o600
    assert 'cleanup' not in result and 'complete' not in result


@pytest.mark.parametrize('fault', ['missing-locator', 'multiple-locators', 'linked-log', 'oversized-log'])
def test_fixture_unknown_control_diagnostics_do_not_follow_links_search_or_invent_cleanup(tmp_path, fault):
    fixture = _entry_fixture()
    control = tmp_path / 'build/build-v2/legacy-host' / ('b' * 32)
    evidence = tmp_path / 'evidence'
    control.mkdir(parents=True, mode=0o700)
    evidence.mkdir(mode=0o700)
    line = f'Managed legacy authority control: {control}\n'
    (evidence / 'stdout.log').write_text('' if fault == 'missing-locator' else
                                       line * (2 if fault == 'multiple-locators' else 1))
    (evidence / 'stdout.log').chmod(0o600)
    outside = tmp_path / 'outside'
    outside.write_bytes(b'private-unrelated-original')
    outside.chmod(0o600)
    if fault == 'linked-log':
        (control / 'scheduler.log').symlink_to(outside)
    elif fault == 'oversized-log':
        (control / 'scheduler.log').write_bytes(b'x' * (256 * 1024 + 1))
        (control / 'scheduler.log').chmod(0o600)
    result = fixture.retain_control_diagnostics(tmp_path, evidence)
    assert result['retained'] == []
    assert result['locator'] == ('unknown' if 'locator' in fault else 'bound')
    assert not (evidence / 'failed-scheduler.log').exists()
    assert outside.read_bytes() == b'private-unrelated-original'
    assert 'cleanup' not in result and 'complete' not in result
