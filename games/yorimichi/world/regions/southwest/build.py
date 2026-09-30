"""blender -b --python-exit-code 1 --python japan/southwest/build.py -- --models stand [--export] [--views front,three_quarter,side,back,detail]
Builds the south-west detour props, renders review views into build/yorimichi/southwest/review/<model>/, exports FBX."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import argparse, json, sys, math
from pathlib import Path
import bpy
from mathutils import Vector
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));OUT=yori.OUT/'southwest'
from mesh import material
import stand, fishing, temple, island
MODELS={'stand':stand.build,**fishing.MODELS,'temple':temple.temple,'island':island.build,'boulder_a':island.boulder_a,'boulder_b':island.boulder_b,'boulder_c':island.boulder_c,'pine_lean_a':island.pine_lean_a,'pine_lean_b':island.pine_lean_b}
VIEWS={'front':((0,-6,1.3),(0,0,.9),3.6),'three_quarter':((-4.5,-5,2.2),(0,0,.9),3.8),'side':((-6,0,1.4),(0,0,.9),3.6),'back':((4,5,2.2),(0,0,.9),3.8),'detail':((-1.6,-3.2,1.55),(-.2,-.9,1.05),1.6)}
FRAMES={'stand':dict(target=(0.3,-0.3,1.45),scale=7.2,lift=0),'wake':dict(target=(-2,0,0),scale=6,lift=.3),'island':dict(target=(0,0,40),scale=340,lift=0),'temple':dict(target=(0,-2.5,2.4),scale=27,lift=0),'boulder_a':dict(target=(0,0,.6),scale=4,lift=0),'boulder_b':dict(target=(0,0,.6),scale=4,lift=0),'boulder_c':dict(target=(0,0,.6),scale=4,lift=0),'pine_lean_a':dict(target=(2.8,0,4.5),scale=15,lift=0),'pine_lean_b':dict(target=(1.8,0,5.5),scale=15,lift=0),'stone_wall':dict(target=(0,0,.4),scale=7,lift=0),'fishing_vignette':dict(target=(0,0,1.5),scale=19,lift=0),'fisher_house_a':dict(target=(0,0,2.2),scale=9,lift=0),'fisher_house_b':dict(target=(0,0,2.2),scale=9,lift=0),'boat_shed':dict(target=(0,0,1.6),scale=9,lift=0),'stairs':dict(target=(0,1.8,1.2),scale=6,lift=0),'dock':dict(target=(0,-3,.5),scale=11,lift=0),'boat':dict(target=(0,0,0),scale=6,lift=.6),'drying_rack':dict(target=(0,0,1),scale=4,lift=0),'kite':dict(target=(0,-.6,-.9),scale=4.6,lift=1.6),'kitebar':dict(target=(0,0,0),scale=.9,lift=0),'kiteboard':dict(target=(0,0,0),scale=1.8,lift=0)}
def studio(target):
    sc=bpy.context.scene;w=bpy.data.worlds.new('sw');w.use_nodes=True;w.node_tree.nodes['Background'].inputs[0].default_value=(.36,.40,.46,1);w.node_tree.nodes['Background'].inputs[1].default_value=1.3;sc.world=w
    bpy.ops.mesh.primitive_plane_add(size=60,location=(0,0,0));f=bpy.context.object;f.name='floor';mat=bpy.data.materials.new('sand');mat.use_nodes=True;mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.55,.47,.30,1);mat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=1;f.data.materials.append(mat)
    for name,loc,power,size,col in [('Key',(-5,-6,7),900,5,(1,.93,.82)),('Fill',(6,-3,4),350,5,(.85,.90,1)),('Rim',(2,6,5),400,4,(1,.95,.9))]:
        d=bpy.data.lights.new(name,'AREA');d.energy,d.shape,d.size,d.color=power,'DISK',size,col;o=bpy.data.objects.new(name,d);bpy.context.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()
    sun=bpy.data.lights.new('Sun','SUN');sun.energy=3.2;sun.angle=math.radians(4);sun.color=(1,.95,.85);so=bpy.data.objects.new('Sun',sun);bpy.context.collection.objects.link(so);so.rotation_euler=(math.radians(52),0,math.radians(-35))
    cd=bpy.data.cameras.new('cam');cam=bpy.data.objects.new('cam',cd);bpy.context.collection.objects.link(cam);cd.type='ORTHO';sc.camera=cam
    sc.render.engine='CYCLES';sc.cycles.samples=48;sc.cycles.use_denoising=True;sc.view_settings.view_transform='Standard';sc.render.image_settings.file_format='PNG'
    return cam
def main():
    p=argparse.ArgumentParser();p.add_argument('--models',default='stand');p.add_argument('--views',default='three_quarter,front,side,back,detail');p.add_argument('--export',action='store_true');p.add_argument('--size',type=int,default=1200);p.add_argument('--no-render',action='store_true')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    bpy.ops.wm.read_factory_settings(use_empty=True);sc=bpy.context.scene;sc.unit_settings.system='METRIC'
    mat=material();manifest=json.loads((OUT/'manifest.json').read_text()) if (OUT/'manifest.json').exists() else {}
    for name in a.models.split(','):
        for o in [o for o in bpy.data.objects if o.type=='MESH' and o.name!='floor']:bpy.data.objects.remove(o,do_unlink=True)
        m=MODELS[name]();obj=m.object(mat);tris=sum(len(f.vertices)-2 for f in obj.data.polygons)
        cam=studio((0,0,.9)) if not sc.camera else sc.camera
        fr=FRAMES.get(name,dict(target=(0,0,.9),scale=None,lift=0));obj.location.z+=fr['lift']
        rev=OUT/'review'/name;rev.mkdir(parents=True,exist_ok=True)
        sc.render.resolution_x=a.size;sc.render.resolution_y=round(a.size*.75);sc.render.resolution_percentage=100
        for v in ([] if a.no_render else a.views.split(',')):
            pos,target,scale=VIEWS[v];target=Vector(fr['target'])+Vector((0,0,fr['lift']));scale=fr['scale'] or scale;far=max(1.0,scale/3.8);cam.location=target+(Vector(pos)-Vector((0,0,.9)))*far;cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=scale
            sc.render.filepath=str(rev/(v+'.png'));bpy.ops.render.render(write_still=True)
        manifest[name]=dict(triangles=tris,vertices=len(obj.data.vertices),colliders=len(m.colliders))
        if a.export:
            # Studio floor clearance must not become an in-game mesh offset.
            obj.location.z-=fr['lift']
            (OUT/'fbx').mkdir(exist_ok=True);bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
            bpy.ops.export_scene.fbx(filepath=str(OUT/'fbx'/(obj.name+'.fbx')),use_selection=True,apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',axis_forward='-Y',axis_up='Z',mesh_smooth_type='FACE',colors_type='SRGB',bake_anim=False)
        print('MODEL',name,manifest[name],flush=True)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2));bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Southwest.blend'));print('SOUTHWEST BUILD COMPLETE',flush=True)
main()
