#pragma once
#include "NativeMath.h"
#include <string>
#include <vector>

namespace atelier::skate
{
inline constexpr std::size_t SkeletonPartCount=26;
inline constexpr std::size_t SkeletonAnimationPartCount=24;
inline constexpr Mat4 SkeletonIdentity{{{1,0,0,0},{0,1,0,0},{0,0,1,0},{0,0,0,0}}};
Mat4 PhysicsBoneFrame(Quat quaternion,Vec4 translation);
Vec4 TransformSkeletonPoint(const Mat4& transform,Vec4 point);
Mat4 ComposeSkeletonAffine(const Mat4& parent,const Mat4& child);
Mat4 InverseSkeletonRigid(const Mat4& source);
bool MapAnimationParts(const std::vector<Mat4>& global_bones,
    const std::array<std::size_t,SkeletonAnimationPartCount>& bone_indices,
    const std::array<Mat4,SkeletonAnimationPartCount>& physics_frames,
    std::array<Mat4,SkeletonAnimationPartCount>& output,std::string& error);
}
