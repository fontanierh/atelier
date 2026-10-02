"""Measure the imported Ride clips against the native data: build/yorimichi/skate-ride/clips-verify.json.

For every clip in Content/Data/SkateRide/clips.json, every frame and every bone, the pose Unreal samples from the
asset's compressed data (UAnimPoseExtensions, EvaluationType Compressed, retargeting left on so the compressed path is
really taken, root motion kept in the root bone) is compared with the native local pose (native.local_pose: the clip
sample, rotation normalised as the native sampler does, added onto RIG_TPOSE as the runtime's BindPose tree does)
converted to Unreal space. The errors are the translation distance (cm), the rotation angle
(rad) and the largest scale component difference, reported per clip and overall. The curves are checked at every
frame against the attribute values they encode.

A control proves the compressed path is measured: a copy of one clip under the engine's default bone compression must
show a non-zero error. The poses of the still clips (import_clips.STILLS) are written in component space to
build/yorimichi/skate-ride/still-poses/ for render_stills.py.

Batched like the import (SKATE_RIDE_VERIFY_BATCH=i/n, default 1/1); the run that finds every clip measured writes
clips-verify.json.
"""
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'world'))
sys.path.insert(0, str(HERE))
import yori  # noqa: E402
import native as N  # noqa: E402
import unreal as U  # noqa: E402

CONTENT = HERE.parents[1] / 'Content'
BUNDLE = CONTENT / 'Data' / 'SkateNative'
MANIFEST = CONTENT / 'Data' / 'SkateRide' / 'clips.json'
OUT = yori.OUT / 'skate-ride'
STATE = OUT / 'verify-state.json'
POSES = OUT / 'still-poses'
STILLS = ('OLLIE_HIGH_G', 'PRO_MCARROLL_KICKFLIP_HI_CYC', 'PRO_DYRDEK_PUSH_HSPD_HSTR_CYC2', 'G_5050_FS_HI_0_CYC')
CONTROL = 'R_HIGHANTIC_FS360SHUVIT_L_0_CYC'
LIMITS = dict(translation_cm=0.01, rotation_rad=1e-4, scale=1e-4)
E = U.EditorAssetLibrary
P = U.AnimPoseExtensions


def log(text):
    U.log(f'SKATE RIDE VERIFY {text}')


def finish_compilation():
    library = getattr(U, 'AutomationLibrary', None) or getattr(U, 'AutomationBlueprintFunctionLibrary')
    library.finish_loading_before_screenshot()


def options(kind=U.AnimDataEvalType.COMPRESSED):
    o = U.AnimPoseEvaluationOptions()
    o.set_editor_property('evaluation_type', kind)
    o.set_editor_property('should_retarget', True)              # False would silently sample the raw data
    o.set_editor_property('extract_root_motion', False)
    o.set_editor_property('incorporate_root_motion_into_pose', True)   # keep TRAJECTORY's own motion
    o.set_editor_property('evaluate_curves', True)
    return o


def sample_poses(sequence, fps, frames, kind=U.AnimDataEvalType.COMPRESSED):
    """The pose at every key (frame f at f / fps), sampled through UAnimPoseExtensions."""
    o = options(kind)
    if hasattr(P, 'get_anim_pose_at_time_intervals'):
        poses = P.get_anim_pose_at_time_intervals(sequence, [f / fps for f in range(frames)], o)
    else:
        poses = [P.get_anim_pose_at_frame(sequence, f, o) for f in range(frames)]
    assert len(poses) == frames, (sequence.get_name(), len(poses), frames)
    return poses


def curve_value(keys, t):
    value = keys[0][1]
    for kt, kv in keys:
        if kt <= t + 1e-6:
            value = kv
    return value


def measure(clip, rig, reference, poses):
    worst = dict(translation_cm=0.0, rotation_rad=0.0, scale=0.0)
    where = {}
    per_bone = {b.name: [0.0, 0.0] for b in rig.bones}
    for f, pose in enumerate(poses):
        for b, bone in enumerate(rig.bones):
            t, q, s = N.sample_to_unreal(N.local_pose(clip, f, b, reference))
            got = P.get_bone_pose(pose, bone.name, U.AnimPoseSpaces.LOCAL)
            gt, gq, gs = got.translation, got.rotation, got.scale3d
            errors = dict(translation_cm=math.dist((gt.x, gt.y, gt.z), t),
                          rotation_rad=N.quaternion_angle((gq.x, gq.y, gq.z, gq.w), q),
                          scale=max(abs(gs.x - s[0]), abs(gs.y - s[1]), abs(gs.z - s[2])))
            for k, v in errors.items():
                if v > worst[k]:
                    worst[k] = v
                    where[k] = dict(frame=f, bone=bone.name)
            pb = per_bone[bone.name]
            pb[0] = max(pb[0], errors['translation_cm'])
            pb[1] = max(pb[1], errors['rotation_rad'])
    return worst, where, per_bone


def control(rig, reference, bundle, manifest):
    """A copy of CONTROL under the engine's default bone compression, measured the same way: proves that the
    measurement reads compressed data (the copy must differ from the native pose; the exact clip must not)."""
    record = manifest['clips'].get(CONTROL)
    if not record:
        return None
    path = '/Game/SkateRideVerify/ControlDefaultCompression'
    if E.does_directory_exist('/Game/SkateRideVerify'):
        E.delete_directory('/Game/SkateRideVerify')
    copy = E.duplicate_asset(record['asset'], path)
    default = E.load_asset('/Engine/Animation/DefaultAnimBoneCompressionSettings')
    copy.set_editor_property('bone_compression_settings', default)
    finish_compilation()
    clip = bundle.clip(record['bank'], CONTROL)
    compressed = sample_poses(copy, clip.fps, clip.frame_count)
    worst, where, _ = measure(clip, rig, reference, compressed)
    raw = sample_poses(copy, clip.fps, clip.frame_count, U.AnimDataEvalType.RAW)
    raw_worst, _, _ = measure(clip, rig, reference, raw)
    E.delete_directory('/Game/SkateRideVerify')
    return dict(clip=CONTROL, compression=default.get_path_name(), compressed=worst, compressed_where=where, raw=raw_worst)


def check_curves(sequence, clip, record, poses):
    """The curve values at every frame against the step encoding of the attributes (import_clips.curve_keys)."""
    meta_events = record.get('events', [])
    if not meta_events:
        return 0.0, []
    grouped = {}
    for e in meta_events:
        grouped.setdefault(e['name'], []).append(e)
    worst, missing = 0.0, []
    for name, events in grouped.items():
        keys = step_keys(events, clip.duration, clip.fps)
        for f, pose in enumerate(poses):
            try:
                got = P.get_curve_weight(pose, name)
            except Exception:
                missing.append(name)
                break
            worst = max(worst, abs(got - curve_value(keys, f / clip.fps)))
    return worst, missing


def step_keys(events, duration, fps):
    """import_clips.curve_keys from the manifest's event records."""
    base, windows = 0.0, []
    for e in events:
        value = e.get('value') or 0.0
        if e['whole_clip']:
            base = value
        else:
            begin, end = e['begin_s'], e['end_s']
            windows.append((begin, max(end, min(begin + 1.0 / fps, duration)), value))
    if not windows:
        return [(0.0, base)]
    times = sorted({0.0, duration} | {t for w in windows for t in w[:2]})
    keys = []
    for t in times:
        value = base
        for begin, end, v in windows:
            if begin <= t < end or (t == end == duration and begin <= t):
                value = v
        if not keys or keys[-1][1] != value:
            keys.append((t, value))
    return keys


def dump_still(name, rig, poses, fps):
    POSES.mkdir(parents=True, exist_ok=True)
    frames = []
    for f, pose in enumerate(poses):
        bones = {}
        for bone in rig.bones:
            t = P.get_bone_pose(pose, bone.name, U.AnimPoseSpaces.WORLD)
            bones[bone.name] = dict(t=[t.translation.x, t.translation.y, t.translation.z],
                                    q=[t.rotation.x, t.rotation.y, t.rotation.z, t.rotation.w])
        frames.append(dict(frame=f, time=f / fps, bones=bones))
    (POSES / f'{name}.json').write_text(json.dumps(dict(clip=name, fps=fps, frames=frames)) + '\n')


def main():
    started = time.time()
    manifest_text = MANIFEST.read_text()
    manifest = json.loads(manifest_text)
    key = hashlib.sha256(manifest_text.encode()).hexdigest()
    bundle = N.Bundle(BUNDLE)
    rig = bundle.rig()
    reference = rig.named_pose(0, 'RIG_TPOSE')
    batch, batches = (int(v) for v in os.environ.get('SKATE_RIDE_VERIFY_BATCH', '1/1').split('/'))
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    if state.get('manifest') != key:
        state = dict(manifest=key, clips={}, control=None)
    names = sorted(manifest['clips'])
    share = [n for i, n in enumerate(names) if i * batches // len(names) == batch - 1]
    todo = [n for n in share if n not in state['clips']]
    log(f'batch {batch}/{batches}: {len(share)} clips, {len(todo)} to measure')
    if state.get('control') is None and CONTROL in todo:
        try:
            state['control'] = control(rig, reference, bundle, manifest)
        except Exception as error:
            state['control'] = dict(clip=CONTROL, error=str(error))
        log(f'control: {state["control"]}')
    for start in range(0, len(todo), 40):
        chunk = todo[start:start + 40]
        loaded = {n: E.load_asset(manifest['clips'][n]['asset']) for n in chunk}
        finish_compilation()
        for name, sequence in loaded.items():
            record = manifest['clips'][name]
            clip = bundle.clip(record['bank'], name)
            poses = sample_poses(sequence, clip.fps, clip.frame_count)
            worst, where, per_bone = measure(clip, rig, reference, poses)
            curve_error, missing = check_curves(sequence, clip, record, poses)
            state['clips'][name] = dict(frames=clip.frame_count, fps=clip.fps, **worst, where=where,
                                        curve_error=curve_error, curves_missing=sorted(set(missing)),
                                        bones={b: [round(v[0], 7), round(v[1], 8)] for b, v in per_bone.items()
                                               if v[0] > 1e-3 or v[1] > 1e-5})
            if name in STILLS:
                dump_still(name, rig, poses, clip.fps)
        U.SystemLibrary.collect_garbage()
        STATE.write_text(json.dumps(state) + '\n')
        log(f'{min(start + 40, len(todo))}/{len(todo)} clips, {time.time() - started:.0f} s')

    if all(n in state['clips'] for n in names):
        clips = state['clips']
        overall = {k: max(c[k] for c in clips.values()) for k in LIMITS}
        worst_clip = {k: max(clips, key=lambda n: clips[n][k]) for k in LIMITS}
        over = {k: sorted(n for n, c in clips.items() if c[k] > LIMITS[k]) for k in LIMITS}
        report = dict(
            about='Runtime-sampled (compressed) Unreal poses against the native decode in Unreal space, every clip, '
                  'frame and bone (unreal/Scripts/skate_ride/verify_clips.py)',
            clips=len(clips), frames=sum(c['frames'] for c in clips.values()), bones=len(rig.bones),
            limits=LIMITS, max=overall, worst_clip=worst_clip,
            passed=all(overall[k] <= LIMITS[k] for k in LIMITS), over_limit={k: v for k, v in over.items() if v},
            curve_max_error=max(c['curve_error'] for c in clips.values()),
            curves_missing=sorted({m for c in clips.values() for m in c['curves_missing']}),
            control=state.get('control'), partial=manifest.get('partial'),
            per_clip={n: {k: c[k] for k in ('frames', 'fps', 'translation_cm', 'rotation_rad', 'scale', 'curve_error',
                                            'where', 'bones')} for n, c in sorted(clips.items())})
        (OUT / 'clips-verify.json').write_text(json.dumps(report, indent=1) + '\n')
        log(f'REPORT max {overall}, passed={report["passed"]}, control={(report["control"] or {}).get("compressed")}')
    else:
        log(f'report not written yet: {sum(n in state["clips"] for n in names)}/{len(names)} clips measured')
    log(f'batch {batch}/{batches} took {time.time() - started:.0f} s')
    U.log('SKATE RIDE CLIPS VERIFY COMPLETE')


main()
