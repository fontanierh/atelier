#pragma once
#include "SimulationMath.h"
#include "Settings.h"
#include <string>
namespace atelier::skate
{
struct GroundForceSettings
{
    float range_1220,speed_scale_1224,scale_1228;
    Vec4 normal_threshold;
};
struct GroundForceInput
{
    float argument_1,application_z,argument_3,argument_4,balance,surface_speed;
    Vec4 axis_384,velocity_400,axis_544;
};
// Source NormalizeSafe gates each lane against the same measured XYZ length.
// The fourth lane remains caller data; it is not implicitly cleared.
Vec4 NormalizeRidingForceVector(const Vec4&,const Vec4& thresholds);
std::array<float,8> CalculateGroundForce(const GroundForceSettings&,const GroundForceInput&);
bool LoadGroundForceSettings(const SettingsDatabase&,GroundForceSettings&,std::string& error);
}
