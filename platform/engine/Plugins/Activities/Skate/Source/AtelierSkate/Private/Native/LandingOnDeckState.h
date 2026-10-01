// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "LandingDeck.h"
namespace atelier::skate
{
struct LandingOnDeckSettings
{
    float minimum_auto_angle=0,automatic_speed=0,input_speed=0,input_delta=0,automatic_delta=0,maximum_landing_speed=0;
};
struct LandingOnDeckEntry
{
    std::uint32_t previous_category;bool hippy;float strength;
    Vec4 board_position,com_position,com_velocity,board_velocity,up,hips_up,animation_right;bool reversed;
};
// State503 owns alignment decisions; the caller passes the same Manager68
// used by BipedAir. It never owns a second landing trajectory.
struct LandingOnDeckState
{
    std::optional<LandingDeckUpdateOutput> output;
    float time_to_land=0;bool dangerous=false,near_deck=false,turning=false,hippy=false;
    std::int32_t takeoff_frames=0;float spin_rate=0,applied_spin=0,transition_angle=0,accumulated_spin=0;
    std::int32_t half_turns=0,next_half_turns=0;
    void Enter(LandingDeckManager&,LandingOnDeckEntry);
    void Align(const LandingOnDeckSettings&,Vec4 board_forward,Vec4 animation_forward,float state_time,float com_velocity_y,float input_spin);
    void AdvanceSpin(LandingDeckUpdateOutput);
    static float AccurateTime(float board_y,float board_velocity_y,float com_velocity_y,std::array<float,2> toe_y,std::uint32_t wheel_contacts);
    void Finish(const LandingOnDeckSettings&,float com_velocity_y);
    std::int32_t LandingHalfTurns() const{return time_to_land>=.05f?half_turns:next_half_turns;}
    bool RequestsBoardFlip() const{return turning&&time_to_land<.02f;}
};
}
