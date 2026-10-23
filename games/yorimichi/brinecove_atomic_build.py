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
HEROES = ('pirate-queen-statue', 'galleon-hull', 'harbor-capstan')


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
    for slug in HEROES:
        name = 'SM_BC_Hero_' + ''.join(part.title() for part in slug.split('-'))
        materials = ctx.out / 'brinecove-data/heroes' / slug
        assets.append(graph.LogicalAsset(name, REGION / 'plan_hero.py',
            args=('--slug', slug, '--metadata-output', str(materials)), suffix='.glb',
            inputs=tuple(GAME / 'assets/brinecove/models' / (slug + suffix)
                         for suffix in ('.glb', '.provenance.json')),
            products=(Product('brinecove.hero_materials.' + slug, (materials,)),)))
    result.extend(graph.steps(ctx, region='brinecove', assets=assets))
    placement_script = REGION / 'placement_data.py'
    placements = ctx.out / 'brinecove-data/placements.json'
    library = ctx.out / 'digests/brinecove-source-library.json'
    model_inputs = [path for path in (GAME / 'assets/brinecove/models').iterdir()
                    if path.suffix == '.glb' or path.name.endswith('.provenance.json')]
    result.append(Step('world.brinecove.placements', [Python(placement_script, (
        '--rim', str(rim), '--source-library', str(library), '--output', str(placements)))],
        inputs=[*local_imports(placement_script, (WORLD, REGIONS)), library, *model_inputs],
        needs=['world.brinecove.sources'], reads=['brinecove.rim_data'],
        products=[Product('brinecove.placements', (placements,))], cache=True,
        about='coastal instance transforms, independent of model geometry/export identities'))
    return result


def assembly_step(out, *, plant_products):
    script = REGION / 'assemble.py'
    parents = ['SM_BC_' + key for key, _ in COMPONENTS] + ['SM_BC_Ground']
    parents.extend('SM_BC_Hero_' + ''.join(part.title() for part in slug.split('-')) for slug in HEROES)
    arguments = ['--out', str(out)]
    for key in parents: arguments.extend(('--parent', key))
    for slug in HEROES: arguments.extend(('--hero', slug))
    return Step('world.brinecove', [Python(script, tuple(arguments))],
        inputs=[*local_imports(script, (WORLD, REGIONS)), GAME / 'assets/brinecove/textures',
                REGION / 'foliage_catalog.json', REGION / 'foliage_models'],
        reads=['brinecove.atomic', 'brinecove.placements',
               *('brinecove.hero_materials.' + slug for slug in HEROES), *plant_products],
        products=[Product('brinecove.library', (out / 'brinecove/glb', out / 'brinecove/textures',
            out / 'brinecove/runtime.json', out / 'brinecove/build-report.json'))], cache=True,
        about='compose separate bounded coastal meshes and instances without geometry joins')
