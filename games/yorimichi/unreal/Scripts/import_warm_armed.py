"""Install the armed locomotion clips (game-r16) into the existing Warm Original character.

Run after `export_warm_original_unreal.py -- --revision game-r16 --clips SwordWalk,SwordSprint,SwordStand,SwordCarry,SwordJumpStart,SwordJumpRise,SwordDoubleJump,SwordFall,SwordLand,SwordHardLand,SwordDashAir,SwordDashGround,SwordCrouchIdle,SwordCrouchWalk,SwordSitDown,SwordSitIdle,SwordStandUp,SwordRoll --clips-only --report export-armed.json`:

    UnrealEditor-Cmd Yorimichi.uproject -run=pythonscript -script=Scripts/import_warm_armed.py -unattended -nosplash -NullRHI -stdout

Imports A_SwordWalk and A_SwordSprint, makes A_SwordRun from the sprint at 0.8x (as A_Run is made from A_Sprint), imports
A_SwordCarry (the one-handed hold for jumps, falls, dashes and crouching) and the armed A_SwordDoubleJump and A_SwordRoll, and
builds BS_SwordLocomotion: SwordStand, SwordWalk, SwordRun and SwordSprint at the speeds of BS_Locomotion's samples, so
the two blend spaces stay in step in the "Stride" sync group. DA_WarmOriginal gets `armed_locomotion` and the three
clips. Every other WarmOriginal asset file must be byte-identical afterwards.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import hashlib, json, sys
from pathlib import Path
import unreal as U
ROOT = yori.OUT
OUT = ROOT / 'warm_original'
CONTENT = yori.GAME / 'unreal/Content/WarmOriginal'
CONFIG = json.loads((OUT / 'export-armed.json').read_text())
DEST = '/Game/WarmOriginal'
E = U.EditorAssetLibrary; AT = U.AssetToolsHelpers.get_asset_tools()
sys.path.insert(0, str(Path(__file__).resolve().parent))
import animation_compression

OWNED = {f'A_{name}.uasset' for name in CONFIG['clips']} | {'A_SwordRun.uasset', 'BS_SwordLocomotion.uasset', 'BS_SwordCrouching.uasset', 'DA_WarmOriginal.uasset'}


def digests():
    return {str(p.relative_to(CONTENT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in CONTENT.rglob('*.uasset')}


def fbx(source, name, sample_rate):
    task = U.AssetImportTask()
    for prop, value in dict(filename=str(OUT / 'fbx' / f'A_{source}.fbx'), destination_path=DEST, destination_name='A_' + name,
                            automated=True, replace_existing=True, save=True).items():
        task.set_editor_property(prop, value)
    options = U.FbxImportUI()
    for prop, value in dict(automated_import_should_detect_type=False, import_materials=False, import_textures=False, import_as_skeletal=True,
                            import_mesh=False, import_animations=True, skeleton=skeleton, mesh_type_to_import=U.FBXImportType.FBXIT_ANIMATION).items():
        options.set_editor_property(prop, value)
    data = options.get_editor_property('anim_sequence_import_data')
    for prop, value in dict(animation_length=U.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME, use_default_sample_rate=False,
                            custom_sample_rate=sample_rate, import_bone_tracks=True, delete_existing_morph_target_curves=True,
                            do_not_import_curve_with_zero=False, convert_scene=True).items():
        data.set_editor_property(prop, value)
    task.set_editor_property('options', options)
    AT.import_asset_tasks([task])
    clip = next((a for a in (E.load_asset(p) for p in task.get_editor_property('imported_object_paths')) if isinstance(a, U.AnimSequence)), None)
    assert clip and clip.get_editor_property('skeleton') == skeleton, 'import failed: ' + name
    clip.set_editor_property('enable_root_motion', False)
    animation_compression.apply_to(clip)
    return clip


before = digests()
mesh = E.load_asset(DEST + '/SK_WarmOriginal'); assert mesh, 'import the full character first'
skeleton = mesh.skeleton
definition = E.load_asset(DEST + '/DA_WarmOriginal'); assert definition
actions = {str(k): v for k, v in definition.get_editor_property('actions').items()}
assert 'SwordIdle' in actions, 'install the sword set first (import_warm_sword.py)'
clips = {}
for name, cfg in CONFIG['clips'].items():
    clip = fbx(name, name, cfg.get('sample_rate', 60))
    assert abs(clip.get_editor_property('sequence_length') - cfg['duration']) < .001, (name, clip.get_editor_property('sequence_length'), cfg['duration'])
    E.save_loaded_asset(clip); clips[name] = clip
run = fbx('SwordSprint', 'SwordRun', CONFIG['clips']['SwordSprint'].get('sample_rate', 60))
run.set_editor_property('rate_scale', .8)
E.save_loaded_asset(run, only_if_is_dirty=False); clips['SwordRun'] = run
# same sample speeds as the unarmed blend space, so both run at the same stride phase
locomotion = definition.get_editor_property('locomotion')
speeds = [0., definition.get_editor_property('walk_speed'), definition.get_editor_property('run_speed'), definition.get_editor_property('sprint_speed')]
path = DEST + '/BS_SwordLocomotion'
if E.does_asset_exist(path): blend = E.load_asset(path)
else:
    factory = U.BlendSpaceFactory1D(); factory.set_editor_property('target_skeleton', skeleton)
    blend = AT.create_asset('BS_SwordLocomotion', DEST, U.BlendSpace1D, factory)
params = list(blend.get_editor_property('blend_parameters'))
for k, v in dict(display_name='Speed (cm/s)', min=0., max=max(speeds)).items(): params[0].set_editor_property(k, v)
blend.set_editor_property('blend_parameters', params)
blend.set_editor_property('scale_animation', True)
smoothing = list(blend.get_editor_property('interpolation_param'))
smoothing[0].set_editor_property('interpolation_time', locomotion.get_editor_property('interpolation_param')[0].get_editor_property('interpolation_time'))
blend.set_editor_property('interpolation_param', smoothing)
# the idle sample is the armed stand (the idle with the sword) when it exists, else the guard
stand = clips.get('SwordStand') or actions['SwordIdle']
assert U.WandererContentLibrary.configure_blend_space(blend, [stand, clips['SwordWalk'], clips['SwordRun'], clips['SwordSprint']], speeds)
E.save_loaded_asset(blend)
# the crouch clips' armed copies, at BS_Crouching's speeds
crouching = None
if 'SwordCrouchIdle' in clips and 'SwordCrouchWalk' in clips:
    source = definition.get_editor_property('crouching')
    cspeeds = [0., definition.get_editor_property('crouch_speed')]
    path = DEST + '/BS_SwordCrouching'
    if E.does_asset_exist(path): crouching = E.load_asset(path)
    else:
        factory = U.BlendSpaceFactory1D(); factory.set_editor_property('target_skeleton', skeleton)
        crouching = AT.create_asset('BS_SwordCrouching', DEST, U.BlendSpace1D, factory)
    params = list(crouching.get_editor_property('blend_parameters'))
    for k, v in dict(display_name='Speed (cm/s)', min=0., max=max(cspeeds)).items(): params[0].set_editor_property(k, v)
    crouching.set_editor_property('blend_parameters', params)
    crouching.set_editor_property('scale_animation', True)
    smoothing = list(crouching.get_editor_property('interpolation_param'))
    smoothing[0].set_editor_property('interpolation_time', source.get_editor_property('interpolation_param')[0].get_editor_property('interpolation_time'))
    crouching.set_editor_property('interpolation_param', smoothing)
    assert U.WandererContentLibrary.configure_blend_space(crouching, [clips['SwordCrouchIdle'], clips['SwordCrouchWalk']], cspeeds)
    E.save_loaded_asset(crouching)
    definition.set_editor_property('armed_crouching', crouching)
actions.update(clips)
definition.set_editor_property('actions', actions)
definition.set_editor_property('armed_locomotion', blend)
E.save_loaded_asset(definition)
after = digests()
changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
report = {'source': CONFIG['source'], 'source_sha256': CONFIG['source_sha256'], 'speeds': speeds, 'changed_files': changed,
          'clips': {n: {'path': c.get_path_name(), 'duration': c.get_editor_property('sequence_length'), 'rate_scale': c.get_editor_property('rate_scale')} for n, c in clips.items()}}
(OUT / 'unreal_import_armed.json').write_text(json.dumps(report, indent=2) + '\n')
assert set(changed) <= OWNED, ('unexpected asset changes', sorted(set(changed) - OWNED))
U.log('WARM ARMED IMPORT COMPLETE ' + ', '.join(changed))
