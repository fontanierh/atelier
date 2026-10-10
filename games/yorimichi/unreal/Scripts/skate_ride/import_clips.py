"""Import the skating animation (the assembled package's animation and metadata) into /Game/SkateRide.

* SK_SkateRider and SKEL_SkateRider: the simulation rig (36 bones, same names and hierarchy, TRAJECTORY at the root) in
  its RIG_TPOSE reference pose, with a plain box body and board (rider_mesh.py), imported from a GLB by Interchange.
* /Game/SkateRide/Clips/B<bank>/<CLIP>: one UAnimSequence per simulation clip, keyed one for one at the clip's own frame
  rate (every frame, every bone, converted to Unreal space by simulation.py), root motion from TRAJECTORY with the root
  locked to zero (the simulation runtime never composes the trajectory into its children either). The simulation clips are
  deltas on RIG_TPOSE (the runtime's BindPose tree adds every clip onto it); the keys are that sum, the simulation local
  pose (simulation.local_pose), so the sequences play as ordinary full-body animation on SK_SkateRider.
* A float curve per metadata attribute, named after it (see README.md for the encoding; the manifest has the exact
  windows and payloads).
* MDT_SkateRider: the simulation mirror partners as a mirror data table.
* Content/Data/SkateRide/clips.json: the manifest the Ride runtime reads (rig, reference pose, per clip the asset,
  timing, root and loop motion, channel weights, events and mirror information).

Compression is ACL Safe (full-precision rotations, translations and scales held to a 0.00001 cm error), so the
compressed pose is the keyed pose; verify_clips.py measures it. A key the sequence's control rig would read as the
reference pose (within its 1e-4 equality test, but not on it) carries a 0.0003 cm X offset so that it is kept
(simulation.snap_guard). SKATE_RIDE_LIMIT=<n> or SKATE_RIDE_CLIPS=<a,b,...>
import a subset (the manifest then says `partial`); SKATE_RIDE_BATCH=<i>/<n> runs one share of the clips per editor
start (the build step runs several, as a heavy step must fit between other jobs' turns on the render lock).
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
import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import simulation as N  # noqa: E402
import rider_mesh  # noqa: E402
import unreal as U  # noqa: E402

CONTENT = HERE.parents[1] / 'Content'
BUNDLE = yori.OUT / 'skate-simulation' / 'package'  # the skate.runtime build step assembles it
DATA = CONTENT / 'Data' / 'SkateRide'
OUT = yori.OUT / 'skate-ride'
DEST = '/Game/SkateRide'
CLIPS = f'{DEST}/Clips'
STILLS = ('OLLIE_HIGH_G', 'PRO_MCARROLL_KICKFLIP_HI_CYC', 'PRO_DYRDEK_PUSH_HSPD_HSTR_CYC2', 'G_5050_FS_HI_0_CYC')
CONTROL = 'R_HIGHANTIC_FS360SHUVIT_L_0_CYC'    # verify_clips.py's compression control
BOARD = ('SKATEBOARD_ROOT', 'TRUCK_FRONT', 'TRUCK_BACK', 'LEFT_WHEELFRONT', 'RIGHT_WHEELFRONT', 'LEFT_WHEELBACK',
         'RIGHT_WHEELBACK')
ACL_ERROR_CM = 0.00001
E = U.EditorAssetLibrary
AT = U.AssetToolsHelpers.get_asset_tools()
REGISTRY = U.AssetRegistryHelpers.get_asset_registry()


def log(text):
    U.log(f'SKATE RIDE {text}')


def enum(owner, *names):
    for name in names:
        if hasattr(owner, name):
            return getattr(owner, name)
    raise AttributeError(f'{owner} has none of {names}')


def set_any(obj, value, *names):
    """set_editor_property under the first name the object accepts (Python or C++ spelling)."""
    for name in names:
        try:
            obj.set_editor_property(name, value)
            return name
        except Exception:
            continue
    raise AttributeError(f'{obj.get_class().get_name()} accepts none of {names}')


def finish_compilation():
    """Finish every in-flight asset compilation (animation compression included): FAssetCompilingManager."""
    library = getattr(U, 'AutomationLibrary', None) or getattr(U, 'AutomationBlueprintFunctionLibrary')
    library.finish_loading_before_screenshot()


# ---------------------------------------------------------------- rig
def assets_in(folder):
    found = {}
    for data in REGISTRY.get_assets_by_path(folder, recursive=True):
        found.setdefault(str(data.asset_class_path.asset_name), []).append(str(data.package_name))
    return found


def create(name, folder, cls, factory):
    """A new asset at folder/name, deleting a leftover one first (a failed run can leave it on disk or loaded)."""
    path = f'{folder}/{name}'
    if E.does_asset_exist(path):
        E.delete_asset(path)
    asset = AT.create_asset(name, folder, cls, factory)
    if asset is None:
        existing = U.find_object(None, f'{path}.{name}') or E.load_asset(path)
        assert existing is not None and isinstance(existing, cls), ('cannot create', path)
        log(f'reusing {path} (could not be recreated)')
        asset = existing
    return asset


def rename(path, name):
    target = f'{path.rsplit("/", 1)[0]}/{name}'
    if path != target:
        assert E.rename_asset(path, target), ('rename failed', path, target)
    return target


def import_rider(rig, pose):
    glb = OUT / 'SK_SkateRider.glb'
    stats = rider_mesh.write_glb(glb, rig, pose, N.split_sample)
    generic = U.InterchangeGenericAssetsPipeline()
    mesh_pipeline = generic.get_editor_property('mesh_pipeline')
    for key, value in dict(import_static_meshes=False, import_skeletal_meshes=True, create_physics_asset=False,
                           import_morph_targets=False).items():
        mesh_pipeline.set_editor_property(key, value)
    generic.get_editor_property('animation_pipeline').set_editor_property('import_animations', False)
    stack = U.InterchangePipelineStackOverride()
    stack.add_pipeline(generic)
    stack.add_pipeline(U.InterchangeGLTFPipeline())
    task = U.AssetImportTask()
    for key, value in dict(filename=str(glb), destination_path=DEST, automated=True, replace_existing=True,
                           save=True, options=stack).items():
        task.set_editor_property(key, value)
    AT.import_asset_tasks([task])
    found = assets_in(DEST)
    assert len(found.get('SkeletalMesh', [])) == 1 and len(found.get('Skeleton', [])) == 1, found
    skeleton = E.load_asset(rename(found['Skeleton'][0], 'SKEL_SkateRider'))
    mesh = E.load_asset(rename(found['SkeletalMesh'][0], 'SK_SkateRider'))
    assert mesh.skeleton == skeleton
    E.save_loaded_asset(skeleton, False)
    E.save_loaded_asset(mesh, False)
    return mesh, skeleton, stats


def check_rider(rig, pose, mesh, skeleton):
    """The imported skeleton has the simulation names and parents, and its reference pose is RIG_TPOSE in Unreal space."""
    ref = U.AnimPoseExtensions.get_reference_pose(skeleton)
    names = [str(n) for n in U.AnimPoseExtensions.get_bone_names(ref)]
    assert sorted(names) == sorted(b.name for b in rig.bones), names
    parents = {}
    for b in rig.bones:
        parent = str(mesh.get_bone_parent(b.name)) if hasattr(mesh, 'get_bone_parent') else None
        parents[b.name] = parent
        expected = rig.bones[b.parent].name if b.parent >= 0 else 'None'
        assert parent in (None, expected), (b.name, parent, expected)
    worst_t = worst_r = 0.0
    for i, b in enumerate(rig.bones):
        t, q, s = N.sample_to_unreal(N.runtime_sample(N.split_sample(pose.samples[i])))
        got = U.AnimPoseExtensions.get_bone_pose(ref, b.name, U.AnimPoseSpaces.LOCAL)
        gt, gq = got.translation, got.rotation
        worst_t = max(worst_t, math.dist((gt.x, gt.y, gt.z), t))
        worst_r = max(worst_r, N.quaternion_angle((gq.x, gq.y, gq.z, gq.w), q))
    log(f'rider: {len(names)} bones, parents checked={all(p is not None for p in parents.values())}, '
        f'reference pose error {worst_t:.6f} cm {worst_r:.7f} rad')
    assert worst_t < 0.01 and worst_r < 1e-4, (worst_t, worst_r)
    return names, worst_t, worst_r


# ---------------------------------------------------------------- compression
def compression_assets():
    """ACL Safe: full-precision rotations (128-bit quaternions) and variable-rate translations and scales held to a
    0.00001 cm error, which keeps them raw wherever a lower rate would move a vertex more than that. (The custom
    codec's explicit formats are not reachable from Python: their enums are not exposed.)"""
    bone = create('ACL_SkateRideExact', DEST, U.AnimBoneCompressionSettings, U.AnimBoneCompressionSettingsFactory())
    codec_class = getattr(U, 'AnimBoneCompressionCodec_ACLSafe', None) or \
        U.load_class(None, '/Script/ACLPlugin.AnimBoneCompressionCodec_ACLSafe')
    codec = U.new_object(codec_class, outer=bone)
    set_any(codec, ACL_ERROR_CM, 'error_threshold', 'ErrorThreshold')
    bone.set_editor_property('codecs', [codec])
    try:
        set_any(bone, ACL_ERROR_CM, 'error_threshold', 'ErrorThreshold')
    except AttributeError:
        pass
    E.save_loaded_asset(bone, False)
    curve = create('CC_SkateRideExact', DEST, U.AnimCurveCompressionSettings, U.AnimCurveCompressionSettingsFactory())
    curve_codec = U.new_object(U.load_class(None, '/Script/Engine.AnimCurveCompressionCodec_CompressedRichCurve'),
                               outer=curve)
    set_any(curve_codec, 0.0, 'max_curve_error', 'MaxCurveError')
    set_any(curve, curve_codec, 'codec', 'Codec')
    E.save_loaded_asset(curve, False)
    return bone, curve


# ---------------------------------------------------------------- clips
def curve_keys(attributes, duration, fps):
    """Rich-curve keys (time, value) for the attributes sharing one name: a whole-clip attribute holds its value; a
    windowed one holds its value from begin to end (a zero-length window for one frame) and 0 outside."""
    base = 0.0
    windows = []
    for a in attributes:
        value = N.attribute_payload(a).get('value', 0.0)
        if a.begin == N.ALWAYS:
            base = value
        else:
            begin, end = a.begin * duration, a.end * duration
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


def attribute_record(a, duration, fps):
    payload = N.attribute_payload(a)
    record = dict(name=a.name, kind=a.type_id, value=payload.get('value'))
    if a.begin == N.ALWAYS:
        record.update(whole_clip=True)
    else:
        record.update(whole_clip=False, begin=a.begin, end=a.end, begin_s=a.begin * duration, end_s=a.end * duration,
                      begin_frame=a.begin * duration * fps, end_frame=a.end * duration * fps)
    if a.type_id == 3:
        record['words'] = [f'0x{w:08x}' for w in payload['words']]
    return record


def round_list(values, digits=6):
    return [round(v, digits) for v in values]


def set_default_frame_rate(fps):
    """The project's default animation frame rate, in this editor session only (the config file is not written). A
    new sequence takes it as its model rate and as its target sampling rate, which a script cannot set otherwise:
    with the target at the clip's own rate, compression keeps every key instead of resampling."""
    settings = U.get_default_object(U.AnimationSettings)
    rate = settings.get_editor_property('default_frame_rate')
    if (rate.numerator, rate.denominator) != (int(round(fps)), 1):
        settings.set_editor_property('default_frame_rate', U.FrameRate(int(round(fps)), 1),
                                     U.PropertyAccessChangeNotifyMode.NEVER)


def make_clip(clip, meta, rig, reference, skeleton, mesh, bone_settings, curve_settings, curve_id_maker):
    folder = f'{CLIPS}/B{clip.bank}'
    set_default_frame_rate(clip.fps)
    factory = U.AnimSequenceFactory()
    factory.set_editor_property('target_skeleton', skeleton)
    factory.set_editor_property('preview_skeletal_mesh', mesh)
    sequence = AT.create_asset(clip.name, folder, U.AnimSequence, factory)
    assert sequence, ('could not create', clip.name)
    try:
        target = sequence.get_editor_property('platform_target_frame_rate').get_editor_property('default')
        target = (target.numerator, target.denominator)
    except Exception as error:
        target = None
        log(f'cannot read the target frame rate: {error}')
    assert target in (None, (int(round(clip.fps)), 1)), (clip.name, 'target frame rate', target)
    sequence.set_editor_property('bone_compression_settings', bone_settings)
    sequence.set_editor_property('curve_compression_settings', curve_settings)
    for key, value in dict(enable_root_motion=True, root_motion_root_lock=U.RootMotionRootLock.ZERO,
                           force_root_lock=False).items():
        sequence.set_editor_property(key, value)
    for names in (('allow_frame_stripping', 'bAllowFrameStripping'), ('loop', 'bLoop')):
        try:
            set_any(sequence, False if 'strip' in names[0] else bool(meta and meta.looping), *names)
        except AttributeError:
            pass
    fps, frames, duration = clip.fps, clip.frame_count, clip.duration
    controller = sequence.get_editor_property('controller')
    controller.open_bracket('Skate Ride import', False)
    controller.set_frame_rate(U.FrameRate(int(round(fps)), 1), False)
    controller.set_number_of_frames(U.FrameNumber(frames - 1), False)
    guarded = 0
    for b, bone in enumerate(rig.bones):
        rest = N.sample_to_unreal(N.runtime_sample(N.split_sample(reference.samples[b])))
        positions, rotations, scales = [], [], []
        for f in range(frames):
            (t, q, s), moved = N.snap_guard(N.sample_to_unreal(N.local_pose(clip, f, b, reference)), rest)
            guarded += moved
            positions.append(U.Vector(*t))
            rotations.append(U.Quat(*q))
            scales.append(U.Vector(*s))
        controller.add_bone_curve(bone.name, False)
        assert controller.set_bone_track_keys(bone.name, positions, rotations, scales, False), (clip.name, bone.name)
    events = []
    if meta:
        grouped = {}
        for a in meta.attributes:
            grouped.setdefault(a.name, []).append(a)
            events.append(attribute_record(a, duration, fps))
        constant = U.RichCurveInterpMode.RCIM_CONSTANT
        for name, attributes in grouped.items():
            ident = curve_id_maker(name)
            controller.add_curve(ident, 4, False)
            keys = []
            for t, v in curve_keys(attributes, duration, fps):
                key = U.RichCurveKey()
                key.set_editor_property('time', t)
                key.set_editor_property('value', v)
                key.set_editor_property('interp_mode', constant)
                keys.append(key)
            controller.set_curve_keys(ident, keys, False)
    controller.close_bracket(False)
    length = sequence.get_play_length()
    assert abs(length - duration) < 1e-4, (clip.name, length, duration)
    return sequence, events, guarded


def curve_identifier_maker():
    """FAnimationCurveIdentifier for a float curve. Its fields are not editable from Python, so it is made by the
    SetCurveIdentifier script method (whose reference argument may come back as the return value) or, failing that,
    from text; either way the result is checked through its exported text."""
    float_type = enum(U.RawCurveTrackTypes, 'RCT_FLOAT', 'RCT_Float')

    def valid(ident, name):
        text = ident.export_text() if ident is not None else ''
        return f'CurveName="{name}"' in text and 'RCT_Float' in text

    def make(name):
        ident = U.AnimationCurveIdentifier()
        try:
            out = ident.set_curve_identifier(name, float_type)
            if isinstance(out, U.AnimationCurveIdentifier) and valid(out, name):
                return out
            if valid(ident, name):
                return ident
        except Exception as error:
            log(f'set_curve_identifier({name}) failed: {error}')
        ident = U.AnimationCurveIdentifier()
        ident.import_text(f'(CurveName="{name}",CurveType=RCT_Float)')
        if not valid(ident, name):
            raise RuntimeError(f'no curve identifier for {name}: {ident.export_text()}')
        return ident
    return make


def motion_record(clip, rig, reference):
    """Root (TRAJECTORY) motion and the simulation loop transform, in Unreal space, and where the board root and the hips
    sit relative to the root (their parent) at the first frame."""
    board, hips = (N.sample_to_unreal(N.local_pose(clip, 0, rig.index(b), reference))[0]
                   for b in ('SKATEBOARD_ROOT', 'HIPS'))
    first = N.sample_to_unreal(N.runtime_sample(clip.sample(0, 0)))
    last = N.sample_to_unreal(N.runtime_sample(clip.sample(clip.frame_count - 1, 0)))
    loop_t = N.translation_to_unreal([N.as_float(w) for w in clip.loop_translation])
    loop_q = N.rotation_to_unreal([N.as_float(w) for w in clip.loop_rotation])
    travel = [b - a for a, b in zip(first[0], last[0])]
    return dict(
        root_bone='TRAJECTORY', root_lock='zero',
        first=dict(translation_cm=round_list(first[0], 4), rotation=round_list(first[1], 7)),
        last=dict(translation_cm=round_list(last[0], 4), rotation=round_list(last[1], 7)),
        travel_cm=round_list(travel, 4), travel_yaw_deg=round(math.degrees(2 * math.atan2(last[1][2], last[1][3])) -
                                                                math.degrees(2 * math.atan2(first[1][2], first[1][3])), 4),
        loop_translation_cm=round_list(loop_t, 4), loop_rotation=round_list(loop_q, 7),
        loop_vs_travel_cm=round(math.dist(loop_t, travel), 4),
        board_root_first_cm=round_list(board, 4), hips_first_cm=round_list(hips, 4))


def channel_record(clip, rig):
    weights = [N.as_float(w) for w in clip.channel_weights]
    distinct = sorted(set(weights))
    return dict(animated=clip.channel_animation, uniform=len(distinct) == 1, distinct=distinct,
                per_bone={b.name: w for b, w in zip(rig.bones, weights)})


def mirror_rows(rig):
    """Every bone the simulation rig mirrors, the centre bones onto themselves: Unreal leaves a bone without a row
    unmirrored (UMirrorDataTable::FillMirrorBoneIndexes), as the engine's own table factory does for unmatched names."""
    return [dict(Name=b.name, MirroredName=rig.bones[b.mirror].name, MirrorEntryType='Bone', bEnabled=True)
            for b in rig.bones if b.mirror >= 0]


def mirror_table(rig, skeleton):
    """MDT_SkateRider. The mirror table factory's skeleton and row struct are not settable from Python, so the table
    is made in the transient package, filled from JSON with the row struct given explicitly (which recreates it as a
    mirror table with that struct), given the skeleton and axis Y, and duplicated into DEST as an asset. Returns
    (path or None, row count, rows, axis); on failure the manifest still has the partners (rig.mirror)."""
    rows = mirror_rows(rig)
    try:
        row_struct = getattr(U, 'MirrorTableRow', None)
        row_struct = row_struct.static_struct() if row_struct else U.load_object(None, '/Script/Engine.MirrorTableRow')
        template = U.new_object(U.MirrorDataTable, name='MDT_SkateRiderTemplate')     # in the transient package
        outer = template.get_outer()
        filled = U.DataTableFunctionLibrary.fill_data_table_from_json_string(template, json.dumps(rows), row_struct)
        template = U.find_object(outer, 'MDT_SkateRiderTemplate') or template
        assert filled and isinstance(template, U.MirrorDataTable), ('mirror table fill', filled, template)
        template.set_editor_property('skeleton', skeleton)
        axis_text = None
        try:                # EAxis::Type is not a reflected enum; take the member from the property's current value
            axis_type = type(template.get_editor_property('mirror_axis'))
            axis = getattr(axis_type, 'Y', None) or getattr(axis_type, 'AXIS_Y', None) or axis_type(2)
            template.set_editor_property('mirror_axis', axis)
            axis = template.get_editor_property('mirror_axis')
            axis_text = getattr(axis, 'name', str(axis))     # 'Y'
        except Exception as error:
            log(f'mirror table: cannot set the axis to Y: {error}')
        if E.does_asset_exist(f'{DEST}/MDT_SkateRider'):
            E.delete_asset(f'{DEST}/MDT_SkateRider')
        table = AT.duplicate_asset('MDT_SkateRider', DEST, template)
        assert table is not None, 'mirror table duplicate'
        E.save_loaded_asset(table, False)
        count = len(table.get_row_names())
        log(f'mirror table: {count} rows, axis {axis_text}, skeleton {table.get_editor_property("skeleton")}')
        return table.get_path_name().split('.')[0], count, rows, axis_text
    except Exception as error:
        log(f'mirror table not made: {error}')
        return None, 0, rows, None


# ---------------------------------------------------------------- main
STATE = OUT / 'import-state.json'


def fingerprint():
    """What the imported assets depend on: the code of these scripts (not their comments or docstrings, see
    `simulation.source_digest`) and the simulation animation files."""
    digest = hashlib.sha256()
    for path in [HERE / 'import_clips.py', HERE / 'simulation.py', HERE / 'rider_mesh.py']:
        digest.update(path.name.encode())
        digest.update(N.source_digest(path).encode())
    for path in [*sorted((BUNDLE / 'animation').rglob('*.skate')), *sorted((BUNDLE / 'metadata').glob('*.skate'))]:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def selected_paths(bundle):
    paths = bundle.clip_paths()
    only = [n for n in os.environ.get('SKATE_RIDE_CLIPS', '').split(',') if n]
    limit = int(os.environ.get('SKATE_RIDE_LIMIT', '0') or 0)
    if only:
        paths = [p for p in paths if p.stem in only]
    if limit:       # the still clips and the control first, then a spread over both banks
        first = [p for p in paths if p.stem in STILLS + (CONTROL,)]
        others = [p for p in paths if p not in first]
        room = max(0, limit - len(first))
        paths = first + (others[::max(1, len(others) // room)][:room] if room else [])
    return paths, bool(only or limit)


def setup(rig, pose, key):
    """Rebuild /Game/SkateRide from scratch: the rider, the compression settings and the mirror table."""
    if E.does_directory_exist(DEST):
        E.delete_directory(DEST)
    E.make_directory(DEST)
    mesh, skeleton, mesh_stats = import_rider(rig, pose)
    unreal_order, ref_t, ref_r = check_rider(rig, pose, mesh, skeleton)
    bone_settings, curve_settings = compression_assets()
    mirror_path, mirror_ok, mirror_rows, mirror_axis = mirror_table(rig, skeleton)
    (OUT / 'mirror-rows.json').write_text(json.dumps(mirror_rows, indent=1) + '\n')
    reference = []
    for i, b in enumerate(rig.bones):
        t, q, s = N.sample_to_unreal(N.runtime_sample(N.split_sample(pose.samples[i])))
        reference.append(dict(bone=b.name, translation_cm=round_list(t), rotation=round_list(q, 8), scale=round_list(s)))
    head = dict(
        skeleton=skeleton.get_path_name().split('.')[0], mesh=mesh.get_path_name().split('.')[0],
        mirror_table=mirror_path, mirror_table_rows=mirror_ok, mirror_axis=mirror_axis,
        compression=dict(bone=bone_settings.get_path_name().split('.')[0], codec='ACL safe: full-precision rotations, variable-rate vectors',
                         error_threshold_cm=ACL_ERROR_CM, curves=curve_settings.get_path_name().split('.')[0]),
        space='Unreal: cm, X forward, Y right, Z up; simulation (x, y, z) m -> (z, -x, y) * 100, rotation (-z, x, -y, w)',
        keys='every frame and bone: the simulation local pose, the clip sample (rotation normalised) added onto RIG_TPOSE '
             '(AddAnimationPose motion_is_a: scale ref.s*s, rotation ref.q*q, translation ref.q(t)+ref.t), rotation '
             'normalised; no posture pose (POSTURE_*) and no BOARD_BACKWARDS layer, which the simulation runtime adds '
             'only when asked; a key within the control rig\'s 1e-4 equality of the reference pose but not on it is '
             f'moved {N.SNAP_GUARD_CM} cm along X so the sequence keeps it (simulation.snap_guard; per clip '
             'snap_guarded_keys)',
        rig=dict(bones=[b.name for b in rig.bones], parents=[b.parent for b in rig.bones],
                 parent_names=[rig.bones[b.parent].name if b.parent >= 0 else None for b in rig.bones],
                 mirror=[b.mirror for b in rig.bones], board_bones=list(BOARD), root='TRAJECTORY',
                 unreal_bone_order=unreal_order, reference_pose='RIG_TPOSE', reference=reference,
                 reference_error=dict(translation_cm=ref_t, rotation_rad=ref_r)),
        mesh_stats=mesh_stats)
    return dict(fingerprint=key, head=head, clips={})


def main():
    """One batch (SKATE_RIDE_BATCH=i/n, default 1/1) of the import. The first batch to find the state stale rebuilds
    /Game/SkateRide; every batch imports its share of the clips not yet imported, and whichever run finds every clip
    imported writes the manifest. A failed or interrupted run is resumed by running the step again."""
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    bundle = N.Bundle(BUNDLE)
    rig = bundle.rig()
    pose = rig.named_pose(0, 'RIG_TPOSE')
    paths, partial = selected_paths(bundle)
    key = fingerprint() + (f':{len(paths)}' if partial else '')
    batch, batches = (int(v) for v in os.environ.get('SKATE_RIDE_BATCH', '1/1').split('/'))
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    if state.get('fingerprint') != key or not E.does_asset_exist(f'{DEST}/SKEL_SkateRider'):
        state = setup(rig, pose, key)
        STATE.write_text(json.dumps(state) + '\n')
    head = state['head']
    skeleton, mesh = E.load_asset(head['skeleton']), E.load_asset(head['mesh'])
    bone_settings, curve_settings = E.load_asset(head['compression']['bone']), E.load_asset(head['compression']['curves'])
    curve_id = curve_identifier_maker()
    metadata = {c.name: c for bank in bundle.metadata() for c in bank.clips}

    share = [p for i, p in enumerate(paths) if i * batches // len(paths) == batch - 1] if paths else []
    todo = [p for p in share if p.stem not in state['clips'] or not E.does_asset_exist(state['clips'][p.stem]['asset'])]
    log(f'batch {batch}/{batches}: {len(share)} clips, {len(todo)} to import')
    for index, path in enumerate(todo):
        clip = N.load_clip(path.read_bytes())
        meta = metadata.get(clip.name)
        if E.does_asset_exist(f'{CLIPS}/B{clip.bank}/{clip.name}'):
            E.delete_asset(f'{CLIPS}/B{clip.bank}/{clip.name}')
        sequence, events, guarded = make_clip(clip, meta, rig, pose, skeleton, mesh, bone_settings, curve_settings,
                                              curve_id)
        names = {a.name for a in meta.attributes} if meta else set()
        state['clips'][clip.name] = dict(
            asset=sequence.get_path_name().split('.')[0], bank=clip.bank, record=clip.record, fps=clip.fps,
            frames=clip.frame_count, duration=clip.duration, looping=bool(meta and meta.looping),
            phase_controlled=bool(meta and meta.phase_controlled), flags=f'0x{meta.flags_word:08x}' if meta else None,
            base_speed=N.as_float(meta.base_speed_bits) if meta else None, motion=motion_record(clip, rig, pose),
            channel_weights=channel_record(clip, rig), snap_guarded_keys=guarded, events=events, curves=sorted(names),
            mirror=dict(table=head['mirror_table'], mirrored_attribute='MIRRORED' in names,
                        switch_attribute='SWITCH' in names))
        E.save_loaded_asset(sequence, False)
        if index % 50 == 49 or index == len(todo) - 1:
            finish_compilation()
            U.SystemLibrary.collect_garbage()
            STATE.write_text(json.dumps(state) + '\n')
            log(f'{index + 1}/{len(todo)} clips, {time.time() - started:.0f} s')

    names = [p.stem for p in paths]
    if all(n in state['clips'] for n in names):
        clips = {n: state['clips'][n] for n in names}
        manifest = dict(about='Skating clips as Unreal assets (unreal/Scripts/skate_ride/README.md)',
                        partial=partial, clip_count=len(clips), **head, clips=clips)
        (DATA / 'clips.json').write_text(json.dumps(manifest, indent=1) + '\n')
        log(f'manifest written: {len(clips)} clips')
    else:
        log(f'manifest not written yet: {sum(n in state["clips"] for n in names)}/{len(names)} clips imported')
    log(f'batch {batch}/{batches} took {time.time() - started:.0f} s')
    U.log('SKATE RIDE CLIPS BATCH COMPLETE')


main()
