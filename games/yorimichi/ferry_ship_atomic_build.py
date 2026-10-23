"""Normal independently cached ferry ship constructors, queries and single-mesh exports.

The central ferry recipe calls steps() instead of the legacy world.ferry_ship action.
Terminal/site preparation remains a separate owner and consumes the assembled manifest.
"""
import importlib.util
from pathlib import Path

from atelier.build import Blender, Call, Product, Python, Step
from atelier.build_inputs import local_imports
from atelier import export_assembly, export_manifest

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
REGION = WORLD / 'regions/ferry'
KIT = GAME / 'assets/vehicles/ferry'


def load(key, path):
    spec = importlib.util.spec_from_file_location(key, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def steps(ctx):
    graph = load('ferry_ship_export_graph', GAME / 'region_exports.py')
    sources = load('ferry_selected_sources', REGION / 'ship_sources.py')
    data = ctx.out / 'ferry/ship-source-data'
    queries = ctx.out / 'ferry/ship-query-data'
    folder = ctx.out / 'ferry'
    result = [Step('world.ferry_ship.sources', [Python(REGION / 'ship_sources.py', ('--output', str(data)))],
        inputs=[*local_imports(REGION / 'ship_sources.py', (WORLD,)), KIT / 'build.py'], cache=True,
        products=[Product('ferry_ship.source.' + key, (data / (key + '.json'),))
                  for key in (*sources.BUILDERS, 'FY_Collision', 'audit')],
        about='exact selected ferry constructor programs; no rendered geometry reads')]
    assets = [graph.LogicalAsset(key, REGION / 'plan_ship.py',
        args=('--asset', key, '--source', str(data / (key + '.json')),
              '--queries', str(queries / (key + '.json'))),
        reads=('ferry_ship.source.' + key,),
        inputs=(WORLD / 'solid_mesh.py',),
        products=(Product('ferry_ship.query.' + key, (queries / (key + '.json'),)),))
        for key in sources.BUILDERS]
    result.extend(graph.steps(ctx, region='ferry_ship', assets=assets))
    audit = folder / 'ship-audit.json'
    proxies = folder / 'ship-collision-data.json'
    result.append(Step('world.ferry_ship.audit', [Blender(REGION / 'ship_audit.py', (
        '--source', str(data / 'audit.json'), '--queries', str(queries), '--output', str(audit),
        '--collision-data', str(proxies), '--deck-layout', str(folder / 'deck_layout.json')),
        threads=3, factory_startup=True)],
        inputs=[*local_imports(REGION / 'ship_audit.py', (WORLD,)), WORLD / 'solid_mesh.py'],
        reads=['ferry_ship.source.audit', *('ferry_ship.query.' + key for key in sources.BUILDERS)],
        products=[Product('ferry_ship.audit', (audit,)), Product('ferry_ship.collision_data', (proxies,)),
                  Product('ferry_ship.deck_layout', (folder / 'deck_layout.json',))],
        heavy=True, cache=True, about='original complete seating/overlap audit from exact pre-export data'))
    collision = ctx.out / 'exports/world.ferry_ship.collision/FY_Collision'
    result.append(Step('world.ferry_ship.collision', [Blender(REGION / 'export_ship_collision.py', (
        '--source', str(data / 'FY_Collision.json'), '--input', str(proxies), '--output', str(collision)),
        threads=3, factory_startup=True)],
        inputs=[*local_imports(REGION / 'export_ship_collision.py', (WORLD,)), WORLD / 'solid_mesh.py'],
        reads=['ferry_ship.source.FY_Collision', 'ferry_ship.collision_data'],
        products=[Product('ferry_ship.collision', (collision,))], heavy=True, cache=True,
        verify=lambda: _present_collision(collision),
        about='single original collision placeholder and every whole authored UCX hull'))
    def assemble(ctx, log):
        products = load('ferry_ship_file_products', GAME / 'ferry_ship_atomic_products.py')
        products.assemble(ctx.out)
        log.write('Assembled complete independently owned ferry ship files\n')
    result.append(Step('world.ferry_ship', [Call('assemble ferry ship files', assemble), Python(KIT / 'walk.py')],
        inputs=[Path(__file__), GAME / 'ferry_ship_atomic_products.py', REGION / 'ship_sources.py',
                KIT / 'build.py', *local_imports(KIT / 'walk.py', (WORLD,)), WORLD / 'solid_mesh.py',
                *export_assembly.runtime_inputs()],
        reads=['ferry_ship.atomic', 'ferry_ship.audit', 'ferry_ship.deck_layout', 'ferry_ship.collision',
               'ferry_ship.source.FY_Hull',
               *('ferry_ship.geometry.' + key for key in sources.BUILDERS)],
        products=[Product('ferry.ship', (folder / 'manifest.json', folder / 'atomic-manifest.json',
            folder / 'atomic-assets', folder / 'review'))],
        about='file-only ferry ship assembly and original full deck walking gates'))
    return result


def _present_collision(root):
    try:
        export_manifest.validate(root, key='FY_Collision')
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False
