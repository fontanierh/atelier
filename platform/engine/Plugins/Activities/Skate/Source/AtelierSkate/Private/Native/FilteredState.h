// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GrindFilteredOutput.h"
namespace atelier::skate
{
enum class FilteredCategory:std::uint32_t {Invalid=0,Ground=1,Air=2,Grind=3,Wipeout=4,Teleport=5,Offboard=6,OffboardAir=7};
// The physical Grind owner already defines this exact publication transport.
using FilteredGrindState=GrindFilteredOutput;
FilteredGrindState ResetFilteredGrindState();
struct FilteredStateInput
{
    std::int32_t physics_category,physics_state;
    bool anything_in_contact;
    std::int32_t physics_surface_type;
    bool wall_ride_exit,targeting_grind,offboard_has_landed,offboard_on_deck;
    FilteredGrindState grind;
    float last_grind_distance;
};
struct FilteredStateOutput
{
    FilteredCategory category,previous_category;
    bool grinding;
    FilteredGrindState grind;
    float last_grind_distance;
};
class FilteredState
{
public:
    FilteredCategory category=FilteredCategory::Invalid,previous_category=FilteredCategory::Invalid;
    std::int32_t previous_physics_state=0,air_count=0,nonspecific_count=0;
    std::int32_t nonspecific_collision_free_count=0,nonspecific_collision_count=0,frames_since_ground_stairs=0;
    bool must_change=true;
    void Reset();
    FilteredStateOutput Update(FilteredStateInput);
    const FilteredGrindState& CachedGrind() const {return cached_grind_;}
private:
    FilteredGrindState cached_grind_=ResetFilteredGrindState();
};
}
