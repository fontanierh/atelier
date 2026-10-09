#pragma once
#include "SkeletonBody.h"
#include "SkeletonDriveFrames.h"
namespace atelier::skate
{
inline constexpr std::size_t SkeletonTargetCount=4;
inline constexpr std::array<std::size_t,SkeletonTargetCount> SkeletonTargetParts{{23,0,24,25}};
struct SkeletonTargetInput
{
    const Mat4& animation_hips;
    const Mat4& animation_board;
    const Mat4& animation_to_world;
    const Mat4& inverse_board;
    const Mat4& skate_root;
    const Mat4& com_frame;
    const Mat4& lifted_com_frame;
    bool teleporting;
};
struct ExtraTargetPositions {Vec4 com,lifted_com,following_com;};
struct SkeletonTargetUpdate {Mat4 animation_board_to_physics;ExtraTargetPositions positions;bool continuous;};
struct SkeletonTargets
{
    std::array<BodySnapshot,SkeletonTargetCount> bodies;
    std::array<DriveFrames,SkeletonTargetCount> frames;
    std::array<DriveDynamics,SkeletonTargetCount> dynamics;
    explicit SkeletonTargets(SimulationStep simulation);
    void Reset(Mat4 hips,Mat4 spawn);
    void SetTransform(std::size_t index,Mat4 frame);
    Mat4 Transform(std::size_t index) const;
    void ApplyFutureDeckDisplacement(Vec3 displacement);
    Mat4 UpdateHookPositions(const SkeletonTargetInput& input);
    ExtraTargetPositions UpdateExtraTargets(SkeletonBody& skeleton,const Mat4& com_frame,const Mat4& lifted_com_frame);
    SkeletonTargetUpdate UpdatePositions(SkeletonTargetInput input,SkeletonBody& skeleton);
};
}
