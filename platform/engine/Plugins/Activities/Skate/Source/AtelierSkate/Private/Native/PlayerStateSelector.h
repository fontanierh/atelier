// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "PhysicalPhase.h"
namespace atelier::skate
{
// Complete player/selector/*.rs decision tree for TU3 0x82D8ADE8.
// Threshold and producer records are supplied by the actual physical owner.
struct BoardBodyState {float field_856,field_7692;};
struct TwoStageThresholds {float field_856_primary,field_856_secondary,field_7692;};
struct SkeletonAnimationState {std::uint32_t mode_16420;float back_chain_lane_12656,threshold_800;};
bool StateConditionOffGroundSkitching(BoardBodyState,TwoStageThresholds);
bool StateConditionOffGround(BoardBodyState,TwoStageThresholds);
bool StateIsSkateboardAnimated(SkeletonAnimationState);
struct ProcessedStateInput
{
    std::uint32_t grind_type_1248;bool grind_candidate_1488;std::int32_t field_1776;
    std::uint32_t flags_2468,flags_2472,flags_2476,flags_2480,flags_2484,flags_2488,category_2512;
    std::int32_t wheel_contact_count_2556;std::uint32_t field_2572;
    float state_timer_2664,field_2732,field_2744,trajectory_collision_time_2772;
    std::uint32_t grind_investigation_flags_1516;
    bool Has2468(std::uint32_t mask) const {return (flags_2468&mask)!=0;}
    bool Has2472(std::uint32_t mask) const {return (flags_2472&mask)!=0;}
    bool Has2476(std::uint32_t mask) const {return (flags_2476&mask)!=0;}
    bool Has2480(std::uint32_t mask) const {return (flags_2480&mask)!=0;}
    bool Has2484(std::uint32_t mask) const {return (flags_2484&mask)!=0;}
    bool Has2488(std::uint32_t mask) const {return (flags_2488&mask)!=0;}
    PhysicalStateId AirVariant() const {return Has2468(0x400) ? PhysicalStateId::KnownAir : PhysicalStateId::PhysicsAir;}
};
struct StateSelectionInput
{
    ProcessedStateInput processed;
    std::uint8_t skateboard_contact_count_869;
    BoardBodyState board_body;
    SkeletonAnimationState skeleton;
    TwoStageThresholds skitching_off_ground,normal_off_ground;
};
struct StateSelector
{
    // These fields are the source state-changer's persistent history, including
    // wrapping signed counters. They are not reset when selecting another state.
    std::optional<PhysicalStateId> current_state;
    std::int32_t nonspecific_collision_free_frames=0,nonspecific_collision_frames=0,something_colliding_frames=0,two_wheel_counter=0,three_wheel_counter=0,post_grind_jump_counter=0,air_frames=0,teleport_countdown=0,skitch_exit_countdown=0;
    bool revert_exited_normally=false,request_teleport=false;
    bool Calculate(PhysicalStateId,const StateSelectionInput&,PhysicalStateId& result,std::string& error);
private:
    struct Facts {bool colliding,wipeout,force_known_air,skateboard_animated,off_ground,off_ground_skitching;std::optional<PhysicalStateId> grind;};
    PhysicalStateId CalculateValid(PhysicalStateId,const StateSelectionInput&);
    PhysicalStateId SelectGround(PhysicalStateId,const StateSelectionInput&,Facts);
    PhysicalStateId SelectPhysicsAir(PhysicalStateId,const StateSelectionInput&,Facts) const;
    PhysicalStateId SelectKnownAir(PhysicalStateId,const StateSelectionInput&,Facts) const;
    PhysicalStateId SelectGrind(const StateSelectionInput&,Facts) const;
    PhysicalStateId SelectBipedPlant(PhysicalStateId,const StateSelectionInput&,Facts) const;
    PhysicalStateId SelectNonspecific(PhysicalStateId,const StateSelectionInput&,Facts) const;
};
}
