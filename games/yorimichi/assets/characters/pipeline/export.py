"""Export a character's body for Unreal: its skinned meshes, textures, authored clips and export.json.

    blender -b --python games/yorimichi/assets/characters/pipeline/export.py -- --character nox [--clips A,B] [--clips-only]

Writes build/yorimichi/<id>/: fbx/<Asset>.fbx, fbx/A_<Clip>.fbx (the source's own clips, when character.toml
[export] actions = "authored"), textures/ and export.json, which Scripts/import_character.py reads. A character's
folder may add an `export_hooks.py` with `body(prepared, report)`: work its source alone needs (a coat's cloth mask,
corrective shapes) before the body FBX is written, recorded in the report.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rig  # noqa: E402
from atelier.character.names import slug  # noqa: E402


def hooks(character):
    path = character.definition.folder / 'export_hooks.py'
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(character.id.replace('-', '_') + '_export_hooks', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def texture_of(c, material, out, name):
    """The base colour texture written to textures/, or None for a plain colour."""
    settings = c.materials
    shader = next(n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    color = shader.inputs['Base Color']
    if not color.is_linked:
        assert not settings['require_texture'], (c.id, material.name, 'no base colour texture')
        return shader, color, None
    node = color.links[0].from_node
    assert node.type == 'TEX_IMAGE', (c.id, material.name, 'unsupported base colour graph', node.type)
    image = node.image
    if settings['atlas']:
        assert tuple(image.size[:]) == (settings['atlas'], settings['atlas']), (c.id, image.name, 'atlas size', image.size[:])
    data = image.packed_file.data if image.packed_file else None
    jpeg = settings['format'] == 'detect' and data and data[:3] == b'\xff\xd8\xff'
    target = out / 'textures' / (name + ('.jpg' if jpeg else '.png'))
    if data:
        target.write_bytes(data)
    else:
        image.save_render(str(target))
    return shader, color, str(target.relative_to(out))


def materials(c, prepared, out):
    """Every body material renamed by [export.materials] name, with its texture, surface and meshes: {name: record}."""
    settings = c.materials
    found = {}
    for obj in prepared.meshes:
        for material in obj.data.materials:
            if material.name in found:
                found[material.name]['meshes'].append(obj.name)
                continue
            old = material.name
            fields = dict(asset=c.name, mesh=obj.name, material=old, source=slug(old))
            material.name = settings['name'].format(**fields)
            shader, color, texture = texture_of(c, material, out, settings['texture'].format(**fields))
            sided = settings['two_sided']
            two_sided = (not material.use_backface_culling if sided == 'backface' else
                         obj.name[len(c.name) + 1:] in sided if isinstance(sided, list) else bool(sided))
            surface = {key: float(shader.inputs[socket].default_value) if settings[key] == 'shader' else float(settings[key])
                       for key, socket in (('roughness', 'Roughness'), ('metallic', 'Metallic'), ('specular', 'Specular IOR Level'))}
            found[material.name] = {'source_name': old, 'base_color': list(color.default_value), 'texture': texture,
                                    'two_sided': two_sided, **surface, 'meshes': [obj.name]}
    return found


def rest(prepared):
    """The body in its rest pose, every shape key at zero and no clip playing."""
    arm = prepared.arm
    if arm.animation_data:
        arm.animation_data.action = None
    arm.data.pose_position = 'REST'
    for obj in prepared.meshes:
        keys = obj.data.shape_keys
        if keys:
            if keys.animation_data:
                keys.animation_data.action = None
            for key in keys.key_blocks[1:]:
                key.value = 0


def clips(c, prepared, out, wanted):
    """The source's own clips (the manifest's roles, one clip per action, and [export] clips) as A_<Clip>.fbx, with
    each frame's shape key values where the body has shape keys."""
    record, scene, arm, meshes = prepared.record, prepared.scene, prepared.arm, prepared.meshes
    roles = record.get('roles', [])
    by_action = {}
    for role in roles:
        by_action.setdefault(role['clip'], role['role'])
    by_action.update(c.export['clips'])
    keyed = [o for o in meshes if o.data.shape_keys]
    result = {}
    for action_name, name in by_action.items():
        if wanted and name not in wanted:
            continue
        action = bpy.data.actions[action_name]
        rig.set_clip(arm, action)
        scene.frame_start, scene.frame_end = map(int, action.frame_range)
        scene.frame_set(scene.frame_start)
        rig.select([arm, *keyed], arm, reveal=True)
        rows = [r for r in roles if r['clip'] == action_name]
        sample_rate = max((r.get('export_sample_rate', c.fps) for r in rows), default=c.fps)
        from atelier.blender.fbx import export_fbx as export_scene_fbx
        export_scene_fbx(filepath=str(out / 'fbx' / ('A_' + name + '.fbx')), object_types={'ARMATURE', 'MESH'},
                                 bake_anim=True, **dict(rig.FBX, bake_anim_step=c.fps / sample_rate))
        entry = {'action': action_name, 'frames': scene.frame_end - scene.frame_start + 1, 'fps': c.fps,
                 'duration': (scene.frame_end - scene.frame_start) / c.fps, 'sample_rate': sample_rate,
                 'root_motion': any('root bone' in str(r.get('root_motion', '')) for r in rows),
                 'loop': any(r.get('loop') for r in rows)}
        if keyed:
            expected = {k.name: [] for o in keyed for k in o.data.shape_keys.key_blocks[1:]}
            for frame in range(scene.frame_start, scene.frame_end + 1):
                scene.frame_set(frame)
                for obj in keyed:
                    for key in obj.data.shape_keys.key_blocks[1:]:
                        expected[key.name].append(round(float(key.value), 7))
            entry['expected_morph_curves'] = expected
        result[name] = entry
        print('UNREAL_CLIP_EXPORTED', name, flush=True)
    return result


def main(args):
    character = rig.load(args.character)
    c = character.definition
    out = character.OUT
    (out / 'fbx').mkdir(parents=True, exist_ok=True)
    (out / 'textures').mkdir(exist_ok=True)
    prepared = character.prepare(Path(args.revision).resolve() if args.revision else None)
    arm, meshes = prepared.arm, prepared.meshes
    feet = {side: list(arm.matrix_world @ arm.data.bones['foot_' + side].head_local) for side in 'LR'}
    report = {'source': prepared.native.name, 'source_sha256': prepared.record['native_sha256'], 'model_scale': prepared.scale,
              'height_cm': c.toml['height_cm'], 'sole_cm': rig.SOLE * 100, 'source_floor': prepared.floor, 'facing': '+X',
              'rest_ankles_cm': {side: p[2] * 100 for side, p in feet.items()}, 'bones': prepared.original_names,
              'parents': {b.name: b.parent.name if b.parent else None for b in arm.data.bones},
              'materials': materials(c, prepared, out)}
    if prepared.secondary_bones:
        report['secondary_bones'] = sorted(prepared.secondary_bones)
    if prepared.dropped:
        report['dropped_bones'] = prepared.dropped
    if prepared.rest_roundtrip:
        report['rest_roundtrip'] = prepared.rest_roundtrip
    if prepared.morphs:
        report['morphs'] = prepared.morphs
    if prepared.record.get('roles'):
        report['roles'] = prepared.record['roles']
    if c.export['meshes'] == 'outfit':
        report['excluded_geometry'] = 'Preserved fitting body and body regions hidden by the equipped outfit.'
    extra = hooks(character)
    if extra and hasattr(extra, 'body'):
        extra.body(prepared, report)
    report['meshes'] = {o.name: len(o.data.vertices) for o in meshes}
    if not args.clips_only:
        rest(prepared)
        rig.select([arm, *meshes], arm, reveal=True)
        from atelier.blender.fbx import export_fbx as export_scene_fbx
        export_scene_fbx(filepath=str(out / 'fbx' / (c.name + '.fbx')), object_types={'ARMATURE', 'MESH'}, bake_anim=False,
                                 **dict(rig.FBX, **c.export['fbx']))
        arm.data.pose_position = 'POSE'
    # The donor's default is the clips the merged move set takes from it (adventure.toml [donor]); otherwise all of them.
    wanted = args.clips.split(',') if args.clips else c.donor and c.donor['clips'] + c.donor['gestures']
    report['clips'] = clips(c, prepared, out, set(wanted or ())) if c.export['actions'] == 'authored' else {}
    (out / (args.report or 'export.json')).write_text(json.dumps(report, indent=2) + '\n')
    print(c.name.upper(), 'EXPORT READY', json.dumps({k: report[k] for k in ('height_cm', 'rest_ankles_cm', 'meshes')}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--character', required=True)
    parser.add_argument('--clips', help="Only these of its own clips (comma-separated); the donor's default is its [donor] clips")
    parser.add_argument('--clips-only', action='store_true', help='Skip the body FBX')
    parser.add_argument('--revision', help='Folder of another revision (from the archive); default is its own folder')
    parser.add_argument('--report', help='Write export.json under this name instead (a partial export keeps the full record)')
    main(parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []))
