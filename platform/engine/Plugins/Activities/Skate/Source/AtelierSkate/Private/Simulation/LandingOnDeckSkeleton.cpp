#include "LandingOnDeckRuntime.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
bool LandingOnDeckRuntime::UpdateSkeleton(LandingOnDeckOwners v,Vec4 position,std::string& error)
{
    auto s=v.shared;auto& p=s.processed;
    if(!s.toolkit){error="Landing skeleton requires the completed board toolkit";return false;}
    const auto board=s.toolkit->deck;auto& f=s.physical;const auto old=f.roots.animation_to_world;
    f.roots.initialize_heading=true;float ground_y;std::memcpy(&ground_y,&p.vectors_880_896_912_928_944[0][1],4);
    f.board_frames.skate_root=LandingOnBoardSkateRoot(old,f.skeleton.record.centre_of_mass,p.flags_2480,ground_y,configuration.root);
    f.board_frames.UpdateComLift(old,f.board_frames.centre_of_mass,0);s.animated.motion.trajectory=SkeletonIdentity;
    // Source mutations above survive either packet failure. Inverse trajectory
    // is retained: only the two actual packet bone0 matrices are cleared.
    if(v.pose.hierarchy.empty()){error="Landing packet has no trajectory bone";return false;}
    v.pose.hierarchy[0]=SkeletonIdentity;
    if(v.pose.local.empty()){error="Landing packet has no local trajectory bone";return false;}
    v.pose.local[0]=SkeletonIdentity;
    const auto revert=(v.pose.flags&0x10000000)!=0?std::optional<std::uint32_t>{static_cast<std::uint32_t>(v.pose.air_dismount_revert_frames)}:std::nullopt;
    UpdateLandingOnBoardRoot(f.roots,position,f.animation_record.centre_of_mass,state.applied_spin,revert,(p.flags_2476&4)!=0);
    const auto target=ComposeSkeletonAffine(f.roots.animation_to_world,f.drive_frames[0]);f.board_frames.animation_target=target;p.flags_2468|=0x80000;
    if((p.flags_2480&0x8000)!=0)f.board_frames.physical_board=s.skeleton_air.ApplyBoard(f.board,target,true);
    const auto collision=BipedRuntimeCollision(f);std::array<Mat4,24> drives;
    if(!s.skeleton_input.GeneralUpdate(p,s.SkeletonOwners(),s.hierarchy,collision,drives,error))return false;
    FinishBipedReckoning(v.biped.skeleton_state,{f.roots.animation_to_world[1],board[2],.5f},f.riding,s.air_reckoning,p,s.animation_input.extra.physical_body_spin);
    s.animated.FinishGround();s.animation_input.fields.flags2468=p.flags_2468;error.clear();return true;
}
}
