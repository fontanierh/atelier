"""Selected foliage definitions and strict legacy-compatible file assembly (no geometry imports)."""
import json
import hashlib
from pathlib import Path

from atelier.atomic_files import atomic_json
from atelier.export_assembly import copy_verified
from atelier.export_manifest import name as asset_name,validate,real_directory,sha
from atelier.model_files import regular_files,flat_files


def definition_rows(kind,spec,materials):
    """@cc [owner:fontanierh,label:correctness;performance] selected-foliage-definition-fields
    Each authored LOD definition MUST include only its consumed constructor, arguments,
    palette and selected stride/level. Screens, collision policy and sibling strides
    MUST stay in the complete kind policy rather than invalidate unchanged geometry.
    Crown geometry MUST consume the last authored pre-export payload, never an FBX.
    """
    asset_name(kind);sizes=spec['screen_sizes'];grass=spec['generator']=='grass_tuft';crown=spec.get('far_crown')
    if (type(spec['import_trunk_collision']) is not bool or len(sizes)<2 or sizes[0]!=1
            or not all(a>b>0 for a,b in zip(sizes,sizes[1:])) or spec['collision'] not in ('default','complex')):
        raise ValueError('Invalid original foliage policy')
    if not grass and len(spec['strides'])!=len(sizes)-1:raise ValueError('Incomplete authored strides')
    if crown is not None and (set(crown)!={'shape','screen_size'} or crown['shape']!='flat12' or not 0<crown['screen_size']<sizes[-1]):
        raise ValueError('Unsupported original far crown policy')
    palette={slot:materials[slot] for slot in spec['materials']};rows={}
    for level in range(len(sizes)):
        key=kind if level==0 else f'{kind}_LOD{level}'
        row=dict(schema=1,kind=kind,key=key,mode='mesh',level=level,generator=spec['generator'],arguments=spec['arguments'],materials=palette,material_order=list(palette))
        if level and not grass:row['stride']=spec['strides'][level-1]
        rows[key]=row
    if crown:
        key=f'{kind}_LOD{len(sizes)}';rows[key]=dict(schema=1,kind=kind,key=key,mode='crown',materials=palette,material_order=list(palette))
    rows[kind+'_Seed']=dict(schema=1,kind=kind,key=kind+'_Seed',mode='seed',materials=palette,material_order=list(palette))
    policy=dict(schema=1,kind=kind,keys=list(rows),levels=list(rows)[:-1],screen_sizes=sizes+([crown['screen_size']] if crown else []),
                collision=spec['collision'],import_trunk_collision=spec['import_trunk_collision'],crown=bool(crown))
    return rows,policy


def project(kind,spec_path,materials,output):
    rows,policy=definition_rows(kind,json.loads(Path(spec_path).read_text()),materials)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    for key,row in rows.items():atomic_json(output/(key+'.json'),row)
    atomic_json(output/'policy.json',policy)


def assemble(out,kind,policy):
    """@cc [owner:fontanierh,label:correctness] complete-file-only-foliage-kind
    Validate every selected source report, actual regular geometry/material payload
    bytes and atomic export before changing the kind folder. Reports and receipts
    MUST NOT substitute for current selected bytes. Unselected old regular source
    files MAY remain unused; they MUST NOT become current outputs. Copy files only,
    retaining original names and manifest/API fields. Retire only recorded previous
    destination members after complete current publication; unknown destination files
    and missing/altered selected payload/export/query membership MUST refuse.
    """
    out=Path(out);kind=asset_name(kind);folder=real_directory(out/'foliage'/kind);data=real_directory(out/'foliage-source'/kind)
    if policy.get('kind')!=kind or policy.get('schema')!=1:raise ValueError('Foreign foliage policy')
    levels=policy['levels'];keys=policy['keys']
    if (not levels or keys!=levels+[kind+'_Seed'] or levels[0]!=kind or
            levels!=[kind]+[f'{kind}_LOD{i}' for i in range(1,len(levels))] or len(levels)!=len(policy['screen_sizes'])):
        raise ValueError('Incomplete foliage member roster')
    members=flat_files(data)
    required={kind+'.base.json',*(key+suffix for key in keys for suffix in ('.report.json','.npz','.materials.json'))}
    if not required<=members:raise ValueError('Incomplete selected foliage source membership')
    def read(member):
        if member not in members:raise ValueError('Missing selected foliage source report')
        return (data/member).read_bytes()
    base_bytes=read(kind+'.base.json');base=json.loads(base_bytes);reports=[];receipts={}
    for key in keys:
        row=json.loads(read(key+'.report.json'))
        receipt=validate(out/'exports/world.foliage.export'/key,key=key)
        if (row['key']!=key or row['triangles']!=receipt['triangles'] or row['collision_hulls']!=receipt['metadata']['collision_hulls']
                or row['materials']!=receipt['metadata']['slots']):
            raise ValueError('Foliage source/export membership differs')
        if any(row.get(field)!=receipt['metadata'].get(field) or not isinstance(row.get(field),str) or len(row[field])!=64
               for field in ('geometry_sha256','materials_sha256')):
            raise ValueError('Foliage source/export identities differ')
        if any(sha(data/(key+suffix))!=row[field] for suffix,field in (
                ('.npz','geometry_sha256'),('.materials.json','materials_sha256'))):
            raise ValueError('Selected foliage payload differs from source/export identity')
        if key==kind and row.get('base_sha256')!=hashlib.sha256(base_bytes).hexdigest():
            raise ValueError('Foliage base query identity differs')
        receipts[key]=receipt
        if key in levels:reports.append(row)
    counts=[row['triangles'] for row in reports]
    if not all(a>b>0 for a,b in zip(counts,counts[1:])):raise ValueError('Original decreasing LOD triangle gate failed')
    palette=base['materials']
    for row in reports[:-1] if policy['crown'] else reports:
        if set(row['materials'])!=set(palette):raise ValueError('Original authored LOD palette changed')
    if policy['import_trunk_collision'] and base['trunk_collision'] is None:raise ValueError('Missing authored trunk geometry')
    result=dict(triangles=counts,screen_sizes=policy['screen_sizes'],materials=palette,bounds=base['bounds'],
                collision=policy['collision'],import_trunk_collision=policy['import_trunk_collision'],trunk_collision=base['trunk_collision'])
    if policy['crown']:result['crown']=reports[-1]['crown']
    current={key+'.fbx' for key in keys};old=set()
    if folder.exists():
        prior=folder/'manifest.json'
        if prior.is_file() and not prior.is_symlink():
            previous=json.loads(prior.read_text());n=len(previous['triangles'])
            if n<2 or len(previous['screen_sizes'])!=n:raise ValueError('Invalid previous foliage inventory')
            old={kind+'.fbx',kind+'_Seed.fbx',*(f'{kind}_LOD{i}.fbx' for i in range(1,n))}
        if regular_files(folder)-current-old-{'manifest.json'}:raise ValueError('Foreign foliage destination member')
        if any(path.is_dir() for path in folder.iterdir()):raise ValueError('Foliage destination must be flat')
    folder.mkdir(parents=True,exist_ok=True)
    for key,receipt in receipts.items():
        copy_verified(out/'exports/world.foliage.export'/key/receipt['primary'],folder/receipt['primary'])
    for key,receipt in receipts.items():
        if validate(out/'exports/world.foliage.export'/key,key=key)!=receipt:raise ValueError('Atomic foliage export changed during assembly')
    atomic_json(folder/'manifest.json',result)
    for key in old-current:(folder/key).unlink(missing_ok=True)
    return result


def main():
    import argparse
    import runpy
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('project','assemble'))
    parser.add_argument('--kind',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--spec',type=Path)
    parser.add_argument('--materials',type=Path)
    parser.add_argument('--policy',type=Path)
    args=parser.parse_args()
    if args.mode=='project':
        project(args.kind,args.spec,runpy.run_path(str(args.materials))['MATERIALS'],args.output)
    else:assemble(args.output,args.kind,json.loads(args.policy.read_text()))
    print('FOLIAGE '+args.mode.upper()+' COMPLETE '+args.kind,flush=True)


if __name__=='__main__':main()
