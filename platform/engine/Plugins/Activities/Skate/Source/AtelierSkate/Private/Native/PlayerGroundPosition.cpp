// SPDX-License-Identifier: Apache-2.0
#include "PlayerGroundPosition.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Vec4 Rotate(const std::array<Vec4,3>& basis,Vec4 point)
{
    Vec4 result;for(std::size_t i=0;i<4;++i){const float x=basis[0][i]*point[0];const float xy=std::fma(basis[1][i],point[1],x);result[i]=std::fma(basis[2][i],point[2],xy);}return result;
}
}
Vec4 PlayerWheelGroundPosition(const std::array<Vec4,4>& wheels,const Mat4& ground)
{
    std::array<Vec4,3> transpose;for(std::size_t axis=0;axis<3;++axis)transpose[axis]={ground[0][axis],ground[1][axis],ground[2][axis],0};
    std::array<Vec4,4> local;for(std::size_t i=0;i<4;++i)local[i]=Rotate(transpose,wheels[i]);
    Vec4 mean;for(std::size_t i=0;i<4;++i)mean[i]=(((local[0][i]+local[1][i])+local[2][i])+local[3][i])*0.25f;
    const float first=local[1][1]>local[0][1] ? local[0][1] : local[1][1];
    const float next=local[2][1]-first>=0.0f ? first : local[2][1];
    mean[1]=local[3][1]-next>=0.0f ? next : local[3][1];
    return Rotate({ground[0],ground[1],ground[2]},mean);
}
RawVector PlayerGroundPosition(const BoardRuntime& board,const Mat4& ground)
{
    std::array<Vec4,4> wheels;for(std::size_t i=0;i<4;++i){const auto p=board.Bodies()[i].rates.position;wheels[i]={p.x,p.y,p.z,0};}
    const auto point=PlayerWheelGroundPosition(wheels,ground);RawVector raw;for(std::size_t i=0;i<4;++i)std::memcpy(&raw[i],&point[i],4);return raw;
}
}
