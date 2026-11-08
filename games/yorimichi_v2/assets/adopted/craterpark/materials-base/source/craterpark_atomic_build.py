"""CraterPark's validated canonical course projection and independent atomic exporters."""
import importlib.util
import json
import os
from pathlib import Path
from atelier.build import Call, Product, Python, Step
from atelier.build_inputs import local_imports
from atelier.export_manifest import real_directory

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
REGIONS = WORLD / 'regions'
REGION = REGIONS / 'craterpark/v2'


def load(label, path):
    spec = importlib.util.spec_from_file_location(label, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def inventory(root):
    real_directory(root)
    path = root / 'inputs.json'
    if not os.path.lexists(path):
        return []
    if path.is_symlink():
        raise ValueError('Linked canonical course inventory')
    value = json.loads(path.read_text())
    if value.get('schema') != 1 or value.get('complete') is not True or not value.get('assets'):
        raise ValueError('Incomplete canonical course inventory')
    from atelier.export_manifest import name
    rows = value['assets']
    if len({name(r['name']).casefold() for r in rows}) != len(rows):
        raise ValueError('Duplicate logical course owners')
    if any(r['packet'] != r['name'] + '.npz' or r['kind'] not in ('render','collision','seed') for r in rows):
        raise ValueError('Foreign logical course packet')
    return rows


def steps(ctx):
    projected = ctx.out / 'craterpark-inputs'
    script = REGION / 'atomic_inputs.py'
    config = load('crater_atomic_selection', REGION / 'v4_config.py')
    selection = config.input_paths()
    legacy_ground = []
    if not config.selected():
        source = GAME / 'assets/craterpark'
        scene = json.loads((source / 'scene.json').read_text())
        legacy_ground = [source / m['npz'] for m in scene['meshes']
                         if m['role'] == 'mountain' and not m['helper']]
    result = [Step('world.craterpark.inputs', [Python(script, ('--source',
        str(ctx.out / 'craterpark/v2/geometry.npz'), '--output', str(projected)))],
        inputs=[*local_imports(script, (WORLD, REGIONS)), *selection], needs=['world.craterpark_geometry'],
        products=[Product('craterpark.source_inputs', (projected,))], cache=True, replan=True,
        about='project validated canonical course into independently consumed geometry data before exports')]
    rows = inventory(projected)
    assembly_product = Product('craterpark.library', tuple(ctx.out / 'craterpark' / p for p in ('fbx','build.json','park.json')))
    if not rows:
        def incomplete(ctx, log):
            raise ValueError('Canonical CraterPark projection must complete and replan before assembly')
        result.append(Step('world.craterpark', [Call('cold course assembly refusal', incomplete)],
            needs=['world.craterpark.inputs'], products=[assembly_product]))
        return result
    graph = load('craterpark_atomic_graph', GAME / 'region_exports.py')
    assets = []
    for row in rows:
        metadata = ctx.out / 'craterpark-data' / (row['name'] + '.json')
        assets.append(graph.LogicalAsset(row['name'], REGION / 'plan_asset.py',
            args=('--input', str(projected / row['packet']), '--metadata', str(metadata)),
            inputs=(projected / row['packet'],),
            products=(Product('craterpark.metadata.' + row['name'], (metadata,)),)))
    result.extend(graph.steps(ctx, region='craterpark', assets=assets, after=['world.craterpark.inputs']))
    script = REGION / 'assemble.py'
    result.append(Step('world.craterpark', [Python(script, ('--out', str(ctx.out)))],
        inputs=[*local_imports(script, (WORLD, REGIONS)), GAME / 'assets/craterpark/scene.json',
                GAME / 'assets/craterpark/drop-in.json', *selection, *legacy_ground],
        reads=['craterpark.atomic', 'craterpark.source_inputs', *('craterpark.metadata.' + r['name'] for r in rows)],
        products=[assembly_product], cache=True, about='assemble separate park meshes, placements and original course metadata'))
    return result
