#include "SlideStateSettings.h"
#include "StockSettingsReader.h"
namespace atelier::skate
{
bool SlideStateSettings::Load(const SettingsDatabase& data,std::string& error)
{
    SlideStateSettings next{};StockSettingsReader reader(data);const std::array<std::string_view,5> keys{"smooth","rough","slow","slippery","veryslow"};
    for (std::size_t i=0;i<keys.size();++i)
    {
        const auto key=keys[i];auto& profile=next.surfaces[i];
        if (!reader.Curve8Layout20("physics_surfaces",key,"Powerslide_SpeedToForce",profile.surface.speed_to_force,error)||!reader.Float("physics_surfaces",key,"Powerslide_YawStrength",profile.surface.yaw_strength,error)||!reader.Float("physics_surfaces",key,"Powerslide_YawDamping",profile.surface.yaw_damping,error)||!reader.Float("physics_surfaces",key,"WheelStaticFriction",profile.material.static_friction,error)||!reader.Float("physics_surfaces",key,"WheelDynamicFriction",profile.material.dynamic_friction,error)||!reader.Float("physicswheels","default","WheelRestitution",profile.material.restitution,error)) return false;
    }
    auto& s=next.settings;
    if (!reader.Curve8Layout20("physics_slide","default","slide_input_remap",s.input_remap,error)||!reader.Curve8Layout20("physics_slide","default","Hash_DE162591FD9D91D7",s.remap_vs_speed,error)||!reader.Curve8Layout20("physics_slide","default","Hash_91282E2CC4252731",s.force_vs_angle,error)||!reader.Curve8Layout20("physics_slide","default","Hash_2AD93E5ABA231D2",s.force_vs_speed,error)||!reader.Float("physicswheels","default","SoftestWheelPowerslideFactor",s.softest_wheel_force,error)||!reader.Float("physicswheels","default","SoftestWheelPowerslideSpinFactor",s.softest_wheel_spin,error)||!reader.Float("physics_slide","default","AngularForceScalar",s.angular_force,error)||!reader.Float("physics_slide","default","PowerSlideForceYOffset",s.force_y_offset,error)||!reader.Float("physics_manual","default","PowerSlideScalar",next.manual_scalar,error)) return false;
    *this=next;error.clear();return true;
}
bool SlideStateSettings::Surface(std::uint32_t mode,const SlideSurfaceProfile*& output,std::string& error) const
{
    if (mode==0) {error="Slide requires the selected SurfacePhysics profile";return false;}
    if (mode>surfaces.size()) {error="Invalid Slide surface mode "+std::to_string(mode);return false;}
    output=&surfaces[mode-1];error.clear();return true;
}
}
