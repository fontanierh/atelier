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


def test_differing_sources_names_each_step():
    def snapshot(**steps):
        return {'steps': [{'name': n, 'source': v} for n, v in steps.items()]}
    assert reuse.differing_sources(snapshot(a='1', b='2'), snapshot(a='1', b='2')) == []
    assert reuse.differing_sources(snapshot(a='1', b='2'), snapshot(a='1', b='3', c='4')) == ['b', 'c']


def test_inspect_reports_a_source_fingerprint_for_every_step():
    from atelier import paths
    snapshot = reuse.inspect(paths.REPO, 'sandbox')
    assert snapshot['steps'] and all(len(s['source']) == 64 for s in snapshot['steps'])


def test_target_files_in_copied_folders_are_found_tracked_ones_are_not(tmp_path):
    import subprocess
    def git(*args):
        subprocess.run(['git', '-C', str(tmp_path), *args], check=True, capture_output=True)
    git('init', '-q')
    (tmp_path / '.gitignore').write_text('Content/*\n!Content/kept.txt\nbuild/\n')
    (tmp_path / 'Content').mkdir()
    (tmp_path / 'Content/kept.txt').write_text('tracked')
    git('add', '.')
    git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'init')
    assert reuse.occupied(tmp_path, ['Content', 'build/game/data', 'Binaries']) == []
    (tmp_path / 'Content/Mesh.uasset').write_text('agent mesh')
    (tmp_path / 'build/game/data').mkdir(parents=True)
    (tmp_path / 'build/game/data/identity.json').write_text('{}')
    (tmp_path / 'Binaries').mkdir()
    (tmp_path / 'Binaries/new.dylib').write_text('')
    (tmp_path / 'build/game/logs').mkdir()
    (tmp_path / 'build/game/logs/step.log').write_text('not copied')
    assert sorted(reuse.occupied(tmp_path, ['Content', 'build/game/data', 'Binaries'])) == [
        'Binaries/new.dylib', 'Content/Mesh.uasset', 'build/game/data/identity.json']
