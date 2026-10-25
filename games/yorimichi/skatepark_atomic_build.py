"""Validated pre-export skate data and separately cached selected pieces and roundtrips."""
import importlib.util
from pathlib import Path
from atelier.build import Batch,Blender,Product,Python,Step
from atelier.build_inputs import local_imports
from atelier.build_batch_source import support as batch_support

GAME=Path(__file__).resolve().parent;WORLD=GAME/'world';REGIONS=WORLD/'regions';REGION=REGIONS/'skatepark'
BOARD=('SM_SkateDeck','SM_SkateTruck','SM_SkateWheel')
PARK=('SM_SkatePier','SM_SkatePierPilings','SM_SkateParkFeatures','SM_SkatePath',
      'SM_SkateParkFurniture','SM_SkateParkPlanting','SM_SkateParkDecals')


def graph():
    spec=importlib.util.spec_from_file_location('skate_atomic_graph',GAME/'region_exports.py')
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def steps(ctx):
    G=graph();script=REGION/'prepare_atomic.py';data=ctx.out/'skatepark-data'
    inputs=local_imports(script,(WORLD,REGIONS))
    result=[Step('world.skatepark.material_geometry',[Python(script,('--kind','materials',
        '--textures',str(ctx.out/'skatepark/textures/textures.json'),'--output',str(data/'materials.json')))],
        inputs=inputs,reads=['skatepark.textures'],products=[Product('skatepark.material_geometry',(data/'materials.json',))],cache=True),
        Step('world.skatepark.ao',[Blender(script,('--kind','ao',*(arg for name in ('SM_SkatePier','SM_SkateParkFeatures','report') for arg in ('--file',name+'.json',str(data/'ao'/(name+'.json'))))),threads=3,factory_startup=True)],
            inputs=[*inputs,GAME/'assets/skatepark/modules.json',GAME/'assets/skatepark/modules'],products=[*(Product('skatepark.ao.'+name,(data/'ao'/(name+'.json'),)) for name in ('SM_SkatePier','SM_SkateParkFeatures')),
                Product('skatepark.ao_report',(data/'ao/report.json',))],cache=True,heavy=True),
        Step('world.skatepark.query_data',[Blender(script,('--kind','queries',*(arg for name in ('SM_SkatePierPilings','SM_SkatePath','collision','logical','report') for arg in ('--file',name+'.json',str(data/'queries'/(name+'.json'))))),threads=3,factory_startup=True)],
            inputs=[*inputs,ctx.out/'heightmap.npy',ctx.out/'world.json',REGION/'park.json',GAME/'assets/skatepark/modules.json',GAME/'assets/skatepark/modules'],
            needs=['world.layout'],products=[*(Product('skatepark.terrain.'+name,(data/'queries'/(name+'.json'),)) for name in ('SM_SkatePierPilings','SM_SkatePath')),
                Product('skatepark.query_metadata',(data/'queries/collision.json',data/'queries/logical.json',data/'queries/report.json'))],cache=True,heavy=True)]
    roundtrips=[]
    for region,names in (('skatepark',PARK),('skatepark_board',BOARD)):
        assets=[]
        for name in names:
            record=data/'records'/(name+'.json');args=['--asset',name,'--record',str(record)];reads=[]
            if name in PARK:args+=['--materials',str(data/'materials.json')];reads.append('skatepark.material_geometry')
            if name in ('SM_SkatePier','SM_SkateParkFeatures'):
                args+=['--ao',str(data/'ao'/(name+'.json'))];reads.append('skatepark.ao.'+name)
            if name in ('SM_SkatePierPilings','SM_SkatePath'):
                args+=['--terrain',str(data/'queries'/(name+'.json'))];reads.append('skatepark.terrain.'+name)
            assets.append(G.LogicalAsset(name,REGION/'plan_atomic.py',args=tuple(args),reads=tuple(reads),
                inputs=(GAME/'assets/skatepark/modules.json',GAME/'assets/skatepark/modules') if name in PARK else (),
                products=(Product('skatepark.record.'+name,(record,)),)))
        result.extend(G.steps(ctx,region=region,assets=assets))
        for name in names:
            for key,payload in G.inventory(ctx.out/'planned_exports'/region/name,name):
                output=data/'roundtrip'/(key+'.json');verify=REGION/'verify_atomic.py';prefix='world.'+region+'.export'
                product='skatepark.roundtrip.'+key;roundtrips.append(product)
                result.append(Step('world.skatepark.roundtrip.'+key,[Blender(verify,('--input',str(payload),
                    '--export',str(ctx.out/'exports'/prefix/key),'--output',str(output)),threads=3,factory_startup=True)],
                    inputs=[*local_imports(verify,(WORLD,REGIONS)),*batch_support().values(),payload],reads=[prefix+'.'+key],
                    products=[Product(product,(output,))],cache=True,heavy=True,batch=Batch('skate atomic FBX roundtrips')))
    script=REGION/'assemble_atomic.py'
    result.append(Step('world.skatepark',[Python(script,('--out',str(ctx.out)))],
        inputs=[*local_imports(script,(WORLD,REGIONS)),REGION/'park.json'],
        reads=['skatepark.atomic','skatepark_board.atomic','skatepark.query_metadata','skatepark.ao_report',
               *('skatepark.record.'+name for name in PARK+BOARD),*roundtrips],
        products=[Product('skatepark.meshes',(ctx.out/'skatepark/assets',ctx.out/'skatepark/board',ctx.out/'skatepark/build-report.json')),
                  Product('skatepark.runtime',(ctx.out/'skatepark/runtime-park.json',)),Product('skatepark.queries',(ctx.out/'skatepark/collision.json',))],
        cache=True,about='file-only atomic skate assembly with current per-piece roundtrips and whole logical riding queries'))
    return result
