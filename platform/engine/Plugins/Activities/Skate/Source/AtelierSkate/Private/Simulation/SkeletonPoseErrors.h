#pragma once
#include "SkeletonCollisionFeedback.h"
#include "SkeletonTargets.h"
namespace atelier::skate
{
struct SkeletonNormalError {Vec4 impulse;std::array<Vec4,2> extra;float maximum_error;};
struct SkeletonPoseErrors
{
    std::array<Vec4,SkeletonAnimationPartCount> parts{};
    std::array<Vec4,2> extra{};
    std::array<Vec4,3> targets{};
    void ResetHistory(){targets={};}
    void SetTargets(ExtraTargetPositions positions){targets={positions.com,positions.lifted_com,positions.following_com};}
    void Update(const SkeletonPhysicalRecord& physical,Mat4 animation_to_world,
        const std::array<Mat4,SkeletonAnimationPartCount>& drive_frames);
    SkeletonNormalError NormalResponse(const SkeletonCollisionFeedback& collision,Vec4 support_normal) const;
    SkeletonNormalError PartialResponse() const;
private:
    float MaximumError() const;
};
}
