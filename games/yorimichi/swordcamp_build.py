"""Independently cached logical SwordCamp constructors and atomic exports."""
import importlib.util
import json
from pathlib import Path

from atelier.atomic_files import atomic_json
from atelier.build import Call, Product, Step
from atelier.build_inputs import local_imports
from atelier.export_assembly import Item, assemble, runtime_inputs

GAME = Path(__file__).resolve().parent
REGION = GAME / 'world/regions/swordcamp'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def steps(ctx):
    graph = load('swordcamp_atomic_graph', GAME / 'region_exports.py')
    catalogue = load('swordcamp_atomic_catalogue', REGION / 'catalogue.py')
    assets = []
    for key, (module, function, parameters) in catalogue.ASSETS.items():
        builder = REGION / 'parts' / (module + '.py')
        assets.append(graph.LogicalAsset(key, REGION / 'plan_asset.py',
            args=('--asset', key, '--builder', module, '--function', function,
                  '--parameters', json.dumps(parameters, sort_keys=True, separators=(',', ':'))),
            inputs=tuple(local_imports(builder, (GAME / 'world', GAME / 'world/regions')))))
    result = graph.steps(ctx, region='swordcamp', assets=assets)
    root = ctx.out / 'swordcamp'
    atomic = ctx.out / 'atomic_regions/swordcamp'
    def finish(ctx, log):
        value = json.loads((atomic / 'assets/manifest.json').read_text())
        parents = json.loads((atomic / 'logical-pieces.json').read_text())['parents']
        # Equipment/runtime identities remain unchanged. An unexpected oversized item
        # refuses here until its receiving owner explicitly supports logical children.
        if any(children != [parent] for parent, children in parents.items()):
            raise ValueError('SwordCamp logical child requires receiving ownership migration')
        rows = value['exports']
        expected = set(catalogue.ASSETS)
        if {row['asset'] for row in rows} != expected:
            raise ValueError('SwordCamp requires the complete current logical equipment library')
        inputs = [Item(row['asset'], ctx.out / 'exports/world.swordcamp.export' / row['asset']) for row in rows]
        published = assemble(inputs, root / 'fbx')
        manifest = {row['asset']: dict(polygons=row['metadata']['polygons'],
                    colliders=row['metadata']['collision_hulls']) for row in published['exports']}
        atomic_json(root / 'manifest.json', manifest)
        log.write(f'SwordCamp: {len(manifest)} complete independent exports\n')
    result.append(Step('world.swordcamp', [Call('publish swordcamp', finish)],
        inputs=[Path(__file__), REGION / 'catalogue.py', *runtime_inputs()], reads=['swordcamp.atomic'],
        products=[Product('swordcamp.meshes', (root / 'fbx', root / 'manifest.json'))],
        about='assemble the complete independently cached equipment library'))
    return result
