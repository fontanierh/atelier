"""Village's actual graph publishes independent native assets before world consumers."""
from pathlib import Path
from types import SimpleNamespace

from atelier import build

GAME = Path(__file__).resolve().parents[1]


def test_complete_village_owner_is_on_actual_world_and_staging_paths(tmp_path):
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path.resolve(), logs=tmp_path/'logs',
                          stamps=tmp_path/'stamps', uproject=None)
    steps = build.load_recipe('yorimichi').steps(ctx)
    by_name = {step.name: step for step in steps}
    selected = build.order(steps, ['unreal.world', 'data.stage'])
    assert len([step for step in selected if step.name.startswith('world.village.geometry.')]) == 12
    owner = by_name['unreal.village']
    assert set(owner.reads) == {'village.atomic', 'village.meshes', 'village.runtime', 'materials.shared'}
    assert 'unreal.village' in by_name['unreal.world'].after
    assert 'village.native_materials' in by_name['unreal.world'].references
    assert {'village.runtime', 'village.meshes'} <= set(by_name['data.stage'].reads)
    products = {product.name: product for product in owner.products}
    assert products['village.native_meshes'].paths == (GAME/'unreal/Content/Experiments/VillageAtomic/v1_atomic',)
    assert len(products['village.native_materials'].paths) == 2
    assert len(products['village.native_materials'].optional_paths) == 10
    assert owner.candidate_scope.directories == products['village.native_meshes'].paths
    assert all(getattr(command, 'script', None) != GAME/'world/regions/village/build.py'
               for step in selected for command in step.commands)
