#pragma once
#include "BoardRuntime.h"
namespace atelier::skate
{
struct BoardMotionOutput
{
    Vec3 angular_velocity,linear_velocity,ground_velocity;
    float speed,ground_speed,forward_speed;
    Basis3 effective_basis;
    static BoardMotionOutput FromBoard(const BoardRuntime&,Vec3 ground_normal,std::uint32_t processed_flags);
};
}
