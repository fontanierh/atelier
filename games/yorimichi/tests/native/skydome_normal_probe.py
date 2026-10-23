"""Observe actual original/selected BMesh sphere cache and allocator behavior; no tolerance waiver."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

GAME=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(GAME/'world'))
import yori  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from atelier import mesh_ir  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from mesh_pieces import capture,subset  # noqa: E402
import asset_mesh  # noqa: E402


def observe(obj,path):
    source=capture(obj.data);piece=subset(source,tuple(range(len(source['counts']))))
    data=mesh_ir.encode(piece,key='SkyDome',slots=[slot.name for slot in source['slots']],
        matrix=[list(row) for row in obj.matrix_world],options={})
    mesh_ir.write(path,data)
    return mesh_ir.decode(data)


def compare(before,after):
    am,a=before;bm,b=after
    report=dict(positions_equal=np.array_equal(a['positions'],b['positions']),
        polygons=len(a['faces']),unmatched=0,rotated=0,normal_components=0,normal_max_abs=0.,uv_components=0)
    ao=bo=0
    for af,bf in zip(a['faces'],b['faces']):
        av=a['positions'][af];bv=b['positions'][bf];offsets=[]
        if len(af)==len(bf):
            offsets=[i for i in range(len(bf)) if av.tobytes()==np.roll(bv,-i,axis=0).tobytes()]
        if len(offsets)!=1:report['unmatched']+=1
        else:
            shift=offsets[0];report['rotated']+=int(shift!=0)
            bn=np.roll(b['normals'][bo:bo+len(bf)],-shift,axis=0);an=a['normals'][ao:ao+len(af)]
            report['normal_components']+=int(np.count_nonzero(an.view('u4')!=bn.view('u4')))
            report['normal_max_abs']=max(report['normal_max_abs'],float(np.max(np.abs(an-bn))))
            for (_,au),(_,bu) in zip(a['uvs'],b['uvs']):
                report['uv_components']+=int(np.count_nonzero(au[ao:ao+len(af)].view('u4')!=np.roll(bu[bo:bo+len(bf)],-shift,axis=0).view('u4')))
        ao+=len(af);bo+=len(bf)
    return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--spec',type=Path,required=True);parser.add_argument('--sha256',required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);raw=args.spec.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==args.sha256
    spec=json.loads(raw);root=Path(spec['output']);assert not root.exists();root.mkdir()
    for path,digest in spec['inputs'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
    yori.OUT=root/'original';yori.TEXTURES=Path(spec['textures'])
    asset_mesh.OUTDIR=str(yori.OUT/'assets');asset_mesh.TEX=str(yori.TEXTURES);asset_mesh.MATS.clear()
    ms=importlib.util.spec_from_file_location('immutable_original_skydome_probe',spec['original']);old=importlib.util.module_from_spec(ms);ms.loader.exec_module(old)
    saved=sys.argv;sys.argv=['original','--']
    try:old.main()
    finally:sys.argv=saved
    original=observe(bpy.data.objects['SkyDome'],root/'original-post-export.npz')
    selected=json.loads(Path(spec['selected']).read_text());records={};previous=None
    for repeat in range(4):
        bpy.ops.wm.read_factory_settings(use_empty=True);asset_mesh.MATS.clear()
        for key,value in selected['materials'].items():asset_mesh.mat(key,**value)
        scope={};exec(compile(selected['program'],spec['selected'],'exec'),scope)
        obj=scope[selected['builder']](selected['asset'],*selected['args'])
        observations={};observations['created']=observe(obj,root/f'selected-{repeat}-created.npz')
        bpy.context.view_layer.update();observations['view_update']=observe(obj,root/f'selected-{repeat}-view-update.npz')
        obj.data.update();observations['mesh_update']=observe(obj,root/f'selected-{repeat}-mesh-update.npz')
        asset_mesh.OUTDIR=str(root/f'selected-export-{repeat}');asset_mesh.export(obj,'SkyDome')
        observations['exported']=observe(obj,root/f'selected-{repeat}-exported.npz')
        records[str(repeat)]={name:compare(original,value) for name,value in observations.items()}
        records[str(repeat)]['cache_changes']={name:compare(observations['created'],value) for name,value in observations.items()}
        if previous is not None:records[str(repeat)]['previous_selected']=compare(previous,observations['created'])
        previous=observations['created']
        print('SKYDOME NORMAL PROBE '+str(repeat)+' '+json.dumps(records[str(repeat)]),flush=True)
    for path,digest in spec['inputs'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
    atomic_json(root/'result.json',dict(complete=True,observations=records,
        scope='diagnostic exact original/selected mesh observations only; no source/export/native acceptance'))
    print('SKYDOME NORMAL PROBE COMPLETE',flush=True)


if __name__=='__main__':main()
