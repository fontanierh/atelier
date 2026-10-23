"""Processless Blender comparison of the executed original and selected world props."""
import sys
sys.dont_write_bytecode=True
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import threading
import time

GAME=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(GAME/'world'));sys.path.insert(0,str(GAME/'tools'))
import yori  # noqa: E402
from atelier import mesh_ir  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from mesh_pieces import capture,subset  # noqa: E402
from atomic_equivalence import face_counter,fbx_counter  # noqa: E402

STAGE=['starting']


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(paths):
    result={}
    for path in paths:
        path=Path(path);stat=path.stat()
        assert path.is_file() and not path.is_symlink(),path
        result[str(path)]=dict(sha256=sha(path),stat=[stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns])
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--spec',type=Path,required=True);parser.add_argument('--sha256',required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);assert sha(args.spec)==args.sha256
    spec=json.loads(args.spec.read_text());root=Path(spec['output']);assert not root.exists();root.mkdir()
    assert identity(spec['inputs'])==spec['inputs']
    yori.OUT=root/'original';yori.TEXTURES=Path(spec['textures'])
    import bpy
    import asset_mesh
    from prop_sources import BUILDERS
    import plan_world_prop
    import export_region_piece
    assert set(BUILDERS)==set(spec['sources'])
    asset_mesh.OUTDIR=str(yori.OUT/'assets');asset_mesh.TEX=str(yori.TEXTURES);asset_mesh.MATS.clear()
    old_path=Path(spec['original'])
    module_spec=importlib.util.spec_from_file_location('immutable_original_world_props',old_path)
    old=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(old)
    STAGE[0]='execute original fourteen-constructor build and original FBX exporter'
    saved=sys.argv;sys.argv=['original-world-props','--']
    try:old.main()
    finally:sys.argv=saved
    objects={obj.name:obj for obj in bpy.context.scene.objects if obj.type=='MESH'}
    assert set(objects)==set(BUILDERS),'Executed original export census differs'
    original={}
    for name,obj in objects.items():
        source=capture(obj.data);piece=subset(source,tuple(range(len(source['counts']))))
        payload=mesh_ir.encode(piece,key=name,slots=[slot.name for slot in source['slots']],
            matrix=[list(row) for row in obj.matrix_world],options={})
        meta,decoded=mesh_ir.decode(payload)
        packet=root/'baseline'/(name+'.npz');mesh_ir.write(packet,payload)
        original[name]=dict(source=face_counter(meta,decoded),fbx=fbx_counter(yori.OUT/'assets'/(name+'.fbx')),
                            triangles=decoded['triangles'])
    records={};export_files={}
    for index,name in enumerate(BUILDERS,1):
        STAGE[0]=f'selected prop {index}/14 {name}'
        plan_root=root/'plans'/name
        plan_world_prop.main(['--source',spec['sources'][name],'--output',str(plan_root)])
        value=json.loads((plan_root/'plan.json').read_text());assert len(value['pieces'])==1
        row=value['pieces'][0];payload=plan_root/row['payload'];meta,piece=mesh_ir.decode(payload.read_bytes())
        assert face_counter(meta,piece)==original[name]['source'],name+' complete source corners'
        assert piece['triangles']==original[name]['triangles'],name+' original triangle count'
        output=root/'exports'/name
        export_region_piece.main(['--input',str(payload),'--output',str(output)])
        primary=output/(name+'.fbx')
        assert fbx_counter(primary)==original[name]['fbx'],name+' complete serialized corners/material names'
        export_files[name]=primary
        records[name]=dict(triangles=piece['triangles'],sha256=sha(primary),source_equal=True,fbx_equal=True)
        print(f'WORLD PROP EQUIVALENCE {index}/14 {name} PASS',flush=True)
    before=identity(export_files.values());name='Guardrail'
    edited=json.loads(Path(spec['sources'][name]).read_text());edited['args']=[2.25]
    edited_path=root/'one-edit/source.json';atomic_json(edited_path,edited)
    plan_world_prop.main(['--source',str(edited_path),'--output',str(root/'one-edit/plan')])
    export_region_piece.main(['--input',str(root/'one-edit/plan/Guardrail.npz'),'--output',str(root/'one-edit/export')])
    assert fbx_counter(root/'one-edit/export/Guardrail.fbx')!=original[name]['fbx'],'Actual one-piece geometry did not change'
    assert identity(export_files.values())==before,'One edit touched unrelated canonical exports'
    assert identity(spec['inputs'])==spec['inputs'],'Frozen source/donor inputs changed'
    atomic_json(root/'result.json',dict(complete=True,assets=records,original_export_census=list(BUILDERS),
        one_piece_edit=True,unchanged_canonical_exports=len(before),inputs=spec['inputs'],
        scope='source attributes and serialized FBX ordered corner/material-name equality; no Unreal/cook/runtime acceptance'))
    print('WORLD PROPS ORIGINAL EQUIVALENCE COMPLETE',flush=True)


if __name__=='__main__':
    done=threading.Event();started=time.monotonic()
    def heartbeat():
        while not done.wait(20):print(f'World prop proof {time.monotonic()-started:.0f}s: {STAGE[0]}',flush=True)
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    try:main()
    finally:done.set();thread.join(timeout=1)
