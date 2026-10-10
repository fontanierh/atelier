#pragma once
#include "AirState.h"
#include <memory>
namespace atelier::skate
{
// The source generic contract may observe every setter and repeated Fill.
// The active host's prepared launch record is a distinct binding in Settings.
class PhysicsAirLaunchInfo
{
public:
    virtual ~PhysicsAirLaunchInfo() = default;
    virtual void SetStartVelocity(Vec4)=0;
    virtual Vec4 CentreOfMassAnimationPosition() const=0;
    virtual void SetTrajectoryStartPositionOverride(Vec4)=0;
    virtual void SetBoardPositionOverride(Vec4)=0;
    virtual std::array<float,2> ConeAngles() const=0;
    virtual void SetConeAngles(std::array<float,2>)=0;
    virtual void SetPlayerJumped(bool)=0;
    virtual void SetUseTrajectoryStartPositionOverride(bool)=0;
    virtual void SetTrajectoryCount(std::uint16_t)=0;
};
// All effects require real bindings. Failure stops immediately, preserving
// mutations already performed; no neutral/no-op implementation is supplied.
class PhysicsAirRuntime : public PhysicsAirMath
{
public:
    virtual bool SetAirCollisionUpdateEnabled(bool,std::string&)=0;
    virtual bool SetSkeletonCollisionState(std::uint32_t,std::string&)=0;
    virtual bool SetSkeletonInverseKinematicsEnabled(bool,std::string&)=0;
    virtual bool EnableBoardAngularDriveOnly(std::string&)=0;
    virtual bool SetFootplantFlag240(bool,std::string&)=0;
    virtual bool ResetFootplants(std::string&)=0;
    virtual float BoardTransformHeight()=0;
    virtual bool RequestSkeletonHeadingUpdate(std::string&)=0;
    virtual bool UpdateAirCollision(std::string&)=0;
    virtual bool TrajectoryQueryJustStarted() const=0;
    virtual bool ConstructTrajectoryLaunchInfo(std::unique_ptr<PhysicsAirLaunchInfo>&,std::string&)=0;
    virtual bool FillSkeletonLaunchInfo(PhysicsAirLaunchInfo&,std::string&)=0;
    virtual bool LaunchTrajectory(const PhysicsAirLaunchInfo&,std::string&)=0;
    virtual bool UpdateTrajectorySelector(std::string&)=0;
    virtual std::optional<Vec4> SelectorLandingNormal() const=0;
    virtual bool SelectorCentreOfMassTrajectoryReady() const=0;
    virtual float AngleBetweenVectors(Vec4,Vec4)=0;
    virtual bool UpdateReckoningAirStates(Vec4,float,float,float,PhysicsAirReckoningFields&,std::string&)=0;
    virtual bool UpdateKnownAirSkeleton(Vec4,std::string&)=0;
    virtual bool UpdateAnimatedSkateboardSkeleton(bool,std::string&)=0;
    virtual bool UpdateBoardSteeringTilt(float,std::string&)=0;
    virtual bool CalculateAirCollisionForce(Vec4,AirBoardForce&,bool& created,std::string&)=0;
    virtual bool EnqueueBoardForce(std::uint32_t,AirBoardForce,std::string&)=0;
    virtual bool SetBoardVelocity(Vec4,std::string&)=0;
    virtual bool EnableSkateboardErrorOnSkeleton(std::string&)=0;
    virtual Vec4 BoardBodyVelocity()=0;
    virtual bool CheckForAirWipeout(bool,std::string&)=0;
};
}
