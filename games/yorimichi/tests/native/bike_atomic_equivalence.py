"""Strict semantic Bike union against frozen, actual immutable original source and FBX."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import struct
from types import SimpleNamespace

GAME=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(GAME/'world'));sys.path.insert(0,str(GAME/'tools'))
import yori  # noqa: E402,F401
import bpy  # noqa: E402
from mesh_pieces import capture,subset  # noqa: E402
from atelier import mesh_ir  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atomic_equivalence import face_counter,fbx_counter  # noqa: E402
from bike_sources import STEERING  # noqa: E402
import plan_vehicle_part  # noqa: E402
import plan_bike_layout  # noqa: E402
import build_bike_scene  # noqa: E402
import export_region_piece  # noqa: E402


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def serialized_materials(path):
    # Independently compare every actual serialized material field/array, not only
    # the material label used by the shared polygon counter. Object UIDs are local.
    from io_scene_fbx import parse_fbx
    tree,_=parse_fbx.parse(str(path))
    def prop(value):
        if isinstance(value,float):return ('float64',struct.pack('<d',value).hex())
        if isinstance(value,bytes):return ('bytes',value.hex())
        if isinstance(value,(str,int,bool)):return (type(value).__name__,value)
        return ('array',tuple(prop(item) for item in value))
    def element(node):return (node.id,tuple(prop(value) for value in node.props),tuple(element(child) for child in node.elems))
    objects=next(node for node in tree.elems if node.id==b'Objects')
    values={}
    for node in objects.elems:
        if node.id==b'Material':
            name=node.props[1];value=(tuple(prop(p) for p in node.props[1:]),tuple(element(child) for child in node.elems))
            assert name not in values;values[name]=value
    assert values
    return values


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--spec',type=Path,required=True);parser.add_argument('--sha256',required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);assert sha(args.spec)==args.sha256
    spec=json.loads(args.spec.read_text());root=Path(spec['output']);assert not root.exists();root.mkdir()
    for path,digest in spec['inputs'].items():assert sha(path)==digest,path
    baseline=Path(spec['baseline']);old=json.loads((baseline/'result.json').read_text())
    current=root/'current';records={};source_union={};fbx_union={};material_fields={}
    for key,source in spec['sources'].items():
        parent='BK_Steer' if key in STEERING else key
        plans=current/'planned_exports/vehicle_bike'/key;report=current/'vehicle-part-reports/bike'/(key+'.json')
        plan_vehicle_part.main(['--source',source,'--output',str(plans),'--report',str(report)])
        value=json.loads((plans/'plan.json').read_text());assert len(value['pieces'])==1
        row=value['pieces'][0];payload=plans/row['payload'];meta,piece=mesh_ir.decode(payload.read_bytes())
        assert not meta['collisions']
        source_union.setdefault(parent,Counter()).update(face_counter(meta,piece))
        output=current/'exports/world.vehicle_bike.export'/key
        export_region_piece.main(['--input',str(payload),'--output',str(output)])
        encoded,count=fbx_counter(output/(key+'.fbx'));assert count==piece['triangles'] and not encoded['collision']
        fbx_union.setdefault(parent,Counter()).update(encoded['render'])
        materials=serialized_materials(output/(key+'.fbx'))
        assert materials==serialized_materials(baseline/'data/bike/assets'/(parent+'.fbx')),key+' all serialized material properties'
        material_fields[key]=True
        records[key]=dict(triangles=piece['triangles'],parent=parent)
        if parent!='BK_Steer':assert json.loads(report.read_text())==old['assets'][parent]['report'],key+' original report'
        print('BIKE ATOMIC EXPORTED '+key+' '+str(piece['triangles']),flush=True)
    for parent,value in old['assets'].items():
        expected=Counter()
        for row in value['packets']:
            meta,piece=mesh_ir.decode((baseline/'baseline'/parent/row['path']).read_bytes());expected.update(face_counter(meta,piece))
        assert source_union[parent]==expected,parent+' strict complete original source corners'
        assert fbx_union[parent]==fbx_counter(baseline/'data/bike/assets'/(parent+'.fbx'))[0]['render'],parent+' strict complete serialized FBX'
        print('BIKE ORIGINAL SOURCE/FBX UNION '+parent+' PASS',flush=True)
    plan_bike_layout.main(['--source',spec['layout_source'],'--output',str(current/'bike-layout.json')])
    module_spec=importlib.util.spec_from_file_location('actual_bike_recipe',GAME/'vehicle_atomic_build.py')
    recipe=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(recipe);context=SimpleNamespace(out=current)
    for step in recipe.steps(context,'bike'):
        for command in step.commands:
            if hasattr(command,'fn'):command.fn(context,io.StringIO())
    manifest=json.loads((current/'bike/manifest.json').read_text());original=json.loads((baseline/'data/bike/manifest.json').read_text())
    assert {key:value for key,value in manifest.items() if key not in ('parts','steering_parts')}=={key:value for key,value in original.items() if key!='parts'}
    assert set(manifest['parts'])==set(records) and set(manifest['steering_parts'])==set(STEERING)
    assert sum(row['triangles'] for row in records.values())==sum(row['triangles'] for row in original['parts'].values())
    build_bike_scene.main(['--plans',str(current/'planned_exports/vehicle_bike'),
        '--layout',str(current/'bike-layout.json'),'--output',str(current/'bike/Bike.blend')])
    def assembled(path):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        with bpy.data.libraries.load(str(path),link=False) as (available,loaded):
            loaded.objects=[name for name in available.objects if name.startswith('BK_')]
        total=Counter();members=[]
        for obj in loaded.objects:
            assert obj and obj.type=='MESH'
            bpy.context.collection.objects.link(obj);members.append(obj.name)
            data=capture(obj.data);groups=[];selected=[];triangles=0
            # Observation of the original whole uses contiguous source-face chunks,
            # never the production semantic partitioner or a raised codec budget.
            for index,count in enumerate(data['counts']):
                if selected and triangles+int(count)-2>32768:
                    groups.append(selected);selected=[];triangles=0
                selected.append(index);triangles+=int(count)-2
            if selected:groups.append(selected)
            for index,faces in enumerate(groups):
                piece=subset(data,tuple(faces))
                payload=mesh_ir.encode(piece,key=obj.name.replace('.','_')+str(index),slots=[slot.name for slot in data['slots']],
                    matrix=[list(row) for row in obj.matrix_world],options={},collisions=[])
                meta,piece=mesh_ir.decode(payload);total.update(face_counter(meta,piece))
        return total,members
    posed_original,original_members=assembled(baseline/'data/bike/Bike.blend')
    posed_actual,actual_members=assembled(current/'bike/Bike.blend')
    assert len(original_members)==9 and len(actual_members)==12
    assert posed_actual==posed_original,'Full saved posed Bicycle source frame/attributes/multiplicity'
    print('BIKE ORIGINAL FULL ASSEMBLED POSE PASS',flush=True)
    files={key:sha(current/'bike/assets'/(key+'.fbx')) for key in records}
    key='BK_Steer_BasketRim';edited=json.loads(Path(spec['sources'][key]).read_text())
    before='m.tube(rim + [rim[0]], 0.0085';assert before in edited['program']
    edited['program']=edited['program'].replace(before,'m.tube(rim + [rim[0]], 0.0086')
    atomic_json(root/'one-edit/source.json',edited)
    plan_vehicle_part.main(['--source',str(root/'one-edit/source.json'),'--output',str(root/'one-edit/plan'),'--report',str(root/'one-edit/report.json')])
    export_region_piece.main(['--input',str(root/'one-edit/plan'/(key+'.npz')),'--output',str(root/'one-edit/export')])
    assert fbx_counter(root/'one-edit/export'/(key+'.fbx'))!=fbx_counter(current/'bike/assets'/(key+'.fbx'))
    assert files=={key:sha(current/'bike/assets'/(key+'.fbx')) for key in records}
    for path,digest in spec['inputs'].items():assert sha(path)==digest,path
    atomic_json(root/'result.json',dict(complete=True,assets=records,exact_original_source_and_fbx_union=True,
        original_layout_equal=True,assembled_pose_equal=True,serialized_material_fields_equal=material_fields,one_piece_edit='BK_Steer_BasketRim',unchanged_canonical_exports=len(files),inputs=spec['inputs'],
        scope='source/serialized FBX/layout/file-only assembly only; actual native GPU/cook/logical sphere/runtime pending'))
    print('BIKE ATOMIC ORIGINAL EQUIVALENCE COMPLETE',flush=True)


if __name__=='__main__':main()
