"""The minimal World Partition test map (plan P1 steps 3 and 6): one engine cube and a player start.

Proves the committed-content path end to end without donor content: a World Partition map, its One File Per
Actor packages under __ExternalActors__, Git LFS upload and download, and region ownership by label. Run once
by the bootstrap writer through `editor.run`; rerunning on an existing map changes nothing.
"""
import unreal as U

MAP = '/Game/V2/Maps/TestMinimal'
REGION = 'region/test-minimal'
LES = U.get_editor_subsystem(U.LevelEditorSubsystem)
EAS = U.get_editor_subsystem(U.EditorActorSubsystem)

if U.EditorAssetLibrary.does_asset_exist(MAP):
    U.log(f'{MAP} exists; nothing to do')
else:
    if not LES.new_level(MAP, True):
        raise RuntimeError(f'cannot create {MAP}')
    cube = EAS.spawn_actor_from_class(U.StaticMeshActor, U.Vector(0, 0, 50))
    cube.static_mesh_component.set_static_mesh(U.EditorAssetLibrary.load_asset('/Engine/BasicShapes/Cube'))
    cube.set_actor_label(f'{REGION}:Cube')
    cube.tags = [U.Name('V2Id:test-minimal-cube'), U.Name(f'V2Region:{REGION}')]
    start = EAS.spawn_actor_from_class(U.PlayerStart, U.Vector(-300, 0, 120))
    start.set_actor_label(f'{REGION}:PlayerStart')
    start.tags = [U.Name('V2Id:test-minimal-start'), U.Name(f'V2Region:{REGION}')]
    if not U.EditorLoadingAndSavingUtils.save_dirty_packages(True, True):
        raise RuntimeError('could not save the test map')
    for actor in (cube, start):
        U.log(f'V2 SAVED {actor.get_package().get_name()}')
