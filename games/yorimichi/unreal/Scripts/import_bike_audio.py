"""Import the bike sounds (build/yorimichi/audio/bike, built by assets/audio/bike/make.py) as /Game/Audio/Bike/<cue>_<nn>.

    UnrealEditor-Cmd Yorimichi.uproject -run=pythonscript -script=Scripts/import_bike_audio.py -unattended -nosplash -NullRHI -stdout

UBikeComponent loads a cue's variants by name (<cue>_01, <cue>_02, ...). The manifest's loops (the tyres on each ground,
freewheel, chain, wind and skids) are imported looping. Re-running replaces the waves in place; nothing else is touched.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json
from pathlib import Path
import unreal as U

ROOT = yori.OUT
SOURCE = ROOT / 'audio/bike'
DEST = '/Game/Audio/Bike'
LOOPS = set(json.loads((SOURCE / 'manifest.json').read_text())['loops'])
E = U.EditorAssetLibrary; AT = U.AssetToolsHelpers.get_asset_tools()
E.make_directory(DEST)
files = sorted(SOURCE.glob('*/*.wav'))
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
        loop = wave.get_name().rsplit('_', 1)[0] in LOOPS
        wave.set_editor_property('looping', loop)
        E.save_loaded_asset(wave)
        imported[wave.get_name()] = {'path': wave.get_path_name(), 'duration': wave.get_editor_property('duration'), 'looping': loop}
missing = sorted({p.stem for p in files} - set(imported))
(ROOT / 'bike_audio_import.json').write_text(json.dumps({'imported': imported, 'missing': missing}, indent=2) + '\n')
if missing: raise SystemExit(f'bike audio: {len(missing)} files not imported: {missing}')
U.log(f'BIKE AUDIO IMPORT COMPLETE {len(imported)} waves')
