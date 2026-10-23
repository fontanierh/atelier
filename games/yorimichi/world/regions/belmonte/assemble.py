"""Gather complete Belmonte atomic files and metadata; never export or join meshes."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.build_cache import copy_file  # noqa: E402
from atelier.export_manifest import real_directory,sha  # noqa: E402
from atelier.model_files import member,regular_files,source_records  # noqa: E402
from belmonte import atomic_library,ground_pieces,query_arrays,runtime_groups,runtime_layout,surface_data  # noqa: E402
from belmonte import layout as L  # noqa: E402
from belmonte.prepare_materials import validate as material_library  # noqa: E402
from belmonte.query_surface import Surface  # noqa: E402
from belmonte.scene_inputs import read as scene_view  # noqa: E402
from belmonte.terrain_bounds import OUTER  # noqa: E402

FOLDERS=('glb','textures','ground/glb','natural')
NORTH=('SM_BM_NorthApron','SM_BM_NorthCountry')
JOURNAL='.assembly-transaction.json'


def document(path):
    path=Path(path);real_directory(path.parent)
    if path.is_symlink() or not path.is_file():raise ValueError('Assembly metadata must be a regular input')
    return json.loads(path.read_text())


def filenames(values):
    if not isinstance(values,list) or len(set(values))!=len(values) or any(member(v)!=Path(v).name for v in values):
        raise ValueError('Nonflat or duplicate Belmonte assembly membership')
    return set(values)


def previous(root):
    """Recover only explicit prior source/texture/query membership, including interrupted publication."""
    root=real_directory(root);known={key:set() for key in FOLDERS}
    if not root.exists():return known
    for path in root.iterdir():
        if path.name in ('glb','textures','ground','natural'):
            real_directory(path)
            if not path.is_dir():raise ValueError('Assembly product folder must be a directory')
        elif path.is_symlink() or not path.is_file() or path.name not in ('build-report.json','runtime.json','import-report.json',JOURNAL):
            raise ValueError('Foreign Belmonte assembly output')
    report=root/'build-report.json'
    if report.exists():
        value=document(report)
        known['glb'].update(Path(relative).name for _,relative in source_records(value['meshes'],collision_directory='glb'))
        known['textures'].update(row['texture'] for row in value['materials'].values() if row.get('texture'))
    ground=root/'ground'
    if ground.exists():
        for path in ground.iterdir():
            if path.name=='glb':
                real_directory(path)
                if not path.is_dir():raise ValueError('Final query folder must be a directory')
            elif path.name!='membership.json' or path.is_symlink() or not path.is_file():
                raise ValueError('Foreign final query output')
        if (ground/'membership.json').exists():
            value=document(ground/'membership.json')
            if value.get('schema')!=1 or value.get('origin_cm')!=L.native_origin():raise ValueError('Foreign prior final ground')
            for row in value['surfaces']:
                if row['path']!='ground/glb/'+row['name']+'.glb' or not ground_pieces.is_ground(row['name']):
                    raise ValueError('Foreign previous query member')
                known['ground/glb'].add(row['name']+'.glb')
    known['natural'].update(key+'.glb' for key in NORTH)
    if (root/JOURNAL).exists():
        value=document(root/JOURNAL)
        if (set(value)!={'schema','owner','files'} or value['schema']!=1 or value['owner']!='BelmonteAtomic'
                or set(value['files'])!=set(FOLDERS)):raise ValueError('Foreign assembly transaction')
        for key in FOLDERS:known[key].update(filenames(value['files'][key]))
    for key in FOLDERS:filenames(list(known[key]))
    return known


def preflight(root,files,old):
    for key in FOLDERS:
        folder=real_directory(root/key)
        if folder.exists() and (regular_files(folder)-set(files[key])-old[key]
                or any(path.is_dir() for path in folder.iterdir())):raise ValueError('Foreign flat assembled member: '+key)
        filenames(list(files[key]))
        for filename,(path,digest) in files[key].items():
            real_directory(path.parent)
            if path.is_symlink() or not path.is_file() or sha(path)!=digest:raise ValueError('Assembly source changed')


def publish(root,files,old,runtime,report,surfaces):
    """@cc [owner:fontanierh,label:correctness;performance] belmonte-file-only-assembly
    Assembly MUST validate every current independent export and all exclusive
    destinations before writes. It MUST copy unchanged files, never construct,
    export or join render geometry. Whole query aliases MUST copy the complete
    final source data, not rendered children. Publish current inventories before
    retiring only explicitly recorded prior files; refusal preserves foreign data.
    """
    preflight(root,files,old)
    root.mkdir(parents=True,exist_ok=True)
    atomic_json(root/JOURNAL,dict(schema=1,owner='BelmonteAtomic',files={key:sorted(old[key]|set(files[key])) for key in FOLDERS}))
    for key in FOLDERS:
        folder=root/key;folder.mkdir(parents=True,exist_ok=True)
        for filename,(source,digest) in files[key].items():
            target=folder/filename
            if not target.exists() or sha(target)!=digest:
                with tempfile.TemporaryDirectory(prefix='.belmonte-stage-',dir=root.parent) as temporary:
                    staging=Path(temporary)/filename;copy_file(source,staging)
                    if sha(staging)!=digest or sha(source)!=digest:raise ValueError('Source changed while staging Belmonte')
                    staging.replace(target)
    for rows in files.values():
        if any(sha(path)!=digest for path,digest in rows.values()):raise ValueError('Source changed before assembly publication')
    # _validate checks complete final surface bytes before membership publication.
    membership=dict(schema=1,origin_cm=L.native_origin(),surfaces=surfaces)
    ground_pieces._validate(root,membership,complete=False)
    atomic_json(root/'ground/membership.json',membership)
    atomic_json(root/'runtime.json',runtime);atomic_json(root/'build-report.json',report)
    for key in FOLDERS:
        for filename in old[key]-set(files[key]):(root/key/filename).unlink(missing_ok=True)
    (root/JOURNAL).unlink()
    ground_pieces.load(root)


def assemble(*,out,scene,materials,planting,models,ground,north,sources,natural,valley,seam):
    out=real_directory(out);old=previous(out);data=scene_view(scene,view='runtime')
    ground_pieces.placements(data)
    originals={row['name']:row for row in data['meshes']}
    if len(originals)!=len(data['meshes']):raise ValueError('Duplicate runtime source owner')
    static=[key for key in originals if not ground_pieces.is_ground(key)]
    terrain=[key for key in originals if ground_pieces.is_ground(key)]
    if len(static)!=232 or len(terrain)!=56:raise ValueError('Incomplete committed Belmonte roster')
    libraries=[atomic_library.read(root,expected=expected,original=originals) for root,expected in
        ((models,static),(ground,terrain),(north,NORTH))]
    by_parent={key:rows for library in libraries for key,rows in library['by_parent'].items()}
    meshes=[row for key in [*originals,*NORTH] for row,_,_ in by_parent[key]]
    by_asset={row['source_asset']:by_parent[row['name']] for row in data['meshes']}
    if len(by_asset)!=len(originals):raise ValueError('Aliased runtime placement source')
    prepared=material_library(materials)
    groups=runtime_groups.groups(data,prepared,by_asset,meshes,libraries[-1]['meshes'])
    plants=document(planting)
    if set(plants)!={'schema','owner','plants','report'} or plants['schema']!=1 or plants['owner']!='BelmontePlants':
        raise ValueError('Foreign planting product')
    for key,transforms in plants['plants'].items():
        tree=key.startswith(('Tree_','HD_'));grass=key.startswith('Grass_')
        groups.append(dict(asset=f'/Game/Japan/Assets/{key}.{key}',materials=[],plant=True,collision=tree,
            shadow=not grass,cull_cm=8000 if grass else 36000 if not tree else 400000,transforms=transforms))
    query=query_arrays.read(valley,owner='BelmonteValley',stage='final')
    town_z=float(Surface(query['faces']).height(0.,-18.))+L.ORIGIN[2]+1.
    runtime=dict(version=1,origin_cm=L.native_origin(),bounds_m=L.BOUNDS,clearance_m=list(OUTER),groups=groups,
        signs=[dict(row,text=runtime_layout.SIGN_TRANSLATIONS.get(row['text'],row['text'])) for row in data['signs']],
        railway_corridor=L.RAILWAY,zones=runtime_layout.map_zones(town_z,data),tv_spots=runtime_layout.tv_spots(data))
    report=dict(meshes=meshes,materials=prepared,planting=plants['report'],seam=document(seam))
    json.dumps([runtime,report],allow_nan=False)
    files={key:{} for key in FOLDERS}
    for library in libraries:
        for key,path in library['files'].items():
            if key in files['glb']:raise ValueError('Duplicate regional primary')
            files['glb'][key]=(path,library['identities'][key])
    for row in prepared.values():
        key=row['texture']
        if key:files['textures'][key]=(Path(materials)/'textures'/key,sha(Path(materials)/'textures'/key))
    # These aliases serve existing whole-surface queries only; they are exact
    # copies of pre-export source data and never enter native render membership.
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.belmonte-query-aliases-',dir=out.parent) as temporary:
        work=Path(temporary);surfaces=[]
        for key in [*terrain,*NORTH]:
            entry,raw=surface_data.read(Path(sources)/(key+'.surface'),owner=key)
            path=work/(key+'.glb');path.write_bytes(raw)
            files['ground/glb'][path.name]=(path,entry['sha256'])
            surfaces.append({field:entry[field] for field in ('name','sha256','bounds_m','triangles')}|dict(path='ground/glb/'+path.name))
        for key in NORTH:
            entry,raw=surface_data.read(Path(natural)/(key+'.surface'),owner=key,stage='natural')
            path=work/(key+'-natural.glb');path.write_bytes(raw)
            files['natural'][key+'.glb']=(path,entry['sha256'])
        publish(out,files,old,runtime,report,surfaces)
    print('BELMONTE ATOMIC ASSEMBLY COMPLETE',len(meshes),'meshes',len(groups),'groups',flush=True)
    return report,runtime


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('out','scene','materials','planting','models','ground','north','sources','natural','valley','seam'):
        parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();assemble(**vars(args))
