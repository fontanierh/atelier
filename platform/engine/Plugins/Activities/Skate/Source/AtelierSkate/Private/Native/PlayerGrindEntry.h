// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "PlayerGrindContact.h"
namespace atelier::skate
{
struct PlayerGrindEntryInput
{
    bool valid;std::uint32_t kind,category,previous_state_2504;float speed,balance_2720;
    Vec4 direction,normal,up,board_velocity,air_velocity;std::uint32_t surface_kind;Vec4 high_side;
    const PointGraph<4>& vertical_help;float max_delta;std::uint32_t flags;Vec4 previous_entry_velocity;
};
struct PlayerGrindEntryOutput {bool valid;std::uint32_t flags;Vec4 entry_velocity;float impact_speed;std::vector<std::size_t> wipeout_reasons;};
struct PlayerGrindEngagement
{
    std::uint32_t tipslide_frames=0;
    PlayerGrindEntryOutput Update(const PlayerGrindEntryInput&);
};
Vec4 PlayerGrindGroundedVelocity(std::uint32_t kind,Vec4 direction,Vec4 velocity,float balance,float speed,const PointGraph<4>&);
Vec4 PlayerGrindAirborneVelocity(std::uint32_t kind,Vec4 direction,Vec4 normal,Vec4 velocity);
std::vector<std::size_t> PlayerGrindAirborneRejections(Vec4 direction,Vec4 up,Vec4 board_velocity,Vec4 air_velocity,Vec4 corrected,
    std::uint32_t surface_kind,Vec4 surface_side,float max_delta);
}
