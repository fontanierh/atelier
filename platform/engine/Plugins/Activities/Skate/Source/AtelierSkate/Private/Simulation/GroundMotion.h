#pragma once
#include "ForceQueue.h"
#include "Manual.h"
#include <optional>
namespace atelier::skate
{
Vec3 GroundEntryAngularVelocity(Vec4 normal,Vec4 angular);
float GroundEntryTargetSpeed(Vec3 velocity,Vec4 normal,Vec4 forward);
QueuedPointForce GroundLandingOnDeckForce(Vec4 physical_velocity,Vec4 animation_velocity,
    Vec4 axis,float mass,float strength,float point_y);
std::optional<Vec3> GroundFutureDeckDisplacement(const BoardForceQueue&,float mass,float dt,
    Vec4 normal,bool pushing,bool manual_correction);
struct ManualGroundInput
{
    float balance;
    Vec4 ground_normal;
    std::uint32_t flags_2468,flags_2472;
};
class ManualGroundBodies
{
public:
    virtual ~ManualGroundBodies()=default;
    virtual Vec4 LinearVelocity(std::size_t part)=0;
    virtual void SetLinearVelocity(std::size_t part,Vec4)=0;
};
class ManualGroundProjection
{
public:
    virtual ~ManualGroundProjection()=default;
    virtual bool NormalSpeed(Vec4 normal,Vec4 velocity,float& output,std::string& error)=0;
};
bool RemoveManualVelocityIntoGround(ManualGroundInput,ManualGroundBodies&,ManualGroundProjection&,std::string& error);
bool EnterManualGround(ManualState&,std::uint32_t previous_category,float powerslide_exit_scale,
    ManualGroundInput,ManualGroundBodies&,ManualGroundProjection&,std::string& error);
}
