"""Original Hidamari materials and one fitted prop or explicit conifer LOD owner."""
import ast
import hashlib
import json
import math
from pathlib import Path

from atelier import native_packages
from atelier.build_v2.blender_validate import decode_mesh_payload
from atelier.conventions import to_unreal
from atelier.export_manifest import validate as validate_export
from city_tile_products import collision_matches
from island_finish_v2 import _identity,_pairs,_selected
from treehouse_materials_v2 import read_data
import numpy as np

SCRIPTS='games/yorimichi/unreal/Scripts/'
MAT='/Game/Japan/Hidamari/Materials/'
TEX='/Game/Japan/Hidamari/Textures/'


def _original(context,name,scope,functions,constants=()):
    path=Path(context.job_dir)/SCRIPTS/(name+'.py')
    if path.resolve()!=path or not path.is_file():raise ValueError('Hidamari original code must be keyed staged source')
    tree=ast.parse(path.read_bytes(),str(path));nodes=[];found=[]
    for node in tree.body:
        if isinstance(node,ast.FunctionDef) and node.name in functions:
            if node.decorator_list:raise ValueError('Decorated original Hidamari factory')
            nodes.append(node);found.append(node.name)
        elif isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in constants:
            nodes.append(node);found.append(node.targets[0].id)
    if sorted(found)!=sorted((*functions,*constants)):raise ValueError('Original Hidamari factory closure differs')
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),scope)
    return scope


def _native(context,mapping):
    import unreal
    loaded={}
    for slot,path in mapping.items():
        if _selected(context,slot)!=path:raise ValueError('Hidamari declared native package differs')
        asset=unreal.EditorAssetLibrary.load_asset(path)
        if asset is None:raise ValueError('Hidamari native dependency did not load')
        _identity(asset,path);loaded[path]=asset
    return loaded


def material(context):
    """@cc [owner:fontanierh,label:correctness] original-hidamari-single-material
    One author MUST execute only the original keyed named material factory and
    constants, binding all texture/parent/native reads to declared Items. Texture
    imports, material roster loops and old importer top-level MUST NOT execute.
    Original graphs, surface tiles, prop gain/2 and Macro=0 MUST be preserved;
    the exact fresh Material/Instance and actual primary save MUST validate.
    """
    import unreal
    import atmosphere
    import sea_look
    import coast_water
    args=context.params['args'];package=args['package'];family=args['family'];function=args['function']
    if context.params.keys()!= {'args','settings'} or context.params['settings']!=[] or list(context.outputs)!=[package]:raise ValueError('Hidamari material must own its exact output')
    native=args['native_inputs'];data=args['data']
    if set(context.inputs)!=set(native)|({'data'} if data else set()) or set(context.packages)!=set(context.inputs):raise ValueError('Hidamari material input roster differs')
    loaded=_native(context,native);E=unreal.EditorAssetLibrary;M=unreal.MaterialEditingLibrary
    if E.does_asset_exist(package):raise ValueError('Hidamari material output must be fresh')
    def texture(name):
        prefix='T_Arcade_' if family=='arcade_material' else 'T_Harbor_'
        path='/Game/Japan/Textures/'+prefix+name
        if path not in loaded:raise ValueError('Undeclared original Hidamari texture read')
        return loaded[path]
    scope={'unreal':unreal,'E':E,'EAL':E,'MEL':M,'AT':unreal.AssetToolsHelpers.get_asset_tools(),
        'atmosphere':atmosphere,'sea_look':sea_look,'coast_water':coast_water,'texture':texture}
    constants=()
    if family=='city_material':constants=('MAT','TEX','STRENGTH','MACRO','PROP_MACRO')
    elif family=='harbor_material':constants=('SEA_RECT','EDGE','FAR_FADE')
    elif family not in ('arcade_material','plaza_material'):raise ValueError('Unknown original Hidamari material family')
    functions=('parent','instance') if family=='city_material' else (function,)
    scope=_original(context,family,scope,functions,constants)
    if family=='city_material' and function=='parent':
        result=scope['parent'](loaded[TEX+'T_HD_plaster'])
    elif family=='city_material' and function=='instance':
        if not data or context.packages[data['slot']] not in ([],()):raise ValueError('Hidamari instance metadata must be actual Data')
        value=read_data(context,data);key=args['key'];prop=args.get('prop',False)
        if prop:
            if value.get('schema')!=1 or value.get('name')!=key or value.get('parent')!=key or value.get('lod')!=0:raise ValueError('Wrong selected Hidamari prop material metadata')
            gain=value['info']['gain']/2;tile=1.;tex=TEX+'T_'+key;name='MI_'+key
        else:
            if key=='flat':tile=1.;tex=TEX+'T_HD_plaster'
            else:tile=value[key]['tile_m'];tex=TEX+'T_HD_'+key
            gain=1.;name='MI_HD_'+key
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in (tile,gain)):raise ValueError('Invalid actual Hidamari tile/gain')
        result=scope['instance'](loaded[MAT+'M_HDCity'],key,loaded[tex],tile,gain,name=name)
        if prop:
            M.set_material_instance_scalar_parameter_value(result,'Macro',scope['PROP_MACRO']);M.update_material_instance(result)
    else:result=scope[function](*args['arguments'],**args['keywords'])
    if not isinstance(result,unreal.MaterialInterface):raise ValueError('Hidamari factory did not return MaterialInterface')
    _identity(result,package);native_packages.save(result,E,context.content_dir);return result


def _directory(context,slot):
    root=Path(context.inputs[slot])
    if not root.is_absolute() or not root.is_relative_to(Path(context.job_dir)) or root.resolve()!=root or not root.is_dir() or context.packages[slot] not in ([],()):
        raise ValueError('Hidamari source requires an independent job-local Data Item')
    return root


def prop(context):
    """@cc [owner:fontanierh,label:correctness] original-hidamari-selected-prop
    Every selected prop/LOD MUST validate its own original export, payload, fitted
    record and committed definition before native mutation. Complete native hull
    vertices, original collision policy/material, UV precision, bounds and exact
    imported LOD0 geometry MUST survive (conifers retain the original 2% source tolerance). Base conifers MUST consume all three captured
    native LOD owners plus their actual records; source inputs MUST NOT be saved.
    LOD counts/screens/reduction and actual owned primary save MUST validate.
    No original importer, sibling generation, ambient source or namespace MAY run.
    """
    import unreal
    p=context.params;args=p['args'];name=args['name'];base=args['base'];level=args['level']
    root=_directory(context,'source_export');receipt=json.loads((root/'export.json').read_bytes(),object_pairs_hook=_pairs)
    if receipt.get('asset')!=name or receipt.get('primary')!=name+'.fbx' or {r.name for r in root.iterdir()}!={name+'.fbx','export.json'} or validate_export(root,key=name)!=receipt:raise ValueError('Hidamari selected export differs')
    payload=_directory(context,'payload');path=payload/(name+'.npz')
    if list(payload.iterdir())!=[path] or path.is_symlink() or not 0<path.stat().st_size<=128*1024*1024:raise ValueError('Hidamari selected MeshIR differs')
    raw_bytes=path.read_bytes();meta,piece,facts=decode_mesh_payload(raw_bytes,expected_asset=name,output_format='fbx')
    if (facts['triangles']!=receipt['triangles'] or [facts['min'],facts['max']]!=receipt['bounds'] or len(facts['slots'])!=1 or len(facts['uv_channels'])!=1
            or receipt['metadata']!={'geometry_sha256':hashlib.sha256(raw_bytes).hexdigest(),'slots':facts['slots'],'polygons':facts['polygons'],'collision_hulls':len(meta['collisions']),'uv_channels':facts['uv_channels']}):raise ValueError('Hidamari payload/export source facts differ')
    parameter=Path(context.inputs['definition'])
    if not parameter.is_relative_to(Path(context.job_dir)) or parameter.resolve()!=parameter or not parameter.is_file() or context.packages['definition'] not in ([],()):raise ValueError('Hidamari definition must be a declared staged file')
    definition=json.loads(parameter.read_bytes(),object_pairs_hook=_pairs);record=read_data(context,args['data'])
    if (definition['name']!=name or definition['parent']!=base or definition['lod']!=level or record.get('schema')!=1 or record.get('name')!=name
            or record.get('parent')!=base or record.get('lod')!=level or record['level'][0]!=receipt['triangles'] or record['hulls']!=meta['collisions']
            or record['info']['boxes']!=len(meta['collisions']) or len(meta['collisions'])!=int(definition['solid']) or args['material']!=MAT+'MI_'+base):raise ValueError('Hidamari actual fitted record/definition ownership differs')
    destination=('/Game/Japan/Hidamari/PropLODs/'+base+'/'+name if level else '/Game/Japan/Assets/'+name)
    raw_path=_selected(context,'raw')
    if raw_path!='/Game/_Raw/Hidamari/'+name or p['destination']!=destination or list(context.outputs)!=[destination]:raise ValueError('Hidamari prop owns only its original native package')
    native=args['native_inputs'];loaded=_native(context,native)
    rows=args['lods'].get('derived_items',{}).get('members',[]) if isinstance(args['lods'],dict) else []
    expected_inputs={'raw','source_export','payload','data','definition',*native,*(r['slot'] for r in rows),*(r['slot'] for r in args['lod_records'])}
    if set(context.inputs)!=expected_inputs or set(context.packages)!=expected_inputs:raise ValueError('Hidamari prop complete input roster differs')
    E=unreal.EditorAssetLibrary;raw=E.load_asset(raw_path);mi=loaded[args['material']]
    if not isinstance(raw,unreal.StaticMesh) or not isinstance(mi,unreal.MaterialInterface):raise ValueError('Hidamari native input types differ')
    _identity(raw,raw_path)
    if E.does_asset_exist(destination):raise ValueError('Hidamari prop output must be fresh')
    unreal.load_module('StaticMeshEditor');editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if editor is None:raise ValueError('StaticMeshEditor unavailable')
    native_triangles=raw.get_num_triangles(0)
    tolerance=max(2,.02*receipt['triangles']) if definition['upright'] else 0
    if abs(native_triangles-receipt['triangles'])>tolerance:raise ValueError('Hidamari imported source triangle accounting differs')
    precision=editor.get_lod_build_settings(raw,0).get_editor_property('use_full_precision_u_vs')
    mesh=E.duplicate_asset(raw_path,destination)
    if not isinstance(mesh,unreal.StaticMesh) or mesh is raw:raise ValueError('Hidamari raw duplicate failed')
    _identity(mesh,destination)
    if len(mesh.static_materials)!=1 or str(mesh.static_materials[0].get_editor_property('imported_material_slot_name'))!=facts['slots'][0]:raise ValueError('Hidamari original complete draw slot differs')
    mesh.set_material(0,mi)
    flag=unreal.CollisionTraceFlag.CTF_USE_DEFAULT if record['info']['boxes'] else unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX
    body=mesh.get_editor_property('body_setup')
    if body is None:raise ValueError('Hidamari prop has no BodySetup')
    body.set_editor_property('collision_trace_flag',flag)
    levels=[record['level']]
    if definition['upright'] and level==0:
        if len(rows)!=3 or len(args['lod_records'])!=3:raise ValueError('Hidamari base requires all three actual native LODs')
        by_name={r['piece']:r for r in rows}
        if set(by_name)!={base+'_LOD'+str(i) for i in range(1,4)}:raise ValueError('Hidamari captured LOD roster differs')
        for index,selection in enumerate(args['lod_records'],1):
            value=read_data(context,selection);key=base+'_LOD'+str(index);slot=by_name[key]['slot'];package='/Game/Japan/Hidamari/PropLODs/'+base+'/'+key
            if _selected(context,slot)!=package or value.get('name')!=key or value.get('parent')!=base or value.get('lod')!=index or value['info']!=record['info'] or value['hulls']:raise ValueError('Hidamari LOD record/source ownership differs')
            source=E.load_asset(package)
            if not isinstance(source,unreal.StaticMesh) or source.get_material(0)!=mi:raise ValueError('Hidamari actual native LOD material differs')
            _identity(source,package);levels.append(value['level'])
            if editor.set_lod_from_static_mesh(mesh,index,source,0,True)!=index:raise ValueError('Hidamari declared native LOD installation failed')
        if not editor.set_lod_screen_sizes(mesh,[float(size) for _,size in levels]):raise ValueError('Hidamari LOD screens failed')
    elif rows or args['lod_records']:raise ValueError('Only base conifers consume sibling LOD Items')
    hulls=[]
    for hull in meta['collisions']:
        matrix=np.asarray(hull['matrix']);vertices=np.asarray(hull['vertices'])@matrix[:3,:3].T+matrix[:3,3]
        hulls.append([[float(v) for v in to_unreal(point)] for point in vertices])
    reader=getattr(getattr(unreal,'CitySurfaceValidation',None),'collision_vertices',None)
    if not callable(reader):raise ValueError('Hidamari actual convex readback unavailable')
    lo,hi=receipt['bounds'];bounds=([lo[0]*100,-hi[1]*100,lo[2]*100],[hi[0]*100,-lo[1]*100,hi[2]*100])
    def validate():
        box=mesh.get_bounding_box()
        if (mesh.get_num_triangles(0)!=native_triangles or mesh.get_num_lods()!=len(levels) or editor.get_num_uv_channels(mesh,0)!=1
                or len(mesh.static_materials)!=1 or mesh.get_material(0)!=mi or body.get_editor_property('collision_trace_flag')!=flag
                or editor.get_lod_build_settings(mesh,0).get_editor_property('use_full_precision_u_vs')!=precision
                or not collision_matches(mesh,{'source_collision_vertices':hulls},{'collision_hulls':len(hulls)},read_vertices=reader)
                or any(not abs(getattr(box.min,axis)-low)<.3 or not abs(getattr(box.max,axis)-high)<.3 for axis,low,high in zip('xyz',*bounds))):raise ValueError('Hidamari native source/material/UV/collision/bounds invariant failed')
        if len(levels)>1:
            counts=[mesh.get_num_triangles(i) for i in range(len(levels))];sizes=list(editor.get_lod_screen_sizes(mesh))
            if (any(abs(a-b)>max(2,.02*b) for a,(b,_) in zip(counts,levels)) or any(a<=b for a,b in zip(counts,counts[1:]))
                    or len(sizes)!=len(levels) or any(abs(a-b)>1e-5 for a,(_,b) in zip(sizes,levels))):raise ValueError('Hidamari original complete LOD validation failed')
    validate();native_packages.save(mesh,E,context.content_dir);validate();return mesh


def run(context):
    if context.params.get('args',{}).get('op')=='material':return material(context)
    return prop(context)
