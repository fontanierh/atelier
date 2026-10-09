#include "GrindAirPoseAdjustment.h"
#include "SkeletonSettingReader.h"
namespace atelier::skate
{
bool UpdateGrindAirPoseAdjustment(GrindAir& state,const GrindAirSettings& settings,Mat4 deck,const ProcessedPhysicsInput& p,AnimatedSkeleton& animated,AnimatedSkeletonOwners owners,const std::vector<Mat4>& globals,bool& adjusted,std::string& error)
{
    const auto decode=[](RawVector words){Vec4 v;for(unsigned i=0;i<4;++i)v[i]=detail::SkeletonSettingFloat(words[i]);return v;};adjusted=false;std::optional<GrindAirAdjustment> adjustment;
    if(!state.Update({true,deck,decode(p.vectors_400_416[0]),decode(p.vectors_720_784_800_816_832_864[0]),decode(p.vectors_544_560_592_608[0]),p.timestep_2604,p.flags_2468,p.flags_2472,p.flags_2480,p.flags_2484},settings,adjustment,error))return false;
    if(!adjustment)return true;std::array<Mat4,24> parts;
    if(!MapAnimationParts(globals,animated.settings.bone_indices,animated.settings.physics_frames,parts,error))return false;
    animated.board_offset.RefreshTransform(adjustment->LocalTransform({owners.roots.animation_to_world,owners.roots.world_to_animation,owners.board_frames.physical_board[2],parts[0][3]}));adjusted=true;return true;
}
}
