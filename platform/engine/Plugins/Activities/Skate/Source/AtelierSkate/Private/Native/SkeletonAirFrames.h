// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "SkeletonBoardFrames.h"
namespace atelier::skate
{
struct AirDismountRevert {bool requested;std::uint32_t frames;bool goofy;};
Mat4 PrepareAnimatedAirFrames(const SkeletonRootFrames&,SkeletonBoardFrames&,const Mat4& mapped_board,std::uint32_t& flags);
void UpdateKnownAirRoots(SkeletonRootFrames&,const Mat4& reckoning,Vec4 target_com,Vec4 animation_com,AirDismountRevert);
Mat4 PrepareKnownAirFrames(const SkeletonRootFrames&,SkeletonBoardFrames&,const Mat4& mapped_board,std::uint32_t& flags);
void FinishKnownAirFrames(SkeletonRootFrames&,SkeletonBoardFrames&,Mat4 effective_board);
void UpdatePlantRoots(SkeletonRootFrames&,const Mat4& reckoning,Vec4 world_anchor,Vec4 animation_anchor);
}
