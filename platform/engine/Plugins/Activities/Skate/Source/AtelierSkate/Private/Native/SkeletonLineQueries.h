#pragma once
#include "PlayerInputTypes.h"
#include "SkeletonBody.h"
#include "WorldGeometry.h"
namespace atelier::skate
{
struct SkeletonLineHit
{
    Vec4 position{},normal{{0,1,0,0}};
    std::uint32_t surface=0;
    bool hit=false;
    float collision_time=-1;
};
struct SkeletonLineTests
{
    SkeletonLineHit hips;
    std::array<SkeletonLineHit,2> feet;
    void Publish(PlayerInputState&) const;
};
// Concrete original world traversal, radius-bearing trajectory and source hit
// selection. Results are retained until the input owner copies them next tick.
bool QuerySkeletonLines(const WorldGeometry&,const SkeletonBody&,SkeletonLineTests&,std::string& error);
}
