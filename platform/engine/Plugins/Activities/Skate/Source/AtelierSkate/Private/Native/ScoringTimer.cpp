// SPDX-License-Identifier: Apache-2.0
#include "ScoringTimer.h"
#include "NativeMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
bool ScoringPointTimer::Advance(float dt,float drain,float scale,bool hold_near_one)
{
    expired=false;
    if(points>0)
    {
        const auto previous=points;points=-((drain*dt)*scale-points);
        if(hold_near_one&&points<1.001f&&previous>1.000001f)
        {points=previous;return true;}
        if(points<=0){points=0;expired=true;}
    }
    return false;
}
void ScoringPointTimer::Credit(float reward,float capacity)
{points=VectorMin(points+reward,capacity);}
void ScoringComboTimer::Credit(float reward,float capacity,const std::array<std::pair<float,float>,3>& levels,float refresh)
{
    timer.Credit(reward,capacity);float next=1;
    for(const auto& level:levels)if(timer.points>=level.first)next=level.second;
    if(next>multiplier||reward>refresh)multiplier=next;
}
}
