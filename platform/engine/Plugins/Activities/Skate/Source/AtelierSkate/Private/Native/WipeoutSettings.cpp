#include "WipeoutSettings.h"
#include <algorithm>
#include <cstring>
namespace atelier::skate
{
namespace
{
const SettingValue* WipeoutField(const SettingsDatabase& data,std::string_view name,std::string& error)
{
    const auto category=NameId("physics_wipeout"),field_id=NameId(name);std::string_view current="default";
    for (std::size_t hop=0;hop<=data.Records().size();++hop)
    {
        const auto key=NameId(current);
        const auto record=std::find_if(data.Records().begin(),data.Records().end(),[&](const SettingRecord& r){return r.category_id==category&&r.key_id==key;});
        if (record==data.Records().end()) {error="Missing stock collection physics_wipeout/"+std::string(current);return nullptr;}
        const auto direct=std::lower_bound(record->fields.begin(),record->fields.end(),name,[](const SettingValue& f,std::string_view n){return f.name<n;});
        if (direct!=record->fields.end()&&direct->name==name) return &*direct;
        const auto alias=std::find_if(record->fields.begin(),record->fields.end(),[&](const SettingValue& f){return f.id==field_id;});
        if (alias!=record->fields.end()) return &*alias;
        if (record->parent.empty()) {error="Missing stock field physics_wipeout/default/"+std::string(name);return nullptr;}
        current=record->parent;
    }
    error="Cyclic stock collection inheritance physics_wipeout/default";return nullptr;
}
bool WipeoutInteger(const SettingsDatabase& data,const StockSettingsReader& reader,std::string_view name,std::int32_t& output,std::string& error)
{
    const auto field=WipeoutField(data,name,error);if (!field) return false;
    if (field->type!="EA::Reflection::Int32"&&field->type!="EA::Reflection::UInt32")
    {error="Expected integer at physics_wipeout/default/"+std::string(name);return false;}
    std::vector<std::uint32_t> words;if (!reader.Words("physics_wipeout","default",name,1,words,error)) return false;
    std::memcpy(&output,&words[0],4);return true;
}
}
bool LoadWipeoutSettings(const SettingsDatabase& data,WipeoutSettings& output,std::array<WipeoutMode,5>& output_modes,std::string& error)
{
    const StockSettingsReader reader(data);WipeoutSettings s{};std::array<WipeoutMode,5> modes{};
    // The graph and all five modes are read before the scalar settings.
    if (!reader.Curve8Layout20("physics_wipeout","default","Hash_4F08D9BAE6831524",s.air.max_landing_angle,error)) return false;
    const std::array<std::string_view,5> keys{"easy","normal","hardcore","motorized","test"};
    for (std::size_t i=0;i<keys.size();++i)
    {
        auto& m=modes[i];
        if (!reader.Boolean("physics_mode",keys[i],"Hash_CC890A3BDCF6290A",m.check_squash,error)
            ||!reader.Boolean("physics_mode",keys[i],"WipeoutCheckForBadLanding",m.check_bad_landing,error)
            ||!reader.Float("physics_mode",keys[i],"Wipeout_GroundXZAcceleration",m.ground_xz,error)
            ||!reader.Float("physics_mode",keys[i],"Hash_D978550D6DB4E6F7",m.bad_landing_scale,error)) return false;
    }
    const auto f=[&](std::string_view name,float& value){return reader.Float("physics_wipeout","default",name,value,error);};
    if (!f("Wipeout_GroundVehicleScalar",s.ground.vehicle_scalar)
        ||!f("Wipeout_GroundVehicleContact",s.ground.vehicle_contact)
        ||!f("Wipeout_GroundSkitchingContact",s.ground.skitch_contact)
        ||!f("Wipeout_GroundSkitchingScalar",s.ground.skitch_scalar)
        ||!f("Wipeout_GroundSkitchingScalarArms",s.ground.skitch_arms_scalar)
        ||!f("SkaterSkaterThresholdScalar",s.ground.skater_scalar)
        ||!f("Wipeout_GroundMaxSquash",s.ground.max_squash)
        ||!f("Wipeout_GroundMaxSquashCoffin",s.ground.max_squash_coffin)
        ||!f("Wipeout_GroundSkeletonMaxDisp",s.ground.max_displacement)
        ||!f("Wipeout_GroundSkeletonMaxContact",s.ground.max_contact)
        ||!f("Wipeout_GroundSkeletonMaxContactArms",s.ground.max_arm_contact)
        ||!f("Wipeout_GroundMaxAngularDeckError",s.ground.max_deck_error)
        ||!f("Wipeout_GroundOpposingContact",s.ground.opposing_contact)
        ||!f("Wipeout_GroundYAcceleration",s.ground.y_acceleration)
        ||!f("WipeoutGroundLightDMOScalar",s.ground.light_dmo_scalar)
        ||!f("DeckAccPlayerScalar",s.ground.player_scalar)
        ||!f("DeckAccAIScalar",s.ground.ai_scalar)
        ||!f("DeckAccSkitchScalar",s.ground.skitch_acc_scalar)
        ||!f("Wipeout_GroundBalanceTotal",s.ground.balance_total)
        ||!f("Wipeout_GroundBalanceMinSpeed",s.ground.balance_min_speed)
        ||!f("Wipeout_GroundBalanceBase",s.ground.balance_base)
        ||!f("Wipeout_AirXZTrick",s.air.xz_trick)
        ||!f("Wipeout_AirYTrick",s.air.y_trick)
        ||!f("Wipeout_AirXZAcceleration",s.air.xz_acceleration)
        ||!f("Wipeout_AirYAcceleration",s.air.y_acceleration)
        ||!f("Wipeout_AirMaxSquash",s.air.max_squash)
        ||!f("Wipeout_AirSkeletonMaxDisp",s.air.max_displacement)
        ||!f("Wipeout_AirSkeletonMaxContact",s.air.max_contact)
        ||!f("Wipeout_AirSkeletonMaxContactArms",s.air.max_arm_contact)
        ||!f("Wipeout_AirBodyFlipScalar",s.air.body_flip_scalar)
        ||!f("DeckAccBodyFlipScalar",s.air.body_flip_acc_scalar)
        ||!f("WipeoutAirLightDMOScalar",s.air.light_dmo_scalar)
        ||!WipeoutInteger(data,reader,"FramesAtStartOfAirToIgnoreDangerZone",s.air.ignore_danger_frames,error)
        ||!f("Wipeout_AirMaxSpeedIntoGround",s.air.max_landing_speed)
        ||!f("Wipeout_AirMaxSpeedIntoStairs",s.air.max_stairs_speed)
        ||!f("Wipeout_AirMaxSpeedIntoCollisionNearGrind",s.air.max_grind_speed)
        ||!f("Wipeout_GroundLeanContactYThresh",s.lean_contact_y)) return false;
    output=std::move(s);output_modes=modes;error.clear();return true;
}
}
