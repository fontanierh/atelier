// SPDX-License-Identifier: Apache-2.0
#include "BipedAirState.h"
#include "BipedAirMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace biped_air_math;
float BipedAirProjectedHeight(Vec4 a,Vec4 b,Vec4 reference,Vec4 up)
{const float first=HeightDot(up,HeightSub(a,reference)),second=HeightDot(up,HeightSub(b,reference));return HeightSelect(first-second,second,first);}
void BipedAirState::CorrectHeight(BipedAirHeightInput i)
{
    const float height=BipedAirProjectedHeight(i.bone15,i.bone19,result.position_272,i.up_544);
    const float limit=std::abs(HeightDot(i.up_544,i.velocity_608)*offboard_air_math::Step())+.05f;
    const float delta=(height+.79f)-height_432,lower=HeightSelect(-limit-delta,-limit,delta);
    height_432+=HeightSelect(limit-lower,lower,limit);body_target_416=HeightMadd(i.up_544,height_432,result.position_272);
    const auto predicted=HeightMadd(result.velocity_288,offboard_air_math::Step(),i.bone1),lowered=HeightMadd(i.up_544,-.4f,predicted);
    body_offset_436=HeightDot(HeightSub(lowered,body_target_416),i.up_544);
}
}
