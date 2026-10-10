#pragma once
#include "SimulationMath.h"
namespace atelier::skate
{
struct SlideFrictionSettings
{
    PointGraph<16> angle_response;
    PointGraph<8> speed_response;
    PointGraph<16> time_response;
    float scalar_516,heading_time_limit,friction;
};
struct SlideFrictionInput {float heading_time;Vec4 normal,velocity,side_axis;float surface_speed,scalar_2764;};
std::array<float,8> CalculateSlideFriction(const SlideFrictionSettings&,const SlideFrictionInput&);
}
