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


@pytest.mark.parametrize('source', [SCRIPTS / 'foliage_package_repair.py', SCRIPTS / 'prepare_foliage.py',
                                    build.paths.STUDIO / 'atelier/unreal_preflight.py'])
def test_package_repair_code_invalidates_native_owners_without_reexporting_geometry(tmp_path, monkeypatch, source):
    changed = changed_by(source, tmp_path, monkeypatch)
    native = {name for name in changed if name.startswith('unreal.foliage.')}
    assert len(native) == 18
    assert changed == native | PACKAGING


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
    recipe = build.load_recipe('yorimichi')
    graph = build_products.Graph(recipe.steps(ctx))
    world = graph.by_name['unreal.world']
    assert not any(name.startswith('foliage.') for name in world.reads)
    names = {step.name for step in graph.select(['unreal.world'])}
    assert len([name for name in names if name.startswith('unreal.foliage.')]) == 18
    assert 'unreal.materials' in names
    expected = {'materials.shared': 'unreal.materials', 'materials.foliage_interface': 'unreal.materials'}
    for name in recipe.foliage_build.catalog.FOLIAGE:
        expected['foliage.' + name + '.source'] = 'world.foliage.' + name
        expected['foliage.' + name + '.native'] = 'unreal.foliage.' + name
    for step in recipe.texture_steps(ctx):
        expected.update({product.name: step.name for product in step.products})
    assert len(expected) == 60
    expected.update({f'terrain.FarHills.{stage}': 'world.farhills'
                     for stage in ('natural', 'final', 'provenance')})
    expected.update({f'terrain.HD_NorthMountains.{stage}': 'world.hidamari'
                     for stage in ('natural', 'final', 'provenance')})
    expected.update({name: name for name in ('audio.footsteps', 'audio.skate')})
    expected.update({f'terrain.HD_Terrain.{stage}': 'world.hidamari'
                     for stage in ('natural', 'final', 'provenance')})
    expected['gondola.kit']='world.gondola_kit'
    expected.update({f'brinecove.{part}': 'world.brinecove.meshes'
                     for part in ('geometry', 'materials', 'runtime', 'map', 'clearance')})
    expected.update({'brinecove.model.' + definition.stem: 'world.brinecove.model.' + definition.stem
                     for definition in recipe.brinecove_library.definitions()})
    expected.update({f'belmonte.{part}': 'world.belmonte.meshes'
                     for part in ('geometry', 'materials', 'runtime')})
    expected.update({f'belmonte.native_{part}': 'unreal.belmonte'
                     for part in ('meshes', 'materials', 'tv', 'report')})
    expected.update({f'brinecove.native_{part}': 'unreal.brinecove'
                     for part in ('meshes', 'materials', 'report')})
    assert graph.owners == expected
    assert all(not graph.by_name[owner].cache for product, owner in expected.items()
               if any(isinstance(command, (build.UnrealScript, build.UnrealCompile, build.UnrealPackage))
                      for command in graph.by_name[owner].commands))
    adapter = build.paths.STUDIO / 'atelier/blender/fbx.py'
    assert all(adapter in step.inputs for step in graph.by_name.values() if step.name.startswith('world.foliage.'))


@pytest.mark.parametrize('same_bytes', [False, True])
def test_one_texture_spec_preserves_foliage_owners_and_byte_cutoffs(tmp_path, monkeypatch, same_bytes):
    changed = changed_by(WORLD / 'textures/white.json', tmp_path, monkeypatch,
                         stable_products={'texture.white'} if same_bytes else ())
    assert {name for name in changed if name.startswith('world.textures.')} == {'world.textures.white'}
    assert not any('.foliage.' in name for name in changed)
    if same_bytes:
        assert changed == {'world.textures.white'}
    else:
        assert {'world.textures', 'unreal.world'} <= changed


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
