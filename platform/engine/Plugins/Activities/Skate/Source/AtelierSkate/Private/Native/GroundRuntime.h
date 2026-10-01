// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GroundSettings.h"
#include "GroundHangGeometry.h"
#include "RidingCollisionResponse.h"
#include "SkeletonAnimationRecord.h"
#include "BoardRuntime.h"
#include "WipeoutRequests.h"
namespace atelier::skate
{
struct GroundControllers
{
    SpeedWobbleState& speed_wobble;
    TruckSteeringState& truck_steering;
    SpeedModelState& speed_model;
    ManualState& manual;
    float& heading_previous;
};
class GroundLaunchScheduler
{
public:
    virtual ~GroundLaunchScheduler()=default;
    virtual bool LaunchAndUpdate(const GroundLaunchInfo&,std::string&)=0;
};
struct GroundPhysicalFrame
{
    const SkeletonAnimationRecord& skeleton_record;
    WallRidePhysical wall_ride;
    RidingCollisionPhysical collision;
    HangGeometryInput hang_geometry;
    Vec4& processed_velocity;
    ContactMaterial& wheel_material;
    WipeoutRequests& wipeout;
    float time_step;
    const GroundLaunchPhysical* launch_physical;
    GroundLaunchScheduler& launch_and_update;
};
class GroundRuntime
{
public:
    Vec4 retained_board_normal{0,1,0,0};
    WallRideSettings wall_ride;
    RidingCollisionResponseSettings collision;
    float deck_center_to_truck,launch_cone_x,launch_cone_z;
    GroundContactResponse contact{};
    std::optional<GroundBoardCollisionResponse> collision_force;
    bool Load(const SettingsDatabase&,std::string&);
    void ResetBoardToolkit() {retained_board_normal={0,1,0,0};}
    GroundContactResponse ContactResponseWithPrevious(GroundContactFrame,WallRidePhysical,Vec4) const;
    std::optional<GroundBoardCollisionResponse> CalculateCollisionForce(RidingCollisionPhysical);
    void UpdateBodyAccumulator(BoardRuntime&);
    void ApplyAngularTarget(BoardRuntime&,Vec4);
    void ApplyAngularDisplacement(BoardRuntime&,Vec4);
    void SetAnimatedVelocity(BoardRuntime&,Vec4);
    Vec4 BuildHangForce(const BoardRuntime&,Vec4 edge_start,Vec4 edge_end) const;
    void ApplyHangForce(BoardRuntime&,Vec4);
    void PinToPosition(BoardRuntime&,float x,float z,float dt);
    std::optional<GroundBoardOutcome> UpdateBoard(BoardRuntime&,const WorldGeometry&,const GroundSettings&,
        PhysicsGroundState&,GroundControllers,GroundBoardInput,GroundPhysicalFrame,GroundBoardError&);
};
}
