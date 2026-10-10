#include "GraphMotionConditions.h"
#include <algorithm>
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
bool PhysicalConditionName(std::string_view name)
{
    constexpr std::array<std::string_view,53> names{{
        "LocoState","GroundSlopeType","IsMovingObject","PhysicsWantsRunout","TimeToLand","IsRidingGoofy",
        "IsBodyFlipping","ShouldPlayHandPlantAnim","PhysicsWantsWipeOut","IsBipedGroundThin","ComVelCompare",
        "EnoughDistToObstacle","TrucksOrDeckInContact","IsCrouchedEnoughForBlendToGrabCycle",
        "ShouldPrepareOneFootAirForFootplant","IsFootPlanting","CanLandOnBoard","IsPhysicsWiping",
        "IsHandPlanting","IsEnteringSkitch","IsRetrievingSkateboard","DistToEdge","IsGrabbingObject",
        "PhysicsWantsManualExit","ApexReached","IsHippyHurdling","IsInBipedAir","IsBipedCommittedToMotion",
        "SurfaceSlope","HasNewHandPlantPos","OBTimeToLand","OBTrajTime","DisableDismount",
        "IsStandingOnMovingObject","CanBipedLand","OkToDoTrickOnStairs","IsSkitching","SkateSlope","IsBumped",
        "IsDeckFree","IsHoldingSkateboard","IsGrindBluntingBackslash","GrindTrickOutTypeAllowed","IsGrindApproach",
        "IsLandingIntoGrind","IsDroppingIn","HasLandingType","HasTiltToLargeForPreland","IsDoneWipingOut",
        "WipeoutTimeToLand","WipeoutTimeSinceContact","GestureType","IsInWater"}};
    return std::find(names.begin(),names.end(),name)!=names.end();
}
}
std::uint32_t MotionConditionRandom::Next()
{
    const auto last=words[7],previous=words[6];auto sum=previous+last;
    std::uint32_t carry=sum<last || sum<previous;words[6]=sum;
    for (int index=5;index>=2;--index)
    {const auto value=words[std::size_t(index)];sum=value+sum+carry;carry=sum<value;words[std::size_t(index)]=sum;}
    words[7]=last+1;
    if (words[7]==0) for (int index=6;index>=2;--index) {if (++words[std::size_t(index)]!=0) break;}
    ++words[1];return words[2];
}
bool ParseGraphMotionCondition(const GraphAttributes& a,GraphMotionCondition& output,std::string& error)
{
    GraphMotionCondition c;const auto raw=a.Text("name").value_or("");const auto name=TrimMotionGraphName(raw);
    c.operation_name=std::string(raw);c.numeric=ParseNumericCondition(a);using K=GraphMotionCondition::Kind;
    // The original early families test raw spelling before the trimmed switch.
    if (raw=="IsPushOffEnabled") c.kind=K::PushOff;
    else if (name=="CurrentGrabType")
    {
        const auto grab=a.Text("grab");if (!grab) {error="CurrentGrabType requires grab";return false;}
        if (*grab=="FS") c.grab=MotionGrabType::Fs;else if (*grab=="BS") c.grab=MotionGrabType::Bs;
        else if (*grab=="Nose") c.grab=MotionGrabType::Nose;else if (*grab=="Tail") c.grab=MotionGrabType::Tail;
        else {error="SetGrabType has unknown grab type \""+std::string(*grab)+"\"";return false;}c.kind=K::CurrentGrabType;
    }
    else if (name=="HasTweak") c.kind=K::HasTweak;
    else if (name=="ManualOutTimerIsActive") c.kind=K::ManualOutTimerIsActive;
    else if (name=="HasGestureIntent") {c.kind=K::Gesture;if (!ParseGestureGroup(a.Text("group").value_or(""),c.gesture,error)) return false;}
    else if (name=="ExpireInTime") c.kind=K::ExpireInTime;
    else if (name=="WillExpire")
    {
        c.kind=K::WillExpire;c.in_time=Float(a.FloatBits("InTime",0));c.wait_for_transitions=a.BooleanByte("waitForTransitions",1)!=0;
        if (const auto tag=a.Text("InTimeTag");tag && !tag->empty()) c.tag=std::string(*tag);
    }
    else if (name=="InTimeWindow") {c.kind=K::InTimeWindow;c.start=Float(a.FloatBits("StartTime",0));c.length=Float(a.FloatBits("WindowFrameLength",0));}
    else if (name=="IsProSkater") {c.kind=K::ProSkater;c.encoded=EncodeAnimationName(a.Text("skater").value_or(""));}
    else if (name=="BreakOutOfPush") c.kind=K::BreakOutOfPush;
    else if (name=="ShouldLeaveSlide") {c.kind=K::ShouldLeaveSlide;c.right=a.BooleanByte("right",1)!=0;}
    else if (name=="IsRidingSwitch") c.kind=K::RidingSwitch;
    else if (name=="MongoPushFootToFar") c.kind=K::MongoPushFootTooFar;
    else if (name=="LastState") {c.kind=K::LastState;c.name=a.Text("state").value_or("");}
    else if (raw=="AllowedToTrick") c.kind=K::AllowedToTrick;
    else if (name=="IsInDebugAnimationsMode") c.kind=K::DebugAnimationsMode;
    else if (name=="RandomCond") {if (raw!=name) {error="Unknown riding condition "+std::string(raw);return false;}c.kind=K::Random;}
    else if (name=="IsDark" || name=="IsUnderflipRequested" || name=="IsDarkCatchRequested" || name=="CanEnterSlide" || name=="IsDroppingSkateboard")
    {
        if (raw!=name) {error="Unknown gameplay condition "+std::string(raw);return false;}
        c.kind=name=="IsDark"?K::Dark:name=="IsUnderflipRequested"?K::UnderflipRequested:
            name=="IsDarkCatchRequested"?K::DarkCatchRequested:name=="CanEnterSlide"?K::CanEnterSlide:K::DroppingBoard;
        c.right=a.BooleanByte("right",1)!=0;
    }
    else
    {
        if (!ParseGraphCondition(a,true,c.shared,error)) return false;
        if (c.shared.kind!=GraphCondition::Kind::Unsupported) c.kind=K::Shared;
        else if (PhysicalConditionName(name)) c.kind=K::Unported;
    }
    output=std::move(c);error.clear();return true;
}
bool GraphMotionCondition::Evaluate(const MotionConditionContext& c,const graph::Frame& frame,bool& result,std::string& error) const
{
    using K=Kind;error.clear();const auto& a=c.animation;result=false;
    switch (kind)
    {
    case K::Unsupported:error="Unsupported MotionGraph condition Unsupported { kind: Condition, name: \""+operation_name+"\" }";return false;
    case K::Unported:error="Unported C++ MotionGraph condition "+operation_name;return false;
    case K::Shared:return shared.Evaluate(c.physical.conditions,c.action_intents,a.motion_intents,a.filtered_intents,a.tree.tree_attributes,frame,c.parents,result,error);
    case K::CurrentGrabType:result=a.grab_type==grab;break;
    case K::HasTweak:
    {
        const auto x=a.FilteredIntent("TweakX"),y=a.FilteredIntent("TweakY");
        if (x || y) {const auto vx=x.value_or(0),vy=y.value_or(0);result=numeric.comparison==NumericComparison::None || numeric.Matches(std::sqrt(vx*vx+vy*vy));}break;
    }
    case K::ManualOutTimerIsActive:result=c.riding.manual_out_timer>0;break;
    case K::Gesture:result=HasGestureIntent(gesture,c.action_controls.authored_values);break;
    case K::ExpireInTime:result=numeric.Matches(a.tree.property.remaining_before_wrap);break;
    case K::WillExpire:
    {
        auto time=in_time;
        if (tag && c.time_tags)
        {const auto found=c.time_tags->find(*tag);if (found==c.time_tags->end()) {error="Missing MotionGraph float tag "+*tag;return false;}time=found->second;}
        result=!(wait_for_transitions && a.InTransition()) && (a.tree.property.crossed_end || !(a.tree.property.remaining_before_wrap>time));break;
    }
    case K::InTimeWindow:
        if (!a.InTransition()) {float time;if (!a.CurrentTime(time,error)) return false;result=!(time<start) && !(time>start+length);}break;
    case K::ProSkater:result=c.playback.pro_skater==encoded;break;
    case K::BreakOutOfPush:
    {
        if (!c.push) {error="BreakOutOfPush requires initialized native push state";return false;}
        float time,total;if (!a.CurrentTime(time,error) || !a.CurrentLength(total,error)) return false;
        result=!(time<c.push->out_factor*total) && !c.push->continue_push;break;
    }
    case K::ShouldLeaveSlide:result=c.slide_latch.ShouldLeave(right);break;
    case K::RidingSwitch:
        if (!c.playback.is_switch) {error="IsRidingSwitch requires actual relative stance";return false;}result=*c.playback.is_switch;break;
    case K::MongoPushFootTooFar:
    {
        const auto event=std::find_if(a.tree.tree_attributes.begin(),a.tree.tree_attributes.end(),[](const auto& v){return v.name==EncodeAnimationName("push_contact");});
        if (event==a.tree.tree_attributes.end()) break;
        const auto matches=[&](std::string_view name)
        {const auto key=EncodeAnimationName(name);for (std::size_t i=0;i<5;++i) if (event->payload[i]!=std::optional<std::uint32_t>(key[i])) return false;return true;};
        const bool is_right=matches("RightToeBase"),is_left=matches("LeftToeBase");
        if (!c.playback.is_mirrored) {error="MongoPushFootToFar requires actual mirrored stance";return false;}
        if ((!*c.playback.is_mirrored && is_right) || (*c.playback.is_mirrored && is_left))
        {if (!c.physical.foot_frame) {error="MongoPushFootToFar requires actual foot frame";return false;}result=c.physical.foot_frame->OutDistance(is_right)[0]<-0.5f;}break;
    }
    case K::LastState:
        if (target) {auto cursor=frame.last;while (cursor) {if (*cursor==*target) {result=true;break;}cursor=*cursor<c.parents.size()?c.parents[*cursor]:std::nullopt;}}break;
    case K::Dark:case K::UnderflipRequested:case K::DarkCatchRequested:case K::CanEnterSlide:case K::DroppingBoard:
    {
        if (!c.physical.gameplay) {error="MotionGraph requires the actual physical condition publication";return false;}
        if (kind==K::Dark) result=c.riding.dark;
        else if (kind==K::UnderflipRequested) result=c.trick_requests.underflip;
        else if (kind==K::DarkCatchRequested) result=c.trick_requests.dark_catch;
        else if (kind==K::DroppingBoard) result=c.physical.gameplay->dropping_board || a.channels.Has("RetrieveBoard");
        else if (c.physical.gameplay->state!=102)
        {if (!a.tree.skater_animation_flags) {error="CanEnterSlide requires actual SkaterAnim stance flags";return false;}result=c.slide_latch.Start(right!=((*a.tree.skater_animation_flags&0x20000000)!=0));}break;
    }
    case K::AllowedToTrick:result=c.flags.tricks_allowed;break;
    // PushOff always holds. DebugAnimationsMode is the session's resolved debug
    // gate, distinct from an unsupported leaf.
    case K::PushOff:result=true;break;
    case K::DebugAnimationsMode:result=false;break;
    case K::Random:result=(c.random.Next()&1)==0;break;
    }
    return true;
}
void BindGraphMotionCondition(const Graph& graph,const GraphBinding& binding,const GraphOperation& operation,GraphMotionCondition& condition)
{
    if (condition.kind==GraphMotionCondition::Kind::Shared)
    {BindGraphConditionTarget(graph,binding,operation,condition.shared);return;}
    if (condition.kind!=GraphMotionCondition::Kind::LastState) return;
    std::vector<std::optional<std::uint32_t>> parents(graph.elements.size());
    for (std::size_t i=0;i<graph.elements.size();++i) for (auto child:graph.elements[i].children) parents[child]=std::uint32_t(i);
    auto cursor=parents[operation.element];
    while (cursor)
    {
        const auto found=std::find_if(binding.states.begin(),binding.states.end(),[&](const auto& state){return state.element==*cursor;});
        if (found!=binding.states.end()) {condition.target=binding.FindState(std::uint32_t(found-binding.states.begin()),condition.name,true);return;}
        cursor=parents[*cursor];
    }
}
}
