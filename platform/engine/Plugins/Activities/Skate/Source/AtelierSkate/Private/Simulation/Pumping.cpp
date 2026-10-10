#include "Pumping.h"
#include "StockSettingsReader.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Word(std::uint32_t w) {float f;std::memcpy(&f,&w,4);return f;}
float Unit(float v) {const float lower=-v>=0?0:v;return 1-lower>=0?lower:1;}
bool Scalar(const SettingsDatabase& data,std::string_view category,std::string_view key,std::string_view name,float& output,std::string& error)
{
    return StockSettingsReader(data).Float(category,key,name,output,error);
}
bool Curve(const SettingsDatabase& data,std::string_view name,PointGraph<8>& output,std::string& error)
{
    return StockSettingsReader(data).Curve8("physics_pumping","default",name,output,error);
}
}
bool PumpingConfiguration::Load(const SettingsDatabase& data,std::string& error)
{
    PumpingConfiguration c;auto& s=c.settings;const auto f=[&](std::string_view name,float& value){return Scalar(data,"physics_pumping","default",name,value,error);};
    if (!Curve(data,"PumpVsVel",s.pump_vs_speed,error)||!Curve(data,"PumpVsTime",s.pump_vs_time,error)||!Curve(data,"MinCrouchVsGroundAngle",s.min_crouch_vs_ground_angle,error)||!Curve(data,"CompressionVsGroundAngle",s.compression_vs_ground_angle,error)||!Curve(data,"CompressionVsDeckAngle",s.compression_vs_deck_angle,error)||
        !f("PumpEffectDamping",s.height_change_damping)||!f("MinChangeInCOMBeforePumping",s.minimum_height_change)||!f("MaxDeltaHeightAllowedPerFrame",s.maximum_height_change)||!f("CompressionGroundScalar",s.ground_compression_scale)||!f("CompressionDeckScalar",s.deck_compression_scale)||!f("AngularSpeedDamping",s.angular_speed_damping)) return false;
    constexpr std::array<std::string_view,5> names{"easy","normal","hardcore","motorized","test"};
    for (std::size_t i=0;i<names.size();++i)
    {
        const auto m=[&](std::string_view name,float& value){return Scalar(data,"physics_mode",names[i],name,value,error);};auto& mode=c.modes[i];
        if (!m("Hash_9D1AEE3D7D8A4A7",mode.controller.maximum_absorption_per_second)||!m("Hash_D77AFD320B6241C5",mode.controller.maximum_acceleration_per_second)||!m("PumpEffectFactorAbsorption",mode.controller.absorption_factor)||!m("PumpEffectFactor",mode.controller.acceleration_factor)||!m("UnintentionalPumpScalar",mode.unintentional_scalar)) return false;
    }
    *this=std::move(c);error.clear();return true;
}
bool PumpingConfiguration::Mode(std::uint32_t index,GroundPumpingMode& output,std::string& error) const
{
    if (index>=modes.size()) {error="Invalid pumping physics mode "+std::to_string(index);return false;}
    output=modes[index];error.clear();return true;
}
PumpingOutput PumpingState::PhysicsOutput() const
{return {0,absorption,ground_normal_absorption,minimum_crouch,deck_angle_absorption,pump_acceleration,intentional_pumping};}
float PumpingHeight(const Vec4& normal,const Vec4& com) {return Dot3(normal,com);}
float PumpingSpeed(const Vec4& previous,const Vec4& current,float dt)
{
    const float inverse=RefinedReciprocal(dt,2);Vec4 velocity;for (std::size_t i=0;i<4;++i) velocity[i]=(current[i]-previous[i])*inverse;
    const float squared=Dot3(velocity,velocity),length=squared*InverseLengthSquared(squared,2);return squared==0?0:length;
}
float PumpingAngularSpeed(const Vec4& previous_position,const Vec4& previous_normal,const PumpingSample& sample,float dt)
{
    Vec4 displacement;for (std::size_t i=0;i<4;++i) displacement[i]=sample.position[i]-previous_position[i];
    auto axis=Cross3(displacement,sample.normal);const float squared=Dot3(axis,axis),inverse=InverseLengthSquared(squared,2);
    const float length=squared==0?0:squared*inverse;
    if (length>Word(0x358637bd)) {for (auto& v:axis) v*=inverse;}else axis.fill(0);
    const float inverse_dt=RefinedReciprocal(dt,2);auto angular=Cross3(previous_normal,sample.normal);for (auto& v:angular) v*=inverse_dt;
    return Dot3(angular,axis);
}
float CalculatePumping(PumpingState& state,const PumpingSettings& s,const PumpingSample& sample,float dt)
{
    const float speed=PumpingSpeed(state.previous_position,sample.position,dt),speed_effect=s.pump_vs_speed.Evaluate(speed);
    const float angular=PumpingAngularSpeed(state.previous_position,state.previous_normal,sample,dt),measured=angular*s.angular_speed_damping;
    state.angular_speed=std::fma(1-s.angular_speed_damping,state.angular_speed,measured);state.absorption=-(speed*state.angular_speed);
    const float quarter_turns=Word(0x3f22f983),inclination=Acos(Unit(state.previous_normal[1]));const float ground_angle=Unit(quarter_turns*inclination);
    state.ground_normal_absorption=s.compression_vs_ground_angle.Evaluate(ground_angle)*s.ground_compression_scale;
    state.minimum_crouch=s.min_crouch_vs_ground_angle.Evaluate(ground_angle);state.deck_angle_absorption=s.compression_vs_deck_angle.Evaluate(sample.deck_angle*quarter_turns);
    const float deck_compression=s.deck_compression_scale*state.deck_angle_absorption,pumping=state.angular_speed*speed_effect;
    if (deck_compression*deck_compression>state.ground_normal_absorption*state.ground_normal_absorption) state.ground_normal_absorption=deck_compression;
    return pumping;
}
void UpdatePumping(PumpingState& state,const PumpingSettings& s,PumpingMode mode,const PumpingSample& sample,float dt)
{
    state.pump_acceleration=0;const float height=PumpingHeight(sample.normal,sample.com_to_deck_world);
    if (state.record_valid)
    {
        state.intentional_pumping=sample.intentional_pumping;const float change=height-state.previous_height,rising=change>=0?change:0;
        const float retained=(1-s.height_change_damping)*state.smoothed_height_change,smoothed=std::fma(rising,s.height_change_damping,retained);state.smoothed_height_change=smoothed;
        float effect=smoothed<s.minimum_height_change?0:smoothed;state.pumping_time=effect>0?state.pumping_time+dt:0;
        if (std::fabs(effect)>s.maximum_height_change) {const float sign=effect>=0?(effect>0?1:0):-1;effect=sign*s.maximum_height_change;}
        effect=s.pump_vs_time.Evaluate(state.pumping_time)*effect;const float pumping=CalculatePumping(state,s,sample,dt);state.pumping=pumping;
        const float factor=pumping*effect>0?mode.acceleration_factor:mode.absorption_factor,raw=(pumping*factor)*effect;
        const float lower=-(mode.maximum_absorption_per_second*dt),upper=mode.maximum_acceleration_per_second*dt,clamped=lower-raw>=0?lower:raw;
        state.pump_acceleration=upper-clamped>=0?clamped:upper;
    }
    state.previous_position=sample.position;state.previous_normal=sample.normal;state.record_valid=true;state.previous_height=height;
}
void UpdateGroundPumping(PumpingState& state,const PumpingSettings& s,PumpingMode mode,const PumpingSample& sample)
{UpdatePumping(state,s,mode,sample,Word(0x3c888889));}
std::array<float,8> CalculatePumpForce(const PumpForceInput& i)
{
    const float pumping=(i.flags_2476&2)==0?i.mode_multiplier*i.pumping_scalar:i.pumping_scalar;
    const float scalar=(i.input_scalar_2660*pumping)/i.timestep;const auto direction=NormalizeRidingForceVector(i.direction_432,i.normal_threshold);
    std::array<float,8> result{};for (std::size_t n=0;n<4;++n) result[n]=direction[n]*scalar;return result;
}
}
