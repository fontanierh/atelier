"""Import the hippodrome race music and sounds (build/yorimichi/audio/hippodrome, built by
assets/audio/hippodrome/make.py) and stage the rhythm charts the race reads.

    UnrealEditor-Cmd Yorimichi.uproject -run=pythonscript -script=Scripts/import_hippodrome_audio.py -unattended -nosplash -NullRHI -stdout

The songs become /Game/Audio/Hippodrome/Music_<song> (race_maiden, race_stakes, race_cup; not looping: the game loops
the tail itself between the chart's loop_from and loop_to), the race sounds /Game/Audio/Hippodrome/<cue>_<nn>
(HR_CrowdLoop looping). charts.json is copied to Content/Data/hippodrome/charts.json, which the game reads with
AtelierDataPath(TEXT("hippodrome/charts.json")). Re-running replaces the waves in place; nothing else is touched.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json, shutil
from pathlib import Path
import unreal as U

ROOT = yori.OUT
SOURCE = ROOT / 'audio/hippodrome'
DEST = '/Game/Audio/Hippodrome'
DATA = Path(__file__).resolve().parents[1] / 'Content' / 'Data' / 'hippodrome'
MANIFEST = json.loads((SOURCE / 'manifest.json').read_text())
LOOPS = set(MANIFEST['loops'])
E = U.EditorAssetLibrary; AT = U.AssetToolsHelpers.get_asset_tools()
E.make_directory(DEST)
names = {}                                  # destination asset name -> wav
for song, entry in MANIFEST['music'].items():
    names[f'Music_{song}'] = ROOT / entry['file']
for cue, files in MANIFEST['cues'].items():
    for entry in files:
        wav = ROOT / entry['file']
        names[wav.stem] = wav
tasks = []
for name, wav in sorted(names.items()):
    task = U.AssetImportTask()
    for k, v in dict(filename=str(wav), destination_path=DEST, destination_name=name, automated=True, replace_existing=True, save=False).items():
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
missing = sorted(set(names) - set(imported))
DATA.mkdir(parents=True, exist_ok=True)
shutil.copy2(SOURCE / 'charts.json', DATA / 'charts.json')
(ROOT / 'hippodrome_audio_import.json').write_text(json.dumps({'imported': imported, 'missing': missing, 'charts': str(DATA / 'charts.json')}, indent=2) + '\n')
if missing: raise SystemExit(f'hippodrome audio: {len(missing)} files not imported: {missing}')
U.log(f'HIPPODROME AUDIO IMPORT COMPLETE {len(imported)} waves, charts staged')
