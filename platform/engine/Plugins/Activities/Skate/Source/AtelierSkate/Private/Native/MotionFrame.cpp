// SPDX-License-Identifier: Apache-2.0
#include "MotionFrame.h"

#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Control(const IntentMap& map,std::string_view name) {const auto p=map.Get(name);return p?*p:0.0f;}
}
ActionGraphOutput ActionGraphOutput::FromHost(std::uint64_t tick,const IntentMap& action,const IntentMap& motion,
    const std::vector<AnimationAttribute>& attributes)
{
    ActionGraphOutput out;out.tick=tick;out.controls.authored_values=action;out.motion_effects=motion;
    out.animation_attributes=attributes;
    out.controls.wipeout.request=action.Contains("WipeOutRequest");
    out.controls.wipeout.air_body_tweak={Control(action,"OB_AirBodyTweakX"),Control(action,"OB_AirBodyTweakY")};
    const auto x=action.Get("WipeoutGestureX"),y=action.Get("WipeoutGestureY");
    if (x && y) out.controls.wipeout.gesture=std::array<float,2>{*x,*y};
    out.controls.board={action.Contains("OB_DropBoard"),action.Contains("OB_ThrowBoard"),action.Contains("OB_RetrieveBoard")};
    out.turning={Control(motion,"Turn"),Control(motion,"RawTurn"),Control(motion,"HardTurn")};
    return out;
}
std::array<float,2> MotionGraphFootFrame::OutDistance(bool right) const
{
    const auto& foot=right?right_foot:left_foot;Vec4 relative,z=deck_z;
    for (std::size_t i=0;i<4;++i) {relative[i]=foot[i]-deck_position[i];if (skateboard_flipped) z[i]=-z[i];}
    return {Dot3(relative,z),Dot3(relative,deck_y)};
}
}
