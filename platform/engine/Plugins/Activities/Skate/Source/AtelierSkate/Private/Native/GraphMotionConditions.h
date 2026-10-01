// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GraphGestureOperations.h"
#include "GraphMotionName.h"
#include "InputIntentions.h"
#include "MotionAnimation.h"
#include "MotionFrame.h"

namespace atelier::skate
{
class MotionConditionRandom
{
public:
    // Original literal821642B0; reset825953B0 preserves this generator.
    std::array<std::uint32_t,8> words{{0,0,0xf22d0e56,0x883126e9,0xc624dd2f,0x0702c49c,0x9e353f7d,0x6fdf3b64}};
    std::uint32_t Next();
};
struct MotionConditionContext
{
    const MotionAnimation& animation;
    const GraphActionControls& action_controls;
    const IntentMap& action_intents;
    const MotionGraphPhysicalPublication& physical;
    const MotionGraphRidingState& riding;
    const MotionGraphFlags& flags;
    const MotionGraphTrickRequests& trick_requests;
    const SlideLatch& slide_latch;
    const PlaybackContext& playback;
    const std::optional<MotionGraphPushState>& push;
    const std::optional<std::map<std::string,float>>& time_tags;
    const std::vector<std::optional<graph::Id>>& parents;
    MotionConditionRandom& random;
};
struct GraphMotionCondition
{
    enum class Kind
    {
        Unsupported,Unported,Shared,CurrentGrabType,HasTweak,ManualOutTimerIsActive,
        Gesture,ExpireInTime,WillExpire,InTimeWindow,ProSkater,BreakOutOfPush,
        ShouldLeaveSlide,RidingSwitch,MongoPushFootTooFar,LastState,
        Dark,UnderflipRequested,DarkCatchRequested,CanEnterSlide,DroppingBoard,
        AllowedToTrick,PushOff,DebugAnimationsMode,Random
    };
    Kind kind=Kind::Unsupported;
    std::string operation_name,name;
    GraphCondition shared;
    NumericCondition numeric;
    MotionGrabType grab=MotionGrabType::Fs;
    GestureGroup gesture=GestureGroup::Square;
    std::optional<graph::Id> target;
    std::optional<std::string> tag;
    AttributeName encoded{};
    float in_time=0,start=0,length=0;
    bool wait_for_transitions=true,right=true;
    bool Evaluate(const MotionConditionContext&,const graph::Frame&,bool& result,std::string& error) const;
};
bool ParseGraphMotionCondition(const GraphAttributes&,GraphMotionCondition&,std::string& error);
void BindGraphMotionCondition(const Graph&,const GraphBinding&,const GraphOperation&,GraphMotionCondition&);
}
