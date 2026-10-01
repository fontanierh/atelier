// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "PlayerStateConditioning.h"
#include "PlayerStateRegistry.h"
#include "PlayerStateSelector.h"
#include <array>
#include <optional>
#include <string_view>
namespace atelier::skate
{
// The host PostInput history. Query, grind and trajectory owners remain shared;
// these four trajectory fields observe their completed publications.
struct PlayerPostInputState
{
    RawVector jump_reference{};
    std::uint32_t jump_fix_frames=1000,latch_frames=0,state_frames=100;
    float heading_adjust=0;
    bool complete=false,trajectory_pending=false,trajectory_valid=false,
        trajectory_available=false,trajectory_new_candidate=false;
};
// One coordinator-owned player state. All phase adapters borrow this lifecycle,
// selector, conditioner and flag array; they must not retain shadow histories.
// Selected-state entry/update/fill dispatch is supplied by the frame coordinator.
class PlayerStateRuntime
{
public:
    PlayerStateRegistry registry;
    PhysicalPlayerStateLifecycle lifecycle{PhysicalStateId::Sleeping};
    StateSelector selector;
    PhysicalStateId requested_state=PhysicalStateId::Sleeping;
    // Contains the sole source filtering history, plus the existing shared
    // landing-quality publication. Its settings load is a separate host stage.
    PlayerStateConditioning conditioning;
    std::optional<PhysicsGroundOutput> ground_output;
    PlayerPostInputState post;
    std::array<bool,36> state_flags{};
    std::uint32_t state_count=0,update_count=0;
    TwoStageThresholds normal_off_ground{},skitching_off_ground{};
    float animated_board_threshold=0;
    bool initialized=false;

    // Original PlayerState::load ignores mode and publishes only a fully
    // constructed owner. Failed ordered reads never expose a partial owner.
    static std::optional<PlayerStateRuntime> Load(const SettingsDatabase&,
        std::string_view mode,std::string& error);
    PhysicalStateId Current() const {return lifecycle.Active().state;}
    void ResetForTeleport();
};
}
