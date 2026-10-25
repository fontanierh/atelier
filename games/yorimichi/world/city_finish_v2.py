"""Finish one current bounded city source child without receiving a namespace."""
import ast
import hashlib
import json
from pathlib import Path

import numpy as np
from atelier import native_packages
from atelier.build_v2.blender_validate import decode_mesh_payload
from atelier.conventions import to_unreal
from atelier.export_manifest import validate as validate_export
from city_atomic_products import SOURCES,DESTINATION,piece_material_paths,collision_matches,native_bounds
from city_tile_products import tile_name
from island_finish_v2 import _identity,_pairs,_selected
from regions.hidamari.tree_policy import TREES

EMPTY='games/yorimichi/unreal/Scripts/import_city_surface_tiles.py'


def _directory(context,slot):
    path=Path(context.inputs[slot])
    if path.resolve()!=path or not path.is_relative_to(Path(context.job_dir)) or not path.is_dir() or context.packages[slot] not in ([],()):raise ValueError('City source must be an independent job-local Data Item')
    return path


def source_facts(context):
    parent=context.params['args']['parent']
    if parent not in SOURCES:raise ValueError('Unknown current logical city owner')
    root=_directory(context,'source_export');path=root/'export.json'
    if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=1024*1024:raise ValueError('Missing bounded city export receipt')
    receipt=json.loads(path.read_bytes(),object_pairs_hook=_pairs);key=receipt['asset']
    if (not (key==parent or tile_name(parent,key)) or receipt['primary']!=key+'.fbx' or {p.name for p in root.iterdir()}!={'export.json',key+'.fbx'}
            or validate_export(root,key=key)!=receipt):raise ValueError('City selected export ownership differs')
    payload=_directory(context,'payload');members=list(payload.iterdir())
    if len(members)!=1 or members[0].name!=key+'.npz' or members[0].is_symlink() or not 0<members[0].stat().st_size<=128*1024*1024:raise ValueError('City requires only its selected MeshIR')
    raw=members[0].read_bytes();meta,_,facts=decode_mesh_payload(raw,expected_asset=key,output_format='fbx')
    if (not 0<facts['triangles']<=32768 or facts['triangles']!=receipt['triangles'] or [facts['min'],facts['max']]!=receipt['bounds']
            or receipt['metadata']!={'geometry_sha256':hashlib.sha256(raw).hexdigest(),'slots':facts['slots'],'polygons':facts['polygons'],
                'collision_hulls':len(meta['collisions']),'uv_channels':facts['uv_channels']}):raise ValueError('City own source geometry/channel/collision facts differ')
    parent_root=_directory(context,'parent');path=parent_root/'plan.json'
    if {p.name for p in parent_root.iterdir()}!={'plan.json'} or path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=1024*1024:raise ValueError('Missing exact city parent-facts Item')
    plan=json.loads(path.read_bytes(),object_pairs_hook=_pairs)
    if (set(plan)!={'parent','source_material_slots','source_collision_hulls'} or plan['parent']!=parent or type(plan['source_collision_hulls']) is not int
            or plan['source_collision_hulls']<0 or len(meta['collisions']) not in (0,plan['source_collision_hulls'])):raise ValueError('City projected parent ownership differs')
    materials=piece_material_paths(parent,plan['source_material_slots'])
    if any(slot not in materials for slot in facts['slots']):raise ValueError('City compact child slots escape original complete material roster')
    hulls=[]
    for hull in meta['collisions']:
        matrix=np.asarray(hull['matrix']);vertices=np.asarray(hull['vertices'])@matrix[:3,:3].T+matrix[:3,3]
        hulls.append([[float(v) for v in to_unreal(point)] for point in vertices])
    tile={'name':key,'triangles':facts['triangles'],'collision_hulls':len(hulls),'uv_channels':facts['uv_channels'],'min':facts['min'],'max':facts['max']}
    return parent,receipt,plan,facts,materials,{'source_collision_vertices':hulls},tile


def _cleanup(context):
    path=Path(context.job_dir)/EMPTY
    if path.resolve()!=path or not path.is_file():raise ValueError('Missing keyed original empty-collision helper')
    parsed=ast.parse(path.read_bytes(),str(path));definitions=[n for n in parsed.body if isinstance(n,ast.FunctionDef) and n.name=='finish_empty_collision']
    if len(definitions)!=1 or definitions[0].decorator_list:raise ValueError('Original empty-collision definition differs')
    scope={};exec(compile(ast.Module(body=definitions,type_ignores=[]),str(path),'exec'),scope);return scope['finish_empty_collision']


def run(context):
    """@cc [owner:fontanierh,label:correctness] current-desktop-selected-city-finish
    Each fresh child MUST consume only its own certified export/payload and narrow
    validated parent facts. Actual compact slots MUST use the original parent's
    complete material policy. Whole-parent authored collision MUST select trace
    policy even on zero-hull render siblings; full owned UCX and current cooked
    LOD0 MUST validate. Original full-precision UVs, distance LODs and tree CPU
    policy MUST remain required, with .2 cm finite bounds and real primary save.
    No original importer, namespace inventory/cache/retirement or parent load MAY run.
    """
    import unreal
    from city_distance_lods import distance_lods
    p=context.params
    if (set(p)-{'op','kind','source','destination','package_sources','args','settings'} or p.get('op')!='finish' or p.get('kind')!='static_mesh'
            or p.get('source')!='raw' or set(p['args'])!={'parent','native_inputs'}):raise ValueError('Unsupported current city finish parameters')
    native=p['args']['native_inputs']
    if not isinstance(native,dict) or set(context.inputs)!={'raw','source_export','payload','parent',*native} or set(context.packages)!=set(context.inputs):raise ValueError('City complete input roster differs')
    parent,receipt,plan,facts,materials,group,tile=source_facts(context);key=receipt['asset'];destination=DESTINATION+'/'+key
    raw_path=_selected(context,'raw')
    if raw_path!='/Game/_Raw/City/'+key or p['destination']!=destination or list(context.outputs)!=[destination]:raise ValueError('City finish owns exactly its current selected child')
    by_package={}
    for slot,path in native.items():
        if _selected(context,slot)!=path:raise ValueError('City declared native input differs')
        by_package[path]=slot
    E=unreal.EditorAssetLibrary;raw=E.load_asset(raw_path)
    if not isinstance(raw,unreal.StaticMesh):raise ValueError('City raw input must be StaticMesh')
    _identity(raw,raw_path);loaded={}
    for path in set(materials[slot] for slot in facts['slots']):
        if path not in by_package:raise ValueError('City actual material lacks its declared native Item')
        asset=E.load_asset(path)
        if not isinstance(asset,unreal.MaterialInterface):raise ValueError('City actual material is unavailable')
        _identity(asset,path);loaded[path]=asset
    validation=getattr(unreal,'CitySurfaceValidation',None)
    if validation is None or not callable(getattr(validation,'collision_vertices',None)) or not callable(getattr(validation,'validate_collision',None)):raise ValueError('City produced native collision validation unavailable')
    unreal.load_module('StaticMeshEditor');editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if editor is None:raise ValueError('City StaticMeshEditor unavailable')
    cleanup=_cleanup(context)
    if E.does_asset_exist(destination):raise ValueError('City output must be fresh')
    mesh=E.duplicate_asset(raw_path,destination)
    if not isinstance(mesh,unreal.StaticMesh) or mesh is raw:raise ValueError('City raw duplicate failed')
    _identity(mesh,destination)
    slots=[str(slot.get_editor_property('imported_material_slot_name')) for slot in mesh.static_materials]
    if len(slots)!=len(facts['slots']) or set(slots)!=set(facts['slots']):raise ValueError('City native imported draw slots differ')
    for index,slot in enumerate(slots):
        material=loaded[materials[slot]]
        if mesh.get_material(index)!=material:mesh.set_material(index,material)
    settings=editor.get_lod_build_settings(mesh,0)
    if settings.get_editor_property('generate_lightmap_u_vs'):raise ValueError('City raw import must preserve disabled generated lightmap UVs')
    if not settings.get_editor_property('use_full_precision_u_vs'):
        settings.set_editor_property('use_full_precision_u_vs',True);editor.set_lod_build_settings(mesh,0,settings)
    body=mesh.get_editor_property('body_setup')
    if body is None:raise ValueError('City mesh has no BodySetup')
    authored=bool(plan['source_collision_hulls']);trace=unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AND_COMPLEX if authored else unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE
    if body.get_editor_property('collision_trace_flag')!=trace:body.set_editor_property('collision_trace_flag',trace)
    cleanup(mesh,tile,editor)
    if parent in TREES:
        if mesh.get_num_lods()>1:mesh.set_num_source_models(1)
        if not mesh.get_editor_property('allow_cpu_access'):mesh.set_editor_property('allow_cpu_access',True)
    def validate(lods=None):
        box=mesh.get_bounding_box();low,high=native_bounds(tile);settings=editor.get_lod_build_settings(mesh,0)
        if (mesh.get_num_triangles(0)!=tile['triangles'] or [str(row.get_editor_property('imported_material_slot_name')) for row in mesh.static_materials]!=slots
                or any(mesh.get_material(i)!=loaded[materials[slot]] for i,slot in enumerate(slots))
                or not settings.get_editor_property('use_full_precision_u_vs') or settings.get_editor_property('generate_lightmap_u_vs')
                or editor.get_num_uv_channels(mesh,0)!=len(tile['uv_channels']) or body.get_editor_property('collision_trace_flag')!=trace
                or (parent in TREES and (mesh.get_num_lods()!=1 or not mesh.get_editor_property('allow_cpu_access')))
                or any(not abs(getattr(box.min,axis)-lo)<.2 or not abs(getattr(box.max,axis)-hi)<.2 for axis,lo,hi in zip('xyz',low,high))
                or not collision_matches(mesh,group,tile,read_vertices=validation.collision_vertices)
                or not validation.validate_collision(mesh,tile['triangles'],authored)):
            raise ValueError('City current geometry/material/UV/lightmap/collision/bounds invariant failed')
        if lods:
            if (mesh.get_num_lods()!=lods['count'] or [mesh.get_num_triangles(i) for i in range(lods['count'])]!=lods['triangles']
                    or list(editor.get_lod_screen_sizes(mesh))!=lods['screen_sizes'] or mesh.get_editor_property('lod_for_collision')!=0):raise ValueError('City saved original distance LOD state differs')
    validate();lods=None
    if (parent.startswith('HD_Shop_') and parent[8:].isdigit()) or parent in ('HD_Station','HD_Shrine'):
        lods=distance_lods(mesh,key,[(1.,1.),(.5,.28),(.15,.12),(.04,.05)])
    elif parent.startswith('HD_House_'):lods=distance_lods(mesh,key,[(1.,1.),(.4,.3),(.12,.12)])
    validate(lods);native_packages.save(mesh,E,context.content_dir);validate(lods);return mesh
