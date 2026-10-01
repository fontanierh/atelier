// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "Graph.h"
#include "MotionAnimation.h"
#include "NativeMath.h"
#include "Settings.h"
namespace atelier::skate
{
struct MotionGraphGrindFadeSettings {float response,input_scale,acceleration,maximum_step;};
struct MotionGraphGrindSettings
{
    MotionGraphGrindFadeSettings fade{};
    std::array<float,3> height{};
    bool Load(const SettingsDatabase&,std::string& error);
};
struct MotionGraphGrindFadeState
{
    bool just_began=false;
    float elapsed=0,value=0,target=0,step=0,minimum=0,maximum=0;
    float Begin(float minimum,float maximum,float twist);
    std::optional<float> Update(float dt,float intent,MotionGraphGrindFadeSettings);
};
struct MotionGraphGrindState
{
    std::optional<MotionGraphGrindFadeState> fade;
    std::optional<float> height;
};
// Actual completed publications; no Default makes absence an explicit input.
struct MotionGraphGrindPhysical
{
    bool grinding;
    AttributeName grind_name;
    Vec3 deck_velocity,effective_board_forward;
    bool processed_bit20;
    float animation_height,physical_crouch,raw_skeleton_twist;
};
struct GraphMotionGrindOperation
{
    enum class Kind {Unsupported,Attributes,Crouch,Fade};
    Kind kind=Kind::Unsupported;
    AttributeName height{},twist{};
    std::string intent;
    bool Execute(MotionGraphGrindState&,MotionAnimation&,const MotionGraphGrindSettings&,
        const std::optional<MotionGraphGrindPhysical>&,float dt,std::uint8_t phase,std::string& error) const;
};
bool ParseGraphMotionGrindOperation(const GraphAttributes&,GraphMotionGrindOperation&,bool& recognized,std::string& error);
bool MotionGraphGrindFacingBackwards(Vec3 deck_velocity,Vec3 effective_board_forward,bool processed_bit20,bool mirrored);
float MotionGraphGrindCrouch(float previous,float intent,float physical,float minimum,float maximum,float rate,float dt);
float MotionGraphGrindMirroredTwist(float twist,bool mirrored);
bool MotionGraphGrindEndpoints(MotionAnimation&,AttributeName,std::array<float,2>& output,std::string& error);
}
