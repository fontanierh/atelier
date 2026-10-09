#include "SkeletonDriveFrames.h"
#include "DrivePreparation.h"
#include <cstring>
namespace atelier::skate
{
namespace
{
DriveFrame Pack(Mat4 frame)
{
    Basis3 basis;for(std::size_t i=0;i<3;++i)for(std::size_t j=0;j<3;++j)basis.columns[i][j]=frame[i][j];
    return {QuaternionFromBasis(basis),{frame[3][0],frame[3][1],frame[3][2]}};
}
}
DriveFrames BoneDriveFrames(const Mat4& child_animation,const Mat4& inverse_child,const Mat4& inverse_parent)
{
    auto common=SkeletonIdentity;common[3]=child_animation[3];
    return {Pack(ComposeSkeletonAffine(inverse_child,common)),Pack(ComposeSkeletonAffine(inverse_parent,common))};
}
DriveFrames PrepareBoneDriveFrames(DriveFrames frames)
{
    std::array<std::uint32_t,16> words{};const std::array<DriveFrame,2> pair{{frames.body_a,frames.body_b}};
    for(std::size_t i=0;i<2;++i)
    {
        const auto q=pair[i].orientation;const auto p=pair[i].translation;
        const std::array<float,8> values{{q[0],q[1],q[2],q[3],p.x,p.y,p.z,0}};
        for(std::size_t j=0;j<8;++j)std::memcpy(&words[i*8+j],&values[j],4);
    }
    NormalizeDriveFrames(words);
    const auto frame=[&](std::size_t offset)->DriveFrame
    {
        std::array<float,7> f;for(std::size_t i=0;i<7;++i)std::memcpy(&f[i],&words[offset+i],4);
        return {{f[0],f[1],f[2],f[3]},{f[4],f[5],f[6]}};
    };
    return {frame(0),frame(8)};
}
}
