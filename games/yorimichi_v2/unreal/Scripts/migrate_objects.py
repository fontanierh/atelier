"""Save runtime-region scenery groups as their own actors (audit A1), run by tools/migrate/objects.py (guarded step
`migrate.objects`) with V2_MIGRATE_PLAN naming:
  map       the World Partition map holding them
  groups    [{region, tag, data, meshes}]: the region that owns them, ABelmonteRegion's runtime tag (brinecove), its
            runtime file under Content/Data, and the group meshes to save (one object each)
UV2Migration.MigrateRegionGroups builds each patch with the runtime's own component code and lists the group in the
map's manifest, so the runtime skips only those groups. A group already saved is kept as it is, edits included: a
rerun creates nothing. Prints each object's actor package for its record.
"""
import json
import os

import unreal as U

MARKER = 'V2 OBJECTS DONE'
plan = json.loads(open(os.environ['V2_MIGRATE_PLAN']).read())
LES = U.get_editor_subsystem(U.LevelEditorSubsystem)
EAS = U.get_editor_subsystem(U.EditorActorSubsystem)

if not LES.load_level(plan['map']):
    raise RuntimeError(f'cannot open {plan["map"]}')
# World Partition loads only the always-loaded actors with the map: an unloaded patch would be made again.
wpl = U.WorldPartitionBlueprintLibrary
guids = [d.get_editor_property('guid') for d in wpl.get_actor_descs() or []]
if guids:
    wpl.load_actors(guids)
world = U.get_editor_subsystem(U.UnrealEditorSubsystem).get_editor_world()
created, kept, keys = [], 0, set()
for group in plan['groups']:
    count, actors, reused, error = U.V2Migration.migrate_region_groups(
        world, U.Name(group['region']), U.Name(group['tag']), group['data'], list(group['meshes']))
    if count < 0:
        raise RuntimeError(f'MigrateRegionGroups {group["tag"]}: {error}')
    created += actors
    kept += reused
    keys |= {f'{group["tag"]}:{mesh}' for mesh in group['meshes']}
if not U.EditorLoadingAndSavingUtils.save_dirty_packages(True, True):
    raise RuntimeError('could not save the objects and the manifest')
for actor in EAS.get_all_level_actors():
    if actor.get_class().get_name() == 'V2ScenePatch' and str(actor.get_editor_property('source_key')) in keys:
        U.log(f'V2 OBJECT {actor.get_package().get_name()} {actor.get_editor_property("source_key")}')
U.log(f'{MARKER} created={len(created)} kept={kept}')
