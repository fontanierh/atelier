"""Independent normal Village constructors, bounded exports and file-only assembly."""
import importlib.util
import json
from pathlib import Path

from atelier.build import Call, Product, Python, Step
from atelier.build_inputs import local_imports
from atelier.atomic_files import atomic_json

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
REGIONS = WORLD / 'regions'
REGION = REGIONS / 'village'


def load(key, path):
    spec = importlib.util.spec_from_file_location(key, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def steps(ctx):
    sources = load('village_atomic_sources', REGION / 'atomic_sources.py')
    graph = load('village_atomic_graph', GAME / 'region_exports.py')
    folder = ctx.out / 'village-source-data'
    data = Step('world.village.sources', [Python(REGION / 'atomic_sources.py', (
        '--world', str(ctx.out / 'world.json'), '--heightmap', str(ctx.out / 'heightmap.npy'), '--output', str(folder)))],
        inputs=[*local_imports(REGION / 'atomic_sources.py', (WORLD, REGIONS)), GAME / 'assets/village/construction-contexts.json', REGION / 'mesh.py',
                ctx.out / 'world.json', ctx.out / 'heightmap.npy'], needs=['world.layout'], cache=True,
        products=[*[Product('village.source.' + key, (folder / (key + '.json'),)) for key in sources.ASSETS],
                  Product('village.final_heightmap', (folder / 'heightmap.npy',)),
                  Product('village.placements', (folder / 'placements.json',)),
                  Product('village.source_inventory', (folder / 'inventory.json',))],
        about='selected Village geometry/placement projections and original RNG state before exports')
    assets = []
    for key in sources.ASSETS:
        args = ['--asset', key, '--source', str(folder / (key + '.json'))]
        reads = ['village.source.' + key]
        if key in sources.HEIGHTS:
            args.extend(('--heightmap', str(folder / 'heightmap.npy'))); reads.append('village.final_heightmap')
        assets.append(graph.LogicalAsset(key, REGION / 'plan_asset.py', args=tuple(args), reads=tuple(reads)))
    result = [data, *graph.steps(ctx, region='village', assets=assets)]
    def assemble(ctx, log):
        module = load('village_atomic_products', GAME / 'village_atomic_products.py')
        module.assemble(ctx.out)
        log.write('Village: complete independently cached mesh and placement membership\n')
    result.append(Step('world.village', [Call('assemble independent Village', assemble)],
        inputs=[Path(__file__), GAME / 'village_atomic_products.py'],
        reads=['village.atomic', 'village.placements', 'village.source_inventory',
               *('village.geometry.' + key for key in sources.ASSETS)],
        products=[Product('village.meshes', (ctx.out / 'village/atomic-manifest.json',)),
                  Product('village.runtime', (ctx.out / 'village/pieces.json',))],
        about='complete Village files and placements; no geometry joins or old-parent fallback'))
    def digest(ctx, log):
        value = dict(manifest=json.loads((ctx.out / 'village/atomic-manifest.json').read_text()),
                     runtime=json.loads((ctx.out / 'village/pieces.json').read_text()))
        atomic_json(ctx.out / 'digests/world.village.import.json', value)
        log.write('Published complete bounded Village receiving identities\n')
    result.append(Step('world.village.import', [Call('Village receiving digest', digest)],
        inputs=[Path(__file__)], reads=['village.atomic', 'village.meshes', 'village.runtime'],
        outputs=[ctx.out / 'digests/world.village.import.json'], cutoff=True,
        about='current Village receiving cutoff without any legacy parent FBX'))
    return result
