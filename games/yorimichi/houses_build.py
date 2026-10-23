"""Independent house models, per-lot terrain projections and atomic mesh exports."""
import importlib.util
import json
from pathlib import Path

from atelier import mesh_ir
from atelier.atomic_files import atomic_json
from atelier.build import Call, Product, Python, Step
from atelier.build_inputs import local_imports
from atelier.export_assembly import Item, assemble, runtime_inputs
from atelier.export_manifest import sha

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
REGIONS = WORLD / 'regions'
REGION = REGIONS / 'houses'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def steps(ctx):
    graph = load('houses_atomic_graph', GAME / 'region_exports.py')
    catalogue = load('houses_atomic_catalogue', REGION / 'catalogue.py')
    layout = load('houses_atomic_layout', REGION / 'layout.py')
    result, assets, data_products = [], [], []
    sources = {REGION / 'catalogue.py'}
    for key, (module, function, mode, prefix) in catalogue.ASSETS.items():
        code = set(local_imports(REGION / (module + '.py'), (WORLD, REGIONS)))
        args = ['--asset', key, '--builder', module, '--function', function, '--mode', mode,
                '--seed', '41', '--prefix-draws', str(prefix)]
        reads = []
        if mode == 'lot':
            script = REGION / 'lot_data.py'
            projection = ctx.out / 'house-data' / (key + '.json')
            product = 'houses.data.' + key
            result.append(Step('world.houses.data.' + key, [Python(script, (
                '--asset', key, '--world', str(ctx.out / 'world.json'),
                '--heightmap', str(ctx.out / 'heightmap.npy'), '--output', str(projection)))],
                inputs=[*local_imports(script, (WORLD, REGIONS)), ctx.out / 'world.json', ctx.out / 'heightmap.npy'],
                needs=['world.layout'], products=[Product(product, (projection,))], cache=True,
                about='only this lot placement and its final terrain cells'))
            code.update(local_imports(script, (WORLD, REGIONS)))
            args.extend(['--data', str(projection)])
            reads.append(product)
            data_products.append(product)
        sources.update(path for path in code if path.is_relative_to(REGIONS))
        assets.append(graph.LogicalAsset(key, REGION / 'plan_asset.py', args=tuple(args),
                                       inputs=tuple(sorted(code)), reads=tuple(reads)))
    result.extend(graph.steps(ctx, region='houses', assets=assets))
    root = ctx.out / 'houses'
    atomic = ctx.out / 'atomic_regions/houses'
    def finish(ctx, log):
        parents = json.loads((atomic / 'logical-pieces.json').read_text())['parents']
        if set(parents) != set(catalogue.ASSETS) or any(value != [key] for key, value in parents.items()):
            raise ValueError('House runtime requires the complete eight bounded logical assets')
        value = json.loads((atomic / 'assets/manifest.json').read_text())
        rows = value['exports']
        if {row['asset'] for row in rows} != set(catalogue.ASSETS):
            raise ValueError('Incomplete house export library')
        queries = {key: json.loads((ctx.out / 'house-data' / (key + '.json')).read_text())['lot']
                   for key in catalogue.ASSETS if key.startswith('HouseLot_')}
        # Complete data/source preflight precedes changes to the canonical library.
        records = {str(path.relative_to(REGIONS)): sha(path) for path in sorted(sources)}
        world_hash, height_hash = sha(ctx.out / 'world.json'), sha(ctx.out / 'heightmap.npy')
        manifest = {}
        for row in rows:
            key, meta = row['asset'], row['metadata']
            payload = ctx.out / 'planned_exports/houses' / key / (key + '.npz')
            identity, geometry = mesh_ir.decode(payload.read_bytes())
            if identity['asset'] != key or geometry['triangles'] != row['triangles']:
                raise ValueError('House export differs from its verified geometry product')
            entry = dict(triangles=row['triangles'], vertices=len(geometry['positions']),
                materials=meta['slots'], collision_boxes=meta['collision_hulls'],
                min=[round(v, 3) for v in row['bounds'][0]], max=[round(v, 3) for v in row['bounds'][1]])
            if key.startswith('House_'):
                entry['about'] = layout.HOUSES[key[-1]]['about']
            else:
                lot = queries[key]
                entry.update({field: lot[field] for field in ('house', 'centre', 'level', 'yaw')})
            manifest[key] = entry
        published = assemble([Item(row['asset'], ctx.out / 'exports/world.houses.export' / row['asset'])
                              for row in rows], root / 'assets')
        atomic_json(root / 'manifest.json', manifest)
        # Preserve the existing receiving owner's full layout/terrain checks. These
        # identities affect cheap assembly, never the independent model exports.
        identity = dict(sources=records, world_sha256=world_hash, heightmap_sha256=height_hash,
                        exports={row['primary']: row['sha256'] for row in published['exports']})
        atomic_json(root / 'build-identity.json', identity)
        log.write('Houses: complete eight-asset independently exported library\n')
    result.append(Step('world.houses', [Call('publish houses', finish)],
        inputs=[Path(__file__), REGION / 'layout.py', Path(mesh_ir.__file__), *sorted(sources),
                ctx.out / 'world.json', ctx.out / 'heightmap.npy', *runtime_inputs()],
        reads=['houses.atomic', *('houses.geometry.' + key for key in catalogue.ASSETS), *data_products],
        products=[Product('houses.meshes', (root / 'assets', root / 'manifest.json', root / 'build-identity.json'))],
        about='assemble independent houses and lots without joining geometry'))
    return result
