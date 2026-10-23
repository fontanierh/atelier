"""Raw mesh items: a fresh import is cached under its exact key and cloned into any checkout."""
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from atelier import mesh_reuse, raw_mesh_cache, unreal_mesh_reuse as native

PACKAGE = '/Game/Japan/Assets/House'
IMPORTER = '''def _import_mesh(path):
    return dict(combine_meshes=True, path=path)


def legacy_options_match(mesh):
    return mesh['combine_meshes'] is True
'''


@pytest.fixture
def machine(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path / 'cache'))
    monkeypatch.setattr(native, 'context', lambda ctx: {'engine': 'same'})
    monkeypatch.setattr(native, 'project_identity', lambda ctx: 'project')
    loaded, scans = set(), []
    registry = SimpleNamespace(scan_files_synchronous=lambda names, force: scans.append(('scan', names)),
                               scan_modified_asset_files=lambda names: scans.append(('modified', names)))
    unreal = SimpleNamespace(
        find_object=lambda outer, name: object() if name.split('.')[0] in loaded else None,
        EditorLoadingAndSavingUtils=SimpleNamespace(get_dirty_content_packages=lambda: [],
                                                    unload_packages=lambda values: loaded.clear()),
        AssetRegistryHelpers=SimpleNamespace(get_asset_registry=lambda: registry))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    importer = tmp_path / 'mesh_import.py'; importer.write_text(IMPORTER)

    def checkout(name, nonce):
        root = tmp_path / name
        ctx = SimpleNamespace(game='game', out=root / 'build/game', uproject=root / 'unreal/Game.uproject')
        ctx.uproject.parent.mkdir(parents=True); ctx.out.mkdir(parents=True)
        monkeypatch.setenv('ATELIER_MESH_REUSE_NONCE', nonce)
        return ctx, native.RawMeshes(ctx, 'unreal.world', importer, ('_import_mesh', 'legacy_options_match'))
    source = tmp_path / 'House.fbx'; source.write_bytes(b'fbx house')
    return SimpleNamespace(checkout=checkout, source=source, loaded=loaded, scans=scans, importer=importer)


def fresh_import(ctx, data=b'fresh package'):
    content = ctx.uproject.parent / 'Content/Japan/Assets'
    content.mkdir(parents=True, exist_ok=True)
    (content / 'House.uasset').write_bytes(data + b' header')
    (content / 'House.ubulk').write_bytes(data + b' bulk')


def produce(machine, name='a', nonce='a' * 24):
    ctx, raw = machine.checkout(name, nonce)
    key = raw.key(PACKAGE, [machine.source], {'format': 'fbx-static-mesh', 'fresh': True})
    assert not raw.install(PACKAGE, key) and raw.clear(PACKAGE)
    fresh_import(ctx)
    raw.capture(PACKAGE, key)
    mesh_reuse.finalize_pending(ctx, 'unreal.world', nonce)  # Only after the owning task succeeded.
    assert raw_mesh_cache.publish(ctx, 'unreal.world') == 1
    return ctx, key


def test_a_fresh_import_is_cached_and_cloned_into_another_checkout(machine):
    _, key = produce(machine)
    ctx, raw = machine.checkout('b', 'b' * 24)
    stale = ctx.uproject.parent / 'Content/Japan/Assets/House.uexp'
    stale.parent.mkdir(parents=True); stale.write_bytes(b'unproved leftover')
    assert raw.key(PACKAGE, [machine.source], {'format': 'fbx-static-mesh', 'fresh': True}) == key
    assert raw.install(PACKAGE, key)
    raw.admitted(PACKAGE)
    folder = ctx.uproject.parent / 'Content/Japan/Assets'
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == {
        'House.uasset': b'fresh package header', 'House.ubulk': b'fresh package bulk'}
    assert not list((ctx.out / '.state').glob('mesh-replace-*'))
    assert raw.counts['raw_installed'] == 1


def test_a_rejected_item_puts_the_previous_package_back(machine):
    _, key = produce(machine)
    ctx, raw = machine.checkout('b', 'b' * 24)
    previous = ctx.uproject.parent / 'Content/Japan/Assets/House.uasset'
    previous.parent.mkdir(parents=True); previous.write_bytes(b'previous finished package')
    assert raw.install(PACKAGE, key)
    assert raw.reject(PACKAGE)
    assert [p.read_bytes() for p in previous.parent.iterdir()] == [b'previous finished package']


def test_a_loaded_package_is_never_replaced(machine):
    _, key = produce(machine)
    ctx, raw = machine.checkout('b', 'b' * 24)
    previous = ctx.uproject.parent / 'Content/Japan/Assets/House.uasset'
    previous.parent.mkdir(parents=True); previous.write_bytes(b'loaded package')
    machine.loaded.add(PACKAGE)
    assert not raw.install(PACKAGE, key) and not raw.clear(PACKAGE)
    assert previous.read_bytes() == b'loaded package'


def test_a_failed_invocation_never_publishes_its_capture(machine):
    ctx, raw = machine.checkout('a', 'a' * 24)
    key = raw.key(PACKAGE, [machine.source], {})
    assert raw.clear(PACKAGE)
    fresh_import(ctx)
    raw.capture(PACKAGE, key)
    assert raw_mesh_cache.publish(ctx, 'unreal.world') == 0  # Never finalized.
    ctx2, raw2 = machine.checkout('b', 'b' * 24)
    assert not raw2.install(PACKAGE, key)


def test_the_key_binds_source_package_and_importer_but_not_owner_or_map_code(machine, tmp_path):
    ctx, raw = machine.checkout('a', 'a' * 24)
    key = raw.key(PACKAGE, [machine.source], {'fresh': True})
    assert raw.key('/Game/Japan/Assets/Other', [machine.source], {'fresh': True}) != key
    machine.source.write_bytes(b'fbx house, one vertex moved')
    assert raw.key(PACKAGE, [machine.source], {'fresh': True}) != key
    machine.source.write_bytes(b'fbx house')
    # The importer's own options are part of the key.
    machine.importer.write_text(machine.importer.read_text().replace('combine_meshes=True', 'combine_meshes=False'))
    _, changed = machine.checkout('c', 'c' * 24)
    assert changed.key(PACKAGE, [machine.source], {'fresh': True}) != key
