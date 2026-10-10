#pragma once
#include "InputIntentions.h"
#include "Settings.h"

namespace atelier::skate
{
// Distinct production-host implementation from graph_host/motion_sliding.rs.
// Do not substitute the core PowerSliding state for this owner.
struct GraphMotionSlidingSettings
{
    float speed_threshold, well_into_slide;
    PointGraph<4> speed_factor, time_threshold, threshold;
    PointGraph<8> speed_to_lean, phys_to_anim_spin;
    float smooth, minimum_entry, turn;
    bool Load(const SettingsDatabase&,std::string& error);
};
struct GraphMotionSlidingState
{
    float not_sliding_time = 0, previous_right = 0, previous_left = 0;
    bool was_ground = false, was_right_start = false, was_left_start = false;
    void Update(const IntentMap& motion,std::uint32_t category,float speed,float direction,float dt,
        const GraphMotionSlidingSettings&,SlideLatch& output);
};
float GraphMotionSlideDirection(Vec4 velocity,Vec4 z,bool flipped);
std::array<float,2> CreateGraphMotionSlide(const SlideLatch&,bool authored_right,std::optional<float> right_intent,
    std::optional<float> left_intent,const GraphMotionSlidingSettings&);
float GraphMotionSlideDeceleration(float& previous,Vec4 velocity,const Mat4& ground,const GraphMotionSlidingSettings&);
float GraphMotionSlideSpin(float direction,const GraphMotionSlidingSettings&);
}
