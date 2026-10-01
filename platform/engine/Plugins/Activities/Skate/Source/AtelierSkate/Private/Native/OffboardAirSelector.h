// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "OffboardAirLaunch.h"
#include "OffboardGroundScene.h"
#include "AirTrajectoryQuery.h"
namespace atelier::skate
{
struct OffboardAirPrediction
{
    AirTrajectoryQueryResult result;AirTrajectoryQueryRequest request;
    Vec4 CollisionPosition() const{return AirTrajectoryPositionAt(request.trajectory,result.contact_time);}
};
struct BipedAirTrajectoryResult
{
    Vec4 position_272{},velocity_288{},normal_304{},contact_velocity_320{},contact_position_336{},adjustment_352{},apex_368{};
    float time_remaining_384=0,duration_388=0,scalar_392=0,apex_time_396=0;
    std::int32_t frame_400=0;bool valid_404=false;std::uint32_t word_408=0;
    void Reset();
};
struct OffboardAirCandidate
{
    AirTrajectory trajectory;Vec4 normal_64{},contact_velocity_80{},contact_position_96{};
    std::int32_t start_frame_112=0,landing_frame_116=0;bool valid_120=false,special_121=false;
};
struct OffboardAirSelection
{
    AirTrajectory trajectory_8144;Vec4 normal_6144{},velocity_6160{},position_6176{};
    bool valid_6200=false,result_present_3888=false;std::int32_t landing_frame_8480=1000;
    float scalar_8392=0;std::uint32_t word_8396=0;float candidate_scalar_100=0;
};
struct OffboardAirSampling
{
    bool pending_8492=false,restart_allowed_8493=true,preinitialized_8494=false;
    AirTrajectory fallback_8208;OffboardAirSelection selection;Vec4 adjustment_8336{};
    float blend_8384=0,elapsed_8388=0;std::int32_t frame_8484=0;
    static OffboardAirSampling ResetSampling(float retained_launch_scalar_100);
    void SeedFallback(Vec4 position,Vec4 velocity,Vec4 gravity);
    bool Commit(OffboardAirCandidate,OffboardAirPrediction&,Vec4 offset_8272);
    void Sample(std::int32_t frame,float timestep,const PointGraph<8>&,BipedAirTrajectoryResult&);
};
struct OffboardAirQuerySettings {float height=0,sphere_radius=0;std::int32_t start_index=0;};
struct OffboardAirContext {std::uint32_t selection_flags_2948;std::int32_t matching_group_2952;Vec4 up_544,forward_224;};
struct OffboardAirLedgeAdjustment
{
    OffboardGroundEdge edge;Vec4 point;AirTrajectory lowered_trajectory;std::int32_t landing_frame;float radius;
    void Apply(OffboardAirCandidate&) const;
};
std::optional<OffboardGroundEdgeSearch> SearchOffboardAirLedge(OffboardAirCandidate,OffboardAirPrediction,OffboardAirContext);
std::vector<OffboardGroundEdge> FilterOffboardAirLedges(const std::vector<OffboardGroundEdge>&,Vec4 reference);
std::optional<float> OffboardAirLedgePlaneTime(AirTrajectory,Vec4 point,Vec4 normal);
std::optional<OffboardAirLedgeAdjustment> ChooseOffboardAirLedge(OffboardAirCandidate,OffboardAirPrediction,
    OffboardAirContext,float radius,const std::vector<OffboardGroundEdge>&);
std::optional<std::array<OffboardGroundLine,6>> OffboardAirLedgeLines(OffboardAirLedgeAdjustment,float half_wheelbase);
bool ConsumeOffboardAirLedgeLines(std::size_t hit_count,std::string& error);
AirTrajectoryQueryRequest OffboardAirRequest(AirTrajectory,float radius);
bool ValidateOffboardAirRequest(AirTrajectoryQueryRequest,std::string& error);
struct OffboardAirSelectorCore
{
    OffboardAirSampling sampling;OffboardAirLaunchPacket launch;
    std::vector<OffboardAirCandidate> candidates;std::vector<OffboardAirPrediction> predictions;std::vector<float> scores;
    std::optional<std::size_t> selected_index;OffboardAirCandidate selected_candidate;
    Vec4 offset_8272{},correction_8304{},ledge_normal_8320{0,1,0,0};
    bool ledge_selected_8496=false,just_changed_8497=false,requery_pending_8499=false;
    std::int32_t requery_count_8488=0;Vec4 requery_position_8352{},requery_normal_8368{};
    explicit OffboardAirSelectorCore(OffboardAirLaunchPacket=OffboardAirLaunchPacket::Initialized(0));
    void Reset();void Exit();
    bool BeginLaunch(OffboardAirLaunchPacket,Vec4 gravity,OffboardAirQuerySettings,std::vector<AirTrajectoryQueryRequest>&,std::string&);
    bool ObserveLaunch(const std::vector<AirTrajectoryQueryResult>&,std::string&);
    bool SelectLaunch(OffboardAirContext,OffboardAirCandidate original_first,std::optional<OffboardAirLedgeAdjustment>,std::size_t&,std::string&);
    bool BeginRequery(std::uint32_t flags_2472,std::uint32_t flags_2488,float radius,std::optional<AirTrajectoryQueryRequest>&,std::string&);
    bool CompleteRequery(OffboardAirPrediction,std::string&);
    void AdjustAnimation(std::int32_t frame,Vec4 animation,const Mat4& axes,float radius);
    void Sample(std::int32_t frame,float dt,const PointGraph<8>& curve,BipedAirTrajectoryResult& out){sampling.Sample(frame,dt,curve,out);}
};
struct OffboardAirSelectorSettings
{
    OffboardAirQuerySettings query;PointGraph<8> blend;float deck_center_to_truck=0;
    bool Load(const SettingsDatabase&,std::string& error);
};
// One selector72 owns both outstanding completion slots; consuming publishes
// them explicitly. The canonical physical owner schedules these methods.
class OffboardAirSelector
{
public:
    OffboardAirSelectorCore core;OffboardAirSelectorSettings settings;
    explicit OffboardAirSelector(OffboardAirSelectorSettings value):settings(std::move(value)){}
    void Reset();void Exit(){core.Exit();}
    bool Launch(const WorldGeometry&,OffboardAirLaunchPacket,Vec4 gravity,OffboardAirContext,std::string&);
    bool ConsumeLaunch(const WorldGeometry&,OffboardAirContext,float half_wheelbase,std::optional<std::size_t>&,std::string&);
    bool Requery(const WorldGeometry&,OffboardAirContext,std::uint32_t flags_2472,std::uint32_t flags_2488,bool&,std::string&);
    bool ConsumeRequery(bool&,std::string&);
    bool Consume(const WorldGeometry&,OffboardAirContext,float half_wheelbase,std::optional<std::size_t>&,std::string&);
    void AdjustAnimation(std::int32_t frame,Vec4 animation,const Mat4& axes){core.AdjustAnimation(frame,animation,axes,settings.query.sphere_radius);}
    void Sample(std::int32_t frame,float dt,BipedAirTrajectoryResult& out){core.Sample(frame,dt,settings.blend,out);}
    const std::optional<std::vector<AirTrajectoryQueryResult>>& CompletedLaunch() const{return completed_launch_;}
    const std::optional<OffboardAirPrediction>& CompletedRequery() const{return completed_requery_;}
private:
    std::optional<std::vector<AirTrajectoryQueryResult>> completed_launch_;
    std::optional<OffboardAirPrediction> completed_requery_;
};
}
