"""Save runtime-region scenery groups as their own actors (audit A1), run by tools/migrate/objects.py (guarded step
`migrate.objects`) with V2_MIGRATE_PLAN naming:
  map       the World Partition map holding them
  groups    [{region, tag, data, meshes, objects}]: the region that owns them, ABelmonteRegion's runtime tag
            (brinecove), its runtime file under Content/Data, the group meshes to save and the object each belongs to
            (one actor per object)
  splits    [{region, tag, keys, objects, points_cm, tolerance_cm}]: placed things of the region's area patches (each
            object's source key and point) that become actors of their own (UV2Migration.SplitPatchObjects)
  parks     [{region, tag, data, pieces, is_collision, units}]: a park's render and collision meshes, each with its
            unit (one actor per unit) and whether it is a collision piece (UV2Migration.MigrateParkPieces)
  hippodromes  [{region, tag, data, pieces, units}]: the hippodrome's meshes, each with its unit (one actor per unit;
            UV2Migration.MigrateHippodromePieces)
  statics   [{region, tag, meshes, units}]: the mini Mega ramp's and the Ronin camp's static meshes, each with its unit
            (one actor per unit; UV2MigrationMisc.MigrateStaticMeshes)
UV2Migration.MigrateRegionGroups builds each patch with the runtime's own component code and lists the group in the
map's manifest, so the runtime skips only those groups. A group already saved is kept as it is, edits included: a
rerun creates nothing. Prints each object's actor package for its record.
A park unit is always loaded, as the runtime park is spawned with the island whatever the distance, so its actor is
not spatially loaded. The hippodrome unit is the same: it is spawned with the island (the Hippodrome service).
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
for group in plan.get('groups', []):
    count, actors, reused, error = U.V2Migration.migrate_region_groups(
        world, U.Name(group['region']), U.Name(group['tag']), group['data'], list(group['meshes']),
        list(group['objects']))
    if count < 0:
        raise RuntimeError(f'MigrateRegionGroups {group["tag"]}: {error}')
    created += actors
    kept += reused
    keys |= {f'{group["tag"]}:{name}' for name in group['objects']}
for park in plan.get('parks', []):
    count, actors, reused, error = U.V2Migration.migrate_park_pieces(
        world, U.Name(park['region']), U.Name(park['tag']), park['data'], list(park['pieces']),
        [bool(c) for c in park['is_collision']], list(park['units']))
    if count < 0:
        raise RuntimeError(f'MigrateParkPieces {park["tag"]}: {error}')
    for actor in actors:
        # The runtime park is spawned with the island, whatever the distance: its saved units load with the map too.
        actor.set_editor_property('is_spatially_loaded', False)
    created += actors
    kept += reused
    keys |= {f'{park["tag"]}:{unit}' for unit in park['units']}
for hippodrome in plan.get('hippodromes', []):
    count, actors, reused, error = U.V2Migration.migrate_hippodrome_pieces(
        world, U.Name(hippodrome['region']), U.Name(hippodrome['tag']), hippodrome['data'], list(hippodrome['pieces']),
        list(hippodrome['units']))
    if count < 0:
        raise RuntimeError(f'MigrateHippodromePieces {hippodrome["tag"]}: {error}')
    for actor in actors:
        actor.set_editor_property('is_spatially_loaded', False)
    created += actors
    kept += reused
    keys |= {f'{hippodrome["tag"]}:{unit}' for unit in hippodrome['units']}
for static in plan.get('statics', []):
    count, actors, reused, error = U.V2MigrationMisc.migrate_static_meshes(
        world, U.Name(static['region']), U.Name(static['tag']), list(static['meshes']), list(static['units']))
    if count < 0:
        raise RuntimeError(f'MigrateStaticMeshes {static["tag"]}: {error}')
    for actor in actors:
        actor.set_editor_property('is_spatially_loaded', False)
    created += actors
    kept += reused
    keys |= {f'{static["tag"]}:{unit}' for unit in static['units']}
for split in plan.get('splits', []):
    count, actors, changed, reused, error = U.V2Migration.split_patch_objects(
        world, U.Name(split['region']), U.Name(split['tag']), list(split['keys']), list(split['objects']),
        [U.Vector2D(x, y) for x, y in split['points_cm']], float(split['tolerance_cm']))
    if count < 0:
        raise RuntimeError(f'SplitPatchObjects {split["region"]}: {error}')
    created += actors
    kept += reused
    keys |= {f'{split["tag"]}:{name}' for name in split['objects']}
    for actor in changed:
        U.log(f'V2 SPLIT FROM {actor.get_package().get_name()}')
if not U.EditorLoadingAndSavingUtils.save_dirty_packages(True, True):
    raise RuntimeError('could not save the objects and the manifest')
for actor in EAS.get_all_level_actors():
    if actor.get_class().get_name() != 'V2ScenePatch':
        continue
    # A split object shares its source key with the area patches: its V2Object tag names it.
    named = [str(t)[len('V2Object:'):] for t in actor.tags if str(t).startswith('V2Object:')]
    key = named[0] if named else str(actor.get_editor_property('source_key'))
    if key in keys:
        U.log(f'V2 OBJECT {actor.get_package().get_name()} {key}')
U.log(f'{MARKER} created={len(created)} kept={kept}')
