"""Retarget a locally downloaded Mixamo FBX to Cairo for a review test.

blender -b --python games/yorimichi/assets/characters/tools/cairo_mixamo_test.py -- --source FILE --out DIR
Raw Mixamo assets stay outside the published output. No video pose reconstruction
or rejected sword action is used. Source rest transforms are measured per import.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import argparse
import json
import math
import sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector, Quaternion

# ROOT (the archive) comes from _archive
HOLD = ROOT/'output/imagegen/yorimichi-yellow-boy-2026-09-12/sword-r01/stage1-bokken/hold-r14/WarmOriginal-SwordHold-r14.blend'
PREFIX = 'mixamorig:'


def anatomical_frame(arm):
    world = arm.matrix_world
    b = arm.data.bones
    left = (world @ b[PREFIX+'LeftArm'].head_local - world @ b[PREFIX+'RightArm'].head_local).normalized()
    up = (world @ b[PREFIX+'Neck'].head_local - world @ b[PREFIX+'Hips'].head_local).normalized()
    forward = left.cross(up).normalized()
    up = forward.cross(left).normalized()
    return Matrix((forward, left, up)).transposed()


def hand_frame(arm, side):
    b=arm.data.bones; world=arm.matrix_world
    wrist=world @ b[PREFIX+side+'Hand'].head_local
    index=world @ b[PREFIX+side+'HandIndex1'].head_local
    pinky=world @ b[PREFIX+side+'HandPinky1'].head_local
    y=((index+pinky)*.5-wrist).normalized()
    z=pinky-index;z=(z-y*z.dot(y)).normalized()
    x=y.cross(z).normalized()
    return Matrix((x,y,z)).transposed()


def fit_support_hand(arm, sword):
    """Solve contact with the captured elbow plane, never a sword-derived pole."""
    upper=arm.pose.bones[PREFIX+'LeftArm']; fore=arm.pose.bones[PREFIX+'LeftForeArm']; hand=arm.pose.bones[PREFIX+'LeftHand']
    W=arm.matrix_world; inv=W.inverted()
    shoulder=W@upper.head; elbow=W@fore.head; wrist=W@hand.head
    socket=Matrix.Translation((-.0167,.0724,-.068)) @ Matrix(((0,-1,0),(-1,0,0),(0,0,-1))).to_4x4()
    wanted=sword.matrix_world @ socket.inverted()
    goal=wanted.translation.copy(); reach=goal-shoulder
    l1=(elbow-shoulder).length;l2=(wrist-elbow).length
    d=reach.length;axis=reach.normalized()
    # Preserve the capture's elbow side; project that elbow onto the new plane.
    bend=elbow-shoulder; pole=(bend-axis*bend.dot(axis)).normalized()
    safe=max(abs(l1-l2)+.001,min(l1+l2-.001,d))
    along=(l1*l1-l2*l2+safe*safe)/(2*safe)
    height=math.sqrt(max(0,l1*l1-along*along))
    new_elbow=shoulder+axis*along+pole*height
    actual_goal=shoulder+axis*safe
    for bone,new_dir in [(upper,new_elbow-shoulder),(fore,actual_goal-new_elbow)]:
        old=(W@bone.matrix).copy()
        # The forearm inherited its parent's new pose; use its current axis.
        now_dir=(W@bone.tail)-(W@bone.head)
        swing=now_dir.normalized().rotation_difference(new_dir.normalized())
        desired=(swing.to_matrix() @ old.to_3x3()).to_4x4();desired.translation=W@bone.head
        bone.matrix=inv@desired
        bpy.context.view_layer.update()
    wanted.translation=W@hand.head
    hand.matrix=inv@wanted
    bpy.context.view_layer.update()
    return (W@hand.head-goal).length


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(sys.argv[sys.argv.index('--')+1:])
    out=args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(HOLD))
    scene=bpy.context.scene
    scene.frame_set(1)
    hero=next(o for o in scene.objects if o.type=='ARMATURE')
    sword=bpy.data.objects['Bokken-stage1-r01']
    socket=(hero.matrix_world @ hero.pose.bones[PREFIX+'RightHand'].matrix).inverted() @ sword.matrix_world
    finger={b.name:b.matrix_basis.copy() for b in hero.pose.bones if b.name.startswith(PREFIX+'RightHand') and b.name[-1].isdigit()}
    finger.update({n.replace('Right','Left'):m.copy() for n,m in list(finger.items())})
    hero.animation_data_clear()
    for bone in hero.pose.bones:
        bone.matrix_basis=Matrix.Identity(4)
    for obj in scene.objects:
        if obj.type=='MESH' and obj.data.shape_keys:
            obj.data.shape_keys.animation_data_clear()
            for key in obj.data.shape_keys.key_blocks:
                key.value=0
    old_objects=set(scene.objects)
    bpy.ops.import_scene.fbx(filepath=str(args.source.resolve()), automatic_bone_orientation=False)
    imported=set(scene.objects)-old_objects
    source=next(o for o in imported if o.type=='ARMATURE')
    action=source.animation_data.action
    fps=scene.render.fps/scene.render.fps_base
    first,last=map(round,action.frame_range)
    C=anatomical_frame(hero) @ anatomical_frame(source).inverted()
    hand_correction={PREFIX+side+'Hand':hand_frame(source,side) @ hand_frame(hero,side).inverted() for side in ['Left','Right']}
    S=source.matrix_world.copy(); T=hero.matrix_world.copy()
    Ti=T.to_quaternion().to_matrix()
    sr={b.name:(S @ b.matrix_local).to_quaternion().to_matrix() for b in source.data.bones}
    tr={b.name:(T @ b.matrix_local).to_quaternion().to_matrix() for b in hero.data.bones}
    sh=S @ source.data.bones[PREFIX+'Hips'].head_local
    th=T @ hero.data.bones[PREFIX+'Hips'].head_local
    source_floor=min((S @ source.data.bones[PREFIX+s+'ToeBase'].head_local).z for s in ['Left','Right'])
    target_floor=min((T @ hero.data.bones[PREFIX+s+'ToeBase'].head_local).z for s in ['Left','Right'])
    scale=(th.z-target_floor)/(sh.z-source_floor)
    names=[b.name for b in hero.data.bones if b.name in source.data.bones]
    missing=[b.name for b in hero.data.bones if b.name!='Root' and b.name not in source.data.bones]
    if missing: raise ValueError(f'Missing source bones: {missing}')
    # Extend only the lower grip to fit two of this character's hands.
    for v in sword.data.vertices:
        if v.co.z<.025:
            v.co.z-=.072 if v.co.z<=-.004 else .072*(.025-v.co.z)/.029
    new=bpy.data.actions.new('Mixamo · Great Sword Combo Slash')
    hero.animation_data_create(); hero.animation_data.action=new
    # Bone parenting uses the bone tail; compensate to retain the approved head-space socket.
    sword.parent=hero; sword.parent_type='BONE'; sword.parent_bone=PREFIX+'RightHand'
    sword.matrix_parent_inverse=Matrix.Identity(4)
    sword.matrix_basis=Matrix.Translation((0,-hero.data.bones[PREFIX+'RightHand'].length,0)) @ socket
    sword.animation_data_clear()
    old_q={}
    samples=[]
    support_errors=[]
    for f in range(first,last+1):
        scene.frame_set(f)
        for name in names:
            pb=hero.pose.bones[name]
            source_rotation=(S @ source.pose.bones[name].matrix).to_quaternion().to_matrix()
            desired_world=C @ source_rotation @ sr[name].inverted() @ hand_correction.get(name,C.inverted()) @ tr[name]
            desired=Ti.inverted() @ desired_world
            # Rotation-only retarget: target bone lengths and offsets remain intact.
            parent_pose=pb.parent.matrix.to_3x3().normalized() if pb.parent else Matrix.Identity(3)
            parent_rest=pb.parent.bone.matrix_local.to_3x3().normalized() if pb.parent else Matrix.Identity(3)
            rest_local=parent_rest.inverted() @ pb.bone.matrix_local.to_3x3().normalized()
            q=(rest_local.inverted() @ parent_pose.inverted() @ desired).to_quaternion().normalized()
            if name in old_q and q.dot(old_q[name])<0:q.negate()
            old_q[name]=q.copy()
            pb.rotation_mode='QUATERNION'; pb.rotation_quaternion=q; pb.location=(0,0,0); pb.scale=(1,1,1)
            if name==PREFIX+'Hips':
                desired_pos=th+C @ ((S @ source.pose.bones[name].head)-sh)*scale
                desired_local=T.inverted() @ desired_pos
                base=pb.parent.matrix @ pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local
                pb.location=base.inverted() @ desired_local
            if name in finger:pb.matrix_basis=finger[name]
            pb.keyframe_insert('rotation_quaternion',frame=f)
            if name==PREFIX+'Hips':pb.keyframe_insert('location',frame=f)
            bpy.context.view_layer.update()
        bpy.context.view_layer.update()
        support_errors.append(fit_support_hand(hero,sword))
        for name in ['LeftArm','LeftForeArm','LeftHand']:
            pb=hero.pose.bones[PREFIX+name]
            q=pb.rotation_quaternion
            if q.dot(old_q[pb.name])<0:q.negate()
            pb.rotation_quaternion=q;old_q[pb.name]=q.copy()
            pb.keyframe_insert('rotation_quaternion',frame=f)
        if f%10==1 or f==last:
            samples.append({'frame':f,'right_hand':list(T @ hero.pose.bones[PREFIX+'RightHand'].head),
                            'left_hand':list(T @ hero.pose.bones[PREFIX+'LeftHand'].head)})
    for layer in new.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fc in bag.fcurves:
                    for key in fc.keyframe_points:key.interpolation='LINEAR'
    # Keep source data in a separate local-only scene for rendered comparisons.
    for obj in imported:obj.hide_render=True;obj.hide_set(True)
    scene.frame_start=first;scene.frame_end=last;scene.frame_set(first)
    report={'source':args.source.name,'source_sha256':__import__('hashlib').sha256(args.source.read_bytes()).hexdigest(),
            'fps':fps,'first':first,'last':last,'duration':(last-first)/fps,'root_scale':scale,
            'alignment':[list(r) for r in C],'mapped_bones':names,'missing':missing,'samples':samples,
            'support_hand_error_max_m':max(support_errors),'support_hand_error_mean_m':sum(support_errors)/len(support_errors),
            'status':'Mocap test with anatomical hand mapping and support-hand fitting; pending visual review.'}
    (out/'retarget.json').write_text(json.dumps(report,indent=2)+'\n')
    bpy.ops.wm.save_as_mainfile(filepath=str((yori.OUT / 'mixamo-sword-test/working.blend').resolve()))
    for obj in imported:bpy.data.objects.remove(obj,do_unlink=True)
    for a in list(bpy.data.actions):
        if a!=new:bpy.data.actions.remove(a)
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'WarmOriginal-Mixamo-Slash.blend'))
    print('RETARGET',json.dumps({k:report[k] for k in ['fps','first','last','duration','root_scale','status']}),flush=True)

if __name__=='__main__':main()
