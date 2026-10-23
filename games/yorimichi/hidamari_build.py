"""Declared city placement products and independent logical mesh construction inputs."""
import importlib.util
from pathlib import Path

from atelier.build import Blender, Product, Python, Step
from atelier.build_inputs import local_imports

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
REGIONS = WORLD / 'regions'
REGION = REGIONS / 'hidamari'
DATA_ASSETS = ('HD_CivicGardens', 'HD_Streets', 'HD_PlazaShopApproaches', 'HD_Wires', 'HD_LaneEdges')


def load(label, path):
    spec = importlib.util.spec_from_file_location(label, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def layout_steps(ctx, *, terrain_inputs=(), terrain_needs=()):
    """@cc [owner:fontanierh,label:correctness;performance] independent-city-layout-products
    City placement MUST be constructed without building or exporting any mesh. Declare
    its complete code, terrain, source-presence and canopy-dimension inputs. Selected
    constructor projections MUST consume only their declared city fields and stop
    unchanged values before any geometry task. Mesh definitions and sibling export
    identities MUST NOT enter a selected city's placement projection or export key.
    """
    out = ctx.out
    script = REGION / 'layout_data.py'
    city = out / 'hidamari/layout-data.json'
    assets = GAME / 'assets'
    result = [Step('world.hidamari.layout_data', [Blender(script, ('--output', str(city)),
        threads=3, factory_startup=True, env=(('PYTHONHASHSEED', '0'),))],
        inputs=[*local_imports(script, (WORLD, REGIONS)), *terrain_inputs,
                REGION / 'location.json', assets / 'hidamari/props',
                assets / 'megapark/map.json', assets / 'megapark/geometry', assets / 'megapark/collision',
                out / 'world.json', out / 'heightmap.npy', out / 'farhills.npy',
                out / 'megapark/trail.json', out / 'treehouse/trees/trees.json'],
        needs=['world.layout', 'world.treehouse_trees', *terrain_needs],
        reads=['terrain.FarHills.final'], products=[Product('hidamari.city_data', (city,))],
        cache=True, toolchain=True, heavy=True,
        about='city placement and final-surface queries without constructing meshes')]
    projection_script = REGION / 'city_data.py'
    for key in DATA_ASSETS:
        path = out / 'hidamari/constructor-data' / (key + '.json')
        result.append(Step('world.hidamari.data.' + key, [Python(projection_script, (
            '--source', str(city), '--asset', key, '--output', str(path)))],
            inputs=local_imports(projection_script, (WORLD, REGIONS)),
            reads=['hidamari.city_data'], products=[Product('hidamari.data.' + key, (path,))],
            cache=True, about='only the city fields consumed by ' + key))
    return result


def mesh_steps(ctx, *, terrain_inputs=(), terrain_needs=()):
    """Build all logical city sources separately, then discover one export per bounded piece.

    Native consumer migration selects this graph when the complete current roster is
    assembled; construction never imports the former whole-city builder.
    """
    graph = load('hidamari_atomic_mesh_graph', GAME / 'region_exports.py')
    catalogue = load('hidamari_logical_catalogue', REGION / 'logical_catalogue.py')
    context = load('hidamari_source_context_inputs', REGION / 'source_context.py')
    parameters = GAME / 'assets/hidamari/export-parameters'
    assets = []
    for key in catalogue.ASSETS:
        constructor = REGION / 'logical' / (key + '.py')
        code = set(local_imports(constructor, (WORLD, REGIONS)))
        code.update((REGION / 'logical/__init__.py', REGION / 'logical_catalogue.py'))
        source_parameters = parameters / (key + '.json')
        code.update(context.inputs(source_parameters, key))
        arguments = ['--asset', key, '--context', str(source_parameters)]
        reads, needs, products = [], [], []
        if REGION / 'layout.py' in code:
            # These constructors sample real final terrain; independent local models do not.
            code.update(terrain_inputs)
            code.update((ctx.out / 'world.json', ctx.out / 'heightmap.npy', ctx.out / 'farhills.npy',
                         ctx.out / 'megapark/trail.json', ctx.out / 'treehouse/trees/trees.json',
                         REGION / 'location.json', GAME / 'assets/megapark/map.json',
                         GAME / 'assets/megapark/geometry', GAME / 'assets/megapark/collision'))
            needs.extend(('world.layout', 'world.treehouse_trees', *terrain_needs))
            if REGION / 'forest_backdrop.py' in code:
                reads.append('terrain.FarHills.final')
        if any(path in code for path in (REGION / 'lettering_mesh.py', REGION / 'kit/_lettering.py')):
            code.add(REGION / 'fonts/NotoSansJP.ttf')
        if key in DATA_ASSETS:
            projection = ctx.out / 'hidamari/constructor-data' / (key + '.json')
            arguments.extend(('--city', str(projection)))
            reads.append('hidamari.data.' + key)
        if key in ('HD_Terrain', 'HD_NorthMountains'):
            for stage in ('natural', 'final', 'provenance'):
                relative = 'manifest.json' if stage == 'provenance' else stage + '.npz'
                products.append(Product('terrain.' + key + '.' + stage,
                                        (ctx.out / 'terrain' / key / relative,)))
        assets.append(graph.LogicalAsset(key, REGION / 'plan_asset.py', args=tuple(arguments),
                      inputs=tuple(sorted(code)), needs=tuple(needs), reads=tuple(reads), products=tuple(products)))
    return graph.steps(ctx, region='hidamari', assets=assets)
