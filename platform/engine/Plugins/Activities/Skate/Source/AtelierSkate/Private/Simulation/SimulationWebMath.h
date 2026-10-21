#pragma once

#include <cmath>
#include <cstdint>
#include <cstring>

// Browser libm's atan2f has different rounding from the native simulation.
// This is an original implementation of the mathematical approximation and
// quadrant policy published in Apple OSS Libm, Source/Intel/atan2f.s, revision
// 17a5f9daa3f5679f7536b26f133b40cc078753c3. No vendor assembly is included.
// Keep contraction disabled, as for the rest of the simulation.
namespace atelier::skate::web
{
inline std::uint32_t FloatBits(float value)
{
    std::uint32_t bits;
    std::memcpy(&bits,&value,sizeof(bits));
    return bits;
}

inline float FloatValue(std::uint32_t bits)
{
    float value;
    std::memcpy(&value,&bits,sizeof(value));
    return value;
}

inline double Promote(float value)
{
    const auto bits=FloatBits(value);
    if ((bits&0x7f800000u)==0) value=FloatValue(bits&0x80000000u);
    return static_cast<double>(value);
}

inline float Demote(double value)
{
    // Native FTZ observes tininess before binary32 rounding. A value just below
    // the smallest normal must not round back up to that normal in Wasm.
    if (std::fabs(value)<0x1p-126)
        return std::copysign(0.0f,static_cast<float>(value));
    return static_cast<float>(value);
}

inline float Atan2(float vertical,float horizontal)
{
    if (std::isnan(horizontal)||std::isnan(vertical)) return horizontal+vertical;
    const double x=Promote(horizontal),y=Promote(vertical);
    const bool negative_x=std::signbit(horizontal),negative_y=std::signbit(vertical);
    constexpr double pi=3.141592653589793238462643;
    const float lower_pi=FloatValue(0x40490fdau);
    // Preserve the native zero fast path's original vertical bits, including a
    // subnormal argument: FTZ changes arithmetic, not an unmodified return.
    if (x==0.0&&y==0.0)
        return negative_x ? std::copysign(lower_pi,vertical) : vertical;
    const double ax=std::fabs(x),ay=std::fabs(y);
    if (ax==ay)
        return Demote(std::copysign(negative_x ? 3.0*pi/4.0 : pi/4.0,y));

    double reduced,offset;
    if (ax>ay)
    {
        reduced=y/x;
        if (negative_x)
        {
            if (std::fabs(reduced)<=0x1p-22) return std::copysign(lower_pi,vertical);
            offset=std::copysign(pi,y);
        }
        else offset=-0.0;
    }
    else
    {
        reduced=-x/y;
        offset=negative_y ? -pi/2.0 : pi/2.0;
    }
    const double square=reduced*reduced;
    const double a0=(square+2.2971562298314633761676433)*square+2.4449692297316409651126041;
    const double a1=(square+0.0207432003007420961489920)*square+3.7888879287802702842997915;
    const double b0=(square-2.9466967515109826289085300)*square+5.4728447324456990092824269;
    const double b1=(square-4.9721072376211623038916292)*square+6.7197076223592378022736307;
    return Demote(((a0*b0)*reduced)*((a1*b1)*0.0029352921857004596570518)+offset);
}
}
