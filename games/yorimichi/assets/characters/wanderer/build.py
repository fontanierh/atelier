"""blender -b --python japan/characters/wanderer/build.py -- --views front,side,back,face"""
import argparse
import json
import math
import sys
from pathlib import Path
import bpy
from mathutils import Vector

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]/'world')); import yori  # noqa: E402
sys.path.insert(0,str(HERE/'kit'))
sys.path.insert(0,str(HERE))
from wanderer_mesh import build_model
from wanderer_rig import build_rig
import pipeline
OUT=yori.OUT/'wanderer'

def studio():
    sc=bpy.context.scene
    world=bpy.data.worlds.new('Neutral reference studio')
    world.use_nodes=True
    world.node_tree.nodes['Background'].inputs[0].default_value=(.32,.33,.36,1)
    world.node_tree.nodes['Background'].inputs[1].default_value=1.0
    sc.world=world
    bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,.0065))
    floor=bpy.context.object
    floor.name='Studio floor'
    m=bpy.data.materials.new('Studio grey')
    m.diffuse_color=(.205,.215,.239,1)
    m.use_nodes=True
    m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.205,.215,.239,1)
    m.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=1
    floor.data.materials.append(m)
    for name,loc,power,size,col in [
        ('Key',(-3,-4,6),250,4,(1,.94,.86)),
        ('Fill',(3,-2,3),150,4,(.88,.92,1)),
        ('Rim',(1,3,4),140,3,(1,.95,.9))]:
        d=bpy.data.lights.new(name,'AREA')
        d.energy,d.shape,d.size,d.color=power,'DISK',size,col
        o=bpy.data.objects.new(name,d)
        bpy.context.collection.objects.link(o)
        o.location=loc
        o.rotation_euler=(Vector((0,0,.9))-o.location).to_track_quat('-Z','Y').to_euler()
    cd=bpy.data.cameras.new('Review camera')
    cam=bpy.data.objects.new('Review camera',cd)
    bpy.context.collection.objects.link(cam)
    cd.type='ORTHO'
    sc.camera=cam
    sc.render.engine='CYCLES'
    sc.cycles.samples=32
    sc.cycles.use_denoising=True
    sc.view_settings.view_transform='Standard'
    sc.view_settings.look='None'
    sc.render.image_settings.file_format='PNG'
    return cam

VIEWS={
    'front':((0,-5,1.06),(0,0,.76),1.65),
    'three_quarter':((-2.8,-5,1.23),(0,0,.76),1.65),
    'side':((-5,0,.76),(0,0,.76),1.65),
    'back':((0,5,1.08),(0,0,.76),1.65),
    'back_three_quarter':((3,5,1.18),(0,0,.76),1.65),
    'face':((0,-5,1.27),(0,0,1.27),.54),
    'head_side':((-5,-1.75,1.32),(0,0,1.27),.52),
    'head_profile':((-5,0,1.27),(0,0,1.27),.54),
    'calibrated_front':((-.000875,-5,1.226875),(-.000875,0,1.226875),.54425),
    'calibrated_side':((-5,-.00855,1.2539),(0,-.00855,1.2539),.5776),
}

def main():
    global OUT
    p=argparse.ArgumentParser()
    p.add_argument('--views',default='front,three_quarter,side,back,face,head_profile')
    p.add_argument('--study')
    p.add_argument('--resolution',type=int,default=800)
    p.add_argument('--animations',action='store_true')
    p.add_argument('--export',action='store_true')
    p.add_argument('--no-render',action='store_true')
    opt=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if opt.study:
        if opt.export: raise ValueError('Study output cannot replace production exports')
        OUT=OUT/'studies'/opt.study
    OUT.mkdir(parents=True,exist_ok=True)
    if opt.export:
        (OUT/'build.json').unlink(missing_ok=True)
    source_hashes=pipeline.source_hashes()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc=bpy.context.scene
    sc.unit_settings.system='METRIC'
    sc.render.fps=60
    arm=build_rig()
    parts=build_model()
    bpy.ops.object.select_all(action='DESELECT')
    for ob in parts: ob.select_set(True)
    bpy.context.view_layer.objects.active=parts[0]
    bpy.ops.object.join()
    body=bpy.context.object
    body.name=body.data.name='Wanderer_Body'
    body.parent=arm
    mod=body.modifiers.new('Wanderer skin','ARMATURE')
    mod.object=arm
    body['reference']='references/design-sheet.png; orthographic and detail crops'
    body['design']='Wanderer V2: moss haori, rust scarf, topknot, simple eyes and back hat'
    for material in body.data.materials: material.name='Wanderer_Palette'
    if opt.animations:
        import wanderer_motion as animate
        animate.build_actions(arm,OUT)
    cam=studio()
    sc.render.resolution_x=opt.resolution
    sc.render.resolution_y=round(opt.resolution*1.15)
    sc.render.resolution_percentage=100
    manifest={
        'vertices':len(body.data.vertices),
        'triangles':sum(len(p.vertices)-2 for p in body.data.polygons),
        'bones':{b.name:b.parent.name if b.parent else None for b in arm.data.bones},
        'materials':[m.name for m in body.data.materials],
        'sole_z_m':.0065, 'ankle_height_cm':10.55, 'character_version':'wanderer_v2',
        'height_m':max(v.co.z for v in body.data.vertices)-min(v.co.z for v in body.data.vertices),
        'source_hashes':source_hashes,
    }
    (OUT/'model_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    if opt.export:
        folder=OUT/'fbx'
        folder.mkdir(exist_ok=True)
        active=arm.animation_data.action if arm.animation_data else None
        if arm.animation_data: arm.animation_data.action=None
        for pb in arm.pose.bones: pb.matrix_basis.identity()
        bpy.context.view_layer.update()
        bpy.ops.object.select_all(action='DESELECT')
        body.select_set(True)
        arm.select_set(True)
        bpy.context.view_layer.objects.active=arm
        common=dict(use_selection=True,apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',
            axis_forward='-Y',axis_up='Z',add_leaf_bones=False,use_armature_deform_only=True,
            bake_anim_use_nla_strips=False,bake_anim_use_all_actions=False,bake_anim_simplify_factor=0,
            mesh_smooth_type='FACE',colors_type='SRGB')
        bpy.ops.export_scene.fbx(filepath=str(folder/'Wanderer.fbx'),object_types={'ARMATURE','MESH'},bake_anim=False,**common)
        if opt.animations:
            body.select_set(False)
            for name,settings in animate.ACTIONS.items():
                arm.animation_data.action=bpy.data.actions[name]
                sc.frame_start,sc.frame_end=1,settings['frames']
                sc.frame_set(1)
                bpy.ops.export_scene.fbx(filepath=str(folder/(name+'.fbx')),object_types={'ARMATURE'},bake_anim=True,**common)
        if arm.animation_data: arm.animation_data.action=active
    # Store reference images inside the native file as images, so the model remains reviewable.
    for name in ('design-sheet','motion-sheet','skate-sheet'):
        im=bpy.data.images.load(str(HERE/'references'/(name+'.png')))
        im.pack()
    sc.frame_start,sc.frame_end=1,241
    sc.frame_set(1)
    cam.location, target, cam.data.ortho_scale=VIEWS['three_quarter']
    cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Wanderer.blend'))
    if not opt.no_render:
        review=OUT/'review'
        review.mkdir(exist_ok=True)
        for name in opt.views.split(','):
            # The landmark cameras compare the authored mesh, without the idle
            # clip's small translation and head tilt shifting the measurement.
            arm.data.pose_position='REST' if name.startswith('calibrated_') else 'POSE'
            bpy.context.view_layer.update()
            sc.render.resolution_x,sc.render.resolution_y={
                'calibrated_front':(892,1244),'calibrated_side':(756,1216),
            }.get(name,(opt.resolution,round(opt.resolution*1.15)))
            cam.location,target,cam.data.ortho_scale=VIEWS[name]
            cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler()
            sc.render.filepath=str(review/(name+'.png'))
            bpy.ops.render.render(write_still=True)
            print('RENDERED',name,flush=True)
    if opt.export and opt.animations:
        pipeline.mark(source_hashes)
    print('WANDERER BUILD COMPLETE',manifest,flush=True)

if __name__=='__main__': main()
