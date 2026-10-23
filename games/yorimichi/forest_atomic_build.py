"""One selected forest species/detail source and one normal cache entry per bounded FBX."""
import importlib.util
from pathlib import Path
from atelier.build import Batch,Blender,Product,Python,Step
from atelier.build_inputs import local_imports
from atelier.build_batch_source import support as batch_support

GAME=Path(__file__).resolve().parent
WORLD=GAME/'world';REGIONS=WORLD/'regions'
PARAMETERS=GAME/'assets/forest/export-parameters'


def load(label,path):
    spec=importlib.util.spec_from_file_location(label,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def native_products(ctx):
    """Complete fixed package inventory, including every source LOD and its material."""
    params=load('forest_native_product_parameters',WORLD/'forest_parameters.py')
    names=[params.load(path)[0] for path in sorted(PARAMETERS.glob('*.json'))]
    if len(names)!=8 or len(set(names))!=8:
        raise ValueError('Forest requires all eight native species')
    content=GAME/'unreal/Content'
    packages=[content/'Japan/Textures/T_ForestNormalDefault.uasset',
              content/'Japan/Materials/M_ForestImpostor.uasset']
    for leaf in ('LeafOlive','LeafOak','LeafCypress','LeafStonePine'):
        packages.extend((content/f'Japan/Textures/T_{leaf}.uasset',content/f'Japan/Materials/MI_{leaf}.uasset'))
    for name in names:
        packages.extend((content/f'Japan/Assets/{name}.uasset',
                         content/f'Japan/Materials/MI_{name}_Impostor.uasset',
                         content/f'Japan/FoliageLODs/MI_{name}_Crown.uasset'))
        packages.extend(content/f'Japan/Textures/T_{name}_{kind}.uasset' for kind in ('colour','normal'))
        packages.extend(content/f'Japan/FoliageLODs/{name}_LOD{i}.uasset' for i in range(1,5))
    sidecars=('.uexp','.ubulk','.uptnl','.m.ubulk','.upayload')
    return [Product('forest.native_assets',tuple(packages),
                optional_paths=tuple(path.with_suffix(suffix) for path in packages for suffix in sidecars)),
            Product('forest.native_reports',(ctx.out/'forest/import-report.json',ctx.out/'forest/native/import.json'))]


def steps(ctx):
    graph=load('forest_atomic_graph',GAME/'region_exports.py')
    params=load('forest_atomic_parameters',WORLD/'forest_parameters.py')
    materials=load('forest_atomic_materials',WORLD/'material_specs.py')
    files=sorted(PARAMETERS.glob('*.json'))
    if len(files)!=8:
        raise ValueError('Forest requires the complete eight-species source inventory')
    assets=[];bakes=[];records=[];bake_products=[]
    for file in files:
        name,spec=params.load(file)
        bark='BarkOlive' if spec[0]=='olive' else 'BarkTuscan' if name.startswith('Tree_Tuscan_') else 'Bark'
        textures=[ctx.out/'textures'/materials.MATERIALS[bark]['texture']]
        textures.append(ctx.out/'forest/textures'/('T_'+spec[-1]+'.png') if name.startswith('Tree_Tuscan_') else
                        ctx.out/'textures'/materials.MATERIALS[spec[-1]]['texture'])
        frame=ctx.out/'forest-data/records'/(name+'.json')
        views=ctx.out/'forest-data/impostor-views'/(name+'.json')
        for level in range(5):
            key=name if level==0 else name+f'_LOD{level}'
            record=ctx.out/'forest-data/records'/(key+'.json');records.append('forest.record.'+key)
            args=['--parameters',str(file),'--level',str(level),'--record',str(record)]
            reads=[]
            if level:
                args.extend(('--frame',str(frame)));reads.append('forest.record.'+name)
            if level==3:
                args.extend(('--proxy',str(views)));reads.append('forest.impostor_views.'+name)
            assets.append(graph.LogicalAsset(key,WORLD/'plan_forest_tree.py',args=tuple(args),
                inputs=(file,*textures),reads=tuple(reads),
                products=(Product('forest.record.'+key,(record,)),)))
        bake=ctx.out/'forest-bakes'/name;product='forest.impostor.'+name;bake_products.append(product)
        script=WORLD/'bake_forest_tree.py'
        bakes.append(Step('world.forest.impostor.'+name,[Blender(script,('--parameters',str(file),'--frame',str(frame),
            '--views',str(views),'--output',str(bake)),threads=3,factory_startup=True)],
            inputs=[*local_imports(script,(WORLD,REGIONS)),*batch_support().values(),file,*textures],reads=['forest.record.'+name],
            products=[Product(product,(bake,)),Product('forest.impostor_views.'+name,(views,))],
            cache=True,heavy=True,batch=Batch('forest impostor data'),
            about='only this species: canonical four-view color/normal atlas and measured billboard geometry'))
    result=[*bakes,*graph.steps(ctx,region='forest',assets=assets,after=['world.textures','world.forest_textures'])]
    script=WORLD/'assemble_forest.py';args=['--out',str(ctx.out)]
    for file in files:args.extend(('--parameters',str(file)))
    result.append(Step('world.forest',[Python(script,tuple(args))],
        inputs=[*local_imports(script,(WORLD,REGIONS)),*files],reads=['forest.atomic',*records,*bake_products],
        products=[Product('forest.library',(ctx.out/'forest/assembled',)),
                  Product('forest.mesh_files',(ctx.out/'forest/mesh-files',)),
                  Product('forest.manifest',(ctx.out/'forest/trees.json',))],
        cache=True,about='copy separate authored forest levels/images; assemble metadata without geometry joins'))
    return result
