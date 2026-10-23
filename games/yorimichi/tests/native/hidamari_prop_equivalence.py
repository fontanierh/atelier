"""Independent immutable-original Hidamari prop/source/FBX and native readback proof.

The host supplies a SHA-bound spec, frozen original source files, frozen models,
and the sealed selected implementation. This script never runs Git/subprocesses.
Run source mode in ordinary guarded Blender; native mode reads caller-owned saved
components in ordinary guarded Unreal. Fixture readback never certifies runtime.
"""
import argparse
import array
import ast
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import struct
import threading
import time
import types

import numpy as np

GAME=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(GAME/'world'),str(GAME/'tools'),str(GAME/'tests/native'),str(GAME/'unreal/Scripts')]
import yori  # noqa: E402,F401
from atelier import mesh_ir  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atomic_equivalence import artifact,canonical,fbx_counter,hull_counter,native_raw_set,require,component_bounds  # noqa: E402

STAGE=['input preflight']


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_inputs(spec):
    require(isinstance(spec.get('inputs'),dict) and spec['inputs'],'Missing frozen proof input inventory')
    for path,digest in spec['inputs'].items():artifact(dict(path=path,sha256=digest))


def members(props,trees):
    require(len(props)==32 and len(trees)==4,'Original immutable prop/conifer census changed')
    result=[*props,*(name if lod==0 else name+'_LOD'+str(lod) for name in trees for lod in range(4))]
    require(len(result)==48 and len(set(result))==48,'Incomplete/duplicate original 48-export census')
    return result


def _array(value,dtype):
    value=np.ascontiguousarray(value,dtype=dtype)
    require(np.isfinite(value).all(),'Nonfinite observed source channel')
    return dict(dtype=str(value.dtype),shape=list(value.shape),sha256=hashlib.sha256(value.tobytes()).hexdigest())


def piece_signature(piece,slots,matrix):
    """Observe every ordered source corner independently of the production capture."""
    faces=piece['faces'];indices=np.asarray([i for face in faces for i in face],dtype='<i4')
    positions=np.asarray(piece['positions'],dtype='<f4')
    return dict(counts=[len(face) for face in faces],all_positions=_array(positions,'<f4'),positions=_array(positions[indices],'<f4'),
        normals=_array(piece['normals'],'<f4'),materials=_array(piece['materials'],'<i4'),
        smooth=_array(piece['smooth'],'?'),slots=list(slots),matrix=np.asarray(matrix,dtype='<f8').tolist(),selection=dict(piece['selection']),
        uvs=[dict(name=name,data=_array(values,'<f4')) for name,values in piece['uvs']],
        point_colours=[dict(name=name,kind=kind,data=_array(values,'<f4')) for name,domain,kind,values in piece['colours'] if domain=='POINT'],
        colours=[dict(name=name,domain=domain,kind=kind,data=_array(np.asarray(values)[indices] if domain=='POINT' else values,'<f4'))
            for name,domain,kind,values in piece['colours']])


def source_signature(obj):
    mesh=obj.data
    positions=[tuple(v.co) for v in mesh.vertices];faces=[list(p.vertices) for p in mesh.polygons]
    uvs=[(layer.name,[tuple(v.uv) for v in layer.data]) for layer in mesh.uv_layers]
    colours=[(layer.name,layer.domain,layer.data_type,[tuple(v.color) for v in layer.data]) for layer in mesh.color_attributes]
    def color(index):return mesh.color_attributes[index].name if 0<=index<len(mesh.color_attributes) else None
    known={'position','material_index','sharp_face','sharp_edge','custom_normal'}|{n for n,_ in uvs}|{n for n,*_ in colours}
    require(all(a.name in known for a in mesh.attributes if not a.is_internal and not a.name.startswith('.')),
        'Unsupported original/current source channel')
    piece=dict(positions=positions,faces=faces,normals=[tuple(v.vector) for v in mesh.corner_normals],
        materials=[p.material_index for p in mesh.polygons],smooth=[p.use_smooth for p in mesh.polygons],uvs=uvs,colours=colours,
        selection=dict(uv_active=mesh.uv_layers.active.name if mesh.uv_layers.active else None,
            uv_render=next((layer.name for layer in mesh.uv_layers if layer.active_render),None),
            colour_active=color(mesh.color_attributes.active_color_index),colour_render=color(mesh.color_attributes.render_color_index)))
    return piece_signature(piece,[slot.name for slot in mesh.materials],[list(row) for row in obj.matrix_world])


def hull_signature(obj):
    return dict(source=source_signature(obj),positions=[list(v.co) for v in obj.data.vertices],
        faces=[list(p.vertices) for p in obj.data.polygons],matrix=[list(row) for row in obj.matrix_world],
        transform=dict(location=list(obj.location),scale=list(obj.scale),rotation_mode=obj.rotation_mode,
            rotation_euler=list(obj.rotation_euler),rotation_quaternion=list(obj.rotation_quaternion),
            rotation_axis_angle=list(obj.rotation_axis_angle)))


def fbx_fields(path):
    """Complete actual Objects, Connections and global settings, excluding local UIDs.

    Unlike triangle counts or representative corners, this includes every geometry
    array, smoothing/channel mapping, material property and authored model frame.
    Geometry datablock labels are keyed by their unique actual bound Model name:
    the immutable fit called the collision datablock Cube while its actual UCX
    Model identity is unchanged. Model names/bindings and all actual geometry
    fields remain exact. Header timestamps/file paths are outside this scope.
    """
    from io_scene_fbx import parse_fbx
    root,_=parse_fbx.parse(str(path))
    objects=next(node for node in root.elems if node.id==b'Objects')
    table={node.props[0]:node for node in objects.elems}
    connections=next(node for node in root.elems if node.id==b'Connections')
    geometry_names={}
    for geometry in (node for node in objects.elems if node.id==b'Geometry'):
        owners=[table[row.props[2]] for row in connections.elems if row.id==b'C'
            and len(row.props)==3 and row.props[0]==b'OO' and row.props[1]==geometry.props[0]
            and row.props[2] in table and table[row.props[2]].id==b'Model']
        require(len(owners)==1,'Serialized geometry lacks a unique actual Model owner')
        geometry_names[geometry.props[0]]=owners[0].props[1]
    identities={node.props[0]:(node.id,node.props[1]) for node in objects.elems}
    identities.update({key:(b'Geometry',name) for key,name in geometry_names.items()})
    require(len(identities)==len(objects.elems) and len(set(identities.values()))==len(identities),
        'Ambiguous actual serialized object identities')
    def value(v):
        if isinstance(v,bytes):return ['bytes',v.hex()]
        if isinstance(v,(str,int,bool)):return [type(v).__name__,v]
        if isinstance(v,float):
            require(np.isfinite(v),'Nonfinite serialized FBX property')
            return ['float64',struct.pack('<d',v).hex()]
        if isinstance(v,array.array):
            require(np.isfinite(np.asarray(v)).all(),'Nonfinite serialized FBX array')
            return ['array',v.typecode,len(v),hashlib.sha256(v.tobytes()).hexdigest()]
        return [type(v).__name__,getattr(v,'typecode',None),[value(x) for x in v]]
    def node(n,object_root=False):
        props=list(n.props)
        if object_root:
            uid=props[0];props[0]=identities[uid]
            if n.id==b'Geometry':props[1]=geometry_names[uid]
        if n.id==b'C':
            for index in (1,2):
                props[index]=identities.get(props[index],('scene-root',props[index]))
        return [n.id.hex(),[value(v) for v in props],[node(child) for child in n.elems]]
    result=dict(objects=sorted((node(n,True) for n in objects.elems),key=lambda n:json.dumps(n,sort_keys=True)))
    for key in (b'Connections',b'GlobalSettings'):
        result[key.decode()]=node(next(n for n in root.elems if n.id==key))
    return hashlib.sha256(canonical(result)).hexdigest()


def texture_signature(path):
    import bpy
    image=bpy.data.images.load(str(path),check_existing=False)
    try:return dict(size=list(image.size),channels=image.channels,colorspace=image.colorspace_settings.name,
        pixels=_array(image.pixels[:],'<f4'))
    finally:bpy.data.images.remove(image)


def original_module(path,label):
    """Run immutable geometry unchanged; omit only diagnostic image render calls."""
    tree=ast.parse(Path(path).read_bytes())
    class DiagnosticOnly(ast.NodeTransformer):
        def visit_Expr(self,node):
            if isinstance(node.value,ast.Call) and ast.unparse(node.value.func)=='bpy.ops.render.render':
                return ast.copy_location(ast.Pass(),node)
            return self.generic_visit(node)
    tree=DiagnosticOnly().visit(tree);ast.fix_missing_locations(tree)
    module=types.ModuleType(label);module.__file__=str(path)
    exec(compile(tree,str(path),'exec'),module.__dict__)
    return module


def source_proof(spec):
    """@cc [owner:fontanierh,label:correctness] immutable-hidamari-prop-equivalence
    Execute the immutable original complete 48-export census. Every ordered source
    corner/channel/material/frame and whole hull MUST match the actual selected
    production planner and its payload; every numeric FBX field, fitted texture
    pixel and report MUST match. Missing/foreign exports or unsupported channels
    MUST refuse. Source/serialized proof MUST NOT claim native/runtime acceptance.
    Git authority belongs only to the enclosing host, outside guarded Blender.
    """
    import bpy
    from atelier.blender import fbx
    check_inputs(spec);root=Path(spec['output']);require(not root.exists(),'Fresh proof output required');root.mkdir()
    old=original_module(spec['original_props'],'immutable_hidamari_props')
    fit=original_module(spec['original_fit'],'immutable_hidamari_fit')
    old.kit=types.SimpleNamespace(fit=fit.fit);old.OUT=root/'original';old.SRC=Path(spec['models'])/'hidamari/props'
    tree_values={key:getattr(old.caldera,key) for key in ('TREES','LODS','SHELL','BASE','FLOAT','TARGET')}
    tree_values['source']=lambda key:Path(spec['tree_sources'][key]);old.caldera=types.SimpleNamespace(**tree_values)
    expected=members(['HD_P_'+slug for slug in old.PROPS],list(old.caldera.TREES))
    require(set(spec['parameters'])==set(expected),'Selected parameters differ from immutable complete census')
    originals={};original_export=fbx.export_fbx
    def observe(**options):
        objects=[obj for obj in bpy.context.selected_objects if obj.type=='MESH']
        renders=[obj for obj in objects if not obj.name.startswith('UCX_')]
        require(len(renders)==1,'Incomplete/ambiguous actual original export')
        obj=renders[0];key=obj.name;STAGE[0]='immutable original '+key
        require(key in expected and key not in originals,'Foreign/duplicate immutable original export')
        originals[key]=dict(source=source_signature(obj),hulls=[hull_signature(o) for o in objects if o.name.startswith('UCX_')])
        result=original_export(**options)
        originals[key].update(fbx_fields=fbx_fields(options['filepath']),triangles=fbx_counter(options['filepath'])[1])
        atomic_json(root/'original-source'/(key+'.json'),originals[key])
        print('HIDAMARI ORIGINAL SOURCE/FBX '+str(len(originals))+'/48 '+key,flush=True)
        return result
    fbx.export_fbx=observe
    try:old.main()
    finally:fbx.export_fbx=original_export
    require(set(originals)==set(expected),'Missing immutable original export')
    reports=json.loads((old.OUT/'props.json').read_text());require(len(reports)==36,'Incomplete original fitted report census')
    textures={name:texture_signature(old.OUT/(name+'.png')) for name in reports}
    from hidamari import plan_prop as planner
    from hidamari import plan_conifer as conifer_planner
    import export_region_piece
    actual_plan=planner.plan;records={}
    for key in expected:
        STAGE[0]='selected planner/source '+key
        parameters=Path(spec['parameters'][key]);params=json.loads(parameters.read_text());parent=params['parent']
        data=root/'selected-data'/key;plan=root/'selected-plans'/key
        def observe_plan(obj,*args,**kwargs):
            require(source_signature(obj)==originals[key]['source'],key+' ordered original source differs')
            require([hull_signature(h) for h in bpy.context.scene.objects if h.type=='MESH' and h.name.startswith('UCX_')]
                ==originals[key]['hulls'],key+' authored whole hull differs')
            return actual_plan(obj,*args,**kwargs)
        planner.plan=observe_plan
        try:(conifer_planner.main if params['upright'] else planner.main)(['--parameters',str(parameters),'--source',spec['sources'][parent],
            '--data',str(data),'--output',str(plan)])
        finally:planner.plan=actual_plan
        value=json.loads((plan/'plan.json').read_text());require(len(value['pieces'])==1,'Expected whole independently bounded prop')
        row=value['pieces'][0];require(row['name']==key,'Selected export identity changed')
        meta,piece=mesh_ir.decode((plan/row['payload']).read_bytes())
        require(piece_signature(piece,meta['slots'],meta['matrix'])==originals[key]['source'],key+' ordered payload corners differ')
        record=json.loads((data/'record.json').read_text());info=dict(reports[parent]);levels=info.pop('lods',None)
        require(record['info']==info,key+' fitted report differs')
        expected_level=levels[params['lod']] if levels else [info['triangles'],1.]
        require(record['level']==expected_level,key+' original authored LOD metadata differs')
        require(texture_signature(data/(parent+'.png'))==textures[parent],key+' fitted texture pixels differ')
        output=root/'selected-exports'/key
        export_region_piece.main(['--input',str(plan/row['payload']),'--output',str(output)])
        path=output/(key+'.fbx')
        require(fbx_counter(path)==fbx_counter(old.OUT/(key+'.fbx')),key+' all original FBX corners/frame/channels/hulls differ')
        require(fbx_fields(path)==originals[key]['fbx_fields'],key+' actual serialized FBX fields differ')
        records[key]=dict(triangles=piece['triangles'],source_equal=True,fbx_fields_equal=True,
            texture_equal=True,report_equal=True,payload_sha256=sha(plan/row['payload']),fbx_sha256=sha(path))
        atomic_json(root/'progress.json',dict(completed=len(records),total=48,last=key))
        print('HIDAMARI SELECTED SOURCE/FBX '+str(len(records))+'/48 '+key+' PASS',flush=True)
    require(set(records)==set(expected),'Incomplete final source/export proof')
    check_inputs(spec)
    result=dict(schema=1,source_complete=True,exporter_complete=True,native_complete=False,complete=False,
        assets=records,baseline_revision=spec['baseline_revision'],current_revision=spec['current_revision'],
        diagnostic_renders_excluded=True,scope='48 source/payload/serialized FBX; fitted report/texture pixels. Native/runtime remains separate.')
    atomic_json(root/'result.json',result)
    print('HIDAMARI PROP SOURCE/FBX EQUIVALENCE COMPLETE',flush=True)
    return result


def native_readback(spec):
    """Read all 48 actual saved caller-owned mesh components without import/mutation."""
    import unreal
    import atomic_equivalence_capture as capture
    check_inputs(spec);expected=members(spec['props'],spec['trees'])
    require(set(spec['components'])==set(spec['meshes'])==set(expected)
        and len(set(spec['components'].values()))==48 and len(set(spec['meshes'].values()))==48,
        'Native fixture lacks complete original unique 48-mesh census')
    records={}
    for key in expected:
        STAGE[0]='actual native readback '+key
        component=unreal.load_object(None,spec['components'][key]);require(component is not None,'Missing actual native fixture component')
        mesh=component.get_editor_property('static_mesh')
        require(mesh is not None and mesh.get_name()==key and mesh.get_path_name()==spec['meshes'][key],
            'Actual native fixture mesh identity differs from original export census')
        records[key]=capture.capture([component],key,Path(spec['output'])/key,controls=[],policy_scope='fixture',inputs=list(spec['inputs']))
        print('HIDAMARI NATIVE READBACK '+str(len(records))+'/48 '+key,flush=True)
    check_inputs(spec);atomic_json(Path(spec['output'])/'native.json',records)
    return records


def whole_bounds(record):
    """Whole logical exports must retain physical bounds, including single-LOD spheres."""
    policies=record.get('component_policies')
    require(isinstance(policies,list) and len(policies)==1,'Whole mesh needs exactly one observed component policy')
    row=json.loads(artifact(policies[0]));physical,logical=component_bounds(row)
    require(record.get('meshes')==[row.get('mesh')],'Whole bounds belong to a different native mesh')
    box=row.get('mesh_bounds');values=np.asarray(box)
    require(values.shape==(2,3) and values.dtype.kind in 'fi' and np.isfinite(values).all()
        and np.all(values[1]>=values[0]),'Missing actual whole mesh bounds')
    return dict(component_bounds=physical,mesh_bounds=box,bounds_scale=row['bounds_scale'],
        lod_coordinated=row['lod_coordinated'],logical_bounds=logical)


def compare_native(before,after,props,trees):
    """Host-only exact saved geometry/LOD/collision/material/settings comparison.

    Input descriptors retain observed component bounds/sphere and fixture policy.
    This result deliberately cannot certify production placement/probes/runtime.
    """
    expected=set(members(props,trees));require(set(before)==set(after)==expected,'Incomplete/foreign native readback census')
    for key in sorted(expected):
        require(whole_bounds(before[key])==whole_bounds(after[key]),key+' actual whole bounds differ')
        a=native_raw_set(before[key],key);b=native_raw_set(after[key],key)
        require(before[key]['policy_scope']==after[key]['policy_scope']=='fixture','Readback fixture scope is explicit')
        for field in ('source_lods','render_lods','cooked','hulls','policy','settings','source_presence'):
            require(a[field]==b[field],key+' actual native '+field+' differs')
    return dict(native_geometry_complete=True,whole_mesh_bounds_complete=True,native_complete=False,complete=False,meshes=48,
        scope='Saved fixture geometry/LOD/cook/collision/material/bounds policy only; production runtime/probes pending')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--spec',type=Path,required=True)
    parser.add_argument('--sha256',required=True);parser.add_argument('--native',action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    payload=artifact(dict(path=str(args.spec.absolute()),sha256=args.sha256));spec=json.loads(payload)
    result=native_readback(spec) if args.native else source_proof(spec)
    require(args.spec.read_bytes()==payload,'Proof spec changed during execution')
    return result


if __name__=='__main__':
    done=threading.Event();start=time.monotonic()
    def heartbeat():
        while not done.wait(25):print('HIDAMARI PROOF '+str(round(time.monotonic()-start))+'s: '+STAGE[0]+'; no new completed stage',flush=True)
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    try:main()
    finally:done.set();thread.join(timeout=1)
