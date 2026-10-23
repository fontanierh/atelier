"""Explicit-only independent Stable semantics/LODs, atomic exports and data assembly."""
import importlib.util
from pathlib import Path

from atelier.build import Blender, Call, Product, Python, Step
from atelier.build_inputs import local_imports

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
REGIONS = WORLD / 'regions'
REGION = REGIONS / 'hidamari_stable'


def load(key, path):
    spec = importlib.util.spec_from_file_location(key, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def steps(ctx):
    catalogue = load('stable_atomic_catalogue', REGION / 'catalogue.py')
    query_inputs = load('stable_atomic_query_inputs', REGION / 'query_inputs.py')
    graph = load('stable_atomic_graph', GAME / 'region_exports.py')
    source = ctx.out / 'stable-source-data'
    query = ctx.out / 'stable-query-data'
    samples = ctx.out / 'stable-sampled-queries'
    query_names = query_inputs.generated()
    data = Step('world.hidamari_stable.sources', [Python(REGION / 'atomic_sources.py', ('--output', str(source),
        '--query-output', str(query), '--data-root', str(ctx.out)))],
        inputs=[*local_imports(REGION / 'atomic_sources.py', (WORLD, REGIONS)),
                GAME / 'assets/hidamari-stable/construction-contexts.json', *(ctx.out / name for name in query_names)],
        needs=['world.layout', 'world.treehouse_trees.data', 'world.craterpark_geometry'], cache=True,
        products=[*[Product('stable.source.' + key, (source / (key + '.json'),)) for key in catalogue.SOURCES],
                  Product('stable.query.sources', (query,))],
        about='selected original Stable random contexts; committed disabled policy refuses normal generation')
    queried = ('SM_HS_Road', 'SM_HS_RoadSign')
    query_step = Step('world.hidamari_stable.query', [Blender(REGION / 'query_data.py', (
        '--source-root', str(query), '--road-context', str(source / 'SM_HS_Road.json'),
        '--sign-context', str(source / 'SM_HS_RoadSign.json'), '--output', str(samples)),
        threads=3, factory_startup=True, env=(('PYTHONHASHSEED', '0'),))],
        inputs=[*local_imports(REGION / 'query_data.py', (WORLD, REGIONS)), *query_inputs.committed(),
                REGIONS / 'hidamari/fonts/NotoSansJP.ttf'],
        reads=['stable.query.sources', *('stable.source.' + key for key in queried)],
        products=[*[Product('stable.queries.' + key, (samples / (key + '.json'),)) for key in queried],
                  Product('stable.site_query', (samples / 'site.json',))],
        cache=True, toolchain=True, heavy=True,
        about='canonical exact selected north height queries before any Stable render export')
    logical = []
    for key in catalogue.SOURCES:
        terrain = key in queried
        logical.append(graph.LogicalAsset(key, REGION / 'plan_asset.py',
            args=('--asset', key, '--source', str(source / (key + '.json')),
                  *(('--queries', str(samples / (key + '.json'))) if terrain else ())),
            reads=('stable.source.' + key, *(('stable.queries.' + key,) if terrain else ())), suffix='.glb',
            inputs=(REGIONS / 'hidamari/fonts/NotoSansJP.ttf',)))
    result = [data, query_step, *graph.steps(ctx, region='hidamari_stable', assets=logical)]
    def assemble(ctx, log):
        module = load('stable_atomic_products', GAME / 'stable_atomic_products.py')
        module.assemble(ctx.out)
        log.write('Stable: complete independent semantic/LOD exports and canonical anchors\n')
    result.append(Step('world.hidamari_stable', [Call('assemble independent Stable files and anchors', assemble)],
        inputs=[GAME / 'stable_atomic_products.py', *local_imports(REGION / 'placement_data.py', (WORLD, REGIONS))],
        reads=['hidamari_stable.atomic', 'stable.site_query',
               *('hidamari_stable.geometry.' + key for key in catalogue.SOURCES)],
        products=[Product('stable.meshes', (ctx.out / 'hidamari-stable/atomic-manifest.json',)),
                  Product('stable.runtime', (ctx.out / 'hidamari-stable/placements.json',))],
        about='complete file-only Stable assembly; no rendered export depends on another export'))
    for step in result: step.explicit = True
    return result
