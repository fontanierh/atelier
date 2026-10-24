"""Finite byte capture is distribution evidence, never a production SourcePlan issuer."""
import hashlib
import os

import pytest

from atelier.build_v2.controller_client import capture_named_sources, MAX_NAMED_ISSUER_FILES


def test_named_issuer_capture_reuses_distribution_framing_without_ambient_discovery(tmp_path):
    left, right = tmp_path / 'left', tmp_path / 'right'
    names = ('game/profile.py', 'game/helper.py')
    for root in (left, right):
        (root / 'game').mkdir(parents=True)
        (root / names[0]).write_bytes(b'PROFILE = 1\n')
        (root / names[1]).write_bytes(b'HELPER = 2\n')
    (right / 'unrelated.py').write_bytes(b'not captured')
    os.utime(right / names[0], ns=(1000000000, 1000000000))
    first = capture_named_sources(left, names)
    second = capture_named_sources(right, tuple(reversed(names)))
    expected = hashlib.sha256()
    for name, raw in sorted(first.files):
        encoded = name.encode()
        expected.update(len(encoded).to_bytes(8, 'big'))
        expected.update(encoded)
        expected.update(len(raw).to_bytes(8, 'big'))
        expected.update(raw)
    assert first.digest == second.digest == expected.hexdigest()
    assert first.files == second.files and len(first.files) == 2
    (right / names[1]).write_bytes(b'HELPER = 3\n')
    assert capture_named_sources(right, names).digest != first.digest


def test_named_issuer_capture_refuses_links_missing_ambiguous_or_unbounded_names(tmp_path):
    (tmp_path / 'real.py').write_bytes(b'VALUE = 1\n')
    (tmp_path / 'alias.py').symlink_to('real.py')
    for names in ((), ('real.py', 'real.py'), ('../real.py',), ('/real.py',), ('real.py',) * 513):
        with pytest.raises(ValueError):
            capture_named_sources(tmp_path, names)
    with pytest.raises(OSError):
        capture_named_sources(tmp_path, ('alias.py',))
    with pytest.raises(FileNotFoundError):
        capture_named_sources(tmp_path, ('absent.py',))
    with pytest.raises(ValueError):
        capture_named_sources(tmp_path, iter(('real.py',)))


def test_named_issuer_count_boundary_preserves_byte_duplicate_and_link_refusals(tmp_path, monkeypatch):
    from atelier.build_v2 import controller_client as client
    names = tuple(f'provider_{i}.py' for i in range(513))
    for name in names:
        (tmp_path / name).write_bytes(b'VALUE = 1\n')
    accepted = capture_named_sources(tmp_path, names[:512])
    assert len(accepted.files) == MAX_NAMED_ISSUER_FILES == 512
    with pytest.raises(ValueError, match='bounded'):
        capture_named_sources(tmp_path, names)
    with pytest.raises(ValueError, match='duplicate'):
        capture_named_sources(tmp_path, (*names[:511], names[0]))
    (tmp_path / names[0]).unlink()
    (tmp_path / names[0]).symlink_to(names[-1])
    with pytest.raises(OSError):
        capture_named_sources(tmp_path, names[:512])
    monkeypatch.setattr(client, 'MAX_SOURCE_FILE_BYTES', 8)
    with pytest.raises(ValueError):
        capture_named_sources(tmp_path, (names[1],))
    monkeypatch.setattr(client, 'MAX_SOURCE_FILE_BYTES', 16)
    monkeypatch.setattr(client, 'MAX_SOURCE_TOTAL_BYTES', 15)
    with pytest.raises(ValueError, match='size bound'):
        capture_named_sources(tmp_path, names[1:3])
