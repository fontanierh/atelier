"""Open a V2 map in the editor and close it without saving (collaboration test C05, warm no-op).

V2_OPEN_MAP names the map (default /Game/V2/Maps/TestMinimal). Opening must not dirty or rewrite any tracked
package; the caller compares `git status` before and after.
"""
import os

import unreal as U

path = os.environ.get('V2_OPEN_MAP', '/Game/V2/Maps/TestMinimal')
if not U.get_editor_subsystem(U.LevelEditorSubsystem).load_level(path):
    raise RuntimeError(f'cannot open {path}')
dirty = [p.get_name() for p in U.EditorLoadingAndSavingUtils.get_dirty_map_packages() +
         U.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
U.log(f'V2 OPENED {path}; dirty after open: {dirty or "none"}')
