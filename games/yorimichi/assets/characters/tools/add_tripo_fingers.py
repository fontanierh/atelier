"""Add articulated fingers and hand controls without replacing Tripo's body rig."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # Blender's --python does not add the script's folder
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import bpy,json,math,sys
from pathlib import Path
from mathutils import Vector,Quaternion

ROOT=ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12'
OUT=ROOT/'tripo-rig-r02';REVIEW=OUT/'blender';REVIEW.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'tripo-rig-r01/blender/WarmOriginal-Rig-r01.blend'))
scene=bpy.context.scene;scene.frame_set(1)
arm=next(o for o in scene.objects if o.type=='ARMATURE')
body=next(o for o in scene.objects if o.type=='MESH' and o.vertex_groups)
before_positions=[v.co.copy() for v in body.data.vertices]
before_weights=[[(g.group,g.weight) for g in v.groups] for v in body.data.vertices]
before_bones={b.name:b.matrix_local.copy() for b in arm.data.bones}
# Joint centers fitted to both approved hands in world coordinates. The base mesh
# is nearly mirrored; each phalanx follows its observed centerline and curvature.
landmarks={
 'Thumb':[(.021,.379,.149),(.021,.391,.164),(.023,.401,.178),(.023,.403,.188)],
 'Index':[(.003,.408,.151),(.007,.430,.153),(.012,.445,.153),(.014,.455,.153)],
 'Middle':[(-.001,.410,.135),(.002,.435,.136),(.010,.454,.136),(.013,.465,.136)],
 'Ring':[(.003,.411,.118),(.006,.434,.120),(.011,.451,.1195),(.013,.462,.119)],
 'Pinky':[(.006,.408,.108),(.009,.426,.1045),(.0115,.438,.102),(.013,.447,.101)]}
bpy.ops.object.select_all(action='DESELECT');arm.select_set(True);bpy.context.view_layer.objects.active=arm
bpy.ops.object.mode_set(mode='EDIT')
chains={};inverse=arm.matrix_world.inverted()
for side,sign in [('Left',1),('Right',-1)]:
 for finger,points in landmarks.items():
  world=[Vector((x,sign*y,z)) for x,y,z in points];names=[]
  for index in range(3):
   name=f'mixamorig:{side}Hand{finger}{index+1}'
   bone=arm.data.edit_bones.new(name);bone.head=inverse@world[index];bone.tail=inverse@world[index+1]
   bone.parent=arm.data.edit_bones[names[-1] if names else f'mixamorig:{side}Hand']
   bone.use_connect=index>0;bone.align_roll(inverse.to_3x3()@Vector((1,0,0)));names.append(name)
  chains[(side,finger)]={'points':world,'bones':names}
bpy.ops.object.mode_set(mode='OBJECT')
for name,matrix in before_bones.items():
 assert max(abs(arm.data.bones[name].matrix_local[i][j]-matrix[i][j]) for i in range(4) for j in range(4))<1e-6

def smooth(value):
 t=max(0,min(1,value));return t*t*(3-2*t)

def along_chain(point,chain):
 points=chain['points'];lengths=[(b-a).length for a,b in zip(points,points[1:])]
 best=None;offset=0
 for index,(a,b,length) in enumerate(zip(points,points[1:],lengths)):
  t=(point-a).dot(b-a)/(length*length);nearest=a+(b-a)*max(0,min(1,t))
  distance=(point-nearest).length
  # Extend the proximal segment into the palm for a smooth hand-to-finger blend.
  s=offset+length*(t if index==0 and t<0 else max(0,min(1,t)))
  if best is None or distance<best[0]:best=(distance,s)
  offset+=length
 return best,lengths

groups={name:body.vertex_groups.new(name=name) for c in chains.values() for name in c['bones']}
changed=[];assigned={f'{side}{finger}':0 for side,finger in chains}
for v in body.data.vertices:
 p=body.matrix_world@v.co
 if abs(p.y)<.372:continue
 side='Left' if p.y>0 else 'Right';hand=body.vertex_groups[f'mixamorig:{side}Hand']
 candidates=[]
 for (s,finger),chain in chains.items():
  if s==side:
   (distance,arc),lengths=along_chain(p,chain);candidates.append((distance,finger,arc,lengths,chain))
 distance,finger,arc,lengths,chain=min(candidates,key=lambda item:item[0])
 band=.006 if finger!='Thumb' else .008
 amount=smooth((arc+band)/(2*band))
 if amount<1e-5:continue
 # Blend only adjacent phalanges, avoiding unrelated fingers pulling one another.
 one=smooth((arc-lengths[0]+.004)/.008)
 two=smooth((arc-lengths[0]-lengths[1]+.0035)/.007)
 weights={chain['bones'][0]:amount*(1-one),chain['bones'][1]:amount*one*(1-two),chain['bones'][2]:amount*one*two,hand.name:1-amount}
 for group in [g.group for g in v.groups]:body.vertex_groups[group].remove([v.index])
 for name,weight in weights.items():
  if weight>1e-7:body.vertex_groups[name].add([v.index],weight,'REPLACE')
 changed.append(v.index);assigned[side+finger]+=1
changed_set=set(changed)
# Relax transitions over actual mesh neighbors, especially the thumb webbing.
# Finger gaps have no connecting edges, so this cannot bleed across separate tips.
neighbors=[set() for _ in body.data.vertices]
for edge in body.data.edges:
 a,b=edge.vertices;neighbors[a].add(b);neighbors[b].add(a)
for _ in range(3):
 current=[{g.group:g.weight for g in v.groups} for v in body.data.vertices];updates={}
 for index in changed:
  adjacent=neighbors[index]
  if not adjacent:continue
  combined={g:w*.65 for g,w in current[index].items()}
  for other in adjacent:
   for group,weight in current[other].items():combined[group]=combined.get(group,0)+.35*weight/len(adjacent)
  chosen=sorted(combined.items(),key=lambda item:item[1],reverse=True)[:4];total=sum(w for _,w in chosen)
  updates[index]=[(g,w/total) for g,w in chosen if w/total>1e-7]
 for index,weights in updates.items():
  for group in [g.group for g in body.data.vertices[index].groups]:body.vertex_groups[group].remove([index])
  for group,weight in weights:body.vertex_groups[group].add([index],weight,'REPLACE')
assert all([(g.group,g.weight) for g in v.groups]==before_weights[v.index] for v in body.data.vertices if v.index not in changed_set)
assert all(v.co==p for v,p in zip(body.data.vertices,before_positions))

for side,sign in [('Left',1),('Right',-1)]:
 hand=arm.pose.bones[f'mixamorig:{side}Hand']
 for prop in [f.lower()+'_curl' for f in landmarks]+['thumb_opposition','finger_spread']:
  hand[prop]=0.0;hand.id_properties_ui(prop).update(min=-1.0 if prop=='finger_spread' else 0.0,max=1.0,description=prop.replace('_',' ').capitalize())
 for finger in landmarks:
  for index,name in enumerate(chains[(side,finger)]['bones']):
   pb=arm.pose.bones[name];pb.rotation_mode='XYZ'
   fc=pb.driver_add('rotation_euler',0);d=fc.driver;d.type='SCRIPTED'
   var=d.variables.new();var.name='curl';var.targets[0].id=arm;var.targets[0].data_path=f'pose.bones["{hand.name}"]["{finger.lower()}_curl"]'
   angles=[35,50,65] if finger=='Thumb' else [85,100,55]
   d.expression=f'max(0,min(1,curl))*{math.radians(angles[index])}'
   if index==0:
    fc=pb.driver_add('rotation_euler',2);d=fc.driver;var=d.variables.new();var.targets[0].id=arm
    if finger=='Thumb':
     var.name='opposition';var.targets[0].data_path=f'pose.bones["{hand.name}"]["thumb_opposition"]';d.expression=f'-{sign}*max(0,min(1,opposition))*1.45'
    else:
     var.name='spread';var.targets[0].data_path=f'pose.bones["{hand.name}"]["finger_spread"]';d.expression=f'{sign}*spread*'+str({'Index':.14,'Middle':.02,'Ring':-.05,'Pinky':-.17}[finger])

hands=[arm.pose.bones[f'mixamorig:{side}Hand'] for side in ('Left','Right')]
properties=[f.lower()+'_curl' for f in landmarks]+['thumb_opposition','finger_spread']
def hand_keys(frame,values):
 for hand in hands:
  for prop in properties:
   hand[prop]=values.get(prop,0.0);hand.keyframe_insert(data_path=f'["{prop}"]',frame=frame,group=hand.name+' · finger controls')
hand_keys(1,{});hand_keys(360,{})
# Return the body to T-pose during hand tests, retaining all original body tests.
for frame in [361,816]:
 for name in before_bones:
  pb=arm.pose.bones[name];pb.rotation_quaternion=Quaternion();pb.keyframe_insert(data_path='rotation_quaternion',frame=frame,group=name)
fist={f.lower()+'_curl':1.0 for f in landmarks};fist['thumb_opposition']=1.0;fist['thumb_curl']=.35;fist['finger_spread']=-.3
grip={f.lower()+'_curl':.63 for f in landmarks};grip['thumb_opposition']=.7;grip['thumb_curl']=.35
for start,values in [(361,fist),(433,grip)]:
 for offset,v in [(0,{}),(24,values),(48,values),(71,{})]:hand_keys(start+offset,v)
for index,finger in enumerate(landmarks):
 start=505+index*48;values={finger.lower()+'_curl':.85}
 if finger=='Thumb':values['thumb_opposition']=.65
 for offset,v in [(0,{}),(16,values),(32,values),(47,{})]:hand_keys(start+offset,v)
pinch={'thumb_opposition':1.0,'thumb_curl':.45,'index_curl':.6,'middle_curl':.15,'ring_curl':.15,'pinky_curl':.15}
for offset,v in [(0,{}),(24,pinch),(48,pinch),(71,{})]:hand_keys(745+offset,v)
segments=[{'id':'fist','label':'Open to fist','start_frame':361,'end_frame':432,'peak_frame':385},
 {'id':'grip','label':'Power grip','start_frame':433,'end_frame':504,'peak_frame':457},
 {'id':'fingers','label':'Individual fingers','start_frame':505,'end_frame':744,'peak_frame':521},
 {'id':'pinch','label':'Thumb opposition','start_frame':745,'end_frame':816,'peak_frame':769}]
for s in segments:scene.timeline_markers.new(s['label'],frame=s['start_frame'])
scene.frame_end=816;arm.animation_data.action.name='Body and finger deformation checks';arm.name='Cairo · Tripo body with articulated fingers'
scene.frame_set(1);bpy.context.view_layer.update()
ev=body.evaluated_get(bpy.context.evaluated_depsgraph_get())
rest_error=max((ev.data.vertices[i].co-before_positions[i]).length for i in range(len(before_positions)))
assert rest_error<2e-5
report={'source':'../../tripo-rig-r01/blender/WarmOriginal-Rig-r01.blend','tripo_body_bones_retained':23,'added_finger_bones':30,'total_bones':len(arm.data.bones),
 'finger_chains':{side+finger:{'bones':c['bones'],'world_joint_centers':[list(p) for p in c['points']]} for (side,finger),c in chains.items()},
 'hand_controls':properties,'reweighted_hand_vertices':len(changed),'vertices_per_chain':assigned,'unmodified_body_weights':True,'mesh_and_materials_unchanged':True,
 'rest_pose_max_vertex_error':rest_error,'max_weights':max(len(v.groups) for v in body.data.vertices),'unweighted_vertices':sum(sum(g.weight for g in v.groups)<.999 for v in body.data.vertices),
 'diagnostic_segments':json.loads((ROOT/'tripo-rig-r01/blender/review.json').read_text())['diagnostic_segments']+segments,'user_approval':'pending','additional_tripo_credits':0}
assert report['total_bones']==53 and report['max_weights']<=4 and report['unweighted_vertices']==0,{k:v for k,v in report.items() if k!='finger_chains'}
cam=scene.camera;scene.render.resolution_x=scene.render.resolution_y=800
for side,sign in [('left',1),('right',-1)]:
 target=Vector((.02,sign*.414,.14));cam.data.ortho_scale=.155
 cam.location=target+Vector((1,-sign*.2,.12))*.6;cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
 for label,frame in [('open',1),('fist',385),('grip',457),('thumb',769)]:
  scene.frame_set(frame);scene.render.filepath=str(REVIEW/f'{side}-{label}.png');bpy.ops.render.render(write_still=True)
scene.frame_set(1);cam.data.ortho_scale=1.18;cam.location=Vector((1,.65,.12)).normalized()*4;cam.rotation_euler=(-cam.location).to_track_quat('-Z','Y').to_euler()
scene.render.filepath=str(REVIEW/'rest.png');bpy.ops.render.render(write_still=True)
bpy.ops.object.select_all(action='DESELECT');arm.select_set(True);body.select_set(True);bpy.context.view_layer.objects.active=arm
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(REVIEW/'WarmOriginal-Rig-r02.blend'))
bpy.ops.export_scene.gltf(filepath=str(REVIEW/'WarmOriginal-Rig-r02.glb'),export_format='GLB',use_selection=True,export_animations=True,export_frame_range=True,export_force_sampling=True)
(REVIEW/'review.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='finger_chains'},indent=2))
