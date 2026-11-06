"""Run one named editor script inside the guarded, admitted editor (build step `editor.run`).

The bootstrap writer's one-off editor writes (a test map, a scrub) go through this step so they get the same lock
and memory guard as every import: V2_EDITOR_SCRIPT names the script, which must live under unreal/Scripts.
"""
import os
import runpy
from pathlib import Path

import unreal

script = Path(os.environ['V2_EDITOR_SCRIPT']).resolve()
if Path(__file__).resolve().parent not in script.parents:
    raise RuntimeError(f'{script} is not a V2 editor script (unreal/Scripts)')
runpy.run_path(str(script), run_name='__main__')
unreal.log('V2 EDITOR SCRIPT DONE')
