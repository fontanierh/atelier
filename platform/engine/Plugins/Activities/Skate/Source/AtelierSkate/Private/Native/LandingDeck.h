#pragma once
#include "AirTrajectoryQuery.h"
#include "BoardToolkit.h"
#include "PlayerInputTypes.h"
#include "OffboardStaticScene.h"
#include "Settings.h"
namespace atelier::skate
{
struct LandingDeckSettings{float deck_min_uprightness=0,approximate_com_height=0;};
struct LandingDeckInput
{
    Vec4 board_up_80,board_position_112,board_velocity_400,up_544;
    std::int32_t support_1776;std::uint32_t flags_2480,mode_2540,wheel_contacts_2556;
};
struct LandingDeckAssistInput{LandingDeckInput processed;Vec4 position,velocity;float maximum_velocity_change;};
struct LandingDeckIkInput{LandingDeckInput processed;float time_to_land;Mat4 animation_root;Vec4 animation_com_10960,mapped_position_12608;};
struct LandingDeckSyncInput{Vec4 position_592;std::uint32_t flags_2488;};
struct LandingDeckUpdateOutput
{
    bool can_land,trajectory_valid;float time_to_land,elapsed,landing_time,apex_time;
    Vec4 position,landing_velocity,launch_position,landing_position,normal,apex_position,direction,up;
    std::optional<AirTrajectoryQueryRequest> query;
};
struct LandingDeckFillOutput{bool can_land_316,hippy_hurdling_317;std::optional<Vec4> moving_contact;};
struct LandingDeckManager;
class LandingDeckHippyVelocity
{
public:
    virtual ~LandingDeckHippyVelocity()=default;
    virtual bool Calculate(const LandingDeckManager&,Vec4&,std::string& error)=0;
};
// Manager68 is shared by501 and503. No separate trajectory belongs to either
// facade, and Reset deliberately retains proposed96 and pending262.
struct LandingDeckManager
{
    AirTrajectory trajectory_32,proposed_96;float elapsed_160=0;bool trajectory_valid_164=false;
    Vec4 ik_offset_176{},vector_192{},moving_contact_208{},vector_224{};
    float obstruction_height_240=0,time_to_land_244=0,proposed_time_248=0;
    std::uint32_t completed_queries_252=0;
    bool can_land_256=false,force_257=false,blocked_258=false,tested_259=false,hippy_hurdling_260=false,publish_moving_contact_261=false,pending_262=false;
    void Reset();void CorrectTrajectory(Vec4 centre_of_mass);LandingDeckFillOutput Fill() const;
    std::optional<AirTrajectoryQueryRequest> Assist(const LandingDeckAssistInput&,LandingDeckSettings);
    LandingDeckUpdateOutput Update(const LandingDeckInput&,LandingDeckSettings);
    Vec4 CalculateAccurateIkOffset(const LandingDeckIkInput&);
    void QuerySubmitted(){pending_262=true;}
    bool Sync(std::optional<AirTrajectoryQueryResult>,LandingDeckSyncInput,LandingDeckHippyVelocity&,std::string& error);
private:
    void ConsiderBoard(const LandingDeckInput&,LandingDeckSettings,Vec4 position,Vec4 velocity);
    AirTrajectoryQueryRequest PrepareQuery(const LandingDeckInput&,Vec4 position,float time);
    bool SyncCompleted(std::optional<AirTrajectoryQueryResult>,LandingDeckSyncInput,LandingDeckHippyVelocity&,std::string& error);
};
// Only references to the canonical player packet/toolkit are borrowed here.
struct LandingDeckPlayerView{const ProcessedPhysicsInput& processed;const std::optional<BoardToolkit>& toolkit;};
Vec4 CalculateOffboardHippyJump(float desired_height,Vec4 board_position,Vec4 centre_of_mass,Vec4 reference_up,Vec4 current_velocity);
bool ReadLandingDeckInput(LandingDeckPlayerView,LandingDeckInput&,std::string& error);
class LandingDeck
{
public:
    LandingDeckManager manager;LandingDeckSettings settings;
    bool Load(const SettingsDatabase&,std::string& error);
    void Reset(){manager.Reset();}
    bool Assist(const OffboardStaticScene&,LandingDeckPlayerView,float maximum_velocity_change,std::string& error);
    bool Update(const OffboardStaticScene&,LandingDeckPlayerView,LandingDeckUpdateOutput&,std::string& error);
    bool Submit(const OffboardStaticScene&,AirTrajectoryQueryRequest,LandingDeckPlayerView,std::string& error);
    bool PostPhysics(LandingDeckPlayerView,std::string& error);
    bool CalculateAccurateIkOffset(LandingDeckPlayerView,const Mat4& animation_root,Vec4 animation_com,
        Vec4 mapped_position_12608,float time_to_land,Vec4&,std::string& error);
    LandingDeckFillOutput Fill() const{return manager.Fill();}
    void Publish(OffBoardOutputFields&,RawVector& skeleton_position_48,std::uint8_t& skeleton_flag_3482) const;
    const std::optional<AirTrajectoryQueryResult>& Completion() const{return completion_;}
private:
    std::optional<AirTrajectoryQueryResult> completion_;
};
}
