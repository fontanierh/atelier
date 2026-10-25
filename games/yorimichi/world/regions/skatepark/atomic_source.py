"""Canonical pre-export skate riding/AO/terrain data and selected construction helpers."""
import hashlib
import json
import math
from pathlib import Path
import tempfile
import numpy as np
from atelier.atomic_files import atomic_json, managed_temporary_parent
from atelier.export_manifest import real_directory
from atelier.model_files import regular_files

BOARD=('SM_SkateDeck','SM_SkateTruck','SM_SkateWheel')
PARK=('SM_SkatePier','SM_SkatePierPilings','SM_SkateParkFeatures','SM_SkatePath',
      'SM_SkateParkFurniture','SM_SkateParkPlanting','SM_SkateParkDecals')
AO=('SM_SkatePier','SM_SkateParkFeatures')


def imported_triangle_count(piece):
    """Blender validates duplicate polygons on import; exports retain both windings.

    Count only the importer's exact shared-index face equivalence, without welding
    distinct vertices or changing the complete authored/exported polygon inventory.
    """
    faces={tuple(sorted(face)) for face in piece['faces']}
    return sum(len(face)-2 for face in faces)


def preflight(root,expected):
    root=real_directory(root)
    if root.exists() and regular_files(root)-set(expected):raise ValueError('Foreign canonical skate source data')
    root.mkdir(parents=True,exist_ok=True)
    return root


def clean(value):
    return json.loads(json.dumps(value,default=float,allow_nan=False))


def geometry_sha(mesh):
    digest=hashlib.sha256()
    for value,dtype in ((mesh.verts,'<f8'),([len(face) for face in mesh.faces],'<i4'),
        ([i for face in mesh.faces for i in face],'<i4'),([c for row in mesh.colors for c in row],'<f8'),(mesh.smooth,'?')):
        array=np.asarray(value,dtype=dtype)
        digest.update(str(array.shape).encode()+array.tobytes())
    digest.update(json.dumps(dict(tags=mesh.tags,uv=mesh.uv),sort_keys=True,separators=(',',':')).encode())
    return digest.hexdigest()


def sample_key(x,y):
    return float(x).hex()+','+float(y).hex()


def recorder(function):
    values={}
    def sample(height,x,y):
        key=sample_key(x,y);value=float(function(height,x,y))
        if not math.isfinite(value) or (key in values and values[key]!=value):raise ValueError('Inconsistent canonical terrain query')
        values[key]=value
        return value
    return values,sample


def lookup(packet,name):
    if packet.get('schema')!=1 or packet.get('name')!=name or not isinstance(packet.get('samples'),dict) or not packet['samples']:
        raise ValueError('Missing selected canonical skate terrain samples')
    values=packet['samples'];used=set()
    def sample(height,x,y):
        key=sample_key(x,y)
        if key not in values or type(values[key]) not in (int,float) or not math.isfinite(values[key]):
            raise ValueError('Missing/invalid exact skate terrain sample')
        used.add(key)
        return values[key]
    def complete():
        if used!=set(values):raise ValueError('Selected skate terrain query membership differs')
    return sample,complete


def write_bytes(path,payload):
    real_directory(path.parent,create=True)
    if path.is_symlink() or (path.exists() and not path.is_file()):raise ValueError('Invalid canonical skate source member')
    if path.is_file() and path.read_bytes()==payload:return
    with tempfile.NamedTemporaryFile(dir=managed_temporary_parent(path),prefix='.query-',delete=False) as stream:
        temporary=Path(stream.name);stream.write(payload)
    try:temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)


def material_projection(manifest):
    value=json.loads(Path(manifest).read_text())
    value['painted']={**value['steel'],'metallic':0.}
    result=[]
    for name,row in value.items():
        repeat=row.get('repeat_m')
        if type(repeat) not in (int,float) or not math.isfinite(repeat) or repeat<=0:
            raise ValueError('Invalid current skate material UV scale')
        result.append(dict(name=name,repeat_m=repeat))
    if {row['name'] for row in result}!={'concrete','basalt','wood','steel','ceramic','mural','painted'}:
        raise ValueError('Incomplete original skate material membership')
    return dict(schema=1,materials=result)


def material_objects(path):
    import bpy
    value=json.loads(Path(path).read_text());rows=value.get('materials')
    if value.get('schema')!=1 or not isinstance(rows,list) or len(rows)!=7:
        raise ValueError('Missing canonical skate material geometry data')
    result={}
    for row in rows:
        name=row.get('name');repeat=row.get('repeat_m')
        if name in result or name not in ('concrete','basalt','wood','steel','ceramic','mural','painted') or type(repeat) not in (int,float) or not math.isfinite(repeat) or repeat<=0:
            raise ValueError('Invalid selected skate material geometry data')
        material=bpy.data.materials.new('Pier_'+name);material['repeat_m']=repeat;result[name]=material
    return result


def publish_ao(root):
    """@cc [owner:fontanierh,label:correctness] canonical-skate-ao-before-exports
    The original Pier/Features joint AO MUST be computed from original source geometry,
    with the exact rays, skip tags and ordered corners. Each owner MUST receive only
    its bound AO values. No rendered export MAY supply shading or riding query data.
    """
    from . import features,geom
    root=preflight(root,[*(name+'.json' for name in AO),'report.json'])
    if not features.MOD.available():raise ValueError('Production skate geometry requires every committed library model')
    meshes=[features.pier(),features.park_features()]
    values=geom.bake_ao(meshes,meshes,skip_tags=('rail','railing','pole','lamp','coping'))
    report={}
    for mesh in meshes:
        data=values[mesh.name]
        atomic_json(root/(mesh.name+'.json'),dict(schema=1,name=mesh.name,geometry_sha256=geometry_sha(mesh),values=data))
        report[mesh.name]={'mean':round(float(np.mean([c for row in data for c in row])),3),
            'max':round(float(np.max([c for row in data for c in row])),3),'corners_over_0.3':int(sum(c>.3 for row in data for c in row))}
        print('SKATE CANONICAL AO COMPLETE',mesh.name,len(data),flush=True)
    atomic_json(root/'report.json',report)


def publish_queries(root):
    from . import features,board,build,layout as L
    from village.layout import sample,upper_surface
    root=preflight(root,['SM_SkatePierPilings.json','SM_SkatePath.json','collision.json','logical.json','report.json'])
    if not features.MOD.available():raise ValueError('Production skate queries require every committed library model')
    world,height=L.load_world();layout=L.path_layout(world,height)
    report=dict(board=build.check_board(board.deck(),board.truck(),board.wheel()))
    pier,feats=features.pier(),features.park_features()
    samples,read=recorder(sample);features.pilings(height,sample_fn=read)
    atomic_json(root/'SM_SkatePierPilings.json',dict(schema=1,name='SM_SkatePierPilings',samples=samples))
    samples,read=recorder(upper_surface);path,_,rows=features.path(layout,height,surface_fn=read)
    frame={key:np.asarray(layout[key]).tolist() for key in ('P','s','n','z','road')}
    atomic_json(root/'SM_SkatePath.json',dict(schema=1,name='SM_SkatePath',samples=samples,frame=frame))
    furniture,_=features.gardens('SM_SkateParkFurniture')
    report['furniture_clearance']=build.check_furniture_clearance(furniture,feats)
    rails=L.rails();report['rails']=build.check_rails(rails,[feats]);report['bar_clearance']=build.check_bar_clearance(rails,[pier,feats])
    triangles=[]
    for mesh in (pier,feats):
        for face in mesh.faces:
            for i in range(1,len(face)-1):
                triangles.append([[mesh.verts[k][1],mesh.verts[k][2],mesh.verts[k][0]] for k in (face[0],face[i],face[i+1])])
    collision=dict(triangles=triangles,rails=[[[p[1],p[2],p[0]] for p in rail['points']] for rail in rails],spawn=[-28,0,-23],heading=0)
    write_bytes(root/'collision.json',json.dumps(collision,separators=(',',':')).encode())
    report['profiles']=build.check_profiles();report['path']=build.check_path(layout,rows,height)
    report['path']['house_roof_clearance_m'],report['path']['house_lot_clearance_m']=build.house_clearance(layout,world)
    if report['path']['house_lot_clearance_m']<=0:raise ValueError('Skate path crosses a house lot')
    report['joins']=build.check_joins(pier,feats,path)
    logical=build.park_json(layout,rails)
    from .pieces import validate_logical_contract
    validate_logical_contract(Path(__file__).with_name('park.json'),logical)
    atomic_json(root/'logical.json',logical)
    report['park_json']=dict(origin=logical['origin'],rails=len(rails),rail_points=sum(len(r['points']) for r in rails),
        meshes=[row['name'] for row in logical['meshes']],spawns=logical['spawns'],bytes=Path(__file__).with_name('park.json').stat().st_size)
    atomic_json(root/'report.json',clean(report))
    print('SKATE CANONICAL QUERIES COMPLETE',len(triangles),flush=True)
