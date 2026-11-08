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
  railways     [{region, tag, data, names, units}]: the Belmonte track's pieces and "<mesh>#<key>" instanced groups, each with
            its unit (UV2MigrationTravel.MigrateRailwayPieces)
  ferries      [{region, tag, data, names, units}]: ferry terminals by key, each with its unit (MigrateFerryTerminals)
  gondolas     [{region, tag, data, names, units}]: the gondola's static entries by name, each with its unit
            (MigrateGondolaStatics)
  trees     [{region, tag, data, units}]: the units of a park whose trees are saved, one actor per unit; the trees of
            each unit are assigned by the runtime rule (UV2MigrationParkDressing.MigrateParkTrees)
  props     [{region, tag, data, meshes, units}]: a park's props (the kei cars), each with its object (one actor per object;
            UV2MigrationParkDressing.MigrateParkProps)
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
# World Partition loads only the always-loaded actors with the map: an unloaded patch would be made again. So every actor
# that is not a scene patch is loaded (terrain, the manifest, services), and the scene patches of the plan's regions; the
# other regions' patches stay unloaded, which keeps a job's editor inside its memory guard as the island grows. A patch's
# label starts with its region ("<region>:<tag>:<object>:<id>"); a patch without that label is loaded.
wpl = U.WorldPartitionBlueprintLibrary
planned = {r['id'] for r in plan['regions']}
planned |= {r.rsplit('/', 1)[-1] for r in planned}


def wanted(desc):
    try:
        if 'V2ScenePatch' not in str(desc.get_editor_property('native_class')):
            return True
        region = str(desc.get_editor_property('label')).split(':', 1)[0]
    except Exception:
        return True
    return not region or region in planned or region.rsplit('/', 1)[-1] in planned


descs = wpl.get_actor_descs() or []
guids = [d.get_editor_property('guid') for d in descs if wanted(d)]
U.log(f'V2 MIGRATION loads {len(guids)} of {len(descs)} actors (regions {sorted(planned)})')
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
for name, call, label in (
        ('railways', U.V2MigrationTravel.migrate_railway_pieces, 'MigrateRailwayPieces'),
        ('ferries', U.V2MigrationTravel.migrate_ferry_terminals, 'MigrateFerryTerminals'),
        ('gondolas', U.V2MigrationTravel.migrate_gondola_statics, 'MigrateGondolaStatics')):
    for route in plan.get(name, []):
        count, actors, reused, error = call(
            world, U.Name(route['region']), U.Name(route['tag']), route['data'], list(route['names']), list(route['units']))
        if count < 0:
            raise RuntimeError(f'{label} {route["tag"]}: {error}')
        for actor in actors:
            # A route's saved units load with the map: the runtime service is spawned with the world, whatever the distance.
            actor.set_editor_property('is_spatially_loaded', False)
        created += actors
        kept += reused
        keys |= {f'{route["tag"]}:{unit}' for unit in route['units']}
for trees in plan.get('trees', []):
    count, actors, reused, error = U.V2MigrationParkDressing.migrate_park_trees(
        world, U.Name(trees['region']), U.Name(trees['tag']), trees['data'], list(trees['units']))
    if count < 0:
        raise RuntimeError(f'MigrateParkTrees {trees["tag"]}: {error}')
    for actor in actors:
        # The runtime park's trees are placed with the island, whatever the distance: their units load with the map too.
        actor.set_editor_property('is_spatially_loaded', False)
    created += actors
    kept += reused
    keys |= {f'{trees["tag"]}:trees/{unit}' for unit in trees['units']}
for props in plan.get('props', []):
    count, actors, reused, error = U.V2MigrationParkDressing.migrate_park_props(
        world, U.Name(props['region']), U.Name(props['tag']), props['data'], list(props['meshes']), list(props['units']))
    if count < 0:
        raise RuntimeError(f'MigrateParkProps {props["tag"]}: {error}')
    for actor in actors:
        actor.set_editor_property('is_spatially_loaded', False)
    created += actors
    kept += reused
    keys |= {f'{props["tag"]}:props/{unit}' for unit in props['units']}
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
