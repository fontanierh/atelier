#pragma once
#include "ConstraintFrames.h"

namespace atelier::skate
{
struct JointBodyInput
{
    std::uint32_t reaction_address=0,state=0;
    Quat orientation{};
    Vec3 center_of_mass{};
    Basis3 basis{};
    Vec3 linear_velocity{},angular_velocity{},force_acceleration{},torque_acceleration{};
    float inverse_mass=0;
    PackedWorldInverseInertia world_inverse_inertia{};
};
struct JointBuildInput
{
    std::array<std::uint32_t,16> parameters{};
    std::array<std::uint32_t,20> frames{};
    JointBodyInput body_a{},body_b{};
    float time_step=0;
    std::uint32_t joint_address=0;
};
// Opaque guest identifiers are retained in packed lanes; actual reaction
// indices belong to the caller's JointConstraint and are never dereferenced.
std::array<std::uint32_t,96> BuildJoint(const JointBuildInput& input);
}
