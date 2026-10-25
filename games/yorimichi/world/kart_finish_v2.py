"""Finish one original Kart rigid mesh while preserving its imported collision policy."""
import hashlib
from pathlib import Path

import numpy as np
from atelier import native_packages
from atelier.build_v2.blender_validate import decode_mesh_payload
from atelier.conventions import to_unreal
from atelier.export_manifest import validate as validate_export
from city_tile_products import collision_matches
from island_finish_v2 import _identity, _pairs, _selected
import json
from vehicle_sources import FAMILIES

MATERIAL='/Game/Japan/Kart/M_Kart'


def source_facts(context):
    args=context.params['args'];parent=args['parent']
    if parent not in FAMILIES['kart']['builders']:raise ValueError('Unknown rigid Kart parent')
    def item(slot):
        value=context.inputs.get(slot)
        if value is None or context.packages.get(slot) not in ([],()):raise ValueError('Kart source must be a declared Data Item')
        path=Path(value)
        if not path.is_absolute() or not path.is_relative_to(Path(context.job_dir)) or path.resolve()!=path or not path.is_dir():
            raise ValueError('Kart source must be an independent job-local Item')
        return path
    root=item(args['source_export']);path=root/'export.json'
    if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=1024*1024:raise ValueError('Missing bounded Kart export receipt')
    receipt=json.loads(path.read_bytes(),object_pairs_hook=_pairs)
    if (receipt.get('asset')!=parent or receipt.get('primary')!=parent+'.fbx'
            or {p.name for p in root.iterdir()}!={'export.json',parent+'.fbx'} or validate_export(root,key=parent)!=receipt):
        raise ValueError('Kart selected export differs from its original rigid owner')
    payload=item(args['payload']);members=list(payload.iterdir())
    if len(members)!=1 or members[0].name!=parent+'.npz' or members[0].is_symlink() or not members[0].is_file() or not 0<members[0].stat().st_size<=128*1024*1024:
        raise ValueError('Kart requires exactly its selected MeshIR payload')
    raw=members[0].read_bytes();metadata,_,facts=decode_mesh_payload(raw,expected_asset=parent,output_format='fbx')
    if (facts['slots']!=['KartPalette'] or facts['uv_channels']!=['UVMap'] or not 0<facts['triangles']<=6000
            or facts['triangles']!=receipt['triangles'] or [facts['min'],facts['max']]!=receipt['bounds']
            or len(metadata['collisions'])!=(1 if parent=='SM_Kart_Body' else 0)
            or receipt['metadata']!={'geometry_sha256':hashlib.sha256(raw).hexdigest(),'slots':facts['slots'],
                'polygons':facts['polygons'],'collision_hulls':len(metadata['collisions']),'uv_channels':facts['uv_channels']}):
        raise ValueError('Kart payload/export geometry, UV or authored collision ownership differs')
    hulls=[]
    for hull in metadata['collisions']:
        transform=np.asarray(hull['matrix']);vertices=np.asarray(hull['vertices'])@transform[:3,:3].T+transform[:3,3]
        hulls.append([[float(v) for v in to_unreal(p)] for p in vertices])
    low,high=receipt['bounds']
    return receipt,{'source_collision_vertices':hulls},{'collision_hulls':len(hulls)},([low[0]*100,-high[1]*100,low[2]*100],[high[0]*100,-low[1]*100,high[2]*100])


def run(context):
    """@cc [owner:fontanierh,label:correctness] original-kart-rigid-native-finish
    Finish MUST own only a fresh duplicate of the selected original raw mesh,
    retaining source pivot/coordinates, exact triangles, KartPalette and material,
    one UV/LOD and complete authored hull vertices. Original imported collision
    trace and UV precision MUST NOT be replaced by a world-surface policy. Bounds
    MUST match within .3 cm; native state and actual primary save MUST validate
    before completion. No original importer, generated scan, cache or namespace IO.
    """
    import unreal
    p=context.params
    if (set(p)-{'op','kind','source','destination','package_sources','args','settings'} or p.get('op')!='finish'
            or p.get('kind')!='static_mesh' or p.get('source')!='raw' or not isinstance(p.get('args'),dict)
            or set(p['args'])!={'parent','source_export','payload','material'}):raise ValueError('Unsupported Kart finish parameters')
    args=p['args']
    if set(context.inputs)!={'raw',args['source_export'],args['payload'],args['material']} or set(context.packages)!=set(context.inputs):
        raise ValueError('Kart finish input membership differs')
    receipt,group,tile,bounds=source_facts(context);name=receipt['asset'];destination='/Game/Japan/Kart/'+name
    source=_selected(context,'raw')
    if source!='/Game/_Raw/Kart/'+name or p['destination']!=destination or list(context.outputs)!=[destination]:
        raise ValueError('Kart finish owns exactly its original selected mesh')
    if _selected(context,args['material'])!=MATERIAL:raise ValueError('Kart material role differs')
    E=unreal.EditorAssetLibrary;raw=E.load_asset(source);material=E.load_asset(MATERIAL)
    if not isinstance(raw,unreal.StaticMesh) or not isinstance(material,unreal.MaterialInterface):raise ValueError('Kart native input type differs')
    _identity(raw,source);_identity(material,MATERIAL)
    reader=getattr(getattr(unreal,'CitySurfaceValidation',None),'collision_vertices',None)
    if not callable(reader):raise ValueError('Required produced Kart hull readback is unavailable')
    unreal.load_module('StaticMeshEditor');editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if editor is None:raise ValueError('Native StaticMeshEditor unavailable')
    raw_body=raw.get_editor_property('body_setup')
    if raw_body is None:raise ValueError('Kart raw mesh has no BodySetup')
    trace=raw_body.get_editor_property('collision_trace_flag')
    precision=editor.get_lod_build_settings(raw,0).get_editor_property('use_full_precision_u_vs')
    if E.does_asset_exist(destination):raise ValueError('Kart finish destination must be fresh')
    mesh=E.duplicate_asset(source,destination)
    if not isinstance(mesh,unreal.StaticMesh) or mesh is raw:raise ValueError('Kart raw duplicate failed')
    _identity(mesh,destination)
    if len(mesh.static_materials)!=1 or str(mesh.static_materials[0].get_editor_property('imported_material_slot_name'))!='KartPalette':
        raise ValueError('Kart original draw slot differs')
    mesh.set_material(0,material)
    def validate():
        box=mesh.get_bounding_box();body=mesh.get_editor_property('body_setup')
        if (mesh.get_num_triangles(0)!=receipt['triangles'] or mesh.get_num_lods()!=1 or editor.get_num_uv_channels(mesh,0)!=1
                or len(mesh.static_materials)!=1 or mesh.get_material(0)!=material
                or str(mesh.static_materials[0].get_editor_property('imported_material_slot_name'))!='KartPalette'
                or body is None or body.get_editor_property('collision_trace_flag')!=trace
                or editor.get_lod_build_settings(mesh,0).get_editor_property('use_full_precision_u_vs')!=precision
                or not collision_matches(mesh,group,tile,read_vertices=reader)
                or any(not abs(getattr(box.min,axis)-lo)<.3 or not abs(getattr(box.max,axis)-hi)<.3
                       for axis,lo,hi in zip(('x','y','z'),*bounds))):raise ValueError('Kart native geometry/material/collision/frame invariant failed')
    validate();native_packages.save(mesh,E,context.content_dir);validate();return mesh
