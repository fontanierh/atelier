"""Strict semantic Bike union against frozen, actual immutable original source and FBX."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace

GAME=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(GAME/'world'));sys.path.insert(0,str(GAME/'tools'))
import yori  # noqa: E402,F401
from atelier import mesh_ir  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atomic_equivalence import face_counter,fbx_counter  # noqa: E402
from bike_sources import STEERING  # noqa: E402
import plan_vehicle_part  # noqa: E402
import plan_bike_layout  # noqa: E402
import export_region_piece  # noqa: E402


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--spec',type=Path,required=True);parser.add_argument('--sha256',required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);assert sha(args.spec)==args.sha256
    spec=json.loads(args.spec.read_text());root=Path(spec['output']);assert not root.exists();root.mkdir()
    for path,digest in spec['inputs'].items():assert sha(path)==digest,path
    baseline=Path(spec['baseline']);old=json.loads((baseline/'result.json').read_text())
    current=root/'current';records={};source_union={};fbx_union={}
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
        original_layout_equal=True,one_piece_edit='BK_Steer_BasketRim',unchanged_canonical_exports=len(files),inputs=spec['inputs'],
        scope='source/serialized FBX/layout/file-only assembly only; actual native GPU/cook/logical sphere/runtime pending'))
    print('BIKE ATOMIC ORIGINAL EQUIVALENCE COMPLETE',flush=True)


if __name__=='__main__':main()
