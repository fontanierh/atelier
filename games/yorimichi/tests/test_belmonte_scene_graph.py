"""Production Belmonte uses complete narrow preparations and file-only assembly."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from atelier import build

GAME=Path(__file__).resolve().parents[1]


def module():
    spec=importlib.util.spec_from_file_location('belmonte_scene_graph_test',GAME/'belmonte_scene_build.py')
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def test_scene_preparation_reads_query_data_and_never_render_exports(tmp_path):
    graph=module();ctx=SimpleNamespace(out=tmp_path.resolve())
    steps=graph.steps(ctx);build.check_modules(steps)
    assert len(steps)==3 and all(step.cache for step in steps)
    materials=next(step for step in steps if step.name.endswith('prepare_materials'))
    planting=next(step for step in steps if step.name.endswith('prepare_planting'))
    assert materials.reads==['belmonte.scene.materials']
    assert planting.reads==['belmonte.scene.planting','belmonte.valley_final','belmonte.query.SM_BM_NorthApron']
    for step in (materials,planting):
        assert not any('atomic_regions' in path.parts or path.suffix in ('.fbx','.glb') for path in step.inputs)
        assert not any(path.name=='build.py' and path.parent.name=='belmonte' for path in step.inputs)
    assert GAME/'assets/vehicles/belmonte-train/line.json' in planting.inputs


def test_actual_cold_recipe_contains_all_sources_and_complete_assembly_without_legacy_export(tmp_path):
    ctx=SimpleNamespace(game='yorimichi',out=tmp_path.resolve(),logs=tmp_path/'logs',stamps=tmp_path/'stamps',uproject=None)
    recipe=build.load_recipe('yorimichi').steps(ctx)
    selected=build.order(recipe,['world.belmonte']);steps={step.name:step for step in selected}
    assembly=steps['world.belmonte'];build.check_modules([assembly])
    assert len([key for key in steps if key.startswith('world.belmonte_models.geometry.')])==232
    assert len([key for key in steps if key.startswith('world.belmonte_ground.geometry.')])==56
    assert len([key for key in steps if key.startswith('world.belmonte_north.geometry.')])==2
    assert len([key for key in steps if key.startswith('world.belmonte.final_source.')])==56
    assert assembly.commands[0].script==GAME/'world/regions/belmonte/assemble.py'
    assert {'belmonte_models.atomic','belmonte_ground.atomic','belmonte_north.atomic'}<=set(assembly.reads)
    assert len([key for key in assembly.reads if key.startswith('belmonte.final_surface.')])==58
    assert len([key for key in assembly.reads if key.startswith('belmonte.natural_surface.')])==2
    assert len(assembly.products)==4 and not assembly.outputs and assembly.cache and assembly.heavy
    paths={path for product in assembly.products for path in product.paths}
    assert paths=={ctx.out/'belmonte'/key for key in ('glb','textures','ground','natural','runtime.json','build-report.json')}
    assert not any(getattr(command,'script',None)==GAME/'world/regions/belmonte/build.py'
        for step in recipe for command in step.commands)
