"""Preserve the approved mesh and materials while reviewing Tripo's body rig.

The raw provider GLB remains immutable. Transfer only its skeleton/weights to the
native approved mesh, then author diagnostic poses rather than final animations.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
from pathlib import Path
import bpy, json, math, sys
from mathutils import Vector, Matrix, Quaternion
from mathutils.kdtree import KDTree

ROOT=ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12'
OUT=ROOT/'tripo-rig-r01'; REVIEW=OUT/'blender'; REVIEW.mkdir(exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'tripo-cleanup-r02/WarmOriginal-Cleanup-r02.blend'))
scene=bpy.context.scene
body=next(o for o in scene.objects if o.type=='MESH')
original_positions=[v.co.copy() for v in body.data.vertices]
original_objects=set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(OUT/'raw/output_model_url.glb'))
imported=set(bpy.data.objects)-original_objects
arm=next(o for o in imported if o.type=='ARMATURE')
provider=next(o for o in imported if o.type=='MESH' and len(o.vertex_groups)>0)
source_points=[body.matrix_world@v.co for v in body.data.vertices]
rig_points=[provider.matrix_world@v.co for v in provider.data.vertices]
def bounds(points):
    return Vector([min(v[i] for v in points) for i in range(3)]),Vector([max(v[i] for v in points) for i in range(3)])
low,high=bounds(source_points);rlow,rhigh=bounds(rig_points)
scale=(rhigh.z-rlow.z)/(high.z-low.z)
offset=(rlow+rhigh)/2-(low+high)/2*scale
align=Matrix.Translation(offset)@Matrix.Scale(scale,4)
tree=KDTree(len(rig_points))
for i,p in enumerate(rig_points):tree.insert(p,i)
tree.balance()
for g in list(body.vertex_groups):body.vertex_groups.remove(g)
groups={g.index:body.vertex_groups.new(name=g.name) for g in provider.vertex_groups}
distances=[]
for v,p in zip(body.data.vertices,source_points):
    query=align@p;_,nearest,distance=tree.find(query);distances.append(distance)
    assert distance<2e-5,(v.index,distance)
    matches=tree.find_range(query,max(distance+1e-7,1e-6))
    weights={}
    for _,index,_ in matches:
        for g in provider.data.vertices[index].groups:weights[g.group]=weights.get(g.group,0)+g.weight/len(matches)
    top=sorted(weights.items(),key=lambda x:x[1],reverse=True)[:4];total=sum(w for _,w in top)
    assert total>.99,(v.index,total)
    for group,w in top:groups[group].add([v.index],w/total,'REPLACE')
arm.matrix_world=align.inverted()@arm.matrix_world
modifier=body.modifiers.new('Tripo skin weights','ARMATURE');modifier.object=arm
modifier.use_deform_preserve_volume=False
body_world=body.matrix_world.copy();body.parent=arm;body.matrix_world=body_world
arm.name='Cairo · Tripo body rig';arm.show_in_front=True;arm.data.display_type='OCTAHEDRAL'
for o in imported:
    if o!=arm:bpy.data.objects.remove(o,do_unlink=True)
# The importer supplies custom-shape helper objects; the review uses ordinary bones.
for b in arm.pose.bones:b.custom_shape=None
assert len(arm.data.bones)==23
assert all(v.co==p for v,p in zip(body.data.vertices,original_positions))
report={'source':'../raw/output_model_url.glb','approved_mesh':'../../tripo-cleanup-r02/WarmOriginal-Cleanup-r02.blend',
        'bones':len(arm.data.bones),'vertices':len(body.data.vertices),'triangles':sum(len(p.vertices)-2 for p in body.data.polygons),
        'native_mesh_and_materials_preserved':True,'max_weight_transfer_distance_in_provider_units':max(distances),
        'provider_alignment_scale':scale,'provider_alignment_offset':list(offset),
        'weight_source':'Tripo auto-rig; coincident UV-seam weights averaged and normalized',
        'individual_finger_bones':False,'facial_controls':False,'production_ik_controls':False,
        'user_approval':'pending'}

def reset():
    for p in arm.pose.bones:
        p.rotation_mode='QUATERNION';p.rotation_quaternion=Quaternion();p.location=(0,0,0);p.scale=(1,1,1)

def rotate(name,axis,degrees):
    p=arm.pose.bones['mixamorig:'+name]
    local_axis=p.bone.matrix_local.to_quaternion().inverted()@Vector(axis)
    p.rotation_quaternion=Quaternion(local_axis,math.radians(degrees))

def pose(kind,amount):
    reset()
    if kind=='shoulders':
        rotate('LeftArm',(1,0,0),-65*amount);rotate('RightArm',(1,0,0),65*amount)
    elif kind=='elbows':
        rotate('LeftForeArm',(0,0,1),-95*amount);rotate('RightForeArm',(0,0,1),95*amount)
        rotate('LeftHand',(0,0,1),-20*amount);rotate('RightHand',(0,0,1),20*amount)
    elif kind=='knees':
        rotate('LeftUpLeg',(0,1,0),-45*amount);rotate('RightUpLeg',(0,1,0),-45*amount)
        rotate('LeftLeg',(0,1,0),80*amount);rotate('RightLeg',(0,1,0),80*amount)
        rotate('LeftFoot',(0,1,0),-35*amount);rotate('RightFoot',(0,1,0),-35*amount)
    elif kind=='head':
        rotate('Head',(0,0,1),40*amount);rotate('Spine1',(0,0,1),15*amount)
    elif kind=='stride':
        rotate('LeftArm',(1,0,0),-65);rotate('RightArm',(1,0,0),65)
        rotate('LeftUpLeg',(0,1,0),-28*amount);rotate('RightUpLeg',(0,1,0),28*amount)
        rotate('LeftLeg',(0,1,0),40*max(0,-amount));rotate('RightLeg',(0,1,0),40*max(0,amount))
    bpy.context.view_layer.update()

# One action containing labelled tests supports Blender timeline and browser scrubbing.
labels=[('shoulders','Shoulders'),('elbows','Elbows and wrists'),('knees','Hips, knees and ankles'),('head','Head and torso'),('stride','Alternating legs')]
segments=[]
for index,(kind,label) in enumerate(labels):
    start=index*72+1
    for frame,amount in [(start,0),(start+18,1),(start+36,0),(start+54,-1 if kind in ('head','stride') else 1),(start+71,0)]:
        pose(kind,amount)
        for p in arm.pose.bones:
            p.keyframe_insert(data_path='rotation_quaternion',frame=frame,group=p.name)
    segments.append({'id':kind,'label':label,'start_frame':start,'end_frame':start+71,'peak_frame':start+18})
    scene.timeline_markers.new(label,frame=start)
arm.animation_data.action.name='Rig check · diagnostic poses'
scene.frame_start=1;scene.frame_end=360;scene.render.fps=24
report['diagnostic_segments']=segments
scene.frame_set(1)
bpy.context.view_layer.update()
evaluated=body.evaluated_get(bpy.context.evaluated_depsgraph_get())
report['rest_pose_max_vertex_error']=max((evaluated.data.vertices[i].co-original_positions[i]).length for i in range(len(original_positions)))
assert report['rest_pose_max_vertex_error']<2e-5
totals=[sum(g.weight for g in v.groups) for v in body.data.vertices]
report['unweighted_vertices']=sum(t<.999 for t in totals)
report['maximum_influences']=max(len(v.groups) for v in body.data.vertices)
assert report['unweighted_vertices']==0

cam=scene.camera;cam.data.ortho_scale=1.18;target=Vector((0,0,0))
cam.location=target+Vector((1,.65,.12)).normalized()*4
cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
scene.render.resolution_x=scene.render.resolution_y=800
scene.render.resolution_percentage=100
for name,frame in [('rest',1)]+[(s['id'],s['peak_frame']) for s in segments]:
    scene.frame_set(frame);scene.render.filepath=str(REVIEW/(name+'.png'));bpy.ops.render.render(write_still=True)
scene.frame_set(1)
bpy.ops.object.select_all(action='DESELECT');body.select_set(True);arm.select_set(True);bpy.context.view_layer.objects.active=arm
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D':
            s=area.spaces.active;s.shading.type='MATERIAL';s.overlay.show_extras=False
            s.overlay.show_floor=False;s.overlay.show_axis_x=s.overlay.show_axis_y=False
            s.region_3d.view_location=target;s.region_3d.view_distance=1.6
            s.region_3d.view_rotation=cam.rotation_euler.to_quaternion();s.clip_start=.01;s.clip_end=10
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(REVIEW/'WarmOriginal-Rig-r01.blend'))
bpy.ops.export_scene.gltf(filepath=str(REVIEW/'WarmOriginal-Rig-r01.glb'),export_format='GLB',use_selection=True,export_animations=True,export_frame_range=True,export_force_sampling=True)
(REVIEW/'review.json').write_text(json.dumps(report,indent=2)+'\n')
if '--render-reel' in sys.argv:
    frames=REVIEW/'deformation-frames';frames.mkdir(exist_ok=True)
    scene.render.resolution_x=scene.render.resolution_y=600
    for index,frame in enumerate(range(1,361,2)):
        scene.frame_set(frame);scene.render.filepath=str(frames/f'{index:04d}.png');bpy.ops.render.render(write_still=True)
print(json.dumps(report,indent=2))
