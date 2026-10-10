#pragma once
#include "AnimationPlayback.h"

namespace atelier::skate
{
enum class PlaybackParameterSource { MotionIntent, FilteredIntent, LastAnimation };
struct PlaybackParameter
{
    PlaybackParameterSource source=PlaybackParameterSource::MotionIntent;
    std::string intent;
    AttributeName last_animation{};
    std::optional<AttributeName> rename;
    std::optional<float> default_value;
    bool normalized=false;
    bool Update(bool beginning,class PlaybackParameterInputs& inputs,class PlaybackAttributeSink& output,std::string& error) const;
};
class PlaybackParameterInputs
{
public:
    virtual ~PlaybackParameterInputs()=default;
    virtual std::optional<float> MotionIntent(std::string_view name) const=0;
    virtual std::optional<float> FilteredIntent(std::string_view name) const=0;
    virtual bool LastAttribute(AttributeName name,std::optional<AnimationAttribute>& output,std::string& error)=0;
};
class PlaybackAttributeSink
{
public:
    virtual ~PlaybackAttributeSink()=default;
    virtual void SetAttribute(SettableAttribute value)=0;
};
class PlaybackQueueSink:public PlaybackAttributeSink
{
public:
    explicit PlaybackQueueSink(SettableAttributes& values):values_(values) {}
    void SetAttribute(SettableAttribute value) override {values_.SetAttribute(value);}
private:
    SettableAttributes& values_;
};
struct TransitionSettings
{
    std::uint32_t kind=0;
    float seconds=0;
    std::uint32_t under=0, matching=0;
    bool use_channels_from_weights=false;
};
struct PlayAnimation
{
    std::string animation;
    std::optional<std::string> switch_animation, mirror_animation, no_board_animation;
    float playback_speed=0;
    bool apply_posture=false;
    TransitionSettings transition;
    std::vector<PlaybackParameter> parameters;
};
struct PlaybackRequest
{
    std::string animation;
    float speed=0, start_time=0;
    TransitionSettings transition;
};
struct PlaybackContext
{
    std::optional<bool> is_switch, is_mirrored, board_available;
    AttributeName pro_skater{};
    std::optional<TransitionSettings> transition_override;
};
class PlaybackService:public PlaybackParameterInputs,public PlaybackAttributeSink
{
public:
    virtual void SetConstructionValue(AttributeName name,AttributeName value)=0;
    virtual void SetPostureEnabled(bool enabled)=0;
    // Missing implementations report errors. False represents a simulation
    // controller refusal and is the only path to the authored fallback.
    virtual bool Play(const PlaybackRequest& request,bool& played,std::string& error)=0;
};
class PlayAnimationInstance
{
public:
    bool Begin(const PlayAnimation& operation,PlaybackContext& context,PlaybackService& service,std::string& error);
    bool Update(const PlayAnimation& operation,PlaybackService& service,std::string& error);
    void End() {}
private:
    bool first_update_=false;
};
}
