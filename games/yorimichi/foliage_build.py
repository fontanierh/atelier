"""Independent foliage exports and native package owners for the Yorimichi recipe."""
import importlib.util
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=64)
def _read_spec(path, mtime_ns, size):
    return json.loads(Path(path).read_text())

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
    from atelier.build import Python
    from atelier import export_tasks
    import sys
    sys.path.insert(0,str(GAME))
    import foliage_source_products as products
    product_code=build_inputs.local_imports(Path(products.__file__))
    source=WORLD/'foliage_selected_source.py';exporter=WORLD/'export_foliage_piece.py'
    source_code=build_inputs.local_imports(source,(WORLD,WORLD/'regions'))
    steps=[]
    for name in catalog.FOLIAGE:
        spec_path=catalog.SPEC_ROOT/(name+'.json');st=spec_path.stat();spec=_read_spec(spec_path,st.st_mtime_ns,st.st_size)
        rows,policy=products.definition_rows(name,spec,material_specs.MATERIALS)
        definitions=ctx.out/'foliage-definitions'/name;data=ctx.out/'foliage-source'/name
        textures=sorted({ctx.out/'textures'/value['texture'] for value in rows[name]['materials'].values() if value.get('texture')})
        steps.append(Step('world.foliage.definitions.'+name,
            [Python(Path(products.__file__),('project','--kind',name,'--spec',str(spec_path),
                '--materials',str(WORLD/'material_specs.py'),'--output',str(definitions)))],
            inputs=[Path(__file__),*product_code,WORLD/'material_specs.py',spec_path],cache=True,
            products=[*(Product('foliage.definition.'+key,(definitions/(key+'.json'),)) for key in rows),
                      Product('foliage.policy.'+name,(definitions/'policy.json',))]))
        for key,row in rows.items():
            args=['--definition',str(definitions/(key+'.json')),'--output',str(data)]
            reads=['foliage.definition.'+key]
            if row['mode'] in ('seed','crown') or row.get('level',0)>0:
                args+=['--palette',str(data/(name+'.palette.json'))];reads+=['foliage.palette.'+name]
            if row['mode']=='crown' or row.get('level',0)>0 and row['generator']!='grass_tuft':
                args+=['--bounds',str(data/(name+'.bounds.json'))];reads+=['foliage.bounds.'+name]
            if row['mode']=='crown':
                last=f'{name}_LOD{len(spec["screen_sizes"])-1}'
                args+=['--last',str(data/(last+'.npz')),'--last-materials',str(data/(last+'.materials.json'))]
                reads+=['foliage.payload.'+last]
            outputs=[Product('foliage.payload.'+key,(data/(key+'.npz'),data/(key+'.materials.json'))),
                     Product('foliage.report.'+key,(data/(key+'.report.json'),))]
            if key==name:
                outputs += [Product('foliage.bounds.'+name,(data/(name+'.bounds.json'),)),
                            Product('foliage.palette.'+name,(data/(name+'.palette.json'),)),
                            Product('foliage.base.'+name,(data/(name+'.base.json'),))]
            steps.append(Step('world.foliage.source.'+key,[Blender(source,tuple(args),threads=3,factory_startup=True,env=(('PYTHONHASHSEED','0'),))],
                inputs=[*source_code,*textures],reads=reads,after=['world.textures'],products=outputs,
                cache=True,toolchain=True,batch=Batch('foliage selected sources'),heavy=True,
                about='one seeded authored foliage source; explicit pre-export bounds/crown dependencies'))
            steps += export_tasks.steps(ctx,prefix='world.foliage.export',assets=[export_tasks.Asset(key,data/(key+'.npz'))],
                script=exporter,inputs=[data/(key+'.materials.json'),*textures],reads=['foliage.payload.'+key],after=['world.textures'])
        steps.append(Step('world.foliage.'+name,
            [Python(Path(products.__file__),('assemble','--kind',name,'--policy',str(definitions/'policy.json'),'--output',str(ctx.out)))],
            inputs=product_code,
            reads=['foliage.policy.'+name,'foliage.base.'+name,*('foliage.report.'+key for key in rows),
                   *('world.foliage.export.'+key for key in rows)],
            products=[Product('foliage.'+name+'.source',(ctx.out/'foliage'/name,))],cache=True,
            about='strict complete file-only foliage assembly with unchanged native API'))
    steps.append(Step('world.foliage_lods',[],after=['world.foliage.'+name for name in catalog.FOLIAGE],
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
