#pragma once
#include "AnimationChannels.h"
#include "Intents.h"
namespace atelier::skate
{
enum class MotionGrabType {Fs,Bs,Nose,Tail};
class MotionAnimation final:public PlaybackService
{
public:
    explicit MotionAnimation(AnimationMetadata metadata);
    AnimationTreeOwner tree;
    AnimationChannels channels;
    IntentMap motion_intents,filtered_intents;
    std::vector<MotionGraphAttribute> motion_attributes;
    std::optional<MotionGrabType> grab_type;
    std::uint32_t natural_stance=1,relative_stance=0,requested_stance=0;
    bool reset_action_intents=false;
    void BeginGraphUpdate();
    void AcceptMotionEffects(const IntentMap& effects);
    void EmitPacket(AttributeName name,float value);
    void Attach(std::string_view intent,AttributeName attribute,bool set);
    void SetGrabType(MotionGrabType value);
    void ClearGrabType();
    bool CurrentTime(float& output,std::string& error) const;
    bool CurrentLength(float& output,std::string& error) const;
    bool InTransition() const;
    void SynchronizeAirTime(float fraction);
    bool JumpInto(AttributeName name,std::string& error);
    bool NewChannel(std::string_view name,std::string_view animation,ChannelSettings settings,bool& created,std::string& error);
    bool TransitionChannel(std::string_view name,std::string_view animation,ChannelSettings settings,TransitionSettings transition,bool resurrect,bool create_missing,bool& transitioned,std::string& error);
    void ResetFromStock();
    bool ResetToGivenStance(std::string& error);
    bool StockClipTranslationZ(std::string_view database,std::string_view animation,float& output,std::string& error) const;
    bool Advance(float dt,float phase,std::string& error);
    bool ApplyParameters(std::string& error);
    bool EvaluatePose(AnimationEvaluation parameters,std::vector<PoseCommand>& output,std::string& error);
    bool RefreshTreeAttributes(std::string& error);
    std::optional<float> MotionIntent(std::string_view name) const override;
    std::optional<float> FilteredIntent(std::string_view name) const override;
    bool LastAttribute(AttributeName name,std::optional<AnimationAttribute>& output,std::string& error) override;
    void SetAttribute(SettableAttribute value) override;
    void SetConstructionValue(AttributeName name,AttributeName value) override;
    void SetPostureEnabled(bool enabled) override;
    bool Play(const PlaybackRequest& request,bool& played,std::string& error) override;
};
}
