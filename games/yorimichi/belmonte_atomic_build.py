"""Independent committed Belmonte source definitions and atomic model exports."""
import json
import importlib.util
from pathlib import Path

from atelier.build import Product,Python,Step
from atelier.build_inputs import local_imports

GAME=Path(__file__).resolve().parent
WORLD=GAME/'world'
REGION=WORLD/'regions/belmonte'
LIBRARY=GAME/'assets/belmonte'


def definitions(ctx):
    """Complete per-source projections stop unrelated catalogue changes before planners."""
    from importlib.util import module_from_spec,spec_from_file_location
    spec=spec_from_file_location('belmonte_atomic_source_projection',REGION/'model_sources.py')
    module=module_from_spec(spec);spec.loader.exec_module(module)
    return module.project(json.loads((LIBRARY/'source.json').read_text()))


def model_steps(ctx):
    """@cc [owner:fontanierh,label:correctness;performance] independent-belmonte-committed-models
    Each committed static model MUST have one selected source definition and its
    own GLB/hull inputs. A global source manifest or sibling model MUST NOT enter
    that planner's inputs. Publish bounded data first, then independently cached
    exact-byte primary exports. Canonical query terrain belongs to separate final
    surface producers; this static graph MUST NOT replace their ownership.
    """
    spec=importlib.util.spec_from_file_location('belmonte_independent_mesh_graph',GAME/'region_exports.py')
    graph=importlib.util.module_from_spec(spec);spec.loader.exec_module(graph)
    selected=definitions(ctx)
    folder=ctx.out/'belmonte-model-definitions'
    projection=Step('world.belmonte.model_definitions',[
        Python(REGION/'model_sources.py',('--source',str(LIBRARY/'source.json'),'--output',str(folder)))],
        inputs=[*local_imports(REGION/'model_sources.py',(WORLD,WORLD/'regions')),LIBRARY/'source.json'],
        products=[Product('belmonte.model_definition.'+key,(folder/(key+'.json'),)) for key in selected]
                 +[Product('belmonte.model_definition_inventory',(folder/'inventory.json',))],
        cache=True,about='project only each committed model geometry identity')
    assets=[]
    for key,value in selected.items():
        if key.startswith(('SM_BM_BT_Terrain_','SM_BM_North')):continue
        source=value['source']
        inputs=[LIBRARY/source['path']]
        if source.get('collision'):inputs.append(LIBRARY/source['collision']['path'])
        assets.append(graph.LogicalAsset(key,REGION/'plan_model.py',
            args=('--asset',key,'--definition',str(folder/(key+'.json')),'--library',str(LIBRARY)),
            inputs=tuple(inputs),reads=('belmonte.model_definition.'+key,),suffix='.glb',encoding='encoded_glb'))
    return [projection,*graph.steps(ctx,region='belmonte_models',assets=assets)]
