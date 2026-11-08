"""Set the map's World Partition loading range (UV2Streaming.SetLoadingRanges) and save only the map package.

The original game spawns its whole island at once and only culls by screen size; with the engine's default 256 m
main-layer range and no HLODs built, a V2 map shows nothing beyond 256 m (the far town, harbour and hills of the original
views). Run through `editor.run` with V2_EDITOR_CLAIM and V2_EDITOR_PATHS naming the map's package file.
V2_LOADING_RANGE_CM is the range (default 300,000: 3 km keeps the original's far town, harbour and crater views;
10 km looked the same and cost about 0.7 GiB more); V2_OPEN_MAP names the map (default /Game/V2/Maps/Slice). The HLOD
layers keep their ranges.
"""
import os

import unreal as U

MAP = os.environ.get('V2_OPEN_MAP') or '/Game/V2/Maps/Slice'
RANGE = float(os.environ.get('V2_LOADING_RANGE_CM') or 300_000)

if not U.get_editor_subsystem(U.LevelEditorSubsystem).load_level(MAP):
    raise RuntimeError(f'cannot open {MAP}')
world = U.get_editor_subsystem(U.UnrealEditorSubsystem).get_editor_world()
changed = U.V2Streaming.set_loading_ranges(world, RANGE)
if not changed:
    raise RuntimeError(f'{MAP} has no World Partition loading range to set')
package = world.get_outermost()
if not U.EditorLoadingAndSavingUtils.save_packages([package], True):
    raise RuntimeError(f'could not save {package.get_name()}')
for line in U.V2Streaming.describe_loading_ranges(world).splitlines():
    U.log(f'V2 STREAMING {line}')
U.log(f'V2 STREAMING set {changed} range(s) to {RANGE:.0f} cm in {package.get_name()}')
