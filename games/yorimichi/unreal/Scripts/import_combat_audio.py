"""Import the sword-fight sounds (build/yorimichi/audio/combat) as /Game/Audio/Combat/<category>_<nn> SoundWaves.

    UnrealEditor-Cmd Yorimichi.uproject -run=pythonscript -script=Scripts/import_combat_audio.py -unattended -nosplash -NullRHI -stdout

AJapanCombatFX loads a cue's variants by name (<cue>_01, <cue>_02, ...) and plays a random one without back-to-back
repeats; the countryside ambience is imported looping. Re-running replaces the waves in place.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json
from pathlib import Path
import unreal as U

ROOT = yori.OUT
SOURCE = ROOT / 'audio/combat'
DEST = '/Game/Audio/Combat'
E = U.EditorAssetLibrary; AT = U.AssetToolsHelpers.get_asset_tools()
E.make_directory(DEST)
files = sorted(p for p in SOURCE.glob('*/*.wav') if p.parent.name != 'preview')
# Earlier runs imported the audition previews too (named after the bare category); remove them.
for stale in sorted({p.stem for p in SOURCE.glob('preview/*.wav')}):
    if E.does_asset_exist(f'{DEST}/{stale}'): E.delete_asset(f'{DEST}/{stale}')
tasks = []
for wav in files:
    task = U.AssetImportTask()
    for k, v in dict(filename=str(wav), destination_path=DEST, destination_name=wav.stem, automated=True, replace_existing=True, save=False).items():
        task.set_editor_property(k, v)
    task.set_editor_property('factory', U.SoundFactory())
    tasks.append(task)
AT.import_asset_tasks(tasks)
imported = {}
for task in tasks:
    for path in task.get_editor_property('imported_object_paths'):
        wave = E.load_asset(path)
        if not isinstance(wave, U.SoundWave): continue
        loop = wave.get_name().startswith('ambience_')
        wave.set_editor_property('looping', loop)
        E.save_loaded_asset(wave)
        imported[wave.get_name()] = {'path': wave.get_path_name(), 'duration': wave.get_editor_property('duration'), 'looping': loop}
missing = sorted({p.stem for p in files} - set(imported))
(ROOT / 'combat_audio_import.json').write_text(json.dumps({'imported': imported, 'missing': missing}, indent=2) + '\n')
if missing: raise SystemExit(f'combat audio: {len(missing)} files not imported: {missing}')
U.log(f'COMBAT AUDIO IMPORT COMPLETE {len(imported)} waves')
