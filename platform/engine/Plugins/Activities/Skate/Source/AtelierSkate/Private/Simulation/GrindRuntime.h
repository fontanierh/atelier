#pragma once
#include "GrindRuntimeSettings.h"
#include "AirStateSettings.h"
#include "GrindChromosome.h"
#include "GrindCamera.h"
#include "GraphMotionConditions.h"
#include "GroundPhaseRuntime.h"
#include "PlayerInputRuntime.h"
#include "PhysicalPhase.h"
#include "SkeletonAirRuntime.h"
#include "TrainerTuning.h"
#include "GrindFilteredOutput.h"
namespace atelier::skate
{
struct GrindPhysicalState
{
    Vec4 direction{0,1,0,0},normal{0,1,0,0},across{0,1,0,0};
    float crouch=0;bool leaving=false;std::uint32_t substate=0,classification_104=0;
    bool just_jumped=false;Vec4 jump_velocity{};bool slide_wipeout=false;Vec4 slide_impulse{};
    std::array<bool,3> tipslide_97_98_99{};
    Mat4 frame{{Vec4{{1,0,0,0}},Vec4{{0,1,0,0}},Vec4{{0,0,1,0}},Vec4{{0,0,0,0}}}};
    bool already_jumped=false;std::int32_t updates=0,leaving_updates=0;bool preparing_jump=false;
    void Enter(PlayerGrindFamily,Mat4 board);
};
// These references are the sole shared owners consumed by Ground, Air, input,
// animation and solve. This runtime owns only the six Grind states/history.
struct GrindRuntimeOwners
{
    PhysicalSimulationRuntime& physical;
    PlayerInputRuntime& input;
    GroundStateRuntime& ground;
    GroundRuntime& ground_runtime;
    GroundPhaseLifecycle& life;
    AnimatedSkeleton& animated;
    FootIk& ik;
    PhysicsAnimationInput& animation_input;
    SkeletonInputRuntime& skeleton_input;
    SkeletonAir& skeleton_air;
    AirReckoning& air_reckoning;
    WipeoutRequests& wipeout;
    AirTrajectoryRuntime& trajectory;
    const GroundSettings& ground_settings;
    const AirStateSettings& air_settings;
    const TrainerTuning& trainer;
    const std::vector<Mat4>& globals;
    SkeletonInputOwners SkeletonOwners() const {return {physical,animated,ik,animation_input};}
};
class GrindRuntime
{
public:
    std::array<GrindPhysicalState,6> states;
    std::optional<PlayerGrindFamily> active;
    bool nonspecific_active=false,nonspecific_jumped=false;
    Vec4 nonspecific_jump_velocity{};
    MotionConditionRandom orientation_random;
    GrindRuntimeSettings settings;
    std::optional<PlayerGrindObservation> manager;
    std::optional<Vec4> pending_wipeout_impulse;
    GrindChromosome chromosome;
    GrindCamera camera;
    bool Load(const SettingsDatabase&,std::string& error);
    void Observe(PlayerGrindObservation value){manager=value;}
    bool Enter(PhysicalStateId,GrindRuntimeOwners,std::string& error);
    bool Exit(GrindRuntimeOwners,std::string& error);
    bool Advance(GrindRuntimeOwners,std::string& error);
    bool Fill(GrindRuntimeOwners,std::string& error);
    bool ConditionOutputs(GrindRuntimeOwners,bool completed_riding_fakie,std::string& error);
    void ConditionCamera(GrindOutputFields& out){camera.ConditionFields(out);}
    bool Post(GrindRuntimeOwners,std::uint32_t actual_jump_fix_frames,std::string& error);
    float LastGrindDistance() const {return 0.0f;}
    static bool FilteredOutput(const GrindOutputFields&,GrindFilteredOutput&,std::string& error);
private:
    bool Execute(GrindRuntimeOwners,const PlayerGrindObservation&,std::string& error);
    bool ExecuteNonspecific(GrindRuntimeOwners,std::string& error);
    bool Contact(GrindRuntimeOwners,const PlayerGrindObservation&,std::string& error);
    bool Involuntary(GrindRuntimeOwners,const PlayerGrindObservation&,std::string& error);
    bool CollisionForce(GrindRuntimeOwners,std::optional<Vec4>& output,std::string& error);
};
// Immediate AddWorldForce82C03F98: no queue tag/capacity/force-point offset.
void ApplyGrindWorldForce(BoardRuntime&,Vec4 force,Vec4 world_point);
void GrindManageWheelSpin(BoardRuntime&,std::array<bool,4> contact);
void GrindClearWheelSpin(BoardRuntime&);
}
