"""Admission and source ownership regressions for all Blender mesh producers."""
from pathlib import Path
import pytest
from atelier import build, mesh_export_contract as contract, paths


@pytest.mark.parametrize('code', [
    'bpy.ops.export_scene.fbx(filepath="mesh.fbx")',
    'operation = bpy.ops.export_scene.fbx',
    'operation = getattr(bpy.ops.export_scene, "fbx")',
    'scene = bpy.ops.export_scene; scene.fbx()',
    'from io_scene_fbx import export_fbx_bin',
    'from bpy.ops import export_scene as scene; scene.fbx()',
    'from bpy.ops.export_scene import fbx as export; export()',
    'scene = bpy.ops.export_scene; alias = scene; alias.fbx()',
])
def test_raw_operator_rejected_before_execution(tmp_path, code):
    source = tmp_path / 'export.py'; source.write_text(code)
    step = build.Step('mesh', [build.Blender(source)])
    assert contract.violations(source, code)
    with pytest.raises(ValueError, match='raw FBX export'):
        build.check_modules([step])


def test_strings_and_comments_are_not_export_operators(tmp_path):
    assert contract.violations(tmp_path / 'safe.py', '# bpy.ops.export_scene.fbx()\ns="export_scene.fbx"') == []
    assert contract.violations(tmp_path / 'reader.py', 'from io_scene_fbx import parse_fbx') == []
    assert contract.violations(tmp_path / 'reader.py', 'from io_scene_fbx.parse_fbx import parse') == []


def test_exporter_input_required_from_nested_import_and_fresh_closure(tmp_path):
    source = tmp_path / 'export.py'
    source.write_text('def run():\n    from atelier.blender.fbx import export_fbx\n    export_fbx(filepath="mesh.fbx")\n')
    step = build.Step('mesh', [build.Blender(source)])
    with pytest.raises(ValueError, match='declared input'):
        build.check_modules([step])
    step.inputs.append(paths.STUDIO / 'atelier' / 'blender' / 'fbx.py')
    build.check_modules([step])
    source.write_text(source.read_text() + '\nbpy.ops.export_scene.fbx()\n')
    with pytest.raises(ValueError, match='raw FBX export'):
        build.check_modules([step])


def test_current_game_recipe_declares_shared_exporter_for_every_producer():
    # The actual complete recipe catches new vehicle/character/world exporters too.
    game = next(p.name for p in paths.GAMES.iterdir() if (p / 'world/asset_mesh.py').is_file())
    steps = build.load_recipe(game).steps(build.Context(game, create=False))
    build.check_modules(steps)
