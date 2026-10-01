// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "BipedGroundState.h"
#include "WipeoutRuntime.h"
namespace atelier::skate
{
struct BipedGroundCollisionSettings
{
    float vehicle_scalar=0,vehicle_contact=0,maximum_displacement=0,maximum_arm_contact=0,
        maximum_body_contact=0,minimum_speed=0,maximum_squash=0,special_scalar=0;
    bool Load(const SettingsDatabase&,std::string& error);
};
struct BipedGroundCollisionInput
{const WipeoutFrame& shared;Vec4 skeleton_velocity_16336;bool contact_flag_4072;float contact_force_4056;};
struct BipedGroundPostInput
{
    BipedGroundCollisionInput collision;std::uint32_t processed_flags_2484;Vec4 processed_velocity_608;
    Vec4 skeleton_displacement_16288,skeleton_displacement_16304;std::uint32_t ground_kind_356;
};
void CheckBipedGroundCollision(WipeoutRequests&,const BipedGroundCollisionSettings&,const BipedGroundCollisionInput&);
void PostBipedGround(BipedGroundState&,WipeoutRequests&,const BipedGroundCollisionSettings&,const BipedGroundPostInput&);
struct BipedGroundPublicationInput
{
    std::array<bool,3> ground_flags_752_to_754;std::uint32_t contact_flags_368;
    Vec4 contact_position_192,query_position_816;std::uint32_t processed_flags_2476,ground_kind_356;
    float ground_scalar_360;Vec4 motion_vector_1040,motion_up_864;std::array<std::array<bool,3>,2> hand_flags;
};
struct BipedGroundPublication
{
    std::uint32_t physics_counter_36,physics_counter_40;bool physics_flag_86,offboard_flag_304;
    std::uint32_t offboard_kind_88;float offboard_scalar_112;bool offboard_flag_329,offboard_flag_330;
    float offboard_distance_116;bool offboard_flag_334;float offboard_scalar_32;bool offboard_flag_328;
    Vec4 animation_vector_144;bool animation_flag_164;std::array<bool,2> offboard_hand_flags_306_307;
};
struct BipedStatePublication{std::uint32_t word_36,word_40;bool flag_86;};
BipedGroundPublication PublishBipedGround(const BipedGroundState&,const BipedGroundPublicationInput&);
BipedStatePublication PublishBipedGroundFields(BipedGroundPublication,PhysicalPlayerInput&);
}
