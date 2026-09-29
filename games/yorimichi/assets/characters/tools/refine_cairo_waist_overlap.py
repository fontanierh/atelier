"""Stabilize the shorts waistband and keep it beneath the approved shirt."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
from pathlib import Path
import argparse
import hashlib
import json
import sys

import bpy
import numpy as np

# ROOT (the archive) comes from _archive
ASSET = ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12'
SOURCE = ASSET / 'outfit-r06/WarmOriginal-Outfit-r06.blend'
OUT = ASSET / 'outfit-r07'
sys.path.insert(0, str(TOOLS))
from cairo_outfit_correctives import set_clip
from cairo_waist_contact import WaistContactProbe

KEY = 'Waist · shirt clearance'


def export_current():
    scene = bpy.context.scene
    arm = next(o for o in scene.objects if o.type == 'ARMATURE')
    set_clip(arm, bpy.data.actions['Standing · outfit review'])
    scene.frame_set(1)

    def export(path, objects, animations):
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:
            obj.hide_set(False)
            obj.select_set(True)
        bpy.context.view_layer.objects.active = arm
        bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB',
            use_selection=True, use_visible=False, use_renderable=False,
            export_animations=animations, export_animation_mode='ACTIONS',
            export_frame_range=False, export_force_sampling=True,
            export_anim_slide_to_zero=True, export_extras=True)

    export(OUT / 'WarmOriginal-Outfit-r07.glb', [o for o in scene.objects
        if o == arm or o.get('outfit_slot') or o.get('body_region') or o.get('base_body')], True)
    shorts = next(o for o in scene.objects if o.get('outfit_slot') == 'shorts')
    for key in shorts.data.shape_keys.key_blocks[1:]:
        key.value = 0
    export(OUT / 'items/shorts.glb', [arm, shorts], False)


def bake_waist_clearance(scene, arm, shirt, shorts, key, loops, actions=None):
    visibility = {o: o.hide_viewport for o in scene.objects if o.type == 'MESH'}
    for obj in visibility:
        obj.hide_viewport = True
    shirt.hide_viewport = False
    shorts.hide_viewport = False
    probe = WaistContactProbe(shirt, shorts)
    ranges = {}
    unresolved = []
    for action in list(bpy.data.actions) if actions is None else actions:
        if not any(s.target_id_type == 'OBJECT' for s in action.slots):
            continue
        set_clip(arm, action)
        start, end = map(int, action.frame_range)
        frames = sorted(set(list(range(start, end+1, 2))+[end]))
        required = []
        for frame in frames:
            scene.frame_set(frame)
            key.value = 0
            value = 0
            if probe.check()['shorts_faces']:
                for level in [.25, .5, .75, 1.0]:
                    key.value = level
                    if not probe.check()['shorts_faces']:
                        value = min(1, level+.15)
                        break
                else:
                    value = 1
                    unresolved.append({'clip':action.name, 'frame':frame})
            required.append(value)
        # A soft lead-in and release covers samples between authoring frames.
        # Circular padding keeps loops continuous at their shared endpoint.
        required = np.array(required)
        loop = action.name in loops
        values_in = required[:-1] if loop and len(required)>1 else required
        padded = np.pad(values_in, 3, mode='wrap' if loop else 'edge')
        envelope = np.maximum.reduce([padded[i:i+len(values_in)] for i in range(7)])
        padded = np.pad(envelope, 2, mode='wrap' if loop else 'edge')
        envelope = sum(padded[i:i+len(values_in)] for i in range(5))/5
        envelope = np.maximum(envelope, values_in)
        if loop and len(required)>1:
            envelope = np.append(envelope, envelope[0])
        values = []
        for frame in range(start, end+1):
            scene.frame_set(frame)
            value = float(np.interp(frame, frames, envelope))
            key.value = value
            key.keyframe_insert('value', frame=frame)
            values.append(value)
        ranges[action.name] = [min(values), max(values)]
        print('WAIST_BAKE', action.name, ranges[action.name], flush=True)
        slot = shorts.data.shape_keys.animation_data.action_slot
        for layer in action.layers:
            for strip in layer.strips:
                bag = strip.channelbag(slot)
                if bag:
                    for fc in bag.fcurves:
                        if KEY in fc.data_path:
                            for point in fc.keyframe_points:
                                point.interpolation = 'LINEAR'
    for obj, hidden in visibility.items():
        obj.hide_viewport = hidden
    return ranges, unresolved


def build(clearance):
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    scene = bpy.context.scene
    arm = next(o for o in scene.objects if o.type == 'ARMATURE')
    shirt = next(o for o in scene.objects if o.get('outfit_slot') == 'sweatshirt')
    shorts = next(o for o in scene.objects if o.get('outfit_slot') == 'shorts')
    assert KEY not in shorts.data.shape_keys.key_blocks
    points = np.array([v.co[:] for v in shorts.data.vertices])
    t = np.clip((points[:, 2] + .16) / .06, 0, 1)
    t = t*t*(3-2*t)
    changed = 0
    for vertex in shorts.data.vertices:
        strength = float(t[vertex.index])
        if strength <= 0:
            continue
        weights = {shorts.vertex_groups[g.group].name: g.weight*(1-strength)
                   for g in vertex.groups}
        weights['mixamorig:Spine'] = weights.get('mixamorig:Spine', 0) + strength
        weights = sorted(weights.items(), key=lambda item: -item[1])[:4]
        total = sum(w for _, w in weights)
        # Copy integer IDs before mutating Blender's live group collection.
        for group_index in [g.group for g in vertex.groups]:
            shorts.vertex_groups[group_index].remove([vertex.index])
        for name, weight in weights:
            if weight > 1e-7:
                shorts.vertex_groups[name].add([vertex.index], weight/total, 'REPLACE')
        changed += 1

    # Move both cloth walls and sewn details together. The field fades before
    # the shorts leg openings; its baked value follows the shirt's inward fold.
    radial = points[:, :2] - [.023, 0]
    radial /= np.maximum(np.linalg.norm(radial, axis=1)[:, None], 1e-8)
    field = np.clip((points[:, 2] + .18) / .08, 0, 1)
    field = field*field*(3-2*field)
    fitted = points.copy()
    fitted[:, :2] -= radial * (clearance*field)[:, None]
    key = shorts.shape_key_add(name=KEY)
    key.data.foreach_set('co', fitted.astype(np.float32).ravel())
    library = json.loads((ASSET / 'outfit-r06/library.json').read_text())
    loops = {c['action'] for c in library['clips'].values() if c.get('loop')}
    loops.add('Sprint · dressed')
    ranges, unresolved = bake_waist_clearance(scene, arm, shirt, shorts, key, loops)
    shorts['waist_revision'] = 'r07: stable waist anchor and baked shirt-underlap correction'
    set_clip(arm, bpy.data.actions['Standing · outfit review'])
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'WarmOriginal-Outfit-r07.blend'))
    report = {'source': str(SOURCE.relative_to(ROOT)),
        'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'waist_anchor': 'mixamorig:Spine', 'anchor_fade_z': [-.16, -.10],
        'clearance_fade_z': [-.18, -.10],
        'changed_weight_vertices': changed, 'maximum_inset_m': clearance,
        'new_key': KEY, 'key_ranges': ranges, 'unresolved_authoring_samples':unresolved,
        'scope': 'Shorts waist weights and one new shorts-only morph channel. '
                 'All rest coordinates, existing morphs, shirt, body, rig and existing action curves preserved.'}
    (OUT / 'fitting.json').write_text(json.dumps(report, indent=2)+'\n')
    print('WAIST_NATIVE_READY', json.dumps(ranges), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-export', action='store_true')
    parser.add_argument('--export-only', action='store_true')
    parser.add_argument('--clearance', type=float, default=.012)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    OUT.mkdir(exist_ok=True)
    (OUT / 'items').mkdir(exist_ok=True)
    (OUT / '.gitignore').write_text('diagnostics/\n*.blend1\n')
    if args.export_only:
        bpy.ops.wm.open_mainfile(filepath=str(OUT / 'WarmOriginal-Outfit-r07.blend'))
    else:
        build(args.clearance)
    if not args.no_export:
        export_current()
        print('WAIST_EXPORT_READY', flush=True)
