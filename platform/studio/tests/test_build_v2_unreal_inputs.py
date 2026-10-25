"""Frozen Item staging needs no Unreal installation or native launch."""
import hashlib
import os
from pathlib import Path

import pytest

from atelier.build_v2 import recipe_job, unreal_inputs


def put(root, name, data=b'bytes'):
    path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    return path


def item(name, path, state='digest'):
    return {'name': name, 'path': path, 'identity': {'state': state}}


@pytest.fixture
def roots(tmp_path):
    job, content = tmp_path / 'job', tmp_path / 'Content'
    job.mkdir(); content.mkdir(); runtime = job / 'runtime'; runtime.mkdir()
    return job, content, runtime


def stage(roots, items, outputs=()):
    job, content, runtime = roots
    return unreal_inputs.stage_inputs(job, items, content, runtime_dir=runtime, output_packages=outputs)


def test_directory_item_copies_all_packages_sidecars_and_bound_reads(roots):
    job, content, _ = roots
    source = job / 'in/native'
    for name in ['Folder/A.uasset', 'Folder/A.m.ubulk', 'Folder/A.upayload', 'B.umap', 'B.uexp', 'B.ubulk', 'B.uptnl']:
        path = put(source, 'content/Game/' + name, name.encode()); path.chmod(0o444)
    before = recipe_job.inventory(source)
    result = stage(roots, [item('native', 'in/native')])
    assert result['packages'] == {'native': ['/Game/B', '/Game/Folder/A']}
    assert result['inputs']['native'] == str(source)
    assert len(result['staged_files']) == 7
    for target, digest in result['staged_files'].items():
        assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
        assert target.stat().st_mode & 0o222 == 0
        assert target.stat().st_ino != (source / 'content/Game' / target.relative_to(content)).stat().st_ino
        assert target in result['declared_reads']
    assert recipe_job.inventory(source) == before


def test_flat_inputs_keep_scalar_compatibility_and_sidecar_package_binding(roots):
    job, content, _ = roots
    put(job, 'in/content/Game/A.uasset'); put(job, 'in/content/Game/A.m.ubulk')
    result = stage(roots, [item('asset', 'in/content/Game/A.uasset'), item('bulk', 'in/content/Game/A.m.ubulk')])
    assert result['inputs'] == {'asset': '/Game/A', 'bulk': str(content / 'A.m.ubulk')}
    assert result['packages'] == {'asset': ['/Game/A'], 'bulk': ['/Game/A']}


def test_root_archive_uses_owned_runtime_and_keeps_staged_archive_unchanged(roots, tmp_path):
    job, content, runtime = roots
    source = tmp_path / 'producer'; put(source, 'content/Game/A.uasset')
    archive = job / 'in/native.tree.tar'; archive.parent.mkdir()
    recipe_job.pack_root(source, archive); original = archive.read_bytes(); archive.chmod(0o444)
    result = stage(roots, [item('native', 'in/native.tree.tar')])
    assert result['packages']['native'] == ['/Game/A']
    assert Path(result['inputs']['native']).is_relative_to(runtime)
    assert archive.read_bytes() == original and not list((job / 'in').glob('item-*'))
    assert (content / 'A.uasset').read_bytes() == b'bytes'


def test_raw_item_directory_is_preserved_and_selection_checks_complete_inventory(roots):
    job, _, _ = roots
    root = job / 'in/raw'; put(root, 'mesh.fbx'); put(root, 'export.json', b'{}')
    result = stage(roots, [item('raw', 'in/raw')])
    assert result['inputs']['raw'] == str(root) and result['packages']['raw'] == []
    rows = [{'path': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in root.iterdir()]
    assert unreal_inputs.select_member(root, rows, 'mesh.fbx') == root / 'mesh.fbx'
    put(root, 'extra.glb')
    with pytest.raises(ValueError, match='inventory differs'): unreal_inputs.select_member(root, rows, 'mesh.fbx')


@pytest.mark.parametrize('bad', ['sidecar', 'unknown', 'double-primary', 'case', 'link', 'fifo'])
def test_malformed_native_item_refuses_without_content_copies(roots, bad):
    job, content, _ = roots; root = job / 'in/native'
    put(root, 'content/Game/A.uasset')
    if bad == 'sidecar': put(root, 'content/Game/Missing.m.ubulk')
    elif bad == 'unknown': put(root, 'content/Game/A.txt')
    elif bad == 'double-primary': put(root, 'content/Game/A.umap')
    elif bad == 'case': put(root, 'content/Game/a.uexp')
    elif bad == 'link': (root / 'content/Game/link').symlink_to(root / 'content/Game/A.uasset')
    elif bad == 'fifo': os.mkfifo(root / 'content/Game/pipe')
    with pytest.raises((ValueError, OSError)): stage(roots, [item('native', 'in/native')])
    assert not list(content.iterdir())


def test_input_output_overlap_refuses_before_any_copy(roots):
    job, content, _ = roots
    put(job, 'in/item/content/Game/A.uasset'); put(job, 'in/item/content/Game/B.uasset')
    with pytest.raises(ValueError, match='both an input and an output'):
        stage(roots, [item('native', 'in/item')], ['/Game/B'])
    assert not list(content.iterdir())


def test_changed_or_missing_member_digest_and_undeclared_selection_refuse(roots):
    job, _, _ = roots; root = job / 'in/raw'; put(root, 'mesh.glb')
    rows = [{'path': 'mesh.glb', 'sha256': '0' * 64}]
    with pytest.raises(ValueError, match='inventory differs'): unreal_inputs.select_member(root, rows, 'mesh.glb')
    rows[0]['sha256'] = hashlib.sha256(b'bytes').hexdigest()
    with pytest.raises(ValueError, match='undeclared'): unreal_inputs.select_member(root, rows, 'other.glb')


def test_optional_absence_and_duplicate_slot_refuse(roots):
    result = stage(roots, [item('missing', 'in/none', 'absent')])
    assert result['inputs'] == {'missing': None} and result['packages'] == {'missing': []}
    with pytest.raises(ValueError, match='duplicate'): stage(roots, [item('x', 'in/none', 'absent')] * 2)


def test_owned_output_root_cannot_be_nested_in_a_staged_item(roots):
    job, _, runtime = roots; source = job / 'in/raw'; put(source, 'mesh.fbx')
    nested = source / 'Content'; nested.mkdir()
    with pytest.raises(ValueError, match='overlaps'):
        unreal_inputs.stage_inputs(job, [item('raw', 'in/raw')], nested, runtime_dir=runtime)
    assert not list(nested.iterdir())


def test_corrupt_root_archive_refuses_without_native_copies(roots, tmp_path):
    job, content, _ = roots; source = tmp_path / 'producer'; put(source, 'content/Game/A.uasset')
    archive = job / 'in/item.tree.tar'; archive.parent.mkdir(); recipe_job.pack_root(source, archive)
    raw = archive.read_bytes(); location = raw.find(b'bytes'); assert location >= 0
    archive.write_bytes(raw[:location] + b'wrong' + raw[location + 5:])
    with pytest.raises(ValueError, match='digest mismatch'): stage(roots, [item('native', 'in/item.tree.tar')])
    assert not list(content.iterdir())


def test_member_inventory_rejects_unexplained_empty_directories(roots):
    job, _, _ = roots; root = job / 'in/raw'; put(root, 'mesh.fbx')
    (root / 'extra').mkdir()
    with pytest.raises(ValueError, match='inventory differs'):
        unreal_inputs.select_member(root, [{'path':'mesh.fbx','sha256':hashlib.sha256(b'bytes').hexdigest()}], 'mesh.fbx')


@pytest.mark.parametrize('path', ['in/../foreign', '/absolute/input', 'in//double', 'in/./dot'])
def test_noncanonical_input_locator_refuses(roots, path):
    with pytest.raises(ValueError, match='noncanonical'):
        stage(roots, [item('raw', path, 'absent')])


def test_explicit_item_root_archive_preserves_raw_filename_extension(roots, tmp_path):
    job, content, runtime = roots
    png = put(tmp_path, 'producer/T_leaf_broad.png', b'png payload')
    root = job / 'in/texture'; archive = root / 'products/0-0.tree.tar'; archive.parent.mkdir(parents=True)
    recipe_job.pack_root(png, archive); put(root, 'products/other.tree.tar', b'not the selected archive')
    archive.chmod(0o444); before = recipe_job.inventory(root)
    binding = {'texture': {'archive_member': 'products/0-0.tree.tar', 'name': png.name}}
    result = unreal_inputs.stage_inputs(job, [item('texture', 'in/texture')], content,
                                       runtime_dir=runtime, root_bindings=binding)
    decoded = Path(result['inputs']['texture'])
    assert decoded == runtime / 'item-0/T_leaf_broad.png'
    assert decoded.suffix == '.png' and decoded.read_bytes() == b'png payload'
    assert archive in result['declared_reads'] and decoded in result['declared_reads']
    assert result['packages']['texture'] == [] and recipe_job.inventory(root) == before


def test_explicit_item_directory_root_is_named_and_stages_native_content(roots, tmp_path):
    job, content, runtime = roots; producer = tmp_path / 'producer'
    put(producer, 'content/Game/A.uasset')
    archive = job / 'in/native/products/0-0.tree.tar'; archive.parent.mkdir(parents=True)
    recipe_job.pack_root(producer, archive)
    result = unreal_inputs.stage_inputs(job, [item('native', 'in/native')], content, runtime_dir=runtime,
                                       root_bindings={'native': {'archive_member':'products/0-0.tree.tar','name':'NativeRoot'}})
    assert result['inputs']['native'] == str(runtime / 'item-0/NativeRoot')
    assert result['packages']['native'] == ['/Game/A']
    assert (content / 'A.uasset').read_bytes() == b'bytes'


@pytest.mark.parametrize('binding', [
    {'missing': {'archive_member':'products/0-0.tree.tar','name':'T.png'}},
    {'texture': {'archive_member':'products/missing.tree.tar','name':'T.png'}},
    {'texture': {'archive_member':'../foreign.tree.tar','name':'T.png'}},
    {'texture': {'archive_member':'products/0-0.tree.tar','name':'nested/T.png'}},
    {'texture': {'archive_member':'products/0-0.tree.tar','name':'T.png','guess':True}},
    {'texture': {'archive_member':'products/source.png','name':'T.png'}},
])
def test_unknown_or_malformed_explicit_archive_binding_refuses(roots, binding):
    job, content, runtime = roots
    put(job, 'in/texture/products/0-0.tree.tar', b'not decoded for a bad binding')
    with pytest.raises(ValueError):
        unreal_inputs.stage_inputs(job, [item('texture', 'in/texture')], content,
                                   runtime_dir=runtime, root_bindings=binding)
    assert not list(runtime.iterdir()) and not list(content.iterdir())


def test_unbound_item_archive_member_is_not_guessed(roots):
    job, _, runtime = roots; source = job / 'in/raw'
    put(source, 'products/0-0.tree.tar', b'not decoded without an explicit binding')
    result = stage(roots, [item('raw', 'in/raw')])
    assert result['inputs']['raw'] == str(source)
    assert not list(runtime.iterdir())
