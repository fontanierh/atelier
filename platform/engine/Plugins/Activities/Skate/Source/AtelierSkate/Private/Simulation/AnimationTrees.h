#pragma once
#include "AnimationPlaybackParameters.h"
#include <functional>
#include <memory>

namespace atelier::skate
{
enum class PosturePose : std::uint32_t { Stiff=0, Slouch=1, Buff=2 };
std::optional<PosturePose> PosturePoseFromProfile(std::uint32_t value);
std::string_view PosturePoseName(PosturePose value);
class PendingPosture
{
public:
    void SetProfile(std::uint32_t value) {profile_=value;}
    std::uint32_t Profile() const {return profile_;}
    void SetRequested(bool value) {pending_=value;}
    bool IsPending() const {return pending_;}
    std::optional<PosturePose> SelectedPose() const;
    template<class T,class F> bool Apply(T& motion,F wrap,std::string& error)
    {
        const auto pose=SelectedPose();if (!pose) {error.clear();return true;}
        if (!wrap(motion,*pose,error)) return false;pending_=false;error.clear();return true;
    }
private:
    std::uint32_t profile_=0;
    bool pending_=false;
};
struct PoseCommand
{
    enum class Kind : std::uint32_t { Clip=0, Blend=1, WeightedBlend=2, ChannelBlend=3, Pose=4, Add=5, Mirror=6 };
    Kind kind=Kind::Clip;
    std::string name;
    float previous_time=0,time=0,weight=0;
    std::uint32_t loops=0,trajectory_mode=0;
    std::vector<float> weights;
    bool use_channels_from_weights=false,motion_is_a=false;
};
struct AnimationEvaluation {float cull_threshold=0;bool update_history=false;};
struct AnimationBlendSimplex
{
    std::vector<std::size_t> children;
    std::vector<std::vector<float>> vertices,normals;
    std::vector<float> scales;
    std::vector<float> Coordinates(const std::vector<float>& point) const;
    std::vector<float> Project(const std::vector<float>& point) const;
};
enum class PlaybackTreeKind { Clip, PhaseBlend, BlendSpace, SelectionSpace, Transition, BindPose };
struct AnimationSelectionCandidate;
class AnimationTree
{
public:
    AnimationTree();
    ~AnimationTree();
    AnimationTree(const AnimationTree& other);
    AnimationTree& operator=(const AnimationTree& other);
    AnimationTree(AnimationTree&& other) noexcept;
    AnimationTree& operator=(AnimationTree&& other) noexcept;
    static AnimationTree Clip(std::string name,PlaybackClip clip);
    static bool PhaseBlend(AttributeName parameter,std::vector<AnimationTree> children,AnimationTree& output,std::string& error);
    static bool BlendSpace(std::vector<AttributeName> parameters,std::vector<AnimationTree> children,std::vector<AnimationBlendSimplex> simplexes,AnimationTree& output,std::string& error);
    static bool SelectionSpace(std::vector<SelectionParameter> parameters,std::vector<AnimationSelectionCandidate> candidates,AnimationTree& output,std::string& error);
    static AnimationTree Transition(AnimationTree from,AnimationTree to,TransitionSettings settings);
    static AnimationTree BindPose(AnimationTree motion,std::optional<PosturePose> posture,bool board_backwards,std::vector<std::uint32_t> mirror_modes,std::shared_ptr<const AttributeMirror> mirror);
    PlaybackTreeKind Kind() const;
    bool AppendBindPoseMirrorMode(std::uint32_t mode,std::string& error);
    float Length() const;
    float Time() const;
    void SetTime(float time);
    void SetSpeed(float speed);
    bool Advance(float dt,float phase,AdvanceResult& property,std::string& error);
    bool SetAttributes(const std::vector<SettableAttribute>& attributes,bool& changed,std::string& error);
    bool Attributes(std::uint32_t mask,std::vector<AnimationAttribute>& output,std::string& error) const;
    bool QueryAttribute(AttributeName name,std::uint32_t mask,AnimationAttribute& output,bool& found,std::string& error) const;
    bool Attribute(AttributeName name,std::uint32_t mask,std::optional<AnimationAttribute>& output,std::string& error) const;
    bool Evaluate(AnimationEvaluation parameters,bool enabled,std::vector<PoseCommand>& output,bool& produced,std::string& error);
    // Original MotionAnimation's deferred raw-child traversal: BlendSpace does
    // not forward parameter preparation to children, unlike PhaseBlend.
    bool PrepareSelectionSpaces(const std::vector<SettableAttribute>& attributes,std::string& error);
    bool TransitionComplete() const;
    float TransitionWeight() const;
    bool HasTransition() const;
    void PruneCompletedTransitions();
    void InsertTransitionTo(AnimationTree to,TransitionSettings settings);
    // Public state probes expose the actual graph's live children without
    // flattening or deduplicating authored references.
    std::vector<const AnimationTree*> Children() const;
    std::optional<std::size_t> SelectedCandidate() const;
    std::vector<std::pair<std::size_t,float>> ActiveWeights() const;
    const ClipClock* ClipClockState() const;
private:
    struct State;
    std::unique_ptr<State> state_;
    bool Select(const std::vector<SettableAttribute>& attributes,std::string& error);
};
struct AnimationSelectionCandidate {std::string name;std::vector<float> values;AnimationTree tree;};
bool BuildAnimationTree(const AnimationMetadata& metadata,std::string_view name,const std::vector<std::pair<AttributeName,AttributeName>>& construction,AnimationTree& output,std::string& error);
// AddBindPose consumes bits22/21 before validating the hierarchy, just as the
// host does; missing actor flags and missing mirrored hierarchy are errors.
bool AddAnimationBindPose(AnimationTree motion,std::optional<PosturePose> posture,std::optional<std::uint32_t>& flags,std::shared_ptr<const AttributeMirror> mirror,AnimationTree& output,std::string& error);
// Main-tree portion of MotionAnimation. The actor owns channel and physical
// scheduling around these separate construction/parameter/evaluation calls.
class AnimationTreeOwner
{
public:
    explicit AnimationTreeOwner(AnimationMetadata metadata);
    std::optional<AnimationTree> current;
    std::optional<std::string> current_name;
    std::vector<std::pair<AttributeName,AttributeName>> construction_values;
    PendingPosture posture;
    bool posture_bank_valid=false;
    std::optional<std::uint32_t> skater_animation_flags;
    std::shared_ptr<const AttributeMirror> attribute_mirror;
    AdvanceResult property{false,-1,-1};
    std::vector<AnimationAttribute> tree_attributes;
    SettableAttributes settable;
    const AnimationMetadata& Metadata() const {return metadata_;}
    bool SetHierarchy(const std::vector<std::string>& names,const std::vector<std::int32_t>& mirror_indices,std::string& error);
    void SetConstructionValue(AttributeName name,AttributeName value);
    bool BuildTree(std::string_view name,AnimationTree& output,std::string& error) const;
    bool Play(const PlaybackRequest& request,bool& played,std::string& error);
    bool Advance(float dt,float phase,std::string& error);
    bool ApplyParameters(std::string& error);
    bool EvaluatePose(AnimationEvaluation parameters,std::vector<PoseCommand>& output,std::string& error);
    bool RefreshTreeAttributes(std::string& error);
private:
    AnimationMetadata metadata_;
};
}
