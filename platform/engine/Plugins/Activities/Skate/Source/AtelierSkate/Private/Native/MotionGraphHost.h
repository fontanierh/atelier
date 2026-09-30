// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "CompiledGraph.h"
#include "GraphIntentOperations.h"
#include "GraphMotionConditions.h"
#include "GraphMotionSliding.h"
#include "GraphMotionPhysicalConditions.h"
#include "GraphMotionSpecialConditions.h"
#include "GraphMotionFeedbackOperations.h"
#include "GraphMotionScoreOperations.h"
#include "MotionAnimationOperations.h"
#include <variant>

namespace atelier::skate
{
struct MotionGraphOperation
{
    enum class Kind
    {
        Unsupported,Unported,SourceMissingProducer,Condition,PhysicalCondition,SpecialCondition,Feedback,Score,Animation,Attach,IntentFilter,PrintText,
        GrabType,Dark,MonitorUnderflip,Anticipating,Landing,Manualing,DoingTrick,DisableTricks,
        ManualOutTimer,SetManualOutTimer,TimeSinceTeleport,TimeSinceKickturn,ResetKickturn,
        DistComToBoard,ForcePhysics,SetSpeed,ApplyingBodyTilt,ResetAnimation,ResetGivenStance,
        HandBusy,MaintainShove,SlideUpdate,SlideCreate,SlideManual,SlideDeceleration,SlideSpin,
        SlideCandidate,PowerSlidingFlag,WeightOnNose,ClearTrickAttribute,JumpInto,SourceStandingOnCarNoop,
        GrabSlideHook,OverrideHook,MongoPushHook
    };
    Kind kind=Kind::Unsupported;
    GraphOperationKind source_kind=GraphOperationKind::Behavior;
    std::string name,text;
    GraphMotionCondition condition;
    GraphMotionPhysicalCondition physical_condition;
    GraphMotionSpecialCondition special_condition;
    GraphMotionFeedbackOperation feedback;
    GraphMotionScoreOperation score;
    MotionAnimationOperation animation;
    AttachIntentOperation attach;
    MotionIntentFilterOperation filter;
    TransitionSettings transition;
    AttributeName attribute{};
    float value=0;
    std::optional<float> optional_value;
    bool right=true,set_manually=false,adjust_for_velocity=false;
    std::uint32_t ordinal=0;
};
struct MotionGraphLandingInstance {float value=0;bool complete=false;};
struct MotionGraphJumpInstance {bool first_update=true;};
using MotionGraphInstance=std::variant<std::monostate,MotionIntentFilterState,GraphMotionSlidingState,
    float,std::int32_t,MotionGraphLandingInstance,MotionGraphJumpInstance,MotionAnimationOperationState,
    GraphMotionFeedbackInstance>;
struct MotionGraphCapabilities
{
    std::size_t supported=0;
    std::vector<std::string> unported,source_unsupported,source_missing_producers,source_placeholder_noops;
};
class MotionGraphHost final:public graph::Host
{
public:
    explicit MotionGraphHost(MotionAnimation& owner):animation(owner) {}
    MotionAnimation& animation;
    PlaybackContext playback_context;
    MotionGraphPhysicalPublication physical;
    GraphActionControls action_controls;
    IntentMap action_intents;
    GraphTurningOutput turning_output;
    std::vector<std::uint32_t> state_requests;
    std::optional<std::map<std::string,float>> time_tags;
    MotionGraphFlags flags;
    MotionGraphTrickRequests trick_requests;
    MotionGraphRidingState riding;
    std::optional<MotionGraphPushState> push_state=MotionGraphPushState{};
    MotionConditionRandom condition_random;
    SlideLatch slide_latch;
    bool is_power_sliding=false,applying_body_tilt=false,hold_fakie=false;
    std::array<std::uint32_t,2> busy_hands{};
    bool keep_shove_channels=false;
    float animation_phase=0;
    std::optional<GraphMotionSlidingSettings> sliding_settings;
    std::optional<GraphMotionFeedbackSettings> feedback_settings;
    GraphMotionFeedbackOwner feedback_owner;
    MotionGraphScorePacket score_packet;
    MotionGraphMovingObjectRegistry moving_objects;
    std::pair<bool,bool> trick_height_settings{true,true};
    std::optional<SetTurningPhysical> turning_physical;
    std::optional<AnimationCrouchingPhysical> crouching_physical;
    std::optional<AnimationBodyTiltPhysical> body_tilt_physical;
    std::optional<AnimationFakiePhysical> fakie_physical;
    std::optional<float> pumping_acceleration;
    std::optional<std::array<float,2>> deck_yaw_pitch;
    std::optional<MotionGraphRidingConditionInputs> riding_condition_inputs;
    std::optional<MotionGraphGrindConditionInputs> grind_condition_inputs;
    std::optional<MotionGraphLandingInputs> landing_inputs;
    std::optional<MotionGraphWipeoutConditionInputs> wipeout_condition_inputs;
    std::optional<MotionGraphPrelandingInputs> prelanding_inputs;
    std::optional<MotionGraphPrelandingConditionSettings> prelanding_condition_settings;
    // Required only by slide operations. Each is a completed physical field.
    std::optional<float> ground_projected_speed;
    std::optional<Vec4> deck_velocity,reckoning_z;
    std::optional<Mat4> reckoning_ground;
    std::vector<MotionGraphOperation> operations;
    std::vector<MotionGraphInstance> instances;
    MotionGraphCapabilities capabilities;
    std::vector<std::string> errors;
    bool diagnostics_overflowed=false;
    bool FromGraph(const Graph&,const GraphBinding&,const CompiledGraph&,const SettingsDatabase&,std::string& error);
    void PublishPhysical(MotionGraphPhysicalPublication value) {physical=std::move(value);}
    void AcceptActionGraph(const MotionGraphInput&);
    std::string Diagnostics(std::string_view separator) const;
    graph::Context GetContext() const override {return {};}
    std::uint32_t ConditionActivation(graph::Id,const graph::Frame&) override;
    std::uint32_t Allocate(graph::Id,const graph::Frame&) override;
    void Begin(graph::Id,graph::Context,const graph::Frame&) override;
    void Update(graph::Id,graph::Context,const graph::Frame&) override;
    void End(graph::Id,graph::Context,const graph::Frame&) override;
    void Hook(graph::Id,const graph::Frame&) override;
    void Release(std::uint32_t) override {}
private:
    GraphOperationRemap remap_;
    std::vector<std::optional<graph::Id>> parents_;
    std::vector<bool> automatic_fakie_conditions_;
    std::uint32_t next_instance_=1;
    void AddError(std::string);
    void Run(graph::Id,const graph::Frame&,std::uint8_t phase);
    bool Execute(graph::Id,const MotionGraphOperation&,const graph::Frame&,std::uint8_t,std::string& error);
    bool SlideDirection(float&,std::string& error) const;
    MotionConditionContext ConditionContext();
};
bool ParseMotionGraphOperation(GraphOperationKind,const GraphAttributes&,MotionGraphOperation&,std::string& error);
}
