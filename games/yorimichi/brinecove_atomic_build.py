"""Independent coastal constructors, explicit final query inputs and one export per bounded mesh."""
import importlib.util
from pathlib import Path

from atelier.build import Product, Python, Step
from atelier.build_inputs import local_imports

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
REGIONS = WORLD / 'regions'
REGION = REGIONS / 'brinecove'
COMPONENTS = (
    ('Rocks', 'terrain_dressing'), ('Harbor', 'harbor'), ('TownLower', 'lower_town'),
    ('Market', 'market'), ('TownUpper', 'upper_town'), ('Landmarks', 'landmarks'),
    ('Ships', 'ships'), ('Props', 'props'), ('Understory', 'vegetation'),
)


def load(label, path):
    spec = importlib.util.spec_from_file_location(label, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def steps(ctx):
    graph = load('brinecove_independent_mesh_graph', GAME / 'region_exports.py')
    rim_script = REGION / 'rim_data.py'
    rim = ctx.out / 'brinecove-data/final-rim.json'
    result = [Step('world.brinecove.rim_data', [Python(rim_script, (
        '--source', str(ctx.out / 'terrain/FarHills/final.npz'), '--output', str(rim)))],
        inputs=local_imports(rim_script, (WORLD, REGIONS)), reads=['terrain.FarHills.final'],
        products=[Product('brinecove.rim_data', (rim,))], cache=True,
        about='only the authoritative final FarHills hole boundary consumed by the coast')]
    assets = []
    paving_products, paving_files = [], []
    for key, function in COMPONENTS:
        script = REGION / 'plan_component.py'
        code = set(local_imports(REGION / 'procedural' / (function + '.py'), (WORLD, REGIONS)))
        code.add(REGION / 'procedural/__init__.py')
        parameters = GAME / 'assets/brinecove/export-parameters' / (key + '.json')
        code.add(parameters)
        if REGION / 'procedural/hero_presence.py' in code:
            code.update(GAME / 'assets/brinecove/models' / name for name in (
                'pirate-queen-statue.glb', 'galleon-figurehead.glb', 'ships-wheel.glb',
                'galleon-hull.glb', 'galleon-hull.provenance.json'))
        paving = ctx.out / 'brinecove-data/paving' / (key + '.json')
        product = 'brinecove.paving.' + key
        paving_files.append(paving); paving_products.append(product)
        assets.append(graph.LogicalAsset('SM_BC_' + key, script,
            args=('--asset', key, '--builder', function, '--context', str(parameters),
                  '--rim', str(rim), '--paving-output', str(paving)),
            inputs=tuple(sorted(code)), reads=('brinecove.rim_data',), suffix='.glb',
            products=(Product(product, (paving,)),)))
    ground_script = REGION / 'plan_ground.py'
    ground_query = ctx.out / 'terrain/Brinecove/final.npz'
    arguments = ['--rim', str(rim), '--query-output', str(ground_query)]
    for path in paving_files: arguments.extend(('--paving', str(path)))
    assets.append(graph.LogicalAsset('SM_BC_Ground', ground_script, args=tuple(arguments),
        reads=('brinecove.rim_data', *paving_products), suffix='.glb',
        products=(Product('terrain.Brinecove.final', (ground_query,)),)))
    result.extend(graph.steps(ctx, region='brinecove', assets=assets))
    return result
