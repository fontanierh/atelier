"""Check head clearance, grip contact and unchanged body motion on the saved clip.

Sample at 240 Hz (four samples per source frame), including interpolated poses.
BVH mesh overlap is a sampled geometric check, not continuous collision proof.
"""
import argparse,json,math,sys
from pathlib import Path
import bpy
from mathutils import Matrix
from mathutils.bvhtree import BVHTree
sys.path.insert(0,str(Path(__file__).parent))
from _archive import ROOT  # noqa: E402  (ROOT: the prototype archive holding the revision history)
# ROOT (the archive) comes from _archive
BASE=ROOT/'output/imagegen/yorimichi-yellow-boy-2026-09-12/sword-r01/stage1-bokken'
P='mixamorig:'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=BASE/'mixamo-r02')
    p.add_argument('--baseline',type=Path,default=BASE/'mixamo-r01/WarmOriginal-Mixamo-Slash.blend',
                   help='the retarget before the clearance pass (cairo_mixamo_test.py output)')
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    out=args.out.resolve();cache={};baseline_grip={}
    changed={P+side+part for side in ['Right','Left'] for part in ['Arm','ForeArm','Hand']}
    bpy.ops.wm.open_mainfile(filepath=str(args.baseline.resolve()))
    a=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
    socket=Matrix.Translation((-.0167,.0724,-.068))@Matrix(((0,-1,0),(-1,0,0),(0,0,-1))).to_4x4()
    sword=bpy.data.objects['Bokken-stage1-r01']
    for i in range(845):
        f=1+i/4;bpy.context.scene.frame_set(math.floor(f),subframe=f%1)
        baseline_grip[f]=(a.matrix_world@a.pose.bones[P+'LeftHand'].head-(sword.matrix_world@socket.inverted()).translation).length
        if f==int(f):cache[int(f)]={b.name:b.matrix_basis.copy() for b in a.pose.bones if b.name not in changed}
    bpy.ops.wm.open_mainfile(filepath=str(out/'WarmOriginal-Mixamo-Slash.blend'))
    scene=bpy.context.scene;a=next(o for o in scene.objects if o.type=='ARMATURE')
    head=bpy.data.objects['Body · head'];sword=bpy.data.objects['Bokken-stage1-r01']
    verts=[v.co.copy() for v in sword.data.vertices];full_faces=[list(p.vertices) for p in sword.data.polygons]
    blade_faces=[p for p in full_faces if min(verts[i].z for i in p)>.11]
    blade_indices=sorted({i for p in blade_faces for i in p})
    socket=Matrix.Translation((-.0167,.0724,-.068))@Matrix(((0,-1,0),(-1,0,0),(0,0,-1))).to_4x4()
    hits=[];blade_hits=[];margin_hits=[];grip_max=[0,0];grip_key_max=0;basis_error=0;distance_min=[1000,0]
    grip_increase=[0,0];previous={};steps={name:[0,0] for name in sorted(changed)}
    for i in range(845):
        f=1+i/4;scene.frame_set(math.floor(f),subframe=f%1)
        ev=head.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
        hv=[ev.matrix_world@v.co for v in mesh.vertices];hf=[list(p.vertices) for p in mesh.polygons];ev.to_mesh_clear()
        tree=BVHTree.FromPolygons(hv,hf);margin=BVHTree.FromPolygons(hv,hf,epsilon=.004)
        sv=[sword.matrix_world@v for v in verts];blade=BVHTree.FromPolygons(sv,blade_faces);full=BVHTree.FromPolygons(sv,full_faces)
        if tree.overlap(blade):blade_hits.append(f)
        if tree.overlap(full):hits.append(f)
        if margin.overlap(blade):margin_hits.append(f)
        distance=min(tree.find_nearest(sv[j])[-1] for j in blade_indices)
        if distance<distance_min[0]:distance_min=[distance,f]
        goal=(sword.matrix_world@socket.inverted()).translation
        error=(a.matrix_world@a.pose.bones[P+'LeftHand'].head-goal).length
        if error>grip_max[0]:grip_max=[error,f]
        if error-baseline_grip[f]>grip_increase[0]:grip_increase=[error-baseline_grip[f],f]
        if f==int(f):
            grip_key_max=max(grip_key_max,error)
            for n,M in cache[int(f)].items():
                N=a.pose.bones[n].matrix_basis
                basis_error=max(basis_error,max(abs(M[r][c]-N[r][c]) for r in range(4) for c in range(4)))
            for n in sorted(changed):
                q=a.pose.bones[n].matrix.to_quaternion()
                if n in previous:
                    degrees=math.degrees(q.rotation_difference(previous[n]).angle);degrees=min(degrees,360-degrees)
                    if degrees>steps[n][0]:steps[n]=[degrees,f]
                previous[n]=q.copy()
    report={'sample_rate_hz':240,'sample_count':845,'frames':[1,212],
            'blade_head_overlap_samples':blade_hits,'whole_sword_head_overlap_samples':hits,
            'blade_head_4mm_bvh_margin_overlap_samples':margin_hits,
            'blade_vertex_to_head_min_distance_m_and_frame':distance_min,
            'support_grip_max_error_m_and_frame':grip_max,'support_grip_keyframe_max_error_m':grip_key_max,
            'baseline_support_grip_max_error_m':max(baseline_grip.values()),'support_grip_error_increase_m_and_frame':grip_increase,
            'unchanged_bone_local_transform_max_abs_error':basis_error,'max_keyframe_world_rotation_step_degrees_and_frame':steps,
            'scope':'Evaluated head mesh (skin and hair) vs blade / whole sword mesh. 4mm BVH margin and blade-vertex distance are extra sampled checks, not exhaustive continuous distance or whole-body clearance proofs.'}
    (out/'clearance-checks.json').write_text(json.dumps(report,indent=2)+'\n')
    print('CLEARANCE_CHECKS',json.dumps(report),flush=True)
    if blade_hits or hits:raise ValueError('Weapon intersects head in sampled poses')
    if basis_error>1e-5:raise ValueError('Bones outside the six intended arm/hand edits changed')
    if grip_increase[0]>.004:raise ValueError('Support grip drifts more than 4mm beyond the baseline')

if __name__=='__main__':main()
