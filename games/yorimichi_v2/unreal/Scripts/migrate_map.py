"""One-time migration of the original game's static world into a V2 World Partition map (plan §6, P3 step 1).

Editor side, run by tools/migrate/run.py (guarded) with V2_MIGRATE_PLAN naming:
  map          the World Partition map to add to (created when missing)
  regions      [{id, bounds_cm}]: the regions to migrate, bounds half-open [min x, min y, max x, max y] in cm
  environment  the region ID that owns the map-wide actors (sun, sky light, fog, post process, player start,
               the AV2WorldManifest) and, when listed in services, the sky dome and sea
  services     whole-world runtime pieces to save: SkyDome, Sea
  patch_m      the scenery patch size in metres (bounded patches, not one actor per tree or one per region)
  only_migrated, runtime_services   the manifest's slice mode: no runtime instance scenery at all, and only
               these region services still start (e.g. SkatePark)

Nothing here re-describes the world. The saved Slice map's pieces (terrain cells, road, lane, guardrail, wires,
far hills) come from the runtime island roster `Content/Data/terrain/island.json` exactly as the original island
owner places them (import_island_world.py → setup_project.build_level: one Static actor per piece at the origin,
tagged `IslandSurface:<parent>`); the environment actors repeat build_level's settings; and the runtime scenery
comes from UV2Migration.MigrateStaticScenery, which builds it with AJapanWorld::Load itself.

Every actor carries `V2Id:<id>` from its source identity and a `region/<id>:` label, so a rerun on unchanged data
creates nothing and save validation assigns each actor to exactly one region. The script prints each created
actor's external package for the region records (tools/content/save_validate.py records them).
"""
import hashlib
import json
import os

import unreal as U

MARKER = 'V2 MIGRATE DONE'
plan = json.loads(open(os.environ['V2_MIGRATE_PLAN']).read())
LES = U.get_editor_subsystem(U.LevelEditorSubsystem)
EAS = U.get_editor_subsystem(U.EditorActorSubsystem)
EAL = U.EditorAssetLibrary
CELL_M = 128.0
created, kept = [], 0


def stable_id(*parts):
    return hashlib.sha1('\0'.join(str(p) for p in parts).encode()).hexdigest()[:16]


def opt(obj, name, value):
    try:
        obj.set_editor_property(name, value)
    except Exception as error:  # noqa: BLE001 — build_level's optional properties, same tolerance
        U.log_warning(f'  (skipped {name}: {error})')


def open_map(path):
    if EAL.does_asset_exist(path):
        if not LES.load_level(path):
            raise RuntimeError(f'cannot open {path}')
    elif not LES.new_level(path, True):            # is_partitioned_world: World Partition + One File Per Actor
        raise RuntimeError(f'cannot create the World Partition map {path}')


def existing():
    """Every actor already in the map by its stable ID. World Partition loads only the always-loaded actors with the
    map, so every actor is loaded first: an unloaded one would be placed again (a duplicate, or its package
    overwritten and a later edit to it lost)."""
    wpl = U.WorldPartitionBlueprintLibrary
    guids = [d.get_editor_property('guid') for d in wpl.get_actor_descs() or []]
    if guids:
        wpl.load_actors(guids)
    found = {}
    for actor in EAS.get_all_level_actors():
        for tag in actor.tags:
            if str(tag).startswith('V2Id:'):
                found[str(tag)[5:]] = actor
    return found


have = {}


def place(cls, region, name, sid, location=U.Vector(0, 0, 0), spatial=True):
    """A new actor of `cls` with its stable ID and region label, or None when the ID is already in the map."""
    global kept
    if sid in have:
        kept += 1
        return None
    actor = EAS.spawn_actor_from_class(cls, location)
    if actor is None:
        raise RuntimeError(f'could not spawn {name}')
    actor.set_actor_label(f'{region}:{name}'[:240])
    actor.tags = [U.Name(f'V2Id:{sid}'), U.Name(f'V2Region:{region}')]
    if not spatial:
        actor.set_editor_property('is_spatially_loaded', False)
    have[sid] = actor
    created.append(actor)
    return actor


def box2d(b):
    """A valid Box2D of [min x, min y, max x, max y]: the constructor takes (min, max) only."""
    box = U.Box2D(U.Vector2D(b[0], b[1]), U.Vector2D(b[2], b[3]))
    box.is_valid = True
    return box


def inside(bounds, x, y):
    return bounds[0] <= x < bounds[2] and bounds[1] <= y < bounds[3]


def region_of(name):
    """The region holding a `<Parent>_cell_<i>_<j>[_PieceN]` island piece: the one whose bounds hold its cell's
    centre (source cell i covers x 128 i .. 128 (i + 1) m; Unreal is (100 x, -100 y) cm). A piece the donor did
    not split into cells (one whole Road, Lane, Guardrail or Wires mesh) spans the island, and a cell no migrated
    region holds is the island foundation's: the environment owns both, so the island has no holes."""
    if '_cell_' not in name:
        return plan['environment']
    parts = name.split('_cell_', 1)[1].split('_')
    i, j = int(parts[0]), int(parts[1])
    x, y = (i + .5) * CELL_M * 100, -(j + .5) * CELL_M * 100
    for region in plan['regions']:
        if inside(region['bounds_cm'], x, y):
            return region['id']
    return plan['environment']


def island_pieces():
    data_root = U.Paths.project_content_dir() + 'Data/'
    roster = json.loads(open(data_root + 'terrain/island.json').read())
    if roster.get('schema') != 1 or roster.get('complete') is not True or roster.get('origin') != [0, 0, 0]:
        raise RuntimeError('terrain/island.json is not a complete schema-1 island roster at the origin')
    for parent, group in sorted(roster['parents'].items()):
        if parent == 'Sea':
            continue                                # AJapanWorld's sea: a scenery service, not a map piece
        for row in group['meshes']:
            region = region_of(row['name'])
            if region is None:
                continue
            mesh = EAL.load_asset(row['asset'])
            if mesh is None:
                raise RuntimeError(f'{row["asset"]} is missing from V2 Content: adopt it first')
            actor = place(U.StaticMeshActor, region, f'Island:{parent}:{row["name"]}',
                          stable_id('island', parent, row['name'], row['sha256']), spatial=False)
            if actor is None:
                continue
            component = actor.static_mesh_component
            if not component.set_static_mesh(mesh):
                raise RuntimeError(f'could not assign {row["name"]}')
            component.set_editor_property('component_tags', [U.Name('IslandSurface:' + parent)])
            actor.set_mobility(U.ComponentMobility.STATIC)


BACKDROP = (':Island:', ':SkyDome:', ':Sea:')


def always_loaded():
    """The island (terrain, far hills, road, lane, guardrail, wires), the sky dome and the sea stay loaded, as the
    donor's AJapanWorld spawns them: the sky light captures the scene beyond 1.5 km once, when it registers, so a
    streamed-out far hill brightens and blues every surface's sky light, and the backdrop is seen from everywhere.
    Kept actors from an earlier run are switched too; returns how many changed."""
    changed = 0
    for actor in EAS.get_all_level_actors():
        if any(part in actor.get_actor_label() for part in BACKDROP) and actor.get_editor_property('is_spatially_loaded'):
            actor.modify()
            actor.set_editor_property('is_spatially_loaded', False)
            changed += 1
    return changed


def soft_colour_grade(settings):
    values = {
        'color_contrast': U.Vector4(.98, .98, .98, 1), 'color_gain': U.Vector4(1.02, 1.0, .98, 1),
        'color_gamma': U.Vector4(1.025, 1.025, 1.025, 1), 'color_gain_shadows': U.Vector4(.94, .98, 1.055, 1),
        'color_gain_highlights': U.Vector4(1.025, 1.005, .97, 1), 'bloom_intensity': .18,
        'vignette_intensity': .16, 'ambient_occlusion_intensity': .45,
    }
    for name, value in values.items():
        settings.set_editor_property('override_' + name, True)
        settings.set_editor_property(name, value)


def environment(region):
    """build_level's sun, sky light, fog, post process and player start, map-wide (never spatially loaded)."""
    sun = place(U.DirectionalLight, region, 'Environment:Sun', stable_id('env', 'sun'), U.Vector(0, 0, 3000), False)
    if sun:
        sun.set_actor_rotation(U.Rotator(roll=0.0, pitch=-48.0, yaw=-30.0), False)
        L = sun.light_component
        L.set_editor_property('forward_shading_priority', 1)
        L.set_mobility(U.ComponentMobility.MOVABLE); L.set_intensity(7.0)
        L.set_light_color(U.LinearColor(1.0, 0.90, 0.76, 1.0))
        opt(L, 'light_source_angle', 5.0); opt(L, 'dynamic_shadow_distance_movable_light', 30000.0)
        opt(L, 'dynamic_shadow_cascades', 4); opt(L, 'cascade_distribution_exponent', 2.5)
        opt(L, 'atmosphere_sun_light', False); opt(L, 'shadow_bias', 0.6)
    sky = place(U.SkyLight, region, 'Environment:SkyLight', stable_id('env', 'sky'), U.Vector(0, 0, 3000), False)
    if sky:
        S = sky.light_component; S.set_mobility(U.ComponentMobility.MOVABLE)
        S.set_editor_property('real_time_capture', False); S.set_intensity(3.8)
        S.set_light_color(U.LinearColor(0.95, 0.96, 1.0, 1.0))
        opt(S, 'lower_hemisphere_color', U.LinearColor(0.30, 0.36, 0.46, 1.0))
    fog = place(U.ExponentialHeightFog, region, 'Environment:Fog', stable_id('env', 'fog'), spatial=False)
    if fog:
        F = fog.component
        F.set_editor_property('fog_density', 0.0); F.set_editor_property('fog_height_falloff', 6.0)
        opt(F, 'second_fog_data', U.ExponentialHeightFogData(fog_density=0.0, fog_height_falloff=1.0, fog_height_offset=0.0))
        opt(F, 'fog_inscattering_luminance', U.LinearColor(0.62, 0.70, 0.83, 1.0)); opt(F, 'start_distance', 3000.0)
        opt(F, 'fog_cutoff_distance', 1200000.0); opt(F, 'fog_max_opacity', 0.55)
    ppv = place(U.PostProcessVolume, region, 'Environment:PostProcess', stable_id('env', 'ppv'), spatial=False)
    if ppv:
        painterly = EAL.load_asset('/Game/Japan/Materials/M_Painterly')
        if painterly is None:
            raise RuntimeError('/Game/Japan/Materials/M_Painterly is missing from V2 Content: adopt it first')
        ppv.set_editor_property('unbound', True)
        s = ppv.settings

        def ov(name, value):
            s.set_editor_property('override_' + name, True); s.set_editor_property(name, value)
        ov('auto_exposure_method', U.AutoExposureMethod.AEM_HISTOGRAM); ov('auto_exposure_bias', 1.24)
        ov('auto_exposure_min_brightness', 1.2); ov('auto_exposure_max_brightness', 1.2)
        ov('color_saturation', U.Vector4(1.0, 1.0, 1.0, 1.0))
        ov('indirect_lighting_intensity', 3.0); ov('lumen_scene_lighting_quality', 1.0)
        ov('lumen_final_gather_quality', 1.0)
        ov('dynamic_global_illumination_method', U.DynamicGlobalIlluminationMethod.LUMEN)
        ov('film_toe', 0.3); ov('film_shoulder', 0.28); ov('film_slope', 0.7)
        ov('ambient_occlusion_radius', 120.0)
        ov('screen_space_reflection_intensity', 0.0); ov('motion_blur_amount', 0.0)
        soft_colour_grade(s)
        s.set_editor_property('weighted_blendables',
                              U.WeightedBlendables(array=[U.WeightedBlendable(weight=1.0, object=painterly)]))
        ppv.set_editor_property('settings', s)
    world = json.loads(open(U.Paths.project_content_dir() + 'Data/world.json').read())
    ps = world['player_start']
    start = place(U.PlayerStart, region, 'Environment:PlayerStart', stable_id('env', 'start', *ps),
                  U.Vector(ps[0] * 100, -ps[1] * 100, ps[2] * 100 + 100), False)
    if start:
        start.set_actor_rotation(U.Rotator(roll=0.0, pitch=0.0, yaw=-ps[3]), False)


def manifest(region):
    manifest_class = U.load_class(None, '/Script/Yorimichi.V2WorldManifest')
    if manifest_class is None:
        raise RuntimeError('AV2WorldManifest is not compiled into this editor')
    found = [a for a in EAS.get_all_level_actors() if a.get_class() == manifest_class]
    actor = found[0] if found else place(manifest_class, region, 'Manifest', stable_id('manifest'), spatial=False)
    boxes = list(actor.get_editor_property('migrated_bounds_cm'))
    for item in plan['regions']:
        b = item['bounds_cm']
        box = box2d(b)
        if not any((x.min.x, x.min.y, x.max.x, x.max.y) == tuple(b) for x in boxes):
            boxes.append(box)
    actor.set_editor_property('migrated_bounds_cm', boxes)
    actor.set_editor_property('migrated_services', [U.Name(s) for s in plan.get('services', [])])
    actor.set_editor_property('only_migrated', bool(plan.get('only_migrated')))
    actor.set_editor_property('runtime_services', [U.Name(s) for s in plan.get('runtime_services', [])])


def scenery(world, env):
    """Every region's runtime scenery from one AJapanWorld::Load, plus the listed whole-world services as env's."""
    boxes = [box2d(b)
             for b in (item['bounds_cm'] for item in plan['regions'])]
    count, actors, reused, error = U.V2Migration.migrate_static_scenery(
        world, [U.Name(item['id']) for item in plan['regions']], boxes, float(plan.get('patch_m', 32)) * 100.0,
        U.Name(env), [U.Name(s) for s in plan.get('services', [])])
    if count < 0:
        raise RuntimeError(f'MigrateStaticScenery: {error}')
    created.extend(actors)
    return reused


open_map(plan['map'])
world = U.get_editor_subsystem(U.UnrealEditorSubsystem).get_editor_world()
have.update(existing())
env = plan['environment']
environment(env)
manifest(env)
island_pieces()
kept += scenery(world, env)
U.log(f'V2 ALWAYS LOADED {always_loaded()} backdrop actor(s) switched')
if not U.EditorLoadingAndSavingUtils.save_dirty_packages(True, True):
    raise RuntimeError('could not save the map and its actor packages')
for actor in created:
    U.log(f'V2 MIGRATED {actor.get_package().get_name()} {actor.get_actor_label()}')
# Every scene patch the map now holds, created or kept: tools/migrate/run.py records them as the regions' rosters.
patches = [a for a in EAS.get_all_level_actors() if a.get_class().get_name() == 'V2ScenePatch']
for actor in patches:
    U.log(f'V2 PATCH {actor.get_package().get_name()} {actor.get_actor_label()}')
U.log(f'{MARKER} created={len(created)} kept={kept} patches={len(patches)}')
