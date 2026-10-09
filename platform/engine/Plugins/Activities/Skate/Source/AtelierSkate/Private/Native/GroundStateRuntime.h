#pragma once
#include "GroundInput.h"
#include "GroundMotion.h"
#include "GroundOutput.h"
#include "GroundPumpingRuntime.h"
#include "AnimatedSkeleton.h"
#include "FootIkTypes.h"

namespace atelier::skate
{
struct GroundEntrySettings
{
    float deck_angular_drag,powerslide_exit,landing_strength,landing_offset;
    bool Load(const SettingsDatabase&,std::string& error);
};
// The original host also borrows these lifecycle owners. These calls must
// operate on the same skeleton, air modifier and grab spline as other states.
class GroundLifecycleServices
{
public:
    virtual ~GroundLifecycleServices()=default;
    virtual bool SetSkeletonCollisionState(std::uint32_t,std::string&)=0;
    virtual bool EnterAirLandingModifier(bool stance,std::string&)=0;
    virtual bool MoveFutureDeck(Vec3 displacement,std::string&)=0;
    virtual void InvalidateOffboardGrab()=0;
};
struct GroundEntryTargets
{
    foot_ik::State& foot_ik;
    bool& skeleton_elapsed_16505;
    float& reckoning_spin_angle;
    float& reckoning_spin_speed;
    std::uint8_t& board_flags_8384;
    std::uint8_t& board_animated_290;
    std::uint32_t& wipeout_mode;
    float& wipeout_timer;
    GroundLifecycleServices& services;
};
struct GroundUpdateFrame
{
    const ProcessedPhysicsInput& processed;
    const PhysicsAnimationInput& animation;
    const PhysicalRidingOutputs& riding;
    const AnimatedSkeleton& skeleton;
    const SkeletonAnimationRecord& skeleton_record;
    const SkeletonBoardFrames& board_frames;
    const BoardToolkit& toolkit;
    std::array<AffineTransform,2> base_trucks;
    GroundInputObservations extra;
};
struct GroundUpdateTargets
{
    foot_ik::State& foot_ik;
    bool& skeleton_elapsed_16505;
    bool& board_correction_pending;
    GroundLifecycleServices& services;
};
struct GroundUpdateError
{
    enum class Stage {BeforeEntry,Pumping,Board,MoveFutureDeck} stage=Stage::BeforeEntry;
    std::string source;
    GroundBoardError board;
};
class GroundStateRuntime
{
public:
    PhysicsGroundState state;
    PumpingState pumping;
    SpeedWobbleState wobble;
    ManualState manual;
    TruckSteeringState steering;
    SpeedModelState speed{};
    float heading_previous=0;
    PumpingConfiguration pumping_settings;
    GroundOutputSettings output_settings;
    std::array<bool,5> auto_push_enabled{};
    bool entered=false;
    GroundEntrySettings entry_settings;
    bool Load(const SettingsDatabase&,bool human_player,std::string& error);
    GroundControllers Controllers();
    PhysicsGroundOutput Output(const ProcessedPhysicsInput&,const PhysicsAnimationInput&,const BoardToolkit&) const;
    bool Enter(BoardRuntime&,const ProcessedPhysicsInput&,const PhysicsAnimationInput&,
        const BoardToolkit&,GroundEntryTargets,std::string& error);
    void Exit(GroundRuntime&,PhysicalSimulationRuntime&,const ProcessedPhysicsInput&);
    std::optional<GroundBoardOutcome> Update(GroundRuntime&,BoardRuntime&,const WorldGeometry&,
        const GroundSettings&,GroundUpdateFrame,GroundPhysicalFrame,GroundUpdateTargets,GroundUpdateError&);
};
}
