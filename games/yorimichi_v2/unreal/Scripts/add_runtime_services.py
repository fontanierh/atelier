"""Add region services to a slice map's runtime list, without a migration (build step `editor.run`).

    V2_EDITOR_SCRIPT=unreal/Scripts/add_runtime_services.py V2_MAP=/Game/V2/Maps/Slice V2_ADD_SERVICES="MegaPark"

A slice map (`AV2WorldManifest::bOnlyMigrated`) starts only the region services its manifest lists. When a service
becomes available later (Mega Park, once its rights were cleared: DECISIONS D05 group 3), this appends it to the
saved list and saves only the manifest's actor package; the migrated scenery and its bounds are untouched. A rerun
with the services already listed saves nothing. tools/migrate/run.py takes the same names as --runtime-service.
"""
import os

import unreal as U

MARKER = 'V2 RUNTIME SERVICES DONE'
LES = U.get_editor_subsystem(U.LevelEditorSubsystem)
EAS = U.get_editor_subsystem(U.EditorActorSubsystem)

path = os.environ.get('V2_MAP', '/Game/V2/Maps/Slice')
wanted = [s for s in os.environ.get('V2_ADD_SERVICES', '').split() if s]
if not wanted:
    raise RuntimeError('V2_ADD_SERVICES must name at least one service')
if not LES.load_level(path):
    raise RuntimeError(f'cannot open {path}')
manifest_class = U.load_class(None, '/Script/Yorimichi.V2WorldManifest')
found = [a for a in EAS.get_all_level_actors() if a.get_class() == manifest_class]
if len(found) != 1:
    raise RuntimeError(f'{path} holds {len(found)} manifests, not one')
manifest = found[0]
services = [str(s) for s in manifest.get_editor_property('runtime_services')]
added = [s for s in wanted if s not in services]
if added:
    manifest.set_editor_property('runtime_services', [U.Name(s) for s in services + added])
    if not U.EditorLoadingAndSavingUtils.save_packages([manifest.get_package()], True):
        raise RuntimeError(f'could not save {manifest.get_package().get_name()}')
U.log(f'{MARKER} {manifest.get_package().get_name()} added={added} services={services + added}')
