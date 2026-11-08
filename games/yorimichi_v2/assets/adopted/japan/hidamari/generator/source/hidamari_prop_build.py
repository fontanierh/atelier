"""Selected committed prop parameters, independent source/LOD tasks and file-only assembly."""
import importlib.util
from pathlib import Path
from atelier.build import Product,Python,Step
from atelier.build_inputs import local_imports

GAME=Path(__file__).resolve().parent
WORLD=GAME/'world';REGIONS=WORLD/'regions';REGION=REGIONS/'hidamari'
PARAMETERS=GAME/'assets/hidamari/prop-export-parameters'
_spec=importlib.util.spec_from_file_location('hidamari_prop_roster',REGION/'prop_roster.py')
_roster=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_roster)
PROPS,TREES,members=_roster.PROPS,_roster.TREES,_roster.members


def steps(ctx):
    spec=importlib.util.spec_from_file_location('hidamari_prop_export_graph',GAME/'region_exports.py')
    graph=importlib.util.module_from_spec(spec);spec.loader.exec_module(graph)
    assets=[]
    for name in members():
        parameter=PARAMETERS/(name+'.json');data=ctx.out/'hidamari-prop-data'/name
        if name.startswith('HD_P_'):
            slug=name.removeprefix('HD_P_');source=GAME/'assets/hidamari/props'/slug/(slug+'.glb')
        else:
            folder=name.removeprefix('Tree_Caldera_').split('_LOD')[0].replace('BlackPine','black_pine').replace('Cedar','cedar').lower()
            source=GAME/'assets/craterpark/trees'/folder/'raw/output_model_url.glb'
        script=REGION/('plan_prop.py' if name.startswith('HD_P_') else 'plan_conifer.py')
        assets.append(graph.LogicalAsset(name,script,
            args=('--parameters',str(parameter),'--source',str(source),'--data',str(data)),
            inputs=(parameter,source),products=(Product('hidamari.prop_data.'+name,(data,)),)))
    result=graph.steps(ctx,region='hidamari_props',assets=assets)
    script=REGION/'assemble_props.py'
    result.append(Step('world.hidamari_props',[Python(script,('--out',str(ctx.out)))],
        inputs=local_imports(script,(WORLD,REGIONS)),
        reads=['hidamari_props.atomic',*('hidamari.prop_data.'+name for name in members())],
        products=[Product('hidamari.props',(ctx.out/'hidamari/props',)),
            Product('hidamari.prop_meshes',(ctx.out/'hidamari/assembled-props',))],cache=True,
        about='validate and gather separate fitted props and conifer LODs without rejoining geometry'))
    return result
