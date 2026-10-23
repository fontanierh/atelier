"""Vehicle source projections, independent bounded exports and file-only assembly."""
import importlib.util
import json
from pathlib import Path

from atelier.atomic_files import atomic_json
from atelier.build import Call,Product,Python,Step
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
    primitive=tuple(local_imports(WORLD/'regions/village/mesh.py',(WORLD,)))
    result=[Step('world.'+family+'.sources',[Python(WORLD/'vehicle_sources.py',('--family',family,'--output',str(data)))],
        inputs=[*local_imports(WORLD/'vehicle_sources.py',(WORLD,)),GAME/'assets/vehicles'/family/'build.py'],
        products=[Product(region+'.source.'+key,(data/(key+'.json'),)) for key in roster],cache=True)]
    assets=[graph.LogicalAsset(key,WORLD/'plan_vehicle_part.py',
        args=('--source',str(data/(key+'.json')),'--report',str(reports/(key+'.json'))),
        reads=(region+'.source.'+key,),inputs=primitive,
        products=(Product(region+'.report.'+key,(reports/(key+'.json'),)),)) for key in roster]
    result.extend(graph.steps(ctx,region=region,assets=assets))
    def assemble(ctx,log):
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
            if row['triangles']!=report['triangles'] or row['metadata']['collision_hulls']!=report['collision_boxes']:
                raise ValueError('Vehicle construction report differs from exported ownership')
            records[key]=report
        atomic_json(ctx.out/family/'manifest.json',records)
        log.write(f'{family}: complete independent parts assembled without joining geometry\n')
    result.append(Step('world.'+family,[Call('assemble independent '+family+' parts',assemble)],
        inputs=[Path(__file__),*export_assembly.runtime_inputs()],
        reads=[region+'.atomic',*(region+'.report.'+key for key in roster)],
        products=[Product(region+'.library',(ctx.out/family/'assets',ctx.out/family/'manifest.json'))]))
    return result
