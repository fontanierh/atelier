#pragma once
#include "OffboardAirSelector.h"
#include "WipeoutRuntime.h"
namespace atelier::skate
{
struct BipedAirEnterInput
{Mat4 animation_frame;Vec4 body_position_15872,body_position_15936,position_592,up_544;std::uint32_t flags_2484;};
struct BipedAirHeightInput{Vec4 bone15,bone19,bone1,up_544,velocity_608;};
struct BipedAirResponse{bool request_52;std::optional<Vec4> restart;};
struct BipedAirThresholds{float squash=0,displacement=0,body_contact=0,arm_contact=0;};
struct BipedAirChecks
{
    BipedAirThresholds skeleton_air,offboard_air;float offboard_min_speed=0;
    bool Load(const SettingsDatabase&,std::string& error);
};
struct BipedAirPostInput{std::uint32_t flags_2484;float state_timer_2664;Vec4 forward_224,side_192;float input_2708,input_2704;};
struct BipedAirOutput
{
    float scalar_32;Vec4 vector_64;float scalar_92;Vec4 vector_96;std::uint32_t word_144;
    float scalar_148,scalar_152,scalar_156;Vec4 vector_160,vector_176,vector_192,vector_208,vector_224,vector_240;
    bool flag_320,flag_328,flag_331;
};
// The source501 state retains its three frames, initial up, active bit and
// shared cadence across Reset. Selector and landing ownership stay separate.
struct BipedAirState
{
    Mat4 frame_80=SkeletonIdentity,frame_144=SkeletonIdentity,frame_208=SkeletonIdentity;
    BipedAirTrajectoryResult result;Vec4 body_target_416{};
    float height_432=0,body_offset_436=0,blend_440=0,time_remaining_444=0,duration_448=-1;
    std::int32_t frame_452=0;Vec4 local_contact_464{},initial_up_480{},adjustment_496{},vector_512{0,0,1,0},restart_normal_528{0,0,1,0};
    std::array<bool,7> flags_544_550{{false,false,false,false,true,false,false}};BipedCadence cadence;bool active=false;
    void Reset();void BeginEnter(BipedAirEnterInput);void BeginEnterAfterReset(BipedAirEnterInput);void FinishEnter(BipedAirEnterInput);
    bool LaunchPacket(const OffboardAirLaunchInput&,const BipedControllerState&,const PointGraph<8>&,
        OffboardAirLaunchSettings,OffboardAirLaunchPacket&,std::string& error) const;
    void Exit(OffboardAirSampling&);std::int32_t BeginUpdate();void UpdateTimes();
    void UpdateCadence(BipedControllerState&,float requested_phase);BipedAirOutput Output() const;
    std::optional<Vec4> AnimationAdjustment(Vec4 animation_end_com_2880);
    void OrientSample(float start_angle_2936,std::uint32_t flags_2476);
    void CorrectHeight(BipedAirHeightInput);
    BipedAirResponse CollisionResponse(std::array<Vec4,2> errors,Vec4 up_544,bool restart_allowed_8493);
    OffboardAirLaunchPacket RestartPacket(OffboardAirLaunchPacket,Vec4 normal,Vec4 position_592,Vec4 up_544,float foot_height);
    void FinishRestart(Mat4 effective_animation_frame,Vec4 normal);void CorrectRestartedSample();
    void PostPhysics(BipedAirPostInput,const BipedAirChecks&,const WipeoutFrame&,WipeoutMode,Vec4 root_velocity,WipeoutRequests&) const;
    static float LandingAssistLimit(float elapsed_2664);void FinishLandingLatch();
private:
    void LandingOrientation(Vec4 velocity,Vec4 up,float remaining,float start_angle,std::uint32_t flags_2476);
};
float BipedAirProjectedHeight(Vec4 bone15,Vec4 bone19,Vec4 reference,Vec4 up);
void PublishBipedAirFields(BipedAirOutput,OffBoardOutputFields&);
}
