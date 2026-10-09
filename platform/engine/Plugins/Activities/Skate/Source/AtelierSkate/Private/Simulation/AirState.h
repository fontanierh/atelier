#pragma once
#include "AirMath.h"
#include <optional>
#include <string>
namespace atelier::skate
{
struct AirTrajectory
{
    Vec4 position{},velocity{},acceleration{};
    float scalar_48=-1;
};
struct PhysicsAirState
{
    AirTrajectory centre_of_mass_trajectory;
    Vec4 landing_normal{0,1,0,0};
    float time_in_state=0,start_y=0,max_y=0;
    bool reached_apex=false,use_centre_of_mass_velocity=false,selector_latch_174=false;
    std::int32_t trajectory_query_countdown=0;
};
struct PhysicsAirFrame
{
    Vec4 current_velocity_400;
    float ground_position_y_500;
    Vec4 trajectory_position_592,trajectory_velocity_608,jump_velocity_848;
    std::uint32_t flags_2468;
    std::int32_t previous_physics_state_2504,previous_physics_category_2516,frames_since_jump_correction_2576;
    float delta_time_2604,body_spin_input_2640,gravity_y_2648,state_timer_2664;
};
struct PhysicsAirSettings
{
    PointGraph<8> body_spin_over_time_320;
    float landing_normal_blend_388,body_spin_scale_428,landing_normal_angle_limit_444;
};
struct PhysicsAirReckoningFields
{
    Vec4 current_landing_normal_1152,collision_reference_normal_1216;
    float body_spin_angle_1568,body_spin_speed_1572;
};
struct AirBoardForce {Vec4 force_world{},point_board_local{};};
struct PhysicsAirOutput
{
    bool is_at_apex;
    float jump_height;
    Vec4 landing_normal;
    std::optional<float> scalar_184_write;
};
class PhysicsAirRuntime;
Vec4 CalculateAirVelocityFromJump(const PhysicsAirFrame&,std::int32_t frames,PhysicsAirMath&);
float WrapAirSignedAngle(float angle);
void IntegrateAirTrajectoryFixedStep(AirTrajectory&);
bool EnterPhysicsAir(PhysicsAirState&,const PhysicsAirFrame&,Vec4 world_acceleration,PhysicsAirRuntime&,std::string& error);
void ExitPhysicsAir(PhysicsAirState&,PhysicsAirReckoningFields&);
PhysicsAirOutput FillPhysicsAirOutput(const PhysicsAirState&);
bool UpdatePhysicsAir(PhysicsAirState&,const PhysicsAirFrame&,const PhysicsAirSettings&,PhysicsAirReckoningFields&,Vec4 world_acceleration,PhysicsAirRuntime&,std::string& error);
bool UpdatePhysicsAirBoard(const PhysicsAirState&,const PhysicsAirFrame&,const PhysicsAirReckoningFields&,PhysicsAirRuntime&,std::string& error);
bool UpdatePhysicsAirPost(PhysicsAirState&,PhysicsAirRuntime&,std::string& error);
}
