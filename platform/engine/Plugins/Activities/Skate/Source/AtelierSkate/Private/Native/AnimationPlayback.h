#pragma once
#include "AnimationName.h"
#include "AnimationMetadata.h"
#include "AnimationSamples.h"
#include "NativeMath.h"
#include <optional>
#include <utility>

namespace atelier::skate
{
struct AdvanceResult { bool crossed_end=false; float overshoot=0, remaining_before_wrap=0; };
struct ClipClock
{
    float frames=0, fps=0, base_speed=0, speed=0, length=0, time=0, previous_time=0;
    std::uint32_t loops_since_evaluation=0;
    bool looping=false, phase_controlled=false;
    void SetTime(float value);
    void SetSpeed(float value);
    float SampleTime() const;
    bool Advance(float dt,float phase,AdvanceResult& result,std::string& error);
    void CommitEvaluation();
    std::uint8_t AttributeStatus(float begin,float end) const;
};
using AttributePayload=std::array<std::optional<std::uint32_t>,6>;
struct AnimationAttribute
{
    AttributePayload payload{};
    float begin_time=0, end_time=0;
    AttributeName name{};
    std::uint8_t status=0, kind=0;
    std::int32_t sequence_id=0;
    // Preserve inactive destination lanes; native assignment copies only active lanes.
    void CopyFrom(const AnimationAttribute& source);
};
struct MotionGraphAttribute
{
    AttributeName name{};
    float value=0;
    AnimationAttribute ToAnimation() const;
};
class PacketAttributes
{
public:
    void Clear() { active_len_=0; }
    void Append(const AnimationAttribute& source);
    void ReplaceFrom(const std::vector<MotionGraphAttribute>& motion_graph,const std::vector<AnimationAttribute>& tree);
    const AnimationAttribute& operator[](std::size_t index) const { return slots_.at(index); }
    std::size_t Size() const { return active_len_; }
private:
    std::vector<AnimationAttribute> slots_;
    std::size_t active_len_=0;
};
struct PlaybackClipAttribute
{
    AttributeName name{};
    std::uint8_t kind=0;
    float begin=0, end=0;
    std::vector<std::uint32_t> payload;
};
class PlaybackClip
{
public:
    ClipClock clock;
    std::vector<PlaybackClipAttribute> attributes;
    PlaybackClip(float frames,float fps,float base_speed,std::uint32_t flags,std::vector<PlaybackClipAttribute> values);
    explicit PlaybackClip(const ClipMetadata& metadata);
    bool Advance(float dt,float phase,AdvanceResult& result,std::string& error);
    bool Attributes(std::uint32_t mask,std::vector<AnimationAttribute>& output,std::string& error) const;
    bool Attribute(AttributeName name,std::uint32_t mask,std::optional<AnimationAttribute>& output,std::string& error) const;
private:
    bool Materialize(const PlaybackClipAttribute& attribute,std::uint8_t status,AnimationAttribute& output,std::string& error) const;
};
bool SampleAnimationCurve(const std::vector<std::uint32_t>& words,float time,float& output,std::string& error);
bool BlendAnimationAttribute(AnimationAttribute& left,const AnimationAttribute& right,float weight,std::string& error);
bool ScaleAnimationAttribute(AnimationAttribute& attribute,float weight,std::string& error);
bool AddWeightedAnimationAttribute(AnimationAttribute& left,const AnimationAttribute& right,float weight,std::string& error);
bool IntersectAnimationAttributes(const std::vector<AnimationAttribute>& left,const std::vector<AnimationAttribute>& right,float weight,std::vector<AnimationAttribute>& output,std::string& error);
class AttributeMirror
{
public:
    std::vector<std::pair<AttributeName,AttributeName>> names;
    bool Apply(AnimationAttribute& attribute,std::string& error) const;
};
struct SettableAttribute { AttributeName name{}; float value=0; bool normalized=false; std::int32_t sequence_id=0; };
class SettableAttributes
{
public:
    const std::vector<SettableAttribute>& Entries() const { return entries_; }
    void Clear() { entries_.clear(); }
    void SetAttribute(SettableAttribute value);
private:
    std::vector<SettableAttribute> entries_;
};
struct SelectionParameter
{
    AttributeName name{};
    std::uint32_t mode=0;
    float weight=0, minimum=0, maximum=0;
};
float SelectionDistance(const std::vector<SelectionParameter>& parameters,const std::vector<float>& values,const std::vector<float>& candidate);
struct ChannelSettings
{
    std::int32_t priority=0;
    bool keep_alive=false, mirrored=false;
    float speed=0, blend_in=0;
    bool hold_during_blend_in=false;
    float blend_out=0;
    bool hold_during_blend_out=false, use_attributes=false;
};
class ChannelPlayback
{
public:
    explicit ChannelPlayback(ChannelSettings value);
    ChannelSettings settings;
    float weight=0, influence=1;
    bool Expired() const;
    void End();
    void EndWith(float seconds,bool from_last_frame);
    bool CanTransition(bool resurrect) const;
    void Transition(ChannelSettings value,bool resurrect);
    bool Advance(float dt,float length,float time);
    void DidAdvance(AdvanceResult value);
    std::vector<AnimationAttribute> MergeAttributes(const std::vector<AnimationAttribute>& base,const std::vector<AnimationAttribute>& channel) const;
private:
    float blend_in_elapsed_=0, blend_out_elapsed_=0, resurrection_elapsed_=0, resurrection_duration_=0;
    std::uint32_t flags_=0;
};
struct FrameSelection { std::size_t first=0, second=0; float coefficient=0; };
bool SelectAnimationFrames(float time,float fps,std::size_t frames,bool blend_frames,float truncation_offset,FrameSelection& output,std::string& error);
Sqt BlendPoseSample(Sqt first,Sqt second,float weight);
Sqt ChannelBlendPoseSample(Sqt first,Sqt second,float weight,bool use_first_weights);
bool WeightedBlendPoses(const std::vector<std::vector<Sqt>>& poses,const std::vector<float>& weights,std::vector<Sqt>& output,std::string& error);
Sqt DecodeSampleWords(const SampleWords& words);
bool SampleAnimationBone(const AnimationClipSamples& clip,float time,std::uint32_t bone,Sqt& output,std::string& error);
bool SampleAnimationClip(const AnimationClipSamples& clip,float time,std::vector<Sqt>& output,std::string& error);
}
