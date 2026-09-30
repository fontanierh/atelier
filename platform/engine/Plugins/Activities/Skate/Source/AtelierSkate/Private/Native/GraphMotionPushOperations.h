// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "MotionAnimation.h"
#include "MotionFrame.h"
#include "Settings.h"
namespace atelier::skate
{
struct MotionGraphPushClipMetrics {float length,begin_velocity,end_velocity;};
struct MotionGraphPushAttributes
{
    std::array<MotionGraphPushClipMetrics,4> clips{};
    float minimum_begin_velocity=0,maximum_begin_velocity=0,minimum_delta_velocity=0,maximum_delta_velocity=0;
    static MotionGraphPushAttributes FromClips(std::array<MotionGraphPushClipMetrics,4>);
    MotionGraphPushBlend Target(float forward_speed,float strength) const;
    float OutFactor(float forward_speed,float strength,float speed_weight,float maximum_out) const;
};
struct MotionGraphPushCurves
{
    PointGraph<8> button_time_max,button_time_to_dv,blend_speed_over_frames,blend_acc_over_frames;
    float Strength(float held_seconds,float speed) const;
    MotionGraphPushBlend UpdateBlend(MotionGraphPushBlend current,MotionGraphPushBlend target,float forward_speed,float dt) const;
};
struct GraphMotionPushSettings
{
    MotionGraphPushCurves curves;
    float teleport_window=0,maximum_holding_acceleration=0,out_speed_weight=0,maximum_out_factor=0;
    MotionGraphPushAttributes regular,mongo;
    bool Load(const SettingsDatabase&,const AnimationMetadata&,std::string& error);
    const MotionGraphPushAttributes& Attributes(bool regular_attributes,bool is_switch) const;
};
struct MotionGraphFirstPushStrength
{
    float simulated_held_seconds=0;
    bool push_from_teleport=false,first_push=true,first_update=true;
    static MotionGraphFirstPushStrength Begin(float time_since_teleport,float teleport_window);
    void Update(MotionGraphPushState&,const MotionGraphPushCurves&,std::optional<float> pushing,float forward_speed,float dt);
};
struct MotionGraphPushIntents {std::optional<float> pushing;bool new_push=false,configured_foot=false;};
struct MotionGraphPushCycle
{
    enum class Phase {HoldingFirst,WaitingNext,HoldingNext,NextReleased};
    Phase phase=Phase::WaitingNext;
    float next_push_dv=0;
    static MotionGraphPushCycle Begin(MotionGraphPushState&,const MotionGraphPushCurves&,MotionGraphPushIntents);
    void Update(MotionGraphPushState&,const MotionGraphPushCurves&,MotionGraphPushIntents,float forward_speed,float maximum_holding_acceleration);
};
struct GraphMotionPushInstance
{
    std::optional<MotionGraphFirstPushStrength> first_strength;
    std::optional<MotionGraphPushCycle> cycle;
    bool first_update=false;
};
struct MotionGraphPushPhysical
{
    float forward_speed;
    bool is_switch;
    std::optional<MotionGraphFootFrame> foot_frame;
};
struct MotionPushOperationContext
{
    const GraphMotionPushSettings& settings;
    std::optional<MotionGraphPushState>& shared;
    MotionAnimation& animation;
    const std::optional<MotionGraphPushPhysical>& physical;
    float time_since_teleport,dt;
};
struct GraphMotionPushOperation
{
    enum class Kind {Unsupported,Init,FirstStrength,TargetCoefficients,RepushDeadline,SetCoefficients,Cycle,Out};
    Kind kind=Kind::Unsupported;
    bool regular_attributes=true,on_first_update_only=false,right_foot=true;
    std::string new_push_name="LeftPush";
    bool Execute(GraphMotionPushInstance&,MotionPushOperationContext,std::uint8_t phase,std::string& error) const;
};
bool ParseGraphMotionPushOperation(const GraphAttributes&,GraphMotionPushOperation&,bool& recognized,std::string& error);
}
