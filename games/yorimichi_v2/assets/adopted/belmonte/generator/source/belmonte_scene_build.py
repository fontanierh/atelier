"""Separate metadata preparation and complete file-only regional assembly."""
import json
from pathlib import Path

from atelier.build import Product,Python,Step
from atelier.build_inputs import local_imports

GAME=Path(__file__).resolve().parent
WORLD=GAME/'world'
REGION=WORLD/'regions/belmonte'
LIBRARY=GAME/'assets/belmonte'
NORTH=('SM_BM_NorthApron','SM_BM_NorthCountry')


def code(script):
    return local_imports(script,(WORLD,WORLD/'regions'))


def steps(ctx):
    """Preparation consumes source/query products, never sibling render exports."""
    scene=ctx.out/'belmonte-scene-data';materials=ctx.out/'belmonte-materials'
    script=REGION/'scene_inputs.py'
    result=[Step('world.belmonte.scene_views',[Python(script,('--source',str(LIBRARY/'source.json'),'--output',str(scene)))],
        inputs=[*code(script),LIBRARY/'source.json'],
        products=[Product('belmonte.scene.'+key,(scene/(key+'.json'),)) for key in ('materials','planting','runtime')]
            +[Product('belmonte.scene.inventory',(scene/'inventory.json',))],cache=True,
        about='only material, planting and placement views consumed independently')]
    data=json.loads((LIBRARY/'source.json').read_text());images=[]
    for path,entry in data['materials'].items():
        if path.endswith('MI_B_foliage'):continue
        texture=entry['textures'].get('BaseColor') or entry['textures'].get('DryColor')
        if not texture:continue
        if 'terrain_' in path:
            images.extend((GAME/'assets/environment/textures/tuscan-ground.jpg',
                           GAME/'assets/environment/textures/tuscan-ground.provenance.json'))
        else:images.append(LIBRARY/data['textures'][texture]['file'])
    script=REGION/'prepare_materials.py'
    result.append(Step('world.belmonte.prepare_materials',[Python(script,(
        '--input',str(scene/'materials.json'),'--output',str(materials),
        '--assets',str(GAME/'assets'),'--library',str(LIBRARY)))],
        inputs=[*code(script),*dict.fromkeys(images)],reads=['belmonte.scene.materials'],
        products=[Product('belmonte.prepared_materials',(materials,))],cache=True,heavy=True,
        about='prepare the original palette and image bytes without geometry'))
    script=REGION/'prepare_planting.py';plants=ctx.out/'belmonte-planting/planting.json'
    result.append(Step('world.belmonte.prepare_planting',[Python(script,(
        '--input',str(scene/'planting.json'),
        '--valley',str(ctx.out/'belmonte-query-data/BelmonteValley-final.npz'),
        '--apron',str(ctx.out/'belmonte-query-data/SM_BM_NorthApron-final.npz'),'--output',str(plants)))],
        inputs=[*code(script),GAME/'assets/vehicles/belmonte-train/line.json'],
        reads=['belmonte.scene.planting','belmonte.valley_final','belmonte.query.SM_BM_NorthApron'],
        products=[Product('belmonte.prepared_planting',(plants,))],cache=True,heavy=True,
        about='authored and connecting woodland from complete final query data'))
    return result


def assembly_step(out):
    """@cc [owner:fontanierh,label:correctness;performance] belmonte-complete-assembly-products
    The production Belmonte owner MUST assemble only complete independent model,
    ground and north export libraries, material/planting views and canonical
    query data. Every output source file, texture, final/natural query alias and
    runtime/report MUST have complete normal product ownership. No monolithic
    exporter or geometry-reconstruction fallback MAY remain in this task.
    """
    script=REGION/'assemble.py';root=out/'belmonte';scene=out/'belmonte-scene-data'
    args=dict(out=root,scene=scene/'runtime.json',materials=out/'belmonte-materials',
        planting=out/'belmonte-planting/planting.json',models=out/'atomic_regions/belmonte_models',
        ground=out/'atomic_regions/belmonte_ground',north=out/'atomic_regions/belmonte_north',
        sources=out/'belmonte-source-data',natural=out/'belmonte-natural-source-data',
        valley=out/'belmonte-query-data/BelmonteValley-final.npz',seam=out/'belmonte-north-data/seam-report.json')
    entries=json.loads((LIBRARY/'source.json').read_text())['meshes']
    ground=[row['name'] for row in entries if row['name'].startswith('SM_BM_BT_Terrain_')]
    reads=['belmonte.scene.runtime','belmonte.prepared_materials','belmonte.prepared_planting',
        'belmonte_models.atomic','belmonte_ground.atomic','belmonte_north.atomic',
        'belmonte.valley_final','belmonte.north_seam_report',
        *('belmonte.final_surface.'+key for key in [*ground,*NORTH]),
        *('belmonte.natural_surface.'+key for key in NORTH)]
    return Step('world.belmonte',[Python(script,tuple(value for key,path in args.items() for value in ('--'+key,str(path))))],
        inputs=code(script),reads=reads,
        products=[Product('belmonte.assembled_models',(root/'glb',)),
            Product('belmonte.assembled_textures',(root/'textures',)),
            Product('belmonte.assembled_queries',(root/'ground',root/'natural')),
            Product('belmonte.assembled_metadata',(root/'runtime.json',root/'build-report.json'))],
        cache=True,heavy=True,about='complete file-only assembly of independent Belmonte exports and runtime metadata')
