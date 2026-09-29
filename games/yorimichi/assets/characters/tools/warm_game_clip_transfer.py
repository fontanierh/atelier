"""Re-author library clips from `warm_clips` and carry their bone curves onto a later game revision.

    blender -b --threads 4 --python-exit-code 1 --python games/yorimichi/assets/characters/tools/warm_game_clip_transfer.py -- \
        --base game-r10 --parent game-r13 --revision game-r14 --clips Walk,CrouchWalk [--legacy key=value,...]

The library clips were authored on `game-r10` (r07 outfit, whose shoe soles fix the floor contacts); the
skate body swap (`game-r11`) and every later revision play those bone curves unchanged. So a change to a
pose function in `warm_clips.py` is authored on the base exactly as `warm_game_revision.author` would, and
only the armature channel bag of the matching `<Clip> · library` action is replaced in the parent. The
garment key bags of the old outfit, every other action, the meshes, weights and the rig are untouched.

`--legacy` first re-authors each clip with the given config overrides and asserts that the result equals
the base's existing curves: proof that this route reproduces the original authoring before anything new is
written. The new revision's evaluated pose is then compared bone by bone with the pose on the base.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
from pathlib import Path
import argparse
import hashlib
import json
import math
import sys
import bpy
from mathutils import Quaternion

# ROOT (the archive) comes from _archive
ASSET = ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12'
sys.path.insert(0, str(TOOLS))
import warm_clips
from warm_rig import Rig
from warm_outfit_correctives import set_clip
from prepare_warm_original_game import action_signature

OB_SLOT = 'OBWarm Original · Tripo body rig'


def open_revision(rev):
    blend = ASSET / rev / f'WarmOriginal-{rev.replace("game-", "Game-")}.blend'
    record = json.loads((blend.parent / 'source-manifest.json').read_text())
    sha = hashlib.sha256(blend.read_bytes()).hexdigest()
    assert sha == record['native_sha256'], (rev, 'blend does not match its source manifest')
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    return blend, record, sha


def armature():
    return next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')


def ob_bag(action):
    slot = next(s for s in action.slots if s.identifier == OB_SLOT)
    return action.layers[0].strips[0].channelbag(slot)


def channels(action):
    """{(data_path, index): (group, [value per keyframe])} of the armature bag, keyed on whole frames."""
    out = {}
    for fc in ob_bag(action).fcurves:
        frames = [p.co.x for p in fc.keyframe_points]
        assert frames == [float(f) for f in range(1, len(frames) + 1)], (action.name, fc.data_path)
        out[(fc.data_path, fc.array_index)] = (fc.group.name if fc.group else None, [p.co.y for p in fc.keyframe_points])
    return out


def pose_function(name, overrides):
    clip = warm_clips.CLIPS[name]
    if not overrides:
        return clip.pose
    cfg = {'Walk': warm_clips.WALK, 'CrouchWalk': warm_clips.CROUCH_WALK}[name]
    cfg = {**cfg, **overrides}
    return lambda rig, t: clip.pose(rig, t, cfg)


def author(rig, arm, name, overrides=None):
    """Author one clip into a scratch action with the library's keying; return its channels and contact samples."""
    clip = warm_clips.CLIPS[name]
    action = bpy.data.actions.new('scratch · ' + name)
    slot = action.slots.new(id_type='OBJECT', name='Warm Original · Tripo body rig')
    arm.animation_data.action = action
    arm.animation_data.action_slot = slot
    pose, last, samples = pose_function(name, overrides), {}, []
    for frame in range(1, clip.frames + 1):
        rig.begin(); info = pose(rig, (frame - 1) / warm_clips.FPS) or {}
        rig.apply(); rig.key(frame, last)
        samples.append({'frame': frame, 'left_sole_z': rig.sole_low('Left').z - rig.floor,
                        'right_sole_z': rig.sole_low('Right').z - rig.floor,
                        'left_planted': bool(info.get('left_planted')), 'right_planted': bool(info.get('right_planted')),
                        'hips_z': rig.head('Hips').z, 'quats': {n: list(m.to_quaternion()) for n, m in rig.M.items()}})
    result = channels(action)
    return action, result, samples


def compare(a, b):
    assert set(a) == set(b), ('channel sets differ', sorted(set(a) ^ set(b)))
    return max(abs(x - y) for key in a for x, y in zip(a[key][1], b[key][1], strict=True))


def evaluated_pose(arm, action, frames):
    set_clip(arm, action)
    table = []
    for frame in frames:
        bpy.context.scene.frame_set(frame)
        table.append({pb.name: [list(r) for r in pb.matrix] for pb in arm.pose.bones})
    return table


def contact_report(samples):
    def angle(q0, q1):
        d = abs(Quaternion(q0).dot(Quaternion(q1)))
        return math.degrees(2 * math.acos(min(1., d)))
    steps = [angle(a['quats'][n], b['quats'][n]) for a, b in zip(samples, samples[1:]) for n in a['quats']]
    planted = [s[f'{side}_sole_z'] for s in samples for side in ('left', 'right') if s[f'{side}_planted']]
    hips = [s['hips_z'] for s in samples]
    low = min(range(len(hips)), key=hips.__getitem__)
    return {'max_joint_step_degrees': round(max(steps), 3),
            'max_ground_penetration': round(-min(min(s['left_sole_z'], s['right_sole_z']) for s in samples), 6),
            'max_planted_hover': round(max(planted, default=0.), 6),
            'hips_range': round(max(hips) - min(hips), 5), 'hips_lowest_frame': samples[low]['frame']}


def main(args):
    names = args.clips.split(',')
    legacy = {k: float(v) for k, v in (kv.split('=') for kv in args.legacy.split(','))} if args.legacy else None

    # ---- author on the base
    base_blend, base_record, base_sha = open_revision(args.base)
    scene, arm = bpy.context.scene, armature()
    items = {o['outfit_slot']: o for o in scene.objects if o.get('outfit_slot')}
    set_clip(arm, bpy.data.actions['Standing · outfit review']); scene.frame_set(1)
    shoes = items['shoes']
    ev = shoes.evaluated_get(bpy.context.evaluated_depsgraph_get())
    rig = Rig(arm, scene, shoes, min((ev.matrix_world @ v.co).z for v in ev.data.vertices))
    for o in scene.objects:
        if o.type == 'MESH': o.hide_viewport = True
    report = {'base': str(base_blend.relative_to(ROOT)), 'base_sha256': base_sha, 'clips': {}}
    authored, base_pose = {}, {}
    for name in names:
        library = bpy.data.actions[name + ' · library']
        before = channels(library)
        entry = report['clips'][name] = {'frames': warm_clips.CLIPS[name].frames}
        if legacy:
            scratch, old, old_samples = author(rig, arm, name, legacy)
            entry['legacy_overrides'] = legacy
            entry['legacy_max_abs_difference'] = compare(old, before)
            entry['legacy_contacts'] = contact_report(old_samples)
            assert entry['legacy_max_abs_difference'] < 1e-5, (name, 'legacy authoring does not reproduce the base', entry)
            bpy.data.actions.remove(scratch)
        scratch, new, samples = author(rig, arm, name)
        entry['contacts'] = contact_report(samples)
        entry['max_abs_change_from_base'] = compare(new, before)
        authored[name] = new
        frames = list(range(1, warm_clips.CLIPS[name].frames + 1))
        base_pose[name] = evaluated_pose(arm, scratch, frames)
        print('AUTHORED', name, json.dumps(entry), flush=True)

    # ---- replace the armature bag in the parent
    parent_blend, record, parent_sha = open_revision(args.parent)
    arm = armature()
    untouched = {k: v for k, v in action_signature(bpy.data.actions).items() if k not in {n + ' · library' for n in names}}
    meshes = {o.name: hashlib.sha256(b''.join(v.co[:].__repr__().encode() for v in o.data.vertices)).hexdigest()
              for o in bpy.context.scene.objects if o.type == 'MESH'}
    for name in names:
        action = bpy.data.actions[name + ' · library']
        bag = ob_bag(action)
        for fc in list(bag.fcurves): bag.fcurves.remove(fc)
        groups = {}
        for (path, index), (group, values) in sorted(authored[name].items()):
            fc = bag.fcurves.new(path, index=index)
            if group:
                if group not in groups: groups[group] = bag.groups.get(group) or bag.groups.new(group)
                fc.group = groups[group]
            fc.keyframe_points.add(len(values))
            fc.keyframe_points.foreach_set('co', [c for f, v in enumerate(values, 1) for c in (float(f), v)])
            for p in fc.keyframe_points: p.interpolation = 'LINEAR'
            if warm_clips.CLIPS[name].loop: fc.modifiers.new('CYCLES')
            fc.update()
        assert compare(channels(action), authored[name]) == 0.
        frames = list(range(1, warm_clips.CLIPS[name].frames + 1))
        error = max(abs(x - y) for a, b in zip(evaluated_pose(arm, action, frames), base_pose[name])
                    for bone in a for ra, rb in zip(a[bone], b[bone]) for x, y in zip(ra, rb))
        report['clips'][name]['max_pose_matrix_difference_vs_base'] = error
        assert error < 1e-4, (name, 'pose on the new revision differs from the base', error)
    assert untouched == {k: v for k, v in action_signature(bpy.data.actions).items() if k in untouched}, 'other actions changed'
    assert meshes == {o.name: hashlib.sha256(b''.join(v.co[:].__repr__().encode() for v in o.data.vertices)).hexdigest()
                      for o in bpy.context.scene.objects if o.type == 'MESH'}, 'meshes changed'
    set_clip(arm, bpy.data.actions['Idle · library']); bpy.context.scene.frame_set(1)

    out = ASSET / args.revision; out.mkdir(exist_ok=True)
    (out / '.gitignore').write_text('diagnostics/\n*.blend1\n')
    native = out / f'WarmOriginal-{args.revision.replace("game-", "Game-")}.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(native))
    for role in record['roles']:
        if role['role'] in names:
            role.setdefault('history', []).append({'revision': args.parent, 'validation': role.pop('validation', None)})
            role['validation'] = {**report['clips'][role['role']]['contacts'], 'record': 'clip-transfer.json'}
    record.update(native=str(native.relative_to(ROOT)), native_sha256=hashlib.sha256(native.read_bytes()).hexdigest(),
                  parent_source=str(parent_blend.relative_to(ROOT)), parent_sha256=parent_sha, revision=args.revision,
                  changed_actions=[n + ' · library' for n in names], other_parent_actions_preserved=True,
                  note=f'{args.revision}: {args.parent} with {", ".join(names)} re-authored from warm_clips.py on {args.base} '
                       '(armature curves only). Meshes, weights, rig, sword and every other clip unchanged.')
    (out / 'source-manifest.json').write_text(json.dumps(record, indent=2) + '\n')
    report.update(parent=str(parent_blend.relative_to(ROOT)), parent_sha256=parent_sha, revision=args.revision,
                  native=record['native'], native_sha256=record['native_sha256'], unchanged_actions=len(untouched))
    (out / 'clip-transfer.json').write_text(json.dumps(report, indent=2) + '\n')
    print('CLIP_TRANSFER_READY', args.revision, flush=True)


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='game-r10')
    parser.add_argument('--parent', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--clips', required=True)
    parser.add_argument('--legacy', help='config overrides that must reproduce the base curves, e.g. bob_low=0,arm_peak=0.5')
    main(parser.parse_args(argv))
