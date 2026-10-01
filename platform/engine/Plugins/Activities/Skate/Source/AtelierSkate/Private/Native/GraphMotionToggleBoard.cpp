// SPDX-License-Identifier: Apache-2.0
#include "GraphMotionToggleBoard.h"
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
void Attribute(MotionAnimation& a,std::string_view name,float value) {a.SetAttribute({EncodeAnimationName(name),value,false,-1});}
void Publish(MotionAnimation& a,std::string_view name) {a.EmitPacket(EncodeAnimationName(name),1);Attribute(a,name,1);}
}
std::string_view MotionGraphToggleBoardClipName(MotionGraphToggleBoardClip clip)
{
    using C=MotionGraphToggleBoardClip;switch (clip) {case C::Throw:return "OFB_THROW_0";case C::Drop:return "OFB_THROW_90";case C::FrontInto:return "OFB_RETRIEVE_HIGH_FRONT_INTO";case C::FrontCycle:return "OFB_RETRIEVE_HIGH_FRONT_CYC";case C::FrontOut:return "OFB_RETRIEVE_HIGH_FRONT_OUT";case C::BackInto:return "OFB_RETRIEVE_HIGH_BACK_INTO";case C::BackCycle:return "OFB_RETRIEVE_HIGH_BACK_CYC";case C::BackOut:return "OFB_RETRIEVE_HIGH_BACK_OUT";}return {};
}
void MotionGraphToggleBoardState::ResetOrientation() {previous_yaw_=0;yaw_=0;pitch_=0;initialized_yaw_=false;back_=false;}
void MotionGraphToggleBoardState::Begin() {phase=MotionGraphToggleBoardPhase::Idle;ResetOrientation();}
void MotionGraphToggleBoardState::Orientation(MotionGraphToggleBoardInput input)
{
    auto yaw=input.yaw_radians*-Float(0x42652ee0);if (input.mirrored) yaw=-yaw;
    if (yaw<-90) {if (initialized_yaw_) yaw=yaw_>=0?180:-90;else yaw=yaw>=-135?-90:180;}
    if (input.mirrored) yaw=-yaw;
    if (initialized_yaw_) {const auto difference=yaw-previous_yaw_,lower=-5-difference>=0?-5:difference,step=5-lower>=0?lower:5;yaw=step+previous_yaw_;}
    previous_yaw_=yaw;yaw_=input.mirrored?-yaw:yaw;pitch_=input.pitch_radians*Float(0x42652ee0);initialized_yaw_=true;back_=std::abs(yaw_)>90;
}
void MotionGraphToggleBoardState::Cycle(MotionGraphToggleBoardOutput& output)
{phase=MotionGraphToggleBoardPhase::RetrieveCycle;output.channel=MotionGraphToggleBoardCommand{MotionGraphToggleBoardCommand::Kind::Sequence,back_?MotionGraphToggleBoardClip::BackCycle:MotionGraphToggleBoardClip::FrontCycle,0};output.retrieve=true;}
void MotionGraphToggleBoardState::Stop(MotionGraphToggleBoardOutput& output)
{phase=MotionGraphToggleBoardPhase::Idle;output.channel=MotionGraphToggleBoardCommand{MotionGraphToggleBoardCommand::Kind::Stop,MotionGraphToggleBoardClip::Throw,Float(0x3e2aaaab)};}
MotionGraphToggleBoardOutput MotionGraphToggleBoardState::Update(MotionGraphToggleBoardInput input,MotionGraphToggleBoardChannel channel)
{
    using P=MotionGraphToggleBoardPhase;using C=MotionGraphToggleBoardClip;using K=MotionGraphToggleBoardCommand::Kind;
    if (!input.grabbing_object && phase==P::Idle)
    {
        if (input.drop_requested && input.holding_board) {phase=P::DropStart;throwing_=false;}
        else if (input.throw_requested && input.holding_board) {phase=P::DropStart;throwing_=true;}
        else if (input.retrieve_requested && !input.holding_board && !input.retrieval_blocked) phase=P::RetrieveStart;
    }
    MotionGraphToggleBoardOutput output;
    switch (phase)
    {
    case P::Idle:ResetOrientation();break;
    case P::DropStart:output.dropping=true;phase=P::DropPlaying;output.channel=MotionGraphToggleBoardCommand{K::Blend,throwing_?C::Throw:C::Drop,0};break;
    case P::DropPlaying:output.dropping=true;if (!channel.exists || channel.remaining<=0 || channel.elapsed>.5f) Stop(output);break;
    default:
        output.retrieving=true;
        switch (phase)
        {
        case P::RetrieveStart:Orientation(input);phase=P::RetrieveInto;output.channel=MotionGraphToggleBoardCommand{K::Blend,back_?C::BackInto:C::FrontInto,0};break;
        case P::RetrieveInto:Orientation(input);if (!channel.exists || channel.remaining<=0) phase=P::Idle;else if (channel.remaining<=.25f) Cycle(output);break;
        case P::RetrieveCycle:Orientation(input);if (!input.retrieval_active) Stop(output);else if (!channel.exists || channel.remaining<=0) phase=P::Idle;else if (input.holding_board) {phase=P::RetrieveOut;output.channel=MotionGraphToggleBoardCommand{K::Blend,back_?C::BackOut:C::FrontOut,0};}else if (channel.remaining<=.25f) Cycle(output);break;
        case P::RetrieveOut:if (!channel.exists || channel.remaining<=0 || channel.elapsed>Float(0x3e2aaaab)) Stop(output);break;
        default:break;
        }
        output.yaw_pitch=std::array<float,2>{yaw_,pitch_};break;
    }
    return output;
}
bool ParseGraphMotionToggleBoard(const GraphAttributes& a,bool& recognized,std::string& error)
{recognized=TrimMotionGraphName(a.Text("name").value_or(""))=="ToggleBoard";error.clear();return true;}
bool ExecuteGraphMotionToggleBoard(MotionGraphToggleBoardState& state,MotionAnimation& animation,const std::optional<MotionGraphToggleBoardPhysical>& physical,std::uint8_t phase,std::string& error)
{
    error.clear();if (phase==0) {state.Begin();return true;}if (phase!=1) return true;
    if (!physical) {error="ToggleBoard requires completed board-possession output (OffBoard36/40/304/311/313 and bundle28 byte87)";return false;}
    if (!animation.tree.skater_animation_flags) {error="ToggleBoard requires the actual animation mirror state";return false;}const auto& p=*physical;
    const auto output=state.Update({p.grabbing_object,p.holding_board,p.retrieval_blocked,p.retrieval_active,animation.motion_intents.Contains("OB_DropBoard"),animation.motion_intents.Contains("OB_ThrowBoard"),animation.motion_intents.Contains("OB_RetrieveBoard"),p.yaw_radians,p.pitch_radians,(*animation.tree.skater_animation_flags&0x40000000u)!=0},
        {animation.channels.Has("RetrieveBoard"),animation.channels.Remaining("RetrieveBoard"),animation.channels.Elapsed("RetrieveBoard")});
    if (output.retrieving) Publish(animation,"OB_RetrievingBoard");if (output.dropping) Publish(animation,"OB_DroppingBoard");
    if (output.channel)
    {
        const auto command=*output.channel;
        if (command.kind==MotionGraphToggleBoardCommand::Kind::Stop) animation.channels.EndWith("RetrieveBoard",command.blend_seconds,false);
        else
        {
            const auto sequence=command.kind==MotionGraphToggleBoardCommand::Kind::Sequence,is_out=command.clip==MotionGraphToggleBoardClip::FrontOut || command.clip==MotionGraphToggleBoardClip::BackOut,hold=sequence||is_out;bool transitioned;
            if (!animation.TransitionChannel("RetrieveBoard",MotionGraphToggleBoardClipName(command.clip),{0,false,false,1,.25f,hold,.25f,hold,true},{sequence?4u:2u,sequence?0:.25f,0,0,false},true,!sequence&&!is_out,transitioned,error)) return false;
        }
    }
    if (output.retrieve) Publish(animation,"OB_RetrieveBoard");if (output.yaw_pitch) {Attribute(animation,"yaw",(*output.yaw_pitch)[0]);Attribute(animation,"pitch",(*output.yaw_pitch)[1]);}return true;
}
}
