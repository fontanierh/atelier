#!/usr/bin/env python3
"""Exercise cooked-content adapters and callbacks in the running editor game.

Run alongside skate_runtime, skatepark and skate_performance in one game session.
The asset builder separately proves collision words, materials and animation output.
"""
import argparse
import json
import struct
import time
import skate as qa


def diagnostics():
    return json.loads(qa.py('print(live.L.skate_diagnostics())').strip())


def wait_for(predicate, timeout=30):
    end = time.monotonic() + timeout
    last = {}
    while time.monotonic() < end:
        last = diagnostics()
        if predicate(last):
            return last
        time.sleep(.2)
    raise RuntimeError('Skating adapter did not reach expected state: ' + json.dumps(last))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8830)
    args = parser.parse_args()
    # Reuse the live bridge's supported runtime spawn verb. Unreal's internal
    # deferred-spawn Blueprint functions are not exported to Python.
    fixture_path = qa.yori.OUT / 'skateqa/fixture.glb'
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    binary = struct.pack('<9f3H', 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 2)
    gltf = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}],
            'nodes': [{'mesh': 0}], 'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'indices': 1}]}],
            'buffers': [{'byteLength': len(binary)}],
            'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': 36},
                            {'buffer': 0, 'byteOffset': 36, 'byteLength': 6}],
            'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 3, 'type': 'VEC3'},
                          {'bufferView': 1, 'componentType': 5123, 'count': 3, 'type': 'SCALAR'}]}
    encoded = json.dumps(gltf, separators=(',', ':')).encode()
    encoded += b' ' * (-len(encoded) % 4)
    binary += b'\0' * (-len(binary) % 4)
    fixture_path.write_bytes(struct.pack('<3I', 0x46546C67, 2, 28 + len(encoded) + len(binary))
                            + struct.pack('<2I', len(encoded), 0x4E4F534A) + encoded
                            + struct.pack('<2I', len(binary), 0x004E4942) + binary)
    qa.bridge.URL = f'http://127.0.0.1:{args.port}'
    qa.py((qa.GAME / 'scenarios/skate_live_skate.py').read_text())
    qa.py('live.skate_park(); live.skate_input()')
    before = wait_for(lambda d: d['ready'] and d['node_valid'])
    report = {}

    def record(name, passed, values):
        report[name] = {'ok': bool(passed), 'values': values}
        print(('PASS ' if passed else 'FAIL ') + name + ': ' + json.dumps(values), flush=True)

    record('asset_and_animgraph', before['data_identity'] and before['node_native_graph_root']
           and before['node_base_pose_linked'] and before['node_weight'] == 1
           and before['node_generation'] == before['pose_generation'] and before['node_rejected'] == 0
           and before['missing_collision_meshes'] == 0 and before['collision_triangles'] > 0, before)
    qa.py('live.SKATE_FIXTURE_GLB=' + repr(str(fixture_path)))
    qa.py("""
p=unreal.GameplayStatics.get_player_character(live.L.game_world(),0)
s=p.get_component_by_class(unreal.SkateComponent)
profile=s.get_editor_property('profile')
def skate_set_profile(candidate):
    result=s.set_profile_report(candidate)
    return [result.get_editor_property('accepted'),result.get_editor_property('failure')]
live.SKATE_EVENTS=[]
def skate_mode_event(previous,current): live.SKATE_EVENTS.append([str(previous),str(current)])
s.on_mode_changed.add_callable(skate_mode_event)
def skate_fixture(mesh):
    location=p.get_actor_location()+unreal.Vector(0,1800,300)
    bounds=mesh.get_bounds()
    scale=min(1,500/max(bounds.box_extent.x,bounds.box_extent.y,bounds.box_extent.z,1))
    location=location-bounds.origin*scale
    a=unreal.LiveLibrary.spawn_model('skate-fixture',live.SKATE_FIXTURE_GLB,location,0,1,'none','')
    if a is None: raise RuntimeError('Could not spawn the skating collision fixture')
    c=a.get_component_by_class(unreal.StaticMeshComponent)
    c.set_mobility(unreal.ComponentMobility.MOVABLE)
    c.set_static_mesh(mesh)
    c.set_world_scale3d(unreal.Vector(scale,scale,scale))
    c.set_collision_profile_name('BlockAll')
    return a
live.SKATE_FIXTURE=skate_fixture(unreal.load_asset('/Game/SkatePark/SM_SkatePath'))
""")
    try:
        added = wait_for(lambda d: d['collision_refreshes'] > before['collision_refreshes'])
        qa.py('live.SKATE_FIXTURE.set_actor_location(live.SKATE_FIXTURE.get_actor_location()+unreal.Vector(100,0,0),False,True)')
        moved = wait_for(lambda d: d['collision_refreshes'] > added['collision_refreshes'])
        qa.py('live.SKATE_FIXTURE.destroy_actor(); live.SKATE_FIXTURE=None')
        removed = wait_for(lambda d: d['collision_refreshes'] > moved['collision_refreshes'])
        record('stationary_scene_refresh', removed['ready'] and removed['missing_collision_meshes'] == 0,
               {'refreshes': [before['collision_refreshes'], added['collision_refreshes'],
                              moved['collision_refreshes'], removed['collision_refreshes']]})
    finally:
        qa.py('if live.SKATE_FIXTURE: live.SKATE_FIXTURE.destroy_actor(); live.SKATE_FIXTURE=None')

    result = json.loads(qa.py('print(json.dumps(skate_set_profile(profile)))').strip().splitlines()[-1])
    record('profile_change_requires_walking', not result[0] and bool(result[1]), result)
    qa.py('s.toggle()')
    off = wait_for(lambda d: not d['node_valid'])
    qa.py("""
bad_profile=unreal.new_object(unreal.SkateProfile)
invalid=skate_set_profile(bad_profile)
unchanged=s.get_editor_property('profile')==profile
bad_board=unreal.new_object(unreal.SkateProfile)
for field in ('runtime_data','collision_data_catalog','deck_mesh','truck_mesh','wheel_mesh'):
    bad_board.set_editor_property(field,profile.get_editor_property(field))
bad_board.set_editor_property('deck_mesh',unreal.SoftObjectPath('/Game/SkateNative/MissingBoard.MissingBoard'))
invalid_board=skate_set_profile(bad_board)
board_unchanged=s.get_editor_property('profile')==profile
valid=skate_set_profile(profile)
""")
    result = json.loads(qa.py('print(json.dumps({"invalid":invalid,"unchanged":unchanged,"invalid_board":invalid_board,"board_unchanged":board_unchanged,"valid":valid,"events":live.SKATE_EVENTS}))').strip().splitlines()[-1])
    record('profile_change_atomic', not result['invalid'][0] and result['unchanged']
           and not result['invalid_board'][0] and result['board_unchanged'] and result['valid'][0], result)
    qa.py('s.toggle()')
    on = wait_for(lambda d: d['ready'] and d['node_valid'] and d['pose_generation'] > before['pose_generation'])
    record('remount_generation', on['node_generation'] == on['pose_generation'] and off['node_weight'] == 0,
           {'before': before['pose_generation'], 'off': off['pose_generation'], 'after': on['pose_generation']})

    # Force this uncatalogued engine mesh to request complex collision; its
    # normal box shape is valid without a bake. Restore the flag without saving.
    # Recovery runs inside the failure
    # delegate, proving obsolete cleanup cannot tear down its new session.
    qa.py("""
live.SKATE_FAILURES=[]
bad_mesh=unreal.load_asset('/Engine/BasicShapes/Cube')
live.SKATE_BAD_BODY=bad_mesh.get_editor_property('BodySetup')
live.SKATE_BAD_TRACE=live.SKATE_BAD_BODY.get_editor_property('CollisionTraceFlag')
def recover_skate_failure(message):
    live.SKATE_FAILURES.append(str(message))
    if live.SKATE_FIXTURE:
        live.SKATE_FIXTURE.destroy_actor(); live.SKATE_FIXTURE=None
    live.SKATE_BAD_BODY.set_editor_property('CollisionTraceFlag',live.SKATE_BAD_TRACE)
    s.set_profile(profile)
    live.park.place(-25,38,0)
s.on_runtime_failure.add_callable(recover_skate_failure)
live.SKATE_BAD_BODY.set_editor_property('CollisionTraceFlag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
live.SKATE_FIXTURE=skate_fixture(bad_mesh)
""")
    try:
        recovered = wait_for(lambda d: d['ready'] and d['node_valid'] and d['pose_generation'] > on['pose_generation'])
        values = json.loads(qa.py('print(json.dumps({"failures":live.SKATE_FAILURES,"events":live.SKATE_EVENTS}))').strip().splitlines()[-1])
        record('failure_callback_recovery', len(values['failures']) == 1 and recovered['missing_collision_meshes'] == 0, values)
    finally:
        qa.py("""s.on_runtime_failure.remove_callable(recover_skate_failure)
s.on_mode_changed.remove_callable(skate_mode_event)
live.SKATE_BAD_BODY.set_editor_property('CollisionTraceFlag',live.SKATE_BAD_TRACE)
if live.SKATE_FIXTURE: live.SKATE_FIXTURE.destroy_actor(); live.SKATE_FIXTURE=None""")

    # Simulate streaming away the final colliders. Restore them inside the
    # failure callback so recovery also proves the old world was discarded.
    qa.py("""
live.SKATE_EMPTY_FAILURES=[]
live.SKATE_DISABLED_COLLISION=[]
def restore_skate_collision():
    for component, enabled in live.SKATE_DISABLED_COLLISION:
        if unreal.SystemLibrary.is_valid(component):
            component.set_collision_enabled(enabled)
    live.SKATE_DISABLED_COLLISION=[]
def recover_empty_skate_world(message):
    live.SKATE_EMPTY_FAILURES.append(str(message))
    restore_skate_collision()
    s.set_profile(profile)
    live.park.place(-25,38,0)
s.on_runtime_failure.add_callable(recover_empty_skate_world)
for actor in unreal.GameplayStatics.get_all_actors_of_class(live.L.game_world(),unreal.Actor):
    for component in actor.get_components_by_class(unreal.StaticMeshComponent):
        enabled=component.get_collision_enabled()
        if enabled != unreal.CollisionEnabled.NO_COLLISION:
            live.SKATE_DISABLED_COLLISION.append((component,enabled))
            component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
""")
    try:
        restored = wait_for(lambda d: d['ready'] and d['node_valid']
                            and d['pose_generation'] > recovered['pose_generation'])
        values = json.loads(qa.py('print(json.dumps(live.SKATE_EMPTY_FAILURES))').strip().splitlines()[-1])
        record('empty_scene_discards_collision', len(values) == 1
               and 'contains no triangles' in values[0] and restored['collision_triangles'] > 0, values)
    finally:
        qa.py('s.on_runtime_failure.remove_callable(recover_empty_skate_world); restore_skate_collision()')
    qa.py('live.skate_park(); live.skate_release()')
    output = qa.yori.OUT / 'skateqa/unreal.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    return 0 if all(v['ok'] for v in report.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
