"""Finite provider capture; real fresh-process Graph proof lives in the Rust T1a case."""
from pathlib import Path
import importlib.util
import signal
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
