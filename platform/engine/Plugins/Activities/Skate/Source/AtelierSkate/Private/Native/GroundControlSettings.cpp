// SPDX-License-Identifier: Apache-2.0
#include "GroundControlSettings.h"
#include <algorithm>
#include <cmath>
#include <cstring>
namespace atelier::skate
{
namespace
{
std::string Path(std::string_view category,std::string_view key,std::string_view name)
{return std::string(category)+"/"+std::string(key)+"/"+std::string(name);}
const SettingValue* Field(const SettingsDatabase& data,std::string_view category,std::string_view key,std::string_view name,std::string& error)
{
    const auto category_id=NameId(category),field_id=NameId(name);auto current=key;
    for (std::size_t hop=0;hop<=data.Records().size();++hop)
    {
        const auto key_id=NameId(current);const auto found=std::find_if(data.Records().begin(),data.Records().end(),[&](const SettingRecord& record) {return record.category_id==category_id&&record.key_id==key_id;});
        if (found==data.Records().end()) {error="Missing stock collection "+std::string(category)+"/"+std::string(current);return nullptr;}
        const auto direct=std::lower_bound(found->fields.begin(),found->fields.end(),name,[](const SettingValue& field,std::string_view value) {return field.name<value;});
        if (direct!=found->fields.end()&&direct->name==name) return &*direct;
        const auto alias=std::find_if(found->fields.begin(),found->fields.end(),[&](const SettingValue& field) {return field.id==field_id;});if (alias!=found->fields.end()) return &*alias;
        if (found->parent.empty()) {error="Missing stock field "+Path(category,key,name);return nullptr;}current=found->parent;
    }
    error="Cyclic stock collection inheritance "+std::string(category)+"/"+std::string(key);return nullptr;
}
float Float(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
std::size_t Whitespace(std::string_view text,std::size_t at)
{
    const auto a=static_cast<unsigned char>(text[at]);if (a==' '||(a>=9&&a<=13)) return 1;
    if (at+1<text.size()&&a==0xc2) {const auto b=static_cast<unsigned char>(text[at+1]);if (b==0x85||b==0xa0) return 2;}
    if (at+2<text.size())
    {
        const auto b=static_cast<unsigned char>(text[at+1]),c=static_cast<unsigned char>(text[at+2]);
        if ((a==0xe1&&b==0x9a&&c==0x80)||(a==0xe2&&b==0x80&&((c>=0x80&&c<=0x8a)||c==0xa8||c==0xa9||c==0xaf))||(a==0xe2&&b==0x81&&c==0x9f)||(a==0xe3&&b==0x80&&c==0x80)) return 3;
    }
    return 0;
}
template<std::size_t N> bool Words(const SettingValue& field,std::array<std::uint32_t,N>& output,std::string& error)
{
    if (!field.is_text)
    {
        const std::uint32_t* words=nullptr;if (!field.Words(N,words)) {error="Expected "+std::to_string(N)+" big-endian words, found "+std::to_string(field.byte_count*2)+" bytes of hex";return false;}
        std::copy_n(words,N,output.begin());return true;
    }
    std::string hex;for (std::size_t at=0;at<field.text.size();) {const auto space=Whitespace(field.text,at);if (space) at+=space;else hex+=field.text[at++];}
    if (hex.size()!=N*8||std::any_of(hex.begin(),hex.end(),[](unsigned char c) {return c>=128;})) {error="Expected "+std::to_string(N)+" big-endian words, found "+std::to_string(hex.size())+" bytes of hex";return false;}
    for (std::size_t i=0;i<N;++i)
    {
        std::uint32_t word=0;for (std::size_t j=0;j<8;++j) {const auto c=hex[i*8+j];const int digit=c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:c>='A'&&c<='F'?c-'A'+10:-1;if (digit<0) {error="Invalid collection payload: invalid digit found in string";return false;}word=(word<<4)|std::uint32_t(digit);}output[i]=word;
    }
    return true;
}
bool Scalar(const SettingsDatabase& data,std::string_view category,std::string_view key,std::string_view name,float& output,std::string& error)
{
    const auto* field=Field(data,category,key,name,error);if (!field) return false;if (field->type!="EA::Reflection::Float") {error="Expected float at "+Path(category,key,name);return false;}
    std::array<std::uint32_t,1> words{};if (!Words(*field,words,error)) return false;const auto value=Float(words[0]);if (!std::isfinite(value)) {error="Non-finite stock float "+Path(category,key,name);return false;}output=value;return true;
}
bool Boolean(const SettingsDatabase& data,std::string_view category,std::string_view key,std::string_view name,bool& output,std::string& error)
{
    const auto* field=Field(data,category,key,name,error);if (!field) return false;if (field->type!="EA::Reflection::Bool") {error="Expected boolean at "+Path(category,key,name);return false;}
    const auto value=field->Boolean();if (!value) {error="Invalid stock boolean "+Path(category,key,name);return false;}output=*value;return true;
}
bool Curve(const SettingsDatabase& data,std::string_view category,std::string_view key,std::string_view name,PointGraph<8>& output,std::string& error,bool fixed_twenty=false)
{
    const auto* field=Field(data,category,key,name,error);if (!field) return false;std::size_t offset=0;std::array<std::uint32_t,20> values{};
    const auto size=field->is_text?field->text.size():field->byte_count*2;
    if (!fixed_twenty&&size==128) {std::array<std::uint32_t,16> words{};if (!Words(*field,words,error)) return false;std::copy(words.begin(),words.end(),values.begin());}
    else if (fixed_twenty||size==160) {if (!Words(*field,values,error)) return false;offset=4;}
    else {error="Invalid native eight-point graph "+Path(category,key,name);return false;}
    for (std::size_t i=0;i<8;++i) {output.x[i]=Float(values[offset+i]);output.y[i]=Float(values[offset+8+i]);}return true;
}
}
bool LoadGroundManualSettings(const SettingsDatabase& data,ManualSettings& output,std::string& error)
{
    ManualSettings s{};auto f=[&](std::string_view name,float& value) {return Scalar(data,"physics_manual","default",name,value,error);};
    if (!Curve(data,"physics_manual","default","NoiseVsSpeed",s.noise_vs_speed,error)||!f("TorqueScalarWithNoContact",s.torque_scale_without_contact)||!f("TorqueBleedOffWithNoContact",s.torque_bleed_without_contact)||!f("StartTorqueScalar",s.start_torque_scale)||!f("ProceduralNoiseScalar",s.procedural_noise_scale)||!f("ProceduralNoiseFreq",s.procedural_noise_frequency)||!f("PowerScalar_P",s.powerslide.proportional)||!f("PowerScalar_I",s.powerslide.integral)||!f("PowerScalar_D",s.powerslide.derivative)||!f("ManualScalar_P",s.manual.proportional)||!f("ManualScalar_I",s.manual.integral)||!f("ManualScalar_D",s.manual.derivative)||!f("MaxTiltAngle",s.maximum_tilt_degrees)||!f("MaxAngleDiff",s.maximum_angle_error)||!f("D_Scalar_Limit",s.derivative_limit)||!f("BrakeTiltAngle",s.brake_tilt_degrees)||!f("AnimationNoiseScalar",s.animation_noise_scale)) return false;
    output=s;error.clear();return true;
}
bool LoadGroundManualMode(const SettingsDatabase& data,std::string_view mode,ManualMode& output,std::string& error)
{
    ManualMode s{};if (!Scalar(data,"physics_mode",mode,"Hash_84CB2F459F3FC811",s.correction_angular_speed_threshold,error)||!Boolean(data,"physics_mode",mode,"Hash_F8CBC0F5FEF2240E",s.corrective_force_enabled,error)) return false;output=s;error.clear();return true;
}
bool LoadGroundPropulsionSettings(const SettingsDatabase& data,std::string_view mode,GroundPropulsionSettings& output,std::string& error)
{
    GroundPropulsionSettings s{};if (!Scalar(data,"physics_brakes","default","FootBrakeForce",s.braking.input_force,error)||!Scalar(data,"physics_brakes","default","TailBrakeForce",s.braking.override_force,error)||!Scalar(data,"physics_brakes","default","SlowSpeed",s.braking.minimum_speed,error)||!Scalar(data,"physics_push","default","MaxPushableSpeed",s.maximum_pushable_speed,error)||!Scalar(data,"physics_mode",mode,"MaxPushDVStart",s.mode_speed_changes[0],error)||!Scalar(data,"physics_mode",mode,"MaxPushDVEnd",s.mode_speed_changes[1],error)) return false;output=s;error.clear();return true;
}
bool LoadGroundLinearDragSettings(const SettingsDatabase& data,LinearDragSettings& output,std::string& error)
{
    LinearDragSettings s{};if (!Scalar(data,"physics_brakes","default","SlowSpeed",s.brake_speed,error)||!Scalar(data,"physics_brakes","default","ManualSpinDragSpeed",s.balance_speed,error)||!Scalar(data,"physics_brakes","default","ManualSpinDragNormal",s.comparison_threshold,error)||!Scalar(data,"physics_brakes","default","ManualSpinDrag",s.balance_drag,error)) return false;output=s;error.clear();return true;
}
bool LoadGroundSpeedModelSettings(const SettingsDatabase& data,std::string_view mode,std::string_view surface,SpeedModelSettings& output,std::string& error)
{
    SpeedModelSettings s{};auto f=[&](std::string_view category,std::string_view name,float& value) {return Scalar(data,category,"default",name,value,error);};
    if (!f("physics_speed_conservation","NegativeGeneralAmount",s.negative_gain)||!f("physics_speed_conservation","MaxGravityAcceleration",s.maximum_gravity_acceleration)||!f("physics_speed_conservation","Gravity",s.gravity)||!f("physics_speed_conservation","GeneralAmount",s.positive_gain)||!f("physics_speed_conservation","CoffinAcceleration",s.coffin_acceleration)||!Scalar(data,"physics_surfaces",surface,"Friction_MaxSpeedChange",s.speed_error_bound,error)||!Curve(data,"physics_surfaces",surface,"FrictionVsSpeedNew",s.surface_friction,error)||!f("physics_manual","SpinCorrectiveForce",s.manual_acceleration)||!f("physics_manual","MinSpeedForCorrection",s.negative_manual_angle_limit)||!f("physics_manual","MaxSpeedForCorrection",s.manual_angle_limit)||!f("physics_friction","NoInputTime",s.no_input_delay)||!Curve(data,"physics_friction","default","FrictionVsSpeed_NoInput",s.no_input_friction,error)||!Curve(data,"physics_friction","default","FrictionVsSpeed_Manual",s.manual_friction,error)||!Boolean(data,"physics_mode",mode,"MotorEnabled",s.override_enabled,error)||!Scalar(data,"physics_mode",mode,"MotorTopSpeed",s.override_speed,error)) return false;
    s.normal_threshold.fill(Float(0x358637bd));s.override_direction_threshold.fill(0.0f);output=s;error.clear();return true;
}
bool LoadGroundWallRideSettings(const SettingsDatabase& data,WallRideSettings& output,std::string& error)
{
    WallRideSettings s{};auto f=[&](std::string_view name,float& value) {return Scalar(data,"physics_feet","default",name,value,error);};
    if (!Curve(data,"physics_feet","default","WallRideAntiGravityVsTime",s.anti_gravity_vs_time,error,true)||!f("WallRideMaxDotFloorWall",s.max_dot_floor_wall)||!f("WallRideFootForceTime",s.foot_force_time)||!f("WallRideAutoJumpHeight",s.auto_jump_height)||!f("WallRideMaxTime",s.max_time)||!f("WallRideVelTimeToConsider",s.velocity_time_to_consider)||!f("WallRideAutoJumpYDownScalar",s.auto_jump_y_down_scalar)||!f("WallRideAutoJumpForce",s.auto_jump_force)) return false;output=s;error.clear();return true;
}
bool GroundSurfaceKey(std::uint32_t mode,std::string_view& output,std::string& error)
{
    constexpr std::array<std::string_view,5> keys{"smooth","rough","slow","slippery","veryslow"};if (mode<1||mode>keys.size()) {error="Processed surface mode "+std::to_string(mode)+" was not normalized by SurfacePhysics";return false;}output=keys[mode-1];error.clear();return true;
}
}
