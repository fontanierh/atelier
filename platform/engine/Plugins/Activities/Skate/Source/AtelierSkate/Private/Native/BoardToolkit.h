// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "BoardRuntime.h"
namespace atelier::skate
{
struct BoardToolkit
{
    Mat4 deck,effective,inverse_effective;
    Vec4 side,up,forward,horizontal_forward,transverse_up,forward_velocity,travel_direction,filtered_normal;
    float absolute_speed,control_sign,total_mass;
    static BoardToolkit FromBoard(const BoardRuntime&,std::uint32_t flags,float speed,Vec4 normal,Vec4 retained_normal);
    static BoardToolkit Calculate(Mat4 deck,const std::vector<float>& inverse_masses,
        std::uint32_t flags,float speed,Vec4 normal,Vec4 retained_normal);
};
}
