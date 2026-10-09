#include "SkeletonAnimationRecord.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
SkeletonAnimationMasses SkeletonAnimationMasses::Normalize(std::array<float,SkeletonAnimationPartCount> weights)
{
    float total=0;
    for(std::size_t i=0;i<weights.size();++i)
        total=i%8==0 || i%8==7 ? weights[i]+total:total+weights[i];
    SkeletonAnimationMasses result;result.part_weights=weights;result.total=total;
    const float reciprocal=1.0f/total;
    for(std::size_t i=0;i<weights.size();++i)result.fractional[i]=weights[i]*reciprocal;
    return result;
}
SkeletonAnimationMasses SkeletonAnimationMasses::FromBoneData(std::array<Vec3,SkeletonAnimationPartCount> sizes,
    std::array<std::uint32_t,SkeletonAnimationPartCount> collision_shapes,bool head_has_hat)
{
    std::array<float,SkeletonAnimationPartCount> weights;
    for(std::size_t i=0;i<weights.size();++i)
        weights[i]=i==0 || (collision_shapes[i]>=3 && !(i==1 && head_has_hat)) ? 0.0f:(sizes[i].x*sizes[i].y)*sizes[i].z;
    return Normalize(weights);
}
SkeletonAnimationRecord::SkeletonAnimationRecord(){pose.fill(SkeletonIdentity);}
void SkeletonAnimationRecord::ResetHistory()
{centre_of_mass={};centre_of_mass_delta={};com_to_deck_world={};com_to_deck_world_delta={};}
void SkeletonAnimationRecord::Update(const std::array<Mat4,SkeletonAnimationPartCount>& input,
    const Mat4& animation_to_board,const SkeletonAnimationMasses& masses)
{
    pose=input;Vec4 com{};
    for(std::size_t part=0;part<pose.size();++part)
        for(std::size_t lane=0;lane<4;++lane)com[lane]=std::fma(pose[part][3][lane],masses.fractional[part],com[lane]);
    for(std::size_t lane=0;lane<4;++lane)centre_of_mass_delta[lane]=com[lane]-centre_of_mass[lane];
    centre_of_mass=com;
    const auto transformed_com=TransformSkeletonPoint(animation_to_board,com);
    const auto transformed_deck=TransformSkeletonPoint(animation_to_board,pose[0][3]);
    Vec4 relative;
    for(std::size_t lane=0;lane<4;++lane)
    {
        relative[lane]=transformed_com[lane]-transformed_deck[lane];
        com_to_deck_world_delta[lane]=(relative[lane]-com_to_deck_world[lane])*reset_scalar;
    }
    com_to_deck_world=relative;reset_scalar=1;
}
}
