#include "AnimationPlaybackParameters.h"
#include <cstring>

namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits) {float value;std::memcpy(&value,&bits,4);return value;}
bool Refresh(const std::vector<PlaybackParameter>& parameters,bool beginning,PlaybackService& service,std::string& error)
{
    // Read/write effects stay interleaved: later parameters see earlier writes.
    for (const auto& parameter:parameters) if (!parameter.Update(beginning,service,service,error)) return false;
    error.clear();return true;
}
}
bool PlaybackParameter::Update(bool beginning,PlaybackParameterInputs& inputs,PlaybackAttributeSink& output,std::string& error) const
{
    AttributeName name{};std::optional<float> value;bool is_normalized=false;
    switch (source)
    {
        case PlaybackParameterSource::MotionIntent:
            name=rename.value_or(EncodeAnimationName(intent));value=inputs.MotionIntent(intent);if (!value) value=default_value;is_normalized=normalized;break;
        case PlaybackParameterSource::FilteredIntent:
            name=rename.value_or(EncodeAnimationName(intent));value=inputs.FilteredIntent(intent);is_normalized=value.has_value() && normalized;if (!value) value=default_value;break;
        case PlaybackParameterSource::LastAnimation:
        {
            if (!beginning) {error.clear();return true;}
            std::optional<AnimationAttribute> found;if (!inputs.LastAttribute(last_animation,found,error)) return false;
            if (found)
            {
                if (found->kind!=0 && found->kind!=2) {error.clear();return true;}
                if (!found->payload[0]) {error="Last animation scalar payload is uninitialized";return false;}
                value=Float(*found->payload[0]);
            } else value=default_value;
            name=rename.value_or(last_animation);break;
        }
    }
    if (value) output.SetAttribute({name,*value,is_normalized,-1});error.clear();return true;
}
bool PlayAnimationInstance::Begin(const PlayAnimation& operation,PlaybackContext& context,PlaybackService& service,std::string& error)
{
    first_update_=true;if (!Refresh(operation.parameters,true,service,error)) return false;
    service.SetConstructionValue(EncodeAnimationName("ProSkater"),context.pro_skater);
    auto transition=operation.transition;
    if (context.transition_override && context.transition_override->kind!=0) transition=*context.transition_override;
    context.transition_override.reset();const std::string* animation=&operation.animation;
    if (operation.switch_animation)
    {
        if (!context.is_switch) {error="PlayAnimation needs skater switch state";return false;}
        if (*context.is_switch) animation=&*operation.switch_animation;
    }
    if (operation.mirror_animation)
    {
        if (!context.is_mirrored) {error="PlayAnimation needs skater mirror state";return false;}
        if (*context.is_mirrored) animation=&*operation.mirror_animation;
    }
    if (operation.no_board_animation)
    {
        if (!context.board_available) {error="PlayAnimation needs PhysOut board availability";return false;}
        if (!*context.board_available) animation=&*operation.no_board_animation;
    }
    service.SetPostureEnabled(operation.apply_posture);bool played=false;
    if (transition.kind>=1 && transition.kind<=4)
        if (!service.Play({*animation,operation.playback_speed,0,transition},played,error)) return false;
    if (!played)
    {
        auto fallback=operation.transition;fallback.kind=1;
        if (!service.Play({"KeepDefaultAnim",1,0,fallback},played,error)) return false;
    }
    error.clear();return true;
}
bool PlayAnimationInstance::Update(const PlayAnimation& operation,PlaybackService& service,std::string& error)
{
    if (!first_update_ && !Refresh(operation.parameters,false,service,error)) return false;
    first_update_=false;error.clear();return true;
}
}
