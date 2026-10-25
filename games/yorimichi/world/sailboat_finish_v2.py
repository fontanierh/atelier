"""Finish one original Sailboat rigid mesh while preserving its imported collision policy."""
import hashlib
from pathlib import Path

from atelier import native_packages
import numpy as np
from atelier import mesh_ir
from atelier.export_manifest import validate as validate_export
from city_tile_products import collision_matches
from island_finish_v2 import _identity, _pairs, _selected
import json
from vehicle_sources import FAMILIES

MATERIAL='/Game/Japan/Materials/M_Village'
CLOTH='/Game/Japan/Materials/M_SailboatCloth'
FOAM='/Game/Japan/Materials/M_SailboatWake'
OPTIONS=dict(apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',axis_forward='-Y',axis_up='Z',
    object_types=['MESH'],mesh_smooth_type='FACE',bake_anim=False,use_custom_props=False)
IDENTITY=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]


def source_facts(context):
    args=context.params['args'];parent=args['parent']
    if parent not in FAMILIES['sailboat']['builders']:raise ValueError('Unknown rigid Sailboat parent')
    def item(slot):
        value=context.inputs.get(slot)
        if value is None or context.packages.get(slot) not in ([],()):raise ValueError('Sailboat source must be a declared Data Item')
        path=Path(value)
        if not path.is_absolute() or not path.is_relative_to(Path(context.job_dir)) or path.resolve()!=path or not path.is_dir():
            raise ValueError('Sailboat source must be an independent job-local Item')
        return path
    root=item(args['source_export']);path=root/'export.json'
    if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=1024*1024:raise ValueError('Missing bounded Sailboat export receipt')
    receipt=json.loads(path.read_bytes(),object_pairs_hook=_pairs)
    if (receipt.get('asset')!=parent or receipt.get('primary')!=parent+'.fbx'
            or {p.name for p in root.iterdir()}!={'export.json',parent+'.fbx'} or validate_export(root,key=parent)!=receipt):
        raise ValueError('Sailboat selected export differs from its original rigid owner')
    payload=item(args['payload']);members=list(payload.iterdir())
    if len(members)!=1 or members[0].name!=parent+'.npz' or members[0].is_symlink() or not members[0].is_file() or not 0<members[0].stat().st_size<=128*1024*1024:
        raise ValueError('Sailboat requires exactly its selected MeshIR payload')
    raw=members[0].read_bytes();metadata,piece=mesh_ir.decode(raw)
    if metadata['schema']!=2 or metadata['asset']!=parent:raise ValueError('Sailboat requires its original rigid FBX payload')
    positions=piece['positions']@np.asarray(metadata['matrix'])[:3,:3].T+np.asarray(metadata['matrix'])[:3,3]
    facts=dict(matrix=metadata['matrix'],options=metadata['options'],slots=metadata['slots'],
        uv_channels=[row[0] for row in piece['uvs']],triangles=piece['triangles'],polygons=len(piece['faces']),
        min=positions.min(0).tolist(),max=positions.max(0).tolist())
    if (facts['matrix']!=IDENTITY or facts['options']!=OPTIONS or facts['slots']!=['SailboatPalette'] or facts['uv_channels']!=['UVMap'] or not 0<facts['triangles']<=32768
            or facts['triangles']!=receipt['triangles'] or [facts['min'],facts['max']]!=receipt['bounds']
            or len(metadata['collisions'])!=0
            or receipt['metadata']!={'geometry_sha256':hashlib.sha256(raw).hexdigest(),'slots':facts['slots'],
                'polygons':facts['polygons'],'collision_hulls':len(metadata['collisions']),'uv_channels':facts['uv_channels']}):
        raise ValueError('Sailboat payload/export geometry, UV or authored collision ownership differs')
    hulls=[]
    low,high=receipt['bounds']
    return receipt,{'source_collision_vertices':hulls},{'collision_hulls':len(hulls)},([low[0]*100,-high[1]*100,low[2]*100],[high[0]*100,-low[1]*100,high[2]*100])


def run(context):
    """@cc [owner:fontanierh,label:correctness] original-sailboat-rigid-native-finish
    Finish MUST own only a fresh duplicate of the selected original raw mesh,
    retaining source pivot/coordinates, exact triangles, SailboatPalette and material,
    one UV/LOD and complete authored hull vertices. Original imported collision
    trace and UV precision MUST NOT be replaced by a world-surface policy. Bounds
    MUST match within .3 cm; native state and actual primary save MUST validate
    before completion. No original importer, generated scan, cache or namespace IO.
    """
    import unreal
    p=context.params
    if (set(p)-{'op','kind','source','destination','package_sources','args','settings'} or p.get('op')!='finish'
            or p.get('kind')!='static_mesh' or p.get('source')!='raw' or not isinstance(p.get('args'),dict)
            or set(p['args'])!={'parent','source_export','payload','material','native_inputs'}):raise ValueError('Unsupported Sailboat finish parameters')
    args=p['args'];native=args['native_inputs']
    if (not isinstance(native,dict) or args['material'] not in native
            or set(context.inputs)!={'raw',args['source_export'],args['payload'],*native}
            or set(context.packages)!=set(context.inputs)):
        raise ValueError('Sailboat finish input membership differs')
    receipt,group,tile,bounds=source_facts(context);name=receipt['asset'];destination='/Game/Japan/Assets/'+name
    source=_selected(context,'raw')
    if source!='/Game/_Raw/Sailboat/'+name or p['destination']!=destination or list(context.outputs)!=[destination]:
        raise ValueError('Sailboat finish owns exactly its original selected mesh')
    expected_material=CLOTH if name=='SB_Sail' else FOAM if name=='SB_Wake' else MATERIAL
    if native[args['material']]!=expected_material:raise ValueError('Sailboat material role differs')
    E=unreal.EditorAssetLibrary;raw=E.load_asset(source)
    if not isinstance(raw,unreal.StaticMesh):raise ValueError('Sailboat raw input type differs')
    _identity(raw,source);loaded={}
    for slot,package in native.items():
        if _selected(context,slot)!=package:raise ValueError('Sailboat native dependency differs')
        asset=E.load_asset(package)
        if asset is None:raise ValueError('Sailboat native dependency failed to load')
        _identity(asset,package);loaded[slot]=asset
    material=loaded[args['material']]
    if not isinstance(material,unreal.MaterialInterface):raise ValueError('Sailboat material input type differs')
    reader=getattr(getattr(unreal,'CitySurfaceValidation',None),'collision_vertices',None)
    if not callable(reader):raise ValueError('Required produced Sailboat hull readback is unavailable')
    unreal.load_module('StaticMeshEditor');editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if editor is None:raise ValueError('Native StaticMeshEditor unavailable')
    raw_body=raw.get_editor_property('body_setup')
    if raw_body is None:raise ValueError('Sailboat raw mesh has no BodySetup')
    trace=raw_body.get_editor_property('collision_trace_flag')
    precision=editor.get_lod_build_settings(raw,0).get_editor_property('use_full_precision_u_vs')
    if E.does_asset_exist(destination):raise ValueError('Sailboat finish destination must be fresh')
    mesh=E.duplicate_asset(source,destination)
    if not isinstance(mesh,unreal.StaticMesh) or mesh is raw:raise ValueError('Sailboat raw duplicate failed')
    _identity(mesh,destination)
    if len(mesh.static_materials)!=1 or str(mesh.static_materials[0].get_editor_property('imported_material_slot_name'))!='SailboatPalette':
        raise ValueError('Sailboat original draw slot differs')
    mesh.set_material(0,material)
    def validate():
        box=mesh.get_bounding_box();body=mesh.get_editor_property('body_setup')
        if (mesh.get_num_triangles(0)!=receipt['triangles'] or mesh.get_num_lods()!=1 or editor.get_num_uv_channels(mesh,0)!=1
                or len(mesh.static_materials)!=1 or mesh.get_material(0)!=material
                or str(mesh.static_materials[0].get_editor_property('imported_material_slot_name'))!='SailboatPalette'
                or body is None or body.get_editor_property('collision_trace_flag')!=trace
                or editor.get_lod_build_settings(mesh,0).get_editor_property('use_full_precision_u_vs')!=precision
                or not collision_matches(mesh,group,tile,read_vertices=reader)
                or any(not abs(getattr(box.min,axis)-lo)<.3 or not abs(getattr(box.max,axis)-hi)<.3
                       for axis,lo,hi in zip(('x','y','z'),*bounds))):raise ValueError('Sailboat native geometry/material/collision/frame invariant failed')
    validate();native_packages.save(mesh,E,context.content_dir);validate();return mesh
