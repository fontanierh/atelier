#include "GroundSettings.h"
#include "GroundControlSettings.h"
#include "StockSettingsReader.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float StockWord(std::uint32_t word) {float f;std::memcpy(&f,&word,4);return f;}
}
bool GroundSettings::Load(const SettingsDatabase& data,std::string_view mode,std::string_view surface,std::string& error)
{
    GroundSettings s{};StockSettingsReader reader(data);
    const auto f=[&](std::string_view category,std::string_view field,float& v) {return reader.Float(category,"default",field,v,error);};
    const auto m=[&](std::string_view field,float& v) {return reader.Float("physics_mode",mode,field,v,error);};
    const auto p=[&](std::string_view field,float& v) {return reader.Float("physics_surfaces",surface,field,v,error);};
    s.push_target_multiplier=1;
    if (!f("physics_feet","FootForceOffset",s.foot_force_offset)
        ||!f("physics_feet","AbsorptionFootForceScalar",s.absorption_front)
        ||!f("physics_feet","AbsorptionFootForceRearScalar",s.absorption_rear)
        ||!p("BrakingScalar",s.surface_braking_factor)
        ||!s.steering.Load(data,error)
        ||!s.wobble.Load(data,error)
        ||!LoadGroundPropulsionSettings(data,mode,s.propulsion,error)
        ||!LoadGroundForceSettings(data,s.force,error)
        ||!LoadGroundSpeedModelSettings(data,mode,surface,s.speed,error)
        ||!s.torque.Load(data,surface,error)
        ||!LoadGroundManualSettings(data,s.manual,error)
        ||!LoadGroundManualMode(data,mode,s.manual_mode,error)
        ||!LoadGroundLinearDragSettings(data,s.drag,error)
        ||!f("physics_collision","CollisionTorqueMaxTime",s.collision_duration)
        ||!f("physics_collision","CollisionTorqueFadeoff",s.collision_scale)
        ||!f("physics_feet","MaxTimeWallRidingForFootForce",s.contact_force_time)
        ||!p("WheelStaticFriction",s.wheel_material.static_friction)
        ||!p("WheelDynamicFriction",s.wheel_material.dynamic_friction)
        ||!f("physicswheels","WheelRestitution",s.wheel_material.restitution)
        ||!m("Hash_77AFCE78FE1206CA",s.wobble_activation)
        ||!m("Hash_5B57F2CCCCEEF430",s.wobble_amplitude)) return false;
    *this=std::move(s);error.clear();return true;
}
GroundSettings GroundSettings::Tuned(TrainerTuning tuning) const
{
    auto result=*this;
    result.push_target_multiplier=tuning.push_speed;
    result.propulsion.maximum_pushable_speed*=tuning.push_speed;
    for (auto& dv:result.propulsion.mode_speed_changes) dv*=tuning.push_power;
    result.propulsion.braking.input_force*=tuning.braking;
    result.propulsion.braking.override_force*=tuning.braking;
    result.steering.general_scalar*=tuning.steering;
    result.wobble_amplitude*=tuning.wobble;
    result.torque.slide.friction*=tuning.grip;
    result.wheel_material.static_friction*=tuning.grip;
    result.wheel_material.dynamic_friction*=tuning.grip;
    result.torque.heading.turn_strength*=tuning.turn_power;
    result.drag.balance_drag*=tuning.manual_drag;
    for (auto* curve:{&result.speed.surface_friction,&result.speed.no_input_friction,&result.speed.manual_friction})
        for (auto& y:curve->y) y*=tuning.rolling_friction;
    result.speed.gravity*=tuning.hill_speed;
    result.speed.maximum_gravity_acceleration*=tuning.hill_speed;
    result.wobble_activation*=tuning.wobble_onset;
    for (auto& y:result.manual.noise_vs_speed.y) y*=tuning.manual_drift;
    result.manual.procedural_noise_scale*=tuning.manual_drift;
    result.manual.animation_noise_scale*=tuning.manual_drift;
    return result;
}
GroundBoardSettings GroundSettings::Board() const
{
    return {steering,wobble,propulsion,force,speed,torque.slide,torque.straighten,torque.heading,torque.anti_flip,
        manual,manual_mode,drag,collision_duration,collision_scale,contact_force_time,StockWord(0x37800000)};
}
bool GroundProfiles::Load(const SettingsDatabase& data,std::string& error)
{
    decltype(profiles_) profiles;
    constexpr std::array<std::string_view,5> modes{"easy","normal","hardcore","motorized","test"};
    for (std::size_t mode=0;mode<modes.size();++mode)
        for (std::uint32_t surface=1;surface<=5;++surface)
        {
            std::string_view key;if (!GroundSurfaceKey(surface,key,error)) return false;
            auto value=std::make_shared<GroundSettings>();
            if (!value->Load(data,modes[mode],key,error)) return false;
            profiles[mode][surface-1]=std::move(value);
        }
    profiles_=std::move(profiles);error.clear();return true;
}
std::shared_ptr<const GroundSettings> GroundProfiles::Select(std::uint32_t mode,std::uint32_t surface,std::string& error) const
{
    if (mode<profiles_.size()&&surface>=1&&surface<=5&&profiles_[mode][surface-1])
    {error.clear();return profiles_[mode][surface-1];}
    error="Invalid processed physics mode/surface "+std::to_string(mode)+"/"+std::to_string(surface);
    return {};
}
}
