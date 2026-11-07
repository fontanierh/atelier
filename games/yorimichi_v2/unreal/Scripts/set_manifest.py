"""Set the map's AV2WorldManifest mode and save only its package (the full port: the whole island in one map).

Run through `editor.run` with V2_EDITOR_CLAIM and V2_EDITOR_PATHS naming the manifest's package file (it is the
environment region's actor). V2_MANIFEST_ONLY_MIGRATED is 1 (a slice: no runtime instance scenery, only
V2_MANIFEST_RUNTIME_SERVICES start) or 0 (the island: instances outside the migrated bounds and every region service
still run at play time, until their regions are migrated). V2_OPEN_MAP names the map (default /Game/V2/Maps/Slice).
The migrated bounds and saved services are left as the migration wrote them.
"""
import os

import unreal as U

MAP = os.environ.get('V2_OPEN_MAP') or '/Game/V2/Maps/Slice'
ONLY = os.environ['V2_MANIFEST_ONLY_MIGRATED'] == '1'
SERVICES = os.environ.get('V2_MANIFEST_RUNTIME_SERVICES', '').split()

if not U.get_editor_subsystem(U.LevelEditorSubsystem).load_level(MAP):
    raise RuntimeError(f'cannot open {MAP}')
manifest_class = U.load_class(None, '/Script/Yorimichi.V2WorldManifest')
found = [a for a in U.get_editor_subsystem(U.EditorActorSubsystem).get_all_level_actors()
         if a.get_class() == manifest_class]
if len(found) != 1:
    raise RuntimeError(f'{MAP} has {len(found)} AV2WorldManifest actors, not one')
actor = found[0]
actor.modify()
actor.set_editor_property('only_migrated', ONLY)
if ONLY:
    actor.set_editor_property('runtime_services', [U.Name(s) for s in SERVICES])
if not U.EditorLoadingAndSavingUtils.save_packages([actor.get_package()], True):
    raise RuntimeError(f'could not save {actor.get_package().get_name()}')
U.log(f"V2 MANIFEST only_migrated={actor.get_editor_property('only_migrated')} "
      f"runtime_services={[str(s) for s in actor.get_editor_property('runtime_services')]} "
      f"bounds={len(actor.get_editor_property('migrated_bounds_cm'))} package={actor.get_package().get_name()}")
