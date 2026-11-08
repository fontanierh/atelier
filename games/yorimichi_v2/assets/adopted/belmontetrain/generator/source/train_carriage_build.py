"""Seven selected coach source owners, bounded independent primaries and file-only runtime assembly."""
import importlib.util
import json
from pathlib import Path

from atelier.build import Call, Blender, Product, Python, Step
from atelier.build_inputs import local_imports
from atelier import export_tasks, export_assembly, paths
from atelier.export_manifest import name, real_directory

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
TRAIN = WORLD / 'train'
TOOLS = GAME / 'tools'
ASSETS = GAME / 'assets/vehicles/belmonte-train'
COACHES = ('locomotive', 'tender', 'baggage-van', 'restaurant', 'first-class', 'second-class', 'brake-van')


def load(label, path):
    spec = importlib.util.spec_from_file_location(label, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def addon(*, required=True):
    # Source preparation binds the actual installed addon files in its ordinary
    # input/tool identity and passes their hashes for inprocess before/after checks.
    from atelier import engine
    from atelier.export_manifest import sha
    root = Path(engine.blender()).resolve().parent.parent / 'Resources'
    found = sorted(root.glob('*/scripts/addons_core/io_scene_gltf2'))
    if not found and not required: return {}, {}
    if len(found) != 1: raise ValueError('Ambiguous installed Blender glTF source')
    files = dict(exporter=found[0] / 'blender/exp/export.py', writer=found[0] / 'io/exp/export.py')
    return files, {key: sha(path) for key, path in files.items()}


def inventory(folder, coach):
    folder = Path(folder); path = folder / 'packets/inventory.json'
    if not path.exists(): return []
    real_directory(path.parent)
    if path.is_symlink() or not path.is_file(): raise ValueError('Linked selected coach inventory')
    value = json.loads(path.read_text())
    if value.get('schema') != 1 or value.get('complete') is not True or value.get('coach') != coach:
        raise ValueError('Incomplete or foreign selected coach inventory')
    rows = [(name(row['name']), folder / 'packets' / row['source']) for row in value['pieces']]
    if (not rows or len({key.casefold() for key, _ in rows}) != len(rows)
            or any(path.name != key + '.source' or path.parent != folder / 'packets' for key, path in rows)):
        raise ValueError('Escaping selected coach source membership')
    return rows


def steps(ctx):
    """@cc [owner:fontanierh,label:correctness;performance] selected-coach-source-and-runtime-graph
    Every coach MUST own its original complete constructor, atlas/fit/check closure and
    published query/mesh source before bounded independent planners and cached exports.
    A planner MUST read only its own packet bytes; a source-folder reference is ordering
    only, with the actual consumed packet declared as an input. Assembly MUST validate
    every current member and copy files only. Keep original authored LOD/material/node,
    door/pivot/boarding/collision/sockets and runtime filename policies.
    """
    query = TRAIN / 'carriage_request.py'; script = TRAIN / 'construct_carriage.py'
    query_code = local_imports(query, (WORLD, TOOLS, paths.STUDIO))
    selected_code = [*local_imports(script, (WORLD, TOOLS, paths.STUDIO)),
        *local_imports(TRAIN / 'carriage_source.py', (WORLD, TOOLS, paths.STUDIO)),
        *(TRAIN / file for file in ('build.py', 'collision.py', 'fittings.py', 'parts.py',
                                    'layout.py', 'textures.py', 'furniture.py', 'budgets.py', '__init__.py'))]
    # PT.atlas_key actually reads the complete raw layout/build/parts/fittings/
    # textures sources. Preserve that original gate; never pretend these reads
    # disappear merely because the constructor's data request is projected.
    chars = GAME / 'assets/characters'
    characters = sorted(chars.glob('*/character.toml'))
    optional = [path.with_name('adventure.toml') for path in characters]
    query_inputs = [*query_code, chars / 'pipeline/definition.py', *characters,
                    ASSETS / 'planning/furniture-dimensions.json']
    source_inputs = [*selected_code, ASSETS / 'planning/furniture-dimensions.json', ASSETS / 'source.toml',
                     ASSETS / 'furniture', ASSETS / 'textures']
    addon_files, _ = addon(required=False)
    addon_path = ctx.out / 'belmonte-train-source-addon.json'
    def prepare_addon(ctx, log):
        from atelier.atomic_files import atomic_json
        _, identities = addon()
        atomic_json(addon_path, dict(schema=1, files=identities))
        log.write('Bound current installed carriage exporter/writer source identities\n')
    result = [Step('world.belmonte_train.addon', [Call('prepare current carriage source addon', prepare_addon)],
        inputs=[Path(__file__), *addon_files.values()],
        products=[Product('belmonte_train.addon', (addon_path,))],
        about='current installed finite pre-file source protocol, without launching Blender')]
    owners = []; assets = []; source_names = []
    for coach in COACHES:
        request = ctx.out / 'belmonte-train-requests' / (coach + '.json')
        request_product = 'belmonte_train.request.' + coach
        result.append(Step('world.belmonte_train.request.' + coach,
            [Python(query, ('--coach', coach, '--output', str(request)))], inputs=query_inputs,
            optional_inputs=optional, products=[Product(request_product, (request,))], cache=True,
            about='selected exact coach layout and capsule/adjacent-door query answers'))
        folder = ctx.out / 'belmonte-train-sources' / coach
        source_name = 'world.belmonte_train.source.' + coach; source_names.append(source_name)
        source_product = 'belmonte_train.source.' + coach; owners.append(source_product)
        def present(folder=folder, coach=coach):
            module = load('carriage_source_presence', GAME / 'train_carriage_products.py')
            return module.present(folder, coach)
        result.append(Step(source_name, [Blender(script, ('--request', str(request), '--coach', coach,
            '--output', str(folder), '--addon', str(addon_path)),
            threads=3, factory_startup=True)], inputs=[*source_inputs, GAME / 'train_carriage_products.py'],
            reads=[request_product, 'belmonte_train.addon'],
            products=[Product(source_product, (folder,))], cache=True, heavy=True, replan=True, verify=present,
            about='selected original coach, exact atlas and complete bounded service source packets'))
        for key, packet in inventory(folder, coach):
            plan = ctx.out / 'planned_exports/belmonte_train' / key
            plan_product = 'belmonte_train.geometry.' + key
            result.append(Step('world.belmonte_train.geometry.' + key, [Python(TRAIN / 'plan_carriage.py', (
                '--source', str(packet), '--asset', key, '--output', str(plan)))],
                inputs=[*local_imports(TRAIN / 'plan_carriage.py', (WORLD, TOOLS, paths.STUDIO)), packet],
                references=[source_product], products=[Product(plan_product, (plan,))], cache=True,
                about='only the selected complete source packet, preserving encoded hierarchy and attributes'))
            assets.append(export_tasks.Asset(key, plan / (key + '.glbdata'), '.glb'))
    if assets:
        exported = export_tasks.steps(ctx, prefix='world.belmonte_train.export', assets=assets,
            script=TRAIN / 'export_carriage.py', inputs=local_imports(TRAIN / 'export_carriage.py', (WORLD, TOOLS, paths.STUDIO)),
            runtime='python')
        for step, asset in zip(exported, assets): step.reads = ['belmonte_train.geometry.' + asset.key]
        result.extend(exported)
    def assemble(ctx, log):
        module = load('train_carriage_files', GAME / 'train_carriage_products.py')
        module.assemble(ctx.out)
        log.write('Assembled all seven coach bodies, doors, authored LODs and exact runtime metadata\n')
    destination = ctx.out / 'belmonte-train'
    # Furniture LOD baking and service own their later subdirectories. This
    # producer owns only the fitted input files and its explicit coach/texture trees.
    fitted = sorted((ASSETS / 'furniture').glob('*'))
    outputs = (destination / 'manifest.json', destination / 'service-meshes.json', destination / 'atomic',
               destination / 'textures', *(destination / coach for coach in COACHES),
               *(destination / 'furniture' / path.name for path in fitted))
    result.append(Step('world.belmonte_train', [Call('assemble selected train files', assemble)],
        inputs=[Path(__file__), GAME / 'train_carriage_products.py', ASSETS / 'source.toml',
                ASSETS / 'planning/furniture-dimensions.json', TRAIN / 'budgets.py',
                TRAIN / 'textures.py', *local_imports(GAME / 'train_carriage_products.py', (WORLD, TOOLS, paths.STUDIO)),
                *export_assembly.runtime_inputs()],
        reads=[*owners, *('world.belmonte_train.export.' + asset.key for asset in assets)],
        needs=source_names if not assets else [], products=[Product('belmonte_train.library', outputs)],
        about='complete file-only train library, signed shell/texture/fit gates and original service filenames'))
    return result
