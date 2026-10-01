// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "ConstraintFrames.h"
#include "ConstraintSolver.h"
#include "DriveFrames.h"

namespace atelier::skate
{
enum class DriveType : std::uint32_t { None=0, Soft=1, Hard=2 };
struct DriveParams
{
    float spring_or_max_velocity=0,damping=0,max_strength=0;
    DriveType type=DriveType::None;
};
struct DriveDynamics { DriveParams linear{},angular{}; };
struct TruckDriveSettings
{
    bool use_linear=false,use_hard_linear=true;
    float angular_displacement=10,angular_damping=0,angular_strength=11;
};
DriveDynamics TruckDriveDynamics(TruckDriveSettings settings);
DriveDynamics WheelDriveDynamics(bool use_hard_drives);

struct DriveBodyState
{
    std::size_t reaction_index=0;
    std::uint32_t state=0;
    Quat orientation{};
    Basis3 basis{};
    Vec3 center_of_mass{},linear_velocity{},angular_velocity{},force_acceleration{},torque_acceleration{};
    float inverse_mass=0;
    PackedWorldInverseInertia world_inverse_inertia{};
};
struct DriveRows
{
    DriveBodyState frame_a_body{},frame_b_body{};
    Vec3 arm_a{},arm_b{};
    std::array<Vec3,3> linear_axes{},angular_axes{};
    std::array<float,3> linear_inverse_effective_mass{},angular_inverse_effective_mass{};
    float linear_softness=0,angular_softness=0;
    std::array<float,3> linear_target_impulse{},angular_target_impulse{};
    std::array<float,3> linear_maximum_impulse{},angular_maximum_impulse{};
    std::array<float,3> accumulated_linear_impulse{},accumulated_angular_impulse{};
};
// Frame B minus frame A; positive impulses apply to frame A. The caller supplies
// the internal frame/body order, which is reversed from AddDrive's arguments.
DriveRows BuildDriveRows(DriveBodyState a,DriveBodyState b,DriveFrames frames,
    DriveDynamics dynamics,float time_step);
DriveConstraint PackDrive(const DriveRows& rows);
}
