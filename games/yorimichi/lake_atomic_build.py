"""Explicit pre-export lake query data and independently constructed/exported logical assets."""
import importlib.util
from pathlib import Path
from atelier.build import Product,Python,Step
from atelier.build_inputs import local_imports
GAME=Path(__file__).resolve().parent
WORLD=GAME/'world';REGIONS=WORLD/'regions';REGION=REGIONS/'forest_lake'
OWNERS=('Lake_Cabin','Lake_Water','Lake_Trail','Lake_Shore','Lake_Plants')


def load(label,path):
    spec=importlib.util.spec_from_file_location(label,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def steps(ctx):
    graph=load('lake_atomic_graph',GAME/'region_exports.py')
    query=REGION/'query_data.py';data=ctx.out/'lake-data/queries'
    result=[Step('world.lake.query_data',[Python(query,('--heightmap',str(ctx.out/'heightmap.npy'),
        '--world',str(ctx.out/'world.json'),'--output',str(data)))],
        inputs=[*local_imports(query,(WORLD,REGIONS)),ctx.out/'heightmap.npy',ctx.out/'world.json'],needs=['world.layout'],
        products=[*(Product('lake.query.'+name,(data/(name+'.json'),)) for name in OWNERS[2:]),
                  Product('lake.query_inventory',(data/'queries.json',))],cache=True,
        about='sample final trail/shore terrain and canonical seeded draws before rendered lake assets')]
    assets=[]
    for name in OWNERS:
        record=ctx.out/'lake-data/records'/(name+'.json')
        args=['--asset',name,'--record',str(record)];reads=[];inputs=[]
        if name in OWNERS[2:]:
            args.extend(('--input',str(data/(name+'.json'))));inputs.append(data/(name+'.json'))
        assets.append(graph.LogicalAsset(name,REGION/'plan_asset.py',args=tuple(args),inputs=tuple(inputs),
            products=(Product('lake.record.'+name,(record,)),)))
    result.extend(graph.steps(ctx,region='lake',assets=assets,after=['world.lake.query_data']))
    script=REGION/'assemble.py'
    result.append(Step('world.lake',[Python(script,('--out',str(ctx.out)))],
        inputs=local_imports(script,(WORLD,REGIONS)),reads=['lake.atomic',*('lake.record.'+name for name in OWNERS)],
        products=[Product('lake.library',(ctx.out/'forest_lake/assets',ctx.out/'forest_lake/manifest.json'))],cache=True,
        about='copy separate bounded lake meshes and publish complete logical membership'))
    return result
