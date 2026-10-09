#pragma once
#include "Graph.h"
#include "MotionAnimation.h"
namespace atelier::skate
{
struct MotionAnimationOperation
{
    enum class Kind {Unsupported,Play,CreateAttribute};
    Kind kind=Kind::Unsupported;
    PlayAnimation play;
    AttributeName attribute{};
    std::array<std::optional<float>,3> values{};
    bool set=false;
};
struct MotionAnimationOperationState {PlayAnimationInstance play;};
bool ParseMotionAnimationOperation(const GraphAttributes&,MotionAnimationOperation&,bool& recognized,std::string& error);
bool AddMotionAnimationParameter(MotionAnimationOperation&,const GraphAttributes&,std::string& error);
bool ExecuteMotionAnimationOperation(const MotionAnimationOperation&,MotionAnimationOperationState&,std::uint8_t phase,PlaybackContext&,MotionAnimation&,std::string& error);
}
