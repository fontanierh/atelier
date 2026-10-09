#pragma once
#include "PlayerInputPhase.h"
#include "PlayerInputPublication.h"
#include "PlayerPreInput.h"
#include "PlayerGrindMaterials.h"
#include "GroundRuntime.h"
#include "SkeletonInputRuntime.h"
#include <memory>
namespace atelier::skate
{
class PlayerGrindInputState;
class PlayerGrindStaticProvider;
struct PlayerGrindPending;
struct PlayerGrindObservation;
struct PlayerInputHostFrame
{
    std::uint32_t actor_query_56,actor_query_44;
    bool input_available;
    float transition_action;
    Mat4 published_board_transform;
    std::int32_t air_counter_40;
};
struct PlayerInputOwners
{
    PhysicalSimulationRuntime& physical;
    GroundRuntime& ground;
    SkeletonInputRuntime& skeleton_input;
    AnimatedSkeleton& animated;
    FootIk& ik;
    PhysicsAnimationInput& animation_input;
    const PlayerGrindMaterials& grind_materials;
    SkeletonInputOwners SkeletonOwners() const {return {physical,animated,ik,animation_input};}
};
struct PlayerInputAnimationFrame
{
    SkeletonInputPose pose;
    SkeletonInputCollision collision;
    bool air_targeting_grind_9653;
};
class PlayerInputTeleportServices
{
public:
    virtual ~PlayerInputTeleportServices()=default;
    // Complete actual whole-player reset and Ground entry. The global owner
    // supplies this implementation; failed requests remain pending unchanged.
    virtual bool Teleport(PlayerInputOwners,Mat4 target,PlayerInputState&,
        PhysicalPlayerInput&,ProcessedPhysicsInput&,std::string& error)=0;
};
struct PlayerInputStage
{
    enum class Kind {ThroughTeleport,AfterTeleport} kind;
    InputContinuation continuation;
};
// The only owner of the host's canonical player/physical/processed packets,
// retained input toolkit and pre/grind history. Physical/pose/IK owners remain
// borrowed and must be the same ones subsequently used by Ground and solve.
class PlayerInputRuntime
{
public:
    PlayerInputState player;
    PhysicalPlayerInput physical;
    ProcessedPhysicsInput processed;
    std::optional<BoardToolkit> toolkit;
    PlayerDynamicNormal dynamic_normal;
    PlayerPreInputManager pre_input;
    std::unique_ptr<PlayerGrindInputState> grind;
    std::unique_ptr<PlayerGrindPending> pending_grind;
    std::unique_ptr<PlayerGrindObservation> grind_observation;
    ~PlayerInputRuntime();
    PlayerInputRuntime(PlayerInputRuntime&&) noexcept;
    PlayerInputRuntime& operator=(PlayerInputRuntime&&) noexcept;
    PlayerInputRuntime(const PlayerInputRuntime&)=delete;
    PlayerInputRuntime& operator=(const PlayerInputRuntime&)=delete;
    static std::optional<PlayerInputRuntime> Load(const SettingsDatabase&,std::string& error);
    const std::optional<Mat4>& PendingTeleport() const {return pending_teleport_;}
    bool RequestTeleport(Mat4,std::string& error);
    ProcessedPhysicsSnapshot Snapshot(std::uint64_t tick) const {return {tick,processed};}
    void UpdateDynamicNormal(const PhysicalRidingOutputs&,Vec3 gravity);
    bool PublishBoard(const PhysicalRidingOutputs&,std::string& error);
    bool PublishGrindGraphOutputs(const SkeletonPhysicalRecord&,Vec4 reckoning_up,
        const PlayerTrajectoryGrindOwner&,std::string& error);
    bool ProcessStage(PlayerInputOwners,const Mat4& ground_frame,const AnimationInputPacket&,
        PlayerInputHostFrame,PlayerInputAnimationFrame,PlayerInputTeleportServices&,PlayerInputStage,
        const PlayerGrindStaticProvider&,std::optional<InputContinuation>& result,std::string& error);
    const PlayerDynamicNormalSettings& NormalSettings() const {return normal_settings_;}
private:
    PlayerInputRuntime();
    PlayerDynamicNormalSettings normal_settings_;
    std::optional<Mat4> pending_teleport_;
};
}
