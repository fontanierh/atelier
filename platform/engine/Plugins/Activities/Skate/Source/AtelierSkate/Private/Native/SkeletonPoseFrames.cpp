// SPDX-License-Identifier: Apache-2.0
#include "SkeletonPoseFrames.h"
#include "RigidBody.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
Mat4 PhysicsBoneFrame(Quat quaternion,Vec4 translation)
{
    const auto basis=BasisFromQuaternion(quaternion);const auto& ri=basis.columns[0];
    const auto& up=basis.columns[1];const auto& at=basis.columns[2];
    return {{{ri[0],ri[1],ri[2],at[2]},{up[0],up[1],up[2],up[0]},
        {at[0],at[1],at[2],ri[1]},translation}};
}
Vec4 TransformSkeletonPoint(const Mat4& transform,Vec4 point)
{
    Vec4 result;
    for(std::size_t i=0;i<4;++i)
    {
        const float x=std::fma(transform[0][i],point[0],transform[3][i]);
        const float y=std::fma(transform[1][i],point[1],x);
        result[i]=std::fma(transform[2][i],point[2],y);
    }
    return result;
}
Mat4 ComposeSkeletonAffine(const Mat4& parent,const Mat4& child)
{
    Mat4 result;
    for(std::size_t column=0;column<4;++column)
    {
        if(column==3){result[column]=TransformSkeletonPoint(parent,child[3]);continue;}
        for(std::size_t lane=0;lane<4;++lane)
        {
            const float x=child[column][0]*parent[0][lane];
            const float y=std::fma(child[column][1],parent[1][lane],x);
            result[column][lane]=std::fma(child[column][2],parent[2][lane],y);
        }
    }
    return result;
}
Mat4 InverseSkeletonRigid(const Mat4& source)
{
    Mat4 result=SkeletonIdentity;
    for(std::size_t axis=0;axis<3;++axis)result[axis]={source[0][axis],source[1][axis],source[2][axis],0};
    const Vec4 translation{0.0f-source[3][0],0.0f-source[3][1],0.0f-source[3][2],0.0f-source[3][3]};
    for(std::size_t i=0;i<4;++i)
    {
        const float z=translation[2]*result[2][i];
        const float y=std::fma(translation[1],result[1][i],z);
        result[3][i]=std::fma(translation[0],result[0][i],y);
    }
    return result;
}
bool MapAnimationParts(const std::vector<Mat4>& global_bones,
    const std::array<std::size_t,SkeletonAnimationPartCount>& bone_indices,
    const std::array<Mat4,SkeletonAnimationPartCount>& physics_frames,
    std::array<Mat4,SkeletonAnimationPartCount>& output,std::string& error)
{
    for(const auto i:bone_indices)if(i>=global_bones.size())
    {error="physics skeleton bone index is outside the animation hierarchy";return false;}
    for(std::size_t part=0;part<SkeletonAnimationPartCount;++part)
        output[part]=ComposeSkeletonAffine(global_bones[bone_indices[part]],physics_frames[part]);
    error.clear();return true;
}
}
