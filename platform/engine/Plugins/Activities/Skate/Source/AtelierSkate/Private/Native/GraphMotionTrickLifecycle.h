// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "Graph.h"
#include "GraphMotionSpecialConditions.h"
#include "GraphMotionName.h"
#include "MotionAnimation.h"
#include "MotionFrame.h"
#include <variant>
namespace atelier::skate
{
struct MotionGraphTrickLifecycleSettings
{
    PointGraph<8> finger_curve,hippy_height,manual_balance;
    float finger_minimum=0,finger_maximum=0,manual_velocity_limit=0,manual_acceleration_limit=0;
    bool Load(const SettingsDatabase&,std::string& error);
};
struct MotionGraphFingerFlipState {float elapsed=0;float Update(bool grab_present,float dt,const MotionGraphTrickLifecycleSettings&);};
struct MotionGraphHippyJumpState {bool active=false;float elapsed=0;};
struct MotionGraphManualAngleState {float angle=0,velocity=0;float Update(std::optional<float>,const MotionGraphTrickLifecycleSettings&);};
struct MotionGraphStoreLandingState
{
    float previous_velocity=0;
    bool was_air=false;
    void Update(std::uint32_t category,Vec4 com_velocity,Vec4 up,MotionGraphRidingState&);
};
struct MotionGraphLandingHeightState {float height=0;};
struct MotionGraphLandingVelocityPublication {Vec4 com_velocity,system_up;};
struct MotionGraphTrickPhysicalPublication
{
    float footplant_duration,handplant_time;
    std::array<float,3> handplant_thresholds;
    bool landing_turning;
};
using MotionGraphTrickLifecycleInstance=std::variant<std::monostate,MotionGraphFingerFlipState,MotionGraphHippyJumpState,MotionGraphManualAngleState,MotionGraphStoreLandingState,MotionGraphLandingHeightState>;
struct MotionTrickLifecycleContext
{
    MotionAnimation& animation;
    const MotionGraphTrickLifecycleSettings& settings;
    MotionGraphRidingState& riding;
    const std::optional<MotionGraphTrickPhysicalPublication>& physical;
    const std::optional<MotionGraphLandingInputs>& landing;
    const std::optional<MotionGraphLandingVelocityPublication>& native_physical;
    std::optional<std::uint32_t> filtered_category;
    const PlaybackContext& playback;
    float dt;
};
struct GraphMotionTrickLifecycleOperation
{
    enum class Kind {Unsupported,FingerFlip,HippyJump,ManualAngle,FootplantAbsorb,HandplantAntic,LandOnBoard,StoreLanding,SetLanding};
    Kind kind=Kind::Unsupported;
    std::string grab_intent;
    bool Execute(MotionGraphTrickLifecycleInstance&,MotionTrickLifecycleContext,std::uint8_t phase,std::string& error) const;
};
MotionGraphTrickLifecycleInstance CreateMotionGraphTrickLifecycleInstance(const GraphMotionTrickLifecycleOperation&);
bool ParseGraphMotionTrickLifecycleOperation(const GraphAttributes&,GraphMotionTrickLifecycleOperation&,bool& recognized,std::string& error);
}
