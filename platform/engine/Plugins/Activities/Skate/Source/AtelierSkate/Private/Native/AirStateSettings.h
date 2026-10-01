// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AirStateRuntime.h"
#include "Settings.h"
namespace atelier::skate
{
struct AirStateSettings
{
    PhysicsAirSettings state;
    float steering_blend;
    std::array<float,5> grind_lock_distance;
    bool Load(const SettingsDatabase&,std::string& error);
};
inline constexpr Mat4 AirLaunchIdentity{{Vec4{1,0,0,0},Vec4{0,1,0,0},Vec4{0,0,1,0},Vec4{0,0,0,0}}};
// Original trajectory LaunchInfo constructor. Physical observations are
// supplied by BindAirLaunchInfo before the record can be submitted.
struct AirLaunchInfo : PhysicsAirLaunchInfo
{
    Mat4 reckoning_transform=AirLaunchIdentity,reckoning_inverse=AirLaunchIdentity;
    Vec4 start_velocity{},com_velocity{},skeleton_vector_160{},skeleton_vector_176{};
    Vec4 board_position{},animation_com_position{},start_position_override{},board_position_override{};
    float cone_angle_x=0,cone_angle_z=0,timestep=0;
    bool player_jumped=false,use_position_override=false;
    std::uint16_t trajectory_count=0;
    void SetStartVelocity(Vec4 value) override {start_velocity=value;}
    Vec4 CentreOfMassAnimationPosition() const override {return animation_com_position;}
    void SetTrajectoryStartPositionOverride(Vec4 value) override {start_position_override=value;}
    void SetBoardPositionOverride(Vec4 value) override {board_position_override=value;}
    std::array<float,2> ConeAngles() const override {return {cone_angle_x,cone_angle_z};}
    void SetConeAngles(std::array<float,2> value) override {cone_angle_x=value[0];cone_angle_z=value[1];}
    void SetPlayerJumped(bool value) override {player_jumped=value;}
    void SetUseTrajectoryStartPositionOverride(bool value) override {use_position_override=value;}
    void SetTrajectoryCount(std::uint16_t value) override {trajectory_count=value;}
};
struct AirSelectorInput
{
    Vec4 gravity,ground_normal,contact_position,heading_direction,reference_up;
    float board_vertical_velocity,directional_input;
    std::uint32_t previous_physics_state,flags_2472,flags_2476,offboard_flags_1776;
    float grind_lock_distance;
};
// Required views of the completed owners consumed by air_phase/input.rs.
// No partial record receives a neutral replacement. Optional toolkit retains
// the source's explicit missing-toolkit error.
struct AirStateBindingInput
{
    std::array<std::array<std::uint32_t,4>,2> vectors_400_416;
    std::array<std::array<std::uint32_t,4>,5> vectors_464_480_496_512_528;
    std::array<std::array<std::uint32_t,4>,4> vectors_544_560_592_608;
    std::array<std::uint32_t,4> prepared_jump_704,jump_reference;
    std::uint32_t flags_2468,flags_2472,flags_2476,state_2504,category_2516,state_variant_index_2528,jump_fix_frames,external_physics_flags;
    float timestep_2604,transition_2636,gravity_2648,state_timer_2664,body_spin;
    Vec4 world_gravity;
    Mat4 reckoning_system,reckoning_inverse;
    Vec4 skeleton_local_centre_of_mass,skeleton_local_board_position;
    std::optional<Mat4> toolkit_deck;
    float trajectory_cone_x,trajectory_cone_z;
};
PhysicsAirFrame BindPhysicsAirFrame(const AirStateBindingInput&);
bool BindAirSelectorInput(const AirStateBindingInput&,const AirStateSettings&,AirSelectorInput&,std::string& error);
bool BindAirLaunchInfo(const AirStateBindingInput&,AirLaunchInfo&,std::string& error);
// Fixed stock COM acceleration; distinct from world rigid-body gravity.
Vec4 PhysicsAirHostComAcceleration();
}
