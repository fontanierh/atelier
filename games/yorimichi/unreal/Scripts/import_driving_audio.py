"""Import the driving sounds (build/yorimichi/audio/kart, built by assets/audio/kart/make.py) as /Game/Audio/Driving.

    UnrealEditor-Cmd Yorimichi.uproject -run=pythonscript -script=Scripts/import_driving_audio.py -unattended -nosplash -NullRHI -stdout

UDrivingComponent loads a cue's variants by name (<cue>_01, <cue>_02, ...) from that folder; a game that stages no
sound there drives silently. The manifest's loops (engine, tyre, skid, wind) are imported looping. Re-running replaces
the waves in place; nothing else is touched.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json
from pathlib import Path
import unreal as U
from atelier.native_packages import save as save_native_package

ROOT = yori.OUT
SOURCE = ROOT / 'audio/kart'
DEST = '/Game/Audio/Driving'
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
        save_native_package(wave, E, yori.GAME / "unreal/Content")
        imported[wave.get_name()] = {'path': wave.get_path_name(), 'duration': wave.get_editor_property('duration'), 'looping': loop}
missing = sorted({p.stem for p in files} - set(imported))
(ROOT / 'driving_audio_import.json').write_text(json.dumps({'imported': imported, 'missing': missing}, indent=2) + '\n')
if missing: raise SystemExit(f'driving audio: {len(missing)} files not imported: {missing}')
U.log(f'DRIVING AUDIO IMPORT COMPLETE {len(imported)} waves')
