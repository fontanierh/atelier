"""Bake the package's runtime files into typed Unreal properties that encode back to the same bytes."""
from pathlib import Path
import sys
import unreal

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'world'))
import yori  # noqa: E402

PACKAGE = yori.OUT / 'skate-simulation' / 'package'  # the skate.runtime build step assembles it
result = unreal.SkateDataLibrary.import_runtime(str(PACKAGE), '/Game/SkateRuntime')
# Unreal Python suppresses a bool return when out parameters are present:
# success returns the Error string (empty); failure returns None.
if result is None:
    raise RuntimeError('Runtime import failed; inspect the commandlet log')
if result:
    raise RuntimeError(result)
unreal.log('SKATE RUNTIME IMPORT COMPLETE')
