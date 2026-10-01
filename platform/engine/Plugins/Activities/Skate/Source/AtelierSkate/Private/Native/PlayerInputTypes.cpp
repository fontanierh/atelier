// SPDX-License-Identifier: Apache-2.0
#include "PlayerInputTypes.h"
#include "SkeletonPhysicalRecord.h"
#include "WipeoutOrientation.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float FloatWord(std::uint32_t w) {float f;std::memcpy(&f,&w,4);return f;}
std::uint32_t FloatBits(float f) {std::uint32_t w;std::memcpy(&w,&f,4);return w;}
}
void SkeletonOutputFields::PublishDeckAngles(Vec4 forward,bool flipped)
{
    if (flipped) for (auto& v:forward) v=-v;
    const float x=forward[0],z=forward[2],reciprocal=ReciprocalEstimate(z);
    const float refined=std::fma(reciprocal,std::fma(-reciprocal,z,1.0f),reciprocal);
    const float basic=Atan(std::fma(x,refined,0.0f));
    const auto sign=FloatBits(x)&0x80000000;
    const float pi=FloatWord(0x40490fdb|sign),half_pi=FloatWord(0x3fc90fdb|sign);
    const float angle=0.0f>z ? pi+basic : basic;
    deck_yaw_536=z==0.0f ? half_pi : angle;
    deck_pitch_540=Dot3(forward,Vec4{0,1,0,0});
}
void SkeletonOutputFields::PublishTwist(const SkeletonPhysicalRecord& record,Vec4 forward,Vec4 up)
{
    Vec4 across;for (std::size_t i=0;i<4;++i) across[i]=record.pose[10][3][i]-record.pose[6][3][i];
    const float squared=Dot3(across,across),inverse=InverseLengthSquared(squared,2);
    const float length=squared==0.0f ? 0.0f : squared*inverse;
    Vec4 direction{};if (length>0.0f) for (std::size_t i=0;i<4;++i) direction[i]=across[i]*inverse;
    const float angle=WipeoutProjectedAngle(forward,direction,up);
    const float turns=angle*FloatWord(0x3e22f983),fraction=turns-std::floor(turns);
    twist_504=(fraction-(fraction>0.5f ? 1.0f : 0.0f))*FloatWord(0x40c90fdb);
}
void GrindOutputFields::ResetNames(std::optional<AttributeName> grind,std::optional<AttributeName> surface)
{animation_name_156=grind;scoring_name_176=grind;surface_name_196=surface;}
}
