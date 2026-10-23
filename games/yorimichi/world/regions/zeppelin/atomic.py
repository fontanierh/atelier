"""Independent Zeppelin constructors, bounded exports and file-only compatibility assembly."""
import json
from pathlib import Path
import sys

GAME=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(GAME));sys.path.insert(0,str(GAME/"world"))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json
from atelier.build import Step,Product,Python,Call
from atelier.build_inputs import local_imports
from atelier import export_assembly
from region_exports import LogicalAsset,steps as region_steps

HERE=Path(__file__).resolve().parent
LOGICAL=(('ZP_Airship','ship'),('ZP_Motors','motors'),('ZP_Propeller','propeller'),
         ('ZP_Gate','gate'),('ZP_Gangway','gangway'),('ZP_Woodland','station_data'),
         ('ZP_City','station_data'),('ZP_MegaPark','station_data'),('ZP_Belmonte','station_data'),('ZP_Trail','trail'))


def steps(ctx,*,query_inputs=(),query_reads=(),query_needs=(),**kwargs):
    result=[];assets=[]
    for key,kind in LOGICAL:
        query=ctx.out/'zeppelin_queries'/(key+'.json')
        needs_query=kind in ('station_data','trail')
        if needs_query:
            task='world.zeppelin.query.'+key;product='zeppelin.query.'+key
            result.append(Step(task,[Python(HERE/'project_queries.py',('--asset',key,'--output',str(query)))],
                inputs=[*local_imports(HERE/'project_queries.py',(HERE.parents[1],HERE.parent)),*query_inputs],
                reads=list(query_reads),needs=list(query_needs),products=[Product(product,(query,))],cache=True))
        script=HERE/('plan_'+key[3:].lower()+'.py')
        assets.append(LogicalAsset(key,script,args=('--query',str(query)) if needs_query else (),
            inputs=(HERE/'parts'/(kind+'.py'),),reads=(product,) if needs_query else ()))
    result+=region_steps(ctx,region='zeppelin',assets=assets,**kwargs)
    def rotor_check(ctx,log):
        from zeppelin.rotor_data_check import check
        check(ctx.out);log.write("Continuous rotor clearance checked against planned source geometry\n")
    result.append(Step("world.zeppelin.rotor_check",[Call("validate complete rotor sweep",rotor_check)],
        inputs=[HERE/"rotor_data_check.py",HERE/"layout.py"],
        reads=["zeppelin.geometry.ZP_Airship","zeppelin.geometry.ZP_Propeller"],
        products=[Product("zeppelin.rotor_clearance",(ctx.out/"zeppelin_rotor_clearance.json",))]))
    def assemble(ctx,log):
        root=ctx.out/'atomic_regions'/'zeppelin';source=root/'assets'
        manifest=json.loads((source/'manifest.json').read_text())
        membership=json.loads((root/'logical-pieces.json').read_text())
        expected=[name for rows in membership['parents'].values() for name in rows]
        receipts={row['asset']:row for row in manifest['exports']}
        if len(expected)!=len(receipts) or set(expected)!=set(receipts):raise ValueError('Incomplete Zeppelin exports')
        from atelier.export_manifest import sha
        for name in expected:
            if sha(source/receipts[name]['primary'])!=receipts[name]['sha256']:raise ValueError('Changed Zeppelin export')
        destination=ctx.out/'zeppelin'/'assets'
        export_assembly.destination_members(destination,{row['primary'] for row in receipts.values()})
        destination.mkdir(parents=True,exist_ok=True)
        from atelier.file_copy import copy_file
        from atelier.model_files import retain_files
        for row in receipts.values():
            path=source/row['primary'];target=destination/path.name
            if not target.exists() or sha(target)!=row['sha256']:copy_file(path,target)
        atomic_json(destination/'manifest.json',manifest)
        retain_files(destination,['manifest.json',*(row['primary'] for row in receipts.values())])
        report={name:dict(triangles=row['triangles'],min=row['bounds'][0],max=row['bounds'][1],
                         materials=len(row['metadata']['slots']),sha256=row['sha256']) for name,row in receipts.items()}
        atomic_json(ctx.out/'zeppelin'/'manifest.json',report)
        atomic_json(ctx.out/'zeppelin'/'logical-pieces.json',membership)
        from atelier.file_copy import copy_file
        copy_file(ctx.out/'zeppelin_rotor_clearance.json',ctx.out/'zeppelin'/'rotor-clearance.json')
        log.write('Complete Zeppelin file-only assembly\n')
    result.append(Step('world.zeppelin',[Call('assemble Zeppelin',assemble)],
        inputs=[Path(__file__),*export_assembly.runtime_inputs()],reads=['zeppelin.atomic','zeppelin.rotor_clearance'],
        products=[Product('zeppelin.region',(ctx.out/'zeppelin',))]))
    return result
