"""Managed scratch changes only explicit execution scope; original JSON bytes remain exact."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import atomic_files


def test_default_sibling_temporary_and_managed_scope_reset_preserve_bytes(tmp_path, monkeypatch):
    seen = []
    original = atomic_files.tempfile.NamedTemporaryFile
    def named(*args, **kwargs):
        seen.append(Path(kwargs['dir']))
        return original(*args, **kwargs)
    monkeypatch.setattr(atomic_files.tempfile, 'NamedTemporaryFile', named)
    target = tmp_path / 'products/result.json'; target.parent.mkdir()
    atomic_files.atomic_json(target, {'b':2,'a':1})
    expected = target.read_bytes(); assert seen[-1] == target.parent
    scratch = tmp_path / '.state/batches/owned/atomic-tmp'
    with atomic_files.managed_temporaries(scratch):
        atomic_files.atomic_json(target, {'b':2,'a':1})
        assert seen[-1] == scratch and target.read_bytes() == expected
        assert list(scratch.iterdir()) == []
    atomic_files.atomic_json(target, {'b':2,'a':1})
    assert seen[-1] == target.parent and target.read_bytes() == expected
    assert target.stat().st_mode & 0o777 == 0o600


def test_managed_scratch_refuses_cross_device_without_replace_or_tempfile(tmp_path, monkeypatch):
    target = tmp_path / 'output.json'; target.write_text('old')
    with atomic_files.managed_temporaries(tmp_path / '.state/scratch'):
        original = Path.lstat
        def observed(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            return (SimpleNamespace(st_dev=info.st_dev+1, st_ino=info.st_ino, st_mode=info.st_mode)
                    if path == target.parent else info)
        with monkeypatch.context() as patch:
            patch.setattr(Path, 'lstat', observed)
            patch.setattr(atomic_files.tempfile, 'NamedTemporaryFile', lambda *a, **k: pytest.fail('created cross-device temp'))
            with pytest.raises(ValueError, match='different filesystems'):
                atomic_files.atomic_json(target, {'new':True})
    assert target.read_text() == 'old'


def test_scope_exception_and_nested_scope_reset_leave_unknown_metadata_untouched(tmp_path):
    outer = tmp_path / '.state/outer'; inner = tmp_path / '.state/inner'
    with atomic_files.managed_temporaries(outer):
        partial = outer / '.write-retained'; partial.write_bytes(b'unknown prior partial')
        with pytest.raises(RuntimeError, match='original'):
            with atomic_files.managed_temporaries(inner):
                raise RuntimeError('original')
        assert atomic_files._MANAGED_TEMPORARY.get()[0] == outer
        assert partial.read_bytes() == b'unknown prior partial'
    assert atomic_files._MANAGED_TEMPORARY.get() is None
    assert partial.read_bytes() == b'unknown prior partial'


def test_managed_scratch_rejects_ancestor_alias_before_creation(tmp_path):
    actual = tmp_path / 'actual'; actual.mkdir()
    alias = tmp_path / 'alias'; alias.symlink_to(actual, target_is_directory=True)
    with pytest.raises(OSError):
        with atomic_files.managed_temporaries(alias / 'absent'):
            pytest.fail('entered linked scratch')
    assert not (actual / 'absent').exists()


def test_managed_scope_checks_complete_held_directory_identity(tmp_path, monkeypatch):
    target = tmp_path / 'output.json'
    with atomic_files.managed_temporaries(tmp_path / '.state/scratch'):
        descriptor = atomic_files._MANAGED_TEMPORARY.get()[1]
        original = atomic_files.os.fstat
        def changed(fd):
            stat = original(fd)
            return SimpleNamespace(st_dev=stat.st_dev+1, st_ino=stat.st_ino) if fd == descriptor else stat
        with monkeypatch.context() as patch:
            patch.setattr(atomic_files.os, 'fstat', changed)
            with pytest.raises(ValueError, match='temporary directory changed'):
                atomic_files.atomic_json(target, {'not':'published'})
    assert not target.exists()
    with pytest.raises(ValueError, match='absolute owned path'):
        with atomic_files.managed_temporaries(tmp_path / '.state/../outside'):
            pytest.fail('entered parent-traversing path')
