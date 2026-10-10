#include "BipedAirRuntime.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace{Vec4 Value(RawVector w){Vec4 v;std::memcpy(v.data(),w.data(),16);return v;}}
BipedAirEnterInput BipedAirRuntime::EnterInput(BipedRuntimeOwners v) const
{
    const auto& p=v.processed;return {EffectiveBipedAirFrame(v.physical.roots.animation_to_world,p.flags_2476),v.physical.board_frames.com_frame[3],v.physical.board_frames.lifted_com_frame[3],Value(p.vectors_544_560_592_608[2]),Value(p.vectors_544_560_592_608[0]),p.flags_2484};
}
BipedAirHeightInput BipedAirRuntime::HeightInput(BipedRuntimeOwners v) const
{
    const auto& p=v.processed;const auto root=v.physical.roots.animation_to_world;
    return {ComposeSkeletonAffine(root,v.physical.animation_record.pose[15])[3],ComposeSkeletonAffine(root,v.physical.animation_record.pose[19])[3],ComposeSkeletonAffine(root,v.physical.drive_frames[1])[3],Value(p.vectors_544_560_592_608[0]),Value(p.vectors_544_560_592_608[3])};
}
bool BipedAirRuntime::LaunchPacket(BipedRuntimeOwners v,const BipedGroundRuntime& ground,OffboardAirLaunchPacket& packet,std::string& error) const
{
    const auto& p=v.processed;OffboardAirLaunchInput input;
    if(!BipedRuntimeLaunchInput(v,OffboardDepartureGeometry{Value(p.grind.point_1120),Value(p.grind.direction_1136)},"BipedAir launch requires the completed BoardToolkit",input,error))return false;
    return state.LaunchPacket(input,ground.controller.state,ground.controller.settings.movement_velocity.turn_vs_speed,ground.air_launch,packet,error);
}
}
