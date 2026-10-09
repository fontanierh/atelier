#pragma once
#include "SkeletonCollisionMode.h"
#include "WorldContactProducer.h"
namespace atelier::skate
{
std::optional<std::vector<BoardWorldVolume>> SkeletonEnabledVolumes(const SkeletonBody&,
    const SkeletonCollisionMode&,std::string& error);
std::optional<std::vector<BoardWorldVolume>> SkeletonWorldVolumes(const SkeletonBody&,
    const SkeletonCollisionMode&,std::string& error);
void RetainSkeletonWorldVolumes(std::vector<BoardWorldVolume>&,const SkeletonCollisionMode&);
}
