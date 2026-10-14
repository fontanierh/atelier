import os

import pytest

from atelier import build_hashes
from atelier.build_hashes import HashIndex


def test_persistent_index_avoids_reading_unchanged_bytes(tmp_path, monkeypatch):
    source = tmp_path / 'mesh'; source.write_bytes(b'mesh')
    database = tmp_path / 'hashes.sqlite3'
    with HashIndex(database) as index:
        expected = index.digest(source)
    def no_read(path):
        pytest.fail('unchanged bytes were read again')
    monkeypatch.setattr(build_hashes, 'digest_file', no_read)
    with HashIndex(database) as index:
        assert index.digest(source) == expected


def test_same_size_edit_with_restored_mtime_is_rehashed(tmp_path):
    source = tmp_path / 'mesh'; source.write_bytes(b'first')
    with HashIndex(tmp_path / 'hashes.sqlite3') as index:
        before = index.digest(source)
        times = source.stat()
        source.write_bytes(b'other')
        os.utime(source, ns=(times.st_atime_ns, times.st_mtime_ns))
        assert index.digest(source) != before
        replacement = tmp_path / 'replacement'; replacement.write_bytes(b'fresh')
        os.utime(replacement, ns=(times.st_atime_ns, times.st_mtime_ns))
        replacement.replace(source)
        assert index.digest(source) == build_hashes.digest_file(source)


def test_verification_bypasses_even_a_matching_index_entry(tmp_path):
    source = tmp_path / 'mesh'; source.write_bytes(b'mesh')
    with HashIndex() as index:
        expected = index.digest(source)
        key = str(source.resolve())
        index.memory[key] = (index.memory[key][0], 'a' * 64)
        assert index.digest(source, verify=True) == expected


def test_missing_or_corrupt_index_is_disposable_and_plan_is_read_only(tmp_path):
    source = tmp_path / 'mesh'; source.write_bytes(b'mesh')
    path = tmp_path / 'new/state/hashes.sqlite3'
    with HashIndex(path, read_only=True) as index:
        assert index.digest(source) == build_hashes.digest_file(source)
    assert not path.parent.exists()
    path.parent.mkdir(parents=True); path.write_bytes(b'corrupted database')
    with HashIndex(path) as index:
        assert index.digest(source) == build_hashes.digest_file(source)


def test_change_during_hashing_is_rejected(tmp_path, monkeypatch):
    source = tmp_path / 'mesh'; source.write_bytes(b'first')
    real = build_hashes.digest_file
    def mutate(path):
        result = real(path)
        path.write_bytes(b'changed')
        return result
    monkeypatch.setattr(build_hashes, 'digest_file', mutate)
    with HashIndex() as index, pytest.raises(ValueError, match='changed while hashing'):
        index.digest(source)
