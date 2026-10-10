#pragma once
#include "PlayerGrindManager.h"
#include "PlayerGrindBalance.h"
#include "PlayerGrindEntry.h"
#include "PlayerGrindControl.h"
#include "PlayerInputTypes.h"
#include "Settings.h"
namespace atelier::skate
{
struct PlayerGrindPreContext
{
    Mat4 board;std::int32_t air_counter;std::uint32_t tip_state;bool air_targeting_grind_9653;
    float balance_2720,translation_2796,stability_nudge_2800,up_down_2804,grab_min_height_2808;
};
struct PlayerGrindPostContext {Mat4 board;float balance_2720,translation_2796,stability_nudge_2800,up_down_2804,grab_min_height_2808;};
enum class PlayerGrindMaterialMode {Unchanged,Standard,Grind};
class PlayerGrindInputHost
{
public:
    virtual ~PlayerGrindInputHost()=default;
    virtual bool ApplyMaterialMode(PlayerGrindMaterialMode,std::string& error)=0;
    virtual bool SurfaceProbe(const WorldGeometry&,std::array<std::uint32_t,2>,std::size_t,PlayerGrindProbe,std::optional<PlayerGrindProbeHit>&,std::string& error)=0;
    virtual bool ForceExitLine(const WorldGeometry&,std::array<std::uint32_t,2>,PlayerGrindForceExitProbe,std::optional<PlayerGrindForceExitHit>&,std::string& error)=0;
};
struct PlayerGrindGeometryWork
{
    PlayerGrindSurfaceInput input;std::optional<PlayerGrindInvestigation> plan;std::array<std::optional<PlayerGrindProbeHit>,7> hits;
};
struct PlayerGrindPending
{
    GrindInvestigationFields fields;
    std::optional<PlayerGrindGeometryWork> geometry;
    std::optional<std::array<std::uint64_t,2>> spline_guids;
    PlayerGrindPending(GrindInvestigationFields f,std::optional<PlayerGrindGeometryWork> g,std::optional<std::array<std::uint64_t,2>> m):fields(f),geometry(std::move(g)),spline_guids(m){}
    PlayerGrindPending(PlayerGrindPending&&)=default;PlayerGrindPending& operator=(PlayerGrindPending&&)=default;
    PlayerGrindPending(const PlayerGrindPending&)=delete;PlayerGrindPending& operator=(const PlayerGrindPending&)=delete;
};
enum class PlayerGrindFamily:std::uint32_t {FiftyFifty=0,Boardslide=1,Tipslide=2,FiveO=3,Backslash=4,Darkslide=5};
// Exact completed manager publication, consumed by the later physical grind
// owner. These required observations deliberately have no guessed defaults.
struct PlayerGrindGeometryObservation
{
    Vec4 point_1120,direction_1136,normal_1152,target_up_1168,primitive_start_1264,primitive_end_1280;
    std::optional<std::array<std::uint64_t,2>> spline_guids_1296;
    Vec4 upmost_normal_1408,high_side_1440;
    std::uint32_t kind_1464,flags_1476;float impact_speed_1492;
};
struct PlayerGrindSurfaceObservation
{
    std::uint32_t audio_surface_1468,material_1472;float friction_vs_time_1496,reckon_blend_selector_1500,gravity_relief_1512;
};
struct PlayerGrindControlObservation
{
    PlayerGrindFamily family;std::uint32_t flags_1516,flags_2468,flags_2488;float translation_2796,balance_2800,exit_lean;
};
struct PlayerGrindEngagementObservation {Vec4 velocity_1184;std::uint32_t kind_1248;};
struct PlayerGrindJumperObservation
{
    std::uint32_t geometry_kind_16;PlayerGrindFamily family_20;float energy_24;
    Vec4 high_side_32,normal_48,direction_64,upmost_normal_80,point_96;
};
struct PlayerGrindObservation
{
    PlayerGrindGeometryObservation geometry;PlayerGrindSurfaceObservation surface;PlayerGrindControlObservation control;
    PlayerGrindEngagementObservation engagement;PlayerGrindJumperObservation jumper;
};
struct PlayerGrindPostResult {std::vector<std::size_t> wipeout_reasons;PlayerGrindObservation observation;};
struct PlayerGrindInputSettings
{
    PointGraph<4> friction,slope_threshold,vertical_help,gravity_vertical,gravity_linear;PointGraph<8> exit_lean;
    float truck_to_wheel,deck_to_truck,test_above,test_below,max_impact;
    static bool Load(const SettingsDatabase&,PlayerGrindInputSettings&,std::string& error);
};
class PlayerGrindInputState
{
public:
    std::uint32_t previous_state=0,engagement_counter=0,cooldown=0;bool disabled=false,suppressed=false;
    float elapsed=0,friction_vs_time=0;RawVector previous_velocity{};
    std::uint32_t grind_history=0,secondary_history=0,grounded_frames=0,air_frames=0,low_wheel_frames=0;
    bool previous_proximity=false,previous_air_target=false;Vec4 previous_direction{};float gravity_timer=0;
    PlayerGrindBalanceState balance;PlayerGrindEngagement engagement;PlayerGrindControl control;PlayerGrindJumper jumper;
    GrindInvestigationFields investigation;
    static std::optional<PlayerGrindInputState> Load(const SettingsDatabase&,std::string& error);
    void Reset();
    void Permission(const ProcessedPhysicsInput&,std::int32_t air_counter);
    void AdvanceHistory(const ProcessedPhysicsInput&);
    PlayerGrindMaterialMode MaterialMode(const ProcessedPhysicsInput&,bool nearby,bool targeting);
    bool PreUpdate(const ProcessedPhysicsInput&,const PlayerGrindStaticProvider&,const WorldGeometry&,
        PlayerGrindPreContext,PlayerGrindInputHost&,std::optional<PlayerGrindPending>& result,std::string& error);
    bool PostUpdate(ProcessedPhysicsInput&,const WorldGeometry&,PlayerGrindPending,
        PlayerGrindPostContext,PlayerGrindInputHost&,std::optional<PlayerGrindPostResult>& result,std::string& error);
    const PlayerGrindInputSettings& Settings() const {return settings_;}
private:
    PlayerGrindInputSettings settings_;
};
void PublishPlayerGrindSurface(GrindInvestigationFields&,const PlayerGrindSurface&);
bool MakePlayerGrindObservation(const ProcessedPhysicsInput&,PlayerGrindPostContext,
    std::optional<std::array<std::uint64_t,2>>,const PlayerGrindJumper&,std::optional<PlayerGrindObservation>& result,std::string& error);
}
