"""Fresh-process exact reload of the typed motion and runtime data and production-session replay verification; no
game/map/rendering."""
from pathlib import Path
import json
import sys
import unreal

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'world'))
import yori

PACKAGE = yori.OUT / 'skate-native' / 'package'  # the skate.runtime build step assembles it
OUT = yori.OUT / 'skate-data'
OUT.mkdir(parents=True, exist_ok=True)
# Verifies the assets the game is configured with (USkateSettings::MotionData and RuntimeData), through its loaders.
result = unreal.SkateDataLibrary.verify(str(PACKAGE), str(OUT / 'verify.json'))
if result is None:
    raise RuntimeError('Skate data verification failed; inspect the commandlet log')
if result:
    raise RuntimeError(result)
report = json.loads((OUT / 'verify.json').read_text())
# The build's presence check includes every bank, so a deleted generated bank invalidates the step.
unreal.log(f"SKATE DATA VERIFY {report['clips']} clips, {report['frames']} frames, {report['runtime_files']} runtime "
           f"files, {report['replay_steps']} steps")
unreal.log('SKATE DATA VERIFY COMPLETE')
