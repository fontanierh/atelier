// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "BodyMass.h"
#include "RigidBody.h"

namespace atelier::skate
{
struct AggregateMassProperties
{
    float volume=0;
    LocalMassFrame local_mass_frame{};
    Vec3 moments_per_unit_mass{};
};
struct MassMoments
{
    // Volume integrals of [x,y,z,1] outer products in column order.
    Mat4 columns{};
    static MassMoments FromPrimitive(PrimitiveMass primitive);
    void Transform(Basis3 basis,Vec3 translation);
    void Add(const MassMoments& child);
    // Mutates columns into the center-of-mass frame before diagonalization.
    AggregateMassProperties PrincipalProperties();
};
struct WheelMassSettings
{
    float radius,mass,mass_factor;
    static WheelMassSettings Stock();
};
struct TruckMassSettings
{
    float wheel_radius,wheel_x_distance,radius_scalar,half_height_scalar,mass,mass_factor;
    static TruckMassSettings Stock();
};
struct PartMassInput { MassShape shape;float requested_mass; };
struct ForwardMassProperties { PrimitiveMass primitive;float mass;Vec3 principal_moments; };
PartMassInput WheelMassInput(WheelMassSettings settings);
PartMassInput TruckMassInput(TruckMassSettings settings);
std::optional<ForwardMassProperties> ComputeForwardMassProperties(PartMassInput input);
std::optional<BodyMassProperties> ComputePrimitiveMassProperties(PartMassInput input,float maximum_angular_velocity,float angular_drag);
BodyMassProperties ComputeAggregateMassProperties(MassMoments moments,float requested_mass,float maximum_angular_velocity,float angular_drag);
BodyMassProperties WheelMassProperties(WheelMassSettings settings);
BodyMassProperties TruckMassProperties(TruckMassSettings settings);
}
