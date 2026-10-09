#include "SkeletonBiped.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
Mat4 PrepareBipedSkeletonAirRoot(SkeletonRootFrames& roots,Mat4 frame,Vec4 position,Vec4 local,const Mat4& mapped,
    std::uint32_t flags2476,std::uint32_t& flags2468)
{
    roots.initialize_heading=true;if((flags2476&4)!=0)for(const auto axis:{0u,2u})for(auto& v:frame[axis])v=-v;
    for(unsigned n=0;n<4;++n){const auto x=frame[0][n]*local[0],y=std::fma(frame[1][n],local[1],x);frame[3][n]=position[n]-std::fma(frame[2][n],local[2],y);}
    roots.ResetInitialAlignment(OrthonormalizeSkeletonFrame(frame));flags2468|=0x80000;return ComposeSkeletonAffine(roots.animation_to_world,mapped);
}
bool UpdateBipedSkeletonAir(SkeletonInputRuntime& input,SkeletonAir& air,BipedSkeletonAirInput data,const BipedSkeletonState& settings,
    ProcessedPhysicsInput& p,SkeletonInputOwners owners,const std::vector<Mat4>& globals,const SkeletonInputCollision& collision,
    AirReckoning& reckoning,Mat4& target,std::string& error)
{
    auto& physical=owners.physical;physical.board_frames.skate_root=ComposeSkeletonAffine(physical.roots.animation_to_world,physical.animation_record.pose[0]);
    physical.board_frames.UpdateComLift(physical.roots.animation_to_world,data.body_target_416,data.lift_436);
    const auto result=PrepareBipedSkeletonAirRoot(physical.roots,data.frame_208,data.trajectory_position_272,physical.animation_record.centre_of_mass,
        physical.drive_frames[0],p.flags_2476,p.flags_2468);physical.board_frames.animation_target=result;
    if((p.flags_2480&0x8000)!=0)physical.board_frames.physical_board=air.ApplyBoard(physical.board,result,true);
    std::array<Mat4,24> drives;if(!input.GeneralUpdate(p,owners,globals,collision,drives,error))return false;
    FinishBipedReckoning(settings,{physical.roots.animation_to_world[1],data.board_forward_96,.5f},physical.riding,reckoning,p,owners.animation_input.extra.physical_body_spin);
    owners.animated.FinishGround();owners.animation_input.fields.flags2468=p.flags_2468;target=result;return true;
}
}
