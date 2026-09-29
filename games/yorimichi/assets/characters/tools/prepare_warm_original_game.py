"""Combine Fable's final animation library with the approved r07 garments."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
from pathlib import Path
import hashlib
import json
import math
import sys
import bpy
from mathutils import Vector, Quaternion

# ROOT (the archive) comes from _archive
ASSET = ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12'
SOURCE = ASSET / 'animations-r01/WarmOriginal-Animations-r01.blend'
GARMENT = ASSET / 'outfit-r07/WarmOriginal-Outfit-r07.blend'
OUT = ASSET / 'game-r01'
sys.path.insert(0, str(TOOLS))
from warm_outfit_correctives import set_clip
from refine_warm_waist_overlap import bake_waist_clearance, KEY


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def action_signature(actions, exclude_paths=()):
    signatures = {}
    for action in actions:
        rows = []
        for layer in action.layers:
            for strip in layer.strips:
                for slot in action.slots:
                    bag = strip.channelbag(slot)
                    if bag:
                        for fc in bag.fcurves:
                            if KEY in fc.data_path or 'white sleeve twist volume' in fc.data_path or any(p in fc.data_path for p in exclude_paths):
                                continue
                            rows.append([slot.name_display, fc.data_path, fc.array_index,
                                [[list(p.co), list(p.handle_left), list(p.handle_right), p.interpolation]
                                 for p in fc.keyframe_points]])
        signatures[action.name] = hashlib.sha256(json.dumps(rows).encode()).hexdigest()
    return signatures


def bake_white_volume(arm, shirt, actions):
    scene = bpy.context.scene
    visibility = {o:o.hide_viewport for o in scene.objects if o.type=='MESH'}
    for obj in visibility:
        obj.hide_viewport = True
    axes = {side:(arm.matrix_world @ arm.data.bones['mixamorig:'+side+'ForeArm'].tail_local
                  -arm.matrix_world @ arm.data.bones['mixamorig:'+side+'ForeArm'].head_local).normalized()
            for side in ['Left','Right']}
    keys = {side:shirt.data.shape_keys.key_blocks[side+' · white sleeve twist volume'] for side in axes}
    ranges = {side:[1.,0.] for side in keys}
    for action in actions:
        set_clip(arm, action)
        for frame in range(int(action.frame_range[0]), int(action.frame_range[1])+1):
            scene.frame_set(frame)
            for side, key in keys.items():
                rotations = []
                for part in ['Arm','ForeArm']:
                    name = 'mixamorig:'+side+part
                    rotations.append((arm.pose.bones[name].matrix @ arm.data.bones[name].matrix_local.inverted()).to_quaternion())
                q = rotations[0].conjugated() @ rotations[1]
                if q.w < 0:
                    q.negate()
                projection = Vector((q.x,q.y,q.z)).dot(axes[side])
                v = axes[side]*projection
                twist = Quaternion((q.w,v.x,v.y,v.z)).normalized()
                angle = 2*math.atan2(abs(projection),abs(q.w))
                swing = (q @ twist.conjugated()).angle
                t = max(0,min(1,(swing-math.radians(15))/math.radians(50)))
                gain = min(2,max(0,1/max(.25,math.cos(angle/2))-1))
                key.value = .5*gain*(1-t*t*(3-2*t))
                key.keyframe_insert('value',frame=frame)
                ranges[side][0] = min(ranges[side][0],key.value)
                ranges[side][1] = max(ranges[side][1],key.value)
    for obj, hidden in visibility.items():
        obj.hide_viewport = hidden
    return ranges


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / 'diagnostics').mkdir(exist_ok=True)
    (OUT / '.gitignore').write_text('diagnostics/\n*.blend1\n')
    manifest = json.loads((SOURCE.parent/'manifest.json').read_text())
    assert manifest['validation_passed']
    assert manifest['files'][SOURCE.name] == hash_file(SOURCE), 'Fable manifest/source mismatch'
    assert json.loads((GARMENT.parent/'validation.json').read_text())['passed']
    bpy.ops.wm.open_mainfile(filepath=str(GARMENT))
    garment_objects = {o['outfit_slot']:o for o in bpy.context.scene.objects
                       if o.get('outfit_slot') in ['sweatshirt','shorts']}
    names = {slot:obj.data.name for slot,obj in garment_objects.items()}
    groups = {slot:[g.name for g in obj.vertex_groups] for slot,obj in garment_objects.items()}
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    scene = bpy.context.scene
    arm = next(o for o in scene.objects if o.type=='ARMATURE')
    actions = list(bpy.data.actions)
    signatures = action_signature(actions)
    objects = {o['outfit_slot']:o for o in scene.objects if o.get('outfit_slot') in names}
    materials = {slot:list(obj.data.materials) for slot,obj in objects.items()}
    with bpy.data.libraries.load(str(GARMENT),link=False) as (_, data):
        data.meshes = list(names.values())
    for slot, mesh in zip(names, data.meshes):
        obj = objects[slot]
        assert [g.name for g in obj.vertex_groups] == groups[slot]
        assert len(obj.data.vertices) == len(mesh.vertices)
        obj.data = mesh
        mesh.materials.clear()
        for material in materials[slot]:
            mesh.materials.append(material)
        keys = mesh.shape_keys
        keys.animation_data_clear()
        mapping = {}
        for action in actions:
            target = next(s for s in action.slots if s.target_id_type=='KEY'
                          and s.name_display=='Cloth · '+slot)
            mapping[action.name] = target.identifier
        keys['clip_slots'] = mapping
    # Appending a mesh can also append its old action dependencies. Only the
    # authoritative Fable actions belong in this combined library.
    for action in list(bpy.data.actions):
        if action not in actions:
            bpy.data.actions.remove(action)
    shirt, shorts = objects['sweatshirt'], objects['shorts']
    volume_ranges = bake_white_volume(arm, shirt, actions)
    loops = {r['clip'] for r in manifest['roles'] if r['loop']}
    waist_ranges, unresolved = bake_waist_clearance(scene,arm,shirt,shorts,
        shorts.data.shape_keys.key_blocks[KEY],loops)
    assert not unresolved, unresolved
    assert signatures == action_signature(actions), 'An original Fable curve changed'
    set_clip(arm,bpy.data.actions['Standing · outfit review'])
    scene.frame_set(1)
    bpy.ops.file.pack_all()
    native = OUT / 'WarmOriginal-Game-r01.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(native))
    report = {'animation_source':str(SOURCE.relative_to(ROOT)), 'animation_source_sha256':hash_file(SOURCE),
        'garment_source':str(GARMENT.relative_to(ROOT)), 'garment_source_sha256':hash_file(GARMENT),
        'native':str(native.relative_to(ROOT)), 'native_sha256':hash_file(native),
        'original_fable_curves_preserved':True, 'original_curve_signatures':signatures,
        'white_volume_ranges':volume_ranges, 'waist_ranges':waist_ranges,
        'waist_authoring_failures':unresolved,'bones':len(arm.data.bones),'finger_drivers':len(arm.animation_data.drivers),
        'roles':manifest['roles'], 'animation_files':manifest['files']}
    (OUT / 'source-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print('WARM_GAME_SOURCE_READY',native,flush=True)


if __name__=='__main__':
    main()
