// SPDX-License-Identifier: Apache-2.0
#include "AnimationPlayback.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstring>
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits) { float value; std::memcpy(&value,&bits,4); return value; }
std::uint32_t Bits(float value) { std::uint32_t bits; std::memcpy(&bits,&value,4); return bits; }
std::size_t ActiveLanes(std::uint8_t kind) { return kind==0||kind==2?1:kind==1?4:kind==3?6:0; }
std::vector<std::size_t> NumericLanes(std::uint8_t kind) { return kind==0||kind==2?std::vector<std::size_t>{0}:kind==1?std::vector<std::size_t>{0,1,2,3}:kind==3?std::vector<std::size_t>{5}:std::vector<std::size_t>{}; }
float Unit(float value) { const auto low=-value>=0?0.0f:value; return 1.0f-low>=0?low:1.0f; }
float SelectionDelta(const SelectionParameter& p,float value,float candidate)
{
    const auto range=p.maximum-p.minimum;
    if (range>Float(0x37800000)) {candidate/=range;value/=range;}
    if (p.mode==1 && value>candidate) return (1.0f-value)+candidate;
    if (p.mode==2) {const auto difference=std::fabs(value-candidate), wrapped=1.0f-difference; return difference-wrapped>=0?wrapped:difference;}
    return candidate-value;
}
Sqt InterpolateKeys(const AnimationClipSamples& clip,const FrameSelection& selection,std::uint32_t bone)
{
    const auto first=DecodeSampleWords(clip.Sample(std::uint32_t(selection.first),bone));
    Sqt result=selection.first==selection.second?first:BlendPoseSample(first,DecodeSampleWords(clip.Sample(std::uint32_t(selection.second),bone)),selection.coefficient);
    result.translation[3]=Float(clip.channel_weights[bone]);return result;
}
}
void ClipClock::SetTime(float value) {time=value;previous_time=value;loops_since_evaluation=0;}
void ClipClock::SetSpeed(float value)
{
    const auto new_rate=base_speed*value, old_rate=speed*base_speed, frames_per_second=fps*base_speed;
    const auto inverse_new_rate=1.0f/new_rate;
    time=(time*old_rate)*inverse_new_rate;previous_time=(previous_time*old_rate)*inverse_new_rate;
    length=(frames-1.0f)/(frames_per_second*value);speed=value;
}
float ClipClock::SampleTime() const {return length-time>=0?time:length;}
bool ClipClock::Advance(float dt,float phase,AdvanceResult& result,std::string& error)
{
    if (phase_controlled) {previous_time=time;time=length*Unit(phase);loops_since_evaluation=std::uint32_t(time<previous_time);error.clear();return true;}
    time+=dt;result.remaining_before_wrap=length-time;
    if (!(time>length)) result.crossed_end=false;
    else if (looping)
    {
        if (!(length>0) || !std::isfinite(time)) {error="invalid looping clip clock";return false;}
        while (time>length)
        {
            result.crossed_end=true;result.overshoot=time-length;const auto next=time-length;
            if (!(next<time)) {error="clip clock cannot advance at this precision";return false;}
            time=next;++loops_since_evaluation;
        }
    }
    else {result.crossed_end=true;result.overshoot=time-length;}
    error.clear();return true;
}
void ClipClock::CommitEvaluation() {previous_time=time;loops_since_evaluation=0;}
std::uint8_t ClipClock::AttributeStatus(float begin,float end) const
{
    if (begin==-1.0f) return 6;begin=length*begin;end=length*end;
    const auto intersects=loops_since_evaluation==0?end>previous_time&&begin<=time:end>previous_time||begin<=time;
    return !intersects?17:time<begin||time>end?9:5;
}
void AnimationAttribute::CopyFrom(const AnimationAttribute& source)
{
    kind=source.kind;name=source.name;begin_time=source.begin_time;end_time=source.end_time;status=source.status;sequence_id=source.sequence_id;
    for (std::size_t i=0;i<ActiveLanes(kind);++i) payload[i]=source.payload[i];
}
AnimationAttribute MotionGraphAttribute::ToAnimation() const
{
    AnimationAttribute result;result.payload[0]=Bits(value);result.name=name;result.kind=0;result.status=6;result.sequence_id=-1;
    result.begin_time=-1.0f;result.end_time=-1.0f;return result;
}
void PacketAttributes::Append(const AnimationAttribute& source)
{
    if (active_len_==slots_.size()) slots_.emplace_back();
    slots_[active_len_].CopyFrom(source);++active_len_;
}
void PacketAttributes::ReplaceFrom(const std::vector<MotionGraphAttribute>& motion_graph,const std::vector<AnimationAttribute>& tree)
{Clear();for (const auto& attribute:motion_graph) Append(attribute.ToAnimation());for (const auto& attribute:tree) Append(attribute);}
PlaybackClip::PlaybackClip(float frames,float fps,float base_speed,std::uint32_t flags,std::vector<PlaybackClipAttribute> values)
    :attributes(std::move(values))
{
    clock.frames=frames;clock.fps=fps;clock.base_speed=base_speed;clock.speed=1;
    clock.length=(frames-1.0f)/((1.0f*base_speed)*fps);
    clock.looping=(flags&0x10000000)!=0;clock.phase_controlled=(flags&0x40000000)!=0;
}
PlaybackClip::PlaybackClip(const ClipMetadata& metadata)
    :PlaybackClip(Float(metadata.frames_bits),Float(metadata.fps_bits),Float(metadata.base_speed_bits),metadata.flags_word,{})
{
    for (const auto& a:metadata.attributes) attributes.push_back({EncodeAnimationName(a.name),a.type_id,Float(a.begin_bits),Float(a.end_bits),a.payload_words});
}
bool PlaybackClip::Advance(float dt,float phase,AdvanceResult& result,std::string& error)
{result={false,-1.0f,-1.0f};return clock.Advance(dt,phase,result,error);}
bool PlaybackClip::Attributes(std::uint32_t mask,std::vector<AnimationAttribute>& output,std::string& error) const
{
    output.clear();
    for (const auto& a:attributes)
    {
        const auto status=a.begin==-1.0f?std::uint8_t(4):clock.AttributeStatus(a.begin,a.end);
        if (a.begin!=-1.0f && ((mask&0x1c&status)==0 || (mask&3&status)==0)) continue;
        AnimationAttribute value;if (!Materialize(a,status,value,error)) return false;output.push_back(value);
    }
    error.clear();return true;
}
bool PlaybackClip::Attribute(AttributeName name,std::uint32_t mask,std::optional<AnimationAttribute>& output,std::string& error) const
{
    output.reset();
    for (const auto& a:attributes)
    {
        if (a.name!=name) continue;const auto status=clock.AttributeStatus(a.begin,a.end);
        if ((mask&0x1c&status)==0 || (mask&3&status)==0) continue;
        AnimationAttribute value;if (!Materialize(a,status,value,error)) return false;output=value;error.clear();return true;
    }
    error.clear();return true;
}
bool PlaybackClip::Materialize(const PlaybackClipAttribute& a,std::uint8_t status,AnimationAttribute& output,std::string& error) const
{
    output={};const auto lanes=a.kind==2?0:ActiveLanes(a.kind);
    if (a.payload.size()<lanes) {error="Truncated clip attribute payload";return false;}
    for (std::size_t i=0;i<lanes;++i) output.payload[i]=a.payload[i];
    if (a.kind==2)
    {
        const auto frame=(clock.time*clock.fps)*clock.speed;float sample;
        if (!SampleAnimationCurve(a.payload,frame,sample,error)) return false;output.payload[0]=Bits(sample);
    }
    output.name=a.name;output.kind=a.kind;output.status=status;output.sequence_id=-1;
    output.begin_time=(status&2)!=0?-1.0f:a.begin*clock.length;output.end_time=(status&2)!=0?-1.0f:a.end*clock.length;
    error.clear();return true;
}
bool SampleAnimationCurve(const std::vector<std::uint32_t>& words,float time,float& output,std::string& error)
{
    if (words.size()<2) {error="Missing animation curve count";return false;}
    const std::size_t count=words[1];if (count==0 || count>(words.size()-2)/2) {error="Truncated/empty animation curve";return false;}
    auto point=[&](std::size_t i) {return std::pair<float,float>{Float(words[2+2*i]),Float(words[3+2*i])};};
    std::size_t low=0,high=count-1;auto lower=point(low),upper=point(high);
    if (!(time>lower.first)) {output=lower.second;error.clear();return true;}
    if (!(time<upper.first)) {output=upper.second;error.clear();return true;}
    while (!(lower.first>upper.first))
    {
        const auto middle=(low+high)/2;const auto p=point(middle);
        if (time>p.first) {low=middle+1;if (low>=count) {error="Malformed animation curve search bounds";return false;}lower=point(low);}
        else if (time<p.first) {if (middle==0) {error="Malformed animation curve search bounds";return false;}high=middle-1;upper=point(high);}
        else {output=p.second;error.clear();return true;}
    }
    const auto slope=(lower.second-upper.second)/(lower.first-upper.first);output=std::fma(slope,time-upper.first,upper.second);error.clear();return true;
}
bool BlendAnimationAttribute(AnimationAttribute& left,const AnimationAttribute& right,float weight,std::string& error)
{
    const auto left_weight=1.0f-weight;
    if ((left.status&2)!=0) {left.begin_time=-1.0f;left.end_time=-1.0f;}
    else {left.begin_time=right.begin_time*weight+left.begin_time*left_weight;left.end_time=right.end_time*weight+left.end_time*left_weight;}
    for (const auto i:NumericLanes(left.kind))
    {
        if (!left.payload[i] || !right.payload[i]) {error="Uninitialized blended attribute payload";return false;}
        left.payload[i]=Bits(std::fma(Float(*right.payload[i]),weight,Float(*left.payload[i])*left_weight));
    }
    error.clear();return true;
}
bool ScaleAnimationAttribute(AnimationAttribute& attribute,float weight,std::string& error)
{
    if ((attribute.status&2)!=0) {attribute.begin_time=-1.0f;attribute.end_time=-1.0f;}
    else {attribute.begin_time*=weight;attribute.end_time*=weight;}
    for (const auto i:NumericLanes(attribute.kind))
    {
        if (!attribute.payload[i]) {error="Uninitialized weighted attribute";return false;}
        attribute.payload[i]=Bits(Float(*attribute.payload[i])*weight);
    }
    error.clear();return true;
}
bool AddWeightedAnimationAttribute(AnimationAttribute& left,const AnimationAttribute& right,float weight,std::string& error)
{
    if ((left.status&2)==0) {left.begin_time+=right.begin_time*weight;left.end_time+=right.end_time*weight;}
    for (const auto i:NumericLanes(left.kind))
    {
        if (!left.payload[i] || !right.payload[i]) {error="Uninitialized weighted attribute";return false;}
        left.payload[i]=Bits(std::fma(Float(*right.payload[i]),weight,Float(*left.payload[i])));
    }
    error.clear();return true;
}
bool IntersectAnimationAttributes(const std::vector<AnimationAttribute>& left,const std::vector<AnimationAttribute>& right,float weight,std::vector<AnimationAttribute>& output,std::string& error)
{
    output.clear();std::size_t next=0;
    for (auto a:left)
    {
        while (next<right.size() && right[next].name<a.name) ++next;
        if (next==right.size()) break;
        if (right[next].name==a.name) {if (!BlendAnimationAttribute(a,right[next],weight,error)) return false;output.push_back(a);}
    }
    error.clear();return true;
}
bool AttributeMirror::Apply(AnimationAttribute& attribute,std::string& error) const
{
    if (attribute.kind==1)
    {
        if (!attribute.payload[0]) {error="Uninitialized mirrored vector attribute";return false;}
        attribute.payload[0]=*attribute.payload[0]^0x80000000;
    }
    else if (attribute.kind==3)
    {
        AttributeName name;
        for (std::size_t i=0;i<5;++i) {if (!attribute.payload[i]) {error="Uninitialized mirrored bone reference";return false;}name[i]=*attribute.payload[i];}
        const auto found=std::find_if(names.begin(),names.end(),[&](const auto& p){return p.first==name;});
        if (found==names.end()) {error="Animation event bone is absent from its hierarchy";return false;}
        for (std::size_t i=0;i<5;++i) attribute.payload[i]=found->second[i];
    }
    error.clear();return true;
}
void SettableAttributes::SetAttribute(SettableAttribute value)
{
    const auto found=std::find_if(entries_.begin(),entries_.end(),[&](const auto& entry){return entry.name==value.name && entry.sequence_id==value.sequence_id;});
    if (found!=entries_.end()) *found=value;else entries_.push_back(value);
}
float SelectionDistance(const std::vector<SelectionParameter>& parameters,const std::vector<float>& values,const std::vector<float>& candidate)
{
    assert(values.size()>=parameters.size() && candidate.size()>=parameters.size());float even=0,odd=0;const auto pairs=parameters.size()/2*2;
    for (std::size_t i=0;i<pairs;i+=2)
    {
        auto d=SelectionDelta(parameters[i],values[i],candidate[i]);even=std::fma(parameters[i].weight*d,d,even);
        d=SelectionDelta(parameters[i+1],values[i+1],candidate[i+1]);odd=std::fma(parameters[i+1].weight*d,d,odd);
    }
    const auto sum=odd+even;
    if (pairs<parameters.size()) {const auto d=SelectionDelta(parameters[pairs],values[pairs],candidate[pairs]);return sum+(parameters[pairs].weight*d)*d;}
    return sum+0.0f;
}
ChannelPlayback::ChannelPlayback(ChannelSettings value):settings(value)
{
    flags_=(std::uint32_t(value.keep_alive)<<28)|(std::uint32_t(value.hold_during_blend_in)<<31)|(std::uint32_t(value.hold_during_blend_out)<<30)|
        (std::uint32_t(value.blend_out>0)<<27)|(std::uint32_t(value.use_attributes)<<25);
}
bool ChannelPlayback::Expired() const {return (flags_&0x08000000)!=0?blend_out_elapsed_>=settings.blend_out:(flags_&0x10000000)==0 && (flags_&0x04000000)!=0;}
void ChannelPlayback::End() {if (blend_out_elapsed_==0) flags_|=0x28000000;}
void ChannelPlayback::EndWith(float seconds,bool from_last_frame)
{if (blend_out_elapsed_==0) {settings.blend_out=seconds;settings.hold_during_blend_out=from_last_frame;flags_=(flags_&~0x40000000)|(std::uint32_t(from_last_frame)<<30)|0x28000000;}}
bool ChannelPlayback::CanTransition(bool resurrect) const {return !(blend_out_elapsed_>0)||resurrect;}
void ChannelPlayback::Transition(ChannelSettings value,bool resurrect)
{
    if (blend_out_elapsed_>0 && resurrect) {resurrection_duration_=value.blend_in;resurrection_elapsed_=Unit(1.0f-blend_out_elapsed_/settings.blend_out)*value.blend_in;}
    blend_out_elapsed_=0;settings.keep_alive=value.keep_alive;settings.blend_out=value.blend_out;settings.hold_during_blend_out=value.hold_during_blend_out;settings.use_attributes=value.use_attributes;
    flags_=(flags_&~0x7a000000)|(std::uint32_t(value.keep_alive)<<28)|(std::uint32_t(value.hold_during_blend_out)<<30)|
        (std::uint32_t(value.blend_out>0)<<27)|(std::uint32_t(value.use_attributes)<<25);
}
bool ChannelPlayback::Advance(float dt,float length,float time)
{
    float fade_in=1;
    if (settings.blend_in>0 && blend_in_elapsed_<settings.blend_in) {fade_in=Unit(blend_in_elapsed_/settings.blend_in);blend_in_elapsed_+=dt;}
    const auto remaining_raw=length-time, remaining=remaining_raw>=0?remaining_raw:0.0f;
    const bool hold_end=(flags_&0x40000000)!=0, ended=(flags_&0x04000000)!=0;
    const bool fade_automatically=hold_end?ended:remaining<settings.blend_out;float fade_out=1;
    if (settings.blend_out>0 && ((flags_&0x20000000)!=0 || ((flags_&0x10000000)==0 && fade_automatically)))
    {fade_out=Unit(1.0f-blend_out_elapsed_/settings.blend_out);blend_out_elapsed_+=dt;}
    float resurrection=1;
    if (resurrection_duration_>0 && resurrection_elapsed_<resurrection_duration_) {resurrection=Unit(resurrection_elapsed_/resurrection_duration_);resurrection_elapsed_+=dt;}
    const auto fade_first=fade_in-fade_out>=0?fade_out:fade_in, fade=fade_first-resurrection>=0?resurrection:fade_first;
    weight=Unit(fade*influence);
    return !((flags_&0x80000000)!=0 && blend_in_elapsed_<settings.blend_in) && !(hold_end && blend_out_elapsed_>0);
}
void ChannelPlayback::DidAdvance(AdvanceResult value) {flags_=(flags_&~0x04000000)|(std::uint32_t(value.crossed_end)<<26);}
std::vector<AnimationAttribute> ChannelPlayback::MergeAttributes(const std::vector<AnimationAttribute>& base,const std::vector<AnimationAttribute>& channel) const
{
    if (!settings.use_attributes) return base;std::vector<AnimationAttribute> result;std::size_t b=0,c=0;
    while (b<base.size() && c<channel.size())
    {
        if (base[b].name<channel[c].name) result.push_back(base[b++]);
        else if (channel[c].name<base[b].name) result.push_back(channel[c++]);
        else {result.push_back(channel[c++]);++b;}
    }
    result.insert(result.end(),base.begin()+b,base.end());result.insert(result.end(),channel.begin()+c,channel.end());return result;
}
bool SelectAnimationFrames(float time,float fps,std::size_t frames,bool blend_frames,float truncation_offset,FrameSelection& output,std::string& error)
{
    if (frames==0 || !std::isfinite(time) || time<0 || !std::isfinite(fps) || fps<=0) {error="Invalid stock animation sampling input";return false;}
    const auto last=float(frames-1), raw=time*fps, position=raw-last>=0?last:raw, offset=blend_frames?0.0f:truncation_offset;
    const auto shifted=position+offset;
    const auto first=!(shifted>0)?std::size_t(0):shifted>=float(std::numeric_limits<std::size_t>::max())?std::numeric_limits<std::size_t>::max():std::size_t(shifted);
    if (first>=frames) {error="Stock frame selection exceeds decoded samples";return false;}
    const auto second=blend_frames?std::min(first+1,frames-1):first;
    const auto raw_fraction=(position-float(first))*65535.0f;
    const auto fraction=!(raw_fraction>0)?std::uint16_t(0):raw_fraction>=65535.0f?std::uint16_t(65535):std::uint16_t(raw_fraction);
    output={first,second,float(fraction)*Float(0x37800080)};error.clear();return true;
}
Sqt BlendPoseSample(Sqt first,Sqt second,float weight)
{
    const bool positive=Dot4(first.rotation,second.rotation)>0;Sqt output;
    for (std::size_t i=0;i<4;++i)
    {
        output.rotation[i]=positive?std::fma(second.rotation[i]-first.rotation[i],weight,first.rotation[i]):std::fma(-(second.rotation[i]+first.rotation[i]),weight,first.rotation[i]);
        output.scale[i]=std::fma(second.scale[i]-first.scale[i],weight,first.scale[i]);output.translation[i]=std::fma(second.translation[i]-first.translation[i],weight,first.translation[i]);
    }
    const auto squared=Dot4(output.rotation,output.rotation);auto inverse=ReciprocalSquareRootEstimate(squared);
    for (unsigned i=0;i<2;++i) inverse=std::fma(inverse*0.5f,std::fma(-squared,inverse*inverse,1.0f),inverse);
    for (auto& v:output.rotation) v*=inverse;return output;
}
Sqt ChannelBlendPoseSample(Sqt first,Sqt second,float weight,bool use_first_weights)
{
    const auto channel=use_first_weights?first.translation[3]:second.translation[3];auto coefficient=weight*channel;
    coefficient=coefficient>1?1.0f:coefficient;coefficient=0>coefficient?0.0f:coefficient;return BlendPoseSample(first,second,coefficient);
}
bool WeightedBlendPoses(const std::vector<std::vector<Sqt>>& poses,const std::vector<float>& weights,std::vector<Sqt>& output,std::string& error)
{
    if (poses.empty() || poses.size()!=weights.size()) {error="ShortInput";return false;}
    const auto bones=poses[0].size();for (const auto& p:poses) if (p.size()!=bones) {error="ShortInput";return false;}
    for (auto weight:weights) if (!std::isfinite(weight)) {error="NonFiniteWeight";return false;}
    output=poses[0];for (auto& s:output) for (std::size_t j=0;j<4;++j) {s.scale[j]*=weights[0];s.rotation[j]*=weights[0];s.translation[j]*=weights[0];}
    for (std::size_t i=1;i<poses.size();++i) for (std::size_t b=0;b<bones;++b) for (std::size_t j=0;j<4;++j)
    {
        output[b].scale[j]=std::fma(poses[i][b].scale[j],weights[i],output[b].scale[j]);
        output[b].rotation[j]=std::fma(poses[i][b].rotation[j],weights[i],output[b].rotation[j]);
        output[b].translation[j]=std::fma(poses[i][b].translation[j],weights[i],output[b].translation[j]);
    }
    for (auto& s:output)
    {
        const auto squared=Dot4(s.rotation,s.rotation);if (!std::isfinite(squared)||squared<=0) {error="InvalidQuaternion";return false;}
        auto inverse=ReciprocalSquareRootEstimate(squared);for (unsigned i=0;i<2;++i) inverse=std::fma(inverse*0.5f,std::fma(-squared,inverse*inverse,1.0f),inverse);
        for (auto& v:s.rotation) {v*=inverse;if (!std::isfinite(v)) {error="InvalidQuaternion";return false;}}
    }
    error.clear();return true;
}
Sqt DecodeSampleWords(const SampleWords& w)
{return {{Float(w[0]),Float(w[1]),Float(w[2]),1.0f},{Float(w[3]),Float(w[4]),Float(w[5]),Float(w[6])},{Float(w[7]),Float(w[8]),Float(w[9]),1.0f}};}
bool SampleAnimationBone(const AnimationClipSamples& clip,float time,std::uint32_t bone,Sqt& output,std::string& error)
{
    FrameSelection selection;if (bone>=clip.bone_count) {error="Animation bone index exceeds samples";return false;}
    if (!SelectAnimationFrames(time,Float(clip.fps_bits),clip.frame_count,true,0,selection,error)) return false;output=InterpolateKeys(clip,selection,bone);error.clear();return true;
}
bool SampleAnimationClip(const AnimationClipSamples& clip,float time,std::vector<Sqt>& output,std::string& error)
{
    FrameSelection selection;if (!SelectAnimationFrames(time,Float(clip.fps_bits),clip.frame_count,true,0,selection,error)) return false;
    output.clear();output.reserve(clip.bone_count);for (std::uint32_t b=0;b<clip.bone_count;++b) output.push_back(InterpolateKeys(clip,selection,b));error.clear();return true;
}
}
