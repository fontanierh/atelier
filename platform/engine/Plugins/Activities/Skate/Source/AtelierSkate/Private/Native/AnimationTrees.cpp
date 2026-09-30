// SPDX-License-Identifier: Apache-2.0
#include "AnimationTrees.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstring>
#include <limits>
#include <numeric>
#include <variant>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits) {float value;std::memcpy(&value,&bits,4);return value;}
float Unit(float value) {const auto low=-value>=0?0.0f:value;return 1.0f-low>=0?low:1.0f;}
bool Normalize(std::vector<float>& weights,std::string& error)
{
    float sum=0;for (auto w:weights) sum+=w;
    if (!std::isfinite(sum) || sum<=0) {error="Degenerate BlendSpace weights";return false;}
    const auto inverse=1.0f/sum;for (auto& w:weights) w*=inverse;return true;
}
struct ClipState {std::string name;PlaybackClip clip;};
struct PhaseState
{
    AttributeName parameter{};
    std::vector<AnimationTree> children;
    std::vector<std::size_t> order;
    std::vector<float> values;
    std::size_t left=0,right=1;
    float weight=0,parameter_value=std::numeric_limits<float>::max(),cull_threshold=0,length=0,time=0;
    bool normalized=true;
    float Phase() const {return time/(-length>=0?1.0f:length);}
};
struct BlendState
{
    std::vector<AttributeName> parameters;
    std::vector<AnimationTree> children;
    std::vector<AnimationBlendSimplex> simplexes;
    std::vector<float> values,weights;
    std::size_t current=0;
    float time=0;
};
struct SelectionState
{
    std::vector<SelectionParameter> parameters;
    std::vector<AnimationSelectionCandidate> candidates;
    std::optional<std::size_t> selected;
    std::vector<std::optional<float>> values;
    float speed=1,requested_time=0;
};
struct TransitionState {AnimationTree from,to;TransitionSettings settings;float elapsed=0;bool sequence_complete=false;};
struct BindState
{
    AnimationTree motion;
    std::optional<PosturePose> posture;
    bool board_backwards=false;
    std::vector<std::uint32_t> mirror_modes;
    std::shared_ptr<const AttributeMirror> mirror;
};
PoseCommand SingleCommand(PoseCommand::Kind kind) {PoseCommand c;c.kind=kind;return c;}
bool Build(const AnimationMetadata& metadata,std::string_view name,const std::vector<std::pair<AttributeName,AttributeName>>& construction,std::vector<std::string>& parents,AnimationTree& output,std::string& error);
}
struct AnimationTree::State
{
    std::variant<ClipState,PhaseState,BlendState,SelectionState,TransitionState,BindState> value;
    template<class T> explicit State(T state):value(std::move(state)) {}
    State(const State&)=default;
};
bool AnimationTree::AppendBindPoseMirrorMode(std::uint32_t mode,std::string& error)
{
    auto* bind=state_?std::get_if<BindState>(&state_->value):nullptr;
    if (!bind) {error="Animation mirror mode requires bind pose";return false;}
    bind->mirror_modes.push_back(mode);error.clear();return true;
}
std::optional<PosturePose> PosturePoseFromProfile(std::uint32_t value)
{return value>=1 && value<=3?std::optional<PosturePose>(PosturePose(value-1)):std::nullopt;}
std::string_view PosturePoseName(PosturePose value)
{
    switch (value) {case PosturePose::Stiff:return "POSTURE_STIFF_POSE";case PosturePose::Slouch:return "POSTURE_SLOUCH_POSE";case PosturePose::Buff:return "POSTURE_BUFF_POSE";}
    return {};
}
std::optional<PosturePose> PendingPosture::SelectedPose() const {return pending_?PosturePoseFromProfile(profile_):std::nullopt;}
AnimationTree::AnimationTree()=default;
AnimationTree::~AnimationTree()=default;
AnimationTree::AnimationTree(const AnimationTree& other):state_(other.state_?std::make_unique<State>(*other.state_):nullptr) {}
AnimationTree& AnimationTree::operator=(const AnimationTree& other)
{if (this!=&other) state_=other.state_?std::make_unique<State>(*other.state_):nullptr;return *this;}
AnimationTree::AnimationTree(AnimationTree&& other) noexcept=default;
AnimationTree& AnimationTree::operator=(AnimationTree&& other) noexcept=default;
AnimationTree AnimationTree::Clip(std::string name,PlaybackClip clip)
{AnimationTree tree;tree.state_=std::make_unique<State>(ClipState{std::move(name),std::move(clip)});return tree;}
bool AnimationTree::PhaseBlend(AttributeName parameter,std::vector<AnimationTree> children,AnimationTree& output,std::string& error)
{
    if (children.size()<2) {error="PhaseBlend requires at least two authored children";return false;}
    PhaseState s;s.parameter=parameter;s.length=children[0].Length();s.children=std::move(children);s.order.resize(s.children.size());s.values.resize(s.children.size(),0);
    std::iota(s.order.begin(),s.order.end(),0);output.state_=std::make_unique<State>(std::move(s));error.clear();return true;
}
bool AnimationTree::BlendSpace(std::vector<AttributeName> parameters,std::vector<AnimationTree> children,std::vector<AnimationBlendSimplex> simplexes,AnimationTree& output,std::string& error)
{
    const auto d=parameters.size();bool invalid=d==0 || d>4 || children.size()<d+1 || simplexes.empty();
    for (const auto& s:simplexes)
    {
        invalid|=s.children.size()!=d+1 || s.vertices.size()!=d+1 || s.normals.size()!=d+1 || s.scales.size()!=d+1;
        for (auto i:s.children) invalid|=i>=children.size();
        for (const auto* matrix:{&s.vertices,&s.normals}) for (const auto& row:*matrix) {invalid|=row.size()!=d;for (auto v:row) invalid|=!std::isfinite(v);}
        for (auto v:s.scales) invalid|=!std::isfinite(v);
    }
    if (invalid) {error="Invalid authored BlendSpace topology";return false;}
    BlendState s;s.parameters=std::move(parameters);s.children=std::move(children);s.simplexes=std::move(simplexes);s.values.resize(d,0);s.weights.resize(d+1,0);s.weights[0]=1;
    output.state_=std::make_unique<State>(std::move(s));error.clear();return true;
}
bool AnimationTree::SelectionSpace(std::vector<SelectionParameter> parameters,std::vector<AnimationSelectionCandidate> candidates,AnimationTree& output,std::string& error)
{
    bool invalid=parameters.size()>10 || candidates.empty();for (const auto& c:candidates) invalid|=c.values.size()!=parameters.size();
    if (invalid) {error="Invalid native selection space dimensions";return false;}
    SelectionState s;s.values.resize(parameters.size());s.parameters=std::move(parameters);s.candidates=std::move(candidates);
    output.state_=std::make_unique<State>(std::move(s));error.clear();return true;
}
AnimationTree AnimationTree::Transition(AnimationTree from,AnimationTree to,TransitionSettings settings)
{AnimationTree tree;tree.state_=std::make_unique<State>(TransitionState{std::move(from),std::move(to),settings,0,false});return tree;}
AnimationTree AnimationTree::BindPose(AnimationTree motion,std::optional<PosturePose> posture,bool board_backwards,std::vector<std::uint32_t> mirror_modes,std::shared_ptr<const AttributeMirror> mirror)
{AnimationTree tree;tree.state_=std::make_unique<State>(BindState{std::move(motion),posture,board_backwards,std::move(mirror_modes),std::move(mirror)});return tree;}
PlaybackTreeKind AnimationTree::Kind() const {assert(state_);return PlaybackTreeKind(state_->value.index());}
float AnimationTree::Length() const
{
    switch (Kind())
    {
        case PlaybackTreeKind::Clip:return std::get<ClipState>(state_->value).clip.clock.length;
        case PlaybackTreeKind::PhaseBlend:return std::get<PhaseState>(state_->value).length;
        case PlaybackTreeKind::BlendSpace:
        {
            const auto& s=std::get<BlendState>(state_->value);float sum=0;const auto& indices=s.simplexes[s.current].children;
            for (std::size_t i=0;i<indices.size();++i) sum=std::fma(s.weights[i],s.children[indices[i]].Length(),sum);return sum;
        }
        case PlaybackTreeKind::SelectionSpace:{const auto& s=std::get<SelectionState>(state_->value);return s.selected?s.candidates[*s.selected].tree.Length():0.0f;}
        case PlaybackTreeKind::Transition:return std::get<TransitionState>(state_->value).to.Length();
        case PlaybackTreeKind::BindPose:return std::get<BindState>(state_->value).motion.Length();
    }
    return 0;
}
float AnimationTree::Time() const
{
    switch (Kind())
    {
        case PlaybackTreeKind::Clip:return std::get<ClipState>(state_->value).clip.clock.SampleTime();
        case PlaybackTreeKind::PhaseBlend:return std::get<PhaseState>(state_->value).time;
        case PlaybackTreeKind::BlendSpace:return std::get<BlendState>(state_->value).time;
        case PlaybackTreeKind::SelectionSpace:{const auto& s=std::get<SelectionState>(state_->value);return s.selected?s.candidates[*s.selected].tree.Time():0.0f;}
        case PlaybackTreeKind::Transition:return std::get<TransitionState>(state_->value).to.Time();
        case PlaybackTreeKind::BindPose:return std::get<BindState>(state_->value).motion.Time();
    }
    return 0;
}
void AnimationTree::SetTime(float time)
{
    switch (Kind())
    {
        case PlaybackTreeKind::Clip:std::get<ClipState>(state_->value).clip.clock.SetTime(time);break;
        case PlaybackTreeKind::PhaseBlend:
        {
            auto& s=std::get<PhaseState>(state_->value);const auto phase=time/s.length;
            const auto left_time=s.children[s.left].Length()*phase,right_time=s.children[s.right].Length()*phase;
            s.children[s.left].SetTime(left_time);s.children[s.right].SetTime(right_time);s.time=time;break;
        }
        case PlaybackTreeKind::BlendSpace:
        {
            auto& s=std::get<BlendState>(state_->value);const auto phase=time/Length();
            for (auto i:s.simplexes[s.current].children) s.children[i].SetTime(phase*s.children[i].Length());break;
        }
        case PlaybackTreeKind::SelectionSpace:
        {auto& s=std::get<SelectionState>(state_->value);s.requested_time=time;if (s.selected) s.candidates[*s.selected].tree.SetTime(time);break;}
        case PlaybackTreeKind::Transition:std::get<TransitionState>(state_->value).to.SetTime(time);break;
        case PlaybackTreeKind::BindPose:std::get<BindState>(state_->value).motion.SetTime(time);break;
    }
}
void AnimationTree::SetSpeed(float speed)
{
    switch (Kind())
    {
        case PlaybackTreeKind::Clip:std::get<ClipState>(state_->value).clip.clock.SetSpeed(speed);break;
        case PlaybackTreeKind::PhaseBlend:
        {
            auto& s=std::get<PhaseState>(state_->value);const auto phase=s.Phase();for (auto i:s.order) s.children[i].SetSpeed(speed);
            s.length=std::fma(s.children[s.right].Length(),s.weight,s.children[s.left].Length()*(1.0f-s.weight));SetTime(s.length*phase);break;
        }
        case PlaybackTreeKind::BlendSpace:for (auto& c:std::get<BlendState>(state_->value).children) c.SetSpeed(speed);break;
        case PlaybackTreeKind::SelectionSpace:
        {auto& s=std::get<SelectionState>(state_->value);s.speed=speed;if (s.selected) s.candidates[*s.selected].tree.SetSpeed(speed);break;}
        case PlaybackTreeKind::Transition:std::get<TransitionState>(state_->value).to.SetSpeed(speed);break;
        case PlaybackTreeKind::BindPose:std::get<BindState>(state_->value).motion.SetSpeed(speed);break;
    }
}
bool AnimationTree::Advance(float dt,float phase,AdvanceResult& property,std::string& error)
{
    switch (Kind())
    {
        case PlaybackTreeKind::Clip:return std::get<ClipState>(state_->value).clip.clock.Advance(dt,phase,property,error);
        case PlaybackTreeKind::PhaseBlend:
        {
            auto& s=std::get<PhaseState>(state_->value);const auto left_length=s.children[s.left].Length(),right_length=s.children[s.right].Length(),fraction=dt/s.length;
            if (!s.children[s.left].Advance(fraction*left_length,phase,property,error)) return false;AdvanceResult discarded{false,-1,-1};if (!s.children[s.right].Advance(fraction*right_length,phase,discarded,error)) return false;
            const auto inverse_left=1.0f/left_length;s.time=(s.children[s.left].Time()*inverse_left)*s.length;
            property.remaining_before_wrap=(property.remaining_before_wrap*inverse_left)*s.length;property.overshoot=(inverse_left*s.length)*property.overshoot;break;
        }
        case PlaybackTreeKind::BlendSpace:
        {
            auto& s=std::get<BlendState>(state_->value);const auto length=Length();const auto& indices=s.simplexes[s.current].children;const auto first=indices[0];const auto first_length=s.children[first].Length();
            for (std::size_t slot=0;slot<indices.size();++slot) {auto& child=s.children[indices[slot]];AdvanceResult result{false,-1,-1};if (!child.Advance((child.Length()*(1.0f/length))*dt,phase,result,error)) return false;if (slot==0) property=result;}
            const auto scale=length/first_length;property.overshoot*=scale;property.remaining_before_wrap*=scale;s.time=s.children[first].Time()*scale;break;
        }
        case PlaybackTreeKind::SelectionSpace:
        {auto& s=std::get<SelectionState>(state_->value);if (s.selected) if (!s.candidates[*s.selected].tree.Advance(dt,phase,property,error)) return false;break;}
        case PlaybackTreeKind::Transition:
        {
            auto& s=std::get<TransitionState>(state_->value);AdvanceResult discarded{false,-1,-1};
            if (s.settings.kind==4)
            {
                if (s.sequence_complete) {if (!s.to.Advance(dt,phase,property,error)) return false;}
                else {if (!s.from.Advance(dt,phase,discarded,error)) return false;if (discarded.crossed_end) {s.sequence_complete=true;if (!s.to.Advance(discarded.overshoot,phase,property,error)) return false;}else {property.crossed_end=false;property.remaining_before_wrap=s.to.Length()+discarded.remaining_before_wrap;}}
                break;
            }
            if (s.settings.matching!=1) if (!s.from.Advance(dt,phase,discarded,error)) return false;
            if (s.settings.matching==3) {const auto length=s.to.Length(),time=s.from.Time();s.to.SetTime(time-length>=0?length:time);}
            else if (s.settings.matching==2 && s.from.Length()>0) s.to.SetTime(s.to.Length()*(s.from.Time()/s.from.Length()));
            else if (!s.to.Advance(dt,phase,property,error)) return false;s.elapsed+=dt;break;
        }
        case PlaybackTreeKind::BindPose:return std::get<BindState>(state_->value).motion.Advance(dt,phase,property,error);
    }
    error.clear();return true;
}
std::vector<float> AnimationBlendSimplex::Coordinates(const std::vector<float>& point) const
{
    std::vector<float> result;
    for (std::size_t i=0;i<children.size();++i)
    {
        const auto& anchor=vertices[(i+1)%children.size()];float even=0,odd=0;
        for (std::size_t j=0;j<point.size()/2;++j)
        {
            even=std::fma(normals[i][j*2],point[j*2]-anchor[j*2],even);
            odd=std::fma(normals[i][j*2+1],point[j*2+1]-anchor[j*2+1],odd);
        }
        auto dot=even+odd;if (point.size()%2!=0) {const auto j=point.size()-1;dot+=normals[i][j]*(point[j]-anchor[j]);}
        result.push_back(dot*scales[i]);
    }
    return result;
}
std::vector<float> AnimationBlendSimplex::Project(const std::vector<float>& point) const
{
    auto matrix=vertices;std::vector<float> projected;
    for (auto target:point)
    {
        const auto count=matrix.size()-1;std::vector<std::vector<float>> sliced;
        for (std::size_t i=0;i<count && sliced.size()<count;++i) for (std::size_t j=i+1;j<matrix.size() && sliced.size()<count;++j)
        {
            const auto& a=matrix[i];const auto& b=matrix[j];if ((a[0]<target)==(b[0]<target)) continue;
            const auto delta=b[0]-a[0];
            if (std::fabs(delta)<=Float(0x3727c5ac)) {sliced.emplace_back(a.begin()+1,a.end());if (sliced.size()<count) sliced.emplace_back(b.begin()+1,b.end());}
            else {const auto t=(target-a[0])/delta;std::vector<float> row;for (std::size_t k=1;k<a.size();++k) row.push_back(std::fma(b[k]-a[k],t,a[k]));sliced.push_back(std::move(row));}
        }
        if (sliced.empty())
        {
            std::size_t nearest=0;float distance=std::numeric_limits<float>::max();
            for (std::size_t i=0;i<matrix.size();++i) {const auto d=(matrix[i][0]-target)*(matrix[i][0]-target);if (d<distance) {distance=d;nearest=i;}}
            projected.insert(projected.end(),matrix[nearest].begin(),matrix[nearest].end());break;
        }
        projected.push_back(target);while (sliced.size()<count) sliced.push_back(sliced.back());matrix=std::move(sliced);
    }
    return projected;
}
bool AnimationTree::Select(const std::vector<SettableAttribute>& attributes,std::string& error)
{
    assert(Kind()==PlaybackTreeKind::SelectionSpace);auto& s=std::get<SelectionState>(state_->value);
    for (const auto& a:attributes) for (std::size_t i=0;i<s.parameters.size();++i) if (s.parameters[i].name==a.name) s.values[i]=a.value;
    if (!s.selected)
    {
        std::vector<float> values;for (std::size_t i=0;i<s.values.size();++i)
        {
            if (!s.values[i]) {error="SelectionSpace parameter "+std::to_string(i)+" has no source producer";return false;}values.push_back(*s.values[i]);
        }
        float best=std::numeric_limits<float>::max();std::optional<std::size_t> selected;
        for (std::size_t i=0;i<s.candidates.size();++i) {const auto distance=SelectionDistance(s.parameters,values,s.candidates[i].values);if (distance<best) {best=distance;selected=i;}}
        if (!selected) {error="SelectionSpace has no finite native minimum";return false;}
        for (std::size_t i=0;i<s.candidates.size();++i) if (s.candidates[i].name==s.candidates[*selected].name) {s.selected=i;break;}
    }
    error.clear();return true;
}
bool AnimationTree::SetAttributes(const std::vector<SettableAttribute>& attributes,bool& changed,std::string& error)
{
    changed=false;
    switch (Kind())
    {
        case PlaybackTreeKind::Clip:break;
        case PlaybackTreeKind::PhaseBlend:
        {
            auto& s=std::get<PhaseState>(state_->value);
            for (auto i:s.order) {bool child_changed;if (!s.children[i].SetAttributes(attributes,child_changed,error)) return false;changed|=child_changed;}
            const auto attribute=std::find_if(attributes.begin(),attributes.end(),[&](const auto& a){return a.name==s.parameter;});
            if (attribute!=attributes.end() && (attribute->normalized!=s.normalized || !(std::fabs(attribute->value-s.parameter_value)<Float(0x38d1b717))))
            {s.parameter_value=attribute->value;s.normalized=attribute->normalized;changed=true;}
            if (!changed) break;
            for (auto i:s.order)
            {
                auto a=MotionGraphAttribute{s.parameter,0}.ToAnimation();bool found;
                if (!s.children[i].QueryAttribute(s.parameter,15,a,found,error)) return false;
                if (!a.payload[0]) {error="Uninitialized PhaseBlend parameter";return false;}
                s.values[i]=Float(*a.payload[0]);
            }
            for (std::size_t end=s.order.size()-1;end>0;--end) for (std::size_t i=0;i<end;++i) if (s.values[s.order[i+1]]<s.values[s.order[i]]) std::swap(s.order[i],s.order[i+1]);
            const auto minimum=s.values[s.order[0]],maximum=s.values[s.order.back()];const auto target=s.normalized?std::fma(maximum-minimum,s.parameter_value,minimum):s.parameter_value;
            std::size_t low=0,count=s.order.size();while (count!=0) {const auto step=count/2,middle=low+step;if (s.values[s.order[middle]]<target) {low=middle+1;count-=step+1;}else count=step;}
            const auto upper=std::clamp(low,std::size_t(1),s.order.size()-1);const auto left=s.order[upper-1],right=s.order[upper];
            const auto lower_value=s.values[left],upper_value=s.values[right],delta=upper_value-lower_value;
            const auto lower=lower_value-target>=0?lower_value:target,clamped=upper_value-lower>=0?lower:upper_value;
            s.weight=Unit((clamped-lower_value)/(delta==0?1.0f:delta));const auto phase=s.Phase();s.left=left;s.right=right;
            s.length=std::fma(s.children[s.right].Length(),s.weight,s.children[s.left].Length()*(1.0f-s.weight));SetTime(s.length*phase);break;
        }
        case PlaybackTreeKind::BlendSpace:
        {
            auto& s=std::get<BlendState>(state_->value);
            for (const auto& a:attributes)
            {
                const auto p=std::find(s.parameters.begin(),s.parameters.end(),a.name);if (p==s.parameters.end()) continue;
                if (!std::isfinite(a.value)) {error="Nonfinite BlendSpace parameter";return false;}s.values[std::size_t(p-s.parameters.begin())]=a.value;changed=true;
            }
            if (!changed) break;std::optional<std::size_t> selected;float closest=std::numeric_limits<float>::max();std::vector<float> selected_weights;
            for (std::size_t index=0;index<s.simplexes.size();++index)
            {
                const auto& simplex=s.simplexes[index];auto weights=simplex.Coordinates(s.values);
                if (std::all_of(weights.begin(),weights.end(),[](auto w){return w>=0;})) {selected=index;selected_weights=std::move(weights);break;}
                weights=simplex.Coordinates(simplex.Project(s.values));for (auto& w:weights) if (w<0) w=0;
                if (!Normalize(weights,error)) return false;float distance=0;
                for (std::size_t j=0;j<s.values.size();++j)
                {
                    float projected=0;for (std::size_t i=0;i<simplex.vertices.size();++i) projected=std::fma(simplex.vertices[i][j],weights[i],projected);
                    distance=std::fma(projected-s.values[j],projected-s.values[j],distance);
                }
                if (distance<closest) {closest=distance;selected=index;selected_weights=std::move(weights);}
            }
            if (!selected) {error="BlendSpace has no finite projection";return false;}
            for (auto& w:selected_weights) w=std::clamp(w,0.0f,1.0f);if (!Normalize(selected_weights,error)) return false;
            if (*selected!=s.current)
            {
                const auto& old=s.children[s.simplexes[s.current].children[0]];const auto phase=old.Time()/old.Length();
                for (auto i:s.simplexes[*selected].children) s.children[i].SetTime(phase*s.children[i].Length());s.current=*selected;
            }
            s.weights=std::move(selected_weights);break;
        }
        case PlaybackTreeKind::SelectionSpace:
        {
            if (!Select(attributes,error)) return false;auto& s=std::get<SelectionState>(state_->value);const auto speed=s.speed;
            if (s.selected) {bool ignored;if (!s.candidates[*s.selected].tree.SetAttributes(attributes,ignored,error)) return false;s.candidates[*s.selected].tree.SetSpeed(speed);}changed=true;break;
        }
        case PlaybackTreeKind::Transition:
        {
            auto& s=std::get<TransitionState>(state_->value);if (!s.to.SetAttributes(attributes,changed,error)) return false;
            if (s.settings.kind==4 && !s.sequence_complete) if (!s.from.SetAttributes(attributes,changed,error)) return false;break;
        }
        case PlaybackTreeKind::BindPose:return std::get<BindState>(state_->value).motion.SetAttributes(attributes,changed,error);
    }
    error.clear();return true;
}
bool AnimationTree::Attributes(std::uint32_t mask,std::vector<AnimationAttribute>& output,std::string& error) const
{
    switch (Kind())
    {
        case PlaybackTreeKind::Clip:return std::get<ClipState>(state_->value).clip.Attributes(mask,output,error);
        case PlaybackTreeKind::PhaseBlend:
        {
            const auto& s=std::get<PhaseState>(state_->value);if (s.weight<s.cull_threshold) return s.children[s.left].Attributes(mask,output,error);
            if (s.weight>1.0f-s.cull_threshold) return s.children[s.right].Attributes(mask,output,error);
            std::vector<AnimationAttribute> left,right;if (!s.children[s.left].Attributes(mask,left,error) || !s.children[s.right].Attributes(31,right,error)) return false;
            return IntersectAnimationAttributes(left,right,s.weight,output,error);
        }
        case PlaybackTreeKind::BlendSpace:
        {
            const auto& s=std::get<BlendState>(state_->value);const auto& indices=s.simplexes[s.current].children;if (!s.children[indices[0]].Attributes(mask,output,error)) return false;
            for (auto& a:output) if (!ScaleAnimationAttribute(a,s.weights[0],error)) return false;
            for (std::size_t slot=1;slot<indices.size();++slot)
            {
                std::vector<AnimationAttribute> right;if (!s.children[indices[slot]].Attributes(mask,right,error)) return false;std::size_t next=0;std::vector<AnimationAttribute> combined;
                for (auto a:output)
                {
                    while (next<right.size() && right[next].name<a.name) ++next;
                    if (next<right.size() && right[next].name==a.name) {if (!AddWeightedAnimationAttribute(a,right[next],s.weights[slot],error)) return false;combined.push_back(a);}
                }
                output=std::move(combined);
            }
            error.clear();return true;
        }
        case PlaybackTreeKind::SelectionSpace:
        {
            const auto& s=std::get<SelectionState>(state_->value);if (!s.selected) {error="SelectionSpace attributes requested before native selection";return false;}
            return s.candidates[*s.selected].tree.Attributes(mask,output,error);
        }
        case PlaybackTreeKind::Transition:
        {const auto& s=std::get<TransitionState>(state_->value);return (s.settings.kind==4 && !s.sequence_complete?s.from:s.to).Attributes(mask,output,error);}
        case PlaybackTreeKind::BindPose:
        {
            const auto& s=std::get<BindState>(state_->value);if (!s.motion.Attributes(mask,output,error)) return false;
            for (auto ignored:s.mirror_modes) {static_cast<void>(ignored);for (auto& a:output) if (!s.mirror->Apply(a,error)) return false;}
            error.clear();return true;
        }
    }
    return false;
}
bool AnimationTree::Attribute(AttributeName name,std::uint32_t mask,std::optional<AnimationAttribute>& output,std::string& error) const
{
    auto value=MotionGraphAttribute{name,0}.ToAnimation();bool found;if (!QueryAttribute(name,mask,value,found,error)) return false;
    output=found?std::optional<AnimationAttribute>(value):std::nullopt;error.clear();return true;
}
bool AnimationTree::QueryAttribute(AttributeName name,std::uint32_t mask,AnimationAttribute& output,bool& found,std::string& error) const
{
    found=false;
    switch (Kind())
    {
        case PlaybackTreeKind::Clip:
        {
            std::optional<AnimationAttribute> value;if (!std::get<ClipState>(state_->value).clip.Attribute(name,mask,value,error)) return false;
            if (value) {output.CopyFrom(*value);found=true;}error.clear();return true;
        }
        case PlaybackTreeKind::PhaseBlend:
        {
            const auto& s=std::get<PhaseState>(state_->value);if (s.weight<s.cull_threshold) return s.children[s.left].QueryAttribute(name,mask,output,found,error);
            if (s.weight>1.0f-s.cull_threshold) return s.children[s.right].QueryAttribute(name,mask,output,found,error);
            bool left,right;if (!s.children[s.left].QueryAttribute(name,mask,output,left,error)) return false;auto other=MotionGraphAttribute{name,0}.ToAnimation();
            if (!s.children[s.right].QueryAttribute(name,31,other,right,error)) return false;
            if (left && right) {if (!BlendAnimationAttribute(output,other,s.weight,error)) return false;found=true;}error.clear();return true;
        }
        case PlaybackTreeKind::BlendSpace:
        {
            const auto& s=std::get<BlendState>(state_->value);bool child_found;if (!s.children[0].QueryAttribute(name,mask,output,child_found,error)) return false;
            if (!child_found) {error.clear();return true;}if (!ScaleAnimationAttribute(output,s.weights[0],error)) return false;
            for (std::size_t i=1;i<s.weights.size();++i)
            {
                auto other=MotionGraphAttribute{name,0}.ToAnimation();if (!s.children[i].QueryAttribute(name,15,other,child_found,error)) return false;
                if (!child_found) {error.clear();return true;}if (!AddWeightedAnimationAttribute(output,other,s.weights[i],error)) return false;
            }
            found=true;error.clear();return true;
        }
        case PlaybackTreeKind::SelectionSpace:
        {
            const auto& s=std::get<SelectionState>(state_->value);if (!s.selected) {error="SelectionSpace attribute requested before native selection";return false;}
            return s.candidates[*s.selected].tree.QueryAttribute(name,mask,output,found,error);
        }
        case PlaybackTreeKind::Transition:
        {const auto& s=std::get<TransitionState>(state_->value);return (s.settings.kind==4 && !s.sequence_complete?s.from:s.to).QueryAttribute(name,mask,output,found,error);}
        case PlaybackTreeKind::BindPose:
        {
            const auto& s=std::get<BindState>(state_->value);if (!s.motion.QueryAttribute(name,mask,output,found,error)) return false;
            if (found) for (auto ignored:s.mirror_modes) {static_cast<void>(ignored);if (!s.mirror->Apply(output,error)) return false;}error.clear();return true;
        }
    }
    return false;
}
bool AnimationTree::Evaluate(AnimationEvaluation parameters,bool enabled,std::vector<PoseCommand>& output,bool& produced,std::string& error)
{
    produced=false;
    switch (Kind())
    {
        case PlaybackTreeKind::Clip:
        {
            auto& s=std::get<ClipState>(state_->value);auto& clock=s.clip.clock;const auto rate=clock.base_speed*clock.speed,limit=(clock.frames-1.0f)/clock.fps;
            auto bound=[&](float time) {const auto lower=-time>=0?0.0f:time;return limit-lower>=0?lower:limit;};
            auto previous=bound(clock.previous_time*rate);const auto time=bound(clock.SampleTime()*rate);
            if (clock.loops_since_evaluation==0 && previous>time) previous=time;
            if (enabled) {auto c=SingleCommand(PoseCommand::Kind::Clip);c.name=s.name;c.previous_time=previous;c.time=time;c.loops=clock.loops_since_evaluation;output.push_back(std::move(c));}
            if (parameters.update_history) clock.CommitEvaluation();produced=enabled;break;
        }
        case PlaybackTreeKind::PhaseBlend:
        {
            auto& s=std::get<PhaseState>(state_->value);s.cull_threshold=parameters.cull_threshold;const auto c=parameters.cull_threshold;
            const auto lower=c-s.weight>=0?c:s.weight,upper=1.0f-c,clamped=upper-lower>=0?lower:upper;
            const auto t=(clamped-c)/std::fma(-c,2.0f,1.0f),square=t*t;float weight=s.weight;
            if (!(t>0.5f) && s.left==s.order[0]) weight=std::fma(-t,4.0f,4.0f)*square;
            else if (t>0.5f && s.right==s.order.back()) {const auto four=t*4.0f;weight=std::fma(8.0f-four,square,-four)+1.0f;}
            bool left,right;if (!s.children[s.left].Evaluate(parameters,enabled && weight<1,output,left,error) || !s.children[s.right].Evaluate(parameters,enabled && weight>0,output,right,error)) return false;
            if (left && right) {auto c=SingleCommand(PoseCommand::Kind::Blend);c.weight=weight;output.push_back(std::move(c));}produced=left||right;break;
        }
        case PlaybackTreeKind::BlendSpace:
        {
            if (!enabled) break;auto& s=std::get<BlendState>(state_->value);
            for (auto i:s.simplexes[s.current].children) {bool child;if (!s.children[i].Evaluate(parameters,true,output,child,error)) return false;if (!child) {error="BlendSpace child produced no pose";return false;}}
            auto c=SingleCommand(PoseCommand::Kind::WeightedBlend);c.weights=s.weights;output.push_back(std::move(c));produced=true;break;
        }
        case PlaybackTreeKind::SelectionSpace:
        {
            if (!enabled) break;auto& s=std::get<SelectionState>(state_->value);if (!s.selected) {error="SelectionSpace evaluated before native selection";return false;}
            return s.candidates[*s.selected].tree.Evaluate(parameters,true,output,produced,error);
        }
        case PlaybackTreeKind::Transition:
        {
            auto& s=std::get<TransitionState>(state_->value);
            if (s.settings.kind==4) return (s.sequence_complete?s.to:s.from).Evaluate(parameters,enabled,output,produced,error);
            const auto weight=TransitionWeight();bool from,to;if (!s.from.Evaluate(parameters,enabled,output,from,error) || !s.to.Evaluate(parameters,enabled,output,to,error)) return false;
            if (enabled && from && to)
            {
                auto c=SingleCommand(s.settings.kind==3?PoseCommand::Kind::ChannelBlend:PoseCommand::Kind::Blend);c.weight=weight;
                if (s.settings.kind==3) c.use_channels_from_weights=s.settings.use_channels_from_weights;output.push_back(std::move(c));
            }
            produced=from||to;break;
        }
        case PlaybackTreeKind::BindPose:
        {
            auto& s=std::get<BindState>(state_->value);if (!s.motion.Evaluate(parameters,enabled,output,produced,error)) return false;
            if (produced)
            {
                auto pose=[&](std::string_view name) {auto c=SingleCommand(PoseCommand::Kind::Pose);c.name=name;output.push_back(std::move(c));};
                auto add=[&](bool motion_is_a) {auto c=SingleCommand(PoseCommand::Kind::Add);c.motion_is_a=motion_is_a;output.push_back(std::move(c));};
                if (s.posture) {pose(PosturePoseName(*s.posture));add(true);}pose("RIG_TPOSE");add(true);
                if (s.board_backwards) {pose("BOARD_BACKWARDS");add(false);pose("BOARD_BACKWARDS_IK");add(true);}
                for (auto mode:s.mirror_modes) {auto c=SingleCommand(PoseCommand::Kind::Mirror);c.trajectory_mode=mode;output.push_back(std::move(c));}
            }
            break;
        }
    }
    error.clear();return true;
}
bool AnimationTree::PrepareSelectionSpaces(const std::vector<SettableAttribute>& attributes,std::string& error)
{
    switch (Kind())
    {
        case PlaybackTreeKind::SelectionSpace:
        {if (!Select(attributes,error)) return false;auto& s=std::get<SelectionState>(state_->value);return s.candidates[*s.selected].tree.PrepareSelectionSpaces(attributes,error);}
        case PlaybackTreeKind::PhaseBlend:for (auto& c:std::get<PhaseState>(state_->value).children) if (!c.PrepareSelectionSpaces(attributes,error)) return false;break;
        case PlaybackTreeKind::Transition:
        {
            auto& s=std::get<TransitionState>(state_->value);if (!s.to.PrepareSelectionSpaces(attributes,error)) return false;
            if (s.settings.kind==4 && !TransitionComplete()) if (!s.from.PrepareSelectionSpaces(attributes,error)) return false;break;
        }
        case PlaybackTreeKind::BindPose:return std::get<BindState>(state_->value).motion.PrepareSelectionSpaces(attributes,error);
        case PlaybackTreeKind::BlendSpace:case PlaybackTreeKind::Clip:break;
    }
    error.clear();return true;
}
bool AnimationTree::TransitionComplete() const
{assert(Kind()==PlaybackTreeKind::Transition);const auto& s=std::get<TransitionState>(state_->value);return s.settings.kind==4?s.sequence_complete:s.elapsed>s.settings.seconds;}
float AnimationTree::TransitionWeight() const
{
    assert(Kind()==PlaybackTreeKind::Transition);const auto& s=std::get<TransitionState>(state_->value);const auto weight=Unit(s.elapsed/s.settings.seconds);
    if (s.settings.seconds<Float(0x3d4ccccd) || weight>1 || weight<0) return weight;
    const auto square=weight*weight,cube=square*weight;return std::fma(square,3.0f,-(cube*2.0f));
}
bool AnimationTree::HasTransition() const
{
    switch (Kind())
    {
        case PlaybackTreeKind::Transition:return true;
        case PlaybackTreeKind::PhaseBlend:for (const auto& c:std::get<PhaseState>(state_->value).children) if (c.HasTransition()) return true;break;
        case PlaybackTreeKind::BlendSpace:for (const auto& c:std::get<BlendState>(state_->value).children) if (c.HasTransition()) return true;break;
        case PlaybackTreeKind::SelectionSpace:{const auto& s=std::get<SelectionState>(state_->value);return s.selected && s.candidates[*s.selected].tree.HasTransition();}
        case PlaybackTreeKind::BindPose:return std::get<BindState>(state_->value).motion.HasTransition();
        case PlaybackTreeKind::Clip:break;
    }
    return false;
}
void AnimationTree::PruneCompletedTransitions()
{
    switch (Kind())
    {
        case PlaybackTreeKind::Transition:
        {
            if (TransitionComplete()) {auto replacement=std::move(std::get<TransitionState>(state_->value).to);replacement.PruneCompletedTransitions();*this=std::move(replacement);}
            else {auto& s=std::get<TransitionState>(state_->value);s.from.PruneCompletedTransitions();s.to.PruneCompletedTransitions();}break;
        }
        case PlaybackTreeKind::PhaseBlend:for (auto& c:std::get<PhaseState>(state_->value).children) c.PruneCompletedTransitions();break;
        case PlaybackTreeKind::BlendSpace:for (auto& c:std::get<BlendState>(state_->value).children) c.PruneCompletedTransitions();break;
        case PlaybackTreeKind::SelectionSpace:for (auto& c:std::get<SelectionState>(state_->value).candidates) c.tree.PruneCompletedTransitions();break;
        case PlaybackTreeKind::BindPose:std::get<BindState>(state_->value).motion.PruneCompletedTransitions();break;
        case PlaybackTreeKind::Clip:break;
    }
}
void AnimationTree::InsertTransitionTo(AnimationTree to,TransitionSettings settings)
{
    if (settings.under!=0 && Kind()==PlaybackTreeKind::Transition)
    {auto& s=std::get<TransitionState>(state_->value);auto from=std::move(s.to);s.to=Transition(std::move(from),std::move(to),settings);}
    else {auto from=std::move(*this);*this=Transition(std::move(from),std::move(to),settings);}
}
std::vector<const AnimationTree*> AnimationTree::Children() const
{
    std::vector<const AnimationTree*> result;
    switch (Kind())
    {
        case PlaybackTreeKind::PhaseBlend:for (const auto& c:std::get<PhaseState>(state_->value).children) result.push_back(&c);break;
        case PlaybackTreeKind::BlendSpace:for (const auto& c:std::get<BlendState>(state_->value).children) result.push_back(&c);break;
        case PlaybackTreeKind::SelectionSpace:for (const auto& c:std::get<SelectionState>(state_->value).candidates) result.push_back(&c.tree);break;
        case PlaybackTreeKind::Transition:{const auto& s=std::get<TransitionState>(state_->value);result={&s.from,&s.to};break;}
        case PlaybackTreeKind::BindPose:result.push_back(&std::get<BindState>(state_->value).motion);break;
        case PlaybackTreeKind::Clip:break;
    }
    return result;
}
std::optional<std::size_t> AnimationTree::SelectedCandidate() const
{return Kind()==PlaybackTreeKind::SelectionSpace?std::get<SelectionState>(state_->value).selected:std::nullopt;}
std::vector<std::pair<std::size_t,float>> AnimationTree::ActiveWeights() const
{
    std::vector<std::pair<std::size_t,float>> result;if (Kind()!=PlaybackTreeKind::BlendSpace) return result;const auto& s=std::get<BlendState>(state_->value);
    const auto& indices=s.simplexes[s.current].children;for (std::size_t i=0;i<indices.size();++i) result.emplace_back(indices[i],s.weights[i]);return result;
}
const ClipClock* AnimationTree::ClipClockState() const
{return Kind()==PlaybackTreeKind::Clip?&std::get<ClipState>(state_->value).clip.clock:nullptr;}
bool AddAnimationBindPose(AnimationTree motion,std::optional<PosturePose> posture,std::optional<std::uint32_t>& flags,std::shared_ptr<const AttributeMirror> mirror,AnimationTree& output,std::string& error)
{
    if (!flags) {error="Animation construction requires actual SkaterAnim flags";return false;}
    const auto value=*flags;std::vector<std::uint32_t> modes;if ((value&0x40000000)!=0) modes.push_back(2);
    if ((value&0x00400000)!=0) modes.push_back(std::uint32_t((value&0x00200000)==0)+1);flags=value&~0x00600000;
    if (!modes.empty() && (!mirror || mirror->names.empty())) {error="Mirrored animation requires the stock bone hierarchy";return false;}
    output=AnimationTree::BindPose(std::move(motion),posture,(value&0x80000000)!=0,std::move(modes),std::move(mirror));error.clear();return true;
}
namespace
{
bool Build(const AnimationMetadata& metadata,std::string_view name,const std::vector<std::pair<AttributeName,AttributeName>>& construction,std::vector<std::string>& parents,AnimationTree& output,std::string& error)
{
    std::string key(name);for (auto& c:key) if (c>='a' && c<='z') c=char(c-'a'+'A');
    if (std::find(parents.begin(),parents.end(),key)!=parents.end()) {error="Cyclic authored animation tree "+key;return false;}parents.push_back(key);
    AnimationTreeMetadata source;if (!metadata.Tree(name,source,error)) return false;
    auto children=[&](const std::vector<std::string>& names,std::vector<AnimationTree>& values)
    {for (const auto& n:names) {AnimationTree child;if (!Build(metadata,n,construction,parents,child,error)) return false;values.push_back(std::move(child));}return true;};
    bool ok=false;
    switch (source.kind)
    {
        case AnimationTreeKind::Clip:output=AnimationTree::Clip(source.clip->name,PlaybackClip(*source.clip));ok=true;break;
        case AnimationTreeKind::PhaseBlend:
        {std::vector<AnimationTree> values;if (!children(source.phase_blend->children,values)) return false;ok=AnimationTree::PhaseBlend(EncodeAnimationName(source.phase_blend->parameter),std::move(values),output,error);break;}
        case AnimationTreeKind::BlendSpace:
        {
            const auto& t=*source.blend_space;std::vector<AttributeName> parameters;for (const auto& p:t.parameters) parameters.push_back(EncodeAnimationName(p));
            std::vector<AnimationTree> values;if (!children(t.children,values)) return false;std::vector<AnimationBlendSimplex> simplexes;
            for (const auto& s:t.simplexes)
            {
                AnimationBlendSimplex simplex;simplex.children.assign(s.children.begin(),s.children.end());
                for (const auto* matrix:{&s.vertex_bits,&s.normal_bits}) {auto& destination=matrix==&s.vertex_bits?simplex.vertices:simplex.normals;
                    for (const auto& row:*matrix) {std::vector<float> value;for (auto v:row) value.push_back(Float(v));destination.push_back(std::move(value));}}
                for (auto v:s.scale_bits) simplex.scales.push_back(Float(v));simplexes.push_back(std::move(simplex));
            }
            ok=AnimationTree::BlendSpace(std::move(parameters),std::move(values),std::move(simplexes),output,error);break;
        }
        case AnimationTreeKind::SelectionSpace:
        {
            const auto& t=*source.selection_space;std::vector<SelectionParameter> parameters;for (const auto& p:t.parameters) parameters.push_back({EncodeAnimationName(p.name),p.mode,Float(p.weight_bits),Float(p.minimum_bits),Float(p.maximum_bits)});
            std::vector<AnimationSelectionCandidate> candidates;for (const auto& c:t.candidates)
            {
                AnimationSelectionCandidate candidate;candidate.name=c.child;for (auto v:c.value_bits) candidate.values.push_back(Float(v));
                if (!Build(metadata,c.child,construction,parents,candidate.tree,error)) return false;candidates.push_back(std::move(candidate));
            }
            ok=AnimationTree::SelectionSpace(std::move(parameters),std::move(candidates),output,error);break;
        }
        case AnimationTreeKind::Selector:
        {
            const auto& t=*source.selector;const auto parameter=EncodeAnimationName(t.parameter);const auto value=std::find_if(construction.begin(),construction.end(),[&](const auto& p){return p.first==parameter;});
            const std::string* child=&t.default_child;if (value!=construction.end()) for (std::size_t i=0;i<t.values.size();++i) if (EncodeAnimationName(t.values[i])==value->second) {child=&t.children[i];break;}
            ok=Build(metadata,*child,construction,parents,output,error);break;
        }
    }
    if (!ok) return false;parents.pop_back();error.clear();return true;
}
}
bool BuildAnimationTree(const AnimationMetadata& metadata,std::string_view name,const std::vector<std::pair<AttributeName,AttributeName>>& construction,AnimationTree& output,std::string& error)
{std::vector<std::string> parents;return Build(metadata,name,construction,parents,output,error);}
AnimationTreeOwner::AnimationTreeOwner(AnimationMetadata metadata):attribute_mirror(std::make_shared<AttributeMirror>()),metadata_(std::move(metadata)) {}
bool AnimationTreeOwner::SetHierarchy(const std::vector<std::string>& names,const std::vector<std::int32_t>& indices,std::string& error)
{
    if (names.size()!=indices.size()) {error="Animation hierarchy mirror count differs from bone count";return false;}
    auto mirror=std::make_shared<AttributeMirror>();for (std::size_t i=0;i<names.size();++i)
    {
        const std::string* target=&names[i];if (indices[i]>=0) {if (std::size_t(indices[i])>=names.size()) {error="Invalid mirrored bone index";return false;}target=&names[std::size_t(indices[i])];}
        else if (indices[i]!=-1) {error="Invalid negative mirrored bone index";return false;}
        mirror->names.emplace_back(EncodeAnimationName(names[i]),EncodeAnimationName(*target));
    }
    attribute_mirror=std::move(mirror);error.clear();return true;
}
void AnimationTreeOwner::SetConstructionValue(AttributeName name,AttributeName value)
{
    const auto found=std::find_if(construction_values.begin(),construction_values.end(),[&](const auto& p){return p.first==name;});
    if (found==construction_values.end()) construction_values.emplace_back(name,value);else found->second=value;
}
bool AnimationTreeOwner::BuildTree(std::string_view name,AnimationTree& output,std::string& error) const
{return BuildAnimationTree(metadata_,name,construction_values,output,error);}
bool AnimationTreeOwner::Play(const PlaybackRequest& request,bool& played,std::string& error)
{
    played=false;if (request.transition.kind<1 || request.transition.kind>4) {error.clear();return true;}
    if (request.transition.kind==1) current.reset();AnimationTree motion;if (!BuildTree(request.animation,motion,error)) return false;
    std::optional<PosturePose> pose;
    if (posture_bank_valid)
    {
        if (!posture.Apply(motion,[&](AnimationTree&,PosturePose value,std::string& failure){pose=value;failure.clear();return true;},error)) return false;
    }
    AnimationTree tree;if (!AddAnimationBindPose(std::move(motion),pose,skater_animation_flags,attribute_mirror,tree,error)) return false;tree.SetSpeed(request.speed);
    if (request.start_time>0 && (request.transition.kind==1 || current)) tree.SetTime(request.start_time);
    if (current) current->InsertTransitionTo(std::move(tree),request.transition);else current=std::move(tree);
    current_name=request.animation;played=true;error.clear();return true;
}
bool AnimationTreeOwner::Advance(float dt,float phase,std::string& error)
{
    if (current) current->PruneCompletedTransitions();property={false,-1,-1};
    if (current && !current->Advance(dt,phase,property,error)) return false;error.clear();return true;
}
bool AnimationTreeOwner::ApplyParameters(std::string& error)
{
    const auto attributes=settable.Entries();
    if (current) {if (!current->PrepareSelectionSpaces(attributes,error)) return false;bool changed;if (!current->SetAttributes(attributes,changed,error)) return false;}
    settable.Clear();error.clear();return true;
}
bool AnimationTreeOwner::EvaluatePose(AnimationEvaluation parameters,std::vector<PoseCommand>& output,std::string& error)
{
    output.clear();if (!current) {error="MotionGraph has not selected an animation";return false;}bool produced;return current->Evaluate(parameters,true,output,produced,error);
}
bool AnimationTreeOwner::RefreshTreeAttributes(std::string& error)
{if (!current) {tree_attributes.clear();error.clear();return true;}std::vector<AnimationAttribute> output;if (!current->Attributes(15,output,error)) return false;tree_attributes=std::move(output);error.clear();return true;}
}
