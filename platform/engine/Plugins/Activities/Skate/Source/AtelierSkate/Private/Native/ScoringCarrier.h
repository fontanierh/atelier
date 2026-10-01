// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "ScoringCore.h"
namespace atelier::skate
{
std::uint32_t ScoringDelayTicks(float authored_seconds,float extra_seconds);
struct ScoringCarrier
{
    ScoringScorable scorable{};
    std::int32_t points{};
    float factor{},reward{},announcement_threshold{};
    std::uint32_t start_tick{},delay_ticks{};
    bool announced{},completed{},unannounced{},switch_stance{},fakie{};
    static ScoringCarrier Create(ScoringScorable,std::int32_t points,float factor,float announcement_threshold,
        std::uint32_t start_tick,std::uint32_t delay_ticks,bool switch_stance,bool fakie);
    bool Announce(std::uint32_t tick,float unannounced_factor);
    bool Complete(float unannounced_factor);
    void ConvertTo(ScoringCarrier& replacement,float unannounced_factor);
private:
    void Credit(float unannounced_factor);
};
}
