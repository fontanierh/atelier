"""Real immutable Village primitive-hull export versus the complete atomic corner path."""
import sys
sys.dont_write_bytecode=True
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

import bpy

GAME=Path(__file__).resolve().parents[2]
REPO=GAME.parents[1]
sys.path[:0]=[str(GAME/'world'),str(GAME/'world/regions'),str(Path(__file__).parent)]
import yori  # noqa: E402,F401
from atelier import mesh_ir,mesh_collision  # noqa: E402
from region_mesh_parts import capture_colliders,plan  # noqa: E402
from export_region_piece import main as export_piece  # noqa: E402
from fbx_face_digests import read as exported  # noqa: E402

REVISION='283329c07ea04bee34587022a3d43827468c66d7'
MEMBER='games/yorimichi/world/regions/village/mesh.py'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    from atelier.export_manifest import real_directory
    root=real_directory(args.output)
    if root.exists() or root.is_symlink():raise ValueError('Collision proof output must be fresh')
    root.mkdir(parents=True);(root/'baseline/assets').mkdir(parents=True)
    source=subprocess.check_output(['git','show',REVISION+':'+MEMBER],cwd=REPO,text=True)
    original=dict(__name__='immutable_village_collision_source',__file__=str(REPO/MEMBER))
    exec(compile(source,REVISION+':'+MEMBER,'exec'),original)
    original['OUT']=root/'baseline'
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mesh=original['Mesh']('AtomicCollisionFixture')
    with mesh.at((3.125,-4.25,1.5),33.):
        mesh.box((0.,0.,1.),(2.,3.,2.),(.3,.4,.5))
        mesh.collider((.125,.25,.75),(1.25,2.5,1.5))
    with mesh.at((-2.5,1.125,.5),-71.):
        mesh.collider((-.125,.5,.75),(2.25,1.5,.75))
    original['export'](mesh,bpy.data.materials.new('Village_Palette'))
    expected=exported(root/'baseline/assets/AtomicCollisionFixture.fbx')
    assert expected['render'] and expected['collision']
    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj=mesh.object(bpy.data.materials.new('Village_Palette'))
    collisions=capture_colliders(mesh.colliders)
    assert len(collisions)==2
    for collision in collisions:
        piece=mesh_collision.decode(collision)
        assert [key for key,_ in piece['uvs']]==['UVMap'] and piece['slots']==[]
        assert piece['selection']['uv_active']==piece['selection']['uv_render']=='UVMap'
        assert not piece['colours'] and not piece['smooth'].any()
    options=dict(apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',axis_forward='-Y',axis_up='Z',
                 mesh_smooth_type='FACE',use_custom_props=False)
    result=plan(obj,root/'planned',partition='whole',collisions=collisions,options=options)
    actual=dict(render=Counter(),collision=Counter())
    for row in result['pieces']:
        packet=root/'planned'/row['payload'];meta,_=mesh_ir.decode(packet.read_bytes())
        export_piece(['--input',str(packet),'--output',str(root/'exports'/row['name']),'--format','.fbx'])
        observed=exported(root/'exports'/row['name']/(row['name']+'.fbx'))
        for key in actual:actual[key].update(observed[key])
        assert len(meta['collisions'])==row['collision_hulls']
    if actual!=expected:raise ValueError('Actual original/atomic FBX corners, collision channels or frames differ')
    value=dict(complete=True,scope='actual immutable Village render and two authored cube hulls; full numeric FBX corner/frame union',
        baseline_revision=REVISION,baseline_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        render_polygons=sum(actual['render'].values()),collision_polygons=sum(actual['collision'].values()),
        pieces=len(result['pieces']),collision_hulls=2,collision_uvs=['UVMap'],material_free_hulls=True)
    (root/'result.json').write_text(json.dumps(value,indent=2)+'\n')
    print('COMPLETE COLLISION CORNER CANARY PASS',flush=True)


if __name__=='__main__':main()
