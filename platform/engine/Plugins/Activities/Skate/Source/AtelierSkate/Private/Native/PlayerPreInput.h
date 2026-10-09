#pragma once
#include "SkeletonAnimationRecord.h"
#include <string>
namespace atelier::skate
{
struct PlayerPreInputResult
{
    Vec4 position,normal;
    Mat4 frame;
    Vec4 vector96,vector112,vector128,vector144;
    float scalar160;
    std::uint32_t word164;
    float scalar168,scalar172;
    std::uint32_t word176,flags180;
    static PlayerPreInputResult Reset();
};
// Actual current host 82D81610 inactive-query owner. Pending geometry is an
// explicit source error, after result/counter reset; it is never a query miss.
struct PlayerPreInputManager
{
    bool pending_geometry=false;
    PlayerPreInputResult result=PlayerPreInputResult::Reset();
    std::array<std::uint32_t,3> result_counts{};
    bool Prepare(std::uint32_t& counter,std::string& error);
};
}
