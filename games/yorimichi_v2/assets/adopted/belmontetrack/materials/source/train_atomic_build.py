"""Selected railway source data and independent authored-LOD mesh exports.

The central recipe calls track_steps with its complete existing route/terrain input
closure. Vehicle and furniture owners are separate from this track graph.
"""
import importlib.util
import json
from pathlib import Path
from atelier.build import Call, Product, Python, Step
from atelier.build_inputs import local_imports
from atelier.export_manifest import name, real_directory
from atelier import export_assembly

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
TRAIN = WORLD / 'train'


def load(label, path):
    spec = importlib.util.spec_from_file_location(label, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def inventory(path):
    path = Path(path); real_directory(path.parent)
    if not path.exists(): return []
    if path.is_symlink() or not path.is_file(): raise ValueError('Linked track source inventory')
    value = json.loads(path.read_text())
    if value.get('schema') != 1 or set(value.get('mesh_order', ())) != set(value.get('meshes', {})):
        raise ValueError('Incomplete track source inventory')
    rows = [(name(key), value['meshes'][key]['levels']) for key in value['mesh_order']]
    if not rows or len({key.casefold() for key, _ in rows}) != len(rows): raise ValueError('Aliased track inventory')
    if any(type(count) is not int or count not in (1, 2, 3) for _, count in rows): raise ValueError('Invalid authored LOD count')
    return rows


def track_steps(ctx, *, source_inputs=(), bank_inputs=()):
    data = ctx.out / 'belmonte-track/source-data'
    roster = data / 'inventory.json'
    script = TRAIN / 'track_sources.py'
    code = local_imports(script, (WORLD, WORLD / 'regions'))
    request_script = TRAIN / 'track_projection.py'
    request_code = [*local_imports(request_script, (WORLD,)),
                    *(TRAIN / file for file in ('track.py', 'station.py', 'station_site.py', 'overbridge.py', 'track_build.py'))]
    inputs = [*code, *source_inputs]
    selected_script = TRAIN / 'construct_track.py'
    selected_code = local_imports(selected_script, (WORLD, WORLD / 'regions'))
    # Only route-derived constructors execute Line/route; fixed primitives and
    # station frames use their published declarations and explicit frame data.
    query_code = local_imports(TRAIN / 'route.py', (WORLD, WORLD / 'regions'))
    terrain_code = local_imports(TRAIN / 'earthworks.py', (WORLD, WORLD / 'regions'))
    result = [Step('world.belmonte_track.sources', [Python(script, ('--output', str(roster)))],
        inputs=inputs, needs=['world.belmonte_train_route'],
        products=[Product('belmonte_track.source_inventory', (roster,))], cache=True, replan=True,
        about='original track placement/query arithmetic without constructing any meshes')]
    rows = inventory(roster)
    product = Product('belmonte_track.library', (ctx.out / 'belmonte-track/atomic',))
    if not rows:
        def refuse(ctx, log): raise ValueError('Track inventory must complete recipe expansion')
        result.append(Step('world.belmonte_track', [Call('cold railway assembly refusal', refuse)],
            needs=['world.belmonte_track.sources'], products=[product]))
        return result
    graph = load('train_track_export_graph', GAME / 'region_exports.py')
    assets = []
    source_products = []
    for parent, count in rows:
        for level in range(count):
            key = f'{parent}_LOD{level}'; path = data / (key + '.json')
            source_product = 'belmonte_track.source.' + key; source_products.append(source_product)
            request = data / 'requests' / (key + '.json')
            request_product = 'belmonte_track.request.' + key
            result.append(Step('world.belmonte_track.request.' + key, [Python(request_script, (
                '--asset', parent, '--level', str(level), '--inventory', str(roster), '--output', str(request)))],
                inputs=[*request_code, roster], needs=['world.belmonte_track.sources'],
                products=[Product(request_product, (request,))], cache=True,
                about='only the selected constructor arguments and exact source frame, without sibling metadata'))
            uses_line = parent.startswith(('SM_TK_Chunk_', 'SM_TK_Loop', 'SM_TK_Tunnel_',
                                          'SM_TK_Bank_', 'SM_TK_Viaduct_', 'SM_ST_Overbridge'))
            bank = parent.startswith('SM_TK_Bank_')
            result.append(Step('world.belmonte_track.source.' + key, [Python(selected_script, (
                '--asset', parent, '--level', str(level), '--descriptor', str(request), '--output', str(path)))],
                inputs=[*selected_code, *(query_code if uses_line else ()),
                        *(terrain_code if bank or parent.startswith('SM_ST_Overbridge') else ()),
                        *(source_inputs if uses_line else ()), *(bank_inputs if bank else ())],
                reads=[request_product, *([
                    'belmonte.natural_surface.SM_BM_NorthApron',
                    'belmonte.natural_surface.SM_BM_NorthCountry'] if bank else [])],
                products=[Product(source_product, (path,))], cache=True, heavy=bank,
                about='exact selected original railway constructor and pre-export source queries'))
            assets.append(graph.LogicalAsset(key, TRAIN / 'plan_track.py', suffix='.glb',
                args=('--source', str(path), '--asset', key, '--materials',
                      str(ctx.out / 'belmonte-track/material-data' / key)),
                reads=(source_product,), products=(Product('belmonte_track.materials.' + key,
                    (ctx.out / 'belmonte-track/material-data' / key,)),)))
    planned = graph.steps(ctx, region='belmonte_track', assets=assets)
    exporter = TRAIN / 'export_track_piece.py'
    for step in planned:
        if not step.name.startswith('world.belmonte_track.export.'): continue
        command, = step.commands
        payload = Path(command.args[1]); key = payload.stem
        palette = ctx.out / 'belmonte-track/material-data' / payload.parent.name / (key + '.json')
        command.script = exporter
        command.args = (*command.args, '--materials', str(palette))
        step.inputs = [path for path in step.inputs if path != WORLD / 'export_region_piece.py']
        step.inputs.extend([*local_imports(exporter, (WORLD,)), palette])
    result.extend(planned)
    def assemble(ctx, log):
        module = load('train_track_file_products', GAME / 'train_track_atomic_products.py')
        module.assemble(ctx.out)
        log.write('Assembled complete railway source/LOD/file membership\n')
    result.append(Step('world.belmonte_track', [Call('assemble railway files', assemble)],
        inputs=[Path(__file__), GAME / 'train_track_atomic_products.py', TRAIN / 'track.py',
                *export_assembly.runtime_inputs()],
        reads=['belmonte_track.atomic', 'belmonte_track.source_inventory', *source_products,
               *('belmonte_track.geometry.' + asset.key for asset in assets)],
        products=[product], about='file-only railway assembly and original signed triangle/disk budget gates'))
    return result
