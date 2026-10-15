"""Import a playable character's riding clips into /Game/<Rig><Ride>: its bike clips (assets/vehicles/bike/rider.py,
RIDE=bike, /Game/<Rig>Bike) or its horse clips (assets/horses/rider.py, RIDE=horse, /Game/<Rig>Horse). RIDE_CHARACTER
picks the character folder (default: cairo; <Rig> is its character.toml [game] bike_rig, as its SK_<Name> is named).

    RIDE=bike RIDE_CHARACTER=cairo UnrealEditor-Cmd Yorimichi.uproject -run=pythonscript -script=Scripts/import_ride_clips.py -unattended -nosplash -NullRHI -stdout

Each build/yorimichi/<id>/<ride>/fbx/A_<Clip>.fbx is imported onto the character's skeleton at the export rate as
A_<Clip>, with the shared character compression and no root motion. The clips live in their own folder rather than in
the character's definition's action map, which its own imports rewrite: UBikeComponent and UHorseComponent load them by
path. The rest of each clip's record (the bike's channels per frame, the limb contact windows) stays in export.json;
for the bike data.stage copies it to Content/Data/<id>/bike/export.json for the component (the horse reads none). Writes
build/yorimichi/<id>/<ride>/unreal_import.json.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json, os, sys
from pathlib import Path
import unreal as U
sys.path.insert(0, str(Path(__file__).resolve().parent))
import animation_compression

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'assets' / 'characters' / 'pipeline'))
import definition  # noqa: E402

RIDE = os.environ['RIDE']
assert RIDE in ('bike', 'horse'), RIDE
CHARACTER = os.environ.get('RIDE_CHARACTER', 'cairo')
SPEC = definition.load(CHARACTER)   # its asset name, output folder, Unreal folder and bike rig
NAME = SPEC.name
OUT = yori.OUT / SPEC.output / RIDE
CONFIG = json.loads((OUT / 'export.json').read_text())
DEST = f"/Game/{SPEC.game['bike_rig']}{RIDE.capitalize()}"   # AMoverCharacter::GetBikeRig: the ride's component reads the clips there
E = U.EditorAssetLibrary; AT = U.AssetToolsHelpers.get_asset_tools()
E.make_directory(DEST)


def fbx(name, skeleton):
    task = U.AssetImportTask()
    for prop, value in dict(filename=str(OUT / 'fbx' / f'A_{name}.fbx'), destination_path=DEST, destination_name=f'A_{name}',
                            automated=True, replace_existing=True, save=True).items():
        task.set_editor_property(prop, value)
    options = U.FbxImportUI()
    for prop, value in dict(automated_import_should_detect_type=False, import_materials=False, import_textures=False, import_as_skeletal=True,
                            import_mesh=False, import_animations=True, skeleton=skeleton, mesh_type_to_import=U.FBXImportType.FBXIT_ANIMATION).items():
        options.set_editor_property(prop, value)
    data = options.get_editor_property('anim_sequence_import_data')
    for prop, value in dict(animation_length=U.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME, use_default_sample_rate=False,
                            custom_sample_rate=CONFIG['fps'], import_bone_tracks=True, delete_existing_morph_target_curves=True,
                            do_not_import_curve_with_zero=False, convert_scene=True).items():
        data.set_editor_property(prop, value)
    task.set_editor_property('options', options)
    AT.import_asset_tasks([task])
    clip = next((a for a in (E.load_asset(p) for p in task.get_editor_property('imported_object_paths')) if isinstance(a, U.AnimSequence)), None)
    assert clip and clip.get_editor_property('skeleton') == skeleton, ('import failed', name)
    clip.set_editor_property('enable_root_motion', False)
    animation_compression.apply_to(clip)
    E.save_loaded_asset(clip)
    return clip


mesh = E.load_asset(f'{SPEC.unreal_path}/SK_{NAME}'); assert mesh, f'import {NAME} first (unreal.{CHARACTER})'
report = {}
for name, entry in CONFIG['clips'].items():
    clip = fbx(name, mesh.skeleton)
    length = clip.get_play_length()
    # Loops export one frame short of the cycle (the last frame is the first again); one-shots include their last frame.
    assert abs(length - entry['duration']) < 1.5 / CONFIG['fps'], (name, 'length', length, entry['duration'])
    report[name] = {'length': round(length, 4), 'frames': entry['frames'], 'loop': entry['loop']}
(OUT / 'unreal_import.json').write_text(json.dumps({'fps': CONFIG['fps'], 'source_sha256': CONFIG['source_sha256'], 'clips': report}, indent=2) + '\n')
U.log(f'{CHARACTER.upper()} {RIDE.upper()} IMPORT COMPLETE')
