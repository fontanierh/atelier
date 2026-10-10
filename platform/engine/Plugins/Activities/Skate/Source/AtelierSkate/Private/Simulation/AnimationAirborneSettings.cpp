#include "AnimationAirborne.h"
#include <algorithm>
#include <cmath>
#include <cstring>
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
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
    const std::uint32_t* words;if (!value->Words(1,words)) {error="Expected 1 big-endian words, found "+std::to_string(value->is_text?value->text.size():value->byte_count*2)+" bytes of hex";return false;}
    const auto scalar=Float(words[0]);if (!std::isfinite(scalar)) {error="Non-finite stock float "+identity;return false;}output=scalar;return true;
}
template<std::size_t N,std::size_t Prefix> bool Curve(const SettingsDatabase& data,std::string_view category,std::string_view key,std::string_view name,PointGraph<N>& output,std::string& error)
{
    const auto value=Field(data,category,key,name,error);if (!value) return false;const std::uint32_t* words;
    if (!value->Words(N*2+Prefix,words)) {error="Expected "+std::to_string(N*2+Prefix)+" big-endian words, found "+std::to_string(value->is_text?value->text.size():value->byte_count*2)+" bytes of hex";return false;}
    for (std::size_t i=0;i<N;++i) {output.x[i]=Float(words[Prefix+i]);output.y[i]=Float(words[Prefix+N+i]);}return true;
}
}
bool LoadAnimationAirborneSettings(const SettingsDatabase& data,AnimationAirborneSettings& output,std::string& error)
{
    AnimationAirborneSettings settings;auto& spin=settings.spin;auto& leg=settings.air_leg;
    // Preserve the production read order, including both curves preceding the
    // spin scalars and the metadata prefix on the four-knot leg curve.
    if (!Curve<8,0>(data,"anim_motion","body_spin","spin_map",spin.map,error)||
        !Curve<8,0>(data,"animation","default","LandingDistanceScalarVsNormalY",spin.landing_distance,error)) return false;
    const auto body=[&](std::string_view name,float& value){return Scalar(data,"anim_motion","body_spin",name,value,error);};
    const auto height=[&](std::string_view name,float& value){return Scalar(data,"anim_motion","inair_disttocog",name,value,error);};
    if (!body("spin_influence_blendout",spin.blend_out)||!body("spin_influence_blendin",spin.blend_in)||
        !body("spin_clamp_influence_deltadelta",spin.maximum_acceleration)||!body("spin_clamp_influence_delta",spin.maximum_delta)||
        !height("preland_final_disttocom",spin.final_height)||!height("preland_disttocom_vel",spin.height_velocity)||
        !height("landingondeck_disttocog",spin.on_deck_height)||
        !Scalar(data,"anim_motion","body_tilt","overide_preland_x",spin.prelanding.override_x,error)||
        !Scalar(data,"anim_motion","body_tilt","overide_preland_velY",spin.prelanding.override_velocity_y,error)) return false;
    if (!Curve<4,4>(data,"anim_motion","inair_disttocog","lo_air_arm_extend",leg.arm_extension,error)||
        !height("goingup_disttocog_speed",leg.going_up_speed)||!height("goingdown_disttocog_speed",leg.going_down_speed)||
        !height("min_inair_disttocog",leg.minimum_height)||!height("preland_disttocom_vel",leg.preland_velocity)||
        !height("preland_final_disttocom",leg.preland_final_height)||!height("offboard_preland_disttocom_vel_multiplier",leg.offboard_multiplier)) return false;
    output=std::move(settings);error.clear();return true;
}
}
