#include "PlayerTeleportRuntime.h"
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Vec4 Float4(RawVector bits)
{Vec4 output;for(unsigned i=0;i<4;++i)std::memcpy(&output[i],&bits[i],4);return output;}
Vec3 XYZ(Vec4 v){return {v[0],v[1],v[2]};}
AffineTransform Affine(Mat4 m)
{
    AffineTransform result;for(unsigned c=0;c<3;++c)for(unsigned i=0;i<3;++i)result.basis.columns[c][i]=m[c][i];
    result.translation=XYZ(m[3]);return result;
}
}
Mat4 HorizontalPlayerTeleportSpawn(Mat4 requested)
{
    auto result=SkeletonIdentity;const auto x=requested[2][0],z=requested[2][2];const float length=std::sqrt(x*x+z*z);
    if(length>0.001f){result[2]={x/length,0,z/length,0};result[0]={result[2][2],0,-result[2][0],0};}
    result[3]=requested[3];result[3][1]+=.1f;return result;
}
bool PlayerTeleportRuntime::ResetPlayer(PlayerInputOwners owners,Mat4 requested,PlayerInputState& player,PhysicalPlayerInput& physical,
    ProcessedPhysicsInput& p,PlayerTeleportFrame frame,std::string& error)
{
    error.clear();auto& runtime=owners.physical;auto& life=lifecycle_;
    if(!life.skeleton_controller.RequestGround(runtime.skeleton_collision,error))return false;
    const auto target=HorizontalPlayerTeleportSpawn(requested);
    player.flags_1296=((player.flags_1296&0xffefffffu)&0x81ffffffu)|0x60000000u;
    player.previous_spin_input_1360=0;player.spin_same_direction_frames_1324=0;player.dismount_request_frames_1332=0;
    player.time_on_ground_1352=0;player.signed_ground_time_1356=0;player.queued_vector_1280={};
    player.hips_line_test_1488={};player.left_line_test_1536={};player.right_line_test_1584={};ResetPhysicalPlayerOutputs(physical);
    runtime.board.ResetPhysical(runtime.settings.board.authored,Affine(target),p.flags_2468,runtime.settings.board.step.simulation.gravity_acceleration);
    life.ground.steering.deck_tilt=0;life.ground.steering.targets={};owners.ground.ResetBoardToolkit();
    life.board_animated_290=0;runtime.board_wiping_out=false;
    life.skeleton_air.ResetBoard();life.footplant.FullReset();life.handplant.FullReset();runtime.riding.ResetForTeleport();
    owners.skeleton_input.ResetForTeleport(owners.SkeletonOwners(),life.wobble,life.skeleton_elapsed_16505);
    frame.collision.contact_4070=runtime.collision_feedback.flags.compliant;
    frame.collision.has_pose_error_4077=runtime.collision_feedback.flags.has_impulse;
    frame.collision.partial_ragdoll=runtime.skeleton_collision.partial_ragdoll;
    frame.collision.drive_weight_4028=runtime.collision_feedback.drive_weight;
    runtime.riding.reckoning.Reset();
    const auto com=runtime.animation_record.com_to_deck_world;const auto normal=Float4(p.vectors_464_480_496_512_528[0]),dynamic=Float4(p.vectors_464_480_496_512_528[4]);
    std::int32_t wheels;std::memcpy(&wheels,&p.wheel_count_2556,4);
    runtime.riding.UpdateGroundReckoning(runtime.board,{{com[0],com[1],com[2]},owners.animation_input.extra.physical_body_spin},
        p.flags_2468,owners.animation_input.fields.balance,false,{XYZ(normal),XYZ(dynamic),p.scalar_2652,p.scalar_2616,wheels});
    life.wipeout.ResetSystems();life.skeleton_controller.effective=0;life.skeleton_controller.requested=0;
    life.skeleton_controller.has_request=false;life.skeleton_controller.override_enabled=false;life.skeleton_controller.flag_18=false;
    life.offboard_grab.Invalidate();player.manager_1856_counter_320=0;player.probe={};
    const auto toolkit=BoardToolkit::FromBoard(runtime.board,p.flags_2468,p.scalar_2612,normal,owners.ground.retained_board_normal);
    owners.ground.retained_board_normal=toolkit.filtered_normal;
    if(!owners.animation_input.SelectPhysicsMode(p.state_variant_index_2528,error))return false;
    if(!owners.skeleton_input.ProcessData(toolkit,frame.packet,physical,p,owners.SkeletonOwners(),frame.pose,frame.collision,error))return false;
    Mat4 ignored_target;
    if(!owners.skeleton_input.UpdateTeleport(runtime.riding.reckoning_frames.system,p,owners.SkeletonOwners(),frame.pose.globals,frame.collision,ignored_target,error))return false;
    life.wipeout.Teleport();frame.teleported=true;error.clear();return true;
}
}
