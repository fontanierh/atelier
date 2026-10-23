"""Hippodrome recipe inventory and file-only venue assembly."""
import hashlib
import json
from pathlib import Path
from atelier.atomic_files import atomic_json
from atelier.build import Call, Product, Step, Python
from atelier import export_assembly
from region_exports import LogicalAsset, steps as region_steps
from hippodrome import layout as L

HERE=Path(__file__).resolve().parent
SURFACES=('Ground','Skirt','Track','Rails','Lane','LaneSkirt')


def assets(query=None):
    for suffix in SURFACES:
        yield LogicalAsset('SM_HD_'+suffix,HERE/('plan_'+suffix.lower()+'.py'),
            args=('--query',str(query)) if suffix in ('Skirt','Lane','LaneSkirt') and query else (),
            reads=('hippodrome.queries',) if suffix in ('Skirt','Lane','LaneSkirt') else (),
            suffix='.glb',encoding='encoded_glb')
    for slug in L.STRUCTURES:
        key='SM_HD_'+''.join(part.title() for part in slug.split('_'))
        yield LogicalAsset(key,HERE/('plan_'+slug+'.py'),
            inputs=(HERE.parents[2]/'assets'/'hippodrome'/'props'/slug/(slug+'.glb'),),suffix='.glb',encoding='encoded_glb')


def assemble(out):
    """Copy verified atomic files and preserve the original complete venue data."""
    from hippodrome.venue_data import metadata
    from hippodrome.query_context import load
    load(Path(out)/'hippodrome_queries.json')
    out=Path(out);source=out/'atomic_regions'/'hippodrome'
    membership=json.loads((source/'logical-pieces.json').read_text())
    exports=json.loads((source/'assets'/'manifest.json').read_text())
    receipts={row['asset']:row for row in exports['exports']}
    expected=[name for names in membership['parents'].values() for name in names]
    if set(expected)!=set(receipts) or len(expected)!=len(receipts):raise ValueError('Incomplete venue assembly')
    from atelier.build_cache import copy_file
    destination=out/'hippodrome'/'region';glb=destination/'glb'
    export_assembly.destination_members(glb,{name+'.glb' for name in expected})
    for name in expected:
        row=receipts[name];path=source/'assets'/row['primary']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('Changed venue export')
    glb.mkdir(parents=True,exist_ok=True)
    from atelier.model_files import retain_files
    for name in expected:
        path=source/'assets'/(name+'.glb');target=glb/path.name
        if not target.exists() or target.read_bytes()!=path.read_bytes():copy_file(path,target)
    atomic_json(glb/'manifest.json',exports)
    retain_files(glb,['manifest.json',*(name+'.glb' for name in expected)])
    data=metadata();meshes=[];report={}
    for entry in data['meshes']:
        for name in membership['parents'][entry['name']]:
            row=receipts[name];info=dict(row['metadata'])
            for key in ('role','slots','geometry_sha256'):info.pop(key,None)
            info['sha256']=row['sha256'];report[name]=info
            meshes.append(dict(entry,name=name,logical_parent=entry['name']))
    data['meshes']=meshes
    atomic_json(destination/'hippodrome.json',data)
    atomic_json(destination/'build-report.json',dict(platform_z=data['origin'][2],meshes=report))


def steps(ctx, *, query_inputs=(), query_reads=(), query_needs=(), **kwargs):
    from atelier.build_inputs import local_imports
    query=ctx.out/"hippodrome_queries.json"
    result=[Step("world.hippodrome.queries",[Python(HERE/"project_queries.py",("--output",str(query)))],
        inputs=[*local_imports(HERE/"project_queries.py",(HERE.parents[1],HERE.parent)),*query_inputs],
        reads=list(query_reads),needs=list(query_needs),products=[Product("hippodrome.queries",(query,))],cache=True)]
    result+=region_steps(ctx,region="hippodrome",assets=assets(query),**kwargs)
    textures=ctx.out/'hippodrome_textures'
    result.append(Step('world.hippodrome.textures',[Python(HERE/'venue_data.py',('--textures',str(textures)))],
        inputs=local_imports(HERE/'venue_data.py',(HERE.parents[1],HERE.parent)),products=[Product('hippodrome.textures',(textures,))],cache=True))
    def finish(ctx,log):
        assemble(ctx.out)
        import shutil
        destination=ctx.out/'hippodrome'/'region'/'textures';destination.mkdir(parents=True,exist_ok=True)
        for path in textures.iterdir():shutil.copy2(path,destination/path.name)
        log.write('Hippodrome complete file-only assembly\n')
    result.append(Step('world.hippodrome',[Call('assemble venue data',finish)],
        inputs=[Path(__file__),HERE/'venue_data.py',HERE/'query_context.py',HERE/'layout.py',*export_assembly.runtime_inputs()],
        reads=['hippodrome.atomic','hippodrome.textures','hippodrome.queries'],products=[Product('hippodrome.region',(ctx.out/'hippodrome'/'region',))]))
    return result
