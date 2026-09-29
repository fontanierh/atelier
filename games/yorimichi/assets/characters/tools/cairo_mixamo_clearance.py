"""Adapt the Mixamo test's high cuts to the larger head without changing timing.

Run after cairo_mixamo_test.py. Source poses remain in mixamo-r01; this layer only
keys both arms/hands in mixamo-r02. Keep the original captured elbow planes and
solve the support hand from the same rigid sword socket.
"""
import argparse
import json
import math
import sys
from pathlib import Path
import bpy
from mathutils import Matrix, Quaternion, Vector
sys.path.insert(0,str(Path(__file__).parent))
from _archive import ROOT  # noqa: E402  (ROOT: the prototype archive holding the revision history)
from cairo_mixamo_test import PREFIX, fit_support_hand

# ROOT (the archive) comes from _archive
BASE=ROOT/'output/imagegen/yorimichi-yellow-boy-2026-09-12/sword-r01/stage1-bokken'


def curve(frame, points):
    for (start,a),(end,b) in zip(points,points[1:]):
        if start<=frame<=end:
            t=(frame-start)/(end-start)
            t=t*t*(3-2*t)
            return a+(b-a)*t
    return 0.0


def move_wrist(arm, goal, rotation):
    """Reach a nearby wrist goal, preserving captured bend side and bone lengths."""
    upper,fore,hand=[arm.pose.bones[PREFIX+'Right'+part] for part in ['Arm','ForeArm','Hand']]
    W=arm.matrix_world;inv=W.inverted();old_hand=W@hand.matrix
    s,e,w=[W@bone.head for bone in [upper,fore,hand]]
    l1=(e-s).length;l2=(w-e).length;axis=(goal-s).normalized()
    d=min(l1+l2-.001,max(abs(l1-l2)+.001,(goal-s).length))
    bend=e-s;pole=(bend-axis*bend.dot(axis)).normalized()
    along=(l1*l1-l2*l2+d*d)/(2*d)
    elbow=s+axis*along+pole*math.sqrt(max(0,l1*l1-along*along))
    actual=s+axis*d
    for bone,direction in [(upper,elbow-s),(fore,actual-elbow)]:
        before=W@bone.matrix
        swing=((W@bone.tail)-(W@bone.head)).normalized().rotation_difference(direction.normalized())
        desired=(swing.to_matrix()@before.to_3x3()).to_4x4();desired.translation=W@bone.head
        bone.matrix=inv@desired;bpy.context.view_layer.update()
    desired=(rotation.to_matrix()@old_hand.to_3x3()).to_4x4();desired.translation=W@hand.head
    hand.matrix=inv@desired;bpy.context.view_layer.update()
    return (W@hand.head-goal).length


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=BASE/'mixamo-r01/WarmOriginal-Mixamo-Slash.blend')
    p.add_argument('--out',type=Path,default=BASE/'mixamo-r02')
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(args.source.resolve()))
    scene=bpy.context.scene;arm=next(o for o in scene.objects if o.type=='ARMATURE')
    head=bpy.data.objects['Body · head'];sword=bpy.data.objects['Bokken-stage1-r01']
    previous={};samples=[]
    for frame in range(1,213):
        scene.frame_set(frame)
        # Lift the blade through a broader overhead arc; blend in before contact.
        angle=curve(frame,[(35,0),(41,28),(45,28),(51,0)])
        angle+=curve(frame,[(125,0),(133,36),(142,36),(150,0)])
        angle+=curve(frame,[(166,0),(174,30),(180,32),(184,64),(187,64),(193,42),(204,0)])
        shift=curve(frame,[(125,0),(133,.025),(142,.025),(150,0)])
        shift+=curve(frame,[(166,0),(174,.04),(189,.04),(193,.025),(204,0)])
        if angle or shift:
            W=arm.matrix_world;w=W@arm.pose.bones[PREFIX+'RightHand'].head
            ev=head.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
            centre=sum((ev.matrix_world@v.co for v in mesh.vertices),Vector())/len(mesh.vertices);ev.to_mesh_clear()
            offset=(w-centre).normalized()*shift
            blade=(sword.matrix_world.to_3x3()@Vector((0,0,1))).normalized()
            axis=blade.cross(Vector((0,0,1))).normalized()
            right_error=move_wrist(arm,w+offset,Quaternion(axis,math.radians(angle)))
            left_error=fit_support_hand(arm,sword)
            samples.append({'frame':frame,'blade_lift_degrees':angle,'wrist_offset_m':shift,
                            'right_reach_error_m':right_error,'support_reach_error_m':left_error})
        for side in ['Right','Left']:
            for part in ['Arm','ForeArm','Hand']:
                pb=arm.pose.bones[PREFIX+side+part];q=pb.rotation_quaternion.copy()
                if pb.name in previous and q.dot(previous[pb.name])<0:q.negate()
                previous[pb.name]=q.copy();pb.rotation_quaternion=q
                pb.keyframe_insert('rotation_quaternion',frame=frame)
    scene.frame_set(1)
    arm.animation_data.action.name='Mixamo · Great Sword Combo Slash · head clearance'
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'WarmOriginal-Mixamo-Slash.blend'))
    source=args.source.resolve()
    report={'source':str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else source.name, 'changed_bones':[PREFIX+side+part for side in ['Right','Left'] for part in ['Arm','ForeArm','Hand']],
            'samples':samples,'max_right_reach_error_m':max(x['right_reach_error_m'] for x in samples),
            'max_support_reach_error_m':max(x['support_reach_error_m'] for x in samples)}
    (out/'clearance-fit.json').write_text(json.dumps(report,indent=2)+'\n')
    print('CLEARANCE_FIT',report['max_right_reach_error_m'],report['max_support_reach_error_m'],flush=True)

if __name__=='__main__':main()
