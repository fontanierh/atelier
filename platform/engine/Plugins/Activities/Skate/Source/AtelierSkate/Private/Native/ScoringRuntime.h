// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "ScoringData.h"
#include "ScoringCarrier.h"
namespace atelier::skate
{
enum class ScoringCollector {None,Ground,Air,Grind,Offboard,Special};
struct ScoringFrame
{
    std::uint32_t tick{},category{},state{},flags{};
    float dt{};
    std::optional<AttributeName> descriptor;
    std::int32_t grind_id{-1};
    std::array<float,3> position{},velocity{},forward{};
    bool switch_stance{},fakie{},nollie{},body_flip{},suspend_air{},teleported{},reverting{};
    bool landing_data_167{};
    std::uint32_t landing_type_96{};
    float sideways_speed_84{},spin_92{};
};
struct ScoringRuntimeState
{
    ScoringCollector collector{ScoringCollector::None};
    std::array<std::optional<ScoringCarrier>,4> carriers{};
    std::array<float,4> held{},distance{},metric_rewards{};
    std::array<bool,4> metric_started{};
    std::array<float,3> start{},previous{};
    float previous_heading{},spin{},peak{},air_factor{1},air_repetition{1};
    bool air_repetition_set{};
    std::uint32_t grab_chain{};
    std::array<float,5> air_metrics{};
    std::uint32_t landing_countdown{},idle_ticks{},collector_ticks{},manual_revert_ticks{};
    std::optional<std::size_t> revert_id;
    bool sequence_active{};
    float sequence_score{};
    std::string trick_name;
    std::array<bool,4> stance{};
    // The host's display (not the original's state): the stance the announced trick started in, and an announce count.
    std::array<bool,2> start_stance{};
    std::uint32_t announces{};
    bool clean{},sketchy{},new_trick{},modified_trick{},close_tricks{};
};
class ScoringRuntime
{
public:
    ScoringData data;
    ScoringSession session;
    bool Load(const SettingsDatabase&,std::string& error);
    bool Advance(const ScoringFrame&,std::string& error);
    const ScoringRuntimeState& State() const {return state_;}
    const std::string& CurrentTrick() const {return state_.trick_name;}
private:
    ScoringRuntimeState state_;
    float Penalty(std::size_t id) const;
    void Finish(std::size_t slot,bool complete,bool keep_metric);
    bool Carrier(std::size_t slot,std::optional<std::size_t> id,const ScoringFrame&,std::string& error);
};
}
