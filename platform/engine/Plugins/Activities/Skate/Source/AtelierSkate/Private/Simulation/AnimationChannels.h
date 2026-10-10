#pragma once
#include "AnimationTrees.h"

namespace atelier::skate
{
struct AnimationChannel
{
    std::string name;
    AnimationTree tree;
    ChannelPlayback playback;
};
// Ordered persistent overlays. Equal-priority insertions follow older channels
// in pose evaluation; encoded intent keys retain first-match lookup semantics.
class AnimationChannels
{
public:
    void ResetFromStock() {channels_.clear();}
    const std::vector<AnimationChannel>& Entries() const {return channels_;}
    bool Has(std::string_view name) const;
    float Remaining(std::string_view name) const;
    float Elapsed(std::string_view name) const;
    bool InTransition(std::string_view name) const;
    void Insert(std::string name,AnimationTree tree,ChannelSettings settings);
    void End(std::string_view name);
    void EndWith(std::string_view name,float seconds,bool from_last_frame);
    bool Influence(std::string_view name,float value);
    bool CanTransition(std::string_view name,bool resurrect) const;
    void Transition(std::string_view name,AnimationTree tree,ChannelSettings settings,TransitionSettings transition,bool resurrect);
    void Retire();
    bool Advance(float dt,float phase,std::string& error);
    bool PrepareSelectionSpaces(const std::vector<SettableAttribute>& attributes,std::string& error);
    bool SetAttributes(const std::vector<SettableAttribute>& attributes,std::string& error);
    bool Attributes(std::vector<AnimationAttribute> base,std::uint32_t mask,std::vector<AnimationAttribute>& output,std::string& error) const;
    bool QueryAttribute(AttributeName name,std::uint32_t mask,AnimationAttribute& output,bool& found,std::string& error) const;
    bool Evaluate(AnimationEvaluation parameters,std::vector<PoseCommand>& output,std::string& error);
private:
    std::vector<AnimationChannel> channels_;
    AnimationChannel* Find(std::string_view name);
    const AnimationChannel* Find(std::string_view name) const;
};
}
