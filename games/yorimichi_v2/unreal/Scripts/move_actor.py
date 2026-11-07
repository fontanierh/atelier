"""Move one saved World Partition actor and save only its package (plan P3 step 2: the actor-placement edit).

Run through `editor.run` with V2_EDITOR_CLAIM and V2_EDITOR_PATHS naming the actor's package file (or as the D04
bootstrap writer). V2_MOVE_ACTOR names the actor's package (/Game/__ExternalActors__/...), V2_MOVE_BY_CM the offset
"x y z" in centimetres, V2_OPEN_MAP the map (default /Game/V2/Maps/Slice). Only that actor is loaded, moved and
saved; the run fails if it is not exactly one actor of the map, and every other package stays unsaved.
"""
import os

import unreal as U

MAP = os.environ.get('V2_OPEN_MAP') or '/Game/V2/Maps/Slice'
PACKAGE = os.environ['V2_MOVE_ACTOR']
BY = U.Vector(*(float(v) for v in os.environ['V2_MOVE_BY_CM'].split()))

if not U.get_editor_subsystem(U.LevelEditorSubsystem).load_level(MAP):
    raise RuntimeError(f'cannot open {MAP}')
WPL = U.WorldPartitionBlueprintLibrary
descs = [d for d in WPL.get_actor_descs() or [] if str(d.get_editor_property('actor_package')) == PACKAGE]
if len(descs) != 1:
    raise RuntimeError(f'{PACKAGE}: {len(descs)} actors of {MAP} are saved in it, not one')
WPL.load_actors([descs[0].get_editor_property('guid')])
actors = [a for a in U.get_editor_subsystem(U.EditorActorSubsystem).get_all_level_actors()
          if a.get_package().get_name() == PACKAGE]
if len(actors) != 1:
    raise RuntimeError(f'{PACKAGE}: loaded {len(actors)} actors, not one')
actor = actors[0]
before = actor.get_actor_location()
actor.modify()
actor.set_actor_location(before + BY, False, False)
if not U.EditorLoadingAndSavingUtils.save_packages([actor.get_package()], True):
    raise RuntimeError(f'could not save {PACKAGE}')
after = actor.get_actor_location()
U.log(f'V2 MOVED {actor.get_actor_label()} {before.x:.1f},{before.y:.1f},{before.z:.1f} -> '
      f'{after.x:.1f},{after.y:.1f},{after.z:.1f}')
U.log(f'V2 SAVED {PACKAGE}')
