// SPDX-License-Identifier: Apache-2.0
#include "AirTrajectorySelectorSettings.h"
#include "StockSettingsReader.h"
#include <algorithm>
#include <cstring>
namespace atelier::skate
{
namespace
{
const SettingValue* Field(const SettingsDatabase& data,std::string_view category,std::string_view name,std::string& error)
{
    const auto category_id=NameId(category),field_id=NameId(name);std::string_view current="default";
    for (std::size_t hop=0;hop<=data.Records().size();++hop)
    {
        const auto key_id=NameId(current);
        const auto record=std::find_if(data.Records().begin(),data.Records().end(),[&](const SettingRecord& r) {return r.category_id==category_id&&r.key_id==key_id;});
        if (record==data.Records().end()) {error="Missing stock collection "+std::string(category)+"/"+std::string(current);return nullptr;}
        const auto direct=std::lower_bound(record->fields.begin(),record->fields.end(),name,[](const SettingValue& field,std::string_view n) {return field.name<n;});
        if (direct!=record->fields.end()&&direct->name==name) return &*direct;
        const auto alias=std::find_if(record->fields.begin(),record->fields.end(),[&](const SettingValue& field) {return field.id==field_id;});
        if (alias!=record->fields.end()) return &*alias;
        if (record->parent.empty()) {error="Missing stock field "+std::string(category)+"/default/"+std::string(name);return nullptr;}
        current=record->parent;
    }
    error="Cyclic stock collection inheritance "+std::string(category)+"/default";return nullptr;
}
float FromBits(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
template<std::size_t N> bool Graph(const SettingsDatabase& data,const StockSettingsReader& reader,
    std::string_view category,std::string_view name,bool negative,PointGraph<N>& output,std::string& error)
{
    const auto field=Field(data,category,name,error);if (!field) return false;
    const std::string expected=std::string(negative?"Sk8::PointNegGraphData":"Sk8::PointGraphData")+std::to_string(N);
    if (field->type!=expected) {error="Wrong stock graph type "+std::string(category)+"/"+std::string(name);return false;}
    const std::size_t offset=negative?4:0;std::vector<std::uint32_t> words;
    if (!reader.Words(category,"default",name,offset+2*N,words,error)) return false;
    for (std::size_t i=0;i<N;++i) {output.x[i]=FromBits(words[offset+i]);output.y[i]=FromBits(words[offset+N+i]);}
    return true;
}
bool Integer(const SettingsDatabase& data,const StockSettingsReader& reader,std::string_view category,
    std::string_view name,std::int32_t& output,std::string& error)
{
    const auto field=Field(data,category,name,error);if (!field) return false;
    if (field->type!="EA::Reflection::Int32"&&field->type!="EA::Reflection::UInt32")
    {error="Expected integer at "+std::string(category)+"/default/"+std::string(name);return false;}
    std::vector<std::uint32_t> words;if (!reader.Words(category,"default",name,1,words,error)) return false;
    std::memcpy(&output,&words[0],4);return true;
}
}
bool LoadAirTrajectorySelectorSettings(const SettingsDatabase& data,AirTrajectorySelectorSettings& output,std::string& error)
{
    AirTrajectorySelectorSettings s{};const StockSettingsReader reader(data);
    const auto t=[&](std::string_view name,float& value) {return reader.Float("physics_trajectory","default",name,value,error);};
    const auto r=[&](std::string_view name,float& value) {return reader.Float("physics_reckoning","default",name,value,error);};
    if (!t("ConeAngleX",s.cone_x)||!t("ConeAngleZ",s.cone_z)||!t("TrajectoryMaxTime",s.trajectory_max_time)
        ||!t("TrajectoryMaxDrop",s.trajectory_max_drop)||!t("TrajectoryMaxErrorStart",s.trajectory_error_start)
        ||!t("TrajectoryMaxErrorEnd",s.trajectory_error_end)||!t("SpeedFactorMin",s.speed_factor_min)||!t("SpeedFactorMax",s.speed_factor_max)
        ||!Graph(data,reader,"physics_trajectory","ConeAngleZVsSpeed",false,s.cone_angle_z_vs_speed,error)
        ||!t("ConeAngleXSecondPass",s.cone_x_second_pass)||!t("ConeAngleZSecondPass",s.cone_z_second_pass)
        ||!Graph(data,reader,"physics_trajectory","LandingTimeBonus",true,s.landing_time_bonus,error)
        ||!Graph(data,reader,"physics_trajectory","LandingComScalarVsSlope",true,s.landing_com_scalar_vs_slope,error)
        ||!Graph(data,reader,"physics_trajectory","LandingForceScalarVsDPVelNorm",false,s.landing_force_scalar,error)
        ||!Graph(data,reader,"physics_trajectory","GrindPenaltyVsDistToGrind",true,s.grind_penalty_vs_distance,error)
        ||!t("ScoreMiddleBonus",s.score_middle_bonus)||!t("ScoreLandingForce",s.score_landing_force)
        ||!t("ScoreLandingDirection",s.score_landing_direction)||!t("ScoreTransition",s.score_transition)
        ||!t("ScoreSurface_Unrideable",s.surface_unrideable_score)||!t("ScoreSurface_DontAlign",s.surface_dont_align_score)
        ||!t("NaturalAirOffVertsScalar",s.natural_air_off_verts_scalar)||!t("MinTimeForTrajectoryToBeValid",s.minimum_valid_time)
        ||!t("MinTimeAfterApexForTransition",s.minimum_time_after_apex)||!t("MinNormalDeltaForSecondPass",s.minimum_normal_delta_second_pass)
        ||!t("MaxTrajectoryAdjust",s.maximum_trajectory_adjust)||!t("WallRideTestDist",s.wall_ride_test_distance)
        ||!t("WallRideMinHeightFromGround",s.wall_ride_minimum_height)||!t("WallRideAngleToAllowLanding",s.wall_ride_angle_allow_landing)
        ||!t("ScoreWallrideHeight",s.wall_ride_height_score)
        ||!Graph(data,reader,"physics_trajectory","WallRideBoost",true,s.wall_ride_boost,error)
        ||!reader.Float("physics_feet","default","WallRideMaxDotFloorWall",s.wall_ride_normal_dot_limit,error)
        ||!Graph(data,reader,"physics_reckoning","TrajectoryDispVsSpeed",false,s.displacement_vs_speed,error)
        ||!Graph(data,reader,"physics_reckoning","TrajectoryDispVsGroundNorm",false,s.displacement_vs_ground_normal,error)
        ||!r("TrajectoryRadius",s.trajectory_radius)||!r("TrajectoryDisplacement",s.trajectory_displacement)
        ||!Integer(data,reader,"physics_reckoning","MinTrajectorySize",s.minimum_trajectory_frames,error)
        ||!r("VertJumpAlignFactor",s.vert_jump_align_factor)||!r("VertJumpAlignMaxGroundNormalY",s.vert_jump_align_max_ground_normal_y)
        ||!r("VertJumpAlignMinJumpDirY",s.vert_jump_align_min_direction_y)||!r("VertJumpAlignMaxAngle",s.vert_jump_align_max_angle)) return false;
    output=std::move(s);error.clear();return true;
}
}
