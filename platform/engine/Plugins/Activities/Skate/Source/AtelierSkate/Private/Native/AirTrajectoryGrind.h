// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AirTrajectoryQuery.h"
#include "PlayerGrindInputWorld.h"
namespace atelier::skate
{
struct AirTrajectoryPrediction
{
    AirTrajectoryQueryResult result;
    AirTrajectoryQueryRequest request;
    Vec4 CollisionPosition() const;
    Vec4 CollisionVelocity() const;
};
struct AirTrajectoryGrindCandidate
{
    Vec4 point,trajectory_point,direction,approach;
    float distance,time,angle;
    std::int32_t frame;
    std::size_t primitive;
};
struct AirTrajectoryGrindSurfaceEvidence {std::uint32_t kind;Vec4 side;};
struct AirTrajectoryGrindAssistLimits
{
    float lock_distance,max_speed_squared_ledge,max_speed_squared_rail,max_downward_speed;
    std::array<float,4> ledge_scalars;
    float tip_scalar,maximum_adjust_angle;
    std::array<float,2> deck_dimensions;
};
struct AirTrajectoryGrindTarget
{
    PlayerGrindPrimitive edge;
    std::size_t provider_index;
    std::uint32_t primitive_flags;
    GrindAirLandingOrientation orientation;
    Vec4 point,vertical_normal;
    GrindAirTarget AirTarget() const;
};
struct AirTrajectoryGrindEvaluation
{
    std::optional<AirTrajectoryGrindTarget> target;
    float score,distance;
    std::optional<float> effective_lock_distance;
    float penalty_domain;
    float PenaltyInput() const;
};
std::vector<std::size_t> AirTrajectoryBoxFilter(const std::vector<std::size_t>&,
    const std::vector<PlayerGrindPrimitive>&,Vec4 takeoff);
std::optional<float> AirTrajectoryDescendingPlaneTime(AirTrajectory,Vec4 point,Vec4 normal);
std::optional<AirTrajectoryGrindCandidate> ConsiderAirTrajectoryGrindPrimitive(
    AirTrajectoryPrediction,PlayerGrindPrimitive,std::size_t primitive,float padding);
std::optional<AirTrajectoryGrindCandidate> TakeBestAirTrajectoryGrind(
    std::vector<AirTrajectoryGrindCandidate>&,float difficulty_distance,const PointGraph<8>& height_penalty);
std::optional<Vec4> AdmitAirTrajectoryGrindDisplacement(AirTrajectoryPrediction,
    AirTrajectoryGrindCandidate,PlayerGrindPrimitive,Vec4 reference_velocity,Vec4 processed_592,
    AirTrajectoryGrindSurfaceEvidence,const AirTrajectoryGrindAssistLimits&,std::optional<float>& effective_lock_distance);
Vec4 AirTrajectoryGrindLandingNormal(Vec4 direction,Vec4 velocity,Vec4 support,
    float velocity_scalar,float maximum_angle_degrees);
void ApplyAirTrajectoryGrindTarget(AirTrajectoryPrediction&,AirTrajectoryGrindCandidate,
    Vec4 correction,Vec4 support_normal,Vec4 reference_velocity,float maximum_adjust,
    float landing_velocity_scalar,float landing_max_angle);
}
