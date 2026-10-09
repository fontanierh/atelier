#include "RidingAnimation.h"
#include <algorithm>
#include <cstring>
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word) {float f;std::memcpy(&f,&word,4);return f;}
const SettingValue* Field(const SettingsDatabase& data,std::string_view category,std::string_view key,std::string_view name,std::string& error)
{
    if (const auto value=data.Field(category,key,name)) return value;
    const auto class_id=NameId(category);std::string current(key);
    for (std::size_t depth=0;depth<=data.Records().size();++depth)
    {
        const auto current_id=NameId(current);const auto item=std::find_if(data.Records().begin(),data.Records().end(),[&](const auto& value){return (value.category==category||value.category_id==class_id)&&(value.key==current||value.key_id==current_id);});
        if (item==data.Records().end()) {error="Missing stock collection "+std::string(category)+"/"+current;return nullptr;}
        if (item->parent.empty()) {error="Missing stock field "+std::string(category)+"/"+std::string(key)+"/"+std::string(name);return nullptr;}current=item->parent;
    }
    error="Cyclic stock collection inheritance "+std::string(category)+"/"+std::string(key);return nullptr;
}
bool Scalar(const SettingsDatabase& data,std::string_view category,std::string_view key,std::string_view name,float& output,std::string& error)
{
    const auto value=Field(data,category,key,name,error);if (!value) return false;const auto identity=std::string(category)+"/"+std::string(key)+"/"+std::string(name);
    if (value->type!="EA::Reflection::Float") {error="Expected float at "+identity;return false;}
    const std::uint32_t* words;
    if (!value->Words(1,words)) {error="Expected 1 big-endian words, found "+std::to_string(value->is_text?value->text.size():value->byte_count*2)+" bytes of hex";return false;}
    const auto f=Float(words[0]);if (!std::isfinite(f)) {error="Non-finite stock float "+identity;return false;}output=f;return true;
}
template<std::size_t N> bool Words(const SettingsDatabase& data,std::string_view category,std::string_view key,std::string_view name,std::array<float,N>& output,std::string& error)
{
    const auto value=Field(data,category,key,name,error);if (!value) return false;const std::uint32_t* words;
    if (!value->Words(N,words)) {error="Expected "+std::to_string(N)+" big-endian words, found "+std::to_string(value->is_text?value->text.size():value->byte_count*2)+" bytes of hex";return false;}
    for (std::size_t i=0;i<N;++i) {output[i]=Float(words[i]);}
    return true;
}
template<std::size_t N,std::size_t Prefix> bool Curve(const SettingsDatabase& data,std::string_view category,std::string_view key,std::string_view name,PointGraph<N>& output,std::string& error)
{
    std::array<float,N*2+Prefix> words;if (!Words(data,category,key,name,words,error)) return false;
    for (std::size_t i=0;i<N;++i) {output.x[i]=words[Prefix+i];output.y[i]=words[Prefix+N+i];}return true;
}
}
bool LoadAnimationCrouchingSettings(const SettingsDatabase& data,AnimationCrouchingSettings& output,std::string& error)
{
    AnimationCrouchingSettings s;const auto c=[&](std::string_view name,float& f){return Scalar(data,"anim_motion","crouching",name,f,error);};const auto a=[&](std::string_view name,float& f){return Scalar(data,"anim_motion","auto_pump",name,f,error);};
    if (!Curve<8,4>(data,"anim_motion","crouching","crouching_max_height",s.maximum_height,error)||!Curve<8,0>(data,"anim_motion","crouching","absorption_upforce",s.absorption_upforce,error)||!Curve<8,0>(data,"anim_motion","crouching","pump_maxspeed",s.pump_maxspeed,error)||
        !c("crouching_min_height",s.minimum_height)||!c("crouch_max_ratio",s.maximum_ratio)||!c("crouch_max_delta_delta",s.maximum_delta_delta)||!c("crouch_max_delta",s.maximum_delta)||!c("crouch_blend_input",s.input_blend)||!c("pump_maxspeed_yaxis",s.pump_vertical_speed)||!c("MaxCrouchFromDeckAngle",s.maximum_crouch_from_deck)||!c("absorption_skateboard_damping",s.skateboard_damping)||!c("absorption_maxforce",s.maximum_force)||!c("absorption_ground_maxforce",s.maximum_ground_force)||!c("absorption_factor",s.absorption_factor)) return false;
    auto& p=s.auto_pump;
    if (!Curve<4,4>(data,"anim_motion","auto_pump","auto_pump_max_crouch",p.maximum_crouch,error)||!a("auto_pump_sufficient_crouch",p.sufficient_crouch)||!a("auto_pump_standing_thresh",p.standing_threshold)||!a("auto_pump_rise_speed",p.rise_speed)||!a("auto_pump_pump_speed",p.pump_speed)||!a("auto_pump_potential_thresh",p.potential_threshold)||!a("auto_pump_potential_blend",p.potential_blend)||!a("auto_pump_intent_mag_start",p.intent_magnitude_start)||!a("auto_pump_intent_angle_region",p.intent_angle_region)||!a("auto_pump_crouch_time",p.crouch_time)||!a("auto_pump_crouch_speed",p.crouch_speed)) return false;
    output=std::move(s);error.clear();return true;
}
bool LoadAnimationBodyTiltSettings(const SettingsDatabase& data,AnimationBodyTiltSettings& output,std::string& error)
{
    AnimationBodyTiltSettings s;const auto f=[&](std::string_view name,float& v){return Scalar(data,"anim_motion","body_tilt",name,v,error);};
    if (!Curve<4,4>(data,"anim_motion","body_tilt","body_tilt_bodyspin_factor",s.body_spin_factor,error)||!f("body_tilt_ground_clamp_vel",s.ground_velocity)||!f("body_tilt_ground_clamp_acc",s.ground_acceleration)||!f("body_tilt_air_clamp_vel",s.air_velocity)||!f("body_tilt_air_clamp_acc",s.air_acceleration)) return false;
    output=std::move(s);error.clear();return true;
}
bool LoadAnimationPumpSettings(const SettingsDatabase& data,AnimationPumpSettings& output,std::string& error)
{
    AnimationPumpSettings s;const auto f=[&](std::string_view name,float& v){return Scalar(data,"anim_motion","anim_pump",name,v,error);};
    if (!Curve<8,0>(data,"anim_motion","anim_pump","pump_amplify",s.amplify,error)||!f("pump_prop_blend",s.input_blend)||!f("max_phys_pump",s.maximum_physics_pump)||!f("new_pump_thresh",s.new_pump_threshold)||!f("pump_blendin",s.blend_in)||!f("pump_blendout",s.blend_out)) return false;
    output=std::move(s);error.clear();return true;
}
bool LoadAnimationTurningSettings(const SettingsDatabase& data,SetTurningSettings& output,std::string& error)
{
    SetTurningSettings s;const auto f=[&](std::string_view name,float& v){return Scalar(data,"anim_carving","default",name,v,error);};
    if (!Curve<16,4>(data,"anim_carving","default","quickMagMap",s.remaps[0].magnitude,error)||!Curve<16,4>(data,"anim_carving","default","quickAngleMap",s.remaps[0].angle,error)||!f("quickAngleOffset",s.remaps[0].angle_offset)||!Curve<16,4>(data,"anim_carving","default","slowMagMap",s.remaps[1].magnitude,error)||!Curve<16,4>(data,"anim_carving","default","slowAngleMap",s.remaps[1].angle,error)||!f("slowAngleOffset",s.remaps[1].angle_offset)||!Curve<8,4>(data,"anim_carving","default","speed_tuck",s.speed_tuck,error)||!Curve<8,4>(data,"anim_carving","default","blend_lean_in",s.blend,error)||!f("speed_tuck_start",s.speed_threshold)||!f("clamp_curr_lean",s.maximum_delta)||!Scalar(data,"anim_motion","power_slide","slide_turn_value",s.override_turn,error)) return false;
    output=std::move(s);error.clear();return true;
}
bool LoadAnimationTurnFeedbackSettings(const SettingsDatabase& data,TurnConditionerSettings& output,std::string& error)
{
    TurnConditionerSettings s;
    if (!Curve<8,4>(data,"physics_animation","default","ScaleQuicknessAtSpeed",s.speed_curve,error)||!Curve<4,4>(data,"physics_animation","default","SpeedWobbleTurnBlend",s.smoothing_curve,error)) return false;
    constexpr std::array<std::string_view,13> parameters{"QuicknessMaxDelta","InputQuicknessMax","InputQuicknessBlendVal","HoldingMinVal","HoldingMaxAcceleration","HoldingIntegralBlend","HoldingBlendUp","HoldingBlendDown","AnimationTurnWobbleScalar","AnimationTurnPhysicsWeight","AnimationTurnMaxLean","AnimationTurnGraphX","AnimationTurnDirMax"};
    for (std::size_t i=0;i<parameters.size();++i) if (!Scalar(data,"physics_animation","default",parameters[i],s.parameters[i],error)) return false;
    constexpr std::array<std::string_view,3> coefficients{"AnimationTurnLeanFilterSlow","AnimationTurnLeanFilter","AnimationTurnDirFilter"};for (std::size_t i=0;i<coefficients.size();++i) if (!Words(data,"physics_animation","default",coefficients[i],s.filter_coefficients[i],error)) return false;
    if (!Curve<8,0>(data,"physics_animation","default","AnimationTurnSpeedGraph",s.input_curve,error)||!Curve<8,0>(data,"physics_animation","default","QuicknessVsQuickness",s.quickness_curve,error)) return false;
    output=std::move(s);error.clear();return true;
}
bool LoadAnimationGroundAccelerationSettings(const SettingsDatabase& data,AnimationGroundAccelerationSettings& output,std::string& error)
{
    AnimationGroundAccelerationSettings s;if (!Scalar(data,"anim_motion","bumps","scale_x_acc",s.scale_x_acc,error)||!Scalar(data,"anim_motion","bumps","min_bump_mag",s.min_bump_mag,error)) return false;output=s;error.clear();return true;
}
}
