#pragma once
#include "GraphMotionName.h"
#include "GraphMotionSpecialConditions.h"
#include "MotionAnimation.h"
#include "MotionFrame.h"
#include <variant>
namespace atelier::skate
{
struct MotionGraphWipeoutControlState
{
    bool seed_from_air_tweak=false,gestures_enabled=false;
    std::array<float,2> gesture{};
};
struct MotionGraphWipeoutSettings
{
    float threshold=0,twist_velocity=0,twist_acceleration=0,lean_velocity=0;
    float twist_blend=0,lean_blend=0,gesture_y_blend=0,gesture_x_blend=0;
    bool Load(const SettingsDatabase&,std::string& error);
};
struct MotionGraphOffboardTweakPhysical {float time_to_land,scalar_92;};
struct MotionGraphOffboardTweakState
{
    std::uint32_t ticks=0;
    std::array<float,2> axes{};
    bool into_started=false,cycle_started=false,released=false;
    void Begin();
};
struct MotionGraphWipeoutState
{
    std::uint32_t ticks=0;
    float lean=0,twist=0,twist_velocity=0;
    std::array<float,2> gesture{};
    bool released=false;
};
struct MotionGraphTwistLeanState {float twist=0,lean=0;};
using MotionGraphOffboardWipeoutInstance=std::variant<std::monostate,MotionGraphOffboardTweakState,MotionGraphWipeoutState,MotionGraphTwistLeanState>;
struct MotionOffboardWipeoutContext
{
    MotionAnimation& animation;
    MotionGraphWipeoutControlState& controls;
    const GraphWipeoutControls& action;
    const MotionGraphWipeoutSettings& settings;
    const std::optional<MotionGraphOffboardTweakPhysical>& tweak_physical;
    const std::optional<MotionGraphWipeoutConditionInputs>& wipeout_physical;
    const PlaybackContext& playback;
};
struct GraphMotionOffboardWipeoutOperation
{
    enum class Kind {Unsupported,BodyTweak,TwistLean,Wipeout,EnableGestures};
    Kind kind=Kind::Unsupported;
    bool always=false;
    std::string nb_cycle="B_OBAIR_BODYTWEAK_NB_CYC",nb_into="B_OBAIR_BODYTWEAK_NB_INTO";
    std::string br_cycle="B_OBAIR_BODYTWEAK_BR_CYC",br_into="B_OBAIR_BODYTWEAK_BR_INTO";
    bool Execute(MotionGraphOffboardWipeoutInstance&,MotionOffboardWipeoutContext,std::uint8_t phase,std::string& error) const;
};
MotionGraphOffboardWipeoutInstance CreateMotionGraphOffboardWipeoutInstance(const GraphMotionOffboardWipeoutOperation&);
bool ParseGraphMotionOffboardWipeoutOperation(const GraphAttributes&,GraphMotionOffboardWipeoutOperation&,bool& recognized,std::string& error);
}
