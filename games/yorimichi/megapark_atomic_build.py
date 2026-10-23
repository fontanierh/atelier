"""Complete MegaPark logical source constructors and independent bounded exports."""
import importlib.util
import json
from pathlib import Path
from atelier.build import Batch, Blender, Product, Python, Step
from atelier.build_inputs import local_imports
from atelier.build_batch_source import support as batch_support

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
REGIONS = WORLD / 'regions'
REGION = REGIONS / 'megapark'
SOURCE = GAME / 'assets/megapark'


def load(label, path):
    spec = importlib.util.spec_from_file_location(label, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def catalogue():
    # Only source semantic metadata is used to select required logical constructors.
    import sys
    sys.path[:0] = [str(WORLD), str(REGIONS)]
    from megapark import plants, cars
    source = json.loads((SOURCE / 'map.json').read_text())
    models = [m for m in source['models'] if any(not plants.is_foliage(p) and not cars.is_car(m,p) for p in m['meshes'])]
    return source, models


def steps(ctx):
    graph = load('megapark_atomic_graph', GAME / 'region_exports.py')
    source, models = catalogue()
    from megapark import sign, cars, placement
    letters = ctx.out / 'megapark/letters.npz'
    letters_script = REGION / 'letters_data.py'
    result = [Step('world.megapark.letters_data', [Blender(letters_script, ('--output', str(letters)),
                   threads=3, factory_startup=True)],
        inputs=[*local_imports(letters_script, (WORLD, REGIONS)), *batch_support().values(), SOURCE / 'map.json',
                *(SOURCE / m['npz'] for m in source['models'] if m['asset_id'] == sign.MODEL), ctx.out / 'megapark/lettering/NotoSansJP-Black.ttf'],
        needs=['world.megapark_restyle'], products=[Product('megapark.letters_data', (letters,))],
        cache=True, heavy=True, batch=Batch('megapark logical geometry'), about='canonical lettering source/query data before mesh exports')]
    assets = []
    selected = [('SM_MP_' + m['asset_id'][2:], [SOURCE / m['npz']]) for m in models]
    for section in source['collision']:
        related = {sign.MODEL} if section['id'] == sign.SECTION else set()
        if section['id'] == cars.SECTION:
            related.update(cars.CARS)
        selected.append(('UC_MP_' + section['id'], [SOURCE / section['npz'],
            *(SOURCE / m['npz'] for m in source['models'] if m['asset_id'] in related)]))
    seam = [SOURCE / m['npz'] for m in source['models'] if m['asset_id'] in placement.SEAM or placement.is_park_model(m)]
    seam += [SOURCE / m['npz'] for m in source['collision'] if m['id'] == '715219D1D6FFC624_0']
    selected += [('SM_MP_Seam', seam), ('UC_MP_Seam', seam), ('SM_MP_ImportSeed', [])]
    for parent, inputs in selected:
        metadata = ctx.out / 'megapark-data' / (parent + '.json')
        assets.append(graph.LogicalAsset(parent, REGION / 'plan_asset.py',
            args=('--asset', parent, '--letters', str(letters), '--metadata', str(metadata)),
            inputs=(SOURCE / 'map.json', *inputs), reads=('megapark.letters_data',),
            products=(Product('megapark.metadata.' + parent, (metadata,)),)))
    result.extend(graph.steps(ctx, region='megapark', assets=assets))
    script = REGION / 'assemble.py'
    args = ['--out', str(ctx.out)]
    for parent, _ in selected:
        args.extend(('--parent', parent))
    result.append(Step('world.megapark', [Python(script, tuple(args))],
        inputs=[*local_imports(script, (WORLD, REGIONS)), SOURCE / 'map.json',
                *(SOURCE / m['npz'] for m in source['models']), *(SOURCE / m['npz'] for m in source['collision'])],
        reads=['megapark.atomic', *('megapark.metadata.' + p for p, _ in selected)],
        products=[Product('megapark.library', tuple(ctx.out / 'megapark' / p for p in
            ('fbx', 'build.json', 'park.json', 'white.png', 'black.png', 'normal.png')))], cache=True,
        about='complete separate park asset and placement assembly; no geometry joins'))
    return result
