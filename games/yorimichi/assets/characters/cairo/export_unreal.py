"""Export the corrected dressed character, textured materials and morph clips for UE."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys
import tomllib
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from outfit_correctives import set_clip
from atelier.character.names import slug, mixamo_aliases

SOURCE = Path(__file__).resolve().parent   # the current revision's source file and manifests
OUT = yori.OUT / 'cairo'


def ue_transform(M, scale, floor):
    """Blender world matrix (metres, Z up, right-handed) -> Unreal component space: cm, Y mirrored, floor at the sole."""
    R = M.to_3x3().normalized(); mirror = Matrix.Diagonal((1,-1,1))
    q = (mirror @ R @ mirror).to_quaternion()
    t = M.translation
    return {'location_cm':[t.x*100,-t.y*100,t.z*100],'rotation_quat_xyzw':[q.x,q.y,q.z,q.w]}


def export_sword(arm, transform, scale, floor):
    """Static-mesh FBX of the bokken in its own pivot frame plus the rest-pose attachment data."""
    sword = bpy.data.objects['Bokken-stage1-r01']
    scene = bpy.context.scene
    arm.animation_data.action = None; arm.data.pose_position = 'REST'
    for pb in arm.pose.bones: pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    # the armature already carries `transform`; the bone-parented sword follows it
    sword_world = sword.matrix_world.copy(); world_scale = sword_world.to_scale().x
    hand = arm.matrix_world @ arm.data.bones['hand_R'].matrix_local
    copy = bpy.data.objects.new('SM_Bokken', sword.data.copy()); scene.collection.objects.link(copy)
    copy.matrix_world = Matrix.Diagonal((world_scale,world_scale,world_scale,1))
    for m in copy.data.materials: m.name = 'M_Bokken_'+slug(m.name) if not m.name.startswith('M_Bokken_') else m.name
    bpy.ops.object.select_all(action='DESELECT'); copy.select_set(True); bpy.context.view_layer.objects.active = copy
    bpy.ops.export_scene.fbx(filepath=str(OUT/'fbx/SM_Bokken.fbx'),use_selection=True,object_types={'MESH'},apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',
        axis_forward='-Y',axis_up='Z',bake_anim=False,mesh_smooth_type='FACE',use_mesh_modifiers=False,path_mode='COPY',embed_textures=True)
    materials = {}
    for material in copy.data.materials:
        shader = next((n for n in material.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None) if material.node_tree else None
        color = shader.inputs['Base Color'] if shader else None; texture=None
        if color is not None and color.is_linked and color.links[0].from_node.type=='TEX_IMAGE':
            image = color.links[0].from_node.image
            data = image.packed_file.data if image.packed_file else None
            # keep the real container: packed Tripo textures are JPEG bytes
            target = OUT/'textures'/('T_'+slug(material.name)+('.jpg' if data and data[:3]==b'\xff\xd8\xff' else '.png'))
            if data: target.write_bytes(data)
            else: image.save_render(str(target))
            texture = str(target.relative_to(OUT))
        materials[material.name] = {'texture':texture,'base_color':list(color.default_value) if color is not None else [.6,.45,.3,1],
            'roughness':float(shader.inputs['Roughness'].default_value) if shader else .7,'metallic':0.,'specular':.3,'two_sided':False}
    bpy.data.objects.remove(copy, do_unlink=True)
    tip = sword_world @ Vector((0,0,.36)); guard = sword_world @ Vector((0,0,.0995))
    arm.data.pose_position = 'POSE'
    return {'mesh':'fbx/SM_Bokken.fbx','materials':materials,'attach_bone':'hand_R','rest_component_transform':ue_transform(sword_world, scale, floor),
            'rest_hand_component_transform':ue_transform(hand, scale, floor),'rest_tip_cm':[tip.x*100,-tip.y*100,tip.z*100],'rest_guard_cm':[guard.x*100,-guard.y*100,guard.z*100],
            'blade_local_cm':{'start':[0,0,.0995*world_scale*100],'end':[0,0,.36*world_scale*100]},'mesh_scale':world_scale,
            'note':'Relative attachment = rest_component_transform * inverse(hand_R reference-pose component transform), computed in Unreal from the imported skeleton.'}


def main(args):
    source = SOURCE if not args.revision else Path(args.revision).resolve()
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'fbx').mkdir(exist_ok=True)
    (OUT/'textures').mkdir(exist_ok=True)
    record = json.loads((source/'source-manifest.json').read_text())
    # In this folder the source file is named in character.toml; an archive revision folder keeps the recorded name.
    toml = source/'character.toml'
    native = source/(tomllib.loads(toml.read_text())['source'] if toml.exists() else Path(record['native']).name)
    assert hashlib.sha256(native.read_bytes()).hexdigest()==record['native_sha256']
    bpy.ops.wm.open_mainfile(filepath=str(native))
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1
    scene.render.fps = 60
    arm = next(o for o in scene.objects if o.type=='ARMATURE')
    meshes = [o for o in scene.objects if o.type=='MESH' and
              (o.get('outfit_slot') or (o.get('body_region') and not o.get('hidden_by_slot')))]
    set_clip(arm,bpy.data.actions['Standing · outfit review'])
    scene.frame_set(1)
    bpy.context.view_layer.update()
    points = []
    for obj in meshes:
        ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        used = {i for f in ev.data.polygons for i in f.vertices}
        points.extend(ev.matrix_world @ ev.data.vertices[i].co for i in used)
    floor, top = min(p.z for p in points), max(p.z for p in points)
    scale = 1.48/(top-floor)
    transform = Matrix.Diagonal((scale,scale,scale,1)) @ Matrix.Translation((0,0,-floor+.0065/scale))
    matrices = {o:o.matrix_world.copy() for o in [arm,*meshes]}
    for obj, original in matrices.items():
        obj.matrix_world = transform @ original
    original_names = mixamo_aliases()
    assert set(original_names)=={b.name for b in arm.data.bones}
    for old, new in original_names.items():
        arm.data.bones[old].name = new
    arm.name = 'Armature'  # UE recognizes and omits the FBX armature object node.
    morphs = {}
    for obj in meshes:
        slot = obj.get('outfit_slot') or obj.get('body_region')
        obj.name = 'Cairo_'+slug(slot)
        if obj.data.shape_keys:
            morphs[slot] = {}
            for key in obj.data.shape_keys.key_blocks[1:]:
                old = key.name
                key.name = slug(slot)+'_'+slug(old)
                morphs[slot][old] = key.name
    # Blender's RNA rename only repairs the attached action in this multi-slot
    # library. Update every inactive clip too, before FBX samples the timeline.
    for action in bpy.data.actions:
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fc in bag.fcurves:
                        for old,new in original_names.items():
                            fc.data_path=fc.data_path.replace('pose.bones["'+old+'"]','pose.bones["'+new+'"]')
        for obj in meshes:
            keys=obj.data.shape_keys
            if not keys or 'clip_slots' not in keys: continue
            identifier=keys['clip_slots'].get(action.name)
            slot=next((s for s in action.slots if s.identifier==identifier),None)
            if not slot: continue
            renames=morphs[obj.get('outfit_slot') or obj.get('body_region')]
            for layer in action.layers:
                for strip in layer.strips:
                    bag=strip.channelbag(slot)
                    if bag:
                        for fc in bag.fcurves:
                            for old,new in renames.items():
                                fc.data_path=fc.data_path.replace('key_blocks["'+old+'"]','key_blocks["'+new+'"]')
    bpy.context.view_layer.update()
    feet = {side:list(arm.matrix_world @ arm.data.bones['foot_'+side].head_local)
            for side in ['L','R']}
    materials = {}
    for obj in meshes:
        for material in obj.data.materials:
            if material.name in materials:
                continue
            old = material.name
            material.name = 'M_Cairo_'+slug(old)
            shader = next(n for n in material.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
            color = shader.inputs['Base Color']
            texture = None
            if color.is_linked:
                node = color.links[0].from_node
                assert node.type=='TEX_IMAGE', (old,'Unsupported base-color graph',node.type)
                image = node.image
                target = OUT/'textures'/('T_'+slug(old)+'.png')
                if image.packed_file:
                    target.write_bytes(image.packed_file.data)
                else:
                    image.save_render(str(target))
                texture = str(target.relative_to(OUT))
            materials[material.name] = {'source_name':old,'base_color':list(color.default_value),
                'texture':texture, 'two_sided':not material.use_backface_culling, 'roughness':float(shader.inputs['Roughness'].default_value),
                'metallic':float(shader.inputs['Metallic'].default_value),
                'specular':float(shader.inputs['Specular IOR Level'].default_value)}
    # Preserve the exact material labels in the FBX; Unreal materials are built
    # explicitly from this manifest instead of the legacy vertex-color shader.
    def select(objects):
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:
            obj.hide_viewport=False
            obj.hide_set(False)
            obj.select_set(True)
        bpy.context.view_layer.objects.active = arm

    common = dict(use_selection=True,apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',
        axis_forward='-Y',axis_up='Z',add_leaf_bones=False,use_armature_deform_only=False,
        bake_anim_use_nla_strips=False,bake_anim_use_all_actions=False,bake_anim_simplify_factor=0,
        bake_anim_step=1,mesh_smooth_type='FACE',use_mesh_modifiers=False,path_mode='ABSOLUTE')
    if not args.clips_only:
        arm.animation_data.action = None
        arm.data.pose_position = 'REST'
        for obj in meshes:
            if obj.data.shape_keys:
                if obj.data.shape_keys.animation_data:
                    obj.data.shape_keys.animation_data.action = None
                for key in obj.data.shape_keys.key_blocks[1:]:
                    key.value = 0
        select([arm,*meshes])
        bpy.ops.export_scene.fbx(filepath=str(OUT/'fbx/Cairo.fbx'),
            object_types={'ARMATURE','MESH'},bake_anim=False,**common)
        arm.data.pose_position = 'POSE'
    clips = {}
    # Skating poses come from the recovered runtime, never the legacy authored clips.
    roles = [r for r in record['roles'] if not r['role'].startswith('Skate')]
    by_action = {}
    for role in roles:
        by_action.setdefault(role['clip'],role['role'])
    by_action['Sprint · dressed'] = 'Sprint'
    for action_name, name in by_action.items():
        if args.clips and name not in args.clips.split(','):
            continue
        action = bpy.data.actions[action_name]
        set_clip(arm,action)
        scene.frame_start,scene.frame_end = map(int,action.frame_range)
        scene.frame_set(scene.frame_start)
        select([arm,*[o for o in meshes if o.data.shape_keys]])
        sample_rate=max(r.get('export_sample_rate',60) for r in roles if r['clip']==action_name)
        bpy.ops.export_scene.fbx(filepath=str(OUT/'fbx'/('A_'+name+'.fbx')),
            object_types={'ARMATURE','MESH'},bake_anim=True,**dict(common,bake_anim_step=60/sample_rate))
        expected = {k.name:[] for o in meshes if o.data.shape_keys for k in o.data.shape_keys.key_blocks[1:]}
        for frame in range(scene.frame_start,scene.frame_end+1):
            scene.frame_set(frame)
            for obj in meshes:
                if obj.data.shape_keys:
                    for key in obj.data.shape_keys.key_blocks[1:]:
                        expected[key.name].append(round(float(key.value),7))
        role_rows=[r for r in roles if r['clip']==action_name]
        clips[name] = {'action':action_name,'frames':scene.frame_end-scene.frame_start+1,
                      'duration':(scene.frame_end-scene.frame_start)/60,'sample_rate':sample_rate,'expected_morph_curves':expected,
                      'root_motion':any('root bone' in str(r.get('root_motion','')) for r in role_rows),'loop':any(r.get('loop') for r in role_rows)}
        print('UNREAL_CLIP_EXPORTED',name,flush=True)
    sword_report = export_sword(arm, transform, scale, floor) if args.sword and record.get('sword') else None
    report = {'source':native.name,'source_sha256':record['native_sha256'],'sword':sword_report,
        'model_scale':scale,'height_cm':148,'sole_cm':.65,'source_floor':floor,
        'rest_ankles_cm':{side:p[2]*100 for side,p in feet.items()},'bones':original_names,
        'materials':materials,'morphs':morphs,'roles':roles,'clips':clips,
        'excluded_geometry':'Preserved fitting body and body regions hidden by the equipped outfit.'}
    (OUT/(args.report or 'export.json')).write_text(json.dumps(report,indent=2)+'\n')
    print('CAIRO_UNREAL_EXPORT_READY',flush=True)


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--clips')
    parser.add_argument('--clips-only',action='store_true')
    parser.add_argument('--revision',help='Folder of another revision (from the archive); default is this folder')
    parser.add_argument('--sword',action='store_true',help='Also export the bone-parented bokken as a static mesh with attachment data')
    parser.add_argument('--report',help='Write export.json under this name instead (partial exports must not replace the full record)')
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    main(args)
