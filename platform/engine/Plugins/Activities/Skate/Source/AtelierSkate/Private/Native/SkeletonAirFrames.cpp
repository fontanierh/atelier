// SPDX-License-Identifier: Apache-2.0
#include "SkeletonAirFrames.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
Mat4 PrepareAnimatedAirFrames(const SkeletonRootFrames& roots,SkeletonBoardFrames& board,const Mat4& mapped,std::uint32_t& flags)
{
    const auto local=ComposeSkeletonAffine(roots.animation_to_board,mapped);auto placement=SkeletonIdentity;placement[3]=roots.predicted_board_position;
    const auto target=ComposeSkeletonAffine(placement,local);flags|=1u<<19;board.animation_target=target;board.skate_root=target;
    board.UpdateComLift(roots.animation_to_world,board.centre_of_mass,0.0f);return target;
}
void UpdateKnownAirRoots(SkeletonRootFrames& roots,const Mat4& reckoning,Vec4 target_com,Vec4 animation_com,AirDismountRevert revert)
{
    if(roots.initialize_heading)
    {
        roots.heading_alignment=ComposeSkeletonAffine(InverseSkeletonRigid(reckoning),roots.animation_to_world);
        roots.heading_alignment[3]={};roots.initialize_heading=false;
    }
    if(revert.requested)
    {
        const std::uint32_t word=0x40490fdb;float pi;std::memcpy(&pi,&word,4);float angle=pi/static_cast<float>(revert.frames);if(!revert.goofy)angle=-angle;
        const auto [sine,cosine]=SinCos(angle);const Mat4 rotation{{{cosine,0,-sine,0},{0,1,0,0},{sine,0,cosine,0},{0,0,0,0}}};
        roots.heading_alignment=OrthonormalizeSkeletonFrame(ComposeSkeletonAffine(roots.heading_alignment,rotation));
    }
    UpdatePlantRoots(roots,reckoning,target_com,animation_com);
}
Mat4 PrepareKnownAirFrames(const SkeletonRootFrames& roots,SkeletonBoardFrames& board,const Mat4& mapped,std::uint32_t& flags)
{
    const auto target=ComposeSkeletonAffine(roots.animation_to_world,mapped);flags|=1u<<19;board.animation_target=target;return target;
}
void FinishKnownAirFrames(SkeletonRootFrames& roots,SkeletonBoardFrames& board,Mat4 effective)
{
    board.physical_board=effective;board.skate_root=effective;board.UpdateComLift(roots.animation_to_world,board.centre_of_mass,0.0f);
    roots.predicted_board_position=effective[3];roots.supplied_prediction=effective[3];
}
void UpdatePlantRoots(SkeletonRootFrames& roots,const Mat4& reckoning,Vec4 world_anchor,Vec4 animation_anchor)
{
    auto world=ComposeSkeletonAffine(reckoning,roots.heading_alignment);
    for(unsigned lane=0;lane<4;++lane)
    {
        const float x=world[0][lane]*animation_anchor[0],y=std::fma(world[1][lane],animation_anchor[1],x);
        world[3][lane]=world_anchor[lane]-std::fma(world[2][lane],animation_anchor[2],y);
    }
    roots.animation_to_world=OrthonormalizeSkeletonFrame(world);roots.world_to_animation=InverseSkeletonRigid(roots.animation_to_world);
}
}
