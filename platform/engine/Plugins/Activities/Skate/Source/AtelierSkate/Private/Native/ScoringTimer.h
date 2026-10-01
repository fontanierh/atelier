// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <array>
#include <utility>
namespace atelier::skate
{
struct ScoringPointTimer
{
    float points{};
    bool expired{};
    bool Advance(float dt,float drain,float scale,bool hold_near_one);
    void Credit(float reward,float capacity);
    float Seconds(float drain) const {return points/drain;}
};
struct ScoringComboTimer
{
    ScoringPointTimer timer{};
    float multiplier{1};
    void Credit(float reward,float capacity,const std::array<std::pair<float,float>,3>& levels,float refresh);
};
}
