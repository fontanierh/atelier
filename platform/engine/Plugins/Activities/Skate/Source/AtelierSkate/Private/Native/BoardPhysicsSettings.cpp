// SPDX-License-Identifier: Apache-2.0
#include "BoardPhysicsSettings.h"
#include <cstring>

namespace atelier::skate
{
std::optional<BoardPhysicsSettings> BoardPhysicsSettings::Load(const SettingsDatabase& data,std::string& error)
{
    error.clear();
    const auto field=[&](std::string_view category,std::string_view name)->const SettingValue*
    {
        const auto value=data.Field(category,"default",name);
        if(!value && error.empty())error="Missing stock field "+std::string(category)+"/default/"+std::string(name);
        return value;
    };
    const auto f=[&](std::string_view category,std::string_view name)
    {
        const auto value=field(category,name);const auto result=value?value->Float():std::nullopt;
        if(!result || !std::isfinite(*result))
        {
            if(error.empty())error="Invalid stock float "+std::string(category)+"/default/"+std::string(name);
            return 0.0f;
        }
        return *result;
    };
    const auto b=[&](std::string_view category,std::string_view name)
    {
        const auto value=field(category,name);const auto result=value?value->Boolean():std::nullopt;
        if(!result && error.empty())error="Invalid stock boolean "+std::string(category)+"/default/"+std::string(name);
        return result.value_or(false);
    };
    const auto u=[&](std::string_view category,std::string_view name)
    {
        const auto value=field(category,name);const auto result=value?value->Integer():std::nullopt;
        if(!result && error.empty())error="Invalid stock integer "+std::string(category)+"/default/"+std::string(name);
        return result.value_or(0);
    };
    BoardPhysicsSettings output;
    const float factor=f("physics_world","SkateboardMassFactor"),radius=f("physicswheels","WheelRadius"),x=f("physicswheels","WheelXDist");
    const AuthoredTransformInputs geometry{f("physicsdeck","DeckMidLength"),x,f("physicstrucks","TruckZPosFront"),
        f("physicstrucks","TruckZPosBack"),f("physicstrucks","TruckYPos")};
    const auto wheel=WheelMassProperties({radius,f("physicswheels","WheelMass"),factor});
    const TruckMassSettings truck_settings{radius,x,f("physicstrucks","RadiusScalar"),f("physicstrucks","HalfHeightScalar"),f("physicstrucks","TruckMass"),factor};
    const auto truck=TruckMassProperties(truck_settings);
    std::array<float,4> gravity{};const std::uint32_t* words=nullptr;
    const auto gravity_field=field("physics","WorldGravity");
    if(!gravity_field || !gravity_field->Words(4,words))
    {if(error.empty())error="Invalid stock gravity vector";return std::nullopt;}
    for(std::size_t i=0;i<4;++i)std::memcpy(&gravity[i],words+i,4);
    const auto simulation=SimulationStep::Fixed60Hz(0,f("physics","FreezingEnergy"),{gravity[0],gravity[1],gravity[2]});
    output.collision.deck_geometry=DeckGeometry({f("physicsdeck","DeckWidth"),geometry.deck_mid_length,
        f("physicsdeck","DeckThickness"),f("physicsdeck","DeckBackEndSize"),f("physicsdeck","DeckFrontEndAngle"),
        f("physicsdeck","DeckBackEndAngle"),static_cast<std::int32_t>(u("physicsdeck","DeckEndCapsules")),
        b("physicsdeck","DeckEnableDeckVolumeCollisions"),b("physicsdeck","DeckEnableEndVolumeCollisions")});
    const auto deck=DeckMassProperties(output.collision.deck_geometry,f("physicsdeck","DeckMass")*factor,
        f("physicsdeck","DeckAngularDrag")*simulation.frequency);
    output.step={simulation,u("physics","RWMaxIterations"),CalculateTruckTransforms({geometry.deck_mid_length,
        geometry.truck_z_position_front,geometry.truck_z_position_back,geometry.truck_y_position,
        f("physicstrucks","TruckRotationAxisAngle")}),TruckDriveDynamics({b("physicstrucks","UseTruckDrives"),
        b("physicsdeck","UseHardDrives"),f("physicstrucks_drives","Angular_Hard_Displacement"),
        f("physicstrucks_drives","Angular_Hard_Damping"),f("physicstrucks_drives","Angular_Hard_Strength")}),f("physicsdeck","DeckForceYOffset")};
    if(!error.empty())return std::nullopt;
    if(radius<=0 || factor<=0 || output.step.iterations==0)
    {error="Invalid stock board radius, mass factor or solver iterations";return std::nullopt;}
    output.masses={wheel,wheel,wheel,wheel,truck,truck,deck};output.authored=AuthoredBodyTransforms(geometry);
    output.collision.truck_shape=TruckMassInput(truck_settings).shape;
    output.collision.truck_collisions=b("physicstrucks","TruckEnableVolumeCollisions");
    output.collision.truck_material={f("physicstrucks","TruckStaticFriction"),f("physicstrucks","TruckDynamicFriction"),f("physicstrucks","TruckRestitution")};
    output.collision.deck_material={f("physicsdeck","DeckStaticFriction"),f("physicsdeck","DeckDynamicFriction"),f("physicsdeck","DeckRestitution")};
    output.collision.wheel_radius=radius;
    output.collision.wheel_material={f("physicswheels","WheelStaticFriction"),f("physicswheels","WheelDynamicFriction"),f("physicswheels","WheelRestitution")};
    output.standard_wheel_material=output.collision.wheel_material;output.floor_material={0,0,1};
    output.input_magnitude_threshold=f("inputlistener","StickMagnitudeMinToCountHeld");
    if(!error.empty())return std::nullopt;return output;
}
}
