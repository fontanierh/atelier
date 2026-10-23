"""Gather independently exported Treehouse assets and publish exact logical membership."""
import argparse
import json
from pathlib import Path
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[3]),str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from atelier import export_assembly,mesh_ir  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.build_cache import copy_file  # noqa: E402
from atelier.export_manifest import real_directory,sha,validate as validate_export  # noqa: E402
from atelier.model_files import regular_files,retain_files  # noqa: E402
from region_mesh_parts import validate  # noqa: E402

PARENTS=('TH_Structure','TH_Frame','TH_Trunks','TH_Dressing')


def copy_verified(source,destination):
    real_directory(destination.parent,create=True)
    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
        raise ValueError('Foreign/link Treehouse assembly destination')
    digest=sha(source)
    if destination.is_file() and sha(destination)==digest:return
    staging=destination.with_name(destination.name+'.atomic-copy')
    if staging.exists() or staging.is_symlink():raise ValueError('Unowned Treehouse copy staging')
    try:
        copy_file(source,staging)
        if sha(source)!=digest or sha(staging)!=digest:raise ValueError('Treehouse source changed during assembly')
        staging.replace(destination)
    finally:staging.unlink(missing_ok=True)


def surfaces(out):
    """@cc [owner:fontanierh,label:correctness;performance] treehouse-file-only-bounded-surface-assembly
    All current export receipts and exclusive destinations MUST validate before
    copying any primary. Assembly MUST copy unchanged independent FBX bytes without
    joining geometry. Complete logical membership MUST precede retiring exact old
    parent source files; unknown members or links MUST never be adopted or removed.
    """
    root=out/'treehouse';real_directory(root/'assets')
    plans={parent:validate(out/'planned_exports/treehouse_surfaces'/parent) for parent in PARENTS}
    # No delete is allowed until the complete current source/export inventory is validated.
    for parent in PARENTS:
        old=root/'assets'/(parent+'.fbx')
        if old.is_symlink() or (old.exists() and not old.is_file()):raise ValueError('Invalid retired Treehouse source')
    asset_root=root/'assets'
    if asset_root.exists():
        for path in asset_root.iterdir():
            if path.name in ('structure','dressing','frame','trunks'):
                real_directory(path);regular_files(path)
            elif path.name not in {name+'.fbx' for name in PARENTS} or path.is_symlink() or not path.is_file():
                raise ValueError('Foreign Treehouse surface source destination')
    for parent,value in plans.items():
        subdir='structure' if parent=='TH_Structure' else 'dressing' if parent=='TH_Dressing' else parent.removeprefix('TH_').lower()
        for row in value['pieces']:
            validate_export(out/'exports/world.treehouse_surfaces.export'/row['name'],key=row['name'])
        export_assembly.destination_members(root/'assets'/subdir,{row['name']+'.fbx' for row in value['pieces']})
    entries={};ownership={}
    for parent,value in plans.items():
        subdir='structure' if parent=='TH_Structure' else 'dressing' if parent=='TH_Dressing' else parent.removeprefix('TH_').lower()
        folder=root/'assets'/subdir
        items=[export_assembly.Item(row['name'],out/'exports/world.treehouse_surfaces.export'/row['name'])
               for row in value['pieces']]
        result=export_assembly.assemble(items,folder)
        digests={row['asset']:row['sha256'] for row in result['exports']}
        ownership[parent]=[row['name'] for row in value['pieces']]
        for row in value['pieces']:
            key=row['name'];meta,piece=mesh_ir.decode((out/'planned_exports/treehouse_surfaces'/parent/row['payload']).read_bytes())
            used=sorted({meta['slots'][int(i)] for i in piece['materials']})
            entries[key]=dict(name=key,parent=parent,triangles=row['triangles'],collision_hulls=row['collision_hulls'],
                min=row['min'],max=row['max'],used_slots=used,slots=value['slots'],
                sha256=digests[key],fbx='assets/'+subdir+'/'+key+'.fbx',
                uv_channels=[label for label,_ in piece['uvs']])
    value=plans['TH_Dressing'];rows=[entries[row['name']] for row in value['pieces']]
    low=[min(row['min'][i] for row in rows) for i in range(3)]
    high=[max(row['max'][i] for row in rows) for i in range(3)]
    dressing=dict(version=1,complete=True,parent='TH_Dressing',triangle_limit=32768,cell_metres=64,
        uv_channels=['UVMap','Piece1','Piece2','Piece3','Piece4'],collision_boxes=0,
        source_triangles=value['source_triangles'],min=low,max=high,slots=value['slots'],
        pieces=[dict(name=row['name'],triangles=row['triangles'],used_slots=row['used_slots'],
                     min=row['min'],max=row['max'],sha256=row['sha256']) for row in rows])
    from treehouse_pieces import members
    members(dressing)
    atomic_json(root/'pieces.json',dressing)
    atomic_json(root/'surfaces.json',dict(schema=1,complete=True,parents=ownership,assets=entries))
    for file in ('runtime.json','manifest.json'):copy_verified(out/'treehouse-data/surfaces'/file,root/file)
    for parent in PARENTS:(root/'assets'/(parent+'.fbx')).unlink(missing_ok=True)
    print('TREEHOUSE SURFACE ASSEMBLY COMPLETE',len(entries),flush=True)


def library(out,kind,names):
    from treehouse_pieces import PROPS,TREES
    if tuple(names)!=tuple(PROPS if kind=='props' else TREES):raise ValueError('Incomplete logical Treehouse library roster')
    region='treehouse_'+kind;root=out/'treehouse'/kind
    plans={name:validate(out/'planned_exports'/region/name) for name in names}
    for name,value in plans.items():
        if len(value['pieces'])!=1 or value['pieces'][0]['name']!=name:raise ValueError('Logical Treehouse instance must stay one asset')
    # File-only assembly keeps the source names used by native importers.
    mesh_folder=out/'treehouse'/('assembled-'+kind)
    items=[export_assembly.Item(name,out/('exports/world.'+region+'.export')/name) for name in names]
    for item in items:validate_export(item.root,key=item.key)
    export_assembly.destination_members(mesh_folder,{name+'.fbx' for name in names})
    previous=regular_files(root) if root.exists() else set()
    if kind=='trees':
        data=json.loads((out/'treehouse-data/canopy/trees.json').read_text())
        if set(data)!=set(names):raise ValueError('Incomplete canopy query dimensions')
        files=[(out/'treehouse-data/canopy/recoloured'/('T_leaf_'+colour+'.png'),'T_leaf_'+colour+'.png') for colour in ('crimson','amber')]
        wanted={'trees.json',*(name+'.fbx' for name in names),*(name for _,name in files)}
    else:
        data={};files=[]
        for name in names:
            folder=out/'treehouse-data/props'/name
            if regular_files(folder)!={name+'.png','record.json'}:raise ValueError('Incomplete/foreign current prop data')
            record=json.loads((folder/'record.json').read_text())
            if record['name']!=name:raise ValueError('Foreign Treehouse prop record')
            data[name]=dict(record['info'],authored_hulls=record['hulls'])
            files.append((folder/(name+'.png'),name+'.png'))
        wanted={'props.json',*(name+'.fbx' for name in names),*(name for _,name in files)}
    # These folders are exclusive generated owners; prior diagnostic images are
    # explicitly superseded by the original named props/trees roster only.
    diagnostics=({f'view-{name.removeprefix("TH_P_")}-{i}{direction}.png' for name in names
        for i,direction in enumerate(('front','right','back','left'))}|{'preview.jpg'}) if kind=='props' else set()
    allowed=wanted|diagnostics
    if previous-allowed:raise ValueError('Foreign files in Treehouse logical library')
    for source,_ in files:
        real_directory(source.parent)
        if source.is_symlink() or not source.is_file():raise ValueError('Missing/linked current Treehouse image')
    export_assembly.assemble(items,mesh_folder)
    for name in names:copy_verified(mesh_folder/(name+'.fbx'),root/(name+'.fbx'))
    for source,name in files:copy_verified(source,root/name)
    atomic_json(root/(kind+'.json'),data)
    retain_files(root,wanted)
    print('TREEHOUSE LOGICAL LIBRARY COMPLETE',kind,len(names),flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--kind',choices=('surfaces','props','trees'),required=True)
    parser.add_argument('--name',action='append')
    args=parser.parse_args(argv)
    if args.kind=='surfaces':surfaces(args.out)
    else:library(args.out,args.kind,args.name)


if __name__=='__main__':main()
