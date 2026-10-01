// SPDX-License-Identifier: Apache-2.0
#include "TruckDriveFrames.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
AffineTransform RotateTruck(AffineTransform base,float angle)
{
    const auto [sin,cos]=SinCos(angle);const std::array<std::array<float,3>,3> rotation={{{1,0,0},{0,cos,sin},{0,-sin,cos}}};
    Basis3 result;
    for (unsigned i=0;i<3;++i)
        for (unsigned lane=0;lane<3;++lane)
        {
            const auto& column=rotation[i];const float first=column[0]*base.basis.columns[0][lane];
            const float second=std::fma(column[1],base.basis.columns[1][lane],first);
            result.columns[i][lane]=std::fma(column[2],base.basis.columns[2][lane],second);
        }
    return {result,base.translation};
}
}
std::array<AffineTransform,2> SteeringTruckTransforms(std::array<AffineTransform,2> base,std::array<float,2> targets)
{return {RotateTruck(base[0],-targets[0]),RotateTruck(base[1],targets[1])};}
std::array<DriveFrames,2> SteeringDriveFrames(std::array<AffineTransform,2> base,std::array<float,2> targets)
{
    const auto trucks=SteeringTruckTransforms(base,targets);
    return {SetDriveFrames2(AffineTransform{},trucks[1]),SetDriveFrames2(AffineTransform{},trucks[0])};
}
}
