"""Native adapter ownership and refusal paths, without launching an editor."""
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from atelier import checkpoint_candidates, mesh_reuse, paths, unreal_mesh_reuse as native


@pytest.fixture
def scene(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'; repo.mkdir()
    monkeypatch.setattr(paths, 'REPO', repo)
    ctx = SimpleNamespace(out=repo / 'build/game', uproject=repo / 'games/game/unreal/Game.uproject',
                          unreal_root=repo / 'engine', game='game')
    ctx.out.mkdir(parents=True); ctx.uproject.parent.mkdir(parents=True)
    script = repo / 'import.py'; script.write_text('def build(): return 1\n')
    current = {'engine': 'engine', 'sdk': 'sdk'}
    monkeypatch.setattr(native, 'context', lambda _: current)
    from atelier import checkpoint_store
    monkeypatch.setattr(checkpoint_store, 'context', lambda _: current)
    monkeypatch.setenv('ATELIER_MESH_REUSE_NONCE', 'e' * 24)
    monkeypatch.setattr(mesh_reuse, 'revision_source', lambda *a: script.read_text())
    source = ctx.out / 'mesh.glb'; source.write_bytes(b'expected mesh source')
    hull = ctx.out / 'hull.glb'; hull.write_bytes(b'expected collision source')
    files, staged = {}, {}
    packages = ['/Game/Region/Mesh', '/Game/Region/Hull']
    for package in packages:
        for member in mesh_reuse.package_members(package)[:3]:
            file = repo / 'staging' / member; file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(('candidate:' + member).encode())
            staged[member] = file
            files[member] = dict(path='files/' + member, sha256=mesh_reuse.digest(file),
                                 size=file.stat().st_size, mode=0o644)
    report = repo / 'report.json'; report.write_text('{"meshes":[]}')
    staged['generated/report.json'] = report
    bundle = dict(checkpoint='a' * 64, donor_task='unreal.region', donor_fingerprint='b' * 64,
                  source_revision='c' * 40, provenance='compatibility-only', files=files)
    monkeypatch.setattr(checkpoint_candidates, 'load', lambda *a: bundle)
    def member(*args, bundle=None):
        return staged.get(args[2])
    monkeypatch.setattr(checkpoint_candidates, 'member_path', member)
    content = ctx.uproject.parent / 'Content'
    tags = {package: json.dumps([{'FileMD5': hashlib.md5(file.read_bytes()).hexdigest()}])
            for package, file in zip(packages, (source, hull))}
    scans = []
    def load(package):
        for required in packages:
            assert (content / mesh_reuse.package_members(required)[0].removeprefix('content/')).exists()
        return SimpleNamespace(package=package)
    unreal = SimpleNamespace(
        EditorAssetLibrary=SimpleNamespace(does_asset_exist=lambda p:
            (content / mesh_reuse.package_members(p)[0].removeprefix('content/')).exists()),
        AssetRegistryHelpers=SimpleNamespace(
            create_asset_data=lambda mesh: SimpleNamespace(get_tag_value=lambda _: tags[mesh.package]),
            get_asset_registry=lambda: SimpleNamespace(scan_files_synchronous=lambda names, force: scans.append(names))),
        load_asset=load)
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    def adapter():
        return native.MeshReuse(ctx, 'unreal.region', script, ('build',), report_member='generated/report.json')
    sources = [(packages[0], source, mesh_reuse.digest(source)), (packages[1], hull, mesh_reuse.digest(hull))]
    return SimpleNamespace(ctx=ctx, adapter=adapter, sources=sources, package=packages[0], tags=tags,
                           staged=staged, content=content, scans=scans, bundle=bundle)


def acquire(scene, adapter, **kwargs):
    return adapter.acquire('Mesh', scene.package, geometry={'source': 'same'},
                           donor_geometry=kwargs.pop('donor_geometry', {'source': 'same'}),
                           sources=scene.sources, **kwargs)


def test_admits_complete_collision_group_then_records_only_after_validation(scene):
    adapter = scene.adapter()
    mesh = acquire(scene, adapter)
    assert mesh and len(scene.scans[0]) == 2
    assert not adapter.receipts.path.exists()
    adapter.validated('Mesh')
    assert not adapter.receipts.path.exists()
    mesh_reuse.finalize_pending(scene.ctx, 'unreal.region', 'e' * 24)
    record = json.loads(adapter.receipts.path.read_text())['meshes']['Mesh']
    assert len(record['packages']) == 6
    assert record['provenance']['kind'] == 'compatibility-only'
    copied = scene.content / 'Region/Mesh.uasset'; copied.write_bytes(b'independent modification')
    assert scene.staged['content/Region/Mesh.uasset'].read_bytes() != copied.read_bytes()


def test_different_geometry_is_ordinary_import_without_content_copy(scene):
    adapter = scene.adapter()
    assert acquire(scene, adapter, donor_geometry={'source': 'changed'}) is None
    assert not scene.content.exists() and not adapter.receipts.path.exists()


def test_missing_native_import_hash_never_certifies_captured_bytes(scene):
    scene.tags[scene.package] = '[]'
    adapter = scene.adapter()
    assert acquire(scene, adapter) is None
    adapter.validated('Mesh')
    assert not adapter.receipts.path.exists()
    assert adapter.counts['reused_candidate'] == 0


def test_changed_source_or_corrupt_copy_cannot_publish_candidate_receipt(scene):
    adapter = scene.adapter()
    scene.sources[0][1].write_bytes(b'changed source')
    with pytest.raises(ValueError, match='generator report'):
        acquire(scene, adapter)
    assert not scene.content.exists()
    scene.sources[0][1].write_bytes(b'expected mesh source')
    scene.staged['content/Region/Mesh.uasset'].write_bytes(b'corrupt staged bytes')
    assert acquire(scene, adapter) is None
    assert not (scene.content / 'Region/Mesh.uasset').exists()


def test_warm_receipt_reuses_and_changed_package_refuses(scene):
    first = scene.adapter(); assert acquire(scene, first)
    first.validated('Mesh')
    mesh_reuse.finalize_pending(scene.ctx, 'unreal.region', 'e' * 24)
    second = scene.adapter(); assert acquire(scene, second)
    assert second.counts['reused_local'] == 1
    (scene.content / 'Region/Mesh.ubulk').write_bytes(b'changed saved geometry')
    third = scene.adapter()
    # An old whole-task stamp cannot override a failed, finer package receipt.
    third.local_compatible = True
    third.previous_fingerprint = 'd' * 64
    assert acquire(scene, third) is None


def test_fresh_import_after_candidate_refusal_records_current_provenance(scene):
    scene.tags[scene.package] = '[]'
    adapter = scene.adapter()
    assert acquire(scene, adapter) is None
    adapter.imported('Mesh')
    assert adapter.pending['Mesh']['provenance'] == {'kind': 'current-native-import'}


def test_receiving_observation_refuses_later_engine_sdk_change(tmp_path):
    ctx = SimpleNamespace(out=tmp_path / 'build', uproject=tmp_path / 'game/Game.uproject',
                          unreal_root=tmp_path / 'engine')
    for path in (ctx.unreal_root / 'Engine/Binaries/Mac/UnrealEditor.modules',
                 ctx.uproject.parent / 'Binaries/Mac/UnrealEditor.modules'):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text('{"BuildId":"same"}')
    assert native.observed_environment(ctx, {'engine': 'same', 'sdk': 'first'})
    assert not native.observed_environment(ctx, {'engine': 'same', 'sdk': 'changed'})


@pytest.mark.parametrize('suffix', ['.uasset', '.ubulk', '.upayload'])
def test_registry_invisible_disk_members_refuse_copy(scene, suffix):
    target = scene.content / ('Region/Mesh' + suffix)
    target.parent.mkdir(parents=True); target.write_bytes(b'unproved existing output')
    adapter = scene.adapter()
    assert acquire(scene, adapter) is None
    assert target.read_bytes() == b'unproved existing output'


def test_matching_property_does_not_dirty_asset():
    writes = []
    asset = SimpleNamespace(get_editor_property=lambda _: 1,
                            set_editor_property=lambda *args: writes.append(args))
    native.set_if_changed(asset, 'setting', 1)
    assert writes == []


def test_material_group_publishes_only_after_parent_and_preserves_unchanged_bytes(tmp_path, monkeypatch):
    from atelier import checkpoint_store
    repo = tmp_path.resolve(); monkeypatch.setattr(paths, 'REPO', repo)
    ctx = SimpleNamespace(out=repo / 'build/game', uproject=repo / 'games/game/unreal/Game.uproject')
    script = ctx.uproject.parent / 'Scripts/importer.py'; script.parent.mkdir(parents=True)
    script.write_text('def materials(): return 1\n')
    texture = ctx.out / 'paint.png'; texture.parent.mkdir(parents=True); texture.write_bytes(b'paint')
    content = ctx.uproject.parent / 'Content/Region/Material.uasset'
    content.parent.mkdir(parents=True); content.write_bytes(b'saved native material')
    monkeypatch.setattr(native, 'context', lambda _: {})
    monkeypatch.setattr(checkpoint_store, 'context', lambda _: {})
    monkeypatch.setenv('ATELIER_MESH_REUSE_NONCE', 'a' * 24)
    saves = []
    monkeypatch.setitem(sys.modules, 'unreal', SimpleNamespace(load_asset=lambda p: p,
        EditorAssetLibrary=SimpleNamespace(save_loaded_asset=lambda asset, **kw: saves.append(asset) or True)))
    group = native.AssetGroup(ctx, 'unreal.region', script, ('materials',), parameters={'colour': 1}, sources=[texture])
    packages = ['/Game/Region/Material']
    assert not group.matches(packages)
    group.validated(packages)
    assert not group.book.path.exists()  # a failed native child leaves no reuse receipt
    mesh_reuse.finalize_pending(ctx, 'unreal.region', 'a' * 24)
    again = native.AssetGroup(ctx, 'unreal.region', script, ('materials',), parameters={'colour': 1}, sources=[texture])
    assert again.matches(packages) and saves == packages
    texture.write_bytes(b'changed paint')
    assert not native.AssetGroup(ctx, 'unreal.region', script, ('materials',), parameters={'colour': 1}, sources=[texture]).matches(packages)
