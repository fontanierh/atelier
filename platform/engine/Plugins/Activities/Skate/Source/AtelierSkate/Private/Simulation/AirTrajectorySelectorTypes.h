#pragma once
#include "AirStateSettings.h"
#include "AirTrajectoryGrind.h"
namespace atelier::skate
{
struct AirTrajectorySelectorSettings
{
    float cone_x,cone_z,trajectory_max_time,trajectory_max_drop,trajectory_error_start,trajectory_error_end;
    float speed_factor_min,speed_factor_max;
    PointGraph<8> cone_angle_z_vs_speed;
    float cone_x_second_pass,cone_z_second_pass;
    PointGraph<8> landing_time_bonus,landing_com_scalar_vs_slope,landing_force_scalar,grind_penalty_vs_distance;
    float score_middle_bonus,score_landing_force,score_landing_direction,score_transition;
    float surface_unrideable_score,surface_dont_align_score,natural_air_off_verts_scalar;
    float minimum_valid_time,minimum_time_after_apex,minimum_normal_delta_second_pass,maximum_trajectory_adjust;
    float wall_ride_test_distance,wall_ride_minimum_height,wall_ride_angle_allow_landing,wall_ride_height_score;
    PointGraph<4> wall_ride_boost;
    float wall_ride_normal_dot_limit;
    PointGraph<8> displacement_vs_speed,displacement_vs_ground_normal;
    float trajectory_radius,trajectory_displacement;
    std::int32_t minimum_trajectory_frames;
    float vert_jump_align_factor,vert_jump_align_max_ground_normal_y,vert_jump_align_min_direction_y,vert_jump_align_max_angle;
};
struct AirTrajectoryCandidate
{
    AirTrajectoryPrediction prediction;
    Vec4 start_velocity,normal,collision_velocity,collision_position;
    float score,wall_score;
    bool wall_ride;
    std::optional<AirTrajectoryGrindTarget> grind;
};
struct AirTrajectorySelection
{
    std::size_t candidate_index;
    AirTrajectoryPrediction prediction;
    Vec4 start_velocity,landing_normal,collision_velocity,collision_position;
    AirTrajectory com_trajectory;
    std::uint32_t surface_category;
    bool wall_ride;
    std::optional<AirTrajectoryGrindTarget> grind;
};
// The host may create this evidence only after checking actual authored topology.
struct AirTrajectoryWorldWithoutGrindEdges {};
class AirTrajectorySelectionServices
{
public:
    virtual ~AirTrajectorySelectionServices()=default;
    virtual bool EvaluateGrind(AirTrajectoryPrediction&,bool middle,
        AirTrajectoryGrindEvaluation&,std::string& error)=0;
    virtual bool Line(Vec4 start,Vec4 end,float radius,
        std::optional<AirTrajectorySurfaceHit>&,std::string& error)=0;
};
}
