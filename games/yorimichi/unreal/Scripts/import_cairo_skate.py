"""Install the skate rider clips (game-r17, docs/SKATE.md) into the existing Cairo character.

Run after `games/yorimichi/assets/characters/cairo/export_unreal.py -- --revision game-r17 --clips <every Skate* role> --clips-only --report export-skate.json`:

    UnrealEditor-Cmd Yorimichi.uproject -run=pythonscript -script=Scripts/import_cairo_skate.py -unattended -nosplash -NullRHI -stdout

Imports every A_Skate*.fbx listed in export-skate.json as /Game/Cairo/A_<Role> (regular and Goofy) and puts them in
DA_Cairo.SkateActions under their role names, which is where USkateComponent looks. Every other Cairo asset
file must be byte-identical afterwards.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import hashlib, json, sys
from pathlib import Path
import unreal as U
ROOT = yori.OUT
OUT = ROOT / 'cairo'
CONTENT = yori.GAME / 'unreal/Content/Cairo'
CONFIG = json.loads((OUT / 'export-skate.json').read_text())
DEST = '/Game/Cairo'
E = U.EditorAssetLibrary; AT = U.AssetToolsHelpers.get_asset_tools()
sys.path.insert(0, str(Path(__file__).resolve().parent))
import animation_compression

ROLES = [name for name in CONFIG['clips'] if name.startswith('Skate')]
OWNED = {f'A_{name}.uasset' for name in ROLES} | {'DA_Cairo.uasset'}


def digests():
    return {str(p.relative_to(CONTENT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in CONTENT.rglob('*.uasset')}


def fbx(name, sample_rate):
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
mesh = E.load_asset(DEST + '/SK_Cairo'); assert mesh, 'import the full character first'
skeleton = mesh.skeleton
definition = E.load_asset(DEST + '/DA_Cairo'); assert definition
skate = {str(k): v for k, v in definition.get_editor_property('skate_actions').items()}
clips = {}
for name in ROLES:
    cfg = CONFIG['clips'][name]
    clip = fbx(name, cfg.get('sample_rate', 60))
    assert abs(clip.get_editor_property('sequence_length') - cfg['duration']) < .001, (name, clip.get_editor_property('sequence_length'), cfg['duration'])
    E.save_loaded_asset(clip); clips[name] = clip
skate.update(clips)
definition.set_editor_property('skate_actions', skate)
E.save_loaded_asset(definition)
after = digests()
changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
report = {'source': CONFIG['source'], 'source_sha256': CONFIG['source_sha256'], 'changed_files': changed,
          'clips': {n: {'path': c.get_path_name(), 'duration': c.get_editor_property('sequence_length')} for n, c in clips.items()}}
(OUT / 'unreal_import_skate.json').write_text(json.dumps(report, indent=2) + '\n')
assert set(changed) <= OWNED, ('unexpected asset changes', sorted(set(changed) - OWNED))
U.log('CAIRO SKATE IMPORT COMPLETE %d clips' % len(clips))
