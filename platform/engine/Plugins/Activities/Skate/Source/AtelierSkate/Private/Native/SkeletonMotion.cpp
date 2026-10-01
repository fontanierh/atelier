// SPDX-License-Identifier: Apache-2.0
#include "SkeletonMotion.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
void SkeletonMotion::ProcessTrajectory(const Mat4& bone,const Mat4& animation_to_world,float dt)
{
    trajectory=ComposeSkeletonAffine(bone,next_trajectory);next_trajectory=trajectory;
    float reciprocal=ReciprocalEstimate(dt);for(unsigned i=0;i<2;++i){const float error=std::fma(-reciprocal,dt,1.0f);reciprocal=std::fma(reciprocal,error,reciprocal);}
    Vec4 velocity;for(unsigned i=0;i<4;++i)velocity[i]=trajectory[3][i]*reciprocal;
    for(unsigned i=0;i<4;++i){const float x=animation_to_world[0][i]*velocity[0],y=std::fma(animation_to_world[1][i],velocity[1],x);velocity_world[i]=std::fma(animation_to_world[2][i],velocity[2],y);}
    const auto source=trajectory;inverse_trajectory={};for(unsigned axis=0;axis<3;++axis)inverse_trajectory[axis]={source[0][axis],source[1][axis],source[2][axis],0.0f};
    for(unsigned lane=0;lane<4;++lane){const float z=(0.0f-source[3][2])*inverse_trajectory[2][lane],y=std::fma(0.0f-source[3][1],inverse_trajectory[1][lane],z);inverse_trajectory[3][lane]=std::fma(0.0f-source[3][0],inverse_trajectory[0][lane],y);}
}
void SkeletonMotion::PublishUnadjustedBoard(const Mat4& board,std::uint32_t& flags)
{
    const std::uint32_t word=0x3f35c28f;float threshold;std::memcpy(&threshold,&word,4);if(std::fabs(board[0][1])>threshold)flags|=0x8000;
}
float SkeletonMotion::PublishAdjustedBoard(const Mat4& board,std::uint32_t& flags)
{
    const float y=board[2][1],delta=y-previous_board_at_y;previous_board_at_y=y;const bool positive=y>0.0f;
    flags=(flags&~0x1800u)|(std::uint32_t(positive)<<12)|(std::uint32_t(!positive)<<11);return delta;
}
}
