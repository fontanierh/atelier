// SPDX-License-Identifier: Apache-2.0
#include "DrivePreparation.h"
#include <cassert>
#include <cstdlib>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Scalar(std::uint32_t bits) {float v;std::memcpy(&v,&bits,4);return v;}
std::uint32_t Word(float v) {std::uint32_t bits;std::memcpy(&bits,&v,4);return bits;}
}
void NormalizeDriveFrames(std::array<std::uint32_t,16>& frames)
{
    for (auto offset:{0,8})
    {
        const Vec4 q={Scalar(frames[offset]),Scalar(frames[offset+1]),Scalar(frames[offset+2]),Scalar(frames[offset+3])};
        const float inverse=InverseLengthSquared(Dot4(q,q),2);
        for (unsigned i=0;i<4;++i) frames[offset+i]=Word(q[i]*inverse);
    }
}
void NormalizeActiveDriveFrames(std::vector<std::array<std::uint32_t,16>>& frames,const std::vector<std::optional<std::size_t>>& active_frame_indices)
{
    for (auto index:active_frame_indices)
        if (index)
        {
            if (*index>=frames.size()) {assert(false && "Active drive frame index out of range");std::abort();}
            NormalizeDriveFrames(frames[*index]);
        }
}
}
