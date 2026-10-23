"""One writer for every Unreal Content package that more than one import used to save.

The step cache restores a run by the files it saved, so a shared package cannot be
restored per step. `content_ownership.PRODUCERS` declares the single producer of each
shared package; these tests hold the declaration, the build plan and the import
scripts together.
"""
import sys
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
SCRIPTS = GAME / 'unreal' / 'Scripts'
sys.path.insert(0, str(SCRIPTS))

import content_ownership as owned  # noqa: E402


def main_body(name):
    """Everything after `def main():` in an import script."""
    text = (SCRIPTS / name).read_text()
    return text.split('def main():', 1)[1]


def test_no_shared_package_has_two_writers():
    assert owned.duplicate_writers() == {}
    for path, steps in owned.writers().items():
        assert len(steps) == 1, (path, steps)


def test_the_check_catches_a_second_writer():
    second = (*owned.PRODUCERS, ('unreal.southwest', ('/Game/Japan/Terrain',)))
    assert owned.duplicate_writers(second) == {'/Game/Japan/Terrain': ['unreal.world', 'unreal.southwest']}
    assert owned.writers()['/Game/Japan/Terrain'] == ['unreal.world']


def test_every_producer_is_a_declared_unreal_step():
    source = (GAME / 'build.py').read_text()
    for step, _paths in owned.PRODUCERS:
        assert f"Step('{step}'" in source, step


def test_the_owner_scripts_write_the_declared_packages():
    """The table follows the code: each package is still created by its declared step."""
    needles = {
        '/Game/Japan/Terrain': ('import_hidamari.py', "import_mesh(ROOT/'terrain.fbx'"),
        '/Game/Japan/Assets/Sea': ('setup_project.py', 'sea_plane()'),
        '/Game/Japan/Materials/MI_Coast': ('import_hidamari.py', 'coast_instance()'),
        '/Game/Japan/Materials/MI_Sand': ('import_hidamari.py', 'sand_material()'),
        '/Game/Japan/Materials/M_ForestGround': ('import_hidamari.py', 'coast_instance()'),
        '/Game/Japan/Materials/M_Sea': ('import_southwest.py', 'sea_material()'),
        '/Game/Japan/Materials/M_Village': ('setup_project.py', 'import_village.main(terrain=False)'),
    }
    assert set(needles) == set(owned.writers()), 'the table and these checks must cover the same packages'
    for path, (script, needle) in needles.items():
        assert needle in (SCRIPTS / script).read_text(), (path, script, needle)


def test_the_other_imports_only_read_the_shared_packages():
    lake = (SCRIPTS / 'import_forest_lake.py').read_text()
    assert 'terrain.fbx' not in lake
    assert 'save_loaded_asset(terrain' not in lake

    southwest = (SCRIPTS / 'import_southwest.py').read_text()
    body = main_body('import_southwest.py')
    for write in ("terrain.fbx", 'sand_material()', 'coast_instance()', 'sea_plane()', 'sea_material()'):
        assert write not in body, write
    assert "load_asset('/Game/Japan/Materials/M_Village')" in body
    assert 'save_loaded_asset' in southwest


def test_the_world_step_needs_the_regions_it_places():
    """The producer runs first: the regions that read its packages need it."""
    source = (GAME / 'build.py').read_text()
    for step in ('unreal.southwest', 'unreal.lake'):
        block = source.split(f"Step('{step}'", 1)[1].split('Step(', 1)[0]
        assert "needs=['unreal.world'" in block, step


def test_southwest_no_longer_needs_the_terrain_mesh_export():
    source = (GAME / 'build.py').read_text()
    block = source.split("Step('unreal.southwest'", 1)[1].split('Step(', 1)[0]
    assert 'world.terrain.meshes' not in block
