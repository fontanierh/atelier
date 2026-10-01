// SPDX-License-Identifier: Apache-2.0
#include "SkeletonBiped.h"
#include "BipedGroundState.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
Mat4 PrepareBipedSkeletonGroundFrames(SkeletonRootFrames& roots,SkeletonBoardFrames& boards,const Mat4& animation_board,
    const Mat4& mapped,BipedSkeletonState& state,BipedSkeletonGroundInput input,std::uint32_t flags2476,std::uint32_t flags2484,std::uint32_t& flags2468)
{
    boards.skate_root=ComposeSkeletonAffine(roots.animation_to_world,animation_board);const std::uint32_t w=0x3e75c28f;float lift;std::memcpy(&lift,&w,4);
    boards.UpdateComLift(roots.animation_to_world,input.centre_of_mass_1056,lift);const auto world=EffectiveBipedRoot(input.world_frame,flags2476);
    roots.initialize_heading=true;roots.ResetInitialAlignment(world);if((flags2484&1)==0)state.retained_board=mapped;flags2468|=0x80000;
    const auto target=ComposeSkeletonAffine(world,state.retained_board);boards.animation_target=target;return target;
}
bool UpdateBipedSkeletonGround(SkeletonInputRuntime& input,SkeletonAir& air,BipedSkeletonGroundInput data,BipedSkeletonState& state,
    ProcessedPhysicsInput& p,SkeletonInputOwners owners,const std::vector<Mat4>& globals,const SkeletonInputCollision& collision,
    AirReckoning& reckoning,Mat4& target,std::string& error)
{
    auto& physical=owners.physical;const auto result=PrepareBipedSkeletonGroundFrames(physical.roots,physical.board_frames,physical.animation_record.pose[0],
        physical.drive_frames[0],state,data,p.flags_2476,p.flags_2484,p.flags_2468);
    if((p.flags_2480&0x8000)!=0||(p.flags_2484&1)!=0)physical.board_frames.physical_board=air.ApplyBoard(physical.board,result,true);
    std::array<Mat4,24> drives;if(!input.GeneralUpdate(p,owners,globals,collision,drives,error))return false;
    owners.animated.FinishGround();const auto root=physical.roots.animation_to_world;
    FinishBipedReckoning(state,{root[1],root[2],.5f},physical.riding,reckoning,p,owners.animation_input.extra.physical_body_spin);
    owners.animation_input.fields.flags2468=p.flags_2468;target=result;return true;
}
}
