#pragma once
#include "AnimationSamples.h"
#include "PhysicsSkeleton.h"
#include "SkeletonAnimationRecord.h"
#include "SkeletonBoardFrames.h"
#include "SkeletonLanding.h"
#include "SkeletonMotion.h"
#include "Settings.h"
namespace atelier::skate
{
struct AnimatedSkeletonSettings
{
    SkeletonAnimationMasses masses;
    std::array<std::size_t,24> bone_indices{};
    std::array<Mat4,24> physics_frames{};
    std::array<std::size_t,4> target_bones{};
    PointGraph<8> landing_on_board_blend;
    LandingSettings landing;
    static std::optional<AnimatedSkeletonSettings> Load(const SettingsDatabase&,const PhysicsSkeleton&,const AnimationRig&,bool head_has_hat,std::string& error);
};
// These references are the same mutable records owned by physical simulation.
// The pose producer has no second COM, root prediction or board-frame history.
struct AnimatedSkeletonOwners
{
    SkeletonAnimationRecord& record;
    SkeletonRootFrames& roots;
    SkeletonBoardFrames& board_frames;
};
struct LandingOnBoardPoseInput{Mat4 deck;Vec4 offset;std::uint32_t flags_2480;float time;};
class AnimatedSkeleton
{
public:
    AnimatedSkeletonSettings settings;
    SkateboardOffset board_offset;
    LandingAdjustment landing;
    std::array<Mat4,4> targets{{SkeletonIdentity,SkeletonIdentity,SkeletonIdentity,SkeletonIdentity}};
    Mat4 animation_board=SkeletonIdentity,unadjusted_board=SkeletonIdentity,animation_hips=SkeletonIdentity;
    SkeletonMotion motion;
    float board_at_y_delta=0;
    explicit AnimatedSkeleton(AnimatedSkeletonSettings s):settings(std::move(s)){}
    std::array<std::size_t,2> ReparentedHandIndices() const{return {settings.target_bones[2],settings.target_bones[3]};}
    bool ProcessPose(AnimatedSkeletonOwners,const std::vector<Mat4>& actual_globals,LandingInput,float dt,
        std::uint32_t& flags_2468,std::uint32_t& flags_2472,std::optional<LandingOnBoardPoseInput>,std::string& error);
    void FinishGround(){motion.next_trajectory=SkeletonIdentity;}
};
}
