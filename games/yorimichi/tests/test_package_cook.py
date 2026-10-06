"""A failed assembly cannot consume a certified cook or replace an existing download."""
import io
import json
from types import SimpleNamespace

import pytest

from atelier import build
from test_package import archive_tool


def cooked_app(tmp_path):
    root = tmp_path / 'package'
    app = root / 'archive/Mac/Yorimichi.app'
    files = {'Contents/MacOS/Yorimichi': b'game', 'Contents/UE/Yorimichi/Content/Data/world.json': b'{}',
             'Contents/UE/Yorimichi/Content/Data/heightmap.bin': b'height',
             'Contents/UE/Yorimichi/Content/Data/map/map.json': b'{}'}
    for name, data in files.items():
        target = app / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (app / 'Contents/MacOS/Yorimichi').chmod(0o755)
    (app / 'Contents/Current').symlink_to('MacOS')
    return root, app


def certify(tmp_path, monkeypatch):
    tool = build.load_recipe('yorimichi').package_cook
    root, app = cooked_app(tmp_path)
    snapshot = dict(revision='a1b2c3d4' * 5, source_dirty=False, fingerprint='inputs-v1', engine={'BuildId': 'test'})
    monkeypatch.setattr(tool, 'source_snapshot', lambda ctx: snapshot.copy())
    ctx = SimpleNamespace(out=tmp_path, cook_source=snapshot)
    tool.finish(ctx, io.StringIO())
    return tool, root, app, ctx


def test_incomplete_or_changed_app_invalidates_the_cook(tmp_path, monkeypatch):
    tool, root, app, _ = certify(tmp_path, monkeypatch)
    assert tool.cook_present(root)
    executable = app / 'Contents/MacOS/Yorimichi'
    executable.write_bytes(b'changed')
    assert not tool.cook_present(root)
    executable.unlink()
    assert not tool.cook_present(root)


def test_source_change_while_hashing_does_not_certify(tmp_path, monkeypatch):
    tool, root, app, ctx = certify(tmp_path, monkeypatch)
    (root / 'cook.json').unlink()
    original = tool.inventory

    def inventory(*args, **kwargs):
        value = original(*args, **kwargs)
        monkeypatch.setattr(tool, 'source_snapshot', lambda ctx: {'revision': 'changed'})
        return value
    monkeypatch.setattr(tool, 'inventory', inventory)
    with pytest.raises(RuntimeError, match='inputs changed'):
        tool.finish(ctx, io.StringIO())
    assert not (root / 'cook.json').exists()


def test_prepare_invalidates_a_previous_success_before_starting_uat(tmp_path, monkeypatch):
    tool, root, _, ctx = certify(tmp_path, monkeypatch)
    (root / 'manifest.json').write_text('previous release')
    tool.prepare(ctx, io.StringIO())
    assert not (root / 'cook.json').exists() and not (root / 'archive').exists()
    assert (root / 'manifest.json').read_text() == 'previous release'


def test_assembly_preserves_cook_identity_and_retries_without_consuming_it(tmp_path, monkeypatch):
    tool, root, app, _ = certify(tmp_path, monkeypatch)
    archive = archive_tool()
    monkeypatch.setattr(archive, 'audio_compatibility', lambda app, log: None)
    original = tool.inventory(app, hashes=True)
    receipt = (root / 'cook.json').read_bytes()
    archive.package_zip(root, io.StringIO(), cook_receipt=True)
    manifest = json.loads((root / 'manifest.json').read_text())
    assert manifest['revision'] == 'a1b2c3d4' and manifest['cook']['revision'] == 'a1b2c3d4' * 5
    assert tool.inventory(app, hashes=True) == original and (root / 'cook.json').read_bytes() == receipt
    previous = {name: (root / name).read_bytes() for name in ('manifest.json', 'SHA256SUMS', manifest['zip'])}
    bounded = archive.bounded

    def fail_zip(argv, log, label, watch):
        if label == 'zip':
            raise RuntimeError('synthetic zip failure')
        return bounded(argv, log, label, watch)
    monkeypatch.setattr(archive, 'bounded', fail_zip)
    with pytest.raises(RuntimeError, match='synthetic zip failure'):
        archive.package_zip(root, io.StringIO(), cook_receipt=True)
    assert all((root / name).read_bytes() == data for name, data in previous.items())
    assert tool.cook_present(root) and tool.inventory(app, hashes=True) == original
    assert not list(root.glob('.assemble-*'))
    monkeypatch.setattr(archive, 'bounded', bounded)
    archive.package_zip(root, io.StringIO(), cook_receipt=True)
    assert tool.cook_present(root)


def test_download_copy_must_match_the_certified_hashes(tmp_path, monkeypatch):
    tool, root, _, _ = certify(tmp_path, monkeypatch)
    receipt = json.loads((root / 'cook.json').read_text())
    receipt['files']['Contents/MacOS/Yorimichi']['sha256'] = '0' * 64
    (root / 'cook.json').write_text(json.dumps(receipt))
    assert tool.cook_present(root), 'quick check uses metadata; assembly must additionally verify hashes'
    archive = archive_tool()
    monkeypatch.setattr(archive, 'audio_compatibility', lambda app, log: None)
    with pytest.raises(RuntimeError, match='differs from the certified cook'):
        archive.package_zip(root, io.StringIO(), cook_receipt=True)
    assert not (root / 'manifest.json').exists()


def test_pipeline_refuses_an_uncertified_app(tmp_path):
    root, _ = cooked_app(tmp_path)
    with pytest.raises(FileNotFoundError):
        archive_tool().package_zip(root, io.StringIO(), cook_receipt=True)
    assert not (root / 'manifest.json').exists()
