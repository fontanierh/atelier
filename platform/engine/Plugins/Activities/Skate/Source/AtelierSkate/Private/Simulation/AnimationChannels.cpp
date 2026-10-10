#include "AnimationChannels.h"
#include <algorithm>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
AnimationChannel* AnimationChannels::Find(std::string_view name)
{
    const auto key=EncodeIntentKey(name);const auto found=std::find_if(channels_.begin(),channels_.end(),[&](const auto& c){return EncodeIntentKey(c.name)==key;});
    return found==channels_.end()?nullptr:&*found;
}
const AnimationChannel* AnimationChannels::Find(std::string_view name) const
{
    const auto key=EncodeIntentKey(name);const auto found=std::find_if(channels_.begin(),channels_.end(),[&](const auto& c){return EncodeIntentKey(c.name)==key;});
    return found==channels_.end()?nullptr:&*found;
}
bool AnimationChannels::Has(std::string_view name) const {return Find(name)!=nullptr;}
float AnimationChannels::Remaining(std::string_view name) const
{const auto c=Find(name);if (!c) return 0;const auto value=c->tree.Length()-c->tree.Time();return value>=0?value:0.0f;}
float AnimationChannels::Elapsed(std::string_view name) const
{const auto c=Find(name);if (!c) return 0;const auto time=c->tree.Time(),lower=-time>=0?0.0f:time,length=c->tree.Length();return length-lower>=0?lower:length;}
bool AnimationChannels::InTransition(std::string_view name) const
{const auto c=Find(name);return c && c->tree.Kind()==PlaybackTreeKind::Transition;}
void AnimationChannels::Insert(std::string name,AnimationTree tree,ChannelSettings settings)
{
    const auto position=std::find_if(channels_.begin(),channels_.end(),[&](const auto& c){return c.playback.settings.priority>settings.priority;});
    channels_.insert(position,AnimationChannel{std::move(name),std::move(tree),ChannelPlayback(settings)});
}
void AnimationChannels::End(std::string_view name) {if (auto c=Find(name)) c->playback.End();}
void AnimationChannels::EndWith(std::string_view name,float seconds,bool from_last_frame)
{if (auto c=Find(name)) c->playback.EndWith(seconds,from_last_frame);}
bool AnimationChannels::Influence(std::string_view name,float value)
{if (auto c=Find(name)) {c->playback.influence=value;return true;}return false;}
bool AnimationChannels::CanTransition(std::string_view name,bool resurrect) const
{const auto c=Find(name);return c && c->playback.CanTransition(resurrect);}
void AnimationChannels::Transition(std::string_view name,AnimationTree tree,ChannelSettings settings,TransitionSettings transition,bool resurrect)
{
    if (auto c=Find(name))
    {
        // CompleteTransition keeps the old target whenever the channel is
        // already transitioning, regardless of completion or blend weight.
        auto old=c->tree.Kind()==PlaybackTreeKind::Transition?*c->tree.Children()[1]:std::move(c->tree);
        c->tree=AnimationTree::Transition(std::move(old),std::move(tree),transition);c->playback.Transition(settings,resurrect);
    }
}
void AnimationChannels::Retire()
{
    for (auto& c:channels_) if (c.tree.Kind()==PlaybackTreeKind::Transition && c.tree.TransitionComplete()) c.tree=*c.tree.Children()[1];
    channels_.erase(std::remove_if(channels_.begin(),channels_.end(),[](const auto& c){return c.playback.Expired();}),channels_.end());
}
bool AnimationChannels::Advance(float dt,float phase,std::string& error)
{
    for (auto& c:channels_) if (c.playback.Advance(dt,c.tree.Length(),c.tree.Time()))
    {
        AdvanceResult property{false,-1,-1};if (!c.tree.Advance(dt,phase,property,error)) return false;c.playback.DidAdvance(property);
    }
    error.clear();return true;
}
bool AnimationChannels::PrepareSelectionSpaces(const std::vector<SettableAttribute>& attributes,std::string& error)
{for (auto& c:channels_) if (!c.tree.PrepareSelectionSpaces(attributes,error)) return false;error.clear();return true;}
bool AnimationChannels::SetAttributes(const std::vector<SettableAttribute>& attributes,std::string& error)
{for (auto& c:channels_) {bool ignored;if (!c.tree.SetAttributes(attributes,ignored,error)) return false;}error.clear();return true;}
bool AnimationChannels::Attributes(std::vector<AnimationAttribute> base,std::uint32_t mask,std::vector<AnimationAttribute>& output,std::string& error) const
{
    for (const auto& c:channels_) if (c.playback.settings.use_attributes)
    {std::vector<AnimationAttribute> right;if (!c.tree.Attributes(mask,right,error)) return false;base=c.playback.MergeAttributes(base,right);}
    output=std::move(base);error.clear();return true;
}
bool AnimationChannels::QueryAttribute(AttributeName name,std::uint32_t mask,AnimationAttribute& output,bool& found,std::string& error) const
{
    found=false;for (auto c=channels_.rbegin();c!=channels_.rend();++c) {if (!c->tree.QueryAttribute(name,mask,output,found,error)) return false;if (found) {error.clear();return true;}}
    error.clear();return true;
}
bool AnimationChannels::Evaluate(AnimationEvaluation parameters,std::vector<PoseCommand>& output,std::string& error)
{
    for (auto& c:channels_)
    {
        const bool enabled=c.playback.weight>0;bool produced;if (!c.tree.Evaluate(parameters,enabled,output,produced,error)) return false;
        if (produced && enabled) {PoseCommand command;command.kind=PoseCommand::Kind::ChannelBlend;command.weight=c.playback.weight;output.push_back(std::move(command));}
    }
    error.clear();return true;
}
}
