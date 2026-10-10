#pragma once
#include "SimulationMath.h"
#include <optional>
namespace atelier::skate
{
struct RidingCollisionResponseSettings
{
    float maximum_velocity_delta,force_y_offset,force_scalar,target_displacement_velocity;
    PointGraph<8> torque_vs_angle;
};
struct RidingCollisionPhysical
{
    std::uint32_t flags;
    Vec4 collision_displacement,velocity,forward,up,ground_normal;
    float time_step,mass;
};
struct RidingCollisionResponse
{
    bool applied;
    Vec4 force,point,angular_displacement,target_velocity;
};
// Absence means no publication. A present late false result still publishes
// its target velocity and angular correction, exactly as the source does.
std::optional<RidingCollisionResponse> CalculateRidingCollisionResponse(
    const RidingCollisionResponseSettings&,RidingCollisionPhysical);
}
