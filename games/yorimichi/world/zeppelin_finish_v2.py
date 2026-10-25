"""Finish one original Zeppelin mesh and author its keyed original fabric."""
import hashlib
from pathlib import Path

from atelier import native_packages
from atelier.build_v2.blender_validate import decode_mesh_payload
from atelier.export_manifest import validate as validate_export
from city_tile_products import collision_matches
from island_finish_v2 import _identity, _pairs, _selected
import json


MATERIAL='/Game/Japan/Materials/M_Village'
FABRIC='/Game/Japan/Materials/M_ZeppelinFabric'
ORIGINAL='games/yorimichi/unreal/Scripts/import_zeppelin.py'
OPTIONS=dict(apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',axis_forward='-Y',axis_up='Z',
    mesh_smooth_type='FACE',bake_anim=False,use_custom_props=False)
PARENTS=('ZP_Airship','ZP_Motors','ZP_Propeller','ZP_Gate','ZP_Gangway','ZP_Woodland','ZP_City','ZP_MegaPark','ZP_Belmonte','ZP_Trail')
IDENTITY=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]


def source_facts(context):
    args=context.params['args'];parent=args['parent']
    if parent not in PARENTS:raise ValueError('Unknown Zeppelin parent')
    def item(slot):
        value=context.inputs.get(slot)
        if value is None or context.packages.get(slot) not in ([],()):raise ValueError('Zeppelin source must be a declared Data Item')
        path=Path(value)
        if not path.is_absolute() or not path.is_relative_to(Path(context.job_dir)) or path.resolve()!=path or not path.is_dir():
            raise ValueError('Zeppelin source must be an independent job-local Item')
        return path
    root=item(args['source_export']);path=root/'export.json'
    if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=1024*1024:raise ValueError('Missing bounded Zeppelin export receipt')
    receipt=json.loads(path.read_bytes(),object_pairs_hook=_pairs)
    if (receipt.get('asset')!=parent or receipt.get('primary')!=parent+'.fbx'
            or {p.name for p in root.iterdir()}!={'export.json',parent+'.fbx'} or validate_export(root,key=parent)!=receipt):
        raise ValueError('Zeppelin selected export differs from its original rigid owner')
    payload=item(args['payload']);members=list(payload.iterdir())
    if len(members)!=1 or members[0].name!=parent+'.npz' or members[0].is_symlink() or not members[0].is_file() or not 0<members[0].stat().st_size<=128*1024*1024:
        raise ValueError('Zeppelin requires exactly its selected MeshIR payload')
    raw=members[0].read_bytes();metadata,_,facts=decode_mesh_payload(raw,expected_asset=parent,output_format='fbx')
    if (facts['matrix']!=IDENTITY or facts['options']!=OPTIONS or facts['slots']!=(['ZeppelinPalette','ZeppelinFabric'] if parent=='ZP_Airship' else ['ZeppelinPalette']) or facts['uv_channels']!=['UVMap'] or not 0<facts['triangles']<=32768
            or facts['triangles']!=receipt['triangles'] or [facts['min'],facts['max']]!=receipt['bounds']
            or len(metadata['collisions'])!=0
            or receipt['metadata']!={'geometry_sha256':hashlib.sha256(raw).hexdigest(),'slots':facts['slots'],
                'polygons':facts['polygons'],'collision_hulls':len(metadata['collisions']),'uv_channels':facts['uv_channels']}):
        raise ValueError('Zeppelin payload/export geometry, UV or authored collision ownership differs')
    hulls=[]
    low,high=receipt['bounds']
    return receipt,{'source_collision_vertices':hulls},{'collision_hulls':len(hulls)},([low[0]*100,-high[1]*100,low[2]*100],[high[0]*100,-low[1]*100,high[2]*100])


def finish(context):
    """@cc [owner:fontanierh,label:correctness] original-zeppelin-rigid-native-finish
    Finish MUST own only a fresh duplicate of the selected original raw mesh,
    retaining source pivot/coordinates, exact triangles and the complete original
    material roster. Airship fabric slots MUST use original fabric, other slots
    M_Village. Original complex-as-simple policy, UV precision, zero authored hulls
    and cooked LOD0 MUST validate. Bounds MUST match within 1 cm on all axes;
    native state and actual primary save MUST validate
    before completion. No original importer, generated scan, cache or namespace IO.
    """
    import unreal
    p=context.params
    if (set(p)-{'op','kind','source','destination','package_sources','args','settings'} or p.get('op')!='finish'
            or p.get('kind')!='static_mesh' or p.get('source')!='raw' or not isinstance(p.get('args'),dict)
            or set(p['args'])!={'parent','source_export','payload','material','fabric','native_inputs'}):raise ValueError('Unsupported Zeppelin finish parameters')
    args=p['args'];native=args['native_inputs']
    if (not isinstance(native,dict) or args['material'] not in native
            or set(context.inputs)!={'raw',args['source_export'],args['payload'],*native}
            or set(context.packages)!=set(context.inputs)):
        raise ValueError('Zeppelin finish input membership differs')
    receipt,group,tile,bounds=source_facts(context);name=receipt['asset'];destination='/Game/Japan/Assets/'+name
    source=_selected(context,'raw')
    if source!='/Game/_Raw/Zeppelin/'+name or p['destination']!=destination or list(context.outputs)!=[destination]:
        raise ValueError('Zeppelin finish owns exactly its original selected mesh')
    if native[args['material']]!=MATERIAL:raise ValueError('Zeppelin Village material role differs')
    if ((name=='ZP_Airship' and (args['fabric'] not in native or native[args['fabric']]!=FABRIC))
            or (name!='ZP_Airship' and args['fabric'] is not None)):
        raise ValueError('Zeppelin fabric parent/material role differs')
    E=unreal.EditorAssetLibrary;raw=E.load_asset(source)
    if not isinstance(raw,unreal.StaticMesh):raise ValueError('Zeppelin raw input type differs')
    _identity(raw,source);loaded={}
    for slot,package in native.items():
        if _selected(context,slot)!=package:raise ValueError('Zeppelin native dependency differs')
        asset=E.load_asset(package)
        if asset is None:raise ValueError('Zeppelin native dependency failed to load')
        _identity(asset,package);loaded[slot]=asset
    material=loaded[args['material']]
    if not isinstance(material,unreal.MaterialInterface):raise ValueError('Zeppelin material input type differs')
    fabric=loaded.get(args['fabric'])
    if name=='ZP_Airship' and not isinstance(fabric,unreal.MaterialInterface):raise ValueError('Zeppelin fabric must be a MaterialInterface')
    reader=getattr(getattr(unreal,'CitySurfaceValidation',None),'collision_vertices',None)
    if not callable(reader):raise ValueError('Required produced Zeppelin hull readback is unavailable')
    validator=getattr(getattr(unreal,'CitySurfaceValidation',None),'validate_collision',None)
    if not callable(validator):raise ValueError('Required produced Zeppelin cooked collision validator is unavailable')
    unreal.load_module('StaticMeshEditor');editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if editor is None:raise ValueError('Native StaticMeshEditor unavailable')
    raw_body=raw.get_editor_property('body_setup')
    if raw_body is None:raise ValueError('Zeppelin raw mesh has no BodySetup')
    trace=unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE
    precision=editor.get_lod_build_settings(raw,0).get_editor_property('use_full_precision_u_vs')
    if E.does_asset_exist(destination):raise ValueError('Zeppelin finish destination must be fresh')
    mesh=E.duplicate_asset(source,destination)
    if not isinstance(mesh,unreal.StaticMesh) or mesh is raw:raise ValueError('Zeppelin raw duplicate failed')
    _identity(mesh,destination)
    slots=receipt['metadata']['slots']
    def binding(slot):return fabric if name=='ZP_Airship' and 'ZeppelinFabric' in slot else material
    if [str(row.get_editor_property('imported_material_slot_name')) for row in mesh.static_materials]!=slots:
        raise ValueError('Zeppelin original complete material roster differs')
    for index,slot in enumerate(slots):
        want=binding(slot)
        if mesh.get_material(index)!=want:mesh.set_material(index,want)
    body=mesh.get_editor_property('body_setup')
    if body is None:raise ValueError('Zeppelin mesh has no BodySetup')
    if body.get_editor_property('collision_trace_flag')!=trace:body.set_editor_property('collision_trace_flag',trace)
    def validate():
        box=mesh.get_bounding_box();body=mesh.get_editor_property('body_setup')
        if (mesh.get_num_triangles(0)!=receipt['triangles'] or mesh.get_num_lods()!=1 or editor.get_num_uv_channels(mesh,0)!=1
                or [str(row.get_editor_property('imported_material_slot_name')) for row in mesh.static_materials]!=slots
                or any(mesh.get_material(index)!=binding(slot) for index,slot in enumerate(slots))
                or body is None or body.get_editor_property('collision_trace_flag')!=trace
                or editor.get_lod_build_settings(mesh,0).get_editor_property('use_full_precision_u_vs')!=precision
                or not collision_matches(mesh,group,tile,read_vertices=reader)
                or any(not abs(getattr(box.min,axis)-lo)<1. or not abs(getattr(box.max,axis)-hi)<1.
                       for axis,lo,hi in zip(('x','y','z'),*bounds))):raise ValueError('Zeppelin native geometry/material/collision/frame invariant failed')
        if not validator(mesh,receipt['triangles'],False):raise ValueError('Zeppelin cooked LOD0 collision validation failed')
    validate();native_packages.save(mesh,E,context.content_dir);validate();return mesh


def fabric(context):
    """@cc [owner:fontanierh,label:correctness] keyed-original-zeppelin-fabric
    Fabric MUST execute only the original keyed fabric_material definition in a
    controlled E/unreal namespace. Importer imports, top-level calls, asset groups,
    native namespace reads and retirement MUST NOT execute. The fresh exact Material
    and its actual primary save MUST validate before completion.
    """
    import ast
    import unreal
    if context.params!={'args':{'op':'fabric'},'settings':[]} or context.inputs or context.packages or list(context.outputs)!=[FABRIC]:
        raise ValueError('Zeppelin fabric owns exactly its fresh Material and no inputs')
    root=Path(context.job_dir).resolve();path=root/ORIGINAL
    if path.resolve()!=path or not path.is_file():raise ValueError('Zeppelin fabric requires keyed original source')
    E=unreal.EditorAssetLibrary
    if E.does_asset_exist(FABRIC):raise ValueError('Zeppelin fabric destination must be fresh')
    tree=ast.parse(path.read_bytes(),str(path))
    definitions=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='fabric_material']
    if len(definitions)!=1 or definitions[0].decorator_list or definitions[0].args.defaults or definitions[0].args.kw_defaults:
        raise ValueError('Zeppelin original fabric definition differs')
    scope={'unreal':unreal,'E':E}
    exec(compile(ast.Module(body=definitions,type_ignores=[]),str(path),'exec'),scope)
    asset=scope['fabric_material']()
    if not isinstance(asset,unreal.Material):raise ValueError('Zeppelin original factory did not return Material')
    _identity(asset,FABRIC)
    native_packages.save(asset,E,context.content_dir)
    return asset


def run(context):
    if context.params.get('args',{}).get('op')=='fabric':return fabric(context)
    return finish(context)
