"""Vehicle source projections, independent bounded exports and file-only assembly."""
import importlib.util
import json
from pathlib import Path

from atelier.atomic_files import atomic_json
from atelier.build import Blender,Call,Product,Python,Step
from atelier.build_inputs import local_imports
from atelier import export_assembly

GAME=Path(__file__).resolve().parent;WORLD=GAME/'world'


def load(key,path):
    spec=importlib.util.spec_from_file_location(key,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def steps(ctx,family):
    sources=load('vehicle_source_roster',WORLD/'vehicle_sources.py')
    graph=load('vehicle_atomic_graph',GAME/'region_exports.py')
    if family not in sources.FAMILIES:raise ValueError('Unknown vehicle family')
    roster=sources.FAMILIES[family]['builders'];region='vehicle_'+family
    data=ctx.out/'vehicle-source-data'/family;reports=ctx.out/'vehicle-part-reports'/family
    primitive=tuple(local_imports(WORLD/'regions/village/mesh.py',(WORLD,))) if family!='bike' else ()
    kart=family=='kart';bike=family=='bike';cockpit=ctx.out/'kart/cockpit.json'
    layout_source=ctx.out/'vehicle-source-data/bike-layout.json';layout=ctx.out/'bike-layout.json'
    result=[Step('world.'+family+'.sources',[Python(WORLD/'vehicle_sources.py',('--family',family,'--output',str(data),
        *(('--layout-output',str(cockpit if kart else layout_source)) if kart or bike else ())))],
        inputs=[*local_imports(WORLD/'vehicle_sources.py',(WORLD,)),GAME/'assets/vehicles'/family/'build.py',
                *((GAME/'assets/vehicles/kart/cockpit.py',GAME/'assets/vehicles/kart/cockpit.json') if kart else ())],
        products=[*[Product(region+'.source.'+key,(data/(key+'.json'),)) for key in roster],
                  *([Product(region+'.cockpit',(cockpit,))] if kart else []),
                  *([Product(region+'.layout_source',(layout_source,))] if bike else [])],cache=True)]
    if bike:
        result.append(Step('world.bike.layout',[Blender(WORLD/'plan_bike_layout.py',
            ('--source',str(layout_source),'--output',str(layout)),threads=3,factory_startup=True)],
            inputs=local_imports(WORLD/'plan_bike_layout.py',(WORLD,)),reads=[region+'.layout_source'],
            products=[Product(region+'.layout',(layout,))],cache=True))
    assets=[graph.LogicalAsset(key,WORLD/'plan_vehicle_part.py',
        args=('--source',str(data/(key+'.json')),'--report',str(reports/(key+'.json'))),
        reads=(region+'.source.'+key,),inputs=primitive,
        products=(Product(region+'.report.'+key,(reports/(key+'.json'),)),)) for key in roster]
    result.extend(graph.steps(ctx,region=region,assets=assets))
    if bike:
        result.append(Step('world.bike.scene',[Blender(WORLD/'build_bike_scene.py',
            ('--plans',str(ctx.out/'planned_exports/vehicle_bike'),'--layout',str(layout),
             '--output',str(ctx.out/'bike/Bike.blend')),threads=3,factory_startup=True)],
            inputs=[*local_imports(WORLD/'build_bike_scene.py',(WORLD,)),GAME/'assets/vehicles/bike/build.py'],
            reads=[region+'.layout',*(region+'.geometry.'+key for key in roster)],
            products=[Product(region+'.scene',(ctx.out/'bike/Bike.blend',))],cache=True))
    def assemble(ctx,log):
        """@cc [owner:fontanierh,label:correctness;performance] complete-independent-vehicle-assembly
        Assembly MUST gather the complete independently exported rigid roster without
        joining geometry or re-exporting parts. Exact original report/layout/pivot fields
        MUST remain available to native and runtime consumers. Kart MUST retain its
        original total budget of 6000 triangles; native reports MUST stay outside source products.
        """
        region_root=ctx.out/'atomic_regions'/region
        logical=json.loads((region_root/'logical-pieces.json').read_text())
        if set(logical['parents'])!=set(roster) or any(values!=[key] for key,values in logical['parents'].items()):
            raise ValueError('Incomplete independent rigid vehicle ownership')
        items=[export_assembly.Item(key,ctx.out/'exports'/('world.'+region+'.export')/key) for key in roster]
        receipt=export_assembly.assemble(items,ctx.out/family/'assets');records={}
        by_name={row['asset']:row for row in receipt['exports']}
        if set(by_name)!=set(roster):raise ValueError('Incomplete vehicle primary receipts')
        for key in roster:
            report=json.loads((reports/(key+'.json')).read_text());row=by_name[key]
            if row['triangles']!=report['triangles'] or row['metadata']['collision_hulls']!=report.get('collision_boxes',0):
                raise ValueError('Vehicle construction report differs from exported ownership')
            records[key]=report
        if kart:
            if sum(row['triangles'] for row in records.values())>6000:raise ValueError('Original kart triangle budget exceeded')
            records['layout']=json.loads(cockpit.read_text())
        if bike:
            steering=sources.BIKE_BUILDERS.keys() & {'BK_Steer_Core','BK_Steer_BasketShell','BK_Steer_BasketRim','BK_Steer_BasketFoot'}
            if len(steering)!=4:raise ValueError('Incomplete Bike steering group')
            records=dict(parts=records,steering_parts=sorted(steering),**json.loads(layout.read_text()))
        atomic_json(ctx.out/family/'manifest.json',records)
        log.write(f'{family}: complete independent parts assembled without joining geometry\n')
    result.append(Step('world.'+family,[Call('assemble independent '+family+' parts',assemble)],
        inputs=[Path(__file__),*export_assembly.runtime_inputs()],
        reads=[region+'.atomic',*(region+'.report.'+key for key in roster),*([region+'.cockpit'] if kart else []),*([region+'.layout',region+'.scene'] if bike else [])],
        products=[Product(region+'.library',(ctx.out/family/'assets',ctx.out/family/'manifest.json'))]))
    return result
