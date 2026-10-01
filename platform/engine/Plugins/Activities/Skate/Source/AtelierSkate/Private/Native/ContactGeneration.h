// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "ContactRetention.h"
#include "ConstraintSolver.h"
namespace atelier::skate
{
struct ContactInput
{
    Vec3 position_on_a{},position_on_b{},normal{};
    float restitution=0,static_friction=0,dynamic_friction=0;
    std::uint32_t tag=0;
};
struct ContactBodyState
{
    std::uint32_t contact_body_id=0;
    Vec3 center_of_mass{};
    std::uint32_t reaction_id=0;
    Vec3 inverse_inertia_full{};
    float inverse_mass=0;
    Vec3 inverse_inertia_split{};
    std::uint32_t state=0;
    Vec3 force_acceleration{};
    float kinetic_energy=0;
    Vec3 torque_acceleration{};
    std::uint32_t cool_down=0;
    Vec3 linear_velocity{},angular_velocity{};
};
ContactRecord GenerateContact(ContactInput input,ContactBodyState body_a,ContactBodyState body_b);
// Positive finite timestep is the original builder contract. Body forces must
// include this tick's queued forces before generating the copied workspaces.
ContactConstraint BuildContactJacobian(ContactRecord contact,float time_step);
ContactConstraint BuildContactJacobian(ContactInput input,ContactBodyState body_a,ContactBodyState body_b,float time_step);
}
