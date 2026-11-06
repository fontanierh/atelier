"""Run one named editor script inside the guarded, admitted editor (build step `editor.run`).

One-off editor writes (a test map, a scrub) go through this step so they get the same lock and memory guard as
every import: V2_EDITOR_SCRIPT names the script, which must live under unreal/Scripts. The step authorizes the
write before the editor starts: V2_EDITOR_CLAIM with V2_EDITOR_PATHS, or the D04 bootstrap writer.
"""
import os
import runpy
from pathlib import Path

import unreal

if os.environ.get('V2_SAVE_ALLOW') and not unreal.V2SaveGuard.is_active():
    raise RuntimeError('V2_SAVE_ALLOW is set but the V2 save guard is not active; refusing to run')
script = Path(os.environ['V2_EDITOR_SCRIPT']).resolve()
if Path(__file__).resolve().parent not in script.parents:
    raise RuntimeError(f'{script} is not a V2 editor script (unreal/Scripts)')
if script.name == 'import_asset.py':
    raise RuntimeError('import_asset.py runs only through its import.<id> step (tools/import/run.py)')
runpy.run_path(str(script), run_name='__main__')
unreal.log('V2 EDITOR SCRIPT DONE')
