"""Path-key optimizations must preserve the legacy fingerprint's exact byte stream."""
from pathlib import Path

import pytest

from atelier import build


def legacy_hash(digest, path, skip=True):
    path = Path(path)
    if path.is_file():
        digest.update(str(path.name).encode())
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b''):
                digest.update(chunk)
    elif path.is_dir():
        for child in sorted(path.rglob('*')):
            if child.is_file() and not (skip and (build.SKIP_PARTS & set(child.parts)
                                                  or child.suffix in build.SKIP_SUFFIXES)):
                digest.update(str(child.relative_to(path)).encode())
                legacy_hash(digest, child, skip)
    else:
        digest.update(b'missing:' + str(path).encode())


@pytest.mark.parametrize('root', ['absolute', '.', 'nested/..', 'linked', 'Binaries'])
@pytest.mark.parametrize('skip', [False, True])
def test_legacy_directory_hash_preserves_the_complete_byte_stream(tmp_path, monkeypatch, root, skip):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'nested').mkdir()
    for name in ('a.bin', 'A source.py', 'café/deep.txt', 'README.md', '.hidden',
                 'Binaries/generated.bin', '__pycache__/cached.pyc'):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
    outside = tmp_path.parent / (tmp_path.name + '-external.bin')
    outside.write_bytes(b'linked source')
    (tmp_path / 'file-link').symlink_to(outside)
    (tmp_path / 'directory-link').symlink_to(tmp_path / 'café', target_is_directory=True)
    linked = tmp_path.parent / (tmp_path.name + '-root-link')
    linked.symlink_to(tmp_path, target_is_directory=True)
    path = tmp_path if root == 'absolute' else linked if root == 'linked' else Path(root)

    class Feed:
        def __init__(self):
            self.chunks = []

        def update(self, chunk):
            self.chunks.append(chunk)

    old, current = Feed(), Feed()
    legacy_hash(old, path, skip)
    build._hash_path(current, path, skip)
    assert current.chunks == old.chunks
