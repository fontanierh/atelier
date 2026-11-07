"""Report one saved World Partition actor's transform, saving nothing (C01: does a claimed move survive a reopen?).

Run through `editor.run` with V2_MOVE_ACTOR naming the actor's package (/Game/__ExternalActors__/...) and
V2_OPEN_MAP the map (default /Game/V2/Maps/Slice). Logs `V2 TRANSFORM <label> loc x,y,z rot p,y,r scale x,y,z`.
"""
import os

import unreal as U

MAP = os.environ.get('V2_OPEN_MAP') or '/Game/V2/Maps/Slice'
PACKAGE = os.environ['V2_MOVE_ACTOR']
if not U.get_editor_subsystem(U.LevelEditorSubsystem).load_level(MAP):
    raise RuntimeError(f'cannot open {MAP}')
WPL = U.WorldPartitionBlueprintLibrary
descs = [d for d in WPL.get_actor_descs() or [] if str(d.get_editor_property('actor_package')) == PACKAGE]
if len(descs) != 1:
    raise RuntimeError(f'{PACKAGE}: {len(descs)} actors')
WPL.load_actors([descs[0].get_editor_property('guid')])
actor = next(a for a in U.get_editor_subsystem(U.EditorActorSubsystem).get_all_level_actors()
             if a.get_package().get_name() == PACKAGE)
loc, rot, scale = actor.get_actor_location(), actor.get_actor_rotation(), actor.get_actor_scale3d()
U.log(f'V2 TRANSFORM {actor.get_actor_label()} loc {loc.x:.1f},{loc.y:.1f},{loc.z:.1f} '
      f'rot {rot.pitch:.2f},{rot.yaw:.2f},{rot.roll:.2f} scale {scale.x:.3f},{scale.y:.3f},{scale.z:.3f}')
