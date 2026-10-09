#pragma once
#include "SkeletonTargets.h"
#include "SkeletonDriveDynamics.h"
namespace atelier::skate
{
struct SkeletonDriveSettings
{
    BoneDriveSettings bone;
    bool enabled;
    std::array<float,2> strength;
    std::array<std::array<float,2>,SkeletonAnimationPartCount> collision_strength;
};
struct BoneDrives
{
    std::array<std::size_t,2> parent;
    std::array<bool,2> active;
    std::array<DriveFrames,2> frames;
    BoneDriveDynamics dynamics;
};
struct SkeletonDriveIdentity
{
    enum class Kind {Target,Bone};
    Kind kind;
    std::size_t index,channel;
};
struct SkeletonDriveBatch {std::vector<DriveRows> rows;std::vector<SkeletonDriveIdentity> identities;std::vector<bool> spy;};
class SkeletonDrives
{
public:
    SkeletonTargets targets;
    std::array<std::optional<BoneDrives>,SkeletonAnimationPartCount> bones;
    SkeletonDriveSettings settings;
    static std::optional<SkeletonDrives> FromDefinition(
        const std::array<Mat4,SkeletonAnimationPartCount>& initial_bones,
        const std::array<Mat4,SkeletonAnimationPartCount>& initial_mapped,
        const std::array<std::optional<std::size_t>,SkeletonAnimationPartCount>& parents,
        Mat4 animation_to_world,Mat4 spawn,SimulationStep simulation,SkeletonDriveSettings settings,std::string& error);
    void Update(const std::array<Mat4,SkeletonAnimationPartCount>& pose,bool partial,float collision_weight);
    SkeletonDriveBatch Build(const std::array<BodySnapshot,SkeletonPartCount>& bodies,
        std::size_t reaction_base,std::size_t target_reaction_base,float time_step);
private:
    SkeletonDrives(SimulationStep simulation,SkeletonDriveSettings settings):targets(simulation),settings(settings){}
};
}
