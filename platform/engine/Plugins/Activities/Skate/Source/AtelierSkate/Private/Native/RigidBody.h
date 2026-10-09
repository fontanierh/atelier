#pragma once
#include "NativeMath.h"
#include <array>
#include <cstdint>

namespace atelier::skate
{
struct SimulationStep
{
    float time_step, frequency;
    std::uint32_t cool_down;
    float minimum_energy;
    Vec3 gravity_acceleration;
    static SimulationStep Fixed60Hz(std::uint32_t cool_down,float minimum_energy,Vec3 gravity);
};
struct InertiaDynamics
{
    Vec3 inverse_tensor;
    float inverse_mass, spherical, maximum_linear_velocity, maximum_angular_velocity, linear_drag, angular_drag;
};
struct LocalMassFrame
{
    Basis3 basis{std::array<std::array<float,3>,3>{{{1,0,0},{0,1,0},{0,0,1}}}};
    Vec3 translation{};
};
struct BodyMassProperties { LocalMassFrame local_mass_frame; InertiaDynamics dynamics; };
struct ReactionCorrections
{
    Vec3 linear_displacement{},position_displacement{},angular_displacement{},orientation_displacement{};
};
struct BodyRates
{
    Quat orientation;
    Basis3 basis,world_inverse_inertia;
    Vec3 position,linear_velocity,angular_velocity,force_acceleration,torque_acceleration;
    float kinetic_energy;
    std::uint32_t cool_down;
};
struct BodyRateStep
{
    BodyRates state;
    Vec3 orientation_displacement;
    float linear_speed_squared,angular_speed_squared;
};
struct PackedWorldInverseInertia { Vec3 full,split; };
struct ForceAccumulator { Vec3 force_acceleration,torque_acceleration; std::uint32_t cool_down; };
struct DynamicUpdateResult
{
    std::array<float,3> orientation_displacement;
    float linear_speed_squared,angular_speed_squared;
};
// Keeps every opaque body lane and clears all sixteen reaction words, just as
// the original solver entry point does. Arithmetic remains binary32 throughout.
DynamicUpdateResult DynamicUpdatePacked(std::array<std::uint32_t,44>& body,
    const std::array<std::uint32_t,10>& inertia,SimulationStep simulation,
    std::array<std::uint32_t,16>& reactions);
BodyRateStep IntegrateBodyRates(BodyRates body,InertiaDynamics inertia,SimulationStep simulation,ReactionCorrections reactions);
Quat IntegrateOrientation(Quat orientation,Vec3 angular_displacement);
Basis3 BasisFromQuaternion(Quat orientation);
Basis3 WorldInverseInertia(Basis3 basis,Vec3 inverse_tensor);
PackedWorldInverseInertia PackWorldInverseInertia(Basis3 tensor);
Vec3 MultiplyPackedWorldInverseInertia(PackedWorldInverseInertia tensor,Vec3 vector);
ForceAccumulator AccumulatePointForce(ForceAccumulator accumulator,Vec3 force_world,Vec3 application_point_body,
    Basis3 deck_basis,float inverse_mass,Basis3 world_inverse_inertia);
}
