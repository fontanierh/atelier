// SPDX-License-Identifier: Apache-2.0
#include "SkeletonPhysicalRecord.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace {float Float(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}}
SkeletonPhysicalRecord::SkeletonPhysicalRecord(){pose.fill(SkeletonIdentity);}
void SkeletonPhysicalRecord::Reset(const std::array<Mat4,SkeletonPartCount>& parts)
{
    pose=parts;
    for(std::size_t i=0;i<parts.size();++i){positions[i]=parts[i][3];velocities[i]={};}
}
void SkeletonPhysicalRecord::Update(const std::array<Mat4,SkeletonPartCount>& parts,Mat4 board_frame,
    const std::array<float,SkeletonAnimationPartCount>& fractional)
{
    timestep=Float(0x3c888889);
    for(std::size_t i=0;i<parts.size();++i)
    {
        const auto& transform=i==0 ? board_frame:parts[i];pose[i]=transform;
        for(std::size_t lane=0;lane<4;++lane)
        {
            const float velocity=(transform[3][lane]-positions[i][lane])*Float(0x426fffff);
            velocity_changes[i][lane]=velocity-velocities[i][lane];velocities[i][lane]=velocity;
        }
        positions[i]=transform[3];
    }
    Vec4 position{},velocity{};
    for(std::size_t i=0;i<fractional.size();++i)for(std::size_t lane=0;lane<4;++lane)
    {
        position[lane]=std::fma(pose[i][3][lane],fractional[i],position[lane]);
        velocity[lane]=std::fma(velocities[i][lane],fractional[i],velocity[lane]);
    }
    centre_of_mass=position;centre_of_mass_velocity=velocity;
}
}
