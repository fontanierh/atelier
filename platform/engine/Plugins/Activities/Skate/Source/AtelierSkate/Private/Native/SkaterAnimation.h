// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "ActionGraphFrame.h"
#include "AnimationPose.h"
#include "AnimationPublication.h"
#include "AnimationPhysical.h"
#include "MotionGraphHost.h"
#include "MotionGraphContinuationHost.h"

namespace atelier::skate
{
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
    MotionGraphContinuationHost complete_motion;
    std::shared_ptr<AnimationPoseEvaluator> evaluator;
    std::shared_ptr<const AnimationSource> source;
    std::vector<Sqt> pose;
    PhysicsPosePacket packet;
    PacketAttributes attributes;
    graph::Controller action_controller,motion_controller;
    AnimationPublication state;
    std::uint64_t ticks=0;
    // Retained preceding completed simulation feedback.
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
