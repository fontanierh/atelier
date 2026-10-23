"""Small independent mini-mega exports and a final-surface query data product."""
import importlib.util
import json
from pathlib import Path

from atelier.atomic_files import atomic_json
from atelier.build import Call, Product, Python, Step
from atelier.build_inputs import local_imports
from atelier.export_assembly import Item, assemble, runtime_inputs
from atelier import mesh_ir

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
REGION = WORLD / 'regions/mega'
ASSETS = ('Mega_Ramp', 'Mega_Trim', 'Mega_Trail')
DIMENSIONS = dict(roll_in_height_m=10.7, gap_m=10.4, quarter_pipe_height_m=6.1, width_m=8.)


def steps(ctx):
    spec = importlib.util.spec_from_file_location('mega_atomic_graph', GAME / 'region_exports.py')
    graph = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(graph)
    data_script = REGION / 'trail_data.py'
    trail = ctx.out / 'mega-data/trail.json'
    result = [Step('world.mega.trail_data', [Python(data_script, (
        '--world', str(ctx.out / 'world.json'), '--heightmap', str(ctx.out / 'heightmap.npy'),
        '--output', str(trail)))],
        inputs=[*local_imports(data_script, (WORLD, WORLD / 'regions')),
                ctx.out / 'world.json', ctx.out / 'heightmap.npy'], needs=['world.layout'],
        products=[Product('mega.trail_data', (trail,))], cache=True,
        about='only the final terrain samples consumed by the woodland trail')]
    ride_inputs = tuple(local_imports(REGION / 'ride.py', (WORLD, WORLD / 'regions')))
    assets = [graph.LogicalAsset(key, REGION / 'plan_asset.py', args=('--asset', key),
                                inputs=ride_inputs) for key in ASSETS[:2]]
    assets.append(graph.LogicalAsset('Mega_Trail', REGION / 'plan_asset.py',
                  args=('--asset', 'Mega_Trail', '--data', str(trail)), reads=('mega.trail_data',)))
    result.extend(graph.steps(ctx, region='mega', assets=assets))
    root = ctx.out / 'mega'
    atomic = ctx.out / 'atomic_regions/mega'
    def finish(ctx, log):
        value = json.loads((atomic / 'assets/manifest.json').read_text())
        parents = json.loads((atomic / 'logical-pieces.json').read_text())['parents']
        if set(parents) != set(ASSETS) or any(children != [parent] for parent, children in parents.items()):
            raise ValueError('Mega riding ownership requires all three current bounded logical assets')
        rows = value['exports']
        if {row['asset'] for row in rows} != set(ASSETS):
            raise ValueError('Mega requires the complete current ride, trim and trail')
        items = [Item(row['asset'], ctx.out / 'exports/world.mega.export' / row['asset']) for row in rows]
        published = assemble(items, root / 'assets')
        manifest = {}
        for row in published['exports']:
            meta = row['metadata']
            payload = ctx.out / 'planned_exports/mega' / row['asset'] / (row['asset'] + '.npz')
            identity, geometry = mesh_ir.decode(payload.read_bytes())
            if identity['asset'] != row['asset'] or geometry['triangles'] != row['triangles']:
                raise ValueError('Mega export differs from its verified geometry product')
            manifest[row['asset']] = dict(triangles=row['triangles'], vertices=len(geometry['positions']),
                materials=len(meta['slots']), collision_boxes=meta['collision_hulls'],
                min=[round(v, 4) for v in row['bounds'][0]], max=[round(v, 4) for v in row['bounds'][1]])
        manifest['dimensions'] = DIMENSIONS
        atomic_json(root / 'manifest.json', manifest)
        log.write('Mega: complete independently exported ride, trim and trail\n')
    result.append(Step('world.mega', [Call('publish mega', finish)],
        inputs=[Path(__file__), Path(mesh_ir.__file__), *runtime_inputs()],
        reads=['mega.atomic', *('mega.geometry.' + key for key in ASSETS)],
        products=[Product('mega.meshes', (root / 'assets', root / 'manifest.json'))],
        about='assemble separate native ride, visual trim and final-surface trail assets'))
    return result
