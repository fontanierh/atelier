"""Independent foliage exports and native package owners for the Yorimichi recipe."""
import importlib.util
import json
from pathlib import Path

from atelier import build_inputs, unreal_modules
from atelier.build import Batch, Blender, Product, Step, UnrealScript
from atelier.build import DeferredInputs
from atelier.native_protocol import runtime_files as native_runtime_files

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
SCRIPTS = GAME / 'unreal/Scripts'


def system_inputs(content):
    """Discovery is content-dependent: new regional foliage invalidates the registry.

    The derivative owner's own packages and Data must never become its inputs.
    Native source packages include their material/texture dependencies; per-asset
    fingerprints inside the adapter avoid rebuilding unchanged representations.
    """
    return sorted(p for p in Path(content).rglob('*') if p.is_file()
                  and p.suffix in ('.uasset', '.uexp', '.ubulk')
                  and p.relative_to(content).parts[0] not in ('FoliageSystem', 'Data'))


def system_packages(content):
    spec=importlib.util.spec_from_file_location('yorimichi_foliage_system',GAME/'foliage_system.py')
    kernel=importlib.util.module_from_spec(spec);spec.loader.exec_module(kernel)
    return kernel.package_inventory(content)


def verify_system(content, report_path):
    """A directory's existence cannot certify its mesh/material packages."""
    try:
        report=json.loads(Path(report_path).read_text())
        registry=json.loads((Path(content)/'Data/foliage_system/registry.json').read_text())
        expected=report['packages']
        return (report==registry and report['version']==1 and bool(report['assets'])
                and bool(expected) and system_packages(content)==expected)
    except (OSError,ValueError,KeyError,TypeError):
        return False


def system_step(ctx, prerequisites):
    content = GAME/'unreal/Content'
    command = UnrealScript(SCRIPTS/'build_foliage_system.py', 'FOLIAGE SYSTEM COMPLETE',
                           modules=('YorimichiFoliagePreparation',), null_rhi=True, memory_gib=20,
                           args=('-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0',))
    command.timeout = 3600
    command.progress = 25
    return Step('unreal.foliage_system',
                [command],
                inputs=[GAME/'foliage_system.py', WORLD/'foliage_roles.py', SCRIPTS/'build_foliage_system.py', SCRIPTS/'atmosphere.py',
                        SCRIPTS/'see_through.py', SCRIPTS/'foliage_material.py', SCRIPTS/'foliage_variant_validation.py',
                        GAME.parents[1]/'platform/studio/atelier/mesh_geometry.py', *native_runtime_files(), GAME/'unreal/Config',
                        *(GAME/'unreal/Source/YorimichiFoliagePreparation'/name for name in
                          ('FoliagePreparation.cpp', 'FoliagePreparation.h', 'MeshGeometrySnapshot.cpp')),
                        ctx.out/'unreal-modules/YorimichiFoliagePreparation.json'],
                deferred_inputs=[DeferredInputs('foliage-source-packages', system_inputs, (content,),
                                                support=(GAME/'foliage_build.py',))],
                needs=[*prerequisites, *unreal_modules.needs(('YorimichiFoliagePreparation',))],
                outputs=[content/'FoliageSystem', content/'Data/foliage_system/registry.json',
                         ctx.out/'foliage_system/report.json', ctx.out/'foliage_system/preparation-counts.json'],
                verify=lambda:verify_system(content,ctx.out/'foliage_system/report.json'),
                heavy=True, about='all foliage: closed canopies, leaf fringes, shadow proxies and verified runtime registry')


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
    preflight = SCRIPTS / 'prepare_foliage.py'
    code = sorted(set(build_inputs.local_imports(script, (WORLD,)) +
                      build_inputs.local_imports(preflight, (WORLD,))))
    for name in catalog.FOLIAGE:
        steps.append(Step(
            'unreal.foliage.' + name,
            [UnrealScript(script, 'FOLIAGE IMPORT COMPLETE ' + name, null_rhi=True, modules=modules,
                          env=(('ATELIER_FOLIAGE', name), ('ATELIER_UNREAL_PREFLIGHT', str(preflight))),
                          args=('-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0',))],
            inputs=[*code, *common], after=['unreal.compile'], needs=unreal_modules.needs(modules),
            reads=['foliage.' + name + '.source', 'materials.foliage_interface'], references=[shared],
            products=[native_product('foliage.' + name + '.native', content, ['/Game/Japan/Assets/' + name],
                                     extra=(content / 'Japan/FoliageLODs' / name,
                                            ctx.out / 'imports/foliage' / (name + '.json')))],
            batch=Batch('foliage imports', runtime_env=('ATELIER_FOLIAGE',)),
            heavy=True, about=f'{name}: import only its package and authored LOD chain'))
    return steps
