// SPDX-License-Identifier: Apache-2.0
#include "AirMath.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace {float Word(std::uint32_t word) {float f;std::memcpy(&f,&word,4);return f;}}
float AirMath::Minimum(float left,float right) {return VectorMin(left,right);}
float AirMath::LengthSquared(Vec4 value) {return Dot3(value,value);}
float AirMath::Length(Vec4 value)
{
    const float square=Dot3(value,value),length=square*InverseLengthSquared(square,2);
    return square==0?0:length;
}
Vec4 AirMath::ClampLength(Vec4 value,float maximum)
{
    const float length=Length(value);
    if (!(length>=Word(0x37800000))) return value;
    const float bound=maximum-length>=-0.0f?length:maximum;
    const float inverse=RefinedReciprocal(length,2);
    for (auto& v:value) v=(v*bound)*inverse;
    return value;
}
float AirAngleBetweenVectors(Vec4 left,Vec4 right)
{
    const float a=Dot3(left,left),b=Dot3(right,right),epsilon=Word(0x38d1b717);
    if (!(a>epsilon&&b>epsilon)) return 0;
    const float inverse_a=InverseLengthSquared(a,1),inverse_b=InverseLengthSquared(b,1);
    for (auto& v:left) v*=inverse_a;
    for (auto& v:right) v*=inverse_b;
    return Acos(VectorMin(VectorMax(Dot3(left,right),-1),1));
}
Vec4 ClampAirJumpVelocity(Vec4 reference,Vec4 current)
{
    AirMath math;const float reference_speed=math.Length(reference),speed=math.Length(current);
    const float denominator=speed-1>=-0.0f?speed:1;
    const float scale=denominator>reference_speed?reference_speed/denominator:1;
    for (auto& v:current) v*=scale;
    return current;
}
}
