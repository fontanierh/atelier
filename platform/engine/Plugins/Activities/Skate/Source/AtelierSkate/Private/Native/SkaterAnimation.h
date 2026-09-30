// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "ActionGraphFrame.h"
#include "AnimationPose.h"
#include "AnimationPublication.h"
#include "MotionGraphHost.h"

namespace atelier::skate
{
struct AnimationCrouchingPhysical
{
    float body_84,body_164,body_188,force_516,ground_force_520;
    float minimum_crouch_528,deck_angle_532,animation_height_72;
};
struct AnimationBodyTiltPhysical {float lateral_tilt,body_spin_speed;std::uint32_t filtered_category;};
struct AnimationFakiePhysical
{
    std::uint32_t category,grind_state;
    bool doing_trick;
    Vec4 board_axis,deck_velocity,external_velocity;
    float ground_projected_speed;
};
struct AnimationPhysicalFeedback
{
    SetTurningPhysical turning;
    AnimationCrouchingPhysical crouching;
    float pumping_acceleration;
    Vec4 ground_acceleration;
    bool bumped;
    std::array<float,8> conditioned_turn;
};
// These are preceding completed simulation publications. There is no neutral
// constructor: callers provide the actual producer record and its absence.
struct AnimationPhysical
{
    GraphConditionInputs conditions;
    AnimationPhysicalFeedback feedback;
    AnimationBodyTiltPhysical body_tilt;
    AnimationFakiePhysical fakie;
    std::pair<bool,bool> physical_stance;
    MotionGraphFootFrame foot_frame;
    bool board_present,physical_28_byte75;
    float time_since_teleport;
};
struct AnimationLoadedGraph {Graph source;GraphBinding binding;CompiledGraph runtime;};
struct AnimationStockGraphs {AnimationLoadedGraph action,motion;};
// The asset packager supplies verified project-native metadata, rig and clips.
// Original bank formats are confined to migration conversion/oracles.
struct AnimationSource
{
    AnimationMetadata metadata;
    std::shared_ptr<AnimationPoseEvaluator> evaluator;
};
class SkaterAnimation
{
public:
    static bool FromSource(const SettingsDatabase& data,const AnimationStockGraphs& graphs,
        std::string_view pro_skater,std::shared_ptr<const AnimationSource> source,
        std::unique_ptr<SkaterAnimation>& output,std::string& error);
    ActionIntentGraphHost action;
    MotionAnimation animation;
    MotionGraphHost motion;
    std::shared_ptr<AnimationPoseEvaluator> evaluator;
    std::shared_ptr<const AnimationSource> source;
    std::vector<Sqt> pose;
    PhysicsPosePacket packet;
    PacketAttributes attributes;
    graph::Controller action_controller,motion_controller;
    AnimationPublication state;
    std::uint64_t ticks=0;
    // Retained real feedback for physical-backed graph owners that have not
    // yet been registered. Their operations still report explicit errors.
    std::optional<AnimationPhysical> completed_physical;
    std::uint32_t CheckpointStance() const {return state.CheckpointStance();}
    void RequestCheckpointStance(std::uint32_t foot) {animation.requested_stance=state.RequestedStanceForFoot(foot);}
    bool FootForward() const {return CheckpointStance()!=0;}
    void RestoreFootForward(bool forward) {RequestCheckpointStance(std::uint32_t(forward));}
    void SetCustomisation(std::uint32_t natural,std::uint32_t style);
    std::pair<bool,bool> Stance() const {return {state.Fakie(),state.Mirrored()};}
    bool EvaluateInitialPose(std::vector<Mat4>& output,std::string& error);
    bool Advance(const AnimationStockGraphs& graphs,float dt,const IntentMap& action_intents,
        const AnimationPhysical& physical,AnimationAdditionalResetFields& reset_fields,std::string& error);
private:
    SkaterAnimation(std::shared_ptr<const AnimationSource> source,const AnimationStockGraphs& graphs);
    bool PublishPhysical(const AnimationPhysical& physical,std::string& error);
};
}
