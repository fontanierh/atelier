"""Independent selected Gondola kit plans, bounded exports and original full audits.

The central gondola recipe replaces only its legacy world.gondola_kit step with
kit_steps(ctx). Existing final-ground/site/service/import steps retain their gates.
"""
import importlib.util
import json
from pathlib import Path

from atelier.build import Blender, Call, Product, Step
from atelier import export_assembly, export_manifest
from atelier.build_inputs import local_imports
from atelier.atomic_files import atomic_json

GAME = Path(__file__).resolve().parent
WORLD = GAME / 'world'
KIT = GAME / 'assets/vehicles/gondola'
REGION = WORLD / 'regions/gondola'


def load(key, path):
    spec = importlib.util.spec_from_file_location(key,path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def kit_names():
    parameters = load('gondola_atomic_parameters', KIT / 'params.py')
    names = parameters.asset_names()
    return parameters, tuple(key for key in names if not key.endswith('_Collision')), tuple(key for key in names if key.endswith('_Collision'))


def assemble_kit(out):
    """@cc [owner:fontanierh,label:correctness] gondola-complete-file-only-kit
    Assembly MUST require the complete independently exported kit membership, original
    successful full audits and all authored collision hulls before publication. It MUST
    copy files only, never reconstruct geometry. Bounded kit parents currently retain
    their exact names; an unexpected subdivision MUST refuse until native/runtime
    membership is explicitly migrated rather than silently dropping its children.
    """
    out = Path(out); folder = out / 'gondola'
    parameters, render, collision = kit_names()
    audit = json.loads((folder / 'kit-audit.json').read_text())
    if audit.get('failures') != [] or audit.get('soft_fail') is not False or audit.get('walk',{}).get('all_pass') is not True:
        raise ValueError('Gondola complete original audits are missing or failed')
    if audit.get('source_hash') != parameters.source_hash(): raise ValueError('Gondola original audit source is stale')
    assembly = json.loads((out / 'atomic_regions/gondola_kit/logical-pieces.json').read_text())
    if assembly.get('schema') != 1 or set(assembly['parents']) != set(render):
        raise ValueError('Incomplete Gondola kit render membership')
    audited = dict(audit['pieces']['cabin']['meshes'])
    audited.update({key: row['mesh'] for key,row in audit['pieces']['towers'].items()})
    for kind in ('valley','rim','crater'): audited.update(audit['pieces']['station_'+kind]['meshes'])
    if set(audited) != set(render): raise ValueError('Incomplete original Gondola audited mesh roster')
    items = []
    for key in render:
        if assembly['parents'][key] != [key]:
            raise ValueError('Gondola kit subdivision requires explicit native/runtime migration: '+key)
        item = export_assembly.Item(key,out / 'exports/world.gondola_kit.export' / key)
        receipt = export_manifest.validate(item.root,key=key)
        if (receipt['triangles'] != assembly['ownership'][key]['source_triangles']
                or receipt['triangles'] != audited[key]['triangles']):
            raise ValueError('Gondola kit count differs from its logical source')
        items.append(item)
    for key in collision:
        item = export_assembly.Item(key,out / 'exports/world.gondola_kit.collision' / key)
        receipt = export_manifest.validate(item.root,key=key)
        source = json.loads((folder / 'source-data' / (key+'.json')).read_text())
        if (receipt['metadata']['collision_hulls'] != len(source['proxies']) or not source['proxies']
                or receipt['metadata']['source_sha256'] != export_manifest.sha(folder / 'source-data' / (key+'.json'))):
            raise ValueError('Gondola authored collision membership differs')
        items.append(item)
    result = export_assembly.assemble(items,folder / 'assets')
    expected = parameters.product_files()
    for name in expected:
        if name == 'manifest.json': continue
        path = folder / name
        if path.is_symlink() or not path.is_file(): raise ValueError('Missing Gondola kit product: '+name)
    atomic_json(folder / 'atomic-manifest.json',assembly | dict(exports=result['exports']))
    atomic_json(folder / 'manifest.json',audit)


def kit_steps(ctx):
    graph = load('gondola_atomic_export_graph',GAME / 'region_exports.py')
    parameters, render, collision = kit_names()
    data = ctx.out / 'gondola/source-data'
    queries = ctx.out / 'gondola/query-data'
    folder = ctx.out / 'gondola'
    source_code = [KIT / (name+'.py') for name in ('cabin','tower','stations','rope','params','solid','commands')]
    result = [Step('world.gondola_kit.sources', [Blender(REGION / 'kit_sources.py',('--output',str(data)),threads=3,factory_startup=True)],
        inputs=sorted({*local_imports(REGION / 'kit_sources.py',(WORLD,KIT)),
            *(path for module in source_code for path in local_imports(module,(WORLD,KIT)))}),
        products=[Product('gondola_kit.source.'+key,(data / (key+'.json'),)) for key in (*render,*collision,'audit')],
        heavy=True,cache=True,about='source-only exact primitive commands and pre-export queries; no mesh generation')]
    assets = [graph.LogicalAsset(key,REGION / 'plan_kit.py',
        args=('--asset',key,'--source',str(data / (key+'.json')),'--queries',str(queries / (key+'.json'))),
        inputs=tuple(local_imports(REGION / 'plan_kit.py',(WORLD,KIT))),
        reads=('gondola_kit.source.'+key,),
        products=(Product('gondola_kit.query.'+key,(queries / (key+'.json'),)),)) for key in render]
    result.extend(graph.steps(ctx,region='gondola_kit',assets=assets))
    actions = REGION / 'kit_actions.py'
    for key in collision:
        root = ctx.out / 'exports/world.gondola_kit.collision' / key
        result.append(Step('world.gondola_kit.collision.'+key,[Blender(REGION / 'export_kit_collision.py',('--input',str(data / (key+'.json')),
            '--asset',key,'--output',str(root)),threads=3,factory_startup=True)],
            inputs=local_imports(REGION / 'export_kit_collision.py',(WORLD,KIT)),
            reads=['gondola_kit.source.'+key],products=[Product('gondola_kit.collision.'+key,(root,))],
            heavy=True,cache=True,about='one original authored collision file and every whole UCX hull'))
    result.append(Step('world.gondola_kit.audit',[Blender(actions,('audit','--input',str(queries),'--output',str(folder)),threads=3,factory_startup=True)],
        inputs=[*local_imports(actions,(WORLD,KIT)),*(KIT / name for name in parameters.BUILD_SOURCES),WORLD / 'solid_mesh.py',WORLD / 'walk_raster.py'],
        reads=['gondola_kit.query.'+key for key in render],
        products=[Product('gondola_kit.audit',(folder / 'kit-audit.json',folder / 'review',
                    *(folder / ('layout_'+key+'.json') for key in ('cabin','valley','rim','crater'))))],
        heavy=True,cache=True,about='unchanged full closure/seating/contact/clearance/level-floor/budget/walking gates from exact queries'))
    textures = tuple(folder / name for name in parameters.product_files() if name.startswith('textures/'))
    result.append(Step('world.gondola_kit.textures',[Blender(REGION / 'kit_textures.py',('--output',str(folder / 'textures')),threads=3,factory_startup=True)],
        inputs=local_imports(REGION / 'kit_textures.py',(WORLD,KIT)),products=[Product('gondola_kit.textures',textures)],heavy=True,cache=True,
        about='original procedural timber maps, independent from geometry'))
    def assemble(ctx,log):
        assemble_kit(ctx.out)
        log.write('Gondola kit assembled from independently cached files and original successful audits\n')
    result.append(Step('world.gondola_kit',[Call('assemble complete Gondola kit',assemble)],
        inputs=[Path(__file__),KIT / 'params.py',*export_assembly.runtime_inputs()],
        reads=['gondola_kit.atomic','gondola_kit.audit','gondola_kit.textures',
            *('gondola_kit.collision.'+key for key in collision),*('gondola_kit.source.'+key for key in collision)],
        products=[Product('gondola.kit',(folder / 'manifest.json',folder / 'atomic-manifest.json',folder / 'assets'))],
        about='complete file-only kit assembly; independent original collision exactly once'))
    return result
