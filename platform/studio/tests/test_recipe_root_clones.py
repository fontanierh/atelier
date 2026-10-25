"""Common ROOT clones on a real APFS volume: independence, exact authority and refusals."""
import io
import json
import os
from pathlib import Path
import sys
import tarfile

import pytest

from atelier.build_v2 import recipe_job
from atelier.build_v2 import recipe_root_clones as clones

pytestmark = pytest.mark.skipif(sys.platform != 'darwin', reason='independent clones need APFS clonefile')


def archive(tmp_path, name, files):
    source = tmp_path / ('src-' + name)
    for relative, (content, mode) in files.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(mode)
    destination = tmp_path / (name + '.tree.tar')
    recipe_job.pack_root(source, destination)
    return destination


FILES = {'Binaries/UnrealEditor-Game.dylib': (b'\x7fELF' * 4096, 0o755), 'Config/Game.ini': (b'[Game]\n', 0o644),
         'Empty/.keep': (b'', 0o644)}


def unpacked(tmp_path, source, name):
    root = tmp_path / 'views' / name / 'root'
    recipe_job.unpack_root(source, root)
    return root


def inode(root, name):
    return (root / name).stat().st_ino


def test_later_exact_roots_become_independent_clones_of_one_private_snapshot(tmp_path):
    source = archive(tmp_path, 'editor', FILES)
    calls = []
    real = clones._clonefile()
    group = clones.CommonRootClones(tmp_path / 'scope', clone=lambda a, b: (calls.append(b), real(a, b)))
    first, second, third = (unpacked(tmp_path, source, n) for n in ('a', 'b', 'c'))
    before = recipe_job.inventory(first)
    assert group.share(source, first)['snapshot'] == 'created'
    unpacked_inodes = {name: inode(second, name) for name in FILES}
    stats = group.share(source, second)
    assert all(inode(second, name) != unpacked_inodes[name] for name in FILES)  # each file was replaced
    assert stats['snapshot'] == 'reused' and stats['files'] == 3 and stats['bytes'] == 16384 + 7
    assert group.share(source, third)['snapshot'] == 'reused'
    assert len(calls) == 9 and recipe_job.inventory(second) == recipe_job.inventory(third) == before
    assert (second / 'Binaries/UnrealEditor-Game.dylib').stat().st_mode & 0o777 == 0o755
    assert (second / 'Config/Game.ini').stat().st_mode & 0o777 == 0o644
    snapshot = tmp_path / 'scope' / stats['archive'] / 'root'
    assert len({inode(r, 'Config/Game.ini') for r in (first, second, third, snapshot)}) == 4
    (second / 'Config/Game.ini').write_bytes(b'mutated')  # an independent clone: nobody else changes
    assert recipe_job.inventory(first) == recipe_job.inventory(third) == recipe_job.inventory(snapshot) == before
    (first / 'Config/Game.ini').write_bytes(b'also mutated')
    assert recipe_job.inventory(third) == before
    group.discard()
    assert not (tmp_path / 'scope').exists() and recipe_job.inventory(third) == before


def test_another_archive_gets_its_own_snapshot_and_never_matches_another_root(tmp_path):
    a = archive(tmp_path, 'a', FILES)
    b = archive(tmp_path, 'b', {**FILES, 'Config/Game.ini': (b'[Other]\n', 0o644)})
    group = clones.CommonRootClones(tmp_path / 'scope')
    root_a, root_b = unpacked(tmp_path, a, 'a'), unpacked(tmp_path, b, 'b')
    first, second = group.share(a, root_a), group.share(b, root_b)
    assert first['snapshot'] == second['snapshot'] == 'created' and first['archive'] != second['archive']
    other = unpacked(tmp_path, a, 'other')
    with pytest.raises(ValueError, match='differs from its archive manifest'):
        group.share(b, other)
    a.write_bytes(b.read_bytes())  # the same path, other bytes: the digest is the authority
    with pytest.raises(ValueError, match='differs from its archive manifest'):
        group.share(a, other)


@pytest.mark.parametrize('damage', ['bytes', 'mode', 'extra', 'missing'])
def test_a_changed_current_root_is_refused_untouched(tmp_path, damage):
    source = archive(tmp_path, 'editor', FILES)
    group = clones.CommonRootClones(tmp_path / 'scope')
    group.share(source, unpacked(tmp_path, source, 'first'))
    root = unpacked(tmp_path, source, 'second')
    target = root / 'Config/Game.ini'
    {'bytes': lambda: target.write_bytes(b'[Changed]\n'), 'mode': lambda: target.chmod(0o755),
     'extra': lambda: (root / 'Config/New.ini').write_bytes(b''), 'missing': target.unlink}[damage]()
    before = {p: p.lstat().st_ino for p in root.rglob('*')}
    with pytest.raises(ValueError):
        group.share(source, root)
    assert {p: p.lstat().st_ino for p in root.rglob('*')} == before


def test_malformed_archives_and_unsupported_modes_refuse(tmp_path):
    plain = tmp_path / 'plain.tree.tar'
    with tarfile.open(plain, 'w') as tar:
        tar.add(tmp_path, arcname='root', recursive=False)
    group = clones.CommonRootClones(tmp_path / 'scope')
    root = tmp_path / 'root'
    root.mkdir()
    with pytest.raises(ValueError, match='manifest'):
        group.share(plain, root)
    odd = tmp_path / 'odd.tree.tar'
    manifest = json.dumps({'version': 1, 'kind': 'directory', 'entries': [['', 'directory', 0, 0o755, None],
                           ['x', 'file', 0, 0o600, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855']]}).encode()
    with tarfile.open(odd, 'w', format=tarfile.USTAR_FORMAT) as tar:
        info = tarfile.TarInfo(recipe_job.MANIFEST)
        info.size = len(manifest)
        tar.addfile(info, io.BytesIO(manifest))
    with pytest.raises(ValueError, match='unsupported kind or mode'):
        group.share(odd, root)


def test_aliased_roots_and_adopted_scopes_refuse(tmp_path):
    source = archive(tmp_path, 'editor', FILES)
    group = clones.CommonRootClones(tmp_path / 'scope')
    root = unpacked(tmp_path, source, 'a')
    link = tmp_path / 'link'
    link.symlink_to(root)
    with pytest.raises(ValueError, match='canonical'):
        group.share(source, link)
    with pytest.raises(ValueError, match='aliases'):
        group.share(source, tmp_path / 'scope')
    inside = root / 'Config/inner.tree.tar'
    with pytest.raises(ValueError, match='aliases'):
        group.share(Path(os.fspath(source)).rename(inside) or inside, root)
    with pytest.raises(FileExistsError):
        clones.CommonRootClones(tmp_path / 'scope')  # never adopt an existing scope


def test_a_tampered_snapshot_or_failed_clone_refuses_without_a_copy_fallback(tmp_path):
    source = archive(tmp_path, 'editor', FILES)
    fail = [False]
    real = clones._clonefile()
    def clone(a, b):
        if fail[0]:
            raise OSError(45, 'Operation not supported')
        real(a, b)
    group = clones.CommonRootClones(tmp_path / 'scope', clone=clone)
    stats = group.share(source, unpacked(tmp_path, source, 'a'))
    root = unpacked(tmp_path, source, 'b')
    fail[0] = True
    with pytest.raises(OSError):
        group.share(source, root)
    assert recipe_job.inventory(root) == recipe_job.inventory(unpacked(tmp_path, source, 'c'))
    assert not list(root.rglob('.atelier-clone-*'))
    fail[0] = False
    snapshot = tmp_path / 'scope' / stats['archive'] / 'root' / 'Config/Game.ini'
    snapshot.chmod(0o644)
    snapshot.write_bytes(b'[Game]\n')  # same bytes, but no longer the recorded immutable file
    with pytest.raises(ValueError, match='snapshot changed'):
        group.share(source, root)


def foreign_tree(path):
    path.mkdir(parents=True)
    (path / 'precious.txt').write_bytes(b'foreign')
    (path / 'precious.txt').chmod(0o400)
    return {p: (p.read_bytes() if p.is_file() else None, p.stat().st_mode) for p in [path, *path.rglob('*')]}


def unchanged(tree):
    return all(p.exists() and (p.read_bytes() if p.is_file() else None, p.stat().st_mode) == value
               for p, value in tree.items())


def test_a_replaced_scope_is_never_shared_into_or_removed(tmp_path):
    source = archive(tmp_path, 'editor', FILES)
    group = clones.CommonRootClones(tmp_path / 'scope')
    group.share(source, unpacked(tmp_path, source, 'a'))
    (tmp_path / 'scope').rename(tmp_path / 'moved-scope')
    tree = foreign_tree(tmp_path / 'scope')  # someone else's directory now holds the scope path
    with pytest.raises(ValueError, match='replaced or aliased'):
        group.share(source, unpacked(tmp_path, source, 'b'))
    with pytest.raises(ValueError, match='replaced or aliased'):
        group.discard()
    assert unchanged(tree)


def test_a_scope_reached_through_a_replaced_ancestor_link_is_never_removed(tmp_path):
    (tmp_path / 'parent').mkdir()
    group = clones.CommonRootClones(tmp_path / 'parent' / 'scope')
    (tmp_path / 'parent').rename(tmp_path / 'moved-parent')
    tree = foreign_tree(tmp_path / 'elsewhere' / 'scope')
    (tmp_path / 'parent').symlink_to(tmp_path / 'elsewhere')  # the ancestor now aliases foreign storage
    with pytest.raises(ValueError, match='replaced or aliased'):
        group.discard()
    assert unchanged(tree) and (tmp_path / 'moved-parent' / 'scope').is_dir()


def test_an_archive_behind_a_linked_parent_or_with_another_link_refuses(tmp_path):
    source = archive(tmp_path, 'editor', FILES)
    group = clones.CommonRootClones(tmp_path / 'scope')
    root = unpacked(tmp_path, source, 'a')
    (tmp_path / 'staged').symlink_to(tmp_path)
    with pytest.raises(ValueError, match='canonical unlinked path'):
        group.share(tmp_path / 'staged' / source.name, root)
    os.link(source, tmp_path / 'second-name.tree.tar')
    with pytest.raises(ValueError, match='single-link'):
        group.share(source, root)
    with pytest.raises(ValueError, match='canonical unlinked path'):
        clones.archive_authority(Path(source.name))  # relative
