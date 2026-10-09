"""Fresh-process exact reload and production-session replay verification; no game/map/rendering."""
from pathlib import Path
import json
import sys
import unreal

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'world'))
import yori

CONTENT = HERE.parents[1] / 'Content'
OUT = yori.OUT / 'skate-motion'
OUT.mkdir(parents=True, exist_ok=True)
# Verifies the asset the game is configured with (USkateSettings::MotionData), through the game's loader.
result = unreal.SkateMotionLibrary.verify_motion(str(CONTENT / 'Data/SkateNative'), str(OUT / 'verify.json'))
if result is None:
    raise RuntimeError('Motion verification failed; inspect the commandlet log')
if result:
    raise RuntimeError(result)
report = json.loads((OUT / 'verify.json').read_text())
# The build's presence check includes every bank, so a deleted generated bank invalidates the step.
unreal.log(f"SKATE MOTION VERIFY {report['clips']} clips, {report['frames']} frames, {report['replay_steps']} steps")
unreal.log('SKATE MOTION VERIFY COMPLETE')
