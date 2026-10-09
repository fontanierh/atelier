#include "SkeletonBoardFrames.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Scalar(std::uint32_t bits){float value;std::memcpy(&value,&bits,4);return value;}
}
void SkeletonBoardFrames::Reset(Mat4 spawn)
{
    com_frame=spawn;com_frame[3][1]+=1.0f;lifted_com_frame=com_frame;
    centre_of_mass=spawn[3];local_centre_of_mass={};
}
void SkeletonBoardFrames::PublishLocalObservations(const SkeletonRootFrames& roots,const Mat4& actual_board)
{
    local_centre_of_mass=TransformSkeletonPoint(roots.world_to_animation,centre_of_mass);
    local_board_position=TransformSkeletonPoint(roots.world_to_animation,actual_board[3]);
}
void SkeletonBoardFrames::PublishCentreOfMass(Vec4 com,float dt,std::uint32_t flags_2472)
{
    previous_centre_of_mass=centre_of_mass;centre_of_mass=com;
    float inverse=ReciprocalEstimate(dt);
    for(unsigned n=0;n<2;++n)inverse=std::fma(inverse,std::fma(-inverse,dt,1.0f),inverse);
    for(std::size_t i=0;i<4;++i)com_velocity[i]=(com[i]-previous_centre_of_mass[i])*inverse;
    if(flags_2472&0x400)previous_centre_of_mass=com;
}
Mat4 SkeletonBoardFrames::PrepareGround(const SkeletonRootFrames& roots,const Mat4& mapped_board,Mat4 actual_board,std::uint32_t& flags_2468)
{
    const auto local_target=ComposeSkeletonAffine(roots.animation_to_board,mapped_board);
    auto world_position=SkeletonIdentity;world_position[3]=roots.predicted_board_position;
    animation_target=ComposeSkeletonAffine(world_position,local_target);flags_2468&=~std::uint32_t(0x80000);
    physical_board=actual_board;skate_root=actual_board;
    UpdateComLift(roots.animation_to_world,centre_of_mass,0.0f);return animation_target;
}
Mat4 SkeletonBoardFrames::PrepareTeleport(const SkeletonRootFrames& roots,const Mat4& mapped_board,Mat4 actual_board,std::uint32_t& flags_2468)
{
    const auto local_target=ComposeSkeletonAffine(roots.animation_to_board,mapped_board);
    auto world_position=SkeletonIdentity;world_position[3]=roots.predicted_board_position;
    animation_target=ComposeSkeletonAffine(world_position,local_target);flags_2468&=~std::uint32_t(0x80000);
    physical_board=actual_board;skate_root=actual_board;
    auto position=actual_board[3];position[1]+=1.0f;
    UpdateComLift(roots.animation_to_world,position,0.0f);return animation_target;
}
void SkeletonBoardFrames::UpdateComLift(const Mat4& animation_to_world,Vec4 position,float requested_height)
{
    const float step=Scalar(0x3d23d70a),low=lift_height-step,high=lift_height+step;
    const float above_low=low-requested_height>=0.0f ? low:requested_height;
    lift_height=high-above_low>=0.0f ? above_low:high;
    auto frame=animation_to_world;frame[3]=position;com_frame=OrthonormalizeSkeletonFrame(frame);
    lifted_com_frame=com_frame;const float height=lift_height+Scalar(0x3e99999a);
    for(std::size_t i=0;i<4;++i)lifted_com_frame[3][i]=std::fma(com_frame[1][i],height,com_frame[3][i]);
}
}
