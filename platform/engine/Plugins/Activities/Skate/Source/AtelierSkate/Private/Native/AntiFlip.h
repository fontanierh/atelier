#pragma once
#include "NativeMath.h"
namespace atelier::skate
{
struct AntiFlipSettings {PointGraph<8> axis_96_response,axis_64_response;Vec4 normal_threshold;};
struct AntiFlipInput {std::uint32_t flags_2468;float balance;Vec4 axis_96,axis_64,projection_axis_544;};
Vec4 CalculateAntiFlip(const AntiFlipSettings&,const AntiFlipInput&);
}
