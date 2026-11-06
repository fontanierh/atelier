"""One-time migration: turn a dump of the original game's runtime scene into saved One File Per Actor actors.

Editor side, run once per region by tools/migrate/run.py (guarded), with V2_MIGRATE_PLAN naming:
  map         the World Partition map to add to (created when missing)
  dump        the scene dump from tools/migrate/dump.py
  region      the region ID that will own the new actors, and its bounds_cm
  patch_m     the instanced-foliage patch size in metres (bounded patches, not one actor per tree)
  skip_meshes /Game mesh paths that stay elsewhere (e.g. pieces another region owns)

Every actor gets a stable ID tag `V2Id:<id>` derived from its source identity (owner actor label, component and
mesh, plus the patch cell for instances), so rerunning the migration on an unchanged dump reproduces the same IDs
and a reordered source list does not recreate every actor. Static meshes become StaticMeshActors with their
mesh, material overrides, transform, mobility, collision and shadow settings. Instanced components become
AV2InstancePatch actors: one per mesh, material set and patch cell. The script writes only new actor packages of
this map plus the map itself, and prints the created external package paths for the region's record.
"""
import hashlib
import json
import math
import os

import unreal as U

MARKER = 'V2 MIGRATE DONE'
plan = json.loads(open(os.environ['V2_MIGRATE_PLAN']).read())
dump = json.loads(open(plan['dump']).read())
region = plan['region']
patch_cm = float(plan.get('patch_m', 32)) * 100.0
skip = set(plan.get('skip_meshes', []))
LES = U.get_editor_subsystem(U.LevelEditorSubsystem)
EAS = U.get_editor_subsystem(U.EditorActorSubsystem)
EAL = U.EditorAssetLibrary


def stable_id(*parts):
    return hashlib.sha1('\0'.join(str(p) for p in parts).encode()).hexdigest()[:16]


def ue_transform(row):
    x, y, z, pitch, yaw, roll, sx, sy, sz = row
    return U.Transform(U.Vector(x, y, z), U.Rotator(roll=roll, pitch=pitch, yaw=yaw), U.Vector(sx, sy, sz))


def open_map(path):
    if EAL.does_asset_exist(path):
        if not LES.load_level(path):
            raise RuntimeError(f'cannot open {path}')
    elif not LES.new_level(path, True):            # is_partitioned_world: World Partition + One File Per Actor
        raise RuntimeError(f'cannot create the World Partition map {path}')


def existing_ids():
    found = {}
    for actor in EAS.get_all_level_actors():
        for tag in actor.tags:
            tag = str(tag)
            if tag.startswith('V2Id:'):
                found[tag[5:]] = actor
    return found


def materials_of(paths):
    loaded = []
    for path in paths:
        material = EAL.load_asset(path) if path else None
        if path and material is None:
            raise RuntimeError(f'material {path} is missing from V2 Content: adopt it first')
        loaded.append(material)
    return loaded


def apply_common(comp, record):
    comp.set_editor_property('cast_shadow', record['cast_shadow'])
    if record['collision_profile'] not in ('None', ''):
        comp.set_collision_profile_name(record['collision_profile'])
    for index, material in enumerate(materials_of(record['materials'])):
        if material is not None:
            comp.set_material(index, material)
    comp.component_tags = [U.Name(t) for t in record['tags']]


def label(record, suffix=''):
    return f'{region["id"]}:{record["actor_label"]}:{record["component"]}{suffix}'[:240]


open_map(plan['map'])
have = existing_ids()
created, kept = [], 0
patch_class = U.load_class(None, '/Script/Yorimichi.V2InstancePatch')
if patch_class is None:
    raise RuntimeError('AV2InstancePatch is not compiled into this editor')

for record in dump['meshes']:
    if record['mesh'] in skip or not record['visible'] or record['hidden_in_game']:
        continue
    mesh = EAL.load_asset(record['mesh'].split('.')[0])
    if mesh is None:
        raise RuntimeError(f'mesh {record["mesh"]} is missing from V2 Content: adopt it first')
    if 'instances' not in record:
        sid = stable_id(record['actor_label'], record['component'], record['mesh'], *record['transform'])
        if sid in have:
            kept += 1
            continue
        actor = EAS.spawn_actor_from_class(U.StaticMeshActor, U.Vector(0, 0, 0))
        actor.set_actor_transform(ue_transform(record['transform']), False, False)
        comp = actor.static_mesh_component
        comp.set_static_mesh(mesh)
        comp.set_editor_property('mobility', U.ComponentMobility.STATIC)
        apply_common(comp, record)
        actor.set_actor_label(label(record))
        actor.tags = [U.Name(f'V2Id:{sid}'), U.Name(f'V2Region:{region["id"]}')] + \
            [U.Name(t) for t in record['actor_tags']]
        created.append(actor)
        continue
    cells = {}
    for row in record['instances']:
        cells.setdefault((math.floor(row[0] / patch_cm), math.floor(row[1] / patch_cm)), []).append(row)
    for (cx, cy), rows in sorted(cells.items()):
        sid = stable_id(record['actor_label'], record['component'], record['mesh'], cx, cy)
        if sid in have:
            kept += 1
            continue
        centre = U.Vector((cx + .5) * patch_cm, (cy + .5) * patch_cm, 0)
        actor = EAS.spawn_actor_from_class(patch_class, centre)
        actor.call_method('SetPatch', (mesh, materials_of(record['materials']),
                                       [ue_transform(r) for r in rows],
                                       record['cull_distance'][0], record['cull_distance'][-1],
                                       record['cast_shadow'], U.Name(record['collision_profile'])))
        actor.set_actor_label(label(record, f':{cx}_{cy}'))
        actor.tags = [U.Name(f'V2Id:{sid}'), U.Name(f'V2Region:{region["id"]}')] + \
            [U.Name(t) for t in record['actor_tags']]
        created.append(actor)

if not LES.save_current_level():
    raise RuntimeError('could not save the map and its actor packages')
for actor in created:
    U.log(f'V2 MIGRATED {actor.get_package().get_name()} {actor.get_actor_label()}')
U.log(f'{MARKER} created={len(created)} kept={kept}')
