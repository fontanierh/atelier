// SPDX-License-Identifier: Apache-2.0
#include "BipedGroundRuntime.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace{Vec4 Value(RawVector w){Vec4 v;std::memcpy(v.data(),w.data(),16);return v;}}
void BipedGroundRuntime::PostPhysics(BipedRuntimeOwners v,const WipeoutFrame& frame)
{
    const auto& p=v.processed;const auto& f=v.physical;
    PostBipedGround(state,v.wipeout.state,collision_settings,{{frame,f.root_velocity,f.collision_feedback.flags.group_8,f.collision_feedback.maximum_group_8_force},p.flags_2484,Value(p.vectors_544_560_592_608[3]),f.collision_extra_errors[0],f.collision_extra_errors[1],contact.kind_164});
}
bool BipedGroundRuntime::Fill(BipedRuntimeOwners v,BipedStatePublication& out,std::string& error) const
{
    if(!result){error="Ground Fill requires completed Ground motion";return false;}
    if(!geometry_adjustment){error="Ground Fill requires this tick's real geometry consumption";return false;}
    const auto g=*geometry_adjustment;const auto position=g.frame_768.position;std::array<std::array<bool,3>,2> hands;
    for(unsigned n=0;n<2;++n)for(unsigned j=0;j<3;++j)hands[n][j]=v.feet.hands[n].flags_104_to_107[j+1];
    const auto output=PublishBipedGround(state,{{g.state_752,g.state_753,g.state_754},contact.flags_176,contact.position,{position.x,position.y,position.z,0},v.processed.flags_2476,contact.kind_164,contact.distance_168,result->velocity,result->physical_frame[1],hands});
    out=PublishBipedGroundFields(output,v.publication);error.clear();return true;
}
}
