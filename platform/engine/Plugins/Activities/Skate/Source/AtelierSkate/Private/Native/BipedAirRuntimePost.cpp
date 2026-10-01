// SPDX-License-Identifier: Apache-2.0
#include "BipedAirRuntime.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace{Vec4 Value(RawVector w){Vec4 v;std::memcpy(v.data(),w.data(),16);return v;}}
bool BipedAirRuntime::PostPhysics(BipedRuntimeOwners v,const WipeoutFrame& frame,std::string& error)
{
    if(!v.landing.PostPhysics({v.processed,v.toolkit},error))return false;const auto& p=v.processed;
    if(p.state_variant_index_2528>=v.wipeout.modes.size()){error="Undefined wipeout physics mode "+std::to_string(p.state_variant_index_2528);return false;}
    state.PostPhysics({p.flags_2484,p.state_timer_2664,Value(p.effective_anim_transform_192[2]),Value(p.effective_anim_transform_192[0]),v.animation_input.extra.look_y,v.animation_input.extra.look_x},checks,frame,v.wipeout.modes[p.state_variant_index_2528],v.physical.root_velocity,v.wipeout.state);
    error.clear();return true;
}
}
