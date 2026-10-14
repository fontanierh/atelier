"""The actual game recipe must keep local foliage edits away from world and region imports."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_products
from test_mega_ramp_layers import changed_by


GAME = Path(__file__).resolve().parents[1]
WORLD = GAME / 'world'
SCRIPTS = GAME / 'unreal/Scripts'
PACKAGING = {'data.content', 'data.network', 'unreal.cook', 'unreal.package'}


def test_one_tree_spec_changes_only_its_export_import_and_final_assembly(tmp_path, monkeypatch):
    assert changed_by(GAME / 'assets/foliage/Tree_Broad_A.json', tmp_path, monkeypatch) == {
        'world.foliage.Tree_Broad_A', 'unreal.foliage.Tree_Broad_A', *PACKAGING}


def test_foliage_lod_policy_does_not_reimport_world_regions_or_sounds(tmp_path, monkeypatch):
    changed = changed_by(WORLD / 'build_foliage_lods.py', tmp_path, monkeypatch)
    assert len([name for name in changed if name.startswith('world.foliage.')]) == 18
    assert len([name for name in changed if name.startswith('unreal.foliage.')]) == 18
    assert changed - PACKAGING == {name for name in changed if '.foliage.' in name}


def test_shader_graph_changes_leave_foliage_imports_current_when_interface_is_identical(tmp_path, monkeypatch):
    changed = changed_by(SCRIPTS / 'shared_materials.py', tmp_path, monkeypatch,
                         stable_products={'materials.foliage_interface'})
    assert 'unreal.materials' in changed
    assert not any('.foliage.' in name for name in changed)
    assert 'unreal.world' not in changed


def test_identical_geometry_cuts_off_a_native_import_after_an_export_source_edit(tmp_path, monkeypatch):
    changed = changed_by(GAME / 'assets/foliage/Tree_Broad_A.json', tmp_path, monkeypatch,
                         stable_products={'foliage.Tree_Broad_A.source'})
    assert changed == {'world.foliage.Tree_Broad_A'}


def test_props_generator_is_not_a_foliage_input(tmp_path, monkeypatch):
    changed = changed_by(WORLD / 'build_assets.py', tmp_path, monkeypatch)
    assert 'world.props' in changed and 'unreal.world' in changed
    assert not any('.foliage.' in name for name in changed)


def test_alpha_texture_is_an_input_only_of_foliage_that_reads_it(tmp_path, monkeypatch):
    texture = tmp_path / 'textures/T_leaf_ginkgo.png'
    texture.parent.mkdir()
    texture.write_bytes(b'fixture for existence, never decoded')
    changed = changed_by(texture, tmp_path, monkeypatch, stable_products={'materials.foliage_interface'})
    assert {name for name in changed if '.foliage.' in name} == {
        'world.foliage.Tree_Ginkgo', 'unreal.foliage.Tree_Ginkgo'}
    assert 'unreal.materials' in changed


def test_world_selector_includes_native_references_without_reading_their_bytes(tmp_path):
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, uproject=None)
    graph = build_products.Graph(build.load_recipe('yorimichi').steps(ctx))
    world = graph.by_name['unreal.world']
    assert not any(name.startswith('foliage.') for name in world.reads)
    names = {step.name for step in graph.select(['unreal.world'])}
    assert len([name for name in names if name.startswith('unreal.foliage.')]) == 18
    assert 'unreal.materials' in names
    assert len(graph.owners) == 38
    adapter = build.paths.STUDIO / 'atelier/blender/fbx.py'
    assert all(adapter in step.inputs for step in graph.by_name.values() if step.name.startswith('world.foliage.'))


def test_catalog_preserves_only_owned_packages_and_rejects_palette_collisions():
    catalog = build.load_recipe('yorimichi').foliage_build.catalog
    assert catalog.independently_owned('/Game/Japan/Assets/Tree_Broad_A')
    assert catalog.independently_owned('/Game/Japan/FoliageLODs/Tree_Broad_A/Tree_Broad_A_LOD1')
    assert catalog.independently_owned('/Game/Japan/Materials/MI_Bark')
    assert not catalog.independently_owned('/Game/Japan/Materials/MI_LeafOlive')
    assert not catalog.independently_owned('/Game/Japan/FoliageLODs/Tree_Tuscan_A/Tree_Tuscan_A_LOD1')
    catalog.check_material_namespace(['LeafOlive', 'LeafCypress'], 'forest')
    with pytest.raises(ValueError, match='shared material ownership'):
        catalog.check_material_namespace(['LeafSmall'], 'forest')
