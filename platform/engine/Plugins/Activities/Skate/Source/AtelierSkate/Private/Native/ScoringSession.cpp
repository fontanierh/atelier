#include "ScoringSession.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
float ScoringSession::PublishSequence(const ScoringSessionRules& rules,float landing,bool penalized,bool enabled)
{
    holder.RewardSequence(landing);const auto& snapshot=holder.State().snapshot;
    auto raw=(snapshot.fingerflip_pending+snapshot.general_pending)+snapshot.accumulated;
    if(penalized&&rules.bail_factor<1)raw*=rules.bail_factor;
    const auto multiplier=enabled?combo.multiplier:1;
    if(enabled)
    {
        combo.Credit(raw,rules.combo_capacity,rules.combo_levels,rules.combo_refresh_threshold);
        const std::uint32_t word=0x3f8147ae;float threshold;std::memcpy(&threshold,&word,4);
        if(combo.multiplier>threshold)line.Credit(raw,rules.line_capacity);
    }
    const auto reward=multiplier*raw;holder.Publish(reward,enabled&&line.points>0);return reward;
}
void ScoringSession::SettleLine(bool reset_requested,bool collector_active)
{
    if(reset_requested||line.expired)
    {line={};combo.multiplier=1;holder.FinishLine();}
    else if(line.points<=0)holder.BankLine(!collector_active);
}
}
