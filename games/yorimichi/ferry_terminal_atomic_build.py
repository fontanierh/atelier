"""Independent normal terminal constructors, exact queries, audit and file-only assembly."""
import importlib.util
from pathlib import Path

from atelier import export_assembly, export_manifest
from atelier.build import Blender, Call, DeferredInputs, Product, Python, Step
from atelier.build_inputs import local_imports

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
REGION = WORLD / 'regions/ferry'
KIT = GAME / 'assets/vehicles/ferry/terminals'
MODELS = ('FT_HD_Jetty', 'FT_HD_Stage', 'FT_HD_Brow', 'FT_HD_WaitingHouse', 'FT_HD_Timetable',
          'FT_BC_Landing', 'FT_BC_Brow', 'FT_BC_Fenders', 'FT_BC_Pavilion', 'FT_BC_TicketHut', 'FT_BC_Props')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def proof_paths(build, repo):
    """Complete actual sweep/raw/final source proof files, discovered after the cut prerequisite."""
    build, repo = Path(build), Path(repo)
    module = load('ferry_terminal_proof_paths', REGION / 'site_inputs.py')
    result = set(module.paths(build, repo))
    result.update(build / relative for relative in ('hidamari/final-source-data/harbor-cut.json',
        'hidamari/final-source-data/harbor-cut-data.json', 'hidamari/query-data/HD_Harbor.npz'))
    for directory in (build / 'hidamari/source-data/HD_Harbor', build / 'planned_exports/hidamari/HD_Harbor'):
        export_manifest.real_directory(directory)
        if directory.exists(): result.update(directory.iterdir())
    return sorted(result)


def steps(ctx, *, site_inputs):
    graph = load('ferry_terminal_export_graph', GAME / 'region_exports.py')
    folder = ctx.out / 'ferry/terminals'
    data = folder / 'source-data'; queries = folder / 'query-data'
    harbor = ctx.out / 'hidamari/query-data/HD_Harbor.npz'
    keys = (*MODELS, 'hidamari_collision', 'brinecove_collision', 'hidamari_walk', 'brinecove_walk', 'primitives')
    result = [Step('world.ferry_terminals.sources', [Python(REGION / 'terminal_sources.py', (
        '--site', str(folder / 'site.json'), '--world-hidamari', str(folder / 'world_hidamari.npz'),
        '--world-brinecove', str(folder / 'world_brinecove.npz'), '--harbor-query', str(harbor),
        '--output', str(data), '--proof', str(folder / 'source-proof.json')))],
        inputs=[*local_imports(REGION / 'terminal_sources.py', (WORLD,)), KIT / 'build.py', KIT.parent / 'build.py',
                *site_inputs, *(WORLD / 'regions' / owner / 'ferry_terminal.py' for owner in ('hidamari', 'brinecove'))],
        needs=['world.ferry_site', 'world.hidamari_ferry_cut'], reads=['hidamari.query.HD_Harbor'],
        deferred_inputs=[DeferredInputs('terminal-final-query-proof', proof_paths, (ctx.out, GAME.parents[1]),
            support=(Path(__file__), REGION / 'site_inputs.py', WORLD / 'regions/hidamari/ferry_source.py'))],
        products=[*[Product('ferry_terminals.source.' + key, (data / (key + '.json'),)) for key in keys],
                  Product('ferry_terminals.query_proof', (folder / 'source-proof.json',))], cache=True,
        about='selected original terminal programs, exact scalar plans and verified final Harbor ground queries')]
    assets = [graph.LogicalAsset(key, REGION / 'plan_terminal.py', args=(
        '--asset', key, '--source', str(data / (key + '.json')),
        '--queries', str(queries / (key + '.json'))), inputs=(WORLD / 'solid_mesh.py',),
        reads=('ferry_terminals.source.' + key,),
        products=(Product('ferry_terminals.query.' + key, (queries / (key + '.json'),)),)) for key in MODELS]
    result.extend(graph.steps(ctx, region='ferry_terminals', assets=assets))
    result.append(Step('world.ferry_terminals.audit', [Blender(REGION / 'terminal_audit.py', (
        '--sources', str(data), '--queries', str(queries), '--harbor-query', str(harbor),
        '--output', str(folder / 'atomic-audit.json')), threads=3, factory_startup=True)],
        inputs=[*local_imports(REGION / 'terminal_audit.py', (WORLD,)), KIT / 'build.py', KIT.parent / 'build.py', *site_inputs],
        needs=['world.ferry_site'], reads=['ferry_terminals.query_proof',
            *('ferry_terminals.source.' + key for key in MODELS),
            *('ferry_terminals.source.' + key for key in ('primitives', 'hidamari_collision', 'brinecove_collision', 'hidamari_walk', 'brinecove_walk')),
            *('ferry_terminals.query.' + key for key in MODELS),
            *('ferry_ship.query.' + key for key in ('FY_Hull', 'FY_Superstructure', 'FY_Funnel', 'FY_Lifeboats', 'FY_Rails', 'FY_Masts', 'FY_Fittings')),
            'hidamari.query.HD_Harbor'],
        deferred_inputs=[DeferredInputs('terminal-audit-site-proof', proof_paths, (ctx.out, GAME.parents[1]),
            support=(Path(__file__), REGION / 'site_inputs.py', WORLD / 'regions/hidamari/ferry_source.py'))],
        products=[Product('ferry_terminals.audit', (folder / 'atomic-audit.json',)),
                  Product('ferry_terminals.walk', (folder / 'walk.json',)),
                  *(Product('ferry_terminals.collision_data.' + owner, (folder / (owner + '-collision-data.json'),))
                    for owner in ('hidamari', 'brinecove'))], heavy=True, cache=True,
        about='all original closure, seating, coplanar, carried, ship-contact, headroom and walking gates'))
    for owner, key in (('hidamari', 'FT_HD_Collision'), ('brinecove', 'FT_BC_Collision')):
        destination = ctx.out / 'exports/world.ferry_terminals.collision' / key
        result.append(Step('world.ferry_terminals.collision.' + key, [Blender(REGION / 'export_terminal_collision.py', (
            '--input', str(folder / (owner + '-collision-data.json')), '--primitives', str(data / 'primitives.json'),
            '--output', str(destination)), threads=3, factory_startup=True)],
            inputs=[*local_imports(REGION / 'export_terminal_collision.py', (WORLD,)), WORLD / 'solid_mesh.py'],
            reads=['ferry_terminals.collision_data.' + owner, 'ferry_terminals.source.primitives'],
            products=[Product('ferry_terminals.collision.' + key, (destination,))], heavy=True, cache=True,
            verify=lambda destination=destination, key=key: present(destination, key),
            about='single original fixed terminal collision primary with every whole UCX hull'))
    def assemble(ctx, log):
        load('ferry_terminal_file_products', GAME / 'ferry_terminal_atomic_products.py').assemble(ctx.out)
        log.write('Assembled complete independent terminal files and current walking proof\n')
    result.append(Step('world.ferry_terminals', [Call('assemble independent ferry terminals', assemble)],
        inputs=[Path(__file__), GAME / 'ferry_terminal_atomic_products.py',
                *local_imports(REGION / 'service.py', (WORLD,)), *export_assembly.runtime_inputs()],
        reads=['ferry_terminals.atomic', 'ferry_terminals.audit', 'ferry_terminals.walk',
            'ferry_terminals.collision.FT_HD_Collision', 'ferry_terminals.collision.FT_BC_Collision',
            *('ferry_terminals.geometry.' + key for key in MODELS)],
        products=[Product('ferry.terminals', (folder / 'manifest.json', folder / 'atomic-manifest.json', folder / 'atomic-assets'))],
        about='file-only terminal assembly; independent native mesh identities and original anchors remain intact'))
    return result


def present(root, key):
    try:
        export_manifest.validate(root, key=key); return True
    except (OSError, ValueError, KeyError, TypeError): return False
