#pragma once
#include "GraphMotionName.h"
#include "Graph.h"
#include "MotionAnimation.h"
#include "WipeoutOrientation.h"
#include <variant>
namespace atelier::skate
{
struct MotionGraphMatchCadenceState
{
    float captured_phase=0;
    bool pending=false;
    void Begin(std::optional<float> physical_phase,bool animation_present);
    void Update(MotionAnimation* animation);
};
struct MotionGraphOffboardAirTiming {float remaining,duration;Vec4 translation;};
struct MotionGraphMatchAirTimeState
{
    float cadence_start=0,duration=0;
    Vec4 translation{};
    bool first_update=false;
    void Begin(float cadence,float new_duration,Vec4 new_translation);
    void Update(MotionAnimation&,MotionGraphOffboardAirTiming);
};
struct MotionGraphRunoutObservation
{
    bool offboard_flag_331;
    Vec4 offboard_velocity_128,reckoning_velocity_16,reckoning_up_96,skeleton_vector_0;
    bool animation_mirrored;
};
struct MotionGraphRunoutState
{
    float angle_degrees=0;
    std::optional<float> speed;
    void Begin(const std::optional<MotionGraphRunoutObservation>&);
    bool Update(MotionAnimation* animation,std::string& error) const;
};
using MotionGraphOffboardTimingInstance=std::variant<std::monostate,MotionGraphMatchCadenceState,MotionGraphMatchAirTimeState,MotionGraphRunoutState>;
struct MotionOffboardTimingContext
{
    MotionAnimation& animation;
    float& animation_phase;
    std::optional<float> cadence_phase;
    const std::optional<MotionGraphOffboardAirTiming>& air;
    const std::optional<MotionGraphRunoutObservation>& runout;
};
struct GraphMotionOffboardTimingOperation
{
    enum class Kind {Unsupported,BipedCadence,MatchCadence,MatchAirTime,Runout};
    Kind kind=Kind::Unsupported;
    bool Execute(MotionGraphOffboardTimingInstance&,MotionOffboardTimingContext,std::uint8_t phase,std::string& error) const;
};
MotionGraphOffboardTimingInstance CreateMotionGraphOffboardTimingInstance(const GraphMotionOffboardTimingOperation&);
bool ParseGraphMotionOffboardTimingOperation(const GraphAttributes&,GraphMotionOffboardTimingOperation&,bool& recognized,std::string& error);
}
