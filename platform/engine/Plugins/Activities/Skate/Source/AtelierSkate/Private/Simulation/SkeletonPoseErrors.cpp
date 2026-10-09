#include "SkeletonPoseErrors.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
constexpr std::array<std::size_t,8> Candidates{{23,17,18,16,21,22,20,1}};
Vec4 Sub(Vec4 a,Vec4 b){for(std::size_t i=0;i<4;++i)a[i]-=b[i];return a;}
}
void SkeletonPoseErrors::Update(const SkeletonPhysicalRecord& physical,Mat4 animation_to_world,
    const std::array<Mat4,SkeletonAnimationPartCount>& drive_frames)
{
    parts[0]={};
    for(std::size_t part=1;part<24;++part)parts[part]=Sub(physical.pose[part][3],TransformSkeletonPoint(animation_to_world,drive_frames[part][3]));
    for(std::size_t i=0;i<2;++i)extra[i]=Sub(physical.pose[24+i][3],targets[1+i]);
}
SkeletonNormalError SkeletonPoseErrors::NormalResponse(const SkeletonCollisionFeedback& collision,Vec4 support_normal) const
{
    std::array<Vec4,8> filtered;
    for(std::size_t i=0;i<filtered.size();++i)filtered[i]=collision.FilterError(parts[Candidates[i]],support_normal);
    auto impulse=filtered[0];
    for(std::size_t i=1;i<filtered.size();++i)if(Dot3(filtered[i],filtered[i])>Dot3(impulse,impulse))impulse=filtered[i];
    return {impulse,{},MaximumError()};
}
SkeletonNormalError SkeletonPoseErrors::PartialResponse() const{return {extra[0],extra,MaximumError()};}
float SkeletonPoseErrors::MaximumError() const
{
    auto maximum=Dot3(parts[Candidates[0]],parts[Candidates[0]])>Dot3(parts[Candidates[1]],parts[Candidates[1]]) ? parts[Candidates[0]]:parts[Candidates[1]];
    for(std::size_t i=2;i<Candidates.size();++i){const auto candidate=parts[Candidates[i]];if(Dot3(candidate,candidate)>Dot3(maximum,maximum))maximum=candidate;}
    return Length3(maximum);
}
}
