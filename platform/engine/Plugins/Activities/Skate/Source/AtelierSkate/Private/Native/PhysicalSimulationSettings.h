// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AnimationPose.h"
#include "BoardPossessionSettings.h"
#include "SkeletonPhysicsSettings.h"
#include "WorldContactProducer.h"

namespace atelier::skate
{
struct GroundOrientationSettings
{
    Vec4 ground_normal_smoothing{},up_vector_smoothing_slow{},up_vector_smoothing_fast{};
    PointGraph<8> dynamic_up_vs_ground_y,ground_vector_blend,deck_angle_usage_vs_speed;
    PointGraph<8> up_vector_smoothing_vs_speed,up_vector_max_delta_vs_speed;
    float ground_blend_max_delta=0,up_vector_max_acceleration=0,anti_wobble_damping=0,extra_side_damping=0;
    std::int32_t minimum_wheels_for_ground_blend=0;
};
struct SpeedAndSlopeSettings
{
    PointGraph<8> turn_torque_vs_speed,turn_torque_vs_slope;
    float heading_adjust_max_speed=0;
    float Calculate(float ground_normal_y,float forward_speed) const;
};
struct PhysicalRidingSettings
{
    GroundOrientationSettings orientation;
    PointGraph<8> tilt_vs_rotation,tilt_vs_slope;
    SpeedAndSlopeSettings speed;
    float maximum_ground_angle=0;
    static std::optional<PhysicalRidingSettings> Load(const SettingsDatabase&,std::string& error);
};
// Native data and the actual animation hierarchy are the constructor inputs.
// Initial pose evaluation remains the AnimationPoseEvaluator owner's work.
struct PhysicalSimulationSettings
{
    BoardPhysicsSettings board;
    PhysicalRidingSettings riding;
    PhysicsSkeleton physical;
    std::vector<std::int32_t> hierarchy_parents;
    std::array<std::size_t,24> bone_indices{};
    std::array<Mat4,24> physics_frames{};
    SkeletonCollisionSettings collision;
    SkeletonFeedbackSettings feedback;
    BoardPossessionSettings possession;
    BoardPossessionLiveState possession_live;
    WorldContactSettings query{0.05f,0.5f,0.999f,0.01f,false};
    ContactRetentionSettings retention{UINT32_MAX,-1.0f,true};
    static std::optional<PhysicalSimulationSettings> Load(const SettingsDatabase&,const PhysicsSkeleton&,
        const AnimationRig&,std::string& error);
    AffineTransform Spawn(Vec3 wheel_ground_anchor) const;
};
}
