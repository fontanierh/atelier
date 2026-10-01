// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "NativeMath.h"
namespace atelier::skate
{
struct PlayerGrindControl
{
    float yaw=0,pitch=0;
    void Update(std::uint32_t kind,Vec4 board_forward,Vec4 normal,bool front,bool switched,bool hanging_back,
        float translation,float nudge,float up_down,float grab_min_height);
};
Vec4 PlayerGrindControlRotate(Vec4 axis,Vec4 value,float angle);
Mat4 PlayerGrindTruckFrame(Mat4 board,Vec4 normal,const PlayerGrindControl&,bool switched);
Mat4 PlayerGrindTipFrame(Mat4 board,Vec4 direction,Vec4 normal,Vec4 point,bool backslash);
}
