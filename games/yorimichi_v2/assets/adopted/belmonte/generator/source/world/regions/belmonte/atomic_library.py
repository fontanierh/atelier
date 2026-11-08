"""Read complete independent Belmonte exports without constructing geometry."""
import json
from pathlib import Path
import re

from atelier import encoded_glb
from atelier.export_manifest import name,real_directory,sha
from atelier.model_files import regular_files
from belmonte.atomic_metadata import entry as runtime_entry


def read(root,*,expected,original):
    """@cc [owner:fontanierh,label:correctness] complete-belmonte-atomic-library
    Assembly MUST require the exact current logical roster and independently
    exported primary inventory, with matching geometry identities/counts and
    complete render/collision ownership. Preserve original source metadata,
    numeric material bindings and single whole-hull ownership on subdivision.
    It MUST NOT export, join, reconstruct or silently substitute a parent.
    """
    root=real_directory(root);assets=real_directory(root/'assets')
    for path in (root/'logical-pieces.json',assets/'manifest.json'):
        if path.is_symlink() or not path.is_file():raise ValueError('Missing atomic Belmonte inventory')
    logical=json.loads((root/'logical-pieces.json').read_text())
    manifest=json.loads((assets/'manifest.json').read_text())
    if (set(logical)!={'schema','parents','ownership','exports'} or logical.get('schema')!=1
            or set(logical.get('parents',{}))!=set(expected)
            or set(logical.get('ownership',{}))!=set(expected) or manifest.get('schema')!=1
            or set(manifest)!={'schema','complete','exports'} or manifest.get('complete') is not True):
        raise ValueError('Incomplete Belmonte logical library')
    if {path.name for path in root.iterdir()}!={'logical-pieces.json','assets'}:
        raise ValueError('Foreign atomic library roots')
    rows=manifest.get('exports',[])
    keys=[name(row['asset']) for row in rows]
    if not keys or len({key.casefold() for key in keys})!=len(keys):raise ValueError('Aliased atomic library')
    union=[key for parent in expected for key in logical['parents'][parent]]
    if len(set(union))!=len(union) or set(union)!=set(keys) or logical.get('exports')!=keys:
        raise ValueError('Belmonte library membership differs')
    if (regular_files(assets)!={'manifest.json',*(key+'.glb' for key in keys)}
            or any(p.is_dir() for p in assets.iterdir())):raise ValueError('Foreign atomic library members')
    receipts={row['asset']:row for row in rows};by_parent={};files={};identities={};meshes=[]
    for parent in expected:
        ownership=logical['ownership'][parent]
        planned=ownership.get('pieces',[])
        if ownership.get('kind')!='encoded_glb' or [r['name'] for r in planned]!=logical['parents'][parent]:
            raise ValueError('Incomplete encoded source ownership')
        prepared=[];totals=dict(render=0,collision=0)
        for piece in planned:
            key=name(piece['name']);row=receipts[key];path=assets/(key+'.glb')
            metadata=row['metadata'];role=metadata['role'];raw=path.read_bytes()
            geometry=encoded_glb.geometry(raw,role=role)
            digest=sha(path)
            if (row['primary']!=path.name or digest!=row['sha256'] or digest!=metadata['geometry_sha256']
                    or geometry['triangles']!=row['triangles'] or geometry['bounds']!=row['bounds']
                    or geometry['slots']!=metadata['slots'] or piece['role']!=role
                    or piece['triangles']!=row['triangles'] or piece['bounds']!=row['bounds']):
                raise ValueError('Atomic Belmonte primary differs from its receipt')
            totals[role]+=row['triangles'];files[path.name]=path;identities[path.name]=digest
            if role=='collision':
                if key!=parent+'_Collision' or metadata.get('parent')!=parent:
                    raise ValueError('Foreign whole collision owner')
                continue
            entry=runtime_entry(piece,metadata)
            if (entry['name']!=key or entry['path']!='glb/'+path.name or entry['sha256']!=digest
                    or entry['triangles']!=row['triangles'] or entry['bounds_m']!=row['bounds']
                    or type(metadata['collision']) is not bool):raise ValueError('Foreign rendered source metadata')
            slots=[]
            for slot in geometry['slots']:
                match=re.fullmatch(r'BM_([0-9]+)_.+',slot)
                if not match:raise ValueError('Missing original numeric material slot')
                slots.append(int(match.group(1)))
            current=dict(original.get(parent,{}),**entry)
            if 'collision' not in entry:current.pop('collision',None)
            prepared.append((current,slots,metadata['collision']));meshes.append(current)
        if (not prepared or totals['render']!=ownership['source_render_triangles']
                or totals['collision']!=ownership['source_collision_triangles']
                or sum(totals.values())!=ownership['source_triangles']):raise ValueError('Incomplete source conservation')
        owners=[row for row,_,_ in prepared if row.get('collision')]
        if totals['collision']:
            if len(owners)!=1 or not prepared[0][0].get('collision') or not prepared[0][2]:
                raise ValueError('Whole collision ownership was not preserved')
            hull=owners[0]['collision']
            if Path(hull['path']).name!=parent+'_Collision.glb' or hull['sha256']!=identities[parent+'_Collision.glb']:
                raise ValueError('Whole collision bytes differ')
        elif owners:raise ValueError('Missing independently exported whole hull')
        wanted=[not totals['collision'] or index==0 for index in range(len(prepared))]
        if [collides for _,_,collides in prepared]!=wanted:
            raise ValueError('Rendered collision policy differs from the logical owner')
        by_parent[parent]=prepared
    return dict(by_parent=by_parent,meshes=meshes,files=files,identities=identities)
