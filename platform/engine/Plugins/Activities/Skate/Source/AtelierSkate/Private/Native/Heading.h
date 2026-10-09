#pragma once
#include "NativeMath.h"
namespace atelier::skate
{
struct HeadingSettings
{
    float manual_wrong_wheel_scalar,manual_damping,speed_max,heading_strength,turn_strength;
    PointGraph<8> angular_response,manual_response,inclination_response,speed_response;
    Vec4 normal_threshold;
};
struct HeadingInput
{
    float balance,manual_turn;
    std::uint32_t flags_2472;
    float timestep,signed_speed,manual_curve_input,turn_2712,scalar_2740;
    Vec4 velocity,normal,angular_velocity;
    Mat4 transform;
};
// previous is the actual board+284 history; its owner controls initialization.
Vec4 CalculateHeading(const HeadingSettings&,const HeadingInput&,float& previous);
}
