#pragma once
#include "GraphConditions.h"
#include "NativeMath.h"
#include <array>
#include <map>

namespace atelier::skate
{
// Immutable transport from graph_host/outputs.rs. These zero fallbacks are
// authored-control projections, never substitutes for physical publications.
struct GraphWipeoutControls
{
    bool request=false;
    std::array<float,2> air_body_tweak{};
    std::optional<std::array<float,2>> gesture;
};
struct GraphBoardControls {bool drop_requested=false,throw_requested=false,retrieve_requested=false;};
struct GraphActionControls
{
    GraphWipeoutControls wipeout;
    GraphBoardControls board;
    IntentMap authored_values;
    bool Has(std::string_view name) const {return authored_values.Contains(name);}
    std::optional<float> Value(std::string_view name) const
    {const auto p=authored_values.Get(name);return p?std::optional<float>(*p):std::nullopt;}
};
struct GraphTurningOutput {float turn=0,raw_turn=0,hard_turn=0;};
struct ActionGraphInput
{
    std::uint64_t tick=0;
    IntentMap controls,prior_motion;
    std::vector<AnimationAttribute> animation_attributes;
};
struct ActionGraphOutput
{
    std::uint64_t tick=0;
    GraphActionControls controls;
    IntentMap motion_effects;
    GraphTurningOutput turning;
    std::vector<AnimationAttribute> animation_attributes;
    // The pinned producer publishes an empty vector; it is not inferred from
    // intent spelling or a presentation transform.
    std::vector<std::uint32_t> state_requests;
    static ActionGraphOutput FromHost(std::uint64_t,const IntentMap&,const IntentMap&,
        const std::vector<AnimationAttribute>&);
};
struct MotionGraphInput {std::uint64_t tick=0;ActionGraphOutput action;};

// Exact gameplay condition publication from motion_gameplay_conditions.rs.
// The optional containing record stays absent until physics completes it.
struct MotionGraphGameplayInputs
{
    std::uint32_t state;
    bool wants_runout,physics_wiping,body_flipping,wants_wipeout,bumped;
    bool grabbing_object,retrieving_board,dropping_board,in_biped_air,hippy_hurdling;
    std::uint32_t handplant_flags;
    float handplant_time;
    std::array<float,3> handplant_thresholds;
    bool footplant_active;
    float footplant_duration,footplant_contact_time,time_to_skitch,skitch_transition_time;
    float time_to_land;
    bool time_to_land_valid;
    float offboard_time_to_land,offboard_air_scalar_92;
    Vec4 offboard_air_translation,offboard_landing_normal;
    bool offboard_committed_to_motion;
    float offboard_obstacle_distance,offboard_edge_distance,offboard_trajectory_time;
    bool offboard_trajectory_valid,reached_apex,can_land_on_board,landing_turning;
    bool grind_contact,wheel_contact,trucks_or_deck_contact,moving_object,tricks_blocked_on_stairs;
};
struct MotionGraphFootFrame
{
    Vec4 left_foot,right_foot,deck_position,deck_y,deck_z;
    bool skateboard_flipped;
    std::array<float,2> OutDistance(bool right_foot) const;
};
struct MotionGraphPhysicalPublication
{
    GraphConditionInputs conditions;
    std::optional<MotionGraphGameplayInputs> gameplay;
    std::optional<MotionGraphFootFrame> foot_frame;
    std::optional<std::pair<bool,bool>> physical_stance;
    std::optional<std::uint32_t> offboard_locomotion_state,ground_slope_type;
    std::optional<bool> biped_ground_thin,holding_board,free_board,manual_exit;
    std::optional<float> animation_height_72;
};
struct MotionGraphFlags
{
    // Original825953B0 clears bits30..27 and sets bit25.
    bool anticipating=false,landing=false,manualing=false,doing_trick=false,tricks_allowed=true;
};
struct MotionGraphTrickRequests {bool underflip=false,dark_catch=false;};
struct MotionGraphPushBlend {float hstr_vel_b=0,lstr_vel_b=0,vel_e=0;};
struct MotionGraphPushState
{
    // Complete constructor/reset initializes the actual graph owner to zero.
    float out_factor=0,current_push_dv=0;
    MotionGraphPushBlend current,target;
    bool continue_push=false;
};
struct MotionGraphRidingState
{
    float time_since_teleport=0,time_since_kickturn=0,manual_out_timer=0;
    bool dark=false;
    float last_good_landing_velocity=0;
    std::optional<std::uint32_t> force_mode;
};
}
