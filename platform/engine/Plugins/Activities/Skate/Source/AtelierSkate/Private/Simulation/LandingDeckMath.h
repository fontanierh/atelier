#pragma once
#include "LandingDeck.h"
#include "GravityScale.h"
#include "OffboardAirMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::landing_deck_math
{
using namespace offboard_air_math;
inline Vec4 Gravity(){return {0,(Bits(0xc11ccccd)*GravityScale()),0,0};}
inline std::int32_t Frames(float time){return Integer(time*Bits(0x426fffff));}
inline float Root(float q){return q==0?0:q*Inverse(q);}
inline std::optional<float> GreatestPlaneTime(AirTrajectory t,Vec4 point,Vec4 normal)
{
    const auto a=Dot(normal,Mul(t.acceleration,Reciprocal(2))),b=Dot(normal,t.velocity),c=Dot(normal,t.position)-Dot(point,normal);
    const auto discriminant=b*b-(4*a)*c;if(discriminant<0)return std::nullopt;
    if(discriminant>0){const auto root=Root(discriminant),inverse=Reciprocal(2*a);return VectorMax(inverse*(-b+root),inverse*(-b-root));}
    const auto time=Reciprocal(2*a)*(-b);return time>0?std::optional<float>{time}:std::nullopt;
}
inline Vec4 FromRaw(RawVector v){Vec4 out{};for(std::size_t n=0;n<4;++n)out[n]=Bits(v[n]);return out;}
inline Vec4 Position(LandingDeckPlayerView v){return FromRaw(v.processed.vectors_544_560_592_608[2]);}
inline Vec4 Velocity(LandingDeckPlayerView v){return FromRaw(v.processed.vectors_544_560_592_608[3]);}
}
