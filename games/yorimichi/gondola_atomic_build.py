"""Selected Gondola source/query plans, bounded exports and original complete audits.

The central recipe calls kit_steps(ctx), query_steps(ctx) and site_steps(ctx),
then the existing service/native actions with their complete helper closures.
"""
import importlib.util
import json
from pathlib import Path

from atelier.build import Blender, Call, Product, Step, DeferredInputs
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
        heavy=True,cache=True,toolchain=True,about='source-only exact primitive commands and pre-export queries; no mesh generation')]
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
            heavy=True,cache=True,toolchain=True,about='one original authored collision file and every whole UCX hull'))
    result.append(Step('world.gondola_kit.audit',[Blender(actions,('audit','--input',str(queries),'--output',str(folder)),threads=3,factory_startup=True)],
        inputs=[*local_imports(actions,(WORLD,KIT)),*(KIT / name for name in parameters.BUILD_SOURCES),WORLD / 'solid_mesh.py',WORLD / 'walk_raster.py'],
        reads=['gondola_kit.query.'+key for key in render],
        products=[Product('gondola_kit.audit',(folder / 'kit-audit.json',folder / 'review',
                    *(folder / ('layout_'+key+'.json') for key in ('cabin','valley','rim','crater'))))],
        heavy=True,cache=True,toolchain=True,about='unchanged full closure/seating/contact/clearance/level-floor/budget/walking gates from exact queries'))
    textures = tuple(folder / name for name in parameters.product_files() if name.startswith('textures/'))
    result.append(Step('world.gondola_kit.textures',[Blender(REGION / 'kit_textures.py',('--output',str(folder / 'textures')),threads=3,factory_startup=True)],
        inputs=local_imports(REGION / 'kit_textures.py',(WORLD,KIT)),products=[Product('gondola_kit.textures',textures)],heavy=True,cache=True,toolchain=True,
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


def site_steps(ctx):
    """Replace the legacy world.gondola_site Step after ground/structures declarations."""
    graph = load('gondola_site_atomic_graph',GAME / 'region_exports.py')
    validation = load('gondola_site_atomic_validation',WORLD / 'gondola/validation.py')
    names = validation.network_layout().mesh_names()
    folder = ctx.out / 'gondola/world'; data = folder / 'source-data'; queries = folder / 'query-data'
    result = [Step('world.gondola_site.sources',[Blender(REGION / 'site_sources.py',
        ('--kit-queries',str(ctx.out / 'gondola/query-data'),'--output',str(data)),threads=3,factory_startup=True)],
        inputs=sorted({*local_imports(REGION / 'site_sources.py',(WORLD,KIT,GAME)),
                       *local_imports(REGION / 'site.py',(WORLD,KIT,GAME)),
                       ctx.out / 'gondola/world/ground.npz',ctx.out / 'gondola/world/ground.json',
                       ctx.out / 'terrain/HD_Terrain/final.npz',ctx.out / 'terrain/HD_NorthMountains/final.npz',
                       ctx.out / 'gondola/world/ground-sources.json'}),
        reads=['gondola_kit.audit','gondola.ground',*('gondola_kit.query.GD_Cabin'+suffix for suffix in ('','Hanger','Grip','DoorLeft','DoorRight'))],
        needs=['world.gondola_ground'],
        products=[Product('gondola_site.source.'+key,(data / (key+'.json'),)) for key in (*names,'fit')],
        heavy=True,cache=True,toolchain=True,about='source-only final-ground fitting, selected primitive commands and original near-rope tolerance gates')]
    assets = [graph.LogicalAsset(key,REGION / 'plan_site.py',
        args=('--asset',key,'--source',str(data / (key+'.json')),'--queries',str(queries / (key+'.json'))),
        inputs=tuple(local_imports(REGION / 'plan_site.py',(WORLD,KIT,GAME))),
        reads=('gondola_site.source.'+key,),
        products=(Product('gondola_site.query.'+key,(queries / (key+'.json'),)),)) for key in names]
    result.extend(graph.steps(ctx,region='gondola_site',assets=assets))
    result.append(Step('world.gondola_site.audit',[Blender(REGION / 'audit_site.py',threads=3,factory_startup=True)],
        inputs=sorted({*local_imports(REGION / 'audit_site.py',(WORLD,KIT,GAME)),
            *local_imports(REGION / 'site.py',(WORLD,KIT,GAME)),*validation.SITE_CODE,
            *(ctx.out / name for name in ('gondola/world/ground.npz','gondola/world/ground.json',
                'gondola/world/structures.npz','gondola/world/structures.json','craterpark/v2/geometry.npz','zeppelin/manifest.json'))}),
        needs=['world.gondola_ground','world.gondola_structures','world.craterpark_geometry','world.zeppelin'],
        reads=['gondola.kit','gondola.ground','gondola.structures','gondola_site.atomic','gondola_site.source.fit',
            *('gondola_site.query.'+key for key in names),
            *('gondola_kit.query.'+key for key in kit_names()[1])],
        products=[Product('gondola_site.audit',(folder / 'site-audit.json',))],
        heavy=True,cache=True,toolchain=True,about='original complete fitted geometry/contact/ground/riding/structure/headroom/flight audit from source queries and actual bounded FBX'))
    def assemble(ctx,log):
        products = load('gondola_site_file_products',GAME / 'gondola_site_products.py')
        products.assemble(ctx.out)
        log.write('Complete fitted Gondola assembled from bounded files; original audits retained\n')
    result.append(Step('world.gondola_site',[Call('assemble fitted Gondola files',assemble)],
        inputs=[Path(__file__),GAME / 'gondola_site_products.py',*validation.SITE_CODE,*export_assembly.runtime_inputs()],
        reads=['gondola_site.atomic','gondola_site.audit','gondola_site.source.fit',
               *('gondola_site.query.'+key for key in names),
               *('gondola_kit.query.'+key for key in kit_names()[1])],
        products=[Product('gondola.site',(folder / 'site.json',folder / 'atomic-assets'))],replan=True,
        about='file-only complete fitted supports/access/towers/three-LOD rope assembly'))
    return result


def site_native_names(out):
    """Cold discovery expands again after world.gondola_site publishes complete membership."""
    path=Path(out) / 'gondola/world/site.json'
    if not path.exists():return ()
    export_manifest.real_directory(path.parent)
    if path.is_symlink() or not path.is_file():raise ValueError('Invalid Gondola native discovery manifest')
    value=json.loads(path.read_text())
    if value.get('atomic') is not True:return ()
    return tuple(export_manifest.name(piece['name']) for row in value['exports'] for piece in row['pieces']
                 if not any(token in piece['name'] for token in ('_Rope_LOD1','_Rope_LOD2')))


def query_steps(ctx):
    """Replace the four legacy ground/structure input+probe Steps, before site_steps."""
    from atelier.build import Python
    source = load('gondola_preexport_source_projection',WORLD / 'gondola/source_inputs.py')
    ground = load('gondola_final_query_inputs',WORLD / 'gondola/inputs.py')
    structures = load('gondola_final_structure_inputs',WORLD / 'gondola/structures.py')
    folder = ctx.out / 'gondola/world'
    script = WORLD / 'gondola/source_inputs.py'
    selected = source.ground_projection(ctx.out)
    result = []
    for kind in ('ground','structures'):
        reads = (['belmonte.scene.runtime','belmonte.prepared_materials',
                  *('belmonte_models.geometry.'+key for key in source.structure_keys())]
                 if kind == 'structures' else [])
        deferred = ([DeferredInputs('gondola-selected-structure-sources',source.structure_paths,(ctx.out,),support=(script,))]
                    if kind=='structures' else [])
        result.append(Step('world.gondola_'+kind+'_sources',[Python(script,(kind,'--out',str(ctx.out)))],
            inputs=[*local_imports(script,(WORLD,KIT,GAME)),GAME / 'assets/belmonte/source.json',
                    WORLD / 'regions/belmonte/layout.py'],reads=reads,deferred_inputs=deferred,
            products=[Product('gondola.'+kind+'_sources',(folder / (kind+'-sources.json'),))],
            cache=True,heavy=kind=='structures',about='narrow explicit '+kind+' source projection before render exports'))
    digest = load('gondola_query_digest',GAME / 'export_digest.py')
    for kind,helper in (('ground',ground),('structure',structures)):
        # Legacy task identities stay stable; their consumed data direction changes.
        product = 'ground' if kind == 'ground' else 'structures'
        target = ctx.out / ('digests/world.gondola.'+product+'.json')
        collector = helper.snapshot if kind == 'ground' else helper.inputs
        def record(ctx,log,target=target,collector=collector):digest.record(target,collector(ctx.out),log)
        reads = ['gondola.'+product+'_sources']
        if kind == 'ground':
            reads += ['hidamari.query.HD_NorthTrail','terrain.HD_Terrain.final','terrain.HD_NorthMountains.final',
                      *('belmonte.final_surface.'+row['name'] for row in selected['groups'])]
        code = list(helper.CODE.values()) if isinstance(helper.CODE,dict) else [GAME.parents[1] / name for name in helper.CODE]
        result.append(Step('world.gondola_'+kind+'_inputs',[Call('current Gondola '+product+' source identities',record)],
            inputs=sorted({*code,*local_imports(Path(helper.__file__),(WORLD,KIT,GAME))}),reads=reads,deferred_inputs=[DeferredInputs('gondola-'+product+'-sources',helper.paths,(ctx.out,),
                support=(WORLD / 'gondola' / ('inputs.py' if kind=='ground' else 'structures.py'),))],
            outputs=[target],cutoff=True,about='only current pre-export '+product+' query identities'))
        probe = WORLD / 'gondola' / ('probe.py' if kind=='ground' else 'structure_probe.py')
        command=(Blender(probe,threads=3,factory_startup=True) if kind=='ground' else Python(probe))
        result.append(Step('world.gondola_'+product,[command],
            inputs=sorted({*local_imports(probe,(WORLD,KIT,GAME)),*code}),
            needs=['world.gondola_'+kind+'_inputs'],products=[Product('gondola.'+product,
                (folder / (product+'.npz'),folder / (product+'.json')))],cache=True,heavy=True,toolchain=kind=='ground',
            about='exact source triangle/frame extraction; no rendered FBX/GLB reads'))
    return result


def service_inputs():
    return local_imports(WORLD / 'gondola/service.py',(WORLD,KIT,GAME))


def native_inputs():
    scripts=GAME / 'unreal/Scripts'
    validation=load('gondola_native_source_closure',WORLD / 'gondola/validation.py')
    return sorted({*local_imports(scripts / 'import_gondola.py',(WORLD,KIT,GAME,scripts)),*validation.SITE_CODE})
