#pragma once
#include "FilteredState.h"
#include "PlayerInputTypes.h"
#include "GraphConditions.h"
#include "GraphMotionGrindOperations.h"
#include "GraphMotionSpecialConditions.h"
namespace atelier::skate
{
struct AnimationStatePublication
{
    GraphPhysicalStateInputs conditions;
    MotionGraphGrindPhysical grind;
    MotionGraphGrindConditionInputs grind_conditions;
    bool animation_mirrored;
};
// Completed-output adapter from the complete original animation_grind.rs.
// The caller installs these into its sole MotionGraphHost; failures retain out.
bool PublishAnimationState(const PhysicalPlayerInput&,const std::optional<FilteredStateOutput>&,
    float actual_animation_height,bool actual_mirrored,Vec3 actual_motion_effective_forward,
    AnimationStatePublication& out,std::string& error);
bool FilteredGrindNameText(AttributeName,std::string& out,std::string& error);
}
