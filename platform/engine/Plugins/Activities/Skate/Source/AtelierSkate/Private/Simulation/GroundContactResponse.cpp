#include "GroundContactResponse.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
GroundContactResponse CalculateWallRideResponse(const WallRideSettings& settings,
    WallRidePhysical physical, GroundContactFrame frame, Vec4 previous_velocity)
{
    GroundContactResponse response; response.vector_2688 = previous_velocity;
    if (!frame.flag_8084 || !(std::abs(physical.board_normal[1]) < .5f)
        || !(Dot3(physical.up, physical.board_normal) > .71f)) return response;
    response.active_2731 = true;
    const float acceleration = settings.anti_gravity_vs_time.Evaluate(frame.scalar_2752);
    response.tag_16_force.force_world = {0, -((acceleration * physical.board_mass) * physical.gravity), 0};
    const float time = frame.scalar_2756;
    const bool consider = (time < 0.0f && time > -1.0f) || (physical.speed < 3.0f && time > .1f);
    if (!(consider || (frame.scalar_2752 > .01f && physical.contact_count > 0)
        || frame.scalar_2752 > settings.foot_force_time)) return response;
    // This dot is read before the aliased temporary is overwritten.
    const float floor_wall = Dot3(frame.vector_8064, physical.board_normal);
    const float height = std::abs(frame.vector_8048[1] - frame.vector_8032[1]);
    const float predicted_height = std::fma(physical.velocity[1], settings.velocity_time_to_consider, height);
    if (!(floor_wall < settings.max_dot_floor_wall
        && (consider || predicted_height < settings.auto_jump_height || time > settings.max_time))) return response;
    response.animated_board_2708 = true;
    const float into_normal = Dot3(physical.board_normal, physical.velocity);
    Vec4 tangent;
    for (std::size_t i = 0; i < 4; ++i) tangent[i] = physical.velocity[i] - physical.board_normal[i] * into_normal;
    if (tangent[1] < 0.0f && tangent[1] > -6.0f) tangent[1] *= settings.auto_jump_y_down_scalar;
    for (std::size_t i = 0; i < 4; ++i)
        response.vector_2688[i] = std::fma(physical.board_normal[i], settings.auto_jump_force, tangent[i]);
    return response;
}
}
