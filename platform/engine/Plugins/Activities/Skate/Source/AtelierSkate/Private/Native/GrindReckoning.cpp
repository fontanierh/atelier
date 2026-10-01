// SPDX-License-Identifier: Apache-2.0
#include "GrindForces.h"
#include <cstring>
#include <cmath>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Vec4 Lanes(Vec3 v){return {v.x,v.y,v.z,0};}
Vec3 Xyz(Vec4 v){return {v[0],v[1],v[2]};}
Vec4 ExistingControl(const GroundNormalFilter& filter){Vec4 result;for(unsigned n=0;n<4;++n)std::memcpy(&result[n],&filter.words[n],4);return result;}
}
bool UpdateGrindReckoning(GroundOrientation& orientation,ReckoningFrames& frames,PhysicalBodySpinState& body,AirReckoningState& air,const GrindReckoningSettings& settings,Vec4 normal,Vec4 heading,float smoothing,bool reverse,float spin,std::string& error)
{
    const auto old_up=Lanes(orientation.up);orientation.dynamic_up=orientation.up;orientation.up_velocity={};
    frames.target_lean_angle=0;air.secondary_lean_angle=0;orientation.ground_blend=0;
    const auto ground=orientation.ground_filter.Update(settings.ground_normal_smoothing,normal);orientation.ground_normal=Xyz(ground);frames.heading=heading;
    Vec4 candidate;for(unsigned n=0;n<4;++n)candidate[n]=std::fma(old_up[n],smoothing,normal[n]*(1-smoothing));
    std::uint32_t word=0x358637bd;float threshold;std::memcpy(&threshold,&word,4);auto up=old_up;
    if(GrindForceLength(candidate)>threshold){const auto inverse=InverseLengthSquared(Dot3(candidate,candidate),2);for(unsigned n=0;n<4;++n)up[n]=candidate[n]*inverse;}
    orientation.up=Xyz(up);orientation.target=orientation.up;
    // The public filter entry copies its existing four control words back
    // unchanged, then executes the exact retained filter body.
    orientation.slow_filter.FilterRaw(ExistingControl(orientation.slow_filter),up);orientation.fast_filter.FilterRaw(ExistingControl(orientation.fast_filter),up);
    orientation.slow_filter.PublishCurrent(up);orientation.fast_filter.PublishCurrent(up);
    frames.CalculateTransform(up,ground);frames.CalculateTilt(reverse,settings.tilt_vs_rotation,settings.tilt_vs_slope);
    return UpdatePhysicalBodySpinGround(body,spin,error);
}
}
