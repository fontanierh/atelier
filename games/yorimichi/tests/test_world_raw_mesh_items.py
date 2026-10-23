"""World meshes as raw items: map and finishing edits keep every raw key (the #566 regression)."""
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from atelier import paths, unreal_mesh_reuse as native

SCRIPTS = Path(__file__).resolve().parents[1] / 'unreal/Scripts'


def raw(tmp_path, monkeypatch, importer_text):
    monkeypatch.setattr(native, 'context', lambda ctx: {'engine': 'same'})
    monkeypatch.setattr(native, 'project_identity', lambda ctx: 'project')
    importer = tmp_path / 'mesh_import.py'; importer.write_text(importer_text)
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path / 'out', uproject=tmp_path / 'unreal/Yorimichi.uproject')
    return native.RawMeshes(ctx, 'unreal.world', importer, ('_import_mesh', 'legacy_options_match'))


def history(revision, name):
    result = subprocess.run(['git', 'show', f'{revision}:games/yorimichi/unreal/Scripts/{name}'],
                            cwd=paths.REPO, capture_output=True, text=True)
    if result.returncode:
        pytest.skip('history of #566 is not available in this clone')
    return result.stdout


def test_world_opts_into_raw_items_through_the_shared_importer():
    text = (SCRIPTS / 'mesh_import.py').read_text()
    assert "RAW_ITEM_TASKS = frozenset({'unreal.world'})" in text


def test_replaying_the_566_map_edit_keeps_all_148_raw_keys(tmp_path, monkeypatch):
    """#566 (ba4541e99) changed setup_project.build_level, a map-assembly function. The receipt
    policy hashed the whole owner AST, so all 148 unchanged world meshes were imported again.
    A raw item's key reads the importer's own functions and the mesh source, never the owner."""
    before, after = history('ba4541e99^', 'setup_project.py'), history('ba4541e99', 'setup_project.py')
    assert native.ast_dump(before) != native.ast_dump(after)  # The owner-AST policy changed.
    importer = (SCRIPTS / 'mesh_import.py').read_text()
    source = tmp_path / 'Mesh.fbx'; source.write_bytes(b'unchanged world mesh')
    keys = []
    for index, owner in enumerate((before, after)):
        folder = tmp_path / str(index); folder.mkdir()
        (folder / 'setup_project.py').write_text(owner)  # The owner each session ran with.
        items = raw(folder, monkeypatch, importer)
        keys.append([items.key(f'/Game/Japan/Assets/Mesh{i}', [source], {'format': 'fbx-static-mesh', 'fresh': True})
                     for i in range(148)])
    assert keys[0] == keys[1]


def test_an_importer_option_change_rekeys_every_raw_item(tmp_path, monkeypatch):
    importer = (SCRIPTS / 'mesh_import.py').read_text()
    assert 'build_nanite=False' in importer
    source = tmp_path / 'Mesh.fbx'; source.write_bytes(b'mesh')
    (tmp_path / 'a').mkdir(); (tmp_path / 'b').mkdir()
    first = raw(tmp_path / 'a', monkeypatch, importer).key('/Game/Japan/Assets/Mesh', [source], {})
    changed = raw(tmp_path / 'b', monkeypatch, importer.replace('build_nanite=False', 'build_nanite=True'))
    assert changed.key('/Game/Japan/Assets/Mesh', [source], {}) != first
