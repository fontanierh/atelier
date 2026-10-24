"""Closed original startup observations; real host execution is hosted separately."""
import pytest

from atelier.build_v2.legacy_entry import operational_environment, original_python_context


def test_managed_original_operational_context_is_closed_and_does_not_leak_environment():
    original = {'PATH': '/usr/bin:/bin', 'ATELIER_AGENT': 'writer', 'ATELIER_CACHE': '/cache',
                'ATELIER_BUILD_ROOT': '/build', 'UNRELATED_SECRET': 'must-not-cross'}
    assert operational_environment(original) == {
        'path': '/usr/bin:/bin', 'agent': 'writer', 'cache': '/cache', 'build_root': '/build'}
    assert operational_environment({'PATH': '/usr/bin'}) == {
        'path': '/usr/bin', 'agent': None, 'cache': None, 'build_root': None}
    for extra in ({'PYTHONPATH': '/project'}, {'DYLD_INSERT_LIBRARIES': '/library'},
                  {'PYTHONHASHSEED': '0'}, {'PYTHONINSPECT': '1'},
                  {'PYTHONUSERBASE': '/user-base'}, {'LD_AUDIT': '/loader.so'},
                  {'ATELIER_CAPACITY_CLIENT': 'legacy'}, {'ATELIER_BUILD_ROOT': 'relative'},
                  {'PATH': '/usr/bin:'}, {'PATH': 'relative:/bin'}):
        with pytest.raises(ValueError):
            operational_environment({**original, **extra})


def test_managed_context_uses_original_c2c_interpreter_scheme(monkeypatch):
    from atelier.build_v2 import python_worker
    from atelier.build_v2 import legacy_entry
    monkeypatch.setattr(python_worker, 'interpreter_roots', lambda: ['/original/root'])
    monkeypatch.setattr(legacy_entry.sysconfig, 'get_paths',
                        lambda: {'purelib': '/original/venv/pure', 'platlib': '/original/venv/plat'})
    assert original_python_context() == {'platform_roots': ['/original/root'],
                                         'purelib': '/original/venv/pure',
                                         'platlib': '/original/venv/plat'}


def test_captured_declaration_path_scope_is_write_free_and_default_unchanged(tmp_path, monkeypatch):
    from atelier import paths
    monkeypatch.setenv('ATELIER_BUILD_ROOT', str(tmp_path / 'build'))
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path / 'cache'))
    monkeypatch.setattr(paths, 'GAMES', tmp_path / 'games')
    (tmp_path / 'games/example').mkdir(parents=True)
    with paths.captured_declaration('example'):
        assert paths.build_dir('example') == tmp_path / 'build/example'
        assert not (tmp_path / 'build').exists()
        for forbidden in (lambda: paths.build_dir('other'), lambda: paths.cache_dir('metadata'),
                          lambda: paths.content_data('example')):
            with pytest.raises(ValueError):
                forbidden()
        assert set(tmp_path.iterdir()) == {tmp_path / 'games'}
        assert not (tmp_path / 'games/example/unreal').exists()
    assert paths.build_dir('example').is_dir()
    assert paths.cache_dir('metadata').is_dir()
    assert paths.content_data('example').is_dir()


def test_managed_selector_never_hides_global_declarations_or_persisted_management(tmp_path, monkeypatch):
    from atelier.build_v2 import legacy_entry
    monkeypatch.setattr(legacy_entry, '_checkout', lambda: tmp_path)
    monkeypatch.setattr(legacy_entry, 'controller_names', lambda game, checkout: ('data.stage.racing_courses',))
    assert legacy_entry.managed('example', [])
    assert legacy_entry.managed('example', ['data.stage'])
    assert legacy_entry.managed('example', ['legacy.only'])
    assert not legacy_entry.managed('example', ['data.stage.racing_courses'])
    assert not list(tmp_path.iterdir())
    monkeypatch.setattr(legacy_entry, 'controller_names', lambda game, checkout: ())
    assert not legacy_entry.managed('example', ['legacy.only'])
    (tmp_path / 'build/build-v2').mkdir(parents=True)
    assert not legacy_entry.managed('example', ['legacy.only'])
    metadata = tmp_path / 'build/build-v2/install'
    metadata.mkdir(parents=True)
    assert legacy_entry.managed('example', ['legacy.only'])


def test_normal_managed_entry_preflight_refuses_before_context_or_host_writes(monkeypatch):
    from atelier import build, build_snapshot
    from atelier.build_v2 import legacy_entry
    observed = []
    monkeypatch.setattr(legacy_entry, 'managed', lambda game, wanted: True)
    monkeypatch.setattr(build_snapshot, 'require_complete', lambda *args, **kwargs: observed.append('barrier'))
    def preflight(*args, **kwargs):
        observed.append('captured-preflight')
        raise ValueError('unsupported captured declaration')
    monkeypatch.setattr(legacy_entry, 'prepare_discovery', preflight)
    monkeypatch.setattr(legacy_entry, 'execute', lambda *args, **kwargs: pytest.fail('host started'))
    monkeypatch.setattr(build, 'Context', lambda *args, **kwargs: pytest.fail('Context constructed'))
    with pytest.raises(ValueError, match='unsupported captured declaration'):
        build.build('example', ['data.stage'])
    assert observed == ['captured-preflight']  # Barrier belongs to the fresh captured dependency scope.


def test_managed_classification_uses_captured_original_bytes_without_pycache_or_mkdir(tmp_path, monkeypatch):
    from atelier import paths
    from atelier.build_v2 import controller_entry, legacy_entry
    monkeypatch.setattr(controller_entry, 'discover', lambda *args, **kwargs: pytest.fail('live declaration loader ran'))
    original = paths.REPO
    for name in legacy_entry.CLASSIFICATION_FILES:
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((original / name).read_bytes())
    declaration = tmp_path / 'games/example/build_v2.py'
    declaration.parent.mkdir(parents=True)
    declaration.write_text('from atelier import paths\nOUT = paths.build_dir("example")\ndef targets(): return {}\n')
    assert legacy_entry.controller_names('example', tmp_path) == ()
    assert not (tmp_path / 'build').exists()
    assert not list(tmp_path.rglob('__pycache__'))
    declaration.write_text('def targets(): return []\n')
    with pytest.raises(ValueError, match='invalid game controller'):
        legacy_entry.controller_names('example', tmp_path)
    assert not (tmp_path / 'build').exists()
    assert not list(tmp_path.rglob('__pycache__'))


def test_unmanaged_normal_entry_reaches_original_context_without_host(monkeypatch):
    from atelier import build
    from atelier.build_v2 import controller_entry, legacy_entry
    monkeypatch.setattr(legacy_entry, 'managed', lambda game, wanted: False)
    monkeypatch.setattr(controller_entry, 'exact_selection', lambda *args: None)
    monkeypatch.setattr(legacy_entry, 'execute', lambda *args, **kwargs: pytest.fail('host started'))
    class OriginalContextBoundary(Exception):
        pass
    def context(*args, **kwargs):
        raise OriginalContextBoundary
    monkeypatch.setattr(build, 'Context', context)
    with pytest.raises(OriginalContextBoundary):
        build.build('sandbox', ['ordinary.existing'])
