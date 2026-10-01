// SPDX-License-Identifier: Apache-2.0
#include "Steering.h"
#include "SpeedWobble.h"
#include <cstring>
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
bool Scalar(const SettingsDatabase& data,std::string_view category,std::string_view key,std::string_view name,float& output,std::string& error)
{const auto* f=data.Field(category,key,name);const auto value=f?f->Float():std::nullopt;if (!value) {error="Expected finite stock float at "+std::string(category)+"/"+std::string(key)+"/"+std::string(name);return false;}output=*value;return true;}
bool Curve(const SettingsDatabase& data,std::string_view category,std::string_view name,PointGraph<8>& output,std::string& error)
{
    const auto* field=data.Field(category,"default",name);const std::uint32_t* words=nullptr;std::size_t offset=0;
    if (field && field->Words(16,words)) offset=0;else if (field && field->Words(20,words)) offset=4;else {error="Invalid native eight-point graph "+std::string(category)+"/default/"+std::string(name);return false;}
    for (std::size_t i=0;i<8;++i) {output.x[i]=Float(words[offset+i]);output.y[i]=Float(words[offset+8+i]);}return true;
}
}
bool SteeringSettings::Load(const SettingsDatabase& data,std::string& error)
{
    const std::pair<std::string_view,float*> fields[]={{"HardTurnIncrease",&hard_turn_increase},{"Damping",&damping},{"SteeringVsSpeedMaxSpeed",&speed_graph_max_speed},{"PushScalarIncriment",&push_scalar_increment},{"PushScalarDecriment",&push_scalar_decrement},{"PushScalarMin",&push_scalar_min},{"GeneralScalar",&general_scalar},{"SteeringScalar_TightTrucks",&tight_trucks_scalar},{"SteeringTiltBlending",&tilt_blending}};
    for (const auto& [name,output]:fields) if (!Scalar(data,"physics_steering","default",name,*output,error)) return false;
    if (!Scalar(data,"physics_manual","default","Tilt_TiltScalar",manual_scalar,error) || !Curve(data,"physics_steering","SteeringVsSpeed",speed_graph,error) || !Curve(data,"physics_steering","SteeringVsInput",input_graph,error)) return false;error.clear();return true;
}
bool SpeedWobbleSettings::Load(const SettingsDatabase& data,std::string& error)
{
    const std::pair<std::string_view,PointGraph<8>*> curves[]={{"FrequencyVsTime",&frequency_time},{"FrequencyVsSpeed",&frequency_speed},{"AmplitudeVsTime",&amplitude_time},{"AmplitudeVsSpeed",&amplitude_speed}};
    for (const auto& [name,output]:curves) if (!Curve(data,"physics_speed_wobble",name,*output,error)) return false;
    const std::pair<std::string_view,float*> fields[]={{"TruckTightnessSpeedMaxAdjust",&tightness_threshold},{"TimeMax",&time_range},{"SpeedRange",&speed_range},{"MaxFrequency",&frequency_scale},{"MaxAmplitude",&amplitude_scale},{"CrouchStartSpeedMaxAdjust",&crouch_threshold},{"CrouchMin",&height_min},{"CrouchMax",&height_max}};
    for (const auto& [name,output]:fields) if (!Scalar(data,"physics_speed_wobble","default",name,*output,error)) return false;error.clear();return true;
}
bool SpeedWobbleMode::Load(const SettingsDatabase& data,std::string_view mode,std::string& error)
{if (!Scalar(data,"physics_mode",mode,"Hash_77AFCE78FE1206CA",activation_threshold,error) || !Scalar(data,"physics_mode",mode,"Hash_5B57F2CCCCEEF430",amplitude_multiplier,error)) return false;error.clear();return true;}
}
