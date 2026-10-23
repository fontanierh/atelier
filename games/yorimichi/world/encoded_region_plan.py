"""Bounded encoded-mesh plans share the normal exclusive planner transaction."""
import hashlib
import json
from pathlib import Path

from atelier import encoded_glb
from atelier.export_manifest import name,real_directory,sha,TRIANGLE_LIMIT
from region_plan_files import begin,finish,files,payloads


def publish(root,*,parent,parts):
    """@cc [owner:fontanierh,label:correctness;performance] encoded-logical-plan-before-export
    A selected source MUST publish complete bounded render/collision data before
    independent exports. Preserve each encoded primitive exactly; no sibling export
    is an input. Validate every current packet and the entire old exclusive tree
    before writing, and retire only that source's previously recorded members.
    """
    root=real_directory(root);parent=name(parent)
    prepared=[];seen=set()
    for part in parts:
        key=name(part['name'])
        if key.casefold() in seen:raise ValueError('Duplicate encoded source member')
        seen.add(key.casefold())
        packet=encoded_glb.encode(part['data'],key=key,role=part.get('role','render'),metadata=part.get('metadata'))
        identity,_=encoded_glb.decode(packet,key=key)
        row=dict(name=key,payload=key+'.mesh',sha256=hashlib.sha256(packet).hexdigest(),
                 triangles=identity['triangles'],role=identity['role'],bounds=identity['bounds'])
        prepared.append((row,packet))
    if not prepared or not any(row['role']=='render' for row,_ in prepared):
        raise ValueError('Encoded source requires its complete rendered membership')
    expected=payloads(parent,[row['payload'] for row,_ in prepared],suffix='.mesh')
    begin(root,parent,expected,suffix='.mesh')
    for row,packet in prepared:
        path=root/row['payload']
        if not path.exists() or path.read_bytes()!=packet:path.write_bytes(packet)
    value=dict(schema=1,kind='encoded_glb',parent=parent,complete=True,triangle_limit=TRIANGLE_LIMIT,
        source_triangles=sum(row['triangles'] for row,_ in prepared),
        source_render_triangles=sum(row['triangles'] for row,_ in prepared if row['role']=='render'),
        source_collision_triangles=sum(row['triangles'] for row,_ in prepared if row['role']=='collision'),
        pieces=[row for row,_ in prepared])
    finish(root,value,suffix='.mesh')
    return validate(root)


def validate(root):
    root=real_directory(root)
    if 'plan.json' not in files(root):raise ValueError('Missing encoded source plan')
    value=json.loads((root/'plan.json').read_text())
    if (value.get('schema')!=1 or value.get('kind')!='encoded_glb' or value.get('complete') is not True
            or value.get('triangle_limit')!=TRIANGLE_LIMIT or not value.get('pieces')):
        raise ValueError('Incomplete encoded source plan')
    parent=name(value['parent'])
    expected=payloads(parent,[row['payload'] for row in value['pieces']],suffix='.mesh')
    if files(root)!=expected|{'plan.json'}:raise ValueError('Foreign encoded source members')
    names=set();totals=dict(render=0,collision=0)
    for row in value['pieces']:
        key=name(row['name'])
        if key.casefold() in names or row['payload']!=key+'.mesh':raise ValueError('Aliased encoded source member')
        names.add(key.casefold())
        path=root/row['payload']
        identity,_=encoded_glb.read(path,key=key)
        if (sha(path)!=row['sha256'] or identity['triangles']!=row['triangles']
                or identity['role']!=row['role'] or identity['bounds']!=row['bounds']):
            raise ValueError('Encoded source changed after planning')
        totals[identity['role']]+=identity['triangles']
    if (not totals['render'] or value['source_triangles']!=sum(totals.values())
            or value['source_render_triangles']!=totals['render'] or value['source_collision_triangles']!=totals['collision']):
        raise ValueError('Incomplete encoded source conservation')
    return value


def present(root):
    try:validate(root);return True
    except (OSError,ValueError,KeyError,TypeError):return False
