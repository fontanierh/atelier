"""Bake the reference motion bank into typed Unreal properties (no opaque payloads)."""
from pathlib import Path
import sys
import unreal

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'world'))
import yori  # noqa: E402

PACKAGE = yori.OUT / 'skate-native' / 'package'  # the skate.runtime build step assembles it
result = unreal.SkateMotionLibrary.import_motion(str(PACKAGE), '/Game/SkateMotion')
# Unreal Python suppresses a bool return when out parameters are present:
# success returns the Error string (empty); failure returns None.
if result is None:
    raise RuntimeError('Motion import failed; inspect the commandlet log')
if result:
    raise RuntimeError(result)
unreal.log('SKATE MOTION IMPORT COMPLETE')
