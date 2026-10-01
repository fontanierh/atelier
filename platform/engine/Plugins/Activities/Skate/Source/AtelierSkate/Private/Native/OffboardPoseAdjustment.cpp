// SPDX-License-Identifier: Apache-2.0
#include "OffboardPoseAdjustment.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
std::size_t OffboardSelectedHand(std::uint32_t flags){return (flags&4)==0?1:0;}
Mat4 OffboardHandAdjustment(const Mat4& actual,const Mat4& reparented)
{return ComposeSkeletonAffine(actual,InverseSkeletonRigid(reparented));}
bool UpdateOffboardPoseAdjustment(AnimatedSkeleton& animated,const std::vector<Mat4>& globals,std::array<std::size_t,2> reparented,const ProcessedPhysicsInput& p,std::string& error)
{
    if(p.category_2512!=500||p.state_2508==503)return true;
    const auto hand=OffboardSelectedHand(p.flags_2476),actual_index=animated.settings.bone_indices[hand==0?3:7];
    if(actual_index>=globals.size()){error="Off-board pose missing actual animation hand";return false;}
    if(reparented[hand]>=globals.size()){error="Off-board pose missing board-parented animation hand";return false;}
    animated.board_offset.RefreshTransform(OffboardHandAdjustment(globals[actual_index],globals[reparented[hand]]));return true;
}
}
