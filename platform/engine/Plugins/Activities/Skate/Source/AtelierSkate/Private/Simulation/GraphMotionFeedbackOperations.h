#pragma once
#include "Graph.h"
#include "GraphController.h"
#include "MotionAnimation.h"
#include "RidingAnimation.h"
#include <variant>
namespace atelier::skate
{
struct GraphMotionFeedbackOperation
{
    enum class Kind {Unsupported,Turning,Crouching,BodyTilt,Fakie,Pumping,DisallowPumping,DeckPitchYaw};
    Kind kind=Kind::Unsupported;
    std::array<AttributeName,5> names{};
    AnimationFakieSettings fakie{1,0.5f,0.2f,3};
};
using GraphMotionFeedbackInstance=std::variant<std::monostate,SetTurningState,
    std::optional<AnimationCrouchingState>,AnimationBodyTiltState,AnimationFakieState,AnimationPumpState>;
struct GraphMotionFeedbackSettings
{
    SetTurningSettings turning;
    AnimationCrouchingSettings crouching;
    AnimationBodyTiltSettings body_tilt;
    AnimationPumpSettings pumping;
};
struct GraphMotionFeedbackOwner {bool allow_pumping=true;};
// All flags are the current graph-owned values at dispatch. Physical pointers
// represent independently absent completed producers, never a default record.
struct GraphMotionFeedbackContext
{
    MotionAnimation& animation;
    GraphMotionFeedbackOwner& owner;
    SlideLatch& slide_latch;
    const GraphMotionFeedbackSettings& settings;
    const SetTurningPhysical* turning=nullptr;
    const AnimationCrouchingPhysical* crouching=nullptr;
    const AnimationBodyTiltPhysical* body_tilt=nullptr;
    const AnimationFakiePhysical* fakie=nullptr;
    const float* pumping_acceleration=nullptr;
    const std::array<float,2>* deck_yaw_pitch=nullptr;
    std::optional<bool> mirrored=std::nullopt;
    bool doing_trick=false,is_power_sliding=false,applying_body_tilt=false;
};
bool ParseGraphMotionFeedbackOperation(const GraphAttributes&,GraphMotionFeedbackOperation&,
    bool& recognized,std::string& error);
GraphMotionFeedbackInstance CreateGraphMotionFeedbackInstance(const GraphMotionFeedbackOperation&);
bool LoadGraphMotionFeedbackSettings(const SettingsDatabase&,GraphMotionFeedbackSettings&,std::string& error);
bool ExecuteGraphMotionFeedbackOperation(const GraphMotionFeedbackOperation&,GraphMotionFeedbackInstance&,
    std::uint8_t phase,const graph::Frame&,GraphMotionFeedbackContext&,std::string& error);
}
