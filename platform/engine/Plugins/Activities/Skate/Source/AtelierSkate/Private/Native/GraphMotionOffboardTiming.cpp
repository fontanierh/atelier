// SPDX-License-Identifier: Apache-2.0
#include "GraphMotionOffboardTiming.h"
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits) {float value;std::memcpy(&value,&bits,4);return value;}
void Set(MotionAnimation& a,std::string_view name,float value) {a.SetAttribute({EncodeAnimationName(name),value,false,-1});}
Vec4 BoundedAirTranslation(Vec4 vector)
{
    // MatchAirTime's actual source has a standard sqrt/recip seed and ordinary
    // XYZ square sum. It differs from the approximation-based common length.
    const auto squared=(vector[0]*vector[0]+vector[1]*vector[1])+vector[2]*vector[2];auto inverse=1.0f/std::sqrt(squared);
    for (unsigned i=0;i<2;++i) {const auto correction=std::fma(-squared,inverse*inverse,1.0f);inverse=std::fma(inverse*.5f,correction,inverse);}
    const auto length=squared==0?0.0f:squared*inverse;if (length>.01f) {const auto bounded=length-2.0f>=0?2.0f:length;for (auto& v:vector) v*=bounded/length;}return vector;
}
}
void MotionGraphMatchCadenceState::Begin(std::optional<float> phase,bool present) {if (phase&&present) {pending=true;captured_phase=*phase;}}
void MotionGraphMatchCadenceState::Update(MotionAnimation* animation) {if (animation) {Set(*animation,"CadenceStartPercent",captured_phase);pending=false;}}
void MotionGraphMatchAirTimeState::Begin(float cadence,float new_duration,Vec4 new_translation) {first_update=true;cadence_start=cadence;duration=new_duration;translation=new_translation;}
void MotionGraphMatchAirTimeState::Update(MotionAnimation& a,MotionGraphOffboardAirTiming p)
{
    if (!first_update && !(p.duration<=0)) {const auto progress=1.0f-p.remaining/p.duration,lower=-progress>=0?0.0f:progress,fraction=1.0f-lower>=0?lower:1.0f;a.SynchronizeAirTime(fraction);}
    translation=BoundedAirTranslation(p.translation);duration=p.duration;Set(a,"CadenceStartPercent",cadence_start);Set(a,"AnimTime",duration);Set(a,"AnimTransX",translation[0]);Set(a,"AnimTransY",translation[1]);Set(a,"AnimTransZ",translation[2]);first_update=false;
}
void MotionGraphRunoutState::Begin(const std::optional<MotionGraphRunoutObservation>& observation)
{
    if (!observation) return;const auto& p=*observation;const auto velocity=p.offboard_flag_331?p.offboard_velocity_128:p.reckoning_velocity_16;auto angle=WipeoutProjectedAngle(p.skeleton_vector_0,velocity,p.reckoning_up_96);if (p.animation_mirrored) angle=-angle;
    speed=Length3(velocity);angle_degrees=WipeoutWrapAngle(angle)*Float(0x42652ee1);
}
bool MotionGraphRunoutState::Update(MotionAnimation* animation,std::string& error) const
{
    error.clear();if (!animation) return true;if (!speed) {error="AddRunoutAttribs speed12 has no successful Begin observation";return false;}Set(*animation,"BipedStartAngle",angle_degrees);Set(*animation,"BipedSpeed",*speed);return true;
}
MotionGraphOffboardTimingInstance CreateMotionGraphOffboardTimingInstance(const GraphMotionOffboardTimingOperation& op)
{
    using K=GraphMotionOffboardTimingOperation::Kind;switch (op.kind) {case K::MatchCadence:return MotionGraphMatchCadenceState{};case K::MatchAirTime:return MotionGraphMatchAirTimeState{};case K::Runout:return MotionGraphRunoutState{};default:return std::monostate{};}
}
bool ParseGraphMotionOffboardTimingOperation(const GraphAttributes& a,GraphMotionOffboardTimingOperation& output,bool& recognized,std::string& error)
{
    GraphMotionOffboardTimingOperation op;const auto raw=a.Text("name").value_or(""),name=TrimMotionGraphName(raw);using K=GraphMotionOffboardTimingOperation::Kind;recognized=true;error.clear();
    if (name=="BipedCadence") op.kind=K::BipedCadence;else if (name=="MatchCadence") op.kind=K::MatchCadence;
    else if (name=="AddRunoutAttribs" && raw==name) op.kind=K::Runout;
    else if (name=="MatchAirTime") {if (raw!=name) {error="Original stock gameplay operation parser has an unreachable raw-name mismatch";return false;}op.kind=K::MatchAirTime;}
    else recognized=false;output=std::move(op);return true;
}
bool GraphMotionOffboardTimingOperation::Execute(MotionGraphOffboardTimingInstance& state,MotionOffboardTimingContext c,std::uint8_t phase,std::string& error) const
{
    error.clear();using K=Kind;
    switch (kind)
    {
    case K::BipedCadence:if (phase==1 && c.cadence_phase) c.animation_phase=*c.cadence_phase;return true;
    case K::MatchCadence:{auto* s=std::get_if<MotionGraphMatchCadenceState>(&state);if (!s) {error="MatchCadence operation/instance mismatch";return false;}if (phase==0) s->Begin(c.cadence_phase,true);else if (phase==1) s->Update(&c.animation);return true;}
    case K::MatchAirTime:{auto* s=std::get_if<MotionGraphMatchAirTimeState>(&state);if (!s) {error="MatchAirTime operation/instance mismatch";return false;}if (phase!=2) {if (!c.air) {error="MatchAirTime requires completed OffBoard output";return false;}if (phase==0) {if (!c.cadence_phase) {error="MatchAirTime requires completed OffBoard80";return false;}s->Begin(*c.cadence_phase,c.air->duration,c.air->translation);}else s->Update(c.animation,*c.air);}return true;}
    case K::Runout:{auto* s=std::get_if<MotionGraphRunoutState>(&state);if (!s) {error="Runout operation/instance mismatch";return false;}if (phase==0) {s->Begin(c.runout);return true;}return s->Update(&c.animation,error);}
    case K::Unsupported:error="Unbound MotionGraph offboard timing operation";return false;
    }
    error="Unbound MotionGraph offboard timing operation";return false;
}
}
