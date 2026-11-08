"""Report the map's saved objects after a reopen (read-only `editor.run`, V2_EDITOR_READ_ONLY=1).

V2_OBJECT_KEYS names the objects' source keys ("brinecove:wreck brinecove:lighthouse"); V2_OPEN_MAP the map (default
/Game/V2/Maps/Slice). For each it prints how many actors hold it (exactly one), the actor's package, location and
rotation, its meshes and saved member count, and whether the manifest lists its groups (the game checks the
members themselves at load: AJapanWorld::RegisterScenePatch).
"""
import os

import unreal as U

MAP = os.environ.get('V2_OPEN_MAP') or '/Game/V2/Maps/Slice'
KEYS = os.environ['V2_OBJECT_KEYS'].split()
EAS = U.get_editor_subsystem(U.EditorActorSubsystem)

if not U.get_editor_subsystem(U.LevelEditorSubsystem).load_level(MAP):
    raise RuntimeError(f'cannot open {MAP}')
wpl = U.WorldPartitionBlueprintLibrary
wpl.load_actors([d.get_editor_property('guid') for d in wpl.get_actor_descs() or []])
actors = EAS.get_all_level_actors()
manifests = [a for a in actors if a.get_class().get_name() == 'V2WorldManifest']
listed = {str(g) for m in manifests for g in m.get_editor_property('migrated_groups')}
patches = [a for a in actors if a.get_class().get_name() == 'V2ScenePatch']
bad = 0
for key in KEYS:
    found = [a for a in patches if str(a.get_editor_property('source_key')) == key]
    for actor in found:
        meshes = sorted({c.static_mesh.get_name() for c in actor.get_components_by_class(U.StaticMeshComponent)
                         if c.static_mesh})
        loc, rot = actor.get_actor_location(), actor.get_actor_rotation()
        unlisted = [m for m in meshes if f'{key.split(":")[0]}:{m}' not in listed]
        U.log(f'V2 OBJECT REPORT {key} package={actor.get_package().get_name()} '
              f'location={loc.x:.1f},{loc.y:.1f},{loc.z:.1f} yaw={rot.yaw:.2f} meshes={",".join(meshes)} '
              f'expected={len(actor.get_editor_property("expected_members"))} unlisted={unlisted}')
        bad += bool(unlisted)
    if len(found) != 1:
        U.log_error(f'V2 OBJECT REPORT {key}: {len(found)} actors hold it, not one')
        bad += 1
U.log(f'V2 OBJECTS REPORTED {len(KEYS)} bad={bad}')
if bad:
    raise RuntimeError(f'{bad} object(s) are not saved exactly once with their groups listed')
