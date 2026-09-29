"""Version selected actions on the equipped rig, preserving every other action.

Used by the Sunburst idle and H3 roll revisions. Each pose is sampled at 60 Hz;
all garment channels are explicit, including zeros, before FBX export.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # Blender's --python does not add the script's folder
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
from pathlib import Path
import hashlib
import json
import bpy
from cairo_rig import Rig, garment_values
from cairo_outfit_correctives import set_clip
from cairo_outfit_arm_clearance import ArmContactProbe
from prepare_cairo_game import bake_white_volume, action_signature
from refine_cairo_waist_overlap import bake_waist_clearance, KEY
from validate_cairo_idle_dash import protected

# ROOT (the archive) comes from _archive
ASSET = ROOT/'output/imagegen/yorimichi-yellow-boy-2026-09-12'


def author(parent, revision, specs):
    source = ASSET/parent/('WarmOriginal-'+parent.replace('game-', 'Game-')+'.blend')
    out = ASSET/revision
    out.mkdir(exist_ok=True)
    (out/'.gitignore').write_text('diagnostics/\n*.blend1\n')
    (out/'diagnostics').mkdir(exist_ok=True)
    record = json.loads((source.parent/'source-manifest.json').read_text())
    assert hashlib.sha256(source.read_bytes()).hexdigest() == record['native_sha256']
    bpy.ops.wm.open_mainfile(filepath=str(source))
    scene = bpy.context.scene
    arm = next(o for o in scene.objects if o.type == 'ARMATURE')
    items = {o['outfit_slot']: o for o in scene.objects if o.get('outfit_slot')}
    shirt, shorts, shoes = [items[k] for k in ['sweatshirt', 'shorts', 'shoes']]
    signatures, geometry = action_signature(bpy.data.actions), protected()
    set_clip(arm, bpy.data.actions['Standing · outfit review']); scene.frame_set(1)
    ev = shoes.evaluated_get(bpy.context.evaluated_depsgraph_get())
    rig = Rig(arm, scene, shoes, min((ev.matrix_world@v.co).z for v in ev.data.vertices))
    actions, tables, measures = [], {}, {}
    visibility = {o: o.hide_viewport for o in scene.objects if o.type == 'MESH'}
    for o in visibility:
        o.hide_viewport = visibility[o] if any(s.get('evaluate_meshes') for s in specs.values()) else True
    for name, spec in specs.items():
        action_name = name+' · library'
        action = bpy.data.actions.get(action_name)
        if action is None:
            action = bpy.data.actions.new(action_name); action.use_fake_user = True
            arm.animation_data.action = action
            for obj in [shirt, shorts]:
                keys = obj.data.shape_keys
                keys.animation_data.action = action
                slot = action.slots.new(id_type='KEY', name=keys.name)
                keys.animation_data.action_slot = slot
                mapping = dict(keys['clip_slots']); mapping[action_name] = slot.identifier
                keys['clip_slots'] = mapping
        else:
            set_clip(arm, action)
            for layer in action.layers:
                for strip in layer.strips:
                    for bag in strip.channelbags:
                        for fc in list(bag.fcurves): bag.fcurves.remove(fc)
        actions.append(action)
        table, samples, last = [], [], {}
        for frame in range(1, round(spec['duration']*60)+2):
            rig.begin(); info = spec['pose'](rig, (frame-1)/60) or {}
            rig.apply(); rig.key(frame, last)
            table.append({n: m.copy() for n, m in rig.M.items()})
            samples.append({'frame': frame, 'left_sole': list(rig.sole_low('Left')),
                'right_sole': list(rig.sole_low('Right')), 'hips': list(rig.head('Hips')),
                'left_hand': list(rig.head('LeftHand')), 'right_hand': list(rig.head('RightHand')),
                **{k: v for k, v in info.items() if isinstance(v, (float, int, bool))}})
        tables[name], measures[name] = table, samples
        if spec.get('filter'):
            table = spec['filter'](rig, table)
            tables[name] = table
            last = {}
            for frame, matrices in enumerate(table, 1):
                scene.frame_set(frame)
                rig.M = matrices; rig.apply(); rig.key(frame, last)
        print('AUTHORED', name, len(table), flush=True)
    for o, hidden in visibility.items(): o.hide_viewport = hidden
    probe, failures = ArmContactProbe(shirt), []
    for name, table in tables.items():
        action = bpy.data.actions[name+' · library']; set_clip(arm, action)
        for i, matrices in enumerate(table):
            scene.frame_set(i+1); rig.M = matrices
            values = garment_values(rig)
            for slot, obj in [('sweatshirt', shirt), ('shorts', shorts)]:
                for key in obj.data.shape_keys.key_blocks[1:]: key.value = values[slot].get(key.name, 0.)
            counts = probe.check()
            for side in ['Left', 'Right']:
                if counts[side]:
                    key = shirt.data.shape_keys.key_blocks[side+' · torso arm clearance']
                    for level in [.15, .3, .5, .7, .9, 1.]:
                        key.value = level
                        if not probe.check()[side]: break
                    else: failures.append({'clip': name, 'frame': i+1, 'side': side})
            for obj in [shirt, shorts]:
                for key in obj.data.shape_keys.key_blocks[1:]: key.keyframe_insert('value', frame=i+1)
        # Exporters discover the clothing slot through muted NLA references.
        for obj in [shirt, shorts]:
            keys = obj.data.shape_keys
            if not any(t.name == action.name for t in keys.animation_data.nla_tracks):
                track = keys.animation_data.nla_tracks.new(); track.name = action.name; track.mute = True
                strip = track.strips.new(action.name, 1, action)
                strip.action_slot = keys.animation_data.action_slot
        print('GARMENTS', name, flush=True)
    volume = bake_white_volume(arm, shirt, actions)
    loops = {name+' · library' for name, spec in specs.items() if spec.get('loop')}
    waist, unresolved = bake_waist_clearance(scene, arm, shirt, shorts,
        shorts.data.shape_keys.key_blocks[KEY], loops, actions=actions)
    for action in actions:
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fc in bag.fcurves:
                        for point in fc.keyframe_points: point.interpolation = 'LINEAR'
                        if action.name in loops: fc.modifiers.new('CYCLES')
    unchanged = {k: v for k, v in signatures.items() if k not in {a.name for a in actions}}
    assert unchanged == {k: v for k, v in action_signature(bpy.data.actions).items() if k in unchanged}
    assert geometry == protected(), 'Geometry, weights, rig, morph shapes or finger drivers changed'
    set_clip(arm, bpy.data.actions['Idle · library']); scene.frame_set(1)
    scene.render.fps = 60; scene.frame_start = 1; scene.frame_end = 241
    native = out/('WarmOriginal-'+revision.replace('game-', 'Game-')+'.blend')
    bpy.ops.wm.save_as_mainfile(filepath=str(native))
    for name, spec in specs.items():
        role = next((r for r in record['roles'] if r['role'] == name), None)
        if role is None:
            role = {'role': name, 'clip': name+' · library', 'mapping': name, 'fps': 60,
                'loop': False, 'kind': 'one-shot', 'root_motion': 'in_place'}
            record['roles'].append(role)
        role.pop('validation', None)
        role.update(duration_seconds=spec['duration'], frames=round(spec['duration']*60)+1,
            validation_record='validation.json', **spec.get('record', {}))
    record.update(native=str(native.relative_to(ROOT)), native_sha256=hashlib.sha256(native.read_bytes()).hexdigest(),
        parent_source=str(source.relative_to(ROOT)), parent_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        changed_actions=[a.name for a in actions], other_parent_actions_preserved=True,
        revision=revision, white_volume_ranges=volume, waist_ranges=waist, waist_authoring_failures=unresolved)
    (out/'source-manifest.json').write_text(json.dumps(record, indent=2)+'\n')
    (out/'authoring.json').write_text(json.dumps({'poses': measures, 'floor': rig.floor,
        'armature_scale': rig.scale, 'arm_contact_failures': failures, 'waist_authoring_failures': unresolved,
        'unchanged_actions': list(unchanged), 'protected_geometry_sha256': geometry}, indent=2)+'\n')
    print('REVISION_READY', revision, 'arm failures', failures, 'waist failures', unresolved, flush=True)
    assert not failures and not unresolved, 'Review garment intersections'
