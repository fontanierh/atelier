// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GraphMotionName.h"
#include "MotionAnimation.h"
#include "MotionFrame.h"
namespace atelier::skate
{
struct MotionGraphRidingConditionInputs
{
    Vec4 com_velocity,skeleton_x,skeleton_z;
    float skate_up_y,surface_up_y;
};
struct MotionPhysicalConditionContext
{
    const MotionAnimation& animation;
    const MotionGraphPhysicalPublication& physical;
    const std::optional<MotionGraphRidingConditionInputs>& riding;
};
struct GraphMotionPhysicalCondition
{
    enum class Kind
    {
        Unsupported,RetrievingBoard,InBipedAir,HippyHurdling,WantsRunout,PhysicsWiping,BodyFlipping,WantsWipeout,
        Bumped,GrabbingObject,TricksOnStairs,EnteringSkitch,Skitching,FootPlanting,PrepareFootplant,
        NewHandplantPosition,PlayHandplant,MovingObject,HandPlanting,TimeToLand,OffboardTimeToLand,
        OffboardTrajectoryTime,LocoState,GroundSlopeType,RidingGoofy,BipedGroundThin,HoldingBoard,
        StandingOnMovingObject,CanLandOnBoard,DistanceToEdge,DeckFree,BipedCommitted,EnoughDistanceToObstacle,
        CanBipedLand,CrouchedEnough,TrucksOrDeckContact,ManualExit,ApexReached,ComVelocity,SkateSlope,SurfaceSlope,DisableDismount
    };
    Kind kind=Kind::Unsupported;
    NumericCondition numeric;
    std::uint32_t value=0,direction=0;
    std::string database,animation;
    bool Evaluate(const MotionPhysicalConditionContext&,bool& result,std::string& error) const;
};
bool ParseGraphMotionPhysicalCondition(const GraphAttributes&,GraphMotionPhysicalCondition&,bool& recognized,std::string& error);
}
