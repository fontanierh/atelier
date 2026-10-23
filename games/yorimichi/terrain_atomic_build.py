"""Normal independent island source projections, bounded exports and file-only assembly."""
import importlib.util
import json
import os
from pathlib import Path

from atelier.atomic_files import atomic_json
from atelier import mesh_ir
from atelier.build import Call, Product, Python, Step
from atelier.build_inputs import local_imports

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
ASSETS = ('Terrain', 'Road', 'Lane', 'Guardrail', 'Wires', 'FarHills', 'Sea')


def selected(root):
    path = root / 'inventory.json'
    if not os.path.lexists(path):
        # Cold recipes must still declare the complete stable downstream targets.
        # The first successful source projection replans before any constructor.
        return ASSETS
    from atelier.export_manifest import real_directory
    real_directory(root)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Invalid island source inventory')
    value = json.loads(path.read_text())
    result = value.get('assets')
    if (value.get('schema') != 1 or not isinstance(result, list) or not result
            or not {'Terrain', 'Road', 'Wires', 'FarHills', 'Sea'} <= set(result)
            or result != [key for key in ASSETS if key in result]):
        raise ValueError('Incomplete or foreign island source inventory')
    return tuple(result)


def steps(ctx, *, city=True):
    """@cc [owner:fontanierh,label:correctness;performance] island-atomic-export-task-owners
    Canonical final FarHills data MUST precede render planning, without acquiring render
    products as inputs. Island logical data MUST be projected before independently cached
    planners. Each bounded child MUST remain a separate primary export/native mesh asset;
    assembly MUST gather files and placement metadata without joining geometry. Cold
    source discovery MUST complete before expanding executable logical/export tasks.
    """
    spec = importlib.util.spec_from_file_location('island_region_graph', GAME / 'region_exports.py')
    graph = importlib.util.module_from_spec(spec); spec.loader.exec_module(graph)
    folder = ctx.out / 'island-source-data'
    products = [Product('island.source.' + key, (folder / (key + '.json'),)) for key in ASSETS]
    products.extend((Product('island.heightmap', (folder / 'heightmap.npy',)),
                     Product('island.source_inventory', (folder / 'inventory.json',))))
    projection = Step('world.island.sources', [Python(WORLD / 'terrain_sources.py', (
        '--world', str(ctx.out / 'world.json'), '--heightmap', str(ctx.out / 'heightmap.npy'),
        '--output', str(folder), *(('--no-city',) if not city else ())))],
        inputs=[*local_imports(WORLD / 'terrain_sources.py', (WORLD,)),
                ctx.out / 'world.json', ctx.out / 'heightmap.npy'],
        needs=['world.layout'], products=products, cache=True, replan=True,
        about='project separate island constructor data before any rendered export')
    assets = []
    for key in selected(folder):
        args = ['--asset', key, '--source', str(folder / (key + '.json'))]
        reads = ['island.source.' + key]
        if key in ('Terrain', 'Lane'):
            args += ['--heightmap', str(folder / 'heightmap.npy')]; reads.append('island.heightmap')
        if key == 'FarHills':
            args += ['--final', str(ctx.out / 'terrain/FarHills/final.npz')]
            reads.append('terrain.FarHills.final')
        # Coastal colour/slot ownership reads the committed railway headland mask.
        # It is data, not an importable Python module, and must be declared explicitly.
        inputs = (GAME / 'assets/vehicles/belmonte-train/line.json',) if key in ('Terrain', 'FarHills') else ()
        assets.append(graph.LogicalAsset(key, WORLD / 'plan_terrain.py', args=tuple(args),
                                        reads=tuple(reads), inputs=inputs))
    result = [projection, *(graph.steps(ctx, region='island', assets=assets) if assets else ())]
    if assets:
        def receiving(ctx, log):
            spec = importlib.util.spec_from_file_location('island_receiving_metadata', GAME / 'island_atomic_products.py')
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            value = module.source_metadata(ctx.out)
            atomic_json(ctx.out / 'terrain/island-receiving.json', value)
            log.write('Projected exact used slots for every bounded island mesh\n')
        result.append(Step('world.island.receiving', [Call('island native source metadata', receiving)],
            inputs=[Path(__file__), GAME / 'island_atomic_products.py', WORLD / 'region_mesh_parts.py',
                    WORLD / 'region_plan_files.py', Path(mesh_ir.__file__),
                    *(Path(mesh_ir.__file__).with_name(key) for key in
                      ('export_manifest.py', 'model_files.py', 'atomic_files.py'))],
            reads=['island.atomic', *('island.geometry.' + a.key for a in assets)],
            products=[Product('island.receiving', (ctx.out / 'terrain/island-receiving.json',))],
            about='exact consumed slot metadata for bounded native receiving'))
    def publish(ctx, log):
        spec = importlib.util.spec_from_file_location('island_runtime_metadata', GAME / 'island_atomic_products.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        groups = module.read(ctx.out)
        value = dict(schema=1, complete=True, origin=[0., 0., 0.], parents={parent: dict(
            meshes=[dict(name=row['name'], asset=row['asset'], sha256=row['sha256'],
                         triangles=row['triangles'], min=row['min'], max=row['max'],
                         materials=module.material_paths(parent, group['slots']),
                         used_slots=row['used_slots']) for row in group['pieces']],
            collision=group['collision'], cast_shadow=group['cast_shadow']) for parent, group in groups.items()})
        atomic_json(ctx.out / 'terrain/island.json', value)
        log.write('Published complete separate island runtime mesh membership\n')
    result.append(Step('world.terrain', [Call('island terrain membership', publish)],
        inputs=[Path(__file__), GAME / 'island_atomic_products.py'],
        reads=['island.atomic', 'island.receiving', 'island.source_inventory'],
        products=[Product('terrain.island.runtime', (ctx.out / 'terrain/island.json',))],
        about='complete island placement and export ownership without joining meshes'))
    def digest(ctx, log):
        value = json.loads((ctx.out / 'terrain/island.json').read_text())
        atomic_json(ctx.out / 'digests/world.terrain.meshes.json', value)
        log.write('Published current independent island receiving identities\n')
    result.append(Step('world.terrain.meshes', [Call('island receiving digest', digest)],
        inputs=[Path(__file__)], needs=['world.terrain'], reads=['terrain.island.runtime'],
        outputs=[ctx.out / 'digests/world.terrain.meshes.json'], cutoff=True,
        about='content cutoff for independent island native imports'))
    return result
