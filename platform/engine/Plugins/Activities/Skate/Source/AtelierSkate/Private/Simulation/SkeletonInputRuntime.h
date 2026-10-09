#pragma once
#include "PhysicalSimulationRuntime.h"
#include "AnimatedSkeleton.h"
#include "FootIk.h"
#include "GrindAir.h"
#include "PhysicsAnimationInput.h"
#include "PlayerInputTypes.h"
#include "SkeletonWobble.h"
namespace atelier::skate
{
// All four references belong to the same player subsequently used by Ground,
// the shared physical solve and pose publication.
struct SkeletonInputOwners
{
    PhysicalSimulationRuntime& physical;
    AnimatedSkeleton& animated;
    FootIk& ik;
    PhysicsAnimationInput& animation_input;
    AnimatedSkeletonOwners AnimationOwners() const
    {return {physical.animation_record,physical.roots,physical.board_frames};}
};
struct SkeletonInputCollision
{
    bool contact_4070,has_pose_error_4077;
    Vec4 pose_error_16272;
    bool partial_ragdoll;
    float drive_weight_4028;
};
struct SkeletonInputPose
{
    const std::vector<Mat4>& globals;
    const std::vector<AnimationAttribute>& attributes;
    ActionMap& actions;
};
class SkeletonInputRuntime
{
public:
    // Root derivatives, target caches and drive frames are borrowed from
    // physical, rather than copied into a second persistent history.
    bool reenable_requested=false,teleporting=false;
    std::uint32_t force_mode=0;
    std::array<Vec4,8> head_tracking_history{};
    bool head_tracking_active=false;
    bool grind_air_started=false,grind_air_active=false,grind_air_adjusting=false;
    GrindAir grind_air;
    static std::optional<SkeletonInputRuntime> Load(const SettingsDatabase&,std::string& error);
    bool ProcessData(const BoardToolkit&,const AnimationInputPacket&,PhysicalPlayerInput&,
        ProcessedPhysicsInput&,SkeletonInputOwners,SkeletonInputPose,const SkeletonInputCollision&,std::string& error);
    bool GeneralUpdate(const ProcessedPhysicsInput&,SkeletonInputOwners,const std::vector<Mat4>& actual_globals,
        const SkeletonInputCollision&,std::array<Mat4,24>& actual_drives,std::string& error);
    bool UpdateGround(const Mat4& reckoning,ProcessedPhysicsInput&,SkeletonInputOwners,
        const std::vector<Mat4>& actual_globals,const SkeletonInputCollision&,Mat4& frame,std::string& error);
    bool UpdateTeleport(const Mat4& reckoning,ProcessedPhysicsInput&,SkeletonInputOwners,
        const std::vector<Mat4>& actual_globals,const SkeletonInputCollision&,Mat4& frame,std::string& error);
    void ResetForTeleport(SkeletonInputOwners,SkeletonWobble&,bool& ground_elapsed_16505);
private:
    std::optional<GrindAirSettings> grind_air_settings_;
};
}
