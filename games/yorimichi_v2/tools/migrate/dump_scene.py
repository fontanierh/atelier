"""Live-side scene dump for the one-time static-world migration (plan §6, P3 step 1, P5 step 3).

Runs inside the ORIGINAL game, through its live bridge, after the world has finished spawning:

    uv run python games/yorimichi_v2/tools/migrate/dump.py --bounds-cm XMIN YMIN XMAX YMAX --out FILE

It records every static mesh the running game shows inside the bounds: the owning actor and component, mesh,
material overrides, world transform, mobility, collision and shadow settings and tags, and for instanced
components every instance's world transform. Lights, fog, sky and post-process volumes are recorded as actors.
Because it reads the running scene, the runtime clean-ups (park clearances, the Ronin camp clearing, the
floating-tree trace) are already applied. The dump is a migration input, never runtime data.

The bridge prepends `PARAMS = {...}` before this file's text.
"""
import json

import unreal as U

params = PARAMS  # noqa: F821  (prepended by dump.py)
XMIN, YMIN, XMAX, YMAX = params['bounds_cm']
world = U.UnrealEditorSubsystem().get_game_world() if hasattr(U, 'UnrealEditorSubsystem') else None
if world is None:
    world = U.EditorLevelLibrary.get_game_world()


def inside(location):
    return XMIN <= location.x <= XMAX and YMIN <= location.y <= YMAX


def transform(t):
    loc, rot, scl = t.translation, t.rotation.rotator(), t.scale3d
    return [round(loc.x, 3), round(loc.y, 3), round(loc.z, 3), round(rot.pitch, 4), round(rot.yaw, 4),
            round(rot.roll, 4), round(scl.x, 5), round(scl.y, 5), round(scl.z, 5)]


def path_of(obj):
    return obj.get_path_name() if obj else None


def component_record(actor, comp):
    mesh = comp.get_editor_property('static_mesh')
    if mesh is None:
        return None
    materials = []
    for index in range(comp.get_num_materials()):
        override = comp.get_editor_property('override_materials')
        materials.append(path_of(override[index]) if index < len(override) and override[index] else None)
    record = {
        'actor': actor.get_name(), 'actor_class': actor.get_class().get_path_name(),
        'actor_label': actor.get_actor_label() if hasattr(actor, 'get_actor_label') else actor.get_name(),
        'component': comp.get_name(), 'component_class': comp.get_class().get_name(),
        'mesh': path_of(mesh), 'materials': materials,
        'transform': transform(comp.get_world_transform()),
        'mobility': str(comp.get_editor_property('mobility')),
        'collision_profile': str(comp.get_collision_profile_name()),
        'collision_enabled': str(comp.get_collision_enabled()),
        'cast_shadow': bool(comp.get_editor_property('cast_shadow')),
        'visible': bool(comp.is_visible()),
        'hidden_in_game': bool(comp.get_editor_property('hidden_in_game')),
        'tags': [str(t) for t in comp.component_tags], 'actor_tags': [str(t) for t in actor.tags],
        'cull_distance': [float(comp.get_editor_property('ld_max_draw_distance'))],
    }
    if isinstance(comp, U.InstancedStaticMeshComponent):
        instances = []
        for i in range(comp.get_instance_count()):
            t = comp.get_instance_transform(i, True)
            if inside(t.translation):
                instances.append(transform(t))
        if not instances:
            return None
        record['instances'] = instances
        record['cull_distance'] = [float(comp.get_editor_property('instance_start_cull_distance')),
                                   float(comp.get_editor_property('instance_end_cull_distance'))]
    elif not inside(comp.get_world_transform().translation):
        bounds = comp.bounds
        origin, extent = bounds.origin, bounds.box_extent
        if (origin.x + extent.x < XMIN or origin.x - extent.x > XMAX or
                origin.y + extent.y < YMIN or origin.y - extent.y > YMAX):
            return None
        record['crosses_bounds'] = True       # a large piece reaching into the bounds: a boundary decision
    return record


meshes, others = [], []
for actor in U.GameplayStatics.get_all_actors_of_class(world, U.Actor):
    for comp in actor.get_components_by_class(U.StaticMeshComponent):
        found = component_record(actor, comp)
        if found:
            meshes.append(found)
    if isinstance(actor, (U.DirectionalLight, U.SkyLight, U.ExponentialHeightFog, U.PostProcessVolume,
                          U.SkyAtmosphere)) or 'Light' in actor.get_class().get_name():
        others.append({'actor': actor.get_name(), 'class': actor.get_class().get_path_name(),
                       'transform': transform(actor.get_actor_transform())})

with open(params['out'], 'w') as handle:
    json.dump({'schema': 1, 'bounds_cm': params['bounds_cm'], 'source_revision': params.get('source_revision'),
               'meshes': meshes, 'environment': others}, handle, sort_keys=True)
print(f'dumped {len(meshes)} mesh components '
      f'({sum(len(m.get("instances", [])) for m in meshes)} instances) and {len(others)} environment actors')
