// SPDX-License-Identifier: Apache-2.0
#include "BipedGroundRuntime.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace{Vec4 Value(RawVector w){Vec4 v;std::memcpy(v.data(),w.data(),16);return v;}Mat4 Matrix(RawMatrix w){Mat4 m;for(unsigned n=0;n<4;++n)m[n]=Value(w[n]);return m;}}
bool BipedGroundRuntime::Enter(BipedRuntimeOwners v,std::string& error)
{
    const auto& p=v.processed;const auto previous=Matrix(p.effective_anim_transform_192);
    EnterCore({EffectiveBipedRoot(v.physical.roots.animation_to_world,p.flags_2476),Value(p.vectors_544_560_592_608[3]),p.flags_2484,p.flags_2476,
        v.animation_input.extra.biped_start_angle,v.animation_input.fields.animation_time,p.state_2504,previous[1],v.physical.board_frames.com_frame[3]},p.state_2508,previous,v.contact);
    if(p.state_2504!=500&&p.state_2504!=501&&p.state_2504!=502)
    {
        v.feet.Reset();v.ik.state.EnableFeet(false);for(auto& limb:v.ik.state.limbs){limb.board_blend=0;limb.external_blend=0;limb.mode=foot_ik::Mode::Disabled;}
    }
    v.feet.flags_304_to_307[0]=p.state_2508==502;
    if(!v.life.skeleton_controller.Request(4,v.physical.skeleton_collision,error))return false;
    v.grab.EnterReset();error.clear();return true;
}
}
