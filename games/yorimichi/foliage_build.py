"""Independent foliage exports and native package owners for the Yorimichi recipe."""
import importlib.util
import json
from pathlib import Path

from atelier import build_inputs, unreal_modules
from atelier.build import Batch, Blender, Product, Step, UnrealScript

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
SCRIPTS = GAME / 'unreal/Scripts'


def source_module(name):
    spec = importlib.util.spec_from_file_location('yorimichi_' + name, WORLD / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


catalog = source_module('asset_catalog')
material_specs = source_module('material_specs')


def native_product(name, content, packages, *, extra=()):
    """Packages may have optional bulk/export companions; absence is part of their identity."""
    roots = tuple(content / (package.removeprefix('/Game/') + '.uasset') for package in packages)
    sidecars = tuple(root.with_suffix(suffix) for root in roots for suffix in ('.uexp', '.ubulk'))
    return Product(name, (*roots, *extra), optional_paths=sidecars)


def world_steps(ctx):
    script = WORLD / 'build_foliage_lods.py'
    code = build_inputs.local_imports(script, (WORLD, WORLD / 'regions'))
    steps = []
    for name in catalog.FOLIAGE:
        spec_path = catalog.SPEC_ROOT / (name + '.json')
        spec = json.loads(spec_path.read_text())
        textures = sorted({material_specs.MATERIALS[slot]['texture'] for slot in spec['materials']
                           if 'texture' in material_specs.MATERIALS[slot]})
        steps.append(Step(
            'world.foliage.' + name,
            [Blender(script, (name,), threads=3, factory_startup=True, env=(('PYTHONHASHSEED', '0'),))],
            inputs=[*code, spec_path, *(ctx.out / 'textures' / filename for filename in textures)],
            after=['world.textures'],
            products=[Product('foliage.' + name + '.source', (ctx.out / 'foliage' / name,))],
            toolchain=True, batch=Batch('foliage exports'),
            heavy=True, about=f'{name}: LOD0, distant levels, collision and import metadata'))
    # Retain the familiar aggregate selector without feeding it into the world import.
    steps.append(Step('world.foliage_lods', [], after=[step.name for step in steps],
                      about='all independent foliage exports'))
    return steps


def unreal_steps(ctx, modules, engine_inputs):
    content = GAME / 'unreal/Content'
    common = [*engine_inputs, GAME / 'unreal/Config']
    shared = 'materials.shared'
    script = SCRIPTS / 'shared_materials.py'
    steps = [Step(
        'unreal.materials', [UnrealScript(script, 'SHARED MATERIALS COMPLETE', modules=modules)],
        inputs=[*build_inputs.local_imports(script, (WORLD,)), *common,
                *(ctx.out / 'textures' / filename for filename in catalog.TEXTURES)],
        after=['world.textures', 'unreal.compile'], needs=unreal_modules.needs(modules),
        products=[native_product(shared, content, catalog.shared_packages()),
                  Product('materials.foliage_interface', (ctx.out / 'materials/foliage-interface.json',))],
        heavy=True, about='shared textures, material graphs and stable parameter collections')]
    script = SCRIPTS / 'import_foliage.py'
    code = build_inputs.local_imports(script, (WORLD,))
    for name in catalog.FOLIAGE:
        steps.append(Step(
            'unreal.foliage.' + name,
            [UnrealScript(script, 'FOLIAGE IMPORT COMPLETE ' + name, null_rhi=True, modules=modules,
                          env=(('ATELIER_FOLIAGE', name),),
                          args=('-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0',))],
            inputs=[*code, *common], after=['unreal.compile'], needs=unreal_modules.needs(modules),
            reads=['foliage.' + name + '.source', 'materials.foliage_interface'], references=[shared],
            products=[native_product('foliage.' + name + '.native', content, ['/Game/Japan/Assets/' + name],
                                     extra=(content / 'Japan/FoliageLODs' / name,
                                            ctx.out / 'imports/foliage' / (name + '.json')))],
            batch=Batch('foliage imports', runtime_env=('ATELIER_FOLIAGE',)),
            heavy=True, about=f'{name}: import only its package and authored LOD chain'))
    return steps
