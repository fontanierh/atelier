"""Bake the reference motion bank into typed Unreal properties (no opaque payloads)."""
from pathlib import Path
import unreal

HERE = Path(__file__).resolve().parent
CONTENT = HERE.parents[1] / 'Content'
result = unreal.SkateMotionLibrary.import_motion(str(CONTENT / 'Data/SkateNative'), '/Game/SkateMotion')
# Unreal Python suppresses a bool return when out parameters are present:
# success returns the Error string (empty); failure returns None.
if result is None:
    raise RuntimeError('Motion import failed; inspect the commandlet log')
if result:
    raise RuntimeError(result)
unreal.log('SKATE MOTION IMPORT COMPLETE')
