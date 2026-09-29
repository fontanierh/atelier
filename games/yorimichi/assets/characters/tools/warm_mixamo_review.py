"""Export the current Mixamo test and render source/target review videos.
Run in Blender after warm_mixamo_test.py. Source FBX/working blend stay local.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import argparse,json,math,struct,subprocess
from pathlib import Path
import bpy
from mathutils import Vector,Matrix
from mathutils.bvhtree import BVHTree
# ROOT (the archive) comes from _archive
OUT=ROOT/'output/imagegen/yorimichi-yellow-boy-2026-09-12/sword-r01/stage1-bokken/mixamo-r01'
WORK=yori.OUT / 'mixamo-sword-test'


def load_source():
    bpy.ops.wm.read_factory_settings(use_empty=False)
    bpy.ops.import_scene.fbx(filepath=str(WORK/'source/great-sword-combo-slash.fbx'),automatic_bone_orientation=False)


def export(source=None, stem="slash", load=True):
    if load:bpy.ops.wm.open_mainfile(filepath=str(source or OUT/'WarmOriginal-Mixamo-Slash.blend'))
    s=bpy.context.scene
    for o in s.objects:o.select_set(o.type in ['MESH','ARMATURE'] and not o.hide_render and not o.name.startswith('Review floor'))
    web=OUT/'web';web.mkdir(exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(web/(stem+'.gltf')),export_format='GLTF_SEPARATE',use_selection=True,
        export_animations=True,export_animation_mode='ACTIONS',export_frame_range=False,export_apply=True,
        export_skins=True,export_materials='EXPORT',export_image_format='JPEG',export_jpeg_quality=85)
    doc=json.loads((web/(stem+'.gltf')).read_text());binary=web/doc['buffers'][0].pop('uri');data=bytearray(binary.read_bytes())
    for anim in doc['animations']:
        inputs={x['input'] for x in anim['samplers']};start=min(doc['accessors'][i]['min'][0] for i in inputs)
        for i in inputs:
            a=doc['accessors'][i];v=doc['bufferViews'][a['bufferView']];offset=v.get('byteOffset',0)+a.get('byteOffset',0);stride=v.get('byteStride',4)
            for j in range(a['count']):
                t=struct.unpack_from('<f',data,offset+j*stride)[0];struct.pack_into('<f',data,offset+j*stride,t-start)
            a['min'][0]-=start;a['max'][0]-=start
    js=json.dumps(doc).encode();js+=b' '*(-len(js)%4);data+=b'\0'*(-len(data)%4)
    (web/(stem+'.glb')).write_bytes(b'glTF'+struct.pack('<II',2,28+len(js)+len(data))+struct.pack('<I',len(js))+b'JSON'+js+struct.pack('<I',len(data))+b'BIN\0'+data)
    (web/(stem+'.gltf')).unlink();binary.unlink()


def render(kind):
    source=kind=='source'
    if source:load_source()
    else:bpy.ops.wm.open_mainfile(filepath=str((OUT.parent/'mixamo-r01' if kind=='before' else OUT)/'WarmOriginal-Mixamo-Slash.blend'))
    s=bpy.context.scene;a=next(o for o in s.objects if o.type=='ARMATURE')
    if source:
        bpy.data.objects.remove(bpy.data.objects['Cube'],do_unlink=True)
        a.matrix_world=Matrix.Rotation(math.pi/2,4,'Z') @ Matrix.Scale(.53,4) @ a.matrix_world;a.location.z=-.5
        s.world.color=(.35,.35,.35)
        for o in s.objects:
            if o.type=='LIGHT':o.data.energy=600;o.location=(2,-2,4)
    for o in s.objects:
        if o.name.startswith('Review floor'):o.hide_render=True
    bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.511))
    floor=bpy.context.object;mat=bpy.data.materials.new('Review floor');mat.diffuse_color=(.32,.32,.32,1);floor.data.materials.append(mat)
    s.render.engine='BLENDER_EEVEE';s.eevee.taa_render_samples=12;s.render.resolution_x=s.render.resolution_y=512;s.render.resolution_percentage=100;s.view_settings.view_transform='Standard'
    cam=s.camera;cam.data.type='ORTHO';cam.data.ortho_scale=1.8
    folder=WORK/(kind+'-video-frames');folder.mkdir(exist_ok=True)
    frames=list(range(1,213,2))
    for i,f in enumerate(frames):
        s.frame_set(f);target=a.matrix_world@a.pose.bones['mixamorig:Hips'].head;target.z=.12
        di=Vector((1,-1,.2)).normalized();cam.location=target+di*4;cam.rotation_euler=(-di).to_track_quat('-Z','Y').to_euler()
        s.render.filepath=str(folder/f'{i:04d}.png');bpy.ops.render.render(write_still=True)
    subprocess.run(['ffmpeg','-y','-loglevel','error','-framerate','30','-i',str(folder/'%04d.png'),'-c:v','libx264','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(OUT/(kind+'.mp4'))],check=True)

def check():
    names=['RightArm','RightForeArm','RightHand','LeftArm','LeftForeArm','LeftHand']
    reports={}
    for kind,path in [('source',WORK/'source.blend'),('target',OUT/'WarmOriginal-Mixamo-Slash.blend')]:
        if kind=='source':load_source()
        else:bpy.ops.wm.open_mainfile(filepath=str(path))
        scene=bpy.context.scene
        arm=next(o for o in scene.objects if o.type=='ARMATURE')
        previous={};changes={n:(0,0) for n in names};floors=[]
        for frame in range(1,213):
            scene.frame_set(frame)
            for n in names:
                q=arm.pose.bones['mixamorig:'+n].matrix.to_quaternion()
                if n in previous:
                    degrees=math.degrees(q.rotation_difference(previous[n]).angle)
                    degrees=min(degrees,360-degrees)
                    if degrees>changes[n][0]:changes[n]=(round(degrees,3),frame)
                previous[n]=q.copy()
            if kind=='target' and frame%10==1:
                zs=[];dg=bpy.context.evaluated_depsgraph_get()
                for obj in scene.objects:
                    if obj.type!='MESH' or obj.hide_render or obj.name.startswith(('Review floor','Bokken')):continue
                    ev=obj.evaluated_get(dg);mesh=ev.to_mesh()
                    zs.extend((ev.matrix_world@v.co).z for v in mesh.vertices);ev.to_mesh_clear()
                floors.append((frame,round(min(zs),4)))
        reports[kind]={'max_frame_rotation_degrees':changes}
        if floors:reports[kind]['sampled_geometry_floor']=floors
    (OUT/'checks.json').write_text(json.dumps(reports,indent=2)+'\n')
    print('CHECKS',json.dumps(reports),flush=True)

def check_head():
    bpy.ops.wm.open_mainfile(filepath=str(OUT/'WarmOriginal-Mixamo-Slash.blend'))
    scene=bpy.context.scene;head=bpy.data.objects['Body · head'];sword=bpy.data.objects['Bokken-stage1-r01']
    faces=[list(p.vertices) for p in sword.data.polygons if min(sword.data.vertices[i].co.z for i in p.vertices)>.11]
    hits=[]
    for frame in range(1,213):
        scene.frame_set(frame);dg=bpy.context.evaluated_depsgraph_get();ev=head.evaluated_get(dg);mesh=ev.to_mesh()
        tree=BVHTree.FromPolygons([ev.matrix_world@v.co for v in mesh.vertices],[list(p.vertices) for p in mesh.polygons]);ev.to_mesh_clear()
        blade=BVHTree.FromPolygons([sword.matrix_world@v.co for v in sword.data.vertices],faces)
        overlap=tree.overlap(blade)
        if overlap:hits.append([frame,len(overlap)])
    (OUT/'head-clearance.json').write_text(json.dumps({'overlap_frames':hits,'method':'Evaluated head mesh BVH vs blade polygons beyond local z=.11. Overlap candidates, not exhaustive signed-distance collision proof.'},indent=2)+'\n')
    print('HEAD_BLADE_OVERLAP',hits,flush=True)

if __name__=='__main__':
    import sys
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task',choices=['export','source','target','before','check','check-head'])
    parser.add_argument('--out',type=Path,default=OUT)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    OUT=args.out.resolve()
    task=args.task
    if task=='export':export()
    elif task=='check':check()
    elif task=='check-head':check_head()
    else:render(task)
