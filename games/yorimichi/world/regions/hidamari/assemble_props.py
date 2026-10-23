"""Preserve the native prop filenames and metadata while gathering independent exports."""
import argparse
import json
from pathlib import Path
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[3]),str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
from atelier import export_assembly
from atelier.atomic_files import atomic_json
from atelier.export_manifest import real_directory,sha,validate as validate_export
from atelier.model_files import flat_files,retain_files
from region_mesh_parts import validate
from hidamari.prop_roster import PROPS,TREES,members


def assemble(out):
    """@cc [owner:fontanierh,label:correctness;performance] complete-independent-hidamari-prop-library
    Every current bounded source/export/texture and complete conifer LOD chain MUST validate
    before copying or retiring files. Assembly MUST preserve the original logical native names,
    fitting/material/collision metadata and strictly decreasing LOD counts/screens. It MUST NOT
    construct geometry or accept missing committed sources. Only exact prior owner diagnostics
    MAY retire; linked, foreign or incomplete trees MUST refuse before any mutation.
    """
    out=Path(out);names=members();root=real_directory(out/'hidamari/props')
    records={};files=[];items=[]
    for name in names:
        value=validate(out/'planned_exports/hidamari_props'/name)
        if [row['name'] for row in value['pieces']]!=[name]:raise ValueError('Prop native membership changed')
        folder=out/'hidamari-prop-data'/name
        parent=name.split('_LOD')[0]
        if flat_files(folder)!={parent+'.png','record.json'}:raise ValueError('Incomplete/foreign selected prop data')
        record=json.loads((folder/'record.json').read_text())
        if (record.get('schema')!=1 or record['name']!=name or record['parent']!=parent
                or record['level'][0]!=value['source_triangles']
                or len(record['hulls'])!=value['source_collision_hulls']):
            raise ValueError('Incomplete/foreign selected prop data')
        records[name]=record
        item=export_assembly.Item(name,out/'exports/world.hidamari_props.export'/name)
        receipt=validate_export(item.root,key=name);piece=value['pieces'][0]
        if (receipt['triangles']!=piece['triangles'] or receipt['bounds']!=[piece['min'],piece['max']]
                or receipt['metadata'].get('geometry_sha256')!=piece['sha256']
                or receipt['metadata'].get('slots')!=value['slots']
                or receipt['metadata'].get('collision_hulls')!=piece['collision_hulls']):
            raise ValueError('Prop export does not match its current source plan')
        items.append(item)
    data={}
    for name in (*PROPS,*TREES):
        base=records[name]
        if base['parent']!=name or base['lod']!=0:raise ValueError('Wrong logical prop base')
        info=dict(base['info'])
        if name in TREES:
            chain=[base,*[records[name+'_LOD'+str(n)] for n in range(1,4)]]
            digest=sha(out/'hidamari-prop-data'/name/(name+'.png'))
            for n,row in enumerate(chain):
                if (row['parent']!=name or row['lod']!=n or row['info']!=base['info'] or row['hulls']
                        or sha(out/'hidamari-prop-data'/row['name']/(name+'.png'))!=digest):
                    raise ValueError('Conifer LOD base/texture policy differs')
            levels=[row['level'] for row in chain]
            if any(levels[i][j]>=levels[i-1][j] for i in range(1,4) for j in (0,1)):
                raise ValueError('Conifer LOD chain must strictly decrease')
            info['lods']=levels
        data[name]=info
        files.append((out/'hidamari-prop-data'/name/(name+'.png'),name+'.png'))
    meshes=out/'hidamari/assembled-props'
    export_assembly.destination_members(meshes,{name+'.fbx' for name in names})
    wanted={'props.json',*(name+'.fbx' for name in names),*(name+'.png' for name in (*PROPS,*TREES))}
    diagnostics={f'view-{name.removeprefix("HD_P_")}-{i}{direction}.png' for name in PROPS
        for i,direction in enumerate(('front','right','back','left'))}
    diagnostics|={f'view-{name}-{i}{direction}.png' for name in ('black_pine_a','black_pine_b','cedar_a','cedar_b')
        for i,direction in enumerate(('front','right','back','left'))}
    diagnostics|={'lods-'+name+'.png' for name in TREES}
    if root.exists() and flat_files(root)-wanted-diagnostics:raise ValueError('Foreign prop assembly destination')
    export_assembly.assemble(items,meshes)
    for name in names:export_assembly.copy_verified(meshes/(name+'.fbx'),root/(name+'.fbx'))
    for source,name in files:export_assembly.copy_verified(source,root/name)
    atomic_json(root/'props.json',data)
    retain_files(root,wanted)
    print('HIDAMARI PROPS COMPLETE',len(data),len(names),'independent exports',flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    assemble(parser.parse_args(argv).out)


if __name__=='__main__':main()
