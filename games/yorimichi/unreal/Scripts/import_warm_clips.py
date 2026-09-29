"""Replace selected Warm Original locomotion clips in place, leaving the rest of the character untouched.

Run after `export_warm_original_unreal.py -- --revision game-rNN --clips Walk,CrouchWalk --clips-only --report export-clips.json`:

    UnrealEditor-Cmd Yorimichi.uproject -run=pythonscript -script=Scripts/import_warm_clips.py -unattended -nosplash -NullRHI -stdout

For clips whose duration and travel speed are unchanged: each `A_<Clip>` is reimported at its existing path
with the full importer's settings (no root motion, the project's compression), so the blend spaces and
DA_WarmOriginal keep their references. Every other WarmOriginal asset file must be byte-identical afterwards.
`WARM_CLIP_REPORT` selects another partial export record.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import hashlib, json, os, sys
from pathlib import Path
import unreal as U
ROOT = yori.OUT
OUT = ROOT / 'warm_original'
CONTENT = yori.GAME / 'unreal/Content/WarmOriginal'
REPORT = os.environ.get('WARM_CLIP_REPORT', 'export-clips.json')
CONFIG = json.loads((OUT / REPORT).read_text())
DEST = '/Game/WarmOriginal'
E = U.EditorAssetLibrary; AT = U.AssetToolsHelpers.get_asset_tools()
sys.path.insert(0, str(Path(__file__).resolve().parent))
import animation_compression

replaced = {f'A_{name}.uasset' for name in CONFIG['clips']}


def digests():
    return {str(p.relative_to(CONTENT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in CONTENT.rglob('*.uasset')}


before = digests()
assert replaced <= set(before), ('clips must already exist; run the full importer first', replaced - set(before))
mesh = E.load_asset(DEST + '/SK_WarmOriginal'); assert mesh
skeleton = mesh.skeleton
report = {'source': CONFIG['source'], 'source_sha256': CONFIG['source_sha256'], 'clips': {}}
for name, cfg in CONFIG['clips'].items():
    old = E.load_asset(f'{DEST}/A_{name}')
    assert abs(old.get_editor_property('sequence_length') - cfg['duration']) < .001, (name, 'duration changed: use the full importer')
    task = U.AssetImportTask()
    for prop, value in dict(filename=str(OUT / 'fbx' / f'A_{name}.fbx'), destination_path=DEST, destination_name='A_' + name,
                            automated=True, replace_existing=True, save=True).items():
        task.set_editor_property(prop, value)
    options = U.FbxImportUI()
    for prop, value in dict(automated_import_should_detect_type=False, import_materials=False, import_textures=False, import_as_skeletal=True,
                            import_mesh=False, import_animations=True, skeleton=skeleton, mesh_type_to_import=U.FBXImportType.FBXIT_ANIMATION).items():
        options.set_editor_property(prop, value)
    data = options.get_editor_property('anim_sequence_import_data')
    for prop, value in dict(animation_length=U.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME, use_default_sample_rate=False,
                            custom_sample_rate=cfg.get('sample_rate', 60), import_bone_tracks=True, delete_existing_morph_target_curves=True,
                            do_not_import_curve_with_zero=False, convert_scene=True).items():
        data.set_editor_property(prop, value)
    task.set_editor_property('options', options)
    AT.import_asset_tasks([task])
    clip = next((a for a in (E.load_asset(p) for p in task.get_editor_property('imported_object_paths')) if isinstance(a, U.AnimSequence)), None)
    assert clip, 'import failed: ' + name
    assert clip.get_path_name() == old.get_path_name()
    assert clip.get_editor_property('skeleton') == skeleton
    assert abs(clip.get_editor_property('sequence_length') - cfg['duration']) < .001, (name, clip.get_editor_property('sequence_length'))
    clip.set_editor_property('enable_root_motion', False)
    animation_compression.apply_to(clip)
    E.save_loaded_asset(clip)
    report['clips'][name] = {'path': clip.get_path_name(), 'duration': clip.get_editor_property('sequence_length')}
    U.log(f'WARM CLIP {name} {clip.get_editor_property("sequence_length"):.3f}s')

after = digests()
changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
report['changed_files'] = changed
assert set(changed) <= replaced, ('unexpected asset changes', sorted(set(changed) - replaced))
(OUT / ('unreal_' + REPORT)).write_text(json.dumps(report, indent=2) + '\n')
U.log('WARM CLIP IMPORT COMPLETE ' + ', '.join(changed))
