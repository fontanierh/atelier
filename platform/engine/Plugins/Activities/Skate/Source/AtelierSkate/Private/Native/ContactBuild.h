// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "NativeMath.h"
#include <functional>

namespace atelier::skate
{
struct ContactPreparation
{
    std::array<Vec3,2> arms{},point_acceleration{};
    std::array<Vec3,3> axes{};
    std::array<bool,2> active{};
    std::array<float,2> inverse_mass{};
    std::array<Vec4,3> angular_response_a{},angular_response_b{};
    std::array<float,3> effective_mass{},separation_projection{},restitution_projection{},predicted_separation_projection{};
    std::array<std::uint32_t,2> reaction_ids{},body_ids{};
    std::uint32_t static_friction_bits=0,dynamic_friction_bits=0,contact_tag=0,combined_state_bit_8=0;
};
using ContactMassResponse = std::function<bool(const std::array<float,3>&,std::array<float,3>&)>;

ContactPreparation PrepareContact(const std::array<std::uint32_t,64>& record,float time_step);
// Preparation and reciprocal response complete before the compiled record is
// published. A failing response leaves the entire original record untouched.
bool BuildContactWithResponse(std::array<std::uint32_t,64>& record,float time_step,const ContactMassResponse& response);
void BuildContact(std::array<std::uint32_t,64>& record,float time_step);
}
