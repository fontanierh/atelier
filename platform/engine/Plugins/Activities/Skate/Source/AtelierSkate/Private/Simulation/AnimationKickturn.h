#pragma once
#include "Graph.h"
#include "MotionAnimation.h"
#include "SimulationMath.h"
#include "Settings.h"
namespace atelier::skate
{
struct AnimationKickturnSettings {PointGraph<8> spin,height;};
struct AnimationKickturnOperation {float max_height=.5f,spin_scale=.5f;};
struct AnimationKickturnOutput {float balance,spin;};
struct AnimationKickturnState
{
    float animation_length=0,elapsed=0,previous_height=0,last_nonzero_intent=0;
    bool first_update=true;
    void Begin(const AnimationKickturnSettings&);
    AnimationKickturnOutput Update(float dt,float intent,AnimationKickturnOperation,const AnimationKickturnSettings&);
};
bool LoadAnimationKickturnSettings(const SettingsDatabase&,AnimationKickturnSettings&,std::string& error);
bool ParseAnimationKickturnOperation(const GraphAttributes&,AnimationKickturnOperation&,bool& recognized,std::string& error);
// First Update applies pending attributes before querying the live tree length;
// later Updates retain that captured length even while tree parameters change.
bool ExecuteAnimationKickturnOperation(AnimationKickturnOperation,AnimationKickturnState&,const AnimationKickturnSettings&,
    MotionAnimation&,float dt,std::uint8_t phase,std::string& error);
}
