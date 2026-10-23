"""Independent bounded lower-level tree exports with the same original polygon owners."""
from pathlib import Path
import importlib.util

from atelier.build import Python, Product, Step
from atelier.build_inputs import local_imports

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
REGIONS = WORLD / 'regions'
REGION = REGIONS / 'hidamari'


def load(label, path):
    spec = importlib.util.spec_from_file_location(label, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def steps(ctx):
    graph = load('city_tree_atomic_graph', GAME / 'region_exports.py')
    policy = load('city_tree_policy', REGION / 'tree_policy.py')
    context = load('city_tree_source_context', REGION / 'source_context.py')
    assets = []
    for parent in policy.TREES:
        constructor = REGION / 'logical' / (parent+'.py')
        parameters = GAME / 'assets/hidamari/export-parameters' / (parent+'.json')
        code = [*local_imports(constructor, (WORLD, REGIONS)), *context.inputs(parameters, parent)]
        for level in (1,2):
            assets.append(graph.LogicalAsset(parent+'_LOD'+str(level), REGION / 'plan_tree_lod.py',
                args=('--asset',parent,'--level',str(level),'--base',str(ctx.out/'planned_exports/hidamari'/parent),
                      '--context',str(parameters)), inputs=tuple(code), reads=('hidamari.geometry.'+parent,)))
    result = graph.steps(ctx, region='city_tree_lods', assets=assets)
    script = GAME / 'city_tree_atomic_products.py'
    result.append(Step('world.city_trees', [Python(script, ('--out', str(ctx.out)))],
        inputs=[*local_imports(script, (GAME, WORLD, REGIONS)),
                GAME / 'unreal/Source/Yorimichi/CitySurfaceParents.h'],
        reads=['city_tree_lods.atomic', 'city.atomic_manifest',
               *('hidamari.geometry.'+key for key in policy.TREES),
               *('city_tree_lods.geometry.'+key+'_LOD'+str(level) for key in policy.TREES for level in (1,2))],
        products=[Product('city.tree_lods', (ctx.out/'city_tree_lods/v4/manifest.json',))], cache=True,
        about='gather complete bounded tree LODs without joining or exporting geometry'))
    return result
