"""Explicit Treehouse query data, selected logical constructors and cached atomic exports."""
import importlib.util
from pathlib import Path
from atelier.build import Blender,Product,Python,Step
from atelier.build_inputs import local_imports

GAME=Path(__file__).resolve().parent
WORLD=GAME/'world';REGIONS=WORLD/'regions';REGION=REGIONS/'treehouse'
PARAMETERS=GAME/'assets/treehouse/export-parameters'
TREES=('Tree_Canopy_Maple','Tree_Canopy_Crimson','Tree_Canopy_Amber','Tree_Canopy_Ginkgo')
PROPS=tuple('TH_P_'+slug for slug in ('backpack','barrel','basket','bell','bookshelf','crate_desk','futon',
    'globe','kamado','log_table','planter','stump_kettle','telescope'))
SURFACES=('TH_Structure','TH_Frame','TH_Trunks','TH_Dressing')


def graph():
    spec=importlib.util.spec_from_file_location('treehouse_atomic_graph',GAME/'region_exports.py')
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def assemble(ctx,kind,reads,products,names=()):
    script=REGION/'assemble_atomic.py'
    return Step('world.treehouse' if kind=='surfaces' else 'world.treehouse_'+kind,
        [Python(script,('--out',str(ctx.out),'--kind',kind,*(item for name in names for item in ('--name',name))))],
        inputs=local_imports(script,(WORLD,REGIONS,GAME)),reads=reads,products=products,cache=True,
        about='assemble exact independent Treehouse '+kind+' files and metadata; no geometry joins')


def canopy_steps(ctx):
    G=graph();assets=[];records=[]
    for name in TREES:
        parameter=PARAMETERS/(name+'.json');record=ctx.out/'treehouse-data/canopy/records'/(name+'.json');records.append(record)
        assets.append(G.LogicalAsset(name,REGION/'plan_tree.py',args=('--parameters',str(parameter),'--record',str(record)),
            inputs=(parameter,ctx.out/'textures/T_bark.jpg',ctx.out/'textures/T_leaf_maple.png'),
            products=(Product('treehouse.canopy_record.'+name,(record,)),),needs=('world.textures',)))
    result=G.steps(ctx,region='treehouse_trees',assets=assets)
    script=REGION/'canopy_data.py';records_root=ctx.out/'treehouse-data/canopy'
    result.append(Step('world.treehouse_trees.data',[Python(script,('--output',str(records_root/'trees.json'),
        *(item for record in records for item in ('--record',str(record)))))],
        inputs=local_imports(script,(WORLD,REGIONS)),reads=['treehouse.canopy_record.'+name for name in TREES],
        products=[Product('treehouse.canopy_dimensions',(records_root/'trees.json',))],cache=True,
        about='publish complete canopy dimensions before world layout and rendered exports'))
    result.append(Step('world.treehouse_trees.recolour',[Blender(script,('--recolour',str(records_root/'recoloured')),
        threads=3,factory_startup=True)],inputs=[*local_imports(script,(WORLD,REGIONS)),ctx.out/'textures/T_leaf_maple.png'],
        needs=['world.textures'],products=[Product('treehouse.canopy_recolours',(records_root/'recoloured',))],cache=True,heavy=True))
    result.append(assemble(ctx,'trees',['treehouse_trees.atomic','treehouse.canopy_dimensions','treehouse.canopy_recolours'],
        [Product('treehouse.trees',(ctx.out/'treehouse/trees',)),Product('treehouse.tree_meshes',(ctx.out/'treehouse/assembled-trees',))],TREES))
    return result


def prop_steps(ctx):
    G=graph();assets=[]
    for name in PROPS:
        slug=name.removeprefix('TH_P_');parameter=PARAMETERS/(name+'.json')
        source=GAME/'assets/treehouse/props'/slug/(slug+'.glb');data=ctx.out/'treehouse-data/props'/name
        assets.append(G.LogicalAsset(name,REGION/'plan_prop.py',args=('--parameters',str(parameter),
            '--source',str(source),'--data',str(data)),inputs=(parameter,source),
            products=(Product('treehouse.prop_data.'+name,(data,)),)))
    result=G.steps(ctx,region='treehouse_props',assets=assets)
    result.append(assemble(ctx,'props',['treehouse_props.atomic',*('treehouse.prop_data.'+name for name in PROPS)],
        [Product('treehouse.props',(ctx.out/'treehouse/props',)),Product('treehouse.prop_meshes',(ctx.out/'treehouse/assembled-props',))],PROPS))
    return result


def surface_steps(ctx):
    G=graph();source=ctx.out/'treehouse-data/surfaces';script=REGION/'geometry_data.py'
    result=[Step('world.treehouse.source_data',[Blender(script,('--out',str(source)),threads=3,factory_startup=True,
        env=(('PYTHONHASHSEED','0'),))],inputs=[*local_imports(script,(WORLD,REGIONS)),ctx.out/'heightmap.npy'],
        needs=['world.layout'],reads=['treehouse.canopy_dimensions'],cache=True,heavy=True,
        products=[*(Product('treehouse.surface_source.'+parent,(source/parent,)) for parent in SURFACES),
                  Product('treehouse.surface_metadata',(source/'runtime.json',source/'manifest.json'))],
        about='finish coupled original geometry and shared Frame/Dressing capsule table before mesh exports')]
    assets=[G.LogicalAsset(parent,REGION/'plan_surface.py',args=('--source',str(source/parent)),
        reads=('treehouse.surface_source.'+parent,)) for parent in SURFACES]
    result.extend(G.steps(ctx,region='treehouse_surfaces',assets=assets,after=['world.treehouse.source_data']))
    result.append(assemble(ctx,'surfaces',['treehouse_surfaces.atomic','treehouse.surface_metadata'],
        [Product('treehouse.surfaces',(ctx.out/'treehouse/assets',ctx.out/'treehouse/pieces.json',
            ctx.out/'treehouse/surfaces.json',ctx.out/'treehouse/runtime.json',ctx.out/'treehouse/manifest.json'))]))
    return result
