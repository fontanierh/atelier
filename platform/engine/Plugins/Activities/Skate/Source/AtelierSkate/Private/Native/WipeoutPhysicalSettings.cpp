// SPDX-License-Identifier: Apache-2.0
#include "WipeoutPhysicalSettings.h"
#include "StockSettingsReader.h"
#include "WipeoutPhysicalMath.h"
#ifdef __clang__
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace wipeout_physical_math;
namespace
{
bool Material(const StockSettingsReader& r,const char* category,const char* prefix,ContactMaterial& m,std::string& e)
{
    const std::string p=prefix;
    return r.Float(category,"default",p+"StaticFriction",m.static_friction,e)
        &&r.Float(category,"default",p+"DynamicFriction",m.dynamic_friction,e)
        &&r.Float(category,"default",p+"Restitution",m.restitution,e);
}
}
bool WipeoutPhysicalSettings::Load(const SettingsDatabase& data,WipeoutPhysicalSettings& output,std::string& e)
{
    StockSettingsReader r(data);WipeoutPhysicalSettings s{};auto f=[&](const char* n,float& v){return r.Float("physics_wipeout","default",n,v,e);};
    if(!f("TeleportMinTimeForAutoReset",s.recovery.minimum_time)||!f("TeleportMinTimeAfterSettlingForAutoReset",s.recovery.minimum_settled)
        ||!f("TeleportMaxTime",s.recovery.maximum_time)||!f("TeleportAutoResetFadeOutTime",s.recovery.fade_time)
        ||!f("WipeoutOverSpeed",s.recovery.over_speed)||!f("WipeoutOverMinTime",s.recovery.over_minimum_time)
        ||!f("TimeToRemoveHook",s.remove_target_time)||!f("TimeToRemoveDrives",s.remove_drives_time)
        ||!f("DynamicDriveWeightVelControlled",s.controlled_weight_step)||!f("DynamicDriveWeightVelCollision",s.collision_weight_step)
        ||!f("SkateboardRestitution",s.board_restitution)||!f("SkateboardFriction",s.board_friction))return false;
    if(!r.Float("physicsdeck","default","DeckAngularDrag",s.deck_angular_drag,e))return false;
    s.deck_angular_drag*=Word(0x426fffff);
    if(!f("LivingWorldPushForce",s.push_force)||!Material(r,"physicswheels","Wheel",s.standard_materials[0],e)
        ||!Material(r,"physicstrucks","Truck",s.standard_materials[1],e)||!Material(r,"physicsdeck","Deck",s.standard_materials[2],e))return false;
    output=s;return true;
}
bool WipeoutControlProfile::Load(const SettingsDatabase& data,std::string_view key,WipeoutControlProfile& output,std::string& e)
{
    StockSettingsReader r(data);WipeoutControlProfile p{};std::vector<std::uint32_t> graph,words;
    auto f=[&](const char* n,float& v){return r.Float("physics_wipeout_control",key,n,v,e);};
    auto b=[&](const char* n,bool& v){return r.Boolean("physics_wipeout_control",key,n,v,e);};
    auto v=[&](const char* n,Vec4& value){if(!r.Words("physics_wipeout_control",key,n,4,words,e))return false;for(unsigned i=0;i<4;++i)value[i]=Word(words[i]);return true;};
    if(!r.Words("physics_wipeout_control",key,"SpinVsTime",20,graph,e))return false;
    if(!v("RollOnGroundAxis",p.roll_axis)||!v("HorizAlignAxis",p.horizontal_axis)||!v("AlignAxisEuler",p.align_euler))return false;
    for(unsigned i=0;i<8;++i){p.spin_vs_time.x[i]=Word(graph[4+i]);p.spin_vs_time.y[i]=Word(graph[12+i]);}
    if(!f("Hash_1BC908CDB3520A8E",p.direction_follow)||!f("TorqueVelScalar",p.torque_velocity)||!f("TorqueDistScalar",p.torque_distance)
        ||!f("SpinInertia",p.spin_inertia)||!b("RollOnGround",p.roll_on_ground)||!f("RollingOnGroundTorqueVelScalar",p.ground_roll_torque)
        ||!f("Hash_40B2B3C1A87A4D76",p.sideways_spin)||!f("Hash_9047531918285FC3",p.forward_spin)
        ||!b("Hash_6009FD75F9EDC436",p.horizontal_directed)||!f("DriftMaxSpeed",p.drift_maximum_speed)
        ||!f("DriftFactorZ",p.drift_forward)||!f("DriftFactorX",p.drift_sideways)||!b("AlignWithVel",p.align_with_velocity)
        ||!b("Hash_9626703A9939FE36",p.align_ground_with_velocity)||!f("AlignOnGroundTorqueVelScalar",p.ground_align_torque)
        ||!f("Hash_B65276A8CC7FB760",p.tilt_degrees)||!f("Hash_7E6B3A99C0A33ABC",p.drift_drag))return false;
    output=p;return true;
}
}
