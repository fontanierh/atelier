"""Runtime copies remain independent and do not import build controllers."""
from pathlib import Path

from atelier import file_copy, source_imports


def test_copy_keeps_bytes_permissions_and_independent_ownership(tmp_path):
    source = tmp_path / 'source'
    source.write_bytes(b'exact source bytes')
    source.chmod(0o600)
    destination = tmp_path / 'owned' / 'copy'
    file_copy.copy_file(source, destination)
    assert destination.read_bytes() == source.read_bytes()
    assert destination.stat().st_ino != source.stat().st_ino
    assert destination.stat().st_mode & 0o777 == 0o644
    source.write_bytes(b'changed source')
    assert destination.read_bytes() == b'exact source bytes'


def test_runtime_copy_has_no_build_or_cache_dependency():
    closure = source_imports.local_imports(Path(file_copy.__file__))
    assert {path.name for path in closure} == {'file_copy.py'}
