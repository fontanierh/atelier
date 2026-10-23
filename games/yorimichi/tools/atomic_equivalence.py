"""Independent, fail-closed export/native equivalence across the original production census.

Run this parser in a normal guarded Blender process when the spec contains FBX files.
The harness never launches a producer, imports geometry into an assembly, or changes outputs.
Adapters execute the IMMUTABLE original constructors separately, retain their complete export
census and canonical source packets, and retain actual current serialized exports/native data.
A PASS boolean in an adapter report is not evidence accepted here.

Spec schema 1:
  scope: {recipe: source-binding, census: artifact, guard: guard-binding}
  regions: {original-owner: {baseline_sources: [source-binding], baseline_guard: guard-binding,
    actual_sources: [source-binding], baseline_inputs: [artifact], actual_inputs: [artifact], actual_guard: guard-binding,
    assets: {logical: {baseline: geometry-set, actual: geometry-set,
       baseline_exports: [artifact], actual_exports: [artifact],
       baseline_policy: artifact, actual_policy: artifact,
       native: {baseline: native-set, actual: native-set,
                baseline_guard: guard-binding, actual_guard: guard-binding}}}}}

source-binding = {revision: full-local-Git-SHA, path: repo-relative-file, sha256: SHA256}
artifact = {path: absolute-unlinked-regular-file, sha256: SHA256}
guard-binding = {receipt: artifact, stdout: artifact, marker: nonempty-string,
                 whole_result: artifact}; whole_result JSON must contain exit_code=0.
geometry-set = {packets: [mesh_ir/encoded_glb/static-GLB artifact], query_stage: 'final'}.
Encoded GLB preserves every encoded attribute/type; unsupported transforms/skins refuse.
Native sets use format='unreal_atomic_native_v2' and contain logical, raw_pages,
component_policies, probes, meshes, policy_scope, inputs and saved_packages. The actual
Scripts/atomic_equivalence_capture.py emitter reads each saved source/render LOD, GPU
tangent/binormal basis and cooked triangles through NativeAtomicEquivalence. All file
members except meshes/scope/logical/format are artifact lists, except probes (one artifact).
Fixture policy proves receiving geometry only; production-created components are required
for complete runtime policy. Older MeshIR-only native sets refuse full acceptance.
Policy is explicit JSON {logical, placements, cull, shadow, fade, collision, materials}.
Probes JSON {logical, controls:[{id,kind,input,target,hit}], seams:[{a,b,controls:[ids]}]}.
Each positive probe's hit is {logical,blocking,position,normal,distance}; miss is null.
Control kinds: ray_positive/ray_negative/capsule_positive/capsule_negative/seam_ray/seam_capsule.

The immutable census JSON is {complete:true, groups:{group:[original-owner]}, owners:{
 owner:{models:[logical], captures:{logical:{source_triangles:int, exported:bool}}}}}.
Every capture must be positive and exported; already-atomic models still need evidence,
not an exemption inferred from new manifests. Mandatory groups below are a MINIMUM,
not a claim that this historical list is a complete source census. Missing adapters fail.
"""
import argparse
import base64
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import struct
import sys

import numpy as np

from atelier import mesh_ir
from atelier.atomic_files import atomic_json
from atelier.export_manifest import real_directory

MINIMUM_GROUPS = ('island','hidamari','hidamari_stable','village','southwest','swordcamp','houses',
    'mini_mega','megapark','craterpark','forest_lake','skatepark','treehouse','brinecove','belmonte',
    'hippodrome','forest','zeppelin','gondola','belmonte_train','ferry','world_props')
HEX = re.compile(r'[0-9a-f]{64}')
REVISION = re.compile(r'[0-9a-f]{40}')
GAME = Path(__file__).resolve().parents[1]
REPO = GAME.parents[1]
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024


class EvidenceError(ValueError):
    pass


def require(condition, message):
    if not condition: raise EvidenceError(message)


def finite(value):
    if isinstance(value, bool): return True
    if isinstance(value, (int,float)): return math.isfinite(value)
    if isinstance(value, str) or value is None: return True
    if isinstance(value,(list,tuple)): return all(finite(v) for v in value)
    if isinstance(value,dict): return all(isinstance(k,str) and finite(v) for k,v in value.items())
    return False


def canonical(value):
    require(finite(value), 'Nonfinite or unsupported canonical evidence value')
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def artifact(row):
    require(isinstance(row,dict) and set(row)=={'path','sha256'} and isinstance(row['path'],str)
            and isinstance(row['sha256'],str) and HEX.fullmatch(row['sha256']), 'Invalid artifact identity')
    path=Path(row['path'])
    require(path.is_absolute(), 'Artifact paths must be absolute')
    real_directory(path.parent)
    require(not path.is_symlink() and path.is_file() and 0<path.stat().st_size<=MAX_ARTIFACT_BYTES,
            'Missing, linked, empty or oversized artifact: '+str(path))
    payload=path.read_bytes()
    require(hashlib.sha256(payload).hexdigest()==row['sha256'], 'Artifact bytes differ: '+str(path))
    return payload


def json_artifact(row):
    value=json.loads(artifact(row))
    require(finite(value), 'Nonfinite JSON artifact')
    return value


def source_binding(row,repo=REPO):
    require(isinstance(row,dict) and set(row)=={'revision','path','sha256'}
        and isinstance(row['revision'],str) and REVISION.fullmatch(row['revision'])
        and isinstance(row['sha256'],str) and HEX.fullmatch(row['sha256'])
        and isinstance(row['path'],str), 'Immutable source binding requires a complete revision and byte identity')
    path=Path(row['path'])
    require(not path.is_absolute() and path.as_posix()==row['path'] and '..' not in path.parts
        and path.parts and path.parts[0]!='.git', 'Unsafe immutable source member')
    result=subprocess.run(['git','show',row['revision']+':'+row['path']],cwd=repo,
        capture_output=True,timeout=10,check=False)
    require(result.returncode==0, 'Immutable source unavailable locally (no fetch permitted): '+row['path'])
    require(hashlib.sha256(result.stdout).hexdigest()==row['sha256'], 'Immutable source identity differs: '+row['path'])
    return row


def guard_binding(row):
    require(isinstance(row,dict) and set(row)=={'receipt','stdout','marker','whole_result'}
        and isinstance(row['marker'],str) and row['marker'], 'Guard evidence is incomplete')
    receipt=json_artifact(row['receipt']); whole=json_artifact(row['whole_result'])
    require(receipt.get('state')=='child_exited' and receipt.get('cleanup_complete') is True
        and receipt.get('processes')==[] and receipt.get('footprint_bytes')==0,
        'Native child/whole cleanup is not positively empty')
    late=receipt.get('late_reporters',{})
    require(not late.get('unresolved') and not late.get('unresolved_pids') and not late.get('scan_failed',False),
        'Native reporter cleanup remains uncertain')
    require(type(whole.get('exit_code')) is int and whole['exit_code']==0, 'Whole enclosing invocation did not succeed')
    require(row['marker'].encode() in artifact(row['stdout']), 'Required diagnostic marker absent')


def _f32(values):
    return np.asarray(values,dtype='<f4').tobytes()


def _f64(values):
    return np.asarray(values,dtype='<f8').tobytes()


def _digest(parts):
    h=hashlib.sha256()
    for part in parts:
        h.update(len(part).to_bytes(8,'little'));h.update(part)
    return h.digest()


def face_counter(meta,piece):
    """Complete ordered polygon corners; no tolerance, triangulation, sorting or geometry joins."""
    result=Counter();offset=0
    header=canonical(dict(matrix=meta['matrix'],selection=meta['selection'],
        uv_names=[name for name,_ in piece['uvs']],colour_types=[list(row[:3]) for row in piece['colours']]))
    for polygon,face in enumerate(piece['faces']):
        parts=[header,canonical([meta['slots'][int(piece['materials'][polygon])],bool(piece['smooth'][polygon])])]
        for local,vertex in enumerate(face):
            corner=offset+local
            parts.extend((_f32(piece['positions'][vertex]),_f32(piece['normals'][corner])))
            parts.extend(_f32(values[corner]) for _,values in piece['uvs'])
            parts.extend(_f32(values[vertex if domain=='POINT' else corner])
                         for _,domain,_,values in piece['colours'])
        result[_digest(parts)]+=1;offset+=len(face)
    return result


def hull_counter(hulls):
    """Each whole authored hull is one object; splitting or duplicating it changes multiplicity."""
    require(isinstance(hulls,list), 'Missing complete hull inventory')
    result=Counter()
    for hull in hulls:
        core={'vertices','faces','matrix'};rich=core|{'material_slots','corner_payload'};transformed=rich|{'transform'}
        require(isinstance(hull,dict) and set(hull) in (core,rich,transformed), 'Incomplete authored hull readback')
        vertices=np.asarray(hull['vertices'],dtype='<f8');matrix=np.asarray(hull['matrix'],dtype='<f8')
        faces=hull['faces']
        require(vertices.ndim==2 and vertices.shape[1]==3 and len(vertices)>=4 and np.isfinite(vertices).all()
            and matrix.shape==(4,4) and np.isfinite(matrix).all() and np.array_equal(matrix[3],[0,0,0,1])
            and np.linalg.det(matrix[:3,:3])!=0 and isinstance(faces,list) and faces,
            'Malformed authored hull geometry/frame')
        rows=Counter()
        for face in faces:
            require(isinstance(face,list) and len(face)>=3 and all(type(i) is int and 0<=i<len(vertices) for i in face),
                    'Malformed authored hull face')
            # Starting corner is irrelevant to a whole collision face; winding is retained.
            points=tuple(_f64(vertices[i]) for i in face)
            cycle=min(points[i:]+points[:i] for i in range(len(points)))
            rows[_digest(cycle)]+=1
        geometry_digest=_digest([_f64(matrix),*sorted(_f64(vertex) for vertex in vertices),
            *(_digest([key,str(count).encode()]) for key,count in sorted(rows.items()))])
        if set(hull) in (rich,transformed):
            if 'transform' in hull:
                pose=hull['transform'];fields={'location':3,'scale':3,'rotation_euler':3,'rotation_quaternion':4,'rotation_axis_angle':4}
                require(isinstance(pose,dict) and set(pose)==set(fields)|{'rotation_mode'}
                    and pose['rotation_mode'] in ('XYZ','XZY','YXZ','YZX','ZXY','ZYX','QUATERNION','AXIS_ANGLE')
                    and all(isinstance(pose[key],list) and len(pose[key])==width
                        and all(type(v) in (int,float) and math.isfinite(v) for v in pose[key]) for key,width in fields.items())
                    and all(v!=0 for v in pose['scale']),'Invalid original authored hull TRS components')
                require(_f32(pose['location'])==_f32(matrix[:3,3]),'Authored hull TRS location and original matrix disagree')
            require(isinstance(hull['material_slots'],list) and all(isinstance(v,str) and v for v in hull['material_slots'])
                and isinstance(hull['corner_payload'],str),'Malformed complete authored hull channels')
            try:payload=base64.b64decode(hull['corner_payload'],validate=True)
            except ValueError as error:raise EvidenceError('Malformed authored hull corner payload') from error
            meta,piece=mesh_ir.decode(payload)
            require(meta['asset']=='Collision' and not meta['options'] and not meta['collisions']
                and meta['matrix']==hull['matrix'] and piece['faces']==faces
                and np.array_equal(piece['positions'],np.asarray(vertices,dtype='<f4')),
                'Authored hull core and complete corner payload disagree')
            if hull['material_slots']:
                require(meta['slots']==hull['material_slots'],'Authored hull material table differs')
            else:
                require(len(meta['slots'])==1 and np.all(piece['materials']==0),'Empty hull requires only a validation slot')
                meta=dict(meta,slots=[None])  # Canonical no-material meaning; never export this validation slot.
            channels=face_counter(meta,piece)
            geometry_digest=_digest([b'complete_corners',geometry_digest,
                *(_digest([key,str(count).encode()]) for key,count in sorted(channels.items()))])
        result[geometry_digest]+=1
    return result


def geometry_set(value,*,bounded):
    require(isinstance(value,dict) and set(value)=={'packets','query_stage'} and value['query_stage']=='final'
        and isinstance(value['packets'],list) and value['packets'], 'Missing final canonical geometry packets')
    faces,hulls,collision_faces=Counter(),Counter(),Counter();total=0;names=set();layouts=set()
    for row in value['packets']:
        payload=artifact(row)
        from atelier import encoded_glb
        if payload.startswith(encoded_glb.MAGIC) or payload.startswith(b'glTF'):
            if payload.startswith(encoded_glb.MAGIC):
                identity,data=encoded_glb.decode(payload);key=identity['asset']
            else:data=payload;key=Path(row['path']).stem
            require(key.casefold() not in names,'Duplicate encoded geometry packet');names.add(key.casefold())
            values,count=glb_counter(data)
            if bounded:require(0<count+sum(values['collision'].values())<=32768,'Encoded atomic geometry exceeds triangle budget')
            faces.update(values['render']);collision_faces.update(values['collision']);total+=count
            continue
        meta,piece=mesh_ir.decode(payload)
        require(meta['asset'].casefold() not in names, 'Duplicate canonical mesh packet')
        names.add(meta['asset'].casefold())
        if bounded: require(0<piece['triangles']<=32768, 'Atomic primary exceeds triangle budget')
        faces.update(face_counter(meta,piece));hulls.update(hull_counter(meta['collisions']))
        layouts.add(canonical(dict(selection=meta['selection'],uvs=[n for n,_ in piece['uvs']],
            colours=[list(v[:3]) for v in piece['colours']],matrix=meta['matrix'])))
        total+=piece['triangles']
    require(len(layouts)<=1 and total>0, 'Pieces changed original frame/channel type/selection roles or have no render geometry')
    return dict(faces=faces,hulls=hulls,collision_faces=collision_faces,triangles=total,polygons=sum(faces.values()),layouts=layouts)


def _fbx_helpers():
    path=GAME/'tests/native/fbx_corners.py'
    spec=importlib.util.spec_from_file_location('equivalence_fbx_fields',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def fbx_counter(path):
    """Independently parse serialized FBX; retain only per-polygon digests to bound memory."""
    try:
        from io_scene_fbx import parse_fbx
    except ImportError as error:
        raise EvidenceError('FBX parser unavailable; run this harness in normally guarded Blender') from error
    f=_fbx_helpers();root,_=parse_fbx.parse(str(path))
    objects=f.child(root,b'Objects').elems;table={item.props[0]:item for item in objects}
    require(len(table)==len(objects),'Duplicate FBX object identity')
    links=[item.props for item in f.child(root,b'Connections').elems if item.id==b'C']
    result=dict(render=Counter(),collision=Counter());render_triangles=0
    for geometry in (item for item in objects if item.id==b'Geometry'):
        models=[table[r[2]] for r in links if len(r)==3 and r[0]==b'OO' and r[1]==geometry.props[0]
                and r[2] in table and table[r[2]].id==b'Model']
        require(len(models)==1,'Unbound/ambiguous FBX model frame');model=models[0]
        materials=[f.label(table[r[1]].props[1]) for r in links if len(r)==3 and r[0]==b'OO'
            and r[2]==model.props[0] and r[1] in table and table[r[1]].id==b'Material']
        points=f.vectors(f.property_value(geometry,b'Vertices'),3)
        raw=np.asarray(f.property_value(geometry,b'PolygonVertexIndex'))
        require(raw.ndim==1 and raw.dtype.kind in 'iu' and len(raw)>0 and raw[-1]<0,'Malformed FBX polygons')
        ends=raw<0;vertices=np.where(ends,-raw-1,raw)
        require(np.all(vertices>=0) and np.all(vertices<len(points)),'FBX missing vertex')
        polygons=np.r_[0,np.cumsum(ends[:-1])];layers=[]
        for key,field,indices,width in ((b'LayerElementNormal',b'Normals',b'NormalsIndex',3),
            (b'LayerElementUV',b'UV',b'UVIndex',2),(b'LayerElementColor',b'Colors',b'ColorIndex',4)):
            found=sorted((item for item in geometry.elems if item.id==key),key=lambda n:n.props[0])
            if key==b'LayerElementNormal':require(len(found)==1,'Missing current serialized normals')
            for layer in found:
                label=f.child(layer,b'Name',optional=True)
                label=label.props[0].decode() if label is not None else ''
                layers.append((key.decode(),int(layer.props[0]),label,
                    f.expanded(layer,field,indices,width,vertices,len(points),polygons)))
        material=f.child(geometry,b'LayerElementMaterial',optional=True)
        if material is None:
            require(len(materials)<=1,'Missing material assignment table')
            slots=np.full(len(raw),0 if materials else -1)
        else:
            require(f.property_value(material,b'ReferenceInformationType')==b'IndexToDirect','Unsupported material reference')
            indices=np.asarray(f.property_value(material,b'Materials'));mode=f.property_value(material,b'MappingInformationType')
            require(indices.ndim==1 and indices.dtype.kind in 'iu','Malformed material indices')
            if mode==b'AllSame' and len(indices)==1:slots=np.repeat(indices,len(raw))
            elif mode==b'ByPolygon' and len(indices)==int(polygons.max())+1:slots=indices[polygons]
            else:raise EvidenceError('Incomplete material mapping')
        frame=f.child(model,b'Properties70',optional=True)
        transform=sorted((p.props[0].decode(),[(v.decode() if isinstance(v,bytes) else v) for v in p.props[4:]])
            for p in frame.elems if p.id==b'P') if frame else []
        global_node=f.child(root,b'GlobalSettings')
        global_props=f.child(global_node,b'Properties70')
        axes={b'UpAxis',b'UpAxisSign',b'FrontAxis',b'FrontAxisSign',b'CoordAxis',b'CoordAxisSign',
            b'OriginalUpAxis',b'OriginalUpAxisSign',b'UnitScaleFactor',b'OriginalUnitScaleFactor'}
        global_frame=sorted((p.props[0].decode(),list(p.props[4:])) for p in global_props.elems
            if p.id==b'P' and p.props[0] in axes)
        require({b'UpAxis',b'UpAxisSign',b'FrontAxis',b'FrontAxisSign',b'CoordAxis',b'CoordAxisSign',b'UnitScaleFactor'}<=
            {p.props[0] for p in global_props.elems if p.id==b'P'},'FBX global axis/unit frame is incomplete')
        header=canonical(dict(transform=transform,global_frame=global_frame,layers=[list(row[:3]) for row in layers]))
        collision=f.label(model.props[1]).startswith('UCX_')
        counter=result['collision' if collision else 'render'];parts=[];face_corners=0
        for index,vertex in enumerate(vertices):
            slot=int(slots[index]);require(-1<=slot<len(materials) and (slot!=-1 or not materials),'Missing FBX material binding')
            face_corners+=1
            parts.extend((_f64(points[vertex]),canonical(materials[slot] if slot>=0 else None)))
            parts.extend(_f64(values[index]) for *_,values in layers)
            if ends[index]:
                require(len(parts)>=3*(2+len(layers)),'Short serialized polygon')
                counter[_digest([header,*parts])]+=1
                if not collision:render_triangles+=face_corners-2
                parts=[];face_corners=0
    require(result['render'],'Serialized file has no positive render geometry')
    return result,render_triangles



def glb_counter(data):
    """Compare every encoded static corner attribute/type and material/texture binding."""
    from atelier.gltf import glb_parts
    from atelier.gltf_partition import COMPONENTS, WIDTHS
    doc,binary=glb_parts(data)
    require(len(doc.get('buffers',[]))==1 and 'uri' not in doc['buffers'][0]
        and doc['buffers'][0].get('byteLength',len(binary))<=len(binary)
        and not doc.get('extensions') and not doc.get('skins') and not doc.get('animations')
        and len(doc.get('nodes',[]))==1 and len(doc.get('meshes',[]))==1,
        'Missing GLB static identity-node adapter')
    node=doc['nodes'][0]
    require(set(node)<={'mesh','name','extras'} and node.get('mesh')==0,
        'GLB frame/children require a complete transform adapter')
    scenes=doc.get('scenes',[])
    require(len(scenes)==1 and scenes[0].get('nodes')==[0] and doc.get('scene',0)==0,'GLB scene membership differs')
    def view(index):
        require(type(index) is int and 0<=index<len(doc['bufferViews']),'Invalid GLB buffer view')
        row=doc['bufferViews'][index];offset=row.get('byteOffset',0);size=row['byteLength']
        require(type(offset) is int and type(size) is int and offset>=0 and size>=0
            and row.get('buffer',0)==0 and not row.get('extensions')
            and offset+size<=doc['buffers'][0]['byteLength'],'Escaping GLB buffer extent')
        return row,binary[offset:offset+size]
    decoded={}
    def accessor(index):
        require(type(index) is int and 0<=index<len(doc['accessors']),'Invalid GLB accessor')
        if index in decoded:return decoded[index]
        row=doc['accessors'][index]
        require(set(row)<={'bufferView','byteOffset','componentType','normalized','count','type','min','max','name','extras'},
            'Unsupported/missing GLB channel fields')
        require(row['componentType'] in COMPONENTS and row['type'] in WIDTHS,'Unsupported GLB channel type')
        code,size=COMPONENTS[row['componentType']];width=WIDTHS[row['type']];count=row['count'];offset=row.get('byteOffset',0)
        descriptor,payload=view(row['bufferView']);stride=descriptor.get('byteStride',width*size)
        require(type(count) is int and count>0 and type(offset) is int and offset>=0 and type(stride) is int
            and stride>=width*size and offset%size==0 and descriptor.get('byteOffset',0)%size==0
            and offset+(count-1)*stride+width*size<=len(payload),'Incomplete GLB channel extent')
        rows=[payload[offset+i*stride:offset+i*stride+width*size] for i in range(count)]
        values=[struct.unpack('<'+code*width,current) for current in rows]
        require(all(math.isfinite(v) for current in values for v in current),'Nonfinite GLB channel')
        decoded[index]=(row,rows,values);return decoded[index]
    images=[]
    for image in doc.get('images',[]):
        require('uri' not in image and 'bufferView' in image,'Unbound external GLB texture')
        _,payload=view(image['bufferView']);images.append(dict(sha256=hashlib.sha256(payload).hexdigest(),mime=image.get('mimeType')))
    texture_identity=canonical(dict(images=images,textures=doc.get('textures',[]),samplers=doc.get('samplers',[])))
    result=dict(render=Counter(),collision=Counter());triangles=0
    primitives=doc['meshes'][0].get('primitives',[]);require(primitives,'Missing GLB primitives')
    for primitive in primitives:
        require(set(primitive)<={'attributes','indices','material','mode','extras'} and primitive.get('mode',4)==4,
            'GLB morph/compression/nontriangle adapter missing')
        attributes={key:accessor(index) for key,index in sorted(primitive['attributes'].items())}
        require('POSITION' in attributes,'Missing GLB positions');position=attributes['POSITION'][0]
        require(position['componentType']==5126 and position['type']=='VEC3' and not position.get('normalized',False),
            'GLB positions changed type')
        count=position['count'];require(all(row['count']==count for row,_,_ in attributes.values()),'GLB corner channel count differs')
        index,_,values=accessor(primitive['indices'])
        require(index['type']=='SCALAR' and index['componentType'] in (5121,5123,5125)
            and not index.get('normalized',False) and len(values)%3==0,'GLB triangle indices differ')
        material_index=primitive.get('material')
        collision=material_index is None
        if not collision:
            require(type(material_index) is int and 0<=material_index<len(doc.get('materials',[])), 'Missing GLB material binding')
            require('NORMAL' in attributes,'Missing GLB render corner normals')
        material=None if collision else doc['materials'][material_index]
        header=canonical(dict(material=material,attributes=[(key,row['componentType'],row['type'],row.get('normalized',False))
            for key,(row,_,_) in attributes.items()],frame='identity'))
        target=result['collision' if collision else 'render']
        for start in range(0,len(values),3):
            ids=[values[start+i][0] for i in range(3)]
            require(all(type(i) is int and 0<=i<count for i in ids),'GLB triangle references absent vertex')
            parts=[header,texture_identity]
            for vertex in ids:parts.extend(rows[vertex] for _,rows,_ in attributes.values())
            target[_digest(parts)]+=1
            if not collision:triangles+=1
    require(result['render'] or result['collision'],'GLB contains no geometry')
    return result,triangles


def serialized_set(rows):
    require(isinstance(rows,list) and rows,'Missing actual serialized mesh exports')
    result=dict(render=Counter(),collision=Counter(),triangles=0);seen=set()
    for row in rows:
        artifact(row);path=Path(row['path'])
        require(path not in seen,'Duplicate serialized mesh file');seen.add(path)
        if path.suffix.lower()=='.fbx':values,count=fbx_counter(path)
        elif path.suffix.lower()=='.glb':values,count=glb_counter(artifact(row))
        else:raise EvidenceError('Serialized format adapter is missing: '+path.suffix)
        artifact(row)  # Refuse an input replacement during parse.
        for kind in ('render','collision'):result[kind].update(values[kind])
        result['triangles']+=count
    return result


def triangles_counter(value):
    points=np.asarray(value,dtype='<f4')
    require(points.ndim==3 and points.shape[1:]==(3,3) and len(points)>0 and np.isfinite(points).all(),
        'Missing actual cooked complex triangle geometry')
    result=Counter()
    for tri in points:
        # A triangle's first vertex may rotate; reversing the winding still differs.
        rows=tuple(_f32(p) for p in tri);cycle=min(rows[i:]+rows[:i] for i in range(3))
        result[_digest(cycle)]+=1
    return result


def native_hulls(value):
    require(isinstance(value,list),'Missing complete actual simple-hull readbacks')
    result=Counter()
    for row in value:
        require(isinstance(row,dict) and row.get('kind') in ('convex','box','sphere','capsule')
            and set(row) in ({'kind','geometry'},{'kind','geometry','authored_vertices'})
            and ('authored_vertices' not in row or row['kind']=='convex'),'Unknown/incomplete native collision primitive')
        if row['kind']=='convex':
            count=hull_counter([row['geometry']])
            authored=[]
            if 'authored_vertices' in row:
                points=np.asarray(row['authored_vertices'],dtype='<f8')
                require(points.ndim==2 and points.shape[1]==3 and len(points)>=4 and np.isfinite(points).all(),'Missing complete authored native convex vertices')
                authored=sorted(_f64(point) for point in points)
            result.update((_digest([b'convex',key,*authored]) for key in count.elements()))
        else:
            expected={'matrix','size'} if row['kind']=='box' else {'matrix','radius'} if row['kind']=='sphere' else {'matrix','radius','length'}
            require(isinstance(row['geometry'],dict) and set(row['geometry'])==expected,'Incomplete simple primitive geometry')
            matrix=np.asarray(row['geometry']['matrix'],dtype=float)
            require(matrix.shape==(4,4) and np.isfinite(matrix).all() and np.array_equal(matrix[3],[0,0,0,1])
                and np.linalg.det(matrix[:3,:3])!=0,'Invalid native primitive frame')
            dimensions=row['geometry'].get('size',[row['geometry'].get('radius'),row['geometry'].get('length',1)])
            require(isinstance(dimensions,list) and all(type(v) in (int,float) and math.isfinite(v) and (v>=0 if row['kind']=='capsule' and i==1 else v>0)
                    for i,v in enumerate(dimensions))
                and (row['kind']!='box' or len(dimensions)==3),'Invalid native primitive dimensions')
            result[_digest([canonical(row)])]+=1
    return result


def policy(row,logical):
    value=json_artifact(row)
    require(isinstance(value,dict) and set(value)=={'logical','placements','cull','shadow','fade','collision','materials'}
        and value['logical']==logical and isinstance(value['placements'],list)
        and all(value[field] is not None and not (isinstance(value[field],(dict,list,str)) and not value[field])
                for field in ('cull','shadow','fade','collision'))
        and isinstance(value['materials'],list) and value['materials'], 'Incomplete logical placement/material/culling policy')
    return canonical(value)


def compare_probes(before,after,logical,meshes,baseline_meshes=None,expected_seams=None):
    """Require exact owned controls and independently derived split seam adjacency."""
    def read(value, allowed):
        require(isinstance(value,dict) and set(value)=={'logical','controls','seams'} and value['logical']==logical
            and isinstance(value['controls'],list) and value['controls'] and isinstance(value['seams'],list),
            'Missing native positive/negative/seam controls')
        result={}
        for row in value['controls']:
            require(isinstance(row,dict) and set(row)=={'id','kind','input','target','hit'}
                and isinstance(row['id'],str) and row['id'] and row['id'] not in result
                and row['kind'] in ('ray_positive','ray_negative','capsule_positive','capsule_negative','seam_ray','seam_capsule')
                and isinstance(row['input'],dict) and row['input'] and row['target'] in allowed,'Malformed native probe')
            negative=row['kind'].endswith('_negative');hit=row['hit']
            if negative:require(hit is None,'Negative collision control unexpectedly blocks')
            else:
                require(isinstance(hit,dict) and set(hit)=={'logical','blocking','position','normal','distance'}
                    and hit['logical']==logical and hit['blocking'] is True
                    and isinstance(hit['position'],list) and len(hit['position'])==3
                    and isinstance(hit['normal'],list) and len(hit['normal'])==3
                    and type(hit['distance']) in (int,float) and hit['distance']>=0,'Owned positive control did not hit its source')
            require(finite(row),'Nonfinite native query/input/readback')
            fields={'start','end','channel','trace_complex'}
            capsule='capsule' in row['kind']
            if capsule:fields|={'radius_cm','half_height_cm','orientation'}
            query=row['input']
            require(set(query)==fields and isinstance(query['channel'],str) and query['channel']
                and type(query['trace_complex']) is bool and all(isinstance(query[k],list) and len(query[k])==3
                and all(type(v) in (int,float) for v in query[k]) for k in ('start','end')),
                'Incomplete actual query parameters')
            start=np.asarray(query['start'],dtype=float);end=np.asarray(query['end'],dtype=float)
            length=float(np.linalg.norm(end-start));require(length>0,'Empty native query segment')
            if capsule:
                require(type(query['radius_cm']) in (int,float) and query['radius_cm']>0
                    and type(query['half_height_cm']) in (int,float) and query['half_height_cm']>=query['radius_cm']
                    and isinstance(query['orientation'],list) and len(query['orientation'])==4
                    and abs(sum(v*v for v in query['orientation'])-1.)<1e-5,'Invalid capsule shape/orientation')
            if hit is not None:
                require(hit['distance']<=length+.001 and abs(sum(v*v for v in hit['normal'])-1.)<1e-4,
                    'Invalid native hit normal/distance')
            result[row['id']]=row
        require({'ray_positive','ray_negative','capsule_positive','capsule_negative'}<=
                {row['kind'] for row in result.values()},'Missing positive/negative ray/capsule coverage')
        return result
    original=read(before, meshes if baseline_meshes is None else baseline_meshes);current=read(after, meshes)
    require(set(original)==set(current),'Original/current native probe inventory differs')
    for key in original:
        require({k:v for k,v in original[key].items() if k!='target'}==
                {k:v for k,v in current[key].items() if k!='target'},'Native ray/capsule result differs: '+key)
    for target in meshes:
        kinds={row['kind'] for row in current.values() if row['target']==target}
        require(kinds & {'ray_positive','seam_ray'} and kinds & {'capsule_positive','seam_capsule'},
            'Each native mesh needs its own positive ray AND capsule control')
    found=set()
    for seam in after['seams']:
        require(isinstance(seam,dict) and set(seam)=={'a','b','controls'} and seam['a'] in meshes
            and seam['b'] in meshes and seam['a']!=seam['b'] and isinstance(seam['controls'],list),
            'Malformed native seam adjacency')
        pair=tuple(sorted((seam['a'],seam['b'])))
        require(pair not in found,'Duplicate native seam adjacency');found.add(pair)
        ids=seam['controls'];require(len(set(ids))==len(ids) and all(key in current for key in ids),'Missing native seam control')
        for target in pair:
            kinds={current[key]['kind'] for key in ids if current[key]['target']==target}
            require({'seam_ray','seam_capsule'}<=kinds,'Each native seam neighbor needs positive ray AND capsule controls')
    if expected_seams is not None:
        require(found==expected_seams,'Native seam census differs from actual source-edge ownership')
    elif len(meshes)>1:
        require(found,'Split native union has no seam coverage')
        require(set(v for pair in found for v in pair)==set(meshes),'Some split native meshes have no seam/boundary controls')
    return len(current)


def seam_adjacency(geometry,owners):
    """Discover actual shared face edges across native pieces; do not trust a claimed seam list."""
    require(len(geometry['packets'])==len(owners),'Missing native packet ownership')
    edges={};pairs=set()
    for row,owner in zip(geometry['packets'],owners):
        meta,piece=mesh_ir.decode(artifact(row));matrix=np.asarray(meta['matrix'],dtype='<f8')
        positions=piece['positions'] @ matrix[:3,:3].T+matrix[:3,3]
        for face in piece['faces']:
            vertices=[_f32(positions[i]) for i in face]
            for first,second in zip(vertices,vertices[1:]+vertices[:1]):
                if first==second:continue
                edge=tuple(sorted((first,second)))
                previous=edges.setdefault(edge,set())
                pairs.update(tuple(sorted((owner,other))) for other in previous if owner!=other)
                previous.add(owner)
    return pairs



def _native_corner_counter(data,slots,lod):
    require(isinstance(data,dict) and set(data)=={'kind','uv_count','color_encoding','triangles'}
        and data['kind'] in ('mesh_description','render_buffers') and type(data['uv_count']) is int
        and 0<=data['uv_count']<=32 and isinstance(data['triangles'],list),'Missing complete native corner channels')
    gpu=data['kind']=='render_buffers';encoding=data['color_encoding']
    require(encoding in (('srgb_uint8','absent') if gpu else ('linear_float32',)),'Unknown native color storage')
    header=canonical(dict(kind=data['kind'],uv_count=data['uv_count'],color_encoding=encoding,lod=lod,space='asset_local_cm'))
    result=Counter();edges=[]
    for triangle in data['triangles']:
        require(isinstance(triangle,dict) and set(triangle)=={'material','corners','hard_edges'}
            and type(triangle['material']) is int and 0<=triangle['material']<len(slots)
            and isinstance(triangle['corners'],list) and len(triangle['corners'])==3,'Malformed actual native triangle')
        hard=triangle['hard_edges']
        require(hard is None if gpu else isinstance(hard,list) and len(hard)==3 and all(type(v) is bool for v in hard),
            'Missing actual saved edge hardness/readback representation')
        corners=[];positions=[]
        for index,corner in enumerate(triangle['corners']):
            require(isinstance(corner,dict) and set(corner)=={'position','normal','tangent','color','uvs'}
                and all(isinstance(corner[key],list) and len(corner[key])==width for key,width in
                    (('position',3),('normal',4 if gpu else 3),('tangent',4)))
                and isinstance(corner['uvs'],list) and len(corner['uvs'])==data['uv_count']
                and all(isinstance(v,list) and len(v)==2 for v in corner['uvs']) and finite(corner),
                'Missing actual native position/normal/tangent/binormal/UV values')
            if encoding=='absent':require(corner['color'] is None,'Absent GPU color buffer was fabricated')
            else:require(isinstance(corner['color'],list) and len(corner['color'])==4,'Missing actual native color values')
            if encoding=='srgb_uint8':require(all(type(v) in (int,float) and int(v)==v and 0<=v<=255 for v in corner['color']),
                'Malformed actual packed native color')
            parts=[_f32(corner[key]) for key in ('position','normal','tangent')]
            parts.extend(_f32(uv) for uv in corner['uvs'])
            parts.append(b'absent' if corner['color'] is None else _f32(corner['color']))
            if hard is not None:parts.append(canonical(hard[index]))
            corners.append(_digest(parts));positions.append(_f32(corner['position']))
        cycle=min(tuple(corners[i:]+corners[:i]) for i in range(3))
        result[_digest([header,canonical(slots[triangle['material']]),*cycle])]+=1
        edges.extend(tuple(sorted((positions[i],positions[(i+1)%3]))) for i in range(3) if positions[i]!=positions[(i+1)%3])
    return result,edges


def _native_policy(rows,info,logical,scope):
    require(rows,'Actual native component policy is missing')
    groups={mesh:Counter() for mesh in info};materials={};placements={};culls={};shadows={};fades={};collisions={}
    for row in rows:
        require(isinstance(row,dict) and row.get('mesh') in info and row.get('policy_scope')==scope
            and isinstance(row.get('instances'),list) and isinstance(row.get('matrix'),list)
            and isinstance(row.get('primitive_data'),list) and isinstance(row.get('responses'),list)
            and isinstance(row.get('material_bindings'),list) and len(row['material_bindings'])==len(info[row['mesh']]['slots'])
            and type(row.get('cast_shadow')) is bool and type(row.get('visible')) is bool,'Incomplete observed native component policy')
        if scope=='production':require(isinstance(row.get('owner_class'),str) and row['owner_class'].startswith('/Script/Yorimichi.'),
            'Fixture actors cannot certify production runtime policy')
        instances=row['instances'] if row['instances'] else [row['matrix']]
        require(all(isinstance(matrix,list) and np.asarray(matrix).shape==(4,4) for matrix in instances),'Missing actual native instance transforms')
        mode=row['primitive_data'][0] if row['primitive_data'] else 0.
        fade=dict(mode=mode)
        if mode==1:  # SeeThrough.cpp FadeInstances consumes logical bounds; other modes consume their vertex/lens data.
            if len(row['primitive_data'])>=8 and row['primitive_data'][7]==1:
                fade['center']=row['primitive_data'][1:4];fade['extent']=row['primitive_data'][4:7]
            else:
                box=row['mesh_bounds'];fade['center']=[(a+b)/2 for a,b in zip(*box)];fade['extent']=[(b-a)/2 for a,b in zip(*box)]
        cull={key:row[key] for key in ('min_draw_distance','max_draw_distance','wpo_disable_distance')}
        for key in ('instance_min_draw','instance_start_cull','instance_end_cull','instance_lod_scale'):
            if key in row:cull[key]=row[key]
        collision={key:row[key] for key in ('collision_enabled','object_channel','responses')}
        state=dict(cull=cull,shadow=row['cast_shadow'],fade=fade,collision=collision,visible=row['visible'],lighting=row['lighting_channels'])
        signature=hashlib.sha256(canonical(state)).hexdigest()
        group=canonical(dict(state=state,instances=instances))
        groups[row['mesh']][group]+=1
        placements[signature]=instances;culls[signature]=cull;shadows[signature]=dict(cast=row['cast_shadow'],visible=row['visible'],lighting=row['lighting_channels'])
        fades[signature]=fade;collisions[signature]=collision
        for slot,path in zip(info[row['mesh']]['slots'],row['material_bindings']):
            require(isinstance(path,str) and path,'Actual component material binding is missing')
            previous=materials.setdefault(slot['name'],path)
            require(previous==path,'Ambiguous per-instance/child material overrides require a complete face-placement adapter')
    require(all(groups.values()),'Some native meshes have no actual component policy')
    first=next(iter(groups.values()))
    require(all(group==first for group in groups.values()),'Split pieces changed logical instance/cull/shadow/fade/collision groups')
    return dict(logical=logical,placements=[dict(group=key,instances=placements[key]) for key in sorted(placements)],
        cull=culls,shadow=shadows,fade=fades,collision=collisions,materials=[list(v) for v in sorted(materials.items())])


def native_raw_set(value,logical):
    require(isinstance(value,dict) and set(value)=={'format','logical','raw_pages','component_policies','probes','meshes','policy_scope','inputs','saved_packages'}
        and value['format']=='unreal_atomic_native_v2' and value['logical']==logical
        and isinstance(value['meshes'],list) and value['meshes'] and len(set(value['meshes']))==len(value['meshes'])
        and value['policy_scope'] in ('fixture','production') and isinstance(value['raw_pages'],list) and value['raw_pages'],
        'Missing executable native capture descriptor')
    for row in [*value['inputs'],*value['saved_packages']]:artifact(row)
    grouped={mesh:{} for mesh in value['meshes']};seen=set()
    for binding in value['raw_pages']:
        page=json_artifact(binding)
        require(isinstance(page,dict) and page.get('schema')==1 and page.get('logical')==logical and page.get('asset') in grouped
            and type(page.get('lod')) is int and page['lod']>=0 and type(page.get('first')) is int and page['first']>=0,
            'Foreign or malformed actual native geometry page')
        identity=(page['asset'],page['lod'],page['first']);require(identity not in seen,'Duplicate native geometry page');seen.add(identity)
        grouped[page['asset']].setdefault(page['lod'],[]).append(page)
    source_lods={};render_lods={};cooked=Counter();hulls=Counter();edge_owners={};seams=set();settings=set();info={};source_presence={}
    for mesh,lods in grouped.items():
        require(0 in lods,'Missing native LOD0 snapshot')
        initial=sorted(lods[0],key=lambda p:p['first'])[0]
        require(initial['first']==0 and isinstance(initial.get('settings'),dict),'Missing native initial page/settings')
        count=initial['settings']['lods']
        require(type(count) is int and count>0 and set(lods)==set(range(count)),'Native LOD census is incomplete')
        require(initial.get('hulls_complete') is True,'Complete actual native hull readback is missing')
        hulls.update(native_hulls(initial['hulls']));info[mesh]=dict(slots=initial['slots'])
        for lod,pages in sorted(lods.items()):
            pages.sort(key=lambda p:p['first']);base=pages[0]
            require(type(base.get('source_available')) is bool and (lod!=0 or base['source_available']),
                'Saved native LOD0 MeshDescription is unavailable')
            counts=[base[key] for key in ('source_count','render_count','cooked_count')]
            require(all(type(v) is int and v>=0 for v in counts) and counts[1]>0 and (lod==0 or counts[2]==0),
                'Missing actual native geometry counts')
            require(bool(counts[0])==base['source_available'],'Saved source availability/count contradicts readback')
            maximum=base['maximum'];require(type(maximum) is int and 0<maximum<=32768,'Invalid native page budget')
            require([p['first'] for p in pages]==list(range(0,max(counts),maximum)),'Native pages do not cover all actual triangles')
            slots=base['slots'];require(isinstance(slots,list) and slots and all(set(v)=={'name','material'} for v in slots),'Missing actual native material bindings')
            require(base['settings'].get('nanite_enabled') is False and isinstance(base['settings'].get('lod_screen_sizes'),list)
                and len(base['settings']['lod_screen_sizes'])==count,'Actual native renderer/LOD settings absent')
            normalized=dict(base['settings']);normalized['complex_proxy']=bool(normalized['complex_proxy'])
            settings.add(canonical(dict(lod=lod,settings=normalized)));source_presence.setdefault(lod,set()).add(base['source_available'])
            for page in pages:
                require(all(page[key]==base[key] for key in ('source_count','render_count','cooked_count','source_available','maximum','slots','settings','bounds')),
                    'Actual native geometry changed during capture')
                for field,index in (('source',0),('render',1),('cooked',2)):
                    observed=page[field];rows=observed['triangles'] if isinstance(observed,dict) else observed
                    expected=max(0,min(maximum,counts[index]-page['first']))
                    if field=='source' and observed is None and expected==0:continue
                    require(isinstance(rows,list) and len(rows)==expected,'Missing native page triangle/channel coverage')
                    if field=='cooked':
                        if rows:cooked.update(triangles_counter(rows))
                        continue
                    faces,edges=_native_corner_counter(observed,slots,lod)
                    (source_lods if field=='source' else render_lods).setdefault(lod,Counter()).update(faces)
                    if field=='source' and lod==0:
                        for edge in edges:
                            owners=edge_owners.setdefault(edge,set());seams.update(tuple(sorted((mesh,other))) for other in owners if other!=mesh);owners.add(mesh)
                if page['first'] or lod:require(page['hulls']==[] and page['hulls_complete'] is False,'Native hulls duplicated on later pages/LODs')
    policies=[json_artifact(row) for row in value['component_policies']]
    normalized_policy=_native_policy(policies,info,logical,value['policy_scope'])
    return dict(source_lods=source_lods,render_lods=render_lods,cooked=cooked,hulls=hulls,policy=canonical(normalized_policy),
        probes=json_artifact(value['probes']),meshes=value['meshes'],seams=seams,settings=settings,
        source_presence=source_presence,basis_complete=True,runtime_complete=value['policy_scope']=='production')


def native_set(value,logical):
    if isinstance(value,dict) and value.get('format')=='unreal_atomic_native_v2':return native_raw_set(value,logical)
    require(isinstance(value,dict) and set(value)=={'render','cooked','hulls','policy','probes','meshes','packet_owners'}
        and isinstance(value['meshes'],list) and value['meshes'] and all(isinstance(v,str) and v for v in value['meshes'])
        and len(set(value['meshes']))==len(value['meshes']),'Missing complete native receiving snapshots')
    require(isinstance(value['packet_owners'],list) and set(value['packet_owners'])==set(value['meshes'])
        and len(value['packet_owners'])==len(value['render']['packets']),'Native snapshots omit or invent a native mesh')
    return dict(basis_complete=False,runtime_complete=False,seams=seam_adjacency(value['render'],value['packet_owners']),render=geometry_set(value['render'],bounded=False),cooked=triangles_counter(json_artifact(value['cooked'])),
        hulls=native_hulls(json_artifact(value['hulls'])),policy=policy(value['policy'],logical),
        probes=json_artifact(value['probes']),meshes=value['meshes'])


def compare_native(value,logical):
    require(isinstance(value,dict) and set(value)=={'baseline','actual','baseline_guard','actual_guard'},'Native acceptance coverage absent')
    guard_binding(value['baseline_guard']);guard_binding(value['actual_guard'])
    before=native_set(value['baseline'],logical);after=native_set(value['actual'],logical)
    require(before['basis_complete'] and after['basis_complete'],
        'Actual GPU tangent/binormal basis and every LOD readback are mandatory; legacy/count-only evidence is insufficient')
    for field in ('source_lods','render_lods','cooked','hulls','policy','settings','source_presence'):
        require(before[field]==after[field],'Native '+field+' differs: '+logical)
    probes=compare_probes(before['probes'],after['probes'],logical,set(after['meshes']),set(before['meshes']),after['seams'])
    runtime=before['runtime_complete'] and after['runtime_complete']
    return dict(complete=runtime,geometry_complete=True,runtime_policy_complete=runtime,
        cooked_triangles=sum(after['cooked'].values()),controls=probes,meshes=len(after['meshes']),
        simple_hulls=sum(after['hulls'].values()),lods=sorted(after['render_lods']))


def compare_asset(value,logical,*,native=True,serialized=True):
    before=geometry_set(value['baseline'],bounded=False);after=geometry_set(value['actual'],bounded=True)
    require(before==after,'Source geometry/corners/channels/frame/whole-hull conservation differs: '+logical)
    require(policy(value['baseline_policy'],logical)==policy(value['actual_policy'],logical),
        'Logical placement/cull/shadow/fade/material/collision policy differs: '+logical)
    if serialized:
        original_exports=serialized_set(value['baseline_exports']);current_exports=serialized_set(value['actual_exports'])
        require(original_exports==current_exports,
            'Actual serialized corner/material/frame/collision conservation differs: '+logical)
        require(original_exports['triangles']==before['triangles'],
            'Serialized exports do not cover the complete canonical source triangles: '+logical)
    result=dict(exporter_complete=serialized,source_complete=True,triangles=after['triangles'],polygons=after['polygons'],
        native_complete=False)
    if native:
        result['native']=compare_native(value.get('native'),logical);result['native_complete']=result['native']['complete']
    return result


def validate_scope(value,repo=REPO,required_groups=MINIMUM_GROUPS):
    require(isinstance(value,dict) and set(value)=={'recipe','census','guard'},'Original scope/census evidence is absent')
    source_binding(value['recipe'],repo);guard_binding(value['guard']);census=json_artifact(value['census'])
    require(isinstance(census,dict) and set(census)=={'complete','groups','owners'} and census['complete'] is True
        and isinstance(census['groups'],dict) and set(required_groups)<=set(census['groups'])
        and isinstance(census['owners'],dict) and census['owners'],'Incomplete original environment owner census')
    covered=[]
    for group,owners in census['groups'].items():
        require(isinstance(group,str) and group and isinstance(owners,list) and owners
            and len(set(owners))==len(owners) and all(owner in census['owners'] for owner in owners),'Missing group owner capture')
        covered.extend(owners)
    require(set(covered)==set(census['owners']),'Original census owner omitted from group coverage')
    for owner,row in census['owners'].items():
        require(isinstance(owner,str) and owner and isinstance(row,dict) and set(row)=={'models','captures'}
            and isinstance(row['models'],list) and row['models'] and len(set(row['models']))==len(row['models'])
            and isinstance(row['captures'],dict) and set(row['models'])==set(row['captures']),
            'Original owner has missing model/export captures')
        for logical,capture in row['captures'].items():
            require(isinstance(logical,str) and logical and isinstance(capture,dict)
                and set(capture)=={'source_triangles','exported'} and type(capture['source_triangles']) is int
                and capture['source_triangles']>0 and capture['exported'] is True,
                'Unmeasured/uncaptured original model; atomic exclusions require actual original evidence')
    return census


def verify(spec,*,repo=REPO,native=True,serialized=True,required_groups=MINIMUM_GROUPS):
    """@cc [owner:fontanierh,label:correctness] all-region-independent-equivalence-evidence
    Immutable original producer bytes and their complete captured original inventory MUST
    define expected coverage; new split manifests MUST NOT define their own expected roster.
    Recompute complete ordered geometry/channel/material/frame and whole-hull multiplicity
    from actual payload artifacts. Require actual serialized export equality separately.
    Native receiving MUST independently compare saved render/cooked/hull snapshots, logical
    placement/cull/shadow/material policy and owned positive/negative/seam controls under
    successful whole/empty guards. Missing region, model, channel, snapshot or native coverage
    MUST fail full acceptance. Owner PASS booleans and subset proofs MUST NOT stand in for it.
    """
    exporter_errors=[];native_errors=[];results={}
    failures=(ValueError,KeyError,TypeError,IndexError,OverflowError,struct.error,OSError,subprocess.SubprocessError)
    try:
        require(isinstance(spec,dict) and set(spec)=={'schema','scope','regions'} and spec['schema']==1
            and isinstance(spec['regions'],dict),'Invalid aggregate equivalence spec')
        census=validate_scope(spec['scope'],repo,required_groups)
        require(set(spec['regions'])==set(census['owners']),'Aggregate omits or invents original producer owners')
    except failures as error:
        return dict(schema=1,complete=False,exporter_complete=False,native_complete=False,regions={},
            errors=[str(error)],exporter_errors=[str(error)],native_errors=[])
    for owner,expected in census['owners'].items():
        item=spec['regions'][owner];observed={};results[owner]=observed
        try:
            require(isinstance(item,dict) and set(item)=={'baseline_sources','actual_sources','baseline_inputs','actual_inputs','baseline_guard','actual_guard','assets'}
                and isinstance(item['assets'],dict) and set(item['assets'])==set(expected['models']),
                'Missing complete logical model coverage: '+owner)
            for field in ('baseline_sources','actual_sources'):
                require(isinstance(item[field],list) and item[field],'Missing pinned source closure: '+owner)
                require(len({(r['revision'],r['path']) for r in item[field]})==len(item[field]),'Duplicate source closure member')
                for row in item[field]:source_binding(row,repo)
            for field in ('baseline_inputs','actual_inputs'):
                require(isinstance(item[field],list),'Missing exact data input inventory: '+owner)
                require(len({r['path'] for r in item[field]})==len(item[field]),'Duplicate data input identity')
                for row in item[field]:artifact(row)
            guard_binding(item['baseline_guard']);guard_binding(item['actual_guard'])
        except failures as error:
            exporter_errors.append(owner+': '+str(error));continue
        for logical in expected['models']:
            try:
                observed[logical]=compare_asset(item['assets'][logical],logical,native=False,serialized=serialized)
                require(observed[logical]['triangles']==expected['captures'][logical]['source_triangles'],
                    'Original census triangle count differs: '+logical)
            except failures as error:
                exporter_errors.append(owner+'/'+logical+': '+str(error));continue
            if native:
                try:
                    observed[logical]['native']=compare_native(item['assets'][logical].get('native'),logical)
                    observed[logical]['native_complete']=observed[logical]['native']['complete']
                    require(observed[logical]['native_complete'],'Production runtime policy remains missing; fixture geometry proof is separate')
                except failures as error:
                    observed[logical]['native_error']=str(error);native_errors.append(owner+'/'+logical+': '+str(error))
    exporter=not exporter_errors and serialized
    native_complete=exporter and not native_errors and native
    return dict(schema=1,complete=native_complete,exporter_complete=exporter,native_complete=native_complete,
        regions=results,errors=[*exporter_errors,*native_errors],exporter_errors=exporter_errors,native_errors=native_errors,
        scope_groups=sorted(census['groups']),mode='full' if native else 'exporter_only',
        precision='float32 source channels; exact parsed numeric serialized/native values')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--exporter-only',action='store_true',help='Exporter evidence only; complete/native_complete remain false')
    args=parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    real_directory(args.spec.absolute().parent)
    require(not args.spec.is_symlink() and args.spec.is_file(),'Spec must be a regular unlinked file')
    payload=args.spec.read_bytes();spec=json.loads(payload)
    result=verify(spec,native=not args.exporter_only)
    require(args.spec.read_bytes()==payload,'Equivalence spec changed during verification')
    result['spec_sha256']=hashlib.sha256(payload).hexdigest();atomic_json(args.output,result)
    for error in result['errors']:print('EQUIVALENCE REFUSED '+error,flush=True)
    passed=result['exporter_complete'] if args.exporter_only else result['complete']
    print('ALL-REGION EQUIVALENCE '+('PASS' if passed else 'REFUSED'),flush=True)
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
