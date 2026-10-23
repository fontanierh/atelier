"""Declared city placement products and independent logical mesh construction inputs."""
import importlib.util
from pathlib import Path

from atelier.build import Batch, Blender, Call, DeferredInputs, Product, Python, Step
from atelier.build_batch_source import support as batch_support
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
    assets, prerequisites = [], []
    for key in catalogue.ASSETS:
        constructor = REGION / 'logical' / (key + '.py')
        code = set(local_imports(constructor, (WORLD, REGIONS)))
        code.add(REGION / 'logical/__init__.py')
        source_parameters = parameters / (key + '.json')
        code.update(context.inputs(source_parameters, key))
        arguments = ['--asset', key, '--context', str(source_parameters)]
        reads, needs, products = [], [], []
        query = ctx.out / 'hidamari/query-data' / (key + '.npz')
        arguments.extend(('--query-output', str(query)))
        products.append(Product('hidamari.query.' + key, (query,)))
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
        if key == 'HD_Harbor':
            raw = ctx.out / 'hidamari/source-data' / key
            raw_query = ctx.out / 'hidamari/query-data' / (key + '.raw.npz')
            script = REGION / 'plan_asset.py'
            prerequisites.append(Step('world.hidamari.source.' + key,
                [Blender(script, ('--asset', key, '--context', str(source_parameters), '--source-only',
                    '--output', str(raw), '--query-output', str(raw_query)), threads=3,
                    factory_startup=True, env=(('PYTHONHASHSEED', '0'),))],
                inputs=[*local_imports(script, (WORLD, REGIONS)), *batch_support().values(), *sorted(code)],
                needs=needs, reads=reads,
                products=[Product('hidamari.source.' + key, (raw,)), Product('hidamari.query.' + key + '.raw', (raw_query,))],
                cache=True, toolchain=True, heavy=True, batch=Batch('hidamari logical geometry'),
                about='raw Harbor source/query data before ferry access cuts; no mesh export'))
            proof_helper = REGIONS / 'ferry/site_inputs.py'
            proof = load('hidamari_ferry_proof_membership', proof_helper)
            cut = ctx.out / 'hidamari/final-source-data/harbor-cut.json'
            cut_data = ctx.out / 'hidamari/final-source-data/harbor-cut-data.json'
            prerequisites.append(Step('world.hidamari.harbor_cut_data',
                [Call('verified Harbor cut parameters', lambda ctx, log, proof=proof, cut_data=cut_data:
                      proof.record(ctx.out, GAME.parents[1], cut_data, log))],
                inputs=[proof_helper], needs=['world.ferry_site'], outputs=[cut_data], cutoff=True,
                deferred_inputs=[DeferredInputs('ferry-cut-proof', proof.paths, (ctx.out, GAME.parents[1]),
                                                support=(proof_helper,))],
                about='verify complete ferry sweep proof before projecting unchanged cut parameters'))
            assets.append(graph.LogicalAsset(key, REGION / 'plan_harbor.py', args=(
                '--source', str(raw), '--cut-data', str(cut_data), '--query-output', str(query), '--proof-output', str(cut)),
                inputs=(cut_data,), needs=('world.hidamari.harbor_cut_data',), reads=('hidamari.source.' + key,),
                products=(Product('hidamari.query.' + key, (query,)), Product('hidamari.harbor_cut', (cut,)))))
        else:
            assets.append(graph.LogicalAsset(key, REGION / 'plan_asset.py', args=tuple(arguments),
                          inputs=tuple(sorted(code)), needs=tuple(needs), reads=tuple(reads), products=tuple(products)))
    return [*prerequisites, *graph.steps(ctx, region='hidamari', assets=assets)]


def metadata_steps(ctx, *, terrain_inputs=(), terrain_needs=()):
    """Independent masks and file-only logical placement/material metadata."""
    masks = REGION/'north_masks.py'
    metadata = GAME/'hidamari_metadata.py'
    helper = load('city_logical_metadata',metadata)
    catalogue = load('city_logical_metadata_roster',REGION/'logical_catalogue.py')
    outputs = [ctx.out/'hidamari'/('north_'+key+suffix) for key in ('snow','crater') for suffix in ('.png','.json')]
    result = [Step('world.hidamari.north_masks',[Blender(masks,threads=3,factory_startup=True,
                    env=(('PYTHONHASHSEED','0'),))],
        inputs=[*local_imports(masks,(WORLD,REGIONS)),*terrain_inputs,
                ctx.out/'world.json',ctx.out/'heightmap.npy',ctx.out/'farhills.npy',
                ctx.out/'megapark/trail.json',ctx.out/'treehouse/trees/trees.json',REGION/'location.json'],
        needs=['world.layout','world.treehouse_trees',*terrain_needs],
        products=[Product('hidamari.north_masks',tuple(outputs))],cache=True,toolchain=True,heavy=True,
        about='north snow/crater mask data; no mesh generation or export'),
        Step('world.hidamari',[Python(metadata,('--out',str(ctx.out)))],
        inputs=[*local_imports(metadata,(GAME,WORLD,REGIONS)),catalogue.ROSTER],
        reads=['hidamari.city_data',*('hidamari.geometry.'+key for key in catalogue.ASSETS)],
        products=[Product('hidamari.logical_metadata',(ctx.out/'hidamari/city.json',ctx.out/'hidamari/manifest.json'))],
        cache=True,about='logical city placement and materials; geometry stays independently owned')]
    for north,key in ((False,'city'),(True,'north')):
        destination = ctx.out/'digests'/('world.hidamari.'+key+'.json')
        def record(ctx,log,north=north,destination=destination):
            digest = load('city_material_metadata_digest',GAME/'export_digest.py')
            digest.record(destination,helper.material_inputs(ctx.out,north),log)
        result.append(Step('world.hidamari.'+key,[Call('city material/placement prerequisites',record)],
            inputs=[metadata,GAME/'export_digest.py',REGION/'logical_catalogue.py',catalogue.ROSTER],
            reads=['hidamari.logical_metadata','hidamari.north_masks'],outputs=[destination],cutoff=True,
            about='city material preparation only; excludes every mesh/export identity'))
    return result


def assembly_steps(ctx):
    script = GAME/'city_atomic_products.py'
    catalogue = load('complete_atomic_city_roster',REGION/'logical_catalogue.py')
    return [Step('world.city_tiles',[Python(script,('--out',str(ctx.out)))],
        inputs=[*local_imports(script,(GAME,WORLD,REGIONS)),catalogue.ROSTER],
        reads=['hidamari.atomic',*('hidamari.geometry.'+key for key in catalogue.ASSETS)],
        products=[Product('city.atomic_manifest',(ctx.out/'city_surface_tiles/v1_128m/manifest.json',)),
                  Product('city.atomic_sources',tuple(ctx.out/'city_surface_tiles/v1_128m'/key for key in catalogue.ASSETS))],
        cache=True,about='file-only gathering of all independently exported bounded city pieces')]
