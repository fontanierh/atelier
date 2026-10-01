// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "ScoringCore.h"
#include "ScoringTimer.h"
namespace atelier::skate
{
struct ScoringSessionRules
{
    float combo_capacity{};
    std::array<std::pair<float,float>,3> combo_levels{};
    float combo_refresh_threshold{},line_capacity{},bail_factor{};
};
struct ScoringSession
{
    ScoringHolder holder{};
    ScoringComboTimer combo{};
    ScoringPointTimer line{};
    float PublishSequence(const ScoringSessionRules&,float landing_factor,bool penalized,bool multiplier_enabled);
    void SettleLine(bool reset_requested,bool collector_active);
};
}
