"""Project the ropeway's exact pre-export final ground and static structure reads.

Consumers load these narrow stdlib manifests in Unreal preflight; geometry and
placement extraction happens only in this explicit ordinary Python producer.
"""
import argparse
import copy
import re
import importlib.util
import json
from pathlib import Path
import sys

WORLD = Path(__file__).resolve().parents[1]
GAME = WORLD.parent
sys.path[:0] = [str(WORLD),str(WORLD / 'regions')]
import yori  # noqa: E402,F401
from atelier import encoded_glb
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory,sha  # noqa: E402
from belmonte import model_sources,scene_inputs,runtime_groups  # noqa: E402

LIBRARY = GAME / 'assets/belmonte'


def layout():
    from belmonte import layout as owner
    return owner


def definitions():
    return model_sources.project(json.loads((LIBRARY / 'source.json').read_text()))


def ground_projection(build,*,models=None,origin=None):
    from gondola.inputs import GROUND_BOUNDS
    models = definitions() if models is None else models
    origin = layout().native_origin() if origin is None else origin
    world = [value/divisor for value,divisor in zip(origin,(100.,-100.,100.))]
    groups = []
    for key,value in models.items():
        if not key.startswith('SM_BM_BT_Terrain_'):continue
        entry = value['source']; low,high = entry['bounds_m']
        x0,y0,x1,y1 = GROUND_BOUNDS
        if high[0]+world[0]<x0 or low[0]+world[0]>x1 or high[1]+world[1]<y0 or low[1]+world[1]>y1:continue
        groups.append(dict(name=key,path='belmonte-source-data/'+key+'.surface'))
    groups.append(dict(name='SM_BM_NorthApron',path='belmonte-source-data/SM_BM_NorthApron.surface'))
    if len(groups)<2:raise ValueError('Final ground source selection has no valley coverage')
    return dict(schema=1,owner='GondolaGroundSources',origin_cm=origin,groups=groups)


def structure_keys(*,scene=None,models=None):
    models=definitions() if models is None else models
    scene=json.loads((LIBRARY/'source.json').read_text()) if scene is None else scene
    by_asset={}
    for row in scene['meshes']:
        if (row['name'] not in models or row['source_asset']!=models[row['name']]['source']['source_asset']
                or row['source_asset'] in by_asset):raise ValueError('Aliased or missing source scene owner')
        by_asset[row['source_asset']]=row['name']
    placed={by_asset[row['asset']] for row in scene['placements']}
    return tuple(key for key in models if key in placed and not key.startswith(('SM_BM_BT_Terrain_','SM_BM_North'))
                 and runtime_groups.logical_collision(key))


def structure_projection(build,*,scene=None,models=None,origin=None,materials=None):
    """Replay original runtime grouping/child-bound selection on pre-export packets."""
    from gondola.structures import BOUNDS,affine,mesh_bounds_data,placed_bounds
    from encoded_region_plan import validate
    from belmonte.prepare_materials import validate as material_library
    build=Path(build)
    scene=scene_inputs.read(build/'belmonte-scene-data/runtime.json',view='runtime') if scene is None else scene
    models=definitions() if models is None else models
    origin=layout().native_origin() if origin is None else origin
    materials=material_library(build/'belmonte-materials') if materials is None else materials
    keys=structure_keys(scene=scene,models=models)
    by_asset={};meshes=[];packets={};bounds={};parents={}
    for parent in keys:
        root=build/'planned_exports/belmonte_models'/parent
        plan=validate(root)
        if plan['parent']!=parent:raise ValueError('Foreign logical model query source')
        prepared=[];collisions=[];identities={}
        for row in plan['pieces']:
            key=row['name'];path=root/row['payload'];identity,data=encoded_glb.read(path,key=key)
            identities[key]=identity
            metadata=identity['metadata'];relative=path.relative_to(build).as_posix()
            packets[key]=(relative,sha(path));bounds[relative]=mesh_bounds_data(data);parents[key]=parent
            if identity['role']=='collision':
                if key!=parent+'_Collision' or metadata.get('parent')!=parent:raise ValueError('Foreign authored whole collision packet')
                collisions.append(key);continue
            entry=metadata['entry']
            if (entry['name']!=key or entry['path']!='glb/'+key+'.glb' or entry['sha256']!=identity['sha256']
                    or entry['triangles']!=identity['triangles'] or entry['bounds_m']!=identity['bounds']
                    or type(metadata.get('collision')) is not bool):raise ValueError('Foreign source model metadata')
            slots=[]
            for label in identity['slots']:
                match=re.fullmatch(r'BM_([0-9]+)_.+',label)
                if not match:raise ValueError('Missing original source material slot')
                slots.append(int(match.group(1)))
            current=dict(models[parent]['source'],**entry)
            if 'collision' not in entry:current.pop('collision',None)
            prepared.append((current,slots,metadata['collision']));meshes.append(current)
        wanted=parent+'_Collision' if models[parent]['source'].get('collision') else None
        if (collisions!=([wanted] if wanted else []) or not prepared or
                [row[2] for row in prepared]!=[not wanted or index==0 for index in range(len(prepared))]):
            raise ValueError('Authored source collision ownership is incomplete')
        owners=[entry for entry,_,_ in prepared if entry.get('collision')]
        if wanted:
            if (len(owners)!=1 or owners[0] is not prepared[0][0] or
                    Path(owners[0]['collision']['path']).name!=wanted+'.glb' or
                    owners[0]['collision']['sha256']!=identities[wanted]['sha256']):
                raise ValueError('Whole authored source collision identity changed')
        elif owners:raise ValueError('Unexpected authored collision owner')
        by_asset[models[parent]['source']['source_asset']]=prepared
    selected_scene=dict(scene,placements=[row for row in scene['placements'] if row['asset'] in by_asset])
    grouped=runtime_groups.groups(selected_scene,copy.deepcopy(materials),by_asset,meshes,[])
    groups=[]
    for group in grouped:
        if type(group.get('plant')) is not bool or type(group.get('collision')) is not bool:
            raise ValueError('Source runtime collision policy is not explicit')
        parent_collision=group.get('parent_collision')
        if type(parent_collision) is not bool or (group['collision'] and not parent_collision):
            raise ValueError('Source parent collision policy is inconsistent')
        if group['plant'] or not parent_collision:continue
        key=group['asset'].rsplit('/',1)[-1].split('.')[0]
        parent=parents[key];entry=next(row for row in meshes if row['name']==key)
        geometry={'visual':packets[key][0]}
        if group['collision']:
            collision=parent+'_Collision' if entry.get('collision') else key
            geometry['collision']=packets[collision][0]
        transforms=[]
        for transform in group['transforms']:
            matrix,offset=affine(transform,origin)
            boxes=[placed_bounds(bounds[path],matrix,offset) for path in set(geometry.values())]
            if any(high[0]>=BOUNDS[0] and low[0]<=BOUNDS[2] and high[1]>=BOUNDS[1] and low[1]<=BOUNDS[3] for low,high in boxes):
                transforms.append(transform)
        if transforms:groups.append(dict(asset=group['asset'],geometry=geometry,transforms=transforms,
                                         plant=False,collision=group['collision'],parent_collision=parent_collision))
    country,country_packets=country_groups(build,origin)
    groups.extend(country)
    groups.sort(key=lambda row:json.dumps({key:row[key] for key in ('asset','geometry','transforms')},sort_keys=True))
    selected={path for row in groups for path in row['geometry'].values()}
    identities={relative:digest for relative,digest in packets.values()}
    identities.update(country_packets)
    return dict(schema=1,owner='GondolaStructureSources',bounds_m=list(BOUNDS),origin_cm=origin,groups=groups,
                sources={path:identities[path] for path in sorted(selected)})


def country_groups(build,origin):
    """Original generated extra: identity instances, selected per actual child box."""
    from gondola.structures import BOUNDS,affine,mesh_bounds_data,placed_bounds
    from encoded_region_plan import validate
    parent='SM_BM_NorthCountry';root=Path(build)/'planned_exports/belmonte_north'/parent
    plan=validate(root)
    if plan['parent']!=parent:raise ValueError('Foreign generated country source owner')
    transform=dict(translation_cm=[0.,0.,0.],rotation_xyzw=[0.,0.,0.,1.],scale=[1.,1.,1.])
    matrix,offset=affine(transform,origin);groups=[];packets={}
    for row in plan['pieces']:
        key=row['name'];path=root/row['payload'];identity,data=encoded_glb.read(path,key=key)
        metadata=identity['metadata'];entry=metadata['entry']
        if (identity['role']!='render' or metadata.get('collision') is not True or entry.get('collision')
                or entry['name']!=key or entry['path']!='glb/'+key+'.glb'
                or entry['sha256']!=identity['sha256'] or entry['triangles']!=identity['triangles']
                or entry['bounds_m']!=identity['bounds']):raise ValueError('Foreign generated country child metadata')
        low,high=placed_bounds(mesh_bounds_data(data),matrix,offset)
        if high[0]<BOUNDS[0] or low[0]>BOUNDS[2] or high[1]<BOUNDS[1] or low[1]>BOUNDS[3]:continue
        relative=path.relative_to(build).as_posix();packets[relative]=sha(path)
        groups.append(dict(asset=f'/Game/Belmonte/Meshes/{key}.{key}',
            geometry=dict(visual=relative,collision=relative),transforms=[transform],
            plant=False,collision=True,parent_collision=True))
    return groups,packets


def structure_paths(build):
    # Product reads own the complete selected planner directories. This deferred
    # census declares every member inspected for bounds selection before exports.
    scene=scene_inputs.read(Path(build)/'belmonte-scene-data/runtime.json',view='runtime')
    paths=[]
    owners=[('belmonte_models',key) for key in structure_keys(scene=scene)]
    owners.append(('belmonte_north','SM_BM_NorthCountry'))
    for namespace,key in owners:
        root=real_directory(Path(build)/'planned_exports'/namespace/key)
        plan=root/'plan.json'
        if plan.is_symlink() or not plan.is_file():raise ValueError('Missing complete source model plan')
        value=json.loads(plan.read_text())
        if value.get('parent')!=key or value.get('complete') is not True:raise ValueError('Foreign source model plan')
        paths.append(plan)
        for row in value['pieces']:
            member=row['payload']
            if Path(member).name!=member or member!=row['name']+'.mesh':raise ValueError('Foreign source model packet')
            paths.append(root/member)
    return paths


def publish(build,kind):
    build = Path(build)
    value = ground_projection(build) if kind == 'ground' else structure_projection(build)
    output = build / 'gondola/world' / (kind+'-sources.json')
    real_directory(output.parent,create=True)
    atomic_json(output,value)
    print('GONDOLA SOURCE READS COMPLETE',kind,len(value['groups']),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind',choices=('ground','structures'))
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args();publish(args.out,args.kind)
