"""Observe the actual original Bike export census and steering semantic construction ranges."""
import argparse
import ast
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import threading
import time

GAME=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(GAME/'world'));sys.path.insert(0,str(GAME/'tools'));sys.path.insert(0,str(GAME/'tests/fixtures'))
import yori  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from atelier import mesh_ir  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atomic_equivalence import face_counter  # noqa: E402
from source_packets import captured,baseline_packets,signature  # noqa: E402

STAGE=['preflight']


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--spec',type=Path,required=True);parser.add_argument('--sha256',required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);assert sha(args.spec)==args.sha256
    spec=json.loads(args.spec.read_text());root=Path(spec['output']);assert not root.exists();root.mkdir()
    for path,digest in spec['inputs'].items():assert sha(path)==digest,path
    yori.OUT=root/'data'
    module_spec=importlib.util.spec_from_file_location('immutable_original_bike',spec['original'])
    old=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(old)
    boundaries={};records={};source_counters={}
    def boundary(mesh,key):
        STAGE[0]='original steering basket '+key
        boundaries[key]=dict(vertices=len(mesh.verts),faces=len(mesh.faces),triangles=sum(len(face)-2 for face in mesh.faces))
    old.__dict__['_observe_basket_boundary']=boundary
    tree=ast.parse(Path(spec['original']).read_text());basket=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='basket')
    def observe(key):return ast.Expr(value=ast.Call(func=ast.Name(id='_observe_basket_boundary',ctx=ast.Load()),args=[ast.Name(id='m',ctx=ast.Load()),ast.Constant(key)],keywords=[]))
    body=[];marked=set()
    for node in basket.body:
        targets=[value.id for target in node.targets for value in ast.walk(target) if isinstance(value,ast.Name)] if isinstance(node,ast.Assign) else []
        if 'rim' in targets and 'rim' not in marked:
            body.append(observe('rim'));marked.add('rim')
        if 'foot' in targets:body.append(observe('foot'))
        body.append(node)
    basket.body=[basket.body[0],observe('shell'),*body[1:],observe('end')]
    ast.fix_missing_locations(basket);exec(compile(ast.Module(body=[basket],type_ignores=[]),spec['original'],'exec'),old.__dict__)
    original_export=old.export
    def snapshot(obj,directory):
        data=captured(obj);matrix=[list(row) for row in obj.matrix_world]
        packets=baseline_packets(data,directory,obj.name,matrix)
        counter=Counter()
        for row in packets:
            meta,piece=mesh_ir.decode((directory/row['path']).read_bytes());counter.update(face_counter(meta,piece))
        return data,packets,counter
    def exported(mesh,material):
        STAGE[0]='original export '+mesh.name
        obj,report=original_export(mesh,material)
        data,packets,counter=snapshot(obj,root/'baseline'/mesh.name)
        source_counters[mesh.name]=counter
        source_faces=[data['vertex_indices'][start:start+count].tolist() for start,count in zip(data['starts'],data['counts'])]
        records[mesh.name]=dict(report=report,signature=signature(data),packets=packets,
            source_triangles=int(sum(data['counts']-2)),source_polygons=len(data['counts']),
            raw_positions_equal=np.asarray(mesh.verts,dtype='<f4').tobytes()==data['positions'].astype('<f4').tobytes(),
            raw_face_order_equal=[list(face) for face in mesh.faces]==source_faces)
        print('BIKE ORIGINAL EXPORTED '+mesh.name+' '+json.dumps({key:records[mesh.name][key] for key in ('source_triangles','source_polygons','raw_positions_equal','raw_face_order_equal')}),flush=True)
        return obj,report
    old.export=exported;STAGE[0]='actual original eight-part construction';old.main()
    constructors={'BK_Frame':lambda:old.frame(),'BK_Steer':lambda:old.steer(),
        'BK_WheelFront':lambda:old.wheel('BK_WheelFront',.048),'BK_WheelRear':lambda:old.wheel('BK_WheelRear',.050),
        'BK_Crank':lambda:old.crank(),'BK_Pedal':lambda:old.pedal(),'BK_Kickstand':lambda:old.kickstand(),'BK_RackBoard':lambda:old.rack_board()}
    assert set(records)==set(constructors)
    original_boundaries=dict(boundaries)
    for key,constructor in constructors.items():
        STAGE[0]='isolated whole-part probe '+key
        bpy.ops.wm.read_factory_settings(use_empty=True)
        mesh=constructor();obj=mesh.object(old.material());data,packets,counter=snapshot(obj,root/'selected-whole-probe'/key)
        records[key]['selected_whole_source_equal']=counter==source_counters[key]
        print('BIKE SELECTED WHOLE SOURCE '+key+' '+str(records[key]['selected_whole_source_equal']),flush=True)
    for path,digest in spec['inputs'].items():assert sha(path)==digest,path
    atomic_json(root/'result.json',dict(complete=True,assets=records,basket_boundaries=original_boundaries,
        scope='actual immutable original export census plus whole-part isolation probe; no split/native acceptance'))
    print('BIKE ORIGINAL CENSUS COMPLETE',flush=True)


if __name__=='__main__':
    done=threading.Event();started=time.monotonic()
    def heartbeat():
        while not done.wait(25):print(f'Bike source census {time.monotonic()-started:.0f}s: {STAGE[0]}; no additional completed stage',flush=True)
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    try:main()
    finally:done.set();thread.join(timeout=1)
