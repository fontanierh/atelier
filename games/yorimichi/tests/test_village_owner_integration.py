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


def test_selected_regions_query_before_exports_and_publish_native_products(tmp_path):
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path.resolve(), logs=tmp_path/'logs',
                          stamps=tmp_path/'stamps', uproject=None)
    steps = build.load_recipe('yorimichi').steps(ctx)
    by_name = {step.name: step for step in steps}
    build.order(steps, ['world.hippodrome', 'world.zeppelin', 'world.skatepark', 'unreal.hippodrome'])
    assert len([s for s in steps if s.name.startswith('world.hippodrome.geometry.')]) == 10
    assert len([s for s in steps if s.name.startswith('world.zeppelin.geometry.')]) == 10
    assert len([s for s in steps if s.name.startswith('world.skatepark.geometry.')]) == 7
    assert len([s for s in steps if s.name.startswith('world.skatepark_board.geometry.')]) == 3
    for name in ('world.hippodrome.queries', 'world.zeppelin.query.ZP_MegaPark'):
        query = by_name[name]
        assert 'world.layout' in query.needs
        assert {ctx.out/'heightmap.npy',ctx.out/'farhills.npy',ctx.out/'megapark/trail.json'} <= set(query.inputs)
        assert not any('export.' in product for product in query.reads)
    assert by_name['unreal.hippodrome'].reads == ['hippodrome.region']
    native = by_name['unreal.hippodrome'].products[0]
    assert ctx.out/'hippodrome/import-report.json' in native.paths
    assert ctx.out/'hippodrome/region/import-report.json' not in native.paths


def test_ferry_ship_is_eight_independent_owners_before_file_assembly(tmp_path):
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path.resolve(), logs=tmp_path/'logs',
                          stamps=tmp_path/'stamps', uproject=None)
    steps = build.load_recipe('yorimichi').steps(ctx)
    by_name = {step.name:step for step in steps}
    build.order(steps,['unreal.ferry'])
    planners=[step for step in steps if step.name.startswith('world.ferry_ship.geometry.')]
    assert len(planners)==8 and all(step.cache for step in planners)
    assert set(by_name['unreal.ferry'].reads)=={'ferry.ship','ferry_ship.collision_data'}
    assert by_name['unreal.ferry'].products[0].paths == (GAME/'unreal/Content/Ferry',ctx.out/'ferry/import-report.json')
    assert not any(getattr(command,'script',None)==GAME/'assets/vehicles/ferry/build.py'
                   for step in steps for command in step.commands)
