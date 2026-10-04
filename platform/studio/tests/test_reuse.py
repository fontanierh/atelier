"""Build reuse must never certify a failed source build or share mutable files between worktrees."""
import os

import pytest

from atelier import reuse


def test_copies_are_independent_and_absolute_local_symlinks_follow_target(tmp_path):
    source, target = tmp_path / 'source', tmp_path / 'target'
    source.mkdir()
    asset = source / 'mesh.uasset'
    asset.write_bytes(b'original mesh')
    (source / 'absolute-link').symlink_to(asset)
    reuse.copy_tree(source, target, source, target, None)
    (target / 'mesh.uasset').write_bytes(b'agent changed mesh')
    assert asset.read_bytes() == b'original mesh'
    assert asset.stat().st_ino != (target / 'mesh.uasset').stat().st_ino
    assert os.readlink(target / 'absolute-link') == str(target / 'mesh.uasset')


def test_different_revision_is_rejected_before_inspecting_or_copying(tmp_path, monkeypatch):
    source, target = tmp_path / 'source', tmp_path / 'target'
    source.mkdir(); target.mkdir()
    monkeypatch.setattr(reuse, 'git', lambda repo, *args: 'a' if repo == source else 'b')
    monkeypatch.setattr(reuse, 'inspect', lambda *args: pytest.fail('must not inspect incompatible source'))
    with pytest.raises(ValueError, match='same source revision'):
        reuse.main('sandbox', source, target)
    assert list(target.iterdir()) == []


def test_partial_target_build_is_rejected_without_overwriting_stamps(tmp_path, monkeypatch):
    source, target = tmp_path / 'source', tmp_path / 'target'
    source.mkdir()
    stamp = target / 'build/sandbox/stamps/unreal.compile.json'
    stamp.parent.mkdir(parents=True)
    stamp.write_text('existing state')
    monkeypatch.setattr(reuse, 'git', lambda repo, *args: 'revision' if args[0] == 'rev-parse' else '')
    monkeypatch.delenv('ATELIER_BUILD_ROOT', raising=False)
    with pytest.raises(ValueError, match='incremental build'):
        reuse.main('sandbox', source, target)
    assert stamp.read_text() == 'existing state'
