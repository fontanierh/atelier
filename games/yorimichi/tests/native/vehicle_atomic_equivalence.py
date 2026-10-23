"""Execute immutable original vehicle exports, then independently construct/export each part."""
import argparse
import ast
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace

GAME=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(GAME/'world'));sys.path.insert(0,str(GAME/'tools'))
import yori  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from atelier import mesh_ir  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from mesh_pieces import capture,subset  # noqa: E402
from atomic_equivalence import face_counter,hull_counter,fbx_counter  # noqa: E402
from village import mesh as kernel  # noqa: E402
import plan_vehicle_part  # noqa: E402
import export_region_piece  # noqa: E402


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--spec',type=Path,required=True);parser.add_argument('--sha256',required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);assert sha(args.spec)==args.sha256
    spec=json.loads(args.spec.read_text());root=Path(spec['output']);assert not root.exists();root.mkdir()
    family=spec['family'];original_root=root/'original';original_root.mkdir();yori.OUT=original_root
    for path,digest in spec['inputs'].items():assert sha(path)==digest,path
    # Original hull discovery is independent of the new production capture helper.
    observed_ast=ast.parse(Path(spec['hull_observer']).read_text())
    observed_ast.body=[node for node in observed_ast.body if isinstance(node,ast.FunctionDef) and node.name=='original_hull']
    assert len(observed_ast.body)==1
    observer=dict(np=np);exec(compile(observed_ast,spec['hull_observer'],'exec'),observer)
    original_export=kernel.export;refs={};hulls={}
    def observe_hulls(objects):
        hulls['current']=[observer['original_hull'](hull)[0] for hull in objects]
    export_ast=ast.parse(Path(spec['kernel']).read_text())
    function=next(node for node in export_ast.body if isinstance(node,ast.FunctionDef) and node.name=='export')
    remove=next(index for index,node in enumerate(function.body) if isinstance(node,ast.For) and ast.unparse(node.iter)=='objs[1:]')
    function.body.insert(remove,ast.Expr(value=ast.Call(func=ast.Name(id='_observe_original_hulls',ctx=ast.Load()),
        args=[ast.Subscript(value=ast.Name(id='objs',ctx=ast.Load()),slice=ast.Slice(lower=ast.Constant(1)),ctx=ast.Load())],keywords=[])))
    ast.fix_missing_locations(function)
    namespace=dict(kernel.__dict__,OUT=original_root/family,_observe_original_hulls=observe_hulls)
    exec(compile(ast.Module(body=[function],type_ignores=[]),spec['kernel'],'exec'),namespace)
    def observed_export(mesh,material):
        obj,report=namespace['export'](mesh,material)
        source=capture(obj.data);piece=subset(source,tuple(range(len(source['counts']))))
        payload=mesh_ir.encode(piece,key=mesh.name,slots=[slot.name for slot in source['slots']],
            matrix=[list(row) for row in obj.matrix_world],options={},collisions=hulls['current'])
        path=root/'baseline'/(mesh.name+'.npz');mesh_ir.write(path,payload);meta,piece=mesh_ir.decode(payload)
        refs[mesh.name]=dict(source=face_counter(meta,piece),hulls=hull_counter(meta['collisions']),
            fbx=fbx_counter(original_root/family/'assets'/(mesh.name+'.fbx')),report=report)
        return obj,report
    kernel.export=observed_export
    module_spec=importlib.util.spec_from_file_location('immutable_original_vehicle',spec['original'])
    old=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(old)
    try:old.main()
    finally:kernel.export=original_export
    assert set(refs)==set(spec['sources']),'Original executed vehicle census differs'
    current=root/'current';records={}
    for key,source in spec['sources'].items():
        plans=current/'planned_exports'/('vehicle_'+family)/key
        report=current/'vehicle-part-reports'/family/(key+'.json')
        plan_vehicle_part.main(['--source',source,'--output',str(plans),'--report',str(report)])
        value=json.loads((plans/'plan.json').read_text());assert len(value['pieces'])==1
        row=value['pieces'][0];payload=plans/row['payload'];meta,piece=mesh_ir.decode(payload.read_bytes())
        assert face_counter(meta,piece)==refs[key]['source'],key+' original source corners'
        assert hull_counter(meta['collisions'])==refs[key]['hulls'],key+' complete original authored hulls'
        assert json.loads(report.read_text())==refs[key]['report'],key+' exact original construction report'
        output=current/'exports'/('world.vehicle_'+family+'.export')/key
        export_region_piece.main(['--input',str(payload),'--output',str(output)])
        assert fbx_counter(output/(key+'.fbx'))==refs[key]['fbx'],key+' complete actual FBX source/collision corners'
        records[key]=dict(triangles=piece['triangles'],hulls=len(meta['collisions']),source_equal=True,fbx_equal=True)
        print('VEHICLE ATOMIC ORIGINAL EQUIVALENCE '+key+' PASS',flush=True)
    module_spec=importlib.util.spec_from_file_location('actual_vehicle_recipe',GAME/'vehicle_atomic_build.py')
    recipe=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(recipe)
    context=SimpleNamespace(out=current)
    for step in recipe.steps(context,family):
        for command in step.commands:
            if hasattr(command,'fn'):command.fn(context,io.StringIO())
    old_manifest=json.loads((original_root/family/'manifest.json').read_text())
    assert json.loads((current/family/'manifest.json').read_text())==old_manifest,'Normal file-only assembly changed original manifest'
    files={key:sha(current/family/'assets'/(key+'.fbx')) for key in records}
    selected,before,after=spec['edit']
    edited=json.loads(Path(spec['sources'][selected]).read_text());edited['program']=edited['program'].replace(before,after)
    assert edited!=json.loads(Path(spec['sources'][selected]).read_text())
    source=root/'one-edit/source.json';atomic_json(source,edited)
    plan_vehicle_part.main(['--source',str(source),'--output',str(root/'one-edit/plan'),'--report',str(root/'one-edit/report.json')])
    export_region_piece.main(['--input',str(root/'one-edit/plan'/(selected+'.npz')),'--output',str(root/'one-edit/export')])
    assert fbx_counter(root/'one-edit/export'/(selected+'.fbx'))!=refs[selected]['fbx']
    assert {key:sha(current/family/'assets'/(key+'.fbx')) for key in records}==files
    for path,digest in spec['inputs'].items():assert sha(path)==digest,path
    atomic_json(root/'result.json',dict(complete=True,family=family,assets=records,exact_original_manifest=True,
        one_piece_edit=selected,unchanged_canonical_exports=len(files),inputs=spec['inputs'],
        scope='complete immutable original source/rich hull/serialized FBX and actual file-only assembly; native/runtime receiving remains separate'))
    print('VEHICLE ATOMIC ORIGINAL EQUIVALENCE COMPLETE',flush=True)


if __name__=='__main__':main()
