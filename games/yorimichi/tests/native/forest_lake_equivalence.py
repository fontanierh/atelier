"""Real immutable predecessor vs atomic Forest/Lake exporter conservation.

Run only through ordinary guarded Blender admission. This compares full expanded
FBX corners/frames/material/UV/colour multiplicity and authored hulls, actual
impostor pixels and complete metadata. It does not claim native cooked receiving.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import subprocess
import sys
from types import SimpleNamespace

GAME=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(GAME/'world'),str(GAME/'world/regions'),str(Path(__file__).resolve().parent)]
import yori  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from atelier.build_inputs import local_imports  # noqa: E402
from atelier.build_cache import copy_file  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402
from region_mesh_parts import validate  # noqa: E402
import fbx_corners  # noqa: E402


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);sys.modules[name]=result;spec.loader.exec_module(result)
    return result


def revision(root):
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()


def record(path):
    info=path.stat()
    return dict(sha256=sha(path),size=info.st_size,device=info.st_dev,inode=info.st_ino,
                mtime_ns=info.st_mtime_ns,ctime_ns=info.st_ctime_ns)


def snapshot(paths):
    result={}
    for path in sorted(set(paths)):
        if path.is_symlink() or not path.is_file():raise ValueError('Missing or linked explicit proof input: '+str(path))
        result[str(path)]=record(path)
    return result


def compare(control,children):
    old=fbx_corners.polygon_cycles(fbx_corners.read(control))
    new=dict(render=Counter(),collision=Counter())
    for path in children:
        value=fbx_corners.polygon_cycles(fbx_corners.read(path))
        for kind in new:new[kind].update(value[kind])
    if old!=new:
        missing={key:sum((old[key]-new[key]).values()) for key in old}
        extra={key:sum((new[key]-old[key]).values()) for key in old}
        raise ValueError(f'Actual exported corners differ: {control.name}, missing={missing},extra={extra}')
    return dict(render_polygons=sum(old['render'].values()),collision_polygons=sum(old['collision'].values()),
                complete_corner_material_uv_colour_frame_multiplicity=True,
                controls=[dict(path=str(control),sha256=sha(control))],
                children=[dict(path=str(path),sha256=sha(path)) for path in children])


def pixels(path):
    image=bpy.data.images.load(str(path),check_existing=False)
    try:
        image.colorspace_settings.name='Non-Color'
        return tuple(image.size),np.asarray(image.pixels[:],dtype=np.float32)
    finally:bpy.data.images.remove(image)


def assemble_graph(module_path,region,out):
    graph=load('proof_'+region+'_recipe',module_path)
    step=next(step for step in graph.steps(SimpleNamespace(out=out)) if step.name=='world.'+region+'.assembled')
    step.commands[0].fn(SimpleNamespace(out=out),sys.stdout)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--donor',type=Path,required=True)
    parser.add_argument('--donor-head',required=True)
    parser.add_argument('--baseline',default='283329c07')
    parser.add_argument('--forest-textures',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--')+1:])
    repo=GAME.parents[1]
    if os.path.lexists(args.output):raise ValueError('Proof output must be fresh')
    real_directory(args.output.parent)
    if revision(args.donor)!=args.donor_head:raise ValueError('Donor head differs')
    source_head=revision(repo)
    if subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True).strip():
        raise ValueError('Proof source must be clean')
    from material_specs import MATERIALS
    from forest.specs import TUSCAN,FOREST
    donor=args.donor/'build/yorimichi'
    files=[donor/'heightmap.npy',donor/'world.json']
    files.extend(donor/'textures'/value['texture'] for value in MATERIALS.values() if 'texture' in value)
    files.append(donor/'forest/textures/textures.json')
    atlas_report=json.loads(files[-1].read_text())
    atlases=[args.forest_textures/('T_'+args_[-1]+'.png') for args_ in TUSCAN.values()]
    atlas_before=snapshot(atlases+[args.forest_textures/'proof.json'])
    for path in atlases:
        if sha(path)!=atlas_report[path.stem.removeprefix('T_')]['sha256']:
            raise ValueError('Private canonical atlas differs from retained donor report')
    before=snapshot(files)
    current_scripts=[GAME/'world/plan_forest_tree.py',GAME/'world/bake_forest_tree.py',
        GAME/'world/assemble_forest.py',GAME/'world/regions/forest_lake/plan_asset.py',
        GAME/'world/regions/forest_lake/query_data.py',GAME/'world/regions/forest_lake/assemble.py',
        GAME/'world/export_region_piece.py',GAME/'forest_atomic_build.py',GAME/'lake_atomic_build.py']
    closure=set(current_scripts)
    for script in current_scripts:closure.update(local_imports(script,(GAME/'world',GAME/'world/regions')))
    closure.update((GAME/'assets/forest/export-parameters').glob('*.json'))
    closure.add(GAME/'tools/forest_textures.py')
    closure.update(GAME/'assets/environment/textures'/('leaf-'+name+suffix)
        for name in ('olive','oak','cypress','pine') for suffix in ('.jpg','.provenance.json'))
    source_before=snapshot(list(closure))
    args.output.mkdir()
    baselines=args.output/'baselines';baselines.mkdir()
    immutable={}
    legacy=('tools/forest_textures.py','world/build_forest.py','world/asset_mesh.py','world/forest_trees.py','world/forest_impostors.py',
        'world/far_crown.py','world/material_specs.py','world/regions/forest/specs.py',
        'world/regions/forest_lake/build.py','world/regions/forest_lake/details.py',
        'world/regions/forest_lake/layout.py','world/regions/village/mesh.py','world/regions/village/layout.py')
    for relative in legacy:
        data=subprocess.check_output(['git','show',args.baseline+':games/yorimichi/'+relative],cwd=repo)
        path=baselines/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        immutable[relative]=hashlib.sha256(data).hexdigest()
        # Only these two edited original entry modules are loaded from the archive;
        # every other legacy dependency must still be the exact immutable bytes.
        if relative not in ('world/regions/forest_lake/details.py',):
            if (GAME/relative).read_bytes()!=data:raise ValueError('Baseline dependency has changed: '+relative)
    old=args.output/'old';new=args.output/'new'
    for root in (old,new):
        root.mkdir()
        for path in files:
            destination=root/path.relative_to(donor);destination.parent.mkdir(parents=True,exist_ok=True)
            copy_file(path,destination)
            if sha(path)!=sha(destination):raise ValueError('Diagnostic source copy differs')
    for root in (old,new):
        folder=root/'forest/textures';folder.mkdir(parents=True,exist_ok=True)
        for path in atlases:copy_file(path,folder/path.name)
    import asset_mesh as A
    original_mesh=A.Mesh
    yori.OUT=old;yori.TEXTURES=old/'textures';A.TEX=str(yori.TEXTURES)
    A.MATS.clear();A.LEAF_CROPS.clear()
    legacy_forest=load('immutable_forest',baselines/'world/build_forest.py')
    legacy_forest.main()
    from village import mesh as village
    village.R=random.Random(76)
    load('forest_lake.details',baselines/'world/regions/forest_lake/details.py')
    legacy_lake=load('immutable_lake',baselines/'world/regions/forest_lake/build.py')
    legacy_lake.main()
    # Restore real current module closure before the selected logical owners run.
    sys.modules.pop('forest_lake.details',None)
    import forest_lake
    if hasattr(forest_lake,'details'):delattr(forest_lake,'details')
    yori.OUT=new;yori.TEXTURES=new/'textures';A.TEX=str(yori.TEXTURES);A.Mesh=original_mesh
    import plan_forest_tree, bake_forest_tree, assemble_forest, export_region_piece
    parameters=sorted((GAME/'assets/forest/export-parameters').glob('*.json'))
    results={};image_results=[]
    for parameter in parameters:
        name=parameter.stem
        frame=new/'forest-data/records'/(name+'.json')
        for level in range(5):
            key=name if level==0 else name+f'_LOD{level}'
            if level==3:
                bake_forest_tree.main(['--parameters',str(parameter),'--frame',str(frame),
                    '--views',str(new/'forest-data/views'/(name+'.json')),'--output',str(new/'forest-bakes'/name)])
            options=['--parameters',str(parameter),'--level',str(level),'--record',str(new/'forest-data/records'/(key+'.json')),
                     '--output',str(new/'planned_exports/forest'/key)]
            if level:options+=['--frame',str(frame)]
            if level==3:options+=['--proxy',str(new/'forest-data/views'/(name+'.json'))]
            plan_forest_tree.main(options)
            value=validate(new/'planned_exports/forest'/key)
            children=[]
            for row in value['pieces']:
                output=new/'exports/world.forest.export'/row['name']
                export_region_piece.main(['--input',str(new/'planned_exports/forest'/key/row['payload']),'--output',str(output)])
                children.append(output/(row['name']+'.fbx'))
            results[key]=compare(old/'forest'/(key+'.fbx'),children)
        for suffix in [mode+f'-{view}' for mode in ('colour','normal') for view in range(4)]+['_colour','_normal']:
            filename=name+(suffix if suffix.startswith('_') else '-'+suffix)+'.png'
            control=old/'forest'/filename;current=new/'forest-bakes'/name/filename
            size,left=pixels(control);right_size,right=pixels(current)
            if size!=right_size or not np.array_equal(left,right):raise ValueError('Impostor pixels differ: '+filename)
            image_results.append(dict(name=filename,pixels=len(left)//4,control=sha(control),current=sha(current),equal=True))
        print('FOREST FULL CONSERVATION',name,flush=True)
    assemble_graph(GAME/'forest_atomic_build.py','forest',new)
    assemble_forest.main(['--out',str(new),*(item for p in parameters for item in ('--parameters',str(p)))])
    previous=json.loads((old/'forest/trees.json').read_text())
    assembled=json.loads((new/'forest/trees.json').read_text())
    for value in assembled.values():value.pop('trunk_hulls')
    if assembled!=previous:raise ValueError('Forest authored metadata or impostor record differs')
    from forest_lake import query_data,plan_asset,assemble
    query_data.publish(new/'heightmap.npy',new/'world.json',new/'lake-data/queries')
    for name in plan_asset.OWNERS:
        options=['--asset',name,'--record',str(new/'lake-data/records'/(name+'.json')),
                 '--output',str(new/'planned_exports/lake'/name)]
        if name in plan_asset.OWNERS[2:]:options+=['--input',str(new/'lake-data/queries'/(name+'.json'))]
        plan_asset.main(options);value=validate(new/'planned_exports/lake'/name);children=[]
        for row in value['pieces']:
            output=new/'exports/world.lake.export'/row['name']
            export_region_piece.main(['--input',str(new/'planned_exports/lake'/name/row['payload']),'--output',str(output)])
            children.append(output/(row['name']+'.fbx'))
        results[name]=compare(old/'forest_lake/assets'/(name+'.fbx'),children)
        print('LAKE FULL CONSERVATION',name,flush=True)
    assemble_graph(GAME/'lake_atomic_build.py','lake',new);assemble.main(['--out',str(new)])
    if snapshot(atlases+[args.forest_textures/'proof.json'])!=atlas_before:
        raise ValueError('Canonical private atlas inputs changed during diagnostic')
    if snapshot(files)!=before or revision(args.donor)!=args.donor_head:raise ValueError('Donor changed during diagnostic')
    if snapshot(list(closure))!=source_before or revision(repo)!=source_head:raise ValueError('Current source changed during diagnostic')
    value=dict(schema=1,complete=True,source_head=source_head,baseline_revision=args.baseline,
        baseline_files=immutable,donor_head=args.donor_head,donor_inputs=before,canonical_atlases=atlas_before,current_source=source_before,
        exports=results,images=image_results,forest_metadata_equal=True,
        scope='exported corner/channel/frame/hull and impostor/query metadata conservation; native receiving separate')
    atomic_json(args.output/'result.json',value)
    print('FOREST LAKE FULL EQUIVALENCE COMPLETE',len(results),len(image_results),flush=True)


if __name__=='__main__':main()
