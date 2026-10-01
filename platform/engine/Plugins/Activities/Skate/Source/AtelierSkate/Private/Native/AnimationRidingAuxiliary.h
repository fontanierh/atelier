// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "Graph.h"
#include "MotionAnimation.h"
#include "Settings.h"
namespace atelier::skate
{
struct AnimationBumpSettings
{
    float scale_x_acc,min_bump_mag,max_bump_mag,min_bump_blend_value;
};
std::array<float,2> AnimationBumpCoefficients(Vec4 conditioned_ground_acceleration,
    bool mirrored,const AnimationBumpSettings&);
bool LoadAnimationBumpSettings(const SettingsDatabase&,AnimationBumpSettings&,std::string& error);
struct AnimationFakieHeadState
{
    float value=0;
    bool was_fakie=false;
    bool Update(MotionAnimation&,bool manualing,bool power_sliding,bool fakie,std::string& error);
};
struct GraphMotionAuxiliaryFeedbackOperation
{
    enum class Kind {Unsupported,Bump,FakieHead};
    Kind kind=Kind::Unsupported;
    std::array<AttributeName,2> names{};
};
bool ParseGraphMotionAuxiliaryFeedbackOperation(const GraphAttributes&,
    GraphMotionAuxiliaryFeedbackOperation&,bool& recognized,std::string& error);
bool ExecuteGraphMotionAuxiliaryFeedbackOperation(const GraphMotionAuxiliaryFeedbackOperation&,
    AnimationFakieHeadState&,std::uint8_t phase,MotionAnimation&,const AnimationBumpSettings&,
    const std::optional<Vec4>& actual_bump_acceleration,bool manualing,bool power_sliding,std::string& error);
}
