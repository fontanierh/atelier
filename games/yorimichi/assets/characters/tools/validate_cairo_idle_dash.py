"""Check requested idle changes, loop closure and subframe garment contacts."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
from pathlib import Path
import hashlib
import json
import sys
import bpy
import numpy as np

# ROOT (the archive) comes from _archive
ASSET=ROOT/'output/imagegen/yorimichi-yellow-boy-2026-09-12'
OUT=ASSET/'game-r02'
sys.path.insert(0, str(TOOLS))
from cairo_outfit_correctives import set_clip
from cairo_outfit_arm_clearance import ArmContactProbe
from cairo_waist_contact import WaistContactProbe
from prepare_cairo_game import action_signature


def protected(ignore_morphs=()):
    arm=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
    digest=hashlib.sha256()
    for o in sorted(bpy.context.scene.objects,key=lambda o:o.name):
        if o.type!='MESH':continue
        for array in ([v.co[:] for v in o.data.vertices],):digest.update(np.array(array,dtype=np.float32).tobytes())
        digest.update(json.dumps([[(g.group,g.weight) for g in v.groups] for v in o.data.vertices]).encode())
        if o.data.shape_keys:
            for key in o.data.shape_keys.key_blocks:
                if key.name not in ignore_morphs:digest.update(np.array([v.co[:] for v in key.data],dtype=np.float32).tobytes())
    digest.update(json.dumps([(b.name,b.parent.name if b.parent else None,[list(r) for r in b.matrix_local]) for b in arm.data.bones]).encode())
    digest.update(json.dumps([(d.data_path,d.array_index,d.driver.expression) for d in arm.animation_data.drivers]).encode())
    return digest.hexdigest()


def measurements(arm,frame):
    set_clip(arm,bpy.data.actions['Idle · library']);bpy.context.scene.frame_set(frame)
    return {key:abs((arm.pose.bones['mixamorig:Left'+bone].head-arm.pose.bones['mixamorig:Right'+bone].head).y)
        for key,bone in [('feet','Foot'),('hands','Hand')]}


def main():
    bpy.ops.wm.open_mainfile(filepath=str(ASSET/'game-r01/WarmOriginal-Game-r01.blend'))
    arm=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
    before=protected();old_actions=action_signature(bpy.data.actions);old_idle=measurements(arm,1)
    bpy.ops.wm.open_mainfile(filepath=str(OUT/'WarmOriginal-Game-r02.blend'))
    scene=bpy.context.scene;arm=next(o for o in scene.objects if o.type=='ARMATURE')
    new_idle=measurements(arm,1);actions=action_signature(bpy.data.actions)
    changes=['Idle · library','DashGround · library','DashAir · library']
    checks={'geometry_weights_morphs_rig_drivers_unchanged':before==protected(),
        'other_actions_unchanged':all(actions[k]==v for k,v in old_actions.items() if k not in changes),
        'idle_feet_wider':new_idle['feet']>old_idle['feet']*1.5,
        'idle_hands_closer':new_idle['hands']<old_idle['hands']-.04}
    set_clip(arm,bpy.data.actions[changes[0]]);scene.frame_set(1)
    first={p.name:p.matrix_basis.copy() for p in arm.pose.bones}
    scene.frame_set(241)
    loop_error=max(abs(p.matrix_basis[r][c]-first[p.name][r][c]) for p in arm.pose.bones for r in range(4) for c in range(4))
    checks['idle_loop_closed']=loop_error<1e-5
    shirt=next(o for o in scene.objects if o.get('outfit_slot')=='sweatshirt')
    shorts=next(o for o in scene.objects if o.get('outfit_slot')=='shorts')
    for o in scene.objects:
        if o.type=='MESH':o.hide_viewport=o not in [shirt,shorts]
    arm_probe,waist_probe=ArmContactProbe(shirt),WaistContactProbe(shirt,shorts)
    rows=[]
    for name in changes:
        action=bpy.data.actions[name];set_clip(arm,action)
        frames=range(1,242,8) if name.startswith('Idle') else np.arange(1,float(action.frame_range[1])+.01,.25)
        for frame in frames:
            scene.frame_set(int(frame),subframe=float(frame)%1)
            rows.append({'clip':name,'frame':float(frame),'arms':arm_probe.check(),'waist':waist_probe.check()})
        print('CONTACTS_CHECKED',name,flush=True)
    checks['arms_clear']=not any(any(r['arms'].values()) for r in rows)
    checks['waist_clear']=not any(r['waist']['shorts_faces'] for r in rows)
    report={'passed':all(checks.values()),'checks':checks,'idle_before':old_idle,'idle_after':new_idle,
        'idle_loop_matrix_error':loop_error,'contacts':rows,'native_sha256':hashlib.sha256((OUT/'WarmOriginal-Game-r02.blend').read_bytes()).hexdigest()}
    (OUT/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print('IDLE_DASH_VALIDATION',checks,flush=True)
    assert report['passed']


if __name__=='__main__':main()
